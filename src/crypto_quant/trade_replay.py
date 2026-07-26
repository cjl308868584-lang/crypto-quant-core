"""Deterministic source-path analysis for complete-trade replay."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .canonical import business_hash, canonical_decimal
from .economics import economic_snapshot_reasons
from .statistics import (
    cash_flow_adjusted_economic_log_growth,
    statistical_series_reasons,
)


_SCOPE_FIELDS = (
    "account_id",
    "evaluation_ledger",
    "release_route",
    "direction",
    "venue",
    "recipe_release_id",
    "recipe_release_hash",
    "deployment_line_id",
    "deployment_line_hash",
)


@dataclass(frozen=True)
class PositionState:
    quantity: Decimal
    average: Decimal
    multiplier: Decimal


@dataclass(frozen=True)
class CompletedTrade:
    trade_id: str
    instrument_id: str
    fill_ids: Tuple[str, ...]
    funding_ids: Tuple[str, ...]
    contribution_usdt: Decimal
    opened_at: str
    closed_at: str
    eligible: bool


@dataclass(frozen=True)
class SourceReplayAnalysis:
    scope: Mapping[str, Any]
    original_replay: Tuple[Mapping[str, Any], ...]
    completed_trades: Tuple[CompletedTrade, ...]
    funding_assignment: Mapping[str, str]


@dataclass
class _ActiveCycle:
    instrument_id: str
    fill_ids: List[str]
    funding_ids: List[str]
    contribution_usdt: Decimal
    opened_at: str
    eligible: bool


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("TRADE_REPLAY_TIME_INVALID")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TRADE_REPLAY_TIME_INVALID")
    return parsed.astimezone(timezone.utc)


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(canonical_decimal(value))
    except Exception as exc:
        raise ValueError("TRADE_REPLAY_DECIMAL_INVALID") from exc


def _position_payload(
    positions: Mapping[str, PositionState],
) -> Tuple[Dict[str, str], ...]:
    return tuple(
        {
            "instrument_id": instrument_id,
            "signed_quantity": canonical_decimal(state.quantity),
            "moving_average_entry_price": canonical_decimal(state.average),
            "contract_multiplier": canonical_decimal(state.multiplier),
        }
        for instrument_id, state in sorted(positions.items())
        if state.quantity != 0
    )


def _expected_position_payload(
    value: Any,
) -> Tuple[Dict[str, str], ...]:
    if not isinstance(value, list):
        raise ValueError("TRADE_REPLAY_ORIGINAL_POSITION_MISMATCH")
    try:
        return tuple(
            {
                "instrument_id": item["instrument_id"],
                "signed_quantity": canonical_decimal(
                    item["signed_quantity"]
                ),
                "moving_average_entry_price": canonical_decimal(
                    item["moving_average_entry_price"]
                ),
                "contract_multiplier": canonical_decimal(
                    item["contract_multiplier"]
                ),
            }
            for item in sorted(
                value,
                key=lambda item: item["instrument_id"],
            )
            if _decimal(item["signed_quantity"]) != 0
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "TRADE_REPLAY_ORIGINAL_POSITION_MISMATCH"
        ) from exc


def _valuation_index(
    valuation_checkpoints: Sequence[Mapping[str, Any]],
) -> Dict[Tuple[str, str], Mapping[str, Any]]:
    indexed: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    for checkpoint in valuation_checkpoints:
        if not isinstance(checkpoint, Mapping):
            raise ValueError("TRADE_REPLAY_VALUATION_INVALID")
        key = (
            checkpoint.get("source_economic_snapshot_hash"),
            checkpoint.get("equity_snapshot_id"),
        )
        if not all(isinstance(item, str) and item for item in key):
            raise ValueError("TRADE_REPLAY_VALUATION_INVALID")
        if key in indexed:
            raise ValueError("TRADE_REPLAY_VALUATION_DUPLICATE")
        indexed[key] = checkpoint
    return indexed


def _unrealized_at_checkpoint(
    *,
    checkpoint: Mapping[str, Any],
    equity_point: Mapping[str, Any],
    positions: Mapping[str, PositionState],
    direction: str,
) -> Tuple[Decimal, Decimal]:
    if checkpoint.get("as_of") != equity_point.get("as_of"):
        raise ValueError("TRADE_REPLAY_VALUATION_TIME_MISMATCH")
    instruments = checkpoint.get("instruments")
    if not isinstance(instruments, list):
        raise ValueError("TRADE_REPLAY_VALUATION_INVALID")
    indexed = {}
    for item in instruments:
        if not isinstance(item, Mapping):
            raise ValueError("TRADE_REPLAY_VALUATION_INVALID")
        instrument_id = item.get("instrument_id")
        if not isinstance(instrument_id, str) or not instrument_id:
            raise ValueError("TRADE_REPLAY_VALUATION_INVALID")
        if instrument_id in indexed:
            raise ValueError("TRADE_REPLAY_VALUATION_DUPLICATE")
        indexed[instrument_id] = item
    required = {
        instrument_id
        for instrument_id, state in positions.items()
        if state.quantity != 0
    }
    if set(indexed) != required:
        raise ValueError("TRADE_REPLAY_VALUATION_MISSING")
    unrealized = Decimal("0")
    expected_exit_fees = Decimal("0")
    for instrument_id in sorted(required):
        state = positions[instrument_id]
        item = indexed[instrument_id]
        multiplier = _decimal(item.get("contract_multiplier"))
        if multiplier != state.multiplier:
            raise ValueError("TRADE_REPLAY_MULTIPLIER_CHANGED")
        if direction == "LONG":
            price_value = item.get("long_executable_exit_price_usdt")
            if item.get("short_executable_exit_price_usdt") is not None:
                raise ValueError("TRADE_REPLAY_VALUATION_INVALID")
        else:
            price_value = item.get("short_executable_exit_price_usdt")
            if item.get("long_executable_exit_price_usdt") is not None:
                raise ValueError("TRADE_REPLAY_VALUATION_INVALID")
        price = _decimal(price_value)
        fee = _decimal(item.get("expected_exit_fee_usdt"))
        source_hash = item.get("valuation_source_hash")
        if (
            price <= 0
            or fee < 0
            or not isinstance(source_hash, str)
            or len(source_hash) != 64
            or any(character not in "0123456789abcdef" for character in source_hash)
        ):
            raise ValueError("TRADE_REPLAY_VALUATION_INVALID")
        unrealized += (
            (price - state.average)
            * state.quantity
            * state.multiplier
            - fee
        )
        expected_exit_fees += fee
    return unrealized, expected_exit_fees


def _source_event(
    fact_type: str,
    fact: Mapping[str, Any],
) -> Tuple[datetime, int, str, str, Mapping[str, Any]]:
    fields = {
        "FILL": ("exchange_event_time", "fill_id"),
        "FUNDING": ("settled_at", "funding_id"),
        "CASH_FLOW": ("occurred_at", "flow_id"),
        "EQUITY": ("as_of", "equity_snapshot_id"),
    }
    time_field, id_field = fields[fact_type]
    sequence = fact.get("source_event_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValueError("TRADE_REPLAY_SOURCE_SEQUENCE_INVALID")
    identifier = fact.get(id_field)
    if not isinstance(identifier, str) or not identifier:
        raise ValueError("TRADE_REPLAY_FACT_ID_INVALID")
    return (
        _timestamp(fact.get(time_field)),
        sequence,
        fact_type,
        identifier,
        fact,
    )


def _trade_id(
    *,
    scope: Mapping[str, Any],
    instrument_id: str,
    fill_ids: Sequence[str],
) -> str:
    return "trd:" + business_hash(
        {
            "scope": dict(scope),
            "instrument_id": instrument_id,
            "fill_ids": list(fill_ids),
        }
    )


def _validate_sources(
    source_series_snapshot: Mapping[str, Any],
    economic_snapshots: Sequence[Mapping[str, Any]],
) -> Tuple[Tuple[Mapping[str, Any], Mapping[str, Any]], ...]:
    series_reasons = statistical_series_reasons(source_series_snapshot)
    if series_reasons:
        raise ValueError(
            "TRADE_REPLAY_SOURCE_SERIES_INVALID:"
            + ",".join(series_reasons)
        )
    if (
        source_series_snapshot.get("series_kind")
        != "PRIMARY_ENDPOINT_CONTRIBUTION"
    ):
        raise ValueError("TRADE_REPLAY_SOURCE_SERIES_KIND_MISMATCH")
    if not economic_snapshots:
        raise ValueError("TRADE_REPLAY_ECONOMIC_SOURCE_MISSING")
    by_hash = {}
    for snapshot in economic_snapshots:
        if not isinstance(snapshot, Mapping):
            raise ValueError("TRADE_REPLAY_ECONOMIC_SOURCE_INVALID")
        if snapshot.get("schema_version") != "1.1.0":
            raise ValueError("TRADE_REPLAY_ECONOMIC_SOURCE_LEGACY")
        for fill in snapshot.get("fills", ()):
            if isinstance(fill, Mapping) and "trade_id" in fill:
                raise ValueError(
                    "TRADE_REPLAY_UPLOADER_TRADE_ID_FORBIDDEN"
                )
        reasons = economic_snapshot_reasons(snapshot)
        if reasons:
            raise ValueError(
                "TRADE_REPLAY_ECONOMIC_SOURCE_INVALID:"
                + ",".join(reasons)
            )
        snapshot_hash = snapshot.get("snapshot_hash")
        if snapshot_hash in by_hash:
            raise ValueError("TRADE_REPLAY_ECONOMIC_SOURCE_DUPLICATE")
        by_hash[snapshot_hash] = snapshot
    declared = source_series_snapshot.get(
        "source_economic_snapshot_hashes"
    )
    if not isinstance(declared, list) or set(declared) != set(by_hash):
        raise ValueError("TRADE_REPLAY_ECONOMIC_SOURCE_MISMATCH")
    observations = source_series_snapshot.get("observations")
    if not isinstance(observations, list) or len(observations) != len(
        economic_snapshots
    ):
        raise ValueError("TRADE_REPLAY_ECONOMIC_SOURCE_MISMATCH")
    pairs = []
    previous_end: Optional[str] = None
    series_scope = source_series_snapshot["scope"]
    for observation in observations:
        snapshot = by_hash.get(
            observation.get("source_economic_snapshot_hash")
        )
        if snapshot is None:
            raise ValueError("TRADE_REPLAY_ECONOMIC_SOURCE_MISMATCH")
        scope = snapshot["scope"]
        if any(scope.get(name) != series_scope.get(name) for name in _SCOPE_FIELDS):
            raise ValueError("TRADE_REPLAY_SCOPE_MISMATCH")
        if (
            observation.get("period_start")
            != scope.get("evaluation_window_start")
            or observation.get("period_end")
            != scope.get("evaluation_window_end")
        ):
            raise ValueError("TRADE_REPLAY_PERIOD_MISMATCH")
        if previous_end is not None and observation["period_start"] != previous_end:
            raise ValueError("TRADE_REPLAY_PERIOD_GAP")
        previous_end = observation["period_end"]
        for name in (
            "accounting_policy_id",
            "accounting_policy_hash",
            "cost_allocation_policy_id",
            "cost_allocation_policy_hash",
        ):
            if snapshot.get(name) != source_series_snapshot.get(name):
                raise ValueError("TRADE_REPLAY_POLICY_MISMATCH")
        status, value, reasons = cash_flow_adjusted_economic_log_growth(
            {"economic_ledger_snapshot": snapshot}
        )
        if (
            status != "COMPUTED"
            or reasons
            or value != canonical_decimal(observation.get("value"))
        ):
            raise ValueError("TRADE_REPLAY_ORIGINAL_SERIES_MISMATCH")
        pairs.append((observation, snapshot))
    if (
        observations[0]["period_start"]
        != series_scope.get("evaluation_window_start")
        or observations[-1]["period_end"]
        != series_scope.get("evaluation_window_end")
    ):
        raise ValueError("TRADE_REPLAY_SCOPE_MISMATCH")
    return tuple(pairs)


def analyze_trade_replay_source(
    *,
    source_series_snapshot: Mapping[str, Any],
    economic_snapshots: Sequence[Mapping[str, Any]],
    valuation_checkpoints: Sequence[Mapping[str, Any]],
) -> SourceReplayAnalysis:
    """Reproduce a source economic path and derive complete position cycles."""

    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        pairs = _validate_sources(
            source_series_snapshot,
            economic_snapshots,
        )
        valuations = _valuation_index(valuation_checkpoints)
        expected_valuation_keys = {
            (
                snapshot["snapshot_hash"],
                point["equity_snapshot_id"],
            )
            for _, snapshot in pairs
            for point in snapshot["equity_points"]
        }
        if set(valuations) != expected_valuation_keys:
            raise ValueError("TRADE_REPLAY_VALUATION_MISSING")

        outer_scope = dict(source_series_snapshot["scope"])
        direction = outer_scope["direction"]
        positions: Dict[str, PositionState] = {}
        active_cycles: Dict[str, _ActiveCycle] = {}
        completed: List[CompletedTrade] = []
        funding_assignment: Dict[str, str] = {}
        original_replay: List[Mapping[str, Any]] = []
        realized = Decimal("0")
        fees = Decimal("0")
        funding = Decimal("0")
        cash_flow = Decimal("0")
        base_equity: Optional[Decimal] = None
        initial_unrealized: Optional[Decimal] = None
        prior_ending_equity: Optional[Decimal] = None
        prior_positions: Optional[Tuple[Dict[str, str], ...]] = None

        for pair_index, (_, snapshot) in enumerate(pairs):
            opening = _expected_position_payload(
                snapshot["opening_positions"]
            )
            if pair_index == 0:
                positions = {
                    item["instrument_id"]: PositionState(
                        _decimal(item["signed_quantity"]),
                        _decimal(item["moving_average_entry_price"]),
                        _decimal(item["contract_multiplier"]),
                    )
                    for item in opening
                }
                for instrument_id, state in positions.items():
                    active_cycles[instrument_id] = _ActiveCycle(
                        instrument_id=instrument_id,
                        fill_ids=[],
                        funding_ids=[],
                        contribution_usdt=Decimal("0"),
                        opened_at=snapshot["scope"][
                            "evaluation_window_start"
                        ],
                        eligible=False,
                    )
                base_equity = _decimal(
                    snapshot["starting_liquidation_equity_usdt"]
                )
            else:
                if opening != prior_positions:
                    raise ValueError(
                        "TRADE_REPLAY_ORIGINAL_POSITION_MISMATCH"
                    )
                if _decimal(
                    snapshot["starting_liquidation_equity_usdt"]
                ) != prior_ending_equity:
                    raise ValueError(
                        "TRADE_REPLAY_ORIGINAL_EQUITY_MISMATCH"
                    )

            events = []
            for fact in snapshot["fills"]:
                events.append(_source_event("FILL", fact))
            for fact in snapshot["funding_cashflows"]:
                events.append(_source_event("FUNDING", fact))
            for fact in snapshot["external_cash_flows"]:
                events.append(_source_event("CASH_FLOW", fact))
            for fact in snapshot["equity_points"]:
                events.append(_source_event("EQUITY", fact))
            events.sort(key=lambda item: item[:4])

            for _, _, fact_type, _, fact in events:
                if fact_type == "FILL":
                    instrument_id = fact["instrument_id"]
                    quantity = _decimal(fact["quantity"])
                    price = _decimal(fact["price"])
                    multiplier = _decimal(fact["contract_multiplier"])
                    fee = _decimal(fact["fee_value_usdt"])
                    delta = quantity if fact["side"] == "BUY" else -quantity
                    state = positions.get(
                        instrument_id,
                        PositionState(
                            Decimal("0"),
                            Decimal("0"),
                            multiplier,
                        ),
                    )
                    if (
                        state.quantity != 0
                        and state.multiplier != multiplier
                    ):
                        raise ValueError(
                            "TRADE_REPLAY_MULTIPLIER_CHANGED"
                        )
                    if state.quantity == 0:
                        if (
                            direction == "LONG" and delta < 0
                        ) or (
                            direction == "SHORT" and delta > 0
                        ):
                            raise ValueError(
                                "TRADE_REPLAY_DIRECTION_MISMATCH"
                            )
                        active_cycles[instrument_id] = _ActiveCycle(
                            instrument_id=instrument_id,
                            fill_ids=[],
                            funding_ids=[],
                            contribution_usdt=Decimal("0"),
                            opened_at=fact["exchange_event_time"],
                            eligible=True,
                        )
                    cycle = active_cycles.get(instrument_id)
                    if cycle is None:
                        raise ValueError(
                            "TRADE_REPLAY_CYCLE_STATE_INVALID"
                        )
                    if state.quantity == 0 or (
                        state.quantity > 0
                    ) == (delta > 0):
                        new_quantity = state.quantity + delta
                        new_average = (
                            price
                            if state.quantity == 0
                            else (
                                abs(state.quantity) * state.average
                                + abs(delta) * price
                            )
                            / abs(new_quantity)
                        )
                        realized_delta = Decimal("0")
                    else:
                        if abs(delta) > abs(state.quantity):
                            raise ValueError(
                                "TRADE_REPLAY_FILL_CROSSES_ZERO"
                            )
                        closed = abs(delta)
                        realized_delta = (
                            (
                                price - state.average
                                if state.quantity > 0
                                else state.average - price
                            )
                            * closed
                            * state.multiplier
                        )
                        new_quantity = state.quantity + delta
                        new_average = (
                            state.average
                            if new_quantity != 0
                            else Decimal("0")
                        )
                    realized += realized_delta
                    fees += fee
                    cycle.contribution_usdt += realized_delta - fee
                    cycle.fill_ids.append(fact["fill_id"])
                    positions[instrument_id] = PositionState(
                        new_quantity,
                        new_average,
                        multiplier,
                    )
                    if new_quantity == 0:
                        trade_id = _trade_id(
                            scope=outer_scope,
                            instrument_id=instrument_id,
                            fill_ids=cycle.fill_ids,
                        )
                        trade = CompletedTrade(
                            trade_id=trade_id,
                            instrument_id=instrument_id,
                            fill_ids=tuple(cycle.fill_ids),
                            funding_ids=tuple(cycle.funding_ids),
                            contribution_usdt=cycle.contribution_usdt,
                            opened_at=cycle.opened_at,
                            closed_at=fact["exchange_event_time"],
                            eligible=cycle.eligible,
                        )
                        completed.append(trade)
                        for funding_id in cycle.funding_ids:
                            funding_assignment[funding_id] = trade_id
                        del active_cycles[instrument_id]
                elif fact_type == "FUNDING":
                    instrument_id = fact["instrument_id"]
                    state = positions.get(
                        instrument_id,
                        PositionState(
                            Decimal("0"),
                            Decimal("0"),
                            Decimal("1"),
                        ),
                    )
                    if _decimal(fact["position_quantity"]) != state.quantity:
                        raise ValueError(
                            "TRADE_REPLAY_FUNDING_POSITION_MISMATCH"
                        )
                    cycle = active_cycles.get(instrument_id)
                    if state.quantity == 0 or cycle is None:
                        raise ValueError(
                            "TRADE_REPLAY_FUNDING_POSITION_MISMATCH"
                        )
                    amount = _decimal(fact["signed_amount_usdt"])
                    funding += amount
                    cycle.contribution_usdt += amount
                    cycle.funding_ids.append(fact["funding_id"])
                elif fact_type == "CASH_FLOW":
                    cash_flow += _decimal(fact["signed_amount_usdt"])
                else:
                    key = (
                        snapshot["snapshot_hash"],
                        fact["equity_snapshot_id"],
                    )
                    unrealized, expected_exit_fee = (
                        _unrealized_at_checkpoint(
                            checkpoint=valuations[key],
                            equity_point=fact,
                            positions=positions,
                            direction=direction,
                        )
                    )
                    if initial_unrealized is None:
                        initial_unrealized = unrealized
                    replayed_equity = (
                        base_equity
                        + realized
                        + unrealized
                        - initial_unrealized
                        - fees
                        + funding
                        + cash_flow
                    )
                    if replayed_equity != _decimal(
                        fact["liquidation_equity_usdt"]
                    ):
                        raise ValueError(
                            "TRADE_REPLAY_ORIGINAL_EQUITY_MISMATCH"
                        )
                    current_positions = _position_payload(positions)
                    if current_positions != _expected_position_payload(
                        fact["position_cost_bases"]
                    ):
                        raise ValueError(
                            "TRADE_REPLAY_ORIGINAL_POSITION_MISMATCH"
                        )
                    if expected_exit_fee != _decimal(
                        fact["expected_exit_fee_accrued_usdt"]
                    ):
                        raise ValueError(
                            "TRADE_REPLAY_ORIGINAL_EXIT_FEE_MISMATCH"
                        )
                    original_replay.append(
                        {
                            "source_economic_snapshot_hash": snapshot[
                                "snapshot_hash"
                            ],
                            "equity_snapshot_id": fact[
                                "equity_snapshot_id"
                            ],
                            "as_of": fact["as_of"],
                            "liquidation_equity_usdt": canonical_decimal(
                                replayed_equity
                            ),
                            "position_cost_bases": list(
                                current_positions
                            ),
                            "expected_exit_fee_accrued_usdt": (
                                canonical_decimal(expected_exit_fee)
                            ),
                        }
                    )

            prior_ending_equity = _decimal(
                snapshot["ending_liquidation_equity_usdt"]
            )
            prior_positions = _position_payload(positions)

        return SourceReplayAnalysis(
            scope=outer_scope,
            original_replay=tuple(original_replay),
            completed_trades=tuple(completed),
            funding_assignment=dict(sorted(funding_assignment.items())),
        )
