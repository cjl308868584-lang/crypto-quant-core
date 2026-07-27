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
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.evidence import artifact_self_hash
from crypto_quant.local_scheduler import (
    LocalSchedulerError,
    build_local_scheduler_contract,
    local_scheduler_contract_reasons,
    local_scheduler_contract_trust_hash,
    publish_local_scheduler_contract,
)
from crypto_quant.local_scheduler_cli import main


ROOT = Path(__file__).parents[1]
UTC = timezone.utc


def credential(path, value):
    path.write_text(value, encoding="ascii")
    path.chmod(0o600)
    return path


def scheduler_inputs(root):
    secrets = root / "secrets"
    secrets.mkdir()
    return {
        "repository_root": ROOT,
        "runtime_root": root / "runtime",
        "python_executable": Path(sys.executable),
        "api_key_file": credential(
            secrets / "api-key", "K" * 32
        ),
        "api_secret_file": credential(
            secrets / "api-secret", "S" * 32
        ),
        "worker_id": "mac-mini-a",
        "created_at": datetime(
            2026, 7, 28, 1, 0, tzinfo=UTC
        ),
    }


class LocalSchedulerTests(unittest.TestCase):
    def test_contract_replays_fixed_launchd_without_secret_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = scheduler_inputs(root)
            contract, body = build_local_scheduler_contract(**inputs)
            trust = local_scheduler_contract_trust_hash(contract)
            self.assertEqual(
                local_scheduler_contract_reasons(
                    contract, body, trust
                ),
                (),
            )
            plist = plistlib.loads(body)
            self.assertEqual(
                plist["Label"],
                "local.crypto-quant.context-complete-cycle",
            )
            self.assertEqual(
                plist["StartCalendarInterval"],
                [
                    {"Hour": hour, "Minute": 6}
                    for hour in (0, 4, 8, 12, 16, 20)
                ],
            )
            self.assertTrue(plist["RunAtLoad"])
            self.assertNotIn(b"K" * 32, body)
            self.assertNotIn(b"S" * 32, body)
            self.assertNotIn("launchctl", " ".join(
                plist["ProgramArguments"]
            ))
            self.assertFalse(
                contract["security_boundary"]["shell_invoked"]
            )

    def test_publish_is_mode_600_and_does_not_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = scheduler_inputs(root)
            result = publish_local_scheduler_contract(
                output_root=root / "output",
                **{name: value for name, value in inputs.items()
                   if name != "created_at"},
                clock=lambda: inputs["created_at"],
            )
            self.assertEqual(
                result["outcome"], "GENERATED_NOT_INSTALLED"
            )
            self.assertFalse(result["launchctl_invoked"])
            self.assertEqual(
                stat.S_IMODE(inputs["runtime_root"].stat().st_mode),
                0o700,
            )
            for name in ("plist_path", "contract_path"):
                mode = stat.S_IMODE(Path(result[name]).stat().st_mode)
                self.assertEqual(mode, 0o600)
            for directory_name in ("state", "log", "artifacts"):
                mode = stat.S_IMODE(
                    (inputs["runtime_root"] / directory_name).stat().st_mode
                )
                self.assertEqual(mode, 0o700)

    def test_bad_credential_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = scheduler_inputs(root)
            inputs["api_key_file"].chmod(0o644)
            with self.assertRaises(LocalSchedulerError):
                build_local_scheduler_contract(**inputs)
            inputs["api_key_file"].chmod(0o600)
            alias = root / "alias"
            alias.symlink_to(inputs["api_key_file"])
            inputs["api_key_file"] = alias
            with self.assertRaises(LocalSchedulerError):
                build_local_scheduler_contract(**inputs)

    def test_mutation_fails_even_after_contract_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, body = build_local_scheduler_contract(
                **scheduler_inputs(root)
            )
            changed = deepcopy(contract)
            changed["program_arguments"][-1] = "attacker"
            changed["contract_hash"] = artifact_self_hash(
                changed, "contract_hash"
            )
            trust = local_scheduler_contract_trust_hash(changed)
            self.assertTrue(
                local_scheduler_contract_reasons(
                    changed, body, trust
                )
            )

    def test_schema_is_packaged_and_valid(self):
        governance = (
            ROOT / "config" / "local-scheduler-contract-v1.schema.json"
        )
        packaged = resources.files("crypto_quant").joinpath(
            "schemas", "local-scheduler-contract-v1.schema.json"
        )
        self.assertEqual(governance.read_bytes(), packaged.read_bytes())
        Draft202012Validator.check_schema(
            json.loads(governance.read_text())
        )

    def test_cli_generates_and_exposes_no_install_or_secret_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = scheduler_inputs(root)
            argv = [
                "--repository-root",
                str(inputs["repository_root"]),
                "--runtime-root",
                str(inputs["runtime_root"]),
                "--python-executable",
                str(inputs["python_executable"]),
                "--api-key-file",
                str(inputs["api_key_file"]),
                "--api-secret-file",
                str(inputs["api_secret_file"]),
                "--worker-id",
                inputs["worker_id"],
                "--output-root",
                str(root / "output"),
            ]
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(argv, clock=lambda: inputs["created_at"]), 0
                )
            self.assertEqual(
                json.loads(stdout.getvalue())["outcome"],
                "GENERATED_NOT_INSTALLED",
            )
            for argument in (
                "--install",
                "--launchctl",
                "--api-key-value",
                "--api-secret-value",
                "--url",
                "--order",
            ):
                with self.subTest(argument=argument), redirect_stderr(
                    io.StringIO()
                ):
                    self.assertEqual(main([argument, "x"]), 2)


if __name__ == "__main__":
    unittest.main()
