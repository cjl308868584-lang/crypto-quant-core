"""Recoverable, archive-only research corpus acquisition.

The corpus is deliberately ineligible for formal PIT/OOS or profitability
claims.  It plans and verifies public Binance monthly archives so later model
research has a complete, reproducible development input.
"""

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .market_data import (
    HistoricalArchiveRequest,
    MarketDataError,
    PublicArchiveTransport,
    fetch_historical_market_data,
    historical_market_data_snapshot_attestation_hash,
    historical_market_data_snapshot_reasons,
)


_PLAN_SCHEMA = "historical-research-corpus-plan-v1.schema.json"
_SNAPSHOT_SCHEMA = "historical-research-corpus-snapshot-v1.schema.json"
_PLAN_ID = "historical-research-corpus-202301-202606"
_CORPUS_START = datetime(2023, 1, 1, tzinfo=timezone.utc)
_CORPUS_END = datetime(2026, 7, 1, tzinfo=timezone.utc)
_OOS_START = datetime(2024, 7, 1, tzinfo=timezone.utc)
_OOS_END = datetime(2026, 7, 1, tzinfo=timezone.utc)
_LEASE_DURATION = timedelta(minutes=15)
_MAX_ITEMS_PER_RUN = 16
_ZERO_HASH = "0" * 64
_WORKER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_EVENT_TYPES = frozenset(("CLAIMED", "SUCCEEDED", "FAILED"))
_STREAMS = (
    (
        "ETH_SPOT_4H",
        {
            "market": "SPOT",
            "data_family": "KLINES",
            "symbol": "ETHUSDT",
            "interval_or_null": "4h",
        },
        "BASE_PROPOSAL_AND_PRICE_VOLUME_FEATURES",
    ),
    (
        "BTC_CONTEXT_4H",
        {
            "market": "SPOT",
            "data_family": "KLINES",
            "symbol": "BTCUSDT",
            "interval_or_null": "4h",
        },
        "CONTEXT_ONLY_NO_BTC_ORDERS",
    ),
    (
        "ETH_MARK_4H",
        {
            "market": "USD_M",
            "data_family": "MARK_PRICE_KLINES",
            "symbol": "ETHUSDT",
            "interval_or_null": "4h",
        },
        "PERPETUAL_MARK_AND_BASIS_RESEARCH",
    ),
    (
        "ETH_FUNDING",
        {
            "market": "USD_M",
            "data_family": "FUNDING_RATE",
            "symbol": "ETHUSDT",
            "interval_or_null": None,
        },
        "FUNDING_CONTEXT_RESEARCH",
    ),
)
_WARNINGS = (
    "ARCHIVE_REPLAY_IS_NOT_POINT_IN_TIME_EVIDENCE",
    "NO_EXECUTION_LABELS_OR_REAL_FILLS",
    "NO_MODEL_TRAINED_OR_APPROVED",
    "NO_PROFITABILITY_CLAIM",
)


class ResearchCorpusError(ValueError):
    """The plan, durable state, source artifact, or publication failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=2)
def _validator(filename: str) -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", filename)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _utc(value: object) -> Tuple[datetime, str]:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ResearchCorpusError("CORPUS_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ResearchCorpusError("CORPUS_TIME_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ResearchCorpusError("CORPUS_TIME_INVALID")
    rendered = utc_datetime(parsed)
    if rendered != value:
        raise ResearchCorpusError("CORPUS_TIME_INVALID")
    return parsed, rendered


def _month_start(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )


def _add_months(value: datetime, count: int) -> datetime:
    absolute = value.year * 12 + value.month - 1 + count
    year, month_index = divmod(absolute, 12)
    return value.replace(year=year, month=month_index + 1)


def _months(start: datetime, end: datetime) -> Tuple[str, ...]:
    if start != _month_start(start) or end != _month_start(end) or start >= end:
        raise ResearchCorpusError("CORPUS_WINDOW_INVALID")
    values = []
    cursor = start
    while cursor < end:
        values.append(cursor.strftime("%Y-%m"))
        cursor = _add_months(cursor, 1)
    return tuple(values)


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


def _request_from_payload(payload: Mapping[str, Any]) -> HistoricalArchiveRequest:
    if not isinstance(payload, Mapping):
        raise ResearchCorpusError("CORPUS_REQUEST_INVALID")
    try:
        if (
            payload.get("schema_version") != "1.0.0"
            or payload.get("provider") != "BINANCE_PUBLIC_DATA"
        ):
            raise ResearchCorpusError("CORPUS_REQUEST_INVALID")
        return HistoricalArchiveRequest.create(
            market=payload["market"],
            data_family=payload["data_family"],
            symbol=payload["symbol"],
            interval_or_null=payload["interval_or_null"],
            period_kind=payload["period_kind"],
            period=payload["period"],
        )
    except (KeyError, MarketDataError) as error:
        raise ResearchCorpusError("CORPUS_REQUEST_INVALID") from error


def _folds() -> Tuple[Dict[str, Any], ...]:
    folds = []
    oos_start = _OOS_START
    index = 1
    while oos_start < _OOS_END:
        oos_end = _add_months(oos_start, 3)
        training_start = _add_months(oos_start, -18)
        calibration_start = _add_months(oos_start, -1)
        identity = {
            "index": index,
            "training_start": utc_datetime(training_start),
            "oos_start": utc_datetime(oos_start),
            "oos_end_exclusive": utc_datetime(oos_end),
        }
        folds.append(
            {
                "fold_id": stable_id("research_fold", identity),
                "fold_index": index,
                "training_window_start": utc_datetime(training_start),
                "training_window_end_exclusive": utc_datetime(oos_start),
                "fit_window_start": utc_datetime(training_start),
                "fit_window_end_exclusive": utc_datetime(calibration_start),
                "calibration_window_start": utc_datetime(calibration_start),
                "calibration_window_end_exclusive": utc_datetime(oos_start),
                "purge_duration_hours": 24,
                "embargo_duration_hours": 24,
                "oos_window_start": utc_datetime(oos_start),
                "oos_window_end_exclusive": utc_datetime(oos_end),
                "eligibility": "RESEARCH_ARCHIVE_FOLD",
            }
        )
        oos_start = oos_end
        index += 1
    return tuple(folds)


def research_corpus_plan_hash(plan: Mapping[str, Any]) -> str:
    return artifact_self_hash(plan, "plan_hash")


def build_default_research_corpus_plan() -> Dict[str, Any]:
    """Build the one frozen 42-month development corpus plan."""

    month_values = _months(_CORPUS_START, _CORPUS_END)
    streams = []
    for stream_id, request_fields, purpose in _STREAMS:
        streams.append(
            {
                "stream_id": stream_id,
                **request_fields,
                "purpose": purpose,
            }
        )
    items = []
    for month in month_values:
        for stream_id, request_fields, _ in _STREAMS:
            request = HistoricalArchiveRequest.create(
                **request_fields,
                period_kind="MONTHLY",
                period=month,
            )
            payload = _request_payload(request)
            identity = {
                "plan_id": _PLAN_ID,
                "stream_id": stream_id,
                "month": month,
                "request": payload,
            }
            items.append(
                {
                    "corpus_item_id": stable_id("corpus_item", identity),
                    "stream_id": stream_id,
                    "month": month,
                    "request": payload,
                    "request_hash": business_hash(payload),
                }
            )
    requests_root = business_hash(items)
    plan = {
        "$schema": "./historical-research-corpus-plan-v1.schema.json",
        "schema_version": "1.0.0",
        "plan_id": _PLAN_ID,
        "plan_hash": _ZERO_HASH,
        "provider": "BINANCE_PUBLIC_DATA",
        "corpus_start": utc_datetime(_CORPUS_START),
        "corpus_end_exclusive": utc_datetime(_CORPUS_END),
        "oos_start": utc_datetime(_OOS_START),
        "oos_end_exclusive": utc_datetime(_OOS_END),
        "months": list(month_values),
        "streams": streams,
        "folds": list(_folds()),
        "items": items,
        "summary": {
            "month_count": len(month_values),
            "stream_count": len(streams),
            "fold_count": len(_folds()),
            "item_count": len(items),
            "expected_physical_get_count": len(items) * 2,
            "requests_root_hash": requests_root,
        },
        "pit_eligibility": "ARCHIVE_REPLAY_ONLY",
        "usage_eligibility": "RESEARCH_DEVELOPMENT_ONLY",
        "prohibited_uses": [
            "FORMAL_PIT_OOS",
            "RELEASE_AUDIT_PASS",
            "MODEL_AUTO_ACTIVATION",
            "PROFITABILITY_CLAIM",
        ],
        "warnings": list(_WARNINGS),
    }
    plan["plan_hash"] = research_corpus_plan_hash(plan)
    return plan


def research_corpus_plan_reasons(plan: Mapping[str, Any]) -> Tuple[str, ...]:
    reasons = []
    if not isinstance(plan, Mapping):
        return ("CORPUS_PLAN_INVALID",)
    try:
        if tuple(_validator(_PLAN_SCHEMA).iter_errors(plan)):
            reasons.append("CORPUS_PLAN_SCHEMA_INVALID")
    except (json.JSONDecodeError, OSError, ValueError):
        reasons.append("CORPUS_PLAN_SCHEMA_INVALID")
    try:
        if plan.get("plan_hash") != research_corpus_plan_hash(plan):
            reasons.append("CORPUS_PLAN_HASH_MISMATCH")
    except (TypeError, ValueError):
        reasons.append("CORPUS_PLAN_HASH_MISMATCH")
    try:
        expected = build_default_research_corpus_plan()
        if business_hash(plan) != business_hash(expected):
            reasons.append("CORPUS_PLAN_SEMANTIC_MISMATCH")
    except (TypeError, ValueError, ResearchCorpusError):
        reasons.append("CORPUS_PLAN_SEMANTIC_MISMATCH")
    return tuple(sorted(set(reasons)))


def _strict_json_bytes(data: bytes) -> Mapping[str, Any]:
    if not isinstance(data, bytes):
        raise ResearchCorpusError("CORPUS_SOURCE_BYTES_INVALID")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ResearchCorpusError("CORPUS_SOURCE_BYTES_INVALID")
            result[key] = value
        return result

    def reject_number(_value):
        raise ResearchCorpusError("CORPUS_SOURCE_BYTES_INVALID")

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except ResearchCorpusError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ResearchCorpusError("CORPUS_SOURCE_BYTES_INVALID") from error
    if not isinstance(value, Mapping) or canonical_json(value).encode("utf-8") != data:
        raise ResearchCorpusError("CORPUS_SOURCE_BYTES_INVALID")
    return value


def _event_payload(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "sequence": row["sequence"],
        "event_id": row["event_id"],
        "corpus_item_id": row["corpus_item_id"],
        "event_type": row["event_type"],
        "worker_id": row["worker_id"],
        "attempt": row["attempt"],
        "recorded_at": row["recorded_at"],
        "lease_expires_at_or_null": row["lease_expires_at_or_null"],
        "source_bytes_sha256_or_null": row["source_bytes_sha256_or_null"],
        "source_snapshot_hash_or_null": row["source_snapshot_hash_or_null"],
        "expected_attestation_hash_or_null": row[
            "expected_attestation_hash_or_null"
        ],
        "physical_get_count": row["physical_get_count"],
        "error_code_or_null": row["error_code_or_null"],
        "previous_event_hash": row["previous_event_hash"],
    }


class HistoricalResearchCorpusState:
    """Append-only SQLite state for resumable corpus acquisition."""

    def __init__(
        self,
        path: Path,
        *,
        plan: Mapping[str, Any],
        output_root: Path,
    ):
        reasons = research_corpus_plan_reasons(plan)
        if reasons:
            raise ResearchCorpusError(reasons[0])
        self._plan = dict(plan)
        self._items = {
            item["corpus_item_id"]: item for item in self._plan["items"]
        }
        raw_path = Path(path).expanduser()
        raw_output_root = Path(output_root).expanduser()
        if raw_path.is_symlink() or (
            raw_path.exists() and not raw_path.is_file()
        ):
            raise ResearchCorpusError("CORPUS_STATE_PATH_INVALID")
        if raw_output_root.is_symlink() or (
            raw_output_root.exists() and not raw_output_root.is_dir()
        ):
            raise ResearchCorpusError("CORPUS_OUTPUT_ROOT_INVALID")
        self.path = raw_path.resolve()
        self.output_root = raw_output_root.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        os.chmod(self.output_root, 0o700)
        self._connection = sqlite3.connect(str(self.path))
        os.chmod(self.path, 0o600)
        self._connection.row_factory = sqlite3.Row
        self._validated_source_cache: Dict[Tuple[str, str, str, str], Mapping[str, Any]] = {}
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._initialize()
        self.replay()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "HistoricalResearchCorpusState":
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS corpus_meta (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                plan_hash TEXT NOT NULL,
                output_root TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS corpus_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                corpus_item_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                lease_expires_at_or_null TEXT,
                source_bytes BLOB,
                source_bytes_sha256_or_null TEXT,
                source_snapshot_hash_or_null TEXT,
                expected_attestation_hash_or_null TEXT,
                physical_get_count INTEGER NOT NULL,
                error_code_or_null TEXT,
                previous_event_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            );
            CREATE TRIGGER IF NOT EXISTS corpus_meta_no_update
            BEFORE UPDATE ON corpus_meta BEGIN SELECT RAISE(ABORT, 'append-only'); END;
            CREATE TRIGGER IF NOT EXISTS corpus_meta_no_delete
            BEFORE DELETE ON corpus_meta BEGIN SELECT RAISE(ABORT, 'append-only'); END;
            CREATE TRIGGER IF NOT EXISTS corpus_events_no_update
            BEFORE UPDATE ON corpus_events BEGIN SELECT RAISE(ABORT, 'append-only'); END;
            CREATE TRIGGER IF NOT EXISTS corpus_events_no_delete
            BEFORE DELETE ON corpus_events BEGIN SELECT RAISE(ABORT, 'append-only'); END;
            """
        )
        row = self._connection.execute(
            "SELECT plan_hash, output_root FROM corpus_meta WHERE singleton = 1"
        ).fetchone()
        binding = (self._plan["plan_hash"], str(self.output_root))
        if row is None:
            self._connection.execute(
                "INSERT INTO corpus_meta(singleton, plan_hash, output_root) "
                "VALUES(1, ?, ?)",
                binding,
            )
        elif (row["plan_hash"], row["output_root"]) != binding:
            raise ResearchCorpusError("CORPUS_STATE_BINDING_MISMATCH")
        self._connection.commit()

    def _rows(self) -> Tuple[Dict[str, Any], ...]:
        values = []
        for row in self._connection.execute(
            "SELECT * FROM corpus_events ORDER BY sequence"
        ):
            values.append(dict(row))
        return tuple(values)

    def _validate_source(
        self,
        item: Mapping[str, Any],
        row: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        data = row["source_bytes"]
        cache_key = (
            item["corpus_item_id"],
            row["source_bytes_sha256_or_null"] or "",
            row["source_snapshot_hash_or_null"] or "",
            row["expected_attestation_hash_or_null"] or "",
        )
        cached = self._validated_source_cache.get(cache_key)
        if cached is not None:
            return cached
        if (
            row["event_type"] != "SUCCEEDED"
            or not isinstance(data, bytes)
            or hashlib.sha256(data).hexdigest()
            != row["source_bytes_sha256_or_null"]
        ):
            raise ResearchCorpusError("CORPUS_SOURCE_BYTES_TAMPERED")
        snapshot = _strict_json_bytes(data)
        expected_attestation = historical_market_data_snapshot_attestation_hash(
            snapshot
        )
        if (
            snapshot.get("snapshot_hash")
            != row["source_snapshot_hash_or_null"]
            or expected_attestation
            != row["expected_attestation_hash_or_null"]
            or historical_market_data_snapshot_reasons(
                snapshot,
                trusted_snapshot_attestation_hashes={expected_attestation},
            )
            or snapshot.get("quality_eligibility") != "FORMAL_COMPLETE"
            or business_hash(snapshot.get("request"))
            != business_hash(item.get("request"))
        ):
            raise ResearchCorpusError("CORPUS_SOURCE_SEMANTIC_MISMATCH")
        self._validated_source_cache[cache_key] = snapshot
        return snapshot

    def replay(self) -> Dict[str, Any]:
        states: Dict[str, Dict[str, Any]] = {}
        previous_hash = _ZERO_HASH
        previous_time: Optional[datetime] = None
        physical_get_count = 0
        for row in self._rows():
            item_id = row["corpus_item_id"]
            if item_id not in self._items or row["event_type"] not in _EVENT_TYPES:
                raise ResearchCorpusError("CORPUS_EVENT_INVALID")
            if (
                not _WORKER_ID.fullmatch(row["worker_id"])
                or not isinstance(row["attempt"], int)
                or row["attempt"] < 1
                or not isinstance(row["physical_get_count"], int)
                or row["physical_get_count"] < 0
                or row["physical_get_count"] > 2
                or row["previous_event_hash"] != previous_hash
            ):
                raise ResearchCorpusError("CORPUS_EVENT_INVALID")
            recorded_at, _ = _utc(row["recorded_at"])
            if previous_time is not None and recorded_at < previous_time:
                raise ResearchCorpusError("CORPUS_EVENT_TIME_REGRESSION")
            previous_time = recorded_at
            payload = _event_payload(row)
            if (
                row["event_id"]
                != stable_id(
                    "corpus_event",
                    {
                        key: value
                        for key, value in payload.items()
                        if key != "event_id"
                    },
                )
                or row["event_hash"] != business_hash(payload)
            ):
                raise ResearchCorpusError("CORPUS_EVENT_HASH_MISMATCH")
            current = states.get(item_id)
            event_type = row["event_type"]
            if event_type == "CLAIMED":
                if (
                    row["lease_expires_at_or_null"] is None
                    or row["source_bytes"] is not None
                    or row["source_bytes_sha256_or_null"] is not None
                    or row["source_snapshot_hash_or_null"] is not None
                    or row["expected_attestation_hash_or_null"] is not None
                    or row["physical_get_count"] != 0
                    or row["error_code_or_null"] is not None
                ):
                    raise ResearchCorpusError("CORPUS_EVENT_INVALID")
                lease, _ = _utc(row["lease_expires_at_or_null"])
                if lease - recorded_at != _LEASE_DURATION:
                    raise ResearchCorpusError("CORPUS_LEASE_INVALID")
                expected_attempt = 1 if current is None else current["attempt"] + 1
                if current is not None:
                    if current["status"] == "SUCCEEDED":
                        raise ResearchCorpusError("CORPUS_SUCCESS_REWRITTEN")
                    if current["status"] == "CLAIMED":
                        prior_lease, _ = _utc(current["lease_expires_at"])
                        if recorded_at < prior_lease:
                            raise ResearchCorpusError("CORPUS_ACTIVE_LEASE_RECLAIMED")
                if row["attempt"] != expected_attempt:
                    raise ResearchCorpusError("CORPUS_ATTEMPT_INVALID")
                states[item_id] = {
                    "status": "CLAIMED",
                    "attempt": row["attempt"],
                    "worker_id": row["worker_id"],
                    "recorded_at": row["recorded_at"],
                    "lease_expires_at": row["lease_expires_at_or_null"],
                    "row": row,
                }
            else:
                current_lease = None
                if current is not None and current.get("status") == "CLAIMED":
                    current_lease, _ = _utc(current["lease_expires_at"])
                if (
                    current is None
                    or current["status"] != "CLAIMED"
                    or current["attempt"] != row["attempt"]
                    or current["worker_id"] != row["worker_id"]
                    or row["lease_expires_at_or_null"] is not None
                    or current_lease is None
                    or recorded_at > current_lease
                ):
                    raise ResearchCorpusError("CORPUS_TERMINAL_EVENT_INVALID")
                if event_type == "SUCCEEDED":
                    if (
                        row["physical_get_count"] != 2
                        or row["error_code_or_null"] is not None
                    ):
                        raise ResearchCorpusError("CORPUS_EVENT_INVALID")
                    snapshot = self._validate_source(self._items[item_id], row)
                    states[item_id] = {
                        "status": "SUCCEEDED",
                        "attempt": row["attempt"],
                        "worker_id": row["worker_id"],
                        "recorded_at": row["recorded_at"],
                        "row": row,
                        "snapshot": snapshot,
                    }
                else:
                    if (
                        row["source_bytes"] is not None
                        or row["source_bytes_sha256_or_null"] is not None
                        or row["source_snapshot_hash_or_null"] is not None
                        or row["expected_attestation_hash_or_null"] is not None
                        or not isinstance(row["error_code_or_null"], str)
                        or not _ERROR_CODE.fullmatch(row["error_code_or_null"])
                    ):
                        raise ResearchCorpusError("CORPUS_EVENT_INVALID")
                    states[item_id] = {
                        "status": "FAILED",
                        "attempt": row["attempt"],
                        "worker_id": row["worker_id"],
                        "recorded_at": row["recorded_at"],
                        "row": row,
                    }
                physical_get_count += row["physical_get_count"]
            previous_hash = row["event_hash"]
        return {
            "states": states,
            "event_count": sum(1 for _ in self._rows()),
            "event_chain_end_hash": previous_hash,
            "physical_get_count": physical_get_count,
        }

    def _append(
        self,
        *,
        corpus_item_id: str,
        event_type: str,
        worker_id: str,
        attempt: int,
        recorded_at: str,
        lease_expires_at_or_null: Optional[str] = None,
        source_bytes: Optional[bytes] = None,
        source_snapshot_hash_or_null: Optional[str] = None,
        expected_attestation_hash_or_null: Optional[str] = None,
        physical_get_count: int = 0,
        error_code_or_null: Optional[str] = None,
    ) -> None:
        source_sha = (
            hashlib.sha256(source_bytes).hexdigest()
            if source_bytes is not None
            else None
        )
        previous = self._connection.execute(
            "SELECT sequence, event_hash, recorded_at FROM corpus_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 1 if previous is None else previous["sequence"] + 1
        previous_hash = _ZERO_HASH if previous is None else previous["event_hash"]
        new_time, _ = _utc(recorded_at)
        if previous is not None:
            prior_time, _ = _utc(previous["recorded_at"])
            if new_time < prior_time:
                raise ResearchCorpusError("CORPUS_EVENT_TIME_REGRESSION")
        payload = {
            "sequence": sequence,
            "event_id": "",
            "corpus_item_id": corpus_item_id,
            "event_type": event_type,
            "worker_id": worker_id,
            "attempt": attempt,
            "recorded_at": recorded_at,
            "lease_expires_at_or_null": lease_expires_at_or_null,
            "source_bytes_sha256_or_null": source_sha,
            "source_snapshot_hash_or_null": source_snapshot_hash_or_null,
            "expected_attestation_hash_or_null": expected_attestation_hash_or_null,
            "physical_get_count": physical_get_count,
            "error_code_or_null": error_code_or_null,
            "previous_event_hash": previous_hash,
        }
        payload["event_id"] = stable_id(
            "corpus_event",
            {key: value for key, value in payload.items() if key != "event_id"},
        )
        # The replay hash includes the final event_id.
        event_hash = business_hash(payload)
        self._connection.execute(
            """
            INSERT INTO corpus_events(
                event_id, corpus_item_id, event_type, worker_id, attempt,
                recorded_at, lease_expires_at_or_null, source_bytes,
                source_bytes_sha256_or_null, source_snapshot_hash_or_null,
                expected_attestation_hash_or_null, physical_get_count,
                error_code_or_null, previous_event_hash, event_hash
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["event_id"],
                corpus_item_id,
                event_type,
                worker_id,
                attempt,
                recorded_at,
                lease_expires_at_or_null,
                source_bytes,
                source_sha,
                source_snapshot_hash_or_null,
                expected_attestation_hash_or_null,
                physical_get_count,
                error_code_or_null,
                previous_hash,
                event_hash,
            ),
        )

    def claim_next(
        self,
        *,
        worker_id: str,
        recorded_at: str,
        excluded_item_ids: Sequence[str] = (),
    ) -> Optional[Mapping[str, Any]]:
        if not isinstance(worker_id, str) or not _WORKER_ID.fullmatch(worker_id):
            raise ResearchCorpusError("CORPUS_WORKER_INVALID")
        excluded_values = tuple(excluded_item_ids)
        excluded = set(excluded_values)
        if (
            len(excluded) != len(excluded_values)
            or any(item_id not in self._items for item_id in excluded)
        ):
            raise ResearchCorpusError("CORPUS_EXCLUSION_SET_INVALID")
        now, now_text = _utc(recorded_at)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            replay = self.replay()
            selected = None
            for item in self._plan["items"]:
                if item["corpus_item_id"] in excluded:
                    continue
                current = replay["states"].get(item["corpus_item_id"])
                if current is None or current["status"] == "FAILED":
                    selected = item
                    break
                if current["status"] == "CLAIMED":
                    lease, _ = _utc(current["lease_expires_at"])
                    if now >= lease:
                        selected = item
                        break
            if selected is None:
                self._connection.commit()
                return None
            prior = replay["states"].get(selected["corpus_item_id"])
            attempt = 1 if prior is None else prior["attempt"] + 1
            self._append(
                corpus_item_id=selected["corpus_item_id"],
                event_type="CLAIMED",
                worker_id=worker_id,
                attempt=attempt,
                recorded_at=now_text,
                lease_expires_at_or_null=utc_datetime(now + _LEASE_DURATION),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        self.replay()
        return selected

    def succeed(
        self,
        *,
        corpus_item_id: str,
        worker_id: str,
        snapshot: Mapping[str, Any],
        physical_get_count: int,
        recorded_at: str,
    ) -> None:
        now, now_text = _utc(recorded_at)
        data = canonical_json(snapshot).encode("utf-8")
        attestation_hash = historical_market_data_snapshot_attestation_hash(snapshot)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            replay = self.replay()
            current = replay["states"].get(corpus_item_id)
            if (
                current is None
                or current["status"] != "CLAIMED"
                or current["worker_id"] != worker_id
            ):
                raise ResearchCorpusError("CORPUS_CLAIM_NOT_OWNED")
            lease, _ = _utc(current["lease_expires_at"])
            if now > lease:
                raise ResearchCorpusError("CORPUS_LEASE_EXPIRED")
            self._validate_source(
                self._items[corpus_item_id],
                {
                    "event_type": "SUCCEEDED",
                    "source_bytes": data,
                    "source_bytes_sha256_or_null": hashlib.sha256(data).hexdigest(),
                    "source_snapshot_hash_or_null": snapshot.get("snapshot_hash"),
                    "expected_attestation_hash_or_null": attestation_hash,
                },
            )
            self._append(
                corpus_item_id=corpus_item_id,
                event_type="SUCCEEDED",
                worker_id=worker_id,
                attempt=current["attempt"],
                recorded_at=now_text,
                source_bytes=data,
                source_snapshot_hash_or_null=snapshot["snapshot_hash"],
                expected_attestation_hash_or_null=attestation_hash,
                physical_get_count=physical_get_count,
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        self.replay()

    def fail(
        self,
        *,
        corpus_item_id: str,
        worker_id: str,
        error_code: str,
        physical_get_count: int,
        recorded_at: str,
    ) -> None:
        if not isinstance(error_code, str) or not _ERROR_CODE.fullmatch(error_code):
            raise ResearchCorpusError("CORPUS_ERROR_CODE_INVALID")
        now, now_text = _utc(recorded_at)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            replay = self.replay()
            current = replay["states"].get(corpus_item_id)
            if (
                current is None
                or current["status"] != "CLAIMED"
                or current["worker_id"] != worker_id
            ):
                raise ResearchCorpusError("CORPUS_CLAIM_NOT_OWNED")
            lease, _ = _utc(current["lease_expires_at"])
            if now > lease:
                raise ResearchCorpusError("CORPUS_LEASE_EXPIRED")
            self._append(
                corpus_item_id=corpus_item_id,
                event_type="FAILED",
                worker_id=worker_id,
                attempt=current["attempt"],
                recorded_at=now_text,
                physical_get_count=physical_get_count,
                error_code_or_null=error_code,
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        self.replay()

    def successful_sources(self) -> Tuple[Tuple[Mapping[str, Any], bytes], ...]:
        replay = self.replay()
        sources = []
        for item in self._plan["items"]:
            current = replay["states"].get(item["corpus_item_id"])
            if current is not None and current["status"] == "SUCCEEDED":
                sources.append((item, current["row"]["source_bytes"]))
        return tuple(sources)


def research_corpus_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    return artifact_self_hash(snapshot, "snapshot_hash")


def build_research_corpus_snapshot(
    *,
    plan: Mapping[str, Any],
    state: HistoricalResearchCorpusState,
    recorded_at: str,
    trusted_snapshot_attestation_hashes: Sequence[str] = (),
) -> Dict[str, Any]:
    reasons = research_corpus_plan_reasons(plan)
    if reasons:
        raise ResearchCorpusError(reasons[0])
    now, now_text = _utc(recorded_at)
    replay = state.replay()
    trusted = set(trusted_snapshot_attestation_hashes)
    if any(not isinstance(value, str) or not _SHA256.fullmatch(value) for value in trusted):
        raise ResearchCorpusError("CORPUS_ATTESTATION_SET_INVALID")
    item_rows = []
    status_counts = {
        "PENDING": 0,
        "CLAIMED": 0,
        "CLAIM_EXPIRED": 0,
        "FAILED": 0,
        "SUCCEEDED": 0,
    }
    quality_complete = True
    attestation_complete = True
    item_lookup = {}
    for item in plan["items"]:
        current = replay["states"].get(item["corpus_item_id"])
        status = "PENDING"
        row = {
            "corpus_item_id": item["corpus_item_id"],
            "stream_id": item["stream_id"],
            "month": item["month"],
            "status": status,
            "attempt_count": 0,
            "snapshot_sha256_or_null": None,
            "snapshot_hash_or_null": None,
            "quality_eligibility_or_null": None,
            "expected_attestation_hash_or_null": None,
            "attestation_anchored": False,
            "last_error_code_or_null": None,
        }
        if current is not None:
            status = current["status"]
            if status == "CLAIMED":
                lease, _ = _utc(current["lease_expires_at"])
                status = "CLAIM_EXPIRED" if now >= lease else "CLAIMED"
            row["attempt_count"] = current["attempt"]
            if current["status"] == "SUCCEEDED":
                source = current["row"]
                source_snapshot = current["snapshot"]
                attestation_hash = source["expected_attestation_hash_or_null"]
                row.update(
                    {
                        "snapshot_sha256_or_null": source[
                            "source_bytes_sha256_or_null"
                        ],
                        "snapshot_hash_or_null": source[
                            "source_snapshot_hash_or_null"
                        ],
                        "quality_eligibility_or_null": source_snapshot[
                            "quality_eligibility"
                        ],
                        "expected_attestation_hash_or_null": attestation_hash,
                        "attestation_anchored": attestation_hash in trusted,
                    }
                )
                quality_complete = quality_complete and (
                    source_snapshot["quality_eligibility"] == "FORMAL_COMPLETE"
                )
                attestation_complete = attestation_complete and (
                    attestation_hash in trusted
                )
            elif current["status"] == "FAILED":
                row["last_error_code_or_null"] = current["row"][
                    "error_code_or_null"
                ]
        row["status"] = status
        status_counts[status] += 1
        if status != "SUCCEEDED":
            quality_complete = False
            attestation_complete = False
        item_rows.append(row)
        item_lookup[(item["stream_id"], item["month"])] = row
    coverage = []
    for stream in plan["streams"]:
        coverage.append(
            {
                "stream_id": stream["stream_id"],
                "months": [
                    {
                        "month": month,
                        "status": item_lookup[(stream["stream_id"], month)][
                            "status"
                        ],
                    }
                    for month in plan["months"]
                ],
            }
        )
    complete = status_counts["SUCCEEDED"] == len(plan["items"])
    snapshot = {
        "$schema": "./historical-research-corpus-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": stable_id(
            "research_corpus_snapshot",
            {
                "plan_hash": plan["plan_hash"],
                "event_chain_end_hash": replay["event_chain_end_hash"],
                "recorded_at": now_text,
            },
        ),
        "snapshot_hash": _ZERO_HASH,
        "recorded_at": now_text,
        "plan_id": plan["plan_id"],
        "plan_hash": plan["plan_hash"],
        "event_count": replay["event_count"],
        "event_chain_end_hash": replay["event_chain_end_hash"],
        "items": item_rows,
        "coverage": coverage,
        "summary": {
            "planned_item_count": len(plan["items"]),
            "pending_item_count": status_counts["PENDING"],
            "claimed_item_count": status_counts["CLAIMED"],
            "expired_claim_item_count": status_counts["CLAIM_EXPIRED"],
            "failed_item_count": status_counts["FAILED"],
            "succeeded_item_count": status_counts["SUCCEEDED"],
            "physical_get_count": replay["physical_get_count"],
            "corpus_complete": complete,
            "quality_complete": quality_complete,
            "attestation_anchoring_complete": attestation_complete,
        },
        "state_integrity": "VERIFIED_APPEND_ONLY_WAL_AND_SOURCE_BYTES",
        "research_training_readiness": (
            "READY_FOR_ARCHIVE_RESEARCH_FEATURE_BUILD"
            if complete and quality_complete
            else "NOT_READY_INCOMPLETE_OR_INVALID"
        ),
        "attestation_eligibility": (
            "EXTERNALLY_ANCHORED"
            if complete and attestation_complete
            else "UNANCHORED_ARCHIVE_RESEARCH"
        ),
        "formal_pit_eligibility": "INELIGIBLE_ARCHIVE_REPLAY",
        "release_oos_eligibility": "INELIGIBLE",
        "profitability_eligibility": "INELIGIBLE",
        "warnings": list(_WARNINGS),
    }
    snapshot["snapshot_hash"] = research_corpus_snapshot_hash(snapshot)
    if tuple(_validator(_SNAPSHOT_SCHEMA).iter_errors(snapshot)):
        raise ResearchCorpusError("CORPUS_SNAPSHOT_SCHEMA_INVALID")
    return snapshot


def research_corpus_snapshot_reasons(
    snapshot: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
) -> Tuple[str, ...]:
    reasons = list(research_corpus_plan_reasons(plan))
    if not isinstance(snapshot, Mapping):
        return tuple(sorted(set(reasons + ["CORPUS_SNAPSHOT_INVALID"])))
    try:
        if tuple(_validator(_SNAPSHOT_SCHEMA).iter_errors(snapshot)):
            reasons.append("CORPUS_SNAPSHOT_SCHEMA_INVALID")
    except (json.JSONDecodeError, OSError, ValueError):
        reasons.append("CORPUS_SNAPSHOT_SCHEMA_INVALID")
    try:
        if snapshot.get("snapshot_hash") != research_corpus_snapshot_hash(snapshot):
            reasons.append("CORPUS_SNAPSHOT_HASH_MISMATCH")
        if (
            snapshot.get("plan_id") != plan.get("plan_id")
            or snapshot.get("plan_hash") != plan.get("plan_hash")
        ):
            reasons.append("CORPUS_SNAPSHOT_PLAN_MISMATCH")
        expected_id = stable_id(
            "research_corpus_snapshot",
            {
                "plan_hash": snapshot["plan_hash"],
                "event_chain_end_hash": snapshot["event_chain_end_hash"],
                "recorded_at": snapshot["recorded_at"],
            },
        )
        if snapshot.get("snapshot_id") != expected_id:
            reasons.append("CORPUS_SNAPSHOT_ID_MISMATCH")
        items = snapshot.get("items")
        if not isinstance(items, list) or len(items) != len(plan["items"]):
            reasons.append("CORPUS_SNAPSHOT_ITEM_COVERAGE_INVALID")
        else:
            expected_keys = [
                (item["corpus_item_id"], item["stream_id"], item["month"])
                for item in plan["items"]
            ]
            actual_keys = [
                (
                    item.get("corpus_item_id"),
                    item.get("stream_id"),
                    item.get("month"),
                )
                for item in items
                if isinstance(item, Mapping)
            ]
            if actual_keys != expected_keys:
                reasons.append("CORPUS_SNAPSHOT_ITEM_COVERAGE_INVALID")
            for item in items:
                if not isinstance(item, Mapping):
                    reasons.append("CORPUS_SNAPSHOT_ITEM_COVERAGE_INVALID")
                    continue
                status = item.get("status")
                hash_fields = (
                    item.get("snapshot_sha256_or_null"),
                    item.get("snapshot_hash_or_null"),
                    item.get("expected_attestation_hash_or_null"),
                )
                if status == "SUCCEEDED":
                    if (
                        any(
                            not isinstance(value, str)
                            or not _SHA256.fullmatch(value)
                            for value in hash_fields
                        )
                        or item.get("quality_eligibility_or_null")
                        != "FORMAL_COMPLETE"
                        or item.get("last_error_code_or_null") is not None
                    ):
                        reasons.append("CORPUS_SNAPSHOT_ITEM_STATE_INVALID")
                elif (
                    any(value is not None for value in hash_fields)
                    or item.get("quality_eligibility_or_null") is not None
                    or item.get("attestation_anchored") is not False
                    or (
                        status == "FAILED"
                        and item.get("last_error_code_or_null") is None
                    )
                    or (
                        status != "FAILED"
                        and item.get("last_error_code_or_null") is not None
                    )
                ):
                    reasons.append("CORPUS_SNAPSHOT_ITEM_STATE_INVALID")
            counts = {
                status: sum(item.get("status") == status for item in items)
                for status in (
                    "PENDING",
                    "CLAIMED",
                    "CLAIM_EXPIRED",
                    "FAILED",
                    "SUCCEEDED",
                )
            }
            summary = snapshot.get("summary", {})
            expected_summary_counts = (
                summary.get("pending_item_count"),
                summary.get("claimed_item_count"),
                summary.get("expired_claim_item_count"),
                summary.get("failed_item_count"),
                summary.get("succeeded_item_count"),
            )
            if expected_summary_counts != tuple(counts.values()):
                reasons.append("CORPUS_SNAPSHOT_SUMMARY_MISMATCH")
            complete = counts["SUCCEEDED"] == len(plan["items"])
            quality_complete = complete and all(
                item.get("quality_eligibility_or_null") == "FORMAL_COMPLETE"
                for item in items
            )
            attestation_complete = complete and all(
                item.get("attestation_anchored") is True for item in items
            )
            if summary.get("corpus_complete") != complete:
                reasons.append("CORPUS_SNAPSHOT_SUMMARY_MISMATCH")
            if (
                summary.get("quality_complete") != quality_complete
                or summary.get("attestation_anchoring_complete")
                != attestation_complete
            ):
                reasons.append("CORPUS_SNAPSHOT_SUMMARY_MISMATCH")
            ready = (
                snapshot.get("research_training_readiness")
                == "READY_FOR_ARCHIVE_RESEARCH_FEATURE_BUILD"
            )
            if ready != quality_complete:
                reasons.append("CORPUS_SNAPSHOT_READINESS_MISMATCH")
            anchored = snapshot.get("attestation_eligibility") == "EXTERNALLY_ANCHORED"
            if anchored != attestation_complete:
                reasons.append("CORPUS_SNAPSHOT_ATTESTATION_MISMATCH")
            expected_coverage = []
            indexed = {
                (item.get("stream_id"), item.get("month")): item.get("status")
                for item in items
                if isinstance(item, Mapping)
            }
            for stream in plan["streams"]:
                expected_coverage.append(
                    {
                        "stream_id": stream["stream_id"],
                        "months": [
                            {
                                "month": month,
                                "status": indexed.get(
                                    (stream["stream_id"], month)
                                ),
                            }
                            for month in plan["months"]
                        ],
                    }
                )
            if business_hash(snapshot.get("coverage")) != business_hash(
                expected_coverage
            ):
                reasons.append("CORPUS_SNAPSHOT_COVERAGE_MATRIX_MISMATCH")
    except (KeyError, TypeError, ValueError):
        reasons.append("CORPUS_SNAPSHOT_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def _publish_exact(path: Path, data: bytes) -> None:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    if target.exists():
        if not target.is_file() or target.read_bytes() != data:
            raise ResearchCorpusError("CORPUS_PUBLISH_CONFLICT")
        os.chmod(target, 0o600)
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".corpus-", suffix=".tmp", dir=str(target.parent)
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        os.chmod(target, 0o600)
        directory_descriptor = os.open(str(target.parent), os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def publish_research_corpus_plan(
    plan: Mapping[str, Any],
    output_path: Path,
) -> None:
    reasons = research_corpus_plan_reasons(plan)
    if reasons:
        raise ResearchCorpusError(reasons[0])
    _publish_exact(
        Path(output_path),
        canonical_json(plan).encode("utf-8"),
    )


def load_research_corpus_plan(path: Path) -> Mapping[str, Any]:
    try:
        data = Path(path).expanduser().resolve().read_bytes()
    except OSError as error:
        raise ResearchCorpusError("CORPUS_PLAN_READ_FAILED") from error
    plan = _strict_json_bytes(data)
    reasons = research_corpus_plan_reasons(plan)
    if reasons:
        raise ResearchCorpusError(reasons[0])
    return plan


def load_research_corpus_snapshot(
    path: Path,
    *,
    plan: Mapping[str, Any],
) -> Mapping[str, Any]:
    try:
        data = Path(path).expanduser().resolve().read_bytes()
    except OSError as error:
        raise ResearchCorpusError("CORPUS_SNAPSHOT_READ_FAILED") from error
    snapshot = _strict_json_bytes(data)
    reasons = research_corpus_snapshot_reasons(snapshot, plan=plan)
    if reasons:
        raise ResearchCorpusError(reasons[0])
    return snapshot


def _publish_successful_sources(state: HistoricalResearchCorpusState) -> None:
    for item, data in state.successful_sources():
        _publish_exact(
            state.output_root
            / "source"
            / item["stream_id"]
            / f"{item['month']}.json",
            data,
        )


class _CountingTransport:
    def __init__(self, transport: Any):
        self._transport = transport
        self.count = 0

    def get(self, url):
        self.count += 1
        return self._transport.get(url)


def run_historical_research_corpus(
    *,
    plan: Mapping[str, Any],
    state_path: Path,
    output_root: Path,
    worker_id: str,
    max_items: int = 1,
    transport: Optional[Any] = None,
    clock: Optional[Callable[[], str]] = None,
    trusted_snapshot_attestation_hashes: Sequence[str] = (),
) -> Dict[str, Any]:
    """Resume at most ``max_items`` and publish source and coverage artifacts."""

    if (
        isinstance(max_items, bool)
        or not isinstance(max_items, int)
        or not 1 <= max_items <= _MAX_ITEMS_PER_RUN
    ):
        raise ResearchCorpusError("CORPUS_MAX_ITEMS_INVALID")
    if not isinstance(worker_id, str) or not _WORKER_ID.fullmatch(worker_id):
        raise ResearchCorpusError("CORPUS_WORKER_INVALID")
    reasons = research_corpus_plan_reasons(plan)
    if reasons:
        raise ResearchCorpusError(reasons[0])
    clock = clock or (
        lambda: utc_datetime(datetime.now(timezone.utc))
    )
    transport = transport or PublicArchiveTransport()
    with HistoricalResearchCorpusState(
        Path(state_path),
        plan=plan,
        output_root=Path(output_root),
    ) as state:
        _publish_successful_sources(state)
        processed_item_ids = set()
        for _ in range(max_items):
            item = state.claim_next(
                worker_id=worker_id,
                recorded_at=clock(),
                excluded_item_ids=tuple(processed_item_ids),
            )
            if item is None:
                break
            processed_item_ids.add(item["corpus_item_id"])
            counting = _CountingTransport(transport)
            try:
                request = _request_from_payload(item["request"])
                snapshot = fetch_historical_market_data(
                    request,
                    counting,
                    clock(),
                )
                state.succeed(
                    corpus_item_id=item["corpus_item_id"],
                    worker_id=worker_id,
                    snapshot=snapshot,
                    physical_get_count=counting.count,
                    recorded_at=clock(),
                )
            except (MarketDataError, ResearchCorpusError) as error:
                reason_code = getattr(error, "reason_code", "CORPUS_FETCH_FAILED")
                state.fail(
                    corpus_item_id=item["corpus_item_id"],
                    worker_id=worker_id,
                    error_code=reason_code,
                    physical_get_count=counting.count,
                    recorded_at=clock(),
                )
            _publish_successful_sources(state)
        result = build_research_corpus_snapshot(
            plan=plan,
            state=state,
            recorded_at=clock(),
            trusted_snapshot_attestation_hashes=(
                trusted_snapshot_attestation_hashes
            ),
        )
        _publish_exact(
            state.output_root / "snapshots" / f"{result['snapshot_id']}.json",
            canonical_json(result).encode("utf-8"),
        )
        return result
