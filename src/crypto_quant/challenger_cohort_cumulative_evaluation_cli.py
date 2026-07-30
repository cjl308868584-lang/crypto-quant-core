"""Offline CLI for the fixed-tail Challenger cohort evaluation."""

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Optional, Sequence

from .challenger_cohort_cumulative_evaluation import (
    ChallengerCohortCumulativeEvaluationError,
    evaluate_challenger_cohort,
)


_DEFAULT_OUTPUT_BASE = (
    Path.home() / "Library" / "Application Support" / "CryptoQuant"
)


class ChallengerCohortCumulativeEvaluationCLIError(ValueError):
    """A CLI path or invocation failed closed."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-cohort-cumulative-evaluation"
    )
    parser.add_argument("--cohort-plan-path", required=True)
    parser.add_argument("--evaluation-plan-path", required=True)
    parser.add_argument("--economic-plan-path", required=True)
    parser.add_argument("--pilot-result-path", required=True)
    parser.add_argument("--install-receipt-path", required=True)
    parser.add_argument("--contract-path", required=True)
    parser.add_argument("--plist-path", required=True)
    parser.add_argument("--episode-receipt-output-root", required=True)
    parser.add_argument("--archive-output-root", required=True)
    parser.add_argument("--result-output-root", required=True)
    parser.add_argument("--evaluation-output-root", required=True)
    return parser


def _trusted_root(
    value: str,
    *,
    allowed_base: Path,
    may_not_exist: bool,
    allowed_modes=(0o700,),
) -> Path:
    try:
        requested = Path(value).expanduser()
        base = Path(allowed_base).expanduser().resolve(strict=True)
        if not requested.is_absolute() or requested.is_symlink():
            raise ValueError
        resolved = requested.resolve()
        if resolved == base or base not in resolved.parents:
            raise ValueError
        if resolved.exists():
            status = resolved.lstat()
            if (
                not stat.S_ISDIR(status.st_mode)
                or stat.S_ISLNK(status.st_mode)
                or status.st_uid != os.getuid()
                or stat.S_IMODE(status.st_mode) not in allowed_modes
                or resolved.resolve(strict=True) != resolved.absolute()
            ):
                raise ValueError
        elif not may_not_exist:
            raise ValueError
        return resolved
    except Exception as error:
        raise ChallengerCohortCumulativeEvaluationCLIError(
            "CHALLENGER_COHORT_CUMULATIVE_ROOT_INVALID"
        ) from error


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    allowed_output_base=None,
    evaluator=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        base = allowed_output_base or _DEFAULT_OUTPUT_BASE
        receipt_root = _trusted_root(
            arguments.episode_receipt_output_root,
            allowed_base=base,
            may_not_exist=True,
            allowed_modes=(0o700, 0o755),
        )
        archive_root = _trusted_root(
            arguments.archive_output_root,
            allowed_base=base,
            may_not_exist=True,
        )
        result_root = _trusted_root(
            arguments.result_output_root,
            allowed_base=base,
            may_not_exist=True,
        )
        evaluation_root = _trusted_root(
            arguments.evaluation_output_root,
            allowed_base=base,
            may_not_exist=True,
        )
        roots = (
            receipt_root,
            archive_root,
            result_root,
            evaluation_root,
        )
        for index, left in enumerate(roots):
            for right in roots[index + 1 :]:
                if (
                    left == right
                    or left in right.parents
                    or right in left.parents
                ):
                    raise ChallengerCohortCumulativeEvaluationCLIError(
                        "CHALLENGER_COHORT_CUMULATIVE_ROOT_OVERLAP"
                    )
        summary = (evaluator or evaluate_challenger_cohort)(
            cohort_plan_path=Path(arguments.cohort_plan_path),
            evaluation_plan_path=Path(arguments.evaluation_plan_path),
            economic_plan_path=Path(arguments.economic_plan_path),
            pilot_result_path=Path(arguments.pilot_result_path),
            install_receipt_path=Path(arguments.install_receipt_path),
            contract_path=Path(arguments.contract_path),
            plist_path=Path(arguments.plist_path),
            episode_receipt_output_root=receipt_root,
            archive_output_root=archive_root,
            result_output_root=result_root,
            evaluation_output_root=evaluation_root,
        )
    except SystemExit as error:
        return int(error.code)
    except (
        ChallengerCohortCumulativeEvaluationCLIError,
        ChallengerCohortCumulativeEvaluationError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {
                    "status": "FAILED_CLOSED_NO_BACKFILL",
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
