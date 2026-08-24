"""Credential-free deterministic fixtures for replacement v3 tests."""

from pathlib import Path

from crypto_quant.challenger_replacement_plan_v3 import (
    load_challenger_replacement_plan_v3,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / (
    "artifacts/challenger-replacement/"
    "challenger-replacement-plan-v0.69.0.json"
)
DEFAULT_SCHEDULED_FOR = "2026-08-24T00:00:00.000Z"
DEFAULT_OBSERVED_AT = "2026-08-24T00:05:00.000Z"


def fixture_v3_plan():
    return load_challenger_replacement_plan_v3(PLAN_PATH)


def fixture_v070_build_identity():
    return {
        "release_tag": "v0.70.0-fixture",
        "peeled_commit": "7" * 40,
        "package_version": "0.70.0",
        "manifest_version": "1.64.0",
        "build_input_tree_hash": "1" * 64,
        "manifest_hash": "2" * 64,
        "manifest_file_sha256": "3" * 64,
    }


def fixture_opportunity_id(scheduled_for=DEFAULT_SCHEDULED_FOR):
    return "ETHUSDT@" + scheduled_for
