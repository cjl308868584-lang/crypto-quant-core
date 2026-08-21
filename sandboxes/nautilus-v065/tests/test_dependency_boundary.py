import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SANDBOX = ROOT / "sandboxes" / "nautilus-v065"


class DependencyBoundaryTests(unittest.TestCase):
    def test_nautilus_dependency_exists_only_in_python312_sandbox(self):
        sandbox = (SANDBOX / "pyproject.toml").read_text(encoding="utf-8")
        root_project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements.lock").read_text(encoding="utf-8")
        self.assertIn('requires-python = ">=3.12,<3.13"', sandbox)
        self.assertIn('"nautilus_trader==1.230.0"', sandbox)
        self.assertNotIn("nautilus", root_project.lower())
        self.assertNotIn("nautilus", requirements.lower())

    def test_root_runtime_does_not_import_nautilus(self):
        for path in (ROOT / "src" / "crypto_quant").glob("*.py"):
            self.assertNotIn("import nautilus_trader", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
