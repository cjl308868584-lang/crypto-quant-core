import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "config" / "v064-public-ci-witness-v1.schema.json"
PACKAGE_SCHEMA = (
    ROOT / "src" / "crypto_quant" / "schemas" / "v064-public-ci-witness-v1.schema.json"
)


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
        "schema_version": "1.0.0",
        "witness_id": "v064_public_ci_witness_" + "1" * 64,
        "witness_hash": "2" * 64,
        "status": "PUBLIC_LINUX_PORTABILITY_WITNESS_COMPLETED",
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
            "repository": "cjl308868584-lang/crypto-quant-v064-public-ci",
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
                "artifacts/v064-public-ci/v064-public-ci-run-api-v1.json", "b"
            ),
            "jobs_api": _raw(
                "artifacts/v064-public-ci/v064-public-ci-jobs-api-v1.json", "c"
            ),
            "run_log": _raw(
                "artifacts/v064-public-ci/v064-public-ci-run-log-v1.txt", "d"
            ),
            "acquisition_transcript": _raw(
                "artifacts/v064-public-ci/v064-public-ci-acquisition-transcript-v1.json",
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
