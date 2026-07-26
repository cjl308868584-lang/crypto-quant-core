"""Deterministic dependent-series statistics over frozen economic facts."""

import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
from functools import wraps
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple, TypeVar

from .canonical import business_hash, canonical_decimal, stable_id
from .economics import economic_snapshot_reasons, period_economic_pnl
from .errors import CanonicalizationError
from .evidence import artifact_self_hash

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


def statistical_series_hash(series: Mapping[str, Any]) -> str:
    return artifact_self_hash(series, "series_hash")


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp is not timezone aware")
    return parsed.astimezone(timezone.utc)


def _decimal(value: Any) -> Decimal:
    return Decimal(canonical_decimal(value))


def _require_id(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
        value,
    ) is None:
        raise ValueError(f"{field_name} is not a canonical ID")


def _require_hash(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or re.fullmatch(
        r"[a-f0-9]{64}",
        value,
    ) is None:
        raise ValueError(f"{field_name} is not a SHA-256 digest")


def _next_month(start: datetime) -> datetime:
    year = start.year + (1 if start.month == 12 else 0)
    month = 1 if start.month == 12 else start.month + 1
    return start.replace(year=year, month=month)


def _is_complete_utc_month(start: datetime, end: datetime) -> bool:
    return (
        start.day == 1
        and start.hour == 0
        and start.minute == 0
        and start.second == 0
        and start.microsecond == 0
        and end == _next_month(start)
    )


_TARGET_ACTIONS = frozenset(
    {
        "NO_DECISION",
        "HOLD_CURRENT",
        "FREEZE_INCREASES",
        "REDUCE_TO",
        "SET_TARGET",
        "FLATTEN",
    }
)
_PAIR_METADATA_FIELDS = (
    "proposal_id",
    "decision_time",
    "recommended_action",
    "absolute_exposure_ratio",
)
_PAIRED_TOP_LEVEL_FIELDS = (
    "source_arm_series",
    "baseline_recipe_release_id",
    "baseline_recipe_release_hash",
    "model_bundle_id",
    "model_bundle_hash",
    "ai_endpoint",
    "pairing_rule",
    "eligibility_rule",
    "pairing_report",
)


def _same_business_value(left: Any, right: Any) -> bool:
    try:
        return business_hash(left) == business_hash(right)
    except CanonicalizationError:
        return False


def _pair_key(observation: Mapping[str, Any]) -> Tuple[str, str]:
    proposal_id = observation.get("proposal_id")
    decision_time = observation.get("decision_time")
    _require_id(proposal_id, "proposal_id")
    parsed_decision = _timestamp(decision_time)
    if parsed_decision != _timestamp(observation.get("period_start")):
        raise ValueError("decision time must equal observation period start")
    _require_id(observation.get("fold_id"), "fold_id")
    if observation.get("recommended_action") not in _TARGET_ACTIONS:
        raise ValueError("recommended action is invalid")
    if _decimal(observation.get("absolute_exposure_ratio")) < 0:
        raise ValueError("absolute exposure cannot be negative")
    return proposal_id, decision_time


def _unpaired_record(observation: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "observation_id": observation["observation_id"],
        "proposal_id": observation["proposal_id"],
        "decision_time": observation["decision_time"],
        "source_economic_snapshot_hash": observation[
            "source_economic_snapshot_hash"
        ],
        "reason": "UNPAIRED",
    }


def _derive_pairing(
    baseline: Mapping[str, Any],
    ai: Mapping[str, Any],
) -> Tuple[Sequence[Dict[str, Any]], Dict[str, Any]]:
    arm_indexes = []
    for arm in (baseline, ai):
        indexed = {}
        for observation in arm["observations"]:
            key = _pair_key(observation)
            if key in indexed:
                raise ValueError("duplicate proposal and decision-time pair key")
            indexed[key] = observation
        arm_indexes.append(indexed)
    baseline_index, ai_index = arm_indexes
    matched_keys = sorted(
        set(baseline_index) & set(ai_index),
        key=lambda item: (_timestamp(item[1]), item[0]),
    )
    if not matched_keys:
        raise ValueError("paired series has no matched observations")

    paired_observations = []
    for key in matched_keys:
        base_observation = baseline_index[key]
        ai_observation = ai_index[key]
        for name in ("period_start", "period_end", "fold_id"):
            if base_observation.get(name) != ai_observation.get(name):
                raise ValueError(f"paired observations disagree on {name}")
        baseline_value = _decimal(base_observation["value"])
        ai_value = _decimal(ai_observation["value"])
        baseline_exposure = _decimal(
            base_observation["absolute_exposure_ratio"]
        )
        ai_exposure = _decimal(ai_observation["absolute_exposure_ratio"])
        action_changed = (
            base_observation["recommended_action"]
            != ai_observation["recommended_action"]
        )
        exposure_changed = baseline_exposure != ai_exposure
        proposal_id, decision_time = key
        paired_observations.append(
            {
                "observation_id": stable_id(
                    "pair",
                    {
                        "proposal_id": proposal_id,
                        "decision_time": decision_time,
                    },
                ),
                "proposal_id": proposal_id,
                "decision_time": decision_time,
                "fold_id": base_observation["fold_id"],
                "period_start": base_observation["period_start"],
                "period_end": base_observation["period_end"],
                "value": canonical_decimal(ai_value - baseline_value),
                "calendar_month_complete": False,
                "baseline_observation_id": base_observation["observation_id"],
                "ai_observation_id": ai_observation["observation_id"],
                "baseline_value": canonical_decimal(baseline_value),
                "ai_value": canonical_decimal(ai_value),
                "baseline_action": base_observation["recommended_action"],
                "ai_action": ai_observation["recommended_action"],
                "baseline_absolute_exposure_ratio": canonical_decimal(
                    baseline_exposure
                ),
                "ai_absolute_exposure_ratio": canonical_decimal(ai_exposure),
                "action_changed": action_changed,
                "absolute_exposure_changed": exposure_changed,
                "eligible": action_changed or exposure_changed,
                "baseline_source_economic_snapshot_hash": base_observation[
                    "source_economic_snapshot_hash"
                ],
                "ai_source_economic_snapshot_hash": ai_observation[
                    "source_economic_snapshot_hash"
                ],
            }
        )

    unmatched_baseline_keys = sorted(
        set(baseline_index) - set(ai_index),
        key=lambda item: (_timestamp(item[1]), item[0]),
    )
    unmatched_ai_keys = sorted(
        set(ai_index) - set(baseline_index),
        key=lambda item: (_timestamp(item[1]), item[0]),
    )
    unpaired_baseline = [
        _unpaired_record(baseline_index[key])
        for key in unmatched_baseline_keys
    ]
    unpaired_ai = [
        _unpaired_record(ai_index[key])
        for key in unmatched_ai_keys
    ]
    eligible_count = sum(
        observation["eligible"] for observation in paired_observations
    )
    report = {
        "baseline_observation_count": len(baseline_index),
        "ai_observation_count": len(ai_index),
        "matched_pair_count": len(paired_observations),
        "eligible_changed_pair_count": eligible_count,
        "excluded_unchanged_pair_count": (
            len(paired_observations) - eligible_count
        ),
        "unpaired_baseline_count": len(unpaired_baseline),
        "unpaired_ai_count": len(unpaired_ai),
        "unpaired_baseline": unpaired_baseline,
        "unpaired_ai": unpaired_ai,
    }
    return paired_observations, report


def _paired_series_reasons(
    series: Mapping[str, Any],
) -> Tuple[str, ...]:
    reasons = []
    if series.get("schema_version") != "1.1.0":
        reasons.append("PAIRED_SERIES_SCHEMA_VERSION_INVALID")
    scope = series["scope"]
    if (
        scope.get("evaluation_ledger") != "PAIRED_COMPARISON"
        or scope.get("release_route") != "AI_ENHANCED"
    ):
        reasons.append("PAIRED_SERIES_SCOPE_ROLE_INVALID")
    if series.get("aggregation") != "SUM":
        reasons.append("PAIRED_SERIES_AGGREGATION_INVALID")
    if (
        series.get("capital_normalization")
        != "APPROVED_CAPITAL_EVALUATION_WINDOW"
    ):
        reasons.append("PAIRED_SERIES_CAPITAL_NORMALIZATION_INVALID")
    if series.get("pairing_rule") != "PROPOSAL_ID_PLUS_DECISION_TIME":
        reasons.append("PAIRED_SERIES_PAIRING_RULE_INVALID")
    if (
        series.get("eligibility_rule")
        != "AI_ACTION_OR_ABSOLUTE_EXPOSURE_CHANGED"
    ):
        reasons.append("PAIRED_SERIES_ELIGIBILITY_RULE_INVALID")

    source_arms = series.get("source_arm_series")
    if not isinstance(source_arms, Mapping):
        return tuple(
            sorted(set(reasons + ["PAIRED_SERIES_SOURCE_ARMS_MISSING"]))
        )
    baseline = source_arms.get("baseline")
    ai = source_arms.get("ai")
    if not isinstance(baseline, Mapping) or not isinstance(ai, Mapping):
        return tuple(
            sorted(set(reasons + ["PAIRED_SERIES_SOURCE_ARMS_INVALID"]))
        )
    for label, arm in (("BASELINE", baseline), ("AI", ai)):
        arm_reasons = statistical_series_reasons(arm)
        reasons.extend(
            f"PAIRED_SERIES_{label}_SOURCE:{reason}"
            for reason in arm_reasons
        )
        if arm.get("series_kind") != "PRIMARY_ENDPOINT_CONTRIBUTION":
            reasons.append(f"PAIRED_SERIES_{label}_KIND_INVALID")
        if any(
            not isinstance(observation, Mapping)
            or any(name not in observation for name in _PAIR_METADATA_FIELDS)
            for observation in arm.get("observations", ())
        ):
            reasons.append(f"PAIRED_SERIES_{label}_PAIR_METADATA_MISSING")

    baseline_scope = baseline.get("scope")
    ai_scope = ai.get("scope")
    if not isinstance(baseline_scope, Mapping) or not isinstance(
        ai_scope,
        Mapping,
    ):
        return tuple(
            sorted(set(reasons + ["PAIRED_SERIES_ARM_SCOPE_INVALID"]))
        )
    if (
        baseline_scope.get("evaluation_ledger") != "BASELINE_LEDGER"
        or baseline_scope.get("release_route") != "AI_ENHANCED"
    ):
        reasons.append("PAIRED_SERIES_BASELINE_ROLE_INVALID")
    if (
        ai_scope.get("evaluation_ledger") != "AI_LEDGER"
        or ai_scope.get("release_route") != "AI_ENHANCED"
    ):
        reasons.append("PAIRED_SERIES_AI_ROLE_INVALID")

    common_scope_fields = (
        "account_id",
        "direction",
        "venue",
        "deployment_line_id",
        "deployment_line_hash",
        "evaluation_window_start",
        "evaluation_window_end",
    )
    for name in common_scope_fields:
        if baseline_scope.get(name) != ai_scope.get(name):
            reasons.append(f"PAIRED_SERIES_ARM_SCOPE_MISMATCH:{name}")
    if (
        series.get("baseline_recipe_release_id")
        != baseline_scope.get("recipe_release_id")
        or series.get("baseline_recipe_release_hash")
        != baseline_scope.get("recipe_release_hash")
    ):
        reasons.append("PAIRED_SERIES_BASELINE_RECIPE_MISMATCH")

    outer_scope_fields = (
        "account_id",
        "release_route",
        "direction",
        "venue",
        "recipe_release_id",
        "recipe_release_hash",
        "deployment_line_id",
        "deployment_line_hash",
        "evaluation_window_start",
        "evaluation_window_end",
    )
    for name in outer_scope_fields:
        if scope.get(name) != ai_scope.get(name):
            reasons.append(f"PAIRED_SERIES_OUTER_SCOPE_MISMATCH:{name}")

    common_series_fields = (
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
    for name in common_series_fields:
        if not _same_business_value(baseline.get(name), ai.get(name)):
            reasons.append(f"PAIRED_SERIES_ARM_SETTING_MISMATCH:{name}")
        if not _same_business_value(series.get(name), ai.get(name)):
            reasons.append(f"PAIRED_SERIES_OUTER_SETTING_MISMATCH:{name}")

    declared_sources = series.get("source_economic_snapshot_hashes")
    expected_sources = (
        list(baseline.get("source_economic_snapshot_hashes", ()))
        + list(ai.get("source_economic_snapshot_hashes", ()))
    )
    if declared_sources != expected_sources:
        reasons.append("PAIRED_SERIES_SOURCE_SEQUENCE_MISMATCH")
    if len(expected_sources) != len(set(expected_sources)):
        reasons.append("PAIRED_SERIES_SOURCE_DUPLICATE")

    try:
        expected_observations, expected_report = _derive_pairing(baseline, ai)
    except (CanonicalizationError, KeyError, TypeError, ValueError):
        reasons.append("PAIRED_SERIES_REPLAY_FAILED")
    else:
        if not _same_business_value(
            series.get("observations"),
            expected_observations,
        ):
            reasons.append("PAIRED_SERIES_OBSERVATION_REPLAY_MISMATCH")
        if not _same_business_value(
            series.get("pairing_report"),
            expected_report,
        ):
            reasons.append("PAIRED_SERIES_REPORT_REPLAY_MISMATCH")

    for name in (
        "baseline_recipe_release_id",
        "model_bundle_id",
    ):
        try:
            _require_id(series.get(name), name)
        except ValueError:
            reasons.append(f"PAIRED_SERIES_REFERENCE_INVALID:{name}")
    for name in (
        "baseline_recipe_release_hash",
        "model_bundle_hash",
    ):
        try:
            _require_hash(series.get(name), name)
        except ValueError:
            reasons.append(f"PAIRED_SERIES_REFERENCE_INVALID:{name}")
    if series.get("ai_endpoint") not in ("GROWTH", "RISK_EFFICIENCY"):
        reasons.append("PAIRED_SERIES_ENDPOINT_INVALID")
    return tuple(sorted(set(reasons)))


@_fixed_decimal_context
def statistical_series_reasons(
    series: Mapping[str, Any],
) -> Tuple[str, ...]:
    reasons = []
    try:
        computed_hash = statistical_series_hash(series)
    except CanonicalizationError:
        computed_hash = ""
        reasons.append("STATISTICAL_SERIES_NOT_CANONICAL")
    if series.get("series_hash") != computed_hash:
        reasons.append("STATISTICAL_SERIES_SELF_HASH_MISMATCH")
    if series.get("replay_verified") is not True:
        reasons.append("STATISTICAL_SERIES_REPLAY_UNVERIFIED")

    scope = series.get("scope")
    if not isinstance(scope, Mapping):
        return tuple(
            sorted(set(reasons + ["STATISTICAL_SERIES_SCOPE_INVALID"]))
        )
    ledger = scope.get("evaluation_ledger")
    route = scope.get("release_route")
    if (
        ledger in ("AI_LEDGER", "PAIRED_COMPARISON")
        and route != "AI_ENHANCED"
    ):
        reasons.append("STATISTICAL_SERIES_LEDGER_ROUTE_MISMATCH")
    if (
        scope.get("direction"),
        scope.get("venue"),
    ) not in {
        ("LONG", "BINANCE_SPOT"),
        ("SHORT", "BINANCE_USDT_PERP"),
    }:
        reasons.append("STATISTICAL_SERIES_DIRECTION_VENUE_MISMATCH")
    try:
        scope_start = _timestamp(scope.get("evaluation_window_start"))
        scope_end = _timestamp(scope.get("evaluation_window_end"))
        generated = _timestamp(series.get("generated_at"))
        if scope_end <= scope_start:
            reasons.append("STATISTICAL_SERIES_WINDOW_NOT_INCREASING")
        if generated < scope_end:
            reasons.append("STATISTICAL_SERIES_GENERATED_BEFORE_END")
    except (TypeError, ValueError):
        return tuple(
            sorted(set(reasons + ["STATISTICAL_SERIES_TIME_INVALID"]))
        )

    kind = series.get("series_kind")
    if kind == "PAIRED_AI_ECONOMIC_NET_LOG_GROWTH_DELTA":
        reasons.extend(
            _paired_series_reasons(series)
        )
        return tuple(sorted(set(reasons)))

    if kind not in (
        "PRIMARY_ENDPOINT_CONTRIBUTION",
        "MONTHLY_ECONOMIC_PNL_USDT",
    ):
        reasons.append("STATISTICAL_SERIES_KIND_INVALID")
    if any(name in series for name in _PAIRED_TOP_LEVEL_FIELDS):
        reasons.append("STATISTICAL_SERIES_PAIRED_FIELDS_UNEXPECTED")
    counterfactual_id = series.get("counterfactual_replay_id")
    is_counterfactual = counterfactual_id is not None
    if is_counterfactual:
        try:
            _require_id(
                counterfactual_id,
                "counterfactual_replay_id",
            )
        except ValueError:
            reasons.append(
                "STATISTICAL_SERIES_COUNTERFACTUAL_ID_INVALID"
            )
        if (
            series.get("schema_version") != "1.2.0"
            or kind != "PRIMARY_ENDPOINT_CONTRIBUTION"
        ):
            reasons.append(
                "STATISTICAL_SERIES_COUNTERFACTUAL_KIND_INVALID"
            )
    elif series.get("schema_version") == "1.2.0":
        reasons.append("STATISTICAL_SERIES_COUNTERFACTUAL_ID_MISSING")

    observations = series.get("observations")
    if not isinstance(observations, list) or not observations:
        return tuple(
            sorted(set(reasons + ["STATISTICAL_SERIES_OBSERVATIONS_MISSING"]))
        )
    identifiers = []
    source_hashes = []
    period_boundaries = []
    month_completeness = []
    previous_end: Optional[datetime] = None
    for observation in observations:
        if not isinstance(observation, Mapping):
            reasons.append("STATISTICAL_SERIES_OBSERVATION_INVALID")
            continue
        identifiers.append(observation.get("observation_id"))
        source_hashes.append(
            observation.get("source_economic_snapshot_hash")
        )
        try:
            start = _timestamp(observation.get("period_start"))
            end = _timestamp(observation.get("period_end"))
            if end <= start:
                reasons.append("STATISTICAL_SERIES_PERIOD_NOT_INCREASING")
            if previous_end is not None and start < previous_end:
                reasons.append("STATISTICAL_SERIES_PERIOD_OVERLAP")
            if start < scope_start or end > scope_end:
                reasons.append("STATISTICAL_SERIES_PERIOD_OUTSIDE_SCOPE")
            if observation.get(
                "calendar_month_complete"
            ) is not _is_complete_utc_month(start, end):
                reasons.append(
                    "STATISTICAL_SERIES_MONTH_COMPLETENESS_MISMATCH"
                )
            period_boundaries.append((start, end))
            month_completeness.append(
                observation.get("calendar_month_complete")
            )
            _decimal(observation.get("value"))
            counterfactual_hash = observation.get(
                "counterfactual_replay_period_hash"
            )
            if is_counterfactual:
                try:
                    _require_hash(
                        counterfactual_hash,
                        "counterfactual_replay_period_hash",
                    )
                except ValueError:
                    reasons.append(
                        "STATISTICAL_SERIES_COUNTERFACTUAL_PERIOD_HASH_INVALID"
                    )
            elif counterfactual_hash is not None:
                reasons.append(
                    "STATISTICAL_SERIES_COUNTERFACTUAL_PERIOD_HASH_UNEXPECTED"
                )
            metadata_present = [
                name in observation for name in _PAIR_METADATA_FIELDS
            ]
            if any(metadata_present) and not all(metadata_present):
                reasons.append(
                    "STATISTICAL_SERIES_PAIR_METADATA_INCOMPLETE"
                )
            elif all(metadata_present):
                if "fold_id" not in observation:
                    reasons.append(
                        "STATISTICAL_SERIES_PAIR_FOLD_ID_MISSING"
                    )
                _pair_key(observation)
            elif "fold_id" in observation:
                _require_id(observation.get("fold_id"), "fold_id")
            previous_end = end
        except (CanonicalizationError, TypeError, ValueError):
            reasons.append("STATISTICAL_SERIES_OBSERVATION_VALUE_INVALID")
    if len(identifiers) != len(set(identifiers)):
        reasons.append("STATISTICAL_SERIES_OBSERVATION_ID_DUPLICATE")
    declared_sources = series.get("source_economic_snapshot_hashes")
    if not isinstance(declared_sources, list) or declared_sources != (
        source_hashes
    ):
        reasons.append("STATISTICAL_SERIES_SOURCE_SEQUENCE_MISMATCH")
    if len(source_hashes) != len(set(source_hashes)):
        reasons.append("STATISTICAL_SERIES_SOURCE_DUPLICATE")
    if period_boundaries:
        if (
            period_boundaries[0][0] != scope_start
            or period_boundaries[-1][1] != scope_end
        ):
            reasons.append("STATISTICAL_SERIES_BOUNDARY_MISMATCH")
    if kind == "MONTHLY_ECONOMIC_PNL_USDT":
        if series.get("aggregation") != "MEAN":
            reasons.append("STATISTICAL_SERIES_MONTHLY_AGGREGATION_INVALID")
        if any(
            current[0] != previous[1]
            for previous, current in zip(
                period_boundaries,
                period_boundaries[1:],
            )
        ):
            reasons.append("STATISTICAL_SERIES_MONTHLY_PERIOD_GAP")
        if any(
            complete is not True
            and index not in (0, len(month_completeness) - 1)
            for index, complete in enumerate(month_completeness)
        ):
            reasons.append("STATISTICAL_SERIES_INTERIOR_PARTIAL_MONTH")
        if (
            series.get("capital_normalization")
            != "MONTHLY_RESET_TO_APPROVED_CAPITAL"
        ):
            reasons.append(
                "STATISTICAL_SERIES_MONTHLY_CAPITAL_NORMALIZATION_INVALID"
            )
    elif kind == "PRIMARY_ENDPOINT_CONTRIBUTION":
        if series.get("aggregation") != "SUM":
            reasons.append("STATISTICAL_SERIES_ENDPOINT_AGGREGATION_INVALID")
        if (
            series.get("capital_normalization")
            != "APPROVED_CAPITAL_EVALUATION_WINDOW"
        ):
            reasons.append(
                "STATISTICAL_SERIES_ENDPOINT_CAPITAL_NORMALIZATION_INVALID"
            )
    return tuple(sorted(set(reasons)))


def _validated_series(
    inputs: Mapping[str, Any],
) -> Tuple[Optional[Mapping[str, Any]], Tuple[str, ...]]:
    series = inputs.get("statistical_series_snapshot")
    if not isinstance(series, Mapping):
        return None, ("STATISTICAL_SERIES_INVALID",)
    reasons = statistical_series_reasons(series)
    return (series, ()) if not reasons else (None, reasons)


def _eligible_values(
    series: Mapping[str, Any],
    *,
    complete_months_only: bool,
) -> Tuple[Decimal, ...]:
    return tuple(
        _decimal(observation["value"])
        for observation in series["observations"]
        if (
            not complete_months_only
            or observation["calendar_month_complete"]
        )
        and (
            series["series_kind"]
            != "PAIRED_AI_ECONOMIC_NET_LOG_GROWTH_DELTA"
            or observation["eligible"]
        )
    )


@_fixed_decimal_context
def geyer_initial_positive_sequence_ess(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    series, reasons = _validated_series(inputs)
    if reasons:
        return "FAIL", None, reasons
    values = _eligible_values(series, complete_months_only=False)
    design = series["bootstrap_design"]
    block_length = design["block_length"]
    if (
        len(values) // block_length
        < design["minimum_block_count"]
        or len(values) < 3
    ):
        return (
            "INCONCLUSIVE",
            None,
            ("STATISTICAL_SERIES_INSUFFICIENT_BLOCKS",),
        )
    count = Decimal(len(values))
    mean = sum(values, Decimal("0")) / count
    centered = tuple(value - mean for value in values)
    gamma_zero = sum(
        (value * value for value in centered),
        Decimal("0"),
    ) / count
    if gamma_zero == 0:
        return (
            "INCONCLUSIVE",
            None,
            ("STATISTICAL_SERIES_ZERO_VARIANCE",),
        )
    autocorrelations = []
    for lag in range(1, len(values)):
        covariance = sum(
            (
                centered[index] * centered[index + lag]
                for index in range(len(values) - lag)
            ),
            Decimal("0"),
        ) / count
        autocorrelations.append(covariance / gamma_zero)
    retained_sum = Decimal("0")
    for index in range(0, len(autocorrelations) - 1, 2):
        pair = autocorrelations[index] + autocorrelations[index + 1]
        if pair <= 0:
            break
        retained_sum += pair
    tau = max(Decimal("1"), Decimal("1") + Decimal("2") * retained_sum)
    effective = (count / tau).to_integral_value(rounding=ROUND_FLOOR)
    return "COMPUTED", int(min(count, effective)), ()


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
        candidate = int.from_bytes(
            hashlib.sha256(material).digest(),
            "big",
        )
        if candidate < acceptance_limit:
            return candidate % start_count
        attempt += 1


def _moving_block_lcb(
    series: Mapping[str, Any],
    *,
    complete_months_only: bool,
) -> Tuple[str, Any, Tuple[str, ...]]:
    values = _eligible_values(
        series,
        complete_months_only=complete_months_only,
    )
    return _moving_block_lcb_values(
        values,
        design=series["bootstrap_design"],
        aggregation=series["aggregation"],
    )


def _moving_block_lcb_values(
    values: Sequence[Decimal],
    *,
    design: Mapping[str, Any],
    aggregation: str,
) -> Tuple[str, Any, Tuple[str, ...]]:
    length = design["block_length"]
    if (
        not values
        or len(values) // length < design["minimum_block_count"]
        or len(values) < length
    ):
        return (
            "INCONCLUSIVE",
            None,
            ("STATISTICAL_SERIES_INSUFFICIENT_BLOCKS",),
        )
    start_count = len(values) - length + 1
    blocks_per_sample = (len(values) + length - 1) // length
    replicates = []
    for replicate in range(design["resample_count"]):
        sampled = []
        for draw in range(blocks_per_sample):
            start = _draw_start(
                seed=design["seed"],
                replicate=replicate,
                draw=draw,
                start_count=start_count,
            )
            sampled.extend(values[start : start + length])
        sampled = sampled[: len(values)]
        statistic = sum(sampled, Decimal("0"))
        if aggregation == "MEAN":
            statistic /= Decimal(len(sampled))
        replicates.append(statistic)
    replicates.sort()
    rank = max(1, (design["resample_count"] * 5 + 99) // 100)
    return "COMPUTED", canonical_decimal(replicates[rank - 1]), ()


@_fixed_decimal_context
def one_sided_95_moving_block_bootstrap(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    series, reasons = _validated_series(inputs)
    if reasons:
        return "FAIL", None, reasons
    if series["series_kind"] != "PRIMARY_ENDPOINT_CONTRIBUTION":
        return "FAIL", None, ("STATISTICAL_SERIES_KIND_MISMATCH",)
    return _moving_block_lcb(series, complete_months_only=False)


@_fixed_decimal_context
def one_sided_95_paired_moving_block_bootstrap(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    series, reasons = _validated_series(inputs)
    if reasons:
        return "FAIL", None, reasons
    if (
        series["series_kind"]
        != "PAIRED_AI_ECONOMIC_NET_LOG_GROWTH_DELTA"
    ):
        return "FAIL", None, ("STATISTICAL_SERIES_KIND_MISMATCH",)
    if not any(
        observation["eligible"] for observation in series["observations"]
    ):
        return (
            "INCONCLUSIVE",
            None,
            ("PAIRED_SERIES_NO_ELIGIBLE_CHANGED_PAIRS",),
        )
    return _moving_block_lcb(series, complete_months_only=False)


def _validated_primary_endpoint(
    inputs: Mapping[str, Any],
) -> Tuple[Optional[Mapping[str, Any]], Tuple[str, ...]]:
    series, reasons = _validated_series(inputs)
    if reasons:
        return None, reasons
    if series["series_kind"] != "PRIMARY_ENDPOINT_CONTRIBUTION":
        return None, ("STATISTICAL_SERIES_KIND_MISMATCH",)
    return series, ()


@_fixed_decimal_context
def leave_max_positive_fold_out_mbb_lcb95(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    series, reasons = _validated_primary_endpoint(inputs)
    if reasons:
        return "FAIL", None, reasons
    if any("fold_id" not in item for item in series["observations"]):
        return "FAIL", None, ("STATISTICAL_SERIES_FOLD_ID_MISSING",)
    fold_contributions: Dict[str, Decimal] = {}
    for observation in series["observations"]:
        fold_id = observation["fold_id"]
        fold_contributions[fold_id] = (
            fold_contributions.get(fold_id, Decimal("0"))
            + _decimal(observation["value"])
        )
    positive_folds = sorted(
        (
            (-contribution, fold_id)
            for fold_id, contribution in fold_contributions.items()
            if contribution > 0
        ),
    )
    excluded_fold = (
        positive_folds[0][1] if positive_folds else None
    )
    values = tuple(
        _decimal(observation["value"])
        for observation in series["observations"]
        if observation["fold_id"] != excluded_fold
    )
    return _moving_block_lcb_values(
        values,
        design=series["bootstrap_design"],
        aggregation=series["aggregation"],
    )


def _leave_top_positive_events(
    inputs: Mapping[str, Any],
    *,
    limit: int,
) -> Tuple[str, Any, Tuple[str, ...]]:
    series, reasons = _validated_primary_endpoint(inputs)
    if reasons:
        return "FAIL", None, reasons
    ranked = sorted(
        (
            observation
            for observation in series["observations"]
            if _decimal(observation["value"]) > 0
        ),
        key=lambda item: (
            -_decimal(item["value"]),
            item["observation_id"],
        ),
    )
    excluded_ids = {
        observation["observation_id"] for observation in ranked[:limit]
    }
    values = tuple(
        _decimal(observation["value"])
        for observation in series["observations"]
        if observation["observation_id"] not in excluded_ids
    )
    return _moving_block_lcb_values(
        values,
        design=series["bootstrap_design"],
        aggregation=series["aggregation"],
    )


@_fixed_decimal_context
def leave_top_5_positive_events_out_mbb_lcb95(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    return _leave_top_positive_events(inputs, limit=5)


@_fixed_decimal_context
def leave_max_positive_event_out_mbb_lcb95(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    return _leave_top_positive_events(inputs, limit=1)


@_fixed_decimal_context
def monthly_economic_pnl_mbb_lcb95(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    series, reasons = _validated_series(inputs)
    if reasons:
        return "FAIL", None, reasons
    if series["series_kind"] != "MONTHLY_ECONOMIC_PNL_USDT":
        return "FAIL", None, ("STATISTICAL_SERIES_KIND_MISMATCH",)
    return _moving_block_lcb(series, complete_months_only=True)


@_fixed_decimal_context
def complete_utc_calendar_month_count(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    series, reasons = _validated_series(inputs)
    if reasons:
        return "FAIL", None, reasons
    if series["series_kind"] != "MONTHLY_ECONOMIC_PNL_USDT":
        return "FAIL", None, ("STATISTICAL_SERIES_KIND_MISMATCH",)
    return (
        "COMPUTED",
        sum(
            1
            for observation in series["observations"]
            if observation["calendar_month_complete"]
        ),
        (),
    )


@_fixed_decimal_context
def cash_flow_adjusted_economic_log_growth(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    snapshot = inputs.get("economic_ledger_snapshot")
    if not isinstance(snapshot, Mapping):
        return "FAIL", None, ("ECONOMIC_SNAPSHOT_INVALID",)
    reasons = economic_snapshot_reasons(snapshot)
    if reasons:
        return "FAIL", None, reasons
    points = snapshot["equity_points"]
    growth = Decimal("0")
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
            return "FAIL", None, ("ECONOMIC_EQUITY_NONPOSITIVE",)
        growth += (adjusted_end / starting_equity).ln()
    return "COMPUTED", canonical_decimal(growth), ()


@_fixed_decimal_context
def monthly_economic_series_snapshot(
    *,
    series_id: str,
    economic_snapshots: Sequence[Mapping[str, Any]],
    approved_production_capital_usdt: Any,
    split_policy_id: str,
    split_policy_hash: str,
    statistical_design_policy_id: str,
    statistical_design_policy_hash: str,
    experiment_manifest_id: str,
    experiment_manifest_hash: str,
    block_length: int,
    minimum_block_count: int,
    resample_count: int,
    seed: int,
    generated_at: str,
) -> Dict[str, Any]:
    """Build a monthly series only from valid, same-scope economic snapshots."""

    if not economic_snapshots:
        raise ValueError("economic snapshots cannot be empty")
    for name, value in (
        ("series_id", series_id),
        ("split_policy_id", split_policy_id),
        ("statistical_design_policy_id", statistical_design_policy_id),
        ("experiment_manifest_id", experiment_manifest_id),
    ):
        _require_id(value, name)
    for name, value in (
        ("split_policy_hash", split_policy_hash),
        ("statistical_design_policy_hash", statistical_design_policy_hash),
        ("experiment_manifest_hash", experiment_manifest_hash),
    ):
        _require_hash(value, name)
    if _decimal(approved_production_capital_usdt) <= 0:
        raise ValueError("approved production capital must be positive")
    approved_capital = _decimal(approved_production_capital_usdt)
    if (
        isinstance(block_length, bool)
        or not isinstance(block_length, int)
        or block_length < 1
        or isinstance(minimum_block_count, bool)
        or not isinstance(minimum_block_count, int)
        or minimum_block_count < 2
        or isinstance(resample_count, bool)
        or not isinstance(resample_count, int)
        or not 1000 <= resample_count <= 1000000
        or isinstance(seed, bool)
        or not isinstance(seed, int)
        or not 0 <= seed <= 9007199254740991
    ):
        raise ValueError("bootstrap design is outside frozen bounds")
    ordered = sorted(
        economic_snapshots,
        key=lambda item: item["scope"]["evaluation_window_start"],
    )
    for snapshot in ordered:
        reasons = economic_snapshot_reasons(snapshot)
        if reasons:
            raise ValueError(f"invalid economic snapshot: {reasons}")
    first_scope = ordered[0]["scope"]
    identity_fields = (
        "account_id",
        "evaluation_ledger",
        "release_route",
        "direction",
        "venue",
        "recipe_release_id",
        "recipe_release_hash",
        "deployment_line_id",
        "deployment_line_hash",
    )
    for snapshot in ordered:
        if any(
            snapshot["scope"].get(name) != first_scope.get(name)
            for name in identity_fields
        ):
            raise ValueError("economic snapshot scopes do not match")
        for name in (
            "accounting_policy_id",
            "accounting_policy_hash",
            "cost_allocation_policy_id",
            "cost_allocation_policy_hash",
        ):
            if snapshot.get(name) != ordered[0].get(name):
                raise ValueError("economic snapshot policies do not match")
        if _decimal(
            snapshot.get("starting_liquidation_equity_usdt")
        ) != approved_capital:
            raise ValueError(
                "economic snapshot is not reset to approved capital"
            )
    observations = []
    previous_end: Optional[datetime] = None
    for snapshot in ordered:
        start = _timestamp(snapshot["scope"]["evaluation_window_start"])
        end = _timestamp(snapshot["scope"]["evaluation_window_end"])
        if previous_end is not None and start < previous_end:
            raise ValueError("economic snapshot windows overlap")
        status, value, reasons = period_economic_pnl(
            {"economic_ledger_snapshot": snapshot}
        )
        if status != "COMPUTED":
            raise ValueError(f"economic PnL unavailable: {reasons}")
        observations.append(
            {
                "observation_id": snapshot["snapshot_id"],
                "period_start": snapshot["scope"]["evaluation_window_start"],
                "period_end": snapshot["scope"]["evaluation_window_end"],
                "value": value,
                "calendar_month_complete": _is_complete_utc_month(
                    start,
                    end,
                ),
                "source_economic_snapshot_hash": snapshot["snapshot_hash"],
            }
        )
        previous_end = end
    artifact = {
        "$schema": "./statistical-series-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "series_id": series_id,
        "series_hash": "0" * 64,
        "hash_algorithm": "SHA-256",
        "canonicalization": "RFC8785_JCS",
        "source_economic_snapshot_hashes": [
            snapshot["snapshot_hash"] for snapshot in ordered
        ],
        "accounting_policy_id": ordered[0]["accounting_policy_id"],
        "accounting_policy_hash": ordered[0]["accounting_policy_hash"],
        "cost_allocation_policy_id": ordered[0][
            "cost_allocation_policy_id"
        ],
        "cost_allocation_policy_hash": ordered[0][
            "cost_allocation_policy_hash"
        ],
        "split_policy_id": split_policy_id,
        "split_policy_hash": split_policy_hash,
        "statistical_design_policy_id": statistical_design_policy_id,
        "statistical_design_policy_hash": statistical_design_policy_hash,
        "experiment_manifest_id": experiment_manifest_id,
        "experiment_manifest_hash": experiment_manifest_hash,
        "scope": {
            **{name: first_scope[name] for name in identity_fields},
            "evaluation_window_start": observations[0]["period_start"],
            "evaluation_window_end": observations[-1]["period_end"],
        },
        "approved_production_capital_usdt": canonical_decimal(
            approved_capital
        ),
        "capital_normalization": "MONTHLY_RESET_TO_APPROVED_CAPITAL",
        "series_kind": "MONTHLY_ECONOMIC_PNL_USDT",
        "aggregation": "MEAN",
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
        "generated_at": generated_at,
        "replay_verified": True,
    }
    artifact["series_hash"] = statistical_series_hash(artifact)
    reasons = statistical_series_reasons(artifact)
    if reasons:
        raise ValueError(f"invalid statistical series: {reasons}")
    return artifact


@_fixed_decimal_context
def paired_ai_delta_series_snapshot(
    *,
    series_id: str,
    baseline_series_snapshot: Mapping[str, Any],
    ai_series_snapshot: Mapping[str, Any],
    model_bundle_id: str,
    model_bundle_hash: str,
    ai_endpoint: str,
    generated_at: str,
) -> Dict[str, Any]:
    """Build a replayable AI-minus-baseline series from exact paired facts."""

    _require_id(series_id, "series_id")
    _require_id(model_bundle_id, "model_bundle_id")
    _require_hash(model_bundle_hash, "model_bundle_hash")
    if ai_endpoint not in ("GROWTH", "RISK_EFFICIENCY"):
        raise ValueError("AI endpoint is invalid")
    baseline = deepcopy(dict(baseline_series_snapshot))
    ai = deepcopy(dict(ai_series_snapshot))
    observations, report = _derive_pairing(baseline, ai)
    ai_scope = ai["scope"]
    baseline_scope = baseline["scope"]
    artifact = {
        "$schema": "./statistical-series-snapshot-v1.schema.json",
        "schema_version": "1.1.0",
        "series_id": series_id,
        "series_hash": "0" * 64,
        "hash_algorithm": "SHA-256",
        "canonicalization": "RFC8785_JCS",
        "source_economic_snapshot_hashes": [
            *baseline["source_economic_snapshot_hashes"],
            *ai["source_economic_snapshot_hashes"],
        ],
        "source_arm_series": {
            "baseline": baseline,
            "ai": ai,
        },
        "baseline_recipe_release_id": baseline_scope[
            "recipe_release_id"
        ],
        "baseline_recipe_release_hash": baseline_scope[
            "recipe_release_hash"
        ],
        "model_bundle_id": model_bundle_id,
        "model_bundle_hash": model_bundle_hash,
        "ai_endpoint": ai_endpoint,
        "pairing_rule": "PROPOSAL_ID_PLUS_DECISION_TIME",
        "eligibility_rule": "AI_ACTION_OR_ABSOLUTE_EXPOSURE_CHANGED",
        "pairing_report": report,
        "accounting_policy_id": ai["accounting_policy_id"],
        "accounting_policy_hash": ai["accounting_policy_hash"],
        "cost_allocation_policy_id": ai["cost_allocation_policy_id"],
        "cost_allocation_policy_hash": ai["cost_allocation_policy_hash"],
        "split_policy_id": ai["split_policy_id"],
        "split_policy_hash": ai["split_policy_hash"],
        "statistical_design_policy_id": ai[
            "statistical_design_policy_id"
        ],
        "statistical_design_policy_hash": ai[
            "statistical_design_policy_hash"
        ],
        "experiment_manifest_id": ai["experiment_manifest_id"],
        "experiment_manifest_hash": ai["experiment_manifest_hash"],
        "scope": {
            **dict(ai_scope),
            "evaluation_ledger": "PAIRED_COMPARISON",
        },
        "approved_production_capital_usdt": ai[
            "approved_production_capital_usdt"
        ],
        "capital_normalization": "APPROVED_CAPITAL_EVALUATION_WINDOW",
        "series_kind": "PAIRED_AI_ECONOMIC_NET_LOG_GROWTH_DELTA",
        "aggregation": "SUM",
        "observations": observations,
        "bootstrap_design": deepcopy(ai["bootstrap_design"]),
        "generated_at": generated_at,
        "replay_verified": True,
    }
    artifact["series_hash"] = statistical_series_hash(artifact)
    reasons = statistical_series_reasons(artifact)
    if reasons:
        raise ValueError(f"invalid paired statistical series: {reasons}")
    return artifact
