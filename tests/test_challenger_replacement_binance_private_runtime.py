import base64
from datetime import datetime, timedelta, timezone
import hashlib
from importlib import resources
import json
import unittest
from unittest.mock import patch

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_binance_private_contract import (
    BinancePrivateActivation,
)
from crypto_quant.challenger_replacement_binance_private_runtime import (
    BinancePrivateRuntimeError,
    run_challenger_replacement_binance_private_intent,
)
from crypto_quant.challenger_replacement_binance_private_transport import (
    BinancePrivateTransportResult,
)
from crypto_quant.challenger_replacement_events import (
    open_challenger_replacement_event_root,
)
from tests.test_challenger_replacement_events import EventWorkspace
from tests.test_challenger_replacement_opportunities import (
    OpportunityStateWorkspace,
)
from tests.challenger_replacement_v3_fixtures import DEFAULT_OBSERVED_AT


class BinancePrivateRuntimeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.workspace = OpportunityStateWorkspace()
        self.addCleanup(self.workspace.close)
        self.state = self.workspace.state()

    def test_different_empty_event_root_is_rejected_before_transport(self):
        other = EventWorkspace()
        self.addCleanup(other.close)
        with open_challenger_replacement_event_root(other.identity()) as root, \
                patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "execute_binance_private_request"
                ) as transport:
            with self.assertRaises(BinancePrivateRuntimeError) as caught:
                run_challenger_replacement_binance_private_intent(
                    state=self.state,
                    event_root=root,
                    intent={},
                    preflight={},
                    activation=object(),
                    credential=object(),
                    build_identity=self.workspace.build,
                )
        self.assertEqual(
            caught.exception.reason_code,
            "BINANCE_PRIVATE_RUNTIME_IDENTITY_INVALID",
        )
        transport.assert_not_called()


class BinancePrivateRuntimeQueryFirstTests(unittest.TestCase):
    NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.workspace = OpportunityStateWorkspace()
        self.addCleanup(self.workspace.close)
        self.state = self.workspace.state()
        self._observe_opportunity()
        self.block_id = "e0-block-" + "2" * 64
        self.intent = {
            "opportunity_id": self.workspace.opportunity_id,
            "intent_id": "intent-" + "1" * 64,
            "block_id": self.block_id,
            "product": "SPOT",
            "action": "OPEN_LONG",
            "quantity": "0.001",
            "attempt_ordinal": 1,
            "unsigned_intent_sha256": "8" * 64,
        }
        self.preflight = {
            "status": "BINANCE_ACCOUNT_PREFLIGHT_VERIFIED_FLAT",
            "preflight_id": "binance_account_preflight_" + "4" * 64,
            "configuration": {
                "position_mode": "ONE_WAY",
                "asset_mode": "SINGLE_ASSET",
                "symbol": "ETHUSDT",
                "margin_type": "ISOLATED",
                "leverage": 1,
                "auto_add_margin": False,
            },
        }
        self.activation = BinancePrivateActivation(
            activation_id="binance_private_activation_" + "5" * 64,
            build_identity=self.workspace.build,
            configuration_sha256="6" * 64,
            account_approval_sha256="7" * 64,
            block_id=self.block_id,
            stage="E0",
            capital_usdt="100",
            max_gross_exposure_usdt="50",
            max_leverage="0.5",
            expires_at="2026-08-28T00:00:00.000Z",
            production_activation=True,
        )

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

    @staticmethod
    def _result(response_class, body):
        return BinancePrivateTransportResult(
            response_class=response_class,
            status_or_null=None if response_class == "UNKNOWN" else 400,
            body=body,
            response_sha256=hashlib.sha256(body).hexdigest(),
            rate_limit_headers=(),
        )

    @staticmethod
    def _spot_account(eth="0", usdt="100"):
        document = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "account-preflight-flat.json",
        ).read_text(encoding="utf-8"))["SPOT_ACCOUNT"]
        balances = {item["asset"]: item for item in document["balances"]}
        balances["ETH"]["free"] = eth
        balances["USDT"]["free"] = usdt
        return canonical_json(document).encode("utf-8")

    def test_query_proven_absent_then_single_unknown_send_blocks_new_risk(self):
        absent = canonical_json({
            "code": -2013,
            "msg": "Order does not exist.",
        }).encode("utf-8")
        unknown = canonical_json({
            "code": -1007,
            "msg": "Timeout waiting for response.",
        }).encode("utf-8")
        responses = (
            self._result("RESPONSE_INVALID", absent),
            self._result("UNKNOWN", unknown),
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now",
            return_value=self.NOW,
            create=True,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            side_effect=responses,
        ) as transport:
            result = run_challenger_replacement_binance_private_intent(
                state=self.state,
                event_root=self.workspace.root,
                intent=self.intent,
                preflight=self.preflight,
                activation=self.activation,
                credential=object(),
                build_identity=self.workspace.build,
            )
        endpoints = [
            call.args[0].endpoint_id for call in transport.call_args_list
        ]
        self.assertEqual(endpoints, ["SPOT_ORDER_QUERY", "SPOT_ORDER_CREATE"])
        replay = self.state.replay()
        private = replay["opportunities"][self.workspace.opportunity_id]["private"]
        self.assertEqual(result, {
            "status": "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN",
            "opportunity_id": self.workspace.opportunity_id,
            "intent_id": self.intent["intent_id"],
            "venue_client_order_id": private["venue_client_order_id"],
        })
        self.assertEqual(private["stage"], "BINANCE_ORDER_UNKNOWN")
        self.assertTrue(private["terminal"])
        self.assertTrue(private["unresolved_unknown"])

    def test_acknowledged_create_is_requeried_before_event_observation(self):
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode("utf-8")
        client_id = "cq7773f849fd1e2d457895f97675d4f7b776"
        order = canonical_json({
            "symbol": "ETHUSDT", "orderId": 101,
            "clientOrderId": client_id, "price": "0",
            "origQty": "0.001", "executedQty": "0",
            "cummulativeQuoteQty": "0", "status": "NEW",
            "timeInForce": "GTC", "type": "MARKET", "side": "BUY",
            "transactTime": 1787832000000,
        }).encode("utf-8")
        account = self._spot_account()
        responses = (
            self._result("RESPONSE_INVALID", absent),
            BinancePrivateTransportResult(
                "ACKNOWLEDGED", 200, order, hashlib.sha256(order).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, order,
                hashlib.sha256(order).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, b"[]",
                hashlib.sha256(b"[]").hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, account,
                hashlib.sha256(account).hexdigest(), (),
            ),
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=responses,
        ) as transport:
            result = run_challenger_replacement_binance_private_intent(
                state=self.state, event_root=self.workspace.root,
                intent=self.intent, preflight=self.preflight,
                activation=self.activation, credential=object(),
                build_identity=self.workspace.build,
            )
        self.assertEqual(
            [call.args[0].endpoint_id for call in transport.call_args_list],
            ["SPOT_ORDER_QUERY", "SPOT_ORDER_CREATE", "SPOT_ORDER_QUERY",
             "SPOT_TRADES", "SPOT_ACCOUNT"],
        )
        self.assertEqual(result["status"], "ORDER_IN_PROGRESS")
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_ORDER_ACKNOWLEDGED")

        filled = canonical_json({
            **json.loads(order), "executedQty": "0.001",
            "cummulativeQuoteQty": "2", "status": "FILLED",
        }).encode("utf-8")
        trade = canonical_json([{
            "symbol": "ETHUSDT", "id": 301, "orderId": 101,
            "qty": "0.001", "price": "2000", "quoteQty": "2",
            "commission": "0.002", "commissionAsset": "USDT",
            "time": 1787832000001, "isBuyer": True,
        }]).encode("utf-8")
        account = self._spot_account("0.001", "97.998")
        followup = tuple(
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, body,
                hashlib.sha256(body).hexdigest(), (),
            )
            for body in (filled, trade, account)
        )
        fresh = self.workspace.state()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW + timedelta(seconds=1),
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=followup,
        ) as transport:
            result = run_challenger_replacement_binance_private_intent(
                state=fresh, event_root=self.workspace.root,
                intent=self.intent, preflight=self.preflight,
                activation=self.activation, credential=object(),
                build_identity=self.workspace.build,
            )
        self.assertEqual(
            [call.args[0].endpoint_id for call in transport.call_args_list],
            ["SPOT_ORDER_QUERY", "SPOT_TRADES", "SPOT_ACCOUNT"],
        )
        self.assertEqual(result["status"],
                         "ORDER_TERMINAL_REQUIRES_RECONCILIATION")
        private = fresh.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_ORDER_FILLED")
        self.assertEqual(private["fill_ids"], [301])

    def test_fresh_retry_after_send_started_queries_id_without_resend(self):
        absent = canonical_json({
            "code": -2013,
            "msg": "Order does not exist.",
        }).encode("utf-8")
        absent_result = self._result("RESPONSE_INVALID", absent)

        class SimulatedCrash(BaseException):
            pass

        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now",
            return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            side_effect=(absent_result, SimulatedCrash()),
        ):
            with self.assertRaises(SimulatedCrash):
                run_challenger_replacement_binance_private_intent(
                    state=self.state,
                    event_root=self.workspace.root,
                    intent=self.intent,
                    preflight=self.preflight,
                    activation=self.activation,
                    credential=object(),
                    build_identity=self.workspace.build,
                )
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_REQUEST_SEND_STARTED")

        order = canonical_json({
            "symbol": "ETHUSDT",
            "orderId": 101,
            "clientOrderId": private["venue_client_order_id"],
            "price": "0",
            "origQty": "0.001",
            "executedQty": "0",
            "cummulativeQuoteQty": "0",
            "status": "NEW",
            "timeInForce": "GTC",
            "type": "MARKET",
            "side": "BUY",
            "transactTime": 1787832000000,
        }).encode("utf-8")
        found = BinancePrivateTransportResult(
            response_class="QUERY_SUCCEEDED",
            status_or_null=200,
            body=order,
            response_sha256=hashlib.sha256(order).hexdigest(),
            rate_limit_headers=(),
        )
        fresh = self.workspace.state()
        empty_trades = b"[]"
        account = self._spot_account()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now",
            return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            side_effect=(
                found,
                BinancePrivateTransportResult(
                    "QUERY_SUCCEEDED", 200, empty_trades,
                    hashlib.sha256(empty_trades).hexdigest(), (),
                ),
                BinancePrivateTransportResult(
                    "QUERY_SUCCEEDED", 200, account,
                    hashlib.sha256(account).hexdigest(), (),
                ),
            ),
        ) as transport:
            result = run_challenger_replacement_binance_private_intent(
                state=fresh,
                event_root=self.workspace.root,
                intent=self.intent,
                preflight=self.preflight,
                activation=self.activation,
                credential=object(),
                build_identity=self.workspace.build,
            )
        self.assertEqual(
            [call.args[0].endpoint_id for call in transport.call_args_list],
            ["SPOT_ORDER_QUERY", "SPOT_TRADES", "SPOT_ACCOUNT"],
        )
        self.assertEqual(result["status"], "ORDER_IN_PROGRESS")
        self.assertEqual(result["venue_client_order_id"],
                         private["venue_client_order_id"])
        self.assertEqual(
            fresh.replay()["opportunities"][self.workspace.opportunity_id]
            ["private"]["stage"],
            "BINANCE_ORDER_ACKNOWLEDGED",
        )

    def test_fresh_retry_after_prepared_request_reuses_durable_timestamp(self):
        absent = canonical_json({
            "code": -2013,
            "msg": "Order does not exist.",
        }).encode("utf-8")
        absent_result = self._result("RESPONSE_INVALID", absent)

        class SimulatedCrash(BaseException):
            pass

        original_append = self.state.append

        def append_then_crash(**kwargs):
            result = original_append(**kwargs)
            if kwargs["event_type"] == "BINANCE_SIGNED_REQUEST_PREPARED":
                raise SimulatedCrash()
            return result

        with patch.object(self.state, "append", side_effect=append_then_crash), \
                patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "_wall_now",
                    return_value=self.NOW,
                ), patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "execute_binance_private_request",
                    return_value=absent_result,
                ):
            with self.assertRaises(SimulatedCrash):
                run_challenger_replacement_binance_private_intent(
                    state=self.state,
                    event_root=self.workspace.root,
                    intent=self.intent,
                    preflight=self.preflight,
                    activation=self.activation,
                    credential=object(),
                    build_identity=self.workspace.build,
                )
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_SIGNED_REQUEST_PREPARED")
        durable_request_id = private["request_id"]
        durable_timestamp_ms = private["request_timestamp_ms"]
        self.assertEqual(durable_timestamp_ms, 1_787_832_000_000)

        unknown = canonical_json({
            "code": -1007,
            "msg": "Timeout waiting for response.",
        }).encode("utf-8")
        fresh = self.workspace.state()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now",
            return_value=self.NOW + timedelta(seconds=1),
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            return_value=self._result("UNKNOWN", unknown),
        ) as transport:
            result = run_challenger_replacement_binance_private_intent(
                state=fresh,
                event_root=self.workspace.root,
                intent=self.intent,
                preflight=self.preflight,
                activation=self.activation,
                credential=object(),
                build_identity=self.workspace.build,
            )
        sent = transport.call_args.args[0]
        self.assertEqual(sent.endpoint_id, "SPOT_ORDER_CREATE")
        self.assertEqual(sent.request_id, durable_request_id)
        self.assertIn(
            ("timestamp=" + str(durable_timestamp_ms)).encode("ascii"),
            sent.encoded_parameters,
        )
        self.assertEqual(result["status"], "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
