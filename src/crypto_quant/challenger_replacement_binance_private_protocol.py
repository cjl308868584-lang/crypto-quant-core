"""Pure Binance request encoding, signing and response classification."""
from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Mapping
from urllib.parse import parse_qsl, quote, urlencode
from .canonical import canonical_decimal, stable_id
from .errors import CanonicalizationError
from .challenger_replacement_binance_private_contract import (
    require_binance_private_endpoint,
)
_MAX_SAFE_INTEGER = (1 << 53) - 1
_MAX_JSON_DEPTH = 64
_MAX_SERVER_TIME_ROUND_TRIP_MS = 1000
_MAX_SERVER_TIME_SKEW_MS = 1000
_RECV_WINDOW_MS = "5000"
_UNSIGNED_ENDPOINTS = frozenset({
    "SPOT_SERVER_TIME",
    "SPOT_EXCHANGE_INFO",
    "FUTURES_SERVER_TIME",
    "FUTURES_EXCHANGE_INFO",
    "FUTURES_MARK_PRICE",
})
_PARAMETER_NAMES = {
    "SPOT_SERVER_TIME": "", "SPOT_EXCHANGE_INFO": "symbol",
    "FUTURES_SERVER_TIME": "", "FUTURES_EXCHANGE_INFO": "",
    "FUTURES_MARK_PRICE": "symbol", "API_RESTRICTIONS": "",
    "API_TRADING_STATUS": "", "SPOT_ACCOUNT": "",
    "SPOT_OPEN_ORDERS": "symbol",
    "SPOT_ORDER_QUERY": "symbol origClientOrderId",
    "SPOT_TRADES": "symbol orderId", "FUTURES_POSITION_MODE": "",
    "FUTURES_MULTI_ASSET_MODE": "", "FUTURES_SYMBOL_CONFIG": "symbol",
    "FUTURES_ACCOUNT": "", "FUTURES_POSITION": "symbol",
    "FUTURES_OPEN_ORDERS": "symbol",
    "FUTURES_ORDER_QUERY": "symbol origClientOrderId",
    "FUTURES_TRADES": "symbol orderId",
    "FUTURES_INCOME": "symbol incomeType startTime endTime",
    "FUTURES_ALGO_QUERY": "clientAlgoId",
    "FUTURES_OPEN_ALGO_ORDERS": "symbol",
    "SPOT_ORDER_CREATE":
        "symbol side type quantity newClientOrderId newOrderRespType",
    "SPOT_ORDER_CANCEL": "symbol origClientOrderId",
    "FUTURES_ORDER_CREATE":
        "symbol side type quantity newClientOrderId positionSide reduceOnly",
    "FUTURES_ORDER_CANCEL": "symbol origClientOrderId",
    "FUTURES_ALGO_CREATE": (
        "algoType symbol side positionSide type quantity triggerPrice "
        "workingType reduceOnly closePosition clientAlgoId"
    ),
    "FUTURES_ALGO_CANCEL": "clientAlgoId",
    "FUTURES_SET_LEVERAGE": "symbol leverage",
    "FUTURES_SET_MARGIN_TYPE": "symbol marginType",
}
_PARAMETER_SETS = {key: frozenset(value.split())
                   for key, value in _PARAMETER_NAMES.items()}
class _ResponseDepthError(ValueError):
    pass
@dataclass(frozen=True)
class BinancePrivateRequest:
    request_id: str
    endpoint_id: str
    host: str
    method: str
    path: str
    encoded_parameters: bytes
    parameter_names: tuple
    mutating: bool
@dataclass(frozen=True)
class BinanceServerTimeEvidence:
    product: str
    local_before_ms: int
    server_time_ms: int
    local_after_ms: int
    midpoint_ms: int
    skew_ms: int
    response_sha256: str
def observe_binance_server_time(*, product, transport, local_clock):
    """Observe one product-matched server clock through a fixed transport."""
    endpoint = {"SPOT": "SPOT_SERVER_TIME",
                "PERPETUAL": "FUTURES_SERVER_TIME"}.get(product)
    try:
        if endpoint is None or not callable(transport) or not callable(local_clock):
            raise ValueError
        before = local_clock()
        if isinstance(before, bool) or not isinstance(before, int):
            raise ValueError
        result = transport(build_binance_private_request(
            endpoint, {}, timestamp_ms=0,
        ))
        after = local_clock()
        if (isinstance(after, bool) or not isinstance(after, int)
                or not 0 <= before <= after <= _MAX_SAFE_INTEGER
                or after - before > _MAX_SERVER_TIME_ROUND_TRIP_MS
                or result.response_class != "QUERY_SUCCEEDED"
                or not isinstance(result.body, bytes)):
            raise ValueError
        document = json.loads(result.body.decode("utf-8"))
        if (not isinstance(document, dict)
                or frozenset(document) != {"serverTime"}
                or isinstance(document["serverTime"], bool)
                or not isinstance(document["serverTime"], int)
                or not 0 <= document["serverTime"] <= _MAX_SAFE_INTEGER):
            raise ValueError
        midpoint = before + (after - before) // 2
        skew = document["serverTime"] - midpoint
        if abs(skew) > _MAX_SERVER_TIME_SKEW_MS:
            raise ValueError
        return BinanceServerTimeEvidence(
            product=product, local_before_ms=before,
            server_time_ms=document["serverTime"], local_after_ms=after,
            midpoint_ms=midpoint, skew_ms=skew,
            response_sha256=hashlib.sha256(result.body).hexdigest(),
        )
    except (AttributeError, TypeError, UnicodeDecodeError, ValueError) as error:
        raise ValueError("BINANCE_SERVER_TIME_INVALID") from error
def _invalid():
    raise ValueError("CHALLENGER_REPLACEMENT_BINANCE_REQUEST_INVALID")
def _venue_id_valid(value):
    return (
        isinstance(value, str)
        and len(value) == 36
        and value.startswith("cq77")
        and not set(value[4:]) - frozenset("0123456789abcdef")
    )
def _positive_decimal(value):
    try:
        normalized = canonical_decimal(value)
    except (CanonicalizationError, TypeError, ValueError):
        return False
    return normalized == value and normalized != "0" and not normalized.startswith("-")


def _values_valid(endpoint_id, parameters):
    if "symbol" in parameters and parameters["symbol"] != "ETHUSDT":
        return False
    for name in ("origClientOrderId", "newClientOrderId", "clientAlgoId"):
        if name in parameters and not _venue_id_valid(parameters[name]):
            return False
    if "orderId" in parameters and not (
        parameters["orderId"].isdigit() and int(parameters["orderId"]) > 0
    ):
        return False
    for name in ("quantity", "triggerPrice"):
        if name in parameters and not _positive_decimal(parameters[name]):
            return False
    if endpoint_id == "SPOT_ORDER_CREATE":
        return (
            parameters["side"] in {"BUY", "SELL"}
            and parameters["type"] == "MARKET"
            and parameters["newOrderRespType"] == "FULL"
        )
    if endpoint_id == "FUTURES_ORDER_CREATE":
        return (
            parameters["side"] in {"BUY", "SELL"}
            and parameters["type"] == "MARKET"
            and parameters["positionSide"] == "BOTH"
            and parameters["reduceOnly"] in {"true", "false"}
        )
    if endpoint_id == "FUTURES_ALGO_CREATE":
        return parameters == {
            **parameters,
            "algoType": "CONDITIONAL",
            "symbol": "ETHUSDT",
            "side": "BUY",
            "positionSide": "BOTH",
            "type": "STOP_MARKET",
            "workingType": "MARK_PRICE",
            "reduceOnly": "true",
            "closePosition": "false",
        }
    if endpoint_id == "FUTURES_SET_LEVERAGE":
        return parameters["leverage"] in {"1", "2"}
    if endpoint_id == "FUTURES_SET_MARGIN_TYPE":
        return parameters["marginType"] == "ISOLATED"
    if endpoint_id == "FUTURES_INCOME":
        try:
            start = int(parameters["startTime"])
            end = int(parameters["endTime"])
        except (TypeError, ValueError):
            return False
        return (
            parameters["incomeType"] == "FUNDING_FEE"
            and 0 <= start <= end <= _MAX_SAFE_INTEGER
            and str(start) == parameters["startTime"]
            and str(end) == parameters["endTime"]
        )
    return True


def build_binance_private_request(endpoint_id, parameters, *, timestamp_ms):
    """Build one deterministic request from a closed endpoint identifier."""

    host, method, path, mutating = require_binance_private_endpoint(endpoint_id)
    allowed = _PARAMETER_SETS.get(endpoint_id)
    if (
        allowed is None
        or not isinstance(parameters, Mapping)
        or frozenset(parameters) != allowed
        or isinstance(timestamp_ms, bool)
        or not isinstance(timestamp_ms, int)
        or not 0 <= timestamp_ms <= _MAX_SAFE_INTEGER
        or any(
            not isinstance(name, str)
            or not isinstance(value, str)
            or not value
            for name, value in parameters.items()
        )
        or not _values_valid(endpoint_id, parameters)
    ):
        _invalid()
    complete = dict(parameters)
    if endpoint_id not in _UNSIGNED_ENDPOINTS:
        complete.update(
            recvWindow=_RECV_WINDOW_MS,
            timestamp=str(timestamp_ms),
        )
    pairs = tuple(sorted(complete.items()))
    encoded = urlencode(pairs, quote_via=quote).encode("ascii")
    identity = {
        "endpoint_id": endpoint_id,
        "host": host,
        "method": method,
        "path": path,
        "encoded_parameters_sha256": hashlib.sha256(encoded).hexdigest(),
    }
    return BinancePrivateRequest(
        request_id=stable_id("binance_private_request", identity),
        endpoint_id=endpoint_id,
        host=host,
        method=method,
        path=path,
        encoded_parameters=encoded,
        parameter_names=tuple(name for name, _value in pairs),
        mutating=mutating,
    )


def compute_binance_hmac_sha256(payload, hmac_key):
    """Compute the pure official HMAC-SHA256 known-answer primitive."""

    if (
        not isinstance(payload, bytes)
        or not 1 <= len(payload) <= 4096
        or not isinstance(hmac_key, bytes)
        or not 16 <= len(hmac_key) <= 256
    ):
        _invalid()
    return hmac.new(hmac_key, payload, hashlib.sha256).hexdigest()


def _validated_request(request):
    if (
        not isinstance(request, BinancePrivateRequest)
        or not isinstance(request.encoded_parameters, bytes)
        or len(request.encoded_parameters) > 4096
    ):
        _invalid()
    try:
        text = request.encoded_parameters.decode("ascii")
        pairs = parse_qsl(
            text,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=32,
        ) if text else []
        if len({name for name, _value in pairs}) != len(pairs):
            _invalid()
        values = dict(pairs)
        if request.endpoint_id in _UNSIGNED_ENDPOINTS:
            timestamp_ms = 0
        else:
            if values.pop("recvWindow", None) != _RECV_WINDOW_MS:
                _invalid()
            timestamp_text = values.pop("timestamp")
            timestamp_ms = int(timestamp_text)
            if str(timestamp_ms) != timestamp_text:
                _invalid()
        rebuilt = build_binance_private_request(
            request.endpoint_id, values, timestamp_ms=timestamp_ms
        )
    except (KeyError, TypeError, UnicodeDecodeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).endswith(
            "BINANCE_REQUEST_INVALID"
        ):
            raise
        raise ValueError(
            "CHALLENGER_REPLACEMENT_BINANCE_REQUEST_INVALID"
        ) from error
    if rebuilt != request:
        _invalid()
    return request


def sign_binance_private_request(request, hmac_secret):
    """Validate one frozen request, then return its lowercase HMAC."""

    request = _validated_request(request)
    return compute_binance_hmac_sha256(
        request.encoded_parameters, hmac_secret
    )


def validate_binance_request_time(*, timestamp_ms, server_time_ms):
    """Validate the fixed 5000 ms window and strict future-time boundary."""

    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= _MAX_SAFE_INTEGER
        for value in (timestamp_ms, server_time_ms)
    ):
        raise ValueError("CHALLENGER_REPLACEMENT_BINANCE_TIMESTAMP_INVALID")
    if not (
        timestamp_ms < server_time_ms + 1000
        and server_time_ms - timestamp_ms <= int(_RECV_WINDOW_MS)
    ):
        raise ValueError("CHALLENGER_REPLACEMENT_BINANCE_TIMESTAMP_INVALID")
    return timestamp_ms - server_time_ms


def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate response key")
        result[key] = value
    return result


def _require_bounded_json_depth(value):
    stack = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if isinstance(current, (dict, list)):
            if depth > _MAX_JSON_DEPTH:
                raise _ResponseDepthError
            children = current.values() if isinstance(current, dict) else current
            stack.extend((child, depth + 1) for child in children)


def classify_binance_private_response(request, *, status, body, headers):
    """Classify bounded HTTP bytes without ever authorizing a retry."""

    request = _validated_request(request)
    if (
        isinstance(status, bool)
        or not isinstance(status, int)
        or not 100 <= status <= 599
        or not isinstance(body, bytes)
        or len(body) > 1_048_576
        or not isinstance(headers, Mapping)
        or any(
            not isinstance(name, str) or not isinstance(value, str)
            for name, value in headers.items()
        )
    ):
        _invalid()
    try:
        document = json.loads(
            body.decode("utf-8"), object_pairs_hook=_strict_pairs
        )
        _require_bounded_json_depth(document)
        parsed = isinstance(document, (dict, list))
    except (_ResponseDepthError, RecursionError) as error:
        raise ValueError(
            "CHALLENGER_REPLACEMENT_BINANCE_RESPONSE_INVALID"
        ) from error
    except (UnicodeDecodeError, ValueError):
        document = None
        parsed = False
    code = document.get("code") if isinstance(document, dict) else None
    valid_error = (
        isinstance(document, dict)
        and isinstance(code, int)
        and not isinstance(code, bool)
        and isinstance(document.get("msg"), str)
    )
    if status in (418, 429):
        response_class = "RATE_LIMITED"
    elif request.mutating and (
        code == -1007 or status >= 500 or (200 <= status < 300 and not parsed)
    ):
        response_class = "UNKNOWN"
    elif 200 <= status < 300 and parsed:
        response_class = "ACKNOWLEDGED" if request.mutating else "QUERY_SUCCEEDED"
    elif request.mutating and 400 <= status < 500 and not valid_error:
        response_class = "UNKNOWN"
    elif request.mutating and 400 <= status < 500:
        response_class = "REJECTED_PROVEN_NO_ACK"
    elif status >= 500:
        response_class = "TRANSIENT_QUERY_FAILURE"
    else:
        response_class = "RESPONSE_INVALID"
    selected = tuple(sorted(
        (name.lower(), value)
        for name, value in headers.items()
        if name.lower() in {
            "retry-after", "x-mbx-used-weight-1m", "x-mbx-order-count-10s",
            "x-mbx-order-count-1m",
        }
    ))
    return {
        "response_class": response_class,
        "status": status,
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "code_or_null": code,
        "rate_limit_headers": selected,
    }
