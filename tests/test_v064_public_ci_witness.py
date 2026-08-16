import copy
import hashlib
import inspect
import json
import os
import subprocess
import sys
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, ValidationError

from crypto_quant.canonical import canonical_json
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


def _raw(path, fill):
    return {"path": path, "size": 123, "sha256": fill * 64}


def _job(python_version, job_id):
    return {
        "python_version": python_version,
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
        "schema_version": "1.1.0",
        "witness_id": "v064_public_ci_witness_" + "1" * 64,
        "witness_hash": "2" * 64,
        "status": "PUBLIC_LINUX_PORTABILITY_WITNESS_COMPLETED",
        "predecessor_failed_public_witness": copy.deepcopy(
            PREDECESSOR_FAILED_PUBLIC_WITNESS
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
            "repository": "cjl308868584-lang/crypto-quant-v064-public-ci-r2",
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
                "artifacts/v064-public-ci-r2/v064-public-ci-r2-run-api-v1.json", "b"
            ),
            "jobs_api": _raw(
                "artifacts/v064-public-ci-r2/v064-public-ci-r2-jobs-api-v1.json", "c"
            ),
            "run_log": _raw(
                "artifacts/v064-public-ci-r2/v064-public-ci-r2-run-log-v1.txt", "d"
            ),
            "acquisition_transcript": _raw(
                "artifacts/v064-public-ci-r2/v064-public-ci-r2-acquisition-transcript-v1.json",
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

    def test_witness_requires_exact_predecessor_failed_public_witness(self):
        schema = self.schema()
        validator = Draft202012Validator(schema)

        missing = copy.deepcopy(valid_witness())
        del missing["predecessor_failed_public_witness"]
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
            changed["predecessor_failed_public_witness"][key] = replacement
            with self.subTest(field=key), self.assertRaises(ValidationError):
                validator.validate(changed)

        for index, job in enumerate(predecessor["jobs"]):
            for key, original in job.items():
                changed = copy.deepcopy(valid_witness())
                replacement = original + 1 if isinstance(original, int) else "wrong"
                changed["predecessor_failed_public_witness"]["jobs"][index][key] = replacement
                with self.subTest(job=index, field=key), self.assertRaises(ValidationError):
                    validator.validate(changed)

        structural_mutations = []
        extra = copy.deepcopy(valid_witness())
        extra["predecessor_failed_public_witness"]["unexpected"] = True
        structural_mutations.append(extra)
        reordered = copy.deepcopy(valid_witness())
        reordered["predecessor_failed_public_witness"]["jobs"].reverse()
        structural_mutations.append(reordered)
        duplicate = copy.deepcopy(valid_witness())
        duplicate["predecessor_failed_public_witness"]["jobs"][1] = copy.deepcopy(
            duplicate["predecessor_failed_public_witness"]["jobs"][0]
        )
        structural_mutations.append(duplicate)
        unsafe = copy.deepcopy(valid_witness())
        unsafe["predecessor_failed_public_witness"]["run_id"] = 2**53
        structural_mutations.append(unsafe)
        long_oid = copy.deepcopy(valid_witness())
        long_oid["predecessor_failed_public_witness"]["public_commit"] = "f" * 64
        structural_mutations.append(long_oid)
        uppercase_hash = copy.deepcopy(valid_witness())
        uppercase_hash["predecessor_failed_public_witness"]["run_log_sha256"] = "A" * 64
        structural_mutations.append(uppercase_hash)
        for changed in structural_mutations:
            with self.assertRaises(ValidationError):
                validator.validate(changed)

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
        "repository": "cjl308868584-lang/crypto-quant-v064-public-ci-r2",
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
    for version in ("3.9", "3.12"):
        verify_prefix = (
            "portability (%s)\tVerify closed bundle before repository imports\t"
            "2026-08-13T01:01:02.1234567Z "
        ) % version
        run_prefix = (
            "portability (%s)\tRun fixed-owner public boundary\t"
            "2026-08-13T01:02:03.1234567Z "
        ) % version
        lines.extend(verify_prefix + marker for marker in markers)
        lines.extend((
            run_prefix + "Python " + version + ".19",
            run_prefix + "Ran 16 tests in 0.735s",
            run_prefix + "OK",
        ))
    log = ("\n".join(lines) + "\n").encode("utf-8")
    bundle = {
        "predecessor_failed_public_witness": copy.deepcopy(
            PREDECESSOR_FAILED_PUBLIC_WITNESS
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
        self.assertEqual(witness["schema_version"], "1.1.0")
        self.assertEqual(
            witness["predecessor_failed_public_witness"],
            PREDECESSOR_FAILED_PUBLIC_WITNESS,
        )
        self.assertEqual(
            witness["public_source"]["repository"],
            "cjl308868584-lang/crypto-quant-v064-public-ci-r2",
        )
        replay.assert_called_once_with(ROOT, bundle)

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
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            path = raw_root / "witness.json"
            path.write_bytes(_canonical(witness)); path.chmod(0o600)
            self.assertEqual(load_v064_public_ci_witness(path), witness)
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


class V064PublicCiWitnessAncestryTests(unittest.TestCase):
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

    def test_strict_descendant_with_exact_allowed_delta_and_unchanged_sources_passes(self):
        candidate_g = self._commit_allowed_g()
        result = verify_v064_public_source_unchanged(
            self.repository, self.source_f, candidate_g, self.manifest
        )
        self.assertEqual(result["status"], "V064_PUBLIC_SOURCE_UNCHANGED")
        self.assertEqual(result["verified_blob_count"], 7)

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
