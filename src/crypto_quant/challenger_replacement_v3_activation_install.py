"""Fixed bootstrap-only installer for replacement v3 public simulation."""

import os
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from importlib import resources

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id, utc_datetime
from .challenger_replacement_install import _post_print_valid, _publish_plist
from .challenger_replacement_install_trust import (
    _close_descriptor, _fixed_empty_event_root_identity, _fixed_python_identity,
    _open_directory, _publish_contract_exact, _read_published_exact,
)
from .challenger_replacement_filesystem_identity import _deserialize_filesystem_identity, _event_root_identity, _serialize_filesystem_identity
from .challenger_replacement_plan import _strict_json_bytes
from .challenger_replacement_preflight import _run, _transcript
from .evidence import artifact_self_hash
from .challenger_replacement_v3_activation_preflight import (
    load_fixed_v3_activation_preflight_bytes,
)
from .challenger_replacement_v3_activation_trust import (
    _DEPENDENCIES,
    _DEPENDENCY_VERSIONS,
    _snapshot_python_paths,
    load_fixed_published_v3_install_contract,
)
from .challenger_replacement_v3_partial_install_recovery import (
    ChallengerReplacementPartialInstallRecoveryError,
    _verify_preserved_partial_install,
    _verify_preserved_partial_install_history,
    load_fixed_published_v3_partial_install_recovery_receipt,
    load_fixed_v3_partial_install_recovery_plan,
)
from .challenger_replacement_events import (
    open_challenger_replacement_event_root,
)
from .challenger_replacement_opportunities import ChallengerReplacementOpportunityState
from .challenger_replacement_plan_v3 import build_challenger_replacement_plan_v3


class ChallengerReplacementV3ActivationInstallError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _binding(value, body, prefix):
    return {
        prefix + "_id": value[prefix + "_id"],
        prefix + "_hash": value[prefix + "_hash"],
        "file_sha256": hashlib.sha256(body).hexdigest(),
    }


def _first_eligible(installed):
    boundary = installed.replace(
        hour=(installed.hour // 4) * 4, minute=0, second=0, microsecond=0
    )
    from datetime import timedelta
    return utc_datetime(boundary + timedelta(hours=4))


def _receipt_semantics(receipt, contract, preflight, recovery, recovery_bytes):
    try:
        installed = datetime.fromisoformat(receipt["installed_at"].replace("Z", "+00:00"))
        observed = datetime.fromisoformat(preflight["observed_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(preflight["expires_at"].replace("Z", "+00:00"))
        print_argv = ["/bin/launchctl", "print", contract["service"]["identity"]]
        bootstrap = ["/bin/launchctl", "bootstrap", "gui/501", contract["paths"]["target_plist"]]
        sequence = [item["argv"] for item in receipt["commands"]]
        exits = [item["exit_code"] for item in receipt["commands"]]
        common = (
            observed <= installed < expires
            and receipt["first_eligible_scheduled_for"] == _first_eligible(installed)
            and receipt["plist"]["path"] == contract["paths"]["target_plist"]
            and receipt["plist"]["mode"] == 0o600
            and receipt["plist"]["link_count"] == 1
            and receipt["recovery_binding"] == _binding(
                recovery, recovery_bytes, "receipt"
            )
            and sequence in ([print_argv, bootstrap], [print_argv, bootstrap, print_argv])
            and exits[0] == 113
        )
        if receipt["status"] == "INSTALLED_WAITING_FOR_FIRST_NATURAL_OPPORTUNITY":
            return common and exits == [113, 0, 0] and receipt["reason_codes"] == []
        return common and receipt["status"] == "INSTALL_STATE_UNKNOWN_FAILED_CLOSED" and (
            (len(exits) == 2 and exits[1] != 0
             and receipt["reason_codes"] == ["INSTALL_BOOTSTRAP_STATE_UNKNOWN"])
            or (len(exits) == 3 and exits[1] == 0 and exits[2] != 0
                and receipt["reason_codes"] == ["INSTALL_POST_PRINT_INVALID"])
        )
    except (IndexError, KeyError, TypeError, ValueError):
        return False


def build_fixed_v3_activation_install_receipt(
    *, contract, contract_bytes, preflight, preflight_bytes, plist_bytes,
    recovery, recovery_bytes, installed_at, plist_record, commands, status,
    reason_codes,
):
    del plist_bytes
    receipt = {
        "$schema": "./challenger-replacement-v3-activation-install-receipt-v1.schema.json",
        "schema_version": "1.0.0", "receipt_id": "", "receipt_hash": "0" * 64,
        "status": status, "installed_at": utc_datetime(installed_at.replace(microsecond=0)),
        "contract_binding": _binding(contract, contract_bytes, "contract"),
        "preflight_binding": _binding(preflight, preflight_bytes, "receipt"),
        "recovery_binding": _binding(recovery, recovery_bytes, "receipt"),
        "snapshot_binding": copy.deepcopy(dict(contract["snapshot"])),
        "event_root_binding": copy.deepcopy(dict(contract["event_root"])),
        "adapter_binding": {
            "release_tag": contract["release"]["tag"],
            "peeled_commit": contract["release"]["peeled_commit"],
            "manifest_version": contract["release"]["manifest_version"],
            "manifest_hash": contract["release"]["manifest_hash"],
            "snapshot_tree_hash": contract["snapshot"]["tree_hash"],
            "module": contract["runtime"]["module"],
        },
        "first_eligible_scheduled_for": _first_eligible(installed_at),
        "plist": _serialize_filesystem_identity(plist_record),
        "commands": copy.deepcopy(list(commands)),
        "authority": {
            "market_request_count": 0,
            "launchctl_read_count": sum(item["argv"][1] == "print" for item in commands),
            "launchctl_mutation_count": sum(item["argv"][1] == "bootstrap" for item in commands),
            "runtime_invocation_count": 0, "state_write_count": 0,
            "credential_count": 0, "account_request_count": 0,
            "broker_request_count": 0, "order_count": 0,
            "fund_movement_count": 0,
        },
        "reason_codes": sorted(set(reason_codes)),
    }
    identity = {k: v for k, v in receipt.items() if k not in ("receipt_id", "receipt_hash")}
    receipt["receipt_id"] = stable_id("challenger_replacement_v3_activation_install", identity)
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    if not _receipt_semantics(
        receipt, contract, preflight, recovery, recovery_bytes
    ):
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_RECEIPT_INVALID"
        )
    return receipt


def load_fixed_v3_activation_install_receipt_bytes(
    data, *, contract, contract_bytes, preflight, preflight_bytes, recovery,
    recovery_bytes,
):
    try:
        value = dict(_strict_json_bytes(data))
        schema = json.loads(resources.files("crypto_quant").joinpath(
            "schemas/challenger-replacement-v3-activation-install-receipt-v1.schema.json"
        ).read_text(encoding="utf-8"))
        identity = {k: v for k, v in value.items() if k not in ("receipt_id", "receipt_hash")}
        if (
            data != canonical_json(value).encode("utf-8")
            or tuple(Draft202012Validator(schema).iter_errors(value))
            or value["contract_binding"] != _binding(contract, contract_bytes, "contract")
            or value["preflight_binding"] != _binding(preflight, preflight_bytes, "receipt")
            or value["recovery_binding"] != _binding(
                recovery, recovery_bytes, "receipt"
            )
            or value["snapshot_binding"] != contract["snapshot"]
            or value["event_root_binding"] != contract["event_root"]
            or value["receipt_id"] != stable_id(
                "challenger_replacement_v3_activation_install", identity
            )
            or value["receipt_hash"] != artifact_self_hash(value, "receipt_hash")
            or not _receipt_semantics(
                value, contract, preflight, recovery, recovery_bytes
            )
        ):
            raise ValueError("identity")
        installed = datetime.fromisoformat(value["installed_at"].replace("Z", "+00:00"))
        rebuilt = build_fixed_v3_activation_install_receipt(
            contract=contract, contract_bytes=contract_bytes,
            preflight=preflight, preflight_bytes=preflight_bytes,
            recovery=recovery, recovery_bytes=recovery_bytes,
            plist_bytes=b"", installed_at=installed,
            plist_record=_deserialize_filesystem_identity(value["plist"]), commands=value["commands"],
            status=value["status"], reason_codes=value["reason_codes"],
        )
        if rebuilt != value:
            raise ValueError("semantics")
        return copy.deepcopy(value)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_RECEIPT_INVALID"
        ) from error


def _now():
    return datetime.now(timezone.utc)


def _load_fixed_contract_inputs():
    contract, contract_bytes, plist_bytes = load_fixed_published_v3_install_contract()
    return contract, contract_bytes, plist_bytes


def _load_fixed_preflight_candidates(contract, contract_bytes):
    binding = {
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "file_sha256": hashlib.sha256(contract_bytes).hexdigest(),
    }
    descriptor = -1
    primary = None
    try:
        descriptor, _ = _open_directory(
            Path(contract["paths"]["preflight_root"]), exact_mode=0o700
        )
        candidates = []
        names = sorted(os.listdir(descriptor))
        if any(not name.endswith(".json") for name in names):
            raise ValueError("names")
        for name in names:
            found = _read_published_exact(descriptor, name)
            if found is None:
                raise ValueError("missing")
            value = load_fixed_v3_activation_preflight_bytes(
                found[0], contract_binding=binding
            )
            if value["status"] == "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE":
                candidates.append((value, found[0]))
        return candidates
    except BaseException as error:
        primary = error
        if isinstance(error, ChallengerReplacementV3ActivationInstallError):
            raise
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_INPUTS_REQUIRED"
        ) from error
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor, primary)


def _select_current_preflight(candidates, now):
    try:
        current = []
        for value, body in candidates:
            observed = datetime.fromisoformat(value["observed_at"].replace("Z", "+00:00"))
            expires = datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00"))
            if observed <= now < expires:
                current.append((value, body))
        if len(current) != 1:
            raise ValueError("current candidate")
        return current[0]
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_INPUTS_REQUIRED"
        ) from error


def _select_bound_preflight(candidates, binding):
    try:
        matched = [
            (value, body) for value, body in candidates
            if _binding(value, body, "receipt") == binding
        ]
        if len(matched) != 1:
            raise ValueError("bound candidate")
        return matched[0]
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_INPUTS_REQUIRED"
        ) from error


def _inputs(contract, contract_bytes, plist_bytes, candidate, recovery):
    value = {
        "contract": contract, "contract_bytes": contract_bytes,
        "preflight": candidate[0], "preflight_bytes": candidate[1],
        "plist_bytes": plist_bytes,
    }
    value.update(recovery)
    return value


def _load_fixed_recovery_inputs(
    contract, contract_bytes, plist_bytes, *, allow_new_target=False,
    historical=False, expected_binding=None,
):
    try:
        plan, plan_bytes = load_fixed_v3_partial_install_recovery_plan()
        if (
            plan["candidate"]["target_plist"]
            != contract["paths"]["target_plist"]
            or plan["candidate"]["recovery_receipt_root"]
            != contract["paths"]["recovery_receipt_root"]
            or plan["candidate"]["release_tag"] != contract["release"]["tag"]
        ):
            raise ValueError("candidate")
        observation = None if historical else _verify_preserved_partial_install(
            plan, allow_new_target=allow_new_target
        )
        preserved = (
            _verify_preserved_partial_install_history(plan)
            if historical else observation["preserved_file_sha256"]
        )
        found = load_fixed_published_v3_partial_install_recovery_receipt(
            plan=plan,
            plan_bytes=plan_bytes,
            contract=contract,
            contract_bytes=contract_bytes,
            candidate_plist_bytes=plist_bytes,
            expected_observation=observation,
            expected_binding=expected_binding,
        )
        if found is None:
            raise ValueError("receipt")
        receipt, receipt_bytes = found
        if (
            not historical and observation != receipt["observation"]
            or preserved != receipt["observation"]["preserved_file_sha256"]
        ):
            raise ValueError("observation")
        return {
            "recovery": receipt,
            "recovery_bytes": receipt_bytes,
        }
    except (KeyError, TypeError, ValueError, ChallengerReplacementPartialInstallRecoveryError) as error:
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_RECOVERY_RECEIPT_REQUIRED"
        ) from error


def _load_fixed_install_inputs():
    contract, contract_bytes, plist_bytes = _load_fixed_contract_inputs()
    candidates = _load_fixed_preflight_candidates(contract, contract_bytes)
    recovery = _load_fixed_recovery_inputs(
        contract, contract_bytes, plist_bytes
    )
    return _inputs(
        contract, contract_bytes, plist_bytes,
        _select_current_preflight(candidates, _now()),
        recovery,
    )


def _target_absent(contract):
    return not os.path.lexists(contract["paths"]["target_plist"])


def _command(argv):
    return _run(argv, __import__("pathlib").Path(__file__).resolve().parents[2])


def _revalidate(inputs, record, *, historical=False):
    contract, contract_bytes, plist_bytes = _load_fixed_contract_inputs()
    candidate = _select_bound_preflight(
        _load_fixed_preflight_candidates(contract, contract_bytes),
        _binding(inputs["preflight"], inputs["preflight_bytes"], "receipt"),
    )
    recovery = _load_fixed_recovery_inputs(
        contract, contract_bytes, plist_bytes, allow_new_target=True,
        historical=historical,
        expected_binding=(
            _binding(inputs["recovery"], inputs["recovery_bytes"], "receipt")
            if historical else None
        ),
    )
    if _inputs(
        contract, contract_bytes, plist_bytes, candidate, recovery
    ) != inputs:
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_SOURCE_CHANGED"
        )
    if _target_absent(contract):
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_TARGET_CHANGED"
        )
    _, replayed = _publish_plist(inputs["contract"], inputs["plist_bytes"])
    if replayed != record:
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_TARGET_CHANGED"
        )
    contract = inputs["contract"]
    if (not historical and _fixed_empty_event_root_identity(contract["paths"])
            != _deserialize_filesystem_identity(contract["event_root"])):
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_EVENT_ROOT_CHANGED"
        )
    observed_python = _fixed_python_identity(
        contract["snapshot"]["root"], package_version="0.78.7",
        dependency_modules=_DEPENDENCIES,
        dependency_versions=_DEPENDENCY_VERSIONS,
        python_paths=_snapshot_python_paths(contract["snapshot"]["root"]),
        import_modules=(
            "crypto_quant.challenger_replacement_v3_installed_runtime",
            "crypto_quant.challenger_replacement_v3_runtime",
        ),
    )
    if observed_python != _deserialize_filesystem_identity(contract["python"]):
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_PYTHON_CHANGED"
        )


def _finish(inputs, record, *pairs, verified=False):
    command_pairs = [pair for pair in pairs if pair is not None]
    bootstrap_ok = len(command_pairs) >= 2 and command_pairs[1][1][0] == 0
    success = bootstrap_ok and verified and len(command_pairs) == 3
    status = (
        "INSTALLED_WAITING_FOR_FIRST_NATURAL_OPPORTUNITY"
        if success else "INSTALL_STATE_UNKNOWN_FAILED_CLOSED"
    )
    reasons = [] if success else [
        "INSTALL_POST_PRINT_INVALID" if bootstrap_ok
        else "INSTALL_BOOTSTRAP_STATE_UNKNOWN"
    ]
    _revalidate(inputs, record, historical=True)
    receipt = build_fixed_v3_activation_install_receipt(
        **inputs, installed_at=_now(), plist_record=record,
        commands=[_transcript(argv, result) for argv, result in command_pairs],
        status=status, reason_codes=reasons,
    )
    outcome, _ = _publish_contract_exact(
        Path(inputs["contract"]["paths"]["install_receipt_root"]),
        receipt["receipt_id"] + ".json", canonical_json(receipt).encode("utf-8"),
    )
    return {"receipt": receipt, "publication_outcome": outcome}


def _load_fixed_successful_install_receipt():
    contract, contract_bytes, plist_bytes = _load_fixed_contract_inputs()
    descriptor = -1
    primary = None
    try:
        descriptor, _ = _open_directory(
            Path(contract["paths"]["install_receipt_root"]),
            exact_mode=0o700,
        )
        names = os.listdir(descriptor)
        if len(names) != 1 or not names[0].endswith(".json"):
            raise ValueError("receipt count")
        found = _read_published_exact(descriptor, names[0])
        if found is None:
            raise ValueError("receipt")
        untrusted = dict(_strict_json_bytes(found[0]))
        candidate = _select_bound_preflight(
            _load_fixed_preflight_candidates(contract, contract_bytes),
            untrusted["preflight_binding"],
        )
        recovery = _load_fixed_recovery_inputs(
            contract, contract_bytes, plist_bytes, historical=True,
            expected_binding=untrusted["recovery_binding"],
        )
        inputs = _inputs(
            contract, contract_bytes, plist_bytes, candidate, recovery
        )
        receipt = load_fixed_v3_activation_install_receipt_bytes(
            found[0], contract=contract, contract_bytes=contract_bytes,
            preflight=candidate[0], preflight_bytes=candidate[1],
            recovery=recovery["recovery"],
            recovery_bytes=recovery["recovery_bytes"],
        )
        replay_contract, replay_contract_bytes, replay_plist_bytes = (
            _load_fixed_contract_inputs()
        )
        replay_candidate = _select_bound_preflight(
            _load_fixed_preflight_candidates(replay_contract, replay_contract_bytes),
            receipt["preflight_binding"],
        )
        replay_recovery = _load_fixed_recovery_inputs(
            replay_contract, replay_contract_bytes, replay_plist_bytes,
            historical=True, expected_binding=receipt["recovery_binding"],
        )
        if (
            receipt["status"] != "INSTALLED_WAITING_FOR_FIRST_NATURAL_OPPORTUNITY"
            or names[0] != receipt["receipt_id"] + ".json"
            or _inputs(
                replay_contract, replay_contract_bytes, replay_plist_bytes,
                replay_candidate,
                replay_recovery,
            ) != inputs
        ):
            raise ValueError("receipt semantics")
        _revalidate(
            inputs, _deserialize_filesystem_identity(receipt["plist"]),
            historical=True,
        )
        return inputs, receipt, found[0]
    except BaseException as error:
        primary = error
        if isinstance(error, ChallengerReplacementV3ActivationInstallError):
            raise
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_RECEIPT_REQUIRED"
        ) from error
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor, primary)


@contextmanager
def open_fixed_v3_installed_sources():
    """Yield receipt-bound state and event-root capabilities only."""

    inputs, _receipt, _body = _load_fixed_successful_install_receipt()
    event = inputs["contract"]["event_root"]
    identity = _event_root_identity(event)
    with open_challenger_replacement_event_root(identity) as event_root:
        yield {
            "event_root": event_root,
            "state": ChallengerReplacementOpportunityState(
                event_root=event_root, plan=build_challenger_replacement_plan_v3(),
                build_identity=inputs["contract"]["deployment"]["build_identity"],
            ),
            "build_identity": copy.deepcopy(
                inputs["contract"]["deployment"]["build_identity"]
            ),
        }


def install_fixed_v3_simulation_launch_agent():
    inputs = _load_fixed_install_inputs()
    contract, preflight = inputs["contract"], inputs["preflight"]
    now = _now()
    try:
        observed = datetime.fromisoformat(preflight["observed_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(preflight["expires_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_PREFLIGHT_EXPIRED"
        ) from error
    if preflight.get("status") != "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE" or not observed <= now < expires:
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_PREFLIGHT_EXPIRED"
        )
    identity = contract["service"]["identity"]
    target = contract["paths"]["target_plist"]
    print_argv = ("/bin/launchctl", "print", identity)
    first = _command(print_argv)
    if first[0] != 113 or not _target_absent(contract):
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_EXISTING_STATE_CONFLICT"
        )
    outcome, record = _publish_plist(contract, inputs["plist_bytes"])
    if outcome != "PUBLISHED":
        raise ChallengerReplacementV3ActivationInstallError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_EXISTING_STATE_CONFLICT"
        )
    _revalidate(inputs, record)
    bootstrap_argv = ("/bin/launchctl", "bootstrap", "gui/501", target)
    try:
        bootstrap = _command(bootstrap_argv)
    except BaseException:
        bootstrap = (255, b"", b"TRANSPORT_STATE_UNKNOWN")
    if bootstrap[0] != 0:
        return _finish(inputs, record, (print_argv, first),
                       (bootstrap_argv, bootstrap), None)
    try:
        post = _command(print_argv)
    except BaseException:
        post = (255, b"", b"TRANSPORT_STATE_UNKNOWN")
    return _finish(
        inputs, record, (print_argv, first), (bootstrap_argv, bootstrap),
        (print_argv, post), verified=_post_print_valid(contract, post),
    )
