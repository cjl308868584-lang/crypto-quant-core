"""Restricted CLI for receipt-first Challenger service decommission."""

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Optional, Sequence

from .challenger_cohort_decommission import (
    ChallengerCohortDecommissionError,
    decommission_failed_challenger_cohort,
)
from .challenger_cohort_failure import ChallengerCohortFailureError


_DEFAULT_OUTPUT_BASE = (
    Path.home() / "Library" / "Application Support" / "CryptoQuant"
)


class ChallengerCohortDecommissionCLIError(ValueError):
    """A CLI path crossed the fixed decommission authority boundary."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-cohort-decommission"
    )
    parser.add_argument("--failure-receipt-path", required=True)
    parser.add_argument("--cohort-plan-path", required=True)
    parser.add_argument("--evaluation-plan-path", required=True)
    parser.add_argument("--install-receipt-path", required=True)
    parser.add_argument("--contract-path", required=True)
    parser.add_argument("--plist-path", required=True)
    parser.add_argument("--failure-output-root", required=True)
    return parser


def _trusted_input(value: str) -> Path:
    try:
        requested = Path(value).expanduser()
        file_stat = requested.lstat()
        if (
            not requested.is_absolute()
            or requested.is_symlink()
            or requested.resolve(strict=True) != requested.absolute()
            or not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_uid != os.getuid()
            or file_stat.st_nlink != 1
            or file_stat.st_size <= 0
        ):
            raise ValueError
        return requested.resolve(strict=True)
    except Exception as error:
        raise ChallengerCohortDecommissionCLIError(
            "CHALLENGER_COHORT_DECOMMISSION_INPUT_INVALID"
        ) from error


def _trusted_output_root(value: str, *, allowed_base: Path) -> Path:
    try:
        requested = Path(value).expanduser()
        base = Path(allowed_base).expanduser().resolve(strict=True)
        if (
            not requested.is_absolute()
            or requested.is_symlink()
            or requested.resolve() != requested.absolute()
        ):
            raise ValueError
        resolved = requested.resolve()
        root_stat = resolved.lstat()
        if (
            resolved == base
            or base not in resolved.parents
            or not stat.S_ISDIR(root_stat.st_mode)
            or stat.S_ISLNK(root_stat.st_mode)
            or root_stat.st_uid != os.getuid()
            or stat.S_IMODE(root_stat.st_mode) != 0o700
        ):
            raise ValueError
        return resolved
    except Exception as error:
        raise ChallengerCohortDecommissionCLIError(
            "CHALLENGER_COHORT_DECOMMISSION_OUTPUT_INVALID"
        ) from error


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    allowed_output_base=None,
    command_runner=None,
) -> int:
    try:
        arguments = _parser().parse_args(argv)
        summary = decommission_failed_challenger_cohort(
            failure_receipt_path=_trusted_input(
                arguments.failure_receipt_path
            ),
            cohort_plan_path=_trusted_input(arguments.cohort_plan_path),
            evaluation_plan_path=_trusted_input(
                arguments.evaluation_plan_path
            ),
            install_receipt_path=_trusted_input(
                arguments.install_receipt_path
            ),
            contract_path=_trusted_input(arguments.contract_path),
            plist_path=_trusted_input(arguments.plist_path),
            failure_output_root=_trusted_output_root(
                arguments.failure_output_root,
                allowed_base=allowed_output_base or _DEFAULT_OUTPUT_BASE,
            ),
            _command_runner=command_runner,
        )
    except SystemExit as error:
        return int(error.code)
    except (
        ChallengerCohortDecommissionCLIError,
        ChallengerCohortDecommissionError,
        ChallengerCohortFailureError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {
                    "status": "FAILED_CLOSED_DECOMMISSION_UNVERIFIED",
                    "error": str(error),
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
