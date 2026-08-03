"""Render, but never install, the System Paper LaunchAgent contract."""

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from .canonical import canonical_json
from .system_paper_launchd import (
    SystemPaperLaunchdError,
    publish_system_paper_launchd_contract,
)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_CLI_ARGUMENT_INVALID"
        )


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="system-paper-launchd-render")
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--python-executable", required=True)
    parser.add_argument("--output-root", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    clock=None,
    _command_runner=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = publish_system_paper_launchd_contract(
            output_root=Path(arguments.output_root),
            repository_root=Path(arguments.repository_root),
            runtime_root=Path(arguments.runtime_root),
            python_executable=Path(arguments.python_executable),
            clock=clock,
            _command_runner=_command_runner,
        )
    except SystemExit as error:
        return int(error.code)
    except (OSError, TypeError, ValueError, SystemPaperLaunchdError) as error:
        reason = getattr(error, "reason_code", "SYSTEM_PAPER_LAUNCHD_CLI_FAILED")
        print(
            canonical_json(
                {
                    "error": "SYSTEM_PAPER_LAUNCHD_RENDER_FAILED",
                    "reason_code": reason,
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
