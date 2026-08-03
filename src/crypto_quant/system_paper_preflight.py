"""Fail-closed, release-bound System Paper machine preflight evidence."""

import hashlib
import ctypes
import json
import os
import platform
import plistlib
import re
import stat
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact
from .runtime_health import (
    BinanceServerTimeTransport,
    RuntimeHealthError,
    RuntimeHealthPolicy,
    _failed_probe,
    build_server_time_probe,
    server_time_probe_reasons,
    server_time_probe_trust_hash,
)
from .system_paper_launchd import (
    SystemPaperLaunchdError,
    load_system_paper_launchd_contract,
    system_paper_launchd_contract_trust_hash,
)


_SCHEMA = "system-paper-preflight-receipt-v1.schema.json"
_LABEL = "local.crypto-quant.system-paper-v1"
_PING_URL = "https://data-api.binance.vision/api/v3/ping"
_PING_HOST = "data-api.binance.vision"
_MAX_BODY_BYTES = 1024
_MAX_COMMAND_BYTES = 64 * 1024
_MIN_FREE_BYTES = 5 * 1024 * 1024 * 1024
_EXPIRY_MINUTES = 30
_WARNINGS = (
    "PREFLIGHT_DOES_NOT_INSTALL_OR_START_SYSTEM_PAPER",
    "VERIFIED_RECEIPT_EXPIRES_AFTER_30_MINUTES",
    "PUBLIC_MARKET_ENDPOINTS_ONLY",
    "NO_LIVE_TRADING_AUTHORITY",
)


class SystemPaperPreflightError(ValueError):
    """The preflight run or its immutable evidence failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> Tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise SystemPaperPreflightError(
                "SYSTEM_PAPER_PREFLIGHT_TIME_INVALID"
            ) from error
    else:
        raise SystemPaperPreflightError("SYSTEM_PAPER_PREFLIGHT_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemPaperPreflightError("SYSTEM_PAPER_PREFLIGHT_TIME_INVALID")
    parsed = parsed.astimezone(timezone.utc)
    if parsed.microsecond % 1000:
        raise SystemPaperPreflightError("SYSTEM_PAPER_PREFLIGHT_TIME_INVALID")
    text = utc_datetime(parsed)
    if isinstance(value, str) and value != text:
        raise SystemPaperPreflightError("SYSTEM_PAPER_PREFLIGHT_TIME_INVALID")
    return parsed, text


def _now() -> str:
    return utc_datetime(datetime.now(timezone.utc))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _absolute(value: object, reason: str) -> Path:
    if not isinstance(value, (str, Path)) or "\x00" in str(value):
        raise SystemPaperPreflightError(reason)
    path = Path(value).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise SystemPaperPreflightError(reason)
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            entry = current.lstat()
        except FileNotFoundError:
            break
        except OSError as error:
            raise SystemPaperPreflightError(reason) from error
        if stat.S_ISLNK(entry.st_mode):
            raise SystemPaperPreflightError(reason)
    return path


def _secure_directory(path: Path, *, create: bool, reason: str) -> Path:
    try:
        if create:
            path.mkdir(mode=0o700, parents=False, exist_ok=True)
        entry = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise SystemPaperPreflightError(reason) from error
    if (
        resolved != path
        or not stat.S_ISDIR(entry.st_mode)
        or entry.st_uid != os.getuid()
        or stat.S_IMODE(entry.st_mode) != 0o700
        or entry.st_nlink < 1
    ):
        raise SystemPaperPreflightError(reason)
    return path


def _secure_file(path: Path, reason: str) -> Path:
    try:
        entry = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise SystemPaperPreflightError(reason) from error
    if (
        resolved != path
        or not stat.S_ISREG(entry.st_mode)
        or entry.st_uid != os.getuid()
        or entry.st_nlink != 1
        or stat.S_IMODE(entry.st_mode) != 0o600
        or entry.st_size <= 0
        or entry.st_size > 8 * 1024 * 1024
    ):
        raise SystemPaperPreflightError(reason)
    return path


def _path_identity(path: Path) -> Dict[str, Any]:
    checked = _secure_directory(
        path, create=False, reason="SYSTEM_PAPER_PREFLIGHT_ROOT_INVALID"
    )
    entry = checked.stat()
    return {
        "path": str(checked),
        "device": entry.st_dev,
        "inode": entry.st_ino,
        "owner_uid": entry.st_uid,
        "mode": stat.S_IMODE(entry.st_mode),
    }


def _default_machine_probe() -> Mapping[str, Any]:
    try:
        timezone_target = os.readlink("/etc/localtime")
        local = time.localtime()
    except OSError as error:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_MACHINE_INVALID"
        ) from error
    timezone_name = (
        "Asia/Shanghai"
        if timezone_target.endswith("/Asia/Shanghai")
        and getattr(local, "tm_gmtoff", None) == 28800
        and local.tm_isdst == 0
        else "INVALID"
    )
    return {
        "uid": os.getuid(),
        "home": str(Path.home().resolve(strict=True)),
        "hostname": platform.node(),
        "timezone": timezone_name,
    }


def _machine_identity(probe) -> Dict[str, Any]:
    try:
        value = dict(probe())
        uid = value["uid"]
        home = _absolute(value["home"], "SYSTEM_PAPER_PREFLIGHT_MACHINE_INVALID")
        hostname = value["hostname"]
        timezone_name = value["timezone"]
        home_entry = home.stat()
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_MACHINE_INVALID"
        ) from error
    if (
        isinstance(uid, bool)
        or not isinstance(uid, int)
        or uid != os.getuid()
        or not isinstance(hostname, str)
        or not hostname
        or len(hostname) > 255
        or timezone_name != "Asia/Shanghai"
        or not stat.S_ISDIR(home_entry.st_mode)
        or home_entry.st_uid != uid
    ):
        raise SystemPaperPreflightError("SYSTEM_PAPER_PREFLIGHT_MACHINE_INVALID")
    return {
        "uid": uid,
        "home": str(home),
        "hostname": hostname,
        "timezone": timezone_name,
        "home_device": home_entry.st_dev,
        "home_inode": home_entry.st_ino,
    }


def _default_filesystem_probe(path: Path) -> Mapping[str, Any]:
    try:
        entry = path.stat()
        value = os.statvfs(path)
    except OSError as error:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_FILESYSTEM_INVALID"
        ) from error
    return {
        "device": entry.st_dev,
        "filesystem_id": getattr(value, "f_fsid", entry.st_dev),
        "free_bytes": value.f_bavail * value.f_frsize,
        "is_local": _darwin_mount_is_local(path),
    }


def _darwin_mount_is_local(path: Path) -> bool:
    if platform.system() != "Darwin":
        return False

    class Fsid(ctypes.Structure):
        _fields_ = [("val", ctypes.c_int32 * 2)]

    class Statfs(ctypes.Structure):
        _fields_ = [
            ("f_bsize", ctypes.c_uint32),
            ("f_iosize", ctypes.c_int32),
            ("f_blocks", ctypes.c_uint64),
            ("f_bfree", ctypes.c_uint64),
            ("f_bavail", ctypes.c_uint64),
            ("f_files", ctypes.c_uint64),
            ("f_ffree", ctypes.c_uint64),
            ("f_fsid", Fsid),
            ("f_owner", ctypes.c_uint32),
            ("f_type", ctypes.c_uint32),
            ("f_flags", ctypes.c_uint32),
            ("f_fssubtype", ctypes.c_uint32),
            ("f_fstypename", ctypes.c_char * 16),
            ("f_mntonname", ctypes.c_char * 1024),
            ("f_mntfromname", ctypes.c_char * 1024),
            ("f_flags_ext", ctypes.c_uint32),
            ("f_reserved", ctypes.c_uint32 * 7),
        ]

    buffer = Statfs()
    libc = ctypes.CDLL(None, use_errno=True)
    call = libc.statfs
    call.argtypes = (ctypes.c_char_p, ctypes.POINTER(Statfs))
    call.restype = ctypes.c_int
    if call(os.fsencode(path), ctypes.byref(buffer)) != 0:
        return False
    return bool(buffer.f_flags & 0x00001000)


def _filesystem(path: Path, probe) -> Dict[str, Any]:
    try:
        value = dict(probe(path))
    except (OSError, TypeError, ValueError) as error:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_FILESYSTEM_INVALID"
        ) from error
    required = ("device", "filesystem_id", "free_bytes", "is_local")
    if any(key not in value for key in required):
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_FILESYSTEM_INVALID"
        )
    if any(
        isinstance(value[key], bool) or not isinstance(value[key], int)
        for key in ("device", "filesystem_id", "free_bytes")
    ) or not isinstance(value["is_local"], bool):
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_FILESYSTEM_INVALID"
        )
    return {key: value[key] for key in required}


def _default_command_runner(argv):
    return subprocess.run(
        list(argv),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
    )


def _run_command(runner, argv) -> Tuple[Mapping[str, Any], str, str]:
    try:
        result = runner(tuple(argv))
        code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except Exception as error:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_COMMAND_FAILED"
        ) from error
    if (
        isinstance(code, bool)
        or not isinstance(code, int)
        or not isinstance(stdout, str)
        or not isinstance(stderr, str)
        or len(stdout.encode("utf-8")) > _MAX_COMMAND_BYTES
        or len(stderr.encode("utf-8")) > _MAX_COMMAND_BYTES
    ):
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_COMMAND_INVALID"
        )
    evidence = {
        "argv": list(argv),
        "returncode": code,
        "stdout_sha256": _sha256(stdout.encode("utf-8")),
        "stderr_sha256": _sha256(stderr.encode("utf-8")),
    }
    return evidence, stdout, stderr


def _safe_run_command(runner, argv):
    try:
        evidence, stdout, stderr = _run_command(runner, argv)
        return evidence, stdout, stderr, None
    except SystemPaperPreflightError as error:
        empty_hash = _sha256(b"")
        return (
            {
                "argv": list(argv),
                "returncode": 255,
                "stdout_sha256": empty_hash,
                "stderr_sha256": empty_hash,
            },
            "",
            "",
            error.reason_code,
        )


def _ac_sleep_minutes(output: str) -> int:
    match = re.search(
        r"(?ms)^AC Power:\s*$.*?^\s*sleep\s+(\d+)\s*$",
        output,
    )
    if match is None:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_AC_SLEEP_UNKNOWN"
        )
    return int(match.group(1))


@dataclass(frozen=True)
class PublicPingHttpResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes


def _valid_ping_url(value: object) -> bool:
    if value != _PING_URL:
        return False
    try:
        parsed = urlparse(value)
        return (
            parsed.scheme == "https"
            and parsed.hostname == _PING_HOST
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
            and parsed.path == "/api/v3/ping"
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


class _SameHostPingRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _valid_ping_url(newurl):
            raise SystemPaperPreflightError(
                "SYSTEM_PAPER_PREFLIGHT_PING_REDIRECT_INVALID"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class BinancePublicPingTransport:
    """Credential-free transport for the one frozen public ping endpoint."""

    def __init__(self, *, opener=None):
        self._opener = opener or build_opener(
            ProxyHandler({}), _SameHostPingRedirectHandler()
        )
        self.calls = 0

    def get(self) -> PublicPingHttpResponse:
        self.calls += 1
        try:
            request = Request(
                _PING_URL,
                method="GET",
                headers={
                    "Accept": "application/json",
                    "User-Agent": "crypto-quant-system-paper-preflight/0.58",
                },
            )
            with self._opener.open(request, timeout=10) as response:
                body = response.read(_MAX_BODY_BYTES + 1)
                status = response.getcode()
                final_url = response.geturl()
                headers = dict(response.headers.items())
        except HTTPError as error:
            status = error.code
            final_url = error.geturl()
            headers = dict(error.headers.items()) if error.headers else {}
            body = b""
        except SystemPaperPreflightError:
            raise
        except (OSError, TimeoutError, URLError) as error:
            raise SystemPaperPreflightError(
                "SYSTEM_PAPER_PREFLIGHT_PING_TRANSPORT_FAILED"
            ) from error
        if len(body) > _MAX_BODY_BYTES:
            raise SystemPaperPreflightError(
                "SYSTEM_PAPER_PREFLIGHT_PING_RESPONSE_TOO_LARGE"
            )
        return PublicPingHttpResponse(status, final_url, headers, body)


def _ping_probe(transport) -> Dict[str, Any]:
    if not hasattr(transport, "get"):
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_PING_TRANSPORT_INVALID"
        )
    response = transport.get()
    if (
        not isinstance(response, PublicPingHttpResponse)
        or response.status != 200
        or not _valid_ping_url(response.final_url)
        or response.body != b"{}"
        or not isinstance(response.headers, Mapping)
    ):
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_PING_RESPONSE_INVALID"
        )
    return {
        "url": _PING_URL,
        "http_method": "GET",
        "security_type": "NONE_PUBLIC",
        "status": 200,
        "response_body_sha256": _sha256(response.body),
        "request_count": 1,
    }


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _canonical_receipt(data: bytes) -> Mapping[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_RECEIPT_READ_INVALID"
        ) from error
    if not isinstance(value, Mapping) or canonical_json(value).encode("utf-8") != data:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_RECEIPT_READ_INVALID"
        )
    return value


def _receipt_reasons(receipt: Mapping[str, Any]) -> Tuple[str, ...]:
    reasons = []
    if tuple(_validator().iter_errors(receipt)):
        reasons.append("SYSTEM_PAPER_PREFLIGHT_RECEIPT_SCHEMA_INVALID")
    if receipt.get("receipt_hash") != artifact_self_hash(receipt, "receipt_hash"):
        reasons.append("SYSTEM_PAPER_PREFLIGHT_RECEIPT_HASH_MISMATCH")
    try:
        identity = {
            "contract_id": receipt["contract_binding"]["contract_id"],
            "contract_hash": receipt["contract_binding"]["contract_hash"],
            "machine_identity": receipt["machine_identity"],
            "verified_at": receipt["verified_at"],
        }
        if receipt.get("receipt_id") != stable_id(
            "system_paper_preflight_receipt", identity
        ):
            reasons.append("SYSTEM_PAPER_PREFLIGHT_RECEIPT_ID_MISMATCH")
        probe = receipt["clock_probe"]
        if server_time_probe_reasons(
            probe, receipt["clock_probe_trust_hash"]
        ):
            reasons.append("SYSTEM_PAPER_PREFLIGHT_CLOCK_REPLAY_INVALID")
        status_value = receipt["status"]
        failure_reasons = receipt["failure_reasons"]
        verified_dt, _ = _utc(receipt["verified_at"])
        expires_value = receipt["expires_at_or_null"]
        expected_expiry = utc_datetime(
            verified_dt + timedelta(minutes=_EXPIRY_MINUTES)
        )
        security = receipt["security_boundary"]
        launchd = receipt["launchd"]
        power = receipt["power"]
        disk = receipt["disk"]
        ping = receipt["ping_probe"]
        machine = receipt["machine_identity"]
        commands = launchd["command_evidence"]
        expected_commands = [
            ["/bin/launchctl", "print", f"gui/{machine['uid']}"],
            [
                "/bin/launchctl",
                "print",
                f"gui/{machine['uid']}/{_LABEL}",
            ],
            ["/usr/bin/pmset", "-g", "custom"],
        ]
        if [item.get("argv") for item in commands] != expected_commands:
            reasons.append("SYSTEM_PAPER_PREFLIGHT_COMMAND_SET_MISMATCH")
        if (
            launchd["login_domain_present"]
            != (commands[0]["returncode"] == 0)
            or launchd["service_present"]
            != (commands[1]["returncode"] == 0)
            or launchd["target_plist_path"]
            != str(
                Path(machine["home"])
                / "Library"
                / "LaunchAgents"
                / f"{_LABEL}.plist"
            )
            or launchd["label"] != _LABEL
            or launchd["run_at_load"] is not True
        ):
            reasons.append("SYSTEM_PAPER_PREFLIGHT_LAUNCHD_EVIDENCE_INVALID")
        if power["ac_sleep_safe"] != (power["ac_sleep_minutes"] == 0):
            reasons.append("SYSTEM_PAPER_PREFLIGHT_POWER_EVIDENCE_INVALID")
        for name in ("state", "artifacts"):
            filesystem = disk["filesystems"][name]
            root = receipt["root_identities"][name]
            if filesystem["device"] != root["device"]:
                reasons.append("SYSTEM_PAPER_PREFLIGHT_DISK_EVIDENCE_INVALID")
        if disk["minimum_free_bytes"] != _MIN_FREE_BYTES:
            reasons.append("SYSTEM_PAPER_PREFLIGHT_DISK_EVIDENCE_INVALID")
        if (
            ping["url"] != _PING_URL
            or ping["http_method"] != "GET"
            or ping["security_type"] != "NONE_PUBLIC"
            or ping["request_count"] not in (0, 1)
        ):
            reasons.append("SYSTEM_PAPER_PREFLIGHT_PING_EVIDENCE_INVALID")
        if (
            receipt["network_request_count"]
            != security["network_request_count"]
            or security
            != {
                "production_activation_enabled": False,
                "launchctl_mutation_count": 0,
                "runtime_invocation_count": 0,
                "network_request_count": receipt["network_request_count"],
                "credential_count": 0,
                "broker_request_count": 0,
                "order_submission_count": 0,
            }
            or receipt["warnings"] != list(_WARNINGS)
        ):
            reasons.append("SYSTEM_PAPER_PREFLIGHT_SECURITY_BOUNDARY_INVALID")
        if status_value == "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE":
            trusted_dt, _ = _utc(probe["trusted_completed_at_or_null"])
            verified_invariants = (
                failure_reasons == []
                and expires_value == expected_expiry
                and receipt["network_request_count"] == 4
                and probe["sample_count"] == 3
                and probe["health_status"]
                in ("HEALTHY_ALIGNED", "HEALTHY_CORRECTED")
                and abs((trusted_dt - verified_dt).total_seconds()) <= 30
                and ping["status"] == 200
                and ping["request_count"] == 1
                and launchd["login_domain_present"] is True
                and launchd["service_present"] is False
                and launchd["target_plist_present"] is False
                and commands[1]["returncode"] == 113
                and power["ac_sleep_minutes"] == 0
                and power["ac_sleep_safe"] is True
                and all(
                    disk["filesystems"][name]["is_local"] is True
                    and disk["filesystems"][name]["free_bytes"]
                    >= _MIN_FREE_BYTES
                    for name in ("state", "artifacts")
                )
            )
            if not verified_invariants:
                reasons.append("SYSTEM_PAPER_PREFLIGHT_VERIFIED_STATE_INVALID")
        elif status_value == "PREFLIGHT_FAILED_CLOSED":
            if not failure_reasons or expires_value is not None:
                reasons.append("SYSTEM_PAPER_PREFLIGHT_FAILED_STATE_INVALID")
        else:
            reasons.append("SYSTEM_PAPER_PREFLIGHT_STATUS_INVALID")
    except (KeyError, TypeError, RuntimeHealthError):
        reasons.append("SYSTEM_PAPER_PREFLIGHT_RECEIPT_REPLAY_INVALID")
    return tuple(sorted(set(reasons)))


def run_system_paper_preflight(
    *,
    contract_path: Path,
    plist_path: Path,
    command_runner=None,
    machine_probe=None,
    filesystem_probe=None,
    server_time_transport=None,
    ping_transport=None,
    clock=None,
) -> Mapping[str, Any]:
    # This is intentionally first: invalid deployment inputs create no evidence.
    try:
        contract = load_system_paper_launchd_contract(
            contract_path=Path(contract_path), plist_path=Path(plist_path)
        )
    except SystemPaperLaunchdError:
        raise
    plist_bytes = _secure_file(
        Path(plist_path), "SYSTEM_PAPER_PREFLIGHT_PLIST_INVALID"
    ).read_bytes()
    try:
        plist = plistlib.loads(plist_bytes)
    except plistlib.InvalidFileException as error:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_PLIST_INVALID"
        ) from error
    if plist.get("Label") != _LABEL or plist.get("RunAtLoad") is not True:
        raise SystemPaperPreflightError("SYSTEM_PAPER_PREFLIGHT_PLIST_INVALID")

    selected_machine_probe = machine_probe or _default_machine_probe
    selected_filesystem_probe = filesystem_probe or _default_filesystem_probe
    selected_runner = command_runner or _default_command_runner
    selected_time_transport = server_time_transport or BinanceServerTimeTransport()
    selected_ping_transport = ping_transport or BinancePublicPingTransport()
    verified_dt, verified_at = _utc((clock or _now)())
    machine = _machine_identity(selected_machine_probe)
    runtime_root = _absolute(
        contract["runtime_root"], "SYSTEM_PAPER_PREFLIGHT_ROOT_INVALID"
    )
    root_paths = {
        name: _absolute(value, "SYSTEM_PAPER_PREFLIGHT_ROOT_INVALID")
        for name, value in contract["root_paths"].items()
        if name in ("runtime", "state", "log", "artifacts", "deployment")
    }
    before = {name: _path_identity(path) for name, path in root_paths.items()}
    preflight_root = _secure_directory(
        _absolute(
            contract["root_paths"]["preflight_receipts"],
            "SYSTEM_PAPER_PREFLIGHT_ROOT_INVALID",
        ),
        create=True,
        reason="SYSTEM_PAPER_PREFLIGHT_ROOT_INVALID",
    )
    root_paths["preflight_receipts"] = preflight_root
    before["preflight_receipts"] = _path_identity(preflight_root)

    failures = []
    commands = []
    domain_command = ("/bin/launchctl", "print", f"gui/{machine['uid']}")
    service_command = (
        "/bin/launchctl",
        "print",
        f"gui/{machine['uid']}/{_LABEL}",
    )
    pmset_command = ("/usr/bin/pmset", "-g", "custom")

    domain, _domain_out, _domain_err, command_failure = _safe_run_command(
        selected_runner, domain_command
    )
    commands.append(domain)
    if command_failure:
        failures.append(command_failure)
    login_domain_present = domain["returncode"] == 0
    if not login_domain_present:
        failures.append("SYSTEM_PAPER_PREFLIGHT_LOGIN_DOMAIN_ABSENT")

    service, _service_out, _service_err, command_failure = _safe_run_command(
        selected_runner, service_command
    )
    commands.append(service)
    if command_failure:
        failures.append(command_failure)
    service_present = service["returncode"] == 0
    if service_present or service["returncode"] not in (0, 113):
        failures.append("SYSTEM_PAPER_PREFLIGHT_SERVICE_NOT_ABSENT")

    power_command, power_stdout, _power_err, command_failure = _safe_run_command(
        selected_runner, pmset_command
    )
    commands.append(power_command)
    if command_failure:
        failures.append(command_failure)
    if power_command["returncode"] != 0:
        failures.append("SYSTEM_PAPER_PREFLIGHT_POWER_PROBE_FAILED")
        sleep_minutes = None
    else:
        try:
            sleep_minutes = _ac_sleep_minutes(power_stdout)
        except SystemPaperPreflightError as error:
            failures.append(error.reason_code)
            sleep_minutes = None
    ac_sleep_safe = sleep_minutes == 0
    if sleep_minutes is not None and not ac_sleep_safe:
        failures.append("SYSTEM_PAPER_PREFLIGHT_AC_SLEEP_UNSAFE")

    target_plist = (
        Path(machine["home"]) / "Library" / "LaunchAgents" / f"{_LABEL}.plist"
    )
    target_present = target_plist.exists() or target_plist.is_symlink()
    if target_present:
        failures.append("SYSTEM_PAPER_PREFLIGHT_TARGET_PLIST_PRESENT")

    filesystems = {}
    for name in ("state", "artifacts"):
        value = _filesystem(root_paths[name], selected_filesystem_probe)
        filesystems[name] = value
        if not value["is_local"]:
            failures.append("SYSTEM_PAPER_PREFLIGHT_NETWORK_FILESYSTEM")
        if value["free_bytes"] < _MIN_FREE_BYTES:
            failures.append("SYSTEM_PAPER_PREFLIGHT_DISK_SPACE_INSUFFICIENT")
        if value["device"] != before[name]["device"]:
            failures.append("SYSTEM_PAPER_PREFLIGHT_FILESYSTEM_IDENTITY_MISMATCH")

    try:
        clock_probe = build_server_time_probe(transport=selected_time_transport)
        clock_trust = server_time_probe_trust_hash(clock_probe)
        if (
            clock_probe["health_status"] not in ("HEALTHY_ALIGNED", "HEALTHY_CORRECTED")
            or server_time_probe_reasons(clock_probe, clock_trust)
        ):
            failures.append("SYSTEM_PAPER_PREFLIGHT_CLOCK_UNHEALTHY")
    except Exception as error:
        reason = "SYSTEM_PAPER_PREFLIGHT_CLOCK_PROBE_FAILED"
        failures.append(reason)
        clock_probe = _failed_probe(
            RuntimeHealthPolicy.create(), reason, verified_at
        )
        clock_trust = server_time_probe_trust_hash(clock_probe)

    try:
        ping_probe = _ping_probe(selected_ping_transport)
    except SystemPaperPreflightError as error:
        failures.append(error.reason_code)
        ping_probe = {
            "url": _PING_URL,
            "http_method": "GET",
            "security_type": "NONE_PUBLIC",
            "status": 0,
            "response_body_sha256": "0" * 64,
            "request_count": getattr(selected_ping_transport, "calls", 0),
        }

    after = {name: _path_identity(path) for name, path in root_paths.items()}
    if before != after:
        failures.append("SYSTEM_PAPER_PREFLIGHT_ROOT_IDENTITY_CHANGED")
    if _machine_identity(selected_machine_probe) != machine:
        failures.append("SYSTEM_PAPER_PREFLIGHT_MACHINE_IDENTITY_CHANGED")

    network_count = getattr(selected_time_transport, "calls", 3) + getattr(
        selected_ping_transport, "calls", 1
    )
    if network_count != 4:
        failures.append("SYSTEM_PAPER_PREFLIGHT_NETWORK_COUNT_INVALID")
    status_value = (
        "PREFLIGHT_FAILED_CLOSED"
        if failures
        else "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE"
    )
    expires = (
        utc_datetime(verified_dt + timedelta(minutes=_EXPIRY_MINUTES))
        if not failures
        else None
    )
    contract_binding = {
        "contract_path": str(Path(contract_path)),
        "plist_path": str(Path(plist_path)),
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "contract_trust_hash": system_paper_launchd_contract_trust_hash(contract),
        "launchd_plist_sha256": _sha256(plist_bytes),
        "release_commit": contract["release"]["release_commit"],
        "snapshot_tree_hash": contract["execution_snapshot"]["tree_hash"],
    }
    identity = {
        "contract_id": contract_binding["contract_id"],
        "contract_hash": contract_binding["contract_hash"],
        "machine_identity": machine,
        "verified_at": verified_at,
    }
    receipt = {
        "$schema": f"./{_SCHEMA}",
        "schema_version": "1.0.0",
        "receipt_id": stable_id("system_paper_preflight_receipt", identity),
        "receipt_hash": "0" * 64,
        "verified_at": verified_at,
        "expires_at_or_null": expires,
        "status": status_value,
        "failure_reasons": sorted(set(failures)),
        "contract_binding": contract_binding,
        "machine_identity": machine,
        "root_identities": before,
        "launchd": {
            "label": _LABEL,
            "login_domain_present": login_domain_present,
            "service_present": service_present,
            "target_plist_path": str(target_plist),
            "target_plist_present": target_present,
            "run_at_load": True,
            "command_evidence": commands,
        },
        "power": {
            "source": "AC Power",
            "ac_sleep_minutes": sleep_minutes,
            "ac_sleep_safe": ac_sleep_safe,
        },
        "disk": {
            "minimum_free_bytes": _MIN_FREE_BYTES,
            "filesystems": filesystems,
        },
        "clock_probe": clock_probe,
        "clock_probe_trust_hash": clock_trust,
        "ping_probe": ping_probe,
        "network_request_count": network_count,
        "security_boundary": {
            "production_activation_enabled": False,
            "launchctl_mutation_count": 0,
            "runtime_invocation_count": 0,
            "network_request_count": network_count,
            "credential_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
        },
        "warnings": list(_WARNINGS),
    }
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    if _receipt_reasons(receipt):
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_RECEIPT_INVALID"
        )
    receipt_path = preflight_root / f"{receipt['receipt_id']}.json"
    try:
        _publish_exact(receipt_path, canonical_json(receipt).encode("utf-8"))
    except ValueError as error:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_PUBLISH_CONFLICT"
        ) from error
    os.chmod(receipt_path, 0o600)
    return {
        "outcome": status_value,
        "receipt_path": str(receipt_path),
        "receipt_id": receipt["receipt_id"],
        "receipt_hash": receipt["receipt_hash"],
    }


def load_system_paper_preflight_receipt(
    *,
    receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    machine_probe=None,
    filesystem_probe=None,
    clock=None,
    _allow_expired_verified=False,
) -> Mapping[str, Any]:
    contract = load_system_paper_launchd_contract(
        contract_path=Path(contract_path), plist_path=Path(plist_path)
    )
    receipt_file = _secure_file(
        Path(receipt_path), "SYSTEM_PAPER_PREFLIGHT_RECEIPT_READ_INVALID"
    )
    seen_ids = set()
    for item in receipt_file.parent.iterdir():
        if not item.is_file() or item.suffix != ".json":
            raise SystemPaperPreflightError(
                "SYSTEM_PAPER_PREFLIGHT_OUTPUT_INVENTORY_INVALID"
            )
        candidate = _canonical_receipt(
            _secure_file(
                item, "SYSTEM_PAPER_PREFLIGHT_OUTPUT_INVENTORY_INVALID"
            ).read_bytes()
        )
        candidate_id = candidate.get("receipt_id")
        if (
            not isinstance(candidate_id, str)
            or item.name != f"{candidate_id}.json"
            or candidate_id in seen_ids
        ):
            raise SystemPaperPreflightError(
                "SYSTEM_PAPER_PREFLIGHT_OUTPUT_INVENTORY_INVALID"
            )
        seen_ids.add(candidate_id)
    receipt = _canonical_receipt(receipt_file.read_bytes())
    if receipt_file.name != f"{receipt.get('receipt_id')}.json" or _receipt_reasons(receipt):
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_RECEIPT_INVALID"
        )
    plist_bytes = _secure_file(
        Path(plist_path), "SYSTEM_PAPER_PREFLIGHT_PLIST_INVALID"
    ).read_bytes()
    binding = receipt["contract_binding"]
    expected_binding = {
        "contract_path": str(Path(contract_path)),
        "plist_path": str(Path(plist_path)),
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "contract_trust_hash": system_paper_launchd_contract_trust_hash(contract),
        "launchd_plist_sha256": _sha256(plist_bytes),
        "release_commit": contract["release"]["release_commit"],
        "snapshot_tree_hash": contract["execution_snapshot"]["tree_hash"],
    }
    if binding != expected_binding:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_CONTRACT_BINDING_MISMATCH"
        )
    machine = _machine_identity(machine_probe or _default_machine_probe)
    if machine != receipt["machine_identity"]:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_MACHINE_IDENTITY_MISMATCH"
        )
    runtime_root = Path(contract["runtime_root"])
    root_paths = {
        name: Path(value)
        for name, value in contract["root_paths"].items()
        if name
        in (
            "runtime",
            "state",
            "log",
            "artifacts",
            "deployment",
            "preflight_receipts",
        )
    }
    identities = {name: _path_identity(path) for name, path in root_paths.items()}
    if identities != receipt["root_identities"]:
        raise SystemPaperPreflightError(
            "SYSTEM_PAPER_PREFLIGHT_ROOT_IDENTITY_MISMATCH"
        )
    probe = filesystem_probe or _default_filesystem_probe
    for name in ("state", "artifacts"):
        value = _filesystem(root_paths[name], probe)
        if value != receipt["disk"]["filesystems"][name]:
            raise SystemPaperPreflightError(
                "SYSTEM_PAPER_PREFLIGHT_ROOT_IDENTITY_MISMATCH"
            )
    if (
        receipt["status"] == "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE"
        and not _allow_expired_verified
    ):
        now_dt, _ = _utc((clock or _now)())
        expiry_dt, _ = _utc(receipt["expires_at_or_null"])
        if now_dt > expiry_dt:
            raise SystemPaperPreflightError(
                "SYSTEM_PAPER_PREFLIGHT_RECEIPT_EXPIRED"
            )
    return receipt
