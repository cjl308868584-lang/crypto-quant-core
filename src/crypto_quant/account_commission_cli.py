"""One-shot CLI for current account commission evidence."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .account_commission import (
    AccountCommissionError,
    publish_account_commission,
)
from .runtime_health import RuntimeHealthError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="account-commission-capture")
    parser.add_argument("--output-root", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    signer=None,
    server_time_transport=None,
    account_transport=None,
    workspace_root=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = publish_account_commission(
            output_root=Path(arguments.output_root),
            signer=signer,
            server_time_transport=server_time_transport,
            account_transport=account_transport,
            workspace_root=workspace_root,
        )
    except SystemExit as error:
        return int(error.code)
    except (
        OSError,
        AccountCommissionError,
        RuntimeHealthError,
        TypeError,
        ValueError,
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
