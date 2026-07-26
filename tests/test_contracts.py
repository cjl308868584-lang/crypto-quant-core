import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from factories import HASH, NOW, make_meta, make_proposal, make_snapshot, make_target

from crypto_quant.contracts import (
    DecisionSource,
    DeploymentStage,
    Direction,
    EventEnvelope,
    MetaDecision,
    StrategyRole,
    TargetAction,
)
from crypto_quant.decimal_math import RiskRatio
from crypto_quant.errors import ContractError


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
    def test_proposal_meta_and_target_hashes_are_deterministic_100_times(self) -> None:
        proposal = make_proposal()
        meta = make_meta(proposal)
        target = make_target(proposal, meta)
        target.assert_lineage(proposal, meta)
        self.assertEqual(len({proposal.proposal_id for _ in range(100)}), 1)
        self.assertEqual(len({meta.meta_decision_id for _ in range(100)}), 1)
        self.assertEqual(len({target.target_id for _ in range(100)}), 1)
        self.assertEqual(target.signed_target_ratio_or_null, Decimal("0.2"))

    def test_no_ai_decision_is_explicit_and_has_no_model_fields(self) -> None:
        proposal = make_proposal()
        meta = make_meta(proposal)
        self.assertEqual(meta.decision_source, DecisionSource.NO_AI_BASE)
        self.assertIsNone(meta.model_id_or_null)
        with self.assertRaises(ContractError):
            replace(meta, no_ai_base_version_or_null=None)
        with self.assertRaises(ContractError):
            replace(meta, model_id_or_null="forbidden-model")

    def test_shadow_or_retired_model_cannot_be_formally_eligible(self) -> None:
        proposal = make_proposal()
        with self.assertRaises(ContractError):
            MetaDecision(
                schema_version="1.1.0",
                proposal_id=proposal.proposal_id,
                decision_source=DecisionSource.MODEL,
                no_ai_base_version_or_null=None,
                model_id_or_null="model-1",
                model_version_or_null="1",
                deployment_stage=DeploymentStage.SHADOW,
                calibration_version_or_null="cal-1",
                p_net_positive_or_null=Decimal("0.6"),
                expected_net_return_or_null=Decimal("0.01"),
                return_q10_or_null=Decimal("-0.02"),
                return_q50_or_null=Decimal("0.01"),
                return_q90_or_null=Decimal("0.03"),
                uncertainty_score_or_null=Decimal("0.2"),
                ood_score_or_null=Decimal("0.1"),
                eligible=True,
                ineligibility_reason_mask=(),
                recommended_action=TargetAction.SET_TARGET,
                recommended_bucket_or_null=RiskRatio("0.25"),
                model_input_hash=HASH,
                prediction_hash=HASH,
            )

    def test_meta_action_uses_null_versus_zero_without_ambiguity(self) -> None:
        proposal = make_proposal()
        with self.assertRaises(ContractError):
            make_meta(proposal, eligible=False)
        ineligible_freeze = make_meta(
            proposal,
            action=TargetAction.FREEZE_INCREASES,
            bucket=None,
            eligible=False,
        )
        self.assertFalse(ineligible_freeze.eligible)
        freeze = make_meta(
            proposal,
            action=TargetAction.FREEZE_INCREASES,
            bucket=None,
        )
        freeze_target = make_target(proposal, freeze)
        self.assertIsNone(freeze_target.signed_target_ratio_or_null)
        self.assertIsNone(freeze_target.risk_bucket_or_null)
        self.assertIsNone(freeze_target.target_notional_usdt_or_null)

        flatten = make_meta(proposal, action=TargetAction.FLATTEN, bucket="0")
        flatten_target = make_target(proposal, flatten)
        self.assertEqual(flatten_target.signed_target_ratio_or_null, Decimal("0"))
        self.assertEqual(flatten_target.risk_bucket_or_null.value, Decimal("0"))
        self.assertEqual(flatten_target.target_notional_usdt_or_null, Decimal("0"))

    def test_shadow_proposal_and_direction_invention_are_rejected(self) -> None:
        shadow = make_proposal(role=StrategyRole.SHADOW)
        meta = make_meta(shadow)
        target = make_target(shadow, meta)
        with self.assertRaises(ContractError):
            target.assert_lineage(shadow, meta)
        formal = make_proposal()
        formal_meta = make_meta(formal)
        formal_target = make_target(formal, formal_meta)
        with self.assertRaises(ContractError):
            replace(formal_target, direction=Direction.SHORT)
        with self.assertRaises(ContractError):
            make_target(
                make_proposal(instrument_id="BINANCE:USDT_PERP:ETHUSDT"),
                make_meta(
                    make_proposal(instrument_id="BINANCE:USDT_PERP:ETHUSDT")
                ),
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
            envelope(payload, available_at=NOW - timedelta(seconds=1))
        exceptional = envelope(
            payload,
            available_at=NOW - timedelta(seconds=1),
            ordering_exception_reason="EXCHANGE_TIMESTAMP_CORRECTION",
        )
        exceptional.validate(payload)

    def test_risk_snapshot_uses_worst_case_gross_not_netting(self) -> None:
        snapshot = make_snapshot(
            net_exposure="0",
            gross_exposure="200",
            active_order_exposure="50",
        )
        self.assertEqual(snapshot.worst_case_gross_exposure_usdt, Decimal("250"))
        self.assertEqual(snapshot.effective_leverage, Decimal("0.5"))
        with self.assertRaises(ContractError):
            replace(snapshot, worst_case_gross_exposure_usdt=Decimal("0"))


if __name__ == "__main__":
    unittest.main()
