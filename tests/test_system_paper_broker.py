import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from crypto_quant.instruments import (
    InstrumentMetadata,
    MarketType,
    OrderSide,
)
from crypto_quant.errors import ContractError
from crypto_quant.orders import OrderState
from crypto_quant.system_paper_broker import (
    FillScenario,
    SimulatedBroker,
    SimulatedMarketEvidence,
    SimulatedOrderCommand,
)


NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


def make_metadata() -> InstrumentMetadata:
    return InstrumentMetadata(
        schema_version="instrument-metadata-v1",
        instrument_id="BINANCE:USDT_PERP:ETHUSDT",
        exchange="BINANCE",
        market_type=MarketType.USDT_PERP,
        symbol="ETHUSDT",
        base_asset="ETH",
        quote_asset="USDT",
        settlement_asset="USDT",
        effective_from=NOW,
        effective_to_or_null=None,
        price_tick=Decimal("0.01"),
        quantity_step=Decimal("0.001"),
        min_quantity=Decimal("0.001"),
        max_quantity=Decimal("1000"),
        min_notional=Decimal("5"),
        contract_multiplier=Decimal("1"),
        supported_order_types=("LIMIT", "MARKET"),
        supported_time_in_force=("GTC", "IOC"),
        supports_reduce_only=True,
        supports_stop_market=True,
        maker_fee=Decimal("0.001"),
        taker_fee=Decimal("0.0015"),
        metadata_source="frozen-test-fixture",
    )


def make_command() -> SimulatedOrderCommand:
    return SimulatedOrderCommand(
        scheduled_for=NOW,
        instrument_id="BINANCE:USDT_PERP:ETHUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        time_in_force_or_null=None,
        requested_quantity=Decimal("0.010"),
        requested_price_or_null=None,
        risk_increasing=True,
        reduce_only=False,
        approved_notional_usdt_or_null=Decimal("20"),
        risk_approved=True,
    )


def make_market() -> SimulatedMarketEvidence:
    return SimulatedMarketEvidence(
        observed_at=NOW,
        instrument_metadata=make_metadata(),
        best_bid_price=Decimal("1799.99"),
        best_ask_price=Decimal("1800.01"),
        last_trade_price=Decimal("1800"),
        market_bundle_hash="a" * 64,
    )


class SimulatedBrokerLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.command = make_command()
        self.market = make_market()

    def test_partial_then_full_fill_is_idempotent(self) -> None:
        broker = SimulatedBroker(FillScenario.partial_then_full("0.40"))

        first = broker.submit(self.command, self.market)
        second = broker.reconcile(first.local_order_id)
        duplicate = broker.reconcile(first.local_order_id)

        self.assertEqual(first.state, OrderState.PARTIALLY_FILLED)
        self.assertEqual(first.cumulative_filled_quantity, Decimal("0.004"))
        self.assertEqual(second.state, OrderState.FILLED)
        self.assertEqual(second.cumulative_filled_quantity, Decimal("0.010"))
        self.assertEqual(duplicate.result_hash, second.result_hash)

    def test_disconnect_after_submit_becomes_unknown_and_blocks_new_risk(self) -> None:
        broker = SimulatedBroker(FillScenario.disconnect_after_submit())

        result = broker.submit(self.command, self.market)

        self.assertEqual(result.state, OrderState.UNKNOWN)
        self.assertTrue(result.risk_lock_required)
        self.assertEqual(result.cumulative_filled_quantity, Decimal("0"))

        reconciled = broker.reconcile(result.local_order_id)
        duplicate = broker.reconcile(result.local_order_id)
        self.assertEqual(reconciled.state, OrderState.UNKNOWN)
        self.assertEqual(len(reconciled.event_ids), len(result.event_ids) + 1)
        self.assertEqual(duplicate.result_hash, reconciled.result_hash)

    def test_venue_rejection_is_terminal_without_fill_or_risk_lock(self) -> None:
        result = SimulatedBroker(FillScenario.rejected()).submit(
            self.command,
            self.market,
        )

        self.assertEqual(result.state, OrderState.REJECTED)
        self.assertEqual(result.cumulative_filled_quantity, Decimal("0"))
        self.assertEqual(result.fee_usdt, Decimal("0"))
        self.assertFalse(result.risk_lock_required)

    def test_cancel_before_fill_is_terminal_and_economically_empty(self) -> None:
        result = SimulatedBroker(FillScenario.cancel_before_fill()).submit(
            self.command,
            self.market,
        )

        self.assertEqual(result.state, OrderState.CANCELED)
        self.assertEqual(result.cumulative_filled_quantity, Decimal("0"))
        self.assertIsNone(result.average_fill_price)

    def test_fill_before_cancel_keeps_fill_and_cancels_only_remainder(self) -> None:
        result = SimulatedBroker(FillScenario.fill_before_cancel("0.30")).submit(
            self.command,
            self.market,
        )

        self.assertEqual(result.state, OrderState.CANCELED)
        self.assertEqual(result.cumulative_filled_quantity, Decimal("0.003"))
        self.assertGreater(result.fee_usdt, Decimal("0"))

    def test_buy_fill_applies_frozen_conservative_slippage_and_taker_fee(self) -> None:
        result = SimulatedBroker(FillScenario.fill_before_cancel("0.30")).submit(
            self.command,
            self.market,
        )

        self.assertEqual(result.average_fill_price, Decimal("1801.82"))
        self.assertEqual(result.fee_usdt, Decimal("0.00810819"))

    def test_fill_before_ack_and_duplicate_event_preserve_one_economic_fill(self) -> None:
        broker = SimulatedBroker(FillScenario.fill_before_ack_with_duplicate("0.40"))

        result = broker.submit(self.command, self.market)
        duplicate_submit = broker.submit(self.command, self.market)

        self.assertEqual(result.state, OrderState.PARTIALLY_FILLED)
        self.assertEqual(result.cumulative_filled_quantity, Decimal("0.004"))
        self.assertEqual(len(result.event_ids), len(set(result.event_ids)))
        self.assertEqual(duplicate_submit.result_hash, result.result_hash)

    def test_timeout_after_ack_is_unknown_until_explicit_reconciliation(self) -> None:
        result = SimulatedBroker(FillScenario.timeout_after_ack()).submit(
            self.command,
            self.market,
        )

        self.assertEqual(result.state, OrderState.UNKNOWN)
        self.assertTrue(result.risk_lock_required)

    def test_local_filters_round_quantity_and_fail_closed_below_min_notional(self) -> None:
        rounded = SimulatedBroker(FillScenario.partial_then_full("0.40")).submit(
            SimulatedOrderCommand(
                **{
                    **self.command.__dict__,
                    "requested_quantity": Decimal("0.0109"),
                }
            ),
            self.market,
        )
        below_minimum = SimulatedBroker(
            FillScenario.partial_then_full("0.40")
        ).submit(
            SimulatedOrderCommand(
                **{
                    **self.command.__dict__,
                    "requested_quantity": Decimal("0.001"),
                    "approved_notional_usdt_or_null": Decimal("2"),
                }
            ),
            self.market,
        )

        self.assertEqual(rounded.requested_quantity, Decimal("0.010"))
        self.assertEqual(rounded.cumulative_filled_quantity, Decimal("0.004"))
        self.assertEqual(below_minimum.state, OrderState.FAILED_PRE_SUBMIT)
        self.assertEqual(below_minimum.cumulative_filled_quantity, Decimal("0"))

    def test_impossible_overfill_fails_without_publishing_a_result(self) -> None:
        broker = SimulatedBroker(FillScenario.impossible_overfill())

        with self.assertRaisesRegex(
            ContractError,
            "cannot exceed requested quantity",
        ):
            broker.submit(self.command, self.market)

    def test_scenarios_must_use_a_validated_factory(self) -> None:
        with self.assertRaises(TypeError):
            FillScenario()

    def test_non_marketable_limit_expires_without_crossing_its_limit(self) -> None:
        limit_command = SimulatedOrderCommand(
            **{
                **self.command.__dict__,
                "order_type": "LIMIT",
                "time_in_force_or_null": "GTC",
                "requested_price_or_null": Decimal("1700"),
            }
        )

        result = SimulatedBroker(FillScenario.partial_then_full("0.40")).submit(
            limit_command,
            self.market,
        )

        self.assertEqual(result.state, OrderState.EXPIRED)
        self.assertEqual(result.cumulative_filled_quantity, Decimal("0"))
        self.assertIsNone(result.average_fill_price)

    def test_market_evidence_time_must_match_the_command_slot(self) -> None:
        stale_market = replace(
            self.market,
            observed_at=NOW - timedelta(seconds=1),
        )

        with self.assertRaisesRegex(
            ContractError,
            "market evidence time must match",
        ):
            SimulatedBroker(FillScenario.partial_then_full("0.40")).submit(
                self.command,
                stale_market,
            )

    def test_conservative_fill_notional_never_exceeds_approved_notional(self) -> None:
        command = replace(
            self.command,
            requested_quantity=Decimal("2"),
            approved_notional_usdt_or_null=Decimal("100"),
        )
        market = replace(
            self.market,
            best_bid_price=Decimal("99.99"),
            best_ask_price=Decimal("100"),
            last_trade_price=Decimal("50"),
            market_bundle_hash="f" * 64,
        )
        broker = SimulatedBroker(FillScenario.partial_then_full("0.40"))

        first = broker.submit(command, market)
        final = broker.reconcile(first.local_order_id)

        self.assertLessEqual(
            final.cumulative_filled_quantity * final.average_fill_price,
            Decimal("100"),
        )

    def test_order_result_hash_binds_instrument_side_and_fill_policy(self) -> None:
        result = SimulatedBroker(FillScenario.partial_then_full("0.40")).submit(
            self.command,
            self.market,
        )

        self.assertEqual(result.instrument_id, self.command.instrument_id)
        self.assertEqual(result.side, OrderSide.BUY)
        self.assertEqual(
            result.fill_policy_version,
            "SYSTEM_PAPER_CONSERVATIVE_BBO_V1",
        )

    def test_immediate_full_scenario_closes_the_entire_order(self) -> None:
        result = SimulatedBroker(FillScenario.immediate_full()).submit(
            self.command,
            self.market,
        )

        self.assertEqual(result.state, OrderState.FILLED)
        self.assertEqual(
            result.cumulative_filled_quantity,
            result.requested_quantity,
        )


if __name__ == "__main__":
    unittest.main()
