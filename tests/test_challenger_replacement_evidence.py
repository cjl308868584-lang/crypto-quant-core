import json
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.challenger_replacement_evidence import (
    ChallengerReplacementEvidenceError,
    build_challenger_replacement_source_bundle,
    load_challenger_replacement_source_bundle_bytes,
)
from tests.challenger_replacement_v2_fixtures import (
    fixture_build_identity, fixture_capture, fixture_plan,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_SOURCE = ROOT / "config/challenger-replacement-source-bundle-v1.schema.json"
PACKAGE_SOURCE = ROOT / "src/crypto_quant/schemas/challenger-replacement-source-bundle-v1.schema.json"
CONFIG_DECISION = ROOT / "config/challenger-replacement-decision-v1.schema.json"
PACKAGE_DECISION = ROOT / "src/crypto_quant/schemas/challenger-replacement-decision-v1.schema.json"


class SourceBundleTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture_plan()
        self.build = fixture_build_identity()

    def _genesis(self):
        return build_challenger_replacement_source_bundle(
            plan=self.plan, capture=fixture_capture(), observed_at="2026-08-22T04:05:00.000Z",
            build_identity=self.build, previous_source_bundle=None, previous_decision=None)

    def test_schemas_are_exact_mirrors_and_validate(self):
        self.assertEqual(CONFIG_SOURCE.read_bytes(), PACKAGE_SOURCE.read_bytes())
        self.assertEqual(CONFIG_DECISION.read_bytes(), PACKAGE_DECISION.read_bytes())
        Draft202012Validator.check_schema(json.loads(CONFIG_SOURCE.read_text()))
        Draft202012Validator.check_schema(json.loads(CONFIG_DECISION.read_text()))
        Draft202012Validator(json.loads(CONFIG_SOURCE.read_text())).validate(self._genesis())

    def test_genesis_is_deterministic_and_v2_bound(self):
        first = self._genesis()
        self.assertEqual(canonical_json(first), canonical_json(self._genesis()))
        self.assertEqual(first["plan"], {"plan_id": self.plan["plan_id"], "plan_hash": self.plan["plan_hash"]})
        self.assertEqual(first["build_identity"], self.build)
        self.assertIsNone(first["parents"]["previous_decision_hash_or_null"])

    def test_bytes_loader_rejects_noncanonical_duplicate_float_tamper_and_wrong_binding(self):
        source = self._genesis()
        data = canonical_json(source).encode("utf-8")
        self.assertEqual(load_challenger_replacement_source_bundle_bytes(
            data, plan=self.plan, build_identity=self.build,
            previous_source_bundle=None, previous_decision=None), source)
        bad_inputs = [
            b" " + data,
            data.replace(b'"schema_version"', b'"schema_version":"x","schema_version"', 1),
            data.replace(b'"sequence":1', b'"sequence":1.0', 1),
            data.replace(b'"bundle_hash":"', b'"bundle_hash":"f', 1),
        ]
        for bad in bad_inputs:
            with self.subTest(bad=bad[:30]), self.assertRaises(ChallengerReplacementEvidenceError):
                load_challenger_replacement_source_bundle_bytes(
                    bad, plan=self.plan, build_identity=self.build,
                    previous_source_bundle=None, previous_decision=None)
        wrong_build = dict(self.build, manifest_hash="e" * 64)
        with self.assertRaises(ChallengerReplacementEvidenceError):
            load_challenger_replacement_source_bundle_bytes(
                data, plan=self.plan, build_identity=wrong_build,
                previous_source_bundle=None, previous_decision=None)

    def test_successor_requires_four_hours_twenty_bar_overlap_and_parents(self):
        from crypto_quant.challenger_replacement_decision import build_challenger_replacement_decision
        first = self._genesis()
        decision = build_challenger_replacement_decision(
            plan=self.plan, source_bundle=first,
            recorded_at=first["slot"]["captured_at"], previous_decision=None)
        capture = fixture_capture(sequence=2, scheduled_for="2026-08-22T08:00:00.000Z",
                                  captured_at="2026-08-22T08:05:00.000Z", latest="102")
        capture["klines"] = deepcopy(first["klines"][1:]) + [capture["klines"][-1]]
        second = build_challenger_replacement_source_bundle(
            plan=self.plan, capture=capture, observed_at=capture["captured_at"],
            build_identity=self.build, previous_source_bundle=first, previous_decision=decision)
        self.assertEqual(second["slot"]["sequence"], 2)
        self.assertEqual(second["klines"][:20], first["klines"][1:])
        revised = deepcopy(capture)
        revised["klines"][0]["close"] = "999"
        row_body = dict(revised["klines"][0]); row_body.pop("source_row_hash")
        revised["klines"][0]["source_row_hash"] = business_hash(row_body)
        with self.assertRaises(ChallengerReplacementEvidenceError):
            build_challenger_replacement_source_bundle(
                plan=self.plan, capture=revised, observed_at=revised["captured_at"],
                build_identity=self.build, previous_source_bundle=first, previous_decision=decision)
        self.assertEqual(load_challenger_replacement_source_bundle_bytes(
            canonical_json(second).encode("utf-8"), plan=self.plan,
            build_identity=self.build, previous_source_bundle=first,
            previous_decision=decision), second)

        skipped = deepcopy(capture)
        skipped["scheduled_for"] = "2026-08-22T12:00:00.000Z"
        with self.assertRaises(ChallengerReplacementEvidenceError):
            build_challenger_replacement_source_bundle(
                plan=self.plan, capture=skipped, observed_at=skipped["captured_at"],
                build_identity=self.build, previous_source_bundle=first,
                previous_decision=decision)


if __name__ == "__main__":
    unittest.main()
