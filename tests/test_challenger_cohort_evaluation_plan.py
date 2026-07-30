import copy
import hashlib
import json
import stat
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_cohort_evaluation_plan import (
    ChallengerCohortEvaluationPlanError,
    build_challenger_cohort_evaluation_plan,
    challenger_cohort_evaluation_contract,
    challenger_cohort_evaluation_plan_hash,
    challenger_cohort_evaluation_plan_reasons,
    load_challenger_cohort_evaluation_plan,
    publish_challenger_cohort_evaluation_plan,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-episode-cohort-plan-v0.43.0.json"
)
SOURCE_SHA = (
    "a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff"
)
ARTIFACT = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-cohort-evaluation-plan-v0.44.0.json"
)


class ChallengerCohortEvaluationPlanTests(unittest.TestCase):
    def source(self):
        return json.loads(SOURCE.read_bytes())

    def plan(self):
        return build_challenger_cohort_evaluation_plan(
            cohort_plan=self.source(),
            cohort_plan_file_sha256=SOURCE_SHA,
        )

    def test_source_cohort_is_exact_and_precedes_registration(self):
        plan = self.plan()
        self.assertEqual(
            plan["source_cohort_plan"]["plan_id"],
            "challenger_episode_cohort_plan_"
            "56fa3d25d37d5445e7c29ad7cda6cd4"
            "dac622e036ee0a017c5790fb33142ab1c",
        )
        self.assertEqual(
            plan["source_cohort_plan"]["file_sha256"], SOURCE_SHA
        )
        self.assertLess(
            plan["source_cohort_plan"]["registered_at"],
            plan["registered_at"],
        )
        changed = copy.deepcopy(self.source())
        changed["cohort"]["end_exclusive"] = (
            "2026-11-01T12:00:00.000Z"
        )
        with self.assertRaisesRegex(
            ChallengerCohortEvaluationPlanError,
            "CHALLENGER_COHORT_EVALUATION_SOURCE_INVALID",
        ):
            build_challenger_cohort_evaluation_plan(
                cohort_plan=changed,
                cohort_plan_file_sha256=SOURCE_SHA,
            )

    def test_population_has_exactly_540_required_slots(self):
        plan = self.plan()
        population = plan["population_contract"]
        self.assertEqual(population["required_slot_count"], 540)
        self.assertEqual(population["slot_cadence_seconds"], 14400)
        self.assertFalse(population["episode_omission_allowed"])
        self.assertFalse(population["historical_backfill_allowed"])
        blocks = plan["time_blocks"]
        self.assertEqual(len(blocks), 6)
        self.assertEqual(
            sum(item["required_slot_count"] for item in blocks), 540
        )
        self.assertTrue(
            all(item["calendar_days"] == 15 for item in blocks)
        )
        self.assertTrue(
            all(
                left["end_exclusive"] == right["start_inclusive"]
                for left, right in zip(blocks, blocks[1:])
            )
        )

    def test_statistical_design_and_sample_gates_are_fixed(self):
        plan = self.plan()
        design = plan["statistical_design"]
        self.assertEqual(design["block_length"], 3)
        self.assertEqual(design["minimum_block_count"], 10)
        self.assertEqual(design["resample_count"], 10000)
        self.assertEqual(design["seed"], 2026073044)
        self.assertEqual(design["minimum_economic_effect"], "0.005")
        self.assertEqual(design["minimum_achieved_power"], "0.80")
        self.assertEqual(
            design["maximum_two_sided_ci_full_width"], "0.02"
        )
        gates = {item["gate_id"]: item for item in plan["sample_gates"]}
        self.assertEqual(
            gates["NOMINAL_COMPLETED_EPISODES"]["threshold"], 30
        )
        self.assertEqual(
            gates["EFFECTIVE_EVENT_COUNT"]["threshold"], 20
        )
        self.assertEqual(
            plan["primary_hypothesis"]["family_size"], 1
        )
        self.assertEqual(
            plan["primary_hypothesis"]["family_wise_alpha"], "0.05"
        )

    def test_economic_stress_leave_out_and_path_gates_are_fixed(self):
        plan = self.plan()
        gates = {item["gate_id"]: item for item in plan["economic_gates"]}
        self.assertEqual(len(gates), 5)
        self.assertEqual(
            gates["PRIMARY_MEAN_RETURN_LCB"]["comparator"], "GT"
        )
        self.assertEqual(
            gates["NONNEGATIVE_FIXED_TIME_BLOCKS"]["threshold"], 5
        )
        self.assertEqual(
            gates["FIXED_NOTIONAL_MAX_DRAWDOWN"]["threshold"], "0.10"
        )
        stress = plan["stress_policy"]
        self.assertEqual(stress["entry_slippage_rate"], "0.0015")
        self.assertEqual(stress["exit_slippage_rate"], "0.0015")
        self.assertEqual(stress["taker_fee_rate_per_side"], "0.00225")
        self.assertTrue(stress["same_source_rows_required"])
        leave_out = plan["leave_out_policy"]
        self.assertEqual(leave_out["maximum_removed_count"], 5)
        self.assertEqual(
            leave_out["ranking"], "NET_PNL_DESC_EPISODE_ID_ASC"
        )
        self.assertTrue(leave_out["rerun_all_sample_gates"])

    def test_final_statuses_never_turn_research_into_profitability(self):
        plan = self.plan()
        states = plan["final_state_machine"]
        self.assertEqual(
            states["before_tail_end"],
            "COLLECTING_DESCRIPTIVE_NO_EARLY_SUCCESS",
        )
        self.assertFalse(plan["interim_policy"]["early_success_allowed"])
        self.assertFalse(
            plan["interim_policy"]["pnl_based_early_stop_allowed"]
        )
        self.assertEqual(
            plan["eligibility"]["profitability"],
            "INELIGIBLE_RESEARCH_PROXY_NOT_SYSTEM_PAPER",
        )
        self.assertEqual(
            plan["eligibility"]["ai_comparison"],
            "INELIGIBLE_NO_PAIRED_AI_COHORT",
        )

    def test_builder_is_deterministic_for_one_hundred_replays(self):
        expected = canonical_json(self.plan()).encode("utf-8")
        for _ in range(100):
            self.assertEqual(
                canonical_json(self.plan()).encode("utf-8"), expected
            )

    def test_rehash_cannot_hide_parameter_or_eligibility_tamper(self):
        original = self.plan()
        variants = []
        changes = (
            ("population_contract", "required_slot_count", 539),
            ("statistical_design", "resample_count", 1000),
            ("statistical_design", "minimum_economic_effect", "0"),
            ("stress_policy", "taker_fee_rate_per_side", "0"),
            ("leave_out_policy", "maximum_removed_count", 0),
            ("interim_policy", "early_success_allowed", True),
            ("eligibility", "profitability", "ELIGIBLE"),
        )
        for section, field, value in changes:
            changed = copy.deepcopy(original)
            changed[section][field] = value
            changed["plan_hash"] = (
                challenger_cohort_evaluation_plan_hash(changed)
            )
            variants.append(changed)
        changed_gate = copy.deepcopy(original)
        changed_gate["sample_gates"][0]["threshold"] = 1
        changed_gate["plan_hash"] = (
            challenger_cohort_evaluation_plan_hash(changed_gate)
        )
        variants.append(changed_gate)
        for changed in variants:
            self.assertTrue(
                challenger_cohort_evaluation_plan_reasons(
                    changed,
                    cohort_plan=self.source(),
                    cohort_plan_file_sha256=SOURCE_SHA,
                )
            )

    def test_publish_load_is_owner_only_and_conflict_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plans" / "plan.json"
            plan = self.plan()
            publish_challenger_cohort_evaluation_plan(
                plan=plan,
                cohort_plan=self.source(),
                cohort_plan_file_sha256=SOURCE_SHA,
                output_path=path,
            )
            publish_challenger_cohort_evaluation_plan(
                plan=plan,
                cohort_plan=self.source(),
                cohort_plan_file_sha256=SOURCE_SHA,
                output_path=path,
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(
                path.read_bytes(), canonical_json(plan).encode("utf-8")
            )
            loaded = load_challenger_cohort_evaluation_plan(
                plan_path=path,
                cohort_plan=self.source(),
                cohort_plan_file_sha256=SOURCE_SHA,
            )
            self.assertEqual(loaded, plan)
            changed = copy.deepcopy(plan)
            changed["plan_hash"] = "0" * 64
            with self.assertRaisesRegex(
                ChallengerCohortEvaluationPlanError,
                "PLAN_INVALID",
            ):
                publish_challenger_cohort_evaluation_plan(
                    plan=changed,
                    cohort_plan=self.source(),
                    cohort_plan_file_sha256=SOURCE_SHA,
                    output_path=path,
                )

    def test_schema_mirror_contract_and_committed_artifact_are_exact(self):
        config = (
            ROOT
            / "config"
            / "challenger-cohort-evaluation-plan-v1.schema.json"
        )
        package = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / "challenger-cohort-evaluation-plan-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), package.read_bytes())
        schema = json.loads(config.read_bytes())
        Draft202012Validator.check_schema(schema)
        body = ARTIFACT.read_bytes()
        plan = json.loads(body)
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "49e3b7642e163bb95c4ce01bc1c8d95a"
            "23b0cefce277d2f99f2e69029207a4d8",
        )
        self.assertEqual(body, canonical_json(plan).encode("utf-8") + b"\n")
        self.assertEqual(plan, self.plan())
        self.assertEqual(
            plan["plan_id"],
            "challenger_cohort_evaluation_plan_"
            "54a5456345f57219e2ee8763fd35dd4c"
            "753e843d31709f342e283fd4026eb037",
        )
        self.assertEqual(
            plan["plan_hash"],
            challenger_cohort_evaluation_plan_hash(plan),
        )
        self.assertFalse(
            tuple(Draft202012Validator(schema).iter_errors(plan))
        )
        contract = challenger_cohort_evaluation_contract()
        for key, value in contract.items():
            self.assertEqual(plan[key], value)
        self.assertEqual(
            challenger_cohort_evaluation_plan_reasons(
                plan,
                cohort_plan=self.source(),
                cohort_plan_file_sha256=SOURCE_SHA,
            ),
            (),
        )


if __name__ == "__main__":
    unittest.main()
