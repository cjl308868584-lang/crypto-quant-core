import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from jsonschema import Draft202012Validator

from crypto_quant.perpetual_context import (
    BinancePerpetualContextTransport,
    PerpetualContextError,
    PerpetualContextPlan,
    PublicPerpetualHttpResponse,
    build_perpetual_context_snapshot,
    capture_perpetual_context,
    perpetual_context_reasons,
    perpetual_context_trust_hash,
)
from crypto_quant.perpetual_context_cli import main
from tests.test_runtime_health import FakeTimeTransport, fake_time_responses


UTC = timezone.utc


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def epoch_ms(value):
    return int(value.timestamp() * 1000)


def fixture_bodies(*, irregular_funding=False):
    base = datetime(2026, 7, 27, 12, 5, 13, tzinfo=UTC)
    funding_times = [
        datetime(2026, 7, 26, 8, tzinfo=UTC),
        datetime(2026, 7, 26, 16, tzinfo=UTC),
        datetime(2026, 7, 27, 0, tzinfo=UTC),
        datetime(2026, 7, 27, 8, tzinfo=UTC),
    ]
    if irregular_funding:
        funding_times[-1] += timedelta(hours=1)
    return [
        {
            "symbol": "ETHUSDT",
            "markPrice": "1928.25",
            "indexPrice": "1929.15302326",
            "estimatedSettlePrice": "1931.08087403",
            "lastFundingRate": "0.0001",
            "interestRate": "0.0001",
            "nextFundingTime": epoch_ms(
                datetime(2026, 7, 27, 16, tzinfo=UTC)
            ),
            "time": epoch_ms(base),
        },
        [
            [
                epoch_ms(base.replace(second=0) - timedelta(minutes=1)),
                "-0.00040",
                "-0.00020",
                "-0.00050",
                "-0.00030",
                "0",
                epoch_ms(base.replace(second=0)) - 1,
                "0",
                0,
                "0",
                "0",
                "0",
            ],
            [
                epoch_ms(base.replace(second=0)),
                "-0.00030",
                "-0.00010",
                "-0.00040",
                "-0.00020",
                "0",
                epoch_ms(base.replace(second=0) + timedelta(minutes=1))
                - 1,
                "0",
                0,
                "0",
                "0",
                "0",
            ],
        ],
        {
            "symbol": "ETHUSDT",
            "openInterest": "812345.678",
            "time": epoch_ms(base + timedelta(milliseconds=200)),
        },
        [
            {
                "symbol": "ETHUSDT",
                "sumOpenInterest": "800000",
                "sumOpenInterestValue": "1540000000",
                "timestamp": epoch_ms(
                    datetime(2026, 7, 27, 4, tzinfo=UTC)
                ),
            },
            {
                "symbol": "ETHUSDT",
                "sumOpenInterest": "810000",
                "sumOpenInterestValue": "1560000000",
                "timestamp": epoch_ms(
                    datetime(2026, 7, 27, 8, tzinfo=UTC)
                ),
            },
            {
                "symbol": "ETHUSDT",
                "sumOpenInterest": "812000",
                "sumOpenInterestValue": "1567000000",
                "timestamp": epoch_ms(
                    datetime(2026, 7, 27, 12, tzinfo=UTC)
                ),
            },
        ],
        [
            {
                "symbol": "ETHUSDT",
                "fundingTime": epoch_ms(moment),
                "fundingRate": rate,
                "markPrice": "1920",
            }
            for moment, rate in zip(
                funding_times,
                ("-0.0002", "0.0001", "0.0002", "0.0003"),
            )
        ],
    ]


def fixture_responses(*, irregular_funding=False):
    base = datetime(2026, 7, 27, 12, 5, 13, 300000, tzinfo=UTC)
    requests = PerpetualContextPlan.create().requests
    responses = []
    for index, (request, body) in enumerate(
        zip(requests, fixture_bodies(irregular_funding=irregular_funding))
    ):
        started = base + timedelta(milliseconds=index * 100)
        responses.append(
            PublicPerpetualHttpResponse(
                status=200,
                final_url=request.url,
                headers={"Date": "Mon, 27 Jul 2026 12:05:13 GMT"},
                body=json.dumps(body, separators=(",", ":")).encode(),
                request_started_at=iso(started),
                response_received_at=iso(
                    started + timedelta(milliseconds=50)
                ),
            )
        )
    return responses


class FakeFuturesTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, _request):
        self.calls += 1
        if not self.responses:
            raise AssertionError("unexpected Futures request")
        return self.responses.pop(0)


class BombFuturesTransport:
    def __init__(self):
        self.calls = 0

    def get(self, _request):
        self.calls += 1
        raise AssertionError("Futures transport must not be called")


class PerpetualPlanTests(unittest.TestCase):
    def test_plan_has_five_exact_public_futures_requests(self):
        plan = PerpetualContextPlan.create()
        self.assertEqual(len(plan.requests), 5)
        self.assertEqual(
            [item.url for item in plan.requests],
            [
                "https://fapi.binance.com/fapi/v1/premiumIndex"
                "?symbol=ETHUSDT",
                "https://fapi.binance.com/fapi/v1/premiumIndexKlines"
                "?symbol=ETHUSDT&interval=1m&limit=2",
                "https://fapi.binance.com/fapi/v1/openInterest"
                "?symbol=ETHUSDT",
                "https://fapi.binance.com/futures/data/openInterestHist"
                "?symbol=ETHUSDT&period=4h&limit=30",
                "https://fapi.binance.com/fapi/v1/fundingRate"
                "?symbol=ETHUSDT&limit=30",
            ],
        )

    def test_plan_and_request_cannot_be_constructed_or_changed(self):
        with self.assertRaises(TypeError):
            PerpetualContextPlan()
        with self.assertRaises(PerpetualContextError):
            PerpetualContextPlan.create(symbol="BTCUSDT")
        self.assertFalse(hasattr(BinancePerpetualContextTransport, "post"))

    def test_production_transport_disables_proxy_and_never_retries(self):
        class FailingOpener:
            def __init__(self):
                self.calls = 0

            def open(self, *_args, **_kwargs):
                self.calls += 1
                raise URLError("offline")

        clock = lambda: "2026-07-27T12:05:13.000Z"
        sentinel = object()
        with patch(
            "crypto_quant.perpetual_context.build_opener",
            return_value=sentinel,
        ) as build:
            production = BinancePerpetualContextTransport(clock=clock)
        self.assertIs(production._opener, sentinel)
        self.assertEqual(build.call_args.args[0].proxies, {})

        opener = FailingOpener()
        transport = BinancePerpetualContextTransport(
            clock=clock, opener=opener
        )
        with self.assertRaisesRegex(
            PerpetualContextError, "PERPETUAL_TRANSPORT_FAILURE"
        ):
            transport.get(PerpetualContextPlan.create().requests[0])
        self.assertEqual(opener.calls, 1)
        self.assertEqual(transport.calls, 1)


class PerpetualSnapshotTests(unittest.TestCase):
    def _capture(self, *, irregular_funding=False):
        time_transport = FakeTimeTransport(fake_time_responses())
        futures_transport = FakeFuturesTransport(
            fixture_responses(irregular_funding=irregular_funding)
        )
        capture = capture_perpetual_context(
            server_time_transport=time_transport,
            futures_transport=futures_transport,
        )
        return build_perpetual_context_snapshot(capture), futures_transport

    def test_snapshot_replays_basis_oi_and_short_funding_scenarios(self):
        snapshot, transport = self._capture()
        self.assertEqual(transport.calls, 5)
        self.assertEqual(snapshot["network_request_count"], 8)
        market = snapshot["market_context"]
        self.assertEqual(market["mark_price"], "1928.25")
        self.assertEqual(market["index_price"], "1929.15302326")
        self.assertEqual(market["basis_usdt"], "-0.90302326")
        self.assertEqual(market["premium_index_1m_close"], "-0.0002")
        self.assertEqual(market["current_open_interest"], "812345.678")
        self.assertEqual(market["funding_observed_interval_hours"], 8)

        scenarios = snapshot["short_funding_scenarios"]
        self.assertEqual(
            scenarios["next_funding_short_cashflow_per_1000_usdt"],
            "0.1",
        )
        self.assertEqual(scenarios["settlement_count_next_24h"], 3)
        self.assertEqual(
            scenarios[
                "repeated_current_rate_24h_short_cashflow_per_1000_usdt"
            ],
            "0.3",
        )
        self.assertEqual(
            scenarios[
                "two_x_recent_absolute_adverse_24h_short_cashflow_per_1000_usdt"
            ],
            "-1.8",
        )
        trust = perpetual_context_trust_hash(snapshot)
        self.assertEqual(perpetual_context_reasons(snapshot, trust), ())

    def test_irregular_funding_interval_keeps_24h_scenarios_null(self):
        snapshot, _ = self._capture(irregular_funding=True)
        self.assertIsNone(
            snapshot["market_context"]["funding_observed_interval_hours"]
        )
        scenarios = snapshot["short_funding_scenarios"]
        self.assertIsNone(scenarios["settlement_count_next_24h"])
        self.assertIsNone(
            scenarios[
                "repeated_current_rate_24h_short_cashflow_per_1000_usdt"
            ]
        )
        self.assertIn(
            "FUNDING_INTERVAL_NOT_PROVEN", snapshot["quality_report"][
                "reason_codes"
            ]
        )

    def test_optional_cmc_supply_is_validated_and_preserved(self):
        responses = fixture_responses()
        body = json.loads(responses[3].body)
        body[-1]["CMCCirculatingSupply"] = "120500000"
        responses[3] = PublicPerpetualHttpResponse(
            **{
                **responses[3].__dict__,
                "body": json.dumps(body, separators=(",", ":")).encode(),
            }
        )
        capture = capture_perpetual_context(
            server_time_transport=FakeTimeTransport(fake_time_responses()),
            futures_transport=FakeFuturesTransport(responses),
        )
        snapshot = build_perpetual_context_snapshot(capture)
        self.assertEqual(
            snapshot["market_context"]["open_interest_history"][-1][
                "cmc_circulating_supply_or_null"
            ],
            "120500000",
        )

    def test_raw_receipt_or_derived_value_tampering_is_detected(self):
        snapshot, _ = self._capture()
        trust = perpetual_context_trust_hash(snapshot)
        for changed in (
            ("receipt",),
            ("derived",),
            ("claim",),
        ):
            candidate = deepcopy(snapshot)
            if changed[0] == "receipt":
                candidate["receipts"][0]["response_body_utf8"] += " "
            elif changed[0] == "derived":
                candidate["market_context"]["basis_usdt"] = "99"
            else:
                candidate["profitability_eligibility"] = "PROVEN"
            self.assertTrue(perpetual_context_reasons(candidate, trust))

    def test_bad_symbol_order_time_float_and_status_fail_closed(self):
        cases = fixture_responses()
        bad_symbol = deepcopy(cases)
        body = json.loads(bad_symbol[0].body)
        body["symbol"] = "BTCUSDT"
        bad_symbol[0] = PublicPerpetualHttpResponse(
            **{**bad_symbol[0].__dict__, "body": json.dumps(body).encode()}
        )
        bad_status = deepcopy(cases)
        bad_status[0] = PublicPerpetualHttpResponse(
            **{**bad_status[0].__dict__, "status": 429}
        )
        bad_float = deepcopy(cases)
        bad_float[0] = PublicPerpetualHttpResponse(
            **{
                **bad_float[0].__dict__,
                "body": b'{"symbol":"ETHUSDT","markPrice":1.2}',
            }
        )
        for responses in (bad_symbol, bad_status, bad_float):
            with self.subTest():
                with self.assertRaises(PerpetualContextError):
                    capture_perpetual_context(
                        server_time_transport=FakeTimeTransport(
                            fake_time_responses()
                        ),
                        futures_transport=FakeFuturesTransport(responses),
                    )

    def test_fixed_interval_series_and_current_window_fail_closed(self):
        base_cases = fixture_responses()
        mutations = []

        broken_kline_spacing = deepcopy(base_cases)
        body = json.loads(broken_kline_spacing[1].body)
        body[1][0] += 1
        broken_kline_spacing[1] = PublicPerpetualHttpResponse(
            **{
                **broken_kline_spacing[1].__dict__,
                "body": json.dumps(body, separators=(",", ":")).encode(),
            }
        )
        mutations.append(broken_kline_spacing)

        stale_kline = deepcopy(base_cases)
        body = json.loads(stale_kline[1].body)
        for row in body:
            row[0] -= 2 * 60_000
            row[6] -= 2 * 60_000
        stale_kline[1] = PublicPerpetualHttpResponse(
            **{
                **stale_kline[1].__dict__,
                "body": json.dumps(body, separators=(",", ":")).encode(),
            }
        )
        mutations.append(stale_kline)

        broken_oi_spacing = deepcopy(base_cases)
        body = json.loads(broken_oi_spacing[3].body)
        body[1]["timestamp"] += 1
        broken_oi_spacing[3] = PublicPerpetualHttpResponse(
            **{
                **broken_oi_spacing[3].__dict__,
                "body": json.dumps(body, separators=(",", ":")).encode(),
            }
        )
        mutations.append(broken_oi_spacing)

        stale_oi = deepcopy(base_cases)
        body = json.loads(stale_oi[3].body)
        for item in body:
            item["timestamp"] -= 8 * 3_600_000
        stale_oi[3] = PublicPerpetualHttpResponse(
            **{
                **stale_oi[3].__dict__,
                "body": json.dumps(body, separators=(",", ":")).encode(),
            }
        )
        mutations.append(stale_oi)

        stale_funding = deepcopy(base_cases)
        body = json.loads(stale_funding[4].body)
        for item in body:
            item["fundingTime"] -= 48 * 3_600_000
        stale_funding[4] = PublicPerpetualHttpResponse(
            **{
                **stale_funding[4].__dict__,
                "body": json.dumps(body, separators=(",", ":")).encode(),
            }
        )
        mutations.append(stale_funding)

        for responses in mutations:
            with self.subTest():
                with self.assertRaises(PerpetualContextError):
                    capture_perpetual_context(
                        server_time_transport=FakeTimeTransport(
                            fake_time_responses()
                        ),
                        futures_transport=FakeFuturesTransport(responses),
                    )

    def test_next_funding_time_must_be_current_and_bounded(self):
        base_cases = fixture_responses()
        for next_time in (
            datetime(2026, 7, 27, 12, 5, 12, tzinfo=UTC),
            datetime(2026, 7, 28, 12, 5, 14, tzinfo=UTC),
        ):
            responses = deepcopy(base_cases)
            body = json.loads(responses[0].body)
            body["nextFundingTime"] = epoch_ms(next_time)
            responses[0] = PublicPerpetualHttpResponse(
                **{
                    **responses[0].__dict__,
                    "body": json.dumps(
                        body, separators=(",", ":")
                    ).encode(),
                }
            )
            with self.subTest(next_time=next_time):
                with self.assertRaisesRegex(
                    PerpetualContextError,
                    "PERPETUAL_NEXT_FUNDING_TIME_INVALID",
                ):
                    capture_perpetual_context(
                        server_time_transport=FakeTimeTransport(
                            fake_time_responses()
                        ),
                        futures_transport=FakeFuturesTransport(responses),
                    )

    def test_futures_capture_must_start_after_health_gate(self):
        responses = fixture_responses()
        shifted = []
        for response in responses:
            started = datetime.fromisoformat(
                response.request_started_at.replace("Z", "+00:00")
            ) - timedelta(seconds=1)
            received = datetime.fromisoformat(
                response.response_received_at.replace("Z", "+00:00")
            ) - timedelta(seconds=1)
            shifted.append(
                PublicPerpetualHttpResponse(
                    **{
                        **response.__dict__,
                        "request_started_at": iso(started),
                        "response_received_at": iso(received),
                    }
                )
            )
        with self.assertRaisesRegex(
            PerpetualContextError,
            "PERPETUAL_CAPTURE_PRECEDES_HEALTH_GATE",
        ):
            capture_perpetual_context(
                server_time_transport=FakeTimeTransport(
                    fake_time_responses()
                ),
                futures_transport=FakeFuturesTransport(shifted),
            )

    def test_blocked_clock_makes_zero_futures_requests(self):
        bomb = BombFuturesTransport()
        with self.assertRaisesRegex(
            PerpetualContextError, "PERPETUAL_CLOCK_BLOCKED"
        ):
            capture_perpetual_context(
                server_time_transport=FakeTimeTransport(
                    fake_time_responses(
                        offset_ms=8000, rtts=(50, 60, 55)
                    )
                ),
                futures_transport=bomb,
            )
        self.assertEqual(bomb.calls, 0)

    def test_schema_is_packaged_mirrored_and_rejects_extra_claims(self):
        root = Path(__file__).resolve().parents[1]
        governance = (
            root / "config" / "perpetual-context-snapshot-v1.schema.json"
        )
        packaged = resources.files("crypto_quant").joinpath(
            "schemas", "perpetual-context-snapshot-v1.schema.json"
        )
        self.assertEqual(governance.read_bytes(), packaged.read_bytes())
        schema = json.loads(governance.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        snapshot, _ = self._capture()
        snapshot["short_ready"] = True
        self.assertTrue(
            tuple(Draft202012Validator(schema).iter_errors(snapshot))
        )

    def test_frozen_real_smoke_failure_evidence_is_explicit(self):
        root = Path(__file__).resolve().parents[1]
        evidence = json.loads(
            (
                root
                / "artifacts"
                / "market-data"
                / "binance-perpetual-context-smoke-failure-v0.21.0.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["outcome"], "FAILED_CLOSED")
        self.assertEqual(
            evidence["eligibility"],
            "REAL_FUTURES_SMOKE_NOT_CAPTURED_NETWORK_UNREACHABLE",
        )
        self.assertEqual(evidence["network"]["futures_receipt_count"], 0)
        self.assertFalse(evidence["security_boundary"]["proxy_used"])
        self.assertFalse(
            evidence["security_boundary"]["substitute_source_used"]
        )


class PerpetualCliTests(unittest.TestCase):
    def test_cli_publishes_immutable_context_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    ["--output-root", directory],
                    server_time_transport=FakeTimeTransport(
                        fake_time_responses()
                    ),
                    futures_transport=FakeFuturesTransport(
                        fixture_responses()
                    ),
                )
            self.assertEqual(result, 0)
            summary = json.loads(stdout.getvalue())
            self.assertTrue(Path(summary["artifact_path"]).is_file())
            self.assertEqual(summary["network_request_count"], 8)

    def test_cli_exposes_no_source_credential_order_or_time_overrides(self):
        for forbidden in (
            "--url",
            "--host",
            "--proxy",
            "--header",
            "--api-key",
            "--secret",
            "--account",
            "--order",
            "--now",
        ):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([forbidden, "x"]), 2)


if __name__ == "__main__":
    unittest.main()
