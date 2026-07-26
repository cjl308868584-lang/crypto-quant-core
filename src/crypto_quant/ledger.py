"""SQLite WAL append-only ledger, outbox, and minimal projections."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Tuple

from .canonical import business_hash, canonical_decimal, canonical_json, utc_datetime
from .contracts import EventEnvelope
from .economics import economic_snapshot_hash
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
    "BalanceStateRecorded": (
        "balances_projection",
        "balance_id",
        (
            "account_id",
            "asset",
            "total_balance",
            "available_balance",
            "locked_balance",
            "borrowed_balance",
            "interest_accrued",
            "exchange_snapshot_time",
            "source_snapshot_hash",
        ),
    ),
    "ProtectiveOrderStateRecorded": (
        "protective_orders_projection",
        "protective_order_id",
        (
            "instrument_id",
            "position_id",
            "risk_decision_id",
            "execution_intent_id",
            "attempt_id",
            "local_order_id",
            "role",
            "side",
            "trigger_price",
            "limit_price_or_null",
            "covered_quantity",
            "reduce_only_or_spot_sell",
            "venue_order_id_or_null",
            "replacement_of_or_null",
            "unprotected_window_started_at_or_null",
            "replacement_deadline_at_or_null",
            "effective_at_or_null",
            "risk_policy_id",
            "risk_policy_hash",
            "policy_version",
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
_PROTECTIVE_ORDER_STATES = {
    "PLANNED",
    "SUBMITTING",
    "ACTIVE",
    "REPLACE_PENDING",
    "UNKNOWN",
    "CANCELED",
    "FAILED",
    "TRIGGERED",
    "EXPIRED",
}
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
_OPERATING_COST_CATEGORIES = {
    "INFRASTRUCTURE",
    "DATA",
    "ALERTING",
    "AI_INFERENCE",
    "MODEL_TRAINING",
    "MONITORING_AND_AUDIT",
}
_EXTERNAL_CASH_FLOW_TYPES = {
    "DEPOSIT",
    "WITHDRAWAL",
    "INTERNAL_TRANSFER",
}
_ALLOCATION_SCOPES = {
    "SHARED",
    "BASELINE_ONLY",
    "AI_ENHANCED",
}
_ECONOMIC_LEDGERS = {
    "BASELINE_LEDGER",
    "AI_LEDGER",
    "ROUTE_RUNTIME",
}
_ECONOMIC_SCOPE_FIELDS = {
    "evaluation_ledger",
    "release_route",
    "direction",
    "venue",
    "recipe_release_id",
    "recipe_release_hash",
    "deployment_line_id",
    "deployment_line_hash",
}


def _require_sha256(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise LedgerIntegrityError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


def _require_utc_datetime(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise LedgerIntegrityError(f"{field_name} must be a UTC date-time")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LedgerIntegrityError(f"{field_name} is not a valid date-time") from exc
    if parsed.utcoffset() is None:
        raise LedgerIntegrityError(f"{field_name} must be timezone-aware")


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
                flow_id TEXT NOT NULL UNIQUE,
                account_id TEXT NOT NULL,
                flow_type TEXT NOT NULL,
                signed_amount_usdt TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY(event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS allocated_costs_projection (
                cost_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                evaluation_ledger TEXT NOT NULL,
                release_route TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                source_event_id TEXT NOT NULL UNIQUE,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY(source_event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS funding_cashflows_projection (
                funding_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                instrument_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                source_event_id TEXT NOT NULL UNIQUE,
                settled_at TEXT NOT NULL,
                FOREIGN KEY(source_event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS equity_snapshots_projection (
                equity_snapshot_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                evaluation_ledger TEXT NOT NULL,
                release_route TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                source_event_id TEXT NOT NULL UNIQUE,
                as_of TEXT NOT NULL,
                FOREIGN KEY(source_event_id) REFERENCES events(event_id)
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

            CREATE TABLE IF NOT EXISTS balances_projection (
                entity_id TEXT PRIMARY KEY,
                entity_version INTEGER NOT NULL CHECK(entity_version >= 1),
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                last_event_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                FOREIGN KEY(last_event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS protective_orders_projection (
                entity_id TEXT PRIMARY KEY,
                entity_version INTEGER NOT NULL CHECK(entity_version >= 1),
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                last_event_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                FOREIGN KEY(last_event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS fills_projection (
                fill_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                market_scope TEXT NOT NULL,
                exchange_trade_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                source_event_id TEXT NOT NULL UNIQUE,
                exchange_event_time TEXT NOT NULL,
                UNIQUE(account_id, market_scope, exchange_trade_id),
                FOREIGN KEY(source_event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                covered_event_sequence INTEGER NOT NULL,
                covered_ledger_hash TEXT NOT NULL,
                covered_projection_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                checkpoint_hash TEXT NOT NULL,
                source_event_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY(source_event_id) REFERENCES events(event_id)
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
            if payload.get("category") not in _OPERATING_COST_CATEGORIES:
                raise LedgerIntegrityError(
                    "operating cost category is not recognized"
                )
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
            required = {
                "flow_id",
                "account_id",
                "flow_type",
                "signed_amount_usdt",
            }
            missing = sorted(required - set(payload))
            if missing:
                raise LedgerIntegrityError(
                    f"ExternalCashFlowRecorded missing fields: {missing}"
                )
            if payload["flow_type"] not in _EXTERNAL_CASH_FLOW_TYPES:
                raise LedgerIntegrityError(
                    "external cash flow type is not recognized"
                )
            amount = Decimal(
                canonical_decimal(payload["signed_amount_usdt"])
            )
            if payload["flow_type"] == "DEPOSIT" and amount <= 0:
                raise LedgerIntegrityError("deposit must be positive")
            if payload["flow_type"] == "WITHDRAWAL" and amount >= 0:
                raise LedgerIntegrityError("withdrawal must be negative")
            self.connection.execute(
                """
                INSERT INTO external_cash_flows_projection
                (event_id, flow_id, account_id, flow_type,
                 signed_amount_usdt, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    payload["flow_id"],
                    payload["account_id"],
                    payload["flow_type"],
                    canonical_decimal(amount),
                    event_time,
                ),
            )
        elif event_type in (
            "AllocatedCostRecorded",
            "FundingCashFlowRecorded",
            "EquitySnapshotRecorded",
        ):
            self._apply_economic_fact_projection(
                event_type=event_type,
                event_id=event_id,
                event_time=event_time,
                payload=payload,
            )
        elif event_type == "FillRecorded":
            self._apply_fill_projection(
                event_id=event_id,
                event_time=event_time,
                payload=payload,
            )
        elif event_type == "CheckpointRecorded":
            self._apply_checkpoint(
                event_id=event_id,
                event_time=event_time,
                payload=payload,
            )
        elif event_type in _VERSIONED_PROJECTIONS:
            self._apply_versioned_projection(
                event_type=event_type,
                event_id=event_id,
                event_time=event_time,
                payload=payload,
            )

    def _apply_economic_fact_projection(
        self,
        *,
        event_type: str,
        event_id: str,
        event_time: str,
        payload: Dict[str, Any],
    ) -> None:
        if event_type == "AllocatedCostRecorded":
            required = {
                "cost_id",
                "account_id",
                "evaluation_ledger",
                "release_route",
                "category",
                "amount_usdt",
                "allocation_scope",
                "allocation_policy_hash",
                "occurred_at",
                *_ECONOMIC_SCOPE_FIELDS,
            }
            missing = sorted(required - set(payload))
            if missing:
                raise LedgerIntegrityError(
                    f"AllocatedCostRecorded missing fields: {missing}"
                )
            amount = Decimal(canonical_decimal(payload["amount_usdt"]))
            if amount < 0:
                raise LedgerIntegrityError("allocated cost cannot be negative")
            if payload["category"] not in _OPERATING_COST_CATEGORIES:
                raise LedgerIntegrityError("allocated cost category is invalid")
            if payload["allocation_scope"] not in _ALLOCATION_SCOPES:
                raise LedgerIntegrityError("allocated cost scope is invalid")
            self._validate_economic_scope(payload, event_type)
            if (
                payload["release_route"] == "BASELINE_ONLY"
                and payload["allocation_scope"] == "AI_ENHANCED"
            ) or (
                payload["release_route"] == "AI_ENHANCED"
                and payload["allocation_scope"] == "BASELINE_ONLY"
            ):
                raise LedgerIntegrityError(
                    "allocated cost scope conflicts with release route"
                )
            _require_sha256(
                payload["allocation_policy_hash"],
                "allocation_policy_hash",
            )
            _require_utc_datetime(payload["occurred_at"], "occurred_at")
            if payload["occurred_at"] != event_time:
                raise LedgerIntegrityError(
                    "allocated cost time must equal event time"
                )
            table = "allocated_costs_projection"
            id_field = "cost_id"
            time_field = "occurred_at"
            columns = (
                payload["account_id"],
                payload["evaluation_ledger"],
                payload["release_route"],
            )
        elif event_type == "FundingCashFlowRecorded":
            required = {
                "funding_id",
                "account_id",
                "instrument_id",
                "signed_amount_usdt",
                "position_quantity",
                "funding_rate",
                "mark_price",
                "settled_at",
                "raw_payload_hash",
                *_ECONOMIC_SCOPE_FIELDS,
            }
            missing = sorted(required - set(payload))
            if missing:
                raise LedgerIntegrityError(
                    f"FundingCashFlowRecorded missing fields: {missing}"
                )
            mark = Decimal(canonical_decimal(payload["mark_price"]))
            Decimal(canonical_decimal(payload["signed_amount_usdt"]))
            position = Decimal(
                canonical_decimal(payload["position_quantity"])
            )
            Decimal(canonical_decimal(payload["funding_rate"]))
            if mark <= 0 or position == 0:
                raise LedgerIntegrityError(
                    "funding requires positive mark and actual position"
                )
            _require_sha256(payload["raw_payload_hash"], "raw_payload_hash")
            self._validate_economic_scope(payload, event_type)
            _require_utc_datetime(payload["settled_at"], "settled_at")
            if payload["settled_at"] != event_time:
                raise LedgerIntegrityError(
                    "funding settlement time must equal event time"
                )
            table = "funding_cashflows_projection"
            id_field = "funding_id"
            time_field = "settled_at"
            columns = (
                payload["account_id"],
                payload["instrument_id"],
            )
        else:
            required = {
                "equity_snapshot_id",
                "account_id",
                "evaluation_ledger",
                "release_route",
                "marked_equity_usdt",
                "liquidation_equity_usdt",
                "spot_notional_usdt",
                "perp_notional_usdt",
                "active_order_risk_increasing_notional_usdt",
                "active_order_unknown_notional_usdt",
                "expected_exit_fee_accrued_usdt",
                "conservative_close_verified",
                "is_utc_day_start",
                "position_cost_bases",
                "as_of",
                "source_snapshot_hash",
                *_ECONOMIC_SCOPE_FIELDS,
            }
            missing = sorted(required - set(payload))
            if missing:
                raise LedgerIntegrityError(
                    f"EquitySnapshotRecorded missing fields: {missing}"
                )
            for name in (
                "marked_equity_usdt",
                "liquidation_equity_usdt",
                "spot_notional_usdt",
                "perp_notional_usdt",
                "active_order_risk_increasing_notional_usdt",
                "active_order_unknown_notional_usdt",
                "expected_exit_fee_accrued_usdt",
            ):
                if Decimal(canonical_decimal(payload[name])) < 0:
                    raise LedgerIntegrityError(
                        f"equity snapshot {name} cannot be negative"
                    )
            self._validate_economic_scope(payload, event_type)
            if payload["conservative_close_verified"] is not True:
                raise LedgerIntegrityError(
                    "equity snapshot executable close is unverified"
                )
            if not isinstance(payload["is_utc_day_start"], bool):
                raise LedgerIntegrityError("is_utc_day_start must be boolean")
            if not isinstance(payload["position_cost_bases"], list):
                raise LedgerIntegrityError(
                    "position_cost_bases must be an array"
                )
            instrument_ids = [
                position.get("instrument_id")
                for position in payload["position_cost_bases"]
                if isinstance(position, Mapping)
            ]
            if len(instrument_ids) != len(set(instrument_ids)):
                raise LedgerIntegrityError(
                    "position cost basis instruments must be unique"
                )
            for position in payload["position_cost_bases"]:
                if not isinstance(position, Mapping):
                    raise LedgerIntegrityError(
                        "position cost basis must be an object"
                    )
                for name in (
                    "instrument_id",
                    "signed_quantity",
                    "moving_average_entry_price",
                    "contract_multiplier",
                ):
                    if name not in position:
                        raise LedgerIntegrityError(
                            f"position cost basis missing {name}"
                        )
                quantity = Decimal(
                    canonical_decimal(position["signed_quantity"])
                )
                average = Decimal(
                    canonical_decimal(
                        position["moving_average_entry_price"]
                    )
                )
                multiplier = Decimal(
                    canonical_decimal(position["contract_multiplier"])
                )
                if multiplier <= 0 or average < 0:
                    raise LedgerIntegrityError(
                        "position cost basis values are invalid"
                    )
                if (quantity == 0) != (average == 0):
                    raise LedgerIntegrityError(
                        "zero position and entry price disagree"
                    )
            _require_sha256(
                payload["source_snapshot_hash"],
                "source_snapshot_hash",
            )
            _require_utc_datetime(payload["as_of"], "as_of")
            if payload["as_of"] != event_time:
                raise LedgerIntegrityError(
                    "equity snapshot time must equal event time"
                )
            table = "equity_snapshots_projection"
            id_field = "equity_snapshot_id"
            time_field = "as_of"
            columns = (
                payload["account_id"],
                payload["evaluation_ledger"],
                payload["release_route"],
            )

        for name in (id_field, "account_id"):
            if not isinstance(payload[name], str) or not payload[name]:
                raise LedgerIntegrityError(
                    f"{event_type} {name} must be non-empty"
                )
        payload_json = canonical_json(payload)
        projection_hash = business_hash(payload)
        if table == "allocated_costs_projection":
            self.connection.execute(
                """
                INSERT INTO allocated_costs_projection (
                    cost_id, account_id, evaluation_ledger, release_route,
                    payload_json, projection_hash, source_event_id, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload[id_field],
                    *columns,
                    payload_json,
                    projection_hash,
                    event_id,
                    payload[time_field],
                ),
            )

        elif table == "funding_cashflows_projection":
            self.connection.execute(
                """
                INSERT INTO funding_cashflows_projection (
                    funding_id, account_id, instrument_id, payload_json,
                    projection_hash, source_event_id, settled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload[id_field],
                    *columns,
                    payload_json,
                    projection_hash,
                    event_id,
                    payload[time_field],
                ),
            )
        else:
            self.connection.execute(
                """
                INSERT INTO equity_snapshots_projection (
                    equity_snapshot_id, account_id, evaluation_ledger,
                    release_route, payload_json, projection_hash,
                    source_event_id, as_of
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload[id_field],
                    *columns,
                    payload_json,
                    projection_hash,
                    event_id,
                    payload[time_field],
                ),
            )

    @staticmethod
    def _validate_economic_scope(
        payload: Mapping[str, Any],
        event_type: str,
    ) -> None:
        missing = sorted(_ECONOMIC_SCOPE_FIELDS - set(payload))
        if missing:
            raise LedgerIntegrityError(
                f"{event_type} economic scope missing fields: {missing}"
            )
        if payload["evaluation_ledger"] not in _ECONOMIC_LEDGERS:
            raise LedgerIntegrityError(
                f"{event_type} economic ledger is invalid"
            )
        if payload["release_route"] not in (
            "BASELINE_ONLY",
            "AI_ENHANCED",
        ):
            raise LedgerIntegrityError(
                f"{event_type} release route is invalid"
            )
        if (
            payload["evaluation_ledger"] == "AI_LEDGER"
            and payload["release_route"] != "AI_ENHANCED"
        ):
            raise LedgerIntegrityError(
                f"{event_type} ledger and release route disagree"
            )
        if payload["direction"] not in ("LONG", "SHORT"):
            raise LedgerIntegrityError(
                f"{event_type} direction is invalid"
            )
        if payload["venue"] not in (
            "BINANCE_SPOT",
            "BINANCE_USDT_PERP",
        ):
            raise LedgerIntegrityError(f"{event_type} venue is invalid")
        if (
            payload["direction"],
            payload["venue"],
        ) not in {
            ("LONG", "BINANCE_SPOT"),
            ("SHORT", "BINANCE_USDT_PERP"),
        }:
            raise LedgerIntegrityError(
                f"{event_type} direction and venue disagree"
            )
        for name in ("recipe_release_id", "deployment_line_id"):
            if not isinstance(payload[name], str) or not payload[name]:
                raise LedgerIntegrityError(
                    f"{event_type} {name} must be non-empty"
                )
        for name in (
            "recipe_release_hash",
            "deployment_line_hash",
        ):
            _require_sha256(payload[name], name)

    def _apply_fill_projection(
        self,
        *,
        event_id: str,
        event_time: str,
        payload: Dict[str, Any],
    ) -> None:
        required = {
            "fill_id",
            "account_id",
            "market_scope",
            "exchange_trade_id",
            "local_order_id",
            "venue_order_id",
            "instrument_id",
            "side",
            "quantity",
            "price",
            "contract_multiplier",
            "decision_reference_price",
            "liquidity_role",
            "fee_amount",
            "fee_asset",
            "fee_value_usdt",
            "fee_fx_rate_id_or_null",
            "implementation_shortfall_usdt",
            "exchange_event_time",
            "raw_payload_hash",
            *_ECONOMIC_SCOPE_FIELDS,
        }
        missing = sorted(required - set(payload))
        if missing:
            raise LedgerIntegrityError(
                f"FillRecorded projection payload missing fields: {missing}"
            )
        for field_name in (
            "fill_id",
            "account_id",
            "market_scope",
            "exchange_trade_id",
            "local_order_id",
            "venue_order_id",
            "instrument_id",
            "fee_asset",
        ):
            value = payload[field_name]
            if not isinstance(value, str) or not value:
                raise LedgerIntegrityError(
                    f"FillRecorded {field_name} must be a non-empty string"
                )
        if payload["side"] not in ("BUY", "SELL"):
            raise LedgerIntegrityError("FillRecorded side must be BUY or SELL")
        if payload["liquidity_role"] not in ("MAKER", "TAKER"):
            raise LedgerIntegrityError("FillRecorded liquidity role is invalid")
        quantity = Decimal(canonical_decimal(payload["quantity"]))
        price = Decimal(canonical_decimal(payload["price"]))
        multiplier = Decimal(
            canonical_decimal(payload["contract_multiplier"])
        )
        reference = Decimal(
            canonical_decimal(payload["decision_reference_price"])
        )
        fee_amount = Decimal(canonical_decimal(payload["fee_amount"]))
        fee_value = Decimal(canonical_decimal(payload["fee_value_usdt"]))
        Decimal(canonical_decimal(payload["implementation_shortfall_usdt"]))
        if (
            quantity <= 0
            or price <= 0
            or multiplier <= 0
            or reference <= 0
        ):
            raise LedgerIntegrityError(
                "FillRecorded quantity and prices must be positive"
            )
        if fee_amount < 0 or fee_value < 0:
            raise LedgerIntegrityError("FillRecorded fees cannot be negative")
        fee_fx = payload["fee_fx_rate_id_or_null"]
        if fee_fx is not None and (
            not isinstance(fee_fx, str) or not fee_fx
        ):
            raise LedgerIntegrityError(
                "fee_fx_rate_id_or_null must be null or a non-empty string"
            )
        _require_utc_datetime(
            payload["exchange_event_time"],
            "exchange_event_time",
        )
        if payload["exchange_event_time"] != event_time:
            raise LedgerIntegrityError(
                "fill exchange time must equal event time"
            )
        self._validate_economic_scope(payload, "FillRecorded")
        _require_sha256(payload["raw_payload_hash"], "raw_payload_hash")
        payload_json = canonical_json(payload)
        projection_hash = business_hash(payload)
        existing_fill_id = self.connection.execute(
            """
            SELECT projection_hash FROM fills_projection WHERE fill_id = ?
            """,
            (payload["fill_id"],),
        ).fetchone()
        if existing_fill_id:
            if existing_fill_id["projection_hash"] != projection_hash:
                raise LedgerConflictError(
                    "fill ID was reused with different Fill content"
                )
            return
        existing = self.connection.execute(
            """
            SELECT projection_hash FROM fills_projection
            WHERE account_id = ? AND market_scope = ? AND exchange_trade_id = ?
            """,
            (
                payload["account_id"],
                payload["market_scope"],
                payload["exchange_trade_id"],
            ),
        ).fetchone()
        if existing:
            if existing["projection_hash"] != projection_hash:
                raise LedgerConflictError(
                    "exchange trade ID was reused with different Fill content"
                )
            return
        self.connection.execute(
            """
            INSERT INTO fills_projection (
                fill_id, account_id, market_scope, exchange_trade_id,
                payload_json, projection_hash, source_event_id,
                exchange_event_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["fill_id"],
                payload["account_id"],
                payload["market_scope"],
                payload["exchange_trade_id"],
                payload_json,
                projection_hash,
                event_id,
                payload["exchange_event_time"],
            ),
        )

    def _apply_checkpoint(
        self,
        *,
        event_id: str,
        event_time: str,
        payload: Dict[str, Any],
    ) -> None:
        required = {
            "checkpoint_id",
            "covered_event_sequence",
            "covered_ledger_hash",
            "covered_projection_hash",
            "code_commit",
            "policy_bundle_hash",
            "created_at",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise LedgerIntegrityError(
                f"CheckpointRecorded payload missing fields: {missing}"
            )
        if not isinstance(payload["checkpoint_id"], str) or not payload["checkpoint_id"]:
            raise LedgerIntegrityError("checkpoint_id must be a non-empty string")
        if not isinstance(payload["code_commit"], str) or not payload["code_commit"]:
            raise LedgerIntegrityError("checkpoint code_commit must be non-empty")
        _require_sha256(payload["covered_ledger_hash"], "covered_ledger_hash")
        _require_sha256(
            payload["covered_projection_hash"],
            "covered_projection_hash",
        )
        _require_sha256(payload["policy_bundle_hash"], "policy_bundle_hash")
        _require_utc_datetime(payload["created_at"], "created_at")
        if payload["created_at"] != event_time:
            raise LedgerIntegrityError(
                "checkpoint created_at must equal its event time"
            )
        covered_sequence = payload["covered_event_sequence"]
        if (
            isinstance(covered_sequence, bool)
            or not isinstance(covered_sequence, int)
            or covered_sequence < 1
        ):
            raise LedgerIntegrityError(
                "covered_event_sequence must be a positive integer"
            )
        current = self.connection.execute(
            "SELECT sequence FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if current is None or covered_sequence != current["sequence"] - 1:
            raise LedgerIntegrityError(
                "checkpoint must cover the immediately preceding event"
            )
        covered = self.connection.execute(
            "SELECT ledger_hash FROM events WHERE sequence = ?",
            (covered_sequence,),
        ).fetchone()
        if (
            covered is None
            or covered["ledger_hash"] != payload["covered_ledger_hash"]
        ):
            raise LedgerIntegrityError(
                "checkpoint covered ledger hash does not match event chain"
            )
        self.verify_economic_consistency()
        if payload["covered_projection_hash"] != self.state_projection_hash():
            raise LedgerIntegrityError(
                "checkpoint covered projection hash does not match current state"
            )
        payload_json = canonical_json(payload)
        checkpoint_hash = business_hash(payload)
        existing = self.connection.execute(
            "SELECT checkpoint_hash FROM checkpoints WHERE checkpoint_id = ?",
            (payload["checkpoint_id"],),
        ).fetchone()
        if existing:
            if existing["checkpoint_hash"] != checkpoint_hash:
                raise LedgerConflictError(
                    "checkpoint ID was reused with different content"
                )
            return
        self.connection.execute(
            """
            INSERT INTO checkpoints (
                checkpoint_id, covered_event_sequence, covered_ledger_hash,
                covered_projection_hash, payload_json, checkpoint_hash,
                source_event_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["checkpoint_id"],
                covered_sequence,
                payload["covered_ledger_hash"],
                payload["covered_projection_hash"],
                payload_json,
                checkpoint_hash,
                event_id,
                payload["created_at"],
            ),
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
            "BalanceStateRecorded": {"OBSERVED"},
            "ProtectiveOrderStateRecorded": _PROTECTIVE_ORDER_STATES,
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
            "BalanceStateRecorded": (
                "balance_id",
                "account_id",
                "asset",
                "exchange_snapshot_time",
                "source_snapshot_hash",
            ),
            "ProtectiveOrderStateRecorded": (
                "protective_order_id",
                "instrument_id",
                "position_id",
                "risk_decision_id",
                "execution_intent_id",
                "attempt_id",
                "local_order_id",
                "role",
                "side",
                "reduce_only_or_spot_sell",
                "risk_policy_id",
                "risk_policy_hash",
                "policy_version",
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
            "source_snapshot_hash",
            "risk_policy_hash",
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
        elif event_type == "BalanceStateRecorded":
            amounts = tuple(
                Decimal(canonical_decimal(payload[field_name]))
                for field_name in (
                    "total_balance",
                    "available_balance",
                    "locked_balance",
                    "borrowed_balance",
                    "interest_accrued",
                )
            )
            if any(amount < 0 for amount in amounts):
                raise LedgerIntegrityError(
                    "balance projection amounts cannot be negative"
                )
            total, available, locked, _, _ = amounts
            if available + locked > total:
                raise LedgerIntegrityError(
                    "available plus locked balance cannot exceed total"
                )
            if payload["balance_id"] != (
                f"{payload['account_id']}:{payload['asset']}"
            ):
                raise LedgerIntegrityError(
                    "balance_id must match account and asset"
                )
            _require_utc_datetime(
                payload["exchange_snapshot_time"],
                "exchange_snapshot_time",
            )
        elif event_type == "ProtectiveOrderStateRecorded":
            if payload["role"] not in ("DISASTER_STOP", "STRATEGY_STOP"):
                raise LedgerIntegrityError("protective order role is invalid")
            if payload["side"] not in ("BUY", "SELL"):
                raise LedgerIntegrityError("protective order side is invalid")
            if payload["reduce_only_or_spot_sell"] not in (
                "REDUCE_ONLY",
                "SPOT_SELL",
            ):
                raise LedgerIntegrityError(
                    "protective order reduction mechanism is invalid"
                )
            if payload["reduce_only_or_spot_sell"] == "SPOT_SELL":
                if (
                    ":SPOT:" not in payload["instrument_id"]
                    or payload["side"] != "SELL"
                ):
                    raise LedgerIntegrityError(
                        "SPOT_SELL protection must be a spot SELL"
                    )
            elif ":USDT_PERP:" not in payload["instrument_id"]:
                raise LedgerIntegrityError(
                    "REDUCE_ONLY protection must use the perpetual carrier"
                )
            trigger = Decimal(canonical_decimal(payload["trigger_price"]))
            covered = Decimal(canonical_decimal(payload["covered_quantity"]))
            limit_value = payload["limit_price_or_null"]
            if trigger <= 0 or covered <= 0:
                raise LedgerIntegrityError(
                    "protective order trigger and coverage must be positive"
                )
            if limit_value is not None and Decimal(
                canonical_decimal(limit_value)
            ) <= 0:
                raise LedgerIntegrityError(
                    "protective order limit price must be positive or null"
                )
            for optional_id in (
                "venue_order_id_or_null",
                "replacement_of_or_null",
            ):
                value = payload[optional_id]
                if value is not None and (
                    not isinstance(value, str) or not value
                ):
                    raise LedgerIntegrityError(
                        f"{optional_id} must be null or a non-empty string"
                    )
            parsed_times = {}
            for field_name in (
                "unprotected_window_started_at_or_null",
                "replacement_deadline_at_or_null",
                "effective_at_or_null",
            ):
                value = payload[field_name]
                if value is not None:
                    _require_utc_datetime(value, field_name)
                    parsed_times[field_name] = datetime.fromisoformat(
                        value[:-1] + "+00:00"
                    )
            started = parsed_times.get("unprotected_window_started_at_or_null")
            deadline = parsed_times.get("replacement_deadline_at_or_null")
            if (started is None) != (deadline is None):
                raise LedgerIntegrityError(
                    "unprotected window start and deadline must appear together"
                )
            if started is not None and deadline <= started:
                raise LedgerIntegrityError(
                    "protective replacement deadline must follow window start"
                )
            if state == "ACTIVE" and "effective_at_or_null" not in parsed_times:
                raise LedgerIntegrityError(
                    "ACTIVE protective order requires effective_at"
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
            self.connection.execute("DELETE FROM allocated_costs_projection")
            self.connection.execute("DELETE FROM funding_cashflows_projection")
            self.connection.execute("DELETE FROM equity_snapshots_projection")
            self.connection.execute("DELETE FROM fills_projection")
            self.connection.execute("DELETE FROM checkpoints")
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

    def _projection_snapshot(
        self,
        *,
        include_checkpoints: bool,
    ) -> Dict[str, Any]:
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
                SELECT event_id, flow_id, account_id, flow_type,
                       signed_amount_usdt, occurred_at
                FROM external_cash_flows_projection ORDER BY event_id
                """
            ).fetchall()
        ]
        snapshot: Dict[str, Any] = {
            "operating_costs_projection": costs,
            "external_cash_flows_projection": cash_flows,
            "allocated_costs_projection": [
                {
                    "cost_id": row["cost_id"],
                    "account_id": row["account_id"],
                    "evaluation_ledger": row["evaluation_ledger"],
                    "release_route": row["release_route"],
                    "payload": json.loads(row["payload_json"]),
                    "projection_hash": row["projection_hash"],
                    "source_event_id": row["source_event_id"],
                    "occurred_at": row["occurred_at"],
                }
                for row in self.connection.execute(
                    """
                    SELECT cost_id, account_id, evaluation_ledger,
                           release_route, payload_json, projection_hash,
                           source_event_id, occurred_at
                    FROM allocated_costs_projection
                    ORDER BY occurred_at, cost_id
                    """
                ).fetchall()
            ],
            "funding_cashflows_projection": [
                {
                    "funding_id": row["funding_id"],
                    "account_id": row["account_id"],
                    "instrument_id": row["instrument_id"],
                    "payload": json.loads(row["payload_json"]),
                    "projection_hash": row["projection_hash"],
                    "source_event_id": row["source_event_id"],
                    "settled_at": row["settled_at"],
                }
                for row in self.connection.execute(
                    """
                    SELECT funding_id, account_id, instrument_id, payload_json,
                           projection_hash, source_event_id, settled_at
                    FROM funding_cashflows_projection
                    ORDER BY settled_at, funding_id
                    """
                ).fetchall()
            ],
            "equity_snapshots_projection": [
                {
                    "equity_snapshot_id": row["equity_snapshot_id"],
                    "account_id": row["account_id"],
                    "evaluation_ledger": row["evaluation_ledger"],
                    "release_route": row["release_route"],
                    "payload": json.loads(row["payload_json"]),
                    "projection_hash": row["projection_hash"],
                    "source_event_id": row["source_event_id"],
                    "as_of": row["as_of"],
                }
                for row in self.connection.execute(
                    """
                    SELECT equity_snapshot_id, account_id, evaluation_ledger,
                           release_route, payload_json, projection_hash,
                           source_event_id, as_of
                    FROM equity_snapshots_projection
                    ORDER BY as_of, equity_snapshot_id
                    """
                ).fetchall()
            ],
            "fills_projection": [
                {
                    "fill_id": row["fill_id"],
                    "account_id": row["account_id"],
                    "market_scope": row["market_scope"],
                    "exchange_trade_id": row["exchange_trade_id"],
                    "payload": json.loads(row["payload_json"]),
                    "projection_hash": row["projection_hash"],
                    "source_event_id": row["source_event_id"],
                    "exchange_event_time": row["exchange_event_time"],
                }
                for row in self.connection.execute(
                    """
                    SELECT fill_id, account_id, market_scope, exchange_trade_id,
                           payload_json, projection_hash, source_event_id,
                           exchange_event_time
                    FROM fills_projection
                    ORDER BY account_id, market_scope, exchange_trade_id
                    """
                ).fetchall()
            ],
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
        if include_checkpoints:
            snapshot["checkpoints"] = [
                {
                    "checkpoint_id": row["checkpoint_id"],
                    "covered_event_sequence": row["covered_event_sequence"],
                    "covered_ledger_hash": row["covered_ledger_hash"],
                    "covered_projection_hash": row["covered_projection_hash"],
                    "payload": json.loads(row["payload_json"]),
                    "checkpoint_hash": row["checkpoint_hash"],
                    "source_event_id": row["source_event_id"],
                    "created_at": row["created_at"],
                }
                for row in self.connection.execute(
                    """
                    SELECT checkpoint_id, covered_event_sequence,
                           covered_ledger_hash, covered_projection_hash,
                           payload_json, checkpoint_hash, source_event_id,
                           created_at
                    FROM checkpoints ORDER BY checkpoint_id
                    """
                ).fetchall()
            ]
        return snapshot

    def projection_snapshot(self) -> Dict[str, Any]:
        """Return canonical projection content suitable for Golden replay hashing."""

        return self._projection_snapshot(include_checkpoints=True)

    def state_projection_hash(self) -> str:
        """Hash current derived state without the checkpoint cache itself."""

        self.verify_projection_integrity()
        return business_hash(
            self._projection_snapshot(include_checkpoints=False)
        )

    def projection_hash(self) -> str:
        self.verify_projection_integrity()
        return business_hash(
            self._projection_snapshot(include_checkpoints=True)
        )

    def economic_ledger_snapshot(
        self,
        *,
        snapshot_id: str,
        account_id: str,
        evaluation_ledger: str,
        release_route: str,
        direction: str,
        venue: str,
        recipe_release_id: str,
        recipe_release_hash: str,
        deployment_line_id: str,
        deployment_line_hash: str,
        evaluation_window_start: str,
        evaluation_window_end: str,
        accounting_policy_id: str,
        accounting_policy_hash: str,
        cost_allocation_policy_id: str,
        cost_allocation_policy_hash: str,
        generated_at: str,
    ) -> Dict[str, Any]:
        """Freeze a verified accounting input over the half-open event window."""

        for name, value in (
            ("snapshot_id", snapshot_id),
            ("account_id", account_id),
            ("recipe_release_id", recipe_release_id),
            ("deployment_line_id", deployment_line_id),
            ("accounting_policy_id", accounting_policy_id),
            ("cost_allocation_policy_id", cost_allocation_policy_id),
        ):
            if not isinstance(value, str) or not value:
                raise LedgerIntegrityError(f"{name} must be non-empty")
        if evaluation_ledger not in _ECONOMIC_LEDGERS:
            raise LedgerIntegrityError("economic snapshot ledger is invalid")
        if release_route not in ("BASELINE_ONLY", "AI_ENHANCED"):
            raise LedgerIntegrityError("economic snapshot route is invalid")
        if direction not in ("LONG", "SHORT"):
            raise LedgerIntegrityError("economic snapshot direction is invalid")
        if venue not in ("BINANCE_SPOT", "BINANCE_USDT_PERP"):
            raise LedgerIntegrityError("economic snapshot venue is invalid")
        if (
            evaluation_ledger == "AI_LEDGER"
            and release_route != "AI_ENHANCED"
        ):
            raise LedgerIntegrityError(
                "economic snapshot ledger and route disagree"
            )
        if (direction, venue) not in {
            ("LONG", "BINANCE_SPOT"),
            ("SHORT", "BINANCE_USDT_PERP"),
        }:
            raise LedgerIntegrityError(
                "economic snapshot direction and venue disagree"
            )
        for name, value in (
            ("recipe_release_hash", recipe_release_hash),
            ("deployment_line_hash", deployment_line_hash),
            ("accounting_policy_hash", accounting_policy_hash),
            ("cost_allocation_policy_hash", cost_allocation_policy_hash),
        ):
            _require_sha256(value, name)
        for name, value in (
            ("evaluation_window_start", evaluation_window_start),
            ("evaluation_window_end", evaluation_window_end),
            ("generated_at", generated_at),
        ):
            _require_utc_datetime(value, name)
        start = datetime.fromisoformat(
            evaluation_window_start.replace("Z", "+00:00")
        )
        end = datetime.fromisoformat(
            evaluation_window_end.replace("Z", "+00:00")
        )
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if end <= start:
            raise LedgerIntegrityError(
                "economic snapshot window must increase"
            )
        if generated < end:
            raise LedgerIntegrityError(
                "economic snapshot cannot precede its window end"
            )

        source_ledger_hash = self.verify_integrity()
        source_projection_hash = self.state_projection_hash()

        def in_event_window(value: str) -> bool:
            current = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return start < current <= end

        def in_equity_window(value: str) -> bool:
            current = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return start <= current <= end

        expected_fact_scope = {
            "evaluation_ledger": evaluation_ledger,
            "release_route": release_route,
            "direction": direction,
            "venue": venue,
            "recipe_release_id": recipe_release_id,
            "recipe_release_hash": recipe_release_hash,
            "deployment_line_id": deployment_line_id,
            "deployment_line_hash": deployment_line_hash,
        }

        def in_exact_scope(payload: Mapping[str, Any]) -> bool:
            return all(
                payload.get(name) == value
                for name, value in expected_fact_scope.items()
            )

        fills = []
        for row in self.connection.execute(
            """
            SELECT payload_json FROM fills_projection
            WHERE account_id = ?
            ORDER BY exchange_event_time, fill_id
            """,
            (account_id,),
        ).fetchall():
            payload = json.loads(row["payload_json"])
            if (
                not in_exact_scope(payload)
                or not in_event_window(payload["exchange_event_time"])
            ):
                continue
            fills.append(
                {
                    name: payload[name]
                    for name in (
                        "fill_id",
                        "instrument_id",
                        "side",
                        "quantity",
                        "price",
                        "contract_multiplier",
                        "fee_value_usdt",
                        "implementation_shortfall_usdt",
                        "exchange_event_time",
                    )
                }
            )

        funding = []
        for row in self.connection.execute(
            """
            SELECT payload_json FROM funding_cashflows_projection
            WHERE account_id = ?
            ORDER BY settled_at, funding_id
            """,
            (account_id,),
        ).fetchall():
            payload = json.loads(row["payload_json"])
            if (
                not in_exact_scope(payload)
                or not in_event_window(payload["settled_at"])
            ):
                continue
            funding.append(
                {
                    name: payload[name]
                    for name in (
                        "funding_id",
                        "instrument_id",
                        "signed_amount_usdt",
                        "position_quantity",
                        "funding_rate",
                        "mark_price",
                        "settled_at",
                    )
                }
            )

        cash_flows = [
            {
                "flow_id": row["flow_id"],
                "flow_type": row["flow_type"],
                "signed_amount_usdt": row["signed_amount_usdt"],
                "occurred_at": row["occurred_at"],
            }
            for row in self.connection.execute(
                """
                SELECT flow_id, flow_type, signed_amount_usdt, occurred_at
                FROM external_cash_flows_projection
                WHERE account_id = ?
                ORDER BY occurred_at, flow_id
                """,
                (account_id,),
            ).fetchall()
            if in_event_window(row["occurred_at"])
        ]

        allocated_costs = []
        for row in self.connection.execute(
            """
            SELECT payload_json FROM allocated_costs_projection
            WHERE account_id = ? AND evaluation_ledger = ?
                  AND release_route = ?
            ORDER BY occurred_at, cost_id
            """,
            (account_id, evaluation_ledger, release_route),
        ).fetchall():
            payload = json.loads(row["payload_json"])
            if (
                not in_exact_scope(payload)
                or not in_event_window(payload["occurred_at"])
            ):
                continue
            if (
                payload["allocation_policy_hash"]
                != cost_allocation_policy_hash
            ):
                raise LedgerIntegrityError(
                    "allocated cost policy hash does not match snapshot"
                )
            allocated_costs.append(
                {
                    name: payload[name]
                    for name in (
                        "cost_id",
                        "category",
                        "amount_usdt",
                        "allocation_scope",
                        "occurred_at",
                    )
                }
            )

        equity_points = []
        for row in self.connection.execute(
            """
            SELECT payload_json FROM equity_snapshots_projection
            WHERE account_id = ? AND evaluation_ledger = ?
                  AND release_route = ?
            ORDER BY as_of, equity_snapshot_id
            """,
            (account_id, evaluation_ledger, release_route),
        ).fetchall():
            payload = json.loads(row["payload_json"])
            if (
                not in_exact_scope(payload)
                or not in_equity_window(payload["as_of"])
            ):
                continue
            equity_points.append(
                {
                    name: payload[name]
                    for name in (
                        "equity_snapshot_id",
                        "as_of",
                        "marked_equity_usdt",
                        "liquidation_equity_usdt",
                        "spot_notional_usdt",
                        "perp_notional_usdt",
                        "active_order_risk_increasing_notional_usdt",
                        "active_order_unknown_notional_usdt",
                        "expected_exit_fee_accrued_usdt",
                        "conservative_close_verified",
                        "is_utc_day_start",
                        "position_cost_bases",
                    )
                }
            )
        if (
            len(equity_points) < 2
            or equity_points[0]["as_of"] != evaluation_window_start
            or equity_points[-1]["as_of"] != evaluation_window_end
        ):
            raise LedgerIntegrityError(
                "economic snapshot requires exact boundary equity facts"
            )

        snapshot = {
            "$schema": "./economic-ledger-snapshot-v1.schema.json",
            "schema_version": "1.0.0",
            "snapshot_id": snapshot_id,
            "snapshot_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "source_ledger_hash": source_ledger_hash,
            "source_projection_hash": source_projection_hash,
            "accounting_policy_id": accounting_policy_id,
            "accounting_policy_hash": accounting_policy_hash,
            "cost_allocation_policy_id": cost_allocation_policy_id,
            "cost_allocation_policy_hash": cost_allocation_policy_hash,
            "scope": {
                "account_id": account_id,
                "evaluation_ledger": evaluation_ledger,
                "release_route": release_route,
                "direction": direction,
                "venue": venue,
                "recipe_release_id": recipe_release_id,
                "recipe_release_hash": recipe_release_hash,
                "deployment_line_id": deployment_line_id,
                "deployment_line_hash": deployment_line_hash,
                "evaluation_window_start": evaluation_window_start,
                "evaluation_window_end": evaluation_window_end,
            },
            "reporting_asset": "USDT",
            "window_event_convention": "START_EXCLUSIVE_END_INCLUSIVE",
            "starting_liquidation_equity_usdt": equity_points[0][
                "liquidation_equity_usdt"
            ],
            "ending_liquidation_equity_usdt": equity_points[-1][
                "liquidation_equity_usdt"
            ],
            "opening_positions": equity_points[0]["position_cost_bases"],
            "fills": fills,
            "funding_cashflows": funding,
            "external_cash_flows": cash_flows,
            "allocated_costs": allocated_costs,
            "equity_points": equity_points,
            "generated_at": generated_at,
            "replay_verified": True,
        }
        snapshot["snapshot_hash"] = economic_snapshot_hash(snapshot)
        return snapshot

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
        for table, event_type in (
            ("operating_costs_projection", "OperatingCostRecorded"),
            ("external_cash_flows_projection", "ExternalCashFlowRecorded"),
        ):
            rows = self.connection.execute(
                f"SELECT * FROM {table}"
            ).fetchall()
            for row in rows:
                source = self.connection.execute(
                    """
                    SELECT event_type, event_time, payload_json
                    FROM events WHERE event_id = ?
                    """,
                    (row["event_id"],),
                ).fetchone()
                if source is None or source["event_type"] != event_type:
                    raise LedgerIntegrityError(
                        f"{table} source event is invalid"
                    )
                payload = json.loads(source["payload_json"])
                mismatch = source["event_time"] != row["occurred_at"]
                if table == "external_cash_flows_projection":
                    mismatch = mismatch or (
                        canonical_decimal(payload["signed_amount_usdt"])
                        != row["signed_amount_usdt"]
                    )
                else:
                    mismatch = mismatch or (
                        canonical_decimal(payload["amount_usdt"])
                        != row["amount_usdt"]
                    )
                if mismatch:
                    raise LedgerIntegrityError(
                        f"{table} does not match its source event"
                    )
                if table == "external_cash_flows_projection":
                    if (
                        payload["flow_id"] != row["flow_id"]
                        or payload["account_id"] != row["account_id"]
                        or payload["flow_type"] != row["flow_type"]
                    ):
                        raise LedgerIntegrityError(
                            "external cash flow columns disagree"
                        )
                elif payload["category"] != row["category"]:
                    raise LedgerIntegrityError(
                        "operating cost category disagrees"
                    )
        economic_specs = (
            (
                "allocated_costs_projection",
                "AllocatedCostRecorded",
                "cost_id",
                "occurred_at",
                ("account_id", "evaluation_ledger", "release_route"),
            ),
            (
                "funding_cashflows_projection",
                "FundingCashFlowRecorded",
                "funding_id",
                "settled_at",
                ("account_id", "instrument_id"),
            ),
            (
                "equity_snapshots_projection",
                "EquitySnapshotRecorded",
                "equity_snapshot_id",
                "as_of",
                ("account_id", "evaluation_ledger", "release_route"),
            ),
        )
        for table, event_type, id_field, time_field, columns in economic_specs:
            rows = self.connection.execute(f"SELECT * FROM {table}").fetchall()
            for row in rows:
                payload = json.loads(row["payload_json"])
                if (
                    payload.get(id_field) != row[id_field]
                    or payload.get(time_field) != row[time_field]
                    or business_hash(payload) != row["projection_hash"]
                    or any(payload.get(name) != row[name] for name in columns)
                ):
                    raise LedgerIntegrityError(
                        f"economic projection integrity mismatch in {table}"
                    )
                source = self.connection.execute(
                    """
                    SELECT event_type, event_time, payload_json
                    FROM events WHERE event_id = ?
                    """,
                    (row["source_event_id"],),
                ).fetchone()
                if (
                    source is None
                    or source["event_type"] != event_type
                    or source["event_time"] != row[time_field]
                    or source["payload_json"] != row["payload_json"]
                ):
                    raise LedgerIntegrityError(
                        f"economic projection source mismatch in {table}"
                    )
        fills = self.connection.execute(
            """
            SELECT fill_id, payload_json, projection_hash, source_event_id,
                   exchange_event_time
            FROM fills_projection
            """
        ).fetchall()
        for row in fills:
            payload = json.loads(row["payload_json"])
            if (
                payload.get("fill_id") != row["fill_id"]
                or payload.get("exchange_event_time") != row["exchange_event_time"]
                or business_hash(payload) != row["projection_hash"]
            ):
                raise LedgerIntegrityError("fill projection integrity mismatch")
            source = self.connection.execute(
                """
                SELECT event_type, event_time, payload_json
                FROM events WHERE event_id = ?
                """,
                (row["source_event_id"],),
            ).fetchone()
            if (
                source is None
                or source["event_type"] != "FillRecorded"
                or source["event_time"] != row["exchange_event_time"]
                or source["payload_json"] != row["payload_json"]
            ):
                raise LedgerIntegrityError(
                    "fill projection does not match its source event"
                )
        checkpoints = self.connection.execute(
            """
            SELECT checkpoint_id, payload_json, checkpoint_hash,
                   source_event_id, created_at
            FROM checkpoints
            """
        ).fetchall()
        for row in checkpoints:
            payload = json.loads(row["payload_json"])
            if (
                payload.get("checkpoint_id") != row["checkpoint_id"]
                or payload.get("created_at") != row["created_at"]
                or business_hash(payload) != row["checkpoint_hash"]
            ):
                raise LedgerIntegrityError("checkpoint integrity mismatch")
            source = self.connection.execute(
                """
                SELECT event_type, event_time, payload_json
                FROM events WHERE event_id = ?
                """,
                (row["source_event_id"],),
            ).fetchone()
            if (
                source is None
                or source["event_type"] != "CheckpointRecorded"
                or source["event_time"] != row["created_at"]
                or source["payload_json"] != row["payload_json"]
            ):
                raise LedgerIntegrityError(
                    "checkpoint does not match its source event"
                )

    def verify_economic_consistency(self) -> None:
        """Require fills, order totals, positions, and protection to reconcile."""

        fill_totals: Dict[str, Decimal] = {}
        for row in self.connection.execute(
            "SELECT payload_json FROM fills_projection"
        ).fetchall():
            fill = json.loads(row["payload_json"])
            order_id = fill["local_order_id"]
            fill_totals[order_id] = fill_totals.get(
                order_id,
                Decimal("0"),
            ) + Decimal(canonical_decimal(fill["quantity"]))
        orders = self.connection.execute(
            "SELECT entity_id, payload_json FROM orders_projection"
        ).fetchall()
        order_ids = {row["entity_id"] for row in orders}
        orphan_fill_orders = sorted(set(fill_totals) - order_ids)
        if orphan_fill_orders:
            raise LedgerIntegrityError(
                f"fill projections reference missing orders: {orphan_fill_orders}"
            )
        for row in orders:
            order = json.loads(row["payload_json"])
            projected_fill = Decimal(
                canonical_decimal(order["cumulative_filled_quantity"])
            )
            fill_sum = fill_totals.get(row["entity_id"], Decimal("0"))
            if fill_sum != projected_fill:
                raise LedgerIntegrityError(
                    f"order {row['entity_id']} fill projection does not reconcile"
                )

        active_protection = self.connection.execute(
            """
            SELECT payload_json FROM protective_orders_projection
            WHERE state = 'ACTIVE'
            """
        ).fetchall()
        protection_coverage: Dict[str, Decimal] = {}
        for row in active_protection:
            protective = json.loads(row["payload_json"])
            position = self.connection.execute(
                """
                SELECT payload_json FROM positions_projection
                WHERE entity_id = ?
                """,
                (protective["position_id"],),
            ).fetchone()
            if position is None:
                raise LedgerIntegrityError(
                    "active protective order has no position projection"
                )
            position_payload = json.loads(position["payload_json"])
            if position_payload["instrument_id"] != protective["instrument_id"]:
                raise LedgerIntegrityError(
                    "protective order carrier differs from covered position"
                )
            covered_quantity = Decimal(
                canonical_decimal(protective["covered_quantity"])
            )
            protection_coverage[protective["position_id"]] = (
                protection_coverage.get(
                    protective["position_id"],
                    Decimal("0"),
                )
                + covered_quantity
            )
        positions = self.connection.execute(
            "SELECT entity_id, payload_json FROM positions_projection"
        ).fetchall()
        for row in positions:
            position = json.loads(row["payload_json"])
            quantity = abs(
                Decimal(canonical_decimal(position["signed_quantity"]))
            )
            if quantity > 0 and protection_coverage.get(
                row["entity_id"],
                Decimal("0"),
            ) < quantity:
                raise LedgerIntegrityError(
                    "actual position is not fully covered by active protection"
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
