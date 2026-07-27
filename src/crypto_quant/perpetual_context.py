"""Current public USD-M perpetual context and Funding cost scenarios."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from jsonschema import Draft202012Validator

from .canonical import (
    business_hash,
    canonical_decimal,
    stable_id,
    utc_datetime,
)
from .evidence import artifact_self_hash
from .market_data_cli import _publish_immutable
from .runtime_health import (
    RuntimeHealthPolicy,
    TrustedRuntimeClock,
    build_server_time_probe,
    server_time_probe_reasons,
    server_time_probe_trust_hash,
)


_PLAN_TOKEN = object()
_REQUEST_TOKEN = object()
_CAPTURE_TOKEN = object()
_HOST = "fapi.binance.com"
_BASE_URL = "https://" + _HOST
_MAX_BODY_BYTES = 262_144
_READ_CHUNK_BYTES = 65_536
_HTTP_TIMEOUT_SECONDS = 10
_MINUTE_MS = 60_000
_FOUR_HOURS_MS = 4 * 3_600_000
_DAY_MS = 24 * 3_600_000
_ATTESTATION_TYPE = "PERPETUAL_CONTEXT_SNAPSHOT_ATTESTATION"
_WARNINGS = (
    "CONTEXT_DOES_NOT_AUTHORIZE_SHORT",
    "FUNDING_SCENARIOS_ARE_NOT_REALIZED_PNL",
    "ACCOUNT_FEE_SCHEDULE_UNOBSERVED",
    "FUTURES_EXECUTION_NOT_IMPLEMENTED",
    "AI_MODEL_NOT_RUN",
)


class PerpetualContextError(ValueError):
    """The public Futures context failed closed."""

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
            raise PerpetualContextError(
                "PERPETUAL_TIME_INVALID"
            ) from error
    else:
        raise PerpetualContextError("PERPETUAL_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PerpetualContextError("PERPETUAL_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    converted = converted.replace(
        microsecond=(converted.microsecond // 1000) * 1000
    )
    return converted, utc_datetime(converted)


def _epoch_ms(value: object) -> int:
    parsed, _ = _utc(value)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return int((parsed - epoch) // timedelta(milliseconds=1))


def _from_epoch_ms(value: object) -> str:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > (1 << 53) - 1
    ):
        raise PerpetualContextError("PERPETUAL_SOURCE_TIME_INVALID")
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        return utc_datetime(epoch + timedelta(milliseconds=value))
    except (OverflowError, ValueError) as error:
        raise PerpetualContextError(
            "PERPETUAL_SOURCE_TIME_INVALID"
        ) from error


def _decimal(value: object, *, positive=False, nonnegative=False) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > 80:
        raise PerpetualContextError("PERPETUAL_DECIMAL_INVALID")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise PerpetualContextError("PERPETUAL_DECIMAL_INVALID") from error
    if not number.is_finite() or (number.is_zero() and number.is_signed()):
        raise PerpetualContextError("PERPETUAL_DECIMAL_INVALID")
    if positive and number <= 0:
        raise PerpetualContextError("PERPETUAL_DECIMAL_INVALID")
    if nonnegative and number < 0:
        raise PerpetualContextError("PERPETUAL_DECIMAL_INVALID")
    return number


def _render(value: Decimal) -> str:
    return canonical_decimal(value)


@dataclass(frozen=True, init=False)
class PerpetualContextRequest:
    family: str
    path: str
    query: Tuple[Tuple[str, object], ...]

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _REQUEST_TOKEN:
            raise TypeError(
                "PerpetualContextRequest is issued by PerpetualContextPlan"
            )
        object.__setattr__(self, "family", kwargs["family"])
        object.__setattr__(self, "path", kwargs["path"])
        object.__setattr__(self, "query", kwargs["query"])

    @property
    def url(self) -> str:
        return _BASE_URL + self.path + "?" + urlencode(self.query)

    def business_payload(self) -> Dict[str, Any]:
        return {
            "family": self.family,
            "method": "GET",
            "url": self.url,
            "path": self.path,
            "query": {name: value for name, value in self.query},
            "security_type": "NONE_PUBLIC",
        }


def _request(
    family: str,
    path: str,
    query: Sequence[Tuple[str, object]],
) -> PerpetualContextRequest:
    return PerpetualContextRequest(
        family=family,
        path=path,
        query=tuple(query),
        _token=_REQUEST_TOKEN,
    )


@dataclass(frozen=True, init=False)
class PerpetualContextPlan:
    schema_version: str
    plan_id: str
    symbol: str
    requests: Tuple[PerpetualContextRequest, ...]

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _PLAN_TOKEN:
            raise TypeError("PerpetualContextPlan must be created with create")
        object.__setattr__(self, "schema_version", "1.0.0")
        object.__setattr__(
            self,
            "plan_id",
            "ethusdt-usdm-current-perpetual-context-v1",
        )
        object.__setattr__(self, "symbol", "ETHUSDT")
        object.__setattr__(
            self,
            "requests",
            (
                _request(
                    "MARK_INDEX_FUNDING",
                    "/fapi/v1/premiumIndex",
                    (("symbol", "ETHUSDT"),),
                ),
                _request(
                    "PREMIUM_INDEX_KLINES",
                    "/fapi/v1/premiumIndexKlines",
                    (
                        ("symbol", "ETHUSDT"),
                        ("interval", "1m"),
                        ("limit", 2),
                    ),
                ),
                _request(
                    "CURRENT_OPEN_INTEREST",
                    "/fapi/v1/openInterest",
                    (("symbol", "ETHUSDT"),),
                ),
                _request(
                    "OPEN_INTEREST_HISTORY",
                    "/futures/data/openInterestHist",
                    (
                        ("symbol", "ETHUSDT"),
                        ("period", "4h"),
                        ("limit", 30),
                    ),
                ),
                _request(
                    "FUNDING_HISTORY",
                    "/fapi/v1/fundingRate",
                    (("symbol", "ETHUSDT"), ("limit", 30)),
                ),
            ),
        )

    @classmethod
    def create(
        cls, *, symbol: str = "ETHUSDT"
    ) -> "PerpetualContextPlan":
        if symbol != "ETHUSDT":
            raise PerpetualContextError("PERPETUAL_PLAN_INVALID")
        return cls(_token=_PLAN_TOKEN)

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "symbol": self.symbol,
            "market": "USD_M_PERPETUAL",
            "base_url": _BASE_URL,
            "request_count": len(self.requests),
            "automatic_retry_count": 0,
            "requests": [
                request.business_payload() for request in self.requests
            ],
        }

    @property
    def plan_hash(self) -> str:
        return business_hash(self.business_payload())


@dataclass(frozen=True)
class PublicPerpetualHttpResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes
    request_started_at: str
    response_received_at: str


def _valid_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or parsed.hostname != _HOST
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        return False
    return value in {
        request.url for request in PerpetualContextPlan.create().requests
    }


class _SameHostRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _valid_url(newurl):
            raise PerpetualContextError("PERPETUAL_REDIRECT_INVALID")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


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
            raise PerpetualContextError("PERPETUAL_RESPONSE_TOO_LARGE")
        chunks.append(chunk)
    return b"".join(chunks)


class BinancePerpetualContextTransport:
    """No-credential transport for the five frozen Futures requests."""

    def __init__(self, *, clock, opener=None):
        if not callable(clock):
            raise PerpetualContextError("PERPETUAL_CLOCK_INVALID")
        self._clock = clock
        self._opener = opener or build_opener(
            ProxyHandler({}), _SameHostRedirectHandler()
        )
        self.calls = 0

    def get(
        self, request: PerpetualContextRequest
    ) -> PublicPerpetualHttpResponse:
        if (
            not isinstance(request, PerpetualContextRequest)
            or request not in PerpetualContextPlan.create().requests
            or not _valid_url(request.url)
        ):
            raise PerpetualContextError("PERPETUAL_REQUEST_INVALID")
        self.calls += 1
        started = self._clock()
        try:
            with self._opener.open(
                Request(
                    request.url,
                    method="GET",
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "crypto-quant-perpetual-context/0.21",
                    },
                ),
                timeout=_HTTP_TIMEOUT_SECONDS,
            ) as response:
                return PublicPerpetualHttpResponse(
                    status=response.getcode(),
                    final_url=response.geturl(),
                    headers=dict(response.headers.items()),
                    body=_read_bounded(response),
                    request_started_at=started,
                    response_received_at=self._clock(),
                )
        except HTTPError as error:
            return PublicPerpetualHttpResponse(
                status=error.code,
                final_url=error.geturl(),
                headers=dict(error.headers.items()) if error.headers else {},
                body=b"",
                request_started_at=started,
                response_received_at=self._clock(),
            )
        except PerpetualContextError:
            raise
        except (OSError, TimeoutError, URLError) as error:
            raise PerpetualContextError(
                "PERPETUAL_TRANSPORT_FAILURE"
            ) from error


def _strict_json(body: bytes) -> object:
    if not isinstance(body, bytes) or len(body) > _MAX_BODY_BYTES:
        raise PerpetualContextError("PERPETUAL_RESPONSE_INVALID")

    def reject_float(_value):
        raise PerpetualContextError("PERPETUAL_JSON_FLOAT_FORBIDDEN")

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PerpetualContextError(
                    "PERPETUAL_JSON_DUPLICATE_KEY"
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
        raise PerpetualContextError(
            "PERPETUAL_RESPONSE_INVALID"
        ) from error


def _selected_headers(headers: object) -> Dict[str, Optional[str]]:
    if not isinstance(headers, Mapping):
        raise PerpetualContextError("PERPETUAL_RESPONSE_INVALID")
    lowered = {}
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise PerpetualContextError("PERPETUAL_RESPONSE_INVALID")
        lowered[name.lower()] = value
    return {
        "http_date_or_null": lowered.get("date"),
        "retry_after_or_null": lowered.get("retry-after"),
    }


def _receipt(
    request: PerpetualContextRequest,
    response: PublicPerpetualHttpResponse,
) -> Dict[str, Any]:
    if (
        not isinstance(response, PublicPerpetualHttpResponse)
        or isinstance(response.status, bool)
        or response.status != 200
        or response.final_url != request.url
        or not _valid_url(response.final_url)
        or not isinstance(response.body, bytes)
        or len(response.body) > _MAX_BODY_BYTES
    ):
        raise PerpetualContextError("PERPETUAL_RESPONSE_INVALID")
    started, started_text = _utc(response.request_started_at)
    received, received_text = _utc(response.response_received_at)
    if received < started:
        raise PerpetualContextError("PERPETUAL_CLOCK_INVALID")
    _strict_json(response.body)
    receipt = {
        "request": request.business_payload(),
        "status": response.status,
        "final_url": response.final_url,
        "selected_headers": _selected_headers(response.headers),
        "response_body_utf8": response.body.decode("utf-8"),
        "response_body_sha256": hashlib.sha256(response.body).hexdigest(),
        "request_started_at": started_text,
        "response_received_at": received_text,
    }
    receipt["receipt_hash"] = business_hash(receipt)
    return receipt


def _validate_probe_capture_boundary(
    probe: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
) -> None:
    try:
        probe_completed, _ = _utc(
            probe["trusted_completed_at_or_null"]
        )
        first_started, _ = _utc(receipts[0]["request_started_at"])
    except (KeyError, IndexError, TypeError) as error:
        raise PerpetualContextError(
            "PERPETUAL_CAPTURE_BOUNDARY_INVALID"
        ) from error
    if first_started < probe_completed:
        raise PerpetualContextError(
            "PERPETUAL_CAPTURE_PRECEDES_HEALTH_GATE"
        )


@dataclass(frozen=True, init=False)
class VerifiedPerpetualContextCapture:
    plan: PerpetualContextPlan
    server_time_probe: Mapping[str, Any]
    receipts: Tuple[Mapping[str, Any], ...]
    recorded_at: str
    network_request_count: int

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _CAPTURE_TOKEN:
            raise TypeError(
                "VerifiedPerpetualContextCapture is issued by capture"
            )
        for name in (
            "plan",
            "server_time_probe",
            "receipts",
            "recorded_at",
            "network_request_count",
        ):
            object.__setattr__(self, name, kwargs[name])


def capture_perpetual_context(
    *,
    server_time_transport=None,
    futures_transport=None,
) -> VerifiedPerpetualContextCapture:
    policy = RuntimeHealthPolicy.create()
    probe = build_server_time_probe(
        transport=server_time_transport,
        policy=policy,
    )
    if probe["health_status"] not in (
        "HEALTHY_ALIGNED",
        "HEALTHY_CORRECTED",
    ):
        raise PerpetualContextError("PERPETUAL_CLOCK_BLOCKED")
    trusted_clock = TrustedRuntimeClock(
        anchor_utc_ms=_epoch_ms(probe["trusted_completed_at_or_null"])
    )
    plan = PerpetualContextPlan.create()
    transport = futures_transport or BinancePerpetualContextTransport(
        clock=trusted_clock
    )
    receipts = []
    for request in plan.requests:
        if not hasattr(transport, "get"):
            raise PerpetualContextError("PERPETUAL_TRANSPORT_INVALID")
        receipts.append(_receipt(request, transport.get(request)))
    _validate_probe_capture_boundary(probe, receipts)
    _derived(receipts)
    now, now_text = _utc(trusted_clock())
    last_received, _ = _utc(receipts[-1]["response_received_at"])
    if now <= last_received:
        now_text = utc_datetime(last_received + timedelta(milliseconds=1))
    return VerifiedPerpetualContextCapture(
        plan=plan,
        server_time_probe=probe,
        receipts=tuple(receipts),
        recorded_at=now_text,
        network_request_count=3 + len(receipts),
        _token=_CAPTURE_TOKEN,
    )


def _mapping(
    value: object, keys: Sequence[str], reason: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise PerpetualContextError(reason)
    return value


def _sequence(value: object, *, minimum: int = 1) -> Sequence[Any]:
    if (
        not isinstance(value, list)
        or len(value) < minimum
        or len(value) > 100
    ):
        raise PerpetualContextError("PERPETUAL_RESPONSE_SHAPE_INVALID")
    return value


def _parse_premium(value: object) -> Dict[str, Any]:
    item = _mapping(
        value,
        (
            "symbol",
            "markPrice",
            "indexPrice",
            "estimatedSettlePrice",
            "lastFundingRate",
            "interestRate",
            "nextFundingTime",
            "time",
        ),
        "PERPETUAL_PREMIUM_INVALID",
    )
    if item["symbol"] != "ETHUSDT":
        raise PerpetualContextError("PERPETUAL_SYMBOL_INVALID")
    mark = _decimal(item["markPrice"], positive=True)
    index = _decimal(item["indexPrice"], positive=True)
    settle = _decimal(item["estimatedSettlePrice"], positive=True)
    funding = _decimal(item["lastFundingRate"])
    interest = _decimal(item["interestRate"])
    with localcontext() as context:
        context.prec = 50
        basis = mark - index
        basis_rate = basis / index
    return {
        "symbol": "ETHUSDT",
        "mark_price": _render(mark),
        "index_price": _render(index),
        "estimated_settle_price": _render(settle),
        "basis_usdt": _render(basis),
        "basis_rate": _render(basis_rate),
        "last_funding_rate": _render(funding),
        "interest_rate": _render(interest),
        "next_funding_time": _from_epoch_ms(item["nextFundingTime"]),
        "source_time": _from_epoch_ms(item["time"]),
        "source_time_ms": item["time"],
        "next_funding_time_ms": item["nextFundingTime"],
    }


def _parse_premium_klines(value: object) -> Tuple[Dict[str, Any], ...]:
    result = []
    previous = None
    for row in _sequence(value, minimum=2):
        if not isinstance(row, list) or len(row) != 12:
            raise PerpetualContextError("PERPETUAL_KLINE_INVALID")
        open_time = row[0]
        close_time = row[6]
        _from_epoch_ms(open_time)
        _from_epoch_ms(close_time)
        if (
            close_time - open_time != _MINUTE_MS - 1
            or (
                previous is not None
                and open_time != previous + _MINUTE_MS
            )
        ):
            raise PerpetualContextError("PERPETUAL_KLINE_ORDER_INVALID")
        prices = [_decimal(row[index]) for index in (1, 2, 3, 4)]
        if prices[1] < max(prices[0], prices[3]) or prices[2] > min(
            prices[0], prices[3]
        ):
            raise PerpetualContextError("PERPETUAL_KLINE_OHLC_INVALID")
        result.append(
            {
                "open_time": _from_epoch_ms(open_time),
                "open_time_ms": open_time,
                "open": _render(prices[0]),
                "high": _render(prices[1]),
                "low": _render(prices[2]),
                "close": _render(prices[3]),
                "close_time": _from_epoch_ms(close_time),
                "close_time_ms": close_time,
            }
        )
        previous = open_time
    return tuple(result)


def _parse_current_oi(value: object) -> Dict[str, Any]:
    item = _mapping(
        value,
        ("symbol", "openInterest", "time"),
        "PERPETUAL_OPEN_INTEREST_INVALID",
    )
    if item["symbol"] != "ETHUSDT":
        raise PerpetualContextError("PERPETUAL_SYMBOL_INVALID")
    return {
        "symbol": "ETHUSDT",
        "open_interest": _render(
            _decimal(item["openInterest"], nonnegative=True)
        ),
        "source_time": _from_epoch_ms(item["time"]),
        "source_time_ms": item["time"],
    }


def _parse_oi_history(value: object) -> Tuple[Dict[str, Any], ...]:
    result = []
    previous = None
    for source in _sequence(value, minimum=2):
        required = {
            "symbol",
            "sumOpenInterest",
            "sumOpenInterestValue",
            "timestamp",
        }
        if (
            not isinstance(source, Mapping)
            or not required.issubset(source)
            or not set(source).issubset(
                required | {"CMCCirculatingSupply"}
            )
        ):
            raise PerpetualContextError(
                "PERPETUAL_OPEN_INTEREST_HISTORY_INVALID"
            )
        item = source
        if item["symbol"] != "ETHUSDT":
            raise PerpetualContextError("PERPETUAL_SYMBOL_INVALID")
        timestamp = item["timestamp"]
        _from_epoch_ms(timestamp)
        if (
            previous is not None
            and timestamp - previous != _FOUR_HOURS_MS
        ):
            raise PerpetualContextError(
                "PERPETUAL_OPEN_INTEREST_ORDER_INVALID"
            )
        result.append(
            {
                "timestamp": _from_epoch_ms(timestamp),
                "timestamp_ms": timestamp,
                "open_interest": _render(
                    _decimal(item["sumOpenInterest"], nonnegative=True)
                ),
                "open_interest_value_usdt": _render(
                    _decimal(
                        item["sumOpenInterestValue"], nonnegative=True
                    )
                ),
                "cmc_circulating_supply_or_null": (
                    _render(
                        _decimal(
                            item["CMCCirculatingSupply"],
                            nonnegative=True,
                        )
                    )
                    if "CMCCirculatingSupply" in item
                    else None
                ),
            }
        )
        previous = timestamp
    return tuple(result)


def _parse_funding(value: object) -> Tuple[Dict[str, Any], ...]:
    result = []
    previous = None
    for source in _sequence(value, minimum=2):
        item = _mapping(
            source,
            ("symbol", "fundingTime", "fundingRate", "markPrice"),
            "PERPETUAL_FUNDING_HISTORY_INVALID",
        )
        if item["symbol"] != "ETHUSDT":
            raise PerpetualContextError("PERPETUAL_SYMBOL_INVALID")
        timestamp = item["fundingTime"]
        _from_epoch_ms(timestamp)
        if previous is not None and timestamp <= previous:
            raise PerpetualContextError("PERPETUAL_FUNDING_ORDER_INVALID")
        result.append(
            {
                "funding_time": _from_epoch_ms(timestamp),
                "funding_time_ms": timestamp,
                "funding_rate": _render(_decimal(item["fundingRate"])),
                "mark_price": _render(
                    _decimal(item["markPrice"], positive=True)
                ),
            }
        )
        previous = timestamp
    return tuple(result)


def _body(receipt: Mapping[str, Any]) -> object:
    body = receipt.get("response_body_utf8")
    if not isinstance(body, str):
        raise PerpetualContextError("PERPETUAL_RECEIPT_INVALID")
    return _strict_json(body.encode("utf-8"))


def _observed_interval(
    funding: Sequence[Mapping[str, Any]]
) -> Optional[int]:
    deltas = [
        funding[index]["funding_time_ms"]
        - funding[index - 1]["funding_time_ms"]
        for index in range(1, len(funding))
    ]
    if not deltas or len(set(deltas)) != 1:
        return None
    delta = deltas[0]
    hour_ms = 3_600_000
    if delta % hour_ms != 0:
        return None
    hours = delta // hour_ms
    return hours if 1 <= hours <= 24 else None


def _derived(
    receipts: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    if len(receipts) != 5:
        raise PerpetualContextError("PERPETUAL_RECEIPT_SET_INVALID")
    premium = _parse_premium(_body(receipts[0]))
    premium_klines = _parse_premium_klines(_body(receipts[1]))
    current_oi = _parse_current_oi(_body(receipts[2]))
    oi_history = _parse_oi_history(_body(receipts[3]))
    funding = _parse_funding(_body(receipts[4]))

    for source_ms, receipt in (
        (premium["source_time_ms"], receipts[0]),
        (current_oi["source_time_ms"], receipts[2]),
    ):
        started = _epoch_ms(receipt["request_started_at"])
        received = _epoch_ms(receipt["response_received_at"])
        if source_ms < started - 3000 or source_ms > received + 3000:
            raise PerpetualContextError(
                "PERPETUAL_SOURCE_CLOCK_OUTSIDE_WINDOW"
            )
    if (
        oi_history[-1]["timestamp_ms"] > premium["source_time_ms"]
        or funding[-1]["funding_time_ms"] > premium["source_time_ms"]
    ):
        raise PerpetualContextError("PERPETUAL_HISTORY_FROM_FUTURE")
    source_ms = premium["source_time_ms"]
    latest_kline = premium_klines[-1]
    if not (
        latest_kline["open_time_ms"]
        <= source_ms
        <= latest_kline["close_time_ms"]
    ):
        raise PerpetualContextError("PERPETUAL_KLINE_NOT_CURRENT")
    next_funding_ms = premium["next_funding_time_ms"]
    if not source_ms <= next_funding_ms <= source_ms + _DAY_MS:
        raise PerpetualContextError(
            "PERPETUAL_NEXT_FUNDING_TIME_INVALID"
        )
    if source_ms - oi_history[-1]["timestamp_ms"] > _FOUR_HOURS_MS:
        raise PerpetualContextError(
            "PERPETUAL_OPEN_INTEREST_HISTORY_STALE"
        )
    if source_ms - funding[-1]["funding_time_ms"] > _DAY_MS:
        raise PerpetualContextError("PERPETUAL_FUNDING_HISTORY_STALE")

    interval = _observed_interval(funding)
    prior_value = _decimal(
        oi_history[-2]["open_interest_value_usdt"], nonnegative=True
    )
    latest_value = _decimal(
        oi_history[-1]["open_interest_value_usdt"], nonnegative=True
    )
    with localcontext() as context:
        context.prec = 50
        oi_change = (
            (latest_value - prior_value) / prior_value
            if prior_value != 0
            else None
        )
    market = {
        "symbol": "ETHUSDT",
        "market": "USD_M_PERPETUAL",
        "source_time": premium["source_time"],
        "mark_price": premium["mark_price"],
        "index_price": premium["index_price"],
        "estimated_settle_price": premium[
            "estimated_settle_price"
        ],
        "basis_usdt": premium["basis_usdt"],
        "basis_rate": premium["basis_rate"],
        "premium_index_1m_close": premium_klines[-1]["close"],
        "last_funding_rate": premium["last_funding_rate"],
        "interest_rate": premium["interest_rate"],
        "next_funding_time": premium["next_funding_time"],
        "current_open_interest": current_oi["open_interest"],
        "open_interest_source_time": current_oi["source_time"],
        "open_interest_4h_value_change_rate_or_null": (
            _render(oi_change) if oi_change is not None else None
        ),
        "funding_observed_interval_hours": interval,
        "premium_index_klines": list(premium_klines),
        "open_interest_history": list(oi_history),
        "funding_history": list(funding),
    }
    reasons = []
    if interval is None:
        reasons.append("FUNDING_INTERVAL_NOT_PROVEN")
    if oi_change is None:
        reasons.append("OPEN_INTEREST_CHANGE_UNDEFINED_ZERO_BASE")
    quality = {
        "status": "PASS" if not reasons else "DEGRADED",
        "reason_codes": reasons,
        "receipt_count": len(receipts),
        "raw_responses_preserved": True,
        "source_order_verified": True,
        "funding_interval_source": (
            "DERIVED_CONSISTENT_SETTLEMENT_TIMES"
            if interval is not None
            else "NOT_PROVEN"
        ),
    }

    notional = Decimal("1000")
    current_rate = _decimal(premium["last_funding_rate"])
    next_cashflow = notional * current_rate
    count = None
    repeated = None
    adverse = None
    adverse_rate = None
    if interval is not None:
        interval_ms = interval * 3_600_000
        now_ms = premium["source_time_ms"]
        end_ms = now_ms + _DAY_MS
        next_ms = premium["next_funding_time_ms"]
        while next_ms < now_ms:
            next_ms += interval_ms
        count = 0
        cursor = next_ms
        while cursor <= end_ms:
            count += 1
            cursor += interval_ms
        repeated = next_cashflow * count
        recent_max = max(
            abs(_decimal(item["funding_rate"])) for item in funding
        )
        adverse_rate = -(recent_max * 2)
        adverse = notional * adverse_rate * count
    scenarios = {
        "notional_usdt": "1000",
        "sign_convention": "POSITIVE_MEANS_SHORT_RECEIVES",
        "next_funding_short_cashflow_per_1000_usdt": _render(
            next_cashflow
        ),
        "settlement_count_next_24h": count,
        "repeated_current_rate_24h_short_cashflow_per_1000_usdt": (
            _render(repeated) if repeated is not None else None
        ),
        "two_x_recent_absolute_adverse_rate_or_null": (
            _render(adverse_rate) if adverse_rate is not None else None
        ),
        "two_x_recent_absolute_adverse_24h_short_cashflow_per_1000_usdt": (
            _render(adverse) if adverse is not None else None
        ),
        "scenario_semantics": "HYPOTHETICAL_NOT_REALIZED_NOT_FORECAST",
    }
    return market, quality, scenarios


def _validate_receipts(
    receipts: Sequence[Mapping[str, Any]],
    plan: PerpetualContextPlan,
) -> None:
    if not isinstance(receipts, list) or len(receipts) != len(plan.requests):
        raise PerpetualContextError("PERPETUAL_RECEIPT_SET_INVALID")
    previous_receive = None
    for source, request in zip(receipts, plan.requests):
        if not isinstance(source, Mapping):
            raise PerpetualContextError("PERPETUAL_RECEIPT_INVALID")
        if source.get("request") != request.business_payload():
            raise PerpetualContextError("PERPETUAL_REQUEST_REPLAY_MISMATCH")
        body = source.get("response_body_utf8")
        if not isinstance(body, str):
            raise PerpetualContextError("PERPETUAL_RECEIPT_INVALID")
        body_bytes = body.encode("utf-8")
        if hashlib.sha256(body_bytes).hexdigest() != source.get(
            "response_body_sha256"
        ):
            raise PerpetualContextError("PERPETUAL_BODY_HASH_MISMATCH")
        if source.get("status") != 200 or source.get("final_url") != request.url:
            raise PerpetualContextError("PERPETUAL_RESPONSE_REPLAY_MISMATCH")
        started, _ = _utc(source.get("request_started_at"))
        received, _ = _utc(source.get("response_received_at"))
        if received < started or (
            previous_receive is not None and started < previous_receive
        ):
            raise PerpetualContextError("PERPETUAL_RECEIPT_TIME_INVALID")
        body_without_hash = dict(source)
        receipt_hash = body_without_hash.pop("receipt_hash", None)
        if business_hash(body_without_hash) != receipt_hash:
            raise PerpetualContextError("PERPETUAL_RECEIPT_HASH_MISMATCH")
        _strict_json(body_bytes)
        previous_receive = received


@lru_cache(maxsize=1)
def _snapshot_validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas", "perpetual-context-snapshot-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def build_perpetual_context_snapshot(
    capture: VerifiedPerpetualContextCapture,
) -> Dict[str, Any]:
    if not isinstance(capture, VerifiedPerpetualContextCapture):
        raise PerpetualContextError("PERPETUAL_CAPTURE_UNVERIFIED")
    plan = capture.plan
    receipts = [dict(item) for item in capture.receipts]
    _validate_receipts(receipts, plan)
    _validate_probe_capture_boundary(capture.server_time_probe, receipts)
    market, quality, scenarios = _derived(receipts)
    identity = {
        "plan_hash": plan.plan_hash,
        "server_time_probe_hash": capture.server_time_probe["probe_hash"],
        "receipt_hashes": [item["receipt_hash"] for item in receipts],
    }
    snapshot = {
        "$schema": "./perpetual-context-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": stable_id("perpetual_context", identity),
        "snapshot_hash": "",
        "recorded_at": capture.recorded_at,
        "policy": {
            **plan.business_payload(),
            "plan_hash": plan.plan_hash,
        },
        "server_time_probe": dict(capture.server_time_probe),
        "receipts": receipts,
        "market_context": market,
        "quality_report": quality,
        "short_funding_scenarios": scenarios,
        "network_request_count": capture.network_request_count,
        "context_eligibility": "CONTEMPORANEOUS_CONTEXT_ONLY",
        "short_execution_eligibility": "NOT_IMPLEMENTED",
        "paper_eligibility": "LONGITUDINAL_COLLECTION_IN_PROGRESS",
        "profitability_eligibility": (
            "INSUFFICIENT_DURATION_COST_AND_EXECUTION"
        ),
        "warnings": list(_WARNINGS),
    }
    snapshot["snapshot_hash"] = artifact_self_hash(
        snapshot, "snapshot_hash"
    )
    if tuple(_snapshot_validator().iter_errors(snapshot)):
        raise PerpetualContextError("PERPETUAL_SNAPSHOT_SCHEMA_INVALID")
    return snapshot


def perpetual_context_trust_hash(snapshot: Mapping[str, Any]) -> str:
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
            }
        )
    except (KeyError, TypeError):
        return ""


def perpetual_context_reasons(
    snapshot: Mapping[str, Any],
    trusted_attestation_hash: str,
) -> Tuple[str, ...]:
    if not isinstance(snapshot, Mapping):
        return ("PERPETUAL_SNAPSHOT_INVALID",)
    reasons = []
    try:
        if tuple(_snapshot_validator().iter_errors(snapshot)):
            reasons.append("PERPETUAL_SNAPSHOT_SCHEMA_INVALID")
        if artifact_self_hash(snapshot, "snapshot_hash") != snapshot.get(
            "snapshot_hash"
        ):
            reasons.append("PERPETUAL_SNAPSHOT_SELF_HASH_MISMATCH")
        if (
            perpetual_context_trust_hash(snapshot)
            != trusted_attestation_hash
        ):
            reasons.append("PERPETUAL_SNAPSHOT_TRUST_HASH_MISMATCH")
        plan = PerpetualContextPlan.create()
        expected_policy = {
            **plan.business_payload(),
            "plan_hash": plan.plan_hash,
        }
        if snapshot.get("policy") != expected_policy:
            reasons.append("PERPETUAL_POLICY_MISMATCH")
        probe = snapshot["server_time_probe"]
        if server_time_probe_reasons(
            probe, server_time_probe_trust_hash(probe)
        ):
            reasons.append("PERPETUAL_SERVER_TIME_PROBE_INVALID")
        receipts = snapshot["receipts"]
        _validate_receipts(receipts, plan)
        _validate_probe_capture_boundary(probe, receipts)
        market, quality, scenarios = _derived(receipts)
        if snapshot.get("market_context") != market:
            reasons.append("PERPETUAL_MARKET_CONTEXT_MISMATCH")
        if snapshot.get("quality_report") != quality:
            reasons.append("PERPETUAL_QUALITY_REPORT_MISMATCH")
        if snapshot.get("short_funding_scenarios") != scenarios:
            reasons.append("PERPETUAL_FUNDING_SCENARIOS_MISMATCH")
        if snapshot.get("network_request_count") != 8:
            reasons.append("PERPETUAL_NETWORK_COUNT_INVALID")
        recorded, _ = _utc(snapshot["recorded_at"])
        last_received, _ = _utc(receipts[-1]["response_received_at"])
        if recorded < last_received:
            reasons.append("PERPETUAL_RECORDED_TIME_INVALID")
        identity = {
            "plan_hash": plan.plan_hash,
            "server_time_probe_hash": probe["probe_hash"],
            "receipt_hashes": [item["receipt_hash"] for item in receipts],
        }
        if snapshot.get("snapshot_id") != stable_id(
            "perpetual_context", identity
        ):
            reasons.append("PERPETUAL_SNAPSHOT_ID_MISMATCH")
    except (
        KeyError,
        TypeError,
        ValueError,
        PerpetualContextError,
    ):
        reasons.append("PERPETUAL_SNAPSHOT_REPLAY_INVALID")
    for name, expected in (
        ("context_eligibility", "CONTEMPORANEOUS_CONTEXT_ONLY"),
        ("short_execution_eligibility", "NOT_IMPLEMENTED"),
        ("paper_eligibility", "LONGITUDINAL_COLLECTION_IN_PROGRESS"),
        (
            "profitability_eligibility",
            "INSUFFICIENT_DURATION_COST_AND_EXECUTION",
        ),
    ):
        if snapshot.get(name) != expected:
            reasons.append("PERPETUAL_ELIGIBILITY_INVALID")
    if snapshot.get("warnings") != list(_WARNINGS):
        reasons.append("PERPETUAL_WARNINGS_INVALID")
    return tuple(sorted(set(reasons)))


def publish_perpetual_context(
    *,
    output_root: Path,
    server_time_transport=None,
    futures_transport=None,
) -> Dict[str, Any]:
    capture = capture_perpetual_context(
        server_time_transport=server_time_transport,
        futures_transport=futures_transport,
    )
    snapshot = build_perpetual_context_snapshot(capture)
    trust_hash = perpetual_context_trust_hash(snapshot)
    if perpetual_context_reasons(snapshot, trust_hash):
        raise PerpetualContextError("PERPETUAL_SNAPSHOT_INVALID")
    artifact_name = snapshot["snapshot_id"].lower() + ".json"
    artifact_bytes = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    path = Path(output_root).resolve() / "market-data" / artifact_name
    created = _publish_immutable(
        Path(output_root),
        artifact_name,
        artifact_bytes,
        output_directory="market-data",
    )
    return {
        "outcome": "CAPTURED",
        "artifact_path": str(path),
        "artifact_created": created,
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_hash": snapshot["snapshot_hash"],
        "trust_hash": trust_hash,
        "network_request_count": snapshot["network_request_count"],
        "context_eligibility": snapshot["context_eligibility"],
        "short_execution_eligibility": snapshot[
            "short_execution_eligibility"
        ],
    }
