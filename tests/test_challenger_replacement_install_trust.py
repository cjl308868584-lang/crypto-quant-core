import copy
import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

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
            "preflight_root": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/deployment/preflight-receipts",
            "install_receipt_root": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/deployment/install-receipts",
            "start_receipt_root": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/evidence/start-receipts",
            "event_root": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/state/challenger-replacement-events-v1",
            "stdout": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/log/challenger-replacement.stdout.log",
            "stderr": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1/log/challenger-replacement.stderr.log",
            "target_plist": "/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist",
        },
        "runtime": {
            "module": "crypto_quant.challenger_replacement_live_runtime_cli",
            "program_arguments": [
                "/usr/bin/python3",
                "-m",
                "crypto_quant.challenger_replacement_live_runtime_cli",
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
    identity = {key: value for key, value in contract.items()
                if key not in ("contract_id", "contract_hash")}
    contract["contract_id"] = stable_id(
        "challenger_replacement_install_contract", identity
    )
    contract["contract_hash"] = artifact_self_hash(contract, "contract_hash")
    return contract


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


if __name__ == "__main__":
    unittest.main()
