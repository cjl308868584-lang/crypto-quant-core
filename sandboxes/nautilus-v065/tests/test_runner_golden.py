import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SANDBOX_SRC = ROOT / "sandboxes" / "nautilus-v065" / "src"
REQUEST_FIXTURE = ROOT / "tests" / "fixtures" / "nautilus-v065" / "ethusdt-4h-input-v2.json"


def _prepare(root):
    request = root / "request.json"
    receipt = root / "receipt.json"
    result = root / "result.json"
    request.write_bytes(REQUEST_FIXTURE.read_bytes())
    receipt.write_text(
        '{"receipt_hash":"' + "4" * 64 + '","receipt_id":"nautilus_v065_supply_chain_' + "3" * 64 + '"}\n',
        encoding="utf-8",
    )
    request.chmod(0o600)
    receipt.chmod(0o600)
    return request, receipt, result


def _run(root, result=None, extra_env=None, prepare=True):
    if prepare:
        request, receipt, default_result = _prepare(root)
    else:
        request, receipt, default_result = root / "request.json", root / "receipt.json", root / "result.json"
    result = result or default_result
    environment = {
        "HOME": str(root),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(SANDBOX_SRC),
        "LANG": "C",
        "LC_ALL": "C",
    }
    environment.update(extra_env or {})
    completed = subprocess.run(
        [
            sys.executable,
            "-P",
            "-m",
            "crypto_quant_nautilus_v065.runner",
            "--request",
            str(request),
            "--receipt",
            str(receipt),
            "--result",
            str(result),
        ],
        cwd=root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return completed, result


class RunnerGoldenTests(unittest.TestCase):
    def test_four_scenarios_use_engine_order_fill_fee_position_and_pnl(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            completed, result = _run(root)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            self.assertEqual(completed.stderr, b"")
            payload = json.loads(result.read_text(encoding="utf-8"))
            self.assertEqual(payload["engine"], "NAUTILUS_TRADER_1.230.0")
            self.assertEqual(
                [item["scenario"] for item in payload["scenario_results"]],
                ["IMMEDIATE_FULL", "PARTIAL_THEN_FULL", "BELOW_MINIMUM_REJECTED", "FRESH_PROCESS_REPLAY"],
            )
            immediate, partial, below, replay = payload["scenario_results"]
            self.assertEqual(
                (immediate["status"], immediate["filled_quantity"], immediate["average_price"], immediate["fee_usdt"], immediate["ending_position_eth"]),
                ("FILLED", "0.05", "2000.1", "0.100005", "0.05"),
            )
            self.assertEqual([event["kind"] for event in partial["events"]], ["ORDER_ACCEPTED", "FILL", "FILL"])
            self.assertEqual(partial["filled_quantity"], "0.05")
            self.assertNotEqual(partial["average_price"], "2000.16")
            self.assertEqual(below["status"], "REJECTED_MIN_NOTIONAL")
            self.assertEqual(below["filled_quantity"], "0")
            self.assertEqual(below["ending_cash_usdt"], "1000")
            for key in ("status", "filled_quantity", "average_price", "fee_usdt", "ending_cash_usdt", "ending_position_eth", "net_pnl_usdt"):
                self.assertEqual(replay[key], immediate[key])
            self.assertEqual(set(payload["safety_counters"].values()), {0})
            self.assertEqual(result.stat().st_mode & 0o777, 0o600)

    def test_second_fresh_process_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as first_raw, tempfile.TemporaryDirectory() as second_raw:
            first_root, second_root = Path(first_raw), Path(second_raw)
            first_root.chmod(0o700)
            second_root.chmod(0o700)
            first, first_result = _run(first_root)
            second, second_result = _run(second_root)
            self.assertEqual((first.returncode, second.returncode), (0, 0), first.stderr + second.stderr)
            self.assertEqual(first_result.read_bytes(), second_result.read_bytes())


if __name__ == "__main__":
    unittest.main()
