import json
import re
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_decimal
from crypto_quant.errors import CanonicalizationError


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


if __name__ == "__main__":
    unittest.main()
