import ast
import hashlib
import json
import unittest
from pathlib import Path

import crypto_quant
from crypto_quant.build import EvaluatorBuild
from tests.test_challenger_replacement_v072_artifacts import (
    MANIFEST_PATH,
    _validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs/implementation-status-v0.72.0.md"
MODULE_BASELINES = {
    "challenger_replacement_binance_lifecycle.py": 0,
    "challenger_replacement_fixture_simulation.py": 0,
    "challenger_replacement_binance_simulation_input.py": 385,
    "challenger_replacement_simulation.py": 517,
    "challenger_replacement_opportunity_evidence.py": 147,
    "challenger_replacement_opportunity_projection.py": 447,
    "challenger_replacement_opportunities.py": 296,
}


class V072ReleaseTests(unittest.TestCase):
    def test_versions_manifest_and_candidate_status_are_exact(self):
        self.assertRegex((ROOT / "pyproject.toml").read_text(), r'(?m)^version = "0\.77\.0"$')
        self.assertRegex((ROOT / "setup.py").read_text(), r'version="0\.77\.0"')
        manifest = json.loads((ROOT / "config/evaluator-build-manifest-v1.json").read_text())
        self.assertEqual(
            (crypto_quant.__version__, manifest["package_version"], manifest["manifest_version"]),
            ("0.77.0", "0.77.0", "1.71.0"),
        )
        status = STATUS.read_text()
        self.assertIn(
            "状态：`FIXTURE_LIFECYCLE_EVIDENCE_VERIFIED_NOT_OPERATIONAL`",
            status,
        )
        self.assertIn(
            "final local full suite：`1974_EXECUTED_5_SKIPPED_7_EXPECTED_STALE_MANIFEST_FAILURES_BEFORE_FINAL_REFRESH`",
            status,
        )
        self.assertIn("post-review focused/adjacent：`76_PASSED`", status)
        self.assertIn(
            "independent complete review：`CRITICAL_0_IMPORTANT_0_MINOR_0`",
            status,
        )
        self.assertIn("final manifest consumer regressions：`49_PASSED`", status)
        self.assertIn(
            "compileall、make validate、diff-check：`PASSED_WITH_EXPECTED_PRODUCTION_FAIL_CLOSED_POLICY_STATUS`",
            status,
        )
        self.assertIn("PR CI、main CI、annotated tag：`PENDING_REMOTE_RELEASE_GATES`", status)

    def test_expected_release_inventory_and_formal_manifest_are_bound(self):
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        required = {
            "config/challenger-replacement-opportunity-result-evidence-v2.schema.json",
            "config/challenger-replacement-binance-golden-fixture-manifest-v1.schema.json",
            "artifacts/challenger-replacement/challenger-replacement-binance-golden-fixture-manifest-v0.72.0.json",
            "src/crypto_quant/challenger_replacement_binance_lifecycle.py",
            "src/crypto_quant/challenger_replacement_fixture_simulation.py",
            "tests/test_challenger_replacement_v072_artifacts.py",
            "tests/test_challenger_replacement_v072_release.py",
            "docs/adr/0072-binance-lifecycle-evidence.md",
            "docs/implementation-status-v0.72.0.md",
        }
        self.assertEqual(required - expected, set())
        manifest = json.loads((ROOT / "config/evaluator-build-manifest-v1.json").read_text())
        self.assertEqual(set(manifest["file_hashes"]), expected)
        body = MANIFEST_PATH.read_bytes()
        self.assertEqual(
            body,
            json.dumps(_validate_manifest(json.loads(body)), sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        )

    def test_predecessor_artifacts_remain_exact(self):
        expected = {
            "artifacts/challenger-replacement/challenger-replacement-binance-simulation-contract-v0.71.0.json": "65a0af1cccee5ad60aeaa7b0266bb217fab680d866ea3191ca77d214a292d86f",
            "artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json": "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3",
            "artifacts/challenger-replacement/challenger-replacement-v3-owner-attestation-v0.69.0.json": "b1ec38575b2e4f2b93b9f4838aa04633f382b60aef65843e4812d9b5c799b9c7",
            "artifacts/challenger-replacement/challenger-replacement-plan-v3-supersession-v0.69.0.json": "1d4932712304a890c5ff0a393d9674c38e2459faa3954a957ac0439ea770a32d",
        }
        for relative, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)

    def test_seven_module_budget_and_zero_authority_are_frozen(self):
        module_root = ROOT / "src/crypto_quant"
        forbidden_imports = {
            "requests", "urllib", "httpx", "aiohttp", "websocket", "socket",
            "subprocess", "sqlite3", "binance", "ccxt", "keyring",
        }
        for name in MODULE_BASELINES:
            source = (module_root / name).read_text()
            imported = set()
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertTrue(forbidden_imports.isdisjoint(imported), (name, imported))
            for forbidden in ("api_key", "secret_key", "fault_injector", "production_root"):
                self.assertNotIn(forbidden, source)

    def test_docs_state_exact_non_authority_and_no_clock_claim(self):
        documents = [
            (ROOT / "docs/adr/0072-binance-lifecycle-evidence.md").read_text(),
            STATUS.read_text(),
        ]
        for document in documents:
            for text in (
                "production_activation=false", "runtime_install_authorized=false",
                "replacement_start_authorized=false", "real_orders_allowed=false",
                "fixture-only", "no seven-day timer started", "no 90-day timer started",
                "no install", "no account", "no credential", "no real order",
                "no funds", "no Paper completion", "no profitability claim",
            ):
                self.assertIn(text, document)
        readme = (ROOT / "README.md").read_text()
        self.assertIn("Binance Lifecycle Evidence v0.72.0", readme)
        self.assertIn("fixture-only", readme)
        self.assertIn("no install/start/account/credential/order/funds", readme)


if __name__ == "__main__":
    unittest.main()
