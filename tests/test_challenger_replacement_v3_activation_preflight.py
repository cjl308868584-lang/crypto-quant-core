import hashlib
import inspect
import unittest
import json
from types import SimpleNamespace
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

from crypto_quant.canonical import canonical_json
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


NOW = datetime(2026, 8, 28, 8, 10, tzinfo=timezone.utc)
COMMANDS = (
    ("git", "remote", "get-url", "origin"),
    ("git", "rev-parse", "HEAD"),
    ("git", "rev-parse", "origin/main"),
    ("git", "rev-parse", "v0.78.5^{}"),
    ("git", "rev-parse", "v0.78.5"),
    ("git", "cat-file", "-t", "v0.78.5"),
    ("git", "status", "--porcelain=v1", "--untracked-files=all"),
    ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-forward"),
    ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-replacement-v1"),
    ("/usr/bin/pmset", "-g", "custom"),
)


def verified_facts():
    return {
        "contract_binding": {
            "contract_id": "challenger_replacement_v3_install_contract_" + "a" * 64,
            "contract_hash": "b" * 64,
            "file_sha256": "c" * 64,
        },
        "machine": {
            "system": "Darwin", "machine": "arm64", "uid": 501,
            "home": "/Users/chenm4", "timezone": "Asia/Shanghai",
        },
        "release_replayed": True, "paths_verified": True,
        "power_safe": True,
        "disk": {"free_bytes": 20_000_000_000, "free_inodes": 200_000},
        "clock": {
            "endpoint": "https://data-api.binance.vision/api/v3/time",
            "request_count": 3, "trust_hash": "d" * 64,
        },
        "credential_count": 0,
        "commands": [{
            "argv": list(argv), "exit_code": 0,
            "stdout_sha256": "1" * 64, "stderr_sha256": "2" * 64,
        } for argv in COMMANDS],
        "observed_at": NOW,
    }


class ChallengerReplacementV3ActivationPreflightTests(unittest.TestCase):
    def test_publication_uses_the_contract_release_scoped_receipt_directory(self):
        from crypto_quant import challenger_replacement_v3_activation_preflight as module

        receipt = {"receipt_id": "receipt"}
        scoped = "/fixed/deployment/preflight-receipts-v0.78.5"
        with patch.object(module, "collect_fixed_v3_activation_preflight", return_value=receipt), \
                patch.object(module, "activation_paths", return_value={
                    "preflight_root": scoped,
                }), patch.object(module, "canonical_json", return_value="{}"), \
                patch.object(module, "_publish_contract_exact", return_value=(
                    "PUBLISHED", object(),
                )) as publish:
            module.publish_fixed_v3_activation_preflight()
        self.assertEqual(publish.call_args.args[:2], (Path(scoped), "receipt.json"))

    def test_real_pmset_custom_output_is_strictly_power_safe(self):
        from crypto_quant import challenger_replacement_v3_activation_preflight as module

        paths = {
            "runtime_root": "/fixed/runtime", "event_root": "/fixed/events",
            "target_plist": "/fixed/agent.plist", "stdout": "/fixed/out",
            "stderr": "/fixed/err",
        }
        contract = {
            "release": {"peeled_commit": "a" * 40, "tag_object": "b" * 40},
            "paths": paths,
            "snapshot": {"root": "/fixed/snapshot", "root_device": "7",
                         "root_inode": "8"},
            "event_root": {"device": "9", "inode": "10"},
        }
        results = [
            (0, b"https://github.com/cjl308868584-lang/crypto-quant-core.git\n", b""),
            (0, ("a" * 40 + "\n").encode()),
            (0, ("a" * 40 + "\n").encode()),
            (0, ("a" * 40 + "\n").encode()),
            (0, ("b" * 40 + "\n").encode()),
            (0, b"tag\n", b""), (0, b"", b""),
            (113, b"", b""), (113, b"", b""),
            (0, (ROOT / "tests/fixtures/pmset-g-custom-ac-safe.txt").read_bytes(), b""),
        ]
        results = [item if len(item) == 3 else item + (b"",) for item in results]
        with patch.object(module, "_fixed_root_boundaries", return_value=True), \
             patch.object(module.os.path, "lexists", return_value=False):
            self.assertEqual(module._fixed_checks(contract, results),
                             (True, True, True))

    def test_pmset_parser_rejects_unsafe_ambiguous_or_malformed_output(self):
        from crypto_quant import challenger_replacement_v3_activation_preflight as module

        safe = (ROOT / "tests/fixtures/pmset-g-custom-ac-safe.txt").read_bytes()
        for data in (
            safe + safe,
            safe.replace(b"sleep                0", b"sleep                1"),
            safe + b" sleep                0\n",
            safe.replace(b"AC Power:", b"UPS Power:"),
            safe.replace(b" sleep                0\n", b""),
            b"AC Power:\n sleep \xff\n",
        ):
            self.assertFalse(module._pmset_power_safe(data))

    def test_root_boundary_uses_retained_descriptors_and_revalidates_attachment(self):
        from crypto_quant import challenger_replacement_v3_activation_preflight as module

        contract = {
            "paths": {"runtime_root": "/runtime", "event_root": "/events"},
            "snapshot": {"root": "/snapshot", "root_device": "2",
                         "root_inode": "20"},
            "event_root": {"device": "3", "inode": "30"},
        }
        opened = [
            SimpleNamespace(st_dev=1, st_ino=10),
            SimpleNamespace(st_dev=2, st_ino=20),
            SimpleNamespace(st_dev=3, st_ino=30),
        ]
        with patch.object(module, "_open_directory", side_effect=[
            (11, opened[0]), (12, opened[1]), (13, opened[2]),
        ]), patch.object(module.os, "listdir", return_value=[]) as listed, \
             patch.object(module, "_validate_directory_attachment") as validate, \
             patch.object(module, "_close_descriptor") as close:
            self.assertTrue(module._fixed_root_boundaries(contract))
        listed.assert_called_once_with(13)
        self.assertEqual(validate.call_count, 3)
        self.assertEqual([call.args[0] for call in close.call_args_list], [13, 12, 11])

        with patch.object(module, "_open_directory", side_effect=[
            (11, opened[0]), (12, opened[1]), (13, opened[2]),
        ]), patch.object(module.os, "listdir", return_value=[]), \
             patch.object(
                 module, "_validate_directory_attachment",
                 side_effect=ValueError("replaced"),
             ), patch.object(module, "_close_descriptor"):
            self.assertFalse(module._fixed_root_boundaries(contract))

    def test_root_boundary_compares_large_decimal_identity_to_os_stat(self):
        from crypto_quant import challenger_replacement_v3_activation_preflight as module

        large = 2**60 + 123
        contract = {
            "paths": {"runtime_root": "/runtime", "event_root": "/events"},
            "snapshot": {
                "root": "/snapshot", "root_device": str(large + 1),
                "root_inode": str(large + 2),
            },
            "event_root": {
                "device": str(large + 3), "inode": str(large + 4),
            },
        }
        opened = [
            SimpleNamespace(st_dev=1, st_ino=2),
            SimpleNamespace(st_dev=large + 1, st_ino=large + 2),
            SimpleNamespace(st_dev=large + 3, st_ino=large + 4),
        ]
        with patch.object(module, "_open_directory", side_effect=[
            (11, opened[0]), (12, opened[1]), (13, opened[2]),
        ]), patch.object(module.os, "listdir", return_value=[]), \
             patch.object(module, "_validate_directory_attachment"), \
             patch.object(module, "_close_descriptor"):
            self.assertTrue(module._fixed_root_boundaries(contract))

    def test_fixed_checks_require_present_trusted_runtime_snapshot_and_event_roots(self):
        from crypto_quant import challenger_replacement_v3_activation_preflight as module

        paths = {
            "runtime_root": "/fixed/runtime", "event_root": "/fixed/events",
            "target_plist": "/fixed/agent.plist", "stdout": "/fixed/out",
            "stderr": "/fixed/err",
        }
        contract = {
            "release": {"peeled_commit": "a" * 40, "tag_object": "b" * 40},
            "paths": paths,
            "snapshot": {"root": "/fixed/snapshot", "root_device": "7",
                         "root_inode": "8"},
            "event_root": {"device": "9", "inode": "10"},
        }
        results = [
            (0, b"https://github.com/cjl308868584-lang/crypto-quant-core.git\n", b""),
            (0, ("a" * 40 + "\n").encode(), b""),
            (0, ("a" * 40 + "\n").encode(), b""),
            (0, ("a" * 40 + "\n").encode(), b""),
            (0, ("b" * 40 + "\n").encode(), b""),
            (0, b"tag\n", b""), (0, b"", b""),
            (113, b"", b""), (113, b"", b""),
            (0, (ROOT / "tests/fixtures/pmset-g-custom-ac-safe.txt").read_bytes(), b""),
        ]
        with patch.object(module, "_fixed_root_boundaries", return_value=True), \
             patch.object(module.os.path, "lexists", return_value=False):
            self.assertEqual(module._fixed_checks(contract, results),
                             (True, True, True))

        with patch.object(module, "_fixed_root_boundaries", return_value=False), \
             patch.object(module.os.path, "lexists", return_value=False):
            self.assertEqual(module._fixed_checks(contract, results),
                             (True, False, True))

        for index, replacement in (
            (5, (0, b"commit\n", b"")),
            (4, (0, ("c" * 40 + "\n").encode(), b"")),
            (3, (0, ("c" * 40 + "\n").encode(), b"")),
            (1, (0, ("c" * 40 + "\n").encode(), b"")),
            (2, (0, ("c" * 40 + "\n").encode(), b"")),
        ):
            changed = list(results)
            changed[index] = replacement
            with patch.object(module, "_fixed_root_boundaries", return_value=True), \
                    patch.object(module.os.path, "lexists", return_value=False):
                self.assertEqual(module._fixed_checks(contract, changed)[0], False)

    def test_verified_receipt_is_30_minutes_and_has_zero_private_authority(self):
        from crypto_quant.challenger_replacement_v3_activation_preflight import (
            build_fixed_v3_activation_preflight,
            load_fixed_v3_activation_preflight_bytes,
        )

        receipt = build_fixed_v3_activation_preflight(**verified_facts())
        self.assertEqual(receipt["status"], "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE")
        self.assertEqual(receipt["expires_at"], "2026-08-28T08:40:00.000Z")
        self.assertEqual(receipt["authority"], {
            "market_request_count": 3, "launchctl_read_count": 2,
            "launchctl_mutation_count": 0, "runtime_invocation_count": 0,
            "state_write_count": 0, "credential_count": 0,
            "account_request_count": 0, "broker_request_count": 0,
            "order_count": 0, "fund_movement_count": 0,
        })
        self.assertEqual(tuple(tuple(item["argv"]) for item in receipt["commands"]),
                         COMMANDS)
        body = canonical_json(receipt).encode()
        schema = json.loads((ROOT / "src/crypto_quant/schemas/"
            "challenger-replacement-v3-activation-preflight-v1.schema.json").read_text())
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(receipt)), [])
        self.assertEqual(
            load_fixed_v3_activation_preflight_bytes(
                body, contract_binding=verified_facts()["contract_binding"]
            ), receipt,
        )

    def test_nonzero_microseconds_normalize_and_failed_receipt_strictly_replays(self):
        from crypto_quant.challenger_replacement_v3_activation_preflight import (
            build_fixed_v3_activation_preflight,
            load_fixed_v3_activation_preflight_bytes,
        )

        facts = verified_facts()
        facts.update({
            "observed_at": NOW.replace(microsecond=149000),
            "paths_verified": False,
            "power_safe": False,
        })
        receipt = build_fixed_v3_activation_preflight(**facts)
        self.assertEqual(receipt["status"], "PREFLIGHT_FAILED_CLOSED")
        self.assertEqual(receipt["observed_at"], "2026-08-28T08:10:00.000Z")
        self.assertEqual(receipt["expires_at"], "2026-08-28T08:40:00.000Z")
        body = canonical_json(receipt).encode()
        schema = json.loads((ROOT / "src/crypto_quant/schemas/"
            "challenger-replacement-v3-activation-preflight-v1.schema.json").read_text())
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(receipt)), [])
        self.assertEqual(
            load_fixed_v3_activation_preflight_bytes(
                body, contract_binding=facts["contract_binding"]
            ),
            receipt,
        )

    def test_wrong_window_and_credentials_fail_closed(self):
        from crypto_quant.challenger_replacement_v3_activation_preflight import (
            build_fixed_v3_activation_preflight,
        )

        for change, reason in (
            ({"observed_at": datetime(2026, 8, 28, 8, 9, 59, tzinfo=timezone.utc)},
             "PREFLIGHT_INSTALL_WINDOW_UNSAFE"),
            ({"credential_count": 1, "clock": {
                "endpoint": "https://data-api.binance.vision/api/v3/time",
                "request_count": 0, "trust_hash": "0" * 64,
            }}, "PREFLIGHT_CREDENTIAL_BOUNDARY_PRESENT"),
        ):
            facts = verified_facts(); facts.update(change)
            receipt = build_fixed_v3_activation_preflight(**facts)
            self.assertEqual(receipt["status"], "PREFLIGHT_FAILED_CLOSED")
            self.assertIn(reason, receipt["reason_codes"])

    def test_wrong_command_transcript_fails_closed(self):
        from crypto_quant.challenger_replacement_v3_activation_preflight import (
            build_fixed_v3_activation_preflight,
        )

        facts = verified_facts()
        facts["commands"] = facts["commands"][:-1]
        receipt = build_fixed_v3_activation_preflight(**facts)
        self.assertEqual(receipt["status"], "PREFLIGHT_FAILED_CLOSED")
        self.assertIn("PREFLIGHT_COMMAND_EVIDENCE_INVALID", receipt["reason_codes"])

    def test_module_has_no_system_paper_dependency(self):
        from crypto_quant import challenger_replacement_v3_activation_preflight as module

        source = inspect.getsource(module).lower()
        self.assertNotIn("system_paper", source)
        self.assertNotIn("challenger_cohort", source)

    def test_fixed_collector_uses_contract_then_exact_read_only_boundaries(self):
        from crypto_quant import challenger_replacement_v3_activation_preflight as module

        contract = {"contract_id": "x", "contract_hash": "y"}
        contract_bytes = b"contract"
        results = [(0, b"ok", b"")] * len(COMMANDS)
        with patch.object(
            module, "load_fixed_published_v3_install_contract",
            return_value=(contract, contract_bytes, b"plist"),
        ), patch.object(module, "_machine", return_value=verified_facts()["machine"]), \
             patch.object(module, "_run_commands", return_value=results), \
             patch.object(module, "_fixed_checks", return_value=(True, True, True)), \
             patch.object(module, "_credential_count", return_value=0), \
             patch.object(module, "_clock", return_value=verified_facts()["clock"]), \
             patch.object(module, "_disk", return_value=verified_facts()["disk"]), \
             patch.object(module, "_now", return_value=NOW):
            receipt = module.collect_fixed_v3_activation_preflight()
        self.assertEqual(receipt["status"], "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE")
        self.assertEqual(receipt["contract_binding"]["file_sha256"],
                         hashlib.sha256(contract_bytes).hexdigest())


if __name__ == "__main__":
    unittest.main()
