"""Crash-recoverable, append-only scheduling for public offline Paper cycles."""

import hashlib
import json
import sqlite3
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .market_data import MarketDataError
from .market_data_cli import _publish_immutable
from .offline_paper import (
    BinanceOfflinePaperTransport,
    OfflinePaperError,
    OfflinePaperPlan,
    build_offline_paper_run,
    capture_offline_paper,
    offline_paper_run_reasons,
    offline_paper_run_trust_hash,
)


_POLICY_TOKEN = object()
_SLOT_TOKEN = object()
_GENESIS_HASH = "0" * 64
_CADENCE = timedelta(hours=4)
_CLOSE_DELAY = timedelta(minutes=5)
_LEASE = timedelta(minutes=15)
_ALLOWED_EVENTS = frozenset(
    (
        "SLOT_CLAIMED",
        "RUN_PREPARED",
        "RUN_SUCCEEDED",
        "RUN_FAILED",
        "SLOT_MISSED",
        "SLOT_EXPIRED",
    )
)
_TERMINAL = frozenset(("SUCCEEDED", "MISSED", "EXPIRED"))
_SCHEDULE_ATTESTATION_TYPE = "PAPER_SCHEDULE_SNAPSHOT_ATTESTATION"
_WARNINGS = (
    "ACCOUNT_FEE_SCHEDULE_UNOBSERVED",
    "ACCOUNT_SPECIFIC_FILTERS_UNOBSERVED",
    "PERPETUAL_CONTEXT_NOT_CAPTURED",
    "AI_MODEL_NOT_RUN",
    "OPERATING_SYSTEM_SCHEDULER_NOT_CONFIGURED",
)


@lru_cache(maxsize=1)
def _snapshot_validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas", "paper-schedule-snapshot-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class PaperScheduleError(ValueError):
    """The schedule, state chain, lease, or prepared run failed closed."""

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
            raise PaperScheduleError("PAPER_SCHEDULE_TIME_INVALID") from error
    else:
        raise PaperScheduleError("PAPER_SCHEDULE_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperScheduleError("PAPER_SCHEDULE_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    converted = converted.replace(microsecond=(converted.microsecond // 1000) * 1000)
    return converted, utc_datetime(converted)


def _worker_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 64
        or not value.isascii()
        or any(not (character.isalnum() or character in "._-") for character in value)
    ):
        raise PaperScheduleError("PAPER_SCHEDULE_WORKER_INVALID")
    return value


@dataclass(frozen=True, init=False)
class PaperSlot:
    slot_id: str
    scheduled_for: str
    due_at: str
    expires_at: str

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _SLOT_TOKEN:
            raise TypeError("PaperSlot is issued by PaperSchedulePolicy")
        for name in ("slot_id", "scheduled_for", "due_at", "expires_at"):
            object.__setattr__(self, name, kwargs[name])


@dataclass(frozen=True, init=False)
class PaperSchedulePolicy:
    schema_version: str
    schedule_id: str
    symbol: str
    cadence_seconds: int
    close_delay_seconds: int
    lease_seconds: int

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _POLICY_TOKEN:
            raise TypeError("PaperSchedulePolicy must be created with create")
        object.__setattr__(self, "schema_version", "1.0.0")
        object.__setattr__(
            self, "schedule_id", "ethusdt-public-offline-paper-4h-v1"
        )
        object.__setattr__(self, "symbol", "ETHUSDT")
        object.__setattr__(self, "cadence_seconds", 14_400)
        object.__setattr__(self, "close_delay_seconds", 300)
        object.__setattr__(self, "lease_seconds", 900)

    @classmethod
    def create(cls, *, symbol: str = "ETHUSDT") -> "PaperSchedulePolicy":
        if symbol != "ETHUSDT":
            raise PaperScheduleError("PAPER_SCHEDULE_POLICY_INVALID")
        return cls(_token=_POLICY_TOKEN)

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "schedule_id": self.schedule_id,
            "symbol": self.symbol,
            "timezone": "UTC",
            "utc_anchor": "00:00:00",
            "cadence_seconds": self.cadence_seconds,
            "close_delay_seconds": self.close_delay_seconds,
            "lease_seconds": self.lease_seconds,
            "network_attempts_per_invocation": 1,
            "historical_backfill_allowed": False,
        }

    @property
    def policy_hash(self) -> str:
        return business_hash(self.business_payload())

    def slot_from_scheduled(self, scheduled_for: object) -> PaperSlot:
        scheduled, scheduled_text = _utc(scheduled_for)
        if (
            scheduled.minute != 0
            or scheduled.second != 0
            or scheduled.microsecond != 0
            or scheduled.hour % 4 != 0
        ):
            raise PaperScheduleError("PAPER_SCHEDULE_SLOT_INVALID")
        due = scheduled + _CLOSE_DELAY
        expires = due + _CADENCE
        compact = scheduled.strftime("%Y%m%dT%H%M%SZ")
        return PaperSlot(
            slot_id="ETHUSDT_" + compact,
            scheduled_for=scheduled_text,
            due_at=utc_datetime(due),
            expires_at=utc_datetime(expires),
            _token=_SLOT_TOKEN,
        )

    def current_slot(self, now: object) -> PaperSlot:
        current, _ = _utc(now)
        shifted = current - _CLOSE_DELAY
        scheduled = shifted.replace(
            hour=(shifted.hour // 4) * 4,
            minute=0,
            second=0,
            microsecond=0,
        )
        return self.slot_from_scheduled(scheduled)


@dataclass(frozen=True)
class ClaimResult:
    outcome: str
    slot: PaperSlot
    worker_id: str
    attempt: int
    claimed_at: str
    lease_expires_at: str
    claim_event_id: Optional[str]
    prepared: Optional[Mapping[str, Any]]


def _slot_core(slot: PaperSlot, policy: PaperSchedulePolicy) -> Dict[str, str]:
    return {
        "schedule_id": policy.schedule_id,
        "schedule_policy_hash": policy.policy_hash,
        "scheduled_for": slot.scheduled_for,
        "due_at": slot.due_at,
        "expires_at": slot.expires_at,
    }


def _event_without_hash(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "sequence": row["sequence"],
        "event_id": row["event_id"],
        "event_type": row["event_type"],
        "slot_id": row["slot_id"],
        "event_time": row["event_time"],
        "payload": row["payload"],
        "payload_hash": row["payload_hash"],
        "previous_event_hash": row["previous_event_hash"],
    }


def _slot_from_payload(slot_id: str, payload: Mapping[str, Any]) -> PaperSlot:
    scheduled, scheduled_text = _utc(payload.get("scheduled_for"))
    _, due_text = _utc(payload.get("due_at"))
    _, expires_text = _utc(payload.get("expires_at"))
    expected = "ETHUSDT_" + scheduled.strftime("%Y%m%dT%H%M%SZ")
    if slot_id != expected:
        raise PaperScheduleError("PAPER_SCHEDULE_SLOT_ID_MISMATCH")
    return PaperSlot(
        slot_id=slot_id,
        scheduled_for=scheduled_text,
        due_at=due_text,
        expires_at=expires_text,
        _token=_SLOT_TOKEN,
    )


def _project_events(
    events: Sequence[Mapping[str, Any]],
    policy: PaperSchedulePolicy,
) -> Dict[str, Dict[str, Any]]:
    projection: Dict[str, Dict[str, Any]] = {}
    previous_sequence = 0
    previous_hash = _GENESIS_HASH
    previous_time: Optional[datetime] = None
    for source in events:
        if not isinstance(source, Mapping):
            raise PaperScheduleError("PAPER_SCHEDULE_EVENT_INVALID")
        try:
            sequence = source["sequence"]
            event_type = source["event_type"]
            slot_id = source["slot_id"]
            payload = source["payload"]
            event_time, event_time_text = _utc(source["event_time"])
        except KeyError as error:
            raise PaperScheduleError("PAPER_SCHEDULE_EVENT_INVALID") from error
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence != previous_sequence + 1
            or event_type not in _ALLOWED_EVENTS
            or not isinstance(slot_id, str)
            or not isinstance(payload, Mapping)
        ):
            raise PaperScheduleError("PAPER_SCHEDULE_EVENT_INVALID")
        if previous_time is not None and event_time < previous_time:
            raise PaperScheduleError("PAPER_SCHEDULE_EVENT_TIME_ORDER_INVALID")
        if source.get("previous_event_hash") != previous_hash:
            raise PaperScheduleError("PAPER_SCHEDULE_EVENT_CHAIN_INVALID")
        payload_hash = business_hash(payload)
        if source.get("payload_hash") != payload_hash:
            raise PaperScheduleError("PAPER_SCHEDULE_EVENT_PAYLOAD_HASH_MISMATCH")
        body = {
            "sequence": sequence,
            "event_id": source.get("event_id"),
            "event_type": event_type,
            "slot_id": slot_id,
            "event_time": event_time_text,
            "payload": dict(payload),
            "payload_hash": payload_hash,
            "previous_event_hash": previous_hash,
        }
        if source.get("event_hash") != business_hash(body):
            raise PaperScheduleError("PAPER_SCHEDULE_EVENT_HASH_MISMATCH")
        slot = _slot_from_payload(slot_id, payload)
        core = _slot_core(slot, policy)
        if any(payload.get(name) != value for name, value in core.items()):
            raise PaperScheduleError("PAPER_SCHEDULE_POLICY_BINDING_MISMATCH")
        state = projection.get(slot_id)
        if state is None:
            state = {
                "slot_id": slot_id,
                **core,
                "status": "UNSEEN",
                "attempt_count": 0,
                "failure_count": 0,
                "last_event_at": event_time_text,
                "active_claim": None,
                "prepared": None,
            }
            projection[slot_id] = state
        elif any(state[name] != value for name, value in core.items()):
            raise PaperScheduleError("PAPER_SCHEDULE_SLOT_BINDING_CHANGED")
        status = state["status"]
        if status in _TERMINAL:
            raise PaperScheduleError("PAPER_SCHEDULE_TERMINAL_SLOT_MUTATED")

        if event_type == "SLOT_MISSED":
            if status != "UNSEEN" or payload.get("reason_code") != (
                "MISSED_NO_CONTEMPORANEOUS_CAPTURE"
            ):
                raise PaperScheduleError("PAPER_SCHEDULE_TRANSITION_INVALID")
            state["status"] = "MISSED"
        elif event_type == "SLOT_EXPIRED":
            if status == "UNSEEN":
                raise PaperScheduleError("PAPER_SCHEDULE_TRANSITION_INVALID")
            if event_time < _utc(slot.expires_at)[0]:
                raise PaperScheduleError("PAPER_SCHEDULE_EXPIRED_EARLY")
            state["status"] = "EXPIRED"
        elif event_type == "SLOT_CLAIMED":
            worker = _worker_id(payload.get("worker_id"))
            attempt = payload.get("attempt")
            if (
                isinstance(attempt, bool)
                or not isinstance(attempt, int)
                or attempt != state["attempt_count"] + 1
            ):
                raise PaperScheduleError("PAPER_SCHEDULE_ATTEMPT_INVALID")
            lease_dt, lease_text = _utc(payload.get("lease_expires_at"))
            if lease_dt != event_time + _LEASE:
                raise PaperScheduleError("PAPER_SCHEDULE_LEASE_INVALID")
            prior_claim = state["active_claim"]
            if (
                status in ("CLAIMED", "PREPARED")
                and prior_claim is not None
                and event_time < _utc(prior_claim["lease_expires_at"])[0]
            ):
                raise PaperScheduleError("PAPER_SCHEDULE_LIVE_LEASE_RECLAIMED")
            state["attempt_count"] = attempt
            state["active_claim"] = {
                "worker_id": worker,
                "attempt": attempt,
                "claim_event_id": source["event_id"],
                "claimed_at": event_time_text,
                "lease_expires_at": lease_text,
            }
            state["status"] = "PREPARED" if state["prepared"] else "CLAIMED"
        elif event_type == "RUN_FAILED":
            claim = state["active_claim"]
            if (
                status != "CLAIMED"
                or claim is None
                or payload.get("worker_id") != claim["worker_id"]
                or payload.get("attempt") != claim["attempt"]
                or not isinstance(payload.get("reason_code"), str)
                or not payload["reason_code"]
            ):
                raise PaperScheduleError("PAPER_SCHEDULE_TRANSITION_INVALID")
            state["failure_count"] += 1
            state["status"] = "FAILED"
        elif event_type == "RUN_PREPARED":
            claim = state["active_claim"]
            if (
                status != "CLAIMED"
                or claim is None
                or state["prepared"] is not None
                or payload.get("worker_id") != claim["worker_id"]
                or payload.get("attempt") != claim["attempt"]
            ):
                raise PaperScheduleError("PAPER_SCHEDULE_TRANSITION_INVALID")
            required = (
                "artifact_name",
                "artifact_sha256",
                "cycle_run_hash",
                "cycle_trust_hash",
                "output_root_hash",
                "decision_time",
            )
            if any(not isinstance(payload.get(name), str) or not payload[name] for name in required):
                raise PaperScheduleError("PAPER_SCHEDULE_PREPARED_INVALID")
            state["prepared"] = {
                name: payload[name] for name in required
            }
            state["prepared"]["source_event_id"] = source["event_id"]
            state["status"] = "PREPARED"
        elif event_type == "RUN_SUCCEEDED":
            claim = state["active_claim"]
            prepared = state["prepared"]
            if (
                status != "PREPARED"
                or claim is None
                or prepared is None
                or payload.get("worker_id") != claim["worker_id"]
                or payload.get("attempt") != claim["attempt"]
                or any(
                    payload.get(name) != prepared[name]
                    for name in (
                        "artifact_name",
                        "artifact_sha256",
                        "cycle_run_hash",
                        "cycle_trust_hash",
                        "output_root_hash",
                    )
                )
            ):
                raise PaperScheduleError("PAPER_SCHEDULE_TRANSITION_INVALID")
            state["status"] = "SUCCEEDED"
        state["last_event_at"] = event_time_text
        previous_sequence = sequence
        previous_hash = source["event_hash"]
        previous_time = event_time
    return projection


def _validate_state_path(path: Path) -> None:
    path = Path(path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        parent_entry = parent.lstat()
        if stat.S_ISLNK(parent_entry.st_mode) or not stat.S_ISDIR(
            parent_entry.st_mode
        ):
            raise PaperScheduleError("PAPER_SCHEDULE_STATE_PATH_INVALID")
        if path.exists() or path.is_symlink():
            entry = path.lstat()
            if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode):
                raise PaperScheduleError("PAPER_SCHEDULE_STATE_PATH_INVALID")
    except OSError as error:
        raise PaperScheduleError("PAPER_SCHEDULE_STATE_PATH_INVALID") from error


class PaperScheduleState:
    """Append-only WAL state; no update/delete path is exposed."""

    def __init__(self, path: Path, policy: PaperSchedulePolicy):
        if not isinstance(policy, PaperSchedulePolicy):
            raise PaperScheduleError("PAPER_SCHEDULE_POLICY_INVALID")
        self.path = Path(path)
        self.policy = policy
        _validate_state_path(self.path)
        self.connection = sqlite3.connect(str(self.path), timeout=0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        mode = self.connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            raise PaperScheduleError("PAPER_SCHEDULE_WAL_REQUIRED")
        self.connection.execute("PRAGMA synchronous = FULL")
        self._create_schema()
        self.verify_integrity()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "PaperScheduleState":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schedule_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                previous_event_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS prepared_blobs (
                source_event_id TEXT PRIMARY KEY,
                slot_id TEXT NOT NULL UNIQUE,
                artifact_name TEXT NOT NULL,
                artifact_bytes BLOB NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                cycle_run_hash TEXT NOT NULL,
                cycle_trust_hash TEXT NOT NULL,
                output_root_hash TEXT NOT NULL,
                FOREIGN KEY(source_event_id) REFERENCES schedule_events(event_id)
            );
            CREATE TRIGGER IF NOT EXISTS schedule_events_no_update
            BEFORE UPDATE ON schedule_events
            BEGIN SELECT RAISE(ABORT, 'schedule events are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS schedule_events_no_delete
            BEFORE DELETE ON schedule_events
            BEGIN SELECT RAISE(ABORT, 'schedule events are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS prepared_blobs_no_update
            BEFORE UPDATE ON prepared_blobs
            BEGIN SELECT RAISE(ABORT, 'prepared blobs are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS prepared_blobs_no_delete
            BEFORE DELETE ON prepared_blobs
            BEGIN SELECT RAISE(ABORT, 'prepared blobs are immutable'); END;
            """
        )

    def events(self) -> Tuple[Dict[str, Any], ...]:
        results = []
        for row in self.connection.execute(
            "SELECT * FROM schedule_events ORDER BY sequence"
        ).fetchall():
            results.append(
                {
                    "sequence": row["sequence"],
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "slot_id": row["slot_id"],
                    "event_time": row["event_time"],
                    "payload": json.loads(row["payload_json"]),
                    "payload_hash": row["payload_hash"],
                    "previous_event_hash": row["previous_event_hash"],
                    "event_hash": row["event_hash"],
                }
            )
        return tuple(results)

    def slot_projection(self) -> Dict[str, Dict[str, Any]]:
        return _project_events(self.events(), self.policy)

    def verify_integrity(self) -> str:
        events = self.events()
        projection = _project_events(events, self.policy)
        prepared_event_ids = {
            item["prepared"]["source_event_id"]
            for item in projection.values()
            if item["prepared"] is not None
        }
        rows = self.connection.execute(
            "SELECT * FROM prepared_blobs ORDER BY source_event_id"
        ).fetchall()
        if {row["source_event_id"] for row in rows} != prepared_event_ids:
            raise PaperScheduleError("PAPER_SCHEDULE_PREPARED_BLOB_SET_MISMATCH")
        for row in rows:
            artifact_bytes = bytes(row["artifact_bytes"])
            if hashlib.sha256(artifact_bytes).hexdigest() != row["artifact_sha256"]:
                raise PaperScheduleError("PAPER_SCHEDULE_PREPARED_BLOB_HASH_MISMATCH")
            state = projection.get(row["slot_id"])
            if state is None or state["prepared"] is None:
                raise PaperScheduleError("PAPER_SCHEDULE_PREPARED_BLOB_ORPHAN")
            prepared = state["prepared"]
            for name in (
                "artifact_name",
                "artifact_sha256",
                "cycle_run_hash",
                "cycle_trust_hash",
                "output_root_hash",
            ):
                if row[name] != prepared[name]:
                    raise PaperScheduleError("PAPER_SCHEDULE_PREPARED_BLOB_MISMATCH")
            try:
                run = json.loads(artifact_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise PaperScheduleError("PAPER_SCHEDULE_PREPARED_JSON_INVALID") from error
            if (
                run.get("run_hash") != row["cycle_run_hash"]
                or offline_paper_run_reasons(run, row["cycle_trust_hash"])
            ):
                raise PaperScheduleError("PAPER_SCHEDULE_PREPARED_RUN_INVALID")
        return events[-1]["event_hash"] if events else _GENESIS_HASH

    def _append_locked(
        self,
        event_type: str,
        slot: PaperSlot,
        event_time: object,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        if event_type not in _ALLOWED_EVENTS:
            raise PaperScheduleError("PAPER_SCHEDULE_EVENT_TYPE_INVALID")
        event_dt, event_text = _utc(event_time)
        last = self.connection.execute(
            "SELECT sequence, event_time, event_hash FROM schedule_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 1 if last is None else int(last["sequence"]) + 1
        previous_hash = _GENESIS_HASH if last is None else last["event_hash"]
        if last is not None and event_dt < _utc(last["event_time"])[0]:
            raise PaperScheduleError("PAPER_SCHEDULE_EVENT_TIME_ORDER_INVALID")
        normalized_payload = json.loads(canonical_json(dict(payload)))
        payload_hash = business_hash(normalized_payload)
        identity = {
            "sequence": sequence,
            "event_type": event_type,
            "slot_id": slot.slot_id,
            "event_time": event_text,
            "payload_hash": payload_hash,
            "previous_event_hash": previous_hash,
        }
        event_id = stable_id("schedule_event", identity)
        body = {
            "sequence": sequence,
            "event_id": event_id,
            "event_type": event_type,
            "slot_id": slot.slot_id,
            "event_time": event_text,
            "payload": normalized_payload,
            "payload_hash": payload_hash,
            "previous_event_hash": previous_hash,
        }
        event_hash = business_hash(body)
        self.connection.execute(
            """
            INSERT INTO schedule_events (
                event_id, event_type, slot_id, event_time, payload_json,
                payload_hash, previous_event_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_type,
                slot.slot_id,
                event_text,
                canonical_json(normalized_payload),
                payload_hash,
                previous_hash,
                event_hash,
            ),
        )
        return {**body, "event_hash": event_hash}

    def _transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")

    def claim(
        self,
        slot: PaperSlot,
        *,
        worker_id: str,
        claimed_at: object,
    ) -> ClaimResult:
        worker = _worker_id(worker_id)
        now, now_text = _utc(claimed_at)
        try:
            self._transaction()
            self.verify_integrity()
            state = self.slot_projection().get(slot.slot_id)
            prepared = None if state is None else state["prepared"]
            if state is not None and state["status"] == "SUCCEEDED":
                self.connection.commit()
                claim = state["active_claim"]
                return ClaimResult(
                    "ALREADY_SUCCEEDED",
                    slot,
                    worker,
                    state["attempt_count"],
                    now_text,
                    claim["lease_expires_at"],
                    None,
                    prepared,
                )
            if state is not None and state["status"] in ("MISSED", "EXPIRED"):
                self.connection.commit()
                return ClaimResult(
                    "TERMINAL_INELIGIBLE",
                    slot,
                    worker,
                    state["attempt_count"],
                    now_text,
                    now_text,
                    None,
                    prepared,
                )
            if not _utc(slot.due_at)[0] <= now < _utc(slot.expires_at)[0]:
                raise PaperScheduleError("PAPER_SCHEDULE_SLOT_NOT_ACTIVE")
            if (
                state is not None
                and state["status"] in ("CLAIMED", "PREPARED")
                and now < _utc(state["active_claim"]["lease_expires_at"])[0]
            ):
                self.connection.commit()
                claim = state["active_claim"]
                return ClaimResult(
                    "BUSY",
                    slot,
                    worker,
                    state["attempt_count"],
                    claim["claimed_at"],
                    claim["lease_expires_at"],
                    claim["claim_event_id"],
                    prepared,
                )
            attempt = 1 if state is None else state["attempt_count"] + 1
            lease_text = utc_datetime(now + _LEASE)
            payload = {
                **_slot_core(slot, self.policy),
                "worker_id": worker,
                "attempt": attempt,
                "lease_expires_at": lease_text,
            }
            event = self._append_locked(
                "SLOT_CLAIMED", slot, now_text, payload
            )
            self.verify_integrity()
            self.connection.commit()
            return ClaimResult(
                "RESUME_PREPARED" if prepared else "CLAIMED",
                slot,
                worker,
                attempt,
                now_text,
                lease_text,
                event["event_id"],
                prepared,
            )
        except Exception:
            self.connection.rollback()
            raise

    def fail(
        self,
        claim: ClaimResult,
        *,
        reason_code: str,
        failed_at: object,
    ) -> None:
        if not isinstance(reason_code, str) or not reason_code:
            raise PaperScheduleError("PAPER_SCHEDULE_FAILURE_REASON_INVALID")
        try:
            self._transaction()
            self.verify_integrity()
            state = self.slot_projection().get(claim.slot.slot_id)
            if (
                state is None
                or state["status"] != "CLAIMED"
                or state["active_claim"]["worker_id"] != claim.worker_id
                or state["active_claim"]["attempt"] != claim.attempt
            ):
                raise PaperScheduleError("PAPER_SCHEDULE_CLAIM_OWNERSHIP_LOST")
            self._append_locked(
                "RUN_FAILED",
                claim.slot,
                failed_at,
                {
                    **_slot_core(claim.slot, self.policy),
                    "worker_id": claim.worker_id,
                    "attempt": claim.attempt,
                    "reason_code": reason_code,
                },
            )
            self.verify_integrity()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def prepare(
        self,
        claim: ClaimResult,
        *,
        artifact_name: str,
        artifact_bytes: bytes,
        cycle_run_hash: str,
        cycle_trust_hash: str,
        output_root_hash: str,
        prepared_at: object,
    ) -> Mapping[str, Any]:
        if (
            not isinstance(artifact_bytes, bytes)
            or not artifact_bytes
            or artifact_name != _artifact_name(claim.slot)
            or "/" in artifact_name
            or "\\" in artifact_name
        ):
            raise PaperScheduleError("PAPER_SCHEDULE_PREPARED_INVALID")
        artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
        try:
            run = json.loads(artifact_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PaperScheduleError("PAPER_SCHEDULE_PREPARED_JSON_INVALID") from error
        decision, _ = _utc(run.get("decision_time"))
        if (
            run.get("run_id") != _run_id(claim.slot)
            or run.get("run_hash") != cycle_run_hash
            or not _utc(claim.slot.due_at)[0]
            <= decision
            < _utc(claim.slot.expires_at)[0]
            or offline_paper_run_reasons(run, cycle_trust_hash)
        ):
            raise PaperScheduleError("PAPER_SCHEDULE_PREPARED_RUN_INVALID")
        try:
            self._transaction()
            self.verify_integrity()
            state = self.slot_projection().get(claim.slot.slot_id)
            if (
                state is None
                or state["status"] != "CLAIMED"
                or state["active_claim"]["worker_id"] != claim.worker_id
                or state["active_claim"]["attempt"] != claim.attempt
            ):
                raise PaperScheduleError("PAPER_SCHEDULE_CLAIM_OWNERSHIP_LOST")
            payload = {
                **_slot_core(claim.slot, self.policy),
                "worker_id": claim.worker_id,
                "attempt": claim.attempt,
                "artifact_name": artifact_name,
                "artifact_sha256": artifact_sha,
                "cycle_run_hash": cycle_run_hash,
                "cycle_trust_hash": cycle_trust_hash,
                "output_root_hash": output_root_hash,
                "decision_time": run["decision_time"],
            }
            event = self._append_locked(
                "RUN_PREPARED", claim.slot, prepared_at, payload
            )
            self.connection.execute(
                """
                INSERT INTO prepared_blobs (
                    source_event_id, slot_id, artifact_name, artifact_bytes,
                    artifact_sha256, cycle_run_hash, cycle_trust_hash,
                    output_root_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    claim.slot.slot_id,
                    artifact_name,
                    artifact_bytes,
                    artifact_sha,
                    cycle_run_hash,
                    cycle_trust_hash,
                    output_root_hash,
                ),
            )
            self.verify_integrity()
            self.connection.commit()
            return payload
        except Exception:
            self.connection.rollback()
            raise

    def load_prepared(self, slot: PaperSlot) -> Dict[str, Any]:
        self.verify_integrity()
        row = self.connection.execute(
            "SELECT * FROM prepared_blobs WHERE slot_id = ?",
            (slot.slot_id,),
        ).fetchone()
        if row is None:
            raise PaperScheduleError("PAPER_SCHEDULE_PREPARED_MISSING")
        return {
            "source_event_id": row["source_event_id"],
            "artifact_name": row["artifact_name"],
            "artifact_bytes": bytes(row["artifact_bytes"]),
            "artifact_sha256": row["artifact_sha256"],
            "cycle_run_hash": row["cycle_run_hash"],
            "cycle_trust_hash": row["cycle_trust_hash"],
            "output_root_hash": row["output_root_hash"],
        }

    def succeed(
        self,
        claim: ClaimResult,
        *,
        completed_at: object,
    ) -> None:
        try:
            self._transaction()
            self.verify_integrity()
            state = self.slot_projection().get(claim.slot.slot_id)
            if (
                state is None
                or state["status"] != "PREPARED"
                or state["active_claim"]["worker_id"] != claim.worker_id
                or state["active_claim"]["attempt"] != claim.attempt
            ):
                raise PaperScheduleError("PAPER_SCHEDULE_CLAIM_OWNERSHIP_LOST")
            prepared = state["prepared"]
            self._append_locked(
                "RUN_SUCCEEDED",
                claim.slot,
                completed_at,
                {
                    **_slot_core(claim.slot, self.policy),
                    "worker_id": claim.worker_id,
                    "attempt": claim.attempt,
                    **{
                        name: prepared[name]
                        for name in (
                            "artifact_name",
                            "artifact_sha256",
                            "cycle_run_hash",
                            "cycle_trust_hash",
                            "output_root_hash",
                        )
                    },
                },
            )
            self.verify_integrity()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def record_gaps(self, current_slot: PaperSlot, *, recorded_at: object) -> None:
        recorded_dt, recorded_text = _utc(recorded_at)
        try:
            self._transaction()
            self.verify_integrity()
            projection = self.slot_projection()
            if not projection:
                self.connection.commit()
                return
            current_scheduled = _utc(current_slot.scheduled_for)[0]
            known_before = [
                state
                for state in projection.values()
                if _utc(state["scheduled_for"])[0] < current_scheduled
            ]
            for state in sorted(
                known_before, key=lambda item: item["scheduled_for"]
            ):
                if state["status"] not in _TERMINAL:
                    slot = self.policy.slot_from_scheduled(state["scheduled_for"])
                    if recorded_dt < _utc(slot.expires_at)[0]:
                        continue
                    self._append_locked(
                        "SLOT_EXPIRED",
                        slot,
                        recorded_text,
                        {
                            **_slot_core(slot, self.policy),
                            "reason_code": "CAPTURE_WINDOW_EXPIRED",
                        },
                    )
            latest_scheduled = max(
                _utc(state["scheduled_for"])[0] for state in projection.values()
            )
            candidate = latest_scheduled + _CADENCE
            while candidate < current_scheduled:
                slot = self.policy.slot_from_scheduled(candidate)
                if slot.slot_id not in projection:
                    self._append_locked(
                        "SLOT_MISSED",
                        slot,
                        recorded_text,
                        {
                            **_slot_core(slot, self.policy),
                            "reason_code": "MISSED_NO_CONTEMPORANEOUS_CAPTURE",
                        },
                    )
                candidate += _CADENCE
            self.verify_integrity()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise


def _run_id(slot: PaperSlot) -> str:
    return "paper-slot-" + slot.slot_id.lower()


def _artifact_name(slot: PaperSlot) -> str:
    return _run_id(slot) + ".json"


def _output_root_hash(output_root: Path) -> str:
    return business_hash(
        {
            "purpose": "OFFLINE_PAPER_IMMUTABLE_OUTPUT_ROOT",
            "resolved_path": str(Path(output_root).resolve()),
        }
    )


def _summary_from_projection(
    projection: Mapping[str, Mapping[str, Any]]
) -> Dict[str, Any]:
    ordered = sorted(projection.values(), key=lambda item: item["scheduled_for"])
    statuses = [item["status"] for item in ordered]
    if ordered:
        first_dt = _utc(ordered[0]["scheduled_for"])[0]
        last_dt = _utc(ordered[-1]["scheduled_for"])[0]
        expected = int((last_dt - first_dt) / _CADENCE) + 1
        days = (last_dt.date() - first_dt.date()).days + 1
    else:
        expected = 0
        days = 0
    succeeded = statuses.count("SUCCEEDED")
    continuous = bool(ordered) and succeeded == expected and all(
        status == "SUCCEEDED" for status in statuses
    )
    return {
        "known_slot_count": len(ordered),
        "expected_slot_count_between_bounds": expected,
        "succeeded_slot_count": succeeded,
        "missed_slot_count": statuses.count("MISSED"),
        "expired_slot_count": statuses.count("EXPIRED"),
        "transient_failed_slot_count": statuses.count("FAILED"),
        "claimed_slot_count": statuses.count("CLAIMED"),
        "prepared_slot_count": statuses.count("PREPARED"),
        "first_scheduled_for_or_null": (
            ordered[0]["scheduled_for"] if ordered else None
        ),
        "last_scheduled_for_or_null": (
            ordered[-1]["scheduled_for"] if ordered else None
        ),
        "observed_calendar_days": days,
        "continuous_success": continuous,
        "ninety_day_complete": continuous and days >= 90 and succeeded >= 540,
    }


def _public_slot_projection(
    projection: Mapping[str, Mapping[str, Any]]
) -> Sequence[Mapping[str, Any]]:
    results = []
    for state in sorted(projection.values(), key=lambda item: item["scheduled_for"]):
        prepared = state["prepared"]
        results.append(
            {
                "slot_id": state["slot_id"],
                "scheduled_for": state["scheduled_for"],
                "due_at": state["due_at"],
                "expires_at": state["expires_at"],
                "status": state["status"],
                "attempt_count": state["attempt_count"],
                "failure_count": state["failure_count"],
                "last_event_at": state["last_event_at"],
                "artifact_name_or_null": (
                    prepared["artifact_name"] if prepared else None
                ),
                "artifact_sha256_or_null": (
                    prepared["artifact_sha256"] if prepared else None
                ),
                "cycle_run_hash_or_null": (
                    prepared["cycle_run_hash"] if prepared else None
                ),
                "cycle_trust_hash_or_null": (
                    prepared["cycle_trust_hash"] if prepared else None
                ),
            }
        )
    return results


def build_schedule_snapshot(
    state: PaperScheduleState,
    *,
    recorded_at: Optional[object] = None,
) -> Dict[str, Any]:
    if not isinstance(state, PaperScheduleState):
        raise PaperScheduleError("PAPER_SCHEDULE_STATE_INVALID")
    chain_end = state.verify_integrity()
    events = list(state.events())
    projection = _project_events(events, state.policy)
    summary = _summary_from_projection(projection)
    if recorded_at is None:
        selected = events[-1]["event_time"] if events else utc_datetime(
            datetime.now(timezone.utc)
        )
    else:
        selected = _utc(recorded_at)[1]
    if events and _utc(selected)[0] < _utc(events[-1]["event_time"])[0]:
        raise PaperScheduleError("PAPER_SCHEDULE_SNAPSHOT_TIME_INVALID")
    snapshot = {
        "$schema": "./paper-schedule-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": stable_id(
            "paper_schedule",
            {
                "schedule_id": state.policy.schedule_id,
                "event_chain_end_hash": chain_end,
            },
        ),
        "snapshot_hash": "0" * 64,
        "recorded_at": selected,
        "policy": {
            **state.policy.business_payload(),
            "policy_hash": state.policy.policy_hash,
        },
        "events": events,
        "events_root_hash": business_hash(events),
        "event_chain_end_hash": chain_end,
        "slots": list(_public_slot_projection(projection)),
        "summary": summary,
        "state_integrity": "VERIFIED_APPEND_ONLY_WAL",
        "scheduler_eligibility": "SCHEDULER_OPERATIONAL_SMOKE_ONLY",
        "paper_eligibility": "LONGITUDINAL_COLLECTION_IN_PROGRESS",
        "profitability_eligibility": "INSUFFICIENT_DURATION_COST_AND_AI",
        "warnings": (
            ([] if summary["ninety_day_complete"] else [
                "PAPER_DURATION_BELOW_90_DAYS"
            ])
            + list(_WARNINGS)
        ),
    }
    snapshot["snapshot_hash"] = artifact_self_hash(snapshot, "snapshot_hash")
    if tuple(_snapshot_validator().iter_errors(snapshot)):
        raise PaperScheduleError("PAPER_SCHEDULE_SNAPSHOT_SCHEMA_INVALID")
    return snapshot


def schedule_snapshot_trust_hash(snapshot: Mapping[str, Any]) -> str:
    try:
        return business_hash(
            {
                "attestation_type": _SCHEDULE_ATTESTATION_TYPE,
                "snapshot_id": snapshot["snapshot_id"],
                "snapshot_hash": snapshot["snapshot_hash"],
                "schedule_policy_hash": snapshot["policy"]["policy_hash"],
                "events_root_hash": snapshot["events_root_hash"],
                "event_chain_end_hash": snapshot["event_chain_end_hash"],
                "successful_cycle_trust_hashes": [
                    item["cycle_trust_hash_or_null"]
                    for item in snapshot["slots"]
                    if item["status"] == "SUCCEEDED"
                ],
            }
        )
    except (KeyError, TypeError):
        return ""


def schedule_snapshot_reasons(
    snapshot: Mapping[str, Any],
    trusted_attestation_hash: str,
) -> Tuple[str, ...]:
    if not isinstance(snapshot, Mapping):
        return ("PAPER_SCHEDULE_SNAPSHOT_INVALID",)
    reasons = []
    if tuple(_snapshot_validator().iter_errors(snapshot)):
        reasons.append("PAPER_SCHEDULE_SNAPSHOT_SCHEMA_INVALID")
    try:
        if artifact_self_hash(snapshot, "snapshot_hash") != snapshot.get(
            "snapshot_hash"
        ):
            reasons.append("PAPER_SCHEDULE_SELF_HASH_MISMATCH")
    except Exception:
        reasons.append("PAPER_SCHEDULE_NOT_CANONICAL")
    if schedule_snapshot_trust_hash(snapshot) != trusted_attestation_hash:
        reasons.append("PAPER_SCHEDULE_TRUST_HASH_MISMATCH")
    try:
        policy = PaperSchedulePolicy.create(symbol=snapshot["policy"]["symbol"])
        if snapshot["policy"] != {
            **policy.business_payload(),
            "policy_hash": policy.policy_hash,
        }:
            reasons.append("PAPER_SCHEDULE_POLICY_MISMATCH")
        events = snapshot["events"]
        projection = _project_events(events, policy)
        if business_hash(events) != snapshot.get("events_root_hash"):
            reasons.append("PAPER_SCHEDULE_EVENTS_ROOT_MISMATCH")
        expected_end = events[-1]["event_hash"] if events else _GENESIS_HASH
        if expected_end != snapshot.get("event_chain_end_hash"):
            reasons.append("PAPER_SCHEDULE_CHAIN_END_MISMATCH")
        if list(_public_slot_projection(projection)) != snapshot.get("slots"):
            reasons.append("PAPER_SCHEDULE_SLOT_PROJECTION_MISMATCH")
        if _summary_from_projection(projection) != snapshot.get("summary"):
            reasons.append("PAPER_SCHEDULE_SUMMARY_MISMATCH")
    except (KeyError, PaperScheduleError, TypeError, ValueError):
        reasons.append("PAPER_SCHEDULE_REPLAY_INVALID")
    for name, expected in (
        ("scheduler_eligibility", "SCHEDULER_OPERATIONAL_SMOKE_ONLY"),
        ("paper_eligibility", "LONGITUDINAL_COLLECTION_IN_PROGRESS"),
        (
            "profitability_eligibility",
            "INSUFFICIENT_DURATION_COST_AND_AI",
        ),
    ):
        if snapshot.get(name) != expected:
            reasons.append("PAPER_SCHEDULE_ELIGIBILITY_INVALID")
    return tuple(sorted(set(reasons)))


def _clock_value(clock) -> str:
    value = clock() if callable(clock) else clock
    return _utc(value)[1]


def run_due_paper_cycle(
    *,
    state_path: Path,
    output_root: Path,
    worker_id: str,
    transport=None,
    clock=None,
    fault_after_prepare: bool = False,
    fault_after_publish: bool = False,
) -> Dict[str, Any]:
    from .offline_paper import _utc_now

    selected_clock = clock or _utc_now
    policy = PaperSchedulePolicy.create()
    invocation_time = _clock_value(selected_clock)
    slot = policy.current_slot(invocation_time)
    output = Path(output_root)
    root_hash = _output_root_hash(output)
    with PaperScheduleState(Path(state_path), policy) as state:
        state.record_gaps(slot, recorded_at=invocation_time)
        claim = state.claim(
            slot,
            worker_id=worker_id,
            claimed_at=invocation_time,
        )
        if claim.outcome == "BUSY":
            return {
                "outcome": "BUSY",
                "slot_id": slot.slot_id,
                "network_request_count": 0,
                "lease_expires_at": claim.lease_expires_at,
            }
        if claim.outcome == "TERMINAL_INELIGIBLE":
            raise PaperScheduleError("PAPER_SCHEDULE_SLOT_TERMINAL")
        prepared_before = claim.prepared is not None
        try:
            if prepared_before or claim.outcome == "ALREADY_SUCCEEDED":
                prepared = state.load_prepared(slot)
                if prepared["output_root_hash"] != root_hash:
                    raise PaperScheduleError(
                        "PAPER_SCHEDULE_OUTPUT_ROOT_MISMATCH"
                    )
                network_count = 0
            else:
                plan = OfflinePaperPlan.create("ETHUSDT")
                selected_transport = transport or BinanceOfflinePaperTransport(
                    clock=selected_clock
                )
                capture = capture_offline_paper(
                    plan,
                    selected_transport,
                    recorded_at=selected_clock,
                )
                run = build_offline_paper_run(
                    capture,
                    run_id=_run_id(slot),
                    recorded_at=_clock_value(selected_clock),
                )
                artifact_bytes = json.dumps(
                    run, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                trust_hash = offline_paper_run_trust_hash(run)
                state.prepare(
                    claim,
                    artifact_name=_artifact_name(slot),
                    artifact_bytes=artifact_bytes,
                    cycle_run_hash=run["run_hash"],
                    cycle_trust_hash=trust_hash,
                    output_root_hash=root_hash,
                    prepared_at=_clock_value(selected_clock),
                )
                prepared = state.load_prepared(slot)
                network_count = 4
                if fault_after_prepare:
                    raise PaperScheduleError("INJECTED_AFTER_PREPARE")
            artifact_path = output.resolve() / "paper" / prepared["artifact_name"]
            created = _publish_immutable(
                output,
                prepared["artifact_name"],
                prepared["artifact_bytes"],
                output_directory="paper",
            )
            if fault_after_publish:
                raise PaperScheduleError("INJECTED_AFTER_PUBLISH")
            if claim.outcome not in ("ALREADY_SUCCEEDED",):
                state.succeed(claim, completed_at=_clock_value(selected_clock))
            snapshot = build_schedule_snapshot(state)
            snapshot_trust = schedule_snapshot_trust_hash(snapshot)
            if schedule_snapshot_reasons(snapshot, snapshot_trust):
                raise PaperScheduleError("PAPER_SCHEDULE_SNAPSHOT_INVALID")
            snapshot_name = (
                "paper-schedule-" + slot.slot_id.lower() + ".json"
            )
            snapshot_bytes = json.dumps(
                snapshot, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            snapshot_path = output.resolve() / "paper" / snapshot_name
            snapshot_created = _publish_immutable(
                output,
                snapshot_name,
                snapshot_bytes,
                output_directory="paper",
            )
            outcome = (
                "ALREADY_SUCCEEDED"
                if claim.outcome == "ALREADY_SUCCEEDED"
                else "RESUMED_PREPARED"
                if prepared_before
                else "EXECUTED"
            )
            return {
                "outcome": outcome,
                "slot_id": slot.slot_id,
                "network_request_count": network_count,
                "artifact_path": str(artifact_path),
                "artifact_created": created,
                "cycle_run_hash": prepared["cycle_run_hash"],
                "cycle_trust_hash": prepared["cycle_trust_hash"],
                "schedule_snapshot_path": str(snapshot_path),
                "schedule_snapshot_created": snapshot_created,
                "schedule_snapshot": snapshot,
                "schedule_snapshot_hash": snapshot["snapshot_hash"],
                "schedule_trust_hash": snapshot_trust,
                "scheduler_eligibility": snapshot["scheduler_eligibility"],
                "paper_eligibility": snapshot["paper_eligibility"],
                "profitability_eligibility": snapshot[
                    "profitability_eligibility"
                ],
            }
        except Exception as error:
            if not prepared_before and claim.outcome == "CLAIMED":
                current = state.slot_projection().get(slot.slot_id)
                if current is not None and current["status"] == "CLAIMED":
                    reason = getattr(error, "reason_code", type(error).__name__)
                    state.fail(
                        claim,
                        reason_code=str(reason),
                        failed_at=_clock_value(selected_clock),
                    )
            if isinstance(error, PaperScheduleError):
                raise
            if isinstance(error, (OfflinePaperError, MarketDataError)):
                raise PaperScheduleError(error.reason_code) from error
            raise
