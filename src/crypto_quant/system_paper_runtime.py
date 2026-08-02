"""Pure single-slot System Paper coordinator.

The coordinator consumes already captured public evidence and returns one
canonical result.  It performs no file, network, credential, account, real
Broker, or real order operation.
"""

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from jsonschema import Draft202012Validator

from .canonical import (
    business_hash,
    canonical_decimal,
    canonical_json,
    stable_id,
    utc_datetime,
)
from .errors import ContractError
from .evidence import artifact_self_hash
from .instruments import OrderSide, instrument_metadata_from_payload
from .offline_paper import build_baseline_paper_decision
from .orders import OrderState
from .risk import DrawdownBand, DrawdownPolicy, DrawdownState
from .system_paper_broker import (
    FillScenario,
    SimulatedBroker,
    SimulatedMarketEvidence,
    SimulatedOrderCommand,
    fill_scenario_from_payload,
    fill_scenario_payload,
)
from .system_paper_plan import system_paper_plan_reasons


_ZERO_HASH = "0" * 64
_SLOT_SCHEMA = "system-paper-slot-result-v1.schema.json"
_MAX_SLOT_BYTES = 1024 * 1024
_SNAPSHOT_KEYS = {
    "schema_version",
    "snapshot_hash",
    "plan_hash",
    "last_slot_id_or_null",
    "last_slot_hash_or_null",
    "processed_slot_ids",
    "cash_usdt",
    "position_quantity",
    "position_cost_usdt",
    "average_entry_price_or_null",
    "cumulative_realized_pnl_usdt",
    "cumulative_fees_usdt",
    "marked_equity_usdt",
    "peak_equity_usdt",
    "risk_state",
    "active_order_or_null",
}
_MARKET_BUNDLE_KEYS = {
    "bundle_hash",
    "provider",
    "observed_at",
    "instrument_metadata_schema_version",
    "instrument_metadata",
    "closed_4h_klines",
    "bbo",
    "source_receipt_hashes",
}


class SystemPaperRuntimeError(ValueError):
    """A slot input or deterministic invariant failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class SystemPaperSlotInputs:
    plan: Mapping[str, Any]
    scheduled_for: str
    public_market_bundle: Mapping[str, Any]
    previous_runtime_snapshot: Mapping[str, Any]
    fill_scenario: FillScenario


@lru_cache(maxsize=1)
def _slot_validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas",
        _SLOT_SCHEMA,
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _decimal(value: object, reason: str) -> Decimal:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise SystemPaperRuntimeError(reason)
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise SystemPaperRuntimeError(reason) from error
    if not number.is_finite() or (number.is_zero() and number.is_signed()):
        raise SystemPaperRuntimeError(reason)
    return number


def _json_native(value: object) -> Any:
    """Normalize replay evidence to the exact JSON-native representation."""

    return json.loads(canonical_json(value))


def _time(value: object) -> Tuple[datetime, str]:
    if not isinstance(value, str):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_TIME_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_TIME_INVALID")
    parsed = parsed.astimezone(timezone.utc)
    parsed = parsed.replace(microsecond=(parsed.microsecond // 1000) * 1000)
    return parsed, utc_datetime(parsed)


def _verified_plan(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(plan, Mapping):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_PLAN_INVALID")
    reasons = system_paper_plan_reasons(plan)
    if reasons:
        raise SystemPaperRuntimeError(reasons[0])
    return plan


def build_initial_system_paper_runtime_snapshot(
    plan: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build the sole empty state allowed before the first natural slot."""

    verified = _verified_plan(plan)
    equity = verified["capital_policy"]["starting_virtual_equity_usdt"]
    snapshot: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "snapshot_hash": _ZERO_HASH,
        "plan_hash": verified["plan_hash"],
        "last_slot_id_or_null": None,
        "last_slot_hash_or_null": None,
        "processed_slot_ids": [],
        "cash_usdt": equity,
        "position_quantity": "0",
        "position_cost_usdt": "0",
        "average_entry_price_or_null": None,
        "cumulative_realized_pnl_usdt": "0",
        "cumulative_fees_usdt": "0",
        "marked_equity_usdt": equity,
        "peak_equity_usdt": equity,
        "risk_state": "NORMAL",
        "active_order_or_null": None,
    }
    snapshot["snapshot_hash"] = artifact_self_hash(snapshot, "snapshot_hash")
    return snapshot


def _verify_snapshot(
    snapshot: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(snapshot, Mapping) or set(snapshot) != _SNAPSHOT_KEYS:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID")
    value = dict(snapshot)
    if value.get("plan_hash") != plan["plan_hash"]:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_PLAN_MISMATCH")
    if value.get("snapshot_hash") != artifact_self_hash(value, "snapshot_hash"):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_SNAPSHOT_HASH_MISMATCH")
    processed = value.get("processed_slot_ids")
    if (
        not isinstance(processed, list)
        or len(processed) != len(set(processed))
        or any(not isinstance(item, str) or not item for item in processed)
    ):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID")
    if not processed:
        if value != build_initial_system_paper_runtime_snapshot(plan):
            raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_GENESIS_MISMATCH")
    else:
        expected_slot_prefix = "system_paper_slot_"
        if (
            value["last_slot_id_or_null"] != processed[-1]
            or any(
                not item.startswith(expected_slot_prefix)
                or len(item) != len(expected_slot_prefix) + 64
                or any(
                    character not in "0123456789abcdef"
                    for character in item[len(expected_slot_prefix):]
                )
                for item in processed
            )
            or not isinstance(value["last_slot_hash_or_null"], str)
            or len(value["last_slot_hash_or_null"]) != 64
            or any(
                character not in "0123456789abcdef"
                for character in value["last_slot_hash_or_null"]
            )
        ):
            raise SystemPaperRuntimeError(
                "SYSTEM_PAPER_RUNTIME_PARENT_BINDING_INVALID"
            )
    cash = _decimal(value["cash_usdt"], "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID")
    position = _decimal(
        value["position_quantity"],
        "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
    )
    position_cost = _decimal(
        value["position_cost_usdt"],
        "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
    )
    _decimal(
        value["cumulative_realized_pnl_usdt"],
        "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
    )
    cumulative_fees = _decimal(
        value["cumulative_fees_usdt"],
        "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
    )
    marked = _decimal(
        value["marked_equity_usdt"],
        "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
    )
    peak = _decimal(
        value["peak_equity_usdt"],
        "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
    )
    if (
        cash < 0
        or position < 0
        or position_cost < 0
        or cumulative_fees < 0
        or marked < 0
        or peak <= 0
    ):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID")
    average = None
    if value["average_entry_price_or_null"] is not None:
        average = _decimal(
            value["average_entry_price_or_null"],
            "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
        )
    if (position == 0) != (average is None) or (average is not None and average <= 0):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID")
    if position_cost != (Decimal("0") if average is None else position * average):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID")
    if value["risk_state"] not in ("NORMAL", "LOCKED"):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID")
    active_order = value["active_order_or_null"]
    if active_order is not None:
        if not isinstance(active_order, Mapping) or set(active_order) != {
            "local_order_id",
            "state",
            "remaining_quantity",
            "result_hash",
        }:
            raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID")
        if active_order["state"] not in (
            "ACKNOWLEDGED",
            "PARTIALLY_FILLED",
            "CANCEL_PENDING",
            "UNKNOWN",
        ):
            raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID")
        if _decimal(
            active_order["remaining_quantity"],
            "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
        ) <= 0:
            raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID")
        for field_name in ("local_order_id", "result_hash"):
            if not isinstance(active_order[field_name], str) or not active_order[field_name]:
                raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID")
    return value


def _verify_bundle(
    bundle: Mapping[str, Any],
    plan: Mapping[str, Any],
    scheduled_dt: datetime,
    scheduled_for: str,
):
    if not isinstance(bundle, Mapping) or set(bundle) != _MARKET_BUNDLE_KEYS:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_MARKET_BUNDLE_INVALID")
    value = dict(bundle)
    if value.get("bundle_hash") != artifact_self_hash(value, "bundle_hash"):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_MARKET_BUNDLE_HASH_MISMATCH")
    if value.get("provider") != plan["market_data_policy"]["provider"]:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_MARKET_PROVIDER_MISMATCH")
    _, observed_at = _time(value.get("observed_at"))
    if observed_at != scheduled_for:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_MARKET_BUNDLE_TIME_MISMATCH")
    klines = value.get("closed_4h_klines")
    if not isinstance(klines, list) or len(klines) < 21:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_MARKET_KLINES_INVALID")
    for row in klines:
        if not isinstance(row, Mapping) or set(row) != {"close", "source_row_hash"}:
            raise SystemPaperRuntimeError("SYSTEM_PAPER_MARKET_KLINES_INVALID")
        _decimal(row["close"], "SYSTEM_PAPER_MARKET_KLINES_INVALID")
        source_hash = row["source_row_hash"]
        if not isinstance(source_hash, str) or len(source_hash) != 64 or any(
            character not in "0123456789abcdef" for character in source_hash
        ):
            raise SystemPaperRuntimeError("SYSTEM_PAPER_MARKET_KLINES_INVALID")
    bbo = value.get("bbo")
    if not isinstance(bbo, Mapping) or set(bbo) != {"bid_price", "ask_price"}:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_MARKET_BBO_INVALID")
    bid = _decimal(bbo["bid_price"], "SYSTEM_PAPER_MARKET_BBO_INVALID")
    ask = _decimal(bbo["ask_price"], "SYSTEM_PAPER_MARKET_BBO_INVALID")
    if bid <= 0 or ask <= 0 or bid > ask:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_MARKET_BBO_INVALID")
    receipts = value.get("source_receipt_hashes")
    if (
        not isinstance(receipts, list)
        or len(receipts) != 4
        or len(set(receipts)) != 4
        or any(
            not isinstance(item, str)
            or len(item) != 64
            or any(character not in "0123456789abcdef" for character in item)
            for item in receipts
        )
    ):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_MARKET_RECEIPTS_INVALID")
    try:
        metadata_payload = dict(value["instrument_metadata"])
        embedded_schema_version = metadata_payload.pop("schema_version")
        if embedded_schema_version != value["instrument_metadata_schema_version"]:
            raise ContractError("instrument metadata schema versions differ")
        metadata = instrument_metadata_from_payload(
            metadata_payload,
            schema_version=value["instrument_metadata_schema_version"],
        )
    except (KeyError, TypeError, ContractError) as error:
        raise SystemPaperRuntimeError(
            "SYSTEM_PAPER_MARKET_METADATA_INVALID"
        ) from error
    expected_instrument_id = "BINANCE:SPOT:ETHUSDT"
    if (
        plan["scope"]["market"] != "SPOT"
        or plan["scope"]["symbol"] != "ETHUSDT"
        or metadata.instrument_id != expected_instrument_id
        or metadata.exchange != "BINANCE"
        or metadata.market_type.value != "SPOT"
        or metadata.symbol != "ETHUSDT"
        or metadata.contract_multiplier != Decimal("1")
    ):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_MARKET_INSTRUMENT_MISMATCH")
    try:
        metadata.assert_effective(scheduled_dt)
    except ContractError as error:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_MARKET_METADATA_STALE") from error
    return value, metadata, bid, ask


def _drawdown_policy(plan: Mapping[str, Any]) -> DrawdownPolicy:
    bands = []
    for item in plan["risk_policy"]["drawdown_bands"]:
        bands.append(
            DrawdownBand(
                lower=Decimal(item["lower"]),
                upper=(
                    Decimal("Infinity")
                    if item["upper"] is None
                    else Decimal(item["upper"])
                ),
                state=DrawdownState(item["state"]),
            )
        )
    return DrawdownPolicy(bands)


def _ledger_entries(
    *,
    slot_id: str,
    side: Optional[OrderSide],
    filled_quantity: Decimal,
    fill_price: Optional[Decimal],
    fee_usdt: Decimal,
    average_entry_price_before: Optional[Decimal],
) -> Tuple[
    Tuple[Dict[str, str], ...],
    Decimal,
    Decimal,
    Decimal,
    Decimal,
]:
    if filled_quantity == 0:
        return (), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")
    if fill_price is None or fill_price <= 0:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_LEDGER_FILL_INVALID")
    if side not in (OrderSide.BUY, OrderSide.SELL):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_LEDGER_SIDE_INVALID")
    notional = filled_quantity * fill_price
    entries_list = []

    def add(leg: int, account: str, side_value: str, amount: Decimal) -> None:
        entries_list.append(
            {
                "entry_id": stable_id(
                    "paper_ledger",
                    {"slot": slot_id, "leg": leg},
                ),
                "account": account,
                "side": side_value,
                "amount_usdt": canonical_decimal(amount),
            }
        )

    position_cost_relieved = Decimal("0")
    realized_pnl = Decimal("0")
    if side is OrderSide.BUY:
        add(1, "ETH_POSITION_COST", "DEBIT", notional)
        add(2, "VIRTUAL_CASH", "CREDIT", notional)
    else:
        if average_entry_price_before is None:
            raise SystemPaperRuntimeError("SYSTEM_PAPER_LEDGER_COST_BASIS_MISSING")
        position_cost_relieved = filled_quantity * average_entry_price_before
        realized_pnl = notional - position_cost_relieved
        add(1, "VIRTUAL_CASH", "DEBIT", notional)
        add(2, "ETH_POSITION_COST", "CREDIT", position_cost_relieved)
        if realized_pnl > 0:
            add(3, "REALIZED_GAIN", "CREDIT", realized_pnl)
        elif realized_pnl < 0:
            add(3, "REALIZED_LOSS", "DEBIT", -realized_pnl)
    fee_leg = len(entries_list) + 1
    add(fee_leg, "TAKER_FEE_EXPENSE", "DEBIT", fee_usdt)
    add(fee_leg + 1, "VIRTUAL_CASH", "CREDIT", fee_usdt)
    entries = tuple(entries_list)
    debits = sum(
        (Decimal(item["amount_usdt"]) for item in entries if item["side"] == "DEBIT"),
        Decimal("0"),
    )
    credits = sum(
        (Decimal(item["amount_usdt"]) for item in entries if item["side"] == "CREDIT"),
        Decimal("0"),
    )
    return entries, debits, credits, position_cost_relieved, realized_pnl


def system_paper_slot_hash(result: Mapping[str, Any]) -> str:
    """Hash a result while breaking the slot↔snapshot identity cycle."""

    value = copy.deepcopy(dict(result))
    value["slot_hash"] = _ZERO_HASH
    snapshot = value.get("runtime_snapshot")
    if isinstance(snapshot, dict):
        snapshot["snapshot_hash"] = _ZERO_HASH
        snapshot["last_slot_hash_or_null"] = _ZERO_HASH
    return business_hash(value)


def run_system_paper_slot(inputs: SystemPaperSlotInputs) -> Dict[str, Any]:
    if not isinstance(inputs, SystemPaperSlotInputs):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_INPUTS_INVALID")
    plan = _verified_plan(inputs.plan)
    scheduled_dt, scheduled_for = _time(inputs.scheduled_for)
    previous = _verify_snapshot(inputs.previous_runtime_snapshot, plan)
    bundle, metadata, bid, ask = _verify_bundle(
        inputs.public_market_bundle,
        plan,
        scheduled_dt,
        scheduled_for,
    )
    if not isinstance(inputs.fill_scenario, FillScenario):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_FILL_SCENARIO_INVALID")

    slot_id = stable_id(
        "system_paper_slot",
        {"plan_hash": plan["plan_hash"], "scheduled_for": scheduled_for},
    )
    if slot_id in previous["processed_slot_ids"]:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_DUPLICATE")
    if previous["active_order_or_null"] is not None:
        raise SystemPaperRuntimeError(
            "SYSTEM_PAPER_ACTIVE_ORDER_RECONCILIATION_REQUIRED"
        )

    market_hash = bundle["bundle_hash"]
    decision, target = build_baseline_paper_decision(
        bundle["closed_4h_klines"],
        scheduled_dt,
        market_hash,
    )
    replay_decision, _ = build_baseline_paper_decision(
        bundle["closed_4h_klines"],
        scheduled_dt,
        market_hash,
    )
    decision_hash = business_hash(decision)
    if (
        decision["proposal"]["instrument_id"] != metadata.instrument_id
        or decision["target_position"]["instrument_id"] != metadata.instrument_id
        or (target is not None and target.instrument_id != metadata.instrument_id)
    ):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_DECISION_INSTRUMENT_MISMATCH")

    cash_before = _decimal(previous["cash_usdt"], "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID")
    position_before = _decimal(
        previous["position_quantity"],
        "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
    )
    peak_before = _decimal(
        previous["peak_equity_usdt"],
        "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
    )
    marked_before = cash_before + position_before * bid
    peak_at_decision = max(peak_before, marked_before)
    drawdown_ratio = (
        Decimal("0")
        if peak_at_decision == 0
        else (peak_at_decision - marked_before) / peak_at_decision
    )
    drawdown_state = _drawdown_policy(plan).classify(drawdown_ratio)
    risk_locked = previous["risk_state"] == "LOCKED" or drawdown_state in (
        DrawdownState.HALT,
        DrawdownState.HARD_BOUNDARY,
    )
    reason_codes = []
    if drawdown_state is DrawdownState.HARD_BOUNDARY:
        reason_codes.append("DRAWDOWN_HARD_BOUNDARY")
    elif drawdown_state is DrawdownState.HALT:
        reason_codes.append("DRAWDOWN_HALT")
    if previous["risk_state"] == "LOCKED":
        reason_codes.append("PARENT_RISK_LOCKED")

    broker_result = None
    order_side: Optional[OrderSide] = None
    current_notional = position_before * bid
    requested_target_notional = current_notional
    if target is not None and target.target_notional_usdt_or_null is not None:
        requested_target_notional = target.target_notional_usdt_or_null
    if previous["risk_state"] == "LOCKED" or drawdown_state in (
        DrawdownState.HALT,
        DrawdownState.HARD_BOUNDARY,
    ):
        approved_target_notional = Decimal("0")
    elif drawdown_state is DrawdownState.REDUCE:
        approved_target_notional = min(
            current_notional,
            requested_target_notional * Decimal("0.5"),
        )
        reason_codes.append("DRAWDOWN_REDUCE")
    elif drawdown_state is DrawdownState.WARNING:
        approved_target_notional = min(
            current_notional,
            requested_target_notional,
        )
        reason_codes.append("DRAWDOWN_WARNING_FREEZE_INCREASES")
    else:
        approved_target_notional = min(
            requested_target_notional,
            marked_before,
        )

    target_quantity = (
        approved_target_notional / (ask if approved_target_notional >= current_notional else bid)
        if approved_target_notional > 0
        else Decimal("0")
    )
    quantity_delta = target_quantity - position_before
    if abs(quantity_delta) * (ask if quantity_delta > 0 else bid) >= metadata.min_notional:
        order_side = OrderSide.BUY if quantity_delta > 0 else OrderSide.SELL
        requested_quantity = abs(quantity_delta)
        risk_increasing = order_side is OrderSide.BUY
        delta_notional = requested_quantity * ask if risk_increasing else None
        broker = SimulatedBroker(inputs.fill_scenario)
        broker_result = broker.submit(
            SimulatedOrderCommand(
                scheduled_for=scheduled_dt,
                instrument_id=metadata.instrument_id,
                side=order_side,
                order_type="MARKET",
                time_in_force_or_null=None,
                requested_quantity=requested_quantity,
                requested_price_or_null=None,
                risk_increasing=risk_increasing,
                reduce_only=False,
                approved_notional_usdt_or_null=delta_notional,
                risk_approved=True,
            ),
            SimulatedMarketEvidence(
                observed_at=scheduled_dt,
                instrument_metadata=metadata,
                best_bid_price=bid,
                best_ask_price=ask,
                last_trade_price=Decimal(bundle["closed_4h_klines"][-1]["close"]),
                market_bundle_hash=market_hash,
            ),
        )
        if broker_result.state in (
            OrderState.ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
            OrderState.CANCEL_PENDING,
            OrderState.UNKNOWN,
        ):
            broker_result = broker.reconcile(broker_result.local_order_id)

    filled_quantity = (
        Decimal("0")
        if broker_result is None
        else broker_result.cumulative_filled_quantity
    )
    fill_price = None if broker_result is None else broker_result.average_fill_price
    fee_usdt = Decimal("0") if broker_result is None else broker_result.fee_usdt
    previous_cost = _decimal(
        previous["position_cost_usdt"],
        "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
    )
    average_entry_before = (
        None
        if previous["average_entry_price_or_null"] is None
        else Decimal(previous["average_entry_price_or_null"])
    )
    cumulative_realized_before = _decimal(
        previous["cumulative_realized_pnl_usdt"],
        "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
    )
    cumulative_fees_before = _decimal(
        previous["cumulative_fees_usdt"],
        "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
    )
    (
        entries,
        debits,
        credits,
        position_cost_relieved,
        realized_pnl,
    ) = _ledger_entries(
        slot_id=slot_id,
        side=order_side,
        filled_quantity=filled_quantity,
        fill_price=fill_price,
        fee_usdt=fee_usdt,
        average_entry_price_before=average_entry_before,
    )
    if debits != credits:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_LEDGER_IMBALANCE")
    fill_notional = Decimal("0") if fill_price is None else filled_quantity * fill_price
    if order_side is OrderSide.SELL:
        cash_after = cash_before + fill_notional - fee_usdt
        position_after = position_before - filled_quantity
    else:
        cash_after = cash_before - fill_notional - fee_usdt
        position_after = position_before + filled_quantity
    if cash_after < 0 or position_after < 0:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_LEDGER_NEGATIVE_BALANCE")
    position_cost_after = (
        previous_cost + fill_notional
        if order_side is not OrderSide.SELL
        else previous_cost - position_cost_relieved
    )
    cumulative_realized_after = cumulative_realized_before + realized_pnl
    cumulative_fees_after = cumulative_fees_before + fee_usdt
    if position_after == 0:
        average_entry = None
        position_cost_after = Decimal("0")
    elif order_side is OrderSide.SELL:
        average_entry = average_entry_before
    else:
        average_entry = position_cost_after / position_after
    marked_after = cash_after + position_after * bid
    peak_after = max(peak_at_decision, marked_after)
    if broker_result is not None and broker_result.state is OrderState.UNKNOWN:
        risk_locked = True
        reason_codes.append("ORDER_STATE_UNKNOWN")
    elif broker_result is not None and broker_result.state is OrderState.REJECTED:
        reason_codes.append("SIMULATED_ORDER_REJECTED")
    unrealized_pnl = (
        Decimal("0")
        if position_after == 0 or average_entry is None
        else position_after * bid - position_cost_after
    )

    order_payload = None
    if broker_result is not None:
        order_payload = {
            "local_order_id": broker_result.local_order_id,
            "instrument_id": broker_result.instrument_id,
            "side": broker_result.side.value,
            "fill_policy_version": broker_result.fill_policy_version,
            "state": broker_result.state.value,
            "requested_quantity": canonical_decimal(
                broker_result.requested_quantity
            ),
            "filled_quantity": canonical_decimal(filled_quantity),
            "average_fill_price_or_null": (
                None if fill_price is None else canonical_decimal(fill_price)
            ),
            "fee_usdt": canonical_decimal(fee_usdt),
            "event_ids": list(broker_result.event_ids),
            "risk_lock_required": broker_result.risk_lock_required,
            "result_hash": broker_result.result_hash,
        }
    active_order_required = (
        broker_result is not None
        and broker_result.state
        in (
            OrderState.ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
            OrderState.CANCEL_PENDING,
            OrderState.UNKNOWN,
        )
    )

    result: Dict[str, Any] = {
        "$schema": "./system-paper-slot-result-v1.schema.json",
        "schema_version": "1.0.0",
        "slot_id": slot_id,
        "slot_hash": _ZERO_HASH,
        "status": "SYSTEM_PAPER_SLOT_COMPLETED",
        "plan_id": plan["plan_id"],
        "plan_hash": plan["plan_hash"],
        "scheduled_for": scheduled_for,
        "parent_slot_hash_or_null": previous["last_slot_hash_or_null"],
        "market_bundle_hash": market_hash,
        "instrument": {
            "provider": bundle["provider"],
            "instrument_id": metadata.instrument_id,
            "metadata_hash": metadata.metadata_hash,
            "market_type": metadata.market_type.value,
            "symbol": metadata.symbol,
            "contract_multiplier": canonical_decimal(metadata.contract_multiplier),
        },
        "signal": {
            "decision_source": decision["decision_source"],
            "strategy_version": decision["strategy_version"],
            "direction": decision["direction"],
            "recommended_action": decision["recommended_action"],
            "target_id": decision["target_id"],
            "decision_hash": decision_hash,
        },
        "risk": {
            "state": "LOCKED" if risk_locked else "NORMAL",
            "drawdown_state": drawdown_state.value,
            "drawdown_ratio": canonical_decimal(drawdown_ratio),
            "requested_target_notional_usdt": canonical_decimal(
                requested_target_notional
            ),
            "approved_target_notional_usdt": canonical_decimal(
                approved_target_notional
            ),
            "reason_codes": sorted(set(reason_codes)),
        },
        "order": order_payload,
        "ledger": {
            "entries": list(entries),
            "debits_usdt": canonical_decimal(debits),
            "credits_usdt": canonical_decimal(credits),
            "position_cost_relieved_usdt": canonical_decimal(
                position_cost_relieved
            ),
            "position_cost_after_usdt": canonical_decimal(position_cost_after),
            "realized_pnl_usdt": canonical_decimal(realized_pnl),
            "cumulative_realized_pnl_usdt": canonical_decimal(
                cumulative_realized_after
            ),
            "cumulative_fees_usdt": canonical_decimal(cumulative_fees_after),
            "unrealized_pnl_usdt": canonical_decimal(unrealized_pnl),
            "balanced": debits == credits,
        },
        "reconciliation": {
            "expected_position_quantity": canonical_decimal(position_after),
            "actual_position_quantity": canonical_decimal(position_after),
            "unexplained_position_difference": "0",
            "ledger_imbalance_usdt": canonical_decimal(debits - credits),
            "status": (
                "OPEN_ORDER_RECONCILIATION_REQUIRED"
                if active_order_required
                else "RECONCILED"
            ),
        },
        "runtime_snapshot": {},
        "replay_inputs": {
            "plan": _json_native(plan),
            "scheduled_for": scheduled_for,
            "public_market_bundle": _json_native(bundle),
            "previous_runtime_snapshot": _json_native(previous),
            "fill_scenario": fill_scenario_payload(inputs.fill_scenario),
        },
        "replay": {
            "decision_hash_match": business_hash(replay_decision) == decision_hash,
            "market_bundle_hash_match": True,
            "full_slot_hash_match": True,
        },
        "safety_counts": {
            "credential_reads": 0,
            "account_requests": 0,
            "real_broker_calls": 0,
            "real_order_writes": 0,
        },
        "warnings": ["CANARY_NOT_AUTHORIZED", "SYSTEM_PAPER_NOT_STARTED"],
    }
    provisional_snapshot = {
        "schema_version": "1.0.0",
        "snapshot_hash": _ZERO_HASH,
        "plan_hash": plan["plan_hash"],
        "last_slot_id_or_null": slot_id,
        "last_slot_hash_or_null": _ZERO_HASH,
        "processed_slot_ids": previous["processed_slot_ids"] + [slot_id],
        "cash_usdt": canonical_decimal(cash_after),
        "position_quantity": canonical_decimal(position_after),
        "position_cost_usdt": canonical_decimal(position_cost_after),
        "average_entry_price_or_null": (
            None if average_entry is None else canonical_decimal(average_entry)
        ),
        "cumulative_realized_pnl_usdt": canonical_decimal(
            cumulative_realized_after
        ),
        "cumulative_fees_usdt": canonical_decimal(cumulative_fees_after),
        "marked_equity_usdt": canonical_decimal(marked_after),
        "peak_equity_usdt": canonical_decimal(peak_after),
        "risk_state": "LOCKED" if risk_locked else "NORMAL",
        "active_order_or_null": (
            None
            if not active_order_required
            else {
                "local_order_id": broker_result.local_order_id,
                "state": broker_result.state.value,
                "remaining_quantity": canonical_decimal(
                    broker_result.requested_quantity
                    - broker_result.cumulative_filled_quantity
                ),
                "result_hash": broker_result.result_hash,
            }
        ),
    }
    result["runtime_snapshot"] = provisional_snapshot
    result["slot_hash"] = system_paper_slot_hash(result)
    provisional_snapshot["last_slot_hash_or_null"] = result["slot_hash"]
    provisional_snapshot["snapshot_hash"] = artifact_self_hash(
        provisional_snapshot,
        "snapshot_hash",
    )
    if result["slot_hash"] != system_paper_slot_hash(result):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_HASH_UNSTABLE")
    return result


def _strict_slot_json(body: bytes) -> Mapping[str, Any]:
    if not isinstance(body, bytes) or not body or len(body) > _MAX_SLOT_BYTES:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_JSON_INVALID")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SystemPaperRuntimeError(
                    "SYSTEM_PAPER_SLOT_JSON_DUPLICATE_KEY"
                )
            result[key] = value
        return result

    def reject_number(_value):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_JSON_FLOAT_FORBIDDEN")

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except SystemPaperRuntimeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_JSON_INVALID") from error
    if not isinstance(value, Mapping):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_JSON_INVALID")
    return value


def _verify_loaded_slot(
    result: Mapping[str, Any],
    expected_parent_or_null: Optional[Mapping[str, Any]] = None,
) -> None:
    if tuple(_slot_validator().iter_errors(result)):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_SCHEMA_INVALID")
    if result["slot_hash"] != system_paper_slot_hash(result):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_HASH_MISMATCH")
    snapshot = result["runtime_snapshot"]
    if snapshot["snapshot_hash"] != artifact_self_hash(
        snapshot,
        "snapshot_hash",
    ):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_RUNTIME_SNAPSHOT_HASH_MISMATCH")
    if (
        snapshot["last_slot_id_or_null"] != result["slot_id"]
        or snapshot["last_slot_hash_or_null"] != result["slot_hash"]
        or not snapshot["processed_slot_ids"]
        or snapshot["processed_slot_ids"][-1] != result["slot_id"]
    ):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_SNAPSHOT_BINDING_INVALID")
    replay_parent = result["replay_inputs"]["previous_runtime_snapshot"]
    if replay_parent["processed_slot_ids"]:
        if expected_parent_or_null is None:
            raise SystemPaperRuntimeError("SYSTEM_PAPER_PARENT_ARTIFACT_REQUIRED")
        if (
            replay_parent != expected_parent_or_null["runtime_snapshot"]
            or result["parent_slot_hash_or_null"]
            != expected_parent_or_null["slot_hash"]
        ):
            raise SystemPaperRuntimeError(
                "SYSTEM_PAPER_PARENT_ARTIFACT_MISMATCH"
            )
    elif expected_parent_or_null is not None:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_PARENT_CHAIN_INVALID")
    entries = result["ledger"]["entries"]
    debits = sum(
        (
            Decimal(item["amount_usdt"])
            for item in entries
            if item["side"] == "DEBIT"
        ),
        Decimal("0"),
    )
    credits = sum(
        (
            Decimal(item["amount_usdt"])
            for item in entries
            if item["side"] == "CREDIT"
        ),
        Decimal("0"),
    )
    if (
        debits != credits
        or canonical_decimal(debits) != result["ledger"]["debits_usdt"]
        or canonical_decimal(credits) != result["ledger"]["credits_usdt"]
    ):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_LEDGER_IMBALANCE")
    order = result["order"]
    if order is not None:
        order_payload = {
            "local_order_id": order["local_order_id"],
            "instrument_id": order["instrument_id"],
            "side": order["side"],
            "fill_policy_version": order["fill_policy_version"],
            "state": order["state"],
            "requested_quantity": order["requested_quantity"],
            "cumulative_filled_quantity": order["filled_quantity"],
            "average_fill_price": order["average_fill_price_or_null"],
            "fee_usdt": order["fee_usdt"],
            "event_ids": order["event_ids"],
            "risk_lock_required": order["risk_lock_required"],
        }
        if business_hash(order_payload) != order["result_hash"]:
            raise SystemPaperRuntimeError("SYSTEM_PAPER_ORDER_RESULT_HASH_MISMATCH")
    replay_inputs = result["replay_inputs"]
    try:
        replayed = run_system_paper_slot(
            SystemPaperSlotInputs(
                plan=replay_inputs["plan"],
                scheduled_for=replay_inputs["scheduled_for"],
                public_market_bundle=replay_inputs["public_market_bundle"],
                previous_runtime_snapshot=replay_inputs["previous_runtime_snapshot"],
                fill_scenario=fill_scenario_from_payload(
                    replay_inputs["fill_scenario"]
                ),
            )
        )
    except (KeyError, TypeError, ContractError, SystemPaperRuntimeError) as error:
        raise SystemPaperRuntimeError("SYSTEM_PAPER_FULL_REPLAY_INVALID") from error
    if canonical_json(replayed) != canonical_json(result):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_FULL_REPLAY_MISMATCH")


def _load_slot_body(body: bytes) -> Dict[str, Any]:
    result = dict(_strict_slot_json(body))
    canonical = canonical_json(result).encode("utf-8")
    if body not in (canonical, canonical + b"\n"):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_CANONICAL_BYTES_REQUIRED")
    return result


def _read_slot_body(path: Path) -> bytes:
    result_path = Path(path).expanduser()
    if (
        not result_path.is_absolute()
        or result_path.is_symlink()
        or not result_path.is_file()
    ):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_SLOT_PATH_INVALID")
    return result_path.read_bytes()


def load_system_paper_slot_result_bytes(
    body: bytes,
    *,
    parent_result_bodies: Tuple[bytes, ...] = (),
) -> Dict[str, Any]:
    """Verify one canonical slot body against its complete ordered parents."""

    if not isinstance(parent_result_bodies, tuple):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_PARENT_CHAIN_INVALID")
    expected_parent = None
    for parent_body in parent_result_bodies:
        parent = _load_slot_body(parent_body)
        _verify_loaded_slot(parent, expected_parent)
        expected_parent = parent
    result = _load_slot_body(body)
    _verify_loaded_slot(result, expected_parent)
    return result


def load_system_paper_slot_result(
    path: Path,
    *,
    parent_result_paths: Tuple[Path, ...] = (),
) -> Dict[str, Any]:
    """Load a canonical slot only after schema, hashes and balances replay."""

    if not isinstance(parent_result_paths, tuple):
        raise SystemPaperRuntimeError("SYSTEM_PAPER_PARENT_CHAIN_INVALID")
    return load_system_paper_slot_result_bytes(
        _read_slot_body(path),
        parent_result_bodies=tuple(
            _read_slot_body(parent_path) for parent_path in parent_result_paths
        ),
    )
