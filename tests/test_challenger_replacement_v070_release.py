import ast
import hashlib
import json
import unittest
from pathlib import Path

import crypto_quant
from crypto_quant.build import EvaluatorBuild


ROOT = Path(__file__).resolve().parents[1]


class V070ReleaseTests(unittest.TestCase):
    def test_versions_and_manifest_inventory_are_frozen(self):
        self.assertRegex(
            (ROOT / "pyproject.toml").read_text(),
            r'(?m)^version = "0\.78\.3"$',
        )
        self.assertRegex(
            (ROOT / "setup.py").read_text(), r'version="0\.78\.3"'
        )
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text()
        )
        self.assertEqual(
            (
                crypto_quant.__version__,
                manifest["package_version"],
                manifest["manifest_version"],
            ),
            ("0.78.3", "0.78.3", "1.75.0"),
        )
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        required = {
            "config/challenger-replacement-opportunity-result-evidence-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-opportunity-result-evidence-v1.schema.json",
            "src/crypto_quant/challenger_replacement_opportunity_evidence.py",
            "src/crypto_quant/challenger_replacement_opportunities.py",
            "tests/challenger_replacement_v3_fixtures.py",
            "tests/test_challenger_replacement_opportunity_evidence.py",
            "tests/test_challenger_replacement_opportunities.py",
            "tests/test_challenger_replacement_v070_release.py",
            "docs/superpowers/specs/2026-08-24-decision-opportunity-event-runtime-design.md",
            "docs/superpowers/plans/2026-08-24-decision-opportunity-event-runtime.md",
            "docs/adr/0070-decision-opportunity-event-runtime.md",
            "docs/implementation-status-v0.71.0.md",
        }
        self.assertEqual(required - expected, set())
        self.assertEqual(set(manifest["file_hashes"]), expected)

    def test_predecessor_artifacts_remain_exact(self):
        expected = {
            "artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json":
                "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3",
            "artifacts/challenger-replacement/challenger-replacement-v3-owner-attestation-v0.69.0.json":
                "b1ec38575b2e4f2b93b9f4838aa04633f382b60aef65843e4812d9b5c799b9c7",
            "artifacts/challenger-replacement/challenger-replacement-plan-v3-supersession-v0.69.0.json":
                "1d4932712304a890c5ff0a393d9674c38e2459faa3954a957ac0439ea770a32d",
        }
        for relative, digest in expected.items():
            with self.subTest(relative=relative):
                self.assertEqual(
                    hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
                    digest,
                )

    def test_runtime_modules_have_no_forbidden_authority_imports(self):
        modules = (
            ROOT / "src/crypto_quant/challenger_replacement_opportunities.py",
            ROOT / "src/crypto_quant/challenger_replacement_opportunity_evidence.py",
        )
        imported = set()
        for path in modules:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
        self.assertTrue({"requests", "urllib", "httpx", "aiohttp", "websocket",
                         "socket", "subprocess", "sqlite3"}.isdisjoint(imported))

    def test_projection_has_no_economic_or_activation_vocabulary(self):
        source = (
            ROOT / "src/crypto_quant/challenger_replacement_opportunities.py"
        ).read_text().lower()
        for forbidden in (
            "pnl", "profit", "return_rate", "win_rate", "api_key",
            "real_order", "production_activation", "launchagent",
        ):
            self.assertNotIn(forbidden, source)
        self.assertLessEqual(len(source.splitlines()), 700)

    def test_release_docs_preserve_fixture_only_nonactivation_boundary(self):
        documents = [
            (ROOT / path).read_text()
            for path in (
                "docs/adr/0070-decision-opportunity-event-runtime.md",
                "docs/implementation-status-v0.71.0.md",
            )
        ]
        for document in documents:
            for text in (
                "production_activation=false",
                "runtime_install_authorized=false",
                "replacement_start_authorized=false",
                "real_orders_allowed=false",
                "fixture-only",
                "no seven-day timer started",
                "no 90-day timer started",
            ):
                self.assertIn(text, document)
        readme = (ROOT / "README.md").read_text()
        self.assertIn("DecisionOpportunity Event Runtime v0.70.0", readme)
        self.assertIn("fixture-only", readme)


if __name__ == "__main__":
    unittest.main()
