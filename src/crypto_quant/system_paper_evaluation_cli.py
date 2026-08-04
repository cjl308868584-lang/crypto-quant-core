"""Evaluate the frozen System Paper cohort from its seven authority paths."""

import argparse
import sys
from typing import Optional, Sequence

from .canonical import canonical_json


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


class _OncePathAction(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None) -> None:
        if getattr(namespace, self.dest, None) is not None:
            raise SystemPaperEvaluationCliError(_ARGUMENT_INVALID)
        setattr(namespace, self.dest, value)


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="system-paper-evaluation", add_help=False, allow_abbrev=False
    )
    for option in (
        "--plan-path",
        "--start-receipt-path",
        "--install-receipt-path",
        "--contract-path",
        "--slot-root",
        "--runtime-root",
        "--output-root",
    ):
        parser.add_argument(option, required=True, action=_OncePathAction)
    return parser


def _absolute_path(value: object):
    from pathlib import Path

    if not isinstance(value, str) or not value or "\x00" in value:
        raise SystemPaperEvaluationCliError(_PATH_INVALID)
    path = Path(value)
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise SystemPaperEvaluationCliError(_PATH_INVALID)
    return path


def _error_reason(error: BaseException) -> str:
    try:
        reason = getattr(error, "reason_code", None)
    except Exception:
        return "SYSTEM_PAPER_EVALUATION_CLI_FAILED"
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
    fallback = canonical_json(
        {"error": _ERROR, "reason_code": "SYSTEM_PAPER_EVALUATION_CLI_FAILED"}
    )
    try:
        payload = canonical_json(
            {"error": _ERROR, "reason_code": _error_reason(error)}
        )
    except Exception:
        payload = fallback
    if len(payload.encode("utf-8")) + 1 > _MAX_ERROR_BYTES:
        payload = fallback
    try:
        _write_exact(sys.stderr, payload + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def _evaluate(**paths):
    from .system_paper_evaluation import evaluate_system_paper

    return evaluate_system_paper(**paths)


def _write_result(result) -> None:
    payload = canonical_json(result)
    _write_exact(sys.stdout, payload + "\n")
    sys.stdout.flush()


def _write_exact(stream, payload: str) -> None:
    remaining = payload
    while remaining:
        written = stream.write(remaining)
        if (
            isinstance(written, bool)
            or not isinstance(written, int)
            or written <= 0
            or written > len(remaining)
        ):
            raise OSError("invalid stream write count")
        remaining = remaining[written:]


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the evaluator with no authority beyond its seven frozen paths."""
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = _evaluate(
            plan_path=_absolute_path(arguments.plan_path),
            start_receipt_path=_absolute_path(arguments.start_receipt_path),
            install_receipt_path=_absolute_path(arguments.install_receipt_path),
            contract_path=_absolute_path(arguments.contract_path),
            slot_root=_absolute_path(arguments.slot_root),
            runtime_root=_absolute_path(arguments.runtime_root),
            output_root=_absolute_path(arguments.output_root),
        )
        _write_result(result)
        return 0
    except Exception as error:
        _write_error(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
