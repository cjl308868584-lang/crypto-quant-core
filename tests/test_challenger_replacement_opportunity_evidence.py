import copy
import inspect
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json, stable_id
from crypto_quant.challenger_replacement_binance_lifecycle import (
    simulate_challenger_replacement_binance_lifecycle,
)
from crypto_quant.challenger_replacement_binance_simulation_input import (
    load_challenger_replacement_binance_simulation_input_bytes,
)
from crypto_quant.challenger_replacement_opportunity_evidence import (
    ChallengerReplacementOpportunityEvidenceError,
    build_challenger_replacement_fixture_result_evidence,
    build_challenger_replacement_simulation_result_evidence,
    load_challenger_replacement_fixture_result_evidence_bytes,
    load_challenger_replacement_simulation_result_evidence_bytes,
)
from crypto_quant.challenger_replacement_simulation import (
    build_challenger_replacement_genesis_snapshot,
)
from crypto_quant.evidence import artifact_self_hash
from tests.challenger_replacement_v3_fixtures import (
    DEFAULT_OBSERVED_AT,
    DEFAULT_SCHEDULED_FOR,
    fixture_opportunity_id,
    fixture_v071_contract,
    fixture_v071_signal_bars,
    fixture_v072_build_identity,
    fixture_v072_input_bytes,
    fixture_v3_plan,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "config" / (
    "challenger-replacement-opportunity-result-evidence-v1.schema.json"
)
PACKAGE_SCHEMA = ROOT / "src" / "crypto_quant" / "schemas" / (
    "challenger-replacement-opportunity-result-evidence-v1.schema.json"
)
CONFIG_SCHEMA_V2 = ROOT / "config" / (
    "challenger-replacement-opportunity-result-evidence-v2.schema.json"
)
PACKAGE_SCHEMA_V2 = ROOT / "src" / "crypto_quant" / "schemas" / (
    "challenger-replacement-opportunity-result-evidence-v2.schema.json"
)
SOURCE_HASH = "a" * 64
DECISION_HASH = "b" * 64


def _kwargs():
    return {
        "opportunity_id": fixture_opportunity_id(),
        "scheduled_for": DEFAULT_SCHEDULED_FOR,
        "observed_at": DEFAULT_OBSERVED_AT,
        "source_bundle_sha256": SOURCE_HASH,
        "decision_sha256": DECISION_HASH,
    }


def _bytes(document):
    return canonical_json(document).encode("utf-8")


class OpportunityEvidenceSchemaTests(unittest.TestCase):
    def test_schema_mirrors_are_exact_and_valid(self):
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        schema = json.loads(CONFIG_SCHEMA.read_text())
        Draft202012Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["properties"]["authority"]["additionalProperties"])

    def test_v2_schema_mirrors_are_exact_strict_and_valid(self):
        self.assertEqual(CONFIG_SCHEMA_V2.read_bytes(), PACKAGE_SCHEMA_V2.read_bytes())
        schema = json.loads(CONFIG_SCHEMA_V2.read_text())
        Draft202012Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            {
                "$schema", "schema_version", "mode", "result_id", "result_hash",
                "evidence_qualification", "plan", "simulation_contract",
                "build_identity", "opportunity", "source", "decision",
                "previous_snapshot", "risk", "lifecycle", "accounting",
                "next_snapshot", "authority",
            },
        )
        self.assertFalse(schema["$defs"]["authority"]["additionalProperties"])


class OpportunityEvidenceTests(unittest.TestCase):
    def test_builder_and_loader_replay_exact_fixture_binding(self):
        document = build_challenger_replacement_fixture_result_evidence(
            **_kwargs()
        )
        self.assertEqual(
            document,
            {
                "$schema": (
                    "./challenger-replacement-opportunity-"
                    "result-evidence-v1.schema.json"
                ),
                "schema_version": "1.0.0",
                "mode": "FIXTURE_ONLY_NO_BROKER_NO_ORDER",
                **_kwargs(),
                "authority": {
                    "network_requests": 0,
                    "broker_requests": 0,
                    "orders": 0,
                    "credentials_used": False,
                    "production_state_writes": 0,
                },
            },
        )
        body = _bytes(document)
        self.assertEqual(
            load_challenger_replacement_fixture_result_evidence_bytes(
                body, **_kwargs()
            ),
            document,
        )
        self.assertEqual(_bytes(document), body)

    def test_every_authority_count_is_zero_and_credentials_are_false(self):
        document = build_challenger_replacement_fixture_result_evidence(
            **_kwargs()
        )
        self.assertEqual(set(document["authority"].values()), {0, False})
        self.assertIs(document["authority"]["credentials_used"], False)

    def test_loader_rejects_binding_and_authority_mutations(self):
        original = build_challenger_replacement_fixture_result_evidence(
            **_kwargs()
        )
        changes = (
            ("opportunity_id", "ETHUSDT@2026-08-24T04:00:00.000Z"),
            ("scheduled_for", "2026-08-24T04:00:00.000Z"),
            ("observed_at", "2026-08-24T00:06:00.000Z"),
            ("source_bundle_sha256", "c" * 64),
            ("decision_sha256", "d" * 64),
            ("mode", "PRODUCTION"),
            ("schema_version", "2.0.0"),
        )
        for key, value in changes:
            with self.subTest(key=key):
                changed = copy.deepcopy(original)
                changed[key] = value
                with self.assertRaises(
                    ChallengerReplacementOpportunityEvidenceError
                ):
                    load_challenger_replacement_fixture_result_evidence_bytes(
                        _bytes(changed), **_kwargs()
                    )
        for key, value in (
            ("network_requests", 1),
            ("broker_requests", 1),
            ("orders", 1),
            ("credentials_used", True),
            ("production_state_writes", 1),
        ):
            with self.subTest(authority=key):
                changed = copy.deepcopy(original)
                changed["authority"][key] = value
                with self.assertRaises(
                    ChallengerReplacementOpportunityEvidenceError
                ):
                    load_challenger_replacement_fixture_result_evidence_bytes(
                        _bytes(changed), **_kwargs()
                    )

    def test_loader_rejects_unknown_missing_and_malformed_fields(self):
        original = build_challenger_replacement_fixture_result_evidence(
            **_kwargs()
        )
        changed = copy.deepcopy(original)
        changed["unknown"] = "value"
        missing = copy.deepcopy(original)
        del missing["decision_sha256"]
        malformed = copy.deepcopy(original)
        malformed["decision_sha256"] = "not-a-hash"
        for document in (changed, missing, malformed):
            with self.assertRaises(
                ChallengerReplacementOpportunityEvidenceError
            ):
                load_challenger_replacement_fixture_result_evidence_bytes(
                    _bytes(document), **_kwargs()
                )


class OpportunityEvidenceV2Tests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture_v3_plan()
        self.contract = fixture_v071_contract()
        self.build_identity = fixture_v072_build_identity()
        source = load_challenger_replacement_binance_simulation_input_bytes(
            fixture_v072_input_bytes(bars=fixture_v071_signal_bars("LONG")),
            plan=self.plan,
            contract=self.contract,
            build_identity=self.build_identity,
            opportunity_id=fixture_opportunity_id(),
        )
        self.result = simulate_challenger_replacement_binance_lifecycle(
            source=source,
            previous_projection=build_challenger_replacement_genesis_snapshot(
                plan=self.plan, contract=self.contract
            ),
            plan=self.plan,
            contract=self.contract,
            build_identity=self.build_identity,
        )

    def build(self):
        return build_challenger_replacement_simulation_result_evidence(
            lifecycle_result=self.result
        )

    def load(self, document=None, **overrides):
        values = {
            "plan": self.plan,
            "contract": self.contract,
            "build_identity": self.build_identity,
        }
        values.update(overrides)
        return load_challenger_replacement_simulation_result_evidence_bytes(
            _bytes(self.build() if document is None else document), **values
        )

    def test_builder_has_one_typed_input_and_no_caller_economic_seams(self):
        self.assertEqual(
            tuple(inspect.signature(
                build_challenger_replacement_simulation_result_evidence
            ).parameters),
            ("lifecycle_result",),
        )

    def test_builder_and_loader_bind_complete_lifecycle_result(self):
        document = self.build()
        source = json.loads(self.result.source_bytes)
        decision = json.loads(self.result.decision_bytes)
        self.assertEqual(
            set(document),
            {
                "$schema", "schema_version", "mode", "result_id", "result_hash",
                "evidence_qualification", "plan", "simulation_contract",
                "build_identity", "opportunity", "source", "decision",
                "previous_snapshot", "risk", "lifecycle", "accounting",
                "next_snapshot", "authority",
            },
        )
        self.assertEqual(document["schema_version"], "2.0.0")
        self.assertEqual(
            document["mode"],
            "FIXTURE_SIMULATION_NO_NETWORK_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER",
        )
        self.assertEqual(
            document["evidence_qualification"],
            "COMMITTED_FIXTURE_NOT_LIVE_MARKET_OR_ACCOUNT",
        )
        self.assertEqual(document["plan"], json.loads(self.result.plan_identity_bytes))
        self.assertEqual(
            document["simulation_contract"],
            json.loads(self.result.contract_identity_bytes),
        )
        self.assertEqual(document["build_identity"], self.build_identity)
        self.assertEqual(document["opportunity"], source["opportunity"])
        self.assertEqual(
            document["source"],
            {"input_id": source["input_id"], "input_hash": source["input_hash"]},
        )
        self.assertEqual(document["decision"], decision)
        self.assertEqual(document["risk"], {
            "approval": decision["risk_approval"],
            "reason_code": decision["reason_code"],
        })
        self.assertEqual(document["lifecycle"]["status"], "RECONCILED_FIXTURE")
        self.assertTrue(document["lifecycle"]["operationally_complete"])
        self.assertIsNone(document["lifecycle"]["reason_code_or_null"])
        self.assertEqual(len(document["lifecycle"]["events"]), 8)
        self.assertEqual(document["result_hash"], artifact_self_hash(document, "result_hash"))
        self.assertEqual(
            document["result_id"],
            stable_id("challenger_replacement_simulation_result", {
                "plan": document["plan"],
                "simulation_contract": document["simulation_contract"],
                "opportunity": document["opportunity"],
                "source": document["source"],
                "decision_hash": document["decision"]["decision_hash"],
                "previous_snapshot_hash": document["previous_snapshot"]["snapshot_hash"],
            }),
        )
        self.assertEqual(self.load(document), document)

    def test_loader_rejects_context_identity_and_derived_mutations(self):
        original = self.build()
        cases = []
        unknown = copy.deepcopy(original); unknown["unknown"] = 1; cases.append(unknown)
        wrong_id = copy.deepcopy(original); wrong_id["result_id"] = "x"; cases.append(wrong_id)
        bad_parent = copy.deepcopy(original)
        bad_parent["lifecycle"]["events"][1]["parent_event_hash_or_null"] = "0" * 64
        cases.append(bad_parent)
        bad_decimal = copy.deepcopy(original); bad_decimal["accounting"]["fee"] = "01.0"; cases.append(bad_decimal)
        bad_authority = copy.deepcopy(original); bad_authority["authority"]["orders_submitted_to_venue"] = 1; cases.append(bad_authority)
        for document in cases:
            with self.subTest(keys=document.keys()):
                with self.assertRaises(ChallengerReplacementOpportunityEvidenceError):
                    self.load(document)
        wrong_build = copy.deepcopy(self.build_identity)
        wrong_build["manifest_hash"] = "0" * 64
        with self.assertRaises(ChallengerReplacementOpportunityEvidenceError):
            self.load(build_identity=wrong_build)

    def test_loader_rejects_unknown_event_payload_even_with_rehashed_chain(self):
        document = self.build()
        document["lifecycle"]["events"][0]["payload"]["unknown"] = "value"
        parent = None
        for event in document["lifecycle"]["events"]:
            event["parent_event_hash_or_null"] = parent
            event["event_hash"] = artifact_self_hash(event, "event_hash")
            parent = event["event_hash"]
        document["result_hash"] = artifact_self_hash(document, "result_hash")
        with self.assertRaises(ChallengerReplacementOpportunityEvidenceError):
            self.load(document)

    def test_loader_rejects_invalid_bytes_before_or_during_parse(self):
        original = self.build()
        duplicate = _bytes(original).replace(
            b'{"$schema":', b'{"schema_version":"2.0.0","$schema":', 1
        )
        with_float = _bytes(original).replace(
            b'"network_requests":0', b'"network_requests":0.0'
        )
        unsafe = _bytes(original).replace(
            b'"network_requests":0', b'"network_requests":9007199254740992'
        )
        for body in (b"", b"x" * (1024 * 1024 + 1), duplicate, with_float, unsafe):
            with self.subTest(size=len(body)):
                with self.assertRaises(ChallengerReplacementOpportunityEvidenceError):
                    load_challenger_replacement_simulation_result_evidence_bytes(
                        body,
                        plan=self.plan,
                        contract=self.contract,
                        build_identity=self.build_identity,
                    )


class OpportunityEvidenceTestsContinued(unittest.TestCase):
    def test_loader_rejects_noncanonical_duplicate_and_json_numbers(self):
        document = build_challenger_replacement_fixture_result_evidence(
            **_kwargs()
        )
        pretty = json.dumps(document, indent=2).encode("utf-8")
        duplicate = (
            b'{"$schema":"x","$schema":"y"}'
        )
        with_float = _bytes(document).replace(
            b'"network_requests":0', b'"network_requests":0.0'
        )
        for body in (pretty, duplicate, with_float, b"", b"[]"):
            with self.subTest(body=body[:30]):
                with self.assertRaises(
                    ChallengerReplacementOpportunityEvidenceError
                ):
                    load_challenger_replacement_fixture_result_evidence_bytes(
                        body, **_kwargs()
                    )

    def test_builder_rejects_invalid_inputs(self):
        for key, value in (
            ("opportunity_id", ""),
            ("scheduled_for", "not-time"),
            ("observed_at", "not-time"),
            ("source_bundle_sha256", "A" * 64),
            ("decision_sha256", None),
        ):
            with self.subTest(key=key):
                arguments = _kwargs()
                arguments[key] = value
                with self.assertRaises(
                    ChallengerReplacementOpportunityEvidenceError
                ):
                    build_challenger_replacement_fixture_result_evidence(
                        **arguments
                    )

    def test_builder_requires_closed_capture_window(self):
        for observed_at in (
            "2026-08-24T00:01:59.999Z",
            "2026-08-24T00:10:00.001Z",
        ):
            with self.subTest(observed_at=observed_at):
                arguments = _kwargs()
                arguments["observed_at"] = observed_at
                with self.assertRaises(
                    ChallengerReplacementOpportunityEvidenceError
                ):
                    build_challenger_replacement_fixture_result_evidence(
                        **arguments
                    )
        for observed_at in (
            "2026-08-24T00:02:00.000Z",
            "2026-08-24T00:10:00.000Z",
        ):
            with self.subTest(observed_at=observed_at):
                arguments = _kwargs()
                arguments["observed_at"] = observed_at
                self.assertEqual(
                    build_challenger_replacement_fixture_result_evidence(
                        **arguments
                    )["observed_at"],
                    observed_at,
                )


if __name__ == "__main__":
    unittest.main()
