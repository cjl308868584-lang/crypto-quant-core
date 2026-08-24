"""Pure, fixture-only signed-position simulation for replacement research."""

import copy
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, DecimalException, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, localcontext
from typing import Mapping

from .canonical import canonical_decimal, stable_id, utc_datetime
from .challenger_replacement_binance_simulation_input import _metadata
from .challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from .evidence import artifact_self_hash
from .instruments import MarketType


_ZERO_HASH = "0" * 64
_QUOTE_QUANTUM = Decimal("0.00000001")
_FIXED_CONTEXT = Context(prec=50)
_SNAPSHOT_KEYS = {
    "snapshot_version", "snapshot_hash", "parent_snapshot_hash_or_null",
    "opportunity_id_or_null", "position_state", "position_certainty", "cash",
    "signed_quantity", "entry_price_or_null", "entry_time", "isolated_margin",
    "contract_multiplier", "instrument_metadata_hash_or_null", "realized_pnl",
    "unrealized_pnl", "cumulative_fees", "cumulative_funding",
    "marked_equity", "peak_equity", "day_start_date_or_null",
    "day_start_equity", "gross_exposure", "risk_state",
    "active_order_or_null", "protective_stop_or_null",
    "reverse_blocked_until_next_opportunity", "unresolved_intent_ids",
    "economic_gap_locked",
}
class ChallengerReplacementSimulationError(ValueError):
    """The deterministic fixture transition failed closed."""

    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code
def _invalid(reason="CHALLENGER_REPLACEMENT_SIMULATION_INPUT_INVALID"):
    raise ChallengerReplacementSimulationError(reason)

def _fixed_decimal(function):
    def wrapped(*args, **kwargs):
        try:
            with localcontext(_FIXED_CONTEXT):
                return function(*args, **kwargs)
        except DecimalException as error:
            raise ChallengerReplacementSimulationError(
                "CHALLENGER_REPLACEMENT_SIMULATION_INPUT_INVALID"
            ) from error
    return wrapped


def _d(value):
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        _invalid()
    if not number.is_finite() or (number.is_zero() and number.is_signed()):
        _invalid()
    return number
def _c(value):
    return canonical_decimal(value)
def _money(value, *, debit=False):
    rounding = ROUND_CEILING if debit else ROUND_FLOOR
    return value.quantize(_QUOTE_QUANTUM, rounding=rounding)
def _signed_cashflow(value):
    return -_money(-value, debit=True) if value < 0 else _money(value)
def _finalize_decision(decision):
    identity = {
        key: value
        for key, value in decision.items()
        if key not in {"decision_id", "decision_hash"}
    }
    decision["decision_id"] = stable_id(
        "challenger_replacement_simulation_decision", identity
    )
    decision["decision_hash"] = artifact_self_hash(decision, "decision_hash")
    return decision
def _time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        _invalid()
    if parsed.tzinfo is None or utc_datetime(parsed) != value:
        _invalid()
    return parsed.astimezone(timezone.utc)


def _valid_context(plan, contract):
    try:
        return (
            isinstance(plan, Mapping)
            and isinstance(contract, Mapping)
            and contract == build_challenger_replacement_simulation_contract(
                plan=plan
            )
        )
    except (KeyError, TypeError, ValueError):
        return False
def _with_hash(snapshot):
    value = copy.deepcopy(snapshot)
    value["snapshot_hash"] = artifact_self_hash(value, "snapshot_hash")
    return value
def build_challenger_replacement_genesis_snapshot(*, plan, contract):
    """Build the sole 100-USDT, verified-flat fixture genesis."""

    if not _valid_context(plan, contract):
        _invalid("CHALLENGER_REPLACEMENT_SIMULATION_SNAPSHOT_INVALID")
    return _with_hash({
        "snapshot_version": "1.0.0", "snapshot_hash": _ZERO_HASH,
        "parent_snapshot_hash_or_null": None, "opportunity_id_or_null": None,
        "position_state": "FLAT", "position_certainty": "VERIFIED",
        "cash": "100", "signed_quantity": "0",
        "entry_price_or_null": None, "entry_time": None,
        "isolated_margin": "0", "contract_multiplier": "0",
        "instrument_metadata_hash_or_null": None,
        "realized_pnl": "0", "unrealized_pnl": "0",
        "cumulative_fees": "0", "cumulative_funding": "0",
        "marked_equity": "100", "peak_equity": "100",
        "day_start_date_or_null": None,
        "day_start_equity": "100", "gross_exposure": "0",
        "risk_state": "RISK_CLEAR", "active_order_or_null": None,
        "protective_stop_or_null": None,
        "reverse_blocked_until_next_opportunity": False,
        "unresolved_intent_ids": [], "economic_gap_locked": False,
    })


def _validate_snapshot(snapshot):
    if (
        not isinstance(snapshot, Mapping)
        or set(snapshot) != _SNAPSHOT_KEYS
        or snapshot.get("snapshot_hash")
        != artifact_self_hash(snapshot, "snapshot_hash")
        or snapshot.get("position_state") not in {"FLAT", "SPOT_LONG", "PERP_SHORT"}
        or snapshot.get("position_certainty") not in {"VERIFIED", "UNRESOLVED"}
        or not isinstance(snapshot.get("unresolved_intent_ids"), list)
    ):
        _invalid("CHALLENGER_REPLACEMENT_SIMULATION_SNAPSHOT_INVALID")
    decimal_fields = (
        "cash", "signed_quantity", "isolated_margin", "contract_multiplier",
        "realized_pnl", "unrealized_pnl", "cumulative_fees",
        "cumulative_funding", "marked_equity", "peak_equity",
        "day_start_equity", "gross_exposure",
    )
    try:
        numbers = {name: _d(snapshot[name]) for name in decimal_fields}
        if any(_c(numbers[name]) != snapshot[name] for name in decimal_fields):
            raise ValueError("noncanonical snapshot decimal")
    except (ChallengerReplacementSimulationError, ValueError):
        _invalid("CHALLENGER_REPLACEMENT_SIMULATION_SNAPSHOT_INVALID")
    quantity, margin = numbers["signed_quantity"], numbers["isolated_margin"]
    if snapshot["risk_state"] not in {
        "RISK_CLEAR", "STOP_NEW_RISK", "GROSS_DRIFT_REDUCTION_REQUIRED",
        "STAGE_FAILED_LOCKED",
    }:
        _invalid("CHALLENGER_REPLACEMENT_SIMULATION_SNAPSHOT_INVALID")
    if snapshot["position_state"] == "FLAT":
        invalid = (
            quantity != 0 or margin != 0 or snapshot["entry_price_or_null"] is not None
            or snapshot["entry_time"] is not None
            or snapshot["instrument_metadata_hash_or_null"] is not None
            or snapshot["protective_stop_or_null"] is not None
            or snapshot["active_order_or_null"] is not None
        )
    elif snapshot["position_state"] == "SPOT_LONG":
        invalid = quantity <= 0 or margin != 0
    else:
        invalid = quantity >= 0 or margin <= 0
    stop = snapshot["protective_stop_or_null"]
    if snapshot["position_state"] != "FLAT" and stop is None:
        invalid = invalid or snapshot["risk_state"] != "STAGE_FAILED_LOCKED"
    if snapshot["position_state"] != "FLAT" and stop is not None:
        product = "spot" if snapshot["position_state"] == "SPOT_LONG" else "perpetual"
        expected = {
            "stop_intent_id", "stop_attempt_id", "stop_client_order_id",
            "product", "side", "reduce_only", "quantity", "trigger_price",
            "status",
        }
        try:
            trigger = _d(stop["trigger_price"])
            entry = _d(snapshot["entry_price_or_null"])
            valid_stop = (
                isinstance(stop, Mapping)
                and set(stop) == expected
                and stop["product"] == product
                and stop["side"] == ("SELL" if product == "spot" else "BUY")
                and stop["reduce_only"] is (product == "perpetual")
                and stop["quantity"] == _c(abs(quantity))
                and stop["trigger_price"] == _c(trigger)
                and trigger > 0
                and ((trigger < entry) if product == "spot" else (trigger > entry))
                and stop["status"] == "CONFIRMED_FIXTURE"
                and stop["stop_attempt_id"] == stable_id(
                    "replacement_attempt",
                    {"intent_id": stop["stop_intent_id"], "attempt_ordinal": 1},
                )
                and stop["stop_client_order_id"] == stable_id(
                    "replacement_client",
                    {"intent_id": stop["stop_intent_id"], "product": product},
                )
                and all(
                    isinstance(stop[name], str)
                    and stop[name].startswith(prefix)
                    and len(stop[name]) == len(prefix) + 64
                    and all(c in "0123456789abcdef" for c in stop[name][len(prefix):])
                    for name, prefix in (
                        ("stop_intent_id", "replacement_stop_"),
                        ("stop_attempt_id", "replacement_attempt_"),
                        ("stop_client_order_id", "replacement_client_"),
                    )
                )
            )
        except (KeyError, TypeError, ChallengerReplacementSimulationError, ValueError):
            try:
                trigger = _d(stop["trigger"])
                entry = _d(snapshot["entry_price_or_null"])
                valid_stop = (
                    isinstance(stop, Mapping)
                    and set(stop) == {"status", "trigger"}
                    and stop["status"] == "CONFIRMED_FIXTURE"
                    and stop["trigger"] == _c(trigger)
                    and ((trigger < entry) if product == "spot" else (trigger > entry))
                )
            except (KeyError, TypeError, ChallengerReplacementSimulationError, ValueError):
                valid_stop = False
        invalid = invalid or not valid_stop
    if invalid:
        _invalid("CHALLENGER_REPLACEMENT_SIMULATION_SNAPSHOT_INVALID")
    if snapshot["position_certainty"] == "UNRESOLVED" and (
        not snapshot["unresolved_intent_ids"]
        or snapshot["risk_state"] != "STAGE_FAILED_LOCKED"
    ):
        _invalid("CHALLENGER_REPLACEMENT_SIMULATION_SNAPSHOT_INVALID")
    return copy.deepcopy(dict(snapshot))
def _validate_source(source, plan, contract):
    if (
        not _valid_context(plan, contract)
        or not isinstance(source, Mapping)
        or source.get("input_hash") != artifact_self_hash(source, "input_hash")
        or source.get("plan")
        != {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]}
        or source.get("simulation_contract")
        != {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
        }
    ):
        _invalid()
    return source
def _indicators(source):
    closes = tuple(_d(bar["close"]) for bar in source["bars"])
    prior = sum(closes[:20], Decimal("0")) / Decimal("20")
    latest, lagged = closes[-1], closes[-6]
    long_signal = latest >= prior * Decimal("1.005") and latest > lagged
    short_signal = latest <= prior * Decimal("0.995") and latest < lagged
    if long_signal and short_signal:
        _invalid("DECISION_POLICY_AMBIGUOUS")
    return {
        "prior_sma20": _c(prior),
        "latest_close": _c(latest),
        "lag5_close": _c(lagged),
        "long_signal": long_signal,
        "short_signal": short_signal,
    }
def _mark(snapshot, source):
    state, quantity = snapshot["position_state"], _d(snapshot["signed_quantity"])
    cash = _d(snapshot["cash"])
    if state == "FLAT":
        unrealized, equity, gross = Decimal("0"), cash, Decimal("0")
    elif state == "SPOT_LONG":
        price = _d(source["quotes"]["spot"]["bid"])
        multiplier = _d(snapshot["contract_multiplier"])
        unrealized = quantity * multiplier * (
            price - _d(snapshot["entry_price_or_null"])
        )
        equity = cash + quantity * multiplier * price
        gross = (
            Decimal("0")
            if equity <= 0
            else quantity * multiplier * price / equity
        )
    else:
        price = _d(source["quotes"]["perpetual"]["mark"])
        multiplier = _d(snapshot["contract_multiplier"])
        unrealized = quantity * multiplier * (
            price - _d(snapshot["entry_price_or_null"])
        )
        equity = cash + unrealized
        gross = (
            Decimal("0")
            if equity <= 0
            else abs(quantity) * multiplier * price / equity
        )
    snapshot["unrealized_pnl"] = _c(_money(unrealized))
    snapshot["marked_equity"] = _c(_money(equity))
    snapshot["gross_exposure"] = _c(gross)


def _risk(snapshot, source):
    scheduled = _time(source["opportunity"]["scheduled_for"])
    _mark(snapshot, source)
    equity = _d(snapshot["marked_equity"])
    prior_peak = _d(snapshot["peak_equity"])
    if snapshot["risk_state"] == "GROSS_DRIFT_REDUCTION_REQUIRED":
        snapshot["risk_state"] = "RISK_CLEAR"
    if snapshot["day_start_date_or_null"] != scheduled.date().isoformat():
        snapshot["day_start_date_or_null"] = scheduled.date().isoformat()
        snapshot["day_start_equity"] = _c(equity)
        if snapshot["risk_state"] == "STOP_NEW_RISK":
            snapshot["risk_state"] = "RISK_CLEAR"
    daily_loss = max(Decimal("0"), _d(snapshot["day_start_equity"]) - equity)
    drawdown = max(Decimal("0"), prior_peak - equity)
    snapshot["peak_equity"] = _c(max(prior_peak, equity))
    margin_exhausted = equity <= 0 or (
        snapshot["position_state"] == "PERP_SHORT"
        and _d(snapshot["cash"]) - _d(snapshot["isolated_margin"]) < 0
    )
    if snapshot["economic_gap_locked"] or margin_exhausted or drawdown >= Decimal("5"):
        snapshot["risk_state"] = "STAGE_FAILED_LOCKED"
    elif (
        snapshot["position_state"] != "FLAT"
        and _d(snapshot["gross_exposure"]) > Decimal("0.5")
    ):
        snapshot["risk_state"] = "GROSS_DRIFT_REDUCTION_REQUIRED"
    elif daily_loss >= Decimal("2"):
        snapshot["risk_state"] = "STOP_NEW_RISK"
    return daily_loss, drawdown


def _prepare_boundary(snapshot, source):
    funding = Decimal("0")
    if (
        snapshot["position_state"] == "PERP_SHORT"
        and source["funding"]["rate_or_null"] is not None
    ):
        funding = _signed_cashflow(
            -_d(snapshot["signed_quantity"])
            * _d(snapshot["contract_multiplier"])
            * _d(source["quotes"]["perpetual"]["mark"])
            * _d(source["funding"]["rate_or_null"])
        )
        snapshot["cash"] = _c(_d(snapshot["cash"]) + funding)
        snapshot["cumulative_funding"] = _c(
            _d(snapshot["cumulative_funding"]) + funding
        )
    daily_loss, drawdown = _risk(snapshot, source)
    return funding, daily_loss, drawdown


def _decision(source, snapshot, previous_hash, daily_loss, drawdown, plan):
    indicators = _indicators(source)
    state = snapshot["position_state"]
    scheduled = _time(source["opportunity"]["scheduled_for"])
    if snapshot["economic_gap_locked"]:
        action = "HOLD_FLAT" if state == "FLAT" else "RISK_FLATTEN"
        reason, approval = "ECONOMIC_GAP_LOCKED", "STAGE_FAILED_LOCKED"
    elif snapshot["risk_state"] == "STAGE_FAILED_LOCKED":
        exhausted = _d(snapshot["marked_equity"]) <= 0 or (
            state == "PERP_SHORT"
            and _d(snapshot["cash"]) - _d(snapshot["isolated_margin"]) < 0
        )
        action = "RISK_FLATTEN"
        reason = "SIMULATION_MARGIN_EXHAUSTED" if exhausted else "DRAWDOWN_LIMIT"
        approval = "STAGE_FAILED_LOCKED"
    elif snapshot["risk_state"] == "GROSS_DRIFT_REDUCTION_REQUIRED":
        action, reason, approval = (
            "RISK_FLATTEN", "GROSS_EXPOSURE_DRIFT", "REDUCE_ONLY"
        )
    elif state == "FLAT" and snapshot["risk_state"] == "STOP_NEW_RISK":
        action, reason, approval = (
            "HOLD_FLAT", "DAILY_LOSS_LIMIT", "STOP_NEW_RISK"
        )
    elif state == "FLAT":
        approval = "RISK_APPROVED"
        if indicators["long_signal"]:
            action, reason = "OPEN_SPOT_LONG", "LONG_ENTRY_SIGNAL"
        elif indicators["short_signal"]:
            action, reason = "OPEN_PERP_SHORT", "SHORT_ENTRY_SIGNAL"
        else:
            action, reason = "HOLD_FLAT", "NO_ENTRY_SIGNAL"
    else:
        approval = (
            "REDUCE_OR_HOLD_ONLY"
            if snapshot["risk_state"] != "RISK_CLEAR"
            else "RISK_APPROVED"
        )
        held = scheduled - _time(snapshot["entry_time"])
        close = (
            "CLOSE_SPOT_LONG"
            if state == "SPOT_LONG"
            else "CLOSE_PERP_SHORT"
        )
        hold = (
            "HOLD_SPOT_LONG"
            if state == "SPOT_LONG"
            else "HOLD_PERP_SHORT"
        )
        if held < timedelta(hours=8):
            action, reason = hold, "MINIMUM_HOLD_ACTIVE"
        elif held >= timedelta(hours=24):
            action, reason = close, "VERTICAL_EXIT"
        elif state == "SPOT_LONG" and _d(indicators["latest_close"]) <= _d(
            indicators["prior_sma20"]
        ):
            action, reason = close, "LONG_EXIT_SIGNAL"
        elif state == "PERP_SHORT" and _d(indicators["latest_close"]) >= _d(
            indicators["prior_sma20"]
        ):
            action, reason = close, "SHORT_EXIT_SIGNAL"
        else:
            action, reason = hold, "POSITION_HOLD"
    decision = {
        "decision_id": _ZERO_HASH,
        "decision_hash": _ZERO_HASH,
        "opportunity_id": source["opportunity"]["opportunity_id"],
        "source_hash": source["input_hash"],
        "plan": {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]},
        "policy_bindings": {
            "decision_policy_hash": plan["decision_policy"]["policy_hash"],
            "risk_policy_hash": plan["risk_policy"]["policy_hash"],
        },
        "previous_snapshot_hash": previous_hash,
        "position_before": state,
        "indicators": indicators,
        "action": action,
        "reason_code": reason,
        "risk_approval": approval,
        "daily_loss": _c(daily_loss),
        "drawdown": _c(drawdown),
    }
    return _finalize_decision(decision)


@_fixed_decimal
def compute_challenger_replacement_simulation_decision(
    *, source, previous_projection, plan, contract
):
    """Compute the frozen dual-direction decision without side effects."""

    source = _validate_source(source, plan, contract)
    snapshot = _validate_snapshot(previous_projection)
    _, daily_loss, drawdown = _prepare_boundary(snapshot, source)
    return _decision(source, snapshot, previous_projection["snapshot_hash"],
                     daily_loss, drawdown, plan)

def _instrument(source, state):
    product = "spot" if state == "SPOT_LONG" else "perpetual"
    market = MarketType.SPOT if product == "spot" else MarketType.USDT_PERP
    record = source["instruments"][product]
    metadata = _metadata(record["metadata"], market_type=market)
    if metadata.metadata_hash != record["metadata_hash"]:
        _invalid()
    return product, metadata


def _fill_price(source, product, side, metadata, contract):
    quote = source["quotes"][product]
    reference = _d(quote["ask"] if side == "BUY" else quote["bid"])
    return _adverse_fill_price(reference, side, metadata, contract)


def _adverse_fill_price(reference, side, metadata, contract):
    slip = _d(contract["market_order_slippage_per_side"])
    if side == "BUY":
        raw, rounding = reference * (1 + slip), ROUND_CEILING
    else:
        raw, rounding = reference * (1 - slip), ROUND_FLOOR
    return (raw / metadata.price_tick).to_integral_value(rounding=rounding) * metadata.price_tick


def _close_position(snapshot, source, contract, *, fill_or_null=None):
    state = snapshot["position_state"]
    product, metadata = _instrument(source, state)
    if metadata.metadata_hash != snapshot["instrument_metadata_hash_or_null"] or _d(snapshot["contract_multiplier"]) != metadata.contract_multiplier:
        _invalid("SIMULATION_INSTRUMENT_METADATA_CONFLICT")
    side = "SELL" if product == "spot" else "BUY"
    fill = (
        _fill_price(source, product, side, metadata, contract)
        if fill_or_null is None
        else fill_or_null
    )
    quantity = abs(_d(snapshot["signed_quantity"]))
    notional = quantity * metadata.contract_multiplier * fill
    fee = _money(notional * metadata.taker_fee, debit=True)
    realized = _signed_cashflow(_d(snapshot["signed_quantity"]) * metadata.contract_multiplier * (fill - _d(snapshot["entry_price_or_null"])))
    cash = _money(
        _d(snapshot["cash"])
        + (notional - fee if product == "spot" else realized - fee)
    )
    snapshot.update(position_state="FLAT", cash=_c(cash), signed_quantity="0", entry_price_or_null=None, entry_time=None, isolated_margin="0", contract_multiplier="0", instrument_metadata_hash_or_null=None, realized_pnl=_c(_d(snapshot["realized_pnl"]) + realized), cumulative_fees=_c(_d(snapshot["cumulative_fees"]) + fee), protective_stop_or_null=None, reverse_blocked_until_next_opportunity=True)
    return {
        "fill_price": _c(fill),
        "quantity": _c(quantity),
        "notional": _c(notional),
        "fee": _c(fee),
        "realized_pnl": _c(realized),
    }


def _opening_quantity(source, product, metadata, fill, contract, snapshot):
    equity = _d(snapshot["marked_equity"])
    approved = min(_d(contract["capital_limit_usdt"]), equity * _d(contract["gross_exposure_limit"]))
    quantity = min(metadata.max_quantity, approved / (fill * metadata.contract_multiplier))
    quantity = (quantity / metadata.quantity_step).to_integral_value(rounding=ROUND_FLOOR) * metadata.quantity_step
    while quantity >= metadata.min_quantity:
        notional = quantity * metadata.contract_multiplier * fill
        fee = _money(notional * metadata.taker_fee, debit=True)
        mark = _d(source["quotes"][product]["bid" if product == "spot" else "mark"])
        marked = equity - fee + (
            Decimal("0") if product == "perpetual"
            else quantity * metadata.contract_multiplier * (mark - fill)
        )
        gross = (
            Decimal("Infinity") if marked <= 0
            else quantity * metadata.contract_multiplier * mark / marked
        )
        daily = max(Decimal("0"), _d(snapshot["day_start_equity"]) - marked)
        drawdown = max(Decimal("0"), _d(snapshot["peak_equity"]) - marked)
        if notional >= metadata.min_notional and gross <= _d(
            contract["gross_exposure_limit"]
        ):
            return (quantity, None) if (
                daily < Decimal("2") and drawdown < Decimal("5")
            ) else (Decimal("0"), "PROJECTED_RISK_LIMIT")
        quantity -= metadata.quantity_step
    return Decimal("0"), "NO_TRADE"


@_fixed_decimal
def simulate_challenger_replacement_opportunity(
    *, source, previous_projection, plan, contract, build_identity
):
    """Apply one normal deterministic fixture transition entirely in memory."""

    source = _validate_source(source, plan, contract)
    if source.get("build_identity") != dict(build_identity):
        _invalid()
    previous = _validate_snapshot(previous_projection)
    snapshot = copy.deepcopy(previous)
    snapshot["parent_snapshot_hash_or_null"] = previous["snapshot_hash"]
    snapshot["opportunity_id_or_null"] = source["opportunity"]["opportunity_id"]
    snapshot["reverse_blocked_until_next_opportunity"] = False
    funding, daily_loss, drawdown = _prepare_boundary(snapshot, source)
    decision = _decision(source, snapshot, previous["snapshot_hash"],
                         daily_loss, drawdown, plan)
    action = decision["action"]
    accounting = {"fill_price": None, "quantity": "0", "notional": "0", "fee": "0", "realized_pnl": "0", "funding_cashflow": _c(funding)}
    if action in {"OPEN_SPOT_LONG", "OPEN_PERP_SHORT"}:
        state = "SPOT_LONG" if action == "OPEN_SPOT_LONG" else "PERP_SHORT"
        product, metadata = _instrument(source, state)
        side = "BUY" if product == "spot" else "SELL"
        fill = _fill_price(source, product, side, metadata, contract)
        quantity, rejection = _opening_quantity(
            source, product, metadata, fill, contract, snapshot
        )
        if quantity <= 0:
            decision.update(
                action="HOLD_FLAT",
                reason_code=rejection,
                risk_approval=(
                    "STOP_NEW_RISK" if rejection == "PROJECTED_RISK_LIMIT"
                    else "RISK_APPROVED"
                ),
            )
            decision = _finalize_decision(decision)
            snapshot = _with_hash(snapshot)
            return {"decision": decision, "accounting": accounting,
                    "next_snapshot": snapshot}
        notional = quantity * metadata.contract_multiplier * fill
        fee = _money(notional * metadata.taker_fee, debit=True)
        snapshot.update(
            position_state=state,
            signed_quantity=_c(quantity if product == "spot" else -quantity),
            entry_price_or_null=_c(fill),
            entry_time=source["opportunity"]["scheduled_for"],
            contract_multiplier=_c(metadata.contract_multiplier),
            instrument_metadata_hash_or_null=metadata.metadata_hash,
            cumulative_fees=_c(_d(snapshot["cumulative_fees"]) + fee),
            cash=_c(_money(
                _d(snapshot["cash"]) - notional - fee
                if product == "spot" else _d(snapshot["cash"]) - fee
            )),
            isolated_margin=_c(_money(
                notional / _d(contract["configured_leverage"]), debit=True,
            ) if product == "perpetual" else Decimal("0")),
            protective_stop_or_null={"status": "CONFIRMED_FIXTURE", "trigger": _c(fill * (Decimal("0.98") if product == "spot" else Decimal("1.02")))},
        )
        accounting.update(fill_price=_c(fill), quantity=_c(quantity), notional=_c(notional), fee=_c(fee))
    elif action in {"CLOSE_SPOT_LONG", "CLOSE_PERP_SHORT", "RISK_FLATTEN"} and snapshot["position_state"] != "FLAT":
        accounting.update(_close_position(snapshot, source, contract))
    _risk(snapshot, source)
    snapshot = _with_hash(snapshot)
    return {"decision": decision, "accounting": accounting, "next_snapshot": snapshot}


@_fixed_decimal
def _simulate_challenger_replacement_v072_transition(
    *, source, previous_projection, plan, contract, build_identity
):
    """Return the released transition plus private v0.72 protective-stop terms."""

    source = _validate_source(source, plan, contract)
    previous = _validate_snapshot(previous_projection)
    stop = previous.get("protective_stop_or_null")
    if previous["position_state"] != "FLAT" and isinstance(stop, Mapping):
        product = "spot" if previous["position_state"] == "SPOT_LONG" else "perpetual"
        expected_keys = {
            "stop_intent_id", "stop_attempt_id", "stop_client_order_id",
            "product", "side", "reduce_only", "quantity", "trigger_price", "status",
        }
        if set(stop) == expected_keys and stop.get("status") == "CONFIRMED_FIXTURE" and stop.get("product") == product:
            trigger = _d(stop["trigger_price"])
            latest = source["bars"][-1]
            triggered = (
                _d(latest["low"]) <= trigger
                if product == "spot"
                else _d(latest["high"]) >= trigger
            )
            if triggered:
                snapshot = copy.deepcopy(previous)
                snapshot["parent_snapshot_hash_or_null"] = previous["snapshot_hash"]
                snapshot["opportunity_id_or_null"] = source["opportunity"]["opportunity_id"]
                snapshot["reverse_blocked_until_next_opportunity"] = False
                funding, daily_loss, drawdown = _prepare_boundary(snapshot, source)
                decision = _decision(source, snapshot, previous["snapshot_hash"], daily_loss, drawdown, plan)
                decision.update(
                    action=("STOP_CLOSE_SPOT_LONG" if product == "spot" else "STOP_CLOSE_PERP_SHORT"),
                    reason_code="PROTECTIVE_STOP_TRIGGERED",
                    risk_approval="REDUCE_ONLY",
                )
                decision = _finalize_decision(decision)
                market = MarketType.SPOT if product == "spot" else MarketType.USDT_PERP
                metadata = _metadata(source["instruments"][product]["metadata"], market_type=market)
                opened = _d(latest["open"])
                gap = min(opened, trigger) if product == "spot" else max(opened, trigger)
                side = "SELL" if product == "spot" else "BUY"
                fill = _adverse_fill_price(gap, side, metadata, contract)
                accounting = {
                    "fill_price": None, "quantity": "0", "notional": "0",
                    "fee": "0", "realized_pnl": "0",
                    "funding_cashflow": _c(funding),
                }
                accounting.update(_close_position(snapshot, source, contract, fill_or_null=fill))
                _risk(snapshot, source)
                return {
                    "decision": decision,
                    "accounting": accounting,
                    "next_snapshot": _with_hash(snapshot),
                    "protective_stop_terms_or_null": None,
                    "triggered_stop_or_null": {**dict(stop), "bar_open": latest["open"], "bar_high": latest["high"], "bar_low": latest["low"], "gap_reference": _c(gap)},
                }
    result = simulate_challenger_replacement_opportunity(
        source=source,
        previous_projection=previous_projection,
        plan=plan,
        contract=contract,
        build_identity=build_identity,
    )
    action = result["decision"]["action"]
    if action not in {"OPEN_SPOT_LONG", "OPEN_PERP_SHORT"}:
        return {**result, "protective_stop_terms_or_null": None, "triggered_stop_or_null": None}
    product = "spot" if action == "OPEN_SPOT_LONG" else "perpetual"
    market = MarketType.SPOT if product == "spot" else MarketType.USDT_PERP
    metadata = _metadata(source["instruments"][product]["metadata"], market_type=market)
    entry = _d(result["accounting"]["fill_price"])
    rounding = ROUND_FLOOR if product == "spot" else ROUND_CEILING
    factor = Decimal("0.98") if product == "spot" else Decimal("1.02")
    trigger = (
        (entry * factor / metadata.price_tick).to_integral_value(rounding=rounding)
        * metadata.price_tick
    )
    return {
        **result,
        "protective_stop_terms_or_null": {
            "product": product,
            "side": "SELL" if product == "spot" else "BUY",
            "reduce_only": product == "perpetual",
            "quantity": result["accounting"]["quantity"],
            "trigger_price": _c(trigger),
        },
        "triggered_stop_or_null": None,
    }
