"""Append-only PREPARED sidecar for context-complete Paper cycles."""

import hashlib
import json
import os
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
from .market_data_cli import _publish_immutable
from .paper_cycle_context import (
    PaperCycleContextError,
    build_paper_cycle_context_bundle,
    paper_cycle_context_reasons,
    paper_cycle_context_trust_hash,
)
from .paper_scheduler import PaperSchedulePolicy, PaperSlot


_GENESIS_HASH = "0" * 64
_LEASE = timedelta(minutes=15)
_ALLOWED_EVENTS = frozenset(
    (
        "CONTEXT_CLAIMED",
        "CONTEXT_PREPARED",
        "CONTEXT_SUCCEEDED",
        "CONTEXT_FAILED",
    )
)
_HASH_FIELDS = (
    "bundle_hash",
    "bundle_trust_hash",
    "paper_cost_binding_trust_hash",
    "offline_paper_trust_hash",
    "account_commission_trust_hash",
    "perpetual_context_trust_hash",
    "output_root_hash",
)
_SCHEDULE_ATTESTATION_TYPE = (
    "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_ATTESTATION"
)
_SCHEDULE_WARNINGS = (
    "CONTEXT_COMPLETE_DURATION_BELOW_90_DAYS",
    "EXTERNAL_SOURCE_ATTESTATIONS_REQUIRED",
    "REAL_ACCOUNT_AND_FUTURES_PROVENANCE_NOT_INFERRED_FROM_STATE",
    "AI_MODEL_NOT_RUN",
    "OPERATING_SYSTEM_SCHEDULER_NOT_CONFIGURED",
    "PROFITABILITY_NOT_PROVEN",
)


@lru_cache(maxsize=1)
def _schedule_validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas", "paper-context-schedule-snapshot-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class PaperContextScheduleError(ValueError):
    """The context schedule state or prepared bundle failed closed."""

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
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_TIME_INVALID"
            ) from error
    else:
        raise PaperContextScheduleError(
            "PAPER_CONTEXT_SCHEDULE_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperContextScheduleError(
            "PAPER_CONTEXT_SCHEDULE_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    converted = converted.replace(
        microsecond=(converted.microsecond // 1000) * 1000
    )
    return converted, utc_datetime(converted)


def _worker(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 64
        or not value.isascii()
        or any(
            not (character.isalnum() or character in "._-")
            for character in value
        )
    ):
        raise PaperContextScheduleError(
            "PAPER_CONTEXT_SCHEDULE_WORKER_INVALID"
        )
    return value


def _hash(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PaperContextScheduleError(
            "PAPER_CONTEXT_SCHEDULE_HASH_INVALID"
        )
    return value


def _artifact_name(slot: PaperSlot) -> str:
    return "paper-context-" + slot.slot_id.lower() + ".json"


def _root_hash(output_root: Path) -> str:
    return business_hash(
        {
            "purpose": "PAPER_CONTEXT_IMMUTABLE_OUTPUT_ROOT",
            "resolved_path": str(Path(output_root).resolve()),
        }
    )


def _core(slot: PaperSlot, policy: PaperSchedulePolicy) -> Dict[str, str]:
    return {
        "schedule_policy_hash": policy.policy_hash,
        "slot_id": slot.slot_id,
        "scheduled_for": slot.scheduled_for,
        "due_at": slot.due_at,
        "expires_at": slot.expires_at,
    }


def _validate_state_path(path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        parent = path.parent.lstat()
        if stat.S_ISLNK(parent.st_mode) or not stat.S_ISDIR(
            parent.st_mode
        ):
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_STATE_PATH_INVALID"
            )
        if path.exists() or path.is_symlink():
            entry = path.lstat()
            if (
                stat.S_ISLNK(entry.st_mode)
                or not stat.S_ISREG(entry.st_mode)
                or entry.st_uid != os.getuid()
                or entry.st_nlink != 1
            ):
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_STATE_PATH_INVALID"
                )
    except OSError as error:
        raise PaperContextScheduleError(
            "PAPER_CONTEXT_SCHEDULE_STATE_PATH_INVALID"
        ) from error


def _project(
    events: Sequence[Mapping[str, Any]],
    policy: PaperSchedulePolicy,
) -> Dict[str, Dict[str, Any]]:
    projection = {}
    previous_sequence = 0
    previous_hash = _GENESIS_HASH
    previous_time = None
    for event in events:
        try:
            sequence = event["sequence"]
            event_type = event["event_type"]
            slot_id = event["slot_id"]
            event_time, event_time_text = _utc(event["event_time"])
            payload = event["payload"]
        except (KeyError, TypeError) as error:
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_EVENT_INVALID"
            ) from error
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence != previous_sequence + 1
            or event_type not in _ALLOWED_EVENTS
            or not isinstance(payload, Mapping)
            or previous_time is not None
            and event_time < previous_time
            or event.get("previous_event_hash") != previous_hash
        ):
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_EVENT_INVALID"
            )
        payload_hash = business_hash(payload)
        if event.get("payload_hash") != payload_hash:
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_EVENT_HASH_INVALID"
            )
        body = {
            "sequence": sequence,
            "event_id": event.get("event_id"),
            "event_type": event_type,
            "slot_id": slot_id,
            "event_time": event_time_text,
            "payload": dict(payload),
            "payload_hash": payload_hash,
            "previous_event_hash": previous_hash,
        }
        if event.get("event_hash") != business_hash(body):
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_EVENT_HASH_INVALID"
            )
        if payload.get("slot_id") != slot_id:
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_SLOT_INVALID"
            )
        slot = policy.slot_from_scheduled(payload.get("scheduled_for"))
        if _core(slot, policy) != {
            name: payload.get(name) for name in _core(slot, policy)
        }:
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_SLOT_INVALID"
            )
        state = projection.get(slot_id)
        if state is None:
            state = {
                **_core(slot, policy),
                "status": "UNSEEN",
                "attempt_count": 0,
                "failure_count": 0,
                "active_claim": None,
                "prepared": None,
            }
            projection[slot_id] = state
        status = state["status"]
        if status == "SUCCEEDED":
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_TERMINAL_MUTATED"
            )
        if event_type == "CONTEXT_CLAIMED":
            attempt = payload.get("attempt")
            lease, lease_text = _utc(payload.get("lease_expires_at"))
            if (
                isinstance(attempt, bool)
                or not isinstance(attempt, int)
                or attempt != state["attempt_count"] + 1
                or lease != event_time + _LEASE
            ):
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_CLAIM_INVALID"
                )
            prior = state["active_claim"]
            if (
                status in ("CLAIMED", "PREPARED")
                and prior is not None
                and event_time < _utc(prior["lease_expires_at"])[0]
            ):
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_LIVE_LEASE_RECLAIMED"
                )
            state["attempt_count"] = attempt
            state["active_claim"] = {
                "worker_id": _worker(payload.get("worker_id")),
                "attempt": attempt,
                "lease_expires_at": lease_text,
            }
            state["status"] = (
                "PREPARED" if state["prepared"] else "CLAIMED"
            )
        elif event_type == "CONTEXT_FAILED":
            claim = state["active_claim"]
            if (
                status != "CLAIMED"
                or claim is None
                or payload.get("worker_id") != claim["worker_id"]
                or payload.get("attempt") != claim["attempt"]
                or not isinstance(payload.get("reason_code"), str)
                or not payload["reason_code"]
            ):
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_TRANSITION_INVALID"
                )
            state["failure_count"] += 1
            state["status"] = "FAILED"
        elif event_type == "CONTEXT_PREPARED":
            claim = state["active_claim"]
            required = (
                "artifact_name",
                "artifact_sha256",
                *_HASH_FIELDS,
            )
            if (
                status != "CLAIMED"
                or claim is None
                or state["prepared"] is not None
                or payload.get("worker_id") != claim["worker_id"]
                or payload.get("attempt") != claim["attempt"]
                or any(
                    not isinstance(payload.get(name), str)
                    or not payload[name]
                    for name in required
                )
            ):
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_PREPARED_INVALID"
                )
            state["prepared"] = {
                name: payload[name] for name in required
            }
            state["prepared"]["source_event_id"] = event["event_id"]
            state["status"] = "PREPARED"
        elif event_type == "CONTEXT_SUCCEEDED":
            claim = state["active_claim"]
            prepared = state["prepared"]
            required = (
                "artifact_name",
                "artifact_sha256",
                *_HASH_FIELDS,
            )
            if (
                status != "PREPARED"
                or claim is None
                or prepared is None
                or payload.get("worker_id") != claim["worker_id"]
                or payload.get("attempt") != claim["attempt"]
                or any(
                    payload.get(name) != prepared[name]
                    for name in required
                )
            ):
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_TRANSITION_INVALID"
                )
            state["status"] = "SUCCEEDED"
        previous_sequence = sequence
        previous_hash = event["event_hash"]
        previous_time = event_time
    return projection


@dataclass(frozen=True)
class ContextClaim:
    outcome: str
    slot: PaperSlot
    worker_id: str
    attempt: int
    lease_expires_at: str
    prepared: bool


class PaperContextScheduleState:
    """Append-only state for context-complete sidecar Artifacts."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.policy = PaperSchedulePolicy.create()
        _validate_state_path(self.path)
        self.connection = sqlite3.connect(str(self.path), timeout=0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        mode = self.connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_WAL_REQUIRED"
            )
        self.connection.execute("PRAGMA synchronous = FULL")
        self._create_schema()
        self._secure_state_files()
        self.verify_integrity()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self._secure_state_files()
        self.connection.close()
        self._secure_state_files()

    def _secure_state_files(self) -> None:
        for candidate in (
            self.path,
            Path(str(self.path) + "-wal"),
            Path(str(self.path) + "-shm"),
        ):
            try:
                if candidate.exists():
                    os.chmod(candidate, 0o600)
            except OSError as error:
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_STATE_MODE_INVALID"
                ) from error

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS context_events (
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
            CREATE TABLE IF NOT EXISTS prepared_context_blobs (
                source_event_id TEXT PRIMARY KEY,
                slot_id TEXT NOT NULL UNIQUE,
                artifact_name TEXT NOT NULL,
                artifact_bytes BLOB NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                bundle_hash TEXT NOT NULL,
                bundle_trust_hash TEXT NOT NULL,
                paper_cost_binding_trust_hash TEXT NOT NULL,
                offline_paper_trust_hash TEXT NOT NULL,
                account_commission_trust_hash TEXT NOT NULL,
                perpetual_context_trust_hash TEXT NOT NULL,
                output_root_hash TEXT NOT NULL,
                FOREIGN KEY(source_event_id)
                    REFERENCES context_events(event_id)
            );
            CREATE TRIGGER IF NOT EXISTS context_events_no_update
            BEFORE UPDATE ON context_events
            BEGIN SELECT RAISE(ABORT, 'context events are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS context_events_no_delete
            BEFORE DELETE ON context_events
            BEGIN SELECT RAISE(ABORT, 'context events are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS prepared_context_blobs_no_update
            BEFORE UPDATE ON prepared_context_blobs
            BEGIN SELECT RAISE(ABORT, 'context blobs are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS prepared_context_blobs_no_delete
            BEFORE DELETE ON prepared_context_blobs
            BEGIN SELECT RAISE(ABORT, 'context blobs are immutable'); END;
            """
        )

    def events(self) -> Tuple[Dict[str, Any], ...]:
        rows = self.connection.execute(
            "SELECT * FROM context_events ORDER BY sequence"
        ).fetchall()
        return tuple(
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
            for row in rows
        )

    def projection(self) -> Dict[str, Dict[str, Any]]:
        return _project(self.events(), self.policy)

    def verify_integrity(self) -> str:
        events = self.events()
        projection = _project(events, self.policy)
        expected = {
            state["prepared"]["source_event_id"]
            for state in projection.values()
            if state["prepared"] is not None
        }
        rows = self.connection.execute(
            "SELECT * FROM prepared_context_blobs ORDER BY source_event_id"
        ).fetchall()
        if {row["source_event_id"] for row in rows} != expected:
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_BLOB_SET_MISMATCH"
            )
        for row in rows:
            prepared = projection[row["slot_id"]]["prepared"]
            artifact_bytes = bytes(row["artifact_bytes"])
            if hashlib.sha256(artifact_bytes).hexdigest() != row[
                "artifact_sha256"
            ]:
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_BLOB_HASH_MISMATCH"
                )
            for name in (
                "artifact_name",
                "artifact_sha256",
                *_HASH_FIELDS,
            ):
                if row[name] != prepared[name]:
                    raise PaperContextScheduleError(
                        "PAPER_CONTEXT_SCHEDULE_BLOB_MISMATCH"
                    )
            try:
                bundle = json.loads(artifact_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_BLOB_JSON_INVALID"
                ) from error
            if (
                bundle.get("bundle_hash") != row["bundle_hash"]
                or paper_cycle_context_reasons(
                    bundle,
                    row["bundle_trust_hash"],
                    paper_cost_binding_trusted_attestation_hash=row[
                        "paper_cost_binding_trust_hash"
                    ],
                    offline_paper_trusted_attestation_hash=row[
                        "offline_paper_trust_hash"
                    ],
                    account_commission_trusted_attestation_hash=row[
                        "account_commission_trust_hash"
                    ],
                    perpetual_context_trusted_attestation_hash=row[
                        "perpetual_context_trust_hash"
                    ],
                )
            ):
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_BUNDLE_INVALID"
                )
        return events[-1]["event_hash"] if events else _GENESIS_HASH

    def _transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")

    def _append(
        self,
        event_type: str,
        slot: PaperSlot,
        event_time: object,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        event_dt, event_text = _utc(event_time)
        last = self.connection.execute(
            "SELECT sequence, event_time, event_hash FROM context_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 1 if last is None else int(last["sequence"]) + 1
        previous_hash = _GENESIS_HASH if last is None else last["event_hash"]
        if last is not None and event_dt < _utc(last["event_time"])[0]:
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_EVENT_TIME_ORDER_INVALID"
            )
        normalized = json.loads(canonical_json(dict(payload)))
        payload_hash = business_hash(normalized)
        identity = {
            "sequence": sequence,
            "event_type": event_type,
            "slot_id": slot.slot_id,
            "event_time": event_text,
            "payload_hash": payload_hash,
            "previous_event_hash": previous_hash,
        }
        event_id = stable_id("context_event", identity)
        body = {
            "sequence": sequence,
            "event_id": event_id,
            "event_type": event_type,
            "slot_id": slot.slot_id,
            "event_time": event_text,
            "payload": normalized,
            "payload_hash": payload_hash,
            "previous_event_hash": previous_hash,
        }
        event_hash = business_hash(body)
        self.connection.execute(
            """
            INSERT INTO context_events (
                event_id, event_type, slot_id, event_time, payload_json,
                payload_hash, previous_event_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_type,
                slot.slot_id,
                event_text,
                canonical_json(normalized),
                payload_hash,
                previous_hash,
                event_hash,
            ),
        )
        return {**body, "event_hash": event_hash}

    def claim(
        self,
        slot: PaperSlot,
        *,
        worker_id: str,
        claimed_at: object,
    ) -> ContextClaim:
        worker_id = _worker(worker_id)
        now, now_text = _utc(claimed_at)
        if not _utc(slot.due_at)[0] <= now < _utc(slot.expires_at)[0]:
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_SLOT_NOT_ACTIVE"
            )
        try:
            self._transaction()
            self.verify_integrity()
            state = self.projection().get(slot.slot_id)
            if state is not None and state["status"] == "SUCCEEDED":
                self.connection.commit()
                return ContextClaim(
                    "ALREADY_SUCCEEDED",
                    slot,
                    worker_id,
                    state["attempt_count"],
                    state["active_claim"]["lease_expires_at"],
                    True,
                )
            if (
                state is not None
                and state["status"] in ("CLAIMED", "PREPARED")
                and now
                < _utc(
                    state["active_claim"]["lease_expires_at"]
                )[0]
            ):
                self.connection.commit()
                return ContextClaim(
                    "BUSY",
                    slot,
                    worker_id,
                    state["attempt_count"],
                    state["active_claim"]["lease_expires_at"],
                    state["prepared"] is not None,
                )
            attempt = 1 if state is None else state["attempt_count"] + 1
            lease = utc_datetime(now + _LEASE)
            self._append(
                "CONTEXT_CLAIMED",
                slot,
                now_text,
                {
                    **_core(slot, self.policy),
                    "worker_id": worker_id,
                    "attempt": attempt,
                    "lease_expires_at": lease,
                },
            )
            self.verify_integrity()
            self.connection.commit()
            return ContextClaim(
                (
                    "RESUME_PREPARED"
                    if state is not None and state["prepared"] is not None
                    else "CLAIMED"
                ),
                slot,
                worker_id,
                attempt,
                lease,
                state is not None and state["prepared"] is not None,
            )
        except Exception:
            self.connection.rollback()
            raise

    def fail(
        self,
        claim: ContextClaim,
        *,
        reason_code: str,
        failed_at: object,
    ) -> None:
        try:
            self._transaction()
            self.verify_integrity()
            state = self.projection().get(claim.slot.slot_id)
            if (
                state is None
                or state["status"] != "CLAIMED"
                or state["active_claim"]["worker_id"] != claim.worker_id
                or state["active_claim"]["attempt"] != claim.attempt
            ):
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_CLAIM_LOST"
                )
            self._append(
                "CONTEXT_FAILED",
                claim.slot,
                failed_at,
                {
                    **_core(claim.slot, self.policy),
                    "worker_id": claim.worker_id,
                    "attempt": claim.attempt,
                    "reason_code": str(reason_code),
                },
            )
            self.verify_integrity()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def prepare(
        self,
        claim: ContextClaim,
        *,
        artifact_bytes: bytes,
        bundle_trust_hash: str,
        output_root_hash: str,
        prepared_at: object,
    ) -> None:
        if not isinstance(artifact_bytes, bytes) or not artifact_bytes:
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_PREPARED_INVALID"
            )
        try:
            bundle = json.loads(artifact_bytes.decode("utf-8"))
            lineage = bundle["lineage"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as error:
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_BLOB_JSON_INVALID"
            ) from error
        source = {
            "paper_cost_binding_trust_hash": lineage[
                "paper_cost_binding_trusted_attestation_hash"
            ],
            "offline_paper_trust_hash": lineage[
                "offline_paper_trusted_attestation_hash"
            ],
            "account_commission_trust_hash": lineage[
                "account_commission_trusted_attestation_hash"
            ],
            "perpetual_context_trust_hash": lineage[
                "perpetual_context_trusted_attestation_hash"
            ],
        }
        for value in (
            bundle_trust_hash,
            output_root_hash,
            *source.values(),
        ):
            _hash(value)
        if (
            bundle["pit_context"]["slot"]["slot_id"]
            != claim.slot.slot_id
            or paper_cycle_context_reasons(
                bundle,
                bundle_trust_hash,
                paper_cost_binding_trusted_attestation_hash=source[
                    "paper_cost_binding_trust_hash"
                ],
                offline_paper_trusted_attestation_hash=source[
                    "offline_paper_trust_hash"
                ],
                account_commission_trusted_attestation_hash=source[
                    "account_commission_trust_hash"
                ],
                perpetual_context_trusted_attestation_hash=source[
                    "perpetual_context_trust_hash"
                ],
            )
        ):
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_BUNDLE_INVALID"
            )
        artifact_name = _artifact_name(claim.slot)
        artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
        payload = {
            **_core(claim.slot, self.policy),
            "worker_id": claim.worker_id,
            "attempt": claim.attempt,
            "artifact_name": artifact_name,
            "artifact_sha256": artifact_sha,
            "bundle_hash": bundle["bundle_hash"],
            "bundle_trust_hash": bundle_trust_hash,
            **source,
            "output_root_hash": output_root_hash,
        }
        try:
            self._transaction()
            self.verify_integrity()
            state = self.projection().get(claim.slot.slot_id)
            if (
                state is None
                or state["status"] != "CLAIMED"
                or state["active_claim"]["worker_id"] != claim.worker_id
                or state["active_claim"]["attempt"] != claim.attempt
            ):
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_CLAIM_LOST"
                )
            event = self._append(
                "CONTEXT_PREPARED",
                claim.slot,
                prepared_at,
                payload,
            )
            self.connection.execute(
                """
                INSERT INTO prepared_context_blobs (
                    source_event_id, slot_id, artifact_name,
                    artifact_bytes, artifact_sha256, bundle_hash,
                    bundle_trust_hash, paper_cost_binding_trust_hash,
                    offline_paper_trust_hash,
                    account_commission_trust_hash,
                    perpetual_context_trust_hash, output_root_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    claim.slot.slot_id,
                    artifact_name,
                    artifact_bytes,
                    artifact_sha,
                    bundle["bundle_hash"],
                    bundle_trust_hash,
                    source["paper_cost_binding_trust_hash"],
                    source["offline_paper_trust_hash"],
                    source["account_commission_trust_hash"],
                    source["perpetual_context_trust_hash"],
                    output_root_hash,
                ),
            )
            self.verify_integrity()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def load_prepared(self, slot: PaperSlot) -> Dict[str, Any]:
        self.verify_integrity()
        row = self.connection.execute(
            "SELECT * FROM prepared_context_blobs WHERE slot_id = ?",
            (slot.slot_id,),
        ).fetchone()
        if row is None:
            raise PaperContextScheduleError(
                "PAPER_CONTEXT_SCHEDULE_PREPARED_MISSING"
            )
        return {
            name: (
                bytes(row[name])
                if name == "artifact_bytes"
                else row[name]
            )
            for name in (
                "artifact_name",
                "artifact_bytes",
                "artifact_sha256",
                *_HASH_FIELDS,
            )
        }

    def succeed(
        self,
        claim: ContextClaim,
        *,
        completed_at: object,
    ) -> None:
        try:
            self._transaction()
            self.verify_integrity()
            state = self.projection().get(claim.slot.slot_id)
            if (
                state is None
                or state["status"] != "PREPARED"
                or state["active_claim"]["worker_id"] != claim.worker_id
                or state["active_claim"]["attempt"] != claim.attempt
            ):
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_CLAIM_LOST"
                )
            prepared = state["prepared"]
            self._append(
                "CONTEXT_SUCCEEDED",
                claim.slot,
                completed_at,
                {
                    **_core(claim.slot, self.policy),
                    "worker_id": claim.worker_id,
                    "attempt": claim.attempt,
                    **{
                        name: prepared[name]
                        for name in (
                            "artifact_name",
                            "artifact_sha256",
                            *_HASH_FIELDS,
                        )
                    },
                },
            )
            self.verify_integrity()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise


def _public_slots(
    projection: Mapping[str, Mapping[str, Any]],
) -> Sequence[Mapping[str, Any]]:
    results = []
    for state in sorted(
        projection.values(), key=lambda item: item["scheduled_for"]
    ):
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
                "artifact_name_or_null": (
                    prepared["artifact_name"] if prepared else None
                ),
                "artifact_sha256_or_null": (
                    prepared["artifact_sha256"] if prepared else None
                ),
                "bundle_hash_or_null": (
                    prepared["bundle_hash"] if prepared else None
                ),
                "bundle_trust_hash_or_null": (
                    prepared["bundle_trust_hash"] if prepared else None
                ),
            }
        )
    return results


def _summary(
    projection: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    ordered = sorted(
        projection.values(), key=lambda item: item["scheduled_for"]
    )
    if ordered:
        first = _utc(ordered[0]["scheduled_for"])[0]
        last = _utc(ordered[-1]["scheduled_for"])[0]
        expected = int((last - first) / timedelta(hours=4)) + 1
        days = (last.date() - first.date()).days + 1
    else:
        expected = 0
        days = 0
    statuses = [item["status"] for item in ordered]
    succeeded = statuses.count("SUCCEEDED")
    continuous = (
        bool(ordered)
        and len(ordered) == expected
        and succeeded == expected
    )
    return {
        "known_slot_count": len(ordered),
        "expected_slot_count_between_bounds": expected,
        "unobserved_slot_count_between_bounds": expected - len(ordered),
        "context_complete_slot_count": succeeded,
        "failed_slot_count": statuses.count("FAILED"),
        "claimed_slot_count": statuses.count("CLAIMED"),
        "prepared_slot_count": statuses.count("PREPARED"),
        "total_failed_attempt_count": sum(
            item["failure_count"] for item in ordered
        ),
        "first_scheduled_for_or_null": (
            ordered[0]["scheduled_for"] if ordered else None
        ),
        "last_scheduled_for_or_null": (
            ordered[-1]["scheduled_for"] if ordered else None
        ),
        "observed_calendar_days": days,
        "continuous_context_complete": continuous,
        "ninety_day_context_complete": (
            continuous and days >= 90 and succeeded >= 540
        ),
    }


def build_context_schedule_snapshot(
    state: PaperContextScheduleState,
    *,
    recorded_at: Optional[object] = None,
) -> Dict[str, Any]:
    if not isinstance(state, PaperContextScheduleState):
        raise PaperContextScheduleError(
            "PAPER_CONTEXT_SCHEDULE_STATE_INVALID"
        )
    chain_end = state.verify_integrity()
    events = list(state.events())
    projection = _project(events, state.policy)
    summary = _summary(projection)
    selected = (
        _utc(recorded_at)[1]
        if recorded_at is not None
        else events[-1]["event_time"]
        if events
        else utc_datetime(datetime.now(timezone.utc))
    )
    if events and _utc(selected)[0] < _utc(events[-1]["event_time"])[0]:
        raise PaperContextScheduleError(
            "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_TIME_INVALID"
        )
    snapshot = {
        "$schema": "./paper-context-schedule-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": stable_id(
            "paper_context_schedule",
            {
                "schedule_policy_hash": state.policy.policy_hash,
                "event_chain_end_hash": chain_end,
            },
        ),
        "snapshot_hash": "",
        "recorded_at": selected,
        "policy": {
            **state.policy.business_payload(),
            "policy_hash": state.policy.policy_hash,
            "sidecar_policy": (
                "ACCOUNT_COST_AND_PERPETUAL_CONTEXT_COMPLETE_V1"
            ),
        },
        "events": events,
        "events_root_hash": business_hash(events),
        "event_chain_end_hash": chain_end,
        "slots": list(_public_slots(projection)),
        "summary": summary,
        "state_integrity": "VERIFIED_APPEND_ONLY_WAL",
        "scheduler_eligibility": (
            "CONTEXT_SIDECAR_OPERATIONAL_RESEARCH_ONLY"
        ),
        "paper_eligibility": "LONGITUDINAL_COLLECTION_IN_PROGRESS",
        "production_eligibility": "NOT_APPROVED",
        "profitability_eligibility": (
            "INSUFFICIENT_DURATION_EXECUTION_AND_AI"
        ),
        "warnings": (
            (
                []
                if summary["ninety_day_context_complete"]
                else [_SCHEDULE_WARNINGS[0]]
            )
            + list(_SCHEDULE_WARNINGS[1:])
        ),
    }
    snapshot["snapshot_hash"] = artifact_self_hash(
        snapshot, "snapshot_hash"
    )
    if tuple(_schedule_validator().iter_errors(snapshot)):
        raise PaperContextScheduleError(
            "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_SCHEMA_INVALID"
        )
    return snapshot


def context_schedule_snapshot_trust_hash(
    snapshot: Mapping[str, Any],
) -> str:
    try:
        return business_hash(
            {
                "attestation_type": _SCHEDULE_ATTESTATION_TYPE,
                "snapshot_id": snapshot["snapshot_id"],
                "snapshot_hash": snapshot["snapshot_hash"],
                "schedule_policy_hash": snapshot["policy"][
                    "policy_hash"
                ],
                "events_root_hash": snapshot["events_root_hash"],
                "event_chain_end_hash": snapshot[
                    "event_chain_end_hash"
                ],
                "successful_bundle_trust_hashes": [
                    item["bundle_trust_hash_or_null"]
                    for item in snapshot["slots"]
                    if item["status"] == "SUCCEEDED"
                ],
            }
        )
    except (KeyError, TypeError):
        return ""


def context_schedule_snapshot_reasons(
    snapshot: Mapping[str, Any],
    trusted_attestation_hash: str,
) -> Tuple[str, ...]:
    if not isinstance(snapshot, Mapping):
        return ("PAPER_CONTEXT_SCHEDULE_SNAPSHOT_INVALID",)
    reasons = []
    try:
        if tuple(_schedule_validator().iter_errors(snapshot)):
            reasons.append(
                "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_SCHEMA_INVALID"
            )
        if artifact_self_hash(
            snapshot, "snapshot_hash"
        ) != snapshot.get("snapshot_hash"):
            reasons.append(
                "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_SELF_HASH_MISMATCH"
            )
        if (
            context_schedule_snapshot_trust_hash(snapshot)
            != trusted_attestation_hash
        ):
            reasons.append(
                "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_TRUST_HASH_MISMATCH"
            )
        policy = PaperSchedulePolicy.create()
        expected_policy = {
            **policy.business_payload(),
            "policy_hash": policy.policy_hash,
            "sidecar_policy": (
                "ACCOUNT_COST_AND_PERPETUAL_CONTEXT_COMPLETE_V1"
            ),
        }
        if snapshot.get("policy") != expected_policy:
            reasons.append(
                "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_POLICY_MISMATCH"
            )
        events = snapshot["events"]
        projection = _project(events, policy)
        if (
            events
            and _utc(snapshot["recorded_at"])[0]
            < _utc(events[-1]["event_time"])[0]
        ):
            reasons.append(
                "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_TIME_INVALID"
            )
        if snapshot.get("events_root_hash") != business_hash(events):
            reasons.append(
                "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_EVENTS_MISMATCH"
            )
        expected_end = (
            events[-1]["event_hash"] if events else _GENESIS_HASH
        )
        if snapshot.get("event_chain_end_hash") != expected_end:
            reasons.append(
                "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_CHAIN_MISMATCH"
            )
        if snapshot.get("slots") != list(_public_slots(projection)):
            reasons.append(
                "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_SLOTS_MISMATCH"
            )
        expected_summary = _summary(projection)
        if snapshot.get("summary") != expected_summary:
            reasons.append(
                "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_SUMMARY_MISMATCH"
            )
        expected_warnings = (
            (
                []
                if expected_summary["ninety_day_context_complete"]
                else [_SCHEDULE_WARNINGS[0]]
            )
            + list(_SCHEDULE_WARNINGS[1:])
        )
        if snapshot.get("warnings") != expected_warnings:
            reasons.append(
                "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_WARNINGS_MISMATCH"
            )
    except (
        KeyError,
        TypeError,
        ValueError,
        PaperContextScheduleError,
    ):
        reasons.append(
            "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_REPLAY_INVALID"
        )
    for name, expected in (
        (
            "scheduler_eligibility",
            "CONTEXT_SIDECAR_OPERATIONAL_RESEARCH_ONLY",
        ),
        ("paper_eligibility", "LONGITUDINAL_COLLECTION_IN_PROGRESS"),
        ("production_eligibility", "NOT_APPROVED"),
        (
            "profitability_eligibility",
            "INSUFFICIENT_DURATION_EXECUTION_AND_AI",
        ),
    ):
        if snapshot.get(name) != expected:
            reasons.append(
                "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_ELIGIBILITY_INVALID"
            )
    return tuple(sorted(set(reasons)))


def _clock(clock) -> str:
    value = clock() if callable(clock) else clock
    return _utc(value)[1]


def run_context_complete_paper_cycle(
    *,
    state_path: Path,
    output_root: Path,
    worker_id: str,
    clock,
    paper_cost_binding: Optional[Mapping[str, Any]] = None,
    paper_cost_binding_trusted_attestation_hash: Optional[str] = None,
    offline_paper_trusted_attestation_hash: Optional[str] = None,
    account_commission_trusted_attestation_hash: Optional[str] = None,
    perpetual_context_snapshot: Optional[Mapping[str, Any]] = None,
    perpetual_context_trusted_attestation_hash: Optional[str] = None,
    fault_after_prepare: bool = False,
    fault_after_publish: bool = False,
) -> Dict[str, Any]:
    """Prepare/publish one context bundle; resume never rereads sources."""

    invocation = _clock(clock)
    policy = PaperSchedulePolicy.create()
    slot = policy.current_slot(invocation)
    output = Path(output_root)
    output_hash = _root_hash(output)
    with PaperContextScheduleState(Path(state_path)) as state:
        claim = state.claim(
            slot, worker_id=worker_id, claimed_at=invocation
        )
        if claim.outcome == "BUSY":
            return {
                "outcome": "BUSY",
                "slot_id": slot.slot_id,
                "source_read_count": 0,
                "network_request_count": 0,
                "lease_expires_at": claim.lease_expires_at,
            }
        prepared_before = claim.prepared
        try:
            if prepared_before or claim.outcome == "ALREADY_SUCCEEDED":
                prepared = state.load_prepared(slot)
                if prepared["output_root_hash"] != output_hash:
                    raise PaperContextScheduleError(
                        "PAPER_CONTEXT_SCHEDULE_OUTPUT_ROOT_MISMATCH"
                    )
                source_count = 0
            else:
                if (
                    paper_cost_binding is None
                    or perpetual_context_snapshot is None
                    or paper_cost_binding_trusted_attestation_hash is None
                    or offline_paper_trusted_attestation_hash is None
                    or account_commission_trusted_attestation_hash is None
                    or perpetual_context_trusted_attestation_hash is None
                ):
                    raise PaperContextScheduleError(
                        "PAPER_CONTEXT_SOURCES_REQUIRED"
                    )
                bundle = build_paper_cycle_context_bundle(
                    paper_cost_binding=paper_cost_binding,
                    paper_cost_binding_trusted_attestation_hash=(
                        paper_cost_binding_trusted_attestation_hash
                    ),
                    offline_paper_trusted_attestation_hash=(
                        offline_paper_trusted_attestation_hash
                    ),
                    account_commission_trusted_attestation_hash=(
                        account_commission_trusted_attestation_hash
                    ),
                    perpetual_context_snapshot=perpetual_context_snapshot,
                    perpetual_context_trusted_attestation_hash=(
                        perpetual_context_trusted_attestation_hash
                    ),
                    created_at=invocation,
                )
                artifact_bytes = json.dumps(
                    bundle, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                bundle_trust = paper_cycle_context_trust_hash(bundle)
                state.prepare(
                    claim,
                    artifact_bytes=artifact_bytes,
                    bundle_trust_hash=bundle_trust,
                    output_root_hash=output_hash,
                    prepared_at=invocation,
                )
                prepared = state.load_prepared(slot)
                source_count = 2
                if fault_after_prepare:
                    raise PaperContextScheduleError(
                        "INJECTED_CONTEXT_AFTER_PREPARE"
                    )
            path = (
                output.resolve()
                / "paper-context"
                / prepared["artifact_name"]
            )
            created = _publish_immutable(
                output,
                prepared["artifact_name"],
                prepared["artifact_bytes"],
                output_directory="paper-context",
            )
            os.chmod(path, 0o600)
            if fault_after_publish:
                raise PaperContextScheduleError(
                    "INJECTED_CONTEXT_AFTER_PUBLISH"
                )
            if claim.outcome != "ALREADY_SUCCEEDED":
                state.succeed(claim, completed_at=invocation)
            schedule_snapshot = build_context_schedule_snapshot(state)
            schedule_trust = context_schedule_snapshot_trust_hash(
                schedule_snapshot
            )
            if context_schedule_snapshot_reasons(
                schedule_snapshot, schedule_trust
            ):
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_INVALID"
                )
            schedule_name = (
                "paper-context-schedule-"
                + slot.slot_id.lower()
                + ".json"
            )
            schedule_bytes = json.dumps(
                schedule_snapshot,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            schedule_path = (
                output.resolve() / "paper-context" / schedule_name
            )
            schedule_created = _publish_immutable(
                output,
                schedule_name,
                schedule_bytes,
                output_directory="paper-context",
            )
            os.chmod(schedule_path, 0o600)
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
                "source_read_count": source_count,
                "network_request_count": 0,
                "artifact_path": str(path),
                "artifact_created": created,
                "artifact_sha256": prepared["artifact_sha256"],
                "bundle_hash": prepared["bundle_hash"],
                "bundle_trust_hash": prepared["bundle_trust_hash"],
                "schedule_snapshot_path": str(schedule_path),
                "schedule_snapshot_created": schedule_created,
                "schedule_snapshot_hash": schedule_snapshot[
                    "snapshot_hash"
                ],
                "schedule_trust_hash": schedule_trust,
                "context_complete_slot_count": schedule_snapshot[
                    "summary"
                ]["context_complete_slot_count"],
                "ninety_day_context_complete": schedule_snapshot[
                    "summary"
                ]["ninety_day_context_complete"],
                "context_eligibility": (
                    "CONTEXT_COMPLETE_RESEARCH_ONLY"
                ),
                "paper_eligibility": (
                    "LONGITUDINAL_COLLECTION_IN_PROGRESS"
                ),
                "production_eligibility": "NOT_APPROVED",
            }
        except Exception as error:
            current = state.projection().get(slot.slot_id)
            if (
                not prepared_before
                and claim.outcome == "CLAIMED"
                and current is not None
                and current["status"] == "CLAIMED"
            ):
                state.fail(
                    claim,
                    reason_code=getattr(
                        error, "reason_code", type(error).__name__
                    ),
                    failed_at=invocation,
                )
            if isinstance(error, PaperContextScheduleError):
                raise
            if isinstance(error, PaperCycleContextError):
                raise PaperContextScheduleError(
                    error.reason_code
                ) from error
            raise
