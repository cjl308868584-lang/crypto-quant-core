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

from crypto_quant.challenger_replacement_plan_v2 import (
    load_challenger_replacement_plan_v2,
)
from crypto_quant.challenger_replacement_plan_v3 import (
    ChallengerReplacementPlanV3Error,
    build_challenger_replacement_plan_v3,
    challenger_replacement_plan_v3_hash,
    challenger_replacement_plan_v3_reasons,
    load_challenger_replacement_plan_v3,
)
from crypto_quant.canonical import business_hash, canonical_json, stable_id


ROOT = Path(__file__).resolve().parents[1]
V2_PATH = (
    ROOT
    / "artifacts"
    / "challenger-replacement"
    / "challenger-replacement-plan-v0.64.0.json"
)
V2_FILE_SHA256 = "5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f"
V2_PLAN_ID = (
    "challenger_replacement_plan_"
    "65d85d60a534a917f45a1ffa5fc9d3f74d6d24995b900d31b8c73cd26f0bd97b"
)
V2_PLAN_HASH = "c9a1e5f74c52fbf23be5a1d27fd23c25f3601ed58133178fc25480391ab65705"
V2_BYTES_BEFORE_TESTS = V2_PATH.read_bytes()

CONFIG_SCHEMA_PATH = ROOT / "config" / "challenger-replacement-plan-v3.schema.json"
PACKAGE_SCHEMA_PATH = (
    ROOT
    / "src"
    / "crypto_quant"
    / "schemas"
    / "challenger-replacement-plan-v3.schema.json"
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
    "opportunity_policy",
    "operational_qualification",
    "economic_evidence",
    "canary_ladder",
    "product_policy",
    "risk_policy",
    "isolation_policy",
    "evidence_policy",
    "storage_authority",
    "supersession",
    "authority",
    "status",
    "eligibility",
    "warnings",
}

EXPECTED_AUTHORITY = {
    "credentials_allowed": False,
    "account_requests_allowed": False,
    "broker_requests_allowed": False,
    "real_orders_allowed": False,
    "production_activation": False,
    "runtime_install_authorized": False,
    "replacement_start_authorized": False,
}

POLICY_SECTIONS = (
    "scope",
    "decision_policy",
    "opportunity_policy",
    "operational_qualification",
    "economic_evidence",
    "canary_ladder",
    "product_policy",
    "risk_policy",
    "isolation_policy",
    "evidence_policy",
    "storage_authority",
)


def _const_object(schema):
    return {
        key: value["const"]
        for key, value in schema["properties"].items()
        if "const" in value
    }


def _walk_object_schemas(value, path="$"):
    if isinstance(value, dict):
        if value.get("type") == "object":
            yield path, value
        for key, child in value.items():
            yield from _walk_object_schemas(child, f"{path}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_object_schemas(child, f"{path}/{index}")


def _v3_identity(plan):
    return {
        "previous_plan_file_sha256": plan["supersession"][
            "previous_plan_file_sha256"
        ],
        "previous_plan_id": plan["supersession"]["previous_plan_id"],
        "previous_plan_hash": plan["supersession"]["previous_plan_hash"],
        "foundation": plan["foundation"],
        **{
            f"{name}_policy_hash": plan[name]["policy_hash"]
            for name in POLICY_SECTIONS
        },
    }


def _rehash_and_reidentify(plan):
    for name in POLICY_SECTIONS:
        policy = dict(plan[name])
        policy.pop("policy_hash")
        plan[name]["policy_hash"] = business_hash(policy)
    plan["plan_id"] = stable_id(
        "challenger_replacement_plan_v3", _v3_identity(plan)
    )
    plan["plan_hash"] = challenger_replacement_plan_v3_hash(plan)
    return plan


def _write_plan(path, plan, *, newline=True):
    body = canonical_json(plan).encode("utf-8")
    path.write_bytes(body + (b"\n" if newline else b""))
    path.chmod(0o644)
    return path


class ChallengerReplacementPlanV3PredecessorTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        if V2_PATH.read_bytes() != V2_BYTES_BEFORE_TESTS:
            raise AssertionError("v0.64 plan bytes changed during v3 schema tests")

    def test_v064_plan_identity_and_loader_replay_remain_exact(self):
        self.assertEqual(
            hashlib.sha256(V2_BYTES_BEFORE_TESTS).hexdigest(),
            V2_FILE_SHA256,
        )
        raw = json.loads(V2_BYTES_BEFORE_TESTS)
        self.assertEqual(raw["plan_id"], V2_PLAN_ID)
        self.assertEqual(raw["plan_hash"], V2_PLAN_HASH)
        self.assertEqual(load_challenger_replacement_plan_v2(V2_PATH), raw)


class ChallengerReplacementPlanV3SchemaTests(unittest.TestCase):
    def _schema(self):
        config_bytes = CONFIG_SCHEMA_PATH.read_bytes()
        self.assertEqual(config_bytes, PACKAGE_SCHEMA_PATH.read_bytes())
        schema = json.loads(config_bytes)
        Draft202012Validator.check_schema(schema)
        return schema

    def test_schema_mirrors_are_valid_and_freeze_the_top_level_contract(self):
        schema = self._schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), EXPECTED_TOP_LEVEL_KEYS)
        self.assertEqual(set(schema["properties"]), EXPECTED_TOP_LEVEL_KEYS)

    def test_every_declared_object_schema_rejects_unknown_keys(self):
        missing = [
            path
            for path, candidate in _walk_object_schemas(self._schema())
            if candidate.get("additionalProperties") is not False
        ]
        self.assertEqual(missing, [])

    def test_foundation_binds_the_released_v068_identity(self):
        self.assertEqual(
            build_challenger_replacement_plan_v3()["foundation"],
            {
                "release_tag": "v0.68.0",
                "peeled_commit": (
                    "1371997d61679609804d58753ae79147d60e1c01"
                ),
                "package_version": "0.68.0",
                "manifest_version": "1.62.0",
                "build_input_tree_hash": (
                    "0e6bde43eff304bc42cab90895da47296a9c6b8996b0d99a0d1ca4009a71083e"
                ),
                "manifest_hash": (
                    "f4ce2f0a67b04541b850f5841897927e2886a339fecb3f11356ad96b2d7370b5"
                ),
                "manifest_file_sha256": (
                    "d7c70074fef46f28d028cc330a8726755fe999bba5af90af90a24f285df37a79"
                ),
            },
        )

    def test_schema_freezes_decision_opportunity_and_dual_track_boundaries(self):
        properties = self._schema()["properties"]
        self.assertEqual(
            _const_object(properties["opportunity_policy"]),
            {
                "cadence_seconds": 14400,
                "capture_open_offset_seconds": 120,
                "capture_close_offset_seconds": 600,
                "terminal_outcomes": ["OBSERVED", "MISSED"],
                "historical_decision_backfill_allowed": False,
                "missed_opportunity_recovery": (
                    "APPEND_MISSED_WITH_ACTUAL_DETECTION_TIME"
                ),
            },
        )
        missed = properties["opportunity_policy"]["properties"][
            "missed_reason_codes"
        ]
        self.assertEqual(
            [item["const"] for item in missed["prefixItems"]],
            [
                "PROCESS_NOT_RUNNING",
                "CAPTURE_WINDOW_EXPIRED",
                "PUBLIC_MARKET_SOURCE_UNAVAILABLE",
                "CLOCK_OR_CONNECTIVITY_UNTRUSTED",
                "PRECONDITION_FAILED_CLOSED",
            ],
        )
        self.assertFalse(missed["items"])
        self.assertEqual(
            _const_object(properties["operational_qualification"])[
                "minimum_calendar_days"
            ],
            7,
        )
        self.assertEqual(
            _const_object(properties["operational_qualification"])[
                "minimum_observed_coverage"
            ],
            "0.95",
        )
        self.assertEqual(
            _const_object(properties["economic_evidence"])[
                "minimum_calendar_days"
            ],
            90,
        )
        self.assertFalse(
            _const_object(properties["economic_evidence"])[
                "interim_profitability_pass_allowed"
            ]
        )

    def test_schema_freezes_canary_product_risk_and_disabled_authority(self):
        properties = self._schema()["properties"]
        ladder = properties["canary_ladder"]["properties"]
        self.assertEqual(
            _const_object(ladder["E0"]),
            {
                "capital_limit_usdt": "100",
                "gross_exposure_limit": "0.5",
                "minimum_calendar_days": 7,
                "minimum_strategy_cycles": 3,
            },
        )
        self.assertEqual(
            _const_object(ladder["E1"]),
            {
                "capital_limit_usdt": "300",
                "gross_exposure_limit": "1",
                "minimum_calendar_days": 14,
                "minimum_strategy_cycles": 5,
            },
        )
        self.assertEqual(
            _const_object(ladder["E2"]),
            {
                "capital_limit_usdt": "1000",
                "gross_exposure_limit": "2",
                "minimum_calendar_days": 30,
                "minimum_strategy_cycles": 10,
            },
        )
        self.assertTrue(ladder["spot_roundtrip_each_stage_required"]["const"])
        self.assertTrue(
            ladder["perpetual_roundtrip_each_stage_required"]["const"]
        )
        product = _const_object(properties["product_policy"])
        self.assertEqual(product["venue"], "BINANCE_ONLY")
        self.assertEqual(product["position_states"], ["FLAT", "SPOT_LONG", "PERP_SHORT"])
        self.assertTrue(product["flatten_before_reversal_required"])
        self.assertEqual(product["perpetual_position_mode"], "ONE_WAY")
        self.assertEqual(product["perpetual_margin_mode"], "ISOLATED")
        self.assertEqual(product["technical_leverage_cap"], "2")
        self.assertEqual(_const_object(properties["authority"]), EXPECTED_AUTHORITY)


class ChallengerReplacementPlanV3BuilderTests(unittest.TestCase):
    def test_builder_is_parameterless_deterministic_and_side_effect_free(self):
        self.assertEqual(
            tuple(inspect.signature(build_challenger_replacement_plan_v3).parameters),
            (),
        )
        first = canonical_json(build_challenger_replacement_plan_v3()).encode(
            "utf-8"
        )
        for _ in range(20):
            self.assertEqual(
                canonical_json(build_challenger_replacement_plan_v3()).encode(
                    "utf-8"
                ),
                first,
            )

    def test_builder_freezes_dual_direction_opportunities_tracks_and_ladder(self):
        plan = build_challenger_replacement_plan_v3()
        decision = plan["decision_policy"]
        self.assertEqual(
            decision["long_entry"],
            "LATEST_CLOSE_GTE_PRIOR_SMA20_TIMES_1_005_AND_LOG_RETURN_5_GT_ZERO",
        )
        self.assertEqual(
            decision["short_entry"],
            "LATEST_CLOSE_LTE_PRIOR_SMA20_TIMES_0_995_AND_LOG_RETURN_5_LT_ZERO",
        )
        self.assertEqual(
            decision["long_exit_after_minimum"],
            "LATEST_CLOSE_LTE_PRIOR_SMA20_OR_VERTICAL_EXIT",
        )
        self.assertEqual(
            decision["short_exit_after_minimum"],
            "LATEST_CLOSE_GTE_PRIOR_SMA20_OR_VERTICAL_EXIT",
        )
        self.assertFalse(decision["same_opportunity_close_and_reverse_allowed"])
        self.assertTrue(
            decision["reverse_requires_next_opportunity_after_verified_flat"]
        )
        self.assertEqual(
            plan["opportunity_policy"]["terminal_outcomes"],
            ["OBSERVED", "MISSED"],
        )
        self.assertEqual(
            plan["operational_qualification"]["minimum_calendar_days"], 7
        )
        self.assertEqual(plan["economic_evidence"]["minimum_calendar_days"], 90)
        self.assertEqual(
            {
                name: {
                    key: plan["canary_ladder"][name][key]
                    for key in (
                        "capital_limit_usdt",
                        "gross_exposure_limit",
                        "minimum_calendar_days",
                        "minimum_strategy_cycles",
                    )
                }
                for name in ("E0", "E1", "E2")
            },
            {
                "E0": {
                    "capital_limit_usdt": "100",
                    "gross_exposure_limit": "0.5",
                    "minimum_calendar_days": 7,
                    "minimum_strategy_cycles": 3,
                },
                "E1": {
                    "capital_limit_usdt": "300",
                    "gross_exposure_limit": "1",
                    "minimum_calendar_days": 14,
                    "minimum_strategy_cycles": 5,
                },
                "E2": {
                    "capital_limit_usdt": "1000",
                    "gross_exposure_limit": "2",
                    "minimum_calendar_days": 30,
                    "minimum_strategy_cycles": 10,
                },
            },
        )
        self.assertEqual(plan["authority"], EXPECTED_AUTHORITY)

    def test_policy_plan_hash_and_identity_are_recomputed_exactly(self):
        plan = build_challenger_replacement_plan_v3()
        for name in POLICY_SECTIONS:
            policy = dict(plan[name])
            claimed = policy.pop("policy_hash")
            self.assertEqual(claimed, business_hash(policy), name)
        self.assertEqual(
            plan["plan_id"],
            stable_id("challenger_replacement_plan_v3", _v3_identity(plan)),
        )
        self.assertEqual(plan["plan_hash"], challenger_replacement_plan_v3_hash(plan))
        self.assertEqual(challenger_replacement_plan_v3_reasons(plan), ())

    def test_rehashed_semantic_tampering_is_rejected(self):
        cases = {
            "opportunity": lambda plan: plan["opportunity_policy"].__setitem__(
                "historical_decision_backfill_allowed", True
            ),
            "operational": lambda plan: plan[
                "operational_qualification"
            ].__setitem__("minimum_calendar_days", 6),
            "economic": lambda plan: plan["economic_evidence"].__setitem__(
                "minimum_calendar_days", 89
            ),
            "short_rule": lambda plan: plan["decision_policy"].__setitem__(
                "short_entry", "DIFFERENT"
            ),
            "leverage": lambda plan: plan["product_policy"].__setitem__(
                "technical_leverage_cap", "3"
            ),
            "capital": lambda plan: plan["canary_ladder"]["E0"].__setitem__(
                "capital_limit_usdt", "101"
            ),
            "risk": lambda plan: plan["risk_policy"]["E0"].__setitem__(
                "daily_loss_limit", "3"
            ),
            "authority": lambda plan: plan["authority"].__setitem__(
                "real_orders_allowed", True
            ),
            "predecessor": lambda plan: plan["predecessor"][
                "previous_plan"
            ].__setitem__("plan_hash", "f" * 64),
            "supersession": lambda plan: plan["supersession"].__setitem__(
                "reason", "DIFFERENT"
            ),
            "warning": lambda plan: plan["warnings"].append("EXTRA"),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(build_challenger_replacement_plan_v3())
                mutate(changed)
                _rehash_and_reidentify(changed)
                self.assertTrue(challenger_replacement_plan_v3_reasons(changed))

    def test_module_has_no_process_network_runtime_or_order_capability(self):
        source = (
            ROOT / "src" / "crypto_quant" / "challenger_replacement_plan_v3.py"
        ).read_text()
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertTrue(
            {
                "subprocess",
                "socket",
                "urllib",
                "requests",
                "sqlite3",
                "execution",
                "broker",
            }.isdisjoint(imported)
        )


class ChallengerReplacementPlanV3LoaderTests(unittest.TestCase):
    def test_committed_v069_plan_matches_the_exact_builder(self):
        root = ROOT / "artifacts" / "challenger-replacement"
        path = root / "challenger-replacement-plan-v0.69.0.json"
        expected = canonical_json(
            build_challenger_replacement_plan_v3()
        ).encode("utf-8") + b"\n"
        self.assertEqual(path.read_bytes(), expected)
        loaded = load_challenger_replacement_plan_v3(path)
        self.assertEqual(loaded, build_challenger_replacement_plan_v3())
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), (
            "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3"
        ))
        self.assertFalse((
            root / "challenger-replacement-v3-supersession-machine-evidence-v0.69.0.json"
        ).exists())
        self.assertFalse((
            root / "challenger-replacement-v3-owner-attestation-v0.69.0.json"
        ).exists())
        self.assertFalse((
            root / "challenger-replacement-plan-v3-supersession-v0.69.0.json"
        ).exists())

    def test_loader_accepts_only_exact_canonical_v3_bytes(self):
        plan = build_challenger_replacement_plan_v3()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for newline in (False, True):
                path = _write_plan(root / f"plan-{newline}.json", plan, newline=newline)
                self.assertEqual(load_challenger_replacement_plan_v3(path), plan)
            pretty = root / "pretty.json"
            pretty.write_text(json.dumps(plan, indent=2))
            pretty.chmod(0o644)
            with self.assertRaises(ChallengerReplacementPlanV3Error):
                load_challenger_replacement_plan_v3(pretty)

    def test_loader_rejects_duplicate_float_v2_and_relative_inputs(self):
        plan = build_challenger_replacement_plan_v3()
        canonical = canonical_json(plan)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.json"
            duplicate.write_text(
                canonical.replace(
                    '"schema_version":"3.0.0"',
                    '"schema_version":"3.0.0","schema_version":"3.0.0"',
                    1,
                )
            )
            duplicate.chmod(0o644)
            floating = root / "float.json"
            floating.write_text(
                canonical.replace('"minimum_calendar_days":7', '"minimum_calendar_days":7.0', 1)
            )
            floating.chmod(0o644)
            for path in (duplicate, floating, V2_PATH):
                with self.subTest(path=path.name):
                    with self.assertRaises(ChallengerReplacementPlanV3Error):
                        load_challenger_replacement_plan_v3(path)
        with self.assertRaises(ChallengerReplacementPlanV3Error):
            load_challenger_replacement_plan_v3(Path("relative.json"))

    def test_loader_rejects_writable_hardlinked_symlinked_and_oversized_files(self):
        plan = build_challenger_replacement_plan_v3()
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
                    with self.assertRaises(ChallengerReplacementPlanV3Error):
                        load_challenger_replacement_plan_v3(path)
