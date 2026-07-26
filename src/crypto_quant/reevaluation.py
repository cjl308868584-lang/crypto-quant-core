"""Deterministic selected-endpoint reevaluation after concentration removal."""

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .canonical import business_hash, canonical_decimal, stable_id
from .errors import CanonicalizationError
from .evidence import artifact_self_hash
from .statistics import (
    one_sided_95_paired_moving_block_bootstrap,
    paired_ai_delta_series_snapshot,
    statistical_series_hash,
    statistical_series_reasons,
)


_FOLD_METHOD = "MAX_POSITIVE_DELTA_FOLD"
_EVENT_METHOD = "MAX_POSITIVE_DELTA_EVENT"
_SUPPORTED_ESTIMATOR = "ONE_SIDED_95_PAIRED_MOVING_BLOCK_BOOTSTRAP_V1"


def endpoint_reevaluation_hash(snapshot: Mapping[str, Any]) -> str:
    return artifact_self_hash(snapshot, "reevaluation_hash")


def _same_business_value(left: Any, right: Any) -> bool:
    try:
        return business_hash(left) == business_hash(right)
    except CanonicalizationError:
        return False


def _eligible_observations(
    paired_series: Mapping[str, Any],
) -> Tuple[Mapping[str, Any], ...]:
    return tuple(
        observation
        for observation in paired_series.get("observations", ())
        if isinstance(observation, Mapping)
        and observation.get("eligible") is True
    )


def _selected_exclusion(
    paired_series: Mapping[str, Any],
    method: str,
) -> Tuple[Optional[str], Decimal]:
    observations = _eligible_observations(paired_series)
    if method == _FOLD_METHOD:
        contributions: Dict[str, Decimal] = {}
        for observation in observations:
            fold_id = observation["fold_id"]
            contributions[fold_id] = (
                contributions.get(fold_id, Decimal("0"))
                + Decimal(canonical_decimal(observation["value"]))
            )
        ranked = sorted(
            (
                (-value, fold_id)
                for fold_id, value in contributions.items()
                if value > 0
            )
        )
        if not ranked:
            return None, Decimal("0")
        selected = ranked[0][1]
        return selected, contributions[selected]
    if method == _EVENT_METHOD:
        ranked_events = sorted(
            (
                observation
                for observation in observations
                if Decimal(canonical_decimal(observation["value"])) > 0
            ),
            key=lambda observation: (
                -Decimal(canonical_decimal(observation["value"])),
                observation["proposal_id"],
                observation["decision_time"],
            ),
        )
        if not ranked_events:
            return None, Decimal("0")
        selected_event = ranked_events[0]
        return (
            selected_event["observation_id"],
            Decimal(canonical_decimal(selected_event["value"])),
        )
    raise ValueError("unsupported endpoint reevaluation exclusion method")


def _filtered_arm_series(
    arm: Mapping[str, Any],
    *,
    paired_series: Mapping[str, Any],
    method: str,
    excluded_unit_id: Optional[str],
    arm_name: str,
    generated_at: str,
) -> Dict[str, Any]:
    excluded_observation_ids = set()
    if excluded_unit_id is not None:
        for pair in paired_series["observations"]:
            should_exclude = (
                pair["fold_id"] == excluded_unit_id
                if method == _FOLD_METHOD
                else pair["observation_id"] == excluded_unit_id
            )
            if should_exclude:
                excluded_observation_ids.add(
                    pair[f"{arm_name}_observation_id"]
                )
    filtered = deepcopy(dict(arm))
    filtered["series_id"] = stable_id(
        "reevaluated-arm",
        {
            "source_series_hash": arm["series_hash"],
            "method": method,
            "excluded_unit_id": excluded_unit_id,
        },
    )
    filtered["observations"] = [
        observation
        for observation in filtered["observations"]
        if observation["observation_id"] not in excluded_observation_ids
    ]
    filtered["source_economic_snapshot_hashes"] = [
        observation["source_economic_snapshot_hash"]
        for observation in filtered["observations"]
    ]
    filtered["generated_at"] = generated_at
    filtered["series_hash"] = statistical_series_hash(filtered)
    reasons = statistical_series_reasons(filtered)
    if reasons:
        raise ValueError(f"invalid filtered {arm_name} series: {reasons}")
    return filtered


def _rebuild_paired_series(
    source: Mapping[str, Any],
    *,
    method: str,
    excluded_unit_id: Optional[str],
    generated_at: str,
) -> Dict[str, Any]:
    arms = source["source_arm_series"]
    baseline = _filtered_arm_series(
        arms["baseline"],
        paired_series=source,
        method=method,
        excluded_unit_id=excluded_unit_id,
        arm_name="baseline",
        generated_at=generated_at,
    )
    ai = _filtered_arm_series(
        arms["ai"],
        paired_series=source,
        method=method,
        excluded_unit_id=excluded_unit_id,
        arm_name="ai",
        generated_at=generated_at,
    )
    return paired_ai_delta_series_snapshot(
        series_id=stable_id(
            "endpoint-reevaluation-series",
            {
                "source_series_hash": source["series_hash"],
                "method": method,
                "excluded_unit_id": excluded_unit_id,
            },
        ),
        baseline_series_snapshot=baseline,
        ai_series_snapshot=ai,
        model_bundle_id=source["model_bundle_id"],
        model_bundle_hash=source["model_bundle_hash"],
        ai_endpoint=source["ai_endpoint"],
        generated_at=generated_at,
    )


def _coerce_threshold(value: Any) -> Decimal:
    return Decimal(canonical_decimal(value))


def _comparison(comparator: str, left: Decimal, right: Decimal) -> bool:
    operations = {
        "GT": left > right,
        "GTE": left >= right,
        "LT": left < right,
        "LTE": left <= right,
        "EQ": left == right,
        "NEQ": left != right,
    }
    if comparator not in operations:
        raise ValueError("unsupported endpoint comparator")
    return operations[comparator]


def _evaluate_growth_gates(
    paired_series: Mapping[str, Any],
    gate_definitions: Sequence[Mapping[str, Any]],
) -> Tuple[str, Any, Tuple[str, ...], Sequence[Dict[str, Any]]]:
    if len(gate_definitions) != 1:
        return (
            "FAIL",
            None,
            ("ENDPOINT_REEVALUATION_GATE_SET_UNSUPPORTED",),
            (),
        )
    gate = gate_definitions[0]
    if (
        gate.get("required") is not True
        or gate.get("estimator_id") != _SUPPORTED_ESTIMATOR
        or "threshold" not in gate
        or "threshold_ast" in gate
        or "threshold_ref" in gate
    ):
        return (
            "FAIL",
            None,
            ("ENDPOINT_REEVALUATION_GATE_DEFINITION_UNSUPPORTED",),
            (),
        )
    execution_status, value, reasons = (
        one_sided_95_paired_moving_block_bootstrap(
            {"statistical_series_snapshot": paired_series}
        )
    )
    if execution_status != "COMPUTED":
        return execution_status, None, reasons, ()
    try:
        observed = Decimal(canonical_decimal(value))
        threshold = _coerce_threshold(gate["threshold"])
        passed = _comparison(gate["comparator"], observed, threshold)
    except (CanonicalizationError, ValueError):
        return (
            "FAIL",
            None,
            ("ENDPOINT_REEVALUATION_THRESHOLD_INVALID",),
            (),
        )
    gate_payload = {
        "gate_id": gate["gate_id"],
        "metric_id": gate["metric_id"],
        "estimator_id": gate["estimator_id"],
        "estimator_status": execution_status,
        "observed_value": canonical_decimal(observed),
        "comparator": gate["comparator"],
        "threshold_value": canonical_decimal(threshold),
        "result": "PASS" if passed else "FAIL",
    }
    gate_payload["result_hash"] = business_hash(gate_payload)
    return (
        "COMPUTED",
        passed,
        (),
        (gate_payload,),
    )


def _expected_snapshot(
    snapshot: Mapping[str, Any],
    *,
    source_paired_series: Mapping[str, Any],
    endpoint_gate_definitions: Sequence[Mapping[str, Any]],
    policy_identity: Mapping[str, Any],
    expected_method: str,
) -> Tuple[str, Any, Tuple[str, ...], Optional[Dict[str, Any]]]:
    source = source_paired_series
    source_reasons = statistical_series_reasons(source)
    if source_reasons:
        return (
            "FAIL",
            None,
            tuple(
                f"ENDPOINT_REEVALUATION_SOURCE:{reason}"
                for reason in source_reasons
            ),
            None,
        )
    if source.get("ai_endpoint") != "GROWTH":
        return (
            "INCONCLUSIVE",
            None,
            ("ENDPOINT_REEVALUATION_ENDPOINT_NOT_EXECUTABLE",),
            None,
        )
    expected_group = (
        "AI_ENDPOINT.GROWTH"
        if expected_method == _FOLD_METHOD
        else "AUDIT_AI_ENDPOINT.GROWTH"
    )
    if snapshot.get("endpoint_gate_group_id") != expected_group:
        return (
            "FAIL",
            None,
            ("ENDPOINT_REEVALUATION_GATE_GROUP_MISMATCH",),
            None,
        )
    if snapshot.get("exclusion_method") != expected_method:
        return (
            "FAIL",
            None,
            ("ENDPOINT_REEVALUATION_METHOD_MISMATCH",),
            None,
        )
    selected_id, contribution = _selected_exclusion(source, expected_method)
    remaining_pairs = [
        pair
        for pair in source["observations"]
        if (
            pair["fold_id"] != selected_id
            if expected_method == _FOLD_METHOD
            else pair["observation_id"] != selected_id
        )
    ]
    if remaining_pairs:
        rebuilt = _rebuild_paired_series(
            source,
            method=expected_method,
            excluded_unit_id=selected_id,
            generated_at=snapshot["generated_at"],
        )
        rebuilt_hash = rebuilt["series_hash"]
        status, value, reasons, gate_results = _evaluate_growth_gates(
            rebuilt,
            endpoint_gate_definitions,
        )
    else:
        rebuilt_hash = business_hash(
            {
                "source_paired_series_hash": source["series_hash"],
                "exclusion_method": expected_method,
                "excluded_unit_id": selected_id,
                "status": "NO_MATCHED_PAIRS_AFTER_EXCLUSION",
            }
        )
        status = "INCONCLUSIVE"
        value = None
        reasons = ("PAIRED_SERIES_EMPTY_AFTER_EXCLUSION",)
        gate_results = ()
    expected = {
        "$schema": "./endpoint-reevaluation-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "reevaluation_id": snapshot["reevaluation_id"],
        "reevaluation_hash": "0" * 64,
        "hash_algorithm": "SHA-256",
        "canonicalization": "RFC8785_JCS",
        "release_gate_policy_id": policy_identity[
            "release_gate_policy_id"
        ],
        "release_gate_policy_version": policy_identity[
            "release_gate_policy_version"
        ],
        "metric_catalog_id": policy_identity["metric_catalog_id"],
        "metric_catalog_version": policy_identity[
            "metric_catalog_version"
        ],
        "ai_endpoint": "GROWTH",
        "endpoint_gate_group_id": snapshot["endpoint_gate_group_id"],
        "exclusion_method": expected_method,
        "excluded_unit_id": selected_id,
        "excluded_positive_delta_contribution": canonical_decimal(
            contribution
        ),
        "source_paired_series_hash": source["series_hash"],
        "reevaluated_paired_series_hash": rebuilt_hash,
        "endpoint_gate_definitions": deepcopy(list(endpoint_gate_definitions)),
        "gate_results": list(gate_results),
        "result": (
            "PASS"
            if status == "COMPUTED" and value is True
            else "FAIL"
            if status in ("COMPUTED", "FAIL")
            else "INCONCLUSIVE"
        ),
        "generated_at": snapshot["generated_at"],
    }
    expected["reevaluation_hash"] = endpoint_reevaluation_hash(expected)
    return status, value, reasons, expected


def build_endpoint_reevaluation_snapshot(
    *,
    reevaluation_id: str,
    source_paired_series: Mapping[str, Any],
    endpoint_gate_group_id: str,
    endpoint_gate_definitions: Sequence[Mapping[str, Any]],
    policy_identity: Mapping[str, Any],
    exclusion_method: str,
    generated_at: str,
) -> Dict[str, Any]:
    """Build a replayable full selected-endpoint reevaluation artifact."""

    seed = {
        "reevaluation_id": reevaluation_id,
        "endpoint_gate_group_id": endpoint_gate_group_id,
        "exclusion_method": exclusion_method,
        "generated_at": generated_at,
    }
    status, _, reasons, expected = _expected_snapshot(
        seed,
        source_paired_series=source_paired_series,
        endpoint_gate_definitions=endpoint_gate_definitions,
        policy_identity=policy_identity,
        expected_method=exclusion_method,
    )
    if expected is None or status == "FAIL":
        raise ValueError(f"endpoint reevaluation cannot be built: {reasons}")
    return expected


def _execute_endpoint_reevaluation(
    inputs: Mapping[str, Any],
    *,
    expected_method: str,
) -> Tuple[str, Any, Tuple[str, ...]]:
    snapshot = inputs.get("endpoint_reevaluation_snapshot")
    source = inputs.get("statistical_series_snapshot")
    gate_definitions = inputs.get("endpoint_gate_definitions")
    policy_identity = inputs.get("policy_identity")
    if (
        not isinstance(snapshot, Mapping)
        or not isinstance(source, Mapping)
        or not isinstance(gate_definitions, Sequence)
        or isinstance(gate_definitions, (str, bytes))
        or not isinstance(policy_identity, Mapping)
    ):
        return (
            "FAIL",
            None,
            ("ENDPOINT_REEVALUATION_INPUT_INVALID",),
        )
    try:
        if snapshot.get("reevaluation_hash") != endpoint_reevaluation_hash(
            snapshot
        ):
            return (
                "FAIL",
                None,
                ("ENDPOINT_REEVALUATION_HASH_MISMATCH",),
            )
        if snapshot.get("source_paired_series_hash") != source.get(
            "series_hash"
        ):
            return (
                "FAIL",
                None,
                ("ENDPOINT_REEVALUATION_SOURCE_HASH_MISMATCH",),
            )
        if snapshot.get("ai_endpoint") != source.get("ai_endpoint"):
            return (
                "FAIL",
                None,
                ("ENDPOINT_REEVALUATION_ENDPOINT_MISMATCH",),
            )
        if any(
            snapshot.get(name) != policy_identity.get(name)
            for name in (
                "release_gate_policy_id",
                "release_gate_policy_version",
                "metric_catalog_id",
                "metric_catalog_version",
            )
        ):
            return (
                "FAIL",
                None,
                ("ENDPOINT_REEVALUATION_POLICY_MISMATCH",),
            )
        if not _same_business_value(
            snapshot.get("endpoint_gate_definitions"),
            gate_definitions,
        ):
            return (
                "FAIL",
                None,
                ("ENDPOINT_REEVALUATION_GATE_SET_MISMATCH",),
            )
    except (CanonicalizationError, TypeError, ValueError):
        return (
            "FAIL",
            None,
            ("ENDPOINT_REEVALUATION_INPUT_INVALID",),
        )
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        try:
            status, value, reasons, expected = _expected_snapshot(
                snapshot,
                source_paired_series=source,
                endpoint_gate_definitions=gate_definitions,
                policy_identity=policy_identity,
                expected_method=expected_method,
            )
        except (
            CanonicalizationError,
            KeyError,
            TypeError,
            ValueError,
        ):
            return (
                "FAIL",
                None,
                ("ENDPOINT_REEVALUATION_REPLAY_INVALID",),
            )
    if expected is None:
        return status, value, tuple(sorted(set(reasons)))
    if not _same_business_value(snapshot, expected):
        return (
            "FAIL",
            None,
            ("ENDPOINT_REEVALUATION_REPLAY_MISMATCH",),
        )
    return status, value, tuple(sorted(set(reasons)))


def leave_max_positive_delta_fold_out_endpoint_reevaluation(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    return _execute_endpoint_reevaluation(
        inputs,
        expected_method=_FOLD_METHOD,
    )


def leave_max_positive_delta_event_out_endpoint_reevaluation(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    return _execute_endpoint_reevaluation(
        inputs,
        expected_method=_EVENT_METHOD,
    )
