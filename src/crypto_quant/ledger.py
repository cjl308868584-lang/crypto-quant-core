"""SQLite WAL append-only ledger, outbox, and minimal projections."""

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple

from .canonical import business_hash, canonical_decimal, canonical_json, utc_datetime
from .contracts import EventEnvelope
from .errors import LedgerConflictError, LedgerIntegrityError

_GENESIS_HASH = "0" * 64


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
        self._apply_projection(event_type, envelope, payload)
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
        envelope: EventEnvelope,
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
                    envelope.event_id,
                    payload["category"],
                    canonical_decimal(amount),
                    utc_datetime(envelope.event_time),
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
                    envelope.event_id,
                    payload["flow_type"],
                    amount,
                    utc_datetime(envelope.event_time),
                ),
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
        """Recreate derived economic state only from immutable event facts."""

        with self.connection:
            self.connection.execute("DELETE FROM operating_costs_projection")
            self.connection.execute("DELETE FROM external_cash_flows_projection")
            rows = self.connection.execute(
                """
                SELECT event_id, event_type, event_time, payload_json
                FROM events ORDER BY sequence
                """
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload_json"])
                if row["event_type"] == "OperatingCostRecorded":
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
                            row["event_id"],
                            payload["category"],
                            canonical_decimal(amount),
                            row["event_time"],
                        ),
                    )
                elif row["event_type"] == "ExternalCashFlowRecorded":
                    self.connection.execute(
                        """
                        INSERT INTO external_cash_flows_projection
                        (event_id, flow_type, signed_amount_usdt, occurred_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            row["event_id"],
                            payload["flow_type"],
                            canonical_decimal(payload["signed_amount_usdt"]),
                            row["event_time"],
                        ),
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
