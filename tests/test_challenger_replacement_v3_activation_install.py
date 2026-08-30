import unittest
import hashlib
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from jsonschema import Draft202012Validator
from crypto_quant.canonical import canonical_json, stable_id, utc_datetime
from crypto_quant.evidence import artifact_self_hash

ROOT = Path(__file__).resolve().parents[1]


NOW = datetime(2026, 8, 28, 8, 15, tzinfo=timezone.utc)
REAL_INSTALL_WITH_MILLISECONDS = datetime(
    2026, 8, 30, 16, 14, 6, 101000, tzinfo=timezone.utc
)


def inputs():
    contract = {
        "contract_id": "challenger_replacement_v3_install_contract_" + "a" * 64,
        "contract_hash": "b" * 64,
        "release": {"tag": "v0.78.7", "peeled_commit": "c" * 40,
                    "manifest_version": "1.79.0", "manifest_hash": "d" * 64},
        "snapshot": {"root": "/fixed/snapshot", "tree_hash": "e" * 64,
                     "root_device": "1", "root_inode": "2",
                     "file_count": 10, "total_size_bytes": 1000},
        "event_root": {"path": "/fixed/events", "device": "3", "inode": "4",
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
    value = {
        "contract": contract, "contract_bytes": b"contract",
        "preflight": preflight, "preflight_bytes": b"preflight",
        "plist_bytes": b"plist",
    }
    value.update(recovery_inputs())
    return value


def recovery_inputs():
    return {
        "recovery": {
            "receipt_id": "challenger_replacement_v3_partial_install_recovery_"
            + "2" * 64,
            "receipt_hash": "3" * 64,
            "status": "PARTIAL_INSTALL_RECOVERY_ELIGIBLE_NOT_EXECUTED",
        },
        "recovery_bytes": b"recovery",
    }


class ChallengerReplacementV3ActivationInstallTests(unittest.TestCase):
    def test_install_inputs_require_strict_recovery_receipt_before_commands(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        source = inputs()
        with patch.object(
            module, "_load_fixed_contract_inputs", return_value=(
                source["contract"], b"contract", b"plist"
            )
        ), patch.object(
            module, "_load_fixed_preflight_candidates", return_value=[
                (source["preflight"], b"preflight")
            ]
        ), patch.object(module, "_now", return_value=NOW), patch.object(
            module, "_load_fixed_recovery_inputs", side_effect=ValueError(
                "CHALLENGER_REPLACEMENT_V3_INSTALL_RECOVERY_RECEIPT_REQUIRED"
            )
        ) as recovery:
            with self.assertRaisesRegex(
                ValueError,
                "CHALLENGER_REPLACEMENT_V3_INSTALL_RECOVERY_RECEIPT_REQUIRED",
            ):
                module._load_fixed_install_inputs()
        recovery.assert_called_once_with(
            source["contract"], b"contract", b"plist"
        )

    def test_install_receipt_binds_exact_recovery_receipt(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        source = inputs()
        record = {
            "path": "/fixed/agent.plist", "device": 5, "inode": 6,
            "owner_uid": 501, "mode": 384, "link_count": 1,
            "size_bytes": 5, "sha256": hashlib.sha256(b"plist").hexdigest(),
        }
        commands = [
            module._transcript(
                ("/bin/launchctl", "print", source["contract"]["service"]["identity"]),
                (113, b"", b""),
            ),
            module._transcript(
                ("/bin/launchctl", "bootstrap", "gui/501", "/fixed/agent.plist"),
                (0, b"", b""),
            ),
            module._transcript(
                ("/bin/launchctl", "print", source["contract"]["service"]["identity"]),
                (0, b"ok", b""),
            ),
        ]
        receipt = module.build_fixed_v3_activation_install_receipt(
            **source,
            installed_at=NOW,
            plist_record=record,
            commands=commands,
            status="INSTALLED_WAITING_FOR_FIRST_NATURAL_OPPORTUNITY",
            reason_codes=[],
        )
        self.assertEqual(
            receipt["recovery_binding"],
            module._binding(source["recovery"], b"recovery", "receipt"),
        )
        body = canonical_json(receipt).encode("utf-8")
        self.assertEqual(
            module.load_fixed_v3_activation_install_receipt_bytes(
                body,
                contract=source["contract"],
                contract_bytes=b"contract",
                preflight=source["preflight"],
                preflight_bytes=b"preflight",
                recovery=source["recovery"],
                recovery_bytes=b"recovery",
            ),
            receipt,
        )

    def test_recovery_gate_requires_exact_current_observation(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        source = inputs()
        source["contract"]["release"]["tag"] = "v0.78.7"
        source["contract"]["paths"].update({
            "target_plist": "/fixed/new-v0.78.7.plist",
            "recovery_receipt_root": "/fixed/recovery-v0.78.7",
        })
        plan = {
            "candidate": {
                "release_tag": "v0.78.7",
                "target_plist": "/fixed/new-v0.78.7.plist",
                "recovery_receipt_root": "/fixed/recovery-v0.78.7",
            }
        }
        observation = {
            "service_state": "DISABLED_AND_NOT_LOADED",
            "preserved_file_sha256": {},
        }
        recovery = dict(recovery_inputs()["recovery"], observation=observation)
        with patch.object(
            module,
            "load_fixed_v3_partial_install_recovery_plan",
            return_value=(plan, b"plan"),
        ), patch.object(
            module,
            "load_fixed_published_v3_partial_install_recovery_receipt",
            return_value=(recovery, b"recovery"),
        ), patch.object(
            module,
            "_verify_preserved_partial_install",
            return_value=observation,
        ):
            self.assertEqual(
                module._load_fixed_recovery_inputs(
                    source["contract"], b"contract", b"plist"
                ),
                {"recovery": recovery, "recovery_bytes": b"recovery"},
            )

        with patch.object(
            module,
            "load_fixed_v3_partial_install_recovery_plan",
            return_value=(plan, b"plan"),
        ), patch.object(
            module,
            "load_fixed_published_v3_partial_install_recovery_receipt",
            return_value=(recovery, b"recovery"),
        ), patch.object(
            module,
            "_verify_preserved_partial_install",
            return_value={"service_state": "LOADED"},
        ):
            with self.assertRaisesRegex(
                ValueError,
                "CHALLENGER_REPLACEMENT_V3_INSTALL_RECOVERY_RECEIPT_REQUIRED",
            ):
                module._load_fixed_recovery_inputs(
                    source["contract"], b"contract", b"plist"
                )
    @staticmethod
    def _successful_receipt_inputs(installed_at=NOW):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        source = inputs()
        source["preflight"]["observed_at"] = utc_datetime(
            (installed_at - timedelta(minutes=2)).replace(microsecond=0)
        )
        source["preflight"]["expires_at"] = utc_datetime(
            (installed_at + timedelta(minutes=28)).replace(microsecond=0)
        )
        record = {
            "path": "/fixed/agent.plist", "device": 5, "inode": 6,
            "owner_uid": 501, "mode": 384, "link_count": 1,
            "size_bytes": 5, "sha256": hashlib.sha256(b"plist").hexdigest(),
        }
        commands = [
            module._transcript(
                ("/bin/launchctl", "print", source["contract"]["service"]["identity"]),
                (113, b"", b""),
            ),
            module._transcript(
                ("/bin/launchctl", "bootstrap", "gui/501", "/fixed/agent.plist"),
                (0, b"", b""),
            ),
            module._transcript(
                ("/bin/launchctl", "print", source["contract"]["service"]["identity"]),
                (0, b"ok", b""),
            ),
        ]
        receipt = module.build_fixed_v3_activation_install_receipt(
            **source, installed_at=installed_at, plist_record=record,
            commands=commands,
            status="INSTALLED_WAITING_FOR_FIRST_NATURAL_OPPORTUNITY",
            reason_codes=[],
        )
        return module, source, receipt

    def test_nonzero_millisecond_install_time_is_canonical_and_strictly_replays(self):
        module, source, receipt = self._successful_receipt_inputs(
            REAL_INSTALL_WITH_MILLISECONDS
        )

        self.assertEqual(receipt["installed_at"], "2026-08-30T16:14:06.000Z")
        temporal_fields = {
            key: value for key, value in receipt.items()
            if key.endswith("_at") or key.endswith("_scheduled_for")
        }
        self.assertEqual(
            temporal_fields,
            {
                "installed_at": "2026-08-30T16:14:06.000Z",
                "first_eligible_scheduled_for": "2026-08-30T20:00:00.000Z",
            },
        )
        body = canonical_json(receipt).encode("utf-8")
        schema = json.loads((
            ROOT / "src/crypto_quant/schemas/"
            "challenger-replacement-v3-activation-install-receipt-v1.schema.json"
        ).read_text())
        self.assertEqual(
            list(Draft202012Validator(schema).iter_errors(receipt)), []
        )
        replayed = module.load_fixed_v3_activation_install_receipt_bytes(
            body, contract=source["contract"], contract_bytes=b"contract",
            preflight=source["preflight"], preflight_bytes=b"preflight",
            recovery=source["recovery"], recovery_bytes=b"recovery",
        )
        self.assertEqual(replayed, receipt)
        self.assertEqual(replayed["receipt_id"], receipt["receipt_id"])
        self.assertEqual(replayed["receipt_hash"], receipt["receipt_hash"])

    def test_partial_v0785_install_fixture_fails_closed_without_overwrite(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "Library" / "LaunchAgents" / "agent.plist"
            receipts = root / "runtime" / "deployment" / "install-receipts-v0.78.5"
            events = root / "runtime" / "state" / "events"
            stdout = root / "runtime" / "log" / "stdout.log"
            stderr = root / "runtime" / "log" / "stderr.log"
            target.parent.mkdir(parents=True)
            receipts.mkdir(parents=True)
            events.mkdir(parents=True)
            target.write_bytes(b"immutable-v0.78.5-target-plist")
            os.chmod(target, 0o600)

            source = inputs()
            source["contract"]["paths"].update({
                "target_plist": str(target),
                "install_receipt_root": str(receipts),
                "event_root": str(events),
                "stdout": str(stdout),
                "stderr": str(stderr),
            })
            source["preflight"]["observed_at"] = "2026-08-30T16:12:50.000Z"
            source["preflight"]["expires_at"] = "2026-08-30T16:42:50.000Z"
            record = {
                "path": str(target), "device": target.stat().st_dev,
                "inode": target.stat().st_ino, "owner_uid": os.getuid(),
                "mode": 0o600, "link_count": 1,
                "size_bytes": target.stat().st_size,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
            commands = [
                module._transcript(
                    ("/bin/launchctl", "print", source["contract"]["service"]["identity"]),
                    (113, b"", b""),
                ),
                module._transcript(
                    ("/bin/launchctl", "bootstrap", "gui/501", str(target)),
                    (0, b"", b""),
                ),
                module._transcript(
                    ("/bin/launchctl", "print", source["contract"]["service"]["identity"]),
                    (0, b"ok", b""),
                ),
            ]
            invalid = module.build_fixed_v3_activation_install_receipt(
                **source, installed_at=REAL_INSTALL_WITH_MILLISECONDS,
                plist_record=record, commands=commands,
                status="INSTALLED_WAITING_FOR_FIRST_NATURAL_OPPORTUNITY",
                reason_codes=[],
            )
            invalid["installed_at"] = "2026-08-30T16:14:06.101Z"
            identity = {
                key: value for key, value in invalid.items()
                if key not in ("receipt_id", "receipt_hash")
            }
            invalid["receipt_id"] = stable_id(
                "challenger_replacement_v3_activation_install", identity
            )
            invalid["receipt_hash"] = artifact_self_hash(invalid, "receipt_hash")
            invalid_body = canonical_json(invalid).encode("utf-8")
            invalid_path = receipts / (invalid["receipt_id"] + ".json")
            invalid_path.write_bytes(invalid_body)
            os.chmod(invalid_path, 0o600)
            before = {
                target: (target.read_bytes(), target.stat()),
                invalid_path: (invalid_path.read_bytes(), invalid_path.stat()),
            }

            with self.assertRaisesRegex(ValueError, "INSTALL_RECEIPT_INVALID"):
                module.load_fixed_v3_activation_install_receipt_bytes(
                    invalid_body, contract=source["contract"],
                    contract_bytes=source["contract_bytes"],
                    preflight=source["preflight"],
                    preflight_bytes=source["preflight_bytes"],
                    recovery=source["recovery"],
                    recovery_bytes=source["recovery_bytes"],
                )

            with patch.object(
                module, "_load_fixed_install_inputs", return_value=source,
            ), patch.object(
                module, "_now", return_value=REAL_INSTALL_WITH_MILLISECONDS,
            ), patch.object(
                module, "_command", return_value=(113, b"", b""),
            ) as command, patch.object(module, "_publish_plist") as publish:
                with self.assertRaisesRegex(
                    ValueError, "INSTALL_EXISTING_STATE_CONFLICT"
                ):
                    module.install_fixed_v3_simulation_launch_agent()

            command.assert_called_once_with((
                "/bin/launchctl", "print",
                "gui/501/local.crypto-quant.challenger-replacement-v1",
            ))
            publish.assert_not_called()
            self.assertEqual(tuple(events.iterdir()), ())
            self.assertFalse(stdout.exists())
            self.assertFalse(stderr.exists())
            for path, (body, stat) in before.items():
                after = path.stat()
                self.assertEqual(path.read_bytes(), body)
                self.assertEqual(
                    (after.st_dev, after.st_ino, after.st_mode, after.st_nlink,
                     after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                    (stat.st_dev, stat.st_ino, stat.st_mode, stat.st_nlink,
                     stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns),
                )

    def test_preflight_loader_uses_only_the_contract_release_scoped_root(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        contract = inputs()["contract"]
        contract["paths"]["preflight_root"] = "/fixed/preflight-receipts-v0.78.7"
        with patch.object(module, "_open_directory", return_value=(9, object())) as open_dir, \
                patch.object(module.os, "listdir", return_value=[]), \
                patch.object(module, "_close_descriptor"):
            self.assertEqual(module._load_fixed_preflight_candidates(contract, b"contract"), [])
        self.assertEqual(open_dir.call_args.args[0], Path(
            "/fixed/preflight-receipts-v0.78.7"
        ))

    def test_revalidate_compares_large_decimal_identities_to_os_stat(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        large = 2**60 + 123
        fixed = inputs()
        fixed["contract"]["snapshot"].update({
            "root_device": str(large + 1), "root_inode": str(large + 2),
        })
        fixed["contract"]["event_root"].update({
            "device": str(large + 3), "inode": str(large + 4),
        })
        fixed["contract"]["python"] = {
            "path": "/usr/bin/python3", "device": str(large + 5),
            "inode": str(large + 6), "owner_uid": 0, "mode": 365,
            "link_count": 1, "size_bytes": 100, "sha256": "a" * 64,
            "sys_version": "3.9", "import_stdout_sha256": "b" * 64,
            "import_stderr_sha256": "c" * 64,
        }
        observed_event = dict(fixed["contract"]["event_root"])
        observed_event.update({"device": large + 3, "inode": large + 4})
        observed_python = dict(fixed["contract"]["python"])
        observed_python.update({"device": large + 5, "inode": large + 6})
        record = {"device": 1, "inode": 2}
        with patch.object(
            module, "_load_fixed_contract_inputs", return_value=(
                fixed["contract"], fixed["contract_bytes"], fixed["plist_bytes"]
            ),
        ), patch.object(
            module, "_load_fixed_preflight_candidates", return_value=[
                (fixed["preflight"], fixed["preflight_bytes"])
            ],
        ), patch.object(
            module, "_load_fixed_recovery_inputs", return_value={
                "recovery": fixed["recovery"],
                "recovery_bytes": fixed["recovery_bytes"],
            },
        ), patch.object(
            module, "_target_absent", return_value=False,
        ), patch.object(
            module, "_publish_plist", return_value=("ALREADY_PUBLISHED", record),
        ), patch.object(
            module, "_fixed_empty_event_root_identity", return_value=observed_event,
        ), patch.object(
            module, "_fixed_python_identity", return_value=observed_python,
        ):
            module._revalidate(fixed, record)

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
            "recovery_binding": module._binding(
                source["recovery"], b"recovery", "receipt"
            ),
            "plist": module._serialize_filesystem_identity({
                "path": "/fixed/agent.plist", "device": 1, "inode": 2,
                "owner_uid": 501, "mode": 384, "link_count": 1,
                "size_bytes": 5, "sha256": hashlib.sha256(b"plist").hexdigest(),
            }),
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
                 module, "_load_fixed_recovery_inputs",
                 return_value=recovery_inputs(),
             ) as load_recovery, patch.object(
                 module, "load_fixed_v3_activation_install_receipt_bytes",
                 return_value=receipt,
             ), patch.object(module, "_revalidate"), patch.object(
                 module, "_close_descriptor"
             ), patch.object(
                 module, "_select_current_preflight",
                 side_effect=AssertionError("current selector must not run after install"),
             ):
            loaded, found_receipt, found_body = (
                module._load_fixed_successful_install_receipt()
            )
        self.assertEqual(loaded, source)
        self.assertEqual(found_receipt, receipt)
        self.assertEqual(found_body, body)
        self.assertEqual(load_recovery.call_count, 2)
        for call in load_recovery.call_args_list:
            self.assertTrue(call.kwargs["historical"])
            self.assertEqual(
                call.kwargs["expected_binding"], receipt["recovery_binding"]
            )

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
            recovery=source["recovery"], recovery_bytes=b"recovery",
        ), receipt)

    def test_receipt_encodes_large_plist_identity_as_decimal_strings(self):
        from crypto_quant import challenger_replacement_v3_activation_install as module

        source = inputs()
        large = 2**60 + 123
        record = {
            "path": "/fixed/agent.plist", "device": large + 1,
            "inode": large + 2, "owner_uid": 501, "mode": 384,
            "link_count": 1, "size_bytes": 5,
            "sha256": hashlib.sha256(b"plist").hexdigest(),
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
        self.assertEqual(receipt["plist"]["device"], str(large + 1))
        self.assertEqual(receipt["plist"]["inode"], str(large + 2))
        body = canonical_json(receipt).encode()
        self.assertEqual(module.load_fixed_v3_activation_install_receipt_bytes(
            body, contract=source["contract"], contract_bytes=b"contract",
            preflight=source["preflight"], preflight_bytes=b"preflight",
            recovery=source["recovery"], recovery_bytes=b"recovery",
        ), receipt)


if __name__ == "__main__":
    unittest.main()
