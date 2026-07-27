"""CLI for one due, public-only challenger forward cycle."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .challenger_forward_runner import (
    ChallengerForwardRunnerError,
    run_challenger_forward_cycle,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="challenger-forward-run")
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--output-root", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    server_time_transport=None,
    kline_transport=None,
    runtime_gate=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = run_challenger_forward_cycle(
            state_path=Path(arguments.state_path),
            output_root=Path(arguments.output_root),
            server_time_transport=server_time_transport,
            kline_transport=kline_transport,
            runtime_gate=runtime_gate,
        )
    except SystemExit as error:
        return int(error.code)
    except (OSError, TypeError, ValueError, ChallengerForwardRunnerError) as error:
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
