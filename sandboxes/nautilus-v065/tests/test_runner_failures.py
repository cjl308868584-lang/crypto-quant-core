import inspect
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_runner_golden import REQUEST_FIXTURE, _prepare, _run


class RunnerFailureTests(unittest.TestCase):
    def test_each_runner_process_uses_exactly_one_engine_without_child_fanout(self):
        from crypto_quant_nautilus_v065 import runner

        source = inspect.getsource(runner)
        self.assertEqual(source.count("BacktestEngine("), 1)
        self.assertNotIn("subprocess.run", source)
        self.assertNotIn("_run_child", source)
        self.assertNotIn("_CHILD_ENV", source)

    def test_account_position_and_pnl_are_read_from_nautilus(self):
        from crypto_quant_nautilus_v065 import runner

        source = inspect.getsource(runner)
        for required in (
            "account_for_venue",
            "balance_total",
            "portfolio.net_position",
            "portfolio.realized_pnl",
            "portfolio.unrealized_pnl",
            "portfolio.total_pnl",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "ending_cash =",
            "unrealized = (",
            "net = unrealized",
            '"realized_pnl_usdt": "0"',
        ):
            self.assertNotIn(forbidden, source)

    def test_canonical_but_changed_fixture_is_rejected_before_engine(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            request, _receipt, result = _prepare(root)
            payload = json.loads(request.read_text(encoding="utf-8"))
            payload["starting_state"]["cash_usdt"] = "900"
            request.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            request.chmod(0o600)
            completed, _ = _run(root, prepare=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(result.exists())

    def test_engine_failure_before_publication_leaves_no_canonical_result(self):
        from crypto_quant_nautilus_v065 import runner

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            request, receipt, result = _prepare(root)
            clean_environment = {"HOME": str(root), "PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
            with mock.patch.dict(os.environ, clean_environment, clear=True), mock.patch.object(
                runner, "_run_engine", side_effect=RuntimeError("TEST_ONLY_ENGINE_CRASH")
            ):
                with self.assertRaisesRegex(RuntimeError, "TEST_ONLY_ENGINE_CRASH"):
                    runner._parent_main(request, receipt, result)
            self.assertFalse(result.exists())

    def test_wrong_receipt_noncanonical_request_and_existing_result_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            request, receipt, result = _prepare(root)
            receipt.write_text('{"receipt_hash":"' + "0" * 64 + '","receipt_id":"wrong"}\n')
            receipt.chmod(0o600)
            completed, _ = _run(root, prepare=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(result.exists())

            request, receipt, result = _prepare(root)
            request.write_text(json.dumps(json.loads(REQUEST_FIXTURE.read_text()), indent=2) + "\n")
            request.chmod(0o600)
            completed = __import__("subprocess").run(
                [__import__("sys").executable, "-P", "-m", "crypto_quant_nautilus_v065.runner", "--request", str(request), "--receipt", str(receipt), "--result", str(result)],
                env={"HOME": str(root), "PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
                cwd=root,
                stdout=__import__("subprocess").PIPE,
                stderr=__import__("subprocess").PIPE,
                timeout=30,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(result.exists())

            request.write_bytes(REQUEST_FIXTURE.read_bytes())
            request.chmod(0o600)
            result.write_bytes(b"sentinel")
            result.chmod(0o600)
            completed = __import__("subprocess").run(
                [__import__("sys").executable, "-P", "-m", "crypto_quant_nautilus_v065.runner", "--request", str(request), "--receipt", str(receipt), "--result", str(result)],
                env={"HOME": str(root), "PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
                cwd=root,
                stdout=__import__("subprocess").PIPE,
                stderr=__import__("subprocess").PIPE,
                timeout=30,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(result.read_bytes(), b"sentinel")

    def test_credential_environment_is_rejected_before_result(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            completed, result = _run(root, extra_env={"BINANCE_API_KEY": "forbidden"})
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(result.exists())

    def test_network_guard_second_engine_and_static_live_adapter_boundary(self):
        from crypto_quant_nautilus_v065 import runner

        runner._install_network_guard()
        with self.assertRaisesRegex(RuntimeError, "NETWORK_FORBIDDEN"):
            socket.socket()
        runner._claim_engine()
        with self.assertRaisesRegex(RuntimeError, "SECOND_ENGINE_FORBIDDEN"):
            runner._claim_engine()
        source = inspect.getsource(runner)
        self.assertNotIn("nautilus_trader.adapters", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib", source)

    def test_symlink_hardlink_and_fifo_result_never_modify_sentinel(self):
        for kind in ("symlink", "hardlink", "fifo"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                root.chmod(0o700)
                sentinel = root / "sentinel"
                sentinel.write_bytes(b"outside")
                sentinel.chmod(0o600)
                result = root / "result.json"
                if kind == "symlink":
                    result.symlink_to(sentinel)
                elif kind == "hardlink":
                    os.link(sentinel, result)
                else:
                    os.mkfifo(result, 0o600)
                completed, _ = _run(root, result=result)
                self.assertNotEqual(completed.returncode, 0)
                self.assertEqual(sentinel.read_bytes(), b"outside")


if __name__ == "__main__":
    unittest.main()
