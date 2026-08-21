import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.nautilus_v065_plan import (
    NautilusV065PlanError,
    build_nautilus_v065_plan,
    load_nautilus_v065_plan,
    nautilus_v065_plan_hash,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "config" / "nautilus-e2e-spike-plan-v1.schema.json"
PACKAGE_SCHEMA = (
    ROOT
    / "src"
    / "crypto_quant"
    / "schemas"
    / "nautilus-e2e-spike-plan-v1.schema.json"
)
V064_COMMIT = "c4f6ea213077850a8fc8b9bd3392f1a4bac466f9"
V063_COMMIT = "df91e19240df14839125608422489adf3b902e76"
V063_LOCK_SHA = "ed0342ea4274026b6d936b5489f215eb44b4ae5e8ba651b69f3ed01db09230ee"
V063_COMPARISON_SHA = "88eb4df9cd37e31fca0e636b2ebcf077ddacb33a1eb9877d5e318f04a9a903be"
WHEEL_SHA = "033f6207d1c52095d64a7644f43b90cab939c2038044db70a4165f2acef3d079"
LICENSE_SHA = "ee907919ec88c9c017b1f8b608db20960b6598aefcc4fe58820bde955d65ed3c"


def _git(*args):
    return subprocess.run(
        ["/usr/bin/git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


class NautilusV065PlanTests(unittest.TestCase):
    def setUp(self):
        self.commit = _git("rev-parse", "HEAD")

    def build(self):
        return build_nautilus_v065_plan(
            repository_root=ROOT,
            candidate_commit=self.commit,
        )

    def test_builder_freezes_foundation_predecessor_and_candidate(self):
        plan = self.build()
        self.assertEqual(
            plan["foundation"],
            {
                "release_tag": "v0.64.0",
                "peeled_commit": V064_COMMIT,
                "package_version": "0.64.0",
                "manifest_version": "1.58.0",
                "build_input_tree_hash": "a2a85267fb424b793fac538df40a55be33e900621cb877b1aa1303f16b134344",
                "manifest_hash": "6d32f81a3f9b558f1aa911b1d8d49b9d51491a9ac720675ee2d1cff88186b760",
                "manifest_file_sha256": "038cf827b84ff47b596bd1f3ab72e370ffb17a64a5e6e36264c952769b32abca",
            },
        )
        self.assertEqual(
            plan["predecessor"],
            {
                "release_tag": "v0.63.0",
                "peeled_commit": V063_COMMIT,
                "dependency_lock_path": "artifacts/nautilus-sandbox/nautilus-sandbox-dependency-lock-v0.63.0.json",
                "dependency_lock_file_sha256": V063_LOCK_SHA,
                "comparison_path": "artifacts/nautilus-sandbox/nautilus-sandbox-comparison-v0.63.0.json",
                "comparison_file_sha256": V063_COMPARISON_SHA,
                "conclusion": "INCONCLUSIVE_BLOCKED",
                "reason_code": "SUPPLY_CHAIN_FETCH_NOT_MACHINE_REPLAYABLE",
                "interpretation": "NO_ENGINE_OR_GOLDEN_COMPATIBILITY_RESULT",
            },
        )
        self.assertEqual(
            plan["candidate"],
            {
                "package": "nautilus_trader",
                "version": "1.230.0",
                "requires_python": ">=3.12,<3.15",
                "official_tag": "v1.230.0",
                "tag_object": "112d335088ec11cdd1d60038b16c8fe56406aead",
                "peeled_commit": "8160730c7c550480b0a439fb11086a4c4de15f0b",
                "wheel_filename": "nautilus_trader-1.230.0-cp312-cp312-macosx_15_0_arm64.whl",
                "wheel_size": 156035900,
                "wheel_sha256": WHEEL_SHA,
                "license_expression": "LGPL-3.0-or-later",
                "license_sha256": LICENSE_SHA,
                "operating_system": "macOS",
                "operating_system_major": 15,
                "machine": "arm64",
                "python_implementation": "CPython",
                "python_minor": "3.12",
            },
        )

    def test_builder_freezes_code_tree_scenarios_classifications_and_authority(self):
        plan = self.build()
        self.assertEqual(plan["code_lock_candidate"]["commit"], self.commit)
        self.assertEqual(
            plan["code_lock_candidate"]["tree"],
            _git("rev-parse", self.commit + "^{tree}"),
        )
        self.assertEqual(
            plan["scenarios"],
            [
                "IMMEDIATE_FULL",
                "PARTIAL_THEN_FULL",
                "BELOW_MINIMUM_REJECTED",
                "FRESH_PROCESS_REPLAY",
            ],
        )
        self.assertEqual(
            plan["difference_classes"],
            [
                "EXACT_MATCH",
                "EXPECTED_ENGINE_REPRESENTATION_DIFFERENCE",
                "ROUNDING_POLICY_DIFFERENCE",
                "FILL_MODEL_DIFFERENCE",
                "FEE_MODEL_DIFFERENCE",
                "POSITION_ACCOUNTING_DIFFERENCE",
                "PNL_ACCOUNTING_DIFFERENCE",
                "RESTART_SEMANTICS_DIFFERENCE",
                "UNSUPPORTED_INSTRUMENT_RULE",
                "SUPPLY_CHAIN_OR_LICENSE_FAILURE",
                "SAFETY_BOUNDARY_VIOLATION",
                "INVALID_OR_INCOMPLETE_EVIDENCE",
            ],
        )
        self.assertEqual(
            plan["terminal_conclusions"],
            [
                "ADOPT_FOR_PREREGISTERED_SHADOW",
                "REJECT_KEEP_CURRENT_CORE",
                "INCONCLUSIVE_KEEP_CURRENT_CORE",
            ],
        )
        self.assertEqual(
            plan["authority"],
            {
                "production_activation": False,
                "runtime_install_authorized": False,
                "sandbox_service_install_authorized": False,
                "live_adapter_allowed": False,
                "credentials_allowed": False,
                "market_requests_allowed_during_sandbox": False,
                "account_requests_allowed": False,
                "broker_requests_allowed": False,
                "real_orders_allowed": False,
                "production_state_writes_allowed": False,
                "runner_or_scheduler_invocation_allowed": False,
            },
        )
        self.assertEqual(plan["status"], "SPIKE_PLAN_PREREGISTERED_NOT_EXECUTED")
        self.assertEqual(plan["plan_hash"], nautilus_v065_plan_hash(plan))
        self.assertRegex(plan["plan_id"], r"^nautilus_v065_plan_[0-9a-f]{64}$")

    def test_schema_is_strict_mirrored_and_accepts_only_builder(self):
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        schema = json.loads(CONFIG_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        plan = self.build()
        self.assertEqual(list(validator.iter_errors(plan)), [])
        changed = copy.deepcopy(plan)
        changed["candidate"]["version"] = "1.231.0"
        self.assertNotEqual(list(validator.iter_errors(changed)), [])
        extra = copy.deepcopy(plan)
        extra["manual_override"] = True
        self.assertNotEqual(list(validator.iter_errors(extra)), [])

    def test_builder_rejects_unreviewed_or_non_descendant_identity(self):
        for candidate, reason in (
            (V063_COMMIT, "NAUTILUS_V065_CANDIDATE_NOT_V064_DESCENDANT"),
            ("A" * 40, "NAUTILUS_V065_CANDIDATE_COMMIT_INVALID"),
            ("0" * 40, "NAUTILUS_V065_CANDIDATE_COMMIT_UNAVAILABLE"),
        ):
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(NautilusV065PlanError, reason):
                    build_nautilus_v065_plan(
                        repository_root=ROOT,
                        candidate_commit=candidate,
                    )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                NautilusV065PlanError, "NAUTILUS_V065_REPOSITORY_ROOT_INVALID"
            ):
                build_nautilus_v065_plan(
                    repository_root=Path(directory),
                    candidate_commit=self.commit,
                )

    def test_loader_replays_canonical_owner_controlled_plan(self):
        plan = self.build()
        body = canonical_json(plan).encode("utf-8") + b"\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_bytes(body)
            path.chmod(0o644)
            self.assertEqual(load_nautilus_v065_plan(path.resolve()), plan)

    def test_loader_rejects_semantic_drift_duplicate_float_and_unsafe_paths(self):
        plan = self.build()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "plan.json"

            changed = copy.deepcopy(plan)
            changed["candidate"]["wheel_sha256"] = "0" * 64
            path.write_bytes(canonical_json(changed).encode("utf-8") + b"\n")
            path.chmod(0o644)
            with self.assertRaisesRegex(
                NautilusV065PlanError, "NAUTILUS_V065_PLAN_SCHEMA_INVALID"
            ):
                load_nautilus_v065_plan(path.resolve())

            path.write_bytes(b'{"a":1,"a":2}\n')
            with self.assertRaisesRegex(
                NautilusV065PlanError, "NAUTILUS_V065_PLAN_JSON_DUPLICATE_KEY"
            ):
                load_nautilus_v065_plan(path.resolve())

            path.write_bytes(b'{"value":1.5}\n')
            with self.assertRaisesRegex(
                NautilusV065PlanError, "NAUTILUS_V065_PLAN_JSON_FLOAT_FORBIDDEN"
            ):
                load_nautilus_v065_plan(path.resolve())

            path.write_bytes(canonical_json(plan).encode("utf-8") + b"\n")
            path.chmod(0o666)
            before = path.stat()
            with self.assertRaisesRegex(
                NautilusV065PlanError, "NAUTILUS_V065_PLAN_PATH_INVALID"
            ):
                load_nautilus_v065_plan(path.resolve())
            after = path.stat()
            self.assertEqual(
                (after.st_dev, after.st_ino, after.st_mode, after.st_size),
                (before.st_dev, before.st_ino, before.st_mode, before.st_size),
            )

            sentinel = root / "sentinel"
            sentinel.write_bytes(b"outside")
            sentinel.chmod(0o600)
            path.unlink()
            path.symlink_to(sentinel)
            sentinel_before = sentinel.stat()
            with self.assertRaisesRegex(
                NautilusV065PlanError, "NAUTILUS_V065_PLAN_PATH_INVALID"
            ):
                load_nautilus_v065_plan(path.absolute())
            sentinel_after = sentinel.stat()
            self.assertEqual(sentinel.read_bytes(), b"outside")
            self.assertEqual(
                (
                    sentinel_after.st_ino,
                    sentinel_after.st_mode,
                    sentinel_after.st_size,
                    sentinel_after.st_nlink,
                ),
                (
                    sentinel_before.st_ino,
                    sentinel_before.st_mode,
                    sentinel_before.st_size,
                    sentinel_before.st_nlink,
                ),
            )


if __name__ == "__main__":
    unittest.main()
