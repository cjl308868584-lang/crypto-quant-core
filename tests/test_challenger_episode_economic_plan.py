import copy
import hashlib
import json
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_episode_economic_plan import (
    ChallengerEpisodeEconomicPlanError,
    build_challenger_episode_economic_plan,
    challenger_episode_economic_plan_hash,
    challenger_episode_economic_plan_reasons,
    challenger_episode_economic_policy,
    load_challenger_episode_economic_plan,
    next_strict_utc_minute,
    publish_challenger_episode_economic_plan,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-first-slot-receipt-v0.35.0.json"
)
SOURCE_SHA = (
    "b1b03bbe584386d3199cef3561fe22b4c92c3f359429ec43838d2b00a9566e43"
)
REGISTERED = datetime(2026, 7, 29, 2, 10, tzinfo=timezone.utc)


class ChallengerEpisodeEconomicPlanTests(unittest.TestCase):
    def receipt(self):
        return json.loads(SOURCE.read_bytes())

    def plan(self):
        return build_challenger_episode_economic_plan(
            first_slot_receipt=self.receipt(),
            source_file_sha256=SOURCE_SHA,
            registered_at=REGISTERED,
        )

    def test_policy_freezes_cost_source_formula_and_rounding(self):
        policy = challenger_episode_economic_policy()
        self.assertEqual(policy["slippage_rate_per_side"], "0.001")
        self.assertEqual(
            policy["assumed_taker_fee_rate_per_side"], "0.0015"
        )
        self.assertEqual(policy["reference_capital_usdt"], "1000")
        self.assertEqual(policy["price_tick_usdt"], "0.01")
        self.assertEqual(policy["quantity_step_eth"], "0.0001")
        self.assertEqual(policy["entry_source_field"], "high")
        self.assertEqual(policy["exit_source_field"], "low")
        self.assertTrue(policy["decimal_arithmetic_only"])
        self.assertFalse(policy["binary_float_allowed"])
        self.assertFalse(policy["historical_fallback_allowed"])

    def test_next_minute_is_strict_and_entry_is_real_recording_derived(self):
        self.assertEqual(
            next_strict_utc_minute("2026-07-29T00:02:06.752Z"),
            "2026-07-29T00:03:00.000Z",
        )
        self.assertEqual(
            next_strict_utc_minute("2026-07-29T00:02:00.000Z"),
            "2026-07-29T00:03:00.000Z",
        )
        plan = self.plan()
        self.assertEqual(
            plan["first_episode"]["entry_execution_minute"],
            "2026-07-29T00:03:00.000Z",
        )
        self.assertEqual(
            plan["status"],
            "PREREGISTERED_WAITING_FIRST_EPISODE_COMPLETION_AND_DAILY_ARCHIVE",
        )
        self.assertNotIn("exit_price", canonical_json(plan))
        self.assertNotIn("net_pnl_usdt", canonical_json(plan))

    def test_source_receipt_hash_file_hash_and_registration_window_are_fixed(self):
        receipt = self.receipt()
        with self.assertRaisesRegex(
            ChallengerEpisodeEconomicPlanError,
            "CHALLENGER_EPISODE_ECONOMIC_SOURCE_INVALID",
        ):
            build_challenger_episode_economic_plan(
                first_slot_receipt=receipt,
                source_file_sha256="0" * 64,
                registered_at=REGISTERED,
            )
        changed = copy.deepcopy(receipt)
        changed["state"]["first_decision"]["recorded_at"] = (
            "2026-07-29T00:02:00.000Z"
        )
        with self.assertRaisesRegex(
            ChallengerEpisodeEconomicPlanError,
            "CHALLENGER_EPISODE_ECONOMIC_SOURCE_INVALID",
        ):
            build_challenger_episode_economic_plan(
                first_slot_receipt=changed,
                source_file_sha256=SOURCE_SHA,
                registered_at=REGISTERED,
            )
        with self.assertRaisesRegex(
            ChallengerEpisodeEconomicPlanError,
            "REGISTRATION_TIME_INVALID",
        ):
            build_challenger_episode_economic_plan(
                first_slot_receipt=receipt,
                source_file_sha256=SOURCE_SHA,
                registered_at="2026-07-29T08:00:00.000Z",
            )

    def test_rehash_cannot_hide_formula_fee_or_authority_tamper(self):
        original = self.plan()
        variants = []
        fee = copy.deepcopy(original)
        fee["economic_policy"]["assumed_taker_fee_rate_per_side"] = "0"
        variants.append(fee)
        formula = copy.deepcopy(original)
        formula["economic_policy"]["entry_fill_formula"] = (
            "entry_minute_close"
        )
        variants.append(formula)
        authority = copy.deepcopy(original)
        authority["authority"]["market_request_count"] = 1
        variants.append(authority)
        for changed in variants:
            changed["economic_policy"]["policy_hash"] = (
                challenger_episode_economic_policy()["policy_hash"]
            )
            changed["plan_hash"] = challenger_episode_economic_plan_hash(
                changed
            )
            self.assertTrue(
                challenger_episode_economic_plan_reasons(
                    changed,
                    first_slot_receipt=self.receipt(),
                    source_file_sha256=SOURCE_SHA,
                )
            )

    def test_publish_load_is_canonical_owner_only_and_conflict_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "plans" / "plan.json"
            plan = self.plan()
            publish_challenger_episode_economic_plan(
                plan=plan,
                first_slot_receipt=self.receipt(),
                source_file_sha256=SOURCE_SHA,
                output_path=path,
            )
            publish_challenger_episode_economic_plan(
                plan=plan,
                first_slot_receipt=self.receipt(),
                source_file_sha256=SOURCE_SHA,
                output_path=path,
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(
                path.read_bytes(), canonical_json(plan).encode("utf-8")
            )
            loaded = load_challenger_episode_economic_plan(
                plan_path=path,
                first_slot_receipt=self.receipt(),
                source_file_sha256=SOURCE_SHA,
            )
            self.assertEqual(loaded, plan)
            other = build_challenger_episode_economic_plan(
                first_slot_receipt=self.receipt(),
                source_file_sha256=SOURCE_SHA,
                registered_at="2026-07-29T02:11:00.000Z",
            )
            with self.assertRaisesRegex(
                ChallengerEpisodeEconomicPlanError,
                "PLAN_CONFLICT",
            ):
                publish_challenger_episode_economic_plan(
                    plan=other,
                    first_slot_receipt=self.receipt(),
                    source_file_sha256=SOURCE_SHA,
                    output_path=path,
                )

    def test_schema_mirror_is_exact_and_plan_is_valid(self):
        config = (
            ROOT
            / "config"
            / "challenger-episode-economic-plan-v1.schema.json"
        )
        package = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / "challenger-episode-economic-plan-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), package.read_bytes())
        schema = json.loads(config.read_bytes())
        Draft202012Validator.check_schema(schema)
        plan = self.plan()
        self.assertFalse(
            tuple(Draft202012Validator(schema).iter_errors(plan))
        )
        self.assertEqual(
            plan["plan_hash"],
            challenger_episode_economic_plan_hash(plan),
        )
        self.assertEqual(
            challenger_episode_economic_plan_reasons(
                plan,
                first_slot_receipt=self.receipt(),
                source_file_sha256=SOURCE_SHA,
            ),
            (),
        )

    def test_committed_v037_plan_is_exact_canonical_and_has_no_outcome(self):
        path = (
            ROOT
            / "artifacts"
            / "challenger-forward"
            / "challenger-episode-economic-plan-v0.37.0.json"
        )
        body = path.read_bytes()
        plan = json.loads(body)
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "f22cb582a7df38e14220fca75359f629"
            "0af2fdb5896e5829ba5d7fd805cf54da",
        )
        self.assertEqual(body, canonical_json(plan).encode("utf-8") + b"\n")
        self.assertEqual(
            plan["plan_id"],
            "challenger_episode_economic_plan_"
            "e5c86696889d209373ce536ee0f54be7"
            "2e59d7de96b6868cd5ab0358491985a4",
        )
        self.assertEqual(
            plan["plan_hash"],
            challenger_episode_economic_plan_hash(plan),
        )
        self.assertEqual(
            challenger_episode_economic_plan_reasons(
                plan,
                first_slot_receipt=self.receipt(),
                source_file_sha256=SOURCE_SHA,
            ),
            (),
        )
        encoded = canonical_json(plan)
        for forbidden in (
            "exit_price",
            "exit_source_row",
            "gross_pnl_usdt",
            "net_pnl_usdt",
        ):
            self.assertNotIn(forbidden, encoded)
        self.assertNotIn("economic_result", plan)
        self.assertNotIn("exit_execution_minute", plan["first_episode"])
        self.assertEqual(plan["authority"]["market_request_count"], 0)
        self.assertEqual(plan["eligibility"]["profitability"], "INELIGIBLE")


if __name__ == "__main__":
    unittest.main()
