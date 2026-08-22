"""Static and YAGNI gates for the bounded v0.66 runtime candidate."""

import inspect
import unittest
from pathlib import Path

from crypto_quant.challenger_replacement_runtime import ChallengerReplacementRuntimeState


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


if __name__ == "__main__":
    unittest.main()
