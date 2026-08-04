"""Evaluate the frozen System Paper cohort from its seven authority paths."""

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from .canonical import canonical_json
from .system_paper_evaluation import (
    SystemPaperEvaluationError,
    evaluate_system_paper,
)


_MAX_ERROR_BYTES = 512
_ERROR = "SYSTEM_PAPER_EVALUATION_CLI_INVOCATION_FAILED"
_ARGUMENT_INVALID = "SYSTEM_PAPER_EVALUATION_CLI_ARGUMENT_INVALID"
_PATH_INVALID = "SYSTEM_PAPER_EVALUATION_CLI_PATH_INVALID"


class SystemPaperEvaluationCliError(ValueError):
    """The fixed evaluation CLI rejected its invocation."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise SystemPaperEvaluationCliError(_ARGUMENT_INVALID)


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="system-paper-evaluation", allow_abbrev=False)
    parser.add_argument("--plan-path", required=True)
    parser.add_argument("--start-receipt-path", required=True)
    parser.add_argument("--install-receipt-path", required=True)
    parser.add_argument("--contract-path", required=True)
    parser.add_argument("--slot-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--output-root", required=True)
    return parser


def _absolute_path(value: object) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SystemPaperEvaluationCliError(_PATH_INVALID)
    path = Path(value)
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise SystemPaperEvaluationCliError(_PATH_INVALID)
    return path


def _error_reason(error: BaseException) -> str:
    reason = getattr(error, "reason_code", None)
    if (
        isinstance(reason, str)
        and reason.isascii()
        and reason.replace("_", "").isalnum()
        and len(reason) <= 160
    ):
        return reason
    if isinstance(error, OSError):
        return "SYSTEM_PAPER_EVALUATION_CLI_IO_FAILED"
    return "SYSTEM_PAPER_EVALUATION_CLI_FAILED"


def _write_error(error: BaseException) -> None:
    payload = canonical_json({"error": _ERROR, "reason_code": _error_reason(error)})
    if len(payload.encode("utf-8")) + 1 > _MAX_ERROR_BYTES:
        payload = canonical_json(
            {"error": _ERROR, "reason_code": "SYSTEM_PAPER_EVALUATION_CLI_FAILED"}
        )
    print(payload, file=sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the evaluator with no authority beyond its seven frozen paths."""
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = evaluate_system_paper(
            plan_path=_absolute_path(arguments.plan_path),
            start_receipt_path=_absolute_path(arguments.start_receipt_path),
            install_receipt_path=_absolute_path(arguments.install_receipt_path),
            contract_path=_absolute_path(arguments.contract_path),
            slot_root=_absolute_path(arguments.slot_root),
            runtime_root=_absolute_path(arguments.runtime_root),
            output_root=_absolute_path(arguments.output_root),
        )
        print(canonical_json(result))
        return 0
    except SystemExit as error:
        return int(error.code)
    except (OSError, TypeError, ValueError, SystemPaperEvaluationError) as error:
        _write_error(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
