import json
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json, stable_id
from crypto_quant.challenger_replacement_live_input import (
    ChallengerReplacementLiveCapture,
    ChallengerReplacementLiveInputError,
    load_challenger_replacement_live_capture_bytes,
)
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.runtime_health import (
    PublicServerTimeHttpResponse,
    build_server_time_probe,
    server_time_probe_trust_hash,
)
from tests.challenger_replacement_v2_fixtures import fixture_plan


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "config/challenger-replacement-live-capture-v1.schema.json"
PACKAGE_SCHEMA = (
    ROOT
    / "src/crypto_quant/schemas/challenger-replacement-live-capture-v1.schema.json"
)


def _utc(value):
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class _TimeTransport:
    def __init__(self):
        base = datetime(2026, 8, 22, 4, 4, tzinfo=timezone.utc)
        self.responses = []
        for index, rtt in enumerate((50, 60, 55)):
            started = base + timedelta(seconds=index)
            received = started + timedelta(milliseconds=rtt)
            midpoint = int((started.timestamp() + received.timestamp()) * 500)
            self.responses.append(
                PublicServerTimeHttpResponse(
                    status=200,
                    final_url="https://data-api.binance.vision/api/v3/time",
                    headers={"Date": "Sat, 22 Aug 2026 04:04:00 GMT"},
                    body=json.dumps(
                        {"serverTime": midpoint + 100}, separators=(",", ":")
                    ).encode("utf-8"),
                    request_started_at=_utc(started),
                    response_received_at=_utc(received),
                    monotonic_rtt_ms=rtt,
                )
            )

    def get(self):
        return self.responses.pop(0)


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
        self.clock_probe = build_server_time_probe(transport=_TimeTransport())

    def _structural_document(self):
        scheduled = datetime(2026, 8, 22, 4, 0, tzinfo=timezone.utc)
        end_time_ms = int(scheduled.timestamp() * 1000) - 1
        request_url = (
            "https://data-api.binance.vision/api/v3/klines?"
            f"endTime={end_time_ms}&interval=4h&limit=21&symbol=ETHUSDT"
        )
        request_identity = {
            "method": "GET",
            "url": request_url,
            "symbol": "ETHUSDT",
            "interval": "4h",
            "limit": 21,
            "end_time_ms": end_time_ms,
        }
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
            "clock": {
                "probe": deepcopy(self.clock_probe),
                "trust_hash": server_time_probe_trust_hash(self.clock_probe),
            },
            "kline_request": {
                "request_id": stable_id(
                    "challenger_replacement_kline_request", request_identity
                ),
                **request_identity,
            },
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

    def test_loader_rejects_untrusted_or_mutated_clock_probe(self):
        wrong_trust = self._structural_document()
        wrong_trust["clock"]["trust_hash"] = "f" * 64
        wrong_trust["capture_hash"] = artifact_self_hash(wrong_trust, "capture_hash")
        mutated_probe = self._structural_document()
        mutated_probe["clock"]["probe"]["samples"][0]["status"] = 503
        mutated_probe["clock"]["trust_hash"] = server_time_probe_trust_hash(
            mutated_probe["clock"]["probe"]
        )
        mutated_probe["capture_hash"] = artifact_self_hash(
            mutated_probe, "capture_hash"
        )
        for document in (wrong_trust, mutated_probe):
            with self.subTest(document=document["clock"]):
                with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
                    load_challenger_replacement_live_capture_bytes(
                        canonical_json(document).encode("utf-8"),
                        plan=self.plan,
                        build_identity=self.build_identity,
                        previous_source_bundle=None,
                    )
                self.assertEqual(
                    caught.exception.reason_code,
                    "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_CLOCK_INVALID",
                )

    def test_loader_rejects_non_allowlisted_or_forged_kline_request(self):
        wrong_method = self._structural_document()
        wrong_method["kline_request"]["method"] = "POST"
        wrong_method["capture_hash"] = artifact_self_hash(
            wrong_method, "capture_hash"
        )
        wrong_url = self._structural_document()
        wrong_url["kline_request"]["url"] = (
            "https://api.binance.com/api/v3/klines"
        )
        wrong_url["capture_hash"] = artifact_self_hash(wrong_url, "capture_hash")
        for document in (wrong_method, wrong_url):
            with self.subTest(request=document["kline_request"]):
                with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
                    load_challenger_replacement_live_capture_bytes(
                        canonical_json(document).encode("utf-8"),
                        plan=self.plan,
                        build_identity=self.build_identity,
                        previous_source_bundle=None,
                    )
                self.assertEqual(
                    caught.exception.reason_code,
                    "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_REQUEST_INVALID",
                )


if __name__ == "__main__":
    unittest.main()
