import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_quant.canonical import utc_datetime
from crypto_quant.challenger_forward import (
    ChallengerForwardState,
    challenger_decision_hash,
)
from crypto_quant.challenger_forward_runner import (
    ChallengerForwardRunnerError,
    ChallengerKlineHttpResponse,
    BinanceChallengerKlineTransport,
    challenger_kline_request,
    challenger_source_bundle_hash,
    challenger_source_bundle_reasons,
    load_challenger_source_bundle,
    run_challenger_forward_cycle,
)
from crypto_quant.challenger_forward_runner_cli import main as runner_main
from crypto_quant.runtime_health import (
    PublicServerTimeHttpResponse,
    open_verified_runtime_gate,
)


START = datetime(2026, 7, 29, tzinfo=timezone.utc)
TIME_URL = "https://data-api.binance.vision/api/v3/time"


def epoch_ms(value):
    return int(value.timestamp() * 1000)


class ServerTimeTransport:
    def __init__(self, now):
        self.now = now
        self.calls = 0

    def get(self):
        self.calls += 1
        text = utc_datetime(self.now)
        body = json.dumps(
            {"serverTime": epoch_ms(self.now)},
            separators=(",", ":"),
        ).encode("utf-8")
        return PublicServerTimeHttpResponse(
            status=200,
            final_url=TIME_URL,
            headers={"Date": "Wed, 29 Jul 2026 00:01:00 GMT"},
            body=body,
            request_started_at=text,
            response_received_at=text,
            monotonic_rtt_ms=0,
        )


def gate_at(value):
    source = ServerTimeTransport(value)
    gate = open_verified_runtime_gate(
        server_time_transport=source,
        monotonic_ns=lambda: 1_000_000_000,
    )
    return gate, source


def raw_window(slot, closes):
    if len(closes) != 21:
        raise ValueError("fixture requires 21 closes")
    first_open = slot - timedelta(hours=84)
    rows = []
    for index, price in enumerate(closes):
        opened = first_open + timedelta(hours=4 * index)
        closed = opened + timedelta(hours=4) - timedelta(milliseconds=1)
        rows.append(
            [
                epoch_ms(opened),
                str(price),
                str(price + 1),
                str(price - 1),
                str(price),
                "1",
                epoch_ms(closed),
                "100",
                10,
                "0.5",
                "50",
                "0",
            ]
        )
    return rows


class KlineTransport:
    def __init__(
        self,
        rows,
        now,
        *,
        status=200,
        final_url=None,
        started_at=None,
    ):
        self.rows = rows
        self.now = now
        self.status = status
        self.final_url = final_url
        self.started_at = started_at or now
        self.calls = 0

    def get(self, request):
        self.calls += 1
        return ChallengerKlineHttpResponse(
            status=self.status,
            final_url=self.final_url or request.url,
            headers={"Date": "Wed, 29 Jul 2026 00:01:00 GMT"},
            body=json.dumps(
                self.rows,
                separators=(",", ":"),
            ).encode("utf-8"),
            request_started_at=utc_datetime(self.started_at),
            response_received_at=utc_datetime(self.now),
        )


class BombKlineTransport:
    def __init__(self):
        self.calls = 0

    def get(self, request):
        self.calls += 1
        raise AssertionError("Kline request must not occur")


class ChallengerForwardRunnerTests(unittest.TestCase):
    def test_request_is_exact_and_cannot_be_directly_constructed(self):
        request = challenger_kline_request("2026-07-29T00:00:00.000Z")
        self.assertEqual(request.method, "GET")
        self.assertEqual(
            request.url,
            "https://data-api.binance.vision/api/v3/klines"
            "?endTime=1785283199999&interval=4h&limit=21&symbol=ETHUSDT",
        )
        with self.assertRaises(TypeError):
            type(request)(
                scheduled_for=request.scheduled_for,
                request_id=request.request_id,
                method="GET",
                url="https://evil.example",
            )

    def test_not_due_and_missed_slot_make_zero_kline_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gate, server = gate_at(START - timedelta(hours=1))
            bomb = BombKlineTransport()
            result = run_challenger_forward_cycle(
                state_path=root / "state.sqlite",
                output_root=root / "out",
                runtime_gate=gate,
                kline_transport=bomb,
            )
            self.assertEqual(result["status"], "NOT_DUE")
            self.assertEqual(result["server_time_request_count"], 3)
            self.assertEqual(result["kline_request_count"], 0)
            self.assertEqual(server.calls, 3)
            self.assertEqual(bomb.calls, 0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gate, _ = gate_at(START + timedelta(hours=4, minutes=1))
            bomb = BombKlineTransport()
            with self.assertRaisesRegex(
                ChallengerForwardRunnerError,
                "CHALLENGER_RUNNER_MISSED_SLOT",
            ):
                run_challenger_forward_cycle(
                    state_path=root / "state.sqlite",
                    output_root=root / "out",
                    runtime_gate=gate,
                    kline_transport=bomb,
                )
            self.assertEqual(bomb.calls, 0)

    def test_due_cycle_records_one_decision_and_replayable_source(self):
        now = START + timedelta(minutes=1)
        gate, server = gate_at(now)
        transport = KlineTransport(raw_window(START, [100] * 21), now)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state" / "forward.sqlite"
            result = run_challenger_forward_cycle(
                state_path=state_path,
                output_root=root / "artifacts",
                runtime_gate=gate,
                kline_transport=transport,
            )
            self.assertEqual(result["status"], "RECORDED")
            self.assertEqual(result["server_time_request_count"], 3)
            self.assertEqual(result["kline_request_count"], 1)
            self.assertEqual(result["broker_request_count"], 0)
            self.assertEqual(result["order_submission_count"], 0)
            self.assertEqual(server.calls, 3)
            self.assertEqual(transport.calls, 1)
            bundle_path = Path(result["source_bundle_path"])
            bundle = load_challenger_source_bundle(bundle_path)
            self.assertEqual(challenger_source_bundle_reasons(bundle), ())
            self.assertEqual(bundle["candidate_decision"]["action"], "REJECT_ENTRY")
            self.assertEqual(os.stat(bundle_path).st_mode & 0o777, 0o600)
            with ChallengerForwardState(state_path) as state:
                self.assertEqual(len(state.replay()), 1)

    def test_same_slot_retry_is_not_due_and_uses_zero_market_requests(self):
        now = START + timedelta(minutes=1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gate, _ = gate_at(now)
            first_transport = KlineTransport(
                raw_window(START, [100] * 21), now
            )
            run_challenger_forward_cycle(
                state_path=root / "state.sqlite",
                output_root=root / "out",
                runtime_gate=gate,
                kline_transport=first_transport,
            )
            retry_gate, _ = gate_at(now)
            bomb = BombKlineTransport()
            retry = run_challenger_forward_cycle(
                state_path=root / "state.sqlite",
                output_root=root / "out",
                runtime_gate=retry_gate,
                kline_transport=bomb,
            )
            self.assertEqual(retry["status"], "NOT_DUE")
            self.assertEqual(retry["decision_count"], 1)
            self.assertEqual(bomb.calls, 0)

    def test_next_slot_reuses_twenty_original_availability_values(self):
        first_now = START + timedelta(minutes=1)
        second_slot = START + timedelta(hours=4)
        second_now = second_slot + timedelta(minutes=2)
        stream = [100] * 21 + [102]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_gate, _ = gate_at(first_now)
            run_challenger_forward_cycle(
                state_path=root / "state.sqlite",
                output_root=root / "out",
                runtime_gate=first_gate,
                kline_transport=KlineTransport(
                    raw_window(START, stream[:21]),
                    first_now,
                ),
            )
            second_gate, _ = gate_at(second_now)
            run_challenger_forward_cycle(
                state_path=root / "state.sqlite",
                output_root=root / "out",
                runtime_gate=second_gate,
                kline_transport=KlineTransport(
                    raw_window(second_slot, stream[1:]),
                    second_now,
                ),
            )
            with ChallengerForwardState(root / "state.sqlite") as state:
                first, second = state.replay()
            self.assertEqual(
                first["input_klines"][1:],
                second["input_klines"][:-1],
            )
            self.assertEqual(
                second["input_klines"][-1]["available_at"],
                utc_datetime(second_now),
            )
            self.assertEqual(second["action"], "ENTER_LONG")

    def test_closed_kline_revision_fails_without_appending(self):
        first_now = START + timedelta(minutes=1)
        second_slot = START + timedelta(hours=4)
        second_now = second_slot + timedelta(minutes=1)
        stream = [100] * 21 + [102]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gate, _ = gate_at(first_now)
            run_challenger_forward_cycle(
                state_path=root / "state.sqlite",
                output_root=root / "out",
                runtime_gate=gate,
                kline_transport=KlineTransport(
                    raw_window(START, stream[:21]), first_now
                ),
            )
            revised = raw_window(second_slot, stream[1:])
            revised[0][4] = "101"
            second_gate, _ = gate_at(second_now)
            with self.assertRaisesRegex(
                ChallengerForwardRunnerError,
                "CHALLENGER_RUNNER_KLINE_REVISION",
            ):
                run_challenger_forward_cycle(
                    state_path=root / "state.sqlite",
                    output_root=root / "out",
                    runtime_gate=second_gate,
                    kline_transport=KlineTransport(revised, second_now),
                )
            with ChallengerForwardState(root / "state.sqlite") as state:
                self.assertEqual(len(state.replay()), 1)

    def test_bad_status_gap_unclosed_and_pre_slot_request_fail_closed(self):
        now = START + timedelta(minutes=1)
        good = raw_window(START, [100] * 21)
        variants = []
        gap = copy.deepcopy(good)
        gap[5][0] += 1
        variants.append(("KLINE_INVALID", KlineTransport(gap, now)))
        unclosed = copy.deepcopy(good)
        unclosed[-1][6] += 1
        variants.append(("KLINE_INVALID", KlineTransport(unclosed, now)))
        variants.append(
            ("RESPONSE_INVALID", KlineTransport(good, now, status=500))
        )
        variants.append(
            (
                "CLOCK_INVALID",
                KlineTransport(
                    good,
                    now,
                    started_at=START - timedelta(milliseconds=1),
                ),
            )
        )
        for expected, transport in variants:
            with self.subTest(expected=expected):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    gate, _ = gate_at(now)
                    with self.assertRaisesRegex(
                        ChallengerForwardRunnerError,
                        expected,
                    ):
                        run_challenger_forward_cycle(
                            state_path=root / "state.sqlite",
                            output_root=root / "out",
                            runtime_gate=gate,
                            kline_transport=transport,
                        )

    def test_bundle_semantic_tamper_and_schema_mirror_are_detected(self):
        now = START + timedelta(minutes=1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gate, _ = gate_at(now)
            result = run_challenger_forward_cycle(
                state_path=root / "state.sqlite",
                output_root=root / "out",
                runtime_gate=gate,
                kline_transport=KlineTransport(
                    raw_window(START, [100] * 21), now
                ),
            )
            bundle = copy.deepcopy(
                load_challenger_source_bundle(
                    Path(result["source_bundle_path"])
                )
            )
            bundle["candidate_decision"]["action"] = "ENTER_LONG"
            bundle["candidate_decision"]["decision_hash"] = (
                challenger_decision_hash(bundle["candidate_decision"])
            )
            bundle["bundle_hash"] = challenger_source_bundle_hash(bundle)
            self.assertIn(
                "CHALLENGER_RUNNER_DECISION_REPLAY_MISMATCH",
                challenger_source_bundle_reasons(bundle),
            )
        repository = Path(__file__).resolve().parents[1]
        self.assertEqual(
            (
                repository
                / "config"
                / "challenger-forward-source-bundle-v1.schema.json"
            ).read_bytes(),
            (
                repository
                / "src"
                / "crypto_quant"
                / "schemas"
                / "challenger-forward-source-bundle-v1.schema.json"
            ).read_bytes(),
        )

    def test_cli_exposes_only_state_and_output_and_runs_fixture(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "crypto_quant"
            / "challenger_forward_runner_cli.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "--url",
            "--host",
            "--symbol",
            "--scheduled-for",
            "--recorded-at",
            "--api-key",
            "--credential",
            "--order",
        ):
            self.assertNotIn(forbidden, source)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(runner_main(["--url", "x"]), 2)
        now = START + timedelta(minutes=1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gate, _ = gate_at(now)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = runner_main(
                    [
                        "--state-path",
                        str(root / "state.sqlite"),
                        "--output-root",
                        str(root / "out"),
                    ],
                    runtime_gate=gate,
                    kline_transport=KlineTransport(
                        raw_window(START, [100] * 21), now
                    ),
                )
            self.assertEqual(status, 0)
            self.assertEqual(
                json.loads(stdout.getvalue())["status"],
                "RECORDED",
            )

    def test_fixed_fixture_is_deterministic_one_hundred_times(self):
        now = START + timedelta(minutes=1)
        expected = None
        for _ in range(100):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                gate, _ = gate_at(now)
                result = run_challenger_forward_cycle(
                    state_path=root / "state.sqlite",
                    output_root=root / "out",
                    runtime_gate=gate,
                    kline_transport=KlineTransport(
                        raw_window(START, [100] * 21), now
                    ),
                )
                identity = (
                    result["decision_id"],
                    result["decision_hash"],
                    result["source_bundle_hash"],
                )
                if expected is None:
                    expected = identity
                self.assertEqual(identity, expected)

    def test_transport_rejects_non_request_and_module_has_no_broker_import(self):
        transport = BinanceChallengerKlineTransport()
        with self.assertRaisesRegex(
            ChallengerForwardRunnerError,
            "CHALLENGER_RUNNER_REQUEST_INVALID",
        ):
            transport.get(object())
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "crypto_quant"
            / "challenger_forward_runner.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("from .orders", source)
        self.assertNotIn("from .execution", source)
        self.assertNotIn("Broker(", source)


if __name__ == "__main__":
    unittest.main()
