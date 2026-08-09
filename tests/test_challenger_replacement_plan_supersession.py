import base64
import copy
import hashlib
import json
import os
import tempfile
import unittest
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
        record = build_challenger_replacement_plan_supersession_record(
            v2_plan_path=self.v2_path,
            machine_evidence_path=self.machine_path,
            owner_attestation_path=self.attestation_path,
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
