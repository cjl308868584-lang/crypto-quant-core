"""Minimal fixed preflight for the credential-free v3 simulation install."""

import copy
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id, utc_datetime
from .challenger_replacement_plan import _strict_json_bytes
from .evidence import artifact_self_hash
from .challenger_replacement_install_trust import _publish_contract_exact
from .challenger_replacement_preflight import (
    _disk, _machine, _run, _time_probe, _transcript,
)
from .challenger_replacement_v3_activation_trust import (
    activation_paths,
    load_fixed_published_v3_install_contract,
)


_MACHINE = {
    "system": "Darwin", "machine": "arm64", "uid": 501,
    "home": "/Users/chenm4", "timezone": "Asia/Shanghai",
}
_CLOCK = "https://data-api.binance.vision/api/v3/time"
_REPOSITORY = Path(__file__).resolve().parents[2]
_COMMANDS = (
    ("git", "remote", "get-url", "origin"),
    ("git", "rev-parse", "HEAD"),
    ("git", "rev-parse", "origin/main"),
    ("git", "rev-parse", "v0.78.0^{}"),
    ("git", "status", "--porcelain=v1", "--untracked-files=all"),
    ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-forward"),
    ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-replacement-v1"),
    ("/usr/bin/pmset", "-g", "custom"),
)


class ChallengerReplacementV3ActivationPreflightError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _window(value):
    boundary = value.replace(
        hour=(value.hour // 4) * 4, minute=0, second=0, microsecond=0
    )
    return boundary + timedelta(minutes=10) <= value <= boundary + timedelta(minutes=30)


def build_fixed_v3_activation_preflight(
    *, contract_binding, machine, release_replayed, paths_verified,
    power_safe, disk, clock, credential_count, commands, observed_at,
):
    supported = machine == _MACHINE
    commands_valid = (
        tuple(tuple(item.get("argv", ())) for item in commands) == _COMMANDS
        and all(
            set(item) == {"argv", "exit_code", "stdout_sha256", "stderr_sha256"}
            and isinstance(item["exit_code"], int)
            and all(isinstance(item[key], str) and len(item[key]) == 64
                    for key in ("stdout_sha256", "stderr_sha256"))
            for item in commands
        )
    )
    reasons = []
    if supported:
        checks = (
            (not release_replayed, "PREFLIGHT_RELEASE_IDENTITY_INVALID"),
            (not paths_verified, "PREFLIGHT_PATH_BOUNDARY_INVALID"),
            (not power_safe, "PREFLIGHT_POWER_UNSAFE"),
            (not commands_valid, "PREFLIGHT_COMMAND_EVIDENCE_INVALID"),
            (disk.get("free_bytes", 0) < 10_000_000_000
             or disk.get("free_inodes", 0) < 100_000,
             "PREFLIGHT_DISK_INSUFFICIENT"),
            (credential_count != 0, "PREFLIGHT_CREDENTIAL_BOUNDARY_PRESENT"),
            (clock.get("endpoint") != _CLOCK
             or clock.get("request_count") != (0 if credential_count else 3)
             or (not credential_count and clock.get("trust_hash") == "0" * 64),
             "PREFLIGHT_CLOCK_INVALID"),
            (not _window(observed_at), "PREFLIGHT_INSTALL_WINDOW_UNSAFE"),
        )
        reasons = [reason for failed, reason in checks if failed]
    elif any((release_replayed, paths_verified, power_safe, commands,
              credential_count, clock.get("request_count", 0))):
        raise ChallengerReplacementV3ActivationPreflightError(
            "CHALLENGER_REPLACEMENT_V3_PREFLIGHT_INVALID"
        )
    status = (
        "PREFLIGHT_PLATFORM_UNSUPPORTED" if not supported
        else "PREFLIGHT_FAILED_CLOSED" if reasons
        else "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE"
    )
    receipt = {
        "$schema": "./challenger-replacement-v3-activation-preflight-v1.schema.json",
        "schema_version": "1.0.0", "receipt_id": "", "receipt_hash": "0" * 64,
        "status": status, "observed_at": utc_datetime(observed_at),
        "expires_at": utc_datetime(observed_at + timedelta(minutes=30)),
        "contract_binding": copy.deepcopy(dict(contract_binding)),
        "machine": copy.deepcopy(dict(machine)),
        "release_replayed": bool(release_replayed),
        "paths_verified": bool(paths_verified), "power_safe": bool(power_safe),
        "disk": copy.deepcopy(dict(disk)), "clock": copy.deepcopy(dict(clock)),
        "commands": copy.deepcopy(list(commands)),
        "authority": {
            "market_request_count": clock.get("request_count", 0),
            "launchctl_read_count": 2 if supported else 0,
            "launchctl_mutation_count": 0, "runtime_invocation_count": 0,
            "state_write_count": 0, "credential_count": credential_count,
            "account_request_count": 0, "broker_request_count": 0,
            "order_count": 0, "fund_movement_count": 0,
        },
        "reason_codes": sorted(set(reasons)),
    }
    identity = {k: v for k, v in receipt.items() if k not in ("receipt_id", "receipt_hash")}
    receipt["receipt_id"] = stable_id("challenger_replacement_v3_activation_preflight", identity)
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    return receipt


def load_fixed_v3_activation_preflight_bytes(data, *, contract_binding):
    try:
        value = dict(_strict_json_bytes(data))
        schema = json.loads(resources.files("crypto_quant").joinpath(
            "schemas/challenger-replacement-v3-activation-preflight-v1.schema.json"
        ).read_text(encoding="utf-8"))
        identity = {k: v for k, v in value.items() if k not in ("receipt_id", "receipt_hash")}
        if (
            data != canonical_json(value).encode("utf-8")
            or tuple(Draft202012Validator(schema).iter_errors(value))
            or value["contract_binding"] != dict(contract_binding)
            or value["receipt_id"] != stable_id(
                "challenger_replacement_v3_activation_preflight", identity
            )
            or value["receipt_hash"] != artifact_self_hash(value, "receipt_hash")
        ):
            raise ValueError("identity")
        observed = datetime.fromisoformat(value["observed_at"].replace("Z", "+00:00"))
        rebuilt = build_fixed_v3_activation_preflight(
            contract_binding=contract_binding, machine=value["machine"],
            release_replayed=value["release_replayed"],
            paths_verified=value["paths_verified"], power_safe=value["power_safe"],
            disk=value["disk"], clock=value["clock"],
            credential_count=value["authority"]["credential_count"],
            commands=value["commands"], observed_at=observed,
        )
        if rebuilt != value:
            raise ValueError("semantics")
        return copy.deepcopy(value)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ChallengerReplacementV3ActivationPreflightError(
            "CHALLENGER_REPLACEMENT_V3_PREFLIGHT_INVALID"
        ) from error


def _now():
    return datetime.now(timezone.utc)


def _run_commands():
    return [_run(argv, _REPOSITORY) for argv in _COMMANDS]


def _fixed_checks(contract, results):
    try:
        text = [item[1].decode("utf-8", "strict").strip() for item in results]
        release = (
            len(results) == len(_COMMANDS)
            and all(results[index][0] == 0 for index in range(5))
            and text[0] == "https://github.com/cjl308868584-lang/crypto-quant-core.git"
            and text[1] == text[2] == text[3] == contract["release"]["peeled_commit"]
            and text[4] == ""
        )
        paths = contract["paths"]
        entry = os.lstat(paths["event_root"])
        boundary = (
            (entry.st_dev, entry.st_ino, entry.st_uid)
            == (contract["event_root"]["device"], contract["event_root"]["inode"], 501)
            and not os.listdir(paths["event_root"])
            and not any(os.path.lexists(paths[key]) for key in (
                "target_plist", "stdout", "stderr",
            ))
            and results[5][0] != 0 and results[6][0] != 0
        )
        power = results[7][0] == 0 and b" sleep 0" in results[7][1]
        return release, boundary, power
    except (IndexError, KeyError, OSError, TypeError, UnicodeError):
        return False, False, False


def _credential_count():
    fragments = ("binance_api", "api_secret", "exchange_api", "private_key")
    paths = activation_paths()
    files = (
        Path.home() / ".config/binance/credentials.json",
        Path.home() / ".binance/credentials.json",
        Path(paths["runtime_root"]) / "credentials",
    )
    return sum(any(part in name.lower() for part in fragments) for name in os.environ) + sum(
        os.path.lexists(path) for path in files
    )


def _clock():
    return {"endpoint": _CLOCK, **_time_probe()}


def collect_fixed_v3_activation_preflight():
    contract, contract_bytes, _plist = load_fixed_published_v3_install_contract()
    binding = {
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "file_sha256": hashlib.sha256(contract_bytes).hexdigest(),
    }
    machine = _machine()
    if machine != _MACHINE:
        return build_fixed_v3_activation_preflight(
            contract_binding=binding, machine=machine, release_replayed=False,
            paths_verified=False, power_safe=False,
            disk={"free_bytes": 0, "free_inodes": 0},
            clock={"endpoint": _CLOCK, "request_count": 0, "trust_hash": "0" * 64},
            credential_count=0, commands=[], observed_at=_now(),
        )
    results = _run_commands()
    release, paths, power = _fixed_checks(contract, results)
    credentials = _credential_count()
    clock = ({"endpoint": _CLOCK, "request_count": 0, "trust_hash": "0" * 64}
             if credentials else _clock())
    return build_fixed_v3_activation_preflight(
        contract_binding=binding, machine=machine, release_replayed=release,
        paths_verified=paths, power_safe=power, disk=_disk(), clock=clock,
        credential_count=credentials,
        commands=[_transcript(argv, result) for argv, result in zip(_COMMANDS, results)],
        observed_at=_now(),
    )


def publish_fixed_v3_activation_preflight():
    receipt = collect_fixed_v3_activation_preflight()
    body = canonical_json(receipt).encode("utf-8")
    outcome, _ = _publish_contract_exact(
        Path(activation_paths()["preflight_root"]), receipt["receipt_id"] + ".json", body
    )
    return {"receipt": receipt, "publication_outcome": outcome}
