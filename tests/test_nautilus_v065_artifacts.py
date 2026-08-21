import subprocess
import unittest
from pathlib import Path

from crypto_quant.canonical import canonical_json
from crypto_quant.nautilus_v065_ceremony_cli import (
    load_nautilus_v065_formal_completion,
)
from crypto_quant.nautilus_v065_plan import (
    build_nautilus_v065_plan,
    load_nautilus_v065_plan,
    nautilus_v065_plan_hash,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN = (
    ROOT
    / "artifacts"
    / "nautilus-sandbox"
    / "nautilus-e2e-spike-plan-v0.65.0.json"
)
REVIEWED_COMMIT = "1f8634046ba586d4db26b38cd432e92755c2b2be"
REVIEWED_TREE = "7a4fa9b8d837d2a875acd2978fb4245e990d4118"
PLAN_COMMIT = "2cdff05629b2c6d0da30d30b12a294311c9c61ac"
FORMAL_ROOT = ROOT / "artifacts" / "nautilus-sandbox" / "v0.65.0"


def _git(*args: str) -> str:
    return subprocess.run(
        ["/usr/bin/git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout


class NautilusV065ArtifactTests(unittest.TestCase):
    def test_committed_plan_is_exact_reviewed_builder_output(self):
        expected = build_nautilus_v065_plan(
            repository_root=ROOT,
            candidate_commit=REVIEWED_COMMIT,
        )
        body = PLAN.read_bytes()
        self.assertEqual(body, canonical_json(expected).encode("utf-8") + b"\n")
        loaded = load_nautilus_v065_plan(PLAN.resolve())
        self.assertEqual(loaded, expected)
        self.assertEqual(loaded["plan_hash"], nautilus_v065_plan_hash(loaded))
        self.assertEqual(loaded["code_lock_candidate"], {
            "commit": REVIEWED_COMMIT,
            "tree": REVIEWED_TREE,
            "foundation_ancestor": "c4f6ea213077850a8fc8b9bd3392f1a4bac466f9",
        })
        self.assertEqual(loaded["foundation"]["release_tag"], "v0.64.0")
        self.assertEqual(loaded["predecessor"]["release_tag"], "v0.63.0")

    def test_plan_commit_is_the_only_allowed_delta_from_reviewed_code(self):
        self.assertEqual(
            _git("rev-list", "--count", f"{REVIEWED_COMMIT}..{PLAN_COMMIT}"),
            "1\n",
        )
        self.assertEqual(
            _git("diff", "--name-status", f"{REVIEWED_COMMIT}..{PLAN_COMMIT}"),
            "A\tartifacts/nautilus-sandbox/nautilus-e2e-spike-plan-v0.65.0.json\n"
            "A\ttests/test_nautilus_v065_artifacts.py\n",
        )

    def test_formal_result_replays_as_platform_inconclusive_without_runner(self):
        plan = load_nautilus_v065_plan(PLAN.resolve())
        result = load_nautilus_v065_formal_completion(
            FORMAL_ROOT.resolve(), expected_plan=plan
        )
        comparison = result["comparison"]
        self.assertEqual(comparison["conclusion"], "INCONCLUSIVE_KEEP_CURRENT_CORE")
        self.assertEqual(
            comparison["reason_code_or_null"], "NAUTILUS_V065_PLATFORM_MISMATCH"
        )
        self.assertEqual(comparison["runner_invocation_count"], 0)
        self.assertEqual(result["marker"]["status"], "FORMAL_CEREMONY_COMPLETED_VERIFIED")
        self.assertEqual(
            {item["name"] for item in result["files"]},
            {
                "nautilus-supply-chain-receipt-v0.65.0.json",
                "nautilus-sandbox-comparison-v0.65.0.json",
            },
        )


if __name__ == "__main__":
    unittest.main()
