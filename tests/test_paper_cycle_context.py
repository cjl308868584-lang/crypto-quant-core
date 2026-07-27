import io
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.evidence import artifact_self_hash
from crypto_quant.offline_paper import PublicPaperHttpResponse
from crypto_quant.paper_context_scheduler import (
    PaperContextScheduleError,
    PaperContextScheduleState,
    build_context_schedule_snapshot,
    context_schedule_snapshot_reasons,
    context_schedule_snapshot_trust_hash,
    run_context_complete_paper_cycle,
)
from crypto_quant.paper_context_scheduler_cli import main
from crypto_quant.paper_cost_binding import (
    build_paper_account_cost_binding,
    paper_account_cost_binding_trust_hash,
)
from crypto_quant.paper_cycle_context import (
    PaperCycleContextError,
    build_paper_cycle_context_bundle,
    paper_cycle_context_reasons,
    paper_cycle_context_trust_hash,
)
from crypto_quant.paper_scheduler import (
    PaperSchedulePolicy,
    run_due_paper_cycle,
)
from crypto_quant.perpetual_context import (
    build_perpetual_context_snapshot,
    capture_perpetual_context,
    perpetual_context_trust_hash,
)
from tests.test_offline_paper import FakeTransport, valid_capture
from tests.test_paper_cost_binding import account_snapshot_at
from tests.test_paper_scheduler import paper_transport
from tests.test_perpetual_context import (
    FakeFuturesTransport,
    fixture_responses,
)
from tests.test_runtime_health import (
    FakeTimeTransport,
    fake_time_responses,
)


ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def paper_transport_at(base):
    capture, _ = valid_capture()
    responses = []
    for index, receipt in enumerate(capture.receipts):
        start = base + timedelta(milliseconds=index * 100)
        responses.append(
            PublicPaperHttpResponse(
                status=200,
                final_url=receipt["final_url"],
                headers={"Date": "Mon, 27 Jul 2026 12:30:00 GMT"},
                body=receipt["response_body_utf8"].encode(),
                request_started_at=iso(start),
                response_received_at=iso(
                    start + timedelta(milliseconds=50)
                ),
            )
        )
    return FakeTransport(responses)


def perpetual_snapshot():
    capture = capture_perpetual_context(
        server_time_transport=FakeTimeTransport(fake_time_responses()),
        futures_transport=FakeFuturesTransport(fixture_responses()),
    )
    snapshot = build_perpetual_context_snapshot(capture)
    return snapshot, perpetual_context_trust_hash(snapshot)


def scheduled_cost_binding(root, *, late_paper=False):
    paper_output = root / ("late-paper" if late_paper else "paper")
    base = (
        datetime(2026, 7, 27, 12, 30, tzinfo=UTC)
        if late_paper
        else None
    )
    result = run_due_paper_cycle(
        state_path=root / (
            "late-paper.sqlite" if late_paper else "paper.sqlite"
        ),
        output_root=paper_output,
        worker_id="paper-worker",
        transport=(
            paper_transport_at(base) if base is not None else paper_transport()
        ),
        clock=lambda: (
            "2026-07-27T12:31:00.000Z"
            if late_paper
            else "2026-07-27T12:05:11.000Z"
        ),
    )
    paper = json.loads(Path(result["artifact_path"]).read_text())
    account, account_trust = account_snapshot_at(
        datetime(2026, 7, 27, 11, 55, tzinfo=UTC)
    )
    binding = build_paper_account_cost_binding(
        offline_paper_run=paper,
        offline_paper_trusted_attestation_hash=result[
            "cycle_trust_hash"
        ],
        account_commission_snapshot=account,
        account_commission_trusted_attestation_hash=account_trust,
        created_at=(
            "2026-07-27T12:31:01.000Z"
            if late_paper
            else "2026-07-27T12:05:12.000Z"
        ),
    )
    return {
        "binding": binding,
        "binding_trust": paper_account_cost_binding_trust_hash(binding),
        "paper_trust": result["cycle_trust_hash"],
        "account_trust": account_trust,
    }


def complete_sources(root):
    cost = scheduled_cost_binding(root)
    perpetual, perpetual_trust = perpetual_snapshot()
    return {
        **cost,
        "perpetual": perpetual,
        "perpetual_trust": perpetual_trust,
    }


def build_bundle(source):
    return build_paper_cycle_context_bundle(
        paper_cost_binding=source["binding"],
        paper_cost_binding_trusted_attestation_hash=source[
            "binding_trust"
        ],
        offline_paper_trusted_attestation_hash=source["paper_trust"],
        account_commission_trusted_attestation_hash=source[
            "account_trust"
        ],
        perpetual_context_snapshot=source["perpetual"],
        perpetual_context_trusted_attestation_hash=source[
            "perpetual_trust"
        ],
        created_at="2026-07-27T12:05:14.000Z",
    )


def runner_kwargs(root, source):
    return {
        "state_path": root / "context.sqlite",
        "output_root": root / "context-artifacts",
        "worker_id": "context-worker-a",
        "clock": lambda: "2026-07-27T12:05:14.000Z",
        "paper_cost_binding": source["binding"],
        "paper_cost_binding_trusted_attestation_hash": source[
            "binding_trust"
        ],
        "offline_paper_trusted_attestation_hash": source["paper_trust"],
        "account_commission_trusted_attestation_hash": source[
            "account_trust"
        ],
        "perpetual_context_snapshot": source["perpetual"],
        "perpetual_context_trusted_attestation_hash": source[
            "perpetual_trust"
        ],
    }


class PaperCycleContextBundleTests(unittest.TestCase):
    def test_bundle_binds_exact_slot_cost_and_observational_perpetual(self):
        with tempfile.TemporaryDirectory() as directory:
            source = complete_sources(Path(directory))
            bundle = build_bundle(source)
        pit = bundle["pit_context"]
        self.assertEqual(
            pit["slot"]["slot_id"], "ETHUSDT_20260727T120000Z"
        )
        self.assertEqual(
            pit["perpetual_availability_role"],
            "POST_DECISION_OBSERVATIONAL_NOT_SIGNAL",
        )
        self.assertLessEqual(pit["absolute_source_skew_seconds"], 3)
        self.assertFalse(pit["perpetual_used_in_signal"])
        self.assertFalse(
            bundle["perpetual_observation"]["funding_realized"]
        )
        self.assertEqual(
            bundle["cycle_eligibility"],
            "CONTEXT_COMPLETE_RESEARCH_ONLY",
        )
        trust = paper_cycle_context_trust_hash(bundle)
        self.assertEqual(
            paper_cycle_context_reasons(
                bundle,
                trust,
                paper_cost_binding_trusted_attestation_hash=source[
                    "binding_trust"
                ],
                offline_paper_trusted_attestation_hash=source[
                    "paper_trust"
                ],
                account_commission_trusted_attestation_hash=source[
                    "account_trust"
                ],
                perpetual_context_trusted_attestation_hash=source[
                    "perpetual_trust"
                ],
            ),
            (),
        )

    def test_unscheduled_smoke_run_is_not_a_scheduler_slot(self):
        from tests.test_paper_cost_binding import filled_binding

        binding, paper_trust, account_trust = filled_binding()
        perpetual, perpetual_trust = perpetual_snapshot()
        with self.assertRaisesRegex(
            PaperCycleContextError,
            "PAPER_CONTEXT_SCHEDULED_RUN_MISMATCH",
        ):
            build_paper_cycle_context_bundle(
                paper_cost_binding=binding,
                paper_cost_binding_trusted_attestation_hash=(
                    paper_account_cost_binding_trust_hash(binding)
                ),
                offline_paper_trusted_attestation_hash=paper_trust,
                account_commission_trusted_attestation_hash=(
                    account_trust
                ),
                perpetual_context_snapshot=perpetual,
                perpetual_context_trusted_attestation_hash=(
                    perpetual_trust
                ),
                created_at="2026-07-27T14:00:00.000Z",
            )

    def test_more_than_fifteen_minute_source_skew_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cost = scheduled_cost_binding(root, late_paper=True)
            perpetual, perpetual_trust = perpetual_snapshot()
            with self.assertRaisesRegex(
                PaperCycleContextError,
                "PAPER_CONTEXT_SOURCE_SKEW_EXCEEDED",
            ):
                build_paper_cycle_context_bundle(
                    paper_cost_binding=cost["binding"],
                    paper_cost_binding_trusted_attestation_hash=cost[
                        "binding_trust"
                    ],
                    offline_paper_trusted_attestation_hash=cost[
                        "paper_trust"
                    ],
                    account_commission_trusted_attestation_hash=cost[
                        "account_trust"
                    ],
                    perpetual_context_snapshot=perpetual,
                    perpetual_context_trusted_attestation_hash=(
                        perpetual_trust
                    ),
                    created_at="2026-07-27T12:31:02.000Z",
                )

    def test_each_external_source_trust_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            source = complete_sources(Path(directory))
            names = (
                "binding_trust",
                "paper_trust",
                "account_trust",
                "perpetual_trust",
            )
            for name in names:
                candidate = dict(source)
                candidate[name] = "0" * 64
                with self.subTest(name=name), self.assertRaises(
                    PaperCycleContextError
                ):
                    build_bundle(candidate)

    def test_derived_and_nested_tampering_fail_after_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            source = complete_sources(Path(directory))
            bundle = build_bundle(source)
        cases = []
        cost = deepcopy(bundle)
        cost["cost_outcome"][
            "account_costed_liquidation_net_change_usdt"
        ] = "99"
        cases.append(cost)
        funding = deepcopy(bundle)
        funding["perpetual_observation"]["funding_realized"] = True
        cases.append(funding)
        nested = deepcopy(bundle)
        nested["perpetual_context_snapshot"]["recorded_at"] = (
            "2026-07-27T12:05:14.000Z"
        )
        cases.append(nested)
        for candidate in cases:
            candidate["bundle_hash"] = artifact_self_hash(
                candidate, "bundle_hash"
            )
            forged = paper_cycle_context_trust_hash(candidate)
            with self.subTest():
                self.assertTrue(
                    paper_cycle_context_reasons(
                        candidate,
                        forged,
                        paper_cost_binding_trusted_attestation_hash=source[
                            "binding_trust"
                        ],
                        offline_paper_trusted_attestation_hash=source[
                            "paper_trust"
                        ],
                        account_commission_trusted_attestation_hash=source[
                            "account_trust"
                        ],
                        perpetual_context_trusted_attestation_hash=source[
                            "perpetual_trust"
                        ],
                    )
                )

    def test_schema_is_mirrored_and_rejects_extra_claims(self):
        governance = (
            ROOT / "config" / "paper-cycle-context-bundle-v1.schema.json"
        )
        packaged = resources.files("crypto_quant").joinpath(
            "schemas", "paper-cycle-context-bundle-v1.schema.json"
        )
        self.assertEqual(governance.read_bytes(), packaged.read_bytes())
        schema = json.loads(governance.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        with tempfile.TemporaryDirectory() as directory:
            bundle = build_bundle(complete_sources(Path(directory)))
        self.assertEqual(
            tuple(Draft202012Validator(schema).iter_errors(bundle)),
            (),
        )
        bundle["profitable"] = True
        self.assertTrue(
            tuple(Draft202012Validator(schema).iter_errors(bundle))
        )


class PaperContextScheduleTests(unittest.TestCase):
    def test_execute_then_same_slot_is_idempotent_without_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = complete_sources(root)
            first = run_context_complete_paper_cycle(
                **runner_kwargs(root, source)
            )
            self.assertEqual(first["outcome"], "EXECUTED")
            self.assertEqual(first["source_read_count"], 2)
            self.assertEqual(first["network_request_count"], 0)
            self.assertEqual(first["context_complete_slot_count"], 1)
            self.assertFalse(first["ninety_day_context_complete"])
            artifact = Path(first["artifact_path"])
            self.assertTrue(artifact.is_file())
            self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                (root / "context.sqlite").stat().st_mode & 0o777,
                0o600,
            )
            schedule = json.loads(
                Path(first["schedule_snapshot_path"]).read_text()
            )
            self.assertEqual(
                context_schedule_snapshot_reasons(
                    schedule, first["schedule_trust_hash"]
                ),
                (),
            )

            second = run_context_complete_paper_cycle(
                state_path=root / "context.sqlite",
                output_root=root / "context-artifacts",
                worker_id="context-worker-b",
                clock=lambda: "2026-07-27T12:06:00.000Z",
            )
            self.assertEqual(second["outcome"], "ALREADY_SUCCEEDED")
            self.assertEqual(second["source_read_count"], 0)
            self.assertEqual(
                first["artifact_sha256"], second["artifact_sha256"]
            )
            self.assertFalse(second["schedule_snapshot_created"])

    def test_prepared_crash_resumes_exact_bytes_with_zero_source_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = complete_sources(root)
            kwargs = runner_kwargs(root, source)
            with self.assertRaisesRegex(
                PaperContextScheduleError,
                "INJECTED_CONTEXT_AFTER_PREPARE",
            ):
                run_context_complete_paper_cycle(
                    **kwargs, fault_after_prepare=True
                )
            self.assertFalse(
                (root / "context-artifacts" / "paper-context").exists()
            )
            resumed = run_context_complete_paper_cycle(
                state_path=root / "context.sqlite",
                output_root=root / "context-artifacts",
                worker_id="context-worker-b",
                clock=lambda: "2026-07-27T12:21:00.000Z",
            )
            self.assertEqual(resumed["outcome"], "RESUMED_PREPARED")
            self.assertEqual(resumed["source_read_count"], 0)
            self.assertEqual(resumed["network_request_count"], 0)
            self.assertEqual(
                hashlib.sha256(
                    Path(resumed["artifact_path"]).read_bytes()
                ).hexdigest(),
                resumed["artifact_sha256"],
            )

    def test_published_crash_is_adopted_without_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = complete_sources(root)
            with self.assertRaisesRegex(
                PaperContextScheduleError,
                "INJECTED_CONTEXT_AFTER_PUBLISH",
            ):
                run_context_complete_paper_cycle(
                    **runner_kwargs(root, source),
                    fault_after_publish=True,
                )
            artifact = (
                root
                / "context-artifacts"
                / "paper-context"
                / "paper-context-ethusdt_20260727t120000z.json"
            )
            original = artifact.read_bytes()
            result = run_context_complete_paper_cycle(
                state_path=root / "context.sqlite",
                output_root=root / "context-artifacts",
                worker_id="context-worker-b",
                clock=lambda: "2026-07-27T12:21:00.000Z",
            )
            self.assertEqual(result["outcome"], "RESUMED_PREPARED")
            self.assertFalse(result["artifact_created"])
            self.assertEqual(artifact.read_bytes(), original)

    def test_live_lease_busy_and_output_root_is_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = complete_sources(root)
            kwargs = runner_kwargs(root, source)
            with self.assertRaises(PaperContextScheduleError):
                run_context_complete_paper_cycle(
                    **kwargs, fault_after_prepare=True
                )
            busy = run_context_complete_paper_cycle(
                state_path=root / "context.sqlite",
                output_root=root / "context-artifacts",
                worker_id="context-worker-b",
                clock=lambda: "2026-07-27T12:10:00.000Z",
            )
            self.assertEqual(busy["outcome"], "BUSY")
            with self.assertRaisesRegex(
                PaperContextScheduleError,
                "PAPER_CONTEXT_SCHEDULE_OUTPUT_ROOT_MISMATCH",
            ):
                run_context_complete_paper_cycle(
                    state_path=root / "context.sqlite",
                    output_root=root / "different",
                    worker_id="context-worker-b",
                    clock=lambda: "2026-07-27T12:21:00.000Z",
                )

    def test_missing_sources_records_failure_and_can_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(
                PaperContextScheduleError,
                "PAPER_CONTEXT_SOURCES_REQUIRED",
            ):
                run_context_complete_paper_cycle(
                    state_path=root / "context.sqlite",
                    output_root=root / "output",
                    worker_id="worker-a",
                    clock=lambda: "2026-07-27T12:05:14.000Z",
                )
            with PaperContextScheduleState(
                root / "context.sqlite"
            ) as state:
                projection = state.projection()
                slot = "ETHUSDT_20260727T120000Z"
                self.assertEqual(projection[slot]["status"], "FAILED")
                self.assertEqual(projection[slot]["failure_count"], 1)

    def test_database_event_and_blob_tampering_is_detected(self):
        for table, column, value, trigger in (
            (
                "context_events",
                "payload_json",
                "{}",
                "context_events_no_update",
            ),
            (
                "prepared_context_blobs",
                "artifact_bytes",
                b"{}",
                "prepared_context_blobs_no_update",
            ),
        ):
            with self.subTest(table=table), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                source = complete_sources(root)
                run_context_complete_paper_cycle(
                    **runner_kwargs(root, source)
                )
                connection = sqlite3.connect(
                    str(root / "context.sqlite")
                )
                connection.execute(f"DROP TRIGGER {trigger}")
                connection.execute(
                    f"UPDATE {table} SET {column} = ?",
                    (value,),
                )
                connection.commit()
                connection.close()
                with self.assertRaises(PaperContextScheduleError):
                    with PaperContextScheduleState(
                        root / "context.sqlite"
                    ):
                        pass

    def test_context_schedule_counts_only_sidecar_success_and_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = complete_sources(root)
            run_context_complete_paper_cycle(
                **runner_kwargs(root, source)
            )
            with PaperContextScheduleState(
                root / "context.sqlite"
            ) as state:
                snapshot = build_context_schedule_snapshot(state)
            trust = context_schedule_snapshot_trust_hash(snapshot)
            self.assertEqual(
                context_schedule_snapshot_reasons(snapshot, trust),
                (),
            )
            self.assertEqual(
                snapshot["summary"]["context_complete_slot_count"], 1
            )
            self.assertEqual(
                snapshot["summary"]["known_slot_count"], 1
            )
            self.assertFalse(
                snapshot["summary"]["ninety_day_context_complete"]
            )
            changed = deepcopy(snapshot)
            changed["summary"]["context_complete_slot_count"] = 99
            self.assertTrue(
                context_schedule_snapshot_reasons(changed, trust)
            )
            changed = deepcopy(snapshot)
            changed["recorded_at"] = "2026-07-27T11:59:59.000Z"
            changed["snapshot_hash"] = artifact_self_hash(
                changed, "snapshot_hash"
            )
            changed_trust = context_schedule_snapshot_trust_hash(changed)
            self.assertIn(
                "PAPER_CONTEXT_SCHEDULE_SNAPSHOT_TIME_INVALID",
                context_schedule_snapshot_reasons(
                    changed, changed_trust
                ),
            )

    def test_context_schedule_schema_is_mirrored(self):
        governance = (
            ROOT
            / "config"
            / "paper-context-schedule-snapshot-v1.schema.json"
        )
        packaged = resources.files("crypto_quant").joinpath(
            "schemas", "paper-context-schedule-snapshot-v1.schema.json"
        )
        self.assertEqual(governance.read_bytes(), packaged.read_bytes())
        schema = json.loads(governance.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


class PaperContextSchedulerCliTests(unittest.TestCase):
    def test_cli_executes_and_resume_needs_only_state_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = complete_sources(root)
            files = {}
            for name, value in (
                ("binding", source["binding"]),
                ("perpetual", source["perpetual"]),
            ):
                path = root / f"{name}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                files[name] = path
            for name in (
                "binding_trust",
                "paper_trust",
                "account_trust",
                "perpetual_trust",
            ):
                path = root / f"{name}.txt"
                path.write_text(source[name] + "\n", encoding="ascii")
                files[name] = path
            base = [
                "--state-path",
                str(root / "cli.sqlite"),
                "--output-root",
                str(root / "cli-output"),
                "--worker-id",
                "cli-worker-a",
            ]
            initial = base + [
                "--paper-cost-binding",
                str(files["binding"]),
                "--paper-cost-binding-trust-hash-file",
                str(files["binding_trust"]),
                "--offline-paper-trust-hash-file",
                str(files["paper_trust"]),
                "--account-commission-trust-hash-file",
                str(files["account_trust"]),
                "--perpetual-context-snapshot",
                str(files["perpetual"]),
                "--perpetual-context-trust-hash-file",
                str(files["perpetual_trust"]),
            ]
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(
                        initial,
                        clock=lambda: "2026-07-27T12:05:14.000Z",
                    ),
                    0,
                )
            self.assertEqual(
                json.loads(stdout.getvalue())["outcome"], "EXECUTED"
            )
            resume = base[:-1] + ["cli-worker-b"]
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(
                        resume,
                        clock=lambda: "2026-07-27T12:06:00.000Z",
                    ),
                    0,
                )
            self.assertEqual(
                json.loads(stdout.getvalue())["outcome"],
                "ALREADY_SUCCEEDED",
            )

    def test_cli_exposes_no_network_key_order_or_time_overrides(self):
        forbidden = (
            "--url",
            "--host",
            "--proxy",
            "--api-key",
            "--secret",
            "--credential",
            "--order",
            "--symbol",
            "--fee-rate",
            "--created-at",
            "--clock",
        )
        for argument in forbidden:
            with self.subTest(argument=argument), redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(main([argument, "x"]), 2)


if __name__ == "__main__":
    unittest.main()
