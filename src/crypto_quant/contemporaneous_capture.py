"""Fail-closed contemporaneous capture of public Binance Spot observations."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Context, Decimal, InvalidOperation, localcontext
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlencode, urlparse

from .canonical import business_hash, canonical_decimal
from .evidence import artifact_self_hash


_BASE_URL = "https://data-api.binance.vision"
_HOST = "data-api.binance.vision"
_ALLOWED_SYMBOLS = frozenset(("ETHUSDT", "BTCUSDT"))
_PARSER_VERSION = "BINANCE_SPOT_REST_CAPTURE_V1"
_MAX_BODY_BYTES = 2 * 1024 * 1024
_DECIMAL_CONTEXT = Context(prec=50)
_PLAN_TOKEN = object()
_BATCH_TOKEN = object()
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_INTERVAL_MS = {"1m": 60_000, "4h": 14_400_000}
_ATTESTATION_TYPE = "CONTEMPORANEOUS_CAPTURE_SNAPSHOT_ATTESTATION"


class CaptureError(ValueError):
    """A capture request or observation violates a stable boundary."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> Tuple[datetime, str]:
    if not isinstance(value, str):
        raise CaptureError("CAPTURE_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CaptureError("CAPTURE_TIME_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CaptureError("CAPTURE_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    milliseconds = converted.microsecond // 1000
    converted = converted.replace(microsecond=milliseconds * 1000)
    rendered = converted.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return converted, rendered


def _milliseconds(value: object) -> Tuple[datetime, str]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CaptureError("CAPTURE_SOURCE_TIME_INVALID")
    try:
        parsed = datetime.fromtimestamp(value / 1000, timezone.utc)
    except (OverflowError, OSError, ValueError) as error:
        raise CaptureError("CAPTURE_SOURCE_TIME_INVALID") from error
    return _utc(parsed.isoformat())


def _decimal(value: object, *, positive: bool = False) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise CaptureError("CAPTURE_DECIMAL_INVALID")
    try:
        with localcontext(_DECIMAL_CONTEXT):
            number = Decimal(value)
    except InvalidOperation as error:
        raise CaptureError("CAPTURE_DECIMAL_INVALID") from error
    if not number.is_finite() or (positive and number <= 0):
        raise CaptureError("CAPTURE_DECIMAL_INVALID")
    try:
        return canonical_decimal(number)
    except ValueError as error:
        raise CaptureError("CAPTURE_DECIMAL_INVALID") from error


def _strict_json(body: bytes) -> Any:
    if not isinstance(body, bytes) or len(body) > _MAX_BODY_BYTES:
        raise CaptureError("CAPTURE_RESPONSE_TOO_LARGE")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CaptureError("CAPTURE_JSON_DUPLICATE_KEY")
            result[key] = value
        return result

    def reject_float(_value):
        raise CaptureError("CAPTURE_JSON_FLOAT_FORBIDDEN")

    try:
        return json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_float,
            parse_constant=reject_float,
        )
    except CaptureError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaptureError("CAPTURE_JSON_INVALID") from error


@dataclass(frozen=True, init=False)
class ContemporaneousCapturePlan:
    schema_version: str
    provider: str
    symbol: str
    families: Tuple[str, ...]
    kline_intervals: Tuple[str, ...]

    def __init__(self, *args, **kwargs):
        token = kwargs.pop("_token", None)
        if token is not _PLAN_TOKEN:
            raise TypeError("ContemporaneousCapturePlan must be created with create")
        object.__setattr__(self, "schema_version", "1.0.0")
        object.__setattr__(self, "provider", "BINANCE_MARKET_DATA_ONLY")
        object.__setattr__(self, "symbol", kwargs["symbol"])
        object.__setattr__(
            self,
            "families",
            ("SPOT_KLINE", "SPOT_AGG_TRADE", "SPOT_BBO"),
        )
        object.__setattr__(self, "kline_intervals", ("1m", "4h"))

    @classmethod
    def create(cls, symbol: str) -> "ContemporaneousCapturePlan":
        if symbol not in _ALLOWED_SYMBOLS:
            raise CaptureError("CAPTURE_PLAN_INVALID")
        return cls(symbol=symbol, _token=_PLAN_TOKEN)


@dataclass(frozen=True)
class CaptureRequest:
    request_id: str
    family: str
    symbol: str
    interval_or_null: Optional[str]
    url: str


@dataclass(frozen=True)
class PublicCaptureHttpResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes
    request_started_at: str
    response_received_at: str


@dataclass(frozen=True, init=False)
class VerifiedCaptureBatch:
    plan: ContemporaneousCapturePlan
    receipts: Tuple[Mapping[str, Any], ...]
    observations: Tuple[Mapping[str, Any], ...]

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _BATCH_TOKEN:
            raise TypeError("VerifiedCaptureBatch is issued only by capture_once")
        object.__setattr__(self, "plan", kwargs["plan"])
        object.__setattr__(self, "receipts", tuple(kwargs["receipts"]))
        object.__setattr__(self, "observations", tuple(kwargs["observations"]))


def _plan_payload(plan: ContemporaneousCapturePlan) -> Dict[str, Any]:
    return {
        "schema_version": plan.schema_version,
        "provider": plan.provider,
        "symbol": plan.symbol,
        "families": list(plan.families),
        "kline_intervals": list(plan.kline_intervals),
        "kline_limit": 2,
        "agg_trade_limit": 100,
    }


def _request(family: str, symbol: str, interval: Optional[str], path: str, query):
    url = _BASE_URL + path + "?" + urlencode(sorted(query.items()))
    identity = {
        "family": family,
        "symbol": symbol,
        "interval_or_null": interval,
        "url": url,
    }
    return CaptureRequest(
        request_id="capreq_" + business_hash(identity),
        family=family,
        symbol=symbol,
        interval_or_null=interval,
        url=url,
    )


def capture_requests(plan: ContemporaneousCapturePlan) -> Tuple[CaptureRequest, ...]:
    if not isinstance(plan, ContemporaneousCapturePlan):
        raise CaptureError("CAPTURE_PLAN_INVALID")
    symbol = plan.symbol
    return (
        _request(
            "SPOT_KLINE",
            symbol,
            "1m",
            "/api/v3/klines",
            {"symbol": symbol, "interval": "1m", "limit": 2},
        ),
        _request(
            "SPOT_KLINE",
            symbol,
            "4h",
            "/api/v3/klines",
            {"symbol": symbol, "interval": "4h", "limit": 2},
        ),
        _request(
            "SPOT_AGG_TRADE",
            symbol,
            None,
            "/api/v3/aggTrades",
            {"symbol": symbol, "limit": 100},
        ),
        _request(
            "SPOT_BBO",
            symbol,
            None,
            "/api/v3/ticker/bookTicker",
            {"symbol": symbol},
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


def _headers(headers: object) -> Dict[str, Optional[str]]:
    if not isinstance(headers, Mapping):
        raise CaptureError("CAPTURE_RESPONSE_INVALID")
    lowered = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise CaptureError("CAPTURE_RESPONSE_INVALID")
        lowered[key.lower()] = value
    return {
        "http_date_or_null": lowered.get("date"),
        "etag_or_null": lowered.get("etag"),
        "last_modified_or_null": lowered.get("last-modified"),
        "retry_after_or_null": lowered.get("retry-after"),
    }


def _receipt(request: CaptureRequest, response: PublicCaptureHttpResponse):
    if (
        not isinstance(response, PublicCaptureHttpResponse)
        or response.status != 200
        or response.final_url != request.url
        or not _valid_public_url(response.final_url)
        or not isinstance(response.body, bytes)
        or len(response.body) > _MAX_BODY_BYTES
    ):
        raise CaptureError("CAPTURE_RESPONSE_INVALID")
    started, started_text = _utc(response.request_started_at)
    received, received_text = _utc(response.response_received_at)
    if received < started:
        raise CaptureError("CAPTURE_CLOCK_INVALID")
    receipt = {
        "request_id": request.request_id,
        "family": request.family,
        "symbol": request.symbol,
        "interval_or_null": request.interval_or_null,
        "url": request.url,
        "request_started_at": started_text,
        "response_received_at": received_text,
        "status": response.status,
        "final_url": response.final_url,
        **_headers(response.headers),
        "body_size_bytes": len(response.body),
        "body_sha256": hashlib.sha256(response.body).hexdigest(),
    }
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    return receipt


def _source_hash(source: object) -> str:
    return business_hash(source)


def _observation(
    *,
    request: CaptureRequest,
    receipt: Mapping[str, Any],
    source_index: int,
    source_payload: Any,
    event_time: str,
    event_time_basis: str,
    business_key: Mapping[str, Any],
    payload: Mapping[str, Any],
    ingested_at: str,
    recorded_at: str,
) -> Dict[str, Any]:
    observation = {
        "observation_id": "cmo_" + business_hash(
            {
                "request_id": request.request_id,
                "receipt_hash": receipt["receipt_hash"],
                "source_index": source_index,
                "business_key": business_key,
            }
        ),
        "fact_type": request.family,
        "symbol": request.symbol,
        "interval_or_null": request.interval_or_null,
        "business_key": dict(business_key),
        "event_time": event_time,
        "event_time_basis": event_time_basis,
        "available_at": receipt["response_received_at"],
        "ingested_at": ingested_at,
        "recorded_at": recorded_at,
        "response_receipt_hash": receipt["receipt_hash"],
        "source_index": source_index,
        "source_payload": source_payload,
        "source_payload_hash": _source_hash(source_payload),
        "payload": dict(payload),
        "payload_hash": business_hash(payload),
        "revision_no": 0,
        "previous_observation_hash": None,
    }
    observation["observation_hash"] = artifact_self_hash(
        observation, "observation_hash"
    )
    return observation


def _parse_kline(
    request: CaptureRequest,
    receipt: Mapping[str, Any],
    payload: object,
    ingested_at: str,
    recorded_at: str,
) -> Tuple[Dict[str, Any], ...]:
    if not isinstance(payload, list) or not payload or len(payload) > 2:
        raise CaptureError("CAPTURE_KLINE_INVALID")
    results = []
    expected_duration = _INTERVAL_MS[request.interval_or_null]
    available_dt, _ = _utc(receipt["response_received_at"])
    for index, row in enumerate(payload):
        if (
            not isinstance(row, list)
            or len(row) != 12
            or isinstance(row[8], bool)
            or not isinstance(row[8], int)
            or row[8] < 0
            or row[11] != "0"
        ):
            raise CaptureError("CAPTURE_KLINE_INVALID")
        open_dt, open_time = _milliseconds(row[0])
        close_dt, close_time = _milliseconds(row[6])
        if row[6] - row[0] + 1 != expected_duration:
            raise CaptureError("CAPTURE_KLINE_INVALID")
        values = [_decimal(row[item], positive=True) for item in (1, 2, 3, 4)]
        opening, high, low, close = map(Decimal, values)
        if low > opening or low > close or high < opening or high < close or low > high:
            raise CaptureError("CAPTURE_KLINE_INVALID")
        volume = _decimal(row[5])
        quote_volume = _decimal(row[7])
        taker_base = _decimal(row[9])
        taker_quote = _decimal(row[10])
        if any(Decimal(item) < 0 for item in (
            volume, quote_volume, taker_base, taker_quote
        )):
            raise CaptureError("CAPTURE_KLINE_INVALID")
        normalized = {
            "open_time": open_time,
            "close_time": close_time,
            "open": values[0],
            "high": values[1],
            "low": values[2],
            "close": values[3],
            "volume": volume,
            "quote_asset_volume": quote_volume,
            "trade_count": row[8],
            "taker_buy_base_volume": taker_base,
            "taker_buy_quote_volume": taker_quote,
            "is_closed": available_dt > close_dt,
        }
        results.append(
            _observation(
                request=request,
                receipt=receipt,
                source_index=index,
                source_payload=list(row),
                event_time=open_time,
                event_time_basis="SOURCE_OPEN_TIME",
                business_key={
                    "symbol": request.symbol,
                    "interval": request.interval_or_null,
                    "open_time": open_time,
                },
                payload=normalized,
                ingested_at=ingested_at,
                recorded_at=recorded_at,
            )
        )
    return tuple(results)


def _parse_agg_trades(
    request: CaptureRequest,
    receipt: Mapping[str, Any],
    payload: object,
    ingested_at: str,
    recorded_at: str,
) -> Tuple[Dict[str, Any], ...]:
    if not isinstance(payload, list) or not payload or len(payload) > 100:
        raise CaptureError("CAPTURE_AGG_TRADE_INVALID")
    results = []
    for index, row in enumerate(payload):
        if not isinstance(row, Mapping) or set(row) != {
            "a", "p", "q", "f", "l", "T", "m", "M"
        }:
            raise CaptureError("CAPTURE_AGG_TRADE_INVALID")
        integers = (row["a"], row["f"], row["l"], row["T"])
        if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in integers):
            raise CaptureError("CAPTURE_AGG_TRADE_INVALID")
        if row["f"] > row["l"] or not isinstance(row["m"], bool) or not isinstance(row["M"], bool):
            raise CaptureError("CAPTURE_AGG_TRADE_INVALID")
        _, event_time = _milliseconds(row["T"])
        normalized = {
            "aggregate_trade_id": row["a"],
            "price": _decimal(row["p"], positive=True),
            "quantity": _decimal(row["q"], positive=True),
            "first_trade_id": row["f"],
            "last_trade_id": row["l"],
            "trade_time": event_time,
            "buyer_is_maker": row["m"],
            "best_price_match": row["M"],
        }
        results.append(
            _observation(
                request=request,
                receipt=receipt,
                source_index=index,
                source_payload=dict(row),
                event_time=event_time,
                event_time_basis="SOURCE_TRADE_TIME",
                business_key={
                    "symbol": request.symbol,
                    "aggregate_trade_id": row["a"],
                },
                payload=normalized,
                ingested_at=ingested_at,
                recorded_at=recorded_at,
            )
        )
    return tuple(results)


def _parse_bbo(
    request: CaptureRequest,
    receipt: Mapping[str, Any],
    payload: object,
    ingested_at: str,
    recorded_at: str,
) -> Tuple[Dict[str, Any], ...]:
    if not isinstance(payload, Mapping) or set(payload) != {
        "symbol", "bidPrice", "bidQty", "askPrice", "askQty"
    } or payload["symbol"] != request.symbol:
        raise CaptureError("CAPTURE_BBO_INVALID")
    bid = _decimal(payload["bidPrice"], positive=True)
    ask = _decimal(payload["askPrice"], positive=True)
    if Decimal(bid) > Decimal(ask):
        raise CaptureError("CAPTURE_BBO_INVALID")
    normalized = {
        "bid_price": bid,
        "bid_quantity": _decimal(payload["bidQty"]),
        "ask_price": ask,
        "ask_quantity": _decimal(payload["askQty"]),
    }
    if Decimal(normalized["bid_quantity"]) < 0 or Decimal(normalized["ask_quantity"]) < 0:
        raise CaptureError("CAPTURE_BBO_INVALID")
    available_at = receipt["response_received_at"]
    return (
        _observation(
            request=request,
            receipt=receipt,
            source_index=0,
            source_payload=dict(payload),
            event_time=available_at,
            event_time_basis="CLIENT_RECEIVE_TIME_PROXY",
            business_key={
                "symbol": request.symbol,
                "response_receipt_hash": receipt["receipt_hash"],
            },
            payload=normalized,
            ingested_at=ingested_at,
            recorded_at=recorded_at,
        ),
    )


def _parse(
    request: CaptureRequest,
    receipt: Mapping[str, Any],
    body: bytes,
    ingested_at: str,
    recorded_at: str,
) -> Tuple[Dict[str, Any], ...]:
    payload = _strict_json(body)
    parser = {
        "SPOT_KLINE": _parse_kline,
        "SPOT_AGG_TRADE": _parse_agg_trades,
        "SPOT_BBO": _parse_bbo,
    }[request.family]
    return parser(request, receipt, payload, ingested_at, recorded_at)


def capture_once(
    plan: ContemporaneousCapturePlan,
    transport: object,
    *,
    recorded_at: str,
) -> VerifiedCaptureBatch:
    recorded_dt, recorded_text = _utc(recorded_at)
    receipts = []
    observations = []
    for request in capture_requests(plan):
        try:
            response = transport.get(request)
        except CaptureError:
            raise
        except Exception as error:
            raise CaptureError("CAPTURE_TRANSPORT_FAILURE") from error
        receipt = _receipt(request, response)
        received_dt, _ = _utc(receipt["response_received_at"])
        if recorded_dt < received_dt:
            raise CaptureError("CAPTURE_CLOCK_INVALID")
        receipts.append(receipt)
        observations.extend(
            _parse(request, receipt, response.body, recorded_text, recorded_text)
        )
    return VerifiedCaptureBatch(
        plan=plan,
        receipts=receipts,
        observations=observations,
        _token=_BATCH_TOKEN,
    )


def _key(item: Mapping[str, Any]) -> str:
    return business_hash(item["business_key"])


def _canonicalize_observations(observations: Sequence[Mapping[str, Any]]):
    ordered = sorted(
        (dict(item) for item in observations),
        key=lambda item: (
            item["available_at"],
            item["fact_type"],
            item["interval_or_null"] or "",
            _key(item),
            item["source_index"],
        ),
    )
    canonical = []
    kline_by_key = {}
    agg_by_key = {}
    bbo_by_payload = {}
    counters = {
        "kline_revision_count": 0,
        "kline_duplicate_count": 0,
        "closed_kline_mutation_count": 0,
        "agg_trade_duplicate_count": 0,
        "agg_trade_conflict_count": 0,
        "bbo_duplicate_count": 0,
    }
    for item in ordered:
        family = item["fact_type"]
        if family == "SPOT_KLINE":
            key = _key(item)
            prior = kline_by_key.get(key)
            if prior is not None:
                if item["payload_hash"] == prior["payload_hash"]:
                    counters["kline_duplicate_count"] += 1
                    continue
                if prior["payload"]["is_closed"]:
                    counters["closed_kline_mutation_count"] += 1
                    raise CaptureError("CLOSED_KLINE_MUTATION")
                item["revision_no"] = prior["revision_no"] + 1
                item["previous_observation_hash"] = prior["observation_hash"]
                item["observation_hash"] = artifact_self_hash(
                    item, "observation_hash"
                )
                counters["kline_revision_count"] += 1
            kline_by_key[key] = item
            canonical.append(item)
        elif family == "SPOT_AGG_TRADE":
            key = _key(item)
            prior = agg_by_key.get(key)
            if prior is not None:
                if item["payload_hash"] == prior["payload_hash"]:
                    counters["agg_trade_duplicate_count"] += 1
                    continue
                counters["agg_trade_conflict_count"] += 1
                raise CaptureError("AGG_TRADE_ID_CONFLICT")
            agg_by_key[key] = item
            canonical.append(item)
        else:
            key = item["payload_hash"]
            if key in bbo_by_payload:
                counters["bbo_duplicate_count"] += 1
                continue
            bbo_by_payload[key] = item
            canonical.append(item)
    return canonical, counters


def _quality_report(
    receipts: Sequence[Mapping[str, Any]],
    raw_observations: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
    counters: Mapping[str, int],
):
    families = sorted(set(item["fact_type"] for item in raw_observations))
    required = {"SPOT_KLINE", "SPOT_AGG_TRADE", "SPOT_BBO"}
    if set(families) != required:
        raise CaptureError("CAPTURE_FAMILY_COVERAGE_INCOMPLETE")
    agg_ids = sorted(
        item["payload"]["aggregate_trade_id"]
        for item in observations
        if item["fact_type"] == "SPOT_AGG_TRADE"
    )
    gaps = sum(max(0, right - left - 1) for left, right in zip(agg_ids, agg_ids[1:]))
    latencies = []
    for receipt in receipts:
        start, _ = _utc(receipt["request_started_at"])
        end, _ = _utc(receipt["response_received_at"])
        latencies.append(int((end - start).total_seconds() * 1000))
    event_times = [item["event_time"] for item in observations]
    receive_times = [item["available_at"] for item in raw_observations]
    report = {
        "response_count": len(receipts),
        "raw_observation_count": len(raw_observations),
        "canonical_observation_count": len(observations),
        "family_coverage": families,
        "first_event_time": min(event_times),
        "last_event_time": max(event_times),
        "first_receive_time": min(receive_times),
        "last_receive_time": max(receive_times),
        **dict(counters),
        "agg_trade_gap_count": gaps,
        "max_response_latency_ms": max(latencies),
        "warnings": [
            "ACCOUNT_COSTS_AND_FILLS_NOT_CAPTURED",
            "BBO_SEQUENCE_UNOBSERVABLE_REST_SNAPSHOT",
            "CAPTURE_DURATION_BELOW_PAPER_MINIMUM",
            "PERPETUAL_CONTEXT_NOT_CAPTURED",
        ],
        "blocking_findings": [],
    }
    report["report_hash"] = artifact_self_hash(report, "report_hash")
    return report


def build_capture_session(
    batches: Sequence[VerifiedCaptureBatch],
    *,
    session_id: str,
    recorded_at: str,
) -> Dict[str, Any]:
    if (
        not isinstance(batches, Sequence)
        or not batches
        or not isinstance(session_id, str)
        or _ID.fullmatch(session_id) is None
        or any(not isinstance(batch, VerifiedCaptureBatch) for batch in batches)
    ):
        raise CaptureError("CAPTURE_SESSION_INVALID")
    plans = {_plan_payload(batch.plan)["symbol"] for batch in batches}
    if len(plans) != 1:
        raise CaptureError("CAPTURE_SESSION_INVALID")
    recorded_dt, recorded_text = _utc(recorded_at)
    receipts = [dict(item) for batch in batches for item in batch.receipts]
    raw = [dict(item) for batch in batches for item in batch.observations]
    if any(_utc(item["recorded_at"])[0] > recorded_dt for item in raw):
        raise CaptureError("CAPTURE_CLOCK_INVALID")
    receipts.sort(key=lambda item: (
        item["request_started_at"], item["request_id"], item["receipt_hash"]
    ))
    observations, counters = _canonicalize_observations(raw)
    report = _quality_report(receipts, raw, observations, counters)
    snapshot = {
        "$schema": "./contemporaneous-capture-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "parser_version": _PARSER_VERSION,
        "session_id": session_id,
        "plan": _plan_payload(batches[0].plan),
        "session_started_at": min(item["request_started_at"] for item in receipts),
        "session_ended_at": max(item["response_received_at"] for item in receipts),
        "recorded_at": recorded_text,
        "response_count": len(receipts),
        "raw_observation_count": len(raw),
        "canonical_observation_count": len(observations),
        "response_receipts": receipts,
        "response_receipts_root_hash": business_hash(receipts),
        "observations": observations,
        "observations_root_hash": business_hash(observations),
        "quality_report": report,
        "pit_eligibility": "CONTEMPORANEOUS_RESEARCH_ONLY",
        "paper_eligibility": "CAPTURE_REPLAY_ONLY",
    }
    snapshot["snapshot_hash"] = capture_snapshot_hash(snapshot)
    return snapshot


def capture_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    return artifact_self_hash(snapshot, "snapshot_hash")


def capture_snapshot_attestation_envelope(
    snapshot: Mapping[str, Any],
) -> Dict[str, Any]:
    try:
        envelope = {
            "attestation_schema_version": "1.0.0",
            "attestation_type": _ATTESTATION_TYPE,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "snapshot_schema": snapshot["$schema"],
            "snapshot_schema_version": snapshot["schema_version"],
            "parser_version": snapshot["parser_version"],
            "session_id": snapshot["session_id"],
            "recorded_at": snapshot["recorded_at"],
            "response_receipts_root_hash": snapshot["response_receipts_root_hash"],
            "observations_root_hash": snapshot["observations_root_hash"],
            "snapshot_hash": snapshot["snapshot_hash"],
        }
    except (KeyError, TypeError) as error:
        raise CaptureError("CAPTURE_ATTESTATION_INVALID") from error
    if (
        envelope["snapshot_schema"]
        != "./contemporaneous-capture-snapshot-v1.schema.json"
        or envelope["snapshot_schema_version"] != "1.0.0"
        or envelope["parser_version"] != _PARSER_VERSION
        or not isinstance(envelope["session_id"], str)
        or _ID.fullmatch(envelope["session_id"]) is None
        or any(
            not isinstance(envelope[field], str)
            or _SHA256.fullmatch(envelope[field]) is None
            for field in (
                "response_receipts_root_hash",
                "observations_root_hash",
                "snapshot_hash",
            )
        )
    ):
        raise CaptureError("CAPTURE_ATTESTATION_INVALID")
    _utc(envelope["recorded_at"])
    return envelope


def capture_snapshot_attestation_hash(snapshot: Mapping[str, Any]) -> str:
    return business_hash(capture_snapshot_attestation_envelope(snapshot))


def _observation_replay_valid(item: Mapping[str, Any]) -> bool:
    try:
        if item["source_payload_hash"] != business_hash(item["source_payload"]):
            return False
        if item["payload_hash"] != business_hash(item["payload"]):
            return False
        if item["observation_hash"] != artifact_self_hash(item, "observation_hash"):
            return False
        event, _ = _utc(item["event_time"])
        available, _ = _utc(item["available_at"])
        ingested, _ = _utc(item["ingested_at"])
        recorded, _ = _utc(item["recorded_at"])
        if not event <= available <= ingested <= recorded:
            return False
        family = item["fact_type"]
        source = item["source_payload"]
        payload = item["payload"]
        if family == "SPOT_KLINE":
            if item["event_time_basis"] != "SOURCE_OPEN_TIME":
                return False
            _, source_open = _milliseconds(source[0])
            if source_open != item["event_time"]:
                return False
            values = [_decimal(source[index], positive=True) for index in (1, 2, 3, 4)]
            if values != [payload[name] for name in ("open", "high", "low", "close")]:
                return False
        elif family == "SPOT_AGG_TRADE":
            if (
                item["event_time_basis"] != "SOURCE_TRADE_TIME"
                or payload["aggregate_trade_id"] != source["a"]
                or payload["price"] != _decimal(source["p"], positive=True)
                or payload["quantity"] != _decimal(source["q"], positive=True)
            ):
                return False
        elif family == "SPOT_BBO":
            if (
                item["event_time_basis"] != "CLIENT_RECEIVE_TIME_PROXY"
                or item["event_time"] != item["available_at"]
                or payload["bid_price"] != _decimal(source["bidPrice"], positive=True)
                or payload["ask_price"] != _decimal(source["askPrice"], positive=True)
            ):
                return False
        else:
            return False
        return True
    except (CaptureError, KeyError, TypeError, ValueError, IndexError):
        return False


def capture_snapshot_reasons(
    snapshot: Mapping[str, Any],
    *,
    trusted_snapshot_attestation_hashes: Optional[Sequence[str]] = None,
) -> Tuple[str, ...]:
    if not isinstance(snapshot, Mapping):
        return ("CAPTURE_SNAPSHOT_INVALID",)
    reasons = []
    if (
        snapshot.get("$schema")
        != "./contemporaneous-capture-snapshot-v1.schema.json"
        or snapshot.get("schema_version") != "1.0.0"
        or snapshot.get("parser_version") != _PARSER_VERSION
    ):
        reasons.append("CAPTURE_SCHEMA_INVALID")
    if (
        snapshot.get("pit_eligibility") != "CONTEMPORANEOUS_RESEARCH_ONLY"
        or snapshot.get("paper_eligibility") != "CAPTURE_REPLAY_ONLY"
    ):
        reasons.append("CAPTURE_ELIGIBILITY_INVALID")
    try:
        if snapshot["snapshot_hash"] != capture_snapshot_hash(snapshot):
            reasons.append("CAPTURE_SNAPSHOT_HASH_MISMATCH")
        receipts = snapshot["response_receipts"]
        observations = snapshot["observations"]
        report = snapshot["quality_report"]
        if snapshot["response_receipts_root_hash"] != business_hash(receipts):
            reasons.append("CAPTURE_RECEIPTS_ROOT_MISMATCH")
        if snapshot["observations_root_hash"] != business_hash(observations):
            reasons.append("CAPTURE_OBSERVATIONS_ROOT_MISMATCH")
        if any(
            receipt.get("receipt_hash")
            != artifact_self_hash(receipt, "receipt_hash")
            for receipt in receipts
        ):
            reasons.append("CAPTURE_RECEIPT_HASH_MISMATCH")
        if report.get("report_hash") != artifact_self_hash(report, "report_hash"):
            reasons.append("CAPTURE_QUALITY_HASH_MISMATCH")
        if any(not _observation_replay_valid(item) for item in observations):
            reasons.append("CAPTURE_OBSERVATION_REPLAY_MISMATCH")
        required_warnings = {
            "ACCOUNT_COSTS_AND_FILLS_NOT_CAPTURED",
            "BBO_SEQUENCE_UNOBSERVABLE_REST_SNAPSHOT",
            "CAPTURE_DURATION_BELOW_PAPER_MINIMUM",
            "PERPETUAL_CONTEXT_NOT_CAPTURED",
        }
        if not required_warnings.issubset(set(report["warnings"])):
            reasons.append("CAPTURE_QUALITY_POLICY_INVALID")
        attestation = capture_snapshot_attestation_hash(snapshot)
        if trusted_snapshot_attestation_hashes is None:
            reasons.append("TRUSTED_CAPTURE_ATTESTATION_REQUIRED")
        else:
            try:
                trusted = set(trusted_snapshot_attestation_hashes)
            except TypeError:
                trusted = set()
            if attestation not in trusted:
                reasons.append("TRUSTED_CAPTURE_ATTESTATION_MISMATCH")
    except (CaptureError, KeyError, TypeError, ValueError):
        reasons.append("CAPTURE_SNAPSHOT_INVALID")
    return tuple(dict.fromkeys(reasons))
