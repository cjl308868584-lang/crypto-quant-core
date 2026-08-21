import copy
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.nautilus_v065_supply_chain import (
    _OFFLINE_IMPORT_CODE,
    _fixed_executable_matches,
    NautilusV065SupplyChainError,
    build_nautilus_v065_dependency_lock,
    load_nautilus_v065_supply_chain_receipt,
    supply_chain_receipt_hash,
)


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "sandboxes" / "nautilus-v065" / "uv.lock"
CONFIG_SCHEMA = ROOT / "config" / "nautilus-supply-chain-receipt-v2.schema.json"
PACKAGE_SCHEMA = (
    ROOT / "src" / "crypto_quant" / "schemas" / CONFIG_SCHEMA.name
)
WHEEL = "nautilus_trader-1.230.0-cp312-cp312-macosx_15_0_arm64.whl"
WHEEL_SHA = "033f6207d1c52095d64a7644f43b90cab939c2038044db70a4165f2acef3d079"
LICENSE = ROOT / "tests" / "fixtures" / "nautilus-v065" / "LICENSE-1.230.0.txt"


class NautilusV065SupplyChainTests(unittest.TestCase):
    def lock(self):
        return build_nautilus_v065_dependency_lock(repository_root=ROOT)

    def receipt(self):
        lock = self.lock()
        workspace = Path("/private/tmp/nautilus-v065-test")
        urls = {
            url.rsplit("/", 1)[1]: url
            for url in re.findall(
                r'url = "(https://files\.pythonhosted\.org/[^"]+\.whl)"',
                LOCK.read_text(encoding="utf-8"),
            )
        }
        command_names = [
            "uv_version", "python_version", "git_version", "gh_version",
            "pypi_version", "official_tag", "license",
            *["download:" + item["filename"] for item in lock["distributions"]],
            "slsa", "offline_venv",
            "offline_sync", "offline_import",
        ]
        def transcript(name):
            if name in {"git_version", "official_tag"}:
                executable = "/usr/bin/git"
            elif name == "pypi_version" or name == "license" or name.startswith("download:"):
                executable = "/usr/bin/curl"
            elif name in {"uv_version", "offline_venv", "offline_sync"}:
                executable = "/opt/homebrew/bin/uv"
            elif name in {"gh_version", "slsa"}:
                executable = "/opt/homebrew/bin/gh"
            elif name == "python_version":
                executable = "/opt/homebrew/bin/python3.12"
            else:
                executable = str(workspace / "venv/bin/python")
            tails = {
                "uv_version": ["--version"],
                "python_version": ["--version"],
                "git_version": ["--version"],
                "gh_version": ["--version"],
                "pypi_version": ["--fail", "--silent", "--show-error", "--proto", "=https", "https://pypi.org/pypi/nautilus_trader/1.230.0/json"],
                "official_tag": ["ls-remote", "https://github.com/nautechsystems/nautilus_trader.git", "refs/tags/v1.230.0", "refs/tags/v1.230.0^{}"],
                "license": ["--fail", "--silent", "--show-error", "--proto", "=https", "https://raw.githubusercontent.com/nautechsystems/nautilus_trader/8160730c7c550480b0a439fb11086a4c4de15f0b/LICENSE"],
                "slsa": ["attestation", "verify", str(workspace / "wheelhouse" / WHEEL), "--repo", "nautechsystems/nautilus_trader"],
                "offline_venv": ["venv", "--offline", "--python", "/opt/homebrew/bin/python3.12", str(workspace / "venv")],
                "offline_sync": ["pip", "install", "--offline", "--python", str(workspace / "venv/bin/python"), "--find-links", str(workspace / "wheelhouse"), "nautilus_trader==1.230.0"],
                "offline_import": ["-I", "-c", _OFFLINE_IMPORT_CODE],
            }
            if name.startswith("download:"):
                filename = name.removeprefix("download:")
                distribution = next(item for item in lock["distributions"] if item["filename"] == filename)
                tails[name] = ["--fail", "--silent", "--show-error", "--proto", "=https", "--max-filesize", str(distribution["size"]), "--output", str(workspace / "wheelhouse" / filename), "--write-out", "%{http_code} %{url_effective}\n", urls[filename]]
            if name == "official_tag":
                raw = b"112d335088ec11cdd1d60038b16c8fe56406aead\trefs/tags/v1.230.0\n8160730c7c550480b0a439fb11086a4c4de15f0b\trefs/tags/v1.230.0^{}\n"
            elif name == "license":
                raw = LICENSE.read_bytes()
            elif name == "pypi_version":
                candidate = next(item for item in lock["distributions"] if item["filename"] == WHEEL)
                raw = json.dumps({
                    "info": {"version": "1.230.0", "requires_python": ">=3.12,<3.15"},
                    "urls": [{"filename": WHEEL, "size": candidate["size"], "url": urls[WHEEL], "digests": {"sha256": WHEEL_SHA}}],
                }, separators=(",", ":")).encode()
            elif name.startswith("download:"):
                raw = ("200 " + urls[name.removeprefix("download:")] + "\n").encode()
            else:
                raw = {
                    "uv_version": b"uv 0.8.12\n",
                    "python_version": b"Python 3.12.13\n",
                    "git_version": b"git version 2.50.1\n",
                    "gh_version": b"gh version 2.76.2\n",
                }.get(name, (name + "\n").encode())
            return {
                "name": name,
                "argv": [executable, *tails[name]],
                "exit_code": 0,
                "environment": {
                    "HOME": "/private/tmp/nautilus-v065-test/home",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_TERMINAL_PROMPT": "0",
                },
                "started_at": "2026-08-22T00:00:00.000000Z",
                "completed_at": "2026-08-22T00:00:01.000000Z",
                "executable_path": executable,
                "executable_device_before": 1,
                "executable_inode_before": 1,
                "executable_mode_before": 493,
                "executable_size_before": 1,
                "executable_sha256_before": "3" * 64,
                "executable_device_after": 1,
                "executable_inode_after": 1,
                "executable_mode_after": 493,
                "executable_size_after": 1,
                "executable_sha256_after": "3" * 64,
                "stdout_encoding": "utf-8",
                "stdout_bytes": raw.decode(),
                "stdout_size": len(raw),
                "stdout_sha256": hashlib.sha256(raw).hexdigest(),
                "stderr_encoding": "utf-8",
                "stderr_bytes": "",
                "stderr_size": 0,
                "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            }
        payload = {
            "$schema": "./nautilus-supply-chain-receipt-v2.schema.json",
            "schema_version": "2.0.0",
            "receipt_id": "nautilus_v065_supply_chain_" + "0" * 64,
            "receipt_hash": "0" * 64,
            "plan_id": "nautilus_v065_plan_" + "1" * 64,
            "plan_hash": "2" * 64,
            "dependency_lock": lock,
            "platform": {
                "operating_system": "macOS",
                "operating_system_major": 15,
                "machine": "arm64",
                "python_implementation": "CPython",
                "python_version": "3.12.13",
            },
            "tools": [],
            "transcripts": [transcript(name) for name in command_names],
            "verified_files": lock["distributions"],
            "license": {
                "expression": "LGPL-3.0-or-later",
                "size": 7651,
                "sha256": "ee907919ec88c9c017b1f8b608db20960b6598aefcc4fe58820bde955d65ed3c",
            },
            "official_source": {
                "tag": "v1.230.0",
                "tag_object": "112d335088ec11cdd1d60038b16c8fe56406aead",
                "peeled_commit": "8160730c7c550480b0a439fb11086a4c4de15f0b",
            },
            "slsa": {
                "verified": True,
                "subject_filename": WHEEL,
                "subject_sha256": WHEEL_SHA,
            },
            "authority_counters": {
                "credential_reads": 0,
                "market_requests": 0,
                "account_requests": 0,
                "broker_requests": 0,
                "orders": 0,
                "production_state_writes": 0,
            },
            "status": "SUPPLY_CHAIN_VERIFIED_SANDBOX_READY",
        }
        payload["tools"] = [
            {
                "name": item["name"].removesuffix("_version"),
                "version": item["stdout_bytes"].strip(),
                "executable_sha256_before": item["executable_sha256_before"],
                "executable_sha256_after": item["executable_sha256_after"],
            }
            for item in payload["transcripts"][:4]
        ]
        payload["receipt_id"] = "nautilus_v065_supply_chain_" + supply_chain_receipt_hash(payload)
        payload["receipt_hash"] = supply_chain_receipt_hash(payload)
        return payload

    def test_lock_freezes_exact_candidate_and_all_distribution_hashes(self):
        lock = self.lock()
        self.assertEqual(lock["format"], "uv.lock")
        self.assertEqual(lock["path"], "sandboxes/nautilus-v065/uv.lock")
        self.assertEqual(lock["file_sha256"], hashlib.sha256(LOCK.read_bytes()).hexdigest())
        top = [item for item in lock["distributions"] if item["filename"] == WHEEL]
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0]["size"], 156035900)
        self.assertEqual(top[0]["sha256"], WHEEL_SHA)
        self.assertGreater(len(lock["distributions"]), 1)
        self.assertEqual(
            lock["distributions"],
            sorted(lock["distributions"], key=lambda item: (item["name"], item["filename"])),
        )

    def test_lock_rejects_unpinned_source_sdist_and_wrong_index(self):
        body = LOCK.read_text(encoding="utf-8")
        for changed in (
            body.replace(
                'name = "nautilus-trader"\nversion = "1.230.0"',
                'name = "nautilus-trader"\nversion = "1.231.0"',
                1,
            ),
            body.replace(
                'source = { registry = "https://pypi.org/simple" }',
                'source = { registry = "https://example.invalid/simple" }',
                1,
            ),
            body.replace(
                "nautilus_trader-1.230.0-cp312-cp312-macosx_15_0_arm64.whl",
                "nautilus_trader-1.230.0-cp312-cp312-macosx_15_0_arm64.tar.gz",
                1,
            ),
        ):
            with self.subTest():
                with tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    target = root / "sandboxes" / "nautilus-v065"
                    target.mkdir(parents=True)
                    (target / "uv.lock").write_text(changed, encoding="utf-8")
                    with self.assertRaises(NautilusV065SupplyChainError):
                        build_nautilus_v065_dependency_lock(repository_root=root)

    def test_receipt_loader_recomputes_transcripts_hashes_and_zero_authority(self):
        payload = self.receipt()
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "receipt.json"
            path.write_bytes(canonical_json(payload).encode("utf-8") + b"\n")
            path.chmod(0o600)
            self.assertEqual(load_nautilus_v065_supply_chain_receipt(path.resolve()), payload)
            changed = copy.deepcopy(payload)
            changed["transcripts"][0]["stdout_sha256"] = "0" * 64
            path.write_bytes(canonical_json(changed).encode("utf-8") + b"\n")
            with self.assertRaisesRegex(
                NautilusV065SupplyChainError, "NAUTILUS_V065_TRANSCRIPT_HASH_MISMATCH"
            ):
                load_nautilus_v065_supply_chain_receipt(path.resolve())
            path.write_bytes(canonical_json(payload).encode("utf-8") + b"\n")
            path.chmod(0o644)
            with self.assertRaisesRegex(
                NautilusV065SupplyChainError, "NAUTILUS_V065_RECEIPT_PATH_INVALID"
            ):
                load_nautilus_v065_supply_chain_receipt(path.resolve())

    def test_receipt_loader_replays_fixed_command_environment_and_network_semantics(self):
        for mutate in (
            lambda value: value["transcripts"][4]["argv"].__setitem__(
                -1, "https://example.invalid/not-pypi"
            ),
            lambda value: value["transcripts"][4]["environment"].__setitem__(
                "HOME", "/private/tmp/other-workspace/home"
            ),
            lambda value: value["transcripts"][4].__setitem__(
                "stdout_bytes",
                value["transcripts"][4]["stdout_bytes"].replace(
                    ">=3.12,<3.15", ">=3.11"
                ),
            ),
        ):
            changed = self.receipt()
            mutate(changed)
            transcript = changed["transcripts"][4]
            raw = transcript["stdout_bytes"].encode("utf-8")
            transcript["stdout_size"] = len(raw)
            transcript["stdout_sha256"] = hashlib.sha256(raw).hexdigest()
            changed["receipt_id"] = "nautilus_v065_supply_chain_" + "0" * 64
            changed["receipt_hash"] = "0" * 64
            digest = supply_chain_receipt_hash(changed)
            changed["receipt_id"] = "nautilus_v065_supply_chain_" + digest
            changed["receipt_hash"] = digest
            with tempfile.TemporaryDirectory() as raw_dir:
                path = Path(raw_dir) / "receipt.json"
                path.write_bytes(canonical_json(changed).encode("utf-8") + b"\n")
                path.chmod(0o600)
                with self.assertRaisesRegex(
                    NautilusV065SupplyChainError,
                    "NAUTILUS_V065_TRANSCRIPT_SEMANTIC_INVALID",
                ):
                    load_nautilus_v065_supply_chain_receipt(path.resolve())

    def test_receipt_loader_rejects_self_declared_untrusted_command_executable(self):
        payload = self.receipt()
        transcript = next(
            item for item in payload["transcripts"] if item["name"] == "pypi_version"
        )
        transcript["executable_path"] = "/tmp/unverified-curl"
        transcript["argv"][0] = "/tmp/unverified-curl"
        payload["receipt_id"] = "nautilus_v065_supply_chain_" + "0" * 64
        payload["receipt_hash"] = "0" * 64
        digest = supply_chain_receipt_hash(payload)
        payload["receipt_id"] = "nautilus_v065_supply_chain_" + digest
        payload["receipt_hash"] = digest
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "receipt.json"
            path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
            path.chmod(0o600)
            with self.assertRaisesRegex(
                NautilusV065SupplyChainError,
                "NAUTILUS_V065_TRANSCRIPT_SEMANTIC_INVALID",
            ):
                load_nautilus_v065_supply_chain_receipt(path)

    def test_fixed_python_mapping_accepts_the_resolved_uv_managed_312_identity(self):
        workspace = Path("/private/tmp/nautilus-v065-test")
        self.assertTrue(
            _fixed_executable_matches(
                "python_version",
                "/Users/chenm4/.local/share/uv/python/"
                "cpython-3.12.13-macos-aarch64-none/bin/python3.12",
                workspace,
            )
        )

    def test_receipt_rejects_missing_output_and_nonzero_authority(self):
        payload = self.receipt()
        for mutate in (
            lambda value: value["transcripts"][0].pop("stderr_bytes"),
            lambda value: value["transcripts"][0].pop("environment"),
            lambda value: value["transcripts"][0].__setitem__(
                "completed_at", "2026-08-21T23:59:59.000000Z"
            ),
            lambda value: value["authority_counters"].__setitem__("orders", 1),
            lambda value: value["verified_files"].pop(),
        ):
            changed = copy.deepcopy(payload)
            mutate(changed)
            with tempfile.TemporaryDirectory() as raw:
                path = Path(raw) / "receipt.json"
                path.write_bytes(canonical_json(changed).encode("utf-8") + b"\n")
                path.chmod(0o600)
                with self.assertRaises(NautilusV065SupplyChainError):
                    load_nautilus_v065_supply_chain_receipt(path.resolve())

    def test_schema_is_strict_mirrored_and_accepts_exact_receipt(self):
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        schema = json.loads(CONFIG_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(self.receipt())), [])
        changed = self.receipt()
        changed["manual_url"] = "https://example.invalid"
        self.assertNotEqual(list(validator.iter_errors(changed)), [])


if __name__ == "__main__":
    unittest.main()
