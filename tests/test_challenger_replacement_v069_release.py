import ast
import hashlib
import json
import unittest
from pathlib import Path

import crypto_quant
from crypto_quant.build import EvaluatorBuild
from crypto_quant.challenger_replacement_plan_v3 import (
    load_challenger_replacement_plan_v3,
)
from crypto_quant.challenger_replacement_plan_v3_supersession import (
    ACCOUNTABLE_OWNER_DECLARATION_V3,
    build_challenger_replacement_v3_supersession_record,
    load_challenger_replacement_v3_machine_evidence,
    load_challenger_replacement_v3_owner_attestation,
    load_challenger_replacement_v3_supersession_record,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts" / "challenger-replacement"
PLAN_PATH = ARTIFACT_ROOT / "challenger-replacement-plan-v0.69.0.json"
MACHINE_PATH = ARTIFACT_ROOT / (
    "challenger-replacement-v3-supersession-machine-evidence-v0.69.0.json"
)
ATTESTATION_PATH = ARTIFACT_ROOT / (
    "challenger-replacement-v3-owner-attestation-v0.69.0.json"
)
RECORD_PATH = ARTIFACT_ROOT / (
    "challenger-replacement-plan-v3-supersession-v0.69.0.json"
)


class V069ReleaseTests(unittest.TestCase):
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
            (
                crypto_quant.__version__,
                manifest["package_version"],
                manifest["manifest_version"],
            ),
            ("0.76.0", "0.76.0", "1.70.0"),
        )
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        required = {
            "config/challenger-replacement-plan-v3.schema.json",
            "config/challenger-replacement-v3-supersession-machine-evidence-v1.schema.json",
            "config/challenger-replacement-v3-owner-attestation-v1.schema.json",
            "config/challenger-replacement-plan-v3-supersession-v1.schema.json",
            "artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json",
            "artifacts/challenger-replacement/challenger-replacement-v3-supersession-machine-evidence-v0.69.0.json",
            "artifacts/challenger-replacement/challenger-replacement-v3-owner-attestation-v0.69.0.json",
            "artifacts/challenger-replacement/challenger-replacement-plan-v3-supersession-v0.69.0.json",
            "tests/test_challenger_replacement_plan_v3.py",
            "tests/test_challenger_replacement_plan_v3_supersession.py",
            "tests/test_challenger_replacement_v069_release.py",
            "docs/superpowers/specs/2026-08-23-decision-opportunity-binance-canary-governance-design.md",
            "docs/superpowers/plans/2026-08-23-decision-opportunity-binance-canary-governance.md",
            "docs/adr/0069-decision-opportunity-binance-canary-preregistration.md",
            "docs/implementation-status-v0.69.0.md",
        }
        self.assertEqual(required - expected, set())
        self.assertEqual(set(manifest["file_hashes"]), expected)

    def test_four_formal_artifacts_replay_and_bind_exact_bytes(self):
        expected_sha256 = {
            PLAN_PATH: "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3",
            MACHINE_PATH: "170dcf26bffdf36149997ed9ceb7d8553735e53daef4e189f90974468662fae1",
            ATTESTATION_PATH: "b1ec38575b2e4f2b93b9f4838aa04633f382b60aef65843e4812d9b5c799b9c7",
            RECORD_PATH: "1d4932712304a890c5ff0a393d9674c38e2459faa3954a957ac0439ea770a32d",
        }
        for path, digest in expected_sha256.items():
            with self.subTest(path=path.name):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

        plan = load_challenger_replacement_plan_v3(PLAN_PATH)
        machine = load_challenger_replacement_v3_machine_evidence(MACHINE_PATH)
        attestation = load_challenger_replacement_v3_owner_attestation(
            ATTESTATION_PATH
        )
        record = load_challenger_replacement_v3_supersession_record(RECORD_PATH)
        self.assertEqual(
            record,
            build_challenger_replacement_v3_supersession_record(
                plan, machine, attestation
            ),
        )
        self.assertEqual(attestation["declaration"], ACCOUNTABLE_OWNER_DECLARATION_V3)
        self.assertEqual(
            attestation["owner_acknowledgement"],
            "I_SIGN_AND_ACCEPT_ACCOUNTABILITY_FOR_THE_EXACT_V3_DECLARATION",
        )
        self.assertEqual(
            machine["current_observation"]["observation"],
            "NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION",
        )
        self.assertEqual(set(machine["collector_authority"].values()), {0})

    def test_release_docs_preserve_plan_only_nonactivation_boundary(self):
        documents = [
            (ROOT / path).read_text()
            for path in (
                "docs/adr/0069-decision-opportunity-binance-canary-preregistration.md",
                "docs/implementation-status-v0.69.0.md",
            )
        ]
        for document in documents:
            for text in (
                "PLAN_FROZEN_REPLACEMENT_V3_NOT_STARTED",
                "production_activation=false",
                "runtime_install_authorized=false",
                "replacement_start_authorized=false",
                "real_orders_allowed=false",
                "no seven-day timer started",
                "no 90-day timer started",
            ):
                self.assertIn(text, document)
        readme = (ROOT / "README.md").read_text()
        self.assertIn("Decision Opportunity Governance v0.69.0", readme)
        self.assertIn("PLAN_FROZEN_REPLACEMENT_V3_NOT_STARTED", readme)

    def test_plan_freezes_dual_track_canary_and_disabled_authority(self):
        plan = load_challenger_replacement_plan_v3(PLAN_PATH)
        self.assertEqual(plan["opportunity_policy"]["cadence_seconds"], 14400)
        self.assertEqual(
            plan["opportunity_policy"]["terminal_outcomes"],
            ["OBSERVED", "MISSED"],
        )
        self.assertEqual(
            plan["operational_qualification"]["minimum_calendar_days"],
            7,
        )
        self.assertEqual(
            plan["economic_evidence"]["minimum_calendar_days"],
            90,
        )
        self.assertEqual(set(plan["authority"].values()), {False})
        self.assertEqual(
            plan["product_policy"]["venue"],
            "BINANCE_ONLY",
        )

    def test_predecessor_artifacts_remain_exact(self):
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

    def test_v069_modules_have_no_runtime_network_or_order_authority(self):
        paths = (
            ROOT / "src/crypto_quant/challenger_replacement_plan_v3.py",
            ROOT / "src/crypto_quant/challenger_replacement_plan_v3_supersession.py",
            ROOT / "src/crypto_quant/challenger_replacement_plan_v3_supersession_cli.py",
        )
        imported = set()
        for path in paths:
            tree = ast.parse(path.read_text())
            imported.update(
                alias.name.split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            )
        self.assertTrue(
            {
                "socket",
                "urllib",
                "requests",
                "binance",
                "sqlite3",
                "execution",
                "broker",
            }.isdisjoint(imported)
        )
        self.assertFalse(
            any(ARTIFACT_ROOT.glob("*install*receipt*v0.69.0.json"))
        )
        self.assertFalse(
            any(ARTIFACT_ROOT.glob("*start*receipt*v0.69.0.json"))
        )


if __name__ == "__main__":
    unittest.main()
