import base64
import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import business_hash, canonical_json, stable_id
from crypto_quant.challenger_replacement_plan_v3 import (
    build_challenger_replacement_plan_v3,
)
from crypto_quant.challenger_replacement_plan_v3_supersession import (
    ACCOUNTABLE_OWNER_DECLARATION_V3,
    REAL_V3_EVIDENCE_QUALIFICATION,
    ChallengerReplacementPlanV3SupersessionError,
    build_challenger_replacement_v3_supersession_record,
    load_challenger_replacement_v3_machine_evidence,
    load_challenger_replacement_v3_owner_attestation,
    load_challenger_replacement_v3_supersession_record,
    v3_supersession_artifact_hash,
)


ROOT = Path(__file__).resolve().parents[1]
EMPTY_SHA = hashlib.sha256(b"").hexdigest()
PREVIOUS_PLAN = {
    "release_tag": "v0.64.0",
    "path": (
        "artifacts/challenger-replacement/"
        "challenger-replacement-plan-v0.64.0.json"
    ),
    "file_sha256": (
        "5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f"
    ),
    "plan_id": (
        "challenger_replacement_plan_"
        "65d85d60a534a917f45a1ffa5fc9d3f74d6d24995b900d31b8c73cd26f0bd97b"
    ),
    "plan_hash": (
        "c9a1e5f74c52fbf23be5a1d27fd23c25f3601ed58133178fc25480391ab65705"
    ),
}
SCHEMAS = (
    "challenger-replacement-v3-supersession-machine-evidence-v1.schema.json",
    "challenger-replacement-v3-owner-attestation-v1.schema.json",
    "challenger-replacement-plan-v3-supersession-v1.schema.json",
)
DECLARATION = (
    "I attest that before the bound machine-evidence collection time the "
    "replacement-v3 service had never been installed or started, no "
    "replacement start receipt or canonical production opportunity event "
    "had been created, and no real order had been submitted by this "
    "replacement path. I understand this is an accountable governance "
    "statement, not a fact that code or an OS snapshot can prove, and that "
    "supersession is forbidden after the first v3 start receipt or canonical "
    "production opportunity event."
)


def _file_sha(data):
    return hashlib.sha256(data).hexdigest()


def _plan_binding():
    plan = build_challenger_replacement_plan_v3()
    body = canonical_json(plan).encode("utf-8") + b"\n"
    return {
        "path": (
            "artifacts/challenger-replacement/"
            "challenger-replacement-plan-v0.69.0.json"
        ),
        "file_sha256": _file_sha(body),
        "plan_id": plan["plan_id"],
        "plan_hash": plan["plan_hash"],
    }


def _transcript(name, argv, stdout=b""):
    return {
        "name": name,
        "argv": list(argv),
        "exit_code": 0,
        "stdout_base64": base64.b64encode(stdout).decode("ascii"),
        "stdout_sha256": _file_sha(stdout),
        "stderr_base64": "",
        "stderr_sha256": EMPTY_SHA,
    }


def _identify(value, *, id_field, hash_field, prefix, identity):
    result = copy.deepcopy(value)
    result[id_field] = stable_id(prefix, identity)
    result[hash_field] = v3_supersession_artifact_hash(result, hash_field)
    return result


def _machine():
    plan = _plan_binding()
    transcripts = [
        _transcript(
            "git_v064_peeled",
            ["/usr/bin/git", "-C", str(ROOT), "rev-parse", "v0.64.0^{}"],
            b"c4f6ea213077850a8fc8b9bd3392f1a4bac466f9\n",
        ),
        _transcript(
            "git_v068_peeled",
            ["/usr/bin/git", "-C", str(ROOT), "rev-parse", "v0.68.0^{}"],
            b"b65481cce9c8955f73da5b78ef2bd3c981f3be3c\n",
        ),
        _transcript(
            "launchctl_service",
            [
                "/bin/launchctl",
                "print",
                "gui/501/local.crypto-quant.challenger-replacement-v1",
            ],
            b"NOT_LOADED\n",
        ),
    ]
    value = {
        "$schema": (
            "./challenger-replacement-v3-supersession-"
            "machine-evidence-v1.schema.json"
        ),
        "schema_version": "1.0.0",
        "evidence_id": "challenger_replacement_v3_machine_evidence_" + "0" * 64,
        "evidence_hash": "0" * 64,
        "evidence_qualification": REAL_V3_EVIDENCE_QUALIFICATION,
        "collected_at": "2026-08-23T12:00:00.000Z",
        "repository": {
            "root": str(ROOT),
            "head": "a" * 40,
            "worktree_state": "CLEAN_PRE_ARTIFACT_HEAD",
        },
        "release_history": {
            "previous_plan": copy.deepcopy(PREVIOUS_PLAN),
            "v068_release_tag": "v0.68.0",
            "v068_peeled_commit": (
                "b65481cce9c8955f73da5b78ef2bd3c981f3be3c"
            ),
            "v3_plan": plan,
        },
        "current_observation": {
            "observation": "NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION",
            "runtime_root": "ABSENT",
            "target_plist": "ABSENT",
            "service": "NOT_LOADED",
            "start_receipt_count": 0,
            "canonical_event_count": 0,
        },
        "transcripts": transcripts,
        "collector_authority": {
            "collector_state_write_count": 0,
            "market_request_count": 0,
            "account_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "production_root_write_count": 0,
        },
        "warnings": [
            "CURRENT_OBSERVATION_DOES_NOT_PROVE_HISTORICAL_NONEXISTENCE",
            "OWNER_ATTESTATION_REQUIRED_FOR_HISTORICAL_PRE_START_CLAIM",
        ],
    }
    history = {
        "repository": value["repository"],
        "release_history": value["release_history"],
        "transcript_hashes": [item["stdout_sha256"] for item in transcripts],
    }
    identity = {
        "collected_at": value["collected_at"],
        "v3_plan": plan,
        "git_history_evidence_hash": business_hash(history),
        "observation": value["current_observation"]["observation"],
    }
    value["git_history_evidence_hash"] = identity["git_history_evidence_hash"]
    return _identify(
        value,
        id_field="evidence_id",
        hash_field="evidence_hash",
        prefix="challenger_replacement_v3_machine_evidence",
        identity=identity,
    )


def _machine_binding(machine):
    body = canonical_json(machine).encode("utf-8") + b"\n"
    return {
        "path": (
            "artifacts/challenger-replacement/"
            "challenger-replacement-v3-supersession-"
            "machine-evidence-v0.69.0.json"
        ),
        "file_sha256": _file_sha(body),
        "evidence_id": machine["evidence_id"],
        "evidence_hash": machine["evidence_hash"],
        "git_history_evidence_hash": machine["git_history_evidence_hash"],
        "collected_at": machine["collected_at"],
    }


def _attestation(machine):
    plan = _plan_binding()
    value = {
        "$schema": "./challenger-replacement-v3-owner-attestation-v1.schema.json",
        "schema_version": "1.0.0",
        "attestation_id": (
            "challenger_replacement_v3_owner_attestation_" + "0" * 64
        ),
        "attestation_hash": "0" * 64,
        "evidence_qualification": REAL_V3_EVIDENCE_QUALIFICATION,
        "attestation_type": "ACCOUNTABLE_OWNER_PRE_START_V3_ATTESTATION",
        "signed_at": "2026-08-23T12:05:00.000Z",
        "signer": {
            "github_login": "cjl308868584-lang",
            "os_username": "chenm4",
            "uid": 501,
        },
        "declaration": DECLARATION,
        "declaration_sha256": _file_sha(DECLARATION.encode("utf-8")),
        "owner_acknowledgement": (
            "I_SIGN_AND_ACCEPT_ACCOUNTABILITY_FOR_THE_EXACT_V3_DECLARATION"
        ),
        "previous_plan": copy.deepcopy(PREVIOUS_PLAN),
        "v068_foundation": copy.deepcopy(
            build_challenger_replacement_plan_v3()["foundation"]
        ),
        "v3_plan": plan,
        "machine_evidence": _machine_binding(machine),
    }
    identity = {
        "signed_at": value["signed_at"],
        "signer": value["signer"],
        "declaration_sha256": value["declaration_sha256"],
        "previous_plan": value["previous_plan"],
        "v3_plan": value["v3_plan"],
        "machine_evidence": value["machine_evidence"],
    }
    return _identify(
        value,
        id_field="attestation_id",
        hash_field="attestation_hash",
        prefix="challenger_replacement_v3_owner_attestation",
        identity=identity,
    )


def _write(path, value):
    path.write_bytes(canonical_json(value).encode("utf-8") + b"\n")
    path.chmod(0o644)
    return path


class V3SupersessionSchemaTests(unittest.TestCase):
    def test_schema_mirrors_are_valid_and_every_object_is_closed(self):
        for name in SCHEMAS:
            with self.subTest(schema=name):
                config = (ROOT / "config" / name).read_bytes()
                package = (
                    ROOT / "src" / "crypto_quant" / "schemas" / name
                ).read_bytes()
                self.assertEqual(config, package)
                schema = json.loads(config)
                Draft202012Validator.check_schema(schema)
                pending = [schema]
                while pending:
                    value = pending.pop()
                    if isinstance(value, dict):
                        if value.get("type") == "object":
                            self.assertIs(value.get("additionalProperties"), False)
                        pending.extend(value.values())
                    elif isinstance(value, list):
                        pending.extend(value)


class V3SupersessionContractTests(unittest.TestCase):
    def test_machine_loader_binds_current_observation_transcripts_and_zero_authority(self):
        machine = _machine()
        with tempfile.TemporaryDirectory() as directory:
            path = _write(Path(directory) / "machine.json", machine)
            self.assertEqual(
                load_challenger_replacement_v3_machine_evidence(path), machine
            )

        mutations = {
            "runtime_present": lambda value: value["current_observation"].__setitem__(
                "runtime_root", "PRESENT"
            ),
            "event_present": lambda value: value["current_observation"].__setitem__(
                "canonical_event_count", 1
            ),
            "collector_write": lambda value: value["collector_authority"].__setitem__(
                "collector_state_write_count", 1
            ),
            "order": lambda value: value["collector_authority"].__setitem__(
                "order_submission_count", 1
            ),
            "transcript": lambda value: value["transcripts"][0].__setitem__(
                "stdout_sha256", "f" * 64
            ),
            "qualification": lambda value: value.__setitem__(
                "evidence_qualification",
                "TEST_FIXTURE_ONLY_NOT_SUPERSESSION_EVIDENCE",
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                changed = copy.deepcopy(machine)
                mutate(changed)
                changed["evidence_hash"] = v3_supersession_artifact_hash(
                    changed, "evidence_hash"
                )
                path = _write(Path(directory) / "machine.json", changed)
                with self.assertRaises(
                    ChallengerReplacementPlanV3SupersessionError
                ):
                    load_challenger_replacement_v3_machine_evidence(path)

    def test_attestation_binds_exact_declaration_owner_plan_and_machine(self):
        self.assertEqual(ACCOUNTABLE_OWNER_DECLARATION_V3, DECLARATION)
        machine = _machine()
        attestation = _attestation(machine)
        with tempfile.TemporaryDirectory() as directory:
            path = _write(Path(directory) / "attestation.json", attestation)
            self.assertEqual(
                load_challenger_replacement_v3_owner_attestation(path),
                attestation,
            )

        for name, mutate in {
            "declaration": lambda value: value.__setitem__(
                "declaration", value["declaration"] + " changed"
            ),
            "uid": lambda value: value["signer"].__setitem__("uid", 502),
            "plan": lambda value: value["v3_plan"].__setitem__(
                "plan_hash", "f" * 64
            ),
            "machine": lambda value: value["machine_evidence"].__setitem__(
                "evidence_hash", "f" * 64
            ),
        }.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                changed = copy.deepcopy(attestation)
                mutate(changed)
                changed["attestation_hash"] = v3_supersession_artifact_hash(
                    changed, "attestation_hash"
                )
                path = _write(Path(directory) / "attestation.json", changed)
                with self.assertRaises(
                    ChallengerReplacementPlanV3SupersessionError
                ):
                    load_challenger_replacement_v3_owner_attestation(path)

    def test_record_builder_and_loader_bind_all_inputs_and_semantic_diff(self):
        machine = _machine()
        attestation = _attestation(machine)
        record = build_challenger_replacement_v3_supersession_record(
            build_challenger_replacement_plan_v3(), machine, attestation
        )
        self.assertEqual(
            record["reason"],
            "SUPERSEDED_PRE_START_RESEARCH_AND_OPERATIONAL_POLICY_CHANGE",
        )
        self.assertEqual(
            record["semantic_diff_hash"],
            business_hash(
                build_challenger_replacement_plan_v3()["supersession"][
                    "semantic_changes"
                ]
            ),
        )
        self.assertEqual(record["status"], "PLAN_V3_SUPERSESSION_RECORDED_PRE_START")
        with tempfile.TemporaryDirectory() as directory:
            path = _write(Path(directory) / "record.json", record)
            self.assertEqual(
                load_challenger_replacement_v3_supersession_record(path), record
            )
            changed = copy.deepcopy(record)
            changed["machine_evidence"]["evidence_hash"] = "f" * 64
            changed["record_hash"] = v3_supersession_artifact_hash(
                changed, "record_hash"
            )
            invalid = _write(Path(directory) / "invalid.json", changed)
            with self.assertRaises(ChallengerReplacementPlanV3SupersessionError):
                load_challenger_replacement_v3_supersession_record(invalid)

    def test_loaders_reject_noncanonical_relative_writable_and_hardlinked_files(self):
        machine = _machine()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pretty = root / "pretty.json"
            pretty.write_text(json.dumps(machine, indent=2))
            pretty.chmod(0o644)
            writable = _write(root / "writable.json", machine)
            writable.chmod(0o666)
            hard_source = _write(root / "hard-source.json", machine)
            hard = root / "hard.json"
            os.link(hard_source, hard)
            for path in (pretty, writable, hard):
                with self.subTest(path=path.name):
                    with self.assertRaises(
                        ChallengerReplacementPlanV3SupersessionError
                    ):
                        load_challenger_replacement_v3_machine_evidence(path)
        with self.assertRaises(ChallengerReplacementPlanV3SupersessionError):
            load_challenger_replacement_v3_machine_evidence(Path("relative.json"))

    def test_structural_validation_does_not_claim_to_prove_provenance_or_truth(self):
        machine = _machine()
        attestation = _attestation(machine)
        self.assertEqual(
            machine["current_observation"]["observation"],
            "NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION",
        )
        self.assertIn(
            "not a fact that code or an OS snapshot can prove",
            attestation["declaration"],
        )
