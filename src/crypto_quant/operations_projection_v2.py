"""Strict read-only operations projection v2 with replacement-v3 readiness."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
import json
from typing import Any, Dict, Mapping

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json
from .challenger_replacement_readiness_observer import (
    ReplacementReadinessObservation,
)
from .operations_projection import (
    ChallengerOperationsSource,
    ReleaseOperationsSource,
    SourceProvenance,
    SystemPaperOperationsSource,
)


_SCHEMA = "operations-projection-v2.schema.json"
_MAX_BYTES = 1024 * 1024
_MAX_SAFE = (1 << 53) - 1
_BOUNDARY = "COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL"
_FRESH = timedelta(minutes=20)
_FUTURE = timedelta(minutes=5)
_OPERATIONAL = frozenset({
    "NOT_STARTED", "COLLECTING_BEFORE_MINIMUM_DURATION",
    "PENDING_AUTOMATIC_EXTENSION", "OPERATIONAL_QUALIFICATION_PASS",
    "OPERATIONAL_QUALIFICATION_DID_NOT_PASS",
    "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
})
_ECONOMIC = frozenset({
    "NOT_STARTED", "WITHHELD_PRE_TAIL",
    "TAIL_REACHED_FINAL_EVALUATOR_NOT_PREREGISTERED", "FAILED_CLOSED",
})


class OperationsProjectionV2Error(ValueError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class OperationsProjectionV2Sources:
    __slots__ = (
        "release", "legacy_challenger", "replacement_v3", "system_paper"
    )
    release: ReleaseOperationsSource
    legacy_challenger: ChallengerOperationsSource
    replacement_v3: ReplacementReadinessObservation
    system_paper: SystemPaperOperationsSource


@dataclass(frozen=True)
class _OperationsProjectionV2Boundary:
    __slots__ = ("qualification", "observed_at")
    qualification: str
    observed_at: str


def _error(reason):
    raise OperationsProjectionV2Error(reason)


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _error("OPERATIONS_PROJECTION_V2_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OperationsProjectionV2Error(
            "OPERATIONS_PROJECTION_V2_TIME_INVALID"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.microsecond % 1000:
        _error("OPERATIONS_PROJECTION_V2_TIME_INVALID")
    canonical = parsed.astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    if canonical != value:
        _error("OPERATIONS_PROJECTION_V2_TIME_INVALID")
    return parsed.astimezone(timezone.utc)


def _count(value):
    return type(value) is int and 0 <= value <= _MAX_SAFE


def _freshness(source: SourceProvenance, now: datetime, *, release=False):
    if type(source) is not SourceProvenance:
        _error("OPERATIONS_PROJECTION_V2_SOURCES_INVALID")
    observed = _utc(source.observed_at)
    if observed > now + _FUTURE:
        _error("OPERATIONS_PROJECTION_V2_SOURCES_INVALID")
    return "IDENTITY_VERIFIED" if release else (
        "FRESH" if now - observed <= _FRESH else "STALE"
    )


def _provenance(value, freshness):
    return {
        "source_kind": value.source_kind,
        "source_sha256": value.source_sha256,
        "observed_at": value.observed_at,
        "freshness": freshness,
    }


def _hash(value):
    return business_hash({"purpose": "TAIL_BLIND_OPERATIONS_PROJECTION_V2", **value})


@lru_cache(maxsize=1)
def _validator():
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _replacement(value: ReplacementReadinessObservation):
    facts = value.facts
    operational = value.operational
    economic = value.economic
    next_required = None
    if facts.opportunities:
        previous = _utc(facts.opportunities[-1].scheduled_for)
        scheduled = previous + timedelta(hours=4)
        text = scheduled.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        next_required = {"opportunity_id": "ETHUSDT@" + text, "scheduled_for": text}
    phase = (
        "REPLACEMENT_NOT_STARTED"
        if operational.policy_status == "NOT_STARTED"
        else "COLLECTING"
    )
    return {
        "phase": phase,
        "service_health": value.service_health,
        "evidence_health": value.evidence_health,
        "due_opportunity_count": operational.due_opportunity_count,
        "terminal_opportunity_count": operational.terminal_opportunity_count,
        "observed_opportunity_count": operational.observed_opportunity_count,
        "missed_opportunity_count": operational.missed_opportunity_count,
        "observed_coverage_numerator": operational.observed_coverage_numerator,
        "observed_coverage_denominator": operational.observed_coverage_denominator,
        "meets_minimum_observed_coverage": operational.meets_minimum_observed_coverage,
        "terminal_coverage_complete": operational.terminal_coverage_complete,
        "current_consecutive_missed": facts.current_consecutive_missed,
        "maximum_consecutive_missed": facts.maximum_consecutive_missed,
        "last_missed_reason_or_null": facts.last_missed_reason_or_null,
        "next_required_opportunity": next_required,
        "operational_elapsed_days": operational.elapsed_complete_days,
        "operational_minimum_days": 7,
        "operational_strategy_cycle_count": operational.strategy_cycle_count,
        "spot_roundtrip_count": operational.spot_roundtrip_count,
        "perpetual_roundtrip_count": operational.perpetual_roundtrip_count,
        "operational_gate_status": operational.policy_status,
        "economic_elapsed_days": economic.elapsed_complete_days,
        "economic_minimum_days": economic.minimum_calendar_days,
        "economic_tail_status": economic.status,
        "current_product": facts.current_position,
        "gross_exposure": facts.gross_exposure,
        "open_order_count": facts.open_order_count,
        "unknown_order_count": facts.unknown_order_count,
        "reconciliation_status": facts.reconciliation_status,
        "protective_stop_status": facts.protective_stop_status,
        "risk_state": facts.risk_state,
        "daily_loss_boundary_state": facts.daily_loss_boundary_state,
        "drawdown_boundary_state": facts.drawdown_boundary_state,
        "incident_count": facts.incident_count,
        "new_risk_advisory": False,
        "provenance": {
            "authority_status": value.authority_status,
            "event_evidence_identity_hash": value.event_evidence_identity_hash,
            "release_provenance_hash": value.release_provenance_hash,
            "provenance_hash": value.provenance_hash,
            "observed_at": value.observed_at,
            "freshness": "FRESH",
        },
    }


def _validate_replacement_source(value: ReplacementReadinessObservation):
    try:
        facts = value.facts
        operational = value.operational
        economic = value.economic
        fact_counts = (
            facts.terminal_opportunity_count,
            facts.observed_opportunity_count,
            facts.missed_opportunity_count,
        )
        operational_counts = (
            operational.terminal_opportunity_count,
            operational.observed_opportunity_count,
            operational.missed_opportunity_count,
        )
        economic_counts = (
            economic.terminal_opportunity_count,
            economic.observed_opportunity_count,
            economic.missed_opportunity_count,
        )
        valid = (
            fact_counts == operational_counts == economic_counts
            and operational.due_opportunity_count == economic.due_opportunity_count
            and operational.observed_coverage_numerator
            == facts.observed_opportunity_count
            and operational.observed_coverage_denominator
            == operational.due_opportunity_count
            and operational.meets_minimum_observed_coverage
            is economic.meets_minimum_observed_coverage
            and operational.terminal_coverage_complete
            is economic.terminal_coverage_complete
            and value.event_evidence_identity_hash
            == facts.event_evidence_identity_hash
            and value.release_provenance_hash == facts.release_provenance_hash
            and operational.evidence_qualification == facts.qualification
            and economic.evidence_qualification == facts.qualification
        )
    except (AttributeError, TypeError):
        valid = False
    if not valid:
        _error("OPERATIONS_PROJECTION_V2_SOURCES_INVALID")


def build_operations_projection_v2(
    sources: OperationsProjectionV2Sources, *, boundary: _OperationsProjectionV2Boundary
) -> bytes:
    if type(sources) is not OperationsProjectionV2Sources:
        _error("OPERATIONS_PROJECTION_V2_SOURCES_INVALID")
    if type(boundary) is not _OperationsProjectionV2Boundary or boundary.qualification != _BOUNDARY:
        _error("OPERATIONS_PROJECTION_V2_BOUNDARY_INVALID")
    now = _utc(boundary.observed_at)
    if (
        type(sources.release) is not ReleaseOperationsSource
        or type(sources.legacy_challenger) is not ChallengerOperationsSource
        or type(sources.replacement_v3) is not ReplacementReadinessObservation
        or type(sources.system_paper) is not SystemPaperOperationsSource
        or sources.replacement_v3.observed_at != boundary.observed_at
    ):
        _error("OPERATIONS_PROJECTION_V2_SOURCES_INVALID")
    _validate_replacement_source(sources.replacement_v3)
    release_fresh = _freshness(sources.release.provenance, now, release=True)
    legacy_fresh = _freshness(sources.legacy_challenger.provenance, now)
    paper_fresh = _freshness(sources.system_paper.provenance, now)
    replacement = _replacement(sources.replacement_v3)
    status = (
        "FAILED_CLOSED"
        if replacement["evidence_health"] == "FAILED_CLOSED"
        else "DEGRADED"
        if (
            sources.legacy_challenger.incident_count
            or legacy_fresh == "STALE"
            or paper_fresh == "STALE"
            or sources.system_paper.phase == "NOT_INSTALLED"
        )
        else "HEALTHY"
    )
    value: Dict[str, Any] = {
        "$schema": "./operations-projection-v2.schema.json",
        "schema_version": "2.0.0",
        "projected_at": boundary.observed_at,
        "status": status,
        "release": {
            "package_version": sources.release.package_version,
            "main_commit": sources.release.main_commit,
            "release_tag": sources.release.release_tag,
            "tag_commit": sources.release.tag_commit,
            "identity_status": sources.release.identity_status,
            "provenance": _provenance(sources.release.provenance, release_fresh),
        },
        "legacy_challenger": {
            "phase": sources.legacy_challenger.phase,
            "service_health": sources.legacy_challenger.service_health,
            "evidence_health": sources.legacy_challenger.evidence_health,
            "verified_slot_count": sources.legacy_challenger.verified_slot_count,
            "completed_episode_count": sources.legacy_challenger.completed_episode_count,
            "active_episode_present": sources.legacy_challenger.active_episode_present,
            "next_required_slot": sources.legacy_challenger.next_required_slot,
            "gate_status": sources.legacy_challenger.gate_status,
            "incident_count": sources.legacy_challenger.incident_count,
            "provenance": _provenance(sources.legacy_challenger.provenance, legacy_fresh),
        },
        "replacement_v3": replacement,
        "system_paper": {
            name: getattr(sources.system_paper, name)
            for name in SystemPaperOperationsSource.__slots__
            if name != "provenance"
        },
    }
    value["system_paper"]["provenance"] = _provenance(
        sources.system_paper.provenance, paper_fresh
    )
    value["projection_hash"] = _hash(value)
    body = canonical_json(value).encode("utf-8")
    load_operations_projection_v2_bytes(body)
    return body


def _strict(body):
    if not isinstance(body, bytes) or not body or len(body) > _MAX_BYTES:
        _error("OPERATIONS_PROJECTION_V2_BYTES_INVALID")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _error("OPERATIONS_PROJECTION_V2_BYTES_INVALID")
            result[key] = value
        return result
    def reject(_value):
        _error("OPERATIONS_PROJECTION_V2_BYTES_INVALID")
    try:
        value = json.loads(
            body.decode("utf-8"), object_pairs_hook=pairs,
            parse_float=reject, parse_constant=reject,
        )
        if not isinstance(value, Mapping) or canonical_json(value).encode("utf-8") != body:
            _error("OPERATIONS_PROJECTION_V2_BYTES_INVALID")
    except OperationsProjectionV2Error:
        raise
    except Exception as error:
        raise OperationsProjectionV2Error(
            "OPERATIONS_PROJECTION_V2_BYTES_INVALID"
        ) from error
    return value


def _semantic(value):
    replacement = value["replacement_v3"]
    counts = tuple(
        replacement[name] for name in (
            "due_opportunity_count", "terminal_opportunity_count",
            "observed_opportunity_count", "missed_opportunity_count",
            "observed_coverage_numerator", "observed_coverage_denominator",
            "current_consecutive_missed", "maximum_consecutive_missed",
            "operational_elapsed_days", "operational_minimum_days",
            "operational_strategy_cycle_count", "spot_roundtrip_count",
            "perpetual_roundtrip_count", "economic_elapsed_days",
            "economic_minimum_days", "open_order_count", "unknown_order_count",
            "incident_count",
        )
    )
    if not all(_count(item) for item in counts):
        _error("OPERATIONS_PROJECTION_V2_SEMANTIC_INVALID")
    due = replacement["due_opportunity_count"]
    terminal = replacement["terminal_opportunity_count"]
    observed = replacement["observed_opportunity_count"]
    missed = replacement["missed_opportunity_count"]
    if (
        terminal > due or observed + missed != terminal
        or replacement["observed_coverage_numerator"] != observed
        or replacement["observed_coverage_denominator"] != due
        or replacement["terminal_coverage_complete"] is not (terminal == due)
        or replacement["meets_minimum_observed_coverage"] is not (
            due > 0 and observed * 100 >= due * 95
        )
        or replacement["operational_gate_status"] not in _OPERATIONAL
        or replacement["economic_tail_status"] not in _ECONOMIC
    ):
        _error("OPERATIONS_PROJECTION_V2_SEMANTIC_INVALID")
    if replacement["operational_gate_status"] == "OPERATIONAL_QUALIFICATION_PASS" and (
        not replacement["terminal_coverage_complete"]
        or not replacement["meets_minimum_observed_coverage"]
        or replacement["operational_strategy_cycle_count"] < 3
        or replacement["spot_roundtrip_count"] < 1
        or replacement["perpetual_roundtrip_count"] < 1
    ):
        _error("OPERATIONS_PROJECTION_V2_SEMANTIC_INVALID")
    if (
        replacement["current_product"] != "FLAT"
        and replacement["protective_stop_status"] != "CONFIRMED_FIXTURE"
    ) or (replacement["unknown_order_count"] and replacement["new_risk_advisory"]):
        _error("OPERATIONS_PROJECTION_V2_SEMANTIC_INVALID")
    if replacement["new_risk_advisory"] is not False:
        _error("OPERATIONS_PROJECTION_V2_SEMANTIC_INVALID")
    provenance = replacement["provenance"]
    if (
        provenance["freshness"] == "STALE"
        and replacement["service_health"] == "HEALTHY"
    ):
        _error("OPERATIONS_PROJECTION_V2_SEMANTIC_INVALID")


def _pre_schema_semantic(value):
    try:
        _semantic(value)
    except (KeyError, TypeError):
        return


def load_operations_projection_v2_bytes(body: bytes) -> Mapping[str, Any]:
    value = _strict(body)
    _pre_schema_semantic(value)
    try:
        errors = tuple(_validator().iter_errors(value))
    except Exception as error:
        raise OperationsProjectionV2Error(
            "OPERATIONS_PROJECTION_V2_SCHEMA_INVALID"
        ) from error
    if errors:
        _error("OPERATIONS_PROJECTION_V2_SCHEMA_INVALID")
    without_hash = dict(value)
    claimed = without_hash.pop("projection_hash")
    if _hash(without_hash) != claimed:
        _error("OPERATIONS_PROJECTION_V2_HASH_MISMATCH")
    _semantic(value)
    return json.loads(canonical_json(value))
