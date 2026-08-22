import copy
import hashlib
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json, stable_id
from crypto_quant.evidence import artifact_self_hash


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = (
    "challenger-replacement-install-contract-v1.schema.json",
    "challenger-replacement-install-preflight-v1.schema.json",
    "challenger-replacement-install-receipt-v1.schema.json",
    "challenger-replacement-start-receipt-v1.schema.json",
)
HASH = "a" * 64
COMMIT = "b" * 40


def temporary_workspace():
    parent = "/private/tmp" if sys.platform == "darwin" and Path("/private/tmp").is_dir() else None
    return tempfile.TemporaryDirectory(dir=parent)


def valid_contract():
    contract = {
        "$schema": "./challenger-replacement-install-contract-v1.schema.json",
        "schema_version": "1.0.0",
        "contract_id": "challenger_replacement_install_contract_" + "0" * 64,
        "contract_hash": "0" * 64,
        "predecessor_release": {
            "release_tag": "v0.67.0",
            "tag_object": "7c65c0a34cf37f4d46ed3cdd2a0278657aa3e8c5",
            "peeled_commit": "ca022edccdcbb2d28b1ea25002e5f19512795e3e",
            "package_version": "0.67.0",
            "manifest_version": "1.61.0",
            "manifest_hash": "2b72a470a2f210461a3a6753fd3d603fee9b90df76e825deea3b9bde61a26110",
            "main_ci_run": 32572208544,
        },
        "candidate_release": {
            "release_tag": "v0.68.0",
            "tag_object": COMMIT,
            "peeled_commit": COMMIT,
            "package_version": "0.68.0",
            "manifest_version": "1.62.0",
            "manifest_hash": HASH,
            "manifest_file_sha256": HASH,
            "build_input_tree_hash": HASH,
            "main_ci_run": 1,
            "main_ci_jobs": {
                "Python 3.9": "success",
                "Python 3.12": "success",
                "macOS 15 arm64": "success",
            },
        },
        "github_verification": {
            "request_count": 3,
            "repository": {
                "name_with_owner": "cjl308868584-lang/crypto-quant-core",
                "visibility": "PUBLIC",
                "admin": True,
            },
            "main_run": {
                "run_id": 1,
                "head_sha": COMMIT,
                "conclusion": "success",
            },
            "jobs": {
                "Python 3.9": "success",
                "Python 3.12": "success",
                "macOS 15 arm64": "success",
            },
            "transcripts": [
                {
                    "argv": ["gh", "fixed", str(index)],
                    "exit_code": 0,
                    "stdout_sha256": HASH,
                    "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                }
                for index in range(3)
            ],
        },
        "plan": {
            "path": "artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json",
            "file_sha256": "5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f",
            "plan_id": "challenger_replacement_plan_" + HASH,
            "plan_hash": "c9a1e5f74c52fbf23be5a1d27fd23c25f3601ed58133178fc25480391ab65705",
        },
        "deployment": {
            "path": "artifacts/challenger-replacement/challenger-replacement-deployment-v0.67.0.json",
            "file_sha256": "8e7e073e2bb23d1509884f53d19fac299d96f38e15f9773e3a0b7d0ff103bea0",
            "deployment_id": "challenger_replacement_deployment_" + HASH,
            "deployment_hash": HASH,
            "plist_sha256": HASH,
        },
        "strategy_core": {
            "release_tag": "v0.67.0",
            "peeled_commit": "ca022edccdcbb2d28b1ea25002e5f19512795e3e",
            "package_version": "0.67.0",
            "manifest_version": "1.61.0",
            "build_input_tree_hash": "5c2a98492aa45f311cea75617745ac6d1e0afe0ea2ff36a5950a0f5c00c4efa1",
            "manifest_hash": "2b72a470a2f210461a3a6753fd3d603fee9b90df76e825deea3b9bde61a26110",
            "manifest_file_sha256": "ec2ba2d48dd35676eb442ed80cd0e45a642a2b109626db2f54a25d25823a2bf8",
            "file_hashes": {
                "src/crypto_quant/challenger_replacement_decision.py": "a72a93a7aec50e6d5d8ffb9424b33eb05453fef2f9396b1dac05a665c7b6c6ec",
                "src/crypto_quant/challenger_replacement_evidence.py": "920e84a77138509f94b42b416b1ce57adc84daad0a855ab39e9ac6a44799002f",
                "src/crypto_quant/challenger_replacement_live_input.py": "84640cbf81659d05d8abdfa935e8340eb565db20bd3006641a77033d59263536",
                "src/crypto_quant/challenger_replacement_runtime.py": "fbaeb06894f0a3f0468c7382c411e4296fbc2b7e514dfcc26867a97a21eaa97f",
            },
        },
        "event_root": {
            "path": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/state/challenger-replacement-events-v1",
            "device": 1, "inode": 2, "owner_uid": 501, "mode": 448,
            "initial_event_count": 0, "initial_orphan_staging_count": 0,
        },
        "plist": {
            "path": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/deployment/local.crypto-quant.challenger-replacement-v1.plist",
            "file_sha256": "0" * 64,
        },
        "snapshot": {
            "root": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/deployment/snapshots/" + HASH,
            "tree_hash": HASH,
            "file_count": 1,
            "total_size_bytes": 1,
            "root_device": 1,
            "root_inode": 1,
        },
        "python": {
            "path": "/usr/bin/python3",
            "device": 1,
            "inode": 1,
            "owner_uid": 0,
            "mode": 365,
            "link_count": 1,
            "size_bytes": 1,
            "sha256": HASH,
            "sys_version": "3.9.6",
            "import_stdout_sha256": HASH,
            "import_stderr_sha256": hashlib.sha256(b"").hexdigest(),
        },
        "service": {
            "label": "local.crypto-quant.challenger-replacement-v1",
            "identity": "gui/501/local.crypto-quant.challenger-replacement-v1",
        },
        "paths": {
            "runtime_root": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1",
            "deployment_root": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/deployment",
            "contract": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/deployment/challenger-replacement-install-contract-v1.json",
            "candidate_plist": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/deployment/local.crypto-quant.challenger-replacement-v1.plist",
            "preflight_root": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/deployment/preflight-receipts",
            "install_receipt_root": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/deployment/install-receipts",
            "start_receipt_root": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/evidence/start-receipts",
            "event_root": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/state/challenger-replacement-events-v1",
            "stdout": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/log/challenger-replacement.stdout.log",
            "stderr": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/log/challenger-replacement.stderr.log",
            "target_plist": "/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist",
        },
        "runtime": {
            "module": "crypto_quant.challenger_replacement_installed_runtime_cli",
            "worker_id": "challenger-replacement-natural-runner-v1",
            "program_arguments": [
                "/usr/bin/python3",
                "-m",
                "crypto_quant.challenger_replacement_installed_runtime_cli",
            ],
            "working_directory": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/deployment/snapshots/" + HASH,
            "environment": {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTHONPATH": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/deployment/snapshots/" + HASH + "/src",
            },
        },
        "schedule": [{"hour": hour, "minute": 2} for hour in (0, 4, 8, 12, 16, 20)],
        "authority": {
            "production_activation": False,
            "runtime_install_authorized": True,
            "replacement_start_authorized": False,
            "real_orders_allowed": False,
        },
        "warnings": [
            "INSTALL_AUTHORIZES_BOOTSTRAP_ONLY",
            "NO_KICKSTART_OR_MANUAL_RUNTIME",
            "NO_CREDENTIAL_BROKER_OR_ORDER_AUTHORITY",
            "START_RECEIPT_NOT_YET_AVAILABLE",
        ],
    }
    from crypto_quant.challenger_replacement_deployment import (
        render_challenger_replacement_install_plist,
    )
    contract["plist"]["file_sha256"] = hashlib.sha256(
        render_challenger_replacement_install_plist(contract)
    ).hexdigest()
    identity = {key: value for key, value in contract.items()
                if key not in ("contract_id", "contract_hash")}
    contract["contract_id"] = stable_id(
        "challenger_replacement_install_contract", identity
    )
    contract["contract_hash"] = artifact_self_hash(contract, "contract_hash")
    return contract


def render_fixture_contract(
    trust, *, repository, snapshot_parent, inventory, candidate_release,
    github_verification, python_identity,
):
    inventory = dict(inventory)
    for name, digest in trust.V067_STRATEGY_CORE["file_hashes"].items():
        body = (ROOT / name).read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise AssertionError("fixture strategy core drift")
        target = repository / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        target.chmod(0o600)
        inventory[name] = digest
    snapshot = trust._publish_snapshot_from_inventory(
        repository, snapshot_parent, inventory
    )
    contract = trust._build_install_contract(
        snapshot=snapshot, inventory=inventory,
        candidate_release=candidate_release,
        github_verification=github_verification,
        python_identity=python_identity,
        event_root_identity={
            **valid_contract()["event_root"],
            "path": trust.replacement_install_paths()["event_root"],
        },
    )
    body = canonical_json(contract).encode()
    trust.load_replacement_install_contract_bytes(body)
    paths = trust.replacement_install_paths()
    outcome, _ = trust._publish_contract_exact(
        Path(paths["deployment_root"]), Path(paths["contract"]).name, body
    )
    loaded = trust.load_replacement_install_contract_bytes(
        Path(paths["contract"]).read_bytes()
    )
    return {"snapshot": snapshot, "contract": loaded,
            "contract_outcome": outcome}


class ReplacementInstallTrustTests(unittest.TestCase):
    def test_fixed_foundation_and_paths(self):
        from crypto_quant.challenger_replacement_install_trust import (
            V067_FOUNDATION,
            replacement_install_paths,
        )

        self.assertEqual(V067_FOUNDATION["tag_object"],
                         "7c65c0a34cf37f4d46ed3cdd2a0278657aa3e8c5")
        self.assertEqual(V067_FOUNDATION["peeled_commit"],
                         "ca022edccdcbb2d28b1ea25002e5f19512795e3e")
        self.assertEqual(V067_FOUNDATION["main_ci_run"], 32572208544)
        paths = replacement_install_paths()
        self.assertEqual(paths["runtime_root"],
                         "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1")
        self.assertEqual(paths["target_plist"],
                         "/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist")
        self.assertEqual(paths["event_root"], paths["runtime_root"] +
                         "/state/challenger-replacement-events-v1")
        self.assertEqual(set(paths), set(valid_contract()["paths"]))

    def test_schema_mirrors_are_strict_and_valid(self):
        for name in SCHEMA_NAMES:
            config = ROOT / "config" / name
            package = ROOT / "src/crypto_quant/schemas" / name
            self.assertEqual(config.read_bytes(), package.read_bytes())
            schema = json.loads(config.read_text())
            self.assertFalse(schema["additionalProperties"])
            Draft202012Validator.check_schema(schema)

    def test_contract_loader_accepts_only_canonical_exact_identity(self):
        from crypto_quant.challenger_replacement_install_trust import (
            ReplacementInstallTrustError,
            load_replacement_install_contract_bytes,
        )

        contract = valid_contract()
        body = canonical_json(contract).encode("utf-8")
        self.assertEqual(load_replacement_install_contract_bytes(body), contract)
        altered = copy.deepcopy(contract)
        altered["unexpected"] = True
        with self.assertRaisesRegex(
            ReplacementInstallTrustError,
            "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_INVALID",
        ):
            load_replacement_install_contract_bytes(
                canonical_json(altered).encode("utf-8")
            )
        with self.assertRaisesRegex(
            ReplacementInstallTrustError,
            "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_INVALID",
        ):
            load_replacement_install_contract_bytes(body + b"\n")

    def test_contract_binds_exact_strategy_and_empty_event_root_identity(self):
        contract = valid_contract()
        self.assertEqual(contract["strategy_core"]["manifest_version"], "1.61.0")
        self.assertEqual(set(contract["strategy_core"]["file_hashes"]), {
            "src/crypto_quant/challenger_replacement_decision.py",
            "src/crypto_quant/challenger_replacement_evidence.py",
            "src/crypto_quant/challenger_replacement_live_input.py",
            "src/crypto_quant/challenger_replacement_runtime.py",
        })
        self.assertEqual(contract["event_root"], {
            "path": contract["paths"]["event_root"],
            "device": 1, "inode": 2, "owner_uid": 501, "mode": 0o700,
            "initial_event_count": 0, "initial_orphan_staging_count": 0,
        })
        self.assertEqual(contract["runtime"]["worker_id"],
                         "challenger-replacement-natural-runner-v1")

    def test_strategy_core_inventory_must_match_v067_exact_bytes(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        inventory = dict(trust.V067_STRATEGY_CORE["file_hashes"])
        trust._validate_strategy_core_inventory(inventory)
        for value in ({}, {**inventory, next(iter(inventory)): "0" * 64}):
            with self.subTest(value=value), self.assertRaisesRegex(
                trust.ReplacementInstallTrustError,
                "CHALLENGER_REPLACEMENT_STRATEGY_CORE_CHANGED",
            ):
                trust._validate_strategy_core_inventory(value)

    def test_v068_candidate_plist_is_derived_from_contract_not_v067_plist(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        contract = valid_contract()
        body = trust.render_replacement_install_plist(contract)
        value = plistlib.loads(body)
        self.assertEqual(
            value["ProgramArguments"], contract["runtime"]["program_arguments"]
        )
        self.assertEqual(
            value["WorkingDirectory"], contract["runtime"]["working_directory"]
        )
        self.assertEqual(
            value["EnvironmentVariables"], contract["runtime"]["environment"]
        )
        self.assertEqual(value["StartCalendarInterval"], [
            {"Hour": item["hour"], "Minute": item["minute"]}
            for item in contract["schedule"]
        ])
        self.assertEqual(
            hashlib.sha256(body).hexdigest(), contract["plist"]["file_sha256"]
        )
        self.assertNotEqual(
            contract["plist"]["file_sha256"], contract["deployment"]["plist_sha256"]
        )
        self.assertEqual(value["ProgramArguments"][2],
                         "crypto_quant.challenger_replacement_installed_runtime_cli")

    def test_v067_unavailable_provider_is_never_the_install_target(self):
        from crypto_quant.challenger_replacement_live_runtime_cli import (
            _load_fixed_runtime_contract,
        )
        from crypto_quant.challenger_replacement_runtime import (
            ChallengerReplacementRuntimeError,
        )

        with self.assertRaisesRegex(
            ChallengerReplacementRuntimeError,
            "CHALLENGER_REPLACEMENT_RUNTIME_CONTRACT_UNAVAILABLE",
        ):
            _load_fixed_runtime_contract()
        self.assertNotEqual(
            valid_contract()["runtime"]["module"],
            "crypto_quant.challenger_replacement_live_runtime_cli",
        )

    def test_import_does_not_create_fixed_production_paths(self):
        script = r'''
import json, os
from pathlib import Path
targets = [
    Path("/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1"),
    Path("/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist"),
]
before = [os.path.lexists(path) for path in targets]
import crypto_quant.challenger_replacement_install_trust
after = [os.path.lexists(path) for path in targets]
print(json.dumps({"before": before, "after": after}))
'''
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        observation = json.loads(result.stdout)
        self.assertEqual(observation["before"], observation["after"])

    def test_snapshot_publication_is_exact_and_idempotent(self):
        from crypto_quant.challenger_replacement_install_trust import (
            _publish_snapshot_from_inventory,
        )

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            (repository / "src/pkg").mkdir(parents=True, mode=0o700)
            snapshots.mkdir(mode=0o700)
            files = {
                "src/pkg/runtime.py": b"VALUE = 1\n",
                "manifest.json": b"{}",
            }
            for name, body in files.items():
                target = repository / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target.write_bytes(body)
                target.chmod(0o600)
            inventory = {
                name: hashlib.sha256(body).hexdigest()
                for name, body in files.items()
            }

            first = _publish_snapshot_from_inventory(
                repository, snapshots, inventory
            )
            second = _publish_snapshot_from_inventory(
                repository, snapshots, inventory
            )

            self.assertEqual(first["outcome"], "PUBLISHED")
            self.assertEqual(second["outcome"], "ALREADY_PUBLISHED")
            self.assertEqual(first["tree_hash"], second["tree_hash"])
            final = Path(first["root"])
            self.assertEqual(
                {name: (final / name).read_bytes() for name in files}, files
            )
            self.assertEqual(final.stat().st_ino, Path(second["root"]).stat().st_ino)
            self.assertEqual(
                [entry.name for entry in snapshots.iterdir()], [first["tree_hash"]]
            )

    def test_snapshot_rejects_symlink_and_hardlink_sources_without_touching_sentinel(self):
        from crypto_quant.challenger_replacement_install_trust import (
            ReplacementInstallTrustError,
            _publish_snapshot_from_inventory,
        )

        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind), temporary_workspace() as directory:
                root = Path(directory)
                repository = root / "repository"
                snapshots = root / "snapshots"
                repository.mkdir(mode=0o700)
                snapshots.mkdir(mode=0o700)
                sentinel = root / "sentinel"
                sentinel.write_bytes(b"sentinel")
                sentinel.chmod(0o600)
                candidate = repository / "candidate.py"
                if kind == "symlink":
                    candidate.symlink_to(sentinel)
                else:
                    os.link(sentinel, candidate)
                before = (
                    sentinel.read_bytes(), sentinel.stat().st_mode,
                    sentinel.stat().st_size, sentinel.stat().st_mtime_ns,
                    sentinel.stat().st_ctime_ns, sentinel.stat().st_ino,
                    sentinel.stat().st_nlink,
                )
                with self.assertRaisesRegex(
                    ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED",
                ):
                    _publish_snapshot_from_inventory(
                        repository,
                        snapshots,
                        {"candidate.py": hashlib.sha256(b"sentinel").hexdigest()},
                    )
                after = (
                    sentinel.read_bytes(), sentinel.stat().st_mode,
                    sentinel.stat().st_size, sentinel.stat().st_mtime_ns,
                    sentinel.stat().st_ctime_ns, sentinel.stat().st_ino,
                    sentinel.stat().st_nlink,
                )
                self.assertEqual(after, before)
                self.assertEqual(list(snapshots.iterdir()), [])

    def test_snapshot_partial_write_never_creates_canonical_final(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"complete")
            source.chmod(0o600)
            inventory = {"runtime.py": hashlib.sha256(b"complete").hexdigest()}
            original = trust._write_all

            def partial_then_crash(descriptor, data):
                os.write(descriptor, bytes(data[:2]))
                raise trust.ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
                )

            with mock.patch.object(trust, "_write_all", side_effect=partial_then_crash):
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED",
                ):
                    trust._publish_snapshot_from_inventory(
                        repository, snapshots, inventory
                    )
            entries = list(snapshots.iterdir())
            self.assertEqual(len(entries), 1)
            self.assertTrue(entries[0].name.startswith(".stage-snapshot-"))
            self.assertNotEqual(entries[0].name, trust._snapshot_tree_hash(inventory))
            with mock.patch.object(trust, "_write_all", wraps=original) as write:
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_ORPHAN_STAGING",
                ):
                    trust._publish_snapshot_from_inventory(
                        repository, snapshots, inventory
                    )
                write.assert_not_called()

    def test_snapshot_missing_nofollow_flag_fails_before_creating_staging(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"complete")
            source.chmod(0o600)
            inventory = {"runtime.py": hashlib.sha256(b"complete").hexdigest()}
            with mock.patch.object(os, "O_NOFOLLOW", 0):
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_INSTALL_PLATFORM_UNSUPPORTED",
                ):
                    trust._publish_snapshot_from_inventory(
                        repository, snapshots, inventory
                    )
            self.assertEqual(list(snapshots.iterdir()), [])

    def test_snapshot_fifo_source_is_rejected_without_blocking(self):
        script = r'''
import hashlib, os, sys
from pathlib import Path
from crypto_quant.challenger_replacement_install_trust import (
    ReplacementInstallTrustError, _publish_snapshot_from_inventory,
)
root = Path(sys.argv[1])
repository = root / "repository"
snapshots = root / "snapshots"
repository.mkdir(mode=0o700)
snapshots.mkdir(mode=0o700)
os.mkfifo(repository / "candidate.py", 0o600)
try:
    _publish_snapshot_from_inventory(
        repository, snapshots, {"candidate.py": hashlib.sha256(b"x").hexdigest()}
    )
except ReplacementInstallTrustError as error:
    print(error.reason_code)
    raise SystemExit(0)
raise SystemExit(9)
'''
        with temporary_workspace() as directory:
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT / "src")
            result = subprocess.run(
                [sys.executable, "-c", script, directory],
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=2,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(
                result.stdout.decode().strip(),
                "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED",
            )

    def test_snapshot_existing_symlink_final_returns_fixed_untrusted_error(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"complete")
            source.chmod(0o600)
            inventory = {"runtime.py": hashlib.sha256(b"complete").hexdigest()}
            sentinel = root / "sentinel"
            sentinel.mkdir(mode=0o700)
            final = snapshots / trust._snapshot_tree_hash(inventory)
            final.symlink_to(sentinel, target_is_directory=True)
            before = sentinel.stat()

            with self.assertRaisesRegex(
                trust.ReplacementInstallTrustError,
                "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED",
            ):
                trust._publish_snapshot_from_inventory(
                    repository, snapshots, inventory
                )
            after = sentinel.stat()
            self.assertEqual(
                (before.st_ino, before.st_mode, before.st_nlink, before.st_ctime_ns),
                (after.st_ino, after.st_mode, after.st_nlink, after.st_ctime_ns),
            )

    def test_snapshot_exact_eexist_race_confirms_durability_and_returns_already(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"complete")
            source.chmod(0o600)
            inventory = {"runtime.py": hashlib.sha256(b"complete").hexdigest()}
            original = trust._rename_noreplace

            def publish_then_report_race(directory_fd, source_name, final_name):
                original(directory_fd, source_name, final_name)
                raise FileExistsError(final_name)

            with mock.patch.object(
                trust, "_rename_noreplace", side_effect=publish_then_report_race
            ), mock.patch.object(
                trust, "_fsync_retry", wraps=trust._fsync_retry
            ) as fsync:
                result = trust._publish_snapshot_from_inventory(
                    repository, snapshots, inventory
                )
            self.assertEqual(result["outcome"], "ALREADY_PUBLISHED")
            self.assertGreaterEqual(fsync.call_count, 4)
            self.assertEqual(
                [entry.name for entry in snapshots.iterdir()],
                [trust._snapshot_tree_hash(inventory)],
            )

    def test_snapshot_revalidates_sources_after_publish(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"before")
            source.chmod(0o600)
            inventory = {"runtime.py": hashlib.sha256(b"before").hexdigest()}
            original = trust._rename_noreplace

            def publish_then_change_source(directory_fd, source_name, final_name):
                original(directory_fd, source_name, final_name)
                source.write_bytes(b"after")
                source.chmod(0o600)

            with mock.patch.object(
                trust,
                "_rename_noreplace",
                side_effect=publish_then_change_source,
            ):
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED",
                ):
                    trust._publish_snapshot_from_inventory(
                        repository, snapshots, inventory
                    )

    def test_snapshot_contract_renderer_is_exact_and_idempotent(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            deployment = root / "deployment"
            snapshots = deployment / "snapshots"
            repository.mkdir(mode=0o700)
            deployment.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"runtime")
            source.chmod(0o600)
            artifact_root = repository / "artifacts/challenger-replacement"
            artifact_root.mkdir(parents=True, mode=0o700)
            for name in (
                "challenger-replacement-plan-v0.64.0.json",
                "challenger-replacement-deployment-v0.67.0.json",
            ):
                (artifact_root / name).write_bytes(
                    (ROOT / "artifacts/challenger-replacement" / name).read_bytes()
                )
            inventory = {
                "runtime.py": hashlib.sha256(b"runtime").hexdigest(),
                **{
                    "artifacts/challenger-replacement/" + name:
                    hashlib.sha256((artifact_root / name).read_bytes()).hexdigest()
                    for name in (
                        "challenger-replacement-plan-v0.64.0.json",
                        "challenger-replacement-deployment-v0.67.0.json",
                    )
                },
            }
            fixture = valid_contract()
            paths = dict(fixture["paths"])
            paths.update({
                "runtime_root": str(root),
                "deployment_root": str(deployment),
                "contract": str(deployment / "challenger-replacement-install-contract-v1.json"),
            })
            fixture["paths"] = paths

            with mock.patch.object(
                trust, "replacement_install_paths", return_value=paths
            ):
                first = render_fixture_contract(trust,
                    repository=repository,
                    snapshot_parent=snapshots,
                    inventory=inventory,
                    candidate_release=fixture["candidate_release"],
                    github_verification=fixture["github_verification"],
                    python_identity=fixture["python"],
                )
                second = render_fixture_contract(trust,
                    repository=repository,
                    snapshot_parent=snapshots,
                    inventory=inventory,
                    candidate_release=fixture["candidate_release"],
                    github_verification=fixture["github_verification"],
                    python_identity=fixture["python"],
                )
                loaded = trust.load_replacement_install_contract_bytes(
                    Path(paths["contract"]).read_bytes()
                )
            self.assertEqual(first["contract_outcome"], "PUBLISHED")
            self.assertEqual(second["contract_outcome"], "ALREADY_PUBLISHED")
            self.assertEqual(first["contract"], loaded)
            self.assertEqual(first["contract"], second["contract"])
            self.assertEqual(first["snapshot"]["tree_hash"],
                             second["snapshot"]["tree_hash"])

    def test_fixed_contract_load_replays_snapshot_before_returning(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            deployment = root / "deployment"
            snapshots = deployment / "snapshots"
            repository.mkdir(mode=0o700)
            deployment.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            manifest_name = "config/evaluator-build-manifest-v1.json"
            manifest = canonical_json({"file_hashes": {}}).encode()
            target = repository / manifest_name
            target.parent.mkdir(mode=0o700)
            target.write_bytes(manifest)
            target.chmod(0o600)
            inventory = {manifest_name: hashlib.sha256(manifest).hexdigest()}
            snapshot = trust._publish_snapshot_from_inventory(
                repository, snapshots, inventory
            )
            contract = valid_contract()
            paths = dict(contract["paths"])
            paths.update({
                "runtime_root": str(root),
                "deployment_root": str(deployment),
                "contract": str(deployment / "contract.json"),
            })
            contract["paths"] = paths
            contract["snapshot"] = {key: snapshot[key] for key in (
                "root", "tree_hash", "file_count", "total_size_bytes",
                "root_device", "root_inode",
            )}
            contract["candidate_release"]["manifest_file_sha256"] = inventory[manifest_name]
            identity = {key: value for key, value in contract.items()
                        if key not in ("contract_id", "contract_hash")}
            contract["contract_id"] = stable_id(
                "challenger_replacement_install_contract", identity
            )
            contract["contract_hash"] = artifact_self_hash(contract, "contract_hash")
            body = canonical_json(contract).encode()
            plist_body = trust.render_replacement_install_plist(contract)
            trust._publish_contract_exact(
                deployment, Path(paths["candidate_plist"]).name, plist_body
            )
            trust._publish_contract_exact(deployment, "contract.json", body)
            with mock.patch.object(
                trust, "replacement_install_paths", return_value=paths
            ):
                self.assertEqual(trust._load_fixed_published_contract()[0], contract)
                snapshot_manifest = Path(snapshot["root"]) / manifest_name
                snapshot_manifest.write_bytes(b"{}")
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED",
                ):
                    trust._load_fixed_published_contract()

    def test_contract_bindings_are_read_from_snapshot_not_mutable_repository_paths(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            deployment = root / "deployment"
            snapshots = deployment / "snapshots"
            artifact_root = repository / "artifacts/challenger-replacement"
            artifact_root.mkdir(parents=True, mode=0o700)
            deployment.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            names = (
                "challenger-replacement-plan-v0.64.0.json",
                "challenger-replacement-deployment-v0.67.0.json",
            )
            for name in names:
                target = artifact_root / name
                target.write_bytes(
                    (ROOT / "artifacts/challenger-replacement" / name).read_bytes()
                )
                target.chmod(0o600)
            inventory = {
                "artifacts/challenger-replacement/" + name:
                hashlib.sha256((artifact_root / name).read_bytes()).hexdigest()
                for name in names
            }
            fixture = valid_contract()
            paths = dict(fixture["paths"])
            paths.update({
                "runtime_root": str(root),
                "deployment_root": str(deployment),
                "contract": str(deployment / "challenger-replacement-install-contract-v1.json"),
            })
            original_publish = trust._publish_snapshot_from_inventory

            def publish_then_replace_plan(repository_path, parent, source_inventory):
                result = original_publish(repository_path, parent, source_inventory)
                (artifact_root / names[0]).write_bytes(b"{}")
                return result

            with mock.patch.object(
                trust, "replacement_install_paths", return_value=paths
            ), mock.patch.object(
                trust, "_publish_snapshot_from_inventory",
                side_effect=publish_then_replace_plan,
            ):
                result = render_fixture_contract(trust,
                    repository=repository,
                    snapshot_parent=snapshots,
                    inventory=inventory,
                    candidate_release=fixture["candidate_release"],
                    github_verification=fixture["github_verification"],
                    python_identity=fixture["python"],
                )
            self.assertEqual(
                result["contract"]["plan"]["file_sha256"],
                inventory["artifacts/challenger-replacement/" + names[0]],
            )

    def test_renderer_cli_rejects_arguments_before_render(self):
        import crypto_quant.challenger_replacement_install_trust_cli as cli

        with mock.patch.object(cli, "render_fixed_replacement_snapshot_and_contract") as render:
            with self.assertRaises(SystemExit):
                cli.main(["--path", "/tmp/not-allowed"])
            render.assert_not_called()

    def test_fixed_renderer_uses_only_collected_release_inputs(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            deployment = root / "deployment"
            snapshots = deployment / "snapshots"
            repository.mkdir(mode=0o700)
            deployment.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"runtime")
            source.chmod(0o600)
            artifact_root = repository / "artifacts/challenger-replacement"
            artifact_root.mkdir(parents=True, mode=0o700)
            for name in (
                "challenger-replacement-plan-v0.64.0.json",
                "challenger-replacement-deployment-v0.67.0.json",
            ):
                (artifact_root / name).write_bytes(
                    (ROOT / "artifacts/challenger-replacement" / name).read_bytes()
                )
            inventory = {
                "runtime.py": hashlib.sha256(b"runtime").hexdigest(),
                **{
                    "artifacts/challenger-replacement/" + name:
                    hashlib.sha256((artifact_root / name).read_bytes()).hexdigest()
                    for name in (
                        "challenger-replacement-plan-v0.64.0.json",
                        "challenger-replacement-deployment-v0.67.0.json",
                    )
                },
            }
            for name, digest in trust.V067_STRATEGY_CORE["file_hashes"].items():
                body = (ROOT / name).read_bytes()
                target = repository / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                target.chmod(0o600)
                self.assertEqual(hashlib.sha256(body).hexdigest(), digest)
                inventory[name] = digest
            fixture = valid_contract()
            paths = dict(fixture["paths"])
            paths.update({
                "runtime_root": str(root),
                "deployment_root": str(deployment),
                "contract": str(deployment / "challenger-replacement-install-contract-v1.json"),
            })
            fixture["paths"] = paths
            with mock.patch.object(
                trust, "replacement_install_paths", return_value=paths
            ), mock.patch.object(
                trust, "_collect_fixed_release_inputs",
                return_value=(inventory, fixture["candidate_release"], fixture["github_verification"]),
            ) as collect, mock.patch.object(
                trust, "_ensure_fixed_snapshot_directories", return_value=snapshots
            ) as ensure, mock.patch.object(
                trust, "_fixed_empty_event_root_identity",
                return_value={**fixture["event_root"],
                              "path": paths["event_root"]},
            ) as event_identity, mock.patch.object(
                trust, "_fixed_python_identity", return_value=fixture["python"]
            ) as python_identity, mock.patch.object(
                trust.Path, "resolve", return_value=repository / "src/crypto_quant/challenger_replacement_install_trust.py"
            ):
                result = trust.render_fixed_replacement_snapshot_and_contract()
            collect.assert_called_once_with(repository)
            ensure.assert_called_once_with(paths)
            event_identity.assert_called_once_with(paths)
            python_identity.assert_called_once_with(result["snapshot"]["root"])
            self.assertEqual(result["plist_outcome"], "PUBLISHED")
            self.assertEqual(result["contract_outcome"], "PUBLISHED")

    def test_release_input_collector_uses_exact_three_github_reads(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            repository = Path(directory) / "repository"
            (repository / "config").mkdir(parents=True, mode=0o700)
            source = repository / "source.txt"
            source.write_bytes(b"source")
            source.chmod(0o600)
            manifest = {
                "manifest_version": "1.62.0",
                "package_version": "0.68.0",
                "build_input_tree_hash": HASH,
                "file_hashes": {"source.txt": hashlib.sha256(b"source").hexdigest()},
                "manifest_hash": "0" * 64,
            }
            manifest["manifest_hash"] = artifact_self_hash(
                manifest, "manifest_hash"
            )
            (repository / "config/evaluator-build-manifest-v1.json").write_bytes(
                canonical_json(manifest).encode("utf-8")
            )
            responses = {
                ("git", "remote", "get-url", "origin"): b"https://github.com/cjl308868584-lang/crypto-quant-core.git\n",
                ("git", "rev-parse", "HEAD"): (COMMIT + "\n").encode(),
                ("git", "rev-parse", "origin/main"): (COMMIT + "\n").encode(),
                ("git", "rev-parse", "v0.68.0^{}"): (COMMIT + "\n").encode(),
                ("git", "rev-parse", "v0.68.0"): ("c" * 40 + "\n").encode(),
                ("git", "cat-file", "-t", "v0.68.0"): b"tag\n",
                ("git", "status", "--porcelain=v1", "--untracked-files=all"): b"",
            }
            calls = []

            def command(argv, *, cwd, environment=None):
                calls.append(tuple(argv))
                if tuple(argv) in responses:
                    return responses[tuple(argv)], b""
                if tuple(argv[:3]) == ("gh", "api", "repos/cjl308868584-lang/crypto-quant-core"):
                    return json.dumps({
                        "full_name": "cjl308868584-lang/crypto-quant-core",
                        "visibility": "public",
                        "permissions": {"admin": True},
                    }).encode(), b""
                if tuple(argv[:3]) == ("gh", "run", "list"):
                    return json.dumps([{
                        "databaseId": 42,
                        "headSha": COMMIT,
                        "conclusion": "success",
                    }]).encode(), b""
                if tuple(argv[:3]) == ("gh", "run", "view"):
                    return json.dumps({"jobs": [
                        {"name": "Python 3.9", "conclusion": "success"},
                        {"name": "Python 3.12", "conclusion": "success"},
                        {"name": "macOS 15 arm64", "conclusion": "success"},
                    ]}).encode(), b""
                raise AssertionError(argv)

            with mock.patch.object(trust, "_run_fixed_command", side_effect=command):
                inventory, candidate, github = trust._collect_fixed_release_inputs(
                    repository
                )
            self.assertEqual(candidate["peeled_commit"], COMMIT)
            self.assertEqual(candidate["main_ci_run"], 42)
            self.assertEqual(github["request_count"], 3)
            self.assertEqual(sum(call[0] == "gh" for call in calls), 3)
            self.assertIn("config/evaluator-build-manifest-v1.json", inventory)

    def test_fixed_directory_creation_is_owner_only_and_idempotent(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            anchor = Path(directory) / "anchor"
            anchor.mkdir(mode=0o700)
            runtime = anchor / "challenger-replacement-v1"
            paths = {
                "runtime_root": str(runtime),
                "event_root": str(runtime / "state/challenger-replacement-events-v1"),
                "start_receipt_root": str(runtime / "evidence/start-receipts"),
                "stdout": str(runtime / "log/challenger-replacement.stdout.log"),
                "stderr": str(runtime / "log/challenger-replacement.stderr.log"),
            }
            first = trust._ensure_fixed_snapshot_directories(paths)
            first_inode = first.stat().st_ino
            second = trust._ensure_fixed_snapshot_directories(paths)
            self.assertEqual(first, second)
            self.assertEqual(first_inode, second.stat().st_ino)
            for path in (
                runtime, runtime / "deployment", first,
                runtime / "deployment/preflight-receipts",
                runtime / "deployment/install-receipts",
                runtime / "state", Path(paths["event_root"]),
                runtime / "log", runtime / "evidence",
                Path(paths["start_receipt_root"]),
            ):
                self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            identity = trust._fixed_empty_event_root_identity(paths)
            self.assertEqual(identity, {
                "path": paths["event_root"],
                "device": Path(paths["event_root"]).stat().st_dev,
                "inode": Path(paths["event_root"]).stat().st_ino,
                "owner_uid": os.getuid(), "mode": 0o700,
                "initial_event_count": 0, "initial_orphan_staging_count": 0,
            })
            self.assertFalse(Path(paths["stdout"]).exists())
            self.assertFalse(Path(paths["stderr"]).exists())

    def test_event_root_binding_rejects_any_existing_entry(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            event_root = root / "events"
            event_root.mkdir(mode=0o700)
            (event_root / "00000000000000000001.event.json").write_bytes(b"x")
            paths = {"event_root": str(event_root)}
            with self.assertRaisesRegex(
                trust.ReplacementInstallTrustError,
                "CHALLENGER_REPLACEMENT_EVENT_ROOT_NOT_EMPTY",
            ):
                trust._fixed_empty_event_root_identity(paths)

    def test_system_python_identity_records_real_link_count(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        stdout = json.dumps({
            "package_version": "0.68.0",
            "sys_version": sys.version,
        }, separators=(",", ":"), sort_keys=True).encode() + b"\n"
        with mock.patch.object(
            trust, "_run_fixed_command", return_value=(stdout, b"")
        ):
            identity = trust._fixed_python_identity("/private/fixed-snapshot")
        self.assertEqual(identity["path"], "/usr/bin/python3")
        self.assertEqual(identity["link_count"], Path("/usr/bin/python3").stat().st_nlink)
        self.assertGreaterEqual(identity["link_count"], 1)

    def test_snapshot_replay_rejects_inventory_extra_file(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"runtime")
            source.chmod(0o600)
            inventory = {"runtime.py": hashlib.sha256(b"runtime").hexdigest()}
            result = trust._publish_snapshot_from_inventory(
                repository, snapshots, inventory
            )
            extra = Path(result["root"]) / "extra.py"
            extra.write_bytes(b"extra")
            extra.chmod(0o600)
            with self.assertRaisesRegex(
                trust.ReplacementInstallTrustError,
                "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED",
            ):
                trust._publish_snapshot_from_inventory(
                    repository, snapshots, inventory
                )

    def test_snapshot_rejects_same_bytes_new_inode_source_after_publish(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"runtime")
            source.chmod(0o600)
            original_inode = source.stat().st_ino
            inventory = {"runtime.py": hashlib.sha256(b"runtime").hexdigest()}
            original_rename = trust._rename_noreplace

            def publish_then_replace_source(directory_fd, source_name, final_name):
                original_rename(directory_fd, source_name, final_name)
                replacement = repository / "replacement"
                replacement.write_bytes(b"runtime")
                replacement.chmod(0o600)
                os.replace(replacement, source)

            with mock.patch.object(
                trust, "_rename_noreplace", side_effect=publish_then_replace_source
            ):
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED",
                ):
                    trust._publish_snapshot_from_inventory(
                        repository, snapshots, inventory
                    )
            self.assertNotEqual(original_inode, source.stat().st_ino)

    def test_snapshot_file_fsync_failure_leaves_only_noncanonical_staging(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"runtime")
            source.chmod(0o600)
            inventory = {"runtime.py": hashlib.sha256(b"runtime").hexdigest()}
            with mock.patch.object(
                trust, "_fsync_retry",
                side_effect=trust.ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_FSYNC_FAILED"
                ),
            ):
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_FSYNC_FAILED",
                ):
                    trust._publish_snapshot_from_inventory(
                        repository, snapshots, inventory
                    )
            entries = list(snapshots.iterdir())
            self.assertEqual(len(entries), 1)
            self.assertTrue(entries[0].name.startswith(".stage-snapshot-"))

    def test_snapshot_dir_fsync_failure_is_confirmed_by_exact_retry(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"runtime")
            source.chmod(0o600)
            inventory = {"runtime.py": hashlib.sha256(b"runtime").hexdigest()}
            original_rename = trust._rename_noreplace
            original_fsync = trust._fsync_retry
            renamed = {"value": False}

            def rename(directory_fd, source_name, final_name):
                original_rename(directory_fd, source_name, final_name)
                renamed["value"] = True

            def fsync(descriptor):
                if renamed["value"]:
                    renamed["value"] = False
                    raise trust.ReplacementInstallTrustError(
                        "CHALLENGER_REPLACEMENT_SNAPSHOT_FSYNC_FAILED"
                    )
                return original_fsync(descriptor)

            with mock.patch.object(trust, "_rename_noreplace", side_effect=rename), \
                    mock.patch.object(trust, "_fsync_retry", side_effect=fsync):
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_FSYNC_FAILED",
                ):
                    trust._publish_snapshot_from_inventory(
                        repository, snapshots, inventory
                    )
            result = trust._publish_snapshot_from_inventory(
                repository, snapshots, inventory
            )
            self.assertEqual(result["outcome"], "ALREADY_PUBLISHED")

    def test_snapshot_no_replace_unsupported_never_reports_success(self):
        import errno
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"runtime")
            source.chmod(0o600)
            inventory = {"runtime.py": hashlib.sha256(b"runtime").hexdigest()}
            with mock.patch.object(
                trust, "_rename_noreplace",
                side_effect=OSError(errno.ENOSYS, "unsupported"),
            ):
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_INSTALL_PLATFORM_UNSUPPORTED",
                ):
                    trust._publish_snapshot_from_inventory(
                        repository, snapshots, inventory
                    )
            self.assertFalse((snapshots / trust._snapshot_tree_hash(inventory)).exists())

    def test_snapshot_rejects_repository_root_rename_and_recreation(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"runtime")
            source.chmod(0o600)
            inventory = {"runtime.py": hashlib.sha256(b"runtime").hexdigest()}
            original = trust._rename_noreplace

            def publish_then_replace_root(directory_fd, source_name, final_name):
                original(directory_fd, source_name, final_name)
                repository.rename(root / "old-repository")
                repository.mkdir(mode=0o700)
                replacement = repository / "runtime.py"
                replacement.write_bytes(b"runtime")
                replacement.chmod(0o600)

            with mock.patch.object(
                trust, "_rename_noreplace", side_effect=publish_then_replace_root
            ):
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED",
                ):
                    trust._publish_snapshot_from_inventory(
                        repository, snapshots, inventory
                    )

    def test_snapshot_rejects_parent_rename_and_recreation(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            root = Path(directory)
            repository = root / "repository"
            snapshots = root / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            source = repository / "runtime.py"
            source.write_bytes(b"runtime")
            source.chmod(0o600)
            inventory = {"runtime.py": hashlib.sha256(b"runtime").hexdigest()}
            original = trust._rename_noreplace

            def publish_then_replace_parent(directory_fd, source_name, final_name):
                original(directory_fd, source_name, final_name)
                snapshots.rename(root / "old-snapshots")
                snapshots.mkdir(mode=0o700)

            with mock.patch.object(
                trust, "_rename_noreplace", side_effect=publish_then_replace_parent
            ):
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_PATH_UNTRUSTED",
                ):
                    trust._publish_snapshot_from_inventory(
                        repository, snapshots, inventory
                    )

    def test_contract_publisher_rejects_special_existing_final_without_side_effects(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        for kind in ("symlink", "hardlink", "fifo", "directory"):
            with self.subTest(kind=kind), temporary_workspace() as directory:
                parent = Path(directory) / "deployment"
                parent.mkdir(mode=0o700)
                sentinel = Path(directory) / "sentinel"
                sentinel.write_bytes(b"sentinel")
                sentinel.chmod(0o600)
                final = parent / "contract.json"
                if kind == "symlink":
                    final.symlink_to(sentinel)
                elif kind == "hardlink":
                    os.link(sentinel, final)
                elif kind == "fifo":
                    os.mkfifo(final, 0o600)
                else:
                    final.mkdir(mode=0o700)
                before = (
                    sentinel.read_bytes(), sentinel.stat().st_mode,
                    sentinel.stat().st_size, sentinel.stat().st_mtime_ns,
                    sentinel.stat().st_ctime_ns, sentinel.stat().st_ino,
                    sentinel.stat().st_nlink,
                )
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_UNTRUSTED",
                ):
                    trust._publish_contract_exact(
                        parent, "contract.json", b"trusted"
                    )
                after = (
                    sentinel.read_bytes(), sentinel.stat().st_mode,
                    sentinel.stat().st_size, sentinel.stat().st_mtime_ns,
                    sentinel.stat().st_ctime_ns, sentinel.stat().st_ino,
                    sentinel.stat().st_nlink,
                )
                self.assertEqual(after, before)

    def test_contract_partial_write_leaves_only_orphan_staging(self):
        import crypto_quant.challenger_replacement_install_trust as trust

        with temporary_workspace() as directory:
            parent = Path(directory) / "deployment"
            parent.mkdir(mode=0o700)

            def partial(descriptor, data):
                os.write(descriptor, bytes(data[:1]))
                raise trust.ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
                )

            with mock.patch.object(trust, "_write_all", side_effect=partial):
                with self.assertRaisesRegex(
                    trust.ReplacementInstallTrustError,
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED",
                ):
                    trust._publish_contract_exact(
                        parent, "contract.json", b"trusted"
                    )
            entries = list(parent.iterdir())
            self.assertEqual(len(entries), 1)
            self.assertTrue(entries[0].name.startswith(".stage-contract-"))
            with self.assertRaisesRegex(
                trust.ReplacementInstallTrustError,
                "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_ORPHAN_STAGING",
            ):
                trust._publish_contract_exact(
                    parent, "contract.json", b"trusted"
                )


if __name__ == "__main__":
    unittest.main()
