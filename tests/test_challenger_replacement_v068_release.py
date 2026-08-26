import hashlib
import json
import unittest
from pathlib import Path

import crypto_quant
from crypto_quant.build import EvaluatorBuild

ROOT = Path(__file__).resolve().parents[1]


class V068ReleaseTests(unittest.TestCase):
    def test_versions_manifest_and_exact_candidate_inventory_are_frozen(self):
        self.assertRegex(
            (ROOT / "pyproject.toml").read_text(),
            r'(?m)^version = "0\.76\.0"$',
        )
        self.assertRegex(
            (ROOT / "setup.py").read_text(), r'version="0\.76\.0"'
        )
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text()
        )
        self.assertEqual(
            (crypto_quant.__version__, manifest["package_version"],
             manifest["manifest_version"]),
            ("0.76.0", "0.76.0", "1.70.0"),
        )
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        required = {
            "config/challenger-replacement-install-contract-v1.schema.json",
            "config/challenger-replacement-install-preflight-v1.schema.json",
            "config/challenger-replacement-install-receipt-v1.schema.json",
            "config/challenger-replacement-start-receipt-v1.schema.json",
            "src/crypto_quant/challenger_replacement_install_trust.py",
            "src/crypto_quant/challenger_replacement_install_preflight.py",
            "src/crypto_quant/challenger_replacement_install.py",
            "src/crypto_quant/challenger_replacement_installed_runtime.py",
            "src/crypto_quant/challenger_replacement_start.py",
            "tests/test_challenger_replacement_v068_release.py",
            "docs/adr/0068-replacement-install-observer-start-trust-chain.md",
            "docs/implementation-status-v0.68.0.md",
        }
        self.assertEqual(required - expected, set())
        self.assertEqual(set(manifest["file_hashes"]), expected)

    def test_release_docs_preserve_code_only_nonactivation_boundary(self):
        documents = [(ROOT / path).read_text() for path in (
            "docs/adr/0068-replacement-install-observer-start-trust-chain.md",
            "docs/implementation-status-v0.68.0.md",
        )]
        for document in documents:
            for text in (
                "REPLACEMENT_INSTALL_TRUST_CHAIN_CODE_RELEASED_NOT_INSTALLED",
                "production_activation=false", "runtime_install_authorized=true",
                "replacement_start_authorized=false", "real_orders_allowed=false",
                "no 90-day timer started",
            ):
                self.assertIn(text, document)
        readme = (ROOT / "README.md").read_text()
        self.assertIn("Replacement Install Trust Chain v0.68.0", readme)
        self.assertIn("REPLACEMENT_INSTALL_TRUST_CHAIN_CODE_RELEASED_NOT_INSTALLED", readme)

    def test_predecessor_plan_and_deployment_bytes_remain_exact(self):
        expected = {
            "artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json":
                "5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f",
            "artifacts/challenger-replacement/challenger-replacement-deployment-v0.67.0.json":
                "8e7e073e2bb23d1509884f53d19fac299d96f38e15f9773e3a0b7d0ff103bea0",
        }
        for name, digest in expected.items():
            self.assertEqual(
                hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest
            )

    def test_design_and_plan_are_committed_without_production_artifacts(self):
        self.assertTrue((ROOT / "docs/superpowers/specs/2026-08-22-replacement-install-observer-start-design.md").is_file())
        self.assertTrue((ROOT / "docs/superpowers/plans/2026-08-22-replacement-install-observer-start.md").is_file())
        artifact_names = {path.name for path in
                          (ROOT / "artifacts/challenger-replacement").glob("*v0.68.0.json")}
        self.assertEqual(artifact_names, set())

    def test_preflight_modules_keep_static_authority_and_line_gates(self):
        paths = [
            ROOT / "src/crypto_quant/challenger_replacement_install_preflight.py",
            ROOT / "src/crypto_quant/challenger_replacement_install_preflight_cli.py",
        ]
        text = "\n".join(path.read_text() for path in paths)
        self.assertNotIn("shell=True", text)
        self.assertNotIn("fault_injector", text)
        self.assertNotIn("kickstart", text)
        self.assertNotIn("import Broker", text)
        self.assertNotIn("import Order", text)
        self.assertLessEqual(sum(len(path.read_text().splitlines()) for path in paths), 345)

    def test_installer_has_one_bootstrap_and_no_forbidden_mutation_surface(self):
        paths = [
            ROOT / "src/crypto_quant/challenger_replacement_install.py",
            ROOT / "src/crypto_quant/challenger_replacement_install_cli.py",
        ]
        text = "\n".join(path.read_text() for path in paths)
        self.assertEqual(text.count('"bootstrap"'), 3)
        for forbidden in ('"kickstart"', '"bootout"', '"enable"',
                          '"submit"', "shell=True", "live_runtime_cli"):
            self.assertNotIn(forbidden, text)
        self.assertLessEqual(sum(len(path.read_text().splitlines()) for path in paths), 415)

    def test_trust_and_shared_plist_renderer_keep_reallocated_yagni_gate(self):
        import ast

        trust_paths = [
            ROOT / "src/crypto_quant/challenger_replacement_install_trust.py",
            ROOT / "src/crypto_quant/challenger_replacement_install_trust_cli.py",
        ]
        self.assertLessEqual(
            sum(len(path.read_text().splitlines()) for path in trust_paths), 1700
        )
        deployment = ROOT / "src/crypto_quant/challenger_replacement_deployment.py"
        tree = ast.parse(deployment.read_text())
        renderer = next(node for node in tree.body if getattr(node, "name", "")
                        == "render_challenger_replacement_install_plist")
        self.assertLessEqual(renderer.end_lineno - renderer.lineno + 1, 20)

    def test_installed_adapter_is_bounded_and_has_no_generic_authority(self):
        paths = [
            ROOT / "src/crypto_quant/challenger_replacement_installed_runtime.py",
            ROOT / "src/crypto_quant/challenger_replacement_installed_runtime_cli.py",
        ]
        text = "\n".join(path.read_text() for path in paths)
        for forbidden in (
            "sqlite3", "fault_injector", "shell=True", "kickstart",
            "bootstrap", "Broker", "Order", "api_key", "secret_key",
        ):
            self.assertNotIn(forbidden, text)
        self.assertLessEqual(
            sum(len(path.read_text().splitlines()) for path in paths), 300
        )

    def test_observer_start_and_global_trust_chain_keep_yagni_gate(self):
        groups = [
            [ROOT / "src/crypto_quant/challenger_replacement_install_trust.py",
             ROOT / "src/crypto_quant/challenger_replacement_install_trust_cli.py"],
            [ROOT / "src/crypto_quant/challenger_replacement_install_preflight.py",
             ROOT / "src/crypto_quant/challenger_replacement_install_preflight_cli.py"],
            [ROOT / "src/crypto_quant/challenger_replacement_install.py",
             ROOT / "src/crypto_quant/challenger_replacement_install_cli.py"],
            [ROOT / "src/crypto_quant/challenger_replacement_installed_runtime.py",
             ROOT / "src/crypto_quant/challenger_replacement_installed_runtime_cli.py"],
            [ROOT / "src/crypto_quant/challenger_replacement_start.py",
             ROOT / "src/crypto_quant/challenger_replacement_start_cli.py"],
        ]
        start_text = "\n".join(path.read_text() for path in groups[-1])
        for forbidden in (
            "sqlite3", "fault_injector", "shell=True", "kickstart",
            "bootstrap", "Broker", "Order", "api_key", "secret_key",
        ):
            self.assertNotIn(forbidden, start_text)
        counts = [sum(len(path.read_text().splitlines()) for path in group)
                  for group in groups]
        self.assertLessEqual(counts[-1], 880)
        self.assertLess(sum(counts), 3620)


if __name__ == "__main__":
    unittest.main()
