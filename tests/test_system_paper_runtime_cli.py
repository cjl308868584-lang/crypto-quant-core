"""Authority, path and recovery contract for the System Paper runtime CLI."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import crypto_quant.system_paper_scheduler as scheduler_module
from crypto_quant.canonical import canonical_json
from crypto_quant.system_paper_broker import FillScenario
from crypto_quant.system_paper_plan import build_system_paper_plan
from crypto_quant.system_paper_public_input import capture_system_paper_input
from crypto_quant.system_paper_runtime import (
    SystemPaperSlotInputs,
    build_initial_system_paper_runtime_snapshot,
    load_system_paper_slot_result_bytes,
    run_system_paper_slot,
)
from crypto_quant.system_paper_runtime_cli import main
from crypto_quant.system_paper_scheduler import (
    SystemPaperInputRequest,
    SystemPaperSchedulePolicy,
    SystemPaperScheduleState,
)
from tests.system_paper_fixtures import valid_public_transport


NOW = "2026-08-02T12:05:11.000Z"
RECOVERY_NOW = "2026-08-02T12:20:12.000Z"


class BombTransport:
    def __init__(self):
        self.requests = []

    def get(self, request):
        self.requests.append(request)
        raise AssertionError("recovery and rejected paths must not use network")


class SystemPaperRuntimeCliTests(unittest.TestCase):
    def invoke(self, argv, **injected):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(argv, **injected)
        return status, stdout.getvalue(), stderr.getvalue()

    def roots(self, base):
        normalized_base = Path(base).resolve()
        state_root = normalized_base / "state"
        output_root = normalized_base / "artifacts"
        state_root.mkdir(mode=0o700)
        output_root.mkdir(mode=0o700)
        os.chmod(state_root, 0o700)
        os.chmod(output_root, 0o700)
        return state_root / "system-paper.sqlite", output_root

    def test_help_exposes_only_the_two_fixed_path_options(self):
        status, stdout, stderr = self.invoke(["--help"])

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("--state-path", stdout)
        self.assertIn("--output-root", stdout)
        for forbidden in (
            "--url",
            "--symbol",
            "--time",
            "--plan",
            "--price",
            "--fee",
            "--fill",
            "--credential",
            "--account",
            "--broker",
            "--order",
            "--date",
            "--worker",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, stdout)

    def test_argument_and_unsafe_path_failures_are_one_canonical_error_line(self):
        bomb = BombTransport()
        cases = []
        with tempfile.TemporaryDirectory() as directory:
            state_path, output_root = self.roots(directory)
            symlink_root = Path(directory) / "artifact-link"
            symlink_root.symlink_to(output_root, target_is_directory=True)
            unsafe_state_root = Path(directory) / "unsafe-state"
            unsafe_state_root.mkdir(mode=0o755)
            os.chmod(unsafe_state_root, 0o755)
            cases.extend(
                (
                    ("unknown_option", ["--url", "https://example.invalid"]),
                    (
                        "relative_state",
                        [
                            "--state-path",
                            "state.sqlite",
                            "--output-root",
                            str(output_root),
                        ],
                    ),
                    (
                        "relative_output",
                        [
                            "--state-path",
                            str(state_path),
                            "--output-root",
                            "artifacts",
                        ],
                    ),
                    (
                        "noncanonical_parent_escape",
                        [
                            "--state-path",
                            str(
                                output_root
                                / ".."
                                / "state"
                                / "system-paper.sqlite"
                            ),
                            "--output-root",
                            str(output_root),
                        ],
                    ),
                    (
                        "symlink_output",
                        [
                            "--state-path",
                            str(state_path),
                            "--output-root",
                            str(symlink_root),
                        ],
                    ),
                    (
                        "unsafe_state_mode",
                        [
                            "--state-path",
                            str(unsafe_state_root / "state.sqlite"),
                            "--output-root",
                            str(output_root),
                        ],
                    ),
                )
            )
            for name, argv in cases:
                with self.subTest(name=name):
                    status, stdout, stderr = self.invoke(
                        argv,
                        transport=bomb,
                        clock=lambda: NOW,
                        worker_identity="test-invocation",
                    )
                    self.assertEqual(status, 1)
                    self.assertEqual(stdout, "")
                    self.assertEqual(len(stderr.splitlines()), 1)
                    self.assertEqual(
                        canonical_json(json.loads(stderr)),
                        stderr.rstrip("\n"),
                    )
            self.assertEqual(bomb.requests, [])

            with patch(
                "crypto_quant.system_paper_runtime_cli.os.getuid",
                return_value=os.getuid() + 1,
            ):
                status, _stdout, _stderr = self.invoke(
                    [
                        "--state-path",
                        str(state_path),
                        "--output-root",
                        str(output_root),
                    ],
                    transport=bomb,
                    clock=lambda: NOW,
                    worker_identity="test-invocation",
                )
            self.assertEqual(status, 1)
            self.assertEqual(bomb.requests, [])

    def test_fresh_slot_then_idempotent_replay_uses_four_then_zero_gets(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path, output_root = self.roots(directory)
            first_transport, clock = valid_public_transport(
                recorded_at_or_none=NOW
            )

            status, stdout, stderr = self.invoke(
                [
                    "--state-path",
                    str(state_path),
                    "--output-root",
                    str(output_root),
                ],
                transport=first_transport,
                clock=clock,
                worker_identity="fresh-invocation",
            )

            self.assertEqual((status, stderr), (0, ""))
            first = json.loads(stdout)
            self.assertEqual(first["outcome"], "EXECUTED")
            self.assertEqual(first["network_request_count"], 4)
            self.assertEqual(len(first_transport.requests), 4)
            self.assertNotIn("pnl", stdout.lower())
            self.assertNotIn("response_body", stdout)
            self.assertEqual(state_path.stat().st_mode & 0o777, 0o600)
            result_path = Path(first["result_path_or_null"])
            loaded = load_system_paper_slot_result_bytes(result_path.read_bytes())
            self.assertEqual(loaded["slot_hash"], first["slot_hash_or_null"])

            second_transport = BombTransport()
            status, stdout, stderr = self.invoke(
                [
                    "--state-path",
                    str(state_path),
                    "--output-root",
                    str(output_root),
                ],
                transport=second_transport,
                clock=clock,
                worker_identity="replay-invocation",
            )
            self.assertEqual((status, stderr), (0, ""))
            second = json.loads(stdout)
            self.assertEqual(second["outcome"], "ALREADY_SUCCEEDED")
            self.assertEqual(second["network_request_count"], 0)
            self.assertEqual(second_transport.requests, [])

    def seed_durable_stage(self, state_path, output_root, *, with_result):
        plan = build_system_paper_plan()
        policy = SystemPaperSchedulePolicy.create(plan)
        slot = policy.current_slot(NOW)
        transport, clock = valid_public_transport(recorded_at_or_none=NOW)
        capture = capture_system_paper_input(
            SystemPaperInputRequest.for_slot(policy, slot),
            transport=transport,
            clock=clock,
        )
        scenario = FillScenario.partial_then_full("0.40")
        with SystemPaperScheduleState(state_path, policy) as state:
            claim = state.claim(slot, worker_id="seed-worker", claimed_at=NOW)
            prepared = state.prepare_input(
                claim,
                plan=plan,
                capture=capture,
                previous_runtime_snapshot=build_initial_system_paper_runtime_snapshot(
                    plan
                ),
                fill_scenario=scenario,
                output_root_hash=scheduler_module._output_root_hash(output_root),
                prepared_at=NOW,
            )
            if with_result:
                payload = prepared["payload"]
                result = run_system_paper_slot(
                    SystemPaperSlotInputs(
                        plan=payload["plan"],
                        scheduled_for=payload["scheduled_for"],
                        public_market_bundle=payload["capture"][
                            "public_market_bundle"
                        ],
                        previous_runtime_snapshot=payload[
                            "previous_runtime_snapshot"
                        ],
                        fill_scenario=scenario,
                    )
                )
                state.prepare_result(
                    claim,
                    result_bytes=canonical_json(result).encode("utf-8"),
                    parent_result_bodies=(),
                    prepared_at=NOW,
                )
        os.chmod(state_path, 0o600)

    def test_prepared_input_and_result_recovery_use_zero_new_gets(self):
        for stage, with_result, expected in (
            ("input", False, "RESUMED_INPUT"),
            ("result", True, "RESUMED_RESULT"),
        ):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                state_path, output_root = self.roots(directory)
                self.seed_durable_stage(
                    state_path,
                    output_root,
                    with_result=with_result,
                )
                transport = BombTransport()

                status, stdout, stderr = self.invoke(
                    [
                        "--state-path",
                        str(state_path),
                        "--output-root",
                        str(output_root),
                    ],
                    transport=transport,
                    clock=lambda: RECOVERY_NOW,
                    worker_identity="recovery-" + stage,
                )

                self.assertEqual((status, stderr), (0, ""))
                summary = json.loads(stdout)
                self.assertEqual(summary["outcome"], expected)
                self.assertEqual(summary["network_request_count"], 0)
                self.assertEqual(transport.requests, [])


if __name__ == "__main__":
    unittest.main()
