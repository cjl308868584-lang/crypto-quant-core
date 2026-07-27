import json
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from importlib import resources
from pathlib import Path
from unittest import mock
from urllib.request import ProxyHandler

from jsonschema import Draft202012Validator

from crypto_quant.economics import economic_snapshot_reasons
from crypto_quant.offline_paper import (
    OFFLINE_PAPER_WARNINGS,
    BinanceOfflinePaperTransport,
    OfflinePaperError,
    OfflinePaperPlan,
    PublicPaperHttpResponse,
    build_offline_paper_run,
    capture_offline_paper,
    offline_paper_requests,
    offline_paper_run_reasons,
    offline_paper_run_trust_hash,
    _read_bounded,
)


UTC = timezone.utc


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def kline(open_time, close):
    start_ms = int(open_time.timestamp() * 1000)
    return [
        start_ms,
        close,
        close,
        close,
        close,
        "10",
        start_ms + 14_400_000 - 1,
        "20000",
        20,
        "5",
        "10000",
        "0",
    ]


def warmup_body(decision_time, *, latest="2200", prior="2000"):
    first = decision_time - timedelta(hours=4 * 22)
    rows = []
    for index in range(22):
        close = prior if index < 21 else latest
        rows.append(kline(first + timedelta(hours=4 * index), close))
    return json.dumps(rows, separators=(",", ":")).encode()


def exchange_info_body():
    return json.dumps(
        {
            "timezone": "UTC",
            "serverTime": 1785100000000,
            "rateLimits": [],
            "exchangeFilters": [],
            "symbols": [
                {
                    "symbol": "ETHUSDT",
                    "status": "TRADING",
                    "baseAsset": "ETH",
                    "baseAssetPrecision": 8,
                    "quoteAsset": "USDT",
                    "quotePrecision": 8,
                    "quoteAssetPrecision": 8,
                    "baseCommissionPrecision": 8,
                    "quoteCommissionPrecision": 8,
                    "orderTypes": [
                        "LIMIT",
                        "LIMIT_MAKER",
                        "MARKET",
                        "STOP_LOSS_LIMIT",
                        "TAKE_PROFIT_LIMIT",
                    ],
                    "icebergAllowed": True,
                    "ocoAllowed": True,
                    "otoAllowed": True,
                    "quoteOrderQtyMarketAllowed": True,
                    "allowTrailingStop": True,
                    "cancelReplaceAllowed": True,
                    "amendAllowed": True,
                    "isSpotTradingAllowed": True,
                    "isMarginTradingAllowed": True,
                    "filters": [
                        {
                            "filterType": "PRICE_FILTER",
                            "minPrice": "0.01",
                            "maxPrice": "1000000",
                            "tickSize": "0.01",
                        },
                        {
                            "filterType": "LOT_SIZE",
                            "minQty": "0.0001",
                            "maxQty": "9000",
                            "stepSize": "0.0001",
                        },
                        {
                            "filterType": "MIN_NOTIONAL",
                            "minNotional": "5",
                            "applyToMarket": True,
                            "avgPriceMins": 5,
                        },
                        {
                            "filterType": "NOTIONAL",
                            "minNotional": "10",
                            "applyMinToMarket": True,
                            "maxNotional": "9000000",
                            "applyMaxToMarket": False,
                            "avgPriceMins": 5,
                        },
                    ],
                    "permissions": [],
                    "permissionSets": [["SPOT"]],
                    "defaultSelfTradePreventionMode": "EXPIRE_MAKER",
                    "allowedSelfTradePreventionModes": ["EXPIRE_MAKER"],
                }
            ],
            "sors": None,
        },
        separators=(",", ":"),
    ).encode()


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def response(request, body, start, received):
    return PublicPaperHttpResponse(
        status=200,
        final_url=request.url,
        headers={"Date": "Mon, 27 Jul 2026 00:00:00 GMT"},
        body=body,
        request_started_at=iso(start),
        response_received_at=iso(received),
    )


def valid_capture(*, latest="2200", prior="2000", ask_qty="10"):
    plan = OfflinePaperPlan.create("ETHUSDT")
    requests = offline_paper_requests(plan)
    base = datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)
    responses = [
        response(
            requests[0],
            warmup_body(base, latest=latest, prior=prior),
            base,
            base + timedelta(milliseconds=100),
        ),
        response(
            requests[1],
            exchange_info_body(),
            base + timedelta(milliseconds=110),
            base + timedelta(milliseconds=200),
        ),
        response(
            requests[2],
            json.dumps(
                {
                    "symbol": "ETHUSDT",
                    "bidPrice": "2199.90",
                    "bidQty": "8",
                    "askPrice": "2200.10",
                    "askQty": ask_qty,
                },
                separators=(",", ":"),
            ).encode(),
            base + timedelta(milliseconds=200),
            base + timedelta(milliseconds=250),
        ),
        response(
            requests[3],
            json.dumps(
                [
                    {
                        "a": 100,
                        "p": "2200",
                        "q": "0.1",
                        "f": 200,
                        "l": 200,
                        "T": int((base + timedelta(milliseconds=230)).timestamp() * 1000),
                        "m": False,
                        "M": True,
                    }
                ],
                separators=(",", ":"),
            ).encode(),
            base + timedelta(milliseconds=260),
            base + timedelta(milliseconds=300),
        ),
    ]
    transport = FakeTransport(responses)
    capture = capture_offline_paper(
        plan,
        transport,
        recorded_at=lambda: iso(base + timedelta(seconds=1)),
    )
    return capture, transport


class _Stream:
    def __init__(self, payload):
        self.payload = payload
        self.offset = 0

    def read(self, amount):
        result = self.payload[self.offset:self.offset + amount]
        self.offset += len(result)
        return result


class OfflinePaperTests(unittest.TestCase):
    def test_production_transport_disables_proxies_and_rejects_non_frozen_request(self):
        with mock.patch.dict(
            "os.environ",
            {"HTTPS_PROXY": "http://credential@example.invalid:8080"},
        ):
            transport = BinanceOfflinePaperTransport()
        self.assertFalse(
            any(
                isinstance(handler, ProxyHandler)
                for handler in transport._opener.handlers
            )
        )
        with self.assertRaisesRegex(OfflinePaperError, "PAPER_REQUEST_INVALID"):
            transport.get(object())

    def test_bounded_reader_rejects_oversized_response(self):
        with self.assertRaisesRegex(
            OfflinePaperError, "PAPER_RESPONSE_TOO_LARGE"
        ):
            _read_bounded(_Stream(b"x" * (2 * 1024 * 1024 + 1)))

    def test_plan_has_only_the_four_frozen_public_gets_in_stage_order(self):
        plan = OfflinePaperPlan.create("ETHUSDT")
        requests = offline_paper_requests(plan)
        self.assertEqual(
            [(item.stage, item.family) for item in requests],
            [
                ("DECISION_INPUT", "SPOT_KLINE_4H_WARMUP"),
                ("DECISION_INPUT", "SPOT_EXCHANGE_INFO"),
                ("EXECUTION_OBSERVATION", "SPOT_BBO"),
                ("EXECUTION_OBSERVATION", "SPOT_AGG_TRADE"),
            ],
        )
        self.assertTrue(all(item.method == "GET" for item in requests))
        self.assertTrue(
            all(item.url.startswith("https://data-api.binance.vision/api/v3/") for item in requests)
        )
        self.assertFalse(any("key" in item.url.lower() for item in requests))

    def test_capture_freezes_after_inputs_and_before_execution_observations(self):
        capture, transport = valid_capture()
        self.assertEqual(transport.requests, list(offline_paper_requests(capture.plan)))
        self.assertEqual(
            capture.decision_time,
            capture.receipts[1]["response_received_at"],
        )
        self.assertGreaterEqual(
            capture.receipts[2]["request_started_at"],
            capture.decision_time,
        )

    def test_capture_rejects_execution_request_started_before_freeze(self):
        plan = OfflinePaperPlan.create("ETHUSDT")
        requests = offline_paper_requests(plan)
        base = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
        responses = [
            response(requests[0], warmup_body(base), base, base + timedelta(milliseconds=100)),
            response(requests[1], exchange_info_body(), base, base + timedelta(milliseconds=200)),
            response(
                requests[2],
                b'{"symbol":"ETHUSDT","bidPrice":"1","bidQty":"1","askPrice":"2","askQty":"1"}',
                base + timedelta(milliseconds=199),
                base + timedelta(milliseconds=250),
            ),
        ]
        with self.assertRaisesRegex(OfflinePaperError, "PAPER_STAGE_ORDER_INVALID"):
            capture_offline_paper(
                plan,
                FakeTransport(responses),
                recorded_at=iso(base + timedelta(seconds=1)),
            )

    def test_long_baseline_builds_conservative_fill_and_two_valid_ledgers(self):
        capture, _ = valid_capture()
        run = build_offline_paper_run(
            capture,
            run_id="offline-paper-test-long",
            recorded_at="2026-07-27T12:00:02.000Z",
        )
        baseline = run["arms"]["baseline"]
        self.assertEqual(baseline["decision"]["direction"], "LONG")
        self.assertEqual(baseline["decision"]["recommended_action"], "SET_TARGET")
        self.assertEqual(baseline["decision"]["risk_bucket"], "0.25")
        self.assertEqual(baseline["fill"]["status"], "FILLED")
        self.assertEqual(baseline["fill"]["side"], "BUY")
        self.assertGreater(
            Decimal(baseline["fill"]["price"]),
            Decimal(run["market"]["bbo"]["ask_price"]),
        )
        self.assertEqual(economic_snapshot_reasons(baseline["economic_snapshot"]), ())
        self.assertEqual(
            economic_snapshot_reasons(run["arms"]["ai"]["economic_snapshot"]), ()
        )
        self.assertEqual(run["arms"]["ai"]["fill"]["status"], "NOT_RUN_NO_APPROVED_MODEL")

    def test_flat_baseline_does_not_manufacture_a_trade(self):
        capture, _ = valid_capture(latest="1900", prior="2000")
        run = build_offline_paper_run(
            capture,
            run_id="offline-paper-test-flat",
            recorded_at="2026-07-27T12:00:02.000Z",
        )
        baseline = run["arms"]["baseline"]
        self.assertEqual(baseline["decision"]["direction"], "FLAT")
        self.assertEqual(baseline["decision"]["recommended_action"], "HOLD_CURRENT")
        self.assertEqual(baseline["fill"]["status"], "NO_TRADE_SIGNAL_FLAT")
        self.assertEqual(baseline["economic_snapshot"]["fills"], [])

    def test_visible_ask_quantity_caps_fill_and_rounding_is_fail_closed(self):
        capture, _ = valid_capture(ask_qty="0.00015")
        run = build_offline_paper_run(
            capture,
            run_id="offline-paper-test-partial",
            recorded_at="2026-07-27T12:00:02.000Z",
        )
        fill = run["arms"]["baseline"]["fill"]
        self.assertEqual(fill["status"], "NO_FILL_BELOW_MIN_NOTIONAL")
        self.assertEqual(fill["rounded_quantity"], "0.0001")

    def test_exchange_info_uses_the_more_conservative_min_notional(self):
        capture, _ = valid_capture()
        run = build_offline_paper_run(
            capture,
            run_id="offline-paper-test-filters",
            recorded_at="2026-07-27T12:00:02.000Z",
        )
        self.assertEqual(run["market"]["instrument_metadata"]["min_notional"], "10")
        self.assertEqual(
            run["market"]["instrument_metadata"]["metadata_source"],
            "BINANCE_PUBLIC_EXCHANGE_INFO_RESPONSE",
        )

    def test_run_is_self_replayable_but_requires_external_trust_hash(self):
        capture, _ = valid_capture()
        run = build_offline_paper_run(
            capture,
            run_id="offline-paper-test-replay",
            recorded_at="2026-07-27T12:00:02.000Z",
        )
        trust_hash = offline_paper_run_trust_hash(run)
        self.assertEqual(offline_paper_run_reasons(run, trust_hash), ())
        self.assertIn(
            "PAPER_TRUST_HASH_MISMATCH",
            offline_paper_run_reasons(run, "0" * 64),
        )

        tampered = deepcopy(run)
        tampered["arms"]["baseline"]["fill"]["price"] = "1"
        self.assertIn(
            "PAPER_RUN_SELF_HASH_MISMATCH",
            offline_paper_run_reasons(tampered, trust_hash),
        )

    def test_profit_and_paper_claims_remain_ineligible(self):
        capture, _ = valid_capture()
        run = build_offline_paper_run(
            capture,
            run_id="offline-paper-test-eligibility",
            recorded_at="2026-07-27T12:00:02.000Z",
        )
        self.assertEqual(run["paper_eligibility"], "OFFLINE_PAPER_SMOKE_ONLY")
        self.assertEqual(
            run["profitability_eligibility"],
            "INSUFFICIENT_DURATION_AND_AI",
        )
        self.assertEqual(tuple(run["warnings"]), OFFLINE_PAPER_WARNINGS)

    def test_schema_is_packaged_byte_identically_and_rejects_extra_fields(self):
        root = Path(__file__).resolve().parents[1]
        governance = (
            root / "config" / "offline-paper-run-v1.schema.json"
        ).read_bytes()
        packaged = resources.files("crypto_quant").joinpath(
            "schemas", "offline-paper-run-v1.schema.json"
        ).read_bytes()
        self.assertEqual(governance, packaged)
        schema = json.loads(governance)
        Draft202012Validator.check_schema(schema)
        capture, _ = valid_capture()
        run = build_offline_paper_run(
            capture,
            run_id="offline-paper-test-schema",
            recorded_at="2026-07-27T12:00:02.000Z",
        )
        broken = deepcopy(run)
        broken["unreviewed_claim"] = "profitable"
        self.assertTrue(
            tuple(Draft202012Validator(schema).iter_errors(broken))
        )

    def test_invalid_symbol_and_floats_fail_closed(self):
        with self.assertRaises(OfflinePaperError):
            OfflinePaperPlan.create("DOGEUSDT")
        capture, _ = valid_capture()
        broken = deepcopy(capture.receipts)
        body = json.loads(broken[0]["response_body_utf8"])
        body[0][1] = 2000.0
        broken[0]["response_body_utf8"] = json.dumps(body)
        with self.assertRaises(OfflinePaperError):
            capture.replay_with_receipts(broken)


if __name__ == "__main__":
    unittest.main()
