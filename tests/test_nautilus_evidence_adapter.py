import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.nautilus_evidence_adapter import (
    NautilusEvidenceAdapterError,
    build_nautilus_supply_chain_fetch_failure,
    compare_nautilus_sandbox,
)
from crypto_quant.nautilus_sandbox_contract import build_nautilus_current_reference
from crypto_quant.nautilus_sandbox_dependency import build_nautilus_sandbox_dependency_lock


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "nautilus-sandbox" / "ethusdt-4h-input-v1.json"
SCHEMA = ROOT / "config" / "nautilus-sandbox-comparison-v1.schema.json"
PACKAGE_SCHEMA = ROOT / "src" / "crypto_quant" / "schemas" / SCHEMA.name


class NautilusEvidenceAdapterTests(unittest.TestCase):
    def fixture(self):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def lock(self):
        return build_nautilus_sandbox_dependency_lock(workspace_root=ROOT)

    def reference(self):
        return build_nautilus_current_reference(fixture=self.fixture())

    def test_fetch_failure_is_exact_bounded_and_has_no_runtime_claim(self):
        failure = build_nautilus_supply_chain_fetch_failure()
        self.assertEqual(failure["reason_code"], "SUPPLY_CHAIN_FETCH_BLOCKED")
        self.assertEqual(failure["official_source"], "https://files.pythonhosted.org")
        self.assertEqual(failure["attempt_count"], 2)
        self.assertEqual(failure["source_change_count"], 0)
        self.assertEqual(failure["version_change_count"], 0)
        self.assertEqual(failure["hash_relaxation_count"], 0)
        self.assertEqual(failure["sandbox_runner_invocation_count"], 0)
        self.assertEqual(failure["production_state_write_count"], 0)
        self.assertEqual(failure["result_published"], False)
        self.assertEqual(
            [attempt["outcome"] for attempt in failure["attempts"]],
            ["UV_RETRIES_EXHAUSTED_TIMEOUT", "BOUNDED_RECOVERY_ABORTED_NO_PROGRESS"],
        )

    def test_adapter_emits_only_inconclusive_blocked_without_result(self):
        comparison = compare_nautilus_sandbox(
            dependency_lock=self.lock(),
            fixture=self.fixture(),
            current_reference=self.reference(),
            result=None,
            failure_evidence=build_nautilus_supply_chain_fetch_failure(),
        )
        self.assertEqual(comparison["conclusion"], "INCONCLUSIVE_BLOCKED")
        self.assertEqual(comparison["classification"], "SUPPLY_CHAIN_OR_LICENSE_FAILURE")
        self.assertEqual(comparison["reason_codes"], ["SUPPLY_CHAIN_FETCH_BLOCKED"])
        self.assertFalse(comparison["sandbox_result_available"])
        self.assertIsNone(comparison["sandbox_result_hash_or_null"])
        self.assertEqual(comparison["authority"], "READ_ONLY_EVIDENCE_ADAPTER")
        self.assertEqual(
            comparison["gates"],
            {
                "exact_dependency_metadata": True,
                "wheel_locally_verified": False,
                "license_bytes_locally_verified": False,
                "golden_scenarios_executed": False,
                "failure_suite_executed": True,
                "fresh_process_replay_verified": False,
                "safety_zero_counters_verified": True,
                "future_shadow_eligible": False,
            },
        )
        body = json.dumps(comparison, sort_keys=True).lower()
        for word in ("pnl", "profit", "return", "win_rate", "adopted"):
            self.assertNotIn(word, body)

    def test_adapter_rejects_tampered_or_result_mixed_failure(self):
        failure = build_nautilus_supply_chain_fetch_failure()
        changed = copy.deepcopy(failure)
        changed["attempt_count"] = 3
        with self.assertRaisesRegex(
            NautilusEvidenceAdapterError, "SUPPLY_CHAIN_FAILURE_EVIDENCE_MISMATCH"
        ):
            compare_nautilus_sandbox(
                dependency_lock=self.lock(), fixture=self.fixture(),
                current_reference=self.reference(), result=None,
                failure_evidence=changed,
            )
        with self.assertRaisesRegex(
            NautilusEvidenceAdapterError, "SANDBOX_RESULT_AND_FAILURE_CONFLICT"
        ):
            compare_nautilus_sandbox(
                dependency_lock=self.lock(), fixture=self.fixture(),
                current_reference=self.reference(), result={}, failure_evidence=failure,
            )

    def test_comparison_schema_is_strict_mirrored_and_valid(self):
        self.assertEqual(SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        comparison = compare_nautilus_sandbox(
            dependency_lock=self.lock(), fixture=self.fixture(),
            current_reference=self.reference(), result=None,
            failure_evidence=build_nautilus_supply_chain_fetch_failure(),
        )
        Draft202012Validator(schema).validate(comparison)


if __name__ == "__main__":
    unittest.main()
