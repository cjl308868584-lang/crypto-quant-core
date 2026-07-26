import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from crypto_quant.canonical import canonical_decimal
from crypto_quant.economics import economic_snapshot_hash
from crypto_quant.statistics import statistical_series_hash
from crypto_quant.trade_replay import analyze_trade_replay_source

from tests.factories import complete_trade_replay_inputs


def timestamp(hour):
    value = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        hours=hour
    )
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def fill(
    fill_id,
    *,
    instrument,
    side,
    quantity,
    price,
    sequence,
    hour,
    multiplier="1",
):
    return {
        "fill_id": fill_id,
        "exchange_trade_id": f"exchange-{fill_id}",
        "local_order_id": f"order-{fill_id}",
        "venue_order_id": f"venue-{fill_id}",
        "source_event_sequence": sequence,
        "instrument_id": instrument,
        "side": side,
        "quantity": quantity,
        "price": price,
        "contract_multiplier": multiplier,
        "fee_value_usdt": "0",
        "implementation_shortfall_usdt": "0",
        "exchange_event_time": timestamp(hour),
    }


class CompleteTradeSourceReplayTests(unittest.TestCase):
    def inputs(self, pnl="10"):
        source, snapshots, valuations = complete_trade_replay_inputs(
            trade_pnls=(pnl,)
        )
        return deepcopy(source), deepcopy(snapshots), deepcopy(valuations)

    @staticmethod
    def rehash(
        source,
        snapshots,
        valuations,
        *,
        recompute_values=True,
    ):
        old_to_new = {}
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            for snapshot, observation in zip(
                snapshots,
                source["observations"],
            ):
                old_hash = observation["source_economic_snapshot_hash"]
                snapshot["snapshot_hash"] = economic_snapshot_hash(snapshot)
                new_hash = snapshot["snapshot_hash"]
                old_to_new[old_hash] = new_hash
                observation["source_economic_snapshot_hash"] = new_hash
                if recompute_values:
                    start = Decimal(
                        snapshot["starting_liquidation_equity_usdt"]
                    )
                    end = Decimal(
                        snapshot["ending_liquidation_equity_usdt"]
                    )
                    observation["value"] = canonical_decimal(
                        (end / start).ln()
                    )
        source["source_economic_snapshot_hashes"] = [
            snapshot["snapshot_hash"] for snapshot in snapshots
        ]
        for checkpoint in valuations:
            checkpoint["source_economic_snapshot_hash"] = old_to_new.get(
                checkpoint["source_economic_snapshot_hash"],
                checkpoint["source_economic_snapshot_hash"],
            )
        source["series_hash"] = statistical_series_hash(source)

    def analyze(self, source, snapshots, valuations):
        return analyze_trade_replay_source(
            source_series_snapshot=source,
            economic_snapshots=snapshots,
            valuation_checkpoints=valuations,
        )

    def test_split_fills_form_one_zero_to_zero_trade(self):
        source, snapshots, valuations = self.inputs("30")
        snapshot = snapshots[0]
        snapshot["fills"] = [
            fill(
                "split-open-1",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="BUY",
                quantity="1",
                price="100",
                sequence=2,
                hour=6,
            ),
            fill(
                "split-open-2",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="BUY",
                quantity="2",
                price="100",
                sequence=3,
                hour=7,
            ),
            fill(
                "split-close-1",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="SELL",
                quantity="1",
                price="110",
                sequence=4,
                hour=8,
            ),
            fill(
                "split-close-2",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="SELL",
                quantity="2",
                price="110",
                sequence=5,
                hour=9,
            ),
        ]
        snapshot["equity_points"][-1]["source_event_sequence"] = 6
        self.rehash(source, snapshots, valuations)

        analysis = self.analyze(source, snapshots, valuations)

        self.assertEqual(len(analysis.completed_trades), 1)
        trade = analysis.completed_trades[0]
        self.assertEqual(
            trade.fill_ids,
            (
                "split-open-1",
                "split-open-2",
                "split-close-1",
                "split-close-2",
            ),
        )
        self.assertEqual(trade.contribution_usdt, Decimal("30"))
        self.assertTrue(trade.eligible)

    def test_overlapping_instruments_form_independent_cycles(self):
        source, snapshots, valuations = self.inputs("30")
        snapshot = snapshots[0]
        snapshot["fills"] = [
            fill(
                "btc-open",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="BUY",
                quantity="1",
                price="100",
                sequence=2,
                hour=6,
            ),
            fill(
                "eth-open",
                instrument="BINANCE:SPOT:ETHUSDT",
                side="BUY",
                quantity="1",
                price="200",
                sequence=3,
                hour=7,
            ),
            fill(
                "btc-close",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="SELL",
                quantity="1",
                price="110",
                sequence=4,
                hour=8,
            ),
            fill(
                "eth-close",
                instrument="BINANCE:SPOT:ETHUSDT",
                side="SELL",
                quantity="1",
                price="220",
                sequence=5,
                hour=9,
            ),
        ]
        snapshot["equity_points"][-1]["source_event_sequence"] = 6
        self.rehash(source, snapshots, valuations)

        analysis = self.analyze(source, snapshots, valuations)

        self.assertEqual(
            [
                (trade.instrument_id, trade.contribution_usdt)
                for trade in analysis.completed_trades
            ],
            [
                ("BINANCE:SPOT:BTCUSDT", Decimal("10")),
                ("BINANCE:SPOT:ETHUSDT", Decimal("20")),
            ],
        )

    def test_opening_and_unclosed_positions_are_not_eligible(self):
        source, snapshots, valuations = self.inputs("10")
        snapshot = snapshots[0]
        opening = {
            "instrument_id": "BINANCE:SPOT:BTCUSDT",
            "signed_quantity": "1",
            "moving_average_entry_price": "100",
            "contract_multiplier": "1",
        }
        snapshot["opening_positions"] = [opening]
        snapshot["equity_points"][0]["position_cost_bases"] = [opening]
        snapshot["fills"] = [
            fill(
                "opening-close",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="SELL",
                quantity="1",
                price="110",
                sequence=2,
                hour=6,
            ),
            fill(
                "unclosed-open",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="BUY",
                quantity="1",
                price="105",
                sequence=3,
                hour=12,
            ),
        ]
        ending = {
            "instrument_id": "BINANCE:SPOT:BTCUSDT",
            "signed_quantity": "1",
            "moving_average_entry_price": "105",
            "contract_multiplier": "1",
        }
        snapshot["equity_points"][-1]["position_cost_bases"] = [ending]
        valuations[0]["instruments"] = [
            {
                "instrument_id": "BINANCE:SPOT:BTCUSDT",
                "long_executable_exit_price_usdt": "100",
                "short_executable_exit_price_usdt": None,
                "contract_multiplier": "1",
                "expected_exit_fee_usdt": "0",
                "valuation_source_hash": "8" * 64,
            }
        ]
        valuations[-1]["instruments"] = [
            {
                "instrument_id": "BINANCE:SPOT:BTCUSDT",
                "long_executable_exit_price_usdt": "105",
                "short_executable_exit_price_usdt": None,
                "contract_multiplier": "1",
                "expected_exit_fee_usdt": "0",
                "valuation_source_hash": "9" * 64,
            }
        ]
        self.rehash(source, snapshots, valuations)

        analysis = self.analyze(source, snapshots, valuations)

        self.assertEqual(len(analysis.completed_trades), 1)
        self.assertFalse(analysis.completed_trades[0].eligible)
        self.assertEqual(
            analysis.completed_trades[0].fill_ids,
            ("opening-close",),
        )

    def test_fill_crossing_zero_fails_closed(self):
        source, snapshots, valuations = self.inputs()
        snapshots[0]["fills"][1]["quantity"] = "2"
        self.rehash(source, snapshots, valuations)

        with self.assertRaisesRegex(
            ValueError,
            "TRADE_REPLAY_FILL_CROSSES_ZERO",
        ):
            self.analyze(source, snapshots, valuations)

    def test_multiplier_change_fails_closed(self):
        source, snapshots, valuations = self.inputs()
        snapshots[0]["fills"][1]["contract_multiplier"] = "2"
        self.rehash(source, snapshots, valuations)

        with self.assertRaisesRegex(
            ValueError,
            "TRADE_REPLAY_MULTIPLIER_CHANGED",
        ):
            self.analyze(source, snapshots, valuations)

    def test_original_equity_must_replay_at_every_checkpoint(self):
        source, snapshots, valuations = self.inputs()
        snapshot = snapshots[0]
        snapshot["ending_liquidation_equity_usdt"] = "1010.01"
        snapshot["equity_points"][-1]["liquidation_equity_usdt"] = "1010.01"
        snapshot["equity_points"][-1]["marked_equity_usdt"] = "1010.01"
        self.rehash(
            source,
            snapshots,
            valuations,
        )

        with self.assertRaisesRegex(
            ValueError,
            "TRADE_REPLAY_ORIGINAL_EQUITY_MISMATCH",
        ):
            self.analyze(source, snapshots, valuations)

    def test_funding_position_must_match_replayed_position(self):
        source, snapshots, valuations = self.inputs("11")
        snapshot = snapshots[0]
        snapshot["funding_cashflows"] = [
            {
                "funding_id": "funding-invalid-position",
                "source_event_sequence": 3,
                "instrument_id": "BINANCE:SPOT:BTCUSDT",
                "signed_amount_usdt": "1",
                "position_quantity": "2",
                "funding_rate": "0.01",
                "mark_price": "100",
                "settled_at": timestamp(12),
            }
        ]
        snapshot["fills"][1]["source_event_sequence"] = 4
        snapshot["equity_points"][-1]["source_event_sequence"] = 5
        self.rehash(source, snapshots, valuations)

        with self.assertRaisesRegex(
            ValueError,
            "TRADE_REPLAY_FUNDING_POSITION_MISMATCH",
        ):
            self.analyze(source, snapshots, valuations)

    def test_trade_id_is_stable_and_uploader_cannot_supply_it(self):
        source, snapshots, valuations = self.inputs()

        first = self.analyze(source, snapshots, valuations)
        second = self.analyze(source, snapshots, valuations)

        expected = (
            "trd:"
            "ab29083599dcffce5ff2f7966f5d6a53"
            "d49d2970ba054a37ea0a81f69467a53c"
        )
        self.assertEqual(first.completed_trades[0].trade_id, expected)
        self.assertEqual(second.completed_trades[0].trade_id, expected)

        forged_source = deepcopy(source)
        forged_snapshots = deepcopy(snapshots)
        forged_valuations = deepcopy(valuations)
        forged_snapshots[0]["fills"][0]["trade_id"] = "uploader-choice"
        self.rehash(
            forged_source,
            forged_snapshots,
            forged_valuations,
        )
        with self.assertRaisesRegex(
            ValueError,
            "TRADE_REPLAY_UPLOADER_TRADE_ID_FORBIDDEN",
        ):
            self.analyze(
                forged_source,
                forged_snapshots,
                forged_valuations,
            )


if __name__ == "__main__":
    unittest.main()
