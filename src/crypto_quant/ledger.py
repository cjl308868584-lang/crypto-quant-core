"""SQLite WAL append-only ledger, outbox, and minimal projections."""

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Tuple

from .canonical import business_hash, canonical_decimal, canonical_json, utc_datetime
from .contracts import EventEnvelope
from .errors import LedgerConflictError, LedgerIntegrityError

_GENESIS_HASH = "0" * 64
_VERSIONED_PROJECTIONS: Mapping[str, Tuple[str, str, Tuple[str, ...]]] = {
    "ExecutionIntentStateRecorded": (
        "execution_intents_projection",
        "intent_id",
        ("risk_decision_id", "target_id", "instrument_id", "intent_hash"),
    ),
    "ChildOrderAttemptStateRecorded": (
        "child_order_attempts_projection",
        "attempt_id",
        ("intent_id", "attempt_no", "client_order_id", "attempt_hash"),
    ),
    "OrderStateRecorded": (
        "orders_projection",
        "order_id",
        (
            "attempt_id",
            "intent_id",
            "instrument_id",
            "client_order_id",
            "requested_quantity",
            "cumulative_filled_quantity",
        ),
    ),
    "PositionStateRecorded": (
        "positions_projection",
        "position_id",
        (
            "account_id",
            "instrument_id",
            "signed_quantity",
            "instrument_metadata_hash",
        ),
    ),
    "RiskLockStateRecorded": (
        "risk_locks_projection",
        "lock_id",
        ("lock_type", "scope", "scope_id"),
    ),
    "DeploymentStateRecorded": (
        "model_deployments_projection",
        "deployment_line_id",
        ("stage", "authoritative_stage_multiplier", "record_hash"),
    ),
    "PositionExecutorStateRecorded": (
        "position_executors_projection",
        "executor_id",
        (
            "account_id",
            "economic_asset",
            "current_target_id_or_null",
            "active_intent_id_or_null",
        ),
    ),
}
_VERSIONED_PROJECTION_TABLES = tuple(
    dict.fromkeys(spec[0] for spec in _VERSIONED_PROJECTIONS.values())
)
_ORDER_STATES = {
    "CREATED",
    "RISK_APPROVED",
    "SUBMITTING",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "CANCEL_PENDING",
    "FILLED",
    "CANCELED",
    "RISK_DENIED",
    "REJECTED",
    "EXPIRED",
    "FAILED_PRE_SUBMIT",
    "UNKNOWN",
}
_INTENT_STATES = {
    "PLANNED",
    "ACTIVE",
    "SATISFIED",
    "CANCELED",
    "EXPIRED",
    "BLOCKED_UNKNOWN",
}
_ATTEMPT_STATES = {"PLANNED", "ACTIVE", "TERMINAL", "UNKNOWN"}
_EXECUTOR_STATES = {
    "PLANNED",
    "CLOSING_OPPOSITE",
    "WAITING_FLAT",
    "OPENING_OR_ADJUSTING",
    "VERIFYING",
    "SATISFIED",
    "BLOCKED_UNKNOWN",
    "ABORTED_BY_RISK",
    "EXPIRED",
}
_DEPLOYMENT_STATES = {"ACTIVE", "RETIRED"}
_RISK_LOCK_STATES = {"ACTIVE", "RELEASED"}
_RISK_LOCK_TYPES = {
    "STARTUP",
    "DATA_STALE",
    "MODEL_INVALID",
    "ORDER_UNKNOWN",
    "POSITION_MISMATCH",
    "CONNECTIVITY",
    "DAILY_LOSS",
    "DRAWDOWN_10",
    "DRAWDOWN_12",
    "DRAWDOWN_15",
    "DRAWDOWN_20",
    "DISASTER_STOP_MISSING",
    "PROTECTIVE_REPLACE",
    "COMPLIANCE",
    "EXTERNAL_POSITION",
    "MANUAL",
}
_RISK_LOCK_SCOPES = {"GLOBAL", "ACCOUNT", "INSTRUMENT", "MODEL"}
_DEPLOYMENT_MULTIPLIERS = {
    "CANARY_25": Decimal("0.25"),
    "CANARY_50": Decimal("0.5"),
    "CANARY_75": Decimal("0.75"),
    "CHAMPION": Decimal("1"),
}


@dataclass(frozen=True)
class AppendResult:
    sequence: int
    inserted: bool
    ledger_hash: str


class EventLedger:
    """Single-process event store; deliberately exposes no Broker interface."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        mode = self.connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            raise LedgerIntegrityError("SQLite WAL mode could not be enabled")
        self._create_schema()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "EventLedger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                causation_id TEXT,
                run_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                available_at TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                source TEXT NOT NULL,
                ordering_exception_reason TEXT,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL,
                previous_ledger_hash TEXT NOT NULL,
                ledger_hash TEXT NOT NULL UNIQUE
            );

            CREATE TRIGGER IF NOT EXISTS events_no_update
            BEFORE UPDATE ON events
            BEGIN
                SELECT RAISE(ABORT, 'events are immutable');
            END;

            CREATE TRIGGER IF NOT EXISTS events_no_delete
            BEFORE DELETE ON events
            BEGIN
                SELECT RAISE(ABORT, 'events are immutable');
            END;

            CREATE TABLE IF NOT EXISTS outbox (
                outbox_id TEXT PRIMARY KEY,
                intent_id TEXT NOT NULL UNIQUE,
                source_event_id TEXT NOT NULL UNIQUE,
                command_json TEXT NOT NULL,
                command_hash TEXT NOT NULL,
                status TEXT NOT NULL CHECK(
                    status IN ('PENDING', 'UNKNOWN', 'ACKNOWLEDGED', 'CANCELED')
                ),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(source_event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS operating_costs_projection (
                event_id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                amount_usdt TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY(event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS external_cash_flows_projection (
                event_id TEXT PRIMARY KEY,
                flow_type TEXT NOT NULL,
                signed_amount_usdt TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY(event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS execution_intents_projection (
                entity_id TEXT PRIMARY KEY,
                entity_version INTEGER NOT NULL CHECK(entity_version >= 1),
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                last_event_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                FOREIGN KEY(last_event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS child_order_attempts_projection (
                entity_id TEXT PRIMARY KEY,
                entity_version INTEGER NOT NULL CHECK(entity_version >= 1),
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                last_event_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                FOREIGN KEY(last_event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS orders_projection (
                entity_id TEXT PRIMARY KEY,
                entity_version INTEGER NOT NULL CHECK(entity_version >= 1),
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                last_event_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                FOREIGN KEY(last_event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS positions_projection (
                entity_id TEXT PRIMARY KEY,
                entity_version INTEGER NOT NULL CHECK(entity_version >= 1),
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                last_event_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                FOREIGN KEY(last_event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS risk_locks_projection (
                entity_id TEXT PRIMARY KEY,
                entity_version INTEGER NOT NULL CHECK(entity_version >= 1),
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                last_event_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                FOREIGN KEY(last_event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS model_deployments_projection (
                entity_id TEXT PRIMARY KEY,
                entity_version INTEGER NOT NULL CHECK(entity_version >= 1),
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                last_event_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                FOREIGN KEY(last_event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS position_executors_projection (
                entity_id TEXT PRIMARY KEY,
                entity_version INTEGER NOT NULL CHECK(entity_version >= 1),
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                last_event_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                FOREIGN KEY(last_event_id) REFERENCES events(event_id)
            );
            """
        )
        self.connection.commit()

    def _append(
        self,
        event_type: str,
        envelope: EventEnvelope,
        payload: Dict[str, Any],
    ) -> AppendResult:
        if not event_type:
            raise LedgerIntegrityError("event_type cannot be empty")
        envelope.validate(payload)
        existing = self.connection.execute(
            """
            SELECT sequence, event_type, event_hash, ledger_hash
            FROM events WHERE event_id = ?
            """,
            (envelope.event_id,),
        ).fetchone()
        if existing:
            if (
                existing["event_hash"] != envelope.event_hash
                or existing["event_type"] != event_type
            ):
                raise LedgerConflictError("event_id was reused with different content")
            return AppendResult(existing["sequence"], False, existing["ledger_hash"])

        previous = self.connection.execute(
            "SELECT ledger_hash FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["ledger_hash"] if previous else _GENESIS_HASH
        ledger_hash = business_hash(
            {
                "previous_ledger_hash": previous_hash,
                "event_hash": envelope.event_hash,
                "event_type": event_type,
            }
        )
        cursor = self.connection.execute(
            """
            INSERT INTO events (
                event_id, event_type, schema_version, trace_id, correlation_id,
                causation_id, run_id, event_time, available_at, ingested_at,
                recorded_at, source, ordering_exception_reason, payload_json,
                payload_hash, event_hash, previous_ledger_hash, ledger_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                envelope.event_id,
                event_type,
                envelope.schema_version,
                envelope.trace_id,
                envelope.correlation_id,
                envelope.causation_id,
                envelope.run_id,
                utc_datetime(envelope.event_time),
                utc_datetime(envelope.available_at),
                utc_datetime(envelope.ingested_at),
                utc_datetime(envelope.recorded_at),
                envelope.source,
                envelope.ordering_exception_reason,
                canonical_json(payload),
                envelope.payload_hash,
                envelope.event_hash,
                previous_hash,
                ledger_hash,
            ),
        )
        self._apply_projection(
            event_type,
            event_id=envelope.event_id,
            event_time=utc_datetime(envelope.event_time),
            payload=payload,
        )
        return AppendResult(int(cursor.lastrowid), True, ledger_hash)

    def append(
        self,
        event_type: str,
        envelope: EventEnvelope,
        payload: Dict[str, Any],
    ) -> AppendResult:
        with self.connection:
            return self._append(event_type, envelope, payload)

    def enqueue_outbox(
        self,
        *,
        event_type: str,
        envelope: EventEnvelope,
        payload: Dict[str, Any],
        outbox_id: str,
        intent_id: str,
        command: Dict[str, Any],
    ) -> AppendResult:
        """Atomically persist an intent event and a not-yet-sent command."""

        with self.connection:
            result = self._append(event_type, envelope, payload)
            command_json = canonical_json(command)
            command_hash = business_hash(command)
            existing = self.connection.execute(
                "SELECT command_hash, source_event_id FROM outbox WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()
            if existing:
                if (
                    existing["command_hash"] != command_hash
                    or existing["source_event_id"] != envelope.event_id
                ):
                    raise LedgerConflictError("intent_id was reused for a different command")
                return result
            now = utc_datetime(envelope.recorded_at)
            self.connection.execute(
                """
                INSERT INTO outbox (
                    outbox_id, intent_id, source_event_id, command_json,
                    command_hash, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)
                """,
                (
                    outbox_id,
                    intent_id,
                    envelope.event_id,
                    command_json,
                    command_hash,
                    now,
                    now,
                ),
            )
            return result

    def _apply_projection(
        self,
        event_type: str,
        *,
        event_id: str,
        event_time: str,
        payload: Dict[str, Any],
    ) -> None:
        if event_type == "OperatingCostRecorded":
            amount = Decimal(canonical_decimal(payload["amount_usdt"]))
            if amount < 0:
                raise LedgerIntegrityError("operating cost cannot be negative")
            self.connection.execute(
                """
                INSERT INTO operating_costs_projection
                (event_id, category, amount_usdt, occurred_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event_id,
                    payload["category"],
                    canonical_decimal(amount),
                    event_time,
                ),
            )
        elif event_type == "ExternalCashFlowRecorded":
            amount = canonical_decimal(payload["signed_amount_usdt"])
            self.connection.execute(
                """
                INSERT INTO external_cash_flows_projection
                (event_id, flow_type, signed_amount_usdt, occurred_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event_id,
                    payload["flow_type"],
                    amount,
                    event_time,
                ),
            )
        elif event_type in _VERSIONED_PROJECTIONS:
            self._apply_versioned_projection(
                event_type=event_type,
                event_id=event_id,
                event_time=event_time,
                payload=payload,
            )

    def _apply_versioned_projection(
        self,
        *,
        event_type: str,
        event_id: str,
        event_time: str,
        payload: Dict[str, Any],
    ) -> None:
        table, entity_id_field, required_fields = _VERSIONED_PROJECTIONS[event_type]
        required = {
            "entity_version",
            "state",
            entity_id_field,
            *required_fields,
        }
        missing = sorted(required - set(payload))
        if missing:
            raise LedgerIntegrityError(
                f"{event_type} projection payload missing fields: {missing}"
            )
        entity_id = payload[entity_id_field]
        version = payload["entity_version"]
        state = payload["state"]
        if not isinstance(entity_id, str) or not entity_id:
            raise LedgerIntegrityError("projection entity id must be a non-empty string")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise LedgerIntegrityError("projection entity_version must be a positive integer")
        if not isinstance(state, str) or not state:
            raise LedgerIntegrityError("projection state must be a non-empty string")
        self._validate_projection_semantics(event_type, state, payload)
        payload_json = canonical_json(payload)
        projection_hash = business_hash(payload)
        existing = self.connection.execute(
            f"""
            SELECT entity_version, projection_hash
            FROM {table} WHERE entity_id = ?
            """,
            (entity_id,),
        ).fetchone()
        if existing:
            if version < existing["entity_version"]:
                return
            if version == existing["entity_version"]:
                if projection_hash != existing["projection_hash"]:
                    raise LedgerConflictError(
                        "entity version was reused with different projection content"
                    )
                return
            self.connection.execute(
                f"""
                UPDATE {table}
                SET entity_version = ?, state = ?, payload_json = ?,
                    projection_hash = ?, last_event_id = ?, event_time = ?
                WHERE entity_id = ?
                """,
                (
                    version,
                    state,
                    payload_json,
                    projection_hash,
                    event_id,
                    event_time,
                    entity_id,
                ),
            )
            return
        self.connection.execute(
            f"""
            INSERT INTO {table} (
                entity_id, entity_version, state, payload_json,
                projection_hash, last_event_id, event_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                version,
                state,
                payload_json,
                projection_hash,
                event_id,
                event_time,
            ),
        )

    @staticmethod
    def _validate_projection_semantics(
        event_type: str,
        state: str,
        payload: Dict[str, Any],
    ) -> None:
        allowed_states = {
            "ExecutionIntentStateRecorded": _INTENT_STATES,
            "ChildOrderAttemptStateRecorded": _ATTEMPT_STATES,
            "OrderStateRecorded": _ORDER_STATES,
            "PositionStateRecorded": {"OBSERVED"},
            "RiskLockStateRecorded": _RISK_LOCK_STATES,
            "DeploymentStateRecorded": _DEPLOYMENT_STATES,
            "PositionExecutorStateRecorded": _EXECUTOR_STATES,
        }[event_type]
        if state not in allowed_states:
            raise LedgerIntegrityError(
                f"{event_type} has unsupported projection state {state}"
            )
        string_fields = {
            "ExecutionIntentStateRecorded": (
                "intent_id",
                "risk_decision_id",
                "target_id",
                "instrument_id",
                "intent_hash",
            ),
            "ChildOrderAttemptStateRecorded": (
                "attempt_id",
                "intent_id",
                "client_order_id",
                "attempt_hash",
            ),
            "OrderStateRecorded": (
                "order_id",
                "attempt_id",
                "intent_id",
                "instrument_id",
                "client_order_id",
            ),
            "PositionStateRecorded": (
                "position_id",
                "account_id",
                "instrument_id",
                "instrument_metadata_hash",
            ),
            "RiskLockStateRecorded": (
                "lock_id",
                "lock_type",
                "scope",
                "scope_id",
            ),
            "DeploymentStateRecorded": (
                "deployment_line_id",
                "stage",
                "record_hash",
            ),
            "PositionExecutorStateRecorded": (
                "executor_id",
                "account_id",
                "economic_asset",
            ),
        }[event_type]
        if any(
            not isinstance(payload[field_name], str) or not payload[field_name]
            for field_name in string_fields
        ):
            raise LedgerIntegrityError(
                f"{event_type} identity fields must be non-empty strings"
            )
        for hash_field in (
            "intent_hash",
            "attempt_hash",
            "instrument_metadata_hash",
            "record_hash",
        ):
            if hash_field in payload:
                digest = payload[hash_field]
                if len(digest) != 64 or any(
                    character not in "0123456789abcdef"
                    for character in digest
                ):
                    raise LedgerIntegrityError(
                        f"{hash_field} must be a lowercase SHA-256 digest"
                    )

        if event_type == "OrderStateRecorded":
            requested = Decimal(canonical_decimal(payload["requested_quantity"]))
            filled = Decimal(
                canonical_decimal(payload["cumulative_filled_quantity"])
            )
            if requested <= 0 or filled < 0 or filled > requested:
                raise LedgerIntegrityError(
                    "order projection quantities violate fill invariants"
                )
            if state == "FILLED" and filled != requested:
                raise LedgerIntegrityError(
                    "FILLED order projection must equal requested quantity"
                )
            if state == "PARTIALLY_FILLED" and not Decimal("0") < filled < requested:
                raise LedgerIntegrityError(
                    "PARTIALLY_FILLED projection requires a strict partial fill"
                )
        elif event_type == "PositionStateRecorded":
            Decimal(canonical_decimal(payload["signed_quantity"]))
        elif event_type == "ChildOrderAttemptStateRecorded":
            attempt_no = payload["attempt_no"]
            if (
                isinstance(attempt_no, bool)
                or not isinstance(attempt_no, int)
                or attempt_no < 1
            ):
                raise LedgerIntegrityError("attempt_no must be a positive integer")
        elif event_type == "RiskLockStateRecorded":
            if payload["lock_type"] not in _RISK_LOCK_TYPES:
                raise LedgerIntegrityError("risk lock type is not frozen in V1")
            if payload["scope"] not in _RISK_LOCK_SCOPES:
                raise LedgerIntegrityError("risk lock scope is not frozen in V1")
        elif event_type == "DeploymentStateRecorded":
            stage = payload["stage"]
            if stage not in _DEPLOYMENT_MULTIPLIERS:
                raise LedgerIntegrityError("deployment stage has no live multiplier")
            multiplier = Decimal(
                canonical_decimal(payload["authoritative_stage_multiplier"])
            )
            if multiplier != _DEPLOYMENT_MULTIPLIERS[stage]:
                raise LedgerIntegrityError(
                    "deployment projection multiplier is not authoritative"
                )
        elif event_type == "PositionExecutorStateRecorded":
            if payload["economic_asset"] != "ETH":
                raise LedgerIntegrityError("V1 executor projection is restricted to ETH")
            for optional_id in (
                "current_target_id_or_null",
                "active_intent_id_or_null",
            ):
                value = payload[optional_id]
                if value is not None and (
                    not isinstance(value, str) or not value
                ):
                    raise LedgerIntegrityError(
                        f"{optional_id} must be null or a non-empty string"
                    )

    def pending_outbox(self) -> Iterator[sqlite3.Row]:
        return iter(
            self.connection.execute(
                """
                SELECT * FROM outbox
                WHERE status IN ('PENDING', 'UNKNOWN')
                ORDER BY created_at, outbox_id
                """
            ).fetchall()
        )

    def projection_totals(self) -> Tuple[Decimal, Decimal]:
        costs = sum(
            (
                Decimal(row[0])
                for row in self.connection.execute(
                    "SELECT amount_usdt FROM operating_costs_projection"
                )
            ),
            Decimal("0"),
        )
        cash_flows = sum(
            (
                Decimal(row[0])
                for row in self.connection.execute(
                    "SELECT signed_amount_usdt FROM external_cash_flows_projection"
                )
            ),
            Decimal("0"),
        )
        return costs, cash_flows

    def rebuild_projections(self) -> None:
        """Recreate every derived state only from immutable event facts."""

        with self.connection:
            self.connection.execute("DELETE FROM operating_costs_projection")
            self.connection.execute("DELETE FROM external_cash_flows_projection")
            for table in _VERSIONED_PROJECTION_TABLES:
                self.connection.execute(f"DELETE FROM {table}")
            rows = self.connection.execute(
                """
                SELECT event_id, event_type, event_time, payload_json
                FROM events ORDER BY sequence
                """
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload_json"])
                self._apply_projection(
                    row["event_type"],
                    event_id=row["event_id"],
                    event_time=row["event_time"],
                    payload=payload,
                )

    def projection_snapshot(self) -> Dict[str, Any]:
        """Return canonical projection content suitable for Golden replay hashing."""

        costs = [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT event_id, category, amount_usdt, occurred_at
                FROM operating_costs_projection ORDER BY event_id
                """
            ).fetchall()
        ]
        cash_flows = [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT event_id, flow_type, signed_amount_usdt, occurred_at
                FROM external_cash_flows_projection ORDER BY event_id
                """
            ).fetchall()
        ]
        snapshot: Dict[str, Any] = {
            "operating_costs_projection": costs,
            "external_cash_flows_projection": cash_flows,
        }
        for table in _VERSIONED_PROJECTION_TABLES:
            snapshot[table] = [
                {
                    "entity_id": row["entity_id"],
                    "entity_version": row["entity_version"],
                    "state": row["state"],
                    "payload": json.loads(row["payload_json"]),
                    "projection_hash": row["projection_hash"],
                    "last_event_id": row["last_event_id"],
                    "event_time": row["event_time"],
                }
                for row in self.connection.execute(
                    f"""
                    SELECT entity_id, entity_version, state, payload_json,
                           projection_hash, last_event_id, event_time
                    FROM {table} ORDER BY entity_id
                    """
                ).fetchall()
            ]
        return snapshot

    def projection_hash(self) -> str:
        self.verify_projection_integrity()
        return business_hash(self.projection_snapshot())

    def verify_projection_integrity(self) -> None:
        """Detect derived-state tampering before it can be treated as current truth."""

        for event_type, (
            table,
            entity_id_field,
            _,
        ) in _VERSIONED_PROJECTIONS.items():
            rows = self.connection.execute(
                f"""
                SELECT entity_id, entity_version, state, payload_json,
                       projection_hash, last_event_id, event_time
                FROM {table}
                """
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload_json"])
                if business_hash(payload) != row["projection_hash"]:
                    raise LedgerIntegrityError(
                        f"projection hash mismatch in {table}"
                    )
                if (
                    payload.get(entity_id_field) != row["entity_id"]
                    or payload.get("entity_version") != row["entity_version"]
                    or payload.get("state") != row["state"]
                ):
                    raise LedgerIntegrityError(
                        f"projection columns disagree with payload in {table}"
                    )
                source = self.connection.execute(
                    """
                    SELECT event_type, event_time, payload_json
                    FROM events WHERE event_id = ?
                    """,
                    (row["last_event_id"],),
                ).fetchone()
                if source is None:
                    raise LedgerIntegrityError(
                        f"projection source event is missing in {table}"
                    )
                if (
                    source["event_type"] != event_type
                    or source["event_time"] != row["event_time"]
                    or source["payload_json"] != row["payload_json"]
                ):
                    raise LedgerIntegrityError(
                        f"projection does not match its source event in {table}"
                    )

    def verify_integrity(self) -> str:
        previous = _GENESIS_HASH
        last = previous
        rows = self.connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        for row in rows:
            payload = json.loads(row["payload_json"])
            if business_hash(payload) != row["payload_hash"]:
                raise LedgerIntegrityError(
                    f"payload hash mismatch at sequence {row['sequence']}"
                )
            body = {
                "schema_version": row["schema_version"],
                "event_id": row["event_id"],
                "trace_id": row["trace_id"],
                "correlation_id": row["correlation_id"],
                "causation_id": row["causation_id"],
                "run_id": row["run_id"],
                "event_time": row["event_time"],
                "available_at": row["available_at"],
                "ingested_at": row["ingested_at"],
                "recorded_at": row["recorded_at"],
                "source": row["source"],
                "payload_hash": row["payload_hash"],
                "ordering_exception_reason": row["ordering_exception_reason"],
            }
            if business_hash(body) != row["event_hash"]:
                raise LedgerIntegrityError(
                    f"event hash mismatch at sequence {row['sequence']}"
                )
            if row["previous_ledger_hash"] != previous:
                raise LedgerIntegrityError(f"broken chain at sequence {row['sequence']}")
            expected = business_hash(
                {
                    "previous_ledger_hash": previous,
                    "event_hash": row["event_hash"],
                    "event_type": row["event_type"],
                }
            )
            if expected != row["ledger_hash"]:
                raise LedgerIntegrityError(
                    f"ledger hash mismatch at sequence {row['sequence']}"
                )
            previous = expected
            last = expected
        return last
