import hashlib
import unittest
from pathlib import Path

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
    load_challenger_replacement_accelerated_canary_plan,
)
from crypto_quant.challenger_replacement_accelerated_canary_supersession import (
    build_challenger_replacement_accelerated_canary_supersession,
    load_challenger_replacement_accelerated_canary_supersession,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = (
    ROOT
    / "artifacts/challenger-replacement/"
    "challenger-replacement-accelerated-canary-plan-v0.75.0.json"
)
RECORD_PATH = (
    ROOT
    / "artifacts/challenger-replacement/"
    "challenger-replacement-accelerated-canary-supersession-v0.75.0.json"
)
V069_PATH = (
    ROOT
    / "artifacts/challenger-replacement/"
    "challenger-replacement-plan-v0.69.0.json"
)
V074_PATH = (
    ROOT
    / "artifacts/challenger-replacement/"
    "challenger-replacement-economic-evaluation-plan-v0.74.0.json"
)


class V075ArtifactTests(unittest.TestCase):
    def test_artifact_sha256_values_are_literal_and_exact(self):
        from crypto_quant import (
            challenger_replacement_accelerated_canary_plan as plan_module,
        )
        from crypto_quant import (
            challenger_replacement_accelerated_canary_supersession as record_module,
        )

        self.assertEqual(
            (
                hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest(),
                plan_module._ARTIFACT_SHA256,
            ),
            (
                "31b9545a18850d068e858ae434a79e43967efd584df2cee9ff0833b1b203d6ee",
                "31b9545a18850d068e858ae434a79e43967efd584df2cee9ff0833b1b203d6ee",
            ),
        )
        self.assertEqual(
            (
                hashlib.sha256(RECORD_PATH.read_bytes()).hexdigest(),
                record_module._ARTIFACT_SHA256,
            ),
            (
                "8f7d2d551b20154dc5bc26316376386e721929fc81a2392fcb1ea692ad09049e",
                "8f7d2d551b20154dc5bc26316376386e721929fc81a2392fcb1ea692ad09049e",
            ),
        )

    def test_artifacts_are_exact_builder_bytes_and_strictly_replay(self):
        plan_bytes = (
            canonical_json(
                build_challenger_replacement_accelerated_canary_plan()
            ).encode("utf-8")
            + b"\n"
        )
        record_bytes = (
            canonical_json(
                build_challenger_replacement_accelerated_canary_supersession()
            ).encode("utf-8")
            + b"\n"
        )
        self.assertEqual(PLAN_PATH.read_bytes(), plan_bytes)
        self.assertEqual(RECORD_PATH.read_bytes(), record_bytes)
        self.assertEqual(
            load_challenger_replacement_accelerated_canary_plan(PLAN_PATH),
            build_challenger_replacement_accelerated_canary_plan(),
        )
        self.assertEqual(
            load_challenger_replacement_accelerated_canary_supersession(
                RECORD_PATH
            ),
            build_challenger_replacement_accelerated_canary_supersession(),
        )

    def test_successor_sha_and_predecessor_identities_are_exact(self):
        record = build_challenger_replacement_accelerated_canary_supersession()
        plan_bytes = (
            canonical_json(
                build_challenger_replacement_accelerated_canary_plan()
            ).encode("utf-8")
            + b"\n"
        )
        self.assertEqual(
            record["successor"]["file_sha256"],
            hashlib.sha256(plan_bytes).hexdigest(),
        )
        self.assertEqual(
            hashlib.sha256(V069_PATH.read_bytes()).hexdigest(),
            "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3",
        )
        self.assertEqual(
            hashlib.sha256(V074_PATH.read_bytes()).hexdigest(),
            "24fba7579ac36c037aaef4fbf34a69b56503358edbd64addbe01f30a70c33297",
        )

    def test_formal_artifacts_grant_no_runtime_or_money_authority(self):
        for value in (
            build_challenger_replacement_accelerated_canary_plan(),
            build_challenger_replacement_accelerated_canary_supersession(),
        ):
            self.assertEqual(set(value["authority"].values()), {False, 0})
        plan = build_challenger_replacement_accelerated_canary_plan()
        self.assertFalse(plan["supersession_scope"]["economic_contract_changed"])
        self.assertEqual(
            plan["projection_contract"]["ceremony_economic_use"],
            "EXCLUDED_FROM_STRATEGY_AND_ECONOMIC_EVIDENCE",
        )


if __name__ == "__main__":
    unittest.main()
