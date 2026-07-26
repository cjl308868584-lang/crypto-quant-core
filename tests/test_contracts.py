import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from crypto_quant.contracts import (
    Direction,
    EventEnvelope,
    MetaAction,
    MetaDecision,
    PortfolioRiskSnapshot,
    TargetPosition,
)
from crypto_quant.decimal_math import RiskRatio
from crypto_quant.errors import ContractError

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def envelope(payload, event_id="event-1", **overrides):
    values = {
        "schema_version": "1.1.0",
        "event_id": event_id,
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "causation_id": None,
        "run_id": "run-1",
        "event_time": NOW,
        "available_at": NOW,
        "ingested_at": NOW,
        "recorded_at": NOW,
        "source": "REPLAY",
        "payload": payload,
    }
    values.update(overrides)
    return EventEnvelope.create(**values)


class ContractTests(unittest.TestCase):
    def test_meta_decision_and_target_ids_are_deterministic(self) -> None:
        decision = MetaDecision(
            schema_version="1.1.0",
            recipe_release_id="recipe-1",
            proposal_id="proposal-1",
            decision_time=NOW,
            direction=Direction.LONG,
            action=MetaAction.REDUCE,
            risk_bucket=RiskRatio("0.25"),
            reason_code="COST_FILTER",
        )
        self.assertEqual(len({decision.decision_id for _ in range(100)}), 1)
        target = TargetPosition(
            schema_version="1.1.0",
            meta_decision_id=decision.decision_id,
            instrument_id="BINANCE:SPOT:ETHUSDT",
            target_sequence=1,
            decision_time=NOW,
            direction=Direction.LONG,
            target_quantity=Decimal("0.0123"),
            approved_capital_usdt=Decimal("500"),
            risk_bucket=RiskRatio("0.25"),
        )
        self.assertEqual(len({target.target_id for _ in range(100)}), 1)

    def test_contracts_reject_semantic_contradictions(self) -> None:
        with self.assertRaises(ContractError):
            MetaDecision(
                schema_version="1.1.0",
                recipe_release_id="recipe-1",
                proposal_id="proposal-1",
                decision_time=NOW,
                direction=Direction.LONG,
                action=MetaAction.REJECT,
                risk_bucket=RiskRatio("0.25"),
                reason_code="REJECT",
            )
        with self.assertRaises(ContractError):
            TargetPosition(
                schema_version="1.1.0",
                meta_decision_id="meta-1",
                instrument_id="BINANCE:PERP:ETHUSDT",
                target_sequence=1,
                decision_time=NOW,
                direction=Direction.SHORT,
                target_quantity=Decimal("0.01"),
                approved_capital_usdt=Decimal("500"),
                risk_bucket=RiskRatio("0.25"),
            )

    def test_event_envelope_detects_time_and_hash_errors(self) -> None:
        payload = {"amount_usdt": Decimal("1.25")}
        valid = envelope(payload)
        valid.validate(payload)
        with self.assertRaises(ContractError):
            valid.validate({"amount_usdt": Decimal("2")})
        with self.assertRaises(ContractError):
            replace(valid, event_hash="0" * 64).validate(payload)
        with self.assertRaises(ContractError):
            envelope(
                payload,
                available_at=NOW - timedelta(seconds=1),
            )
        exceptional = envelope(
            payload,
            available_at=NOW - timedelta(seconds=1),
            ordering_exception_reason="EXCHANGE_TIMESTAMP_CORRECTION",
        )
        exceptional.validate(payload)

    def test_risk_snapshot_consumes_actual_account_state(self) -> None:
        snapshot = PortfolioRiskSnapshot(
            schema_version="1.1.0",
            snapshot_time=NOW,
            marked_equity_usdt=Decimal("500"),
            current_signed_exposure_usdt=Decimal("-100"),
            active_order_worst_case_exposure_usdt=Decimal("25"),
            deployment_stage_cap=RiskRatio("0.25"),
            drawdown_ratio=RiskRatio("0.10"),
            unresolved_order_count=1,
            reconciliation_clean=False,
        )
        self.assertEqual(snapshot.current_signed_exposure_usdt, Decimal("-100"))
        self.assertFalse(snapshot.reconciliation_clean)


if __name__ == "__main__":
    unittest.main()
