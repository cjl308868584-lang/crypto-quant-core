"""CLI for one immutable, public-only contemporaneous capture session."""

import argparse
import json
import sys
from typing import Callable, Optional, Sequence

from .canonical import business_hash
from .contemporaneous_capture import (
    BinancePublicMarketDataTransport,
    CaptureError,
    ContemporaneousCapturePlan,
    build_capture_session,
    capture_once,
    capture_snapshot_attestation_hash,
)
from .market_data_cli import _publish_immutable, _selected_root_path, _utc_now


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="public-market-capture")
    parser.add_argument("--symbol", required=True, choices=("ETHUSDT", "BTCUSDT"))
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--session-id")
    return parser


def _artifact_bytes(snapshot: object) -> bytes:
    return json.dumps(
        snapshot, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _session_id(symbol: str, batch) -> str:
    return "capture_" + business_hash(
        {
            "symbol": symbol,
            "receipt_hashes": [
                receipt["receipt_hash"] for receipt in batch.receipts
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
        plan = ContemporaneousCapturePlan.create(arguments.symbol)
        selected_transport = transport or BinancePublicMarketDataTransport(
            clock=now
        )
        batch = capture_once(
            plan,
            selected_transport,
            recorded_at=now,
        )
        session_id = arguments.session_id or _session_id(arguments.symbol, batch)
        snapshot = build_capture_session(
            [batch],
            session_id=session_id,
            recorded_at=now(),
        )
        attestation_hash = capture_snapshot_attestation_hash(snapshot)
        root = _selected_root_path(arguments.output_root)
        artifact_name = session_id + ".json"
        artifact = root.resolve() / "market-data" / artifact_name
        created = _publish_immutable(
            root, artifact_name, _artifact_bytes(snapshot)
        )
    except SystemExit as error:
        return int(error.code)
    except (CaptureError, OSError, TypeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "artifact_path": str(artifact),
                "created": created,
                "pit_eligibility": snapshot["pit_eligibility"],
                "paper_eligibility": snapshot["paper_eligibility"],
                "snapshot_attestation_hash": attestation_hash,
                "snapshot_hash": snapshot["snapshot_hash"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
