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
    "config/challenger-cohort-daily-archive-receipt-v1.schema.json",
    "config/challenger-cohort-evidence-maintenance-launchd-contract-v1.schema.json",
    "config/challenger-cohort-evidence-maintenance-deployment-manifest-v1.schema.json",
    "config/challenger-cohort-evidence-maintenance-launchd-install-receipt-v1.schema.json",
    "config/challenger-cohort-evidence-maintenance-first-run-receipt-v1.schema.json",
    "config/challenger-cohort-failure-receipt-v1.schema.json",
    "config/challenger-cohort-decommission-receipt-v1.schema.json",
    "config/challenger-cohort-cumulative-evaluation-v1.schema.json",
    "config/challenger-cohort-economic-result-index-v1.schema.json",
    "config/challenger-cohort-episode-economic-result-v1.schema.json",
    "config/challenger-cohort-evaluation-plan-v1.schema.json",
    "config/challenger-cohort-episode-receipt-v1.schema.json",
    "config/challenger-episode-archive-receipt-v1.schema.json",
    "config/challenger-episode-cohort-plan-v1.schema.json",
    "config/challenger-episode-economic-result-v1.schema.json",
    "config/challenger-prequential-snapshot-v1.schema.json",
    "config/challenger-replacement-plan-v1.schema.json",
    "config/challenger-episode-economic-plan-v1.schema.json",
    "config/challenger-forward-source-bundle-v1.schema.json",
    "config/challenger-first-episode-receipt-v1.schema.json",
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
    "config/nautilus-sandbox-comparison-v1.schema.json",
    "config/nautilus-sandbox-dependency-lock-v1.schema.json",
    "config/offline-paper-run-v1.schema.json",
    "config/operations-projection-v1.schema.json",
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
    "config/system-paper-plan-v1.schema.json",
    "config/system-paper-market-bundle-v1.schema.json",
    "config/system-paper-launchd-contract-v1.schema.json",
    "config/system-paper-preflight-receipt-v1.schema.json",
    "config/system-paper-install-receipt-v1.schema.json",
    "config/system-paper-start-receipt-v1.schema.json",
    "config/system-paper-slot-result-v1.schema.json",
    "config/system-paper-evaluation-v1.schema.json",
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
    "artifacts/challenger-forward/challenger-cohort-evaluation-plan-v0.44.0.json",
    "artifacts/challenger-forward/challenger-cohort-evidence-maintenance-launchd-not-installed-v0.50.0.json",
    "artifacts/challenger-forward/challenger-cohort-evidence-maintenance-install-candidate-v0.51.0.json",
    "artifacts/challenger-forward/challenger-cohort-evidence-maintenance-installed-v0.51.0.json",
    "artifacts/challenger-forward/challenger-cohort-evidence-maintenance-first-run-waiting-v0.52.0.json",
    "artifacts/challenger-forward/challenger-cohort-evidence-maintenance-first-run-receipt-v0.53.0.json",
    "artifacts/challenger-forward/challenger-cohort-missed-slot-failure-receipt-v0.54.0.json",
    "artifacts/challenger-forward/challenger-cohort-decommission-receipt-v0.54.0.json",
    "artifacts/challenger-forward/challenger-episode-cohort-plan-v0.43.0.json",
    "artifacts/challenger-forward/challenger-episode-economic-result-v0.42.0.json",
    "artifacts/challenger-forward/challenger-episode-economic-plan-v0.37.0.json",
    "artifacts/challenger-forward/challenger-first-episode-in-progress-v0.36.0.json",
    "artifacts/challenger-forward/challenger-first-episode-receipt-v0.41.0.json",
    "artifacts/challenger-forward/challenger-first-slot-waiting-v0.34.0.json",
    "artifacts/challenger-forward/challenger-first-slot-receipt-v0.35.0.json",
    "artifacts/challenger-forward/challenger-launchd-not-installed-v0.32.0.json",
    "artifacts/challenger-replacement/challenger-replacement-plan-v0.62.0.json",
    "artifacts/nautilus-sandbox/nautilus-sandbox-comparison-v0.63.0.json",
    "artifacts/nautilus-sandbox/nautilus-sandbox-dependency-lock-v0.63.0.json",
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
    "artifacts/system-paper/system-paper-plan-v0.55.0.json",
)
_FROZEN_RELEASE_PATHS = (
    "tests/test_estimators.py",
    "tests/system_paper_fixtures.py",
    "tests/test_offline_paper.py",
    "tests/test_system_paper_scheduler.py",
    "tests/test_system_paper_fault_injection.py",
    "tests/test_system_paper_public_input.py",
    "tests/test_system_paper_runtime.py",
    "tests/test_system_paper_runtime_cli.py",
    "tests/test_system_paper_launchd.py",
    "tests/test_system_paper_preflight.py",
    "tests/test_system_paper_install.py",
    "tests/test_system_paper_observer.py",
    "tests/test_system_paper_start_receipt.py",
    "tests/test_system_paper_evidence.py",
    "tests/test_system_paper_launchctl.py",
    "tests/fixtures/launchctl/system-paper-not-running.txt",
    "tests/fixtures/launchctl/system-paper-first-success.txt",
    "docs/superpowers/specs/"
    "2026-08-02-system-paper-wal-scheduler-design.md",
    "docs/superpowers/plans/2026-08-02-system-paper-wal-scheduler.md",
    "docs/superpowers/specs/"
    "2026-08-03-system-paper-deployment-trust-chain-design.md",
    "docs/superpowers/plans/"
    "2026-08-03-system-paper-deployment-trust-chain.md",
    "docs/superpowers/specs/"
    "2026-08-04-system-paper-deployment-review-hardening-design.md",
    "docs/superpowers/plans/"
    "2026-08-04-system-paper-deployment-review-hardening.md",
    "docs/adr/0058-system-paper-deployment-trust-chain.md",
    "docs/implementation-status-v0.58.0.md",
    "README.md",
    "tests/test_system_paper_evaluation.py",
    "tests/test_system_paper_evaluation_cli.py",
    "docs/superpowers/specs/"
    "2026-08-04-system-paper-fixed-tail-evaluation-design.md",
    "docs/superpowers/plans/"
    "2026-08-04-system-paper-fixed-tail-evaluation.md",
    "docs/superpowers/specs/"
    "2026-08-04-system-paper-finalization-hardening-design.md",
    "docs/superpowers/plans/"
    "2026-08-04-system-paper-finalization-hardening.md",
    "docs/superpowers/specs/"
    "2026-08-05-system-paper-finalization-residual-design.md",
    "docs/superpowers/plans/"
    "2026-08-05-system-paper-finalization-residual.md",
    "docs/adr/0059-system-paper-fixed-tail-evaluation.md",
    "docs/implementation-status-v0.59.0.md",
    "tests/test_operations_projection.py",
    "docs/superpowers/specs/"
    "2026-08-05-tail-blind-operations-projection-design.md",
    "docs/superpowers/plans/"
    "2026-08-05-tail-blind-operations-projection.md",
    "docs/adr/0060-tail-blind-operations-projection.md",
    "docs/implementation-status-v0.60.0.md",
    "src/crypto_quant/dashboard/index.html",
    "src/crypto_quant/dashboard/app.js",
    "src/crypto_quant/dashboard/styles.css",
    "tests/test_operations_alerts.py",
    "tests/test_operations_dashboard.py",
    "tests/fixtures/operations-projection-healthy.json",
    "docs/superpowers/specs/"
    "2026-08-05-loopback-read-only-operations-console-design.md",
    "docs/superpowers/plans/"
    "2026-08-05-loopback-read-only-operations-console.md",
    "docs/runbooks/system-paper-operations.md",
    "docs/runbooks/operations-dashboard.md",
    "docs/adr/0061-loopback-read-only-operations-console.md",
    "docs/implementation-status-v0.61.0.md",
    "tests/test_challenger_replacement_plan.py",
    "docs/superpowers/specs/"
    "2026-08-05-replacement-challenger-preregistration-isolation-design.md",
    "docs/superpowers/plans/"
    "2026-08-05-replacement-challenger-preregistration-isolation.md",
    "docs/adr/0062-replacement-challenger-preregistration-isolation.md",
    "docs/implementation-status-v0.62.0.md",
    "sandboxes/nautilus/pyproject.toml",
    "sandboxes/nautilus/uv.lock",
    "sandboxes/nautilus/src/crypto_quant_nautilus_sandbox/__init__.py",
    "sandboxes/nautilus/tests/test_dependency_boundary.py",
    "tests/test_nautilus_sandbox_dependency.py",
    "tests/test_nautilus_evidence_adapter.py",
    "tests/test_nautilus_sandbox_artifacts.py",
    "docs/superpowers/specs/"
    "2026-08-05-nautilus-sandbox-isolation-spike-design.md",
    "docs/superpowers/plans/"
    "2026-08-05-nautilus-sandbox-isolation-spike.md",
    "docs/adr/0063-nautilus-sandbox-isolation-spike.md",
    "docs/implementation-status-v0.63.0.md",
    "scripts/refresh_evaluator_build_manifest.py",
)

_V064_PUBLIC_CI_PRIVATE_CONTRACT_PATHS = (
    ".github/workflows/ci.yml",
    ".gitattributes",
    ".gitignore",
    "artifacts/challenger-replacement/"
    "challenger-replacement-owner-attestation-v0.64.0.json",
    "artifacts/challenger-replacement/"
    "challenger-replacement-plan-supersession-v0.64.0.json",
    "artifacts/challenger-replacement/"
    "challenger-replacement-plan-v0.64.0.json",
    "artifacts/challenger-replacement/"
    "challenger-replacement-supersession-machine-evidence-v0.64.0.json",
    "artifacts/v064-public-ci-r2-failure/"
    "v064-public-ci-r2-failure-record-v1.json",
    "artifacts/v064-public-ci-r2-failure/"
    "v064-public-ci-r2-jobs-api-v1.json",
    "artifacts/v064-public-ci-r2-failure/"
    "v064-public-ci-r2-run-api-v1.json",
    "artifacts/v064-public-ci-r2-failure/"
    "v064-public-ci-r2-run-log-v1.txt",
    "artifacts/v064-public-ci-r3/"
    "v064-public-ci-r3-acquisition-transcript-v1.json",
    "artifacts/v064-public-ci-r3/v064-public-ci-r3-jobs-api-v1.json",
    "artifacts/v064-public-ci-r3/v064-public-ci-r3-run-api-v1.json",
    "artifacts/v064-public-ci-r3/v064-public-ci-r3-run-log-v1.txt",
    "artifacts/v064-public-ci-r3/v064-public-ci-r3-witness-v1.json",
    "config/challenger-replacement-owner-attestation-v1.schema.json",
    "config/challenger-replacement-plan-supersession-v1.schema.json",
    "config/challenger-replacement-plan-v2.schema.json",
    "config/challenger-replacement-supersession-machine-evidence-v1.schema.json",
    "config/v064-public-ci-bundle-manifest-v1.schema.json",
    "config/v064-public-ci-r2-failure-record-v1.schema.json",
    "config/v064-public-ci-witness-v1.schema.json",
    "docs/adr/0064-replacement-challenger-plan-v2-storage-supersession.md",
    "docs/implementation-status-v0.64.0.md",
    "docs/superpowers/plans/"
    "2026-08-09-replacement-challenger-plan-v2-supersession.md",
    "docs/superpowers/plans/2026-08-13-v064-minimal-public-ci-mirror.md",
    "docs/superpowers/plans/2026-08-16-v064-public-ci-r2-correction.md",
    "docs/superpowers/plans/"
    "2026-08-20-v064-public-ci-r3-interpreter-identity.md",
    "docs/superpowers/plans/"
    "2026-08-21-v064-public-core-ci-umask-correction.md",
    "docs/superpowers/specs/"
    "2026-08-09-replacement-challenger-plan-v2-supersession-design.md",
    "docs/superpowers/specs/"
    "2026-08-12-v064-minimal-public-ci-mirror-design.md",
    "docs/superpowers/specs/"
    "2026-08-15-v064-public-ci-r2-correction-design.md",
    "docs/superpowers/specs/"
    "2026-08-20-v064-public-ci-r3-interpreter-identity-design.md",
    "docs/superpowers/specs/"
    "2026-08-21-v064-public-core-ci-umask-correction-design.md",
    "public_ci/v064/.github/workflows/ci.yml",
    "public_ci/v064/.gitignore",
    "public_ci/v064/NOTICE.md",
    "public_ci/v064/README.md",
    "public_ci/v064/SECURITY.md",
    "tests/test_v064_linux_supersession_publish.py",
    "tests/test_challenger_replacement_plan_supersession.py",
    "tests/test_challenger_replacement_plan_v2.py",
    "tests/test_v064_public_ci_bundle.py",
    "tests/test_v064_public_ci_r2_failure.py",
    "tests/test_v064_public_ci_witness.py",
)

_V065_RELEASE_PATHS = (
    "config/nautilus-e2e-spike-plan-v1.schema.json",
    "config/nautilus-supply-chain-receipt-v2.schema.json",
    "config/nautilus-sandbox-request-v2.schema.json",
    "config/nautilus-sandbox-result-v2.schema.json",
    "config/nautilus-sandbox-comparison-v2.schema.json",
    "config/nautilus-formal-completion-v1.schema.json",
    "artifacts/nautilus-sandbox/nautilus-e2e-spike-plan-v0.65.0.json",
    "artifacts/nautilus-sandbox/v0.65.0/nautilus-supply-chain-receipt-v0.65.0.json",
    "artifacts/nautilus-sandbox/v0.65.0/nautilus-sandbox-comparison-v0.65.0.json",
    "artifacts/nautilus-sandbox/v0.65.0/nautilus-sandbox-complete-v0.65.0.json",
    "sandboxes/nautilus-v065/pyproject.toml",
    "sandboxes/nautilus-v065/uv.lock",
    "sandboxes/nautilus-v065/src/crypto_quant_nautilus_v065/__init__.py",
    "sandboxes/nautilus-v065/src/crypto_quant_nautilus_v065/runner.py",
    "sandboxes/nautilus-v065/tests/test_dependency_boundary.py",
    "sandboxes/nautilus-v065/tests/test_runner_failures.py",
    "sandboxes/nautilus-v065/tests/test_runner_golden.py",
    "tests/fixtures/nautilus-v065/LICENSE-1.230.0.txt",
    "tests/fixtures/nautilus-v065/current-reference-v2.json",
    "tests/fixtures/nautilus-v065/ethusdt-4h-input-v2.json",
    "tests/test_nautilus_v065_plan.py",
    "tests/test_nautilus_v065_supply_chain.py",
    "tests/test_nautilus_v065_acquisition.py",
    "tests/test_nautilus_v065_contract.py",
    "tests/test_nautilus_v065_evidence.py",
    "tests/test_nautilus_v065_artifacts.py",
    "tests/test_nautilus_v065_release.py",
    "tests/test_nautilus_v0651_hardening.py",
    "docs/superpowers/specs/2026-08-22-nautilus-end-to-end-spike-design.md",
    "docs/superpowers/plans/2026-08-22-nautilus-end-to-end-spike.md",
    "docs/adr/0065-nautilus-end-to-end-spike.md",
    "docs/implementation-status-v0.65.0.md",
    "docs/implementation-status-v0.65.1.md",
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
                + list(_FROZEN_RELEASE_PATHS)
                + list(_V064_PUBLIC_CI_PRIVATE_CONTRACT_PATHS)
                + list(_V065_RELEASE_PATHS)
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
