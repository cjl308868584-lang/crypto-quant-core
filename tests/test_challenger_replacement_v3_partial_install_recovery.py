import copy
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from crypto_quant.canonical import canonical_json


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = (
    ROOT / "config/challenger-replacement-v3-partial-install-recovery-v0.78.7.json"
)
SCHEMA_PATH = (
    ROOT / "src/crypto_quant/schemas/"
    "challenger-replacement-v3-partial-install-recovery-plan-v1.schema.json"
)


def _file_record(path):
    value = path.stat()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "device": str(value.st_dev),
        "inode": str(value.st_ino),
        "owner_uid": value.st_uid,
        "mode": stat.S_IMODE(value.st_mode),
        "link_count": value.st_nlink,
        "size_bytes": value.st_size,
        "mtime_ns": str(value.st_mtime_ns),
        "ctime_ns": str(value.st_ctime_ns),
    }


def _directory_record(path):
    value = path.stat()
    names = sorted(item.name for item in path.iterdir())
    return {
        "path": str(path),
        "device": str(value.st_dev),
        "inode": str(value.st_ino),
        "owner_uid": value.st_uid,
        "mode": stat.S_IMODE(value.st_mode),
        "link_count": value.st_nlink,
        "size_bytes": value.st_size,
        "mtime_ns": str(value.st_mtime_ns),
        "ctime_ns": str(value.st_ctime_ns),
        "entry_names": names,
        "entry_names_hash": hashlib.sha256(
            canonical_json(names).encode("utf-8")
        ).hexdigest(),
    }


def _sentinel(path):
    value = path.stat()
    return (
        path.read_bytes(), value.st_mode, value.st_size, value.st_ino,
        value.st_nlink, value.st_mtime_ns, value.st_ctime_ns,
    )


class EventWorkspace:
    def __init__(self):
        parent = "/private/tmp" if __import__("platform").system() == "Darwin" else None
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temporary.name)
        os.chmod(self.root, 0o700)

    def cleanup(self):
        self.temporary.cleanup()


def _fixture_plan(module, workspace):
    from crypto_quant.challenger_replacement_install_trust import (
        _publish_snapshot_from_inventory,
    )

    root = workspace.root
    runtime = root / "runtime"
    deployment = runtime / "deployment"
    state = runtime / "state"
    event = state / "challenger-replacement-events-v1"
    start = runtime / "evidence" / "start-receipts"
    log = runtime / "log"
    launch_agents = root / "LaunchAgents"
    source = root / "source"
    for directory in (
        deployment, state, event, start, log, launch_agents,
        source / "config", deployment / "snapshots",
    ):
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)

    payload = source / "payload.txt"
    payload.write_bytes(b"snapshot-payload")
    os.chmod(payload, 0o600)
    manifest = source / "config" / "evaluator-build-manifest-v1.json"
    manifest_value = {
        "file_hashes": {
            "payload.txt": hashlib.sha256(payload.read_bytes()).hexdigest()
        }
    }
    manifest.write_bytes(canonical_json(manifest_value).encode("utf-8"))
    os.chmod(manifest, 0o600)
    inventory = {
        "payload.txt": hashlib.sha256(payload.read_bytes()).hexdigest(),
        "config/evaluator-build-manifest-v1.json": hashlib.sha256(
            manifest.read_bytes()
        ).hexdigest(),
    }
    snapshot = _publish_snapshot_from_inventory(
        source, deployment / "snapshots", inventory
    )

    files = {
        "target_plist": launch_agents / "local.crypto-quant.challenger-replacement-v1.plist",
        "predecessor_plist": launch_agents / "local.crypto-quant.challenger-forward.plist",
        "install_contract": deployment / "challenger-replacement-v3-install-contract-v0.78.5.json",
        "candidate_plist": deployment / "local.crypto-quant.challenger-replacement-v1-v0.78.5.plist",
        "failed_install_receipt": deployment / "install-receipts-v0.78.5" / "failed.json",
        "preflight_receipt": deployment / "preflight-receipts-v0.78.5" / "preflight.json",
    }
    for path in files.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
    files["target_plist"].write_bytes(b"old-target")
    files["predecessor_plist"].write_bytes(b"old-predecessor")
    files["candidate_plist"].write_bytes(b"old-target")
    files["failed_install_receipt"].write_bytes(b"old-failed-receipt")
    files["preflight_receipt"].write_bytes(b"old-preflight-receipt")
    contract_value = {
        "release": {
            "manifest_file_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()
        }
    }
    files["install_contract"].write_bytes(
        canonical_json(contract_value).encode("utf-8")
    )
    for path in files.values():
        os.chmod(path, 0o600)

    automation = root / "automation.toml"
    automation.write_text('id = "v0-78-3-replacement"\nstatus = "PAUSED"\n')
    os.chmod(automation, 0o600)

    plan = module._build_fixed_plan()
    plan["preserved_files"] = {
        name: _file_record(path) for name, path in files.items()
    }
    plan["empty_directories"] = {
        "state_parent": _directory_record(state),
        "event_root": _directory_record(event),
        "start_receipt_root": _directory_record(start),
        "log_root": _directory_record(log),
    }
    snapshot_root = Path(snapshot["root"])
    plan["snapshot"] = {
        "tree_hash": snapshot["tree_hash"],
        "file_count": snapshot["file_count"],
        "total_size_bytes": snapshot["total_size_bytes"],
        "root_record": _directory_record(snapshot_root),
    }
    plan["candidate"] = {
        "release_tag": "v0.78.7",
        "target_plist": str(
            launch_agents / "local.crypto-quant.challenger-replacement-v1-v0.78.7.plist"
        ),
        "recovery_receipt_root": str(
            deployment / "partial-install-recovery-receipts-v0.78.7"
        ),
    }
    plan["required_state"]["automation_path"] = str(automation)
    return plan, files, automation


def _launchctl_result(argv):
    if tuple(argv) == ("/bin/launchctl", "print-disabled", "gui/501"):
        return (
            b'disabled services = {\n\t"local.crypto-quant.challenger-forward" => disabled\n'
            b'\t"local.crypto-quant.challenger-replacement-v1" => disabled\n}\n',
            b"",
            0,
        )
    label = argv[-1].split("/")[-1]
    return (
        b"",
        ("Could not find service \"{}\" in domain for user gui: 501\n".format(label)).encode(),
        113,
    )


def _fifo_verify_child(plan, queue):
    from crypto_quant import challenger_replacement_v3_partial_install_recovery as module

    try:
        module._verify_preserved_partial_install(plan)
    except module.ChallengerReplacementPartialInstallRecoveryError as error:
        queue.put(error.reason_code)
    except BaseException as error:
        queue.put(type(error).__name__)
    else:
        queue.put("UNEXPECTED_SUCCESS")


class PartialInstallRecoveryPlanTests(unittest.TestCase):
    def test_frozen_plan_strictly_binds_incident_and_release_foundation(self):
        self.assertTrue(PLAN_PATH.is_file(), "v0.78.7 recovery plan is missing")
        self.assertTrue(SCHEMA_PATH.is_file(), "v0.78.7 recovery schema is missing")
        from crypto_quant import challenger_replacement_v3_partial_install_recovery as module

        body = PLAN_PATH.read_bytes()
        plan = module.load_fixed_v3_partial_install_recovery_plan_bytes(body)
        self.assertEqual(body, canonical_json(plan).encode("utf-8"))
        self.assertEqual(
            plan["foundation"],
            {
                "manifest_file_sha256": "f06bbfa5dba81cd9f713c4d6b51bbd403d67439b063fdfe1f5b7fe49ae0f5cea",
                "manifest_hash": "808c2fd2aefbfc363725f0cf2a46a74cfc56a538e284dce6fd62042d475ea477",
                "manifest_version": "1.78.0",
                "package_version": "0.78.6",
                "peeled_commit": "faf6e03632c21dba0894f0a1248f308306b13737",
                "release_tag": "v0.78.6",
                "repository": "cjl308868584-lang/crypto-quant-core",
                "tag_object": "bc78d140129a23b38d3c72c1f4a93d8df568275e",
                "visibility": "PUBLIC",
            },
        )
        self.assertEqual(
            plan["preserved_files"]["target_plist"]["sha256"],
            "30efabbd76ab5af9c277213b3377612b5119a7889c6b8165748dbcc36acd329b",
        )
        self.assertEqual(
            plan["preserved_files"]["failed_install_receipt"]["sha256"],
            "97747c0ebd2f49c3afe875e9a1f99d541d98e363ac457e767a622586f8523198",
        )
        self.assertEqual(
            plan["preserved_files"]["preflight_receipt"]["sha256"],
            "3440beab833c998a3d0c250e60fd2f6876f4aa206c0e5c609a772d4333a59ce5",
        )
        self.assertEqual(
            plan["snapshot"]["tree_hash"],
            "b5ac484d5b7b8e61d36c33b7cc686fda23a79524734167158123720b2c14cfbe",
        )
        self.assertEqual(
            (plan["snapshot"]["file_count"], plan["snapshot"]["total_size_bytes"]),
            (101, 3248480),
        )
        self.assertEqual(
            plan["candidate"]["target_plist"],
            "/Users/chenm4/Library/LaunchAgents/"
            "local.crypto-quant.challenger-replacement-v1-v0.78.7.plist",
        )
        self.assertEqual(plan["candidate"]["release_tag"], "v0.78.7")
        self.assertEqual(plan["required_state"]["automation_status"], "PAUSED")
        self.assertEqual(
            plan["required_state"]["service_labels"],
            [
                "local.crypto-quant.challenger-forward",
                "local.crypto-quant.challenger-replacement-v1",
            ],
        )
        self.assertEqual(
            plan["empty_directories"]["state_parent"]["entry_names"],
            ["challenger-replacement-events-v1"],
        )
        for name in ("event_root", "start_receipt_root", "log_root"):
            self.assertEqual(plan["empty_directories"][name]["entry_names"], [])
        for record in list(plan["preserved_files"].values()) + list(
            plan["empty_directories"].values()
        ) + [plan["snapshot"]["root_record"]]:
            for name in ("device", "inode", "mtime_ns", "ctime_ns"):
                self.assertRegex(record[name], r"^(0|[1-9][0-9]*)$")

    def test_plan_loader_rejects_noncanonical_extra_and_tampered_bytes(self):
        self.assertTrue(PLAN_PATH.is_file(), "v0.78.7 recovery plan is missing")
        from crypto_quant import challenger_replacement_v3_partial_install_recovery as module

        body = PLAN_PATH.read_bytes()
        plan = json.loads(body)
        cases = []
        extra = copy.deepcopy(plan)
        extra["unexpected"] = True
        cases.append(canonical_json(extra).encode("utf-8"))
        changed = copy.deepcopy(plan)
        changed["preserved_files"]["target_plist"]["sha256"] = "0" * 64
        cases.append(canonical_json(changed).encode("utf-8"))
        cases.append(body + b"\n")
        for candidate in cases:
            with self.subTest(candidate=candidate[-16:]):
                with self.assertRaisesRegex(
                    ValueError, "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_PLAN_INVALID"
                ):
                    module.load_fixed_v3_partial_install_recovery_plan_bytes(candidate)

    def test_fixed_plan_loader_returns_exact_published_bytes(self):
        self.assertTrue(PLAN_PATH.is_file(), "v0.78.7 recovery plan is missing")
        from crypto_quant import challenger_replacement_v3_partial_install_recovery as module

        value, body = module.load_fixed_v3_partial_install_recovery_plan()
        self.assertEqual(body, PLAN_PATH.read_bytes())
        self.assertEqual(value, json.loads(body))


class PartialInstallRecoveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        from crypto_quant import challenger_replacement_v3_partial_install_recovery as module

        self.module = module
        self.workspace = EventWorkspace()
        self.plan, self.files, self.automation = _fixture_plan(
            module, self.workspace
        )

    def tearDown(self):
        self.workspace.cleanup()

    def _verify(self):
        with patch.object(
            self.module, "_run_observation_command", side_effect=_launchctl_result
        ):
            return self.module._verify_preserved_partial_install(self.plan)

    def test_exact_fixture_returns_normalized_read_only_observation(self):
        observed = self._verify()
        self.assertEqual(observed["service_state"], "DISABLED_AND_NOT_LOADED")
        self.assertEqual(observed["automation_status"], "PAUSED")
        self.assertEqual(observed["event_count"], 0)
        self.assertEqual(observed["start_receipt_count"], 0)
        self.assertEqual(observed["log_file_count"], 0)
        self.assertEqual(
            observed["preserved_file_sha256"],
            {
                name: record["sha256"]
                for name, record in self.plan["preserved_files"].items()
            },
        )

    def test_same_bytes_on_new_inode_is_rejected_without_mutating_sentinel(self):
        target = self.files["target_plist"]
        body = target.read_bytes()
        before = _sentinel(self.files["predecessor_plist"])
        target.unlink()
        target.write_bytes(body)
        os.chmod(target, 0o600)

        with self.assertRaisesRegex(
            ValueError, "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT"
        ):
            self._verify()
        self.assertEqual(_sentinel(self.files["predecessor_plist"]), before)

    def test_mtime_or_ctime_drift_is_rejected(self):
        target = self.files["preflight_receipt"]
        original = target.stat()
        os.utime(
            target,
            ns=(original.st_atime_ns, original.st_mtime_ns + 1_000_000_000),
        )
        with self.assertRaisesRegex(
            ValueError, "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT"
        ):
            self._verify()

    def test_hardlink_and_symlink_substitutions_are_rejected_without_chmod(self):
        target = self.files["failed_install_receipt"]
        sentinel = self.workspace.root / "outside-sentinel"
        sentinel.write_bytes(b"outside")
        os.chmod(sentinel, 0o640)
        for replacement in ("hardlink", "symlink"):
            with self.subTest(replacement=replacement):
                if target.exists() or target.is_symlink():
                    target.unlink()
                if replacement == "hardlink":
                    os.link(sentinel, target)
                else:
                    target.symlink_to(sentinel)
                before = _sentinel(sentinel)
                with self.assertRaisesRegex(
                    ValueError,
                    "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT",
                ):
                    self._verify()
                self.assertEqual(_sentinel(sentinel), before)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_fifo_substitution_fails_quickly_without_blocking_or_writing(self):
        target = self.files["target_plist"]
        target.unlink()
        os.mkfifo(target, 0o600)
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        child = context.Process(target=_fifo_verify_child, args=(self.plan, queue))
        child.start()
        child.join(3)
        if child.is_alive():
            child.kill()
            child.join()
            self.fail("FIFO verification blocked before fstat")
        self.assertEqual(
            queue.get(timeout=1),
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT",
        )
        self.assertEqual(target.stat().st_size, 0)

    def test_replaced_empty_root_inode_is_rejected(self):
        event = Path(self.plan["empty_directories"]["event_root"]["path"])
        displaced = event.with_name(event.name + "-old")
        event.rename(displaced)
        event.mkdir(mode=0o700)
        with self.assertRaisesRegex(
            ValueError, "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT"
        ):
            self._verify()
        self.assertEqual(tuple(displaced.iterdir()), ())

    def test_nonempty_event_start_or_log_root_is_rejected(self):
        for name in ("event_root", "start_receipt_root", "log_root"):
            with self.subTest(name=name):
                path = Path(self.plan["empty_directories"][name]["path"])
                extra = path / "unexpected"
                extra.write_bytes(b"unexpected")
                with self.assertRaisesRegex(
                    ValueError,
                    "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT",
                ):
                    self._verify()
                extra.unlink()

    def test_loaded_or_enabled_service_is_rejected(self):
        def loaded(argv):
            if tuple(argv) == ("/bin/launchctl", "print-disabled", "gui/501"):
                return _launchctl_result(argv)
            if argv[-1].endswith("challenger-forward"):
                return b"loaded", b"", 0
            return _launchctl_result(argv)

        with patch.object(
            self.module, "_run_observation_command", side_effect=loaded
        ):
            with self.assertRaisesRegex(
                ValueError, "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT"
            ):
                self.module._verify_preserved_partial_install(self.plan)

        def enabled(argv):
            if tuple(argv) == ("/bin/launchctl", "print-disabled", "gui/501"):
                stdout, stderr, code = _launchctl_result(argv)
                return stdout.replace(
                    b'"local.crypto-quant.challenger-forward" => disabled',
                    b'"local.crypto-quant.challenger-forward" => enabled',
                ), stderr, code
            return _launchctl_result(argv)

        with patch.object(
            self.module, "_run_observation_command", side_effect=enabled
        ):
            with self.assertRaisesRegex(
                ValueError, "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT"
            ):
                self.module._verify_preserved_partial_install(self.plan)

    def test_unpaused_or_duplicate_automation_status_is_rejected(self):
        for body in (
            'id = "v0-78-3-replacement"\nstatus = "ACTIVE"\n',
            'status = "PAUSED"\nstatus = "PAUSED"\n',
        ):
            with self.subTest(body=body):
                self.automation.write_text(body)
                with self.assertRaisesRegex(
                    ValueError,
                    "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT",
                ):
                    self._verify()

    def test_existing_new_target_is_rejected(self):
        target = Path(self.plan["candidate"]["target_plist"])
        target.write_bytes(b"unexpected")
        os.chmod(target, 0o600)
        before = _sentinel(target)
        with self.assertRaisesRegex(
            ValueError, "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT"
        ):
            self._verify()
        self.assertEqual(_sentinel(target), before)


if __name__ == "__main__":
    unittest.main()
