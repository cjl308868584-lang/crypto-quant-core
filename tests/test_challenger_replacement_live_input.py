import json
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json, stable_id
from crypto_quant.challenger_replacement_live_input import (
    ChallengerReplacementLiveCapture,
    ChallengerReplacementLiveInputError,
    load_challenger_replacement_live_capture_bytes,
)
from crypto_quant.evidence import artifact_self_hash
from tests.challenger_replacement_v2_fixtures import fixture_plan


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "config/challenger-replacement-live-capture-v1.schema.json"
PACKAGE_SCHEMA = (
    ROOT
    / "src/crypto_quant/schemas/challenger-replacement-live-capture-v1.schema.json"
)


class LiveCaptureCodecTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture_plan()
        self.build_identity = {
            "release_tag": "v0.67.0",
            "peeled_commit": "c" * 40,
            "package_version": "0.67.0",
            "manifest_version": "1.61.0",
            "build_input_tree_hash": "a" * 64,
            "manifest_hash": "b" * 64,
            "manifest_file_sha256": "d" * 64,
        }

    def _structural_document(self):
        document = {
            "$schema": "./challenger-replacement-live-capture-v1.schema.json",
            "schema_version": "1.0.0",
            "capture_id": "",
            "capture_hash": "0" * 64,
            "evidence_qualification": "REPLACEMENT_CONFIRMATORY_COHORT_INPUT",
            "plan": {
                "plan_id": self.plan["plan_id"],
                "plan_hash": self.plan["plan_hash"],
            },
            "build_identity": deepcopy(self.build_identity),
            "slot": {
                "slot_id": stable_id(
                    "challenger_replacement_slot",
                    {
                        "plan_hash": self.plan["plan_hash"],
                        "scheduled_for": "2026-08-22T04:00:00.000Z",
                    },
                ),
                "sequence": 1,
                "scheduled_for": "2026-08-22T04:00:00.000Z",
                "captured_at": "2026-08-22T04:05:00.000Z",
            },
            "clock": {},
            "kline_request": {},
            "attempts": [{}],
            "selected_success_attempt_index": 0,
            "rows": [{} for _ in range(21)],
            "authority": {
                "network_request_count": 4,
                "credentials_allowed": False,
                "account_requests_allowed": False,
                "broker_requests_allowed": False,
                "orders_allowed": False,
            },
        }
        document["capture_id"] = stable_id(
            "challenger_replacement_live_capture",
            {
                "plan": document["plan"],
                "build_identity": document["build_identity"],
                "slot": document["slot"],
            },
        )
        document["capture_hash"] = artifact_self_hash(document, "capture_hash")
        return document

    def test_live_capture_capability_cannot_be_constructed_directly(self):
        with self.assertRaises(TypeError):
            ChallengerReplacementLiveCapture(document={}, canonical_bytes=b"{}")

    def test_live_capture_schema_is_an_exact_valid_mirror(self):
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        Draft202012Validator.check_schema(json.loads(CONFIG_SCHEMA.read_text()))

    def test_loader_rejects_schema_invalid_duplicate_and_float_documents(self):
        cases = (
            (b"{}", "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_SCHEMA_INVALID"),
            (
                b'{"schema_version":"1","schema_version":"1"}',
                "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_JSON_INVALID",
            ),
            (
                b'{"network_request_count":4.0}',
                "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_JSON_INVALID",
            ),
        )
        for data, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
                    load_challenger_replacement_live_capture_bytes(
                        data,
                        plan=self.plan,
                        build_identity=self.build_identity,
                        previous_source_bundle=None,
                    )
                self.assertEqual(caught.exception.reason_code, reason)

    def test_loader_rejects_wrong_plan_and_build_bindings(self):
        wrong_plan = self._structural_document()
        wrong_plan["plan"]["plan_hash"] = "f" * 64
        wrong_plan["capture_hash"] = artifact_self_hash(wrong_plan, "capture_hash")
        wrong_build = self._structural_document()
        wrong_build["build_identity"]["manifest_hash"] = "e" * 64
        wrong_build["capture_hash"] = artifact_self_hash(wrong_build, "capture_hash")
        for document, reason in (
            (
                wrong_plan,
                "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_PLAN_BINDING_INVALID",
            ),
            (
                wrong_build,
                "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_BUILD_BINDING_INVALID",
            ),
        ):
            with self.subTest(reason=reason):
                with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
                    load_challenger_replacement_live_capture_bytes(
                        canonical_json(document).encode("utf-8"),
                        plan=self.plan,
                        build_identity=self.build_identity,
                        previous_source_bundle=None,
                    )
                self.assertEqual(caught.exception.reason_code, reason)

    def test_loader_rejects_forged_slot_and_authority(self):
        wrong_slot = self._structural_document()
        wrong_slot["slot"]["slot_id"] = "challenger_replacement_slot_" + "f" * 64
        wrong_slot["capture_hash"] = artifact_self_hash(wrong_slot, "capture_hash")
        wrong_authority = self._structural_document()
        wrong_authority["authority"]["credentials_allowed"] = True
        wrong_authority["capture_hash"] = artifact_self_hash(
            wrong_authority, "capture_hash"
        )
        for document, reason in (
            (wrong_slot, "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_SLOT_INVALID"),
            (
                wrong_authority,
                "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_AUTHORITY_INVALID",
            ),
        ):
            with self.subTest(reason=reason):
                with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
                    load_challenger_replacement_live_capture_bytes(
                        canonical_json(document).encode("utf-8"),
                        plan=self.plan,
                        build_identity=self.build_identity,
                        previous_source_bundle=None,
                    )
                self.assertEqual(caught.exception.reason_code, reason)

    def test_loader_rejects_wrong_capture_hash_and_identity(self):
        wrong_hash = self._structural_document()
        wrong_hash["capture_hash"] = "f" * 64
        wrong_identity = self._structural_document()
        wrong_identity["capture_id"] = (
            "challenger_replacement_live_capture_" + "f" * 64
        )
        wrong_identity["capture_hash"] = artifact_self_hash(
            wrong_identity, "capture_hash"
        )
        for document, reason in (
            (wrong_hash, "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_HASH_INVALID"),
            (wrong_identity, "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_ID_INVALID"),
        ):
            with self.subTest(reason=reason):
                with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
                    load_challenger_replacement_live_capture_bytes(
                        canonical_json(document).encode("utf-8"),
                        plan=self.plan,
                        build_identity=self.build_identity,
                        previous_source_bundle=None,
                    )
                self.assertEqual(caught.exception.reason_code, reason)


if __name__ == "__main__":
    unittest.main()
