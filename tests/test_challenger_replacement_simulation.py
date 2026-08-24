import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import unittest

from crypto_quant.evidence import artifact_self_hash
from crypto_quant.challenger_replacement_binance_simulation_input import (
    load_challenger_replacement_binance_simulation_input_bytes,
)
from crypto_quant.challenger_replacement_simulation import (
    ChallengerReplacementSimulationError,
    build_challenger_replacement_genesis_snapshot,
    compute_challenger_replacement_simulation_decision,
    simulate_challenger_replacement_opportunity,
)
from tests.challenger_replacement_v3_fixtures import (
    fixture_opportunity_id,
    fixture_v071_build_identity,
    fixture_v071_contract,
    fixture_v071_input_bytes,
    fixture_v071_perpetual_metadata,
    fixture_v071_signal_bars,
    fixture_v071_spot_metadata,
    fixture_v3_plan,
)


class ChallengerReplacementSimulationTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture_v3_plan()
        self.contract = fixture_v071_contract()
        self.build = fixture_v071_build_identity()

    def source(
        self,
        *,
        signal="LONG",
        scheduled_for="2026-08-24T00:00:00.000Z",
        observed_at=None,
        spot_quote=None,
        perpetual_quote=None,
        funding_rate=None,
        spot_metadata=None,
        perpetual_metadata=None,
    ):
        scheduled = datetime.fromisoformat(
            scheduled_for.replace("Z", "+00:00")
        )
        observed_at = observed_at or (
            scheduled + timedelta(minutes=5)
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        data = fixture_v071_input_bytes(
            scheduled_for=scheduled_for,
            observed_at=observed_at,
            bars=fixture_v071_signal_bars(signal, scheduled_for),
            spot_quote=spot_quote,
            perpetual_quote=perpetual_quote,
            funding_boundary_at_or_null=(
                None if funding_rate is None else scheduled_for
            ),
            funding_rate_or_null=funding_rate,
            spot_metadata=spot_metadata,
            perpetual_metadata=perpetual_metadata,
        )
        return load_challenger_replacement_binance_simulation_input_bytes(
            data,
            plan=self.plan,
            contract=self.contract,
            build_identity=self.build,
            opportunity_id=fixture_opportunity_id(scheduled_for),
        )

    def genesis(self):
        return build_challenger_replacement_genesis_snapshot(
            plan=self.plan,
            contract=self.contract,
        )

    def simulate(self, source, previous=None):
        return simulate_challenger_replacement_opportunity(
            source=source,
            previous_projection=self.genesis() if previous is None else previous,
            plan=self.plan,
            contract=self.contract,
            build_identity=self.build,
        )

    def test_genesis_is_exact_verified_flat_self_hashed_snapshot(self):
        snapshot = self.genesis()
        self.assertEqual(snapshot["position_state"], "FLAT")
        self.assertEqual(snapshot["position_certainty"], "VERIFIED")
        self.assertEqual(snapshot["cash"], "100")
        self.assertEqual(snapshot["signed_quantity"], "0")
        self.assertEqual(snapshot["marked_equity"], "100")
        self.assertEqual(snapshot["peak_equity"], "100")
        self.assertIsNone(snapshot["parent_snapshot_hash_or_null"])
        self.assertIsNone(snapshot["opportunity_id_or_null"])
        self.assertEqual(
            snapshot["snapshot_hash"],
            artifact_self_hash(snapshot, "snapshot_hash"),
        )

    def test_flat_decision_uses_exact_sma20_and_lag5_sign(self):
        cases = (
            ("LONG", "OPEN_SPOT_LONG", "LONG_ENTRY_SIGNAL"),
            ("SHORT", "OPEN_PERP_SHORT", "SHORT_ENTRY_SIGNAL"),
            ("FLAT", "HOLD_FLAT", "NO_ENTRY_SIGNAL"),
        )
        for signal, action, reason in cases:
            with self.subTest(signal=signal):
                source = self.source(signal=signal)
                decision = compute_challenger_replacement_simulation_decision(
                    source=source,
                    previous_projection=self.genesis(),
                    plan=self.plan,
                    contract=self.contract,
                )
                self.assertEqual(decision["action"], action)
                self.assertEqual(decision["reason_code"], reason)
                self.assertEqual(decision["indicators"]["prior_sma20"], "2000")
                self.assertEqual(
                    decision["indicators"]["latest_close"],
                    {"LONG": "2020", "SHORT": "1980", "FLAT": "2000"}[signal],
                )
                self.assertEqual(
                    decision["decision_hash"],
                    artifact_self_hash(decision, "decision_hash"),
                )
                self.assertEqual(
                    decision["plan"],
                    {
                        "plan_id": self.plan["plan_id"],
                        "plan_hash": self.plan["plan_hash"],
                    },
                )
                self.assertEqual(
                    decision["policy_bindings"],
                    {
                        "decision_policy_hash": self.plan["decision_policy"][
                            "policy_hash"
                        ],
                        "risk_policy_hash": self.plan["risk_policy"]["policy_hash"],
                    },
                )

    def test_spot_open_uses_adverse_fill_fee_and_conservative_bid_mark(self):
        result = self.simulate(self.source(signal="LONG"))
        snapshot = result["next_snapshot"]
        self.assertEqual(result["decision"]["action"], "OPEN_SPOT_LONG")
        self.assertEqual(snapshot["position_state"], "SPOT_LONG")
        self.assertEqual(result["accounting"]["fill_price"], "2003.01")
        self.assertEqual(snapshot["signed_quantity"], "0.0249")
        self.assertEqual(result["accounting"]["fee"], "0.07481243")
        self.assertEqual(snapshot["cash"], "50.05023857")
        self.assertEqual(snapshot["marked_equity"], "99.82533857")
        self.assertEqual(snapshot["isolated_margin"], "0")
        self.assertLessEqual(Decimal(snapshot["gross_exposure"]), Decimal("0.5"))

    def test_perp_open_is_negative_signed_isolated_and_marked_once(self):
        result = self.simulate(self.source(signal="SHORT"))
        snapshot = result["next_snapshot"]
        self.assertEqual(result["decision"]["action"], "OPEN_PERP_SHORT")
        self.assertEqual(result["accounting"]["fill_price"], "1996.5")
        self.assertEqual(snapshot["signed_quantity"], "-0.024")
        self.assertEqual(result["accounting"]["fee"], "0.071874")
        self.assertEqual(snapshot["cash"], "99.928126")
        self.assertEqual(snapshot["isolated_margin"], "47.916")
        self.assertEqual(snapshot["unrealized_pnl"], "-0.066")
        self.assertEqual(snapshot["marked_equity"], "99.862126")

    def test_multiplier_is_used_in_notional_fee_margin_and_mark(self):
        metadata = fixture_v071_perpetual_metadata(multiplier="2")
        result = self.simulate(
            self.source(signal="SHORT", perpetual_metadata=metadata)
        )
        snapshot = result["next_snapshot"]
        self.assertEqual(snapshot["signed_quantity"], "-0.012")
        self.assertEqual(result["accounting"]["notional"], "47.916")
        self.assertEqual(snapshot["isolated_margin"], "47.916")
        self.assertEqual(result["accounting"]["fee"], "0.071874")
        self.assertEqual(snapshot["unrealized_pnl"], "-0.066")

    def test_minimum_hold_and_vertical_exit_are_exact(self):
        opened = self.simulate(self.source(signal="LONG"))["next_snapshot"]
        at_four = compute_challenger_replacement_simulation_decision(
            source=self.source(
                signal="SHORT", scheduled_for="2026-08-24T04:00:00.000Z"
            ),
            previous_projection=opened,
            plan=self.plan,
            contract=self.contract,
        )
        at_eight = compute_challenger_replacement_simulation_decision(
            source=self.source(
                signal="SHORT", scheduled_for="2026-08-24T08:00:00.000Z"
            ),
            previous_projection=opened,
            plan=self.plan,
            contract=self.contract,
        )
        self.assertEqual(at_four["action"], "HOLD_SPOT_LONG")
        self.assertEqual(at_four["reason_code"], "MINIMUM_HOLD_ACTIVE")
        self.assertEqual(at_eight["action"], "CLOSE_SPOT_LONG")
        self.assertEqual(at_eight["reason_code"], "LONG_EXIT_SIGNAL")

        still_long = copy.deepcopy(opened)
        still_long["entry_time"] = "2026-08-23T00:00:00.000Z"
        still_long["snapshot_hash"] = artifact_self_hash(
            still_long, "snapshot_hash"
        )
        vertical = compute_challenger_replacement_simulation_decision(
            source=self.source(signal="LONG"),
            previous_projection=still_long,
            plan=self.plan,
            contract=self.contract,
        )
        self.assertEqual(vertical["action"], "CLOSE_SPOT_LONG")
        self.assertEqual(vertical["reason_code"], "VERTICAL_EXIT")

    def test_close_cannot_reverse_in_same_opportunity(self):
        opened = self.simulate(self.source(signal="LONG"))["next_snapshot"]
        closed = self.simulate(
            self.source(
                signal="SHORT",
                scheduled_for="2026-08-24T08:00:00.000Z",
                spot_quote={"bid": "1900", "ask": "1902", "last": "1901"},
            ),
            opened,
        )["next_snapshot"]
        self.assertEqual(closed["position_state"], "FLAT")
        self.assertTrue(closed["reverse_blocked_until_next_opportunity"])
        self.assertEqual(closed["signed_quantity"], "0")

    def test_short_profit_uses_negative_signed_quantity_once(self):
        opened = self.simulate(self.source(signal="SHORT"))["next_snapshot"]
        closed_result = self.simulate(
            self.source(
                signal="LONG",
                scheduled_for="2026-08-24T08:00:00.000Z",
                perpetual_quote={
                    "bid": "1899",
                    "ask": "1900",
                    "last": "1899.5",
                    "mark": "1899.25",
                },
            ),
            opened,
        )
        self.assertEqual(closed_result["accounting"]["realized_pnl"], "2.2704")
        self.assertGreater(
            Decimal(closed_result["next_snapshot"]["cash"]),
            Decimal("100"),
        )

    def test_funding_is_applied_before_decision_and_equity(self):
        opened = self.simulate(self.source(signal="SHORT"))["next_snapshot"]
        held = self.simulate(
            self.source(
                signal="SHORT",
                scheduled_for="2026-08-24T04:00:00.000Z",
                funding_rate="0.001",
            ),
            opened,
        )
        self.assertEqual(held["decision"]["action"], "HOLD_PERP_SHORT")
        self.assertEqual(held["accounting"]["funding_cashflow"], "0.047982")
        self.assertEqual(
            held["next_snapshot"]["cumulative_funding"], "0.047982"
        )

    def test_daily_loss_and_drawdown_equality_fail_closed(self):
        source = self.source(signal="LONG")
        daily = self.genesis()
        daily.update(
            cash="98",
            marked_equity="98",
            day_start_date_or_null="2026-08-24",
            day_start_equity="100",
        )
        daily["snapshot_hash"] = artifact_self_hash(daily, "snapshot_hash")
        decision = compute_challenger_replacement_simulation_decision(
            source=source,
            previous_projection=daily,
            plan=self.plan,
            contract=self.contract,
        )
        self.assertEqual(decision["action"], "HOLD_FLAT")
        self.assertEqual(decision["risk_approval"], "STOP_NEW_RISK")

        drawdown = self.genesis()
        drawdown.update(cash="95", marked_equity="95", peak_equity="100")
        drawdown["snapshot_hash"] = artifact_self_hash(
            drawdown, "snapshot_hash"
        )
        decision = compute_challenger_replacement_simulation_decision(
            source=source,
            previous_projection=drawdown,
            plan=self.plan,
            contract=self.contract,
        )
        self.assertEqual(decision["action"], "RISK_FLATTEN")
        self.assertEqual(decision["risk_approval"], "STAGE_FAILED_LOCKED")

    def test_open_sizing_uses_current_equity_not_genesis_constant(self):
        reduced = self.genesis()
        reduced.update(
            cash="80",
            marked_equity="80",
            peak_equity="80",
            day_start_date_or_null="2026-08-24",
            day_start_equity="80",
        )
        reduced["snapshot_hash"] = artifact_self_hash(
            reduced, "snapshot_hash"
        )
        result = self.simulate(self.source(signal="LONG"), reduced)
        self.assertEqual(result["next_snapshot"]["signed_quantity"], "0.0199")
        self.assertLessEqual(
            Decimal(result["accounting"]["notional"]), Decimal("40")
        )

    def test_projected_fill_cost_cannot_cross_daily_or_drawdown_limit(self):
        near_limit = self.genesis()
        near_limit.update(
            cash="98.05",
            marked_equity="98.05",
            peak_equity="100",
            day_start_date_or_null="2026-08-24",
            day_start_equity="100",
        )
        near_limit["snapshot_hash"] = artifact_self_hash(
            near_limit, "snapshot_hash"
        )
        result = self.simulate(self.source(signal="LONG"), near_limit)
        self.assertEqual(result["decision"]["action"], "HOLD_FLAT")
        self.assertEqual(result["decision"]["reason_code"], "PROJECTED_RISK_LIMIT")
        self.assertEqual(result["next_snapshot"]["position_state"], "FLAT")
        self.assertEqual(result["accounting"]["quantity"], "0")

    def test_economic_gap_lock_forbids_new_risk(self):
        locked = self.genesis()
        locked["economic_gap_locked"] = True
        locked["snapshot_hash"] = artifact_self_hash(locked, "snapshot_hash")
        result = self.simulate(self.source(signal="LONG"), locked)
        self.assertEqual(result["decision"]["action"], "HOLD_FLAT")
        self.assertEqual(result["decision"]["reason_code"], "ECONOMIC_GAP_LOCKED")
        self.assertEqual(result["next_snapshot"]["position_state"], "FLAT")
        self.assertEqual(result["next_snapshot"]["risk_state"], "STAGE_FAILED_LOCKED")

    def test_exchange_constraints_no_trade_is_not_a_risk_stop(self):
        result = self.simulate(self.source(
            signal="LONG",
            spot_metadata=fixture_v071_spot_metadata(min_notional="1000"),
        ))
        self.assertEqual(result["decision"]["action"], "HOLD_FLAT")
        self.assertEqual(result["decision"]["reason_code"], "NO_TRADE")
        self.assertEqual(result["decision"]["risk_approval"], "RISK_APPROVED")
        self.assertEqual(result["accounting"]["quantity"], "0")

    def test_gross_drift_flattens_before_strategy_hold(self):
        opened = self.simulate(self.source(signal="LONG"))["next_snapshot"]
        source = self.source(
            signal="LONG",
            scheduled_for="2026-08-24T04:00:00.000Z",
            spot_quote={"bid": "3000", "ask": "3002", "last": "3001"},
        )
        decision = compute_challenger_replacement_simulation_decision(
            source=source,
            previous_projection=opened,
            plan=self.plan,
            contract=self.contract,
        )
        self.assertEqual(decision["action"], "RISK_FLATTEN")
        self.assertEqual(decision["reason_code"], "GROSS_EXPOSURE_DRIFT")
        self.assertEqual(self.simulate(source, opened)["next_snapshot"]["position_state"], "FLAT")

    def test_cash_and_margin_never_exceed_quote_quantum(self):
        spot = self.simulate(
            self.source(
                signal="LONG",
                spot_metadata=fixture_v071_spot_metadata(
                    multiplier="1.23456789"
                ),
            )
        )["next_snapshot"]
        perp = self.simulate(
            self.source(
                signal="SHORT",
                perpetual_metadata=fixture_v071_perpetual_metadata(
                    multiplier="1.23456789"
                ),
            )
        )["next_snapshot"]
        for value in (spot["cash"], perp["cash"], perp["isolated_margin"]):
            with self.subTest(value=value):
                self.assertLessEqual(
                    max(0, len(value.partition(".")[2])),
                    8,
                )

    def test_canonical_result_is_independent_of_caller_decimal_context(self):
        source = self.source(
            signal="LONG",
            spot_metadata=fixture_v071_spot_metadata(multiplier="1.23456789"),
        )
        results = []
        for precision in (10, 16, 28, 50):
            with localcontext() as context:
                context.prec = precision
                results.append(self.simulate(source))
        self.assertTrue(all(result == results[0] for result in results[1:]))

    def test_margin_exhaustion_flattens_with_frozen_reason(self):
        opened = self.simulate(self.source(signal="SHORT"))["next_snapshot"]
        opened["cash"] = "40"
        opened["snapshot_hash"] = artifact_self_hash(opened, "snapshot_hash")
        source = self.source(
            signal="SHORT", scheduled_for="2026-08-24T04:00:00.000Z"
        )
        decision = compute_challenger_replacement_simulation_decision(
            source=source,
            previous_projection=opened,
            plan=self.plan,
            contract=self.contract,
        )
        self.assertEqual(decision["action"], "RISK_FLATTEN")
        self.assertEqual(decision["reason_code"], "SIMULATION_MARGIN_EXHAUSTED")
        self.assertEqual(self.simulate(source, opened)["next_snapshot"]["position_state"], "FLAT")

    def test_daily_stop_unlocks_only_at_next_utc_day_boundary(self):
        stopped = self.genesis()
        stopped.update(
            cash="98",
            marked_equity="98",
            peak_equity="100",
            day_start_date_or_null="2026-08-23",
            day_start_equity="100",
            risk_state="STOP_NEW_RISK",
        )
        stopped["snapshot_hash"] = artifact_self_hash(
            stopped, "snapshot_hash"
        )
        decision = compute_challenger_replacement_simulation_decision(
            source=self.source(signal="LONG"),
            previous_projection=stopped,
            plan=self.plan,
            contract=self.contract,
        )
        self.assertEqual(decision["action"], "OPEN_SPOT_LONG")
        self.assertEqual(decision["risk_approval"], "RISK_APPROVED")

    def test_negative_funding_crosses_daily_limit_before_decision(self):
        opened = self.simulate(self.source(signal="SHORT"))["next_snapshot"]
        opened.update(
            day_start_date_or_null="2026-08-24",
            day_start_equity="101.842126",
        )
        opened["snapshot_hash"] = artifact_self_hash(opened, "snapshot_hash")
        result = self.simulate(
            self.source(
                signal="SHORT",
                scheduled_for="2026-08-24T04:00:00.000Z",
                funding_rate="-0.001",
            ),
            opened,
        )
        self.assertEqual(result["accounting"]["funding_cashflow"], "-0.047982")
        self.assertEqual(result["decision"]["risk_approval"], "REDUCE_OR_HOLD_ONLY")
        self.assertEqual(result["decision"]["daily_loss"], "2.027982")

    def test_negative_funding_debit_rounds_away_from_zero(self):
        opened = self.simulate(self.source(signal="SHORT"))["next_snapshot"]
        result = self.simulate(
            self.source(
                signal="SHORT",
                scheduled_for="2026-08-24T04:00:00.000Z",
                funding_rate="-0.0000000003",
            ),
            opened,
        )
        self.assertEqual(result["accounting"]["funding_cashflow"], "-0.00000002")

    def test_snapshot_binding_and_mutual_exclusion_fail_closed(self):
        result = self.simulate(self.source(signal="LONG"))
        snapshot = result["next_snapshot"]
        self.assertEqual(
            snapshot["parent_snapshot_hash_or_null"],
            self.genesis()["snapshot_hash"],
        )
        self.assertEqual(
            snapshot["snapshot_hash"],
            artifact_self_hash(snapshot, "snapshot_hash"),
        )
        tampered = copy.deepcopy(snapshot)
        tampered["isolated_margin"] = "1"
        tampered["snapshot_hash"] = artifact_self_hash(tampered, "snapshot_hash")
        with self.assertRaisesRegex(
            ChallengerReplacementSimulationError,
            "CHALLENGER_REPLACEMENT_SIMULATION_SNAPSHOT_INVALID",
        ):
            self.simulate(
                self.source(
                    signal="FLAT", scheduled_for="2026-08-24T04:00:00.000Z"
                ),
                tampered,
            )
        malformed = self.genesis()
        malformed["cash"] = "not-a-decimal"
        malformed["snapshot_hash"] = artifact_self_hash(
            malformed, "snapshot_hash"
        )
        with self.assertRaisesRegex(
            ChallengerReplacementSimulationError,
            "CHALLENGER_REPLACEMENT_SIMULATION_SNAPSHOT_INVALID",
        ):
            self.simulate(
                self.source(
                    signal="FLAT", scheduled_for="2026-08-24T04:00:00.000Z"
                ),
                malformed,
            )
        invalid_cases = []
        evil_risk = self.genesis()
        evil_risk["risk_state"] = "EVIL"
        invalid_cases.append(evil_risk)
        active_flat = self.genesis()
        active_flat["active_order_or_null"] = {"fake": True}
        invalid_cases.append(active_flat)
        unresolved = self.genesis()
        unresolved["position_certainty"] = "UNRESOLVED"
        invalid_cases.append(unresolved)
        for candidate in invalid_cases:
            candidate["snapshot_hash"] = artifact_self_hash(
                candidate, "snapshot_hash"
            )
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(
                    ChallengerReplacementSimulationError,
                    "CHALLENGER_REPLACEMENT_SIMULATION_SNAPSHOT_INVALID",
                ):
                    self.simulate(
                        self.source(
                            signal="FLAT",
                            scheduled_for="2026-08-24T04:00:00.000Z",
                        ),
                        candidate,
                    )


if __name__ == "__main__":
    unittest.main()
