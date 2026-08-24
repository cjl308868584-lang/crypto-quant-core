import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_opportunity_evidence import (
    ChallengerReplacementOpportunityEvidenceError,
    build_challenger_replacement_fixture_result_evidence,
    load_challenger_replacement_fixture_result_evidence_bytes,
)
from tests.challenger_replacement_v3_fixtures import (
    DEFAULT_OBSERVED_AT,
    DEFAULT_SCHEDULED_FOR,
    fixture_opportunity_id,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "config" / (
    "challenger-replacement-opportunity-result-evidence-v1.schema.json"
)
PACKAGE_SCHEMA = ROOT / "src" / "crypto_quant" / "schemas" / (
    "challenger-replacement-opportunity-result-evidence-v1.schema.json"
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
