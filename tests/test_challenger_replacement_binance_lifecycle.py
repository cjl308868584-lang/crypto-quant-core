import inspect
import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from crypto_quant.canonical import canonical_json
import crypto_quant.challenger_replacement_binance_lifecycle as lifecycle
from crypto_quant.challenger_replacement_binance_simulation_input import (
    load_challenger_replacement_binance_simulation_input_bytes,
)
from crypto_quant.challenger_replacement_binance_lifecycle import (
    ChallengerReplacementLifecycleError,
    simulate_challenger_replacement_binance_lifecycle,
)
from crypto_quant.challenger_replacement_simulation import (
    build_challenger_replacement_genesis_snapshot,
    simulate_challenger_replacement_opportunity,
)
from crypto_quant.evidence import artifact_self_hash
from tests.challenger_replacement_v3_fixtures import (
    fixture_opportunity_id,
    fixture_v071_build_identity,
    fixture_v071_contract,
    fixture_v071_signal_bars,
    fixture_v072_build_identity,
    fixture_v072_input_bytes,
    fixture_v3_plan,
)


class ChallengerReplacementBinanceLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture_v3_plan()
        self.contract = fixture_v071_contract()
        self.build = fixture_v072_build_identity()
        self.source = load_challenger_replacement_binance_simulation_input_bytes(
            fixture_v072_input_bytes(bars=fixture_v071_signal_bars("FLAT")),
            plan=self.plan,
            contract=self.contract,
            build_identity=self.build,
            opportunity_id=fixture_opportunity_id(),
        )
        self.genesis = build_challenger_replacement_genesis_snapshot(
            plan=self.plan,
            contract=self.contract,
        )

    def source_for(
        self,
        signal,
        scheduled_for="2026-08-24T00:00:00.000Z",
        bars=None,
        **kwargs,
    ):
        scheduled = datetime.fromisoformat(scheduled_for.replace("Z", "+00:00"))
        observed_at = (scheduled + timedelta(minutes=5)).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        data = fixture_v072_input_bytes(
            scheduled_for=scheduled_for,
            observed_at=observed_at,
            bars=(
                fixture_v071_signal_bars(signal, scheduled_for)
                if bars is None
                else bars
            ),
            **kwargs,
        )
        return load_challenger_replacement_binance_simulation_input_bytes(
            data,
            plan=self.plan,
            contract=self.contract,
            build_identity=self.build,
            opportunity_id=fixture_opportunity_id(scheduled_for),
        )

    def simulate(self, **overrides):
        values = {
            "source": self.source,
            "previous_projection": self.genesis,
            "plan": self.plan,
            "contract": self.contract,
            "build_identity": self.build,
        }
        values.update(overrides)
        return simulate_challenger_replacement_binance_lifecycle(**values)

    def test_public_entrypoint_has_no_caller_identity_or_scenario_seam(self):
        self.assertEqual(
            tuple(inspect.signature(
                simulate_challenger_replacement_binance_lifecycle
            ).parameters),
            (
                "source",
                "previous_projection",
                "plan",
                "contract",
                "build_identity",
            ),
        )
        with self.assertRaises(TypeError):
            self.simulate(intent_id="caller-chosen")

    def test_no_intent_has_exact_canonical_lifecycle(self):
        result = self.simulate()
        expected = simulate_challenger_replacement_opportunity(
            source=self.source,
            previous_projection=self.genesis,
            plan=self.plan,
            contract=self.contract,
            build_identity=self.build,
        )
        self.assertEqual(result.source_bytes, canonical_json(self.source).encode())
        self.assertEqual(
            result.previous_snapshot_bytes,
            canonical_json(self.genesis).encode(),
        )
        self.assertEqual(
            json.loads(result.plan_identity_bytes),
            {"plan_hash": self.plan["plan_hash"], "plan_id": self.plan["plan_id"]},
        )
        self.assertEqual(
            json.loads(result.contract_identity_bytes),
            {
                "contract_hash": self.contract["contract_hash"],
                "contract_id": self.contract["contract_id"],
            },
        )
        self.assertEqual(json.loads(result.build_identity_bytes), self.build)
        self.assertEqual(json.loads(result.decision_bytes), expected["decision"])
        self.assertEqual(json.loads(result.accounting_bytes), expected["accounting"])
        self.assertEqual(json.loads(result.next_snapshot_bytes), expected["next_snapshot"])
        self.assertEqual(
            [event.event_type for event in result.lifecycle_events],
            ["NO_INTENT_RECONCILED", "LIFECYCLE_RECONCILED_FIXTURE"],
        )
        self.assertEqual(result.status, "RECONCILED_FIXTURE")
        self.assertTrue(result.operationally_complete)
        self.assertIsNone(result.reason_code_or_null)

    def test_no_intent_event_envelope_payload_and_hash_chain_are_exact(self):
        events = self.simulate().lifecycle_events
        self.assertEqual(
            json.loads(events[0].payload_bytes),
            {"action": "HOLD_FLAT", "reason_code": "NO_ENTRY_SIGNAL"},
        )
        self.assertEqual(
            set(json.loads(events[1].payload_bytes)),
            {
                "engine_projection_hash",
                "venue_projection_hash",
                "ledger_projection_hash",
            },
        )
        for index, event in enumerate(events, 1):
            self.assertEqual(event.ordinal, index)
            self.assertIsNone(event.intent_id_or_null)
            self.assertIsNone(event.attempt_id_or_null)
            self.assertEqual(
                event.parent_event_hash_or_null,
                None if index == 1 else events[index - 2].event_hash,
            )
            envelope = {
                "ordinal": event.ordinal,
                "event_type": event.event_type,
                "event_hash": event.event_hash,
                "parent_event_hash_or_null": event.parent_event_hash_or_null,
                "intent_id_or_null": event.intent_id_or_null,
                "attempt_id_or_null": event.attempt_id_or_null,
                "payload": json.loads(event.payload_bytes),
            }
            self.assertEqual(
                event.event_hash,
                artifact_self_hash(envelope, "event_hash"),
            )

    def test_lifecycle_rejects_non_v072_or_unbound_build(self):
        with self.assertRaisesRegex(
            ChallengerReplacementLifecycleError,
            "CHALLENGER_REPLACEMENT_LIFECYCLE_IDENTITY_INVALID",
        ):
            self.simulate(build_identity=fixture_v071_build_identity())

    def test_spot_open_has_exact_full_fill_and_confirmed_stop_sequence(self):
        result = self.simulate(source=self.source_for("LONG"))
        self.assertEqual(
            [event.event_type for event in result.lifecycle_events],
            [
                "INTENT_PREPARED",
                "ATTEMPT_SUBMITTED_FIXTURE",
                "ORDER_ACKNOWLEDGED_FIXTURE",
                "FILL_OBSERVED_FIXTURE",
                "ORDER_RECONCILED_FIXTURE",
                "STOP_INTENT_PREPARED",
                "STOP_ACKNOWLEDGED_FIXTURE",
                "LIFECYCLE_RECONCILED_FIXTURE",
            ],
        )
        decision = json.loads(result.decision_bytes)
        accounting = json.loads(result.accounting_bytes)
        snapshot = json.loads(result.next_snapshot_bytes)
        self.assertEqual(decision["action"], "OPEN_SPOT_LONG")
        self.assertEqual(accounting["fill_price"], "2003.01")
        self.assertEqual(snapshot["position_state"], "SPOT_LONG")
        stop = snapshot["protective_stop_or_null"]
        self.assertEqual(
            set(stop),
            {
                "stop_intent_id",
                "stop_attempt_id",
                "stop_client_order_id",
                "product",
                "side",
                "reduce_only",
                "quantity",
                "trigger_price",
                "status",
            },
        )
        self.assertEqual(
            {key: stop[key] for key in (
                "product", "side", "reduce_only", "quantity",
                "trigger_price", "status",
            )},
            {
                "product": "spot",
                "side": "SELL",
                "reduce_only": False,
                "quantity": accounting["quantity"],
                "trigger_price": "1962.94",
                "status": "CONFIRMED_FIXTURE",
            },
        )
        self.assertRegex(stop["stop_intent_id"], r"^replacement_stop_[0-9a-f]{64}$")
        self.assertRegex(stop["stop_attempt_id"], r"^replacement_attempt_[0-9a-f]{64}$")
        self.assertRegex(stop["stop_client_order_id"], r"^replacement_client_[0-9a-f]{64}$")
        stop_prepared = json.loads(result.lifecycle_events[5].payload_bytes)
        stop_ack = json.loads(result.lifecycle_events[6].payload_bytes)
        self.assertEqual(stop_prepared["stop_intent_id"], stop["stop_intent_id"])
        self.assertEqual(stop_ack["stop_client_order_id"], stop["stop_client_order_id"])

    def test_perpetual_open_is_sell_isolated_and_has_rounded_up_stop(self):
        result = self.simulate(source=self.source_for("SHORT"))
        decision = json.loads(result.decision_bytes)
        accounting = json.loads(result.accounting_bytes)
        snapshot = json.loads(result.next_snapshot_bytes)
        intent = json.loads(result.lifecycle_events[0].payload_bytes)
        stop = snapshot["protective_stop_or_null"]
        self.assertEqual(decision["action"], "OPEN_PERP_SHORT")
        self.assertEqual(intent["product"], "perpetual")
        self.assertEqual(intent["side"], "SELL")
        self.assertFalse(intent["reduce_only"])
        self.assertGreater(Decimal(snapshot["isolated_margin"]), 0)
        self.assertEqual(stop["side"], "BUY")
        self.assertTrue(stop["reduce_only"])
        self.assertEqual(stop["quantity"], accounting["quantity"])
        self.assertEqual(stop["trigger_price"], "2036.43")

    def test_normal_close_cancels_stop_before_reduce_order_and_finishes_flat(self):
        cases = (
            ("LONG", "SPOT_LONG", "spot", "SELL", False),
            ("SHORT", "PERP_SHORT", "perpetual", "BUY", True),
        )
        for signal, state, product, side, reduce_only in cases:
            with self.subTest(product=product):
                opened = self.simulate(source=self.source_for(signal))
                previous = json.loads(opened.next_snapshot_bytes)
                self.assertEqual(previous["position_state"], state)
                closed = self.simulate(
                    source=self.source_for(
                        "FLAT", "2026-08-24T12:00:00.000Z"
                    ),
                    previous_projection=previous,
                )
                self.assertEqual(
                    [event.event_type for event in closed.lifecycle_events],
                    [
                        "STOP_CANCEL_REQUESTED_FIXTURE",
                        "STOP_CANCEL_ACKNOWLEDGED_FIXTURE",
                        "INTENT_PREPARED",
                        "ATTEMPT_SUBMITTED_FIXTURE",
                        "ORDER_ACKNOWLEDGED_FIXTURE",
                        "FILL_OBSERVED_FIXTURE",
                        "ORDER_RECONCILED_FIXTURE",
                        "LIFECYCLE_RECONCILED_FIXTURE",
                    ],
                )
                intent = json.loads(closed.lifecycle_events[2].payload_bytes)
                self.assertEqual(intent["product"], product)
                self.assertEqual(intent["side"], side)
                self.assertEqual(intent["reduce_only"], reduce_only)
                next_snapshot = json.loads(closed.next_snapshot_bytes)
                self.assertEqual(next_snapshot["position_state"], "FLAT")
                self.assertIsNone(next_snapshot["protective_stop_or_null"])

    def test_perpetual_hold_applies_funding_and_preserves_exact_stop(self):
        opened = self.simulate(source=self.source_for("SHORT"))
        previous = json.loads(opened.next_snapshot_bytes)
        held = self.simulate(
            source=self.source_for(
                "SHORT",
                "2026-08-24T04:00:00.000Z",
                funding_boundary_at_or_null="2026-08-24T04:00:00.000Z",
                funding_rate_or_null="0.0001",
            ),
            previous_projection=previous,
        )
        self.assertEqual(json.loads(held.decision_bytes)["action"], "HOLD_PERP_SHORT")
        self.assertNotEqual(json.loads(held.accounting_bytes)["funding_cashflow"], "0")
        self.assertEqual(
            json.loads(held.next_snapshot_bytes)["protective_stop_or_null"],
            previous["protective_stop_or_null"],
        )

    def test_stop_trigger_precedes_strategy_and_uses_gap_adverse_fill(self):
        cases = (
            ("LONG", "spot", "STOP_CLOSE_SPOT_LONG", "1960.97", "low", "1900"),
            ("SHORT", "perpetual", "STOP_CLOSE_PERP_SHORT", "2038.47", "high", "2100"),
        )
        for signal, product, action, fill, extreme_key, extreme in cases:
            with self.subTest(product=product):
                opened = self.simulate(source=self.source_for(signal))
                previous = json.loads(opened.next_snapshot_bytes)
                scheduled = "2026-08-24T04:00:00.000Z"
                bars = fixture_v071_signal_bars("FLAT", scheduled)
                bars[-1][extreme_key] = extreme
                stopped = self.simulate(
                    source=self.source_for("FLAT", scheduled, bars=bars),
                    previous_projection=previous,
                )
                decision = json.loads(stopped.decision_bytes)
                self.assertEqual(decision["action"], action)
                self.assertEqual(decision["reason_code"], "PROTECTIVE_STOP_TRIGGERED")
                self.assertEqual(decision["risk_approval"], "REDUCE_ONLY")
                self.assertEqual(
                    [event.event_type for event in stopped.lifecycle_events],
                    [
                        "STOP_TRIGGERED_FIXTURE",
                        "FILL_OBSERVED_FIXTURE",
                        "ORDER_RECONCILED_FIXTURE",
                        "LIFECYCLE_RECONCILED_FIXTURE",
                    ],
                )
                self.assertEqual(json.loads(stopped.accounting_bytes)["fill_price"], fill)
                self.assertEqual(
                    json.loads(stopped.next_snapshot_bytes)["position_state"],
                    "FLAT",
                )

    def test_three_reconciliation_reducers_have_distinct_types_and_fresh_venue(self):
        captured = []
        original = lifecycle._reduce_venue

        def capture(observations, previous_position):
            value = original(observations, previous_position)
            captured.append((observations, previous_position, value))
            return value

        with patch.object(lifecycle, "_reduce_venue", side_effect=capture):
            result = self.simulate(source=self.source_for("LONG"))
        self.assertEqual(result.status, "RECONCILED_FIXTURE")
        observations, previous_position, venue = captured[0]
        fresh = original(tuple(observations), previous_position)
        self.assertEqual(fresh, venue)
        self.assertIsInstance(venue, lifecycle.VenueProjection)
        self.assertNotIsInstance(venue, lifecycle.EngineProjection)
        self.assertNotIsInstance(venue, lifecycle.LedgerProjection)

    def test_each_independent_projection_mismatch_fails_closed(self):
        for reducer_name in ("_reduce_engine", "_reduce_venue", "_reduce_ledger"):
            with self.subTest(reducer=reducer_name):
                original = getattr(lifecycle, reducer_name)

                def tamper(*args, _original=original):
                    return replace(_original(*args), signed_quantity="999")

                with patch.object(lifecycle, reducer_name, side_effect=tamper):
                    result = self.simulate(source=self.source_for("LONG"))
                self.assertEqual(result.status, "FAILED_CLOSED")
                self.assertFalse(result.operationally_complete)
                self.assertEqual(
                    result.reason_code_or_null,
                    "LEDGER_POSITION_MISMATCH",
                )
                self.assertEqual(
                    result.lifecycle_events[-1].event_type,
                    "LIFECYCLE_FAILED_CLOSED",
                )
                snapshot = json.loads(result.next_snapshot_bytes)
                self.assertEqual(snapshot["risk_state"], "STAGE_FAILED_LOCKED")

    def test_fill_before_ack_is_preserved_and_reconciles_once(self):
        original = lifecycle._normal_lifecycle_observations

        def fill_before_ack(*args):
            item = original(*args)[0]
            return (replace(item, fill_before_ack=True),)

        with patch.object(
            lifecycle, "_normal_lifecycle_observations", side_effect=fill_before_ack
        ):
            result = self.simulate(source=self.source_for("LONG"))
        types = [event.event_type for event in result.lifecycle_events]
        self.assertLess(
            types.index("FILL_OBSERVED_FIXTURE"),
            types.index("ORDER_ACKNOWLEDGED_FIXTURE"),
        )
        self.assertEqual(types.count("FILL_OBSERVED_FIXTURE"), 1)
        self.assertEqual(result.status, "RECONCILED_FIXTURE")

    def test_fixed_fault_observations_fail_with_single_frozen_reason(self):
        cases = (
            ({"unknown_reason_or_null": "TIMEOUT"}, "UNRESOLVED_UNKNOWN"),
            ({"conflicting_duplicate": True}, "DUPLICATE_ECONOMIC_ORDER"),
            ({"overfill": True}, "UNRECORDED_OR_CONFLICTING_FILL"),
            ({"stop_confirmed": False}, "DISASTER_STOP_MISSING_OR_UNCONFIRMED"),
        )
        original = lifecycle._normal_lifecycle_observations
        for changes, reason in cases:
            with self.subTest(reason=reason):
                def fault(*args, _changes=changes):
                    return (replace(original(*args)[0], **_changes),)

                with patch.object(
                    lifecycle,
                    "_normal_lifecycle_observations",
                    side_effect=fault,
                ):
                    result = self.simulate(source=self.source_for("LONG"))
                self.assertEqual(result.status, "FAILED_CLOSED")
                self.assertEqual(result.reason_code_or_null, reason)
                self.assertEqual(
                    result.lifecycle_events[-1].event_type,
                    "LIFECYCLE_FAILED_CLOSED",
                )

    def test_partial_fill_rebuilds_one_quantity_exact_stop_before_success(self):
        original = lifecycle._normal_lifecycle_observations

        def partial(*args):
            return (replace(
                original(*args)[0],
                partial_first_quantity_or_null="0.01",
            ),)

        with patch.object(
            lifecycle, "_normal_lifecycle_observations", side_effect=partial
        ):
            result = self.simulate(source=self.source_for("LONG"))
        types = [event.event_type for event in result.lifecycle_events]
        first = types.index("FILL_OBSERVED_FIXTURE")
        second = types.index("FILL_OBSERVED_FIXTURE", first + 1)
        self.assertEqual(
            types[first:first + 3],
            ["FILL_OBSERVED_FIXTURE", "STOP_INTENT_PREPARED", "STOP_ACKNOWLEDGED_FIXTURE"],
        )
        self.assertEqual(
            types[second:second + 5],
            [
                "FILL_OBSERVED_FIXTURE",
                "STOP_CANCEL_REQUESTED_FIXTURE",
                "STOP_CANCEL_ACKNOWLEDGED_FIXTURE",
                "STOP_INTENT_PREPARED",
                "STOP_ACKNOWLEDGED_FIXTURE",
            ],
        )
        stops = [
            json.loads(event.payload_bytes)
            for event in result.lifecycle_events
            if event.event_type == "STOP_INTENT_PREPARED"
        ]
        self.assertEqual([item["quantity"] for item in stops], ["0.01", "0.0249"])
        self.assertNotEqual(stops[0]["stop_intent_id"], stops[1]["stop_intent_id"])
        final_stop = json.loads(result.next_snapshot_bytes)["protective_stop_or_null"]
        self.assertEqual(final_stop["stop_intent_id"], stops[-1]["stop_intent_id"])
        fills = [
            json.loads(event.payload_bytes)
            for event in result.lifecycle_events
            if event.event_type == "FILL_OBSERVED_FIXTURE"
        ]
        self.assertTrue(all(Decimal(item["fee"]).as_tuple().exponent >= -8 for item in fills))
        self.assertEqual(
            sum((Decimal(item["fee"]) for item in fills), Decimal("0")),
            Decimal(json.loads(result.accounting_bytes)["fee"]),
        )
        self.assertEqual(result.status, "RECONCILED_FIXTURE")

    def test_partial_fill_protection_faults_never_return_reconciled(self):
        cases = (
            ("missing_cancel_ack", "DISASTER_STOP_MISSING_OR_UNCONFIRMED"),
            ("missing_new_stop_ack", "DISASTER_STOP_MISSING_OR_UNCONFIRMED"),
            ("second_fill_before_stop_ack", "DISASTER_STOP_MISSING_OR_UNCONFIRMED"),
            ("old_stop_late_fill", "UNRECORDED_OR_CONFLICTING_FILL"),
            ("wrong_product_or_side", "UNRECORDED_OR_CONFLICTING_FILL"),
            ("flatten_succeeded", "DISASTER_STOP_MISSING_OR_UNCONFIRMED"),
        )
        original = lifecycle._normal_lifecycle_observations
        for field, reason in cases:
            with self.subTest(field=field):
                value = False if field == "flatten_succeeded" else True
                def fault(*args, _field=field, _value=value):
                    return (replace(
                        original(*args)[0],
                        partial_first_quantity_or_null="0.01",
                        **{_field: _value},
                    ),)
                with patch.object(
                    lifecycle, "_normal_lifecycle_observations", side_effect=fault
                ):
                    result = self.simulate(source=self.source_for("LONG"))
                self.assertEqual(result.status, "FAILED_CLOSED")
                self.assertEqual(result.reason_code_or_null, reason)
                snapshot = json.loads(result.next_snapshot_bytes)
                self.assertEqual(snapshot["risk_state"], "STAGE_FAILED_LOCKED")
                self.assertEqual(snapshot["position_state"], "SPOT_LONG")
                self.assertIsNone(snapshot["protective_stop_or_null"])
                types = [event.event_type for event in result.lifecycle_events]
                if field == "missing_cancel_ack":
                    self.assertIn("STOP_CANCEL_REQUESTED_FIXTURE", types)
                    self.assertNotIn("STOP_CANCEL_ACKNOWLEDGED_FIXTURE", types)
                elif field == "missing_new_stop_ack":
                    self.assertEqual(types.count("STOP_INTENT_PREPARED"), 2)
                    self.assertEqual(types.count("STOP_ACKNOWLEDGED_FIXTURE"), 1)
                elif field == "second_fill_before_stop_ack":
                    first_fill = types.index("FILL_OBSERVED_FIXTURE")
                    second_fill = types.index("FILL_OBSERVED_FIXTURE", first_fill + 1)
                    first_stop_ack = types.index("STOP_ACKNOWLEDGED_FIXTURE")
                    self.assertLess(second_fill, first_stop_ack)
                elif field == "old_stop_late_fill":
                    cancel_ack = types.index("STOP_CANCEL_ACKNOWLEDGED_FIXTURE")
                    late_fill = types.index("FILL_OBSERVED_FIXTURE", cancel_ack + 1)
                    self.assertGreater(late_fill, cancel_ack)

    def test_exact_duplicate_observation_is_normalized_once(self):
        original = lifecycle._normal_lifecycle_observations
        def duplicate(*args):
            item = original(*args)[0]
            return item, item
        with patch.object(
            lifecycle, "_normal_lifecycle_observations", side_effect=duplicate
        ):
            result = self.simulate(source=self.source_for("LONG"))
        self.assertEqual(result.status, "RECONCILED_FIXTURE")
        self.assertEqual(
            [event.event_type for event in result.lifecycle_events].count(
                "FILL_OBSERVED_FIXTURE"
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
