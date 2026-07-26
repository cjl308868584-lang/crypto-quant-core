"""Deterministic ReleasePolicy loader and fail-closed evaluator skeleton."""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Set, Tuple

from jsonschema import Draft202012Validator, FormatChecker

from .canonical import business_hash, canonical_decimal
from .errors import PolicyError


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
