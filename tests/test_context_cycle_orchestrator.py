import json
import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from crypto_quant.account_commission import (
    AccountCommissionHttpResponse,
    _create_test_signer,
)
from crypto_quant.context_cycle_orchestrator import (
    ContextCycleOrchestrationError,
    ContextCycleOrchestrationState,
    build_orchestration_snapshot,
    orchestration_snapshot_reasons,
    orchestration_snapshot_trust_hash,
    run_context_complete_orchestration,
)
from crypto_quant.context_cycle_orchestrator_cli import main
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.runtime_health import (
    RuntimeHealthError,
    VerifiedRuntimeGate,
    open_verified_runtime_gate,
)
from tests.test_account_commission import (
    futures_body,
    safe_permission_body,
    spot_body,
)
from tests.test_paper_scheduler import BombTransport, paper_transport
from tests.test_perpetual_context import (
    BombFuturesTransport,
    FakeFuturesTransport,
    fixture_responses,
)
from tests.test_runtime_health import (
    FakeTimeTransport,
    fake_time_responses,
)


UTC = timezone.utc


def iso(value):
    return value.astimezone(UTC).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


class MonotonicTicks:
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += 1_000_000_000
        return self.value


class DynamicAccountTransport:
    def __init__(self):
        self.bodies = [
            safe_permission_body(),
            spot_body(),
            futures_body(),
        ]
        self.calls = 0

    def get(self, request, _api_key_header):
        index = self.calls
        self.calls += 1
        if index >= len(self.bodies):
            raise AssertionError("unexpected account request")
        signed_at = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
            milliseconds=request.timestamp_ms
        )
        started = signed_at + timedelta(milliseconds=25)
        received = started + timedelta(milliseconds=25)
        return AccountCommissionHttpResponse(
            status=200,
            final_url=request.url,
            headers={
                "Date": "Mon, 27 Jul 2026 12:05:06 GMT",
                "X-MBX-USED-WEIGHT-1M": str(index + 1),
            },
            body=json.dumps(
                self.bodies[index], separators=(",", ":")
            ).encode(),
            request_started_at=iso(started),
            response_received_at=iso(received),
        )


class FailOnceFuturesTransport:
    def __init__(self):
        self.calls = 0

    def get(self, _request):
        self.calls += 1
        raise RuntimeHealthError("INJECTED_FUTURES_FAILURE")


def time_transport(*, second=0):
    return FakeTimeTransport(
        fake_time_responses(
            base=datetime(
                2026, 7, 27, 12, 5, second, tzinfo=UTC
            ),
            offset_ms=100,
            rtts=(50, 50, 50),
        )
    )


def futures_transport(*, receipt_second=13):
    responses = []
    base = datetime(
        2026, 7, 27, 12, 5, receipt_second, 300000, tzinfo=UTC
    )
    for index, response in enumerate(fixture_responses()):
        started = base + timedelta(milliseconds=index * 100)
        body = json.loads(response.body)
        shift_ms = (receipt_second - 13) * 1000
        if index in (0, 2):
            body["time"] += shift_ms
        responses.append(
            response.__class__(
                **{
                    **response.__dict__,
                    "body": json.dumps(
                        body, separators=(",", ":")
                    ).encode(),
                    "request_started_at": iso(started),
                    "response_received_at": iso(
                        started + timedelta(milliseconds=50)
                    ),
                }
            )
        )
    return FakeFuturesTransport(responses)


def paths(root):
    return {
        "orchestration_state_path": root / "orchestration.sqlite",
        "paper_state_path": root / "paper.sqlite",
        "context_state_path": root / "context.sqlite",
        "output_root": root / "output",
        "worker_id": "worker-a",
    }


def execute(root, **overrides):
    arguments = {
        **paths(root),
        "signer": _create_test_signer(),
        "server_time_transport": time_transport(),
        "account_transport": DynamicAccountTransport(),
        "paper_transport": paper_transport(),
        "futures_transport": futures_transport(),
        "monotonic_ns": MonotonicTicks(),
    }
    arguments.update(overrides)
    try:
        return run_context_complete_orchestration(**arguments)
    finally:
        arguments["signer"].close()


class SharedRuntimeGateTests(unittest.TestCase):
    def test_gate_is_issued_and_direct_construction_is_forbidden(self):
        gate = open_verified_runtime_gate(
            server_time_transport=time_transport(),
            monotonic_ns=MonotonicTicks(),
        )
        self.assertIsInstance(gate, VerifiedRuntimeGate)
        self.assertEqual(gate.probe_request_count, 3)
        self.assertIn(
            gate.probe["health_status"],
            ("HEALTHY_ALIGNED", "HEALTHY_CORRECTED"),
        )
        with self.assertRaises(TypeError):
            VerifiedRuntimeGate()


class ContextCycleOrchestratorTests(unittest.TestCase):
    def test_normal_path_uses_one_gate_and_exactly_fifteen_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = execute(root)
            self.assertEqual(result["outcome"], "EXECUTED")
            self.assertEqual(
                result["physical_network_request_count"], 15
            )
            self.assertEqual(result["account_request_count"], 3)
            self.assertEqual(result["paper_request_count"], 4)
            self.assertEqual(result["perpetual_request_count"], 5)
            self.assertTrue(result["normal_path_shared_gate"])
            snapshot = json.loads(
                Path(result["orchestration_snapshot_path"]).read_text()
            )
            self.assertEqual(
                snapshot["summary"]["physical_network_request_count"],
                15,
            )
            self.assertEqual(
                snapshot["summary"]["unique_runtime_probe_count"], 1
            )
            trust = result["orchestration_trust_hash"]
            self.assertEqual(
                orchestration_snapshot_reasons(snapshot, trust), ()
            )
            account = json.loads(
                next(
                    (root / "output" / "account-cost").glob("*.json")
                ).read_text()
            )
            perpetual = json.loads(
                next(
                    path
                    for path in (
                        root / "output" / "market-data"
                    ).glob("*.json")
                    if path.name.startswith("perpetual_context_")
                ).read_text()
            )
            self.assertEqual(
                account["server_time_probe"]["probe_hash"],
                result["runtime_probe_hash"],
            )
            self.assertEqual(
                perpetual["server_time_probe"]["probe_hash"],
                result["runtime_probe_hash"],
            )

    def test_account_prepare_crash_reuses_predecision_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            signer = _create_test_signer()
            with self.assertRaises(ContextCycleOrchestrationError):
                run_context_complete_orchestration(
                    **paths(root),
                    signer=signer,
                    server_time_transport=time_transport(),
                    account_transport=DynamicAccountTransport(),
                    paper_transport=BombTransport(),
                    futures_transport=BombFuturesTransport(),
                    monotonic_ns=MonotonicTicks(),
                    fault_after_account_prepare=True,
                )
            signer.close()
            signer = _create_test_signer()
            account_bomb = DynamicAccountTransport()
            account_bomb.bodies = []
            result = run_context_complete_orchestration(
                **paths(root),
                signer=signer,
                server_time_transport=time_transport(second=20),
                account_transport=account_bomb,
                paper_transport=paper_transport(),
                futures_transport=futures_transport(receipt_second=23),
                monotonic_ns=MonotonicTicks(),
            )
            signer.close()
            self.assertEqual(result["outcome"], "RECOVERED")
            self.assertEqual(result["account_request_count"], 0)
            self.assertEqual(
                result["physical_network_request_count"], 12
            )
            self.assertFalse(result["normal_path_shared_gate"])

    def test_perpetual_failure_reuses_account_and_paper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            signer = _create_test_signer()
            with self.assertRaises(ContextCycleOrchestrationError):
                run_context_complete_orchestration(
                    **paths(root),
                    signer=signer,
                    server_time_transport=time_transport(),
                    account_transport=DynamicAccountTransport(),
                    paper_transport=paper_transport(),
                    futures_transport=FailOnceFuturesTransport(),
                    monotonic_ns=MonotonicTicks(),
                )
            signer.close()
            signer = _create_test_signer()
            result = run_context_complete_orchestration(
                **paths(root),
                signer=signer,
                server_time_transport=time_transport(second=20),
                account_transport=DynamicAccountTransport(),
                paper_transport=BombTransport(),
                futures_transport=futures_transport(receipt_second=23),
                monotonic_ns=MonotonicTicks(),
            )
            signer.close()
            self.assertEqual(result["outcome"], "RECOVERED")
            self.assertEqual(result["account_request_count"], 0)
            self.assertEqual(result["paper_request_count"], 0)
            self.assertEqual(result["perpetual_request_count"], 5)
            self.assertEqual(
                result["physical_network_request_count"], 8
            )

    def test_completed_slot_checks_clock_but_makes_no_stage_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            execute(root)
            signer = _create_test_signer()
            result = run_context_complete_orchestration(
                **paths(root),
                signer=signer,
                server_time_transport=time_transport(second=20),
                account_transport=DynamicAccountTransport(),
                paper_transport=BombTransport(),
                futures_transport=BombFuturesTransport(),
                monotonic_ns=MonotonicTicks(),
            )
            signer.close()
            self.assertEqual(result["outcome"], "ALREADY_SUCCEEDED")
            self.assertEqual(
                result["physical_network_request_count"], 3
            )
            self.assertEqual(result["account_request_count"], 0)
            self.assertEqual(result["paper_request_count"], 0)
            self.assertEqual(result["perpetual_request_count"], 0)

    def test_event_and_blob_tampering_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            execute(root)
            state_path = paths(root)["orchestration_state_path"]
            connection = sqlite3.connect(state_path)
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute(
                    "UPDATE orchestration_events SET event_type='x'"
                )
            connection.close()
            raw = sqlite3.connect(state_path)
            raw.execute("DROP TRIGGER orchestration_blobs_no_update")
            raw.execute(
                "UPDATE orchestration_blobs SET artifact_bytes=? "
                "WHERE blob_type='ACCOUNT'",
                (b"{}",),
            )
            raw.commit()
            raw.close()
            with self.assertRaises(ContextCycleOrchestrationError):
                ContextCycleOrchestrationState(
                    state_path, paths(root)["output_root"]
                )

    def test_snapshot_rejects_semantic_mutation_after_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            execute(root)
            with ContextCycleOrchestrationState(
                paths(root)["orchestration_state_path"],
                paths(root)["output_root"],
            ) as state:
                snapshot = build_orchestration_snapshot(state)
            changed = deepcopy(snapshot)
            changed["summary"]["physical_network_request_count"] = 999
            changed["snapshot_hash"] = artifact_self_hash(
                changed, "snapshot_hash"
            )
            trust = orchestration_snapshot_trust_hash(changed)
            self.assertTrue(
                orchestration_snapshot_reasons(changed, trust)
            )

    def test_schema_is_packaged_and_valid(self):
        governance = (
            Path(__file__).parents[1]
            / "config"
            / "context-cycle-orchestration-snapshot-v1.schema.json"
        )
        packaged = resources.files("crypto_quant").joinpath(
            "schemas",
            "context-cycle-orchestration-snapshot-v1.schema.json",
        )
        self.assertEqual(governance.read_bytes(), packaged.read_bytes())
        Draft202012Validator.check_schema(
            json.loads(governance.read_text())
        )

    def test_cli_executes_and_missing_credentials_make_zero_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = [
                "--orchestration-state-path",
                str(root / "orchestration.sqlite"),
                "--paper-state-path",
                str(root / "paper.sqlite"),
                "--context-state-path",
                str(root / "context.sqlite"),
                "--output-root",
                str(root / "output"),
                "--worker-id",
                "worker-a",
            ]
            time_source = time_transport()
            with patch.dict(os.environ, {}, clear=True), redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(
                    main(
                        base,
                        workspace_root=root,
                        server_time_transport=time_source,
                    ),
                    1,
                )
            self.assertEqual(time_source.calls, 0)

            signer = _create_test_signer()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(
                        base,
                        signer=signer,
                        workspace_root=root,
                        server_time_transport=time_transport(),
                        account_transport=DynamicAccountTransport(),
                        paper_transport=paper_transport(),
                        futures_transport=futures_transport(),
                        monotonic_ns=MonotonicTicks(),
                    ),
                    0,
                )
            signer.close()
            self.assertEqual(
                json.loads(stdout.getvalue())["outcome"], "EXECUTED"
            )

    def test_cli_has_no_url_key_value_order_or_time_overrides(self):
        forbidden = (
            "--url",
            "--host",
            "--proxy",
            "--api-key",
            "--api-secret",
            "--credential-value",
            "--order",
            "--symbol",
            "--clock",
            "--created-at",
        )
        for argument in forbidden:
            with self.subTest(argument=argument), redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(main([argument, "x"]), 2)


if __name__ == "__main__":
    unittest.main()
