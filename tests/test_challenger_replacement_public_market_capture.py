import base64
import hashlib
import json
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
from unittest.mock import patch
from urllib.request import OpenerDirector

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json, stable_id
from crypto_quant.build import EvaluatorBuild
from crypto_quant import (
    challenger_replacement_public_market_capture as public_capture_module,
)
from crypto_quant.challenger_replacement_live_input import (
    ChallengerReplacementLiveInputError,
    _build_live_capture_document,
    load_challenger_replacement_live_capture_bytes,
)
from crypto_quant.challenger_replacement_opportunity_projection import (
    opportunity_id_for,
)
from crypto_quant.challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityState,
)
from crypto_quant.challenger_replacement_public_http import (
    PublicHttpError,
    PublicHttpResponse,
    attempt_document,
    transport_failure_attempt,
)
from crypto_quant.challenger_replacement_public_market_capture import (
    ChallengerReplacementPublicMarketCapture,
    ChallengerReplacementPublicMarketCaptureError,
    load_challenger_replacement_public_market_capture_bytes,
)
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.runtime_health import (
    PublicServerTimeHttpResponse,
    build_server_time_probe,
    server_time_probe_trust_hash,
)
from tests.challenger_replacement_v2_fixtures import fixture_klines, fixture_plan
from tests.challenger_replacement_v3_fixtures import fixture_v3_plan


SCHEDULED_FOR = "2026-08-26T04:00:00.000Z"
CAPTURED_AT = "2026-08-26T04:05:00.000Z"
V067_BUILD = {
    "release_tag": "v0.67.0",
    "peeled_commit": "ca022edccdcbb2d28b1ea25002e5f19512795e3e",
    "package_version": "0.67.0",
    "manifest_version": "1.61.0",
    "build_input_tree_hash": "5c2a98492aa45f311cea75617745ac6d1e0afe0ea2ff36a5950a0f5c00c4efa1",
    "manifest_hash": "2b72a470a2f210461a3a6753fd3d603fee9b90df76e825deea3b9bde61a26110",
    "manifest_file_sha256": "ec2ba2d48dd35676eb442ed80cd0e45a642a2b109626db2f54a25d25823a2bf8",
}
V076_BUILD = {
    "release_tag": "v0.76.0-fixture",
    "peeled_commit": "7" * 40,
    "package_version": "0.76.0",
    "manifest_version": "1.70.0",
    "build_input_tree_hash": "1" * 64,
    "manifest_hash": "2" * 64,
    "manifest_file_sha256": "3" * 64,
}
V076_FORMAL_BUILD = {
    "reviewed_code_checkpoint": "7" * 40,
    "package_version": "0.76.0",
    "predecessor_manifest_identity": {
        "repository": "cjl308868584-lang/crypto-quant-core",
        "visibility": "PUBLIC",
        "release_tag": "v0.75.0",
        "tag_object": "4bd4b2e21c760d6fad2a27903c67ee509ac116c9",
        "peeled_commit": "a51ed15d5a484e5bb9a54dc75a7fef4e8876e4d5",
        "package_version": "0.75.0",
        "manifest_version": "1.69.0",
        "manifest_hash": "b15479590536c302e173a41a758c9113cd7452b0000d8b6c5cb5c2ad8b9404d9",
        "manifest_file_sha256": "df1695827975cbeb9c094b8182839e132219a52a19dc4166677a742d48442220",
        "build_input_tree_hash": "07812c0a352dabab3742aa1c3417eaa8a8363e46a5059e49323f2b1c0d8a4a78",
        "main_ci_run": 32869868571,
    },
    "executable_core_hash": "4" * 64,
}
SPOT_EXCHANGE_INFO_URL = "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=ETHUSDT"
SPOT_BOOK_TICKER_URL = "https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol=ETHUSDT"
FUTURES_EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
FUTURES_BOOK_TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol=ETHUSDT"
FUTURES_PREMIUM_INDEX_URL = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=ETHUSDT"
FUNDING_URL = (
    "https://fapi.binance.com/fapi/v1/fundingRate?"
    "endTime=1787716800000&limit=16&startTime=1787702400001&symbol=ETHUSDT"
)
LEGACY_COMMITTED_CAPTURE = Path(__file__).parent / "fixtures" / (
    "challenger_replacement_v076/public-market-capture.json"
)
CURRENT_COMMITTED_CAPTURE = Path(__file__).parent / "fixtures" / (
    "challenger_replacement_v076/public-market-capture-v2.1.json"
)
COMMITTED_CAPTURE = LEGACY_COMMITTED_CAPTURE


def _utc(value):
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class _TimeTransport:
    def __init__(self):
        base = datetime(2026, 8, 26, 4, 4, tzinfo=timezone.utc)
        self.responses = []
        for index, rtt in enumerate((50, 60, 55)):
            started = base + timedelta(seconds=index)
            received = started + timedelta(milliseconds=rtt)
            midpoint = int((started.timestamp() + received.timestamp()) * 500)
            self.responses.append(PublicServerTimeHttpResponse(
                status=200,
                final_url="https://data-api.binance.vision/api/v3/time",
                headers={"Content-Type": "application/json"},
                body=json.dumps({"serverTime": midpoint + 100}, separators=(",", ":")).encode("utf-8"),
                request_started_at=_utc(started),
                response_received_at=_utc(received),
                monotonic_rtt_ms=rtt,
            ))

    def get(self):
        return self.responses.pop(0)


def _raw_kline_body(rows):
    raw = []
    for row in rows:
        opened = datetime.fromisoformat(row["open_time"].replace("Z", "+00:00"))
        closed = datetime.fromisoformat(row["close_time"].replace("Z", "+00:00"))
        raw.append([
            int(opened.timestamp() * 1000), row["open"], row["high"], row["low"],
            row["close"], "0", int(closed.timestamp() * 1000), "0", 1,
            "0", "0", "0",
        ])
    return canonical_json(raw).encode("utf-8")


def _live_capture_bytes(latest="3310"):
    plan = fixture_plan()
    rows = fixture_klines(scheduled_for=SCHEDULED_FOR, latest=latest)
    scheduled = datetime.fromisoformat(SCHEDULED_FOR.replace("Z", "+00:00"))
    end_time_ms = int(scheduled.timestamp() * 1000) - 1
    request_identity = {
        "method": "GET",
        "url": "https://data-api.binance.vision/api/v3/klines?"
        f"endTime={end_time_ms}&interval=4h&limit=21&symbol=ETHUSDT",
        "symbol": "ETHUSDT", "interval": "4h", "limit": 21,
        "end_time_ms": end_time_ms,
    }
    probe = build_server_time_probe(transport=_TimeTransport())
    response = PublicHttpResponse(
        status=200, final_url=request_identity["url"],
        headers={"Content-Type": "application/json"}, body=_raw_kline_body(rows),
        monotonic_rtt_ms=100,
        request_started_at="2026-08-26T04:04:03.000Z",
        response_received_at="2026-08-26T04:04:03.100Z",
    )
    document = _build_live_capture_document(
        plan=plan, build_identity=V067_BUILD,
        slot={
            "slot_id": stable_id("challenger_replacement_slot", {
                "plan_hash": plan["plan_hash"], "scheduled_for": SCHEDULED_FOR,
            }),
            "sequence": 1, "scheduled_for": SCHEDULED_FOR,
            "captured_at": CAPTURED_AT,
        },
        clock_records={"probe": probe, "trust_hash": server_time_probe_trust_hash(probe)},
        kline_request={
            "request_id": stable_id("challenger_replacement_kline_request", request_identity),
            **request_identity,
        },
        attempts=[attempt_document(response, 1)], selected_attempt_index=0,
        rows=rows,
    )
    body = canonical_json(document).encode("utf-8")
    load_challenger_replacement_live_capture_bytes(
        body, plan=plan, build_identity=V067_BUILD, previous_source_bundle=None
    )
    return body, document


def _payloads():
    spot_filters = [
        {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
        {"filterType": "LOT_SIZE", "minQty": "0.0001", "maxQty": "1000", "stepSize": "0.0001"},
        {"filterType": "MARKET_LOT_SIZE", "minQty": "0.0002", "maxQty": "900", "stepSize": "0.0002"},
        {"filterType": "MIN_NOTIONAL", "minNotional": "5", "applyToMarket": True},
        {"filterType": "NOTIONAL", "minNotional": "6", "applyMinToMarket": True},
    ]
    perpetual_filters = [
        {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.1"},
        {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
        {"filterType": "MARKET_LOT_SIZE", "minQty": "0.002", "maxQty": "800", "stepSize": "0.002"},
        {"filterType": "MIN_NOTIONAL", "notional": "5"},
    ]
    return (
        ("spot_exchange_info", SPOT_EXCHANGE_INFO_URL, 1024 * 1024, {
            "timezone": "UTC", "symbols": [{"symbol": "ETHUSDT", "status": "TRADING", "baseAsset": "ETH", "quoteAsset": "USDT", "filters": spot_filters}],
        }),
        ("spot_book_ticker", SPOT_BOOK_TICKER_URL, 1024 * 1024, {
            "symbol": "ETHUSDT", "bidPrice": "3309.90", "bidQty": "10", "askPrice": "3310.10", "askQty": "11",
        }),
        ("perpetual_exchange_info", FUTURES_EXCHANGE_INFO_URL, 4 * 1024 * 1024, {
            "timezone": "UTC", "symbols": [{"symbol": "ETHUSDT", "pair": "ETHUSDT", "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "ETH", "quoteAsset": "USDT", "marginAsset": "USDT", "filters": perpetual_filters}],
        }),
        ("perpetual_book_ticker", FUTURES_BOOK_TICKER_URL, 1024 * 1024, {
            "symbol": "ETHUSDT", "bidPrice": "3309.80", "bidQty": "20", "askPrice": "3310.20", "askQty": "21", "time": 1787717040000,
        }),
        ("perpetual_mark", FUTURES_PREMIUM_INDEX_URL, 1024 * 1024, {
            "symbol": "ETHUSDT", "markPrice": "3310.25", "indexPrice": "3310.20", "lastFundingRate": "-0.0001", "nextFundingTime": 1787731200000, "time": 1787717040000,
        }),
        ("funding_history", FUNDING_URL, 1024 * 1024, [{
            "symbol": "ETHUSDT", "fundingTime": 1787716800000,
            "fundingRate": "-0.0001", "markPrice": "3310.25",
            "rateType": "Regular",
        }]),
    )


def _outer_document(latest="3310"):
    live_bytes, live = _live_capture_bytes(latest=latest)
    requests = []
    for index, (kind, url, limit, payload) in enumerate(_payloads()):
        body = canonical_json(payload).encode("utf-8")
        response = PublicHttpResponse(
            status=200, final_url=url, headers={"Content-Type": "application/json"},
            body=body, monotonic_rtt_ms=100,
            request_started_at=f"2026-08-26T04:04:{10 + index:02d}.000Z",
            response_received_at=f"2026-08-26T04:04:{10 + index:02d}.100Z",
        )
        identity = {"request_kind": kind, "method": "GET", "url": url, "max_body_bytes": limit}
        attempt = attempt_document(response, 1)
        attempt["selected_headers"]["content_type_or_null"] = "application/json"
        requests.append({
            "request": {"request_id": stable_id("challenger_replacement_public_market_request", identity), **identity},
            "attempts": [attempt],
            "selected_success_attempt_index": 0,
        })
    plan = fixture_v3_plan()
    opportunity = {
        "opportunity_id": opportunity_id_for(SCHEDULED_FOR), "sequence": 1,
        "scheduled_for": SCHEDULED_FOR, "captured_at": CAPTURED_AT,
    }
    document = {
        "$schema": "./challenger-replacement-public-market-capture-v2.schema.json",
        "schema_version": "2.1.0", "capture_id": "", "capture_hash": "0" * 64,
        "evidence_qualification": "PUBLIC_MARKET_CAPTURE_V2_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER",
        "plan": {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]},
        "build_identity": deepcopy(V076_BUILD), "opportunity": opportunity,
        "nested_live_capture": {
            "canonical_base64": base64.b64encode(live_bytes).decode("ascii"),
            "sha256": hashlib.sha256(live_bytes).hexdigest(),
            "capture_id": live["capture_id"], "capture_hash": live["capture_hash"],
        },
        "requests": requests,
        "normalized": {
            "bars": deepcopy(live["rows"]),
            "quotes": {
                "spot": {"bid": "3309.9", "ask": "3310.1"},
                "perpetual": {"bid": "3309.8", "ask": "3310.2", "mark": "3310.25"},
            },
            "funding_records": [{
                "funding_time": SCHEDULED_FOR, "rate": "-0.0001",
                "mark": "3310.25", "rate_type": "Regular",
            }],
            "simulation_rules": {
                "spot": {"price_tick": "0.01", "min_quantity": "0.0002", "max_quantity": "900", "quantity_step": "0.0002", "min_notional": "6"},
                "perpetual": {"price_tick": "0.1", "min_quantity": "0.002", "max_quantity": "800", "quantity_step": "0.002", "min_notional": "5", "contract_multiplier": "1"},
            },
        },
        "authority": {
            "network_request_count": 10, "credentials_allowed": False,
            "account_requests_allowed": False, "broker_requests_allowed": False,
            "orders_allowed": False, "fund_movement_allowed": False,
        },
    }
    identity = {
        "plan": document["plan"], "build_identity": document["build_identity"],
        "opportunity": document["opportunity"],
        "nested_live_capture_sha256": document["nested_live_capture"]["sha256"],
    }
    document["capture_id"] = stable_id("challenger_replacement_public_market_capture", identity)
    document["capture_hash"] = artifact_self_hash(document, "capture_hash")
    return document


def _canonical_capture(document):
    document["capture_hash"] = artifact_self_hash(document, "capture_hash")
    return canonical_json(document).encode("utf-8")


def _request_payload(document, index):
    attempt = document["requests"][index]["attempts"][
        document["requests"][index]["selected_success_attempt_index"]
    ]
    return json.loads(base64.b64decode(attempt["response_body_base64"]))


def _replace_request_payload(document, index, payload):
    attempt = document["requests"][index]["attempts"][
        document["requests"][index]["selected_success_attempt_index"]
    ]
    body = canonical_json(payload).encode("utf-8")
    attempt["body_size_bytes"] = len(body)
    attempt["body_sha256"] = hashlib.sha256(body).hexdigest()
    attempt["response_body_base64"] = base64.b64encode(body).decode("ascii")


class PublicMarketCaptureCapabilityTests(unittest.TestCase):
    def test_capability_cannot_be_constructed_by_caller(self):
        with self.assertRaises(TypeError):
            ChallengerReplacementPublicMarketCapture(document={"forged": True}, canonical_bytes=b"{}")


class PublicMarketCaptureLoaderTests(unittest.TestCase):
    def _assert_invalid(self, document_or_bytes, reason):
        body = (
            document_or_bytes
            if isinstance(document_or_bytes, bytes)
            else _canonical_capture(document_or_bytes)
        )
        with self.assertRaisesRegex(
            ChallengerReplacementPublicMarketCaptureError,
            f"^{reason}$",
        ):
            load_challenger_replacement_public_market_capture_bytes(
                body,
                plan=fixture_v3_plan(),
                build_identity=V076_BUILD,
                previous_source_bundle=None,
            )

    def test_valid_composite_replays_to_exact_normalized_evidence(self):
        document = _outer_document()
        body = canonical_json(document).encode("utf-8")
        loaded = load_challenger_replacement_public_market_capture_bytes(
            body, plan=fixture_v3_plan(), build_identity=V076_BUILD,
            previous_source_bundle=None,
        )
        self.assertIsInstance(loaded, ChallengerReplacementPublicMarketCapture)
        self.assertEqual(loaded.canonical_bytes, body)
        self.assertEqual(loaded.document, document)
        self.assertEqual(loaded.document["normalized"]["funding_records"], [{
            "funding_time": "2026-08-26T04:00:00.000Z", "rate": "-0.0001",
            "mark": "3310.25", "rate_type": "Regular",
        }])
        self.assertNotIn("last", loaded.document["normalized"]["quotes"]["spot"])

    def test_current_funding_compatibility_evidence_is_build_bound(self):
        expected = {
            "docs/binance-funding-rate-type-compatibility.md",
            "tests/fixtures/challenger_replacement_v076/"
            "public-market-capture-v2.1.json",
            "tests/fixtures/challenger_replacement_v076/"
            "public-simulation-golden-v2.1.json",
        }

        actual = set(EvaluatorBuild.expected_file_paths(
            Path(__file__).resolve().parents[1]
        ))

        self.assertTrue(expected <= actual, expected - actual)

    def test_schema_and_loader_accept_formal_candidate_identity(self):
        document = _outer_document()
        document["build_identity"] = deepcopy(V076_FORMAL_BUILD)
        document["capture_id"] = stable_id(
            "challenger_replacement_public_market_capture",
            {
                "plan": document["plan"],
                "build_identity": document["build_identity"],
                "opportunity": document["opportunity"],
                "nested_live_capture_sha256": document["nested_live_capture"]["sha256"],
            },
        )
        body = _canonical_capture(document)

        loaded = load_challenger_replacement_public_market_capture_bytes(
            body, plan=fixture_v3_plan(), build_identity=V076_FORMAL_BUILD,
            previous_source_bundle=None,
        )

        self.assertEqual(loaded.document["build_identity"], V076_FORMAL_BUILD)

    def test_schema_rejects_legacy_seven_key_v076_release_identity(self):
        schema = json.loads(
            resources.files("crypto_quant").joinpath(
                "schemas",
                "challenger-replacement-public-market-capture-v2.schema.json",
            ).read_text(encoding="utf-8")
        )
        document = _outer_document()
        document["build_identity"]["release_tag"] = "v0.76.0"

        errors = tuple(Draft202012Validator(schema).iter_errors(document))

        self.assertTrue(errors)

    def test_schema_couples_version_to_normalized_funding_shape(self):
        schema = json.loads(
            resources.files("crypto_quant").joinpath(
                "schemas",
                "challenger-replacement-public-market-capture-v2.schema.json",
            ).read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)

        current_shape_under_legacy_version = _outer_document()
        current_shape_under_legacy_version["schema_version"] = "2.0.0"
        self.assertTrue(tuple(validator.iter_errors(
            current_shape_under_legacy_version
        )))

        legacy_shape_under_current_version = _outer_document()
        del legacy_shape_under_current_version["normalized"][
            "funding_records"
        ][0]["rate_type"]
        self.assertTrue(tuple(validator.iter_errors(
            legacy_shape_under_current_version
        )))

    def test_selected_response_without_json_content_type_fails_closed(self):
        document = _outer_document()
        document["requests"][0]["attempts"][0]["selected_headers"][
            "content_type_or_null"
        ] = None

        with self.assertRaisesRegex(
            ChallengerReplacementPublicMarketCaptureError,
            "^PUBLIC_MARKET_CAPTURE_ATTEMPT_INVALID$",
        ):
            load_challenger_replacement_public_market_capture_bytes(
                _canonical_capture(document),
                plan=fixture_v3_plan(),
                build_identity=V076_BUILD,
                previous_source_bundle=None,
            )

    def test_transport_failure_then_success_is_replayed_as_two_attempts(self):
        document = _outer_document()
        failed = transport_failure_attempt(
            1,
            started=datetime(2026, 8, 26, 4, 4, 9, tzinfo=timezone.utc),
            received=datetime(
                2026, 8, 26, 4, 4, 9, 100000, tzinfo=timezone.utc
            ),
        )
        failed["selected_headers"]["content_type_or_null"] = None
        success = document["requests"][0]["attempts"][0]
        success["sequence"] = 2
        document["requests"][0]["attempts"] = [failed, success]
        document["requests"][0]["selected_success_attempt_index"] = 1
        document["authority"]["network_request_count"] = 11

        loaded = load_challenger_replacement_public_market_capture_bytes(
            _canonical_capture(document),
            plan=fixture_v3_plan(),
            build_identity=V076_BUILD,
            previous_source_bundle=None,
        )

        self.assertEqual(
            loaded.document["requests"][0]["attempts"][0]["outcome"],
            "TRANSPORT_ERROR",
        )
        self.assertEqual(
            loaded.document["authority"]["network_request_count"], 11
        )

    def test_exchange_millisecond_times_never_cross_a_binary_float_boundary(self):
        class NoBinaryFloatDatetime:
            fromisoformat = staticmethod(datetime.fromisoformat)

            @staticmethod
            def fromtimestamp(value, tz=None):
                if isinstance(value, float):
                    raise AssertionError("binary float timestamp")
                return datetime.fromtimestamp(value, tz=tz)

        document = _outer_document()
        with patch(
            "crypto_quant.challenger_replacement_public_market_capture.datetime",
            NoBinaryFloatDatetime,
        ):
            loaded = load_challenger_replacement_public_market_capture_bytes(
                _canonical_capture(document),
                plan=fixture_v3_plan(),
                build_identity=V076_BUILD,
                previous_source_bundle=None,
            )

        self.assertEqual(
            loaded.document["normalized"]["quotes"]["perpetual"]["mark"],
            "3310.25",
        )

    def test_response_before_the_opportunity_window_fails_closed(self):
        document = _outer_document()
        attempt = document["requests"][0]["attempts"][0]
        attempt["request_started_at"] = "2026-08-26T03:59:59.000Z"
        attempt["response_received_at"] = "2026-08-26T03:59:59.100Z"

        with self.assertRaisesRegex(
            ChallengerReplacementPublicMarketCaptureError,
            "^PUBLIC_MARKET_CAPTURE_ATTEMPT_INVALID$",
        ):
            load_challenger_replacement_public_market_capture_bytes(
                _canonical_capture(document),
                plan=fixture_v3_plan(),
                build_identity=V076_BUILD,
                previous_source_bundle=None,
            )

    def test_conflicting_applicable_spot_minimum_notionals_fail_closed(self):
        document = _outer_document()
        payload = _request_payload(document, 0)
        payload["symbols"][0]["filters"].append({
            "filterType": "MIN_NOTIONAL",
            "minNotional": "7",
            "applyToMarket": True,
        })
        _replace_request_payload(document, 0, payload)
        document["normalized"]["simulation_rules"]["spot"][
            "min_notional"
        ] = "7"

        with self.assertRaisesRegex(
            ChallengerReplacementPublicMarketCaptureError,
            "^PUBLIC_MARKET_CAPTURE_RULES_INVALID$",
        ):
            load_challenger_replacement_public_market_capture_bytes(
                _canonical_capture(document),
                plan=fixture_v3_plan(),
                build_identity=V076_BUILD,
                previous_source_bundle=None,
            )

    def test_unknown_spot_minimum_notional_applicability_fails_closed(self):
        document = _outer_document()
        payload = _request_payload(document, 0)
        min_notional = next(
            item
            for item in payload["symbols"][0]["filters"]
            if item["filterType"] == "MIN_NOTIONAL"
        )
        min_notional["applyToMarket"] = "true"
        _replace_request_payload(document, 0, payload)

        with self.assertRaisesRegex(
            ChallengerReplacementPublicMarketCaptureError,
            "^PUBLIC_MARKET_CAPTURE_RULES_INVALID$",
        ):
            load_challenger_replacement_public_market_capture_bytes(
                _canonical_capture(document),
                plan=fixture_v3_plan(),
                build_identity=V076_BUILD,
                previous_source_bundle=None,
            )

    def test_revised_funding_record_shape_fails_closed(self):
        document = _outer_document()
        payload = _request_payload(document, 5)
        payload[0]["revision"] = "unexpected"
        _replace_request_payload(document, 5, payload)

        with self.assertRaisesRegex(
            ChallengerReplacementPublicMarketCaptureError,
            "^PUBLIC_MARKET_CAPTURE_FUNDING_INVALID$",
        ):
            load_challenger_replacement_public_market_capture_bytes(
                _canonical_capture(document),
                plan=fixture_v3_plan(),
                build_identity=V076_BUILD,
                previous_source_bundle=None,
            )

    def test_schema_rejects_unknown_nested_request_leaf(self):
        schema = json.loads(
            resources.files("crypto_quant").joinpath(
                "schemas",
                "challenger-replacement-public-market-capture-v2.schema.json",
            ).read_text(encoding="utf-8")
        )
        document = _outer_document()
        document["requests"][0]["request"]["unreviewed"] = True

        errors = tuple(Draft202012Validator(schema).iter_errors(document))

        self.assertTrue(errors)

    def test_duplicate_key_float_and_noncanonical_bytes_are_rejected(self):
        body = _canonical_capture(_outer_document())
        duplicate = body.replace(
            b'"schema_version":"2.1.0"',
            b'"schema_version":"2.1.0","schema_version":"2.1.0"',
            1,
        )
        floating = body.replace(b'"sequence":1', b'"sequence":1.0', 1)

        for candidate, reason in (
            (duplicate, "PUBLIC_MARKET_CAPTURE_JSON_INVALID"),
            (floating, "PUBLIC_MARKET_CAPTURE_JSON_INVALID"),
            (body + b"\n", "PUBLIC_MARKET_CAPTURE_CANONICAL_BYTES_REQUIRED"),
        ):
            with self.subTest(reason=reason):
                self._assert_invalid(candidate, reason)

    def test_request_url_body_hash_and_authority_tampering_are_rejected(self):
        cases = []
        wrong_url = _outer_document()
        wrong_url["requests"][0]["request"]["url"] += "&extra=true"
        cases.append((wrong_url, "PUBLIC_MARKET_CAPTURE_REQUEST_INVALID"))

        wrong_hash = _outer_document()
        wrong_hash["requests"][1]["attempts"][0]["body_sha256"] = "0" * 64
        cases.append((wrong_hash, "PUBLIC_MARKET_CAPTURE_ATTEMPT_INVALID"))

        wrong_count = _outer_document()
        wrong_count["authority"]["network_request_count"] = 11
        cases.append((wrong_count, "PUBLIC_MARKET_CAPTURE_AUTHORITY_INVALID"))

        for document, reason in cases:
            with self.subTest(reason=reason):
                self._assert_invalid(document, reason)

    def test_invalid_quotes_and_mark_are_rejected(self):
        crossed = _outer_document()
        spot = _request_payload(crossed, 1)
        spot["bidPrice"] = "3311"
        _replace_request_payload(crossed, 1, spot)

        zero_mark = _outer_document()
        mark = _request_payload(zero_mark, 4)
        mark["markPrice"] = "0"
        _replace_request_payload(zero_mark, 4, mark)

        stale_mark = _outer_document()
        mark = _request_payload(stale_mark, 4)
        mark["time"] = 1787716199999
        _replace_request_payload(stale_mark, 4, mark)

        pre_boundary_mark = _outer_document()
        mark = _request_payload(pre_boundary_mark, 4)
        mark["time"] = 1787716799999
        _replace_request_payload(pre_boundary_mark, 4, mark)

        for document, reason in (
            (crossed, "PUBLIC_MARKET_CAPTURE_QUOTE_INVALID"),
            (zero_mark, "PUBLIC_MARKET_CAPTURE_DECIMAL_INVALID"),
            (stale_mark, "PUBLIC_MARKET_CAPTURE_QUOTE_INVALID"),
            (pre_boundary_mark, "PUBLIC_MARKET_CAPTURE_QUOTE_INVALID"),
        ):
            with self.subTest(reason=reason):
                self._assert_invalid(document, reason)

    def test_current_funding_rate_types_replay_with_type_preserved(self):
        capture_hashes = {}
        for rate_type in ("Regular", "Special"):
            document = _outer_document()
            funding = _request_payload(document, 5)
            funding[0]["rateType"] = rate_type
            _replace_request_payload(document, 5, funding)
            document["normalized"]["funding_records"][0]["rate_type"] = rate_type

            with self.subTest(rate_type=rate_type):
                loaded = load_challenger_replacement_public_market_capture_bytes(
                    _canonical_capture(document),
                    plan=fixture_v3_plan(),
                    build_identity=V076_BUILD,
                    previous_source_bundle=None,
                )
                self.assertEqual(
                    loaded.document["normalized"]["funding_records"],
                    [{
                        "funding_time": SCHEDULED_FOR,
                        "rate": "-0.0001",
                        "mark": "3310.25",
                        "rate_type": rate_type,
                    }],
                )
                self.assertEqual(
                    _request_payload(loaded.document, 5)[0]["rateType"], rate_type
                )
                capture_hashes[rate_type] = loaded.document["capture_hash"]

        self.assertNotEqual(
            capture_hashes["Regular"], capture_hashes["Special"]
        )

    def test_legacy_funding_shape_replays_only_as_schema_v2_0(self):
        legacy = _outer_document()
        funding = _request_payload(legacy, 5)
        funding[0]["fundingRateType"] = "REGULAR"
        del funding[0]["rateType"]
        _replace_request_payload(legacy, 5, funding)
        legacy["schema_version"] = "2.0.0"
        del legacy["normalized"]["funding_records"][0]["rate_type"]

        loaded = load_challenger_replacement_public_market_capture_bytes(
            _canonical_capture(legacy),
            plan=fixture_v3_plan(),
            build_identity=V076_BUILD,
            previous_source_bundle=None,
        )

        self.assertEqual(loaded.document["schema_version"], "2.0.0")
        self.assertNotIn(
            "rate_type", loaded.document["normalized"]["funding_records"][0]
        )

        legacy_under_current_schema = deepcopy(legacy)
        legacy_under_current_schema["schema_version"] = "2.1.0"
        self._assert_invalid(
            legacy_under_current_schema, "PUBLIC_MARKET_CAPTURE_SCHEMA_INVALID"
        )

    def test_current_funding_type_field_matrix_fails_closed(self):
        cases = []

        missing = _outer_document()
        funding = _request_payload(missing, 5)
        del funding[0]["rateType"]
        _replace_request_payload(missing, 5, funding)
        cases.append(("missing", missing))

        dual = _outer_document()
        funding = _request_payload(dual, 5)
        funding[0]["rateType"] = "Special"
        funding[0]["fundingRateType"] = "REGULAR"
        _replace_request_payload(dual, 5, funding)
        cases.append(("dual_conflict", dual))

        legacy_only = _outer_document()
        funding = _request_payload(legacy_only, 5)
        funding[0]["fundingRateType"] = "REGULAR"
        del funding[0]["rateType"]
        _replace_request_payload(legacy_only, 5, funding)
        cases.append(("legacy_in_current_schema", legacy_only))

        for value in ("REGULAR", "regular", "Special ", "", None, 1):
            unknown = _outer_document()
            funding = _request_payload(unknown, 5)
            funding[0]["rateType"] = value
            _replace_request_payload(unknown, 5, funding)
            cases.append((f"unknown_{value!r}", unknown))

        for value in ([], {}):
            unhashable = _outer_document()
            funding = _request_payload(unhashable, 5)
            funding[0]["rateType"] = value
            _replace_request_payload(unhashable, 5, funding)
            cases.append((f"unhashable_{type(value).__name__}", unhashable))

        for name, document in cases:
            with self.subTest(case=name):
                self._assert_invalid(
                    document, "PUBLIC_MARKET_CAPTURE_FUNDING_INVALID"
                )

    def test_current_funding_illegal_values_fail_closed(self):
        cases = []
        for field, value, reason in (
            ("fundingRate", "NaN", "PUBLIC_MARKET_CAPTURE_DECIMAL_INVALID"),
            ("fundingRate", "Infinity", "PUBLIC_MARKET_CAPTURE_DECIMAL_INVALID"),
            ("fundingRate", "-0", "PUBLIC_MARKET_CAPTURE_DECIMAL_INVALID"),
            ("fundingRate", 0, "PUBLIC_MARKET_CAPTURE_DECIMAL_INVALID"),
            ("markPrice", "0", "PUBLIC_MARKET_CAPTURE_DECIMAL_INVALID"),
            ("fundingTime", True, "PUBLIC_MARKET_CAPTURE_FUNDING_INVALID"),
            ("fundingTime", 2**53 - 1, "PUBLIC_MARKET_CAPTURE_TIME_INVALID"),
            ("fundingTime", -(2**53) + 1, "PUBLIC_MARKET_CAPTURE_TIME_INVALID"),
        ):
            document = _outer_document()
            funding = _request_payload(document, 5)
            funding[0][field] = value
            _replace_request_payload(document, 5, funding)
            cases.append((field, value, reason, document))

        for field, value, reason, document in cases:
            with self.subTest(field=field, value=value):
                self._assert_invalid(document, reason)

    def test_funding_interval_order_type_and_limit_are_rejected(self):
        outside = _outer_document()
        funding = _request_payload(outside, 5)
        funding[0]["fundingTime"] = 1787702400000
        _replace_request_payload(outside, 5, funding)

        unknown_type = _outer_document()
        funding = _request_payload(unknown_type, 5)
        funding[0]["rateType"] = "REGULAR"
        _replace_request_payload(unknown_type, 5, funding)

        duplicate = _outer_document()
        funding = _request_payload(duplicate, 5)
        funding.append(deepcopy(funding[0]))
        _replace_request_payload(duplicate, 5, funding)

        same_time_different_type = _outer_document()
        funding = _request_payload(same_time_different_type, 5)
        special = deepcopy(funding[0])
        special["rateType"] = "Special"
        funding.append(special)
        _replace_request_payload(same_time_different_type, 5, funding)

        overflow = _outer_document()
        funding = _request_payload(overflow, 5) * 17
        _replace_request_payload(overflow, 5, funding)

        for document in (
            outside, unknown_type, duplicate, same_time_different_type, overflow,
        ):
            with self.subTest(document=document["capture_id"]):
                self._assert_invalid(
                    document, "PUBLIC_MARKET_CAPTURE_FUNDING_INVALID"
                )

    def test_market_quantity_filter_absent_or_disabled_uses_lot_size(self):
        for mode in ("absent", "disabled"):
            document = _outer_document()
            payload = _request_payload(document, 0)
            filters = payload["symbols"][0]["filters"]
            market = next(
                item for item in filters if item["filterType"] == "MARKET_LOT_SIZE"
            )
            if mode == "absent":
                filters.remove(market)
            else:
                market.update({"minQty": "0", "maxQty": "0", "stepSize": "0"})
            _replace_request_payload(document, 0, payload)
            document["normalized"]["simulation_rules"]["spot"].update({
                "min_quantity": "0.0001",
                "max_quantity": "1000",
                "quantity_step": "0.0001",
            })

            with self.subTest(mode=mode):
                loaded = load_challenger_replacement_public_market_capture_bytes(
                    _canonical_capture(document),
                    plan=fixture_v3_plan(),
                    build_identity=V076_BUILD,
                    previous_source_bundle=None,
                )
                self.assertEqual(
                    loaded.document["normalized"]["simulation_rules"]["spot"]
                    ["quantity_step"],
                    "0.0001",
                )

    def test_empty_and_four_record_funding_intervals_replay_exactly(self):
        empty = _outer_document()
        _replace_request_payload(empty, 5, [])
        empty["normalized"]["funding_records"] = []

        four = _outer_document()
        raw = [
            {
                "symbol": "ETHUSDT",
                "fundingTime": millis,
                "fundingRate": rate,
                "markPrice": mark,
                "rateType": "Regular",
            }
            for millis, rate, mark in (
                (1787706000000, "-0.0004", "3301"),
                (1787709600000, "-0.0003", "3302"),
                (1787713200000, "-0.0002", "3303"),
                (1787716800000, "-0.0001", "3310.25"),
            )
        ]
        _replace_request_payload(four, 5, raw)
        four["normalized"]["funding_records"] = [
            {
                "funding_time": time, "rate": rate, "mark": mark,
                "rate_type": "Regular",
            }
            for time, rate, mark in (
                ("2026-08-26T01:00:00.000Z", "-0.0004", "3301"),
                ("2026-08-26T02:00:00.000Z", "-0.0003", "3302"),
                ("2026-08-26T03:00:00.000Z", "-0.0002", "3303"),
                ("2026-08-26T04:00:00.000Z", "-0.0001", "3310.25"),
            )
        ]

        for document, expected_count in ((empty, 0), (four, 4)):
            with self.subTest(expected_count=expected_count):
                loaded = load_challenger_replacement_public_market_capture_bytes(
                    _canonical_capture(document),
                    plan=fixture_v3_plan(),
                    build_identity=V076_BUILD,
                    previous_source_bundle=None,
                )
                self.assertEqual(
                    len(loaded.document["normalized"]["funding_records"]),
                    expected_count,
                )

    def test_one_and_four_mebibyte_response_limits_fail_before_parsing(self):
        for index, limit in ((0, 1024 * 1024), (2, 4 * 1024 * 1024)):
            document = _outer_document()
            payload = _request_payload(document, index)
            payload["padding"] = "x" * limit
            _replace_request_payload(document, index, payload)

            with self.subTest(index=index, limit=limit):
                self._assert_invalid(
                    document, "PUBLIC_MARKET_CAPTURE_ATTEMPT_INVALID"
                )

    def test_symbol_status_request_order_and_normalized_decimal_are_bound(self):
        wrong_status = _outer_document()
        payload = _request_payload(wrong_status, 0)
        payload["symbols"][0]["status"] = "BREAK"
        _replace_request_payload(wrong_status, 0, payload)

        duplicate_symbol = _outer_document()
        payload = _request_payload(duplicate_symbol, 2)
        payload["symbols"].append(deepcopy(payload["symbols"][0]))
        _replace_request_payload(duplicate_symbol, 2, payload)

        wrong_order = _outer_document()
        wrong_order["requests"][0], wrong_order["requests"][1] = (
            wrong_order["requests"][1],
            wrong_order["requests"][0],
        )

        noncanonical = _outer_document()
        noncanonical["normalized"]["quotes"]["spot"]["bid"] = "3309.90"

        wrong_rate_type = _outer_document()
        wrong_rate_type["normalized"]["funding_records"][0]["rate_type"] = (
            "Special"
        )

        for document, reason in (
            (wrong_status, "PUBLIC_MARKET_CAPTURE_RULES_INVALID"),
            (duplicate_symbol, "PUBLIC_MARKET_CAPTURE_RULES_INVALID"),
            (wrong_order, "PUBLIC_MARKET_CAPTURE_REQUEST_INVALID"),
            (noncanonical, "PUBLIC_MARKET_CAPTURE_NORMALIZED_INVALID"),
            (wrong_rate_type, "PUBLIC_MARKET_CAPTURE_NORMALIZED_INVALID"),
        ):
            with self.subTest(reason=reason):
                self._assert_invalid(document, reason)

    def test_missing_applicable_spot_minimum_notional_fails_closed(self):
        document = _outer_document()
        payload = _request_payload(document, 0)
        for item in payload["symbols"][0]["filters"]:
            if item["filterType"] == "MIN_NOTIONAL":
                item["applyToMarket"] = False
            elif item["filterType"] == "NOTIONAL":
                item["applyMinToMarket"] = False
        _replace_request_payload(document, 0, payload)

        self._assert_invalid(document, "PUBLIC_MARKET_CAPTURE_RULES_INVALID")

    def test_nested_live_capture_overlap_revision_is_not_hidden(self):
        document = _outer_document()
        previous = {
            "klines": [deepcopy(document["normalized"]["bars"][0])]
            + deepcopy(document["normalized"]["bars"][:20])
        }
        previous["klines"][1]["close"] = "99"

        with self.assertRaisesRegex(
            ChallengerReplacementPublicMarketCaptureError,
            "^PUBLIC_MARKET_CAPTURE_NESTED_INVALID$",
        ):
            load_challenger_replacement_public_market_capture_bytes(
                _canonical_capture(document),
                plan=fixture_v3_plan(),
                build_identity=V076_BUILD,
                previous_source_bundle=previous,
            )

    def test_legacy_committed_public_market_capture_replays_to_frozen_identity(self):
        body = LEGACY_COMMITTED_CAPTURE.read_bytes()

        loaded = load_challenger_replacement_public_market_capture_bytes(
            body,
            plan=fixture_v3_plan(),
            build_identity=V076_BUILD,
            previous_source_bundle=None,
        )

        self.assertEqual(
            loaded.document["capture_id"],
            "challenger_replacement_public_market_capture_"
            "39552325dfbc524f2e3787c220a23e7dcf06bf231c005b9e610a837a0adeb248",
        )
        self.assertEqual(
            loaded.document["capture_hash"],
            "eddecf6df397b2c025f974932ae4477b246e8fb4456d1a30f248b9d536f48a0c",
        )

    def test_current_committed_public_market_capture_replays_to_frozen_identity(self):
        body = CURRENT_COMMITTED_CAPTURE.read_bytes()

        loaded = load_challenger_replacement_public_market_capture_bytes(
            body,
            plan=fixture_v3_plan(),
            build_identity=V076_BUILD,
            previous_source_bundle=None,
        )

        self.assertEqual(loaded.canonical_bytes, body)
        self.assertEqual(loaded.document["schema_version"], "2.1.0")
        self.assertEqual(
            loaded.document["capture_id"],
            "challenger_replacement_public_market_capture_"
            "39552325dfbc524f2e3787c220a23e7dcf06bf231c005b9e610a837a0adeb248",
        )
        self.assertEqual(
            loaded.document["capture_hash"],
            "7c0d202a338085623b7e463e3e81d6b96053d8d8ef9a2b96f041d13b98f2abf7",
        )

    def test_nested_capture_rejects_noncanonical_base64_pad_bits(self):
        document = _outer_document()
        encoded = document["nested_live_capture"]["canonical_base64"]
        self.assertTrue(encoded.endswith("="))
        document["nested_live_capture"]["canonical_base64"] = (
            encoded[:-2] + "1="
        )

        self._assert_invalid(document, "PUBLIC_MARKET_CAPTURE_NESTED_INVALID")


class _PublicCaptureState(ChallengerReplacementOpportunityState):
    def __init__(self):
        self.plan = fixture_v3_plan()
        self.build_identity = deepcopy(V076_BUILD)
        self.projection = {
            "failed_opportunity_count": 0,
            "active_opportunity_id": None,
            "_previous_observed_source_bytes": None,
        }

    def _replay(self):
        return deepcopy(self.projection)


class PublicMarketAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.state = _PublicCaptureState()
        self.requests = []
        self.sleeps = []
        self.live_states = []

    def _responses(self):
        responses = []
        for index, (_kind, url, _limit, payload) in enumerate(_payloads()):
            responses.append(PublicHttpResponse(
                status=200,
                final_url=url,
                headers={"Content-Type": "application/json"},
                body=canonical_json(payload).encode("utf-8"),
                monotonic_rtt_ms=100,
                request_started_at=f"2026-08-26T04:04:{10 + index:02d}.000Z",
                response_received_at=f"2026-08-26T04:04:{10 + index:02d}.100Z",
            ))
        return responses

    def _acquire_from_pending(self, pending):
        live_bytes, live_document = _live_capture_bytes()
        nested = type("NestedCapture", (), {
            "canonical_bytes": live_bytes,
            "document": live_document,
        })()
        pending = list(pending)

        def acquire_live(*, state):
            self.live_states.append(state)
            return nested

        def open_request(request, *, max_body_bytes):
            self.requests.append((request, max_body_bytes))
            candidate = pending.pop(0)
            if isinstance(candidate, BaseException):
                raise candidate
            return candidate

        with patch.object(
            public_capture_module,
            "_acquire_live_capture",
            side_effect=acquire_live,
        ), patch.object(
            public_capture_module,
            "_open_fixed_public_request",
            side_effect=open_request,
        ), patch.object(
            public_capture_module,
            "_wall_now",
            return_value=datetime(
                2026, 8, 26, 4, 4, 9, tzinfo=timezone.utc
            ),
        ), patch.object(
            public_capture_module,
            "_sleep",
            side_effect=self.sleeps.append,
        ):
            return (
                public_capture_module.acquire_challenger_replacement_public_market_capture(
                    state=self.state
                )
            )

    def test_v3_state_uses_a_read_only_v067_acquisition_facade(self):
        self._acquire_from_pending(self._responses())

        self.assertEqual(len(self.live_states), 1)
        facade = self.live_states[0]
        self.assertIsNot(facade, self.state)
        self.assertEqual(facade.plan, fixture_plan())
        self.assertEqual(facade.build_identity, V067_BUILD)
        self.assertEqual(facade._replay()["next_required_slot"], {
            "sequence": 1,
            "scheduled_for": None,
        })
        self.assertIsNone(facade._replay()["_previous_source_bundle"])

    def test_fresh_acquisition_rejects_legacy_project_funding_field(self):
        responses = self._responses()
        funding = json.loads(responses[5].body)
        funding[0]["fundingRateType"] = "REGULAR"
        del funding[0]["rateType"]
        responses[5] = replace(
            responses[5], body=canonical_json(funding).encode("utf-8")
        )

        with self.assertRaisesRegex(
            ChallengerReplacementPublicMarketCaptureError,
            "^PUBLIC_MARKET_CAPTURE_FUNDING_INVALID$",
        ):
            self._acquire_from_pending(responses)

    def test_exact_v067_then_six_request_order_replays_golden_capture(self):
        live_bytes, live_document = _live_capture_bytes()
        nested = type("NestedCapture", (), {
            "canonical_bytes": live_bytes,
            "document": live_document,
        })()
        pending = self._responses()

        def open_request(request, *, max_body_bytes):
            self.requests.append((request, max_body_bytes))
            return pending.pop(0)

        with patch.object(
            public_capture_module,
            "_acquire_live_capture",
            return_value=nested,
            create=True,
        ), patch.object(
            public_capture_module,
            "_open_fixed_public_request",
            side_effect=open_request,
            create=True,
        ), patch.object(
            public_capture_module,
            "_sleep",
            side_effect=self.sleeps.append,
            create=True,
        ), patch.object(
            OpenerDirector,
            "open",
            side_effect=AssertionError("network forbidden"),
        ):
            capture = (
                public_capture_module.acquire_challenger_replacement_public_market_capture(
                    state=self.state
                )
            )

        self.assertEqual(capture.document, _outer_document())
        self.assertEqual(
            capture.canonical_bytes, CURRENT_COMMITTED_CAPTURE.read_bytes()
        )
        self.assertEqual(
            [request.full_url for request, _limit in self.requests],
            [url for _kind, url, _limit, _payload in _payloads()],
        )
        self.assertEqual(
            [limit for _request, limit in self.requests],
            [limit for _kind, _url, limit, _payload in _payloads()],
        )
        self.assertTrue(
            all(request.get_method() == "GET" for request, _ in self.requests)
        )
        self.assertTrue(all(request.data is None for request, _ in self.requests))
        self.assertEqual(self.sleeps, [])
        self.assertEqual(capture.document["authority"]["network_request_count"], 10)

    def test_transport_failure_is_recorded_then_retried_once(self):
        live_bytes, live_document = _live_capture_bytes()
        nested = type("NestedCapture", (), {
            "canonical_bytes": live_bytes,
            "document": live_document,
        })()
        responses = self._responses()
        pending = [
            PublicHttpError("PUBLIC_HTTP_TRANSPORT_FAILURE"),
            responses[0],
            *responses[1:],
        ]
        wall = iter((
            datetime(2026, 8, 26, 4, 4, 9, tzinfo=timezone.utc),
            datetime(2026, 8, 26, 4, 4, 9, 100000, tzinfo=timezone.utc),
            *(
                datetime(2026, 8, 26, 4, 4, 9, 100000, tzinfo=timezone.utc)
                for _ in range(6)
            ),
        ))

        def open_request(request, *, max_body_bytes):
            self.requests.append((request, max_body_bytes))
            candidate = pending.pop(0)
            if isinstance(candidate, BaseException):
                raise candidate
            return candidate

        with patch.object(
            public_capture_module,
            "_acquire_live_capture",
            return_value=nested,
        ), patch.object(
            public_capture_module,
            "_open_fixed_public_request",
            side_effect=open_request,
        ), patch.object(
            public_capture_module,
            "_wall_now",
            side_effect=wall,
            create=True,
        ), patch.object(
            public_capture_module,
            "_sleep",
            side_effect=self.sleeps.append,
        ):
            capture = (
                public_capture_module.acquire_challenger_replacement_public_market_capture(
                    state=self.state
                )
            )

        first_attempts = capture.document["requests"][0]["attempts"]
        self.assertEqual([item["outcome"] for item in first_attempts], [
            "TRANSPORT_ERROR", "HTTP_RESPONSE",
        ])
        self.assertEqual(self.sleeps, [1])
        self.assertEqual(capture.document["authority"]["network_request_count"], 11)

    def test_two_transient_responses_then_success_preserve_all_attempts(self):
        responses = self._responses()
        first = responses[0]
        capture = self._acquire_from_pending([
            replace(
                first, status=503,
                headers={"Content-Type": "text/plain"}, body=b'{"code":-1}',
            ),
            replace(
                first, status=429,
                headers={"Content-Type": "text/plain"}, body=b'{"code":-2}',
                request_started_at="2026-08-26T04:04:11.000Z",
                response_received_at="2026-08-26T04:04:11.100Z",
            ),
            replace(
                first,
                request_started_at="2026-08-26T04:04:12.000Z",
                response_received_at="2026-08-26T04:04:12.100Z",
            ),
            *responses[1:],
        ])

        self.assertEqual(
            [attempt["status"] for attempt in capture.document["requests"][0]["attempts"]],
            [503, 429, 200],
        )
        self.assertEqual(self.sleeps, [1, 2])
        self.assertEqual(capture.document["authority"]["network_request_count"], 12)

    def test_permanent_status_retry_exhaustion_wrong_url_and_bad_json_fail_fixed(self):
        responses = self._responses()
        first = responses[0]
        cases = (
            (
                [replace(first, status=400), *responses[1:]],
                "PUBLIC_MARKET_CAPTURE_RESPONSE_INVALID",
                1,
                [],
            ),
            (
                [
                    replace(first, status=503),
                    replace(first, status=503),
                    replace(first, status=503),
                    *responses[1:],
                ],
                "PUBLIC_MARKET_CAPTURE_RETRIES_EXHAUSTED",
                3,
                [1, 2],
            ),
            (
                [
                    PublicHttpError("PUBLIC_HTTP_TRANSPORT_FAILURE"),
                    PublicHttpError("PUBLIC_HTTP_TRANSPORT_FAILURE"),
                    PublicHttpError("PUBLIC_HTTP_TRANSPORT_FAILURE"),
                ],
                "PUBLIC_MARKET_CAPTURE_RETRIES_EXHAUSTED",
                3,
                [1, 2],
            ),
            (
                [replace(first, final_url=first.final_url + "&wrong=1"), *responses[1:]],
                "PUBLIC_MARKET_CAPTURE_RESPONSE_INVALID",
                1,
                [],
            ),
            (
                [replace(first, body=b"not-json"), *responses[1:]],
                "PUBLIC_MARKET_CAPTURE_RESPONSE_INVALID",
                1,
                [],
            ),
        )
        for pending, reason, request_count, sleeps in cases:
            with self.subTest(reason=reason, request_count=request_count):
                self.requests = []
                self.sleeps = []
                with self.assertRaisesRegex(
                    ChallengerReplacementPublicMarketCaptureError,
                    f"^{reason}$",
                ):
                    self._acquire_from_pending(pending)
                self.assertEqual(len(self.requests), request_count)
                self.assertEqual(self.sleeps, sleeps)

    def test_outer_capture_window_extends_through_later_public_responses(self):
        responses = self._responses()
        later = replace(
            responses[0],
            request_started_at="2026-08-26T04:05:00.001Z",
            response_received_at="2026-08-26T04:05:00.101Z",
        )
        capture = self._acquire_from_pending([later, *responses[1:]])
        self.assertEqual(
            capture.document["opportunity"]["captured_at"],
            "2026-08-26T04:05:00.101Z",
        )
        self.assertEqual(len(self.requests), 6)
        self.assertEqual(self.sleeps, [])

    def test_v067_clock_or_window_failure_maps_before_six_new_requests(self):
        with patch.object(
            public_capture_module,
            "_acquire_live_capture",
            side_effect=ChallengerReplacementLiveInputError(
                "CHALLENGER_REPLACEMENT_LIVE_INPUT_WINDOW_INVALID"
            ),
        ), patch.object(
            public_capture_module,
            "_open_fixed_public_request",
            side_effect=AssertionError("new endpoint must not be called"),
        ):
            with self.assertRaisesRegex(
                ChallengerReplacementPublicMarketCaptureError,
                "^PUBLIC_MARKET_CAPTURE_NESTED_INVALID$",
            ):
                public_capture_module.acquire_challenger_replacement_public_market_capture(
                    state=self.state
                )

        self.assertEqual(self.requests, [])

    def test_previous_public_capture_becomes_v067_overlap_bundle(self):
        self.state.projection["_previous_observed_source_bytes"] = (
            LEGACY_COMMITTED_CAPTURE.read_bytes()
        )
        seen = []

        def inspect_facade(*, state):
            seen.append(state._replay()["_previous_source_bundle"])
            raise ChallengerReplacementLiveInputError(
                "CHALLENGER_REPLACEMENT_LIVE_INPUT_WINDOW_INVALID"
            )

        with patch.object(
            public_capture_module,
            "_acquire_live_capture",
            side_effect=inspect_facade,
        ), patch.object(
            public_capture_module,
            "_open_fixed_public_request",
            side_effect=AssertionError("new endpoint must not be called"),
        ):
            with self.assertRaisesRegex(
                ChallengerReplacementPublicMarketCaptureError,
                "^PUBLIC_MARKET_CAPTURE_NESTED_INVALID$",
            ):
                public_capture_module.acquire_challenger_replacement_public_market_capture(
                    state=self.state
                )

        self.assertEqual(seen, [{
            "klines": _outer_document()["normalized"]["bars"],
        }])

    def test_forged_duck_typed_state_fails_before_any_request(self):
        forged = type("ForgedState", (), {
            "plan": fixture_v3_plan(),
            "build_identity": deepcopy(V076_BUILD),
            "_replay": lambda self: deepcopy(self.projection),
            "projection": deepcopy(self.state.projection),
        })()

        with patch.object(
            public_capture_module,
            "_acquire_live_capture",
            side_effect=AssertionError("nested request forbidden"),
        ), patch.object(
            public_capture_module,
            "_open_fixed_public_request",
            side_effect=AssertionError("new endpoint forbidden"),
        ):
            with self.assertRaisesRegex(
                ChallengerReplacementPublicMarketCaptureError,
                "^PUBLIC_MARKET_CAPTURE_STATE_INVALID$",
            ):
                public_capture_module.acquire_challenger_replacement_public_market_capture(
                    state=forged
                )

    def test_nested_bytes_and_document_mismatch_fails_before_new_requests(self):
        live_bytes, live_document = _live_capture_bytes()
        live_document["capture_hash"] = "0" * 64
        nested = type("NestedCapture", (), {
            "canonical_bytes": live_bytes,
            "document": live_document,
        })()

        with patch.object(
            public_capture_module,
            "_acquire_live_capture",
            return_value=nested,
        ), patch.object(
            public_capture_module,
            "_open_fixed_public_request",
            side_effect=AssertionError("new endpoint forbidden"),
        ):
            with self.assertRaisesRegex(
                ChallengerReplacementPublicMarketCaptureError,
                "^PUBLIC_MARKET_CAPTURE_NESTED_INVALID$",
            ):
                public_capture_module.acquire_challenger_replacement_public_market_capture(
                    state=self.state
                )


if __name__ == "__main__":
    unittest.main()
