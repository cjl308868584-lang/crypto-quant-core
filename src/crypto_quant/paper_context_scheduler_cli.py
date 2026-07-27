"""One-shot CLI for the context-complete Paper sidecar scheduler."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from .paper_context_scheduler import (
    PaperContextScheduleError,
    run_context_complete_paper_cycle,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-context-scheduler")
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--paper-cost-binding")
    parser.add_argument("--paper-cost-binding-trust-hash-file")
    parser.add_argument("--offline-paper-trust-hash-file")
    parser.add_argument("--account-commission-trust-hash-file")
    parser.add_argument("--perpetual-context-snapshot")
    parser.add_argument("--perpetual-context-trust-hash-file")
    return parser


def _json(path: Optional[str]):
    if path is None:
        return None

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PaperContextScheduleError(
                    "PAPER_CONTEXT_JSON_DUPLICATE_KEY"
                )
            result[key] = value
        return result

    def reject_number(_value):
        raise PaperContextScheduleError(
            "PAPER_CONTEXT_JSON_FLOAT_FORBIDDEN"
        )

    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=pairs,
        parse_float=reject_number,
        parse_constant=reject_number,
    )


def _trust(path: Optional[str]):
    if path is None:
        return None
    value = Path(path).read_text(encoding="ascii")
    return value[:-1] if value.endswith("\n") else value


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    clock=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        selected_clock = clock or (
            lambda: datetime.now(timezone.utc)
        )
        result = run_context_complete_paper_cycle(
            state_path=Path(arguments.state_path),
            output_root=Path(arguments.output_root),
            worker_id=arguments.worker_id,
            clock=selected_clock,
            paper_cost_binding=_json(arguments.paper_cost_binding),
            paper_cost_binding_trusted_attestation_hash=_trust(
                arguments.paper_cost_binding_trust_hash_file
            ),
            offline_paper_trusted_attestation_hash=_trust(
                arguments.offline_paper_trust_hash_file
            ),
            account_commission_trusted_attestation_hash=_trust(
                arguments.account_commission_trust_hash_file
            ),
            perpetual_context_snapshot=_json(
                arguments.perpetual_context_snapshot
            ),
            perpetual_context_trusted_attestation_hash=_trust(
                arguments.perpetual_context_trust_hash_file
            ),
        )
    except SystemExit as error:
        return int(error.code)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        PaperContextScheduleError,
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
