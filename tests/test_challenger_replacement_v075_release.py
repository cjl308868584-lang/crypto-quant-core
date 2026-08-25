import ast
import hashlib
import json
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


class V075CrossContractTests(unittest.TestCase):
    def test_ceremony_is_excluded_from_every_strategy_and_economic_count(self):
        plan = load_challenger_replacement_accelerated_canary_plan(PLAN_PATH)
        self.assertEqual(
            plan["operational_ceremony"]["label"],
            "OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE",
        )
        self.assertEqual(
            plan["operational_ceremony"]["evidence_exclusions"],
            {
                "strategy_cycle_count": True,
                "economic_population": True,
                "simulation_performance": True,
                "stage_strategy_cycle_count": True,
            },
        )

    def test_operational_unlock_cannot_rewrite_failure_or_economic_window(self):
        plan = load_challenger_replacement_accelerated_canary_plan(PLAN_PATH)
        record = load_challenger_replacement_accelerated_canary_supersession(
            RECORD_PATH
        )
        self.assertEqual(
            plan["operational_ceremony"]["retry_policy"],
            "FAILED_BLOCK_RETAINED_NEW_EXACT_APPROVAL_AFTER_INCIDENT_ACCEPTANCE",
        )
        self.assertEqual(
            record["effectivity"]["failed_blocks_disposition"],
            "IMMUTABLE_RETAINED",
        )
        self.assertEqual(
            record["effectivity"]["existing_events_disposition"],
            "IMMUTABLE_RETAINED",
        )
        self.assertEqual(
            record["effectivity"]["economic_window_disposition"],
            "V074_UNCHANGED",
        )
        self.assertFalse(
            record["preserved_economic_authority"][
                "economic_start_or_window_changed"
            ]
        )

    def test_disconnected_segments_never_sum_to_72_hours(self):
        plan = load_challenger_replacement_accelerated_canary_plan(PLAN_PATH)
        qualification = plan["simulation_qualification"]
        self.assertEqual(qualification["minimum_continuous_seconds"], 259_200)
        self.assertEqual(
            qualification["healthy_segment_rule"],
            "ONE_FINAL_UNINTERRUPTED_SEGMENT_DISCONNECTED_SECONDS_NEVER_SUMMED",
        )
        self.assertEqual(
            qualification["flat_missed_action"],
            "CLOSE_SEGMENT_RECOVERABLE_START_NEW_SEGMENT_AT_NEXT_NATURAL_OBSERVED",
        )

    def test_hard_stops_and_ladder_are_exact_v069_values(self):
        v069 = json.loads(V069_PATH.read_text())
        plan = load_challenger_replacement_accelerated_canary_plan(PLAN_PATH)
        self.assertEqual(
            plan["hard_stop_policy"]["absolute_classes"],
            [
                "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN",
                "VENUE_LOCAL_POSITION_MISMATCH",
                "PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP",
                "RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT",
            ],
        )
        for stage in ("E0", "E1", "E2"):
            for key in (
                "capital_limit_usdt",
                "gross_exposure_limit",
                "minimum_calendar_days",
                "minimum_strategy_cycles",
            ):
                self.assertEqual(
                    plan["canary_ladder"][stage][key],
                    v069["canary_ladder"][stage][key],
                )
            for key in (
                "daily_loss_limit_kind",
                "daily_loss_limit",
                "daily_limit_action",
                "drawdown_limit_kind",
                "drawdown_limit",
                "drawdown_limit_action",
            ):
                self.assertEqual(
                    plan["canary_ladder"][stage][key],
                    v069["risk_policy"][stage][key],
                )

    def test_new_modules_have_no_runtime_network_secret_or_write_capability(self):
        forbidden_import_roots = {
            "sqlite3",
            "requests",
            "urllib",
            "http",
            "socket",
            "subprocess",
            "keyring",
            "binance",
        }
        forbidden_calls = {
            "open",
            "write_text",
            "write_bytes",
            "mkdir",
            "chmod",
            "replace",
            "rename",
            "unlink",
            "getenv",
        }
        for relative in (
            "src/crypto_quant/challenger_replacement_accelerated_canary_plan.py",
            "src/crypto_quant/challenger_replacement_accelerated_canary_supersession.py",
        ):
            tree = ast.parse((ROOT / relative).read_text())
            imported = set()
            called = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        called.add(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        called.add(node.func.attr)
            self.assertEqual(imported & forbidden_import_roots, set(), relative)
            self.assertEqual(called & forbidden_calls, set(), relative)


if __name__ == "__main__":
    unittest.main()
