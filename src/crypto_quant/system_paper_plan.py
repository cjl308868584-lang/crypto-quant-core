"""Immutable, credential-free plan for the 90-day System Paper cohort.

The plan is a preregistration artifact only.  Building or loading it performs no
network request, creates no runtime state, and grants no Broker or order authority.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id
from .evidence import artifact_self_hash
from .offline_paper import OfflinePaperPlan


_SCHEMA = "system-paper-plan-v1.schema.json"
_PLAN_TOKEN = object()
_ZERO_HASH = "0" * 64
_MAX_PLAN_BYTES = 256 * 1024


class SystemPaperPlanError(ValueError):
    """The System Paper plan failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, init=False)
class SystemPaperPlan:
    schema_version: str
    symbol: str
    route: str
    decision_cadence_seconds: int
    starting_virtual_equity_usdt: Decimal
    slippage_per_side: Decimal
    taker_fee_per_side: Decimal
    credentials_allowed: bool
    real_orders_allowed: bool

    def __init__(self, *args, **kwargs):
        if args or kwargs.pop("_token", None) is not _PLAN_TOKEN or kwargs:
            raise TypeError("SystemPaperPlan must be created with create")
        object.__setattr__(self, "schema_version", "1.0.0")
        object.__setattr__(self, "symbol", "ETHUSDT")
        object.__setattr__(self, "route", "BASELINE_ONLY")
        object.__setattr__(self, "decision_cadence_seconds", 14_400)
        object.__setattr__(
            self, "starting_virtual_equity_usdt", Decimal("1000")
        )
        object.__setattr__(self, "slippage_per_side", Decimal("0.001"))
        object.__setattr__(self, "taker_fee_per_side", Decimal("0.0015"))
        object.__setattr__(self, "credentials_allowed", False)
        object.__setattr__(self, "real_orders_allowed", False)

    @classmethod
    def create(cls) -> "SystemPaperPlan":
        return cls(_token=_PLAN_TOKEN)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _with_policy_hash(policy: Mapping[str, Any]) -> Dict[str, Any]:
    value = dict(policy)
    value["policy_hash"] = business_hash(policy)
    return value


def system_paper_plan_hash(plan: Mapping[str, Any]) -> str:
    return artifact_self_hash(plan, "plan_hash")


def _identity(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "scope_policy_hash": plan["scope"]["policy_hash"],
        "market_data_policy_hash": plan["market_data_policy"]["policy_hash"],
        "capital_policy_hash": plan["capital_policy"]["policy_hash"],
        "cost_policy_hash": plan["cost_policy"]["policy_hash"],
        "fill_policy_hash": plan["fill_policy"]["policy_hash"],
        "risk_policy_hash": plan["risk_policy"]["policy_hash"],
    }


def build_system_paper_plan() -> Dict[str, Any]:
    """Build the sole V1 BASELINE_ONLY plan without runtime side effects."""

    fixed = SystemPaperPlan.create()
    offline = OfflinePaperPlan.create(fixed.symbol)
    scope = _with_policy_hash(
        {
            "mode": "SYSTEM_PAPER",
            "route": fixed.route,
            "strategy_policy_id": "SPOT_LONG_SMA20_VOL12_BUCKET25_V1",
            "offline_plan_schema_version": offline.schema_version,
            "market_data_provider": offline.provider,
            "symbol": fixed.symbol,
            "market": "SPOT",
            "direction": "LONG_ONLY",
            "duration_days": 90,
            "decision_cadence_seconds": fixed.decision_cadence_seconds,
            "historical_backfill_allowed": False,
            "evidence_scope_reset_on_semantic_change": True,
        }
    )
    market_data_policy = _with_policy_hash(
        {
            "provider": "BINANCE_MARKET_DATA_ONLY",
            "public_only": True,
            "http_method": "GET",
            "public_request_families": [
                "SPOT_AGG_TRADE",
                "SPOT_BBO",
                "SPOT_EXCHANGE_INFO",
                "SPOT_KLINE_4H_WARMUP",
            ],
            "account_requests_allowed": False,
            "private_endpoints_allowed": False,
            "missing_or_stale_input_action": "FAIL_CLOSED_NO_DECISION",
        }
    )
    capital_policy = _with_policy_hash(
        {
            "starting_virtual_equity_usdt": "1000",
            "external_cash_flows_allowed": False,
            "leverage": "1",
            "margin_borrowing_allowed": False,
        }
    )
    cost_policy = _with_policy_hash(
        {
            "slippage_rate_per_side": "0.001",
            "taker_fee_rate_per_side": "0.0015",
            "funding_applicable": False,
            "funding_rate": "0",
            "decimal_arithmetic_only": True,
            "binary_float_allowed": False,
            "cost_override_allowed": False,
        }
    )
    fill_policy = _with_policy_hash(
        {
            "execution_mode": "DETERMINISTIC_SIMULATED_BROKER",
            "fill_model_version": "SYSTEM_PAPER_CONSERVATIVE_BBO_V1",
            "partial_fill_required": True,
            "reject_cancel_timeout_unknown_required": True,
            "real_fill_claim_allowed": False,
            "fill_override_allowed": False,
        }
    )
    risk_policy = _with_policy_hash(
        {
            "volatility_target": "0.12",
            "risk_bucket": "0.25",
            "maximum_gross_leverage": "1",
            "drawdown_bands": [
                {"lower": "0.10", "upper": "0.12", "state": "WARNING"},
                {"lower": "0.12", "upper": "0.15", "state": "REDUCE"},
                {"lower": "0.15", "upper": "0.20", "state": "HALT"},
                {
                    "lower": "0.20",
                    "upper": None,
                    "state": "HARD_BOUNDARY",
                },
            ],
            "risk_lock_required": True,
            "position_reconciliation_required": True,
            "ledger_reconciliation_required": True,
            "kill_switch_required": True,
            "new_risk_on_unknown_allowed": False,
            "risk_override_allowed": False,
        }
    )
    plan: Dict[str, Any] = {
        "$schema": "./system-paper-plan-v1.schema.json",
        "schema_version": fixed.schema_version,
        "plan_id": "system_paper_plan_" + _ZERO_HASH,
        "plan_hash": _ZERO_HASH,
        "scope": scope,
        "market_data_policy": market_data_policy,
        "capital_policy": capital_policy,
        "cost_policy": cost_policy,
        "fill_policy": fill_policy,
        "risk_policy": risk_policy,
        "authority": {
            "credentials_allowed": fixed.credentials_allowed,
            "account_requests_allowed": False,
            "broker_requests_allowed": False,
            "real_orders_allowed": fixed.real_orders_allowed,
            "production_activation": False,
            "runtime_install_authorized": False,
            "paper_start_authorized": False,
        },
        "status": "PLAN_FROZEN_PAPER_NOT_STARTED",
        "eligibility": {
            "system_paper_start": "INELIGIBLE_RUNTIME_NOT_INSTALLED",
            "system_paper_pass": "INELIGIBLE_90_DAY_EVIDENCE_NOT_STARTED",
            "canary": "INELIGIBLE",
            "profitability": "INELIGIBLE_NO_SYSTEM_PAPER_EVIDENCE",
            "ai_comparison": "NOT_APPLICABLE_BASELINE_ONLY",
        },
        "warnings": ["PAPER_NOT_STARTED", "CANARY_NOT_AUTHORIZED"],
    }
    plan["plan_id"] = stable_id("system_paper_plan", _identity(plan))
    plan["plan_hash"] = system_paper_plan_hash(plan)
    if tuple(_validator().iter_errors(plan)):
        raise SystemPaperPlanError("SYSTEM_PAPER_PLAN_SCHEMA_INVALID")
    return plan


def system_paper_plan_reasons(plan: Mapping[str, Any]) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator().iter_errors(plan)):
            reasons.append("SYSTEM_PAPER_PLAN_SCHEMA_INVALID")
        if plan.get("plan_hash") != system_paper_plan_hash(plan):
            reasons.append("SYSTEM_PAPER_PLAN_HASH_MISMATCH")
        if business_hash(plan) != business_hash(build_system_paper_plan()):
            reasons.append("SYSTEM_PAPER_PLAN_SEMANTIC_MISMATCH")
    except (KeyError, TypeError, ValueError, SystemPaperPlanError):
        reasons.append("SYSTEM_PAPER_PLAN_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def _strict_json_bytes(body: bytes) -> Mapping[str, Any]:
    if not isinstance(body, bytes) or not body or len(body) > _MAX_PLAN_BYTES:
        raise SystemPaperPlanError("SYSTEM_PAPER_PLAN_JSON_INVALID")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SystemPaperPlanError(
                    "SYSTEM_PAPER_PLAN_JSON_DUPLICATE_KEY"
                )
            result[key] = value
        return result

    def reject_number(_value):
        raise SystemPaperPlanError("SYSTEM_PAPER_PLAN_JSON_FLOAT_FORBIDDEN")

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except SystemPaperPlanError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemPaperPlanError("SYSTEM_PAPER_PLAN_JSON_INVALID") from error
    if not isinstance(value, Mapping):
        raise SystemPaperPlanError("SYSTEM_PAPER_PLAN_JSON_INVALID")
    return value


def load_system_paper_plan(path: Path) -> Dict[str, Any]:
    """Load only the one canonical, semantically frozen plan."""

    plan_path = Path(path).expanduser()
    if not plan_path.is_absolute() or plan_path.is_symlink() or not plan_path.is_file():
        raise SystemPaperPlanError("SYSTEM_PAPER_PLAN_PATH_INVALID")
    body = plan_path.read_bytes()
    plan = dict(_strict_json_bytes(body))
    canonical = canonical_json(plan).encode("utf-8")
    if body not in (canonical, canonical + b"\n"):
        raise SystemPaperPlanError("SYSTEM_PAPER_PLAN_CANONICAL_BYTES_REQUIRED")
    reasons = system_paper_plan_reasons(plan)
    if reasons:
        raise SystemPaperPlanError(reasons[0])
    return plan
