"""One-pass, fixture-only readiness observation over strict v0.72 replay."""

from dataclasses import dataclass
import hashlib
from typing import Mapping

from .canonical import business_hash, canonical_json
from .challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityError,
    ChallengerReplacementOpportunityState,
)
from .challenger_replacement_opportunity_projection import opportunity_id_for
from .challenger_replacement_plan import _strict_json_bytes
from .challenger_replacement_plan_v3 import (
    challenger_replacement_plan_v3_reasons,
)
from .challenger_replacement_readiness import (
    EconomicTailObservation,
    OpportunityReadinessFact,
    OperationalReadinessResult,
    ReplacementReadinessFacts,
    _ReplacementReadinessBoundary,
    evaluate_challenger_replacement_operational_readiness,
    observe_challenger_replacement_economic_tail,
)


_V072_COMMIT = "44d294a8fbc55a0fb4f9fe0537bb868824815d80"
_HASH = frozenset("0123456789abcdef")


class ChallengerReplacementReadinessObserverError(ValueError):
    """The read-only fixture observation failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ReplacementReadinessReleaseProvenance:
    __slots__ = (
        "release_tag",
        "peeled_commit",
        "package_version",
        "manifest_version",
        "build_input_tree_hash",
        "manifest_hash",
    )

    release_tag: str
    peeled_commit: str
    package_version: str
    manifest_version: str
    build_input_tree_hash: str
    manifest_hash: str


@dataclass(frozen=True)
class ReplacementReadinessObservation:
    __slots__ = (
        "authority_status",
        "service_health",
        "evidence_health",
        "observed_at",
        "event_evidence_identity_hash",
        "release_provenance_hash",
        "provenance_hash",
        "facts",
        "operational",
        "economic",
    )

    authority_status: str
    service_health: str
    evidence_health: str
    observed_at: str
    event_evidence_identity_hash: str
    release_provenance_hash: str
    provenance_hash: str
    facts: ReplacementReadinessFacts
    operational: OperationalReadinessResult
    economic: EconomicTailObservation


class ChallengerReplacementReadinessReplaySource:
    """Reviewed fixture façade whose only public operation is replay."""

    def __init__(self, state):
        if type(state) is not ChallengerReplacementOpportunityState:
            _invalid("CHALLENGER_REPLACEMENT_READINESS_REPLAY_SOURCE_INVALID")
        build = state.build_identity
        if (
            build.get("release_tag") != "v0.72.0-fixture"
            or build.get("package_version") != "0.72.0"
            or build.get("manifest_version") != "1.66.0"
        ):
            _invalid("CHALLENGER_REPLACEMENT_READINESS_REPLAY_SOURCE_INVALID")
        self._state = state
        self._event_evidence_identity_hash = business_hash(build)
        self._plan_id = state.plan["plan_id"]
        self._plan_hash = state.plan["plan_hash"]

    def replay(self):
        return self._state.replay()


def _invalid(reason="CHALLENGER_REPLACEMENT_READINESS_OBSERVER_INVALID"):
    raise ChallengerReplacementReadinessObserverError(reason)


def _sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and not set(value) - _HASH
    )


def _release_document(value):
    if (
        type(value) is not ReplacementReadinessReleaseProvenance
        or value.release_tag != "v0.72.0"
        or value.peeled_commit != _V072_COMMIT
        or value.package_version != "0.72.0"
        or value.manifest_version != "1.66.0"
        or not _sha(value.build_input_tree_hash)
        or not _sha(value.manifest_hash)
    ):
        _invalid("CHALLENGER_REPLACEMENT_READINESS_RELEASE_PROVENANCE_INVALID")
    return {
        name: getattr(value, name)
        for name in ReplacementReadinessReleaseProvenance.__slots__
    }


def _plan(plan_bytes, replay_source):
    if not isinstance(plan_bytes, bytes) or not plan_bytes:
        _invalid("CHALLENGER_REPLACEMENT_READINESS_PLAN_INVALID")
    try:
        plan = dict(_strict_json_bytes(plan_bytes))
        canonical = canonical_json(plan).encode("utf-8")
        if plan_bytes not in (canonical, canonical + b"\n"):
            _invalid("CHALLENGER_REPLACEMENT_READINESS_PLAN_INVALID")
    except ChallengerReplacementReadinessObserverError:
        raise
    except (ValueError, TypeError, UnicodeError) as error:
        raise ChallengerReplacementReadinessObserverError(
            "CHALLENGER_REPLACEMENT_READINESS_PLAN_INVALID"
        ) from error
    if (
        challenger_replacement_plan_v3_reasons(plan)
        or plan.get("plan_id") != replay_source._plan_id
        or plan.get("plan_hash") != replay_source._plan_hash
    ):
        _invalid("CHALLENGER_REPLACEMENT_READINESS_PLAN_INVALID")
    return plan


def _observed_fact(slot, tracked_position):
    evidence = slot.get("result_evidence")
    if not isinstance(evidence, Mapping):
        _invalid()
    previous = evidence.get("previous_snapshot")
    current = evidence.get("next_snapshot")
    lifecycle = evidence.get("lifecycle")
    opportunity = evidence.get("opportunity")
    if not all(
        isinstance(value, Mapping)
        for value in (previous, current, lifecycle, opportunity)
    ):
        _invalid()
    position_before = previous.get("position_state")
    position_after = current.get("position_state")
    if position_before != tracked_position:
        _invalid(
            "CONFIRMED_EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE"
        )
    product = None
    if "SPOT_LONG" in (position_before, position_after):
        product = "spot"
    elif "PERP_SHORT" in (position_before, position_after):
        product = "perpetual"
    stop = current.get("protective_stop_or_null")
    stop_status = "NOT_REQUIRED_FLAT"
    reasons = []
    if position_after != "FLAT":
        if isinstance(stop, Mapping):
            stop_status = stop.get("status")
        else:
            stop_status = "MISSING_OR_UNCONFIRMED"
        if stop_status != "CONFIRMED_FIXTURE":
            reasons.append("DISASTER_STOP_MISSING_OR_UNCONFIRMED")
    lifecycle_status = lifecycle.get("status")
    if lifecycle_status != "RECONCILED_FIXTURE":
        reason = lifecycle.get("reason_code_or_null")
        reasons.append(
            reason if isinstance(reason, str) and reason else "LIFECYCLE_NOT_RECONCILED"
        )
    if current.get("economic_gap_locked") is True:
        reasons.append("ECONOMIC_GAP_LOCKED")
    unresolved = current.get("unresolved_intent_ids")
    if isinstance(unresolved, list) and unresolved:
        reasons.append("UNRESOLVED_UNKNOWN")
    risk = current.get("risk_state")
    return OpportunityReadinessFact(
        opportunity_id=opportunity.get("opportunity_id"),
        scheduled_for=opportunity.get("scheduled_for"),
        outcome="OBSERVED",
        terminal_recorded_at=opportunity.get("observed_at"),
        observed_at_or_null=opportunity.get("observed_at"),
        missed_reason_or_null=None,
        detected_at_or_null=None,
        result_evidence_sha256_or_null=slot.get("result_evidence_sha256"),
        position_before=position_before,
        position_after=position_after,
        product_or_null=product,
        lifecycle_status_or_null=lifecycle_status,
        risk_state="NORMAL" if risk == "RISK_CLEAR" else "HALT",
        protective_stop_status=stop_status,
        economic_gap_locked=current.get("economic_gap_locked"),
        unresolved_reason_codes=tuple(dict.fromkeys(reasons)),
    )


def _facts(plan, projection, replay_source, release_hash):
    opportunities = []
    tracked_position = "FLAT"
    last_missed = None
    for scheduled_for in projection.get("terminal_scheduled_for", ()):
        opportunity_id = opportunity_id_for(scheduled_for)
        slot = projection.get("opportunities", {}).get(opportunity_id)
        if not isinstance(slot, Mapping):
            _invalid()
        if slot.get("outcome") == "OBSERVED":
            fact = _observed_fact(slot, tracked_position)
            tracked_position = fact.position_after
        elif slot.get("outcome") == "MISSED":
            last_missed = slot.get("reason_code")
            product = {
                "SPOT_LONG": "spot",
                "PERP_SHORT": "perpetual",
            }.get(tracked_position)
            locked = tracked_position != "FLAT"
            fact = OpportunityReadinessFact(
                opportunity_id=opportunity_id,
                scheduled_for=scheduled_for,
                outcome="MISSED",
                terminal_recorded_at=slot.get("detected_at"),
                observed_at_or_null=None,
                missed_reason_or_null=last_missed,
                detected_at_or_null=slot.get("detected_at"),
                result_evidence_sha256_or_null=None,
                position_before=tracked_position,
                position_after=tracked_position,
                product_or_null=product,
                lifecycle_status_or_null=None,
                risk_state="HALT" if locked else "NORMAL",
                protective_stop_status=(
                    "UNVERIFIED_DUE_TO_MISSED" if locked else "NOT_REQUIRED_FLAT"
                ),
                economic_gap_locked=locked,
                unresolved_reason_codes=(
                    ("ECONOMIC_GAP_LOCKED",) if locked else ()
                ),
            )
        else:
            _invalid()
        opportunities.append(fact)
    latest = projection.get("latest_next_snapshot_or_null") or {}
    unresolved = latest.get("unresolved_intent_ids") or []
    stop = latest.get("protective_stop_or_null")
    current_position = latest.get("position_state", tracked_position)
    stop_status = (
        "NOT_REQUIRED_FLAT"
        if current_position == "FLAT"
        else stop.get("status") if isinstance(stop, Mapping) else "MISSING_OR_UNCONFIRMED"
    )
    observed_count = projection.get("observed_opportunity_count")
    missed_count = projection.get("missed_opportunity_count")
    return ReplacementReadinessFacts(
        qualification="STRICT_V072_FIXTURE_SANITIZED",
        plan_id=plan["plan_id"],
        plan_hash=plan["plan_hash"],
        event_evidence_identity_hash=replay_source._event_evidence_identity_hash,
        release_provenance_hash=release_hash,
        event_chain_end_hash_or_null=projection.get("last_event_hash"),
        opportunities=tuple(opportunities),
        terminal_opportunity_count=projection.get("terminal_opportunity_count"),
        observed_opportunity_count=observed_count,
        missed_opportunity_count=missed_count,
        current_consecutive_missed=projection.get("current_consecutive_missed"),
        maximum_consecutive_missed=projection.get("maximum_consecutive_missed"),
        last_missed_reason_or_null=last_missed,
        active_opportunity_present=(
            projection.get("active_opportunity_id") is not None
        ),
        current_position=current_position,
        gross_exposure=latest.get("gross_exposure", "0"),
        open_order_count=1 if latest.get("active_order_or_null") else 0,
        unknown_order_count=len(unresolved),
        reconciliation_status=(
            "RECONCILED"
            if all(
                item.outcome != "OBSERVED"
                or item.lifecycle_status_or_null == "RECONCILED_FIXTURE"
                for item in opportunities
            )
            else "FAILED_CLOSED"
        ),
        protective_stop_status=stop_status,
        risk_state=("NORMAL" if latest.get("risk_state") == "RISK_CLEAR" else "HALT"),
        daily_loss_boundary_state="NORMAL",
        drawdown_boundary_state=(
            "BREACHED" if latest.get("risk_state") == "STAGE_FAILED" else "NORMAL"
        ),
        incident_count=0,
        evidence_failure_kind_or_null=None,
    )


def _failure_facts(plan, replay_source, release_hash, failure_kind):
    return ReplacementReadinessFacts(
        qualification="STRICT_V072_FIXTURE_SANITIZED",
        plan_id=plan["plan_id"],
        plan_hash=plan["plan_hash"],
        event_evidence_identity_hash=replay_source._event_evidence_identity_hash,
        release_provenance_hash=release_hash,
        event_chain_end_hash_or_null=None,
        opportunities=(),
        terminal_opportunity_count=0,
        observed_opportunity_count=0,
        missed_opportunity_count=0,
        current_consecutive_missed=0,
        maximum_consecutive_missed=0,
        last_missed_reason_or_null=None,
        active_opportunity_present=False,
        current_position="FLAT",
        gross_exposure="0",
        open_order_count=0,
        unknown_order_count=0,
        reconciliation_status="NOT_AVAILABLE",
        protective_stop_status="NOT_AVAILABLE",
        risk_state="NOT_AVAILABLE",
        daily_loss_boundary_state="NOT_AVAILABLE",
        drawdown_boundary_state="NOT_AVAILABLE",
        incident_count=0,
        evidence_failure_kind_or_null=failure_kind,
    )


def _compose(facts, boundary, *, service_health, evidence_health):
    operational = evaluate_challenger_replacement_operational_readiness(
        facts, boundary
    )
    economic = observe_challenger_replacement_economic_tail(facts, boundary)
    provenance = {
        "event_evidence_identity_hash": facts.event_evidence_identity_hash,
        "release_provenance_hash": facts.release_provenance_hash,
        "event_chain_end_hash_or_null": facts.event_chain_end_hash_or_null,
        "observed_at": boundary.observed_at,
    }
    return ReplacementReadinessObservation(
        authority_status="FIXTURE_NOT_OPERATIONAL",
        service_health=service_health,
        evidence_health=evidence_health,
        observed_at=boundary.observed_at,
        event_evidence_identity_hash=facts.event_evidence_identity_hash,
        release_provenance_hash=facts.release_provenance_hash,
        provenance_hash=business_hash(provenance),
        facts=facts,
        operational=operational,
        economic=economic,
    )


def observe_challenger_replacement_readiness(
    *, plan_bytes, replay_source, boundary, release_provenance
) -> ReplacementReadinessObservation:
    """Replay once, sanitize strict v0.72 fixture evidence and evaluate."""

    if (
        type(replay_source) is not ChallengerReplacementReadinessReplaySource
        or type(boundary) is not _ReplacementReadinessBoundary
    ):
        _invalid()
    plan = _plan(plan_bytes, replay_source)
    release_document = _release_document(release_provenance)
    release_hash = business_hash(release_document)
    try:
        projection = replay_source.replay()
    except ChallengerReplacementOpportunityError as error:
        failure_kind = (
            "EVIDENCE_SOURCE_UNAVAILABLE_OR_QUALIFICATION_UNKNOWN"
            if error.reason_code == "CHALLENGER_REPLACEMENT_EVENT_IO_FAILED"
            else "CONFIRMED_EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE"
        )
        facts = _failure_facts(
            plan, replay_source, release_hash, failure_kind
        )
        return _compose(
            facts,
            boundary,
            service_health="FAILED_CLOSED",
            evidence_health=(
                "NOT_AVAILABLE"
                if failure_kind.startswith("EVIDENCE_SOURCE_UNAVAILABLE")
                else "FAILED_CLOSED"
            ),
        )
    if not isinstance(projection, Mapping):
        _invalid()
    if projection.get("orphan_staging_count"):
        facts = _failure_facts(
            plan,
            replay_source,
            release_hash,
            "CONFIRMED_EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE",
        )
        return _compose(
            facts,
            boundary,
            service_health="FAILED_CLOSED",
            evidence_health="FAILED_CLOSED",
        )
    facts = _facts(plan, projection, replay_source, release_hash)
    return _compose(
        facts,
        boundary,
        service_health="NOT_LOADED",
        evidence_health="VERIFIED",
    )
