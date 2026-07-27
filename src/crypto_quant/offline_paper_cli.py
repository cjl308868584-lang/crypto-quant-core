"""Atomic CLI for one public-only offline Paper cycle."""

import argparse
import json
import sys
from typing import Callable, Optional, Sequence

from .canonical import business_hash
from .market_data import MarketDataError
from .market_data_cli import _publish_immutable, _selected_root_path
from .offline_paper import (
    BinanceOfflinePaperTransport,
    OfflinePaperError,
    OfflinePaperPlan,
    _utc_now,
    build_offline_paper_run,
    capture_offline_paper,
    minimum_paper_run_recorded_at,
    offline_paper_run_trust_hash,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="offline-paper-run")
    parser.add_argument("--symbol", required=True, choices=("ETHUSDT",))
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-id")
    return parser


def _artifact_bytes(run: object) -> bytes:
    return json.dumps(run, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _run_id(capture) -> str:
    return "offline-paper_" + business_hash(
        {
            "symbol": capture.plan.symbol,
            "decision_time": capture.decision_time,
            "receipt_hashes": [
                receipt["receipt_hash"] for receipt in capture.receipts
            ],
        }
    )


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    transport=None,
    clock: Optional[Callable[[], str]] = None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        now = clock or _utc_now
        plan = OfflinePaperPlan.create(arguments.symbol)
        capture = capture_offline_paper(
            plan,
            transport or BinanceOfflinePaperTransport(clock=now),
            recorded_at=now,
        )
        run_id = arguments.run_id or _run_id(capture)
        run = build_offline_paper_run(
            capture,
            run_id=run_id,
            recorded_at=minimum_paper_run_recorded_at(capture, now()),
        )
        trust_hash = offline_paper_run_trust_hash(run)
        root = _selected_root_path(arguments.output_root)
        artifact_name = run_id + ".json"
        artifact = root.resolve() / "paper" / artifact_name
        created = _publish_immutable(
            root,
            artifact_name,
            _artifact_bytes(run),
            output_directory="paper",
        )
    except SystemExit as error:
        return int(error.code)
    except (
        MarketDataError,
        OfflinePaperError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "artifact_path": str(artifact),
                "created": created,
                "paper_eligibility": run["paper_eligibility"],
                "profitability_eligibility": run["profitability_eligibility"],
                "run_hash": run["run_hash"],
                "trusted_attestation_hash": trust_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
