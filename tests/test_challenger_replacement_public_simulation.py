import json
import unittest
from copy import deepcopy
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from crypto_quant.challenger_replacement_public_market_capture import (
    load_challenger_replacement_public_market_capture_bytes,
)
from crypto_quant.challenger_replacement_public_simulation import (
    ChallengerReplacementPublicSimulationError,
    build_challenger_replacement_public_genesis_snapshot,
    build_challenger_replacement_public_simulation_input,
    build_challenger_replacement_public_simulation_result,
    _kernel_source,
    load_challenger_replacement_public_simulation_input_bytes,
    load_challenger_replacement_public_simulation_result_bytes,
    simulate_challenger_replacement_public_opportunity,
)
from crypto_quant.challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from crypto_quant.challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from crypto_quant.evidence import artifact_self_hash
from tests.challenger_replacement_v3_fixtures import fixture_v3_plan
from tests.test_challenger_replacement_public_market_capture import (
    COMMITTED_CAPTURE,
    V076_BUILD,
    _canonical_capture,
    _outer_document,
    _replace_request_payload,
    _request_payload,
)


class PublicSimulationInputTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture_v3_plan()
        self.economic_plan = build_challenger_replacement_economic_plan()
        self.predecessor = build_challenger_replacement_simulation_contract(
            plan=self.plan
        )
        self.contract = build_challenger_replacement_public_simulation_contract(
            plan=self.plan,
            economic_plan=self.economic_plan,
            predecessor_contract=self.predecessor,
        )
        self.capture = load_challenger_replacement_public_market_capture_bytes(
            COMMITTED_CAPTURE.read_bytes(),
            plan=self.plan,
            build_identity=V076_BUILD,
            previous_source_bundle=None,
        )

    def _build(self):
        return build_challenger_replacement_public_simulation_input(
            self.capture,
            plan=self.plan,
            economic_plan=self.economic_plan,
            predecessor_contract=self.predecessor,
            public_contract=self.contract,
            build_identity=V076_BUILD,
        )

    def _load(self, document):
        return load_challenger_replacement_public_simulation_input_bytes(
            canonical_json(document).encode("utf-8"),
            plan=self.plan,
            economic_plan=self.economic_plan,
            predecessor_contract=self.predecessor,
            public_contract=self.contract,
            build_identity=V076_BUILD,
            opportunity_id="ETHUSDT@2026-08-26T04:00:00.000Z",
        )

    def test_input_replays_embedded_capture_without_fixture_or_last_fields(self):
        document = self._build()
        loaded = self._load(document)

        self.assertEqual(loaded, document)
        self.assertEqual(
            loaded["evidence_qualification"],
            "PUBLIC_MARKET_DETERMINISTIC_SIMULATION_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER",
        )
        self.assertEqual(loaded["public_profile"], self.contract["public_profile"])
        self.assertNotIn("last", loaded["normalized"]["quotes"]["spot"])
        self.assertNotIn("last", loaded["normalized"]["quotes"]["perpetual"])
        self.assertEqual(loaded["authority"], {
            "public_network_requests": 10,
            "account_requests": 0,
            "broker_requests": 0,
            "orders_submitted_to_venue": 0,
            "credentials_used": False,
            "production_state_writes": 0,
        })

    def test_rehashed_capture_profile_rule_decimal_funding_and_authority_changes_fail(self):
        cases = (
            (("capture", "capture_hash"), "0" * 64),
            (("public_profile", "protective_stop_status"), "CONFIRMED_FIXTURE"),
            (("rule_response_hashes", "spot_exchange_info"), "0" * 64),
            (("normalized", "quotes", "spot", "bid"), "3309.90"),
            (("normalized", "funding_records", 0, "rate"), "0"),
            (("authority", "account_requests"), 1),
        )
        for path, value in cases:
            document = self._build()
            target = document
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            document["input_hash"] = artifact_self_hash(document, "input_hash")
            with self.subTest(path=path), self.assertRaises(
                ChallengerReplacementPublicSimulationError
            ):
                self._load(document)

    def test_input_accepts_embedded_valid_capture_larger_than_256_kib(self):
        capture_document = _outer_document()
        for index in range(5):
            payload = _request_payload(capture_document, index)
            payload["irrelevant_padding"] = "x" * (60 * 1024)
            _replace_request_payload(capture_document, index, payload)
        capture = load_challenger_replacement_public_market_capture_bytes(
            _canonical_capture(capture_document),
            plan=self.plan,
            build_identity=V076_BUILD,
            previous_source_bundle=None,
        )
        document = build_challenger_replacement_public_simulation_input(
            capture,
            plan=self.plan,
            economic_plan=self.economic_plan,
            predecessor_contract=self.predecessor,
            public_contract=self.contract,
            build_identity=V076_BUILD,
        )
        body = canonical_json(document).encode("utf-8")

        self.assertGreater(len(body), 256 * 1024)
        self.assertEqual(
            load_challenger_replacement_public_simulation_input_bytes(
                body,
                plan=self.plan,
                economic_plan=self.economic_plan,
                predecessor_contract=self.predecessor,
                public_contract=self.contract,
                build_identity=V076_BUILD,
                opportunity_id="ETHUSDT@2026-08-26T04:00:00.000Z",
            ),
            document,
        )


class PublicSimulationSnapshotSchemaTests(unittest.TestCase):
    def test_exposed_snapshot_accepts_only_confirmed_simulated_protection(self):
        schema = json.loads(resources.files("crypto_quant").joinpath(
            "schemas", "challenger-replacement-public-simulation-snapshot-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        snapshot = {
            "snapshot_version": "1.0.0", "snapshot_hash": "1" * 64,
            "parent_snapshot_hash_or_null": "2" * 64,
            "opportunity_id_or_null": "ETHUSDT@2026-08-26T04:00:00.000Z",
            "position_state": "PERP_SHORT", "position_certainty": "VERIFIED",
            "cash": "100", "signed_quantity": "-0.015",
            "entry_price_or_null": "3310", "entry_time": "2026-08-26T04:05:00.000Z",
            "isolated_margin": "25", "contract_multiplier": "1",
            "instrument_metadata_hash_or_null": "3" * 64,
            "realized_pnl": "0", "unrealized_pnl": "0",
            "cumulative_fees": "0.01", "cumulative_funding": "0",
            "marked_equity": "99.99", "peak_equity": "100",
            "day_start_date_or_null": "2026-08-26", "day_start_equity": "100",
            "gross_exposure": "0.5", "risk_state": "RISK_CLEAR",
            "active_order_or_null": None,
            "protective_stop_or_null": {
                "status": "CONFIRMED_SIMULATED", "trigger": "3376.2",
            },
            "reverse_blocked_until_next_opportunity": False,
            "unresolved_intent_ids": [], "economic_gap_locked": False,
        }
        self.assertFalse(tuple(Draft202012Validator(schema).iter_errors(snapshot)))
        changed = deepcopy(snapshot)
        changed["protective_stop_or_null"]["status"] = "CONFIRMED_FIXTURE"
        self.assertTrue(tuple(Draft202012Validator(schema).iter_errors(changed)))


class PublicSimulationTransitionTests(PublicSimulationInputTests):
    def setUp(self):
        super().setUp()
        self.source = self._build()
        self.genesis = build_challenger_replacement_public_genesis_snapshot(
            plan=self.plan, public_contract=self.contract
        )

    def _transition(self, previous=None):
        return simulate_challenger_replacement_public_opportunity(
            source=self.source,
            previous_projection=self.genesis if previous is None else previous,
            plan=self.plan,
            public_contract=self.contract,
            build_identity=V076_BUILD,
        )

    def test_public_genesis_and_spot_open_use_simulated_not_fixture_evidence(self):
        transition = self._transition()

        self.assertEqual(self.genesis["cash"], "100")
        self.assertEqual(transition["decision"]["action"], "OPEN_SPOT_LONG")
        self.assertEqual(transition["next_snapshot"]["position_state"], "SPOT_LONG")
        self.assertEqual(
            transition["next_snapshot"]["protective_stop_or_null"]["status"],
            "CONFIRMED_SIMULATED",
        )
        self.assertEqual(transition["accounting"]["funding_cashflows"], [])
        self.assertNotIn("FIXTURE", canonical_json(transition))

    def test_public_result_recomputes_and_replays_exact_bytes(self):
        transition = self._transition()
        result = build_challenger_replacement_public_simulation_result(
            source=self.source,
            previous_projection=self.genesis,
            transition=transition,
            plan=self.plan,
            economic_plan=self.economic_plan,
            public_contract=self.contract,
            build_identity=V076_BUILD,
            sequence=1,
            parent_event_hash="0" * 64,
        )
        body = canonical_json(result).encode("utf-8")
        golden = Path(__file__).parent / "fixtures" / (
            "challenger_replacement_v076/public-simulation-golden.json"
        )
        self.assertEqual(body + b"\n", golden.read_bytes())
        loaded = load_challenger_replacement_public_simulation_result_bytes(
            body,
            source=self.source,
            previous_projection=self.genesis,
            plan=self.plan,
            economic_plan=self.economic_plan,
            public_contract=self.contract,
            build_identity=V076_BUILD,
            sequence=1,
            parent_event_hash="0" * 64,
        )

        self.assertEqual(loaded, result)
        self.assertEqual(
            loaded["evidence_qualification"],
            "PUBLIC_MARKET_DETERMINISTIC_SIMULATION_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER",
        )
        self.assertEqual(
            loaded["lifecycle"]["events"],
            ["SIMULATED_ORDER_ACCEPTED", "SIMULATED_FILL_APPLIED"],
        )
        self.assertEqual(loaded["reconciliation"]["status"], "MATCHED")
        self.assertEqual(loaded["authority"]["orders_submitted_to_venue"], 0)
        self.assertNotIn("_FIXTURE", canonical_json(loaded))

        mutations = (
            (("parent_event_hash",), "1" * 64),
            (("source", "capture_hash"), "1" * 64),
            (("decision", "action"), "HOLD_FLAT"),
            (("next_snapshot", "protective_stop_or_null", "status"), "CONFIRMED_FIXTURE"),
            (("lifecycle", "events", 0), "ORDER_ACCEPTED_FIXTURE"),
            (("lifecycle", "unresolved_unknown"), True),
            (("reconciliation", "status"), "MISMATCH"),
            (("authority", "orders_submitted_to_venue"), 1),
        )
        for path, value in mutations:
            changed = deepcopy(result)
            target = changed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            changed["result_hash"] = artifact_self_hash(changed, "result_hash")
            with self.subTest(path=path), self.assertRaises(
                ChallengerReplacementPublicSimulationError
            ):
                load_challenger_replacement_public_simulation_result_bytes(
                    canonical_json(changed).encode("utf-8"),
                    source=self.source,
                    previous_projection=self.genesis,
                    plan=self.plan,
                    economic_plan=self.economic_plan,
                    public_contract=self.contract,
                    build_identity=V076_BUILD,
                    sequence=1,
                    parent_event_hash="0" * 64,
                )

    def test_ordered_public_funding_uses_each_record_mark_exactly_once(self):
        capture_document = _outer_document()
        funding_payload = [
            {
                "symbol": "ETHUSDT", "fundingTime": 1787706000000,
                "fundingRate": "0.0001", "markPrice": "3300",
                "fundingRateType": "REGULAR",
            },
            {
                "symbol": "ETHUSDT", "fundingTime": 1787713200000,
                "fundingRate": "-0.0002", "markPrice": "3320",
                "fundingRateType": "REGULAR",
            },
        ]
        _replace_request_payload(capture_document, 5, funding_payload)
        capture_document["normalized"]["funding_records"] = [
            {
                "funding_time": "2026-08-26T01:00:00.000Z",
                "rate": "0.0001", "mark": "3300",
            },
            {
                "funding_time": "2026-08-26T03:00:00.000Z",
                "rate": "-0.0002", "mark": "3320",
            },
        ]
        capture = load_challenger_replacement_public_market_capture_bytes(
            _canonical_capture(capture_document),
            plan=self.plan,
            build_identity=V076_BUILD,
            previous_source_bundle=None,
        )
        source = build_challenger_replacement_public_simulation_input(
            capture,
            plan=self.plan,
            economic_plan=self.economic_plan,
            predecessor_contract=self.predecessor,
            public_contract=self.contract,
            build_identity=V076_BUILD,
        )
        perpetual = _kernel_source(
            source, self.plan, self.contract
        )["instruments"]["perpetual"]
        previous = deepcopy(self.genesis)
        previous.update({
            "position_state": "PERP_SHORT", "cash": "100",
            "signed_quantity": "-0.015", "entry_price_or_null": "3310",
            "entry_time": "2026-08-25T20:00:00.000Z",
            "isolated_margin": "49.65", "contract_multiplier": "1",
            "instrument_metadata_hash_or_null": perpetual["metadata_hash"],
            "protective_stop_or_null": {
                "status": "CONFIRMED_SIMULATED", "trigger": "3376.2",
            },
        })
        previous["snapshot_hash"] = artifact_self_hash(previous, "snapshot_hash")

        transition = simulate_challenger_replacement_public_opportunity(
            source=source,
            previous_projection=previous,
            plan=self.plan,
            public_contract=self.contract,
            build_identity=V076_BUILD,
        )

        self.assertEqual(transition["accounting"]["funding_cashflows"], [
            {"amount": "0.00495", "funding_time": "2026-08-26T01:00:00.000Z"},
            {"amount": "-0.00996", "funding_time": "2026-08-26T03:00:00.000Z"},
        ])

    def test_public_protective_stop_triggers_before_strategy_hold(self):
        opened = self._transition()["next_snapshot"]
        opened["protective_stop_or_null"]["trigger"] = "3309.5"
        opened["snapshot_hash"] = artifact_self_hash(opened, "snapshot_hash")

        stopped = self._transition(opened)

        self.assertEqual(stopped["decision"]["action"], "STOP_CLOSE_SPOT_LONG")
        self.assertEqual(stopped["decision"]["reason_code"], "PROTECTIVE_STOP_TRIGGERED")
        self.assertEqual(stopped["next_snapshot"]["position_state"], "FLAT")
        self.assertIsNotNone(stopped["triggered_stop_or_null"])


if __name__ == "__main__":
    unittest.main()
