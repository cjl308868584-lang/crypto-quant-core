"""Fail-closed boundary for Binance public historical archives."""

import csv
import hashlib
import hmac
import json
import re
import stat
import zipfile
from functools import lru_cache
from importlib import resources
from io import BytesIO
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, InvalidOperation, localcontext
from pathlib import PurePosixPath
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from jsonschema import Draft202012Validator

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
_PUBLIC_ARCHIVE_HOST = "data.binance.vision"
_HTTP_TIMEOUT_SECONDS = 15
_HTTP_GET_ATTEMPTS = 2
_REQUEST_CONSTRUCTION_TOKEN = object()
_VERIFIED_ARCHIVE_TOKEN = object()
_DECIMAL_CONTEXT = Context(prec=50)
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_FACT_ID = re.compile(r"^mdf_[a-f0-9]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_KLINE_INTERVAL_MS = {"1m": 60_000, "15m": 900_000, "4h": 14_400_000, "1d": 86_400_000}
_SPOT_MICROSECOND_BOUNDARY = datetime(2025, 1, 1, tzinfo=timezone.utc)
_PARSER_VERSION = "BINANCE_CSV_V2"
_SUPPORTED_PARSER_VERSIONS = frozenset(
    ("BINANCE_CSV_V1", "BINANCE_CSV_V2")
)
_AVAILABILITY_BASIS = "OFFLINE_ARCHIVE_OBSERVED_AT_INGESTION"
_FUNDING_SCHEDULE_JITTER = timedelta(seconds=1)
_SNAPSHOT_ATTESTATION_TYPE = "HISTORICAL_MARKET_DATA_SNAPSHOT_ATTESTATION"
_SNAPSHOT_ATTESTATION_SCHEMA_VERSION = "1.0.0"
_FAMILY_SPECS = {
    ("SPOT", "KLINES"): (
        "spot",
        frozenset(("daily", "monthly")),
        "klines",
        True,
    ),
    ("SPOT", "AGG_TRADES"): (
        "spot",
        frozenset(("daily",)),
        "aggTrades",
        False,
    ),
    ("USD_M", "MARK_PRICE_KLINES"): (
        "futures/um",
        frozenset(("daily", "monthly")),
        "markPriceKlines",
        True,
    ),
    ("USD_M", "FUNDING_RATE"): (
        "futures/um",
        frozenset(("monthly",)),
        "fundingRate",
        False,
    ),
}


@lru_cache(maxsize=2)
def _artifact_validator(filename: str) -> Draft202012Validator:
    schema_resource = resources.files("crypto_quant").joinpath("schemas", filename)
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _schema_valid(filename: str, artifact: Mapping[str, Any]) -> bool:
    return not tuple(_artifact_validator(filename).iter_errors(artifact))


class MarketDataError(ValueError):
    """A public archive request violates a stable safety boundary."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class HttpResponse:
    """The complete, non-streaming result of one public HTTPS GET."""

    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes


def _is_public_archive_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == _PUBLIC_ARCHIVE_HOST
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
            and bool(parsed.path)
        )
    except ValueError:
        return False


def _require_public_archive_url(url: object) -> None:
    if not _is_public_archive_url(url):
        raise MarketDataError("HTTP_RESPONSE_REDIRECT_INVALID")


class _SameHostRedirectHandler(HTTPRedirectHandler):
    """Allow HTTPS redirects only when they remain on the public archive host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _require_public_archive_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _public_archive_opener():
    """Build an opener that cannot inherit proxy credentials from the environment."""

    return build_opener(ProxyHandler({}), _SameHostRedirectHandler())


def _response_read_limit(url: str) -> int:
    _require_public_archive_url(url)
    return _MAX_CHECKSUM_BYTES if url.endswith(".CHECKSUM") else _MAX_ARCHIVE_BYTES


class PublicArchiveTransport:
    """Concrete, credential-free public archive transport with a GET-only API."""

    def get(self, url):
        _require_public_archive_url(url)
        maximum_bytes = _response_read_limit(url)
        opener = _public_archive_opener()
        for attempt in range(_HTTP_GET_ATTEMPTS):
            try:
                request = Request(url, method="GET")
                with opener.open(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
                    return HttpResponse(
                        status=response.getcode(),
                        final_url=response.geturl(),
                        headers=dict(response.headers.items()),
                        body=_read_bounded_response(response, maximum_bytes),
                    )
            except HTTPError as error:
                return HttpResponse(
                    status=error.code,
                    final_url=error.geturl(),
                    headers=dict(error.headers.items()) if error.headers is not None else {},
                    body=b"",
                )
            except (OSError, TimeoutError, URLError) as error:
                if attempt + 1 == _HTTP_GET_ATTEMPTS:
                    raise MarketDataError("HTTP_TRANSPORT_FAILURE") from error
        raise MarketDataError("HTTP_TRANSPORT_FAILURE")


def _read_bounded_response(response: Any, maximum_bytes: int) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = response.read(min(_READ_CHUNK_BYTES, maximum_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > maximum_bytes:
            raise MarketDataError("HTTP_RESPONSE_TOO_LARGE")
        chunks.append(chunk)
    return b"".join(chunks)


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
        _, allowed_period_kinds, _, needs_interval = spec
        if (
            not isinstance(period_kind, str)
            or period_kind.lower() not in allowed_period_kinds
        ):
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
        root, _, directory, needs_interval = _FAMILY_SPECS[
            (self.market, self.data_family)
        ]
        path = [root, self.period_kind.lower(), directory, self.symbol]
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
    _checksum_bytes: bytes
    _official_sha256: str

    def __init__(self, *args, **kwargs):
        raise TypeError("verified archives are issued by checksum validation")

    @classmethod
    def _issue(
        cls,
        token: object,
        request: HistoricalArchiveRequest,
        archive_bytes: bytes,
        checksum_bytes: bytes,
        official_sha256: str,
    ) -> "_VerifiedArchive":
        if token is not _VERIFIED_ARCHIVE_TOKEN:
            raise TypeError("verified archives are issued by checksum validation")
        verified = object.__new__(cls)
        object.__setattr__(verified, "_request", request)
        object.__setattr__(verified, "_archive_bytes", archive_bytes)
        object.__setattr__(verified, "_checksum_bytes", checksum_bytes)
        object.__setattr__(verified, "_official_sha256", official_sha256)
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
        checksum_bytes,
        expected_digest.lower(),
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


def _response_header(headers: Mapping[str, str], name: str) -> Optional[str]:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _validated_response(
    response: object,
    *,
    maximum_bytes: int,
) -> HttpResponse:
    if not isinstance(response, HttpResponse):
        raise MarketDataError("HTTP_RESPONSE_METADATA_INVALID")
    if response.status != 200:
        raise MarketDataError("HTTP_STATUS_INVALID")
    if (
        not isinstance(response.final_url, str)
        or not isinstance(response.headers, Mapping)
        or not isinstance(response.body, bytes)
        or any(not isinstance(key, str) or not isinstance(value, str) for key, value in response.headers.items())
    ):
        raise MarketDataError("HTTP_RESPONSE_METADATA_INVALID")
    _require_public_archive_url(response.final_url)
    content_length = _response_header(response.headers, "Content-Length")
    if content_length is not None:
        if not content_length.isascii() or not content_length.isdigit():
            raise MarketDataError("HTTP_RESPONSE_METADATA_INVALID")
        if int(content_length) > maximum_bytes:
            raise MarketDataError("HTTP_RESPONSE_TOO_LARGE")
    if len(response.body) > maximum_bytes:
        raise MarketDataError("HTTP_RESPONSE_TOO_LARGE")
    return response


def _fetched_snapshot_id(request: HistoricalArchiveRequest) -> str:
    return "historical-" + business_hash(_request_payload(request))


def fetch_historical_market_data(
    request: HistoricalArchiveRequest,
    transport: PublicArchiveTransport,
    retrieved_at: str,
    *,
    allow_research_degraded: bool = False,
) -> Dict[str, Any]:
    """Fetch, authenticate, parse, and freeze one allowlisted archive snapshot."""

    if not isinstance(request, HistoricalArchiveRequest) or not hasattr(transport, "get"):
        raise MarketDataError("REQUEST_INVALID")
    _utc_input(retrieved_at)
    archive_response = _validated_response(
        transport.get(request.archive_url),
        maximum_bytes=_MAX_ARCHIVE_BYTES,
    )
    checksum_response = _validated_response(
        transport.get(request.checksum_url),
        maximum_bytes=_MAX_CHECKSUM_BYTES,
    )
    verified_archive = verify_official_checksum(
        request,
        archive_response.body,
        checksum_response.body,
    )
    fields = {
        "snapshot_id": _fetched_snapshot_id(request),
        "verified_archive": verified_archive,
        "retrieved_at": retrieved_at,
        "ingested_at": retrieved_at,
        "recorded_at": retrieved_at,
        "source_etag_or_null": _response_header(
            archive_response.headers,
            "ETag",
        ),
        "source_last_modified_at_or_null": _response_header(
            archive_response.headers,
            "Last-Modified",
        ),
    }
    try:
        return build_historical_market_data_snapshot(**fields)
    except MarketDataError as error:
        if (
            not allow_research_degraded
            or error.reason_code != "MARKET_DATA_QUALITY_BLOCKING"
        ):
            raise
        return build_research_degraded_historical_market_data_snapshot(
            **fields
        )


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
_CSV_HEADER_ALIASES = {
    "KLINES": frozenset(
        (
            (
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "count",
                "taker_buy_volume",
                "taker_buy_quote_volume",
                "ignore",
            ),
        )
    ),
    "MARK_PRICE_KLINES": frozenset(
        (
            (
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "count",
                "taker_buy_volume",
                "taker_buy_quote_volume",
                "ignore",
            ),
        )
    ),
    "AGG_TRADES": frozenset(),
    "FUNDING_RATE": frozenset(),
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


def _nonnegative_decimal(value: str) -> str:
    rendered = _decimal(value)
    if Decimal(rendered) < 0:
        raise _market_fact_error()
    return rendered


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
    if first == expected or first in _CSV_HEADER_ALIASES[request.data_family]:
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


_FACT_PROVENANCE_FIELDS = frozenset(
    (
        "fact_id",
        "source_row_fact_id",
        "source_row",
        "source_row_hash",
        "payload_hash",
        "source_row_number",
    )
)


def _normalized_fact_payload(fact: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in fact.items()
        if key not in _FACT_PROVENANCE_FIELDS
    }


def _finalize_parsed_fact(fact: Dict[str, Any]) -> Dict[str, Any]:
    fact["payload_hash"] = business_hash(_normalized_fact_payload(fact))
    return fact


def _base_fact(
    request: HistoricalArchiveRequest,
    source_row_number: int,
    business_key: str,
    event_time: str,
    ingested_at: str,
    fact_type: str,
    source_row: Sequence[str],
) -> Dict[str, Any]:
    source_row_fact_id = _fact_id(request, source_row_number, business_key, source_row)
    source_row_values = list(source_row)
    return {
        "fact_id": source_row_fact_id,
        "source_row_fact_id": source_row_fact_id,
        "source_row": source_row_values,
        "source_row_hash": business_hash(source_row_values),
        "fact_type": fact_type,
        "provider": request.provider,
        "market": request.market,
        "data_family": request.data_family,
        "symbol": request.symbol,
        "business_key": business_key,
        "source_row_number": source_row_number,
        "event_time": event_time,
        "available_at": ingested_at,
        "ingested_at": ingested_at,
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
    _nonnegative_decimal(row[5])
    _nonnegative_decimal(row[7])
    _integer(row[8])
    _nonnegative_decimal(row[9])
    _nonnegative_decimal(row[10])
    if _integer(row[11]) != 0:
        raise _market_fact_error()
    business_key = request.symbol + ":" + event_text
    fact = _base_fact(
        request, row_number, business_key, close_text, ingested_at,
        "KLINE" if request.market == "SPOT" else "MARK_PRICE_KLINE",
        row,
    )
    fact.update(
        {
            "open_time": event_text,
            "close_time": close_text,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close_price,
            "volume": _nonnegative_decimal(row[5]),
            "quote_asset_volume": _nonnegative_decimal(row[7]),
            "number_of_trades": _integer(row[8]),
            "taker_buy_base_asset_volume": _nonnegative_decimal(row[9]),
            "taker_buy_quote_asset_volume": _nonnegative_decimal(row[10]),
            "ignore": _integer(row[11]),
        }
    )
    return _finalize_parsed_fact(fact)


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
    return _finalize_parsed_fact(fact)


def _parse_funding_rate(
    request: HistoricalArchiveRequest,
    row_number: int,
    row: Sequence[str],
    ingested_at: str,
) -> Dict[str, Any]:
    event, event_text = _timestamp(row[0], unit="ms")
    funding_interval_hours = _integer(row[1], positive=True)
    if (
        not _request_period_contains(request, event)
        or funding_interval_hours > 24
    ):
        raise _market_fact_error()
    fact = _base_fact(request, row_number, request.symbol + ":" + event_text, event_text, ingested_at, "FUNDING_RATE", row)
    fact.update({"funding_interval_hours": funding_interval_hours, "funding_rate": _decimal(row[2])})
    return _finalize_parsed_fact(fact)


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
    "fact_id", "source_row_fact_id", "source_row", "source_row_hash", "payload_hash",
    "fact_type", "provider", "market", "data_family", "symbol", "business_key",
    "source_row_number", "event_time", "available_at", "ingested_at",
))
_KLINE_PAYLOAD_FIELDS = frozenset(
    (
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
        "ignore",
    )
)
_FACT_FIELDS = {
    "KLINES": ("KLINE", _FACT_BASE_FIELDS | _KLINE_PAYLOAD_FIELDS),
    "MARK_PRICE_KLINES": ("MARK_PRICE_KLINE", _FACT_BASE_FIELDS | _KLINE_PAYLOAD_FIELDS),
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
            or not isinstance(fact["source_row_fact_id"], str)
            or _FACT_ID.fullmatch(fact["source_row_fact_id"]) is None
            or not isinstance(fact["source_row"], list)
            or not fact["source_row"]
            or any(not isinstance(value, str) for value in fact["source_row"])
            or not isinstance(fact["source_row_hash"], str)
            or _SHA256.fullmatch(fact["source_row_hash"]) is None
            or fact["source_row_hash"] != business_hash(fact["source_row"])
            or not isinstance(fact["payload_hash"], str)
            or _SHA256.fullmatch(fact["payload_hash"]) is None
            or fact["payload_hash"] != business_hash(_normalized_fact_payload(fact))
            or not isinstance(fact["business_key"], str)
            or not fact["business_key"]
            or not isinstance(fact["source_row_number"], int)
            or fact["source_row_number"] < 1
        ):
            return False
        _utc_input(fact["ingested_at"])
        if request.data_family in ("KLINES", "MARK_PRICE_KLINES"):
            open_price, high, low, close = (Decimal(_decimal(fact[name], positive=True)) for name in ("open", "high", "low", "close"))
            return (
                low <= min(open_price, close) <= max(open_price, close) <= high
                and _nonnegative_decimal(fact["volume"]) == fact["volume"]
                and _nonnegative_decimal(fact["quote_asset_volume"]) == fact["quote_asset_volume"]
                and _integer(str(fact["number_of_trades"])) == fact["number_of_trades"]
                and _nonnegative_decimal(fact["taker_buy_base_asset_volume"])
                == fact["taker_buy_base_asset_volume"]
                and _nonnegative_decimal(fact["taker_buy_quote_asset_volume"])
                == fact["taker_buy_quote_asset_volume"]
                and fact["ignore"] == 0
            )
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
            isinstance(fact["funding_interval_hours"], int)
            and 1 <= fact["funding_interval_hours"] <= 24
            and _decimal(fact["funding_rate"]) == fact["funding_rate"]
        )
    except (MarketDataError, TypeError, ValueError, InvalidOperation):
        return False


def _expected_kline_events(request: HistoricalArchiveRequest) -> set:
    if request.period_kind == "DAILY":
        start = datetime.strptime(request.period, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        end = start + timedelta(days=1)
    else:
        start = datetime.strptime(request.period, "%Y-%m").replace(
            tzinfo=timezone.utc
        )
        end = (
            start.replace(year=start.year + 1, month=1)
            if start.month == 12
            else start.replace(month=start.month + 1)
        )
    interval = timedelta(milliseconds=_KLINE_INTERVAL_MS[request.interval_or_null or ""])
    uses_microseconds = request.market == "SPOT" and start >= _SPOT_MICROSECOND_BOUNDARY
    closing_precision = timedelta(microseconds=1 if uses_microseconds else 1_000)
    return {
        start + (index + 1) * interval - closing_precision
        for index in range(int((end - start) / interval))
    }


def _quality_report(
    request: HistoricalArchiveRequest,
    facts: Sequence[Mapping[str, Any]],
    ingested_at: str,
    recorded_at: str,
) -> Dict[str, Any]:
    reasons = []
    warning_findings = []
    try:
        ingested, _ = _utc_input(ingested_at)
        recorded, _ = _utc_input(recorded_at)
    except MarketDataError:
        ingested = recorded = datetime.min.replace(tzinfo=timezone.utc)
        reasons.append("MARKET_DATA_TIME_INVALID")
    if ingested > recorded:
        reasons.append("MARKET_DATA_TIME_ORDER")
    source_facts = sorted(
        (fact for fact in facts if isinstance(fact, Mapping)),
        key=lambda fact: fact.get("source_row_number", -1)
        if isinstance(fact.get("source_row_number"), int)
        else -1,
    )
    seen_ids, seen_keys = set(), set()
    previous_row = None
    previous_event = None
    event_times = []
    duplicate_count = 0
    source_order_regression_count = 0
    for fact in source_facts:
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
            fact_ingested, _ = _utc_input(fact["ingested_at"])
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
        elif previous_row is not None and row_number <= previous_row:
            reasons.append("MARKET_DATA_SOURCE_ORDER")
            source_order_regression_count += 1
        previous_row = row_number
        if fact_id in seen_ids or key in seen_keys:
            reasons.append("MARKET_DATA_DUPLICATE")
            duplicate_count += 1
        seen_ids.add(fact_id)
        seen_keys.add(key)
        if event > available or available != ingested:
            reasons.append("MARKET_DATA_AVAILABILITY_ORDER")
        if available != fact_ingested or fact_ingested != ingested:
            reasons.append("MARKET_DATA_FACT_TIME_CROSSLINK")
        if available > fact_ingested or fact_ingested > recorded:
            reasons.append("MARKET_DATA_TIME_ORDER")
        if not _request_period_contains(request, event):
            reasons.append("MARKET_DATA_PERIOD_SCOPE")
        if previous_event is not None and event < previous_event:
            reasons.append("MARKET_DATA_EVENT_ORDER")
        previous_event = event
        event_times.append(event)
    if not facts:
        reasons.append("MARKET_DATA_PERIOD_COVERAGE")
    missing_interval_count = 0
    expected_period_coverage = bool(facts)
    if request.data_family in ("KLINES", "MARK_PRICE_KLINES"):
        expected = _expected_kline_events(request)
        missing_interval_count = len(expected - set(event_times))
        expected_period_coverage = (
            set(event_times) == expected and len(event_times) == len(expected)
        )
        if not expected_period_coverage:
            reasons.append("MARKET_DATA_PERIOD_COVERAGE")
    elif request.data_family == "FUNDING_RATE":
        start = datetime.strptime(request.period, "%Y-%m").replace(
            tzinfo=timezone.utc
        )
        end = (
            start.replace(year=start.year + 1, month=1)
            if start.month == 12
            else start.replace(month=start.month + 1)
        )
        funding_events = []
        for fact in source_facts:
            try:
                event, _ = _utc_input(fact["event_time"])
                interval_hours = fact["funding_interval_hours"]
                if (
                    not isinstance(interval_hours, int)
                    or not 1 <= interval_hours <= 24
                ):
                    raise ValueError("funding interval")
                funding_events.append((event, interval_hours))
            except (KeyError, MarketDataError, TypeError, ValueError):
                continue
        if funding_events:
            scheduled = start
            maximum_jitter = timedelta(0)
            for event, interval_hours in funding_events:
                interval = timedelta(hours=interval_hours)
                while event > scheduled + _FUNDING_SCHEDULE_JITTER:
                    missing_interval_count += 1
                    scheduled += interval
                jitter = abs(event - scheduled)
                maximum_jitter = max(maximum_jitter, jitter)
                if jitter > _FUNDING_SCHEDULE_JITTER:
                    missing_interval_count += 1
                scheduled += interval
            while scheduled < end:
                missing_interval_count += 1
                scheduled += timedelta(hours=funding_events[-1][1])
            if scheduled != end:
                missing_interval_count += 1
            if maximum_jitter > timedelta(0):
                warning_findings.append(
                    "FUNDING_CALC_TIME_JITTER_WITHIN_1S"
                )
        else:
            missing_interval_count = 1
        expected_period_coverage = missing_interval_count == 0
        if not expected_period_coverage:
            reasons.append("MARKET_DATA_FUNDING_GAP")
            reasons.append("MARKET_DATA_PERIOD_COVERAGE")
    ordered_event_times = sorted(event_times)
    report = {
        "row_count": len(facts),
        "first_event_time": (
            ordered_event_times[0].isoformat().replace("+00:00", "Z")
            if ordered_event_times
            else None
        ),
        "last_event_time": (
            ordered_event_times[-1].isoformat().replace("+00:00", "Z")
            if ordered_event_times
            else None
        ),
        "duplicate_business_key_count": duplicate_count,
        "source_order_regression_count": source_order_regression_count,
        "missing_interval_count": missing_interval_count,
        "malformed_row_count": 0,
        "rejected_row_count": 0,
        "checksum_pass": True,
        "expected_period_coverage": expected_period_coverage,
        "warning_findings": sorted(set(warning_findings)),
        "blocking_findings": sorted(set(reasons)),
        "report_hash": "0" * 64,
    }
    report["report_hash"] = artifact_self_hash(report, "report_hash")
    return report


def _quality_reasons(
    request: HistoricalArchiveRequest,
    facts: Sequence[Mapping[str, Any]],
    ingested_at: str,
    recorded_at: str,
) -> Tuple[str, ...]:
    return tuple(
        _quality_report(request, facts, ingested_at, recorded_at)[
            "blocking_findings"
        ]
    )


def _archive_bound_fact_id(
    archive_sha256: str,
    source_row_fact_id: str,
    business_key: str,
) -> str:
    return "mdf_" + business_hash(
        {
            "archive_sha256": archive_sha256,
            "source_row_fact_id": source_row_fact_id,
            "business_key": business_key,
        }
    )


def historical_market_data_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    """Return a snapshot self-hash excluding only the self-hash field."""

    return artifact_self_hash(snapshot, "snapshot_hash")


def historical_market_data_snapshot_attestation_envelope(
    snapshot: Mapping[str, Any],
) -> Dict[str, Any]:
    """Return the external trust envelope for one complete snapshot version."""

    try:
        receipt = snapshot["source_receipt"]
        envelope = {
            "attestation_schema_version": _SNAPSHOT_ATTESTATION_SCHEMA_VERSION,
            "attestation_type": _SNAPSHOT_ATTESTATION_TYPE,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "snapshot_schema": snapshot["$schema"],
            "snapshot_schema_version": snapshot["schema_version"],
            "parser_version": snapshot["parser_version"],
            "snapshot_id": snapshot["snapshot_id"],
            "recorded_at": snapshot["recorded_at"],
            "receipt_hash": receipt["receipt_hash"],
            "snapshot_hash": snapshot["snapshot_hash"],
        }
    except (KeyError, TypeError) as error:
        raise MarketDataError("SNAPSHOT_ATTESTATION_INVALID") from error
    if (
        not isinstance(receipt, Mapping)
        or envelope["snapshot_schema"]
        != "./historical-market-data-snapshot-v1.schema.json"
        or envelope["snapshot_schema_version"] != "1.0.0"
        or envelope["parser_version"] not in _SUPPORTED_PARSER_VERSIONS
        or not isinstance(envelope["snapshot_id"], str)
        or _ID.fullmatch(envelope["snapshot_id"]) is None
        or not isinstance(envelope["receipt_hash"], str)
        or _SHA256.fullmatch(envelope["receipt_hash"]) is None
        or not isinstance(envelope["snapshot_hash"], str)
        or _SHA256.fullmatch(envelope["snapshot_hash"]) is None
    ):
        raise MarketDataError("SNAPSHOT_ATTESTATION_INVALID")
    try:
        _utc_input(envelope["recorded_at"])
    except MarketDataError as error:
        raise MarketDataError("SNAPSHOT_ATTESTATION_INVALID") from error
    return envelope


def historical_market_data_snapshot_attestation_hash(
    snapshot: Mapping[str, Any],
) -> str:
    """Hash the external envelope that must be anchored outside the snapshot."""

    return business_hash(
        historical_market_data_snapshot_attestation_envelope(snapshot)
    )


def _facts_root_hash(facts: Sequence[Mapping[str, Any]]) -> str:
    return business_hash([dict(fact) for fact in facts])


def _source_rows_root_hash(facts: Sequence[Mapping[str, Any]]) -> str:
    return business_hash(
        [
            {
                "source_row_number": fact["source_row_number"],
                "source_row_hash": fact["source_row_hash"],
            }
            for fact in sorted(facts, key=lambda item: item["source_row_number"])
        ]
    )


def _bind_fact_to_archive(
    fact: Mapping[str, Any],
    archive_sha256: str,
) -> Dict[str, Any]:
    bound = dict(fact)
    bound["source_row"] = list(fact["source_row"])
    bound["fact_id"] = _archive_bound_fact_id(
        archive_sha256,
        fact["source_row_fact_id"],
        fact["business_key"],
    )
    return bound


def _parse_one_fact(
    request: HistoricalArchiveRequest,
    row_number: int,
    source_row: Sequence[str],
    ingested_at: str,
) -> Dict[str, Any]:
    parser = {
        "KLINES": _parse_kline,
        "AGG_TRADES": _parse_agg_trade,
        "MARK_PRICE_KLINES": _parse_kline,
        "FUNDING_RATE": _parse_funding_rate,
    }[request.data_family]
    return parser(request, row_number, tuple(source_row), ingested_at)


def historical_market_data_snapshot_reasons(
    snapshot: Mapping[str, Any],
    *,
    trusted_snapshot_attestation_hashes: Optional[Sequence[str]] = None,
    trusted_receipt_hashes: Optional[Sequence[str]] = None,
) -> Tuple[str, ...]:
    """Fail closed when a replayed archive artifact is not self-consistent."""

    if not isinstance(snapshot, Mapping):
        return ("MARKET_DATA_SNAPSHOT_INVALID",)
    reasons = []
    if not _schema_valid("historical-market-data-snapshot-v1.schema.json", snapshot):
        reasons.append("MARKET_DATA_SCHEMA_INVALID")
    if snapshot.get("$schema") != "./historical-market-data-snapshot-v1.schema.json":
        reasons.append("MARKET_DATA_SCHEMA_INVALID")
    if snapshot.get("schema_version") != "1.0.0":
        reasons.append("MARKET_DATA_SCHEMA_INVALID")
    if snapshot.get("pit_eligibility") != "ARCHIVE_REPLAY_ONLY":
        reasons.append("MARKET_DATA_PIT_POLICY_INVALID")
    if snapshot.get("parser_version") not in _SUPPORTED_PARSER_VERSIONS:
        reasons.append("MARKET_DATA_PARSER_VERSION_INVALID")
    if snapshot.get("availability_basis") != _AVAILABILITY_BASIS:
        reasons.append("MARKET_DATA_AVAILABILITY_BASIS_INVALID")
    if snapshot.get("quality_eligibility") == "RESEARCH_ONLY_DEGRADED":
        reasons.append("MARKET_DATA_RESEARCH_ONLY_DEGRADED")
    elif snapshot.get("quality_eligibility") != "FORMAL_COMPLETE":
        reasons.append("MARKET_DATA_QUALITY_ELIGIBILITY_INVALID")
    try:
        if snapshot.get("snapshot_hash") != historical_market_data_snapshot_hash(snapshot):
            reasons.append("SNAPSHOT_HASH_MISMATCH")
        receipt = snapshot["source_receipt"]
        report = snapshot["quality_report"]
        snapshot_attestation_hash = (
            historical_market_data_snapshot_attestation_hash(snapshot)
        )
        if trusted_snapshot_attestation_hashes is None:
            reasons.append("TRUSTED_SNAPSHOT_ATTESTATION_REQUIRED")
            if trusted_receipt_hashes is not None:
                reasons.append("TRUSTED_RECEIPT_ATTESTATION_INSUFFICIENT")
        else:
            try:
                trusted_hashes = set(trusted_snapshot_attestation_hashes)
            except TypeError:
                trusted_hashes = set()
            if snapshot_attestation_hash not in trusted_hashes:
                reasons.append("TRUSTED_SNAPSHOT_ATTESTATION_MISMATCH")
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
        if dict(request_fields) != _request_payload(request):
            reasons.append("REQUEST_CROSSLINK_MISMATCH")
        expected_receipt_fields = {
            "request",
            "archive_url",
            "checksum_url",
            "retrieved_at",
            "archive_size_bytes",
            "checksum_size_bytes",
            "official_sha256",
            "archive_sha256",
            "checksum_file_sha256",
            "csv_member",
            "csv_sha256",
            "source_rows_root_hash",
            "facts_root_hash",
            "source_etag_or_null",
            "source_last_modified_at_or_null",
            "receipt_hash",
        }
        if (
            set(receipt) != expected_receipt_fields
            or receipt.get("request") != _request_payload(request)
            or receipt.get("archive_url") != request.archive_url
            or receipt.get("checksum_url") != request.checksum_url
            or receipt.get("csv_member") != request.expected_csv_name
            or receipt.get("retrieved_at") != snapshot["retrieved_at"]
            or not isinstance(receipt.get("archive_size_bytes"), int)
            or receipt.get("archive_size_bytes", 0) <= 0
            or not isinstance(receipt.get("checksum_size_bytes"), int)
            or receipt.get("checksum_size_bytes", 0) <= 0
            or not isinstance(receipt.get("archive_sha256"), str)
            or _SHA256.fullmatch(receipt["archive_sha256"]) is None
            or receipt.get("official_sha256") != receipt.get("archive_sha256")
            or not isinstance(receipt.get("checksum_file_sha256"), str)
            or _SHA256.fullmatch(receipt["checksum_file_sha256"]) is None
            or not isinstance(receipt.get("csv_sha256"), str)
            or _SHA256.fullmatch(receipt["csv_sha256"]) is None
            or not isinstance(receipt.get("source_etag_or_null"), (str, type(None)))
            or not isinstance(receipt.get("source_last_modified_at_or_null"), (str, type(None)))
        ):
            reasons.append("RECEIPT_CROSSLINK_MISMATCH")
        if not isinstance(snapshot.get("snapshot_id"), str) or _ID.fullmatch(snapshot["snapshot_id"]) is None:
            reasons.append("MARKET_DATA_SCHEMA_INVALID")
        facts = snapshot["facts"]
        if not isinstance(facts, list):
            raise TypeError("facts")
        expected_order = sorted(
            facts,
            key=lambda fact: (
                fact.get("event_time", ""),
                fact.get("source_row_number", -1),
                fact.get("fact_id", ""),
            ),
        )
        if facts != expected_order:
            reasons.append("MARKET_DATA_FACT_ORDER_INVALID")
        for fact in facts:
            if not isinstance(fact, Mapping):
                reasons.append("MARKET_DATA_FACT_INVALID")
                continue
            if fact.get("fact_id") != _archive_bound_fact_id(
                receipt["archive_sha256"],
                fact.get("source_row_fact_id", ""),
                fact.get("business_key", ""),
            ):
                reasons.append("ARCHIVE_FACT_ID_MISMATCH")
            try:
                replayed = _parse_one_fact(
                    request,
                    fact["source_row_number"],
                    fact["source_row"],
                    snapshot["ingested_at"],
                )
                replayed = _bind_fact_to_archive(
                    replayed,
                    receipt["archive_sha256"],
                )
                if replayed != dict(fact):
                    reasons.append("FACT_SOURCE_ROW_REPLAY_MISMATCH")
            except (KeyError, TypeError, MarketDataError, ValueError):
                reasons.append("FACT_SOURCE_ROW_REPLAY_MISMATCH")
        if receipt.get("source_rows_root_hash") != _source_rows_root_hash(facts):
            reasons.append("RECEIPT_SOURCE_ROWS_ROOT_MISMATCH")
        if receipt.get("facts_root_hash") != _facts_root_hash(facts):
            reasons.append("RECEIPT_FACTS_ROOT_MISMATCH")
        expected_report = _quality_report(
            request,
            sorted(facts, key=lambda fact: fact["source_row_number"]),
            snapshot["ingested_at"],
            snapshot["recorded_at"],
        )
        if report != expected_report:
            reasons.append("QUALITY_REPORT_REPLAY_MISMATCH")
        reasons.extend(expected_report["blocking_findings"])
        if report.get("blocking_findings"):
            reasons.append("MARKET_DATA_QUALITY_BLOCKING")
        retrieved, _ = _utc_input(snapshot["retrieved_at"])
        ingested, _ = _utc_input(snapshot["ingested_at"])
        recorded, _ = _utc_input(snapshot["recorded_at"])
        if retrieved > ingested or ingested > recorded:
            reasons.append("MARKET_DATA_TIME_ORDER")
    except (KeyError, TypeError, MarketDataError, ValueError, AttributeError):
        reasons.append("MARKET_DATA_SNAPSHOT_INVALID")
    return tuple(sorted(set(reasons)))


def _validated_verified_archive(
    verified_archive: object,
) -> Tuple[HistoricalArchiveRequest, bytes, bytes]:
    if not isinstance(verified_archive, _VerifiedArchive):
        raise MarketDataError("ARCHIVE_UNVERIFIED")
    request = verified_archive._request
    archive_bytes = verified_archive._archive_bytes
    checksum_bytes = verified_archive._checksum_bytes
    if (
        not isinstance(request, HistoricalArchiveRequest)
        or not isinstance(archive_bytes, bytes)
        or not isinstance(checksum_bytes, bytes)
    ):
        raise MarketDataError("ARCHIVE_UNVERIFIED")
    reverified = verify_official_checksum(request, archive_bytes, checksum_bytes)
    if (
        reverified._official_sha256 != verified_archive._official_sha256
        or reverified._archive_bytes != archive_bytes
        or reverified._checksum_bytes != checksum_bytes
    ):
        raise MarketDataError("ARCHIVE_UNVERIFIED")
    return request, archive_bytes, checksum_bytes


def _build_historical_market_data_snapshot(
    *,
    snapshot_id: str,
    verified_archive: _VerifiedArchive,
    retrieved_at: str,
    ingested_at: str,
    recorded_at: str,
    source_etag_or_null: Optional[str] = None,
    source_last_modified_at_or_null: Optional[str] = None,
    quality_eligibility: str,
) -> Dict[str, Any]:
    """Build a self-verifying, archive-only market-data artifact."""

    if (
        not isinstance(snapshot_id, str)
        or _ID.fullmatch(snapshot_id) is None
        or not isinstance(source_etag_or_null, (str, type(None)))
        or not isinstance(source_last_modified_at_or_null, (str, type(None)))
    ):
        raise MarketDataError("MARKET_DATA_QUALITY_BLOCKING")
    request, archive_bytes, checksum_bytes = _validated_verified_archive(
        verified_archive
    )
    try:
        retrieved, _ = _utc_input(retrieved_at)
        ingested, _ = _utc_input(ingested_at)
        recorded, _ = _utc_input(recorded_at)
    except MarketDataError as error:
        raise MarketDataError("MARKET_DATA_QUALITY_BLOCKING") from error
    if retrieved > ingested or ingested > recorded:
        raise MarketDataError("MARKET_DATA_QUALITY_BLOCKING")
    csv_bytes = extract_expected_csv(request, verified_archive)
    parsed_facts = parse_market_facts(request, csv_bytes, ingested_at)
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    archive_bound_facts = sorted(
        (
            _bind_fact_to_archive(fact, archive_sha256)
            for fact in parsed_facts
        ),
        key=lambda fact: (
            fact["event_time"],
            fact["source_row_number"],
            fact["fact_id"],
        ),
    )
    report = _quality_report(
        request,
        parsed_facts,
        ingested_at,
        recorded_at,
    )
    degraded_allowed_findings = {
        "MARKET_DATA_PERIOD_COVERAGE",
        "MARKET_DATA_FUNDING_GAP",
    }
    if (
        quality_eligibility == "FORMAL_COMPLETE"
        and report["blocking_findings"]
    ):
        raise MarketDataError("MARKET_DATA_QUALITY_BLOCKING")
    if (
        quality_eligibility == "RESEARCH_ONLY_DEGRADED"
        and set(report["blocking_findings"]) - degraded_allowed_findings
    ):
        raise MarketDataError("MARKET_DATA_QUALITY_BLOCKING")
    if quality_eligibility not in (
        "FORMAL_COMPLETE",
        "RESEARCH_ONLY_DEGRADED",
    ):
        raise MarketDataError("MARKET_DATA_QUALITY_BLOCKING")
    receipt = {
        "request": _request_payload(request),
        "archive_url": request.archive_url,
        "checksum_url": request.checksum_url,
        "retrieved_at": retrieved_at,
        "archive_size_bytes": len(archive_bytes),
        "checksum_size_bytes": len(checksum_bytes),
        "official_sha256": verified_archive._official_sha256,
        "archive_sha256": archive_sha256,
        "checksum_file_sha256": hashlib.sha256(checksum_bytes).hexdigest(),
        "csv_member": request.expected_csv_name,
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "source_rows_root_hash": _source_rows_root_hash(archive_bound_facts),
        "facts_root_hash": _facts_root_hash(archive_bound_facts),
        "source_etag_or_null": source_etag_or_null,
        "source_last_modified_at_or_null": source_last_modified_at_or_null,
        "receipt_hash": "0" * 64,
    }
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    snapshot = {
        "$schema": "./historical-market-data-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": snapshot_id,
        "snapshot_hash": "0" * 64,
        "hash_algorithm": "SHA-256",
        "canonicalization": "RFC8785_JCS",
        "parser_version": _PARSER_VERSION,
        "availability_basis": _AVAILABILITY_BASIS,
        "pit_eligibility": "ARCHIVE_REPLAY_ONLY",
        "quality_eligibility": quality_eligibility,
        "request": _request_payload(request),
        "source_receipt": receipt,
        "quality_report": report,
        "facts": archive_bound_facts,
        "retrieved_at": retrieved_at,
        "ingested_at": ingested_at,
        "recorded_at": recorded_at,
    }
    snapshot["snapshot_hash"] = historical_market_data_snapshot_hash(snapshot)
    snapshot_attestation_hash = historical_market_data_snapshot_attestation_hash(
        snapshot
    )
    reasons = historical_market_data_snapshot_reasons(
        snapshot,
        trusted_snapshot_attestation_hashes={snapshot_attestation_hash},
    )
    allowed_degraded_reasons = set(report["blocking_findings"]) | {
        "MARKET_DATA_QUALITY_BLOCKING",
        "MARKET_DATA_RESEARCH_ONLY_DEGRADED",
    }
    if (
        quality_eligibility == "FORMAL_COMPLETE"
        and reasons
    ) or (
        quality_eligibility == "RESEARCH_ONLY_DEGRADED"
        and set(reasons) - allowed_degraded_reasons
    ):
        raise MarketDataError("MARKET_DATA_QUALITY_BLOCKING")
    return snapshot


def build_historical_market_data_snapshot(
    *,
    snapshot_id: str,
    verified_archive: _VerifiedArchive,
    retrieved_at: str,
    ingested_at: str,
    recorded_at: str,
    source_etag_or_null: Optional[str] = None,
    source_last_modified_at_or_null: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a strict complete snapshot from a verified archive capability."""

    return _build_historical_market_data_snapshot(
        snapshot_id=snapshot_id,
        verified_archive=verified_archive,
        retrieved_at=retrieved_at,
        ingested_at=ingested_at,
        recorded_at=recorded_at,
        source_etag_or_null=source_etag_or_null,
        source_last_modified_at_or_null=source_last_modified_at_or_null,
        quality_eligibility="FORMAL_COMPLETE",
    )


def build_research_degraded_historical_market_data_snapshot(
    *,
    snapshot_id: str,
    verified_archive: _VerifiedArchive,
    retrieved_at: str,
    ingested_at: str,
    recorded_at: str,
    source_etag_or_null: Optional[str] = None,
    source_last_modified_at_or_null: Optional[str] = None,
) -> Dict[str, Any]:
    """Preserve valid-but-gapped rows for research without formal eligibility."""

    return _build_historical_market_data_snapshot(
        snapshot_id=snapshot_id,
        verified_archive=verified_archive,
        retrieved_at=retrieved_at,
        ingested_at=ingested_at,
        recorded_at=recorded_at,
        source_etag_or_null=source_etag_or_null,
        source_last_modified_at_or_null=source_last_modified_at_or_null,
        quality_eligibility="RESEARCH_ONLY_DEGRADED",
    )


def fee_schedule_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    """Return the independent Fee Schedule self-hash."""

    return artifact_self_hash(snapshot, "content_hash")


def _approved(approval: Any) -> bool:
    if (
        not isinstance(approval, Mapping)
        or set(approval)
        != {"approved_by", "approved_at", "approval_reference"}
        or not isinstance(approval.get("approved_by"), str)
        or not isinstance(approval.get("approval_reference"), str)
    ):
        return False
    if (
        _ID.fullmatch(approval["approved_by"]) is None
        or not approval["approval_reference"]
    ):
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
    if not _schema_valid("fee-schedule-snapshot-v1.schema.json", snapshot):
        reasons.append("FEE_SCHEDULE_INVALID")
    if snapshot.get("$schema") != "./fee-schedule-snapshot-v1.schema.json" or snapshot.get("schema_version") != "1.0.0":
        reasons.append("FEE_SCHEDULE_INVALID")
    try:
        allowed_snapshot_fields = {
            "$schema", "schema_version", "fee_schedule_id", "content_hash",
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
        if snapshot.get("content_hash") != fee_schedule_snapshot_hash(snapshot):
            reasons.append("FEE_SCHEDULE_HASH_MISMATCH")
        schedules = snapshot["schedules"]
        if not isinstance(schedules, list) or not schedules:
            raise ValueError("schedules")
        grouped: Dict[Tuple[Any, Any, Any, Any], list] = {}
        for item in schedules:
            required_fields = {
                "fee_id",
                "venue",
                "product",
                "account_tier",
                "symbol",
                "maker_rate",
                "taker_rate",
                "effective_from",
                "effective_to_or_null",
                "source_reference",
                "recorded_at",
                "lifecycle",
                "approval",
            }
            if not isinstance(item, Mapping) or set(item) != required_fields:
                raise ValueError("schedule")
            if (
                not isinstance(item["fee_id"], str)
                or _ID.fullmatch(item["fee_id"]) is None
                or item["venue"] != "BINANCE"
                or item["product"] not in ("SPOT", "USD_M_PERPETUAL")
                or not isinstance(item["account_tier"], str)
                or _ID.fullmatch(item["account_tier"]) is None
                or item["symbol"] not in _ALLOWED_SYMBOLS
                or not isinstance(item["source_reference"], str)
                or not item["source_reference"]
            ):
                reasons.append("FEE_SCHEDULE_INVALID")
            start, _ = _utc_input(item["effective_from"])
            end = None
            if item.get("effective_to_or_null") is not None:
                end, _ = _utc_input(item["effective_to_or_null"])
                if end <= start:
                    reasons.append("FEE_SCHEDULE_EFFECTIVE_INTERVAL_INVALID")
            _utc_input(item["recorded_at"])
            for rate in (item.get("maker_rate"), item.get("taker_rate")):
                try:
                    rendered = _decimal(rate)
                    if Decimal(rendered) < 0 or rendered != rate:
                        reasons.append("FEE_SCHEDULE_INVALID_DECIMAL")
                except MarketDataError:
                    reasons.append("FEE_SCHEDULE_INVALID_DECIMAL")
            lifecycle = item.get("lifecycle")
            if lifecycle not in ("DRAFT", "APPROVED", "RETIRED"):
                reasons.append("FEE_SCHEDULE_LIFECYCLE_INVALID")
            approval = item.get("approval")
            if lifecycle == "DRAFT" and approval is not None:
                reasons.append("FEE_SCHEDULE_APPROVAL_INVALID")
            elif lifecycle in ("APPROVED", "RETIRED") and not _approved(approval):
                reasons.append("FEE_SCHEDULE_APPROVAL_INVALID")
            grouped.setdefault(
                (
                    item.get("venue"),
                    item.get("product"),
                    item.get("account_tier"),
                    item.get("symbol"),
                ),
                [],
            ).append((start, end))
        for intervals in grouped.values():
            intervals.sort(key=lambda value: value[0])
            for (_, previous_end), (current_start, _) in zip(intervals, intervals[1:]):
                if previous_end is None or current_start < previous_end:
                    reasons.append("FEE_SCHEDULE_EFFECTIVE_INTERVAL_OVERLAP")
        if snapshot.get("usage_environment") == "PRODUCTION":
            reasons.append("FEE_SCHEDULE_PRODUCTION_UNSUPPORTED")
    except (KeyError, TypeError, ValueError, MarketDataError):
        reasons.append("FEE_SCHEDULE_INVALID")
    return tuple(sorted(set(reasons)))
