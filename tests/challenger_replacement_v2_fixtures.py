"""Credential-free deterministic fixtures for replacement v2 tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_quant.canonical import business_hash, stable_id, utc_datetime
from crypto_quant.challenger_replacement_plan_v2 import load_challenger_replacement_plan_v2


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json"
DEFAULT_SCHEDULED_FOR = "2026-08-22T04:00:00.000Z"
DEFAULT_CAPTURED_AT = "2026-08-22T04:05:00.000Z"
ZERO_HASH = "0" * 64


def fixture_plan():
    return load_challenger_replacement_plan_v2(PLAN_PATH)


def fixture_build_identity():
    return {
        "release_tag": "v0.66.0",
        "peeled_commit": "c" * 40,
        "package_version": "0.66.0",
        "manifest_version": "1.60.0",
        "build_input_tree_hash": "a" * 64,
        "manifest_hash": "b" * 64,
        "manifest_file_sha256": "d" * 64,
    }


def _utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def fixture_klines(*, scheduled_for=DEFAULT_SCHEDULED_FOR, latest="101"):
    boundary = _utc(scheduled_for)
    rows = []
    for index in range(21):
        opened = boundary - timedelta(hours=4 * (21 - index))
        close = "100" if index < 20 else latest
        row = {
            "provider": "BINANCE_PUBLIC_DATA", "market": "SPOT",
            "data_family": "KLINES", "symbol": "ETHUSDT", "interval": "4h",
            "open_time": utc_datetime(opened),
            "close_time": utc_datetime(opened + timedelta(hours=4) - timedelta(milliseconds=1)),
            "available_at": utc_datetime(opened + timedelta(hours=4)),
            "open": close, "high": str(int(close) + 1),
            "low": str(int(close) - 1), "close": close,
        }
        row["source_row_hash"] = business_hash(row)
        rows.append(row)
    return rows


def fixture_capture(*, scheduled_for=DEFAULT_SCHEDULED_FOR,
                    captured_at=DEFAULT_CAPTURED_AT, latest="101", sequence=1):
    plan = fixture_plan()
    return {
        "slot_id": stable_id("challenger_replacement_slot", {
            "plan_hash": plan["plan_hash"], "scheduled_for": scheduled_for,
        }),
        "sequence": sequence, "scheduled_for": scheduled_for,
        "captured_at": captured_at,
        "evidence_qualification": "TEST_FIXTURE_ONLY_NOT_COHORT_EVIDENCE",
        "request_descriptor": {
            "provider": "BINANCE_PUBLIC_DATA", "market": "SPOT",
            "data_family": "KLINES", "symbol": "ETHUSDT", "interval": "4h",
        },
        "klines": fixture_klines(scheduled_for=scheduled_for, latest=latest),
        "network_request_count_observed_by_runtime": 0,
    }
