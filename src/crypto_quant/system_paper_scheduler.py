"""Crash-safe, append-only scheduling primitives for System Paper slots."""

import json
import sqlite3
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .system_paper_plan import system_paper_plan_reasons


_POLICY_TOKEN = object()
_SLOT_TOKEN = object()
_CADENCE = timedelta(hours=4)
_CLOSE_DELAY = timedelta(minutes=5)
_LEASE = timedelta(minutes=15)
_GENESIS_HASH = "0" * 64
_ALLOWED_EVENTS = frozenset(
    (
        "CLAIMED",
        "INPUT_PREPARED",
        "RESULT_PREPARED",
        "SUCCEEDED",
        "FAILED",
        "MISSED",
        "EXPIRED",
    )
)
_TERMINAL_STATES = frozenset(("MISSED", "EXPIRED", "SUCCEEDED"))


class SystemPaperScheduleError(ValueError):
    """The System Paper schedule has failed closed."""

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
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_TIME_INVALID") from error
    else:
        raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    converted = converted.replace(
        microsecond=(converted.microsecond // 1000) * 1000
    )
    return converted, utc_datetime(converted)


@dataclass(frozen=True, init=False)
class SystemPaperSlot:
    slot_id: str
    scheduled_for: str
    due_at: str
    expires_at: str

    def __init__(self, *args: object, **kwargs: object) -> None:
        if kwargs.pop("_token", None) is not _SLOT_TOKEN:
            raise TypeError("SystemPaperSlot is issued by SystemPaperSchedulePolicy")
        for name in ("slot_id", "scheduled_for", "due_at", "expires_at"):
            object.__setattr__(self, name, kwargs[name])


@dataclass(frozen=True, init=False)
class SystemPaperSchedulePolicy:
    plan_hash: str
    schedule_policy_hash: str
    cadence_seconds: int
    close_delay_seconds: int
    lease_seconds: int
    historical_backfill_allowed: bool

    def __init__(self, *args: object, **kwargs: object) -> None:
        if kwargs.pop("_token", None) is not _POLICY_TOKEN:
            raise TypeError("SystemPaperSchedulePolicy must be created with create")
        plan_hash = kwargs["plan_hash"]
        if not isinstance(plan_hash, str) or not plan_hash:
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_POLICY_INVALID")
        payload = {
            "schema_version": "1.0.0",
            "plan_hash": plan_hash,
            "symbol": "ETHUSDT",
            "timezone": "UTC",
            "utc_anchor": "00:00:00",
            "cadence_seconds": 14_400,
            "close_delay_seconds": 300,
            "lease_seconds": 900,
            "historical_backfill_allowed": False,
        }
        object.__setattr__(self, "plan_hash", plan_hash)
        object.__setattr__(self, "schedule_policy_hash", business_hash(payload))
        object.__setattr__(self, "cadence_seconds", 14_400)
        object.__setattr__(self, "close_delay_seconds", 300)
        object.__setattr__(self, "lease_seconds", 900)
        object.__setattr__(self, "historical_backfill_allowed", False)

    @classmethod
    def create(cls, plan: Mapping[str, Any]) -> "SystemPaperSchedulePolicy":
        if not isinstance(plan, Mapping):
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_POLICY_INVALID")
        reasons = system_paper_plan_reasons(plan)
        if reasons:
            raise SystemPaperScheduleError(reasons[0])
        return cls(_token=_POLICY_TOKEN, plan_hash=plan["plan_hash"])

    def slot_from_scheduled(self, scheduled_for: object) -> SystemPaperSlot:
        scheduled, scheduled_text = _utc(scheduled_for)
        if (
            scheduled.minute != 0
            or scheduled.second != 0
            or scheduled.microsecond != 0
            or scheduled.hour % 4 != 0
        ):
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_SLOT_INVALID")
        due = scheduled + _CLOSE_DELAY
        expires = due + _CADENCE
        return SystemPaperSlot(
            slot_id=stable_id(
                "system_paper_slot",
                {
                    "plan_hash": self.plan_hash,
                    "scheduled_for": scheduled_text,
                },
            ),
            scheduled_for=scheduled_text,
            due_at=utc_datetime(due),
            expires_at=utc_datetime(expires),
            _token=_SLOT_TOKEN,
        )

    def current_slot(self, now: object) -> SystemPaperSlot:
        current, _ = _utc(now)
        shifted = current - _CLOSE_DELAY
        scheduled = shifted.replace(
            hour=(shifted.hour // 4) * 4,
            minute=0,
            second=0,
            microsecond=0,
        )
        return self.slot_from_scheduled(scheduled)


def _validate_state_path(path: Path) -> None:
    """Reject unsafe state identities and create at most its direct parent."""

    state_path = Path(path)
    parent = state_path.parent
    try:
        if not parent.exists():
            parent.mkdir()
        parent_entry = parent.lstat()
        if stat.S_ISLNK(parent_entry.st_mode) or not stat.S_ISDIR(parent_entry.st_mode):
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_STATE_PATH_INVALID")
        if state_path.exists() or state_path.is_symlink():
            entry = state_path.lstat()
            if (
                stat.S_ISLNK(entry.st_mode)
                or not stat.S_ISREG(entry.st_mode)
                or entry.st_nlink != 1
            ):
                raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_STATE_PATH_INVALID")
    except OSError as error:
        raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_STATE_PATH_INVALID") from error


def _worker_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 64
        or not value.isascii()
        or any(not (character.isalnum() or character in "._-") for character in value)
    ):
        raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_WORKER_INVALID")
    return value


def _slot_core(
    slot: SystemPaperSlot, policy: SystemPaperSchedulePolicy
) -> Dict[str, str]:
    return {
        "plan_hash": policy.plan_hash,
        "schedule_policy_hash": policy.schedule_policy_hash,
        "scheduled_for": slot.scheduled_for,
        "due_at": slot.due_at,
        "expires_at": slot.expires_at,
    }


def _slot_from_payload(
    slot_id: object, payload: Mapping[str, Any], policy: SystemPaperSchedulePolicy
) -> SystemPaperSlot:
    if not isinstance(slot_id, str):
        raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_SLOT_ID_MISMATCH")
    try:
        slot = policy.slot_from_scheduled(payload["scheduled_for"])
    except (KeyError, SystemPaperScheduleError) as error:
        raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_SLOT_INVALID") from error
    if (
        slot_id != slot.slot_id
        or payload.get("due_at") != slot.due_at
        or payload.get("expires_at") != slot.expires_at
        or payload.get("plan_hash") != policy.plan_hash
        or payload.get("schedule_policy_hash") != policy.schedule_policy_hash
    ):
        raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_POLICY_BINDING_MISMATCH")
    return slot


def _event_projection(
    events: Sequence[Mapping[str, Any]], policy: SystemPaperSchedulePolicy
) -> Dict[str, Dict[str, Any]]:
    projection: Dict[str, Dict[str, Any]] = {}
    previous_sequence = 0
    previous_hash = _GENESIS_HASH
    previous_time: Optional[datetime] = None
    for source in events:
        try:
            sequence = source["sequence"]
            event_type = source["event_type"]
            slot_id = source["slot_id"]
            event_time, event_time_text = _utc(source["event_time"])
            payload = source["payload"]
        except (KeyError, SystemPaperScheduleError) as error:
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_EVENT_INVALID") from error
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence != previous_sequence + 1
            or event_type not in _ALLOWED_EVENTS
            or not isinstance(payload, Mapping)
        ):
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_EVENT_INVALID")
        if previous_time is not None and event_time < previous_time:
            raise SystemPaperScheduleError(
                "SYSTEM_PAPER_SCHEDULE_EVENT_TIME_ORDER_INVALID"
            )
        if source.get("previous_event_hash") != previous_hash:
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_EVENT_CHAIN_INVALID")
        payload_hash = business_hash(payload)
        if source.get("payload_hash") != payload_hash:
            raise SystemPaperScheduleError(
                "SYSTEM_PAPER_SCHEDULE_EVENT_PAYLOAD_HASH_MISMATCH"
            )
        event_identity = {
            "sequence": sequence,
            "event_type": event_type,
            "slot_id": slot_id,
            "event_time": event_time_text,
            "payload_hash": payload_hash,
            "previous_event_hash": previous_hash,
        }
        if source.get("event_id") != stable_id(
            "system_paper_schedule_event", event_identity
        ):
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_EVENT_ID_MISMATCH")
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
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_EVENT_HASH_MISMATCH")
        slot = _slot_from_payload(slot_id, payload, policy)
        state = projection.get(slot.slot_id)
        if state is None:
            state = {
                "slot_id": slot.slot_id,
                **_slot_core(slot, policy),
                "attempt_status": "UNSEEN",
                "durable_stage": "NONE",
                "active_claim": None,
                "attempt_count": 0,
                "terminal_state": None,
                "last_event_at": event_time_text,
                "input_event_id": None,
                "result_event_id": None,
            }
            projection[slot.slot_id] = state
        elif any(state[name] != value for name, value in _slot_core(slot, policy).items()):
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_SLOT_BINDING_CHANGED")
        if state["terminal_state"] in _TERMINAL_STATES:
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_TERMINAL_SLOT_MUTATED")

        if event_type == "CLAIMED":
            worker = _worker_id(payload.get("worker_id"))
            attempt = payload.get("attempt")
            lease_at, lease_text = _utc(payload.get("lease_expires_at"))
            if (
                isinstance(attempt, bool)
                or not isinstance(attempt, int)
                or attempt != state["attempt_count"] + 1
                or lease_at != event_time + _LEASE
            ):
                raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_CLAIM_INVALID")
            active_claim = state["active_claim"]
            if active_claim is not None and event_time < _utc(
                active_claim["lease_expires_at"]
            )[0]:
                raise SystemPaperScheduleError(
                    "SYSTEM_PAPER_SCHEDULE_LIVE_LEASE_RECLAIMED"
                )
            state["attempt_count"] = attempt
            state["attempt_status"] = "CLAIMED"
            state["active_claim"] = {
                "worker_id": worker,
                "attempt": attempt,
                "claimed_at": event_time_text,
                "lease_expires_at": lease_text,
                "claim_event_id": source["event_id"],
            }
        elif event_type == "FAILED":
            active_claim = state["active_claim"]
            if (
                state["attempt_status"] != "CLAIMED"
                or active_claim is None
                or payload.get("worker_id") != active_claim["worker_id"]
                or payload.get("attempt") != active_claim["attempt"]
                or not isinstance(payload.get("reason_code"), str)
                or not payload["reason_code"]
            ):
                raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_TRANSITION_INVALID")
            state["attempt_status"] = "FAILED"
            state["active_claim"] = None
        elif event_type == "INPUT_PREPARED":
            active_claim = state["active_claim"]
            if (
                state["attempt_status"] != "CLAIMED"
                or state["durable_stage"] != "NONE"
                or active_claim is None
                or payload.get("worker_id") != active_claim["worker_id"]
                or payload.get("attempt") != active_claim["attempt"]
                or not isinstance(payload.get("input_sha256"), str)
            ):
                raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_TRANSITION_INVALID")
            state["durable_stage"] = "INPUT"
            state["input_event_id"] = source["event_id"]
        elif event_type == "RESULT_PREPARED":
            active_claim = state["active_claim"]
            if (
                state["attempt_status"] != "CLAIMED"
                or state["durable_stage"] != "INPUT"
                or active_claim is None
                or payload.get("worker_id") != active_claim["worker_id"]
                or payload.get("attempt") != active_claim["attempt"]
                or not isinstance(payload.get("result_sha256"), str)
            ):
                raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_TRANSITION_INVALID")
            state["durable_stage"] = "RESULT"
            state["result_event_id"] = source["event_id"]
        elif event_type == "SUCCEEDED":
            active_claim = state["active_claim"]
            if (
                state["attempt_status"] != "CLAIMED"
                or state["durable_stage"] != "RESULT"
                or active_claim is None
                or payload.get("worker_id") != active_claim["worker_id"]
                or payload.get("attempt") != active_claim["attempt"]
            ):
                raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_TRANSITION_INVALID")
            state["terminal_state"] = "SUCCEEDED"
            state["attempt_status"] = "SUCCEEDED"
        elif event_type == "MISSED":
            if (
                state["attempt_status"] != "UNSEEN"
                or state["durable_stage"] != "NONE"
                or payload.get("reason_code") != "MISSED_NO_CONTEMPORANEOUS_CAPTURE"
            ):
                raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_TRANSITION_INVALID")
            state["terminal_state"] = "MISSED"
            state["attempt_status"] = "MISSED"
        elif event_type == "EXPIRED":
            if (
                state["attempt_status"] == "UNSEEN"
                or state["durable_stage"] != "NONE"
                or event_time < _utc(slot.expires_at)[0]
                or payload.get("reason_code") != "EXPIRED_UNPREPARED_SLOT"
            ):
                raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_TRANSITION_INVALID")
            state["terminal_state"] = "EXPIRED"
            state["attempt_status"] = "EXPIRED"
            state["active_claim"] = None
        state["last_event_at"] = event_time_text
        previous_sequence = sequence
        previous_hash = source["event_hash"]
        previous_time = event_time
    return projection


@dataclass(frozen=True)
class SystemPaperClaim:
    outcome: str
    slot: SystemPaperSlot
    worker_id: str
    attempt: int
    claimed_at: str
    lease_expires_at: str
    durable_stage: str


class SystemPaperScheduleState:
    """SQLite WAL event chain for System Paper; all durable rows are immutable."""

    def __init__(self, path: Path, policy: SystemPaperSchedulePolicy):
        if not isinstance(policy, SystemPaperSchedulePolicy):
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_POLICY_INVALID")
        self.path = Path(path)
        self.policy = policy
        _validate_state_path(self.path)
        self.connection = sqlite3.connect(str(self.path), timeout=0)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA busy_timeout = 0")
            mode = self.connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if str(mode).lower() != "wal":
                raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_WAL_REQUIRED")
            self.connection.execute("PRAGMA synchronous = FULL")
            self._create_schema()
            self.verify_integrity()
        except Exception:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SystemPaperScheduleState":
        return self

    def __exit__(self, *_args: object) -> None:
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
            CREATE TABLE IF NOT EXISTS prepared_inputs (
                source_event_id TEXT PRIMARY KEY,
                slot_id TEXT NOT NULL UNIQUE,
                input_bytes BLOB NOT NULL,
                input_sha256 TEXT NOT NULL,
                plan_hash TEXT NOT NULL,
                market_bundle_hash TEXT NOT NULL,
                previous_snapshot_hash TEXT NOT NULL,
                fill_scenario_hash TEXT NOT NULL,
                output_root_hash TEXT NOT NULL,
                FOREIGN KEY(source_event_id) REFERENCES schedule_events(event_id)
            );
            CREATE TABLE IF NOT EXISTS prepared_results (
                source_event_id TEXT PRIMARY KEY,
                slot_id TEXT NOT NULL UNIQUE,
                result_bytes BLOB NOT NULL,
                result_sha256 TEXT NOT NULL,
                slot_hash TEXT NOT NULL,
                runtime_snapshot_hash TEXT NOT NULL,
                parent_slot_hash TEXT NOT NULL,
                output_root_hash TEXT NOT NULL,
                FOREIGN KEY(source_event_id) REFERENCES schedule_events(event_id)
            );
            CREATE TRIGGER IF NOT EXISTS schedule_events_no_update
            BEFORE UPDATE ON schedule_events
            BEGIN SELECT RAISE(ABORT, 'schedule events are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS schedule_events_no_delete
            BEFORE DELETE ON schedule_events
            BEGIN SELECT RAISE(ABORT, 'schedule events are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS prepared_inputs_no_update
            BEFORE UPDATE ON prepared_inputs
            BEGIN SELECT RAISE(ABORT, 'prepared inputs are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS prepared_inputs_no_delete
            BEFORE DELETE ON prepared_inputs
            BEGIN SELECT RAISE(ABORT, 'prepared inputs are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS prepared_results_no_update
            BEFORE UPDATE ON prepared_results
            BEGIN SELECT RAISE(ABORT, 'prepared results are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS prepared_results_no_delete
            BEFORE DELETE ON prepared_results
            BEGIN SELECT RAISE(ABORT, 'prepared results are immutable'); END;
            """
        )

    def events(self) -> Tuple[Dict[str, Any], ...]:
        events = []
        for row in self.connection.execute(
            "SELECT * FROM schedule_events ORDER BY sequence"
        ).fetchall():
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError as error:
                raise SystemPaperScheduleError(
                    "SYSTEM_PAPER_SCHEDULE_EVENT_PAYLOAD_INVALID"
                ) from error
            if row["payload_json"] != canonical_json(payload):
                raise SystemPaperScheduleError(
                    "SYSTEM_PAPER_SCHEDULE_EVENT_PAYLOAD_CANONICAL_INVALID"
                )
            events.append(
                {
                    "sequence": row["sequence"],
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "slot_id": row["slot_id"],
                    "event_time": row["event_time"],
                    "payload": payload,
                    "payload_hash": row["payload_hash"],
                    "previous_event_hash": row["previous_event_hash"],
                    "event_hash": row["event_hash"],
                }
            )
        return tuple(events)

    def slot_projection(self) -> Dict[str, Dict[str, Any]]:
        return _event_projection(self.events(), self.policy)

    def verify_integrity(self) -> str:
        events = self.events()
        projection = _event_projection(events, self.policy)
        input_ids = {
            item["input_event_id"]
            for item in projection.values()
            if item["input_event_id"] is not None
        }
        result_ids = {
            item["result_event_id"]
            for item in projection.values()
            if item["result_event_id"] is not None
        }
        actual_inputs = {
            row["source_event_id"]
            for row in self.connection.execute(
                "SELECT source_event_id FROM prepared_inputs"
            ).fetchall()
        }
        actual_results = {
            row["source_event_id"]
            for row in self.connection.execute(
                "SELECT source_event_id FROM prepared_results"
            ).fetchall()
        }
        if actual_inputs != input_ids:
            raise SystemPaperScheduleError(
                "SYSTEM_PAPER_SCHEDULE_PREPARED_INPUT_SET_MISMATCH"
            )
        if actual_results != result_ids:
            raise SystemPaperScheduleError(
                "SYSTEM_PAPER_SCHEDULE_PREPARED_RESULT_SET_MISMATCH"
            )
        return events[-1]["event_hash"] if events else _GENESIS_HASH

    def _append_locked(
        self,
        event_type: str,
        slot: SystemPaperSlot,
        event_time: object,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        if event_type not in _ALLOWED_EVENTS:
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_EVENT_TYPE_INVALID")
        event_dt, event_text = _utc(event_time)
        last = self.connection.execute(
            "SELECT sequence, event_time, event_hash FROM schedule_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if last is not None and event_dt < _utc(last["event_time"])[0]:
            raise SystemPaperScheduleError(
                "SYSTEM_PAPER_SCHEDULE_EVENT_TIME_ORDER_INVALID"
            )
        sequence = 1 if last is None else int(last["sequence"]) + 1
        previous_hash = _GENESIS_HASH if last is None else last["event_hash"]
        try:
            normalized_payload = json.loads(canonical_json(dict(payload)))
        except (TypeError, ValueError) as error:
            raise SystemPaperScheduleError(
                "SYSTEM_PAPER_SCHEDULE_EVENT_PAYLOAD_INVALID"
            ) from error
        payload_hash = business_hash(normalized_payload)
        identity = {
            "sequence": sequence,
            "event_type": event_type,
            "slot_id": slot.slot_id,
            "event_time": event_text,
            "payload_hash": payload_hash,
            "previous_event_hash": previous_hash,
        }
        event_id = stable_id("system_paper_schedule_event", identity)
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

    def _transaction(self) -> None:
        self.connection.execute("BEGIN IMMEDIATE")

    def _validate_slot(self, slot: SystemPaperSlot) -> None:
        if not isinstance(slot, SystemPaperSlot):
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_SLOT_INVALID")
        expected = self.policy.slot_from_scheduled(slot.scheduled_for)
        if slot != expected:
            raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_SLOT_INVALID")

    def record_gaps(
        self, current_slot: SystemPaperSlot, *, recorded_at: object
    ) -> None:
        self._validate_slot(current_slot)
        recorded, recorded_text = _utc(recorded_at)
        if current_slot != self.policy.current_slot(recorded):
            raise SystemPaperScheduleError(
                "SYSTEM_PAPER_SCHEDULE_CURRENT_SLOT_MISMATCH"
            )
        try:
            self._transaction()
            self.verify_integrity()
            projection = self.slot_projection()
            if projection:
                current_scheduled = _utc(current_slot.scheduled_for)[0]
                existing_before = [
                    _utc(item["scheduled_for"])[0]
                    for item in projection.values()
                    if _utc(item["scheduled_for"])[0] < current_scheduled
                ]
                if existing_before:
                    latest = max(existing_before)
                    candidate = latest + _CADENCE
                    while candidate < current_scheduled:
                        missed = self.policy.slot_from_scheduled(candidate)
                        if missed.slot_id not in projection:
                            self._append_locked(
                                "MISSED",
                                missed,
                                recorded_text,
                                {
                                    **_slot_core(missed, self.policy),
                                    "reason_code": "MISSED_NO_CONTEMPORANEOUS_CAPTURE",
                                },
                            )
                        candidate += _CADENCE
                for item in sorted(
                    projection.values(), key=lambda value: value["scheduled_for"]
                ):
                    slot = self.policy.slot_from_scheduled(item["scheduled_for"])
                    if (
                        _utc(slot.scheduled_for)[0] < current_scheduled
                        and item["terminal_state"] is None
                        and item["durable_stage"] == "NONE"
                        and recorded >= _utc(slot.expires_at)[0]
                    ):
                        self._append_locked(
                            "EXPIRED",
                            slot,
                            recorded_text,
                            {
                                **_slot_core(slot, self.policy),
                                "reason_code": "EXPIRED_UNPREPARED_SLOT",
                            },
                        )
            self.verify_integrity()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def claim(
        self,
        slot: SystemPaperSlot,
        *,
        worker_id: str,
        claimed_at: object,
    ) -> SystemPaperClaim:
        self._validate_slot(slot)
        worker = _worker_id(worker_id)
        now, now_text = _utc(claimed_at)
        try:
            self._transaction()
            self.verify_integrity()
            state = self.slot_projection().get(slot.slot_id)
            if state is not None and state["terminal_state"] == "SUCCEEDED":
                self.connection.commit()
                return SystemPaperClaim(
                    "ALREADY_SUCCEEDED",
                    slot,
                    worker,
                    state["attempt_count"],
                    now_text,
                    now_text,
                    state["durable_stage"],
                )
            if state is not None and state["terminal_state"] in ("MISSED", "EXPIRED"):
                self.connection.commit()
                return SystemPaperClaim(
                    "TERMINAL_INELIGIBLE",
                    slot,
                    worker,
                    state["attempt_count"],
                    now_text,
                    now_text,
                    state["durable_stage"],
                )
            if (
                state is None or state["durable_stage"] == "NONE"
            ) and not (_utc(slot.due_at)[0] <= now < _utc(slot.expires_at)[0]):
                raise SystemPaperScheduleError("SYSTEM_PAPER_SCHEDULE_SLOT_NOT_ACTIVE")
            if (
                state is not None
                and state["active_claim"] is not None
                and now < _utc(state["active_claim"]["lease_expires_at"])[0]
            ):
                active_claim = state["active_claim"]
                self.connection.commit()
                return SystemPaperClaim(
                    "BUSY",
                    slot,
                    worker,
                    state["attempt_count"],
                    active_claim["claimed_at"],
                    active_claim["lease_expires_at"],
                    state["durable_stage"],
                )
            attempt = 1 if state is None else state["attempt_count"] + 1
            lease_expires_at = utc_datetime(now + _LEASE)
            self._append_locked(
                "CLAIMED",
                slot,
                now_text,
                {
                    **_slot_core(slot, self.policy),
                    "worker_id": worker,
                    "attempt": attempt,
                    "lease_expires_at": lease_expires_at,
                },
            )
            self.verify_integrity()
            self.connection.commit()
            stage = "NONE" if state is None else state["durable_stage"]
            return SystemPaperClaim(
                "RESUME_RESULT" if stage == "RESULT" else (
                    "RESUME_INPUT" if stage == "INPUT" else "CLAIMED"
                ),
                slot,
                worker,
                attempt,
                now_text,
                lease_expires_at,
                stage,
            )
        except Exception:
            self.connection.rollback()
            raise
