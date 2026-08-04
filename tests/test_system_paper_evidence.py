import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import crypto_quant.system_paper_evidence as evidence_module
from crypto_quant.system_paper_evidence import (
    SystemPaperEvidenceError,
    publish_owner_exact,
)


class SystemPaperEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name).resolve() / "evidence"
        self.parent.mkdir(mode=0o700)
        os.chmod(self.parent, 0o700)
        self.target = self.parent / "receipt.json"

    def _write_target(self, body=b"existing", mode=0o600):
        self.target.write_bytes(body)
        os.chmod(self.target, mode)

    def test_concurrent_different_target_is_never_overwritten(self):
        def concurrent_create():
            self._write_target(b"concurrent")

        with self.assertRaisesRegex(
            SystemPaperEvidenceError,
            "SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT",
        ):
            publish_owner_exact(
                self.target,
                b"candidate",
                _before_link=concurrent_create,
            )

        self.assertEqual(self.target.read_bytes(), b"concurrent")

    def test_existing_exact_target_is_idempotent_without_metadata_change(self):
        self._write_target(b"exact")
        before = self.target.stat()

        publish_owner_exact(self.target, b"exact")

        after = self.target.stat()
        self.assertEqual((after.st_dev, after.st_ino), (before.st_dev, before.st_ino))
        self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(after.st_mode, before.st_mode)

    def test_unsafe_existing_targets_are_rejected(self):
        cases = ("symlink", "hardlink", "wrong_mode")
        for kind in cases:
            with self.subTest(kind=kind):
                if self.target.exists() or self.target.is_symlink():
                    self.target.unlink()
                auxiliary = self.parent / "auxiliary"
                if auxiliary.exists():
                    auxiliary.unlink()
                if kind == "symlink":
                    auxiliary.write_bytes(b"exact")
                    os.chmod(auxiliary, 0o600)
                    self.target.symlink_to(auxiliary)
                elif kind == "hardlink":
                    self._write_target(b"exact")
                    os.link(self.target, auxiliary)
                else:
                    self._write_target(b"exact", mode=0o644)
                with self.assertRaisesRegex(
                    SystemPaperEvidenceError,
                    "SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT",
                ):
                    publish_owner_exact(self.target, b"exact")

    def test_wrong_owner_probe_rejects_parent_before_write(self):
        with mock.patch(
            "crypto_quant.system_paper_evidence.os.getuid",
            return_value=os.getuid() + 1,
        ):
            with self.assertRaisesRegex(
                SystemPaperEvidenceError,
                "SYSTEM_PAPER_EVIDENCE_PARENT_INVALID",
            ):
                publish_owner_exact(self.target, b"candidate")
        self.assertFalse(self.target.exists())

    def test_invalid_parent_close_failure_is_typed(self):
        os.chmod(self.parent, 0o755)
        with mock.patch.object(
            evidence_module.os,
            "close",
            side_effect=OSError("close failure"),
        ), self.assertRaisesRegex(
            SystemPaperEvidenceError,
            "SYSTEM_PAPER_EVIDENCE_PARENT_INVALID",
        ):
            publish_owner_exact(self.target, b"candidate")

    def test_parent_replacement_during_publication_fails_and_cleans_link(self):
        moved = self.parent.with_name("evidence-retained")

        def replace_parent():
            self.parent.rename(moved)
            self.parent.mkdir(mode=0o700)
            os.chmod(self.parent, 0o700)

        with self.assertRaisesRegex(
            SystemPaperEvidenceError,
            "SYSTEM_PAPER_EVIDENCE_PARENT_CHANGED",
        ):
            publish_owner_exact(
                self.target,
                b"candidate",
                _before_link=replace_parent,
            )

        self.assertFalse(self.target.exists())
        self.assertFalse((moved / self.target.name).exists())

    def test_eexist_race_rechecks_visible_parent_before_success(self):
        moved = self.parent.with_name("evidence-retained")
        original_open = evidence_module.os.open
        injected = {"done": False}

        def replace_parent_before_exclusive_open(path, flags, *args, **kwargs):
            if path == self.target.name and flags & os.O_EXCL and not injected["done"]:
                injected["done"] = True
                self._write_target(b"candidate")
                self.parent.rename(moved)
                self.parent.mkdir(mode=0o700)
                os.chmod(self.parent, 0o700)
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(
            evidence_module.os,
            "open",
            side_effect=replace_parent_before_exclusive_open,
        ), self.assertRaisesRegex(
            SystemPaperEvidenceError,
            "SYSTEM_PAPER_EVIDENCE_PARENT_CHANGED",
        ):
            publish_owner_exact(self.target, b"candidate")

        self.assertTrue(injected["done"])
        self.assertFalse(self.target.exists())
        self.assertEqual((moved / self.target.name).read_bytes(), b"candidate")

    def test_existing_exact_path_replacement_after_read_is_rejected(self):
        self._write_target(b"exact")
        original = evidence_module._read_all

        def replace_after_read(descriptor, expected_size):
            body = original(descriptor, expected_size)
            self.target.unlink()
            self._write_target(b"evil!")
            return body

        with mock.patch.object(
            evidence_module, "_read_all", side_effect=replace_after_read
        ), self.assertRaisesRegex(
            SystemPaperEvidenceError,
            "SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT",
        ):
            publish_owner_exact(self.target, b"exact")
        self.assertEqual(self.target.read_bytes(), b"evil!")

    def test_filesystem_failures_are_typed_and_never_remove_published_name(self):
        missing = self.parent / "missing" / "receipt.json"
        with self.assertRaises(SystemPaperEvidenceError):
            publish_owner_exact(missing, b"candidate")

        self._write_target(b"exact")
        with mock.patch.object(
            evidence_module.os, "read", side_effect=OSError("read failed")
        ), self.assertRaisesRegex(
            SystemPaperEvidenceError,
            "SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT",
        ):
            publish_owner_exact(self.target, b"exact")

        self.target.unlink()
        with mock.patch.object(
            evidence_module.os, "write", side_effect=OSError("write failure")
        ), self.assertRaisesRegex(
            SystemPaperEvidenceError,
            "SYSTEM_PAPER_EVIDENCE_WRITE_FAILED",
        ):
            publish_owner_exact(self.target, b"candidate")
        self.assertTrue(self.target.exists())
        self.assertEqual(self.target.read_bytes(), b"")
        with self.assertRaisesRegex(
            SystemPaperEvidenceError,
            "SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT",
        ):
            publish_owner_exact(self.target, b"candidate")

        self.target.unlink()

        calls = {"count": 0}
        original_fsync = evidence_module.os.fsync

        def fail_directory_fsync(descriptor):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("directory fsync failure")
            return original_fsync(descriptor)

        with mock.patch.object(
            evidence_module.os, "fsync", side_effect=fail_directory_fsync
        ), self.assertRaises(SystemPaperEvidenceError):
            publish_owner_exact(self.target, b"candidate")
        self.assertEqual(self.target.read_bytes(), b"candidate")
        publish_owner_exact(self.target, b"candidate")

    def test_publication_uses_no_temporary_path_or_unlink(self):
        def assert_no_temporary_path():
            self.assertFalse(
                any(
                    item.name.startswith(".system-paper-evidence-")
                    for item in self.parent.iterdir()
                )
            )

        with mock.patch.object(
            evidence_module.os,
            "unlink",
            side_effect=AssertionError("publisher attempted unlink"),
        ):
            publish_owner_exact(
                self.target,
                b"candidate",
                _before_link=assert_no_temporary_path,
            )
        self.assertEqual(self.target.read_bytes(), b"candidate")

    def test_post_publish_failure_never_unlinks_concurrent_replacement(self):
        original_fsync = evidence_module.os.fsync
        original_unlink = evidence_module.os.unlink
        calls = {"count": 0}

        def replace_public_name_then_fail(descriptor):
            calls["count"] += 1
            if calls["count"] == 2:
                original_unlink(self.target)
                self._write_target(b"replacement")
                raise OSError("directory fsync failure")
            return original_fsync(descriptor)

        with mock.patch.object(
            evidence_module.os,
            "fsync",
            side_effect=replace_public_name_then_fail,
        ), self.assertRaises(SystemPaperEvidenceError):
            publish_owner_exact(self.target, b"candidate")

        self.assertEqual(self.target.read_bytes(), b"replacement")


if __name__ == "__main__":
    unittest.main()
