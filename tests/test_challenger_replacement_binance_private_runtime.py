import base64
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import crypto_quant.challenger_replacement_binance_private_runtime as private_runtime
from crypto_quant.canonical import canonical_decimal, canonical_json
from crypto_quant.challenger_replacement_binance_private_contract import (
    BinanceAccountApproval, BinancePrivateActivation,
)
from crypto_quant.challenger_replacement_binance_credential import (
    BinanceCredentialIdentity,
)
from crypto_quant.challenger_replacement_binance_preflight import (
    evaluate_binance_account_preflight,
    open_binance_account_preflight_capability,
)
from crypto_quant.challenger_replacement_binance_private_lifecycle import (
    build_binance_order_intent_from_opportunity,
    derive_binance_client_order_id, prepare_binance_protective_stop,
)
from crypto_quant.challenger_replacement_binance_private_runtime import (
    BinancePrivateRuntimeError,
    _cleanup_perpetual_stop,
    _emergency_flatten,
    _observe_order,
    _perpetual_facts,
    _previous_reconciliation_bytes,
    _spot_facts,
    run_challenger_replacement_binance_private_intent,
)
from crypto_quant.challenger_replacement_binance_private_transport import (
    BinancePrivateTransportResult,
)
from crypto_quant.challenger_replacement_binance_reconciliation import (
    load_binance_reconciliation_bytes,
    reconcile_binance_private_state,
)
from crypto_quant.challenger_replacement_public_http import PublicHttpResponse
from crypto_quant.challenger_replacement_events import (
    open_challenger_replacement_event_root,
)
from crypto_quant.challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from crypto_quant.challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityState,
)
from crypto_quant.challenger_replacement_public_market_capture import (
    load_challenger_replacement_public_market_capture_bytes,
)
from crypto_quant.challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from crypto_quant.challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from crypto_quant.challenger_replacement_v3_runtime import (
    run_challenger_replacement_v3_opportunity,
)
from tests.test_challenger_replacement_events import EventWorkspace
from tests.test_challenger_replacement_opportunities import (
    OpportunityStateWorkspace,
)
from tests.challenger_replacement_v3_fixtures import (
    DEFAULT_OBSERVED_AT, fixture_v3_plan,
)
from tests.challenger_replacement_v077_private_fixtures import (
    loaded_private_activation, observe_fixture_opportunity,
)
from tests.test_challenger_replacement_public_market_capture import (
    COMMITTED_CAPTURE, V076_BUILD, _canonical_capture, _outer_document,
)
from tests.test_challenger_replacement_binance_reconciliation import (
    fixture_capture_publications,
)


class PrivateRuntimeWorkspace:
    def __init__(self, *, latest="3310"):
        self.files = EventWorkspace()
        self.root = open_challenger_replacement_event_root(self.files.identity())
        self.plan = fixture_v3_plan()
        self.build = V076_BUILD
        self.latest = latest
        self.opportunity_id = "ETHUSDT@2026-08-26T04:00:00.000Z"

    def close(self):
        self.root.close()
        self.files.close()

    def state(self):
        return ChallengerReplacementOpportunityState(
            event_root=self.root, plan=self.plan, build_identity=self.build,
        )

    def observe(self, state):
        economic = build_challenger_replacement_economic_plan()
        predecessor = build_challenger_replacement_simulation_contract(
            plan=self.plan
        )
        public_contract = build_challenger_replacement_public_simulation_contract(
            plan=self.plan, economic_plan=economic,
            predecessor_contract=predecessor,
        )
        capture_bytes = (COMMITTED_CAPTURE.read_bytes() if self.latest == "3310"
                         else _canonical_capture(_outer_document(latest=self.latest)))
        capture = load_challenger_replacement_public_market_capture_bytes(
            capture_bytes, plan=self.plan,
            build_identity=self.build, previous_source_bundle=None,
        )
        with patch(
            "crypto_quant.challenger_replacement_v3_runtime._acquire",
            return_value=capture,
        ), patch(
            "crypto_quant.challenger_replacement_v3_runtime._wall_now",
            return_value=datetime(2026, 8, 26, 4, 5, tzinfo=timezone.utc),
        ):
            run_challenger_replacement_v3_opportunity(
                state=state, event_root=self.root, plan=self.plan,
                economic_plan=economic, predecessor_contract=predecessor,
                public_contract=public_contract, build_identity=self.build,
            )


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
                    preflight_capability={},
                    activation=object(),
                    credential=object(),
                    build_identity=self.workspace.build,
                )
        self.assertEqual(
            caught.exception.reason_code,
            "BINANCE_PRIVATE_RUNTIME_IDENTITY_INVALID",
        )
        transport.assert_not_called()


class BinancePrivateRuntimeDecisionBindingTests(unittest.TestCase):
    def test_nonstandard_evidence_schema_cannot_bypass_intent_reconstruction(self):
        workspace = OpportunityStateWorkspace()
        self.addCleanup(workspace.close)
        state = workspace.state()
        observe_fixture_opportunity(
            state=state, workspace=workspace, recorded_at=DEFAULT_OBSERVED_AT,
        )
        activation = loaded_private_activation(
            build_identity=workspace.build, now="2026-08-27T12:00:00.000Z",
            block_id="e0-block-" + "a" * 64,
        )
        intent = {
            "opportunity_id": workspace.opportunity_id,
            "intent_id": "replacement_intent_" + "b" * 64,
            "block_id": activation.block_id, "product": "SPOT",
            "action": "OPEN_LONG", "quantity": "0.001",
            "attempt_ordinal": 1, "unsigned_intent_sha256": "c" * 64,
        }
        before = state.replay()["last_event_hash"]
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            side_effect=AssertionError("transport must not run"),
        ) as transport, self.assertRaisesRegex(
            BinancePrivateRuntimeError,
            "BINANCE_PRIVATE_RUNTIME_INTENT_DECISION_MISMATCH",
        ):
            run_challenger_replacement_binance_private_intent(
                state=state, event_root=workspace.root, intent=intent,
                preflight_capability={}, activation=activation, credential=object(),
                build_identity=workspace.build,
            )
        self.assertEqual(state.replay()["last_event_hash"], before)
        transport.assert_not_called()

    def test_caller_cannot_change_verified_v076_quantity_before_transport(self):
        workspace = EventWorkspace()
        self.addCleanup(workspace.close)
        plan = fixture_v3_plan()
        economic = build_challenger_replacement_economic_plan()
        predecessor = build_challenger_replacement_simulation_contract(plan=plan)
        public_contract = build_challenger_replacement_public_simulation_contract(
            plan=plan, economic_plan=economic,
            predecessor_contract=predecessor,
        )
        capture = load_challenger_replacement_public_market_capture_bytes(
            COMMITTED_CAPTURE.read_bytes(), plan=plan,
            build_identity=V076_BUILD, previous_source_bundle=None,
        )
        root = open_challenger_replacement_event_root(workspace.identity())
        self.addCleanup(root.close)
        state = ChallengerReplacementOpportunityState(
            event_root=root, plan=plan, build_identity=V076_BUILD,
        )
        with patch(
            "crypto_quant.challenger_replacement_v3_runtime._acquire",
            return_value=capture,
        ), patch(
            "crypto_quant.challenger_replacement_v3_runtime._wall_now",
            return_value=datetime(2026, 8, 26, 4, 5, tzinfo=timezone.utc),
        ):
            run_challenger_replacement_v3_opportunity(
                state=state, event_root=root, plan=plan,
                economic_plan=economic, predecessor_contract=predecessor,
                public_contract=public_contract, build_identity=V076_BUILD,
            )
        activation = loaded_private_activation(
            build_identity=V076_BUILD, now="2026-08-27T12:00:00.000Z",
            activation_id="binance_private_activation_" + "4" * 64,
            configuration_sha256="5" * 64,
            account_approval_sha256="6" * 64,
            block_id="e0_block_" + "7" * 64,
        )
        slot = state.replay()["opportunities"][
            "ETHUSDT@2026-08-26T04:00:00.000Z"
        ]
        intent = build_binance_order_intent_from_opportunity(
            slot=slot, activation=activation, attempt_ordinal=1,
        )
        intent["quantity"] = "0.016"
        preflight = {
            "status": "BINANCE_ACCOUNT_PREFLIGHT_VERIFIED_FLAT",
            "preflight_id": "binance_account_preflight_" + "8" * 64,
            "configuration": {
                "position_mode": "ONE_WAY", "asset_mode": "SINGLE_ASSET",
                "symbol": "ETHUSDT", "margin_type": "ISOLATED",
                "leverage": 1, "auto_add_margin": False,
            },
        }
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            side_effect=AssertionError("transport must not run"),
        ) as transport, self.assertRaisesRegex(
            BinancePrivateRuntimeError,
            "BINANCE_PRIVATE_RUNTIME_INTENT_DECISION_MISMATCH",
        ):
            run_challenger_replacement_binance_private_intent(
                state=state, event_root=root, intent=intent,
                preflight_capability=preflight, activation=activation,
                credential=object(), build_identity=V076_BUILD,
            )
        transport.assert_not_called()


class BinancePrivateRuntimeQueryFirstTests(unittest.TestCase):
    NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.workspace = PrivateRuntimeWorkspace()
        self.addCleanup(self.workspace.close)
        self.public_time_patch = patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "open_fixed_public_request", side_effect=self._public_time_response,
        )
        self.public_time_patch.start()
        self.addCleanup(self.public_time_patch.stop)
        self.state = self.workspace.state()
        self._observe_opportunity()
        self.block_id = "e0-block-" + "2" * 64
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
        self.raw_preflight = self.preflight
        preflight_fixture = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "account-preflight-flat.json",
        ).read_text(encoding="utf-8"))
        account_identity = hashlib.sha256(canonical_json({
            "api_key_create_time": preflight_fixture["API_RESTRICTIONS"]["createTime"],
            "spot_uid": preflight_fixture["SPOT_ACCOUNT"]["uid"],
            "venue": "BINANCE",
        }).encode("utf-8")).hexdigest()
        credential_identity = BinanceCredentialIdentity(
            1, 2, 501, 3, 4, "9" * 64, "a" * 64,
        )
        approval = BinanceAccountApproval(
            account_identity_sha256=account_identity,
            key_fingerprint=credential_identity.key_fingerprint,
            reviewed_egress_ip="203.0.113.10", reviewer_uid=501,
            reviewed_at="2026-08-27T10:00:00.000Z",
            expires_at="2026-08-28T00:00:00.000Z",
            spot_trading_approved=True, futures_trading_approved=True,
        )
        receipt = evaluate_binance_account_preflight(
            responses={key: canonical_json(value).encode("utf-8")
                       for key, value in preflight_fixture.items()},
            account_approval=approval,
            credential_identity=credential_identity,
            build_identity=self.workspace.build,
            now="2026-08-27T12:00:00.000Z",
        )
        receipt_document = json.loads(receipt)
        self.preflight_document = receipt_document
        self.activation = loaded_private_activation(
            build_identity=self.workspace.build,
            now="2026-08-27T12:00:00.000Z",
            block_id=self.block_id,
            configuration_sha256=receipt_document["configuration_sha256"],
            account_approval_sha256=receipt_document["account_approval_sha256"],
        )
        preflight_directory = tempfile.TemporaryDirectory()
        self.addCleanup(preflight_directory.cleanup)
        parent = Path(preflight_directory.name) / "owner-only"
        parent.mkdir(mode=0o700)
        path = parent / "account-preflight.json"
        path.write_bytes(receipt); path.chmod(0o600)
        parent_stat, file_stat = parent.stat(), path.stat()
        reference = {
            "schema_version": "1.0.0", "absolute_path": str(path),
            "parent_device": parent_stat.st_dev,
            "parent_inode": parent_stat.st_ino,
            "file_device": file_stat.st_dev, "file_inode": file_stat.st_ino,
            "file_sha256": hashlib.sha256(receipt).hexdigest(),
        }
        self.preflight = open_binance_account_preflight_capability(
            reference_bytes=(canonical_json(reference) + "\n").encode(),
            expected_uid=os.getuid(), build_identity=self.workspace.build,
        )
        self.addCleanup(self.preflight.close)
        self.credential = SimpleNamespace(identity=credential_identity)
        self.intent = build_binance_order_intent_from_opportunity(
            slot=self.state.replay()["opportunities"][self.workspace.opportunity_id],
            activation=self.activation, attempt_ordinal=1,
        )
        self.client_id = self._client_id()

    @staticmethod
    def _public_time_response(request, *, max_body_bytes):
        return PublicHttpResponse(
            status=200, final_url=request.full_url,
            headers={"Content-Type": "application/json"},
            body=b'{"serverTime":1787832000000}', monotonic_rtt_ms=0,
            request_started_at="2026-08-27T12:00:00.000Z",
            response_received_at="2026-08-27T12:00:00.000Z",
        )

    def test_raw_preflight_mapping_cannot_authorize_runtime(self):
        before = self.state.replay()["last_event_hash"]
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            side_effect=AssertionError("transport must not run"),
        ) as transport, self.assertRaisesRegex(
            TypeError, "unexpected keyword argument 'preflight'",
        ):
            run_challenger_replacement_binance_private_intent(
                state=self.state, event_root=self.state.event_root,
                intent=self.intent, preflight=self.raw_preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        self.assertEqual(self.state.replay()["last_event_hash"], before)
        transport.assert_not_called()

    def test_server_time_is_durable_before_any_private_request(self):
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode("utf-8")
        public = PublicHttpResponse(
            status=200, final_url="https://api.binance.com/api/v3/time",
            headers={"Content-Type": "application/json"},
            body=b'{"serverTime":1787832000000}', monotonic_rtt_ms=0,
            request_started_at="2026-08-27T12:00:00.000Z",
            response_received_at="2026-08-27T12:00:00.000Z",
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "open_fixed_public_request", create=True, return_value=public,
        ) as public_request, patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            side_effect=(self._result("RESPONSE_INVALID", absent),
                         self._result("UNKNOWN", b"")),
        ):
            run_challenger_replacement_binance_private_intent(
                state=self.state, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["server_time_evidence"], {
            "product": "SPOT", "local_before_ms": 1787832000000,
            "server_time_ms": 1787832000000,
            "local_after_ms": 1787832000000,
            "midpoint_ms": 1787832000000, "skew_ms": 0,
            "response_sha256": hashlib.sha256(public.body).hexdigest(),
        })
        self.assertEqual(public_request.call_count, 2)
        events = [json.loads(event.final_bytes)["event_type"]
                  for event in self.state._replay()["events"]]
        self.assertEqual(events.count("BINANCE_SERVER_TIME_OBSERVED"), 2)

    def _observe_opportunity(self):
        self.workspace.observe(self.state)

    def _client_id(self):
        return derive_binance_client_order_id(
            plan_hash=self.workspace.plan["plan_hash"],
            block_id=self.intent["block_id"], intent_id=self.intent["intent_id"],
            attempt_ordinal=self.intent["attempt_ordinal"],
            product=self.intent["product"],
        )

    def _use_perpetual_decision(self):
        self.workspace = PrivateRuntimeWorkspace(latest="50")
        self.addCleanup(self.workspace.close)
        self.state = self.workspace.state()
        self._observe_opportunity()
        self.intent = build_binance_order_intent_from_opportunity(
            slot=self.state.replay()["opportunities"][self.workspace.opportunity_id],
            activation=self.activation, attempt_ordinal=1,
        )
        self.client_id = self._client_id()
        self.assertEqual(
            (self.intent["product"], self.intent["action"]),
            ("PERPETUAL", "OPEN_SHORT"),
        )

    def _append_private(self, event_type, payload):
        projection = self.state.replay()
        return self.state.append(
            event_type=event_type,
            opportunity_id=self.workspace.opportunity_id,
            worker_id="fixture-private-worker",
            recorded_at=DEFAULT_OBSERVED_AT,
            payload=payload,
            expected_last_event_hash=projection["last_event_hash"],
        )

    def _prime_perpetual_close_attempt(self):
        self.intent.update(
            product="PERPETUAL", action="CLOSE_SHORT", quantity="0.025",
        )
        client = "cq77" + "9" * 32
        common = {"intent_id": self.intent["intent_id"]}
        self._append_private("BINANCE_INTENT_AUTHORIZED", {
            **common, "opportunity_id": self.workspace.opportunity_id,
            "block_id": self.block_id, "product": "PERPETUAL",
            "action": "CLOSE_SHORT", "quantity": "0.025",
            "venue_client_order_id": client,
            "activation_id": self.activation.activation_id,
            "preflight_sha256": "4" * 64,
            "unsigned_intent_sha256": self.intent["unsigned_intent_sha256"],
        })
        self._append_private("BINANCE_ABSENCE_CHECKED", {
            **common, "venue_client_order_id": client,
            "query_response_sha256": "5" * 64, "proven_absent": True,
        })
        request_id = "binance_private_request_" + "6" * 64
        self._append_private("BINANCE_SIGNED_REQUEST_PREPARED", {
            **common, "request_id": request_id,
            "endpoint_id": "FUTURES_ORDER_CREATE",
            "request_sha256": "7" * 64, "timestamp_ms": 1787832000000,
        })
        self._append_private("BINANCE_REQUEST_SEND_STARTED", {
            **common, "request_id": request_id,
        })
        self._append_private("BINANCE_ORDER_ACKNOWLEDGED", {
            **common, "order_id": 203, "venue_client_order_id": client,
        })
        return {
            **self.intent, "venue_client_order_id": client,
            "activation_id": self.activation.activation_id,
            "side": "BUY", "reduce_only": True, "symbol": "ETHUSDT",
            "preflight_id": self.preflight_document["preflight_id"],
            "required_first_endpoint": "FUTURES_ORDER_QUERY",
            "send_permitted": False,
        }

    def _prime_perpetual_close_fills(self):
        attempt = self._prime_perpetual_close_attempt()
        common = {"intent_id": self.intent["intent_id"]}
        self._append_private("BINANCE_FILL_OBSERVED", {
            **common, "trade_id": 402, "order_id": 203,
            "quantity": "0.025", "price": "1900",
            "quote_quantity": "47.5", "fee": "0.019",
            "fee_asset": "USDT", "cumulative_filled_quantity": "0.025",
            "realized_pnl": "2.5",
        })
        self._append_private("BINANCE_ORDER_FILLED", {
            **common, "cumulative_filled_quantity": "0.025",
            "cumulative_fee": "0.019", "venue_terminal_status": "FILLED",
        })
        self._append_private("BINANCE_FILLS_FEES_REPLAYED", {
            **common, "fill_ids": [402], "cumulative_fee": "0.019",
        })
        return attempt

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

    @staticmethod
    def _futures_position(quantity="-0.025", entry="2000"):
        document = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "account-preflight-flat.json",
        ).read_text(encoding="utf-8"))["FUTURES_POSITION"]
        amount, price = Decimal(quantity), Decimal(entry)
        mark = Decimal("0") if amount == 0 else Decimal("1960")
        initial = canonical_decimal(abs(amount) * price / Decimal("2"))
        unrealized = canonical_decimal(abs(amount) * (price - mark))
        document[0].update(
            positionAmt=quantity, entryPrice=entry, markPrice=canonical_decimal(mark),
            unRealizedProfit=unrealized,
            notional=canonical_decimal(amount * mark),
            isolatedMargin=initial, isolatedWallet=initial,
            initialMargin=initial, maintMargin="1",
            positionInitialMargin=initial,
        )
        return canonical_json(document).encode("utf-8")

    @staticmethod
    def _futures_account(wallet="99.975", available="74.975",
                         unrealized="1", initial="25"):
        document = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "account-preflight-flat.json",
        ).read_text(encoding="utf-8"))["FUTURES_ACCOUNT"]
        document.update(
            totalInitialMargin=initial, totalMaintMargin="1",
            totalWalletBalance=wallet, totalUnrealizedProfit=unrealized,
            totalMarginBalance=canonical_decimal(
                Decimal(wallet) + Decimal(unrealized)
            ), totalPositionInitialMargin=initial,
            availableBalance=available, maxWithdrawAmount=available,
        )
        document["assets"][0].update(
            walletBalance=wallet, unrealizedProfit=unrealized,
            marginBalance=canonical_decimal(Decimal(wallet) + Decimal(unrealized)),
            maintMargin="1", initialMargin=initial,
            positionInitialMargin=initial, availableBalance=available,
            maxWithdrawAmount=available,
        )
        return canonical_json(document).encode("utf-8")

    def _futures_account_for(self, quantity):
        amount = Decimal(quantity)
        initial = amount * Decimal("2000") / Decimal("2")
        fee = amount * Decimal("2000") * Decimal("0.0004")
        wallet = Decimal("100") - fee - Decimal("0.005")
        return self._futures_account(
            canonical_decimal(wallet), canonical_decimal(wallet - initial),
            canonical_decimal(amount * Decimal("40")), canonical_decimal(initial),
        )

    def _futures_filled_documents(self, quantity="0.025"):
        quote = canonical_decimal(Decimal(quantity) * Decimal("2000"))
        fee = canonical_decimal(Decimal(quote) * Decimal("0.0004"))
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode("utf-8")
        filled = canonical_json({
            "symbol": "ETHUSDT", "orderId": 202,
            "clientOrderId": self.client_id, "avgPrice": "2000",
            "origQty": quantity, "executedQty": quantity,
            "cumQuote": quote, "status": "FILLED", "type": "MARKET",
            "side": "SELL", "positionSide": "BOTH", "reduceOnly": False,
            "updateTime": 1787832000000,
        }).encode("utf-8")
        trades = canonical_json([{
            "symbol": "ETHUSDT", "id": 401, "orderId": 202,
            "qty": quantity, "price": "2000", "quoteQty": quote,
            "commission": fee, "commissionAsset": "USDT",
            "realizedPnl": "0", "time": 1787832000002, "buyer": False,
        }]).encode("utf-8")
        return absent, filled, trades, self._futures_position("-" + quantity)

    def _spot_reconciliation(self, trade_id=301):
        facts = {
            "product": "SPOT", "signed_quantity": "0.001",
            "average_entry_price_or_null": "2000", "realized_pnl": "0",
            "unrealized_pnl": "0", "cumulative_fee": "0.002",
            "funding": "0", "wallet_balance": "99.998",
            "available_balance": "97.998", "open_order_count": 0,
            "protective_stop_client_id_or_null": None,
            "fill_ids": [trade_id],
        }
        order_id = 100 + trade_id
        order = canonical_json({
            "symbol": "ETHUSDT", "orderId": order_id,
            "clientOrderId": "cq77" + format(trade_id, "032x"),
            "price": "0", "origQty": "0.001", "executedQty": "0.001",
            "cummulativeQuoteQty": "2", "status": "FILLED",
            "timeInForce": "GTC", "type": "MARKET", "side": "BUY",
            "transactTime": 1787832000000,
        }).encode()
        trade = canonical_json({
            "symbol": "ETHUSDT", "id": trade_id, "orderId": order_id,
            "qty": "0.001", "price": "2000", "quoteQty": "2",
            "commission": "0.002", "commissionAsset": "USDT",
            "time": 1787832000001, "isBuyer": True,
        }).encode()
        return reconcile_binance_private_state(
            event_projection=facts, ledger_projection=facts,
            authorized_order={"order_id": order_id,
                              "client_order_id": "cq77" + format(trade_id, "032x")},
            authorized_stop_or_null=None,
            order_documents=(order,), trade_documents=(trade,),
            account_document=self._spot_account("0.001", "97.998"),
            position_document=canonical_json({
                "symbol": "ETHUSDT", "mark_price": "2000", "ask_price": "2001",
                "asset_marks_usdt": {"ETH": "2000", "USDT": "1"},
            }).encode(), income_documents=(), algo_documents=(),
            capture_publications=fixture_capture_publications(),
        )

    def test_previous_reconciliation_rejects_unbound_historical_parent(self):
        first, latest = self._spot_reconciliation(301), self._spot_reconciliation(302)

        def private(data, product="SPOT"):
            loaded = load_binance_reconciliation_bytes(data)
            return {
                "stage": "BINANCE_RECONCILIATION_SUCCEEDED",
                "product": product, "action": "OPEN_LONG",
                "reconciliation_id": loaded["reconciliation_id"],
                "reconciliation_sha256": hashlib.sha256(data).hexdigest(),
                "reconciliation_bytes_base64": base64.b64encode(data).decode(),
            }

        class HistoricalState:
            def replay(self_nonlocal):
                return {"opportunities": {
                    "ETHUSDT@2026-08-27T00:00:00.000Z": {"private": private(first)},
                    "ETHUSDT@2026-08-27T04:00:00.000Z": {
                        "private": private(first, "PERPETUAL"),
                    },
                    "ETHUSDT@2026-08-27T08:00:00.000Z": {"private": private(latest)},
                    "ETHUSDT@2026-08-27T12:00:00.000Z": {},
                }}

        with self.assertRaisesRegex(
            BinancePrivateRuntimeError,
            "BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID",
        ):
            _previous_reconciliation_bytes(
                HistoricalState(), product="SPOT",
                before_opportunity_id="ETHUSDT@2026-08-27T12:00:00.000Z",
            )
        self.assertIsNone(_previous_reconciliation_bytes(
            HistoricalState(), product="SPOT",
            before_opportunity_id="ETHUSDT@2026-08-27T00:00:00.000Z",
        ))

    def test_spot_close_facts_preserve_parent_cost_fees_and_realized_pnl(self):
        opportunity_id = "ETHUSDT@2026-08-27T12:00:00.000Z"
        fill = {
            "trade_id": 302, "order_id": 402, "quantity": "0.001",
            "price": "2100", "quote_quantity": "2.1", "fee": "0.0021",
            "fee_asset": "USDT",
        }

        class Event:
            final_bytes = canonical_json({
                "slot_id": opportunity_id,
                "event_type": "BINANCE_FILL_OBSERVED",
                "payload_bytes_base64": base64.b64encode(
                    canonical_json(fill).encode()
                ).decode(),
            }).encode()

        class State:
            def _replay(self_nonlocal):
                return {"events": [Event()]}

        facts = _spot_facts(
            State(), {"opportunity_id": opportunity_id, "action": "CLOSE_LONG"},
            self.activation, market=canonical_json({
                "symbol": "ETHUSDT", "mark_price": "2100", "ask_price": "2101",
                "asset_marks_usdt": {"ETH": "2100", "USDT": "1"},
            }).encode(),
            previous_reconciliation_bytes_or_null=self._spot_reconciliation(),
        )
        expected = {
            "product": "SPOT", "signed_quantity": "0",
            "average_entry_price_or_null": None, "realized_pnl": "0.1",
            "unrealized_pnl": "0", "cumulative_fee": "0.0041",
            "funding": "0", "wallet_balance": "100.0959",
            "available_balance": "100.0959", "open_order_count": 0,
            "protective_stop_client_id_or_null": None,
            "fill_ids": [301, 302],
        }
        self.assertEqual(facts, expected)

    def _futures_stop(self, quantity="0.025"):
        return prepare_binance_protective_stop(
            short_quantity=quantity, trigger_price="2036.43",
            intent_identity={
                "plan_hash": self.workspace.plan["plan_hash"],
                "block_id": self.intent["block_id"],
                "intent_id": self.intent["intent_id"],
            },
        )

    def _perpetual_reconciliation(self):
        stop = self._futures_stop()
        _, order, trades, position = self._futures_filled_documents()
        trade_documents = tuple(
            canonical_json(item).encode() for item in json.loads(trades)
        )
        income = canonical_json({
            "tranId": 501, "symbol": "ETHUSDT",
            "incomeType": "FUNDING_FEE", "income": "-0.005",
            "asset": "USDT", "time": 1787832000003,
        }).encode()
        facts = {
            "product": "PERPETUAL", "signed_quantity": "-0.025",
            "average_entry_price_or_null": "2000", "realized_pnl": "0",
            "unrealized_pnl": "1", "cumulative_fee": "0.02",
            "funding": "-0.005", "wallet_balance": "99.975",
            "available_balance": "74.975", "open_order_count": 0,
            "protective_stop_client_id_or_null": stop["client_algo_id"],
            "fill_ids": [401],
        }
        return reconcile_binance_private_state(
            event_projection=facts, ledger_projection=facts,
            authorized_order={"order_id": 202,
                              "client_order_id": json.loads(order)["clientOrderId"]},
            authorized_stop_or_null={
                "client_algo_id": stop["client_algo_id"],
                "side": stop["side"], "quantity": stop["quantity"],
                "trigger_price": stop["trigger_price"],
                "reduce_only": stop["reduce_only"],
            },
            order_documents=(order,), trade_documents=trade_documents,
            account_document=self._futures_account(),
            position_document=position, income_documents=(income,),
            algo_documents=(self._active_algo(stop),),
            capture_publications=fixture_capture_publications(),
        )

    def _partial_close_case(self):
        attempt = self._prime_perpetual_close_attempt()
        previous = self._perpetual_reconciliation()
        old = self._futures_stop("0.025")
        order = canonical_json({
            "symbol": "ETHUSDT", "orderId": 203,
            "clientOrderId": attempt["venue_client_order_id"],
            "avgPrice": "1900", "origQty": "0.025",
            "executedQty": "0.01", "cumQuote": "19",
            "status": "PARTIALLY_FILLED", "type": "MARKET", "side": "BUY",
            "positionSide": "BOTH", "reduceOnly": True,
            "updateTime": 1787832000000,
        }).encode()
        trades = canonical_json([{
            "symbol": "ETHUSDT", "id": 402, "orderId": 203,
            "qty": "0.01", "price": "1900", "quoteQty": "19",
            "commission": "0.0076", "commissionAsset": "USDT",
            "realizedPnl": "1", "time": 1787832000001, "buyer": True,
        }]).encode()
        position = self._futures_position("-0.015")
        result = BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, order, hashlib.sha256(order).hexdigest(), (),
        )
        context = SimpleNamespace(
            credential=self.credential, activation=self.activation,
            build_identity=self.workspace.build,
            recorded_at="2026-08-27T12:00:00.000Z",
            timestamp_ms=1787832000000,
        )
        return SimpleNamespace(
            attempt=attempt, previous=previous, old=old, order=result,
            trades=trades, position=position, context=context,
        )

    def test_perpetual_close_facts_flatten_parent_and_drop_protection(self):
        opportunity_id = "ETHUSDT@2026-08-27T12:00:00.000Z"
        fill = {
            "trade_id": 402, "order_id": 203, "quantity": "0.025",
            "price": "1900", "quote_quantity": "47.5", "fee": "0.019",
            "realized_pnl": "2.5",
        }

        class Event:
            final_bytes = canonical_json({
                "slot_id": opportunity_id,
                "event_type": "BINANCE_FILL_OBSERVED",
                "payload_bytes_base64": base64.b64encode(
                    canonical_json(fill).encode()
                ).decode(),
            }).encode()

        class State:
            def _replay(self_nonlocal):
                return {"events": [Event()]}

        position = json.loads(self._futures_position("0", "0"))
        position[0].update(
            markPrice="0", unRealizedProfit="0", notional="0",
            isolatedMargin="0", isolatedWallet="0", initialMargin="0",
            maintMargin="0", positionInitialMargin="0",
        )
        facts = _perpetual_facts(
            State(), {"opportunity_id": opportunity_id,
                      "action": "CLOSE_SHORT"}, self.activation,
            canonical_json(position).encode(), (), None,
            previous_reconciliation_bytes_or_null=self._perpetual_reconciliation(),
        )
        expected = {
            "product": "PERPETUAL", "signed_quantity": "0",
            "average_entry_price_or_null": None, "realized_pnl": "2.5",
            "unrealized_pnl": "0", "cumulative_fee": "0.039",
            "funding": "-0.005", "wallet_balance": "102.456",
            "available_balance": "102.456", "open_order_count": 0,
            "protective_stop_client_id_or_null": None,
            "fill_ids": [401, 402],
        }
        self.assertEqual(facts, expected)

    def _flat_close_capture_inputs(self):
        attempt = self._prime_perpetual_close_fills()
        previous = self._perpetual_reconciliation()
        order = canonical_json({
            "symbol": "ETHUSDT", "orderId": 203,
            "clientOrderId": attempt["venue_client_order_id"],
            "avgPrice": "1900", "origQty": "0.025",
            "executedQty": "0.025", "cumQuote": "47.5",
            "status": "FILLED", "type": "MARKET", "side": "BUY",
            "positionSide": "BOTH", "reduceOnly": True,
            "updateTime": 1787832000000,
        }).encode()
        trade = canonical_json({
            "symbol": "ETHUSDT", "id": 402, "orderId": 203,
            "qty": "0.025", "price": "1900", "quoteQty": "47.5",
            "commission": "0.019", "commissionAsset": "USDT",
            "realizedPnl": "2.5", "time": 1787832000001,
            "buyer": True,
        }).encode()
        position = json.loads(self._futures_position("0", "0"))
        position[0].update(
            markPrice="0", unRealizedProfit="0", notional="0",
            isolatedMargin="0", isolatedWallet="0", initialMargin="0",
            maintMargin="0", positionInitialMargin="0",
        )
        inputs = list(private_runtime._capture_inputs(
            self.state, attempt, self.activation, order_documents=(order,),
            trade_documents=(trade,),
            account_document=self._futures_account(
                "102.456", "102.456", "0", "0",
            ),
            position_document=canonical_json(position).encode(),
            income_documents=(), algo_documents=(), previous=previous,
            stop=None,
        ))
        return attempt, inputs

    def test_captured_ledger_disagreement_cannot_reuse_event_projection(self):
        attempt, inputs = self._flat_close_capture_inputs()
        ledger = json.loads(inputs[1])
        ledger["fills"][0]["fee"] = "9"
        inputs[1] = canonical_json(ledger).encode()
        private_runtime._capture(
            self.state, attempt, tuple(inputs), DEFAULT_OBSERVED_AT,
        )
        with self.assertRaisesRegex(
            BinancePrivateRuntimeError, "BINANCE_LEDGER_PROJECTION_MISMATCH",
        ):
            private_runtime._reconcile_captured(
                self.state, attempt, self.activation, DEFAULT_OBSERVED_AT,
            )
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_RECONCILIATION_FAILED")
        self.assertEqual(private["failure_reason_code"],
                         "BINANCE_LEDGER_PROJECTION_MISMATCH")

    def test_captured_event_transcript_disagreement_is_rejected(self):
        attempt, inputs = self._flat_close_capture_inputs()
        event_input = json.loads(inputs[0])
        fill = next(item["payload"] for item in event_input["private_events"]
                    if item["event_type"] == "BINANCE_FILL_OBSERVED")
        fill["fee"] = "9"
        inputs[0] = canonical_json(event_input).encode()
        private_runtime._capture(
            self.state, attempt, tuple(inputs), DEFAULT_OBSERVED_AT,
        )
        with self.assertRaisesRegex(
            BinancePrivateRuntimeError,
            "BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID",
        ):
            private_runtime._reconcile_captured(
                self.state, attempt, self.activation, DEFAULT_OBSERVED_AT,
            )

    def test_perpetual_close_queries_then_cancels_orphan_stop_once(self):
        attempt = self._prime_perpetual_close_fills()
        stop = self._futures_stop(self.intent["quantity"])
        active = self._active_algo(stop)
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode()
        responses = tuple(BinancePrivateTransportResult(
            kind, status, body, hashlib.sha256(body).hexdigest(), (),
        ) for kind, status, body in (
            ("QUERY_SUCCEEDED", 200, active),
            ("ACKNOWLEDGED", 200, active),
            ("RESPONSE_INVALID", 400, absent),
        ))
        context = SimpleNamespace(
            credential=self.credential, activation=self.activation,
            build_identity=self.workspace.build,
            recorded_at="2026-08-27T12:00:00.000Z",
            timestamp_ms=1787832000000,
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=responses,
        ) as transport, patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_finish_perpetual", return_value={"status": "FINISHED"},
        ) as finish:
            result = _cleanup_perpetual_stop(
                self.state, attempt, self._perpetual_reconciliation(), context,
            )
        self.assertEqual(result, {"status": "FINISHED"})
        self.assertEqual(
            [call.args[0].endpoint_id for call in transport.call_args_list],
            ["FUTURES_ALGO_QUERY", "FUTURES_ALGO_CANCEL",
             "FUTURES_ALGO_QUERY"],
        )
        finish.assert_called_once()
        cleanup = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]["stop_cleanup"]
        self.assertEqual(cleanup["stage"], "BINANCE_STOP_CLEANUP_RECONCILED")
        self.assertEqual(cleanup["client_algo_id"], stop["client_algo_id"])

    def test_unprotected_short_uses_query_first_reduce_only_emergency_flatten(self):
        attempt = self._prime_perpetual_close_fills()
        position = self._futures_position("-0.025")
        flat = self._futures_position("0", "0")
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode()
        filled = canonical_json({"status": "FILLED"}).encode()
        responses = (
            BinancePrivateTransportResult(
                "RESPONSE_INVALID", 400, absent,
                hashlib.sha256(absent).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "ACKNOWLEDGED", 200, filled,
                hashlib.sha256(filled).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, filled,
                hashlib.sha256(filled).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, flat,
                hashlib.sha256(flat).hexdigest(), (),
            ),
        )
        context = SimpleNamespace(
            credential=self.credential, activation=self.activation,
            build_identity=self.workspace.build,
            recorded_at="2026-08-27T12:00:00.000Z",
            timestamp_ms=1787832000000,
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=responses,
        ) as transport:
            result = _emergency_flatten(
                self.state, attempt, position, context,
            )
        self.assertEqual(result["status"], "EMERGENCY_FLATTEN_RECONCILED")
        requests = [call.args[0] for call in transport.call_args_list]
        self.assertEqual([item.endpoint_id for item in requests], [
            "FUTURES_ORDER_QUERY", "FUTURES_ORDER_CREATE",
            "FUTURES_ORDER_QUERY", "FUTURES_POSITION",
        ])
        self.assertIn(b"reduceOnly=true", requests[1].encoded_parameters)
        self.assertIn(b"side=BUY", requests[1].encoded_parameters)
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(
            private["emergency_flatten"]["stage"],
            "BINANCE_EMERGENCY_FLATTEN_RECONCILED",
        )

    def test_emergency_flatten_unknown_never_resends_and_restart_queries_flat(self):
        attempt = self._prime_perpetual_close_fills()
        position = self._futures_position("-0.025")
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode()
        unknown = b'{"code":-1007,"msg":"Timeout"}'
        first = (
            BinancePrivateTransportResult(
                "RESPONSE_INVALID", 400, absent,
                hashlib.sha256(absent).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "UNKNOWN", None, unknown,
                hashlib.sha256(unknown).hexdigest(), (),
            ),
        )
        context = SimpleNamespace(
            credential=self.credential, activation=self.activation,
            build_identity=self.workspace.build,
            recorded_at="2026-08-27T12:00:00.000Z",
            timestamp_ms=1787832000000,
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=first,
        ):
            result = _emergency_flatten(
                self.state, attempt, position, context,
            )
        self.assertEqual(result["status"], "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN")
        flat = self._futures_position("0", "0")
        observed = canonical_json({"status": "FILLED"}).encode()
        second = (
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, observed,
                hashlib.sha256(observed).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, flat,
                hashlib.sha256(flat).hexdigest(), (),
            ),
        )
        fresh = self.workspace.state()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=second,
        ) as transport:
            resumed = _emergency_flatten(
                fresh, attempt, position, context,
            )
        self.assertEqual(resumed["status"], "EMERGENCY_FLATTEN_RECONCILED")
        self.assertEqual([call.args[0].endpoint_id for call in
                          transport.call_args_list], [
            "FUTURES_ORDER_QUERY", "FUTURES_POSITION",
        ])

    def test_perpetual_cleanup_rejects_inactive_status_for_different_algo(self):
        attempt = self._prime_perpetual_close_fills()
        stop = self._futures_stop(self.intent["quantity"])
        active = self._active_algo(stop)
        wrong = json.loads(active)
        wrong.update(algoId=902, algoStatus="CANCELED")
        wrong = canonical_json(wrong).encode()
        responses = tuple(BinancePrivateTransportResult(
            kind, 200, body, hashlib.sha256(body).hexdigest(), (),
        ) for kind, body in (
            ("QUERY_SUCCEEDED", active), ("ACKNOWLEDGED", active),
            ("QUERY_SUCCEEDED", wrong),
        ))
        context = SimpleNamespace(
            credential=self.credential, activation=self.activation,
            build_identity=self.workspace.build,
            recorded_at="2026-08-27T12:00:00.000Z",
            timestamp_ms=1787832000000,
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=responses,
        ), self.assertRaisesRegex(
            BinancePrivateRuntimeError,
            "BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID",
        ):
            _cleanup_perpetual_stop(
                self.state, attempt, self._perpetual_reconciliation(), context,
            )

    def test_perpetual_close_routes_terminal_fill_to_stop_cleanup(self):
        attempt = self._prime_perpetual_close_fills()
        order = canonical_json({
            "symbol": "ETHUSDT", "orderId": 203,
            "clientOrderId": attempt["venue_client_order_id"],
            "avgPrice": "1900", "origQty": "0.025",
            "executedQty": "0.025", "cumQuote": "47.5",
            "status": "FILLED", "type": "MARKET", "side": "BUY",
            "positionSide": "BOTH", "reduceOnly": True,
            "updateTime": 1787832000000,
        }).encode()
        trades = canonical_json([{
            "symbol": "ETHUSDT", "id": 402, "orderId": 203,
            "qty": "0.025", "price": "1900", "quoteQty": "47.5",
            "commission": "0.019", "commissionAsset": "USDT",
            "realizedPnl": "2.5", "time": 1787832000001,
            "buyer": True,
        }]).encode()
        flat = json.loads(self._futures_position("0", "0"))
        flat[0].update(positionAmt="0", entryPrice="0")
        position = canonical_json(flat).encode()
        result = BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, order, hashlib.sha256(order).hexdigest(), (),
        )
        context = SimpleNamespace(
            credential=self.credential, activation=self.activation,
            build_identity=self.workspace.build,
            recorded_at="2026-08-27T12:00:00.000Z",
            timestamp_ms=1787832000000,
        )
        query_results = (
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, trades,
                hashlib.sha256(trades).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, position,
                hashlib.sha256(position).hexdigest(), (),
            ),
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime._query",
            side_effect=query_results,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_previous_reconciliation_bytes",
            return_value=self._perpetual_reconciliation(),
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_cleanup_perpetual_stop", return_value={"status": "CLEANED"},
        ) as cleanup, patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_ensure_stop", side_effect=AssertionError("must not create stop"),
        ):
            self.assertEqual(_observe_order(
                state=self.state, attempt=attempt,
                order_result=result, context=context,
            ), {"status": "CLEANED"})
        cleanup.assert_called_once()

    def test_partial_perpetual_close_inherits_verified_stop_before_replacement(self):
        attempt = self._prime_perpetual_close_attempt()
        previous = self._perpetual_reconciliation()
        loaded = load_binance_reconciliation_bytes(previous)
        old = self._futures_stop("0.025")
        order = canonical_json({
            "symbol": "ETHUSDT", "orderId": 203,
            "clientOrderId": attempt["venue_client_order_id"],
            "avgPrice": "1900", "origQty": "0.025",
            "executedQty": "0.01", "cumQuote": "19",
            "status": "PARTIALLY_FILLED", "type": "MARKET", "side": "BUY",
            "positionSide": "BOTH", "reduceOnly": True,
            "updateTime": 1787832000000,
        }).encode()
        trades = canonical_json([{
            "symbol": "ETHUSDT", "id": 402, "orderId": 203,
            "qty": "0.01", "price": "1900", "quoteQty": "19",
            "commission": "0.0076", "commissionAsset": "USDT",
            "realizedPnl": "1", "time": 1787832000001, "buyer": True,
        }]).encode()
        position = self._futures_position("-0.015")
        active = self._active_algo(old)
        result = BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, order, hashlib.sha256(order).hexdigest(), (),
        )
        context = SimpleNamespace(
            credential=self.credential, activation=self.activation,
            build_identity=self.workspace.build,
            recorded_at="2026-08-27T12:00:00.000Z",
            timestamp_ms=1787832000000,
        )
        query_results = tuple(BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, body, hashlib.sha256(body).hexdigest(), (),
        ) for body in (trades, position))
        old_result = BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, active,
            hashlib.sha256(active).hexdigest(), (),
        )
        original_append = self.state.append

        class InheritanceBoundary(BaseException):
            pass

        def append_then_crash(**kwargs):
            event = original_append(**kwargs)
            if kwargs["event_type"] == "BINANCE_STOP_INHERITED":
                raise InheritanceBoundary()
            return event

        with patch.object(self.state, "append", side_effect=append_then_crash), \
                patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "_query", side_effect=query_results,
                ), patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "_previous_reconciliation_bytes", return_value=previous,
                ), patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "execute_binance_private_request", return_value=old_result,
                ) as transport, self.assertRaises(InheritanceBoundary):
            _observe_order(
                state=self.state, attempt=attempt,
                order_result=result, context=context,
            )
        inherited = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]["stop"]
        self.assertEqual(inherited["stage"], "BINANCE_STOP_RECONCILED")
        self.assertEqual(inherited["client_algo_id"], old["client_algo_id"])
        self.assertEqual(inherited["quantity"], "0.025")
        self.assertEqual(inherited["prior_reconciliation_id"],
                         loaded["reconciliation_id"])
        self.assertEqual([call.args[0].endpoint_id for call in
                          transport.call_args_list], ["FUTURES_ALGO_QUERY"])

    def test_partial_perpetual_close_replaces_stop_for_remaining_exposure(self):
        case = self._partial_close_case()
        candidate = prepare_binance_protective_stop(
            short_quantity="0.015", trigger_price=case.old["trigger_price"],
            intent_identity={
                "plan_hash": self.workspace.plan["plan_hash"],
                "block_id": case.attempt["block_id"],
                "intent_id": case.attempt["intent_id"],
            },
        )
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode()
        active_old = self._active_algo(case.old)
        active_candidate = self._active_algo(candidate)
        canceled_old = canonical_json({
            **json.loads(active_old), "algoStatus": "CANCELED",
        }).encode()
        query_results = tuple(BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, body, hashlib.sha256(body).hexdigest(), (),
        ) for body in (case.trades, case.position))
        documents = (
            ("QUERY_SUCCEEDED", 200, active_old),
            ("RESPONSE_INVALID", 400, absent),
            ("ACKNOWLEDGED", 200, active_candidate),
            ("QUERY_SUCCEEDED", 200, active_candidate),
            ("QUERY_SUCCEEDED", 200, active_candidate),
            ("ACKNOWLEDGED", 200, canceled_old),
            ("QUERY_SUCCEEDED", 200, canceled_old),
        )
        responses = tuple(BinancePrivateTransportResult(
            kind, status, body, hashlib.sha256(body).hexdigest(), (),
        ) for kind, status, body in documents)
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_query", side_effect=query_results,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_previous_reconciliation_bytes", return_value=case.previous,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=responses,
        ) as transport:
            result = _observe_order(
                state=self.state, attempt=case.attempt,
                order_result=case.order, context=case.context,
            )
        self.assertEqual(result["status"],
                         "PROTECTION_VERIFIED_RECONCILIATION_PENDING")
        stop = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]["stop"]
        self.assertEqual(stop["quantity"], "0.015")
        self.assertEqual(stop["client_algo_id"], candidate["client_algo_id"])
        self.assertEqual(stop["replacement"]["stage"],
                         "BINANCE_STOP_REPLACEMENT_SUCCEEDED")
        self.assertEqual([call.args[0].endpoint_id for call in
                          transport.call_args_list], [
            "FUTURES_ALGO_QUERY", "FUTURES_ALGO_QUERY",
            "FUTURES_ALGO_CREATE", "FUTURES_ALGO_QUERY",
            "FUTURES_ALGO_QUERY", "FUTURES_ALGO_CANCEL",
            "FUTURES_ALGO_QUERY",
        ])
        fresh = self.workspace.state()
        fresh_queries = tuple(BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, body, hashlib.sha256(body).hexdigest(), (),
        ) for body in (case.trades, case.position))
        verified = BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, active_candidate,
            hashlib.sha256(active_candidate).hexdigest(), (),
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_query", side_effect=fresh_queries,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", return_value=verified,
        ) as fresh_transport:
            replayed = _observe_order(
                state=fresh, attempt=case.attempt,
                order_result=case.order, context=case.context,
            )
        self.assertEqual(replayed["status"],
                         "PROTECTION_VERIFIED_RECONCILIATION_PENDING")
        self.assertEqual([call.args[0].endpoint_id for call in
                          fresh_transport.call_args_list], [
            "FUTURES_ALGO_QUERY",
        ])
        dispatched = self.workspace.state()
        existing = dispatched.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        dispatched_queries = tuple(BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, body, hashlib.sha256(body).hexdigest(), (),
        ) for body in (case.trades, case.position))
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_query_order", return_value=case.order,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_query", side_effect=dispatched_queries,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", return_value=verified,
        ):
            resumed = private_runtime._resume_perpetual_fills(
                dispatched, case.attempt, existing, case.context,
            )
        self.assertEqual(resumed["status"],
                         "PROTECTION_VERIFIED_RECONCILIATION_PENDING")
        cleanup_state = self.workspace.state()
        absent_after_cancel = BinancePrivateTransportResult(
            "RESPONSE_INVALID", 400, absent,
            hashlib.sha256(absent).hexdigest(), (),
        )
        cleanup_responses = (
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, active_candidate,
                hashlib.sha256(active_candidate).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "ACKNOWLEDGED", 200, active_candidate,
                hashlib.sha256(active_candidate).hexdigest(), (),
            ),
            absent_after_cancel,
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=cleanup_responses,
        ) as cleanup_transport, patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_finish_perpetual", return_value={"status": "CLEANED"},
        ):
            cleaned = _cleanup_perpetual_stop(
                cleanup_state, case.attempt, case.previous, case.context,
            )
        self.assertEqual(cleaned, {"status": "CLEANED"})
        self.assertEqual([call.args[0].encoded_parameters for call in
                          cleanup_transport.call_args_list][0].count(
            candidate["client_algo_id"].encode("ascii")
        ), 1)

    def test_partial_close_candidate_prepared_crash_resumes_one_create(self):
        case = self._partial_close_case()
        candidate = prepare_binance_protective_stop(
            short_quantity="0.015", trigger_price=case.old["trigger_price"],
            intent_identity={
                "plan_hash": self.workspace.plan["plan_hash"],
                "block_id": case.attempt["block_id"],
                "intent_id": case.attempt["intent_id"],
            },
        )
        active_old = self._active_algo(case.old)
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode()
        initial_queries = tuple(BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, body, hashlib.sha256(body).hexdigest(), (),
        ) for body in (case.trades, case.position))
        initial_transport = (
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, active_old,
                hashlib.sha256(active_old).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "RESPONSE_INVALID", 400, absent,
                hashlib.sha256(absent).hexdigest(), (),
            ),
        )
        original_append = self.state.append

        class PreparedBoundary(BaseException):
            pass

        def append_then_crash(**kwargs):
            event = original_append(**kwargs)
            if (kwargs["event_type"] == "BINANCE_STOP_SIGNED_REQUEST_PREPARED"
                    and kwargs["payload"]["client_algo_id"]
                    == candidate["client_algo_id"]):
                raise PreparedBoundary()
            return event

        with patch.object(self.state, "append", side_effect=append_then_crash), \
                patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "_query", side_effect=initial_queries,
                ), patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "_previous_reconciliation_bytes", return_value=case.previous,
                ), patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "execute_binance_private_request",
                    side_effect=initial_transport,
                ), self.assertRaises(PreparedBoundary):
            _observe_order(
                state=self.state, attempt=case.attempt,
                order_result=case.order, context=case.context,
            )
        prepared = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]["stop"]["replacement"]["candidate"]
        self.assertEqual(prepared["stage"],
                         "BINANCE_STOP_SIGNED_REQUEST_PREPARED")

        active_candidate = self._active_algo(candidate)
        canceled_old = canonical_json({
            **json.loads(active_old), "algoStatus": "CANCELED",
        }).encode()
        fresh_queries = tuple(BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, body, hashlib.sha256(body).hexdigest(), (),
        ) for body in (case.trades, case.position))
        documents = (
            ("RESPONSE_INVALID", absent),
            ("ACKNOWLEDGED", active_candidate),
            ("QUERY_SUCCEEDED", active_candidate),
            ("QUERY_SUCCEEDED", active_candidate),
            ("ACKNOWLEDGED", canceled_old),
            ("QUERY_SUCCEEDED", canceled_old),
        )
        responses = tuple(BinancePrivateTransportResult(
            kind, 400 if kind == "RESPONSE_INVALID" else 200,
            body, hashlib.sha256(body).hexdigest(), (),
        ) for kind, body in documents)
        fresh = self.workspace.state()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_query", side_effect=fresh_queries,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=responses,
        ) as transport:
            result = _observe_order(
                state=fresh, attempt=case.attempt,
                order_result=case.order, context=case.context,
            )
        self.assertEqual(result["status"],
                         "PROTECTION_VERIFIED_RECONCILIATION_PENDING")
        self.assertEqual([call.args[0].endpoint_id for call in
                          transport.call_args_list], [
            "FUTURES_ALGO_QUERY", "FUTURES_ALGO_CREATE",
            "FUTURES_ALGO_QUERY",
            "FUTURES_ALGO_QUERY", "FUTURES_ALGO_CANCEL",
            "FUTURES_ALGO_QUERY",
        ])

    @staticmethod
    def _active_algo(stop):
        return canonical_json({
            "algoId": 901, "clientAlgoId": stop["client_algo_id"],
            "algoType": "CONDITIONAL", "orderType": "STOP_MARKET",
            "symbol": "ETHUSDT", "side": "BUY", "positionSide": "BOTH",
            "quantity": stop["quantity"], "triggerPrice": stop["trigger_price"],
            "workingType": "MARK_PRICE", "reduceOnly": True,
            "closePosition": False, "algoStatus": "NEW",
        }).encode("utf-8")

    def test_futures_fixture_without_v076_stop_evidence_fails_closed(self):
        self._use_perpetual_decision()
        replay = self.state.replay
        def without_stop_evidence():
            projection = copy.deepcopy(replay())
            slot = projection["opportunities"][self.workspace.opportunity_id]
            if slot.get("private", {}).get("stage") == "BINANCE_FILLS_FEES_REPLAYED":
                slot["result_evidence"]["next_snapshot"][
                    "protective_stop_or_null"] = None
            return projection
        absent, filled, trades, position = self._futures_filled_documents(
            self.intent["quantity"]
        )
        responses = tuple(
            BinancePrivateTransportResult(
                kind, status, body, hashlib.sha256(body).hexdigest(), (),
            )
            for kind, status, body in (
                ("RESPONSE_INVALID", 400, absent),
                ("ACKNOWLEDGED", 200, filled),
                ("QUERY_SUCCEEDED", 200, filled),
                ("QUERY_SUCCEEDED", 200, trades),
                ("QUERY_SUCCEEDED", 200, position),
            )
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch.object(
            self.state, "replay", side_effect=without_stop_evidence,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=responses,
        ) as transport, self.assertRaisesRegex(
            BinancePrivateRuntimeError,
            "BINANCE_PRIVATE_RUNTIME_STOP_EVIDENCE_REQUIRED",
        ):
            run_challenger_replacement_binance_private_intent(
                state=self.state, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        self.assertEqual(
            [call.args[0].endpoint_id for call in transport.call_args_list],
            ["FUTURES_ORDER_QUERY", "FUTURES_ORDER_CREATE",
             "FUTURES_ORDER_QUERY", "FUTURES_TRADES", "FUTURES_POSITION"],
        )
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_FILLS_FEES_REPLAYED")
        self.assertNotIn("stop", private)

    def test_futures_fill_creates_query_first_stop_before_pending_reconciliation(self):
        self._use_perpetual_decision()
        absent, filled, trades, position = self._futures_filled_documents(
            self.intent["quantity"]
        )
        stop = self._futures_stop(self.intent["quantity"])
        algo = canonical_json({
            "algoId": 901, "clientAlgoId": stop["client_algo_id"],
            "algoType": "CONDITIONAL", "orderType": "STOP_MARKET",
            "symbol": "ETHUSDT", "side": "BUY", "positionSide": "BOTH",
            "quantity": stop["quantity"], "triggerPrice": stop["trigger_price"],
            "workingType": "MARK_PRICE", "reduceOnly": True,
            "closePosition": False, "algoStatus": "NEW",
        }).encode("utf-8")
        documents = (
            ("RESPONSE_INVALID", 400, absent),
            ("ACKNOWLEDGED", 200, filled),
            ("QUERY_SUCCEEDED", 200, filled),
            ("QUERY_SUCCEEDED", 200, trades),
            ("QUERY_SUCCEEDED", 200, position),
            ("RESPONSE_INVALID", 400, absent),
            ("ACKNOWLEDGED", 200, algo),
            ("QUERY_SUCCEEDED", 200, algo),
        )
        responses = tuple(BinancePrivateTransportResult(
            kind, status, body, hashlib.sha256(body).hexdigest(), (),
        ) for kind, status, body in documents)
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_expected_stop", return_value=stop, create=True,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=responses,
        ) as transport:
            result = run_challenger_replacement_binance_private_intent(
                state=self.state, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        self.assertEqual(result["status"],
                         "PROTECTION_VERIFIED_RECONCILIATION_PENDING")
        self.assertEqual(
            [call.args[0].endpoint_id for call in transport.call_args_list],
            ["FUTURES_ORDER_QUERY", "FUTURES_ORDER_CREATE",
             "FUTURES_ORDER_QUERY", "FUTURES_TRADES", "FUTURES_POSITION",
             "FUTURES_ALGO_QUERY", "FUTURES_ALGO_CREATE",
             "FUTURES_ALGO_QUERY"],
        )
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_FILLS_FEES_REPLAYED")
        self.assertEqual(private["stop"]["stage"], "BINANCE_STOP_RECONCILED")
        self.assertEqual(private["stop"]["algo_id"], 901)

        account = self._futures_account_for(self.intent["quantity"])
        funding = canonical_json([{
            "tranId": 501, "symbol": "ETHUSDT",
            "incomeType": "FUNDING_FEE", "income": "-0.005",
            "asset": "USDT", "time": 1787832000003,
        }]).encode("utf-8")
        active_algos = canonical_json([json.loads(algo)]).encode("utf-8")
        terminal_responses = tuple(BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, body, hashlib.sha256(body).hexdigest(), (),
        ) for body in (
            filled, trades, account, position, funding, active_algos,
        ))
        fresh = self.workspace.state()
        original_append = fresh.append

        class ReconciliationCrash(BaseException):
            pass

        def append_then_crash(**kwargs):
            event = original_append(**kwargs)
            if kwargs["event_type"] == "BINANCE_RECONCILIATION_INPUTS_CAPTURED":
                raise ReconciliationCrash()
            return event

        with patch.object(fresh, "append", side_effect=append_then_crash), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW + timedelta(seconds=1),
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_expected_stop", return_value=stop,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=terminal_responses,
        ) as terminal_transport:
            with self.assertRaises(ReconciliationCrash):
                run_challenger_replacement_binance_private_intent(
                    state=fresh, event_root=self.workspace.root,
                    intent=self.intent, preflight_capability=self.preflight,
                    activation=self.activation, credential=self.credential,
                    build_identity=self.workspace.build,
                )
        self.assertEqual(
            [call.args[0].endpoint_id
             for call in terminal_transport.call_args_list],
            ["FUTURES_ORDER_QUERY", "FUTURES_TRADES", "FUTURES_ACCOUNT",
             "FUTURES_POSITION", "FUTURES_INCOME",
             "FUTURES_OPEN_ALGO_ORDERS"],
        )
        private = fresh.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"],
                         "BINANCE_RECONCILIATION_INPUTS_CAPTURED")
        recovered = self.workspace.state()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW + timedelta(seconds=1),
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
        ) as recovery_transport:
            terminal = run_challenger_replacement_binance_private_intent(
                state=recovered, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        recovery_transport.assert_not_called()
        self.assertEqual(terminal["status"], "TERMINAL_RECONCILED")
        private = recovered.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_RECONCILIATION_SUCCEEDED")
        loaded = load_binance_reconciliation_bytes(base64.b64decode(
            private["reconciliation_bytes_base64"], validate=True,
        ))
        self.assertEqual(loaded["event_projection"]["funding"], "-0.005")
        self.assertEqual(
            loaded["event_projection"]["protective_stop_client_id_or_null"],
            stop["client_algo_id"],
        )
        capture_path = self.workspace.files.event_root / (
            f"{private['capture_event_sequence']:020d}.event.json"
        )
        displaced = self.workspace.files.base / "displaced-capture"
        capture_path.rename(displaced)
        capture_path.write_bytes(displaced.read_bytes())
        capture_path.chmod(0o600)
        before = (displaced.read_bytes(), displaced.lstat().st_ino,
                  displaced.lstat().st_mode, displaced.lstat().st_nlink)
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW + timedelta(seconds=1),
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            side_effect=AssertionError("transport must not run"),
        ) as transport, self.assertRaisesRegex(
            BinancePrivateRuntimeError,
            "BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID",
        ):
            run_challenger_replacement_binance_private_intent(
                state=self.workspace.state(), event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        transport.assert_not_called()
        after = (displaced.read_bytes(), displaced.lstat().st_ino,
                 displaced.lstat().st_mode, displaced.lstat().st_nlink)
        self.assertEqual(after, before)

    def test_first_partial_perpetual_fill_is_protected_before_return(self):
        self._use_perpetual_decision()
        absent, filled, trades, _position = self._futures_filled_documents(
            self.intent["quantity"]
        )
        order = json.loads(filled)
        order.update(executedQty="0.005", cumQuote="10", status="PARTIALLY_FILLED")
        partial = canonical_json(order).encode("utf-8")
        trade = json.loads(trades)[0]
        trade.update(qty="0.005", quoteQty="10", commission="0.004")
        trades = canonical_json([trade]).encode("utf-8")
        position = self._futures_position("-0.005")
        stop = self._futures_stop("0.005")
        algo = canonical_json({
            "algoId": 901, "clientAlgoId": stop["client_algo_id"],
            "algoType": "CONDITIONAL", "orderType": "STOP_MARKET",
            "symbol": "ETHUSDT", "side": "BUY", "positionSide": "BOTH",
            "quantity": "0.005", "triggerPrice": stop["trigger_price"],
            "workingType": "MARK_PRICE", "reduceOnly": True,
            "closePosition": False, "algoStatus": "NEW",
        }).encode("utf-8")
        documents = (
            ("RESPONSE_INVALID", 400, absent), ("ACKNOWLEDGED", 200, partial),
            ("QUERY_SUCCEEDED", 200, partial), ("QUERY_SUCCEEDED", 200, trades),
            ("QUERY_SUCCEEDED", 200, position), ("RESPONSE_INVALID", 400, absent),
            ("ACKNOWLEDGED", 200, algo), ("QUERY_SUCCEEDED", 200, algo),
        )
        responses = tuple(BinancePrivateTransportResult(
            kind, status, body, hashlib.sha256(body).hexdigest(), (),
        ) for kind, status, body in documents)
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_expected_stop", return_value=stop,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=responses,
        ) as transport:
            result = run_challenger_replacement_binance_private_intent(
                state=self.state, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        self.assertEqual(result["status"],
                         "PROTECTION_VERIFIED_RECONCILIATION_PENDING")
        self.assertEqual([call.args[0].endpoint_id for call in
                          transport.call_args_list][-3:], [
            "FUTURES_ALGO_QUERY", "FUTURES_ALGO_CREATE", "FUTURES_ALGO_QUERY",
        ])
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_FILLS_FEES_REPLAYED")
        self.assertEqual(private["stop"]["quantity"], "0.005")
        self.assertEqual(private["stop"]["stage"], "BINANCE_STOP_RECONCILED")

        larger = dict(order, executedQty="0.01", cumQuote="20",
                      status="PARTIALLY_FILLED")
        larger = canonical_json(larger).encode("utf-8")
        second_trade = dict(trade, id=402)
        larger_trades = canonical_json([trade, second_trade]).encode("utf-8")
        larger_position = self._futures_position("-0.01")
        candidate = self._futures_stop("0.01")
        candidate_algo = canonical_json({
            **json.loads(algo), "algoId": 902,
            "clientAlgoId": candidate["client_algo_id"], "quantity": "0.01",
            "triggerPrice": candidate["trigger_price"],
        }).encode("utf-8")
        canceled_old = canonical_json({
            **json.loads(algo), "algoStatus": "CANCELED",
        }).encode("utf-8")
        second_documents = (
            ("QUERY_SUCCEEDED", 200, larger),
            ("QUERY_SUCCEEDED", 200, larger_trades),
            ("QUERY_SUCCEEDED", 200, larger_position),
            ("RESPONSE_INVALID", 400, absent),
            ("ACKNOWLEDGED", 200, candidate_algo),
            ("QUERY_SUCCEEDED", 200, candidate_algo),
            ("QUERY_SUCCEEDED", 200, candidate_algo),
            ("ACKNOWLEDGED", 200, canceled_old),
            ("QUERY_SUCCEEDED", 200, canceled_old),
        )
        second_responses = tuple(BinancePrivateTransportResult(
            kind, status, body, hashlib.sha256(body).hexdigest(), (),
        ) for kind, status, body in second_documents)
        fresh = self.workspace.state()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_expected_stop", return_value=candidate,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=second_responses,
        ) as replacement_transport:
            replaced = run_challenger_replacement_binance_private_intent(
                state=fresh, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        self.assertEqual(replaced["status"],
                         "PROTECTION_VERIFIED_RECONCILIATION_PENDING")
        self.assertEqual([call.args[0].endpoint_id for call in
                          replacement_transport.call_args_list], [
            "FUTURES_ORDER_QUERY", "FUTURES_TRADES", "FUTURES_POSITION",
            "FUTURES_ALGO_QUERY", "FUTURES_ALGO_CREATE", "FUTURES_ALGO_QUERY",
            "FUTURES_ALGO_QUERY", "FUTURES_ALGO_CANCEL", "FUTURES_ALGO_QUERY",
        ])
        replaced_stop = fresh.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]["stop"]
        self.assertEqual(replaced_stop["client_algo_id"],
                         candidate["client_algo_id"])
        self.assertEqual(replaced_stop["quantity"], "0.01")
        self.assertEqual(replaced_stop["replacement"]["stage"],
                         "BINANCE_STOP_REPLACEMENT_SUCCEEDED")

    def test_fresh_retry_after_stop_send_started_queries_without_recreate(self):
        self._use_perpetual_decision()
        absent, filled, trades, position = self._futures_filled_documents(
            self.intent["quantity"]
        )
        stop = self._futures_stop(self.intent["quantity"])
        algo = canonical_json({
            "algoId": 901, "clientAlgoId": stop["client_algo_id"],
            "algoType": "CONDITIONAL", "orderType": "STOP_MARKET",
            "symbol": "ETHUSDT", "side": "BUY", "positionSide": "BOTH",
            "quantity": stop["quantity"], "triggerPrice": stop["trigger_price"],
            "workingType": "MARK_PRICE", "reduceOnly": True,
            "closePosition": False, "algoStatus": "NEW",
        }).encode("utf-8")
        initial = tuple(BinancePrivateTransportResult(
            kind, status, body, hashlib.sha256(body).hexdigest(), (),
        ) for kind, status, body in (
            ("RESPONSE_INVALID", 400, absent),
            ("ACKNOWLEDGED", 200, filled),
            ("QUERY_SUCCEEDED", 200, filled),
            ("QUERY_SUCCEEDED", 200, trades),
            ("QUERY_SUCCEEDED", 200, position),
            ("RESPONSE_INVALID", 400, absent),
        ))

        class SimulatedCrash(BaseException):
            pass

        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_expected_stop", return_value=stop,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            side_effect=(*initial, SimulatedCrash()),
        ):
            with self.assertRaises(SimulatedCrash):
                run_challenger_replacement_binance_private_intent(
                    state=self.state, event_root=self.workspace.root,
                    intent=self.intent, preflight_capability=self.preflight,
                    activation=self.activation, credential=self.credential,
                    build_identity=self.workspace.build,
                )
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(
            private["stop"]["stage"], "BINANCE_STOP_REQUEST_SEND_STARTED",
        )
        observed_position = BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, position,
            hashlib.sha256(position).hexdigest(), (),
        )
        observed = BinancePrivateTransportResult(
            "QUERY_SUCCEEDED", 200, algo, hashlib.sha256(algo).hexdigest(), (),
        )
        fresh = self.workspace.state()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW + timedelta(seconds=1),
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_expected_stop", return_value=stop,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            side_effect=(observed_position, observed),
        ) as transport:
            result = run_challenger_replacement_binance_private_intent(
                state=fresh, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        self.assertEqual(result["status"],
                         "PROTECTION_VERIFIED_RECONCILIATION_PENDING")
        self.assertEqual(
            [call.args[0].endpoint_id for call in transport.call_args_list],
            ["FUTURES_POSITION", "FUTURES_ALGO_QUERY"],
        )

    def test_fresh_retry_from_prepared_stop_rechecks_absence_and_resigns(self):
        self._use_perpetual_decision()
        absent, filled, trades, position = self._futures_filled_documents(
            self.intent["quantity"]
        )
        stop = self._futures_stop(self.intent["quantity"])
        algo = self._active_algo(stop)
        initial = tuple(BinancePrivateTransportResult(
            kind, status, body, hashlib.sha256(body).hexdigest(), (),
        ) for kind, status, body in (
            ("RESPONSE_INVALID", 400, absent),
            ("ACKNOWLEDGED", 200, filled),
            ("QUERY_SUCCEEDED", 200, filled),
            ("QUERY_SUCCEEDED", 200, trades),
            ("QUERY_SUCCEEDED", 200, position),
            ("RESPONSE_INVALID", 400, absent),
        ))

        class SimulatedCrash(BaseException):
            pass

        original_append = self.state.append

        def append_then_crash(**kwargs):
            event = original_append(**kwargs)
            if kwargs["event_type"] == "BINANCE_STOP_SIGNED_REQUEST_PREPARED":
                raise SimulatedCrash()
            return event

        with patch.object(self.state, "append", side_effect=append_then_crash), \
                patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "_wall_now", return_value=self.NOW,
                ), patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "_expected_stop", return_value=stop,
                ), patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "execute_binance_private_request", side_effect=initial,
                ):
            with self.assertRaises(SimulatedCrash):
                run_challenger_replacement_binance_private_intent(
                    state=self.state, event_root=self.workspace.root,
                    intent=self.intent, preflight_capability=self.preflight,
                    activation=self.activation, credential=self.credential,
                    build_identity=self.workspace.build,
                )
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(
            private["stop"]["stage"], "BINANCE_STOP_SIGNED_REQUEST_PREPARED",
        )
        durable_timestamp = private["stop"]["request_timestamp_ms"]
        results = (
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, position,
                hashlib.sha256(position).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "RESPONSE_INVALID", 400, absent,
                hashlib.sha256(absent).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "ACKNOWLEDGED", 200, algo,
                hashlib.sha256(algo).hexdigest(), (),
            ),
            BinancePrivateTransportResult(
                "QUERY_SUCCEEDED", 200, algo,
                hashlib.sha256(algo).hexdigest(), (),
            ),
        )
        fresh = self.workspace.state()
        fresh_time = PublicHttpResponse(
            status=200, final_url="https://fapi.binance.com/fapi/v1/time",
            headers={}, body=b'{"serverTime":1787832001000}',
            monotonic_rtt_ms=0,
            request_started_at="2026-08-27T12:00:01.000Z",
            response_received_at="2026-08-27T12:00:01.000Z",
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW + timedelta(seconds=1),
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_expected_stop", return_value=stop,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "open_fixed_public_request", return_value=fresh_time,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=results,
        ) as transport:
            result = run_challenger_replacement_binance_private_intent(
                state=fresh, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        self.assertEqual(result["status"],
                         "PROTECTION_VERIFIED_RECONCILIATION_PENDING")
        requests = [call.args[0] for call in transport.call_args_list]
        self.assertEqual([item.endpoint_id for item in requests], [
            "FUTURES_POSITION", "FUTURES_ALGO_QUERY",
            "FUTURES_ALGO_CREATE", "FUTURES_ALGO_QUERY",
        ])
        self.assertNotIn(
            ("timestamp=" + str(durable_timestamp)).encode("ascii"),
            requests[2].encoded_parameters,
        )

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
                preflight_capability=self.preflight,
                activation=self.activation,
                credential=self.credential,
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
        self.assertFalse(private["terminal"])
        self.assertTrue(private["unresolved_unknown"])
        from tests import test_challenger_replacement_canary_controller as canary
        unknown = next(event for event in replay["events"] if json.loads(
            event.final_bytes)["event_type"] == "BINANCE_ORDER_UNKNOWN")
        event_stat = os.stat(self.workspace.root.path /
                             ("%020d.event.json" % unknown.sequence))
        publication = {"sequence": unknown.sequence,
            "event_hash": unknown.event_hash, "device": event_stat.st_dev,
            "inode": event_stat.st_ino, "size": event_stat.st_size}
        fixture = canary.ChallengerReplacementCanaryControllerTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        start = fixture.start() | {"block_id": self.block_id}
        mark = fixture.stage_event(fixture.mark(
            "2026-09-02T04:00:00.000Z", "99", flat=False,
            hard_stop="UNRESOLVED_ECONOMIC_ORDER_UNKNOWN",
        ), stage="E0", block_id=self.block_id)
        mark["private_event_publication_or_null"] = publication
        _data, projected = fixture.project(
            fixture.ceremony_events() + (start, mark),
            now="2026-09-02T08:00:00.000Z", event_root=self.workspace.root,
        )
        self.assertEqual(projected["stage_block_or_null"]["hard_stop_or_null"],
                         "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN")
        event_path = self.workspace.root.path / ("%020d.event.json" % unknown.sequence)
        replacement = event_path.with_name("same-private-bytes-new-inode.tmp")
        replacement.write_bytes(event_path.read_bytes()); replacement.chmod(0o600)
        os.replace(replacement, event_path)
        with self.assertRaisesRegex(
            canary.ChallengerReplacementCanaryControllerError,
            "CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID",
        ):
            canary.project_challenger_replacement_canary(
                event_root=self.workspace.root,
                replacement_plan=self.workspace.plan, canary_plan=fixture.plan,
                build_identity=self.workspace.build,
                now="2026-09-02T08:00:00.000Z",
            )

    def test_unknown_fresh_process_queries_exact_client_id_and_never_resends(self):
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode("utf-8")
        unknown = canonical_json({
            "code": -1007, "msg": "Timeout waiting for response.",
        }).encode("utf-8")
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=(
                self._result("RESPONSE_INVALID", absent),
                self._result("UNKNOWN", unknown),
            ),
        ) as first_transport:
            run_challenger_replacement_binance_private_intent(
                state=self.state, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        filled = canonical_json({
            "symbol": "ETHUSDT", "orderId": 101,
            "clientOrderId": self.client_id, "price": "0",
            "origQty": "0.015", "executedQty": "0.015",
            "cummulativeQuoteQty": "30", "status": "FILLED",
            "timeInForce": "GTC", "type": "MARKET", "side": "BUY",
            "transactTime": 1787832000000,
        }).encode("utf-8")
        trades = canonical_json([{
            "symbol": "ETHUSDT", "id": 301, "orderId": 101,
            "qty": "0.015", "price": "2000", "quoteQty": "30",
            "commission": "0.03", "commissionAsset": "USDT",
            "time": 1787832000001, "isBuyer": True,
        }]).encode("utf-8")
        account = self._spot_account("0.015", "69.97")
        followup = tuple(self._result("QUERY_SUCCEEDED", body)
                         for body in (filled, trades, account))
        fresh = self.workspace.state()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=followup,
        ) as second_transport:
            result = run_challenger_replacement_binance_private_intent(
                state=fresh, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        endpoints = [call.args[0].endpoint_id for call in
                     first_transport.call_args_list + second_transport.call_args_list]
        self.assertEqual(endpoints.count("SPOT_ORDER_CREATE"), 1)
        self.assertEqual(endpoints[-3:], [
            "SPOT_ORDER_QUERY", "SPOT_TRADES", "SPOT_ACCOUNT",
        ])
        self.assertEqual(result["status"], "TERMINAL_RECONCILED")
        events = fresh._replay()["events"]
        self.assertIn("BINANCE_UNKNOWN_QUERY_OBSERVED",
                      [json.loads(event.final_bytes)["event_type"]
                       for event in events])

    def test_unknown_query_failure_remains_recoverable_without_resend(self):
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode("utf-8")
        unknown = canonical_json({
            "code": -1007, "msg": "Timeout waiting for response.",
        }).encode("utf-8")
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=(
                self._result("RESPONSE_INVALID", absent),
                self._result("UNKNOWN", unknown),
            ),
        ):
            run_challenger_replacement_binance_private_intent(
                state=self.state, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        fresh = self.workspace.state()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            return_value=self._result("UNKNOWN", unknown),
        ) as transport:
            result = run_challenger_replacement_binance_private_intent(
                state=fresh, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        self.assertEqual(result["status"], "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN")
        self.assertEqual([call.args[0].endpoint_id for call in
                          transport.call_args_list], ["SPOT_ORDER_QUERY"])
        private = fresh.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_ORDER_UNKNOWN")
        self.assertTrue(private["unresolved_unknown"])
        self.assertFalse(private["terminal"])

    def test_acknowledged_create_is_requeried_before_event_observation(self):
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode("utf-8")
        client_id = self.client_id
        order = canonical_json({
            "symbol": "ETHUSDT", "orderId": 101,
            "clientOrderId": client_id, "price": "0",
            "origQty": "0.015", "executedQty": "0",
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
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
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
            **json.loads(order), "executedQty": "0.015",
            "cummulativeQuoteQty": "30", "status": "FILLED",
        }).encode("utf-8")
        trade = canonical_json([{
            "symbol": "ETHUSDT", "id": 301, "orderId": 101,
            "qty": "0.015", "price": "2000", "quoteQty": "30",
            "commission": "0.03", "commissionAsset": "USDT",
            "time": 1787832000001, "isBuyer": True,
        }]).encode("utf-8")
        account = self._spot_account("0.015", "69.97")
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
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        self.assertEqual(
            [call.args[0].endpoint_id for call in transport.call_args_list],
            ["SPOT_ORDER_QUERY", "SPOT_TRADES", "SPOT_ACCOUNT"],
        )
        self.assertEqual(result["status"], "TERMINAL_RECONCILED")
        private = fresh.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"], "BINANCE_RECONCILIATION_SUCCEEDED")
        self.assertEqual(private["fill_ids"], [301])
        reconciliation = base64.b64decode(
            private["reconciliation_bytes_base64"], validate=True,
        )
        loaded = load_binance_reconciliation_bytes(reconciliation)
        self.assertEqual(loaded["reconciliation_id"],
                         private["reconciliation_id"])

        terminal = self.workspace.state()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW + timedelta(seconds=1),
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
        ) as transport:
            replayed = run_challenger_replacement_binance_private_intent(
                state=terminal, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        transport.assert_not_called()
        self.assertEqual(replayed["status"], "TERMINAL_RECONCILED")
        self.assertEqual(replayed["reconciliation_id"],
                         private["reconciliation_id"])

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
                    preflight_capability=self.preflight,
                    activation=self.activation,
                    credential=self.credential,
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
            "origQty": "0.015",
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
                preflight_capability=self.preflight,
                activation=self.activation,
                credential=self.credential,
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

    def test_fresh_retry_after_prepared_request_proves_absence_and_supersedes_time(self):
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
                    preflight_capability=self.preflight,
                    activation=self.activation,
                    credential=self.credential,
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
        fresh_time = PublicHttpResponse(
            status=200, final_url="https://api.binance.com/api/v3/time",
            headers={}, body=b'{"serverTime":1787832001000}',
            monotonic_rtt_ms=0,
            request_started_at="2026-08-27T12:00:01.000Z",
            response_received_at="2026-08-27T12:00:01.000Z",
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now",
            return_value=self.NOW + timedelta(seconds=1),
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "open_fixed_public_request", return_value=fresh_time,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            side_effect=(absent_result, self._result("UNKNOWN", unknown)),
        ) as transport:
            result = run_challenger_replacement_binance_private_intent(
                state=fresh,
                event_root=self.workspace.root,
                intent=self.intent,
                preflight_capability=self.preflight,
                activation=self.activation,
                credential=self.credential,
                build_identity=self.workspace.build,
            )
        self.assertEqual([call.args[0].endpoint_id for call in transport.call_args_list],
                         ["SPOT_ORDER_QUERY", "SPOT_ORDER_CREATE"])
        sent = transport.call_args_list[-1].args[0]
        self.assertEqual(sent.endpoint_id, "SPOT_ORDER_CREATE")
        self.assertNotEqual(sent.request_id, durable_request_id)
        self.assertIn(
            b"timestamp=1787832001000",
            sent.encoded_parameters,
        )
        self.assertEqual(result["status"], "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN")

    def test_prepared_request_is_not_sent_when_fresh_absence_is_unresolved(self):
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode("utf-8")

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
                    "_wall_now", return_value=self.NOW,
                ), patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "execute_binance_private_request",
                    return_value=self._result("RESPONSE_INVALID", absent),
                ):
            with self.assertRaises(SimulatedCrash):
                run_challenger_replacement_binance_private_intent(
                    state=self.state, event_root=self.workspace.root,
                    intent=self.intent, preflight_capability=self.preflight,
                    activation=self.activation, credential=self.credential,
                    build_identity=self.workspace.build,
                )
        fresh_time = PublicHttpResponse(
            status=200, final_url="https://api.binance.com/api/v3/time",
            headers={}, body=b'{"serverTime":1787832006001}',
            monotonic_rtt_ms=0,
            request_started_at="2026-08-27T12:00:06.001Z",
            response_received_at="2026-08-27T12:00:06.001Z",
        )
        fresh = self.workspace.state()
        unresolved = self._result(
            "TRANSIENT_QUERY_FAILURE", b'{"code":-1001}',
        )
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW + timedelta(milliseconds=6001),
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "open_fixed_public_request", return_value=fresh_time,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
            return_value=unresolved,
        ) as private_transport:
            result = run_challenger_replacement_binance_private_intent(
                state=fresh, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        self.assertEqual(result["status"], "PREPARED_SEND_ABSENCE_UNRESOLVED")
        private_transport.assert_called_once()
        self.assertEqual(
            private_transport.call_args.args[0].endpoint_id,
            "SPOT_ORDER_QUERY",
        )

    def test_crash_after_exact_reconciliation_resumes_without_network(self):
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode("utf-8")
        client_id = self.client_id
        filled = canonical_json({
            "symbol": "ETHUSDT", "orderId": 101,
            "clientOrderId": client_id, "price": "0",
            "origQty": "0.015", "executedQty": "0.015",
            "cummulativeQuoteQty": "30", "status": "FILLED",
            "timeInForce": "GTC", "type": "MARKET", "side": "BUY",
            "transactTime": 1787832000000,
        }).encode("utf-8")
        trades = canonical_json([{
            "symbol": "ETHUSDT", "id": 301, "orderId": 101,
            "qty": "0.015", "price": "2000", "quoteQty": "30",
            "commission": "0.03", "commissionAsset": "USDT",
            "time": 1787832000001, "isBuyer": True,
        }]).encode("utf-8")
        account = self._spot_account("0.015", "69.97")
        responses = tuple(
            BinancePrivateTransportResult(
                response_class, status, body,
                hashlib.sha256(body).hexdigest(), (),
            )
            for response_class, status, body in (
                ("RESPONSE_INVALID", 400, absent),
                ("ACKNOWLEDGED", 200, filled),
                ("QUERY_SUCCEEDED", 200, filled),
                ("QUERY_SUCCEEDED", 200, trades),
                ("QUERY_SUCCEEDED", 200, account),
            )
        )

        class SimulatedCrash(BaseException):
            pass

        original_append = self.state.append

        def append_then_crash(**kwargs):
            result = original_append(**kwargs)
            if kwargs["event_type"] == "BINANCE_POSITION_BALANCE_RECONCILED":
                raise SimulatedCrash()
            return result

        with patch.object(self.state, "append", side_effect=append_then_crash), \
                patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "_wall_now", return_value=self.NOW,
                ), patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "execute_binance_private_request", side_effect=responses,
                ):
            with self.assertRaises(SimulatedCrash):
                run_challenger_replacement_binance_private_intent(
                    state=self.state, event_root=self.workspace.root,
                    intent=self.intent, preflight_capability=self.preflight,
                    activation=self.activation, credential=self.credential,
                    build_identity=self.workspace.build,
                )
        private = self.state.replay()["opportunities"][
            self.workspace.opportunity_id
        ]["private"]
        self.assertEqual(private["stage"],
                         "BINANCE_POSITION_BALANCE_RECONCILED")

        fresh = self.workspace.state()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW + timedelta(seconds=1),
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request",
        ) as transport:
            result = run_challenger_replacement_binance_private_intent(
                state=fresh, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        transport.assert_not_called()
        self.assertEqual(result["status"], "TERMINAL_RECONCILED")
        self.assertEqual(
            fresh.replay()["opportunities"][self.workspace.opportunity_id]
            ["private"]["stage"],
            "BINANCE_RECONCILIATION_SUCCEEDED",
        )

    def test_terminal_and_fill_replay_crashes_requery_but_never_resend(self):
        absent = canonical_json({
            "code": -2013, "msg": "Order does not exist.",
        }).encode("utf-8")
        client_id = self.client_id
        filled = canonical_json({
            "symbol": "ETHUSDT", "orderId": 101,
            "clientOrderId": client_id, "price": "0",
            "origQty": "0.015", "executedQty": "0.015",
            "cummulativeQuoteQty": "30", "status": "FILLED",
            "timeInForce": "GTC", "type": "MARKET", "side": "BUY",
            "transactTime": 1787832000000,
        }).encode("utf-8")
        trades = canonical_json([{
            "symbol": "ETHUSDT", "id": 301, "orderId": 101,
            "qty": "0.015", "price": "2000", "quoteQty": "30",
            "commission": "0.03", "commissionAsset": "USDT",
            "time": 1787832000001, "isBuyer": True,
        }]).encode("utf-8")
        account = self._spot_account("0.015", "69.97")
        result = lambda kind, status, body: BinancePrivateTransportResult(
            kind, status, body, hashlib.sha256(body).hexdigest(), (),
        )

        class SimulatedCrash(BaseException):
            pass

        original_append = self.state.append

        def append_then_crash(**kwargs):
            publication = original_append(**kwargs)
            if kwargs["event_type"] == "BINANCE_ORDER_FILLED":
                raise SimulatedCrash()
            return publication

        first = (
            result("RESPONSE_INVALID", 400, absent),
            result("ACKNOWLEDGED", 200, filled),
            result("QUERY_SUCCEEDED", 200, filled),
            result("QUERY_SUCCEEDED", 200, trades),
            result("QUERY_SUCCEEDED", 200, account),
        )
        with patch.object(self.state, "append", side_effect=append_then_crash), \
                patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "_wall_now", return_value=self.NOW,
                ), patch(
                    "crypto_quant.challenger_replacement_binance_private_runtime."
                    "execute_binance_private_request", side_effect=first,
                ):
            with self.assertRaises(SimulatedCrash):
                run_challenger_replacement_binance_private_intent(
                    state=self.state, event_root=self.workspace.root,
                    intent=self.intent, preflight_capability=self.preflight,
                    activation=self.activation, credential=self.credential,
                    build_identity=self.workspace.build,
                )
        self.assertEqual(
            self.state.replay()["opportunities"][self.workspace.opportunity_id]
            ["private"]["stage"], "BINANCE_ORDER_FILLED",
        )

        fresh = self.workspace.state()
        second = (
            result("QUERY_SUCCEEDED", 200, filled),
            result("QUERY_SUCCEEDED", 200, trades),
            result("QUERY_SUCCEEDED", 200, account),
        )
        original_fresh_append = fresh.append

        def replay_then_crash(**kwargs):
            publication = original_fresh_append(**kwargs)
            if kwargs["event_type"] == "BINANCE_FILLS_FEES_REPLAYED":
                raise SimulatedCrash()
            return publication

        with patch.object(fresh, "append", side_effect=replay_then_crash), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=second,
        ) as transport:
            with self.assertRaises(SimulatedCrash):
                run_challenger_replacement_binance_private_intent(
                    state=fresh, event_root=self.workspace.root,
                    intent=self.intent, preflight_capability=self.preflight,
                    activation=self.activation, credential=self.credential,
                    build_identity=self.workspace.build,
                )
        self.assertEqual(
            [call.args[0].endpoint_id for call in transport.call_args_list],
            ["SPOT_ORDER_QUERY", "SPOT_TRADES", "SPOT_ACCOUNT"],
        )
        self.assertEqual(
            fresh.replay()["opportunities"][self.workspace.opportunity_id]
            ["private"]["stage"], "BINANCE_FILLS_FEES_REPLAYED",
        )
        terminal = self.workspace.state()
        with patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "_wall_now", return_value=self.NOW,
        ), patch(
            "crypto_quant.challenger_replacement_binance_private_runtime."
            "execute_binance_private_request", side_effect=(
                result("QUERY_SUCCEEDED", 200, filled),
                result("QUERY_SUCCEEDED", 200, trades),
                result("QUERY_SUCCEEDED", 200, account),
            ),
        ) as transport:
            completed = run_challenger_replacement_binance_private_intent(
                state=terminal, event_root=self.workspace.root,
                intent=self.intent, preflight_capability=self.preflight,
                activation=self.activation, credential=self.credential,
                build_identity=self.workspace.build,
            )
        self.assertEqual(
            [call.args[0].endpoint_id for call in transport.call_args_list],
            ["SPOT_ORDER_QUERY", "SPOT_TRADES", "SPOT_ACCOUNT"],
        )
        self.assertEqual(completed["status"], "TERMINAL_RECONCILED")


if __name__ == "__main__":
    unittest.main()
