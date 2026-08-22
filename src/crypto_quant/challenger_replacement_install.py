"""Atomic fixed LaunchAgent installer for replacement Challenger."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator
from .canonical import canonical_json, stable_id, utc_datetime
from .challenger_replacement_install_preflight import (
    _install_window_safe,
    load_replacement_install_preflight_bytes,
)
from .challenger_replacement_install_trust import (
    ReplacementInstallTrustError,
    _close_descriptor, _open_directory,
    _fixed_empty_event_root_identity,
    _publish_contract_exact, _read_published_exact,
    _revalidate_fixed_python_identity,
    _load_fixed_published_contract,
    replacement_install_paths,
)
from .challenger_replacement_plan import _strict_json_bytes
from .challenger_replacement_preflight import _run, _transcript
from .evidence import artifact_self_hash
from .system_paper_launchctl import SystemPaperLaunchctlParseError, parse_challenger_replacement_launchctl_print


_REPOSITORY = Path(__file__).resolve().parents[2]


class ReplacementInstallError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _binding(value, data, prefix):
    return {
        prefix + "_id": value[prefix + "_id"],
        prefix + "_hash": value[prefix + "_hash"],
        "file_sha256": hashlib.sha256(data).hexdigest(),
    }


def _schema():
    name = "schemas/challenger-replacement-install-receipt-v1.schema.json"
    return json.loads(resources.files("crypto_quant").joinpath(name).read_text())


def _first_eligible(installed):
    boundary = installed.replace(
        hour=(installed.hour // 4) * 4, minute=0, second=0, microsecond=0
    )
    return utc_datetime(boundary + timedelta(hours=4))


def _adapter_binding(contract):
    release = contract["candidate_release"]
    return {
        "release_tag": release["release_tag"],
        "peeled_commit": release["peeled_commit"],
        "manifest_version": release["manifest_version"],
        "manifest_hash": release["manifest_hash"],
        "snapshot_tree_hash": contract["snapshot"]["tree_hash"],
        "module": contract["runtime"]["module"],
    }


def _semantics(receipt, contract, preflight):
    print_argv = ["/bin/launchctl", "print", contract["service"]["identity"]]
    bootstrap = ["/bin/launchctl", "bootstrap", "gui/501",
                 contract["paths"]["target_plist"]]
    commands = receipt["commands"]
    sequence = [item["argv"] for item in commands]
    exits = [item["exit_code"] for item in commands]
    try:
        installed = datetime.fromisoformat(receipt["installed_at"].replace("Z", "+00:00"))
        observed = datetime.fromisoformat(preflight["observed_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(preflight["expires_at"].replace("Z", "+00:00"))
    except ValueError:
        return False
    common = (
        sequence in ([print_argv, bootstrap], [print_argv, bootstrap, print_argv])
        and exits[0] == 113
        and receipt["plist"]["path"] == contract["paths"]["target_plist"]
        and receipt["authority"]["launchctl_read_count"] == len(commands) - 1
        and receipt["authority"]["launchctl_mutation_count"] == 1
        and observed <= installed < expires
        and receipt["first_eligible_scheduled_for"] == _first_eligible(installed)
        and receipt["event_root_binding"] == contract["event_root"]
        and receipt["strategy_core_binding"] == contract["strategy_core"]
        and receipt["adapter_binding"] == _adapter_binding(contract)
    )
    if receipt["status"] == "INSTALLED_WAITING_FOR_FIRST_NATURAL_SLOT":
        return common and exits == [113, 0, 0] and not receipt["reason_codes"]
    allowed = (["INSTALL_POST_PRINT_INVALID"], ["INSTALL_BOOTSTRAP_STATE_UNKNOWN"])
    return common and receipt["reason_codes"] in allowed and (
        exits == [113, 255] or len(exits) == 3 and exits[1] == 0
    )


def build_replacement_install_receipt(
    *, contract, contract_bytes, preflight, preflight_bytes, status,
    installed_at, plist_record, commands, reason_codes,
):
    read_count = sum(item.get("argv", [None, None])[1] == "print"
                     for item in commands if len(item.get("argv", ())) > 1)
    mutation_count = sum(item.get("argv", [None, None])[1] == "bootstrap"
                         for item in commands if len(item.get("argv", ())) > 1)
    receipt = {
        "$schema": "./challenger-replacement-install-receipt-v1.schema.json",
        "schema_version": "1.0.0",
        "receipt_id": "challenger_replacement_install_receipt_" + "0" * 64,
        "receipt_hash": "0" * 64,
        "status": status, "installed_at": utc_datetime(installed_at),
        "contract_binding": _binding(contract, contract_bytes, "contract"),
        "preflight_binding": _binding(preflight, preflight_bytes, "receipt"),
        "snapshot_binding": {
            key: contract["snapshot"][key] for key in
            ("root", "tree_hash", "root_device", "root_inode")
        },
        "event_root_binding": dict(contract["event_root"]),
        "strategy_core_binding": dict(contract["strategy_core"]),
        "adapter_binding": _adapter_binding(contract),
        "first_eligible_scheduled_for": _first_eligible(installed_at),
        "plist": dict(plist_record), "commands": list(commands),
        "authority": {
            "github_request_count": 0, "market_request_count": 0,
            "launchctl_read_count": read_count,
            "launchctl_mutation_count": mutation_count,
            "runtime_invocation_count": 0, "state_write_count": 0,
            "credential_count": 0, "broker_request_count": 0, "order_count": 0,
        },
        "reason_codes": sorted(set(reason_codes)),
    }
    identity = {key: value for key, value in receipt.items()
                if key not in ("receipt_id", "receipt_hash")}
    receipt["receipt_id"] = stable_id(
        "challenger_replacement_install_receipt", identity
    )
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    if (tuple(Draft202012Validator(_schema()).iter_errors(receipt))
            or not _semantics(receipt, contract, preflight)):
        raise ReplacementInstallError(
            "CHALLENGER_REPLACEMENT_INSTALL_RECEIPT_INVALID")
    return receipt


def load_replacement_install_receipt_bytes(
    data, *, contract, contract_bytes, preflight, preflight_bytes,
):
    try:
        receipt = dict(_strict_json_bytes(data))
        identity = {key: value for key, value in receipt.items()
                    if key not in ("receipt_id", "receipt_hash")}
        if (
            data != canonical_json(receipt).encode()
            or tuple(Draft202012Validator(_schema()).iter_errors(receipt))
            or receipt["contract_binding"] != _binding(contract, contract_bytes, "contract")
            or receipt["preflight_binding"] != _binding(preflight, preflight_bytes, "receipt")
            or receipt["snapshot_binding"] != {
                key: contract["snapshot"][key] for key in
                ("root", "tree_hash", "root_device", "root_inode")
            }
            or receipt["event_root_binding"] != contract["event_root"]
            or receipt["strategy_core_binding"] != contract["strategy_core"]
            or receipt["adapter_binding"] != _adapter_binding(contract)
            or receipt["receipt_id"] != stable_id(
                "challenger_replacement_install_receipt", identity)
            or receipt["receipt_hash"] != artifact_self_hash(receipt, "receipt_hash")
            or not _semantics(receipt, contract, preflight)
        ):
            raise ValueError("invalid receipt")
        return receipt
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ReplacementInstallError):
            raise
        raise ReplacementInstallError(
            "CHALLENGER_REPLACEMENT_INSTALL_RECEIPT_INVALID") from error


def _load_fixed_install_inputs():
    contract, contract_bytes, plist_bytes = _load_fixed_published_contract()
    root = Path(contract["paths"]["preflight_root"])
    root_fd, _ = _open_directory(root, exact_mode=0o700)
    primary = None
    candidates = []
    try:
        names = sorted(os.listdir(root_fd))
        if any(not name.endswith(".json") for name in names):
            raise ReplacementInstallError(
                "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_INVALID")
        for name in names:
            loaded = _read_published_exact(root_fd, name)
            if loaded is None:
                raise ReplacementInstallError(
                    "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_INVALID")
            value = load_replacement_install_preflight_bytes(
                loaded[0], contract=contract,
                contract_file_sha256=hashlib.sha256(contract_bytes).hexdigest(),
            )
            if value["status"] == "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE":
                candidates.append((value, loaded[0]))
        if len(candidates) != 1:
            raise ReplacementInstallError(
                "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_INVALID")
        preflight, preflight_bytes = candidates[0]
        return {"contract": contract, "contract_bytes": contract_bytes,
                "preflight": preflight, "preflight_bytes": preflight_bytes,
                "plist_bytes": plist_bytes}
    except BaseException as error:
        primary = error
        raise
    finally:
        _close_descriptor(root_fd, primary)


def _load_fixed_successful_install_receipt():
    inputs = _load_fixed_install_inputs()
    root = Path(inputs["contract"]["paths"]["install_receipt_root"])
    root_fd = -1
    primary = None
    try:
        root_fd, _ = _open_directory(root, exact_mode=0o700)
        names = os.listdir(root_fd)
        if len(names) != 1 or not names[0].endswith(".json"):
            raise ReplacementInstallError(
                "CHALLENGER_REPLACEMENT_INSTALL_RECEIPT_REQUIRED"
            )
        loaded = _read_published_exact(root_fd, names[0])
        if loaded is None:
            raise ReplacementInstallError(
                "CHALLENGER_REPLACEMENT_INSTALL_RECEIPT_REQUIRED"
            )
        receipt = load_replacement_install_receipt_bytes(
            loaded[0], contract=inputs["contract"],
            contract_bytes=inputs["contract_bytes"],
            preflight=inputs["preflight"],
            preflight_bytes=inputs["preflight_bytes"],
        )
        if (
            receipt["status"] != "INSTALLED_WAITING_FOR_FIRST_NATURAL_SLOT"
            or names[0] != receipt["receipt_id"] + ".json"
            or _load_fixed_install_inputs() != inputs
        ):
            raise ReplacementInstallError(
                "CHALLENGER_REPLACEMENT_INSTALL_RECEIPT_REQUIRED"
            )
        return inputs, receipt, loaded[0]
    except BaseException as error:
        primary = error
        raise
    finally:
        if root_fd >= 0:
            _close_descriptor(root_fd, primary)


def _now():
    return datetime.now(timezone.utc)


def _target_absent(contract):
    return not os.path.lexists(contract["paths"]["target_plist"])


def _plist_record(path, entry, body):
    return {
        "path": str(path), "device": entry.st_dev, "inode": entry.st_ino,
        "owner_uid": entry.st_uid, "mode": entry.st_mode & 0o777,
        "link_count": entry.st_nlink, "size_bytes": entry.st_size,
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _publish_plist(contract, body):
    path = Path(contract["paths"]["target_plist"])
    outcome, entry = _publish_contract_exact(
        path.parent, path.name, body, parent_mode=None
    )
    return outcome, _plist_record(path, entry, body)


def _revalidate_empty_event_root(contract):
    try:
        if _fixed_empty_event_root_identity(contract["paths"]) != contract[
            "event_root"
        ]:
            raise ValueError("identity")
    except (KeyError, TypeError, ValueError, ReplacementInstallTrustError) as error:
        raise ReplacementInstallError(
            "CHALLENGER_REPLACEMENT_INSTALL_EVENT_ROOT_CHANGED"
        ) from error


def _command(argv):
    return _run(argv, _REPOSITORY)


def _post_print_valid(contract, result):
    code, stdout, stderr = result
    if code != 0 or stderr:
        return False
    try:
        parse_challenger_replacement_launchctl_print(stdout, contract)
        return True
    except (KeyError, TypeError, SystemPaperLaunchctlParseError):
        return False


def _publish_install_receipt(contract, receipt):
    root = Path(contract["paths"]["install_receipt_root"])
    outcome, _ = _publish_contract_exact(
        root, receipt["receipt_id"] + ".json", canonical_json(receipt).encode()
    )
    return outcome


def _finish(inputs, record, status, command_pairs, reasons):
    if _load_fixed_install_inputs() != inputs:
        raise ReplacementInstallError(
            "CHALLENGER_REPLACEMENT_INSTALL_SOURCE_CHANGED")
    _, replayed_record = _publish_plist(inputs["contract"], inputs["plist_bytes"])
    if replayed_record != record:
        raise ReplacementInstallError(
            "CHALLENGER_REPLACEMENT_INSTALL_TARGET_IDENTITY_CHANGED")
    receipt = build_replacement_install_receipt(
        contract=inputs["contract"], contract_bytes=inputs["contract_bytes"],
        preflight=inputs["preflight"], preflight_bytes=inputs["preflight_bytes"],
        status=status, installed_at=_now(), plist_record=record,
        commands=[_transcript(argv, result) for argv, result in command_pairs],
        reason_codes=reasons,
    )
    publication = _publish_install_receipt(inputs["contract"], receipt)
    return {"receipt": receipt, "publication_outcome": publication}


def install_fixed_replacement_launch_agent():
    inputs = _load_fixed_install_inputs()
    contract, preflight = inputs["contract"], inputs["preflight"]
    now = _now()
    observed = datetime.fromisoformat(
        preflight["observed_at"].replace("Z", "+00:00")
    )
    expires = datetime.fromisoformat(preflight["expires_at"].replace("Z", "+00:00"))
    if (preflight["status"] != "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE"
            or not observed <= now < expires
            or not _install_window_safe(now)):
        raise ReplacementInstallError(
            "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_EXPIRED")
    try:
        _revalidate_fixed_python_identity(contract)
    except ReplacementInstallTrustError as error:
        raise ReplacementInstallError(
            "CHALLENGER_REPLACEMENT_INSTALL_PYTHON_IDENTITY_CHANGED"
        ) from error
    target = contract["paths"]["target_plist"]
    identity = contract["service"]["identity"]
    print_argv = ("/bin/launchctl", "print", identity)
    first = _command(print_argv)
    if first[0] != 113 or not _target_absent(contract):
        raise ReplacementInstallError(
            "CHALLENGER_REPLACEMENT_INSTALL_EXISTING_STATE_CONFLICT")
    outcome, record = _publish_plist(contract, inputs["plist_bytes"])
    if outcome != "PUBLISHED":
        raise ReplacementInstallError(
            "CHALLENGER_REPLACEMENT_INSTALL_EXISTING_STATE_CONFLICT")
    bootstrap_argv = ("/bin/launchctl", "bootstrap", "gui/501", target)
    if _load_fixed_install_inputs() != inputs:
        raise ReplacementInstallError(
            "CHALLENGER_REPLACEMENT_INSTALL_SOURCE_CHANGED")
    _revalidate_empty_event_root(contract)
    _, replayed_record = _publish_plist(contract, inputs["plist_bytes"])
    if replayed_record != record:
        raise ReplacementInstallError(
            "CHALLENGER_REPLACEMENT_INSTALL_TARGET_IDENTITY_CHANGED")
    try:
        bootstrap = _command(bootstrap_argv)
    except Exception:
        bootstrap = (255, b"", b"TRANSPORT_STATE_UNKNOWN")
        return _finish(
            inputs, record, "INSTALL_STATE_UNKNOWN_FAILED_CLOSED",
            ((print_argv, first), (bootstrap_argv, bootstrap)),
            ["INSTALL_BOOTSTRAP_STATE_UNKNOWN"],
        )
    if bootstrap[0] != 0:
        raise ReplacementInstallError(
            "CHALLENGER_REPLACEMENT_INSTALL_BOOTSTRAP_FAILED")
    try:
        post = _command(print_argv)
    except Exception:
        post = (255, b"", b"TRANSPORT_STATE_UNKNOWN")
    verified = _post_print_valid(contract, post)
    status = ("INSTALLED_WAITING_FOR_FIRST_NATURAL_SLOT" if verified
              else "INSTALL_STATE_UNKNOWN_FAILED_CLOSED")
    reasons = [] if verified else ["INSTALL_POST_PRINT_INVALID"]
    return _finish(
        inputs, record, status,
        ((print_argv, first), (bootstrap_argv, bootstrap), (print_argv, post)),
        reasons,
    )
