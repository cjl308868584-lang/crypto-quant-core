from datetime import datetime, timedelta, timezone
from decimal import Decimal

from crypto_quant.contracts import (
    DecisionSource,
    DeploymentStage,
    Direction,
    MetaDecision,
    PortfolioRiskSnapshot,
    StrategyProposal,
    StrategyRole,
    TargetAction,
    TargetPosition,
)
from crypto_quant.decimal_math import RiskRatio
from crypto_quant.execution import (
    DeploymentRegistryRecord,
    RegistryStatus,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
HASH = "a" * 64


def make_proposal(
    *,
    role=StrategyRole.BASE,
    direction=Direction.LONG,
    instrument_id="BINANCE:SPOT:ETHUSDT",
):
    return StrategyProposal(
        schema_version="1.1.0",
        market_snapshot_id="market-1",
        feature_snapshot_id="feature-1",
        strategy_id="trend-breakout",
        strategy_version="1.0.0",
        strategy_role=role,
        instrument_id=instrument_id,
        direction=direction,
        raw_strength=Decimal("0.7"),
        reason_codes=("BREAKOUT",),
        expected_horizon_hours=24,
        minimum_hold_hours=8,
        valid_until=NOW + timedelta(hours=24),
        created_at=NOW,
    )


def make_meta(
    proposal,
    *,
    action=TargetAction.SET_TARGET,
    bucket="0.25",
    eligible=True,
):
    return MetaDecision(
        schema_version="1.1.0",
        proposal_id=proposal.proposal_id,
        decision_source=DecisionSource.NO_AI_BASE,
        no_ai_base_version_or_null="no-ai-base-1",
        model_id_or_null=None,
        model_version_or_null=None,
        deployment_stage=DeploymentStage.CHAMPION,
        calibration_version_or_null=None,
        p_net_positive_or_null=None,
        expected_net_return_or_null=None,
        return_q10_or_null=None,
        return_q50_or_null=None,
        return_q90_or_null=None,
        uncertainty_score_or_null=None,
        ood_score_or_null=None,
        eligible=eligible,
        ineligibility_reason_mask=() if eligible else ("RISK_LOCKED",),
        recommended_action=action,
        recommended_bucket_or_null=None if bucket is None else RiskRatio(bucket),
        model_input_hash=HASH,
        prediction_hash=HASH,
        hard_risk_authorized=action is TargetAction.FLATTEN,
    )


def make_target(
    proposal,
    meta,
    *,
    sequence=1,
    supersedes=None,
    base_exposure="0.8",
    target_notional="100",
):
    action = meta.recommended_action
    if action in (TargetAction.SET_TARGET, TargetAction.REDUCE_TO):
        bucket = meta.recommended_bucket_or_null
        sign = Decimal("-1") if proposal.direction is Direction.SHORT else Decimal("1")
        ratio = sign * Decimal(base_exposure) * bucket.value
        notional = Decimal(target_notional)
        direction = proposal.direction
    elif action is TargetAction.FLATTEN:
        bucket = RiskRatio("0")
        ratio = Decimal("0")
        notional = Decimal("0")
        direction = Direction.FLAT
    else:
        bucket = None
        ratio = None
        notional = None
        direction = proposal.direction
    return TargetPosition(
        schema_version="1.1.0",
        target_sequence=sequence,
        supersedes_target_id_or_null=supersedes,
        instrument_id=proposal.instrument_id,
        account_id="account-1",
        target_action=action,
        direction=direction,
        signed_target_ratio_or_null=ratio,
        risk_bucket_or_null=bucket,
        base_volatility_exposure=RiskRatio(base_exposure),
        target_notional_usdt_or_null=notional,
        volatility_target=Decimal("0.12"),
        volatility_estimator_version="ewma-1",
        decision_time=NOW,
        valid_until=NOW + timedelta(hours=24),
        minimum_hold_until=NOW + timedelta(hours=8),
        hysteresis_state="STABLE",
        source_proposal_id=proposal.proposal_id,
        source_meta_decision_id=meta.meta_decision_id,
        position_policy_version="position-policy-1",
    )


def make_snapshot(
    *,
    net_exposure="10",
    gross_exposure="10",
    active_order_exposure="0",
    equity="500",
    deployable_capital="500",
    daily_loss="0",
    drawdown="0",
    unresolved=0,
    clean=True,
):
    gross = Decimal(gross_exposure)
    active = Decimal(active_order_exposure)
    marked_equity = Decimal(equity)
    worst = gross + active
    return PortfolioRiskSnapshot(
        schema_version="1.1.0",
        portfolio_risk_snapshot_id="risk-snapshot-1",
        account_id="account-1",
        exchange_snapshot_time=NOW,
        marked_equity_usdt=marked_equity,
        available_balance_usdt=Decimal(deployable_capital),
        actual_deployable_capital_usdt=Decimal(deployable_capital),
        net_eth_exposure_usdt=Decimal(net_exposure),
        gross_eth_exposure_usdt=gross,
        active_orders_max_potential_fill_usdt=active,
        worst_case_gross_exposure_usdt=worst,
        margin_used_usdt=Decimal("0"),
        effective_leverage=worst / marked_equity,
        daily_loss_ratio=Decimal(daily_loss),
        current_drawdown=RiskRatio(drawdown),
        instrument_metadata_versions=("binance-ethusdt-1",),
        unresolved_order_count=unresolved,
        reconciliation_clean=clean,
    )


def make_deployment(
    *,
    stage=DeploymentStage.CANARY_25,
    multiplier="0.25",
    direction=Direction.LONG,
):
    return DeploymentRegistryRecord(
        schema_version="1.1.0",
        deployment_line_id="line-1",
        release_route="BASELINE_ONLY",
        recipe_release_id="recipe-1",
        recipe_release_hash=HASH,
        direction=direction,
        venue="BINANCE",
        stage=stage,
        authoritative_stage_multiplier=RiskRatio(multiplier),
        approved_production_capital_usdt=Decimal("500"),
        break_even_capital_lcb_root_usdt=Decimal("300"),
        actual_deployable_capital_usdt_at_approval=Decimal("500"),
        capital_gate_evidence_hash=HASH,
        active_model_bundle_id_or_no_ai_base_version="no-ai-base-1",
        approved_fallback_record_id_or_null=None,
        effective_from=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=30),
        release_gate_policy_hash=HASH,
        required_policy_bundle_hash=HASH,
        approval_evidence_hash=HASH,
        status=RegistryStatus.ACTIVE,
    )
