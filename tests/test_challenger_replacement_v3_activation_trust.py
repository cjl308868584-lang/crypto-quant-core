import json
import hashlib
import os
import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crypto_quant.canonical import canonical_json, stable_id
from crypto_quant.evidence import artifact_self_hash
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


class ChallengerReplacementV3ActivationTrustTests(unittest.TestCase):
    def test_v0787_paths_use_new_target_and_recovery_root(self):
        from crypto_quant import challenger_replacement_v3_activation_trust as trust

        paths = trust.activation_paths()
        self.assertTrue(paths["contract"].endswith(
            "challenger-replacement-v3-install-contract-v0.78.7.json"
        ))
        self.assertTrue(paths["candidate_plist"].endswith(
            "local.crypto-quant.challenger-replacement-v1-v0.78.7.plist"
        ))
        self.assertTrue(paths["preflight_root"].endswith(
            "preflight-receipts-v0.78.7"
        ))
        self.assertTrue(paths["install_receipt_root"].endswith(
            "install-receipts-v0.78.7"
        ))
        self.assertTrue(paths["recovery_receipt_root"].endswith(
            "partial-install-recovery-receipts-v0.78.7"
        ))
        self.assertEqual(
            paths["target_plist"],
            "/Users/chenm4/Library/LaunchAgents/"
            "local.crypto-quant.challenger-replacement-v1-v0.78.7.plist",
        )

    def test_renderer_supersedes_v0783_candidate_without_mutating_history(self):
        from crypto_quant import challenger_replacement_v3_activation_trust as trust
        from crypto_quant.challenger_replacement_install_trust import (
            ReplacementInstallTrustError,
        )

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            runtime = Path(temporary) / "challenger-replacement-v1"
            deployment = runtime / "deployment"
            old_paths = {
                "contract": deployment
                / "challenger-replacement-v3-install-contract-v1.json",
                "candidate_plist": deployment
                / "local.crypto-quant.challenger-replacement-v1.plist",
                "preflight": deployment / "preflight-receipts" / "failed.json",
                "install": deployment / "install-receipts" / "failed.json",
            }
            for path, body in (
                (old_paths["contract"], b"v0.78.3 contract"),
                (old_paths["candidate_plist"], b"v0.78.3 plist"),
                (old_paths["preflight"], b"v0.78.3 preflight"),
                (old_paths["install"], b"v0.78.3 install"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.parent.chmod(0o700)
                path.write_bytes(body)
                path.chmod(0o600)
            runtime.chmod(0o700)
            original = {
                name: (path.read_bytes(), os.stat(path, follow_symlinks=False))
                for name, path in old_paths.items()
            }
            paths = dict(trust.replacement_install_paths())
            paths.update({
                "runtime_root": str(runtime),
                "deployment_root": str(deployment),
                "contract": str(old_paths["contract"]),
                "candidate_plist": str(old_paths["candidate_plist"]),
                "preflight_root": str(old_paths["preflight"].parent),
                "install_receipt_root": str(old_paths["install"].parent),
                "start_receipt_root": str(runtime / "evidence/start-receipts"),
                "event_root": str(runtime / "state/challenger-replacement-events-v1"),
                "stdout": str(runtime / "log/challenger-replacement-v3.stdout.log"),
                "stderr": str(runtime / "log/challenger-replacement-v3.stderr.log"),
                "target_plist": str(runtime / "target.plist"),
            })
            python = {
                "path": "/usr/bin/python3", "device": 1, "inode": 2,
                "owner_uid": 0, "mode": 0o555, "link_count": 1,
                "size_bytes": 1, "sha256": "a" * 64, "sys_version": "3.9",
                "import_stdout_sha256": "b" * 64,
                "import_stderr_sha256": "c" * 64,
            }
            release = {
                "tag": "v0.78.7", "peeled_commit": "d" * 40,
                "tag_object": "e" * 40, "manifest_version": "1.79.0",
                "manifest_hash": "f" * 64,
                "manifest_file_sha256": "0" * 64,
            }
            with patch.object(trust, "_RELEASE", {
                "tag": "v0.78.7", "package_version": "0.78.7",
            }), patch.object(trust, "replacement_install_paths", return_value=paths), \
                    patch.object(trust, "_released_identity", return_value=release), \
                    patch.object(trust, "_fixed_python_identity", return_value=python):
                rendered = trust.render_fixed_v3_activation_candidate()

            expected = {
                "contract": deployment
                / "challenger-replacement-v3-install-contract-v0.78.7.json",
                "candidate_plist": deployment
                / "local.crypto-quant.challenger-replacement-v1-v0.78.7.plist",
                "preflight_root": deployment / "preflight-receipts-v0.78.7",
                "install_receipt_root": deployment / "install-receipts-v0.78.7",
                "recovery_receipt_root": deployment / "partial-install-recovery-receipts-v0.78.7",
            }
            self.assertEqual(rendered["contract"]["paths"]["contract"],
                             str(expected["contract"]))
            self.assertEqual(rendered["contract"]["paths"]["candidate_plist"],
                             str(expected["candidate_plist"]))
            self.assertEqual(rendered["contract"]["paths"]["preflight_root"],
                             str(expected["preflight_root"]))
            self.assertEqual(rendered["contract"]["paths"]["install_receipt_root"],
                             str(expected["install_receipt_root"]))
            self.assertTrue(all(path.is_file() or path.is_dir()
                                for path in expected.values()))
            self.assertFalse(Path(paths["target_plist"]).exists())
            self.assertEqual(os.listdir(paths["event_root"]), [])
            self.assertFalse((runtime / "credentials").exists())
            with patch.object(trust, "_RELEASE", {
                "tag": "v0.78.7", "package_version": "0.78.7",
            }), patch.object(trust, "replacement_install_paths", return_value=paths), \
                    patch.object(trust, "_released_identity", return_value=release), \
                    patch.object(trust, "_fixed_python_identity", return_value=python):
                self.assertEqual(
                    trust.render_fixed_v3_activation_candidate()["plist_outcome"],
                    "ALREADY_PUBLISHED",
                )
            expected["candidate_plist"].write_bytes(b"conflicting candidate")
            with patch.object(trust, "_RELEASE", {
                "tag": "v0.78.7", "package_version": "0.78.7",
            }), patch.object(trust, "replacement_install_paths", return_value=paths), \
                    patch.object(trust, "_released_identity", return_value=release), \
                    patch.object(trust, "_fixed_python_identity", return_value=python):
                with self.assertRaisesRegex(
                    ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_CONFLICT",
                ):
                    trust.render_fixed_v3_activation_candidate()
            for name, path in old_paths.items():
                body, before = original[name]
                after = os.stat(path, follow_symlinks=False)
                self.assertEqual(path.read_bytes(), body)
                self.assertEqual(
                    (after.st_dev, after.st_ino, after.st_mode, after.st_nlink,
                     after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                    (before.st_dev, before.st_ino, before.st_mode, before.st_nlink,
                     before.st_size, before.st_mtime_ns, before.st_ctime_ns),
                )

    def test_release_scoped_receipt_directories_reject_untrusted_entries(self):
        from crypto_quant import challenger_replacement_install_trust as install

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            runtime = Path(temporary) / "challenger-replacement-v1"
            deployment = runtime / "deployment"
            paths = {
                "runtime_root": str(runtime),
                "preflight_root": str(deployment / "preflight-receipts-v0.78.7"),
                "install_receipt_root": str(deployment / "install-receipts-v0.78.7"),
                "recovery_receipt_root": str(deployment / "partial-install-recovery-receipts-v0.78.7"),
                "event_root": str(runtime / "state/challenger-replacement-events-v1"),
                "start_receipt_root": str(runtime / "evidence/start-receipts"),
            }
            for entry_type in ("symlink", "hardlink", "wrong-mode"):
                with self.subTest(entry_type=entry_type):
                    deployment.mkdir(parents=True, exist_ok=True)
                    runtime.chmod(0o700)
                    deployment.chmod(0o700)
                    receipt_root = Path(paths["preflight_root"])
                    if entry_type == "symlink":
                        target = deployment / "symlink-target"
                        target.mkdir(mode=0o700, exist_ok=True)
                        os.symlink(target.name, receipt_root)
                    elif entry_type == "hardlink":
                        target = deployment / "hardlink-target"
                        target.write_bytes(b"not a directory")
                        os.link(target, receipt_root)
                    else:
                        receipt_root.mkdir(mode=0o755)
                        receipt_root.chmod(0o755)
                    with self.assertRaises(
                        install.ReplacementInstallTrustError,
                    ):
                        install._ensure_fixed_snapshot_directories(paths)
                    if receipt_root.is_symlink() or receipt_root.is_file():
                        receipt_root.unlink()
                    elif receipt_root.exists():
                        receipt_root.rmdir()

    def test_release_tag_is_validated_before_any_path_derivation(self):
        from crypto_quant import challenger_replacement_v3_activation_trust as trust

        with patch.object(trust, "_RELEASE", {
            "tag": "v0.78.7/unsafe", "package_version": "0.78.7",
        }), patch.object(trust, "replacement_install_paths") as paths:
            with self.assertRaisesRegex(
                trust.ChallengerReplacementV3ActivationTrustError,
                "CHALLENGER_REPLACEMENT_V3_ACTIVATION_RELEASE_TAG_INVALID",
            ):
                trust.activation_paths()
        paths.assert_not_called()

    def test_release_tag_rejects_leading_zero_numeric_components(self):
        from crypto_quant import challenger_replacement_v3_activation_trust as trust

        for tag in ("v01.2.3", "v1.02.3", "v1.2.03"):
            with self.subTest(tag=tag), patch.object(trust, "_RELEASE", {
                "tag": tag, "package_version": "0.78.6",
            }), patch.object(trust, "replacement_install_paths", return_value={
                "deployment_root": "/fixed/deployment", "runtime_root": "/fixed",
            }) as paths:
                with self.assertRaisesRegex(
                    trust.ChallengerReplacementV3ActivationTrustError,
                    "CHALLENGER_REPLACEMENT_V3_ACTIVATION_RELEASE_TAG_INVALID",
                ):
                    trust.activation_paths()
            paths.assert_not_called()

    def test_release_identity_binds_current_v0787_main_and_annotated_tag(self):
        from crypto_quant import challenger_replacement_v3_activation_trust as trust

        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            config = repository / "config"
            config.mkdir()
            manifest = json.loads((
                ROOT / "config/evaluator-build-manifest-v1.json"
            ).read_text())
            manifest["package_version"] = "0.78.7"
            manifest["manifest_version"] = "1.79.0"
            manifest["manifest_hash"] = "0" * 64
            manifest["manifest_hash"] = artifact_self_hash(
                manifest, "manifest_hash"
            )
            body = canonical_json(manifest).encode()
            (config / "evaluator-build-manifest-v1.json").write_bytes(body)
            commit = b"a" * 40 + b"\n"
            commands = iter((
                (commit, b""), (commit, b""), (commit, b""),
                (b"b" * 40 + b"\n", b""), (b"tag\n", b""),
                (b"", b""),
            ))
            observed = []

            def run_fixed(argv, *, cwd):
                observed.append((argv, cwd))
                return next(commands)

            with patch.object(trust, "_REPOSITORY", repository), \
                    patch.object(
                        trust, "_run_fixed_command",
                        side_effect=run_fixed,
                    ):
                release = trust._released_identity()

            for values in (
                (commit, b"c" * 40 + b"\n", commit,
                 b"b" * 40 + b"\n", b"tag\n", b""),
                (commit, commit, b"c" * 40 + b"\n",
                 b"b" * 40 + b"\n", b"tag\n", b""),
                (commit, commit, commit,
                 b"b" * 40 + b"\n", b"commit\n", b""),
                (commit, commit, commit,
                 b"b" * 40 + b"\n", b"tag\n", b" M file\n"),
            ):
                results = iter((value, b"") for value in values)
                with patch.object(trust, "_REPOSITORY", repository), \
                        patch.object(
                            trust, "_run_fixed_command",
                            side_effect=lambda *args, **kwargs: next(results),
                        ), self.assertRaises(
                            trust.ChallengerReplacementV3ActivationTrustError
                        ):
                    trust._released_identity()

        self.assertEqual(release["tag"], "v0.78.7")
        self.assertEqual(release["peeled_commit"], "a" * 40)
        self.assertEqual(release["tag_object"], "b" * 40)
        self.assertEqual(release["manifest_version"], "1.79.0")
        self.assertEqual(
            release["manifest_file_sha256"], hashlib.sha256(body).hexdigest()
        )
        self.assertEqual([item[0] for item in observed], [
            ("git", "rev-parse", "HEAD"),
            ("git", "rev-parse", "origin/main"),
            ("git", "rev-parse", "v0.78.7^{}"),
            ("git", "rev-parse", "v0.78.7"),
            ("git", "cat-file", "-t", "v0.78.7"),
            ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        ])
        self.assertTrue(all(item[1] == repository for item in observed))

    def test_snapshot_inventory_uses_current_release_bytes_for_v076_key_set(self):
        from crypto_quant.challenger_replacement_v3_activation_trust import (
            build_fixed_v3_activation_candidate,
        )

        inventory = build_fixed_v3_activation_candidate()["snapshot_inventory"]
        mismatches = {
            name for name, digest in inventory.items()
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
        }
        self.assertEqual(mismatches, set())

    def test_snapshot_inventory_is_executable_public_runtime_import_closure(self):
        from crypto_quant.challenger_replacement_v3_activation_trust import (
            build_fixed_v3_activation_candidate,
        )

        inventory = build_fixed_v3_activation_candidate()["snapshot_inventory"]
        required = {
            "src/crypto_quant/challenger_replacement_install.py",
            "src/crypto_quant/challenger_replacement_install_preflight.py",
            "src/crypto_quant/challenger_replacement_preflight.py",
            "src/crypto_quant/system_paper_launchctl.py",
        }
        self.assertEqual(required - set(inventory), set())
        target_identity = (
            platform.system() == "Darwin"
            and platform.machine() == "arm64"
            and sys.version_info[:2] == (3, 9)
        )
        if not target_identity:
            self.skipTest(
                "release snapshot native import requires Darwin arm64 Python 3.9"
            )
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            for name in inventory:
                destination = target / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / name).read_bytes())
            environment = os.environ.copy()
            vendor_paths = (
                str(target / "vendor/challenger-replacement-v3"),
            ) + tuple(str(target / "vendor/challenger-replacement-v3/wheels" / name)
                      for name in build_fixed_v3_activation_candidate.__globals__["_VENDOR_WHEELS"])
            environment.update({
                "PYTHONPATH": os.pathsep.join(vendor_paths + (str(target / "src"),)),
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
            })
            result = subprocess.run(
                [sys.executable, "-s", "-c", (
                    "import crypto_quant.challenger_replacement_v3_activation_install;"
                    "import crypto_quant.challenger_replacement_v3_installed_runtime"
                )],
                env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_fixed_candidate_binds_releases_and_excludes_private_execution(self):
        from crypto_quant.challenger_replacement_v3_activation_trust import (
            build_fixed_v3_activation_candidate,
        )

        candidate = build_fixed_v3_activation_candidate()
        self.assertEqual(candidate["release"]["tag"], "v0.78.7")
        self.assertEqual(candidate["predecessor_release"]["tag"], "v0.77.0")
        self.assertEqual(candidate["deployment"]["release_tag"], "v0.76.0")
        self.assertLessEqual(len(candidate["snapshot_inventory"]), 256)
        forbidden = (
            "binance_private", "private_protocol", "private_runtime",
            "canary_controller", "credential_envelope",
        )
        self.assertFalse(any(
            any(word in path.lower() for word in forbidden)
            for path in candidate["snapshot_inventory"]
        ))
        self.assertEqual(
            candidate["runtime_module"],
            "crypto_quant.challenger_replacement_v3_installed_runtime",
        )
        self.assertFalse(candidate["authority"]["production_activation"])
        self.assertFalse(candidate["authority"]["real_orders_allowed"])
        self.assertIn(
            "src/crypto_quant/challenger_replacement_v3_activation_trust_cli.py",
            candidate["snapshot_inventory"],
        )

    def test_candidate_loader_requires_exact_canonical_local_identity(self):
        from crypto_quant.challenger_replacement_v3_activation_trust import (
            ChallengerReplacementV3ActivationTrustError,
            build_fixed_v3_activation_candidate,
            load_fixed_v3_activation_candidate,
        )

        candidate = build_fixed_v3_activation_candidate()
        body = canonical_json(candidate).encode()
        self.assertEqual(load_fixed_v3_activation_candidate(body), candidate)
        with self.assertRaises(ChallengerReplacementV3ActivationTrustError):
            load_fixed_v3_activation_candidate(body + b"\n")

    def test_three_schema_mirrors_are_exact_and_closed(self):
        names = (
            "challenger-replacement-v3-install-contract-v1.schema.json",
            "challenger-replacement-v3-activation-preflight-v1.schema.json",
            "challenger-replacement-v3-activation-install-receipt-v1.schema.json",
        )
        for name in names:
            packaged = ROOT / "src/crypto_quant/schemas" / name
            configured = ROOT / "config" / name
            self.assertEqual(packaged.read_bytes(), configured.read_bytes())
            schema = json.loads(packaged.read_text())
            self.assertFalse(schema["additionalProperties"])

    def test_renderer_uses_existing_secure_snapshot_and_exact_publish_only(self):
        from crypto_quant import challenger_replacement_v3_activation_trust as trust

        candidate = trust.build_fixed_v3_activation_candidate()
        snapshot = {
            "outcome": "PUBLISHED", "root": "/fixed/snapshot/tree",
            "tree_hash": "a" * 64, "file_count": len(candidate["snapshot_inventory"]),
            "total_size_bytes": 123, "root_device": 1, "root_inode": 2,
        }
        event = {
            "path": trust.activation_paths()["event_root"], "device": 3,
            "inode": 4, "owner_uid": 501, "mode": 448,
            "initial_event_count": 0, "initial_orphan_staging_count": 0,
        }
        python = {
            "path": "/usr/bin/python3", "device": 5, "inode": 6,
            "owner_uid": 0, "mode": 365, "link_count": 1,
            "size_bytes": 100, "sha256": "b" * 64,
            "sys_version": "3.9", "import_stdout_sha256": "1" * 64,
            "import_stderr_sha256": "2" * 64,
        }
        with patch.object(trust, "_released_identity", return_value={
            "tag": "v0.78.7", "peeled_commit": "c" * 40,
            "manifest_version": "1.79.0", "manifest_hash": "d" * 64,
            "manifest_file_sha256": "e" * 64,
        }), patch.object(
            trust, "_ensure_fixed_snapshot_directories",
            return_value=Path("/fixed/snapshot"),
        ), patch.object(
            trust, "_publish_snapshot_from_inventory", return_value=snapshot,
        ) as publish_snapshot, patch.object(
            trust, "_fixed_empty_event_root_identity", return_value=event,
        ), patch.object(
            trust, "_fixed_python_identity", return_value=python,
        ) as python_identity, patch.object(
            trust, "_publish_contract_exact",
            side_effect=(("PUBLISHED", object()), ("PUBLISHED", object())),
        ) as publish_exact:
            rendered = trust.render_fixed_v3_activation_candidate()
        publish_snapshot.assert_called_once()
        self.assertEqual(publish_exact.call_count, 2)
        self.assertEqual(rendered["contract"]["snapshot"]["tree_hash"], "a" * 64)
        self.assertEqual(rendered["contract"]["release"]["peeled_commit"], "c" * 40)
        self.assertEqual(rendered["contract_outcome"], "PUBLISHED")
        self.assertNotIn("allow_user_site", python_identity.call_args.kwargs)
        self.assertEqual(
            python_identity.call_args.kwargs["dependency_modules"], trust._DEPENDENCIES
        )
        self.assertEqual(
            python_identity.call_args.kwargs["dependency_versions"],
            trust._DEPENDENCY_VERSIONS,
        )
        self.assertEqual(
            python_identity.call_args.kwargs["python_paths"],
            trust._snapshot_python_paths("/fixed/snapshot/tree"),
        )
        self.assertEqual(
            rendered["contract"]["runtime"]["environment"]["PYTHONNOUSERSITE"], "1"
        )

    def test_renderer_encodes_large_filesystem_identities_as_decimal_strings(self):
        from crypto_quant import challenger_replacement_v3_activation_trust as trust

        large = 2**60 + 123
        candidate = trust.build_fixed_v3_activation_candidate()
        snapshot = {
            "outcome": "PUBLISHED", "root": "/fixed/snapshot/tree",
            "tree_hash": "a" * 64,
            "file_count": len(candidate["snapshot_inventory"]),
            "total_size_bytes": 123,
            "root_device": large + 1, "root_inode": large + 2,
        }
        event = {
            "path": trust.activation_paths()["event_root"],
            "device": large + 3, "inode": large + 4,
            "owner_uid": 501, "mode": 448,
            "initial_event_count": 0, "initial_orphan_staging_count": 0,
        }
        python = {
            "path": "/usr/bin/python3",
            "device": large + 5, "inode": large + 6,
            "owner_uid": 0, "mode": 365, "link_count": 1,
            "size_bytes": 100, "sha256": "b" * 64,
            "sys_version": "3.9", "import_stdout_sha256": "1" * 64,
            "import_stderr_sha256": "2" * 64,
        }
        release = {
            "tag": "v0.78.7", "peeled_commit": "c" * 40,
            "tag_object": "f" * 40, "manifest_version": "1.79.0",
            "manifest_hash": "d" * 64, "manifest_file_sha256": "e" * 64,
        }
        with patch.object(trust, "_released_identity", return_value=release), \
                patch.object(
                    trust, "_ensure_fixed_snapshot_directories",
                    return_value=Path("/fixed/snapshot"),
                ), patch.object(
                    trust, "_publish_snapshot_from_inventory",
                    return_value=snapshot,
                ), patch.object(
                    trust, "_fixed_empty_event_root_identity",
                    return_value=event,
                ), patch.object(
                    trust, "_fixed_python_identity", return_value=python,
                ), patch.object(
                    trust, "_publish_contract_exact",
                    side_effect=(("PUBLISHED", object()), ("PUBLISHED", object())),
                ):
            contract = trust.render_fixed_v3_activation_candidate()["contract"]

        self.assertEqual(contract["snapshot"]["root_device"], str(large + 1))
        self.assertEqual(contract["snapshot"]["root_inode"], str(large + 2))
        self.assertEqual(contract["event_root"]["device"], str(large + 3))
        self.assertEqual(contract["event_root"]["inode"], str(large + 4))
        self.assertEqual(contract["python"]["device"], str(large + 5))
        self.assertEqual(contract["python"]["inode"], str(large + 6))
        canonical_json(contract)

    @unittest.skipUnless(platform.system() == "Darwin", "macOS filesystem identity")
    def test_real_macos_system_python_large_inode_is_canonicalizable(self):
        from crypto_quant.challenger_replacement_filesystem_identity import (
            _encode_filesystem_identity,
        )

        inode = os.stat("/usr/bin/python3", follow_symlinks=False).st_ino
        self.assertGreater(inode, 2**53 - 1)
        self.assertEqual(
            _encode_filesystem_identity(inode, allow_zero=False), str(inode)
        )

    def test_install_contract_loader_replays_canonical_semantics(self):
        from crypto_quant import challenger_replacement_v3_activation_trust as trust

        candidate = trust.build_fixed_v3_activation_candidate()
        snapshot = {
            "root": "/fixed/snapshot/tree", "tree_hash": "a" * 64,
            "file_count": len(candidate["snapshot_inventory"]),
            "total_size_bytes": 123, "root_device": 1, "root_inode": 2,
        }
        event = {
            "path": trust.activation_paths()["event_root"], "device": 3,
            "inode": 4, "owner_uid": 501, "mode": 448,
            "initial_event_count": 0, "initial_orphan_staging_count": 0,
        }
        release = {
            "tag": "v0.78.7", "peeled_commit": "c" * 40,
            "tag_object": "f" * 40, "manifest_version": "1.79.0",
            "manifest_hash": "d" * 64, "manifest_file_sha256": "e" * 64,
        }
        contract = trust._contract(candidate, release, snapshot, event, {
            "path": "/usr/bin/python3", "device": 5, "inode": 6,
            "owner_uid": 0, "mode": 365, "link_count": 1,
            "size_bytes": 100, "sha256": "b" * 64,
            "sys_version": "3.9", "import_stdout_sha256": "1" * 64,
            "import_stderr_sha256": "2" * 64,
        })
        body = canonical_json(contract).encode()
        schema = json.loads((
            ROOT / "src/crypto_quant/schemas/"
            "challenger-replacement-v3-install-contract-v1.schema.json"
        ).read_text())
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(contract)), [])
        self.assertEqual(trust.load_fixed_v3_install_contract_bytes(body), contract)
        self.assertEqual(contract["runtime"]["program_arguments"][1], "-s")
        for path, invalid in (
            (("snapshot", "root_device"), "00"),
            (("snapshot", "root_inode"), "01"),
            (("event_root", "device"), "+3"),
            (("event_root", "inode"), "-4"),
            (("python", "device"), " 5"),
            (("python", "inode"), str(2**64)),
        ):
            malformed = json.loads(body)
            malformed[path[0]][path[1]] = invalid
            malformed["contract_id"] = ""
            malformed["contract_hash"] = "0" * 64
            identity = {
                key: value for key, value in malformed.items()
                if key not in ("contract_id", "contract_hash")
            }
            malformed["contract_id"] = stable_id(
                "challenger_replacement_v3_install_contract", identity
            )
            malformed["contract_hash"] = artifact_self_hash(
                malformed, "contract_hash"
            )
            with self.assertRaises(
                trust.ChallengerReplacementV3ActivationTrustError,
                msg="%s.%s accepted %r" % (path[0], path[1], invalid),
            ):
                trust.load_fixed_v3_install_contract_bytes(
                    canonical_json(malformed).encode()
                )
        mutable = json.loads(body)
        mutable["runtime"]["environment"]["PYTHONPATH"] = "/tmp/mutable"
        mutable["plist"]["file_sha256"] = hashlib.sha256(
            trust._plist(mutable)
        ).hexdigest()
        identity = {
            key: value for key, value in mutable.items()
            if key not in ("contract_id", "contract_hash")
        }
        mutable["contract_id"] = stable_id(
            "challenger_replacement_v3_install_contract", identity
        )
        mutable["contract_hash"] = artifact_self_hash(mutable, "contract_hash")
        with self.assertRaises(trust.ChallengerReplacementV3ActivationTrustError):
            trust.load_fixed_v3_install_contract_bytes(canonical_json(mutable).encode())
        altered = json.loads(body)
        altered["runtime"]["module"] = "not.allowed"
        altered["contract_hash"] = "0" * 64
        with self.assertRaises(trust.ChallengerReplacementV3ActivationTrustError):
            trust.load_fixed_v3_install_contract_bytes(canonical_json(altered).encode())


if __name__ == "__main__":
    unittest.main()
