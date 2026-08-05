import copy
import inspect
import json
import re
import unittest
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_plan import (
    build_challenger_replacement_plan,
    challenger_replacement_plan_hash,
    challenger_replacement_plan_reasons,
)


ROOT = Path(__file__).resolve().parents[1]
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ChallengerReplacementPlanBuilderTests(unittest.TestCase):
    def plan(self):
        return build_challenger_replacement_plan()

    def test_builder_is_parameterless_and_deterministic(self):
        self.assertEqual(tuple(inspect.signature(build_challenger_replacement_plan).parameters), ())
        first = canonical_json(self.plan()).encode("utf-8")
        for _ in range(100):
            self.assertEqual(
                canonical_json(self.plan()).encode("utf-8"),
                first,
            )

    def test_plan_binds_exact_release_and_failed_predecessor_identities(self):
        plan = self.plan()
        self.assertEqual(
            plan["foundation"],
            {
                "release_tag": "v0.61.0",
                "peeled_commit": "0811402ae4f9baebf905f548336ca2c29885ce9c",
                "package_version": "0.61.0",
                "manifest_version": "1.55.0",
                "build_input_tree_hash": "b786255726e606fd8409ad668675ae35cefbb88a4d29f80d2cb8b92323812d76",
                "manifest_hash": "e084ac0aa126824204f6f40fb89db52cd274e96abb96fd512ad6fdccd29eadb6",
                "manifest_file_sha256": "8e3b0f455238de170d55836ab0b76b1e2b41a894e540bf07c0e422a59e6e5296",
            },
        )
        predecessor = plan["predecessor"]
        self.assertEqual(
            predecessor["failure_receipt"],
            {
                "path": "artifacts/challenger-forward/challenger-cohort-missed-slot-failure-receipt-v0.54.0.json",
                "file_sha256": "7907b97d4447039c686f53dc62694c37836417b4ae555d3322b16478319b85ae",
                "receipt_id": "challenger_cohort_failure_receipt_955e47c773683f1ae4ba7997a84badc373d3daf5afb24763bdc88d1b95d30545",
                "receipt_hash": "3b2bcc2651bb80f58fb44d08ac4dfb2bdd9ab6c3ada4cfd83de00627ec8480b3",
                "failure_reason": "CHALLENGER_RUNNER_MISSED_SLOT",
                "eligibility": "PERMANENTLY_INELIGIBLE_CONTINUITY_GAP",
            },
        )
        self.assertEqual(
            predecessor["decommission_receipt"],
            {
                "path": "artifacts/challenger-forward/challenger-cohort-decommission-receipt-v0.54.0.json",
                "file_sha256": "540b831797228c950d954ee75b183fbeac08d63679463e14121fefc44fdf851f",
                "receipt_id": "challenger_cohort_decommission_receipt_30f87c50715e9f4c09b9b21072cb8c3f6fecf932d2703300adcf153fbab9323e",
                "receipt_hash": "56cfaa3f44b23e6dbc282f5947676ea93b4b92a89dcf90539a19eeb865b0bae7",
                "service_label": "local.crypto-quant.challenger-forward",
                "service_state": "DECOMMISSIONED",
            },
        )
        self.assertEqual(
            predecessor["cohort_plan"]["plan_id"],
            "challenger_episode_cohort_plan_56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c",
        )
        self.assertEqual(
            predecessor["evaluation_plan"]["plan_id"],
            "challenger_cohort_evaluation_plan_54a5456345f57219e2ee8763fd35dd4c753e843d31709f342e283fd4026eb037",
        )

    def test_research_contract_has_new_clock_and_same_decision_semantics(self):
        plan = self.plan()
        self.assertEqual(
            plan["scope"],
            {
                "mode": "REPLACEMENT_CHALLENGER_CONFIRMATORY",
                "cohort_generation": "replacement-v1",
                "route": "BASELINE_ONLY",
                "symbol": "ETHUSDT",
                "venue": "BINANCE_SPOT",
                "market": "SPOT",
                "direction": "LONG_ONLY",
                "predecessor_policy_id": "SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2",
                "predecessor_policy_hash": "2ef83c7c73fff8b163d9bad8527921bd0d87e60595680236e936254536c800e4",
                "hypothesis_registration_hash": "885b33d3a91eae1d5822fe12c16773a446c23e702f9a4110ef32f474157fa27f",
                "policy_hash": plan["scope"]["policy_hash"],
            },
        )
        decision = plan["decision_policy"]
        self.assertEqual(decision["warmup_bar_count"], 21)
        self.assertEqual(decision["sma_window"], 20)
        self.assertEqual(decision["momentum_bar_count"], 5)
        self.assertEqual(decision["entry_distance_ratio"], "0.005")
        self.assertEqual(decision["minimum_log_return"], "0")
        self.assertEqual(decision["minimum_hold_hours"], 8)
        self.assertEqual(decision["vertical_exit_hours"], 24)
        self.assertNotIn("forward_start", decision)
        cohort = plan["cohort_policy"]
        self.assertEqual(cohort["duration_days"], 90)
        self.assertEqual(cohort["slot_cadence_seconds"], 14_400)
        self.assertEqual(cohort["required_slot_count"], 540)
        self.assertEqual(
            cohort["start_source"],
            "FIRST_VERIFIED_NATURAL_SLOT_FROM_START_RECEIPT",
        )
        self.assertIsNone(cohort["start_inclusive"])
        self.assertIsNone(cohort["end_exclusive"])
        self.assertIsNone(cohort["observation_tail_end"])
        self.assertFalse(cohort["historical_backfill_allowed"])
        self.assertFalse(cohort["manual_slot_allowed"])
        self.assertFalse(cohort["window_reset_allowed"])
        self.assertFalse(cohort["window_extension_allowed"])
        self.assertFalse(cohort["optional_stopping_allowed"])

    def test_isolation_contract_uses_new_nonoverlapping_identity(self):
        isolation = self.plan()["isolation_policy"]
        root = isolation["runtime_root"]
        self.assertEqual(
            isolation["service_label"],
            "local.crypto-quant.challenger-replacement-v1",
        )
        self.assertEqual(
            isolation["service_identity"],
            "gui/501/local.crypto-quant.challenger-replacement-v1",
        )
        self.assertEqual(
            root,
            "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1",
        )
        self.assertEqual(
            isolation["target_plist"],
            "/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist",
        )
        self.assertEqual(isolation["directory_mode_octal"], "0700")
        self.assertEqual(isolation["file_mode_octal"], "0600")
        self.assertTrue(isolation["single_hardlink_required"])
        self.assertTrue(isolation["no_overwrite_required"])
        self.assertTrue(isolation["symlink_ancestors_forbidden"])
        self.assertEqual(
            isolation["forbidden_runtime_roots"],
            [
                "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1",
                "/Users/chenm4/Library/Application Support/CryptoQuant/system-paper-v1",
                "/tmp",
                "/private/tmp",
            ],
        )
        for relative in isolation["relative_paths"].values():
            parsed = PurePosixPath(relative)
            self.assertFalse(parsed.is_absolute())
            self.assertNotIn("..", parsed.parts)
        self.assertNotIn("challenger-forward-v1", root)
        self.assertNotIn("system-paper-v1", root)

    def test_evidence_and_authority_forbid_migration_and_activation(self):
        plan = self.plan()
        evidence = plan["evidence_policy"]
        self.assertFalse(evidence["old_decisions_migrated"])
        self.assertFalse(evidence["old_episodes_migrated"])
        self.assertFalse(evidence["old_receipts_migrated"])
        self.assertFalse(evidence["old_archives_migrated"])
        self.assertFalse(evidence["old_results_migrated"])
        self.assertFalse(evidence["old_pnl_migrated"])
        self.assertFalse(evidence["old_elapsed_days_migrated"])
        self.assertTrue(evidence["predecessor_failure_preserved"])
        self.assertTrue(evidence["all_stream_inclusion_required"])
        self.assertTrue(evidence["interim_economics_withheld"])
        self.assertEqual(
            plan["authority"],
            {
                "credentials_allowed": False,
                "account_requests_allowed": False,
                "broker_requests_allowed": False,
                "real_orders_allowed": False,
                "production_activation": False,
                "runtime_install_authorized": False,
                "replacement_start_authorized": False,
                "runner_invocation_count": 0,
                "market_request_count": 0,
                "state_write_count": 0,
            },
        )
        self.assertEqual(plan["status"], "PLAN_FROZEN_REPLACEMENT_NOT_STARTED")
        self.assertEqual(plan["eligibility"]["canary"], "INELIGIBLE")
        self.assertEqual(plan["eligibility"]["profitability"], "INELIGIBLE")
        self.assertEqual(plan["eligibility"]["ai_advantage"], "INELIGIBLE")

    def test_hashes_bind_each_policy_and_full_plan_semantics(self):
        plan = self.plan()
        self.assertRegex(plan["plan_id"], r"^challenger_replacement_plan_[0-9a-f]{64}$")
        self.assertTrue(HASH_PATTERN.fullmatch(plan["plan_hash"]))
        self.assertEqual(plan["plan_hash"], challenger_replacement_plan_hash(plan))
        for section in (
            "scope",
            "decision_policy",
            "cohort_policy",
            "isolation_policy",
            "evidence_policy",
        ):
            self.assertTrue(HASH_PATTERN.fullmatch(plan[section]["policy_hash"]))
        self.assertEqual(challenger_replacement_plan_reasons(plan), ())
        changed = copy.deepcopy(plan)
        changed["cohort_policy"]["required_slot_count"] = 539
        changed["cohort_policy"]["policy_hash"] = "0" * 64
        changed["plan_hash"] = challenger_replacement_plan_hash(changed)
        self.assertTrue(challenger_replacement_plan_reasons(changed))

    def test_schema_mirrors_are_strict_and_accept_only_the_frozen_plan(self):
        config = ROOT / "config" / "challenger-replacement-plan-v1.schema.json"
        package = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / "challenger-replacement-plan-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), package.read_bytes())
        schema = json.loads(config.read_bytes())
        Draft202012Validator.check_schema(schema)
        plan = self.plan()
        self.assertFalse(tuple(Draft202012Validator(schema).iter_errors(plan)))
        unknown = copy.deepcopy(plan)
        unknown["api_key"] = "forbidden"
        self.assertTrue(tuple(Draft202012Validator(schema).iter_errors(unknown)))

    def test_plan_contains_no_executable_request_or_outcome_input(self):
        forbidden_keys = {
            "url",
            "headers",
            "api_key",
            "secret",
            "credential_path",
            "account_endpoint",
            "broker_endpoint",
            "order_endpoint",
            "price",
            "fee_override",
            "pnl",
            "outcome_label",
            "manual_date",
        }

        def visit(value):
            if isinstance(value, dict):
                self.assertTrue(forbidden_keys.isdisjoint(value))
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for nested in value:
                    visit(nested)
            elif isinstance(value, str):
                self.assertNotIn("http://", value.lower())
                self.assertNotIn("https://", value.lower())

        visit(self.plan())


if __name__ == "__main__":
    unittest.main()
