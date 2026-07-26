"""Deterministic ReleasePolicy loader and fail-closed release evaluator."""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from jsonschema import Draft202012Validator, FormatChecker

from .canonical import business_hash, canonical_decimal
from .errors import CanonicalizationError, PolicyError


def strict_format_checker() -> FormatChecker:
    checker = FormatChecker()

    @checker.checks("date")
    def is_date(value: object) -> bool:
        if not isinstance(value, str):
            return True
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return False
        try:
            date.fromisoformat(value)
            return True
        except ValueError:
            return False

    @checker.checks("date-time")
    def is_date_time(value: object) -> bool:
        if not isinstance(value, str):
            return True
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.tzinfo is not None and parsed.utcoffset() is not None
        except ValueError:
            return False

    return checker


# Kept as a compatibility alias for the v0.1 public test surface.
_format_checker = strict_format_checker


def load_json_strict(path: Path) -> Dict[str, Any]:
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


def _walk_key(value: Any, key: str) -> Iterable[Any]:
    if isinstance(value, dict):
        for current_key, current_value in value.items():
            if current_key == key:
                yield current_value
            yield from _walk_key(current_value, key)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_key(item, key)


@dataclass(frozen=True)
class EvaluationResult:
    result: str
    reason_codes: Tuple[str, ...]
    policy_id: str
    policy_version: str
    result_hash: str


@dataclass(frozen=True)
class ExpressionResolution:
    """A Decimal expression result with explicit fail-closed status."""

    status: str
    value: Optional[str]
    reason_codes: Tuple[str, ...]


@dataclass(frozen=True)
class GateEvaluation:
    """Computed result for one policy gate, independent of claimed evidence."""

    gate_group_id: str
    gate_id: str
    metric_id: str
    result: str
    observed_value: Any
    threshold_value: Any
    comparator: str
    reason_codes: Tuple[str, ...]
    result_hash: str


@dataclass(frozen=True)
class GroupEvaluation:
    """A gate group result that retains every child result."""

    gate_group_id: str
    result: str
    gate_results: Tuple[GateEvaluation, ...]
    reason_codes: Tuple[str, ...]
    result_hash: str


@dataclass(frozen=True)
class AuditPlanItem:
    gate_group_id: str
    evaluation_ledger: str


@dataclass(frozen=True)
class _Resolution:
    status: str
    value: Any = None
    reason_codes: Tuple[str, ...] = ()


class MetricResolver:
    def __init__(self, catalog: Mapping[str, Any]) -> None:
        self.catalog = catalog
        self.algorithms = set(catalog["algorithms"])

    def resolve(self, metric_id: str) -> Mapping[str, Any]:
        exact = self.catalog["exact_overrides"]
        if metric_id in exact:
            definition = exact[metric_id]
        else:
            definition = next(
                (
                    family
                    for family in self.catalog["metric_families"]
                    if re.fullmatch(family["pattern"], metric_id)
                ),
                None,
            )
        if definition is None:
            raise PolicyError(f"unknown metric: {metric_id}")
        if definition["estimator_id"] not in self.algorithms:
            raise PolicyError(f"unknown estimator: {definition['estimator_id']}")
        return definition


class PolicyBundle:
    """Load and verify the frozen release policy artifacts."""

    _EXPRESSION_OPERATORS = {
        "ADD",
        "SUBTRACT",
        "MULTIPLY",
        "DIVIDE",
        "ABS",
        "MIN",
        "MAX",
        "FLOOR",
    }
    _MAX_EXPRESSION_DEPTH = 32
    _MAX_EXPRESSION_NODES = 256
    _SCHEMAS = (
        "release-gates-v1.1.schema.json",
        "release-metrics-v1.1.schema.json",
        "release-evidence-v1.1.schema.json",
        "recipe-release-v1.1.schema.json",
        "model-bundle-v1.1.schema.json",
        "approved-fallback-registry-v1.1.schema.json",
    )

    def __init__(
        self,
        *,
        root: Path,
        policy: Dict[str, Any],
        catalog: Dict[str, Any],
        evidence_schema: Dict[str, Any],
    ) -> None:
        self.root = root
        self.policy = policy
        self.catalog = catalog
        self.evidence_schema = evidence_schema
        self.metrics = MetricResolver(catalog)

    @classmethod
    def load(cls, config_dir: Path) -> "PolicyBundle":
        config_dir = Path(config_dir)
        policy = load_json_strict(config_dir / "release-gates-v1.1.json")
        catalog = load_json_strict(config_dir / "release-metrics-v1.1.json")
        evidence_schema = load_json_strict(
            config_dir / "release-evidence-v1.1.schema.json"
        )

        for schema_name in cls._SCHEMAS:
            Draft202012Validator.check_schema(
                load_json_strict(config_dir / schema_name)
            )
        cls._validate_instance(
            config_dir / "release-gates-v1.1.schema.json",
            policy,
            "ReleaseGatePolicy",
        )
        cls._validate_instance(
            config_dir / "release-metrics-v1.1.schema.json",
            catalog,
            "MetricCatalog",
        )
        bundle = cls(
            root=config_dir,
            policy=policy,
            catalog=catalog,
            evidence_schema=evidence_schema,
        )
        bundle.validate_cross_references()
        return bundle

    @staticmethod
    def _validate_instance(schema_path: Path, instance: Any, label: str) -> None:
        schema = load_json_strict(schema_path)
        validator = Draft202012Validator(
            schema,
            format_checker=strict_format_checker(),
        )
        errors = list(validator.iter_errors(instance))
        if errors:
            first = min(errors, key=lambda error: "/".join(map(str, error.path)))
            location = "/".join(str(part) for part in first.path)
            raise PolicyError(f"{label} schema failure at {location}: {first.message}")

    def flat_gate_groups(self) -> Dict[str, List[Dict[str, Any]]]:
        flat: Dict[str, List[Dict[str, Any]]] = {}
        for group, value in self.policy["gates"].items():
            if isinstance(value, list):
                flat[group] = value
            elif isinstance(value, dict):
                for endpoint, gates in value.items():
                    flat[f"{group}.{endpoint}"] = gates
            else:
                raise PolicyError(f"invalid gate group: {group}")
        return flat

    def _group_exists(self, group: str, available: Set[str]) -> bool:
        if group in available:
            return True
        if group in ("AI_ENDPOINT.{ai_endpoint}", "AUDIT_AI_ENDPOINT.{ai_endpoint}"):
            prefix = group.split(".", 1)[0]
            return all(
                f"{prefix}.{endpoint}" in available
                for endpoint in ("GROWTH", "RISK_EFFICIENCY")
            )
        return False

    def validate_cross_references(self) -> None:
        if self.policy["metric_catalog_id"] != self.catalog["catalog_id"]:
            raise PolicyError("policy metric_catalog_id does not match the catalog")
        if self.policy["evidence_schema_id"] != self.evidence_schema["$id"]:
            raise PolicyError("policy evidence_schema_id does not match the schema")

        groups = self.flat_gate_groups()
        gate_ids: Set[str] = set()
        for group, gates in groups.items():
            for gate in gates:
                if gate["gate_id"] in gate_ids:
                    raise PolicyError(f"duplicate gate_id: {gate['gate_id']}")
                gate_ids.add(gate["gate_id"])
                self.metrics.resolve(gate["metric_id"])
                applies = gate.get("applies_when")
                if applies is not None and (
                    not isinstance(applies, dict)
                    or not isinstance(applies.get("all"), list)
                    or not applies["all"]
                ):
                    raise PolicyError(f"{group}.{gate['gate_id']}: invalid applies_when")

        for metric_ref in _walk_key(self.policy, "metric_ref"):
            self.metrics.resolve(metric_ref)
        known_bindings = {
            binding["binding"] for binding in self.policy["required_policy_bindings"]
        }
        for reference in _walk_key(self.policy["gates"], "threshold_reference"):
            if reference["binding"] not in known_bindings:
                raise PolicyError(
                    f"unknown threshold binding: {reference['binding']}"
                )
        for reference in _walk_key(self.policy["gates"], "boundary_reference"):
            if reference["binding"] not in known_bindings:
                raise PolicyError(
                    f"unknown boundary binding: {reference['binding']}"
                )
        for path in _walk_key(self.policy["gates"], "threshold_ast_ref"):
            expression = self._policy_path(self.policy, path)
            if not isinstance(expression, Mapping):
                raise PolicyError(f"threshold_ast_ref is not an expression: {path}")
        for path in _walk_key(self.policy, "expression_ref"):
            expression = self._policy_path(self.policy, path)
            if not isinstance(expression, Mapping):
                raise PolicyError(f"expression_ref is not an expression: {path}")
        required_estimator = self.policy["sample_policy"]["effective_sample_estimator_id"]
        if required_estimator not in self.metrics.algorithms:
            raise PolicyError(f"unknown estimator: {required_estimator}")

        available = set(groups)
        references: List[str] = list(_walk_key(self.policy["release_audit_matrix"], "gate_group"))
        for stages in self.policy["forward_gate_matrix"].values():
            for stage_groups in stages.values():
                references.extend(stage_groups)
        for transition in self.policy["deployment_state_machine"][
            "allowed_forward_transitions"
        ]:
            references.extend(transition["required_gate_groups"])
        minor = self.policy["minor_bundle_refresh_workflow"]
        references.extend(minor["required_gate_groups"])
        references.append(minor["required_endpoint_gate_group_template"])
        missing = sorted(
            {reference for reference in references if not self._group_exists(reference, available)}
        )
        if missing:
            raise PolicyError(f"unknown gate groups: {missing}")

        stage_for_transition = {
            ("SHADOW", "PAPER"): "SHADOW",
            ("PAPER", "CANARY_25"): "PAPER",
            ("CANARY_25", "CANARY_50"): "CANARY_25",
            ("CANARY_50", "CANARY_75"): "CANARY_50",
            ("CANARY_75", "CHAMPION"): "CANARY_75",
        }
        for transition in self.policy["deployment_state_machine"][
            "allowed_forward_transitions"
        ]:
            key = (transition["from"], transition["to"])
            if key not in stage_for_transition:
                continue
            stage = stage_for_transition[key]
            expected = self.policy["forward_gate_matrix"][transition["release_route"]][stage]
            if transition["required_gate_groups"] != expected:
                raise PolicyError(f"forward matrix mismatch: {transition['release_route']} {key}")
            if "RUNTIME" not in expected:
                raise PolicyError(f"RUNTIME missing: {transition['release_route']} {stage}")
        for route, stages in self.policy["forward_gate_matrix"].items():
            for stage, stage_groups in stages.items():
                if "RUNTIME" not in stage_groups:
                    raise PolicyError(f"RUNTIME missing: {route} {stage}")
                if stage in (
                    "PAPER",
                    "CANARY_25",
                    "CANARY_50",
                    "CANARY_75",
                    "CHAMPION",
                ) and "CAPITAL_READINESS" not in stage_groups:
                    raise PolicyError(f"CAPITAL_READINESS missing: {route} {stage}")

        for release_kind in ("INITIAL", "MAJOR"):
            matrix = self.policy["release_audit_matrix"][release_kind]
            baseline = {
                (entry["gate_group"], entry["evaluation_ledger"])
                for entry in matrix["BASELINE_ONLY"]
            }
            if ("AUDIT_BASE_ARM", "BASELINE_LEDGER") not in baseline:
                raise PolicyError(f"{release_kind} baseline audit ledger missing")
            for endpoint in ("GROWTH", "RISK_EFFICIENCY"):
                ai = {
                    (entry["gate_group"], entry["evaluation_ledger"])
                    for entry in matrix["AI_ENHANCED"][endpoint]
                }
                required = {
                    ("AUDIT_BASE_ARM", "BASELINE_LEDGER"),
                    ("AUDIT_AI_ARM", "AI_LEDGER"),
                    ("AUDIT_AI_PAIRED_COMMON", "PAIRED_COMPARISON"),
                    (f"AUDIT_AI_ENDPOINT.{endpoint}", "PAIRED_COMPARISON"),
                }
                if not required.issubset(ai):
                    raise PolicyError(f"{release_kind}.{endpoint} audit ledgers incomplete")

    def audit_plan(
        self,
        release_kind: str,
        release_route: str,
        ai_endpoint: Optional[str] = None,
    ) -> Tuple[AuditPlanItem, ...]:
        """Select the one authoritative Release Audit plan."""

        try:
            matrix = self.policy["release_audit_matrix"][release_kind]
            if release_route == "BASELINE_ONLY":
                if ai_endpoint is not None:
                    raise PolicyError("BASELINE_ONLY audit cannot select an AI endpoint")
                entries = matrix[release_route]
            elif release_route == "AI_ENHANCED":
                if ai_endpoint not in ("GROWTH", "RISK_EFFICIENCY"):
                    raise PolicyError("AI_ENHANCED audit requires a valid endpoint")
                entries = matrix[release_route][ai_endpoint]
            else:
                raise PolicyError(f"unknown release route: {release_route}")
        except KeyError as exc:
            raise PolicyError(
                f"unknown Release Audit selection: {release_kind}/{release_route}"
            ) from exc
        return tuple(
            AuditPlanItem(
                gate_group_id=entry["gate_group"],
                evaluation_ledger=entry["evaluation_ledger"],
            )
            for entry in entries
        )

    def forward_gate_groups(
        self,
        release_route: str,
        stage: str,
    ) -> Tuple[str, ...]:
        """Select the exact gate groups required at a forward stage."""

        try:
            return tuple(self.policy["forward_gate_matrix"][release_route][stage])
        except KeyError as exc:
            raise PolicyError(
                f"unknown forward gate selection: {release_route}/{stage}"
            ) from exc

    def evidence_schema_errors(self, evidence: Mapping[str, Any]) -> Tuple[str, ...]:
        """Return stable schema error strings for one GateEvidence envelope."""

        validator = Draft202012Validator(
            self.evidence_schema,
            format_checker=strict_format_checker(),
        )
        errors = sorted(
            validator.iter_errors(evidence),
            key=lambda error: (
                "/".join(map(str, error.absolute_path)),
                error.message,
            ),
        )
        return tuple(
            "EVIDENCE_SCHEMA:"
            + ("/".join(map(str, error.absolute_path)) or "$")
            + ":"
            + error.message
            for error in errors
        )

    def evidence_scope_snapshot(
        self,
        evidence: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Extract every dimension that controls GateEvidence reuse."""

        dimensions = list(self.policy["evidence_scope"]["required_dimensions"])
        dimensions.extend(
            (
                "metric_catalog_id",
                "release_gate_policy_id",
                "release_gate_policy_version",
                "recipe_release_schema_id",
                "actual_deployable_capital_usdt",
                "break_even_capital_lcb_root_usdt",
                "policy_binding_hashes",
            )
        )
        if evidence.get("release_route") == "AI_ENHANCED":
            dimensions.extend(self.policy["evidence_scope"]["ai_dimensions"])
            dimensions.extend(("model_bundle_schema_id", "model_bundle_hash"))
        stage = evidence.get("stage")
        if stage in ("CANARY_25", "CANARY_50", "CANARY_75"):
            dimensions.extend(self.policy["evidence_scope"]["canary_dimensions"])
        if evidence.get("fallback_activation_requested") is True:
            dimensions.extend(
                (
                    "approved_fallback_registry_record_id",
                    "approved_fallback_registry_schema_id",
                    "approved_fallback_registry_record_hash",
                    "approved_fallback_registry_evidence_hash",
                    "approved_fallback_registry_status",
                    "approved_fallback_registry_expires_at",
                    "approved_fallback_registry_signer_id",
                    "approved_fallback_registry_signature_hash",
                )
            )

        missing = sorted({name for name in dimensions if name not in evidence})
        if missing:
            raise PolicyError(f"GateEvidence scope dimensions missing: {missing}")
        frozen_inputs = evidence.get("frozen_release_inputs")
        if not isinstance(frozen_inputs, Mapping):
            raise PolicyError("GateEvidence frozen_release_inputs missing")
        capital_plan = frozen_inputs.get("approved_capital_and_break_even_plan")
        if (
            not isinstance(capital_plan, Mapping)
            or "artifact_hash" not in capital_plan
        ):
            raise PolicyError(
                "GateEvidence capital and break-even plan artifact hash missing"
            )
        snapshot = {name: evidence[name] for name in dict.fromkeys(dimensions)}
        snapshot["approved_capital_and_break_even_plan_hash"] = capital_plan[
            "artifact_hash"
        ]
        return snapshot

    @staticmethod
    def _policy_path(root: Mapping[str, Any], path: str) -> Any:
        if not path or any(
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part)
            for part in path.split(".")
        ):
            raise PolicyError(f"invalid expression reference: {path!r}")
        current: Any = root
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                raise PolicyError(f"unknown expression reference: {path}")
            current = current[part]
        return current

    @staticmethod
    def _json_pointer(root: Any, pointer: str) -> Any:
        if pointer == "":
            return root
        if not pointer.startswith("/"):
            raise PolicyError(f"invalid JSON Pointer: {pointer!r}")
        current = root
        for raw_part in pointer[1:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if isinstance(current, Mapping):
                if part not in current:
                    raise PolicyError(f"JSON Pointer does not resolve: {pointer}")
                current = current[part]
            elif isinstance(current, Sequence) and not isinstance(
                current, (str, bytes, bytearray)
            ):
                if not part.isdigit() or int(part) >= len(current):
                    raise PolicyError(f"JSON Pointer does not resolve: {pointer}")
                current = current[int(part)]
            else:
                raise PolicyError(f"JSON Pointer does not resolve: {pointer}")
        return current

    @staticmethod
    def _decimal_value(value: Any) -> Fraction:
        if isinstance(value, bool) or isinstance(value, float):
            raise PolicyError("expression operands must be exact numeric values")
        try:
            return Fraction(Decimal(canonical_decimal(value)))
        except CanonicalizationError as exc:
            raise PolicyError("expression operand is not a canonical Decimal") from exc

    @staticmethod
    def _fraction_decimal(value: Fraction) -> str:
        """Render a finite base-10 Fraction without Decimal context rounding."""

        denominator = value.denominator
        powers_of_two = 0
        powers_of_five = 0
        while denominator % 2 == 0:
            denominator //= 2
            powers_of_two += 1
        while denominator % 5 == 0:
            denominator //= 5
            powers_of_five += 1
        if denominator != 1:
            raise PolicyError("expression result is not a finite canonical Decimal")
        scale = max(powers_of_two, powers_of_five)
        numerator = value.numerator
        numerator *= 2 ** (scale - powers_of_two)
        numerator *= 5 ** (scale - powers_of_five)
        negative = numerator < 0
        digits = str(abs(numerator))
        if scale:
            digits = digits.zfill(scale + 1)
            rendered = f"{digits[:-scale]}.{digits[-scale:]}"
        else:
            rendered = digits
        if negative:
            rendered = "-" + rendered
        return canonical_decimal(rendered)

    def _resolve_expression(
        self,
        expression: Any,
        observations: Mapping[str, Any],
        context: Mapping[str, Any],
        inconclusive_metrics: Set[str],
        *,
        depth: int,
        budget: List[int],
        reference_stack: Tuple[str, ...],
    ) -> _Resolution:
        if depth > self._MAX_EXPRESSION_DEPTH:
            return _Resolution("FAIL", reason_codes=("EXPRESSION_DEPTH_EXCEEDED",))
        budget[0] -= 1
        if budget[0] < 0:
            return _Resolution("FAIL", reason_codes=("EXPRESSION_NODE_LIMIT_EXCEEDED",))
        if not isinstance(expression, Mapping):
            return _Resolution("FAIL", reason_codes=("INVALID_EXPRESSION_NODE",))

        if set(expression) == {"literal"}:
            try:
                return _Resolution(
                    "RESOLVED",
                    self._decimal_value(expression["literal"]),
                )
            except PolicyError:
                return _Resolution("FAIL", reason_codes=("INVALID_EXPRESSION_LITERAL",))

        if set(expression) == {"metric_ref"}:
            metric_id = expression["metric_ref"]
            if not isinstance(metric_id, str):
                return _Resolution(
                    "FAIL",
                    reason_codes=("INVALID_METRIC_REFERENCE",),
                )
            try:
                definition = self.metrics.resolve(metric_id)
            except (PolicyError, TypeError):
                return _Resolution(
                    "FAIL",
                    reason_codes=(f"UNKNOWN_METRIC_REFERENCE:{metric_id}",),
                )
            if definition["value_type"] not in ("decimal", "integer"):
                return _Resolution(
                    "FAIL",
                    reason_codes=(f"NON_NUMERIC_METRIC_REFERENCE:{metric_id}",),
                )
            if metric_id in inconclusive_metrics:
                return _Resolution(
                    "INCONCLUSIVE",
                    reason_codes=(f"INSUFFICIENT_SAMPLE:{metric_id}",),
                )
            if metric_id not in observations:
                return _Resolution(
                    "FAIL",
                    reason_codes=(f"MISSING_METRIC_REFERENCE:{metric_id}",),
                )
            if definition["value_type"] == "integer" and (
                isinstance(observations[metric_id], bool)
                or not isinstance(observations[metric_id], int)
            ):
                return _Resolution(
                    "FAIL",
                    reason_codes=(f"INVALID_METRIC_REFERENCE:{metric_id}",),
                )
            try:
                return _Resolution(
                    "RESOLVED",
                    self._decimal_value(observations[metric_id]),
                )
            except PolicyError:
                return _Resolution(
                    "FAIL",
                    reason_codes=(f"INVALID_METRIC_REFERENCE:{metric_id}",),
                )

        if set(expression) == {"attribute_ref"}:
            attribute = expression["attribute_ref"]
            if not isinstance(attribute, str):
                return _Resolution(
                    "FAIL",
                    reason_codes=("INVALID_ATTRIBUTE_REFERENCE",),
                )
            if attribute not in context:
                return _Resolution(
                    "FAIL",
                    reason_codes=(f"MISSING_ATTRIBUTE_REFERENCE:{attribute}",),
                )
            try:
                return _Resolution(
                    "RESOLVED",
                    self._decimal_value(context[attribute]),
                )
            except PolicyError:
                return _Resolution(
                    "FAIL",
                    reason_codes=(f"INVALID_ATTRIBUTE_REFERENCE:{attribute}",),
                )

        if set(expression) == {"expression_ref"}:
            path = expression["expression_ref"]
            if not isinstance(path, str):
                return _Resolution(
                    "FAIL",
                    reason_codes=("INVALID_EXPRESSION_REFERENCE",),
                )
            if path in reference_stack:
                return _Resolution(
                    "FAIL",
                    reason_codes=(f"EXPRESSION_REFERENCE_CYCLE:{path}",),
                )
            try:
                referenced = self._policy_path(self.policy, path)
            except PolicyError:
                return _Resolution(
                    "FAIL",
                    reason_codes=(f"UNKNOWN_EXPRESSION_REFERENCE:{path}",),
                )
            return self._resolve_expression(
                referenced,
                observations,
                context,
                inconclusive_metrics,
                depth=depth + 1,
                budget=budget,
                reference_stack=reference_stack + (path,),
            )

        if set(expression) != {"op", "args"}:
            return _Resolution("FAIL", reason_codes=("INVALID_EXPRESSION_NODE",))
        operator = expression["op"]
        arguments = expression["args"]
        if not isinstance(operator, str) or operator not in self._EXPRESSION_OPERATORS:
            return _Resolution(
                "FAIL",
                reason_codes=(f"UNSUPPORTED_EXPRESSION_OPERATOR:{operator}",),
            )
        if not isinstance(arguments, list):
            return _Resolution("FAIL", reason_codes=("INVALID_EXPRESSION_ARGUMENTS",))
        if operator in ("ABS", "FLOOR") and len(arguments) != 1:
            return _Resolution(
                "FAIL",
                reason_codes=(f"INVALID_EXPRESSION_ARITY:{operator}",),
            )
        if operator in ("SUBTRACT", "DIVIDE") and len(arguments) != 2:
            return _Resolution(
                "FAIL",
                reason_codes=(f"INVALID_EXPRESSION_ARITY:{operator}",),
            )
        if operator in ("ADD", "MULTIPLY", "MIN", "MAX") and not arguments:
            return _Resolution(
                "FAIL",
                reason_codes=(f"INVALID_EXPRESSION_ARITY:{operator}",),
            )

        resolved = [
            self._resolve_expression(
                argument,
                observations,
                context,
                inconclusive_metrics,
                depth=depth + 1,
                budget=budget,
                reference_stack=reference_stack,
            )
            for argument in arguments
        ]
        failed = next((item for item in resolved if item.status == "FAIL"), None)
        if failed is not None:
            return failed
        inconclusive = next(
            (item for item in resolved if item.status == "INCONCLUSIVE"),
            None,
        )
        if inconclusive is not None:
            return inconclusive
        values = [item.value for item in resolved]
        if operator == "ADD":
            value = sum(values, Fraction(0))
        elif operator == "SUBTRACT":
            value = values[0] - values[1]
        elif operator == "MULTIPLY":
            value = Fraction(1)
            for item in values:
                value *= item
        elif operator == "DIVIDE":
            if values[1] == 0:
                return _Resolution(
                    "INCONCLUSIVE",
                    reason_codes=("DIVISION_BY_ZERO",),
                )
            value = values[0] / values[1]
        elif operator == "ABS":
            value = abs(values[0])
        elif operator == "MIN":
            value = min(values)
        elif operator == "MAX":
            value = max(values)
        else:
            value = Fraction(values[0].numerator // values[0].denominator)
        return _Resolution("RESOLVED", value)

    def resolve_expression(
        self,
        expression: Mapping[str, Any],
        observations: Mapping[str, Any],
        context: Mapping[str, Any],
        inconclusive_metrics: Iterable[str] = (),
    ) -> ExpressionResolution:
        """Evaluate RELEASE_EXPR_AST_V1 without eval, floats, or free-form text."""

        resolved = self._resolve_expression(
            expression,
            observations,
            context,
            set(inconclusive_metrics),
            depth=0,
            budget=[self._MAX_EXPRESSION_NODES],
            reference_stack=(),
        )
        value = None
        if resolved.status == "RESOLVED":
            try:
                value = self._fraction_decimal(resolved.value)
            except PolicyError:
                resolved = _Resolution(
                    "FAIL",
                    reason_codes=("NON_TERMINATING_DECIMAL_RESULT",),
                )
        return ExpressionResolution(
            status=resolved.status,
            value=value,
            reason_codes=tuple(sorted(resolved.reason_codes)),
        )

    def _resolve_threshold(
        self,
        gate: Mapping[str, Any],
        observations: Mapping[str, Any],
        context: Mapping[str, Any],
        binding_documents: Mapping[str, Any],
        inconclusive_metrics: Set[str],
    ) -> _Resolution:
        if "threshold" in gate:
            return _Resolution("RESOLVED", gate["threshold"])
        if "threshold_ast" in gate:
            resolved = self._resolve_expression(
                gate["threshold_ast"],
                observations,
                context,
                inconclusive_metrics,
                depth=0,
                budget=[self._MAX_EXPRESSION_NODES],
                reference_stack=(),
            )
            return self._render_expression_threshold(resolved)
        if "threshold_ast_ref" in gate:
            path = gate["threshold_ast_ref"]
            try:
                expression = self._policy_path(self.policy, path)
            except PolicyError:
                return _Resolution(
                    "FAIL",
                    reason_codes=(f"UNKNOWN_EXPRESSION_REFERENCE:{path}",),
                )
            resolved = self._resolve_expression(
                expression,
                observations,
                context,
                inconclusive_metrics,
                depth=0,
                budget=[self._MAX_EXPRESSION_NODES],
                reference_stack=(path,),
            )
            return self._render_expression_threshold(resolved)
        if "threshold_reference" in gate:
            reference = gate["threshold_reference"]
            binding = reference["binding"]
            if binding not in binding_documents:
                return _Resolution(
                    "FAIL",
                    reason_codes=(f"MISSING_BINDING_DOCUMENT:{binding}",),
                )
            template = reference["json_pointer_template"]

            def substitute(match: "re.Match[str]") -> str:
                attribute = match.group(1)
                if attribute == "ai_endpoint_or_baseline":
                    value = context.get(
                        attribute,
                        context.get("ai_endpoint") or "BASELINE",
                    )
                elif attribute in context:
                    value = context[attribute]
                else:
                    raise PolicyError(
                        f"missing JSON Pointer template attribute: {attribute}"
                    )
                if value is None or isinstance(value, (dict, list)):
                    raise PolicyError(
                        f"invalid JSON Pointer template attribute: {attribute}"
                    )
                return str(value).replace("~", "~0").replace("/", "~1")

            try:
                pointer = re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", substitute, template)
                if "{" in pointer or "}" in pointer:
                    raise PolicyError("invalid unresolved JSON Pointer template")
                value = self._json_pointer(binding_documents[binding], pointer)
                return _Resolution("RESOLVED", value)
            except PolicyError as exc:
                return _Resolution(
                    "FAIL",
                    reason_codes=(
                        f"THRESHOLD_REFERENCE_UNRESOLVED:{binding}:{str(exc)}",
                    ),
                )
        return _Resolution("FAIL", reason_codes=("MISSING_GATE_THRESHOLD",))

    def _render_expression_threshold(self, resolved: _Resolution) -> _Resolution:
        if resolved.status != "RESOLVED":
            return resolved
        try:
            return _Resolution("RESOLVED", self._fraction_decimal(resolved.value))
        except PolicyError:
            return _Resolution(
                "FAIL",
                reason_codes=("NON_TERMINATING_DECIMAL_RESULT",),
            )

    @staticmethod
    def _coerce_scalar(
        value_type: str,
        value: Any,
        *,
        threshold: bool = False,
    ) -> Tuple[Any, Any]:
        if value_type == "boolean":
            if not isinstance(value, bool):
                raise PolicyError("boolean metric requires a boolean value")
            return value, value
        if value_type == "integer":
            if isinstance(value, bool) or isinstance(value, float):
                raise PolicyError("integer metric requires an exact integer")
            if not threshold and not isinstance(value, int):
                raise PolicyError("integer metric evidence must use a JSON integer")
            try:
                decimal = Decimal(canonical_decimal(value))
            except CanonicalizationError as exc:
                raise PolicyError("invalid integer metric") from exc
            if decimal != decimal.to_integral_value():
                raise PolicyError("integer metric contains a fractional value")
            integer = int(decimal)
            return integer, integer
        if value_type == "decimal":
            if isinstance(value, bool) or isinstance(value, float):
                raise PolicyError("decimal metric requires an exact value")
            try:
                rendered = canonical_decimal(value)
            except CanonicalizationError as exc:
                raise PolicyError("invalid decimal metric") from exc
            return Decimal(rendered), rendered
        raise PolicyError(f"unknown metric value type: {value_type}")

    @staticmethod
    def _comparison(comparator: str, left: Any, right: Any) -> bool:
        operations = {
            "EQ": lambda: left == right,
            "NEQ": lambda: left != right,
            "GT": lambda: left > right,
            "GTE": lambda: left >= right,
            "LT": lambda: left < right,
            "LTE": lambda: left <= right,
        }
        if comparator not in operations:
            raise PolicyError(f"unsupported gate comparator: {comparator}")
        try:
            return operations[comparator]()
        except TypeError as exc:
            raise PolicyError("metric and threshold types cannot be compared") from exc

    @staticmethod
    def _gate_evaluation(
        *,
        gate_group_id: str,
        gate: Mapping[str, Any],
        result: str,
        observed_value: Any,
        threshold_value: Any,
        reasons: Iterable[str],
    ) -> GateEvaluation:
        reason_codes = tuple(sorted(set(reasons)))
        payload = {
            "gate_group_id": gate_group_id,
            "gate_id": gate.get("gate_id", "UNKNOWN"),
            "metric_id": gate.get("metric_id", "unknown"),
            "result": result,
            "observed_value": observed_value,
            "threshold_value": threshold_value,
            "comparator": gate.get("comparator", "UNKNOWN"),
            "reason_codes": reason_codes,
        }
        return GateEvaluation(
            gate_group_id=gate_group_id,
            gate_id=payload["gate_id"],
            metric_id=payload["metric_id"],
            result=result,
            observed_value=observed_value,
            threshold_value=threshold_value,
            comparator=payload["comparator"],
            reason_codes=reason_codes,
            result_hash=business_hash(payload),
        )

    def evaluate_gate(
        self,
        gate_group_id: str,
        gate: Mapping[str, Any],
        observations: Mapping[str, Any],
        context: Mapping[str, Any],
        *,
        binding_documents: Optional[Mapping[str, Any]] = None,
        inconclusive_metrics: Iterable[str] = (),
    ) -> GateEvaluation:
        """Evaluate any literal, AST, AST-ref, or bound-threshold gate."""

        binding_documents = binding_documents or {}
        inconclusive = set(inconclusive_metrics)
        try:
            definition = self.metrics.resolve(gate["metric_id"])
        except (KeyError, PolicyError):
            return self._gate_evaluation(
                gate_group_id=gate_group_id,
                gate=gate,
                result="FAIL",
                observed_value=None,
                threshold_value=None,
                reasons=("UNKNOWN_GATE_METRIC",),
            )

        for condition in gate.get("applies_when", {}).get("all", ()):
            match = self._condition_matches(condition, context)
            if match == "MISSING":
                return self._gate_evaluation(
                    gate_group_id=gate_group_id,
                    gate=gate,
                    result="FAIL",
                    observed_value=None,
                    threshold_value=None,
                    reasons=(
                        f"CONDITION_FIELD_MISSING:{condition.get('attribute')}",
                    ),
                )
            if match == "UNSUPPORTED":
                return self._gate_evaluation(
                    gate_group_id=gate_group_id,
                    gate=gate,
                    result="FAIL",
                    observed_value=None,
                    threshold_value=None,
                    reasons=("UNSUPPORTED_GATE_CONDITION",),
                )
            if match == "NO_MATCH":
                return self._gate_evaluation(
                    gate_group_id=gate_group_id,
                    gate=gate,
                    result="NOT_APPLICABLE",
                    observed_value=None,
                    threshold_value=None,
                    reasons=("CONDITION_FALSE",),
                )

        metric_id = gate["metric_id"]
        if metric_id in inconclusive:
            return self._gate_evaluation(
                gate_group_id=gate_group_id,
                gate=gate,
                result="INCONCLUSIVE",
                observed_value=None,
                threshold_value=None,
                reasons=(f"INSUFFICIENT_SAMPLE:{metric_id}",),
            )
        if metric_id not in observations:
            return self._gate_evaluation(
                gate_group_id=gate_group_id,
                gate=gate,
                result="FAIL",
                observed_value=None,
                threshold_value=None,
                reasons=(f"MISSING_METRIC:{metric_id}",),
            )

        threshold = self._resolve_threshold(
            gate,
            observations,
            context,
            binding_documents,
            inconclusive,
        )
        if threshold.status != "RESOLVED":
            return self._gate_evaluation(
                gate_group_id=gate_group_id,
                gate=gate,
                result=threshold.status,
                observed_value=None,
                threshold_value=None,
                reasons=threshold.reason_codes,
            )
        try:
            observed, observed_snapshot = self._coerce_scalar(
                definition["value_type"],
                observations[metric_id],
            )
            expected, threshold_snapshot = self._coerce_scalar(
                definition["value_type"],
                threshold.value,
                threshold=True,
            )
            passed = self._comparison(gate["comparator"], observed, expected)
        except (KeyError, PolicyError):
            return self._gate_evaluation(
                gate_group_id=gate_group_id,
                gate=gate,
                result="FAIL",
                observed_value=None,
                threshold_value=None,
                reasons=("INVALID_METRIC_OR_THRESHOLD",),
            )
        return self._gate_evaluation(
            gate_group_id=gate_group_id,
            gate=gate,
            result="PASS" if passed else "FAIL",
            observed_value=observed_snapshot,
            threshold_value=threshold_snapshot,
            reasons=() if passed else ("COMPARISON_FALSE",),
        )

    def _scope_reason_codes(
        self,
        gate_group_id: str,
        actual_scope: Mapping[str, Any],
        expected_scope: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Tuple[str, ...]:
        reasons: List[str] = []
        required = list(self.policy["evidence_scope"]["required_dimensions"])
        route = actual_scope.get("release_route")
        if route == "AI_ENHANCED":
            required.extend(self.policy["evidence_scope"]["ai_dimensions"])
        if actual_scope.get("stage") in ("CANARY_25", "CANARY_50", "CANARY_75"):
            required.extend(self.policy["evidence_scope"]["canary_dimensions"])
        for name in sorted(set(required)):
            if name not in actual_scope:
                reasons.append(f"SCOPE_DIMENSION_MISSING:{name}")
        if actual_scope.get("gate_group_id") != gate_group_id:
            reasons.append("SCOPE_GATE_GROUP_MISMATCH")
        for name in sorted(set(required) & set(context)):
            try:
                matches = business_hash(actual_scope.get(name)) == business_hash(
                    context[name]
                )
            except CanonicalizationError:
                matches = False
            if not matches:
                reasons.append(f"SCOPE_CONTEXT_MISMATCH:{name}")

        actual_keys = set(actual_scope)
        expected_keys = set(expected_scope)
        for name in sorted(expected_keys - actual_keys):
            reasons.append(f"SCOPE_KEY_MISSING:{name}")
        for name in sorted(actual_keys - expected_keys):
            reasons.append(f"SCOPE_KEY_UNEXPECTED:{name}")
        for name in sorted(actual_keys & expected_keys):
            try:
                matches = business_hash(actual_scope[name]) == business_hash(
                    expected_scope[name]
                )
            except CanonicalizationError:
                matches = False
            if not matches:
                reasons.append(f"SCOPE_VALUE_MISMATCH:{name}")
        return tuple(sorted(set(reasons)))

    def evaluate_group(
        self,
        gate_group_id: str,
        observations: Mapping[str, Any],
        context: Mapping[str, Any],
        *,
        actual_scope: Mapping[str, Any],
        expected_scope: Mapping[str, Any],
        binding_documents: Optional[Mapping[str, Any]] = None,
        inconclusive_metrics: Iterable[str] = (),
    ) -> GroupEvaluation:
        """Evaluate one scoped gate group and aggregate all required children."""

        groups = self.flat_gate_groups()
        if gate_group_id not in groups:
            raise PolicyError(f"unknown gate group: {gate_group_id}")
        scope_reasons = self._scope_reason_codes(
            gate_group_id,
            actual_scope,
            expected_scope,
            context,
        )
        if scope_reasons:
            gate_results = tuple(
                self._gate_evaluation(
                    gate_group_id=gate_group_id,
                    gate=gate,
                    result="FAIL",
                    observed_value=None,
                    threshold_value=None,
                    reasons=scope_reasons,
                )
                for gate in groups[gate_group_id]
            )
        else:
            gate_results = tuple(
                self.evaluate_gate(
                    gate_group_id,
                    gate,
                    observations,
                    context,
                    binding_documents=binding_documents,
                    inconclusive_metrics=inconclusive_metrics,
                )
                for gate in groups[gate_group_id]
            )

        required_results = [
            result
            for gate, result in zip(groups[gate_group_id], gate_results)
            if gate["required"]
        ]
        reasons = list(scope_reasons)
        failed = [result for result in required_results if result.result == "FAIL"]
        unresolved = [
            result
            for result in required_results
            if result.result == "INCONCLUSIVE"
        ]
        applicable = [
            result
            for result in required_results
            if result.result != "NOT_APPLICABLE"
        ]
        if failed:
            group_result = "FAIL"
            reasons.extend(f"REQUIRED_GATE_FAIL:{result.gate_id}" for result in failed)
        elif unresolved:
            group_result = "INCONCLUSIVE"
            reasons.extend(
                f"REQUIRED_GATE_INCONCLUSIVE:{result.gate_id}"
                for result in unresolved
            )
        elif not applicable:
            group_result = "NOT_APPLICABLE"
            reasons.append("NO_APPLICABLE_REQUIRED_GATES")
        else:
            group_result = "PASS"

        reason_codes = tuple(sorted(set(reasons)))
        try:
            scope_hash = business_hash(actual_scope)
        except CanonicalizationError:
            scope_hash = "INVALID_SCOPE"
            reason_codes = tuple(
                sorted(set(reason_codes + ("SCOPE_NOT_CANONICAL",)))
            )
            if group_result != "FAIL":
                group_result = "FAIL"
        payload = {
            "gate_group_id": gate_group_id,
            "result": group_result,
            "gate_result_hashes": [item.result_hash for item in gate_results],
            "reason_codes": reason_codes,
            "scope_hash": scope_hash,
        }
        return GroupEvaluation(
            gate_group_id=gate_group_id,
            result=group_result,
            gate_results=gate_results,
            reason_codes=reason_codes,
            result_hash=business_hash(payload),
        )

    def readiness(self) -> EvaluationResult:
        """Return FAIL until every required binding and activation control passes."""

        reasons = []
        for binding in self.policy["required_policy_bindings"]:
            if binding["value"] is None:
                reasons.append(f"MISSING_BINDING:{binding['binding']}")
        if self.policy["status"] != "ACTIVE":
            reasons.append(f"POLICY_STATUS:{self.policy['status']}")
        if not self.policy["production_activation"]["enabled"]:
            reasons.append("PRODUCTION_ACTIVATION_DISABLED")
        result = "PASS" if not reasons else "FAIL"
        payload = {
            "result": result,
            "reason_codes": sorted(reasons),
            "policy_id": self.policy["policy_id"],
            "policy_version": self.policy["policy_version"],
        }
        return EvaluationResult(
            result=result,
            reason_codes=tuple(sorted(reasons)),
            policy_id=self.policy["policy_id"],
            policy_version=self.policy["policy_version"],
            result_hash=business_hash(payload),
        )

    @staticmethod
    def _condition_matches(condition: Mapping[str, Any], context: Mapping[str, Any]) -> str:
        attribute = condition.get("attribute")
        if not isinstance(attribute, str):
            return "UNSUPPORTED"
        if attribute not in context:
            return "MISSING"
        value = context[attribute]
        expected = condition.get("value")
        comparator = condition.get("comparator")
        if comparator not in ("EQ", "NEQ", "IN", "NOT_IN"):
            return "UNSUPPORTED"
        if comparator in ("IN", "NOT_IN") and not isinstance(expected, list):
            return "UNSUPPORTED"
        operations = {
            "EQ": value == expected,
            "NEQ": value != expected,
            "IN": value in expected if isinstance(expected, list) else False,
            "NOT_IN": value not in expected if isinstance(expected, list) else False,
        }
        return "MATCH" if operations.get(comparator, False) else "NO_MATCH"

    def evaluate_literal_gate(
        self,
        gate: Mapping[str, Any],
        evidence: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> str:
        """Evaluate a literal-threshold gate; unsupported input fails closed."""

        try:
            definition = self.metrics.resolve(gate["metric_id"])
        except (KeyError, PolicyError):
            return "FAIL"
        applies = gate.get("applies_when", {}).get("all", ())
        for condition in applies:
            match = self._condition_matches(condition, context)
            if match in ("MISSING", "UNSUPPORTED"):
                return "FAIL"
            if match == "NO_MATCH":
                return "NOT_APPLICABLE"
        if gate["metric_id"] not in evidence or "threshold" not in gate:
            return "FAIL"

        value = evidence[gate["metric_id"]]
        threshold = gate["threshold"]
        comparator = gate["comparator"]
        try:
            if definition["value_type"] == "decimal":
                left: Any = Decimal(canonical_decimal(value))
                right: Any = Decimal(canonical_decimal(threshold))
            else:
                left, right = value, threshold
            operations = {
                "EQ": left == right,
                "NEQ": left != right,
                "GT": left > right,
                "GTE": left >= right,
                "LT": left < right,
                "LTE": left <= right,
                "IN": left in right if isinstance(right, list) else False,
                "NOT_IN": left not in right if isinstance(right, list) else False,
            }
            return "PASS" if operations[comparator] else "FAIL"
        except (KeyError, TypeError, ValueError, ArithmeticError):
            return "FAIL"
