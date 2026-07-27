import copy
import io
import json
import os
import plistlib
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from crypto_quant.challenger_launchd import (
    ChallengerLaunchdError,
    build_challenger_launchd_contract,
    challenger_launchd_contract_reasons,
    challenger_launchd_contract_trust_hash,
    load_challenger_launchd_contract,
    publish_challenger_launchd_contract,
)
from crypto_quant.challenger_launchd_cli import main as launchd_main
from crypto_quant.evidence import artifact_self_hash


ROOT = Path(__file__).resolve().parents[1]
CREATED = datetime(2026, 7, 28, 6, tzinfo=timezone.utc)


def inputs(root):
    return {
        "repository_root": ROOT,
        "runtime_root": root / "runtime",
        "python_executable": Path(sys.executable),
        "created_at": CREATED,
    }


class ChallengerLaunchdTests(unittest.TestCase):
    def test_contract_replays_fixed_uncredentialed_launchagent(self):
        with tempfile.TemporaryDirectory() as directory:
            contract, body = build_challenger_launchd_contract(
                **inputs(Path(directory))
            )
            trust = challenger_launchd_contract_trust_hash(contract)
            self.assertEqual(
                challenger_launchd_contract_reasons(
                    contract, body, trust
                ),
                (),
            )
            plist = plistlib.loads(body)
            self.assertEqual(
                plist["Label"],
                "local.crypto-quant.challenger-forward",
            )
            self.assertEqual(
                plist["StartCalendarInterval"],
                [
                    {"Hour": hour, "Minute": 2}
                    for hour in (0, 4, 8, 12, 16, 20)
                ],
            )
            self.assertEqual(
                plist["ProgramArguments"][1:],
                [
                    "-m",
                    "crypto_quant.challenger_forward_runner_cli",
                    "--state-path",
                    str(
                        (
                            Path(directory)
                            / "runtime"
                            / "state"
                            / "challenger-forward.sqlite"
                        ).resolve()
                    ),
                    "--output-root",
                    str(
                        (Path(directory) / "runtime" / "artifacts").resolve()
                    ),
                ],
            )
            self.assertEqual(
                plist["EnvironmentVariables"],
                {"PYTHONPATH": str(ROOT / "src")},
            )
            self.assertEqual(plist["Umask"], 0o077)
            self.assertTrue(plist["RunAtLoad"])
            self.assertFalse(
                contract["security_boundary"][
                    "credential_paths_present"
                ]
            )
            self.assertFalse(
                contract["security_boundary"]["broker_access"]
            )

    def test_publish_load_permissions_idempotency_and_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arguments = {
                name: value
                for name, value in inputs(root).items()
                if name != "created_at"
            }
            result = publish_challenger_launchd_contract(
                output_root=root / "output",
                **arguments,
                clock=lambda: CREATED,
            )
            retry = publish_challenger_launchd_contract(
                output_root=root / "output",
                **arguments,
                clock=lambda: CREATED,
            )
            self.assertEqual(result, retry)
            for name in ("contract_path", "plist_path"):
                self.assertEqual(
                    stat.S_IMODE(Path(result[name]).stat().st_mode),
                    0o600,
                )
            for name in ("runtime", "state", "log", "artifacts"):
                path = (
                    root / "runtime"
                    if name == "runtime"
                    else root / "runtime" / name
                )
                self.assertEqual(
                    stat.S_IMODE(path.stat().st_mode), 0o700
                )
            contract = load_challenger_launchd_contract(
                contract_path=Path(result["contract_path"]),
                plist_path=Path(result["plist_path"]),
            )
            self.assertEqual(contract["contract_id"], result["contract_id"])
            with self.assertRaisesRegex(
                ChallengerLaunchdError,
                "CHALLENGER_LAUNCHD_PUBLISH_CONFLICT",
            ):
                publish_challenger_launchd_contract(
                    output_root=root / "output",
                    **arguments,
                    clock=lambda: CREATED.replace(hour=7),
                )

    def test_timezone_name_offset_and_dst_fail_closed(self):
        bad_values = (
            (
                "/var/db/timezone/zoneinfo/UTC",
                SimpleNamespace(tm_gmtoff=0, tm_isdst=0),
            ),
            (
                "/var/db/timezone/zoneinfo/Asia/Shanghai",
                SimpleNamespace(tm_gmtoff=28800, tm_isdst=1),
            ),
        )
        for target, local in bad_values:
            with self.subTest(target=target):
                with tempfile.TemporaryDirectory() as directory, patch(
                    "crypto_quant.challenger_launchd._timezone_link_target",
                    return_value=target,
                ), patch(
                    "crypto_quant.challenger_launchd.time.localtime",
                    return_value=local,
                ):
                    with self.assertRaisesRegex(
                        ChallengerLaunchdError,
                        "CHALLENGER_LAUNCHD_TIMEZONE_INVALID",
                    ):
                        build_challenger_launchd_contract(
                            **inputs(Path(directory))
                        )

    def test_repository_runtime_and_python_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = inputs(root)
            values["repository_root"] = root / "missing"
            with self.assertRaises(ChallengerLaunchdError):
                build_challenger_launchd_contract(**values)
            values = inputs(root)
            target = root / "runtime-target"
            target.mkdir()
            alias = root / "runtime"
            alias.symlink_to(target, target_is_directory=True)
            values["runtime_root"] = alias
            with self.assertRaises(ChallengerLaunchdError):
                build_challenger_launchd_contract(**values)
            values = inputs(root)
            fake_python = root / "python"
            fake_python.write_text("not executable", encoding="utf-8")
            values["python_executable"] = fake_python
            with self.assertRaises(ChallengerLaunchdError):
                build_challenger_launchd_contract(**values)

    def test_semantic_mutation_fails_after_contract_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            contract, body = build_challenger_launchd_contract(
                **inputs(Path(directory))
            )
            changed = copy.deepcopy(contract)
            changed["program_arguments"][-1] = "/tmp/attacker"
            changed["contract_hash"] = artifact_self_hash(
                changed, "contract_hash"
            )
            trust = challenger_launchd_contract_trust_hash(changed)
            reasons = challenger_launchd_contract_reasons(
                changed, body, trust
            )
            self.assertIn(
                "CHALLENGER_LAUNCHD_ARGUMENTS_MISMATCH",
                reasons,
            )

    def test_schema_mirror_is_exact(self):
        self.assertEqual(
            (
                ROOT
                / "config"
                / "challenger-launchd-contract-v1.schema.json"
            ).read_bytes(),
            (
                ROOT
                / "src"
                / "crypto_quant"
                / "schemas"
                / "challenger-launchd-contract-v1.schema.json"
            ).read_bytes(),
        )

    def test_cli_only_renders_and_exposes_no_install_or_secret_options(self):
        source = (
            ROOT / "src" / "crypto_quant" / "challenger_launchd_cli.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "--install",
            "--load",
            "--launchctl",
            "--credential",
            "--api-key",
            "--url",
            "--symbol",
            "--order",
        ):
            self.assertNotIn(forbidden, source)
            with self.subTest(forbidden=forbidden), redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(launchd_main([forbidden, "x"]), 2)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = launchd_main(
                    [
                        "--repository-root",
                        str(ROOT),
                        "--runtime-root",
                        str(root / "runtime"),
                        "--python-executable",
                        sys.executable,
                        "--output-root",
                        str(root / "output"),
                    ],
                    clock=lambda: CREATED,
                )
            self.assertEqual(status, 0)
            output = json.loads(stdout.getvalue())
            self.assertEqual(
                output["outcome"], "GENERATED_NOT_INSTALLED"
            )
            self.assertFalse(output["launchctl_invoked"])

    def test_contract_is_deterministic_one_hundred_times(self):
        with tempfile.TemporaryDirectory() as directory:
            values = inputs(Path(directory))
            expected = build_challenger_launchd_contract(**values)
            for _ in range(100):
                self.assertEqual(
                    build_challenger_launchd_contract(**values),
                    expected,
                )

    def test_default_wall_clock_is_normalized_to_milliseconds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = {
                name: value
                for name, value in inputs(root).items()
                if name != "created_at"
            }
            result = publish_challenger_launchd_contract(
                output_root=root / "output",
                **values,
            )
            contract = load_challenger_launchd_contract(
                contract_path=Path(result["contract_path"]),
                plist_path=Path(result["plist_path"]),
            )
            self.assertRegex(
                contract["created_at"],
                r"\.[0-9]{3}Z$",
            )


if __name__ == "__main__":
    unittest.main()
