"""Pure schedule and health semantics for replacement v3 opportunities."""

from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional, Tuple

from .canonical import utc_datetime


_CADENCE = timedelta(hours=4)
_OPEN_OFFSET = timedelta(seconds=120)
_CLOSE_OFFSET = timedelta(seconds=600)


class ChallengerReplacementOpportunityError(ValueError):
    """DecisionOpportunity semantics failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="CHALLENGER_REPLACEMENT_OPPORTUNITY_INPUT_INVALID"):
    raise ChallengerReplacementOpportunityError(reason)


def _time(value, *, grid=False):
    if not isinstance(value, str):
        _invalid()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ChallengerReplacementOpportunityError(
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_INPUT_INVALID"
        ) from error
    parsed = parsed.astimezone(timezone.utc)
    if (
        parsed.microsecond % 1000
        or utc_datetime(parsed) != value
        or (
            grid
            and (
                parsed.hour % 4
                or parsed.minute
                or parsed.second
                or parsed.microsecond
            )
        )
    ):
        _invalid()
    return parsed


def opportunity_id_for(scheduled_for: str) -> str:
    """Derive the only v3 opportunity identifier from a UTC grid time."""

    _time(scheduled_for, grid=True)
    return "ETHUSDT@" + scheduled_for


def _window(scheduled):
    return scheduled + _OPEN_OFFSET, scheduled + _CLOSE_OFFSET


def _candidate(scheduled, detected):
    opened, closed = _window(scheduled)
    if detected < opened:
        status = "NOT_OPEN"
    elif detected <= closed:
        status = "ELIGIBLE_WINDOW"
    else:
        status = "EXPIRED"
    scheduled_text = utc_datetime(scheduled)
    return {
        "opportunity_id": opportunity_id_for(scheduled_text),
        "scheduled_for": scheduled_text,
        "capture_open": utc_datetime(opened),
        "capture_close": utc_datetime(closed),
        "status": status,
    }


def _schedule_count(start, detected):
    return int((detected - start).total_seconds() // int(_CADENCE.total_seconds())) + 1


def derive_due_opportunities(
    *, start_scheduled_for: str, detected_at: str,
    terminal_scheduled_for: Tuple[str, ...]
):
    """Return missing due opportunities from explicit fixture boundaries."""

    start = _time(start_scheduled_for, grid=True)
    detected = _time(detected_at)
    if detected < start or not isinstance(terminal_scheduled_for, tuple):
        _invalid()
    count = _schedule_count(start, detected)
    if count > 1_000_000 or len(terminal_scheduled_for) > count:
        _invalid()
    for index, value in enumerate(terminal_scheduled_for):
        expected = start + index * _CADENCE
        if _time(value, grid=True) != expected:
            _invalid()
    return tuple(
        _candidate(start + index * _CADENCE, detected)
        for index in range(len(terminal_scheduled_for), count)
    )


def opportunity_coverage(observed_count: int, due_count: int):
    """Return exact coverage without Decimal or binary floating point."""

    if (
        isinstance(observed_count, bool)
        or not isinstance(observed_count, int)
        or isinstance(due_count, bool)
        or not isinstance(due_count, int)
        or observed_count < 0
        or due_count < 0
        or observed_count > due_count
    ):
        _invalid()
    return {
        "coverage_numerator": observed_count,
        "coverage_denominator": due_count,
        "meets_minimum_observed_coverage": (
            None if due_count == 0 else observed_count * 100 >= due_count * 95
        ),
    }


def opportunity_health(
    *, projection: Mapping, start_scheduled_for: Optional[str], detected_at: str
):
    """Overlay explicit fixture boundaries on a boundary-free replay."""

    _time(detected_at)
    if not isinstance(projection, Mapping):
        _invalid()
    if start_scheduled_for is None:
        coverage = opportunity_coverage(0, 0)
        return {
            "due_opportunity_count": 0,
            **coverage,
            "eligibility_status": "NOT_STARTED_NO_START_BOUNDARY",
        }
    terminal = projection.get("terminal_scheduled_for")
    observed = projection.get("observed_opportunity_count")
    if not isinstance(terminal, tuple):
        _invalid()
    start = _time(start_scheduled_for, grid=True)
    detected = _time(detected_at)
    if detected < start:
        _invalid()
    due = _schedule_count(start, detected)
    derive_due_opportunities(
        start_scheduled_for=start_scheduled_for,
        detected_at=detected_at,
        terminal_scheduled_for=terminal,
    )
    if len(terminal) > due:
        _invalid()
    coverage = opportunity_coverage(observed, due)
    status = (
        "BLOCKED_LIFECYCLE_EVIDENCE_NOT_IMPLEMENTED"
        if coverage["meets_minimum_observed_coverage"]
        else "PRE_TAIL_ELIGIBILITY_ONLY"
    )
    return {
        "due_opportunity_count": due,
        **coverage,
        "eligibility_status": status,
    }
