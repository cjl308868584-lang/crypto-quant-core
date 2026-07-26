"""Replayable multiple-testing, precision, and power decisions."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .canonical import business_hash, canonical_decimal
from .errors import CanonicalizationError
from .evidence import artifact_self_hash
from .statistics import (
    _draw_start,
    _fixed_decimal_context,
    geyer_initial_positive_sequence_ess,
    statistical_series_hash,
    statistical_series_reasons,
)


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_SOURCE_BOOTSTRAP_FIELDS = (
    "block_length",
    "minimum_block_count",
    "resample_count",
    "seed",
    "confidence_level",
    "sampling_rule",
    "quantile_rule",
)
_SCOPE_FIELDS = (
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
_VALID_STATUSES = frozenset(
    {"EVALUATED", "ABORTED", "FAILED", "INVALID"}
)


@dataclass(frozen=True)
class StatisticalDecisionReplay:
    status: str
    reason_codes: Tuple[str, ...]
    family_results: Tuple[Mapping[str, Any], ...] = ()
    current_results: Optional[Mapping[str, Any]] = None


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp is not timezone aware")
    return parsed.astimezone(timezone.utc)


def _decimal(value: Any) -> Decimal:
    return Decimal(canonical_decimal(value))


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and _ID_PATTERN.fullmatch(value) is not None


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH_PATTERN.fullmatch(value) is not None


def _same_value(left: Any, right: Any) -> bool:
    try:
        return business_hash(left) == business_hash(right)
    except CanonicalizationError:
        return False


def statistical_trial_registry_hash(
    trial_registry: Sequence[Mapping[str, Any]],
) -> str:
    projection = [
        {
            "candidate_id": item.get("candidate_id"),
            "candidate_status": item.get("candidate_status"),
            "recipe_release_id": item.get("recipe_release_id"),
            "recipe_release_hash": item.get("recipe_release_hash"),
            "source_series_hash": item.get("source_series_hash"),
        }
        for item in sorted(
            trial_registry,
            key=lambda value: str(value.get("candidate_id", "")),
        )
    ]
    return business_hash(projection)


def statistical_decision_snapshot_hash(
    snapshot: Mapping[str, Any],
) -> str:
    return artifact_self_hash(snapshot, "snapshot_hash")


def _statistic(values: Sequence[Decimal], aggregation: str) -> Decimal:
    total = sum(values, Decimal("0"))
    if aggregation == "SUM":
        return total
    if aggregation == "MEAN":
        return total / Decimal(len(values))
    raise ValueError("unsupported aggregation")


def _mbb_replicates(
    values: Sequence[Decimal],
    *,
    design: Mapping[str, Any],
    aggregation: str,
) -> Tuple[Decimal, ...]:
    length = design["block_length"]
    start_count = len(values) - length + 1
    blocks_per_sample = (len(values) + length - 1) // length
    replicates = []
    for replicate in range(design["resample_count"]):
        sampled: List[Decimal] = []
        for draw in range(blocks_per_sample):
            start = _draw_start(
                seed=design["seed"],
                replicate=replicate,
                draw=draw,
                start_count=start_count,
            )
            sampled.extend(values[start : start + length])
        replicates.append(
            _statistic(sampled[: len(values)], aggregation)
        )
    return tuple(replicates)


def _ceil_fraction(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


def _eligible_values(series: Mapping[str, Any]) -> Tuple[Decimal, ...]:
    return tuple(
        _decimal(observation["value"])
        for observation in series["observations"]
    )


def _design_reasons(design: Any) -> Tuple[str, ...]:
    if not isinstance(design, Mapping):
        return ("STATISTICAL_DECISION_DESIGN_INVALID",)
    expected = {
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
        "sampling_rule": "OVERLAPPING_NON_CIRCULAR_MBB_TRUNCATE_TO_N",
        "quantile_rule": "CONSERVATIVE_NEAREST_RANK_V1",
    }
    reasons = []
    for name, value in expected.items():
        if design.get(name) != value:
            reasons.append(f"STATISTICAL_DECISION_DESIGN_INVALID:{name}")
    try:
        if _decimal(design.get("minimum_economic_effect")) <= 0:
            reasons.append(
                "STATISTICAL_DECISION_DESIGN_INVALID:"
                "minimum_economic_effect"
            )
        _decimal(design.get("null_boundary"))
    except (ArithmeticError, TypeError, ValueError):
        reasons.append("STATISTICAL_DECISION_DESIGN_DECIMAL_INVALID")
    for name, minimum, maximum in (
        ("block_length", 1, None),
        ("minimum_block_count", 2, None),
        ("resample_count", 1000, 1000000),
        ("seed", 0, 9007199254740991),
    ):
        value = design.get(name)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum
            or (maximum is not None and value > maximum)
        ):
            reasons.append(f"STATISTICAL_DECISION_DESIGN_INVALID:{name}")
    return tuple(sorted(set(reasons)))


def _identity_reasons(snapshot: Mapping[str, Any]) -> Tuple[str, ...]:
    reasons = []
    if snapshot.get("schema_version") != "1.0.0":
        reasons.append("STATISTICAL_DECISION_SCHEMA_VERSION_INVALID")
    if snapshot.get("hash_algorithm") != "SHA-256":
        reasons.append("STATISTICAL_DECISION_HASH_ALGORITHM_INVALID")
    if snapshot.get("canonicalization") != "RFC8785_JCS":
        reasons.append("STATISTICAL_DECISION_CANONICALIZATION_INVALID")
    for name in (
        "snapshot_id",
        "trial_family_id",
        "current_candidate_id",
        "release_gate_policy_id",
        "metric_catalog_id",
        "statistical_design_policy_id",
        "experiment_manifest_id",
    ):
        if not _valid_id(snapshot.get(name)):
            reasons.append(f"STATISTICAL_DECISION_ID_INVALID:{name}")
    for name in (
        "statistical_design_policy_hash",
        "experiment_manifest_hash",
        "trial_registry_hash",
    ):
        if not _valid_hash(snapshot.get(name)):
            reasons.append(f"STATISTICAL_DECISION_HASH_INVALID:{name}")
    for name in (
        "release_gate_policy_version",
        "metric_catalog_version",
    ):
        if not isinstance(snapshot.get(name), str) or re.fullmatch(
            r"[0-9]+\.[0-9]+\.[0-9]+",
            snapshot.get(name, ""),
        ) is None:
            reasons.append(f"STATISTICAL_DECISION_VERSION_INVALID:{name}")
    if snapshot.get("replay_verified") is not True:
        reasons.append("STATISTICAL_DECISION_REPLAY_UNVERIFIED")
    scope = snapshot.get("scope")
    if not isinstance(scope, Mapping):
        reasons.append("STATISTICAL_DECISION_SCOPE_INVALID")
    else:
        for name in (
            "account_id",
            "evaluation_ledger",
            "release_route",
            "direction",
            "venue",
            "deployment_line_id",
            "endpoint_id",
            "endpoint_unit",
        ):
            if not _valid_id(scope.get(name)):
                reasons.append(f"STATISTICAL_DECISION_SCOPE_INVALID:{name}")
        if not _valid_hash(scope.get("deployment_line_hash")):
            reasons.append(
                "STATISTICAL_DECISION_SCOPE_INVALID:deployment_line_hash"
            )
        if scope.get("endpoint_direction") != "GREATER":
            reasons.append(
                "STATISTICAL_DECISION_SCOPE_INVALID:endpoint_direction"
            )
        try:
            if _decimal(scope.get("approved_production_capital_usdt")) <= 0:
                reasons.append(
                    "STATISTICAL_DECISION_SCOPE_INVALID:"
                    "approved_production_capital_usdt"
                )
            start = _timestamp(scope.get("evaluation_window_start"))
            end = _timestamp(scope.get("evaluation_window_end"))
            generated = _timestamp(snapshot.get("generated_at"))
            if end <= start or generated < end:
                reasons.append("STATISTICAL_DECISION_TIME_INVALID")
        except (ArithmeticError, TypeError, ValueError):
            reasons.append("STATISTICAL_DECISION_TIME_INVALID")
    return tuple(sorted(set(reasons)))


@_fixed_decimal_context
def _replay_statistical_decision(
    snapshot: Mapping[str, Any],
) -> StatisticalDecisionReplay:
    reasons = list(_identity_reasons(snapshot))
    reasons.extend(_design_reasons(snapshot.get("design")))
    registry = snapshot.get("trial_registry")
    if not isinstance(registry, list) or not registry:
        reasons.append("STATISTICAL_DECISION_TRIAL_REGISTRY_INVALID")
        return StatisticalDecisionReplay("FAIL", tuple(sorted(set(reasons))))
    actual_total = snapshot.get("actual_total_trials")
    if (
        isinstance(actual_total, bool)
        or not isinstance(actual_total, int)
        or actual_total < 1
        or actual_total != len(registry)
    ):
        reasons.append("STATISTICAL_DECISION_TRIAL_COUNT_MISMATCH")
    try:
        expected_registry_hash = statistical_trial_registry_hash(registry)
    except (CanonicalizationError, TypeError, ValueError):
        expected_registry_hash = ""
        reasons.append("STATISTICAL_DECISION_TRIAL_REGISTRY_INVALID")
    if snapshot.get("trial_registry_hash") != expected_registry_hash:
        reasons.append(
            "STATISTICAL_DECISION_TRIAL_REGISTRY_HASH_MISMATCH"
        )
    candidate_ids = [
        item.get("candidate_id")
        for item in registry
        if isinstance(item, Mapping)
    ]
    if len(candidate_ids) != len(registry) or any(
        not _valid_id(value) for value in candidate_ids
    ):
        reasons.append("STATISTICAL_DECISION_CANDIDATE_ID_INVALID")
    if len(candidate_ids) != len(set(candidate_ids)):
        reasons.append("STATISTICAL_DECISION_CANDIDATE_ID_DUPLICATE")
    if candidate_ids != sorted(candidate_ids):
        reasons.append("STATISTICAL_DECISION_TRIAL_REGISTRY_ORDER_INVALID")

    design = snapshot.get("design")
    scope = snapshot.get("scope")
    usable_design = isinstance(design, Mapping) and not _design_reasons(
        design
    )
    usable_scope = isinstance(scope, Mapping)
    current_member: Optional[Mapping[str, Any]] = None
    candidate_data: Dict[
        str, Tuple[Mapping[str, Any], Tuple[Decimal, ...], str]
    ] = {}
    sample_reasons = []
    for item in registry:
        if not isinstance(item, Mapping):
            reasons.append("STATISTICAL_DECISION_TRIAL_INVALID")
            continue
        candidate_id = item.get("candidate_id")
        status = item.get("candidate_status")
        if status not in _VALID_STATUSES:
            reasons.append(
                f"STATISTICAL_DECISION_CANDIDATE_STATUS_INVALID:{candidate_id}"
            )
        if not _valid_id(item.get("recipe_release_id")) or not _valid_hash(
            item.get("recipe_release_hash")
        ):
            reasons.append(
                f"STATISTICAL_DECISION_RECIPE_INVALID:{candidate_id}"
            )
        if candidate_id == snapshot.get("current_candidate_id"):
            current_member = item
        source = item.get("source_series_snapshot")
        source_hash = item.get("source_series_hash")
        if status != "EVALUATED":
            if source is not None or source_hash is not None:
                reasons.append(
                    "STATISTICAL_DECISION_NON_EVALUATED_SOURCE_UNEXPECTED:"
                    f"{candidate_id}"
                )
            continue
        if not isinstance(source, Mapping) or not _valid_hash(source_hash):
            reasons.append(
                f"STATISTICAL_DECISION_SOURCE_SERIES_INVALID:{candidate_id}"
            )
            continue
        source_reasons = statistical_series_reasons(source)
        try:
            computed_source_hash = statistical_series_hash(source)
        except CanonicalizationError:
            computed_source_hash = ""
        if (
            source_reasons
            or source.get("series_hash") != computed_source_hash
            or source_hash != computed_source_hash
        ):
            reasons.append(
                f"STATISTICAL_DECISION_SOURCE_SERIES_INVALID:{candidate_id}"
            )
            continue
        if (
            source.get("series_kind") != "PRIMARY_ENDPOINT_CONTRIBUTION"
            or source.get("aggregation") not in ("SUM", "MEAN")
        ):
            reasons.append(
                f"STATISTICAL_DECISION_SOURCE_KIND_INVALID:{candidate_id}"
            )
        source_scope = source.get("scope")
        if not isinstance(source_scope, Mapping) or not usable_scope:
            reasons.append(
                f"STATISTICAL_DECISION_SOURCE_SCOPE_MISMATCH:{candidate_id}"
            )
        else:
            for name in _SCOPE_FIELDS:
                if source_scope.get(name) != scope.get(name):
                    reasons.append(
                        "STATISTICAL_DECISION_SOURCE_SCOPE_MISMATCH:"
                        f"{candidate_id}:{name}"
                    )
            if (
                source_scope.get("recipe_release_id")
                != item.get("recipe_release_id")
                or source_scope.get("recipe_release_hash")
                != item.get("recipe_release_hash")
            ):
                reasons.append(
                    f"STATISTICAL_DECISION_RECIPE_MISMATCH:{candidate_id}"
                )
            if not _same_value(
                source.get("approved_production_capital_usdt"),
                scope.get("approved_production_capital_usdt"),
            ):
                reasons.append(
                    "STATISTICAL_DECISION_SOURCE_SCOPE_MISMATCH:"
                    f"{candidate_id}:approved_production_capital_usdt"
                )
        if (
            source.get("statistical_design_policy_id")
            != snapshot.get("statistical_design_policy_id")
            or source.get("statistical_design_policy_hash")
            != snapshot.get("statistical_design_policy_hash")
        ):
            reasons.append(
                f"STATISTICAL_DECISION_POLICY_MISMATCH:{candidate_id}"
            )
        if (
            source.get("experiment_manifest_id")
            != snapshot.get("experiment_manifest_id")
            or source.get("experiment_manifest_hash")
            != snapshot.get("experiment_manifest_hash")
        ):
            reasons.append(
                f"STATISTICAL_DECISION_EXPERIMENT_MISMATCH:{candidate_id}"
            )
        source_bootstrap = source.get("bootstrap_design")
        bootstrap_mismatch = (
            not isinstance(source_bootstrap, Mapping)
            or not usable_design
            or source_bootstrap.get("confidence_side")
            != "LOWER_ONE_SIDED"
            or any(
                source_bootstrap.get(name) != design.get(name)
                for name in _SOURCE_BOOTSTRAP_FIELDS
            )
        )
        if bootstrap_mismatch:
            reasons.append(
                "STATISTICAL_DECISION_BOOTSTRAP_DESIGN_MISMATCH:"
                f"{candidate_id}"
            )
            continue
        try:
            values = _eligible_values(source)
        except (ArithmeticError, KeyError, TypeError, ValueError):
            reasons.append(
                f"STATISTICAL_DECISION_SOURCE_SERIES_INVALID:{candidate_id}"
            )
            continue
        length = design["block_length"]
        if (
            len(values) < 3
            or len(values) < length
            or len(values) // length < design["minimum_block_count"]
        ):
            sample_reasons.append(
                f"STATISTICAL_DECISION_INSUFFICIENT_BLOCKS:{candidate_id}"
            )
        elif all(value == values[0] for value in values[1:]):
            sample_reasons.append(
                f"STATISTICAL_DECISION_ZERO_VARIANCE:{candidate_id}"
            )
        candidate_data[candidate_id] = (
            source,
            values,
            source["aggregation"],
        )

    if (
        current_member is None
        or current_member.get("candidate_status") != "EVALUATED"
    ):
        reasons.append("STATISTICAL_DECISION_CURRENT_CANDIDATE_INVALID")
    if reasons:
        return StatisticalDecisionReplay(
            "FAIL",
            tuple(sorted(set(reasons))),
        )
    if sample_reasons:
        return StatisticalDecisionReplay(
            "INCONCLUSIVE",
            tuple(sorted(set(sample_reasons))),
        )

    raw_results = []
    errors_by_candidate: Dict[str, Tuple[Decimal, ...]] = {}
    for item in registry:
        candidate_id = item["candidate_id"]
        if item["candidate_status"] != "EVALUATED":
            raw_p = Decimal("1")
        else:
            source, values, aggregation = candidate_data[candidate_id]
            mean = sum(values, Decimal("0")) / Decimal(len(values))
            residuals = tuple(value - mean for value in values)
            errors = _mbb_replicates(
                residuals,
                design=design,
                aggregation=aggregation,
            )
            errors_by_candidate[candidate_id] = errors
            observed = _statistic(values, aggregation)
            null_boundary = _decimal(design["null_boundary"])
            exceedances = sum(
                1 for error in errors if null_boundary + error >= observed
            )
            raw_p = (
                Decimal(1 + exceedances)
                / Decimal(design["resample_count"] + 1)
            )
        raw_results.append((raw_p, candidate_id, item))
    raw_results.sort(key=lambda row: (row[0], row[1]))

    family_size = len(raw_results)
    familywise_alpha = _decimal(design["family_wise_alpha"])
    ranked = []
    current_rank = 0
    for index, (raw_p, candidate_id, item) in enumerate(raw_results, 1):
        threshold = familywise_alpha / Decimal(family_size - index + 1)
        if candidate_id == snapshot["current_candidate_id"]:
            current_rank = index
        ranked.append((raw_p, threshold, candidate_id, item, index))
    current_remaining = family_size - current_rank + 1
    minimum_p = Decimal(1) / Decimal(design["resample_count"] + 1)
    current_threshold = familywise_alpha / Decimal(current_remaining)
    if minimum_p > current_threshold:
        return StatisticalDecisionReplay(
            "INCONCLUSIVE",
            ("STATISTICAL_DECISION_BOOTSTRAP_RESOLUTION_INSUFFICIENT",),
        )

    family_results = []
    continue_steps = True
    for raw_p, threshold, candidate_id, item, rank in ranked:
        reached = continue_steps
        rejected = reached and raw_p <= threshold
        family_results.append(
            {
                "candidate_id": candidate_id,
                "candidate_status": item["candidate_status"],
                "raw_p_value": canonical_decimal(raw_p),
                "holm_rank": rank,
                "holm_threshold": canonical_decimal(threshold),
                "step_reached": reached,
                "rejected": rejected,
            }
        )
        if not rejected:
            continue_steps = False

    current_source, current_values, current_aggregation = candidate_data[
        snapshot["current_candidate_id"]
    ]
    original_replicates = sorted(
        _mbb_replicates(
            current_values,
            design=design,
            aggregation=current_aggregation,
        )
    )
    count = design["resample_count"]
    lower_rank = max(1, _ceil_fraction(count * 5, 200))
    upper_rank = min(count, _ceil_fraction(count * 195, 200))
    lower = original_replicates[lower_rank - 1]
    upper = original_replicates[upper_rank - 1]

    ess_status, effective_count, ess_reasons = (
        geyer_initial_positive_sequence_ess(
            {"statistical_series_snapshot": current_source}
        )
    )
    if ess_status != "COMPUTED":
        return StatisticalDecisionReplay(
            "INCONCLUSIVE",
            tuple(
                sorted(
                    set(
                        f"STATISTICAL_DECISION_ESS_UNAVAILABLE:{reason}"
                        for reason in ess_reasons
                    )
                )
            ),
        )

    alpha_fraction = Fraction(1, 20 * current_remaining)
    critical_rank = min(
        count,
        _ceil_fraction(
            count * (alpha_fraction.denominator - alpha_fraction.numerator),
            alpha_fraction.denominator,
        ),
    )
    current_errors = errors_by_candidate[snapshot["current_candidate_id"]]
    null_boundary = _decimal(design["null_boundary"])
    null_statistics = sorted(
        null_boundary + error for error in current_errors
    )
    critical_value = null_statistics[critical_rank - 1]
    minimum_effect = _decimal(design["minimum_economic_effect"])
    alternative_exceedances = sum(
        1
        for error in current_errors
        if null_boundary + minimum_effect + error > critical_value
    )
    power = Decimal(alternative_exceedances) / Decimal(count)
    current_family = next(
        item
        for item in family_results
        if item["candidate_id"] == snapshot["current_candidate_id"]
    )
    current_results = {
        "observed_statistic": canonical_decimal(
            _statistic(current_values, current_aggregation)
        ),
        "effective_event_count": effective_count,
        "ci_lower": canonical_decimal(lower),
        "ci_upper": canonical_decimal(upper),
        "ci_width": canonical_decimal(upper - lower),
        "holm_adjusted_alpha": canonical_decimal(current_threshold),
        "holm_rejected": current_family["rejected"],
        "minimum_economic_effect": canonical_decimal(minimum_effect),
        "achieved_power": canonical_decimal(power),
    }
    return StatisticalDecisionReplay(
        "COMPUTED",
        (),
        tuple(family_results),
        current_results,
    )


@_fixed_decimal_context
def statistical_decision_snapshot_reasons(
    snapshot: Mapping[str, Any],
) -> Tuple[str, ...]:
    reasons = []
    try:
        computed_hash = statistical_decision_snapshot_hash(snapshot)
    except (CanonicalizationError, TypeError, ValueError):
        computed_hash = ""
        reasons.append("STATISTICAL_DECISION_NOT_CANONICAL")
    if snapshot.get("snapshot_hash") != computed_hash:
        reasons.append("STATISTICAL_DECISION_SELF_HASH_MISMATCH")
    replay = _replay_statistical_decision(snapshot)
    if replay.status == "FAIL":
        reasons.extend(replay.reason_codes)
        return tuple(sorted(set(reasons)))
    if snapshot.get("analysis_status") != replay.status:
        reasons.append("STATISTICAL_DECISION_STATUS_REPLAY_MISMATCH")
    if snapshot.get("analysis_reason_codes") != list(replay.reason_codes):
        reasons.append("STATISTICAL_DECISION_REASON_REPLAY_MISMATCH")
    if not _same_value(
        snapshot.get("family_results"),
        list(replay.family_results),
    ):
        reasons.append(
            "STATISTICAL_DECISION_FAMILY_RESULTS_REPLAY_MISMATCH"
        )
    if not _same_value(
        snapshot.get("current_candidate_results"),
        replay.current_results,
    ):
        reasons.append(
            "STATISTICAL_DECISION_CURRENT_RESULTS_REPLAY_MISMATCH"
        )
    return tuple(sorted(set(reasons)))


@_fixed_decimal_context
def build_statistical_decision_snapshot(
    *,
    snapshot_id: str,
    trial_family_id: str,
    current_candidate_id: str,
    release_gate_policy_id: str,
    release_gate_policy_version: str,
    metric_catalog_id: str,
    metric_catalog_version: str,
    statistical_design_policy_id: str,
    statistical_design_policy_hash: str,
    experiment_manifest_id: str,
    experiment_manifest_hash: str,
    expected_actual_total_trials: int,
    expected_trial_registry_hash: str,
    scope: Mapping[str, Any],
    design: Mapping[str, Any],
    trial_registry: Sequence[Mapping[str, Any]],
    generated_at: str,
) -> Dict[str, Any]:
    artifact = {
        "$schema": "./statistical-decision-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": snapshot_id,
        "snapshot_hash": "0" * 64,
        "hash_algorithm": "SHA-256",
        "canonicalization": "RFC8785_JCS",
        "trial_family_id": trial_family_id,
        "current_candidate_id": current_candidate_id,
        "release_gate_policy_id": release_gate_policy_id,
        "release_gate_policy_version": release_gate_policy_version,
        "metric_catalog_id": metric_catalog_id,
        "metric_catalog_version": metric_catalog_version,
        "statistical_design_policy_id": statistical_design_policy_id,
        "statistical_design_policy_hash": statistical_design_policy_hash,
        "experiment_manifest_id": experiment_manifest_id,
        "experiment_manifest_hash": experiment_manifest_hash,
        "scope": deepcopy(dict(scope)),
        "design": deepcopy(dict(design)),
        "actual_total_trials": expected_actual_total_trials,
        "trial_registry": deepcopy(list(trial_registry)),
        "trial_registry_hash": expected_trial_registry_hash,
        "analysis_status": "INCONCLUSIVE",
        "analysis_reason_codes": ["STATISTICAL_DECISION_NOT_REPLAYED"],
        "family_results": [],
        "current_candidate_results": None,
        "generated_at": generated_at,
        "replay_verified": True,
    }
    replay = _replay_statistical_decision(artifact)
    if replay.status == "FAIL":
        raise ValueError(",".join(replay.reason_codes))
    artifact["analysis_status"] = replay.status
    artifact["analysis_reason_codes"] = list(replay.reason_codes)
    artifact["family_results"] = list(replay.family_results)
    artifact["current_candidate_results"] = (
        dict(replay.current_results)
        if replay.current_results is not None
        else None
    )
    artifact["snapshot_hash"] = statistical_decision_snapshot_hash(artifact)
    reasons = statistical_decision_snapshot_reasons(artifact)
    if reasons:
        raise ValueError(",".join(reasons))
    return artifact


def _validated_snapshot(
    inputs: Mapping[str, Any],
) -> Tuple[Optional[Mapping[str, Any]], Tuple[str, ...]]:
    snapshot = inputs.get("statistical_decision_snapshot")
    if not isinstance(snapshot, Mapping):
        return None, ("STATISTICAL_DECISION_INVALID",)
    reasons = statistical_decision_snapshot_reasons(snapshot)
    if reasons:
        return None, reasons
    return snapshot, ()


def _decision_value(
    inputs: Mapping[str, Any],
    field: str,
) -> Tuple[str, Any, Tuple[str, ...]]:
    snapshot, reasons = _validated_snapshot(inputs)
    if reasons:
        return "FAIL", None, reasons
    if snapshot["analysis_status"] == "INCONCLUSIVE":
        return (
            "INCONCLUSIVE",
            None,
            tuple(snapshot["analysis_reason_codes"]),
        )
    return "COMPUTED", snapshot["current_candidate_results"][field], ()


@_fixed_decimal_context
def primary_endpoint_ci_width(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    return _decision_value(inputs, "ci_width")


@_fixed_decimal_context
def achieved_power_at_mere(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    return _decision_value(inputs, "achieved_power")


@_fixed_decimal_context
def holm_family_adjusted_primary_pass(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    return _decision_value(inputs, "holm_rejected")
