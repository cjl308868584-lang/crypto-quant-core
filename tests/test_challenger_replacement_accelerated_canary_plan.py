import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/crypto_quant/schemas/"
    "challenger-replacement-accelerated-canary-plan-v1.schema.json"
)
EXPECTED_KEYS = {
    "$schema",
    "schema_version",
    "plan_id",
    "plan_hash",
    "foundation",
    "supersession_scope",
    "projection_contract",
    "code_complete_program",
    "simulation_qualification",
    "operational_ceremony",
    "hard_stop_policy",
    "canary_ladder",
    "credential_boundary",
    "approval_ledger",
    "authority",
    "status",
    "warnings",
}


def _object_schemas(value):
    if isinstance(value, dict):
        if value.get("type") == "object":
            yield value
        for child in value.values():
            yield from _object_schemas(child)
    elif isinstance(value, list):
        for child in value:
            yield from _object_schemas(child)


class AcceleratedCanaryPlanSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text())

    def test_schema_is_draft_202012_and_exact_key(self):
        Draft202012Validator.check_schema(self.schema)
        self.assertEqual(
            self.schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(set(self.schema["required"]), EXPECTED_KEYS)
        self.assertEqual(set(self.schema["properties"]), EXPECTED_KEYS)

    def test_every_object_is_exact_key(self):
        objects = tuple(_object_schemas(self.schema))
        self.assertGreater(len(objects), 15)
        for schema in objects:
            self.assertIs(
                schema.get("additionalProperties"),
                False,
                msg=schema.get("title", schema),
            )
            self.assertEqual(
                set(schema.get("required", ())),
                set(schema.get("properties", ())),
                msg=schema.get("title", schema),
            )

    def test_schema_freezes_accelerated_boundaries(self):
        properties = self.schema["properties"]
        self.assertEqual(
            properties["status"]["const"],
            "ACCELERATED_CANARY_PLAN_PREREGISTERED_NOT_ACTIVATED",
        )
        simulation = properties["simulation_qualification"]["properties"]
        self.assertEqual(simulation["minimum_continuous_seconds"]["const"], 259_200)
        self.assertEqual(simulation["cadence_seconds"]["const"], 14_400)
        ceremony = properties["operational_ceremony"]["properties"]
        self.assertEqual(
            ceremony["label"]["const"],
            "OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE",
        )
        hard_stops = properties["hard_stop_policy"]["properties"][
            "absolute_classes"
        ]
        self.assertFalse(hard_stops["items"])
        self.assertEqual(
            [item["const"] for item in hard_stops["prefixItems"]],
            [
                "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN",
                "VENUE_LOCAL_POSITION_MISMATCH",
                "PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP",
                "RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT",
            ],
        )

    def test_schema_freezes_all_authority_false_or_zero(self):
        authority = self.schema["properties"]["authority"]["properties"]
        false_keys = {
            "production_activation",
            "runtime_install_authorized",
            "replacement_start_authorized",
            "credentials_allowed",
            "account_requests_allowed",
            "broker_requests_allowed",
            "real_orders_allowed",
            "fund_movement_allowed",
            "ceremony_authorized",
            "e0_activation_authorized",
        }
        zero_keys = {
            "market_requests",
            "private_account_requests",
            "production_state_writes",
            "economic_outcome_reads",
        }
        self.assertEqual(set(authority), false_keys | zero_keys)
        for key in false_keys:
            self.assertIs(authority[key]["const"], False)
        for key in zero_keys:
            self.assertEqual(authority[key]["const"], 0)


if __name__ == "__main__":
    unittest.main()
