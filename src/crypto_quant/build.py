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
    "config/baseline-failure-attribution-v1.schema.json",
    "config/causal-feature-label-dataset-v1.schema.json",
    "config/challenger-prequential-snapshot-v1.schema.json",
    "config/challenger-forward-source-bundle-v1.schema.json",
    "config/challenger-first-slot-receipt-v1.schema.json",
    "config/challenger-launchd-contract-v1.schema.json",
    "config/challenger-launchd-install-receipt-v1.schema.json",
    "config/contemporaneous-capture-snapshot-v1.schema.json",
    "config/deployment-line-v1.1.schema.json",
    "config/economic-ledger-snapshot-v1.schema.json",
    "config/endpoint-reevaluation-snapshot-v1.schema.json",
    "config/estimator-golden-vectors-v1.json",
    "config/estimator-golden-vectors-v1.schema.json",
    "config/estimator-registry-v1.json",
    "config/estimator-registry-v1.schema.json",
    "config/evaluator-build-manifest-v1.schema.json",
    "config/experiment-manifest-v1.1.schema.json",
    "config/account-commission-snapshot-v1.schema.json",
    "config/fee-schedule-snapshot-v1.schema.json",
    "config/historical-market-data-snapshot-v1.schema.json",
    "config/historical-execution-source-v1.schema.json",
    "config/historical-research-corpus-plan-v1.schema.json",
    "config/historical-research-corpus-repair-v1.schema.json",
    "config/historical-research-corpus-snapshot-v1.schema.json",
    "config/model-bundle-v1.1.schema.json",
    "config/offline-paper-run-v1.schema.json",
    "config/paper-runtime-snapshot-v1.schema.json",
    "config/paper-schedule-snapshot-v1.schema.json",
    "config/paired-risk-evaluation-snapshot-v1.schema.json",
    "config/paper-account-cost-binding-v1.schema.json",
    "config/paper-context-schedule-snapshot-v1.schema.json",
    "config/paper-cycle-context-bundle-v1.schema.json",
    "config/context-cycle-orchestration-snapshot-v1.schema.json",
    "config/local-scheduler-contract-v1.schema.json",
    "config/logistic-archive-research-v1.schema.json",
    "config/perpetual-context-snapshot-v1.schema.json",
    "config/recipe-release-v1.1.schema.json",
    "config/release-evidence-v1.1.schema.json",
    "config/release-gates-v1.1.json",
    "config/release-gates-v1.1.schema.json",
    "config/release-metrics-v1.1.json",
    "config/release-metrics-v1.1.schema.json",
    "config/supporting-observation-bundle-v1.schema.json",
    "config/statistical-series-snapshot-v1.schema.json",
    "config/statistical-decision-snapshot-v1.schema.json",
    "config/server-time-probe-v1.schema.json",
    "config/trade-replay-snapshot-v1.schema.json",
    "pyproject.toml",
    "requirements.lock",
    "setup.py",
)
_FROZEN_ARTIFACT_PATHS = (
    "artifacts/account-cost/binance-account-commission-smoke-not-run-v0.22.0.json",
    "artifacts/baseline-research/binance-baseline-failure-attribution-v0.29.0.json",
    "artifacts/challenger-forward/binance-challenger-forward-not-run-v0.30.0.json",
    "artifacts/challenger-forward/binance-challenger-live-runner-not-run-v0.31.0.json",
    "artifacts/challenger-forward/challenger-first-slot-waiting-v0.34.0.json",
    "artifacts/challenger-forward/challenger-launchd-not-installed-v0.32.0.json",
    "artifacts/challenger-forward/challenger-launchd-installed-v0.33.0.json",
    "artifacts/paper-cost/binance-paper-account-cost-binding-not-run-v0.23.0.json",
    "artifacts/paper-context/binance-context-complete-cycle-not-run-v0.24.0.json",
    "artifacts/orchestration/context-cycle-orchestration-not-run-v0.25.0.json",
    "artifacts/research-corpus/binance-monthly-corpus-smoke-v0.26.0.json",
    "artifacts/research-corpus/binance-research-corpus-completion-v0.27.0.json",
    "artifacts/ai-research/binance-causal-logistic-research-v0.28.0.json",
    "artifacts/market-data/binance-contemporaneous-smoke-v0.17.0.json",
    "artifacts/market-data/binance-public-data-smoke-v0.16.0.json",
    "artifacts/paper/binance-offline-paper-smoke-v0.18.0.json",
    "artifacts/paper/paper-schedule-ethusdt_20260727t120000z.json",
    "artifacts/paper/paper-slot-ethusdt_20260727t120000z.json",
    "artifacts/market-data/binance-perpetual-context-smoke-failure-v0.21.0.json",
    "artifacts/runtime/v0.20-smoke/paper/paper-schedule-ethusdt_20260727t120000z.json",
    "artifacts/runtime/v0.20-smoke/paper/paper-slot-ethusdt_20260727t120000z.json",
    "artifacts/runtime/v0.20-smoke/runtime/paper-runtime-runtime_event_827acba8afd454ae735cd0c0d157b76beb125466a243b30159e2ee7233283f2c.json",
    "artifacts/runtime/v0.20-smoke/runtime/paper-runtime-runtime_event_ea4452a8f11abc78d4e8df0a02f57554e2ec918567b9bedb7c5df20d47b3e34e.json",
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
        package_resources = sorted(
            str(path.relative_to(workspace_root))
            for path in (workspace_root / "src" / "crypto_quant" / "schemas").glob(
                "*.json"
            )
        )
        return tuple(
            sorted(
                source
                + package_resources
                + list(_FROZEN_CONFIG_PATHS)
                + list(_FROZEN_ARTIFACT_PATHS)
            )
        )

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
