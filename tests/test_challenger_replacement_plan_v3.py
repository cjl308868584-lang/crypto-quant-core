import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.challenger_replacement_plan_v2 import (
    load_challenger_replacement_plan_v2,
)


ROOT = Path(__file__).resolve().parents[1]
V2_PATH = (
    ROOT
    / "artifacts"
    / "challenger-replacement"
    / "challenger-replacement-plan-v0.64.0.json"
)
V2_FILE_SHA256 = "5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f"
V2_PLAN_ID = (
    "challenger_replacement_plan_"
    "65d85d60a534a917f45a1ffa5fc9d3f74d6d24995b900d31b8c73cd26f0bd97b"
)
V2_PLAN_HASH = "c9a1e5f74c52fbf23be5a1d27fd23c25f3601ed58133178fc25480391ab65705"
V2_BYTES_BEFORE_TESTS = V2_PATH.read_bytes()

CONFIG_SCHEMA_PATH = ROOT / "config" / "challenger-replacement-plan-v3.schema.json"
PACKAGE_SCHEMA_PATH = (
    ROOT
    / "src"
    / "crypto_quant"
    / "schemas"
    / "challenger-replacement-plan-v3.schema.json"
)

EXPECTED_TOP_LEVEL_KEYS = {
    "$schema",
    "schema_version",
    "plan_id",
    "plan_hash",
    "foundation",
    "predecessor",
    "scope",
    "decision_policy",
    "opportunity_policy",
    "operational_qualification",
    "economic_evidence",
    "canary_ladder",
    "product_policy",
    "risk_policy",
    "isolation_policy",
    "evidence_policy",
    "storage_authority",
    "supersession",
    "authority",
    "status",
    "eligibility",
    "warnings",
}

EXPECTED_AUTHORITY = {
    "credentials_allowed": False,
    "account_requests_allowed": False,
    "broker_requests_allowed": False,
    "real_orders_allowed": False,
    "production_activation": False,
    "runtime_install_authorized": False,
    "replacement_start_authorized": False,
}


def _const_object(schema):
    return {
        key: value["const"]
        for key, value in schema["properties"].items()
        if "const" in value
    }


def _walk_object_schemas(value, path="$"):
    if isinstance(value, dict):
        if value.get("type") == "object":
            yield path, value
        for key, child in value.items():
            yield from _walk_object_schemas(child, f"{path}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_object_schemas(child, f"{path}/{index}")


class ChallengerReplacementPlanV3PredecessorTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        if V2_PATH.read_bytes() != V2_BYTES_BEFORE_TESTS:
            raise AssertionError("v0.64 plan bytes changed during v3 schema tests")

    def test_v064_plan_identity_and_loader_replay_remain_exact(self):
        self.assertEqual(
            hashlib.sha256(V2_BYTES_BEFORE_TESTS).hexdigest(),
            V2_FILE_SHA256,
        )
        raw = json.loads(V2_BYTES_BEFORE_TESTS)
        self.assertEqual(raw["plan_id"], V2_PLAN_ID)
        self.assertEqual(raw["plan_hash"], V2_PLAN_HASH)
        self.assertEqual(load_challenger_replacement_plan_v2(V2_PATH), raw)


class ChallengerReplacementPlanV3SchemaTests(unittest.TestCase):
    def _schema(self):
        config_bytes = CONFIG_SCHEMA_PATH.read_bytes()
        self.assertEqual(config_bytes, PACKAGE_SCHEMA_PATH.read_bytes())
        schema = json.loads(config_bytes)
        Draft202012Validator.check_schema(schema)
        return schema

    def test_schema_mirrors_are_valid_and_freeze_the_top_level_contract(self):
        schema = self._schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), EXPECTED_TOP_LEVEL_KEYS)
        self.assertEqual(set(schema["properties"]), EXPECTED_TOP_LEVEL_KEYS)

    def test_every_declared_object_schema_rejects_unknown_keys(self):
        missing = [
            path
            for path, candidate in _walk_object_schemas(self._schema())
            if candidate.get("additionalProperties") is not False
        ]
        self.assertEqual(missing, [])

    def test_schema_freezes_decision_opportunity_and_dual_track_boundaries(self):
        properties = self._schema()["properties"]
        self.assertEqual(
            _const_object(properties["opportunity_policy"]),
            {
                "cadence_seconds": 14400,
                "capture_open_offset_seconds": 120,
                "capture_close_offset_seconds": 600,
                "terminal_outcomes": ["OBSERVED", "MISSED"],
                "historical_decision_backfill_allowed": False,
                "missed_opportunity_recovery": (
                    "APPEND_MISSED_WITH_ACTUAL_DETECTION_TIME"
                ),
            },
        )
        missed = properties["opportunity_policy"]["properties"][
            "missed_reason_codes"
        ]
        self.assertEqual(
            [item["const"] for item in missed["prefixItems"]],
            [
                "PROCESS_NOT_RUNNING",
                "CAPTURE_WINDOW_EXPIRED",
                "PUBLIC_MARKET_SOURCE_UNAVAILABLE",
                "CLOCK_OR_CONNECTIVITY_UNTRUSTED",
                "PRECONDITION_FAILED_CLOSED",
            ],
        )
        self.assertFalse(missed["items"])
        self.assertEqual(
            _const_object(properties["operational_qualification"])[
                "minimum_calendar_days"
            ],
            7,
        )
        self.assertEqual(
            _const_object(properties["operational_qualification"])[
                "minimum_observed_coverage"
            ],
            "0.95",
        )
        self.assertEqual(
            _const_object(properties["economic_evidence"])[
                "minimum_calendar_days"
            ],
            90,
        )
        self.assertFalse(
            _const_object(properties["economic_evidence"])[
                "interim_profitability_pass_allowed"
            ]
        )

    def test_schema_freezes_canary_product_risk_and_disabled_authority(self):
        properties = self._schema()["properties"]
        ladder = properties["canary_ladder"]["properties"]
        self.assertEqual(
            _const_object(ladder["E0"]),
            {
                "capital_limit_usdt": "100",
                "gross_exposure_limit": "0.5",
                "minimum_calendar_days": 7,
                "minimum_strategy_cycles": 3,
            },
        )
        self.assertEqual(
            _const_object(ladder["E1"]),
            {
                "capital_limit_usdt": "300",
                "gross_exposure_limit": "1",
                "minimum_calendar_days": 14,
                "minimum_strategy_cycles": 5,
            },
        )
        self.assertEqual(
            _const_object(ladder["E2"]),
            {
                "capital_limit_usdt": "1000",
                "gross_exposure_limit": "2",
                "minimum_calendar_days": 30,
                "minimum_strategy_cycles": 10,
            },
        )
        self.assertTrue(ladder["spot_roundtrip_each_stage_required"]["const"])
        self.assertTrue(
            ladder["perpetual_roundtrip_each_stage_required"]["const"]
        )
        product = _const_object(properties["product_policy"])
        self.assertEqual(product["venue"], "BINANCE_ONLY")
        self.assertEqual(product["position_states"], ["FLAT", "SPOT_LONG", "PERP_SHORT"])
        self.assertTrue(product["flatten_before_reversal_required"])
        self.assertEqual(product["perpetual_position_mode"], "ONE_WAY")
        self.assertEqual(product["perpetual_margin_mode"], "ISOLATED")
        self.assertEqual(product["technical_leverage_cap"], "2")
        self.assertEqual(_const_object(properties["authority"]), EXPECTED_AUTHORITY)
