"""Disabled-by-default fixed-host Binance private HTTPS transport."""

from dataclasses import dataclass
import hashlib
import http.client
import ssl
from typing import Optional, Tuple

from .canonical import canonical_json
from .challenger_replacement_binance_credential import (
    BinanceCredentialCapability, _consume_binance_authorization,
)
from .challenger_replacement_binance_private_contract import (
    BinancePrivateActivation, load_binance_private_activation_bytes,
)
from .challenger_replacement_binance_private_protocol import (
    BinancePrivateRequest, classify_binance_private_response,
)

_MAX_BODY = 1_048_576
_TIMEOUT = 5.0


class BinancePrivateTransportError(RuntimeError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.close_failure_reason_code = None


@dataclass(frozen=True)
class BinancePrivateTransportResult:
    response_class: str
    status_or_null: Optional[int]
    body: bytes
    response_sha256: str
    rate_limit_headers: Tuple[Tuple[str, str], ...]


def _fail(reason, error=None):
    failure = BinancePrivateTransportError(reason)
    if error is None:
        raise failure
    raise failure from error


def _activation_document(activation):
    return {
        "$schema": "./challenger-replacement-binance-private-activation-v1.schema.json",
        "schema_version": "1.0.0",
        "activation_id": activation.activation_id,
        "build_identity": dict(activation.build_identity),
        "configuration_sha256": activation.configuration_sha256,
        "account_approval_sha256": activation.account_approval_sha256,
        "block_id": activation.block_id,
        "stage": activation.stage,
        "capital_usdt": activation.capital_usdt,
        "max_gross_exposure_usdt": activation.max_gross_exposure_usdt,
        "max_leverage": activation.max_leverage,
        "expires_at": activation.expires_at,
        "production_activation": activation.production_activation,
    }


def _require_authority(activation, expected_build_identity, now):
    try:
        if not isinstance(activation, BinancePrivateActivation):
            raise ValueError
        document = _activation_document(activation)
        loaded = load_binance_private_activation_bytes(
            (canonical_json(document) + "\n").encode("utf-8"),
            build_identity=expected_build_identity,
            now=now,
        )
        if loaded != activation or loaded.production_activation is not True:
            raise ValueError
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_TRANSPORT_NOT_AUTHORIZED", error)


def _result(response_class, status, body=b"", headers=()):
    return BinancePrivateTransportResult(
        response_class=response_class,
        status_or_null=status,
        body=body,
        response_sha256=hashlib.sha256(body).hexdigest(),
        rate_limit_headers=headers,
    )


def _selected_headers(raw_headers):
    selected = {}
    for name, value in raw_headers:
        if not isinstance(name, str) or not isinstance(value, str):
            _fail("BINANCE_PRIVATE_TRANSPORT_RESPONSE_INVALID")
        lowered = name.lower()
        if lowered in {
            "retry-after", "x-mbx-used-weight-1m",
            "x-mbx-order-count-10s", "x-mbx-order-count-1m",
        }:
            if lowered in selected:
                _fail("BINANCE_PRIVATE_TRANSPORT_RESPONSE_INVALID")
            selected[lowered] = value
    return tuple(sorted(selected.items()))


def execute_binance_private_request(
    request, *, credential, activation, expected_build_identity, now
):
    """Execute one authorized request exactly once; never follow or retry."""

    _require_authority(activation, expected_build_identity, now)
    if not isinstance(credential, BinanceCredentialCapability):
        _fail("BINANCE_PRIVATE_TRANSPORT_NOT_AUTHORIZED")
    authorization = credential.authorize(request)
    connection = None
    primary = None
    try:
        with authorization:
            frozen, api_key, parameters = _consume_binance_authorization(
                authorization
            )
            context = ssl.create_default_context()
            try:
                connection = http.client.HTTPSConnection(
                    frozen.host, port=443, timeout=_TIMEOUT, context=context
                )
            except (OSError, ssl.SSLError) as error:
                _fail("BINANCE_PRIVATE_TRANSPORT_CONNECT_FAILED", error)
            headers = {"X-MBX-APIKEY": bytes(api_key).decode("ascii")}
            if frozen.method == "POST":
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                target, body = frozen.path, bytes(parameters)
            else:
                target, body = frozen.path + "?" + bytes(parameters).decode("ascii"), None
            try:
                connection.request(frozen.method, target, body=body, headers=headers)
                response = connection.getresponse()
                response_body = response.read(_MAX_BODY + 1)
            except (OSError, TimeoutError, ssl.SSLError, http.client.HTTPException):
                return _result(
                    "UNKNOWN" if frozen.mutating else "TRANSIENT_QUERY_FAILURE",
                    None,
                )
            if not isinstance(response_body, bytes):
                _fail("BINANCE_PRIVATE_TRANSPORT_RESPONSE_INVALID")
            if len(response_body) > _MAX_BODY:
                _fail("BINANCE_PRIVATE_TRANSPORT_RESPONSE_TOO_LARGE")
            try:
                selected = _selected_headers(response.getheaders())
                classified = classify_binance_private_response(
                    frozen, status=response.status, body=response_body,
                    headers=dict(selected),
                )
            except BinancePrivateTransportError:
                raise
            except (AttributeError, TypeError, ValueError) as error:
                _fail("BINANCE_PRIVATE_TRANSPORT_RESPONSE_INVALID", error)
            return _result(
                classified["response_class"], response.status, response_body,
                classified["rate_limit_headers"],
            )
    except BinancePrivateTransportError as error:
        primary = error
        raise
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, ssl.SSLError) as error:
                if primary is None:
                    _fail("BINANCE_PRIVATE_TRANSPORT_CLOSE_FAILED", error)
                primary.close_failure_reason_code = (
                    "BINANCE_PRIVATE_TRANSPORT_CLOSE_FAILED"
                )
