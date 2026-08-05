import ast
import json
import re
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import crypto_quant
from crypto_quant.build import EvaluatorBuild
from crypto_quant.errors import PolicyError
from crypto_quant.estimators import EstimatorRegistry
from crypto_quant.release import load_json_strict
from crypto_quant.statistical_decision import (
    statistical_decision_snapshot_hash,
)
from crypto_quant.statistics import statistical_series_hash
from crypto_quant.trade_replay import (
    build_trade_replay_snapshot,
    trade_replay_snapshot_hash,
)

from tests.factories import (
    complete_trade_replay_inputs,
    make_statistical_decision_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]


class EstimatorRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_json_strict(
            ROOT / "config" / "release-metrics-v1.1.json"
        )
        cls.registry = EstimatorRegistry.load(ROOT / "config", cls.catalog)

    def test_every_catalog_algorithm_resolves_without_implicit_execution(self):
        all_ids = set(self.catalog["algorithms"])
        executable = set(self.registry.executable_estimator_ids)
        unavailable = set(self.registry.unavailable_estimator_ids)

        self.assertEqual(self.catalog["catalog_version"], "1.1.6")
        self.assertEqual(
            self.registry.registry["registry_version"],
            "1.7.0",
        )
        self.assertEqual(all_ids, executable | unavailable)
        self.assertFalse(executable & unavailable)
        self.assertEqual(len(all_ids), 58)
        self.assertEqual(len(executable), 26)
        self.assertEqual(len(unavailable), 32)

        unavailable_result = self.registry.execute(
            "DEFLATED_SHARPE_CONFIDENCE_V1",
            {},
        )
        self.assertEqual(unavailable_result.status, "FAIL")
        self.assertEqual(
            unavailable_result.reason_codes,
            ("ESTIMATOR_NOT_EXECUTABLE",),
        )

        unknown_result = self.registry.execute("NOT_IN_CATALOG_V1", {})
        self.assertEqual(unknown_result.status, "FAIL")
        self.assertEqual(unknown_result.reason_codes, ("UNKNOWN_ESTIMATOR",))

    def test_input_contract_and_decimal_boundaries_fail_closed(self):
        missing = self.registry.execute(
            "ACTUAL_DEPLOYABLE_CAPITAL_V1",
            {"snapshot_verified": True},
        )
        self.assertEqual(missing.status, "FAIL")
        self.assertEqual(
            missing.reason_codes,
            (
                "ESTIMATOR_INPUT_MISSING:"
                "actual_deployable_capital_usdt",
            ),
        )

        unexpected = self.registry.execute(
            "ACTUAL_DEPLOYABLE_CAPITAL_V1",
            {
                "actual_deployable_capital_usdt": "1",
                "snapshot_verified": True,
                "unapproved_input": "ignored-if-not-checked",
            },
        )
        self.assertEqual(unexpected.status, "FAIL")
        self.assertEqual(
            unexpected.reason_codes,
            ("ESTIMATOR_INPUT_UNEXPECTED:unapproved_input",),
        )

        for invalid in (-1, "-0.01", 0.1):
            with self.subTest(invalid=invalid):
                result = self.registry.execute(
                    "ACTUAL_DEPLOYABLE_CAPITAL_V1",
                    {
                        "actual_deployable_capital_usdt": invalid,
                        "snapshot_verified": True,
                    },
                )
                self.assertEqual(result.status, "FAIL")
                self.assertEqual(
                    result.reason_codes,
                    ("ACTUAL_DEPLOYABLE_CAPITAL_INVALID",),
                )

        exact_boundary = self.registry.execute(
            "DECIMAL_CAPITAL_COMPARISON_V1",
            {
                "actual_deployable_capital_usdt": "0.10000000000000000001",
                "approved_production_capital_usdt": "0.1",
                "break_even_capital_lcb_root_usdt": None,
                "comparison": "APPROVED",
                "scope_verified": True,
            },
        )
        self.assertEqual(exact_boundary.status, "COMPUTED")
        self.assertIs(exact_boundary.value, True)

    def test_complete_trade_replay_estimator_is_executable(self):
        source, snapshots, valuations = complete_trade_replay_inputs()
        replay = build_trade_replay_snapshot(
            replay_id="registry-trade-replay",
            source_series_snapshot=source,
            economic_snapshots=snapshots,
            valuation_checkpoints=valuations,
            generated_at=source["generated_at"],
        )

        self.assertTrue(
            self.registry.is_executable(
                "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1"
            )
        )
        execution = self.registry.execute(
            "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1",
            {"trade_replay_snapshot": replay},
        )
        self.assertEqual(execution.status, "COMPUTED")
        self.assertEqual(execution.value, "0")
        self.assertEqual(execution.reason_codes, ())

        missing = self.registry.execute(
            "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1",
            {},
        )
        self.assertEqual(
            missing.reason_codes,
            ("ESTIMATOR_INPUT_MISSING:trade_replay_snapshot",),
        )

        schema_invalid = deepcopy(replay)
        schema_invalid.pop("source_series_hash")
        rejected = self.registry.execute(
            "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1",
            {"trade_replay_snapshot": schema_invalid},
        )
        self.assertEqual(
            rejected.reason_codes,
            ("TRADE_REPLAY_SCHEMA_INVALID",),
        )

        semantic_tamper = deepcopy(replay)
        semantic_tamper["selected_trade_ids"] = []
        semantic_tamper["replay_hash"] = trade_replay_snapshot_hash(
            semantic_tamper
        )
        rejected = self.registry.execute(
            "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1",
            {"trade_replay_snapshot": semantic_tamper},
        )
        self.assertEqual(
            rejected.reason_codes,
            ("TRADE_REPLAY_SELECTION_MISMATCH",),
        )

    def test_statistical_decision_estimators_are_executable(self):
        snapshot = make_statistical_decision_snapshot()
        expected = {
            "ACHIEVED_POWER_AT_MERE_V1": "0.031",
            "PRIMARY_ENDPOINT_CI_WIDTH_V1": "20",
            "HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1": True,
        }

        for estimator_id, expected_value in expected.items():
            with self.subTest(estimator_id=estimator_id):
                self.assertTrue(self.registry.is_executable(estimator_id))
                execution = self.registry.execute(
                    estimator_id,
                    {"statistical_decision_snapshot": snapshot},
                )
                self.assertEqual(execution.status, "COMPUTED")
                self.assertEqual(execution.value, expected_value)
                self.assertEqual(execution.reason_codes, ())

        schema_invalid = deepcopy(snapshot)
        schema_invalid["uploaded_power_claim"] = "1"
        rejected = self.registry.execute(
            "ACHIEVED_POWER_AT_MERE_V1",
            {"statistical_decision_snapshot": schema_invalid},
        )
        self.assertEqual(
            rejected.reason_codes,
            ("STATISTICAL_DECISION_SCHEMA_INVALID",),
        )

        embedded_schema_invalid = deepcopy(snapshot)
        current = next(
            item
            for item in embedded_schema_invalid["trial_registry"]
            if item["candidate_id"]
            == embedded_schema_invalid["current_candidate_id"]
        )
        del current["source_series_snapshot"]["$schema"]
        current["source_series_snapshot"]["series_hash"] = (
            statistical_series_hash(current["source_series_snapshot"])
        )
        current["source_series_hash"] = current[
            "source_series_snapshot"
        ]["series_hash"]
        embedded_schema_invalid["snapshot_hash"] = (
            statistical_decision_snapshot_hash(embedded_schema_invalid)
        )
        rejected = self.registry.execute(
            "ACHIEVED_POWER_AT_MERE_V1",
            {
                "statistical_decision_snapshot": (
                    embedded_schema_invalid
                ),
            },
        )
        self.assertEqual(
            rejected.reason_codes,
            ("STATISTICAL_DECISION_SOURCE_SERIES_SCHEMA_INVALID",),
        )

    def test_golden_vectors_are_deterministic(self):
        reports = [self.registry.run_golden_vectors() for _ in range(100)]
        self.assertTrue(all(report.passed for report in reports))
        self.assertEqual({report.vector_count for report in reports}, {41})
        self.assertEqual(
            {report.report_hash for report in reports},
            {
                "e3e7dc45865d860489514a574c64ca14"
                "a8dd6f089a0b74129414231741882fc3"
            },
        )

    def test_registry_and_golden_bundle_tampering_is_rejected(self):
        cases = (
            ("estimator-registry-v1.json", "registry_version", "1.0.1"),
            (
                "estimator-golden-vectors-v1.json",
                "bundle_version",
                "1.0.1",
            ),
        )
        for filename, field, value in cases:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp) / "config"
                shutil.copytree(ROOT / "config", config)
                path = config / filename
                artifact = json.loads(path.read_text(encoding="utf-8"))
                artifact[field] = value
                path.write_text(
                    json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(PolicyError, "self hash mismatch"):
                    EstimatorRegistry.load(config, self.catalog)


class EvaluatorBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog = load_json_strict(
            ROOT / "config" / "release-metrics-v1.1.json"
        )
        cls.registry = EstimatorRegistry.load(ROOT / "config", catalog)

    def test_expected_file_paths_bind_market_data_resources_and_smoke(self):
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))

        self.assertIn(
            "config/historical-market-data-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/historical-market-data-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "artifacts/market-data/binance-public-data-smoke-v0.16.0.json",
            expected,
        )
        self.assertIn(
            "config/contemporaneous-capture-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/contemporaneous-capture-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "artifacts/market-data/binance-contemporaneous-smoke-v0.17.0.json",
            expected,
        )
        self.assertIn(
            "config/offline-paper-run-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/offline-paper-run-v1.schema.json",
            expected,
        )
        self.assertIn(
            "artifacts/paper/binance-offline-paper-smoke-v0.18.0.json",
            expected,
        )
        self.assertIn(
            "config/paper-schedule-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/paper-runtime-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/server-time-probe-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/perpetual-context-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/account-commission-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "account-commission-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "artifacts/account-cost/"
            "binance-account-commission-smoke-not-run-v0.22.0.json",
            expected,
        )
        self.assertIn(
            "config/paper-account-cost-binding-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "paper-account-cost-binding-v1.schema.json",
            expected,
        )
        self.assertIn(
            "artifacts/paper-cost/"
            "binance-paper-account-cost-binding-not-run-v0.23.0.json",
            expected,
        )
        self.assertIn(
            "config/paper-cycle-context-bundle-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/paper-context-schedule-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "paper-cycle-context-bundle-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "paper-context-schedule-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "artifacts/paper-context/"
            "binance-context-complete-cycle-not-run-v0.24.0.json",
            expected,
        )
        self.assertIn(
            "config/context-cycle-orchestration-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/local-scheduler-contract-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "context-cycle-orchestration-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "local-scheduler-contract-v1.schema.json",
            expected,
        )
        self.assertIn(
            "artifacts/orchestration/"
            "context-cycle-orchestration-not-run-v0.25.0.json",
            expected,
        )
        self.assertIn(
            "config/historical-research-corpus-plan-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/historical-research-corpus-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/historical-research-corpus-repair-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "historical-research-corpus-plan-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "historical-research-corpus-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "historical-research-corpus-repair-v1.schema.json",
            expected,
        )
        self.assertIn(
            "artifacts/research-corpus/"
            "binance-monthly-corpus-smoke-v0.26.0.json",
            expected,
        )
        self.assertIn(
            "artifacts/research-corpus/"
            "binance-research-corpus-completion-v0.27.0.json",
            expected,
        )
        self.assertIn(
            "artifacts/ai-research/"
            "binance-causal-logistic-research-v0.28.0.json",
            expected,
        )
        self.assertIn(
            "artifacts/baseline-research/"
            "binance-baseline-failure-attribution-v0.29.0.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "baseline-failure-attribution-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "historical-execution-source-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "causal-feature-label-dataset-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "logistic-archive-research-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/"
            "perpetual-context-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "artifacts/market-data/"
            "binance-perpetual-context-smoke-failure-v0.21.0.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/paper-schedule-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "artifacts/paper/paper-slot-ethusdt_20260727t120000z.json",
            expected,
        )
        self.assertIn(
            "artifacts/paper/paper-schedule-ethusdt_20260727t120000z.json",
            expected,
        )
        self.assertIn(
            "artifacts/runtime/v0.20-smoke/runtime/"
            "paper-runtime-runtime_event_827acba8afd454ae735cd0c0d157b76"
            "beb125466a243b30159e2ee7233283f2c.json",
            expected,
        )
        self.assertIn("setup.py", expected)
        self.assertIn(
            "src/crypto_quant/system_paper_scheduler.py",
            expected,
        )
        self.assertIn(
            "tests/test_system_paper_scheduler.py",
            expected,
        )
        self.assertIn(
            "tests/test_system_paper_fault_injection.py",
            expected,
        )
        self.assertIn(
            "docs/superpowers/specs/"
            "2026-08-02-system-paper-wal-scheduler-design.md",
            expected,
        )
        self.assertIn(
            "docs/superpowers/plans/"
            "2026-08-02-system-paper-wal-scheduler.md",
            expected,
        )

    def test_manifest_binds_complete_evaluator_file_set(self):
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        manifest = load_json_strict(
            ROOT / "config" / "evaluator-build-manifest-v1.json"
        )

        pyproject_match = re.search(
            r'^version = "([^"]+)"$',
            (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        self.assertIsNotNone(pyproject_match)
        setup_tree = ast.parse(
            (ROOT / "setup.py").read_text(encoding="utf-8")
        )
        setup_version = next(
            keyword.value.value
            for node in ast.walk(setup_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setup"
            for keyword in node.keywords
            if keyword.arg == "version"
            and isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, str)
        )
        semantic_versions = {
            tuple(int(part) for part in version.split("."))
            for version in (
                pyproject_match.group(1),
                setup_version,
                crypto_quant.__version__,
            )
        }

        self.assertEqual(set(manifest["file_hashes"]), expected)
        self.assertEqual(semantic_versions, {(0, 63, 0)})
        self.assertEqual(crypto_quant.__version__, "0.63.0")
        self.assertEqual(manifest["package_version"], "0.63.0")
        self.assertEqual(manifest["manifest_version"], "1.57.0")
        self.assertIn("src/crypto_quant/release.py", expected)
        self.assertIn("src/crypto_quant/estimators.py", expected)
        self.assertIn("config/release-gates-v1.1.json", expected)
        self.assertIn(
            "config/trade-replay-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/statistical-decision-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/paired-risk-evaluation-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-prequential-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-episode-archive-receipt-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-episode-economic-result-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-episode-economic-plan-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-forward-source-bundle-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-first-slot-receipt-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-first-episode-receipt-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-episode-cohort-plan-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-cohort-evaluation-plan-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-cohort-episode-economic-result-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-cohort-evidence-maintenance-"
            "launchd-contract-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-cohort-evidence-maintenance-"
            "deployment-manifest-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-cohort-evidence-maintenance-"
            "launchd-install-receipt-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-cohort-economic-result-index-v1.schema.json",
            expected,
        )
        for path in (
            "tests/test_estimators.py",
            "config/system-paper-market-bundle-v1.schema.json",
            "config/system-paper-launchd-contract-v1.schema.json",
            "config/system-paper-preflight-receipt-v1.schema.json",
            "config/system-paper-install-receipt-v1.schema.json",
            "config/system-paper-start-receipt-v1.schema.json",
            "src/crypto_quant/schemas/system-paper-market-bundle-v1.schema.json",
            "src/crypto_quant/schemas/system-paper-launchd-contract-v1.schema.json",
            "src/crypto_quant/schemas/system-paper-preflight-receipt-v1.schema.json",
            "src/crypto_quant/schemas/system-paper-install-receipt-v1.schema.json",
            "src/crypto_quant/schemas/system-paper-start-receipt-v1.schema.json",
            "tests/system_paper_fixtures.py",
            "tests/test_offline_paper.py",
            "tests/test_system_paper_public_input.py",
            "tests/test_system_paper_runtime.py",
            "tests/test_system_paper_runtime_cli.py",
            "tests/test_system_paper_launchd.py",
            "tests/test_system_paper_preflight.py",
            "tests/test_system_paper_install.py",
            "tests/test_system_paper_observer.py",
            "tests/test_system_paper_start_receipt.py",
            "src/crypto_quant/system_paper_evidence.py",
            "src/crypto_quant/system_paper_launchctl.py",
            "tests/test_system_paper_evidence.py",
            "tests/test_system_paper_launchctl.py",
            "tests/fixtures/launchctl/system-paper-not-running.txt",
            "tests/fixtures/launchctl/system-paper-first-success.txt",
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
            "config/system-paper-evaluation-v1.schema.json",
            "src/crypto_quant/system_paper_evaluation.py",
            "src/crypto_quant/system_paper_evaluation_cli.py",
            "src/crypto_quant/schemas/system-paper-evaluation-v1.schema.json",
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
            "config/operations-projection-v1.schema.json",
            "src/crypto_quant/operations_projection.py",
            "src/crypto_quant/schemas/operations-projection-v1.schema.json",
            "tests/test_operations_projection.py",
            "docs/superpowers/specs/"
            "2026-08-05-tail-blind-operations-projection-design.md",
            "docs/superpowers/plans/"
            "2026-08-05-tail-blind-operations-projection.md",
            "docs/adr/0060-tail-blind-operations-projection.md",
            "docs/implementation-status-v0.60.0.md",
            "src/crypto_quant/operations_alerts.py",
            "src/crypto_quant/operations_dashboard.py",
            "src/crypto_quant/dashboard/index.html",
            "src/crypto_quant/dashboard/app.js",
            "src/crypto_quant/dashboard/styles.css",
            "tests/fixtures/operations-projection-healthy.json",
            "tests/test_operations_alerts.py",
            "tests/test_operations_dashboard.py",
            "docs/superpowers/specs/"
            "2026-08-05-loopback-read-only-operations-console-design.md",
            "docs/superpowers/plans/"
            "2026-08-05-loopback-read-only-operations-console.md",
            "docs/runbooks/system-paper-operations.md",
            "docs/runbooks/operations-dashboard.md",
            "docs/adr/0061-loopback-read-only-operations-console.md",
            "docs/implementation-status-v0.61.0.md",
            "config/challenger-replacement-plan-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-plan-v1.schema.json",
            "src/crypto_quant/challenger_replacement_plan.py",
            "tests/test_challenger_replacement_plan.py",
            "artifacts/challenger-replacement/"
            "challenger-replacement-plan-v0.62.0.json",
            "docs/superpowers/specs/"
            "2026-08-05-replacement-challenger-preregistration-"
            "isolation-design.md",
            "docs/superpowers/plans/"
            "2026-08-05-replacement-challenger-preregistration-"
            "isolation.md",
            "docs/adr/0062-replacement-challenger-preregistration-"
            "isolation.md",
            "docs/implementation-status-v0.62.0.md",
            "config/nautilus-sandbox-dependency-lock-v1.schema.json",
            "config/nautilus-sandbox-comparison-v1.schema.json",
            "artifacts/nautilus-sandbox/"
            "nautilus-sandbox-dependency-lock-v0.63.0.json",
            "artifacts/nautilus-sandbox/"
            "nautilus-sandbox-comparison-v0.63.0.json",
            "sandboxes/nautilus/pyproject.toml",
            "sandboxes/nautilus/uv.lock",
            "sandboxes/nautilus/src/"
            "crypto_quant_nautilus_sandbox/__init__.py",
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
        ):
            self.assertIn(path, expected)
        self.assertIn(
            "artifacts/challenger-forward/"
            "challenger-episode-cohort-plan-v0.43.0.json",
            expected,
        )
        self.assertIn(
            "artifacts/challenger-forward/"
            "challenger-cohort-evaluation-plan-v0.44.0.json",
            expected,
        )
        self.assertIn(
            "artifacts/challenger-forward/"
            "challenger-cohort-evidence-maintenance-"
            "launchd-not-installed-v0.50.0.json",
            expected,
        )
        self.assertIn(
            "artifacts/challenger-forward/"
            "challenger-first-episode-in-progress-v0.36.0.json",
            expected,
        )
        self.assertIn(
            "artifacts/challenger-forward/"
            "challenger-episode-economic-plan-v0.37.0.json",
            expected,
        )
        self.assertIn(
            "artifacts/challenger-forward/"
            "challenger-first-slot-receipt-v0.35.0.json",
            expected,
        )
        self.assertIn(
            "artifacts/challenger-forward/"
            "challenger-cohort-evidence-maintenance-first-run-"
            "receipt-v0.53.0.json",
            expected,
        )
        self.assertIn(
            "artifacts/challenger-forward/"
            "challenger-cohort-missed-slot-failure-receipt-v0.54.0.json",
            expected,
        )
        self.assertIn(
            "artifacts/challenger-forward/"
            "challenger-cohort-decommission-receipt-v0.54.0.json",
            expected,
        )
        self.assertIn(
            "artifacts/system-paper/system-paper-plan-v0.55.0.json",
            expected,
        )
        self.assertIn(
            "config/system-paper-plan-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-cohort-failure-receipt-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-cohort-decommission-receipt-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-launchd-contract-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/challenger-launchd-install-receipt-v1.schema.json",
            expected,
        )
        self.assertIn(
            "config/historical-market-data-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "src/crypto_quant/schemas/historical-market-data-snapshot-v1.schema.json",
            expected,
        )
        self.assertIn(
            "artifacts/market-data/binance-public-data-smoke-v0.16.0.json",
            expected,
        )
        self.assertIn("src/crypto_quant/paired_risk.py", expected)
        self.assertIn("src/crypto_quant/statistical_decision.py", expected)
        self.assertEqual(manifest["manifest_version"], "1.57.0")
        self.assertEqual(manifest["package_version"], "0.63.0")
        self.assertEqual(crypto_quant.__version__, "0.63.0")
        self.assertEqual(
            manifest["file_set_policy"],
            "ALL_PACKAGE_CODE_RESOURCES_PLUS_FROZEN_RELEASE_INPUTS",
        )
        self.assertEqual(manifest["metric_catalog_version"], "1.1.6")
        self.assertEqual(manifest["golden_vector_count"], 41)
        build = EvaluatorBuild.load(ROOT, self.registry)
        self.assertEqual(build.manifest_version, "1.57.0")
        self.assertEqual(build.executable_estimator_count, 26)
        self.assertEqual(build.unavailable_estimator_count, 32)
        self.assertEqual(build.build_hash, manifest["manifest_hash"])

    def test_modified_evaluator_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp) / "workspace"
            shutil.copytree(
                ROOT,
                clone,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            release_path = clone / "src" / "crypto_quant" / "release.py"
            release_path.write_text(
                release_path.read_text(encoding="utf-8") + "\n# tampered\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                PolicyError,
                "EvaluatorBuild input hash mismatch",
            ):
                EvaluatorBuild.load(clone, self.registry)


if __name__ == "__main__":
    unittest.main()
