"""Pure, tail-blind operations projection boundary."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional

from .canonical import business_hash


class OperationsProjectionError(ValueError):
    """An operations projection failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class SourceProvenance:
    __slots__ = ("source_kind", "source_sha256", "observed_at")

    source_kind: str
    source_sha256: str
    observed_at: str


@dataclass(frozen=True)
class ReleaseOperationsSource:
    __slots__ = (
        "package_version",
        "main_commit",
        "release_tag",
        "tag_commit",
        "identity_status",
        "provenance",
    )

    package_version: str
    main_commit: str
    release_tag: str
    tag_commit: str
    identity_status: str
    provenance: SourceProvenance


@dataclass(frozen=True)
class ChallengerOperationsSource:
    __slots__ = (
        "phase",
        "service_health",
        "evidence_health",
        "verified_slot_count",
        "completed_episode_count",
        "active_episode_present",
        "next_required_slot",
        "gate_status",
        "incident_count",
        "provenance",
    )

    phase: str
    service_health: str
    evidence_health: str
    verified_slot_count: int
    completed_episode_count: int
    active_episode_present: bool
    next_required_slot: Optional[str]
    gate_status: str
    incident_count: int
    provenance: SourceProvenance


@dataclass(frozen=True)
class SystemPaperOperationsSource:
    __slots__ = (
        "phase",
        "service_health",
        "evidence_health",
        "elapsed_days",
        "verified_slot_count",
        "next_required_slot",
        "submitted_order_count",
        "filled_order_count",
        "partially_filled_order_count",
        "cancelled_order_count",
        "rejected_order_count",
        "timeout_unknown_order_count",
        "reconciliation_status",
        "risk_state",
        "gate_status",
        "incident_count",
        "provenance",
    )

    phase: str
    service_health: str
    evidence_health: str
    elapsed_days: int
    verified_slot_count: int
    next_required_slot: Optional[str]
    submitted_order_count: int
    filled_order_count: int
    partially_filled_order_count: int
    cancelled_order_count: int
    rejected_order_count: int
    timeout_unknown_order_count: int
    reconciliation_status: str
    risk_state: str
    gate_status: str
    incident_count: int
    provenance: SourceProvenance


@dataclass(frozen=True)
class OperationsProjectionSources:
    __slots__ = (
        "release_loader",
        "challenger_loader",
        "system_paper_loader",
    )

    release_loader: Callable[[], ReleaseOperationsSource]
    challenger_loader: Callable[[], ChallengerOperationsSource]
    system_paper_loader: Callable[[], SystemPaperOperationsSource]


def _load_source(loader, expected_type):
    try:
        value = loader()
    except Exception as error:
        raise OperationsProjectionError(
            "OPERATIONS_PROJECTION_SOURCE_LOAD_FAILED"
        ) from error
    if type(value) is not expected_type:
        raise OperationsProjectionError("OPERATIONS_PROJECTION_SOURCE_INVALID")
    return value


def _provenance(value: SourceProvenance, freshness: str) -> Dict[str, Any]:
    return {
        "source_kind": value.source_kind,
        "source_sha256": value.source_sha256,
        "observed_at": value.observed_at,
        "freshness": freshness,
    }


def build_operations_projection(
    now: str,
    sources: OperationsProjectionSources,
) -> Mapping[str, Any]:
    """Build one allowlisted projection from exactly three injected sources."""

    if type(sources) is not OperationsProjectionSources:
        raise OperationsProjectionError("OPERATIONS_PROJECTION_SOURCES_INVALID")
    release = _load_source(sources.release_loader, ReleaseOperationsSource)
    challenger = _load_source(
        sources.challenger_loader, ChallengerOperationsSource
    )
    system_paper = _load_source(
        sources.system_paper_loader, SystemPaperOperationsSource
    )
    projection: Dict[str, Any] = {
        "$schema": "./operations-projection-v1.schema.json",
        "schema_version": "1.0.0",
        "projected_at": now,
        "status": "HEALTHY",
        "release": {
            "package_version": release.package_version,
            "main_commit": release.main_commit,
            "release_tag": release.release_tag,
            "tag_commit": release.tag_commit,
            "identity_status": release.identity_status,
            "provenance": _provenance(
                release.provenance, "IDENTITY_VERIFIED"
            ),
        },
        "challenger": {
            "phase": challenger.phase,
            "service_health": challenger.service_health,
            "evidence_health": challenger.evidence_health,
            "verified_slot_count": challenger.verified_slot_count,
            "completed_episode_count": challenger.completed_episode_count,
            "active_episode_present": challenger.active_episode_present,
            "next_required_slot": challenger.next_required_slot,
            "gate_status": challenger.gate_status,
            "incident_count": challenger.incident_count,
            "provenance": _provenance(challenger.provenance, "FRESH"),
        },
        "system_paper": {
            "phase": system_paper.phase,
            "service_health": system_paper.service_health,
            "evidence_health": system_paper.evidence_health,
            "elapsed_days": system_paper.elapsed_days,
            "verified_slot_count": system_paper.verified_slot_count,
            "next_required_slot": system_paper.next_required_slot,
            "submitted_order_count": system_paper.submitted_order_count,
            "filled_order_count": system_paper.filled_order_count,
            "partially_filled_order_count": (
                system_paper.partially_filled_order_count
            ),
            "cancelled_order_count": system_paper.cancelled_order_count,
            "rejected_order_count": system_paper.rejected_order_count,
            "timeout_unknown_order_count": (
                system_paper.timeout_unknown_order_count
            ),
            "reconciliation_status": system_paper.reconciliation_status,
            "risk_state": system_paper.risk_state,
            "gate_status": system_paper.gate_status,
            "incident_count": system_paper.incident_count,
            "provenance": _provenance(system_paper.provenance, "FRESH"),
        },
    }
    projection["projection_hash"] = business_hash(
        {"purpose": "TAIL_BLIND_OPERATIONS_PROJECTION_V1", **projection}
    )
    return projection
