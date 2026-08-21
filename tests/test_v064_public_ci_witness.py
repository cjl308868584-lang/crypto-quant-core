import copy
import errno
import hashlib
import inspect
import io
import json
import os
import subprocess
import sys
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, ValidationError

from crypto_quant.canonical import canonical_json
from crypto_quant.evidence import artifact_self_hash
from crypto_quant import v064_public_ci_witness
from crypto_quant.v064_public_ci_bundle import stage_v064_public_ci_bundle
from crypto_quant.v064_public_ci_witness import (
    V064PublicCiWitnessError,
    derive_v064_public_ci_witness,
    load_v064_public_ci_witness,
    verify_v064_public_source_unchanged,
)
from crypto_quant import v064_public_ci_witness_cli


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "config" / "v064-public-ci-witness-v1.schema.json"
PACKAGE_SCHEMA = (
    ROOT / "src" / "crypto_quant" / "schemas" / "v064-public-ci-witness-v1.schema.json"
)
PREDECESSOR_FAILED_PUBLIC_WITNESS = {
    "repository": "cjl308868584-lang/crypto-quant-v064-public-ci",
    "private_candidate_f": "1967f79ff8d013bf149bf36e2cdcb6a81ed200ff",
    "private_tree_f": "5389cc01164ce6dd5955df1d014e974f4bf1a104",
    "public_commit": "0429837e5de8052e9e8216ed08ba9c7aa9c905b3",
    "public_tree": "4ebb723e73dc9eb43b7273febd96af3ef87ef951",
    "manifest_sha256": "c238c904495b167e436b2c32e822d8fa55285e42eaaad8e095805e73570e3fd7",
    "file_set_sha256": "2d7ed3d4b3380b43e50f16f04113eae46360397e46aeba2edd639ce46a7f76c7",
    "workflow_blob_oid": "d2c0104eafb8e1aa5ea68a60f716921f2668ce42",
    "run_id": 31850146784,
    "run_attempt": 1,
    "event": "push",
    "head_branch": "main",
    "status": "completed",
    "conclusion": "failure",
    "jobs": [
        {
            "python_version": "3.9",
            "job_id": 94924270273,
            "conclusion": "failure",
            "test_step_conclusion": "skipped",
        },
        {
            "python_version": "3.12",
            "job_id": 94924270340,
            "conclusion": "failure",
            "test_step_conclusion": "skipped",
        },
    ],
    "reason_code": "PUBLIC_SENSITIVE_BYTES_INVALID",
    "run_json_sha256": "f442ae366539fc4a244977fdafb2cd5de383b4248483381d8d79b751ea6a6099",
    "jobs_json_sha256": "9a69273c07548e97dbc2f43883eea4b5935f84256b7ad95b2874ca498bc67923",
    "run_log_sha256": "e47462120131eadb3161a40ffe679f4f74889103d7b3a13bb563df705f9ef32c",
    "transcript_summary_sha256": "cd2072e246698bec6d8767d37da4a3dca82d09fc38466a8009aea9690a0c9790",
}
R2_FAILURE_RECORD_PATH = (
    "artifacts/v064-public-ci-r2-failure/v064-public-ci-r2-failure-record-v1.json"
)
R2_FAILURE_RECORD_SHA256 = (
    "857150ae490e54d5b6bdaa816efb96cf3f24a9778220f61973312426644dd264"
)
PREDECESSOR_FAILED_PUBLIC_WITNESS_R2 = {
    "failure_record_path": R2_FAILURE_RECORD_PATH,
    "failure_record_sha256": R2_FAILURE_RECORD_SHA256,
    **json.loads((ROOT / R2_FAILURE_RECORD_PATH).read_text(encoding="utf-8")),
}
PREDECESSOR_FAILED_PUBLIC_WITNESSES = [
    PREDECESSOR_FAILED_PUBLIC_WITNESS,
    PREDECESSOR_FAILED_PUBLIC_WITNESS_R2,
]


def _raw(path, fill):
    return {"path": path, "size": 123, "sha256": fill * 64}


def _job(python_version, job_id):
    return {
        "python_version": python_version,
        "setup_python_version": python_version + ".25",
        "fixed_owner_python_version": python_version + ".25",
        "job_id": job_id,
        "name": "linux-python-" + python_version,
        "status": "completed",
        "conclusion": "success",
        "runner_os": "Linux",
        "started_at": "2026-08-13T01:00:00Z",
        "completed_at": "2026-08-13T01:05:00Z",
        "steps": [
            {
                "number": 1,
                "name": "Verify exact bundle",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "number": 2,
                "name": "Run exact Linux boundary",
                "status": "completed",
                "conclusion": "success",
            },
        ],
    }


def valid_witness():
    return {
        "$schema": "./v064-public-ci-witness-v1.schema.json",
        "schema_version": "1.2.0",
        "witness_id": "v064_public_ci_witness_" + "1" * 64,
        "witness_hash": "2" * 64,
        "status": "PUBLIC_LINUX_PORTABILITY_WITNESS_COMPLETED",
        "predecessor_failed_public_witnesses": copy.deepcopy(
            PREDECESSOR_FAILED_PUBLIC_WITNESSES
        ),
        "private_source": {
            "repository": "cjl308868584-lang/crypto-quant-core",
            "candidate_commit": "3" * 40,
            "candidate_tree": "4" * 40,
            "object_format": "sha1",
            "historical_billing_blocked_private_pr": {
                "number": 32,
                "run_id": 31436609135,
                "status": "PRIVATE_PR_CI_NOT_EXECUTED_BILLING_BLOCKED",
            },
        },
        "public_source": {
            "repository": "cjl308868584-lang/crypto-quant-v064-public-ci-r3",
            "commit": "5" * 40,
            "tree": "6" * 40,
            "branch": "main",
            "parent_count": 0,
        },
        "bundle": {
            "manifest_sha256": "7" * 64,
            "file_set_sha256": "8" * 64,
        },
        "workflow": {
            "path": ".github/workflows/ci.yml",
            "blob_oid": "9" * 40,
            "sha256": "a" * 64,
        },
        "run": {
            "run_id": 31400000000,
            "workflow_id": 7654321,
            "run_attempt": 1,
            "event": "push",
            "head_branch": "main",
            "head_sha": "5" * 40,
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-08-13T00:59:00Z",
            "updated_at": "2026-08-13T01:06:00Z",
        },
        "jobs": [_job("3.9", 111), _job("3.12", 222)],
        "raw_evidence": {
            "run_api": _raw(
                "artifacts/v064-public-ci-r3/v064-public-ci-r3-run-api-v1.json", "b"
            ),
            "jobs_api": _raw(
                "artifacts/v064-public-ci-r3/v064-public-ci-r3-jobs-api-v1.json", "c"
            ),
            "run_log": _raw(
                "artifacts/v064-public-ci-r3/v064-public-ci-r3-run-log-v1.txt", "d"
            ),
            "acquisition_transcript": _raw(
                "artifacts/v064-public-ci-r3/v064-public-ci-r3-acquisition-transcript-v1.json",
                "e",
            ),
        },
        "ancestry": {
            "witness_binds_private_source_f": True,
            "public_commit_is_parentless": True,
            "candidate_g_not_yet_bound": True,
        },
        "safety": {
            "production_activation": False,
            "credentials_present": False,
            "broker_allowed": False,
            "orders_allowed": False,
            "runtime_state_write_allowed": False,
        },
        "non_claims": [
            "NOT_FULL_PROJECT_CI",
            "NOT_PRIVATE_PR_CHECK",
            "NOT_STRATEGY_CORRECTNESS_EVIDENCE",
            "NOT_PROFITABILITY_OR_AI_ADVANTAGE_EVIDENCE",
            "NOT_PAPER_CANARY_OR_LIVE_TRADING_AUTHORIZATION",
        ],
    }


def _object_paths(value, path=()):
    if isinstance(value, dict):
        yield path
        for key, child in value.items():
            yield from _object_paths(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _object_paths(child, path + (index,))


def _at_path(value, path):
    for part in path:
        value = value[part]
    return value


class V064PublicCiWitnessSchemaTests(unittest.TestCase):
    def schema(self):
        return json.loads(CONFIG_SCHEMA.read_text(encoding="utf-8"))

    def test_config_and_package_schemas_are_exact_valid_mirrors(self):
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        schema = self.schema()
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(valid_witness())

    def test_witness_requires_exact_ordered_r1_r2_predecessors(self):
        schema = self.schema()
        validator = Draft202012Validator(schema)

        missing = copy.deepcopy(valid_witness())
        del missing["predecessor_failed_public_witnesses"]
        with self.assertRaises(ValidationError):
            validator.validate(missing)

        predecessor = PREDECESSOR_FAILED_PUBLIC_WITNESS
        scalar_replacements = {
            "repository": "cjl308868584-lang/wrong",
            "private_candidate_f": "0" * 40,
            "private_tree_f": "0" * 40,
            "public_commit": "0" * 40,
            "public_tree": "0" * 40,
            "manifest_sha256": "0" * 64,
            "file_set_sha256": "0" * 64,
            "workflow_blob_oid": "0" * 40,
            "run_id": predecessor["run_id"] + 1,
            "run_attempt": 2,
            "event": "workflow_dispatch",
            "head_branch": "wrong",
            "status": "queued",
            "conclusion": "success",
            "reason_code": "WRONG",
            "run_json_sha256": "0" * 64,
            "jobs_json_sha256": "0" * 64,
            "run_log_sha256": "0" * 64,
            "transcript_summary_sha256": "0" * 64,
        }
        for key, replacement in scalar_replacements.items():
            changed = copy.deepcopy(valid_witness())
            changed["predecessor_failed_public_witnesses"][0][key] = replacement
            with self.subTest(field=key), self.assertRaises(ValidationError):
                validator.validate(changed)

        for index, job in enumerate(predecessor["jobs"]):
            for key, original in job.items():
                changed = copy.deepcopy(valid_witness())
                replacement = original + 1 if isinstance(original, int) else "wrong"
                changed["predecessor_failed_public_witnesses"][0]["jobs"][index][key] = replacement
                with self.subTest(job=index, field=key), self.assertRaises(ValidationError):
                    validator.validate(changed)

        structural_mutations = []
        extra = copy.deepcopy(valid_witness())
        extra["predecessor_failed_public_witnesses"][0]["unexpected"] = True
        structural_mutations.append(extra)
        singular = copy.deepcopy(valid_witness())
        singular["predecessor_failed_public_witnesses"].pop()
        structural_mutations.append(singular)
        reordered = copy.deepcopy(valid_witness())
        reordered["predecessor_failed_public_witnesses"].reverse()
        structural_mutations.append(reordered)
        duplicate = copy.deepcopy(valid_witness())
        duplicate["predecessor_failed_public_witnesses"][1] = copy.deepcopy(
            duplicate["predecessor_failed_public_witnesses"][0]
        )
        structural_mutations.append(duplicate)
        unsafe = copy.deepcopy(valid_witness())
        unsafe["predecessor_failed_public_witnesses"][0]["run_id"] = 2**53
        structural_mutations.append(unsafe)
        long_oid = copy.deepcopy(valid_witness())
        long_oid["predecessor_failed_public_witnesses"][0]["public_commit"] = "f" * 64
        structural_mutations.append(long_oid)
        uppercase_hash = copy.deepcopy(valid_witness())
        uppercase_hash["predecessor_failed_public_witnesses"][0]["run_log_sha256"] = "A" * 64
        structural_mutations.append(uppercase_hash)
        for changed in structural_mutations:
            with self.assertRaises(ValidationError):
                validator.validate(changed)

        old_shape = copy.deepcopy(valid_witness())
        old_shape["predecessor_failed_public_witness"] = old_shape.pop(
            "predecessor_failed_public_witnesses"
        )[0]
        with self.assertRaises(ValidationError):
            validator.validate(old_shape)

        old_repository = copy.deepcopy(valid_witness())
        old_repository["public_source"]["repository"] = (
            "cjl308868584-lang/crypto-quant-v064-public-ci-r2"
        )
        with self.assertRaises(ValidationError):
            validator.validate(old_repository)

    def test_witness_requires_exact_successful_python_jobs(self):
        schema = self.schema()

        missing = copy.deepcopy(valid_witness())
        missing["jobs"].pop()
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(missing)

        duplicate = copy.deepcopy(valid_witness())
        duplicate["jobs"][1] = copy.deepcopy(duplicate["jobs"][0])
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(duplicate)

        failed = copy.deepcopy(valid_witness())
        failed["jobs"][0]["conclusion"] = "failure"
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(failed)

        empty_steps = copy.deepcopy(valid_witness())
        empty_steps["jobs"][0]["steps"] = []
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(empty_steps)

        unsafe_integer = copy.deepcopy(valid_witness())
        unsafe_integer["run"]["run_id"] = 2**53
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(unsafe_integer)

        dispatched = copy.deepcopy(valid_witness())
        dispatched["run"]["event"] = "workflow_dispatch"
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(dispatched)

        for field in ("setup_python_version", "fixed_owner_python_version"):
            mismatched = copy.deepcopy(valid_witness())
            mismatched["jobs"][0][field] = "3.12.14"
            with self.subTest(field=field), self.assertRaises(ValidationError):
                Draft202012Validator(schema).validate(mismatched)

    def test_witness_rejects_permissions_unknown_fields_and_candidate_g(self):
        schema = self.schema()

        permission = copy.deepcopy(valid_witness())
        permission["safety"]["broker_allowed"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(permission)

        candidate_g = copy.deepcopy(valid_witness())
        candidate_g["candidate_g"] = "f" * 40
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(candidate_g)

        invalid_raw_hash = copy.deepcopy(valid_witness())
        invalid_raw_hash["raw_evidence"]["run_log"]["sha256"] = "not-a-hash"
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(invalid_raw_hash)

        mismatched_object_format = copy.deepcopy(valid_witness())
        mismatched_object_format["private_source"]["candidate_tree"] = "4" * 64
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(mismatched_object_format)

        old_pr_claim = copy.deepcopy(valid_witness())
        old_pr_claim["private_source"]["private_pr"] = 32
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(old_pr_claim)

    def test_witness_rejects_mixed_git_object_formats(self):
        schema = self.schema()
        for path in (
            ("private_source", "candidate_commit"),
            ("private_source", "candidate_tree"),
            ("public_source", "commit"),
            ("public_source", "tree"),
            ("workflow", "blob_oid"),
            ("run", "head_sha"),
        ):
            changed = copy.deepcopy(valid_witness())
            container = _at_path(changed, path[:-1])
            container[path[-1]] = "f" * 64
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    Draft202012Validator(schema).validate(changed)

    def test_witness_rejects_unknown_fields_at_every_object_boundary(self):
        schema = self.schema()
        validator = Draft202012Validator(schema)
        original = valid_witness()
        for path in _object_paths(original):
            changed = copy.deepcopy(original)
            _at_path(changed, path)["unexpected"] = True
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    validator.validate(changed)


def _canonical(value):
    return canonical_json(value).encode("utf-8") + b"\n"


def _realistic_inputs():
    run = {
        "id": 31400000000,
        "workflow_id": 7654321,
        "run_attempt": 1,
        "event": "push",
        "head_branch": "main",
        "head_sha": "5" * 40,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-08-13T00:59:00Z",
        "updated_at": "2026-08-13T01:06:00Z",
        "path": ".github/workflows/ci.yml",
        "repository": "cjl308868584-lang/crypto-quant-v064-public-ci-r3",
    }
    jobs = {
        "total_count": 2,
        "jobs": [
            {
                "id": 111,
                "name": "portability (3.9)",
                "status": "completed",
                "conclusion": "success",
                "runner_name": "GitHub Actions 1",
                "labels": ["ubuntu-latest"],
                "started_at": "2026-08-13T01:00:00Z",
                "completed_at": "2026-08-13T01:05:00Z",
                "steps": [
                    {"number": 1, "name": "Set up job", "status": "completed", "conclusion": "success"},
                    {"number": 2, "name": "Verify closed bundle before repository imports", "status": "completed", "conclusion": "success"},
                    {"number": 3, "name": "Run fixed-owner public boundary", "status": "completed", "conclusion": "success"},
                ],
            },
            {
                "id": 222,
                "name": "portability (3.12)",
                "status": "completed",
                "conclusion": "success",
                "runner_name": "GitHub Actions 2",
                "labels": ["ubuntu-latest"],
                "started_at": "2026-08-13T01:00:00Z",
                "completed_at": "2026-08-13T01:05:00Z",
                "steps": [
                    {"number": 1, "name": "Set up job", "status": "completed", "conclusion": "success"},
                    {"number": 2, "name": "Verify closed bundle before repository imports", "status": "completed", "conclusion": "success"},
                    {"number": 3, "name": "Run fixed-owner public boundary", "status": "completed", "conclusion": "success"},
                ],
            },
        ],
    }
    markers = (
        "source_candidate_f=" + "3" * 40,
        "public_commit=" + "5" * 40,
        "manifest_sha256=" + "7" * 64,
        "file_set_sha256=" + "8" * 64,
    )
    lines = []
    actual_versions = {"3.9": "3.9.25", "3.12": "3.12.14"}
    for version in ("3.9", "3.12"):
        verify_prefix = (
            "portability (%s)\tVerify closed bundle before repository imports\t"
            "2026-08-13T01:01:02.1234567Z "
        ) % version
        run_prefix = (
            "portability (%s)\tRun fixed-owner public boundary\t"
            "2026-08-13T01:02:03.1234567Z "
        ) % version
        setup_prefix = (
            "portability (%s)\t"
            "Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1\t"
            "2026-08-13T01:01:30.1234567Z "
        ) % version
        lines.extend(verify_prefix + marker for marker in markers)
        lines.extend((
            setup_prefix + "Successfully set up CPython (" + actual_versions[version] + ")",
            run_prefix + "Python " + actual_versions[version],
            run_prefix + "Ran 16 tests in 0.735s",
            run_prefix + "OK",
        ))
    log = ("\n".join(lines) + "\n").encode("utf-8")
    bundle = {
        "predecessor_failed_public_witnesses": copy.deepcopy(
            PREDECESSOR_FAILED_PUBLIC_WITNESSES
        ),
        "source": {
            "private_repository": "cjl308868584-lang/crypto-quant-core",
            "candidate_commit": "3" * 40,
            "candidate_tree": "4" * 40,
            "object_format": "sha1",
            "historical_billing_blocked_private_pr": {
                "number": 32, "run_id": 31436609135,
                "status": "PRIVATE_PR_CI_NOT_EXECUTED_BILLING_BLOCKED",
            },
        },
        "files": [{"path": ".github/workflows/ci.yml", "sha256": "a" * 64, "source_blob_oid": "9" * 40}],
        "file_set_sha256": "8" * 64,
    }
    transcript = {
        "schema_version": "1.0.0",
        "gh_identity": {
            "path": "/Users/chenm4/.local/bin/gh",
            "file_sha256": "b1d6c442fde99ca27c04e1e74d624895abe37785f4a3e9e9b684bf7586ce4bc8",
            "version_size": 79,
            "version_sha256": "baca303bf2a08915a78b513817a4fc7c754a7bcdd0fce71990e75c5e067688ff",
        },
        "commands": [
            {
                "name": name, "argv": list(argv), "exit_code": 0,
                "stdout_size": len(body), "stdout_sha256": hashlib.sha256(body).hexdigest(),
                "stderr_size": 0, "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            }
            for name, argv, body in zip(
                ("run_api", "jobs_api", "run_log"),
                v064_public_ci_witness_cli._commands(run["id"]),
                (_canonical(run), _canonical(jobs), log),
            )
        ],
    }
    return bundle, _canonical(run), _canonical(jobs), log, transcript


def _transcript_with_log(transcript, log_bytes):
    changed = copy.deepcopy(transcript)
    changed["commands"][2]["stdout_size"] = len(log_bytes)
    changed["commands"][2]["stdout_sha256"] = hashlib.sha256(
        log_bytes
    ).hexdigest()
    return changed


class V064PublicCiWitnessDerivationTests(unittest.TestCase):
    @mock.patch("crypto_quant.v064_public_ci_witness.verify_v064_public_ci_bundle")
    @mock.patch("crypto_quant.v064_public_ci_witness.build_v064_public_ci_bundle_manifest")
    def test_candidate_replay_rejects_caller_bundle_that_is_not_exact_git_builder(self, build, verify):
        bundle, _run, _jobs, _log, _transcript = _realistic_inputs()
        expected = copy.deepcopy(bundle)
        build.return_value = expected
        verify.return_value = {
            "commit": "5" * 40, "tree": "6" * 40,
            "manifest_sha256": "7" * 64,
        }
        changed = copy.deepcopy(bundle)
        changed["file_set_sha256"] = "f" * 64
        with self.assertRaisesRegex(V064PublicCiWitnessError, "BUNDLE_INVALID"):
            from crypto_quant.v064_public_ci_witness import _replay_public_candidate
            _replay_public_candidate(ROOT, changed)
        verify.assert_not_called()

    @mock.patch("crypto_quant.v064_public_ci_witness.verify_v064_public_ci_bundle")
    @mock.patch("crypto_quant.v064_public_ci_witness.build_v064_public_ci_bundle_manifest")
    def test_candidate_replay_returns_only_exact_builder_bound_local_identity(self, build, verify):
        bundle, _run, _jobs, _log, _transcript = _realistic_inputs()
        build.return_value = copy.deepcopy(bundle)
        verify.return_value = {
            "commit": "5" * 40, "tree": "6" * 40,
            "manifest_sha256": "7" * 64,
        }
        from crypto_quant.v064_public_ci_witness import _replay_public_candidate
        self.assertEqual(
            _replay_public_candidate(ROOT, bundle),
            {"commit": "5" * 40, "tree": "6" * 40, "parent_count": 0, "manifest_sha256": "7" * 64},
        )
        build.assert_called_once_with(ROOT, "3" * 40)
        verify.assert_called_once()

    @mock.patch("crypto_quant.v064_public_ci_witness._replay_public_candidate")
    def test_realistic_projected_api_and_prefixed_logs_derive_success(self, replay):
        bundle, run_bytes, jobs_bytes, log_bytes, transcript = _realistic_inputs()
        replay.return_value = {
            "commit": "5" * 40, "tree": "6" * 40, "parent_count": 0,
            "manifest_sha256": "7" * 64,
        }
        witness = derive_v064_public_ci_witness(
            bundle=bundle, run_bytes=run_bytes, jobs_bytes=jobs_bytes,
            log_bytes=log_bytes, transcript=transcript,
            private_repository=ROOT,
        )
        self.assertEqual([job["python_version"] for job in witness["jobs"]], ["3.9", "3.12"])
        self.assertEqual(witness["schema_version"], "1.2.0")
        self.assertEqual(
            witness["predecessor_failed_public_witnesses"],
            bundle["predecessor_failed_public_witnesses"],
        )
        self.assertEqual(
            [job["setup_python_version"] for job in witness["jobs"]],
            ["3.9.25", "3.12.14"],
        )
        self.assertEqual(
            [job["fixed_owner_python_version"] for job in witness["jobs"]],
            ["3.9.25", "3.12.14"],
        )
        self.assertEqual(
            witness["public_source"]["repository"],
            "cjl308868584-lang/crypto-quant-v064-public-ci-r3",
        )
        replay.assert_called_once_with(ROOT, bundle)

    @mock.patch("crypto_quant.v064_public_ci_witness._replay_public_candidate")
    def test_one_bom_before_selected_timestamp_preserves_semantic_witness(self, replay):
        bundle, run_bytes, jobs_bytes, log_bytes, transcript = _realistic_inputs()
        replay.return_value = {
            "commit": "5" * 40, "tree": "6" * 40, "parent_count": 0,
            "manifest_sha256": "7" * 64,
        }
        baseline = derive_v064_public_ci_witness(
            bundle=bundle, run_bytes=run_bytes, jobs_bytes=jobs_bytes,
            log_bytes=log_bytes, transcript=transcript,
            private_repository=ROOT,
        )
        bom_log = log_bytes.replace(
            b"\t2026-08-13T01:01:02.1234567Z ",
            b"\t\xef\xbb\xbf2026-08-13T01:01:02.1234567Z ",
            1,
        )
        self.assertEqual(bom_log.count(b"\xef\xbb\xbf"), 1)
        try:
            with_bom = derive_v064_public_ci_witness(
                bundle=bundle, run_bytes=run_bytes, jobs_bytes=jobs_bytes,
                log_bytes=bom_log,
                transcript=_transcript_with_log(transcript, bom_log),
                private_repository=ROOT,
            )
        except V064PublicCiWitnessError as error:
            self.fail("single leading timestamp BOM was rejected: %s" % error)
        self.assertEqual(
            {key: value for key, value in with_bom.items()
             if key not in {"raw_evidence", "witness_hash"}},
            {key: value for key, value in baseline.items()
             if key not in {"raw_evidence", "witness_hash"}},
        )

    @mock.patch("crypto_quant.v064_public_ci_witness._replay_public_candidate")
    def test_bom_elsewhere_repeated_or_before_malformed_timestamp_is_rejected(self, replay):
        bundle, run_bytes, jobs_bytes, log_bytes, transcript = _realistic_inputs()
        replay.return_value = {
            "commit": "5" * 40, "tree": "6" * 40, "parent_count": 0,
            "manifest_sha256": "7" * 64,
        }
        selected = b"\t2026-08-13T01:01:02.1234567Z "
        mutations = {
            "elsewhere": log_bytes.replace(
                selected,
                b"\t2026-\xef\xbb\xbf08-13T01:01:02.1234567Z ",
                1,
            ),
            "repeated": log_bytes.replace(
                selected,
                b"\t\xef\xbb\xbf\xef\xbb\xbf2026-08-13T01:01:02.1234567Z ",
                1,
            ),
            "malformed_timestamp": log_bytes.replace(
                selected,
                b"\t\xef\xbb\xbf2026-08-13T01:01:02.1234567X ",
                1,
            ),
        }
        for name, changed_log in mutations.items():
            with self.subTest(name=name), self.assertRaisesRegex(
                V064PublicCiWitnessError, "^V064_PUBLIC_CI_LOG_INVALID$"
            ):
                derive_v064_public_ci_witness(
                    bundle=bundle, run_bytes=run_bytes, jobs_bytes=jobs_bytes,
                    log_bytes=changed_log,
                    transcript=_transcript_with_log(transcript, changed_log),
                    private_repository=ROOT,
                )

    @mock.patch("crypto_quant.v064_public_ci_witness._replay_public_candidate")
    def test_job_api_order_is_irrelevant_but_run_must_contain_job_times(self, replay):
        bundle, run_bytes, jobs_bytes, log_bytes, transcript = _realistic_inputs()
        replay.return_value = {"commit": "5" * 40, "tree": "6" * 40, "parent_count": 0, "manifest_sha256": "7" * 64}
        jobs = json.loads(jobs_bytes)
        jobs["jobs"].reverse()
        reversed_bytes = _canonical(jobs)
        transcript["commands"][1]["stdout_size"] = len(reversed_bytes)
        transcript["commands"][1]["stdout_sha256"] = hashlib.sha256(reversed_bytes).hexdigest()
        witness = derive_v064_public_ci_witness(
            bundle=bundle, run_bytes=run_bytes, jobs_bytes=reversed_bytes,
            log_bytes=log_bytes, transcript=transcript, private_repository=ROOT,
        )
        self.assertEqual([job["python_version"] for job in witness["jobs"]], ["3.9", "3.12"])

        jobs["jobs"][0]["completed_at"] = "2026-08-13T01:07:00Z"
        invalid = _canonical(jobs)
        transcript["commands"][1]["stdout_size"] = len(invalid)
        transcript["commands"][1]["stdout_sha256"] = hashlib.sha256(invalid).hexdigest()
        with self.assertRaisesRegex(V064PublicCiWitnessError, "JOB_INVALID"):
            derive_v064_public_ci_witness(
                bundle=bundle, run_bytes=run_bytes, jobs_bytes=invalid,
                log_bytes=log_bytes, transcript=transcript, private_repository=ROOT,
            )

    @mock.patch("crypto_quant.v064_public_ci_witness._replay_public_candidate")
    def test_unsafe_integer_duplicate_job_step_and_bad_time_fail_closed(self, replay):
        bundle, run_bytes, jobs_bytes, log_bytes, transcript = _realistic_inputs()
        replay.return_value = {"commit": "5" * 40, "tree": "6" * 40, "parent_count": 0, "manifest_sha256": "7" * 64}
        mutations = []
        mutations.append((run_bytes.replace(b"31400000000", b"9007199254740992"), jobs_bytes))
        jobs = json.loads(jobs_bytes)
        jobs["jobs"][1]["id"] = jobs["jobs"][0]["id"]
        mutations.append((run_bytes, _canonical(jobs)))
        jobs = json.loads(jobs_bytes)
        jobs["jobs"][0]["steps"][1]["number"] = 1
        mutations.append((run_bytes, _canonical(jobs)))
        jobs = json.loads(jobs_bytes)
        jobs["jobs"][0]["completed_at"] = "2026-08-13T00:00:00Z"
        mutations.append((run_bytes, _canonical(jobs)))
        for changed_run, changed_jobs in mutations:
            with self.subTest(), self.assertRaises(V064PublicCiWitnessError):
                derive_v064_public_ci_witness(
                    bundle=bundle, run_bytes=changed_run, jobs_bytes=changed_jobs,
                    log_bytes=log_bytes, transcript=transcript,
                    private_repository=ROOT,
                )

    @mock.patch("crypto_quant.v064_public_ci_witness._replay_public_candidate")
    def test_run_job_and_log_mutation_matrix_fails_closed(self, replay):
        bundle, run_bytes, jobs_bytes, log_bytes, transcript = _realistic_inputs()
        replay.return_value = {"commit": "5" * 40, "tree": "6" * 40, "parent_count": 0, "manifest_sha256": "7" * 64}
        mutations = []
        for key, value in (
            ("repository", "someone/other"), ("event", "workflow_dispatch"),
            ("head_branch", "other"), ("head_sha", "f" * 40),
            ("run_attempt", 2), ("path", ".github/workflows/other.yml"),
        ):
            changed = json.loads(run_bytes); changed[key] = value
            mutations.append((_canonical(changed), jobs_bytes, log_bytes))
        for key, value in (("conclusion", "failure"), ("status", "queued")):
            changed = json.loads(jobs_bytes); changed["jobs"][0][key] = value
            mutations.append((run_bytes, _canonical(changed), log_bytes))
        changed = json.loads(jobs_bytes); changed["jobs"][0]["steps"] = []
        mutations.append((run_bytes, _canonical(changed), log_bytes))
        changed = json.loads(jobs_bytes); changed["jobs"][0]["steps"][-1]["name"] = "Other"
        mutations.append((run_bytes, _canonical(changed), log_bytes))
        mutations.append((run_bytes, jobs_bytes, log_bytes.replace(b"source_candidate_f=", b"source_missing=")))
        for changed_run, changed_jobs, changed_log in mutations:
            changed_transcript = copy.deepcopy(transcript)
            for index, body in enumerate((changed_run, changed_jobs, changed_log)):
                changed_transcript["commands"][index]["stdout_size"] = len(body)
                changed_transcript["commands"][index]["stdout_sha256"] = hashlib.sha256(body).hexdigest()
            with self.subTest(), self.assertRaises(V064PublicCiWitnessError):
                derive_v064_public_ci_witness(
                    bundle=bundle, run_bytes=changed_run, jobs_bytes=changed_jobs,
                    log_bytes=changed_log, transcript=changed_transcript,
                    private_repository=ROOT,
                )

    @mock.patch("crypto_quant.v064_public_ci_witness._replay_public_candidate")
    def test_distinct_fixed_owner_interpreters_are_required(self, replay):
        bundle, run_bytes, jobs_bytes, log_bytes, transcript = _realistic_inputs()
        replay.return_value = {
            "commit": "5" * 40, "tree": "6" * 40, "parent_count": 0,
            "manifest_sha256": "7" * 64,
        }
        changed_log = log_bytes.replace(b"Python 3.9.25", b"Python 3.12.14")
        changed_transcript = copy.deepcopy(transcript)
        changed_transcript["commands"][2]["stdout_size"] = len(changed_log)
        changed_transcript["commands"][2]["stdout_sha256"] = hashlib.sha256(
            changed_log
        ).hexdigest()
        with self.assertRaisesRegex(
            V064PublicCiWitnessError, "^V064_PUBLIC_CI_LOG_INVALID$"
        ):
            derive_v064_public_ci_witness(
                bundle=bundle, run_bytes=run_bytes, jobs_bytes=jobs_bytes,
                log_bytes=changed_log, transcript=changed_transcript,
                private_repository=ROOT,
            )

    @mock.patch("crypto_quant.v064_public_ci_witness._replay_public_candidate")
    def test_extra_conflicting_setup_or_fixed_owner_identity_is_rejected(self, replay):
        bundle, run_bytes, jobs_bytes, log_bytes, transcript = _realistic_inputs()
        replay.return_value = {
            "commit": "5" * 40, "tree": "6" * 40, "parent_count": 0,
            "manifest_sha256": "7" * 64,
        }
        setup_prefix = (
            b"portability (3.9)\t"
            b"Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1\t"
            b"2026-08-13T01:01:31.1234567Z "
        )
        fixed_prefix = (
            b"portability (3.9)\tRun fixed-owner public boundary\t"
            b"2026-08-13T01:02:04.1234567Z "
        )
        for source, extra in (
            ("setup", setup_prefix + b"Successfully set up CPython (3.12.14)\n"),
            ("fixed_owner", fixed_prefix + b"Python 3.12.14\n"),
        ):
            changed_log = log_bytes + extra
            changed_transcript = copy.deepcopy(transcript)
            changed_transcript["commands"][2]["stdout_size"] = len(changed_log)
            changed_transcript["commands"][2]["stdout_sha256"] = hashlib.sha256(
                changed_log
            ).hexdigest()
            with self.subTest(source=source), self.assertRaisesRegex(
                V064PublicCiWitnessError, "^V064_PUBLIC_CI_LOG_INVALID$"
            ):
                derive_v064_public_ci_witness(
                    bundle=bundle, run_bytes=run_bytes, jobs_bytes=jobs_bytes,
                    log_bytes=changed_log, transcript=changed_transcript,
                    private_repository=ROOT,
                )

    @mock.patch("crypto_quant.v064_public_ci_witness._replay_public_candidate")
    def test_raw_api_json_must_be_exact_canonical_bytes(self, replay):
        bundle, run_bytes, jobs_bytes, log_bytes, transcript = _realistic_inputs()
        replay.return_value = {
            "commit": "5" * 40, "tree": "6" * 40, "parent_count": 0,
            "manifest_sha256": "7" * 64,
        }
        for index, (run_body, jobs_body, reason) in enumerate((
            (b" " + run_bytes, jobs_bytes, "RUN_INVALID"),
            (run_bytes, b" " + jobs_bytes, "JOBS_INVALID"),
        )):
            changed_transcript = copy.deepcopy(transcript)
            body = run_body if index == 0 else jobs_body
            changed_transcript["commands"][index]["stdout_size"] = len(body)
            changed_transcript["commands"][index]["stdout_sha256"] = hashlib.sha256(
                body
            ).hexdigest()
            with self.subTest(reason=reason), self.assertRaisesRegex(
                V064PublicCiWitnessError, reason
            ):
                derive_v064_public_ci_witness(
                    bundle=bundle, run_bytes=run_body, jobs_bytes=jobs_body,
                    log_bytes=log_bytes, transcript=changed_transcript,
                    private_repository=ROOT,
                )

    def test_cli_retains_exact_stdout_and_has_no_supplied_result_fields(self):
        source = inspect.getsource(v064_public_ci_witness_cli)
        for forbidden in ("--status", "--conclusion", "--verified", "--repository", "--filename", "--output", "--python-version", "--predecessor"):
            self.assertNotIn(forbidden, source)
        completed = mock.Mock(
            returncode=0, stdout=b"exact stdout\n", stderr=b""
        )
        with mock.patch(
            "crypto_quant.v064_public_ci_witness_cli._verify_gh",
            return_value={"path": "/Users/chenm4/.local/bin/gh"},
        ), mock.patch(
            "crypto_quant.v064_public_ci_witness_cli._run_bounded",
            return_value=completed,
        ):
            capture = v064_public_ci_witness_cli._capture(31400000000)
        self.assertEqual(capture["raw"]["run_api"], b"exact stdout\n")
        self.assertEqual(len(capture["transcript"]["commands"]), 3)

    def test_cli_verifies_frozen_gh_binary_before_any_network_command(self):
        expected_version = (
            b"gh version 2.96.0 (2026-07-02)\n"
            b"https://github.com/cli/cli/releases/tag/v2.96.0\n"
        )
        calls = []

        def run(argv, **kwargs):
            calls.append(tuple(argv))
            return mock.Mock(returncode=0, stdout=expected_version, stderr=b"")

        with mock.patch(
            "crypto_quant.v064_public_ci_witness_cli._run_bounded",
            side_effect=run,
        ) as bounded, mock.patch(
            "crypto_quant.v064_public_ci_witness_cli._gh_file_sha256",
            return_value="b1d6c442fde99ca27c04e1e74d624895abe37785f4a3e9e9b684bf7586ce4bc8",
        ) as identity_check:
            identity = v064_public_ci_witness_cli._verify_gh()
        self.assertEqual(calls, [("/Users/chenm4/.local/bin/gh", "--version")])
        self.assertEqual(identity["version_sha256"], hashlib.sha256(expected_version).hexdigest())
        self.assertEqual(identity_check.call_count, 2)
        self.assertEqual(bounded.call_args.kwargs, {"timeout_seconds": 5, "max_bytes": 4096})

        with mock.patch(
            "crypto_quant.v064_public_ci_witness_cli._verify_gh",
            side_effect=ValueError("V064_PUBLIC_CI_GH_INVALID"),
        ), mock.patch("subprocess.run") as network:
            with self.assertRaisesRegex(ValueError, "GH_INVALID"):
                v064_public_ci_witness_cli._capture(31400000000)
            network.assert_not_called()

    def test_gh_identity_requires_exact_reviewed_executable_mode(self):
        class Stat:
            st_mode = stat.S_IFREG | 0o700
            st_uid = os.getuid()
            st_nlink = 1
            st_dev = 1
            st_ino = 2
            st_size = 3
        with mock.patch("os.lstat", return_value=Stat()), mock.patch("os.open") as opened:
            with self.assertRaisesRegex(ValueError, "GH_INVALID"):
                v064_public_ci_witness_cli._gh_file_sha256()
            opened.assert_not_called()

    @mock.patch("crypto_quant.v064_public_ci_witness._replay_public_candidate")
    def test_loader_uses_nofollow_descriptor_and_recomputes_id_and_hash(self, replay):
        bundle, run_bytes, jobs_bytes, log_bytes, transcript = _realistic_inputs()
        replay.return_value = {"commit": "5" * 40, "tree": "6" * 40, "parent_count": 0, "manifest_sha256": "7" * 64}
        witness = derive_v064_public_ci_witness(
            bundle=bundle, run_bytes=run_bytes, jobs_bytes=jobs_bytes,
            log_bytes=log_bytes, transcript=transcript,
            private_repository=ROOT,
        )
        with tempfile.TemporaryDirectory(dir=ROOT) as raw:
            raw_root = Path(raw).resolve()
            path = raw_root / "witness.json"
            path.write_bytes(_canonical(witness)); path.chmod(0o600)
            self.assertEqual(load_v064_public_ci_witness(path), witness)

            mismatched = copy.deepcopy(witness)
            mismatched["jobs"][0]["setup_python_version"] = "3.9.24"
            mismatched["witness_hash"] = artifact_self_hash(
                mismatched, "witness_hash"
            )
            mismatched_path = raw_root / "mismatched.json"
            mismatched_path.write_bytes(_canonical(mismatched))
            mismatched_path.chmod(0o600)
            with self.assertRaisesRegex(
                V064PublicCiWitnessError, "WITNESS_SCHEMA_INVALID"
            ):
                load_v064_public_ci_witness(mismatched_path)

            target = raw_root / "target"; target.write_bytes(path.read_bytes()); target.chmod(0o600)
            path.unlink(); path.symlink_to(target)
            with self.assertRaises(V064PublicCiWitnessError):
                load_v064_public_ci_witness(path)

            trusted_parent = raw_root / "trusted"
            trusted_parent.mkdir(mode=0o700)
            nested = trusted_parent / "witness.json"
            nested.write_bytes(_canonical(witness)); nested.chmod(0o600)
            link_parent = raw_root / "linked"
            link_parent.symlink_to(trusted_parent, target_is_directory=True)
            with self.assertRaises(V064PublicCiWitnessError):
                load_v064_public_ci_witness(link_parent / "witness.json")

    def test_cli_timeout_and_exact_stderr_are_retained(self):
        completed = mock.Mock(returncode=7, stdout=b"partial stdout", stderr=b"exact stderr\n")
        with mock.patch(
            "crypto_quant.v064_public_ci_witness_cli._verify_gh",
            return_value={"path": "/Users/chenm4/.local/bin/gh"},
        ), mock.patch(
            "crypto_quant.v064_public_ci_witness_cli._run_bounded",
            return_value=completed,
        ) as bounded:
            capture = v064_public_ci_witness_cli._capture(31400000000)
            self.assertEqual(capture["raw_stderr"]["run_api"], b"exact stderr\n")
        self.assertEqual(capture["transcript"]["commands"][0]["stderr_size"], 13)
        self.assertEqual(bounded.call_count, 3)
        for call in bounded.call_args_list:
            self.assertEqual(call.kwargs, {"timeout_seconds": 60, "max_bytes": 67108864})

    def test_capture_replays_binary_identity_before_and_after_each_command(self):
        completed = mock.Mock(returncode=0, stdout=b"body", stderr=b"")
        identities = [
            {"path": "/Users/chenm4/.local/bin/gh", "file_sha256": "b" * 64,
             "version_size": 79, "version_sha256": "c" * 64}
            for _ in range(7)
        ]
        with mock.patch(
            "crypto_quant.v064_public_ci_witness_cli._verify_gh",
            side_effect=identities,
        ) as verify, mock.patch(
            "crypto_quant.v064_public_ci_witness_cli._run_bounded",
            return_value=completed,
        ):
            v064_public_ci_witness_cli._capture(31400000000)
        self.assertEqual(verify.call_count, 7)

        changed = copy.deepcopy(identities)
        changed[2] = dict(changed[2], file_sha256="d" * 64)
        with mock.patch(
            "crypto_quant.v064_public_ci_witness_cli._verify_gh",
            side_effect=changed,
        ), mock.patch(
            "crypto_quant.v064_public_ci_witness_cli._run_bounded",
            return_value=completed,
        ):
            with self.assertRaisesRegex(ValueError, "GH_IDENTITY_CHANGED"):
                v064_public_ci_witness_cli._capture(31400000000)

    def test_bounded_runner_maps_timeout_and_rejects_oversize_output(self):
        with self.assertRaisesRegex(ValueError, "GH_COMMAND_FAILED"):
            v064_public_ci_witness_cli._run_bounded(
                (sys.executable, "-c", "import time; time.sleep(2)"),
                timeout_seconds=1, max_bytes=4,
            )
        with self.assertRaisesRegex(ValueError, "GH_OUTPUT_TOO_LARGE"):
            v064_public_ci_witness_cli._run_bounded(
                (sys.executable, "-c", "import sys; sys.stdout.write('12345')"),
                timeout_seconds=2, max_bytes=4,
            )


class V064PublicCiWitnessCliTests(unittest.TestCase):
    def test_acquisition_is_fixed_to_r3_repository_root_names_and_three_reads(self):
        run_id = 31400000000
        repository = "cjl308868584-lang/crypto-quant-v064-public-ci-r3"
        prefix = "repos/%s/actions/runs/%s" % (repository, run_id)
        commands = v064_public_ci_witness_cli._commands(run_id)
        self.assertEqual(len(commands), 3)
        self.assertEqual(commands[0][:3], (
            "/Users/chenm4/.local/bin/gh", "api", prefix,
        ))
        self.assertEqual(commands[1][:3], (
            "/Users/chenm4/.local/bin/gh", "api",
            prefix + "/jobs?filter=all&per_page=100",
        ))
        self.assertEqual(commands[2], (
            "/Users/chenm4/.local/bin/gh", "run", "view", str(run_id),
            "--repo", repository, "--log",
        ))
        self.assertEqual(
            v064_public_ci_witness_cli._ARTIFACT_ROOT,
            v064_public_ci_witness_cli._PRIVATE_REPOSITORY
            / "artifacts" / "v064-public-ci-r3",
        )
        self.assertEqual(
            v064_public_ci_witness_cli._PUBLIC_CANDIDATE_MANIFEST,
            Path(
                "/private/tmp/crypto-quant-v064-public-ci-r3-candidate/"
                "bundle-manifest-v1.json"
            ),
        )
        self.assertEqual(
            v064_public_ci_witness_cli._EVIDENCE_NAMES,
            (
                "v064-public-ci-r3-run-api-v1.json",
                "v064-public-ci-r3-jobs-api-v1.json",
                "v064-public-ci-r3-run-log-v1.txt",
                "v064-public-ci-r3-acquisition-transcript-v1.json",
                "v064-public-ci-r3-witness-v1.json",
            ),
        )

    def test_run_id_is_only_caller_acquisition_selector(self):
        source = inspect.getsource(v064_public_ci_witness_cli.main)
        self.assertEqual(source.count("parser.add_argument"), 1)
        self.assertIn('parser.add_argument("--run-id"', source)
        for forbidden in (
            "--status", "--success", "--conclusion", "--python-version",
            "--repository", "--path", "--filename", "--output",
        ):
            self.assertNotIn(forbidden, source)
        with self.assertRaises(TypeError):
            bundle, run_bytes, jobs_bytes, log_bytes, transcript = _realistic_inputs()
            derive_v064_public_ci_witness(
                bundle=bundle, run_bytes=run_bytes, jobs_bytes=jobs_bytes,
                log_bytes=log_bytes, transcript=transcript,
                private_repository=ROOT, success=True,
            )


class V064PublicCiWitnessPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name) / "repository"
        self.repository.mkdir(mode=0o700)
        self.artifacts = self.repository / "artifacts"
        self.artifacts.mkdir(mode=0o755)
        self.output = self.artifacts / "v064-public-ci-r3"
        self.patches = (
            mock.patch.object(v064_public_ci_witness_cli, "_PRIVATE_REPOSITORY", self.repository),
            mock.patch.object(v064_public_ci_witness_cli, "_ARTIFACT_ROOT", self.output),
            mock.patch.object(v064_public_ci_witness_cli, "_OWNER_UID", os.geteuid()),
            mock.patch.object(
                v064_public_ci_witness_cli,
                "_validate_repository_identity",
                return_value=None,
                create=True,
            ),
        )
        for patcher in self.patches:
            patcher.start()
        self.prepared = {
            "v064-public-ci-r3-run-api-v1.json": b'{"run":1}\n',
            "v064-public-ci-r3-jobs-api-v1.json": b'{"jobs":2}\n',
            "v064-public-ci-r3-run-log-v1.txt": b"exact log\n",
            "v064-public-ci-r3-acquisition-transcript-v1.json": b'{"transcript":3}\n',
            "v064-public-ci-r3-witness-v1.json": b'{"witness":4}\n',
        }

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temporary.cleanup()

    @staticmethod
    def _snapshot(path):
        value = path.lstat()
        return (
            path.read_bytes() if stat.S_ISREG(value.st_mode) else None,
            value.st_mode,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
            value.st_dev,
            value.st_ino,
            value.st_nlink,
        )

    def test_fixed_publisher_creates_exact_owner_only_files_and_replays(self):
        first = v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertEqual(first["status"], "V064_PUBLIC_CI_R3_EVIDENCE_PUBLISHED")
        self.assertEqual(set(first["files"]), set(self.prepared))
        snapshots = {}
        for name, body in self.prepared.items():
            path = self.output / name
            value = path.lstat()
            self.assertTrue(stat.S_ISREG(value.st_mode))
            self.assertEqual(stat.S_IMODE(value.st_mode), 0o600)
            self.assertEqual(value.st_uid, os.geteuid())
            self.assertEqual(value.st_nlink, 1)
            self.assertEqual(path.read_bytes(), body)
            snapshots[name] = self._snapshot(path)
        self.assertEqual(
            [path for path in self.output.iterdir() if path.name.endswith(".staging")],
            [],
        )
        second = v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertEqual(second["status"], "V064_PUBLIC_CI_R3_EVIDENCE_ALREADY_PUBLISHED")
        self.assertEqual(
            {name: self._snapshot(self.output / name) for name in self.prepared},
            snapshots,
        )

    def test_all_files_are_staged_before_first_canonical_publish_and_retry_recovers(self):
        calls = []

        def crash_before_first(parent_fd, source, target):
            calls.append((source, target))
            raise RuntimeError("test-only crash before first publish")

        with mock.patch.object(
            v064_public_ci_witness_cli,
            "_atomic_no_replace",
            side_effect=crash_before_first,
        ):
            with self.assertRaisesRegex(RuntimeError, "test-only crash"):
                v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [path for path in self.output.iterdir() if path.name in self.prepared],
            [],
        )
        self.assertEqual(
            len([path for path in self.output.iterdir() if path.name.endswith(".staging")]),
            5,
        )
        with mock.patch.object(
            v064_public_ci_witness_cli, "_write_all", wraps=v064_public_ci_witness_cli._write_all
        ) as write:
            result = v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertEqual(result["status"], "V064_PUBLIC_CI_R3_EVIDENCE_PUBLISHED")
        self.assertEqual(write.call_count, 0)

    def test_partial_staging_write_is_completed_only_after_exact_prefix_replay(self):
        real_write = v064_public_ci_witness_cli._write_all
        calls = 0

        def partial_then_crash(descriptor, body):
            nonlocal calls
            calls += 1
            if calls == 1:
                os.write(descriptor, body[:2])
                raise RuntimeError("test-only partial staging crash")
            return real_write(descriptor, body)

        with mock.patch.object(
            v064_public_ci_witness_cli, "_write_all", side_effect=partial_then_crash
        ):
            with self.assertRaisesRegex(RuntimeError, "partial staging"):
                v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertEqual(
            len([path for path in self.output.iterdir() if path.name.endswith(".staging")]),
            1,
        )
        result = v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertEqual(result["status"], "V064_PUBLIC_CI_R3_EVIDENCE_PUBLISHED")
        for name, body in self.prepared.items():
            self.assertEqual((self.output / name).read_bytes(), body)

    def test_failed_staging_fsync_is_reconfirmed_before_publication(self):
        real_fsync = v064_public_ci_witness_cli._fsync
        calls = 0

        def fail_first(descriptor):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_FSYNC_FAILED")
            return real_fsync(descriptor)

        with mock.patch.object(
            v064_public_ci_witness_cli, "_fsync", side_effect=fail_first
        ):
            with self.assertRaisesRegex(ValueError, "FSYNC_FAILED"):
                v064_public_ci_witness_cli._publish_evidence(self.prepared)
        real_os_fsync = os.fsync
        regular_fsyncs = 0

        def count_regular(descriptor):
            nonlocal regular_fsyncs
            if stat.S_ISREG(os.fstat(descriptor).st_mode):
                regular_fsyncs += 1
            return real_os_fsync(descriptor)

        with mock.patch.object(
            v064_public_ci_witness_cli.os, "fsync", side_effect=count_regular
        ):
            result = v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertEqual(result["status"], "V064_PUBLIC_CI_R3_EVIDENCE_PUBLISHED")
        self.assertEqual(regular_fsyncs, 5)

    def test_retry_after_first_visible_final_preserves_inode_and_performs_zero_writes(self):
        real = v064_public_ci_witness_cli._atomic_no_replace
        calls = 0

        def publish_first_then_crash(parent_fd, source, target):
            nonlocal calls
            calls += 1
            real(parent_fd, source, target)
            raise RuntimeError("test-only crash after first publish")

        with mock.patch.object(
            v064_public_ci_witness_cli,
            "_atomic_no_replace",
            side_effect=publish_first_then_crash,
        ):
            with self.assertRaisesRegex(RuntimeError, "after first publish"):
                v064_public_ci_witness_cli._publish_evidence(self.prepared)
        first_name = next(iter(self.prepared))
        first = self.output / first_name
        inode = first.lstat().st_ino
        self.assertEqual(calls, 1)
        with mock.patch.object(
            v064_public_ci_witness_cli, "_write_all", wraps=v064_public_ci_witness_cli._write_all
        ) as write:
            result = v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertEqual(result["status"], "V064_PUBLIC_CI_R3_EVIDENCE_PUBLISHED")
        self.assertEqual(write.call_count, 0)
        self.assertEqual(first.lstat().st_ino, inode)

    def test_untrusted_existing_final_is_rejected_without_sentinel_side_effect(self):
        self.output.mkdir(mode=0o700)
        name = next(iter(self.prepared))
        final = self.output / name
        sentinel = Path(self.temporary.name) / "sentinel"
        sentinel.write_bytes(self.prepared[name])
        sentinel.chmod(0o600)
        final.symlink_to(sentinel)
        before = self._snapshot(sentinel)
        with self.assertRaisesRegex(ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_UNTRUSTED"):
            v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertEqual(self._snapshot(sentinel), before)
        self.assertTrue(final.is_symlink())
        self.assertEqual(
            [path for path in self.output.iterdir() if path.name.endswith(".staging")],
            [],
        )

    def test_hardlink_and_nonregular_wrong_mode_and_different_bytes_fail_without_mutation(self):
        name = next(iter(self.prepared))
        for case_name in (
            "hardlink", "fifo", "directory", "wrong-mode",
            "different-bytes",
        ):
            with self.subTest(case_name=case_name):
                repository = Path(self.temporary.name) / case_name / "repository"
                repository.mkdir(parents=True, mode=0o700)
                artifacts = repository / "artifacts"
                artifacts.mkdir(mode=0o755)
                output = artifacts / "v064-public-ci-r3"
                output.mkdir(mode=0o700)
                final = output / name
                sentinel = Path(self.temporary.name) / ("sentinel-" + case_name)
                if case_name == "hardlink":
                    sentinel.write_bytes(self.prepared[name])
                    sentinel.chmod(0o600)
                    os.link(sentinel, final)
                elif case_name == "fifo":
                    os.mkfifo(final, 0o600)
                    sentinel = final
                elif case_name == "directory":
                    final.mkdir(mode=0o600)
                    sentinel = final
                elif case_name == "wrong-mode":
                    final.write_bytes(self.prepared[name])
                    final.chmod(0o644)
                    sentinel = final
                else:
                    final.write_bytes(b"x" * len(self.prepared[name]))
                    final.chmod(0o600)
                    sentinel = final
                before = self._snapshot(sentinel)
                with mock.patch.object(
                    v064_public_ci_witness_cli, "_ARTIFACT_ROOT", output
                ), mock.patch.object(
                    v064_public_ci_witness_cli,
                    "_PRIVATE_REPOSITORY",
                    repository,
                ):
                    with self.assertRaisesRegex(
                        ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_UNTRUSTED"
                    ):
                        v064_public_ci_witness_cli._publish_evidence(self.prepared)
                self.assertEqual(self._snapshot(sentinel), before)
                self.assertEqual(
                    [path for path in output.iterdir() if path.name.endswith(".staging")],
                    [],
                )

    def test_prepared_key_or_size_failure_precedes_root_creation(self):
        missing = dict(self.prepared)
        missing.pop(next(iter(missing)))
        with self.assertRaisesRegex(ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_INVALID"):
            v064_public_ci_witness_cli._publish_evidence(missing)
        self.assertFalse(self.output.exists())

    def test_short_writes_are_completed_exactly(self):
        real_write = os.write

        def short_write(descriptor, body):
            return real_write(descriptor, body[: max(1, len(body) // 2)])

        with mock.patch.object(
            v064_public_ci_witness_cli.os, "write", side_effect=short_write
        ):
            result = v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertEqual(result["status"], "V064_PUBLIC_CI_R3_EVIDENCE_PUBLISHED")
        for name, body in self.prepared.items():
            self.assertEqual((self.output / name).read_bytes(), body)

    def test_ceremony_lock_failure_precedes_staging(self):
        with mock.patch.object(
            v064_public_ci_witness_cli.fcntl,
            "flock",
            side_effect=OSError(errno.ENOTSUP, "unsupported"),
        ):
            with self.assertRaisesRegex(
                ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_LOCK_FAILED"
            ):
                v064_public_ci_witness_cli._publish_evidence(self.prepared)
        if self.output.exists():
            self.assertEqual(tuple(self.output.iterdir()), ())

    def test_noncanonical_json_precedes_root_creation(self):
        for name in (
            "v064-public-ci-r3-run-api-v1.json",
            "v064-public-ci-r3-jobs-api-v1.json",
            "v064-public-ci-r3-acquisition-transcript-v1.json",
            "v064-public-ci-r3-witness-v1.json",
        ):
            with self.subTest(name=name):
                prepared = dict(self.prepared)
                prepared[name] = b'{ "not":"canonical" }\n'
                with self.assertRaisesRegex(
                    ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_INVALID"
                ):
                    v064_public_ci_witness_cli._publish_evidence(prepared)
                self.assertFalse(self.output.exists())
        prepared = dict(self.prepared)
        prepared["v064-public-ci-r3-run-api-v1.json"] = b'{"value":NaN}\n'
        with self.assertRaisesRegex(
            ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_INVALID"
        ):
            v064_public_ci_witness_cli._publish_evidence(prepared)
        self.assertFalse(self.output.exists())

    def test_wrong_owner_is_rejected_before_read(self):
        self.output.mkdir(mode=0o700)
        name = next(iter(self.prepared))
        final = self.output / name
        final.write_bytes(self.prepared[name])
        final.chmod(0o600)
        root_fd = os.open(self.output, os.O_RDONLY | os.O_DIRECTORY)
        real_fstat = os.fstat

        def wrong_owner(descriptor):
            value = real_fstat(descriptor)
            if descriptor == root_fd:
                return value
            fields = list(value)
            fields[4] = value.st_uid + 1
            return os.stat_result(fields)

        try:
            with mock.patch.object(
                v064_public_ci_witness_cli.os, "fstat", side_effect=wrong_owner
            ), mock.patch.object(
                v064_public_ci_witness_cli.os, "read", wraps=os.read
            ) as read:
                with self.assertRaisesRegex(
                    ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_UNTRUSTED"
                ):
                    v064_public_ci_witness_cli._read_named(
                        root_fd, name, self.prepared[name]
                    )
            self.assertEqual(read.call_count, 0)
        finally:
            os.close(root_fd)

    def test_post_file_fsync_attachment_swap_fails_before_publication(self):
        real_fsync = v064_public_ci_witness_cli._fsync
        swapped = False

        def swap_after_file_fsync(descriptor):
            nonlocal swapped
            real_fsync(descriptor)
            if not swapped and stat.S_ISREG(os.fstat(descriptor).st_mode):
                swapped = True
                staging = next(
                    path for path in self.output.iterdir()
                    if path.name.endswith(".staging")
                )
                replacement = self.output / "test-only-replacement"
                replacement.write_bytes(next(iter(self.prepared.values())))
                replacement.chmod(0o600)
                os.replace(replacement, staging)

        with mock.patch.object(
            v064_public_ci_witness_cli, "_fsync", side_effect=swap_after_file_fsync
        ):
            with self.assertRaisesRegex(
                ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_UNTRUSTED"
            ):
                v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertFalse(any((self.output / name).exists() for name in self.prepared))

    def test_fresh_process_concurrent_loser_creates_no_staging_and_winner_recovers(self):
        marker = Path(self.temporary.name) / "winner-locked"
        release = Path(self.temporary.name) / "release-winner"
        child = r'''
import json
import os
import sys
import time
from pathlib import Path
from crypto_quant import v064_public_ci_witness_cli as module

repository = Path(sys.argv[1])
role = sys.argv[2]
marker = Path(sys.argv[3])
release = Path(sys.argv[4])
module._PRIVATE_REPOSITORY = repository
module._ARTIFACT_ROOT = repository / "artifacts" / "v064-public-ci-r3"
module._OWNER_UID = os.geteuid()
module._validate_repository_identity = lambda: None
prepared = {
    "v064-public-ci-r3-run-api-v1.json": b'{"run":1}\n',
    "v064-public-ci-r3-jobs-api-v1.json": b'{"jobs":2}\n',
    "v064-public-ci-r3-run-log-v1.txt": b"exact log\n",
    "v064-public-ci-r3-acquisition-transcript-v1.json": b'{"transcript":3}\n',
    "v064-public-ci-r3-witness-v1.json": b'{"witness":4}\n',
}
if role == "winner":
    original = module._staging_inventory
    first = [True]
    def hold(root_fd, value):
        result = original(root_fd, value)
        if first[0]:
            first[0] = False
            marker.write_text("locked")
            deadline = time.monotonic() + 10
            while not release.exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("test-only release timeout")
                time.sleep(0.01)
        return result
    module._staging_inventory = hold
try:
    print(json.dumps(module._publish_evidence(prepared), sort_keys=True))
except BaseException as error:
    print(type(error).__name__ + ":" + str(error))
    raise SystemExit(3)
'''
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        winner = subprocess.Popen(
            (sys.executable, "-c", child, str(self.repository), "winner", str(marker), str(release)),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
        )
        deadline = time.monotonic() + 10
        while not marker.exists() and winner.poll() is None:
            if time.monotonic() >= deadline:
                winner.kill()
                winner.wait()
                self.fail("winner did not reach retained-directory boundary")
            time.sleep(0.01)
        loser = subprocess.run(
            (sys.executable, "-c", child, str(self.repository), "loser", str(marker), str(release)),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment, timeout=10,
        )
        release.write_text("release")
        winner_stdout, winner_stderr = winner.communicate(timeout=10)
        self.assertEqual(
            winner.returncode,
            0,
            (winner_stdout + winner_stderr).decode(errors="replace"),
        )
        self.assertEqual(loser.returncode, 3)
        self.assertIn(b"V064_PUBLIC_CI_R3_EVIDENCE_CONCURRENT", loser.stdout)
        self.assertIn(b"V064_PUBLIC_CI_R3_EVIDENCE_PUBLISHED", winner_stdout)
        self.assertEqual(
            tuple(sorted(path.name for path in self.output.iterdir())),
            tuple(sorted(self.prepared)),
        )

    def test_no_replace_failure_and_exact_concurrent_loser_never_overwrite(self):
        with mock.patch.object(
            v064_public_ci_witness_cli,
            "_atomic_no_replace",
            side_effect=ValueError("test-only no-replace failure"),
        ):
            with self.assertRaisesRegex(ValueError, "no-replace failure"):
                v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertFalse(any((self.output / name).exists() for name in self.prepared))

        for path in self.output.iterdir():
            path.unlink()
        real = v064_public_ci_witness_cli._atomic_no_replace
        winner = {}

        def lose_after_exact_winner(parent_fd, source, target):
            real(parent_fd, source, target)
            winner["inode"] = (self.output / target).lstat().st_ino
            raise FileExistsError(target)

        with mock.patch.object(
            v064_public_ci_witness_cli,
            "_atomic_no_replace",
            side_effect=lose_after_exact_winner,
        ):
            with self.assertRaises(FileExistsError):
                v064_public_ci_witness_cli._publish_evidence(self.prepared)
        first = self.output / next(iter(self.prepared))
        self.assertEqual(first.lstat().st_ino, winner["inode"])
        self.assertEqual(first.read_bytes(), next(iter(self.prepared.values())))

    def test_missing_or_zero_required_flags_fail_before_root_creation(self):
        for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"):
            for value in (None, 0):
                with self.subTest(flag=flag, value=value):
                    repository = Path(self.temporary.name) / (flag + str(value))
                    repository.mkdir(mode=0o700)
                    artifacts = repository / "artifacts"
                    artifacts.mkdir(mode=0o755)
                    output = artifacts / "v064-public-ci-r3"
                    with mock.patch.object(
                        v064_public_ci_witness_cli, "_PRIVATE_REPOSITORY", repository
                    ), mock.patch.object(
                        v064_public_ci_witness_cli, "_ARTIFACT_ROOT", output
                    ), mock.patch.object(
                        v064_public_ci_witness_cli.os, flag, value, create=True
                    ):
                        with self.assertRaisesRegex(
                            ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_UNSUPPORTED"
                        ):
                            v064_public_ci_witness_cli._publish_evidence(self.prepared)
                    self.assertFalse(output.exists())

    def test_extra_directory_entry_blocks_without_mutation_or_staging(self):
        self.output.mkdir(mode=0o700)
        sentinel = self.output / "unrelated-sentinel"
        sentinel.write_bytes(b"external\n")
        sentinel.chmod(0o600)
        before = self._snapshot(sentinel)
        with self.assertRaisesRegex(
            ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_RECOVERY_BLOCKED"
        ):
            v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertEqual(self._snapshot(sentinel), before)
        self.assertEqual(tuple(self.output.iterdir()), (sentinel,))

    def test_parent_descriptor_close_failure_never_returns_success(self):
        real_close = os.close
        calls = 0

        def close_then_fail_first(descriptor):
            nonlocal calls
            calls += 1
            real_close(descriptor)
            if calls == 1:
                raise OSError("test-only parent close failure")

        with mock.patch.object(
            v064_public_ci_witness_cli.os, "close", side_effect=close_then_fail_first
        ):
            with self.assertRaisesRegex(
                ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_CLOSE_FAILED"
            ):
                v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertGreaterEqual(calls, 2)
        self.assertEqual(
            [path for path in self.output.iterdir() if path.name in self.prepared],
            [],
        )

    def test_open_root_failure_closes_each_successfully_opened_descriptor_once(self):
        self.output.mkdir(mode=0o755)
        real_open = os.open
        real_close = os.close
        opened = []
        closed = []

        def record_open(*args, **kwargs):
            descriptor = real_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor

        def record_close(descriptor):
            closed.append(descriptor)
            real_close(descriptor)

        with mock.patch.object(
            v064_public_ci_witness_cli.os, "open", side_effect=record_open
        ), mock.patch.object(
            v064_public_ci_witness_cli.os, "close", side_effect=record_close
        ):
            with self.assertRaisesRegex(
                ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_ROOT_INVALID"
            ):
                v064_public_ci_witness_cli._open_artifact_root()
        self.assertEqual(len(opened), 2)
        self.assertCountEqual(closed, opened)
        for descriptor in opened:
            self.assertEqual(closed.count(descriptor), 1)

    def test_read_primary_failure_is_preserved_when_descriptor_close_fails(self):
        self.output.mkdir(mode=0o700)
        name = next(iter(self.prepared))
        final = self.output / name
        final.write_bytes(self.prepared[name])
        final.chmod(0o600)
        root_fd = os.open(self.output, os.O_RDONLY | os.O_DIRECTORY)
        real_close = os.close

        def close_then_fail(descriptor):
            real_close(descriptor)
            raise OSError("test-only close failure")

        try:
            with mock.patch.object(
                v064_public_ci_witness_cli.os,
                "read",
                side_effect=OSError("test-only read failure"),
            ), mock.patch.object(
                v064_public_ci_witness_cli.os,
                "close",
                side_effect=close_then_fail,
            ):
                with self.assertRaisesRegex(
                    ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_IO_FAILED"
                ) as captured:
                    v064_public_ci_witness_cli._read_named(
                        root_fd, name, self.prepared[name]
                    )
            self.assertEqual(
                captured.exception.close_error,
                "V064_PUBLIC_CI_R3_EVIDENCE_CLOSE_FAILED",
            )
        finally:
            real_close(root_fd)

    def test_staging_primary_failure_is_preserved_when_close_fails(self):
        real_close = os.close
        close_calls = 0

        def close_staging_then_fail(descriptor):
            nonlocal close_calls
            close_calls += 1
            real_close(descriptor)
            if close_calls == 2:
                raise OSError("test-only staging close failure")

        with mock.patch.object(
            v064_public_ci_witness_cli,
            "_write_all",
            side_effect=ValueError("V064_PUBLIC_CI_R3_EVIDENCE_IO_FAILED"),
        ), mock.patch.object(
            v064_public_ci_witness_cli.os,
            "close",
            side_effect=close_staging_then_fail,
        ):
            with self.assertRaisesRegex(
                ValueError, "V064_PUBLIC_CI_R3_EVIDENCE_IO_FAILED"
            ) as captured:
                v064_public_ci_witness_cli._publish_evidence(self.prepared)
        self.assertEqual(
            captured.exception.close_error,
            "V064_PUBLIC_CI_R3_EVIDENCE_CLOSE_FAILED",
        )

    def test_successful_cli_derives_and_publishes_only_five_fixed_files(self):
        capture = {
            "raw": {
                "run_api": b'{"run":1}\n',
                "jobs_api": b'{"jobs":2}\n',
                "run_log": b"exact log\n",
            },
            "raw_stderr": {"run_api": b"", "jobs_api": b"", "run_log": b""},
            "transcript": {"schema_version": "1.0.0", "commands": []},
        }
        bundle = {"bundle": "exact"}
        witness = {"witness": "exact"}
        output = io.StringIO()
        with mock.patch.object(
            v064_public_ci_witness_cli, "_capture", return_value=capture
        ), mock.patch(
            "crypto_quant.v064_public_ci_bundle.load_v064_public_ci_bundle_manifest",
            return_value=bundle,
        ) as load, mock.patch(
            "crypto_quant.v064_public_ci_witness.derive_v064_public_ci_witness",
            return_value=witness,
        ) as derive, mock.patch.object(sys, "stdout", output):
            result = v064_public_ci_witness_cli.main(("--run-id", "123"))
        self.assertEqual(result, 0)
        load.assert_called_once_with(
            Path("/private/tmp/crypto-quant-v064-public-ci-r3-candidate/bundle-manifest-v1.json")
        )
        derive.assert_called_once_with(
            bundle=bundle,
            run_bytes=capture["raw"]["run_api"],
            jobs_bytes=capture["raw"]["jobs_api"],
            log_bytes=capture["raw"]["run_log"],
            transcript=capture["transcript"],
            private_repository=self.repository,
        )
        expected = dict(self.prepared)
        expected["v064-public-ci-r3-acquisition-transcript-v1.json"] = _canonical(
            capture["transcript"]
        )
        expected["v064-public-ci-r3-witness-v1.json"] = _canonical(witness)
        for name, body in expected.items():
            self.assertEqual((self.output / name).read_bytes(), body)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary["status"], "V064_PUBLIC_CI_R3_EVIDENCE_PUBLISHED")

    def test_cli_acquisition_validation_and_unsuccessful_run_create_zero_files(self):
        with mock.patch.object(
            v064_public_ci_witness_cli,
            "_capture",
            side_effect=ValueError("V064_PUBLIC_CI_GH_COMMAND_FAILED"),
        ):
            with self.assertRaisesRegex(ValueError, "GH_COMMAND_FAILED"):
                v064_public_ci_witness_cli.main(("--run-id", "123"))
        self.assertFalse(self.output.exists())

        failed = {
            "raw": {"run_api": b"{}\n", "jobs_api": b"{}\n", "run_log": b"x"},
            "raw_stderr": {"run_api": b"", "jobs_api": b"", "run_log": b""},
            "transcript": {
                "schema_version": "1.0.0",
                "commands": [{"exit_code": 1}],
            },
        }
        with mock.patch.object(
            v064_public_ci_witness_cli, "_capture", return_value=failed
        ), mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(
                v064_public_ci_witness_cli.main(("--run-id", "123")), 2
            )
        self.assertFalse(self.output.exists())

        stderr_capture = copy.deepcopy(failed)
        stderr_capture["transcript"]["commands"][0]["exit_code"] = 0
        stderr_capture["raw_stderr"]["jobs_api"] = b"unexpected stderr\n"
        with mock.patch.object(
            v064_public_ci_witness_cli, "_capture", return_value=stderr_capture
        ), mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(
                v064_public_ci_witness_cli.main(("--run-id", "123")), 2
            )
        self.assertFalse(self.output.exists())

        valid_capture = copy.deepcopy(failed)
        valid_capture["transcript"]["commands"][0]["exit_code"] = 0
        with mock.patch.object(
            v064_public_ci_witness_cli, "_capture", return_value=valid_capture
        ), mock.patch(
            "crypto_quant.v064_public_ci_bundle.load_v064_public_ci_bundle_manifest",
            side_effect=ValueError("V064_PUBLIC_CI_BUNDLE_INVALID"),
        ):
            with self.assertRaisesRegex(ValueError, "BUNDLE_INVALID"):
                v064_public_ci_witness_cli.main(("--run-id", "123"))
        self.assertFalse(self.output.exists())

        with mock.patch.object(
            v064_public_ci_witness_cli, "_capture", return_value=valid_capture
        ), mock.patch(
            "crypto_quant.v064_public_ci_bundle.load_v064_public_ci_bundle_manifest",
            return_value={"bundle": "exact"},
        ), mock.patch(
            "crypto_quant.v064_public_ci_witness.derive_v064_public_ci_witness",
            side_effect=ValueError("V064_PUBLIC_CI_WITNESS_INVALID"),
        ):
            with self.assertRaisesRegex(ValueError, "WITNESS_INVALID"):
                v064_public_ci_witness_cli.main(("--run-id", "123"))
        self.assertFalse(self.output.exists())

        with mock.patch.object(
            v064_public_ci_witness_cli, "_capture", return_value=valid_capture
        ), mock.patch(
            "crypto_quant.v064_public_ci_bundle.load_v064_public_ci_bundle_manifest",
            return_value={"bundle": "exact"},
        ), mock.patch(
            "crypto_quant.v064_public_ci_witness.derive_v064_public_ci_witness",
            return_value={"witness": "exact"},
        ), mock.patch.object(
            v064_public_ci_witness_cli,
            "_validate_repository_identity",
            side_effect=ValueError("V064_PUBLIC_CI_R3_REPOSITORY_INVALID"),
        ):
            with self.assertRaisesRegex(ValueError, "REPOSITORY_INVALID"):
                v064_public_ci_witness_cli.main(("--run-id", "123"))
        self.assertFalse(self.output.exists())


class V064PublicCiR2CommittedArtifactTests(unittest.TestCase):
    ROOT = ROOT / "artifacts" / "v064-public-ci-r2"
    NAMES = (
        "v064-public-ci-r2-run-api-v1.json",
        "v064-public-ci-r2-jobs-api-v1.json",
        "v064-public-ci-r2-run-log-v1.txt",
        "v064-public-ci-r2-acquisition-transcript-v1.json",
        "v064-public-ci-r2-witness-v1.json",
    )

    def _loaded_witness(self):
        try:
            entries = tuple(sorted(path.name for path in self.ROOT.iterdir()))
        except FileNotFoundError:
            entries = ()
        if not entries:
            self.skipTest("V064_PUBLIC_CI_R2_FORMAL_ARTIFACTS_NOT_YET_PUBLISHED")
        self.assertEqual(entries, tuple(sorted(self.NAMES)), "R2 evidence set is not exact")
        return load_v064_public_ci_witness(
            self.ROOT / "v064-public-ci-r2-witness-v1.json"
        )

    def _read_formal(self, name):
        path = self.ROOT / name
        before = path.lstat()
        descriptor = os.open(
            path,
            os.O_RDONLY
            | v064_public_ci_witness_cli._required_flag("O_NOFOLLOW")
            | v064_public_ci_witness_cli._required_flag("O_NONBLOCK"),
        )
        try:
            opened = os.fstat(descriptor)
            self.assertTrue(stat.S_ISREG(opened.st_mode))
            self.assertEqual(opened.st_uid, os.geteuid())
            self.assertEqual(opened.st_nlink, 1)
            self.assertIn(stat.S_IMODE(opened.st_mode), (0o600, 0o644))
            self.assertGreater(opened.st_size, 0)
            self.assertLessEqual(opened.st_size, 64 * 1024 * 1024)
            self.assertEqual(
                (before.st_dev, before.st_ino), (opened.st_dev, opened.st_ino)
            )
            body = v064_public_ci_witness_cli._read_descriptor(
                descriptor, opened.st_size
            )
            attached = path.lstat()
            after = os.fstat(descriptor)
            self.assertEqual(
                (attached.st_dev, attached.st_ino),
                (opened.st_dev, opened.st_ino),
            )
            self.assertEqual(
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns),
            )
            return body
        finally:
            os.close(descriptor)

    def _assert_raw(self, key, name, require_canonical):
        witness = self._loaded_witness()
        body = self._read_formal(name)
        self.assertEqual(witness["raw_evidence"][key]["size"], len(body))
        self.assertEqual(
            witness["raw_evidence"][key]["sha256"],
            hashlib.sha256(body).hexdigest(),
        )
        self.assertEqual(
            witness["raw_evidence"][key]["path"],
            "artifacts/v064-public-ci-r2/" + name,
        )
        if require_canonical:
            self.assertEqual(_canonical(json.loads(body)), body)

    def test_committed_run_api_replays_or_exact_set_is_absent(self):
        self._assert_raw("run_api", self.NAMES[0], True)

    def test_committed_jobs_api_replays_or_exact_set_is_absent(self):
        self._assert_raw("jobs_api", self.NAMES[1], True)

    def test_committed_run_log_replays_or_exact_set_is_absent(self):
        self._assert_raw("run_log", self.NAMES[2], False)

    def test_committed_transcript_replays_or_exact_set_is_absent(self):
        self._assert_raw("acquisition_transcript", self.NAMES[3], True)

    def test_committed_witness_replays_or_exact_set_is_absent(self):
        witness = self._loaded_witness()
        self._read_formal(self.NAMES[4])
        self.assertEqual(witness["schema_version"], "1.1.0")
        self.assertEqual(
            witness["predecessor_failed_public_witness"],
            PREDECESSOR_FAILED_PUBLIC_WITNESS,
        )


class V064PublicCiR2CommittedArtifactBoundaryTests(unittest.TestCase):
    def test_extra_or_partial_inventory_is_never_an_all_absent_skip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate = V064PublicCiR2CommittedArtifactTests(
                "test_committed_witness_replays_or_exact_set_is_absent"
            )
            with mock.patch.object(gate, "ROOT", root):
                extra = root / "unexpected"
                extra.write_bytes(b"sentinel\n")
                with self.assertRaisesRegex(AssertionError, "not exact"):
                    gate._loaded_witness()
                extra.unlink()
                first = root / gate.NAMES[0]
                first.write_bytes(b"{}\n")
                first.chmod(0o600)
                with self.assertRaisesRegex(AssertionError, "not exact"):
                    gate._loaded_witness()

    def test_formal_fifo_is_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate = V064PublicCiR2CommittedArtifactTests(
                "test_committed_run_api_replays_or_exact_set_is_absent"
            )
            fifo = root / gate.NAMES[0]
            os.mkfifo(fifo, 0o600)
            with mock.patch.object(gate, "ROOT", root):
                started = time.monotonic()
                with self.assertRaises(AssertionError):
                    gate._read_formal(gate.NAMES[0])
                self.assertLess(time.monotonic() - started, 1.0)


class V064PublicCiR3CommittedArtifactTests(unittest.TestCase):
    ROOT = ROOT / "artifacts" / "v064-public-ci-r3"
    SOURCE_F3 = "f9705fa2151ab98a5b9efe63be05979e4bc5bfa6"
    NAMES = (
        "v064-public-ci-r3-run-api-v1.json",
        "v064-public-ci-r3-jobs-api-v1.json",
        "v064-public-ci-r3-run-log-v1.txt",
        "v064-public-ci-r3-acquisition-transcript-v1.json",
        "v064-public-ci-r3-witness-v1.json",
    )
    EXACT_FILES = {
        NAMES[0]: (
            363,
            "e617d41ea4e09215ef917160f1ac39c94224040582a2029c339481a05535a70b",
        ),
        NAMES[1]: (
            2312,
            "6b752ccefd77281542ba603eded94f0d459a7d4f86bfe2a623893dbb200bc7fa",
        ),
        NAMES[2]: (
            106671,
            "6b8fd0fb32f7c060b06805151e63417bbac66cb253ed647b2be11fc66313d1ef",
        ),
        NAMES[3]: (
            1698,
            "1dd8cd4a5920bdade465c655f6f8a59c6b62adae1b62f7f93b09c1a385e790da",
        ),
        NAMES[4]: (
            8860,
            "2b6d8639baab5d637605f62e92f0ab217681d25b29c7b90e4f754fd42f52c1d2",
        ),
    }

    def _read_formal(self, name):
        path = self.ROOT / name
        descriptor = None
        try:
            before = path.lstat()
            descriptor = os.open(
                path,
                os.O_RDONLY
                | v064_public_ci_witness_cli._required_flag("O_NOFOLLOW")
                | v064_public_ci_witness_cli._required_flag("O_NONBLOCK"),
            )
            opened = os.fstat(descriptor)
            self.assertTrue(stat.S_ISREG(opened.st_mode))
            self.assertEqual(opened.st_uid, os.geteuid())
            self.assertEqual(opened.st_nlink, 1)
            self.assertIn(stat.S_IMODE(opened.st_mode), (0o600, 0o644))
            self.assertGreater(opened.st_size, 0)
            self.assertLessEqual(opened.st_size, 64 * 1024 * 1024)
            self.assertEqual(
                (before.st_dev, before.st_ino), (opened.st_dev, opened.st_ino)
            )
            body = v064_public_ci_witness_cli._read_descriptor(
                descriptor, opened.st_size
            )
            attached = path.lstat()
            after = os.fstat(descriptor)
            self.assertEqual(
                (attached.st_dev, attached.st_ino),
                (opened.st_dev, opened.st_ino),
            )
            self.assertEqual(
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns),
            )
            return body
        except OSError as error:
            raise AssertionError("R3 formal artifact is not trusted") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _archive(self):
        try:
            root_stat = self.ROOT.lstat()
            entries = tuple(sorted(path.name for path in self.ROOT.iterdir()))
        except FileNotFoundError as error:
            raise AssertionError("R3 evidence set is required") from error
        self.assertTrue(stat.S_ISDIR(root_stat.st_mode))
        self.assertEqual(root_stat.st_uid, os.geteuid())
        self.assertFalse(stat.S_IMODE(root_stat.st_mode) & 0o022)
        self.assertEqual(
            entries, tuple(sorted(self.NAMES)), "R3 evidence set is not exact"
        )
        bodies = {name: self._read_formal(name) for name in self.NAMES}
        for name, (size, sha256) in self.EXACT_FILES.items():
            with self.subTest(name=name):
                self.assertEqual(len(bodies[name]), size)
                self.assertEqual(hashlib.sha256(bodies[name]).hexdigest(), sha256)
        return bodies

    def _witness(self):
        self._archive()
        return load_v064_public_ci_witness(self.ROOT / self.NAMES[4])

    def test_exact_five_entry_inventory_and_literal_file_identities(self):
        self._archive()

    def test_production_loader_replays_canonical_witness(self):
        witness_body = self._archive()[self.NAMES[4]]
        witness = self._witness()
        self.assertEqual(_canonical(witness), witness_body)
        self.assertEqual(
            witness["witness_id"],
            "v064_public_ci_witness_73d6a8bbd96a3705613924f34e464204a138320211f4f206160accf487f715da",
        )
        self.assertEqual(
            witness["witness_hash"],
            "f90c46551bf08b4b22509c0946576359cfa9186494c7925ef292639629c1a32a",
        )

    def test_raw_paths_sizes_hashes_and_canonical_json_are_bound(self):
        bodies = self._archive()
        witness = self._witness()
        raw_names = {
            "run_api": self.NAMES[0],
            "jobs_api": self.NAMES[1],
            "run_log": self.NAMES[2],
            "acquisition_transcript": self.NAMES[3],
        }
        for key, name in raw_names.items():
            with self.subTest(key=key):
                size, sha256 = self.EXACT_FILES[name]
                self.assertEqual(
                    witness["raw_evidence"][key],
                    {
                        "path": "artifacts/v064-public-ci-r3/" + name,
                        "size": size,
                        "sha256": sha256,
                    },
                )
        for name in (self.NAMES[0], self.NAMES[1], self.NAMES[3], self.NAMES[4]):
            with self.subTest(canonical=name):
                self.assertEqual(_canonical(json.loads(bodies[name])), bodies[name])

    def test_transcript_is_canonical_and_binds_exact_raw_outputs(self):
        bodies = self._archive()
        transcript = json.loads(bodies[self.NAMES[3]])
        self.assertEqual(_canonical(transcript), bodies[self.NAMES[3]])
        self.assertEqual(
            tuple(tuple(record["argv"]) for record in transcript["commands"]),
            v064_public_ci_witness_cli._commands(32435172937),
        )
        for record, name in zip(transcript["commands"], self.NAMES[:3]):
            with self.subTest(command=record["name"]):
                size, sha256 = self.EXACT_FILES[name]
                self.assertEqual(record["exit_code"], 0)
                self.assertEqual(record["stdout_size"], size)
                self.assertEqual(record["stdout_sha256"], sha256)
                self.assertEqual(record["stderr_size"], 0)
                self.assertEqual(
                    record["stderr_sha256"], hashlib.sha256(b"").hexdigest()
                )

    def test_exact_private_public_run_and_job_identities_are_frozen(self):
        witness = self._witness()
        self.assertEqual(
            witness["private_source"],
            {
                "repository": "cjl308868584-lang/crypto-quant-core",
                "candidate_commit": self.SOURCE_F3,
                "candidate_tree": "c3ed7d9a506d2a3c1531b0cb979a564f52991145",
                "object_format": "sha1",
                "historical_billing_blocked_private_pr": {
                    "number": 32,
                    "run_id": 31436609135,
                    "status": "PRIVATE_PR_CI_NOT_EXECUTED_BILLING_BLOCKED",
                },
            },
        )
        self.assertEqual(
            witness["public_source"],
            {
                "repository": "cjl308868584-lang/crypto-quant-v064-public-ci-r3",
                "commit": "460ec57568e863b2e39e7572193f2545542d586b",
                "tree": "2ab63c4fdecb06d0a4498365b9debd53a122a2ba",
                "branch": "main",
                "parent_count": 0,
            },
        )
        self.assertEqual(
            witness["run"],
            {
                "run_id": 32435172937,
                "workflow_id": 339016620,
                "run_attempt": 1,
                "event": "push",
                "head_branch": "main",
                "head_sha": "460ec57568e863b2e39e7572193f2545542d586b",
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-08-21T01:07:15Z",
                "updated_at": "2026-08-21T01:07:32Z",
            },
        )
        self.assertEqual(
            [(job["python_version"], job["job_id"]) for job in witness["jobs"]],
            [("3.9", 96634805095), ("3.12", 96634805278)],
        )

    def test_distinct_setup_and_fixed_owner_interpreters_are_exact(self):
        jobs = self._witness()["jobs"]
        self.assertEqual(
            [
                (
                    job["python_version"],
                    job["setup_python_version"],
                    job["fixed_owner_python_version"],
                )
                for job in jobs
            ],
            [("3.9", "3.9.25", "3.9.25"), ("3.12", "3.12.14", "3.12.14")],
        )
        self.assertEqual(len({job["fixed_owner_python_version"] for job in jobs}), 2)

    def test_all_safety_authorities_are_false_and_nonclaims_are_exact(self):
        witness = self._witness()
        self.assertEqual(
            witness["safety"],
            {
                "production_activation": False,
                "credentials_present": False,
                "broker_allowed": False,
                "orders_allowed": False,
                "runtime_state_write_allowed": False,
            },
        )
        self.assertEqual(
            witness["non_claims"],
            [
                "NOT_FULL_PROJECT_CI",
                "NOT_PRIVATE_PR_CHECK",
                "NOT_STRATEGY_CORRECTNESS_EVIDENCE",
                "NOT_PROFITABILITY_OR_AI_ADVANTAGE_EVIDENCE",
                "NOT_PAPER_CANARY_OR_LIVE_TRADING_AUTHORIZATION",
            ],
        )

    def test_production_derivation_replays_all_exact_evidence_from_f3(self):
        bodies = self._archive()
        witness = self._witness()
        transcript = json.loads(bodies[self.NAMES[3]])
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary).resolve()
            source = temporary_root / "source-f3"
            subprocess.run(
                (
                    "/usr/bin/git", "clone", "--no-hardlinks", "-q",
                    str(ROOT), str(source),
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            subprocess.run(
                ("/usr/bin/git", "-C", str(source), "checkout", "-q", self.SOURCE_F3),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            public_root = temporary_root / "public-candidate"
            bundle = stage_v064_public_ci_bundle(source, self.SOURCE_F3, public_root)
            with mock.patch.object(v064_public_ci_witness, "_PUBLIC_ROOT", public_root):
                replayed = derive_v064_public_ci_witness(
                    bundle=bundle,
                    run_bytes=bodies[self.NAMES[0]],
                    jobs_bytes=bodies[self.NAMES[1]],
                    log_bytes=bodies[self.NAMES[2]],
                    transcript=transcript,
                    private_repository=source,
                )
        self.assertEqual(replayed, witness)


class V064PublicCiR3CommittedArtifactBoundaryTests(unittest.TestCase):
    def _gate(self, root):
        gate = V064PublicCiR3CommittedArtifactTests(
            "test_exact_five_entry_inventory_and_literal_file_identities"
        )
        gate.ROOT = root
        return gate

    def test_missing_partial_extra_and_tampered_archives_fail_closed(self):
        source_gate = self._gate(V064PublicCiR3CommittedArtifactTests.ROOT)
        exact_bodies = {
            name: source_gate._read_formal(name) for name in source_gate.NAMES
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "archive"
            gate = self._gate(root)
            with self.assertRaisesRegex(AssertionError, "required"):
                gate._archive()
            root.mkdir(mode=0o700)
            first = root / gate.NAMES[0]
            first.write_bytes(exact_bodies[gate.NAMES[0]])
            first.chmod(0o600)
            with self.assertRaisesRegex(AssertionError, "not exact"):
                gate._archive()
            for name, body in exact_bodies.items():
                path = root / name
                if not path.exists():
                    path.write_bytes(body)
                    path.chmod(0o600)
            extra = root / "unexpected"
            extra.write_bytes(b"sentinel\n")
            extra.chmod(0o600)
            with self.assertRaisesRegex(AssertionError, "not exact"):
                gate._archive()
            extra.unlink()
            first.write_bytes(exact_bodies[gate.NAMES[0]] + b" ")
            with self.assertRaises(AssertionError):
                gate._archive()

    def test_symlink_hardlink_fifo_and_directory_entries_fail_closed(self):
        source_gate = self._gate(V064PublicCiR3CommittedArtifactTests.ROOT)
        target_body = source_gate._read_formal(source_gate.NAMES[0])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "target"
            target.write_bytes(target_body)
            target.chmod(0o600)
            for kind in ("symlink", "hardlink", "fifo", "directory"):
                with self.subTest(kind=kind):
                    formal = root / source_gate.NAMES[0]
                    if kind == "symlink":
                        formal.symlink_to(target)
                    elif kind == "hardlink":
                        os.link(target, formal)
                    elif kind == "fifo":
                        os.mkfifo(formal, 0o600)
                    else:
                        formal.mkdir(mode=0o700)
                    started = time.monotonic()
                    gate = self._gate(root)
                    with self.assertRaises(AssertionError):
                        gate._read_formal(gate.NAMES[0])
                    self.assertLess(time.monotonic() - started, 1.0)
                    if formal.is_dir() and not formal.is_symlink():
                        formal.rmdir()
                    else:
                        formal.unlink()

    def test_canonical_witness_tamper_is_rejected_by_production_loader(self):
        source = (
            V064PublicCiR3CommittedArtifactTests.ROOT
            / V064PublicCiR3CommittedArtifactTests.NAMES[4]
        )
        changed = json.loads(source.read_text(encoding="utf-8"))
        changed["safety"]["orders_allowed"] = True
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "tampered-witness.json"
            path.write_bytes(_canonical(changed))
            path.chmod(0o600)
            with self.assertRaises(V064PublicCiWitnessError):
                load_v064_public_ci_witness(path)


class V064PublicCiWitnessFixedIdentityTests(unittest.TestCase):
    def test_repository_identity_uses_raw_module_ancestry_and_rejects_symlink(self):
        self.assertEqual(
            v064_public_ci_witness_cli._PRIVATE_REPOSITORY,
            Path(v064_public_ci_witness_cli.__file__).absolute().parents[2],
        )
        self.assertEqual(
            v064_public_ci_witness_cli._ARTIFACT_ROOT,
            v064_public_ci_witness_cli._PRIVATE_REPOSITORY
            / "artifacts"
            / "v064-public-ci-r3",
        )
        v064_public_ci_witness_cli._validate_repository_identity()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "module.py"
            target.write_bytes(b"module\n")
            link = root / "linked.py"
            link.symlink_to(target)
            with mock.patch.object(v064_public_ci_witness_cli, "__file__", str(link)):
                with self.assertRaisesRegex(
                    ValueError, "V064_PUBLIC_CI_R3_REPOSITORY_INVALID"
                ):
                    v064_public_ci_witness_cli._validate_repository_identity()


class V064PublicCiWitnessAncestryTests(unittest.TestCase):
    R3_EVIDENCE_PATHS = (
        "artifacts/v064-public-ci-r3/v064-public-ci-r3-run-api-v1.json",
        "artifacts/v064-public-ci-r3/v064-public-ci-r3-jobs-api-v1.json",
        "artifacts/v064-public-ci-r3/v064-public-ci-r3-run-log-v1.txt",
        "artifacts/v064-public-ci-r3/v064-public-ci-r3-acquisition-transcript-v1.json",
        "artifacts/v064-public-ci-r3/v064-public-ci-r3-witness-v1.json",
    )
    OBSOLETE_EVIDENCE_PATHS = (
        "artifacts/v064-public-ci/v064-public-ci-run-api-v1.json",
        "artifacts/v064-public-ci/v064-public-ci-jobs-api-v1.json",
        "artifacts/v064-public-ci/v064-public-ci-run-log-v1.txt",
        "artifacts/v064-public-ci/v064-public-ci-acquisition-transcript-v1.json",
        "artifacts/v064-public-ci/v064-public-ci-witness-v1.json",
    )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name) / "repository"
        self.repository.mkdir()
        self._git("init", "-q")
        self._git("config", "user.name", "fixture")
        self._git("config", "user.email", "fixture@example.invalid")
        self.sources = (
            "public_ci/v064/.github/workflows/ci.yml",
            "public_ci/v064/.gitignore",
            "public_ci/v064/NOTICE.md",
            "public_ci/v064/README.md",
            "public_ci/v064/SECURITY.md",
            "src/crypto_quant/challenger_replacement_supersession_publish.py",
            "tests/test_v064_linux_supersession_publish.py",
        )
        for index, relative in enumerate(self.sources):
            path = self.repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("source-%d\n" % index).encode())
        self._git("add", "--", *self.sources)
        self._git("commit", "-q", "-m", "F")
        self.source_f = self._git("rev-parse", "HEAD").decode().strip()
        public_paths = (
            ".github/workflows/ci.yml", ".gitignore", "NOTICE.md", "README.md",
            "SECURITY.md", "src/crypto_quant/challenger_replacement_supersession_publish.py",
            "tests/test_v064_linux_supersession_publish.py",
        )
        self.manifest = {
            "source": {"candidate_commit": self.source_f},
            "files": [
                {
                    "path": public,
                    "source_blob_oid": self._git(
                        "rev-parse", "%s:%s" % (self.source_f, private)
                    ).decode().strip(),
                }
                for public, private in zip(public_paths, self.sources)
            ],
        }

    def tearDown(self):
        self.temporary.cleanup()

    def _git(self, *arguments):
        return subprocess.run(
            ("/usr/bin/git", "-C", str(self.repository), *arguments),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        ).stdout

    def _commit_allowed_g(self):
        allowed = self.repository / "tests/test_v064_public_ci_witness.py"
        allowed.parent.mkdir(parents=True, exist_ok=True)
        allowed.write_bytes(b"formal witness regression\n")
        self._git("add", "--", str(allowed.relative_to(self.repository)))
        self._git("commit", "-q", "-m", "G")
        return self._git("rev-parse", "HEAD").decode().strip()

    def _commit_paths(self, paths, message):
        for index, relative in enumerate(paths):
            path = self.repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("evidence-%d\n" % index).encode("ascii"))
        self._git("add", "--", *paths)
        self._git("commit", "-q", "-m", message)
        return self._git("rev-parse", "HEAD").decode().strip()

    def test_strict_descendant_with_exact_allowed_delta_and_unchanged_sources_passes(self):
        candidate_g = self._commit_allowed_g()
        result = verify_v064_public_source_unchanged(
            self.repository, self.source_f, candidate_g, self.manifest
        )
        self.assertEqual(result["status"], "V064_PUBLIC_SOURCE_UNCHANGED")
        self.assertEqual(result["verified_blob_count"], 7)

    def test_exact_five_r3_evidence_paths_are_accepted_by_real_git_delta(self):
        candidate_g = self._commit_paths(self.R3_EVIDENCE_PATHS, "R3 evidence")
        result = verify_v064_public_source_unchanged(
            self.repository, self.source_f, candidate_g, self.manifest
        )
        self.assertEqual(
            result["allowed_delta_paths"], sorted(self.R3_EVIDENCE_PATHS)
        )

    def test_each_obsolete_evidence_path_is_rejected_by_real_git_delta(self):
        for obsolete in self.OBSOLETE_EVIDENCE_PATHS:
            with self.subTest(path=obsolete):
                self._git("reset", "--hard", self.source_f)
                candidate_g = self._commit_paths((obsolete,), "obsolete evidence")
                with self.assertRaisesRegex(
                    V064PublicCiWitnessError, "PUBLIC_SOURCE_DELTA_INVALID"
                ):
                    verify_v064_public_source_unchanged(
                        self.repository, self.source_f, candidate_g, self.manifest
                    )

    def test_equal_nondescendant_source_change_and_unexpected_delta_fail_closed(self):
        with self.assertRaisesRegex(V064PublicCiWitnessError, "SOURCE_F_INVALID"):
            verify_v064_public_source_unchanged(
                self.repository, "HEAD", self.source_f, self.manifest
            )
        duplicated = copy.deepcopy(self.manifest)
        duplicated["files"].append(copy.deepcopy(duplicated["files"][0]))
        with self.assertRaisesRegex(V064PublicCiWitnessError, "MANIFEST_INVALID"):
            verify_v064_public_source_unchanged(
                self.repository, self.source_f, self._commit_allowed_g(), duplicated
            )

        with self.assertRaises(V064PublicCiWitnessError):
            verify_v064_public_source_unchanged(
                self.repository, self.source_f, self.source_f, self.manifest
            )

        changed = self.repository / self.sources[0]
        changed.write_bytes(b"changed source\n")
        self._git("add", "--", self.sources[0])
        self._git("commit", "-q", "-m", "bad source")
        with self.assertRaisesRegex(V064PublicCiWitnessError, "PUBLIC_SOURCE_BLOB_CHANGED"):
            verify_v064_public_source_unchanged(
                self.repository, self.source_f,
                self._git("rev-parse", "HEAD").decode().strip(), self.manifest,
            )

        self._git("reset", "--hard", self.source_f)
        unexpected = self.repository / "unexpected.txt"
        unexpected.write_bytes(b"unexpected\n")
        self._git("add", "unexpected.txt")
        self._git("commit", "-q", "-m", "unexpected")
        with self.assertRaisesRegex(V064PublicCiWitnessError, "PUBLIC_SOURCE_DELTA_INVALID"):
            verify_v064_public_source_unchanged(
                self.repository, self.source_f,
                self._git("rev-parse", "HEAD").decode().strip(), self.manifest,
            )
