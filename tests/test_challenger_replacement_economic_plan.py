import copy
import ast
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

import crypto_quant.challenger_replacement_economic_plan as economic_plan
import crypto_quant.build as build
from crypto_quant.canonical import business_hash, canonical_decimal, canonical_json, stable_id
from crypto_quant.errors import CanonicalizationError
from crypto_quant.build import EvaluatorBuild
from crypto_quant.challenger_replacement_economic_plan import (
    ChallengerReplacementEconomicPlanError,
    build_challenger_replacement_economic_plan,
    challenger_replacement_economic_plan_hash,
    challenger_replacement_economic_plan_reasons,
    load_challenger_replacement_economic_plan,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / (
    "artifacts/challenger-replacement/"
    "challenger-replacement-economic-evaluation-plan-v0.74.0.json"
)
ARTIFACT_SHA256 = "24fba7579ac36c037aaef4fbf34a69b56503358edbd64addbe01f30a70c33297"
PLAN_ID = "challenger_replacement_economic_evaluation_plan_13ba2b74dd8c330732789a3fccd36f017847047f9fd07ea0bcf36b66f54a943e"
PLAN_HASH = "7c02267a0895cb3d8ceea79b6a38415140de23fb1cfcf3350c7fddff62089fa4"
POLICY_HASHES = {
    "population_contract": "7ec30b3a53c26dc1209773e860eb68de7081b4683d2e8535f2ea7b3ecc754e58",
    "economic_measurement": "844901a2fcadb5d1405bf4cf504bf84a42cacab7ec91b3ad4a4516a5f96ff42b",
    "missingness_policy": "d29a2347a70c6fff2d9ac9c945e174f687c1cfda68c894e3b2046f0efee078f6",
    "statistical_design": "343c3214d2c2ebe407cf07a0783339db68abf04bb837303f61999a7075950968",
    "final_state_machine": "0ac5e02fe9fd8ef29f95e6cf4981ea039d085322bb9c7ede9d4c82059dae54f7",
    "interim_policy": "6d9e542b5880b6fa1a6085a2c369efd81db44ba261ca082c913afaf8b023308d",
}
FROZEN_PREDECESSOR_PATHS = (
    ROOT / "artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json",
    ROOT / "artifacts/challenger-replacement/challenger-replacement-v3-owner-attestation-v0.69.0.json",
    ROOT / "src/crypto_quant/schemas/challenger-replacement-opportunity-result-evidence-v2.schema.json",
    ROOT / "artifacts/challenger-replacement/challenger-replacement-binance-simulation-contract-v0.71.0.json",
    ROOT / "artifacts/challenger-replacement/challenger-replacement-binance-golden-fixture-manifest-v0.72.0.json",
)
V073_PEELED_COMMIT = "34bd0e9ba96c769b7301c482730a03fb975c24ce"
V073_MANIFEST_GIT_PATH = "config/evaluator-build-manifest-v1.json"
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
SCHEMA_INVALID_REASON = "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_SCHEMA_INVALID"
V074_INVENTORY_PATHS = {
    "src/crypto_quant/challenger_replacement_economic_plan.py",
    "src/crypto_quant/schemas/challenger-replacement-economic-evaluation-plan-v1.schema.json",
    "artifacts/challenger-replacement/challenger-replacement-economic-evaluation-plan-v0.74.0.json",
    "tests/test_challenger_replacement_economic_plan.py",
    "tests/test_challenger_replacement_v074_release.py",
    "docs/superpowers/specs/2026-08-25-replacement-v3-economic-preregistration-design.md",
    "docs/superpowers/plans/2026-08-25-replacement-v3-economic-preregistration.md",
    "docs/adr/0074-replacement-v3-economic-preregistration.md",
    "docs/implementation-status-v0.74.0.md",
}
V074_RELEASE_PATHS = (
    "artifacts/challenger-replacement/"
    "challenger-replacement-economic-evaluation-plan-v0.74.0.json",
    "tests/test_challenger_replacement_economic_plan.py",
    "tests/test_challenger_replacement_v074_release.py",
    "docs/superpowers/specs/"
    "2026-08-25-replacement-v3-economic-preregistration-design.md",
    "docs/superpowers/plans/"
    "2026-08-25-replacement-v3-economic-preregistration.md",
    "docs/adr/0074-replacement-v3-economic-preregistration.md",
    "docs/implementation-status-v0.74.0.md",
)
FORBIDDEN_IMPORTS = {
    "requests", "urllib", "socket", "http", "websocket", "binance",
    "broker", "order", "credential", "install", "launchctl", "scheduler",
    "runner", "observer", "dashboard", "opportunity_events",
    "opportunity_projection", "simulation", "lifecycle",
}


def _read_frozen_v073_manifest_blob():
    try:
        completed = subprocess.run(
            (
                "git",
                "-C",
                str(ROOT),
                "show",
                f"{V073_PEELED_COMMIT}:{V073_MANIFEST_GIT_PATH}",
            ),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AssertionError(
            "frozen v0.73 manifest blob unavailable"
        ) from error
    return completed.stdout


def _packaged_schema_failure(error):
    if isinstance(error, SchemaError):
        return mock.patch.object(
            economic_plan.Draft202012Validator,
            "check_schema",
            side_effect=error,
        )

    class RaisingSchemaResource:
        def read_text(self, *, encoding):
            if encoding != "utf-8":
                raise AssertionError("unexpected Schema encoding")
            raise error

    class SchemaPackage:
        def joinpath(self, *parts):
            if parts != ("schemas", economic_plan._SCHEMA):
                raise AssertionError(f"unexpected Schema path: {parts!r}")
            return RaisingSchemaResource()

    return mock.patch.object(
        economic_plan.resources,
        "files",
        return_value=SchemaPackage(),
    )


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

    def test_schema_requires_the_ordered_final_result_reducer(self):
        """Catches a Schema that admits reordered or incomplete decision rules."""
        schema = json.loads(PACKAGE_SCHEMA.read_text())
        state_machine = self._definition(schema, "finalStateMachine")
        self.assertIn("decision_rules", state_machine["required"])
        rules = state_machine["properties"]["decision_rules"]
        self.assertEqual((rules["minItems"], rules["maxItems"]), (4, 4))
        self.assertIs(rules["items"], False)
        self.assertEqual(
            [item["properties"]["priority"]["const"] for item in rules["prefixItems"]],
            [1, 2, 3, 4],
        )
        self.assertEqual(
            [item["properties"]["result"]["const"] for item in rules["prefixItems"]],
            [
                "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
                "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                "RESEARCH_CONTINUATION_GATE_PASS",
            ],
        )
        self.assertEqual(
            [
                item["const"]
                for item in rules["prefixItems"][0]["properties"]["when_any"]
                ["prefixItems"]
            ],
            [
                "INVALID_PLAN", "IDENTITY_MISMATCH", "MALFORMED_EVENT",
                "DUPLICATE_AUTHORITY", "MISSING_TAIL_PRE_ACTION_MARK",
                "UNREADABLE_EVIDENCE",
            ],
        )

    def test_schema_requires_every_new_computation_contract_key(self):
        """Catches an optional or permissive tail, economic, sample, or miss rule."""
        schema = json.loads(PACKAGE_SCHEMA.read_text())
        expected_required = {
            "populationContract": {
                "tail_scheduled_for_base", "tail_scheduled_for_offset_seconds",
                "tail_pre_action_mark_source", "tail_action",
                "untrusted_tail_mark_input_allowed",
                "last_convenient_price_fallback_allowed",
                "missing_tail_mark_result",
            },
            "economicMeasurement": {
                "slippage_treatment", "marked_equity_calculation",
                "daily_boundary_construction", "daily_return_calculation",
                "maximum_drawdown_calculation", "stress_replay",
                "fixed_15_day_blocks",
            },
            "missingnessPolicy": {
                "confirmed_failure_boundaries", "confirmed_failure_result",
                "confirmed_failure_imputation_allowed",
                "confirmed_failure_repair_allowed", "flat_miss_included_in_population",
                "flat_miss_history_alteration_allowed", "flat_miss_notional_formula",
                "flat_miss_loss_rate_formula", "taker_fee_rate_selection",
                "flat_miss_funding_benefit_usdt",
                "charges_per_distinct_flat_missed_opportunity",
                "duplicate_flat_miss_charge_allowed", "observed_coverage_formula",
                "favorable_bound_selection_allowed",
            },
            "statisticalDesign": {
                "multiple_testing_adjustment", "resample_construction",
                "achieved_power_calculation", "completed_cycle_counting",
                "sample_gate_shortfall_result", "window_extension_allowed",
                "post_tail_evidence_changes_population",
            },
        }
        for definition_name, required in expected_required.items():
            with self.subTest(definition=definition_name):
                definition = self._definition(schema, definition_name)
                self.assertTrue(required.issubset(definition["required"]))
                self.assertTrue(required.issubset(definition["properties"]))

        nested_required = {
            "markedEquityCalculation": {
                "cash_coefficient", "conservative_marked_position_value_coefficient",
                "all_accrued_fees_coefficient",
                "signed_funding_cashflow_coefficient",
                "accounting_semantics_source",
            },
            "dailyBoundaryConstruction": {
                "kind", "offset_formula", "k_minimum", "k_maximum",
            },
            "dailyReturnCalculation": {
                "numerator", "fixed_capital_denominator_usdt",
                "intermediate_rounding_allowed", "canonical_output_encoder",
                "compounded", "annualized",
            },
            "maximumDrawdownCalculation": {
                "peak_source", "formula", "nonpositive_equity_result",
            },
            "stressReplay": {
                "nonnegative_fee_multiplier", "adverse_slippage_multiplier",
                "negative_funding_cashflow_multiplier",
                "positive_funding_benefit_multiplier", "unchanged_components",
                "unreconstructable_cost_result", "zero_cost_substitution_allowed",
            },
            "fixed15DayBlocks": {
                "count", "length_days", "interval", "start_formula", "end_formula",
                "n_values", "value_formula", "nonnegative_operator",
            },
            "resampleConstruction": {
                "block_selection", "within_block_order", "concatenation",
                "truncation_length", "lower_bound", "language_prng_allowed",
            },
            "achievedPowerCalculation": {
                "minimum_economic_effect_is_alternate_pass_threshold",
                "centered_error_formula", "critical_value", "comparison_left",
                "comparison_operator", "centered_error_count",
                "satisfying_error_aggregation", "result_formula",
                "result_denominator", "shortfall_result",
            },
            "completedCycleCounting": {
                "begins", "ends", "partial_fills_belong_to_matching_cycle",
                "partial_fills_create_additional_cycles",
                "retries_create_additional_cycles",
                "duplicate_observations_create_additional_cycles",
            },
        }
        for definition_name, required in nested_required.items():
            with self.subTest(definition=definition_name):
                definition = self._definition(schema, definition_name)
                self.assertEqual(set(definition["required"]), required)
                self.assertEqual(set(definition["properties"]), required)

    def test_schema_freezes_the_exact_tail_offset(self):
        """Catches a tail that is not start plus exactly 7,776,000 seconds."""
        schema = json.loads(PACKAGE_SCHEMA.read_text())
        population = self._definition(schema, "populationContract")["properties"]
        self.assertEqual(
            {
                "tail_scheduled_for_base": population["tail_scheduled_for_base"]["const"],
                "tail_scheduled_for_offset_seconds": population[
                    "tail_scheduled_for_offset_seconds"
                ]["const"],
            },
            {
                "tail_scheduled_for_base": "START_SCHEDULED_FOR",
                "tail_scheduled_for_offset_seconds": 7_776_000,
            },
        )

    def test_schema_freezes_grouped_coverage_and_block_end_formulas(self):
        """Catches formulas whose required addition grouping is ambiguous."""
        schema = json.loads(PACKAGE_SCHEMA.read_text())
        self.assertEqual(
            self._definition(schema, "missingnessPolicy")["properties"]
            ["observed_coverage_formula"]["const"],
            "OBSERVED_DIVIDED_BY_(OBSERVED_PLUS_MISSED)_IN_EXACT_HALF_OPEN_WINDOW",
        )
        self.assertEqual(
            self._definition(schema, "fixed15DayBlocks")["properties"]
            ["end_formula"]["const"],
            "START_SCHEDULED_FOR_PLUS_(N_PLUS_1)_TIMES_15_DAYS",
        )

    def test_schema_freezes_achieved_power_as_the_fraction_of_all_errors(self):
        """Catches a count/Boolean result or a fraction with another denominator."""
        schema = json.loads(PACKAGE_SCHEMA.read_text())
        achieved_power = self._definition(
            schema, "achievedPowerCalculation"
        )["properties"]
        self.assertEqual(
            {
                key: achieved_power[key]["const"]
                for key in (
                    "satisfying_error_aggregation", "result_formula",
                    "result_denominator",
                )
            },
            {
                "satisfying_error_aggregation": (
                    "COUNT_ALL_CENTERED_ERRORS_SATISFYING_COMPARISON"
                ),
                "result_formula": (
                    "SATISFYING_ERROR_AGGREGATION_DIVIDED_BY_RESULT_DENOMINATOR"
                ),
                "result_denominator": 10_000,
            },
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

    def test_foundation_uses_separate_exact_key_identity_schemas(self):
        """Catches a generic identity Schema that admits incomplete foundations."""
        schema = json.loads(PACKAGE_SCHEMA.read_text())
        foundation = self._definition(schema, "foundation")
        expected = {
            "v069_plan": ("v069PlanIdentity", {"file_sha256", "plan_id", "plan_hash"}),
            "v069_owner_attestation": (
                "v069OwnerAttestationIdentity",
                {"file_sha256", "attestation_id", "attestation_hash"},
            ),
            "v070_result_evidence_schema": (
                "v070ResultEvidenceSchemaIdentity",
                {"file_sha256"},
            ),
            "v071_simulation_contract": (
                "v071SimulationContractIdentity",
                {"file_sha256", "contract_id", "contract_hash"},
            ),
            "v072_golden_manifest": (
                "v072GoldenManifestIdentity",
                {"file_sha256", "manifest_id", "manifest_hash"},
            ),
            "v073_release": (
                "v073ReleaseIdentity",
                {
                    "release_tag", "peeled_commit", "package_version",
                    "manifest_version", "manifest_hash", "tree_hash",
                    "file_sha256",
                },
            ),
        }
        for member, (definition_name, keys) in expected.items():
            with self.subTest(member=member):
                self.assertEqual(
                    foundation["properties"][member],
                    {"$ref": f"#/$defs/{definition_name}"},
                )
                definition = self._definition(schema, definition_name)
                self.assertIs(definition["additionalProperties"], False)
                self.assertEqual(set(definition["required"]), keys)
                self.assertEqual(set(definition["properties"]), keys)


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
                    "attestation_id": "challenger_replacement_v3_owner_attestation_18626ea8f79c90f5924b50317635ce07c1c933879de42463f0e79095fb8e4388",
                    "attestation_hash": "99d99968eb5aa12bad064864d02aac4f37248a0fafb36d633c8c18315206fb21",
                },
                "v070_result_evidence_schema": {
                    "file_sha256": "755f4e049da22ab4300ce5ed68b73c0d9462581792b7b3955fff1712f6ca6dca",
                },
                "v071_simulation_contract": {
                    "file_sha256": "65a0af1cccee5ad60aeaa7b0266bb217fab680d866ea3191ca77d214a292d86f",
                    "contract_id": "challenger_replacement_simulation_contract_c95cee71f23e58cf40bc4739e5063824de1a77fd5c6fcc72794ff42e1f84f791",
                    "contract_hash": "b21beb877101590aabcc65927539d58eb001c4dc5de89ead0306ac840450f501",
                },
                "v072_golden_manifest": {
                    "file_sha256": "c86993a5d56805eee3b703301f92d704cf0e7dacd06d4725a7ad9c3c16dd2b5f",
                    "manifest_id": "challenger_replacement_binance_golden_fixture_manifest_b2ce1d97bd41c812a5f58907602519da7df8d4543e33298389f0e5232e5c1821",
                    "manifest_hash": "6977acff468689aeba64f1d814842c77ffa394f28bf686fdc82d02f5b61efbb4",
                },
                "v073_release": {
                    "release_tag": "v0.73.0",
                    "peeled_commit": "34bd0e9ba96c769b7301c482730a03fb975c24ce",
                    "package_version": "0.73.0",
                    "manifest_version": "1.67.0",
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
                "tail_scheduled_for_base": "START_SCHEDULED_FOR",
                "tail_scheduled_for_offset_seconds": 7_776_000,
                "window_kind": "HALF_OPEN_SCHEDULED_FOR_START_INCLUSIVE_TAIL_EXCLUSIVE",
                "terminal_outcomes": ["OBSERVED", "MISSED"],
                "historical_backfill_allowed": False, "window_reset_allowed": False,
                "alternate_start_allowed": False, "tail_pre_action_mark_required": True,
                "tail_pre_action_mark_source": "CANONICAL_SOURCE_AND_PRIOR_PROJECTION_AT_TAIL_SCHEDULED_FOR",
                "tail_action": "NO_NEW_ENTRY_OR_REVERSAL",
                "untrusted_tail_mark_input_allowed": False,
                "last_convenient_price_fallback_allowed": False,
                "missing_tail_mark_result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
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
                "slippage_treatment": "ADVERSE_COST_INCLUDED_ONCE_ONLY",
                "marked_equity_calculation": {
                    "cash_coefficient": "1",
                    "conservative_marked_position_value_coefficient": "1",
                    "all_accrued_fees_coefficient": "-1",
                    "signed_funding_cashflow_coefficient": "1",
                    "accounting_semantics_source": "V071_SIMULATION_CONTRACT_ACCOUNTING",
                },
                "daily_boundary_construction": {
                    "kind": "PRE_ACTION_UTC_ALIGNED",
                    "offset_formula": "START_SCHEDULED_FOR_PLUS_K_TIMES_86400_SECONDS",
                    "k_minimum": 0,
                    "k_maximum": 90,
                },
                "daily_return_calculation": {
                    "numerator": "BOUNDARY_EQUITY_K_MINUS_BOUNDARY_EQUITY_K_MINUS_1",
                    "fixed_capital_denominator_usdt": "100",
                    "intermediate_rounding_allowed": False,
                    "canonical_output_encoder": "REPOSITORY_DECIMAL_ENCODER",
                    "compounded": False,
                    "annualized": False,
                },
                "maximum_drawdown_calculation": {
                    "peak_source": "CONTINUOUS_HIGH_WATER_MARKED_EQUITY",
                    "formula": "(PEAK_MINUS_CURRENT)_DIVIDED_BY_PEAK",
                    "nonpositive_equity_result": "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
                },
                "stress_replay": {
                    "nonnegative_fee_multiplier": "1.5",
                    "adverse_slippage_multiplier": "1.5",
                    "negative_funding_cashflow_multiplier": "1.5",
                    "positive_funding_benefit_multiplier": "0.5",
                    "unchanged_components": [
                        "GROSS_MARKET_MOVEMENT", "QUANTITIES",
                        "PRODUCT_SELECTION", "EVENT_ORDER",
                    ],
                    "unreconstructable_cost_result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                    "zero_cost_substitution_allowed": False,
                },
                "fixed_15_day_blocks": {
                    "count": 6,
                    "length_days": 15,
                    "interval": "HALF_OPEN",
                    "start_formula": "START_SCHEDULED_FOR_PLUS_N_TIMES_15_DAYS",
                    "end_formula": "START_SCHEDULED_FOR_PLUS_(N_PLUS_1)_TIMES_15_DAYS",
                    "n_values": [0, 1, 2, 3, 4, 5],
                    "value_formula": "SUM_OF_DAILY_NET_RETURNS",
                    "nonnegative_operator": "GTE_ZERO",
                },
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
                "confirmed_failure_boundaries": [
                    "EXPOSED_MISSED", "UNRESOLVED_POSITION", "ECONOMIC_GAP_LOCK",
                    "UNRECORDED_FILL", "DUPLICATE_ECONOMIC_ORDER",
                    "RECONCILIATION_FAILURE",
                ],
                "confirmed_failure_result": "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
                "confirmed_failure_imputation_allowed": False,
                "confirmed_failure_repair_allowed": False,
                "flat_miss_included_in_population": True,
                "flat_miss_history_alteration_allowed": False,
                "flat_miss_notional_formula": "STARTING_VIRTUAL_EQUITY_USDT_TIMES_GROSS_EXPOSURE_LIMIT",
                "flat_miss_loss_rate_formula": "PROTECTIVE_STOP_DISTANCE_PLUS_2_TIMES_MARKET_SLIPPAGE_PER_SIDE_PLUS_2_TIMES_MAX_FROZEN_TAKER_FEE_PER_SIDE",
                "taker_fee_rate_selection": "MAX_FROZEN_SPOT_AND_PERPETUAL_TAKER_RATE",
                "flat_miss_funding_benefit_usdt": "0",
                "charges_per_distinct_flat_missed_opportunity": 1,
                "duplicate_flat_miss_charge_allowed": False,
                "observed_coverage_formula": "OBSERVED_DIVIDED_BY_(OBSERVED_PLUS_MISSED)_IN_EXACT_HALF_OPEN_WINDOW",
                "favorable_bound_selection_allowed": False,
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
                "multiple_testing_adjustment": "NONE_SINGLE_PRIMARY_HYPOTHESIS",
                "resample_construction": {
                    "block_selection": "UNIFORM_OVERLAPPING_SEVEN_DAY_BLOCKS",
                    "within_block_order": "ORIGINAL",
                    "concatenation": "CONCATENATE_SELECTED_BLOCKS",
                    "truncation_length": 90,
                    "lower_bound": "CONSERVATIVE_NEAREST_RANK_5TH_PERCENTILE_OF_10000_RESAMPLED_MEANS",
                    "language_prng_allowed": False,
                },
                "achieved_power_calculation": {
                    "minimum_economic_effect_is_alternate_pass_threshold": False,
                    "centered_error_formula": "BOOTSTRAP_MEAN_MINUS_OBSERVED_SAMPLE_MEAN",
                    "critical_value": "CONSERVATIVE_NEAREST_RANK_95TH_PERCENTILE_OF_CENTERED_ERRORS",
                    "comparison_left": "MINIMUM_ECONOMIC_EFFECT_DAILY_PLUS_CENTERED_ERROR",
                    "comparison_operator": "STRICT_GT_CRITICAL_VALUE",
                    "centered_error_count": 10_000,
                    "satisfying_error_aggregation": (
                        "COUNT_ALL_CENTERED_ERRORS_SATISFYING_COMPARISON"
                    ),
                    "result_formula": (
                        "SATISFYING_ERROR_AGGREGATION_DIVIDED_BY_RESULT_DENOMINATOR"
                    ),
                    "result_denominator": 10_000,
                    "shortfall_result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                },
                "completed_cycle_counting": {
                    "begins": "VERIFIED_FLAT_TO_EXPOSED_TRANSITION",
                    "ends": "MATCHING_VERIFIED_EXPOSED_TO_FLAT_TRANSITION",
                    "partial_fills_belong_to_matching_cycle": True,
                    "partial_fills_create_additional_cycles": False,
                    "retries_create_additional_cycles": False,
                    "duplicate_observations_create_additional_cycles": False,
                },
                "sample_gate_shortfall_result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                "window_extension_allowed": False,
                "post_tail_evidence_changes_population": False,
            },
            "final_state_machine": {
                "terminal_outcomes": TERMINAL_OUTCOMES,
                "decision_rules": [
                    {
                        "priority": 1,
                        "when_any": [
                            "INVALID_PLAN", "IDENTITY_MISMATCH",
                            "MALFORMED_EVENT", "DUPLICATE_AUTHORITY",
                            "MISSING_TAIL_PRE_ACTION_MARK", "UNREADABLE_EVIDENCE",
                        ],
                        "result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                        "research_continuation_discussion_eligible": False,
                    },
                    {
                        "priority": 2,
                        "when_any": [
                            "CONFIRMED_SAFETY_OR_RISK_BOUNDARY", "EXPOSED_MISSED",
                            "ECONOMIC_GAP_LOCK", "NONPOSITIVE_EQUITY",
                            "TRUSTED_SUFFICIENT_EVIDENCE_FAILS_ANY_ECONOMIC_GATE",
                        ],
                        "result": "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
                        "research_continuation_discussion_eligible": False,
                    },
                    {
                        "priority": 3,
                        "when_any": [
                            "TRUSTED_EVIDENCE_FAILS_ANY_SAMPLE_GATE",
                            "OPTIMISTIC_PESSIMISTIC_FLAT_MISS_BOUND_DISAGREEMENT",
                        ],
                        "result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                        "research_continuation_discussion_eligible": False,
                    },
                    {
                        "priority": 4,
                        "when_all": [
                            "TRUSTED_EVIDENCE", "SUFFICIENT_EVIDENCE",
                            "ALL_SAMPLE_GATES_PASS",
                            "ALL_ECONOMIC_GATES_PASS_UNDER_OPTIMISTIC_FLAT_MISS_BOUND",
                            "ALL_ECONOMIC_GATES_PASS_UNDER_PESSIMISTIC_FLAT_MISS_BOUND",
                        ],
                        "result": "RESEARCH_CONTINUATION_GATE_PASS",
                        "research_continuation_discussion_eligible": True,
                    },
                ],
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

    def test_builder_foundation_matches_immutable_checked_in_sources(self):
        """Catches guessed or stale object identities despite plausible file names."""
        foundation = build_challenger_replacement_economic_plan()["foundation"]
        source_expectations = (
            (
                FROZEN_PREDECESSOR_PATHS[0], "v069_plan",
                {"plan_id": "plan_id", "plan_hash": "plan_hash"},
            ),
            (
                FROZEN_PREDECESSOR_PATHS[1], "v069_owner_attestation",
                {"attestation_id": "attestation_id", "attestation_hash": "attestation_hash"},
            ),
            (
                FROZEN_PREDECESSOR_PATHS[3], "v071_simulation_contract",
                {"contract_id": "contract_id", "contract_hash": "contract_hash"},
            ),
            (
                FROZEN_PREDECESSOR_PATHS[4], "v072_golden_manifest",
                {"manifest_id": "manifest_id", "manifest_hash": "manifest_hash"},
            ),
        )
        for path, member, source_fields in source_expectations:
            with self.subTest(member=member):
                body = path.read_bytes()
                source = json.loads(body)
                self.assertEqual(
                    hashlib.sha256(body).hexdigest(),
                    foundation[member]["file_sha256"],
                )
                for source_field, identity_field in source_fields.items():
                    self.assertEqual(
                        source[source_field], foundation[member][identity_field]
                    )

        v070_body = FROZEN_PREDECESSOR_PATHS[2].read_bytes()
        self.assertEqual(
            hashlib.sha256(v070_body).hexdigest(),
            foundation["v070_result_evidence_schema"]["file_sha256"],
        )
        manifest_body = _read_frozen_v073_manifest_blob()
        manifest = json.loads(manifest_body)
        self.assertEqual(
            hashlib.sha256(manifest_body).hexdigest(),
            foundation["v073_release"]["file_sha256"],
        )
        self.assertEqual(
            {
                "package_version": manifest["package_version"],
                "manifest_version": manifest["manifest_version"],
                "manifest_hash": manifest["manifest_hash"],
                "tree_hash": manifest["build_input_tree_hash"],
            },
            {
                key: foundation["v073_release"][key]
                for key in (
                    "package_version", "manifest_version", "manifest_hash",
                    "tree_hash",
                )
            },
        )

    def test_v073_foundation_manifest_uses_exact_git_blob_and_fails_closed(self):
        """Catches mutable-path fallback or skipped historical authority."""
        reader = globals().get("_read_frozen_v073_manifest_blob")
        self.assertIsNotNone(
            reader,
            "v0.73 foundation must have an exact peeled-commit blob reader",
        )
        body = reader()
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "c41a46442993bac947773d383f722dfbaa358417ba67e87bf1e81db37c5e1c74",
        )
        manifest = json.loads(body)
        self.assertEqual(
            (
                manifest["package_version"],
                manifest["manifest_version"],
                manifest["manifest_hash"],
                manifest["build_input_tree_hash"],
            ),
            (
                "0.73.0",
                "1.67.0",
                "0117d3a17bdea7e2a22004d675175083e9d863722c6c176632d29e3c4c6e62d0",
                "569afbae2352932a05a6c5daeb1c52049c9a3ec74034d666664579aa2bd0a97e",
            ),
        )
        with mock.patch.object(
            subprocess,
            "run",
            side_effect=OSError("git unavailable"),
        ):
            with self.assertRaisesRegex(
                AssertionError,
                "frozen v0.73 manifest blob unavailable",
            ):
                reader()

    def test_builder_freezes_the_ordered_final_result_reducer(self):
        """Catches a changed precedence, condition class, or terminal result."""
        self.assertEqual(
            build_challenger_replacement_economic_plan()["final_state_machine"]
            ["decision_rules"],
            [
                {
                    "priority": 1,
                    "when_any": [
                        "INVALID_PLAN", "IDENTITY_MISMATCH",
                        "MALFORMED_EVENT", "DUPLICATE_AUTHORITY",
                        "MISSING_TAIL_PRE_ACTION_MARK", "UNREADABLE_EVIDENCE",
                    ],
                    "result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                    "research_continuation_discussion_eligible": False,
                },
                {
                    "priority": 2,
                    "when_any": [
                        "CONFIRMED_SAFETY_OR_RISK_BOUNDARY", "EXPOSED_MISSED",
                        "ECONOMIC_GAP_LOCK", "NONPOSITIVE_EQUITY",
                        "TRUSTED_SUFFICIENT_EVIDENCE_FAILS_ANY_ECONOMIC_GATE",
                    ],
                    "result": "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
                    "research_continuation_discussion_eligible": False,
                },
                {
                    "priority": 3,
                    "when_any": [
                        "TRUSTED_EVIDENCE_FAILS_ANY_SAMPLE_GATE",
                        "OPTIMISTIC_PESSIMISTIC_FLAT_MISS_BOUND_DISAGREEMENT",
                    ],
                    "result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                    "research_continuation_discussion_eligible": False,
                },
                {
                    "priority": 4,
                    "when_all": [
                        "TRUSTED_EVIDENCE", "SUFFICIENT_EVIDENCE",
                        "ALL_SAMPLE_GATES_PASS",
                        "ALL_ECONOMIC_GATES_PASS_UNDER_OPTIMISTIC_FLAT_MISS_BOUND",
                        "ALL_ECONOMIC_GATES_PASS_UNDER_PESSIMISTIC_FLAT_MISS_BOUND",
                    ],
                    "result": "RESEARCH_CONTINUATION_GATE_PASS",
                    "research_continuation_discussion_eligible": True,
                },
            ],
        )

    def test_builder_freezes_tail_and_economic_gate_calculations(self):
        """Catches omitted tail-mark, drawdown, stress, or fixed-block semantics."""
        plan = build_challenger_replacement_economic_plan()
        self.assertEqual(
            {
                key: plan["population_contract"][key]
                for key in (
                    "tail_scheduled_for_base",
                    "tail_scheduled_for_offset_seconds",
                    "tail_pre_action_mark_source", "tail_action",
                    "untrusted_tail_mark_input_allowed",
                    "last_convenient_price_fallback_allowed",
                    "missing_tail_mark_result",
                )
            },
            {
                "tail_scheduled_for_base": "START_SCHEDULED_FOR",
                "tail_scheduled_for_offset_seconds": 7_776_000,
                "tail_pre_action_mark_source": "CANONICAL_SOURCE_AND_PRIOR_PROJECTION_AT_TAIL_SCHEDULED_FOR",
                "tail_action": "NO_NEW_ENTRY_OR_REVERSAL",
                "untrusted_tail_mark_input_allowed": False,
                "last_convenient_price_fallback_allowed": False,
                "missing_tail_mark_result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
            },
        )
        self.assertEqual(
            plan["economic_measurement"]["maximum_drawdown_calculation"],
            {
                "peak_source": "CONTINUOUS_HIGH_WATER_MARKED_EQUITY",
                "formula": "(PEAK_MINUS_CURRENT)_DIVIDED_BY_PEAK",
                "nonpositive_equity_result": "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
            },
        )
        self.assertEqual(
            plan["economic_measurement"]["stress_replay"],
            {
                "nonnegative_fee_multiplier": "1.5",
                "adverse_slippage_multiplier": "1.5",
                "negative_funding_cashflow_multiplier": "1.5",
                "positive_funding_benefit_multiplier": "0.5",
                "unchanged_components": [
                    "GROSS_MARKET_MOVEMENT", "QUANTITIES",
                    "PRODUCT_SELECTION", "EVENT_ORDER",
                ],
                "unreconstructable_cost_result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                "zero_cost_substitution_allowed": False,
            },
        )
        self.assertEqual(
            plan["economic_measurement"]["fixed_15_day_blocks"],
            {
                "count": 6,
                "length_days": 15,
                "interval": "HALF_OPEN",
                "start_formula": "START_SCHEDULED_FOR_PLUS_N_TIMES_15_DAYS",
                "end_formula": "START_SCHEDULED_FOR_PLUS_(N_PLUS_1)_TIMES_15_DAYS",
                "n_values": [0, 1, 2, 3, 4, 5],
                "value_formula": "SUM_OF_DAILY_NET_RETURNS",
                "nonnegative_operator": "GTE_ZERO",
            },
        )

    def test_builder_freezes_the_grouped_fixed_block_end_formula(self):
        """Catches treating the block end as start + n + (1 * 15 days)."""
        self.assertEqual(
            build_challenger_replacement_economic_plan()["economic_measurement"]
            ["fixed_15_day_blocks"]["end_formula"],
            "START_SCHEDULED_FOR_PLUS_(N_PLUS_1)_TIMES_15_DAYS",
        )

    def test_builder_freezes_flat_miss_failure_and_counting_rules(self):
        """Catches omitted failure, greater-fee, zero-funding, or charge-once rules."""
        missingness = build_challenger_replacement_economic_plan()[
            "missingness_policy"
        ]
        self.assertEqual(
            missingness["confirmed_failure_boundaries"],
            [
                "EXPOSED_MISSED", "UNRESOLVED_POSITION", "ECONOMIC_GAP_LOCK",
                "UNRECORDED_FILL", "DUPLICATE_ECONOMIC_ORDER",
                "RECONCILIATION_FAILURE",
            ],
        )
        self.assertEqual(
            {
                key: missingness[key]
                for key in (
                    "taker_fee_rate_selection",
                    "flat_miss_funding_benefit_usdt",
                    "charges_per_distinct_flat_missed_opportunity",
                    "duplicate_flat_miss_charge_allowed",
                    "observed_coverage_formula",
                    "favorable_bound_selection_allowed",
                )
            },
            {
                "taker_fee_rate_selection": "MAX_FROZEN_SPOT_AND_PERPETUAL_TAKER_RATE",
                "flat_miss_funding_benefit_usdt": "0",
                "charges_per_distinct_flat_missed_opportunity": 1,
                "duplicate_flat_miss_charge_allowed": False,
                "observed_coverage_formula": "OBSERVED_DIVIDED_BY_(OBSERVED_PLUS_MISSED)_IN_EXACT_HALF_OPEN_WINDOW",
                "favorable_bound_selection_allowed": False,
            },
        )

    def test_builder_freezes_bootstrap_power_and_cycle_counting_rules(self):
        """Catches altered centering, rank, strict comparison, or cycle counts."""
        design = build_challenger_replacement_economic_plan()["statistical_design"]
        self.assertEqual(
            design["achieved_power_calculation"],
            {
                "minimum_economic_effect_is_alternate_pass_threshold": False,
                "centered_error_formula": "BOOTSTRAP_MEAN_MINUS_OBSERVED_SAMPLE_MEAN",
                "critical_value": "CONSERVATIVE_NEAREST_RANK_95TH_PERCENTILE_OF_CENTERED_ERRORS",
                "comparison_left": "MINIMUM_ECONOMIC_EFFECT_DAILY_PLUS_CENTERED_ERROR",
                "comparison_operator": "STRICT_GT_CRITICAL_VALUE",
                "centered_error_count": 10_000,
                "satisfying_error_aggregation": (
                    "COUNT_ALL_CENTERED_ERRORS_SATISFYING_COMPARISON"
                ),
                "result_formula": (
                    "SATISFYING_ERROR_AGGREGATION_DIVIDED_BY_RESULT_DENOMINATOR"
                ),
                "result_denominator": 10_000,
                "shortfall_result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
            },
        )
        self.assertEqual(
            design["completed_cycle_counting"],
            {
                "begins": "VERIFIED_FLAT_TO_EXPOSED_TRANSITION",
                "ends": "MATCHING_VERIFIED_EXPOSED_TO_FLAT_TRANSITION",
                "partial_fills_belong_to_matching_cycle": True,
                "partial_fills_create_additional_cycles": False,
                "retries_create_additional_cycles": False,
                "duplicate_observations_create_additional_cycles": False,
            },
        )

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

    def test_builder_reduces_packaged_schema_failures_to_a_public_error(self):
        """Catches raw Schema I/O, construction, or recursion errors from builder."""
        for error in (
            OSError("schema unavailable"),
            SchemaError("schema invalid"),
            RecursionError("schema recursion"),
        ):
            with self.subTest(error=type(error).__name__):
                economic_plan._validator.cache_clear()
                try:
                    with _packaged_schema_failure(error):
                        with self.assertRaises(
                            ChallengerReplacementEconomicPlanError
                        ) as raised:
                            build_challenger_replacement_economic_plan()
                    self.assertEqual(raised.exception.reason_code, SCHEMA_INVALID_REASON)
                finally:
                    economic_plan._validator.cache_clear()


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

    def test_loader_accepts_only_exact_canonical_plus_lf_bytes(self):
        """Catches optional-LF acceptance for a distinct byte identity."""
        self._write(self._canonical_plan_bytes() + b"\n")
        self.assertEqual(
            load_challenger_replacement_economic_plan(self.path),
            build_challenger_replacement_economic_plan(),
        )

        self._write(self._canonical_plan_bytes())
        with self.assertRaises(
            ChallengerReplacementEconomicPlanError
        ) as raised:
            load_challenger_replacement_economic_plan(self.path)
        self.assertEqual(
            raised.exception.reason_code,
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_CANONICAL_BYTES_REQUIRED",
        )

    def test_loader_requires_the_literal_committed_artifact_sha256(self):
        """Catches canonical alternate content that is not the committed authority."""
        self.assertEqual(economic_plan._ARTIFACT_SHA256, ARTIFACT_SHA256)
        mutated = build_challenger_replacement_economic_plan()
        mutated["warnings"][0] = "MUTATED_BUT_CANONICAL"
        mutated["plan_hash"] = challenger_replacement_economic_plan_hash(mutated)
        self._write(canonical_json(mutated).encode("utf-8") + b"\n")
        with self.assertRaises(
            ChallengerReplacementEconomicPlanError
        ) as raised:
            load_challenger_replacement_economic_plan(self.path)
        self.assertEqual(
            raised.exception.reason_code,
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_FILE_SHA256_MISMATCH",
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

    def test_loader_reduces_packaged_schema_failures_to_a_public_error(self):
        """Catches raw Schema I/O, construction, or recursion errors from loader."""
        self._write(self._canonical_plan_bytes() + b"\n")
        for error in (
            OSError("schema unavailable"),
            SchemaError("schema invalid"),
            RecursionError("schema recursion"),
        ):
            with self.subTest(error=type(error).__name__):
                economic_plan._validator.cache_clear()
                try:
                    with _packaged_schema_failure(error):
                        with self.assertRaises(
                            ChallengerReplacementEconomicPlanError
                        ) as raised:
                            load_challenger_replacement_economic_plan(self.path)
                    self.assertEqual(raised.exception.reason_code, SCHEMA_INVALID_REASON)
                finally:
                    economic_plan._validator.cache_clear()


class EconomicPlanArtifactTests(unittest.TestCase):
    """The committed preregistration is exact builder output and authority."""

    def test_artifact_is_exact_canonical_builder_bytes_and_strictly_replays(self):
        """Catches a missing, hand-edited, or non-replayable formal plan file."""
        predecessor_bytes = {
            path: path.read_bytes() for path in FROZEN_PREDECESSOR_PATHS
        }
        self.assertTrue(ARTIFACT_PATH.is_file())
        expected = canonical_json(
            build_challenger_replacement_economic_plan()
        ).encode("utf-8") + b"\n"
        self.assertEqual(ARTIFACT_PATH.read_bytes(), expected)
        self.assertEqual(
            load_challenger_replacement_economic_plan(ARTIFACT_PATH),
            build_challenger_replacement_economic_plan(),
        )
        for path, before in predecessor_bytes.items():
            with self.subTest(path=path.name):
                self.assertEqual(path.read_bytes(), before)

    def test_artifact_has_the_frozen_literal_sha256(self):
        """Catches a changed future authority artifact even if it still parses."""
        self.assertTrue(ARTIFACT_PATH.is_file())
        self.assertRegex(ARTIFACT_SHA256, r"^[0-9a-f]{64}$")
        self.assertNotEqual(ARTIFACT_SHA256, "0" * 64)
        self.assertEqual(
            hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest(),
            ARTIFACT_SHA256,
        )

    def test_artifact_has_frozen_literal_plan_and_policy_identities(self):
        """Catches a rehashed plan that silently changes formal authority."""
        artifact = json.loads(ARTIFACT_PATH.read_bytes())
        built = build_challenger_replacement_economic_plan()
        for plan in (artifact, built):
            self.assertEqual(plan["plan_id"], PLAN_ID)
            self.assertEqual(plan["plan_hash"], PLAN_HASH)
            self.assertEqual(
                {
                    section: plan[section]["policy_hash"]
                    for section in POLICY_HASHES
                },
                POLICY_HASHES,
            )


class EconomicPlanAuthorityTests(unittest.TestCase):
    """The preregistration remains a plan-only, deterministic boundary."""

    def test_module_has_no_forbidden_imports(self):
        """Catches an import that could grant runtime, network, or outcome authority."""
        tree = ast.parse(Path(economic_plan.__file__).read_text(encoding="utf-8"))
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_names.add(node.module or "")
                imported_names.update(alias.name for alias in node.names)
        for forbidden in FORBIDDEN_IMPORTS:
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    any(forbidden in imported for imported in imported_names),
                    msg=f"forbidden import: {forbidden}",
                )

    def test_builder_reads_only_the_package_schema_without_side_effects(self):
        """Catches builder access to artifacts, events, production, processes, or networks."""
        schema_text = PACKAGE_SCHEMA.read_text(encoding="utf-8")
        resource_calls = []
        test_case = self

        class SchemaResource:
            def read_text(self, *, encoding):
                test_case.assertEqual(encoding, "utf-8")
                return schema_text

        class SchemaPackage:
            def joinpath(self, *parts):
                resource_calls.append(parts)
                return SchemaResource()

        def fail_boundary(*_args, **_kwargs):
            raise AssertionError("unexpected side effect")

        economic_plan._validator.cache_clear()
        try:
            with (
                mock.patch.object(
                    economic_plan.resources,
                    "files",
                    return_value=SchemaPackage(),
                ) as resource_files,
                mock.patch("builtins.open", side_effect=fail_boundary),
                mock.patch.object(Path, "open", side_effect=fail_boundary),
                mock.patch.object(Path, "read_bytes", side_effect=fail_boundary),
                mock.patch.object(Path, "read_text", side_effect=fail_boundary),
                mock.patch.object(Path, "write_bytes", side_effect=fail_boundary),
                mock.patch.object(Path, "write_text", side_effect=fail_boundary),
                mock.patch("os.system", side_effect=fail_boundary),
                mock.patch("os.popen", side_effect=fail_boundary),
                mock.patch("subprocess.run", side_effect=fail_boundary),
                mock.patch("subprocess.call", side_effect=fail_boundary),
                mock.patch("subprocess.check_call", side_effect=fail_boundary),
                mock.patch("subprocess.check_output", side_effect=fail_boundary),
                mock.patch("subprocess.Popen", side_effect=fail_boundary),
                mock.patch("socket.socket", side_effect=fail_boundary),
                mock.patch("socket.create_connection", side_effect=fail_boundary),
                mock.patch("urllib.request.urlopen", side_effect=fail_boundary),
                mock.patch("http.client.HTTPConnection", side_effect=fail_boundary),
                mock.patch("http.client.HTTPSConnection", side_effect=fail_boundary),
            ):
                plan = build_challenger_replacement_economic_plan()
        finally:
            economic_plan._validator.cache_clear()

        self.assertEqual(plan["authority"], AUTHORITY_CONSTS)
        resource_files.assert_called_once_with("crypto_quant")
        self.assertEqual(resource_calls, [("schemas", economic_plan._SCHEMA)])

    def test_evaluator_build_inventory_covers_the_v074_formal_inputs(self):
        """Catches a formal v0.74 input omitted from deterministic build coverage."""
        self.assertEqual(build._V074_RELEASE_PATHS, V074_RELEASE_PATHS)
        self.assertTrue(
            V074_INVENTORY_PATHS.issubset(EvaluatorBuild.expected_file_paths(ROOT)),
            msg="v0.74 formal inputs missing from evaluator build inventory",
        )


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

    def test_reasons_reduce_packaged_schema_failures_to_a_public_reason(self):
        """Catches raw or misclassified Schema boundary failures from reasons."""
        plan = build_challenger_replacement_economic_plan()
        for error in (
            OSError("schema unavailable"),
            SchemaError("schema invalid"),
            RecursionError("schema recursion"),
        ):
            with self.subTest(error=type(error).__name__):
                economic_plan._validator.cache_clear()
                try:
                    with _packaged_schema_failure(error):
                        self.assertEqual(
                            challenger_replacement_economic_plan_reasons(plan),
                            (SCHEMA_INVALID_REASON,),
                        )
                finally:
                    economic_plan._validator.cache_clear()


if __name__ == "__main__":
    unittest.main()
