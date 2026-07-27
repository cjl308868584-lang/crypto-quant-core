"""Compact, checksum-bound 1m execution sources for archive research."""

import csv
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib import resources
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import (
    business_hash,
    canonical_decimal,
    canonical_json,
    stable_id,
    utc_datetime,
)
from .evidence import artifact_self_hash
from .market_data import (
    HistoricalArchiveRequest,
    MarketDataError,
    PublicArchiveTransport,
    extract_expected_csv,
    verify_official_checksum,
)
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "historical-execution-source-v1.schema.json"
_ZERO_HASH = "0" * 64
_MINUTE = timedelta(minutes=1)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MICROSECOND_BOUNDARY = datetime(2025, 1, 1, tzinfo=timezone.utc)
_LEGACY_HEADER = (
    "open time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close time",
    "quote asset volume",
    "number of trades",
    "taker buy base asset volume",
    "taker buy quote asset volume",
    "ignore",
)
_OFFICIAL_HEADER = (
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
)
_WARNINGS = (
    "ARCHIVE_REPLAY_IS_NOT_POINT_IN_TIME_EVIDENCE",
    "SELECTED_MINUTE_BARS_ARE_EXECUTION_PROXIES_NOT_REAL_FILLS",
    "DAILY_REPAIRS_PRESERVE_MONTHLY_SOURCE_GAPS_EXPLICITLY",
    "UNREPAIRED_SOURCE_GAPS_ARE_ALLOWED_ONLY_OUTSIDE_REQUIRED_MINUTES",
    "NO_PROFITABILITY_CLAIM",
)


class ResearchExecutionError(ValueError):
    """The compact source or its publication failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _utc(value: object) -> Tuple[datetime, str]:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ResearchExecutionError("EXECUTION_SOURCE_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ResearchExecutionError("EXECUTION_SOURCE_TIME_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ResearchExecutionError("EXECUTION_SOURCE_TIME_INVALID")
    rendered = utc_datetime(parsed)
    if rendered != value:
        raise ResearchExecutionError("EXECUTION_SOURCE_TIME_INVALID")
    return parsed, rendered


def _month_bounds(period: str) -> Tuple[datetime, datetime]:
    try:
        start = datetime.strptime(period, "%Y-%m").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as error:
        raise ResearchExecutionError("EXECUTION_SOURCE_PERIOD_INVALID") from error
    if start < datetime(2023, 1, 1, tzinfo=timezone.utc) or start >= datetime(
        2026, 7, 1, tzinfo=timezone.utc
    ):
        raise ResearchExecutionError("EXECUTION_SOURCE_PERIOD_INVALID")
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, end


def _request(period: str) -> HistoricalArchiveRequest:
    _month_bounds(period)
    return HistoricalArchiveRequest.create(
        market="SPOT",
        data_family="KLINES",
        symbol="ETHUSDT",
        interval_or_null="1m",
        period_kind="MONTHLY",
        period=period,
    )


def _daily_request(period: str) -> HistoricalArchiveRequest:
    try:
        parsed = datetime.strptime(period, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except (TypeError, ValueError) as error:
        raise ResearchExecutionError("EXECUTION_SOURCE_PERIOD_INVALID") from error
    start, end = _month_bounds(period[:7])
    if not start <= parsed < end:
        raise ResearchExecutionError("EXECUTION_SOURCE_PERIOD_INVALID")
    return HistoricalArchiveRequest.create(
        market="SPOT",
        data_family="KLINES",
        symbol="ETHUSDT",
        interval_or_null="1m",
        period_kind="DAILY",
        period=period,
    )


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
        "archive_filename": request.archive_filename,
        "checksum_filename": request.archive_filename + ".CHECKSUM",
    }


def _raw_timestamp(value: str, *, microseconds: bool) -> datetime:
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise ResearchExecutionError("EXECUTION_SOURCE_ROW_INVALID")
    try:
        raw = int(value)
        delta = (
            timedelta(microseconds=raw)
            if microseconds
            else timedelta(milliseconds=raw)
        )
        result = _EPOCH + delta
    except (OverflowError, ValueError) as error:
        raise ResearchExecutionError("EXECUTION_SOURCE_ROW_INVALID") from error
    return result


def _decimal(value: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value.isascii():
        raise ResearchExecutionError("EXECUTION_SOURCE_ROW_INVALID")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ResearchExecutionError("EXECUTION_SOURCE_ROW_INVALID") from error
    if not parsed.is_finite() or (positive and parsed <= 0) or parsed < 0:
        raise ResearchExecutionError("EXECUTION_SOURCE_ROW_INVALID")
    return parsed


def _selected_row(
    row: Sequence[str],
    *,
    row_number: int,
    open_time: datetime,
) -> Dict[str, Any]:
    opened = _decimal(row[1], positive=True)
    high = _decimal(row[2], positive=True)
    low = _decimal(row[3], positive=True)
    close = _decimal(row[4], positive=True)
    volume = _decimal(row[5])
    quote = _decimal(row[7])
    taker_base = _decimal(row[9])
    taker_quote = _decimal(row[10])
    if (
        high < max(opened, close)
        or low > min(opened, close)
        or low > high
        or taker_base > volume
        or taker_quote > quote
        or not row[8].isascii()
        or not row[8].isdigit()
    ):
        raise ResearchExecutionError("EXECUTION_SOURCE_ROW_INVALID")
    raw = list(row)
    return {
        "open_time": utc_datetime(open_time),
        "open": canonical_decimal(opened),
        "high": canonical_decimal(high),
        "low": canonical_decimal(low),
        "close": canonical_decimal(close),
        "source_row_number": row_number,
        "source_row": raw,
        "source_row_hash": business_hash(raw),
    }


def _archive_rows(
    *,
    request: HistoricalArchiveRequest,
    archive_bytes: bytes,
    checksum_bytes: bytes,
    start: datetime,
    end: datetime,
) -> Tuple[
    bytes,
    Dict[datetime, Dict[str, Any]],
    Sequence[str],
    Sequence[datetime],
]:
    if not isinstance(archive_bytes, bytes) or not isinstance(
        checksum_bytes, bytes
    ):
        raise ResearchExecutionError("EXECUTION_SOURCE_BYTES_INVALID")
    try:
        verified = verify_official_checksum(
            request,
            archive_bytes,
            checksum_bytes,
        )
        csv_bytes = extract_expected_csv(request, verified)
        text = csv_bytes.decode("ascii")
    except (MarketDataError, UnicodeDecodeError) as error:
        raise ResearchExecutionError("EXECUTION_SOURCE_ARCHIVE_INVALID") from error
    rows = list(csv.reader(StringIO(text, newline="")))
    if rows and tuple(rows[0]) in (_LEGACY_HEADER, _OFFICIAL_HEADER):
        rows = rows[1:]
        first_row_number = 2
    else:
        first_row_number = 1
    microseconds = start >= _MICROSECOND_BOUNDARY
    parsed_rows = {}
    row_hashes = []
    excluded_times = set()
    previous = None
    for offset, row in enumerate(rows):
        if len(row) != 12:
            raise ResearchExecutionError("EXECUTION_SOURCE_ROW_INVALID")
        opened_at = _raw_timestamp(row[0], microseconds=microseconds)
        closed_at = _raw_timestamp(row[6], microseconds=microseconds)
        expected_close = opened_at + _MINUTE - (
            timedelta(microseconds=1)
            if microseconds
            else timedelta(milliseconds=1)
        )
        if (
            not start <= opened_at < end
            or opened_at.second
            or opened_at.microsecond
            or (previous is not None and opened_at <= previous)
            or opened_at in parsed_rows
        ):
            raise ResearchExecutionError("EXECUTION_SOURCE_COVERAGE_INVALID")
        normalized = _selected_row(
            row,
            row_number=first_row_number + offset,
            open_time=opened_at,
        )
        if closed_at != expected_close:
            excluded_times.add(opened_at)
            previous = opened_at
            continue
        parsed_rows[opened_at] = normalized
        row_hashes.append(normalized["source_row_hash"])
        previous = opened_at
    return csv_bytes, parsed_rows, row_hashes, excluded_times


def execution_source_hash(snapshot: Mapping[str, Any]) -> str:
    return artifact_self_hash(snapshot, "source_hash")


def execution_source_missing_days(
    *,
    period: str,
    archive_bytes: bytes,
    checksum_bytes: bytes,
) -> Tuple[str, ...]:
    request = _request(period)
    start, end = _month_bounds(period)
    _, rows, _, excluded_times = _archive_rows(
        request=request,
        archive_bytes=archive_bytes,
        checksum_bytes=checksum_bytes,
        start=start,
        end=end,
    )
    missing_days = set()
    cursor = start
    while cursor < end:
        if cursor not in rows or cursor in excluded_times:
            missing_days.add(cursor.strftime("%Y-%m-%d"))
        cursor += _MINUTE
    return tuple(sorted(missing_days))


def build_execution_source(
    *,
    period: str,
    archive_bytes: bytes,
    checksum_bytes: bytes,
    required_open_times: Sequence[str],
    retrieved_at: str,
    daily_repair_archives: Optional[
        Mapping[str, Tuple[bytes, bytes]]
    ] = None,
) -> Dict[str, Any]:
    """Verify a month plus exact official daily gap repairs."""

    request = _request(period)
    _, retrieved_text = _utc(retrieved_at)
    required = []
    for value in required_open_times:
        parsed, rendered = _utc(value)
        if (
            parsed.second
            or parsed.microsecond
            or parsed.strftime("%Y-%m") != period
        ):
            raise ResearchExecutionError(
                "EXECUTION_SOURCE_REQUIRED_TIME_INVALID"
            )
        required.append(rendered)
    if tuple(sorted(set(required))) != tuple(required):
        raise ResearchExecutionError("EXECUTION_SOURCE_REQUIRED_TIME_INVALID")
    start, end = _month_bounds(period)
    expected_count = int((end - start) / _MINUTE)
    csv_bytes, monthly_rows, _, monthly_excluded = _archive_rows(
        request=request,
        archive_bytes=archive_bytes,
        checksum_bytes=checksum_bytes,
        start=start,
        end=end,
    )
    expected_times = set()
    cursor = start
    while cursor < end:
        expected_times.add(cursor)
        cursor += _MINUTE
    if set(monthly_rows) - expected_times:
        raise ResearchExecutionError("EXECUTION_SOURCE_COVERAGE_INVALID")
    missing = expected_times - set(monthly_rows)
    missing_days = {value.strftime("%Y-%m-%d") for value in missing}
    repair_inputs = dict(daily_repair_archives or {})
    if not set(repair_inputs).issubset(missing_days):
        raise ResearchExecutionError("EXECUTION_SOURCE_REPAIR_SET_INVALID")
    combined = dict(monthly_rows)
    daily_repairs = []
    for day in sorted(repair_inputs):
        repair_request = _daily_request(day)
        repair_archive, repair_checksum = repair_inputs[day]
        day_start = datetime.strptime(day, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        day_end = day_start + timedelta(days=1)
        repair_csv, daily_rows, _, repair_excluded = _archive_rows(
            request=repair_request,
            archive_bytes=repair_archive,
            checksum_bytes=repair_checksum,
            start=day_start,
            end=day_end,
        )
        if len(daily_rows) != 1440 or repair_excluded:
            raise ResearchExecutionError("EXECUTION_SOURCE_REPAIR_INVALID")
        for open_time, row in daily_rows.items():
            if (
                open_time in monthly_rows
                and monthly_rows[open_time]["source_row_hash"]
                != row["source_row_hash"]
            ):
                raise ResearchExecutionError(
                    "EXECUTION_SOURCE_REPAIR_OVERLAP_MISMATCH"
                )
        added_times = sorted(
            open_time for open_time in missing if open_time in daily_rows
        )
        if not added_times or {
            value for value in missing if value.strftime("%Y-%m-%d") == day
        } != set(added_times):
            raise ResearchExecutionError("EXECUTION_SOURCE_REPAIR_INVALID")
        for open_time in added_times:
            combined[open_time] = daily_rows[open_time]
        daily_repairs.append(
            {
                "period": day,
                "archive_filename": repair_request.archive_filename,
                "checksum_filename": repair_request.archive_filename
                + ".CHECKSUM",
                "archive_sha256": hashlib.sha256(repair_archive).hexdigest(),
                "checksum_file_sha256": hashlib.sha256(
                    repair_checksum
                ).hexdigest(),
                "csv_sha256": hashlib.sha256(repair_csv).hexdigest(),
                "csv_row_count": len(daily_rows),
                "added_row_count": len(added_times),
                "added_open_times_root_hash": business_hash(
                    [utc_datetime(value) for value in added_times]
                ),
            }
        )
    unresolved = sorted(expected_times - set(combined))
    required_parsed = {_utc(value)[0] for value in required}
    if required_parsed & set(unresolved):
        raise ResearchExecutionError("EXECUTION_SOURCE_REQUIRED_ROWS_MISSING")
    selected = [
        combined[_utc(value)[0]]
        for value in required
        if _utc(value)[0] in combined
    ]
    if [row["open_time"] for row in selected] != required:
        raise ResearchExecutionError("EXECUTION_SOURCE_REQUIRED_ROWS_MISSING")
    row_hashes = [
        combined[value]["source_row_hash"] for value in sorted(combined)
    ]
    selected_root = business_hash(
        [
            {
                "open_time": row["open_time"],
                "source_row_hash": row["source_row_hash"],
            }
            for row in selected
        ]
    )
    identity = {
        "request": _request_payload(request),
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "daily_repair_archive_sha256": [
            repair["archive_sha256"] for repair in daily_repairs
        ],
        "source_gap_open_times": [
            utc_datetime(value) for value in unresolved
        ],
        "required_open_times": required,
        "selected_open_times_root_hash": selected_root,
    }
    snapshot = {
        "$schema": "./historical-execution-source-v1.schema.json",
        "schema_version": "1.0.0",
        "source_id": stable_id("execution_source", identity),
        "source_hash": _ZERO_HASH,
        "request": _request_payload(request),
        "retrieved_at": retrieved_text,
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "checksum_file_sha256": hashlib.sha256(checksum_bytes).hexdigest(),
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "source_rows_root_hash": business_hash(row_hashes),
        "monthly_csv_row_count": len(monthly_rows) + len(monthly_excluded),
        "csv_row_count": len(combined),
        "expected_row_count": expected_count,
        "source_gap_count": len(unresolved),
        "source_gap_open_times_root_hash": business_hash(
            [utc_datetime(value) for value in unresolved]
        ),
        "source_gap_open_times": [
            utc_datetime(value) for value in unresolved
        ],
        "first_open_time": utc_datetime(start),
        "last_open_time": utc_datetime(end - _MINUTE),
        "required_open_times": required,
        "selected_open_times_root_hash": selected_root,
        "selected_rows": selected,
        "daily_repairs": daily_repairs,
        "quality_eligibility": (
            "RESEARCH_REQUIRED_ROWS_COMPLETE_WITH_SOURCE_GAPS"
            if unresolved
            else (
                "FORMAL_COMPLETE_WITH_EXPLICIT_DAILY_REPAIRS"
                if daily_repairs
                else "FORMAL_COMPLETE"
            )
        ),
        "formal_pit_eligibility": "INELIGIBLE_ARCHIVE_REPLAY",
        "warnings": list(_WARNINGS),
    }
    snapshot["source_hash"] = execution_source_hash(snapshot)
    if tuple(_validator().iter_errors(snapshot)):
        raise ResearchExecutionError("EXECUTION_SOURCE_SCHEMA_INVALID")
    return snapshot


def execution_source_reasons(
    snapshot: Mapping[str, Any],
    *,
    archive_bytes: bytes,
    checksum_bytes: bytes,
    daily_repair_archives: Optional[
        Mapping[str, Tuple[bytes, bytes]]
    ] = None,
) -> Tuple[str, ...]:
    reasons = []
    if not isinstance(snapshot, Mapping):
        return ("EXECUTION_SOURCE_INVALID",)
    try:
        if tuple(_validator().iter_errors(snapshot)):
            reasons.append("EXECUTION_SOURCE_SCHEMA_INVALID")
        if snapshot.get("source_hash") != execution_source_hash(snapshot):
            reasons.append("EXECUTION_SOURCE_HASH_MISMATCH")
        rebuilt = build_execution_source(
            period=snapshot["request"]["period"],
            archive_bytes=archive_bytes,
            checksum_bytes=checksum_bytes,
            required_open_times=snapshot["required_open_times"],
            retrieved_at=snapshot["retrieved_at"],
            daily_repair_archives=daily_repair_archives,
        )
        if business_hash(rebuilt) != business_hash(snapshot):
            reasons.append("EXECUTION_SOURCE_SEMANTIC_MISMATCH")
    except (
        KeyError,
        TypeError,
        ValueError,
        ResearchExecutionError,
    ):
        reasons.append("EXECUTION_SOURCE_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def fetch_execution_source(
    *,
    period: str,
    required_open_times: Sequence[str],
    retrieved_at: str,
    transport: PublicArchiveTransport,
) -> Tuple[
    Dict[str, Any],
    bytes,
    bytes,
    Mapping[str, Tuple[bytes, bytes]],
]:
    request = _request(period)
    if not hasattr(transport, "get"):
        raise ResearchExecutionError("EXECUTION_SOURCE_TRANSPORT_INVALID")
    archive_response = transport.get(request.archive_url)
    checksum_response = transport.get(request.checksum_url)
    for response, expected_url in (
        (archive_response, request.archive_url),
        (checksum_response, request.checksum_url),
    ):
        if (
            getattr(response, "status", None) != 200
            or getattr(response, "final_url", None) != expected_url
            or not isinstance(getattr(response, "body", None), bytes)
        ):
            raise ResearchExecutionError("EXECUTION_SOURCE_HTTP_INVALID")
    archive_bytes = archive_response.body
    checksum_bytes = checksum_response.body
    repair_archives = {}
    snapshot = build_execution_source(
        period=period,
        archive_bytes=archive_bytes,
        checksum_bytes=checksum_bytes,
        required_open_times=required_open_times,
        retrieved_at=retrieved_at,
        daily_repair_archives=repair_archives,
    )
    return snapshot, archive_bytes, checksum_bytes, repair_archives


def publish_execution_source(
    *,
    snapshot: Mapping[str, Any],
    archive_bytes: bytes,
    checksum_bytes: bytes,
    daily_repair_archives: Optional[
        Mapping[str, Tuple[bytes, bytes]]
    ] = None,
    output_root: Path,
) -> None:
    if execution_source_reasons(
        snapshot,
        archive_bytes=archive_bytes,
        checksum_bytes=checksum_bytes,
        daily_repair_archives=daily_repair_archives,
    ):
        raise ResearchExecutionError("EXECUTION_SOURCE_INVALID")
    root = Path(output_root).expanduser().resolve()
    period = snapshot["request"]["period"]
    period_root = root / period
    repair_root = period_root / "repairs"
    directories = [root, period_root]
    if snapshot["daily_repairs"]:
        directories.append(repair_root)
    for directory in directories:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    _publish_exact(
        period_root / snapshot["request"]["archive_filename"],
        archive_bytes,
    )
    _publish_exact(
        period_root / snapshot["request"]["checksum_filename"],
        checksum_bytes,
    )
    repair_inputs = dict(daily_repair_archives or {})
    for repair in snapshot["daily_repairs"]:
        repair_archive, repair_checksum = repair_inputs[repair["period"]]
        _publish_exact(
            repair_root / repair["archive_filename"],
            repair_archive,
        )
        _publish_exact(
            repair_root / repair["checksum_filename"],
            repair_checksum,
        )
    _publish_exact(
        period_root / "source.json",
        canonical_json(snapshot).encode("utf-8"),
    )


def load_execution_source(
    *,
    period: str,
    output_root: Path,
) -> Tuple[
    Mapping[str, Any],
    bytes,
    bytes,
    Mapping[str, Tuple[bytes, bytes]],
]:
    root = Path(output_root).expanduser().resolve() / period
    try:
        snapshot = _strict_json_bytes((root / "source.json").read_bytes())
        request = snapshot["request"]
        archive_bytes = (root / request["archive_filename"]).read_bytes()
        checksum_bytes = (root / request["checksum_filename"]).read_bytes()
        repair_archives = {
            repair["period"]: (
                (root / "repairs" / repair["archive_filename"]).read_bytes(),
                (
                    root / "repairs" / repair["checksum_filename"]
                ).read_bytes(),
            )
            for repair in snapshot["daily_repairs"]
        }
    except (KeyError, OSError, TypeError) as error:
        raise ResearchExecutionError("EXECUTION_SOURCE_READ_FAILED") from error
    reasons = execution_source_reasons(
        snapshot,
        archive_bytes=archive_bytes,
        checksum_bytes=checksum_bytes,
        daily_repair_archives=repair_archives,
    )
    if reasons:
        raise ResearchExecutionError(reasons[0])
    return snapshot, archive_bytes, checksum_bytes, repair_archives
