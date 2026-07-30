"""CLI for read-only, all-inclusive Challenger cohort Episode receipts."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .challenger_cohort_episode_receipt import (
    ChallengerCohortEpisodeReceiptError,
    observe_challenger_cohort_episodes,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-cohort-episode-observe"
    )
    parser.add_argument("--cohort-plan-path", required=True)
    parser.add_argument("--install-receipt-path", required=True)
    parser.add_argument("--contract-path", required=True)
    parser.add_argument("--plist-path", required=True)
    parser.add_argument("--receipt-output-root", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    clock=None,
    launchctl_runner=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = observe_challenger_cohort_episodes(
            cohort_plan_path=Path(arguments.cohort_plan_path),
            install_receipt_path=Path(arguments.install_receipt_path),
            contract_path=Path(arguments.contract_path),
            plist_path=Path(arguments.plist_path),
            receipt_output_root=Path(arguments.receipt_output_root),
            clock=clock,
            _launchctl_runner=launchctl_runner,
        )
    except SystemExit as error:
        return int(error.code)
    except (
        ChallengerCohortEpisodeReceiptError,
        OSError,
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
