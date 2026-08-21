import argparse
import contextlib
import copy
import hashlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
import time
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
    _command,
    _acquire_and_run,
    _capture_fixed_command,
    _commit_formal_ceremony,
    _invoke_fixed_runner,
    _load_frozen_current_reference,
    _publish_fixed_artifact,
    _publish_formal_completion_marker,
    _run_bounded_command,
    _verify_staged_artifact_set,
    _verify_formal_candidate,
    _verified_acquisition_workspace,
    acquire_nautilus_v065_supply_chain,
    build_parser,
    main,
)


ROOT = Path(__file__).resolve().parents[1]


def _transcript_provenance():
    return {
        "environment": {
            "HOME": "/private/tmp/nautilus-v065-test/home",
            "LANG": "C", "LC_ALL": "C",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
        },
        "started_at": "2026-08-22T00:00:00.000000Z",
        "completed_at": "2026-08-22T00:00:01.000000Z",
    }


def _supply_transcripts_by_name():
    receipt = __import__(
        "test_nautilus_v065_supply_chain"
    ).NautilusV065SupplyChainTests().receipt()
    return {item["name"]: copy.deepcopy(item) for item in receipt["transcripts"]}


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
        with self.assertRaises(SystemExit):
            parser.parse_args(["acquire-and-run", "--output", "chosen.json"])

    def test_acquire_and_run_requires_clean_head_before_loading_formal_plan(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as raw, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._clean_head",
            return_value="1" * 40,
        ) as clean, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._ARTIFACT_ROOT",
            Path(raw),
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli.load_nautilus_v065_plan",
            return_value=plan,
        ) as load, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._verify_formal_candidate",
        ) as verify, mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._commit_formal_ceremony",
            return_value={"conclusion": "INCONCLUSIVE_KEEP_CURRENT_CORE"},
        ) as commit:
            self.assertEqual(main(["acquire-and-run"]), 0)
        clean.assert_called_once_with()
        load.assert_called_once()
        verify.assert_called_once_with(plan, "1" * 40)
        commit.assert_called_once_with(plan)

    def test_formal_ceremony_uses_comparison_marker_and_never_reruns_partial(self):
        plan = self.plan()
        from crypto_quant import nautilus_v065_ceremony_cli as module

        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            parent.chmod(0o755)
            formal = parent / "v0.65.0"
            with mock.patch.object(module, "_ARTIFACT_ROOT", parent), mock.patch.object(
                module, "_FORMAL_ROOT", formal
            ), mock.patch.object(
                module,
                "_acquire_and_run",
                return_value={"conclusion": "REJECT_KEEP_CURRENT_CORE"},
            ) as acquire, mock.patch.object(
                module,
                "_verify_staged_artifact_set",
            ) as verify_set, mock.patch.object(
                module, "_publish_formal_completion_marker"
            ) as marker:
                result = _commit_formal_ceremony(plan)
            self.assertEqual(result["conclusion"], "REJECT_KEEP_CURRENT_CORE")
            self.assertTrue(formal.is_dir())
            self.assertFalse((parent / ".v0.65.0.in-progress").exists())
            acquire.assert_called_once_with(plan=plan, artifact_root=formal)
            verify_set.assert_called_once()
            marker.assert_called_once()

        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            parent.chmod(0o755)
            formal = parent / "v0.65.0"
            with mock.patch.object(module, "_ARTIFACT_ROOT", parent), mock.patch.object(
                module, "_FORMAL_ROOT", formal
            ), mock.patch.object(
                module,
                "_acquire_and_run",
                side_effect=RuntimeError("TEST_ONLY_CRASH_AFTER_OBSERVATION"),
            ):
                with self.assertRaisesRegex(RuntimeError, "TEST_ONLY_CRASH_AFTER_OBSERVATION"):
                    _commit_formal_ceremony(plan)
            self.assertTrue(formal.is_dir())
            self.assertFalse((parent / ".v0.65.0.in-progress").exists())

            with mock.patch.object(module, "_ARTIFACT_ROOT", parent), mock.patch.object(
                module, "_FORMAL_ROOT", formal
            ), mock.patch.object(module, "_acquire_and_run") as rerun:
                with self.assertRaisesRegex(
                    NautilusV065SupplyChainError,
                    "NAUTILUS_V065_FORMAL_STATE_CONFLICT",
                ):
                    _commit_formal_ceremony(plan)
            rerun.assert_not_called()

    def test_formal_ceremony_never_commits_an_empty_or_incomplete_artifact_set(self):
        plan = self.plan()
        from crypto_quant import nautilus_v065_ceremony_cli as module

        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            parent.chmod(0o755)
            with mock.patch.object(module, "_ARTIFACT_ROOT", parent), mock.patch.object(
                module, "_FORMAL_ROOT", parent / "v0.65.0"
            ), mock.patch.object(
                module,
                "_acquire_and_run",
                return_value={
                    "conclusion": "INCONCLUSIVE_KEEP_CURRENT_CORE",
                    "runner_invocation_count": 0,
                },
            ):
                with self.assertRaisesRegex(
                    NautilusV065SupplyChainError,
                    "NAUTILUS_V065_FORMAL_ARTIFACT_SET_INVALID",
                ):
                    _commit_formal_ceremony(plan)
            self.assertTrue((parent / "v0.65.0").is_dir())
            self.assertFalse(
                (parent / "v0.65.0" / "nautilus-sandbox-comparison-v0.65.0.json").exists()
            )
            self.assertFalse((parent / ".v0.65.0.in-progress").exists())

    def test_formal_ceremony_never_renames_a_verified_directory_by_name(self):
        plan = self.plan()
        from crypto_quant import nautilus_v065_ceremony_cli as module

        source_is_directory = []

        def inspect_source(parent_fd, source, _target):
            source_is_directory.append(
                __import__("stat").S_ISDIR(
                    os.stat(source, dir_fd=parent_fd, follow_symlinks=False).st_mode
                )
            )
            raise RuntimeError("TEST_ONLY_STOP_AT_ATOMIC_PUBLICATION")

        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            parent.chmod(0o755)
            with mock.patch.object(module, "_ARTIFACT_ROOT", parent), mock.patch.object(
                module, "_FORMAL_ROOT", parent / "v0.65.0"
            ), mock.patch.object(
                module,
                "_acquire_and_run",
                return_value={"conclusion": "REJECT_KEEP_CURRENT_CORE"},
            ), mock.patch.object(
                module, "_verify_staged_artifact_set"
            ), mock.patch.object(
                module, "_publish_formal_completion_marker"
            ), mock.patch.object(
                module, "_atomic_no_replace", side_effect=inspect_source
            ):
                _commit_formal_ceremony(plan)
        self.assertNotIn(True, source_is_directory)

    def test_formal_completion_marker_is_published_only_after_set_replay(self):
        plan = self.plan()
        from crypto_quant import nautilus_v065_ceremony_cli as module

        order = []
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            parent.chmod(0o755)
            with mock.patch.object(module, "_ARTIFACT_ROOT", parent), mock.patch.object(
                module, "_FORMAL_ROOT", parent / "v0.65.0"
            ), mock.patch.object(
                module,
                "_acquire_and_run",
                return_value={"conclusion": "REJECT_KEEP_CURRENT_CORE"},
            ), mock.patch.object(
                module,
                "_verify_staged_artifact_set",
                side_effect=lambda *_args, **_kwargs: order.append("replay"),
            ), mock.patch.object(
                module,
                "_publish_formal_completion_marker",
                create=True,
                side_effect=lambda *_args, **_kwargs: order.append("marker"),
            ):
                _commit_formal_ceremony(plan)
        self.assertEqual(order, ["replay", "marker"])

    def test_staged_set_verifier_rejects_individually_valid_unbound_documents(self):
        from crypto_quant.nautilus_v065_evidence import compare_nautilus_v065
        from crypto_quant.nautilus_v065_supply_chain import supply_chain_receipt_hash

        plan = self.plan()
        receipt = __import__(
            "test_nautilus_v065_supply_chain"
        ).NautilusV065SupplyChainTests().receipt()
        receipt["plan_id"], receipt["plan_hash"] = plan["plan_id"], plan["plan_hash"]
        receipt["receipt_id"] = "nautilus_v065_supply_chain_" + "0" * 64
        receipt["receipt_hash"] = "0" * 64
        digest = supply_chain_receipt_hash(receipt)
        receipt["receipt_id"] = "nautilus_v065_supply_chain_" + digest
        receipt["receipt_hash"] = digest
        request = build_nautilus_v065_request(
            plan_id=plan["plan_id"],
            plan_hash=plan["plan_hash"],
            supply_chain_receipt_id=receipt["receipt_id"],
            supply_chain_receipt_hash=receipt["receipt_hash"],
        )
        current = build_nautilus_v065_current_reference(request=request)
        candidate = copy.deepcopy(current)
        candidate["engine"] = "NAUTILUS_TRADER_1.230.0"
        candidate["result_id"] = "nautilus_v065_result_" + "0" * 64
        candidate["result_hash"] = "0" * 64
        result_digest = _self_hash(candidate, "result_id", "result_hash")
        candidate["result_id"] = "nautilus_v065_result_" + result_digest
        candidate["result_hash"] = result_digest
        comparison = compare_nautilus_v065(
            plan=plan,
            receipt=receipt,
            request=request,
            current_reference=current,
            first_result=candidate,
            replay_result=candidate,
        )
        unrelated = copy.deepcopy(receipt)
        unrelated["transcripts"][0]["started_at"] = (
            "2026-08-21T23:59:59.000000Z"
        )
        unrelated["receipt_id"] = "nautilus_v065_supply_chain_" + "0" * 64
        unrelated["receipt_hash"] = "0" * 64
        unrelated_digest = supply_chain_receipt_hash(unrelated)
        unrelated["receipt_id"] = "nautilus_v065_supply_chain_" + unrelated_digest
        unrelated["receipt_hash"] = unrelated_digest

        values = {
            "nautilus-supply-chain-receipt-v0.65.0.json": unrelated,
            "nautilus-sandbox-request-v0.65.0.json": request,
            "nautilus-sandbox-result-first-v0.65.0.json": candidate,
            "nautilus-sandbox-result-replay-v0.65.0.json": candidate,
            "nautilus-sandbox-comparison-v0.65.0.json": comparison,
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            for name, value in values.items():
                path = root / name
                path.write_text(canonical_json(value) + "\n", encoding="utf-8")
                path.chmod(0o600)
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaisesRegex(
                    NautilusV065SupplyChainError,
                    "NAUTILUS_V065_FORMAL_ARTIFACT_SET_INVALID",
                ):
                    _verify_staged_artifact_set(
                        root,
                        descriptor,
                        {
                            "conclusion": comparison["conclusion"],
                            "runner_invocation_count": 2,
                        },
                        expected_plan=plan,
                    )
                receipt_path = root / "nautilus-supply-chain-receipt-v0.65.0.json"
                receipt_path.write_text(
                    canonical_json(receipt) + "\n", encoding="utf-8"
                )
                wrong_plan = dict(
                    plan,
                    plan_id="nautilus_v065_plan_" + "a" * 64,
                    plan_hash="b" * 64,
                )
                with self.assertRaisesRegex(
                    NautilusV065SupplyChainError,
                    "NAUTILUS_V065_FORMAL_ARTIFACT_SET_INVALID",
                ):
                    _verify_staged_artifact_set(
                        root,
                        descriptor,
                        {
                            "conclusion": comparison["conclusion"],
                            "runner_invocation_count": 2,
                        },
                        expected_plan=wrong_plan,
                    )
                _verify_staged_artifact_set(
                    root,
                    descriptor,
                    {
                        "conclusion": comparison["conclusion"],
                        "runner_invocation_count": 2,
                    },
                    expected_plan=plan,
                )
                _publish_formal_completion_marker(
                    root,
                    descriptor,
                    {
                        "conclusion": comparison["conclusion"],
                        "runner_invocation_count": 2,
                    },
                    expected_plan=plan,
                )
                marker = json.loads(
                    (root / "nautilus-sandbox-complete-v0.65.0.json").read_text()
                )
                self.assertEqual(marker["plan_id"], plan["plan_id"])
                self.assertEqual(marker["comparison_hash"], comparison["comparison_hash"])
                self.assertEqual(len(marker["files"]), 5)
            finally:
                os.close(descriptor)

    def test_formal_candidate_allows_exactly_one_plan_only_commit(self):
        plan = self.plan()
        current = "2" * 40
        plan_bytes = canonical_json(plan).encode("utf-8") + b"\n"

        def exact_git(argv, **_kwargs):
            arguments = argv[1:]
            if arguments == ["rev-list", "--count", f"{plan['code_lock_candidate']['commit']}..{current}"]:
                return mock.Mock(returncode=0, stdout=b"1\n", stderr=b"")
            if arguments == ["diff", "--name-status", f"{plan['code_lock_candidate']['commit']}..{current}"]:
                return mock.Mock(
                    returncode=0,
                    stdout=(
                        b"A\tartifacts/nautilus-sandbox/nautilus-e2e-spike-plan-v0.65.0.json\n"
                        b"A\ttests/test_nautilus_v065_artifacts.py\n"
                    ),
                    stderr=b"",
                )
            if arguments == ["show", f"{current}:artifacts/nautilus-sandbox/nautilus-e2e-spike-plan-v0.65.0.json"]:
                return mock.Mock(returncode=0, stdout=plan_bytes, stderr=b"")
            self.fail(f"unexpected git command: {arguments}")

        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli.subprocess.run",
            side_effect=exact_git,
        ):
            _verify_formal_candidate(plan, current)

        def changed_source(argv, **kwargs):
            value = exact_git(argv, **kwargs)
            if argv[1:3] == ["diff", "--name-status"]:
                value.stdout += b"M\tsrc/crypto_quant/nautilus_v065_ceremony_cli.py\n"
            return value

        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli.subprocess.run",
            side_effect=changed_source,
        ):
            with self.assertRaisesRegex(
                NautilusV065SupplyChainError,
                "NAUTILUS_V065_FORMAL_CANDIDATE_INVALID",
            ):
                _verify_formal_candidate(plan, current)

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

    def test_formal_current_reference_requires_exact_committed_fixture_semantics(self):
        plan = self.plan()
        receipt = __import__("test_nautilus_v065_supply_chain").NautilusV065SupplyChainTests().receipt()
        request = build_nautilus_v065_request(
            plan_id=receipt["plan_id"],
            plan_hash=receipt["plan_hash"],
            supply_chain_receipt_id=receipt["receipt_id"],
            supply_chain_receipt_hash=receipt["receipt_hash"],
        )
        expected = build_nautilus_v065_current_reference(request=request)
        fixture = json.loads(
            (ROOT / "tests/fixtures/nautilus-v065/current-reference-v2.json").read_text()
        )
        fixture_bytes = canonical_json(fixture).encode("utf-8") + b"\n"
        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._read_candidate_blob",
            return_value=fixture_bytes,
        ) as read:
            self.assertEqual(_load_frozen_current_reference(plan, request), expected)
        read.assert_called_once_with(
            plan["code_lock_candidate"]["commit"],
            "tests/fixtures/nautilus-v065/current-reference-v2.json",
        )

        changed = copy.deepcopy(fixture)
        changed["scenario_results"][0]["net_pnl_usdt"] = "999"
        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._read_candidate_blob",
            return_value=canonical_json(changed).encode("utf-8") + b"\n",
        ):
            with self.assertRaisesRegex(
                NautilusV065SupplyChainError,
                "NAUTILUS_V065_CURRENT_REFERENCE_INVALID",
            ):
                _load_frozen_current_reference(plan, request)

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
            side_effect=[expected, expected, expected, expected],
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
            run.return_value = mock.Mock(returncode=0, stdout=b"", stderr=b"unexpected-warning")
            with self.assertRaisesRegex(
                NautilusV065SupplyChainError,
                "NAUTILUS_V065_RUNNER_FAILED",
            ):
                _invoke_fixed_runner(
                    python=python,
                    workspace=workspace,
                    request=request,
                    receipt=receipt,
                    invocation="replay",
                )
        self.assertEqual(identity.call_count, 4)
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

    def test_runner_stderr_maps_only_observed_safety_boundaries_to_reject_reasons(self):
        module = __import__(
            "crypto_quant.nautilus_v065_ceremony_cli",
            fromlist=["_runner_failure_reason"],
        )
        self.assertEqual(
            module._runner_failure_reason(1, b"", b"NETWORK_FORBIDDEN\n"),
            "NAUTILUS_V065_SAFETY_NETWORK_ATTEMPT",
        )
        self.assertEqual(
            module._runner_failure_reason(1, b"", b"SECOND_ENGINE_FORBIDDEN\n"),
            "NAUTILUS_V065_SAFETY_SECOND_ENGINE_ATTEMPT",
        )
        self.assertEqual(
            module._runner_failure_reason(1, b"", b"CREDENTIAL_ENV_FORBIDDEN\n"),
            "NAUTILUS_V065_SAFETY_CREDENTIAL_ATTEMPT",
        )
        self.assertEqual(
            module._runner_failure_reason(1, b"", b"anything-else\n"),
            "NAUTILUS_V065_RUNNER_FAILED",
        )

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
        transcripts = _supply_transcripts_by_name()
        failed = transcripts["git_version"]
        failed["exit_code"] = 17
        error = NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_NONZERO")
        error.evidence = failed
        calls = [transcripts["uv_version"], transcripts["python_version"], error]
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
        transcripts = _supply_transcripts_by_name()

        def command(name, **_kwargs):
            calls.append(name)
            record = copy.deepcopy(transcripts[name])
            if name.startswith("download:"):
                record["exit_code"] = 22
                raise NautilusV065SupplyChainError(
                    "NAUTILUS_V065_DOWNLOAD_FAILED", evidence=record
                )
            return record

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
            "crypto_quant.nautilus_v065_ceremony_cli._verify_pypi_version_transcript",
        ):
            with _verified_acquisition_workspace(plan) as session:
                receipt = session["receipt"]
        self.assertEqual(receipt["failure"]["completed_transcript_count"], 7)
        self.assertEqual([item["name"] for item in receipt["transcripts"]], calls[:-1])
        self.assertEqual(receipt["failure"]["failed_command"]["name"], calls[-1])

    def test_command_capture_uses_fixed_executable_sanitized_env_and_exact_bytes(self):
        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._run_bounded_command",
            return_value=(0, b"ok\n", b"", False),
        ) as run:
            record = _capture_fixed_command("git_version")
        argv = run.call_args.args[0]
        self.assertEqual(argv, ["/usr/bin/git", "--version"])
        environment = run.call_args.kwargs["environment"]
        self.assertEqual(
            set(environment),
            {"HOME", "LANG", "LC_ALL", "PATH", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT"},
        )
        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertEqual(record["environment"], environment)
        self.assertRegex(record["started_at"], r"^\d{4}-\d{2}-\d{2}T.*Z$")
        self.assertRegex(record["completed_at"], r"^\d{4}-\d{2}-\d{2}T.*Z$")
        self.assertLessEqual(record["started_at"], record["completed_at"])
        self.assertEqual(record["stdout_bytes"], "ok\n")
        self.assertEqual(record["stdout_size"], 3)
        self.assertEqual(record["stdout_sha256"], hashlib.sha256(b"ok\n").hexdigest())
        self.assertEqual(record["stderr_sha256"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(record["executable_sha256_before"], record["executable_sha256_after"])

    def test_supply_commands_freeze_pypi_metadata_and_each_nonredirecting_download(self):
        lock = build_nautilus_v065_dependency_lock(repository_root=ROOT)
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw)
            (workspace / "wheelhouse").mkdir()
            metadata = list(_command("pypi_version", workspace))
            self.assertEqual(
                metadata[-1],
                "https://pypi.org/pypi/nautilus_trader/1.230.0/json",
            )
            self.assertNotIn("--location", metadata)
            self.assertNotIn("--location", _command("license", workspace))
            offline_probe = _command("offline_import", workspace)[-1]
            self.assertIn("importlib.metadata", offline_probe)
            self.assertIn("LGPL-3.0-or-later", offline_probe)
            self.assertIn("m.distributions()", offline_probe)
            self.assertIn("nautilus_trader.adapters", offline_probe)
            urls = __import__(
                "crypto_quant.nautilus_v065_ceremony_cli",
                fromlist=["_download_urls"],
            )._download_urls()
            for item in lock["distributions"]:
                name = "download:" + item["filename"]
                argv = list(_command(name, workspace))
                self.assertNotIn("--location", argv)
                self.assertEqual(argv[-1], urls[item["filename"]])
                self.assertIn(str(workspace / "wheelhouse" / item["filename"]), argv)
                self.assertIn("%{http_code} %{url_effective}\n", argv)
                limit_index = argv.index("--max-filesize")
                self.assertEqual(argv[limit_index + 1], str(item["size"]))

    def test_pypi_version_and_download_transcripts_bind_exact_official_files(self):
        module = __import__(
            "crypto_quant.nautilus_v065_ceremony_cli",
            fromlist=["_verify_pypi_version_transcript"],
        )
        lock = build_nautilus_v065_dependency_lock(repository_root=ROOT)
        candidate = next(
            item for item in lock["distributions"]
            if item["filename"].startswith("nautilus_trader-")
        )
        url = module._download_urls()[candidate["filename"]]
        metadata = {
            "info": {"version": "1.230.0", "requires_python": ">=3.12,<3.15"},
            "urls": [{
                "filename": candidate["filename"],
                "size": candidate["size"],
                "url": url,
                "digests": {"sha256": candidate["sha256"]},
            }],
        }
        record = {
            "stdout_encoding": "utf-8",
            "stdout_bytes": json.dumps(metadata),
        }
        module._verify_pypi_version_transcript(record, lock)
        changed = copy.deepcopy(record)
        changed["stdout_bytes"] = changed["stdout_bytes"].replace(
            "files.pythonhosted.org", "example.invalid"
        )
        with self.assertRaisesRegex(
            NautilusV065SupplyChainError, "NAUTILUS_V065_PYPI_METADATA_MISMATCH"
        ):
            module._verify_pypi_version_transcript(changed, lock)
        changed = copy.deepcopy(record)
        changed["stdout_bytes"] = changed["stdout_bytes"].replace(
            ">=3.12,<3.15", ">=3.11"
        )
        with self.assertRaisesRegex(
            NautilusV065SupplyChainError, "NAUTILUS_V065_PYPI_METADATA_MISMATCH"
        ):
            module._verify_pypi_version_transcript(changed, lock)

        with tempfile.TemporaryDirectory() as raw:
            wheelhouse = Path(raw)
            item = {
                "name": "fixture", "version": "1", "filename": "fixture.whl",
                "size": 3, "sha256": hashlib.sha256(b"abc").hexdigest(),
                "source_origin": "https://files.pythonhosted.org",
            }
            fixture_url = "https://files.pythonhosted.org/fixed/fixture.whl"
            target = wheelhouse / item["filename"]
            target.write_bytes(b"abc")
            download = {
                "stdout_encoding": "utf-8",
                "stdout_bytes": "200 " + fixture_url + "\n",
                "stderr_size": 0,
            }
            with mock.patch.object(module, "_download_urls", return_value={"fixture.whl": fixture_url}):
                self.assertEqual(
                    module._verify_download_transcript(download, item, wheelhouse),
                    item,
                )
                redirected = dict(download, stdout_bytes="200 https://example.invalid/fixture.whl\n")
                with self.assertRaisesRegex(
                    NautilusV065SupplyChainError, "NAUTILUS_V065_DOWNLOAD_IDENTITY_MISMATCH"
                ):
                    module._verify_download_transcript(redirected, item, wheelhouse)

    def test_license_transcript_requires_exact_frozen_size_and_hash(self):
        module = __import__(
            "crypto_quant.nautilus_v065_ceremony_cli",
            fromlist=["_verify_license_transcript"],
        )
        with self.assertRaisesRegex(
            NautilusV065SupplyChainError, "NAUTILUS_V065_LICENSE_MISMATCH"
        ):
            module._verify_license_transcript({
                "stdout_encoding": "utf-8",
                "stdout_bytes": "wrong-license",
            })

    def test_command_capture_fails_closed_on_timeout_output_and_executable_change(self):
        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._run_bounded_command",
            return_value=(-1, b"partial-out", b"partial-err", True),
        ):
            with self.assertRaisesRegex(NautilusV065SupplyChainError, "NAUTILUS_V065_COMMAND_TIMEOUT"):
                _capture_fixed_command("git_version")
        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._run_bounded_command",
            return_value=(0, b"ok", b"", False),
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._executable_identity",
            side_effect=[{"sha256": "1" * 64}, {"sha256": "2" * 64}],
        ):
            with self.assertRaisesRegex(NautilusV065SupplyChainError, "NAUTILUS_V065_EXECUTABLE_CHANGED"):
                _capture_fixed_command("git_version")

    def test_bounded_command_stops_a_live_process_before_output_exceeds_limit(self):
        module = __import__(
            "crypto_quant.nautilus_v065_ceremony_cli",
            fromlist=["_run_bounded_command"],
        )
        started = time.monotonic()
        with self.assertRaisesRegex(
            NautilusV065SupplyChainError, "NAUTILUS_V065_COMMAND_OUTPUT_LIMIT"
        ):
            module._run_bounded_command(
                [sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'x'*(5*1024*1024))"],
                cwd=ROOT,
                environment={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                timeout=10,
            )
        self.assertLess(time.monotonic() - started, 5)

    def test_bounded_command_timeout_does_not_wait_for_escaped_pipe_holder(self):
        code = (
            "import os,time;pid=os.fork();"
            "(os.setsid(),time.sleep(2.5)) if pid==0 else time.sleep(100)"
        )
        started = time.monotonic()
        returncode, _stdout, _stderr, timed_out = _run_bounded_command(
            [sys.executable, "-c", code],
            cwd=ROOT,
            environment={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            timeout=1,
        )
        self.assertTrue(timed_out)
        self.assertNotEqual(returncode, 0)
        self.assertLess(time.monotonic() - started, 2)

    def test_nonzero_command_error_retains_exact_failure_record(self):
        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._run_bounded_command",
            return_value=(17, b"failure-stdout\n", b"failure-stderr\n", False),
        ):
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

            with mock.patch(
                "crypto_quant.nautilus_v065_ceremony_cli._run_bounded_command",
                return_value=(0, b"", b"", False),
            ):
                record = _capture_fixed_command("offline_import", workspace=workspace)
        self.assertEqual(record["executable_path"], str(python_link))
        self.assertEqual(
            record["executable_sha256_before"],
            hashlib.sha256(Path("/usr/bin/true").read_bytes()).hexdigest(),
        )
        self.assertEqual(record["executable_sha256_before"], record["executable_sha256_after"])

    def test_timeout_command_error_retains_partial_output_record(self):
        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._run_bounded_command",
            return_value=(-1, b"partial-out", b"partial-err", True),
        ):
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
        transcripts = _supply_transcripts_by_name()

        def command(name, **_kwargs):
            calls.append(("command", name))
            return copy.deepcopy(transcripts[name])

        def verify_download(_record, item, _wheelhouse):
            return dict(item)

        with mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._capture_fixed_command",
            side_effect=command,
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._verify_pypi_version_transcript",
        ), mock.patch(
            "crypto_quant.nautilus_v065_ceremony_cli._verify_download_transcript",
            side_effect=verify_download,
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
            [
                "uv_version", "python_version", "git_version", "gh_version",
                "pypi_version", "official_tag", "license",
                *["download:" + item["filename"] for item in lock["distributions"]],
                "slsa", "offline_venv", "offline_sync", "offline_import",
            ],
        )
        self.assertFalse(any(kind == "download" for kind, _value in calls))
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

    def test_existing_final_eof_fails_closed_without_hanging(self):
        script = r'''
from pathlib import Path
from unittest import mock
from crypto_quant.nautilus_v065_ceremony_cli import _publish_fixed_artifact
from crypto_quant.nautilus_v065_supply_chain import NautilusV065SupplyChainError
root = Path(__import__("sys").argv[1])
calls = 0
def truncated(_fd, _size):
    global calls
    calls += 1
    return b"{" if calls == 1 else b""
try:
    with mock.patch("crypto_quant.nautilus_v065_ceremony_cli.os.read", side_effect=truncated):
        _publish_fixed_artifact(root=root, final_name="nautilus-supply-chain-receipt-v0.65.0.json", data=b'{"fixed":true}\n')
except NautilusV065SupplyChainError as error:
    if error.reason_code == "NAUTILUS_V065_FINAL_UNTRUSTED":
        raise SystemExit(0)
raise SystemExit(3)
'''
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            target = root / "nautilus-supply-chain-receipt-v0.65.0.json"
            target.write_bytes(b'{"fixed":true}\n')
            target.chmod(0o600)
            completed = subprocess.run(
                [sys.executable, "-c", script, str(root)],
                cwd=ROOT,
                env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=1,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", "replace"))

    def test_existing_final_same_bytes_new_inode_is_rejected(self):
        from crypto_quant import nautilus_v065_ceremony_cli as module

        data = b'{"fixed":true}\n'
        name = "nautilus-supply-chain-receipt-v0.65.0.json"
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            root.chmod(0o700)
            target = root / name
            target.write_bytes(data)
            target.chmod(0o600)
            original_inode = target.stat().st_ino
            original_read = module.os.read
            replaced = False

            def replace_then_read(descriptor, size):
                nonlocal replaced
                if not replaced:
                    replaced = True
                    target.unlink()
                    target.write_bytes(data)
                    target.chmod(0o600)
                return original_read(descriptor, size)

            with mock.patch.object(module.os, "read", side_effect=replace_then_read):
                with self.assertRaisesRegex(
                    NautilusV065SupplyChainError,
                    "NAUTILUS_V065_FINAL_UNTRUSTED",
                ):
                    _publish_fixed_artifact(root=root, final_name=name, data=data)
            self.assertNotEqual(target.stat().st_ino, original_inode)
            self.assertEqual(target.read_bytes(), data)

    def test_source_contains_no_public_override_or_arbitrary_injection_seam(self):
        source = inspect.getsource(__import__("crypto_quant.nautilus_v065_ceremony_cli", fromlist=["*"]))
        self.assertNotIn("fault_injector", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.environ.copy", source)
        self.assertNotIn("--url", source)


if __name__ == "__main__":
    unittest.main()
