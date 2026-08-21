import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SANDBOX = ROOT / "sandboxes" / "nautilus-v065"


def _imports_nautilus(source):
    tree = ast.parse(source)
    return any(
        (
            isinstance(node, ast.Import)
            and any(alias.name == "nautilus_trader" or alias.name.startswith("nautilus_trader.") for alias in node.names)
        )
        or (
            isinstance(node, ast.ImportFrom)
            and isinstance(node.module, str)
            and (node.module == "nautilus_trader" or node.module.startswith("nautilus_trader."))
        )
        for node in ast.walk(tree)
    )


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
            self.assertFalse(_imports_nautilus(path.read_text(encoding="utf-8")), path)

    def test_import_boundary_detects_real_imports_not_subprocess_probe_text(self):
        self.assertTrue(_imports_nautilus("import nautilus_trader\n"))
        self.assertTrue(_imports_nautilus("from nautilus_trader.core import UUID4\n"))
        self.assertFalse(_imports_nautilus('probe = "import nautilus_trader"\n'))


if __name__ == "__main__":
    unittest.main()
