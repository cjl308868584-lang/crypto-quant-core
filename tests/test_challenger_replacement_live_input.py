import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.challenger_replacement_live_input import (
    ChallengerReplacementLiveCapture,
    ChallengerReplacementLiveInputError,
    load_challenger_replacement_live_capture_bytes,
)
from tests.challenger_replacement_v2_fixtures import fixture_plan


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "config/challenger-replacement-live-capture-v1.schema.json"
PACKAGE_SCHEMA = (
    ROOT
    / "src/crypto_quant/schemas/challenger-replacement-live-capture-v1.schema.json"
)


class LiveCaptureCodecTests(unittest.TestCase):
    def test_live_capture_capability_cannot_be_constructed_directly(self):
        with self.assertRaises(TypeError):
            ChallengerReplacementLiveCapture(document={}, canonical_bytes=b"{}")

    def test_live_capture_schema_is_an_exact_valid_mirror(self):
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        Draft202012Validator.check_schema(json.loads(CONFIG_SCHEMA.read_text()))

    def test_loader_rejects_schema_invalid_duplicate_and_float_documents(self):
        build_identity = {
            "release_tag": "v0.67.0",
            "peeled_commit": "c" * 40,
            "package_version": "0.67.0",
            "manifest_version": "1.61.0",
            "build_input_tree_hash": "a" * 64,
            "manifest_hash": "b" * 64,
            "manifest_file_sha256": "d" * 64,
        }
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
                        plan=fixture_plan(),
                        build_identity=build_identity,
                        previous_source_bundle=None,
                    )
                self.assertEqual(caught.exception.reason_code, reason)


if __name__ == "__main__":
    unittest.main()
