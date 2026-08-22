"""Fixed, code-only trust contracts for replacement Challenger installation."""

import json
from importlib import resources
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id
from .challenger_replacement_plan import _strict_json_bytes
from .evidence import artifact_self_hash


_RUNTIME_ROOT = (
    "/Users/chenm4/Library/Application Support/CryptoQuant/"
    "challenger-replacement-v1"
)
_TARGET_PLIST = (
    "/Users/chenm4/Library/LaunchAgents/"
    "local.crypto-quant.challenger-replacement-v1.plist"
)

V067_FOUNDATION = MappingProxyType(
    {
        "release_tag": "v0.67.0",
        "tag_object": "7c65c0a34cf37f4d46ed3cdd2a0278657aa3e8c5",
        "peeled_commit": "ca022edccdcbb2d28b1ea25002e5f19512795e3e",
        "package_version": "0.67.0",
        "manifest_version": "1.61.0",
        "manifest_hash": (
            "2b72a470a2f210461a3a6753fd3d603fee9b90df76e825deea3b9bde61a26110"
        ),
        "main_ci_run": 32572208544,
    }
)


class ReplacementInstallTrustError(ValueError):
    """A fixed fail-closed replacement installation trust error."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def replacement_install_paths() -> Mapping[str, str]:
    """Return the only production paths authorized by the frozen contract."""

    deployment = _RUNTIME_ROOT + "/deployment"
    return {
        "runtime_root": _RUNTIME_ROOT,
        "deployment_root": deployment,
        "contract": deployment
        + "/challenger-replacement-install-contract-v1.json",
        "preflight_root": deployment + "/preflight-receipts",
        "install_receipt_root": deployment + "/install-receipts",
        "start_receipt_root": _RUNTIME_ROOT + "/evidence/start-receipts",
        "event_root": _RUNTIME_ROOT
        + "/state/challenger-replacement-events-v1",
        "stdout": _RUNTIME_ROOT + "/log/challenger-replacement.stdout.log",
        "stderr": _RUNTIME_ROOT + "/log/challenger-replacement.stderr.log",
        "target_plist": _TARGET_PLIST,
    }


def _contract_schema() -> Mapping[str, Any]:
    return json.loads(
        resources.files("crypto_quant")
        .joinpath("schemas/challenger-replacement-install-contract-v1.schema.json")
        .read_text(encoding="utf-8")
    )


def load_replacement_install_contract_bytes(data: bytes) -> Mapping[str, Any]:
    """Load canonical contract bytes without touching any production path."""

    try:
        contract = dict(_strict_json_bytes(data))
        if data != canonical_json(contract).encode("utf-8"):
            raise ValueError("non-canonical contract")
        if tuple(Draft202012Validator(_contract_schema()).iter_errors(contract)):
            raise ValueError("contract schema")
        identity = {
            key: value
            for key, value in contract.items()
            if key not in ("contract_id", "contract_hash")
        }
        if contract["contract_id"] != stable_id(
            "challenger_replacement_install_contract", identity
        ):
            raise ValueError("contract id")
        if contract["contract_hash"] != artifact_self_hash(
            contract, "contract_hash"
        ):
            raise ValueError("contract hash")
        if contract["predecessor_release"] != dict(V067_FOUNDATION):
            raise ValueError("predecessor")
        if contract["paths"] != replacement_install_paths():
            raise ValueError("paths")
        if contract["authority"] != {
            "production_activation": False,
            "runtime_install_authorized": True,
            "replacement_start_authorized": False,
            "real_orders_allowed": False,
        }:
            raise ValueError("authority")
        if contract["schedule"] != [
            {"hour": hour, "minute": 2} for hour in (0, 4, 8, 12, 16, 20)
        ]:
            raise ValueError("schedule")
        return contract
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ReplacementInstallTrustError):
            raise
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_INVALID"
        ) from error
