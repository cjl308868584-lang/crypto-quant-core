import copy
import hashlib
import json
import stat
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_episode_cohort_plan import (
    ChallengerEpisodeCohortPlanError,
    build_challenger_episode_cohort_plan,
    challenger_episode_cohort_contract,
    challenger_episode_cohort_plan_hash,
    challenger_episode_cohort_plan_reasons,
    load_challenger_episode_cohort_plan,
    publish_challenger_episode_cohort_plan,
)


ROOT = Path(__file__).resolve().parents[1]
PILOT = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-episode-economic-result-v0.42.0.json"
)
PILOT_SHA = (
    "8627677275c31de573f1a59f638ba1678772115dc6d932027a36e2f8b62d9fee"
)
ARTIFACT = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-episode-cohort-plan-v0.43.0.json"
)


class ChallengerEpisodeCohortPlanTests(unittest.TestCase):
    def pilot(self):
        return json.loads(PILOT.read_bytes())

    def plan(self):
        return build_challenger_episode_cohort_plan(
            pilot_result=self.pilot(),
            pilot_result_file_sha256=PILOT_SHA,
        )

    def test_known_negative_pilot_is_exact_and_not_confirmatory(self):
        plan = self.plan()
        pilot = plan["known_pilot"]
        self.assertEqual(
            pilot["role"], "EXPOSED_PILOT_MANDATORY_ALL_STREAM"
        )
        self.assertEqual(pilot["net_pnl_usdt"], "-23.4627746535")
        self.assertEqual(pilot["net_return"], "-0.0234627746535")
        self.assertEqual(pilot["positive_label"], 0)
        self.assertFalse(pilot["confirmatory_eligible"])
        self.assertTrue(pilot["all_stream_inclusion_required"])
        changed = copy.deepcopy(self.pilot())
        changed["economics"]["net_pnl_usdt"] = "1"
        with self.assertRaisesRegex(
            ChallengerEpisodeCohortPlanError,
            "CHALLENGER_EPISODE_COHORT_PILOT_INVALID",
        ):
            build_challenger_episode_cohort_plan(
                pilot_result=changed,
                pilot_result_file_sha256=PILOT_SHA,
            )

    def test_forward_window_population_and_tail_are_fixed(self):
        cohort = self.plan()["cohort"]
        self.assertEqual(
            cohort["start_inclusive"], "2026-07-30T12:00:00.000Z"
        )
        self.assertEqual(
            cohort["end_exclusive"], "2026-10-28T12:00:00.000Z"
        )
        self.assertEqual(cohort["duration_days"], 90)
        self.assertEqual(cohort["slot_cadence_seconds"], 14400)
        self.assertEqual(cohort["maximum_episode_hours"], 24)
        self.assertEqual(
            cohort["observation_tail_end"], "2026-10-29T12:00:00.000Z"
        )
        self.assertEqual(
            cohort["entry_population"],
            "ALL_ENTER_LONG_WITH_ENTRY_SLOT_IN_HALF_OPEN_WINDOW",
        )
        self.assertEqual(
            cohort["exit_followup"],
            "FOLLOW_TO_NATURAL_EXIT_EVEN_AFTER_END",
        )
        self.assertFalse(cohort["episode_omission_allowed"])
        self.assertFalse(cohort["historical_backfill_allowed"])

    def test_cost_stopping_reporting_and_ai_boundaries_are_fixed(self):
        plan = self.plan()
        measurement = plan["measurement_binding"]
        self.assertEqual(measurement["slippage_rate_per_side"], "0.001")
        self.assertEqual(
            measurement["assumed_taker_fee_rate_per_side"], "0.0015"
        )
        self.assertEqual(measurement["reference_capital_usdt"], "1000")
        stopping = plan["stopping_policy"]
        self.assertFalse(
            stopping["positive_or_negative_pnl_early_stop_allowed"]
        )
        self.assertFalse(stopping["window_extension_allowed"])
        self.assertFalse(stopping["window_reset_allowed"])
        self.assertEqual(
            stopping["insufficient_evidence_status"], "INCONCLUSIVE"
        )
        self.assertEqual(
            stopping["continuity_failure_status"],
            "FAILED_CLOSED_NO_BACKFILL",
        )
        self.assertTrue(
            plan["reporting_policy"][
                "pilot_and_confirmatory_separate_required"
            ]
        )
        self.assertFalse(
            plan["reporting_policy"]["positive_only_reporting_allowed"]
        )
        self.assertFalse(plan["ai_policy"]["ai_training_in_scope"])
        self.assertFalse(plan["ai_policy"]["ai_trading_authority"])

    def test_builder_is_deterministic_for_one_hundred_replays(self):
        expected = canonical_json(self.plan()).encode("utf-8")
        for _ in range(100):
            self.assertEqual(
                canonical_json(self.plan()).encode("utf-8"), expected
            )

    def test_rehash_cannot_hide_semantic_tamper(self):
        original = self.plan()
        variants = []
        for path, value in (
            (("cohort", "end_exclusive"), "2026-11-01T12:00:00.000Z"),
            (("known_pilot", "net_pnl_usdt"), "23.4627746535"),
            (("trial_binding", "policy_hash"), "0" * 64),
            (
                (
                    "stopping_policy",
                    "positive_or_negative_pnl_early_stop_allowed",
                ),
                True,
            ),
            (("ai_policy", "ai_training_in_scope"), True),
            (("eligibility", "profitability"), "ELIGIBLE"),
        ):
            changed = copy.deepcopy(original)
            changed[path[0]][path[1]] = value
            changed["plan_hash"] = challenger_episode_cohort_plan_hash(
                changed
            )
            variants.append(changed)
        for changed in variants:
            self.assertTrue(
                challenger_episode_cohort_plan_reasons(
                    changed,
                    pilot_result=self.pilot(),
                    pilot_result_file_sha256=PILOT_SHA,
                )
            )

    def test_publish_and_load_are_owner_only_and_conflict_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plans" / "plan.json"
            plan = self.plan()
            publish_challenger_episode_cohort_plan(
                plan=plan,
                pilot_result=self.pilot(),
                pilot_result_file_sha256=PILOT_SHA,
                output_path=path,
            )
            publish_challenger_episode_cohort_plan(
                plan=plan,
                pilot_result=self.pilot(),
                pilot_result_file_sha256=PILOT_SHA,
                output_path=path,
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(
                path.read_bytes(), canonical_json(plan).encode("utf-8")
            )
            loaded = load_challenger_episode_cohort_plan(
                plan_path=path,
                pilot_result=self.pilot(),
                pilot_result_file_sha256=PILOT_SHA,
            )
            self.assertEqual(loaded, plan)
            changed = copy.deepcopy(plan)
            changed["plan_hash"] = "0" * 64
            with self.assertRaisesRegex(
                ChallengerEpisodeCohortPlanError,
                "PLAN_INVALID",
            ):
                publish_challenger_episode_cohort_plan(
                    plan=changed,
                    pilot_result=self.pilot(),
                    pilot_result_file_sha256=PILOT_SHA,
                    output_path=path,
                )

    def test_schema_mirror_and_committed_artifact_are_exact(self):
        config = (
            ROOT
            / "config"
            / "challenger-episode-cohort-plan-v1.schema.json"
        )
        package = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / "challenger-episode-cohort-plan-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), package.read_bytes())
        schema = json.loads(config.read_bytes())
        Draft202012Validator.check_schema(schema)
        body = ARTIFACT.read_bytes()
        plan = json.loads(body)
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "a431fe2d316d8c9a647a4c45de280644"
            "e60554719603b5506670cef8a02ee7ff",
        )
        self.assertEqual(body, canonical_json(plan).encode("utf-8") + b"\n")
        self.assertEqual(plan, self.plan())
        self.assertEqual(
            plan["plan_id"],
            "challenger_episode_cohort_plan_"
            "56fa3d25d37d5445e7c29ad7cda6cd4"
            "dac622e036ee0a017c5790fb33142ab1c",
        )
        self.assertEqual(
            plan["plan_hash"], challenger_episode_cohort_plan_hash(plan)
        )
        self.assertFalse(
            tuple(Draft202012Validator(schema).iter_errors(plan))
        )
        self.assertEqual(
            challenger_episode_cohort_plan_reasons(
                plan,
                pilot_result=self.pilot(),
                pilot_result_file_sha256=PILOT_SHA,
            ),
            (),
        )

    def test_contract_matches_plan_without_runtime_authority(self):
        plan = self.plan()
        contract = challenger_episode_cohort_contract()
        for key, value in contract.items():
            self.assertEqual(plan[key], value)
        self.assertEqual(
            plan["authority"],
            {
                "market_request_count": 0,
                "runner_invocation_count": 0,
                "broker_request_count": 0,
                "order_submission_count": 0,
                "state_write_count": 0,
                "date_override_allowed": False,
                "episode_override_allowed": False,
                "economic_override_allowed": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
