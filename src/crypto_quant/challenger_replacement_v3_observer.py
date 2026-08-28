"""Fixed-path, read-only observation boundary for replacement v3."""

import os
import stat
import hashlib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from .canonical import utc_datetime
from .challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)
from .challenger_replacement_economic_evaluation import (
    ChallengerReplacementEconomicEvaluationError,
    build_economic_evaluation_facts_from_state,
    build_economic_progress_facts_from_state,
    evaluate_challenger_replacement_economic_result,
    observe_challenger_replacement_economic_progress,
)
from .challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from .challenger_replacement_events import (
    ChallengerReplacementEventRootIdentity,
    open_challenger_replacement_event_root,
)
from .challenger_replacement_install_trust import (
    _close_descriptor, _open_relative_directory, _read_published_exact,
)
from .challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityState,
)
from .challenger_replacement_plan import _strict_json_bytes
from .challenger_replacement_plan_v3 import build_challenger_replacement_plan_v3
from .challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from .challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from .challenger_replacement_v3_deployment import (
    _PREDECESSOR, load_challenger_replacement_v3_deployment_bytes,
)
from .challenger_replacement_v3_start import (
    load_challenger_replacement_v3_start_receipt_bytes,
)


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
_DEPLOYMENT = (
    "deployment/snapshot/artifacts/challenger-replacement/"
    "challenger-replacement-v3-deployment-v0.76.0.json"
)
_FAULT = (
    "deployment/snapshot/artifacts/challenger-replacement/"
    "challenger-replacement-fault-matrix-v0.76.0.json"
)
_START = "evidence/start-receipts/challenger-replacement-v3-start-receipt-v1.json"


@dataclass(frozen=True)
class ChallengerReplacementV3Observation:
    deployment: Mapping[str, Any]
    start_receipt_or_null: Optional[Mapping[str, Any]]
    event_projection: Mapping[str, Any]
    operational_qualification: Mapping[str, Any]
    economic_progress: Mapping[str, Any]
    evidence_health: str


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
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_fixed(root, relative):
    parts = relative.split("/")
    current = os.dup(root)
    try:
        for part in parts[:-1]:
            following = _open_relative_directory(current, part, create=False)
            _close_descriptor(current)
            current = following
        found = _read_published_exact(current, parts[-1])
        return None if found is None else found[0]
    finally:
        _close_descriptor(current)


def _load_deployment(root):
    data = _read_fixed(root, _DEPLOYMENT)
    if data is None:
        raise OSError("fixed deployment absent")
    header = _strict_json_bytes(data)
    plan = build_challenger_replacement_plan_v3()
    economic = build_challenger_replacement_economic_plan()
    accelerated = build_challenger_replacement_accelerated_canary_plan()
    predecessor = build_challenger_replacement_simulation_contract(plan=plan)
    public = build_challenger_replacement_public_simulation_contract(
        plan=plan, economic_plan=economic, predecessor_contract=predecessor,
    )
    deployment = load_challenger_replacement_v3_deployment_bytes(
        data, predecessor_release=_PREDECESSOR, plan=plan,
        economic_plan=economic, accelerated_plan=accelerated,
        predecessor_contract=predecessor, public_contract=public,
        build_identity=header["candidate_build"],
        strategy_inventory=header["executable_core_identity"],
    )
    for path, digest in deployment["executable_core_identity"].items():
        body = _read_fixed(root, "deployment/snapshot/" + path)
        if body is None or hashlib.sha256(body).hexdigest() != digest:
            raise OSError("installed executable core mismatch")
    return deployment


@contextmanager
def _open_state(deployment):
    path = deployment["paths"]["event_root"]
    entry = os.lstat(path)
    identity = ChallengerReplacementEventRootIdentity(
        path, entry.st_dev, entry.st_ino, entry.st_uid, "0700"
    )
    with open_challenger_replacement_event_root(identity) as event_root:
        yield identity, ChallengerReplacementOpportunityState(
            event_root=event_root, plan=build_challenger_replacement_plan_v3(),
            build_identity=deployment["candidate_build"],
        )


def _observed_at():
    return utc_datetime(datetime.now(timezone.utc))


@contextmanager
def _open_sources(root):
    deployment = _load_deployment(root)
    with _open_state(deployment) as (identity, state):
        projection = state._replay()
        data = _read_fixed(root, _START)
        install_binding = None
        try:
            start_header = {} if data is None else _strict_json_bytes(data)
        except Exception:
            start_header = {}
        if "install_receipt_binding" in start_header:
            from .challenger_replacement_v3_activation_install import (
                _load_fixed_successful_install_receipt,
            )
            inputs, installed, installed_bytes = (
                _load_fixed_successful_install_receipt()
            )
            if (
                inputs["contract"]["deployment"]["deployment_id"]
                != deployment["deployment_id"]
                or inputs["contract"]["deployment"]["deployment_hash"]
                != deployment["deployment_hash"]
            ):
                raise OSError("installed deployment mismatch")
            install_binding = {
                "receipt_id": installed["receipt_id"],
                "receipt_hash": installed["receipt_hash"],
                "file_sha256": hashlib.sha256(installed_bytes).hexdigest(),
            }
        receipt = None if data is None else (
            load_challenger_replacement_v3_start_receipt_bytes(
                data, deployment=deployment, event_projection=projection,
                event_root_identity=identity,
                install_receipt_binding=install_binding,
            )
        )
        yield deployment, state, projection, receipt


def _load_installed_observation(root):
    from .challenger_replacement_fault_matrix import (
        load_challenger_replacement_fault_matrix_bytes,
    )
    from .challenger_replacement_operational_qualification import (
        build_operational_qualification_facts_from_state,
        evaluate_challenger_replacement_operational_qualification,
    )
    with _open_sources(root) as (deployment, state, _projection, receipt):
        event_projection = state.replay()
        if receipt is None:
            empty = _sentinel("HEALTHY")
            return ChallengerReplacementV3Observation(
                deployment, None, event_projection,
                empty.operational_qualification, empty.economic_progress,
                "HEALTHY",
            )
        fault_data = _read_fixed(root, _FAULT)
        fault_header = _strict_json_bytes(fault_data)
        fault = load_challenger_replacement_fault_matrix_bytes(
            fault_data, build_identity=deployment["candidate_build"],
            runtime_core_identity=fault_header["runtime_core_identity"],
        )
        observed_at = _observed_at()
        operational = evaluate_challenger_replacement_operational_qualification(
            build_operational_qualification_facts_from_state(
                state=state, start_receipt=receipt, observed_at=observed_at,
            ), accelerated_plan=build_challenger_replacement_accelerated_canary_plan(),
            fault_receipt=fault,
        )
        progress = observe_challenger_replacement_economic_progress(
            build_economic_progress_facts_from_state(
                state=state, start_receipt=receipt, observed_at=observed_at,
            ), economic_plan=build_challenger_replacement_economic_plan(),
        )
        health = "FAILED_CLOSED" if operational["status"] == "BLOCK_FAILED" else (
            "DEGRADED" if operational["status"] == "INTERRUPTED_RECOVERABLE"
            else "HEALTHY"
        )
        return ChallengerReplacementV3Observation(
            deployment, receipt, event_projection, operational, progress, health
        )


def _evaluate_fixed_economic_result():
    root = _runtime_entry()
    if root is None:
        raise OSError("fixed runtime root absent")
    try:
        with _open_sources(root) as (deployment, state, _projection, receipt):
            if receipt is None:
                raise OSError("fixed start receipt absent")
            observed_at = _observed_at()
            start = datetime.fromisoformat(
                receipt["economic_start"]["scheduled_for"].replace("Z", "+00:00")
            )
            if datetime.fromisoformat(observed_at.replace("Z", "+00:00")) < (
                start + timedelta(days=90)
            ):
                raise ChallengerReplacementEconomicEvaluationError(
                    "ECONOMIC_TAIL_NOT_REACHED"
                )
            facts = build_economic_evaluation_facts_from_state(
                    state=state, start_receipt=receipt,
                    observed_at=observed_at, tail_mark_or_null=None,
                )
            return evaluate_challenger_replacement_economic_result(
                facts, economic_plan=build_challenger_replacement_economic_plan(),
                build_identity=deployment["candidate_build"],
            )
    finally:
        os.close(root)


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


def observe_challenger_replacement_v3():
    """Observe fixed roots without accepting paths or mutating evidence."""
    root = None
    try:
        root = _runtime_entry()
        if root is None:
            return _sentinel("NOT_INSTALLED")
        value = _load_installed_observation(root)
        valid = isinstance(value, ChallengerReplacementV3Observation) and (
            value.evidence_health in {"HEALTHY", "DEGRADED", "FAILED_CLOSED"}
            and value.operational_qualification["status"] in {
                "NOT_STARTED", "ACTIVE", "INTERRUPTED_RECOVERABLE",
                "BLOCK_FAILED", "QUALIFIED"}
            and value.economic_progress["status"] == "TAIL_BLIND"
            and not any(value.deployment.get("authority", {}).values()))
        result = value if valid else _sentinel("FAILED_CLOSED")
    except Exception:
        result = _sentinel("FAILED_CLOSED")
    if root is not None:
        try:
            os.close(root)
        except OSError:
            result = _sentinel("FAILED_CLOSED")
    return result
