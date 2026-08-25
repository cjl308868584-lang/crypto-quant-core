import copy
import hashlib
import json
import inspect
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json, stable_id


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "src/crypto_quant/schemas/"
    "challenger-replacement-accelerated-canary-plan-v1.schema.json"
)
EXPECTED_KEYS = {
    "$schema",
    "schema_version",
    "plan_id",
    "plan_hash",
    "foundation",
    "supersession_scope",
    "projection_contract",
    "code_complete_program",
    "simulation_qualification",
    "operational_ceremony",
    "hard_stop_policy",
    "canary_ladder",
    "credential_boundary",
    "approval_ledger",
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


class AcceleratedCanaryPlanSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text())

    def test_schema_is_draft_202012_and_exact_key(self):
        Draft202012Validator.check_schema(self.schema)
        self.assertEqual(
            self.schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(set(self.schema["required"]), EXPECTED_KEYS)
        self.assertEqual(set(self.schema["properties"]), EXPECTED_KEYS)

    def test_every_object_is_exact_key(self):
        objects = tuple(_object_schemas(self.schema))
        self.assertGreater(len(objects), 15)
        for schema in objects:
            self.assertIs(
                schema.get("additionalProperties"),
                False,
                msg=schema.get("title", schema),
            )
            self.assertEqual(
                set(schema.get("required", ())),
                set(schema.get("properties", ())),
                msg=schema.get("title", schema),
            )

    def test_schema_freezes_accelerated_boundaries(self):
        properties = self.schema["properties"]
        self.assertEqual(
            properties["status"]["const"],
            "ACCELERATED_CANARY_PLAN_PREREGISTERED_NOT_ACTIVATED",
        )
        simulation = properties["simulation_qualification"]["properties"]
        self.assertEqual(simulation["minimum_continuous_seconds"]["const"], 259_200)
        self.assertEqual(simulation["cadence_seconds"]["const"], 14_400)
        ceremony = properties["operational_ceremony"]["properties"]
        self.assertEqual(
            ceremony["label"]["const"],
            "OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE",
        )
        hard_stops = properties["hard_stop_policy"]["properties"][
            "absolute_classes"
        ]
        self.assertFalse(hard_stops["items"])
        self.assertEqual(
            [item["const"] for item in hard_stops["prefixItems"]],
            [
                "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN",
                "VENUE_LOCAL_POSITION_MISMATCH",
                "PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP",
                "RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT",
            ],
        )

    def test_schema_freezes_all_authority_false_or_zero(self):
        authority = self.schema["properties"]["authority"]["properties"]
        false_keys = {
            "production_activation",
            "runtime_install_authorized",
            "replacement_start_authorized",
            "credentials_allowed",
            "account_requests_allowed",
            "broker_requests_allowed",
            "real_orders_allowed",
            "fund_movement_allowed",
            "ceremony_authorized",
            "e0_activation_authorized",
        }
        zero_keys = {
            "market_requests",
            "private_account_requests",
            "production_state_writes",
            "economic_outcome_reads",
        }
        self.assertEqual(set(authority), false_keys | zero_keys)
        for key in false_keys:
            self.assertIs(authority[key]["const"], False)
        for key in zero_keys:
            self.assertEqual(authority[key]["const"], 0)


class AcceleratedCanaryPlanBuilderTests(unittest.TestCase):
    def _api(self):
        from crypto_quant.challenger_replacement_accelerated_canary_plan import (
            build_challenger_replacement_accelerated_canary_plan,
            challenger_replacement_accelerated_canary_plan_hash,
            challenger_replacement_accelerated_canary_plan_reasons,
        )

        return (
            build_challenger_replacement_accelerated_canary_plan,
            challenger_replacement_accelerated_canary_plan_hash,
            challenger_replacement_accelerated_canary_plan_reasons,
        )

    def test_builder_is_parameterless_deterministic_and_schema_valid(self):
        build, _, reasons = self._api()
        self.assertEqual(tuple(inspect.signature(build).parameters), ())
        first = build()
        second = build()
        self.assertEqual(canonical_json(first), canonical_json(second))
        schema = json.loads(SCHEMA.read_text())
        self.assertEqual(tuple(Draft202012Validator(schema).iter_errors(first)), ())
        self.assertEqual(reasons(first), ())

    def test_builder_binds_exact_released_foundation(self):
        build, _, _ = self._api()
        foundation = build()["foundation"]
        self.assertEqual(
            foundation["v069_plan"],
            {
                "file_sha256": "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3",
                "plan_id": "challenger_replacement_plan_v3_e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f",
                "plan_hash": "f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486",
            },
        )
        self.assertEqual(
            foundation["v073_release"],
            {
                "release_tag": "v0.73.0",
                "peeled_commit": "34bd0e9ba96c769b7301c482730a03fb975c24ce",
                "package_version": "0.73.0",
                "manifest_version": "1.67.0",
                "manifest_hash": "0117d3a17bdea7e2a22004d675175083e9d863722c6c176632d29e3c4c6e62d0",
            },
        )
        self.assertEqual(
            foundation["v074_economic_plan"],
            {
                "file_sha256": "24fba7579ac36c037aaef4fbf34a69b56503358edbd64addbe01f30a70c33297",
                "plan_id": "challenger_replacement_economic_evaluation_plan_13ba2b74dd8c330732789a3fccd36f017847047f9fd07ea0bcf36b66f54a943e",
                "plan_hash": "7c02267a0895cb3d8ceea79b6a38415140de23fb1cfcf3350c7fddff62089fa4",
            },
        )
        self.assertEqual(
            foundation["v074_release"],
            {
                "release_tag": "v0.74.0",
                "tag_object": "86624de8be8d5117e4b4ef6fd825a9eb711c7c38",
                "peeled_commit": "bfe0080b0a29a74550449a1eb2ac2907a2d2ddac",
                "package_version": "0.74.0",
                "manifest_version": "1.68.0",
                "manifest_file_sha256": "0db974c9d143abee2e3fc078c09db8893a82754f1c4209178fb982d3d449db12",
                "manifest_hash": "699b50fe198b25934e67433d95ea75deb3f6e0657fa8c440a61c7d6c5349e2ec",
                "tree_hash": "fe58cc252f9b548e6eedb25e8249c6329cd20ee50f7a0cec48fe88abbbe4bb8e",
            },
        )

    def test_builder_freezes_dual_projection_and_continuous_72_hours(self):
        build, _, _ = self._api()
        plan = build()
        self.assertEqual(
            plan["projection_contract"]["economic_projection"],
            "V074_ECONOMIC_RESEARCH_PROJECTION_V1_UNCHANGED",
        )
        self.assertEqual(
            plan["projection_contract"]["operational_projection"],
            "ACCELERATED_OPERATIONAL_CANARY_PROJECTION_V2",
        )
        qualification = plan["simulation_qualification"]
        self.assertEqual(qualification["minimum_continuous_seconds"], 259_200)
        self.assertEqual(qualification["cadence_seconds"], 14_400)
        self.assertEqual(
            qualification["healthy_segment_rule"],
            "ONE_FINAL_UNINTERRUPTED_SEGMENT_DISCONNECTED_SECONDS_NEVER_SUMMED",
        )
        self.assertFalse(qualification["fixture_time_counts"])
        scope = plan["supersession_scope"]
        self.assertFalse(scope["economic_contract_changed"])
        self.assertFalse(scope["retroactive_rewrite_allowed"])

    def test_builder_freezes_ceremony_exclusion_and_four_hard_stops(self):
        build, _, _ = self._api()
        plan = build()
        ceremony = plan["operational_ceremony"]
        self.assertEqual(
            ceremony["label"],
            "OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE",
        )
        self.assertEqual(set(ceremony["evidence_exclusions"].values()), {True})
        self.assertEqual(
            plan["hard_stop_policy"]["absolute_classes"],
            [
                "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN",
                "VENUE_LOCAL_POSITION_MISMATCH",
                "PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP",
                "RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT",
            ],
        )

    def test_builder_freezes_ladder_and_zero_authority(self):
        build, _, _ = self._api()
        plan = build()
        ladder = plan["canary_ladder"]
        self.assertEqual(
            (
                ladder["E0"]["capital_limit_usdt"],
                ladder["E0"]["gross_exposure_limit"],
                ladder["E0"]["minimum_calendar_days"],
                ladder["E0"]["minimum_strategy_cycles"],
            ),
            ("100", "0.5", 7, 3),
        )
        self.assertEqual(
            (
                ladder["E1"]["capital_limit_usdt"],
                ladder["E1"]["gross_exposure_limit"],
                ladder["E1"]["minimum_calendar_days"],
                ladder["E1"]["minimum_strategy_cycles"],
            ),
            ("300", "1", 14, 5),
        )
        self.assertEqual(
            (
                ladder["E2"]["capital_limit_usdt"],
                ladder["E2"]["gross_exposure_limit"],
                ladder["E2"]["minimum_calendar_days"],
                ladder["E2"]["minimum_strategy_cycles"],
            ),
            ("1000", "2", 30, 10),
        )
        authority = plan["authority"]
        counter_keys = {
            "market_requests",
            "private_account_requests",
            "production_state_writes",
            "economic_outcome_reads",
        }
        for key, value in authority.items():
            if key in counter_keys:
                self.assertIs(type(value), int, key)
                self.assertEqual(value, 0, key)
            else:
                self.assertIs(value, False, key)

    def test_builder_derives_stable_id_and_self_hash(self):
        build, plan_hash, _ = self._api()
        plan = build()
        identity = {
            "foundation": plan["foundation"],
            **{
                section + "_policy_hash": plan[section]["policy_hash"]
                for section in (
                    "supersession_scope",
                    "projection_contract",
                    "code_complete_program",
                    "simulation_qualification",
                    "operational_ceremony",
                    "hard_stop_policy",
                    "canary_ladder",
                    "credential_boundary",
                    "approval_ledger",
                )
            },
        }
        self.assertEqual(
            plan["plan_id"],
            stable_id("challenger_replacement_accelerated_canary_plan", identity),
        )
        self.assertEqual(plan["plan_hash"], plan_hash(plan))


class AcceleratedCanaryPlanLoaderTests(unittest.TestCase):
    def setUp(self):
        from crypto_quant import challenger_replacement_accelerated_canary_plan

        self.module = challenger_replacement_accelerated_canary_plan
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "plan.json"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _body(self):
        return (
            canonical_json(
                self.module.build_challenger_replacement_accelerated_canary_plan()
            ).encode("utf-8")
            + b"\n"
        )

    def _write(self, body):
        self.path.write_bytes(body)
        self.path.chmod(0o600)

    def _load_with_matching_sha(self):
        body = self.path.read_bytes()
        with mock.patch.object(
            self.module,
            "_ARTIFACT_SHA256",
            hashlib.sha256(body).hexdigest(),
        ):
            return self.module.load_challenger_replacement_accelerated_canary_plan(
                self.path
            )

    def test_loader_accepts_only_exact_canonical_plus_lf(self):
        self._write(self._body())
        self.assertEqual(
            self._load_with_matching_sha(),
            self.module.build_challenger_replacement_accelerated_canary_plan(),
        )
        self._write(self._body()[:-1])
        with self.assertRaises(self.module.ChallengerReplacementAcceleratedCanaryPlanError) as raised:
            self._load_with_matching_sha()
        self.assertEqual(
            raised.exception.reason_code,
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_CANONICAL_BYTES_REQUIRED",
        )

    def test_loader_rejects_relative_and_untrusted_paths(self):
        with self.assertRaises(self.module.ChallengerReplacementAcceleratedCanaryPlanError) as raised:
            self.module.load_challenger_replacement_accelerated_canary_plan(
                Path("plan.json")
            )
        self.assertEqual(
            raised.exception.reason_code,
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_PATH_INVALID",
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
                    self.module.ChallengerReplacementAcceleratedCanaryPlanError
                ) as candidate_error:
                    self.module.load_challenger_replacement_accelerated_canary_plan(
                        candidate
                    )
                self.assertEqual(
                    candidate_error.exception.reason_code,
                    "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_PATH_INVALID",
                )

    def test_loader_maps_strict_json_and_noncanonical_bytes(self):
        cases = (
            (
                b'{"x":1,"x":2}',
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_JSON_DUPLICATE_KEY",
            ),
            (
                b'{"x":1.0}',
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_JSON_FLOAT_FORBIDDEN",
            ),
            (
                b'{not json}',
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_JSON_INVALID",
            ),
            (
                self._body() + b" ",
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_CANONICAL_BYTES_REQUIRED",
            ),
            (
                self._body() + b"\n",
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_CANONICAL_BYTES_REQUIRED",
            ),
        )
        for body, reason in cases:
            with self.subTest(reason=reason):
                self._write(body)
                with self.assertRaises(
                    self.module.ChallengerReplacementAcceleratedCanaryPlanError
                ) as raised:
                    self._load_with_matching_sha()
                self.assertEqual(raised.exception.reason_code, reason)

    def test_loader_requires_literal_artifact_sha_before_semantics(self):
        self._write(self._body())
        with mock.patch.object(self.module, "_ARTIFACT_SHA256", "0" * 64):
            with self.assertRaises(
                self.module.ChallengerReplacementAcceleratedCanaryPlanError
            ) as raised:
                self.module.load_challenger_replacement_accelerated_canary_plan(
                    self.path
                )
        self.assertEqual(
            raised.exception.reason_code,
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_FILE_SHA256_MISMATCH",
        )


class AcceleratedCanaryPlanMutationTests(unittest.TestCase):
    _POLICY_SECTIONS = (
        "supersession_scope",
        "projection_contract",
        "code_complete_program",
        "simulation_qualification",
        "operational_ceremony",
        "hard_stop_policy",
        "canary_ladder",
        "credential_boundary",
        "approval_ledger",
    )

    @staticmethod
    def _api():
        from crypto_quant import challenger_replacement_accelerated_canary_plan

        return challenger_replacement_accelerated_canary_plan

    @staticmethod
    def _leaves(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items():
                yield from AcceleratedCanaryPlanMutationTests._leaves(
                    child, path + (key,)
                )
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from AcceleratedCanaryPlanMutationTests._leaves(
                    child, path + (index,)
                )
        else:
            yield path

    @staticmethod
    def _replace(plan, path):
        target = plan
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

    def _reclaim(self, plan):
        module = self._api()
        for section_name in self._POLICY_SECTIONS:
            section = dict(plan[section_name])
            section.pop("policy_hash")
            plan[section_name]["policy_hash"] = self._business_hash(section)
        identity = {
            "foundation": plan["foundation"],
            **{
                section + "_policy_hash": plan[section]["policy_hash"]
                for section in self._POLICY_SECTIONS
            },
        }
        plan["plan_id"] = stable_id(
            "challenger_replacement_accelerated_canary_plan", identity
        )
        plan["plan_hash"] = module.challenger_replacement_accelerated_canary_plan_hash(
            plan
        )

    @staticmethod
    def _business_hash(value):
        from crypto_quant.canonical import business_hash

        return business_hash(value)

    def test_mutating_each_policy_and_authority_leaf_is_semantic_mismatch(self):
        module = self._api()
        original = module.build_challenger_replacement_accelerated_canary_plan()
        roots = (
            "foundation",
            *self._POLICY_SECTIONS,
            "authority",
            "status",
            "warnings",
        )
        for root in roots:
            for relative in self._leaves(original[root]):
                if relative and relative[-1] == "policy_hash":
                    continue
                with self.subTest(path=(root,) + relative):
                    changed = copy.deepcopy(original)
                    self._replace(changed, (root,) + relative)
                    self._reclaim(changed)
                    self.assertIn(
                        "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_SEMANTIC_MISMATCH",
                        module.challenger_replacement_accelerated_canary_plan_reasons(
                            changed
                        ),
                    )

    def test_reasons_report_hash_policy_and_id_failures(self):
        module = self._api()
        plan = module.build_challenger_replacement_accelerated_canary_plan()
        plan["plan_hash"] = "0" * 64
        plan["simulation_qualification"]["policy_hash"] = "0" * 64
        plan["plan_id"] = (
            "challenger_replacement_accelerated_canary_plan_" + "0" * 64
        )
        reasons = module.challenger_replacement_accelerated_canary_plan_reasons(
            plan
        )
        self.assertIn(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_HASH_MISMATCH",
            reasons,
        )
        self.assertIn(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_POLICY_HASH_MISMATCH",
            reasons,
        )
        self.assertIn(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_ID_MISMATCH",
            reasons,
        )


if __name__ == "__main__":
    unittest.main()
