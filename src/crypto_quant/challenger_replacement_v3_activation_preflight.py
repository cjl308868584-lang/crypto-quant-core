"""Minimal fixed preflight for the credential-free v3 simulation install."""

import copy
from datetime import datetime, timedelta, timezone

from .canonical import canonical_json, stable_id, utc_datetime
from .challenger_replacement_plan import _strict_json_bytes
from .evidence import artifact_self_hash


_MACHINE = {
    "system": "Darwin", "machine": "arm64", "uid": 501,
    "home": "/Users/chenm4", "timezone": "Asia/Shanghai",
}
_CLOCK = "https://data-api.binance.vision/api/v3/time"


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
    power_safe, disk, clock, credential_count, commands_verified, observed_at,
):
    supported = machine == _MACHINE
    reasons = []
    if supported:
        checks = (
            (not release_replayed, "PREFLIGHT_RELEASE_IDENTITY_INVALID"),
            (not paths_verified, "PREFLIGHT_PATH_BOUNDARY_INVALID"),
            (not power_safe, "PREFLIGHT_POWER_UNSAFE"),
            (not commands_verified, "PREFLIGHT_COMMAND_EVIDENCE_INVALID"),
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
    elif any((release_replayed, paths_verified, power_safe, commands_verified,
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
        "commands_verified": bool(commands_verified),
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
        identity = {k: v for k, v in value.items() if k not in ("receipt_id", "receipt_hash")}
        if (
            data != canonical_json(value).encode("utf-8")
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
            commands_verified=value["commands_verified"], observed_at=observed,
        )
        if rebuilt != value:
            raise ValueError("semantics")
        return copy.deepcopy(value)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ChallengerReplacementV3ActivationPreflightError(
            "CHALLENGER_REPLACEMENT_V3_PREFLIGHT_INVALID"
        ) from error
