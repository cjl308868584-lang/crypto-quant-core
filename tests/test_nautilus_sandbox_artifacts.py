import json
import unittest
from pathlib import Path

from crypto_quant.canonical import canonical_json
from crypto_quant.nautilus_evidence_adapter import (
    build_nautilus_supply_chain_fetch_failure,
    compare_nautilus_sandbox,
)
from crypto_quant.nautilus_sandbox_contract import (
    build_nautilus_current_reference,
    build_nautilus_sandbox_request,
)
from crypto_quant.nautilus_sandbox_dependency import build_nautilus_sandbox_dependency_lock


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts" / "nautilus-sandbox"
FIXTURE = ROOT / "tests" / "fixtures" / "nautilus-sandbox" / "ethusdt-4h-input-v1.json"


class NautilusSandboxArtifactTests(unittest.TestCase):
    def expected(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        dependency = build_nautilus_sandbox_dependency_lock(workspace_root=ROOT)
        reference = build_nautilus_current_reference(fixture=fixture)
        request = build_nautilus_sandbox_request(
            dependency_lock=dependency,
            fixture=fixture,
            current_reference=reference,
        )
        comparison = compare_nautilus_sandbox(
            dependency_lock=dependency,
            fixture=fixture,
            current_reference=reference,
            result=None,
            failure_evidence=build_nautilus_supply_chain_fetch_failure(),
        )
        return reference, request, comparison

    def test_committed_bytes_are_exact_parameterless_evidence(self):
        reference, request, comparison = self.expected()
        expected = {
            "nautilus-sandbox-current-reference-v0.63.0.json": reference,
            "nautilus-sandbox-request-v0.63.0.json": request,
            "nautilus-sandbox-comparison-v0.63.0.json": comparison,
        }
        for name, payload in expected.items():
            with self.subTest(name=name):
                self.assertEqual(
                    (ARTIFACT_ROOT / name).read_bytes(),
                    canonical_json(payload).encode("utf-8") + b"\n",
                )

    def test_blocked_spike_has_no_synthetic_result_or_runner(self):
        self.assertFalse(
            (ARTIFACT_ROOT / "nautilus-sandbox-result-v0.63.0.json").exists()
        )
        self.assertFalse(
            (
                ROOT
                / "sandboxes"
                / "nautilus"
                / "src"
                / "crypto_quant_nautilus_sandbox"
                / "runner.py"
            ).exists()
        )
        comparison = self.expected()[2]
        self.assertFalse(comparison["sandbox_result_available"])
        self.assertEqual(comparison["conclusion"], "INCONCLUSIVE_BLOCKED")
        self.assertEqual(comparison["current_core_effect"], "NONE_KEEP_CURRENT_CORE")


if __name__ == "__main__":
    unittest.main()
