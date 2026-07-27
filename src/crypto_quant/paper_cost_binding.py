"""Point-in-time binding of account commission evidence to offline Paper."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .account_commission import account_commission_reasons
from .canonical import (
    business_hash,
    canonical_decimal,
    stable_id,
    utc_datetime,
)
from .evidence import artifact_self_hash
from .offline_paper import offline_paper_run_reasons


_ATTESTATION_TYPE = "PAPER_ACCOUNT_COST_BINDING_ATTESTATION"
_POLICY_VERSION = "PAPER_ACCOUNT_COMMISSION_NO_DISCOUNT_REBASE_V1"
_ASSUMED_TAKER_RATE = Decimal("0.0015")
_WARNINGS = (
    "ACCOUNT_COMMISSION_CURRENT_ONLY_NO_HISTORICAL_BACKFILL",
    "EXTERNAL_SOURCE_ATTESTATIONS_REQUIRED",
    "COST_ONLY_REPLAY_NOT_NEW_MARKET_OBSERVATION",
    "SIGNAL_FILL_SLIPPAGE_AND_QUANTITY_UNCHANGED",
    "BNB_DISCOUNT_NOT_APPLIED",
    "AI_MODEL_NOT_RUN",
    "PAPER_DURATION_BELOW_90_DAYS",
    "PROFITABILITY_NOT_PROVEN",
)


class PaperCostBindingError(ValueError):
    """The account-cost Paper binding failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> Tuple[datetime, str]:
    if not isinstance(value, str):
        raise PaperCostBindingError("PAPER_COST_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PaperCostBindingError(
            "PAPER_COST_TIME_INVALID"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperCostBindingError("PAPER_COST_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise PaperCostBindingError("PAPER_COST_TIME_INVALID")
    return converted, utc_datetime(converted)


def _decimal(value: object, *, nonnegative: bool = True) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > 80:
        raise PaperCostBindingError("PAPER_COST_DECIMAL_INVALID")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise PaperCostBindingError(
            "PAPER_COST_DECIMAL_INVALID"
        ) from error
    if (
        not number.is_finite()
        or (nonnegative and number < 0)
        or (number.is_zero() and number.is_signed())
        or canonical_decimal(number) != value
    ):
        raise PaperCostBindingError("PAPER_COST_DECIMAL_INVALID")
    return number


def _hash(value: object, reason: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PaperCostBindingError(reason)
    return value


@lru_cache(maxsize=1)
def _binding_validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas", "paper-account-cost-binding-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_sources(
    offline_paper_run: Mapping[str, Any],
    offline_paper_trusted_attestation_hash: str,
    account_commission_snapshot: Mapping[str, Any],
    account_commission_trusted_attestation_hash: str,
) -> None:
    paper_trust = _hash(
        offline_paper_trusted_attestation_hash,
        "PAPER_COST_PAPER_TRUST_HASH_INVALID",
    )
    account_trust = _hash(
        account_commission_trusted_attestation_hash,
        "PAPER_COST_ACCOUNT_TRUST_HASH_INVALID",
    )
    if offline_paper_run_reasons(offline_paper_run, paper_trust):
        raise PaperCostBindingError("PAPER_COST_PAPER_SOURCE_INVALID")
    if account_commission_reasons(
        account_commission_snapshot, account_trust
    ):
        raise PaperCostBindingError("PAPER_COST_ACCOUNT_SOURCE_INVALID")


def _pit_binding(
    offline_paper_run: Mapping[str, Any],
    account_commission_snapshot: Mapping[str, Any],
) -> Dict[str, Any]:
    observed, observed_text = _utc(
        account_commission_snapshot["observed_at"]
    )
    valid_until, valid_until_text = _utc(
        account_commission_snapshot["valid_until"]
    )
    decision, decision_text = _utc(offline_paper_run["decision_time"])
    run_end, run_end_text = _utc(offline_paper_run["run_end"])
    if observed > decision:
        raise PaperCostBindingError(
            "PAPER_COST_ACCOUNT_OBSERVED_AFTER_DECISION"
        )
    if valid_until < run_end:
        raise PaperCostBindingError(
            "PAPER_COST_ACCOUNT_EXPIRED_BEFORE_RUN_END"
        )
    if decision > run_end or observed > valid_until:
        raise PaperCostBindingError("PAPER_COST_PIT_INVALID")
    try:
        if (
            offline_paper_run["plan"]["symbol"] != "ETHUSDT"
            or account_commission_snapshot["policy"]["symbol"]
            != "ETHUSDT"
            or account_commission_snapshot["commission_context"]["spot"][
                "symbol"
            ]
            != "ETHUSDT"
            or account_commission_snapshot["cost_context_eligibility"]
            != "CURRENT_PAPER_CONTEXT_ONLY"
            or account_commission_snapshot[
                "historical_backfill_eligibility"
            ]
            != "FORBIDDEN"
        ):
            raise PaperCostBindingError(
                "PAPER_COST_SOURCE_SCOPE_INVALID"
            )
    except (KeyError, TypeError) as error:
        raise PaperCostBindingError(
            "PAPER_COST_SOURCE_SCOPE_INVALID"
        ) from error
    return {
        "status": "PASS",
        "account_observed_at": observed_text,
        "paper_decision_time": decision_text,
        "paper_run_end": run_end_text,
        "account_valid_until": valid_until_text,
        "observed_no_later_than_decision": True,
        "valid_through_run_end": True,
        "historical_backfill_used": False,
    }


def _rates(
    account_commission_snapshot: Mapping[str, Any],
) -> Tuple[Decimal, Decimal, Dict[str, Any]]:
    try:
        spot = account_commission_snapshot["commission_context"]["spot"]
        rates = spot["authoritative_no_discount_rates"]
        semantics = spot["authoritative_cost_semantics"]
        discount = spot["bnb_discount_scenario_or_null"]
    except (KeyError, TypeError) as error:
        raise PaperCostBindingError(
            "PAPER_COST_RATE_CONTEXT_INVALID"
        ) from error
    buy = _decimal(rates.get("taker_buy"))
    sell = _decimal(rates.get("taker_sell"))
    if buy > 1 or sell > 1:
        raise PaperCostBindingError("PAPER_COST_RATE_CONTEXT_INVALID")
    if semantics != "NO_DISCOUNT_UNTIL_PAYMENT_ASSET_AND_BALANCE_PROVEN":
        raise PaperCostBindingError("PAPER_COST_RATE_CONTEXT_INVALID")
    return buy, sell, {
        "policy_version": _POLICY_VERSION,
        "source": "ACCOUNT_COMMISSION_AUTHORITATIVE_NO_DISCOUNT_RATES",
        "assumed_taker_rate_per_side": "0.0015",
        "account_taker_buy_rate": canonical_decimal(buy),
        "account_taker_sell_rate": canonical_decimal(sell),
        "bnb_discount_applied": False,
        "bnb_discount_scenario_present": discount is not None,
        "signal_changed": False,
        "fill_changed": False,
        "slippage_changed": False,
        "quantity_changed": False,
    }


def _baseline_replay(
    offline_paper_run: Mapping[str, Any],
    taker_buy_rate: Decimal,
    taker_sell_rate: Decimal,
) -> Dict[str, Any]:
    try:
        arm = offline_paper_run["arms"]["baseline"]
        fill = arm["fill"]
        economic = arm["economic_snapshot"]
        fills = economic["fills"]
        points = economic["equity_points"]
        starting = _decimal(
            economic["starting_liquidation_equity_usdt"]
        )
        original_ending = _decimal(
            economic["ending_liquidation_equity_usdt"]
        )
        source_market_hash = offline_paper_run["market"]["market_hash"]
        decision_hash = arm["decision"]["prediction_business_hash"]
    except (KeyError, TypeError, IndexError) as error:
        raise PaperCostBindingError(
            "PAPER_COST_BASELINE_SOURCE_INVALID"
        ) from error
    if (
        not isinstance(fills, list)
        or len(fills) > 1
        or not isinstance(points, list)
        or len(points) != 2
    ):
        raise PaperCostBindingError(
            "PAPER_COST_BASELINE_SOURCE_INVALID"
        )
    final_point = points[-1]
    if not isinstance(final_point, Mapping):
        raise PaperCostBindingError(
            "PAPER_COST_BASELINE_SOURCE_INVALID"
        )

    zero = Decimal("0")
    entry_notional = zero
    exit_notional = zero
    assumed_entry_fee = zero
    assumed_exit_fee = zero
    account_entry_fee = zero
    account_exit_fee = zero
    executed = bool(fills)
    if executed:
        if (
            len(fills) != 1
            or fill.get("status")
            not in ("FILLED", "PARTIALLY_FILLED_VISIBLE_LIQUIDITY")
            or not isinstance(fills[0], Mapping)
            or fills[0].get("side") != "BUY"
        ):
            raise PaperCostBindingError(
                "PAPER_COST_FILL_SCOPE_INVALID"
            )
        recorded_fill = fills[0]
        quantity = _decimal(recorded_fill.get("quantity"))
        price = _decimal(recorded_fill.get("price"))
        entry_notional = _decimal(fill.get("notional_usdt"))
        assumed_entry_fee = _decimal(
            recorded_fill.get("fee_value_usdt")
        )
        exit_notional = _decimal(
            final_point.get("spot_notional_usdt")
        )
        assumed_exit_fee = _decimal(
            final_point.get("expected_exit_fee_accrued_usdt")
        )
        with localcontext() as context:
            context.prec = 50
            if (
                quantity <= 0
                or price <= 0
                or quantity * price != entry_notional
                or assumed_entry_fee
                != entry_notional * _ASSUMED_TAKER_RATE
                or assumed_exit_fee
                != exit_notional * _ASSUMED_TAKER_RATE
                or _decimal(fill.get("fee_value_usdt"))
                != assumed_entry_fee
            ):
                raise PaperCostBindingError(
                    "PAPER_COST_ASSUMPTION_REPLAY_MISMATCH"
                )
            account_entry_fee = entry_notional * taker_buy_rate
            account_exit_fee = exit_notional * taker_sell_rate
    else:
        if (
            fill.get("status")
            in ("FILLED", "PARTIALLY_FILLED_VISIBLE_LIQUIDITY")
            or _decimal(
                final_point.get("expected_exit_fee_accrued_usdt")
            )
            != zero
            or _decimal(final_point.get("spot_notional_usdt")) != zero
        ):
            raise PaperCostBindingError(
                "PAPER_COST_NO_TRADE_REPLAY_MISMATCH"
            )

    with localcontext() as context:
        context.prec = 50
        assumed_total = assumed_entry_fee + assumed_exit_fee
        account_total = account_entry_fee + account_exit_fee
        fee_delta = account_total - assumed_total
        rebased_ending = original_ending - fee_delta
        original_change = original_ending - starting
        rebased_change = rebased_ending - starting
    render = canonical_decimal
    return {
        "status": "REPLAYED_FILLED" if executed else "REPLAYED_NO_TRADE",
        "source_fill_status": fill.get("status"),
        "source_market_hash": source_market_hash,
        "source_prediction_business_hash": decision_hash,
        "entry_notional_usdt": render(entry_notional),
        "conservative_exit_notional_usdt": render(exit_notional),
        "assumed_entry_fee_usdt": render(assumed_entry_fee),
        "assumed_exit_fee_usdt": render(assumed_exit_fee),
        "assumed_total_fee_usdt": render(assumed_total),
        "account_entry_fee_usdt": render(account_entry_fee),
        "account_exit_fee_usdt": render(account_exit_fee),
        "account_total_fee_usdt": render(account_total),
        "account_minus_assumed_fee_usdt": render(fee_delta),
        "original_starting_liquidation_equity_usdt": render(starting),
        "original_ending_liquidation_equity_usdt": render(
            original_ending
        ),
        "account_costed_ending_liquidation_equity_usdt": render(
            rebased_ending
        ),
        "original_liquidation_net_change_usdt": render(original_change),
        "account_costed_liquidation_net_change_usdt": render(
            rebased_change
        ),
        "only_fee_values_changed": True,
        "realized_pnl_claimed": False,
    }


def build_paper_account_cost_binding(
    *,
    offline_paper_run: Mapping[str, Any],
    offline_paper_trusted_attestation_hash: str,
    account_commission_snapshot: Mapping[str, Any],
    account_commission_trusted_attestation_hash: str,
    created_at: str,
) -> Dict[str, Any]:
    """Build a replayable fee-only Paper/account-cost binding."""

    if not isinstance(offline_paper_run, Mapping) or not isinstance(
        account_commission_snapshot, Mapping
    ):
        raise PaperCostBindingError("PAPER_COST_SOURCE_INVALID")
    _validate_sources(
        offline_paper_run,
        offline_paper_trusted_attestation_hash,
        account_commission_snapshot,
        account_commission_trusted_attestation_hash,
    )
    pit = _pit_binding(offline_paper_run, account_commission_snapshot)
    buy_rate, sell_rate, policy = _rates(
        account_commission_snapshot
    )
    baseline = _baseline_replay(
        offline_paper_run, buy_rate, sell_rate
    )
    created, created_text = _utc(created_at)
    paper_recorded, _ = _utc(offline_paper_run["recorded_at"])
    account_recorded, _ = _utc(
        account_commission_snapshot["recorded_at"]
    )
    if created < max(paper_recorded, account_recorded):
        raise PaperCostBindingError(
            "PAPER_COST_CREATED_BEFORE_SOURCES"
        )
    paper_trust = _hash(
        offline_paper_trusted_attestation_hash,
        "PAPER_COST_PAPER_TRUST_HASH_INVALID",
    )
    account_trust = _hash(
        account_commission_trusted_attestation_hash,
        "PAPER_COST_ACCOUNT_TRUST_HASH_INVALID",
    )
    identity = {
        "policy_version": _POLICY_VERSION,
        "offline_paper_run_hash": offline_paper_run["run_hash"],
        "account_commission_snapshot_hash": (
            account_commission_snapshot["snapshot_hash"]
        ),
        "paper_trusted_attestation_hash": paper_trust,
        "account_trusted_attestation_hash": account_trust,
    }
    binding = {
        "$schema": "./paper-account-cost-binding-v1.schema.json",
        "schema_version": "1.0.0",
        "binding_id": stable_id("paper_cost_binding", identity),
        "binding_hash": "",
        "created_at": created_text,
        "source_attestations": {
            "offline_paper_trusted_attestation_hash": paper_trust,
            "account_commission_trusted_attestation_hash": account_trust,
            "copies_are_lineage_not_independent_proof": True,
        },
        "offline_paper_run": deepcopy(dict(offline_paper_run)),
        "account_commission_snapshot": deepcopy(
            dict(account_commission_snapshot)
        ),
        "pit_binding": pit,
        "fee_policy": policy,
        "baseline_cost_replay": baseline,
        "ai_cost_replay": {
            "status": "NOT_RUN_NO_APPROVED_MODEL",
            "fee_replay_performed": False,
            "paired_increment_claimed": False,
        },
        "security_boundary": {
            "network_requests_made": 0,
            "credentials_read": False,
            "account_balances_read": False,
            "orders_submitted": False,
            "source_signal_changed": False,
            "source_fill_changed": False,
            "source_market_changed": False,
        },
        "paper_eligibility": "COST_REPLAY_ONLY_NOT_LONGITUDINAL",
        "production_eligibility": "NOT_APPROVED",
        "profitability_eligibility": (
            "INSUFFICIENT_DURATION_EXECUTION_AND_AI"
        ),
        "warnings": list(_WARNINGS),
    }
    binding["binding_hash"] = artifact_self_hash(
        binding, "binding_hash"
    )
    if tuple(_binding_validator().iter_errors(binding)):
        raise PaperCostBindingError(
            "PAPER_COST_BINDING_SCHEMA_INVALID"
        )
    return binding


def paper_account_cost_binding_trust_hash(
    binding: Mapping[str, Any],
) -> str:
    try:
        return business_hash(
            {
                "attestation_type": _ATTESTATION_TYPE,
                "binding_id": binding["binding_id"],
                "binding_hash": binding["binding_hash"],
                "offline_paper_run_hash": binding[
                    "offline_paper_run"
                ]["run_hash"],
                "account_commission_snapshot_hash": binding[
                    "account_commission_snapshot"
                ]["snapshot_hash"],
                "source_attestations": binding["source_attestations"],
            }
        )
    except (KeyError, TypeError):
        return ""


def paper_account_cost_binding_reasons(
    binding: Mapping[str, Any],
    trusted_binding_attestation_hash: str,
    *,
    offline_paper_trusted_attestation_hash: str,
    account_commission_trusted_attestation_hash: str,
) -> Tuple[str, ...]:
    if not isinstance(binding, Mapping):
        return ("PAPER_COST_BINDING_INVALID",)
    reasons = []
    try:
        if tuple(_binding_validator().iter_errors(binding)):
            reasons.append("PAPER_COST_BINDING_SCHEMA_INVALID")
        if artifact_self_hash(
            binding, "binding_hash"
        ) != binding.get("binding_hash"):
            reasons.append("PAPER_COST_BINDING_SELF_HASH_MISMATCH")
        if (
            paper_account_cost_binding_trust_hash(binding)
            != trusted_binding_attestation_hash
        ):
            reasons.append("PAPER_COST_BINDING_TRUST_HASH_MISMATCH")
        rebuilt = build_paper_account_cost_binding(
            offline_paper_run=binding["offline_paper_run"],
            offline_paper_trusted_attestation_hash=(
                offline_paper_trusted_attestation_hash
            ),
            account_commission_snapshot=binding[
                "account_commission_snapshot"
            ],
            account_commission_trusted_attestation_hash=(
                account_commission_trusted_attestation_hash
            ),
            created_at=binding["created_at"],
        )
        if rebuilt != binding:
            reasons.append("PAPER_COST_BINDING_REPLAY_MISMATCH")
    except (
        KeyError,
        TypeError,
        ValueError,
        PaperCostBindingError,
    ):
        reasons.append("PAPER_COST_BINDING_REPLAY_INVALID")
    return tuple(sorted(set(reasons)))
