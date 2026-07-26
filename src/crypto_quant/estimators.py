"""Versioned, fail-closed estimator function registry."""

import json
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_decimal
from .economics import (
    cash_flow_adjusted_daily_loss,
    cash_flow_adjusted_max_drawdown,
    fill_based_trading_net_pnl,
    period_economic_pnl,
    worst_case_gross_exposure_ratio,
)
from .errors import CanonicalizationError, PolicyError
from .evidence import artifact_self_hash
from .reevaluation import (
    leave_max_positive_delta_event_out_endpoint_reevaluation,
    leave_max_positive_delta_fold_out_endpoint_reevaluation,
)
from .statistics import (
    cash_flow_adjusted_economic_log_growth,
    complete_utc_calendar_month_count,
    geyer_initial_positive_sequence_ess,
    leave_max_positive_event_out_mbb_lcb95,
    leave_max_positive_fold_out_mbb_lcb95,
    leave_top_5_positive_events_out_mbb_lcb95,
    monthly_economic_pnl_mbb_lcb95,
    one_sided_95_moving_block_bootstrap,
    one_sided_95_paired_moving_block_bootstrap,
)


@dataclass(frozen=True)
class EstimatorExecution:
    estimator_id: str
    implementation_id: Optional[str]
    implementation_version: Optional[str]
    status: str
    value: Any
    reason_codes: Tuple[str, ...]
    execution_hash: str


@dataclass(frozen=True)
class GoldenVectorReport:
    passed: bool
    vector_count: int
    failed_vector_ids: Tuple[str, ...]
    report_hash: str


def _load_json_strict(path: Path) -> Dict[str, Any]:
    def reject_duplicates(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PolicyError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"cannot load {path}") from exc


def _nonnegative_decimal(value: Any, reason: str) -> Tuple[Optional[str], Tuple[str, ...]]:
    try:
        rendered = canonical_decimal(value)
        if Decimal(rendered) < 0:
            raise CanonicalizationError("negative capital")
        return rendered, ()
    except CanonicalizationError:
        return None, (reason,)


def _actual_deployable_capital(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    if inputs.get("snapshot_verified") is not True:
        return "FAIL", None, ("CAPITAL_SNAPSHOT_UNVERIFIED",)
    value, reasons = _nonnegative_decimal(
        inputs.get("actual_deployable_capital_usdt"),
        "ACTUAL_DEPLOYABLE_CAPITAL_INVALID",
    )
    return ("COMPUTED", value, ()) if not reasons else ("FAIL", None, reasons)


def _approved_production_capital(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    if inputs.get("scope_verified") is not True:
        return "FAIL", None, ("CAPITAL_SCOPE_UNVERIFIED",)
    value, reasons = _nonnegative_decimal(
        inputs.get("approved_production_capital_usdt"),
        "APPROVED_PRODUCTION_CAPITAL_INVALID",
    )
    return ("COMPUTED", value, ()) if not reasons else ("FAIL", None, reasons)


def _finite_break_even_root(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    if inputs.get("capital_grid_replay_verified") is not True:
        return "FAIL", None, ("CAPITAL_GRID_REPLAY_UNVERIFIED",)
    root = inputs.get("break_even_capital_lcb_root_usdt")
    if root is None:
        return "COMPUTED", False, ()
    value, reasons = _nonnegative_decimal(root, "BREAK_EVEN_ROOT_INVALID")
    if reasons:
        return "FAIL", None, reasons
    return "COMPUTED", Decimal(value) > 0, ()


def _decimal_capital_comparison(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    if inputs.get("scope_verified") is not True:
        return "FAIL", None, ("CAPITAL_SCOPE_UNVERIFIED",)
    actual, reasons = _nonnegative_decimal(
        inputs.get("actual_deployable_capital_usdt"),
        "ACTUAL_DEPLOYABLE_CAPITAL_INVALID",
    )
    if reasons:
        return "FAIL", None, reasons
    comparison = inputs.get("comparison")
    if comparison == "APPROVED":
        threshold, reasons = _nonnegative_decimal(
            inputs.get("approved_production_capital_usdt"),
            "APPROVED_PRODUCTION_CAPITAL_INVALID",
        )
        if reasons:
            return "FAIL", None, reasons
        return "COMPUTED", Decimal(actual) >= Decimal(threshold), ()
    if comparison == "BREAK_EVEN":
        root = inputs.get("break_even_capital_lcb_root_usdt")
        if root is None:
            return "COMPUTED", False, ()
        threshold, reasons = _nonnegative_decimal(
            root,
            "BREAK_EVEN_ROOT_INVALID",
        )
        if reasons:
            return "FAIL", None, reasons
        if Decimal(threshold) <= 0:
            return "COMPUTED", False, ()
        return "COMPUTED", Decimal(actual) >= Decimal(threshold), ()
    return "FAIL", None, ("CAPITAL_COMPARISON_UNKNOWN",)


_CALLABLES: Mapping[
    str,
    Callable[[Mapping[str, Any]], Tuple[str, Any, Tuple[str, ...]]],
] = {
    "actual_deployable_capital": _actual_deployable_capital,
    "approved_production_capital": _approved_production_capital,
    "finite_break_even_root": _finite_break_even_root,
    "decimal_capital_comparison": _decimal_capital_comparison,
    "fill_based_trading_net_pnl": fill_based_trading_net_pnl,
    "period_economic_pnl": period_economic_pnl,
    "cash_flow_adjusted_daily_loss": cash_flow_adjusted_daily_loss,
    "cash_flow_adjusted_max_drawdown": cash_flow_adjusted_max_drawdown,
    "worst_case_gross_exposure_ratio": worst_case_gross_exposure_ratio,
    "geyer_initial_positive_sequence_ess": (
        geyer_initial_positive_sequence_ess
    ),
    "one_sided_95_moving_block_bootstrap": (
        one_sided_95_moving_block_bootstrap
    ),
    "one_sided_95_paired_moving_block_bootstrap": (
        one_sided_95_paired_moving_block_bootstrap
    ),
    "leave_max_positive_fold_out_mbb_lcb95": (
        leave_max_positive_fold_out_mbb_lcb95
    ),
    "leave_top_5_positive_events_out_mbb_lcb95": (
        leave_top_5_positive_events_out_mbb_lcb95
    ),
    "leave_max_positive_event_out_mbb_lcb95": (
        leave_max_positive_event_out_mbb_lcb95
    ),
    "monthly_economic_pnl_mbb_lcb95": (
        monthly_economic_pnl_mbb_lcb95
    ),
    "complete_utc_calendar_month_count": (
        complete_utc_calendar_month_count
    ),
    "cash_flow_adjusted_economic_log_growth": (
        cash_flow_adjusted_economic_log_growth
    ),
    "leave_max_positive_delta_fold_out_endpoint_reevaluation": (
        leave_max_positive_delta_fold_out_endpoint_reevaluation
    ),
    "leave_max_positive_delta_event_out_endpoint_reevaluation": (
        leave_max_positive_delta_event_out_endpoint_reevaluation
    ),
}


class EstimatorRegistry:
    """Resolve every Catalog algorithm to executable or explicit unavailable."""

    def __init__(
        self,
        *,
        registry: Mapping[str, Any],
        golden_vectors: Mapping[str, Any],
        catalog: Mapping[str, Any],
        economic_snapshot_schema: Mapping[str, Any],
        statistical_series_schema: Mapping[str, Any],
        endpoint_reevaluation_schema: Mapping[str, Any],
    ) -> None:
        self.registry = registry
        self.golden_vectors = golden_vectors
        self.catalog = catalog
        self.economic_snapshot_schema = economic_snapshot_schema
        self.statistical_series_schema = statistical_series_schema
        self.endpoint_reevaluation_schema = endpoint_reevaluation_schema
        self.registry_hash = registry["registry_hash"]
        self.golden_bundle_hash = golden_vectors["bundle_hash"]
        self._implementations = {
            entry["estimator_id"]: entry
            for entry in registry["implementations"]
        }
        self._catalog_algorithms = set(catalog["algorithms"])

    @classmethod
    def load(
        cls,
        config_dir: Path,
        catalog: Mapping[str, Any],
    ) -> "EstimatorRegistry":
        config_dir = Path(config_dir)
        registry_schema = _load_json_strict(
            config_dir / "estimator-registry-v1.schema.json"
        )
        golden_schema = _load_json_strict(
            config_dir / "estimator-golden-vectors-v1.schema.json"
        )
        economic_snapshot_schema = _load_json_strict(
            config_dir / "economic-ledger-snapshot-v1.schema.json"
        )
        statistical_series_schema = _load_json_strict(
            config_dir / "statistical-series-snapshot-v1.schema.json"
        )
        endpoint_reevaluation_schema = _load_json_strict(
            config_dir / "endpoint-reevaluation-snapshot-v1.schema.json"
        )
        Draft202012Validator.check_schema(registry_schema)
        Draft202012Validator.check_schema(golden_schema)
        Draft202012Validator.check_schema(economic_snapshot_schema)
        Draft202012Validator.check_schema(statistical_series_schema)
        Draft202012Validator.check_schema(endpoint_reevaluation_schema)
        registry = _load_json_strict(config_dir / "estimator-registry-v1.json")
        golden = _load_json_strict(
            config_dir / "estimator-golden-vectors-v1.json"
        )
        for label, schema, artifact in (
            ("EstimatorRegistry", registry_schema, registry),
            ("EstimatorGoldenVectors", golden_schema, golden),
        ):
            errors = list(Draft202012Validator(schema).iter_errors(artifact))
            if errors:
                first = min(
                    errors,
                    key=lambda error: "/".join(map(str, error.absolute_path)),
                )
                location = "/".join(map(str, first.absolute_path))
                raise PolicyError(
                    f"{label} schema failure at {location}: {first.message}"
                )
        if artifact_self_hash(registry, "registry_hash") != registry["registry_hash"]:
            raise PolicyError("EstimatorRegistry self hash mismatch")
        if artifact_self_hash(golden, "bundle_hash") != golden["bundle_hash"]:
            raise PolicyError("Estimator golden bundle self hash mismatch")
        if registry["metric_catalog_id"] != catalog["catalog_id"]:
            raise PolicyError("EstimatorRegistry catalog ID mismatch")
        if registry["metric_catalog_version"] != catalog["catalog_version"]:
            raise PolicyError("EstimatorRegistry catalog version mismatch")
        if golden["estimator_registry_id"] != registry["registry_id"]:
            raise PolicyError("Golden bundle registry ID mismatch")
        if golden["estimator_registry_hash"] != registry["registry_hash"]:
            raise PolicyError("Golden bundle registry hash mismatch")

        estimator_ids = [item["estimator_id"] for item in registry["implementations"]]
        if len(estimator_ids) != len(set(estimator_ids)):
            raise PolicyError("duplicate executable estimator ID")
        unknown = sorted(set(estimator_ids) - set(catalog["algorithms"]))
        if unknown:
            raise PolicyError(f"registry has unknown estimator IDs: {unknown}")
        callable_ids = [item["callable_id"] for item in registry["implementations"]]
        unknown_callables = sorted(set(callable_ids) - set(_CALLABLES))
        if unknown_callables:
            raise PolicyError(f"registry has unknown callables: {unknown_callables}")

        vector_ids = [item["vector_id"] for item in golden["vectors"]]
        if len(vector_ids) != len(set(vector_ids)):
            raise PolicyError("duplicate estimator golden vector ID")
        fixture_ids = set(golden["fixtures"])
        for vector in golden["vectors"]:
            unknown_fixtures = sorted(
                set(vector["fixture_bindings"].values()) - fixture_ids
            )
            if unknown_fixtures:
                raise PolicyError(
                    "golden vector references unknown fixtures: "
                    + vector["vector_id"]
                )
            overlap = set(vector["inputs"]) & set(vector["fixture_bindings"])
            if overlap:
                raise PolicyError(
                    "golden vector input and fixture binding overlap: "
                    + vector["vector_id"]
                )
        vectors_by_estimator: Dict[str, set] = {}
        for vector in golden["vectors"]:
            vectors_by_estimator.setdefault(vector["estimator_id"], set()).add(
                vector["vector_id"]
            )
        for implementation in registry["implementations"]:
            expected = set(implementation["golden_vector_ids"])
            actual = vectors_by_estimator.get(implementation["estimator_id"], set())
            if expected != actual:
                raise PolicyError(
                    "golden vector coverage mismatch: "
                    + implementation["estimator_id"]
                )
        instance = cls(
            registry=registry,
            golden_vectors=golden,
            catalog=catalog,
            economic_snapshot_schema=economic_snapshot_schema,
            statistical_series_schema=statistical_series_schema,
            endpoint_reevaluation_schema=endpoint_reevaluation_schema,
        )
        report = instance.run_golden_vectors()
        if not report.passed:
            raise PolicyError(
                f"estimator golden vectors failed: {report.failed_vector_ids}"
            )
        return instance

    @property
    def executable_estimator_ids(self) -> Tuple[str, ...]:
        return tuple(sorted(self._implementations))

    @property
    def unavailable_estimator_ids(self) -> Tuple[str, ...]:
        return tuple(sorted(self._catalog_algorithms - set(self._implementations)))

    def is_executable(self, estimator_id: str) -> bool:
        return estimator_id in self._implementations

    def execute(
        self,
        estimator_id: str,
        inputs: Mapping[str, Any],
    ) -> EstimatorExecution:
        implementation = self._implementations.get(estimator_id)
        if implementation is None:
            reason = (
                "ESTIMATOR_NOT_EXECUTABLE"
                if estimator_id in self._catalog_algorithms
                else "UNKNOWN_ESTIMATOR"
            )
            return self._execution(
                estimator_id,
                None,
                "FAIL",
                None,
                (reason,),
            )
        required_fields = set(implementation["input_fields"])
        actual_fields = set(inputs)
        if required_fields != actual_fields:
            reasons = []
            for name in sorted(required_fields - actual_fields):
                reasons.append(f"ESTIMATOR_INPUT_MISSING:{name}")
            for name in sorted(actual_fields - required_fields):
                reasons.append(f"ESTIMATOR_INPUT_UNEXPECTED:{name}")
            return self._execution(
                estimator_id,
                implementation,
                "FAIL",
                None,
                tuple(reasons),
            )
        if "economic_ledger_snapshot" in required_fields:
            errors = list(
                Draft202012Validator(
                    self.economic_snapshot_schema
                ).iter_errors(inputs["economic_ledger_snapshot"])
            )
            if errors:
                return self._execution(
                    estimator_id,
                    implementation,
                    "FAIL",
                    None,
                    ("ECONOMIC_SNAPSHOT_SCHEMA_INVALID",),
                )
        if "statistical_series_snapshot" in required_fields:
            statistical_series = inputs["statistical_series_snapshot"]
            errors = list(
                Draft202012Validator(
                    self.statistical_series_schema
                ).iter_errors(statistical_series)
            )
            if errors:
                return self._execution(
                    estimator_id,
                    implementation,
                    "FAIL",
                    None,
                    ("STATISTICAL_SERIES_SCHEMA_INVALID",),
                )
            if (
                statistical_series.get("series_kind")
                == "PAIRED_AI_ECONOMIC_NET_LOG_GROWTH_DELTA"
            ):
                source_arms = statistical_series.get("source_arm_series")
                if not isinstance(source_arms, Mapping) or any(
                    list(
                        Draft202012Validator(
                            self.statistical_series_schema
                        ).iter_errors(source_arms.get(arm))
                    )
                    for arm in ("baseline", "ai")
                ):
                    return self._execution(
                        estimator_id,
                        implementation,
                        "FAIL",
                        None,
                        ("PAIRED_SOURCE_SERIES_SCHEMA_INVALID",),
                    )
        if "endpoint_reevaluation_snapshot" in required_fields:
            reevaluation = inputs["endpoint_reevaluation_snapshot"]
            errors = list(
                Draft202012Validator(
                    self.endpoint_reevaluation_schema
                ).iter_errors(reevaluation)
            )
            if errors:
                return self._execution(
                    estimator_id,
                    implementation,
                    "FAIL",
                    None,
                    ("ENDPOINT_REEVALUATION_SCHEMA_INVALID",),
                )
        status, value, reasons = _CALLABLES[implementation["callable_id"]](inputs)
        return self._execution(
            estimator_id,
            implementation,
            status,
            value,
            reasons,
        )

    @staticmethod
    def _execution(
        estimator_id: str,
        implementation: Optional[Mapping[str, Any]],
        status: str,
        value: Any,
        reasons: Tuple[str, ...],
    ) -> EstimatorExecution:
        reason_codes = tuple(sorted(set(reasons)))
        payload = {
            "estimator_id": estimator_id,
            "implementation_id": (
                implementation["implementation_id"]
                if implementation is not None
                else None
            ),
            "implementation_version": (
                implementation["implementation_version"]
                if implementation is not None
                else None
            ),
            "status": status,
            "value": value,
            "reason_codes": reason_codes,
        }
        return EstimatorExecution(
            estimator_id=estimator_id,
            implementation_id=payload["implementation_id"],
            implementation_version=payload["implementation_version"],
            status=status,
            value=value,
            reason_codes=reason_codes,
            execution_hash=business_hash(payload),
        )

    def run_golden_vectors(self) -> GoldenVectorReport:
        failed = []
        for vector in self.golden_vectors["vectors"]:
            inputs = deepcopy(vector["inputs"])
            for field, fixture_id in vector["fixture_bindings"].items():
                inputs[field] = deepcopy(
                    self.golden_vectors["fixtures"][fixture_id]
                )
            execution = self.execute(vector["estimator_id"], inputs)
            actual = {
                "status": execution.status,
                "value": execution.value,
                "reason_codes": list(execution.reason_codes),
            }
            expected = {
                "status": vector["expected_status"],
                "value": vector["expected_value"],
                "reason_codes": sorted(vector["expected_reason_codes"]),
            }
            if actual != expected:
                failed.append(vector["vector_id"])
        failed_ids = tuple(sorted(failed))
        payload = {
            "registry_hash": self.registry_hash,
            "golden_bundle_hash": self.golden_bundle_hash,
            "vector_count": len(self.golden_vectors["vectors"]),
            "failed_vector_ids": failed_ids,
        }
        return GoldenVectorReport(
            passed=not failed_ids,
            vector_count=len(self.golden_vectors["vectors"]),
            failed_vector_ids=failed_ids,
            report_hash=business_hash(payload),
        )
