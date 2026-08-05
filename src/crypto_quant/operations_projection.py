"""Pure, tail-blind operations projection boundary."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
import json
import re
from typing import Any, Callable, Dict, Mapping, Optional

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json


_VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SERVICE_HEALTH = frozenset(
    {"NOT_LOADED", "HEALTHY", "DEGRADED", "FAILED_CLOSED"}
)
_EVIDENCE_HEALTH = frozenset(
    {
        "VERIFIED",
        "STALE",
        "INCIDENT_DETECTED",
        "FAILED_CLOSED",
        "NOT_AVAILABLE",
    }
)
_CHALLENGER_PHASES = frozenset(
    {
        "LEGACY_FAILED_REPLACEMENT_NOT_STARTED",
        "REPLACEMENT_NOT_STARTED",
        "COLLECTING",
        "FINAL",
    }
)
_CHALLENGER_TERMINAL_GATES = frozenset(
    {
        "RESEARCH_CONTINUATION_GATE_PASS",
        "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
        "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
    }
)
_CHALLENGER_GATES = _CHALLENGER_TERMINAL_GATES | frozenset(
    {"NOT_AVAILABLE", "WITHHELD_PRE_TAIL"}
)
_SYSTEM_PAPER_PHASES = frozenset(
    {"NOT_INSTALLED", "INSTALLED_NOT_STARTED", "COLLECTING", "FINAL"}
)
_RECONCILIATION = frozenset(
    {"NOT_AVAILABLE", "RECONCILED", "FAILED_CLOSED"}
)
_RISK_STATES = frozenset(
    {
        "NOT_AVAILABLE",
        "NORMAL",
        "WARNING",
        "REDUCE",
        "HALT",
        "HARD_BOUNDARY",
    }
)
_SYSTEM_PAPER_TERMINAL_GATES = frozenset(
    {
        "SYSTEM_PAPER_GATE_PASS",
        "SYSTEM_PAPER_GATE_DID_NOT_PASS",
        "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
    }
)
_SYSTEM_PAPER_GATES = _SYSTEM_PAPER_TERMINAL_GATES | frozenset(
    {"NOT_EVALUATED"}
)
_FRESH_WINDOW = timedelta(minutes=20)
_MAX_FUTURE_SKEW = timedelta(minutes=5)
_SCHEMA = "operations-projection-v1.schema.json"
_MAX_PROJECTION_BYTES = 1024 * 1024
_MAX_SAFE_INTEGER = (1 << 53) - 1


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


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise OperationsProjectionError("OPERATIONS_PROJECTION_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OperationsProjectionError(
            "OPERATIONS_PROJECTION_TIME_INVALID"
        ) from error
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or parsed.microsecond % 1000
    ):
        raise OperationsProjectionError("OPERATIONS_PROJECTION_TIME_INVALID")
    canonical = (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    if value != canonical:
        raise OperationsProjectionError("OPERATIONS_PROJECTION_TIME_INVALID")
    return parsed.astimezone(timezone.utc)


def _nonnegative_integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= _MAX_SAFE_INTEGER


def _enum(value: object, allowed) -> bool:
    return isinstance(value, str) and value in allowed


def _validate_provenance(
    value: object,
    expected_kind: str,
    now: datetime,
    *,
    release_identity: bool = False,
) -> str:
    if (
        type(value) is not SourceProvenance
        or value.source_kind != expected_kind
        or not isinstance(value.source_sha256, str)
        or _SHA256.fullmatch(value.source_sha256) is None
    ):
        raise OperationsProjectionError("OPERATIONS_PROJECTION_SOURCE_INVALID")
    observed_at = _utc(value.observed_at)
    age = now - observed_at
    if age < -_MAX_FUTURE_SKEW:
        raise OperationsProjectionError("OPERATIONS_PROJECTION_FUTURE_SOURCE")
    if release_identity:
        return "IDENTITY_VERIFIED"
    return "STALE" if age > _FRESH_WINDOW else "FRESH"


def _validate_release(value: ReleaseOperationsSource, now: datetime) -> str:
    if (
        not isinstance(value.package_version, str)
        or _VERSION.fullmatch(value.package_version) is None
        or not isinstance(value.main_commit, str)
        or _GIT_COMMIT.fullmatch(value.main_commit) is None
        or not isinstance(value.tag_commit, str)
        or _GIT_COMMIT.fullmatch(value.tag_commit) is None
        or value.main_commit != value.tag_commit
        or value.release_tag != "v" + value.package_version
        or value.identity_status != "VERIFIED"
    ):
        raise OperationsProjectionError(
            "OPERATIONS_PROJECTION_RELEASE_IDENTITY_MISMATCH"
        )
    return _validate_provenance(
        value.provenance,
        "RELEASE_IDENTITY",
        now,
        release_identity=True,
    )


def _validate_next_slot(value: object) -> None:
    if value is not None:
        _utc(value)


def _validate_challenger(
    value: ChallengerOperationsSource, now: datetime
) -> str:
    counts = (
        value.verified_slot_count,
        value.completed_episode_count,
        value.incident_count,
    )
    if (
        not _enum(value.phase, _CHALLENGER_PHASES)
        or not _enum(value.service_health, _SERVICE_HEALTH)
        or not _enum(value.evidence_health, _EVIDENCE_HEALTH)
        or not _enum(value.gate_status, _CHALLENGER_GATES)
        or any(not _nonnegative_integer(item) for item in counts)
        or type(value.active_episode_present) is not bool
    ):
        raise OperationsProjectionError("OPERATIONS_PROJECTION_SOURCE_INVALID")
    _validate_next_slot(value.next_required_slot)
    if value.phase in {
        "LEGACY_FAILED_REPLACEMENT_NOT_STARTED",
        "REPLACEMENT_NOT_STARTED",
    }:
        if (
            value.verified_slot_count != 0
            or value.completed_episode_count != 0
            or value.active_episode_present
            or value.next_required_slot is not None
            or value.gate_status != "NOT_AVAILABLE"
        ):
            raise OperationsProjectionError(
                "OPERATIONS_PROJECTION_SOURCE_INVALID"
            )
    elif value.phase == "COLLECTING":
        if value.gate_status != "WITHHELD_PRE_TAIL":
            raise OperationsProjectionError(
                "OPERATIONS_PROJECTION_SOURCE_INVALID"
            )
    elif (
        value.gate_status not in _CHALLENGER_TERMINAL_GATES
        or value.active_episode_present
        or value.next_required_slot is not None
    ):
        raise OperationsProjectionError("OPERATIONS_PROJECTION_SOURCE_INVALID")
    return _validate_provenance(
        value.provenance, "CHALLENGER_OPERATIONS", now
    )


def _validate_system_paper(
    value: SystemPaperOperationsSource, now: datetime
) -> str:
    counts = (
        value.elapsed_days,
        value.verified_slot_count,
        value.submitted_order_count,
        value.filled_order_count,
        value.partially_filled_order_count,
        value.cancelled_order_count,
        value.rejected_order_count,
        value.timeout_unknown_order_count,
        value.incident_count,
    )
    if (
        not _enum(value.phase, _SYSTEM_PAPER_PHASES)
        or not _enum(value.service_health, _SERVICE_HEALTH)
        or not _enum(value.evidence_health, _EVIDENCE_HEALTH)
        or not _enum(value.reconciliation_status, _RECONCILIATION)
        or not _enum(value.risk_state, _RISK_STATES)
        or not _enum(value.gate_status, _SYSTEM_PAPER_GATES)
        or any(not _nonnegative_integer(item) for item in counts)
    ):
        raise OperationsProjectionError("OPERATIONS_PROJECTION_SOURCE_INVALID")
    _validate_next_slot(value.next_required_slot)
    if value.phase == "NOT_INSTALLED":
        if (
            any(item != 0 for item in counts)
            or value.next_required_slot is not None
            or value.reconciliation_status != "NOT_AVAILABLE"
            or value.risk_state != "NOT_AVAILABLE"
            or value.gate_status != "NOT_EVALUATED"
        ):
            raise OperationsProjectionError(
                "OPERATIONS_PROJECTION_SOURCE_INVALID"
            )
    elif value.phase == "INSTALLED_NOT_STARTED":
        if (
            value.elapsed_days != 0
            or value.verified_slot_count != 0
            or value.next_required_slot is not None
            or value.gate_status != "NOT_EVALUATED"
        ):
            raise OperationsProjectionError(
                "OPERATIONS_PROJECTION_SOURCE_INVALID"
            )
    elif value.phase == "COLLECTING":
        if value.gate_status != "NOT_EVALUATED":
            raise OperationsProjectionError(
                "OPERATIONS_PROJECTION_SOURCE_INVALID"
            )
    elif (
        value.gate_status not in _SYSTEM_PAPER_TERMINAL_GATES
        or value.next_required_slot is not None
    ):
        raise OperationsProjectionError("OPERATIONS_PROJECTION_SOURCE_INVALID")
    return _validate_provenance(
        value.provenance, "SYSTEM_PAPER_OPERATIONS", now
    )


def _provenance(value: SourceProvenance, freshness: str) -> Dict[str, Any]:
    return {
        "source_kind": value.source_kind,
        "source_sha256": value.source_sha256,
        "observed_at": value.observed_at,
        "freshness": freshness,
    }


def _projection_status(
    challenger: ChallengerOperationsSource,
    challenger_freshness: str,
    system_paper: SystemPaperOperationsSource,
    paper_freshness: str,
) -> str:
    if (
        "FAILED_CLOSED"
        in {
            challenger.service_health,
            challenger.evidence_health,
            system_paper.service_health,
            system_paper.evidence_health,
            system_paper.reconciliation_status,
        }
    ):
        return "FAILED_CLOSED"
    if (
        "STALE" in {challenger_freshness, paper_freshness}
        or "DEGRADED"
        in {challenger.service_health, system_paper.service_health}
        or challenger.evidence_health in {"STALE", "INCIDENT_DETECTED"}
        or system_paper.evidence_health in {"STALE", "INCIDENT_DETECTED"}
        or challenger.incident_count > 0
        or system_paper.incident_count > 0
        or system_paper.risk_state in {"HALT", "HARD_BOUNDARY"}
    ):
        return "DEGRADED"
    return "HEALTHY"


def _projection_hash(value: Mapping[str, Any]) -> str:
    return business_hash(
        {"purpose": "TAIL_BLIND_OPERATIONS_PROJECTION_V1", **value}
    )


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def build_operations_projection(
    now: str,
    sources: OperationsProjectionSources,
) -> Mapping[str, Any]:
    """Build one allowlisted projection from exactly three injected sources."""

    if type(sources) is not OperationsProjectionSources:
        raise OperationsProjectionError("OPERATIONS_PROJECTION_SOURCES_INVALID")
    projected_at = _utc(now)
    release = _load_source(sources.release_loader, ReleaseOperationsSource)
    challenger = _load_source(
        sources.challenger_loader, ChallengerOperationsSource
    )
    system_paper = _load_source(
        sources.system_paper_loader, SystemPaperOperationsSource
    )
    release_freshness = _validate_release(release, projected_at)
    challenger_freshness = _validate_challenger(challenger, projected_at)
    paper_freshness = _validate_system_paper(system_paper, projected_at)
    status = _projection_status(
        challenger,
        challenger_freshness,
        system_paper,
        paper_freshness,
    )
    projection: Dict[str, Any] = {
        "$schema": "./operations-projection-v1.schema.json",
        "schema_version": "1.0.0",
        "projected_at": now,
        "status": status,
        "release": {
            "package_version": release.package_version,
            "main_commit": release.main_commit,
            "release_tag": release.release_tag,
            "tag_commit": release.tag_commit,
            "identity_status": release.identity_status,
            "provenance": _provenance(
                release.provenance, release_freshness
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
            "provenance": _provenance(
                challenger.provenance, challenger_freshness
            ),
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
            "provenance": _provenance(
                system_paper.provenance, paper_freshness
            ),
        },
    }
    projection["projection_hash"] = _projection_hash(projection)
    return projection


def _strict_json_bytes(body: bytes) -> Mapping[str, Any]:
    if (
        not isinstance(body, bytes)
        or not body
        or len(body) > _MAX_PROJECTION_BYTES
    ):
        raise OperationsProjectionError("OPERATIONS_PROJECTION_BYTES_INVALID")

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise OperationsProjectionError(
                    "OPERATIONS_PROJECTION_BYTES_INVALID"
                )
            value[key] = item
        return value

    def reject_number(_value):
        raise OperationsProjectionError(
            "OPERATIONS_PROJECTION_BYTES_INVALID"
        )

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
        if (
            not isinstance(value, Mapping)
            or canonical_json(value).encode("utf-8") != body
        ):
            raise OperationsProjectionError(
                "OPERATIONS_PROJECTION_BYTES_INVALID"
            )
    except OperationsProjectionError:
        raise
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise OperationsProjectionError(
            "OPERATIONS_PROJECTION_BYTES_INVALID"
        ) from error
    return value


def _source_from_projection(value: Mapping[str, Any]):
    release = value["release"]
    challenger = value["challenger"]
    system_paper = value["system_paper"]

    def source_provenance(section):
        source = section["provenance"]
        return SourceProvenance(
            source_kind=source["source_kind"],
            source_sha256=source["source_sha256"],
            observed_at=source["observed_at"],
        )

    return (
        ReleaseOperationsSource(
            package_version=release["package_version"],
            main_commit=release["main_commit"],
            release_tag=release["release_tag"],
            tag_commit=release["tag_commit"],
            identity_status=release["identity_status"],
            provenance=source_provenance(release),
        ),
        ChallengerOperationsSource(
            phase=challenger["phase"],
            service_health=challenger["service_health"],
            evidence_health=challenger["evidence_health"],
            verified_slot_count=challenger["verified_slot_count"],
            completed_episode_count=challenger["completed_episode_count"],
            active_episode_present=challenger["active_episode_present"],
            next_required_slot=challenger["next_required_slot"],
            gate_status=challenger["gate_status"],
            incident_count=challenger["incident_count"],
            provenance=source_provenance(challenger),
        ),
        SystemPaperOperationsSource(
            phase=system_paper["phase"],
            service_health=system_paper["service_health"],
            evidence_health=system_paper["evidence_health"],
            elapsed_days=system_paper["elapsed_days"],
            verified_slot_count=system_paper["verified_slot_count"],
            next_required_slot=system_paper["next_required_slot"],
            submitted_order_count=system_paper["submitted_order_count"],
            filled_order_count=system_paper["filled_order_count"],
            partially_filled_order_count=system_paper[
                "partially_filled_order_count"
            ],
            cancelled_order_count=system_paper["cancelled_order_count"],
            rejected_order_count=system_paper["rejected_order_count"],
            timeout_unknown_order_count=system_paper[
                "timeout_unknown_order_count"
            ],
            reconciliation_status=system_paper["reconciliation_status"],
            risk_state=system_paper["risk_state"],
            gate_status=system_paper["gate_status"],
            incident_count=system_paper["incident_count"],
            provenance=source_provenance(system_paper),
        ),
    )


def load_operations_projection_bytes(body: bytes) -> Mapping[str, Any]:
    """Replay one exact canonical projection without operational I/O."""

    value = _strict_json_bytes(body)
    try:
        errors = tuple(_validator().iter_errors(value))
    except Exception as error:
        raise OperationsProjectionError(
            "OPERATIONS_PROJECTION_SCHEMA_INVALID"
        ) from error
    if errors:
        raise OperationsProjectionError("OPERATIONS_PROJECTION_SCHEMA_INVALID")

    without_hash = dict(value)
    claimed_hash = without_hash.pop("projection_hash")
    if _projection_hash(without_hash) != claimed_hash:
        raise OperationsProjectionError("OPERATIONS_PROJECTION_HASH_MISMATCH")

    try:
        release, challenger, system_paper = _source_from_projection(value)
        expected = build_operations_projection(
            value["projected_at"],
            OperationsProjectionSources(
                release_loader=lambda: release,
                challenger_loader=lambda: challenger,
                system_paper_loader=lambda: system_paper,
            ),
        )
    except OperationsProjectionError as error:
        raise OperationsProjectionError(
            "OPERATIONS_PROJECTION_SCHEMA_INVALID"
        ) from error
    if expected != value:
        raise OperationsProjectionError("OPERATIONS_PROJECTION_SCHEMA_INVALID")
    return dict(value)
