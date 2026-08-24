"""Credential-free deterministic fixtures for replacement v3 tests."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

from pathlib import Path

from crypto_quant.canonical import canonical_json, stable_id, utc_datetime
from crypto_quant.challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.instruments import InstrumentMetadata, MarketType
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


def fixture_v071_build_identity():
    return {
        "release_tag": "v0.71.0-fixture",
        "peeled_commit": "8" * 40,
        "package_version": "0.71.0",
        "manifest_version": "1.65.0",
        "build_input_tree_hash": "4" * 64,
        "manifest_hash": "5" * 64,
        "manifest_file_sha256": "6" * 64,
    }


def fixture_v071_contract():
    return build_challenger_replacement_simulation_contract(plan=fixture_v3_plan())


def _fixture_metadata(market_type, *, taker_fee="0.0015", multiplier="1"):
    return InstrumentMetadata(
        schema_version="1.1.0",
        instrument_id=(
            "BINANCE:%s:ETHUSDT" % market_type.value
        ),
        exchange="BINANCE",
        market_type=market_type,
        symbol="ETHUSDT",
        base_asset="ETH",
        quote_asset="USDT",
        settlement_asset="USDT",
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        effective_to_or_null=None,
        price_tick=Decimal("0.01"),
        quantity_step=(
            Decimal("0.0001")
            if market_type is MarketType.SPOT
            else Decimal("0.001")
        ),
        min_quantity=(
            Decimal("0.0001")
            if market_type is MarketType.SPOT
            else Decimal("0.001")
        ),
        max_quantity=Decimal("1000"),
        min_notional=Decimal("5"),
        contract_multiplier=Decimal(multiplier),
        supported_order_types=("MARKET", "STOP_MARKET"),
        supported_time_in_force=("GTC", "IOC"),
        supports_reduce_only=market_type is MarketType.USDT_PERP,
        supports_stop_market=True,
        maker_fee=Decimal("0.0015"),
        taker_fee=Decimal(taker_fee),
        metadata_source="COMMITTED_TEST_FIXTURE_NOT_FOR_TRADING",
    )


def fixture_v071_spot_metadata(
    *, taker_fee="0.0015", multiplier="1", min_notional="5"
):
    metadata = _fixture_metadata(
        MarketType.SPOT,
        taker_fee=taker_fee,
        multiplier=multiplier,
    )
    return replace(metadata, min_notional=Decimal(min_notional))


def fixture_v071_perpetual_metadata(*, taker_fee="0.0015", multiplier="1"):
    return _fixture_metadata(
        MarketType.USDT_PERP,
        taker_fee=taker_fee,
        multiplier=multiplier,
    )


def fixture_v071_bars(scheduled_for=DEFAULT_SCHEDULED_FOR):
    boundary = datetime.fromisoformat(
        scheduled_for.replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    bars = []
    for index in range(21):
        opened = boundary - timedelta(hours=4 * (21 - index))
        closed = opened + timedelta(hours=4)
        close = Decimal("1900") + Decimal(index * 5)
        bars.append(
            {
                "open_time": utc_datetime(opened),
                "close_boundary": utc_datetime(closed),
                "open": str(close - Decimal("2")),
                "high": str(close + Decimal("4")),
                "low": str(close - Decimal("4")),
                "close": str(close),
            }
        )
    return bars


def fixture_v071_signal_bars(signal, scheduled_for=DEFAULT_SCHEDULED_FOR):
    if signal not in {"LONG", "SHORT", "FLAT"}:
        raise ValueError("unknown fixture signal")
    bars = fixture_v071_bars(scheduled_for)
    prior = Decimal("2000")
    latest = {
        "LONG": Decimal("2020"),
        "SHORT": Decimal("1980"),
        "FLAT": Decimal("2000"),
    }[signal]
    for index, bar in enumerate(bars):
        close = latest if index == 20 else prior
        bar.update(
            open=str(close),
            high=str(close + Decimal("2")),
            low=str(close - Decimal("2")),
            close=str(close),
        )
    return bars


def fixture_v071_input_document(
    *,
    scheduled_for=DEFAULT_SCHEDULED_FOR,
    observed_at=DEFAULT_OBSERVED_AT,
    bars=None,
    spot_metadata=None,
    perpetual_metadata=None,
    spot_quote=None,
    perpetual_quote=None,
    funding_boundary_at_or_null=None,
    funding_rate_or_null=None,
):
    plan = fixture_v3_plan()
    contract = fixture_v071_contract()
    build = fixture_v071_build_identity()
    scheduled = datetime.fromisoformat(
        scheduled_for.replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    spot = spot_metadata or fixture_v071_spot_metadata()
    perpetual = perpetual_metadata or fixture_v071_perpetual_metadata()
    opportunity_id = fixture_opportunity_id(scheduled_for)
    document = {
        "$schema": "./challenger-replacement-binance-simulation-input-v1.schema.json",
        "schema_version": "1.0.0",
        "input_id": "challenger_replacement_binance_simulation_input_" + "0" * 64,
        "input_hash": "0" * 64,
        "evidence_qualification": "COMMITTED_FIXTURE_NOT_LIVE_MARKET",
        "plan": {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]},
        "simulation_contract": {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
        },
        "build_identity": deepcopy(build),
        "opportunity": {
            "opportunity_id": opportunity_id,
            "scheduled_for": scheduled_for,
            "capture_open": utc_datetime(scheduled + timedelta(minutes=2)),
            "capture_close": utc_datetime(scheduled + timedelta(minutes=10)),
            "observed_at": observed_at,
        },
        "bars": deepcopy(bars if bars is not None else fixture_v071_bars(scheduled_for)),
        "instruments": {
            "spot": {
                "metadata": json.loads(canonical_json(spot.business_payload())),
                "metadata_hash": spot.metadata_hash,
            },
            "perpetual": {
                "metadata": json.loads(
                    canonical_json(perpetual.business_payload())
                ),
                "metadata_hash": perpetual.metadata_hash,
            },
        },
        "quotes": {
            "spot": deepcopy(
                spot_quote
                or {"bid": "1999", "ask": "2001", "last": "2000"}
            ),
            "perpetual": deepcopy(
                perpetual_quote
                or {
                    "bid": "1998.5",
                    "ask": "2000.5",
                    "last": "1999.5",
                    "mark": "1999.25",
                }
            ),
        },
        "funding": {
            "boundary_at_or_null": funding_boundary_at_or_null,
            "rate_or_null": funding_rate_or_null,
        },
        "authority": {
            "network_requests": 0,
            "account_requests": 0,
            "broker_requests": 0,
            "orders_submitted_to_venue": 0,
            "credentials_used": False,
            "production_state_writes": 0,
        },
    }
    document["input_id"] = stable_id(
        "challenger_replacement_binance_simulation_input",
        {
            "plan": document["plan"],
            "simulation_contract": document["simulation_contract"],
            "build_identity": document["build_identity"],
            "opportunity": document["opportunity"],
        },
    )
    document["input_hash"] = artifact_self_hash(document, "input_hash")
    return document


def fixture_v071_input_bytes(**kwargs):
    return canonical_json(fixture_v071_input_document(**kwargs)).encode("utf-8")


def fixture_opportunity_id(scheduled_for=DEFAULT_SCHEDULED_FOR):
    return "ETHUSDT@" + scheduled_for
