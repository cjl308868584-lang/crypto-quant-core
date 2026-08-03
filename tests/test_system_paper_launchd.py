"""Release snapshot and non-installing LaunchAgent contract tests."""

import hashlib
import io
import json
import os
import plistlib
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from crypto_quant.canonical import business_hash, canonical_json, stable_id
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.system_paper_launchd import (
    SystemPaperLaunchdError,
    load_system_paper_launchd_contract,
    publish_system_paper_launchd_contract,
)
from crypto_quant.system_paper_launchd_cli import main as launchd_main


ROOT = Path(__file__).resolve().parents[1]
RELEASE_COMMIT = "8" * 40
FOUNDATION_COMMIT = "6b103a5d962ca53c470f08573418be73929b63a7"
CREATED_AT = "2026-08-04T04:00:00.000Z"
PYTHON_EXECUTABLE = Path(sys.executable).resolve()


class ReleaseCommandRunner:
    def __init__(self, overrides=None):
        self.overrides = overrides or {}
        self.calls = []

    def __call__(self, argv, *, cwd=None, env=None):
        command = tuple(str(item) for item in argv)
        self.calls.append((command, None if cwd is None else str(cwd), env))
        if command in self.overrides:
            value = self.overrides[command]
            if isinstance(value, tuple):
                return SimpleNamespace(
                    returncode=value[0], stdout=value[1], stderr=value[2]
                )
            return SimpleNamespace(returncode=0, stdout=value, stderr="")
        if command == ("git", "status", "--porcelain=v1"):
            stdout = ""
        elif command == ("git", "rev-parse", "HEAD"):
            stdout = RELEASE_COMMIT + "\n"
        elif command == ("git", "cat-file", "-t", "v0.58.0"):
            stdout = "tag\n"
        elif command == ("git", "rev-parse", "v0.58.0^{}"):
            stdout = RELEASE_COMMIT + "\n"
        elif command == ("git", "rev-parse", "v0.57.0^{}"):
            stdout = FOUNDATION_COMMIT + "\n"
        elif command == (
            "git",
            "merge-base",
            "--is-ancestor",
            "v0.57.0",
            "HEAD",
        ):
            stdout = ""
        elif command == ("git", "remote", "get-url", "origin"):
            stdout = (
                "https://github.com/cjl308868584-lang/crypto-quant-core.git\n"
            )
        elif command == (
            "git",
            "ls-remote",
            "origin",
            "refs/heads/main",
        ):
            stdout = RELEASE_COMMIT + "\trefs/heads/main\n"
        elif command[0] == str(PYTHON_EXECUTABLE) and command[1] == "-c":
            if "json.dumps" in command[2]:
                stdout = canonical_json(
                    {
                        "package_version": "0.58.0",
                        "sys_version": sys.version,
                    }
                ) + "\n"
            else:
                stdout = "SYSTEM_PAPER_SNAPSHOT_IMPORT_OK\n"
        else:
            return SimpleNamespace(
                returncode=99,
                stdout="",
                stderr="unexpected command: " + repr(command),
            )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def write_file(path, body):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    data = body if isinstance(body, bytes) else body.encode("utf-8")
    path.write_bytes(data)
    os.chmod(path, 0o600)


def fake_release_repository(root):
    repository = (Path(root).resolve() / "release-repository")
    repository.mkdir(mode=0o700)
    files = {
        "pyproject.toml": '[project]\nname = "crypto-quant-core"\nversion = "0.58.0"\n',
        "setup.py": 'setup(name="crypto-quant-core", version="0.58.0")\n',
        "requirements.lock": "jsonschema==4.25.1\n",
        "src/crypto_quant/__init__.py": '__version__ = "0.58.0"\n',
        "src/crypto_quant/system_paper_runtime_cli.py": "VALUE = 'runtime-cli'\n",
        "src/crypto_quant/system_paper_launchd.py": "VALUE = 'launchd'\n",
        "src/crypto_quant/system_paper_launchd_cli.py": "VALUE = 'launchd-cli'\n",
        "config/evaluator-build-manifest-v1.schema.json": (
            ROOT / "config" / "evaluator-build-manifest-v1.schema.json"
        ).read_bytes(),
        "config/system-paper-launchd-contract-v1.schema.json": "{}\n",
        "src/crypto_quant/schemas/system-paper-launchd-contract-v1.schema.json": "{}\n",
    }
    for relative, body in files.items():
        write_file(repository / relative, body)
    hashes = {
        relative: hashlib.sha256((repository / relative).read_bytes()).hexdigest()
        for relative in sorted(files)
    }
    manifest = json.loads(
        (ROOT / "config" / "evaluator-build-manifest-v1.json").read_text(
            encoding="utf-8"
        )
    )
    manifest["manifest_version"] = "1.52.0"
    manifest["package_version"] = "0.58.0"
    manifest["file_hashes"] = hashes
    manifest["build_input_tree_hash"] = business_hash(hashes)
    manifest["manifest_hash"] = artifact_self_hash(manifest, "manifest_hash")
    write_file(
        repository / "config" / "evaluator-build-manifest-v1.json",
        canonical_json(manifest),
    )
    return repository


class SystemPaperLaunchdTests(unittest.TestCase):
    def publish(self, base, *, runner=None):
        root = Path(base).resolve()
        repository = fake_release_repository(root)
        runtime_root = root / "system-paper-runtime"
        output_root = root / "rendered-contract"
        command_runner = runner or ReleaseCommandRunner()
        timezone = SimpleNamespace(tm_gmtoff=28800, tm_isdst=0)
        with patch(
            "crypto_quant.system_paper_launchd._timezone_link_target",
            return_value="/var/db/timezone/zoneinfo/Asia/Shanghai",
        ), patch(
            "crypto_quant.system_paper_launchd.time.localtime",
            return_value=timezone,
        ):
            result = publish_system_paper_launchd_contract(
                output_root=output_root,
                repository_root=repository,
                runtime_root=runtime_root,
                python_executable=PYTHON_EXECUTABLE,
                clock=lambda: CREATED_AT,
                _command_runner=command_runner,
            )
        return result, repository, runtime_root, output_root, command_runner

    def test_publish_replays_release_snapshot_and_fixed_launchagent(self):
        with tempfile.TemporaryDirectory() as directory:
            result, repository, runtime_root, _output, runner = self.publish(
                directory
            )
            contract = load_system_paper_launchd_contract(
                contract_path=Path(result["contract_path"]),
                plist_path=Path(result["plist_path"]),
                _command_runner=runner,
            )
            plist_bytes = Path(result["plist_path"]).read_bytes()
            plist = plistlib.loads(plist_bytes)

            self.assertEqual(result["outcome"], "GENERATED_NOT_INSTALLED")
            self.assertFalse(result["launchctl_invoked"])
            self.assertEqual(
                plist["Label"], "local.crypto-quant.system-paper-v1"
            )
            self.assertEqual(
                plist["StartCalendarInterval"],
                [
                    {"Hour": hour, "Minute": 5}
                    for hour in (0, 4, 8, 12, 16, 20)
                ],
            )
            self.assertFalse(plist["RunAtLoad"])
            self.assertFalse(contract["cadence"]["run_at_load"])
            snapshot = Path(contract["execution_snapshot"]["repository_root"])
            self.assertNotEqual(snapshot, repository)
            self.assertEqual(plist["WorkingDirectory"], str(snapshot))
            self.assertEqual(
                plist["EnvironmentVariables"],
                {"PYTHONPATH": str(snapshot / "src")},
            )
            self.assertEqual(
                plist["ProgramArguments"],
                [
                    str(PYTHON_EXECUTABLE),
                    "-m",
                    "crypto_quant.system_paper_runtime_cli",
                    "--state-path",
                    str(runtime_root / "state" / "system-paper.sqlite"),
                    "--output-root",
                    str(runtime_root / "artifacts"),
                ],
            )
            self.assertEqual(
                contract["root_paths"],
                {
                    "runtime": str(runtime_root),
                    "state": str(runtime_root / "state"),
                    "log": str(runtime_root / "log"),
                    "artifacts": str(runtime_root / "artifacts"),
                    "deployment": str(runtime_root / "deployment"),
                    "preflight_receipts": str(runtime_root / "preflight-receipts"),
                    "install_receipts": str(runtime_root / "install-receipts"),
                    "start_receipts": str(runtime_root / "start-receipts"),
                },
            )
            self.assertNotIn("challenger", plist_bytes.decode("utf-8").lower())
            self.assertEqual(contract["release"]["release_commit"], RELEASE_COMMIT)
            self.assertEqual(contract["release"]["foundation_commit"], FOUNDATION_COMMIT)
            self.assertEqual(contract["release"]["manifest_version"], "1.52.0")
            self.assertEqual(contract["release"]["package_version"], "0.58.0")
            executable_bytes = PYTHON_EXECUTABLE.read_bytes()
            executable_stat = PYTHON_EXECUTABLE.stat()
            self.assertEqual(
                contract["python_identity"],
                {
                    "path": str(PYTHON_EXECUTABLE),
                    "device": executable_stat.st_dev,
                    "inode": executable_stat.st_ino,
                    "mode": stat.S_IMODE(executable_stat.st_mode),
                    "owner_uid": executable_stat.st_uid,
                    "link_count": executable_stat.st_nlink,
                    "size_bytes": len(executable_bytes),
                    "sha256": hashlib.sha256(executable_bytes).hexdigest(),
                    "sys_version": sys.version,
                    "package_version": "0.58.0",
                    "requirements_lock_sha256": hashlib.sha256(
                        (snapshot / "requirements.lock").read_bytes()
                    ).hexdigest(),
                },
            )
            self.assertEqual(
                contract["execution_snapshot"]["file_count"],
                len(contract["execution_snapshot"]["files"]),
            )
            self.assertTrue(
                any(call[0][0] == str(PYTHON_EXECUTABLE) for call in runner.calls)
            )
            import_call = next(
                call for call in runner.calls if call[0][0] == str(PYTHON_EXECUTABLE)
            )
            self.assertEqual(
                set(import_call[2]),
                {"PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "LANG", "LC_ALL"},
            )
            manifest = json.loads(
                (snapshot / "config" / "evaluator-build-manifest-v1.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(
                {item["path"] for item in contract["execution_snapshot"]["files"]},
                set(manifest["file_hashes"])
                | {"config/evaluator-build-manifest-v1.json"},
            )
            self.assertFalse(
                any("launchctl" in part for call in runner.calls for part in call[0])
            )
            for path in (
                Path(result["contract_path"]),
                Path(result["plist_path"]),
            ):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            for path in (
                runtime_root,
                runtime_root / "state",
                runtime_root / "log",
                runtime_root / "artifacts",
                snapshot,
            ):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)

    def test_loader_is_command_free_and_rejects_python_identity_mutation(self):
        class ForbiddenRunner:
            def __call__(self, *args, **kwargs):
                raise AssertionError("production loader executed a command")

        with tempfile.TemporaryDirectory() as directory:
            result, _repository, _runtime, _output, _runner = self.publish(directory)
            contract_path = Path(result["contract_path"])
            plist_path = Path(result["plist_path"])
            loaded = load_system_paper_launchd_contract(
                contract_path=contract_path,
                plist_path=plist_path,
                _command_runner=ForbiddenRunner(),
            )
            self.assertEqual(loaded["python_identity"]["path"], str(PYTHON_EXECUTABLE))

            for field in ("device", "inode", "mode", "owner_uid", "link_count", "size_bytes", "sha256"):
                with self.subTest(field=field):
                    changed = deepcopy(loaded)
                    current = changed["python_identity"][field]
                    changed["python_identity"][field] = (
                        "f" * 64 if field == "sha256" else current + 1
                    )
                    changed["contract_hash"] = artifact_self_hash(
                        changed, "contract_hash"
                    )
                    contract_path.write_bytes(
                        canonical_json(changed).encode("utf-8")
                    )
                    os.chmod(contract_path, 0o600)
                    with self.assertRaises(SystemPaperLaunchdError):
                        load_system_paper_launchd_contract(
                            contract_path=contract_path,
                            plist_path=plist_path,
                            _command_runner=ForbiddenRunner(),
                        )
                    contract_path.write_bytes(
                        canonical_json(loaded).encode("utf-8")
                    )
                    os.chmod(contract_path, 0o600)

    def test_release_git_and_manifest_mismatches_fail_before_snapshot(self):
        cases = (
            (
                "dirty",
                {("git", "status", "--porcelain=v1"): " M source.py\n"},
            ),
            (
                "lightweight",
                {("git", "cat-file", "-t", "v0.58.0"): "commit\n"},
            ),
            (
                "foundation",
                {("git", "rev-parse", "v0.57.0^{}"): "7" * 40 + "\n"},
            ),
            (
                "foundation_not_ancestor",
                {
                    (
                        "git",
                        "merge-base",
                        "--is-ancestor",
                        "v0.57.0",
                        "HEAD",
                    ): (1, "", "not an ancestor")
                },
            ),
            (
                "origin",
                {("git", "remote", "get-url", "origin"): "https://example.invalid/x\n"},
            ),
            (
                "main",
                {
                    ("git", "ls-remote", "origin", "refs/heads/main"):
                    "7" * 40 + "\trefs/heads/main\n"
                },
            ),
        )
        for name, overrides in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                repository = fake_release_repository(root)
                runtime_root = root / "system-paper-runtime"
                timezone = SimpleNamespace(tm_gmtoff=28800, tm_isdst=0)
                with patch(
                    "crypto_quant.system_paper_launchd._timezone_link_target",
                    return_value="/zoneinfo/Asia/Shanghai",
                ), patch(
                    "crypto_quant.system_paper_launchd.time.localtime",
                    return_value=timezone,
                ), self.assertRaises(SystemPaperLaunchdError):
                    publish_system_paper_launchd_contract(
                        output_root=root / "output",
                        repository_root=repository,
                        runtime_root=runtime_root,
                        python_executable=PYTHON_EXECUTABLE,
                        clock=lambda: CREATED_AT,
                        _command_runner=ReleaseCommandRunner(overrides),
                    )
                self.assertFalse(runtime_root.exists())

    def test_manifest_version_and_package_metadata_mismatch_fail_closed(self):
        for name in ("manifest_version", "package_metadata"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                repository = fake_release_repository(root)
                manifest_path = (
                    repository / "config" / "evaluator-build-manifest-v1.json"
                )
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if name == "manifest_version":
                    manifest["manifest_version"] = "1.51.0"
                else:
                    pyproject = repository / "pyproject.toml"
                    write_file(
                        pyproject,
                        '[project]\nname = "crypto-quant-core"\nversion = "0.57.0"\n',
                    )
                    manifest["file_hashes"]["pyproject.toml"] = hashlib.sha256(
                        pyproject.read_bytes()
                    ).hexdigest()
                    manifest["build_input_tree_hash"] = business_hash(
                        manifest["file_hashes"]
                    )
                manifest["manifest_hash"] = artifact_self_hash(
                    manifest, "manifest_hash"
                )
                write_file(manifest_path, canonical_json(manifest))
                timezone = SimpleNamespace(tm_gmtoff=28800, tm_isdst=0)
                with patch(
                    "crypto_quant.system_paper_launchd._timezone_link_target",
                    return_value="/zoneinfo/Asia/Shanghai",
                ), patch(
                    "crypto_quant.system_paper_launchd.time.localtime",
                    return_value=timezone,
                ), self.assertRaises(SystemPaperLaunchdError):
                    publish_system_paper_launchd_contract(
                        output_root=root / "output",
                        repository_root=repository,
                        runtime_root=root / "system-paper-runtime",
                        python_executable=PYTHON_EXECUTABLE,
                        clock=lambda: CREATED_AT,
                        _command_runner=ReleaseCommandRunner(),
                    )

    def test_exact_publication_is_idempotent_and_conflicts_on_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            result, repository, runtime_root, output_root, runner = self.publish(
                directory
            )
            timezone = SimpleNamespace(tm_gmtoff=28800, tm_isdst=0)
            arguments = {
                "output_root": output_root,
                "repository_root": repository,
                "runtime_root": runtime_root,
                "python_executable": PYTHON_EXECUTABLE,
                "_command_runner": runner,
            }
            with patch(
                "crypto_quant.system_paper_launchd._timezone_link_target",
                return_value="/zoneinfo/Asia/Shanghai",
            ), patch(
                "crypto_quant.system_paper_launchd.time.localtime",
                return_value=timezone,
            ):
                retry = publish_system_paper_launchd_contract(
                    **arguments, clock=lambda: CREATED_AT
                )
                with self.assertRaisesRegex(
                    SystemPaperLaunchdError,
                    "SYSTEM_PAPER_LAUNCHD_PUBLISH_CONFLICT",
                ):
                    publish_system_paper_launchd_contract(
                        **arguments,
                        clock=lambda: "2026-08-04T04:00:01.000Z",
                    )
            self.assertEqual(result["contract_hash"], retry["contract_hash"])
            self.assertEqual(result["snapshot_root"], retry["snapshot_root"])
            self.assertFalse(retry["snapshot_created"])

    def test_loader_rejects_snapshot_and_rehashed_contract_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            result, _repository, _runtime, _output, _runner = self.publish(directory)
            contract_path = Path(result["contract_path"])
            plist_path = Path(result["plist_path"])
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            snapshot = Path(contract["execution_snapshot"]["repository_root"])
            target = snapshot / contract["execution_snapshot"]["files"][0]["path"]
            target.write_bytes(target.read_bytes() + b"tamper")
            os.chmod(target, 0o600)
            with self.assertRaises(SystemPaperLaunchdError):
                load_system_paper_launchd_contract(
                    contract_path=contract_path,
                    plist_path=plist_path,
                )

    def test_loader_rejects_coordinated_snapshot_inventory_and_contract_rehash(self):
        """Catches treating the contract inventory as its own source of truth."""

        with tempfile.TemporaryDirectory() as directory:
            result, _repository, _runtime, _output, _runner = self.publish(directory)
            contract_path = Path(result["contract_path"])
            plist_path = Path(result["plist_path"])
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            snapshot = Path(contract["execution_snapshot"]["repository_root"])
            record = next(
                item
                for item in contract["execution_snapshot"]["files"]
                if item["path"] == "pyproject.toml"
            )
            target = snapshot / record["path"]
            target.write_bytes(target.read_bytes() + b"# coordinated tamper\n")
            os.chmod(target, 0o600)
            record["size_bytes"] = target.stat().st_size
            record["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
            records = contract["execution_snapshot"]["files"]
            contract["execution_snapshot"]["total_bytes"] = sum(
                item["size_bytes"] for item in records
            )
            contract["execution_snapshot"]["tree_hash"] = business_hash(
                {"files": records}
            )
            identity = {
                "release_commit": contract["release"]["release_commit"],
                "snapshot_tree_hash": contract["execution_snapshot"]["tree_hash"],
                "runtime_root": contract["runtime_root"],
                "python_executable": contract["python_executable"],
                "launchd_plist_sha256": contract["launchd_plist_sha256"],
            }
            contract["contract_id"] = stable_id(
                "system_paper_launchd_contract", identity
            )
            contract["contract_hash"] = artifact_self_hash(
                contract, "contract_hash"
            )
            contract_path.write_bytes(canonical_json(contract).encode("utf-8"))
            os.chmod(contract_path, 0o600)

            with self.assertRaises(SystemPaperLaunchdError):
                load_system_paper_launchd_contract(
                    contract_path=contract_path,
                    plist_path=plist_path,
                )

        with tempfile.TemporaryDirectory() as directory:
            result, _repository, _runtime, _output, _runner = self.publish(directory)
            contract_path = Path(result["contract_path"])
            plist_path = Path(result["plist_path"])
            changed = json.loads(contract_path.read_text(encoding="utf-8"))
            changed["program_arguments"][-1] = "/private/tmp/attacker"
            changed["contract_hash"] = artifact_self_hash(changed, "contract_hash")
            contract_path.write_bytes(canonical_json(changed).encode("utf-8"))
            os.chmod(contract_path, 0o600)
            with self.assertRaises(SystemPaperLaunchdError):
                load_system_paper_launchd_contract(
                    contract_path=contract_path,
                    plist_path=plist_path,
                )

    def test_source_change_during_snapshot_is_removed_and_fails_closed(self):
        import crypto_quant.system_paper_launchd as module

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repository = fake_release_repository(root)
            runtime_root = root / "system-paper-runtime"
            original = module._write_snapshot_file
            changed = {"done": False}

            def mutate_after_first_write(path, body):
                original(path, body)
                if not changed["done"]:
                    changed["done"] = True
                    source = repository / "pyproject.toml"
                    source.write_bytes(source.read_bytes() + b"# changed\n")

            timezone = SimpleNamespace(tm_gmtoff=28800, tm_isdst=0)
            with patch.object(
                module, "_write_snapshot_file", side_effect=mutate_after_first_write
            ), patch.object(
                module,
                "_timezone_link_target",
                return_value="/zoneinfo/Asia/Shanghai",
            ), patch.object(
                module.time, "localtime", return_value=timezone
            ), self.assertRaises(SystemPaperLaunchdError):
                publish_system_paper_launchd_contract(
                    output_root=root / "output",
                    repository_root=repository,
                    runtime_root=runtime_root,
                    python_executable=PYTHON_EXECUTABLE,
                    clock=lambda: CREATED_AT,
                    _command_runner=ReleaseCommandRunner(),
                )
            snapshot_parent = runtime_root / "deployment" / "system-paper-snapshots"
            if snapshot_parent.exists():
                self.assertEqual(tuple(snapshot_parent.iterdir()), ())

    def test_paths_timezone_schema_and_cli_authority_fail_closed(self):
        self.assertEqual(
            (ROOT / "config" / "system-paper-launchd-contract-v1.schema.json").read_bytes(),
            (
                ROOT
                / "src"
                / "crypto_quant"
                / "schemas"
                / "system-paper-launchd-contract-v1.schema.json"
            ).read_bytes(),
        )
        status_out = io.StringIO()
        with redirect_stdout(status_out):
            self.assertEqual(launchd_main(["--help"]), 0)
        help_text = status_out.getvalue()
        for required in (
            "--repository-root",
            "--runtime-root",
            "--python-executable",
            "--output-root",
        ):
            self.assertIn(required, help_text)
        for forbidden in (
            "--install",
            "--start",
            "--launchctl",
            "--credential",
            "--url",
            "--symbol",
            "--order",
        ):
            self.assertNotIn(forbidden, help_text)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repository = fake_release_repository(root)
            target = root / "runtime-target"
            target.mkdir(mode=0o700)
            alias = root / "runtime-alias"
            alias.symlink_to(target, target_is_directory=True)
            for runtime_root in (
                repository / "nested-runtime",
                root / "challenger-runtime",
                alias,
            ):
                with self.subTest(runtime_root=runtime_root), self.assertRaises(
                    SystemPaperLaunchdError
                ):
                    publish_system_paper_launchd_contract(
                        output_root=root / ("output-" + runtime_root.name),
                        repository_root=repository,
                        runtime_root=runtime_root,
                        python_executable=PYTHON_EXECUTABLE,
                        clock=lambda: CREATED_AT,
                        _command_runner=ReleaseCommandRunner(),
                    )

            with patch(
                "crypto_quant.system_paper_launchd._timezone_link_target",
                return_value="/zoneinfo/UTC",
            ), patch(
                "crypto_quant.system_paper_launchd.time.localtime",
                return_value=SimpleNamespace(tm_gmtoff=0, tm_isdst=0),
            ), self.assertRaises(SystemPaperLaunchdError):
                publish_system_paper_launchd_contract(
                    output_root=root / "timezone-output",
                    repository_root=repository,
                    runtime_root=root / "timezone-runtime",
                    python_executable=PYTHON_EXECUTABLE,
                    clock=lambda: CREATED_AT,
                    _command_runner=ReleaseCommandRunner(),
                )

    def test_render_cli_publishes_but_never_installs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repository = fake_release_repository(root)
            timezone = SimpleNamespace(tm_gmtoff=28800, tm_isdst=0)
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch(
                "crypto_quant.system_paper_launchd._timezone_link_target",
                return_value="/zoneinfo/Asia/Shanghai",
            ), patch(
                "crypto_quant.system_paper_launchd.time.localtime",
                return_value=timezone,
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                status = launchd_main(
                    [
                        "--repository-root",
                        str(repository),
                        "--runtime-root",
                        str(root / "system-paper-runtime"),
                        "--python-executable",
                        str(PYTHON_EXECUTABLE),
                        "--output-root",
                        str(root / "output"),
                    ],
                    clock=lambda: CREATED_AT,
                    _command_runner=ReleaseCommandRunner(),
                )
            self.assertEqual((status, stderr.getvalue()), (0, ""))
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["outcome"], "GENERATED_NOT_INSTALLED")
            self.assertFalse(result["launchctl_invoked"])


if __name__ == "__main__":
    unittest.main()
