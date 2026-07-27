"""Replayable current Binance account commission evidence."""

import hashlib
import hmac
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_decimal, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .market_data_cli import _publish_immutable
from .runtime_health import (
    RuntimeHealthError,
    VerifiedRuntimeGate,
    open_verified_runtime_gate,
    server_time_probe_reasons,
    server_time_probe_trust_hash,
)


_PLAN_TOKEN = object()
_REQUEST_TOKEN = object()
_SIGNED_TOKEN = object()
_CAPTURE_TOKEN = object()
_SIGNER_TOKEN = object()
_RECV_WINDOW_MS = 5000
_MAX_BODY_BYTES = 65_536
_READ_CHUNK_BYTES = 16_384
_HTTP_TIMEOUT_SECONDS = 10
_VALIDITY_HOURS = 4
_ATTESTATION_TYPE = "ACCOUNT_COMMISSION_SNAPSHOT_ATTESTATION"
_API_KEY_FILE_ENV = "CRYPTO_QUANT_BINANCE_READONLY_API_KEY_FILE"
_API_SECRET_FILE_ENV = "CRYPTO_QUANT_BINANCE_READONLY_API_SECRET_FILE"
_WARNINGS = (
    "CURRENT_RATES_DO_NOT_AUTHORIZE_HISTORICAL_BACKFILL",
    "BNB_DISCOUNT_SCENARIO_NOT_ACCOUNTED",
    "EXTERNAL_PRODUCTION_APPROVAL_NOT_IMPLEMENTED",
    "BALANCES_POSITIONS_ORDERS_AND_FILLS_NOT_CAPTURED",
    "CREDENTIAL_PROCESS_MEMORY_CANNOT_BE_PROVEN_ZEROIZED",
    "AI_MODEL_NOT_RUN",
)
_REQUIRED_PERMISSION_FIELDS = frozenset(
    (
        "ipRestrict",
        "createTime",
        "enableWithdrawals",
        "enableInternalTransfer",
        "permitsUniversalTransfer",
        "enableVanillaOptions",
        "enableReading",
        "enableFutures",
        "enableMargin",
        "enableSpotAndMarginTrading",
    )
)
_NON_PERMISSION_INTEGER_FIELDS = frozenset(
    ("createTime", "tradingAuthorityExpirationTime")
)


class AccountCommissionError(ValueError):
    """The account commission evidence flow failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> Tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_TIME_INVALID"
            ) from error
    else:
        raise AccountCommissionError("ACCOUNT_COMMISSION_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AccountCommissionError("ACCOUNT_COMMISSION_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    converted = converted.replace(
        microsecond=(converted.microsecond // 1000) * 1000
    )
    return converted, utc_datetime(converted)


def _epoch_ms(value: object) -> int:
    parsed, _ = _utc(value)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return int((parsed - epoch) // timedelta(milliseconds=1))


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > 80:
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_DECIMAL_INVALID"
        )
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_DECIMAL_INVALID"
        ) from error
    if (
        not number.is_finite()
        or number < 0
        or number > 1
        or (number.is_zero() and number.is_signed())
        or canonical_decimal(number) != value
    ):
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_DECIMAL_INVALID"
        )
    return number


def _render(value: Decimal) -> str:
    return canonical_decimal(value)


@dataclass(frozen=True, init=False)
class AccountCommissionRequest:
    family: str
    host: str
    path: str
    symbol_or_null: Optional[str]

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _REQUEST_TOKEN:
            raise TypeError(
                "AccountCommissionRequest is issued by its frozen plan"
            )
        for name in ("family", "host", "path", "symbol_or_null"):
            object.__setattr__(self, name, kwargs[name])

    def business_payload(self) -> Dict[str, Any]:
        return {
            "family": self.family,
            "method": "GET",
            "host": self.host,
            "path": self.path,
            "symbol_or_null": self.symbol_or_null,
            "security_type": "USER_DATA_SIGNED",
        }


def _request(
    family: str,
    host: str,
    path: str,
    symbol_or_null: Optional[str],
) -> AccountCommissionRequest:
    return AccountCommissionRequest(
        family=family,
        host=host,
        path=path,
        symbol_or_null=symbol_or_null,
        _token=_REQUEST_TOKEN,
    )


@dataclass(frozen=True, init=False)
class AccountCommissionPlan:
    schema_version: str
    plan_id: str
    symbol: str
    recv_window_ms: int
    requests: Tuple[AccountCommissionRequest, ...]

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _PLAN_TOKEN:
            raise TypeError("AccountCommissionPlan must be created with create")
        object.__setattr__(self, "schema_version", "1.0.0")
        object.__setattr__(
            self,
            "plan_id",
            "ethusdt-current-account-commission-evidence-v1",
        )
        object.__setattr__(self, "symbol", "ETHUSDT")
        object.__setattr__(self, "recv_window_ms", _RECV_WINDOW_MS)
        object.__setattr__(
            self,
            "requests",
            (
                _request(
                    "API_KEY_RESTRICTIONS",
                    "api.binance.com",
                    "/sapi/v1/account/apiRestrictions",
                    None,
                ),
                _request(
                    "SPOT_ACCOUNT_COMMISSION",
                    "api.binance.com",
                    "/api/v3/account/commission",
                    "ETHUSDT",
                ),
                _request(
                    "USD_M_ACCOUNT_COMMISSION",
                    "fapi.binance.com",
                    "/fapi/v1/commissionRate",
                    "ETHUSDT",
                ),
            ),
        )

    @classmethod
    def create(
        cls, *, symbol: str = "ETHUSDT"
    ) -> "AccountCommissionPlan":
        if symbol != "ETHUSDT":
            raise AccountCommissionError("ACCOUNT_COMMISSION_PLAN_INVALID")
        return cls(_token=_PLAN_TOKEN)

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "symbol": self.symbol,
            "recv_window_ms": self.recv_window_ms,
            "server_time_request_count": 3,
            "signed_request_count": len(self.requests),
            "automatic_retry_count": 0,
            "requests": [
                request.business_payload() for request in self.requests
            ],
        }

    @property
    def plan_hash(self) -> str:
        return business_hash(self.business_payload())


class HmacAccountSigner:
    """Opaque HMAC signer whose representation never includes credentials."""

    __slots__ = ("_api_key", "_secret", "_closed", "_fingerprint")

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _SIGNER_TOKEN:
            raise TypeError("HmacAccountSigner is loaded by the credential gate")
        api_key = kwargs["api_key"]
        secret = kwargs["secret"]
        if not isinstance(api_key, bytearray) or not isinstance(
            secret, bytearray
        ):
            raise AccountCommissionError(
                "ACCOUNT_CREDENTIAL_FORMAT_INVALID"
            )
        self._api_key = api_key
        self._secret = secret
        self._closed = False
        self._fingerprint = hashlib.sha256(bytes(api_key)).hexdigest()

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def api_key_header(self) -> str:
        if self._closed:
            raise AccountCommissionError("ACCOUNT_CREDENTIAL_CLOSED")
        try:
            return bytes(self._api_key).decode("ascii")
        except UnicodeDecodeError as error:
            raise AccountCommissionError(
                "ACCOUNT_CREDENTIAL_FORMAT_INVALID"
            ) from error

    def sign(self, payload: bytes) -> str:
        if self._closed or not isinstance(payload, bytes):
            raise AccountCommissionError("ACCOUNT_CREDENTIAL_CLOSED")
        return hmac.new(
            bytes(self._secret), payload, hashlib.sha256
        ).hexdigest()

    def close(self) -> None:
        for buffer in (self._secret, self._api_key):
            for index in range(len(buffer)):
                buffer[index] = 0
        self._closed = True

    def __enter__(self) -> "HmacAccountSigner":
        if self._closed:
            raise AccountCommissionError("ACCOUNT_CREDENTIAL_CLOSED")
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            "HmacAccountSigner("
            f"fingerprint={self._fingerprint[:12]}...,closed={self._closed})"
        )


def _create_test_signer(
    api_key: str = "A" * 32,
    secret: str = "B" * 32,
) -> HmacAccountSigner:
    """Create an injected signer for deterministic tests only."""

    return HmacAccountSigner(
        api_key=bytearray(api_key.encode("ascii")),
        secret=bytearray(secret.encode("ascii")),
        _token=_SIGNER_TOKEN,
    )


def _inside(path: Path, boundary: Path) -> bool:
    try:
        path.relative_to(boundary)
        return True
    except ValueError:
        return False


def _credential_bytes(
    environment_name: str,
    *,
    output_root: Path,
    workspace_root: Path,
) -> bytearray:
    raw_path = os.environ.get(environment_name)
    if not raw_path or "\x00" in raw_path:
        raise AccountCommissionError("ACCOUNT_CREDENTIAL_FILE_REQUIRED")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise AccountCommissionError("ACCOUNT_CREDENTIAL_FILE_INVALID")
    descriptor = None
    try:
        entry = path.lstat()
        resolved = path.resolve(strict=True)
        descriptor = os.open(
            str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
        opened = os.fstat(descriptor)
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise AccountCommissionError(
            "ACCOUNT_CREDENTIAL_FILE_INVALID"
        ) from error
    if (
        stat.S_ISLNK(entry.st_mode)
        or not stat.S_ISREG(entry.st_mode)
        or not stat.S_ISREG(opened.st_mode)
        or (entry.st_dev, entry.st_ino)
        != (opened.st_dev, opened.st_ino)
        or opened.st_nlink != 1
        or entry.st_uid != os.getuid()
        or stat.S_IMODE(entry.st_mode) != 0o600
        or entry.st_size < 16
        or entry.st_size > 512
        or _inside(resolved, Path(output_root).resolve())
        or _inside(resolved, Path(workspace_root).resolve())
    ):
        os.close(descriptor)
        raise AccountCommissionError("ACCOUNT_CREDENTIAL_FILE_INVALID")
    try:
        body = bytearray()
        while len(body) <= entry.st_size:
            chunk = os.read(
                descriptor, min(512, entry.st_size - len(body) + 1)
            )
            if not chunk:
                break
            body.extend(chunk)
        final_opened = os.fstat(descriptor)
        final_entry = path.lstat()
    except OSError as error:
        raise AccountCommissionError(
            "ACCOUNT_CREDENTIAL_FILE_INVALID"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        len(body) != entry.st_size
        or (final_opened.st_dev, final_opened.st_ino)
        != (opened.st_dev, opened.st_ino)
        or (final_entry.st_dev, final_entry.st_ino)
        != (opened.st_dev, opened.st_ino)
    ):
        raise AccountCommissionError("ACCOUNT_CREDENTIAL_FILE_INVALID")
    if body.endswith(b"\n"):
        body = body[:-1]
    if (
        len(body) < 16
        or len(body) > 256
        or b"\n" in body
        or b"\r" in body
        or any(value < 33 or value > 126 for value in body)
    ):
        raise AccountCommissionError("ACCOUNT_CREDENTIAL_FORMAT_INVALID")
    return body


def load_account_signer_from_environment(
    *,
    output_root: Path,
    workspace_root: Optional[Path] = None,
) -> HmacAccountSigner:
    """Load an owner-only read credential without accepting secret values."""

    workspace = Path(workspace_root or Path.cwd()).resolve()
    api_key = _credential_bytes(
        _API_KEY_FILE_ENV,
        output_root=output_root,
        workspace_root=workspace,
    )
    try:
        secret = _credential_bytes(
            _API_SECRET_FILE_ENV,
            output_root=output_root,
            workspace_root=workspace,
        )
    except Exception:
        for index in range(len(api_key)):
            api_key[index] = 0
        raise
    return HmacAccountSigner(
        api_key=api_key,
        secret=secret,
        _token=_SIGNER_TOKEN,
    )


@dataclass(frozen=True, init=False)
class SignedAccountCommissionRequest:
    request: AccountCommissionRequest
    timestamp_ms: int
    unsigned_query: str
    signature: str
    api_key_fingerprint: str

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _SIGNED_TOKEN:
            raise TypeError("Signed request must be issued by the signer")
        for name in (
            "request",
            "timestamp_ms",
            "unsigned_query",
            "signature",
            "api_key_fingerprint",
        ):
            object.__setattr__(self, name, kwargs[name])

    @property
    def signed_query(self) -> str:
        return self.unsigned_query + "&signature=" + self.signature

    @property
    def url(self) -> str:
        return (
            "https://"
            + self.request.host
            + self.request.path
            + "?"
            + self.signed_query
        )

    def redacted_payload(self) -> Dict[str, Any]:
        return {
            **self.request.business_payload(),
            "timestamp_ms": self.timestamp_ms,
            "recv_window_ms": _RECV_WINDOW_MS,
            "unsigned_query_sha256": hashlib.sha256(
                self.unsigned_query.encode("ascii")
            ).hexdigest(),
            "signed_query_sha256": hashlib.sha256(
                self.signed_query.encode("ascii")
            ).hexdigest(),
            "api_key_fingerprint": self.api_key_fingerprint,
        }

    def __repr__(self) -> str:
        return (
            "SignedAccountCommissionRequest("
            f"family={self.request.family},redacted=True)"
        )


def _unsigned_query(
    request: AccountCommissionRequest, timestamp_ms: int
) -> str:
    if (
        isinstance(timestamp_ms, bool)
        or not isinstance(timestamp_ms, int)
        or timestamp_ms < 0
        or timestamp_ms > (1 << 53) - 1
    ):
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_TIMESTAMP_INVALID"
        )
    parameters = []
    if request.symbol_or_null is not None:
        parameters.append(("symbol", request.symbol_or_null))
    parameters.extend(
        (("recvWindow", _RECV_WINDOW_MS), ("timestamp", timestamp_ms))
    )
    return urlencode(parameters)


def sign_account_commission_request(
    request: AccountCommissionRequest,
    timestamp_ms: int,
    signer: HmacAccountSigner,
) -> SignedAccountCommissionRequest:
    if (
        request not in AccountCommissionPlan.create().requests
        or not isinstance(signer, HmacAccountSigner)
    ):
        raise AccountCommissionError("ACCOUNT_COMMISSION_REQUEST_INVALID")
    unsigned = _unsigned_query(request, timestamp_ms)
    return SignedAccountCommissionRequest(
        request=request,
        timestamp_ms=timestamp_ms,
        unsigned_query=unsigned,
        signature=signer.sign(unsigned.encode("ascii")),
        api_key_fingerprint=signer.fingerprint,
        _token=_SIGNED_TOKEN,
    )


@dataclass(frozen=True)
class AccountCommissionHttpResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes
    request_started_at: str
    response_received_at: str


class _RejectRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise AccountCommissionError("ACCOUNT_COMMISSION_REDIRECT_BLOCKED")


def _read_bounded(response: object) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = response.read(
            min(_READ_CHUNK_BYTES, _MAX_BODY_BYTES - total + 1)
        )
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_BODY_BYTES:
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_RESPONSE_TOO_LARGE"
            )
        chunks.append(chunk)
    return b"".join(chunks)


class BinanceAccountCommissionTransport:
    """No-retry signed GET transport for the three frozen requests."""

    def __init__(self, *, clock, opener=None):
        if not callable(clock):
            raise AccountCommissionError("ACCOUNT_COMMISSION_CLOCK_INVALID")
        self._clock = clock
        self._opener = opener or build_opener(
            ProxyHandler({}), _RejectRedirectHandler()
        )
        self.calls = 0

    def get(
        self,
        request: SignedAccountCommissionRequest,
        api_key_header: str,
    ) -> AccountCommissionHttpResponse:
        if (
            not isinstance(request, SignedAccountCommissionRequest)
            or not isinstance(api_key_header, str)
            or not api_key_header
        ):
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_REQUEST_INVALID"
            )
        self.calls += 1
        started = self._clock()
        try:
            with self._opener.open(
                Request(
                    request.url,
                    method="GET",
                    headers={
                        "Accept": "application/json",
                        "X-MBX-APIKEY": api_key_header,
                        "User-Agent": (
                            "crypto-quant-account-commission/0.22"
                        ),
                    },
                ),
                timeout=_HTTP_TIMEOUT_SECONDS,
            ) as response:
                return AccountCommissionHttpResponse(
                    status=response.getcode(),
                    final_url=response.geturl(),
                    headers=dict(response.headers.items()),
                    body=_read_bounded(response),
                    request_started_at=started,
                    response_received_at=self._clock(),
                )
        except HTTPError as error:
            return AccountCommissionHttpResponse(
                status=error.code,
                final_url=error.geturl(),
                headers=dict(error.headers.items()) if error.headers else {},
                body=b"",
                request_started_at=started,
                response_received_at=self._clock(),
            )
        except AccountCommissionError:
            raise
        except (OSError, TimeoutError, URLError) as error:
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_TRANSPORT_FAILURE"
            ) from error


def _strict_json(body: bytes) -> object:
    if not isinstance(body, bytes) or len(body) > _MAX_BODY_BYTES:
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_RESPONSE_INVALID"
        )

    def reject_float(_value):
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_JSON_FLOAT_FORBIDDEN"
        )

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise AccountCommissionError(
                    "ACCOUNT_COMMISSION_JSON_DUPLICATE_KEY"
                )
            result[key] = value
        return result

    try:
        return json.loads(
            body.decode("utf-8"),
            parse_float=reject_float,
            parse_constant=reject_float,
            object_pairs_hook=object_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_RESPONSE_INVALID"
        ) from error


def _matches_signed_url(
    value: object, request: SignedAccountCommissionRequest
) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        query = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
        )
    except (ValueError, TypeError):
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == request.request.host
        and parsed.port is None
        and parsed.username is None
        and parsed.password is None
        and parsed.path == request.request.path
        and not parsed.fragment
        and urlencode(query) == request.signed_query
    )


def _selected_headers(headers: object) -> Dict[str, Optional[str]]:
    if not isinstance(headers, Mapping):
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_RESPONSE_INVALID"
        )
    lowered = {}
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_RESPONSE_INVALID"
            )
        lowered[name.lower()] = value
    return {
        "http_date_or_null": lowered.get("date"),
        "retry_after_or_null": lowered.get("retry-after"),
        "used_weight_1m_or_null": lowered.get("x-mbx-used-weight-1m"),
    }


def _receipt(
    request: SignedAccountCommissionRequest,
    response: AccountCommissionHttpResponse,
) -> Dict[str, Any]:
    if (
        not isinstance(response, AccountCommissionHttpResponse)
        or isinstance(response.status, bool)
        or response.status != 200
        or not _matches_signed_url(response.final_url, request)
        or not isinstance(response.body, bytes)
        or len(response.body) > _MAX_BODY_BYTES
    ):
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_RESPONSE_INVALID"
        )
    started, started_text = _utc(response.request_started_at)
    received, received_text = _utc(response.response_received_at)
    if received < started:
        raise AccountCommissionError("ACCOUNT_COMMISSION_CLOCK_INVALID")
    timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
        milliseconds=request.timestamp_ms
    )
    if timestamp > received + timedelta(seconds=1) or (
        received - timestamp
    ) > timedelta(milliseconds=_RECV_WINDOW_MS):
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_TIMESTAMP_OUTSIDE_WINDOW"
        )
    _strict_json(response.body)
    receipt = {
        "request": request.redacted_payload(),
        "status": response.status,
        "final_host": request.request.host,
        "final_path": request.request.path,
        "selected_headers": _selected_headers(response.headers),
        "response_body_utf8": response.body.decode("utf-8"),
        "response_body_sha256": hashlib.sha256(response.body).hexdigest(),
        "request_started_at": started_text,
        "response_received_at": received_text,
    }
    receipt["receipt_hash"] = business_hash(receipt)
    return receipt


def _body(receipt: Mapping[str, Any]) -> object:
    body = receipt.get("response_body_utf8")
    if not isinstance(body, str):
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_RECEIPT_INVALID"
        )
    return _strict_json(body.encode("utf-8"))


def _permission_summary(value: object) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or not _REQUIRED_PERMISSION_FIELDS.issubset(
        value
    ):
        raise AccountCommissionError(
            "ACCOUNT_CREDENTIAL_SCOPE_INVALID"
        )
    flags = {}
    integers = {}
    for name, item in value.items():
        if not isinstance(name, str):
            raise AccountCommissionError(
                "ACCOUNT_CREDENTIAL_SCOPE_INVALID"
            )
        if name in _NON_PERMISSION_INTEGER_FIELDS:
            if (
                isinstance(item, bool)
                or not isinstance(item, int)
                or item < 0
                or item > (1 << 53) - 1
            ):
                raise AccountCommissionError(
                    "ACCOUNT_CREDENTIAL_SCOPE_INVALID"
                )
            integers[name] = item
        elif isinstance(item, bool):
            flags[name] = item
        else:
            raise AccountCommissionError(
                "ACCOUNT_CREDENTIAL_SCOPE_INVALID"
            )
    if (
        flags.get("enableReading") is not True
        or flags.get("ipRestrict") is not True
    ):
        raise AccountCommissionError("ACCOUNT_CREDENTIAL_SCOPE_BLOCKED")
    permitted_true = {"enableReading", "ipRestrict"}
    excessive = sorted(
        name
        for name, enabled in flags.items()
        if enabled and name not in permitted_true
    )
    if excessive:
        raise AccountCommissionError("ACCOUNT_CREDENTIAL_SCOPE_BLOCKED")
    return {
        "status": "READ_ONLY_IP_RESTRICTED",
        "flags": dict(sorted(flags.items())),
        "create_time_ms": integers["createTime"],
        "trading_authority_expiration_time_ms_or_null": integers.get(
            "tradingAuthorityExpirationTime"
        ),
        "unknown_true_permissions": [],
    }


def _rate_group(value: object) -> Dict[str, Decimal]:
    keys = ("maker", "taker", "buyer", "seller")
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise AccountCommissionError(
            "ACCOUNT_SPOT_COMMISSION_INVALID"
        )
    return {name: _decimal(value[name]) for name in keys}


def _spot_context(value: object) -> Dict[str, Any]:
    keys = (
        "symbol",
        "standardCommission",
        "specialCommission",
        "taxCommission",
        "discount",
    )
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise AccountCommissionError(
            "ACCOUNT_SPOT_COMMISSION_INVALID"
        )
    if value["symbol"] != "ETHUSDT":
        raise AccountCommissionError("ACCOUNT_COMMISSION_SYMBOL_INVALID")
    standard = _rate_group(value["standardCommission"])
    special = _rate_group(value["specialCommission"])
    tax = _rate_group(value["taxCommission"])
    discount = value["discount"]
    if (
        not isinstance(discount, Mapping)
        or set(discount)
        != {
            "enabledForAccount",
            "enabledForSymbol",
            "discountAsset",
            "discount",
        }
        or not isinstance(discount["enabledForAccount"], bool)
        or not isinstance(discount["enabledForSymbol"], bool)
        or discount["discountAsset"] != "BNB"
    ):
        raise AccountCommissionError(
            "ACCOUNT_SPOT_COMMISSION_INVALID"
        )
    discount_rate = _decimal(discount["discount"])
    no_discount = {}
    discounted = {}
    with localcontext() as context:
        context.prec = 50
        for role in ("maker", "taker"):
            for side in ("buyer", "seller"):
                name = role + "_" + ("buy" if side == "buyer" else "sell")
                standard_component = standard[role] + standard[side]
                other = (
                    special[role]
                    + special[side]
                    + tax[role]
                    + tax[side]
                )
                no_discount[name] = _render(standard_component + other)
                discounted[name] = _render(
                    standard_component * discount_rate + other
                )
    eligible = (
        discount["enabledForAccount"]
        and discount["enabledForSymbol"]
    )
    return {
        "symbol": "ETHUSDT",
        "standard_commission": {
            name: _render(number) for name, number in standard.items()
        },
        "special_commission": {
            name: _render(number) for name, number in special.items()
        },
        "tax_commission": {
            name: _render(number) for name, number in tax.items()
        },
        "discount": {
            "enabled_for_account": discount["enabledForAccount"],
            "enabled_for_symbol": discount["enabledForSymbol"],
            "asset": "BNB",
            "rate": _render(discount_rate),
        },
        "authoritative_no_discount_rates": no_discount,
        "bnb_discount_scenario_or_null": discounted if eligible else None,
        "authoritative_cost_semantics": (
            "NO_DISCOUNT_UNTIL_PAYMENT_ASSET_AND_BALANCE_PROVEN"
        ),
    }


def _futures_context(value: object) -> Dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value)
        != {
            "symbol",
            "makerCommissionRate",
            "takerCommissionRate",
        }
        or value["symbol"] != "ETHUSDT"
    ):
        raise AccountCommissionError(
            "ACCOUNT_FUTURES_COMMISSION_INVALID"
        )
    maker = _decimal(value["makerCommissionRate"])
    taker = _decimal(value["takerCommissionRate"])
    return {
        "symbol": "ETHUSDT",
        "maker_rate": _render(maker),
        "taker_rate": _render(taker),
        "two_taker_sides_rate": _render(taker * 2),
    }


def _derived(
    receipts: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    if len(receipts) != 3:
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_RECEIPT_SET_INVALID"
        )
    permission = _permission_summary(_body(receipts[0]))
    spot = _spot_context(_body(receipts[1]))
    futures = _futures_context(_body(receipts[2]))
    spot_rates = spot["authoritative_no_discount_rates"]
    assumption = Decimal("0.0015")
    notional = Decimal("1000")
    spot_taker_buy = _decimal(spot_rates["taker_buy"])
    spot_taker_sell = _decimal(spot_rates["taker_sell"])
    futures_taker = _decimal(futures["taker_rate"])
    with localcontext() as context:
        context.prec = 50
        spot_round_trip = spot_taker_buy + spot_taker_sell
        futures_round_trip = futures_taker * 2
    costs = {
        "notional_usdt": "1000",
        "rate_unit": "UNIT_RATIO",
        "spot_taker_buy_per_1000_usdt": _render(
            notional * spot_taker_buy
        ),
        "spot_taker_sell_per_1000_usdt": _render(
            notional * spot_taker_sell
        ),
        "spot_two_taker_sides_rate": _render(spot_round_trip),
        "spot_two_taker_sides_per_1000_usdt": _render(
            notional * spot_round_trip
        ),
        "futures_taker_per_1000_usdt": _render(
            notional * futures_taker
        ),
        "futures_two_taker_sides_rate": _render(futures_round_trip),
        "futures_two_taker_sides_per_1000_usdt": _render(
            notional * futures_round_trip
        ),
        "v0_18_assumed_rate_per_side": "0.0015",
        "v0_18_assumption_covers_spot_taker_buy": (
            assumption >= spot_taker_buy
        ),
        "v0_18_assumption_covers_spot_taker_sell": (
            assumption >= spot_taker_sell
        ),
        "v0_18_assumption_covers_futures_taker": (
            assumption >= futures_taker
        ),
        "scenario_semantics": (
            "CURRENT_COMMISSION_CONTEXT_NOT_REALIZED_PNL"
        ),
    }
    quality = {
        "status": "PASS",
        "reason_codes": [],
        "receipt_count": 3,
        "raw_responses_preserved": True,
        "permission_scope_verified_before_commission": True,
        "credentials_persisted": False,
        "bnb_discount_authoritative": False,
    }
    return permission, {"spot": spot, "usd_m_perpetual": futures}, {
        "costs": costs,
        "quality": quality,
    }


@dataclass(frozen=True, init=False)
class VerifiedAccountCommissionCapture:
    plan: AccountCommissionPlan
    server_time_probe: Mapping[str, Any]
    receipts: Tuple[Mapping[str, Any], ...]
    api_key_fingerprint: str
    recorded_at: str
    network_request_count: int

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _CAPTURE_TOKEN:
            raise TypeError(
                "VerifiedAccountCommissionCapture is issued by capture"
            )
        for name in (
            "plan",
            "server_time_probe",
            "receipts",
            "api_key_fingerprint",
            "recorded_at",
            "network_request_count",
        ):
            object.__setattr__(self, name, kwargs[name])


def capture_account_commission(
    *,
    signer: HmacAccountSigner,
    server_time_transport=None,
    account_transport=None,
) -> VerifiedAccountCommissionCapture:
    if not isinstance(signer, HmacAccountSigner):
        raise AccountCommissionError("ACCOUNT_CREDENTIAL_INVALID")
    try:
        gate = open_verified_runtime_gate(
            server_time_transport=server_time_transport
        )
    except RuntimeHealthError as error:
        if error.reason_code == "PAPER_CLOCK_PROBE_BLOCKED":
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_CLOCK_BLOCKED"
            ) from error
        raise
    return capture_account_commission_with_runtime_gate(
        signer=signer,
        runtime_gate=gate,
        account_transport=account_transport,
    )


def capture_account_commission_with_runtime_gate(
    *,
    signer: HmacAccountSigner,
    runtime_gate: VerifiedRuntimeGate,
    account_transport=None,
) -> VerifiedAccountCommissionCapture:
    """Capture account costs using an already verified shared clock gate."""

    if not isinstance(signer, HmacAccountSigner):
        raise AccountCommissionError("ACCOUNT_CREDENTIAL_INVALID")
    if not isinstance(runtime_gate, VerifiedRuntimeGate):
        raise AccountCommissionError("ACCOUNT_RUNTIME_GATE_INVALID")
    probe = runtime_gate.probe
    if server_time_probe_reasons(
        probe, server_time_probe_trust_hash(probe)
    ):
        raise AccountCommissionError("ACCOUNT_RUNTIME_GATE_INVALID")
    if probe["health_status"] not in (
        "HEALTHY_ALIGNED",
        "HEALTHY_CORRECTED",
    ):
        raise AccountCommissionError("ACCOUNT_COMMISSION_CLOCK_BLOCKED")
    trusted_clock = runtime_gate.clock
    transport = account_transport or BinanceAccountCommissionTransport(
        clock=trusted_clock
    )
    if not hasattr(transport, "get"):
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_TRANSPORT_INVALID"
        )
    plan = AccountCommissionPlan.create()
    receipts = []
    for index, request in enumerate(plan.requests):
        signed = sign_account_commission_request(
            request, _epoch_ms(trusted_clock()), signer
        )
        receipt = _receipt(
            signed,
            transport.get(signed, signer.api_key_header()),
        )
        receipts.append(receipt)
        if index == 0:
            _permission_summary(_body(receipt))
    _derived(receipts)
    first_started, _ = _utc(receipts[0]["request_started_at"])
    probe_completed, _ = _utc(probe["trusted_completed_at_or_null"])
    if first_started < probe_completed:
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_PRECEDES_HEALTH_GATE"
        )
    now, now_text = _utc(trusted_clock())
    last_received, _ = _utc(receipts[-1]["response_received_at"])
    if now <= last_received:
        now_text = utc_datetime(last_received + timedelta(milliseconds=1))
    return VerifiedAccountCommissionCapture(
        plan=plan,
        server_time_probe=probe,
        receipts=tuple(receipts),
        api_key_fingerprint=signer.fingerprint,
        recorded_at=now_text,
        network_request_count=3 + len(receipts),
        _token=_CAPTURE_TOKEN,
    )


def _validate_receipts(
    receipts: Sequence[Mapping[str, Any]],
    plan: AccountCommissionPlan,
    api_key_fingerprint: str,
) -> None:
    if not isinstance(receipts, list) or len(receipts) != 3:
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_RECEIPT_SET_INVALID"
        )
    previous_receive = None
    for receipt, request in zip(receipts, plan.requests):
        if not isinstance(receipt, Mapping):
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_RECEIPT_INVALID"
            )
        redacted = receipt.get("request")
        if not isinstance(redacted, Mapping):
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_RECEIPT_INVALID"
            )
        timestamp_ms = redacted.get("timestamp_ms")
        expected_request = {
            **request.business_payload(),
            "timestamp_ms": timestamp_ms,
            "recv_window_ms": _RECV_WINDOW_MS,
            "unsigned_query_sha256": hashlib.sha256(
                _unsigned_query(request, timestamp_ms).encode("ascii")
            ).hexdigest(),
            "signed_query_sha256": redacted.get(
                "signed_query_sha256"
            ),
            "api_key_fingerprint": api_key_fingerprint,
        }
        if redacted != expected_request:
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_REQUEST_REPLAY_MISMATCH"
            )
        body = receipt.get("response_body_utf8")
        if not isinstance(body, str):
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_RECEIPT_INVALID"
            )
        body_bytes = body.encode("utf-8")
        if hashlib.sha256(body_bytes).hexdigest() != receipt.get(
            "response_body_sha256"
        ):
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_BODY_HASH_MISMATCH"
            )
        if (
            receipt.get("status") != 200
            or receipt.get("final_host") != request.host
            or receipt.get("final_path") != request.path
        ):
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_RESPONSE_REPLAY_MISMATCH"
            )
        started, _ = _utc(receipt.get("request_started_at"))
        received, _ = _utc(receipt.get("response_received_at"))
        if received < started or (
            previous_receive is not None and started < previous_receive
        ):
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_RECEIPT_TIME_INVALID"
            )
        timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
            milliseconds=timestamp_ms
        )
        if timestamp > received + timedelta(seconds=1) or (
            received - timestamp
        ) > timedelta(milliseconds=_RECV_WINDOW_MS):
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_TIMESTAMP_OUTSIDE_WINDOW"
            )
        without_hash = dict(receipt)
        receipt_hash = without_hash.pop("receipt_hash", None)
        if business_hash(without_hash) != receipt_hash:
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_RECEIPT_HASH_MISMATCH"
            )
        _strict_json(body_bytes)
        previous_receive = received


@lru_cache(maxsize=1)
def _snapshot_validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas", "account-commission-snapshot-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def build_account_commission_snapshot(
    capture: VerifiedAccountCommissionCapture,
) -> Dict[str, Any]:
    if not isinstance(capture, VerifiedAccountCommissionCapture):
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_CAPTURE_UNVERIFIED"
        )
    plan = capture.plan
    receipts = [dict(item) for item in capture.receipts]
    _validate_receipts(
        receipts, plan, capture.api_key_fingerprint
    )
    permission, context, derived = _derived(receipts)
    observed, observed_text = _utc(
        receipts[-1]["response_received_at"]
    )
    valid_until_text = utc_datetime(
        observed + timedelta(hours=_VALIDITY_HOURS)
    )
    identity = {
        "plan_hash": plan.plan_hash,
        "server_time_probe_hash": capture.server_time_probe["probe_hash"],
        "receipt_hashes": [item["receipt_hash"] for item in receipts],
        "api_key_fingerprint": capture.api_key_fingerprint,
    }
    snapshot = {
        "$schema": "./account-commission-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": stable_id("account_commission", identity),
        "snapshot_hash": "",
        "recorded_at": capture.recorded_at,
        "observed_at": observed_text,
        "valid_until": valid_until_text,
        "policy": {
            **plan.business_payload(),
            "plan_hash": plan.plan_hash,
        },
        "server_time_probe": dict(capture.server_time_probe),
        "api_key_fingerprint": capture.api_key_fingerprint,
        "receipts": receipts,
        "permission_summary": permission,
        "commission_context": context,
        "cost_scenarios": derived["costs"],
        "quality_report": derived["quality"],
        "network_request_count": capture.network_request_count,
        "cost_context_eligibility": "CURRENT_PAPER_CONTEXT_ONLY",
        "historical_backfill_eligibility": "FORBIDDEN",
        "production_eligibility": (
            "EXTERNAL_APPROVAL_NOT_IMPLEMENTED"
        ),
        "profitability_eligibility": (
            "INSUFFICIENT_DURATION_AND_EXECUTION"
        ),
        "warnings": list(_WARNINGS),
    }
    snapshot["snapshot_hash"] = artifact_self_hash(
        snapshot, "snapshot_hash"
    )
    if tuple(_snapshot_validator().iter_errors(snapshot)):
        raise AccountCommissionError(
            "ACCOUNT_COMMISSION_SNAPSHOT_SCHEMA_INVALID"
        )
    return snapshot


def account_commission_trust_hash(snapshot: Mapping[str, Any]) -> str:
    try:
        return business_hash(
            {
                "attestation_type": _ATTESTATION_TYPE,
                "snapshot_id": snapshot["snapshot_id"],
                "snapshot_hash": snapshot["snapshot_hash"],
                "plan_hash": snapshot["policy"]["plan_hash"],
                "server_time_probe_trust_hash": (
                    server_time_probe_trust_hash(
                        snapshot["server_time_probe"]
                    )
                ),
                "receipt_hashes": [
                    item["receipt_hash"] for item in snapshot["receipts"]
                ],
                "api_key_fingerprint": snapshot[
                    "api_key_fingerprint"
                ],
            }
        )
    except (KeyError, TypeError):
        return ""


def account_commission_reasons(
    snapshot: Mapping[str, Any],
    trusted_attestation_hash: str,
) -> Tuple[str, ...]:
    if not isinstance(snapshot, Mapping):
        return ("ACCOUNT_COMMISSION_SNAPSHOT_INVALID",)
    reasons = []
    try:
        if tuple(_snapshot_validator().iter_errors(snapshot)):
            reasons.append("ACCOUNT_COMMISSION_SNAPSHOT_SCHEMA_INVALID")
        if artifact_self_hash(
            snapshot, "snapshot_hash"
        ) != snapshot.get("snapshot_hash"):
            reasons.append(
                "ACCOUNT_COMMISSION_SNAPSHOT_SELF_HASH_MISMATCH"
            )
        if (
            account_commission_trust_hash(snapshot)
            != trusted_attestation_hash
        ):
            reasons.append(
                "ACCOUNT_COMMISSION_SNAPSHOT_TRUST_HASH_MISMATCH"
            )
        plan = AccountCommissionPlan.create()
        if snapshot.get("policy") != {
            **plan.business_payload(),
            "plan_hash": plan.plan_hash,
        }:
            reasons.append("ACCOUNT_COMMISSION_POLICY_MISMATCH")
        probe = snapshot["server_time_probe"]
        if server_time_probe_reasons(
            probe, server_time_probe_trust_hash(probe)
        ):
            reasons.append(
                "ACCOUNT_COMMISSION_SERVER_TIME_PROBE_INVALID"
            )
        fingerprint = snapshot["api_key_fingerprint"]
        receipts = snapshot["receipts"]
        _validate_receipts(receipts, plan, fingerprint)
        probe_completed, _ = _utc(
            probe["trusted_completed_at_or_null"]
        )
        first_started, _ = _utc(
            receipts[0]["request_started_at"]
        )
        if first_started < probe_completed:
            reasons.append(
                "ACCOUNT_COMMISSION_PRECEDES_HEALTH_GATE"
            )
        permission, context, derived = _derived(receipts)
        if snapshot.get("permission_summary") != permission:
            reasons.append(
                "ACCOUNT_COMMISSION_PERMISSION_MISMATCH"
            )
        if snapshot.get("commission_context") != context:
            reasons.append(
                "ACCOUNT_COMMISSION_CONTEXT_MISMATCH"
            )
        if snapshot.get("cost_scenarios") != derived["costs"]:
            reasons.append("ACCOUNT_COMMISSION_COST_MISMATCH")
        if snapshot.get("quality_report") != derived["quality"]:
            reasons.append("ACCOUNT_COMMISSION_QUALITY_MISMATCH")
        observed, observed_text = _utc(
            receipts[-1]["response_received_at"]
        )
        if snapshot.get("observed_at") != observed_text:
            reasons.append("ACCOUNT_COMMISSION_OBSERVED_TIME_INVALID")
        if snapshot.get("valid_until") != utc_datetime(
            observed + timedelta(hours=_VALIDITY_HOURS)
        ):
            reasons.append("ACCOUNT_COMMISSION_VALIDITY_INVALID")
        recorded, _ = _utc(snapshot["recorded_at"])
        if recorded < observed:
            reasons.append("ACCOUNT_COMMISSION_RECORDED_TIME_INVALID")
        identity = {
            "plan_hash": plan.plan_hash,
            "server_time_probe_hash": probe["probe_hash"],
            "receipt_hashes": [
                item["receipt_hash"] for item in receipts
            ],
            "api_key_fingerprint": fingerprint,
        }
        if snapshot.get("snapshot_id") != stable_id(
            "account_commission", identity
        ):
            reasons.append("ACCOUNT_COMMISSION_SNAPSHOT_ID_MISMATCH")
        if snapshot.get("network_request_count") != 6:
            reasons.append("ACCOUNT_COMMISSION_NETWORK_COUNT_INVALID")
    except (
        KeyError,
        TypeError,
        ValueError,
        AccountCommissionError,
    ):
        reasons.append("ACCOUNT_COMMISSION_SNAPSHOT_REPLAY_INVALID")
    for name, expected in (
        ("cost_context_eligibility", "CURRENT_PAPER_CONTEXT_ONLY"),
        ("historical_backfill_eligibility", "FORBIDDEN"),
        (
            "production_eligibility",
            "EXTERNAL_APPROVAL_NOT_IMPLEMENTED",
        ),
        (
            "profitability_eligibility",
            "INSUFFICIENT_DURATION_AND_EXECUTION",
        ),
    ):
        if snapshot.get(name) != expected:
            reasons.append("ACCOUNT_COMMISSION_ELIGIBILITY_INVALID")
    if snapshot.get("warnings") != list(_WARNINGS):
        reasons.append("ACCOUNT_COMMISSION_WARNINGS_INVALID")
    return tuple(sorted(set(reasons)))


def publish_account_commission(
    *,
    output_root: Path,
    signer: Optional[HmacAccountSigner] = None,
    server_time_transport=None,
    account_transport=None,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    own_signer = signer is None
    active_signer = signer or load_account_signer_from_environment(
        output_root=output_root,
        workspace_root=workspace_root,
    )
    try:
        capture = capture_account_commission(
            signer=active_signer,
            server_time_transport=server_time_transport,
            account_transport=account_transport,
        )
        snapshot = build_account_commission_snapshot(capture)
        trust_hash = account_commission_trust_hash(snapshot)
        if account_commission_reasons(snapshot, trust_hash):
            raise AccountCommissionError(
                "ACCOUNT_COMMISSION_SNAPSHOT_INVALID"
            )
        artifact_name = snapshot["snapshot_id"].lower() + ".json"
        artifact_bytes = json.dumps(
            snapshot, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        path = (
            Path(output_root).resolve()
            / "account-cost"
            / artifact_name
        )
        created = _publish_immutable(
            Path(output_root),
            artifact_name,
            artifact_bytes,
            output_directory="account-cost",
        )
        return {
            "outcome": "CAPTURED",
            "artifact_path": str(path),
            "artifact_created": created,
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_hash": snapshot["snapshot_hash"],
            "trust_hash": trust_hash,
            "api_key_fingerprint": snapshot["api_key_fingerprint"],
            "network_request_count": snapshot[
                "network_request_count"
            ],
            "cost_context_eligibility": snapshot[
                "cost_context_eligibility"
            ],
            "production_eligibility": snapshot[
                "production_eligibility"
            ],
        }
    finally:
        if own_signer:
            active_signer.close()
