import base64
import errno
import hashlib
import json
import multiprocessing
import os
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import crypto_quant.challenger_replacement_events as events_module
from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_events import (
    ChallengerReplacementEventError,
    ChallengerReplacementEventRootIdentity,
    open_challenger_replacement_event_root,
)


_ZERO_HASH = "0" * 64
_PLAN_HASH = "1" * 64
_BUILD_HASH = "2" * 64


def _concurrent_publish_worker(identity_values, payload, barrier, queue):
    identity = ChallengerReplacementEventRootIdentity(*identity_values)
    root = open_challenger_replacement_event_root(identity)
    real_rename = events_module._rename_noreplace

    def synchronized_rename(directory_descriptor, source_name, destination_name):
        barrier.wait(timeout=10)
        try:
            real_rename(directory_descriptor, source_name, destination_name)
        except OSError as error:
            queue.put(("rename", "EEXIST" if error.errno == errno.EEXIST else error.errno))
            raise
        queue.put(("rename", "OK"))

    try:
        event = fixture_event(root, payload=payload)
        with patch.object(events_module, "_rename_noreplace", synchronized_rename):
            try:
                outcome = events_module.publish_challenger_replacement_event(
                    root, event
                ).outcome
            except ChallengerReplacementEventError as error:
                outcome = error.reason_code
        queue.put(("outcome", outcome))
    finally:
        root.close()


def sentinel_snapshot(path):
    entry = path.lstat()
    return {
        "bytes": path.read_bytes(),
        "mode": entry.st_mode,
        "size": entry.st_size,
        "mtime_ns": entry.st_mtime_ns,
        "ctime_ns": entry.st_ctime_ns,
        "device": entry.st_dev,
        "inode": entry.st_ino,
        "nlink": entry.st_nlink,
    }


class EventWorkspace:
    def __init__(self):
        self.temporary_parent = (
            "/private/tmp"
            if sys.platform == "darwin" and Path("/private/tmp").is_dir()
            else tempfile.gettempdir()
        )
        self.temporary = tempfile.TemporaryDirectory(dir=self.temporary_parent)
        self.base = Path(self.temporary.name)
        self.event_root = self.base / "events"
        self.event_root.mkdir(mode=0o700)

    def identity(self):
        entry = self.event_root.lstat()
        return ChallengerReplacementEventRootIdentity(
            absolute_path=str(self.event_root),
            device=entry.st_dev,
            inode=entry.st_ino,
            uid=entry.st_uid,
            mode_octal="0700",
        )

    def close(self):
        self.temporary.cleanup()


def fixture_event(
    root, *, sequence=1, payload=b"fixture-payload", previous_event_hash=_ZERO_HASH
):
    return events_module.build_challenger_replacement_event(
        sequence=sequence,
        event_type="INPUT_PREPARED",
        slot_id="slot-fixture",
        worker_id="worker-fixture",
        recorded_at="2026-08-09T08:05:00.000Z",
        previous_event_hash=previous_event_hash,
        payload_bytes=payload,
        plan_hash=_PLAN_HASH,
        build_identity_hash=_BUILD_HASH,
        event_root=root,
    )


class PublicEventSafetyContractTests(unittest.TestCase):
    def setUp(self):
        self.workspace = EventWorkspace()

    def tearDown(self):
        self.workspace.close()

    def test_recorded_at_requires_exact_canonical_utc_milliseconds(self):
        root = open_challenger_replacement_event_root(self.workspace.identity())
        try:
            for invalid in (
                "not-a-time", "2026-08-09T08:05:00Z",
                "2026-08-09T08:05:00.000+00:00",
                "2026-08-09T08:05:00.000001Z",
            ):
                with self.subTest(invalid=invalid), self.assertRaisesRegex(
                    ChallengerReplacementEventError,
                    "CHALLENGER_REPLACEMENT_EVENT_BYTES_INVALID",
                ):
                    events_module.build_challenger_replacement_event(
                        sequence=1, event_type="INPUT_PREPARED", slot_id="slot",
                        worker_id="worker", recorded_at=invalid,
                        previous_event_hash=_ZERO_HASH, payload_bytes=b"payload",
                        plan_hash=_PLAN_HASH, build_identity_hash=_BUILD_HASH,
                        event_root=root)
            valid = fixture_event(root)
            core = json.loads(valid.final_bytes)
            core.pop("event_hash")
            core["recorded_at"] = "not-a-time"
            forged = events_module._event_from_core(core)
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_BYTES_INVALID",
            ):
                events_module.load_challenger_replacement_event_bytes(
                    forged.final_bytes)
        finally:
            root.close()

    def test_replaced_event_root_never_receives_a_write(self):
        identity = self.workspace.identity()
        displaced = self.workspace.base / "retained-events"
        real_open = events_module.os.open

        def replace_before_open(path, flags, *args, **kwargs):
            if Path(path) == self.workspace.event_root:
                self.workspace.event_root.rename(displaced)
                self.workspace.event_root.mkdir(mode=0o700)
            return real_open(path, flags, *args, **kwargs)

        with patch.object(events_module.os, "open", side_effect=replace_before_open):
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_ROOT_CHANGED",
            ):
                open_challenger_replacement_event_root(identity)

        self.assertEqual(list(self.workspace.event_root.iterdir()), [])
        self.assertEqual(list(displaced.iterdir()), [])

    def test_existing_final_symlink_never_changes_sentinel(self):
        with open_challenger_replacement_event_root(
            self.workspace.identity()
        ) as root:
            event = fixture_event(root)
            sentinel = self.workspace.base / "sentinel.txt"
            sentinel.write_bytes(b"must-not-change")
            sentinel.chmod(0o600)
            final = self.workspace.event_root / "00000000000000000001.event.json"
            final.symlink_to(sentinel)
            before = sentinel_snapshot(sentinel)

            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED",
            ):
                events_module.publish_challenger_replacement_event(root, event)

            self.assertEqual(sentinel_snapshot(sentinel), before)

    def test_existing_final_hardlink_never_changes_sentinel(self):
        with open_challenger_replacement_event_root(
            self.workspace.identity()
        ) as root:
            event = fixture_event(root)
            sentinel = self.workspace.base / "sentinel.txt"
            sentinel.write_bytes(b"must-not-change")
            sentinel.chmod(0o600)
            final = self.workspace.event_root / "00000000000000000001.event.json"
            os.link(sentinel, final)
            before = sentinel_snapshot(sentinel)

            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED",
            ):
                events_module.publish_challenger_replacement_event(root, event)

            self.assertEqual(sentinel_snapshot(sentinel), before)

    def test_existing_staging_symlink_never_changes_sentinel(self):
        with open_challenger_replacement_event_root(
            self.workspace.identity()
        ) as root:
            event = fixture_event(root)
            sentinel = self.workspace.base / "sentinel.txt"
            sentinel.write_bytes(b"must-not-change")
            sentinel.chmod(0o600)
            staging = self.workspace.event_root / (
                f".stage-{event.sequence:020d}-{event.event_hash}-{'a' * 32}.tmp"
            )
            staging.symlink_to(sentinel)
            before = sentinel_snapshot(sentinel)

            with patch.object(events_module.secrets, "token_hex", return_value="a" * 32):
                with self.assertRaises(ChallengerReplacementEventError):
                    events_module.publish_challenger_replacement_event(root, event)

            self.assertEqual(sentinel_snapshot(sentinel), before)

    def test_replaced_staging_entry_never_changes_sentinel(self):
        with open_challenger_replacement_event_root(
            self.workspace.identity()
        ) as root:
            event = fixture_event(root)
            sentinel = self.workspace.base / "sentinel.txt"
            sentinel.write_bytes(b"must-not-change")
            sentinel.chmod(0o600)
            staging = self.workspace.event_root / (
                f".stage-{event.sequence:020d}-{event.event_hash}-{'b' * 32}.tmp"
            )
            before = sentinel_snapshot(sentinel)
            real_write = events_module.os.write
            replaced = False

            def replace_before_write(fd, data):
                nonlocal replaced
                if not replaced:
                    staging.unlink()
                    staging.symlink_to(sentinel)
                    replaced = True
                return real_write(fd, data)

            with patch.object(events_module.secrets, "token_hex", return_value="b" * 32), \
                 patch.object(events_module.os, "write", side_effect=replace_before_write):
                with self.assertRaises(ChallengerReplacementEventError):
                    events_module.publish_challenger_replacement_event(root, event)

            self.assertEqual(sentinel_snapshot(sentinel), before)


class EventRootTests(unittest.TestCase):
    def setUp(self):
        self.workspace = EventWorkspace()

    def tearDown(self):
        self.workspace.close()

    def test_opens_exact_owner_only_directory_and_closes_once(self):
        closed = []
        real_close = events_module.os.close

        def recording_close(fd):
            closed.append(fd)
            return real_close(fd)

        with patch.object(events_module.os, "close", side_effect=recording_close):
            root = open_challenger_replacement_event_root(self.workspace.identity())
            descriptor = root.descriptor
            root.validate()
            root.close()
            root.close()

        self.assertEqual(closed, [descriptor])
        with self.assertRaises(OSError):
            os.fstat(descriptor)

    def test_context_manager_closes_descriptor(self):
        with open_challenger_replacement_event_root(
            self.workspace.identity()
        ) as root:
            descriptor = root.descriptor
            self.assertEqual(os.fstat(descriptor).st_ino, root.inode)
        with self.assertRaises(OSError):
            os.fstat(descriptor)

    def test_workspace_uses_portable_owner_only_child(self):
        expected_parent = (
            "/private/tmp"
            if sys.platform == "darwin" and Path("/private/tmp").is_dir()
            else tempfile.gettempdir()
        )
        self.assertEqual(self.workspace.temporary_parent, expected_parent)
        self.assertEqual(stat.S_IMODE(self.workspace.event_root.lstat().st_mode), 0o700)

    def test_missing_required_open_flags_fails_before_open(self):
        for flag_name in ("O_NOFOLLOW", "O_DIRECTORY"):
            with self.subTest(flag_name=flag_name), \
                 patch.object(events_module.os, flag_name, 0), \
                 patch.object(events_module.os, "open") as mocked_open:
                with self.assertRaisesRegex(
                    ChallengerReplacementEventError,
                    "CHALLENGER_REPLACEMENT_EVENT_PLATFORM_UNSUPPORTED",
                ):
                    open_challenger_replacement_event_root(self.workspace.identity())
                mocked_open.assert_not_called()

    def test_rejects_relative_path_before_open(self):
        identity = replace(self.workspace.identity(), absolute_path="events")
        with self.assertRaisesRegex(
            ChallengerReplacementEventError,
            "CHALLENGER_REPLACEMENT_EVENT_ROOT_INVALID",
        ):
            open_challenger_replacement_event_root(identity)

    def test_rejects_wrong_identity_and_closes_every_opened_fd_once(self):
        identity = replace(
            self.workspace.identity(),
            inode=self.workspace.identity().inode + 1,
        )
        opened = []
        closed = []
        real_open = events_module.os.open
        real_close = events_module.os.close

        def recording_open(*args, **kwargs):
            descriptor = real_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor

        def recording_close(descriptor):
            closed.append(descriptor)
            return real_close(descriptor)

        with patch.object(events_module.os, "open", side_effect=recording_open), \
             patch.object(events_module.os, "close", side_effect=recording_close):
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_ROOT_INVALID",
            ):
                open_challenger_replacement_event_root(identity)

        self.assertEqual(opened, closed)
        self.assertTrue(all(closed.count(fd) == 1 for fd in opened))

    def test_post_open_validation_failure_closes_transferred_descriptor_once(self):
        opened = []
        closed = []
        real_open = events_module.os.open
        real_close = events_module.os.close

        def recording_open(*args, **kwargs):
            descriptor = real_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor

        def recording_close(descriptor):
            closed.append(descriptor)
            return real_close(descriptor)

        with patch.object(events_module.os, "open", side_effect=recording_open), \
             patch.object(events_module.os, "close", side_effect=recording_close), \
             patch.object(
                 events_module.ChallengerReplacementEventRoot,
                 "validate",
                 side_effect=ChallengerReplacementEventError(
                     "CHALLENGER_REPLACEMENT_EVENT_ROOT_CHANGED"
                 ),
             ):
            with self.assertRaises(ChallengerReplacementEventError):
                open_challenger_replacement_event_root(self.workspace.identity())

        self.assertEqual(opened, closed)
        self.assertEqual(len(opened), 1)

    def test_rejects_symlink_root(self):
        target = self.workspace.event_root
        link = self.workspace.base / "events-link"
        link.symlink_to(target, target_is_directory=True)
        entry = target.lstat()
        identity = ChallengerReplacementEventRootIdentity(
            absolute_path=str(link),
            device=entry.st_dev,
            inode=entry.st_ino,
            uid=entry.st_uid,
            mode_octal="0700",
        )
        with self.assertRaisesRegex(
            ChallengerReplacementEventError,
            "CHALLENGER_REPLACEMENT_EVENT_ROOT_INVALID",
        ):
            open_challenger_replacement_event_root(identity)


class CanonicalEventTests(unittest.TestCase):
    def setUp(self):
        self.workspace = EventWorkspace()
        self.root = open_challenger_replacement_event_root(self.workspace.identity())

    def tearDown(self):
        self.root.close()
        self.workspace.close()

    def test_builds_exact_versioned_fields_and_hand_derived_hash(self):
        payload = b"fixture-payload"
        event = fixture_event(self.root, payload=payload)
        core = {
            "schema_version": "challenger_replacement_event_v1",
            "sequence": 1,
            "event_type": "INPUT_PREPARED",
            "slot_id": "slot-fixture",
            "worker_id": "worker-fixture",
            "recorded_at": "2026-08-09T08:05:00.000Z",
            "previous_event_hash": _ZERO_HASH,
            "payload_encoding": "base64_rfc4648",
            "payload_bytes_base64": base64.b64encode(payload).decode("ascii"),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "plan_hash": _PLAN_HASH,
            "build_identity_hash": _BUILD_HASH,
            "event_root_device": self.root.device,
            "event_root_inode": self.root.inode,
        }
        expected_hash = hashlib.sha256(
            b"CHALLENGER_REPLACEMENT_EVENT_V1\x00"
            + canonical_json(core).encode("utf-8")
        ).hexdigest()
        expected = {**core, "event_hash": expected_hash}

        self.assertEqual(event.event_hash, expected_hash)
        self.assertEqual(event.final_bytes, canonical_json(expected).encode("utf-8"))
        self.assertEqual(set(json.loads(event.final_bytes)), set(expected))
        self.assertNotIn("lease_expires_at_or_null", expected)
        self.assertFalse(event.final_bytes.endswith(b"\n"))

    def test_build_is_deterministic_and_loader_rebuilds_exact_bytes(self):
        built = [fixture_event(self.root) for _ in range(100)]
        self.assertTrue(all(item == built[0] for item in built))
        self.assertEqual(
            events_module.load_challenger_replacement_event_bytes(
                built[0].final_bytes
            ),
            built[0],
        )

    def test_loader_rejects_duplicate_unknown_float_and_invalid_base64(self):
        event = fixture_event(self.root)
        parsed = json.loads(event.final_bytes)
        cases = []
        duplicate = event.final_bytes[:-1] + b',"sequence":1}'
        cases.append(duplicate)
        cases.append(canonical_json({**parsed, "unknown": "field"}).encode())
        cases.append(event.final_bytes.replace(b'"sequence":1', b'"sequence":1.0'))
        invalid_base64 = {**parsed, "payload_bytes_base64": "Zg="}
        cases.append(canonical_json(invalid_base64).encode())

        for candidate in cases:
            with self.subTest(candidate=candidate[-80:]), self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_BYTES_INVALID",
            ):
                events_module.load_challenger_replacement_event_bytes(candidate)

    def test_loader_rejects_tampered_payload_hash_root_and_sequence(self):
        event = fixture_event(self.root)
        parsed = json.loads(event.final_bytes)
        mutations = (
            {**parsed, "payload_bytes_base64": base64.b64encode(b"changed").decode()},
            {**parsed, "event_hash": "f" * 64},
            {**parsed, "event_root_inode": self.root.inode + 1},
            {**parsed, "sequence": 2},
        )
        for mutation in mutations:
            with self.subTest(field=mutation), self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_BYTES_INVALID",
            ):
                events_module.load_challenger_replacement_event_bytes(
                    canonical_json(mutation).encode()
                )

    def test_build_rejects_oversize_final_bytes(self):
        with self.assertRaisesRegex(
            ChallengerReplacementEventError,
            "CHALLENGER_REPLACEMENT_EVENT_BYTES_INVALID",
        ):
            fixture_event(self.root, payload=b"x" * 3_145_728)

    def test_sequence_is_bounded_by_the_twenty_digit_filename_contract(self):
        maximum = (1 << 53) - 1
        self.assertEqual(events_module._MAX_CANONICAL_EVENT_SEQUENCE, maximum)
        event = fixture_event(self.root, sequence=maximum)
        self.assertEqual(event.sequence, maximum)
        for invalid in (1 << 53, 10**20):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_BYTES_INVALID",
            ):
                fixture_event(self.root, sequence=invalid)


class EventPublicationTests(unittest.TestCase):
    def setUp(self):
        self.workspace = EventWorkspace()
        self.root = open_challenger_replacement_event_root(self.workspace.identity())

    def tearDown(self):
        self.root.close()
        self.workspace.close()

    @staticmethod
    def publication_record(publication):
        return {
            name: getattr(publication, name)
            for name in ("sequence", "event_hash", "device", "inode", "size")
        }

    def test_read_only_verifier_binds_exact_publication_inode(self):
        event = fixture_event(self.root)
        publication = events_module.publish_challenger_replacement_event(
            self.root, event,
        )
        record = self.publication_record(publication)
        self.assertEqual(
            events_module.verify_challenger_replacement_event_publication(
                self.root, record,
            ), event,
        )

        final = Path(publication.absolute_path)
        replacement = final.with_name("same-bytes-new-inode.tmp")
        replacement.write_bytes(final.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, final)
        with self.assertRaisesRegex(
            ChallengerReplacementEventError,
            "CHALLENGER_REPLACEMENT_EVENT_PUBLICATION_UNTRUSTED",
        ):
            events_module.verify_challenger_replacement_event_publication(
                self.root, record,
            )

    def test_read_only_verifier_rejects_nonexact_record(self):
        publication = events_module.publish_challenger_replacement_event(
            self.root, fixture_event(self.root),
        )
        record = self.publication_record(publication)
        for changed in (
            {**record, "event_hash": "f" * 64},
            {**record, "unexpected": 1},
            {**record, "size": 0},
        ):
            with self.subTest(changed=changed), self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_PUBLICATION_UNTRUSTED",
            ):
                events_module.verify_challenger_replacement_event_publication(
                    self.root, changed,
                )

    def test_commits_once_then_exact_fast_path_never_creates_staging(self):
        event = fixture_event(self.root)
        first = events_module.publish_challenger_replacement_event(self.root, event)
        opened = []
        real_open = events_module.os.open

        def recording_open(path, flags, *args, **kwargs):
            opened.append((str(path), flags))
            return real_open(path, flags, *args, **kwargs)

        with patch.object(events_module.os, "open", side_effect=recording_open):
            second = events_module.publish_challenger_replacement_event(self.root, event)

        self.assertEqual(first.outcome, "COMMITTED")
        self.assertEqual(second.outcome, "ALREADY_COMMITTED")
        self.assertFalse(any(flags & os.O_CREAT for _, flags in opened))
        final_flags = [flags for name, flags in opened if name.endswith(".event.json")]
        self.assertTrue(final_flags)
        self.assertTrue(all(flags & os.O_NOFOLLOW for flags in final_flags))
        self.assertTrue(all(flags & os.O_NONBLOCK for flags in final_flags))
        self.assertTrue(all(not flags & (os.O_WRONLY | os.O_RDWR) for flags in final_flags))

    def test_conflicting_sequence_fails_before_staging_create(self):
        events_module.publish_challenger_replacement_event(
            self.root, fixture_event(self.root)
        )
        conflicting = fixture_event(self.root, payload=b"different")
        with patch.object(events_module.os, "open", wraps=events_module.os.open) as opened:
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_SEQUENCE_CONFLICT",
            ):
                events_module.publish_challenger_replacement_event(
                    self.root, conflicting
                )
        self.assertFalse(
            any(call.args[1] & os.O_CREAT for call in opened.call_args_list)
        )

    def test_exact_retry_confirms_directory_durability_before_already_committed(self):
        event = fixture_event(self.root)
        real_fsync = events_module._fsync_retry

        def fail_before_directory_fsync(descriptor):
            if descriptor == self.root.descriptor:
                raise ChallengerReplacementEventError(
                    "CHALLENGER_REPLACEMENT_EVENT_FSYNC_FAILED"
                )
            real_fsync(descriptor)

        with patch.object(
            events_module, "_fsync_retry", side_effect=fail_before_directory_fsync
        ):
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_FSYNC_FAILED",
            ):
                events_module.publish_challenger_replacement_event(self.root, event)
        self.assertTrue(
            (self.workspace.event_root / "00000000000000000001.event.json").exists()
        )

        directory_fsyncs = 0
        final_reads = 0
        root_validations = 0
        real_read_final = events_module._read_final
        real_validate = self.root.validate

        def record_fsync(descriptor):
            nonlocal directory_fsyncs
            real_fsync(descriptor)
            if descriptor == self.root.descriptor:
                directory_fsyncs += 1

        def record_final_read(*args):
            nonlocal final_reads
            final_reads += 1
            return real_read_final(*args)

        def record_validate():
            nonlocal root_validations
            root_validations += 1
            return real_validate()

        with patch.object(events_module, "_fsync_retry", side_effect=record_fsync), \
             patch.object(events_module, "_read_final", side_effect=record_final_read), \
             patch.object(self.root, "validate", side_effect=record_validate):
            result = events_module.publish_challenger_replacement_event(self.root, event)

        self.assertEqual(result.outcome, "ALREADY_COMMITTED")
        self.assertEqual(directory_fsyncs, 1)
        self.assertGreaterEqual(final_reads, 2)
        self.assertGreaterEqual(root_validations, 2)

        with patch.object(
            events_module,
            "_fsync_retry",
            side_effect=ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_FSYNC_FAILED"
            ),
        ):
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_FSYNC_FAILED",
            ):
                events_module.publish_challenger_replacement_event(self.root, event)

    def test_eexist_exact_race_confirms_directory_durability(self):
        event = fixture_event(self.root)
        real_rename = events_module._rename_noreplace
        real_fsync = events_module._fsync_retry
        directory_fsyncs = 0

        def publish_then_report_eexist(directory_descriptor, source, destination):
            real_rename(directory_descriptor, source, destination)
            raise OSError(errno.EEXIST, "race loser")

        def record_fsync(descriptor):
            nonlocal directory_fsyncs
            real_fsync(descriptor)
            if descriptor == self.root.descriptor:
                directory_fsyncs += 1

        with patch.object(
            events_module, "_rename_noreplace", publish_then_report_eexist
        ), patch.object(events_module, "_fsync_retry", side_effect=record_fsync):
            result = events_module.publish_challenger_replacement_event(self.root, event)

        self.assertEqual(result.outcome, "ALREADY_COMMITTED")
        self.assertEqual(directory_fsyncs, 1)

    def test_eexist_exact_race_never_succeeds_when_durability_confirmation_fails(self):
        event = fixture_event(self.root)
        real_rename = events_module._rename_noreplace
        real_fsync = events_module._fsync_retry

        def publish_then_report_eexist(directory_descriptor, source, destination):
            real_rename(directory_descriptor, source, destination)
            raise OSError(errno.EEXIST, "race loser")

        def fail_before_directory_fsync(descriptor):
            if descriptor == self.root.descriptor:
                raise ChallengerReplacementEventError(
                    "CHALLENGER_REPLACEMENT_EVENT_FSYNC_FAILED"
                )
            real_fsync(descriptor)

        with patch.object(
            events_module, "_rename_noreplace", publish_then_report_eexist
        ), patch.object(
            events_module, "_fsync_retry", side_effect=fail_before_directory_fsync
        ):
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_FSYNC_FAILED",
            ):
                events_module.publish_challenger_replacement_event(self.root, event)

    def test_staging_uses_exclusive_read_write_and_handles_eintr_short_write(self):
        event = fixture_event(self.root)
        real_write = events_module.os.write
        writes = 0

        def interrupted_short_write(fd, data):
            nonlocal writes
            writes += 1
            if writes == 1:
                raise InterruptedError()
            return real_write(fd, data[:7] if writes == 2 else data)

        opened = []
        real_open = events_module.os.open

        def recording_open(path, flags, *args, **kwargs):
            opened.append((str(path), flags))
            return real_open(path, flags, *args, **kwargs)

        with patch.object(events_module.os, "write", side_effect=interrupted_short_write), \
             patch.object(events_module.os, "open", side_effect=recording_open):
            result = events_module.publish_challenger_replacement_event(self.root, event)

        self.assertEqual(result.outcome, "COMMITTED")
        staging = [(name, flags) for name, flags in opened if name.startswith(".stage-")]
        self.assertEqual(len(staging), 1)
        required = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        self.assertEqual(staging[0][1] & required, required)

    def test_zero_write_and_same_fd_readback_corruption_fail(self):
        event = fixture_event(self.root)
        with patch.object(events_module.os, "write", return_value=0):
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_WRITE_FAILED",
            ):
                events_module.publish_challenger_replacement_event(self.root, event)

        real_read = events_module.os.read
        corrupted = False

        def corrupt_first_read(fd, size):
            nonlocal corrupted
            data = real_read(fd, size)
            if not corrupted and data:
                corrupted = True
                return bytes([data[0] ^ 1]) + data[1:]
            return data

        with patch.object(events_module.os, "read", side_effect=corrupt_first_read):
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_STAGING_UNTRUSTED",
            ):
                events_module.publish_challenger_replacement_event(self.root, event)

    def test_fsync_and_no_replace_failures_never_report_success(self):
        event = fixture_event(self.root)
        with patch.object(events_module.os, "fsync", side_effect=OSError(errno.EIO, "x")):
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_FSYNC_FAILED",
            ):
                events_module.publish_challenger_replacement_event(self.root, event)
        with patch.object(
            events_module, "_rename_noreplace", side_effect=OSError(errno.ENOSYS, "x")
        ):
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_PUBLISH_FAILED",
            ):
                events_module.publish_challenger_replacement_event(self.root, event)

    def test_every_successfully_opened_publication_fd_is_closed_once(self):
        event = fixture_event(self.root)
        opened = []
        closed = []
        real_open = events_module.os.open
        real_close = events_module.os.close

        def recording_open(*args, **kwargs):
            descriptor = real_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor

        def recording_close(descriptor):
            closed.append(descriptor)
            return real_close(descriptor)

        with patch.object(events_module.os, "open", side_effect=recording_open), \
             patch.object(events_module.os, "close", side_effect=recording_close):
            result = events_module.publish_challenger_replacement_event(self.root, event)

        self.assertEqual(result.outcome, "COMMITTED")
        self.assertCountEqual(opened, closed)
        self.assertEqual(len(opened), len(closed))

    def test_empty_oversize_directory_and_socket_final_reject_before_read(self):
        event = fixture_event(self.root)
        final = self.workspace.event_root / "00000000000000000001.event.json"
        creators = (
            lambda: final.touch(mode=0o600),
            lambda: final.write_bytes(b"x" * 4_194_305),
            lambda: final.mkdir(mode=0o700),
        )
        for create in creators:
            with self.subTest(create=create):
                try:
                    create()
                    with patch.object(events_module.os, "read") as read:
                        with self.assertRaisesRegex(
                            ChallengerReplacementEventError,
                            "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED",
                        ):
                            events_module.publish_challenger_replacement_event(
                                self.root, event
                            )
                        read.assert_not_called()
                finally:
                    if final.is_dir():
                        final.rmdir()
                    elif final.exists():
                        final.unlink()

        server = socket.socket(socket.AF_UNIX)
        try:
            server.bind(str(final))
            with patch.object(events_module.os, "read") as read:
                with self.assertRaisesRegex(
                    ChallengerReplacementEventError,
                    "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED",
                ):
                    events_module.publish_challenger_replacement_event(self.root, event)
                read.assert_not_called()
        finally:
            server.close()
            final.unlink(missing_ok=True)

    def test_fifo_final_fast_path_is_nonblocking_in_subprocess(self):
        event = fixture_event(self.root)
        final = self.workspace.event_root / "00000000000000000001.event.json"
        os.mkfifo(final, 0o600)
        before = final.lstat()
        source_root = str(Path(__file__).parents[1] / "src")
        script = """
import os, sys
from crypto_quant.challenger_replacement_events import *
path, dev, ino, uid = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
identity = ChallengerReplacementEventRootIdentity(path, dev, ino, uid, '0700')
with open_challenger_replacement_event_root(identity) as root:
    event = build_challenger_replacement_event(sequence=1,event_type='INPUT_PREPARED',slot_id='slot-fixture',worker_id='worker-fixture',recorded_at='2026-08-09T08:05:00.000Z',previous_event_hash='0'*64,payload_bytes=b'fixture-payload',plan_hash='1'*64,build_identity_hash='2'*64,event_root=root)
    try:
        publish_challenger_replacement_event(root, event)
    except ChallengerReplacementEventError as error:
        print(error.reason_code)
"""
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(self.workspace.event_root),
                str(self.root.device),
                str(self.root.inode),
                str(self.root.uid),
            ],
            env={**os.environ, "PYTHONPATH": source_root},
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        after = final.lstat()
        self.assertEqual(
            completed.stdout.strip(),
            "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED",
        )
        self.assertEqual(
            (after.st_dev, after.st_ino, after.st_mode, after.st_nlink, after.st_ctime_ns),
            (before.st_dev, before.st_ino, before.st_mode, before.st_nlink, before.st_ctime_ns),
        )


class EventIoFailureTests(unittest.TestCase):
    def setUp(self):
        self.workspace = EventWorkspace()
        self.root = open_challenger_replacement_event_root(self.workspace.identity())

    def tearDown(self):
        self.root.close()
        self.workspace.close()

    def test_write_read_lseek_fstat_and_stat_oserrors_map_to_fixed_io_failure(self):
        event = fixture_event(self.root)
        real_fstat = events_module.os.fstat
        real_stat = events_module.os.stat

        def fail_nonroot_fstat(descriptor):
            if descriptor != self.root.descriptor:
                raise OSError(errno.EIO, "fstat")
            return real_fstat(descriptor)

        def fail_relative_stat(path, *args, **kwargs):
            if kwargs.get("dir_fd") == self.root.descriptor:
                raise OSError(errno.EIO, "stat")
            return real_stat(path, *args, **kwargs)

        failures = (
            patch.object(events_module.os, "write", side_effect=OSError(errno.ENOSPC, "write")),
            patch.object(events_module.os, "read", side_effect=OSError(errno.EIO, "read")),
            patch.object(events_module.os, "lseek", side_effect=OSError(errno.EIO, "lseek")),
            patch.object(events_module.os, "fstat", side_effect=fail_nonroot_fstat),
            patch.object(events_module.os, "stat", side_effect=fail_relative_stat),
        )
        for failure in failures:
            with self.subTest(failure=failure):
                with failure, self.assertRaisesRegex(
                    ChallengerReplacementEventError,
                    "CHALLENGER_REPLACEMENT_EVENT_IO_FAILED",
                ):
                    events_module.publish_challenger_replacement_event(
                        self.root, event
                    )

    def test_root_close_maps_oserror_to_fixed_close_failure(self):
        descriptor = self.root.descriptor
        with patch.object(
            events_module.os, "close", side_effect=OSError(errno.EIO, "close")
        ):
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_CLOSE_FAILED",
            ):
                self.root.close()
        os.close(descriptor)

    def test_close_failure_does_not_override_primary_failure(self):
        staging_fd = None
        staging_close_attempts = 0
        real_open = events_module.os.open
        real_close = events_module.os.close

        def record_staging_open(path, flags, *args, **kwargs):
            nonlocal staging_fd
            descriptor = real_open(path, flags, *args, **kwargs)
            if str(path).startswith(".stage-"):
                staging_fd = descriptor
            return descriptor

        def fail_staging_close(descriptor):
            nonlocal staging_close_attempts
            if descriptor == staging_fd:
                staging_close_attempts += 1
                raise OSError(errno.EIO, "close")
            return real_close(descriptor)

        with patch.object(events_module.os, "open", side_effect=record_staging_open), \
             patch.object(events_module.os, "write", side_effect=OSError(errno.ENOSPC, "write")), \
             patch.object(events_module.os, "close", side_effect=fail_staging_close):
            with self.assertRaises(ChallengerReplacementEventError) as raised:
                events_module.publish_challenger_replacement_event(
                    self.root, fixture_event(self.root)
                )

        self.assertEqual(
            raised.exception.reason_code,
            "CHALLENGER_REPLACEMENT_EVENT_IO_FAILED",
        )
        self.assertEqual(
            raised.exception.close_failure_reason_code,
            "CHALLENGER_REPLACEMENT_EVENT_CLOSE_FAILED",
        )
        self.assertEqual(staging_close_attempts, 1)
        real_close(staging_fd)

    def test_publication_close_failure_without_primary_maps_to_fixed_failure(self):
        staging_fd = None
        attempts = 0
        real_open = events_module.os.open
        real_close = events_module.os.close

        def record_staging_open(path, flags, *args, **kwargs):
            nonlocal staging_fd
            descriptor = real_open(path, flags, *args, **kwargs)
            if str(path).startswith(".stage-"):
                staging_fd = descriptor
            return descriptor

        def fail_staging_close(descriptor):
            nonlocal attempts
            if descriptor == staging_fd:
                attempts += 1
                raise OSError(errno.EIO, "close")
            return real_close(descriptor)

        with patch.object(events_module.os, "open", side_effect=record_staging_open), \
             patch.object(events_module.os, "close", side_effect=fail_staging_close):
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_CLOSE_FAILED",
            ):
                events_module.publish_challenger_replacement_event(
                    self.root, fixture_event(self.root)
                )
        self.assertEqual(attempts, 1)
        real_close(staging_fd)

    def test_existing_final_read_oserrors_map_to_fixed_io_failure(self):
        event = fixture_event(self.root)
        events_module.publish_challenger_replacement_event(self.root, event)
        real_fstat = events_module.os.fstat
        real_stat = events_module.os.stat

        def fail_final_fstat(descriptor):
            if descriptor != self.root.descriptor:
                raise OSError(errno.EIO, "final fstat")
            return real_fstat(descriptor)

        def fail_final_stat(path, *args, **kwargs):
            if kwargs.get("dir_fd") == self.root.descriptor:
                raise OSError(errno.EIO, "final stat")
            return real_stat(path, *args, **kwargs)

        failures = (
            patch.object(events_module.os, "read", side_effect=OSError(errno.EIO, "final read")),
            patch.object(events_module.os, "fstat", side_effect=fail_final_fstat),
            patch.object(events_module.os, "stat", side_effect=fail_final_stat),
        )
        for failure in failures:
            with self.subTest(failure=failure), failure, self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_IO_FAILED",
            ):
                events_module.publish_challenger_replacement_event(self.root, event)

    def test_unexpected_publish_error_survives_staging_close_failure(self):
        staging_fd = None
        real_open = events_module.os.open
        real_close = events_module.os.close

        def record_open(path, flags, *args, **kwargs):
            nonlocal staging_fd
            descriptor = real_open(path, flags, *args, **kwargs)
            if str(path).startswith(".stage-"):
                staging_fd = descriptor
            return descriptor

        def fail_close(descriptor):
            if descriptor == staging_fd:
                raise OSError(errno.EIO, "close")
            return real_close(descriptor)

        with patch.object(events_module.os, "open", side_effect=record_open), \
             patch.object(events_module, "_write_all", side_effect=RuntimeError("primary")), \
             patch.object(events_module.os, "close", side_effect=fail_close):
            with self.assertRaisesRegex(RuntimeError, "primary") as raised:
                events_module.publish_challenger_replacement_event(
                    self.root, fixture_event(self.root)
                )
        self.assertEqual(
            raised.exception.close_failure_reason_code,
            "CHALLENGER_REPLACEMENT_EVENT_CLOSE_FAILED",
        )
        real_close(staging_fd)

    def test_unexpected_final_loader_error_survives_final_close_failure(self):
        event = fixture_event(self.root)
        events_module.publish_challenger_replacement_event(self.root, event)
        final_fd = None
        real_open = events_module.os.open
        real_close = events_module.os.close

        def record_open(path, flags, *args, **kwargs):
            nonlocal final_fd
            descriptor = real_open(path, flags, *args, **kwargs)
            if str(path).endswith(".event.json"):
                final_fd = descriptor
            return descriptor

        def fail_close(descriptor):
            if descriptor == final_fd:
                raise OSError(errno.EIO, "close")
            return real_close(descriptor)

        with patch.object(events_module.os, "open", side_effect=record_open), \
             patch.object(
                 events_module,
                 "load_challenger_replacement_event_bytes",
                 side_effect=RuntimeError("primary-final"),
             ), \
             patch.object(events_module.os, "close", side_effect=fail_close):
            with self.assertRaisesRegex(RuntimeError, "primary-final") as raised:
                events_module._read_final(
                    self.root, "00000000000000000001.event.json"
                )
        self.assertEqual(
            raised.exception.close_failure_reason_code,
            "CHALLENGER_REPLACEMENT_EVENT_CLOSE_FAILED",
        )
        real_close(final_fd)


class EventReplayTests(unittest.TestCase):
    def setUp(self):
        self.workspace = EventWorkspace()
        self.root = open_challenger_replacement_event_root(self.workspace.identity())

    def tearDown(self):
        self.root.close()
        self.workspace.close()

    def test_empty_and_two_event_replay_has_exact_projection(self):
        empty = events_module.replay_challenger_replacement_events(self.root)
        self.assertEqual(empty.events, ())
        self.assertEqual(empty.last_event_hash, _ZERO_HASH)
        self.assertEqual(empty.next_sequence, 1)

        first = fixture_event(self.root)
        second = fixture_event(
            self.root,
            sequence=2,
            payload=b"second",
            previous_event_hash=first.event_hash,
        )
        events_module.publish_challenger_replacement_event(self.root, first)
        events_module.publish_challenger_replacement_event(self.root, second)
        replay = events_module.replay_challenger_replacement_events(self.root)
        self.assertEqual(replay.events, (first, second))
        self.assertEqual(replay.last_event_hash, second.event_hash)
        self.assertEqual(replay.next_sequence, 3)

    def test_orphan_staging_is_counted_but_never_read_as_state(self):
        partial = self.workspace.event_root / (
            f".stage-{1:020d}-{'a' * 64}-{'b' * 32}.tmp"
        )
        complete = self.workspace.event_root / (
            f".stage-{1:020d}-{'c' * 64}-{'d' * 32}.tmp"
        )
        partial.write_bytes(b"partial")
        complete.write_bytes(b"complete-staging-body")
        partial.chmod(0o600)
        complete.chmod(0o600)
        with patch.object(events_module.os, "read") as read:
            replay = events_module.replay_challenger_replacement_events(self.root)
            read.assert_not_called()
        self.assertEqual(replay.events, ())
        self.assertEqual(replay.next_sequence, 1)
        self.assertEqual(replay.orphan_staging_count, 2)
        self.assertEqual(
            replay.orphan_staging_bytes,
            len(b"partial") + len(b"complete-staging-body"),
        )

    def test_rejects_gap_parent_fork_and_unknown_name(self):
        second = fixture_event(self.root, sequence=2)
        events_module.publish_challenger_replacement_event(self.root, second)
        with self.assertRaisesRegex(
            ChallengerReplacementEventError,
            "CHALLENGER_REPLACEMENT_EVENT_CONTINUITY_GAP",
        ):
            events_module.replay_challenger_replacement_events(self.root)
        (self.workspace.event_root / "00000000000000000002.event.json").unlink()

        first = fixture_event(self.root)
        wrong_parent = fixture_event(self.root, sequence=2, payload=b"fork")
        events_module.publish_challenger_replacement_event(self.root, first)
        events_module.publish_challenger_replacement_event(self.root, wrong_parent)
        with self.assertRaisesRegex(
            ChallengerReplacementEventError,
            "CHALLENGER_REPLACEMENT_EVENT_CONTINUITY_GAP",
        ):
            events_module.replay_challenger_replacement_events(self.root)
        for candidate in self.workspace.event_root.iterdir():
            candidate.unlink()

        (self.workspace.event_root / "1.event.json").write_bytes(b"x")
        with self.assertRaisesRegex(
            ChallengerReplacementEventError,
            "CHALLENGER_REPLACEMENT_EVENT_DIRECTORY_UNTRUSTED",
        ):
            events_module.replay_challenger_replacement_events(self.root)

    def test_final_size_is_checked_before_read(self):
        final = self.workspace.event_root / "00000000000000000001.event.json"
        for body in (b"", b"x" * 4_194_305):
            final.write_bytes(body)
            final.chmod(0o600)
            with patch.object(events_module.os, "read") as read:
                with self.assertRaisesRegex(
                    ChallengerReplacementEventError,
                    "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED",
                ):
                    events_module.replay_challenger_replacement_events(self.root)
                read.assert_not_called()
            final.unlink()

    def test_fresh_capability_ignores_crash_staging_and_retries_event(self):
        event = fixture_event(self.root)
        with patch.object(
            events_module, "_rename_noreplace", side_effect=OSError(errno.EIO, "crash")
        ):
            with self.assertRaises(ChallengerReplacementEventError):
                events_module.publish_challenger_replacement_event(self.root, event)
        self.root.close()
        self.root = open_challenger_replacement_event_root(self.workspace.identity())
        replay = events_module.replay_challenger_replacement_events(self.root)
        self.assertEqual(replay.events, ())
        self.assertEqual(replay.orphan_staging_count, 1)
        result = events_module.publish_challenger_replacement_event(self.root, event)
        self.assertEqual(result.outcome, "COMMITTED")
        self.assertEqual(
            events_module.replay_challenger_replacement_events(self.root).events,
            (event,),
        )

    def test_reopened_capability_crash_point_table(self):
        phases = (
            ("after_staging_create", False),
            ("after_partial_write", False),
            ("after_complete_write", False),
            ("after_file_fsync", False),
            ("after_no_replace", True),
            ("after_dir_fsync", True),
        )
        for phase, final_visible in phases:
            with self.subTest(phase=phase):
                workspace = EventWorkspace()
                root = open_challenger_replacement_event_root(workspace.identity())
                event = fixture_event(root)
                original_write_all = events_module._write_all
                original_fsync = events_module._fsync_retry
                original_read_final = events_module._read_final

                def crash_write(fd, data):
                    if phase == "after_partial_write":
                        os.write(fd, data[:7])
                    elif phase == "after_complete_write":
                        original_write_all(fd, data)
                    raise RuntimeError(phase)

                def crash_fsync(fd):
                    if phase == "after_no_replace" and fd == root.descriptor:
                        raise RuntimeError(phase)
                    original_fsync(fd)

                final_reads = 0

                def crash_final_read(capability, name):
                    nonlocal final_reads
                    final_reads += 1
                    if phase == "after_dir_fsync" and final_reads == 2:
                        raise RuntimeError(phase)
                    return original_read_final(capability, name)

                patches = []
                if phase in {
                    "after_staging_create",
                    "after_partial_write",
                    "after_complete_write",
                }:
                    patches.append(
                        patch.object(events_module, "_write_all", side_effect=crash_write)
                    )
                elif phase == "after_file_fsync":
                    patches.append(
                        patch.object(
                            events_module,
                            "_rename_noreplace",
                            side_effect=RuntimeError(phase),
                        )
                    )
                elif phase == "after_no_replace":
                    patches.append(
                        patch.object(events_module, "_fsync_retry", side_effect=crash_fsync)
                    )
                else:
                    patches.append(
                        patch.object(events_module, "_read_final", side_effect=crash_final_read)
                    )
                try:
                    with patches[0], self.assertRaises(RuntimeError):
                        events_module.publish_challenger_replacement_event(root, event)
                    root.close()
                    root = open_challenger_replacement_event_root(workspace.identity())
                    replay = events_module.replay_challenger_replacement_events(root)
                    self.assertEqual(bool(replay.events), final_visible)
                    outcome = events_module.publish_challenger_replacement_event(
                        root, event
                    ).outcome
                    self.assertEqual(
                        outcome,
                        "ALREADY_COMMITTED" if final_visible else "COMMITTED",
                    )
                finally:
                    root.close()
                    workspace.close()

    def test_new_interpreter_retries_rename_visible_before_directory_fsync(self):
        event = fixture_event(self.root)
        real_fsync = events_module._fsync_retry

        def crash_before_directory_fsync(descriptor):
            if descriptor == self.root.descriptor:
                raise ChallengerReplacementEventError(
                    "CHALLENGER_REPLACEMENT_EVENT_FSYNC_FAILED"
                )
            real_fsync(descriptor)

        with patch.object(
            events_module,
            "_fsync_retry",
            side_effect=crash_before_directory_fsync,
        ):
            with self.assertRaises(ChallengerReplacementEventError):
                events_module.publish_challenger_replacement_event(self.root, event)

        source_root = str(Path(__file__).parents[1] / "src")
        script = """
import sys
import crypto_quant.challenger_replacement_events as module
identity = module.ChallengerReplacementEventRootIdentity(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), '0700')
with module.open_challenger_replacement_event_root(identity) as root:
    event = module.build_challenger_replacement_event(sequence=1,event_type='INPUT_PREPARED',slot_id='slot-fixture',worker_id='worker-fixture',recorded_at='2026-08-09T08:05:00.000Z',previous_event_hash='0'*64,payload_bytes=b'fixture-payload',plan_hash='1'*64,build_identity_hash='2'*64,event_root=root)
    original = module._fsync_retry
    calls = [0]
    def record(fd):
        original(fd)
        if fd == root.descriptor:
            calls[0] += 1
    from unittest.mock import patch
    with patch.object(module, '_fsync_retry', side_effect=record):
        result = module.publish_challenger_replacement_event(root, event)
    print(result.outcome, calls[0])
"""
        completed = subprocess.run(
            [sys.executable, "-c", script, str(self.workspace.event_root),
             str(self.root.device), str(self.root.inode), str(self.root.uid)],
            env={**os.environ, "PYTHONPATH": source_root},
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        self.assertEqual(completed.stdout.strip(), "ALREADY_COMMITTED 1")

    def test_new_interpreter_replay_confirms_visible_final_durability(self):
        event = fixture_event(self.root)
        real_fsync = events_module._fsync_retry

        def crash_before_directory_fsync(descriptor):
            if descriptor == self.root.descriptor:
                raise ChallengerReplacementEventError(
                    "CHALLENGER_REPLACEMENT_EVENT_FSYNC_FAILED"
                )
            real_fsync(descriptor)

        with patch.object(
            events_module, "_fsync_retry", side_effect=crash_before_directory_fsync
        ):
            with self.assertRaises(ChallengerReplacementEventError):
                events_module.publish_challenger_replacement_event(self.root, event)

        source_root = str(Path(__file__).parents[1] / "src")
        script = """
import sys
import crypto_quant.challenger_replacement_events as module
from unittest.mock import patch
identity = module.ChallengerReplacementEventRootIdentity(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), '0700')
with module.open_challenger_replacement_event_root(identity) as root:
    original = module._fsync_retry
    calls = [0]
    def record(fd):
        original(fd)
        if fd == root.descriptor:
            calls[0] += 1
    with patch.object(module, '_fsync_retry', side_effect=record):
        replay = module.replay_challenger_replacement_events(root)
    print('REPLAY', len(replay.events), calls[0])
"""
        completed = subprocess.run(
            [sys.executable, "-c", script, str(self.workspace.event_root),
             str(self.root.device), str(self.root.inode), str(self.root.uid)],
            env={**os.environ, "PYTHONPATH": source_root},
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        self.assertEqual(completed.stdout.strip(), "REPLAY 1 1")

    def test_replay_never_returns_events_when_directory_fsync_fails(self):
        event = fixture_event(self.root)
        events_module.publish_challenger_replacement_event(self.root, event)
        with patch.object(
            events_module,
            "_fsync_retry",
            side_effect=ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_FSYNC_FAILED"
            ),
        ):
            with self.assertRaisesRegex(
                ChallengerReplacementEventError,
                "CHALLENGER_REPLACEMENT_EVENT_FSYNC_FAILED",
            ):
                events_module.replay_challenger_replacement_events(self.root)

    def test_fifo_replay_is_nonblocking_in_subprocess(self):
        final = self.workspace.event_root / "00000000000000000001.event.json"
        os.mkfifo(final, 0o600)
        source_root = str(Path(__file__).parents[1] / "src")
        script = """
import sys
from crypto_quant.challenger_replacement_events import *
identity = ChallengerReplacementEventRootIdentity(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), '0700')
with open_challenger_replacement_event_root(identity) as root:
    try:
        replay_challenger_replacement_events(root)
    except ChallengerReplacementEventError as error:
        print(error.reason_code)
"""
        completed = subprocess.run(
            [sys.executable, "-c", script, str(self.workspace.event_root),
             str(self.root.device), str(self.root.inode), str(self.root.uid)],
            env={**os.environ, "PYTHONPATH": source_root},
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        self.assertEqual(
            completed.stdout.strip(),
            "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED",
        )


class EventConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.workspace = EventWorkspace()
        self.first_root = open_challenger_replacement_event_root(
            self.workspace.identity()
        )
        self.second_root = open_challenger_replacement_event_root(
            self.workspace.identity()
        )

    def tearDown(self):
        self.first_root.close()
        self.second_root.close()
        self.workspace.close()

    def _run_competitors(self, payloads):
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        queue = context.Queue()
        identity = self.workspace.identity()
        identity_values = (
            identity.absolute_path,
            identity.device,
            identity.inode,
            identity.uid,
            identity.mode_octal,
        )
        processes = [
            context.Process(
                target=_concurrent_publish_worker,
                args=(identity_values, payload, barrier, queue),
            )
            for payload in payloads
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(15)
            if process.is_alive():
                process.terminate()
                process.join(5)
                self.fail("concurrent publisher hung at rename barrier")
            self.assertEqual(process.exitcode, 0)
        messages = [queue.get(timeout=2) for _ in range(4)]
        return (
            [value for kind, value in messages if kind == "rename"],
            [value for kind, value in messages if kind == "outcome"],
        )

    def test_same_event_true_process_race_hits_eexist(self):
        rename_results, outcomes = self._run_competitors(
            (b"fixture-payload", b"fixture-payload")
        )
        self.assertCountEqual(rename_results, ["OK", "EEXIST"])
        self.assertCountEqual(outcomes, ["COMMITTED", "ALREADY_COMMITTED"])
        finals = list(self.workspace.event_root.glob("*.event.json"))
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0].lstat().st_nlink, 1)

    def test_different_event_true_process_race_has_one_conflict(self):
        rename_results, outcomes = self._run_competitors(
            (b"fixture-payload", b"loser")
        )
        self.assertCountEqual(rename_results, ["OK", "EEXIST"])
        self.assertIn("COMMITTED", outcomes)
        self.assertIn("CHALLENGER_REPLACEMENT_EVENT_SEQUENCE_CONFLICT", outcomes)
        finals = list(self.workspace.event_root.glob("*.event.json"))
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0].lstat().st_nlink, 1)
        replay = events_module.replay_challenger_replacement_events(self.second_root)
        self.assertEqual(replay.next_sequence, 2)

if __name__ == "__main__":
    unittest.main()
