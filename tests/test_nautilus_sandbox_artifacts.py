import unittest
from pathlib import Path

from crypto_quant.canonical import canonical_json
from crypto_quant.nautilus_evidence_adapter import (
    build_nautilus_supply_chain_fetch_attestation,
    compare_nautilus_sandbox,
)
from crypto_quant.nautilus_sandbox_dependency import build_nautilus_sandbox_dependency_lock


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts" / "nautilus-sandbox"


class NautilusSandboxArtifactTests(unittest.TestCase):
    def test_committed_comparison_is_exact_blocked_report(self):
        dependency = build_nautilus_sandbox_dependency_lock(workspace_root=ROOT)
        comparison = compare_nautilus_sandbox(
            dependency_lock=dependency,
            workspace_root=ROOT,
            failure_attestation=build_nautilus_supply_chain_fetch_attestation(),
        )
        self.assertEqual(
            (ARTIFACT_ROOT / "nautilus-sandbox-comparison-v0.63.0.json").read_bytes(),
            canonical_json(comparison).encode("utf-8") + b"\n",
        )

    def test_blocked_preflight_has_no_unverified_protocol_or_result(self):
        for name in (
            "nautilus-sandbox-request-v0.63.0.json",
            "nautilus-sandbox-current-reference-v0.63.0.json",
            "nautilus-sandbox-result-v0.63.0.json",
        ):
            self.assertFalse((ARTIFACT_ROOT / name).exists())
        self.assertFalse(
            (ROOT / "src" / "crypto_quant" / "nautilus_sandbox_contract.py").exists()
        )
        self.assertFalse(
            (ROOT / "sandboxes" / "nautilus" / "src" / "crypto_quant_nautilus_sandbox" / "runner.py").exists()
        )


if __name__ == "__main__":
    unittest.main()
