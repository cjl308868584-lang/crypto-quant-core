"""CLI that renders but never installs a local LaunchAgent."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .local_scheduler import (
    LocalSchedulerError,
    publish_local_scheduler_contract,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-cycle-launchd-render"
    )
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--python-executable", required=True)
    parser.add_argument("--api-key-file", required=True)
    parser.add_argument("--api-secret-file", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--output-root", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    clock=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = publish_local_scheduler_contract(
            output_root=Path(arguments.output_root),
            repository_root=Path(arguments.repository_root),
            runtime_root=Path(arguments.runtime_root),
            python_executable=Path(arguments.python_executable),
            api_key_file=Path(arguments.api_key_file),
            api_secret_file=Path(arguments.api_secret_file),
            worker_id=arguments.worker_id,
            clock=clock,
        )
    except SystemExit as error:
        return int(error.code)
    except (
        OSError,
        LocalSchedulerError,
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
