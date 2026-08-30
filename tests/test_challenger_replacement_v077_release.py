import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import crypto_quant
from crypto_quant.challenger_replacement_private_fault_matrix import (
    load_challenger_replacement_private_fault_matrix_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
FAULT_RECEIPT = ROOT / (
    "artifacts/challenger-replacement/"
    "challenger-replacement-private-fault-matrix-v0.77.0.json"
)
FOUNDATION_RECEIPT = ROOT / (
    "artifacts/challenger-replacement/"
    "challenger-replacement-fault-matrix-v0.76.0.json"
)
V076_DEPLOYMENT = ROOT / (
    "artifacts/challenger-replacement/"
    "challenger-replacement-v3-deployment-v0.76.0.json"
)
ADR = ROOT / "docs/adr/0077-binance-private-canary-bundle.md"
STATUS = ROOT / "docs/implementation-status-v0.77.0.md"
DOSSIER = ROOT / "docs/v1-code-complete-not-activated-dossier.md"
EXECUTABLE_CHECKPOINT = "bd8cb5dd43c469cb28bcfd0fe75d8d997625c1e7"
EXECUTABLE_TREE = "5fe797538ca3bd27ded323d6e5483685fb00caa9"
RECEIPT_SHA256 = "0223b124515dc4b1ce688e2681b31cc3f596be0575a09c91641584aaf8eba4f9"
V076_PEELED_COMMIT = "8ebcb07ab2c1ffe2b5f78e19626bfbdaba131867"
V076_TAG_OBJECT = "62d3611eb5c7b1bf197bc0f03d5d3871eaa23aff"
V076_TREE = "4d8e9acf8e68c037c8ad274d970bfe67c71d4766"
V076_MAIN_CI_RUN = "33132350975"

V077_PRIVATE_MODULES = (
    "challenger_replacement_binance_credential.py",
    "challenger_replacement_binance_preflight.py",
    "challenger_replacement_binance_private_contract.py",
    "challenger_replacement_binance_private_lifecycle.py",
    "challenger_replacement_binance_private_protocol.py",
    "challenger_replacement_binance_private_runtime.py",
    "challenger_replacement_binance_private_transport.py",
    "challenger_replacement_binance_reconciliation.py",
    "challenger_replacement_canary_controller.py",
    "challenger_replacement_private_fault_matrix.py",
)

V077_RELEASE_INPUTS = {
    "artifacts/challenger-replacement/challenger-replacement-private-fault-matrix-v0.77.0.json",
    "config/challenger-replacement-binance-v1.example.json",
    "config/local.crypto-quant.challenger-replacement-binance-v1.plist.example",
    "config/operations-projection-v3.schema.json",
    "docs/adr/0077-binance-private-canary-bundle.md",
    "docs/implementation-status-v0.77.0.md",
    "docs/v1-code-complete-not-activated-dossier.md",
    "docs/runbooks/binance-order-unknown-v0.77.md",
    "docs/runbooks/binance-private-preflight-v0.77.md",
    "docs/runbooks/binance-safe-flatten-v0.77.md",
    "docs/runbooks/binance-secret-incident-v0.77.md",
    "docs/superpowers/plans/2026-08-27-binance-private-canary-bundle.md",
    "docs/superpowers/specs/2026-08-27-binance-private-canary-budget-amendment-design.md",
    "docs/superpowers/specs/2026-08-27-binance-private-canary-bundle-design.md",
    "src/crypto_quant/fixtures/challenger-replacement-v077/account-preflight-flat.json",
    "src/crypto_quant/fixtures/challenger-replacement-v077/futures-request-known-answers.json",
    "src/crypto_quant/fixtures/challenger-replacement-v077/private-order-observations.json",
    "src/crypto_quant/fixtures/challenger-replacement-v077/private-runtime-seeds-v1.json",
    "src/crypto_quant/fixtures/challenger-replacement-v077/spot-hmac-known-answer.json",
    "tests/challenger_replacement_v077_private_fixtures.py",
    "tests/test_challenger_replacement_binance_credential.py",
    "tests/test_challenger_replacement_binance_delivery.py",
    "tests/test_challenger_replacement_binance_preflight.py",
    "tests/test_challenger_replacement_binance_private_contract.py",
    "tests/test_challenger_replacement_binance_private_lifecycle.py",
    "tests/test_challenger_replacement_binance_private_protocol.py",
    "tests/test_challenger_replacement_binance_private_runtime.py",
    "tests/test_challenger_replacement_binance_private_transport.py",
    "tests/test_challenger_replacement_binance_protective_stop.py",
    "tests/test_challenger_replacement_binance_reconciliation.py",
    "tests/test_challenger_replacement_canary_controller.py",
    "tests/test_challenger_replacement_events.py",
    "tests/test_challenger_replacement_opportunities.py",
    "tests/test_challenger_replacement_private_fault_matrix.py",
    "tests/test_challenger_replacement_public_market_capture.py",
    "tests/test_challenger_replacement_v077_architecture.py",
    "tests/test_challenger_replacement_v077_release.py",
}


class V077ReleaseMetadataTests(unittest.TestCase):
    def test_private_fixtures_are_present_in_wheel_and_sdist(self):
        members = {
            "crypto_quant/fixtures/challenger-replacement-v077/" + path.name
            for path in (ROOT / "src/crypto_quant/fixtures/challenger-replacement-v077").glob("*.json")
        }
        self.assertEqual(len(members), 5)
        with tempfile.TemporaryDirectory(prefix="cq-v077-package-") as directory:
            candidate = Path(directory) / "candidate"
            shutil.copytree(ROOT / "src", candidate / "src")
            for name in ("README.md", "pyproject.toml", "setup.py"):
                shutil.copy2(ROOT / name, candidate / name)
            dist = candidate / "dist"
            result = subprocess.run(
                [sys.executable, "setup.py", "--quiet", "sdist", "bdist_wheel",
                 "--dist-dir", str(dist)],
                cwd=candidate, capture_output=True, text=True,
                timeout=60, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(next(dist.glob("*.whl"))) as archive:
                self.assertEqual(members - set(archive.namelist()), set())
            with tarfile.open(next(dist.glob("*.tar.gz"))) as archive:
                archived = {name.split("/src/", 1)[-1]
                            for name in archive.getnames() if "/src/" in name}
                self.assertEqual(members - archived, set())

    def test_versions_manifest_and_release_inventory_are_exact(self):
        self.assertEqual(crypto_quant.__version__, "0.78.7")
        self.assertRegex((ROOT / "pyproject.toml").read_text(),
                         r'(?m)^version = "0\.78\.7"$')
        self.assertRegex((ROOT / "setup.py").read_text(), r'version="0\.78\.7"')
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text()
        )
        self.assertEqual(
            (manifest["package_version"], manifest["manifest_version"]),
            ("0.78.7", "1.79.0"),
        )
        from crypto_quant.build import EvaluatorBuild, _V077_RELEASE_PATHS
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        self.assertEqual(set(_V077_RELEASE_PATHS), V077_RELEASE_INPUTS)
        self.assertEqual(V077_RELEASE_INPUTS - expected, set())
        self.assertEqual(set(manifest["file_hashes"]), expected)

    def test_fault_receipt_replays_exact_historical_executable_checkpoint(self):
        receipt = FAULT_RECEIPT.read_bytes()
        historical = json.loads(receipt)
        self.assertEqual(hashlib.sha256(receipt).hexdigest(), RECEIPT_SHA256)
        with patch(
            "crypto_quant.challenger_replacement_private_fault_matrix._git_identity",
            return_value=(EXECUTABLE_CHECKPOINT, EXECUTABLE_TREE),
        ) as git_identity, patch(
            "crypto_quant.challenger_replacement_private_fault_matrix._inventory",
            return_value=(historical["executable_inventory"],
                          historical["executable_core_hash"]),
        ):
            loaded = load_challenger_replacement_private_fault_matrix_bytes(
                receipt,
                v076_fault_receipt_bytes=FOUNDATION_RECEIPT.read_bytes(),
                expected_executable_checkpoint=EXECUTABLE_CHECKPOINT,
                expected_executable_tree=EXECUTABLE_TREE,
                expected_receipt_sha256=RECEIPT_SHA256,
            )
        git_identity.assert_called_once_with(EXECUTABLE_CHECKPOINT, EXECUTABLE_TREE)
        self.assertEqual(loaded["status"], "PRIVATE_FAULT_MATRIX_PASSED_NOT_ACTIVATED")
        self.assertEqual(len(loaded["cases"]), 59)
        self.assertTrue(loaded["independent_replay"]["semantic_match"])
        self.assertEqual(set(loaded["authority"].values()), {0})
        self.assertEqual(set(loaded["independent_replay"]["authority"].values()), {0})

    def test_v076_annotated_release_binds_historical_core_blobs(self):
        def git(*arguments):
            return subprocess.run(
                ["git", *arguments], cwd=ROOT, check=True,
                capture_output=True,
            ).stdout

        self.assertEqual(git("cat-file", "-t", V076_TAG_OBJECT), b"tag\n")
        self.assertEqual(git("rev-parse", "v0.76.0"),
                         (V076_TAG_OBJECT + "\n").encode())
        self.assertEqual(git("rev-parse", "v0.76.0^{}"),
                         (V076_PEELED_COMMIT + "\n").encode())
        self.assertEqual(git("rev-parse", V076_PEELED_COMMIT + "^{tree}"),
                         (V076_TREE + "\n").encode())
        core = json.loads(V076_DEPLOYMENT.read_bytes())["executable_core_identity"]
        for path, expected_hash in core.items():
            with self.subTest(path=path):
                historical = git("show", V076_PEELED_COMMIT + ":" + path)
                self.assertEqual(hashlib.sha256(historical).hexdigest(), expected_hash)

    def test_release_documents_map_requirements_and_freeze_nonactivation(self):
        status, adr, dossier = STATUS.read_text(), ADR.read_text(), DOSSIER.read_text()
        shared_claims = (
            "CODE_COMPLETE_NOT_ACTIVATED",
            "production_activation=false",
            "no service installed or started",
            "no production root or start receipt created",
            "no real or production Binance credential created or read",
            "no private Binance request made",
            "no real order submitted",
            "no funds moved",
            "no 72-hour or 90-day timer started",
            "no profitability or AI-advantage conclusion",
            RECEIPT_SHA256,
            EXECUTABLE_CHECKPOINT,
            V076_PEELED_COMMIT,
            V076_TAG_OBJECT,
            V076_MAIN_CI_RUN,
        )
        for document in (status, adr, dossier):
            with self.subTest(document=document[:40]):
                for claim in shared_claims:
                    self.assertIn(claim, document)
        normalized_dossier = dossier.casefold()
        for requirement in (
            "architecture and threat model",
            "dependency, license and endpoint inventory",
            "fault, restart, reconciliation and secret-absence evidence",
            "read-only console acceptance",
            "known limitations and residual risks",
            "installation", "start", "credential", "IP/account binding",
            "configuration", "funding", "Spot ceremony", "Futures ceremony",
            "E0", "E1", "E2", "incident unlock",
            "v0.75", "v0.76", "v0.77",
        ):
            self.assertIn(requirement.casefold(), normalized_dossier)
        for path in (
            "src/crypto_quant/challenger_replacement_binance_private_runtime.py",
            "src/crypto_quant/challenger_replacement_canary_controller.py",
            "tests/test_challenger_replacement_private_fault_matrix.py",
            "artifacts/challenger-replacement/challenger-replacement-private-fault-matrix-v0.77.0.json",
            "config/evaluator-build-manifest-v1.json",
        ):
            self.assertIn(path, dossier)

    def test_private_release_has_only_frozen_dependencies_and_no_activation_default(self):
        forbidden_imports = {"requests", "aiohttp", "websockets", "ccxt", "binance"}
        source_root = ROOT / "src/crypto_quant"
        for name in V077_PRIVATE_MODULES:
            tree = ast.parse((source_root / name).read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertEqual(imported & forbidden_imports, set(), name)
        configuration = json.loads(
            (ROOT / "config/challenger-replacement-binance-v1.example.json").read_text()
        )
        self.assertIs(configuration["production_activation"], False)
        self.assertIs(configuration["runtime_install_authorized"], False)
        self.assertIs(configuration["replacement_start_authorized"], False)
        self.assertIs(configuration["credentials_allowed"], False)
        self.assertIs(configuration["account_requests_allowed"], False)
        self.assertIs(configuration["real_orders_allowed"], False)
        self.assertIs(configuration["fund_movement_allowed"], False)


if __name__ == "__main__":
    unittest.main()
