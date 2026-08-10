import ast
import copy
import hashlib
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import business_hash, canonical_json, stable_id
from crypto_quant.challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    load_challenger_replacement_plan,
)
from crypto_quant.challenger_replacement_plan_v2 import (
    ChallengerReplacementPlanV2Error,
    build_challenger_replacement_plan_v2,
    challenger_replacement_plan_v2_hash,
    challenger_replacement_plan_v2_reasons,
    load_challenger_replacement_plan_v2,
)


ROOT = Path(__file__).resolve().parents[1]
V1_PATH = (
    ROOT
    / "artifacts"
    / "challenger-replacement"
    / "challenger-replacement-plan-v0.62.0.json"
)
V2_PATH = (
    ROOT
    / "artifacts"
    / "challenger-replacement"
    / "challenger-replacement-plan-v0.64.0.json"
)
V1_FILE_SHA256 = "d450d1e9f8dc422eb5a93beb8a5ffbb1746a4a6d1facb3c5a20a76f4bd527734"
V1_PLAN_ID = "challenger_replacement_plan_d4a542c1566f7a90466ca4d5301b81847f5b5eba93c7a00903d2d95331bc23a2"
V1_PLAN_HASH = "95f395b17d9c09d325c58391542ce5f3d9df5ce6a706b1bba8ffcb62dc6c883c"
V1_PEELED_COMMIT = "e0a9b3eb6a3f385ea259722e6613df8708e8fe5a"
V1_BYTES_BEFORE_TESTS = V1_PATH.read_bytes()

CONFIG_SCHEMA_PATH = ROOT / "config" / "challenger-replacement-plan-v2.schema.json"
PACKAGE_SCHEMA_PATH = (
    ROOT
    / "src"
    / "crypto_quant"
    / "schemas"
    / "challenger-replacement-plan-v2.schema.json"
)

EXPECTED_TOP_LEVEL_KEYS = {
    "$schema",
    "schema_version",
    "plan_id",
    "plan_hash",
    "foundation",
    "predecessor",
    "scope",
    "decision_policy",
    "cohort_policy",
    "isolation_policy",
    "evidence_policy",
    "storage_authority",
    "supersession",
    "authority",
    "status",
    "eligibility",
    "warnings",
}

EXPECTED_RELATIVE_PATHS = {
    "state_events": "state/challenger-replacement-events-v1",
    "non_authoritative_exports": "exports",
    "stdout": "log/challenger-replacement.stdout.log",
    "stderr": "log/challenger-replacement.stderr.log",
    "deployment_contract": "deployment/contract.json",
    "deployment_plist": "deployment/local.crypto-quant.challenger-replacement-v1.plist",
    "preflight_receipts": "preflight-receipts",
    "install_receipts": "install-receipts",
    "start_receipts": "start-receipts",
    "episode_receipts": "episode-receipts",
    "archives": "archives",
    "results": "results",
    "indexes": "indexes",
    "evaluations": "evaluations",
}

EXPECTED_STORAGE_AUTHORITY = {
    "authoritative_state_kind": "APPEND_ONLY_CANONICAL_EVENT_LOG",
    "authoritative_relative_path": "state/challenger-replacement-events-v1",
    "runner_authority_source": "CANONICAL_EVENT_LOG_ONLY",
    "observer_authority_source": "STRICT_EVENT_PROJECTION_ONLY",
    "evaluator_authority_source": "STRICT_EVENT_PROJECTION_ONLY",
    "exports_authoritative": False,
    "exports_required_for_slot_success": False,
    "exports_required_for_evaluation": False,
    "exports_reconstructible": True,
    "source_bundle_export_subdirectory": "source-bundles",
    "decision_export_subdirectory": "decisions",
}

EXPECTED_SUPERSESSION = {
    "previous_plan_release_tag": "v0.62.0",
    "previous_plan_peeled_commit": V1_PEELED_COMMIT,
    "previous_plan_path": (
        "artifacts/challenger-replacement/"
        "challenger-replacement-plan-v0.62.0.json"
    ),
    "previous_plan_file_sha256": V1_FILE_SHA256,
    "previous_plan_id": V1_PLAN_ID,
    "previous_plan_hash": V1_PLAN_HASH,
    "reason": "SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION",
    "previous_plan_state": "PLAN_FROZEN_REPLACEMENT_NOT_STARTED",
    "previous_plan_disposition": "SUPERSEDED_BEFORE_START_NO_COHORT_EVIDENCE",
    "supersession_forbidden_after": "FIRST_START_RECEIPT_OR_CANONICAL_EVENT",
}

EXPECTED_WARNINGS = [
    "OLD_COHORT_PERMANENTLY_FAILED_NO_BACKFILL",
    "REPLACEMENT_RUNTIME_NOT_IMPLEMENTED",
    "REPLACEMENT_NOT_INSTALLED_OR_STARTED",
    "NO_INTERIM_ECONOMIC_REPORTING",
    "NO_PROFITABILITY_OR_AI_ADVANTAGE_CLAIM",
    "CANARY_NOT_AUTHORIZED",
    "V0_62_SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION",
]

V2_FOUNDATION = {
    "release_tag": "v0.63.0",
    "peeled_commit": "df91e19240df14839125608422489adf3b902e76",
    "package_version": "0.63.0",
    "manifest_version": "1.57.0",
    "build_input_tree_hash": "7fdfd6c69f1342892b222882b76ee4988487a482c958a9cdacf00461b2fd8f19",
    "manifest_hash": "f4a74896a6d7b2166adba86075ef06b8d7986f900a086d04ee2f03754baded4b",
    "manifest_file_sha256": "13bea4bfcf633e767eed73d431e57d496dcee47820aacf92e7b61b0efed5c546",
}

BYTE_EQUAL_PATHS = (
    "scope",
    "decision_policy",
    "cohort_policy",
    "evidence_policy",
    "predecessor",
    "eligibility",
)

ALLOWED_DIFF_PREFIXES = (
    "/$schema",
    "/schema_version",
    "/foundation",
    "/plan_id",
    "/plan_hash",
    "/status",
    "/warnings",
    "/isolation_policy/relative_paths",
    "/isolation_policy/policy_hash",
    "/storage_authority",
    "/supersession",
)


def _const_object(schema):
    return {
        key: value["const"]
        for key, value in schema["properties"].items()
        if "const" in value
    }


def _diff_paths(left, right, path=""):
    if isinstance(left, dict) and isinstance(right, dict):
        paths = []
        for key in sorted(set(left) | set(right)):
            child = f"{path}/{key}"
            if key not in left or key not in right:
                paths.append(child)
            else:
                paths.extend(_diff_paths(left[key], right[key], child))
        return paths
    if isinstance(left, list) and isinstance(right, list):
        paths = []
        for index in range(max(len(left), len(right))):
            child = f"{path}/{index}"
            if index >= len(left) or index >= len(right):
                paths.append(child)
            else:
                paths.extend(_diff_paths(left[index], right[index], child))
        return paths
    return [] if left == right else [path]


def _v2_identity(plan):
    return {
        "previous_plan_file_sha256": plan["supersession"][
            "previous_plan_file_sha256"
        ],
        "previous_plan_id": plan["supersession"]["previous_plan_id"],
        "previous_plan_hash": plan["supersession"]["previous_plan_hash"],
        "previous_plan_peeled_commit": plan["supersession"][
            "previous_plan_peeled_commit"
        ],
        "foundation": plan["foundation"],
        "scope_policy_hash": plan["scope"]["policy_hash"],
        "decision_policy_hash": plan["decision_policy"]["policy_hash"],
        "cohort_policy_hash": plan["cohort_policy"]["policy_hash"],
        "isolation_policy_hash": plan["isolation_policy"]["policy_hash"],
        "evidence_policy_hash": plan["evidence_policy"]["policy_hash"],
        "storage_authority_policy_hash": plan["storage_authority"][
            "policy_hash"
        ],
    }


def _reidentify(plan):
    plan["plan_id"] = stable_id("challenger_replacement_plan", _v2_identity(plan))
    plan["plan_hash"] = challenger_replacement_plan_v2_hash(plan)
    return plan


def _write_plan(path, plan, *, newline=True):
    body = canonical_json(plan).encode("utf-8")
    path.write_bytes(body + (b"\n" if newline else b""))
    path.chmod(0o644)
    return path


class ChallengerReplacementPlanV1ImmutableSourceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        if V1_PATH.read_bytes() != V1_BYTES_BEFORE_TESTS:
            raise AssertionError("v0.62 plan bytes changed during v2 schema tests")

    def test_v1_committed_source_identity_and_loader_replay_are_exact(self):
        self.assertEqual(
            hashlib.sha256(V1_BYTES_BEFORE_TESTS).hexdigest(),
            V1_FILE_SHA256,
        )
        raw = json.loads(V1_BYTES_BEFORE_TESTS)
        self.assertEqual(raw["plan_id"], V1_PLAN_ID)
        self.assertEqual(raw["plan_hash"], V1_PLAN_HASH)
        self.assertEqual(load_challenger_replacement_plan(V1_PATH), raw)


class ChallengerReplacementPlanV2ArtifactTests(unittest.TestCase):
    def test_committed_artifact_is_exact_builder_bytes_and_loader_verified(self):
        expected = (
            canonical_json(build_challenger_replacement_plan_v2()).encode("utf-8")
            + b"\n"
        )
        self.assertEqual(V2_PATH.read_bytes(), expected)
        loaded = load_challenger_replacement_plan_v2(V2_PATH)
        self.assertEqual(loaded, build_challenger_replacement_plan_v2())
        self.assertEqual(
            hashlib.sha256(V2_PATH.read_bytes()).hexdigest(),
            hashlib.sha256(expected).hexdigest(),
        )
        v1 = load_challenger_replacement_plan(V1_PATH)
        for key in BYTE_EQUAL_PATHS:
            self.assertEqual(
                canonical_json(loaded[key]).encode("utf-8"),
                canonical_json(v1[key]).encode("utf-8"),
                key,
            )


class ChallengerReplacementPlanV2SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config_bytes = CONFIG_SCHEMA_PATH.read_bytes()
        cls.package_bytes = PACKAGE_SCHEMA_PATH.read_bytes()
        cls.schema = json.loads(cls.config_bytes)

    def test_schema_mirrors_and_top_level_contract_are_exact(self):
        self.assertEqual(self.config_bytes, self.package_bytes)
        Draft202012Validator.check_schema(self.schema)
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(set(self.schema["required"]), EXPECTED_TOP_LEVEL_KEYS)
        self.assertEqual(set(self.schema["properties"]), EXPECTED_TOP_LEVEL_KEYS)
        self.assertEqual(
            self.schema["properties"]["$schema"]["const"],
            "./challenger-replacement-plan-v2.schema.json",
        )
        self.assertEqual(self.schema["properties"]["schema_version"]["const"], "2.0.0")
        self.assertEqual(
            self.schema["properties"]["status"]["const"],
            "PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED",
        )

    def test_relative_paths_replace_all_three_unsafe_v1_keys(self):
        relative_schema = self.schema["properties"]["isolation_policy"]["properties"][
            "relative_paths"
        ]
        self.assertFalse(relative_schema["additionalProperties"])
        self.assertEqual(set(relative_schema["required"]), set(EXPECTED_RELATIVE_PATHS))
        self.assertEqual(_const_object(relative_schema), EXPECTED_RELATIVE_PATHS)
        self.assertFalse(list(Draft202012Validator(relative_schema).iter_errors(EXPECTED_RELATIVE_PATHS)))

        for old_key in ("state", "source_bundles", "decisions"):
            candidate = dict(EXPECTED_RELATIVE_PATHS)
            candidate[old_key] = "forbidden"
            self.assertTrue(
                list(Draft202012Validator(relative_schema).iter_errors(candidate)),
                old_key,
            )
            self.assertNotIn(old_key, relative_schema["properties"])

    def test_storage_authority_and_supersession_are_closed_exact_objects(self):
        storage_schema = self.schema["properties"]["storage_authority"]
        self.assertFalse(storage_schema["additionalProperties"])
        self.assertEqual(
            set(storage_schema["required"]),
            set(EXPECTED_STORAGE_AUTHORITY) | {"policy_hash"},
        )
        self.assertEqual(_const_object(storage_schema), EXPECTED_STORAGE_AUTHORITY)
        self.assertEqual(storage_schema["properties"]["policy_hash"], {"$ref": "#/$defs/hash"})

        supersession_schema = self.schema["properties"]["supersession"]
        self.assertFalse(supersession_schema["additionalProperties"])
        self.assertEqual(set(supersession_schema["required"]), set(EXPECTED_SUPERSESSION))
        self.assertEqual(_const_object(supersession_schema), EXPECTED_SUPERSESSION)

    def test_foundation_warnings_and_every_object_boundary_are_frozen(self):
        self.assertEqual(
            _const_object(self.schema["properties"]["foundation"]),
            {
                "release_tag": "v0.63.0",
                "peeled_commit": "df91e19240df14839125608422489adf3b902e76",
                "package_version": "0.63.0",
                "manifest_version": "1.57.0",
                "build_input_tree_hash": "7fdfd6c69f1342892b222882b76ee4988487a482c958a9cdacf00461b2fd8f19",
                "manifest_hash": "f4a74896a6d7b2166adba86075ef06b8d7986f900a086d04ee2f03754baded4b",
                "manifest_file_sha256": "13bea4bfcf633e767eed73d431e57d496dcee47820aacf92e7b61b0efed5c546",
            },
        )
        self.assertEqual(self.schema["properties"]["warnings"]["const"], EXPECTED_WARNINGS)

        pending = [self.schema]
        while pending:
            node = pending.pop()
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False, node)
                pending.extend(node.values())
            elif isinstance(node, list):
                pending.extend(node)


class ChallengerReplacementPlanV2BuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v1 = load_challenger_replacement_plan(V1_PATH)

    def test_builder_is_parameterless_and_deterministic(self):
        self.assertEqual(
            tuple(inspect.signature(build_challenger_replacement_plan_v2).parameters),
            (),
        )
        first = canonical_json(build_challenger_replacement_plan_v2()).encode(
            "utf-8"
        )
        for _ in range(100):
            self.assertEqual(
                canonical_json(build_challenger_replacement_plan_v2()).encode(
                    "utf-8"
                ),
                first,
            )

    def test_research_subtrees_authority_and_isolation_identity_are_unchanged(self):
        v2 = build_challenger_replacement_plan_v2()
        for key in BYTE_EQUAL_PATHS:
            self.assertEqual(
                canonical_json(v2[key]).encode("utf-8"),
                canonical_json(self.v1[key]).encode("utf-8"),
                key,
            )
        self.assertEqual(v2["authority"], self.v1["authority"])
        for key, value in self.v1["isolation_policy"].items():
            if key not in ("relative_paths", "policy_hash"):
                self.assertEqual(v2["isolation_policy"][key], value, key)
        for key in ("service_label", "service_identity", "runtime_root", "target_plist"):
            self.assertEqual(v2["isolation_policy"][key], self.v1["isolation_policy"][key])
        self.assertNotIn("strategy", v2)
        self.assertNotIn("evaluation", v2)

    def test_only_preregistered_paths_change_and_exact_new_objects_are_frozen(self):
        v2 = build_challenger_replacement_plan_v2()
        differences = _diff_paths(self.v1, v2)
        self.assertTrue(differences)
        for path in differences:
            self.assertTrue(
                any(
                    path == prefix or path.startswith(prefix + "/")
                    for prefix in ALLOWED_DIFF_PREFIXES
                ),
                path,
            )
        self.assertEqual(v2["foundation"], V2_FOUNDATION)
        self.assertEqual(v2["warnings"], EXPECTED_WARNINGS)
        self.assertEqual(v2["isolation_policy"]["relative_paths"], EXPECTED_RELATIVE_PATHS)
        self.assertEqual(
            {key: v2["storage_authority"][key] for key in EXPECTED_STORAGE_AUTHORITY},
            EXPECTED_STORAGE_AUTHORITY,
        )
        self.assertEqual(v2["supersession"], EXPECTED_SUPERSESSION)

    def test_policy_plan_hash_and_plan_identity_recompute_exactly(self):
        plan = build_challenger_replacement_plan_v2()
        for key in (
            "scope",
            "decision_policy",
            "cohort_policy",
            "isolation_policy",
            "evidence_policy",
            "storage_authority",
        ):
            policy = dict(plan[key])
            claimed = policy.pop("policy_hash")
            self.assertEqual(claimed, business_hash(policy), key)
        self.assertEqual(
            plan["plan_id"],
            stable_id("challenger_replacement_plan", _v2_identity(plan)),
        )
        self.assertEqual(plan["plan_hash"], challenger_replacement_plan_v2_hash(plan))
        self.assertEqual(challenger_replacement_plan_v2_reasons(plan), ())

    def test_rehashed_semantic_tampering_is_rejected(self):
        cases = {
            "scope": lambda plan: plan["scope"].__setitem__("market", "FUTURES"),
            "decision": lambda plan: plan["decision_policy"].__setitem__(
                "minimum_hold_hours", 9
            ),
            "cohort": lambda plan: plan["cohort_policy"].__setitem__(
                "duration_days", 91
            ),
            "evidence": lambda plan: plan["evidence_policy"].__setitem__(
                "old_decisions_migrated", True
            ),
            "predecessor": lambda plan: plan["predecessor"][
                "failure_receipt"
            ].__setitem__("failure_reason", "DIFFERENT"),
            "eligibility": lambda plan: plan["eligibility"].__setitem__(
                "runtime", "ELIGIBLE"
            ),
            "authority": lambda plan: plan["authority"].__setitem__(
                "production_activation", True
            ),
            "service": lambda plan: plan["isolation_policy"].__setitem__(
                "service_label", "different"
            ),
            "runtime_root": lambda plan: plan["isolation_policy"].__setitem__(
                "runtime_root", "/different"
            ),
            "old_path": lambda plan: plan["isolation_policy"][
                "relative_paths"
            ].__setitem__("state", "state/old.sqlite"),
            "storage": lambda plan: plan["storage_authority"].__setitem__(
                "exports_authoritative", True
            ),
            "supersession": lambda plan: plan["supersession"].__setitem__(
                "reason", "DIFFERENT"
            ),
            "v1_binding": lambda plan: plan["supersession"].__setitem__(
                "previous_plan_hash", "f" * 64
            ),
            "foundation": lambda plan: plan["foundation"].__setitem__(
                "release_tag", "v0.64.0"
            ),
            "warning_value": lambda plan: plan["warnings"].__setitem__(
                0, "DIFFERENT"
            ),
            "warning_order": lambda plan: plan["warnings"].reverse(),
            "warning_count": lambda plan: plan["warnings"].append("EIGHTH"),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(build_challenger_replacement_plan_v2())
                mutate(changed)
                for key in (
                    "scope",
                    "decision_policy",
                    "cohort_policy",
                    "isolation_policy",
                    "evidence_policy",
                    "storage_authority",
                ):
                    policy = dict(changed[key])
                    policy.pop("policy_hash")
                    changed[key]["policy_hash"] = business_hash(policy)
                _reidentify(changed)
                self.assertTrue(challenger_replacement_plan_v2_reasons(changed))

    def test_claimed_policy_id_and_plan_hash_tampering_is_rejected(self):
        for name, mutate in {
            "policy_hash": lambda plan: plan["scope"].__setitem__(
                "policy_hash", "f" * 64
            ),
            "plan_id": lambda plan: plan.__setitem__(
                "plan_id", "challenger_replacement_plan_" + "f" * 64
            ),
            "plan_hash": lambda plan: plan.__setitem__("plan_hash", "f" * 64),
        }.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(build_challenger_replacement_plan_v2())
                mutate(changed)
                self.assertTrue(challenger_replacement_plan_v2_reasons(changed))

    def test_module_ast_has_no_process_network_or_state_capability(self):
        source = (
            ROOT / "src" / "crypto_quant" / "challenger_replacement_plan_v2.py"
        ).read_text()
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertTrue(
            {"subprocess", "socket", "urllib", "requests", "sqlite3"}.isdisjoint(
                imported
            )
        )


class ChallengerReplacementPlanV2LoaderTests(unittest.TestCase):
    def test_fixture_writer_has_explicit_formal_artifact_mode(self):
        plan = build_challenger_replacement_plan_v2()
        with tempfile.TemporaryDirectory() as directory:
            previous_umask = os.umask(0o022)
            try:
                path = _write_plan(Path(directory) / "owner-only.json", plan)
            finally:
                os.umask(previous_umask)
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_loader_accepts_only_exact_canonical_v2_bytes(self):
        plan = build_challenger_replacement_plan_v2()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for newline in (False, True):
                path = _write_plan(root / f"plan-{newline}.json", plan, newline=newline)
                self.assertEqual(load_challenger_replacement_plan_v2(path), plan)

            pretty = root / "pretty.json"
            pretty.write_text(json.dumps(plan, indent=2))
            with self.assertRaises(ChallengerReplacementPlanV2Error):
                load_challenger_replacement_plan_v2(pretty)

    def test_loader_rejects_v1_duplicate_float_and_nonabsolute_inputs(self):
        plan = build_challenger_replacement_plan_v2()
        canonical = canonical_json(plan)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.json"
            duplicate.write_text(
                canonical.replace(
                    '"schema_version":"2.0.0"',
                    '"schema_version":"2.0.0","schema_version":"2.0.0"',
                    1,
                )
            )
            floating = root / "float.json"
            floating.write_text(
                canonical.replace('"required_slot_count":540', '"required_slot_count":540.0', 1)
            )
            for path in (duplicate, floating, V1_PATH):
                with self.subTest(path=path.name):
                    with self.assertRaises(ChallengerReplacementPlanV2Error):
                        load_challenger_replacement_plan_v2(path)
            with self.assertRaises(ChallengerReplacementPlanV2Error):
                load_challenger_replacement_plan_v2(Path("relative.json"))

    def test_loader_rejects_writable_hardlinked_symlinked_and_oversized_files(self):
        plan = build_challenger_replacement_plan_v2()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            writable = _write_plan(root / "writable.json", plan)
            writable.chmod(0o666)
            hardlink_source = _write_plan(root / "hardlink-source.json", plan)
            hardlink = root / "hardlink.json"
            os.link(hardlink_source, hardlink)
            symlink = root / "symlink.json"
            symlink.symlink_to(hardlink_source)
            oversized = root / "oversized.json"
            oversized.write_bytes(b"{" + b" " * (256 * 1024))
            for path in (writable, hardlink, symlink, oversized):
                with self.subTest(path=path.name):
                    with self.assertRaises(ChallengerReplacementPlanV2Error):
                        load_challenger_replacement_plan_v2(path)

    def test_v1_and_v2_loaders_reject_the_other_schema(self):
        plan = build_challenger_replacement_plan_v2()
        with tempfile.TemporaryDirectory() as directory:
            path = _write_plan(Path(directory) / "v2.json", plan)
            with self.assertRaises(ChallengerReplacementPlanError):
                load_challenger_replacement_plan(path)
        with self.assertRaises(ChallengerReplacementPlanV2Error):
            load_challenger_replacement_plan_v2(V1_PATH)
