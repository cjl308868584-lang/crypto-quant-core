"""Replayable paired risk paths over trusted economic snapshots."""

import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from functools import wraps
from typing import Any, Callable, Dict, Mapping, Sequence, Tuple, TypeVar

from .canonical import business_hash, canonical_decimal, stable_id
from .economics import (
    economic_snapshot_reasons,
)
from .errors import CanonicalizationError
from .evidence import artifact_self_hash
from .statistics import statistical_series_reasons

_Result = TypeVar("_Result")


def _fixed_decimal_context(
    function: Callable[..., _Result],
) -> Callable[..., _Result]:
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> _Result:
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            return function(*args, **kwargs)

    return wrapped


def paired_risk_evaluation_snapshot_hash(
    snapshot: Mapping[str, Any],
) -> str:
    return artifact_self_hash(snapshot, "snapshot_hash")


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp is not timezone aware")
    return parsed.astimezone(timezone.utc)


def _decimal(value: Any) -> Decimal:
    return Decimal(canonical_decimal(value))


def _require_id(value: Any, name: str) -> None:
    if not isinstance(value, str) or re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
        value,
    ) is None:
        raise ValueError(f"{name} is not a canonical ID")


def _require_hash(value: Any, name: str) -> None:
    if not isinstance(value, str) or re.fullmatch(
        r"[a-f0-9]{64}",
        value,
    ) is None:
        raise ValueError(f"{name} is not a SHA-256 digest")


def _segment_returns(snapshot: Mapping[str, Any]) -> Tuple[str, ...]:
    returns = []
    points = snapshot["equity_points"]
    for previous, current in zip(points, points[1:]):
        start = _timestamp(previous["as_of"])
        end = _timestamp(current["as_of"])
        starting_equity = _decimal(previous["liquidation_equity_usdt"])
        external = sum(
            (
                _decimal(item["signed_amount_usdt"])
                for item in snapshot["external_cash_flows"]
                if start < _timestamp(item["occurred_at"]) <= end
            ),
            Decimal("0"),
        )
        costs = sum(
            (
                _decimal(item["amount_usdt"])
                for item in snapshot["allocated_costs"]
                if start < _timestamp(item["occurred_at"]) <= end
            ),
            Decimal("0"),
        )
        adjusted_end = (
            _decimal(current["liquidation_equity_usdt"])
            - external
            - costs
        )
        if starting_equity <= 0 or adjusted_end <= 0:
            raise ValueError("economic equity is nonpositive")
        returns.append(canonical_decimal((adjusted_end / starting_equity).ln()))
    if not returns:
        raise ValueError("economic snapshot has no return interval")
    return tuple(returns)


def _pair_key(observation: Mapping[str, Any]) -> Tuple[str, str]:
    proposal_id = observation["proposal_id"]
    decision_time = observation["decision_time"]
    _require_id(proposal_id, "proposal_id")
    _timestamp(decision_time)
    return proposal_id, decision_time


def _unpaired(observation: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "observation_id": observation["observation_id"],
        "proposal_id": observation["proposal_id"],
        "decision_time": observation["decision_time"],
        "source_economic_snapshot_hash": observation[
            "source_economic_snapshot_hash"
        ],
    }


def _derive_pairs(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    economic_by_hash: Mapping[str, Mapping[str, Any]],
) -> Tuple[Sequence[Dict[str, Any]], Dict[str, Any]]:
    indexes = []
    for series in (reference, candidate):
        index = {}
        for observation in series["observations"]:
            key = _pair_key(observation)
            if key in index:
                raise ValueError("duplicate paired-risk key")
            index[key] = observation
        indexes.append(index)
    reference_index, candidate_index = indexes
    matched = sorted(
        set(reference_index) & set(candidate_index),
        key=lambda item: (_timestamp(item[1]), item[0]),
    )
    if not matched:
        raise ValueError("paired risk has no matched observations")
    segments = []
    for key in matched:
        reference_observation = reference_index[key]
        candidate_observation = candidate_index[key]
        for field in ("period_start", "period_end", "fold_id"):
            if reference_observation[field] != candidate_observation[field]:
                raise ValueError(f"paired observations disagree on {field}")
        reference_source = economic_by_hash[
            reference_observation["source_economic_snapshot_hash"]
        ]
        candidate_source = economic_by_hash[
            candidate_observation["source_economic_snapshot_hash"]
        ]
        reference_returns = _segment_returns(reference_source)
        candidate_returns = _segment_returns(candidate_source)
        if sum(map(_decimal, reference_returns), Decimal("0")) != _decimal(
            reference_observation["value"]
        ):
            raise ValueError("reference observation growth mismatch")
        if sum(map(_decimal, candidate_returns), Decimal("0")) != _decimal(
            candidate_observation["value"]
        ):
            raise ValueError("candidate observation growth mismatch")
        action_changed = (
            reference_observation["recommended_action"]
            != candidate_observation["recommended_action"]
        )
        exposure_changed = _decimal(
            reference_observation["absolute_exposure_ratio"]
        ) != _decimal(candidate_observation["absolute_exposure_ratio"])
        proposal_id, decision_time = key
        segments.append(
            {
                "segment_id": stable_id(
                    "riskseg",
                    {
                        "proposal_id": proposal_id,
                        "decision_time": decision_time,
                    },
                ),
                "proposal_id": proposal_id,
                "decision_time": decision_time,
                "fold_id": reference_observation["fold_id"],
                "period_start": reference_observation["period_start"],
                "period_end": reference_observation["period_end"],
                "reference_observation_id": reference_observation[
                    "observation_id"
                ],
                "candidate_observation_id": candidate_observation[
                    "observation_id"
                ],
                "reference_series_hash": reference["series_hash"],
                "candidate_series_hash": candidate["series_hash"],
                "reference_source_economic_snapshot_hash": (
                    reference_source["snapshot_hash"]
                ),
                "candidate_source_economic_snapshot_hash": (
                    candidate_source["snapshot_hash"]
                ),
                "reference_log_returns": list(reference_returns),
                "candidate_log_returns": list(candidate_returns),
                "action_changed": action_changed,
                "absolute_exposure_changed": exposure_changed,
                "changed": action_changed or exposure_changed,
            }
        )
    reference_only = sorted(
        set(reference_index) - set(candidate_index),
        key=lambda item: (_timestamp(item[1]), item[0]),
    )
    candidate_only = sorted(
        set(candidate_index) - set(reference_index),
        key=lambda item: (_timestamp(item[1]), item[0]),
    )
    changed = sum(segment["changed"] for segment in segments)
    report = {
        "reference_observation_count": len(reference_index),
        "candidate_observation_count": len(candidate_index),
        "matched_pair_count": len(segments),
        "changed_pair_count": changed,
        "unchanged_pair_count": len(segments) - changed,
        "unpaired_reference_count": len(reference_only),
        "unpaired_candidate_count": len(candidate_only),
        "unpaired_reference": [
            _unpaired(reference_index[key]) for key in reference_only
        ],
        "unpaired_candidate": [
            _unpaired(candidate_index[key]) for key in candidate_only
        ],
    }
    return segments, report


def _role_reasons(
    comparison_role: Any,
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> Tuple[str, ...]:
    expected = {
        "AI_VS_RECIPE_BASELINE": (
            ("RECIPE_BASELINE", "RECIPE_RELEASE", "BASELINE_LEDGER"),
            ("AI_CANDIDATE", "MODEL_BUNDLE", "AI_LEDGER"),
        ),
        "MINOR_CANDIDATE_VS_ACTIVE_BUNDLE": (
            ("ACTIVE_BUNDLE", "MODEL_BUNDLE", "AI_LEDGER"),
            ("MINOR_CANDIDATE", "MODEL_BUNDLE", "AI_LEDGER"),
        ),
    }
    if comparison_role not in expected:
        return ("PAIRED_RISK_COMPARISON_ROLE_INVALID",)
    reasons = []
    for arm, identity, required in (
        (reference, expected[comparison_role][0], "reference"),
        (candidate, expected[comparison_role][1], "candidate"),
    ):
        role, subject_type, ledger = identity
        if (
            arm.get("role") != role
            or arm.get("subject_type") != subject_type
            or arm.get("statistical_series_snapshot", {})
            .get("scope", {})
            .get("evaluation_ledger")
            != ledger
        ):
            reasons.append(f"PAIRED_RISK_ARM_ROLE_INVALID:{required}")
    return tuple(reasons)


@_fixed_decimal_context
def paired_risk_evaluation_snapshot_reasons(
    snapshot: Mapping[str, Any],
) -> Tuple[str, ...]:
    reasons = []
    try:
        computed_hash = paired_risk_evaluation_snapshot_hash(snapshot)
    except CanonicalizationError:
        computed_hash = ""
        reasons.append("PAIRED_RISK_NOT_CANONICAL")
    if snapshot.get("snapshot_hash") != computed_hash:
        reasons.append("PAIRED_RISK_SELF_HASH_MISMATCH")
    if snapshot.get("replay_verified") is not True:
        reasons.append("PAIRED_RISK_REPLAY_UNVERIFIED")
    if snapshot.get("ai_endpoint") != "RISK_EFFICIENCY":
        reasons.append("PAIRED_RISK_ENDPOINT_INVALID")
    reference = snapshot.get("reference_arm")
    candidate = snapshot.get("candidate_arm")
    if not isinstance(reference, Mapping) or not isinstance(
        candidate,
        Mapping,
    ):
        return tuple(sorted(set(reasons + ["PAIRED_RISK_ARMS_INVALID"])))
    reasons.extend(
        _role_reasons(snapshot.get("comparison_role"), reference, candidate)
    )
    series = []
    for arm in (reference, candidate):
        source = arm.get("statistical_series_snapshot")
        if not isinstance(source, Mapping) or statistical_series_reasons(
            source
        ):
            reasons.append("PAIRED_RISK_SOURCE_SERIES_INVALID")
        else:
            series.append(source)
    economics = snapshot.get("economic_snapshots")
    if not isinstance(economics, list):
        reasons.append("PAIRED_RISK_ECONOMIC_SOURCES_INVALID")
        economics = []
    economic_by_hash = {}
    for source in economics:
        if not isinstance(source, Mapping) or economic_snapshot_reasons(source):
            reasons.append("PAIRED_RISK_ECONOMIC_SOURCE_INVALID")
            continue
        digest = source["snapshot_hash"]
        if digest in economic_by_hash:
            reasons.append("PAIRED_RISK_ECONOMIC_SOURCE_DUPLICATE")
        economic_by_hash[digest] = source
    declared = snapshot.get("source_economic_snapshot_hashes")
    actual = [
        source.get("snapshot_hash")
        for source in economics
        if isinstance(source, Mapping)
    ]
    if declared != actual:
        reasons.append("PAIRED_RISK_SOURCE_SEQUENCE_MISMATCH")
    if len(series) == 2:
        reference_series, candidate_series = series
        common_fields = (
            "accounting_policy_id",
            "accounting_policy_hash",
            "cost_allocation_policy_id",
            "cost_allocation_policy_hash",
            "split_policy_id",
            "split_policy_hash",
            "statistical_design_policy_id",
            "statistical_design_policy_hash",
            "experiment_manifest_id",
            "experiment_manifest_hash",
            "approved_production_capital_usdt",
            "capital_normalization",
            "aggregation",
            "bootstrap_design",
        )
        for field in common_fields:
            if business_hash(reference_series.get(field)) != business_hash(
                candidate_series.get(field)
            ):
                reasons.append(f"PAIRED_RISK_ARM_SETTING_MISMATCH:{field}")
        outer_fields = (
            "accounting_policy_id",
            "accounting_policy_hash",
            "cost_allocation_policy_id",
            "cost_allocation_policy_hash",
            "split_policy_id",
            "split_policy_hash",
            "statistical_design_policy_id",
            "statistical_design_policy_hash",
            "experiment_manifest_id",
            "experiment_manifest_hash",
            "approved_production_capital_usdt",
            "bootstrap_design",
        )
        for field in outer_fields:
            if business_hash(snapshot.get(field)) != business_hash(
                candidate_series.get(field)
            ):
                reasons.append(f"PAIRED_RISK_OUTER_SETTING_MISMATCH:{field}")
        common_scope = (
            "account_id",
            "release_route",
            "direction",
            "venue",
            "deployment_line_id",
            "deployment_line_hash",
            "evaluation_window_start",
            "evaluation_window_end",
        )
        for field in common_scope:
            if (
                reference_series["scope"].get(field)
                != candidate_series["scope"].get(field)
            ):
                reasons.append(f"PAIRED_RISK_ARM_SCOPE_MISMATCH:{field}")
        expected_hashes = (
            reference_series["source_economic_snapshot_hashes"]
            + candidate_series["source_economic_snapshot_hashes"]
        )
        if declared != expected_hashes:
            reasons.append("PAIRED_RISK_SOURCE_SEQUENCE_MISMATCH")
        try:
            expected_segments, expected_report = _derive_pairs(
                reference_series,
                candidate_series,
                economic_by_hash,
            )
        except (KeyError, TypeError, ValueError, CanonicalizationError):
            reasons.append("PAIRED_RISK_PAIR_REPLAY_FAILED")
        else:
            if business_hash(snapshot.get("paired_segments")) != business_hash(
                expected_segments
            ):
                reasons.append("PAIRED_RISK_PAIR_REPLAY_MISMATCH")
            if business_hash(snapshot.get("pairing_report")) != business_hash(
                expected_report
            ):
                reasons.append("PAIRED_RISK_REPORT_REPLAY_MISMATCH")
    return tuple(sorted(set(reasons)))


def build_paired_risk_evaluation_snapshot(
    *,
    snapshot_id: str,
    comparison_role: str,
    reference_subject: Mapping[str, Any],
    candidate_subject: Mapping[str, Any],
    reference_series_snapshot: Mapping[str, Any],
    candidate_series_snapshot: Mapping[str, Any],
    economic_snapshots: Sequence[Mapping[str, Any]],
    generated_at: str,
) -> Dict[str, Any]:
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        _require_id(snapshot_id, "snapshot_id")
        _timestamp(generated_at)
        reference = deepcopy(dict(reference_series_snapshot))
        candidate = deepcopy(dict(candidate_series_snapshot))
        economics = [deepcopy(dict(item)) for item in economic_snapshots]
        if statistical_series_reasons(reference) or statistical_series_reasons(
            candidate
        ):
            raise ValueError("source statistical series is invalid")
        for source in economics:
            if economic_snapshot_reasons(source):
                raise ValueError("source economic snapshot is invalid")
        economic_by_hash = {
            source["snapshot_hash"]: source for source in economics
        }
        segments, report = _derive_pairs(
            reference,
            candidate,
            economic_by_hash,
        )
        candidate_scope = candidate["scope"]
        artifact = {
            "$schema": "./paired-risk-evaluation-snapshot-v1.schema.json",
            "schema_version": "1.0.0",
            "snapshot_id": snapshot_id,
            "snapshot_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "comparison_role": comparison_role,
            "ai_endpoint": "RISK_EFFICIENCY",
            "reference_arm": {
                **deepcopy(dict(reference_subject)),
                "statistical_series_snapshot": reference,
            },
            "candidate_arm": {
                **deepcopy(dict(candidate_subject)),
                "statistical_series_snapshot": candidate,
            },
            "economic_snapshots": economics,
            "source_economic_snapshot_hashes": [
                item["snapshot_hash"] for item in economics
            ],
            "pairing_rule": "PROPOSAL_ID_PLUS_DECISION_TIME",
            "pairing_report": report,
            "paired_segments": segments,
            "accounting_policy_id": candidate["accounting_policy_id"],
            "accounting_policy_hash": candidate["accounting_policy_hash"],
            "cost_allocation_policy_id": candidate[
                "cost_allocation_policy_id"
            ],
            "cost_allocation_policy_hash": candidate[
                "cost_allocation_policy_hash"
            ],
            "split_policy_id": candidate["split_policy_id"],
            "split_policy_hash": candidate["split_policy_hash"],
            "statistical_design_policy_id": candidate[
                "statistical_design_policy_id"
            ],
            "statistical_design_policy_hash": candidate[
                "statistical_design_policy_hash"
            ],
            "experiment_manifest_id": candidate["experiment_manifest_id"],
            "experiment_manifest_hash": candidate[
                "experiment_manifest_hash"
            ],
            "scope": {
                **deepcopy(dict(candidate_scope)),
                "evaluation_ledger": "PAIRED_COMPARISON",
            },
            "approved_production_capital_usdt": candidate[
                "approved_production_capital_usdt"
            ],
            "bootstrap_design": deepcopy(candidate["bootstrap_design"]),
            "generated_at": generated_at,
            "replay_verified": True,
        }
        artifact["snapshot_hash"] = paired_risk_evaluation_snapshot_hash(
            artifact
        )
        reasons = paired_risk_evaluation_snapshot_reasons(artifact)
        if reasons:
            raise ValueError(f"invalid paired risk snapshot: {reasons}")
        return artifact


def _max_drawdown(log_returns: Sequence[Decimal]) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        cumulative = Decimal("0")
        peak = Decimal("0")
        maximum = Decimal("0")
        for value in log_returns:
            cumulative += value
            if cumulative > peak:
                peak = cumulative
            drawdown = Decimal("1") - (cumulative - peak).exp()
            maximum = max(maximum, drawdown)
        return +maximum


def _empirical_es95(log_returns: Sequence[Decimal]) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        if not log_returns:
            raise ValueError("ES95 requires at least one return")
        losses = sorted(
            (max(Decimal("0"), -value) for value in log_returns),
            reverse=True,
        )
        tail_count = max(1, (len(losses) * 5 + 99) // 100)
        return +(sum(losses[:tail_count], Decimal("0")) / tail_count)


def _draw_start(
    *,
    seed: int,
    replicate: int,
    draw: int,
    start_count: int,
) -> int:
    modulus = 1 << 256
    acceptance_limit = modulus - modulus % start_count
    attempt = 0
    while True:
        material = (
            "MBB_V1:"
            f"{seed}:{replicate}:{draw}:{start_count}:{attempt}"
        ).encode("ascii")
        candidate = int.from_bytes(hashlib.sha256(material).digest(), "big")
        if candidate < acceptance_limit:
            return candidate % start_count
        attempt += 1


def _validated_risk_snapshot(
    inputs: Mapping[str, Any],
) -> Tuple[Mapping[str, Any], Tuple[str, ...]]:
    snapshot = inputs.get("paired_risk_evaluation_snapshot")
    if not isinstance(snapshot, Mapping):
        return {}, ("PAIRED_RISK_SNAPSHOT_INVALID",)
    reasons = paired_risk_evaluation_snapshot_reasons(snapshot)
    if reasons:
        return {}, reasons
    if snapshot.get("ai_endpoint") != "RISK_EFFICIENCY":
        return {}, ("PAIRED_RISK_ENDPOINT_MISMATCH",)
    report = snapshot["pairing_report"]
    if report["changed_pair_count"] == 0:
        return {}, ("PAIRED_RISK_NO_CHANGED_PAIRS",)
    if (
        report["unpaired_reference_count"] != 0
        or report["unpaired_candidate_count"] != 0
    ):
        return {}, ("PAIRED_RISK_INCOMPLETE_PAIRING",)
    design = snapshot["bootstrap_design"]
    count = len(snapshot["paired_segments"])
    length = design["block_length"]
    if (
        count < length
        or count // length < design["minimum_block_count"]
    ):
        return {}, ("PAIRED_RISK_INSUFFICIENT_BLOCKS",)
    return snapshot, ()


def _paired_risk_lcb(
    snapshot: Mapping[str, Any],
    *,
    statistic: Any,
    zero_reason: str,
) -> Tuple[str, Any, Tuple[str, ...]]:
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        segments = snapshot["paired_segments"]
        observed_reference_returns = tuple(
            _decimal(value)
            for segment in segments
            for value in segment["reference_log_returns"]
        )
        observed_reference = statistic(observed_reference_returns)
        if observed_reference == 0:
            return "INCONCLUSIVE", None, (zero_reason,)
        design = snapshot["bootstrap_design"]
        length = design["block_length"]
        start_count = len(segments) - length + 1
        blocks_per_sample = (len(segments) + length - 1) // length
        replicate_values = []
        for replicate in range(design["resample_count"]):
            sampled_segments = []
            for draw in range(blocks_per_sample):
                start = _draw_start(
                    seed=design["seed"],
                    replicate=replicate,
                    draw=draw,
                    start_count=start_count,
                )
                sampled_segments.extend(segments[start : start + length])
            sampled_segments = sampled_segments[: len(segments)]
            reference_returns = tuple(
                _decimal(value)
                for segment in sampled_segments
                for value in segment["reference_log_returns"]
            )
            candidate_returns = tuple(
                _decimal(value)
                for segment in sampled_segments
                for value in segment["candidate_log_returns"]
            )
            reference_risk = statistic(reference_returns)
            candidate_risk = statistic(candidate_returns)
            replicate_values.append(
                (reference_risk - candidate_risk) / observed_reference
            )
        replicate_values.sort()
        rank = max(1, (design["resample_count"] * 5 + 99) // 100)
        return (
            "COMPUTED",
            canonical_decimal(replicate_values[rank - 1]),
            (),
        )


@_fixed_decimal_context
def paired_max_drawdown_relative_improvement_lcb95(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    snapshot, reasons = _validated_risk_snapshot(inputs)
    if reasons:
        status = (
            "INCONCLUSIVE"
            if reasons[0]
            in {
                "PAIRED_RISK_NO_CHANGED_PAIRS",
                "PAIRED_RISK_INCOMPLETE_PAIRING",
                "PAIRED_RISK_INSUFFICIENT_BLOCKS",
            }
            else "FAIL"
        )
        return status, None, reasons
    return _paired_risk_lcb(
        snapshot,
        statistic=_max_drawdown,
        zero_reason="PAIRED_RISK_REFERENCE_MDD_ZERO",
    )


@_fixed_decimal_context
def paired_es95_relative_improvement_lcb95(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    snapshot, reasons = _validated_risk_snapshot(inputs)
    if reasons:
        status = (
            "INCONCLUSIVE"
            if reasons[0]
            in {
                "PAIRED_RISK_NO_CHANGED_PAIRS",
                "PAIRED_RISK_INCOMPLETE_PAIRING",
                "PAIRED_RISK_INSUFFICIENT_BLOCKS",
            }
            else "FAIL"
        )
        return status, None, reasons
    return _paired_risk_lcb(
        snapshot,
        statistic=_empirical_es95,
        zero_reason="PAIRED_RISK_REFERENCE_ES95_ZERO",
    )
