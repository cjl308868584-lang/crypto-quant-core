"""Tail-blind progress and exact Decimal reconstruction for replacement v3."""

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping, Optional, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_decimal, canonical_json, stable_id
from .challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from .challenger_replacement_plan_v3 import build_challenger_replacement_plan_v3
from .challenger_replacement_plan import _strict_json_bytes
from .challenger_replacement_public_simulation import (
    _kernel_source,
    _snapshot_validator,
    _validated_source,
    build_challenger_replacement_public_genesis_snapshot,
    build_challenger_replacement_public_simulation_input,
    load_challenger_replacement_public_simulation_result_bytes,
)
from .challenger_replacement_public_market_capture import (
    load_challenger_replacement_public_market_capture_bytes,
)
from .challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from .challenger_replacement_simulation import _mark
from .challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from .challenger_replacement_opportunity_projection import validate_build_identity
from .evidence import artifact_self_hash
from .statistics import _draw_start, _fixed_decimal_context


_CADENCE = 14_400
_TAIL_SECONDS = 7_776_000
_PUBLIC = (
    "PUBLIC_MARKET_DETERMINISTIC_SIMULATION_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER"
)
_SCHEMA = "challenger-replacement-economic-evaluation-v1.schema.json"
_STRICT_EVENT_FACTS = object()


class ChallengerReplacementEconomicEvaluationError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="ECONOMIC_EVALUATION_FACTS_INVALID"):
    raise ChallengerReplacementEconomicEvaluationError(reason)


@dataclass(frozen=True)
class EconomicProgressFacts:
    start_receipt: Mapping[str, Any]
    terminal_headers: Tuple[Mapping[str, Any], ...]
    observed_at: str


@dataclass(frozen=True)
class EconomicOpportunityFact:
    opportunity_id: str
    scheduled_for: str
    outcome: str
    result_or_null: Optional[Mapping[str, Any]]
    missed_position_state_or_null: Optional[str]
    missed_reason_or_null: Optional[str]


@dataclass(frozen=True)
class EconomicEvaluationFacts:
    start_receipt: Mapping[str, Any]
    opportunities: Tuple[EconomicOpportunityFact, ...]
    observed_at: str
    tail_mark_or_null: Optional[Mapping[str, Any]]


def _event_facts(value):
    if getattr(value, "_authority", None) is not _STRICT_EVENT_FACTS:
        _invalid("ECONOMIC_FACT_SOURCE_INVALID")
    return value


def _bind_event_facts(value):
    object.__setattr__(value, "_authority", _STRICT_EVENT_FACTS)
    return value


def _validate_start_against_projection(start_receipt, projection, build_identity):
    try:
        observed = next(
            event for event in projection["events"]
            if json.loads(event.final_bytes.decode("utf-8"))["event_type"]
            == "OPPORTUNITY_OBSERVED"
        )
        event = json.loads(observed.final_bytes.decode("utf-8"))
        slot = projection["opportunities"][event["slot_id"]]
        if (
            not isinstance(start_receipt, Mapping)
            or start_receipt.get("status")
            != "V3_FIRST_NATURAL_OBSERVED_BOUND_NOT_ACTIVATED"
            or start_receipt.get("deployment", {}).get("candidate_build")
            != build_identity
            or start_receipt.get("shared_opportunity_id") != event["slot_id"]
            or start_receipt.get("shared_event_hash") != observed.event_hash
            or start_receipt.get("economic_start", {}).get("scheduled_for")
            != slot["scheduled_for"]
            or start_receipt.get("operational_start", {}).get("observed_at")
            != slot["result_evidence"]["opportunity"]["captured_at"]
            or any(start_receipt.get("authority", {}).values())
        ):
            _invalid("ECONOMIC_FACT_SOURCE_INVALID")
    except (KeyError, StopIteration, TypeError, UnicodeDecodeError, ValueError) as error:
        raise ChallengerReplacementEconomicEvaluationError(
            "ECONOMIC_FACT_SOURCE_INVALID"
        ) from error


def build_economic_progress_facts_from_state(
    *, state, start_receipt, observed_at
):
    """Derive tail-blind headers without reading economic result payloads."""
    from .challenger_replacement_opportunities import (
        ChallengerReplacementOpportunityState,
    )
    if not isinstance(state, ChallengerReplacementOpportunityState):
        _invalid("ECONOMIC_FACT_SOURCE_INVALID")
    projection = state._replay()
    _validate_start_against_projection(
        start_receipt, projection, state.build_identity
    )
    headers = tuple({
        "opportunity_id": _opportunity_id(_time(scheduled_for)),
        "scheduled_for": scheduled_for,
        "outcome": projection["opportunities"][
            _opportunity_id(_time(scheduled_for))
        ]["outcome"],
        "evidence_health": "STRICT_REPLAY_VERIFIED",
    } for scheduled_for in projection["terminal_scheduled_for"])
    return _bind_event_facts(EconomicProgressFacts(
        start_receipt=copy.deepcopy(dict(start_receipt)),
        terminal_headers=headers,
        observed_at=observed_at,
    ))


def build_economic_evaluation_facts_from_state(
    *, state, start_receipt, observed_at, tail_mark_or_null
):
    """Derive production facts only from a retained strict replay capability."""
    from .challenger_replacement_opportunities import (
        ChallengerReplacementOpportunityState,
    )
    if (
        not isinstance(state, ChallengerReplacementOpportunityState)
    ):
        _invalid("ECONOMIC_FACT_SOURCE_INVALID")
    projection = state._replay()
    _validate_start_against_projection(
        start_receipt, projection, state.build_identity
    )
    plan = state.plan
    economic = build_challenger_replacement_economic_plan()
    predecessor = build_challenger_replacement_simulation_contract(plan=plan)
    public = build_challenger_replacement_public_simulation_contract(
        plan=plan, economic_plan=economic, predecessor_contract=predecessor
    )
    previous = build_challenger_replacement_public_genesis_snapshot(
        plan=plan, public_contract=public
    )
    previous_bundle = None
    result = []
    for scheduled_for in projection["terminal_scheduled_for"]:
        opportunity_id = _opportunity_id(_time(scheduled_for))
        slot = projection["opportunities"][opportunity_id]
        if slot["outcome"] == "MISSED":
            result.append(EconomicOpportunityFact(
                opportunity_id, scheduled_for, "MISSED", None,
                previous["position_state"], slot["reason_code"],
            ))
            continue
        capture = load_challenger_replacement_public_market_capture_bytes(
            slot["source_bundle_bytes"], plan=plan,
            build_identity=state.build_identity,
            previous_source_bundle=previous_bundle,
        )
        source = build_challenger_replacement_public_simulation_input(
            capture, plan=plan, economic_plan=economic,
            predecessor_contract=predecessor, public_contract=public,
            build_identity=state.build_identity,
        )
        evidence = slot["result_evidence"]
        envelope = {
            "source": source, "previous_projection": previous,
            "result": evidence, "sequence": evidence["sequence"],
            "parent_event_hash": evidence["parent_event_hash"],
        }
        _strict_result(
            envelope, economic_plan=economic,
            expected_previous_hash=previous["snapshot_hash"],
            expected_build=state.build_identity,
        )
        result.append(EconomicOpportunityFact(
            opportunity_id, scheduled_for, "OBSERVED", envelope, None, None
        ))
        previous = evidence["next_snapshot"]
        previous_bundle = {"klines": capture.document["normalized"]["bars"]}
    return _bind_event_facts(EconomicEvaluationFacts(
        start_receipt=copy.deepcopy(dict(start_receipt)),
        opportunities=tuple(result), observed_at=observed_at,
        tail_mark_or_null=copy.deepcopy(tail_mark_or_null),
    ))


def _time(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        _invalid()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ChallengerReplacementEconomicEvaluationError(
            "ECONOMIC_EVALUATION_FACTS_INVALID"
        ) from error
    if parsed.utcoffset() is None:
        _invalid()
    return parsed


def _validated_plan(plan):
    expected = build_challenger_replacement_economic_plan()
    if plan != expected:
        _invalid("ECONOMIC_EVALUATION_PLAN_MISMATCH")
    return expected


def _start(receipt):
    try:
        if (
            not isinstance(receipt, Mapping)
            or receipt["status"]
            != "V3_FIRST_NATURAL_OBSERVED_BOUND_NOT_ACTIVATED"
            or not isinstance(receipt["receipt_id"], str)
            or not isinstance(receipt["receipt_hash"], str)
            or len(receipt["shared_event_hash"]) != 64
        ):
            _invalid()
        return _time(receipt["economic_start"]["scheduled_for"])
    except (KeyError, TypeError):
        _invalid()


def _opportunity_id(scheduled):
    text = scheduled.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return "ETHUSDT@" + text


def observe_challenger_replacement_economic_progress(
    facts: EconomicProgressFacts, *, economic_plan: Mapping[str, Any]
):
    plan = _validated_plan(economic_plan)
    if not isinstance(facts, EconomicProgressFacts):
        _invalid()
    _event_facts(facts)
    start = _start(facts.start_receipt)
    observed = _time(facts.observed_at)
    if observed < start:
        _invalid()
    tail = start + timedelta(seconds=_TAIL_SECONDS)
    due_through = min(observed, tail - timedelta(milliseconds=1))
    due_count = max(0, int((due_through - start).total_seconds()) // _CADENCE + 1)
    expected = start
    observed_count = missed_count = 0
    required = {"opportunity_id", "scheduled_for", "outcome", "evidence_health"}
    for header in facts.terminal_headers:
        if not isinstance(header, Mapping) or set(header) != required:
            _invalid()
        scheduled = _time(header["scheduled_for"])
        if (
            scheduled != expected
            or header["opportunity_id"] != _opportunity_id(scheduled)
            or header["outcome"] not in {"OBSERVED", "MISSED"}
            or header["evidence_health"] != "STRICT_REPLAY_VERIFIED"
            or scheduled >= tail
        ):
            _invalid()
        observed_count += header["outcome"] == "OBSERVED"
        missed_count += header["outcome"] == "MISSED"
        expected += timedelta(seconds=_CADENCE)
    terminal_count = len(facts.terminal_headers)
    health = "HEALTHY" if terminal_count == min(due_count, 540) else "INCOMPLETE"
    next_at = start + timedelta(seconds=terminal_count * _CADENCE)
    return {
        "status": "TAIL_BLIND",
        "due_opportunity_count": due_count,
        "terminal_opportunity_count": terminal_count,
        "observed_opportunity_count": observed_count,
        "missed_opportunity_count": missed_count,
        "elapsed_complete_days": min(90, int((observed - start).total_seconds()) // 86400),
        "next_required_opportunity": (
            None if terminal_count >= 540 else _opportunity_id(next_at)
        ),
        "evidence_health": health,
        "plan_binding": {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]},
        "authority": {"economic_outcome_reads": 0, "production_state_writes": 0},
    }


def _strict_result(envelope, *, economic_plan, expected_previous_hash=None,
                   expected_build=None):
    if not isinstance(envelope, Mapping) or set(envelope) != {
        "source", "previous_projection", "result", "sequence",
        "parent_event_hash",
    }:
        _invalid("ECONOMIC_RESULT_REPLAY_INVALID")
    try:
        plan = build_challenger_replacement_plan_v3()
        predecessor = build_challenger_replacement_simulation_contract(plan=plan)
        public = build_challenger_replacement_public_simulation_contract(
            plan=plan, economic_plan=economic_plan,
            predecessor_contract=predecessor,
        )
        result = envelope["result"]
        if (
            expected_previous_hash is not None
            and envelope["previous_projection"].get("snapshot_hash")
            != expected_previous_hash
        ):
            _invalid("ECONOMIC_RESULT_REPLAY_INVALID")
        return load_challenger_replacement_public_simulation_result_bytes(
            canonical_json(result).encode("utf-8"), source=envelope["source"],
            previous_projection=envelope["previous_projection"], plan=plan,
            economic_plan=economic_plan, public_contract=public,
            build_identity=expected_build or result["build_identity"], sequence=envelope["sequence"],
            parent_event_hash=envelope["parent_event_hash"],
        )
    except ChallengerReplacementEconomicEvaluationError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementEconomicEvaluationError(
            "ECONOMIC_RESULT_REPLAY_INVALID"
        ) from error


def _strict_tail_mark(
    envelope, *, economic_plan, expected_previous_hash=None,
    expected_scheduled_for=None, expected_build=None
):
    if not isinstance(envelope, Mapping) or set(envelope) != {
        "source", "previous_projection", "marked_equity"
    }:
        _invalid("ECONOMIC_TAIL_MARK_INVALID")
    try:
        plan = build_challenger_replacement_plan_v3()
        predecessor = build_challenger_replacement_simulation_contract(plan=plan)
        public = build_challenger_replacement_public_simulation_contract(
            plan=plan, economic_plan=economic_plan,
            predecessor_contract=predecessor,
        )
        source = _validated_source(
            envelope["source"], plan=plan, public_contract=public,
            build_identity=expected_build or envelope["source"]["build_identity"],
        )
        snapshot = copy.deepcopy(dict(envelope["previous_projection"]))
        if (
            tuple(_snapshot_validator().iter_errors(snapshot))
            or snapshot.get("snapshot_hash")
            != artifact_self_hash(snapshot, "snapshot_hash")
            or (expected_previous_hash is not None
                and snapshot["snapshot_hash"] != expected_previous_hash)
            or (expected_scheduled_for is not None
                and source["opportunity"]["scheduled_for"]
                != expected_scheduled_for)
        ):
            _invalid("ECONOMIC_TAIL_MARK_INVALID")
        _mark(snapshot, _kernel_source(source, plan, public))
        if snapshot["marked_equity"] != envelope["marked_equity"]:
            _invalid("ECONOMIC_TAIL_MARK_INVALID")
        return snapshot["marked_equity"]
    except ChallengerReplacementEconomicEvaluationError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementEconomicEvaluationError(
            "ECONOMIC_TAIL_MARK_INVALID"
        ) from error


def _c(value):
    return canonical_decimal(value)


@lru_cache(maxsize=1)
def _validator():
    schema = json.loads(resources.files("crypto_quant").joinpath(
        "schemas", _SCHEMA
    ).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _series(equities):
    returns = [
        (equities[index] - equities[index - 1]) / Decimal("100")
        for index in range(1, len(equities))
    ]
    blocks = [sum(returns[index:index + 15], Decimal("0")) for index in range(0, 90, 15)]
    peak = equities[0]
    drawdown = Decimal("0")
    for equity in equities:
        peak = max(peak, equity)
        if peak > 0:
            drawdown = max(drawdown, (peak - equity) / peak)
    return {
        "boundary_equities": [_c(value) for value in equities],
        "daily_returns": [_c(value) for value in returns],
        "fixed_15_day_blocks": [_c(value) for value in blocks],
        "maximum_drawdown_fraction": _c(drawdown),
    }


def _continuous_drawdown(values):
    peak = values[0]
    result = Decimal("0")
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            result = max(result, (peak - value) / peak)
    return result


@_fixed_decimal_context
def _build_economic_boundary_series(
    facts: EconomicEvaluationFacts, *, economic_plan: Mapping[str, Any]
):
    plan = _validated_plan(economic_plan)
    if not isinstance(facts, EconomicEvaluationFacts):
        _invalid()
    start = _start(facts.start_receipt)
    observed = _time(facts.observed_at)
    tail = start + timedelta(seconds=_TAIL_SECONDS)
    expected_build = facts.start_receipt["deployment"]["candidate_build"]
    if observed < tail:
        _invalid("ECONOMIC_TAIL_NOT_REACHED")
    window = []
    expected = start
    for fact in facts.opportunities:
        if not isinstance(fact, EconomicOpportunityFact):
            _invalid()
        scheduled = _time(fact.scheduled_for)
        if scheduled >= tail:
            _invalid()
        if (
            scheduled != expected
            or fact.opportunity_id != _opportunity_id(scheduled)
            or fact.outcome not in {"OBSERVED", "MISSED"}
        ):
            _invalid()
        window.append((scheduled, fact))
        expected += timedelta(seconds=_CADENCE)
    if len(window) != 540 or expected != tail:
        _invalid("ECONOMIC_TERMINAL_COVERAGE_INCOMPLETE")
    base = Decimal("100")
    stress_extra = Decimal("0")
    pessimistic_extra = Decimal("0")
    base_boundaries = [base]
    stress_boundaries = [base]
    optimistic_boundaries = [base]
    pessimistic_boundaries = [base]
    continuous_base = [base]
    continuous_stress = [base]
    continuous_optimistic = [base]
    continuous_pessimistic = [base]
    confirmed = []
    flat_misses = observed_count = 0
    cycles = spot_cycles = perp_cycles = 0
    opened = None
    last_snapshot_hash = None
    cursor = 0
    for day in range(1, 91):
        boundary = start + timedelta(days=day)
        while cursor < len(window) and window[cursor][0] < boundary:
            _scheduled, fact = window[cursor]
            cursor += 1
            if fact.outcome == "MISSED":
                if fact.result_or_null is not None or not fact.missed_reason_or_null:
                    _invalid()
                if fact.missed_position_state_or_null == "FLAT":
                    flat_misses += 1
                    pessimistic_extra += Decimal("1.25")
                    continuous_base.append(base)
                    continuous_stress.append(base - stress_extra)
                    continuous_optimistic.append(base)
                    continuous_pessimistic.append(base - pessimistic_extra)
                else:
                    confirmed.append("EXPOSED_MISSED")
                continue
            if (
                fact.missed_position_state_or_null is not None
                or fact.missed_reason_or_null is not None
            ):
                _invalid()
            result = _strict_result(
                fact.result_or_null, economic_plan=plan,
                expected_previous_hash=last_snapshot_hash,
                expected_build=expected_build,
            )
            if (
                result["opportunity"]["opportunity_id"] != fact.opportunity_id
                or result["opportunity"]["scheduled_for"] != fact.scheduled_for
                or result["evidence_qualification"] != _PUBLIC
            ):
                _invalid("ECONOMIC_RESULT_REPLAY_INVALID")
            observed_count += 1
            snapshot = result["next_snapshot"]
            last_snapshot_hash = snapshot.get("snapshot_hash")
            base = Decimal(snapshot["marked_equity"])
            position = snapshot["position_state"]
            if snapshot["economic_gap_locked"]:
                confirmed.append("ECONOMIC_GAP_LOCK")
            if result["lifecycle"]["unresolved_unknown"]:
                confirmed.append("UNRESOLVED_POSITION")
            if result["reconciliation"]["status"] != "MATCHED":
                confirmed.append("RECONCILIATION_FAILURE")
            if opened is None and position in {"SPOT_LONG", "PERP_SHORT"}:
                opened = position
            elif opened is not None and position == "FLAT":
                cycles += 1
                spot_cycles += opened == "SPOT_LONG"
                perp_cycles += opened == "PERP_SHORT"
                opened = None
            accounting = result["accounting"]
            fee = Decimal(accounting["fee"])
            funding = Decimal(accounting["funding_cashflow"])
            notional = Decimal(accounting["notional"])
            stress_extra += (
                fee * Decimal("0.5") + abs(funding) * Decimal("0.5")
                + notional * Decimal("0.0005")
            )
            peak = Decimal(snapshot["peak_equity"])
            continuous_base.append(peak)
            continuous_stress.append(peak - stress_extra)
            continuous_optimistic.append(peak)
            continuous_pessimistic.append(peak - pessimistic_extra)
            continuous_base.append(base)
            continuous_stress.append(base - stress_extra)
            continuous_optimistic.append(base)
            continuous_pessimistic.append(base - pessimistic_extra)
        if day == 90:
            if facts.tail_mark_or_null is None:
                _invalid("ECONOMIC_TAIL_MARK_MISSING")
            ending_base = Decimal(_strict_tail_mark(
                facts.tail_mark_or_null, economic_plan=plan,
                expected_previous_hash=last_snapshot_hash,
                expected_scheduled_for=(
                    tail.isoformat(timespec="milliseconds").replace("+00:00", "Z")
                ),
                expected_build=expected_build,
            ))
        else:
            ending_base = base
        base_boundaries.append(ending_base)
        optimistic_boundaries.append(ending_base)
        pessimistic_boundaries.append(ending_base - pessimistic_extra)
        stress_boundaries.append(ending_base - stress_extra)
        if day == 90:
            continuous_base.append(ending_base)
            continuous_stress.append(ending_base - stress_extra)
            continuous_optimistic.append(ending_base)
            continuous_pessimistic.append(ending_base - pessimistic_extra)
    terminal_count = len(window)
    base_series = _series(base_boundaries)
    stress_series = _series(stress_boundaries)
    optimistic_series = _series(optimistic_boundaries)
    pessimistic_series = _series(pessimistic_boundaries)
    for item, values in (
        (base_series, continuous_base),
        (stress_series, continuous_stress),
        (optimistic_series, continuous_optimistic),
        (pessimistic_series, continuous_pessimistic),
    ):
        item["maximum_drawdown_fraction"] = _c(_continuous_drawdown(values))
    return {
        "base": base_series,
        "stress": stress_series,
        "optimistic_flat_miss": optimistic_series,
        "pessimistic_flat_miss": (
            None if "EXPOSED_MISSED" in confirmed else pessimistic_series
        ),
        "terminal_opportunity_count": terminal_count,
        "observed_opportunity_count": observed_count,
        "missed_opportunity_count": terminal_count - observed_count,
        "observed_coverage": _c(Decimal(observed_count) / Decimal(terminal_count)),
        "flat_miss_count": flat_misses,
        "completed_cycle_count": cycles,
        "spot_completed_cycle_count": spot_cycles,
        "perpetual_completed_cycle_count": perp_cycles,
        "stress_extra_cost_usdt": _c(stress_extra),
        "confirmed_failure_boundaries": sorted(set(confirmed)),
        "nonpositive_equity": any(value <= 0 for value in continuous_base),
    }


def _nearest_rank(values, numerator, denominator):
    ordered = sorted(values)
    rank = (len(ordered) * numerator + denominator - 1) // denominator
    return ordered[max(1, rank) - 1]


@_fixed_decimal_context
def _bootstrap_statistics(values, *, economic_plan):
    plan = _validated_plan(economic_plan)
    try:
        if any(isinstance(value, (bool, float)) for value in values):
            _invalid("ECONOMIC_BOOTSTRAP_INPUT_INVALID")
        sample = tuple(Decimal(value) for value in values)
    except (TypeError, ValueError) as error:
        raise ChallengerReplacementEconomicEvaluationError(
            "ECONOMIC_BOOTSTRAP_INPUT_INVALID"
        ) from error
    design = plan["statistical_design"]
    if len(sample) != design["sample_length"]:
        _invalid("ECONOMIC_BOOTSTRAP_INPUT_INVALID")
    length = design["block_length_days"]
    start_count = len(sample) - length + 1
    draws = (len(sample) + length - 1) // length
    replicates = []
    for replicate in range(design["resample_count"]):
        selected = []
        for draw in range(draws):
            start = _draw_start(
                seed=design["seed"], replicate=replicate, draw=draw,
                start_count=start_count,
            )
            selected.extend(sample[start:start + length])
        selected = selected[:len(sample)]
        replicates.append(sum(selected, Decimal("0")) / Decimal(len(sample)))
    observed = sum(sample, Decimal("0")) / Decimal(len(sample))
    lcb = _nearest_rank(replicates, 5, 100)
    errors = tuple(value - observed for value in replicates)
    critical = _nearest_rank(errors, 95, 100)
    mere = Decimal(design["minimum_economic_effect_daily"])
    power = Decimal(sum(mere + error > critical for error in errors)) / Decimal(
        design["resample_count"]
    )
    return {
        "observed_mean": _c(observed), "lcb95": _c(lcb),
        "centered_error_critical95": _c(critical),
        "achieved_power_at_mere": _c(power),
    }


def _economic_gates(one, statistics, stress_total):
    total = Decimal(one["boundary_equities"][-1]) - Decimal(
        one["boundary_equities"][0]
    )
    return {
        "mean_daily_net_return_lcb95_gt_zero": Decimal(statistics["lcb95"]) > 0,
        "total_net_pnl_usdt_gt_zero": total > 0,
        "maximum_drawdown_fraction_lt_0_05": (
            Decimal(one["maximum_drawdown_fraction"]) < Decimal("0.05")
        ),
        "nonnegative_fixed_15_day_blocks_gte_5": sum(
            Decimal(value) >= 0 for value in one["fixed_15_day_blocks"]
        ) >= 5,
        "stress_total_net_pnl_usdt_gte_zero": stress_total >= 0,
    }


def _finish_result(value):
    identity = {key: item for key, item in value.items() if key not in {
        "$schema", "schema_version", "result_id", "result_hash"
    }}
    value["result_id"] = stable_id(
        "challenger_replacement_economic_evaluation", identity
    )
    value["result_hash"] = artifact_self_hash(value, "result_hash")
    if tuple(_validator().iter_errors(value)):
        _invalid("ECONOMIC_EVALUATION_RESULT_INVALID")
    return value


def _empty_result(facts, plan, build_identity, reason):
    return _finish_result({
        "$schema": "./" + _SCHEMA, "schema_version": "1.0.0",
        "result_id": "", "result_hash": "0" * 64,
        "status": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
        "bindings": {
            "economic_plan_id": plan["plan_id"],
            "economic_plan_hash": plan["plan_hash"],
            "build_identity": copy.deepcopy(dict(build_identity)),
            "facts_hash": business_hash(facts),
        },
        "facts": {"reason_codes": [reason]}, "series": {},
        "statistics": {}, "gates": {},
        "authority": {"production_activation": False, "account_requests": 0,
                      "broker_requests": 0, "orders": 0, "fund_movement": 0},
    })


def _result_document(facts, plan, build_identity):
    validate_build_identity(build_identity)
    if facts.start_receipt.get("deployment", {}).get("candidate_build") != dict(build_identity):
        _invalid("ECONOMIC_RESULT_REPLAY_INVALID")
    try:
        series = _build_economic_boundary_series(facts, economic_plan=plan)
    except ChallengerReplacementEconomicEvaluationError as error:
        if error.reason_code == "ECONOMIC_TAIL_NOT_REACHED":
            raise
        return _empty_result(
            facts, plan, build_identity, error.reason_code
        )
    candidates = {
        "optimistic": series["optimistic_flat_miss"],
        "pessimistic": series["pessimistic_flat_miss"],
    }
    cache = {}
    statistics = {}
    for name, item in candidates.items():
        if item is None:
            statistics[name] = None
            continue
        key = tuple(item["daily_returns"])
        if key not in cache:
            cache[key] = _bootstrap_statistics(key, economic_plan=plan)
        statistics[name] = cache[key]
    stress_total = Decimal(series["stress"]["boundary_equities"][-1]) - Decimal(
        series["stress"]["boundary_equities"][0]
    )
    economic = {
        name: None if candidates[name] is None else _economic_gates(
            candidates[name], statistics[name], stress_total
        ) for name in candidates
    }
    sample = {
        "calendar_days_eq_90": len(series["base"]["daily_returns"]) == 90,
        "daily_return_count_eq_90": len(series["base"]["daily_returns"]) == 90,
        "terminal_coverage_eq_1": series["terminal_opportunity_count"] == 540,
        "observed_coverage_gte_0_95": Decimal(series["observed_coverage"]) >= Decimal("0.95"),
        "completed_cycles_gte_12": series["completed_cycle_count"] >= 12,
        "spot_completed_cycles_gte_3": series["spot_completed_cycle_count"] >= 3,
        "perpetual_completed_cycles_gte_3": series["perpetual_completed_cycle_count"] >= 3,
        "nonempty_fixed_blocks_eq_6": (
            len(series["base"]["daily_returns"]) == 90
            and len(series["base"]["fixed_15_day_blocks"]) == 6
        ),
        "minimum_mbb_blocks_gte_12": 90 // 7 >= 12,
        "achieved_power_gte_0_80": all(
            item is not None and Decimal(item["achieved_power_at_mere"]) >= Decimal("0.80")
            for item in statistics.values()
        ),
    }
    confirmed = bool(series["confirmed_failure_boundaries"] or series["nonpositive_equity"])
    bounds = [item is not None and all(item.values()) for item in economic.values()]
    if confirmed:
        status = "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS"
    elif not all(sample.values()) or None in economic.values() or bounds[0] != bounds[1]:
        status = "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
    elif all(bounds):
        status = "RESEARCH_CONTINUATION_GATE_PASS"
    else:
        status = "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS"
    value = {
        "$schema": "./" + _SCHEMA, "schema_version": "1.0.0",
        "result_id": "", "result_hash": "0" * 64, "status": status,
        "bindings": {
            "economic_plan_id": plan["plan_id"],
            "economic_plan_hash": plan["plan_hash"],
            "build_identity": copy.deepcopy(dict(build_identity)),
            "facts_hash": business_hash(facts),
        },
        "facts": {
            key: copy.deepcopy(series[key]) for key in (
                "terminal_opportunity_count", "observed_opportunity_count",
                "missed_opportunity_count", "observed_coverage",
                "flat_miss_count", "completed_cycle_count",
                "spot_completed_cycle_count", "perpetual_completed_cycle_count",
                "confirmed_failure_boundaries", "nonpositive_equity",
            )
        },
        "series": copy.deepcopy({key: series[key] for key in (
            "base", "stress", "optimistic_flat_miss", "pessimistic_flat_miss"
        )}),
        "statistics": statistics,
        "gates": {"sample": sample, "economic": economic},
        "authority": {"production_activation": False, "account_requests": 0,
                      "broker_requests": 0, "orders": 0, "fund_movement": 0},
    }
    return _finish_result(value)


def evaluate_challenger_replacement_economic_result(
    facts: EconomicEvaluationFacts, *, economic_plan: Mapping[str, Any],
    build_identity: Mapping[str, Any]
):
    try:
        _event_facts(facts)
        return copy.deepcopy(_result_document(
            facts, _validated_plan(economic_plan), build_identity
        ))
    except ChallengerReplacementEconomicEvaluationError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementEconomicEvaluationError(
            "ECONOMIC_EVALUATION_RESULT_INVALID"
        ) from error


def load_challenger_replacement_economic_evaluation_bytes(
    data: bytes, *, facts: EconomicEvaluationFacts,
    economic_plan: Mapping[str, Any], build_identity: Mapping[str, Any]
):
    if not isinstance(data, bytes) or not 0 < len(data) <= 4_194_304:
        _invalid("ECONOMIC_EVALUATION_BYTES_INVALID")
    try:
        _event_facts(facts)
        value = _strict_json_bytes(data)
        expected = _result_document(facts, _validated_plan(economic_plan), build_identity)
        if data != canonical_json(value).encode("utf-8") or value != expected:
            _invalid("ECONOMIC_EVALUATION_RESULT_INVALID")
        return copy.deepcopy(value)
    except ChallengerReplacementEconomicEvaluationError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementEconomicEvaluationError(
            "ECONOMIC_EVALUATION_BYTES_INVALID"
        ) from error
