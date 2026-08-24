"""Pure replacement-v3 readiness policy boundary."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Optional, Tuple

from .challenger_replacement_opportunity_projection import opportunity_id_for


_CADENCE = timedelta(hours=4)
_CAPTURE_CLOSE_OFFSET = timedelta(minutes=10)
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_PLAN_ID = re.compile(r"challenger_replacement_plan_v3_[0-9a-f]{64}\Z")
_POSITION = frozenset({"FLAT", "SPOT_LONG", "PERP_SHORT"})
_OUTCOME = frozenset({"OBSERVED", "MISSED"})
_QUALIFICATION = "STRICT_V072_FIXTURE_SANITIZED"
_BOUNDARY_QUALIFICATION = "COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL"
_UNKNOWN_EVIDENCE_FAILURE = (
    "EVIDENCE_SOURCE_UNAVAILABLE_OR_QUALIFICATION_UNKNOWN"
)
_CONFIRMED_EVIDENCE_FAILURE = (
    "CONFIRMED_EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE"
)


class ChallengerReplacementReadinessError(ValueError):
    """Readiness facts or boundaries failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class OpportunityReadinessFact:
    __slots__ = (
        "opportunity_id",
        "scheduled_for",
        "outcome",
        "terminal_recorded_at",
        "observed_at_or_null",
        "missed_reason_or_null",
        "detected_at_or_null",
        "result_evidence_sha256_or_null",
        "position_before",
        "position_after",
        "product_or_null",
        "lifecycle_status_or_null",
        "risk_state",
        "protective_stop_status",
        "economic_gap_locked",
        "unresolved_reason_codes",
    )

    opportunity_id: str
    scheduled_for: str
    outcome: str
    terminal_recorded_at: str
    observed_at_or_null: Optional[str]
    missed_reason_or_null: Optional[str]
    detected_at_or_null: Optional[str]
    result_evidence_sha256_or_null: Optional[str]
    position_before: str
    position_after: str
    product_or_null: Optional[str]
    lifecycle_status_or_null: Optional[str]
    risk_state: str
    protective_stop_status: str
    economic_gap_locked: bool
    unresolved_reason_codes: Tuple[str, ...]


@dataclass(frozen=True)
class ReplacementReadinessFacts:
    __slots__ = (
        "qualification",
        "plan_id",
        "plan_hash",
        "event_evidence_identity_hash",
        "release_provenance_hash",
        "event_chain_end_hash_or_null",
        "opportunities",
        "terminal_opportunity_count",
        "observed_opportunity_count",
        "missed_opportunity_count",
        "current_consecutive_missed",
        "maximum_consecutive_missed",
        "last_missed_reason_or_null",
        "active_opportunity_present",
        "current_position",
        "gross_exposure",
        "open_order_count",
        "unknown_order_count",
        "reconciliation_status",
        "protective_stop_status",
        "risk_state",
        "daily_loss_boundary_state",
        "drawdown_boundary_state",
        "incident_count",
        "evidence_failure_kind_or_null",
    )

    qualification: str
    plan_id: str
    plan_hash: str
    event_evidence_identity_hash: str
    release_provenance_hash: str
    event_chain_end_hash_or_null: Optional[str]
    opportunities: Tuple[OpportunityReadinessFact, ...]
    terminal_opportunity_count: int
    observed_opportunity_count: int
    missed_opportunity_count: int
    current_consecutive_missed: int
    maximum_consecutive_missed: int
    last_missed_reason_or_null: Optional[str]
    active_opportunity_present: bool
    current_position: str
    gross_exposure: str
    open_order_count: int
    unknown_order_count: int
    reconciliation_status: str
    protective_stop_status: str
    risk_state: str
    daily_loss_boundary_state: str
    drawdown_boundary_state: str
    incident_count: int
    evidence_failure_kind_or_null: Optional[str]


@dataclass(frozen=True)
class _ReplacementReadinessBoundary:
    __slots__ = (
        "qualification",
        "start_opportunity_id_or_null",
        "start_scheduled_for_or_null",
        "start_observed_at_or_null",
        "observed_at",
    )

    qualification: str
    start_opportunity_id_or_null: Optional[str]
    start_scheduled_for_or_null: Optional[str]
    start_observed_at_or_null: Optional[str]
    observed_at: str


@dataclass(frozen=True)
class OperationalReadinessResult:
    __slots__ = (
        "evidence_qualification",
        "policy_status",
        "authority_status",
        "elapsed_complete_days",
        "due_opportunity_count",
        "terminal_opportunity_count",
        "observed_opportunity_count",
        "missed_opportunity_count",
        "observed_coverage_numerator",
        "observed_coverage_denominator",
        "meets_minimum_observed_coverage",
        "terminal_coverage_complete",
        "strategy_cycle_count",
        "spot_roundtrip_count",
        "perpetual_roundtrip_count",
        "reason_codes",
    )

    evidence_qualification: str
    policy_status: str
    authority_status: str
    elapsed_complete_days: int
    due_opportunity_count: int
    terminal_opportunity_count: int
    observed_opportunity_count: int
    missed_opportunity_count: int
    observed_coverage_numerator: int
    observed_coverage_denominator: int
    meets_minimum_observed_coverage: bool
    terminal_coverage_complete: bool
    strategy_cycle_count: int
    spot_roundtrip_count: int
    perpetual_roundtrip_count: int
    reason_codes: Tuple[str, ...]


@dataclass(frozen=True)
class EconomicTailObservation:
    __slots__ = (
        "evidence_qualification",
        "status",
        "elapsed_complete_days",
        "minimum_calendar_days",
        "due_opportunity_count",
        "terminal_opportunity_count",
        "observed_opportunity_count",
        "missed_opportunity_count",
        "meets_minimum_observed_coverage",
        "terminal_coverage_complete",
        "lifecycle_complete",
        "unresolved_safety_failure",
        "next_boundary_or_null",
    )

    evidence_qualification: str
    status: str
    elapsed_complete_days: int
    minimum_calendar_days: int
    due_opportunity_count: int
    terminal_opportunity_count: int
    observed_opportunity_count: int
    missed_opportunity_count: int
    meets_minimum_observed_coverage: bool
    terminal_coverage_complete: bool
    lifecycle_complete: bool
    unresolved_safety_failure: bool
    next_boundary_or_null: Optional[str]


def _invalid() -> None:
    raise ChallengerReplacementReadinessError(
        "CHALLENGER_REPLACEMENT_READINESS_FACTS_INVALID"
    )


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _invalid()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _invalid()
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or parsed.microsecond % 1000
    ):
        _invalid()
    canonical = (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    if value != canonical:
        _invalid()
    return parsed.astimezone(timezone.utc)


def _count(value: object) -> bool:
    return type(value) is int and 0 <= value <= (1 << 53) - 1


def _validate_fact(value: object, expected_scheduled: datetime) -> None:
    if type(value) is not OpportunityReadinessFact:
        _invalid()
    scheduled = _time(value.scheduled_for)
    if (
        scheduled != expected_scheduled
        or value.opportunity_id != opportunity_id_for(value.scheduled_for)
        or value.outcome not in _OUTCOME
        or value.position_before not in _POSITION
        or value.position_after not in _POSITION
        or value.product_or_null not in {None, "spot", "perpetual"}
        or value.lifecycle_status_or_null
        not in {None, "RECONCILED_FIXTURE", "FAILED_CLOSED"}
        or type(value.economic_gap_locked) is not bool
        or not isinstance(value.unresolved_reason_codes, tuple)
        or any(
            not isinstance(reason, str) or not reason
            for reason in value.unresolved_reason_codes
        )
        or len(set(value.unresolved_reason_codes))
        != len(value.unresolved_reason_codes)
    ):
        _invalid()
    _time(value.terminal_recorded_at)
    if value.outcome == "OBSERVED":
        if (
            value.observed_at_or_null is None
            or value.missed_reason_or_null is not None
            or value.detected_at_or_null is not None
            or not isinstance(value.result_evidence_sha256_or_null, str)
            or _HASH.fullmatch(value.result_evidence_sha256_or_null) is None
        ):
            _invalid()
        _time(value.observed_at_or_null)
    elif (
        value.observed_at_or_null is not None
        or not isinstance(value.missed_reason_or_null, str)
        or not value.missed_reason_or_null
        or value.detected_at_or_null is None
        or value.result_evidence_sha256_or_null is not None
    ):
        _invalid()
    else:
        _time(value.detected_at_or_null)


def _validate(
    facts: object, boundary: object
) -> Tuple[Optional[datetime], datetime]:
    if (
        type(facts) is not ReplacementReadinessFacts
        or type(boundary) is not _ReplacementReadinessBoundary
        or facts.qualification != _QUALIFICATION
        or boundary.qualification != _BOUNDARY_QUALIFICATION
        or _PLAN_ID.fullmatch(facts.plan_id) is None
        or _HASH.fullmatch(facts.plan_hash) is None
        or _HASH.fullmatch(facts.event_evidence_identity_hash) is None
        or _HASH.fullmatch(facts.release_provenance_hash) is None
        or (
            facts.event_chain_end_hash_or_null is not None
            and (
                not isinstance(facts.event_chain_end_hash_or_null, str)
                or _HASH.fullmatch(facts.event_chain_end_hash_or_null) is None
            )
        )
        or not isinstance(facts.opportunities, tuple)
        or facts.current_position not in _POSITION
    ):
        _invalid()
    counts = (
        facts.terminal_opportunity_count,
        facts.observed_opportunity_count,
        facts.missed_opportunity_count,
        facts.current_consecutive_missed,
        facts.maximum_consecutive_missed,
        facts.open_order_count,
        facts.unknown_order_count,
        facts.incident_count,
    )
    if not all(_count(value) for value in counts):
        _invalid()
    if (
        facts.terminal_opportunity_count != len(facts.opportunities)
        or facts.observed_opportunity_count + facts.missed_opportunity_count
        != facts.terminal_opportunity_count
    ):
        _invalid()
    start_values = (
        boundary.start_opportunity_id_or_null,
        boundary.start_scheduled_for_or_null,
        boundary.start_observed_at_or_null,
    )
    if start_values == (None, None, None):
        observed_at = _time(boundary.observed_at)
        if facts.opportunities or facts.terminal_opportunity_count:
            _invalid()
        return None, observed_at
    if any(value is None for value in start_values):
        _invalid()
    start = _time(boundary.start_scheduled_for_or_null)
    start_observed = _time(boundary.start_observed_at_or_null)
    observed_at = _time(boundary.observed_at)
    if (
        boundary.start_opportunity_id_or_null
        != opportunity_id_for(boundary.start_scheduled_for_or_null)
        or start_observed < start
        or observed_at < start_observed
    ):
        _invalid()
    if not facts.opportunities:
        if facts.evidence_failure_kind_or_null is None:
            _invalid()
        return start_observed, observed_at
    first = facts.opportunities[0]
    if (
        first.outcome != "OBSERVED"
        or first.opportunity_id != boundary.start_opportunity_id_or_null
        or first.scheduled_for != boundary.start_scheduled_for_or_null
        or first.observed_at_or_null != boundary.start_observed_at_or_null
    ):
        _invalid()
    for index, item in enumerate(facts.opportunities):
        scheduled = start + index * _CADENCE
        _validate_fact(item, scheduled)
        terminal = _time(item.terminal_recorded_at)
        event_time = _time(
            item.observed_at_or_null
            if item.outcome == "OBSERVED"
            else item.detected_at_or_null
        )
        if (
            terminal < scheduled
            or terminal > observed_at
            or event_time < scheduled
            or event_time > observed_at
        ):
            _invalid()
    return start_observed, observed_at


def _due_count(start_scheduled: datetime, observed_at: datetime) -> int:
    last_due_schedule = observed_at - _CAPTURE_CLOSE_OFFSET
    if last_due_schedule < start_scheduled:
        return 0
    return int((last_due_schedule - start_scheduled) // _CADENCE) + 1


def _cycle_counts(
    opportunities: Tuple[OpportunityReadinessFact, ...],
) -> Tuple[int, int, Tuple[str, ...]]:
    active_product = None
    spot = 0
    perpetual = 0
    reasons = []
    for fact in opportunities:
        if fact.outcome != "OBSERVED":
            continue
        if fact.lifecycle_status_or_null != "RECONCILED_FIXTURE":
            _append_once(reasons, "LIFECYCLE_NOT_RECONCILED")
            if fact.position_after == "FLAT":
                active_product = None
            continue
        transition = (fact.position_before, fact.position_after)
        if transition in {
            ("SPOT_LONG", "PERP_SHORT"),
            ("PERP_SHORT", "SPOT_LONG"),
        }:
            _append_once(reasons, "CROSS_PRODUCT_REVERSAL_WITHOUT_FLAT")
            active_product = None
            continue
        if transition == ("FLAT", "SPOT_LONG") and fact.product_or_null == "spot":
            if active_product is not None:
                _append_once(reasons, "DUPLICATE_POSITION_ENTRY_TRANSITION")
            active_product = "spot"
        elif (
            transition == ("FLAT", "PERP_SHORT")
            and fact.product_or_null == "perpetual"
        ):
            if active_product is not None:
                _append_once(reasons, "DUPLICATE_POSITION_ENTRY_TRANSITION")
            active_product = "perpetual"
        elif (
            transition == ("SPOT_LONG", "FLAT")
            and fact.product_or_null == "spot"
            and active_product == "spot"
        ):
            spot += 1
            active_product = None
        elif (
            transition == ("PERP_SHORT", "FLAT")
            and fact.product_or_null == "perpetual"
            and active_product == "perpetual"
        ):
            perpetual += 1
            active_product = None
    return spot, perpetual, tuple(reasons)


def _append_once(values: list, value: str) -> None:
    if value not in values:
        values.append(value)


def _policy(
    facts: ReplacementReadinessFacts,
    *,
    elapsed_days: int,
    terminal_complete: bool,
    observed_coverage: bool,
    spot_cycles: int,
    perpetual_cycles: int,
    cycle_reason_codes: Tuple[str, ...],
    started: bool,
) -> Tuple[str, Tuple[str, ...]]:
    confirmed = list(cycle_reason_codes)
    for fact in facts.opportunities:
        for reason in fact.unresolved_reason_codes:
            _append_once(confirmed, reason)
        if fact.economic_gap_locked:
            _append_once(confirmed, "ECONOMIC_GAP_LOCKED")
    if facts.incident_count:
        _append_once(confirmed, "S0_OR_S1_INCIDENT")
    if facts.unknown_order_count:
        _append_once(confirmed, "UNKNOWN_ORDER_PRESENT")
    if facts.open_order_count:
        _append_once(confirmed, "OPEN_ORDER_PRESENT_AT_BOUNDARY")
    if facts.reconciliation_status == "FAILED_CLOSED":
        _append_once(confirmed, "LEDGER_POSITION_MISMATCH")
    if facts.current_position != "FLAT":
        _append_once(confirmed, "NON_FLAT_TERMINAL_POSITION")
        if facts.protective_stop_status != "CONFIRMED_FIXTURE":
            _append_once(
                confirmed, "PROTECTIVE_STOP_MISSING_OR_UNCONFIRMED"
            )
    if facts.risk_state in {"HALT", "HARD_BOUNDARY"}:
        _append_once(confirmed, "STAGE_FAILED_RISK_LOCK")
    if (
        facts.daily_loss_boundary_state == "BREACHED"
        or facts.drawdown_boundary_state == "BREACHED"
    ):
        _append_once(confirmed, "SAFETY_BOUNDARY_BREACHED")
    if facts.evidence_failure_kind_or_null == _CONFIRMED_EVIDENCE_FAILURE:
        _append_once(confirmed, _CONFIRMED_EVIDENCE_FAILURE)
    if confirmed:
        return "OPERATIONAL_QUALIFICATION_DID_NOT_PASS", tuple(confirmed)
    if facts.evidence_failure_kind_or_null == _UNKNOWN_EVIDENCE_FAILURE:
        return "INCONCLUSIVE_INSUFFICIENT_EVIDENCE", (_UNKNOWN_EVIDENCE_FAILURE,)
    if not started:
        return "NOT_STARTED", ()
    if elapsed_days < 7:
        return "COLLECTING_BEFORE_MINIMUM_DURATION", ()

    pending = []
    if not terminal_complete:
        pending.append("TERMINAL_COVERAGE_INCOMPLETE")
    if not observed_coverage:
        pending.append("MINIMUM_OBSERVED_COVERAGE_NOT_MET")
    if spot_cycles + perpetual_cycles < 3:
        pending.append("MINIMUM_STRATEGY_CYCLES_NOT_MET")
    if spot_cycles == 0:
        pending.append("SPOT_ROUNDTRIP_NOT_OBSERVED")
    if perpetual_cycles == 0:
        pending.append("PERPETUAL_ROUNDTRIP_NOT_OBSERVED")
    if pending:
        return "PENDING_AUTOMATIC_EXTENSION", tuple(pending)
    return "OPERATIONAL_QUALIFICATION_PASS", ()


def evaluate_challenger_replacement_operational_readiness(
    facts: ReplacementReadinessFacts,
    boundary: _ReplacementReadinessBoundary,
) -> OperationalReadinessResult:
    """Evaluate exact fixture policy without granting operational authority."""

    start_observed, observed_at = _validate(facts, boundary)
    started = start_observed is not None
    if started:
        start_scheduled = _time(boundary.start_scheduled_for_or_null)
        due = _due_count(start_scheduled, observed_at)
        elapsed_days = int(
            (observed_at - start_observed).total_seconds() // 86400
        )
    else:
        due = 0
        elapsed_days = 0
    observed_coverage = (
        due > 0 and facts.observed_opportunity_count * 100 >= due * 95
    )
    terminal_complete = facts.terminal_opportunity_count == due
    spot_cycles, perpetual_cycles, cycle_reasons = _cycle_counts(
        facts.opportunities
    )
    policy_status, reason_codes = _policy(
        facts,
        elapsed_days=elapsed_days,
        terminal_complete=terminal_complete,
        observed_coverage=observed_coverage,
        spot_cycles=spot_cycles,
        perpetual_cycles=perpetual_cycles,
        cycle_reason_codes=cycle_reasons,
        started=started,
    )
    return OperationalReadinessResult(
        evidence_qualification=_QUALIFICATION,
        policy_status=policy_status,
        authority_status="FIXTURE_POLICY_RESULT_NOT_OPERATIONAL",
        elapsed_complete_days=elapsed_days,
        due_opportunity_count=due,
        terminal_opportunity_count=facts.terminal_opportunity_count,
        observed_opportunity_count=facts.observed_opportunity_count,
        missed_opportunity_count=facts.missed_opportunity_count,
        observed_coverage_numerator=facts.observed_opportunity_count,
        observed_coverage_denominator=due,
        meets_minimum_observed_coverage=observed_coverage,
        terminal_coverage_complete=terminal_complete,
        strategy_cycle_count=spot_cycles + perpetual_cycles,
        spot_roundtrip_count=spot_cycles,
        perpetual_roundtrip_count=perpetual_cycles,
        reason_codes=reason_codes,
    )


def observe_challenger_replacement_economic_tail(
    facts: ReplacementReadinessFacts,
    boundary: _ReplacementReadinessBoundary,
) -> EconomicTailObservation:
    """Expose structural progress only; no economic-final evaluator exists."""

    operational = evaluate_challenger_replacement_operational_readiness(
        facts, boundary
    )
    started = boundary.start_observed_at_or_null is not None
    unresolved_safety = operational.policy_status == (
        "OPERATIONAL_QUALIFICATION_DID_NOT_PASS"
    )
    evidence_unavailable = operational.policy_status == (
        "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
    )
    if unresolved_safety or evidence_unavailable:
        status = "FAILED_CLOSED"
    elif not started:
        status = "NOT_STARTED"
    elif operational.elapsed_complete_days < 90:
        status = "WITHHELD_PRE_TAIL"
    else:
        status = "TAIL_REACHED_FINAL_EVALUATOR_NOT_PREREGISTERED"

    next_boundary = None
    if status == "WITHHELD_PRE_TAIL":
        start_observed = _time(boundary.start_observed_at_or_null)
        next_boundary = (
            (start_observed + timedelta(days=90))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
    lifecycle_complete = (
        not facts.active_opportunity_present
        and facts.current_position == "FLAT"
        and all(
            fact.outcome != "OBSERVED"
            or fact.lifecycle_status_or_null == "RECONCILED_FIXTURE"
            for fact in facts.opportunities
        )
    )
    return EconomicTailObservation(
        evidence_qualification=_QUALIFICATION,
        status=status,
        elapsed_complete_days=operational.elapsed_complete_days,
        minimum_calendar_days=90,
        due_opportunity_count=operational.due_opportunity_count,
        terminal_opportunity_count=operational.terminal_opportunity_count,
        observed_opportunity_count=operational.observed_opportunity_count,
        missed_opportunity_count=operational.missed_opportunity_count,
        meets_minimum_observed_coverage=(
            operational.meets_minimum_observed_coverage
        ),
        terminal_coverage_complete=operational.terminal_coverage_complete,
        lifecycle_complete=lifecycle_complete,
        unresolved_safety_failure=unresolved_safety,
        next_boundary_or_null=next_boundary,
    )
