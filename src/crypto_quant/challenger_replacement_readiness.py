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


def _validate(facts: object, boundary: object) -> Tuple[datetime, datetime]:
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
    if (
        boundary.start_scheduled_for_or_null is None
        or boundary.start_observed_at_or_null is None
        or boundary.start_opportunity_id_or_null is None
    ):
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
    for index, item in enumerate(facts.opportunities):
        _validate_fact(item, start + index * _CADENCE)
    return start_observed, observed_at


def _due_count(start_scheduled: datetime, observed_at: datetime) -> int:
    last_due_schedule = observed_at - _CAPTURE_CLOSE_OFFSET
    if last_due_schedule < start_scheduled:
        return 0
    return int((last_due_schedule - start_scheduled) // _CADENCE) + 1


def evaluate_challenger_replacement_operational_readiness(
    facts: ReplacementReadinessFacts,
    boundary: _ReplacementReadinessBoundary,
) -> OperationalReadinessResult:
    """Evaluate exact fixture policy without granting operational authority."""

    start_observed, observed_at = _validate(facts, boundary)
    start_scheduled = _time(boundary.start_scheduled_for_or_null)
    due = _due_count(start_scheduled, observed_at)
    elapsed_days = int((observed_at - start_observed).total_seconds() // 86400)
    return OperationalReadinessResult(
        evidence_qualification=_QUALIFICATION,
        policy_status="COLLECTING_BEFORE_MINIMUM_DURATION",
        authority_status="FIXTURE_POLICY_RESULT_NOT_OPERATIONAL",
        elapsed_complete_days=elapsed_days,
        due_opportunity_count=due,
        terminal_opportunity_count=facts.terminal_opportunity_count,
        observed_opportunity_count=facts.observed_opportunity_count,
        missed_opportunity_count=facts.missed_opportunity_count,
        observed_coverage_numerator=facts.observed_opportunity_count,
        observed_coverage_denominator=due,
        meets_minimum_observed_coverage=(
            due > 0 and facts.observed_opportunity_count * 100 >= due * 95
        ),
        terminal_coverage_complete=facts.terminal_opportunity_count == due,
        strategy_cycle_count=0,
        spot_roundtrip_count=0,
        perpetual_roundtrip_count=0,
        reason_codes=(),
    )
