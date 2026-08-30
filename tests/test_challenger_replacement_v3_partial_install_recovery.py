import copy
import json
from pathlib import Path
import unittest

from crypto_quant.canonical import canonical_json


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = (
    ROOT / "config/challenger-replacement-v3-partial-install-recovery-v0.78.7.json"
)
SCHEMA_PATH = (
    ROOT / "src/crypto_quant/schemas/"
    "challenger-replacement-v3-partial-install-recovery-plan-v1.schema.json"
)


class PartialInstallRecoveryPlanTests(unittest.TestCase):
    def test_frozen_plan_strictly_binds_incident_and_release_foundation(self):
        self.assertTrue(PLAN_PATH.is_file(), "v0.78.7 recovery plan is missing")
        self.assertTrue(SCHEMA_PATH.is_file(), "v0.78.7 recovery schema is missing")
        from crypto_quant import challenger_replacement_v3_partial_install_recovery as module

        body = PLAN_PATH.read_bytes()
        plan = module.load_fixed_v3_partial_install_recovery_plan_bytes(body)
        self.assertEqual(body, canonical_json(plan).encode("utf-8"))
        self.assertEqual(
            plan["foundation"],
            {
                "manifest_file_sha256": "f06bbfa5dba81cd9f713c4d6b51bbd403d67439b063fdfe1f5b7fe49ae0f5cea",
                "manifest_hash": "808c2fd2aefbfc363725f0cf2a46a74cfc56a538e284dce6fd62042d475ea477",
                "manifest_version": "1.78.0",
                "package_version": "0.78.6",
                "peeled_commit": "faf6e03632c21dba0894f0a1248f308306b13737",
                "release_tag": "v0.78.6",
                "repository": "cjl308868584-lang/crypto-quant-core",
                "tag_object": "bc78d140129a23b38d3c72c1f4a93d8df568275e",
                "visibility": "PUBLIC",
            },
        )
        self.assertEqual(
            plan["preserved_files"]["target_plist"]["sha256"],
            "30efabbd76ab5af9c277213b3377612b5119a7889c6b8165748dbcc36acd329b",
        )
        self.assertEqual(
            plan["preserved_files"]["failed_install_receipt"]["sha256"],
            "97747c0ebd2f49c3afe875e9a1f99d541d98e363ac457e767a622586f8523198",
        )
        self.assertEqual(
            plan["preserved_files"]["preflight_receipt"]["sha256"],
            "3440beab833c998a3d0c250e60fd2f6876f4aa206c0e5c609a772d4333a59ce5",
        )
        self.assertEqual(
            plan["snapshot"]["tree_hash"],
            "b5ac484d5b7b8e61d36c33b7cc686fda23a79524734167158123720b2c14cfbe",
        )
        self.assertEqual(
            (plan["snapshot"]["file_count"], plan["snapshot"]["total_size_bytes"]),
            (101, 3248480),
        )
        self.assertEqual(
            plan["candidate"]["target_plist"],
            "/Users/chenm4/Library/LaunchAgents/"
            "local.crypto-quant.challenger-replacement-v1-v0.78.7.plist",
        )
        self.assertEqual(plan["candidate"]["release_tag"], "v0.78.7")
        self.assertEqual(plan["required_state"]["automation_status"], "PAUSED")
        self.assertEqual(
            plan["required_state"]["service_labels"],
            [
                "local.crypto-quant.challenger-forward",
                "local.crypto-quant.challenger-replacement-v1",
            ],
        )
        self.assertEqual(
            plan["empty_directories"]["state_parent"]["entry_names"],
            ["challenger-replacement-events-v1"],
        )
        for name in ("event_root", "start_receipt_root", "log_root"):
            self.assertEqual(plan["empty_directories"][name]["entry_names"], [])
        for record in list(plan["preserved_files"].values()) + list(
            plan["empty_directories"].values()
        ) + [plan["snapshot"]["root_record"]]:
            for name in ("device", "inode", "mtime_ns", "ctime_ns"):
                self.assertRegex(record[name], r"^(0|[1-9][0-9]*)$")

    def test_plan_loader_rejects_noncanonical_extra_and_tampered_bytes(self):
        self.assertTrue(PLAN_PATH.is_file(), "v0.78.7 recovery plan is missing")
        from crypto_quant import challenger_replacement_v3_partial_install_recovery as module

        body = PLAN_PATH.read_bytes()
        plan = json.loads(body)
        cases = []
        extra = copy.deepcopy(plan)
        extra["unexpected"] = True
        cases.append(canonical_json(extra).encode("utf-8"))
        changed = copy.deepcopy(plan)
        changed["preserved_files"]["target_plist"]["sha256"] = "0" * 64
        cases.append(canonical_json(changed).encode("utf-8"))
        cases.append(body + b"\n")
        for candidate in cases:
            with self.subTest(candidate=candidate[-16:]):
                with self.assertRaisesRegex(
                    ValueError, "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_PLAN_INVALID"
                ):
                    module.load_fixed_v3_partial_install_recovery_plan_bytes(candidate)

    def test_fixed_plan_loader_returns_exact_published_bytes(self):
        self.assertTrue(PLAN_PATH.is_file(), "v0.78.7 recovery plan is missing")
        from crypto_quant import challenger_replacement_v3_partial_install_recovery as module

        value, body = module.load_fixed_v3_partial_install_recovery_plan()
        self.assertEqual(body, PLAN_PATH.read_bytes())
        self.assertEqual(value, json.loads(body))


if __name__ == "__main__":
    unittest.main()
