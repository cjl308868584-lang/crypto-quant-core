import hashlib
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
from crypto_quant import challenger_replacement_live_input as live_input_module
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.runtime_health import (
    PublicServerTimeHttpResponse,
    build_server_time_probe,
    server_time_probe_trust_hash,
)
from tests.challenger_replacement_v2_fixtures import fixture_klines, fixture_plan


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
        rows = fixture_klines()
        raw_rows = []
        for row in rows:
            opened = datetime.fromisoformat(
                row["open_time"].replace("Z", "+00:00")
            )
            closed = datetime.fromisoformat(
                row["close_time"].replace("Z", "+00:00")
            )
            raw_rows.append(
                [
                    int(opened.timestamp() * 1000),
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    "0",
                    int(closed.timestamp() * 1000),
                    "0",
                    1,
                    "0",
                    "0",
                    "0",
                ]
            )
        response_body = canonical_json(raw_rows).encode("utf-8")
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
            "attempts": [
                {
                    "sequence": 1,
                    "request_started_at": "2026-08-22T04:04:03.000Z",
                    "response_received_at": "2026-08-22T04:04:03.100Z",
                    "status": 200,
                    "final_url": request_url,
                    "selected_headers": {
                        "http_date_or_null": "Sat, 22 Aug 2026 04:04:03 GMT",
                        "etag_or_null": None,
                        "last_modified_or_null": None,
                        "retry_after_or_null": None,
                    },
                    "body_size_bytes": len(response_body),
                    "body_sha256": hashlib.sha256(response_body).hexdigest(),
                    "response_body_utf8": response_body.decode("utf-8"),
                }
            ],
            "selected_success_attempt_index": 0,
            "rows": rows,
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

    def test_private_builder_and_grant_preserve_exact_defensive_bytes(self):
        expected = self._structural_document()
        document = live_input_module._build_live_capture_document(
            plan=self.plan,
            build_identity=self.build_identity,
            slot=expected["slot"],
            clock_records=expected["clock"],
            kline_request=expected["kline_request"],
            attempts=expected["attempts"],
            selected_attempt_index=expected["selected_success_attempt_index"],
            rows=expected["rows"],
        )
        self.assertEqual(document, expected)
        canonical_bytes = canonical_json(document).encode("utf-8")
        capture = live_input_module._grant_live_capture(
            document=document,
            canonical_bytes=canonical_bytes,
            token=live_input_module._CAPABILITY_TOKEN,
        )
        document["rows"][0]["close"] = "999"
        self.assertEqual(capture.canonical_bytes, canonical_bytes)
        self.assertNotEqual(capture.document["rows"][0]["close"], "999")
        with self.assertRaises(TypeError):
            live_input_module._grant_live_capture(
                document=expected,
                canonical_bytes=canonical_bytes,
                token=object(),
            )

    def test_live_capture_schema_is_an_exact_valid_mirror(self):
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        Draft202012Validator.check_schema(json.loads(CONFIG_SCHEMA.read_text()))

    def test_live_capture_schema_rejects_unknown_nested_fields(self):
        validator = Draft202012Validator(json.loads(CONFIG_SCHEMA.read_text()))
        document = self._structural_document()
        self.assertEqual(list(validator.iter_errors(document)), [])
        for path in (("slot",), ("kline_request",), ("attempts", 0), ("rows", 0)):
            changed = deepcopy(document)
            target = changed
            for component in path:
                target = target[component]
            target["unexpected"] = True
            with self.subTest(path=path):
                self.assertTrue(list(validator.iter_errors(changed)))

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
                "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_SCHEMA_INVALID",
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
        for document, reason in (
            (wrong_method, "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_SCHEMA_INVALID"),
            (wrong_url, "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_REQUEST_INVALID"),
        ):
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
                    reason,
                )

    def test_loader_rejects_attempt_hash_selection_and_body_row_mismatch(self):
        wrong_hash = self._structural_document()
        wrong_hash["attempts"][0]["body_sha256"] = "f" * 64
        wrong_hash["capture_hash"] = artifact_self_hash(wrong_hash, "capture_hash")
        wrong_selection = self._structural_document()
        wrong_selection["selected_success_attempt_index"] = 1
        wrong_selection["capture_hash"] = artifact_self_hash(
            wrong_selection, "capture_hash"
        )
        changed_body = self._structural_document()
        raw = json.loads(changed_body["attempts"][0]["response_body_utf8"])
        raw[-1][4] = "102"
        changed_bytes = canonical_json(raw).encode("utf-8")
        changed_body["attempts"][0]["response_body_utf8"] = changed_bytes.decode()
        changed_body["attempts"][0]["body_size_bytes"] = len(changed_bytes)
        changed_body["attempts"][0]["body_sha256"] = hashlib.sha256(
            changed_bytes
        ).hexdigest()
        changed_body["capture_hash"] = artifact_self_hash(
            changed_body, "capture_hash"
        )
        cases = (
            (wrong_hash, "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_ATTEMPT_INVALID"),
            (
                wrong_selection,
                "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_ATTEMPT_INVALID",
            ),
            (changed_body, "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_ROWS_INVALID"),
        )
        for document, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
                    load_challenger_replacement_live_capture_bytes(
                        canonical_json(document).encode("utf-8"),
                        plan=self.plan,
                        build_identity=self.build_identity,
                        previous_source_bundle=None,
                    )
                self.assertEqual(caught.exception.reason_code, reason)

    def test_loader_rejects_row_hash_and_previous_overlap_revision(self):
        wrong_row = self._structural_document()
        wrong_row["rows"][0]["source_row_hash"] = "f" * 64
        wrong_row["capture_hash"] = artifact_self_hash(wrong_row, "capture_hash")
        with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
            load_challenger_replacement_live_capture_bytes(
                canonical_json(wrong_row).encode("utf-8"),
                plan=self.plan,
                build_identity=self.build_identity,
                previous_source_bundle=None,
            )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_ROWS_INVALID",
        )

        current = self._structural_document()
        previous = {"klines": [deepcopy(current["rows"][0])] + deepcopy(current["rows"][:20])}
        previous["klines"][1]["close"] = "99"
        with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
            load_challenger_replacement_live_capture_bytes(
                canonical_json(current).encode("utf-8"),
                plan=self.plan,
                build_identity=self.build_identity,
                previous_source_bundle=previous,
            )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_OVERLAP_INVALID",
        )

    def test_loader_maps_unsafe_integer_to_fixed_row_failure(self):
        document = self._structural_document()
        original = document["attempts"][0]["response_body_utf8"]
        first_open = str(json.loads(original)[0][0])
        body = original.replace(first_open, str(2**53), 1).encode("utf-8")
        document["attempts"][0]["response_body_utf8"] = body.decode("utf-8")
        document["attempts"][0]["body_size_bytes"] = len(body)
        document["attempts"][0]["body_sha256"] = hashlib.sha256(body).hexdigest()
        document["capture_hash"] = artifact_self_hash(document, "capture_hash")
        with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
            load_challenger_replacement_live_capture_bytes(
                canonical_json(document).encode("utf-8"),
                plan=self.plan,
                build_identity=self.build_identity,
                previous_source_bundle=None,
            )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_ROWS_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
