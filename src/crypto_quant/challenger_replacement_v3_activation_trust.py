"""Fixed, credential-free release candidate for replacement v3 activation."""

import copy
import hashlib
import json
from pathlib import Path

from .canonical import business_hash
from .challenger_replacement_plan import _strict_json_bytes


_REPOSITORY = Path(__file__).resolve().parents[2]
_DEPLOYMENT_PATH = Path(
    "artifacts/challenger-replacement/"
    "challenger-replacement-v3-deployment-v0.76.0.json"
)
_PREDECESSOR = {
    "tag": "v0.77.0",
    "peeled_commit": "39a973d51bdc8fc957a65052f4bb5f310a1f72c3",
}
_RELEASE = {"tag": "v0.78.0", "package_version": "0.78.0"}
_THIN_FILES = (
    "src/crypto_quant/challenger_replacement_v3_activation_trust.py",
    "src/crypto_quant/challenger_replacement_v3_activation_trust_cli.py",
    "src/crypto_quant/challenger_replacement_v3_installed_runtime.py",
    "src/crypto_quant/schemas/challenger-replacement-v3-install-contract-v1.schema.json",
    "src/crypto_quant/schemas/challenger-replacement-v3-activation-preflight-v1.schema.json",
    "src/crypto_quant/schemas/challenger-replacement-v3-activation-install-receipt-v1.schema.json",
)
_FORBIDDEN = (
    "binance_private", "private_protocol", "private_runtime",
    "canary_controller", "credential_envelope",
)


class ChallengerReplacementV3ActivationTrustError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="CHALLENGER_REPLACEMENT_V3_ACTIVATION_CANDIDATE_INVALID"):
    raise ChallengerReplacementV3ActivationTrustError(reason)


def _sha(path):
    try:
        return hashlib.sha256((_REPOSITORY / path).read_bytes()).hexdigest()
    except OSError as error:
        raise ChallengerReplacementV3ActivationTrustError(
            "CHALLENGER_REPLACEMENT_V3_ACTIVATION_SOURCE_INVALID"
        ) from error


def build_fixed_v3_activation_candidate():
    """Build the exact local candidate without touching the production root."""

    try:
        raw = (_REPOSITORY / _DEPLOYMENT_PATH).read_bytes()
        deployment = dict(_strict_json_bytes(raw))
        inventory = dict(deployment["executable_core_identity"])
        inventory[str(_DEPLOYMENT_PATH)] = hashlib.sha256(raw).hexdigest()
        for path in _THIN_FILES:
            inventory[path] = _sha(path)
        if (
            not 0 < len(inventory) <= 256
            or any(any(token in name.lower() for token in _FORBIDDEN)
                   for name in inventory)
        ):
            _invalid()
        candidate = {
            "schema_version": "1.0.0",
            "release": copy.deepcopy(_RELEASE),
            "predecessor_release": copy.deepcopy(_PREDECESSOR),
            "deployment": {
                "release_tag": "v0.76.0",
                "file": str(_DEPLOYMENT_PATH),
                "file_sha256": hashlib.sha256(raw).hexdigest(),
                "deployment_id": deployment["deployment_id"],
                "deployment_hash": deployment["deployment_hash"],
            },
            "runtime_module": (
                "crypto_quant.challenger_replacement_v3_installed_runtime"
            ),
            "snapshot_inventory": dict(sorted(inventory.items())),
            "snapshot_inventory_hash": business_hash(dict(sorted(inventory.items()))),
            "authority": {
                "production_activation": False,
                "credentials_allowed": False,
                "account_requests_allowed": False,
                "real_orders_allowed": False,
                "fund_movement_allowed": False,
            },
            "status": "V3_SIMULATION_ACTIVATION_CANDIDATE_NOT_INSTALLED",
        }
        return candidate
    except ChallengerReplacementV3ActivationTrustError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementV3ActivationTrustError(
            "CHALLENGER_REPLACEMENT_V3_ACTIVATION_CANDIDATE_INVALID"
        ) from error


def load_fixed_v3_activation_candidate(data):
    """Strictly replay canonical candidate bytes against the local release tree."""

    try:
        value = dict(_strict_json_bytes(data))
        expected = build_fixed_v3_activation_candidate()
        from .canonical import canonical_json
        if data != canonical_json(value).encode("utf-8") or value != expected:
            _invalid()
        return copy.deepcopy(value)
    except ChallengerReplacementV3ActivationTrustError:
        raise
    except (TypeError, ValueError) as error:
        raise ChallengerReplacementV3ActivationTrustError(
            "CHALLENGER_REPLACEMENT_V3_ACTIVATION_CANDIDATE_INVALID"
        ) from error


def render_fixed_v3_activation_candidate():
    """Return the fixed candidate; publication is composed by the installer tasks."""

    return build_fixed_v3_activation_candidate()
