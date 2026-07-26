"""Exact-Decimal economic accounting over verified ledger snapshots."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Tuple

from .canonical import business_hash, canonical_decimal
from .errors import CanonicalizationError
from .evidence import artifact_self_hash


def economic_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    return artifact_self_hash(snapshot, "snapshot_hash")


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp is not timezone aware")
    return parsed


def _decimal(value: Any) -> Decimal:
    return Decimal(canonical_decimal(value))


def _ordered_unique_facts(
    facts: Any,
    *,
    id_field: str,
    time_field: str,
    start: datetime,
    end: datetime,
    include_start: bool,
) -> Tuple[str, ...]:
    if not isinstance(facts, list):
        return ("ECONOMIC_SNAPSHOT_FACT_LIST_INVALID",)
    reasons = []
    identifiers = []
    previous: Optional[datetime] = None
    for fact in facts:
        if not isinstance(fact, Mapping):
            reasons.append("ECONOMIC_SNAPSHOT_FACT_INVALID")
            continue
        identifiers.append(fact.get(id_field))
        try:
            current = _timestamp(fact.get(time_field))
            if previous is not None and current < previous:
                reasons.append("ECONOMIC_SNAPSHOT_FACT_ORDER_INVALID")
            if current > end or (
                current < start if include_start else current <= start
            ):
                reasons.append("ECONOMIC_SNAPSHOT_FACT_OUTSIDE_WINDOW")
            previous = current
        except (TypeError, ValueError):
            reasons.append("ECONOMIC_SNAPSHOT_FACT_TIME_INVALID")
    if len(identifiers) != len(set(identifiers)):
        reasons.append("ECONOMIC_SNAPSHOT_FACT_ID_DUPLICATE")
    return tuple(reasons)


def _replay_trace_reasons(
    snapshot: Mapping[str, Any],
    fact_specs: Tuple[Tuple[str, str, str, bool], ...],
) -> Tuple[str, ...]:
    if snapshot.get("schema_version") != "1.1.0":
        return ()
    reasons = []
    sequences = []
    for field, id_field, time_field, _ in fact_specs:
        facts = snapshot.get(field)
        if not isinstance(facts, list):
            continue
        canonical_order = []
        for fact in facts:
            if not isinstance(fact, Mapping):
                continue
            sequence = fact.get("source_event_sequence")
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence < 1
            ):
                reasons.append(
                    "ECONOMIC_SNAPSHOT_SOURCE_SEQUENCE_INVALID"
                )
                continue
            sequences.append(sequence)
            try:
                canonical_order.append(
                    (
                        _timestamp(fact.get(time_field)),
                        sequence,
                        str(fact.get(id_field)),
                    )
                )
            except (TypeError, ValueError):
                pass
            if field == "fills" and any(
                not isinstance(fact.get(name), str) or not fact.get(name)
                for name in (
                    "exchange_trade_id",
                    "local_order_id",
                    "venue_order_id",
                )
            ):
                reasons.append("ECONOMIC_SNAPSHOT_FILL_IDENTITY_INVALID")
        if canonical_order != sorted(canonical_order):
            reasons.append("ECONOMIC_SNAPSHOT_FACT_ORDER_INVALID")
    if len(sequences) != len(set(sequences)):
        reasons.append("ECONOMIC_SNAPSHOT_SOURCE_SEQUENCE_DUPLICATE")
    return tuple(reasons)


def economic_snapshot_reasons(
    snapshot: Mapping[str, Any],
) -> Tuple[str, ...]:
    reasons = []
    try:
        computed_hash = economic_snapshot_hash(snapshot)
    except CanonicalizationError:
        computed_hash = ""
        reasons.append("ECONOMIC_SNAPSHOT_NOT_CANONICAL")
    if snapshot.get("snapshot_hash") != computed_hash:
        reasons.append("ECONOMIC_SNAPSHOT_SELF_HASH_MISMATCH")
    if snapshot.get("replay_verified") is not True:
        reasons.append("ECONOMIC_SNAPSHOT_REPLAY_UNVERIFIED")

    scope = snapshot.get("scope")
    if not isinstance(scope, Mapping):
        return tuple(sorted(set(reasons + ["ECONOMIC_SNAPSHOT_SCOPE_INVALID"])))
    if (
        scope.get("evaluation_ledger") == "AI_LEDGER"
        and scope.get("release_route") != "AI_ENHANCED"
    ):
        reasons.append("ECONOMIC_SNAPSHOT_LEDGER_ROUTE_MISMATCH")
    if (
        scope.get("direction"),
        scope.get("venue"),
    ) not in {
        ("LONG", "BINANCE_SPOT"),
        ("SHORT", "BINANCE_USDT_PERP"),
    }:
        reasons.append("ECONOMIC_SNAPSHOT_DIRECTION_VENUE_MISMATCH")
    try:
        start = _timestamp(scope.get("evaluation_window_start"))
        end = _timestamp(scope.get("evaluation_window_end"))
        generated = _timestamp(snapshot.get("generated_at"))
        if end <= start:
            reasons.append("ECONOMIC_SNAPSHOT_WINDOW_NOT_INCREASING")
        if generated < end:
            reasons.append("ECONOMIC_SNAPSHOT_GENERATED_BEFORE_WINDOW_END")
    except (TypeError, ValueError):
        return tuple(
            sorted(set(reasons + ["ECONOMIC_SNAPSHOT_WINDOW_TIME_INVALID"]))
        )

    fact_specs = (
        ("fills", "fill_id", "exchange_event_time", False),
        ("funding_cashflows", "funding_id", "settled_at", False),
        ("external_cash_flows", "flow_id", "occurred_at", False),
        ("allocated_costs", "cost_id", "occurred_at", False),
        ("equity_points", "equity_snapshot_id", "as_of", True),
    )
    for field, id_field, time_field, include_start in fact_specs:
        reasons.extend(
            _ordered_unique_facts(
                snapshot.get(field),
                id_field=id_field,
                time_field=time_field,
                start=start,
                end=end,
                include_start=include_start,
            )
        )
    reasons.extend(_replay_trace_reasons(snapshot, fact_specs))

    equity = snapshot.get("equity_points")
    if isinstance(equity, list) and equity:
        first = equity[0]
        last = equity[-1]
        if isinstance(first, Mapping) and isinstance(last, Mapping):
            try:
                if _timestamp(first.get("as_of")) != start:
                    reasons.append(
                        "ECONOMIC_SNAPSHOT_START_EQUITY_TIME_MISMATCH"
                    )
                if _timestamp(last.get("as_of")) != end:
                    reasons.append(
                        "ECONOMIC_SNAPSHOT_END_EQUITY_TIME_MISMATCH"
                    )
            except (TypeError, ValueError):
                reasons.append("ECONOMIC_SNAPSHOT_EQUITY_TIME_INVALID")
            try:
                if _decimal(first.get("liquidation_equity_usdt")) != _decimal(
                    snapshot.get("starting_liquidation_equity_usdt")
                ):
                    reasons.append(
                        "ECONOMIC_SNAPSHOT_START_EQUITY_VALUE_MISMATCH"
                    )
                if _decimal(last.get("liquidation_equity_usdt")) != _decimal(
                    snapshot.get("ending_liquidation_equity_usdt")
                ):
                    reasons.append(
                        "ECONOMIC_SNAPSHOT_END_EQUITY_VALUE_MISMATCH"
                    )
            except CanonicalizationError:
                reasons.append("ECONOMIC_SNAPSHOT_EQUITY_VALUE_INVALID")
            try:
                if business_hash(snapshot.get("opening_positions")) != (
                    business_hash(first.get("position_cost_bases"))
                ):
                    reasons.append(
                        "ECONOMIC_SNAPSHOT_OPENING_POSITION_MISMATCH"
                    )
            except CanonicalizationError:
                reasons.append(
                    "ECONOMIC_SNAPSHOT_OPENING_POSITION_INVALID"
                )
            current_date = end.date()
            current_day_starts = []
            for point in equity:
                if not isinstance(point, Mapping):
                    continue
                position_cost_bases = point.get("position_cost_bases")
                if isinstance(position_cost_bases, list):
                    position_ids = [
                        position.get("instrument_id")
                        for position in position_cost_bases
                        if isinstance(position, Mapping)
                    ]
                    if len(position_ids) != len(set(position_ids)):
                        reasons.append(
                            "ECONOMIC_SNAPSHOT_POSITION_COST_BASIS_DUPLICATE"
                        )
                    for position in position_cost_bases:
                        if not isinstance(position, Mapping):
                            continue
                        try:
                            quantity = _decimal(
                                position.get("signed_quantity")
                            )
                            average = _decimal(
                                position.get(
                                    "moving_average_entry_price"
                                )
                            )
                            multiplier = _decimal(
                                position.get("contract_multiplier")
                            )
                            if multiplier <= 0 or average < 0:
                                reasons.append(
                                    "ECONOMIC_SNAPSHOT_POSITION_COST_BASIS_INVALID"
                                )
                            if (quantity == 0) != (average == 0):
                                reasons.append(
                                    "ECONOMIC_SNAPSHOT_POSITION_COST_BASIS_INVALID"
                                )
                        except CanonicalizationError:
                            reasons.append(
                                "ECONOMIC_SNAPSHOT_POSITION_COST_BASIS_INVALID"
                            )
                if point.get("conservative_close_verified") is not True:
                    reasons.append(
                        "ECONOMIC_SNAPSHOT_CONSERVATIVE_CLOSE_UNVERIFIED"
                    )
                if point.get("is_utc_day_start") is True:
                    try:
                        point_time = _timestamp(point.get("as_of"))
                        if (
                            point_time.hour != 0
                            or point_time.minute != 0
                            or point_time.second != 0
                            or point_time.microsecond != 0
                        ):
                            reasons.append(
                                "ECONOMIC_SNAPSHOT_DAY_START_NOT_MIDNIGHT"
                            )
                        if point_time.date() == current_date:
                            current_day_starts.append(point)
                    except (TypeError, ValueError):
                        reasons.append(
                            "ECONOMIC_SNAPSHOT_DAY_START_TIME_INVALID"
                        )
            if len(current_day_starts) != 1:
                reasons.append(
                    "ECONOMIC_SNAPSHOT_CURRENT_DAY_START_NOT_UNIQUE"
                )
    else:
        reasons.append("ECONOMIC_SNAPSHOT_EQUITY_POINTS_MISSING")

    opening = snapshot.get("opening_positions")
    if isinstance(opening, list):
        instruments = [
            item.get("instrument_id")
            for item in opening
            if isinstance(item, Mapping)
        ]
        if len(instruments) != len(set(instruments)):
            reasons.append("ECONOMIC_SNAPSHOT_OPENING_POSITION_DUPLICATE")
        for item in opening:
            if not isinstance(item, Mapping):
                continue
            try:
                quantity = _decimal(item.get("signed_quantity"))
                average = _decimal(item.get("moving_average_entry_price"))
                multiplier = _decimal(item.get("contract_multiplier"))
                if multiplier <= 0:
                    reasons.append(
                        "ECONOMIC_SNAPSHOT_CONTRACT_MULTIPLIER_INVALID"
                    )
                if (quantity == 0) != (average == 0):
                    reasons.append(
                        "ECONOMIC_SNAPSHOT_OPENING_COST_BASIS_INVALID"
                    )
            except CanonicalizationError:
                reasons.append("ECONOMIC_SNAPSHOT_OPENING_POSITION_INVALID")
    fills = snapshot.get("fills")
    if isinstance(fills, list):
        for fill in fills:
            if not isinstance(fill, Mapping):
                continue
            try:
                if (
                    _decimal(fill.get("quantity")) <= 0
                    or _decimal(fill.get("price")) <= 0
                    or _decimal(fill.get("contract_multiplier")) <= 0
                    or _decimal(fill.get("fee_value_usdt")) < 0
                ):
                    reasons.append("ECONOMIC_SNAPSHOT_FILL_VALUE_INVALID")
            except CanonicalizationError:
                reasons.append("ECONOMIC_SNAPSHOT_FILL_VALUE_INVALID")
    costs = snapshot.get("allocated_costs")
    if isinstance(costs, list):
        route = scope.get("release_route")
        invalid_scope = (
            "AI_ENHANCED" if route == "BASELINE_ONLY" else "BASELINE_ONLY"
        )
        if any(
            isinstance(cost, Mapping)
            and cost.get("allocation_scope") == invalid_scope
            for cost in costs
        ):
            reasons.append("ECONOMIC_SNAPSHOT_COST_SCOPE_MISMATCH")
    return tuple(sorted(set(reasons)))


def _fail_if_invalid(
    snapshot: Any,
) -> Tuple[Optional[Mapping[str, Any]], Tuple[str, ...]]:
    if not isinstance(snapshot, Mapping):
        return None, ("ECONOMIC_SNAPSHOT_INVALID",)
    reasons = economic_snapshot_reasons(snapshot)
    return (snapshot, ()) if not reasons else (None, reasons)


def fill_based_trading_net_pnl(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    snapshot, reasons = _fail_if_invalid(
        inputs.get("economic_ledger_snapshot")
    )
    if reasons:
        return "FAIL", None, reasons
    positions: Dict[str, Tuple[Decimal, Decimal, Decimal]] = {}
    for opening in snapshot["opening_positions"]:
        positions[opening["instrument_id"]] = (
            _decimal(opening["signed_quantity"]),
            _decimal(opening["moving_average_entry_price"]),
            _decimal(opening["contract_multiplier"]),
        )
    realized = Decimal("0")
    fees = Decimal("0")
    for fill in snapshot["fills"]:
        instrument_id = fill["instrument_id"]
        quantity = _decimal(fill["quantity"])
        price = _decimal(fill["price"])
        multiplier = _decimal(fill["contract_multiplier"])
        delta = quantity if fill["side"] == "BUY" else -quantity
        position, average, known_multiplier = positions.get(
            instrument_id,
            (Decimal("0"), Decimal("0"), multiplier),
        )
        if known_multiplier != multiplier:
            return (
                "FAIL",
                None,
                ("ECONOMIC_CONTRACT_MULTIPLIER_CHANGED",),
            )
        if position == 0 or (position > 0) == (delta > 0):
            new_position = position + delta
            new_average = (
                price
                if position == 0
                else (
                    abs(position) * average + abs(delta) * price
                )
                / abs(new_position)
            )
        else:
            if abs(delta) > abs(position):
                return "FAIL", None, ("ECONOMIC_FILL_CROSSES_ZERO",)
            closed = abs(delta)
            realized += (
                (price - average)
                if position > 0
                else (average - price)
            ) * closed * multiplier
            new_position = position + delta
            new_average = average if new_position != 0 else Decimal("0")
        positions[instrument_id] = (
            new_position,
            new_average,
            multiplier,
        )
        fees += _decimal(fill["fee_value_usdt"])
    funding = sum(
        (
            _decimal(item["signed_amount_usdt"])
            for item in snapshot["funding_cashflows"]
        ),
        Decimal("0"),
    )
    return "COMPUTED", canonical_decimal(realized - fees + funding), ()


def period_economic_pnl(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    snapshot, reasons = _fail_if_invalid(
        inputs.get("economic_ledger_snapshot")
    )
    if reasons:
        return "FAIL", None, reasons
    external = sum(
        (
            _decimal(item["signed_amount_usdt"])
            for item in snapshot["external_cash_flows"]
        ),
        Decimal("0"),
    )
    costs = sum(
        (
            _decimal(item["amount_usdt"])
            for item in snapshot["allocated_costs"]
        ),
        Decimal("0"),
    )
    trading = (
        _decimal(snapshot["ending_liquidation_equity_usdt"])
        - _decimal(snapshot["starting_liquidation_equity_usdt"])
        - external
    )
    return "COMPUTED", canonical_decimal(trading - costs), ()


def cash_flow_adjusted_daily_loss(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    snapshot, reasons = _fail_if_invalid(
        inputs.get("economic_ledger_snapshot")
    )
    if reasons:
        return "FAIL", None, reasons
    equity = snapshot["equity_points"]
    current = equity[-1]
    current_time = _timestamp(current["as_of"])
    day_start = next(
        point
        for point in equity
        if point["is_utc_day_start"]
        and _timestamp(point["as_of"]).date() == current_time.date()
    )
    denominator = _decimal(day_start["marked_equity_usdt"])
    if denominator <= 0:
        return "FAIL", None, ("DAILY_LOSS_DENOMINATOR_NONPOSITIVE",)
    day_start_time = _timestamp(day_start["as_of"])
    flows = sum(
        (
            _decimal(item["signed_amount_usdt"])
            for item in snapshot["external_cash_flows"]
            if day_start_time < _timestamp(item["occurred_at"]) <= current_time
        ),
        Decimal("0"),
    )
    ratio = (
        _decimal(current["marked_equity_usdt"])
        - denominator
        - flows
    ) / denominator
    return "COMPUTED", canonical_decimal(ratio), ()


def cash_flow_adjusted_max_drawdown(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    snapshot, reasons = _fail_if_invalid(
        inputs.get("economic_ledger_snapshot")
    )
    if reasons:
        return "FAIL", None, reasons
    window_start = _timestamp(
        snapshot["scope"]["evaluation_window_start"]
    )
    high_watermark: Optional[Decimal] = None
    maximum = Decimal("0")
    for point in snapshot["equity_points"]:
        as_of = _timestamp(point["as_of"])
        external = sum(
            (
                _decimal(item["signed_amount_usdt"])
                for item in snapshot["external_cash_flows"]
                if window_start < _timestamp(item["occurred_at"]) <= as_of
            ),
            Decimal("0"),
        )
        costs = sum(
            (
                _decimal(item["amount_usdt"])
                for item in snapshot["allocated_costs"]
                if window_start < _timestamp(item["occurred_at"]) <= as_of
            ),
            Decimal("0"),
        )
        adjusted = (
            _decimal(point["liquidation_equity_usdt"])
            - external
            - costs
        )
        if adjusted <= 0:
            return (
                "FAIL",
                None,
                ("ECONOMIC_EQUITY_NONPOSITIVE",),
            )
        if high_watermark is None or adjusted > high_watermark:
            high_watermark = adjusted
        drawdown = (high_watermark - adjusted) / high_watermark
        maximum = max(maximum, drawdown)
    return "COMPUTED", canonical_decimal(maximum), ()


def worst_case_gross_exposure_ratio(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    snapshot, reasons = _fail_if_invalid(
        inputs.get("economic_ledger_snapshot")
    )
    if reasons:
        return "FAIL", None, reasons
    maximum = Decimal("0")
    for point in snapshot["equity_points"]:
        equity = _decimal(point["marked_equity_usdt"])
        if equity <= 0:
            return (
                "FAIL",
                None,
                ("MARKED_EQUITY_NONPOSITIVE",),
            )
        gross = sum(
            (
                _decimal(point[field])
                for field in (
                    "spot_notional_usdt",
                    "perp_notional_usdt",
                    "active_order_risk_increasing_notional_usdt",
                    "active_order_unknown_notional_usdt",
                )
            ),
            Decimal("0"),
        )
        maximum = max(maximum, gross / equity)
    return "COMPUTED", canonical_decimal(maximum), ()
