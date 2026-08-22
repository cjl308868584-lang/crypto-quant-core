import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.evidence import artifact_self_hash
from crypto_quant import challenger_replacement_decision as decision_module
from crypto_quant import challenger_replacement_evidence as evidence_module
from crypto_quant.challenger_replacement_live_input import (
    ChallengerReplacementLiveCapture,
)
from tests import test_challenger_replacement_live_input as live_fixture_module
from tests import challenger_replacement_v2_fixtures as replacement_fixtures


class LiveDocumentTests(unittest.TestCase):
    def setUp(self):
        acquisition = live_fixture_module.LiveAcquisitionTests()
        acquisition.setUp()
        self.plan = acquisition.plan
        self.build_identity = acquisition.build_identity
        self.live_capture = acquisition._acquire_with(
            live_fixture_module._TimeTransport().responses
            + [acquisition._kline_response()]
        )

    def _source_and_decision(self):
        source = evidence_module.build_challenger_replacement_cohort_source_bundle(
            plan=self.plan,
            build_identity=self.build_identity,
            live_capture=self.live_capture,
            previous_source_bundle=None,
            previous_decision=None,
        )
        decision = decision_module.build_challenger_replacement_cohort_decision(
            plan=self.plan,
            source_bundle=source,
            recorded_at=source["slot"]["captured_at"],
            previous_decision=None,
        )
        return source, decision

    def test_cohort_source_and_decision_bind_exact_live_capture(self):
        source = evidence_module.build_challenger_replacement_cohort_source_bundle(
            plan=self.plan,
            build_identity=self.build_identity,
            live_capture=self.live_capture,
            previous_source_bundle=None,
            previous_decision=None,
        )
        self.assertEqual(
            source["evidence_qualification"],
            "REPLACEMENT_CONFIRMATORY_COHORT_EVIDENCE",
        )
        self.assertEqual(source["live_capture_receipt"], self.live_capture.document)
        self.assertEqual(source["network_request_count_observed_by_core_runtime"], 0)
        self.assertEqual(
            source["klines"], self.live_capture.document["rows"]
        )
        self.assertEqual(
            source["$schema"], "./challenger-replacement-source-bundle-v2.schema.json"
        )

        decision = decision_module.build_challenger_replacement_cohort_decision(
            plan=self.plan,
            source_bundle=source,
            recorded_at=source["slot"]["captured_at"],
            previous_decision=None,
        )
        self.assertEqual(
            decision["evidence_qualification"],
            "REPLACEMENT_CONFIRMATORY_COHORT_EVIDENCE",
        )
        self.assertEqual(
            decision["$schema"], "./challenger-replacement-decision-v2.schema.json"
        )
        self.assertEqual(decision["parents"]["current_source_bundle_hash"], source["bundle_hash"])

    def test_cohort_source_requires_adapter_derived_capability(self):
        self.assertIsInstance(self.live_capture, ChallengerReplacementLiveCapture)
        with self.assertRaises(ValueError):
            evidence_module.build_challenger_replacement_cohort_source_bundle(
                plan=self.plan,
                build_identity=self.build_identity,
                live_capture=self.live_capture.document,
                previous_source_bundle=None,
                previous_decision=None,
            )

    def test_v2_schemas_are_valid_exact_mirrors(self):
        root = Path(__file__).resolve().parents[1]
        for name in (
            "challenger-replacement-source-bundle-v2.schema.json",
            "challenger-replacement-decision-v2.schema.json",
        ):
            config = root / "config" / name
            package = root / "src/crypto_quant/schemas" / name
            self.assertEqual(config.read_bytes(), package.read_bytes())
            Draft202012Validator.check_schema(json.loads(config.read_text()))

        source, decision = self._source_and_decision()
        cases = (
            ("challenger-replacement-source-bundle-v2.schema.json", source, "plan"),
            ("challenger-replacement-source-bundle-v2.schema.json", source, "build_identity"),
            ("challenger-replacement-source-bundle-v2.schema.json", source, "slot"),
            ("challenger-replacement-source-bundle-v2.schema.json", source, "parents"),
            ("challenger-replacement-source-bundle-v2.schema.json", source, "authority"),
            ("challenger-replacement-decision-v2.schema.json", decision, "features"),
            ("challenger-replacement-decision-v2.schema.json", decision, "state_after"),
            ("challenger-replacement-decision-v2.schema.json", decision, "authority"),
        )
        for name, document, field in cases:
            schema = json.loads((root / "config" / name).read_text())
            validator = Draft202012Validator(schema)
            changed = deepcopy(document)
            changed[field]["unexpected"] = True
            with self.subTest(schema=name, field=field):
                self.assertTrue(list(validator.iter_errors(changed)))

    def test_v2_bytes_loaders_replay_and_reject_receipt_revision(self):
        source, decision = self._source_and_decision()
        loaded_source = evidence_module.load_challenger_replacement_cohort_source_bundle_bytes(
            canonical_json(source).encode("utf-8"),
            plan=self.plan,
            build_identity=self.build_identity,
            previous_source_bundle=None,
            previous_decision=None,
        )
        loaded_decision = decision_module.load_challenger_replacement_cohort_decision_bytes(
            canonical_json(decision).encode("utf-8"),
            plan=self.plan,
            source_bundle=loaded_source,
            previous_decision=None,
        )
        self.assertEqual((loaded_source, loaded_decision), (source, decision))

        revised = deepcopy(source)
        revised["live_capture_receipt"]["rows"][0]["close"] = "99"
        revised["live_capture_receipt"]["capture_hash"] = artifact_self_hash(
            revised["live_capture_receipt"], "capture_hash"
        )
        revised["bundle_hash"] = artifact_self_hash(revised, "bundle_hash")
        with self.assertRaises(ValueError):
            evidence_module.load_challenger_replacement_cohort_source_bundle_bytes(
                canonical_json(revised).encode("utf-8"),
                plan=self.plan,
                build_identity=self.build_identity,
                previous_source_bundle=None,
                previous_decision=None,
            )

    def test_second_slot_requires_exact_parent_and_twenty_bar_overlap(self):
        source, decision = self._source_and_decision()
        scheduled = datetime(2026, 8, 22, 8, 0, tzinfo=timezone.utc)
        next_rows = deepcopy(source["klines"][1:])
        next_rows.append(
            live_fixture_module.fixture_klines(
                scheduled_for="2026-08-22T08:00:00.000Z", latest="102"
            )[-1]
        )
        acquisition = live_fixture_module.LiveAcquisitionTests()
        acquisition.setUp()
        acquisition.state.projection.update(
            completed_slot_count=1,
            next_required_slot={
                "sequence": 2,
                "scheduled_for": "2026-08-22T08:00:00.000Z",
            },
            _previous_source_bundle=source,
            _previous_decision=decision,
        )
        second_capture = acquisition._acquire_with(
            live_fixture_module._TimeTransport(
                datetime(2026, 8, 22, 8, 4, tzinfo=timezone.utc)
            ).responses
            + [
                acquisition._kline_response(
                    scheduled=scheduled,
                    body=live_fixture_module._raw_kline_body(next_rows),
                )
            ],
            wall=datetime(2026, 8, 22, 8, 4, 2, 500000, tzinfo=timezone.utc),
        )
        second_source = evidence_module.build_challenger_replacement_cohort_source_bundle(
            plan=self.plan,
            build_identity=self.build_identity,
            live_capture=second_capture,
            previous_source_bundle=source,
            previous_decision=decision,
        )
        second_decision = decision_module.build_challenger_replacement_cohort_decision(
            plan=self.plan,
            source_bundle=second_source,
            recorded_at=second_source["slot"]["captured_at"],
            previous_decision=decision,
        )
        self.assertEqual(second_source["klines"][:20], source["klines"][1:])
        self.assertEqual(
            second_source["parents"],
            {
                "previous_source_bundle_hash": source["bundle_hash"],
                "previous_decision_hash_or_null": decision["decision_hash"],
            },
        )
        self.assertEqual(
            second_decision["parents"]["previous_decision_hash_or_null"],
            decision["decision_hash"],
        )
        self.assertEqual(
            evidence_module.load_challenger_replacement_cohort_source_bundle_bytes(
                canonical_json(second_source).encode("utf-8"),
                plan=self.plan,
                build_identity=self.build_identity,
                previous_source_bundle=source,
                previous_decision=decision,
            ),
            second_source,
        )
        self.assertEqual(
            decision_module.load_challenger_replacement_cohort_decision_bytes(
                canonical_json(second_decision).encode("utf-8"),
                plan=self.plan,
                source_bundle=second_source,
                previous_decision=decision,
            ),
            second_decision,
        )

    def test_v1_documents_and_wrong_v2_build_are_not_reinterpreted(self):
        v1_build = replacement_fixtures.fixture_build_identity()
        v1_source = evidence_module.build_challenger_replacement_source_bundle(
            plan=self.plan,
            build_identity=v1_build,
            capture=replacement_fixtures.fixture_capture(),
            observed_at=replacement_fixtures.DEFAULT_CAPTURED_AT,
            previous_source_bundle=None,
            previous_decision=None,
        )
        v1_decision = decision_module.build_challenger_replacement_decision(
            plan=self.plan,
            source_bundle=v1_source,
            recorded_at=v1_source["slot"]["captured_at"],
            previous_decision=None,
        )
        with self.assertRaises(ValueError):
            evidence_module.load_challenger_replacement_cohort_source_bundle_bytes(
                canonical_json(v1_source).encode("utf-8"),
                plan=self.plan,
                build_identity=self.build_identity,
                previous_source_bundle=None,
                previous_decision=None,
            )
        with self.assertRaises(ValueError):
            decision_module.load_challenger_replacement_cohort_decision_bytes(
                canonical_json(v1_decision).encode("utf-8"),
                plan=self.plan,
                source_bundle=v1_source,
                previous_decision=None,
            )

        source, _decision = self._source_and_decision()
        wrong_build = deepcopy(self.build_identity)
        wrong_build["manifest_hash"] = "f" * 64
        with self.assertRaises(ValueError):
            evidence_module.load_challenger_replacement_cohort_source_bundle_bytes(
                canonical_json(source).encode("utf-8"),
                plan=self.plan,
                build_identity=wrong_build,
                previous_source_bundle=None,
                previous_decision=None,
            )


if __name__ == "__main__":
    unittest.main()
