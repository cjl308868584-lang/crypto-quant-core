import ast
import hashlib
import json
import unittest
from pathlib import Path

import crypto_quant
from crypto_quant.build import EvaluatorBuild


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs/implementation-status-v0.71.0.md"
SIX_MODULES = (
    "src/crypto_quant/challenger_replacement_opportunities.py",
    "src/crypto_quant/challenger_replacement_opportunity_evidence.py",
    "src/crypto_quant/challenger_replacement_opportunity_projection.py",
    "src/crypto_quant/challenger_replacement_simulation_contract.py",
    "src/crypto_quant/challenger_replacement_binance_simulation_input.py",
    "src/crypto_quant/challenger_replacement_simulation.py",
)


class V071ReleaseTests(unittest.TestCase):
    def test_versions_manifest_and_candidate_status_are_exact(self):
        self.assertRegex((ROOT / "pyproject.toml").read_text(), r'(?m)^version = "0\.71\.0"$')
        self.assertRegex((ROOT / "setup.py").read_text(), r'version="0\.71\.0"')
        manifest = json.loads((ROOT / "config/evaluator-build-manifest-v1.json").read_text())
        self.assertEqual(
            (crypto_quant.__version__, manifest["package_version"], manifest["manifest_version"]),
            ("0.71.0", "0.71.0", "1.65.0"),
        )
        self.assertIn(
            "状态：`FIXTURE_ACCOUNTING_CORE_VERIFIED_LIFECYCLE_NOT_IMPLEMENTED`",
            STATUS.read_text(),
        )
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        required = {
            "artifacts/challenger-replacement/challenger-replacement-binance-simulation-contract-v0.71.0.json",
            "config/challenger-replacement-simulation-contract-v1.schema.json",
            "config/challenger-replacement-binance-simulation-input-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-simulation-contract-v1.schema.json",
            "src/crypto_quant/challenger_replacement_simulation_contract.py",
            "src/crypto_quant/challenger_replacement_binance_simulation_input.py",
            "src/crypto_quant/challenger_replacement_simulation.py",
            "docs/superpowers/specs/2026-08-24-v071-accounting-core-version-split-design.md",
            "docs/superpowers/plans/2026-08-24-v071-accounting-core-release.md",
            "docs/adr/0071-binance-accounting-core.md",
            "docs/implementation-status-v0.71.0.md",
            "tests/test_challenger_replacement_v071_artifacts.py",
            "tests/test_challenger_replacement_v071_release.py",
        }
        self.assertEqual(required - expected, set())
        self.assertEqual(set(manifest["file_hashes"]), expected)

    def test_contract_and_predecessor_artifacts_remain_exact(self):
        expected = {
            "artifacts/challenger-replacement/challenger-replacement-binance-simulation-contract-v0.71.0.json":
                "65a0af1cccee5ad60aeaa7b0266bb217fab680d866ea3191ca77d214a292d86f",
            "artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json":
                "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3",
            "artifacts/challenger-replacement/challenger-replacement-v3-owner-attestation-v0.69.0.json":
                "b1ec38575b2e4f2b93b9f4838aa04633f382b60aef65843e4812d9b5c799b9c7",
            "artifacts/challenger-replacement/challenger-replacement-plan-v3-supersession-v0.69.0.json":
                "1d4932712304a890c5ff0a393d9674c38e2459faa3954a957ac0439ea770a32d",
        }
        for relative, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)

    def test_accounting_core_budget_and_authority_boundary_are_frozen(self):
        counts = {path: len((ROOT / path).read_text().splitlines()) for path in SIX_MODULES}
        self.assertTrue(all(count <= 700 for count in counts.values()), counts)
        self.assertLessEqual(sum(counts.values()) - 843, 1200, counts)
        simulation = ROOT / "src/crypto_quant/challenger_replacement_simulation.py"
        imported = set()
        for node in ast.walk(ast.parse(simulation.read_text())):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue({"requests", "urllib", "httpx", "aiohttp", "websocket", "socket", "subprocess", "sqlite3"}.isdisjoint(imported))
        source = simulation.read_text()
        for forbidden in (
            "run_challenger_replacement_fixture_simulation_opportunity",
            "load_challenger_replacement_simulation_result_evidence_bytes",
            "fault_injector", "api_key", "production_activation",
        ):
            self.assertNotIn(forbidden, source)

    def test_docs_state_exact_non_authority_and_v072_deferral(self):
        documents = [
            (ROOT / "docs/adr/0071-binance-accounting-core.md").read_text(),
            STATUS.read_text(),
        ]
        for document in documents:
            for text in (
                "production_activation=false", "runtime_install_authorized=false",
                "replacement_start_authorized=false", "real_orders_allowed=false",
                "fixture-only", "no seven-day timer started", "no 90-day timer started",
                "v0.72", "lifecycle",
            ):
                self.assertIn(text, document)
        readme = (ROOT / "README.md").read_text()
        self.assertIn("Binance Accounting Core v0.71.0", readme)
        self.assertIn("lifecycle not implemented", readme)


if __name__ == "__main__":
    unittest.main()
