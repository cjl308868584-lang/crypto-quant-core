"""Offline CLI for publishing a trusted Challenger episode economic result."""

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Optional, Sequence

from .challenger_episode_archive_acquisition import (
    ChallengerEpisodeArchiveAcquisitionError,
    load_challenger_episode_daily_archives,
)
from .challenger_episode_economic_evaluator import (
    ChallengerEpisodeEconomicEvaluatorError,
    build_challenger_episode_economic_result,
    load_challenger_episode_economic_result,
    publish_challenger_episode_economic_result,
)
from .challenger_first_episode_receipt import (
    ChallengerFirstEpisodeReceiptError,
    load_challenger_first_episode_receipt,
)
from .research_corpus import _strict_json_bytes


_MAX_PLAN_BYTES = 256 * 1024
_MAX_RECEIPT_BYTES = 8 * 1024 * 1024
_DEFAULT_OUTPUT_BASE = (
    Path.home()
    / "Library"
    / "Application Support"
    / "CryptoQuant"
)


class ChallengerEpisodeEconomicResultCLIError(ValueError):
    """A trusted input or output path failed closed."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-episode-economic-result"
    )
    parser.add_argument("--economic-plan-path", required=True)
    parser.add_argument("--completion-receipt-path", required=True)
    parser.add_argument("--install-receipt-path", required=True)
    parser.add_argument("--contract-path", required=True)
    parser.add_argument("--plist-path", required=True)
    parser.add_argument("--archive-output-root", required=True)
    parser.add_argument("--result-output-root", required=True)
    return parser


def _read_input(
    path: Path, maximum_bytes: int, allowed_modes
) -> bytes:
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
        raise ChallengerEpisodeEconomicResultCLIError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_INPUT_INVALID"
        ) from error


def _trusted_root(
    value: str,
    *,
    allowed_base: Path,
    reason_code: str,
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
                or stat.S_IMODE(status.st_mode) != 0o700
            ):
                raise ValueError
        return resolved
    except Exception as error:
        raise ChallengerEpisodeEconomicResultCLIError(
            reason_code
        ) from error


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    receipt_loader=None,
    archive_loader=None,
    result_builder=None,
    result_publisher=None,
    result_loader=None,
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
        plan_file_sha256 = hashlib.sha256(plan_bytes).hexdigest()

        completion_receipt_path = Path(
            arguments.completion_receipt_path
        )
        completion_receipt_bytes = _read_input(
            completion_receipt_path,
            _MAX_RECEIPT_BYTES,
            (0o600,),
        )
        completion_receipt = (
            receipt_loader or load_challenger_first_episode_receipt
        )(
            receipt_path=completion_receipt_path,
            install_receipt_path=Path(arguments.install_receipt_path),
            contract_path=Path(arguments.contract_path),
            plist_path=Path(arguments.plist_path),
        )
        completion_receipt_file_sha256 = hashlib.sha256(
            completion_receipt_bytes
        ).hexdigest()

        base = allowed_output_base or _DEFAULT_OUTPUT_BASE
        archive_root = _trusted_root(
            arguments.archive_output_root,
            allowed_base=base,
            reason_code=(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_ARCHIVE_ROOT_INVALID"
            ),
        )
        result_root = _trusted_root(
            arguments.result_output_root,
            allowed_base=base,
            reason_code=(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_OUTPUT_INVALID"
            ),
        )
        if (
            result_root == archive_root
            or result_root in archive_root.parents
            or archive_root in result_root.parents
        ):
            raise ChallengerEpisodeEconomicResultCLIError(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_OUTPUT_INVALID"
            )
        daily_archives = (
            archive_loader or load_challenger_episode_daily_archives
        )(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            completion_receipt=completion_receipt,
            completion_receipt_file_sha256=(
                completion_receipt_file_sha256
            ),
            output_root=archive_root,
        )
        try:
            evaluated_at = max(
                value[2] for value in daily_archives.values()
            )
        except (AttributeError, IndexError, TypeError, ValueError) as error:
            raise ChallengerEpisodeEconomicResultCLIError(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_ARCHIVE_SET_INVALID"
            ) from error

        common = {
            "plan": plan,
            "plan_file_sha256": plan_file_sha256,
            "completion_receipt": completion_receipt,
            "completion_receipt_file_sha256": (
                completion_receipt_file_sha256
            ),
            "daily_archives": daily_archives,
        }
        result = (
            result_builder or build_challenger_episode_economic_result
        )(
            **common,
            evaluated_at=evaluated_at,
        )
        output_path = result_root / f"{result['result_id']}.json"
        (
            result_publisher
            or publish_challenger_episode_economic_result
        )(
            result=result,
            output_path=output_path,
            **common,
        )
        loaded = (
            result_loader or load_challenger_episode_economic_result
        )(
            result_path=output_path,
            **common,
        )
        if loaded != result:
            raise ChallengerEpisodeEconomicResultCLIError(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_RELOAD_MISMATCH"
            )
        result_bytes = output_path.read_bytes()
        summary = {
            "status": result["status"],
            "result_path": str(output_path),
            "result_file_sha256": hashlib.sha256(
                result_bytes
            ).hexdigest(),
            "result_id": result["result_id"],
            "result_hash": result["result_hash"],
            "evaluated_at": result["evaluated_at"],
            "net_pnl_usdt": result["economics"]["net_pnl_usdt"],
            "net_return": result["economics"]["net_return"],
            "eligibility": result["eligibility"],
            "warnings": result["warnings"],
            "security_boundary": result["security_boundary"],
        }
    except SystemExit as error:
        return int(error.code)
    except (
        ChallengerEpisodeArchiveAcquisitionError,
        ChallengerEpisodeEconomicEvaluatorError,
        ChallengerEpisodeEconomicResultCLIError,
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
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
