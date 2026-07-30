"""CLI for shared official DAILY archives across all cohort Episodes."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from .canonical import utc_datetime
from .challenger_cohort_daily_archive import (
    ChallengerCohortDailyArchiveError,
    acquire_challenger_cohort_daily_archives,
)
from .challenger_cohort_episode_receipt import (
    ChallengerCohortEpisodeReceiptError,
)
from .market_data import PublicArchiveTransport


_DEFAULT_OUTPUT_BASE = (
    Path.home() / "Library" / "Application Support" / "CryptoQuant"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-cohort-daily-archive-acquire"
    )
    parser.add_argument("--cohort-plan-path", required=True)
    parser.add_argument("--episode-receipt-output-root", required=True)
    parser.add_argument("--install-receipt-path", required=True)
    parser.add_argument("--contract-path", required=True)
    parser.add_argument("--plist-path", required=True)
    parser.add_argument("--archive-output-root", required=True)
    return parser


def _output_root(value: str, allowed_base: Path) -> Path:
    requested = Path(value).expanduser()
    base = Path(allowed_base).expanduser().resolve()
    if (
        not requested.is_absolute()
        or requested.is_symlink()
        or requested.resolve() == base
        or base not in requested.resolve().parents
    ):
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_OUTPUT_INVALID"
        )
    return requested.resolve()


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    clock=None,
    transport=None,
    receipt_loader=None,
    allowed_output_base=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        observed_at = (
            clock()
            if clock is not None
            else utc_datetime(datetime.now(timezone.utc))
        )
        result = acquire_challenger_cohort_daily_archives(
            cohort_plan_path=Path(arguments.cohort_plan_path),
            episode_receipt_output_root=Path(
                arguments.episode_receipt_output_root
            ),
            install_receipt_path=Path(arguments.install_receipt_path),
            contract_path=Path(arguments.contract_path),
            plist_path=Path(arguments.plist_path),
            archive_output_root=_output_root(
                arguments.archive_output_root,
                allowed_output_base or _DEFAULT_OUTPUT_BASE,
            ),
            observed_at=observed_at,
            transport=transport or PublicArchiveTransport(),
            receipt_loader=receipt_loader,
        )
    except SystemExit as error:
        return int(error.code)
    except (
        ChallengerCohortDailyArchiveError,
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
