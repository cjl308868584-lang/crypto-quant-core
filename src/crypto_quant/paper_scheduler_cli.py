"""One-shot CLI for the durable 4h offline Paper scheduler."""

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence

from .paper_scheduler import PaperScheduleError, run_due_paper_cycle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-scheduler-run")
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--worker-id", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    transport=None,
    clock: Optional[Callable[[], str]] = None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = run_due_paper_cycle(
            state_path=Path(arguments.state_path),
            output_root=Path(arguments.output_root),
            worker_id=arguments.worker_id,
            transport=transport,
            clock=clock,
        )
    except SystemExit as error:
        return int(error.code)
    except (OSError, PaperScheduleError, TypeError, ValueError) as error:
        print(
            json.dumps(
                {"error": str(error)},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    public = {name: value for name, value in result.items() if name != "schedule_snapshot"}
    print(json.dumps(public, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
