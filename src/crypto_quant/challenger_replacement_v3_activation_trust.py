"""Fixed, credential-free release candidate for replacement v3 activation."""

import copy
import hashlib
import json
import plistlib
from pathlib import Path

from .canonical import business_hash, canonical_json, stable_id
from .challenger_replacement_plan import _strict_json_bytes
from .evidence import artifact_self_hash
from .challenger_replacement_install_trust import (
    _ensure_fixed_snapshot_directories,
    _fixed_empty_event_root_identity,
    _fixed_python_identity,
    _publish_contract_exact,
    _publish_snapshot_from_inventory,
    _run_fixed_command,
    replacement_install_paths,
)


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


def activation_paths():
    paths = dict(replacement_install_paths())
    paths.update({
        "contract": paths["deployment_root"]
        + "/challenger-replacement-v3-install-contract-v1.json",
        "stdout": paths["runtime_root"]
        + "/log/challenger-replacement-v3.stdout.log",
        "stderr": paths["runtime_root"]
        + "/log/challenger-replacement-v3.stderr.log",
    })
    return paths


def _released_identity():
    """Require exact clean v0.78 annotated release identity."""

    try:
        manifest_path = _REPOSITORY / "config/evaluator-build-manifest-v1.json"
        body = manifest_path.read_bytes()
        manifest = dict(_strict_json_bytes(body))
        if (
            manifest["package_version"] != "0.78.0"
            or manifest["manifest_version"] != "1.72.0"
            or manifest["manifest_hash"]
            != artifact_self_hash(manifest, "manifest_hash")
        ):
            raise ValueError("manifest")
        commands = (
            ("git", "rev-parse", "HEAD"),
            ("git", "rev-parse", "origin/main"),
            ("git", "rev-parse", "v0.78.0^{}"),
            ("git", "rev-parse", "v0.78.0"),
            ("git", "cat-file", "-t", "v0.78.0"),
            ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        )
        values = [
            _run_fixed_command(argv, cwd=_REPOSITORY)[0].decode("ascii").strip()
            for argv in commands
        ]
        if values[0] != values[1] or values[0] != values[2] or values[4] != "tag" or values[5]:
            raise ValueError("git")
        return {
            "tag": "v0.78.0", "peeled_commit": values[0],
            "tag_object": values[3],
            "manifest_version": manifest["manifest_version"],
            "manifest_hash": manifest["manifest_hash"],
            "manifest_file_sha256": hashlib.sha256(body).hexdigest(),
        }
    except (KeyError, OSError, TypeError, UnicodeError, ValueError) as error:
        raise ChallengerReplacementV3ActivationTrustError(
            "CHALLENGER_REPLACEMENT_V3_RELEASE_IDENTITY_INVALID"
        ) from error


def _plist(contract):
    paths = contract["paths"]
    payload = {
        "Label": contract["service"]["label"],
        "ProgramArguments": contract["runtime"]["program_arguments"],
        "WorkingDirectory": contract["snapshot"]["root"],
        "StandardOutPath": paths["stdout"],
        "StandardErrorPath": paths["stderr"],
        "RunAtLoad": False, "KeepAlive": False,
        "ProcessType": "Background", "Umask": 0o077,
        "EnvironmentVariables": contract["runtime"]["environment"],
        "StartCalendarInterval": [
            {"Hour": item["hour"], "Minute": item["minute"]}
            for item in contract["schedule"]
        ],
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)


def _contract(candidate, release, snapshot, event, python):
    paths = activation_paths()
    runtime = {
        "module": "crypto_quant.challenger_replacement_v3_installed_runtime",
        "program_arguments": [
            python["path"], "-m",
            "crypto_quant.challenger_replacement_v3_installed_runtime",
        ],
        "environment": {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": snapshot["root"] + "/src",
        },
    }
    value = {
        "$schema": "./challenger-replacement-v3-install-contract-v1.schema.json",
        "schema_version": "1.0.0", "contract_id": "", "contract_hash": "0" * 64,
        "release": dict(release), "predecessor_release": dict(_PREDECESSOR),
        "deployment": dict(candidate["deployment"]),
        "snapshot": {key: snapshot[key] for key in (
            "root", "tree_hash", "file_count", "total_size_bytes",
            "root_device", "root_inode",
        )},
        "event_root": dict(event), "python": dict(python),
        "paths": paths,
        "service": {"label": "local.crypto-quant.challenger-replacement-v1",
                    "identity": "gui/501/local.crypto-quant.challenger-replacement-v1"},
        "runtime": runtime,
        "schedule": [{"hour": hour, "minute": 2} for hour in (0, 4, 8, 12, 16, 20)],
        "plist": {"path": paths["candidate_plist"], "file_sha256": "0" * 64},
        "authority": {
            "production_activation": False, "runtime_install_authorized": True,
            "replacement_start_authorized": False, "credentials_allowed": False,
            "account_requests_allowed": False, "real_orders_allowed": False,
            "fund_movement_allowed": False,
        },
        "status": "V3_SIMULATION_INSTALL_CONTRACT_VERIFIED_NOT_INSTALLED",
    }
    value["plist"]["file_sha256"] = hashlib.sha256(_plist(value)).hexdigest()
    identity = {k: v for k, v in value.items() if k not in ("contract_id", "contract_hash")}
    value["contract_id"] = stable_id("challenger_replacement_v3_install_contract", identity)
    value["contract_hash"] = artifact_self_hash(value, "contract_hash")
    return value


def load_fixed_v3_install_contract_bytes(data):
    """Load only the canonical fixed v3 contract; grant no install by itself."""

    try:
        value = dict(_strict_json_bytes(data))
        if data != canonical_json(value).encode("utf-8"):
            raise ValueError("canonical")
        identity = {
            key: item for key, item in value.items()
            if key not in ("contract_id", "contract_hash")
        }
        candidate = build_fixed_v3_activation_candidate()
        hashes = set("0123456789abcdef")
        release = value["release"]
        if (
            set(value) != {
                "$schema", "schema_version", "contract_id", "contract_hash",
                "release", "predecessor_release", "deployment", "snapshot",
                "event_root", "python", "paths", "service", "runtime",
                "schedule", "plist", "authority", "status",
            }
            or value["$schema"]
            != "./challenger-replacement-v3-install-contract-v1.schema.json"
            or value["schema_version"] != "1.0.0"
            or value["contract_id"] != stable_id(
                "challenger_replacement_v3_install_contract", identity
            )
            or value["contract_hash"] != artifact_self_hash(value, "contract_hash")
            or value["predecessor_release"] != _PREDECESSOR
            or value["deployment"] != candidate["deployment"]
            or value["paths"] != activation_paths()
            or release.get("tag") != "v0.78.0"
            or release.get("manifest_version") != "1.72.0"
            or any(
                not isinstance(release.get(key), str)
                or len(release[key]) != length
                or set(release[key]) - hashes
                for key, length in (
                    ("peeled_commit", 40), ("tag_object", 40),
                    ("manifest_hash", 64), ("manifest_file_sha256", 64),
                )
            )
            or value["runtime"]["module"]
            != "crypto_quant.challenger_replacement_v3_installed_runtime"
            or value["runtime"]["program_arguments"] != [
                value["python"]["path"], "-m",
                "crypto_quant.challenger_replacement_v3_installed_runtime",
            ]
            or value["service"] != {
                "label": "local.crypto-quant.challenger-replacement-v1",
                "identity": "gui/501/local.crypto-quant.challenger-replacement-v1",
            }
            or value["schedule"]
            != [{"hour": hour, "minute": 2} for hour in (0, 4, 8, 12, 16, 20)]
            or value["authority"] != {
                "production_activation": False,
                "runtime_install_authorized": True,
                "replacement_start_authorized": False,
                "credentials_allowed": False,
                "account_requests_allowed": False,
                "real_orders_allowed": False,
                "fund_movement_allowed": False,
            }
            or value["plist"] != {
                "path": value["paths"]["candidate_plist"],
                "file_sha256": hashlib.sha256(_plist(value)).hexdigest(),
            }
            or value["status"]
            != "V3_SIMULATION_INSTALL_CONTRACT_VERIFIED_NOT_INSTALLED"
        ):
            raise ValueError("semantics")
        return copy.deepcopy(value)
    except ChallengerReplacementV3ActivationTrustError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementV3ActivationTrustError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_CONTRACT_INVALID"
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
    """Publish an exact release-bound snapshot, plist and install contract."""

    candidate = build_fixed_v3_activation_candidate()
    release = _released_identity()
    paths = activation_paths()
    parent = _ensure_fixed_snapshot_directories(paths)
    snapshot = _publish_snapshot_from_inventory(
        _REPOSITORY, parent, candidate["snapshot_inventory"]
    )
    python = _fixed_python_identity(
        snapshot["root"], package_version="0.78.0",
        import_modules=(
            "crypto_quant.challenger_replacement_v3_installed_runtime",
            "crypto_quant.challenger_replacement_v3_runtime",
        ),
    )
    contract = _contract(
        candidate, release, snapshot,
        _fixed_empty_event_root_identity(paths), python,
    )
    plist_outcome, _ = _publish_contract_exact(
        Path(paths["deployment_root"]), Path(paths["candidate_plist"]).name,
        _plist(contract),
    )
    contract_outcome, _ = _publish_contract_exact(
        Path(paths["deployment_root"]), Path(paths["contract"]).name,
        canonical_json(contract).encode("utf-8"),
    )
    return {
        "snapshot": snapshot, "contract": contract,
        "plist_outcome": plist_outcome, "contract_outcome": contract_outcome,
    }
