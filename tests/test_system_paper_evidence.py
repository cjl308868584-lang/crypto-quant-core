import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
