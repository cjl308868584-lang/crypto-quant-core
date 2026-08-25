import json
import copy
import os
import re
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import business_hash, canonical_decimal, canonical_json, stable_id
from crypto_quant.errors import CanonicalizationError
from crypto_quant.challenger_replacement_economic_plan import (
    ChallengerReplacementEconomicPlanError,
    build_challenger_replacement_economic_plan,
    challenger_replacement_economic_plan_hash,
    challenger_replacement_economic_plan_reasons,
    load_challenger_replacement_economic_plan,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SCHEMA = (
    ROOT
    / "src/crypto_quant/schemas/"
    "challenger-replacement-economic-evaluation-plan-v1.schema.json"
)
EXPECTED_TOP_LEVEL_KEYS = {
    "$schema",
    "schema_version",
    "plan_id",
    "plan_hash",
    "foundation",
    "population_contract",
    "economic_measurement",
    "missingness_policy",
    "statistical_design",
    "sample_gates",
    "economic_gates",
    "final_state_machine",
    "interim_policy",
    "authority",
    "status",
    "eligibility",
    "warnings",
}
TERMINAL_OUTCOMES = [
    "RESEARCH_CONTINUATION_GATE_PASS",
    "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
    "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
]
AUTHORITY_CONSTS = {
    "production_activation": False,
    "runtime_install_authorized": False,
    "replacement_start_authorized": False,
    "account_requests_allowed": False,
    "credentials_allowed": False,
    "broker_requests_allowed": False,
    "real_orders_allowed": False,
    "market_requests": 0,
    "production_state_writes": 0,
    "economic_outcome_reads": 0,
}


class EconomicPlanSchemaTests(unittest.TestCase):
    def _definition(self, schema, name):
        return schema["$defs"][name]

    def _walk(self, value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from self._walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._walk(child)

    def test_schema_is_exact_key_draft_202012(self):
        """Catches a permissive or non-Draft-2020-12 package contract."""
        schema = json.loads(PACKAGE_SCHEMA.read_text())
        Draft202012Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), EXPECTED_TOP_LEVEL_KEYS)
        self.assertNotIn("result", schema["properties"])
        self.assertNotIn("observations", schema["properties"])

    def test_every_object_schema_rejects_unknown_keys(self):
        """Catches a nested object that could admit caller-provided values."""
        schema = json.loads(PACKAGE_SCHEMA.read_text())
        object_schemas = [
            node for node in self._walk(schema) if node.get("type") == "object"
        ]
        self.assertTrue(object_schemas)
        for object_schema in object_schemas:
            self.assertIs(object_schema.get("additionalProperties"), False)

    def test_terminal_outcomes_are_the_frozen_three_state_result_set(self):
        """Catches a renamed, reordered, added, or omitted terminal result."""
        schema = json.loads(PACKAGE_SCHEMA.read_text())
        self.assertEqual(
            [
                item["const"]
                for item in self._definition(schema, "finalStateMachine")
                ["properties"]["terminal_outcomes"]["prefixItems"]
            ],
            TERMINAL_OUTCOMES,
        )

    def test_decimal_grammar_matches_canonical_decimal_rendering(self):
        """Catches Decimal spellings that canonical_decimal would normalize or reject."""
        schema = json.loads(PACKAGE_SCHEMA.read_text())
        pattern = self._definition(schema, "decimal")["pattern"]
        for value in ("0", "1", "-1", "0.5", "-0.5", "123.004"):
            self.assertEqual(canonical_decimal(value), value)
            self.assertIsNotNone(re.fullmatch(pattern, value))

        with self.assertRaises(CanonicalizationError):
            canonical_decimal("-0")
        for value, canonical_value in (
            ("-0", None),
            ("0.0", "0"),
            ("1.0", "1"),
            ("-1.0", "-1"),
            ("00", "0"),
            ("01", "1"),
            ("1.", "1"),
        ):
            if canonical_value is not None:
                self.assertEqual(canonical_decimal(value), canonical_value)
            self.assertIsNone(re.fullmatch(pattern, value))

    def test_authority_is_fixed_to_plan_only_zeros_and_falses(self):
        """Catches any schema path that could grant runtime or outcome authority."""
        schema = json.loads(PACKAGE_SCHEMA.read_text())
        authority = self._definition(schema, "authority")
        self.assertEqual(set(authority["required"]), set(AUTHORITY_CONSTS))
        self.assertEqual(
            {
                key: authority["properties"][key]["const"]
                for key in AUTHORITY_CONSTS
            },
            AUTHORITY_CONSTS,
        )


class EconomicPlanBuilderTests(unittest.TestCase):
    """Behavioral contract for the parameterless preregistration builder."""

    def test_builder_freezes_all_economic_preregistration_values(self):
        """Catches a changed policy, authority, foundation, or future result."""
        plan = build_challenger_replacement_economic_plan()

        self.assertEqual(
            plan["foundation"],
            {
                "v069_plan": {
                    "file_sha256": "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3",
                    "plan_id": "challenger_replacement_plan_v3_e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f",
                    "plan_hash": "f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486",
                },
                "v069_owner_attestation": {
                    "file_sha256": "b1ec38575b2e4f2b93b9f4838aa04633f382b60aef65843e4812d9b5c799b9c7",
                },
                "v070_result_evidence_schema": {
                    "file_sha256": "755f4e049da22ab4300ce5ed68b73c0d9462581792b7b3955fff1712f6ca6dca",
                },
                "v071_simulation_contract": {
                    "file_sha256": "65a0af1cccee5ad60aeaa7b0266bb217fab680d866ea3191ca77d214a292d86f",
                },
                "v072_golden_manifest": {
                    "file_sha256": "c86993a5d56805eee3b703301f92d704cf0e7dacd06d4725a7ad9c3c16dd2b5f",
                },
                "v073_release": {
                    "peeled_commit": "34bd0e9ba96c769b7301c482730a03fb975c24ce",
                    "manifest_hash": "0117d3a17bdea7e2a22004d675175083e9d863722c6c176632d29e3c4c6e62d0",
                    "tree_hash": "569afbae2352932a05a6c5daeb1c52049c9a3ec74034d666664579aa2bd0a97e",
                    "file_sha256": "c41a46442993bac947773d383f722dfbaa358417ba67e87bf1e81db37c5e1c74",
                },
            },
        )
        expected_policies = {
            "population_contract": {
                "start_source": "FIRST_VERIFIED_NATURAL_OBSERVED_DECISION_OPPORTUNITY",
                "start_identity_fields": ["opportunity_id", "event_hash", "scheduled_for", "observed_at", "plan_id", "plan_hash", "deployment_identity", "event_root_identity"],
                "cadence_seconds": 14_400, "minimum_calendar_days": 90,
                "start_scheduled_for_or_null": None, "tail_scheduled_for_or_null": None,
                "window_kind": "HALF_OPEN_SCHEDULED_FOR_START_INCLUSIVE_TAIL_EXCLUSIVE",
                "terminal_outcomes": ["OBSERVED", "MISSED"],
                "historical_backfill_allowed": False, "window_reset_allowed": False,
                "alternate_start_allowed": False, "tail_pre_action_mark_required": True,
            },
            "economic_measurement": {
                "starting_virtual_equity_usdt": "100", "capital_limit_usdt": "100",
                "gross_exposure_limit": "0.5", "technical_leverage_cap": "2",
                "configured_simulation_leverage": "1", "economic_asset": "ETH",
                "daily_boundary_count": 91, "daily_return_count": 90,
                "daily_return_formula": "BOUNDARY_EQUITY_DELTA_DIVIDED_BY_100",
                "decimal_arithmetic_only": True, "binary_float_allowed": False,
                "spot_mark": "CONSERVATIVE_BID_MARK",
                "perpetual_mark": "CANONICAL_MARK_PRICE_AND_CONTRACT_MULTIPLIER",
                "fee_treatment": "ACCRUED_ONCE_ONLY", "funding_treatment": "SIGNED_CASHFLOW_ONCE_ONLY",
            },
            "missingness_policy": {
                "observed_coverage_minimum": "0.95", "terminal_coverage_required": "1",
                "exposed_miss_result": "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
                "optimistic_flat_miss": "ZERO_ECONOMIC_CHANGE",
                "pessimistic_flat_miss": "ONE_FROZEN_STOPPED_CYCLE_LOSS_PER_DISTINCT_FLAT_MISS",
                "flat_miss_notional_usdt": "50", "protective_stop_distance": "0.02",
                "market_slippage_per_side": "0.001", "taker_fee_per_side": "0.0015",
                "flat_miss_loss_rate": "0.025", "flat_miss_loss_usdt": "1.25",
                "pass_requires_both_bounds": True,
                "disagreement_result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
            },
            "statistical_design": {
                "primary_null": "MEAN_DAILY_NET_RETURN_LTE_ZERO",
                "primary_alternative": "MEAN_DAILY_NET_RETURN_GT_ZERO", "family_size": 1,
                "family_wise_alpha": "0.05", "method": "OVERLAPPING_NON_CIRCULAR_MOVING_BLOCK_BOOTSTRAP",
                "block_length_days": 7, "sample_length": 90, "resample_count": 10_000,
                "seed": 2026082574, "draw_start_method": "SHA256_REJECTION_SAMPLED_MBB_V1",
                "quantile": "CONSERVATIVE_NEAREST_RANK_0_05", "confidence_level": "0.95",
                "primary_endpoint": "MEAN_DAILY_NET_RETURN_LCB95",
                "minimum_economic_effect_daily": "0.0005",
                "power_method": "CENTERED_BOOTSTRAP_CRITICAL_VALUE_ACHIEVED_POWER",
            },
            "final_state_machine": {
                "terminal_outcomes": TERMINAL_OUTCOMES,
                "first_final_artifact_immutable": True, "rerun_allowed": False,
                "threshold_override_allowed": False, "sample_deletion_allowed": False,
                "alternate_seed_allowed": False, "alternate_start_allowed": False,
                "favorable_result_selection_allowed": False,
            },
            "interim_policy": {
                "economics_withheld_before_tail": True, "early_success_allowed": False,
                "pnl_based_early_stop_allowed": False, "threshold_override_allowed": False,
                "sample_override_allowed": False, "rerun_to_seek_better_result_allowed": False,
            },
        }
        for section, expected in expected_policies.items():
            with self.subTest(section=section):
                self.assertEqual(
                    plan[section], {**expected, "policy_hash": business_hash(expected)}
                )
        self.assertEqual(
            plan["sample_gates"],
            [
                {"metric": "CALENDAR_DAYS", "operator": "EQ", "threshold": "90"},
                {"metric": "DAILY_RETURN_COUNT", "operator": "EQ", "threshold": "90"},
                {"metric": "TERMINAL_COVERAGE", "operator": "EQ", "threshold": "1"},
                {"metric": "OBSERVED_COVERAGE", "operator": "GTE", "threshold": "0.95"},
                {"metric": "COMPLETED_CYCLES", "operator": "GTE", "threshold": "12"},
                {"metric": "SPOT_COMPLETED_CYCLES", "operator": "GTE", "threshold": "3"},
                {"metric": "PERPETUAL_COMPLETED_CYCLES", "operator": "GTE", "threshold": "3"},
                {"metric": "NONEMPTY_FIXED_BLOCKS", "operator": "EQ", "threshold": "6"},
                {"metric": "MINIMUM_MBB_BLOCKS", "operator": "GTE", "threshold": "12"},
                {"metric": "ACHIEVED_POWER_AT_MERE", "operator": "GTE", "threshold": "0.80"},
            ],
        )
        self.assertEqual(
            plan["economic_gates"],
            [
                {"metric": "MEAN_DAILY_NET_RETURN_LCB95", "operator": "GT", "threshold": "0"},
                {"metric": "TOTAL_NET_PNL_USDT", "operator": "GT", "threshold": "0"},
                {"metric": "MAX_DRAWDOWN_FRACTION", "operator": "LT", "threshold": "0.05"},
                {"metric": "NONNEGATIVE_FIXED_15_DAY_BLOCKS", "operator": "GTE", "threshold": "5", "denominator": "6"},
                {"metric": "STRESS_1_5X_ADVERSE_FRICTION_TOTAL_NET_PNL_USDT", "operator": "GTE", "threshold": "0"},
            ],
        )
        self.assertEqual(plan["status"], "ECONOMIC_EVALUATION_PLAN_PREREGISTERED_NOT_STARTED")
        self.assertEqual(plan["authority"], AUTHORITY_CONSTS)
        self.assertEqual(
            plan["eligibility"],
            {
                "research_continuation_discussion": "ELIGIBLE_ONLY_AFTER_FUTURE_GATE_PASS",
                "canary": "INELIGIBLE", "live_trading": "INELIGIBLE",
                "profitability_claim": "INELIGIBLE",
            },
        )
        self.assertEqual(
            plan["warnings"],
            ["NO_ECONOMIC_OUTCOME_WAS_READ", "NO_90_DAY_ECONOMIC_CLOCK_WAS_STARTED", "NO_PRODUCTION_AUTHORITY_WAS_GRANTED"],
        )
        self.assertNotIn("result", plan)
        self.assertNotIn("observations", plan)

    def test_builder_returns_a_valid_independent_plan(self):
        """Catches an invalid artifact, broken self-hash, or leaked mutation."""
        first = build_challenger_replacement_economic_plan()
        self.assertRegex(first["plan_id"], r"^challenger_replacement_economic_evaluation_plan_[0-9a-f]{64}$")
        self.assertEqual(first["plan_hash"], challenger_replacement_economic_plan_hash(first))
        first["authority"]["market_requests"] = 1
        self.assertEqual(
            build_challenger_replacement_economic_plan()["authority"]["market_requests"],
            0,
        )


class _EconomicPlanFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "plan.json"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _write(self, body):
        self.path.write_bytes(body)
        self.path.chmod(0o600)

    def _canonical_plan_bytes(self):
        return canonical_json(build_challenger_replacement_economic_plan()).encode()


class EconomicPlanLoaderTests(_EconomicPlanFileTests):
    """Boundary tests for the owner-controlled canonical plan loader."""

    def test_loader_accepts_canonical_bytes_and_one_optional_final_lf(self):
        """Catches rejection of the only two allowed canonical encodings."""
        for suffix in (b"", b"\n"):
            self._write(self._canonical_plan_bytes() + suffix)
            self.assertEqual(
                load_challenger_replacement_economic_plan(self.path),
                build_challenger_replacement_economic_plan(),
            )

    def test_loader_rejects_relative_path(self):
        """Catches a relative path that could escape explicit caller authority."""
        with self.assertRaisesRegex(
            ChallengerReplacementEconomicPlanError,
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_PATH_INVALID",
        ):
            load_challenger_replacement_economic_plan(Path("plan.json"))

    def test_loader_reduces_raising_pathlike_conversion_failures(self):
        """Catches raw path-protocol exceptions leaking past the public boundary."""

        class RaisingPathLike(os.PathLike):
            def __init__(self, error):
                self.error = error

            def __fspath__(self):
                raise self.error

        for error in (OSError("path conversion failed"), RecursionError("loop")):
            with self.subTest(error=type(error).__name__):
                with self.assertRaisesRegex(
                    ChallengerReplacementEconomicPlanError,
                    "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_PATH_INVALID",
                ):
                    load_challenger_replacement_economic_plan(RaisingPathLike(error))

    def test_loader_reduces_strict_json_and_byte_failures_to_public_codes(self):
        """Catches permissive JSON or noncanonical byte acceptance."""
        cases = (
            (b'{"x":1,"x":2}', "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_JSON_DUPLICATE_KEY"),
            (b'{"x":1.0}', "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_JSON_FLOAT_FORBIDDEN"),
            (b'{not json}', "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_JSON_INVALID"),
            (self._canonical_plan_bytes() + b" ", "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_CANONICAL_BYTES_REQUIRED"),
            (self._canonical_plan_bytes() + b"\n\n", "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_CANONICAL_BYTES_REQUIRED"),
        )
        for body, reason_code in cases:
            with self.subTest(reason_code=reason_code):
                self._write(body)
                with self.assertRaisesRegex(ChallengerReplacementEconomicPlanError, reason_code):
                    load_challenger_replacement_economic_plan(self.path)

    def test_loader_rejects_non_owner_controlled_file_kinds_and_modes(self):
        """Catches a loader that follows links or trusts unsafe filesystem state."""
        self._write(self._canonical_plan_bytes())
        linked = self.path.with_name("linked-plan.json")
        linked.symlink_to(self.path)
        directory = self.path.with_name("directory")
        directory.mkdir(mode=0o700)
        hardlink = self.path.with_name("hardlinked-plan.json")
        os.link(self.path, hardlink)
        unsafe_mode = self.path.with_name("unsafe-mode-plan.json")
        unsafe_mode.write_bytes(self._canonical_plan_bytes())
        unsafe_mode.chmod(0o622)
        oversized = self.path.with_name("oversized-plan.json")
        oversized.write_bytes(b"x" * (256 * 1024 + 1))
        oversized.chmod(0o600)
        for candidate in (linked, directory, hardlink, unsafe_mode, oversized):
            with self.subTest(path=candidate.name):
                with self.assertRaisesRegex(
                    ChallengerReplacementEconomicPlanError,
                    "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_PATH_INVALID",
                ):
                    load_challenger_replacement_economic_plan(candidate)


class EconomicPlanMutationTests(unittest.TestCase):
    """Every frozen preregistration leaf must be semantically immutable."""

    _POLICY_SECTIONS = (
        "population_contract",
        "economic_measurement",
        "missingness_policy",
        "statistical_design",
        "final_state_machine",
        "interim_policy",
    )

    @classmethod
    def _reclaim(cls, plan):
        for section in cls._POLICY_SECTIONS:
            claimed = dict(plan[section])
            claimed.pop("policy_hash")
            plan[section]["policy_hash"] = business_hash(claimed)
        identity = {
            "foundation": plan["foundation"],
            **{
                f"{section}_policy_hash": plan[section]["policy_hash"]
                for section in cls._POLICY_SECTIONS
            },
            "sample_gates_hash": business_hash(plan["sample_gates"]),
            "economic_gates_hash": business_hash(plan["economic_gates"]),
            "final_state_machine_hash": business_hash(plan["final_state_machine"]),
        }
        plan["plan_id"] = stable_id(
            "challenger_replacement_economic_evaluation_plan", identity
        )
        plan["plan_hash"] = challenger_replacement_economic_plan_hash(plan)

    @staticmethod
    def _leaves(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items():
                yield from EconomicPlanMutationTests._leaves(child, path + (key,))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from EconomicPlanMutationTests._leaves(child, path + (index,))
        else:
            yield path

    @staticmethod
    def _replace(plan, path):
        target = plan
        for segment in path[:-1]:
            target = target[segment]
        leaf = path[-1]
        value = target[leaf]
        if isinstance(value, bool):
            target[leaf] = not value
        elif isinstance(value, int):
            target[leaf] = value + 1
        elif value is None:
            target[leaf] = "2000-01-01T00:00:00.000Z"
        else:
            target[leaf] = f"{value}_MUTATED"

    def test_mutating_each_frozen_leaf_remains_a_semantic_mismatch(self):
        """Catches a rebuilt artifact that trusts claimed hashes over content."""
        original = build_challenger_replacement_economic_plan()
        mutable_roots = (
            "foundation", "population_contract", "economic_measurement",
            "missingness_policy", "statistical_design", "sample_gates",
            "economic_gates", "final_state_machine", "interim_policy",
            "authority", "warnings", "status", "eligibility",
        )
        for root in mutable_roots:
            for relative_path in self._leaves(original[root]):
                if relative_path and relative_path[-1] == "policy_hash":
                    continue
                with self.subTest(path=(root,) + relative_path):
                    mutated = copy.deepcopy(original)
                    self._replace(mutated, (root,) + relative_path)
                    self._reclaim(mutated)
                    self.assertIn(
                        "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_SEMANTIC_MISMATCH",
                        challenger_replacement_economic_plan_reasons(mutated),
                    )

    def test_reasons_report_public_hash_policy_and_id_codes(self):
        """Catches loss of specific diagnosable integrity failures."""
        plan = build_challenger_replacement_economic_plan()
        plan["plan_hash"] = "0" * 64
        plan["population_contract"]["policy_hash"] = "0" * 64
        plan["plan_id"] = "challenger_replacement_economic_evaluation_plan_" + "0" * 64
        reasons = challenger_replacement_economic_plan_reasons(plan)
        self.assertIn("CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_HASH_MISMATCH", reasons)
        self.assertIn("CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_POLICY_HASH_MISMATCH", reasons)
        self.assertIn("CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_ID_MISMATCH", reasons)


if __name__ == "__main__":
    unittest.main()
