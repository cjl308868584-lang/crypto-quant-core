"""Immutable release-artifact validation and supporting observations."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Set, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash
from .errors import CanonicalizationError, PolicyError
from .estimators import EstimatorRegistry, _load_json_strict
from .evidence import artifact_self_hash


_STAGE_ORDER = (
    "RECIPE_CANDIDATE",
    "SHADOW",
    "PAPER",
    "CANARY_25",
    "CANARY_50",
    "CANARY_75",
    "CHAMPION",
)

_RECIPE_DESIGN_FIELDS = (
    "strategy_proposal_hash",
    "feature_schema_hash",
    "label_definition_hash",
    "model_family_hash",
    "hyperparameter_search_space_hash",
    "calibration_method_hash",
    "decision_thresholds_hash",
    "position_policy_hash",
    "risk_policy_hash",
    "execution_fill_model_hash",
    "data_source_policy_hash",
    "cost_definition_hash",
    "accounting_policy_hash",
    "interface_compatibility_hash",
    "data_quality_policy_hash",
    "split_policy_hash",
    "statistical_design_policy_hash",
    "cost_allocation_policy_hash",
    "forward_control_policy_hash",
    "release_gate_policy_hash",
    "policy_bundle_hash",
)


@dataclass(frozen=True)
class ReleaseArtifactValidation:
    valid: bool
    reason_codes: Tuple[str, ...]
    validation_hash: str


@dataclass(frozen=True)
class SupportingObservationValidation:
    valid: bool
    observations: Mapping[str, Any]
    inconclusive_metrics: Tuple[str, ...]
    execution_hashes: Tuple[str, ...]
    reason_codes: Tuple[str, ...]
    validation_hash: str


def load_release_artifact_schemas(
    config_dir: Path,
) -> Mapping[str, Mapping[str, Any]]:
    schemas = {
        "experiment_manifest": _load_json_strict(
            Path(config_dir) / "experiment-manifest-v1.1.schema.json"
        ),
        "deployment_line": _load_json_strict(
            Path(config_dir) / "deployment-line-v1.1.schema.json"
        ),
        "supporting_observation_bundle": _load_json_strict(
            Path(config_dir) / "supporting-observation-bundle-v1.schema.json"
        ),
        "endpoint_reevaluation_snapshot": _load_json_strict(
            Path(config_dir)
            / "endpoint-reevaluation-snapshot-v1.schema.json"
        ),
    }
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    return schemas


def experiment_manifest_hash(manifest: Mapping[str, Any]) -> str:
    """Hash pre-registered experiment content without the circular Recipe link."""

    body = dict(manifest)
    body.pop("experiment_manifest_hash", None)
    body.pop("recipe_binding", None)
    body.pop("manifest_attestation", None)
    return business_hash(body)


def experiment_recipe_binding_hash(manifest: Mapping[str, Any]) -> str:
    binding = manifest.get("recipe_binding")
    if not isinstance(binding, Mapping):
        raise CanonicalizationError("experiment recipe binding missing")
    return business_hash(
        {
            "experiment_manifest_hash": manifest.get(
                "experiment_manifest_hash"
            ),
            "recipe_release_id": binding.get("recipe_release_id"),
            "recipe_release_hash": binding.get("recipe_release_hash"),
        }
    )


def deployment_line_hash(line: Mapping[str, Any]) -> str:
    return artifact_self_hash(
        line,
        "deployment_line_hash",
        "line_attestation",
    )


def supporting_observation_hash(observation: Mapping[str, Any]) -> str:
    return artifact_self_hash(observation, "observation_hash")


def supporting_observation_bundle_hash(bundle: Mapping[str, Any]) -> str:
    return artifact_self_hash(
        bundle,
        "bundle_hash",
        "bundle_attestation",
    )


def _schema_reasons(
    schema: Mapping[str, Any],
    artifact: Mapping[str, Any],
    prefix: str,
) -> Tuple[str, ...]:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(artifact),
        key=lambda error: (
            "/".join(map(str, error.absolute_path)),
            error.message,
        ),
    )
    return tuple(
        f"{prefix}_SCHEMA:"
        + ("/".join(map(str, error.absolute_path)) or "$")
        for error in errors
    )


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp is not timezone aware")
    return parsed


def _same_value(left: Any, right: Any) -> bool:
    try:
        return business_hash(left) == business_hash(right)
    except CanonicalizationError:
        return False


def _result(
    artifact_id: Any,
    reasons: Sequence[str],
) -> ReleaseArtifactValidation:
    reason_codes = tuple(sorted(set(reasons)))
    return ReleaseArtifactValidation(
        valid=not reason_codes,
        reason_codes=reason_codes,
        validation_hash=business_hash(
            {
                "artifact_id": artifact_id,
                "valid": not reason_codes,
                "reason_codes": reason_codes,
            }
        ),
    )


def validate_experiment_manifest(
    manifest: Mapping[str, Any],
    *,
    schema: Mapping[str, Any],
    recipe: Mapping[str, Any],
    evidence: Mapping[str, Any],
    verified_attestations: Mapping[str, str],
) -> ReleaseArtifactValidation:
    reasons = list(_schema_reasons(schema, manifest, "EXPERIMENT_MANIFEST"))
    try:
        computed_manifest_hash = experiment_manifest_hash(manifest)
    except CanonicalizationError:
        computed_manifest_hash = ""
    if manifest.get("experiment_manifest_hash") != computed_manifest_hash:
        reasons.append("EXPERIMENT_MANIFEST_SELF_HASH_MISMATCH")

    try:
        computed_binding_hash = experiment_recipe_binding_hash(manifest)
    except CanonicalizationError:
        computed_binding_hash = ""
    binding = manifest.get("recipe_binding")
    if not isinstance(binding, Mapping):
        binding = {}
    if binding.get("recipe_binding_hash") != computed_binding_hash:
        reasons.append("EXPERIMENT_RECIPE_BINDING_HASH_MISMATCH")
    attestation = manifest.get("manifest_attestation")
    signature = (
        attestation.get("signature_base64")
        if isinstance(attestation, Mapping)
        else None
    )
    if verified_attestations.get(signature) != computed_binding_hash:
        reasons.append("EXPERIMENT_MANIFEST_ATTESTATION_UNVERIFIED")

    reference_fields = (
        "release_route",
        "ai_endpoint",
        "baseline_recipe_release_id",
        "baseline_recipe_release_hash",
    )
    for name in reference_fields:
        if manifest.get(name) != recipe.get(name):
            reasons.append(f"EXPERIMENT_REFERENCE_MISMATCH:{name}")
        if name in evidence and manifest.get(name) != evidence.get(name):
            reasons.append(f"EXPERIMENT_EVIDENCE_MISMATCH:{name}")
    for name in ("recipe_release_id", "recipe_release_hash"):
        if (
            binding.get(name) != recipe.get(name)
            or binding.get(name) != evidence.get(name)
        ):
            reasons.append(f"EXPERIMENT_RECIPE_REFERENCE_MISMATCH:{name}")
    if (
        recipe.get("experiment_manifest_hash")
        != manifest.get("experiment_manifest_hash")
    ):
        reasons.append("RECIPE_EXPERIMENT_MANIFEST_HASH_MISMATCH")

    design = manifest.get("frozen_design_hashes")
    if not isinstance(design, Mapping):
        design = {}
    for name in _RECIPE_DESIGN_FIELDS:
        if design.get(name) != recipe.get(name):
            reasons.append(f"EXPERIMENT_DESIGN_HASH_MISMATCH:{name}")
    data = manifest.get("data")
    if (
        isinstance(data, Mapping)
        and data.get("data_source_policy_hash")
        != recipe.get("data_source_policy_hash")
    ):
        reasons.append("EXPERIMENT_DATA_SOURCE_POLICY_HASH_MISMATCH")
    search = manifest.get("search_budget")
    if (
        isinstance(search, Mapping)
        and search.get("hyperparameter_search_space_hash")
        != recipe.get("hyperparameter_search_space_hash")
    ):
        reasons.append("EXPERIMENT_SEARCH_SPACE_HASH_MISMATCH")

    if manifest.get("status") != "COMPLETED":
        reasons.append("EXPERIMENT_MANIFEST_NOT_COMPLETED")
    outputs = manifest.get("outputs")
    if (
        not isinstance(outputs, Mapping)
        or outputs.get("conclusion") != "CANDIDATE"
    ):
        reasons.append("EXPERIMENT_CONCLUSION_NOT_CANDIDATE")
    if isinstance(search, Mapping):
        budget = search.get("predeclared_trial_budget")
        actual = search.get("actual_total_trials")
        if isinstance(budget, int) and isinstance(actual, int) and actual > budget:
            reasons.append("EXPERIMENT_TRIAL_BUDGET_EXCEEDED")
        counted = sum(
            value
            for value in (
                search.get("aborted_trials"),
                search.get("failed_trials"),
                search.get("invalid_trials"),
            )
            if isinstance(value, int)
        )
        if isinstance(actual, int) and counted > actual:
            reasons.append("EXPERIMENT_TRIAL_OUTCOME_COUNT_EXCEEDED")

    parent_ids = manifest.get("parent_experiment_ids")
    if (
        isinstance(parent_ids, list)
        and manifest.get("experiment_id") in parent_ids
    ):
        reasons.append("EXPERIMENT_SELF_PARENT")

    data_windows = data.get("windows") if isinstance(data, Mapping) else None
    if isinstance(data_windows, list):
        roles = []
        previous_end: Optional[datetime] = None
        for window in data_windows:
            if not isinstance(window, Mapping):
                continue
            roles.append(window.get("role"))
            try:
                start = _timestamp(window.get("start"))
                end = _timestamp(window.get("end"))
                if end <= start:
                    reasons.append("EXPERIMENT_DATA_WINDOW_NOT_INCREASING")
                if previous_end is not None and start < previous_end:
                    reasons.append("EXPERIMENT_DATA_WINDOWS_OVERLAP")
                previous_end = end
            except (TypeError, ValueError):
                reasons.append("EXPERIMENT_DATA_WINDOW_TIME_INVALID")
        if len(roles) != len(set(roles)):
            reasons.append("EXPERIMENT_DATA_WINDOW_ROLE_DUPLICATE")

    economics = manifest.get("economics")
    if isinstance(economics, Mapping):
        try:
            if _timestamp(economics.get("evaluation_window_end")) <= _timestamp(
                economics.get("evaluation_window_start")
            ):
                reasons.append("EXPERIMENT_EVALUATION_WINDOW_NOT_INCREASING")
        except (TypeError, ValueError):
            reasons.append("EXPERIMENT_EVALUATION_WINDOW_TIME_INVALID")
        if not _same_value(
            economics.get("approved_production_capital_usdt"),
            evidence.get("approved_production_capital_usdt"),
        ):
            reasons.append("EXPERIMENT_APPROVED_CAPITAL_MISMATCH")

    try:
        created_at = _timestamp(manifest.get("created_at"))
        frozen_at = _timestamp(manifest.get("route_and_endpoint_frozen_at"))
        reveal_at = _timestamp(evidence.get("first_result_revealed_at"))
        if frozen_at < created_at:
            reasons.append("EXPERIMENT_FROZEN_BEFORE_CREATE")
        if frozen_at >= reveal_at:
            reasons.append("EXPERIMENT_FROZEN_AFTER_RESULT_REVEAL")
    except (TypeError, ValueError):
        reasons.append("EXPERIMENT_FREEZE_TIME_INVALID")
    if isinstance(attestation, Mapping):
        try:
            signed_at = _timestamp(attestation.get("signed_at"))
            if signed_at < _timestamp(
                manifest.get("route_and_endpoint_frozen_at")
            ):
                reasons.append("EXPERIMENT_ATTESTED_BEFORE_FREEZE")
            if signed_at >= _timestamp(evidence.get("first_result_revealed_at")):
                reasons.append(
                    "EXPERIMENT_ATTESTED_AFTER_RESULT_REVEAL"
                )
        except (TypeError, ValueError):
            reasons.append("EXPERIMENT_ATTESTATION_TIME_INVALID")

    return _result(manifest.get("experiment_id"), reasons)


def validate_deployment_line(
    line: Mapping[str, Any],
    *,
    schema: Mapping[str, Any],
    recipe: Mapping[str, Any],
    experiment: Mapping[str, Any],
    model: Optional[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    verified_attestations: Mapping[str, str],
) -> ReleaseArtifactValidation:
    reasons = list(_schema_reasons(schema, line, "DEPLOYMENT_LINE"))
    try:
        computed_hash = deployment_line_hash(line)
    except CanonicalizationError:
        computed_hash = ""
    if line.get("deployment_line_hash") != computed_hash:
        reasons.append("DEPLOYMENT_LINE_SELF_HASH_MISMATCH")
    attestation = line.get("line_attestation")
    signature = (
        attestation.get("signature_base64")
        if isinstance(attestation, Mapping)
        else None
    )
    if verified_attestations.get(signature) != computed_hash:
        reasons.append("DEPLOYMENT_LINE_ATTESTATION_UNVERIFIED")

    reference_sources = {
        "deployment_line_id": evidence,
        "release_kind": recipe,
        "recipe_release_id": evidence,
        "recipe_release_hash": evidence,
        "release_route": evidence,
        "ai_endpoint": evidence,
        "baseline_recipe_release_id": recipe,
        "baseline_recipe_release_hash": recipe,
        "direction": evidence,
        "venue": evidence,
    }
    for name, source in reference_sources.items():
        expected = source.get(name)
        if line.get(name) != expected:
            reasons.append(f"DEPLOYMENT_LINE_REFERENCE_MISMATCH:{name}")
    if line.get("experiment_manifest_hash") != experiment.get(
        "experiment_manifest_hash"
    ):
        reasons.append("DEPLOYMENT_LINE_EXPERIMENT_HASH_MISMATCH")
    evidence_stage = evidence.get("stage")
    expected_stage = (
        "RECIPE_CANDIDATE"
        if evidence_stage in ("OFFLINE_OOS", "RELEASE_AUDIT")
        else evidence_stage
    )
    if (
        evidence_stage != "MINOR_REFRESH"
        and line.get("current_stage") != expected_stage
    ):
        reasons.append("DEPLOYMENT_LINE_STAGE_MISMATCH")
    if line.get("lifecycle_status") != "ACTIVE":
        reasons.append("DEPLOYMENT_LINE_NOT_ACTIVE")
    if line.get("direction") not in recipe.get("directions", ()):
        reasons.append("DEPLOYMENT_LINE_DIRECTION_NOT_IN_RECIPE")
    if line.get("venue") not in recipe.get("venues", ()):
        reasons.append("DEPLOYMENT_LINE_VENUE_NOT_IN_RECIPE")

    if line.get("release_route") == "AI_ENHANCED":
        if not isinstance(model, Mapping):
            reasons.append("DEPLOYMENT_LINE_MODEL_DOCUMENT_MISSING")
        else:
            if line.get("active_model_bundle_id") != model.get(
                "model_bundle_id"
            ):
                reasons.append("DEPLOYMENT_LINE_ACTIVE_MODEL_ID_MISMATCH")
            if line.get("active_model_bundle_hash") != model.get(
                "model_bundle_hash"
            ):
                reasons.append("DEPLOYMENT_LINE_ACTIVE_MODEL_HASH_MISMATCH")
            if model.get("deployment_line_id") != line.get(
                "deployment_line_id"
            ):
                reasons.append("MODEL_DEPLOYMENT_LINE_REFERENCE_MISMATCH")

    history = line.get("stage_history")
    if isinstance(history, list):
        stages = [
            item.get("stage")
            for item in history
            if isinstance(item, Mapping)
        ]
        if tuple(stages) != _STAGE_ORDER[: len(stages)]:
            reasons.append("DEPLOYMENT_LINE_STAGE_SEQUENCE_INVALID")
        if stages and stages[-1] != line.get("current_stage"):
            reasons.append("DEPLOYMENT_LINE_CURRENT_STAGE_NOT_LAST")
        previous_exit: Optional[datetime] = None
        for index, record in enumerate(history):
            if not isinstance(record, Mapping):
                continue
            try:
                entered = _timestamp(record.get("entered_at"))
                exited_value = record.get("exited_at")
                exited = (
                    _timestamp(exited_value)
                    if exited_value is not None
                    else None
                )
                if previous_exit is not None and entered < previous_exit:
                    reasons.append("DEPLOYMENT_LINE_STAGE_TIME_OVERLAP")
                if entered < _timestamp(line.get("created_at")):
                    reasons.append(
                        "DEPLOYMENT_LINE_STAGE_BEFORE_LINE_CREATE"
                    )
                if exited is not None and exited <= entered:
                    reasons.append("DEPLOYMENT_LINE_STAGE_TIME_INVALID")
                if index < len(history) - 1:
                    if exited is None or record.get("result") != "PASS":
                        reasons.append(
                            "DEPLOYMENT_LINE_PRIOR_STAGE_NOT_PASSED"
                        )
                    if record.get("evidence_hash") is None:
                        reasons.append(
                            "DEPLOYMENT_LINE_PRIOR_STAGE_EVIDENCE_MISSING"
                        )
                else:
                    if exited is not None:
                        reasons.append(
                            "DEPLOYMENT_LINE_CURRENT_STAGE_ALREADY_EXITED"
                        )
                    if record.get("result") != "IN_PROGRESS":
                        reasons.append(
                            "DEPLOYMENT_LINE_CURRENT_STAGE_NOT_IN_PROGRESS"
                        )
                previous_exit = exited
            except (TypeError, ValueError):
                reasons.append("DEPLOYMENT_LINE_STAGE_TIME_INVALID")
    try:
        created = _timestamp(line.get("created_at"))
        updated = _timestamp(line.get("updated_at"))
        reveal = _timestamp(evidence.get("first_result_revealed_at"))
        if updated < created:
            reasons.append("DEPLOYMENT_LINE_UPDATE_BEFORE_CREATE")
        if updated >= reveal:
            reasons.append("DEPLOYMENT_LINE_UPDATED_AFTER_RESULT_REVEAL")
        if isinstance(attestation, Mapping):
            signed_at = _timestamp(attestation.get("signed_at"))
            if signed_at < updated:
                reasons.append("DEPLOYMENT_LINE_ATTESTED_BEFORE_UPDATE")
            if signed_at >= reveal:
                reasons.append("DEPLOYMENT_LINE_ATTESTED_AFTER_RESULT_REVEAL")
    except (TypeError, ValueError):
        reasons.append("DEPLOYMENT_LINE_TIME_INVALID")

    return _result(line.get("deployment_line_id"), reasons)


def validate_supporting_observation_bundle(
    bundle: Mapping[str, Any],
    *,
    schema: Mapping[str, Any],
    expected_scope: Mapping[str, Any],
    policy_bundle_hash: str,
    evaluator_build_hash: str,
    resolve_metric: Callable[[str], Mapping[str, Any]],
    estimators: EstimatorRegistry,
    allowed_source_hashes: Set[str],
    verified_attestations: Mapping[str, str],
    first_result_revealed_at: str,
) -> SupportingObservationValidation:
    reasons = list(
        _schema_reasons(
            schema,
            bundle,
            "SUPPORTING_OBSERVATION_BUNDLE",
        )
    )
    try:
        computed_bundle_hash = supporting_observation_bundle_hash(bundle)
    except CanonicalizationError:
        computed_bundle_hash = ""
    if bundle.get("bundle_hash") != computed_bundle_hash:
        reasons.append("SUPPORTING_BUNDLE_SELF_HASH_MISMATCH")
    if bundle.get("scope_hash") != business_hash(expected_scope):
        reasons.append("SUPPORTING_BUNDLE_SCOPE_MISMATCH")
    if bundle.get("policy_bundle_hash") != policy_bundle_hash:
        reasons.append("SUPPORTING_BUNDLE_POLICY_HASH_MISMATCH")
    if bundle.get("evaluator_build_hash") != evaluator_build_hash:
        reasons.append("SUPPORTING_BUNDLE_EVALUATOR_HASH_MISMATCH")
    attestation = bundle.get("bundle_attestation")
    signature = (
        attestation.get("signature_base64")
        if isinstance(attestation, Mapping)
        else None
    )
    if verified_attestations.get(signature) != computed_bundle_hash:
        reasons.append("SUPPORTING_BUNDLE_ATTESTATION_UNVERIFIED")
    try:
        computed_at = _timestamp(bundle.get("computed_at"))
        if computed_at < _timestamp(first_result_revealed_at):
            reasons.append("SUPPORTING_BUNDLE_COMPUTED_BEFORE_REVEAL")
        if isinstance(attestation, Mapping) and _timestamp(
            attestation.get("signed_at")
        ) < computed_at:
            reasons.append("SUPPORTING_BUNDLE_ATTESTED_BEFORE_COMPUTE")
    except (TypeError, ValueError):
        reasons.append("SUPPORTING_BUNDLE_TIME_INVALID")

    observations: Dict[str, Any] = {}
    inconclusive: Set[str] = set()
    execution_hashes = []
    seen_ids = set()
    seen_metrics = set()
    items = bundle.get("observations")
    if not isinstance(items, list):
        items = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        observation_id = item.get("observation_id")
        metric_id = item.get("metric_id")
        if observation_id in seen_ids:
            reasons.append("SUPPORTING_OBSERVATION_ID_DUPLICATE")
        seen_ids.add(observation_id)
        if metric_id in seen_metrics:
            reasons.append(f"SUPPORTING_METRIC_DUPLICATE:{metric_id}")
        seen_metrics.add(metric_id)
        try:
            computed_observation_hash = supporting_observation_hash(item)
        except CanonicalizationError:
            computed_observation_hash = ""
        if item.get("observation_hash") != computed_observation_hash:
            reasons.append(
                f"SUPPORTING_OBSERVATION_SELF_HASH_MISMATCH:{metric_id}"
            )
        try:
            definition = resolve_metric(metric_id)
        except (PolicyError, TypeError):
            definition = {}
            reasons.append(f"SUPPORTING_METRIC_UNKNOWN:{metric_id}")
        if definition:
            if item.get("metric_unit") != definition.get("unit"):
                reasons.append(f"SUPPORTING_METRIC_UNIT_MISMATCH:{metric_id}")
            if item.get("estimator_id") != definition.get("estimator_id"):
                reasons.append(
                    f"SUPPORTING_METRIC_ESTIMATOR_MISMATCH:{metric_id}"
                )
        inputs = item.get("estimator_inputs")
        execution = estimators.execute(
            definition.get("estimator_id", ""),
            inputs if isinstance(inputs, Mapping) else {},
        )
        execution_hashes.append(execution.execution_hash)
        expected_execution = {
            "implementation_id": execution.implementation_id,
            "implementation_version": execution.implementation_version,
            "status": execution.status,
            "value": execution.value,
            "reason_codes": list(execution.reason_codes),
            "estimator_execution_hash": execution.execution_hash,
        }
        for name, expected in expected_execution.items():
            if not _same_value(item.get(name), expected):
                reasons.append(
                    f"SUPPORTING_ESTIMATOR_RESULT_MISMATCH:{metric_id}:{name}"
                )
        source_hashes = item.get("source_artifact_hashes")
        if not isinstance(source_hashes, list) or not set(source_hashes).issubset(
            allowed_source_hashes
        ):
            reasons.append(f"SUPPORTING_SOURCE_UNVERIFIED:{metric_id}")
        economic_snapshot = (
            inputs.get("economic_ledger_snapshot")
            if isinstance(inputs, Mapping)
            else None
        )
        if isinstance(economic_snapshot, Mapping):
            economic_scope = economic_snapshot.get("scope")
            if not isinstance(economic_scope, Mapping):
                reasons.append(
                    f"SUPPORTING_ECONOMIC_SCOPE_MISSING:{metric_id}"
                )
                economic_scope = {}
            for name in (
                "evaluation_ledger",
                "release_route",
                "direction",
                "venue",
                "recipe_release_id",
                "recipe_release_hash",
                "deployment_line_id",
                "deployment_line_hash",
                "evaluation_window_start",
                "evaluation_window_end",
            ):
                if (
                    name in expected_scope
                    and economic_scope.get(name) != expected_scope.get(name)
                ):
                    reasons.append(
                        f"SUPPORTING_ECONOMIC_SCOPE_MISMATCH:{metric_id}:{name}"
                    )
            bindings = expected_scope.get("policy_binding_hashes")
            if isinstance(bindings, Mapping):
                if economic_snapshot.get(
                    "accounting_policy_hash"
                ) != bindings.get("accounting_policy_id"):
                    reasons.append(
                        f"SUPPORTING_ECONOMIC_ACCOUNTING_POLICY_MISMATCH:{metric_id}"
                    )
                if economic_snapshot.get(
                    "cost_allocation_policy_hash"
                ) != bindings.get("cost_allocation_policy_id"):
                    reasons.append(
                        f"SUPPORTING_ECONOMIC_COST_POLICY_MISMATCH:{metric_id}"
                    )
            required_economic_sources = {
                economic_snapshot.get("snapshot_hash"),
                economic_snapshot.get("source_ledger_hash"),
                economic_snapshot.get("source_projection_hash"),
            }
            if (
                not isinstance(source_hashes, list)
                or not required_economic_sources.issubset(set(source_hashes))
            ):
                reasons.append(
                    f"SUPPORTING_ECONOMIC_SOURCE_INCOMPLETE:{metric_id}"
                )
        statistical_series = (
            inputs.get("statistical_series_snapshot")
            if isinstance(inputs, Mapping)
            else None
        )
        if isinstance(statistical_series, Mapping):
            statistical_scope = statistical_series.get("scope")
            if not isinstance(statistical_scope, Mapping):
                reasons.append(
                    f"SUPPORTING_STATISTICAL_SCOPE_MISSING:{metric_id}"
                )
                statistical_scope = {}
            for name in (
                "evaluation_ledger",
                "release_route",
                "direction",
                "venue",
                "recipe_release_id",
                "recipe_release_hash",
                "deployment_line_id",
                "deployment_line_hash",
                "evaluation_window_start",
                "evaluation_window_end",
            ):
                if (
                    name in expected_scope
                    and statistical_scope.get(name)
                    != expected_scope.get(name)
                ):
                    reasons.append(
                        f"SUPPORTING_STATISTICAL_SCOPE_MISMATCH:{metric_id}:{name}"
                    )
            bindings = expected_scope.get("policy_binding_hashes")
            if isinstance(bindings, Mapping):
                policy_fields = {
                    "accounting_policy_hash": "accounting_policy_id",
                    "cost_allocation_policy_hash": "cost_allocation_policy_id",
                    "split_policy_hash": "split_policy_id",
                    "statistical_design_policy_hash": (
                        "statistical_design_policy_id"
                    ),
                }
                for series_field, binding_name in policy_fields.items():
                    if statistical_series.get(
                        series_field
                    ) != bindings.get(binding_name):
                        reasons.append(
                            f"SUPPORTING_STATISTICAL_POLICY_MISMATCH:{metric_id}:{binding_name}"
                        )
            for name in (
                "experiment_manifest_id",
                "experiment_manifest_hash",
                "approved_production_capital_usdt",
            ):
                if (
                    name in expected_scope
                    and not _same_value(
                        statistical_series.get(name),
                        expected_scope.get(name),
                    )
                ):
                    reasons.append(
                        f"SUPPORTING_STATISTICAL_REFERENCE_MISMATCH:{metric_id}:{name}"
                    )
            statistical_source_hashes = statistical_series.get(
                "source_economic_snapshot_hashes"
            )
            if not isinstance(statistical_source_hashes, list):
                statistical_source_hashes = []
                reasons.append(
                    f"SUPPORTING_STATISTICAL_SOURCE_LIST_INVALID:{metric_id}"
                )
            required_statistical_sources = {
                statistical_series.get("series_hash"),
                *statistical_source_hashes,
            }
            if (
                statistical_series.get("series_kind")
                == "PAIRED_AI_ECONOMIC_NET_LOG_GROWTH_DELTA"
            ):
                for name in (
                    "model_bundle_id",
                    "model_bundle_hash",
                    "ai_endpoint",
                ):
                    if (
                        name in expected_scope
                        and not _same_value(
                            statistical_series.get(name),
                            expected_scope.get(name),
                        )
                    ):
                        reasons.append(
                            f"SUPPORTING_PAIRED_REFERENCE_MISMATCH:{metric_id}:{name}"
                        )
                source_arms = statistical_series.get("source_arm_series")
                if not isinstance(source_arms, Mapping):
                    reasons.append(
                        f"SUPPORTING_PAIRED_SOURCE_ARMS_MISSING:{metric_id}"
                    )
                else:
                    for arm in ("baseline", "ai"):
                        arm_series = source_arms.get(arm)
                        if not isinstance(arm_series, Mapping):
                            reasons.append(
                                f"SUPPORTING_PAIRED_SOURCE_ARM_MISSING:{metric_id}:{arm}"
                            )
                        else:
                            required_statistical_sources.add(
                                arm_series.get("series_hash")
                            )
            if (
                not isinstance(source_hashes, list)
                or not required_statistical_sources.issubset(
                    set(source_hashes)
                )
            ):
                reasons.append(
                    f"SUPPORTING_STATISTICAL_SOURCE_INCOMPLETE:{metric_id}"
                )
        endpoint_reevaluation = (
            inputs.get("endpoint_reevaluation_snapshot")
            if isinstance(inputs, Mapping)
            else None
        )
        if isinstance(endpoint_reevaluation, Mapping):
            if (
                isinstance(statistical_series, Mapping)
                and endpoint_reevaluation.get("source_paired_series_hash")
                != statistical_series.get("series_hash")
            ):
                reasons.append(
                    f"SUPPORTING_ENDPOINT_SOURCE_MISMATCH:{metric_id}"
                )
            if endpoint_reevaluation.get("ai_endpoint") != (
                expected_scope.get("ai_endpoint")
            ):
                reasons.append(
                    f"SUPPORTING_ENDPOINT_SCOPE_MISMATCH:{metric_id}"
                )
            required_endpoint_sources = {
                endpoint_reevaluation.get("reevaluation_hash"),
                endpoint_reevaluation.get("source_paired_series_hash"),
                endpoint_reevaluation.get(
                    "reevaluated_paired_series_hash"
                ),
            }
            if (
                not isinstance(source_hashes, list)
                or not required_endpoint_sources.issubset(
                    set(source_hashes)
                )
            ):
                reasons.append(
                    f"SUPPORTING_ENDPOINT_SOURCE_INCOMPLETE:{metric_id}"
                )
        if execution.status == "COMPUTED":
            observations[metric_id] = execution.value
        elif execution.status == "INCONCLUSIVE":
            inconclusive.add(metric_id)
        else:
            reasons.extend(
                f"SUPPORTING_ESTIMATOR_EXECUTION:{metric_id}:{reason}"
                for reason in execution.reason_codes
            )

    reason_codes = tuple(sorted(set(reasons)))
    valid = not reason_codes
    accepted = observations if valid else {}
    accepted_inconclusive = tuple(sorted(inconclusive)) if valid else ()
    payload = {
        "bundle_id": bundle.get("bundle_id"),
        "valid": valid,
        "observations": accepted,
        "inconclusive_metrics": accepted_inconclusive,
        "execution_hashes": tuple(execution_hashes),
        "reason_codes": reason_codes,
    }
    return SupportingObservationValidation(
        valid=valid,
        observations=accepted,
        inconclusive_metrics=accepted_inconclusive,
        execution_hashes=tuple(execution_hashes),
        reason_codes=reason_codes,
        validation_hash=business_hash(payload),
    )
