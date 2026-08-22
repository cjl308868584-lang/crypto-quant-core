import base64
import hashlib
import json
import os
import unittest
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

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
from crypto_quant.challenger_replacement_runtime import (
    ChallengerReplacementRuntimeState,
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
    def __init__(
        self,
        base=datetime(2026, 8, 22, 4, 4, tzinfo=timezone.utc),
    ):
        self.responses = []
        for index, rtt in enumerate((50, 60, 55)):
            started = base + timedelta(seconds=index)
            received = started + timedelta(milliseconds=rtt)
            midpoint = int((started.timestamp() + received.timestamp()) * 500)
            self.responses.append(
                PublicServerTimeHttpResponse(
                    status=200,
                    final_url="https://data-api.binance.vision/api/v3/time",
                    headers={
                        "Date": "Sat, 22 Aug 2026 04:04:00 GMT",
                        "Content-Type": "application/json",
                    },
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


def _raw_kline_body(rows):
    raw_rows = []
    for row in rows:
        opened = datetime.fromisoformat(row["open_time"].replace("Z", "+00:00"))
        closed = datetime.fromisoformat(row["close_time"].replace("Z", "+00:00"))
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
    return canonical_json(raw_rows).encode("utf-8")


@dataclass(frozen=True)
class _KlineResponse:
    status: int
    final_url: str
    headers: dict
    body: bytes
    request_started_at: str
    response_received_at: str


class _FixtureState(ChallengerReplacementRuntimeState):
    def __init__(self, *, plan, build_identity):
        self.plan = plan
        self.build_identity = build_identity
        self.projection = {
            "events": (),
            "slots": {},
            "last_event_hash": "0" * 64,
            "next_sequence": 1,
            "active_slot_id": None,
            "completed_slot_count": 0,
            "failed_slot_count": 0,
            "next_required_slot": {"sequence": 1, "scheduled_for": None},
            "orphan_staging_count": 0,
            "orphan_staging_bytes": 0,
            "_previous_source_bundle": None,
            "_previous_decision": None,
        }

    def _replay(self):
        return deepcopy(self.projection)

    def replay(self):
        return {
            key: deepcopy(value)
            for key, value in self.projection.items()
            if not key.startswith("_")
        }


class _OpenerResponse:
    def __init__(self, body):
        self.body = body
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit):
        return self.body[:limit]

    def getcode(self):
        return 200

    def geturl(self):
        return "https://data-api.binance.vision/api/v3/time"


class _Opener:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        return self.response


class LivePublicHttpBoundaryTests(unittest.TestCase):
    def test_public_http_disables_proxies_rejects_redirect_and_bounds_body(self):
        wall = (
            datetime(2026, 8, 22, 4, 4, tzinfo=timezone.utc),
            datetime(2026, 8, 22, 4, 4, 0, 100000, tzinfo=timezone.utc),
        )
        body = b'{"serverTime":1787371440050}'
        opener = _Opener(_OpenerResponse(body))
        with patch.object(
            live_input_module, "build_opener", return_value=opener
        ) as built, patch.object(
            live_input_module, "_wall_now", side_effect=wall
        ), patch.object(
            live_input_module, "_monotonic", side_effect=(1_000_000_000, 1_100_000_000)
        ):
            response = live_input_module._open_public_request(
                Request(
                    "https://data-api.binance.vision/api/v3/time",
                    method="GET",
                )
            )
        self.assertIsInstance(response, PublicServerTimeHttpResponse)
        self.assertEqual(response.monotonic_rtt_ms, 100)
        handlers = built.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
            handlers[1].redirect_request(None, None, 302, "redirect", {}, "https://evil.example")
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_REDIRECT_FORBIDDEN",
        )
        self.assertEqual(opener.calls[0][1], 15)

        oversized = _Opener(
            _OpenerResponse(b"x" * (live_input_module._MAX_RESPONSE_BYTES + 1))
        )
        with patch.object(
            live_input_module, "build_opener", return_value=oversized
        ), patch.object(
            live_input_module, "_wall_now", side_effect=wall
        ), patch.object(
            live_input_module, "_monotonic", side_effect=(1_000_000_000, 1_100_000_000)
        ):
            with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
                live_input_module._open_public_request(
                    Request(
                        "https://data-api.binance.vision/api/v3/time",
                        method="GET",
                    )
                )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_RESPONSE_INVALID",
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
        response_body = _raw_kline_body(rows)
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
                    "outcome": "HTTP_RESPONSE",
                    "error_reason_or_null": None,
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
                    "response_body_base64": base64.b64encode(response_body).decode("ascii"),
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
        raw = json.loads(base64.b64decode(changed_body["attempts"][0]["response_body_base64"]))
        raw[-1][4] = "102"
        changed_bytes = canonical_json(raw).encode("utf-8")
        changed_body["attempts"][0]["response_body_base64"] = base64.b64encode(changed_bytes).decode("ascii")
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

    def test_loader_accepts_explicit_transport_error_before_success(self):
        document = self._structural_document()
        success = document["attempts"][0]
        success["sequence"] = 2
        transport = {
            "sequence": 1,
            "outcome": "TRANSPORT_ERROR",
            "error_reason_or_null": "CHALLENGER_REPLACEMENT_LIVE_INPUT_TRANSPORT_FAILURE",
            "request_started_at": "2026-08-22T04:04:02.500Z",
            "response_received_at": "2026-08-22T04:04:02.600Z",
            "status": None,
            "final_url": None,
            "selected_headers": {
                "http_date_or_null": None,
                "etag_or_null": None,
                "last_modified_or_null": None,
                "retry_after_or_null": None,
            },
            "body_size_bytes": 0,
            "body_sha256": hashlib.sha256(b"").hexdigest(),
            "response_body_base64": "",
        }
        document["attempts"] = [transport, success]
        document["selected_success_attempt_index"] = 1
        document["authority"]["network_request_count"] = 5
        document["capture_hash"] = artifact_self_hash(document, "capture_hash")
        self.assertEqual(
            load_challenger_replacement_live_capture_bytes(
                canonical_json(document).encode("utf-8"),
                plan=self.plan,
                build_identity=self.build_identity,
                previous_source_bundle=None,
            ),
            document,
        )

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
        previous = {
            "klines": [deepcopy(current["rows"][0])]
            + deepcopy(current["rows"][:20])
        }
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
        original = document["attempts"][0]["response_body_base64"]
        raw = base64.b64decode(original).decode("utf-8")
        first_open = str(json.loads(raw)[0][0])
        body = raw.replace(first_open, str(2**53), 1).encode("utf-8")
        document["attempts"][0]["response_body_base64"] = base64.b64encode(body).decode("ascii")
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

    def test_loader_rejects_noncanonical_base64_pad_bits(self):
        document = self._structural_document()
        encoded = document["attempts"][0]["response_body_base64"]
        self.assertTrue(encoded.endswith("="))
        document["attempts"][0]["response_body_base64"] = encoded[:-2] + "1="
        document["capture_hash"] = artifact_self_hash(document, "capture_hash")
        with self.assertRaisesRegex(
            ChallengerReplacementLiveInputError,
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_ATTEMPT_INVALID",
        ):
            load_challenger_replacement_live_capture_bytes(
                canonical_json(document).encode(), plan=self.plan,
                build_identity=self.build_identity, previous_source_bundle=None)


class LiveAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.codec_fixture = LiveCaptureCodecTests()
        self.codec_fixture.setUp()
        self.plan = self.codec_fixture.plan
        self.build_identity = self.codec_fixture.build_identity
        self.state = _FixtureState(
            plan=self.plan, build_identity=self.build_identity
        )
        self.requests = []
        self.sleeps = []

    def _kline_response(
        self,
        *,
        status=200,
        sequence=1,
        body=None,
        content_type="application/json",
        scheduled=datetime(2026, 8, 22, 4, 0, tzinfo=timezone.utc),
    ):
        end_time_ms = int(scheduled.timestamp() * 1000) - 1
        url = (
            "https://data-api.binance.vision/api/v3/klines?"
            f"endTime={end_time_ms}&interval=4h&limit=21&symbol=ETHUSDT"
        )
        started = scheduled + timedelta(minutes=4, seconds=3 + sequence - 1)
        default_rows = fixture_klines(scheduled_for=_utc(scheduled))
        default_body = _raw_kline_body(default_rows)
        received = started + timedelta(milliseconds=100)
        return _KlineResponse(
            status=status,
            final_url=url,
            headers={
                "Date": "Sat, 22 Aug 2026 04:04:03 GMT",
                "Content-Type": content_type,
            },
            body=(
                default_body
                if body is None
                else body
            ),
            request_started_at=_utc(started),
            response_received_at=_utc(received),
        )

    def _acquire_with(self, responses, *, wall=None):
        pending = list(responses)
        wall = wall or datetime(
            2026, 8, 22, 4, 4, 2, 500000, tzinfo=timezone.utc
        )

        def open_request(request):
            self.requests.append(request)
            if not pending:
                raise AssertionError("unexpected public request")
            response = pending.pop(0)
            if isinstance(response, BaseException):
                raise response
            return response

        with patch.dict(os.environ, {}, clear=True), patch.object(
            live_input_module, "_open_public_request", side_effect=open_request, create=True
        ), patch.object(
            live_input_module, "_sleep", side_effect=self.sleeps.append, create=True
        ), patch.object(
            live_input_module, "_wall_now", return_value=wall
        ):
            return live_input_module.acquire_challenger_replacement_live_capture(
                state=self.state
            )

    def test_exact_three_time_and_one_kline_happy_path(self):
        capture = self._acquire_with(
            _TimeTransport().responses + [self._kline_response()]
        )
        self.assertIsInstance(capture, ChallengerReplacementLiveCapture)
        self.assertEqual(capture.document["authority"]["network_request_count"], 4)
        self.assertEqual(len(self.requests), 4)
        self.assertEqual(self.sleeps, [])
        self.assertEqual(
            [request.full_url for request in self.requests[:3]],
            ["https://data-api.binance.vision/api/v3/time"] * 3,
        )
        self.assertEqual(
            self.requests[3].full_url,
            self.codec_fixture._structural_document()["kline_request"]["url"],
        )
        self.assertTrue(all(request.get_method() == "GET" for request in self.requests))
        self.assertTrue(all(request.data is None for request in self.requests))

    def test_two_transient_klines_then_success_records_six_requests(self):
        capture = self._acquire_with(
            _TimeTransport().responses
            + [
                self._kline_response(status=503, sequence=1, body=b'{"code":-1}', content_type="text/plain"),
                self._kline_response(status=429, sequence=2, body=b'{"code":-2}', content_type="text/plain"),
                self._kline_response(sequence=3),
            ]
        )
        self.assertEqual(capture.document["authority"]["network_request_count"], 6)
        self.assertEqual(len(self.requests), 6)
        self.assertEqual(self.sleeps, [1, 2])

    def test_binary_transient_body_is_recorded_and_retried(self):
        capture = self._acquire_with(
            _TimeTransport().responses
            + [
                self._kline_response(
                    status=503, sequence=1, body=b"\xff", content_type="text/plain"
                ),
                self._kline_response(sequence=2),
            ]
        )
        self.assertEqual(capture.document["authority"]["network_request_count"], 5)
        self.assertEqual(self.sleeps, [1])

    def test_empty_transient_body_is_recorded_and_retried(self):
        capture = self._acquire_with(
            _TimeTransport().responses
            + [
                self._kline_response(
                    status=503, sequence=1, body=b"", content_type="text/plain"
                ),
                self._kline_response(sequence=2),
            ]
        )
        self.assertEqual(capture.document["authority"]["network_request_count"], 5)
        self.assertEqual(self.sleeps, [1])

    def test_transport_failure_is_recorded_and_retried_once(self):
        capture = self._acquire_with(
            _TimeTransport().responses
            + [
                ChallengerReplacementLiveInputError(
                    "CHALLENGER_REPLACEMENT_LIVE_INPUT_TRANSPORT_FAILURE"
                ),
                self._kline_response(sequence=2),
            ]
        )
        self.assertEqual(len(self.requests), 5)
        self.assertEqual(self.sleeps, [1])
        self.assertEqual(
            capture.document["attempts"][0]["outcome"], "TRANSPORT_ERROR"
        )
        self.assertEqual(
            capture.document["attempts"][0]["error_reason_or_null"],
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_TRANSPORT_FAILURE",
        )

    def test_malformed_http_200_is_not_retried(self):
        with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
            self._acquire_with(
                _TimeTransport().responses
                + [self._kline_response(body=b"not-json")]
            )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_JSON_INVALID",
        )
        self.assertEqual(len(self.requests), 4)
        self.assertEqual(self.sleeps, [])

    def test_non_utf8_http_200_has_fixed_json_failure(self):
        with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
            self._acquire_with(
                _TimeTransport().responses + [self._kline_response(body=b"\xff")]
            )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_JSON_INVALID",
        )

    def test_non_json_http_200_is_not_retried(self):
        with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
            self._acquire_with(
                _TimeTransport().responses
                + [self._kline_response(content_type="text/html")]
            )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_RESPONSE_INVALID",
        )
        self.assertEqual(len(self.requests), 4)
        self.assertEqual(self.sleeps, [])

    def test_non_json_server_time_fails_clock_probe(self):
        responses = _TimeTransport().responses
        responses[0] = replace(
            responses[0],
            headers={"Content-Type": "text/html"},
        )
        with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
            self._acquire_with(responses)
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_CLOCK_INVALID",
        )
        self.assertEqual(len(self.requests), 1)

    def test_transient_server_time_status_is_classified_transient(self):
        responses = _TimeTransport().responses
        responses[0] = replace(
            responses[0], status=503, headers={"Content-Type": "text/plain"}
        )
        with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
            self._acquire_with(responses)
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_TRANSPORT_FAILURE",
        )
        self.assertEqual(len(self.requests), 1)

    def test_active_failed_and_terminal_streams_make_zero_requests(self):
        cases = (
            ("active_slot_id", "active"),
            ("failed_slot_count", 1),
            ("next_required_slot", None),
        )
        for key, value in cases:
            with self.subTest(key=key):
                self.state.projection[key] = value
                with self.assertRaises(ChallengerReplacementLiveInputError):
                    self._acquire_with([])
                self.assertEqual(self.requests, [])
                self.state = _FixtureState(
                    plan=self.plan, build_identity=self.build_identity
                )

    def test_known_pre_window_and_continuity_gap_make_zero_requests(self):
        self.state.projection["next_required_slot"] = {
            "sequence": 2,
            "scheduled_for": "2026-08-22T04:00:00.000Z",
        }
        with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
            self._acquire_with(
                [],
                wall=datetime(2026, 8, 22, 4, 1, tzinfo=timezone.utc),
            )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_WINDOW_INVALID",
        )
        self.assertEqual(self.requests, [])

        self.state.projection["next_required_slot"] = {
            "sequence": 2,
            "scheduled_for": "2026-08-22T04:00:00.000Z",
        }
        with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
            self._acquire_with(
                [],
                wall=datetime(2026, 8, 22, 4, 11, tzinfo=timezone.utc),
            )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_WINDOW_INVALID",
        )
        self.assertEqual(self.requests, [])

        self.state.projection["next_required_slot"] = {
            "sequence": 2,
            "scheduled_for": "2026-08-22T00:00:00.000Z",
        }
        with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
            self._acquire_with(
                [],
                wall=datetime(2026, 8, 22, 4, 5, tzinfo=timezone.utc),
            )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_CONTINUITY_GAP",
        )
        self.assertEqual(self.requests, [])

    def test_credential_environment_fails_before_request(self):
        with patch.dict(os.environ, {"BINANCE_API_KEY": "sentinel"}, clear=True), patch.object(
            live_input_module, "_open_public_request", create=True
        ) as opened:
            with self.assertRaises(ChallengerReplacementLiveInputError) as caught:
                live_input_module.acquire_challenger_replacement_live_capture(
                    state=self.state
                )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_ENVIRONMENT_FORBIDDEN",
        )
        opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()
