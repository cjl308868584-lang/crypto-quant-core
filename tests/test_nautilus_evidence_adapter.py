import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.nautilus_evidence_adapter import (
    NautilusEvidenceAdapterError,
    build_nautilus_supply_chain_fetch_attestation,
    compare_nautilus_sandbox,
)
from crypto_quant.nautilus_sandbox_dependency import build_nautilus_sandbox_dependency_lock


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "config" / "nautilus-sandbox-comparison-v1.schema.json"
PACKAGE_SCHEMA = ROOT / "src" / "crypto_quant" / "schemas" / SCHEMA.name


class NautilusEvidenceAdapterTests(unittest.TestCase):
    def lock(self):
        return build_nautilus_sandbox_dependency_lock(workspace_root=ROOT)

    def test_fetch_attestation_never_claims_machine_replayable_evidence(self):
        attestation = build_nautilus_supply_chain_fetch_attestation()
        self.assertEqual(attestation["reason_code"], "SUPPLY_CHAIN_FETCH_NOT_MACHINE_REPLAYABLE")
        self.assertEqual(attestation["attempt_count"], 2)
        self.assertFalse(attestation["exact_transcript_bytes_available"])
        self.assertFalse(attestation["external_attestation_available"])
        self.assertFalse(attestation["machine_replayable"])
        self.assertEqual(attestation["sandbox_runner_invocation_count"], 0)
        self.assertEqual(attestation["sandbox_engine_creation_count"], 0)
        self.assertEqual(attestation["production_state_write_count"], 0)

    def test_adapter_binds_full_exact_lock_and_stays_inconclusive(self):
        comparison = compare_nautilus_sandbox(
            dependency_lock=self.lock(),
            workspace_root=ROOT,
            failure_attestation=build_nautilus_supply_chain_fetch_attestation(),
        )
        self.assertEqual(comparison["conclusion"], "INCONCLUSIVE_BLOCKED")
        self.assertEqual(comparison["classification"], "SUPPLY_CHAIN_EVIDENCE_INCOMPLETE")
        self.assertEqual(
            comparison["reason_codes"],
            ["SUPPLY_CHAIN_FETCH_NOT_MACHINE_REPLAYABLE"],
        )
        self.assertEqual(comparison["authority"], "READ_ONLY_EVIDENCE_ADAPTER")
        self.assertEqual(
            comparison["gates"],
            {
                "exact_dependency_metadata": True,
                "wheel_locally_verified": False,
                "license_bytes_locally_verified": False,
                "compatibility_request_frozen": False,
                "sandbox_result_available": False,
                "golden_scenarios_executed": False,
                "runtime_failure_suite_executed": False,
                "static_blocked_path_tests_executed": True,
                "fresh_process_replay_verified": False,
                "future_shadow_eligible": False,
            },
        )

    def test_adapter_rejects_forged_lock_and_tampered_attestation(self):
        with self.assertRaisesRegex(
            NautilusEvidenceAdapterError, "DEPENDENCY_LOCK_EVIDENCE_INVALID"
        ):
            compare_nautilus_sandbox(
                dependency_lock={"dependency_lock_hash": "a" * 64},
                workspace_root=ROOT,
                failure_attestation=build_nautilus_supply_chain_fetch_attestation(),
            )
        changed = copy.deepcopy(build_nautilus_supply_chain_fetch_attestation())
        changed["attempt_count"] = 3
        with self.assertRaisesRegex(
            NautilusEvidenceAdapterError, "SUPPLY_CHAIN_ATTESTATION_MISMATCH"
        ):
            compare_nautilus_sandbox(
                dependency_lock=self.lock(),
                workspace_root=ROOT,
                failure_attestation=changed,
            )

    def test_comparison_schema_is_strict_mirrored_and_valid(self):
        self.assertEqual(SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(
            compare_nautilus_sandbox(
                dependency_lock=self.lock(),
                workspace_root=ROOT,
                failure_attestation=build_nautilus_supply_chain_fetch_attestation(),
            )
        )


if __name__ == "__main__":
    unittest.main()
