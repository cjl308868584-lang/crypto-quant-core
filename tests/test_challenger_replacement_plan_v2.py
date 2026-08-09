import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.challenger_replacement_plan import (
    load_challenger_replacement_plan,
)


ROOT = Path(__file__).resolve().parents[1]
V1_PATH = (
    ROOT
    / "artifacts"
    / "challenger-replacement"
    / "challenger-replacement-plan-v0.62.0.json"
)
V1_FILE_SHA256 = "d450d1e9f8dc422eb5a93beb8a5ffbb1746a4a6d1facb3c5a20a76f4bd527734"
V1_PLAN_ID = "challenger_replacement_plan_d4a542c1566f7a90466ca4d5301b81847f5b5eba93c7a00903d2d95331bc23a2"
V1_PLAN_HASH = "95f395b17d9c09d325c58391542ce5f3d9df5ce6a706b1bba8ffcb62dc6c883c"
V1_PEELED_COMMIT = "e0a9b3eb6a3f385ea259722e6613df8708e8fe5a"
V1_BYTES_BEFORE_TESTS = V1_PATH.read_bytes()

CONFIG_SCHEMA_PATH = ROOT / "config" / "challenger-replacement-plan-v2.schema.json"
PACKAGE_SCHEMA_PATH = (
    ROOT
    / "src"
    / "crypto_quant"
    / "schemas"
    / "challenger-replacement-plan-v2.schema.json"
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
    "cohort_policy",
    "isolation_policy",
    "evidence_policy",
    "storage_authority",
    "supersession",
    "authority",
    "status",
    "eligibility",
    "warnings",
}

EXPECTED_RELATIVE_PATHS = {
    "state_events": "state/challenger-replacement-events-v1",
    "non_authoritative_exports": "exports",
    "stdout": "log/challenger-replacement.stdout.log",
    "stderr": "log/challenger-replacement.stderr.log",
    "deployment_contract": "deployment/contract.json",
    "deployment_plist": "deployment/local.crypto-quant.challenger-replacement-v1.plist",
    "preflight_receipts": "preflight-receipts",
    "install_receipts": "install-receipts",
    "start_receipts": "start-receipts",
    "episode_receipts": "episode-receipts",
    "archives": "archives",
    "results": "results",
    "indexes": "indexes",
    "evaluations": "evaluations",
}

EXPECTED_STORAGE_AUTHORITY = {
    "authoritative_state_kind": "APPEND_ONLY_CANONICAL_EVENT_LOG",
    "authoritative_relative_path": "state/challenger-replacement-events-v1",
    "runner_authority_source": "CANONICAL_EVENT_LOG_ONLY",
    "observer_authority_source": "STRICT_EVENT_PROJECTION_ONLY",
    "evaluator_authority_source": "STRICT_EVENT_PROJECTION_ONLY",
    "exports_authoritative": False,
    "exports_required_for_slot_success": False,
    "exports_required_for_evaluation": False,
    "exports_reconstructible": True,
    "source_bundle_export_subdirectory": "source-bundles",
    "decision_export_subdirectory": "decisions",
}

EXPECTED_SUPERSESSION = {
    "previous_plan_release_tag": "v0.62.0",
    "previous_plan_peeled_commit": V1_PEELED_COMMIT,
    "previous_plan_path": (
        "artifacts/challenger-replacement/"
        "challenger-replacement-plan-v0.62.0.json"
    ),
    "previous_plan_file_sha256": V1_FILE_SHA256,
    "previous_plan_id": V1_PLAN_ID,
    "previous_plan_hash": V1_PLAN_HASH,
    "reason": "SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION",
    "previous_plan_state": "PLAN_FROZEN_REPLACEMENT_NOT_STARTED",
    "previous_plan_disposition": "SUPERSEDED_BEFORE_START_NO_COHORT_EVIDENCE",
    "supersession_forbidden_after": "FIRST_START_RECEIPT_OR_CANONICAL_EVENT",
}

EXPECTED_WARNINGS = [
    "OLD_COHORT_PERMANENTLY_FAILED_NO_BACKFILL",
    "REPLACEMENT_RUNTIME_NOT_IMPLEMENTED",
    "REPLACEMENT_NOT_INSTALLED_OR_STARTED",
    "NO_INTERIM_ECONOMIC_REPORTING",
    "NO_PROFITABILITY_OR_AI_ADVANTAGE_CLAIM",
    "CANARY_NOT_AUTHORIZED",
    "V0_62_SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION",
]


def _const_object(schema):
    return {
        key: value["const"]
        for key, value in schema["properties"].items()
        if "const" in value
    }


class ChallengerReplacementPlanV1ImmutableSourceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        if V1_PATH.read_bytes() != V1_BYTES_BEFORE_TESTS:
            raise AssertionError("v0.62 plan bytes changed during v2 schema tests")

    def test_v1_committed_source_identity_and_loader_replay_are_exact(self):
        self.assertEqual(
            hashlib.sha256(V1_BYTES_BEFORE_TESTS).hexdigest(),
            V1_FILE_SHA256,
        )
        raw = json.loads(V1_BYTES_BEFORE_TESTS)
        self.assertEqual(raw["plan_id"], V1_PLAN_ID)
        self.assertEqual(raw["plan_hash"], V1_PLAN_HASH)
        self.assertEqual(load_challenger_replacement_plan(V1_PATH), raw)


class ChallengerReplacementPlanV2SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config_bytes = CONFIG_SCHEMA_PATH.read_bytes()
        cls.package_bytes = PACKAGE_SCHEMA_PATH.read_bytes()
        cls.schema = json.loads(cls.config_bytes)

    def test_schema_mirrors_and_top_level_contract_are_exact(self):
        self.assertEqual(self.config_bytes, self.package_bytes)
        Draft202012Validator.check_schema(self.schema)
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(set(self.schema["required"]), EXPECTED_TOP_LEVEL_KEYS)
        self.assertEqual(set(self.schema["properties"]), EXPECTED_TOP_LEVEL_KEYS)
        self.assertEqual(
            self.schema["properties"]["$schema"]["const"],
            "./challenger-replacement-plan-v2.schema.json",
        )
        self.assertEqual(self.schema["properties"]["schema_version"]["const"], "2.0.0")
        self.assertEqual(
            self.schema["properties"]["status"]["const"],
            "PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED",
        )

    def test_relative_paths_replace_all_three_unsafe_v1_keys(self):
        relative_schema = self.schema["properties"]["isolation_policy"]["properties"][
            "relative_paths"
        ]
        self.assertFalse(relative_schema["additionalProperties"])
        self.assertEqual(set(relative_schema["required"]), set(EXPECTED_RELATIVE_PATHS))
        self.assertEqual(_const_object(relative_schema), EXPECTED_RELATIVE_PATHS)
        self.assertFalse(list(Draft202012Validator(relative_schema).iter_errors(EXPECTED_RELATIVE_PATHS)))

        for old_key in ("state", "source_bundles", "decisions"):
            candidate = dict(EXPECTED_RELATIVE_PATHS)
            candidate[old_key] = "forbidden"
            self.assertTrue(
                list(Draft202012Validator(relative_schema).iter_errors(candidate)),
                old_key,
            )
            self.assertNotIn(old_key, relative_schema["properties"])

    def test_storage_authority_and_supersession_are_closed_exact_objects(self):
        storage_schema = self.schema["properties"]["storage_authority"]
        self.assertFalse(storage_schema["additionalProperties"])
        self.assertEqual(
            set(storage_schema["required"]),
            set(EXPECTED_STORAGE_AUTHORITY) | {"policy_hash"},
        )
        self.assertEqual(_const_object(storage_schema), EXPECTED_STORAGE_AUTHORITY)
        self.assertEqual(storage_schema["properties"]["policy_hash"], {"$ref": "#/$defs/hash"})

        supersession_schema = self.schema["properties"]["supersession"]
        self.assertFalse(supersession_schema["additionalProperties"])
        self.assertEqual(set(supersession_schema["required"]), set(EXPECTED_SUPERSESSION))
        self.assertEqual(_const_object(supersession_schema), EXPECTED_SUPERSESSION)

    def test_foundation_warnings_and_every_object_boundary_are_frozen(self):
        self.assertEqual(
            _const_object(self.schema["properties"]["foundation"]),
            {
                "release_tag": "v0.63.0",
                "peeled_commit": "df91e19240df14839125608422489adf3b902e76",
                "package_version": "0.63.0",
                "manifest_version": "1.57.0",
                "build_input_tree_hash": "7fdfd6c69f1342892b222882b76ee4988487a482c958a9cdacf00461b2fd8f19",
                "manifest_hash": "f4a74896a6d7b2166adba86075ef06b8d7986f900a086d04ee2f03754baded4b",
                "manifest_file_sha256": "13bea4bfcf633e767eed73d431e57d496dcee47820aacf92e7b61b0efed5c546",
            },
        )
        self.assertEqual(self.schema["properties"]["warnings"]["const"], EXPECTED_WARNINGS)

        pending = [self.schema]
        while pending:
            node = pending.pop()
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False, node)
                pending.extend(node.values())
            elif isinstance(node, list):
                pending.extend(node)
