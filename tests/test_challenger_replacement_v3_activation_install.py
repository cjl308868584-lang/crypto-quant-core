import unittest
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from jsonschema import Draft202012Validator
from crypto_quant.canonical import canonical_json

ROOT = Path(__file__).resolve().parents[1]


NOW = datetime(2026, 8, 28, 8, 15, tzinfo=timezone.utc)


def inputs():
    contract = {
        "contract_id": "challenger_replacement_v3_install_contract_" + "a" * 64,
        "contract_hash": "b" * 64,
        "release": {"tag": "v0.78.0", "peeled_commit": "c" * 40,
                    "manifest_version": "1.72.0", "manifest_hash": "d" * 64},
        "snapshot": {"root": "/fixed/snapshot", "tree_hash": "e" * 64,
                     "root_device": 1, "root_inode": 2,
                     "file_count": 10, "total_size_bytes": 1000},
        "event_root": {"path": "/fixed/events", "device": 3, "inode": 4,
                       "owner_uid": 501, "mode": 448,
                       "initial_event_count": 0,
                       "initial_orphan_staging_count": 0},
        "runtime": {"module": "crypto_quant.challenger_replacement_v3_installed_runtime"},
        "service": {"identity": "gui/501/local.crypto-quant.challenger-replacement-v1"},
        "paths": {"target_plist": "/fixed/agent.plist",
                  "install_receipt_root": "/fixed/receipts"},
    }
    preflight = {
        "receipt_id": "challenger_replacement_v3_activation_preflight_" + "f" * 64,
        "receipt_hash": "1" * 64,
        "status": "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE",
        "observed_at": "2026-08-28T08:10:00.000Z",
        "expires_at": "2026-08-28T08:40:00.000Z",
    }
    return {
        "contract": contract, "contract_bytes": b"contract",
        "preflight": preflight, "preflight_bytes": b"preflight",
        "plist_bytes": b"plist",
    }


class ChallengerReplacementV3ActivationInstallTests(unittest.TestCase):
    def test_current_preflight_ignores_expired_success_and_selects_new_success(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        expired = inputs()["preflight"]
        expired_body = b"expired"
        current = dict(expired)
        current.update({
            "receipt_id": "challenger_replacement_v3_activation_preflight_" + "2" * 64,
            "observed_at": "2026-08-28T08:14:00.000Z",
            "expires_at": "2026-08-28T08:44:00.000Z",
        })
        expired = dict(expired, expires_at="2026-08-28T08:14:00.000Z")

        self.assertEqual(
            module._select_current_preflight(
                [(expired, expired_body), (current, b"current")], NOW
            ),
            (current, b"current"),
        )

    def test_two_simultaneously_valid_preflights_fail_closed(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        first = inputs()["preflight"]
        second = dict(first, receipt_id=(
            "challenger_replacement_v3_activation_preflight_" + "2" * 64
        ))
        with self.assertRaisesRegex(ValueError, "INSTALL_INPUTS_REQUIRED"):
            module._select_current_preflight(
                [(first, b"first"), (second, b"second")], NOW
            )

    def test_installed_preflight_binding_replays_expired_exact_receipt(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        expired = dict(
            inputs()["preflight"], expires_at="2026-08-28T08:14:00.000Z"
        )
        expired_body = b"expired"
        current = dict(expired, receipt_id=(
            "challenger_replacement_v3_activation_preflight_" + "2" * 64
        ), observed_at="2026-08-28T08:14:00.000Z",
                       expires_at="2026-08-28T08:44:00.000Z")
        binding = module._binding(expired, expired_body, "receipt")

        self.assertEqual(
            module._select_bound_preflight(
                [(expired, expired_body), (current, b"current")], binding
            ),
            (expired, expired_body),
        )

    def test_successful_install_loader_uses_receipt_binding_not_current_window(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        source = inputs()
        binding = module._binding(source["preflight"], b"preflight", "receipt")
        receipt = {
            "receipt_id": "installed", "preflight_binding": binding,
            "status": "INSTALLED_WAITING_FOR_FIRST_NATURAL_OPPORTUNITY",
        }
        body = canonical_json(receipt).encode("utf-8")
        with patch.object(module, "_load_fixed_contract_inputs", return_value=(
            source["contract"], b"contract", b"plist"
        )), patch.object(module, "_open_directory", return_value=(9, object())), \
             patch.object(module.os, "listdir", return_value=["installed.json"]), \
             patch.object(module, "_read_published_exact", return_value=(body, {})), \
             patch.object(module, "_load_fixed_preflight_candidates", return_value=[
                 (source["preflight"], b"preflight")
             ]), patch.object(
                 module, "load_fixed_v3_activation_install_receipt_bytes",
                 return_value=receipt,
             ), patch.object(module, "_close_descriptor"), patch.object(
                 module, "_select_current_preflight",
                 side_effect=AssertionError("current selector must not run after install"),
             ):
            loaded, found_receipt, found_body = (
                module._load_fixed_successful_install_receipt()
            )
        self.assertEqual(loaded, source)
        self.assertEqual(found_receipt, receipt)
        self.assertEqual(found_body, body)

    def test_success_uses_only_print_bootstrap_print(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        calls = []
        def command(argv):
            calls.append(tuple(argv))
            return (113, b"", b"") if len(calls) == 1 else (0, b"ok", b"")

        with patch.object(module, "_load_fixed_install_inputs", return_value=inputs()), \
             patch.object(module, "_now", return_value=NOW), \
             patch.object(module, "_command", side_effect=command), \
             patch.object(module, "_target_absent", return_value=True), \
             patch.object(module, "_publish_plist", return_value=("PUBLISHED", {"inode": 1})), \
             patch.object(module, "_revalidate", return_value=None), \
             patch.object(module, "_post_print_valid", return_value=True), \
             patch.object(module, "_finish", return_value={"status": "INSTALLED"}):
            self.assertEqual(module.install_fixed_v3_simulation_launch_agent(),
                             {"status": "INSTALLED"})
        self.assertEqual(calls, [
            ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-replacement-v1"),
            ("/bin/launchctl", "bootstrap", "gui/501", "/fixed/agent.plist"),
            ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-replacement-v1"),
        ])

    def test_expired_preflight_has_zero_command_and_zero_plist(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        expired = inputs()
        expired["preflight"]["expires_at"] = "2026-08-28T08:14:00.000Z"
        with patch.object(module, "_load_fixed_install_inputs", return_value=expired), \
             patch.object(module, "_now", return_value=NOW), \
             patch.object(module, "_command") as command, \
             patch.object(module, "_publish_plist") as publish:
            with self.assertRaisesRegex(ValueError, "PREFLIGHT_EXPIRED"):
                module.install_fixed_v3_simulation_launch_agent()
        command.assert_not_called(); publish.assert_not_called()

    def test_receipt_is_canonical_and_derives_next_natural_opportunity(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module
        from crypto_quant.canonical import canonical_json

        source = inputs()
        record = {
            "path": "/fixed/agent.plist", "device": 5, "inode": 6,
            "owner_uid": 501, "mode": 384, "link_count": 1,
            "size_bytes": 5, "sha256": hashlib.sha256(b"plist").hexdigest(),
        }
        commands = [
            module._transcript(("/bin/launchctl", "print", source["contract"]["service"]["identity"]), (113, b"", b"")),
            module._transcript(("/bin/launchctl", "bootstrap", "gui/501", "/fixed/agent.plist"), (0, b"", b"")),
            module._transcript(("/bin/launchctl", "print", source["contract"]["service"]["identity"]), (0, b"ok", b"")),
        ]
        receipt = module.build_fixed_v3_activation_install_receipt(
            **source, installed_at=NOW, plist_record=record, commands=commands,
            status="INSTALLED_WAITING_FOR_FIRST_NATURAL_OPPORTUNITY",
            reason_codes=[],
        )
        self.assertEqual(receipt["first_eligible_scheduled_for"],
                         "2026-08-28T12:00:00.000Z")
        body = canonical_json(receipt).encode()
        schema = json.loads((ROOT / "src/crypto_quant/schemas/"
            "challenger-replacement-v3-activation-install-receipt-v1.schema.json").read_text())
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(receipt)), [])
        self.assertEqual(module.load_fixed_v3_activation_install_receipt_bytes(
            body, contract=source["contract"], contract_bytes=b"contract",
            preflight=source["preflight"], preflight_bytes=b"preflight",
        ), receipt)


if __name__ == "__main__":
    unittest.main()
