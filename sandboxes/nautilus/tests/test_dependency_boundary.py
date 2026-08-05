import importlib.util
import sys
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DependencyBoundaryTests(unittest.TestCase):
    def test_sandbox_requires_exact_python312_and_nautilus_version(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["project"]["requires-python"], ">=3.12,<3.13")
        self.assertEqual(project["project"]["dependencies"], ["nautilus_trader==1.227.0"])
        self.assertEqual(sys.version_info[:2], (3, 12))

    def test_sandbox_has_one_one_shot_entrypoint_and_no_live_adapter_dependency(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(
            project["project"]["scripts"],
            {
                "crypto-quant-nautilus-sandbox":
                    "crypto_quant_nautilus_sandbox.runner:main"
            },
        )
        lock_text = (ROOT / "uv.lock").read_text(encoding="utf-8").lower()
        for forbidden in (
            "nautilus-binance",
            "nautilus-bybit",
            "nautilus-okx",
            "ibapi",
        ):
            self.assertNotIn(forbidden, lock_text)

    def test_dependency_task_does_not_install_environment_or_runner(self):
        self.assertFalse((ROOT / ".venv").exists())
        self.assertIsNone(
            importlib.util.find_spec("crypto_quant_nautilus_sandbox.runner")
        )


if __name__ == "__main__":
    unittest.main()
