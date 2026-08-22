import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crypto_quant.challenger_replacement_deployment import (
    ChallengerReplacementDeploymentError,
    _read_owner_exact,
    challenger_replacement_deployment_bytes,
)
from crypto_quant import challenger_replacement_live_runtime_cli as live_cli


class DeploymentIoSafetyTests(unittest.TestCase):
    def test_close_failure_is_fixed_domain_error_without_file_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.json"
            candidate.write_bytes(challenger_replacement_deployment_bytes())
            os.chmod(candidate, 0o600)
            before = candidate.stat()
            with patch(
                "crypto_quant.challenger_replacement_deployment.os.close",
                side_effect=OSError("test-only close failure"),
            ), self.assertRaises(ChallengerReplacementDeploymentError) as raised:
                _read_owner_exact(candidate)
            after = candidate.stat()
        self.assertEqual(
            raised.exception.reason_code,
            "CHALLENGER_REPLACEMENT_DEPLOYMENT_PATH_UNTRUSTED",
        )
        self.assertEqual(
            (before.st_dev, before.st_ino, before.st_nlink, before.st_mode,
             before.st_size, before.st_mtime_ns, before.st_ctime_ns),
            (after.st_dev, after.st_ino, after.st_nlink, after.st_mode,
             after.st_size, after.st_mtime_ns, after.st_ctime_ns),
        )

    def test_preflight_subprocess_timeout_maps_to_fixed_failure(self):
        from crypto_quant import challenger_replacement_preflight as preflight

        with tempfile.TemporaryDirectory() as directory, patch(
            "crypto_quant.challenger_replacement_preflight.subprocess.run",
            side_effect=subprocess.TimeoutExpired(("git", "status"), 15),
        ), self.assertRaisesRegex(ValueError, "PREFLIGHT_COMMAND_FAILED"):
            preflight._run(("git", "status"), Path(directory))

    def test_untrusted_existing_objects_are_rejected_without_sentinel_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); sentinel = root / "sentinel"
            sentinel.write_bytes(challenger_replacement_deployment_bytes()); os.chmod(sentinel, 0o600)
            symlink = root / "symlink"; os.symlink(sentinel, symlink)
            hardlink = root / "hardlink"; os.link(sentinel, hardlink)
            fifo = root / "fifo"; os.mkfifo(fifo, 0o600)
            before = sentinel.stat()
            for candidate in (symlink, hardlink, fifo, root):
                with self.subTest(candidate=candidate), self.assertRaises(ChallengerReplacementDeploymentError):
                    _read_owner_exact(candidate)
            after = sentinel.stat()
        self.assertEqual((before.st_dev,before.st_ino,before.st_nlink,before.st_mode,before.st_size,before.st_mtime_ns,before.st_ctime_ns),(after.st_dev,after.st_ino,after.st_nlink,after.st_mode,after.st_size,after.st_mtime_ns,after.st_ctime_ns))


class LiveCrashSafetyTests(unittest.TestCase):
    def test_crash_before_input_publication_reacquires_in_same_window(self):
        from tests.test_challenger_replacement_live_runtime import LiveRuntimeTests

        fixture = LiveRuntimeTests(); fixture.setUp()
        try:
            state = fixture._state()
            with patch.object(state, "append", side_effect=SystemExit("before INPUT")), patch.object(
                live_cli, "_load_fixed_runtime_contract", return_value={"state":state,"worker_id":"crash-worker"}
            ), patch.object(live_cli, "acquire_challenger_replacement_live_capture", return_value=fixture.live_capture) as acquire, self.assertRaises(SystemExit):
                live_cli._run_live_invocation()
            self.assertEqual(len(fixture._state().replay()["events"]), 0)
            fresh = fixture._state()
            with patch.object(live_cli, "_load_fixed_runtime_contract", return_value={"state":fresh,"worker_id":"retry-worker"}), patch.object(
                live_cli, "acquire_challenger_replacement_live_capture", return_value=fixture.live_capture
            ) as retry_acquire:
                result = live_cli._run_live_invocation()
            self.assertEqual((acquire.call_count,retry_acquire.call_count,result["terminal_stage"]),(1,1,"SLOT_SUCCEEDED"))
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    unittest.main()
