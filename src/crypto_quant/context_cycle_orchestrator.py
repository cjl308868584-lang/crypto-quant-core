"""Recoverable account -> Paper -> perpetual -> context orchestration."""

import hashlib
import json
import os
import sqlite3
import stat
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .account_commission import (
    AccountCommissionError,
    BinanceAccountCommissionTransport,
    HmacAccountSigner,
    account_commission_reasons,
    account_commission_trust_hash,
    build_account_commission_snapshot,
    capture_account_commission_with_runtime_gate,
    load_account_signer_from_environment,
)
from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .market_data_cli import _publish_immutable
from .offline_paper import offline_paper_run_reasons
from .offline_paper import BinanceOfflinePaperTransport
from .paper_context_scheduler import (
    PaperContextScheduleError,
    run_context_complete_paper_cycle,
)
from .paper_cost_binding import (
    PaperCostBindingError,
    build_paper_account_cost_binding,
    paper_account_cost_binding_reasons,
    paper_account_cost_binding_trust_hash,
)
from .paper_scheduler import (
    PaperScheduleError,
    PaperSchedulePolicy,
    PaperSlot,
    run_due_paper_cycle,
)
from .perpetual_context import (
    BinancePerpetualContextTransport,
    PerpetualContextError,
    build_perpetual_context_snapshot,
    capture_perpetual_context_with_runtime_gate,
    perpetual_context_reasons,
    perpetual_context_trust_hash,
)
from .runtime_health import (
    BinanceServerTimeTransport,
    RuntimeHealthError,
    open_verified_runtime_gate,
    server_time_probe_reasons,
    server_time_probe_trust_hash,
)


_GENESIS_HASH = "0" * 64
_ATTESTATION_TYPE = "CONTEXT_CYCLE_ORCHESTRATION_ATTESTATION"
_EVENT_TYPES = frozenset(
    (
        "ORCHESTRATION_CLAIMED",
        "ACCOUNT_PREPARED",
        "PAPER_REFERENCED",
        "PERPETUAL_PREPARED",
        "COST_BINDING_PREPARED",
        "CONTEXT_SUCCEEDED",
        "ORCHESTRATION_FAILED",
    )
)
_BLOB_STAGE = {
    "ACCOUNT": ("ACCOUNT_PREPARED", "ACCOUNT"),
    "PERPETUAL": ("PERPETUAL_PREPARED", "PERPETUAL"),
    "COST_BINDING": ("COST_BINDING_PREPARED", "COST_BINDING"),
}
_STAGES = ("NONE", "ACCOUNT", "PAPER", "PERPETUAL", "COST_BINDING")
_WARNINGS = (
    "OPERATING_SYSTEM_SCHEDULER_INSTALLATION_NOT_ATTESTED",
    "REAL_ACCOUNT_AND_FUTURES_SOURCES_REQUIRED",
    "RECOVERY_MAY_USE_A_NEW_VERIFIED_RUNTIME_GATE",
    "AI_MODEL_NOT_RUN",
    "PAPER_DURATION_BELOW_90_DAYS",
    "PROFITABILITY_NOT_PROVEN",
)


class ContextCycleOrchestrationError(ValueError):
    """The complete-cycle orchestration failed closed."""

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
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_TIME_INVALID"
            ) from error
    else:
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_TIME_INVALID"
        )
    return converted, utc_datetime(converted)


def _hash(value: object, reason: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ContextCycleOrchestrationError(reason)
    return value


def _worker(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 80
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in value
        )
    ):
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_WORKER_INVALID"
        )
    return value


def _root_hash(output_root: Path) -> str:
    return business_hash(
        {
            "root_type": "CONTEXT_CYCLE_OUTPUT_ROOT_V1",
            "resolved_path": str(Path(output_root).resolve()),
        }
    )


def _slot_core(slot: PaperSlot) -> Dict[str, str]:
    return {
        "scheduled_for": slot.scheduled_for,
        "due_at": slot.due_at,
        "expires_at": slot.expires_at,
    }


def _artifact_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 220
        or value in (".", "..")
        or "/" in value
        or "\\" in value
        or not value.endswith(".json")
    ):
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_ARTIFACT_NAME_INVALID"
        )
    return value


def _strict_json_bytes(body: bytes) -> Mapping[str, Any]:
    if not isinstance(body, bytes) or not body:
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_ARTIFACT_INVALID"
        )

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_JSON_DUPLICATE_KEY"
                )
            result[key] = value
        return result

    def reject_number(_value):
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_JSON_FLOAT_FORBIDDEN"
        )

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_ARTIFACT_INVALID"
        ) from error
    if not isinstance(value, Mapping):
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_ARTIFACT_INVALID"
        )
    return value


def _event_body(
    sequence: int,
    event_type: str,
    slot_id: str,
    event_time: str,
    payload: Mapping[str, Any],
    previous_event_hash: str,
) -> Dict[str, Any]:
    payload_hash = business_hash(payload)
    identity = {
        "sequence": sequence,
        "event_type": event_type,
        "slot_id": slot_id,
        "event_time": event_time,
        "payload_hash": payload_hash,
        "previous_event_hash": previous_event_hash,
    }
    body = {
        "sequence": sequence,
        "event_id": stable_id("context_orchestration_event", identity),
        "event_type": event_type,
        "slot_id": slot_id,
        "event_time": event_time,
        "payload": deepcopy(dict(payload)),
        "payload_hash": payload_hash,
        "previous_event_hash": previous_event_hash,
    }
    body["event_hash"] = business_hash(body)
    return body


def _event_without_hash(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        name: row[name]
        for name in (
            "sequence",
            "event_id",
            "event_type",
            "slot_id",
            "event_time",
            "payload",
            "payload_hash",
            "previous_event_hash",
        )
    }


def _new_projection(slot_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "slot_id": slot_id,
        **{name: payload[name] for name in ("scheduled_for", "due_at", "expires_at")},
        "status": "NEW",
        "stage": "NONE",
        "attempt_count": 0,
        "failure_count": 0,
        "lease_expires_at": None,
        "last_worker_id": None,
        "account": None,
        "paper": None,
        "perpetual": None,
        "cost_binding": None,
        "context": None,
    }


def _core_matches(state: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    return all(
        state[name] == payload.get(name)
        for name in ("scheduled_for", "due_at", "expires_at")
    )


def _project_events(
    events: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    projection: Dict[str, Dict[str, Any]] = {}
    previous = _GENESIS_HASH
    previous_time = None
    for expected_sequence, event in enumerate(events, 1):
        if event.get("sequence") != expected_sequence:
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_EVENT_SEQUENCE_INVALID"
            )
        event_type = event.get("event_type")
        if event_type not in _EVENT_TYPES:
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_EVENT_TYPE_INVALID"
            )
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_EVENT_PAYLOAD_INVALID"
            )
        if event.get("previous_event_hash") != previous:
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_EVENT_CHAIN_INVALID"
            )
        if event.get("payload_hash") != business_hash(payload):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_EVENT_PAYLOAD_HASH_INVALID"
            )
        if event.get("event_hash") != business_hash(
            _event_without_hash(event)
        ):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_EVENT_HASH_INVALID"
            )
        slot_id = event.get("slot_id")
        if not isinstance(slot_id, str):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_SLOT_INVALID"
            )
        state = projection.get(slot_id)
        if state is None:
            if event_type != "ORCHESTRATION_CLAIMED":
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_TRANSITION_INVALID"
                )
            state = _new_projection(slot_id, payload)
            projection[slot_id] = state
        if not _core_matches(state, payload):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_SLOT_CORE_MISMATCH"
            )
        event_time, _ = _utc(event["event_time"])
        if previous_time is not None and event_time < previous_time:
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_EVENT_TIME_REVERSED"
            )
        due, _ = _utc(state["due_at"])
        expires, _ = _utc(state["expires_at"])
        if not due <= event_time < expires:
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_EVENT_OUTSIDE_SLOT"
            )
        if (
            event_type != "ORCHESTRATION_CLAIMED"
            and state["status"] == "CLAIMED"
            and event_time >= _utc(state["lease_expires_at"])[0]
        ):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_LEASE_EXPIRED"
            )
        if event_type == "ORCHESTRATION_CLAIMED":
            attempt = payload.get("attempt")
            if (
                state["status"] == "SUCCEEDED"
                or isinstance(attempt, bool)
                or attempt != state["attempt_count"] + 1
                or payload.get("stage") != state["stage"]
            ):
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_CLAIM_INVALID"
                )
            lease, lease_text = _utc(payload.get("lease_expires_at"))
            expected_lease = min(
                event_time
                + timedelta(
                    seconds=PaperSchedulePolicy.create().lease_seconds
                ),
                expires,
            )
            if lease != expected_lease:
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_LEASE_INVALID"
                )
            state["attempt_count"] = attempt
            state["lease_expires_at"] = lease_text
            state["last_worker_id"] = _worker(payload.get("worker_id"))
            state["status"] = "CLAIMED"
            probe = payload.get("runtime_probe")
            if (
                not isinstance(probe, Mapping)
                or server_time_probe_reasons(
                    probe, server_time_probe_trust_hash(probe)
                )
                or probe.get("health_status")
                not in ("HEALTHY_ALIGNED", "HEALTHY_CORRECTED")
                or payload.get("physical_network_request_count") != 3
                or _utc(probe["trusted_completed_at_or_null"])[0]
                > event_time
            ):
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_RUNTIME_GATE_INVALID"
                )
        elif event_type in (
            "ACCOUNT_PREPARED",
            "PERPETUAL_PREPARED",
            "COST_BINDING_PREPARED",
        ):
            blob_type = payload.get("blob_type")
            expected_event, expected_stage = _BLOB_STAGE.get(
                blob_type, (None, None)
            )
            expected_previous = {
                "ACCOUNT": "NONE",
                "PERPETUAL": "PAPER",
                "COST_BINDING": "PERPETUAL",
            }.get(blob_type)
            if (
                state["status"] != "CLAIMED"
                or event_type != expected_event
                or state["stage"] != expected_previous
                or payload.get("physical_network_request_count")
                != (3 if blob_type == "ACCOUNT" else 5 if blob_type == "PERPETUAL" else 0)
            ):
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_TRANSITION_INVALID"
                )
            reference = {
                name: payload[name]
                for name in (
                    "artifact_name",
                    "artifact_sha256",
                    "artifact_hash",
                    "trust_hash",
                    "runtime_probe_hash",
                )
            }
            state[blob_type.lower()] = reference
            state["stage"] = expected_stage
        elif event_type == "PAPER_REFERENCED":
            if (
                state["status"] != "CLAIMED"
                or state["stage"] != "ACCOUNT"
                or payload.get("physical_network_request_count")
                not in (0, 4)
            ):
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_TRANSITION_INVALID"
                )
            state["paper"] = {
                name: payload[name]
                for name in (
                    "artifact_name",
                    "cycle_run_hash",
                    "cycle_trust_hash",
                )
            }
            state["stage"] = "PAPER"
        elif event_type == "CONTEXT_SUCCEEDED":
            if state["status"] != "CLAIMED" or state["stage"] != "COST_BINDING":
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_TRANSITION_INVALID"
                )
            if payload.get("physical_network_request_count") != 0:
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_NETWORK_COUNT_INVALID"
                )
            state["context"] = {
                name: payload[name]
                for name in (
                    "bundle_hash",
                    "bundle_trust_hash",
                    "schedule_snapshot_hash",
                    "schedule_trust_hash",
                )
            }
            state["status"] = "SUCCEEDED"
            state["lease_expires_at"] = None
        elif event_type == "ORCHESTRATION_FAILED":
            if state["status"] != "CLAIMED":
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_TRANSITION_INVALID"
                )
            count = payload.get("physical_network_request_count")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_NETWORK_COUNT_INVALID"
                )
            state["status"] = "FAILED"
            state["failure_count"] += 1
            state["lease_expires_at"] = None
        previous_time = event_time
        previous = event["event_hash"]
    return projection


def _validate_state_path(path: Path) -> None:
    if path.is_symlink():
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_STATE_PATH_INVALID"
        )
    if path.exists():
        status = path.stat()
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_nlink != 1
            or status.st_uid != os.getuid()
            or stat.S_IMODE(status.st_mode) != 0o600
        ):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_STATE_PATH_INVALID"
            )


@dataclass(frozen=True)
class OrchestrationClaim:
    outcome: str
    slot: PaperSlot
    attempt: int
    lease_expires_at: Optional[str]
    stage: str


class ContextCycleOrchestrationState:
    """Append-only orchestration journal with exact prepared source bytes."""

    def __init__(self, path: Path, output_root: Path):
        self.path = Path(path)
        self.output_root_hash = _root_hash(Path(output_root))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _validate_state_path(self.path)
        self.connection = sqlite3.connect(
            str(self.path), isolation_level=None, timeout=5
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS orchestration_meta (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                output_root_hash TEXT NOT NULL,
                policy_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orchestration_events (
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
            CREATE TABLE IF NOT EXISTS orchestration_blobs (
                slot_id TEXT NOT NULL,
                blob_type TEXT NOT NULL,
                artifact_name TEXT NOT NULL,
                artifact_bytes BLOB NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                trust_hash TEXT NOT NULL,
                runtime_probe_hash TEXT NOT NULL,
                prepared_at TEXT NOT NULL,
                PRIMARY KEY(slot_id, blob_type)
            );
            CREATE TRIGGER IF NOT EXISTS orchestration_events_no_update
            BEFORE UPDATE ON orchestration_events BEGIN
                SELECT RAISE(ABORT, 'append-only orchestration_events');
            END;
            CREATE TRIGGER IF NOT EXISTS orchestration_events_no_delete
            BEFORE DELETE ON orchestration_events BEGIN
                SELECT RAISE(ABORT, 'append-only orchestration_events');
            END;
            CREATE TRIGGER IF NOT EXISTS orchestration_blobs_no_update
            BEFORE UPDATE ON orchestration_blobs BEGIN
                SELECT RAISE(ABORT, 'immutable orchestration_blobs');
            END;
            CREATE TRIGGER IF NOT EXISTS orchestration_blobs_no_delete
            BEFORE DELETE ON orchestration_blobs BEGIN
                SELECT RAISE(ABORT, 'immutable orchestration_blobs');
            END;
            CREATE TRIGGER IF NOT EXISTS orchestration_meta_no_update
            BEFORE UPDATE ON orchestration_meta BEGIN
                SELECT RAISE(ABORT, 'immutable orchestration_meta');
            END;
            CREATE TRIGGER IF NOT EXISTS orchestration_meta_no_delete
            BEFORE DELETE ON orchestration_meta BEGIN
                SELECT RAISE(ABORT, 'immutable orchestration_meta');
            END;
            """
        )
        policy_hash = PaperSchedulePolicy.create().policy_hash
        row = self.connection.execute(
            "SELECT output_root_hash, policy_hash FROM orchestration_meta "
            "WHERE singleton=1"
        ).fetchone()
        if row is None:
            self.connection.execute(
                "INSERT INTO orchestration_meta "
                "(singleton, output_root_hash, policy_hash) VALUES (1, ?, ?)",
                (self.output_root_hash, policy_hash),
            )
        elif (
            row["output_root_hash"] != self.output_root_hash
            or row["policy_hash"] != policy_hash
        ):
            self.connection.close()
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_STATE_BINDING_MISMATCH"
            )
        self._secure_files()
        self.verify_integrity()

    def _secure_files(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.path) + suffix)
            if candidate.exists() and not candidate.is_symlink():
                os.chmod(candidate, 0o600)

    def close(self) -> None:
        self.connection.close()
        self._secure_files()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def events(self) -> Tuple[Mapping[str, Any], ...]:
        rows = self.connection.execute(
            "SELECT * FROM orchestration_events ORDER BY sequence"
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
        return _project_events(self.events())

    def verify_integrity(self) -> str:
        events = self.events()
        projection = _project_events(events)
        rows = self.connection.execute(
            "SELECT * FROM orchestration_blobs "
            "ORDER BY slot_id, blob_type"
        ).fetchall()
        observed = set()
        artifacts = {}
        for row in rows:
            blob_type = row["blob_type"]
            if blob_type not in _BLOB_STAGE:
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_BLOB_TYPE_INVALID"
                )
            body = bytes(row["artifact_bytes"])
            artifact = _strict_json_bytes(body)
            if (
                hashlib.sha256(body).hexdigest()
                != row["artifact_sha256"]
                or artifact.get(
                    "snapshot_hash"
                    if blob_type in ("ACCOUNT", "PERPETUAL")
                    else "binding_hash"
                )
                != row["artifact_hash"]
            ):
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_BLOB_HASH_INVALID"
                )
            if (
                blob_type == "ACCOUNT"
                and (
                    account_commission_reasons(
                        artifact, row["trust_hash"]
                    )
                    or artifact["server_time_probe"]["probe_hash"]
                    != row["runtime_probe_hash"]
                )
            ):
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_ACCOUNT_BLOB_INVALID"
                )
            if (
                blob_type == "PERPETUAL"
                and (
                    perpetual_context_reasons(
                        artifact, row["trust_hash"]
                    )
                    or artifact["server_time_probe"]["probe_hash"]
                    != row["runtime_probe_hash"]
                )
            ):
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_PERPETUAL_BLOB_INVALID"
                )
            state = projection.get(row["slot_id"])
            reference = (
                state.get(blob_type.lower()) if state is not None else None
            )
            if (
                not isinstance(reference, Mapping)
                or reference.get("artifact_name") != row["artifact_name"]
                or reference.get("artifact_sha256")
                != row["artifact_sha256"]
                or reference.get("artifact_hash") != row["artifact_hash"]
                or reference.get("trust_hash") != row["trust_hash"]
                or reference.get("runtime_probe_hash")
                != row["runtime_probe_hash"]
            ):
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_BLOB_EVENT_MISMATCH"
                )
            observed.add((row["slot_id"], blob_type))
            artifacts[(row["slot_id"], blob_type)] = (
                artifact,
                row["trust_hash"],
            )
        for slot_id, state in projection.items():
            for blob_type in _BLOB_STAGE:
                if state.get(blob_type.lower()) is not None and (
                    slot_id,
                    blob_type,
                ) not in observed:
                    raise ContextCycleOrchestrationError(
                        "CONTEXT_ORCHESTRATION_BLOB_MISSING"
                    )
            binding_pair = artifacts.get(
                (slot_id, "COST_BINDING")
            )
            account_pair = artifacts.get((slot_id, "ACCOUNT"))
            if binding_pair is not None:
                if (
                    account_pair is None
                    or not isinstance(state.get("paper"), Mapping)
                    or paper_account_cost_binding_reasons(
                        binding_pair[0],
                        binding_pair[1],
                        offline_paper_trusted_attestation_hash=state[
                            "paper"
                        ]["cycle_trust_hash"],
                        account_commission_trusted_attestation_hash=(
                            account_pair[1]
                        ),
                    )
                ):
                    raise ContextCycleOrchestrationError(
                        "CONTEXT_ORCHESTRATION_BINDING_BLOB_INVALID"
                    )
        return events[-1]["event_hash"] if events else _GENESIS_HASH

    def _append(
        self,
        event_type: str,
        slot: PaperSlot,
        event_time: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        last = self.connection.execute(
            "SELECT sequence, event_hash FROM orchestration_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 1 if last is None else last["sequence"] + 1
        previous = _GENESIS_HASH if last is None else last["event_hash"]
        event = _event_body(
            sequence,
            event_type,
            slot.slot_id,
            event_time,
            payload,
            previous,
        )
        self.connection.execute(
            "INSERT INTO orchestration_events "
            "(event_id,event_type,slot_id,event_time,payload_json,"
            "payload_hash,previous_event_hash,event_hash) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                event["event_id"],
                event["event_type"],
                event["slot_id"],
                event["event_time"],
                canonical_json(event["payload"]),
                event["payload_hash"],
                event["previous_event_hash"],
                event["event_hash"],
            ),
        )
        return event

    def claim(
        self,
        slot: PaperSlot,
        *,
        worker_id: str,
        claimed_at: object,
        runtime_probe: Mapping[str, Any],
    ) -> OrchestrationClaim:
        worker = _worker(worker_id)
        claimed, claimed_text = _utc(claimed_at)
        due, _ = _utc(slot.due_at)
        expires, _ = _utc(slot.expires_at)
        if not due <= claimed < expires:
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_SLOT_INACTIVE"
            )
        probe_trust = server_time_probe_trust_hash(runtime_probe)
        if server_time_probe_reasons(runtime_probe, probe_trust):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_RUNTIME_GATE_INVALID"
            )
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.verify_integrity()
            state = self.projection().get(slot.slot_id)
            if state is not None and state["status"] == "SUCCEEDED":
                self.connection.commit()
                return OrchestrationClaim(
                    "ALREADY_SUCCEEDED",
                    slot,
                    state["attempt_count"],
                    None,
                    state["stage"],
                )
            if (
                state is not None
                and state["status"] == "CLAIMED"
                and _utc(state["lease_expires_at"])[0] > claimed
            ):
                self.connection.commit()
                return OrchestrationClaim(
                    "BUSY",
                    slot,
                    state["attempt_count"],
                    state["lease_expires_at"],
                    state["stage"],
                )
            attempt = 1 if state is None else state["attempt_count"] + 1
            stage = "NONE" if state is None else state["stage"]
            lease = min(
                claimed + timedelta(
                    seconds=PaperSchedulePolicy.create().lease_seconds
                ),
                expires,
            )
            lease_text = utc_datetime(lease)
            payload = {
                **_slot_core(slot),
                "worker_id": worker,
                "attempt": attempt,
                "stage": stage,
                "lease_expires_at": lease_text,
                "runtime_probe": deepcopy(dict(runtime_probe)),
                "runtime_probe_trust_hash": probe_trust,
                "physical_network_request_count": 3,
            }
            self._append(
                "ORCHESTRATION_CLAIMED", slot, claimed_text, payload
            )
            self.verify_integrity()
            self.connection.commit()
            return OrchestrationClaim(
                "CLAIMED", slot, attempt, lease_text, stage
            )
        except Exception:
            self.connection.rollback()
            raise

    def _active(
        self,
        claim: OrchestrationClaim,
        expected_stage: str,
        event_time: Optional[datetime] = None,
    ) -> Mapping[str, Any]:
        state = self.projection().get(claim.slot.slot_id)
        if (
            state is None
            or state["status"] != "CLAIMED"
            or state["attempt_count"] != claim.attempt
            or state["stage"] != expected_stage
        ):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_CLAIM_STALE"
            )
        if (
            event_time is not None
            and event_time >= _utc(state["lease_expires_at"])[0]
        ):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_LEASE_EXPIRED"
            )
        return state

    def prepare_blob(
        self,
        claim: OrchestrationClaim,
        *,
        blob_type: str,
        artifact_name: str,
        artifact_bytes: bytes,
        artifact_hash: str,
        trust_hash: str,
        runtime_probe_hash: str,
        prepared_at: object,
        physical_network_request_count: int,
    ) -> None:
        expected_event, expected_stage = _BLOB_STAGE.get(
            blob_type, (None, None)
        )
        previous_stage = {
            "ACCOUNT": "NONE",
            "PERPETUAL": "PAPER",
            "COST_BINDING": "PERPETUAL",
        }.get(blob_type)
        if expected_event is None:
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_BLOB_TYPE_INVALID"
            )
        name = _artifact_name(artifact_name)
        body = bytes(artifact_bytes)
        artifact = _strict_json_bytes(body)
        hash_field = (
            "snapshot_hash"
            if blob_type in ("ACCOUNT", "PERPETUAL")
            else "binding_hash"
        )
        if artifact.get(hash_field) != _hash(
            artifact_hash, "CONTEXT_ORCHESTRATION_ARTIFACT_HASH_INVALID"
        ):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_ARTIFACT_HASH_INVALID"
            )
        trust = _hash(
            trust_hash, "CONTEXT_ORCHESTRATION_TRUST_HASH_INVALID"
        )
        probe_hash = _hash(
            runtime_probe_hash,
            "CONTEXT_ORCHESTRATION_PROBE_HASH_INVALID",
        )
        if (
            isinstance(physical_network_request_count, bool)
            or physical_network_request_count
            != (3 if blob_type == "ACCOUNT" else 5 if blob_type == "PERPETUAL" else 0)
        ):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_NETWORK_COUNT_INVALID"
            )
        prepared, prepared_text = _utc(prepared_at)
        if not _utc(claim.slot.due_at)[0] <= prepared < _utc(
            claim.slot.expires_at
        )[0]:
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_EVENT_OUTSIDE_SLOT"
            )
        sha = hashlib.sha256(body).hexdigest()
        payload = {
            **_slot_core(claim.slot),
            "blob_type": blob_type,
            "artifact_name": name,
            "artifact_sha256": sha,
            "artifact_hash": artifact_hash,
            "trust_hash": trust,
            "runtime_probe_hash": probe_hash,
            "physical_network_request_count": physical_network_request_count,
        }
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.verify_integrity()
            self._active(claim, previous_stage, prepared)
            self.connection.execute(
                "INSERT INTO orchestration_blobs "
                "(slot_id,blob_type,artifact_name,artifact_bytes,"
                "artifact_sha256,artifact_hash,trust_hash,"
                "runtime_probe_hash,prepared_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    claim.slot.slot_id,
                    blob_type,
                    name,
                    body,
                    sha,
                    artifact_hash,
                    trust,
                    probe_hash,
                    prepared_text,
                ),
            )
            self._append(
                expected_event, claim.slot, prepared_text, payload
            )
            self.verify_integrity()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def load_blob(
        self, slot: PaperSlot, blob_type: str
    ) -> Mapping[str, Any]:
        self.verify_integrity()
        row = self.connection.execute(
            "SELECT * FROM orchestration_blobs "
            "WHERE slot_id=? AND blob_type=?",
            (slot.slot_id, blob_type),
        ).fetchone()
        if row is None:
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_BLOB_MISSING"
            )
        return {
            "artifact_name": row["artifact_name"],
            "artifact_bytes": bytes(row["artifact_bytes"]),
            "artifact_sha256": row["artifact_sha256"],
            "artifact_hash": row["artifact_hash"],
            "trust_hash": row["trust_hash"],
            "runtime_probe_hash": row["runtime_probe_hash"],
            "artifact": _strict_json_bytes(bytes(row["artifact_bytes"])),
        }

    def reference_paper(
        self,
        claim: OrchestrationClaim,
        *,
        artifact_name: str,
        cycle_run_hash: str,
        cycle_trust_hash: str,
        recorded_at: object,
        physical_network_request_count: int,
    ) -> None:
        if physical_network_request_count not in (0, 4):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_NETWORK_COUNT_INVALID"
            )
        recorded, recorded_text = _utc(recorded_at)
        payload = {
            **_slot_core(claim.slot),
            "artifact_name": _artifact_name(artifact_name),
            "cycle_run_hash": _hash(
                cycle_run_hash,
                "CONTEXT_ORCHESTRATION_PAPER_HASH_INVALID",
            ),
            "cycle_trust_hash": _hash(
                cycle_trust_hash,
                "CONTEXT_ORCHESTRATION_PAPER_TRUST_INVALID",
            ),
            "physical_network_request_count": physical_network_request_count,
        }
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.verify_integrity()
            self._active(claim, "ACCOUNT", recorded)
            self._append(
                "PAPER_REFERENCED", claim.slot, recorded_text, payload
            )
            self.verify_integrity()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def succeed(
        self,
        claim: OrchestrationClaim,
        *,
        context_result: Mapping[str, Any],
        completed_at: object,
    ) -> None:
        completed, completed_text = _utc(completed_at)
        payload = {
            **_slot_core(claim.slot),
            "bundle_hash": _hash(
                context_result.get("bundle_hash"),
                "CONTEXT_ORCHESTRATION_CONTEXT_HASH_INVALID",
            ),
            "bundle_trust_hash": _hash(
                context_result.get("bundle_trust_hash"),
                "CONTEXT_ORCHESTRATION_CONTEXT_TRUST_INVALID",
            ),
            "schedule_snapshot_hash": _hash(
                context_result.get("schedule_snapshot_hash"),
                "CONTEXT_ORCHESTRATION_CONTEXT_HASH_INVALID",
            ),
            "schedule_trust_hash": _hash(
                context_result.get("schedule_trust_hash"),
                "CONTEXT_ORCHESTRATION_CONTEXT_TRUST_INVALID",
            ),
            "physical_network_request_count": 0,
        }
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.verify_integrity()
            self._active(claim, "COST_BINDING", completed)
            self._append(
                "CONTEXT_SUCCEEDED", claim.slot, completed_text, payload
            )
            self.verify_integrity()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def fail(
        self,
        claim: OrchestrationClaim,
        *,
        reason_code: str,
        failed_at: object,
        physical_network_request_count: int,
    ) -> None:
        if (
            not isinstance(reason_code, str)
            or not reason_code
            or len(reason_code) > 180
            or isinstance(physical_network_request_count, bool)
            or not isinstance(physical_network_request_count, int)
            or physical_network_request_count < 0
        ):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_FAILURE_INVALID"
            )
        _, failed_text = _utc(failed_at)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.verify_integrity()
            state = self.projection().get(claim.slot.slot_id)
            if (
                state is not None
                and state["status"] == "CLAIMED"
                and state["attempt_count"] == claim.attempt
            ):
                self._append(
                    "ORCHESTRATION_FAILED",
                    claim.slot,
                    failed_text,
                    {
                        **_slot_core(claim.slot),
                        "stage": state["stage"],
                        "reason_code": reason_code,
                        "physical_network_request_count": (
                            physical_network_request_count
                        ),
                    },
                )
                self.verify_integrity()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise


def _public_projection(
    projection: Mapping[str, Mapping[str, Any]],
) -> Sequence[Mapping[str, Any]]:
    results = []
    for state in sorted(
        projection.values(), key=lambda item: item["scheduled_for"]
    ):
        results.append(
            {
                "slot_id": state["slot_id"],
                "scheduled_for": state["scheduled_for"],
                "due_at": state["due_at"],
                "expires_at": state["expires_at"],
                "status": state["status"],
                "stage": state["stage"],
                "attempt_count": state["attempt_count"],
                "failure_count": state["failure_count"],
                "account_hash_or_null": (
                    state["account"]["artifact_hash"]
                    if state["account"]
                    else None
                ),
                "paper_hash_or_null": (
                    state["paper"]["cycle_run_hash"]
                    if state["paper"]
                    else None
                ),
                "perpetual_hash_or_null": (
                    state["perpetual"]["artifact_hash"]
                    if state["perpetual"]
                    else None
                ),
                "cost_binding_hash_or_null": (
                    state["cost_binding"]["artifact_hash"]
                    if state["cost_binding"]
                    else None
                ),
                "context_bundle_hash_or_null": (
                    state["context"]["bundle_hash"]
                    if state["context"]
                    else None
                ),
            }
        )
    return results


def _summary(
    events: Sequence[Mapping[str, Any]],
    projection: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    statuses = [state["status"] for state in projection.values()]
    succeeded_states = [
        state
        for state in projection.values()
        if state["status"] == "SUCCEEDED"
    ]
    probes = [
        event["payload"]["runtime_probe"]["probe_hash"]
        for event in events
        if event["event_type"] == "ORCHESTRATION_CLAIMED"
    ]
    return {
        "known_slot_count": len(projection),
        "succeeded_slot_count": statuses.count("SUCCEEDED"),
        "failed_slot_count": statuses.count("FAILED"),
        "claimed_slot_count": statuses.count("CLAIMED"),
        "attempt_count": sum(
            state["attempt_count"] for state in projection.values()
        ),
        "failure_count": sum(
            state["failure_count"] for state in projection.values()
        ),
        "runtime_gate_count": len(probes),
        "unique_runtime_probe_count": len(set(probes)),
        "physical_network_request_count": sum(
            event["payload"].get("physical_network_request_count", 0)
            for event in events
        ),
        "normal_path_shared_gate": (
            bool(succeeded_states)
            and all(
                state["attempt_count"] == 1
                for state in succeeded_states
            )
        ),
    }


@lru_cache(maxsize=1)
def _snapshot_validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas", "context-cycle-orchestration-snapshot-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def build_orchestration_snapshot(
    state: ContextCycleOrchestrationState,
) -> Dict[str, Any]:
    if not isinstance(state, ContextCycleOrchestrationState):
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_STATE_INVALID"
        )
    chain_end = state.verify_integrity()
    events = list(state.events())
    projection = _project_events(events)
    latest_time = (
        events[-1]["event_time"]
        if events
        else utc_datetime(datetime.now(timezone.utc))
    )
    policy = PaperSchedulePolicy.create()
    snapshot = {
        "$schema": "./context-cycle-orchestration-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": stable_id(
            "context_cycle_orchestration",
            {
                "policy_hash": policy.policy_hash,
                "event_chain_end_hash": chain_end,
            },
        ),
        "snapshot_hash": "",
        "recorded_at": latest_time,
        "policy": {
            **policy.business_payload(),
            "policy_hash": policy.policy_hash,
            "stage_order": list(_STAGES),
            "normal_path_request_count": 15,
        },
        "events": events,
        "events_root_hash": business_hash(events),
        "event_chain_end_hash": chain_end,
        "slots": list(_public_projection(projection)),
        "summary": _summary(events, projection),
        "state_integrity": "VERIFIED_APPEND_ONLY_WAL_AND_SOURCE_BLOBS",
        "orchestration_eligibility": "LOCAL_RECOVERABLE_RESEARCH_ONLY",
        "paper_eligibility": "LONGITUDINAL_COLLECTION_IN_PROGRESS",
        "production_eligibility": "NOT_APPROVED",
        "profitability_eligibility": (
            "INSUFFICIENT_DURATION_EXECUTION_AND_AI"
        ),
        "warnings": list(_WARNINGS),
    }
    snapshot["snapshot_hash"] = artifact_self_hash(
        snapshot, "snapshot_hash"
    )
    if tuple(_snapshot_validator().iter_errors(snapshot)):
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_SNAPSHOT_SCHEMA_INVALID"
        )
    return snapshot


def orchestration_snapshot_trust_hash(
    snapshot: Mapping[str, Any],
) -> str:
    try:
        return business_hash(
            {
                "attestation_type": _ATTESTATION_TYPE,
                "snapshot_id": snapshot["snapshot_id"],
                "snapshot_hash": snapshot["snapshot_hash"],
                "policy_hash": snapshot["policy"]["policy_hash"],
                "events_root_hash": snapshot["events_root_hash"],
                "event_chain_end_hash": snapshot[
                    "event_chain_end_hash"
                ],
                "successful_context_bundle_hashes": [
                    slot["context_bundle_hash_or_null"]
                    for slot in snapshot["slots"]
                    if slot["status"] == "SUCCEEDED"
                ],
            }
        )
    except (KeyError, TypeError):
        return ""


def orchestration_snapshot_reasons(
    snapshot: Mapping[str, Any],
    trusted_attestation_hash: str,
) -> Tuple[str, ...]:
    if not isinstance(snapshot, Mapping):
        return ("CONTEXT_ORCHESTRATION_SNAPSHOT_INVALID",)
    reasons = []
    try:
        if tuple(_snapshot_validator().iter_errors(snapshot)):
            reasons.append(
                "CONTEXT_ORCHESTRATION_SNAPSHOT_SCHEMA_INVALID"
            )
        if artifact_self_hash(
            snapshot, "snapshot_hash"
        ) != snapshot.get("snapshot_hash"):
            reasons.append(
                "CONTEXT_ORCHESTRATION_SNAPSHOT_SELF_HASH_MISMATCH"
            )
        if (
            orchestration_snapshot_trust_hash(snapshot)
            != trusted_attestation_hash
        ):
            reasons.append(
                "CONTEXT_ORCHESTRATION_SNAPSHOT_TRUST_HASH_MISMATCH"
            )
        policy = PaperSchedulePolicy.create()
        expected_policy = {
            **policy.business_payload(),
            "policy_hash": policy.policy_hash,
            "stage_order": list(_STAGES),
            "normal_path_request_count": 15,
        }
        if snapshot.get("policy") != expected_policy:
            reasons.append(
                "CONTEXT_ORCHESTRATION_SNAPSHOT_POLICY_MISMATCH"
            )
        events = snapshot["events"]
        projection = _project_events(events)
        if snapshot.get("events_root_hash") != business_hash(events):
            reasons.append(
                "CONTEXT_ORCHESTRATION_SNAPSHOT_EVENTS_MISMATCH"
            )
        expected_end = (
            events[-1]["event_hash"] if events else _GENESIS_HASH
        )
        if snapshot.get("event_chain_end_hash") != expected_end:
            reasons.append(
                "CONTEXT_ORCHESTRATION_SNAPSHOT_CHAIN_MISMATCH"
            )
        expected_recorded_at = (
            events[-1]["event_time"] if events else None
        )
        if snapshot.get("recorded_at") != expected_recorded_at:
            reasons.append(
                "CONTEXT_ORCHESTRATION_SNAPSHOT_TIME_MISMATCH"
            )
        if snapshot.get("snapshot_id") != stable_id(
            "context_cycle_orchestration",
            {
                "policy_hash": policy.policy_hash,
                "event_chain_end_hash": expected_end,
            },
        ):
            reasons.append(
                "CONTEXT_ORCHESTRATION_SNAPSHOT_ID_MISMATCH"
            )
        if snapshot.get("slots") != list(_public_projection(projection)):
            reasons.append(
                "CONTEXT_ORCHESTRATION_SNAPSHOT_SLOTS_MISMATCH"
            )
        if snapshot.get("summary") != _summary(events, projection):
            reasons.append(
                "CONTEXT_ORCHESTRATION_SNAPSHOT_SUMMARY_MISMATCH"
            )
    except (
        KeyError,
        TypeError,
        ValueError,
        ContextCycleOrchestrationError,
    ):
        reasons.append(
            "CONTEXT_ORCHESTRATION_SNAPSHOT_REPLAY_INVALID"
        )
    for name, expected in (
        (
            "state_integrity",
            "VERIFIED_APPEND_ONLY_WAL_AND_SOURCE_BLOBS",
        ),
        (
            "orchestration_eligibility",
            "LOCAL_RECOVERABLE_RESEARCH_ONLY",
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
                "CONTEXT_ORCHESTRATION_SNAPSHOT_ELIGIBILITY_INVALID"
            )
    if snapshot.get("warnings") != list(_WARNINGS):
        reasons.append(
            "CONTEXT_ORCHESTRATION_SNAPSHOT_WARNINGS_INVALID"
        )
    return tuple(sorted(set(reasons)))


def _publish_blob(
    output_root: Path,
    blob: Mapping[str, Any],
    directory: str,
) -> Tuple[Path, bool]:
    created = _publish_immutable(
        Path(output_root),
        blob["artifact_name"],
        blob["artifact_bytes"],
        output_directory=directory,
    )
    path = Path(output_root).resolve() / directory / blob["artifact_name"]
    os.chmod(path, 0o600)
    return path, created


def _read_paper(path: Path, trust_hash: str) -> Mapping[str, Any]:
    try:
        body = path.read_bytes()
    except OSError as error:
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_PAPER_ARTIFACT_MISSING"
        ) from error
    paper = _strict_json_bytes(body)
    if offline_paper_run_reasons(paper, trust_hash):
        raise ContextCycleOrchestrationError(
            "CONTEXT_ORCHESTRATION_PAPER_INVALID"
        )
    return paper


class _CountingTransport:
    def __init__(self, transport):
        self.transport = transport
        self.calls = 0

    def get(self, *args):
        self.calls += 1
        return self.transport.get(*args)


def run_context_complete_orchestration(
    *,
    orchestration_state_path: Path,
    paper_state_path: Path,
    context_state_path: Path,
    output_root: Path,
    worker_id: str,
    signer: Optional[HmacAccountSigner] = None,
    workspace_root: Optional[Path] = None,
    server_time_transport=None,
    account_transport=None,
    paper_transport=None,
    futures_transport=None,
    monotonic_ns=None,
    fault_after_account_prepare: bool = False,
    fault_after_paper_reference: bool = False,
    fault_after_perpetual_prepare: bool = False,
    fault_after_binding_prepare: bool = False,
) -> Dict[str, Any]:
    """Run or recover one complete 4h research cycle."""

    own_signer = signer is None
    active_signer = signer or load_account_signer_from_environment(
        output_root=Path(output_root),
        workspace_root=workspace_root,
    )
    claim = None
    state = None
    accounted = 0
    counted_time = _CountingTransport(
        server_time_transport or BinanceServerTimeTransport()
    )
    counted_account = None
    counted_paper = None
    counted_perpetual = None
    try:
        gate = open_verified_runtime_gate(
            server_time_transport=counted_time,
            monotonic_ns=monotonic_ns,
        )
        invocation = gate.clock()
        slot = PaperSchedulePolicy.create().current_slot(invocation)
        state = ContextCycleOrchestrationState(
            Path(orchestration_state_path), Path(output_root)
        )
        claim = state.claim(
            slot,
            worker_id=worker_id,
            claimed_at=invocation,
            runtime_probe=gate.probe,
        )
        accounted = 3
        if claim.outcome in ("BUSY", "ALREADY_SUCCEEDED"):
            snapshot = build_orchestration_snapshot(state)
            trust = orchestration_snapshot_trust_hash(snapshot)
            return {
                "outcome": claim.outcome,
                "slot_id": slot.slot_id,
                "physical_network_request_count": 3,
                "account_request_count": 0,
                "paper_request_count": 0,
                "perpetual_request_count": 0,
                "runtime_probe_hash": gate.probe["probe_hash"],
                "orchestration_snapshot_hash": snapshot["snapshot_hash"],
                "orchestration_trust_hash": trust,
                "lease_expires_at_or_null": claim.lease_expires_at,
            }

        stage = state.projection()[slot.slot_id]["stage"]
        if stage == "NONE":
            counted_account = _CountingTransport(
                account_transport
                or BinanceAccountCommissionTransport(clock=gate.clock)
            )
            account_capture = capture_account_commission_with_runtime_gate(
                signer=active_signer,
                runtime_gate=gate,
                account_transport=counted_account,
            )
            account = build_account_commission_snapshot(account_capture)
            account_trust = account_commission_trust_hash(account)
            if account_commission_reasons(account, account_trust):
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_ACCOUNT_INVALID"
                )
            account_bytes = json.dumps(
                account, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            state.prepare_blob(
                claim,
                blob_type="ACCOUNT",
                artifact_name=account["snapshot_id"].lower() + ".json",
                artifact_bytes=account_bytes,
                artifact_hash=account["snapshot_hash"],
                trust_hash=account_trust,
                runtime_probe_hash=gate.probe["probe_hash"],
                prepared_at=gate.clock(),
                physical_network_request_count=3,
            )
            accounted += 3
            if fault_after_account_prepare:
                raise ContextCycleOrchestrationError(
                    "INJECTED_AFTER_ACCOUNT_PREPARE"
                )
        account_blob = state.load_blob(slot, "ACCOUNT")
        _publish_blob(Path(output_root), account_blob, "account-cost")
        stage = state.projection()[slot.slot_id]["stage"]

        if stage == "ACCOUNT":
            counted_paper = _CountingTransport(
                paper_transport
                or BinanceOfflinePaperTransport(clock=gate.clock)
            )
            paper_result = run_due_paper_cycle(
                state_path=Path(paper_state_path),
                output_root=Path(output_root),
                worker_id=worker_id,
                transport=counted_paper,
                clock=gate.clock,
            )
            if paper_result["outcome"] == "BUSY":
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_PAPER_BUSY"
                )
            paper_name = Path(paper_result["artifact_path"]).name
            state.reference_paper(
                claim,
                artifact_name=paper_name,
                cycle_run_hash=paper_result["cycle_run_hash"],
                cycle_trust_hash=paper_result["cycle_trust_hash"],
                recorded_at=gate.clock(),
                physical_network_request_count=paper_result[
                    "network_request_count"
                ],
            )
            accounted += paper_result["network_request_count"]
            if fault_after_paper_reference:
                raise ContextCycleOrchestrationError(
                    "INJECTED_AFTER_PAPER_REFERENCE"
                )
        projection = state.projection()[slot.slot_id]
        paper_ref = projection["paper"]
        paper_path = (
            Path(output_root).resolve()
            / "paper"
            / paper_ref["artifact_name"]
        )
        paper = _read_paper(
            paper_path, paper_ref["cycle_trust_hash"]
        )
        stage = projection["stage"]

        if stage == "PAPER":
            counted_perpetual = _CountingTransport(
                futures_transport
                or BinancePerpetualContextTransport(clock=gate.clock)
            )
            perpetual_capture = (
                capture_perpetual_context_with_runtime_gate(
                    runtime_gate=gate,
                    futures_transport=counted_perpetual,
                )
            )
            perpetual = build_perpetual_context_snapshot(
                perpetual_capture
            )
            perpetual_trust = perpetual_context_trust_hash(perpetual)
            if perpetual_context_reasons(
                perpetual, perpetual_trust
            ):
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_PERPETUAL_INVALID"
                )
            perpetual_bytes = json.dumps(
                perpetual, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            state.prepare_blob(
                claim,
                blob_type="PERPETUAL",
                artifact_name=perpetual["snapshot_id"].lower() + ".json",
                artifact_bytes=perpetual_bytes,
                artifact_hash=perpetual["snapshot_hash"],
                trust_hash=perpetual_trust,
                runtime_probe_hash=gate.probe["probe_hash"],
                prepared_at=gate.clock(),
                physical_network_request_count=5,
            )
            accounted += 5
            if fault_after_perpetual_prepare:
                raise ContextCycleOrchestrationError(
                    "INJECTED_AFTER_PERPETUAL_PREPARE"
                )
        perpetual_blob = state.load_blob(slot, "PERPETUAL")
        _publish_blob(
            Path(output_root), perpetual_blob, "market-data"
        )
        stage = state.projection()[slot.slot_id]["stage"]

        if stage == "PERPETUAL":
            binding = build_paper_account_cost_binding(
                offline_paper_run=paper,
                offline_paper_trusted_attestation_hash=paper_ref[
                    "cycle_trust_hash"
                ],
                account_commission_snapshot=account_blob["artifact"],
                account_commission_trusted_attestation_hash=account_blob[
                    "trust_hash"
                ],
                created_at=gate.clock(),
            )
            binding_trust = paper_account_cost_binding_trust_hash(
                binding
            )
            if paper_account_cost_binding_reasons(
                binding,
                binding_trust,
                offline_paper_trusted_attestation_hash=paper_ref[
                    "cycle_trust_hash"
                ],
                account_commission_trusted_attestation_hash=account_blob[
                    "trust_hash"
                ],
            ):
                raise ContextCycleOrchestrationError(
                    "CONTEXT_ORCHESTRATION_BINDING_INVALID"
                )
            binding_bytes = json.dumps(
                binding, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            state.prepare_blob(
                claim,
                blob_type="COST_BINDING",
                artifact_name=binding["binding_id"].lower() + ".json",
                artifact_bytes=binding_bytes,
                artifact_hash=binding["binding_hash"],
                trust_hash=binding_trust,
                runtime_probe_hash=gate.probe["probe_hash"],
                prepared_at=gate.clock(),
                physical_network_request_count=0,
            )
            if fault_after_binding_prepare:
                raise ContextCycleOrchestrationError(
                    "INJECTED_AFTER_BINDING_PREPARE"
                )
        binding_blob = state.load_blob(slot, "COST_BINDING")
        _publish_blob(Path(output_root), binding_blob, "paper-cost")

        context_result = run_context_complete_paper_cycle(
            state_path=Path(context_state_path),
            output_root=Path(output_root),
            worker_id=worker_id,
            clock=gate.clock,
            paper_cost_binding=binding_blob["artifact"],
            paper_cost_binding_trusted_attestation_hash=binding_blob[
                "trust_hash"
            ],
            offline_paper_trusted_attestation_hash=paper_ref[
                "cycle_trust_hash"
            ],
            account_commission_trusted_attestation_hash=account_blob[
                "trust_hash"
            ],
            perpetual_context_snapshot=perpetual_blob["artifact"],
            perpetual_context_trusted_attestation_hash=perpetual_blob[
                "trust_hash"
            ],
        )
        state.succeed(
            claim, context_result=context_result, completed_at=gate.clock()
        )
        snapshot = build_orchestration_snapshot(state)
        snapshot_trust = orchestration_snapshot_trust_hash(snapshot)
        if orchestration_snapshot_reasons(snapshot, snapshot_trust):
            raise ContextCycleOrchestrationError(
                "CONTEXT_ORCHESTRATION_SNAPSHOT_INVALID"
            )
        snapshot_name = (
            "context-orchestration-" + slot.slot_id.lower() + ".json"
        )
        snapshot_bytes = json.dumps(
            snapshot, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        snapshot_created = _publish_immutable(
            Path(output_root),
            snapshot_name,
            snapshot_bytes,
            output_directory="paper-context",
        )
        snapshot_path = (
            Path(output_root).resolve()
            / "paper-context"
            / snapshot_name
        )
        os.chmod(snapshot_path, 0o600)
        account_count = counted_account.calls if counted_account else 0
        paper_count = counted_paper.calls if counted_paper else 0
        perpetual_count = (
            counted_perpetual.calls if counted_perpetual else 0
        )
        physical = (
            counted_time.calls
            + account_count
            + paper_count
            + perpetual_count
        )
        return {
            "outcome": "EXECUTED" if claim.attempt == 1 else "RECOVERED",
            "slot_id": slot.slot_id,
            "physical_network_request_count": physical,
            "account_request_count": account_count,
            "paper_request_count": paper_count,
            "perpetual_request_count": perpetual_count,
            "runtime_probe_hash": gate.probe["probe_hash"],
            "normal_path_shared_gate": claim.attempt == 1,
            "context_bundle_hash": context_result["bundle_hash"],
            "context_bundle_trust_hash": context_result[
                "bundle_trust_hash"
            ],
            "orchestration_snapshot_path": str(snapshot_path),
            "orchestration_snapshot_created": snapshot_created,
            "orchestration_snapshot_hash": snapshot["snapshot_hash"],
            "orchestration_trust_hash": snapshot_trust,
            "context_complete_slot_count": context_result[
                "context_complete_slot_count"
            ],
            "ninety_day_context_complete": context_result[
                "ninety_day_context_complete"
            ],
            "production_eligibility": "NOT_APPROVED",
            "profitability_eligibility": (
                "INSUFFICIENT_DURATION_EXECUTION_AND_AI"
            ),
        }
    except Exception as error:
        if state is not None and claim is not None and claim.outcome == "CLAIMED":
            physical = (
                counted_time.calls
                + (counted_account.calls if counted_account else 0)
                + (counted_paper.calls if counted_paper else 0)
                + (
                    counted_perpetual.calls
                    if counted_perpetual
                    else 0
                )
            )
            uncommitted = max(0, physical - accounted)
            try:
                state.fail(
                    claim,
                    reason_code=getattr(
                        error, "reason_code", type(error).__name__
                    ),
                    failed_at=(
                        gate.clock()
                        if "gate" in locals()
                        else datetime.now(timezone.utc)
                    ),
                    physical_network_request_count=uncommitted,
                )
            except ContextCycleOrchestrationError:
                pass
        if isinstance(error, ContextCycleOrchestrationError):
            raise
        if isinstance(
            error,
            (
                AccountCommissionError,
                PaperScheduleError,
                PerpetualContextError,
                PaperCostBindingError,
                PaperContextScheduleError,
                RuntimeHealthError,
            ),
        ):
            raise ContextCycleOrchestrationError(
                error.reason_code
            ) from error
        raise
    finally:
        if state is not None:
            state.close()
        if own_signer:
            active_signer.close()
