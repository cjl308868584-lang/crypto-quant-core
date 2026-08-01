"""Restricted exact-byte release CLI for Challenger failure evidence."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .challenger_cohort_failure_release import (
    ChallengerCohortFailureReleaseError,
    release_challenger_cohort_failure_receipt,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-cohort-failure-release"
    )
    parser.add_argument("--release-kind", choices=("failure",), required=True)
    parser.add_argument("--runtime-receipt-path", required=True)
    parser.add_argument("--artifact-output-path", required=True)
    parser.add_argument("--cohort-plan-path", required=True)
    parser.add_argument("--evaluation-plan-path", required=True)
    parser.add_argument("--install-receipt-path", required=True)
    parser.add_argument("--contract-path", required=True)
    parser.add_argument("--plist-path", required=True)
    return parser


def _absolute(value: str) -> Path:
    selected = Path(value).expanduser()
    if not selected.is_absolute():
        raise ChallengerCohortFailureReleaseError(
            "CHALLENGER_COHORT_FAILURE_RELEASE_PATH_INVALID"
        )
    return selected


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    receipt_loader=None,
) -> int:
    try:
        arguments = _parser().parse_args(argv)
        if arguments.release_kind != "failure":
            raise ChallengerCohortFailureReleaseError(
                "CHALLENGER_COHORT_FAILURE_RELEASE_KIND_INVALID"
            )
        summary = release_challenger_cohort_failure_receipt(
            runtime_receipt_path=_absolute(
                arguments.runtime_receipt_path
            ),
            artifact_output_path=_absolute(
                arguments.artifact_output_path
            ),
            cohort_plan_path=_absolute(arguments.cohort_plan_path),
            evaluation_plan_path=_absolute(
                arguments.evaluation_plan_path
            ),
            install_receipt_path=_absolute(
                arguments.install_receipt_path
            ),
            contract_path=_absolute(arguments.contract_path),
            plist_path=_absolute(arguments.plist_path),
            _receipt_loader=receipt_loader,
        )
    except SystemExit as error:
        return int(error.code)
    except (
        ChallengerCohortFailureReleaseError,
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
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
