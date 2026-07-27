"""One-shot CLI for recoverable context-complete orchestration."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .account_commission import AccountCommissionError
from .context_cycle_orchestrator import (
    ContextCycleOrchestrationError,
    run_context_complete_orchestration,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-complete-cycle-run"
    )
    parser.add_argument(
        "--orchestration-state-path", required=True
    )
    parser.add_argument("--paper-state-path", required=True)
    parser.add_argument("--context-state-path", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--worker-id", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    signer=None,
    workspace_root=None,
    server_time_transport=None,
    account_transport=None,
    paper_transport=None,
    futures_transport=None,
    monotonic_ns=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = run_context_complete_orchestration(
            orchestration_state_path=Path(
                arguments.orchestration_state_path
            ),
            paper_state_path=Path(arguments.paper_state_path),
            context_state_path=Path(arguments.context_state_path),
            output_root=Path(arguments.output_root),
            worker_id=arguments.worker_id,
            signer=signer,
            workspace_root=workspace_root,
            server_time_transport=server_time_transport,
            account_transport=account_transport,
            paper_transport=paper_transport,
            futures_transport=futures_transport,
            monotonic_ns=monotonic_ns,
        )
    except SystemExit as error:
        return int(error.code)
    except (
        OSError,
        AccountCommissionError,
        ContextCycleOrchestrationError,
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
