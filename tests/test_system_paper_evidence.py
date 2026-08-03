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

    def test_filesystem_failures_are_typed_and_do_not_leave_final_target(self):
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
        original_unlink = evidence_module.os.unlink
        failed = {"done": False}

        def fail_first_temp_unlink(name, *args, **kwargs):
            if str(name).startswith(".system-paper-evidence-") and not failed["done"]:
                failed["done"] = True
                raise OSError("one-shot unlink failure")
            return original_unlink(name, *args, **kwargs)

        with mock.patch.object(
            evidence_module.os, "unlink", side_effect=fail_first_temp_unlink
        ), self.assertRaises(SystemPaperEvidenceError):
            publish_owner_exact(self.target, b"candidate")
        self.assertFalse(self.target.exists())
        self.assertFalse(
            any(item.name.startswith(".system-paper-evidence-") for item in self.parent.iterdir())
        )

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
        self.assertFalse(self.target.exists())
        self.assertFalse(
            any(item.name.startswith(".system-paper-evidence-") for item in self.parent.iterdir())
        )


if __name__ == "__main__":
    unittest.main()
