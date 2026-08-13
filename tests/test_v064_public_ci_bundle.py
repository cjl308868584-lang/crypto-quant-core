import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "config" / "v064-public-ci-bundle-manifest-v1.schema.json"
PACKAGE_SCHEMA = (
    ROOT
    / "src"
    / "crypto_quant"
    / "schemas"
    / "v064-public-ci-bundle-manifest-v1.schema.json"
)


def _file(path, source_kind):
    return {
        "path": path,
        "size": 123,
        "sha256": "1" * 64,
        "source_kind": source_kind,
        "source_blob_oid": "2" * 40,
    }


def valid_bundle_manifest():
    return {
        "$schema": "./v064-public-ci-bundle-manifest-v1.schema.json",
        "schema_version": "1.0.0",
        "purpose": "V064_LINUX_PORTABILITY_WITNESS_ONLY",
        "source": {
            "private_repository": "cjl308868584-lang/crypto-quant-core",
            "candidate_commit": "3" * 40,
            "candidate_tree": "4" * 40,
            "private_release_baseline": "df91e19240df14839125608422489adf3b902e76",
            "object_format": "sha1",
            "historical_billing_blocked_private_pr": {
                "number": 32,
                "run_id": 31436609135,
                "status": "PRIVATE_PR_CI_NOT_EXECUTED_BILLING_BLOCKED",
            },
        },
        "public_repository": "cjl308868584-lang/crypto-quant-v064-public-ci",
        "files": [
            _file(".github/workflows/ci.yml", "PRIVATE_TEMPLATE_BLOB"),
            _file(".gitignore", "PRIVATE_TEMPLATE_BLOB"),
            _file("NOTICE.md", "PRIVATE_TEMPLATE_BLOB"),
            _file("README.md", "PRIVATE_TEMPLATE_BLOB"),
            _file("SECURITY.md", "PRIVATE_TEMPLATE_BLOB"),
            _file(
                "src/crypto_quant/challenger_replacement_supersession_publish.py",
                "PRIVATE_GIT_BLOB",
            ),
            _file(
                "tests/test_v064_linux_supersession_publish.py",
                "PRIVATE_GIT_BLOB",
            ),
        ],
        "file_set_sha256": "5" * 64,
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


class V064PublicCiSchemaTests(unittest.TestCase):
    def schema(self):
        return json.loads(CONFIG_SCHEMA.read_text(encoding="utf-8"))

    def test_config_and_package_schemas_are_exact_valid_mirrors(self):
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        schema = self.schema()
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(valid_bundle_manifest())

    def test_manifest_rejects_wrong_purpose_permissions_and_source_identity(self):
        schema = self.schema()
        mutations = []

        wrong_purpose = copy.deepcopy(valid_bundle_manifest())
        wrong_purpose["purpose"] = "FULL_PROJECT_CI"
        mutations.append(wrong_purpose)

        order_permission = copy.deepcopy(valid_bundle_manifest())
        order_permission["safety"]["orders_allowed"] = True
        mutations.append(order_permission)

        invalid_commit = copy.deepcopy(valid_bundle_manifest())
        invalid_commit["source"]["candidate_commit"] = "not-a-sha"
        mutations.append(invalid_commit)

        mismatched_object_format = copy.deepcopy(valid_bundle_manifest())
        mismatched_object_format["source"]["candidate_commit"] = "3" * 64
        mutations.append(mismatched_object_format)

        wrong_historical_status = copy.deepcopy(valid_bundle_manifest())
        wrong_historical_status["source"]["historical_billing_blocked_private_pr"][
            "status"
        ] = "SUCCESS"
        mutations.append(wrong_historical_status)

        old_pr_claim = copy.deepcopy(valid_bundle_manifest())
        old_pr_claim["source"]["private_pr"] = 32
        mutations.append(old_pr_claim)

        for value in mutations:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    Draft202012Validator(schema).validate(value)

    def test_manifest_rejects_mixed_git_object_formats(self):
        schema = self.schema()
        for path in (
            ("source", "candidate_commit"),
            ("source", "candidate_tree"),
            ("files", 0, "source_blob_oid"),
            ("files", 5, "source_blob_oid"),
        ):
            changed = copy.deepcopy(valid_bundle_manifest())
            container = _at_path(changed, path[:-1])
            container[path[-1]] = "f" * 64
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    Draft202012Validator(schema).validate(changed)

    def test_manifest_requires_the_exact_sorted_non_manifest_file_set(self):
        schema = self.schema()

        duplicate = copy.deepcopy(valid_bundle_manifest())
        duplicate["files"].append(copy.deepcopy(duplicate["files"][0]))
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(duplicate)

        reordered = copy.deepcopy(valid_bundle_manifest())
        reordered["files"][0], reordered["files"][1] = (
            reordered["files"][1],
            reordered["files"][0],
        )
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(reordered)

        unknown = copy.deepcopy(valid_bundle_manifest())
        unknown["files"][0]["unexpected"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(unknown)

    def test_manifest_rejects_unknown_fields_at_every_object_boundary(self):
        schema = self.schema()
        validator = Draft202012Validator(schema)
        original = valid_bundle_manifest()
        for path in _object_paths(original):
            changed = copy.deepcopy(original)
            _at_path(changed, path)["unexpected"] = True
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    validator.validate(changed)
