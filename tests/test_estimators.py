import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from crypto_quant.build import EvaluatorBuild
from crypto_quant.errors import PolicyError
from crypto_quant.estimators import EstimatorRegistry
from crypto_quant.release import load_json_strict
from crypto_quant.trade_replay import (
    build_trade_replay_snapshot,
    trade_replay_snapshot_hash,
)

from tests.factories import complete_trade_replay_inputs


ROOT = Path(__file__).resolve().parents[1]


class EstimatorRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_json_strict(
            ROOT / "config" / "release-metrics-v1.1.json"
        )
        cls.registry = EstimatorRegistry.load(ROOT / "config", cls.catalog)

    def test_every_catalog_algorithm_resolves_without_implicit_execution(self):
        all_ids = set(self.catalog["algorithms"])
        executable = set(self.registry.executable_estimator_ids)
        unavailable = set(self.registry.unavailable_estimator_ids)

        self.assertEqual(self.catalog["catalog_version"], "1.1.4")
        self.assertEqual(
            self.registry.registry["registry_version"],
            "1.5.0",
        )
        self.assertEqual(all_ids, executable | unavailable)
        self.assertFalse(executable & unavailable)
        self.assertEqual(len(all_ids), 57)
        self.assertEqual(len(executable), 21)
        self.assertEqual(len(unavailable), 36)

        unavailable_result = self.registry.execute(
            "ACHIEVED_POWER_AT_MERE_V1",
            {},
        )
        self.assertEqual(unavailable_result.status, "FAIL")
        self.assertEqual(
            unavailable_result.reason_codes,
            ("ESTIMATOR_NOT_EXECUTABLE",),
        )

        unknown_result = self.registry.execute("NOT_IN_CATALOG_V1", {})
        self.assertEqual(unknown_result.status, "FAIL")
        self.assertEqual(unknown_result.reason_codes, ("UNKNOWN_ESTIMATOR",))

    def test_input_contract_and_decimal_boundaries_fail_closed(self):
        missing = self.registry.execute(
            "ACTUAL_DEPLOYABLE_CAPITAL_V1",
            {"snapshot_verified": True},
        )
        self.assertEqual(missing.status, "FAIL")
        self.assertEqual(
            missing.reason_codes,
            (
                "ESTIMATOR_INPUT_MISSING:"
                "actual_deployable_capital_usdt",
            ),
        )

        unexpected = self.registry.execute(
            "ACTUAL_DEPLOYABLE_CAPITAL_V1",
            {
                "actual_deployable_capital_usdt": "1",
                "snapshot_verified": True,
                "unapproved_input": "ignored-if-not-checked",
            },
        )
        self.assertEqual(unexpected.status, "FAIL")
        self.assertEqual(
            unexpected.reason_codes,
            ("ESTIMATOR_INPUT_UNEXPECTED:unapproved_input",),
        )

        for invalid in (-1, "-0.01", 0.1):
            with self.subTest(invalid=invalid):
                result = self.registry.execute(
                    "ACTUAL_DEPLOYABLE_CAPITAL_V1",
                    {
                        "actual_deployable_capital_usdt": invalid,
                        "snapshot_verified": True,
                    },
                )
                self.assertEqual(result.status, "FAIL")
                self.assertEqual(
                    result.reason_codes,
                    ("ACTUAL_DEPLOYABLE_CAPITAL_INVALID",),
                )

        exact_boundary = self.registry.execute(
            "DECIMAL_CAPITAL_COMPARISON_V1",
            {
                "actual_deployable_capital_usdt": "0.10000000000000000001",
                "approved_production_capital_usdt": "0.1",
                "break_even_capital_lcb_root_usdt": None,
                "comparison": "APPROVED",
                "scope_verified": True,
            },
        )
        self.assertEqual(exact_boundary.status, "COMPUTED")
        self.assertIs(exact_boundary.value, True)

    def test_complete_trade_replay_estimator_is_executable(self):
        source, snapshots, valuations = complete_trade_replay_inputs()
        replay = build_trade_replay_snapshot(
            replay_id="registry-trade-replay",
            source_series_snapshot=source,
            economic_snapshots=snapshots,
            valuation_checkpoints=valuations,
            generated_at=source["generated_at"],
        )

        self.assertTrue(
            self.registry.is_executable(
                "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1"
            )
        )
        execution = self.registry.execute(
            "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1",
            {"trade_replay_snapshot": replay},
        )
        self.assertEqual(execution.status, "COMPUTED")
        self.assertEqual(execution.value, "0")
        self.assertEqual(execution.reason_codes, ())

        missing = self.registry.execute(
            "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1",
            {},
        )
        self.assertEqual(
            missing.reason_codes,
            ("ESTIMATOR_INPUT_MISSING:trade_replay_snapshot",),
        )

        schema_invalid = deepcopy(replay)
        schema_invalid.pop("source_series_hash")
        rejected = self.registry.execute(
            "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1",
            {"trade_replay_snapshot": schema_invalid},
        )
        self.assertEqual(
            rejected.reason_codes,
            ("TRADE_REPLAY_SCHEMA_INVALID",),
        )

        semantic_tamper = deepcopy(replay)
        semantic_tamper["selected_trade_ids"] = []
        semantic_tamper["replay_hash"] = trade_replay_snapshot_hash(
            semantic_tamper
        )
        rejected = self.registry.execute(
            "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1",
            {"trade_replay_snapshot": semantic_tamper},
        )
        self.assertEqual(
            rejected.reason_codes,
            ("TRADE_REPLAY_SELECTION_MISMATCH",),
        )

    def test_golden_vectors_are_deterministic(self):
        reports = [self.registry.run_golden_vectors() for _ in range(100)]
        self.assertTrue(all(report.passed for report in reports))
        self.assertEqual({report.vector_count for report in reports}, {33})
        self.assertEqual(
            {report.report_hash for report in reports},
            {
                "589a82cd39bce26e9b39d249a3f24e9f"
                "54cb35602c9582425239186bd1a7da90"
            },
        )

    def test_registry_and_golden_bundle_tampering_is_rejected(self):
        cases = (
            ("estimator-registry-v1.json", "registry_version", "1.0.1"),
            (
                "estimator-golden-vectors-v1.json",
                "bundle_version",
                "1.0.1",
            ),
        )
        for filename, field, value in cases:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp) / "config"
                shutil.copytree(ROOT / "config", config)
                path = config / filename
                artifact = json.loads(path.read_text(encoding="utf-8"))
                artifact[field] = value
                path.write_text(
                    json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(PolicyError, "self hash mismatch"):
                    EstimatorRegistry.load(config, self.catalog)


class EvaluatorBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog = load_json_strict(
            ROOT / "config" / "release-metrics-v1.1.json"
        )
        cls.registry = EstimatorRegistry.load(ROOT / "config", catalog)

    def test_manifest_binds_complete_evaluator_file_set(self):
        build = EvaluatorBuild.load(ROOT, self.registry)
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        manifest = load_json_strict(
            ROOT / "config" / "evaluator-build-manifest-v1.json"
        )

        self.assertEqual(set(manifest["file_hashes"]), expected)
        self.assertIn("src/crypto_quant/release.py", expected)
        self.assertIn("src/crypto_quant/estimators.py", expected)
        self.assertIn("config/release-gates-v1.1.json", expected)
        self.assertIn(
            "config/trade-replay-snapshot-v1.schema.json",
            expected,
        )
        self.assertEqual(manifest["manifest_version"], "1.6.0")
        self.assertEqual(manifest["package_version"], "0.13.0")
        self.assertEqual(manifest["metric_catalog_version"], "1.1.4")
        self.assertEqual(manifest["golden_vector_count"], 33)
        self.assertEqual(build.executable_estimator_count, 21)
        self.assertEqual(build.unavailable_estimator_count, 36)
        self.assertEqual(build.build_hash, manifest["manifest_hash"])

    def test_modified_evaluator_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp) / "workspace"
            shutil.copytree(
                ROOT,
                clone,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            release_path = clone / "src" / "crypto_quant" / "release.py"
            release_path.write_text(
                release_path.read_text(encoding="utf-8") + "\n# tampered\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                PolicyError,
                "EvaluatorBuild input hash mismatch",
            ):
                EvaluatorBuild.load(clone, self.registry)


if __name__ == "__main__":
    unittest.main()
