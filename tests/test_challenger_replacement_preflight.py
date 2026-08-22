import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from jsonschema import Draft202012Validator

from crypto_quant.challenger_replacement_deployment import (
    build_challenger_replacement_deployment,
    render_challenger_replacement_plist,
)
from crypto_quant.canonical import canonical_json


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "config/challenger-replacement-preflight-v1.schema.json"
PACKAGE_SCHEMA = ROOT / "src/crypto_quant/schemas/challenger-replacement-preflight-v1.schema.json"


class ReplacementPreflightTests(unittest.TestCase):
    def test_verified_fixture_observes_exact_commands_and_writes_nothing(self):
        from crypto_quant import challenger_replacement_preflight as preflight

        deployment = build_challenger_replacement_deployment()
        commands = []
        outputs = {
            ("git", "remote", "get-url", "origin"): (0, b"https://github.com/cjl308868584-lang/crypto-quant-core.git\n", b""),
            ("git", "rev-parse", "origin/main"): (0, b"f" * 40 + b"\n", b""),
            ("git", "rev-parse", "v0.67.0^{}"): (0, b"f" * 40 + b"\n", b""),
            ("git", "status", "--porcelain=v1", "--untracked-files=all"): (0, b"", b""),
            ("gh", "api", "repos/cjl308868584-lang/crypto-quant-core", "--jq", ".permissions.admin"): (0, b"true\n", b""),
            ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-forward"): (113, b"", b"not found"),
            ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-replacement-v1"): (113, b"", b"not found"),
            ("/usr/bin/pmset", "-g", "custom"): (0, b" sleep 0\n", b""),
        }

        def run(argv, repository):
            commands.append(tuple(argv))
            return outputs[tuple(argv)]

        with TemporaryDirectory() as directory:
            repository = Path(directory)
            sentinel = repository / "sentinel"
            sentinel.write_bytes(b"unchanged")
            before = sentinel.stat()
            with patch.object(preflight, "load_challenger_replacement_deployment", return_value=deployment), \
                 patch.object(preflight, "_machine", return_value={"system": "Darwin", "machine": "arm64", "uid": 501, "home": "/Users/chenm4", "timezone": "Asia/Shanghai"}), \
                 patch.object(preflight, "_credential_count", return_value=0, create=True), \
                 patch.object(preflight, "_run", side_effect=run), \
                 patch.object(preflight, "_paths_absent", return_value=True), \
                 patch.object(preflight, "_disk", return_value={"free_bytes": 20_000_000_000, "free_inodes": 1_000_000}), \
                 patch.object(preflight, "_time_probe", return_value={"request_count": 3, "trust_hash": "a" * 64}), \
                 patch.object(preflight, "_now", return_value="2026-08-22T08:25:00.000Z"):
                receipt = preflight.observe_challenger_replacement_preflight(
                    repository=repository,
                    deployment_path=repository / "deployment.json",
                    manifest_path=repository / "manifest.json",
                )
            after = sentinel.stat()
        self.assertEqual(receipt["status"], "PREFLIGHT_CANDIDATE_VERIFIED_NOT_PUBLISHED")
        self.assertEqual(receipt["historical_qualification"], "NO_OBSERVABLE_REPLACEMENT_INSTALLATION_AT_COLLECTION")
        self.assertEqual(receipt["authority"], {"state_write_count": 0, "launchctl_mutation_count": 0, "credential_count": 0, "broker_request_count": 0, "order_count": 0})
        self.assertEqual(commands, list(outputs))
        self.assertEqual((before.st_ino, before.st_size, before.st_mtime_ns), (after.st_ino, after.st_size, after.st_mtime_ns))
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        schema = json.loads(CONFIG_SCHEMA.read_text())
        Draft202012Validator.check_schema(schema)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(receipt)), [])

    def test_unsupported_machine_stops_before_commands_or_network(self):
        from crypto_quant import challenger_replacement_preflight as preflight

        deployment = build_challenger_replacement_deployment()
        with TemporaryDirectory() as directory, patch.object(
            preflight, "load_challenger_replacement_deployment", return_value=deployment
        ), patch.object(
            preflight, "_machine", return_value={
                "system": "Linux", "machine": "x86_64", "uid": 1000,
                "home": "/tmp/fixture", "timezone": "UTC",
            }
        ), patch.object(
            preflight, "_run", side_effect=AssertionError("command forbidden")
        ) as run, patch.object(
            preflight, "_time_probe", side_effect=AssertionError("network forbidden")
        ) as probe, patch.object(
            preflight, "_now", return_value="2026-08-22T08:25:00.000Z"
        ):
            receipt = preflight.observe_challenger_replacement_preflight(
                repository=Path(directory),
                deployment_path=Path(directory) / "deployment.json",
                manifest_path=Path(directory) / "manifest.json",
            )
        self.assertEqual(receipt["status"], "PREFLIGHT_PLATFORM_UNSUPPORTED")
        self.assertEqual((run.call_count, probe.call_count), (0, 0))
        self.assertEqual(receipt["commands"], [])
        self.assertEqual(receipt["network"]["request_count"], 0)

    def test_loader_replays_canonical_bytes_and_exact_deployment_binding(self):
        from crypto_quant import challenger_replacement_preflight as preflight

        deployment = build_challenger_replacement_deployment()
        machine = {"system": "Linux", "machine": "x86_64", "uid": 1000,
                   "home": "/tmp/fixture", "timezone": "UTC"}
        with TemporaryDirectory() as directory, patch.object(
            preflight, "load_challenger_replacement_deployment", return_value=deployment
        ), patch.object(preflight, "_machine", return_value=machine), patch.object(
            preflight, "_now", return_value="2026-08-22T08:25:00.000Z"
        ):
            receipt = preflight.observe_challenger_replacement_preflight(
                repository=Path(directory), deployment_path=Path(directory) / "deployment.json",
                manifest_path=Path(directory) / "manifest.json")
        body = canonical_json(receipt).encode()
        loaded = preflight.load_challenger_replacement_preflight_bytes(
            body, deployment=deployment,
            plist_bytes=render_challenger_replacement_plist(deployment))
        self.assertEqual(loaded, receipt)
        mutated = dict(receipt); mutated["receipt_hash"] = "0" * 64
        with self.assertRaises(ValueError):
            preflight.load_challenger_replacement_preflight_bytes(
                canonical_json(mutated).encode(), deployment=deployment,
                plist_bytes=render_challenger_replacement_plist(deployment))

    def test_absent_target_below_symlink_ancestor_is_not_safe(self):
        from crypto_quant import challenger_replacement_preflight as preflight

        deployment = build_challenger_replacement_deployment()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"; real.mkdir()
            link = root / "link"; os.symlink(real, link)
            deployment["paths"]["runtime_root"] = str(link / "runtime")
            deployment["paths"]["target_plist"] = str(link / "agent.plist")
            self.assertFalse(preflight._paths_absent(deployment))

    def test_credential_environment_is_ineligible_and_skips_network(self):
        from crypto_quant import challenger_replacement_preflight as preflight

        deployment = build_challenger_replacement_deployment()
        def run(argv, repository):
            if argv[:3] == ("git", "remote", "get-url"): return 0, b"https://github.com/cjl308868584-lang/crypto-quant-core.git\n", b""
            if argv[:2] == ("git", "rev-parse"): return 0, b"f" * 40 + b"\n", b""
            if argv[:2] == ("git", "status"): return 0, b"", b""
            if argv[0] == "gh": return 0, b"true\n", b""
            if argv[0] == "/bin/launchctl": return 113, b"", b"not found"
            return 0, b" sleep 0\n", b""
        machine = {"system": "Darwin", "machine": "arm64", "uid": 501,
                   "home": "/Users/chenm4", "timezone": "Asia/Shanghai"}
        with TemporaryDirectory() as directory, patch.object(
            preflight, "load_challenger_replacement_deployment", return_value=deployment
        ), patch.object(preflight, "_machine", return_value=machine), patch.object(
            preflight, "_credential_count", return_value=1, create=True
        ), patch.object(preflight, "_run", side_effect=run), patch.object(
            preflight, "_paths_absent", return_value=True
        ), patch.object(preflight, "_disk", return_value={"free_bytes": 20_000_000_000, "free_inodes": 1_000_000}), patch.object(
            preflight, "_time_probe", side_effect=AssertionError("network forbidden")
        ) as probe, patch.object(preflight, "_now", return_value="2026-08-22T08:25:00.000Z"):
            receipt = preflight.observe_challenger_replacement_preflight(
                repository=Path(directory), deployment_path=Path(directory) / "deployment.json",
                manifest_path=Path(directory) / "manifest.json")
        self.assertEqual(receipt["status"], "PREFLIGHT_CANDIDATE_INELIGIBLE")
        self.assertEqual(receipt["authority"]["credential_count"], 1)
        self.assertEqual(receipt["network"]["request_count"], 0)
        self.assertEqual(probe.call_count, 0)


if __name__ == "__main__":
    unittest.main()
