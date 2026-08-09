import base64
import copy
import ctypes
import errno
import hashlib
import io
import inspect
import json
import multiprocessing
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json, stable_id
from crypto_quant.challenger_replacement_plan_supersession import (
    ACCOUNTABLE_OWNER_DECLARATION,
    ChallengerReplacementPlanSupersessionError,
    build_challenger_replacement_plan_supersession_record,
    load_challenger_replacement_owner_attestation,
    load_challenger_replacement_plan_supersession_record,
    load_challenger_replacement_supersession_machine_evidence,
    supersession_artifact_hash,
)
import crypto_quant.challenger_replacement_plan_supersession as supersession_module
import crypto_quant.challenger_replacement_plan_supersession_cli as supersession_cli
import crypto_quant.challenger_replacement_supersession_publish as publish_module
from crypto_quant.challenger_replacement_plan_v2 import (
    build_challenger_replacement_plan_v2,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts" / "challenger-replacement"
V2_ARTIFACT = ARTIFACT_ROOT / "challenger-replacement-plan-v0.64.0.json"
MACHINE_ARTIFACT = (
    ARTIFACT_ROOT
    / "challenger-replacement-supersession-machine-evidence-v0.64.0.json"
)
ATTESTATION_ARTIFACT = (
    ARTIFACT_ROOT
    / "challenger-replacement-owner-attestation-v0.64.0.json"
)
RECORD_ARTIFACT = (
    ARTIFACT_ROOT
    / "challenger-replacement-plan-supersession-v0.64.0.json"
)

TEST_EVIDENCE_QUALIFICATION = "TEST_FIXTURE_ONLY_NOT_SUPERSESSION_EVIDENCE"
REAL_EVIDENCE_QUALIFICATION = "REAL_MACHINE_READ_ONLY_SUPERSESSION_PRECONDITION"
ABSENCE_SKIP = "FIXED_FORMAL_SUPERSESSION_ARTIFACT_NOT_YET_PUBLISHED"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _test_temp_root():
    darwin_root = Path("/private/tmp")
    if sys.platform == "darwin" and darwin_root.is_dir():
        return darwin_root
    return Path(tempfile.gettempdir())

PREVIOUS_PLAN = {
    "release_tag": "v0.62.0",
    "peeled_commit": "e0a9b3eb6a3f385ea259722e6613df8708e8fe5a",
    "path": (
        "artifacts/challenger-replacement/"
        "challenger-replacement-plan-v0.62.0.json"
    ),
    "file_sha256": "d450d1e9f8dc422eb5a93beb8a5ffbb1746a4a6d1facb3c5a20a76f4bd527734",
    "plan_id": "challenger_replacement_plan_d4a542c1566f7a90466ca4d5301b81847f5b5eba93c7a00903d2d95331bc23a2",
    "plan_hash": "95f395b17d9c09d325c58391542ce5f3d9df5ce6a706b1bba8ffcb62dc6c883c",
    "service_identity": "gui/501/local.crypto-quant.challenger-replacement-v1",
    "runtime_root": (
        "/Users/chenm4/Library/Application Support/CryptoQuant/"
        "challenger-replacement-v1"
    ),
}


def _canonical_file(path, value):
    path.write_bytes(canonical_json(value).encode("utf-8") + b"\n")
    path.chmod(0o644)
    return path


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finalize(value, *, id_field, hash_field, prefix):
    value[id_field] = stable_id(
        prefix,
        {key: item for key, item in value.items() if key not in (id_field, hash_field)},
    )
    value[hash_field] = supersession_artifact_hash(value, hash_field)
    return value


def _transcript(name, argv, stdout=b""):
    return {
        "name": name,
        "argv": list(argv),
        "exit_code": 0,
        "stdout_base64": base64.b64encode(stdout).decode("ascii"),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_base64": "",
        "stderr_sha256": EMPTY_SHA256,
    }


def _machine_evidence(qualification=REAL_EVIDENCE_QUALIFICATION):
    transcripts = [
        _transcript("v0_62_tag_type", ("/usr/bin/git", "cat-file", "-t", "v0.62.0"), b"tag\n"),
        _transcript("v0_63_tag_type", ("/usr/bin/git", "cat-file", "-t", "v0.63.0"), b"tag\n"),
        _transcript("candidate_status", ("/usr/bin/git", "status", "--porcelain=v1")),
    ]
    git_history = {
        "v0_62_tag_type": "tag",
        "v0_62_peeled_commit": PREVIOUS_PLAN["peeled_commit"],
        "v0_62_plan_path": PREVIOUS_PLAN["path"],
        "v0_62_plan_file_sha256": PREVIOUS_PLAN["file_sha256"],
        "v0_62_plan_id": PREVIOUS_PLAN["plan_id"],
        "v0_62_plan_hash": PREVIOUS_PLAN["plan_hash"],
        "v0_63_tag_type": "tag",
        "v0_63_peeled_commit": "df91e19240df14839125608422489adf3b902e76",
        "candidate_head": "1" * 40,
        "v0_63_ancestor_of_candidate": True,
        "candidate_status_porcelain_base64": "",
        "candidate_status_porcelain_sha256": EMPTY_SHA256,
        "transcripts": transcripts,
        "git_history_evidence_hash": "0" * 64,
    }
    git_history["git_history_evidence_hash"] = supersession_artifact_hash(
        git_history, "git_history_evidence_hash"
    )
    evidence = {
        "$schema": "./challenger-replacement-supersession-machine-evidence-v1.schema.json",
        "schema_version": "1.0.0",
        "evidence_id": "challenger_replacement_supersession_machine_evidence_" + "0" * 64,
        "evidence_hash": "0" * 64,
        "evidence_qualification": qualification,
        "observed_at": "2026-08-10T00:00:00.000Z",
        "system_timezone": "Asia/Shanghai",
        "effective_uid": 501,
        "observation": "NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION",
        "service_identity": PREVIOUS_PLAN["service_identity"],
        "runtime_root": PREVIOUS_PLAN["runtime_root"],
        "target_plist": (
            "/Users/chenm4/Library/LaunchAgents/"
            "local.crypto-quant.challenger-replacement-v1.plist"
        ),
        "current_observations": {
            "runtime_root_lstat": "ENOENT",
            "target_plist_lstat": "ENOENT",
            "service_state": "NOT_LOADED",
            "start_receipt_root_state": "ABSENT_DERIVED_FROM_RUNTIME_ROOT_ABSENT",
            "start_receipt_count": 0,
            "state_event_root_state": "ABSENT_DERIVED_FROM_RUNTIME_ROOT_ABSENT",
            "state_event_count": 0,
            "canonical_event_count": 0,
        },
        "collector_actions": {
            "state_write_count": 0,
            "runner_invocation_count": 0,
            "market_request_count": 0,
            "broker_request_count": 0,
            "order_count": 0,
        },
        "launchctl_transcript": _transcript(
            "replacement_service_state",
            (
                "/bin/launchctl",
                "print",
                "gui/501/local.crypto-quant.challenger-replacement-v1",
            ),
        ),
        "git_history": git_history,
    }
    return _finalize(
        evidence,
        id_field="evidence_id",
        hash_field="evidence_hash",
        prefix="challenger_replacement_supersession_machine_evidence",
    )


def _superseding_plan_binding(v2_path, v2):
    return {
        "path": (
            "artifacts/challenger-replacement/"
            "challenger-replacement-plan-v0.64.0.json"
        ),
        "file_sha256": _file_sha(v2_path),
        "plan_id": v2["plan_id"],
        "plan_hash": v2["plan_hash"],
        "foundation": v2["foundation"],
        "service_identity": v2["isolation_policy"]["service_identity"],
        "runtime_root": v2["isolation_policy"]["runtime_root"],
    }


def _final_snapshot(path, relative_path):
    value = path.stat()
    return {
        "path": relative_path,
        "file_sha256": _file_sha(path),
        "device_decimal": str(value.st_dev),
        "inode_decimal": str(value.st_ino),
        "mode_octal": format(stat.S_IMODE(value.st_mode), "04o"),
        "nlink": value.st_nlink,
        "size": value.st_size,
        "mtime_ns_decimal": str(value.st_mtime_ns),
        "ctime_ns_decimal": str(value.st_ctime_ns),
    }


def _ceremony_precondition(state, status_lines, snapshots):
    head = "1" * 40
    status = b"".join((line + "\n").encode() for line in sorted(status_lines))
    return {
        "state": state,
        "candidate_head": head,
        "head_transcript": _transcript(
            state.lower() + "_head",
            ("/usr/bin/git", "rev-parse", "HEAD"),
            (head + "\n").encode(),
        ),
        "status_transcript": _transcript(
            state.lower() + "_status",
            (
                "/usr/bin/git",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ),
            status,
        ),
        "allowlisted_finals": snapshots,
        "staging_inventory": [],
    }


def _attestation(v2_path, machine_path, *, qualification=REAL_EVIDENCE_QUALIFICATION):
    v2 = build_challenger_replacement_plan_v2()
    machine = json.loads(machine_path.read_bytes())
    value = {
        "$schema": "./challenger-replacement-owner-attestation-v1.schema.json",
        "schema_version": "1.0.0",
        "attestation_id": "challenger_replacement_owner_attestation_" + "0" * 64,
        "attestation_hash": "0" * 64,
        "evidence_qualification": qualification,
        "attestation_type": "ACCOUNTABLE_OWNER_PRE_START_HISTORY_ATTESTATION_V1",
        "signed_at": "2026-08-10T00:05:00.000Z",
        "signer_github_login": "cjl308868584-lang",
        "signer_os_username": "chenm4",
        "signer_uid": 501,
        "declaration": ACCOUNTABLE_OWNER_DECLARATION,
        "owner_acknowledgement": "I_SIGN_AND_ACCEPT_ACCOUNTABILITY_FOR_THE_EXACT_DECLARATION",
        "previous_plan": copy.deepcopy(PREVIOUS_PLAN),
        "superseding_plan": _superseding_plan_binding(v2_path, v2),
        "machine_evidence_binding": {
            "path": (
                "artifacts/challenger-replacement/"
                "challenger-replacement-supersession-machine-evidence-v0.64.0.json"
            ),
            "file_sha256": _file_sha(machine_path),
            "evidence_id": machine["evidence_id"],
            "evidence_hash": machine["evidence_hash"],
            "git_history_evidence_hash": machine["git_history"][
                "git_history_evidence_hash"
            ],
        },
        "ceremony_precondition": _ceremony_precondition(
            "C1_EVIDENCE_ONLY",
            (
                "?? artifacts/challenger-replacement/"
                "challenger-replacement-supersession-machine-evidence-v0.64.0.json",
            ),
            [
                _final_snapshot(
                    machine_path,
                    "artifacts/challenger-replacement/"
                    "challenger-replacement-supersession-machine-evidence-v0.64.0.json",
                )
            ],
        ),
    }
    return _finalize(
        value,
        id_field="attestation_id",
        hash_field="attestation_hash",
        prefix="challenger_replacement_owner_attestation",
    )


class SupersessionContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.v2 = build_challenger_replacement_plan_v2()
        self.v2_path = _canonical_file(self.root / "v2.json", self.v2)
        self.machine = _machine_evidence()
        self.machine_path = _canonical_file(self.root / "machine.json", self.machine)
        self.attestation = _attestation(self.v2_path, self.machine_path)
        self.attestation_path = _canonical_file(
            self.root / "attestation.json", self.attestation
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_canonical_fixture_files_have_explicit_formal_artifact_mode(self):
        previous_umask = os.umask(0o022)
        try:
            path = _canonical_file(self.root / "owner-only.json", self.machine)
        finally:
            os.umask(previous_umask)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_machine_evidence_separates_current_observation_from_history(self):
        loaded = load_challenger_replacement_supersession_machine_evidence(
            self.machine_path
        )
        self.assertEqual(
            loaded["observation"],
            "NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION",
        )
        self.assertEqual(loaded["current_observations"]["canonical_event_count"], 0)
        self.assertEqual(set(loaded["collector_actions"].values()), {0})
        self.assertNotIn("historical_state_write_count", canonical_json(loaded))

    def test_schema_mirrors_are_strict_closed_objects(self):
        names = (
            "challenger-replacement-supersession-machine-evidence-v1.schema.json",
            "challenger-replacement-owner-attestation-v1.schema.json",
            "challenger-replacement-plan-supersession-v1.schema.json",
        )
        for name in names:
            with self.subTest(name=name):
                config = (ROOT / "config" / name).read_bytes()
                package = (ROOT / "src" / "crypto_quant" / "schemas" / name).read_bytes()
                self.assertEqual(config, package)
                schema = json.loads(config)
                Draft202012Validator.check_schema(schema)
                pending = [schema]
                while pending:
                    node = pending.pop()
                    if isinstance(node, dict):
                        if node.get("type") == "object":
                            self.assertIs(node.get("additionalProperties"), False)
                        pending.extend(node.values())
                    elif isinstance(node, list):
                        pending.extend(node)

    def test_test_qualified_fixture_is_structurally_valid_but_formally_rejected(self):
        fixture = _machine_evidence(TEST_EVIDENCE_QUALIFICATION)
        schema = json.loads(
            (ROOT / "config" / "challenger-replacement-supersession-machine-evidence-v1.schema.json").read_bytes()
        )
        self.assertFalse(list(Draft202012Validator(schema).iter_errors(fixture)))
        self.assertEqual(
            fixture["evidence_hash"],
            supersession_artifact_hash(fixture, "evidence_hash"),
        )
        path = _canonical_file(self.root / "fixture.json", fixture)
        with self.assertRaises(ChallengerReplacementPlanSupersessionError):
            load_challenger_replacement_supersession_machine_evidence(path)

    def test_attestation_binds_owner_declaration_plans_and_evidence(self):
        loaded = load_challenger_replacement_owner_attestation(
            self.attestation_path,
            v2_plan_path=self.v2_path,
            machine_evidence_path=self.machine_path,
        )
        self.assertEqual(loaded["declaration"], ACCOUNTABLE_OWNER_DECLARATION)
        self.assertEqual(loaded["previous_plan"], PREVIOUS_PLAN)
        self.assertEqual(
            loaded["superseding_plan"],
            _superseding_plan_binding(self.v2_path, self.v2),
        )

    def test_record_builder_and_loader_bind_every_exact_input(self):
        record_precondition = _ceremony_precondition(
            "C2_EVIDENCE_ATTESTATION_ONLY",
            (
                "?? artifacts/challenger-replacement/"
                "challenger-replacement-owner-attestation-v0.64.0.json",
                "?? artifacts/challenger-replacement/"
                "challenger-replacement-supersession-machine-evidence-v0.64.0.json",
            ),
            [
                _final_snapshot(
                    self.attestation_path,
                    "artifacts/challenger-replacement/"
                    "challenger-replacement-owner-attestation-v0.64.0.json",
                ),
                _final_snapshot(
                    self.machine_path,
                    "artifacts/challenger-replacement/"
                    "challenger-replacement-supersession-machine-evidence-v0.64.0.json",
                ),
            ],
        )
        record = build_challenger_replacement_plan_supersession_record(
            v2_plan_path=self.v2_path,
            machine_evidence_path=self.machine_path,
            owner_attestation_path=self.attestation_path,
            ceremony_precondition=record_precondition,
        )
        record_path = _canonical_file(self.root / "record.json", record)
        self.assertEqual(
            load_challenger_replacement_plan_supersession_record(
                record_path,
                v2_plan_path=self.v2_path,
                machine_evidence_path=self.machine_path,
                owner_attestation_path=self.attestation_path,
            ),
            record,
        )
        self.assertEqual(
            record["prohibition"],
            {
                "reason": "SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION",
                "supersession_forbidden_after": "PLAN_SUPERSESSION_FORBIDDEN_AFTER_FIRST_START_RECEIPT_OR_CANONICAL_EVENT",
            },
        )
        self.assertNotIn("record_file_sha256", record)
        self.assertNotIn("build", record)
        self.assertNotIn("manifest", record)

    def test_machine_and_attestation_prohibitions_fail_closed(self):
        machine_cases = {
            "observation": ("observation", "UNKNOWN"),
            "uid": ("effective_uid", 502),
        }
        for name, (key, value) in machine_cases.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(self.machine)
                changed[key] = value
                _finalize(changed, id_field="evidence_id", hash_field="evidence_hash", prefix="challenger_replacement_supersession_machine_evidence")
                path = _canonical_file(self.root / f"machine-{name}.json", changed)
                with self.assertRaises(ChallengerReplacementPlanSupersessionError):
                    load_challenger_replacement_supersession_machine_evidence(path)

        for section, key, value in (
            ("current_observations", "runtime_root_lstat", "PRESENT"),
            ("current_observations", "target_plist_lstat", "PRESENT"),
            ("current_observations", "service_state", "LOADED"),
            ("current_observations", "start_receipt_count", 1),
            ("current_observations", "state_event_count", 1),
            ("current_observations", "canonical_event_count", 1),
            ("collector_actions", "state_write_count", 1),
            ("collector_actions", "runner_invocation_count", 1),
            ("collector_actions", "market_request_count", 1),
            ("collector_actions", "broker_request_count", 1),
            ("collector_actions", "order_count", 1),
        ):
            with self.subTest(section=section, key=key):
                changed = copy.deepcopy(self.machine)
                changed[section][key] = value
                _finalize(changed, id_field="evidence_id", hash_field="evidence_hash", prefix="challenger_replacement_supersession_machine_evidence")
                path = _canonical_file(self.root / f"machine-{key}.json", changed)
                with self.assertRaises(ChallengerReplacementPlanSupersessionError):
                    load_challenger_replacement_supersession_machine_evidence(path)

        for key, value in (
            ("signer_github_login", "different"),
            ("signer_os_username", "different"),
            ("signer_uid", 502),
            ("signed_at", "UNKNOWN"),
            ("owner_acknowledgement", "NO"),
            ("declaration", "DIFFERENT"),
            ("evidence_qualification", TEST_EVIDENCE_QUALIFICATION),
        ):
            with self.subTest(attestation=key):
                changed = copy.deepcopy(self.attestation)
                changed[key] = value
                _finalize(changed, id_field="attestation_id", hash_field="attestation_hash", prefix="challenger_replacement_owner_attestation")
                path = _canonical_file(self.root / f"attestation-{key}.json", changed)
                with self.assertRaises(ChallengerReplacementPlanSupersessionError):
                    load_challenger_replacement_owner_attestation(
                        path,
                        v2_plan_path=self.v2_path,
                        machine_evidence_path=self.machine_path,
                    )

        for key, value in (
            ("candidate_head", "2" * 40),
            ("staging_inventory", [{"unexpected": True}]),
        ):
            with self.subTest(precondition=key):
                changed = copy.deepcopy(self.attestation)
                changed["ceremony_precondition"][key] = value
                _finalize(
                    changed,
                    id_field="attestation_id",
                    hash_field="attestation_hash",
                    prefix="challenger_replacement_owner_attestation",
                )
                path = _canonical_file(
                    self.root / f"attestation-precondition-{key}.json", changed
                )
                with self.assertRaises(
                    ChallengerReplacementPlanSupersessionError
                ):
                    load_challenger_replacement_owner_attestation(
                        path,
                        v2_plan_path=self.v2_path,
                        machine_evidence_path=self.machine_path,
                    )

        for section, key, value in (
            ("previous_plan", "plan_hash", "f" * 64),
            ("superseding_plan", "plan_hash", "f" * 64),
            ("machine_evidence_binding", "evidence_hash", "f" * 64),
            (
                "machine_evidence_binding",
                "git_history_evidence_hash",
                "f" * 64,
            ),
        ):
            with self.subTest(binding=section, key=key):
                changed = copy.deepcopy(self.attestation)
                changed[section][key] = value
                _finalize(changed, id_field="attestation_id", hash_field="attestation_hash", prefix="challenger_replacement_owner_attestation")
                path = _canonical_file(self.root / f"binding-{section}-{key}.json", changed)
                with self.assertRaises(ChallengerReplacementPlanSupersessionError):
                    load_challenger_replacement_owner_attestation(
                        path,
                        v2_plan_path=self.v2_path,
                        machine_evidence_path=self.machine_path,
                    )

    def test_machine_loader_rejects_ambiguous_git_and_unsafe_json_or_paths(self):
        ambiguous = copy.deepcopy(self.machine)
        ambiguous["git_history"]["transcripts"].append(
            copy.deepcopy(ambiguous["git_history"]["transcripts"][0])
        )
        ambiguous["git_history"]["git_history_evidence_hash"] = supersession_artifact_hash(
            ambiguous["git_history"], "git_history_evidence_hash"
        )
        _finalize(ambiguous, id_field="evidence_id", hash_field="evidence_hash", prefix="challenger_replacement_supersession_machine_evidence")
        ambiguous_path = _canonical_file(self.root / "ambiguous.json", ambiguous)
        with self.assertRaises(ChallengerReplacementPlanSupersessionError):
            load_challenger_replacement_supersession_machine_evidence(
                ambiguous_path
            )

        canonical = canonical_json(self.machine)
        duplicate = self.root / "duplicate.json"
        duplicate.write_text(
            canonical.replace(
                '"effective_uid":501',
                '"effective_uid":501,"effective_uid":501',
                1,
            )
        )
        floating = self.root / "float.json"
        floating.write_text(canonical.replace('"effective_uid":501', '"effective_uid":501.0', 1))
        pretty = self.root / "pretty.json"
        pretty.write_text(json.dumps(self.machine, indent=2))
        writable = _canonical_file(self.root / "writable.json", self.machine)
        writable.chmod(0o666)
        hardlink = self.root / "hardlink.json"
        os.link(self.machine_path, hardlink)
        for path in (duplicate, floating, pretty, writable, hardlink):
            with self.subTest(path=path.name):
                with self.assertRaises(ChallengerReplacementPlanSupersessionError):
                    load_challenger_replacement_supersession_machine_evidence(path)
        with self.assertRaises(ChallengerReplacementPlanSupersessionError):
            load_challenger_replacement_supersession_machine_evidence(
                Path("relative.json")
            )

    def test_binding_sha_rechecks_owner_control_after_semantic_load(self):
        original = load_challenger_replacement_supersession_machine_evidence

        def load_then_make_untrusted(path):
            value = original(path)
            Path(path).chmod(0o666)
            return value

        try:
            with mock.patch.object(
                supersession_module,
                "load_challenger_replacement_supersession_machine_evidence",
                side_effect=load_then_make_untrusted,
            ):
                with self.assertRaises(
                    ChallengerReplacementPlanSupersessionError
                ):
                    load_challenger_replacement_owner_attestation(
                        self.attestation_path,
                        v2_plan_path=self.v2_path,
                        machine_evidence_path=self.machine_path,
                    )
        finally:
            self.machine_path.chmod(0o600)


class CommittedSupersessionArtifactRegressionTests(unittest.TestCase):
    @unittest.skipUnless(MACHINE_ARTIFACT.is_file(), ABSENCE_SKIP)
    def test_committed_supersession_machine_evidence_exact(self):
        load_challenger_replacement_supersession_machine_evidence(MACHINE_ARTIFACT)

    @unittest.skipUnless(ATTESTATION_ARTIFACT.is_file(), ABSENCE_SKIP)
    def test_committed_owner_attestation_exact(self):
        load_challenger_replacement_owner_attestation(
            ATTESTATION_ARTIFACT,
            v2_plan_path=V2_ARTIFACT,
            machine_evidence_path=MACHINE_ARTIFACT,
        )

    @unittest.skipUnless(RECORD_ARTIFACT.is_file(), ABSENCE_SKIP)
    def test_committed_plan_supersession_record_exact(self):
        load_challenger_replacement_plan_supersession_record(
            RECORD_ARTIFACT,
            v2_plan_path=V2_ARTIFACT,
            machine_evidence_path=MACHINE_ARTIFACT,
            owner_attestation_path=ATTESTATION_ARTIFACT,
        )


@unittest.skipUnless(
    os.geteuid() == 501,
    "FIXED_OWNER_UID_501_SECURITY_BOUNDARY_REQUIRES_DEDICATED_CI_STEP",
)
class FixedSupersessionPublisherTests(unittest.TestCase):
    def test_test_temp_root_is_existing_and_platform_appropriate(self):
        root = _test_temp_root()
        self.assertTrue(root.is_dir())
        if sys.platform == "darwin" and Path("/private/tmp").is_dir():
            self.assertEqual(root, Path("/private/tmp"))
        else:
            self.assertEqual(root, Path(tempfile.gettempdir()))
        with mock.patch.object(sys, "platform", "linux"), mock.patch.object(
            tempfile, "gettempdir", return_value="/tmp"
        ):
            self.assertEqual(_test_temp_root(), Path("/tmp"))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=_test_temp_root())
        self.parent = Path(self.temporary.name) / "artifacts" / "challenger-replacement"
        self.parent.mkdir(parents=True, mode=0o755)
        self.parent.chmod(0o755)
        self.parent_patch = mock.patch.object(
            publish_module, "_artifact_parent", return_value=self.parent
        )
        self.parent_patch.start()
        self.publisher_stderr = io.StringIO()
        self.stderr_patch = mock.patch.object(
            publish_module.sys, "stderr", self.publisher_stderr
        )
        self.stderr_patch.start()

    def tearDown(self):
        self.stderr_patch.stop()
        self.parent_patch.stop()
        self.temporary.cleanup()

    def test_public_publishers_accept_bytes_but_no_path_or_override(self):
        for function in (
            publish_module.publish_challenger_replacement_plan_v2_bytes,
            publish_module.publish_challenger_replacement_machine_evidence_bytes,
            publish_module.publish_challenger_replacement_owner_attestation_bytes,
            publish_module.publish_challenger_replacement_supersession_record_bytes,
        ):
            self.assertEqual(tuple(inspect.signature(function).parameters), ("data",))

    def test_exact_publish_is_no_overwrite_and_replayable(self):
        data = b'{"fixed":true}\n'
        first = publish_module.publish_challenger_replacement_plan_v2_bytes(data)
        final = self.parent / "challenger-replacement-plan-v0.64.0.json"
        first_stat = final.stat()
        self.assertEqual(first["status"], "COMMITTED")
        self.assertEqual(final.read_bytes(), data)
        self.assertEqual(stat.S_IMODE(first_stat.st_mode), 0o644)
        self.assertEqual(first_stat.st_nlink, 1)

        second = publish_module.publish_challenger_replacement_plan_v2_bytes(data)
        second_stat = final.stat()
        self.assertEqual(second["status"], "ALREADY_PUBLISHED")
        self.assertEqual((second_stat.st_dev, second_stat.st_ino), (first_stat.st_dev, first_stat.st_ino))
        with self.assertRaises(publish_module.SupersessionPublishError):
            publish_module.publish_challenger_replacement_plan_v2_bytes(b"different\n")
        self.assertEqual(final.read_bytes(), data)

    def test_untrusted_final_and_sealed_orphan_never_modify_sentinel(self):
        sentinel = Path(self.temporary.name) / "sentinel"
        sentinel.write_bytes(b"sentinel")
        sentinel.chmod(0o600)
        final = self.parent / "challenger-replacement-plan-v0.64.0.json"
        final.symlink_to(sentinel)
        before = sentinel.stat()
        with self.assertRaises(publish_module.SupersessionPublishError):
            publish_module.publish_challenger_replacement_plan_v2_bytes(b"plan\n")
        after = sentinel.stat()
        self.assertEqual(sentinel.read_bytes(), b"sentinel")
        self.assertEqual(
            (after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_dev, after.st_ino, after.st_nlink),
            (before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_dev, before.st_ino, before.st_nlink),
        )

        final.unlink()
        orphan = self.parent / (
            ".v064-supersession-plan-" + "a" * 64 + "-" + "b" * 32 + ".staging"
        )
        orphan.write_bytes(b"sealed")
        orphan.chmod(0o644)
        orphan_before = orphan.stat()
        with self.assertRaisesRegex(
            publish_module.SupersessionPublishError,
            "RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED",
        ):
            publish_module.publish_challenger_replacement_plan_v2_bytes(b"plan\n")
        orphan_after = orphan.stat()
        self.assertEqual(orphan.read_bytes(), b"sealed")
        self.assertEqual(
            (orphan_after.st_mode, orphan_after.st_size, orphan_after.st_mtime_ns, orphan_after.st_ctime_ns, orphan_after.st_dev, orphan_after.st_ino, orphan_after.st_nlink),
            (orphan_before.st_mode, orphan_before.st_size, orphan_before.st_mtime_ns, orphan_before.st_ctime_ns, orphan_before.st_dev, orphan_before.st_ino, orphan_before.st_nlink),
        )
        self.assertEqual(final.read_bytes(), b"plan\n")

    def test_untrusted_staging_entries_fail_without_touching_external_inode(self):
        sentinel = Path(self.temporary.name) / "external-sentinel"
        sentinel.write_bytes(b"external")
        sentinel.chmod(0o600)
        for kind in ("symlink", "hardlink"):
            staging = self.parent / (
                ".v064-supersession-plan-" + "c" * 64 + "-" + "d" * 32 + ".staging"
            )
            if kind == "symlink":
                staging.symlink_to(sentinel)
            else:
                os.link(sentinel, staging)
            before = sentinel.stat()
            with self.subTest(kind=kind), self.assertRaisesRegex(
                publish_module.SupersessionPublishError,
                "STAGING_INVENTORY_INVALID",
            ):
                publish_module.publish_challenger_replacement_plan_v2_bytes(b"plan\n")
            after = sentinel.stat()
            self.assertEqual(sentinel.read_bytes(), b"external")
            self.assertEqual(
                (
                    after.st_mode,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                    after.st_dev,
                    after.st_ino,
                    after.st_nlink,
                ),
                (
                    before.st_mode,
                    before.st_size,
                    before.st_mtime_ns,
                    before.st_ctime_ns,
                    before.st_dev,
                    before.st_ino,
                    before.st_nlink,
                ),
            )
            staging.unlink()

    def test_sixty_fifth_protocol_staging_entry_fails_closed(self):
        for index in range(65):
            entry = self.parent / (
                ".v064-supersession-plan-"
                + "e" * 64
                + "-"
                + format(index, "032x")
                + ".staging"
            )
            entry.write_bytes(b"")
            entry.chmod(0o644)
        with self.assertRaisesRegex(
            publish_module.SupersessionPublishError,
            "STAGING_INVENTORY_INVALID",
        ):
            publish_module.publish_challenger_replacement_plan_v2_bytes(b"plan\n")

    def test_actual_platform_no_replace_preserves_existing_inode(self):
        staging = self.parent / "staging"
        final = self.parent / "final"
        staging.write_bytes(b"new")
        final.write_bytes(b"old")
        before = final.stat()
        descriptor = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaises(FileExistsError):
                publish_module._atomic_no_replace(
                    descriptor, staging.name, final.name
                )
        finally:
            os.close(descriptor)
        after = final.stat()
        self.assertEqual(final.read_bytes(), b"old")
        self.assertEqual((after.st_dev, after.st_ino), (before.st_dev, before.st_ino))
        self.assertTrue(staging.exists())

    def test_two_fresh_interpreters_race_raw_primitive_success_and_eexist(self):
        staging_names = ("raw-staging-a", "raw-staging-b")
        for name in staging_names:
            (self.parent / name).write_bytes(name.encode())
        start = Path(self.temporary.name) / "start-race"
        script = r'''
import sys, time
from pathlib import Path
import crypto_quant.challenger_replacement_supersession_publish as module
parent, staging, start = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
deadline = time.monotonic() + 5
while not start.exists():
    if time.monotonic() >= deadline:
        raise SystemExit(90)
    time.sleep(0.005)
descriptor = __import__("os").open(parent, __import__("os").O_RDONLY | __import__("os").O_DIRECTORY)
try:
    module._atomic_no_replace(descriptor, staging, "raw-final")
except FileExistsError:
    print("EEXIST")
else:
    print("SUCCESS")
finally:
    __import__("os").close(descriptor)
'''
        environment = {"PYTHONPATH": str(ROOT / "src")}
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", script, str(self.parent), name, str(start)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
            )
            for name in staging_names
        ]
        start.touch()
        outputs = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            outputs.append(stdout.strip())
        self.assertEqual(sorted(outputs), [b"EEXIST", b"SUCCESS"])
        self.assertTrue((self.parent / "raw-final").is_file())

    def test_actual_two_process_publication_race_leaves_exact_final_but_blocks_release(self):
        context = multiprocessing.get_context("fork")
        barrier = context.Barrier(2)
        queue = context.Queue()

        def publish_after_barrier():
            barrier.wait()
            try:
                result = publish_module.publish_challenger_replacement_plan_v2_bytes(
                    b'{"race":true}\n'
                )
                queue.put(("ok", result["status"], result["inode"]))
            except BaseException as error:
                queue.put(("error", type(error).__name__, str(error)))

        workers = [context.Process(target=publish_after_barrier) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(worker.exitcode, 0)
        outcomes = [queue.get(timeout=1) for _ in workers]
        self.assertTrue(any(item[0] == "error" for item in outcomes))
        for item in outcomes:
            if item[0] == "error":
                self.assertIn("RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED", item[2])
            else:
                self.assertEqual(item[1], "COMMITTED")
        final = self.parent / "challenger-replacement-plan-v0.64.0.json"
        self.assertEqual(final.read_bytes(), b'{"race":true}\n')
        self.assertEqual(final.stat().st_nlink, 1)

    def test_directory_fsync_failure_is_repaired_before_exact_retry_succeeds(self):
        data = b'{"durable":true}\n'
        real_fsync = publish_module._fsync_retry
        calls = []

        def fail_before_directory_fsync(descriptor):
            calls.append(descriptor)
            if len(calls) == 2:
                raise publish_module.SupersessionPublishError(
                    "CHALLENGER_REPLACEMENT_SUPERSESSION_FSYNC_FAILED"
                )
            return real_fsync(descriptor)

        with mock.patch.object(
            publish_module,
            "_fsync_retry",
            side_effect=fail_before_directory_fsync,
        ):
            with self.assertRaisesRegex(
                publish_module.SupersessionPublishError, "FSYNC_FAILED"
            ):
                publish_module.publish_challenger_replacement_plan_v2_bytes(data)
        final = self.parent / "challenger-replacement-plan-v0.64.0.json"
        self.assertEqual(final.read_bytes(), data)

        with mock.patch.object(
            publish_module, "_fsync_retry", wraps=real_fsync
        ) as repaired:
            result = publish_module.publish_challenger_replacement_plan_v2_bytes(data)
        self.assertEqual(result["status"], "ALREADY_PUBLISHED")
        self.assertEqual(repaired.call_count, 1)

    def test_fresh_interpreter_repairs_visible_final_after_dir_fsync_crash(self):
        environment = {"PYTHONPATH": str(ROOT / "src")}
        crash_script = r'''
import sys
from pathlib import Path
import crypto_quant.challenger_replacement_supersession_publish as module
module._artifact_parent = lambda: Path(sys.argv[1])
real = module._fsync_retry
count = 0
def fail_before_directory_fsync(descriptor):
    global count
    count += 1
    if count == 2:
        raise module.SupersessionPublishError("CHALLENGER_REPLACEMENT_SUPERSESSION_FSYNC_FAILED")
    return real(descriptor)
module._fsync_retry = fail_before_directory_fsync
try:
    module.publish_challenger_replacement_plan_v2_bytes(b'{"fresh":true}\n')
except module.SupersessionPublishError as error:
    print(error.reason_code)
    raise SystemExit(17)
raise SystemExit(99)
'''
        crashed = subprocess.run(
            [sys.executable, "-c", crash_script, str(self.parent)],
            capture_output=True,
            env=environment,
            check=False,
        )
        self.assertEqual(crashed.returncode, 17, crashed.stderr)
        self.assertIn(b"FSYNC_FAILED", crashed.stdout)
        final = self.parent / "challenger-replacement-plan-v0.64.0.json"
        first_inode = final.stat().st_ino

        replay_script = r'''
import sys
from pathlib import Path
import crypto_quant.challenger_replacement_supersession_publish as module
module._artifact_parent = lambda: Path(sys.argv[1])
result = module.publish_challenger_replacement_plan_v2_bytes(b'{"fresh":true}\n')
print(result["status"])
'''
        replayed = subprocess.run(
            [sys.executable, "-c", replay_script, str(self.parent)],
            capture_output=True,
            env=environment,
            check=False,
        )
        self.assertEqual(replayed.returncode, 0, replayed.stderr)
        self.assertEqual(replayed.stdout, b"ALREADY_PUBLISHED\n")
        self.assertEqual(final.stat().st_ino, first_inode)

    def test_fresh_interpreter_recovers_partial_file_fsync_and_noreplace_crashes(self):
        environment = {"PYTHONPATH": str(ROOT / "src")}
        crash_script = r'''
import os, sys
from pathlib import Path
import crypto_quant.challenger_replacement_supersession_publish as module
module._artifact_parent = lambda: Path(sys.argv[1])
scenario = sys.argv[2]
if scenario == "partial-write":
    def partial(descriptor, data):
        os.write(descriptor, data[:2])
        raise module.SupersessionPublishError("CHALLENGER_REPLACEMENT_SUPERSESSION_WRITE_FAILED")
    module._write_all = partial
elif scenario == "file-fsync":
    real = module._fsync_retry
    count = 0
    def fail_file_fsync(descriptor):
        global count
        count += 1
        if count == 1:
            raise module.SupersessionPublishError("CHALLENGER_REPLACEMENT_SUPERSESSION_FSYNC_FAILED")
        return real(descriptor)
    module._fsync_retry = fail_file_fsync
elif scenario == "no-replace":
    def fail_no_replace(*unused):
        raise module.SupersessionPublishError("CHALLENGER_REPLACEMENT_SUPERSESSION_ATOMIC_NOREPLACE_FAILED")
    module._atomic_no_replace = fail_no_replace
try:
    module.publish_challenger_replacement_plan_v2_bytes(b'{"fresh":true}\n')
except module.SupersessionPublishError as error:
    print(error.reason_code)
    raise SystemExit(17)
raise SystemExit(99)
'''
        retry_script = r'''
import sys
from pathlib import Path
import crypto_quant.challenger_replacement_supersession_publish as module
module._artifact_parent = lambda: Path(sys.argv[1])
try:
    module.publish_challenger_replacement_plan_v2_bytes(b'{"fresh":true}\n')
except module.SupersessionPublishError as error:
    print(error.reason_code)
    raise SystemExit(18)
raise SystemExit(99)
'''
        for scenario in ("partial-write", "file-fsync", "no-replace"):
            with self.subTest(scenario=scenario):
                parent = (
                    Path(self.temporary.name)
                    / ("crash-" + scenario)
                    / "artifacts"
                    / "challenger-replacement"
                )
                parent.mkdir(parents=True, mode=0o755)
                parent.chmod(0o755)
                crashed = subprocess.run(
                    [sys.executable, "-c", crash_script, str(parent), scenario],
                    capture_output=True,
                    env=environment,
                    check=False,
                )
                self.assertEqual(crashed.returncode, 17, crashed.stderr)
                retried = subprocess.run(
                    [sys.executable, "-c", retry_script, str(parent)],
                    capture_output=True,
                    env=environment,
                    check=False,
                )
                self.assertEqual(retried.returncode, 18, retried.stderr)
                self.assertIn(
                    b"RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED",
                    retried.stdout,
                )
                self.assertEqual(
                    (parent / "challenger-replacement-plan-v0.64.0.json").read_bytes(),
                    b'{"fresh":true}\n',
                )
                self.assertEqual(
                    len(tuple(parent.glob(".v064-supersession-*.staging"))),
                    1,
                )

    def test_new_orphan_seen_after_final_replay_blocks_success(self):
        data = b'{"final":true}\n'
        publish_module.publish_challenger_replacement_plan_v2_bytes(data)
        real_inventory = publish_module._inventory_staging
        calls = 0

        def inject_before_post_inventory(parent_fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                entry = self.parent / (
                    ".v064-supersession-plan-"
                    + "f" * 64
                    + "-"
                    + "1" * 32
                    + ".staging"
                )
                entry.write_bytes(b"sealed")
                entry.chmod(0o644)
            return real_inventory(parent_fd)

        with mock.patch.object(
            publish_module,
            "_inventory_staging",
            side_effect=inject_before_post_inventory,
        ):
            with self.assertRaisesRegex(
                publish_module.SupersessionPublishError,
                "RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED",
            ):
                publish_module.publish_challenger_replacement_plan_v2_bytes(data)

    def test_missing_platform_no_replace_symbol_fails_closed(self):
        descriptor = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with mock.patch.object(
                publish_module.ctypes, "CDLL", return_value=object()
            ):
                with self.assertRaisesRegex(
                    publish_module.SupersessionPublishError,
                    "ATOMIC_NOREPLACE_UNSUPPORTED",
                ):
                    publish_module._atomic_no_replace(
                        descriptor, "staging", "final"
                    )
        finally:
            os.close(descriptor)

    def test_unsupported_platform_errnos_have_one_fixed_failure(self):
        class FailingPrimitive:
            argtypes = None
            restype = None

            def __init__(self, code):
                self.code = code

            def __call__(self, *unused_args):
                ctypes.set_errno(self.code)
                return -1

        descriptor = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for code in {
                errno.ENOSYS,
                getattr(errno, "EOPNOTSUPP", errno.ENOSYS),
                getattr(errno, "ENOTSUP", errno.ENOSYS),
            }:
                library = type("Library", (), {})()
                attribute = (
                    "renameatx_np"
                    if publish_module.platform.system() == "Darwin"
                    else "renameat2"
                )
                setattr(library, attribute, FailingPrimitive(code))
                with self.subTest(code=code), mock.patch.object(
                    publish_module.ctypes, "CDLL", return_value=library
                ):
                    with self.assertRaisesRegex(
                        publish_module.SupersessionPublishError,
                        "ATOMIC_NOREPLACE_UNSUPPORTED",
                    ):
                        publish_module._atomic_no_replace(
                            descriptor, "staging", "final"
                        )
        finally:
            os.close(descriptor)

    def test_parent_replacement_before_success_fails_closed(self):
        real_no_replace = publish_module._atomic_no_replace
        displaced = self.parent.with_name("challenger-replacement-displaced")

        def replace_parent_after_publish(parent_fd, staging_name, final_name):
            real_no_replace(parent_fd, staging_name, final_name)
            os.rename(self.parent, displaced)
            self.parent.mkdir(mode=0o755)
            self.parent.chmod(0o755)

        with mock.patch.object(
            publish_module,
            "_atomic_no_replace",
            side_effect=replace_parent_after_publish,
        ):
            with self.assertRaisesRegex(
                publish_module.SupersessionPublishError, "PARENT_INVALID"
            ):
                publish_module.publish_challenger_replacement_plan_v2_bytes(b"plan\n")
        self.assertFalse(
            (self.parent / "challenger-replacement-plan-v0.64.0.json").exists()
        )
        self.assertEqual(
            (displaced / "challenger-replacement-plan-v0.64.0.json").read_bytes(),
            b"plan\n",
        )

    def test_staging_path_swap_during_file_fsync_never_reaches_final(self):
        attacker = self.parent / "attacker"
        attacker.write_bytes(b"attacker")
        attacker.chmod(0o644)
        real_fsync = publish_module._fsync_retry
        calls = 0

        def swap_after_file_fsync(descriptor):
            nonlocal calls
            real_fsync(descriptor)
            calls += 1
            if calls == 1:
                staging = next(self.parent.glob(".v064-supersession-*.staging"))
                os.replace(attacker, staging)

        with mock.patch.object(
            publish_module, "_fsync_retry", side_effect=swap_after_file_fsync
        ):
            with self.assertRaisesRegex(
                publish_module.SupersessionPublishError,
                "STAGING_UNTRUSTED",
            ):
                publish_module.publish_challenger_replacement_plan_v2_bytes(b"plan\n")
        self.assertFalse(
            (self.parent / "challenger-replacement-plan-v0.64.0.json").exists()
        )

    def test_missing_required_open_flags_fail_before_open(self):
        for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"):
            parent_fd = None
            if name == "O_NONBLOCK":
                parent_fd = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY)
            with self.subTest(name=name), mock.patch.object(
                publish_module.os, name, 0
            ), mock.patch.object(publish_module.os, "open") as opened:
                with self.assertRaisesRegex(
                    publish_module.SupersessionPublishError,
                    "PLATFORM_UNSUPPORTED",
                ):
                    if name == "O_NONBLOCK":
                        publish_module._read_final(parent_fd, "missing")
                    else:
                        publish_module._open_parent()
                opened.assert_not_called()
            if parent_fd is not None:
                os.close(parent_fd)

    def test_fifo_final_is_rejected_without_blocking(self):
        final = self.parent / "challenger-replacement-plan-v0.64.0.json"
        os.mkfifo(final, 0o644)
        started = __import__("time").monotonic()
        with self.assertRaisesRegex(
            publish_module.SupersessionPublishError, "FINAL_UNTRUSTED"
        ):
            publish_module.publish_challenger_replacement_plan_v2_bytes(b"plan\n")
        self.assertLess(__import__("time").monotonic() - started, 1.0)

    def test_partial_staging_is_sealed_and_retry_cannot_claim_release_clean(self):
        with mock.patch.object(
            publish_module,
            "_write_all",
            side_effect=publish_module.SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_WRITE_FAILED"
            ),
        ):
            with self.assertRaisesRegex(
                publish_module.SupersessionPublishError, "WRITE_FAILED"
            ):
                publish_module.publish_challenger_replacement_plan_v2_bytes(b"plan\n")
        staging = tuple(self.parent.glob(".v064-supersession-*.staging"))
        self.assertEqual(len(staging), 1)
        self.assertIn(
            "staging_basename=" + staging[0].name,
            self.publisher_stderr.getvalue(),
        )
        with self.assertRaisesRegex(
            publish_module.SupersessionPublishError,
            "RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED",
        ):
            publish_module.publish_challenger_replacement_plan_v2_bytes(b"plan\n")
        self.assertEqual(staging[0].stat().st_nlink, 1)
        self.assertEqual(
            (self.parent / "challenger-replacement-plan-v0.64.0.json").read_bytes(),
            b"plan\n",
        )

    def test_final_fstat_error_is_mapped_and_every_open_fd_is_closed(self):
        final = self.parent / "challenger-replacement-plan-v0.64.0.json"
        final.write_bytes(b"plan\n")
        final.chmod(0o644)
        real_fstat = os.fstat
        real_close = os.close
        fstat_calls = []
        closed = []

        def fail_final_fstat(descriptor):
            fstat_calls.append(descriptor)
            if len(fstat_calls) == 2:
                raise OSError(5, "injected EIO")
            return real_fstat(descriptor)

        def record_close(descriptor):
            closed.append(descriptor)
            return real_close(descriptor)

        with mock.patch.object(
            publish_module.os, "fstat", side_effect=fail_final_fstat
        ), mock.patch.object(
            publish_module.os, "close", side_effect=record_close
        ):
            with self.assertRaisesRegex(
                publish_module.SupersessionPublishError, "FINAL_UNTRUSTED"
            ):
                publish_module.publish_challenger_replacement_plan_v2_bytes(b"plan\n")
        self.assertEqual(len(closed), 2)
        self.assertEqual(len(set(closed)), 2)

    def test_source_contains_no_fallback_rename_or_hardlink(self):
        source = Path(publish_module.__file__).read_text()
        for forbidden in ("os.rename", "os.replace", "os.link", "os.symlink", "syscall("):
            self.assertNotIn(forbidden, source)


class SupersessionCliBoundaryTests(unittest.TestCase):
    def test_linux_ci_runs_full_suite_and_fixed_owner_boundary_separately(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn(
            "      - uses: actions/checkout@v5\n"
            "        with:\n"
            "          fetch-depth: 0\n",
            workflow,
        )
        fixed_owner_boundary = """\
      - run: make test
      - name: Configure fixed owner UID for security-boundary tests
        run: |
          ! getent passwd 501
          ! getent group 501
          sudo groupadd --gid 501 cryptoquant-ci
          sudo useradd --uid 501 --gid 501 --no-create-home --shell /usr/sbin/nologin cryptoquant-ci
          sudo install -d -o 501 -g 501 -m 700 /opt/cryptoquant-ci-home
          sudo install -d -o 501 -g 501 -m 700 /opt/cryptoquant-ci-workspace
          sudo cp -a "$GITHUB_WORKSPACE/." /opt/cryptoquant-ci-workspace/
          sudo chown -R 501:501 /opt/cryptoquant-ci-workspace
          sudo chmod 700 /opt/cryptoquant-ci-workspace
      - name: Run fixed-owner supersession security-boundary tests
        run: >-
          sudo -u '#501' env
          HOME=/opt/cryptoquant-ci-home
          TMPDIR=/opt/cryptoquant-ci-home
          PATH="$PATH"
          PYTHONPATH=/opt/cryptoquant-ci-workspace/src:/opt/cryptoquant-ci-workspace/tests
          python3 -m unittest
          -v
          test_challenger_replacement_plan_supersession.FixedSupersessionPublisherTests
          test_challenger_replacement_plan_supersession.SupersessionCliBoundaryTests.test_temporary_git_ceremony_transitions_c0_through_c4_exactly
"""
        self.assertIn(fixed_owner_boundary, workflow)
        self.assertEqual(workflow.count("make test"), 1)
        self.assertEqual(workflow.count("python3 -m unittest"), 1)

    @staticmethod
    def _completed(argv, returncode=0, stdout=b"", stderr=b""):
        return type(
            "Completed",
            (),
            {
                "args": argv,
                "returncode": returncode,
                "stdout": stdout,
                "stderr": stderr,
            },
        )()

    def test_only_three_parameterless_commands_are_registered(self):
        self.assertEqual(
            supersession_cli.COMMANDS,
            (
                "collect-machine-evidence",
                "record-owner-attestation",
                "assemble-record",
            ),
        )
        self.assertEqual(tuple(inspect.signature(supersession_cli.main).parameters), ())
        ignore_lines = (ROOT / ".gitignore").read_text().splitlines()
        self.assertEqual(
            [line for line in ignore_lines if "v064-supersession" in line],
            ["/artifacts/challenger-replacement/.v064-supersession-*.staging"],
        )

    def test_git_argv_is_fixed_to_reviewed_repository(self):
        repository = Path("/reviewed/repository")
        argv = supersession_cli._git_argv(repository)
        self.assertEqual(len(argv), 12)
        self.assertEqual(argv[0], ("/usr/bin/git", "-C", str(repository), "rev-parse", "v0.62.0"))
        self.assertEqual(argv[8][-2:], ("--porcelain=v1", "--untracked-files=all"))
        self.assertEqual(
            argv[-1][-3:],
            (
                "artifacts/challenger-replacement/",
                "docs/adr/0062-replacement-challenger-preregistration-isolation.md",
                "docs/implementation-status-v0.62.0.md",
            ),
        )

    def test_collector_uses_only_fixed_read_only_boundaries(self):
        repository = supersession_cli._repository_root()
        plan_bytes = (
            repository
            / "artifacts/challenger-replacement/"
            "challenger-replacement-plan-v0.62.0.json"
        ).read_bytes()
        git_stdout = (
            b"b33c0cf58a954f548f76792f0b7cf989dcf0900c\n",
            b"tag\n",
            b"e0a9b3eb6a3f385ea259722e6613df8708e8fe5a\n",
            b"a142927d96c4e6d52df22f79e929e679a219e82e\n",
            b"tag\n",
            b"df91e19240df14839125608422489adf3b902e76\n",
            b"c" * 40 + b"\n",
            b"",
            b"",
            b"",
            plan_bytes,
            b"e0a9b3eb6a3f385ea259722e6613df8708e8fe5a\n",
        )
        launch_argv = (
            "/bin/launchctl",
            "print",
            "gui/501/local.crypto-quant.challenger-replacement-v1",
        )
        calls = []

        def run(argv):
            calls.append(tuple(argv))
            if tuple(argv) == launch_argv:
                return self._completed(
                    argv,
                    returncode=113,
                    stderr=(
                        b'Bad request.\nCould not find service "'
                        b'local.crypto-quant.challenger-replacement-v1" '
                        b'in domain for user gui: 501\n'
                    ),
                )
            index = supersession_cli._git_argv(repository).index(tuple(argv))
            return self._completed(argv, stdout=git_stdout[index])

        with mock.patch.object(supersession_cli.os, "geteuid", return_value=501), mock.patch.object(
            supersession_cli, "_require_absent"
        ) as absent_call, mock.patch.object(
            supersession_cli, "_validate_reviewed_repo_root"
        ) as validate_root, mock.patch.object(
            supersession_cli, "_run", side_effect=run
        ):
            evidence = supersession_cli._collect_machine_evidence()

        self.assertEqual(absent_call.call_count, 2)
        validate_root.assert_called_once_with(repository)
        self.assertEqual(calls, [launch_argv, *supersession_cli._git_argv(repository)])
        self.assertEqual(
            evidence["observation"],
            "NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION",
        )
        self.assertEqual(evidence["current_observations"]["canonical_event_count"], 0)
        self.assertEqual(evidence["collector_actions"]["state_write_count"], 0)
        self.assertEqual(
            evidence["git_history"]["candidate_status_porcelain_base64"], ""
        )

    def test_wrong_uid_fails_before_launchctl(self):
        with mock.patch.object(supersession_cli.os, "geteuid", return_value=502), mock.patch.object(
            supersession_cli, "_run"
        ) as run:
            with self.assertRaisesRegex(
                supersession_cli.SupersessionCommandError, "UID_INVALID"
            ):
                supersession_cli._collect_machine_evidence()
        run.assert_not_called()

    def test_absence_boundary_uses_lstat_and_rejects_any_present_object(self):
        path = Path("/fixed/absent")
        with mock.patch.object(
            supersession_cli.os, "lstat", side_effect=FileNotFoundError
        ) as lstat_call:
            self.assertIsNone(supersession_cli._require_absent(path, "PRESENT"))
        lstat_call.assert_called_once_with(path)
        with mock.patch.object(
            supersession_cli.os, "lstat", return_value=mock.Mock()
        ):
            with self.assertRaisesRegex(
                supersession_cli.SupersessionCommandError, "PRESENT"
            ):
                supersession_cli._require_absent(path, "PRESENT")

    def test_processes_receive_no_inherited_git_or_locale_environment(self):
        completed = self._completed(("/usr/bin/git",), stdout=b"ok\n")
        with mock.patch.object(
            supersession_cli.subprocess, "run", return_value=completed
        ) as run:
            self.assertIs(
                supersession_cli._run(("/usr/bin/git", "version")), completed
            )
        self.assertEqual(
            run.call_args.kwargs["env"], supersession_cli._PROCESS_ENV
        )
        self.assertNotIn("GIT_DIR", run.call_args.kwargs["env"])
        self.assertNotIn("GIT_WORK_TREE", run.call_args.kwargs["env"])

    def test_later_ceremony_rejects_head_changed_since_machine_evidence(self):
        with tempfile.TemporaryDirectory(dir=_test_temp_root()) as temporary:
            root = Path(temporary)
            machine_path = root / supersession_cli._MACHINE_RELATIVE
            machine_path.parent.mkdir(parents=True)
            _canonical_file(machine_path, _machine_evidence())
            results = [self._completed(()) for unused in range(7)]
            results[6] = self._completed((), stdout=b"2" * 40 + b"\n")
            with self.assertRaisesRegex(
                supersession_cli.SupersessionCommandError, "HEAD_CHANGED"
            ):
                supersession_cli._require_original_candidate_head(root, results)

    def test_gitdir_marker_must_reciprocally_bind_reviewed_root(self):
        with tempfile.TemporaryDirectory(dir=_test_temp_root()) as temporary:
            base = Path(temporary)
            reviewed = base / "reviewed"
            other = base / "other"
            metadata = base / "metadata"
            reviewed.mkdir(mode=0o755)
            other.mkdir(mode=0o755)
            metadata.mkdir(mode=0o755)
            marker = reviewed / ".git"
            marker.write_text("gitdir: " + str(metadata) + "\n")
            marker.chmod(0o644)
            reciprocal = metadata / "gitdir"
            reciprocal.write_text(str(other / ".git") + "\n")
            reciprocal.chmod(0o644)
            with self.assertRaisesRegex(
                supersession_cli.SupersessionCommandError,
                "REPOSITORY_INVALID",
            ):
                supersession_cli._validate_reviewed_repo_root(reviewed)

            reciprocal.write_text(str(reviewed / ".git") + "\n")
            self.assertIsNone(
                supersession_cli._validate_reviewed_repo_root(reviewed)
            )

    def test_module_symlink_ancestry_cannot_be_resolved_away(self):
        with tempfile.TemporaryDirectory(dir=_test_temp_root()) as temporary:
            root = Path(temporary)
            target = root / "target.py"
            target.write_text("# fixture\n")
            linked = root / "linked.py"
            linked.symlink_to(target)
            with mock.patch.object(
                supersession_cli, "__file__", str(linked)
            ):
                with self.assertRaisesRegex(
                    supersession_cli.SupersessionCommandError,
                    "REPOSITORY_INVALID",
                ):
                    supersession_cli._repository_root()

    def test_cli_has_no_mutating_or_network_process_commands(self):
        source = Path(supersession_cli.__file__).read_text()
        for forbidden in (
            "mkdir(",
            "chmod(",
            '"kickstart"',
            '"bootstrap"',
            "requests.",
            "urllib.",
        ):
            self.assertNotIn(forbidden, source)

    def test_owner_ceremony_displays_exact_hashes_and_requires_exact_ack(self):
        with tempfile.TemporaryDirectory(dir=_test_temp_root()) as temporary:
            root = Path(temporary)
            artifact_root = root / "artifacts" / "challenger-replacement"
            artifact_root.mkdir(parents=True)
            plan_path = artifact_root / "challenger-replacement-plan-v0.64.0.json"
            machine_path = artifact_root / (
                "challenger-replacement-supersession-machine-evidence-v0.64.0.json"
            )
            _canonical_file(plan_path, build_challenger_replacement_plan_v2())
            _canonical_file(machine_path, _machine_evidence())
            precondition = _ceremony_precondition(
                "C1_EVIDENCE_ONLY",
                (
                    "?? artifacts/challenger-replacement/"
                    "challenger-replacement-supersession-machine-evidence-v0.64.0.json",
                ),
                [
                    _final_snapshot(
                        machine_path,
                        "artifacts/challenger-replacement/"
                        "challenger-replacement-supersession-machine-evidence-v0.64.0.json",
                    )
                ],
            )
            output = io.StringIO()
            output.isatty = lambda: True
            rejected_output = io.StringIO()
            rejected_output.isatty = lambda: True
            with mock.patch.object(
                supersession_cli, "_repository_root", return_value=root
            ), mock.patch.object(
                supersession_cli,
                "_capture_ceremony_precondition",
                return_value=(precondition, ()),
            ), mock.patch.object(
                supersession_cli, "_timestamp", return_value="2026-08-10T00:05:00.000Z"
            ), mock.patch.object(
                supersession_cli.sys,
                "stdin",
                mock.Mock(isatty=mock.Mock(return_value=True)),
            ), mock.patch("builtins.input", return_value=supersession_cli._ACKNOWLEDGEMENT), mock.patch.object(
                supersession_cli,
                "publish_challenger_replacement_owner_attestation_bytes",
            ) as publish, redirect_stdout(output):
                self.assertEqual(supersession_cli._attestation_command(), 0)
            published = publish.call_args.args[0]
            attestation = json.loads(published)
            self.assertEqual(attestation["declaration"], ACCOUNTABLE_OWNER_DECLARATION)
            self.assertIn(
                "declaration_sha256="
                + hashlib.sha256(ACCOUNTABLE_OWNER_DECLARATION.encode()).hexdigest(),
                output.getvalue(),
            )
            self.assertRegex(output.getvalue(), r"binding_sha256=[0-9a-f]{64}")

            with mock.patch.object(
                supersession_cli, "_repository_root", return_value=root
            ), mock.patch.object(
                supersession_cli,
                "_capture_ceremony_precondition",
                return_value=(precondition, ()),
            ), mock.patch.object(
                supersession_cli, "_timestamp", return_value="2026-08-10T00:05:00.000Z"
            ), mock.patch.object(
                supersession_cli.sys,
                "stdin",
                mock.Mock(isatty=mock.Mock(return_value=True)),
            ), mock.patch("builtins.input", return_value="no"), mock.patch.object(
                supersession_cli,
                "publish_challenger_replacement_owner_attestation_bytes",
            ) as rejected_publish, redirect_stdout(rejected_output):
                with self.assertRaisesRegex(
                    supersession_cli.SupersessionCommandError,
                    "ACKNOWLEDGEMENT_REQUIRED",
                ):
                    supersession_cli._attestation_command()
            rejected_publish.assert_not_called()

            with mock.patch.object(
                supersession_cli, "_repository_root", return_value=root
            ), mock.patch.object(
                supersession_cli,
                "_capture_ceremony_precondition",
                return_value=(precondition, ()),
            ), mock.patch.object(
                supersession_cli, "_timestamp", return_value="2026-08-10T00:05:00.000Z"
            ), mock.patch.object(
                supersession_cli.sys,
                "stdin",
                mock.Mock(isatty=mock.Mock(return_value=True)),
            ), mock.patch("builtins.input", return_value=supersession_cli._ACKNOWLEDGEMENT), mock.patch.object(
                supersession_cli,
                "publish_challenger_replacement_owner_attestation_bytes",
            ) as hidden_publish, redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(
                    supersession_cli.SupersessionCommandError,
                    "INTERACTIVE_TTY_REQUIRED",
                ):
                    supersession_cli._attestation_command()
            hidden_publish.assert_not_called()

            changed_precondition = copy.deepcopy(precondition)
            changed_precondition["allowlisted_finals"][0]["inode_decimal"] = str(
                int(changed_precondition["allowlisted_finals"][0]["inode_decimal"])
                + 1
            )
            changed_output = io.StringIO()
            changed_output.isatty = lambda: True
            with mock.patch.object(
                supersession_cli, "_repository_root", return_value=root
            ), mock.patch.object(
                supersession_cli,
                "_capture_ceremony_precondition",
                side_effect=[(precondition, ()), (changed_precondition, ())],
            ), mock.patch.object(
                supersession_cli, "_timestamp", return_value="2026-08-10T00:05:00.000Z"
            ), mock.patch.object(
                supersession_cli.sys,
                "stdin",
                mock.Mock(isatty=mock.Mock(return_value=True)),
            ), mock.patch("builtins.input", return_value=supersession_cli._ACKNOWLEDGEMENT), mock.patch.object(
                supersession_cli,
                "publish_challenger_replacement_owner_attestation_bytes",
            ) as changed_publish, redirect_stdout(changed_output):
                with self.assertRaisesRegex(
                    supersession_cli.SupersessionCommandError,
                    "PRECONDITION_CHANGED",
                ):
                    supersession_cli._attestation_command()
            changed_publish.assert_not_called()

    @unittest.skipUnless(
        os.geteuid() == 501,
        "FIXED_OWNER_UID_501_SECURITY_BOUNDARY_REQUIRES_DEDICATED_CI_STEP",
    )
    def test_temporary_git_ceremony_transitions_c0_through_c4_exactly(self):
        with tempfile.TemporaryDirectory(dir=_test_temp_root()) as temporary:
            clone = Path(temporary) / "reviewed-clone"
            head = subprocess.run(
                ["/usr/bin/git", "-C", str(ROOT), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
            ).stdout.decode("ascii").strip()
            subprocess.run(
                [
                    "/usr/bin/git",
                    "clone",
                    "--no-local",
                    "--no-hardlinks",
                    "--no-checkout",
                    str(ROOT),
                    str(clone),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["/usr/bin/git", "-C", str(clone), "checkout", "--detach", head],
                check=True,
                capture_output=True,
            )
            artifact_root = clone / "artifacts" / "challenger-replacement"
            plan_path = artifact_root / "challenger-replacement-plan-v0.64.0.json"
            _canonical_file(plan_path, build_challenger_replacement_plan_v2())
            subprocess.run(
                ["/usr/bin/git", "-C", str(clone), "add", str(plan_path)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(clone),
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@invalid",
                    "commit",
                    "-m",
                    "fixture: freeze plan",
                ],
                check=True,
                capture_output=True,
            )
            self.assertEqual(
                subprocess.run(
                    ["/usr/bin/git", "-C", str(clone), "status", "--porcelain=v1"],
                    check=True,
                    capture_output=True,
                ).stdout,
                b"",
            )

            real_run = supersession_cli._run

            def run_with_absent_service(argv):
                if tuple(argv) == (
                    "/bin/launchctl",
                    "print",
                    "gui/501/local.crypto-quant.challenger-replacement-v1",
                ):
                    return self._completed(
                        argv,
                        returncode=113,
                        stderr=(
                            b'Bad request.\nCould not find service "'
                            b'local.crypto-quant.challenger-replacement-v1" '
                            b'in domain for user gui: 501\n'
                        ),
                    )
                return real_run(argv)

            tty_stdout = io.StringIO()
            tty_stdout.isatty = lambda: True
            tty_stderr = io.StringIO()
            tty_stderr.isatty = lambda: True
            with mock.patch.object(
                supersession_cli, "_repository_root", return_value=clone
            ), mock.patch.object(
                publish_module, "_artifact_parent", return_value=artifact_root
            ), mock.patch.object(
                supersession_cli, "_run", side_effect=run_with_absent_service
            ), mock.patch.object(
                supersession_cli, "_require_absent"
            ), mock.patch.object(
                supersession_cli.sys, "stdin", mock.Mock(isatty=mock.Mock(return_value=True))
            ), mock.patch.object(
                supersession_cli.sys, "stdout", tty_stdout
            ), mock.patch.object(
                publish_module.sys, "stderr", tty_stderr
            ), mock.patch(
                "builtins.input", return_value=supersession_cli._ACKNOWLEDGEMENT
            ):
                unexpected = clone / "unexpected.txt"
                unexpected.write_text("unexpected")
                with self.assertRaisesRegex(
                    supersession_cli.SupersessionCommandError,
                    "CANDIDATE_STATE_INVALID",
                ):
                    supersession_cli._collect_command()
                unexpected.unlink()
                self.assertEqual(supersession_cli._collect_command(), 0)
                self.assertEqual(supersession_cli._attestation_command(), 0)
                self.assertEqual(supersession_cli._assemble_command(), 0)

            expected_c3 = tuple(
                sorted(
                    (
                        "?? artifacts/challenger-replacement/"
                        "challenger-replacement-owner-attestation-v0.64.0.json",
                        "?? artifacts/challenger-replacement/"
                        "challenger-replacement-plan-supersession-v0.64.0.json",
                        "?? artifacts/challenger-replacement/"
                        "challenger-replacement-supersession-machine-evidence-v0.64.0.json",
                    )
                )
            )
            c3 = tuple(
                subprocess.run(
                    ["/usr/bin/git", "-C", str(clone), "status", "--porcelain=v1"],
                    check=True,
                    capture_output=True,
                ).stdout.decode("utf-8").splitlines()
            )
            self.assertEqual(c3, expected_c3)
            formal_paths = [
                clone / line[3:] for line in expected_c3
            ]
            subprocess.run(
                ["/usr/bin/git", "-C", str(clone), "add", *map(str, formal_paths)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(clone),
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@invalid",
                    "commit",
                    "-m",
                    "fixture: record supersession",
                ],
                check=True,
                capture_output=True,
            )
            self.assertEqual(
                subprocess.run(
                    ["/usr/bin/git", "-C", str(clone), "status", "--porcelain=v1"],
                    check=True,
                    capture_output=True,
                ).stdout,
                b"",
            )
