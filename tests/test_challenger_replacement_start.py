import os
import stat
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from crypto_quant.canonical import canonical_json
from tests.test_challenger_replacement_install_trust import temporary_workspace
from tests.test_challenger_replacement_install import (
    install_inputs,
    launchctl_print_bytes,
)
from tests import test_challenger_replacement_live_runtime as live_fixture


ELIGIBLE = "2026-08-22T04:00:00.000Z"


def observation_sources(projection=None, stdout=b"", stderr=b""):
    root = mock.Mock()
    projected = projection or {
        "events": [], "slots": {}, "active_slot_id": None,
        "completed_slot_count": 0, "failed_slot_count": 0,
        "orphan_staging_count": 0, "orphan_staging_bytes": 0,
        "last_event_hash": "0" * 64,
    }
    state = mock.Mock()
    state.replay.return_value = projected
    return {
        "contract": {
            "service": {
                "identity": "gui/501/local.crypto-quant.challenger-replacement-v1"
            }
        },
        "install_receipt": {
            "first_eligible_scheduled_for": ELIGIBLE,
        },
        "event_root": root, "state": state, "projection": projected,
        "stdout": stdout,
        "stderr": stderr,
    }


def successful_projection(count=1, scheduled_for=ELIGIBLE):
    slots = {}
    for index in range(count):
        slot_id = "slot-{}".format(index + 1)
        slots[slot_id] = {
            "stage": "SLOT_SUCCEEDED",
            "source_bundle": {
                "slot": {
                    "slot_id": slot_id,
                    "scheduled_for": scheduled_for if index == 0 else
                    "2026-08-22T08:00:00.000Z",
                }
            },
            "source_bundle_sha256": "a" * 64,
            "decision_sha256": "b" * 64,
        }
    return {
        "events": [object()] * (3 * count), "slots": slots,
        "active_slot_id": None, "completed_slot_count": count,
        "failed_slot_count": 0, "orphan_staging_count": 0,
        "orphan_staging_bytes": 0,
        "last_event_hash": "c" * 64 if count else "0" * 64,
        "next_required_slot": {
            "sequence": count + 1,
            "scheduled_for": "2026-08-22T08:00:00.000Z",
        },
    }


def runtime_stdout(*, slot_id="slot-1", scheduled_for=ELIGIBLE, event_count=3):
    return canonical_json({
        "event_count": event_count,
        "next_required_slot": {
            "sequence": 2,
            "scheduled_for": "2026-08-22T08:00:00.000Z",
        },
        "reason_code": "CHALLENGER_REPLACEMENT_SLOT_SUCCEEDED_VERIFIED",
        "scheduled_for": scheduled_for,
        "slot_id": slot_id,
        "status": "CHALLENGER_REPLACEMENT_LIVE_RUNTIME_SUCCEEDED",
        "terminal_stage": "SLOT_SUCCEEDED",
    }).encode() + b"\n"


class ReplacementFirstSlotObserverTests(unittest.TestCase):
    def test_source_revalidation_rejects_receipt_or_snapshot_change(self):
        import crypto_quant.challenger_replacement_start as start

        inputs = install_inputs()
        receipt = {"first_eligible_scheduled_for": ELIGIBLE}
        sources = {
            "install_inputs": inputs,
            "install_receipt": receipt,
            "install_receipt_bytes": b"receipt",
            "plan": {"plan_hash": "a" * 64},
        }
        changed = {**inputs, "contract_bytes": inputs["contract_bytes"] + b"x"}
        with mock.patch.object(
            start, "_load_fixed_successful_install_receipt",
            return_value=(changed, receipt, b"receipt"),
        ), mock.patch.object(
            start, "_load_snapshot_plan_and_strategy",
            return_value=sources["plan"],
        ), self.assertRaisesRegex(
            start.ChallengerReplacementStartError,
            "FIRST_SLOT_SOURCE_CHANGED",
        ):
            start._revalidate_sources(sources)

        with mock.patch.object(
            start, "_load_fixed_successful_install_receipt",
            return_value=(inputs, receipt, b"receipt"),
        ), mock.patch.object(
            start, "_load_snapshot_plan_and_strategy",
            return_value={"plan_hash": "b" * 64},
        ), self.assertRaisesRegex(
            start.ChallengerReplacementStartError,
            "FIRST_SLOT_SOURCE_CHANGED",
        ):
            start._revalidate_sources(sources)

    def test_untrusted_loader_failure_returns_failed_closed_before_launch_or_network(self):
        import crypto_quant.challenger_replacement_start as start

        with mock.patch.object(
            start, "_load_fixed_observation_sources",
            side_effect=start.ChallengerReplacementStartError(
                "CHALLENGER_REPLACEMENT_FIRST_SLOT_PATH_UNTRUSTED"
            ),
        ), mock.patch.object(start, "_command") as command, mock.patch.object(
            start, "acquire_challenger_replacement_live_capture"
        ) as network, mock.patch.object(
            start, "_now",
            return_value=datetime(2026, 8, 22, 4, 10, tzinfo=timezone.utc),
        ):
            result = start.observe_fixed_replacement_first_slot()
        self.assertEqual(result["status"], "FAILED_CLOSED")
        self.assertEqual(result["reason_codes"], [
            "CHALLENGER_REPLACEMENT_FIRST_SLOT_PATH_UNTRUSTED"
        ])
        self.assertEqual(result["authority"]["launchctl_read_count"], 0)
        command.assert_not_called()
        network.assert_not_called()

    def test_launchctl_observation_requires_exact_run_and_zero_exit(self):
        import crypto_quant.challenger_replacement_start as start

        contract = install_inputs()["contract"]
        zero = (0, launchctl_print_bytes(contract), b"")
        one = (0, launchctl_print_bytes(contract).replace(
            b"\truns = 0", b"\truns = 1"
        ).replace(
            b"\tlast exit code = (never exited)", b"\tlast exit code = 0"
        ), b"")
        self.assertTrue(start._launchctl_observation_valid(contract, zero, 0))
        self.assertTrue(start._launchctl_observation_valid(contract, one, 1))
        self.assertFalse(start._launchctl_observation_valid(contract, one, 0))
        self.assertFalse(start._launchctl_observation_valid(
            contract, (0, one[1], b"bad"), 1
        ))

    def test_fixed_loader_retains_receipt_bound_event_logs_and_plist(self):
        import hashlib
        import crypto_quant.challenger_replacement_start as start

        fixture = live_fixture.LiveRuntimeTests()
        fixture.setUp()
        try:
            with temporary_workspace() as directory:
                base = Path(directory)
                log = base / "log"
                launch_agents = base / "LaunchAgents"
                log.mkdir(mode=0o700)
                launch_agents.mkdir(mode=0o700)
                stdout = log / "stdout.log"
                stderr = log / "stderr.log"
                target = launch_agents / "replacement.plist"
                stdout.write_bytes(b"")
                stderr.write_bytes(b"")
                target.write_bytes(b"plist")
                for path in (stdout, stderr, target):
                    path.chmod(0o600)
                inputs = install_inputs()
                identity = fixture.workspace.identity()
                inputs["contract"]["event_root"].update({
                    "path": identity.absolute_path, "device": identity.device,
                    "inode": identity.inode, "owner_uid": identity.uid,
                })
                inputs["contract"]["paths"].update({
                    "event_root": identity.absolute_path,
                    "stdout": str(stdout), "stderr": str(stderr),
                    "target_plist": str(target),
                })
                entry = target.stat()
                receipt = {
                    "first_eligible_scheduled_for": ELIGIBLE,
                    "plist": {
                        "path": str(target), "device": entry.st_dev,
                        "inode": entry.st_ino, "owner_uid": entry.st_uid,
                        "mode": stat.S_IMODE(entry.st_mode),
                        "link_count": entry.st_nlink,
                        "size_bytes": entry.st_size,
                        "sha256": hashlib.sha256(b"plist").hexdigest(),
                    },
                }
                with mock.patch.object(
                    start, "_load_fixed_successful_install_receipt",
                    return_value=(inputs, receipt, b"receipt"),
                ), mock.patch.object(
                    start, "_load_snapshot_plan_and_strategy",
                    return_value=fixture.plan,
                ):
                    sources = start._load_fixed_observation_sources()
                try:
                    self.assertEqual(sources["projection"]["events"], ())
                    self.assertEqual(sources["stdout"], b"")
                    self.assertEqual(sources["stderr"], b"")
                    self.assertEqual(len(sources["retained_paths"]), 3)
                finally:
                    for capability in sources["retained_paths"]:
                        capability.close()
                    sources["event_root"].close()
        finally:
            fixture.tearDown()

    def test_retained_file_rejects_same_bytes_new_inode_and_preserves_sentinel(self):
        import crypto_quant.challenger_replacement_start as start

        with temporary_workspace() as directory:
            parent = Path(directory)
            parent.chmod(0o700)
            target = parent / "stdout.log"
            target.write_bytes(b"exact\n")
            target.chmod(0o600)
            capability = start._open_retained_path(
                target, allow_absent=False, allow_empty=False
            )
            try:
                sentinel = parent / "sentinel"
                target.rename(sentinel)
                target.write_bytes(b"exact\n")
                target.chmod(0o600)
                before = sentinel.stat()
                with self.assertRaisesRegex(
                    start.ChallengerReplacementStartError,
                    "FIRST_SLOT_PATH_IDENTITY_CHANGED",
                ):
                    capability.validate()
                after = sentinel.stat()
                self.assertEqual(sentinel.read_bytes(), b"exact\n")
                self.assertEqual(
                    (stat.S_IMODE(after.st_mode), after.st_ino, after.st_nlink,
                     after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                    (stat.S_IMODE(before.st_mode), before.st_ino, before.st_nlink,
                     before.st_size, before.st_mtime_ns, before.st_ctime_ns),
                )
            finally:
                capability.close()

    def test_retained_file_rejects_fifo_without_blocking_or_modifying_it(self):
        import crypto_quant.challenger_replacement_start as start

        with temporary_workspace() as directory:
            parent = Path(directory)
            parent.chmod(0o700)
            fifo = parent / "stderr.log"
            os.mkfifo(fifo, 0o600)
            before = fifo.lstat()
            with self.assertRaisesRegex(
                start.ChallengerReplacementStartError,
                "FIRST_SLOT_PATH_UNTRUSTED",
            ):
                start._open_retained_path(
                    fifo, allow_absent=False, allow_empty=True
                )
            after = fifo.lstat()
            self.assertEqual(
                (stat.S_IMODE(after.st_mode), after.st_ino, after.st_nlink,
                 after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                (stat.S_IMODE(before.st_mode), before.st_ino, before.st_nlink,
                 before.st_size, before.st_mtime_ns, before.st_ctime_ns),
            )

    def _observe(self, sources, now, *, launch=(0, b"launch", b""), valid=True):
        import crypto_quant.challenger_replacement_start as start

        with mock.patch.object(
            start, "_load_fixed_observation_sources", return_value=sources
        ), mock.patch.object(
            start, "_now", return_value=now
        ), mock.patch.object(
            start, "_command", return_value=launch
        ) as command, mock.patch.object(
            start, "_launchctl_observation_valid", return_value=valid
        ), mock.patch.object(
            start, "acquire_challenger_replacement_live_capture"
        ) as network, mock.patch.object(
            sources["event_root"], "close", wraps=sources["event_root"].close
        ) as close:
            result = start.observe_fixed_replacement_first_slot()
        network.assert_not_called()
        command.assert_called_once_with((
            "/bin/launchctl", "print",
            "gui/501/local.crypto-quant.challenger-replacement-v1",
        ))
        close.assert_called_once()
        self.assertEqual(result["authority"], {
            "launchctl_read_count": 1, "market_request_count": 0,
            "runtime_invocation_count": 0, "state_write_count": 0,
            "credential_count": 0, "broker_request_count": 0,
            "order_count": 0,
        })
        return result

    def test_waiting_states_are_derived_only_from_first_eligible_time(self):
        before = self._observe(
            observation_sources(),
            datetime(2026, 8, 22, 3, 59, tzinfo=timezone.utc),
        )
        self.assertEqual(before["status"], "WAITING_BEFORE_FIRST_ELIGIBLE_SLOT")
        waiting = self._observe(
            observation_sources(),
            datetime(2026, 8, 22, 4, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(waiting["status"], "WAITING_FOR_FIRST_NATURAL_SLOT")

    def test_one_exact_first_success_is_verified_without_economic_output(self):
        sources = observation_sources(
            successful_projection(),
            stdout=runtime_stdout(),
        )
        result = self._observe(
            sources, datetime(2026, 8, 22, 4, 10, tzinfo=timezone.utc)
        )
        self.assertEqual(result["status"], "FIRST_NATURAL_SLOT_VERIFIED")
        self.assertEqual(result["first_scheduled_for"], ELIGIBLE)
        self.assertEqual(result["terminal_event_hash"], "c" * 64)
        self.assertEqual(result["source_bundle_sha256"], "a" * 64)
        self.assertEqual(result["decision_sha256"], "b" * 64)
        forbidden = {"pnl", "return", "win_rate", "profit", "gate"}
        self.assertFalse(forbidden.intersection(result))

    def test_observer_replays_event_chain_again_before_return(self):
        sources = observation_sources(
            successful_projection(), stdout=runtime_stdout()
        )
        changed = {**sources["projection"], "last_event_hash": "d" * 64}
        sources["state"].replay.return_value = changed
        result = self._observe(
            sources, datetime(2026, 8, 22, 4, 10, tzinfo=timezone.utc)
        )
        self.assertEqual(result["status"], "FAILED_CLOSED")
        self.assertIn(
            "CHALLENGER_REPLACEMENT_FIRST_SLOT_SOURCE_CHANGED",
            result["reason_codes"],
        )

    def test_observer_attempts_every_close_and_reports_fixed_close_failure(self):
        import crypto_quant.challenger_replacement_start as start

        sources = observation_sources(
            successful_projection(), stdout=runtime_stdout()
        )
        first = mock.Mock()
        second = mock.Mock()
        first.close.side_effect = OSError("first close")
        second.close.side_effect = OSError("second close")
        sources["retained_paths"] = (first, second)
        sources["event_root"].close.side_effect = OSError("root close")
        with mock.patch.object(
            start, "_load_fixed_observation_sources", return_value=sources
        ), mock.patch.object(
            start, "_now",
            return_value=datetime(2026, 8, 22, 4, 10,
                                  tzinfo=timezone.utc),
        ), mock.patch.object(
            start, "_command", return_value=(0, b"launch", b"")
        ), mock.patch.object(
            start, "_launchctl_observation_valid", return_value=True
        ):
            result = start.observe_fixed_replacement_first_slot()

        self.assertEqual(result["status"], "FAILED_CLOSED")
        self.assertEqual(
            result["reason_codes"],
            ["CHALLENGER_REPLACEMENT_FIRST_SLOT_CLOSE_FAILED"],
        )
        first.close.assert_called_once()
        second.close.assert_called_once()
        sources["event_root"].close.assert_called_once()

    def test_close_failures_never_override_unexpected_primary_error(self):
        import crypto_quant.challenger_replacement_start as start

        sources = observation_sources()
        retained = mock.Mock()
        retained.close.side_effect = OSError("retained close")
        sources["retained_paths"] = (retained,)
        sources["event_root"].close.side_effect = OSError("root close")
        primary = KeyboardInterrupt("primary")
        with mock.patch.object(
            start, "_load_fixed_observation_sources", return_value=sources
        ), mock.patch.object(
            start, "_now",
            return_value=datetime(2026, 8, 22, 4, 10,
                                  tzinfo=timezone.utc),
        ), mock.patch.object(
            start, "_command", side_effect=primary
        ):
            with self.assertRaises(KeyboardInterrupt) as raised:
                start.observe_fixed_replacement_first_slot()

        self.assertIs(raised.exception, primary)
        self.assertEqual(len(primary.close_failures), 2)
        retained.close.assert_called_once()
        sources["event_root"].close.assert_called_once()

    def test_success_stdout_must_bind_exact_first_slot_and_event_count(self):
        for stdout in (
            runtime_stdout(slot_id="other"),
            runtime_stdout(scheduled_for="2026-08-22T08:00:00.000Z"),
            runtime_stdout(event_count=6),
        ):
            with self.subTest(stdout=stdout):
                result = self._observe(
                    observation_sources(successful_projection(), stdout=stdout),
                    datetime(2026, 8, 22, 4, 10, tzinfo=timezone.utc),
                )
                self.assertEqual(result["status"], "FAILED_CLOSED")


    def _inputs(self):
        inputs = install_inputs()
        install_receipt = {
            "receipt_id": "challenger_replacement_install_receipt_" + "a" * 64,
            "receipt_hash": "b" * 64,
            "first_eligible_scheduled_for": ELIGIBLE,
        }
        observer = {
            "status": "FIRST_NATURAL_SLOT_VERIFIED",
            "observed_at": "2026-08-22T04:10:00.000Z",
            "first_eligible_scheduled_for": ELIGIBLE,
            "first_scheduled_for": ELIGIBLE,
            "event_count": 3,
            "completed_slot_count": 1,
            "terminal_event_hash": "c" * 64,
            "source_bundle_sha256": "a" * 64,
            "decision_sha256": "b" * 64,
            "reason_codes": [],
            "authority": {
                "launchctl_read_count": 1, "market_request_count": 0,
                "runtime_invocation_count": 0, "state_write_count": 0,
                "credential_count": 0, "broker_request_count": 0,
                "order_count": 0,
            },
        }
        return inputs, install_receipt, observer

    def test_builder_derives_exact_540_slot_90_day_boundary_and_bindings(self):
        import crypto_quant.challenger_replacement_start as start

        inputs, install_receipt, observer = self._inputs()
        receipt = start._build_replacement_start_receipt(
            observer=observer, contract=inputs["contract"],
            contract_bytes=inputs["contract_bytes"],
            install_receipt=install_receipt,
            install_receipt_bytes=b"install-receipt",
            published_at=datetime(2026, 8, 22, 4, 11, tzinfo=timezone.utc),
        )
        self.assertEqual(receipt["first_scheduled_for"], ELIGIBLE)
        self.assertEqual(receipt["required_slot_count"], 540)
        self.assertEqual(
            receipt["last_required_scheduled_for"],
            "2026-11-20T00:00:00.000Z",
        )
        self.assertEqual(receipt["tail_end"], "2026-11-20T04:00:00.000Z")
        self.assertEqual(
            receipt["evaluation_not_before"], "2026-11-20T04:05:00.000Z"
        )
        self.assertEqual(receipt["event_root_binding"],
                         inputs["contract"]["event_root"])
        self.assertEqual(receipt["strategy_core_binding"],
                         inputs["contract"]["strategy_core"])
        self.assertEqual(receipt["cohort_status"], "STARTED_COLLECTION_ONLY")
        self.assertEqual(receipt["observer_binding"]["terminal_event_hash"],
                         "c" * 64)
        self.assertEqual(receipt["observer_binding"]["source_bundle_sha256"],
                         "a" * 64)
        self.assertEqual(receipt["observer_binding"]["decision_sha256"],
                         "b" * 64)

        body = canonical_json(receipt).encode()
        self.assertEqual(
            start.load_replacement_start_receipt_bytes(
                body, install_receipt=install_receipt,
                install_receipt_bytes=b"install-receipt",
                contract=inputs["contract"],
                contract_bytes=inputs["contract_bytes"], observer=observer,
            ), receipt,
        )
        altered = dict(receipt)
        altered["tail_end"] = "2026-11-19T00:00:00.000Z"
        with self.assertRaises(start.ChallengerReplacementStartError):
            start.load_replacement_start_receipt_bytes(
                canonical_json(altered).encode(),
                install_receipt=install_receipt,
                install_receipt_bytes=b"install-receipt",
                contract=inputs["contract"],
                contract_bytes=inputs["contract_bytes"], observer=observer,
            )

    def test_nonverified_observation_scans_once_but_never_publishes_receipt(self):
        import crypto_quant.challenger_replacement_start as start

        inputs, install_receipt, waiting = self._inputs()
        waiting = {**waiting, "status": "WAITING_FOR_FIRST_NATURAL_SLOT"}
        with temporary_workspace() as directory:
            root = Path(directory) / "start-receipts"
            root.mkdir(mode=0o700)
            inputs["contract"]["paths"]["start_receipt_root"] = str(root)
            with mock.patch.object(
                start, "observe_fixed_replacement_first_slot",
                return_value=waiting,
            ), mock.patch.object(
                start, "_load_fixed_successful_install_receipt",
                return_value=(inputs, install_receipt, b"install-receipt"),
            ) as load, mock.patch.object(
                start, "_publish_contract_exact"
            ) as publish:
                result = start.publish_fixed_replacement_start_receipt()
        self.assertEqual(result["publication_outcome"], "NOT_PUBLISHED")
        load.assert_called_once()
        publish.assert_not_called()

    def test_verified_observation_with_changed_install_source_fails_closed(self):
        import crypto_quant.challenger_replacement_start as start
        from crypto_quant.challenger_replacement_install import (
            ReplacementInstallError,
        )

        observer = self._inputs()[2]
        with mock.patch.object(
            start, "observe_fixed_replacement_first_slot", return_value=observer
        ), mock.patch.object(
            start, "_load_fixed_successful_install_receipt",
            side_effect=ReplacementInstallError(
                "CHALLENGER_REPLACEMENT_INSTALL_RECEIPT_REQUIRED"
            ),
        ), self.assertRaisesRegex(
            start.ChallengerReplacementStartError,
            "START_RECEIPT_SOURCE_INVALID",
        ):
            start.publish_fixed_replacement_start_receipt()

    def test_publication_retains_and_revalidates_first_slot_sources(self):
        import crypto_quant.challenger_replacement_start as start

        inputs, install_receipt, observer = self._inputs()
        sources = observation_sources(
            successful_projection(), stdout=runtime_stdout()
        )
        changed = {**sources["projection"], "last_event_hash": "d" * 64}
        with temporary_workspace() as directory:
            root = Path(directory) / "start-receipts"
            root.mkdir(mode=0o700)
            inputs["contract"]["paths"]["start_receipt_root"] = str(root)

            def publish_then_change(*_args, **_kwargs):
                sources["state"].replay.return_value = changed
                return "PUBLISHED", mock.Mock()

            with mock.patch.object(
                start, "observe_fixed_replacement_first_slot",
                return_value=observer,
            ), mock.patch.object(
                start, "_load_fixed_successful_install_receipt",
                return_value=(inputs, install_receipt, b"install-receipt"),
            ), mock.patch.object(
                start, "_load_fixed_observation_sources",
                return_value=sources,
            ) as retain, mock.patch.object(
                start, "_publish_contract_exact",
                side_effect=publish_then_change,
            ), mock.patch.object(
                start, "_now",
                return_value=datetime(
                    2026, 8, 22, 4, 11, tzinfo=timezone.utc
                ),
            ), self.assertRaisesRegex(
                start.ChallengerReplacementStartError,
                "FIRST_SLOT_SOURCE_CHANGED",
            ):
                start.publish_fixed_replacement_start_receipt()
        retain.assert_called_once()
        sources["event_root"].close.assert_called_once()

    def test_publication_rejects_stderr_appearing_after_observation(self):
        import crypto_quant.challenger_replacement_start as start

        observer = self._inputs()[2]
        sources = observation_sources(
            successful_projection(), stdout=runtime_stdout(), stderr=b"late"
        )
        with mock.patch.object(
            start, "_load_fixed_observation_sources", return_value=sources
        ), self.assertRaisesRegex(
            start.ChallengerReplacementStartError,
            "FIRST_SLOT_SOURCE_CHANGED",
        ):
            start._retain_verified_observer_sources(observer)
        sources["event_root"].close.assert_called_once()

    def test_existing_receipt_revalidates_current_first_slot_sources(self):
        import crypto_quant.challenger_replacement_start as start

        inputs, install_receipt, observer = self._inputs()
        sources = observation_sources(
            successful_projection(), stdout=runtime_stdout()
        )
        with temporary_workspace() as directory:
            root = Path(directory) / "start-receipts"
            root.mkdir(mode=0o700)
            inputs["contract"]["paths"]["start_receipt_root"] = str(root)
            fixed = (inputs, install_receipt, b"install-receipt")
            with mock.patch.object(
                start, "observe_fixed_replacement_first_slot",
                return_value=observer,
            ), mock.patch.object(
                start, "_load_fixed_successful_install_receipt",
                return_value=fixed,
            ), mock.patch.object(
                start, "_load_fixed_observation_sources",
                return_value=sources,
            ), mock.patch.object(
                start, "_now",
                return_value=datetime(
                    2026, 8, 22, 4, 11, tzinfo=timezone.utc
                ),
            ):
                start.publish_fixed_replacement_start_receipt()

            mismatched = observation_sources(
                {**successful_projection(), "last_event_hash": "d" * 64},
                stdout=runtime_stdout(),
            )
            with mock.patch.object(
                start, "observe_fixed_replacement_first_slot",
                side_effect=AssertionError("must not re-observe"),
            ), mock.patch.object(
                start, "_load_fixed_successful_install_receipt",
                return_value=fixed,
            ), mock.patch.object(
                start, "_load_fixed_observation_sources",
                return_value=mismatched,
            ), self.assertRaisesRegex(
                start.ChallengerReplacementStartError,
                "FIRST_SLOT_SOURCE_CHANGED",
            ):
                start.publish_fixed_replacement_start_receipt()
        mismatched["event_root"].close.assert_called_once()

    def test_start_receipt_publication_is_exact_idempotent_and_conflict_closed(self):
        import json
        import crypto_quant.challenger_replacement_start as start

        inputs, install_receipt, observer = self._inputs()
        retained = observation_sources(
            successful_projection(), stdout=runtime_stdout()
        )
        with temporary_workspace() as directory:
            root = Path(directory) / "start-receipts"
            root.mkdir(mode=0o700)
            inputs["contract"]["paths"]["start_receipt_root"] = str(root)
            with mock.patch.object(
                start, "observe_fixed_replacement_first_slot",
                return_value=observer,
            ), mock.patch.object(
                start, "_load_fixed_successful_install_receipt",
                return_value=(inputs, install_receipt, b"install-receipt"),
            ), mock.patch.object(
                start, "_load_fixed_observation_sources",
                return_value=retained,
            ), mock.patch.object(
                start, "_now",
                return_value=datetime(
                    2026, 8, 22, 4, 11, tzinfo=timezone.utc
                ),
            ):
                first = start.publish_fixed_replacement_start_receipt()
                second = start.publish_fixed_replacement_start_receipt()
                self.assertEqual(first["publication_outcome"], "PUBLISHED")
                self.assertEqual(second["publication_outcome"], "ALREADY_PUBLISHED")
                self.assertEqual(first["receipt"], second["receipt"])
                path = Path(first["receipt_path"])
                self.assertEqual(json.loads(path.read_bytes()), first["receipt"])
                path.write_bytes(b"{}")
                path.chmod(0o600)
                with self.assertRaisesRegex(
                    start.ChallengerReplacementStartError,
                    "START_RECEIPT_PUBLICATION_FAILED",
                ):
                    start.publish_fixed_replacement_start_receipt()

    def test_existing_start_receipt_replays_before_new_observation_or_time(self):
        import crypto_quant.challenger_replacement_start as start

        inputs, install_receipt, observer = self._inputs()
        retained = observation_sources(
            successful_projection(), stdout=runtime_stdout()
        )
        with temporary_workspace() as directory:
            root = Path(directory) / "start-receipts"
            root.mkdir(mode=0o700)
            inputs["contract"]["paths"]["start_receipt_root"] = str(root)
            sources = (inputs, install_receipt, b"install-receipt")
            with mock.patch.object(
                start, "observe_fixed_replacement_first_slot",
                return_value=observer,
            ), mock.patch.object(
                start, "_load_fixed_successful_install_receipt",
                return_value=sources,
            ), mock.patch.object(
                start, "_load_fixed_observation_sources",
                return_value=retained,
            ), mock.patch.object(
                start, "_now",
                return_value=datetime(2026, 8, 22, 4, 11,
                                      tzinfo=timezone.utc),
            ):
                first = start.publish_fixed_replacement_start_receipt()

            with mock.patch.object(
                start, "observe_fixed_replacement_first_slot",
                side_effect=AssertionError("must not re-observe"),
            ), mock.patch.object(
                start, "_load_fixed_successful_install_receipt",
                return_value=sources,
            ), mock.patch.object(
                start, "_load_fixed_observation_sources",
                return_value=retained,
            ), mock.patch.object(
                start, "_now",
                return_value=datetime(2026, 8, 22, 4, 12,
                                      tzinfo=timezone.utc),
            ):
                second = start.publish_fixed_replacement_start_receipt()

            self.assertEqual(second["publication_outcome"], "ALREADY_PUBLISHED")
            self.assertEqual(second["receipt"], first["receipt"])
            self.assertEqual(second["receipt_path"], first["receipt_path"])

    def test_existing_start_receipt_requires_directory_durability_confirmation(self):
        import crypto_quant.challenger_replacement_start as start

        inputs, install_receipt, observer = self._inputs()
        with temporary_workspace() as directory:
            root = Path(directory) / "start-receipts"
            root.mkdir(mode=0o700)
            inputs["contract"]["paths"]["start_receipt_root"] = str(root)
            receipt = start._build_replacement_start_receipt(
                observer=observer, contract=inputs["contract"],
                contract_bytes=inputs["contract_bytes"],
                install_receipt=install_receipt,
                install_receipt_bytes=b"install-receipt",
                published_at=datetime(
                    2026, 8, 22, 4, 11, tzinfo=timezone.utc
                ),
            )
            start._publish_contract_exact(
                root, receipt["receipt_id"] + ".json",
                canonical_json(receipt).encode(),
            )
            with mock.patch.object(
                start, "_fsync_retry", create=True
            ) as confirm:
                loaded = start._load_existing_start_receipt(
                    inputs, install_receipt, b"install-receipt"
                )
            self.assertEqual(loaded[0], receipt)
            confirm.assert_called_once()

            with mock.patch.object(
                start, "_fsync_retry", create=True,
                side_effect=OSError("directory fsync failed"),
            ), self.assertRaisesRegex(
                start.ChallengerReplacementStartError,
                "START_RECEIPT_PUBLICATION_FAILED",
            ):
                start._load_existing_start_receipt(
                    inputs, install_receipt, b"install-receipt"
                )

    def test_start_receipt_schema_mirror_is_strict_and_valid(self):
        import json
        from jsonschema import Draft202012Validator
        from tests.test_challenger_replacement_install_trust import ROOT

        name = "challenger-replacement-start-receipt-v1.schema.json"
        config = ROOT / "config" / name
        package = ROOT / "src/crypto_quant/schemas" / name
        self.assertEqual(config.read_bytes(), package.read_bytes())
        schema = json.loads(config.read_text())
        self.assertFalse(schema["additionalProperties"])
        Draft202012Validator.check_schema(schema)

    def test_cli_rejects_arguments_before_observe_or_publish(self):
        import crypto_quant.challenger_replacement_start_cli as cli

        with mock.patch.object(
            cli, "publish_fixed_replacement_start_receipt"
        ) as publish:
            self.assertEqual(cli.main(["--date", ELIGIBLE]), 2)
        publish.assert_not_called()

    def test_second_slot_or_elapsed_second_boundary_is_missed(self):
        two = self._observe(
            observation_sources(successful_projection(2), stdout=b"ok\n"),
            datetime(2026, 8, 22, 8, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(two["status"], "FIRST_SLOT_OBSERVATION_WINDOW_MISSED")
        late = self._observe(
            observation_sources(),
            datetime(2026, 8, 22, 8, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(late["status"], "FIRST_SLOT_OBSERVATION_WINDOW_MISSED")

    def test_partial_failed_wrong_slot_or_bad_process_evidence_fails_closed(self):
        partial = observation_sources({
            **successful_projection(0), "events": [object()],
            "active_slot_id": "slot-1",
        })
        failed = observation_sources({
            **successful_projection(0), "events": [object()],
            "failed_slot_count": 1,
        })
        wrong = observation_sources(
            successful_projection(scheduled_for="2026-08-22T08:00:00.000Z"),
            stdout=b"ok\n",
        )
        for sources in (partial, failed, wrong):
            with self.subTest(sources=sources):
                result = self._observe(
                    sources, datetime(2026, 8, 22, 4, 10, tzinfo=timezone.utc)
                )
                self.assertEqual(result["status"], "FAILED_CLOSED")
        for sources, launch, valid in (
            (observation_sources(successful_projection(), stderr=b"bad"),
             (0, b"launch", b""), True),
            (observation_sources(successful_projection(), stdout=b"ok\n"),
             (1, b"", b"bad"), False),
        ):
            result = self._observe(
                sources, datetime(2026, 8, 22, 4, 10, tzinfo=timezone.utc),
                launch=launch, valid=valid,
            )
            self.assertEqual(result["status"], "FAILED_CLOSED")


if __name__ == "__main__":
    unittest.main()
