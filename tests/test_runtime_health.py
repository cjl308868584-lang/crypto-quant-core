import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from importlib import resources

from jsonschema import Draft202012Validator

from crypto_quant.runtime_health import (
    BinanceServerTimeTransport,
    PublicServerTimeHttpResponse,
    RuntimeHealthError,
    RuntimeHealthPolicy,
    RuntimeHealthState,
    TrustedRuntimeClock,
    build_server_time_probe,
    build_runtime_snapshot,
    run_healthy_paper_cycle,
    runtime_snapshot_reasons,
    runtime_snapshot_trust_hash,
    server_time_probe_reasons,
    server_time_probe_trust_hash,
)
from crypto_quant.runtime_health_cli import main
from tests.test_paper_scheduler import BombTransport, paper_transport


UTC = timezone.utc


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def epoch_ms(value):
    return int(value.timestamp() * 1000)


def fake_time_responses(
    *,
    base=datetime(2026, 7, 27, 12, 5, 8, tzinfo=UTC),
    offset_ms=2500,
    rtts=(700, 760, 720),
):
    responses = []
    for index, rtt in enumerate(rtts):
        start = base + timedelta(seconds=index)
        receive = start + timedelta(milliseconds=rtt)
        midpoint_ms = (epoch_ms(start) + epoch_ms(receive)) // 2
        server_ms = midpoint_ms + offset_ms
        responses.append(
            PublicServerTimeHttpResponse(
                status=200,
                final_url="https://data-api.binance.vision/api/v3/time",
                headers={"Date": "Mon, 27 Jul 2026 12:05:10 GMT"},
                body=json.dumps(
                    {"serverTime": server_ms}, separators=(",", ":")
                ).encode(),
                request_started_at=iso(start),
                response_received_at=iso(receive),
                monotonic_rtt_ms=rtt,
            )
        )
    return responses


class FakeTimeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self):
        self.calls += 1
        if not self.responses:
            raise AssertionError("unexpected server-time request")
        return self.responses.pop(0)


class ServerTimeProbeTests(unittest.TestCase):
    def test_three_samples_produce_conservative_corrected_health(self):
        transport = FakeTimeTransport(fake_time_responses())
        probe = build_server_time_probe(transport=transport)

        self.assertEqual(transport.calls, 3)
        self.assertEqual(probe["health_status"], "HEALTHY_CORRECTED")
        self.assertEqual(probe["sample_count"], 3)
        self.assertEqual(probe["valid_sample_count"], 3)
        self.assertLessEqual(
            probe["offset_intersection"]["width_ms"], 1000
        )
        self.assertGreater(
            probe["offset_intersection"]["lower_ms"], 1000
        )
        self.assertEqual(probe["reason_codes"], [])
        trust = server_time_probe_trust_hash(probe)
        self.assertEqual(server_time_probe_reasons(probe, trust), ())

    def test_small_offset_is_aligned(self):
        probe = build_server_time_probe(
            transport=FakeTimeTransport(
                fake_time_responses(offset_ms=100, rtts=(50, 60, 55))
            )
        )
        self.assertEqual(probe["health_status"], "HEALTHY_ALIGNED")
        self.assertEqual(probe["correction_ms"], 100)

    def test_unstable_or_excessive_clock_is_blocked(self):
        excessive = build_server_time_probe(
            transport=FakeTimeTransport(
                fake_time_responses(offset_ms=8000, rtts=(50, 60, 55))
            )
        )
        self.assertEqual(excessive["health_status"], "BLOCKED")
        self.assertIn(
            "PAPER_CLOCK_OFFSET_EXCEEDS_LIMIT", excessive["reason_codes"]
        )

        unstable_responses = fake_time_responses(
            offset_ms=100, rtts=(50, 60, 55)
        )
        body = json.loads(unstable_responses[-1].body)
        body["serverTime"] += 3000
        unstable_responses[-1] = PublicServerTimeHttpResponse(
            **{
                **unstable_responses[-1].__dict__,
                "body": json.dumps(body, separators=(",", ":")).encode(),
            }
        )
        unstable = build_server_time_probe(
            transport=FakeTimeTransport(unstable_responses)
        )
        self.assertEqual(unstable["health_status"], "BLOCKED")
        self.assertIn(
            "PAPER_CLOCK_INTERVALS_DO_NOT_INTERSECT",
            unstable["reason_codes"],
        )

    def test_probe_rejects_bad_endpoint_status_json_rtt_and_tampering(self):
        cases = []
        response = fake_time_responses()[0]
        cases.append(
            PublicServerTimeHttpResponse(
                **{**response.__dict__, "status": 429}
            )
        )
        cases.append(
            PublicServerTimeHttpResponse(
                **{
                    **response.__dict__,
                    "final_url": "https://example.com/api/v3/time",
                }
            )
        )
        cases.append(
            PublicServerTimeHttpResponse(
                **{**response.__dict__, "body": b'{"serverTime":true}'}
            )
        )
        for bad in cases:
            with self.subTest(bad=bad):
                with self.assertRaises(RuntimeHealthError):
                    build_server_time_probe(
                        transport=FakeTimeTransport([bad] * 3)
                    )

        slow = build_server_time_probe(
            transport=FakeTimeTransport(
                [
                    PublicServerTimeHttpResponse(
                        **{
                            **item.__dict__,
                            "monotonic_rtt_ms": 3001,
                        }
                    )
                    for item in fake_time_responses()
                ]
            )
        )
        self.assertEqual(slow["health_status"], "BLOCKED")
        self.assertIn(
            "PAPER_CLOCK_RTT_EXCEEDS_LIMIT", slow["reason_codes"]
        )

        probe = build_server_time_probe(
            transport=FakeTimeTransport(fake_time_responses())
        )
        changed = deepcopy(probe)
        changed["samples"][0]["server_time_ms"] += 1
        self.assertIn(
            "PAPER_CLOCK_PROBE_SELF_HASH_MISMATCH",
            server_time_probe_reasons(
                changed, server_time_probe_trust_hash(probe)
            ),
        )

    def test_probe_failure_is_recorded_as_blocked_runtime_evidence(self):
        class FailingTransport:
            def __init__(self):
                self.calls = 0

            def get(self):
                self.calls += 1
                raise RuntimeHealthError("PAPER_CLOCK_TRANSPORT_FAILURE")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transport = FailingTransport()
            result = run_healthy_paper_cycle(
                runtime_state_path=root / "runtime.sqlite",
                scheduler_state_path=root / "schedule.sqlite",
                output_root=root / "artifacts",
                worker_id="worker-a",
                server_time_transport=transport,
                paper_transport=BombTransport(),
            )
            self.assertEqual(result["outcome"], "CLOCK_BLOCKED")
            self.assertEqual(result["server_time_request_count"], 1)
            probe = result["runtime_snapshot"]["events"][0]["payload"][
                "probe"
            ]
            self.assertEqual(probe["sample_count"], 0)
            self.assertEqual(
                probe["reason_codes"], ["PAPER_CLOCK_TRANSPORT_FAILURE"]
            )
            self.assertEqual(
                server_time_probe_reasons(
                    probe, server_time_probe_trust_hash(probe)
                ),
                (),
            )

    def test_production_transport_has_one_fixed_public_url(self):
        policy = RuntimeHealthPolicy.create()
        self.assertEqual(
            policy.server_time_url,
            "https://data-api.binance.vision/api/v3/time",
        )
        self.assertFalse(hasattr(BinanceServerTimeTransport, "post"))


class TrustedClockTests(unittest.TestCase):
    def test_monotonic_anchor_ignores_wall_clock_jumps(self):
        ticks = iter((10_000_000_000, 10_250_000_000, 11_000_000_000))
        clock = TrustedRuntimeClock(
            anchor_utc_ms=epoch_ms(
                datetime(2026, 7, 27, 12, 5, 11, tzinfo=UTC)
            ),
            anchor_monotonic_ns=10_000_000_000,
            monotonic_ns=lambda: next(ticks),
        )
        self.assertEqual(clock(), "2026-07-27T12:05:11.000Z")
        self.assertEqual(clock(), "2026-07-27T12:05:11.250Z")
        self.assertEqual(clock(), "2026-07-27T12:05:12.000Z")

    def test_clock_rejects_monotonic_reversal(self):
        ticks = iter((10_000, 9_999))
        clock = TrustedRuntimeClock(
            anchor_utc_ms=epoch_ms(
                datetime(2026, 7, 27, 12, 5, 11, tzinfo=UTC)
            ),
            anchor_monotonic_ns=10_000,
            monotonic_ns=lambda: next(ticks),
        )
        clock()
        with self.assertRaises(RuntimeHealthError):
            clock()


class RuntimeStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "runtime.sqlite"
        self.policy = RuntimeHealthPolicy.create()

    def tearDown(self):
        self.temp.cleanup()

    def _payload(self, base, *, active_alerts=()):
        probe = build_server_time_probe(
            transport=FakeTimeTransport(fake_time_responses(base=base))
        )
        return {
            "time_basis": "BINANCE_SERVER_TIME_CORRECTED",
            "probe": probe,
            "scheduler": {
                "outcome": "ALREADY_SUCCEEDED",
                "reason_code_or_null": None,
                "slot_id_or_null": "ETHUSDT_20260727T120000Z",
                "cycle_run_hash_or_null": "a" * 64,
                "cycle_trust_hash_or_null": "b" * 64,
                "schedule_snapshot_hash_or_null": "c" * 64,
                "schedule_trust_hash_or_null": "d" * 64,
            },
            "network": {
                "server_time_request_count": 3,
                "paper_market_request_count": 0,
                "total_network_request_count": 3,
            },
            "alerts": {
                "active": list(active_alerts),
                "raised": list(active_alerts),
                "cleared": [],
                "delivery": "LOCAL_ARTIFACT_ONLY",
            },
        }

    def test_state_is_append_only_wal_and_replayable(self):
        with RuntimeHealthState(self.path, self.policy) as state:
            payload = self._payload(
                datetime(2026, 7, 27, 12, 5, 8, tzinfo=UTC)
            )
            event = state.append_heartbeat(payload)
            self.assertEqual(event["sequence"], 1)
            self.assertEqual(
                state.connection.execute("PRAGMA journal_mode").fetchone()[0],
                "wal",
            )
            self.assertEqual(
                state.connection.execute("PRAGMA synchronous").fetchone()[0],
                2,
            )
            with self.assertRaises(sqlite3.DatabaseError):
                state.connection.execute(
                    "UPDATE runtime_events SET event_type='x'"
                )
            with self.assertRaises(sqlite3.DatabaseError):
                state.connection.execute("DELETE FROM runtime_events")
            snapshot = build_runtime_snapshot(state)

        trust = runtime_snapshot_trust_hash(snapshot)
        self.assertEqual(runtime_snapshot_reasons(snapshot, trust), ())
        self.assertEqual(snapshot["summary"]["heartbeat_count"], 1)

    def test_database_event_tampering_is_detected_on_reopen(self):
        with RuntimeHealthState(self.path, self.policy) as state:
            state.append_heartbeat(
                self._payload(
                    datetime(2026, 7, 27, 12, 5, 8, tzinfo=UTC)
                )
            )
        connection = sqlite3.connect(self.path)
        connection.execute("DROP TRIGGER runtime_events_no_update")
        connection.execute(
            "UPDATE runtime_events SET payload_hash=?", ("0" * 64,)
        )
        connection.commit()
        connection.close()
        with self.assertRaises(RuntimeHealthError):
            RuntimeHealthState(self.path, self.policy)

    def test_gap_and_unknown_continuity_alerts_are_derived(self):
        first_base = datetime(2026, 7, 27, 8, 5, 8, tzinfo=UTC)
        second_base = first_base + timedelta(hours=4, minutes=20)
        with RuntimeHealthState(self.path, self.policy) as state:
            first = state.prepare_heartbeat(self._payload(first_base))
            state.append_heartbeat(first)
            second = state.prepare_heartbeat(self._payload(second_base))
            self.assertIn("PAPER_HEARTBEAT_GAP", second["alerts"]["active"])
            self.assertGreater(second["heartbeat_gap_seconds_or_null"], 15300)

    def test_alert_raise_and_clear_transitions_are_replayed(self):
        first_base = datetime(2026, 7, 27, 12, 5, 8, tzinfo=UTC)
        with RuntimeHealthState(self.path, self.policy) as state:
            first = state.prepare_heartbeat(
                self._payload(
                    first_base,
                    active_alerts=("PAPER_SCHEDULER_FAILURE",),
                )
            )
            state.append_heartbeat(first)
            second = state.prepare_heartbeat(
                self._payload(first_base + timedelta(minutes=1))
            )
            self.assertEqual(
                second["alerts"]["cleared"], ["PAPER_SCHEDULER_FAILURE"]
            )
            state.append_heartbeat(second)
            snapshot = build_runtime_snapshot(state)
        self.assertEqual(
            runtime_snapshot_reasons(
                snapshot, runtime_snapshot_trust_hash(snapshot)
            ),
            (),
        )

    def test_symlink_state_is_rejected(self):
        target = Path(self.temp.name) / "target.sqlite"
        target.touch()
        link = Path(self.temp.name) / "linked.sqlite"
        link.symlink_to(target)
        with self.assertRaises(RuntimeHealthError):
            RuntimeHealthState(link, self.policy)

    def test_runtime_schema_is_packaged_mirrored_and_rejects_claims(self):
        root = Path(__file__).resolve().parents[1]
        governance = (
            root / "config" / "paper-runtime-snapshot-v1.schema.json"
        )
        packaged = resources.files("crypto_quant").joinpath(
            "schemas", "paper-runtime-snapshot-v1.schema.json"
        )
        self.assertEqual(
            governance.read_bytes(),
            packaged.read_bytes(),
        )
        schema = json.loads(governance.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        with RuntimeHealthState(self.path, self.policy) as state:
            state.append_heartbeat(
                self._payload(
                    datetime(2026, 7, 27, 12, 5, 8, tzinfo=UTC)
                )
            )
            snapshot = build_runtime_snapshot(state)
        snapshot["profitability_claim"] = "PROVEN"
        errors = tuple(Draft202012Validator(schema).iter_errors(snapshot))
        self.assertTrue(errors)


class RuntimeWrapperTests(unittest.TestCase):
    def test_blocked_probe_never_calls_paper_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bomb = BombTransport()
            result = run_healthy_paper_cycle(
                runtime_state_path=root / "state" / "runtime.sqlite",
                scheduler_state_path=root / "state" / "schedule.sqlite",
                output_root=root / "artifacts",
                worker_id="worker-a",
                server_time_transport=FakeTimeTransport(
                    fake_time_responses(offset_ms=8000, rtts=(50, 60, 55))
                ),
                paper_transport=bomb,
            )
            self.assertEqual(result["outcome"], "CLOCK_BLOCKED")
            self.assertEqual(bomb.calls, 0)
            self.assertEqual(result["server_time_request_count"], 3)
            self.assertEqual(result["paper_market_request_count"], 0)
            self.assertIn(
                "PAPER_CLOCK_PROBE_BLOCKED", result["active_alerts"]
            )
            self.assertTrue(Path(result["runtime_snapshot_path"]).is_file())

    def test_healthy_probe_runs_once_then_preserves_market_idempotency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            time_transport = FakeTimeTransport(
                fake_time_responses()
                + fake_time_responses(
                    base=datetime(
                        2026, 7, 27, 12, 6, 8, tzinfo=UTC
                    )
                )
            )
            first = run_healthy_paper_cycle(
                runtime_state_path=root / "state" / "runtime.sqlite",
                scheduler_state_path=root / "state" / "schedule.sqlite",
                output_root=root / "artifacts",
                worker_id="worker-a",
                server_time_transport=time_transport,
                paper_transport=paper_transport(),
            )
            second = run_healthy_paper_cycle(
                runtime_state_path=root / "state" / "runtime.sqlite",
                scheduler_state_path=root / "state" / "schedule.sqlite",
                output_root=root / "artifacts",
                worker_id="worker-a",
                server_time_transport=time_transport,
                paper_transport=BombTransport(),
            )
            self.assertEqual(first["outcome"], "EXECUTED")
            self.assertEqual(first["total_network_request_count"], 7)
            self.assertEqual(second["outcome"], "ALREADY_SUCCEEDED")
            self.assertEqual(second["paper_market_request_count"], 0)
            self.assertEqual(second["total_network_request_count"], 3)

    def test_cli_publishes_machine_readable_runtime_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "--runtime-state-path",
                        str(root / "runtime.sqlite"),
                        "--scheduler-state-path",
                        str(root / "schedule.sqlite"),
                        "--output-root",
                        str(root / "artifacts"),
                        "--worker-id",
                        "cli-worker",
                    ],
                    server_time_transport=FakeTimeTransport(
                        fake_time_responses()
                    ),
                    paper_transport=paper_transport(),
                )
            self.assertEqual(result, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["outcome"], "EXECUTED")
            self.assertTrue(Path(summary["runtime_snapshot_path"]).is_file())

    def test_cli_has_no_network_credential_order_or_time_overrides(self):
        for forbidden in (
            "--now",
            "--slot",
            "--url",
            "--header",
            "--api-key",
            "--secret",
            "--account",
            "--order",
        ):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([forbidden, "x"]), 2)


if __name__ == "__main__":
    unittest.main()
