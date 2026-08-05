import copy
import hashlib
import importlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.nautilus_sandbox_dependency import (
    NautilusSandboxDependencyError,
    build_nautilus_sandbox_dependency_lock,
    load_nautilus_sandbox_dependency_lock,
    verify_nautilus_sandbox_dependency_lock,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "config" / "nautilus-sandbox-dependency-lock-v1.schema.json"
PACKAGE_SCHEMA_PATH = (
    ROOT / "src" / "crypto_quant" / "schemas" / SCHEMA_PATH.name
)
ARTIFACT = (
    ROOT
    / "artifacts"
    / "nautilus-sandbox"
    / "nautilus-sandbox-dependency-lock-v0.63.0.json"
)


class NautilusSandboxDependencyTests(unittest.TestCase):
    def payload(self):
        return build_nautilus_sandbox_dependency_lock(workspace_root=ROOT)

    def test_builder_freezes_exact_official_supply_chain(self):
        payload = self.payload()
        self.assertEqual(payload["schema_version"], "1.0.0")
        self.assertEqual(payload["status"], "DEPENDENCY_LOCK_VERIFIED_SANDBOX_ONLY")
        self.assertEqual(
            payload["package"],
            {
                "name": "nautilus_trader",
                "version": "1.227.0",
                "development_status": "BETA",
                "requires_python": ">=3.12,<3.15",
                "official_tag": "v1.227.0",
                "tag_object": "0ccb5b55879c072a6e07fc7cbe5297c53c378107",
                "peeled_commit": "280ae1762df51a492a4ce71506a40b5c8706def5",
            },
        )
        self.assertEqual(
            payload["wheel"],
            {
                "filename": "nautilus_trader-1.227.0-cp312-cp312-macosx_15_0_arm64.whl",
                "size": 145812901,
                "sha256": "735fbbc0737be8f945ee641aeb0dbf0ea6b4c6111f11f10c244fe198f8158953",
                "python_tag": "cp312",
                "abi_tag": "cp312",
                "platform_tag": "macosx_15_0_arm64",
            },
        )
        self.assertEqual(
            payload["license"],
            {
                "expression": "LGPL-3.0-or-later",
                "path": "LICENSE",
                "git_blob": "5550e2db15f239ea8d3cf54bfa3b035eab8d3174",
                "size": 7651,
                "sha256": "ee907919ec88c9c017b1f8b608db20960b6598aefcc4fe58820bde955d65ed3c",
            },
        )
        self.assertEqual(
            payload["platform"],
            {
                "operating_system": "macOS",
                "minimum_version": "15.0",
                "machine": "arm64",
                "python": "3.12",
                "observed_compatible_machine": "macOS 15.7.5 arm64 CPython 3.12.13",
            },
        )
        self.assertEqual(
            payload["authority"],
            {
                "production_activation": False,
                "runtime_install_authorized": False,
                "live_adapter_allowed": False,
                "credentials_allowed": False,
                "network_allowed_during_sandbox_runtime": False,
                "broker_requests_allowed": False,
                "real_orders_allowed": False,
                "production_state_writes_allowed": False,
            },
        )

    def test_builder_binds_frozen_lock_and_all_distribution_hashes(self):
        payload = self.payload()
        lock_path = ROOT / payload["transitive_lock"]["path"]
        self.assertEqual(payload["transitive_lock"]["format"], "uv.lock")
        self.assertEqual(payload["transitive_lock"]["version"], 1)
        self.assertEqual(
            payload["transitive_lock"]["file_sha256"],
            hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        )
        distributions = payload["transitive_lock"]["distributions"]
        self.assertGreater(len(distributions), 1)
        self.assertEqual(
            [item["name"] for item in distributions],
            sorted(item["name"] for item in distributions),
        )
        for item in distributions:
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(item["size"], 0)
            self.assertTrue(item["filename"])

    def test_config_and_package_schemas_are_exact_mirrors(self):
        self.assertEqual(SCHEMA_PATH.read_bytes(), PACKAGE_SCHEMA_PATH.read_bytes())
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(self.payload())

    def test_committed_artifact_is_exact_canonical_builder_output(self):
        expected = canonical_json(self.payload()).encode("utf-8") + b"\n"
        self.assertEqual(ARTIFACT.read_bytes(), expected)

    def test_committed_exact_bytes_replay_through_owner_only_loader(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / ARTIFACT.name
            path.write_bytes(ARTIFACT.read_bytes())
            path.chmod(0o600)
            self.assertEqual(
                load_nautilus_sandbox_dependency_lock(path),
                self.payload(),
            )

    def test_loader_accepts_only_canonical_owner_only_regular_file(self):
        payload = self.payload()
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "dependency-lock.json"
            path.write_text(canonical_json(payload), encoding="utf-8")
            path.chmod(0o600)
            loaded = load_nautilus_sandbox_dependency_lock(path)
        self.assertEqual(loaded, payload)

    def test_loader_rejects_mutation_permissions_and_symlink(self):
        payload = self.payload()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "dependency-lock.json"
            path.write_text(canonical_json(payload), encoding="utf-8")
            path.chmod(0o600)

            changed = copy.deepcopy(payload)
            changed["wheel"]["sha256"] = "f" * 64
            path.write_text(canonical_json(changed), encoding="utf-8")
            with self.assertRaisesRegex(
                NautilusSandboxDependencyError, "DEPENDENCY_LOCK_SEMANTIC_MISMATCH"
            ):
                load_nautilus_sandbox_dependency_lock(path)

            path.write_text(canonical_json(payload), encoding="utf-8")
            path.chmod(0o620)
            with self.assertRaisesRegex(
                NautilusSandboxDependencyError, "DEPENDENCY_LOCK_UNSAFE_FILE"
            ):
                load_nautilus_sandbox_dependency_lock(path)

            path.chmod(0o600)
            link = root / "dependency-lock-link.json"
            link.symlink_to(path)
            with self.assertRaisesRegex(
                NautilusSandboxDependencyError, "DEPENDENCY_LOCK_UNSAFE_FILE"
            ):
                load_nautilus_sandbox_dependency_lock(link)

    def test_verifier_rejects_incompatible_machine_and_changed_lockfile(self):
        payload = self.payload()
        with self.assertRaisesRegex(
            NautilusSandboxDependencyError, "DEPENDENCY_LOCK_PLATFORM_MISMATCH"
        ):
            verify_nautilus_sandbox_dependency_lock(
                payload, workspace_root=ROOT, machine="x86_64", macos_version="15.7.5"
            )
        changed = copy.deepcopy(payload)
        changed["transitive_lock"]["file_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            NautilusSandboxDependencyError, "DEPENDENCY_LOCK_SEMANTIC_MISMATCH"
        ):
            verify_nautilus_sandbox_dependency_lock(
                changed, workspace_root=ROOT, machine="arm64", macos_version="15.7.5"
            )

    def test_root_package_remains_python39_and_nautilus_free(self):
        root_pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements.lock").read_text(encoding="utf-8")
        self.assertIn('requires-python = ">=3.9"', root_pyproject)
        self.assertNotIn("nautilus", root_pyproject.lower())
        self.assertNotIn("nautilus", requirements.lower())
        for path in (ROOT / "src" / "crypto_quant").glob("*.py"):
            self.assertNotIn("import nautilus_trader", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
