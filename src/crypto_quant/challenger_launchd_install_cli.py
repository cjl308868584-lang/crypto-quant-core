"""CLI for the fixed user-domain challenger LaunchAgent installation."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .challenger_launchd_install import (
    ChallengerLaunchdInstallError,
    install_challenger_launchd,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-launchd-install"
    )
    parser.add_argument("--contract-path", required=True)
    parser.add_argument("--plist-path", required=True)
    parser.add_argument("--receipt-output-root", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    clock=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = install_challenger_launchd(
            contract_path=Path(arguments.contract_path),
            plist_path=Path(arguments.plist_path),
            receipt_output_root=Path(arguments.receipt_output_root),
            clock=clock,
        )
    except SystemExit as error:
        return int(error.code)
    except (
        OSError,
        TypeError,
        ValueError,
        ChallengerLaunchdInstallError,
    ) as error:
        print(
            json.dumps(
                {"error": str(error)},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
