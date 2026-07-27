"""Structured, public-only historical market-data artifact command."""

import argparse
import json
import os
import secrets
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

from .market_data import (
    HistoricalArchiveRequest,
    MarketDataError,
    PublicArchiveTransport,
    fetch_historical_market_data,
)


_OUTPUT_DIRECTORY = "market-data"
_TEMPORARY_PREFIX = ".market-data-"


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


def _directory_flags() -> int:
    required = (getattr(os, "O_DIRECTORY", None), getattr(os, "O_NOFOLLOW", None))
    if any(flag is None for flag in required):
        raise MarketDataError("ARTIFACT_OUTPUT_INVALID")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _selected_root_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def _open_output_root(root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(str(root), _directory_flags())
    except OSError as error:
        raise MarketDataError("ARTIFACT_OUTPUT_INVALID") from error


def _open_output_directory(root_fd: int) -> int:
    try:
        os.mkdir(_OUTPUT_DIRECTORY, dir_fd=root_fd)
    except FileExistsError:
        pass
    try:
        return os.open(_OUTPUT_DIRECTORY, _directory_flags(), dir_fd=root_fd)
    except OSError as error:
        raise MarketDataError("ARTIFACT_OUTPUT_INVALID") from error


def _directory_is_attached(root_fd: int, output_fd: int) -> bool:
    try:
        entry = os.stat(_OUTPUT_DIRECTORY, dir_fd=root_fd, follow_symlinks=False)
        opened = os.fstat(output_fd)
    except OSError:
        return False
    return (
        stat.S_ISDIR(entry.st_mode)
        and stat.S_ISDIR(opened.st_mode)
        and (entry.st_dev, entry.st_ino) == (opened.st_dev, opened.st_ino)
    )


def _require_attached_directory(root_fd: int, output_fd: int) -> None:
    if not _directory_is_attached(root_fd, output_fd):
        raise MarketDataError("ARTIFACT_OUTPUT_INVALID")


def _regular_stat(directory_fd: int, name: str):
    try:
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1:
        raise MarketDataError("ARTIFACT_OUTPUT_INVALID")
    return entry


def _read_existing_artifact(directory_fd: int, name: str, expected_size: int):
    entry = _regular_stat(directory_fd, name)
    if entry is None:
        return None
    if entry.st_size != expected_size:
        return b""
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    except OSError as error:
        raise MarketDataError("ARTIFACT_OUTPUT_INVALID") from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino)
        ):
            raise MarketDataError("ARTIFACT_OUTPUT_INVALID")
        chunks = []
        remaining = expected_size
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                raise MarketDataError("ARTIFACT_OUTPUT_INVALID")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    finally:
        _close_without_reversing_result(descriptor)


def _close_without_reversing_result(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _discard_created_temporary(
    directory_fd: int,
    name: str,
    identity: Optional[Tuple[int, int]],
) -> None:
    if identity is None:
        entry = _regular_stat(directory_fd, name)
        if entry is None:
            return
        identity = (entry.st_dev, entry.st_ino)
    try:
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (entry.st_dev, entry.st_ino) != identity:
        raise MarketDataError("ARTIFACT_OUTPUT_INVALID")
    os.unlink(name, dir_fd=directory_fd)
    os.fsync(directory_fd)


def _open_temporary_artifact(directory_fd: int) -> Tuple[str, int, Tuple[int, int]]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    for _ in range(32):
        name = _TEMPORARY_PREFIX + secrets.token_hex(16)
        try:
            descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
        except FileExistsError:
            continue
        identity = None
        try:
            opened = os.fstat(descriptor)
            identity = (opened.st_dev, opened.st_ino)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise MarketDataError("ARTIFACT_OUTPUT_INVALID")
            return name, descriptor, identity
        except (MarketDataError, OSError):
            _close_without_reversing_result(descriptor)
            _discard_created_temporary(directory_fd, name, identity)
            raise
    raise MarketDataError("ARTIFACT_OUTPUT_INVALID")


def _write_and_sync(
    descriptor: int,
    payload: bytes,
    identity: Tuple[int, int],
) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("temporary artifact write failed")
        offset += written
    os.fsync(descriptor)
    written_stat = os.fstat(descriptor)
    if (
        not stat.S_ISREG(written_stat.st_mode)
        or written_stat.st_nlink != 1
        or (written_stat.st_dev, written_stat.st_ino) != identity
    ):
        raise MarketDataError("ARTIFACT_OUTPUT_INVALID")


def _unlink_own_name(directory_fd: int, name: str, identity: Tuple[int, int]) -> None:
    try:
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISREG(entry.st_mode)
        or (entry.st_dev, entry.st_ino) != identity
    ):
        raise MarketDataError("ARTIFACT_OUTPUT_INVALID")
    os.unlink(name, dir_fd=directory_fd)


def _rollback_publication(
    directory_fd: int,
    artifact_name: str,
    temporary_name: Optional[str],
    identity: Tuple[int, int],
) -> None:
    _unlink_own_name(directory_fd, artifact_name, identity)
    if temporary_name is not None:
        _unlink_own_name(directory_fd, temporary_name, identity)
    os.fsync(directory_fd)


def _publish_in_directory(
    root_fd: int,
    directory_fd: int,
    artifact_name: str,
    payload: bytes,
) -> bool:
    _require_attached_directory(root_fd, directory_fd)
    existing = _read_existing_artifact(directory_fd, artifact_name, len(payload))
    if existing is not None:
        if existing == payload:
            _require_attached_directory(root_fd, directory_fd)
            return False
        raise MarketDataError("ARTIFACT_CONFLICT")

    temporary_name = None
    temporary_fd = None
    identity = None
    published = False
    try:
        temporary_name, temporary_fd, identity = _open_temporary_artifact(directory_fd)
        _write_and_sync(temporary_fd, payload, identity)
        os.close(temporary_fd)
        temporary_fd = None
        _require_attached_directory(root_fd, directory_fd)
        try:
            os.link(
                temporary_name,
                artifact_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            existing = _read_existing_artifact(directory_fd, artifact_name, len(payload))
            if existing == payload:
                _unlink_own_name(directory_fd, temporary_name, identity)
                os.fsync(directory_fd)
                _require_attached_directory(root_fd, directory_fd)
                return False
            raise MarketDataError("ARTIFACT_CONFLICT")
        published = True
        _require_attached_directory(root_fd, directory_fd)
        os.fsync(directory_fd)
        _unlink_own_name(directory_fd, temporary_name, identity)
        temporary_name = None
        os.fsync(directory_fd)
        _require_attached_directory(root_fd, directory_fd)
        return True
    except (MarketDataError, OSError) as error:
        if temporary_fd is not None:
            _close_without_reversing_result(temporary_fd)
            temporary_fd = None
        try:
            if identity is not None:
                if published:
                    _rollback_publication(
                        directory_fd, artifact_name, temporary_name, identity
                    )
                elif temporary_name is not None:
                    _unlink_own_name(directory_fd, temporary_name, identity)
                    os.fsync(directory_fd)
        except (MarketDataError, OSError) as rollback_error:
            raise MarketDataError("ARTIFACT_PUBLISH_FAILED") from rollback_error
        if isinstance(error, MarketDataError):
            raise
        raise MarketDataError("ARTIFACT_PUBLISH_FAILED") from error
    finally:
        if temporary_fd is not None:
            _close_without_reversing_result(temporary_fd)


def _publish_immutable(root: Path, artifact_name: str, payload: bytes) -> bool:
    """Publish bytes below a no-follow directory boundary without replacement."""

    root_fd = _open_output_root(root)
    directory_fd = None
    try:
        directory_fd = _open_output_directory(root_fd)
        return _publish_in_directory(root_fd, directory_fd, artifact_name, payload)
    finally:
        if directory_fd is not None:
            _close_without_reversing_result(directory_fd)
        _close_without_reversing_result(root_fd)


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
        root = _selected_root_path(arguments.output_root)
        artifact_name = snapshot["snapshot_id"] + ".json"
        artifact = root.resolve() / _OUTPUT_DIRECTORY / artifact_name
        created = _publish_immutable(root, artifact_name, _artifact_bytes(snapshot))
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
