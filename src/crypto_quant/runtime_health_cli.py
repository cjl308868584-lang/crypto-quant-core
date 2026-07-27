"""One-shot CLI for time-gated Paper runtime health."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .runtime_health import (
    RuntimeHealthError,
    run_healthy_paper_cycle,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-runtime-run")
    parser.add_argument("--runtime-state-path", required=True)
    parser.add_argument("--scheduler-state-path", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--worker-id", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    server_time_transport=None,
    paper_transport=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = run_healthy_paper_cycle(
            runtime_state_path=Path(arguments.runtime_state_path),
            scheduler_state_path=Path(arguments.scheduler_state_path),
            output_root=Path(arguments.output_root),
            worker_id=arguments.worker_id,
            server_time_transport=server_time_transport,
            paper_transport=paper_transport,
        )
    except SystemExit as error:
        return int(error.code)
    except (
        OSError,
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
    public = {
        name: value
        for name, value in result.items()
        if name != "runtime_snapshot"
    }
    print(json.dumps(public, sort_keys=True, separators=(",", ":")))
    return 1 if result["outcome"] in ("CLOCK_BLOCKED", "SCHEDULER_FAILED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
