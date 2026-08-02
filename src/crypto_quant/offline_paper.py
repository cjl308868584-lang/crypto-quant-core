"""One-cycle, public-only offline Paper replay with conservative economics.

This module deliberately exposes no account, credential, Broker, or order-submit
surface.  Its only network boundary is four frozen public GET requests.  Every
economic result is produced in temporary, independent SQLite WAL ledgers.
"""

import hashlib
import json
import tempfile
from functools import lru_cache
from importlib import resources
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_decimal, stable_id, utc_datetime
from .contracts import (
    DecisionSource,
    DeploymentStage,
    Direction,
    EventEnvelope,
    MetaDecision,
    StrategyProposal,
    StrategyRole,
    TargetAction,
    TargetPosition,
)
from .decimal_math import RiskRatio, round_down_to_step, round_price_down, round_price_up
from .economics import economic_snapshot_reasons
from .evidence import artifact_self_hash
from .instruments import InstrumentMetadata, MarketType
from .ledger import EventLedger


_BASE_URL = "https://data-api.binance.vision"
_HOST = "data-api.binance.vision"
_ALLOWED_SYMBOLS = frozenset(("ETHUSDT",))
_MAX_BODY_BYTES = 2 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_HTTP_TIMEOUT_SECONDS = 15
_HTTP_ATTEMPTS = 1
_PLAN_TOKEN = object()
_CAPTURE_TOKEN = object()
_DECIMAL_CONTEXT = Context(prec=50)
_FOUR_HOURS_MS = 14_400_000
_STARTING_EQUITY = Decimal("1000")
_VOLATILITY_TARGET = Decimal("0.12")
_RISK_BUCKET = Decimal("0.25")
_TAKER_FEE = Decimal("0.0015")
_SLIPPAGE = Decimal("0.001")
_BASELINE_VERSION = "SPOT_LONG_SMA20_VOL12_BUCKET25_V1"
_FILL_POLICY_VERSION = "OFFLINE_PAPER_CONSERVATIVE_BBO_V1"
_ATTESTATION_TYPE = "OFFLINE_PAPER_RUN_ATTESTATION"

OFFLINE_PAPER_WARNINGS = (
    "ACCOUNT_FEE_SCHEDULE_UNOBSERVED",
    "ACCOUNT_SPECIFIC_FILTERS_UNOBSERVED",
    "BBO_SEQUENCE_UNOBSERVABLE_REST_SNAPSHOT",
    "AGG_TRADE_WINDOW_GAPS_POSSIBLE",
    "PERPETUAL_CONTEXT_NOT_CAPTURED",
    "AI_MODEL_NOT_RUN",
    "PAPER_DURATION_BELOW_90_DAYS",
    "NO_FORMAL_STATISTICAL_SAMPLE",
)


@lru_cache(maxsize=1)
def _run_validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas", "offline-paper-run-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class OfflinePaperError(ValueError):
    """The public capture or deterministic replay failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> Tuple[datetime, str]:
    if not isinstance(value, str):
        raise OfflinePaperError("PAPER_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OfflinePaperError("PAPER_TIME_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OfflinePaperError("PAPER_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    converted = converted.replace(microsecond=(converted.microsecond // 1000) * 1000)
    return converted, utc_datetime(converted)


def _milliseconds(value: object) -> Tuple[datetime, str]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OfflinePaperError("PAPER_SOURCE_TIME_INVALID")
    try:
        parsed = datetime.fromtimestamp(value / 1000, timezone.utc)
    except (OverflowError, OSError, ValueError) as error:
        raise OfflinePaperError("PAPER_SOURCE_TIME_INVALID") from error
    return _utc(parsed.isoformat())


def _decimal(value: object, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise OfflinePaperError("PAPER_DECIMAL_INVALID")
    try:
        with localcontext(_DECIMAL_CONTEXT):
            number = Decimal(value)
    except InvalidOperation as error:
        raise OfflinePaperError("PAPER_DECIMAL_INVALID") from error
    if not number.is_finite() or (positive and number <= 0):
        raise OfflinePaperError("PAPER_DECIMAL_INVALID")
    if number.is_zero() and number.is_signed():
        raise OfflinePaperError("PAPER_DECIMAL_INVALID")
    return number


def _strict_json(body: bytes) -> Any:
    if not isinstance(body, bytes) or len(body) > _MAX_BODY_BYTES:
        raise OfflinePaperError("PAPER_RESPONSE_TOO_LARGE")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise OfflinePaperError("PAPER_JSON_DUPLICATE_KEY")
            result[key] = value
        return result

    def reject_number(_value):
        raise OfflinePaperError("PAPER_JSON_FLOAT_FORBIDDEN")

    try:
        return json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except OfflinePaperError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OfflinePaperError("PAPER_JSON_INVALID") from error


@dataclass(frozen=True, init=False)
class OfflinePaperPlan:
    schema_version: str
    provider: str
    symbol: str

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _PLAN_TOKEN:
            raise TypeError("OfflinePaperPlan must be created with create")
        object.__setattr__(self, "schema_version", "1.0.0")
        object.__setattr__(self, "provider", "BINANCE_MARKET_DATA_ONLY")
        object.__setattr__(self, "symbol", kwargs["symbol"])

    @classmethod
    def create(cls, symbol: str) -> "OfflinePaperPlan":
        if symbol not in _ALLOWED_SYMBOLS:
            raise OfflinePaperError("PAPER_PLAN_INVALID")
        return cls(symbol=symbol, _token=_PLAN_TOKEN)


@dataclass(frozen=True)
class OfflinePaperRequest:
    request_id: str
    stage: str
    family: str
    symbol: str
    method: str
    url: str


@dataclass(frozen=True)
class PublicPaperHttpResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes
    request_started_at: str
    response_received_at: str


def _request(stage: str, family: str, symbol: str, path: str, query):
    url = _BASE_URL + path + "?" + urlencode(sorted(query.items()))
    identity = {
        "stage": stage,
        "family": family,
        "symbol": symbol,
        "method": "GET",
        "url": url,
    }
    return OfflinePaperRequest(
        request_id="paperreq_" + business_hash(identity),
        stage=stage,
        family=family,
        symbol=symbol,
        method="GET",
        url=url,
    )


def offline_paper_requests(plan: OfflinePaperPlan) -> Tuple[OfflinePaperRequest, ...]:
    if not isinstance(plan, OfflinePaperPlan):
        raise OfflinePaperError("PAPER_PLAN_INVALID")
    symbol = plan.symbol
    return (
        _request(
            "DECISION_INPUT",
            "SPOT_KLINE_4H_WARMUP",
            symbol,
            "/api/v3/klines",
            {"symbol": symbol, "interval": "4h", "limit": 200},
        ),
        _request(
            "DECISION_INPUT",
            "SPOT_EXCHANGE_INFO",
            symbol,
            "/api/v3/exchangeInfo",
            {"symbol": symbol},
        ),
        _request(
            "EXECUTION_OBSERVATION",
            "SPOT_BBO",
            symbol,
            "/api/v3/ticker/bookTicker",
            {"symbol": symbol},
        ),
        _request(
            "EXECUTION_OBSERVATION",
            "SPOT_AGG_TRADE",
            symbol,
            "/api/v3/aggTrades",
            {"symbol": symbol, "limit": 100},
        ),
    )


def _valid_public_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == _HOST
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
            and parsed.path.startswith("/api/v3/")
        )
    except ValueError:
        return False


class _SameHostRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _valid_public_url(newurl):
            raise OfflinePaperError("PAPER_REDIRECT_INVALID")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _utc_now() -> str:
    return utc_datetime(datetime.now(timezone.utc))


def _read_bounded(response: object) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = response.read(min(_READ_CHUNK_BYTES, _MAX_BODY_BYTES - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_BODY_BYTES:
            raise OfflinePaperError("PAPER_RESPONSE_TOO_LARGE")
        chunks.append(chunk)
    return b"".join(chunks)


class BinanceOfflinePaperTransport:
    """Credential-free transport accepting only the four frozen request objects."""

    def __init__(self, *, clock=None, opener=None):
        self._clock = clock or _utc_now
        self._opener = opener or build_opener(
            ProxyHandler({}), _SameHostRedirectHandler()
        )

    def get(self, request: OfflinePaperRequest) -> PublicPaperHttpResponse:
        try:
            allowed = offline_paper_requests(OfflinePaperPlan.create(request.symbol))
        except (AttributeError, OfflinePaperError):
            allowed = ()
        if (
            not isinstance(request, OfflinePaperRequest)
            or request not in allowed
            or not _valid_public_url(request.url)
        ):
            raise OfflinePaperError("PAPER_REQUEST_INVALID")
        for attempt in range(_HTTP_ATTEMPTS):
            started = self._clock()
            try:
                with self._opener.open(
                    Request(request.url, method="GET"),
                    timeout=_HTTP_TIMEOUT_SECONDS,
                ) as response:
                    status = response.getcode()
                    result = PublicPaperHttpResponse(
                        status=status,
                        final_url=response.geturl(),
                        headers=dict(response.headers.items()),
                        body=_read_bounded(response),
                        request_started_at=started,
                        response_received_at=self._clock(),
                    )
                if status >= 500 and attempt + 1 < _HTTP_ATTEMPTS:
                    continue
                return result
            except HTTPError as error:
                if error.code >= 500 and attempt + 1 < _HTTP_ATTEMPTS:
                    continue
                return PublicPaperHttpResponse(
                    status=error.code,
                    final_url=error.geturl(),
                    headers=dict(error.headers.items()) if error.headers else {},
                    body=b"",
                    request_started_at=started,
                    response_received_at=self._clock(),
                )
            except OfflinePaperError:
                raise
            except (OSError, TimeoutError, URLError) as error:
                if attempt + 1 == _HTTP_ATTEMPTS:
                    raise OfflinePaperError("PAPER_TRANSPORT_FAILURE") from error
        raise OfflinePaperError("PAPER_TRANSPORT_FAILURE")


def _selected_headers(headers: object) -> Dict[str, Optional[str]]:
    if not isinstance(headers, Mapping):
        raise OfflinePaperError("PAPER_RESPONSE_INVALID")
    lowered = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise OfflinePaperError("PAPER_RESPONSE_INVALID")
        lowered[key.lower()] = value
    return {
        "http_date_or_null": lowered.get("date"),
        "etag_or_null": lowered.get("etag"),
        "last_modified_or_null": lowered.get("last-modified"),
        "retry_after_or_null": lowered.get("retry-after"),
    }


def _receipt(
    request: OfflinePaperRequest,
    response: PublicPaperHttpResponse,
    recorded_at: object,
) -> Dict[str, Any]:
    if (
        not isinstance(response, PublicPaperHttpResponse)
        or response.status != 200
        or response.final_url != request.url
        or not _valid_public_url(response.final_url)
        or not isinstance(response.body, bytes)
        or len(response.body) > _MAX_BODY_BYTES
    ):
        raise OfflinePaperError("PAPER_RESPONSE_INVALID")
    started, started_text = _utc(response.request_started_at)
    received, received_text = _utc(response.response_received_at)
    recorded, recorded_text = _utc(recorded_at)
    if received < started or recorded < received:
        raise OfflinePaperError("PAPER_CLOCK_INVALID")
    _strict_json(response.body)
    try:
        body_text = response.body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise OfflinePaperError("PAPER_JSON_INVALID") from error
    receipt = {
        "request_id": request.request_id,
        "stage": request.stage,
        "family": request.family,
        "symbol": request.symbol,
        "method": request.method,
        "url": request.url,
        "request_started_at": started_text,
        "response_received_at": received_text,
        "recorded_at": recorded_text,
        "status": response.status,
        "final_url": response.final_url,
        **_selected_headers(response.headers),
        "body_size_bytes": len(response.body),
        "body_sha256": hashlib.sha256(response.body).hexdigest(),
        "response_body_utf8": body_text,
    }
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    return receipt


@dataclass(frozen=True, init=False)
class VerifiedOfflinePaperCapture:
    plan: OfflinePaperPlan
    decision_time: str
    receipts: Tuple[Mapping[str, Any], ...]

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _CAPTURE_TOKEN:
            raise TypeError("VerifiedOfflinePaperCapture is issued by capture_offline_paper")
        object.__setattr__(self, "plan", kwargs["plan"])
        object.__setattr__(self, "decision_time", kwargs["decision_time"])
        object.__setattr__(self, "receipts", tuple(kwargs["receipts"]))

    def replay_with_receipts(
        self, receipts: Sequence[Mapping[str, Any]]
    ) -> "VerifiedOfflinePaperCapture":
        return _capture_from_receipts(self.plan, receipts)


def _recorded(clock) -> str:
    return clock() if callable(clock) else clock


def capture_offline_paper(
    plan: OfflinePaperPlan,
    transport: object,
    *,
    recorded_at,
) -> VerifiedOfflinePaperCapture:
    if not isinstance(plan, OfflinePaperPlan):
        raise OfflinePaperError("PAPER_PLAN_INVALID")
    receipts = []
    requests = offline_paper_requests(plan)
    for index, request in enumerate(requests):
        try:
            response = transport.get(request)
        except OfflinePaperError:
            raise
        except Exception as error:
            raise OfflinePaperError("PAPER_TRANSPORT_FAILURE") from error
        receipt = _receipt(request, response, _recorded(recorded_at))
        if index == 2:
            decision_dt, _ = _utc(receipts[1]["response_received_at"])
            started_dt, _ = _utc(receipt["request_started_at"])
            if started_dt < decision_dt:
                raise OfflinePaperError("PAPER_STAGE_ORDER_INVALID")
        if index > 2:
            decision_dt, _ = _utc(receipts[1]["response_received_at"])
            started_dt, _ = _utc(receipt["request_started_at"])
            if started_dt < decision_dt:
                raise OfflinePaperError("PAPER_STAGE_ORDER_INVALID")
        receipts.append(receipt)
    decision_time = max(
        receipts[0]["response_received_at"], receipts[1]["response_received_at"]
    )
    return VerifiedOfflinePaperCapture(
        plan=plan,
        decision_time=decision_time,
        receipts=receipts,
        _token=_CAPTURE_TOKEN,
    )


def _capture_from_receipts(
    plan: OfflinePaperPlan,
    receipts: Sequence[Mapping[str, Any]],
) -> VerifiedOfflinePaperCapture:
    if not isinstance(receipts, (list, tuple)) or len(receipts) != 4:
        raise OfflinePaperError("PAPER_RECEIPTS_INVALID")
    expected = offline_paper_requests(plan)
    verified = []
    for request, source in zip(expected, receipts):
        if not isinstance(source, Mapping):
            raise OfflinePaperError("PAPER_RECEIPT_INVALID")
        try:
            body = source["response_body_utf8"].encode("utf-8")
        except (AttributeError, KeyError) as error:
            raise OfflinePaperError("PAPER_RECEIPT_INVALID") from error
        _strict_json(body)
        if hashlib.sha256(body).hexdigest() != source.get("body_sha256"):
            raise OfflinePaperError("PAPER_RECEIPT_BODY_HASH_MISMATCH")
        if artifact_self_hash(source, "receipt_hash") != source.get("receipt_hash"):
            raise OfflinePaperError("PAPER_RECEIPT_SELF_HASH_MISMATCH")
        for name, value in (
            ("request_id", request.request_id),
            ("stage", request.stage),
            ("family", request.family),
            ("symbol", request.symbol),
            ("method", request.method),
            ("url", request.url),
            ("final_url", request.url),
            ("status", 200),
        ):
            if source.get(name) != value:
                raise OfflinePaperError("PAPER_RECEIPT_IDENTITY_MISMATCH")
        if source.get("body_size_bytes") != len(body):
            raise OfflinePaperError("PAPER_RECEIPT_SIZE_MISMATCH")
        started, _ = _utc(source.get("request_started_at"))
        received, _ = _utc(source.get("response_received_at"))
        recorded, _ = _utc(source.get("recorded_at"))
        if received < started or recorded < received:
            raise OfflinePaperError("PAPER_CLOCK_INVALID")
        verified.append(dict(source))
    decision_time = max(
        verified[0]["response_received_at"], verified[1]["response_received_at"]
    )
    decision_dt, _ = _utc(decision_time)
    for receipt in verified[2:]:
        started, _ = _utc(receipt["request_started_at"])
        if started < decision_dt:
            raise OfflinePaperError("PAPER_STAGE_ORDER_INVALID")
    return VerifiedOfflinePaperCapture(
        plan=plan,
        decision_time=decision_time,
        receipts=verified,
        _token=_CAPTURE_TOKEN,
    )


def _parse_klines(body: bytes, decision_time: datetime) -> Tuple[Dict[str, Any], ...]:
    payload = _strict_json(body)
    if not isinstance(payload, list) or not 21 <= len(payload) <= 200:
        raise OfflinePaperError("PAPER_WARMUP_INVALID")
    rows = []
    previous_open = None
    for row in payload:
        if (
            not isinstance(row, list)
            or len(row) != 12
            or isinstance(row[8], bool)
            or not isinstance(row[8], int)
            or row[8] < 0
            or row[11] != "0"
            or isinstance(row[0], bool)
            or not isinstance(row[0], int)
            or isinstance(row[6], bool)
            or not isinstance(row[6], int)
            or row[6] - row[0] + 1 != _FOUR_HOURS_MS
        ):
            raise OfflinePaperError("PAPER_KLINE_INVALID")
        open_dt, open_text = _milliseconds(row[0])
        close_dt, close_text = _milliseconds(row[6])
        if previous_open is not None and open_dt <= previous_open:
            raise OfflinePaperError("PAPER_KLINE_ORDER_INVALID")
        previous_open = open_dt
        opening, high, low, close = [_decimal(row[i], positive=True) for i in (1, 2, 3, 4)]
        if low > opening or low > close or high < opening or high < close or low > high:
            raise OfflinePaperError("PAPER_KLINE_INVALID")
        for item in (5, 7, 9, 10):
            if _decimal(row[item]) < 0:
                raise OfflinePaperError("PAPER_KLINE_INVALID")
        if close_dt < decision_time:
            rows.append(
                {
                    "open_time": open_text,
                    "close_time": close_text,
                    "open": canonical_decimal(opening),
                    "high": canonical_decimal(high),
                    "low": canonical_decimal(low),
                    "close": canonical_decimal(close),
                    "trade_count": row[8],
                    "source_row_hash": business_hash(row),
                }
            )
    if len(rows) < 21:
        raise OfflinePaperError("PAPER_CLOSED_WARMUP_INSUFFICIENT")
    return tuple(rows)


def _find_filter(filters: object, name: str) -> Mapping[str, Any]:
    if not isinstance(filters, list):
        raise OfflinePaperError("PAPER_EXCHANGE_INFO_INVALID")
    matches = [
        item
        for item in filters
        if isinstance(item, Mapping) and item.get("filterType") == name
    ]
    if len(matches) != 1:
        raise OfflinePaperError("PAPER_EXCHANGE_FILTER_INVALID")
    return matches[0]


def _parse_exchange_info(body: bytes, decision_time: datetime) -> InstrumentMetadata:
    payload = _strict_json(body)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("symbols"), list):
        raise OfflinePaperError("PAPER_EXCHANGE_INFO_INVALID")
    symbols = payload["symbols"]
    if len(symbols) != 1 or not isinstance(symbols[0], Mapping):
        raise OfflinePaperError("PAPER_EXCHANGE_INFO_INVALID")
    symbol = symbols[0]
    if (
        symbol.get("symbol") != "ETHUSDT"
        or symbol.get("status") != "TRADING"
        or symbol.get("baseAsset") != "ETH"
        or symbol.get("quoteAsset") != "USDT"
        or symbol.get("isSpotTradingAllowed") is not True
        or not isinstance(symbol.get("orderTypes"), list)
        or "MARKET" not in symbol["orderTypes"]
    ):
        raise OfflinePaperError("PAPER_EXCHANGE_INFO_INELIGIBLE")
    price_filter = _find_filter(symbol.get("filters"), "PRICE_FILTER")
    lot_filter = _find_filter(symbol.get("filters"), "LOT_SIZE")
    minimums = []
    for name in ("MIN_NOTIONAL", "NOTIONAL"):
        matches = [
            item
            for item in symbol["filters"]
            if isinstance(item, Mapping) and item.get("filterType") == name
        ]
        if len(matches) > 1:
            raise OfflinePaperError("PAPER_EXCHANGE_FILTER_INVALID")
        if matches:
            minimums.append(_decimal(matches[0].get("minNotional"), positive=True))
    if not minimums:
        raise OfflinePaperError("PAPER_EXCHANGE_FILTER_INVALID")
    supported_tif = tuple(
        item for item in ("GTC", "IOC", "FOK") if "LIMIT" in symbol["orderTypes"]
    )
    return InstrumentMetadata(
        schema_version="1.0.0",
        instrument_id="BINANCE:SPOT:ETHUSDT",
        exchange="BINANCE",
        market_type=MarketType.SPOT,
        symbol="ETHUSDT",
        base_asset="ETH",
        quote_asset="USDT",
        settlement_asset="USDT",
        effective_from=decision_time,
        effective_to_or_null=None,
        price_tick=_decimal(price_filter.get("tickSize"), positive=True),
        quantity_step=_decimal(lot_filter.get("stepSize"), positive=True),
        min_quantity=_decimal(lot_filter.get("minQty"), positive=True),
        max_quantity=_decimal(lot_filter.get("maxQty"), positive=True),
        min_notional=max(minimums),
        contract_multiplier=Decimal("1"),
        supported_order_types=tuple(symbol["orderTypes"]),
        supported_time_in_force=supported_tif,
        supports_reduce_only=False,
        supports_stop_market="STOP_LOSS" in symbol["orderTypes"],
        maker_fee=_TAKER_FEE,
        taker_fee=_TAKER_FEE,
        metadata_source="BINANCE_PUBLIC_EXCHANGE_INFO_RESPONSE",
    )


def _parse_bbo(body: bytes) -> Dict[str, str]:
    payload = _strict_json(body)
    if not isinstance(payload, Mapping) or set(payload) != {
        "symbol", "bidPrice", "bidQty", "askPrice", "askQty"
    } or payload["symbol"] != "ETHUSDT":
        raise OfflinePaperError("PAPER_BBO_INVALID")
    bid = _decimal(payload["bidPrice"], positive=True)
    ask = _decimal(payload["askPrice"], positive=True)
    bid_qty = _decimal(payload["bidQty"])
    ask_qty = _decimal(payload["askQty"])
    if bid > ask or bid_qty < 0 or ask_qty < 0:
        raise OfflinePaperError("PAPER_BBO_INVALID")
    return {
        "bid_price": canonical_decimal(bid),
        "bid_quantity": canonical_decimal(bid_qty),
        "ask_price": canonical_decimal(ask),
        "ask_quantity": canonical_decimal(ask_qty),
    }


def _parse_agg_trades(body: bytes) -> Dict[str, Any]:
    payload = _strict_json(body)
    if not isinstance(payload, list) or not payload or len(payload) > 100:
        raise OfflinePaperError("PAPER_AGG_TRADE_INVALID")
    ids = []
    normalized = []
    for row in payload:
        if not isinstance(row, Mapping) or set(row) != {
            "a", "p", "q", "f", "l", "T", "m", "M"
        }:
            raise OfflinePaperError("PAPER_AGG_TRADE_INVALID")
        integers = [row[name] for name in ("a", "f", "l", "T")]
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in integers):
            raise OfflinePaperError("PAPER_AGG_TRADE_INVALID")
        if row["f"] > row["l"] or not isinstance(row["m"], bool) or not isinstance(row["M"], bool):
            raise OfflinePaperError("PAPER_AGG_TRADE_INVALID")
        _decimal(row["p"], positive=True)
        _decimal(row["q"], positive=True)
        _, trade_time = _milliseconds(row["T"])
        ids.append(row["a"])
        normalized.append(
            {
                "aggregate_trade_id": row["a"],
                "price": canonical_decimal(_decimal(row["p"], positive=True)),
                "quantity": canonical_decimal(_decimal(row["q"], positive=True)),
                "trade_time": trade_time,
                "source_row_hash": business_hash(row),
            }
        )
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise OfflinePaperError("PAPER_AGG_TRADE_ORDER_INVALID")
    gaps = sum(max(0, right - left - 1) for left, right in zip(ids, ids[1:]))
    return {
        "observed_count": len(normalized),
        "first_aggregate_trade_id": ids[0],
        "last_aggregate_trade_id": ids[-1],
        "observable_gap_count": gaps,
        "trades": normalized,
    }


def _sample_volatility(closes: Sequence[Decimal]) -> Decimal:
    if len(closes) != 21:
        raise OfflinePaperError("PAPER_VOLATILITY_INPUT_INVALID")
    with localcontext(_DECIMAL_CONTEXT):
        returns = [(closes[index] / closes[index - 1]).ln() for index in range(1, 21)]
        mean = sum(returns, Decimal("0")) / Decimal(len(returns))
        variance = sum((item - mean) ** 2 for item in returns) / Decimal(len(returns) - 1)
        annualizer = Decimal(6 * 365).sqrt()
        return variance.sqrt() * annualizer


def build_baseline_paper_decision(
    klines: Sequence[Mapping[str, Any]],
    decision_time: datetime,
    market_hash: str,
) -> Tuple[Dict[str, Any], Optional[TargetPosition]]:
    selected = tuple(klines[-21:])
    closes = tuple(Decimal(item["close"]) for item in selected)
    latest = closes[-1]
    sma = sum(closes[:-1], Decimal("0")) / Decimal("20")
    volatility = _sample_volatility(closes)
    denominator = max(volatility, _VOLATILITY_TARGET)
    exposure = min(Decimal("1"), _VOLATILITY_TARGET / denominator)
    is_long = latest > sma
    direction = Direction.LONG if is_long else Direction.FLAT
    action = TargetAction.SET_TARGET if is_long else TargetAction.HOLD_CURRENT
    raw_strength = latest / sma - Decimal("1")
    input_payload = {
        "market_hash": market_hash,
        "closed_kline_hashes": [item["source_row_hash"] for item in selected],
        "latest_close": canonical_decimal(latest),
        "prior_20_sma": canonical_decimal(sma),
        "annualized_log_return_volatility": canonical_decimal(volatility),
        "decision_time": utc_datetime(decision_time),
    }
    proposal = StrategyProposal(
        schema_version="1.0.0",
        market_snapshot_id="market_" + market_hash,
        feature_snapshot_id=stable_id("features", input_payload),
        strategy_id="spot-long-sma20-vol12",
        strategy_version=_BASELINE_VERSION,
        strategy_role=StrategyRole.BASE,
        instrument_id="BINANCE:SPOT:ETHUSDT",
        direction=direction,
        raw_strength=raw_strength,
        reason_codes=("LATEST_CLOSE_ABOVE_PRIOR_SMA20",) if is_long else (
            "LATEST_CLOSE_NOT_ABOVE_PRIOR_SMA20",
        ),
        expected_horizon_hours=24,
        minimum_hold_hours=8,
        valid_until=decision_time + timedelta(hours=24),
        created_at=decision_time,
    )
    prediction_hash = business_hash(
        {
            "baseline_version": _BASELINE_VERSION,
            "direction": direction.value,
            "action": action.value,
            "risk_bucket_or_null": "0.25" if is_long else None,
            "input_hash": business_hash(input_payload),
        }
    )
    meta = MetaDecision(
        schema_version="1.0.0",
        proposal_id=proposal.proposal_id,
        decision_source=DecisionSource.NO_AI_BASE,
        no_ai_base_version_or_null=_BASELINE_VERSION,
        model_id_or_null=None,
        model_version_or_null=None,
        deployment_stage=DeploymentStage.PAPER,
        calibration_version_or_null=None,
        p_net_positive_or_null=None,
        expected_net_return_or_null=None,
        return_q10_or_null=None,
        return_q50_or_null=None,
        return_q90_or_null=None,
        uncertainty_score_or_null=None,
        ood_score_or_null=None,
        eligible=True,
        ineligibility_reason_mask=(),
        recommended_action=action,
        recommended_bucket_or_null=RiskRatio(_RISK_BUCKET) if is_long else None,
        model_input_hash=business_hash(input_payload),
        prediction_hash=prediction_hash,
    )
    target = TargetPosition(
        schema_version="1.0.0",
        target_sequence=0,
        supersedes_target_id_or_null=None,
        instrument_id="BINANCE:SPOT:ETHUSDT",
        account_id="paper-baseline",
        target_action=action,
        direction=direction,
        signed_target_ratio_or_null=exposure * _RISK_BUCKET if is_long else None,
        risk_bucket_or_null=RiskRatio(_RISK_BUCKET) if is_long else None,
        base_volatility_exposure=RiskRatio(exposure),
        target_notional_usdt_or_null=(
            _STARTING_EQUITY * exposure * _RISK_BUCKET if is_long else None
        ),
        volatility_target=_VOLATILITY_TARGET,
        volatility_estimator_version="4H_LOG_RETURN_SAMPLE_STD_ANNUALIZED_V1",
        decision_time=decision_time,
        valid_until=decision_time + timedelta(hours=24),
        minimum_hold_until=decision_time + timedelta(hours=8),
        hysteresis_state="INITIAL_OFFLINE_PAPER",
        source_proposal_id=proposal.proposal_id,
        source_meta_decision_id=meta.meta_decision_id,
        position_policy_version=_BASELINE_VERSION,
    )
    target.assert_lineage(proposal, meta)
    decision = {
        "decision_source": "NO_AI_BASE",
        "strategy_version": _BASELINE_VERSION,
        "direction": direction.value,
        "recommended_action": action.value,
        "risk_bucket": "0.25" if is_long else None,
        "latest_close": canonical_decimal(latest),
        "prior_20_sma": canonical_decimal(sma),
        "annualized_log_return_volatility": canonical_decimal(volatility),
        "base_volatility_exposure": canonical_decimal(exposure),
        "proposal": proposal.business_payload(),
        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal.proposal_hash,
        "meta_decision": meta.business_payload(),
        "meta_decision_id": meta.meta_decision_id,
        "prediction_business_hash": meta.prediction_business_hash,
        "target_position": target.business_payload(),
        "target_id": target.target_id,
        "target_hash": target.target_hash,
    }
    return decision, target


def _conservative_fill(
    target: Optional[TargetPosition],
    metadata: InstrumentMetadata,
    bbo: Mapping[str, str],
    event_time: str,
    raw_payload_hash: str,
) -> Dict[str, Any]:
    if target is None or target.target_action is not TargetAction.SET_TARGET:
        return {
            "policy_version": _FILL_POLICY_VERSION,
            "status": "NO_TRADE_SIGNAL_FLAT",
            "side": None,
            "requested_quantity": "0",
            "rounded_quantity": "0",
            "price": None,
            "fee_value_usdt": "0",
            "exchange_event_time": event_time,
            "raw_payload_hash": raw_payload_hash,
        }
    ask = Decimal(bbo["ask_price"])
    ask_qty = Decimal(bbo["ask_quantity"])
    price = round_price_up(ask * (Decimal("1") + _SLIPPAGE), metadata.price_tick)
    requested = target.target_notional_usdt_or_null / price
    capped = min(requested, ask_qty, metadata.max_quantity)
    quantity = round_down_to_step(capped, metadata.quantity_step)
    notional = quantity * price
    common = {
        "policy_version": _FILL_POLICY_VERSION,
        "side": "BUY",
        "requested_quantity": canonical_decimal(requested),
        "rounded_quantity": canonical_decimal(quantity),
        "price": canonical_decimal(price),
        "fee_value_usdt": canonical_decimal(notional * _TAKER_FEE),
        "exchange_event_time": event_time,
        "raw_payload_hash": raw_payload_hash,
    }
    if quantity < metadata.min_quantity:
        return {**common, "status": "NO_FILL_BELOW_MIN_QUANTITY"}
    if notional < metadata.min_notional:
        return {**common, "status": "NO_FILL_BELOW_MIN_NOTIONAL"}
    status = (
        "PARTIALLY_FILLED_VISIBLE_LIQUIDITY"
        if min(ask_qty, metadata.max_quantity) < requested
        else "FILLED"
    )
    implementation_shortfall = (price - ask) * quantity
    return {
        **common,
        "status": status,
        "notional_usdt": canonical_decimal(notional),
        "implementation_shortfall_usdt": canonical_decimal(implementation_shortfall),
    }


def _event(
    *,
    run_id: str,
    arm: str,
    event_id: str,
    event_time: str,
    payload: Dict[str, Any],
) -> EventEnvelope:
    parsed, _ = _utc(event_time)
    return EventEnvelope.create(
        schema_version="1.1.0",
        event_id=event_id,
        trace_id=stable_id("trace", {"run_id": run_id, "arm": arm}),
        correlation_id=stable_id("corr", {"run_id": run_id, "arm": arm}),
        causation_id=None,
        run_id=run_id,
        event_time=parsed,
        available_at=parsed,
        ingested_at=parsed,
        recorded_at=parsed,
        source="OFFLINE_PAPER_SIMULATOR",
        payload=payload,
    )


def _economic_scope(arm: str) -> Dict[str, str]:
    baseline = arm == "baseline"
    evaluation_ledger = "BASELINE_LEDGER" if baseline else "AI_LEDGER"
    release_route = "BASELINE_ONLY" if baseline else "AI_ENHANCED"
    recipe = {
        "strategy_version": _BASELINE_VERSION,
        "arm": arm,
        "starting_equity_usdt": "1000",
    }
    line = {
        "evaluation_ledger": evaluation_ledger,
        "release_route": release_route,
        "stage": "OFFLINE_PAPER",
    }
    return {
        "evaluation_ledger": evaluation_ledger,
        "release_route": release_route,
        "direction": "LONG",
        "venue": "BINANCE_SPOT",
        "recipe_release_id": "offline-paper-recipe-" + arm,
        "recipe_release_hash": business_hash(recipe),
        "deployment_line_id": "offline-paper-line-" + arm,
        "deployment_line_hash": business_hash(line),
    }


def _equity_payload(
    *,
    account_id: str,
    scope: Mapping[str, str],
    snapshot_id: str,
    as_of: str,
    marked: Decimal,
    liquidation: Decimal,
    spot_notional: Decimal,
    exit_fee: Decimal,
    positions: Sequence[Mapping[str, Any]],
    is_day_start: bool,
    source_hash: str,
) -> Dict[str, Any]:
    return {
        "equity_snapshot_id": snapshot_id,
        "account_id": account_id,
        **scope,
        "marked_equity_usdt": marked,
        "liquidation_equity_usdt": liquidation,
        "spot_notional_usdt": spot_notional,
        "perp_notional_usdt": Decimal("0"),
        "active_order_risk_increasing_notional_usdt": Decimal("0"),
        "active_order_unknown_notional_usdt": Decimal("0"),
        "expected_exit_fee_accrued_usdt": exit_fee,
        "conservative_close_verified": True,
        "is_utc_day_start": is_day_start,
        "position_cost_bases": list(positions),
        "as_of": as_of,
        "source_snapshot_hash": source_hash,
    }


def _economic_arm(
    *,
    run_id: str,
    arm: str,
    fill: Mapping[str, Any],
    bbo: Mapping[str, str],
    metadata: InstrumentMetadata,
    market_hash: str,
    window_start: str,
    window_end: str,
    generated_at: str,
) -> Dict[str, Any]:
    scope = _economic_scope(arm)
    account_id = "paper-baseline" if arm == "baseline" else "paper-ai"
    policy_hash = business_hash(
        {
            "policy": "EXACT_DECIMAL_CONSERVATIVE_LIQUIDATION_V1",
            "fill_policy": _FILL_POLICY_VERSION,
        }
    )
    allocation_hash = business_hash({"policy": "NO_ALLOCATED_COSTS_SMOKE_V1"})
    with tempfile.TemporaryDirectory(prefix="offline-paper-ledger-") as directory:
        with EventLedger(Path(directory) / f"{arm}.sqlite") as ledger:
            start_payload = _equity_payload(
                account_id=account_id,
                scope=scope,
                snapshot_id=stable_id("equity", {"run": run_id, "arm": arm, "point": "start"}),
                as_of=window_start,
                marked=_STARTING_EQUITY,
                liquidation=_STARTING_EQUITY,
                spot_notional=Decimal("0"),
                exit_fee=Decimal("0"),
                positions=(),
                is_day_start=True,
                source_hash=market_hash,
            )
            ledger.append(
                "EquitySnapshotRecorded",
                _event(
                    run_id=run_id,
                    arm=arm,
                    event_id=stable_id("event", {"run": run_id, "arm": arm, "point": "start"}),
                    event_time=window_start,
                    payload=start_payload,
                ),
                start_payload,
            )
            positions = []
            marked = _STARTING_EQUITY
            liquidation = _STARTING_EQUITY
            spot_notional = Decimal("0")
            exit_fee = Decimal("0")
            if fill.get("status") in ("FILLED", "PARTIALLY_FILLED_VISIBLE_LIQUIDITY"):
                quantity = Decimal(fill["rounded_quantity"])
                price = Decimal(fill["price"])
                fee = Decimal(fill["fee_value_usdt"])
                notional = quantity * price
                fill_payload = {
                    "fill_id": stable_id("fill", {"run": run_id, "arm": arm}),
                    "account_id": account_id,
                    "market_scope": "BINANCE:SPOT",
                    "exchange_trade_id": stable_id("simtrade", {"run": run_id, "arm": arm}),
                    "local_order_id": stable_id("simorder", {"run": run_id, "arm": arm}),
                    "venue_order_id": stable_id("simvenue", {"run": run_id, "arm": arm}),
                    "instrument_id": metadata.instrument_id,
                    "side": "BUY",
                    "quantity": quantity,
                    "price": price,
                    "contract_multiplier": Decimal("1"),
                    "decision_reference_price": Decimal(bbo["ask_price"]),
                    "liquidity_role": "TAKER",
                    "fee_amount": fee,
                    "fee_asset": "USDT",
                    "fee_value_usdt": fee,
                    "fee_fx_rate_id_or_null": None,
                    "implementation_shortfall_usdt": Decimal(
                        fill["implementation_shortfall_usdt"]
                    ),
                    "exchange_event_time": fill["exchange_event_time"],
                    "raw_payload_hash": fill["raw_payload_hash"],
                    **scope,
                }
                ledger.append(
                    "FillRecorded",
                    _event(
                        run_id=run_id,
                        arm=arm,
                        event_id=stable_id("event", {"run": run_id, "arm": arm, "point": "fill"}),
                        event_time=fill["exchange_event_time"],
                        payload=fill_payload,
                    ),
                    fill_payload,
                )
                cash = _STARTING_EQUITY - notional - fee
                bid = Decimal(bbo["bid_price"])
                exit_price = round_price_down(
                    bid * (Decimal("1") - _SLIPPAGE), metadata.price_tick
                )
                close_notional = quantity * exit_price
                exit_fee = close_notional * _TAKER_FEE
                marked = cash + quantity * bid
                liquidation = cash + close_notional - exit_fee
                spot_notional = close_notional
                positions = [
                    {
                        "instrument_id": metadata.instrument_id,
                        "signed_quantity": quantity,
                        "moving_average_entry_price": price,
                        "contract_multiplier": Decimal("1"),
                    }
                ]
            end_payload = _equity_payload(
                account_id=account_id,
                scope=scope,
                snapshot_id=stable_id("equity", {"run": run_id, "arm": arm, "point": "end"}),
                as_of=window_end,
                marked=marked,
                liquidation=liquidation,
                spot_notional=spot_notional,
                exit_fee=exit_fee,
                positions=positions,
                is_day_start=False,
                source_hash=market_hash,
            )
            ledger.append(
                "EquitySnapshotRecorded",
                _event(
                    run_id=run_id,
                    arm=arm,
                    event_id=stable_id("event", {"run": run_id, "arm": arm, "point": "end"}),
                    event_time=window_end,
                    payload=end_payload,
                ),
                end_payload,
            )
            snapshot = ledger.economic_ledger_snapshot(
                snapshot_id=stable_id("economic", {"run": run_id, "arm": arm}),
                account_id=account_id,
                evaluation_ledger=scope["evaluation_ledger"],
                release_route=scope["release_route"],
                direction="LONG",
                venue="BINANCE_SPOT",
                recipe_release_id=scope["recipe_release_id"],
                recipe_release_hash=scope["recipe_release_hash"],
                deployment_line_id=scope["deployment_line_id"],
                deployment_line_hash=scope["deployment_line_hash"],
                evaluation_window_start=window_start,
                evaluation_window_end=window_end,
                accounting_policy_id="exact-decimal-conservative-liquidation-v1",
                accounting_policy_hash=policy_hash,
                cost_allocation_policy_id="no-allocated-costs-smoke-v1",
                cost_allocation_policy_hash=allocation_hash,
                generated_at=generated_at,
            )
    reasons = economic_snapshot_reasons(snapshot)
    if reasons:
        raise OfflinePaperError("PAPER_ECONOMIC_REPLAY_INVALID:" + ",".join(reasons))
    return snapshot


def _raw_body(capture: VerifiedOfflinePaperCapture, index: int) -> bytes:
    return capture.receipts[index]["response_body_utf8"].encode("utf-8")


def minimum_paper_run_recorded_at(
    capture: VerifiedOfflinePaperCapture,
    candidate: object,
) -> str:
    """Apply the deterministic +1ms run-end floor without sleeping."""

    if not isinstance(capture, VerifiedOfflinePaperCapture):
        raise OfflinePaperError("PAPER_CAPTURE_UNVERIFIED")
    candidate_dt, _ = _utc(candidate)
    run_end = max(
        _utc(capture.receipts[2]["response_received_at"])[0],
        _utc(capture.receipts[3]["response_received_at"])[0],
    ) + timedelta(milliseconds=1)
    return utc_datetime(max(candidate_dt, run_end))


def _build_offline_paper_run(
    capture: VerifiedOfflinePaperCapture,
    *,
    run_id: str,
    recorded_at: str,
) -> Dict[str, Any]:
    if not isinstance(run_id, str) or not run_id or len(run_id) > 128:
        raise OfflinePaperError("PAPER_RUN_ID_INVALID")
    decision_dt, decision_text = _utc(capture.decision_time)
    recorded_dt, recorded_text = _utc(recorded_at)
    run_end_dt = max(
        _utc(capture.receipts[2]["response_received_at"])[0],
        _utc(capture.receipts[3]["response_received_at"])[0],
    ) + timedelta(milliseconds=1)
    run_end_text = utc_datetime(run_end_dt)
    if recorded_dt < run_end_dt:
        raise OfflinePaperError("PAPER_CLOCK_INVALID")
    window_start = utc_datetime(
        decision_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    )
    klines = _parse_klines(_raw_body(capture, 0), decision_dt)
    metadata = _parse_exchange_info(_raw_body(capture, 1), decision_dt)
    metadata.assert_effective(decision_dt)
    bbo = _parse_bbo(_raw_body(capture, 2))
    agg_trades = _parse_agg_trades(_raw_body(capture, 3))
    market = {
        "symbol": capture.plan.symbol,
        "decision_time": decision_text,
        "closed_4h_klines": list(klines),
        "instrument_metadata": metadata.business_payload(),
        "instrument_metadata_hash": metadata.metadata_hash,
        "bbo": bbo,
        "agg_trade_window": agg_trades,
        "receipt_hashes": [item["receipt_hash"] for item in capture.receipts],
    }
    market_hash = business_hash(market)
    decision, target = build_baseline_paper_decision(
        klines,
        decision_dt,
        market_hash,
    )
    baseline_fill = _conservative_fill(
        target,
        metadata,
        bbo,
        capture.receipts[2]["response_received_at"],
        capture.receipts[2]["body_sha256"],
    )
    ai_fill = {
        "policy_version": _FILL_POLICY_VERSION,
        "status": "NOT_RUN_NO_APPROVED_MODEL",
        "side": None,
        "requested_quantity": "0",
        "rounded_quantity": "0",
        "price": None,
        "fee_value_usdt": "0",
        "exchange_event_time": capture.receipts[2]["response_received_at"],
        "raw_payload_hash": capture.receipts[2]["body_sha256"],
    }
    baseline_economics = _economic_arm(
        run_id=run_id,
        arm="baseline",
        fill=baseline_fill,
        bbo=bbo,
        metadata=metadata,
        market_hash=market_hash,
        window_start=window_start,
        window_end=run_end_text,
        generated_at=recorded_text,
    )
    ai_economics = _economic_arm(
        run_id=run_id,
        arm="ai",
        fill=ai_fill,
        bbo=bbo,
        metadata=metadata,
        market_hash=market_hash,
        window_start=window_start,
        window_end=run_end_text,
        generated_at=recorded_text,
    )
    run = {
        "$schema": "./offline-paper-run-v1.schema.json",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "run_hash": "0" * 64,
        "recorded_at": recorded_text,
        "plan": {
            "schema_version": capture.plan.schema_version,
            "provider": capture.plan.provider,
            "symbol": capture.plan.symbol,
            "requests": [
                {
                    "request_id": item.request_id,
                    "stage": item.stage,
                    "family": item.family,
                    "method": item.method,
                    "url": item.url,
                }
                for item in offline_paper_requests(capture.plan)
            ],
        },
        "decision_time": decision_text,
        "run_end": run_end_text,
        "receipts": [dict(item) for item in capture.receipts],
        "market": {**market, "market_hash": market_hash},
        "policies": {
            "baseline_strategy": _BASELINE_VERSION,
            "fill_policy": _FILL_POLICY_VERSION,
            "starting_virtual_equity_usdt": "1000",
            "volatility_target": "0.12",
            "risk_bucket": "0.25",
            "slippage_per_side": "0.001",
            "assumed_taker_fee_per_side": "0.0015",
        },
        "arms": {
            "baseline": {
                "arm_status": "RUN",
                "decision": decision,
                "fill": baseline_fill,
                "economic_snapshot": baseline_economics,
            },
            "ai": {
                "arm_status": "NOT_RUN_NO_APPROVED_MODEL",
                "decision": {
                    "decision_source": "NOT_RUN",
                    "eligible": False,
                    "ineligibility_reason_mask": ["NO_APPROVED_MODEL"],
                    "recommended_action": "FREEZE_INCREASES",
                    "model_id_or_null": None,
                    "model_version_or_null": None,
                },
                "fill": ai_fill,
                "economic_snapshot": ai_economics,
            },
        },
        "pairing": {
            "same_decision_time": True,
            "same_market_input": True,
            "baseline_market_hash": market_hash,
            "ai_market_hash": market_hash,
            "paired_statistical_eligibility": "INELIGIBLE_AI_NOT_RUN",
            "paired_observation_count": 0,
        },
        "security_boundary": {
            "public_get_only": True,
            "credentials_read": False,
            "account_endpoints_called": False,
            "broker_interface_present": False,
            "orders_submitted": False,
            "temporary_wal_ledgers_only": True,
        },
        "paper_eligibility": "OFFLINE_PAPER_SMOKE_ONLY",
        "profitability_eligibility": "INSUFFICIENT_DURATION_AND_AI",
        "warnings": list(OFFLINE_PAPER_WARNINGS),
    }
    run["run_hash"] = artifact_self_hash(run, "run_hash")
    if tuple(_run_validator().iter_errors(run)):
        raise OfflinePaperError("PAPER_RUN_SCHEMA_INVALID")
    return run


def build_offline_paper_run(
    capture: VerifiedOfflinePaperCapture,
    *,
    run_id: str,
    recorded_at: str,
) -> Dict[str, Any]:
    if not isinstance(capture, VerifiedOfflinePaperCapture):
        raise OfflinePaperError("PAPER_CAPTURE_UNVERIFIED")
    replayed = capture.replay_with_receipts(capture.receipts)
    return _build_offline_paper_run(
        replayed,
        run_id=run_id,
        recorded_at=recorded_at,
    )


def offline_paper_run_trust_hash(run: Mapping[str, Any]) -> str:
    try:
        return business_hash(
            {
                "attestation_type": _ATTESTATION_TYPE,
                "run_id": run["run_id"],
                "run_hash": run["run_hash"],
                "receipt_hashes": [
                    item["receipt_hash"] for item in run["receipts"]
                ],
                "baseline_economic_snapshot_hash": run["arms"]["baseline"][
                    "economic_snapshot"
                ]["snapshot_hash"],
                "ai_economic_snapshot_hash": run["arms"]["ai"][
                    "economic_snapshot"
                ]["snapshot_hash"],
            }
        )
    except (KeyError, TypeError):
        return ""


def offline_paper_run_reasons(
    run: Mapping[str, Any],
    trusted_attestation_hash: str,
) -> Tuple[str, ...]:
    reasons = []
    if not isinstance(run, Mapping):
        return ("PAPER_RUN_INVALID",)
    if tuple(_run_validator().iter_errors(run)):
        reasons.append("PAPER_RUN_SCHEMA_INVALID")
    try:
        if run.get("run_hash") != artifact_self_hash(run, "run_hash"):
            reasons.append("PAPER_RUN_SELF_HASH_MISMATCH")
    except Exception:
        reasons.append("PAPER_RUN_NOT_CANONICAL")
    if offline_paper_run_trust_hash(run) != trusted_attestation_hash:
        reasons.append("PAPER_TRUST_HASH_MISMATCH")
    for arm in ("baseline", "ai"):
        try:
            nested = economic_snapshot_reasons(
                run["arms"][arm]["economic_snapshot"]
            )
            reasons.extend(f"PAPER_{arm.upper()}_{item}" for item in nested)
        except (KeyError, TypeError):
            reasons.append(f"PAPER_{arm.upper()}_ECONOMIC_SNAPSHOT_INVALID")
    try:
        plan = OfflinePaperPlan.create(run["plan"]["symbol"])
        capture = _capture_from_receipts(plan, run["receipts"])
        rebuilt = _build_offline_paper_run(
            capture,
            run_id=run["run_id"],
            recorded_at=run["recorded_at"],
        )
        if rebuilt["run_hash"] != run.get("run_hash"):
            reasons.append("PAPER_RUN_REPLAY_MISMATCH")
    except (KeyError, OfflinePaperError, TypeError, ValueError):
        reasons.append("PAPER_RUN_REPLAY_INVALID")
    return tuple(sorted(set(reasons)))
