"""Fixed preflight receipt for the replacement Challenger installer."""
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
from .challenger_replacement_install_trust import (
    _load_fixed_published_contract,
    _publish_contract_exact,
    replacement_install_paths,
)
from .challenger_replacement_preflight import (
    _disk,
    _machine,
    _run,
    _time_probe,
    _transcript,
)


_SUPPORTED_MACHINE = {
    "system": "Darwin", "machine": "arm64", "uid": 501,
    "home": "/Users/chenm4", "timezone": "Asia/Shanghai",
}
_CLOCK_ENDPOINT = "https://data-api.binance.vision/api/v3/time"
_REPOSITORY = Path(__file__).resolve().parents[2]
_COMMANDS = (
    ("git", "remote", "get-url", "origin"),
    ("git", "rev-parse", "HEAD"),
    ("git", "rev-parse", "origin/main"),
    ("git", "rev-parse", "v0.68.0^{}"),
    ("git", "status", "--porcelain=v1", "--untracked-files=all"),
    ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-forward"),
    ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-replacement-v1"),
    ("/usr/bin/pmset", "-g", "custom"),
)
_CREDENTIAL_NAMES = (
    "BINANCE_API_KEY", "BINANCE_API_SECRET",
    "EXCHANGE_API_KEY", "EXCHANGE_API_SECRET",
)


class ReplacementInstallPreflightError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _binding(contract, file_sha256):
    return {
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "file_sha256": file_sha256,
    }


def _schema():
    path = "schemas/challenger-replacement-install-preflight-v1.schema.json"
    return json.loads(resources.files("crypto_quant").joinpath(path).read_text())


def build_replacement_install_preflight_receipt(
    *, contract, contract_file_sha256, machine, release_replayed,
    paths_verified, power_safe, disk, clock, credential_count, commands,
    observed_at,
):
    supported = machine == _SUPPORTED_MACHINE
    if not supported and (commands or clock.get("request_count") or credential_count):
        raise ReplacementInstallPreflightError(
            "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_INVALID")
    if not supported:
        reasons = ["PREFLIGHT_PLATFORM_UNSUPPORTED"]
    else:
        checks = (
            (not release_replayed, "PREFLIGHT_RELEASE_IDENTITY_INVALID"),
            (not paths_verified, "PREFLIGHT_PATH_BOUNDARY_INVALID"),
            (not power_safe, "PREFLIGHT_POWER_UNSAFE"),
            (tuple(tuple(item.get("argv", ())) for item in commands) != _COMMANDS,
             "PREFLIGHT_COMMAND_EVIDENCE_INVALID"),
            (disk.get("free_bytes", 0) < 10_000_000_000
             or disk.get("free_inodes", 0) < 100_000,
             "PREFLIGHT_DISK_INSUFFICIENT"),
            (bool(credential_count), "PREFLIGHT_CREDENTIAL_BOUNDARY_PRESENT"),
            (clock.get("endpoint") != _CLOCK_ENDPOINT
             or clock.get("request_count") != (0 if credential_count else 3)
             or (not credential_count and clock.get("trust_hash") == "0" * 64),
             "PREFLIGHT_CLOCK_INVALID"),
        )
        reasons = [reason for failed, reason in checks if failed]
    status = (
        "PREFLIGHT_PLATFORM_UNSUPPORTED"
        if not supported
        else "PREFLIGHT_FAILED_CLOSED"
        if reasons
        else "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE"
    )
    observed = utc_datetime(observed_at)
    receipt = {
        "$schema": "./challenger-replacement-install-preflight-v1.schema.json",
        "schema_version": "1.0.0",
        "receipt_id": "challenger_replacement_install_preflight_" + "0" * 64,
        "receipt_hash": "0" * 64,
        "status": status,
        "observed_at": observed,
        "expires_at": utc_datetime(observed_at + timedelta(minutes=30)),
        "contract_binding": _binding(contract, contract_file_sha256),
        "machine": dict(machine),
        "release_replayed": bool(release_replayed),
        "paths_verified": bool(paths_verified),
        "power_safe": bool(power_safe),
        "disk": dict(disk),
        "clock": dict(clock),
        "commands": list(commands),
        "authority": {
            "github_request_count": 0,
            "market_request_count": clock.get("request_count", 0),
            "launchctl_read_count": 0 if not supported else 2,
            "launchctl_mutation_count": 0,
            "runtime_invocation_count": 0,
            "state_write_count": 0,
            "credential_count": credential_count,
            "broker_request_count": 0,
            "order_count": 0,
        },
        "reason_codes": sorted(set(reasons)),
    }
    identity = {
        key: value for key, value in receipt.items()
        if key not in ("receipt_id", "receipt_hash")
    }
    receipt["receipt_id"] = stable_id(
        "challenger_replacement_install_preflight", identity
    )
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    if tuple(Draft202012Validator(_schema()).iter_errors(receipt)):
        raise ReplacementInstallPreflightError(
            "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_INVALID")
    return receipt


def load_replacement_install_preflight_bytes(
    data, *, contract, contract_file_sha256
):
    try:
        receipt = dict(_strict_json_bytes(data))
        schema = _schema()
        identity = {
            key: value for key, value in receipt.items()
            if key not in ("receipt_id", "receipt_hash")
        }
        if (
            data != canonical_json(receipt).encode("utf-8")
            or tuple(Draft202012Validator(schema).iter_errors(receipt))
            or receipt["contract_binding"]
            != _binding(contract, contract_file_sha256)
            or receipt["receipt_id"]
            != stable_id("challenger_replacement_install_preflight", identity)
            or receipt["receipt_hash"]
            != artifact_self_hash(receipt, "receipt_hash")
        ):
            raise ValueError("invalid preflight")
        observed = datetime.fromisoformat(
            receipt["observed_at"].replace("Z", "+00:00")
        )
        rebuilt = build_replacement_install_preflight_receipt(
            contract=contract,
            contract_file_sha256=contract_file_sha256,
            machine=receipt["machine"],
            release_replayed=receipt["release_replayed"],
            paths_verified=receipt["paths_verified"],
            power_safe=receipt["power_safe"],
            disk=receipt["disk"], clock=receipt["clock"],
            credential_count=receipt["authority"]["credential_count"],
            commands=receipt["commands"], observed_at=observed,
        )
        if rebuilt != receipt:
            raise ValueError("preflight semantics")
        return receipt
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ReplacementInstallPreflightError(
            "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_INVALID"
        ) from error


def _now():
    return datetime.now(timezone.utc)


def _run_fixed_commands():
    results = [_run(argv, _REPOSITORY) for argv in _COMMANDS]
    for _, stdout, stderr in results:
        try:
            stdout.decode("utf-8", "strict")
            stderr.decode("utf-8", "strict")
        except UnicodeError as error:
            raise ReplacementInstallPreflightError(
                "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_COMMAND_FAILED"
            ) from error
    return results


def _load_fixed_contract():
    contract, contract_bytes, _ = _load_fixed_published_contract()
    return contract, contract_bytes


def _fixed_checks(contract, results):
    text = [item[1].decode("utf-8").strip() for item in results]
    expected = contract["candidate_release"]["peeled_commit"]
    release = (
        all(results[index][0] == 0 for index in range(5))
        and text[0] == "https://github.com/cjl308868584-lang/crypto-quant-core.git"
        and text[1] == text[2] == text[3] == expected and text[4] == ""
    )
    paths = contract["paths"]
    absent = all(not os.path.lexists(paths[key]) for key in (
        "target_plist", "event_root", "stdout", "stderr", "start_receipt_root",
    ))
    return release, absent and results[5][0] != 0 and results[6][0] != 0


def _power_safe(results):
    return results[7][0] == 0 and b" sleep 0" in results[7][1]


def _credential_count(contract_bytes):
    paths = (
        Path.home() / ".config/binance/credentials.json",
        Path.home() / ".binance/credentials.json",
        Path(replacement_install_paths()["runtime_root"]) / "credentials",
    )
    return (
        sum(name in os.environ for name in _CREDENTIAL_NAMES)
        + sum(os.path.lexists(path) for path in paths)
        + sum(name.encode() in contract_bytes for name in _CREDENTIAL_NAMES)
    )


def _clock():
    clock = _time_probe()
    return {"endpoint": _CLOCK_ENDPOINT, **clock}


def observe_fixed_replacement_install_preflight():
    contract, contract_bytes = _load_fixed_contract()
    machine = _machine()
    file_hash = hashlib.sha256(contract_bytes).hexdigest()
    if machine != _SUPPORTED_MACHINE:
        return build_replacement_install_preflight_receipt(
            contract=contract, contract_file_sha256=file_hash, machine=machine,
            release_replayed=False, paths_verified=False, power_safe=False,
            disk={"free_bytes": 0, "free_inodes": 0},
            clock={"endpoint": _CLOCK_ENDPOINT, "request_count": 0,
                   "trust_hash": "0" * 64},
            credential_count=0, commands=[], observed_at=_now(),
        )
    results = _run_fixed_commands()
    release, paths = _fixed_checks(contract, results)
    credentials = _credential_count(contract_bytes)
    clock = ({"endpoint": _CLOCK_ENDPOINT, "request_count": 0,
              "trust_hash": "0" * 64} if credentials else _clock())
    return build_replacement_install_preflight_receipt(
        contract=contract, contract_file_sha256=file_hash, machine=machine,
        release_replayed=release, paths_verified=paths,
        power_safe=_power_safe(results), disk=_disk(), clock=clock,
        credential_count=credentials,
        commands=[_transcript(argv, result)
                  for argv, result in zip(_COMMANDS, results)],
        observed_at=_now(),
    )


def _ensure_preflight_root():
    return Path(replacement_install_paths()["preflight_root"])


def publish_fixed_replacement_install_preflight():
    receipt = observe_fixed_replacement_install_preflight()
    body = canonical_json(receipt).encode("utf-8")
    root = _ensure_preflight_root()
    outcome, _ = _publish_contract_exact(
        root, receipt["receipt_id"] + ".json", body
    )
    return {"receipt": receipt, "publication_outcome": outcome}
