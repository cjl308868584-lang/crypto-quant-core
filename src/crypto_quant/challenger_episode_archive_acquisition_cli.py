"""CLI for trusted, recoverable Challenger episode DAILY archives."""

import argparse
import hashlib
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from .canonical import utc_datetime
from .challenger_episode_archive_acquisition import (
    ChallengerEpisodeArchiveAcquisitionError,
    acquire_challenger_episode_archives,
)
from .challenger_first_episode_receipt import (
    ChallengerFirstEpisodeReceiptError,
    load_challenger_first_episode_receipt,
)
from .market_data import PublicArchiveTransport
from .research_corpus import _strict_json_bytes


_MAX_PLAN_BYTES = 256 * 1024
_MAX_RECEIPT_BYTES = 8 * 1024 * 1024
_DEFAULT_OUTPUT_BASE = (
    Path.home()
    / "Library"
    / "Application Support"
    / "CryptoQuant"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-episode-archive-acquire"
    )
    parser.add_argument("--economic-plan-path", required=True)
    parser.add_argument("--completion-receipt-path", required=True)
    parser.add_argument("--install-receipt-path", required=True)
    parser.add_argument("--contract-path", required=True)
    parser.add_argument("--plist-path", required=True)
    parser.add_argument("--archive-output-root", required=True)
    return parser


def _read_input(path: Path, maximum_bytes: int, allowed_modes) -> bytes:
    try:
        requested = Path(path).expanduser()
        status = requested.lstat()
        if (
            not requested.is_absolute()
            or stat.S_ISLNK(status.st_mode)
            or not stat.S_ISREG(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) not in allowed_modes
            or status.st_size <= 0
            or status.st_size > maximum_bytes
        ):
            raise ValueError
        return requested.resolve(strict=True).read_bytes()
    except Exception as error:
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_INPUT_INVALID"
        ) from error


def _output_root(value: str, allowed_base: Path) -> Path:
    requested = Path(value).expanduser()
    base = Path(allowed_base).expanduser().resolve()
    if (
        not requested.is_absolute()
        or requested.is_symlink()
        or requested.resolve() == base
        or base not in requested.resolve().parents
    ):
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_OUTPUT_INVALID"
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
        plan_bytes = _read_input(
            Path(arguments.economic_plan_path),
            _MAX_PLAN_BYTES,
            (0o600, 0o644),
        )
        plan = _strict_json_bytes(
            plan_bytes[:-1]
            if plan_bytes.endswith(b"\n")
            else plan_bytes
        )
        receipt_path = Path(arguments.completion_receipt_path)
        receipt = (
            receipt_loader or load_challenger_first_episode_receipt
        )(
            receipt_path=receipt_path,
            install_receipt_path=Path(arguments.install_receipt_path),
            contract_path=Path(arguments.contract_path),
            plist_path=Path(arguments.plist_path),
        )
        receipt_bytes = _read_input(
            receipt_path, _MAX_RECEIPT_BYTES, (0o600,)
        )
        observed_at = (
            clock() if clock is not None else utc_datetime(
                datetime.now(timezone.utc)
            )
        )
        result = acquire_challenger_episode_archives(
            plan=plan,
            plan_file_sha256=hashlib.sha256(plan_bytes).hexdigest(),
            completion_receipt=receipt,
            completion_receipt_file_sha256=hashlib.sha256(
                receipt_bytes
            ).hexdigest(),
            output_root=_output_root(
                arguments.archive_output_root,
                allowed_output_base or _DEFAULT_OUTPUT_BASE,
            ),
            observed_at=observed_at,
            transport=transport or PublicArchiveTransport(),
        )
    except SystemExit as error:
        return int(error.code)
    except (
        ChallengerEpisodeArchiveAcquisitionError,
        ChallengerFirstEpisodeReceiptError,
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
