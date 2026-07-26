import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from factories import (
    NOW,
    make_deployment,
    make_meta,
    make_proposal,
    make_snapshot,
    make_target,
)

from crypto_quant.contracts import DeploymentStage, Direction, TargetAction
from crypto_quant.errors import ContractError
from crypto_quant.execution import (
    AttemptBook,
    AttemptReason,
    ChildOrderAttempt,
    ExecutionIntent,
    IntentStatus,
    OrderPolicy,
    ProposalAcceptance,
    ProposalBook,
    RiskDecisionAction,
    RiskGate,
    RiskLock,
    RiskLockScope,
    RiskLockType,
    TargetAcceptance,
    TargetBook,
)


def make_lock(lock_type, *, manual=False):
    return RiskLock(
        schema_version="1.1.0",
        lock_type=lock_type,
        scope=RiskLockScope.ACCOUNT,
        scope_id="account-1",
        activated_at=NOW,
        trigger_value="test",
        policy_version="1.1.2",
        allowed_actions=(
            RiskDecisionAction.FREEZE_INCREASES,
            RiskDecisionAction.REDUCE_ONLY,
            RiskDecisionAction.FLATTEN,
        ),
        release_condition="TEST_ONLY",
        requires_manual_release=manual,
    )


class TargetAndRiskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proposal = make_proposal()
        self.meta = make_meta(self.proposal)
        self.target = make_target(self.proposal, self.meta)
        self.snapshot = make_snapshot()
        self.deployment = make_deployment()
        self.gate = RiskGate()

    def evaluate(self, **overrides):
        values = {
            "target": self.target,
            "snapshot": self.snapshot,
            "deployment": self.deployment,
            "active_locks": (),
            "deployment_registry_version": "registry-1",
            "policy_version": "1.1.2",
        }
        values.update(overrides)
        return self.gate.evaluate(**values)

    def test_target_sequence_requires_explicit_supersession(self) -> None:
        book = TargetBook()
        self.assertEqual(book.accept(self.target), TargetAcceptance.ACCEPTED)
        self.assertEqual(book.accept(self.target), TargetAcceptance.DUPLICATE)
        stale = replace(self.target, target_sequence=0)
        self.assertEqual(book.accept(stale), TargetAcceptance.IGNORED_STALE)
        conflict = replace(self.target, hysteresis_state="CONFLICT")
        with self.assertRaises(ContractError):
            book.accept(conflict)
        missing_link = replace(self.target, target_sequence=2)
        with self.assertRaises(ContractError):
            book.accept(missing_link)
        successor = replace(
            self.target,
            target_sequence=2,
            supersedes_target_id_or_null=self.target.target_id,
        )
        self.assertEqual(book.accept(successor), TargetAcceptance.ACCEPTED)
        self.assertEqual(
            book.current("account-1", "ETH").target_id,
            successor.target_id,
        )

    def test_proposal_idempotency_and_cross_carrier_target_sequence(self) -> None:
        proposals = ProposalBook()
        self.assertEqual(
            proposals.accept(self.proposal),
            ProposalAcceptance.ACCEPTED,
        )
        self.assertEqual(
            proposals.accept(self.proposal),
            ProposalAcceptance.DUPLICATE,
        )
        with self.assertRaises(ContractError):
            proposals.accept(replace(self.proposal, raw_strength=Decimal("0.8")))

        targets = TargetBook()
        targets.accept(self.target)
        short_proposal = make_proposal(
            direction=Direction.SHORT,
            instrument_id="BINANCE:USDT_PERP:ETHUSDT",
        )
        short_meta = make_meta(short_proposal)
        short_target = make_target(
            short_proposal,
            short_meta,
            sequence=2,
            supersedes=self.target.target_id,
        )
        self.assertEqual(targets.accept(short_target), TargetAcceptance.ACCEPTED)
        self.assertEqual(
            targets.current("account-1", "ETH").instrument_id,
            "BINANCE:USDT_PERP:ETHUSDT",
        )

    def test_stage_multiplier_is_authoritative_and_multiplies_risk_bucket(self) -> None:
        decision = self.evaluate()
        self.assertEqual(self.target.signed_target_ratio_or_null, Decimal("0.2"))
        self.assertEqual(decision.stage_capped_target_ratio, Decimal("0.05"))
        self.assertEqual(decision.after_target_ratio, Decimal("0.05"))
        self.assertEqual(decision.action, RiskDecisionAction.CLAMP)
        self.assertEqual(len({decision.risk_decision_hash for _ in range(100)}), 1)
        with self.assertRaises(ContractError):
            make_deployment(stage=DeploymentStage.CANARY_25, multiplier="0.5")

    def test_unknown_or_capital_failure_freezes_increases(self) -> None:
        unknown = make_lock(RiskLockType.ORDER_UNKNOWN)
        locked = self.evaluate(active_locks=(unknown,))
        self.assertEqual(locked.action, RiskDecisionAction.FREEZE_INCREASES)
        self.assertEqual(locked.after_target_ratio, self.snapshot.current_actual_ratio)
        self.assertIn(unknown.lock_id, locked.active_lock_ids)

        insufficient = self.evaluate(
            snapshot=make_snapshot(deployable_capital="100"),
        )
        self.assertEqual(insufficient.action, RiskDecisionAction.FREEZE_INCREASES)
        self.assertIn("CAPITAL_READINESS", insufficient.triggered_limits)

        freeze_meta = make_meta(
            self.proposal,
            action=TargetAction.FREEZE_INCREASES,
            bucket=None,
        )
        freeze_target = make_target(self.proposal, freeze_meta)
        explicit = self.evaluate(target=freeze_target)
        self.assertEqual(explicit.action, RiskDecisionAction.FREEZE_INCREASES)
        self.assertEqual(explicit.after_target_ratio, self.snapshot.current_actual_ratio)

    def test_drawdown_12_and_active_orders_can_only_reduce_the_stage_cap(self) -> None:
        champion = make_deployment(
            stage=DeploymentStage.CHAMPION,
            multiplier="1",
        )
        current = make_snapshot(
            net_exposure="50",
            gross_exposure="50",
        )
        drawdown = self.evaluate(
            deployment=champion,
            snapshot=current,
            active_locks=(make_lock(RiskLockType.DRAWDOWN_12),),
        )
        self.assertLessEqual(
            abs(drawdown.after_target_ratio),
            abs(drawdown.stage_capped_target_ratio),
        )
        self.assertEqual(drawdown.after_target_ratio, Decimal("0.1"))

        high_target = make_target(
            self.proposal,
            self.meta,
            base_exposure="1",
        )
        capacity = self.evaluate(
            target=high_target,
            deployment=champion,
            snapshot=make_snapshot(
                net_exposure="10",
                gross_exposure="10",
                active_order_exposure="450",
            ),
        )
        self.assertEqual(capacity.after_target_ratio, Decimal("0.1"))
        self.assertIn("MAX_EFFECTIVE_LEVERAGE_1X", capacity.triggered_limits)

    def test_hard_drawdown_lock_flattens_and_manual_lock_does_not_auto_release(self) -> None:
        hard = make_lock(RiskLockType.DRAWDOWN_15)
        decision = self.evaluate(active_locks=(hard,))
        self.assertEqual(decision.action, RiskDecisionAction.FLATTEN)
        self.assertEqual(decision.after_target_ratio, Decimal("0"))

        manual = make_lock(RiskLockType.MANUAL, manual=True)
        with self.assertRaises(ContractError):
            manual.release(
                released_at=NOW + timedelta(minutes=1),
                release_reason="not-approved",
                manual_approved=False,
            )
        released = manual.release(
            released_at=NOW + timedelta(minutes=1),
            release_reason="approved",
            manual_approved=True,
        )
        self.assertFalse(released.active)

    def test_risk_gate_rejects_unapproved_direction(self) -> None:
        with self.assertRaises(ContractError):
            self.evaluate(deployment=make_deployment(direction=Direction.SHORT))
        with self.assertRaises(ContractError):
            self.evaluate(deployment=replace(self.deployment, venue="GATE"))

    def test_current_worst_case_leverage_above_one_freezes_increases(self) -> None:
        overloaded = make_snapshot(
            net_exposure="10",
            gross_exposure="500",
            active_order_exposure="10",
        )
        decision = self.evaluate(snapshot=overloaded)
        self.assertEqual(decision.action, RiskDecisionAction.FREEZE_INCREASES)
        self.assertLessEqual(
            abs(decision.after_target_ratio),
            abs(overloaded.current_actual_ratio),
        )
        self.assertIn(
            "CURRENT_WORST_CASE_LEVERAGE_ABOVE_1X",
            decision.triggered_limits,
        )

    def test_risk_lock_cannot_block_protective_actions(self) -> None:
        with self.assertRaises(ContractError):
            replace(
                make_lock(RiskLockType.MANUAL),
                allowed_actions=(RiskDecisionAction.FREEZE_INCREASES,),
            )


class IntentAndAttemptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proposal = make_proposal()
        self.meta = make_meta(self.proposal)
        self.target = make_target(self.proposal, self.meta)
        self.risk = RiskGate().evaluate(
            target=self.target,
            snapshot=make_snapshot(),
            deployment=make_deployment(),
            active_locks=(),
            deployment_registry_version="registry-1",
            policy_version="1.1.2",
        )

    def make_intent(self):
        return ExecutionIntent(
            schema_version="1.1.0",
            risk_decision_id=self.risk.risk_decision_id,
            target_id=self.target.target_id,
            instrument_id=self.target.instrument_id,
            exchange_position_before=Decimal("0"),
            desired_position=Decimal("0.01"),
            delta_quantity=Decimal("0.01"),
            reduce_only=False,
            order_policy=OrderPolicy.AGGRESSIVE_LIMIT,
            max_slippage_bps=Decimal("8"),
            deadline=NOW + timedelta(minutes=5),
            created_at=NOW,
            intent_status=IntentStatus.PLANNED,
            instrument_metadata_version="binance-ethusdt-1",
        )

    def test_intent_idempotency_and_full_lineage(self) -> None:
        intent = self.make_intent()
        intent.assert_lineage(
            target=self.target,
            risk_decision=self.risk,
            execution_reference_price_usdt=Decimal("1800"),
        )
        self.assertEqual(len({intent.intent_id for _ in range(100)}), 1)
        self.assertEqual(len({intent.idempotency_key for _ in range(100)}), 1)
        with self.assertRaises(ContractError):
            replace(
                intent,
                desired_position=Decimal("0.02"),
                delta_quantity=Decimal("0.02"),
            ).assert_lineage(
                target=self.target,
                risk_decision=self.risk,
                execution_reference_price_usdt=Decimal("1800"),
            )
        with self.assertRaises(ContractError):
            replace(
                intent,
                exchange_position_before=Decimal("0.01"),
                desired_position=Decimal("-0.01"),
                delta_quantity=Decimal("-0.02"),
                reduce_only=True,
            )

    def test_attempt_chain_blocks_blind_retry_until_predecessor_resolved(self) -> None:
        intent = self.make_intent()
        first = ChildOrderAttempt(
            schema_version="1.1.0",
            intent_id=intent.intent_id,
            attempt_no=1,
            planned_quantity=Decimal("0.01"),
            planned_price_or_market=Decimal("1800"),
            created_reason=AttemptReason.INITIAL,
            supersedes_attempt_id_or_null=None,
        )
        second = ChildOrderAttempt(
            schema_version="1.1.0",
            intent_id=intent.intent_id,
            attempt_no=2,
            planned_quantity=Decimal("0.004"),
            planned_price_or_market=Decimal("1801"),
            created_reason=AttemptReason.RESIDUAL,
            supersedes_attempt_id_or_null=first.attempt_id,
        )
        book = AttemptBook()
        book.register(
            first,
            predecessor_terminal=False,
            predecessor_residual_reconciled=False,
            remaining_intent_quantity=Decimal("0.01"),
        )
        with self.assertRaises(ContractError):
            book.register(
                second,
                predecessor_terminal=False,
                predecessor_residual_reconciled=False,
                remaining_intent_quantity=Decimal("0.004"),
            )
        book.register(
            second,
            predecessor_terminal=True,
            predecessor_residual_reconciled=False,
            remaining_intent_quantity=Decimal("0.004"),
        )
        oversized = replace(
            second,
            planned_quantity=Decimal("0.005"),
        )
        with self.assertRaises(ContractError):
            AttemptBook().register(
                oversized,
                predecessor_terminal=False,
                predecessor_residual_reconciled=False,
                remaining_intent_quantity=Decimal("0.004"),
            )
        self.assertEqual(len(book.chain(intent.intent_id)), 2)
        self.assertEqual(first.client_order_id, first.client_order_id)
        self.assertLessEqual(len(first.client_order_id), 36)


if __name__ == "__main__":
    unittest.main()
