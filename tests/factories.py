from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from crypto_quant.canonical import business_hash, canonical_decimal
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
from crypto_quant.economics import economic_snapshot_hash
from crypto_quant.execution import (
    DeploymentRegistryRecord,
    RegistryStatus,
)
from crypto_quant.statistics import statistical_series_hash

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


def _fixture_time(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def complete_trade_replay_inputs(
    *,
    trade_pnls=("10", "9", "8", "7", "6", "5"),
    block_length=2,
    minimum_block_count=2,
):
    scope_identity = {
        "account_id": "account-replay",
        "evaluation_ledger": "BASELINE_LEDGER",
        "release_route": "BASELINE_ONLY",
        "direction": "LONG",
        "venue": "BINANCE_SPOT",
        "recipe_release_id": "recipe-replay",
        "recipe_release_hash": "1" * 64,
        "deployment_line_id": "line-replay",
        "deployment_line_hash": "2" * 64,
    }
    economic_snapshots = []
    observations = []
    valuation_checkpoints = []
    initial = datetime(2026, 1, 1, tzinfo=timezone.utc)
    running_equity = Decimal("1000")
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        for index, pnl_text in enumerate(trade_pnls, start=1):
            sequence_offset = (index - 1) * 4
            pnl = Decimal(pnl_text)
            start = initial + timedelta(days=index - 1)
            end = start + timedelta(days=1)
            buy_time = start + timedelta(hours=6)
            sell_time = start + timedelta(hours=18)
            start_text = _fixture_time(start)
            end_text = _fixture_time(end)
            buy_text = _fixture_time(buy_time)
            sell_text = _fixture_time(sell_time)
            source_scope = {
                **scope_identity,
                "evaluation_window_start": start_text,
                "evaluation_window_end": end_text,
            }
            starting_equity = running_equity
            ending_equity = starting_equity + pnl
            snapshot = {
                "$schema": "./economic-ledger-snapshot-v1.schema.json",
                "schema_version": "1.1.0",
                "snapshot_id": f"economic-replay-{index}",
                "snapshot_hash": "0" * 64,
                "hash_algorithm": "SHA-256",
                "canonicalization": "RFC8785_JCS",
                "source_ledger_hash": business_hash(
                    {"period": index, "source": "ledger"}
                ),
                "source_projection_hash": business_hash(
                    {"period": index, "source": "projection"}
                ),
                "accounting_policy_id": "accounting-replay",
                "accounting_policy_hash": "3" * 64,
                "cost_allocation_policy_id": "cost-replay",
                "cost_allocation_policy_hash": "4" * 64,
                "scope": source_scope,
                "reporting_asset": "USDT",
                "window_event_convention": (
                    "START_EXCLUSIVE_END_INCLUSIVE"
                ),
                "starting_liquidation_equity_usdt": canonical_decimal(
                    starting_equity
                ),
                "ending_liquidation_equity_usdt": canonical_decimal(
                    ending_equity
                ),
                "opening_positions": [],
                "fills": [
                    {
                        "fill_id": f"fill-{index}-open",
                        "exchange_trade_id": f"exchange-{index}-open",
                        "local_order_id": f"order-{index}-open",
                        "venue_order_id": f"venue-{index}-open",
                        "source_event_sequence": sequence_offset + 2,
                        "instrument_id": "BINANCE:SPOT:BTCUSDT",
                        "side": "BUY",
                        "quantity": "1",
                        "price": "100",
                        "contract_multiplier": "1",
                        "fee_value_usdt": "0",
                        "implementation_shortfall_usdt": "0",
                        "exchange_event_time": buy_text,
                    },
                    {
                        "fill_id": f"fill-{index}-close",
                        "exchange_trade_id": f"exchange-{index}-close",
                        "local_order_id": f"order-{index}-close",
                        "venue_order_id": f"venue-{index}-close",
                        "source_event_sequence": sequence_offset + 3,
                        "instrument_id": "BINANCE:SPOT:BTCUSDT",
                        "side": "SELL",
                        "quantity": "1",
                        "price": canonical_decimal(
                            Decimal("100") + pnl
                        ),
                        "contract_multiplier": "1",
                        "fee_value_usdt": "0",
                        "implementation_shortfall_usdt": "0",
                        "exchange_event_time": sell_text,
                    },
                ],
                "funding_cashflows": [],
                "external_cash_flows": [],
                "allocated_costs": [],
                "equity_points": [
                    {
                        "equity_snapshot_id": f"equity-{index}-start",
                        "source_event_sequence": sequence_offset + 1,
                        "as_of": start_text,
                        "marked_equity_usdt": canonical_decimal(
                            starting_equity
                        ),
                        "liquidation_equity_usdt": canonical_decimal(
                            starting_equity
                        ),
                        "spot_notional_usdt": "0",
                        "perp_notional_usdt": "0",
                        "active_order_risk_increasing_notional_usdt": "0",
                        "active_order_unknown_notional_usdt": "0",
                        "expected_exit_fee_accrued_usdt": "0",
                        "conservative_close_verified": True,
                        "is_utc_day_start": True,
                        "position_cost_bases": [],
                    },
                    {
                        "equity_snapshot_id": f"equity-{index}-end",
                        "source_event_sequence": sequence_offset + 4,
                        "as_of": end_text,
                        "marked_equity_usdt": canonical_decimal(
                            ending_equity
                        ),
                        "liquidation_equity_usdt": canonical_decimal(
                            ending_equity
                        ),
                        "spot_notional_usdt": "0",
                        "perp_notional_usdt": "0",
                        "active_order_risk_increasing_notional_usdt": "0",
                        "active_order_unknown_notional_usdt": "0",
                        "expected_exit_fee_accrued_usdt": "0",
                        "conservative_close_verified": True,
                        "is_utc_day_start": True,
                        "position_cost_bases": [],
                    },
                ],
                "generated_at": end_text,
                "replay_verified": True,
            }
            snapshot["snapshot_hash"] = economic_snapshot_hash(snapshot)
            economic_snapshots.append(snapshot)
            growth = (ending_equity / starting_equity).ln()
            observations.append(
                {
                    "observation_id": f"observation-{index}",
                    "period_start": start_text,
                    "period_end": end_text,
                    "value": canonical_decimal(growth),
                    "calendar_month_complete": False,
                    "source_economic_snapshot_hash": snapshot[
                        "snapshot_hash"
                    ],
                    "fold_id": f"fold-{index}",
                }
            )
            for point in snapshot["equity_points"]:
                valuation_checkpoints.append(
                    {
                        "source_economic_snapshot_hash": snapshot[
                            "snapshot_hash"
                        ],
                        "equity_snapshot_id": point["equity_snapshot_id"],
                        "as_of": point["as_of"],
                        "instruments": [],
                    }
                )
            running_equity = ending_equity
    source_series = {
        "$schema": "./statistical-series-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "series_id": "series-complete-trades",
        "series_hash": "0" * 64,
        "hash_algorithm": "SHA-256",
        "canonicalization": "RFC8785_JCS",
        "source_economic_snapshot_hashes": [
            snapshot["snapshot_hash"] for snapshot in economic_snapshots
        ],
        "accounting_policy_id": "accounting-replay",
        "accounting_policy_hash": "3" * 64,
        "cost_allocation_policy_id": "cost-replay",
        "cost_allocation_policy_hash": "4" * 64,
        "split_policy_id": "split-replay",
        "split_policy_hash": "5" * 64,
        "statistical_design_policy_id": "statistics-replay",
        "statistical_design_policy_hash": "6" * 64,
        "experiment_manifest_id": "experiment-replay",
        "experiment_manifest_hash": "7" * 64,
        "scope": {
            **scope_identity,
            "evaluation_window_start": observations[0]["period_start"],
            "evaluation_window_end": observations[-1]["period_end"],
        },
        "approved_production_capital_usdt": "1000",
        "capital_normalization": "APPROVED_CAPITAL_EVALUATION_WINDOW",
        "series_kind": "PRIMARY_ENDPOINT_CONTRIBUTION",
        "aggregation": "SUM",
        "observations": observations,
        "bootstrap_design": {
            "block_length": block_length,
            "minimum_block_count": minimum_block_count,
            "resample_count": 1000,
            "seed": 19,
            "confidence_level": "0.95",
            "confidence_side": "LOWER_ONE_SIDED",
            "sampling_rule": (
                "OVERLAPPING_NON_CIRCULAR_MBB_TRUNCATE_TO_N"
            ),
            "quantile_rule": "CONSERVATIVE_NEAREST_RANK_V1",
        },
        "generated_at": observations[-1]["period_end"],
        "replay_verified": True,
    }
    source_series["series_hash"] = statistical_series_hash(source_series)
    return source_series, economic_snapshots, valuation_checkpoints


def statistical_decision_inputs(
    *,
    current_values=("4", "5", "6", "7", "8", "9"),
    competitor_values=("1", "1", "2", "1", "2", "1"),
    include_aborted=True,
    block_length=2,
    minimum_block_count=2,
    resample_count=1000,
    seed=29,
):
    """Return a deterministic cumulative family and frozen design."""

    window_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    window_end = datetime(2025, 1, 7, tzinfo=timezone.utc)
    common_scope = {
        "account_id": "account-statistical-decision",
        "evaluation_ledger": "BASELINE_LEDGER",
        "release_route": "BASELINE_ONLY",
        "direction": "LONG",
        "venue": "BINANCE_SPOT",
        "deployment_line_id": "line-statistical-decision",
        "deployment_line_hash": "a" * 64,
        "evaluation_window_start": window_start.isoformat().replace(
            "+00:00", "Z"
        ),
        "evaluation_window_end": window_end.isoformat().replace(
            "+00:00", "Z"
        ),
    }
    design = {
        "minimum_economic_effect": "2",
        "null_boundary": "0",
        "confidence_level": "0.95",
        "confidence_side": "TWO_SIDED",
        "ci_method": "PERCENTILE_MBB_V1",
        "raw_p_value_method": "CENTERED_MBB_GREATER_ADD_ONE_V1",
        "power_method": "SHIFTED_CENTERED_MBB_AT_MERE_V1",
        "effective_sample_method": (
            "GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1"
        ),
        "multiple_testing_method": "HOLM_V1",
        "family_wise_alpha": "0.05",
        "block_length": block_length,
        "minimum_block_count": minimum_block_count,
        "resample_count": resample_count,
        "seed": seed,
        "sampling_rule": (
            "OVERLAPPING_NON_CIRCULAR_MBB_TRUNCATE_TO_N"
        ),
        "quantile_rule": "CONSERVATIVE_NEAREST_RANK_V1",
    }

    def series(candidate_id, recipe_hash, values):
        period_seconds = int((window_end - window_start).total_seconds())
        observations = []
        source_hashes = []
        for index, value in enumerate(values):
            start = window_start + timedelta(
                seconds=period_seconds * index // len(values)
            )
            end = window_start + timedelta(
                seconds=period_seconds * (index + 1) // len(values)
            )
            source_hash = business_hash(
                {"candidate_id": candidate_id, "index": index}
            )
            source_hashes.append(source_hash)
            observations.append(
                {
                    "observation_id": f"{candidate_id}-observation-{index}",
                    "period_start": start.isoformat().replace("+00:00", "Z"),
                    "period_end": end.isoformat().replace("+00:00", "Z"),
                    "value": canonical_decimal(value),
                    "calendar_month_complete": False,
                    "source_economic_snapshot_hash": source_hash,
                    "fold_id": f"fold-{index}",
                }
            )
        result = {
            "$schema": "./statistical-series-snapshot-v1.schema.json",
            "schema_version": "1.0.0",
            "series_id": f"series-{candidate_id}",
            "series_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "source_economic_snapshot_hashes": source_hashes,
            "accounting_policy_id": "accounting-replay",
            "accounting_policy_hash": "3" * 64,
            "cost_allocation_policy_id": "cost-replay",
            "cost_allocation_policy_hash": "4" * 64,
            "split_policy_id": "split-replay",
            "split_policy_hash": "5" * 64,
            "statistical_design_policy_id": "statistics-replay",
            "statistical_design_policy_hash": "6" * 64,
            "experiment_manifest_id": "experiment-replay",
            "experiment_manifest_hash": "7" * 64,
            "scope": {
                **common_scope,
                "recipe_release_id": f"recipe-{candidate_id}",
                "recipe_release_hash": recipe_hash,
            },
            "approved_production_capital_usdt": "1000",
            "capital_normalization": (
                "APPROVED_CAPITAL_EVALUATION_WINDOW"
            ),
            "series_kind": "PRIMARY_ENDPOINT_CONTRIBUTION",
            "aggregation": "SUM",
            "observations": observations,
            "bootstrap_design": {
                "block_length": block_length,
                "minimum_block_count": minimum_block_count,
                "resample_count": resample_count,
                "seed": seed,
                "confidence_level": "0.95",
                "confidence_side": "LOWER_ONE_SIDED",
                "sampling_rule": (
                    "OVERLAPPING_NON_CIRCULAR_MBB_TRUNCATE_TO_N"
                ),
                "quantile_rule": "CONSERVATIVE_NEAREST_RANK_V1",
            },
            "generated_at": common_scope["evaluation_window_end"],
            "replay_verified": True,
        }
        result["series_hash"] = statistical_series_hash(result)
        return result

    candidates = (
        (
            "candidate-current",
            "b" * 64,
            tuple(current_values),
        ),
        (
            "candidate-competitor",
            "c" * 64,
            tuple(competitor_values),
        ),
    )
    registry = []
    for candidate_id, recipe_hash, values in candidates:
        source = series(candidate_id, recipe_hash, values)
        registry.append(
            {
                "candidate_id": candidate_id,
                "candidate_status": "EVALUATED",
                "recipe_release_id": f"recipe-{candidate_id}",
                "recipe_release_hash": recipe_hash,
                "source_series_snapshot": source,
                "source_series_hash": source["series_hash"],
            }
        )
    if include_aborted:
        registry.append(
            {
                "candidate_id": "candidate-aborted",
                "candidate_status": "ABORTED",
                "recipe_release_id": "recipe-candidate-aborted",
                "recipe_release_hash": "d" * 64,
                "source_series_snapshot": None,
                "source_series_hash": None,
            }
        )
    registry.sort(key=lambda item: item["candidate_id"])
    registry_projection = [
        {
            "candidate_id": item["candidate_id"],
            "candidate_status": item["candidate_status"],
            "recipe_release_id": item["recipe_release_id"],
        }
        for item in registry
    ]
    scope = {
        **{
            name: common_scope[name]
            for name in (
                "account_id",
                "evaluation_ledger",
                "release_route",
                "direction",
                "venue",
                "deployment_line_id",
                "deployment_line_hash",
                "evaluation_window_start",
                "evaluation_window_end",
            )
        },
        "approved_production_capital_usdt": "1000",
        "endpoint_id": "PRIMARY_NET_GROWTH",
        "endpoint_unit": "log_growth",
        "endpoint_direction": "GREATER",
    }
    return {
        "scope": scope,
        "design": design,
        "trial_registry": registry,
        "trial_family_id": "trial-family-statistical-decision",
        "current_candidate_id": "candidate-current",
        "expected_actual_total_trials": len(registry),
        "expected_trial_registry_hash": business_hash(registry_projection),
    }


def make_statistical_decision_snapshot(**fixture_overrides):
    from crypto_quant.statistical_decision import (
        build_statistical_decision_snapshot,
    )

    return build_statistical_decision_snapshot(
        snapshot_id="statistical-decision-fixture",
        release_gate_policy_id="release-gates-v1.1",
        release_gate_policy_version="1.1.5",
        metric_catalog_id="release-metrics-v1.1",
        metric_catalog_version="1.1.5",
        statistical_design_policy_id="statistics-replay",
        statistical_design_policy_hash="6" * 64,
        experiment_manifest_id="experiment-replay",
        experiment_manifest_hash="7" * 64,
        generated_at="2025-01-07T00:00:00Z",
        **statistical_decision_inputs(**fixture_overrides),
    )
