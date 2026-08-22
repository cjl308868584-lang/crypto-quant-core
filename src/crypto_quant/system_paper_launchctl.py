"""Bounded semantic parser for the frozen System Paper launchctl service."""

import re
from typing import Any, Dict, Mapping


_LABEL = "local.crypto-quant.system-paper-v1"
_MAX_BYTES = 64 * 1024
_MAX_RUNS = 2**63 - 1
_SERVICE = re.compile(r"^(gui/[0-9]+)/(" + re.escape(_LABEL) + r") = \{$")
_SCALAR = re.compile(r"^\t([^=]+?) = (.*)$")
_BLOCK = re.compile(r"^\t([^=]+?) = \{$")
_ENVIRONMENT = re.compile(r"^[ \t]+([A-Z][A-Z0-9_]*) => (.+)$")
_FIELD_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 ,()_-]*$")


class SystemPaperLaunchctlParseError(ValueError):
    """The launchctl print bytes are not the frozen bounded grammar."""

    def __init__(self, reason_code="SYSTEM_PAPER_LAUNCHCTL_PRINT_INVALID"):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _text(data: bytes) -> str:
    if not isinstance(data, bytes) or not data or len(data) > _MAX_BYTES:
        raise SystemPaperLaunchctlParseError()
    try:
        value = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SystemPaperLaunchctlParseError() from error
    if (
        "\x00" in value
        or "\r" in value
        or not value.endswith("\n")
        or any(character < " " and character not in "\n\t" for character in value)
    ):
        raise SystemPaperLaunchctlParseError()
    return value


def _integer(value: str, *, maximum: int) -> int:
    if not re.fullmatch(r"0|[1-9][0-9]*", value):
        raise SystemPaperLaunchctlParseError()
    parsed = int(value)
    if parsed > maximum:
        raise SystemPaperLaunchctlParseError()
    return parsed


def _block(lines, start):
    values = []
    index = start + 1
    while index < len(lines):
        line = lines[index]
        if line == "\t}":
            return values, index + 1
        if not line.startswith("\t\t") or line.startswith("\t\t\t"):
            raise SystemPaperLaunchctlParseError()
        values.append(line[2:])
        index += 1
    raise SystemPaperLaunchctlParseError()


def _ignored_block(lines, start):
    depth = 1
    index = start + 1
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.endswith("{"):
            depth += 1
        elif stripped == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise SystemPaperLaunchctlParseError()


def _parse_launchctl_structure(data: bytes, label: str):
    lines = _text(data).splitlines()
    if len(lines) < 3 or lines[-1] != "}":
        raise SystemPaperLaunchctlParseError()
    pattern = re.compile(r"^(gui/[0-9]+)/(" + re.escape(label) + r") = \{$")
    if pattern.fullmatch(lines[0]) is None:
        raise SystemPaperLaunchctlParseError()
    service = lines[0][:-4]
    scalars: Dict[str, str] = {}
    blocks: Dict[str, Any] = {}
    seen_names = set()
    index = 1
    while index < len(lines) - 1:
        line = lines[index]
        if line == "":
            index += 1
            continue
        if line.strip() == "}":
            raise SystemPaperLaunchctlParseError()
        block_match = _BLOCK.fullmatch(line)
        if block_match is not None:
            name = block_match.group(1)
            if _FIELD_NAME.fullmatch(name) is None or name in seen_names:
                raise SystemPaperLaunchctlParseError()
            seen_names.add(name)
            if name in ("arguments", "environment"):
                blocks[name], index = _block(lines, index)
            else:
                index = _ignored_block(lines, index)
            continue
        scalar_match = _SCALAR.fullmatch(line)
        if scalar_match is not None:
            name, value = scalar_match.groups()
            if _FIELD_NAME.fullmatch(name) is None or name in seen_names:
                raise SystemPaperLaunchctlParseError()
            seen_names.add(name)
            if name in {"path", "state", "program", "working directory",
                        "runs", "last exit code", "last exit status"}:
                scalars[name] = value
            index += 1
            continue
        raise SystemPaperLaunchctlParseError()
    return service, scalars, blocks


def parse_system_paper_launchctl_print(data: bytes) -> Mapping[str, Any]:
    """Parse one exact System Paper service print without substring trust."""
    service, scalars, blocks = _parse_launchctl_structure(data, _LABEL)

    required = {"path", "state", "program", "working directory", "runs"}
    if set(scalars).intersection(required) != required:
        raise SystemPaperLaunchctlParseError()
    if "arguments" not in blocks or "environment" not in blocks:
        raise SystemPaperLaunchctlParseError()
    if "last exit code" in scalars and "last exit status" in scalars:
        raise SystemPaperLaunchctlParseError()
    path = scalars["path"]
    program = scalars["program"]
    working_directory = scalars["working directory"]
    state = scalars["state"]
    arguments = blocks["arguments"]
    if (
        not path.startswith("/")
        or not path.endswith(f"/{_LABEL}.plist")
        or not program.startswith("/")
        or not working_directory.startswith("/")
        or not re.fullmatch(r"[A-Za-z0-9 _-]{1,64}", state)
        or len(arguments) != 7
        or arguments[0] != program
        or arguments[1:4]
        != ["-m", "crypto_quant.system_paper_runtime_cli", "--state-path"]
        or not arguments[4].startswith("/")
        or arguments[5] != "--output-root"
        or not arguments[6].startswith("/")
    ):
        raise SystemPaperLaunchctlParseError()
    environment = {}
    for line in blocks["environment"]:
        match = _ENVIRONMENT.fullmatch("\t\t" + line)
        if match is None or match.group(1) in environment:
            raise SystemPaperLaunchctlParseError()
        environment[match.group(1)] = match.group(2)
    if (
        set(environment) != {"PYTHONPATH", "XPC_SERVICE_NAME"}
        or not environment["PYTHONPATH"].startswith("/")
        or environment["XPC_SERVICE_NAME"] != _LABEL
    ):
        raise SystemPaperLaunchctlParseError()
    runs = _integer(scalars["runs"], maximum=_MAX_RUNS)
    exit_value = scalars.get("last exit code", scalars.get("last exit status"))
    if runs == 0:
        if exit_value != "(never exited)":
            raise SystemPaperLaunchctlParseError()
        last_exit_status = None
    else:
        if exit_value is None or exit_value == "(never exited)":
            raise SystemPaperLaunchctlParseError()
        last_exit_status = _integer(exit_value, maximum=255)
    return {
        "label": _LABEL,
        "service": service,
        "path": path,
        "program": program,
        "arguments": list(arguments),
        "working_directory": working_directory,
        "environment": environment,
        "runs": runs,
        "state": state,
        "last_exit_status": last_exit_status,
    }


def parse_challenger_replacement_launchctl_print(
    data: bytes, contract: Mapping[str, Any], expected_runs: int = 0
) -> Mapping[str, Any]:
    label = contract["service"]["label"]
    service, scalars, blocks = _parse_launchctl_structure(data, label)
    required = {"path", "state", "program", "working directory", "runs"}
    environment = {}
    for line in blocks.get("environment", ()):
        match = _ENVIRONMENT.fullmatch("\t\t" + line)
        if match is None or match.group(1) in environment:
            raise SystemPaperLaunchctlParseError()
        environment[match.group(1)] = match.group(2)
    expected_environment = {
        **contract["runtime"]["environment"], "XPC_SERVICE_NAME": label,
    }
    if (
        set(scalars).intersection(required) != required
        or set(blocks) != {"arguments", "environment"}
        or scalars["path"] != contract["paths"]["target_plist"]
        or scalars["state"] != "not running"
        or scalars["program"] != contract["runtime"]["program_arguments"][0]
        or blocks["arguments"] != contract["runtime"]["program_arguments"]
        or scalars["working directory"] != contract["runtime"]["working_directory"]
        or environment != expected_environment
        or not isinstance(expected_runs, int)
        or isinstance(expected_runs, bool)
        or not 0 <= expected_runs <= _MAX_RUNS
        or _integer(scalars["runs"], maximum=_MAX_RUNS) != expected_runs
        or scalars.get("last exit code", scalars.get("last exit status"))
        != ("(never exited)" if expected_runs == 0 else "0")
    ):
        raise SystemPaperLaunchctlParseError()
    return {"service": service, "label": label, "runs": expected_runs}
