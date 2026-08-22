"""Fixed installed adapter for one natural replacement Challenger invocation."""

from datetime import timedelta
from pathlib import Path

from .canonical import canonical_json
from .challenger_replacement_events import (
    ChallengerReplacementEventError,
    ChallengerReplacementEventRootIdentity,
    open_challenger_replacement_event_root,
)
from .challenger_replacement_install import (
    ReplacementInstallError,
    _load_fixed_successful_install_receipt,
)
from .challenger_replacement_install_trust import (
    ReplacementInstallTrustError,
    _close_descriptor,
    _open_directory,
    _read_snapshot_file,
)
from .challenger_replacement_live_input import (
    _utc_millis,
    _wall_now,
    acquire_challenger_replacement_live_capture,
)
from .challenger_replacement_runtime import (
    ChallengerReplacementRuntimeState,
    resume_challenger_replacement_slot,
    run_challenger_replacement_cohort_slot,
)
from .challenger_replacement_plan import _strict_json_bytes
from .challenger_replacement_plan_v2 import challenger_replacement_plan_v2_reasons


class ReplacementInstalledRuntimeError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _load_snapshot_plan_and_strategy(contract):
    root_fd = -1
    primary = None
    try:
        root_fd, opened = _open_directory(
            Path(contract["snapshot"]["root"]), exact_mode=0o700
        )
        if (opened.st_dev, opened.st_ino) != (
            contract["snapshot"]["root_device"],
            contract["snapshot"]["root_inode"],
        ):
            raise ValueError("snapshot identity")
        for name, digest in contract["strategy_core"]["file_hashes"].items():
            _read_snapshot_file(root_fd, name, digest)
        plan_body = _read_snapshot_file(
            root_fd, contract["plan"]["path"],
            contract["plan"]["file_sha256"],
        )
        plan = dict(_strict_json_bytes(plan_body))
        if (
            plan_body not in (
                canonical_json(plan).encode(), canonical_json(plan).encode() + b"\n"
            )
            or plan.get("plan_id") != contract["plan"]["plan_id"]
            or plan.get("plan_hash") != contract["plan"]["plan_hash"]
            or challenger_replacement_plan_v2_reasons(plan)
        ):
            raise ValueError("plan")
        return plan
    except BaseException as error:
        primary = error
        raise
    finally:
        if root_fd >= 0:
            _close_descriptor(root_fd, primary)


def _load_fixed_runtime_sources():
    try:
        inputs, receipt, _ = _load_fixed_successful_install_receipt()
        contract = inputs["contract"]
        plan = _load_snapshot_plan_and_strategy(contract)
        event = contract["event_root"]
        root = open_challenger_replacement_event_root(
            ChallengerReplacementEventRootIdentity(
                event["path"], event["device"], event["inode"],
                event["owner_uid"], "0700",
            )
        )
        try:
            build = {
                key: contract["strategy_core"][key]
                for key in (
                    "release_tag", "peeled_commit", "package_version",
                    "manifest_version", "build_input_tree_hash",
                    "manifest_hash", "manifest_file_sha256",
                )
            }
            state = ChallengerReplacementRuntimeState(
                event_root=root, plan=plan, build_identity=build
            )
        except BaseException:
            root.close()
            raise
        return {
            "state": state, "event_root": root,
            "worker_id": contract["runtime"]["worker_id"],
            "first_eligible_scheduled_for": receipt[
                "first_eligible_scheduled_for"
            ],
        }
    except ReplacementInstalledRuntimeError:
        raise
    except ReplacementInstallError as error:
        raise ReplacementInstalledRuntimeError(
            "CHALLENGER_REPLACEMENT_INSTALL_RECEIPT_REQUIRED"
        ) from error
    except (ChallengerReplacementEventError, ReplacementInstallTrustError,
            KeyError, TypeError, ValueError) as error:
        raise ReplacementInstalledRuntimeError(
            "CHALLENGER_REPLACEMENT_RUNTIME_CONTRACT_INVALID"
        ) from error


def run_fixed_replacement_installed_invocation():
    sources = _load_fixed_runtime_sources()
    try:
        if (
            not isinstance(sources, dict)
            or set(sources) != {
                "state", "event_root", "worker_id",
                "first_eligible_scheduled_for",
            }
            or not isinstance(sources["state"], ChallengerReplacementRuntimeState)
            or sources["state"].event_root is not sources["event_root"]
            or not isinstance(sources["worker_id"], str)
            or not sources["worker_id"]
        ):
            raise ReplacementInstalledRuntimeError(
                "CHALLENGER_REPLACEMENT_RUNTIME_CONTRACT_INVALID"
            )
        state = sources["state"]
        projection = state.replay()
        if not projection["events"]:
            try:
                eligible = _utc_millis(sources["first_eligible_scheduled_for"])
            except (TypeError, ValueError) as error:
                raise ReplacementInstalledRuntimeError(
                    "CHALLENGER_REPLACEMENT_RUNTIME_CONTRACT_INVALID"
                ) from error
            now = _wall_now()
            if not eligible + timedelta(minutes=2) <= now <= eligible + timedelta(minutes=10):
                raise ReplacementInstalledRuntimeError(
                    "CHALLENGER_REPLACEMENT_RUNTIME_WINDOW_INVALID"
                )
        next_slot = projection["next_required_slot"]
        if projection["active_slot_id"] is not None or (
            projection["events"] and (
                next_slot is None
                or _wall_now()
                < _utc_millis(next_slot["scheduled_for"]) + timedelta(minutes=2)
            )
        ):
            result = resume_challenger_replacement_slot(
                state=state, worker_id=sources["worker_id"]
            )
        else:
            capture = acquire_challenger_replacement_live_capture(state=state)
            result = run_challenger_replacement_cohort_slot(
                state=state, live_capture=capture,
                worker_id=sources["worker_id"],
            )
        projection = state.replay()
        slot = result["source_bundle"]["slot"]
        return {
            "event_count": len(projection["events"]),
            "next_required_slot": projection["next_required_slot"],
            "reason_code": "CHALLENGER_REPLACEMENT_SLOT_SUCCEEDED_VERIFIED",
            "scheduled_for": slot["scheduled_for"],
            "slot_id": slot["slot_id"],
            "status": "CHALLENGER_REPLACEMENT_LIVE_RUNTIME_SUCCEEDED",
            "terminal_stage": result["stage"],
        }
    finally:
        if isinstance(sources, dict) and "event_root" in sources:
            sources["event_root"].close()
