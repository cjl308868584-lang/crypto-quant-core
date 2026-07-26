"""Fail-closed boundary for Binance public historical archives."""

import csv
import hashlib
import hmac
import re
import stat
import zipfile
from io import BytesIO
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, InvalidOperation, localcontext
from pathlib import PurePosixPath
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .canonical import business_hash, canonical_decimal
from .evidence import artifact_self_hash


_ARCHIVE_BASE_URL = "https://data.binance.vision/data"
_ALLOWED_SYMBOLS = frozenset(("ETHUSDT", "BTCUSDT"))
_ALLOWED_INTERVALS = frozenset(("1m", "15m", "4h", "1d"))
_MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
_MAX_CSV_BYTES = 256 * 1024 * 1024
_MAX_CHECKSUM_BYTES = 4 * 1024
_MAX_COMPRESSION_RATIO = 100
_READ_CHUNK_BYTES = 64 * 1024
_REQUEST_CONSTRUCTION_TOKEN = object()
_VERIFIED_ARCHIVE_TOKEN = object()
_DECIMAL_CONTEXT = Context(prec=50)
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_FACT_ID = re.compile(r"^mdf_[a-f0-9]{64}$")
_KLINE_INTERVAL_MS = {"1m": 60_000, "15m": 900_000, "4h": 14_400_000, "1d": 86_400_000}
_SPOT_MICROSECOND_BOUNDARY = datetime(2025, 1, 1, tzinfo=timezone.utc)
_FAMILY_SPECS = {
    ("SPOT", "KLINES"): ("spot", "daily", "klines", True),
    ("SPOT", "AGG_TRADES"): ("spot", "daily", "aggTrades", False),
    ("USD_M", "MARK_PRICE_KLINES"): (
        "futures/um",
        "daily",
        "markPriceKlines",
        True,
    ),
    ("USD_M", "FUNDING_RATE"): (
        "futures/um",
        "monthly",
        "fundingRate",
        False,
    ),
}


class MarketDataError(ValueError):
    """A public archive request violates a stable safety boundary."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, init=False)
class HistoricalArchiveRequest:
    """An allowlisted, canonical public archive request."""

    schema_version: str
    provider: str
    market: str
    data_family: str
    symbol: str
    interval_or_null: Optional[str]
    period_kind: str
    period: str

    def __init__(self, *args, **kwargs):
        raise TypeError("HistoricalArchiveRequest must be created with create")

    @classmethod
    def create(
        cls,
        *,
        market: str,
        data_family: str,
        symbol: str,
        interval_or_null: Optional[str],
        period_kind: str,
        period: str,
    ) -> "HistoricalArchiveRequest":
        spec = _FAMILY_SPECS.get((market, data_family))
        if spec is None or symbol not in _ALLOWED_SYMBOLS:
            raise MarketDataError("REQUEST_INVALID")
        _, expected_kind, _, needs_interval = spec
        if period_kind != expected_kind.upper():
            raise MarketDataError("REQUEST_INVALID")
        if needs_interval:
            if interval_or_null not in _ALLOWED_INTERVALS:
                raise MarketDataError("REQUEST_INVALID")
        elif interval_or_null is not None:
            raise MarketDataError("REQUEST_INVALID")
        _validate_period(period, period_kind)
        return cls._from_validated(
            _REQUEST_CONSTRUCTION_TOKEN,
            market=market,
            data_family=data_family,
            symbol=symbol,
            interval_or_null=interval_or_null,
            period_kind=period_kind,
            period=period,
        )

    @classmethod
    def _from_validated(
        cls,
        token: object,
        *,
        market: str,
        data_family: str,
        symbol: str,
        interval_or_null: Optional[str],
        period_kind: str,
        period: str,
    ) -> "HistoricalArchiveRequest":
        if token is not _REQUEST_CONSTRUCTION_TOKEN:
            raise TypeError("HistoricalArchiveRequest must be created with create")
        request = object.__new__(cls)
        object.__setattr__(request, "schema_version", "1.0.0")
        object.__setattr__(request, "provider", "BINANCE_PUBLIC_DATA")
        object.__setattr__(request, "market", market)
        object.__setattr__(request, "data_family", data_family)
        object.__setattr__(request, "symbol", symbol)
        object.__setattr__(request, "interval_or_null", interval_or_null)
        object.__setattr__(request, "period_kind", period_kind)
        object.__setattr__(request, "period", period)
        return request

    @property
    def archive_filename(self) -> str:
        _, _, directory, needs_interval = _FAMILY_SPECS[
            (self.market, self.data_family)
        ]
        name_parts = [self.symbol]
        if needs_interval:
            name_parts.append(self.interval_or_null or "")
        else:
            name_parts.append(directory)
        name_parts.append(self.period)
        return "-".join(name_parts) + ".zip"

    @property
    def expected_csv_name(self) -> str:
        return self.archive_filename[:-4] + ".csv"

    @property
    def archive_url(self) -> str:
        root, period_kind, directory, needs_interval = _FAMILY_SPECS[
            (self.market, self.data_family)
        ]
        path = [root, period_kind, directory, self.symbol]
        if needs_interval:
            path.append(self.interval_or_null or "")
        path.append(self.archive_filename)
        return _ARCHIVE_BASE_URL + "/" + "/".join(path)

    @property
    def checksum_url(self) -> str:
        return self.archive_url + ".CHECKSUM"


def _validate_period(period: str, period_kind: str) -> None:
    if not isinstance(period, str):
        raise MarketDataError("REQUEST_INVALID")
    format_string = "%Y-%m-%d" if period_kind == "DAILY" else "%Y-%m"
    try:
        parsed = datetime.strptime(period, format_string)
    except ValueError as exc:
        raise MarketDataError("REQUEST_INVALID") from exc
    if parsed.strftime(format_string) != period:
        raise MarketDataError("REQUEST_INVALID")


@dataclass(frozen=True, init=False)
class _VerifiedArchive:
    """Opaque result proving one request's bytes passed checksum validation."""

    _request: HistoricalArchiveRequest
    _archive_bytes: bytes

    def __init__(self, *args, **kwargs):
        raise TypeError("verified archives are issued by checksum validation")

    @classmethod
    def _issue(
        cls,
        token: object,
        request: HistoricalArchiveRequest,
        archive_bytes: bytes,
    ) -> "_VerifiedArchive":
        if token is not _VERIFIED_ARCHIVE_TOKEN:
            raise TypeError("verified archives are issued by checksum validation")
        verified = object.__new__(cls)
        object.__setattr__(verified, "_request", request)
        object.__setattr__(verified, "_archive_bytes", archive_bytes)
        return verified


def verify_official_checksum(
    request: HistoricalArchiveRequest,
    archive_bytes: bytes,
    checksum_bytes: bytes,
) -> _VerifiedArchive:
    """Require the single official SHA-256 record to match the archive."""

    if len(checksum_bytes) > _MAX_CHECKSUM_BYTES:
        raise MarketDataError("CHECKSUM_TOO_LARGE")
    try:
        checksum_text = checksum_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise MarketDataError("CHECKSUM_MALFORMED") from exc
    match = re.fullmatch(
        r"([0-9A-Fa-f]{64})  ([^\r\n]+)\r?\n?",
        checksum_text,
    )
    if match is None:
        raise MarketDataError("CHECKSUM_MALFORMED")
    expected_digest, filename = match.groups()
    if filename != request.archive_filename:
        raise MarketDataError("CHECKSUM_FILENAME_MISMATCH")
    actual_digest = hashlib.sha256(archive_bytes).hexdigest()
    if not hmac.compare_digest(expected_digest.lower(), actual_digest.lower()):
        raise MarketDataError("CHECKSUM_DIGEST_MISMATCH")
    return _VerifiedArchive._issue(
        _VERIFIED_ARCHIVE_TOKEN,
        request,
        archive_bytes,
    )


def extract_expected_csv(
    request: HistoricalArchiveRequest,
    verified_archive: _VerifiedArchive,
) -> bytes:
    """Read one validated CSV member without extracting it to disk."""

    if (
        not isinstance(verified_archive, _VerifiedArchive)
        or verified_archive._request != request
    ):
        raise MarketDataError("ARCHIVE_UNVERIFIED")
    archive_bytes = verified_archive._archive_bytes
    if len(archive_bytes) > _MAX_ARCHIVE_BYTES:
        raise MarketDataError("ZIP_ARCHIVE_TOO_LARGE")
    try:
        archive = zipfile.ZipFile(BytesIO(archive_bytes))
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise MarketDataError("ZIP_MALFORMED") from exc
    with archive:
        try:
            members = archive.infolist()
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise MarketDataError("ZIP_MALFORMED") from exc
        if len(members) != 1:
            raise MarketDataError("ZIP_MEMBER_COUNT")
        member = members[0]
        _validate_zip_member(request, member)
        try:
            with archive.open(member) as source:
                chunks = []
                total = 0
                while True:
                    chunk = source.read(_READ_CHUNK_BYTES)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_CSV_BYTES:
                        raise MarketDataError("ZIP_MEMBER_ACTUAL_SIZE")
                    chunks.append(chunk)
        except MarketDataError:
            raise
        except (EOFError, OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
            raise MarketDataError("ZIP_MEMBER_READ") from exc
    return b"".join(chunks)


def _validate_zip_member(
    request: HistoricalArchiveRequest,
    member: zipfile.ZipInfo,
) -> None:
    member_path = PurePosixPath(member.filename)
    if (
        member.is_dir()
        or member_path.is_absolute()
        or ".." in member_path.parts
        or "\\" in member.filename
        or member.filename != request.expected_csv_name
    ):
        raise MarketDataError("ZIP_MEMBER_NAME")
    if member.flag_bits & 0x1:
        raise MarketDataError("ZIP_MEMBER_ENCRYPTED")
    if stat.S_ISLNK(member.external_attr >> 16):
        raise MarketDataError("ZIP_MEMBER_NAME")
    if member.compress_size > _MAX_ARCHIVE_BYTES:
        raise MarketDataError("ZIP_MEMBER_COMPRESSED_SIZE")
    if member.file_size > _MAX_CSV_BYTES:
        raise MarketDataError("ZIP_MEMBER_UNCOMPRESSED_SIZE")
    if member.file_size and member.compress_size == 0:
        raise MarketDataError("ZIP_COMPRESSION_RATIO")
    if (
        member.compress_size
        and member.file_size > member.compress_size * _MAX_COMPRESSION_RATIO
    ):
        raise MarketDataError("ZIP_COMPRESSION_RATIO")


_CSV_HEADERS = {
    "KLINES": (
        "open time", "open", "high", "low", "close", "volume", "close time",
        "quote asset volume", "number of trades", "taker buy base asset volume",
        "taker buy quote asset volume", "ignore",
    ),
    "AGG_TRADES": (
        "aggregate tradeId", "price", "quantity", "first tradeId", "last tradeId",
        "transact time", "is buyer maker", "is best match",
    ),
    "MARK_PRICE_KLINES": (
        "open time", "open", "high", "low", "close", "volume", "close time",
        "quote asset volume", "number of trades", "taker buy base asset volume",
        "taker buy quote asset volume", "ignore",
    ),
    "FUNDING_RATE": ("calc_time", "funding_interval_hours", "last_funding_rate"),
}


def _market_fact_error() -> MarketDataError:
    return MarketDataError("MARKET_FACT_INVALID")


def _utc_input(value: Any) -> Tuple[datetime, str]:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise _market_fact_error()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _market_fact_error() from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise _market_fact_error()
    return parsed, value


def _timestamp(value: str, *, unit: str) -> Tuple[datetime, str]:
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise _market_fact_error()
    try:
        raw = int(value)
        delta = timedelta(microseconds=raw) if unit == "us" else timedelta(milliseconds=raw)
        parsed = datetime(1970, 1, 1, tzinfo=timezone.utc) + delta
    except (OverflowError, ValueError) as exc:
        raise _market_fact_error() from exc
    if not 2017 <= parsed.year <= 2100:
        raise _market_fact_error()
    if parsed.microsecond % 1_000 == 0:
        rendered = parsed.isoformat(timespec="milliseconds")
    else:
        rendered = parsed.isoformat(timespec="microseconds")
    return parsed, rendered.replace("+00:00", "Z")


def _decimal(value: str, *, positive: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise _market_fact_error()
    try:
        with localcontext(_DECIMAL_CONTEXT):
            rendered = canonical_decimal(Decimal(value))
            number = Decimal(rendered)
    except (InvalidOperation, ValueError) as exc:
        raise _market_fact_error() from exc
    if positive and number <= 0:
        raise _market_fact_error()
    return rendered


def _integer(value: str, *, positive: bool = False) -> int:
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise _market_fact_error()
    result = int(value)
    if positive and result <= 0:
        raise _market_fact_error()
    return result


def _boolean(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise _market_fact_error()


def _request_period_contains(request: HistoricalArchiveRequest, event_time: datetime) -> bool:
    if request.period_kind == "DAILY":
        return event_time.strftime("%Y-%m-%d") == request.period
    return event_time.strftime("%Y-%m") == request.period


def _spot_timestamp(value: str) -> Tuple[datetime, str, str]:
    unit = "us" if int(value) >= 1_000_000_000_000_000 else "ms"
    parsed, rendered = _timestamp(value, unit=unit)
    if (parsed >= _SPOT_MICROSECOND_BOUNDARY) != (unit == "us"):
        raise _market_fact_error()
    return parsed, rendered, unit


def _rows_for(request: HistoricalArchiveRequest, csv_bytes: bytes) -> Sequence[Tuple[int, Sequence[str]]]:
    try:
        text = csv_bytes.decode("utf-8-sig")
        rows = list(csv.reader(text.splitlines(), strict=True))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise _market_fact_error() from exc
    if not rows:
        raise _market_fact_error()
    expected = _CSV_HEADERS[request.data_family]
    first = tuple(rows[0])
    if first == expected:
        rows = rows[1:]
        offset = 2
    else:
        offset = 1
        if first and not first[0].isdigit():
            raise _market_fact_error()
    if not rows or any(len(row) != len(expected) for row in rows):
        raise _market_fact_error()
    return tuple((offset + index, tuple(row)) for index, row in enumerate(rows))


def _fact_id(
    request: HistoricalArchiveRequest,
    source_row_number: int,
    business_key: str,
    source_row: Sequence[str],
) -> str:
    return "mdf_" + business_hash(
        {
            "provider": request.provider,
            "market": request.market,
            "data_family": request.data_family,
            "symbol": request.symbol,
            "period": request.period,
            "source_row_number": source_row_number,
            "business_key": business_key,
            "source_row_hash": business_hash(list(source_row)),
        }
    )


def _base_fact(
    request: HistoricalArchiveRequest,
    source_row_number: int,
    business_key: str,
    event_time: str,
    ingested_at: str,
    fact_type: str,
    source_row: Sequence[str],
) -> Dict[str, Any]:
    return {
        "fact_id": _fact_id(request, source_row_number, business_key, source_row),
        "fact_type": fact_type,
        "provider": request.provider,
        "market": request.market,
        "data_family": request.data_family,
        "symbol": request.symbol,
        "business_key": business_key,
        "source_row_number": source_row_number,
        "event_time": event_time,
        "available_at": ingested_at,
    }


def _parse_kline(
    request: HistoricalArchiveRequest,
    row_number: int,
    row: Sequence[str],
    ingested_at: str,
) -> Dict[str, Any]:
    unit = "ms"
    if request.market == "SPOT":
        event, event_text, unit = _spot_timestamp(row[0])
    else:
        event, event_text = _timestamp(row[0], unit=unit)
    close, close_text = _timestamp(row[6], unit=unit)
    if not _request_period_contains(request, event) or close < event:
        raise _market_fact_error()
    interval = _KLINE_INTERVAL_MS[request.interval_or_null or ""]
    expected_close = event + timedelta(milliseconds=interval) - timedelta(
        microseconds=1 if unit == "us" else 1_000
    )
    if close != expected_close:
        raise _market_fact_error()
    open_price, high, low, close_price = (
        _decimal(row[1], positive=True),
        _decimal(row[2], positive=True),
        _decimal(row[3], positive=True),
        _decimal(row[4], positive=True),
    )
    if not (Decimal(low) <= min(Decimal(open_price), Decimal(close_price)) <= max(Decimal(open_price), Decimal(close_price)) <= Decimal(high)):
        raise _market_fact_error()
    business_key = request.symbol + ":" + event_text
    fact = _base_fact(
        request, row_number, business_key, close_text, ingested_at,
        "KLINE" if request.market == "SPOT" else "MARK_PRICE_KLINE",
        row,
    )
    fact.update({"open": open_price, "high": high, "low": low, "close": close_price})
    return fact


def _parse_agg_trade(
    request: HistoricalArchiveRequest,
    row_number: int,
    row: Sequence[str],
    ingested_at: str,
) -> Dict[str, Any]:
    aggregate_id, first_id, last_id = _integer(row[0], positive=True), _integer(row[3], positive=True), _integer(row[4], positive=True)
    if first_id > last_id:
        raise _market_fact_error()
    event, event_text, _ = _spot_timestamp(row[5])
    if not _request_period_contains(request, event):
        raise _market_fact_error()
    fact = _base_fact(request, row_number, request.symbol + ":" + str(aggregate_id), event_text, ingested_at, "AGG_TRADE", row)
    fact.update({
        "aggregate_trade_id": aggregate_id,
        "price": _decimal(row[1], positive=True),
        "quantity": _decimal(row[2], positive=True),
        "first_trade_id": first_id,
        "last_trade_id": last_id,
        "is_buyer_maker": _boolean(row[6]),
        "is_best_match": _boolean(row[7]),
    })
    return fact


def _parse_funding_rate(
    request: HistoricalArchiveRequest,
    row_number: int,
    row: Sequence[str],
    ingested_at: str,
) -> Dict[str, Any]:
    event, event_text = _timestamp(row[0], unit="ms")
    if not _request_period_contains(request, event) or _integer(row[1], positive=True) != 8:
        raise _market_fact_error()
    fact = _base_fact(request, row_number, request.symbol + ":" + event_text, event_text, ingested_at, "FUNDING_RATE", row)
    fact.update({"funding_interval_hours": 8, "funding_rate": _decimal(row[2])})
    return fact


def parse_market_facts(
    request: HistoricalArchiveRequest,
    csv_bytes: bytes,
    ingested_at: str,
) -> Tuple[Dict[str, Any], ...]:
    """Normalize one verified archive's CSV rows into immutable market facts."""

    if not isinstance(request, HistoricalArchiveRequest) or not isinstance(csv_bytes, bytes):
        raise _market_fact_error()
    _utc_input(ingested_at)
    rows = _rows_for(request, csv_bytes)
    parsers = {
        "KLINES": _parse_kline,
        "AGG_TRADES": _parse_agg_trade,
        "MARK_PRICE_KLINES": _parse_kline,
        "FUNDING_RATE": _parse_funding_rate,
    }
    facts = []
    previous_id = None
    for row_number, row in rows:
        try:
            fact = parsers[request.data_family](request, row_number, row, ingested_at)
        except (IndexError, ValueError, InvalidOperation, OverflowError) as exc:
            raise _market_fact_error() from exc
        if request.data_family == "AGG_TRADES":
            current_id = fact["aggregate_trade_id"]
            if previous_id is not None and current_id <= previous_id:
                raise _market_fact_error()
            previous_id = current_id
        facts.append(fact)
    return tuple(facts)


def _request_payload(request: HistoricalArchiveRequest) -> Dict[str, Any]:
    return {
        "schema_version": request.schema_version,
        "provider": request.provider,
        "market": request.market,
        "data_family": request.data_family,
        "symbol": request.symbol,
        "interval_or_null": request.interval_or_null,
        "period_kind": request.period_kind,
        "period": request.period,
    }


_FACT_BASE_FIELDS = frozenset((
    "fact_id", "fact_type", "provider", "market", "data_family", "symbol",
    "business_key", "source_row_number", "event_time", "available_at",
))
_FACT_FIELDS = {
    "KLINES": ("KLINE", _FACT_BASE_FIELDS | frozenset(("open", "high", "low", "close"))),
    "MARK_PRICE_KLINES": ("MARK_PRICE_KLINE", _FACT_BASE_FIELDS | frozenset(("open", "high", "low", "close"))),
    "AGG_TRADES": ("AGG_TRADE", _FACT_BASE_FIELDS | frozenset(("aggregate_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "is_buyer_maker", "is_best_match"))),
    "FUNDING_RATE": ("FUNDING_RATE", _FACT_BASE_FIELDS | frozenset(("funding_interval_hours", "funding_rate"))),
}


def _valid_fact_payload(request: HistoricalArchiveRequest, fact: Mapping[str, Any]) -> bool:
    expected_type, expected_fields = _FACT_FIELDS[request.data_family]
    if set(fact) != expected_fields or fact.get("fact_type") != expected_type:
        return False
    try:
        if (
            not isinstance(fact["fact_id"], str)
            or _FACT_ID.fullmatch(fact["fact_id"]) is None
            or not isinstance(fact["business_key"], str)
            or not fact["business_key"]
            or not isinstance(fact["source_row_number"], int)
            or fact["source_row_number"] < 1
        ):
            return False
        if request.data_family in ("KLINES", "MARK_PRICE_KLINES"):
            open_price, high, low, close = (Decimal(_decimal(fact[name], positive=True)) for name in ("open", "high", "low", "close"))
            return low <= min(open_price, close) <= max(open_price, close) <= high
        if request.data_family == "AGG_TRADES":
            return (
                _integer(str(fact["aggregate_trade_id"]), positive=True) > 0
                and _integer(str(fact["first_trade_id"]), positive=True) <= _integer(str(fact["last_trade_id"]), positive=True)
                and _decimal(fact["price"], positive=True) == fact["price"]
                and _decimal(fact["quantity"], positive=True) == fact["quantity"]
                and isinstance(fact["is_buyer_maker"], bool)
                and isinstance(fact["is_best_match"], bool)
            )
        return (
            fact["funding_interval_hours"] == 8
            and _decimal(fact["funding_rate"]) == fact["funding_rate"]
        )
    except (MarketDataError, TypeError, ValueError, InvalidOperation):
        return False


def _quality_reasons(
    request: HistoricalArchiveRequest,
    facts: Sequence[Mapping[str, Any]],
    ingested_at: str,
    recorded_at: str,
) -> Tuple[str, ...]:
    reasons = []
    try:
        ingested, _ = _utc_input(ingested_at)
        recorded, _ = _utc_input(recorded_at)
    except MarketDataError:
        return ("MARKET_DATA_TIME_INVALID",)
    if ingested > recorded:
        reasons.append("MARKET_DATA_TIME_ORDER")
    seen_ids, seen_keys = set(), set()
    previous_row = None
    previous_event = None
    event_times = []
    for fact in facts:
        if not isinstance(fact, Mapping):
            reasons.append("MARKET_DATA_FACT_INVALID")
            continue
        if not _valid_fact_payload(request, fact):
            reasons.append("MARKET_DATA_FACT_INVALID")
        try:
            row_number = fact["source_row_number"]
            fact_id = fact["fact_id"]
            key = fact["business_key"]
            event, _ = _utc_input(fact["event_time"])
            available, _ = _utc_input(fact["available_at"])
        except (KeyError, MarketDataError):
            reasons.append("MARKET_DATA_FACT_INVALID")
            continue
        if (
            fact.get("market") != request.market
            or fact.get("data_family") != request.data_family
            or fact.get("symbol") != request.symbol
            or fact.get("provider") != request.provider
        ):
            reasons.append("MARKET_DATA_FACT_SCOPE")
        if not isinstance(row_number, int) or row_number < 1:
            reasons.append("MARKET_DATA_SOURCE_ORDER")
        elif previous_row is not None and row_number != previous_row + 1:
            reasons.append("MARKET_DATA_SOURCE_ORDER")
        previous_row = row_number
        if fact_id in seen_ids or key in seen_keys:
            reasons.append("MARKET_DATA_DUPLICATE")
        seen_ids.add(fact_id)
        seen_keys.add(key)
        if event > available or available != ingested:
            reasons.append("MARKET_DATA_AVAILABILITY_ORDER")
        if available > ingested or ingested > recorded:
            reasons.append("MARKET_DATA_TIME_ORDER")
        if not _request_period_contains(request, event):
            reasons.append("MARKET_DATA_PERIOD_SCOPE")
        if previous_event is not None and event < previous_event:
            reasons.append("MARKET_DATA_EVENT_ORDER")
        previous_event = event
        event_times.append(event)
    if not facts:
        reasons.append("MARKET_DATA_PERIOD_COVERAGE")
    if request.data_family in ("KLINES", "MARK_PRICE_KLINES"):
        start = datetime.strptime(request.period, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        interval = timedelta(milliseconds=_KLINE_INTERVAL_MS[request.interval_or_null or ""])
        uses_microseconds = request.market == "SPOT" and start >= _SPOT_MICROSECOND_BOUNDARY
        closing_precision = timedelta(microseconds=1 if uses_microseconds else 1_000)
        expected = {
            start + (index + 1) * interval - closing_precision
            for index in range(int(timedelta(days=1) / interval))
        }
        if set(event_times) != expected or len(event_times) != len(expected):
            reasons.append("MARKET_DATA_PERIOD_COVERAGE")
    return tuple(sorted(set(reasons)))


def historical_market_data_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    """Return a snapshot self-hash excluding only the self-hash field."""

    return artifact_self_hash(snapshot, "snapshot_hash")


def historical_market_data_snapshot_reasons(snapshot: Mapping[str, Any]) -> Tuple[str, ...]:
    """Fail closed when a replayed archive artifact is not self-consistent."""

    if not isinstance(snapshot, Mapping):
        return ("MARKET_DATA_SNAPSHOT_INVALID",)
    reasons = []
    if snapshot.get("$schema") != "./historical-market-data-snapshot-v1.schema.json":
        reasons.append("MARKET_DATA_SCHEMA_INVALID")
    if snapshot.get("schema_version") != "1.0.0":
        reasons.append("MARKET_DATA_SCHEMA_INVALID")
    if snapshot.get("point_in_time_policy") != "ARCHIVE_REPLAY_ONLY":
        reasons.append("MARKET_DATA_PIT_POLICY_INVALID")
    try:
        if snapshot.get("snapshot_hash") != historical_market_data_snapshot_hash(snapshot):
            reasons.append("SNAPSHOT_HASH_MISMATCH")
        receipt = snapshot["source_receipt"]
        report = snapshot["quality_report"]
        if receipt.get("receipt_hash") != artifact_self_hash(receipt, "receipt_hash"):
            reasons.append("RECEIPT_HASH_MISMATCH")
        if report.get("report_hash") != artifact_self_hash(report, "report_hash"):
            reasons.append("QUALITY_REPORT_HASH_MISMATCH")
        request_fields = snapshot["request"]
        request = HistoricalArchiveRequest.create(
            market=request_fields["market"], data_family=request_fields["data_family"],
            symbol=request_fields["symbol"], interval_or_null=request_fields["interval_or_null"],
            period_kind=request_fields["period_kind"], period=request_fields["period"],
        )
        reasons.extend(_quality_reasons(
            request, snapshot["facts"], snapshot["ingested_at"], snapshot["recorded_at"]
        ))
        if report.get("blocking_findings"):
            reasons.append("MARKET_DATA_QUALITY_BLOCKING")
    except (KeyError, TypeError, MarketDataError, ValueError):
        reasons.append("MARKET_DATA_SNAPSHOT_INVALID")
    return tuple(sorted(set(reasons)))


def build_historical_market_data_snapshot(
    *,
    snapshot_id: str,
    request: HistoricalArchiveRequest,
    facts: Sequence[Mapping[str, Any]],
    archive_sha256: str,
    checksum_sha256: str,
    ingested_at: str,
    recorded_at: str,
) -> Dict[str, Any]:
    """Build a self-verifying, archive-only market-data artifact."""

    if (
        not isinstance(snapshot_id, str)
        or not snapshot_id
        or not isinstance(request, HistoricalArchiveRequest)
        or not isinstance(archive_sha256, str)
        or not isinstance(checksum_sha256, str)
        or _SHA256.fullmatch(archive_sha256) is None
        or _SHA256.fullmatch(checksum_sha256) is None
    ):
        raise MarketDataError("MARKET_DATA_QUALITY_BLOCKING")
    copied_facts = [dict(fact) for fact in facts]
    blocking = _quality_reasons(request, copied_facts, ingested_at, recorded_at)
    if blocking:
        raise MarketDataError("MARKET_DATA_QUALITY_BLOCKING")
    archive_bound_facts = []
    for fact in copied_facts:
        bound = dict(fact)
        bound["fact_id"] = "mdf_" + business_hash(
            {
                "archive_sha256": archive_sha256,
                "source_row_fact_id": fact["fact_id"],
                "business_key": fact["business_key"],
            }
        )
        archive_bound_facts.append(bound)
    receipt = {
        "provider": request.provider,
        "archive_sha256": archive_sha256,
        "checksum_sha256": checksum_sha256,
        "available_at": ingested_at,
        "ingested_at": ingested_at,
        "receipt_hash": "0" * 64,
    }
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    report = {
        "blocking_findings": [],
        "warning_findings": [],
        "report_hash": "0" * 64,
    }
    report["report_hash"] = artifact_self_hash(report, "report_hash")
    snapshot = {
        "$schema": "./historical-market-data-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": snapshot_id,
        "snapshot_hash": "0" * 64,
        "hash_algorithm": "SHA-256",
        "canonicalization": "RFC8785_JCS",
        "point_in_time_policy": "ARCHIVE_REPLAY_ONLY",
        "request": _request_payload(request),
        "source_receipt": receipt,
        "quality_report": report,
        "facts": archive_bound_facts,
        "ingested_at": ingested_at,
        "recorded_at": recorded_at,
    }
    snapshot["snapshot_hash"] = historical_market_data_snapshot_hash(snapshot)
    reasons = historical_market_data_snapshot_reasons(snapshot)
    if reasons:
        raise MarketDataError("MARKET_DATA_QUALITY_BLOCKING")
    return snapshot


def fee_schedule_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    """Return the independent Fee Schedule self-hash."""

    return artifact_self_hash(snapshot, "fee_schedule_hash")


def _approved(approval: Any) -> bool:
    if not isinstance(approval, Mapping) or not isinstance(approval.get("approved_by"), str):
        return False
    if not approval.get("approved_by"):
        return False
    try:
        _utc_input(approval.get("approved_at"))
    except MarketDataError:
        return False
    return True


def fee_schedule_snapshot_reasons(snapshot: Mapping[str, Any]) -> Tuple[str, ...]:
    """Validate that a Fee Schedule is explicit, non-overlapping and approved."""

    if not isinstance(snapshot, Mapping):
        return ("FEE_SCHEDULE_INVALID",)
    reasons = []
    if snapshot.get("$schema") != "./fee-schedule-snapshot-v1.schema.json" or snapshot.get("schema_version") != "1.0.0":
        reasons.append("FEE_SCHEDULE_INVALID")
    try:
        allowed_snapshot_fields = {
            "$schema", "schema_version", "fee_schedule_id", "fee_schedule_hash",
            "hash_algorithm", "canonicalization", "usage_environment", "schedules",
            "production_approval",
        }
        if (
            not set(snapshot).issubset(allowed_snapshot_fields)
            or not isinstance(snapshot.get("fee_schedule_id"), str)
            or not snapshot.get("fee_schedule_id")
            or snapshot.get("hash_algorithm") != "SHA-256"
            or snapshot.get("canonicalization") != "RFC8785_JCS"
            or snapshot.get("usage_environment") not in ("RESEARCH", "PRODUCTION")
        ):
            reasons.append("FEE_SCHEDULE_INVALID")
        if snapshot.get("fee_schedule_hash") != fee_schedule_snapshot_hash(snapshot):
            reasons.append("FEE_SCHEDULE_HASH_MISMATCH")
        schedules = snapshot["schedules"]
        if not isinstance(schedules, list) or not schedules:
            raise ValueError("schedules")
        grouped: Dict[Tuple[Any, Any], list] = {}
        for item in schedules:
            required_fields = {
                "fee_id", "market", "symbol", "effective_at", "expires_at", "maker_rate",
                "taker_rate", "lifecycle", "approval",
            }
            if not isinstance(item, Mapping) or set(item) != required_fields:
                raise ValueError("schedule")
            if (
                not isinstance(item["fee_id"], str) or not item["fee_id"]
                or item["market"] not in ("SPOT", "USD_M")
                or item["symbol"] not in _ALLOWED_SYMBOLS
            ):
                reasons.append("FEE_SCHEDULE_INVALID")
            start, _ = _utc_input(item["effective_at"])
            end = None
            if item.get("expires_at") is not None:
                end, _ = _utc_input(item["expires_at"])
                if end <= start:
                    reasons.append("FEE_SCHEDULE_EFFECTIVE_INTERVAL_INVALID")
            for rate in (item.get("maker_rate"), item.get("taker_rate")):
                try:
                    if Decimal(_decimal(rate)) < 0:
                        reasons.append("FEE_SCHEDULE_INVALID_DECIMAL")
                except MarketDataError:
                    reasons.append("FEE_SCHEDULE_INVALID_DECIMAL")
            lifecycle = item.get("lifecycle")
            if lifecycle not in ("DRAFT", "APPROVED", "RETIRED"):
                reasons.append("FEE_SCHEDULE_LIFECYCLE_INVALID")
            approval = item.get("approval")
            if lifecycle == "APPROVED" and not _approved(approval):
                reasons.append("FEE_SCHEDULE_APPROVAL_INVALID")
            grouped.setdefault((item.get("market"), item.get("symbol")), []).append((start, end))
        for intervals in grouped.values():
            intervals.sort(key=lambda value: value[0])
            for (_, previous_end), (current_start, _) in zip(intervals, intervals[1:]):
                if previous_end is None or current_start < previous_end:
                    reasons.append("FEE_SCHEDULE_EFFECTIVE_INTERVAL_OVERLAP")
        if snapshot.get("usage_environment") == "PRODUCTION":
            approval = snapshot.get("production_approval")
            if not _approved(approval):
                reasons.append("FEE_SCHEDULE_PRODUCTION_UNAPPROVED")
            if any(item.get("lifecycle") != "APPROVED" for item in schedules):
                reasons.append("FEE_SCHEDULE_PRODUCTION_UNAPPROVED")
    except (KeyError, TypeError, ValueError, MarketDataError):
        reasons.append("FEE_SCHEDULE_INVALID")
    return tuple(sorted(set(reasons)))
