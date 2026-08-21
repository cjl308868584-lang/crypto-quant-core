import argparse
import hashlib
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crypto_quant.canonical import canonical_json
from crypto_quant.nautilus_v065_plan import build_nautilus_v065_plan
from crypto_quant.nautilus_v065_supply_chain import (
    NautilusV065SupplyChainError,
    build_nautilus_v065_dependency_lock,
    load_nautilus_v065_supply_chain_receipt,
)
from crypto_quant.nautilus_v065_ceremony_cli import (
    _capture_fixed_command,
    _publish_fixed_artifact,
    acquire_nautilus_v065_supply_chain,
    build_parser,
)


ROOT = Path(__file__).resolve().parents[1]


def _subcommands(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


class NautilusV065AcquisitionTests(unittest.TestCase):
    def plan(self):
        head = __import__("subprocess").run(
            ["/usr/bin/git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            stdout=__import__("subprocess").PIPE,
            text=True,
        ).stdout.strip()
        return build_nautilus_v065_plan(repository_root=ROOT, candidate_commit=head)

    def test_intermediate_cli_exposes_only_parameterless_publish_plan(self):
        parser = build_parser()
        self.assertEqual(_subcommands(parser), {"publish-plan"})
        args = parser.parse_args(["publish-plan"])
        self.assertEqual(vars(args), {"command": "publish-plan"})
        with self.assertRaises(SystemExit):
            parser.parse_args(["publish-plan", "--url", "https://example.invalid"])

    def test_command_capture_uses_fixed_executable_sanitized_env_and_exact_bytes(self):
        def execute(*_args, **kwargs):
            kwargs["stdout"].write(b"ok\n")
            return mock.Mock(returncode=0)

        with mock.patch("subprocess.run", side_effect=execute) as run:
            record = _capture_fixed_command("git_version")
        argv = run.call_args.args[0]
        self.assertEqual(argv, ["/usr/bin/git", "--version"])
        self.assertFalse(run.call_args.kwargs["shell"])
        environment = run.call_args.kwargs["env"]
        self.assertEqual(
            set(environment),
            {"HOME", "LANG", "LC_ALL", "PATH", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT"},
        )
        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertEqual(record["stdout_bytes"], "ok\n")
        self.assertEqual(record["stdout_size"], 3)
        self.assertEqual(record["stdout_sha256"], hashlib.sha256(b"ok\n").hexdigest())
        self.assertEqual(record["stderr_sha256"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(record["executable_sha256_before"], record["executable_sha256_after"])

    def test_command_capture_fails_closed_on_timeout_output_and_executable_change(self):
        with mock.patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired("git", 10)):
            with self.assertRaisesRegex(NautilusV065SupplyChainError, "NAUTILUS_V065_COMMAND_TIMEOUT"):
                _capture_fixed_command("git_version")
        def too_large(*_args, **kwargs):
            kwargs["stdout"].write(b"x" * (4 * 1024 * 1024 + 1))
            return mock.Mock(returncode=0)

        with mock.patch("subprocess.run", side_effect=too_large):
            with self.assertRaisesRegex(NautilusV065SupplyChainError, "NAUTILUS_V065_COMMAND_OUTPUT_LIMIT"):
                _capture_fixed_command("git_version")
        def ok(*_args, **kwargs):
            kwargs["stdout"].write(b"ok")
            return mock.Mock(returncode=0)

        with mock.patch("subprocess.run", side_effect=ok), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._executable_identity",
            side_effect=[{"sha256": "1" * 64}, {"sha256": "2" * 64}],
        ):
            with self.assertRaisesRegex(NautilusV065SupplyChainError, "NAUTILUS_V065_EXECUTABLE_CHANGED"):
                _capture_fixed_command("git_version")

    def test_acquisition_has_fixed_order_zero_authority_and_verified_receipt(self):
        plan = self.plan()
        lock = build_nautilus_v065_dependency_lock(repository_root=ROOT)
        calls = []

        def command(name, **_kwargs):
            calls.append(("command", name))
            if name == "official_tag":
                raw = b"112d335088ec11cdd1d60038b16c8fe56406aead refs/tags/v1.230.0\n8160730c7c550480b0a439fb11086a4c4de15f0b refs/tags/v1.230.0^{}\n"
            elif name == "license":
                raw = b"license-fixture"
            else:
                raw = (name + "\n").encode()
            return {
                "name": name,
                "argv": [name],
                "exit_code": 0,
                "executable_path": "/usr/bin/true",
                "executable_device_before": 1,
                "executable_inode_before": 1,
                "executable_mode_before": 0o755,
                "executable_size_before": 1,
                "stdout_encoding": "utf-8",
                "stdout_bytes": raw.decode(),
                "stdout_size": len(raw),
                "stdout_sha256": hashlib.sha256(raw).hexdigest(),
                "stderr_encoding": "utf-8",
                "stderr_bytes": "",
                "stderr_size": 0,
                "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                "executable_sha256_before": "3" * 64,
                "executable_device_after": 1,
                "executable_inode_after": 1,
                "executable_mode_after": 0o755,
                "executable_size_after": 1,
                "executable_sha256_after": "3" * 64,
            }

        def download(item, _wheelhouse):
            calls.append(("download", item["filename"]))
            return dict(item)

        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._capture_fixed_command",
            side_effect=command,
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._download_fixed_artifact",
            side_effect=download,
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._platform_identity",
            return_value={
                "operating_system": "macOS",
                "operating_system_major": 15,
                "machine": "arm64",
                "python_implementation": "CPython",
                "python_version": "3.12.13",
            },
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._verify_license_transcript"
        ):
            receipt = acquire_nautilus_v065_supply_chain(plan=plan)
        command_names = [value for kind, value in calls if kind == "command"]
        self.assertEqual(
            command_names,
            ["uv_version", "python_version", "git_version", "gh_version", "official_tag", "license", "slsa", "offline_venv", "offline_sync", "offline_import"],
        )
        first_download = next(index for index, value in enumerate(calls) if value[0] == "download")
        self.assertLess(command_names.index("gh_version"), first_download)
        self.assertLess(max(index for index, value in enumerate(calls) if value[0] == "download"), calls.index(("command", "offline_sync")))
        self.assertEqual(receipt["verified_files"], lock["distributions"])
        self.assertEqual(set(receipt["authority_counters"].values()), {0})
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "receipt.json"
            path.write_bytes(canonical_json(receipt).encode() + b"\n")
            path.chmod(0o600)
            self.assertEqual(load_nautilus_v065_supply_chain_receipt(path.resolve()), receipt)

    def test_safe_publisher_is_no_overwrite_and_recovers_exact_final(self):
        data = b'{"fixed":true}\n'
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            name = "nautilus-supply-chain-receipt-v0.65.0.json"
            first = _publish_fixed_artifact(root=root, final_name=name, data=data)
            target = root / name
            inode = target.stat().st_ino
            second = _publish_fixed_artifact(root=root, final_name=name, data=data)
            self.assertEqual(first["status"], "COMMITTED")
            self.assertEqual(second["status"], "ALREADY_PUBLISHED")
            self.assertEqual(target.stat().st_ino, inode)
            with self.assertRaisesRegex(NautilusV065SupplyChainError, "NAUTILUS_V065_FINAL_CONFLICT"):
                _publish_fixed_artifact(root=root, final_name=name, data=b"different")
            self.assertEqual(target.read_bytes(), data)

    def test_safe_publisher_rejects_symlink_hardlink_fifo_and_wrong_mode(self):
        data = b'{"fixed":true}\n'
        name = "nautilus-supply-chain-receipt-v0.65.0.json"
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            sentinel = root / "sentinel"
            sentinel.write_bytes(b"outside")
            sentinel.chmod(0o600)
            before = sentinel.stat()
            for kind in ("symlink", "hardlink", "fifo", "wrong_mode"):
                target = root / name
                if target.exists() or target.is_symlink():
                    target.unlink()
                if kind == "symlink":
                    target.symlink_to(sentinel)
                elif kind == "hardlink":
                    os.link(sentinel, target)
                elif kind == "fifo":
                    os.mkfifo(target, 0o600)
                else:
                    target.write_bytes(data)
                    target.chmod(0o644)
                with self.subTest(kind=kind):
                    with self.assertRaisesRegex(
                        NautilusV065SupplyChainError, "NAUTILUS_V065_FINAL_UNTRUSTED"
                    ):
                        _publish_fixed_artifact(root=root, final_name=name, data=data)
                if kind == "fifo":
                    target.unlink()
            after = sentinel.stat()
            self.assertEqual(sentinel.read_bytes(), b"outside")
            self.assertEqual(
                (before.st_ino, before.st_mode, before.st_size, before.st_nlink),
                (after.st_ino, after.st_mode, after.st_size, after.st_nlink),
            )

    def test_safe_publisher_detects_root_replacement_before_success(self):
        from crypto_quant import nautilus_v065_ceremony_cli as module

        data = b'{"fixed":true}\n'
        name = "nautilus-supply-chain-receipt-v0.65.0.json"
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            root = parent / "root"
            moved = parent / "moved"
            root.mkdir(mode=0o700)
            original = module._atomic_no_replace

            def replace_then_publish(parent_fd, staging, final):
                root.rename(moved)
                root.mkdir(mode=0o700)
                return original(parent_fd, staging, final)

            with mock.patch.object(module, "_atomic_no_replace", replace_then_publish):
                with self.assertRaisesRegex(
                    NautilusV065SupplyChainError, "NAUTILUS_V065_ARTIFACT_ROOT_INVALID"
                ):
                    _publish_fixed_artifact(root=root, final_name=name, data=data)
            self.assertFalse((root / name).exists())

    def test_source_contains_no_public_override_or_arbitrary_injection_seam(self):
        source = inspect.getsource(__import__("crypto_quant.nautilus_v065_ceremony_cli", fromlist=["*"]))
        self.assertNotIn("fault_injector", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.environ.copy", source)
        self.assertNotIn("--url", source)
        self.assertNotIn("--output", source)


if __name__ == "__main__":
    unittest.main()
