import argparse
import contextlib
import copy
import hashlib
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crypto_quant.canonical import canonical_json
from crypto_quant.nautilus_v065_contract import (
    _self_hash,
    build_nautilus_v065_current_reference,
    build_nautilus_v065_request,
)
from crypto_quant.nautilus_v065_plan import build_nautilus_v065_plan
from crypto_quant.nautilus_v065_supply_chain import (
    NautilusV065SupplyChainError,
    build_nautilus_v065_dependency_lock,
    load_nautilus_v065_supply_chain_receipt,
)
from crypto_quant.nautilus_v065_ceremony_cli import (
    _acquire_and_run,
    _capture_fixed_command,
    _invoke_fixed_runner,
    _publish_fixed_artifact,
    _verified_acquisition_workspace,
    acquire_nautilus_v065_supply_chain,
    build_parser,
    main,
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
        self.assertEqual(_subcommands(parser), {"publish-plan", "acquire-and-run"})
        args = parser.parse_args(["publish-plan"])
        self.assertEqual(vars(args), {"command": "publish-plan"})
        self.assertEqual(vars(parser.parse_args(["acquire-and-run"])), {"command": "acquire-and-run"})
        with self.assertRaises(SystemExit):
            parser.parse_args(["publish-plan", "--url", "https://example.invalid"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["acquire-and-run", "--result", "chosen.json"])

    def test_acquire_and_run_requires_clean_head_before_loading_formal_plan(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as raw, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._clean_head",
            return_value="1" * 40,
        ) as clean, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._ARTIFACT_ROOT",
            Path(raw),
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._FORMAL_ROOT",
            Path(raw) / "v0.65.0",
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli.load_nautilus_v065_plan",
            return_value=plan,
        ) as load, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._acquire_and_run",
            return_value={"conclusion": "INCONCLUSIVE_KEEP_CURRENT_CORE"},
        ):
            self.assertEqual(main(["acquire-and-run"]), 0)
        clean.assert_called_once_with()
        load.assert_called_once()

    def test_success_ceremony_runs_twice_inside_verified_session_and_publishes_fixed_set(self):
        plan = self.plan()
        receipt = __import__("test_nautilus_v065_supply_chain").NautilusV065SupplyChainTests().receipt()
        receipt["plan_id"], receipt["plan_hash"] = plan["plan_id"], plan["plan_hash"]
        from crypto_quant.nautilus_v065_supply_chain import supply_chain_receipt_hash
        receipt["receipt_id"] = "nautilus_v065_supply_chain_" + "0" * 64
        receipt["receipt_hash"] = "0" * 64
        digest = supply_chain_receipt_hash(receipt)
        receipt["receipt_id"], receipt["receipt_hash"] = "nautilus_v065_supply_chain_" + digest, digest
        request = build_nautilus_v065_request(
            plan_id=plan["plan_id"], plan_hash=plan["plan_hash"],
            supply_chain_receipt_id=receipt["receipt_id"], supply_chain_receipt_hash=receipt["receipt_hash"],
        )
        candidate = build_nautilus_v065_current_reference(request=request)
        candidate["engine"] = "NAUTILUS_TRADER_1.230.0"
        candidate["result_id"] = "nautilus_v065_result_" + "0" * 64
        candidate["result_hash"] = "0" * 64
        candidate_digest = _self_hash(candidate, "result_id", "result_hash")
        candidate["result_id"] = "nautilus_v065_result_" + candidate_digest
        candidate["result_hash"] = candidate_digest
        comparison = {"conclusion": "ADOPT_FOR_PREREGISTERED_SHADOW"}
        session_root = Path("/private/tmp/fixed-nautilus-v065-session")

        @contextlib.contextmanager
        def session(_plan):
            yield {
                "status": "SUPPLY_CHAIN_VERIFIED_SANDBOX_READY",
                "receipt": receipt,
                "python": session_root / "venv/bin/python",
                "workspace": session_root,
            }

        with tempfile.TemporaryDirectory() as raw, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._verified_acquisition_workspace",
            side_effect=session,
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._invoke_fixed_runner",
            side_effect=[candidate, copy.deepcopy(candidate)],
        ) as invoke, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli.compare_nautilus_v065",
            return_value=comparison,
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._publish_fixed_artifact",
            return_value={"status": "COMMITTED"},
        ) as publish:
            root = Path(raw)
            root.chmod(0o700)
            summary = _acquire_and_run(plan=plan, artifact_root=root)
        self.assertEqual(invoke.call_count, 2)
        self.assertTrue(all(call.kwargs["python"] == session_root / "venv/bin/python" for call in invoke.call_args_list))
        self.assertEqual(
            [call.kwargs["final_name"] for call in publish.call_args_list],
            [
                "nautilus-supply-chain-receipt-v0.65.0.json",
                "nautilus-sandbox-request-v0.65.0.json",
                "nautilus-sandbox-result-first-v0.65.0.json",
                "nautilus-sandbox-result-replay-v0.65.0.json",
                "nautilus-sandbox-comparison-v0.65.0.json",
            ],
        )
        self.assertEqual(summary["conclusion"], "ADOPT_FOR_PREREGISTERED_SHADOW")

    def test_runner_revalidates_verified_python_identity_before_and_after(self):
        plan = self.plan()
        receipt = __import__("test_nautilus_v065_supply_chain").NautilusV065SupplyChainTests().receipt()
        request = build_nautilus_v065_request(
            plan_id=receipt["plan_id"], plan_hash=receipt["plan_hash"],
            supply_chain_receipt_id=receipt["receipt_id"], supply_chain_receipt_hash=receipt["receipt_hash"],
        )
        transcript = next(item for item in receipt["transcripts"] if item["name"] == "offline_import")
        python = Path(transcript["executable_path"])
        expected = {
            field: transcript[f"executable_{field}_before"]
            for field in ("device", "inode", "mode", "size", "sha256")
        }
        with tempfile.TemporaryDirectory() as raw, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._venv_python_identity",
            side_effect=[expected, expected],
        ) as identity, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli.subprocess.run",
            return_value=mock.Mock(returncode=0, stdout=b"", stderr=b""),
        ) as run, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli.load_nautilus_v065_result",
            return_value={"verified": True},
        ):
            workspace = Path(raw)
            workspace.chmod(0o700)
            self.assertEqual(
                _invoke_fixed_runner(
                    python=python, workspace=workspace, request=request,
                    receipt=receipt, invocation="first",
                ),
                {"verified": True},
            )
        self.assertEqual(identity.call_count, 2)
        self.assertEqual(run.call_args.args[0][0:4], [str(python), "-P", "-m", "crypto_quant_nautilus_v065.runner"])
        self.assertEqual(set(run.call_args.kwargs["env"]), {"HOME", "PATH", "PYTHONPATH", "LANG", "LC_ALL"})

        changed = dict(expected, inode=expected["inode"] + 1)
        with tempfile.TemporaryDirectory() as raw, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._venv_python_identity",
            return_value=changed,
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli.subprocess.run"
        ) as run:
            workspace = Path(raw)
            workspace.chmod(0o700)
            with self.assertRaisesRegex(NautilusV065SupplyChainError, "NAUTILUS_V065_RUNNER_PYTHON_IDENTITY_INVALID"):
                _invoke_fixed_runner(
                    python=python, workspace=workspace, request=request,
                    receipt=receipt, invocation="first",
                )
        run.assert_not_called()

    def test_failed_acquisition_publishes_failure_receipt_and_inconclusive_with_zero_runner(self):
        plan = self.plan()
        failure_receipt = {
            "receipt_id": "nautilus_v065_supply_chain_failure_" + "1" * 64,
            "receipt_hash": "2" * 64,
            "status": "SUPPLY_CHAIN_ACQUISITION_FAILED",
        }
        comparison = {"conclusion": "INCONCLUSIVE_KEEP_CURRENT_CORE"}

        @contextlib.contextmanager
        def session(_plan):
            yield {
                "status": "SUPPLY_CHAIN_ACQUISITION_FAILED",
                "receipt": failure_receipt,
                "reason_code": "NAUTILUS_V065_SLSA_VERIFICATION_FAILED",
                "python": None,
                "workspace": None,
            }

        with tempfile.TemporaryDirectory() as raw, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._verified_acquisition_workspace",
            side_effect=session,
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._invoke_fixed_runner"
        ) as invoke, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli.build_nautilus_v065_supply_failure_comparison",
            return_value=comparison,
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._publish_fixed_artifact",
            return_value={"status": "COMMITTED"},
        ) as publish:
            root = Path(raw)
            root.chmod(0o700)
            summary = _acquire_and_run(plan=plan, artifact_root=root)
        invoke.assert_not_called()
        self.assertEqual(
            [call.kwargs["final_name"] for call in publish.call_args_list],
            [
                "nautilus-supply-chain-receipt-v0.65.0.json",
                "nautilus-sandbox-comparison-v0.65.0.json",
            ],
        )
        self.assertEqual(summary["conclusion"], "INCONCLUSIVE_KEEP_CURRENT_CORE")

    def test_runner_failure_freezes_inconclusive_without_retry_selection(self):
        plan = self.plan()
        receipt = __import__("test_nautilus_v065_supply_chain").NautilusV065SupplyChainTests().receipt()
        receipt["plan_id"], receipt["plan_hash"] = plan["plan_id"], plan["plan_hash"]
        from crypto_quant.nautilus_v065_supply_chain import supply_chain_receipt_hash
        receipt["receipt_id"] = "nautilus_v065_supply_chain_" + "0" * 64
        receipt["receipt_hash"] = "0" * 64
        digest = supply_chain_receipt_hash(receipt)
        receipt["receipt_id"], receipt["receipt_hash"] = "nautilus_v065_supply_chain_" + digest, digest

        @contextlib.contextmanager
        def session(_plan):
            yield {
                "status": "SUPPLY_CHAIN_VERIFIED_SANDBOX_READY", "receipt": receipt,
                "python": Path("/private/tmp/verified/python"),
                "workspace": Path("/private/tmp/verified"),
            }

        comparison = {
            "conclusion": "INCONCLUSIVE_KEEP_CURRENT_CORE",
            "difference_classes": ["INVALID_OR_INCOMPLETE_EVIDENCE"],
        }
        with tempfile.TemporaryDirectory() as raw, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._verified_acquisition_workspace",
            side_effect=session,
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._invoke_fixed_runner",
            side_effect=NautilusV065SupplyChainError("NAUTILUS_V065_RUNNER_FAILED"),
        ) as invoke, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli.build_nautilus_v065_execution_failure_comparison",
            return_value=comparison,
        ) as build_failure, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._publish_fixed_artifact",
            return_value={"status": "COMMITTED"},
        ) as publish:
            root = Path(raw)
            root.chmod(0o700)
            summary = _acquire_and_run(plan=plan, artifact_root=root)
        self.assertEqual(invoke.call_count, 1)
        build_failure.assert_called_once()
        self.assertEqual(build_failure.call_args.kwargs["runner_invocation_count"], 1)
        self.assertEqual(
            [call.kwargs["final_name"] for call in publish.call_args_list],
            [
                "nautilus-supply-chain-receipt-v0.65.0.json",
                "nautilus-sandbox-request-v0.65.0.json",
                "nautilus-sandbox-comparison-v0.65.0.json",
            ],
        )
        self.assertEqual(summary, {
            "conclusion": "INCONCLUSIVE_KEEP_CURRENT_CORE",
            "runner_invocation_count": 1,
        })

    def test_real_acquisition_error_becomes_replayable_failure_receipt_without_runner(self):
        plan = self.plan()
        published = []

        def publish(**kwargs):
            published.append((kwargs["final_name"], kwargs["data"]))
            return {"status": "COMMITTED"}

        with tempfile.TemporaryDirectory() as raw, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._platform_identity",
            return_value={
                "operating_system": "macOS", "operating_system_major": 15,
                "machine": "arm64", "python_implementation": "CPython",
                "python_version": "3.12.13",
            },
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._capture_fixed_command",
            side_effect=NautilusV065SupplyChainError("NAUTILUS_V065_TAG_FETCH_FAILED"),
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._invoke_fixed_runner"
        ) as invoke, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._publish_fixed_artifact",
            side_effect=publish,
        ):
            root = Path(raw)
            root.chmod(0o700)
            summary = _acquire_and_run(plan=plan, artifact_root=root)
        invoke.assert_not_called()
        self.assertEqual(summary, {
            "conclusion": "INCONCLUSIVE_KEEP_CURRENT_CORE",
            "runner_invocation_count": 0,
        })
        self.assertEqual(
            [name for name, _data in published],
            [
                "nautilus-supply-chain-receipt-v0.65.0.json",
                "nautilus-sandbox-comparison-v0.65.0.json",
            ],
        )
        receipt = json.loads(published[0][1])
        self.assertEqual(receipt["status"], "SUPPLY_CHAIN_ACQUISITION_FAILED")
        self.assertEqual(receipt["failure"]["reason_code"], "NAUTILUS_V065_TAG_FETCH_FAILED")
        with tempfile.TemporaryDirectory() as receipt_raw:
            path = Path(receipt_raw) / "receipt.json"
            path.write_bytes(published[0][1])
            path.chmod(0o600)
            self.assertEqual(load_nautilus_v065_supply_chain_receipt(path.resolve()), receipt)

    def test_failure_receipt_retains_completed_and_failed_command_evidence(self):
        plan = self.plan()

        def transcript(name):
            raw = (name + "\n").encode()
            return {
                "name": name, "argv": [name], "exit_code": 0,
                "executable_path": "/usr/bin/true",
                "executable_device_before": 1, "executable_inode_before": 1,
                "executable_mode_before": 0o755, "executable_size_before": 1,
                "executable_sha256_before": "3" * 64,
                "executable_device_after": 1, "executable_inode_after": 1,
                "executable_mode_after": 0o755, "executable_size_after": 1,
                "executable_sha256_after": "3" * 64,
                "stdout_encoding": "utf-8", "stdout_bytes": raw.decode(),
                "stdout_size": len(raw), "stdout_sha256": hashlib.sha256(raw).hexdigest(),
                "stderr_encoding": "utf-8", "stderr_bytes": "", "stderr_size": 0,
                "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            }

        failed = transcript("git_version")
        failed["exit_code"] = 17
        error = NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_NONZERO")
        error.evidence = failed
        calls = [transcript("uv_version"), transcript("python_version"), error]
        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._platform_identity",
            return_value={
                "operating_system": "macOS", "operating_system_major": 15,
                "machine": "arm64", "python_implementation": "CPython",
                "python_version": "3.12.13",
            },
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._capture_fixed_command",
            side_effect=calls,
        ):
            with _verified_acquisition_workspace(plan) as session:
                receipt = session["receipt"]
        self.assertEqual(receipt["failure"]["completed_transcript_count"], 2)
        self.assertEqual([item["name"] for item in receipt["transcripts"]], ["uv_version", "python_version"])
        self.assertEqual(receipt["failure"]["failed_command"]["name"], "git_version")
        self.assertEqual(receipt["failure"]["failed_command"]["exit_code"], 17)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "receipt.json"
            path.write_bytes(canonical_json(receipt).encode() + b"\n")
            path.chmod(0o600)
            self.assertEqual(load_nautilus_v065_supply_chain_receipt(path.resolve()), receipt)
            changed = copy.deepcopy(receipt)
            changed["transcripts"].reverse()
            changed["receipt_id"] = "nautilus_v065_supply_chain_failure_" + "0" * 64
            changed["receipt_hash"] = "0" * 64
            from crypto_quant.nautilus_v065_supply_chain import supply_chain_receipt_hash
            digest = supply_chain_receipt_hash(changed)
            changed["receipt_id"] = "nautilus_v065_supply_chain_failure_" + digest
            changed["receipt_hash"] = digest
            path.write_bytes(canonical_json(changed).encode() + b"\n")
            with self.assertRaisesRegex(NautilusV065SupplyChainError, "NAUTILUS_V065_FAILURE_RECEIPT_INVALID"):
                load_nautilus_v065_supply_chain_receipt(path.resolve())

    def test_download_failure_receipt_keeps_all_completed_command_transcripts(self):
        plan = self.plan()
        calls = []

        def command(name, **_kwargs):
            calls.append(name)
            raw = (name + "\n").encode()
            if name == "official_tag":
                raw = b"112d335088ec11cdd1d60038b16c8fe56406aead refs/tags/v1.230.0\n8160730c7c550480b0a439fb11086a4c4de15f0b refs/tags/v1.230.0^{}\n"
            return {
                "name": name, "argv": [name], "exit_code": 0,
                "executable_path": "/usr/bin/true",
                "executable_device_before": 1, "executable_inode_before": 1,
                "executable_mode_before": 0o755, "executable_size_before": 1,
                "executable_sha256_before": "3" * 64,
                "executable_device_after": 1, "executable_inode_after": 1,
                "executable_mode_after": 0o755, "executable_size_after": 1,
                "executable_sha256_after": "3" * 64,
                "stdout_encoding": "utf-8", "stdout_bytes": raw.decode(),
                "stdout_size": len(raw), "stdout_sha256": hashlib.sha256(raw).hexdigest(),
                "stderr_encoding": "utf-8", "stderr_bytes": "", "stderr_size": 0,
                "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            }

        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._platform_identity",
            return_value={
                "operating_system": "macOS", "operating_system_major": 15,
                "machine": "arm64", "python_implementation": "CPython",
                "python_version": "3.12.13",
            },
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._capture_fixed_command",
            side_effect=command,
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._verify_license_transcript"
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._download_fixed_artifact",
            side_effect=NautilusV065SupplyChainError("NAUTILUS_V065_DOWNLOAD_FAILED"),
        ):
            with _verified_acquisition_workspace(plan) as session:
                receipt = session["receipt"]
        self.assertEqual(receipt["failure"]["completed_transcript_count"], 6)
        self.assertEqual([item["name"] for item in receipt["transcripts"]], calls)
        self.assertIsNone(receipt["failure"]["failed_command"])

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

    def test_nonzero_command_error_retains_exact_failure_record(self):
        def nonzero(*_args, **kwargs):
            kwargs["stdout"].write(b"failure-stdout\n")
            kwargs["stderr"].write(b"failure-stderr\n")
            return mock.Mock(returncode=17)

        with mock.patch("subprocess.run", side_effect=nonzero):
            with self.assertRaises(NautilusV065SupplyChainError) as raised:
                _capture_fixed_command("git_version")
        evidence = raised.exception.evidence
        self.assertEqual(evidence["name"], "git_version")
        self.assertEqual(evidence["exit_code"], 17)
        self.assertEqual(evidence["stdout_bytes"], "failure-stdout\n")
        self.assertEqual(evidence["stderr_bytes"], "failure-stderr\n")
        self.assertEqual(evidence["stdout_sha256"], hashlib.sha256(b"failure-stdout\n").hexdigest())

    def test_fixed_venv_python_symlink_binds_nofollow_target_identity(self):
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw)
            (workspace / "home").mkdir()
            (workspace / "venv/bin").mkdir(parents=True)
            python_link = workspace / "venv/bin/python"
            python_link.symlink_to(Path("/usr/bin/true"))

            def execute(*_args, **_kwargs):
                return mock.Mock(returncode=0)

            with mock.patch("subprocess.run", side_effect=execute):
                record = _capture_fixed_command("offline_import", workspace=workspace)
        self.assertEqual(record["executable_path"], str(python_link))
        self.assertEqual(
            record["executable_sha256_before"],
            hashlib.sha256(Path("/usr/bin/true").read_bytes()).hexdigest(),
        )
        self.assertEqual(record["executable_sha256_before"], record["executable_sha256_after"])

    def test_timeout_command_error_retains_partial_output_record(self):
        def timeout(*_args, **kwargs):
            kwargs["stdout"].write(b"partial-out")
            kwargs["stderr"].write(b"partial-err")
            raise __import__("subprocess").TimeoutExpired("git", 120)

        with mock.patch("subprocess.run", side_effect=timeout):
            with self.assertRaisesRegex(NautilusV065SupplyChainError, "NAUTILUS_V065_COMMAND_TIMEOUT") as raised:
                _capture_fixed_command("git_version")
        evidence = raised.exception.evidence
        self.assertEqual(evidence["exit_code"], -1)
        self.assertEqual(evidence["stdout_bytes"], "partial-out")
        self.assertEqual(evidence["stderr_bytes"], "partial-err")

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
            with _verified_acquisition_workspace(plan) as session:
                receipt = session["receipt"]
                retained_workspace = session["workspace"]
                self.assertTrue(retained_workspace.is_dir())
                self.assertEqual(session["python"], retained_workspace / "venv/bin/python")
            self.assertFalse(retained_workspace.exists())
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

    def test_safe_publisher_accepts_public_readonly_parent_and_rejects_writable_parent(self):
        data = b'{"fixed":true}\n'
        name = "nautilus-supply-chain-receipt-v0.65.0.json"
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            public_root = parent / "public"
            public_root.mkdir(mode=0o755)
            result = _publish_fixed_artifact(root=public_root, final_name=name, data=data)
            self.assertEqual(result["status"], "COMMITTED")
            self.assertEqual((public_root / name).read_bytes(), data)

            for mode in (0o775, 0o777):
                writable_root = parent / f"writable-{mode:o}"
                writable_root.mkdir(mode=mode)
                writable_root.chmod(mode)
                sentinel = writable_root / "sentinel"
                sentinel.write_bytes(b"unchanged")
                sentinel.chmod(0o600)
                before = sentinel.stat()
                with self.subTest(mode=oct(mode)):
                    with self.assertRaisesRegex(
                        NautilusV065SupplyChainError,
                        "NAUTILUS_V065_ARTIFACT_ROOT_INVALID",
                    ):
                        _publish_fixed_artifact(root=writable_root, final_name=name, data=data)
                after = sentinel.stat()
                self.assertFalse((writable_root / name).exists())
                self.assertEqual(sentinel.read_bytes(), b"unchanged")
                self.assertEqual(
                    (before.st_ino, before.st_mode, before.st_size, before.st_nlink),
                    (after.st_ino, after.st_mode, after.st_size, after.st_nlink),
                )

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
