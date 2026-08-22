import copy
import hashlib
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from tests.test_challenger_replacement_install_trust import (
    ROOT,
    temporary_workspace,
    valid_contract,
)


OBSERVED = datetime(2026, 8, 22, 8, 10, tzinfo=timezone.utc)
EMPTY_HASH = hashlib.sha256(b"").hexdigest()
FIXED_COMMANDS = (
    ("git", "remote", "get-url", "origin"),
    ("git", "rev-parse", "HEAD"),
    ("git", "rev-parse", "origin/main"),
    ("git", "rev-parse", "v0.68.0^{}"),
    ("git", "status", "--porcelain=v1", "--untracked-files=all"),
    ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-forward"),
    ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-replacement-v1"),
    ("/usr/bin/pmset", "-g", "custom"),
)


def verified_inputs():
    contract = valid_contract()
    return {
        "contract": contract,
        "contract_file_sha256": hashlib.sha256(
            canonical_json(contract).encode("utf-8")
        ).hexdigest(),
        "machine": {
            "system": "Darwin",
            "machine": "arm64",
            "uid": 501,
            "home": "/Users/chenm4",
            "timezone": "Asia/Shanghai",
        },
        "release_replayed": True,
        "paths_verified": True,
        "power_safe": True,
        "disk": {"free_bytes": 20_000_000_000, "free_inodes": 200_000},
        "clock": {
            "endpoint": "https://data-api.binance.vision/api/v3/time",
            "request_count": 3,
            "trust_hash": "a" * 64,
        },
        "credential_count": 0,
        "commands": [
            {
                "argv": list(argv),
                "exit_code": 0,
                "stdout_sha256": EMPTY_HASH,
                "stderr_sha256": EMPTY_HASH,
            }
            for argv in FIXED_COMMANDS
        ],
        "observed_at": OBSERVED,
    }


class ReplacementInstallPreflightTests(unittest.TestCase):
    def test_verified_receipt_has_exact_expiry_and_authority_counts(self):
        from crypto_quant.challenger_replacement_install_preflight import (
            build_replacement_install_preflight_receipt,
            load_replacement_install_preflight_bytes,
        )

        inputs = verified_inputs()
        receipt = build_replacement_install_preflight_receipt(**inputs)
        self.assertEqual(receipt["status"], "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE")
        self.assertEqual(receipt["observed_at"], "2026-08-22T08:10:00.000Z")
        self.assertEqual(receipt["expires_at"], "2026-08-22T08:40:00.000Z")
        self.assertEqual(receipt["authority"], {
            "github_request_count": 0,
            "market_request_count": 3,
            "launchctl_read_count": 2,
            "launchctl_mutation_count": 0,
            "runtime_invocation_count": 0,
            "state_write_count": 0,
            "credential_count": 0,
            "broker_request_count": 0,
            "order_count": 0,
        })
        body = canonical_json(receipt).encode("utf-8")
        self.assertEqual(
            load_replacement_install_preflight_bytes(
                body,
                contract=inputs["contract"],
                contract_file_sha256=inputs["contract_file_sha256"],
            ),
            receipt,
        )

    def test_verified_status_requires_fixed_post_boundary_install_window(self):
        from crypto_quant.challenger_replacement_install_preflight import (
            build_replacement_install_preflight_receipt,
        )

        for observed in (
            datetime(2026, 8, 22, 7, 59, 59, 999000, tzinfo=timezone.utc),
            datetime(2026, 8, 22, 8, 9, 59, 999000, tzinfo=timezone.utc),
            datetime(2026, 8, 22, 8, 30, 0, 1000, tzinfo=timezone.utc),
        ):
            with self.subTest(observed=observed):
                inputs = verified_inputs()
                inputs["observed_at"] = observed
                receipt = build_replacement_install_preflight_receipt(**inputs)
                self.assertEqual(receipt["status"], "PREFLIGHT_FAILED_CLOSED")
                self.assertIn("PREFLIGHT_INSTALL_WINDOW_UNSAFE",
                              receipt["reason_codes"])

    def test_credential_boundary_fails_and_requires_zero_clock_requests(self):
        from crypto_quant.challenger_replacement_install_preflight import (
            build_replacement_install_preflight_receipt,
        )

        inputs = verified_inputs()
        inputs["credential_count"] = 1
        inputs["clock"] = {
            "endpoint": "https://data-api.binance.vision/api/v3/time",
            "request_count": 0,
            "trust_hash": "0" * 64,
        }
        receipt = build_replacement_install_preflight_receipt(**inputs)
        self.assertEqual(receipt["status"], "PREFLIGHT_FAILED_CLOSED")
        self.assertIn("PREFLIGHT_CREDENTIAL_BOUNDARY_PRESENT", receipt["reason_codes"])
        self.assertEqual(receipt["authority"]["market_request_count"], 0)

    def test_unsupported_platform_has_zero_commands_and_network(self):
        from crypto_quant.challenger_replacement_install_preflight import (
            build_replacement_install_preflight_receipt,
        )

        inputs = verified_inputs()
        inputs.update({
            "machine": {
                "system": "Linux", "machine": "x86_64", "uid": 1000,
                "home": "/home/ci", "timezone": "UTC",
            },
            "release_replayed": False,
            "paths_verified": False,
            "power_safe": False,
            "disk": {"free_bytes": 0, "free_inodes": 0},
            "clock": {
                "endpoint": "https://data-api.binance.vision/api/v3/time",
                "request_count": 0,
                "trust_hash": "0" * 64,
            },
            "commands": [],
        })
        receipt = build_replacement_install_preflight_receipt(**inputs)
        self.assertEqual(receipt["status"], "PREFLIGHT_PLATFORM_UNSUPPORTED")
        self.assertEqual(receipt["commands"], [])
        self.assertEqual(receipt["authority"]["market_request_count"], 0)
        self.assertEqual(receipt["authority"]["launchctl_read_count"], 0)

    def test_unsupported_platform_rejects_nonzero_observation_evidence(self):
        from crypto_quant.challenger_replacement_install_preflight import (
            ReplacementInstallPreflightError,
            build_replacement_install_preflight_receipt,
        )

        inputs = verified_inputs()
        inputs["machine"] = {
            "system": "Linux", "machine": "x86_64", "uid": 1000,
            "home": "/home/ci", "timezone": "UTC",
        }
        with self.assertRaisesRegex(
            ReplacementInstallPreflightError,
            "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_INVALID",
        ):
            build_replacement_install_preflight_receipt(**inputs)

    def test_loader_rejects_extra_key_and_wrong_contract_binding(self):
        from crypto_quant.challenger_replacement_install_preflight import (
            ReplacementInstallPreflightError,
            build_replacement_install_preflight_receipt,
            load_replacement_install_preflight_bytes,
        )

        inputs = verified_inputs()
        receipt = build_replacement_install_preflight_receipt(**inputs)
        altered = copy.deepcopy(receipt)
        altered["extra"] = True
        with self.assertRaisesRegex(
            ReplacementInstallPreflightError,
            "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_INVALID",
        ):
            load_replacement_install_preflight_bytes(
                canonical_json(altered).encode("utf-8"),
                contract=inputs["contract"],
                contract_file_sha256=inputs["contract_file_sha256"],
            )
        wrong = valid_contract()
        wrong["contract_hash"] = "f" * 64
        with self.assertRaisesRegex(
            ReplacementInstallPreflightError,
            "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_INVALID",
        ):
            load_replacement_install_preflight_bytes(
                canonical_json(receipt).encode("utf-8"),
                contract=wrong,
                contract_file_sha256=inputs["contract_file_sha256"],
            )

    def test_loader_rejects_rehashed_semantically_inconsistent_receipt(self):
        from crypto_quant.challenger_replacement_install_preflight import (
            ReplacementInstallPreflightError,
            build_replacement_install_preflight_receipt,
            load_replacement_install_preflight_bytes,
        )
        from crypto_quant.canonical import stable_id
        from crypto_quant.evidence import artifact_self_hash

        inputs = verified_inputs()
        receipt = build_replacement_install_preflight_receipt(**inputs)
        receipt["status"] = "PREFLIGHT_FAILED_CLOSED"
        identity = {key: value for key, value in receipt.items()
                    if key not in ("receipt_id", "receipt_hash")}
        receipt["receipt_id"] = stable_id(
            "challenger_replacement_install_preflight", identity
        )
        receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
        with self.assertRaisesRegex(
            ReplacementInstallPreflightError,
            "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_INVALID",
        ):
            load_replacement_install_preflight_bytes(
                canonical_json(receipt).encode("utf-8"),
                contract=inputs["contract"],
                contract_file_sha256=inputs["contract_file_sha256"],
            )

    def test_supported_receipt_without_exact_command_evidence_is_not_verified(self):
        from crypto_quant.challenger_replacement_install_preflight import (
            build_replacement_install_preflight_receipt,
        )

        inputs = verified_inputs()
        inputs["commands"] = []
        receipt = build_replacement_install_preflight_receipt(**inputs)
        self.assertEqual(receipt["status"], "PREFLIGHT_FAILED_CLOSED")
        self.assertIn("PREFLIGHT_COMMAND_EVIDENCE_INVALID", receipt["reason_codes"])

    def test_builder_rejects_schema_invalid_negative_command_exit(self):
        from crypto_quant.challenger_replacement_install_preflight import (
            ReplacementInstallPreflightError,
            build_replacement_install_preflight_receipt,
        )

        inputs = verified_inputs()
        inputs["commands"][0]["exit_code"] = -9
        with self.assertRaisesRegex(
            ReplacementInstallPreflightError,
            "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_INVALID",
        ):
            build_replacement_install_preflight_receipt(**inputs)

    def test_observer_uses_fixed_checks_and_exactly_three_clock_gets(self):
        import crypto_quant.challenger_replacement_install_preflight as preflight

        inputs = verified_inputs()
        contract = inputs["contract"]
        command_results = [
            (0, b"fixed\n", b"") for _ in range(8)
        ]
        with mock.patch.object(
            preflight, "_load_fixed_contract", return_value=(contract, b"contract")
        ), mock.patch.object(
            preflight, "_machine", return_value=inputs["machine"]
        ), mock.patch.object(
            preflight, "_run_fixed_commands", return_value=command_results
        ) as commands, mock.patch.object(
            preflight, "_fixed_checks", return_value=(True, True)
        ), mock.patch.object(
            preflight, "_power_safe", return_value=True
        ), mock.patch.object(
            preflight, "_disk", return_value=inputs["disk"]
        ), mock.patch.object(
            preflight, "_credential_count", return_value=0
        ), mock.patch.object(
            preflight, "_clock", return_value=inputs["clock"]
        ) as clock, mock.patch.object(
            preflight, "_now", return_value=OBSERVED
        ):
            receipt = preflight.observe_fixed_replacement_install_preflight()
        self.assertEqual(receipt["status"], "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE")
        self.assertEqual(len(receipt["commands"]), 8)
        self.assertEqual(receipt["authority"]["market_request_count"], 3)
        commands.assert_called_once()
        clock.assert_called_once()

    def test_fixed_checks_require_bound_empty_event_and_start_roots(self):
        import crypto_quant.challenger_replacement_install_preflight as preflight

        with temporary_workspace() as directory:
            runtime = Path(directory) / "runtime"
            event_root = runtime / "state/events"
            start_root = runtime / "evidence/start-receipts"
            log = runtime / "log"
            event_root.mkdir(parents=True, mode=0o700)
            start_root.mkdir(parents=True, mode=0o700)
            log.mkdir(mode=0o700)
            for path in (runtime, runtime / "state", runtime / "evidence"):
                path.chmod(0o700)
            contract = valid_contract()
            contract["paths"].update({
                "runtime_root": str(runtime), "event_root": str(event_root),
                "start_receipt_root": str(start_root),
                "stdout": str(log / "stdout.log"),
                "stderr": str(log / "stderr.log"),
                "target_plist": str(Path(directory) / "agent.plist"),
            })
            entry = event_root.stat()
            contract["event_root"].update({
                "path": str(event_root), "device": entry.st_dev,
                "inode": entry.st_ino, "owner_uid": os.getuid(),
            })
            head = contract["candidate_release"]["peeled_commit"].encode() + b"\n"
            results = [
                (0, b"https://github.com/cjl308868584-lang/crypto-quant-core.git\n", b""),
                (0, head, b""), (0, head, b""), (0, head, b""),
                (0, b"", b""), (113, b"", b""), (113, b"", b""),
                (0, b" sleep 0\n", b""),
            ]
            self.assertEqual(preflight._fixed_checks(contract, results),
                             (True, True))
            (event_root / "unexpected").write_bytes(b"x")
            self.assertEqual(preflight._fixed_checks(contract, results),
                             (True, False))

    def test_observer_skips_commands_and_network_on_unsupported_platform(self):
        import crypto_quant.challenger_replacement_install_preflight as preflight

        contract = verified_inputs()["contract"]
        machine = {
            "system": "Linux", "machine": "x86_64", "uid": 1000,
            "home": "/home/ci", "timezone": "UTC",
        }
        with mock.patch.object(
            preflight, "_load_fixed_contract", return_value=(contract, b"contract")
        ), mock.patch.object(
            preflight, "_machine", return_value=machine
        ), mock.patch.object(preflight, "_run_fixed_commands") as commands, \
             mock.patch.object(preflight, "_clock") as clock, \
             mock.patch.object(preflight, "_now", return_value=OBSERVED):
            receipt = preflight.observe_fixed_replacement_install_preflight()
        self.assertEqual(receipt["status"], "PREFLIGHT_PLATFORM_UNSUPPORTED")
        commands.assert_not_called()
        clock.assert_not_called()

    def test_credential_boundary_skips_clock_collection(self):
        import crypto_quant.challenger_replacement_install_preflight as preflight

        inputs = verified_inputs()
        with mock.patch.object(
            preflight, "_load_fixed_contract",
            return_value=(inputs["contract"], b"contract")
        ), mock.patch.object(
            preflight, "_machine", return_value=inputs["machine"]
        ), mock.patch.object(
            preflight, "_run_fixed_commands",
            return_value=[(0, b"fixed\n", b"") for _ in range(8)]
        ), mock.patch.object(
            preflight, "_fixed_checks", return_value=(True, True)
        ), mock.patch.object(
            preflight, "_power_safe", return_value=True
        ), mock.patch.object(
            preflight, "_disk", return_value=inputs["disk"]
        ), mock.patch.object(
            preflight, "_credential_count", return_value=1
        ), mock.patch.object(preflight, "_clock") as clock, \
             mock.patch.object(preflight, "_now", return_value=OBSERVED):
            receipt = preflight.observe_fixed_replacement_install_preflight()
        self.assertIn(
            "PREFLIGHT_CREDENTIAL_BOUNDARY_PRESENT", receipt["reason_codes"]
        )
        clock.assert_not_called()

    def test_publisher_uses_fixed_owner_only_root_and_deterministic_name(self):
        import crypto_quant.challenger_replacement_install_preflight as preflight

        receipt = preflight.build_replacement_install_preflight_receipt(
            **verified_inputs()
        )
        with mock.patch.object(
            preflight, "observe_fixed_replacement_install_preflight",
            return_value=receipt
        ), mock.patch.object(
            preflight, "_ensure_preflight_root"
        ) as ensure, mock.patch.object(
            preflight, "_publish_contract_exact",
            return_value=("PUBLISHED", object())
        ) as publish:
            result = preflight.publish_fixed_replacement_install_preflight()
        self.assertEqual(result["receipt"], receipt)
        ensure.assert_called_once()
        self.assertEqual(
            publish.call_args.args[1], receipt["receipt_id"] + ".json"
        )

    def test_command_boundary_rejects_non_utf8_and_bounded_runner_failure(self):
        import crypto_quant.challenger_replacement_install_preflight as preflight

        with mock.patch.object(
            preflight, "_run", return_value=(0, b"\xff", b"")
        ):
            with self.assertRaisesRegex(
                preflight.ReplacementInstallPreflightError,
                "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_COMMAND_FAILED",
            ):
                preflight._run_fixed_commands()
        with mock.patch.object(
            preflight, "_run", side_effect=ValueError("PREFLIGHT_COMMAND_FAILED")
        ):
            with self.assertRaisesRegex(ValueError, "PREFLIGHT_COMMAND_FAILED"):
                preflight._run_fixed_commands()

    def test_wrong_release_or_loaded_service_fails_fixed_checks(self):
        import crypto_quant.challenger_replacement_install_preflight as preflight

        contract = valid_contract()
        commit = contract["candidate_release"]["peeled_commit"].encode()
        results = [
            (0, b"https://github.com/cjl308868584-lang/crypto-quant-core.git\n", b""),
            (0, commit + b"\n", b""), (0, commit + b"\n", b""),
            (0, b"f" * 40 + b"\n", b""), (0, b"", b""),
            (0, b"loaded", b""), (1, b"", b""),
            (0, b" sleep 0\n", b""),
        ]
        release, paths = preflight._fixed_checks(contract, results)
        self.assertFalse(release)
        self.assertFalse(paths)

    def test_contract_failure_happens_before_any_receipt_publication(self):
        import crypto_quant.challenger_replacement_install_preflight as preflight

        with mock.patch.object(
            preflight, "_load_fixed_contract", side_effect=ValueError("invalid")
        ), mock.patch.object(preflight, "_ensure_preflight_root") as ensure, \
             mock.patch.object(preflight, "_publish_contract_exact") as publish:
            with self.assertRaisesRegex(ValueError, "invalid"):
                preflight.publish_fixed_replacement_install_preflight()
        ensure.assert_not_called()
        publish.assert_not_called()

    def test_cli_rejects_all_arguments_before_collection(self):
        import crypto_quant.challenger_replacement_install_preflight_cli as cli

        with mock.patch.object(cli, "publish_fixed_replacement_install_preflight") as publish:
            with self.assertRaises(SystemExit):
                cli.main(["--url", "https://not-allowed.example"])
            publish.assert_not_called()

    def test_schema_mirror_is_valid(self):
        name = "challenger-replacement-install-preflight-v1.schema.json"
        config = ROOT / "config" / name
        package = ROOT / "src/crypto_quant/schemas" / name
        self.assertEqual(config.read_bytes(), package.read_bytes())
        Draft202012Validator.check_schema(json.loads(config.read_text()))


if __name__ == "__main__":
    unittest.main()
