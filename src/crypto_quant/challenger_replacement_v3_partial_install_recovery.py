"""Strict v0.78.7 plan for preserving the v0.78.5 partial installation."""

import copy
import hashlib
import json
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id
from .challenger_replacement_plan import _strict_json_bytes
from .evidence import artifact_self_hash


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
