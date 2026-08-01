import copy
import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.system_paper_plan import (
    SystemPaperPlan,
    SystemPaperPlanError,
    build_system_paper_plan,
    load_system_paper_plan,
    system_paper_plan_hash,
    system_paper_plan_reasons,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "artifacts"
    / "system-paper"
    / "system-paper-plan-v0.55.0.json"
)


class SystemPaperPlanTests(unittest.TestCase):
    def plan(self):
        return build_system_paper_plan()

    def write(self, body: bytes, root: Path) -> Path:
        path = root / "system-paper-plan.json"
        path.write_bytes(body)
        return path

    def test_fixed_plan_identity_is_baseline_only_and_credential_free(self):
        plan = SystemPaperPlan.create()
        self.assertEqual(plan.schema_version, "1.0.0")
        self.assertEqual(plan.symbol, "ETHUSDT")
        self.assertEqual(plan.route, "BASELINE_ONLY")
        self.assertEqual(plan.decision_cadence_seconds, 14_400)
        self.assertEqual(plan.starting_virtual_equity_usdt, Decimal("1000"))
        self.assertEqual(plan.slippage_per_side, Decimal("0.001"))
        self.assertEqual(plan.taker_fee_per_side, Decimal("0.0015"))
        self.assertFalse(plan.credentials_allowed)
        self.assertFalse(plan.real_orders_allowed)

    def test_direct_construction_and_all_overrides_are_rejected(self):
        with self.assertRaises(TypeError):
            SystemPaperPlan(symbol="BTCUSDT")
        with self.assertRaises(TypeError):
            SystemPaperPlan.create(symbol="BTCUSDT")

    def test_built_plan_freezes_scope_cost_data_and_authority(self):
        plan = self.plan()
        self.assertEqual(plan["scope"]["route"], "BASELINE_ONLY")
        self.assertEqual(plan["scope"]["symbol"], "ETHUSDT")
        self.assertEqual(plan["scope"]["market"], "SPOT")
        self.assertEqual(plan["scope"]["direction"], "LONG_ONLY")
        self.assertEqual(plan["scope"]["duration_days"], 90)
        self.assertEqual(plan["scope"]["decision_cadence_seconds"], 14_400)
        self.assertEqual(plan["capital_policy"]["starting_virtual_equity_usdt"], "1000")
        self.assertEqual(plan["cost_policy"]["slippage_rate_per_side"], "0.001")
        self.assertEqual(plan["cost_policy"]["taker_fee_rate_per_side"], "0.0015")
        self.assertFalse(plan["cost_policy"]["funding_applicable"])
        self.assertEqual(plan["cost_policy"]["funding_rate"], "0")
        self.assertEqual(
            plan["market_data_policy"]["public_request_families"],
            [
                "SPOT_AGG_TRADE",
                "SPOT_BBO",
                "SPOT_EXCHANGE_INFO",
                "SPOT_KLINE_4H_WARMUP",
            ],
        )
        self.assertEqual(plan["market_data_policy"]["http_method"], "GET")
        self.assertEqual(plan["risk_policy"]["volatility_target"], "0.12")
        self.assertEqual(plan["risk_policy"]["risk_bucket"], "0.25")
        self.assertEqual(plan["risk_policy"]["maximum_gross_leverage"], "1")
        self.assertEqual(
            plan["risk_policy"]["drawdown_bands"],
            [
                {"lower": "0.10", "upper": "0.12", "state": "WARNING"},
                {"lower": "0.12", "upper": "0.15", "state": "REDUCE"},
                {"lower": "0.15", "upper": "0.20", "state": "HALT"},
                {"lower": "0.20", "upper": None, "state": "HARD_BOUNDARY"},
            ],
        )
        self.assertFalse(plan["authority"]["credentials_allowed"])
        self.assertFalse(plan["authority"]["account_requests_allowed"])
        self.assertFalse(plan["authority"]["broker_requests_allowed"])
        self.assertFalse(plan["authority"]["real_orders_allowed"])
        self.assertFalse(plan["authority"]["production_activation"])
        self.assertEqual(
            plan["warnings"], ["PAPER_NOT_STARTED", "CANARY_NOT_AUTHORIZED"]
        )

    def test_builder_is_deterministic_and_policy_hashes_bind_semantics(self):
        expected = canonical_json(self.plan()).encode("utf-8")
        for _ in range(100):
            self.assertEqual(canonical_json(self.plan()).encode("utf-8"), expected)
        original = self.plan()
        for section, key, value in (
            ("scope", "route", "AI_ENHANCED"),
            ("cost_policy", "taker_fee_rate_per_side", "0"),
            ("authority", "real_orders_allowed", True),
            ("market_data_policy", "http_method", "POST"),
        ):
            changed = copy.deepcopy(original)
            changed[section][key] = value
            changed["plan_hash"] = system_paper_plan_hash(changed)
            self.assertTrue(system_paper_plan_reasons(changed))

    def test_loader_requires_exact_canonical_json_and_rejects_unsafe_json(self):
        plan = self.plan()
        body = canonical_json(plan).encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(load_system_paper_plan(self.write(body, root)), plan)
            malformed = (
                b'{"plan_hash":"' + b"0" * 64 + b'","plan_hash":"' + b"0" * 64 + b'"}'
            )
            with self.assertRaisesRegex(SystemPaperPlanError, "JSON_DUPLICATE_KEY"):
                load_system_paper_plan(self.write(malformed, root))
            with self.assertRaisesRegex(SystemPaperPlanError, "JSON_FLOAT_FORBIDDEN"):
                load_system_paper_plan(self.write(b'{"unsafe":1.5}', root))
            with self.assertRaisesRegex(SystemPaperPlanError, "CANONICAL_BYTES_REQUIRED"):
                load_system_paper_plan(self.write(json.dumps(plan).encode("utf-8"), root))

    def test_loader_rejects_unknown_fields_hash_tamper_and_semantic_rehash(self):
        variants = []
        unknown = copy.deepcopy(self.plan())
        unknown["api_key"] = "forbidden"
        unknown["plan_hash"] = system_paper_plan_hash(unknown)
        variants.append((unknown, "PLAN_SCHEMA_INVALID"))
        bad_hash = copy.deepcopy(self.plan())
        bad_hash["plan_hash"] = "0" * 64
        variants.append((bad_hash, "PLAN_HASH_MISMATCH"))
        rehashed = copy.deepcopy(self.plan())
        rehashed["authority"]["credentials_allowed"] = True
        rehashed["plan_hash"] = system_paper_plan_hash(rehashed)
        variants.append((rehashed, "PLAN_SCHEMA_INVALID"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for plan, reason in variants:
                path = self.write(canonical_json(plan).encode("utf-8"), root)
                with self.assertRaisesRegex(SystemPaperPlanError, reason):
                    load_system_paper_plan(path)

    def test_schema_mirrors_are_exact_strict_and_plan_has_no_request_secrets(self):
        config = ROOT / "config" / "system-paper-plan-v1.schema.json"
        package = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / "system-paper-plan-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), package.read_bytes())
        schema = json.loads(config.read_bytes())
        Draft202012Validator.check_schema(schema)
        plan = self.plan()
        self.assertFalse(tuple(Draft202012Validator(schema).iter_errors(plan)))
        self.assertEqual(plan["plan_hash"], system_paper_plan_hash(plan))
        self.assertEqual(system_paper_plan_reasons(plan), ())
        forbidden_keys = {
            "url",
            "headers",
            "api_key",
            "secret",
            "credential_path",
            "account_endpoint",
            "order_endpoint",
        }

        def visit(value):
            if isinstance(value, dict):
                self.assertTrue(forbidden_keys.isdisjoint(value))
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for nested in value:
                    visit(nested)
            elif isinstance(value, str):
                self.assertNotIn("http://", value.lower())
                self.assertNotIn("https://", value.lower())

        visit(plan)

    def test_committed_plan_is_exact_canonical_and_loader_verified(self):
        body = ARTIFACT.read_bytes()
        plan = self.plan()
        self.assertEqual(body, canonical_json(plan).encode("utf-8") + b"\n")
        self.assertEqual(load_system_paper_plan(ARTIFACT), plan)
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "05ade7d62d755c8dc3b003e41f8ac47975f441450146f8f4b6020b454fb81fda",
        )


if __name__ == "__main__":
    unittest.main()
