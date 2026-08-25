import copy
import hashlib
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json, stable_id
from crypto_quant.challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/crypto_quant/schemas/"
    "challenger-replacement-accelerated-canary-supersession-v1.schema.json"
)
EXPECTED_KEYS = {
    "$schema",
    "schema_version",
    "record_id",
    "record_hash",
    "reason",
    "predecessor",
    "successor",
    "changed_operational_rules",
    "preserved_economic_authority",
    "effectivity",
    "authority",
    "status",
    "warnings",
}


def _object_schemas(value):
    if isinstance(value, dict):
        if value.get("type") == "object":
            yield value
        for child in value.values():
            yield from _object_schemas(child)
    elif isinstance(value, list):
        for child in value:
            yield from _object_schemas(child)


class AcceleratedCanarySupersessionSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text())

    def test_schema_is_exact_key_draft_202012(self):
        Draft202012Validator.check_schema(self.schema)
        self.assertEqual(
            self.schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(set(self.schema["required"]), EXPECTED_KEYS)
        self.assertEqual(set(self.schema["properties"]), EXPECTED_KEYS)
        for schema in _object_schemas(self.schema):
            self.assertIs(schema.get("additionalProperties"), False)
            self.assertEqual(
                set(schema.get("required", ())),
                set(schema.get("properties", ())),
            )

    def test_schema_freezes_reason_effectivity_and_zero_authority(self):
        properties = self.schema["properties"]
        self.assertEqual(
            properties["reason"]["const"],
            "SUPERSEDED_FUTURE_ACTIVATION_ACCELERATED_OPERATIONAL_QUALIFICATION",
        )
        self.assertEqual(
            properties["status"]["const"],
            "SUPERSESSION_PREREGISTERED_NOT_ACTIVATED",
        )
        effectivity = properties["effectivity"]["properties"]
        self.assertEqual(
            effectivity["applies_to"]["const"],
            "ONLY_START_RECEIPTS_CREATED_AFTER_V075_AND_BINDING_SUCCESSOR_PLAN",
        )
        self.assertEqual(effectivity["retroactive_effect"]["const"], "NONE")
        authority = properties["authority"]["properties"]
        self.assertTrue(all(item["const"] in (False, 0) for item in authority.values()))


class AcceleratedCanarySupersessionBuilderTests(unittest.TestCase):
    @staticmethod
    def _api():
        from crypto_quant import (
            challenger_replacement_accelerated_canary_supersession as module,
        )

        return module

    def test_builder_is_parameterless_deterministic_and_schema_valid(self):
        module = self._api()
        build = module.build_challenger_replacement_accelerated_canary_supersession
        self.assertEqual(tuple(inspect.signature(build).parameters), ())
        first = build()
        second = build()
        self.assertEqual(canonical_json(first), canonical_json(second))
        schema = json.loads(SCHEMA.read_text())
        self.assertEqual(tuple(Draft202012Validator(schema).iter_errors(first)), ())
        self.assertEqual(
            module.challenger_replacement_accelerated_canary_supersession_reasons(
                first
            ),
            (),
        )

    def test_builder_derives_successor_file_identity_without_input(self):
        module = self._api()
        record = module.build_challenger_replacement_accelerated_canary_supersession()
        plan = build_challenger_replacement_accelerated_canary_plan()
        plan_bytes = canonical_json(plan).encode("utf-8") + b"\n"
        self.assertEqual(
            record["successor"],
            {
                "file_sha256": hashlib.sha256(plan_bytes).hexdigest(),
                "plan_id": plan["plan_id"],
                "plan_hash": plan["plan_hash"],
                "target_release": "v0.75.0",
            },
        )

    def test_builder_preserves_economic_authority_and_changes_only_operations(self):
        module = self._api()
        record = module.build_challenger_replacement_accelerated_canary_supersession()
        self.assertEqual(
            record["preserved_economic_authority"],
            {
                "v074_economic_plan_disposition": "IMMUTABLE_UNCHANGED_AUTHORITY",
                "file_sha256": "24fba7579ac36c037aaef4fbf34a69b56503358edbd64addbe01f30a70c33297",
                "plan_id": "challenger_replacement_economic_evaluation_plan_13ba2b74dd8c330732789a3fccd36f017847047f9fd07ea0bcf36b66f54a943e",
                "plan_hash": "7c02267a0895cb3d8ceea79b6a38415140de23fb1cfcf3350c7fddff62089fa4",
                "economic_start_or_window_changed": False,
            },
        )
        self.assertEqual(
            record["changed_operational_rules"],
            [
                "SEVEN_DAY_NATURAL_CYCLE_GATE_TO_CONTINUOUS_72_HOUR_QUALIFICATION",
                "NATURAL_PRE_E0_PRODUCT_ROUNDTRIPS_TO_EXCLUDED_OPERATIONAL_CEREMONY",
                "PERMANENT_STREAM_LOCK_TO_IMMUTABLE_FAILED_BLOCK_AND_APPROVED_NEW_BLOCK",
                "BROAD_TERMINAL_OPERATIONAL_FAILURES_TO_FOUR_ABSOLUTE_STAGE_HARD_STOPS",
            ],
        )
        counter_keys = {
            "market_requests",
            "private_account_requests",
            "production_state_writes",
            "economic_outcome_reads",
        }
        for key, value in record["authority"].items():
            if key in counter_keys:
                self.assertIs(type(value), int, key)
                self.assertEqual(value, 0, key)
            else:
                self.assertIs(value, False, key)

    def test_builder_derives_stable_id_and_self_hash(self):
        module = self._api()
        record = module.build_challenger_replacement_accelerated_canary_supersession()
        identity = {
            "reason": record["reason"],
            "predecessor": record["predecessor"],
            "successor": record["successor"],
            "changed_operational_rules": record["changed_operational_rules"],
            "preserved_economic_authority": record[
                "preserved_economic_authority"
            ],
            "effectivity": record["effectivity"],
        }
        self.assertEqual(
            record["record_id"],
            stable_id(
                "challenger_replacement_accelerated_canary_supersession",
                identity,
            ),
        )
        self.assertEqual(
            record["record_hash"],
            module.challenger_replacement_accelerated_canary_supersession_hash(
                record
            ),
        )


class AcceleratedCanarySupersessionLoaderTests(unittest.TestCase):
    def setUp(self):
        from crypto_quant import (
            challenger_replacement_accelerated_canary_supersession as module,
        )

        self.module = module
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "record.json"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _body(self):
        return (
            canonical_json(
                self.module.build_challenger_replacement_accelerated_canary_supersession()
            ).encode("utf-8")
            + b"\n"
        )

    def _write(self, body):
        self.path.write_bytes(body)
        self.path.chmod(0o600)

    def _load_matching_sha(self):
        body = self.path.read_bytes()
        with mock.patch.object(
            self.module,
            "_ARTIFACT_SHA256",
            hashlib.sha256(body).hexdigest(),
        ):
            return self.module.load_challenger_replacement_accelerated_canary_supersession(
                self.path
            )

    def test_loader_accepts_only_canonical_plus_lf(self):
        self._write(self._body())
        self.assertEqual(
            self._load_matching_sha(),
            self.module.build_challenger_replacement_accelerated_canary_supersession(),
        )
        self._write(self._body()[:-1])
        with self.assertRaises(
            self.module.ChallengerReplacementAcceleratedCanarySupersessionError
        ) as raised:
            self._load_matching_sha()
        self.assertEqual(
            raised.exception.reason_code,
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_SUPERSESSION_CANONICAL_BYTES_REQUIRED",
        )

    def test_loader_rejects_relative_and_untrusted_paths(self):
        with self.assertRaises(
            self.module.ChallengerReplacementAcceleratedCanarySupersessionError
        ) as raised:
            self.module.load_challenger_replacement_accelerated_canary_supersession(
                Path("record.json")
            )
        self.assertEqual(
            raised.exception.reason_code,
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_SUPERSESSION_PATH_INVALID",
        )

        self._write(self._body())
        symlink = self.path.with_name("symlink.json")
        symlink.symlink_to(self.path)
        hardlink = self.path.with_name("hardlink.json")
        os.link(self.path, hardlink)
        unsafe = self.path.with_name("unsafe.json")
        unsafe.write_bytes(self._body())
        unsafe.chmod(0o622)
        directory = self.path.with_name("directory")
        directory.mkdir(mode=0o700)
        oversized = self.path.with_name("oversized.json")
        oversized.write_bytes(b"x" * (256 * 1024 + 1))
        oversized.chmod(0o600)
        for candidate in (symlink, hardlink, unsafe, directory, oversized):
            with self.subTest(candidate=candidate.name):
                with self.assertRaises(
                    self.module.ChallengerReplacementAcceleratedCanarySupersessionError
                ) as candidate_error:
                    self.module.load_challenger_replacement_accelerated_canary_supersession(
                        candidate
                    )
                self.assertEqual(
                    candidate_error.exception.reason_code,
                    "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_SUPERSESSION_PATH_INVALID",
                )

    def test_loader_maps_json_noncanonical_and_literal_sha_failures(self):
        cases = (
            (
                b'{"x":1,"x":2}',
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_SUPERSESSION_JSON_DUPLICATE_KEY",
            ),
            (
                b'{"x":1.0}',
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_SUPERSESSION_JSON_FLOAT_FORBIDDEN",
            ),
            (
                b'{not json}',
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_SUPERSESSION_JSON_INVALID",
            ),
            (
                self._body() + b" ",
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_SUPERSESSION_CANONICAL_BYTES_REQUIRED",
            ),
        )
        for body, reason in cases:
            with self.subTest(reason=reason):
                self._write(body)
                with self.assertRaises(
                    self.module.ChallengerReplacementAcceleratedCanarySupersessionError
                ) as raised:
                    self._load_matching_sha()
                self.assertEqual(raised.exception.reason_code, reason)

        self._write(self._body())
        with mock.patch.object(self.module, "_ARTIFACT_SHA256", "0" * 64):
            with self.assertRaises(
                self.module.ChallengerReplacementAcceleratedCanarySupersessionError
            ) as raised:
                self.module.load_challenger_replacement_accelerated_canary_supersession(
                    self.path
                )
        self.assertEqual(
            raised.exception.reason_code,
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_SUPERSESSION_FILE_SHA256_MISMATCH",
        )


class AcceleratedCanarySupersessionMutationTests(unittest.TestCase):
    @staticmethod
    def _api():
        from crypto_quant import (
            challenger_replacement_accelerated_canary_supersession as module,
        )

        return module

    @staticmethod
    def _leaves(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items():
                yield from AcceleratedCanarySupersessionMutationTests._leaves(
                    child, path + (key,)
                )
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from AcceleratedCanarySupersessionMutationTests._leaves(
                    child, path + (index,)
                )
        else:
            yield path

    @staticmethod
    def _replace(record, path):
        target = record
        for segment in path[:-1]:
            target = target[segment]
        leaf = path[-1]
        value = target[leaf]
        if isinstance(value, bool):
            target[leaf] = not value
        elif isinstance(value, int):
            target[leaf] = value + 1
        else:
            target[leaf] = str(value) + "_MUTATED"

    def _reclaim(self, record):
        module = self._api()
        identity = {
            "reason": record["reason"],
            "predecessor": record["predecessor"],
            "successor": record["successor"],
            "changed_operational_rules": record["changed_operational_rules"],
            "preserved_economic_authority": record[
                "preserved_economic_authority"
            ],
            "effectivity": record["effectivity"],
        }
        record["record_id"] = stable_id(
            "challenger_replacement_accelerated_canary_supersession",
            identity,
        )
        record["record_hash"] = (
            module.challenger_replacement_accelerated_canary_supersession_hash(
                record
            )
        )

    def test_every_frozen_leaf_remains_semantically_immutable(self):
        module = self._api()
        original = module.build_challenger_replacement_accelerated_canary_supersession()
        roots = (
            "reason",
            "predecessor",
            "successor",
            "changed_operational_rules",
            "preserved_economic_authority",
            "effectivity",
            "authority",
            "status",
            "warnings",
        )
        for root in roots:
            for relative in self._leaves(original[root]):
                with self.subTest(path=(root,) + relative):
                    changed = copy.deepcopy(original)
                    self._replace(changed, (root,) + relative)
                    self._reclaim(changed)
                    self.assertIn(
                        "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_SUPERSESSION_SEMANTIC_MISMATCH",
                        module.challenger_replacement_accelerated_canary_supersession_reasons(
                            changed
                        ),
                    )

    def test_reasons_report_hash_and_id_failures(self):
        module = self._api()
        record = module.build_challenger_replacement_accelerated_canary_supersession()
        record["record_hash"] = "0" * 64
        record["record_id"] = (
            "challenger_replacement_accelerated_canary_supersession_" + "0" * 64
        )
        reasons = module.challenger_replacement_accelerated_canary_supersession_reasons(
            record
        )
        self.assertIn(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_SUPERSESSION_HASH_MISMATCH",
            reasons,
        )
        self.assertIn(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_SUPERSESSION_ID_MISMATCH",
            reasons,
        )


if __name__ == "__main__":
    unittest.main()
