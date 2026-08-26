"""Fixed-path, read-only observation boundary for replacement v3."""

import os
import stat
from dataclasses import dataclass
from typing import Any, Mapping, Optional


_RUNTIME_ROOT = (
    "/Users/chenm4/Library/Application Support/CryptoQuant/"
    "challenger-replacement-v1"
)
_AUTHORITY_KEYS = (
    "production_activation", "runtime_install_authorized",
    "replacement_start_authorized", "credentials_allowed",
    "account_requests_allowed", "broker_requests_allowed",
    "real_orders_allowed", "fund_movement_allowed",
)


@dataclass(frozen=True)
class ChallengerReplacementV3Observation:
    deployment: Mapping[str, Any]
    start_receipt_or_null: Optional[Mapping[str, Any]]
    event_projection: Mapping[str, Any]
    operational_qualification: Mapping[str, Any]
    economic_progress: Mapping[str, Any]
    evidence_health: str


@dataclass(frozen=True)
class _RuntimeRoot:
    fd: int


def _runtime_entry():
    required = tuple(getattr(os, name, 0) for name in
                     ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"))
    if not all(required):
        raise OSError("fixed runtime root unsupported")
    try:
        descriptor = os.open(
            _RUNTIME_ROOT, os.O_RDONLY | required[0] | required[1] | required[2]
        )
    except FileNotFoundError:
        return None
    try:
        entry = os.fstat(descriptor)
        attached = os.lstat(_RUNTIME_ROOT)
        if (
            (entry.st_dev, entry.st_ino) != (attached.st_dev, attached.st_ino)
            or not stat.S_ISDIR(entry.st_mode)
            or entry.st_uid != os.getuid()
            or stat.S_IMODE(entry.st_mode) != 0o700
            or entry.st_nlink < 1
        ):
            raise OSError("untrusted fixed runtime root")
        return _RuntimeRoot(descriptor)
    except BaseException:
        os.close(descriptor)
        raise


def _load_installed_observation(_root):
    raise OSError("installed v3 strict sources unavailable")


def _sentinel(health):
    return ChallengerReplacementV3Observation(
        deployment={
            "status": "V3_NOT_INSTALLED_NOT_ACTIVATED",
            "authority": {key: False for key in _AUTHORITY_KEYS},
        },
        start_receipt_or_null=None,
        event_projection={
            "events": (), "opportunities": {},
            **{name + "_opportunity_count": 0
               for name in ("terminal", "observed", "missed")},
            "latest_next_snapshot_or_null": None,
        },
        operational_qualification={
            "status": "NOT_STARTED", "eligible_continuous_seconds": 0,
            "final_segment_id_or_null": None, "reason_codes": [],
            "bindings": {},
        },
        economic_progress={
            "status": "TAIL_BLIND", "due_opportunity_count": 0,
            **{name + "_opportunity_count": 0
               for name in ("terminal", "observed", "missed")},
            "elapsed_complete_days": 0,
            "next_required_opportunity": None,
            "evidence_health": health,
        },
        evidence_health=health,
    )


def _valid(value):
    try:
        return (
            isinstance(value, ChallengerReplacementV3Observation)
            and value.evidence_health in {"HEALTHY", "DEGRADED", "FAILED_CLOSED"}
            and value.operational_qualification["status"] in {
                "NOT_STARTED", "ACTIVE", "INTERRUPTED_RECOVERABLE",
                "BLOCK_FAILED", "QUALIFIED",
            }
            and value.economic_progress["status"] == "TAIL_BLIND"
            and not any(value.deployment.get("authority", {}).values())
        )
    except (AttributeError, KeyError, TypeError):
        return False


def observe_challenger_replacement_v3():
    """Observe fixed roots without accepting paths or mutating evidence."""
    root = None
    try:
        root = _runtime_entry()
        if root is None:
            return _sentinel("NOT_INSTALLED")
        value = _load_installed_observation(root)
        result = value if _valid(value) else _sentinel("FAILED_CLOSED")
    except Exception:
        result = _sentinel("FAILED_CLOSED")
    if root is not None:
        try:
            os.close(root.fd)
        except OSError:
            result = _sentinel("FAILED_CLOSED")
    return result
