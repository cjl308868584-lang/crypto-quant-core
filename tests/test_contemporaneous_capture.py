import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from crypto_quant.contemporaneous_capture import (
    CaptureError,
    ContemporaneousCapturePlan,
    PublicCaptureHttpResponse,
    build_capture_session,
    capture_once,
    capture_requests,
    capture_snapshot_attestation_hash,
    capture_snapshot_hash,
    capture_snapshot_reasons,
)


def _kline(
    close="2000.00",
    open_time=1_775_001_660_000,
    close_time=1_775_001_719_999,
):
    return [
        open_time,
        "1990.00",
        "2010.00",
        "1980.00",
        close,
        "12.50",
        close_time,
        "25000.00",
        42,
        "7.00",
        "14000.00",
        "0",
    ]


def _responses(*, kline_close="2000.00", agg_ids=(100, 101), bbo_bid="1999.00"):
    one_minute = [_kline(kline_close)]
    four_hour = [
        _kline(
            kline_close,
            open_time=1_775_001_600_000,
            close_time=1_775_015_999_999,
        )
    ]
    trades = [
        {
            "a": trade_id,
            "p": str(2000 + trade_id - 100),
            "q": "0.25",
            "f": trade_id * 2,
            "l": trade_id * 2 + 1,
            "T": 1_774_828_820_000 + trade_id,
            "m": trade_id % 2 == 0,
            "M": True,
        }
        for trade_id in agg_ids
    ]
    bbo = {
        "symbol": "ETHUSDT",
        "bidPrice": bbo_bid,
        "bidQty": "3.00",
        "askPrice": "2001.00",
        "askQty": "2.00",
    }
    return [one_minute, four_hour, trades, bbo]


class FakeTransport:
    def __init__(self, payloads, *, started="2026-04-01T00:01:00.000Z"):
        self.payloads = list(payloads)
        self.started = started
        started_at = datetime.fromisoformat(started.replace("Z", "+00:00"))
        self.received = (
            started_at.replace(microsecond=100_000)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        self.urls = []

    def get(self, request):
        self.urls.append(request.url)
        payload = self.payloads.pop(0)
        return PublicCaptureHttpResponse(
            status=200,
            final_url=request.url,
            headers={"Date": "Wed, 01 Apr 2026 00:01:00 GMT"},
            body=json.dumps(payload, separators=(",", ":")).encode(),
            request_started_at=self.started,
            response_received_at=self.received,
        )


class CapturePlanAndReceiptTests(unittest.TestCase):
    def test_plan_emits_only_four_exact_public_market_urls(self):
        plan = ContemporaneousCapturePlan.create("ETHUSDT")
        self.assertEqual(
            [request.url for request in capture_requests(plan)],
            [
                "https://data-api.binance.vision/api/v3/klines?interval=1m&limit=2&symbol=ETHUSDT",
                "https://data-api.binance.vision/api/v3/klines?interval=4h&limit=2&symbol=ETHUSDT",
                "https://data-api.binance.vision/api/v3/aggTrades?limit=100&symbol=ETHUSDT",
                "https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol=ETHUSDT",
            ],
        )
        with self.assertRaises(TypeError):
            ContemporaneousCapturePlan(symbol="ETHUSDT")
        with self.assertRaises(CaptureError):
            ContemporaneousCapturePlan.create("DOGEUSDT")

    def test_capture_rejects_bad_status_host_and_clock(self):
        plan = ContemporaneousCapturePlan.create("ETHUSDT")
        request = capture_requests(plan)[0]
        cases = [
            {"status": 429},
            {"final_url": "https://example.com/api/v3/klines"},
            {
                "request_started_at": "2026-04-01T00:01:01.000Z",
                "response_received_at": "2026-04-01T00:01:00.000Z",
            },
        ]
        for overrides in cases:
            fields = dict(
                status=200,
                final_url=request.url,
                headers={},
                body=b"[]",
                request_started_at="2026-04-01T00:01:00.000Z",
                response_received_at="2026-04-01T00:01:00.100Z",
            )
            fields.update(overrides)

            class One:
                def get(self, ignored):
                    return PublicCaptureHttpResponse(**fields)

            with self.assertRaises(CaptureError):
                capture_once(plan, One(), recorded_at="2026-04-01T00:01:00.200Z")


class ObservationAndSessionTests(unittest.TestCase):
    def test_capture_parses_source_time_and_receive_time_without_float(self):
        plan = ContemporaneousCapturePlan.create("ETHUSDT")
        batch = capture_once(
            plan,
            FakeTransport(_responses()),
            recorded_at="2026-04-01T00:01:00.200Z",
        )
        snapshot = build_capture_session(
            [batch],
            session_id="eth-smoke",
            recorded_at="2026-04-01T00:01:00.300Z",
        )
        self.assertEqual(snapshot["response_count"], 4)
        self.assertEqual(snapshot["quality_report"]["family_coverage"], [
            "SPOT_AGG_TRADE", "SPOT_BBO", "SPOT_KLINE"
        ])
        kline = next(
            item for item in snapshot["observations"]
            if item["fact_type"] == "SPOT_KLINE"
        )
        self.assertEqual(kline["event_time_basis"], "SOURCE_OPEN_TIME")
        self.assertEqual(kline["event_time"], "2026-04-01T00:01:00.000Z")
        bbo = next(
            item for item in snapshot["observations"]
            if item["fact_type"] == "SPOT_BBO"
        )
        self.assertEqual(bbo["event_time_basis"], "CLIENT_RECEIVE_TIME_PROXY")
        self.assertEqual(bbo["event_time"], bbo["available_at"])
        self.assertNotIn(".", json.dumps(snapshot["observations"][0]["source_payload"])[:1])

    def test_two_rounds_chain_kline_revision_and_count_duplicates(self):
        plan = ContemporaneousCapturePlan.create("ETHUSDT")
        first = capture_once(
            plan,
            FakeTransport(_responses(kline_close="2000.00")),
            recorded_at="2026-04-01T00:01:00.200Z",
        )
        second_transport = FakeTransport(
            _responses(kline_close="2000.50"),
            started="2026-04-01T00:02:00.000Z",
        )
        second = capture_once(
            plan,
            second_transport,
            recorded_at="2026-04-01T00:02:00.200Z",
        )
        snapshot = build_capture_session(
            [first, second],
            session_id="revision-session",
            recorded_at="2026-04-01T00:02:00.300Z",
        )
        report = snapshot["quality_report"]
        self.assertEqual(report["kline_revision_count"], 2)
        revisions = [
            item for item in snapshot["observations"]
            if item["fact_type"] == "SPOT_KLINE" and item["revision_no"] == 1
        ]
        self.assertEqual(len(revisions), 2)
        self.assertTrue(all(item["previous_observation_hash"] for item in revisions))
        self.assertGreaterEqual(report["agg_trade_duplicate_count"], 2)
        self.assertEqual(report["bbo_duplicate_count"], 1)

    def test_aggtrade_gap_is_explicit_and_bbo_limitation_is_mandatory(self):
        plan = ContemporaneousCapturePlan.create("ETHUSDT")
        batch = capture_once(
            plan,
            FakeTransport(_responses(agg_ids=(100, 102))),
            recorded_at="2026-04-01T00:01:00.200Z",
        )
        snapshot = build_capture_session(
            [batch],
            session_id="gap-session",
            recorded_at="2026-04-01T00:01:00.300Z",
        )
        report = snapshot["quality_report"]
        self.assertEqual(report["agg_trade_gap_count"], 1)
        self.assertIn(
            "BBO_SEQUENCE_UNOBSERVABLE_REST_SNAPSHOT",
            report["warnings"],
        )
        self.assertEqual(snapshot["pit_eligibility"], "CONTEMPORANEOUS_RESEARCH_ONLY")
        self.assertEqual(snapshot["paper_eligibility"], "CAPTURE_REPLAY_ONLY")

    def test_external_attestation_and_replay_detect_all_mutations(self):
        plan = ContemporaneousCapturePlan.create("ETHUSDT")
        batch = capture_once(
            plan,
            FakeTransport(_responses()),
            recorded_at="2026-04-01T00:01:00.200Z",
        )
        snapshot = build_capture_session(
            [batch],
            session_id="trusted-session",
            recorded_at="2026-04-01T00:01:00.300Z",
        )
        anchor = capture_snapshot_attestation_hash(snapshot)
        self.assertEqual(
            capture_snapshot_reasons(
                snapshot, trusted_snapshot_attestation_hashes=[anchor]
            ),
            (),
        )
        self.assertIn(
            "TRUSTED_CAPTURE_ATTESTATION_REQUIRED",
            capture_snapshot_reasons(snapshot),
        )
        changed = copy.deepcopy(snapshot)
        changed["session_id"] = "forged-session"
        changed["snapshot_hash"] = capture_snapshot_hash(changed)
        reasons = capture_snapshot_reasons(
            changed, trusted_snapshot_attestation_hashes=[anchor]
        )
        self.assertIn("TRUSTED_CAPTURE_ATTESTATION_MISMATCH", reasons)
        changed = copy.deepcopy(snapshot)
        changed["observations"][0]["payload"]["close"] = "9999"
        changed["observations"][0]["payload_hash"] = "0" * 64
        changed["observations"][0]["observation_hash"] = "0" * 64
        changed["snapshot_hash"] = capture_snapshot_hash(changed)
        self.assertIn(
            "CAPTURE_OBSERVATION_REPLAY_MISMATCH",
            capture_snapshot_reasons(
                changed, trusted_snapshot_attestation_hashes=[anchor]
            ),
        )

    def test_schema_and_raw_response_are_revalidated(self):
        plan = ContemporaneousCapturePlan.create("ETHUSDT")
        batch = capture_once(
            plan,
            FakeTransport(_responses()),
            recorded_at="2026-04-01T00:01:00.200Z",
        )
        snapshot = build_capture_session(
            [batch],
            session_id="schema-session",
            recorded_at="2026-04-01T00:01:00.300Z",
        )
        anchor = capture_snapshot_attestation_hash(snapshot)
        changed = copy.deepcopy(snapshot)
        changed["unexpected"] = True
        changed["snapshot_hash"] = capture_snapshot_hash(changed)
        self.assertIn(
            "CAPTURE_SCHEMA_INVALID",
            capture_snapshot_reasons(
                changed, trusted_snapshot_attestation_hashes=[anchor]
            ),
        )
        changed = copy.deepcopy(snapshot)
        changed["response_receipts"][0]["response_body_utf8"] = "[]"
        changed["response_receipts"][0]["body_size_bytes"] = 2
        changed["response_receipts"][0]["body_sha256"] = (
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e5b5a"
            "75ecf31b4a5a86c1f"
        )
        changed["response_receipts"][0]["receipt_hash"] = "0" * 64
        changed["response_receipts_root_hash"] = "0" * 64
        changed["snapshot_hash"] = capture_snapshot_hash(changed)
        reasons = capture_snapshot_reasons(
            changed, trusted_snapshot_attestation_hashes=[anchor]
        )
        self.assertIn("CAPTURE_OBSERVATION_REPLAY_MISMATCH", reasons)

    def test_governance_and_packaged_schemas_are_byte_identical(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(
            (
                root / "config"
                / "contemporaneous-capture-snapshot-v1.schema.json"
            ).read_bytes(),
            (
                root / "src" / "crypto_quant" / "schemas"
                / "contemporaneous-capture-snapshot-v1.schema.json"
            ).read_bytes(),
        )

    def test_closed_kline_content_change_fails_closed(self):
        plan = ContemporaneousCapturePlan.create("ETHUSDT")
        old_payload = _responses(kline_close="2000.00")
        old_payload[0] = [
            _kline(
                "2000.00",
                open_time=1_775_001_540_000,
                close_time=1_775_001_599_999,
            )
        ]
        first = capture_once(
            plan,
            FakeTransport(old_payload),
            recorded_at="2026-04-01T00:01:00.200Z",
        )
        new_payload = _responses(kline_close="2001.00")
        new_payload[0] = [
            _kline(
                "2001.00",
                open_time=1_775_001_540_000,
                close_time=1_775_001_599_999,
            )
        ]
        second = capture_once(
            plan,
            FakeTransport(new_payload, started="2026-04-01T00:02:00.000Z"),
            recorded_at="2026-04-01T00:02:00.200Z",
        )
        with self.assertRaisesRegex(CaptureError, "CLOSED_KLINE_MUTATION"):
            build_capture_session(
                [first, second],
                session_id="bad-closed",
                recorded_at="2026-04-01T00:02:00.300Z",
            )


if __name__ == "__main__":
    unittest.main()
