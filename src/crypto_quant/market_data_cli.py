"""Structured, public-only historical market-data artifact command."""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence

from .market_data import (
    HistoricalArchiveRequest,
    MarketDataError,
    PublicArchiveTransport,
    fetch_historical_market_data,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="market-data-fetch")
    parser.add_argument("--market", required=True, choices=("SPOT", "USD_M"))
    parser.add_argument(
        "--data-family",
        required=True,
        choices=("KLINES", "AGG_TRADES", "MARK_PRICE_KLINES", "FUNDING_RATE"),
    )
    parser.add_argument("--symbol", required=True, choices=("ETHUSDT", "BTCUSDT"))
    parser.add_argument("--interval")
    parser.add_argument("--period", required=True)
    parser.add_argument("--output-root", required=True)
    return parser


def _artifact_bytes(snapshot: object) -> bytes:
    return json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _publish_immutable(path: Path, payload: bytes) -> bool:
    """Publish bytes once, returning true only when this call creates the file."""

    if path.exists():
        if path.read_bytes() == payload:
            return False
        raise MarketDataError("ARTIFACT_CONFLICT")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=str(path.parent), prefix=".market-data-", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise MarketDataError("ARTIFACT_CONFLICT")
            return False
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return True
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    transport: Optional[PublicArchiveTransport] = None,
    clock: Optional[Callable[[], str]] = None,
) -> int:
    """Fetch one allowlisted archive and atomically publish its immutable JSON."""

    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        period_kind = "MONTHLY" if arguments.data_family == "FUNDING_RATE" else "DAILY"
        request = HistoricalArchiveRequest.create(
            market=arguments.market,
            data_family=arguments.data_family,
            symbol=arguments.symbol,
            interval_or_null=arguments.interval,
            period_kind=period_kind,
            period=arguments.period,
        )
        retrieved_at = (clock or _utc_now)()
        snapshot = fetch_historical_market_data(
            request,
            transport or PublicArchiveTransport(),
            retrieved_at,
        )
        root = Path(arguments.output_root).expanduser().resolve()
        artifact = root / "market-data" / (snapshot["snapshot_id"] + ".json")
        created = _publish_immutable(artifact, _artifact_bytes(snapshot))
    except SystemExit as error:
        return int(error.code)
    except (MarketDataError, OSError, TypeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "artifact_path": str(artifact),
                "created": created,
                "snapshot_hash": snapshot["snapshot_hash"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
