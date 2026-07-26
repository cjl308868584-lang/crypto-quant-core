"""Deterministic evaluator build manifest verification."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash
from .errors import PolicyError
from .estimators import EstimatorRegistry, _load_json_strict
from .evidence import artifact_self_hash


_FROZEN_CONFIG_PATHS = (
    "config/approved-fallback-registry-v1.1.schema.json",
    "config/deployment-line-v1.1.schema.json",
    "config/economic-ledger-snapshot-v1.schema.json",
    "config/endpoint-reevaluation-snapshot-v1.schema.json",
    "config/estimator-golden-vectors-v1.json",
    "config/estimator-golden-vectors-v1.schema.json",
    "config/estimator-registry-v1.json",
    "config/estimator-registry-v1.schema.json",
    "config/evaluator-build-manifest-v1.schema.json",
    "config/experiment-manifest-v1.1.schema.json",
    "config/model-bundle-v1.1.schema.json",
    "config/recipe-release-v1.1.schema.json",
    "config/release-evidence-v1.1.schema.json",
    "config/release-gates-v1.1.json",
    "config/release-gates-v1.1.schema.json",
    "config/release-metrics-v1.1.json",
    "config/release-metrics-v1.1.schema.json",
    "config/supporting-observation-bundle-v1.schema.json",
    "config/statistical-series-snapshot-v1.schema.json",
    "pyproject.toml",
    "requirements.lock",
)


@dataclass(frozen=True)
class EvaluatorBuild:
    manifest_id: str
    manifest_version: str
    build_hash: str
    build_input_tree_hash: str
    executable_estimator_count: int
    unavailable_estimator_count: int
    golden_report_hash: str

    @staticmethod
    def expected_file_paths(workspace_root: Path) -> Tuple[str, ...]:
        source = sorted(
            str(path.relative_to(workspace_root))
            for path in (workspace_root / "src" / "crypto_quant").glob("*.py")
        )
        return tuple(sorted(source + list(_FROZEN_CONFIG_PATHS)))

    @staticmethod
    def file_hashes(
        workspace_root: Path,
        paths: Tuple[str, ...],
    ) -> Dict[str, str]:
        hashes = {}
        for relative in paths:
            path = workspace_root / relative
            if not path.is_file():
                raise PolicyError(f"evaluator build input missing: {relative}")
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes

    @classmethod
    def load(
        cls,
        workspace_root: Path,
        estimators: EstimatorRegistry,
    ) -> "EvaluatorBuild":
        workspace_root = Path(workspace_root)
        config_dir = workspace_root / "config"
        schema = _load_json_strict(
            config_dir / "evaluator-build-manifest-v1.schema.json"
        )
        Draft202012Validator.check_schema(schema)
        manifest = _load_json_strict(
            config_dir / "evaluator-build-manifest-v1.json"
        )
        errors = list(Draft202012Validator(schema).iter_errors(manifest))
        if errors:
            first = min(
                errors,
                key=lambda error: "/".join(map(str, error.absolute_path)),
            )
            location = "/".join(map(str, first.absolute_path))
            raise PolicyError(
                f"EvaluatorBuild schema failure at {location}: {first.message}"
            )
        if artifact_self_hash(manifest, "manifest_hash") != manifest["manifest_hash"]:
            raise PolicyError("EvaluatorBuild self hash mismatch")
        expected_paths = cls.expected_file_paths(workspace_root)
        if set(manifest["file_hashes"]) != set(expected_paths):
            raise PolicyError("EvaluatorBuild file set mismatch")
        actual_hashes = cls.file_hashes(workspace_root, expected_paths)
        if manifest["file_hashes"] != actual_hashes:
            changed = sorted(
                path
                for path in expected_paths
                if manifest["file_hashes"].get(path) != actual_hashes[path]
            )
            raise PolicyError(f"EvaluatorBuild input hash mismatch: {changed}")
        tree_hash = business_hash(actual_hashes)
        if manifest["build_input_tree_hash"] != tree_hash:
            raise PolicyError("EvaluatorBuild input tree hash mismatch")
        report = estimators.run_golden_vectors()
        project_text = (workspace_root / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        version_match = re.search(
            r'^version = "([0-9]+\.[0-9]+\.[0-9]+)"$',
            project_text,
            flags=re.MULTILINE,
        )
        if version_match is None:
            raise PolicyError("EvaluatorBuild package version cannot be resolved")
        checks: Mapping[str, Any] = {
            "package_version": version_match.group(1),
            "metric_catalog_id": estimators.catalog["catalog_id"],
            "metric_catalog_version": estimators.catalog["catalog_version"],
            "catalog_algorithm_count": len(estimators.catalog["algorithms"]),
            "estimator_registry_id": estimators.registry["registry_id"],
            "estimator_registry_hash": estimators.registry_hash,
            "golden_bundle_id": estimators.golden_vectors["bundle_id"],
            "golden_bundle_hash": estimators.golden_bundle_hash,
            "golden_report_hash": report.report_hash,
            "golden_vector_count": report.vector_count,
            "executable_estimator_count": len(
                estimators.executable_estimator_ids
            ),
            "unavailable_estimator_count": len(
                estimators.unavailable_estimator_ids
            ),
        }
        for name, expected in checks.items():
            if manifest[name] != expected:
                raise PolicyError(f"EvaluatorBuild field mismatch: {name}")
        if not report.passed:
            raise PolicyError("EvaluatorBuild golden vectors failed")
        if manifest["capabilities"]["all_catalog_estimators_executable"] != (
            not estimators.unavailable_estimator_ids
        ):
            raise PolicyError("EvaluatorBuild estimator coverage claim mismatch")
        return cls(
            manifest_id=manifest["manifest_id"],
            manifest_version=manifest["manifest_version"],
            build_hash=manifest["manifest_hash"],
            build_input_tree_hash=tree_hash,
            executable_estimator_count=len(
                estimators.executable_estimator_ids
            ),
            unavailable_estimator_count=len(
                estimators.unavailable_estimator_ids
            ),
            golden_report_hash=report.report_hash,
        )
