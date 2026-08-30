"""Strict v0.78.7 plan for preserving the v0.78.5 partial installation."""

import copy
import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id
from .challenger_replacement_plan import _strict_json_bytes
from .challenger_replacement_install_trust import (
    ReplacementInstallTrustError,
    _close_descriptor,
    _open_directory,
    _publish_contract_exact,
    _read_exact,
    _read_published_exact,
    _read_snapshot_file,
    _replay_snapshot,
    _require_open_flag,
    _same_file_identity,
    _snapshot_tree_entries,
    _snapshot_tree_hash,
    _validate_directory_attachment,
)
from .evidence import artifact_self_hash
from .challenger_replacement_v3_activation_trust import (
    load_fixed_published_v3_install_contract,
)
from .canonical import utc_datetime


_REPOSITORY = Path(__file__).resolve().parents[2]
_PLAN_RELATIVE = Path(
    "config/challenger-replacement-v3-partial-install-recovery-v0.78.7.json"
)


class ChallengerReplacementPartialInstallRecoveryError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _file_record(
    path, sha256, device, inode, mode, size_bytes, mtime_ns, ctime_ns
):
    return {
        "path": path,
        "sha256": sha256,
        "device": device,
        "inode": inode,
        "owner_uid": 501,
        "mode": mode,
        "link_count": 1,
        "size_bytes": size_bytes,
        "mtime_ns": mtime_ns,
        "ctime_ns": ctime_ns,
    }


def _directory_record(
    path, device, inode, link_count, size_bytes, mtime_ns, ctime_ns, entry_names
):
    names = list(entry_names)
    return {
        "path": path,
        "device": device,
        "inode": inode,
        "owner_uid": 501,
        "mode": 0o700,
        "link_count": link_count,
        "size_bytes": size_bytes,
        "mtime_ns": mtime_ns,
        "ctime_ns": ctime_ns,
        "entry_names": names,
        "entry_names_hash": hashlib.sha256(
            canonical_json(names).encode("utf-8")
        ).hexdigest(),
    }


def _build_fixed_plan():
    runtime = "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1"
    launch_agents = "/Users/chenm4/Library/LaunchAgents"
    deployment = runtime + "/deployment"
    value = {
        "$schema": "./challenger-replacement-v3-partial-install-recovery-plan-v1.schema.json",
        "schema_version": "1.0.0",
        "plan_id": "challenger_replacement_v3_partial_install_recovery_plan_" + "0" * 64,
        "plan_hash": "0" * 64,
        "status": "PARTIAL_INSTALL_RECOVERY_PLAN_FROZEN_NOT_EXECUTED",
        "foundation": {
            "repository": "cjl308868584-lang/crypto-quant-core",
            "visibility": "PUBLIC",
            "release_tag": "v0.78.6",
            "package_version": "0.78.6",
            "peeled_commit": "faf6e03632c21dba0894f0a1248f308306b13737",
            "tag_object": "bc78d140129a23b38d3c72c1f4a93d8df568275e",
            "manifest_version": "1.78.0",
            "manifest_hash": "808c2fd2aefbfc363725f0cf2a46a74cfc56a538e284dce6fd62042d475ea477",
            "manifest_file_sha256": "f06bbfa5dba81cd9f713c4d6b51bbd403d67439b063fdfe1f5b7fe49ae0f5cea",
        },
        "incident": {
            "release_tag": "v0.78.5",
            "reason_code": "INSTALL_RECEIPT_CANONICAL_TIMESTAMP_REPLAY_FAILED",
            "failed_install_receipt_id": "challenger_replacement_v3_activation_install_1360395f65ff586b76dc0c430c3e724046c93a32de55dd6293072f210bbca5cf",
            "preflight_receipt_id": "challenger_replacement_v3_activation_preflight_ffe13b514e31d92e6b8c7cec26a444a23ad6dd16ea9fae66b59c04c42454cfee",
            "preservation_policy": "IMMUTABLE_READ_ONLY_NO_REPAIR",
        },
        "preserved_files": {
            "target_plist": _file_record(
                launch_agents + "/local.crypto-quant.challenger-replacement-v1.plist",
                "30efabbd76ab5af9c277213b3377612b5119a7889c6b8165748dbcc36acd329b",
                "16777233", "28400729", 0o600, 3994,
                "1788106445350995444", "1788106445351350194",
            ),
            "predecessor_plist": _file_record(
                launch_agents + "/local.crypto-quant.challenger-forward.plist",
                "f6b2283ad4c01ee6e7dc8e954bdcb29dd221d5b79d4a04b69618af1d26182b53",
                "16777233", "13229927", 0o600, 2409,
                "1785225670103701526", "1785225670104072295",
            ),
            "install_contract": _file_record(
                deployment + "/challenger-replacement-v3-install-contract-v0.78.5.json",
                "03d6cf60e51ebe87d5a81d8f45d33d8e39d4074bf57b6bd450c4b5cdfbd026af",
                "16777233", "28345100", 0o600, 7716,
                "1788094333906665632", "1788094333906787632",
            ),
            "candidate_plist": _file_record(
                deployment + "/local.crypto-quant.challenger-replacement-v1-v0.78.5.plist",
                "30efabbd76ab5af9c277213b3377612b5119a7889c6b8165748dbcc36acd329b",
                "16777233", "28345099", 0o600, 3994,
                "1788094333906258632", "1788094333906436132",
            ),
            "failed_install_receipt": _file_record(
                deployment + "/install-receipts-v0.78.5/"
                "challenger_replacement_v3_activation_install_1360395f65ff586b76dc0c430c3e724046c93a32de55dd6293072f210bbca5cf.json",
                "97747c0ebd2f49c3afe875e9a1f99d541d98e363ac457e767a622586f8523198",
                "16777233", "28400732", 0o600, 3536,
                "1788106446101743460", "1788106446102116127",
            ),
            "preflight_receipt": _file_record(
                deployment + "/preflight-receipts-v0.78.5/"
                "challenger_replacement_v3_activation_preflight_ffe13b514e31d92e6b8c7cec26a444a23ad6dd16ea9fae66b59c04c42454cfee.json",
                "3440beab833c998a3d0c250e60fd2f6876f4aa206c0e5c609a772d4333a59ce5",
                "16777233", "28400661", 0o600, 3768,
                "1788106370886738162", "1788106370887602828",
            ),
        },
        "empty_directories": {
            "state_parent": _directory_record(
                runtime + "/state", "16777233", "27114720", 3, 96,
                "1787981014554873954", "1787981014554873954",
                ["challenger-replacement-events-v1"],
            ),
            "event_root": _directory_record(
                runtime + "/state/challenger-replacement-events-v1",
                "16777233", "27114721", 2, 64,
                "1787981014554873120", "1787981014554882704", [],
            ),
            "start_receipt_root": _directory_record(
                runtime + "/evidence/start-receipts",
                "16777233", "27114723", 2, 64,
                "1787981014554948496", "1787981014554958079", [],
            ),
            "log_root": _directory_record(
                runtime + "/log", "16777233", "27114724", 2, 64,
                "1787981014554984121", "1787981014554995580", [],
            ),
        },
        "snapshot": {
            "tree_hash": "b5ac484d5b7b8e61d36c33b7cc686fda23a79524734167158123720b2c14cfbe",
            "file_count": 101,
            "total_size_bytes": 3248480,
            "root_record": _directory_record(
                deployment + "/snapshots/"
                "b5ac484d5b7b8e61d36c33b7cc686fda23a79524734167158123720b2c14cfbe",
                "16777233", "28344985", 5, 160,
                "1788094333382848241", "1788094333384556282",
                ["artifacts", "src", "vendor"],
            ),
        },
        "candidate": {
            "release_tag": "v0.78.7",
            "target_plist": launch_agents
            + "/local.crypto-quant.challenger-replacement-v1-v0.78.7.plist",
            "recovery_receipt_root": deployment + "/partial-install-recovery-receipts-v0.78.7",
        },
        "required_state": {
            "launchctl_domain": "gui/501",
            "service_labels": [
                "local.crypto-quant.challenger-forward",
                "local.crypto-quant.challenger-replacement-v1",
            ],
            "service_state": "DISABLED_AND_NOT_LOADED",
            "automation_id": "v0-78-3-replacement",
            "automation_path": "/Users/chenm4/.codex/automations/v0-78-3-replacement/automation.toml",
            "automation_status": "PAUSED",
        },
        "authority": {
            "production_activation": False,
            "runtime_install_authorized": False,
            "replacement_start_authorized": False,
            "credential_access_allowed": False,
            "private_account_requests_allowed": False,
            "broker_requests_allowed": False,
            "orders_allowed": False,
            "fund_movement_allowed": False,
        },
    }
    identity = {key: item for key, item in value.items() if key not in ("plan_id", "plan_hash")}
    value["plan_id"] = stable_id(
        "challenger_replacement_v3_partial_install_recovery_plan", identity
    )
    value["plan_hash"] = artifact_self_hash(value, "plan_hash")
    return value


def _schema():
    return json.loads(
        resources.files("crypto_quant").joinpath(
            "schemas/challenger-replacement-v3-partial-install-recovery-plan-v1.schema.json"
        ).read_text(encoding="utf-8")
    )


def load_fixed_v3_partial_install_recovery_plan_bytes(data):
    try:
        value = dict(_strict_json_bytes(data))
        identity = {
            key: item for key, item in value.items()
            if key not in ("plan_id", "plan_hash")
        }
        if (
            data != canonical_json(value).encode("utf-8")
            or tuple(Draft202012Validator(_schema()).iter_errors(value))
            or value["plan_id"] != stable_id(
                "challenger_replacement_v3_partial_install_recovery_plan", identity
            )
            or value["plan_hash"] != artifact_self_hash(value, "plan_hash")
            or value != _build_fixed_plan()
        ):
            raise ValueError("plan")
        return copy.deepcopy(value)
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementPartialInstallRecoveryError(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_PLAN_INVALID"
        ) from error


def load_fixed_v3_partial_install_recovery_plan():
    try:
        body = (_REPOSITORY / _PLAN_RELATIVE).read_bytes()
    except OSError as error:
        raise ChallengerReplacementPartialInstallRecoveryError(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_PLAN_INVALID"
        ) from error
    return load_fixed_v3_partial_install_recovery_plan_bytes(body), body


def _raise_recovery(reason_code, error=None):
    failure = ChallengerReplacementPartialInstallRecoveryError(reason_code)
    if error is None:
        raise failure
    raise failure from error


def _stat_fields(value):
    return {
        "device": str(value.st_dev),
        "inode": str(value.st_ino),
        "owner_uid": value.st_uid,
        "mode": stat.S_IMODE(value.st_mode),
        "link_count": value.st_nlink,
        "size_bytes": value.st_size,
        "mtime_ns": str(value.st_mtime_ns),
        "ctime_ns": str(value.st_ctime_ns),
    }


def _verify_file_record(record):
    parent_fd = -1
    primary = None
    try:
        path = Path(record["path"])
        parent_mode = 0o755 if path.parent == Path(
            "/Users/chenm4/Library/LaunchAgents"
        ) else 0o700
        parent_fd, _ = _open_directory(path.parent, exact_mode=parent_mode)
        found = _read_published_exact(parent_fd, path.name)
        if found is None:
            raise ValueError("missing")
        body, opened = found
        expected = {key: record[key] for key in _stat_fields(opened)}
        if (
            _stat_fields(opened) != expected
            or hashlib.sha256(body).hexdigest() != record["sha256"]
        ):
            raise ValueError("identity")
        return body
    except BaseException as error:
        primary = error
        if isinstance(error, ChallengerReplacementPartialInstallRecoveryError):
            raise
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT", error
        )
    finally:
        if parent_fd >= 0:
            _close_descriptor(parent_fd, primary)


def _verify_directory_record(record):
    descriptor = -1
    primary = None
    try:
        path = Path(record["path"])
        descriptor, opened = _open_directory(path, exact_mode=0o700)
        names = sorted(os.listdir(descriptor))
        expected = {key: record[key] for key in _stat_fields(opened)}
        if (
            _stat_fields(opened) != expected
            or names != record["entry_names"]
            or hashlib.sha256(canonical_json(names).encode("utf-8")).hexdigest()
            != record["entry_names_hash"]
        ):
            raise ValueError("identity")
        _validate_directory_attachment(
            path,
            descriptor,
            opened,
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT",
        )
        return names
    except BaseException as error:
        primary = error
        if isinstance(error, ChallengerReplacementPartialInstallRecoveryError):
            raise
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT", error
        )
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor, primary)


def _verify_snapshot(plan):
    root_fd = parent_fd = -1
    primary = None
    try:
        snapshot = plan["snapshot"]
        root = Path(snapshot["root_record"]["path"])
        if root.name != snapshot["tree_hash"]:
            raise ValueError("snapshot path")
        root_fd, _ = _open_directory(root, exact_mode=0o700)
        files, _ = _snapshot_tree_entries(root_fd)
        inventory = {
            name: hashlib.sha256(
                _read_snapshot_file(root_fd, name)
            ).hexdigest()
            for name in files
        }
        if _snapshot_tree_hash(inventory) != snapshot["tree_hash"]:
            raise ValueError("snapshot hash")
        parent_fd, _ = _open_directory(root.parent, exact_mode=0o700)
        replayed = _replay_snapshot(parent_fd, snapshot["tree_hash"], inventory)
        if (
            replayed is None
            or len(inventory) != snapshot["file_count"]
            or replayed[1] != snapshot["total_size_bytes"]
            or (str(replayed[0].st_dev), str(replayed[0].st_ino))
            != (
                snapshot["root_record"]["device"],
                snapshot["root_record"]["inode"],
            )
        ):
            raise ValueError("snapshot replay")
    except BaseException as error:
        primary = error
        if isinstance(error, ChallengerReplacementPartialInstallRecoveryError):
            raise
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT", error
        )
    finally:
        if parent_fd >= 0:
            _close_descriptor(parent_fd, primary)
        if root_fd >= 0:
            _close_descriptor(root_fd, primary)


def _read_automation_status(path):
    parent_fd = descriptor = -1
    primary = None
    try:
        parent_mode = 0o755 if path == Path(
            "/Users/chenm4/.codex/automations/v0-78-3-replacement/automation.toml"
        ) else 0o700
        parent_fd, _ = _open_directory(path.parent, exact_mode=parent_mode)
        descriptor = os.open(
            path.name,
            os.O_RDONLY
            | _require_open_flag("O_NOFOLLOW")
            | _require_open_flag("O_NONBLOCK"),
            dir_fd=parent_fd,
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) not in (0o600, 0o644)
            or not 0 < opened.st_size <= 1024 * 1024
        ):
            raise ValueError("automation identity")
        body = _read_exact(descriptor, opened.st_size)
        after = os.fstat(descriptor)
        attached = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if not _same_file_identity(opened, after) or not _same_file_identity(
            after, attached
        ):
            raise ValueError("automation attachment")
        entries = {}
        for line in body.decode("utf-8", "strict").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            matched = re.fullmatch(
                r'([A-Za-z0-9_-]+) = ("(?:[^"\\]|\\.)*"|[0-9]+|true|false)',
                line,
            )
            if matched is None or matched.group(1) in entries:
                raise ValueError("automation syntax")
            entries[matched.group(1)] = matched.group(2)
        if entries.get("status") != '"PAUSED"':
            raise ValueError("automation status")
        return "PAUSED"
    except BaseException as error:
        primary = error
        if isinstance(error, ChallengerReplacementPartialInstallRecoveryError):
            raise
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT", error
        )
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor, primary)
        if parent_fd >= 0:
            _close_descriptor(parent_fd, primary)


def _run_observation_command(argv):
    try:
        result = subprocess.run(
            tuple(argv),
            cwd=_REPOSITORY,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT", error
        )
    if len(result.stdout) > 1024 * 1024 or len(result.stderr) > 1024 * 1024:
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT"
        )
    return bytes(result.stdout), bytes(result.stderr), result.returncode


def _verify_services(required):
    domain = required["launchctl_domain"]
    labels = required["service_labels"]
    disabled_argv = ("/bin/launchctl", "print-disabled", domain)
    stdout, stderr, code = _run_observation_command(disabled_argv)
    try:
        text = stdout.decode("utf-8", "strict")
    except UnicodeError as error:
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT", error
        )
    lines = text.splitlines()
    if lines[:1] == [""]:
        lines = lines[1:]
    entries = {}
    for line in lines[1:-1]:
        matched = re.fullmatch(
            r'\t\t"([A-Za-z0-9._-]+)" => (disabled|enabled)', line
        )
        if matched is None or matched.group(1) in entries:
            _raise_recovery(
                "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT"
            )
        entries[matched.group(1)] = matched.group(2)
    if (
        code != 0 or stderr or lines[:1] != ["\tdisabled services = {"]
        or lines[-1:] != ["\t}"]
        or any(entries.get(label) != "disabled" for label in labels)
    ):
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT"
        )
    transcripts = [{
        "argv": list(disabled_argv),
        "exit_code": code,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
    }]
    for label in labels:
        argv = ("/bin/launchctl", "print", domain + "/" + label)
        out, err, exit_code = _run_observation_command(argv)
        not_found = (
            'Could not find service "{}" in domain for user gui: 501\n'.format(
                label
            ).encode("utf-8")
        )
        if (
            exit_code != 113
            or out
            or err not in (not_found, b"Bad request.\n" + not_found)
        ):
            _raise_recovery(
                "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT"
            )
        transcripts.append({
            "argv": list(argv),
            "exit_code": exit_code,
            "stdout_sha256": hashlib.sha256(out).hexdigest(),
            "stderr_sha256": hashlib.sha256(err).hexdigest(),
        })
    return transcripts


def _verify_preserved_partial_install_history(plan):
    try:
        observed_files = {
            name: _verify_file_record(record)
            for name, record in plan["preserved_files"].items()
        }
        _verify_directory_record(plan["snapshot"]["root_record"])
        _verify_snapshot(plan)
        return {
            name: hashlib.sha256(body).hexdigest()
            for name, body in observed_files.items()
        }
    except ChallengerReplacementPartialInstallRecoveryError:
        raise
    except (KeyError, TypeError, ValueError, ReplacementInstallTrustError) as error:
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT", error
        )


def _verify_preserved_partial_install(plan, allow_new_target=False):
    try:
        preserved_hashes = _verify_preserved_partial_install_history(plan)
        for record in plan["empty_directories"].values():
            _verify_directory_record(record)
        transcripts = _verify_services(plan["required_state"])
        automation = _read_automation_status(
            Path(plan["required_state"]["automation_path"])
        )
        if (not allow_new_target
                and os.path.lexists(plan["candidate"]["target_plist"])):
            _raise_recovery(
                "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT"
            )
        return {
            "service_state": "DISABLED_AND_NOT_LOADED",
            "automation_status": automation,
            "event_count": 0,
            "start_receipt_count": 0,
            "log_file_count": 0,
            "preserved_file_sha256": preserved_hashes,
            "transcripts": transcripts,
        }
    except ChallengerReplacementPartialInstallRecoveryError:
        raise
    except (KeyError, TypeError, ValueError, ReplacementInstallTrustError) as error:
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT", error
        )


def _binding(value, body, prefix):
    return {
        prefix + "_id": value[prefix + "_id"],
        prefix + "_hash": value[prefix + "_hash"],
        "file_sha256": hashlib.sha256(body).hexdigest(),
    }


def _candidate_binding(contract, contract_bytes, candidate_plist_bytes):
    return {
        **_binding(contract, contract_bytes, "contract"),
        "release": copy.deepcopy(contract["release"]),
        "candidate_plist_sha256": hashlib.sha256(
            candidate_plist_bytes
        ).hexdigest(),
        "target_plist": contract["paths"]["target_plist"],
    }


def _receipt_semantics(
    receipt, *, plan, plan_bytes, contract, contract_bytes,
    candidate_plist_bytes, expected_observation
):
    try:
        observation = receipt["observation"]
        return (
            receipt["status"]
            == "PARTIAL_INSTALL_RECOVERY_ELIGIBLE_NOT_EXECUTED"
            and receipt["plan_binding"] == _binding(plan, plan_bytes, "plan")
            and receipt["candidate_binding"]
            == _candidate_binding(contract, contract_bytes, candidate_plist_bytes)
            and receipt["incident_binding"] == {
                "release_tag": plan["incident"]["release_tag"],
                "failed_install_receipt_id": plan["incident"][
                    "failed_install_receipt_id"
                ],
                "preflight_receipt_id": plan["incident"]["preflight_receipt_id"],
                "preserved_file_sha256": {
                    name: record["sha256"]
                    for name, record in plan["preserved_files"].items()
                },
                "snapshot_tree_hash": plan["snapshot"]["tree_hash"],
            }
            and receipt["supersession"] == {
                "from_failed_install_receipt_id": plan["incident"][
                    "failed_install_receipt_id"
                ],
                "to_contract_id": contract["contract_id"],
                "new_target_plist": plan["candidate"]["target_plist"],
                "relationship": "SUPERSEDES_FAILED_INSTALL_WITHOUT_MUTATING_HISTORY",
            }
            and contract["release"]["tag"] == plan["candidate"]["release_tag"]
            and contract["paths"]["target_plist"]
            == plan["candidate"]["target_plist"]
            and contract["paths"]["recovery_receipt_root"]
            == plan["candidate"]["recovery_receipt_root"]
            and contract["plist"]["file_sha256"]
            == hashlib.sha256(candidate_plist_bytes).hexdigest()
            and observation["service_state"] == "DISABLED_AND_NOT_LOADED"
            and observation["automation_status"] == "PAUSED"
            and observation["event_count"] == 0
            and observation["start_receipt_count"] == 0
            and observation["log_file_count"] == 0
            and observation["preserved_file_sha256"]
            == receipt["incident_binding"]["preserved_file_sha256"]
            and observation == expected_observation
            and len(observation["transcripts"]) == 3
            and receipt["authority"] == {
                "filesystem_observation_count": (
                    len(plan["preserved_files"])
                    + len(plan["empty_directories"])
                    + 1
                ),
                "launchctl_read_count": 3,
                "launchctl_mutation_count": 0,
                "runtime_invocation_count": 0,
                "state_write_count": 0,
                "credential_count": 0,
                "account_request_count": 0,
                "broker_request_count": 0,
                "order_count": 0,
                "fund_movement_count": 0,
            }
            and receipt["reason_codes"] == []
        )
    except (KeyError, TypeError):
        return False


def build_fixed_v3_partial_install_recovery_receipt(
    *,
    plan,
    plan_bytes,
    observation,
    contract,
    contract_bytes,
    candidate_plist_bytes,
    observed_at,
):
    receipt = {
        "$schema": "./challenger-replacement-v3-partial-install-recovery-receipt-v1.schema.json",
        "schema_version": "1.0.0",
        "receipt_id": "challenger_replacement_v3_partial_install_recovery_"
        + "0" * 64,
        "receipt_hash": "0" * 64,
        "status": "PARTIAL_INSTALL_RECOVERY_ELIGIBLE_NOT_EXECUTED",
        "observed_at": utc_datetime(observed_at.replace(microsecond=0)),
        "plan_binding": _binding(plan, plan_bytes, "plan"),
        "incident_binding": {
            "release_tag": plan["incident"]["release_tag"],
            "failed_install_receipt_id": plan["incident"][
                "failed_install_receipt_id"
            ],
            "preflight_receipt_id": plan["incident"]["preflight_receipt_id"],
            "preserved_file_sha256": {
                name: record["sha256"]
                for name, record in plan["preserved_files"].items()
            },
            "snapshot_tree_hash": plan["snapshot"]["tree_hash"],
        },
        "candidate_binding": _candidate_binding(
            contract, contract_bytes, candidate_plist_bytes
        ),
        "observation": copy.deepcopy(dict(observation)),
        "supersession": {
            "from_failed_install_receipt_id": plan["incident"][
                "failed_install_receipt_id"
            ],
            "to_contract_id": contract["contract_id"],
            "new_target_plist": plan["candidate"]["target_plist"],
            "relationship": "SUPERSEDES_FAILED_INSTALL_WITHOUT_MUTATING_HISTORY",
        },
        "authority": {
            "filesystem_observation_count": (
                len(plan["preserved_files"])
                + len(plan["empty_directories"])
                + 1
            ),
            "launchctl_read_count": 3,
            "launchctl_mutation_count": 0,
            "runtime_invocation_count": 0,
            "state_write_count": 0,
            "credential_count": 0,
            "account_request_count": 0,
            "broker_request_count": 0,
            "order_count": 0,
            "fund_movement_count": 0,
        },
        "reason_codes": [],
    }
    identity = {
        key: value for key, value in receipt.items()
        if key not in ("receipt_id", "receipt_hash")
    }
    receipt["receipt_id"] = stable_id(
        "challenger_replacement_v3_partial_install_recovery", identity
    )
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    if not _receipt_semantics(
        receipt,
        plan=plan,
        plan_bytes=plan_bytes,
        contract=contract,
        contract_bytes=contract_bytes,
        candidate_plist_bytes=candidate_plist_bytes,
        expected_observation=observation,
    ):
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_RECEIPT_INVALID"
        )
    return receipt


def _receipt_schema():
    return json.loads(
        resources.files("crypto_quant").joinpath(
            "schemas/challenger-replacement-v3-partial-install-recovery-receipt-v1.schema.json"
        ).read_text(encoding="utf-8")
    )


def load_fixed_v3_partial_install_recovery_receipt_bytes(
    data,
    *,
    plan,
    plan_bytes,
    contract,
    contract_bytes,
    candidate_plist_bytes,
    expected_observation,
):
    try:
        value = dict(_strict_json_bytes(data))
        identity = {
            key: item for key, item in value.items()
            if key not in ("receipt_id", "receipt_hash")
        }
        if (
            data != canonical_json(value).encode("utf-8")
            or tuple(Draft202012Validator(_receipt_schema()).iter_errors(value))
            or value["receipt_id"] != stable_id(
                "challenger_replacement_v3_partial_install_recovery", identity
            )
            or value["receipt_hash"]
            != artifact_self_hash(value, "receipt_hash")
            or not _receipt_semantics(
                value,
                plan=plan,
                plan_bytes=plan_bytes,
                contract=contract,
                contract_bytes=contract_bytes,
                candidate_plist_bytes=candidate_plist_bytes,
                expected_observation=expected_observation,
            )
        ):
            raise ValueError("receipt")
        observed_at = datetime.fromisoformat(
            value["observed_at"].replace("Z", "+00:00")
        )
        rebuilt = build_fixed_v3_partial_install_recovery_receipt(
            plan=plan,
            plan_bytes=plan_bytes,
            observation=value["observation"],
            contract=contract,
            contract_bytes=contract_bytes,
            candidate_plist_bytes=candidate_plist_bytes,
            observed_at=observed_at,
        )
        if rebuilt != value:
            raise ValueError("rebuild")
        return copy.deepcopy(value)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        if isinstance(error, ChallengerReplacementPartialInstallRecoveryError):
            raise
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_RECEIPT_INVALID", error
        )


def _now():
    return datetime.now(timezone.utc)


def load_fixed_published_v3_partial_install_recovery_receipt(
    *, plan, plan_bytes, contract, contract_bytes, candidate_plist_bytes,
    expected_observation=None, expected_binding=None
):
    descriptor = -1
    primary = None
    try:
        descriptor, _ = _open_directory(
            Path(plan["candidate"]["recovery_receipt_root"]), exact_mode=0o700
        )
        names = sorted(os.listdir(descriptor))
        if not names:
            return None
        if len(names) != 1 or not names[0].endswith(".json"):
            raise ValueError("receipt count")
        found = _read_published_exact(descriptor, names[0])
        if found is None:
            raise ValueError("receipt missing")
        untrusted = dict(_strict_json_bytes(found[0]))
        if expected_observation is None:
            if expected_binding != _binding(untrusted, found[0], "receipt"):
                raise ValueError("receipt binding")
            expected_observation = untrusted["observation"]
        receipt = load_fixed_v3_partial_install_recovery_receipt_bytes(
            found[0],
            plan=plan,
            plan_bytes=plan_bytes,
            contract=contract,
            contract_bytes=contract_bytes,
            candidate_plist_bytes=candidate_plist_bytes,
            expected_observation=expected_observation,
        )
        if names[0] != receipt["receipt_id"] + ".json":
            raise ValueError("receipt filename")
        return receipt, found[0]
    except BaseException as error:
        primary = error
        if isinstance(error, ChallengerReplacementPartialInstallRecoveryError):
            raise
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_RECEIPT_INVALID", error
        )
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor, primary)


def publish_fixed_v3_partial_install_recovery_receipt():
    plan, plan_bytes = load_fixed_v3_partial_install_recovery_plan()
    try:
        contract, contract_bytes, candidate_plist_bytes = (
            load_fixed_published_v3_install_contract()
        )
    except BaseException as error:
        if isinstance(error, ChallengerReplacementPartialInstallRecoveryError):
            raise
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_CANDIDATE_INVALID", error
        )
    observation = _verify_preserved_partial_install(plan)
    try:
        existing = load_fixed_published_v3_partial_install_recovery_receipt(
            plan=plan,
            plan_bytes=plan_bytes,
            contract=contract,
            contract_bytes=contract_bytes,
            candidate_plist_bytes=candidate_plist_bytes,
            expected_observation=observation,
        )
    except ChallengerReplacementPartialInstallRecoveryError as error:
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_PUBLICATION_FAILED", error
        )
    if existing is not None:
        try:
            outcome, _ = _publish_contract_exact(
                Path(plan["candidate"]["recovery_receipt_root"]),
                existing[0]["receipt_id"] + ".json", existing[1],
            )
        except BaseException as error:
            _raise_recovery(
                "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_PUBLICATION_FAILED",
                error,
            )
        if outcome != "ALREADY_PUBLISHED":
            _raise_recovery(
                "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_PUBLICATION_FAILED"
            )
        after = _verify_preserved_partial_install(plan)
        if after != observation:
            _raise_recovery(
                "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT"
            )
        return {"receipt": existing[0], "publication_outcome": outcome}
    receipt = build_fixed_v3_partial_install_recovery_receipt(
        plan=plan,
        plan_bytes=plan_bytes,
        observation=observation,
        contract=contract,
        contract_bytes=contract_bytes,
        candidate_plist_bytes=candidate_plist_bytes,
        observed_at=_now(),
    )
    body = canonical_json(receipt).encode("utf-8")
    try:
        outcome, _ = _publish_contract_exact(
            Path(plan["candidate"]["recovery_receipt_root"]),
            receipt["receipt_id"] + ".json",
            body,
        )
    except BaseException as error:
        if isinstance(error, ChallengerReplacementPartialInstallRecoveryError):
            raise
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_PUBLICATION_FAILED", error
        )
    replayed = load_fixed_v3_partial_install_recovery_receipt_bytes(
        body,
        plan=plan,
        plan_bytes=plan_bytes,
        contract=contract,
        contract_bytes=contract_bytes,
        candidate_plist_bytes=candidate_plist_bytes,
        expected_observation=observation,
    )
    after = _verify_preserved_partial_install(plan)
    if after != observation:
        _raise_recovery(
            "CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT"
        )
    return {"receipt": replayed, "publication_outcome": outcome}
