"""Static and YAGNI gates for the bounded v0.66 runtime candidate."""

import inspect
import json
import re
import unittest
from pathlib import Path

from crypto_quant.challenger_replacement_runtime import ChallengerReplacementRuntimeState
import crypto_quant
from crypto_quant.build import EvaluatorBuild


ROOT = Path(__file__).resolve().parents[1]
FOUR_MODULES = tuple(
    ROOT / "src/crypto_quant" / f"challenger_replacement_{name}.py"
    for name in ("decision", "evidence", "events", "runtime")
)
FORBIDDEN = (
    "sqlite3", "PRAGMA", "-wal", "-shm", "fault_injector",
    "SOURCE_BUNDLE_PUBLISHED", "DECISION_PUBLISHED",
    "ChallengerReplacementOutputRoot", "order_writes",
)


class V066RuntimeScopeTests(unittest.TestCase):
    def test_four_production_modules_stay_below_frozen_line_cap(self):
        counts = {path.name: len(path.read_text().splitlines()) for path in FOUR_MODULES}
        self.assertLess(sum(counts.values()), 2743, counts)

    def test_forbidden_platform_and_old_authority_symbols_are_absent(self):
        combined = "\n".join(path.read_text() for path in FOUR_MODULES)
        for forbidden in FORBIDDEN:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)

    def test_runtime_constructor_accepts_only_capabilities_and_frozen_identity(self):
        self.assertEqual(
            tuple(inspect.signature(ChallengerReplacementRuntimeState).parameters),
            ("event_root", "plan", "build_identity"),
        )

    def test_evidence_and_decision_modules_have_no_path_io(self):
        for path in FOUR_MODULES[:2]:
            text = path.read_text()
            for forbidden in ("open(", "read_bytes", "write_bytes", "chmod("):
                with self.subTest(path=path.name, forbidden=forbidden):
                    self.assertNotIn(forbidden, text)

    def test_runtime_does_not_create_sqlite_or_export_authority_files(self):
        forbidden_names = (
            "challenger-replacement.sqlite", "challenger-replacement.sqlite-wal",
            "challenger-replacement.sqlite-shm",
        )
        for name in forbidden_names:
            self.assertFalse(any(ROOT.rglob(name)), name)
        self.assertFalse((ROOT / "exports/source-bundles").exists())
        self.assertFalse((ROOT / "exports/decisions").exists())


class V066ReleaseIdentityTests(unittest.TestCase):
    def test_release_versions_and_build_inputs_are_frozen(self):
        pyproject = (ROOT / "pyproject.toml").read_text()
        self.assertIsNotNone(re.search(r'^version = "0\.68\.0"$', pyproject, re.MULTILINE))
        manifest = json.loads((ROOT / "config/evaluator-build-manifest-v1.json").read_text())
        self.assertEqual(crypto_quant.__version__, "0.68.0")
        self.assertEqual(manifest["package_version"], "0.68.0")
        self.assertEqual(manifest["manifest_version"], "1.62.0")
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        required = {
            "config/challenger-replacement-source-bundle-v1.schema.json",
            "config/challenger-replacement-decision-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-source-bundle-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-decision-v1.schema.json",
            "src/crypto_quant/challenger_replacement_events.py",
            "src/crypto_quant/challenger_replacement_evidence.py",
            "src/crypto_quant/challenger_replacement_decision.py",
            "src/crypto_quant/challenger_replacement_runtime.py",
            "tests/challenger_replacement_v2_fixtures.py",
            "tests/test_challenger_replacement_events.py",
            "tests/test_challenger_replacement_evidence.py",
            "tests/test_challenger_replacement_decision.py",
            "tests/test_challenger_replacement_runtime.py",
            "tests/test_challenger_replacement_v066_release.py",
            "docs/superpowers/specs/2026-08-22-replacement-three-stage-event-runtime-design.md",
            "docs/superpowers/plans/2026-08-22-replacement-three-stage-event-runtime.md",
            "docs/adr/0066-replacement-three-stage-event-runtime.md",
            "docs/implementation-status-v0.66.0.md",
        }
        self.assertEqual(required - expected, set())

    def test_release_docs_preserve_nonactivation_boundary(self):
        documents = [
            (ROOT / "docs/adr/0066-replacement-three-stage-event-runtime.md").read_text(),
            (ROOT / "docs/implementation-status-v0.66.0.md").read_text(),
        ]
        required = (
            "RUNTIME_RELEASED_NOT_INSTALLED", "production_activation=false",
            "runtime_install_authorized=false", "replacement_start_authorized=false",
            "no 90-day timer started", "no profitability or AI advantage claim",
        )
        for document in documents:
            for text in required:
                self.assertIn(text, document)


if __name__ == "__main__":
    unittest.main()
