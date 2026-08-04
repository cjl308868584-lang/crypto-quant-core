"""One-shot, credential-free System Paper runtime CLI."""

import argparse
import os
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from .canonical import business_hash, canonical_json, utc_datetime
from .system_paper_broker import FillScenario
from .system_paper_plan import build_system_paper_plan
from .system_paper_public_input import (
    SystemPaperPublicInputError,
    capture_system_paper_input,
)
from .system_paper_scheduler import (
    SystemPaperScheduleError,
    run_due_system_paper_slot,
)


_SERVICE_LABEL = "local.crypto-quant.system-paper-v1"


class SystemPaperRuntimeCliError(ValueError):
    """The bounded runtime CLI rejected its invocation."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise SystemPaperRuntimeCliError(
            "SYSTEM_PAPER_RUNTIME_CLI_ARGUMENT_INVALID"
        )


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="system-paper-run")
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--output-root", required=True)
    return parser


def _utc_now() -> str:
    return utc_datetime(datetime.now(timezone.utc))


def _reject_symlink_ancestors(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            entry = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(entry.st_mode):
            raise SystemPaperRuntimeCliError(
                "SYSTEM_PAPER_RUNTIME_CLI_PATH_INVALID"
            )


def _absolute_path(value: object) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SystemPaperRuntimeCliError(
            "SYSTEM_PAPER_RUNTIME_CLI_PATH_INVALID"
        )
    path = Path(value)
    if (
        not path.is_absolute()
        or path.name in ("", ".", "..")
        or ".." in path.parts
    ):
        raise SystemPaperRuntimeCliError(
            "SYSTEM_PAPER_RUNTIME_CLI_PATH_INVALID"
        )
    _reject_symlink_ancestors(path)
    return path


def _owner_only_directory(path: Path) -> None:
    try:
        entry = path.lstat()
    except OSError as error:
        raise SystemPaperRuntimeCliError(
            "SYSTEM_PAPER_RUNTIME_CLI_PATH_INVALID"
        ) from error
    if (
        not stat.S_ISDIR(entry.st_mode)
        or entry.st_uid != os.getuid()
        or stat.S_IMODE(entry.st_mode) != 0o700
    ):
        raise SystemPaperRuntimeCliError(
            "SYSTEM_PAPER_RUNTIME_CLI_PATH_UNSAFE"
        )


def _validated_paths(state_value: object, output_value: object):
    state_path = _absolute_path(state_value)
    output_root = _absolute_path(output_value)
    _owner_only_directory(state_path.parent)
    _owner_only_directory(output_root)
    if state_path.exists() or state_path.is_symlink():
        try:
            entry = state_path.lstat()
        except OSError as error:
            raise SystemPaperRuntimeCliError(
                "SYSTEM_PAPER_RUNTIME_CLI_PATH_INVALID"
            ) from error
        if (
            not stat.S_ISREG(entry.st_mode)
            or entry.st_uid != os.getuid()
            or stat.S_IMODE(entry.st_mode) != 0o600
            or entry.st_nlink != 1
        ):
            raise SystemPaperRuntimeCliError(
                "SYSTEM_PAPER_RUNTIME_CLI_PATH_UNSAFE"
            )
    return state_path, output_root


def _worker_id(worker_identity: Optional[str]) -> str:
    identity = (
        f"{os.getpid()}:{time.monotonic_ns()}"
        if worker_identity is None
        else worker_identity
    )
    if (
        not isinstance(identity, str)
        or not identity
        or len(identity) > 256
        or not identity.isascii()
    ):
        raise SystemPaperRuntimeCliError(
            "SYSTEM_PAPER_RUNTIME_CLI_WORKER_IDENTITY_INVALID"
        )
    return business_hash(
        {
            "service_label": _SERVICE_LABEL,
            "process_id": os.getpid(),
            "invocation_identity": identity,
        }
    )


def _error_reason(error: BaseException) -> str:
    reason = getattr(error, "reason_code", None)
    if isinstance(reason, str) and reason:
        return reason
    if isinstance(error, OSError):
        return "SYSTEM_PAPER_RUNTIME_CLI_IO_FAILED"
    return "SYSTEM_PAPER_RUNTIME_CLI_FAILED"


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    transport=None,
    clock=None,
    worker_identity: Optional[str] = None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        state_path, output_root = _validated_paths(
            arguments.state_path,
            arguments.output_root,
        )
        worker_id = _worker_id(worker_identity)
        runtime_clock = clock or _utc_now
        previous_umask = os.umask(0o077)
        try:
            result = run_due_system_paper_slot(
                state_path=state_path,
                output_root=output_root,
                plan=build_system_paper_plan(),
                worker_id=worker_id,
                public_input_provider=lambda request: capture_system_paper_input(
                    request,
                    transport=transport,
                    clock=runtime_clock,
                ),
                fill_scenario=FillScenario.partial_then_full("0.40"),
                clock=runtime_clock,
            )
        finally:
            os.umask(previous_umask)
    except SystemExit as error:
        return int(error.code)
    except (
        OSError,
        TypeError,
        ValueError,
        SystemPaperPublicInputError,
        SystemPaperScheduleError,
    ) as error:
        print(
            canonical_json(
                {
                    "error": "SYSTEM_PAPER_RUNTIME_CLI_INVOCATION_FAILED",
                    "reason_code": _error_reason(error),
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
