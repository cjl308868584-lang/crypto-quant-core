"""Read-only observation of the first natural replacement Challenger slot."""

import json
import hashlib
import os
import stat
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id, utc_datetime
from .challenger_replacement_live_input import (
    _utc_millis,
    acquire_challenger_replacement_live_capture,
)
from .challenger_replacement_preflight import _run
from .challenger_replacement_install_trust import (
    ReplacementInstallTrustError,
    _close_descriptor,
    _fsync_retry,
    _open_directory,
    _publish_contract_exact,
    _read_exact,
    _read_published_exact,
    _require_open_flag,
    _same_file_identity,
    _validate_directory_attachment,
)
from .challenger_replacement_install import (
    ReplacementInstallError,
    _adapter_binding,
    _load_fixed_successful_install_receipt,
)
from .challenger_replacement_installed_runtime import (
    _load_snapshot_plan_and_strategy,
)
from .challenger_replacement_events import (
    ChallengerReplacementEventError,
    ChallengerReplacementEventRootIdentity,
    open_challenger_replacement_event_root,
)
from .challenger_replacement_runtime import (
    ChallengerReplacementRuntimeError,
    ChallengerReplacementRuntimeState,
)
from .challenger_replacement_plan import _strict_json_bytes
from .evidence import artifact_self_hash
from .system_paper_launchctl import (
    SystemPaperLaunchctlParseError,
    parse_challenger_replacement_launchctl_print,
)


_REPOSITORY = Path(__file__).resolve().parents[2]
_MAX_LOG_BYTES = 4 * 1024 * 1024


class ChallengerReplacementStartError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _now():
    return datetime.now(timezone.utc)


def _command(argv):
    return _run(argv, _REPOSITORY)


def _start_schema():
    name = "schemas/challenger-replacement-start-receipt-v1.schema.json"
    return json.loads(resources.files("crypto_quant").joinpath(name).read_text())


class _RetainedPath:
    def __init__(self, path, parent_fd, parent_opened, descriptor, opened, body):
        self.path = path
        self.parent_fd = parent_fd
        self.parent_opened = parent_opened
        self.descriptor = descriptor
        self.opened = opened
        self.body = body

    def validate(self):
        try:
            if self.opened is None:
                try:
                    os.stat(self.path.name, dir_fd=self.parent_fd,
                            follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise ChallengerReplacementStartError(
                        "CHALLENGER_REPLACEMENT_FIRST_SLOT_PATH_IDENTITY_CHANGED"
                    )
            else:
                current = os.fstat(self.descriptor)
                os.lseek(self.descriptor, 0, os.SEEK_SET)
                current_body = _read_exact(self.descriptor, current.st_size)
                after_read = os.fstat(self.descriptor)
                attached = os.stat(
                    self.path.name, dir_fd=self.parent_fd,
                    follow_symlinks=False,
                )
                if (
                    not _same_file_identity(self.opened, current)
                    or not _same_file_identity(current, after_read)
                    or not _same_file_identity(after_read, attached)
                    or current_body != self.body
                ):
                    raise ChallengerReplacementStartError(
                        "CHALLENGER_REPLACEMENT_FIRST_SLOT_PATH_IDENTITY_CHANGED"
                    )
            _validate_directory_attachment(
                self.path.parent, self.parent_fd, self.parent_opened,
                "CHALLENGER_REPLACEMENT_FIRST_SLOT_PATH_IDENTITY_CHANGED",
            )
        except ReplacementInstallTrustError as error:
            raise ChallengerReplacementStartError(
                "CHALLENGER_REPLACEMENT_FIRST_SLOT_PATH_IDENTITY_CHANGED"
            ) from error
        except OSError as error:
            raise ChallengerReplacementStartError(
                "CHALLENGER_REPLACEMENT_FIRST_SLOT_PATH_IDENTITY_CHANGED"
            ) from error

    def close(self):
        primary = None
        try:
            if self.descriptor >= 0:
                _close_descriptor(self.descriptor)
        except BaseException as error:
            primary = error
            raise
        finally:
            _close_descriptor(self.parent_fd, primary)


def _open_retained_path(path, *, allow_absent, allow_empty, parent_mode=0o700):
    path = Path(path)
    parent_fd = -1
    descriptor = -1
    primary = None
    try:
        parent_fd, parent_opened = _open_directory(
            path.parent, exact_mode=parent_mode
        )
        try:
            descriptor = os.open(
                path.name,
                os.O_RDONLY | _require_open_flag("O_NOFOLLOW")
                | _require_open_flag("O_NONBLOCK"),
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            if not allow_absent:
                raise
            return _RetainedPath(
                path, parent_fd, parent_opened, -1, None, b""
            )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_size > _MAX_LOG_BYTES
            or (not allow_empty and opened.st_size == 0)
        ):
            raise ChallengerReplacementStartError(
                "CHALLENGER_REPLACEMENT_FIRST_SLOT_PATH_UNTRUSTED"
            )
        body = _read_exact(descriptor, opened.st_size) if opened.st_size else b""
        capability = _RetainedPath(
            path, parent_fd, parent_opened, descriptor, opened, body
        )
        capability.validate()
        return capability
    except BaseException as error:
        primary = error
        raise ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_FIRST_SLOT_PATH_UNTRUSTED"
        ) from error
    finally:
        if primary is not None:
            if descriptor >= 0:
                _close_descriptor(descriptor, primary)
            if parent_fd >= 0:
                _close_descriptor(parent_fd, primary)


def _load_fixed_observation_sources():
    inputs, receipt, receipt_bytes = _load_fixed_successful_install_receipt()
    contract = inputs["contract"]
    plan = _load_snapshot_plan_and_strategy(contract)
    event = contract["event_root"]
    root = open_challenger_replacement_event_root(
        ChallengerReplacementEventRootIdentity(
            event["path"], event["device"], event["inode"],
            event["owner_uid"], "0700",
        )
    )
    retained = []
    try:
        build = {
            key: contract["strategy_core"][key]
            for key in (
                "release_tag", "peeled_commit", "package_version",
                "manifest_version", "build_input_tree_hash", "manifest_hash",
                "manifest_file_sha256",
            )
        }
        state = ChallengerReplacementRuntimeState(
            event_root=root, plan=plan, build_identity=build
        )
        stdout = _open_retained_path(
            contract["paths"]["stdout"], allow_absent=True, allow_empty=True
        )
        retained.append(stdout)
        stderr = _open_retained_path(
            contract["paths"]["stderr"], allow_absent=True, allow_empty=True
        )
        retained.append(stderr)
        plist = _open_retained_path(
            contract["paths"]["target_plist"], allow_absent=False,
            allow_empty=False, parent_mode=None,
        )
        retained.append(plist)
        entry = plist.opened
        record = receipt["plist"]
        if record != {
            "path": str(plist.path), "device": entry.st_dev,
            "inode": entry.st_ino, "owner_uid": entry.st_uid,
            "mode": stat.S_IMODE(entry.st_mode), "link_count": entry.st_nlink,
            "size_bytes": entry.st_size,
            "sha256": hashlib.sha256(plist.body).hexdigest(),
        }:
            raise ChallengerReplacementStartError(
                "CHALLENGER_REPLACEMENT_FIRST_SLOT_PLIST_CHANGED"
            )
        return {
            "contract": contract, "install_receipt": receipt,
            "install_inputs": inputs,
            "install_receipt_bytes": receipt_bytes, "plan": plan,
            "event_root": root, "state": state, "projection": state.replay(),
            "stdout": stdout.body, "stderr": stderr.body,
            "retained_paths": tuple(retained),
        }
    except BaseException as error:
        _close_observation_sources({
            "retained_paths": tuple(retained), "event_root": root,
        }, error)
        raise


def _close_observation_sources(sources, primary_error=None):
    failures = []
    for capability in reversed(sources.get("retained_paths", ())):
        try:
            capability.close()
        except BaseException as error:
            failures.append(error)
    if "event_root" in sources:
        try:
            sources["event_root"].close()
        except BaseException as error:
            failures.append(error)
    if not failures:
        return
    if primary_error is not None:
        try:
            primary_error.close_failures = tuple(
                repr(error) for error in failures
            )
        except BaseException:
            pass
        return
    raise ChallengerReplacementStartError(
        "CHALLENGER_REPLACEMENT_FIRST_SLOT_CLOSE_FAILED"
    ) from failures[0]


def _revalidate_sources(sources):
    inputs, receipt, receipt_bytes = _load_fixed_successful_install_receipt()
    if (
        inputs != sources["install_inputs"]
        or receipt != sources["install_receipt"]
        or receipt_bytes != sources["install_receipt_bytes"]
        or _load_snapshot_plan_and_strategy(inputs["contract"])
        != sources["plan"]
    ):
        raise ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_FIRST_SLOT_SOURCE_CHANGED"
        )


def _revalidate_retained_sources(sources):
    for capability in sources.get("retained_paths", ()):
        capability.validate()
    sources["event_root"].validate()
    if (
        "state" in sources
        and sources["state"].replay() != sources["projection"]
    ):
        raise ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_FIRST_SLOT_SOURCE_CHANGED"
        )
    sources["event_root"].validate()
    if "install_inputs" in sources:
        _revalidate_sources(sources)


def _launchctl_observation_valid(contract, result, expected_runs):
    if result[0] != 0 or result[2]:
        return False
    try:
        parse_challenger_replacement_launchctl_print(
            result[1], contract, expected_runs
        )
        return True
    except (KeyError, TypeError, SystemPaperLaunchctlParseError):
        return False


def _stdout_valid(data, projection, successful):
    try:
        if not data.endswith(b"\n") or data.count(b"\n") != 1:
            return False
        value = json.loads(data)
        slot = successful["source_bundle"]["slot"]
        return (
            isinstance(value, dict)
            and data == canonical_json(value).encode("utf-8") + b"\n"
            and value == {
                "event_count": len(projection["events"]),
                "next_required_slot": projection["next_required_slot"],
                "reason_code":
                "CHALLENGER_REPLACEMENT_SLOT_SUCCEEDED_VERIFIED",
                "scheduled_for": slot["scheduled_for"],
                "slot_id": slot["slot_id"],
                "status": "CHALLENGER_REPLACEMENT_LIVE_RUNTIME_SUCCEEDED",
                "terminal_stage": "SLOT_SUCCEEDED",
            }
        )
    except (TypeError, ValueError):
        return False


def _classify(sources, observed):
    projection = sources["projection"]
    eligible = _utc_millis(
        sources["install_receipt"]["first_eligible_scheduled_for"]
    )
    completed = projection["completed_slot_count"]
    failed = projection["failed_slot_count"]
    first_scheduled = None
    reasons = []
    if completed == 1:
        successful = [
            slot for slot in projection["slots"].values()
            if slot["stage"] == "SLOT_SUCCEEDED"
        ]
        if len(successful) == 1:
            first_scheduled = successful[0]["source_bundle"]["slot"][
                "scheduled_for"
            ]
    invalid_chain = (
        failed != 0
        or projection["active_slot_id"] is not None
        or projection["orphan_staging_count"] != 0
        or projection["orphan_staging_bytes"] != 0
        or len(projection["events"]) != completed * 3
    )
    if invalid_chain:
        status = "FAILED_CLOSED"
        reasons.append("FIRST_SLOT_EVENT_PROJECTION_INVALID")
    elif completed > 1 or observed >= eligible + timedelta(hours=4):
        status = "FIRST_SLOT_OBSERVATION_WINDOW_MISSED"
        reasons.append("FIRST_SLOT_OBSERVATION_WINDOW_MISSED")
    elif completed == 1:
        if (
            first_scheduled != sources["install_receipt"][
                "first_eligible_scheduled_for"
            ]
            or not _stdout_valid(sources["stdout"], projection, successful[0])
        ):
            status = "FAILED_CLOSED"
            reasons.append("FIRST_SLOT_EVIDENCE_INVALID")
        else:
            status = "FIRST_NATURAL_SLOT_VERIFIED"
    elif observed < eligible:
        status = "WAITING_BEFORE_FIRST_ELIGIBLE_SLOT"
    else:
        status = "WAITING_FOR_FIRST_NATURAL_SLOT"
    return status, first_scheduled, reasons


def _authority(launchctl_reads):
    return {
        "launchctl_read_count": launchctl_reads, "market_request_count": 0,
        "runtime_invocation_count": 0, "state_write_count": 0,
        "credential_count": 0, "broker_request_count": 0,
        "order_count": 0,
    }


def _terminal_evidence(projection):
    successful = [
        slot for slot in projection.get("slots", {}).values()
        if slot.get("stage") == "SLOT_SUCCEEDED"
    ]
    if len(successful) != 1:
        return {
            "terminal_event_hash": None,
            "source_bundle_sha256": None,
            "decision_sha256": None,
        }
    return {
        "terminal_event_hash": projection.get("last_event_hash"),
        "source_bundle_sha256": successful[0].get("source_bundle_sha256"),
        "decision_sha256": successful[0].get("decision_sha256"),
    }


def _failed_summary(observed, error, *, launchctl_reads, sources=None):
    projection = {} if sources is None else sources.get("projection", {})
    receipt = {} if sources is None else sources.get("install_receipt", {})
    return {
        "status": "FAILED_CLOSED", "observed_at": utc_datetime(observed),
        "first_eligible_scheduled_for": receipt.get(
            "first_eligible_scheduled_for"
        ),
        "first_scheduled_for": None,
        "event_count": len(projection.get("events", ())),
        "completed_slot_count": projection.get("completed_slot_count", 0),
        **_terminal_evidence(projection),
        "reason_codes": [getattr(
            error, "reason_code",
            "CHALLENGER_REPLACEMENT_FIRST_SLOT_EVIDENCE_INVALID",
        )],
        "authority": _authority(launchctl_reads),
    }


_EXPECTED_OBSERVATION_ERRORS = (
    ChallengerReplacementStartError,
    ChallengerReplacementEventError,
    ChallengerReplacementRuntimeError,
    ReplacementInstallError,
    ReplacementInstallTrustError,
    KeyError,
    TypeError,
    ValueError,
)


def observe_fixed_replacement_first_slot():
    observed = _now()
    body_error = None
    try:
        sources = _load_fixed_observation_sources()
    except _EXPECTED_OBSERVATION_ERRORS as error:
        return _failed_summary(
            observed, error, launchctl_reads=0
        )
    try:
        contract = sources["contract"]
        launch = _command((
            "/bin/launchctl", "print", contract["service"]["identity"],
        ))
        status, first_scheduled, reasons = _classify(sources, observed)
        if sources["stderr"] or not _launchctl_observation_valid(
            contract, launch, sources["projection"]["completed_slot_count"]
        ):
            status = "FAILED_CLOSED"
            reasons.append("FIRST_SLOT_PROCESS_EVIDENCE_INVALID")
        result = {
            "status": status,
            "observed_at": utc_datetime(observed),
            "first_eligible_scheduled_for": sources["install_receipt"][
                "first_eligible_scheduled_for"
            ],
            "first_scheduled_for": first_scheduled,
            "event_count": len(sources["projection"]["events"]),
            "completed_slot_count": sources["projection"][
                "completed_slot_count"
            ],
            **_terminal_evidence(sources["projection"]),
            "reason_codes": sorted(set(reasons)),
            "authority": _authority(1),
        }
        _revalidate_retained_sources(sources)
    except _EXPECTED_OBSERVATION_ERRORS as error:
        body_error = error
        result = _failed_summary(
            observed, error, launchctl_reads=1, sources=sources
        )
    except BaseException as error:
        _close_observation_sources(sources, error)
        raise
    try:
        _close_observation_sources(sources, body_error)
    except ChallengerReplacementStartError as error:
        return _failed_summary(
            observed, error, launchctl_reads=1, sources=sources
        )
    return result


def _source_binding(value, data, prefix):
    return {
        "id": value[prefix + "_id"], "hash": value[prefix + "_hash"],
        "file_sha256": hashlib.sha256(data).hexdigest(),
    }


def _observer_binding(observer):
    return {
        "summary_sha256": hashlib.sha256(
            canonical_json(observer).encode("utf-8")
        ).hexdigest(),
        "observed_at": observer["observed_at"],
        "first_eligible_scheduled_for": observer[
            "first_eligible_scheduled_for"
        ],
        "first_scheduled_for": observer["first_scheduled_for"],
        "event_count": observer["event_count"],
        "completed_slot_count": observer["completed_slot_count"],
        "terminal_event_hash": observer["terminal_event_hash"],
        "source_bundle_sha256": observer["source_bundle_sha256"],
        "decision_sha256": observer["decision_sha256"],
    }


def _observer_from_binding(binding):
    observer = {
        "status": "FIRST_NATURAL_SLOT_VERIFIED",
        "observed_at": binding["observed_at"],
        "first_eligible_scheduled_for": binding[
            "first_eligible_scheduled_for"
        ],
        "first_scheduled_for": binding["first_scheduled_for"],
        "event_count": binding["event_count"],
        "completed_slot_count": binding["completed_slot_count"],
        "terminal_event_hash": binding["terminal_event_hash"],
        "source_bundle_sha256": binding["source_bundle_sha256"],
        "decision_sha256": binding["decision_sha256"],
        "reason_codes": [],
        "authority": _authority(1),
    }
    if _observer_binding(observer) != binding:
        raise ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_START_RECEIPT_INVALID"
        )
    return observer


def _validate_retained_observer_sources(sources, observer):
    _revalidate_retained_sources(sources)
    status, first_scheduled, reasons = _classify(
        sources, _utc_millis(observer["observed_at"])
    )
    expected = {
        "status": status, "observed_at": observer["observed_at"],
        "first_eligible_scheduled_for": sources["install_receipt"][
            "first_eligible_scheduled_for"
        ],
        "first_scheduled_for": first_scheduled,
        "event_count": len(sources["projection"]["events"]),
        "completed_slot_count": sources["projection"][
            "completed_slot_count"
        ],
        **_terminal_evidence(sources["projection"]),
        "reason_codes": sorted(set(reasons)), "authority": _authority(1),
    }
    if sources.get("stderr") or expected != observer:
        raise ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_FIRST_SLOT_SOURCE_CHANGED"
        )


def _retain_verified_observer_sources(observer):
    sources = None
    try:
        sources = _load_fixed_observation_sources()
        _validate_retained_observer_sources(sources, observer)
        return sources
    except _EXPECTED_OBSERVATION_ERRORS as error:
        if sources is not None:
            _close_observation_sources(sources, error)
        raise ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_FIRST_SLOT_SOURCE_CHANGED"
        ) from error
    except BaseException as error:
        if sources is not None:
            _close_observation_sources(sources, error)
        raise


def _build_replacement_start_receipt(
    *, observer, contract, contract_bytes, install_receipt,
    install_receipt_bytes, published_at,
):
    first = _utc_millis(observer["first_scheduled_for"])
    observed = _utc_millis(observer["observed_at"])
    if (
        observer.get("status") != "FIRST_NATURAL_SLOT_VERIFIED"
        or observer.get("reason_codes")
        or observer.get("first_eligible_scheduled_for")
        != install_receipt.get("first_eligible_scheduled_for")
        or first != _utc_millis(
            install_receipt["first_eligible_scheduled_for"]
        )
        or published_at < observed
    ):
        raise ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_START_RECEIPT_INVALID"
        )
    receipt = {
        "$schema": "./challenger-replacement-start-receipt-v1.schema.json",
        "schema_version": "1.0.0",
        "receipt_id": "challenger_replacement_start_receipt_" + "0" * 64,
        "receipt_hash": "0" * 64,
        "published_at": utc_datetime(published_at),
        "contract_binding": _source_binding(
            contract, contract_bytes, "contract"
        ),
        "install_receipt_binding": _source_binding(
            install_receipt, install_receipt_bytes, "receipt"
        ),
        "observer_binding": _observer_binding(observer),
        "event_root_binding": dict(contract["event_root"]),
        "strategy_core_binding": dict(contract["strategy_core"]),
        "adapter_binding": _adapter_binding(contract),
        "first_scheduled_for": utc_datetime(first),
        "required_slot_count": 540,
        "last_required_scheduled_for": utc_datetime(
            first + timedelta(hours=4 * 539)
        ),
        "tail_end": utc_datetime(first + timedelta(hours=4 * 540)),
        "evaluation_not_before": utc_datetime(
            first + timedelta(hours=4 * 540, minutes=5)
        ),
        "cohort_status": "STARTED_COLLECTION_ONLY",
        "authority": {
            "github_request_count": 0, "market_request_count": 0,
            "launchctl_read_count": 1, "launchctl_mutation_count": 0,
            "runtime_invocation_count": 0, "state_write_count": 0,
            "receipt_write_count": 1, "credential_count": 0,
            "broker_request_count": 0, "order_count": 0,
        },
    }
    identity = {
        key: value for key, value in receipt.items()
        if key not in ("receipt_id", "receipt_hash")
    }
    receipt["receipt_id"] = stable_id(
        "challenger_replacement_start_receipt", identity
    )
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    if tuple(Draft202012Validator(_start_schema()).iter_errors(receipt)):
        raise ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_START_RECEIPT_INVALID"
        )
    return receipt


def load_replacement_start_receipt_bytes(
    data, *, install_receipt, install_receipt_bytes, contract,
    contract_bytes, observer,
):
    try:
        receipt = dict(_strict_json_bytes(data))
        if data != canonical_json(receipt).encode("utf-8"):
            raise ValueError("canonical")
        rebuilt = _build_replacement_start_receipt(
            observer=observer, contract=contract,
            contract_bytes=contract_bytes, install_receipt=install_receipt,
            install_receipt_bytes=install_receipt_bytes,
            published_at=_utc_millis(receipt["published_at"]),
        )
        if receipt != rebuilt:
            raise ValueError("semantic")
        return receipt
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ChallengerReplacementStartError):
            raise
        raise ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_START_RECEIPT_INVALID"
        ) from error


def _load_start_receipt_source_bytes(
    data, *, install_receipt, install_receipt_bytes, contract, contract_bytes,
):
    try:
        receipt = dict(_strict_json_bytes(data))
        observer = _observer_from_binding(receipt["observer_binding"])
        loaded = load_replacement_start_receipt_bytes(
            data, install_receipt=install_receipt,
            install_receipt_bytes=install_receipt_bytes,
            contract=contract, contract_bytes=contract_bytes,
            observer=observer,
        )
        return loaded, observer
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ChallengerReplacementStartError):
            raise
        raise ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_START_RECEIPT_INVALID"
        ) from error


def _load_existing_start_receipt(inputs, install_receipt, install_bytes):
    root = Path(inputs["contract"]["paths"]["start_receipt_root"])
    root_fd = -1
    primary = None
    try:
        root_fd, root_opened = _open_directory(root, exact_mode=0o700)
        names = sorted(os.listdir(root_fd))
        if not names:
            return None
        if len(names) != 1 or not names[0].endswith(".json"):
            raise ChallengerReplacementStartError(
                "CHALLENGER_REPLACEMENT_START_RECEIPT_PUBLICATION_FAILED"
            )
        loaded = _read_published_exact(root_fd, names[0])
        if loaded is None:
            raise ChallengerReplacementStartError(
                "CHALLENGER_REPLACEMENT_START_RECEIPT_PUBLICATION_FAILED"
            )
        receipt, observer = _load_start_receipt_source_bytes(
            loaded[0], install_receipt=install_receipt,
            install_receipt_bytes=install_bytes,
            contract=inputs["contract"],
            contract_bytes=inputs["contract_bytes"],
        )
        if names[0] != receipt["receipt_id"] + ".json":
            raise ChallengerReplacementStartError(
                "CHALLENGER_REPLACEMENT_START_RECEIPT_PUBLICATION_FAILED"
            )
        _fsync_retry(root_fd)
        _validate_directory_attachment(
            root, root_fd, root_opened,
            "CHALLENGER_REPLACEMENT_START_RECEIPT_PUBLICATION_FAILED",
        )
        return receipt, observer
    except ChallengerReplacementStartError as error:
        if error.reason_code == (
            "CHALLENGER_REPLACEMENT_START_RECEIPT_PUBLICATION_FAILED"
        ):
            primary = error
            raise
        primary = ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_START_RECEIPT_PUBLICATION_FAILED"
        )
        raise primary from error
    except (OSError, ReplacementInstallTrustError) as error:
        primary = ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_START_RECEIPT_PUBLICATION_FAILED"
        )
        raise primary from error
    except BaseException as error:
        primary = error
        raise
    finally:
        if root_fd >= 0:
            _close_descriptor(root_fd, primary)


def _load_start_install_sources():
    try:
        return _load_fixed_successful_install_receipt()
    except (ReplacementInstallError, ReplacementInstallTrustError) as error:
        raise ChallengerReplacementStartError(
            "CHALLENGER_REPLACEMENT_START_RECEIPT_SOURCE_INVALID"
        ) from error


def publish_fixed_replacement_start_receipt():
    inputs, install_receipt, install_bytes = _load_start_install_sources()
    retained = None
    primary = None
    try:
        existing = _load_existing_start_receipt(
            inputs, install_receipt, install_bytes
        )
        if existing is not None:
            receipt, observer = existing
            retained = _retain_verified_observer_sources(observer)
            if _load_start_install_sources() != (
                inputs, install_receipt, install_bytes
            ):
                raise ChallengerReplacementStartError(
                    "CHALLENGER_REPLACEMENT_FIRST_SLOT_SOURCE_CHANGED"
                )
            outcome = "ALREADY_PUBLISHED"
        else:
            observer = observe_fixed_replacement_first_slot()
            if observer["status"] != "FIRST_NATURAL_SLOT_VERIFIED":
                return {
                    "publication_outcome": "NOT_PUBLISHED",
                    "observer": observer,
                }
            retained = _retain_verified_observer_sources(observer)
            receipt = _build_replacement_start_receipt(
                observer=observer, contract=inputs["contract"],
                contract_bytes=inputs["contract_bytes"],
                install_receipt=install_receipt,
                install_receipt_bytes=install_bytes, published_at=_now(),
            )
            root = Path(inputs["contract"]["paths"]["start_receipt_root"])
            try:
                outcome, _ = _publish_contract_exact(
                    root, receipt["receipt_id"] + ".json",
                    canonical_json(receipt).encode("utf-8"),
                )
            except ReplacementInstallTrustError as error:
                raise ChallengerReplacementStartError(
                    "CHALLENGER_REPLACEMENT_START_RECEIPT_PUBLICATION_FAILED"
                ) from error
        _validate_retained_observer_sources(retained, observer)
        if _load_start_install_sources() != (
            inputs, install_receipt, install_bytes
        ):
            raise ChallengerReplacementStartError(
                "CHALLENGER_REPLACEMENT_FIRST_SLOT_SOURCE_CHANGED"
            )
        root = Path(inputs["contract"]["paths"]["start_receipt_root"])
        return {
            "publication_outcome": outcome, "observer": observer,
            "receipt": receipt,
            "receipt_path": str(root / (receipt["receipt_id"] + ".json")),
        }
    except BaseException as error:
        primary = error
        raise
    finally:
        if retained is not None:
            _close_observation_sources(retained, primary)
