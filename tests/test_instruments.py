import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from crypto_quant.errors import ContractError
from crypto_quant.instruments import (
    InstrumentMetadata,
    InstrumentMetadataCatalog,
    MarketType,
    OrderPlanStatus,
    OrderSide,
    instrument_metadata_from_payload,
    plan_order,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_metadata(
    *,
    market_type=MarketType.SPOT,
    effective_from=NOW,
    effective_to=None,
):
    return InstrumentMetadata(
        schema_version="1.1.0",
        instrument_id=f"BINANCE:{market_type.value}:ETHUSDT",
        exchange="BINANCE",
        market_type=market_type,
        symbol="ETHUSDT",
        base_asset="ETH",
        quote_asset="USDT",
        settlement_asset="USDT",
        effective_from=effective_from,
        effective_to_or_null=effective_to,
        price_tick=Decimal("0.01"),
        quantity_step=Decimal(
            "0.0001" if market_type is MarketType.SPOT else "0.001"
        ),
        min_quantity=Decimal(
            "0.0001" if market_type is MarketType.SPOT else "0.001"
        ),
        max_quantity=Decimal("1000"),
        min_notional=Decimal("5"),
        contract_multiplier=Decimal("1"),
        supported_order_types=("LIMIT", "MARKET", "STOP_MARKET"),
        supported_time_in_force=("GTC", "IOC", "FOK"),
        supports_reduce_only=market_type is MarketType.USDT_PERP,
        supports_stop_market=True,
        maker_fee=Decimal("0.001"),
        taker_fee=Decimal("0.001"),
        metadata_source="TEST_FIXTURE",
    )


class InstrumentMetadataTests(unittest.TestCase):
    def test_binance_sample_is_explicitly_non_authoritative_and_hashes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "config/instrument-metadata-binance-v1.sample.json").read_text()
        )
        self.assertEqual(payload["status"], "NON_AUTHORITATIVE_TEST_FIXTURE")
        records = tuple(
            instrument_metadata_from_payload(
                record,
                schema_version=payload["schema_version"],
            )
            for record in payload["records"]
        )
        self.assertEqual(len(records), 2)
        self.assertEqual(len({record.metadata_hash for record in records}), 2)
        self.assertEqual(
            len({records[0].metadata_hash for _ in range(100)}),
            1,
        )

    def test_catalog_preserves_versions_and_rejects_overlaps(self) -> None:
        catalog = InstrumentMetadataCatalog()
        first = make_metadata(effective_to=NOW + timedelta(days=1))
        second = make_metadata(effective_from=NOW + timedelta(days=1))
        catalog.register(second)
        catalog.register(first)
        catalog.register(first)
        self.assertEqual(len(catalog.versions(first.instrument_id)), 2)
        self.assertEqual(
            catalog.effective_at(
                first.instrument_id,
                NOW + timedelta(hours=12),
            ).metadata_hash,
            first.metadata_hash,
        )
        self.assertEqual(
            catalog.effective_at(
                first.instrument_id,
                NOW + timedelta(days=2),
            ).metadata_hash,
            second.metadata_hash,
        )
        with self.assertRaises(ContractError):
            catalog.register(
                replace(
                    first,
                    effective_from=NOW + timedelta(hours=12),
                    effective_to_or_null=NOW + timedelta(days=2),
                )
            )

    def test_risk_increasing_limits_round_safely_and_cap_notional(self) -> None:
        metadata = make_metadata()
        buy = plan_order(
            metadata=metadata,
            decision_time=NOW,
            side=OrderSide.BUY,
            order_type="LIMIT",
            time_in_force_or_null="GTC",
            requested_quantity="0.02",
            requested_price_or_null="1800.129",
            notional_reference_price="1800.125",
            risk_increasing=True,
            reduce_only=False,
            approved_notional_usdt_or_null="20",
        )
        self.assertEqual(buy.rounded_price_or_null, Decimal("1800.12"))
        self.assertLessEqual(buy.rounded_quantity, buy.requested_quantity)
        self.assertLessEqual(buy.rounded_notional, Decimal("20"))
        self.assertTrue(buy.was_clamped_to_approved_notional)
        self.assertEqual(buy.status, OrderPlanStatus.READY)

        short_metadata = make_metadata(market_type=MarketType.USDT_PERP)
        sell = plan_order(
            metadata=short_metadata,
            decision_time=NOW,
            side=OrderSide.SELL,
            order_type="LIMIT",
            time_in_force_or_null="GTC",
            requested_quantity="0.02",
            requested_price_or_null="1800.121",
            notional_reference_price="1800.125",
            risk_increasing=True,
            reduce_only=False,
            approved_notional_usdt_or_null="20",
        )
        self.assertEqual(sell.rounded_price_or_null, Decimal("1800.13"))
        self.assertLessEqual(sell.rounded_notional, Decimal("20"))

    def test_reductions_use_more_executable_price_and_never_round_quantity_up(self) -> None:
        spot = make_metadata()
        protective_sell = plan_order(
            metadata=spot,
            decision_time=NOW,
            side=OrderSide.SELL,
            order_type="LIMIT",
            time_in_force_or_null="IOC",
            requested_quantity="0.01009",
            requested_price_or_null="1799.999",
            notional_reference_price="1800",
            risk_increasing=False,
            reduce_only=False,
            approved_notional_usdt_or_null=None,
        )
        self.assertEqual(protective_sell.rounded_price_or_null, Decimal("1799.99"))
        self.assertEqual(protective_sell.rounded_quantity, Decimal("0.01"))

        perp = make_metadata(market_type=MarketType.USDT_PERP)
        close_short = plan_order(
            metadata=perp,
            decision_time=NOW,
            side=OrderSide.BUY,
            order_type="LIMIT",
            time_in_force_or_null="IOC",
            requested_quantity="0.0109",
            requested_price_or_null="1800.001",
            notional_reference_price="1800",
            risk_increasing=False,
            reduce_only=True,
            approved_notional_usdt_or_null=None,
        )
        self.assertEqual(close_short.rounded_price_or_null, Decimal("1800.01"))
        self.assertEqual(close_short.rounded_quantity, Decimal("0.01"))

    def test_minimums_never_round_up_and_reduction_residual_becomes_dust(self) -> None:
        spot = make_metadata()
        below_min_notional = plan_order(
            metadata=spot,
            decision_time=NOW,
            side=OrderSide.BUY,
            order_type="MARKET",
            time_in_force_or_null=None,
            requested_quantity="0.001",
            requested_price_or_null=None,
            notional_reference_price="1800",
            risk_increasing=True,
            reduce_only=False,
            approved_notional_usdt_or_null="2",
        )
        self.assertEqual(
            below_min_notional.status,
            OrderPlanStatus.NO_TRADE_BELOW_MIN_NOTIONAL,
        )
        self.assertFalse(below_min_notional.tradable)

        dust = plan_order(
            metadata=spot,
            decision_time=NOW,
            side=OrderSide.SELL,
            order_type="MARKET",
            time_in_force_or_null=None,
            requested_quantity="0.00019",
            requested_price_or_null=None,
            notional_reference_price="1800",
            risk_increasing=False,
            reduce_only=False,
            approved_notional_usdt_or_null=None,
        )
        self.assertEqual(dust.rounded_quantity, Decimal("0.0001"))
        self.assertEqual(
            dust.status,
            OrderPlanStatus.NO_TRADE_BELOW_MIN_NOTIONAL,
        )
        self.assertTrue(dust.is_dust)

    def test_rounding_property_never_exceeds_quantity_or_approved_notional(self) -> None:
        metadata = make_metadata()
        for index in range(1, 1001):
            requested = Decimal(index) / Decimal("100000")
            approved = Decimal(index + 5) / Decimal("10")
            plan = plan_order(
                metadata=metadata,
                decision_time=NOW,
                side=OrderSide.BUY,
                order_type="LIMIT",
                time_in_force_or_null="GTC",
                requested_quantity=requested,
                requested_price_or_null="1800.009",
                notional_reference_price="1800",
                risk_increasing=True,
                reduce_only=False,
                approved_notional_usdt_or_null=approved,
            )
            self.assertLessEqual(plan.rounded_quantity, requested)
            self.assertLessEqual(plan.rounded_notional, approved)
            self.assertEqual(
                plan.rounded_quantity % metadata.quantity_step,
                Decimal("0"),
            )

    def test_invalid_capabilities_or_stale_metadata_fail_closed(self) -> None:
        spot = make_metadata()
        with self.assertRaises(ContractError):
            replace(spot, supports_reduce_only=True)
        with self.assertRaises(ContractError):
            plan_order(
                metadata=replace(spot, supports_stop_market=False),
                decision_time=NOW,
                side=OrderSide.SELL,
                order_type="STOP_MARKET",
                time_in_force_or_null=None,
                requested_quantity="0.01",
                requested_price_or_null=None,
                notional_reference_price="1800",
                risk_increasing=False,
                reduce_only=False,
                approved_notional_usdt_or_null=None,
            )
        with self.assertRaises(ContractError):
            plan_order(
                metadata=spot,
                decision_time=NOW,
                side=OrderSide.BUY,
                order_type="MARKET",
                time_in_force_or_null=None,
                requested_quantity="0.01",
                requested_price_or_null="1800",
                notional_reference_price="1800",
                risk_increasing=True,
                reduce_only=False,
                approved_notional_usdt_or_null="20",
            )
        with self.assertRaises(ContractError):
            plan_order(
                metadata=spot,
                decision_time=NOW - timedelta(seconds=1),
                side=OrderSide.BUY,
                order_type="LIMIT",
                time_in_force_or_null="GTC",
                requested_quantity="0.01",
                requested_price_or_null="1800",
                notional_reference_price="1800",
                risk_increasing=True,
                reduce_only=False,
                approved_notional_usdt_or_null="20",
            )


if __name__ == "__main__":
    unittest.main()
