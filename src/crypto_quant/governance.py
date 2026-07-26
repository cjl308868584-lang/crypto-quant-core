"""Strict validation for unapproved Phase 0 governance templates."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash
from .errors import PolicyError
from .release import load_json_strict, strict_format_checker

_EXPECTED_TEMPLATES = {
    "experiment-manifest-v1.template.json": "EXPERIMENT_MANIFEST",
    "data-quality-policy-v1.template.json": "DATA_QUALITY_POLICY",
    "split-policy-v1.template.json": "SPLIT_POLICY",
    "statistical-design-policy-v1.template.json": "STATISTICAL_DESIGN_POLICY",
    "accounting-policy-v1.template.json": "ACCOUNTING_POLICY",
    "cost-allocation-policy-v1.template.json": "COST_ALLOCATION_POLICY",
    "forward-control-policy-v1.template.json": "FORWARD_CONTROL_POLICY",
    "incident-report-v1.template.json": "INCIDENT_REPORT",
}


@dataclass(frozen=True)
class GovernanceValidationResult:
    template_count: int
    artifact_types: Tuple[str, ...]
    lifecycle_status: str
    production_eligible: bool
    bundle_hash: str


class GovernanceTemplateBundle:
    """Validate shape and frozen cross-template safety semantics."""

    def __init__(
        self,
        *,
        schema: Dict[str, Any],
        templates: Mapping[str, Dict[str, Any]],
    ) -> None:
        self.schema = schema
        self.templates = dict(templates)
        self.validator = Draft202012Validator(
            schema,
            format_checker=strict_format_checker(),
        )

    @classmethod
    def load(cls, config_dir: Path) -> "GovernanceTemplateBundle":
        config_dir = Path(config_dir)
        schema = load_json_strict(
            config_dir / "governance-artifact-v1.schema.json"
        )
        Draft202012Validator.check_schema(schema)
        template_dir = config_dir / "templates"
        actual_files = {path.name for path in template_dir.glob("*.json")}
        expected_files = set(_EXPECTED_TEMPLATES)
        if actual_files != expected_files:
            raise PolicyError(
                "governance template files mismatch; "
                f"missing={sorted(expected_files - actual_files)}, "
                f"extra={sorted(actual_files - expected_files)}"
            )
        templates = {
            filename: load_json_strict(template_dir / filename)
            for filename in sorted(expected_files)
        }
        bundle = cls(schema=schema, templates=templates)
        for filename, artifact in templates.items():
            expected_type = _EXPECTED_TEMPLATES[filename]
            if artifact.get("artifact_type") != expected_type:
                raise PolicyError(
                    f"{filename}: expected artifact_type {expected_type}"
                )
            bundle.validate_artifact(artifact, label=filename)
        return bundle

    def validate_artifact(
        self,
        artifact: Mapping[str, Any],
        *,
        label: str = "GovernanceArtifact",
    ) -> None:
        errors = list(self.validator.iter_errors(artifact))
        if errors:
            first = min(
                errors,
                key=lambda error: "/".join(map(str, error.path)),
            )
            location = "/".join(str(part) for part in first.path)
            raise PolicyError(
                f"{label} schema failure at {location}: {first.message}"
            )
        if artifact["lifecycle_status"] != "TEMPLATE_UNAPPROVED":
            raise PolicyError(f"{label}: template lifecycle must remain unapproved")
        if artifact["production_eligible"] is not False:
            raise PolicyError(f"{label}: template cannot be production eligible")
        if artifact["artifact_id_or_null"] is not None:
            raise PolicyError(f"{label}: template cannot carry an approved artifact ID")
        if any(value is not None for value in artifact["approval"].values()):
            raise PolicyError(f"{label}: template cannot carry approval evidence")
        self._validate_semantics(artifact, label)

    @staticmethod
    def _validate_semantics(
        artifact: Mapping[str, Any],
        label: str,
    ) -> None:
        artifact_type = artifact["artifact_type"]
        specification = artifact["specification"]
        if artifact_type == "DATA_QUALITY_POLICY":
            products = {
                rule["product"] for rule in specification["product_data_matrix"]
            }
            if products != {"SPOT_LONG", "USDT_PERP_SHORT"}:
                raise PolicyError(f"{label}: product data matrix is incomplete")
        elif artifact_type == "FORWARD_CONTROL_POLICY":
            drawdown = {
                item["threshold"]: item["action"]
                for item in specification["drawdown_actions"]
            }
            expected = {
                "0.12": "HALVE_APPROVED_RISK",
                "0.15": "FLATTEN_AND_HALT",
                "0.20": "FLATTEN_DISABLE_AUTO_RESTART_AND_INCIDENT",
            }
            if drawdown != expected:
                raise PolicyError(f"{label}: drawdown harm boundaries changed")
        elif artifact_type == "COST_ALLOCATION_POLICY":
            required = set(specification["required_cost_event_types"])
            if required != {
                "OperatingCost",
                "AIInferenceCost",
                "ModelTrainingCost",
                "MonitoringAndAuditCost",
            }:
                raise PolicyError(f"{label}: required cost facts are incomplete")
        elif artifact_type == "INCIDENT_REPORT":
            if specification["report_status"] != "DRAFT":
                raise PolicyError(f"{label}: reusable incident template must be DRAFT")
        elif artifact_type == "EXPERIMENT_MANIFEST":
            identity = specification["identity_and_lineage"]
            if identity["run_status"] != "PLANNED":
                raise PolicyError(f"{label}: reusable experiment template must be PLANNED")
            search = specification["search_budget"]
            observed_trials = sum(
                search[field]
                for field in (
                    "aborted_trials",
                    "failed_trials",
                    "invalid_trials",
                )
            )
            if observed_trials > search["actual_total_trials"]:
                raise PolicyError(f"{label}: failed trial counts exceed all trials")

    def result(self) -> GovernanceValidationResult:
        artifact_types = tuple(
            sorted(
                artifact["artifact_type"]
                for artifact in self.templates.values()
            )
        )
        payload = {
            filename: {
                "artifact_type": artifact["artifact_type"],
                "template_hash": business_hash(artifact),
            }
            for filename, artifact in sorted(self.templates.items())
        }
        return GovernanceValidationResult(
            template_count=len(self.templates),
            artifact_types=artifact_types,
            lifecycle_status="TEMPLATE_UNAPPROVED",
            production_eligible=False,
            bundle_hash=business_hash(payload),
        )
