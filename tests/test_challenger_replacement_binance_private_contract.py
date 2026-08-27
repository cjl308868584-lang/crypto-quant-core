import base64
import hashlib
from importlib import resources
import json
from types import SimpleNamespace
import unittest

from jsonschema import Draft202012Validator

from crypto_quant.challenger_replacement_binance_private_contract import (
    BINANCE_PRIVATE_ENDPOINTS,
    BinanceAccountApproval,
    BinancePrivateActivation,
    apply_challenger_replacement_private_event,
    load_binance_account_approval_bytes,
    load_binance_private_activation_bytes,
    require_binance_private_endpoint,
)
from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityError,
)
from tests.challenger_replacement_v3_fixtures import DEFAULT_OBSERVED_AT
from tests.test_challenger_replacement_opportunities import (
    OpportunityStateWorkspace,
)


class BinancePrivateEndpointContractTests(unittest.TestCase):
    def test_endpoint_inventory_is_exact_and_product_specific(self):
        expected = {
            "SPOT_SERVER_TIME": ("api.binance.com", "GET", "/api/v3/time", False),
            "SPOT_EXCHANGE_INFO": ("api.binance.com", "GET", "/api/v3/exchangeInfo", False),
            "FUTURES_SERVER_TIME": ("fapi.binance.com", "GET", "/fapi/v1/time", False),
            "FUTURES_EXCHANGE_INFO": ("fapi.binance.com", "GET", "/fapi/v1/exchangeInfo", False),
            "FUTURES_MARK_PRICE": ("fapi.binance.com", "GET", "/fapi/v1/premiumIndex", False),
            "API_RESTRICTIONS": ("api.binance.com", "GET", "/sapi/v1/account/apiRestrictions", False),
            "API_TRADING_STATUS": ("api.binance.com", "GET", "/sapi/v1/account/apiTradingStatus", False),
            "SPOT_ACCOUNT": ("api.binance.com", "GET", "/api/v3/account", False),
            "SPOT_OPEN_ORDERS": ("api.binance.com", "GET", "/api/v3/openOrders", False),
            "SPOT_ORDER_QUERY": ("api.binance.com", "GET", "/api/v3/order", False),
            "SPOT_TRADES": ("api.binance.com", "GET", "/api/v3/myTrades", False),
            "FUTURES_POSITION_MODE": ("fapi.binance.com", "GET", "/fapi/v1/positionSide/dual", False),
            "FUTURES_MULTI_ASSET_MODE": ("fapi.binance.com", "GET", "/fapi/v1/multiAssetsMargin", False),
            "FUTURES_SYMBOL_CONFIG": ("fapi.binance.com", "GET", "/fapi/v1/symbolConfig", False),
            "FUTURES_ACCOUNT": ("fapi.binance.com", "GET", "/fapi/v3/account", False),
            "FUTURES_POSITION": ("fapi.binance.com", "GET", "/fapi/v3/positionRisk", False),
            "FUTURES_OPEN_ORDERS": ("fapi.binance.com", "GET", "/fapi/v1/openOrders", False),
            "FUTURES_ORDER_QUERY": ("fapi.binance.com", "GET", "/fapi/v1/order", False),
            "FUTURES_TRADES": ("fapi.binance.com", "GET", "/fapi/v1/userTrades", False),
            "FUTURES_INCOME": ("fapi.binance.com", "GET", "/fapi/v1/income", False),
            "FUTURES_ALGO_QUERY": ("fapi.binance.com", "GET", "/fapi/v1/algoOrder", False),
            "FUTURES_OPEN_ALGO_ORDERS": ("fapi.binance.com", "GET", "/fapi/v1/openAlgoOrders", False),
            "SPOT_ORDER_CREATE": ("api.binance.com", "POST", "/api/v3/order", True),
            "SPOT_ORDER_CANCEL": ("api.binance.com", "DELETE", "/api/v3/order", True),
            "FUTURES_ORDER_CREATE": ("fapi.binance.com", "POST", "/fapi/v1/order", True),
            "FUTURES_ORDER_CANCEL": ("fapi.binance.com", "DELETE", "/fapi/v1/order", True),
            "FUTURES_ALGO_CREATE": ("fapi.binance.com", "POST", "/fapi/v1/algoOrder", True),
            "FUTURES_ALGO_CANCEL": ("fapi.binance.com", "DELETE", "/fapi/v1/algoOrder", True),
            "FUTURES_SET_LEVERAGE": ("fapi.binance.com", "POST", "/fapi/v1/leverage", True),
            "FUTURES_SET_MARGIN_TYPE": ("fapi.binance.com", "POST", "/fapi/v1/marginType", True),
        }
        self.assertEqual(dict(BINANCE_PRIVATE_ENDPOINTS), expected)
        for endpoint_id, value in expected.items():
            with self.subTest(endpoint_id=endpoint_id):
                self.assertEqual(require_binance_private_endpoint(endpoint_id), value)

    def test_withdrawal_endpoint_is_rejected_before_request_construction(self):
        with self.assertRaisesRegex(ValueError, "BINANCE_ENDPOINT_FORBIDDEN"):
            require_binance_private_endpoint("WITHDRAW")

    def test_request_and_initial_private_event_schemas_are_exact(self):
        request = {
            "$schema": "./challenger-replacement-binance-private-request-v1.schema.json",
            "schema_version": "1.0.0",
            "request_id": "binance_private_request_" + "a" * 64,
            "endpoint_id": "SPOT_ORDER_QUERY",
            "timestamp_ms": 1787788800000,
            "parameters": {
                "origClientOrderId": "cq77" + "b" * 32,
                "symbol": "ETHUSDT",
            },
        }
        event = {
            "$schema": "./challenger-replacement-binance-private-event-v1.schema.json",
            "schema_version": "1.0.0",
            "event_type": "BINANCE_INTENT_AUTHORIZED",
            "opportunity_id": "ETHUSDT@2026-08-24T00:00:00.000Z",
            "payload": {
                "opportunity_id": "ETHUSDT@2026-08-24T00:00:00.000Z",
                "intent_id": "intent-" + "1" * 64,
                "block_id": "e0-block-" + "2" * 64,
                "product": "SPOT",
                "action": "OPEN_LONG",
                "quantity": "0.001",
                "venue_client_order_id": "cq77" + "3" * 32,
                "activation_id": "activation-" + "4" * 64,
                "preflight_sha256": "5" * 64,
                "unsigned_intent_sha256": "6" * 64,
            },
        }
        for filename, document in (
            ("challenger-replacement-binance-private-request-v1.schema.json", request),
            ("challenger-replacement-binance-private-event-v1.schema.json", event),
        ):
            with self.subTest(filename=filename):
                schema = json.loads(
                    resources.files("crypto_quant").joinpath(
                        "schemas", filename
                    ).read_text(encoding="utf-8")
                )
                Draft202012Validator.check_schema(schema)
                validator = Draft202012Validator(schema)
                self.assertEqual(tuple(validator.iter_errors(document)), ())
                altered = dict(document)
                altered["unreviewed"] = True
                self.assertTrue(tuple(validator.iter_errors(altered)))
                if filename.endswith("private-event-v1.schema.json"):
                    zero = dict(document)
                    zero["payload"] = dict(document["payload"])
                    zero["payload"]["quantity"] = "0"
                    self.assertTrue(tuple(validator.iter_errors(zero)))


class BinancePrivateAuthorityContractTests(unittest.TestCase):
    BUILD = {
        "release_tag": "v0.76.0-fixture",
        "peeled_commit": "7" * 40,
        "package_version": "0.76.0",
        "manifest_version": "1.70.0",
        "build_input_tree_hash": "1" * 64,
        "manifest_hash": "2" * 64,
        "manifest_file_sha256": "3" * 64,
    }

    def _activation(self):
        return {
            "$schema": "./challenger-replacement-binance-private-activation-v1.schema.json",
            "schema_version": "1.0.0",
            "activation_id": "binance_private_activation_" + "4" * 64,
            "build_identity": self.BUILD,
            "configuration_sha256": "5" * 64,
            "account_approval_sha256": "6" * 64,
            "block_id": "e0_block_" + "7" * 64,
            "stage": "E0",
            "capital_usdt": "100",
            "max_gross_exposure_usdt": "50",
            "max_leverage": "0.5",
            "expires_at": "2026-08-28T00:00:00.000Z",
            "production_activation": True,
        }

    def _account_approval(self):
        return {
            "$schema": "./challenger-replacement-binance-account-approval-v1.schema.json",
            "schema_version": "1.0.0",
            "account_identity_sha256": "8" * 64,
            "key_fingerprint": "9" * 64,
            "reviewed_egress_ip": "203.0.113.10",
            "reviewer_uid": 501,
            "reviewed_at": "2026-08-27T10:00:00.000Z",
            "expires_at": "2026-08-28T00:00:00.000Z",
            "spot_trading_approved": True,
            "futures_trading_approved": True,
        }

    def test_account_approval_binds_human_review_without_claiming_machine_proof(self):
        loaded = load_binance_account_approval_bytes(
            (canonical_json(self._account_approval()) + "\n").encode("utf-8"),
            now="2026-08-27T12:00:00.000Z",
        )
        self.assertIsInstance(loaded, BinanceAccountApproval)
        self.assertEqual(
            (loaded.reviewed_egress_ip, loaded.reviewer_uid,
             loaded.spot_trading_approved, loaded.futures_trading_approved),
            ("203.0.113.10", 501, True, True),
        )

    def test_authority_schemas_are_valid_and_reject_extra_keys(self):
        for filename, document in (
            ("challenger-replacement-binance-account-approval-v1.schema.json",
             self._account_approval()),
            ("challenger-replacement-binance-private-activation-v1.schema.json",
             self._activation()),
        ):
            with self.subTest(filename=filename):
                schema = json.loads(
                    resources.files("crypto_quant").joinpath(
                        "schemas", filename
                    ).read_text(encoding="utf-8")
                )
                Draft202012Validator.check_schema(schema)
                validator = Draft202012Validator(schema)
                self.assertEqual(tuple(validator.iter_errors(document)), ())
                altered = dict(document)
                altered["unreviewed"] = True
                self.assertTrue(tuple(validator.iter_errors(altered)))

    def test_e0_activation_binds_exact_build_limits_and_expiry(self):
        document = self._activation()
        loaded = load_binance_private_activation_bytes(
            (canonical_json(document) + "\n").encode("utf-8"),
            build_identity=self.BUILD,
            now="2026-08-27T12:00:00.000Z",
        )
        self.assertIsInstance(loaded, BinancePrivateActivation)
        self.assertEqual(
            (loaded.stage, loaded.capital_usdt, loaded.max_gross_exposure_usdt,
             loaded.max_leverage, loaded.production_activation),
            ("E0", "100", "50", "0.5", True),
        )

        document["max_gross_exposure_usdt"] = "51"
        with self.assertRaisesRegex(ValueError, "BINANCE_ACTIVATION_INVALID"):
            load_binance_private_activation_bytes(
                (canonical_json(document) + "\n").encode("utf-8"),
                build_identity=self.BUILD,
                now="2026-08-27T12:00:00.000Z",
            )


class BinancePrivateEventContractTests(unittest.TestCase):
    def setUp(self):
        self.workspace = OpportunityStateWorkspace()
        self.state = self.workspace.state()
        schema = json.loads(resources.files("crypto_quant").joinpath(
            "schemas", "challenger-replacement-binance-private-event-v1.schema.json"
        ).read_text(encoding="utf-8"))
        self.private_validator = Draft202012Validator(schema)

    def tearDown(self):
        self.workspace.close()

    def _intent_payload(self):
        return {
            "opportunity_id": self.workspace.opportunity_id,
            "intent_id": "intent-" + "1" * 64,
            "block_id": "e0-block-" + "2" * 64,
            "product": "SPOT",
            "action": "OPEN_LONG",
            "quantity": "0.001",
            "venue_client_order_id": "cq77" + "3" * 32,
            "activation_id": "activation-" + "4" * 64,
            "preflight_sha256": "5" * 64,
            "unsigned_intent_sha256": "6" * 64,
        }

    def _observe_opportunity(self):
        projection = self.state.replay()
        input_event = self.state.append(
            event_type="INPUT_PREPARED",
            opportunity_id=self.workspace.opportunity_id,
            worker_id="fixture-private-worker",
            recorded_at=DEFAULT_OBSERVED_AT,
            payload=self.workspace.input_payload(),
            expected_last_event_hash=projection["last_event_hash"],
        )
        projection = self.state.replay()
        result_event = self.state.append(
            event_type="RESULT_PREPARED",
            opportunity_id=self.workspace.opportunity_id,
            worker_id="fixture-private-worker",
            recorded_at=DEFAULT_OBSERVED_AT,
            payload={
                "opportunity_id": self.workspace.opportunity_id,
                "scheduled_for": "2026-08-24T00:00:00.000Z",
                "input_event_hash": input_event.event_hash,
                "input_event_sequence": input_event.sequence,
                "source_bundle_sha256": self.workspace.source_hash,
                "decision_bytes_base64": base64.b64encode(
                    self.workspace.decision_bytes
                ).decode("ascii"),
                "decision_sha256": self.workspace.decision_hash,
                "result_evidence_bytes_base64": base64.b64encode(
                    self.workspace.evidence_bytes
                ).decode("ascii"),
                "result_evidence_sha256": self.workspace.evidence_hash,
                "previous_observed_decision_hash_or_null": None,
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
        projection = self.state.replay()
        self.state.append(
            event_type="OPPORTUNITY_OBSERVED",
            opportunity_id=self.workspace.opportunity_id,
            worker_id="fixture-private-worker",
            recorded_at=DEFAULT_OBSERVED_AT,
            payload={
                "opportunity_id": self.workspace.opportunity_id,
                "scheduled_for": "2026-08-24T00:00:00.000Z",
                "input_event_hash": input_event.event_hash,
                "input_event_sequence": input_event.sequence,
                "result_event_hash": result_event.event_hash,
                "result_event_sequence": result_event.sequence,
                "source_bundle_sha256": self.workspace.source_hash,
                "decision_sha256": self.workspace.decision_hash,
                "result_evidence_sha256": self.workspace.evidence_hash,
                "observed_at": DEFAULT_OBSERVED_AT,
            },
            expected_last_event_hash=projection["last_event_hash"],
        )

    def _append_private(self, event_type, payload):
        envelope = {
            "$schema": "./challenger-replacement-binance-private-event-v1.schema.json",
            "schema_version": "1.0.0", "event_type": event_type,
            "opportunity_id": self.workspace.opportunity_id,
            "payload": payload,
        }
        self.assertEqual(tuple(self.private_validator.iter_errors(envelope)), ())
        projection = self.state.replay()
        return self.state.append(
            event_type=event_type,
            opportunity_id=self.workspace.opportunity_id,
            worker_id="fixture-private-worker",
            recorded_at=DEFAULT_OBSERVED_AT,
            payload=payload,
            expected_last_event_hash=projection["last_event_hash"],
        )

    @staticmethod
    def _reconciliation_bytes():
        facts = {
            "product": "SPOT", "signed_quantity": "0.001",
            "average_entry_price_or_null": "2000", "realized_pnl": "0",
            "unrealized_pnl": "0", "cumulative_fee": "0.002",
            "funding": "0", "wallet_balance": "99.998",
            "available_balance": "97.998", "open_order_count": 0,
            "protective_stop_client_id_or_null": None, "fill_ids": [301],
        }
        document = {
            "$schema": "./challenger-replacement-binance-reconciliation-v1.schema.json",
            "schema_version": "1.0.0",
            "status": "BINANCE_PRIVATE_RECONCILIATION_MATCHED",
            "event_projection": facts, "venue_projection": facts,
            "ledger_projection": facts,
            "authority": {"network_requests": 0, "orders": 0,
                          "state_writes": 0},
        }
        document["reconciliation_id"] = (
            "binance_reconciliation_" + hashlib.sha256(
                canonical_json(document).encode("utf-8")
            ).hexdigest()
        )
        return (canonical_json(document) + "\n").encode("utf-8")

    def _authorize(self):
        self._observe_opportunity()
        self._append_private("BINANCE_INTENT_AUTHORIZED", self._intent_payload())

    def _pre_send(self):
        self._authorize()
        intent = self._intent_payload()
        self._append_private("BINANCE_ABSENCE_CHECKED", {
            "intent_id": intent["intent_id"],
            "venue_client_order_id": intent["venue_client_order_id"],
            "query_response_sha256": "7" * 64,
            "proven_absent": True,
        })
        self._append_private("BINANCE_SIGNED_REQUEST_PREPARED", {
            "intent_id": intent["intent_id"],
            "request_id": "binance_private_request_" + "8" * 64,
            "endpoint_id": "SPOT_ORDER_CREATE",
            "request_sha256": "9" * 64,
            "timestamp_ms": 1787832000000,
        })
        self._append_private("BINANCE_REQUEST_SEND_STARTED", {
            "intent_id": intent["intent_id"],
            "request_id": "binance_private_request_" + "8" * 64,
        })

    def test_observed_opportunity_accepts_one_exact_private_intent(self):
        self._observe_opportunity()
        projection = self.state.replay()
        publication = self.state.append(
            event_type="BINANCE_INTENT_AUTHORIZED",
            opportunity_id=self.workspace.opportunity_id,
            worker_id="fixture-private-worker",
            recorded_at=DEFAULT_OBSERVED_AT,
            payload=self._intent_payload(),
            expected_last_event_hash=projection["last_event_hash"],
        )
        replay = self.state.replay()
        private = replay["opportunities"][self.workspace.opportunity_id]["private"]
        self.assertEqual(publication.outcome, "COMMITTED")
        self.assertEqual(
            (private["stage"], private["intent_id"], private["product"]),
            ("BINANCE_INTENT_AUTHORIZED", "intent-" + "1" * 64, "SPOT"),
        )

    def test_non_positive_intent_quantity_is_rejected_without_event(self):
        self._observe_opportunity()
        before = self.state.replay()
        payload = self._intent_payload()
        payload["quantity"] = "-0.001"
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError,
            "CHALLENGER_REPLACEMENT_BINANCE_PRIVATE_EVENT_INVALID",
        ):
            self.state.append(
                event_type="BINANCE_INTENT_AUTHORIZED",
                opportunity_id=self.workspace.opportunity_id,
                worker_id="fixture-private-worker",
                recorded_at=DEFAULT_OBSERVED_AT,
                payload=payload,
                expected_last_event_hash=before["last_event_hash"],
            )
        after = self.state.replay()
        self.assertEqual(after["last_event_hash"], before["last_event_hash"])
        self.assertEqual(len(after["events"]), len(before["events"]))

    def test_private_intent_before_observation_is_rejected_by_private_contract(self):
        projection = self.state.replay()
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError,
            "CHALLENGER_REPLACEMENT_BINANCE_PRIVATE_EVENT_INVALID",
        ):
            self.state.append(
                event_type="BINANCE_INTENT_AUTHORIZED",
                opportunity_id=self.workspace.opportunity_id,
                worker_id="fixture-private-worker",
                recorded_at=DEFAULT_OBSERVED_AT,
                payload=self._intent_payload(),
                expected_last_event_hash=projection["last_event_hash"],
            )

    def test_exact_private_lifecycle_replays_to_terminal_reconciliation(self):
        self._pre_send()
        intent = self._intent_payload()
        self._append_private("BINANCE_ORDER_ACKNOWLEDGED", {
            "intent_id": intent["intent_id"], "order_id": 101,
            "venue_client_order_id": intent["venue_client_order_id"],
        })
        self._append_private("BINANCE_FILL_OBSERVED", {
            "intent_id": intent["intent_id"], "trade_id": 301,
            "order_id": 101, "quantity": "0.001", "price": "2000",
            "quote_quantity": "2", "fee": "0.002", "fee_asset": "USDT",
            "cumulative_filled_quantity": "0.001",
        })
        self._append_private("BINANCE_ORDER_FILLED", {
            "intent_id": intent["intent_id"],
            "cumulative_filled_quantity": "0.001",
            "cumulative_fee": "0.002", "venue_terminal_status": "FILLED",
        })
        self._append_private("BINANCE_FILLS_FEES_REPLAYED", {
            "intent_id": intent["intent_id"], "fill_ids": [301],
            "cumulative_fee": "0.002",
        })
        reconciliation = self._reconciliation_bytes()
        reconciliation_id = json.loads(reconciliation)["reconciliation_id"]
        self._append_private("BINANCE_POSITION_BALANCE_RECONCILED", {
            "intent_id": intent["intent_id"],
            "reconciliation_id": reconciliation_id,
            "reconciliation_bytes_base64": base64.b64encode(
                reconciliation
            ).decode("ascii"),
            "reconciliation_sha256": hashlib.sha256(
                reconciliation
            ).hexdigest(),
        })
        self._append_private("BINANCE_PROTECTION_RECONCILED_IF_EXPOSED", {
            "intent_id": intent["intent_id"], "required": False,
            "client_algo_id_or_null": None, "status": "NOT_REQUIRED",
        })
        self._append_private("BINANCE_RECONCILIATION_SUCCEEDED", {
            "intent_id": intent["intent_id"],
            "reconciliation_id": reconciliation_id,
        })
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_RECONCILIATION_SUCCEEDED")
        self.assertTrue(private["terminal"])
        self.assertFalse(private["unresolved_unknown"])
        self.assertEqual(private["fill_ids"], [301])
        self.assertEqual(private["reconciliation_id"], reconciliation_id)
        self.assertEqual(base64.b64decode(
            private["reconciliation_bytes_base64"]), reconciliation)

    def test_fill_order_id_must_match_durable_acknowledgement(self):
        self._pre_send()
        intent = self._intent_payload()
        self._append_private("BINANCE_ORDER_ACKNOWLEDGED", {
            "intent_id": intent["intent_id"], "order_id": 202,
            "venue_client_order_id": intent["venue_client_order_id"],
        })
        before = self.state.replay()
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError,
            "CHALLENGER_REPLACEMENT_BINANCE_PRIVATE_EVENT_INVALID",
        ):
            self._append_private("BINANCE_FILL_OBSERVED", {
                "intent_id": intent["intent_id"], "trade_id": 301,
                "order_id": 999, "quantity": "0.001", "price": "2000",
                "quote_quantity": "2", "fee": "0.002",
                "fee_asset": "USDT", "cumulative_filled_quantity": "0.001",
            })
        after = self.state.replay()
        self.assertEqual(after["last_event_hash"], before["last_event_hash"])

    def test_out_of_order_private_event_is_rejected_without_append(self):
        self._authorize()
        before = self.state.replay()
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError,
            "CHALLENGER_REPLACEMENT_BINANCE_PRIVATE_EVENT_INVALID",
        ):
            self._append_private("BINANCE_REQUEST_SEND_STARTED", {
                "intent_id": self._intent_payload()["intent_id"],
                "request_id": "binance_private_request_" + "8" * 64,
            })
        after = self.state.replay()
        self.assertEqual(after["last_event_hash"], before["last_event_hash"])

    def test_unknown_requires_bound_query_before_normal_transition(self):
        self._pre_send()
        intent = self._intent_payload()
        self._append_private("BINANCE_ORDER_UNKNOWN", {
            "intent_id": intent["intent_id"], "venue_code": -1007,
            "blocks_new_risk": True,
        })
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertFalse(private["terminal"])
        self.assertTrue(private["unresolved_unknown"])
        with self.assertRaises(ChallengerReplacementOpportunityError):
            self._append_private("BINANCE_ORDER_ACKNOWLEDGED", {
                "intent_id": intent["intent_id"], "order_id": 101,
                "venue_client_order_id": intent["venue_client_order_id"],
            })
        self._append_private("BINANCE_UNKNOWN_QUERY_OBSERVED", {
            "intent_id": intent["intent_id"],
            "venue_client_order_id": intent["venue_client_order_id"],
            "order_response_sha256": "1" * 64,
            "trades_response_sha256": "2" * 64,
            "account_response_sha256": "3" * 64,
        })
        self._append_private("BINANCE_ORDER_ACKNOWLEDGED", {
            "intent_id": intent["intent_id"], "order_id": 101,
            "venue_client_order_id": intent["venue_client_order_id"],
        })
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_ORDER_ACKNOWLEDGED")
        self.assertTrue(private["unresolved_unknown"])
        self.assertFalse(private["terminal"])

    def _perpetual_with_verified_stop(self):
        self._observe_opportunity()
        intent = self._intent_payload()
        intent.update(product="PERPETUAL", action="OPEN_SHORT")
        self._append_private("BINANCE_INTENT_AUTHORIZED", intent)
        self._append_private("BINANCE_ABSENCE_CHECKED", {
            "intent_id": intent["intent_id"],
            "venue_client_order_id": intent["venue_client_order_id"],
            "query_response_sha256": "7" * 64, "proven_absent": True,
        })
        self._append_private("BINANCE_SIGNED_REQUEST_PREPARED", {
            "intent_id": intent["intent_id"],
            "request_id": "binance_private_request_" + "8" * 64,
            "endpoint_id": "FUTURES_ORDER_CREATE",
            "request_sha256": "9" * 64, "timestamp_ms": 1787832000000,
        })
        self._append_private("BINANCE_REQUEST_SEND_STARTED", {
            "intent_id": intent["intent_id"],
            "request_id": "binance_private_request_" + "8" * 64,
        })
        self._append_private("BINANCE_ORDER_ACKNOWLEDGED", {
            "intent_id": intent["intent_id"], "order_id": 202,
            "venue_client_order_id": intent["venue_client_order_id"],
        })
        self._append_private("BINANCE_FILL_OBSERVED", {
            "intent_id": intent["intent_id"], "trade_id": 401,
            "order_id": 202, "quantity": "0.025", "price": "2000",
            "quote_quantity": "50", "fee": "0.02", "fee_asset": "USDT",
            "cumulative_filled_quantity": "0.025", "realized_pnl": "0",
        })
        self._append_private("BINANCE_ORDER_FILLED", {
            "intent_id": intent["intent_id"],
            "cumulative_filled_quantity": "0.025",
            "cumulative_fee": "0.02", "venue_terminal_status": "FILLED",
        })
        self._append_private("BINANCE_FILLS_FEES_REPLAYED", {
            "intent_id": intent["intent_id"], "fill_ids": [401],
            "cumulative_fee": "0.02",
        })
        client = "cq77" + "a" * 32
        self._append_private("BINANCE_STOP_INTENT_AUTHORIZED", {
            "protected_intent_id": intent["intent_id"], "symbol": "ETHUSDT",
            "algo_type": "CONDITIONAL", "order_type": "STOP_MARKET",
            "side": "BUY", "position_side": "BOTH",
            "working_type": "MARK_PRICE", "quantity": "0.025",
            "trigger_price": "2036.43", "reduce_only": True,
            "close_position": False, "client_algo_id": client,
            "required_first_endpoint": "FUTURES_ALGO_QUERY",
            "send_permitted": False,
        })
        stop_request_id = "binance_private_request_" + "c" * 64
        self._append_private("BINANCE_STOP_ABSENCE_CHECKED", {
            "protected_intent_id": intent["intent_id"],
            "client_algo_id": client, "query_response_sha256": "d" * 64,
            "proven_absent": True,
        })
        self._append_private("BINANCE_STOP_SIGNED_REQUEST_PREPARED", {
            "protected_intent_id": intent["intent_id"],
            "client_algo_id": client, "request_id": stop_request_id,
            "request_sha256": "e" * 64, "timestamp_ms": 1787832000000,
        })
        self._append_private("BINANCE_STOP_REQUEST_SEND_STARTED", {
            "protected_intent_id": intent["intent_id"],
            "client_algo_id": client, "request_id": stop_request_id,
        })
        self._append_private("BINANCE_STOP_ACKNOWLEDGED", {
            "protected_intent_id": intent["intent_id"],
            "client_algo_id": client, "algo_id": 901,
        })
        self._append_private("BINANCE_STOP_RECONCILED", {
            "status": "BINANCE_PROTECTIVE_STOP_VERIFIED", "exposed": True,
            "new_risk_blocked": False, "client_algo_id": client,
            "algo_id": 901, "quantity": "0.025",
            "trigger_price": "2036.43",
        })
        return intent, client

    def test_perpetual_stop_events_use_substate_without_advancing_order_stage(self):
        _, client = self._perpetual_with_verified_stop()
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_FILLS_FEES_REPLAYED")
        self.assertEqual(private["stop"]["stage"], "BINANCE_STOP_RECONCILED")
        self.assertEqual(private["stop"]["client_algo_id"], client)

    def test_stop_replacement_starts_only_from_verified_old_stop(self):
        intent, old_client = self._perpetual_with_verified_stop()
        new_client = "cq77" + "b" * 32
        self._append_private("BINANCE_STOP_REPLACEMENT_STARTED", {
            "protected_intent_id": intent["intent_id"],
            "old_client_algo_id": old_client,
            "new_client_algo_id": new_client,
        })
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_FILLS_FEES_REPLAYED")
        self.assertEqual(private["stop"]["stage"], "BINANCE_STOP_RECONCILED")
        self.assertEqual(private["stop"]["client_algo_id"], old_client)
        self.assertEqual(private["stop"]["replacement"], {
            "stage": "BINANCE_STOP_REPLACEMENT_STARTED",
            "old_client_algo_id": old_client,
            "new_client_algo_id": new_client,
        })

    def test_stop_replacement_promotes_only_a_reconciled_new_stop(self):
        intent, old_client = self._perpetual_with_verified_stop()
        new_client = "cq77" + "b" * 32
        self._append_private("BINANCE_STOP_REPLACEMENT_STARTED", {
            "protected_intent_id": intent["intent_id"],
            "old_client_algo_id": old_client,
            "new_client_algo_id": new_client,
        })
        self._append_private("BINANCE_STOP_INTENT_AUTHORIZED", {
            "protected_intent_id": intent["intent_id"], "symbol": "ETHUSDT",
            "algo_type": "CONDITIONAL", "order_type": "STOP_MARKET",
            "side": "BUY", "position_side": "BOTH",
            "working_type": "MARK_PRICE", "quantity": "0.02",
            "trigger_price": "2029", "reduce_only": True,
            "close_position": False, "client_algo_id": new_client,
            "required_first_endpoint": "FUTURES_ALGO_QUERY",
            "send_permitted": False,
        })
        request_id = "binance_private_request_" + "f" * 64
        self._append_private("BINANCE_STOP_ABSENCE_CHECKED", {
            "protected_intent_id": intent["intent_id"],
            "client_algo_id": new_client, "query_response_sha256": "0" * 64,
            "proven_absent": True,
        })
        self._append_private("BINANCE_STOP_SIGNED_REQUEST_PREPARED", {
            "protected_intent_id": intent["intent_id"],
            "client_algo_id": new_client, "request_id": request_id,
            "request_sha256": "1" * 64, "timestamp_ms": 1787832000000,
        })
        self._append_private("BINANCE_STOP_REQUEST_SEND_STARTED", {
            "protected_intent_id": intent["intent_id"],
            "client_algo_id": new_client, "request_id": request_id,
        })
        self._append_private("BINANCE_STOP_ACKNOWLEDGED", {
            "protected_intent_id": intent["intent_id"],
            "client_algo_id": new_client, "algo_id": 902,
        })
        self._append_private("BINANCE_STOP_RECONCILED", {
            "status": "BINANCE_PROTECTIVE_STOP_VERIFIED", "exposed": True,
            "new_risk_blocked": False, "client_algo_id": new_client,
            "algo_id": 902, "quantity": "0.02", "trigger_price": "2029",
        })
        cancel_request_id = "binance_private_request_" + "2" * 64
        self._append_private(
            "BINANCE_STOP_REPLACEMENT_CANCEL_SEND_STARTED", {
                "protected_intent_id": intent["intent_id"],
                "old_client_algo_id": old_client,
                "new_client_algo_id": new_client,
                "request_id": cancel_request_id,
                "request_sha256": "3" * 64,
                "timestamp_ms": 1787832000000,
            },
        )
        self._append_private("BINANCE_STOP_REPLACEMENT_SUCCEEDED", {
            "protected_intent_id": intent["intent_id"],
            "old_client_algo_id": old_client,
            "new_client_algo_id": new_client,
            "reason_code_or_null": None,
        })
        stop = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]["stop"]
        self.assertEqual(stop["client_algo_id"], new_client)
        self.assertEqual(stop["algo_id"], 902)
        self.assertEqual(stop["quantity"], "0.02")
        self.assertEqual(stop["trigger_price"], "2029")
        self.assertEqual(
            stop["replacement"]["stage"],
            "BINANCE_STOP_REPLACEMENT_SUCCEEDED",
        )

    def test_failed_stop_replacement_keeps_verified_old_stop(self):
        intent, old_client = self._perpetual_with_verified_stop()
        new_client = "cq77" + "b" * 32
        self._append_private("BINANCE_STOP_REPLACEMENT_STARTED", {
            "protected_intent_id": intent["intent_id"],
            "old_client_algo_id": old_client,
            "new_client_algo_id": new_client,
        })
        self._append_private("BINANCE_STOP_REPLACEMENT_FAILED", {
            "protected_intent_id": intent["intent_id"],
            "old_client_algo_id": old_client,
            "new_client_algo_id": new_client,
            "reason_code_or_null": "NEW_STOP_NOT_ACKNOWLEDGED",
        })
        stop = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]["stop"]
        self.assertEqual(stop["client_algo_id"], old_client)
        self.assertEqual(stop["stage"], "BINANCE_STOP_RECONCILED")
        self.assertEqual(stop["replacement"], {
            "stage": "BINANCE_STOP_REPLACEMENT_FAILED",
            "old_client_algo_id": old_client,
            "new_client_algo_id": new_client,
            "reason_code": "NEW_STOP_NOT_ACKNOWLEDGED",
        })

    def test_flat_close_stop_cleanup_has_one_query_first_durable_chain(self):
        opportunity_id = self.workspace.opportunity_id
        intent_id = "close-intent-" + "1" * 64
        client = "cq77" + "a" * 32
        projection = {"opportunities": {opportunity_id: {
            "outcome": "OBSERVED", "stage": "OPPORTUNITY_OBSERVED",
            "private": {
                "stage": "BINANCE_FILLS_FEES_REPLAYED", "terminal": False,
                "intent_id": intent_id, "product": "PERPETUAL",
                "action": "CLOSE_SHORT", "fill_ids": [402],
            },
        }}}
        events = (
            ("BINANCE_STOP_CLEANUP_AUTHORIZED", {
                "intent_id": intent_id, "client_algo_id": client,
                "prior_reconciliation_id": "binance_reconciliation_" + "b" * 64,
            }),
            ("BINANCE_STOP_CLEANUP_REQUEST_PREPARED", {
                "intent_id": intent_id, "client_algo_id": client,
                "request_id": "binance_private_request_" + "d" * 64,
                "request_sha256": "e" * 64, "timestamp_ms": 1787832000000,
                "query_response_sha256": "c" * 64, "algo_id": 901,
            }),
            ("BINANCE_STOP_CLEANUP_SEND_STARTED", {
                "intent_id": intent_id, "client_algo_id": client,
                "request_id": "binance_private_request_" + "d" * 64,
            }),
            ("BINANCE_STOP_CLEANUP_RECONCILED", {
                "intent_id": intent_id, "client_algo_id": client,
                "query_response_sha256": "f" * 64,
                "status": "BINANCE_FLAT_STOP_CLEANED",
            }),
        )
        for sequence, (event_type, payload) in enumerate(events, 10):
            header = {
                "event_type": event_type, "slot_id": opportunity_id,
                "payload_bytes_base64": base64.b64encode(
                    canonical_json(payload).encode()
                ).decode(),
            }
            apply_challenger_replacement_private_event(
                projection,
                SimpleNamespace(
                    final_bytes=canonical_json(header).encode(),
                    event_hash=format(sequence, "064x"), sequence=sequence,
                ),
            )
        cleanup = projection["opportunities"][opportunity_id]["private"][
            "stop_cleanup"
        ]
        self.assertEqual(cleanup, {
            "stage": "BINANCE_STOP_CLEANUP_RECONCILED",
            "client_algo_id": client,
            "prior_reconciliation_id": "binance_reconciliation_" + "b" * 64,
            "query_response_sha256": "f" * 64, "algo_id": 901,
            "request_id": "binance_private_request_" + "d" * 64,
            "request_sha256": "e" * 64,
            "request_timestamp_ms": 1787832000000,
            "status": "BINANCE_FLAT_STOP_CLEANED",
        })


if __name__ == "__main__":
    unittest.main()
