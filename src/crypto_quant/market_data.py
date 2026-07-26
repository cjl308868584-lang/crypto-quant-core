"""Fail-closed boundary for Binance public historical archives."""

import hashlib
import hmac
import re
import stat
import zipfile
from io import BytesIO
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Optional


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
