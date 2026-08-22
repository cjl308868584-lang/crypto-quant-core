"""Deterministic, code-only replacement Challenger deployment candidate."""

import hashlib
import os
import plistlib
import stat
from pathlib import Path

from jsonschema import Draft202012Validator

from .build import EvaluatorBuild
from .canonical import business_hash, canonical_json, stable_id
from .challenger_replacement_plan_v2 import load_challenger_replacement_plan_v2
from .challenger_replacement_plan import _strict_json_bytes
from .evidence import artifact_self_hash
_ROOT = Path(__file__).resolve().parents[2]
_PLAN = _ROOT / "artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json"
_RUNTIME = "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1"
_SNAPSHOT = _RUNTIME + "/deployment/snapshot"
_FOUNDATION = {
    "release_tag": "v0.66.0", "tag_object": "3b7ee80d0b6eb5e57934bd5b6cecf837e0a562d6",
    "peeled_commit": "12d835807580fb118f17942cd6a568e6b37818e3",
    "package_version": "0.66.0", "manifest_version": "1.60.0",
    "build_input_tree_hash": "f22df35dd1a2c9dbf0885406fa5f8f7f6167efde1ac9a4e71049bc2c01ea86ae",
    "manifest_hash": "c2f2288a69c2e370c62db2d58db9a241023f5c8edce87905d5d5e74d11e9fe3e",
    "manifest_file_sha256": "bff44edf8dd6025ad4683293380458d08e85e9b0f47377844dc5a86614e48ed6",
    "main_ci_run": 32554406969,
    "main_ci_jobs": {"Python 3.9": "success", "Python 3.12": "success", "macOS 15 arm64": "success"},
}
_SOURCES = [
    "src/crypto_quant/challenger_replacement_live_input.py", "src/crypto_quant/challenger_replacement_live_runtime_cli.py",
    "src/crypto_quant/challenger_replacement_runtime.py", "src/crypto_quant/challenger_replacement_evidence.py",
    "src/crypto_quant/challenger_replacement_decision.py",
]

class ChallengerReplacementDeploymentError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code

def _read_owner_exact(path):
    if not all(hasattr(os, name) and getattr(os, name) for name in ("O_NOFOLLOW", "O_NONBLOCK")):
        raise ChallengerReplacementDeploymentError(
            "CHALLENGER_REPLACEMENT_DEPLOYMENT_PLATFORM_UNSUPPORTED")
    descriptor = -1; primary = None
    try:
        descriptor = os.open(Path(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid()
            or opened.st_nlink != 1 or stat.S_IMODE(opened.st_mode) & 0o022
            or not 1 <= opened.st_size <= 4 * 1024 * 1024
        ):
            raise OSError("untrusted deployment file")
        chunks, remaining = [], opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise OSError("short deployment read")
            chunks.append(chunk); remaining -= len(chunk)
        after = os.fstat(descriptor)
        attached = Path(path).lstat()
        before_identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
        if (before_identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            or (opened.st_dev, opened.st_ino) != (attached.st_dev, attached.st_ino)):
            raise OSError("deployment file changed")
        return b"".join(chunks)
    except (OSError, ValueError) as error:
        primary = ChallengerReplacementDeploymentError("CHALLENGER_REPLACEMENT_DEPLOYMENT_PATH_UNTRUSTED")
        raise primary from error
    except BaseException as error:
        primary = error; raise
    finally:
        if descriptor >= 0:
            try: os.close(descriptor)
            except OSError as error:
                if primary is None: raise ChallengerReplacementDeploymentError("CHALLENGER_REPLACEMENT_DEPLOYMENT_PATH_UNTRUSTED") from error
                setattr(primary,"close_failure",repr(error))

def _plist_payload(deployment):
    paths = deployment["paths"]
    return {
        "Label": deployment["service"]["label"], "ProgramArguments": deployment["runtime"]["program_arguments"],
        "WorkingDirectory": paths["snapshot_root"], "StandardOutPath": paths["stdout"],
        "StandardErrorPath": paths["stderr"], "RunAtLoad": False, "KeepAlive": False,
        "ProcessType": "Background", "Umask": 0o077,
        "EnvironmentVariables": {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONPATH": paths["snapshot_root"] + "/src",
        },
        "StartCalendarInterval": [{"Hour": item["hour"], "Minute": item["minute"]} for item in deployment["schedule"]],
    }

def render_challenger_replacement_plist(deployment):
    return plistlib.dumps(_plist_payload(deployment), fmt=plistlib.FMT_XML, sort_keys=True)

def build_challenger_replacement_deployment():
    plan = load_challenger_replacement_plan_v2(_PLAN)
    paths = {
        "runtime_root": _RUNTIME, "event_root": _RUNTIME + "/state/challenger-replacement-events-v1",
        "stdout": _RUNTIME + "/log/challenger-replacement.stdout.log", "stderr": _RUNTIME + "/log/challenger-replacement.stderr.log",
        "target_plist": "/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist",
        "snapshot_root": _SNAPSHOT, "python": _SNAPSHOT + "/bin/python3",
    }
    deployment = {
        "$schema": "./challenger-replacement-deployment-v1.schema.json",
        "schema_version": "1.0.0",
        "deployment_id": "challenger_replacement_deployment_" + "0" * 64,
        "deployment_hash": "0" * 64,
        "plan": {
            "path": "artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json",
            "file_sha256": hashlib.sha256(_PLAN.read_bytes()).hexdigest(), "plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"],
        },
        "foundation": dict(_FOUNDATION),
        "candidate_release": {
            "release_tag": "v0.67.0", "package_version": "0.67.0",
            "manifest_version": "1.61.0",
        },
        "service": {"label": "local.crypto-quant.challenger-replacement-v1", "identity": "gui/501/local.crypto-quant.challenger-replacement-v1"},
        "paths": paths,
        "runtime": {
            "module": "crypto_quant.challenger_replacement_live_runtime_cli",
            "program_arguments": [paths["python"], "-m", "crypto_quant.challenger_replacement_live_runtime_cli"],
            "working_directory": paths["snapshot_root"],
        },
        "schedule": [{"hour": hour, "minute": 2} for hour in (0, 4, 8, 12, 16, 20)],
        "network_contract": {
            "base_url": "https://data-api.binance.vision", "time_requests": 3,
            "kline_attempts_min": 1, "kline_attempts_max": 3,
            "credentials_allowed": False,
        },
        "authority": {"production_activation": False, "runtime_install_authorized": False,
                      "replacement_start_authorized": False, "real_orders_allowed": False},
        "source_file_allowlist": list(_SOURCES),
        "plist_sha256": "0" * 64,
    }
    deployment["plist_sha256"] = hashlib.sha256(render_challenger_replacement_plist(deployment)).hexdigest()
    identity = {key: deployment[key] for key in (
        "plan", "foundation", "candidate_release", "service", "paths",
        "runtime", "schedule", "network_contract", "authority",
        "source_file_allowlist", "plist_sha256",
    )}
    deployment["deployment_id"] = stable_id("challenger_replacement_deployment", identity)
    deployment["deployment_hash"] = artifact_self_hash(deployment, "deployment_hash")
    return deployment

def challenger_replacement_deployment_bytes():
    return canonical_json(build_challenger_replacement_deployment()).encode("utf-8") + b"\n"

def load_challenger_replacement_deployment(path, *, manifest_path):
    expected = build_challenger_replacement_deployment()
    body = _read_owner_exact(path)
    if body != challenger_replacement_deployment_bytes():
        raise ChallengerReplacementDeploymentError("CHALLENGER_REPLACEMENT_DEPLOYMENT_BYTES_INVALID")
    try:
        manifest = _strict_json_bytes(_read_owner_exact(manifest_path))
        workspace = Path(manifest_path).parent.parent
        schema = _strict_json_bytes(_read_owner_exact(
            workspace / "config/evaluator-build-manifest-v1.schema.json"))
        if tuple(Draft202012Validator(schema).iter_errors(manifest)):
            raise ValueError("manifest schema")
        files = manifest["file_hashes"]
        expected_paths = EvaluatorBuild.expected_file_paths(workspace)
        actual = {name: hashlib.sha256(_read_owner_exact(workspace / name)).hexdigest()
                  for name in expected_paths}
        plist_name = "artifacts/challenger-replacement/local.crypto-quant.challenger-replacement-v1.plist"
        if (manifest["manifest_version"] != "1.61.0"
            or manifest["manifest_hash"] != artifact_self_hash(manifest, "manifest_hash")
            or set(files) != set(expected_paths) or files != actual
            or manifest["build_input_tree_hash"] != business_hash(actual)
            or _read_owner_exact(workspace / plist_name) != render_challenger_replacement_plist(expected)
            or files[plist_name] != expected["plist_sha256"]
        ):
            raise ValueError("manifest mismatch")
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementDeploymentError(
            "CHALLENGER_REPLACEMENT_DEPLOYMENT_MANIFEST_INVALID") from error
    return expected
