import inspect
import json
import unittest

from crypto_quant.canonical import canonical_json
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


if __name__ == "__main__":
    unittest.main()
