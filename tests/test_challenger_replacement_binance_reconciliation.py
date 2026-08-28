import json
from importlib import resources
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator

import crypto_quant.challenger_replacement_binance_reconciliation as reconciliation_module
from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_binance_reconciliation import (
    BinanceReconciliationError,
    load_binance_reconciliation_bytes,
    reconcile_binance_private_state,
)
from crypto_quant.challenger_replacement_events import (
    ChallengerReplacementEventRootIdentity,
    build_challenger_replacement_event,
    open_challenger_replacement_event_root,
    publish_challenger_replacement_event,
)


def fixture_capture_publications():
    shared = {
        "capture_event_sequence": 1, "capture_event_hash": "1" * 64,
        "device": 1, "inode": 2, "uid": os.getuid(), "mode_octal": "0600",
        "link_count": 1, "event_size": 1024, "event_sha256": "2" * 64,
    }
    return {selector: {**shared, "payload_selector": selector,
                       "decoded_size": 64, "decoded_sha256": digit * 64}
            for selector, digit in zip(
                ("event_input", "ledger_input", "venue_input"), "345"
            )}


class BinanceReconciliationTests(unittest.TestCase):
    CLIENT = "cq77" + "1" * 32

    @staticmethod
    def body(value):
        return canonical_json(value).encode("utf-8")

    def spot_market(self, *, mark="2000", ask="2001", **asset_marks):
        return self.body({
            "symbol": "ETHUSDT", "mark_price": mark, "ask_price": ask,
            "asset_marks_usdt": {"ETH": mark, "USDT": "1", **asset_marks},
        })

    def setUp(self):
        self.publications = fixture_capture_publications()
        facts = {
            "product": "PERPETUAL", "signed_quantity": "-0.025",
            "average_entry_price_or_null": "2000", "realized_pnl": "-0.01",
            "unrealized_pnl": "1", "cumulative_fee": "0.02",
            "funding": "-0.005", "wallet_balance": "100",
            "available_balance": "75", "open_order_count": 0,
            "protective_stop_client_id_or_null": self.CLIENT,
            "fill_ids": [401],
        }
        self.event = facts
        self.ledger = dict(facts)
        self.orders = (self.body({
            "symbol": "ETHUSDT", "orderId": 202,
            "clientOrderId": "cq77" + "2" * 32, "avgPrice": "2000",
            "origQty": "0.025", "executedQty": "0.025", "cumQuote": "50",
            "status": "FILLED", "type": "MARKET", "side": "SELL",
            "positionSide": "BOTH", "reduceOnly": False,
            "updateTime": 1787832000000,
        }),)
        self.trades = (self.body({
            "symbol": "ETHUSDT", "id": 401, "orderId": 202,
            "qty": "0.025", "price": "2000", "quoteQty": "50",
            "commission": "0.02", "commissionAsset": "USDT",
            "realizedPnl": "-0.01", "time": 1787832000002,
            "buyer": False,
        }),)
        fixture = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "account-preflight-flat.json",
        ).read_text(encoding="utf-8"))
        account = fixture["FUTURES_ACCOUNT"]
        account["totalInitialMargin"] = "25"
        account["totalMaintMargin"] = "1"
        account["totalUnrealizedProfit"] = "1"
        account["totalMarginBalance"] = "101"
        account["totalPositionInitialMargin"] = "25"
        account["availableBalance"] = "75"
        account["maxWithdrawAmount"] = "75"
        account["assets"][0]["unrealizedProfit"] = "1"
        account["assets"][0]["marginBalance"] = "101"
        account["assets"][0]["maintMargin"] = "1"
        account["assets"][0]["initialMargin"] = "25"
        account["assets"][0]["positionInitialMargin"] = "25"
        account["assets"][0]["availableBalance"] = "75"
        account["assets"][0]["maxWithdrawAmount"] = "75"
        self.account = self.body(account)
        position = fixture["FUTURES_POSITION"]
        position[0].update(positionAmt="-0.025", entryPrice="2000",
                           markPrice="1960", unRealizedProfit="1", notional="-49",
                           isolatedMargin="25", isolatedWallet="25",
                           initialMargin="25", maintMargin="1",
                           positionInitialMargin="25")
        self.position = self.body(position)
        self.income = (self.body({
            "tranId": 501, "symbol": "ETHUSDT", "incomeType": "FUNDING_FEE",
            "income": "-0.005", "asset": "USDT", "time": 1787832000003,
        }),)
        self.algos = (self.body({
            "algoId": 901, "clientAlgoId": self.CLIENT,
            "symbol": "ETHUSDT", "algoStatus": "NEW", "side": "BUY",
            "positionSide": "BOTH", "quantity": "0.025",
            "triggerPrice": "2036.43", "workingType": "MARK_PRICE",
            "reduceOnly": True, "closePosition": False,
            "algoType": "CONDITIONAL", "orderType": "STOP_MARKET",
        }),)

    def reconcile(self, **changes):
        values = {
            "event_projection": self.event,
            "ledger_projection": self.ledger,
            "authorized_order": {
                "order_id": 202,
                "client_order_id": "cq77" + "2" * 32,
            },
            "authorized_stop_or_null": {
                "client_algo_id": self.CLIENT, "side": "BUY",
                "quantity": "0.025", "trigger_price": "2036.43",
                "reduce_only": True,
            },
            "order_documents": self.orders, "trade_documents": self.trades,
            "account_document": self.account,
            "position_document": self.position,
            "income_documents": self.income, "algo_documents": self.algos,
            "capture_publications": self.publications,
        }
        values.update(changes)
        return reconcile_binance_private_state(**values)

    def test_exact_three_way_agreement_is_canonical_and_strictly_replayable(self):
        data = self.reconcile()
        self.assertTrue(data.endswith(b"\n"))
        document = json.loads(data)
        self.assertEqual(document["status"], "BINANCE_PRIVATE_RECONCILIATION_MATCHED")
        self.assertEqual(document["event_projection"], document["venue_projection"])
        self.assertEqual(document["venue_projection"], document["ledger_projection"])
        loaded = load_binance_reconciliation_bytes(data)
        self.assertEqual(json.loads(canonical_json(loaded)), document)
        self.assertEqual(self.reconcile(), data)

    def test_capture_publications_are_required(self):
        with self.assertRaisesRegex(
            BinanceReconciliationError, "BINANCE_RECONCILIATION_INPUT_INVALID",
        ):
            self.reconcile(capture_publications=None)

    def test_spot_open_reconciles_full_account_at_fill_cost_basis(self):
        facts = {
            "product": "SPOT", "signed_quantity": "0.001",
            "average_entry_price_or_null": "2000", "realized_pnl": "0",
            "unrealized_pnl": "0.1", "cumulative_fee": "0.002",
            "funding": "0", "wallet_balance": "100.098",
            "available_balance": "97.998", "open_order_count": 0,
            "protective_stop_client_id_or_null": None, "fill_ids": [301],
        }
        account = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "account-preflight-flat.json",
        ).read_text(encoding="utf-8"))["SPOT_ACCOUNT"]
        balances = {item["asset"]: item for item in account["balances"]}
        balances["ETH"]["free"] = "0.001"
        balances["USDT"]["free"] = "97.998"
        order = json.dumps({
            "symbol": "ETHUSDT", "orderId": 101,
            "orderListId": -1,
            "clientOrderId": "cq77" + "6" * 32, "price": "0",
            "origQty": "0.001", "executedQty": "0.001",
            "cummulativeQuoteQty": "2", "status": "FILLED",
            "timeInForce": "GTC", "type": "MARKET", "side": "BUY",
            "time": 1787832000000, "updateTime": 1787832000001,
            "workingTime": 1787832000000, "isWorking": True,
            "stopPrice": "0", "icebergQty": "0", "origQuoteOrderQty": "0",
            "selfTradePreventionMode": "EXPIRE_MAKER",
        }, indent=2).encode()
        trade = json.dumps({
            "symbol": "ETHUSDT", "id": 301, "orderId": 101,
            "orderListId": -1,
            "qty": "0.001", "price": "2000", "quoteQty": "2",
            "commission": "0.002", "commissionAsset": "USDT",
            "time": 1787832000001, "isBuyer": True,
            "isMaker": False, "isBestMatch": True,
        }, indent=2).encode()
        data = reconcile_binance_private_state(
            event_projection=facts, ledger_projection=facts,
            authorized_order={"order_id": 101,
                              "client_order_id": "cq77" + "6" * 32},
            authorized_stop_or_null=None,
            order_documents=(order,), trade_documents=(trade,),
            account_document=self.body(account),
            position_document=self.spot_market(mark="2100", ask="2101"),
            income_documents=(), algo_documents=(),
            capture_publications=self.publications,
        )
        loaded = load_binance_reconciliation_bytes(data)
        self.assertEqual(
            json.loads(canonical_json(loaded["venue_projection"])), facts
        )
        self.assertEqual(loaded["status"],
                         "BINANCE_PRIVATE_RECONCILIATION_MATCHED")

    def test_spot_close_replays_previous_cost_basis_and_cumulative_fees(self):
        previous_facts = {
            "product": "SPOT", "signed_quantity": "0.001",
            "average_entry_price_or_null": "2000", "realized_pnl": "0",
            "unrealized_pnl": "0.1", "cumulative_fee": "0.002",
            "funding": "0", "wallet_balance": "100.098",
            "available_balance": "97.998", "open_order_count": 0,
            "protective_stop_client_id_or_null": None, "fill_ids": [301],
        }
        account = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "account-preflight-flat.json",
        ).read_text(encoding="utf-8"))["SPOT_ACCOUNT"]
        balances = {item["asset"]: item for item in account["balances"]}
        balances["ETH"]["free"] = "0.001"
        balances["USDT"]["free"] = "97.998"
        open_order = self.body({
            "symbol": "ETHUSDT", "orderId": 101,
            "clientOrderId": "cq77" + "6" * 32, "price": "0",
            "origQty": "0.001", "executedQty": "0.001",
            "cummulativeQuoteQty": "2", "status": "FILLED",
            "timeInForce": "GTC", "type": "MARKET", "side": "BUY",
            "transactTime": 1787832000000,
        })
        open_trade = self.body({
            "symbol": "ETHUSDT", "id": 301, "orderId": 101,
            "qty": "0.001", "price": "2000", "quoteQty": "2",
            "commission": "0.002", "commissionAsset": "USDT",
            "time": 1787832000001, "isBuyer": True,
        })
        previous = reconcile_binance_private_state(
            event_projection=previous_facts, ledger_projection=previous_facts,
            authorized_order={"order_id": 101,
                              "client_order_id": "cq77" + "6" * 32},
            authorized_stop_or_null=None,
            order_documents=(open_order,), trade_documents=(open_trade,),
            account_document=self.body(account),
            position_document=self.spot_market(mark="2100", ask="2101"),
            income_documents=(), algo_documents=(),
            capture_publications=self.publications,
        )

        balances["ETH"]["free"] = "0"
        balances["USDT"]["free"] = "100.0959"
        close_order = self.body({
            "symbol": "ETHUSDT", "orderId": 102,
            "clientOrderId": "cq77" + "7" * 32, "price": "0",
            "origQty": "0.001", "executedQty": "0.001",
            "cummulativeQuoteQty": "2.1", "status": "FILLED",
            "timeInForce": "GTC", "type": "MARKET", "side": "SELL",
            "transactTime": 1787846400000,
        })
        close_trade = self.body({
            "symbol": "ETHUSDT", "id": 302, "orderId": 102,
            "qty": "0.001", "price": "2100", "quoteQty": "2.1",
            "commission": "0.0021", "commissionAsset": "USDT",
            "time": 1787846400001, "isBuyer": False,
        })
        final = {
            "product": "SPOT", "signed_quantity": "0",
            "average_entry_price_or_null": None, "realized_pnl": "0.1",
            "unrealized_pnl": "0", "cumulative_fee": "0.0041",
            "funding": "0", "wallet_balance": "100.0959",
            "available_balance": "100.0959", "open_order_count": 0,
            "protective_stop_client_id_or_null": None,
            "fill_ids": [301, 302],
        }
        data = reconcile_binance_private_state(
            event_projection=final, ledger_projection=final,
            authorized_order={"order_id": 102,
                              "client_order_id": "cq77" + "7" * 32},
            authorized_stop_or_null=None,
            order_documents=(close_order,), trade_documents=(close_trade,),
            account_document=self.body(account),
            position_document=self.spot_market(mark="2100", ask="2101"),
            income_documents=(), algo_documents=(),
            previous_reconciliation_bytes_or_null=previous,
            capture_publications=self.publications,
        )
        self.assertEqual(
            json.loads(canonical_json(
                load_binance_reconciliation_bytes(data)["venue_projection"]
            )),
            final,
        )

    def test_spot_bnb_fee_is_converted_by_captured_mark(self):
        facts = {
            "product": "SPOT", "signed_quantity": "0.025",
            "average_entry_price_or_null": "2000", "realized_pnl": "0",
            "unrealized_pnl": "0", "cumulative_fee": "0.0108",
            "funding": "0", "wallet_balance": "159.9892",
            "available_balance": "50", "open_order_count": 0,
            "protective_stop_client_id_or_null": None, "fill_ids": [301],
        }
        account = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "account-preflight-flat.json",
        ).read_text(encoding="utf-8"))["SPOT_ACCOUNT"]
        balances = {item["asset"]: item for item in account["balances"]}
        balances["ETH"]["free"] = "0.025"
        balances["USDT"]["free"] = "50"
        account["balances"].append({"asset": "BNB", "free": "0.099982", "locked": "0"})
        order = self.body({
            "symbol": "ETHUSDT", "orderId": 101,
            "clientOrderId": "cq77" + "6" * 32, "price": "0",
            "origQty": "0.025", "executedQty": "0.025",
            "cummulativeQuoteQty": "50", "status": "FILLED",
            "timeInForce": "GTC", "type": "MARKET", "side": "BUY",
            "transactTime": 1787832000000,
        })
        trade = self.body({
            "symbol": "ETHUSDT", "id": 301, "orderId": 101,
            "qty": "0.025", "price": "2000", "quoteQty": "50",
            "commission": "0.000018", "commissionAsset": "BNB",
            "time": 1787832000001, "isBuyer": True,
        })
        data = reconcile_binance_private_state(
            event_projection=facts, ledger_projection=facts,
            authorized_order={"order_id": 101,
                              "client_order_id": "cq77" + "6" * 32},
            authorized_stop_or_null=None, order_documents=(order,),
            trade_documents=(trade,), account_document=self.body(account),
            position_document=self.spot_market(BNB="600"),
            income_documents=(), algo_documents=(),
            capture_publications=self.publications,
        )
        self.assertEqual(load_binance_reconciliation_bytes(data)[
            "venue_projection"]["cumulative_fee"], "0.0108")
        with self.assertRaisesRegex(
            BinanceReconciliationError, "BINANCE_RECONCILIATION_INPUT_INVALID",
        ):
            reconcile_binance_private_state(
                event_projection=facts, ledger_projection=facts,
                authorized_order={"order_id": 101,
                                  "client_order_id": "cq77" + "6" * 32},
                authorized_stop_or_null=None, order_documents=(order,),
                trade_documents=(trade,), account_document=self.body(account),
                position_document=self.spot_market(), income_documents=(),
                algo_documents=(), capture_publications=self.publications,
            )

    def test_perpetual_close_replays_cumulative_fee_funding_pnl_and_fills(self):
        previous = self.reconcile()
        fixture = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "account-preflight-flat.json",
        ).read_text(encoding="utf-8"))
        account = fixture["FUTURES_ACCOUNT"]
        account["totalWalletBalance"] = "102.481"
        account["totalMarginBalance"] = "102.481"
        account["availableBalance"] = "102.481"
        account["maxWithdrawAmount"] = "102.481"
        account["assets"][0].update(
            walletBalance="102.481", marginBalance="102.481",
            availableBalance="102.481", maxWithdrawAmount="102.481",
        )
        order = self.body({
            "symbol": "ETHUSDT", "orderId": 203,
            "clientOrderId": "cq77" + "3" * 32, "avgPrice": "1900",
            "origQty": "0.025", "executedQty": "0.025",
            "cumQuote": "47.5", "status": "FILLED", "type": "MARKET",
            "side": "BUY", "positionSide": "BOTH", "reduceOnly": True,
            "updateTime": 1787846400000,
        })
        trade = self.body({
            "symbol": "ETHUSDT", "id": 402, "orderId": 203,
            "qty": "0.025", "price": "1900", "quoteQty": "47.5",
            "commission": "0.019", "commissionAsset": "USDT",
            "realizedPnl": "2.5", "time": 1787846400001,
            "buyer": True,
        })
        final = {
            "product": "PERPETUAL", "signed_quantity": "0",
            "average_entry_price_or_null": None, "realized_pnl": "2.49",
            "unrealized_pnl": "0", "cumulative_fee": "0.039",
            "funding": "-0.005", "wallet_balance": "102.481",
            "available_balance": "102.481", "open_order_count": 0,
            "protective_stop_client_id_or_null": None,
            "fill_ids": [401, 402],
        }
        data = reconcile_binance_private_state(
            event_projection=final, ledger_projection=final,
            authorized_order={"order_id": 203,
                              "client_order_id": "cq77" + "3" * 32},
            authorized_stop_or_null=None,
            order_documents=(order,), trade_documents=(trade,),
            account_document=self.body(account),
            position_document=self.body(fixture["FUTURES_POSITION"]),
            income_documents=(), algo_documents=(),
            previous_reconciliation_bytes_or_null=previous,
            capture_publications=self.publications,
        )
        self.assertEqual(
            json.loads(canonical_json(
                load_binance_reconciliation_bytes(data)["venue_projection"]
            )), final,
        )

    def test_exact_duplicate_fill_and_funding_are_idempotent(self):
        self.assertEqual(
            self.reconcile(
                trade_documents=self.trades + self.trades,
                income_documents=self.income + self.income,
            ),
            self.reconcile(),
        )

    def test_conflicting_fill_or_funding_duplicate_fails_closed(self):
        conflicting_trade = self.body({
            **json.loads(self.trades[0]), "commission": "0.03",
        })
        conflicting_income = self.body({
            **json.loads(self.income[0]), "income": "-0.006",
        })
        for changes, reason in (
            ({"trade_documents": self.trades + (conflicting_trade,)},
             "BINANCE_RECONCILIATION_CONFLICTING_FILL"),
            ({"income_documents": self.income + (conflicting_income,)},
             "BINANCE_RECONCILIATION_CONFLICTING_FUNDING"),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(
                BinanceReconciliationError, reason
            ):
                self.reconcile(**changes)

    def test_each_economic_projection_mismatch_fails_closed(self):
        mutations = {
            "signed_quantity": "-0.024", "average_entry_price_or_null": "2001",
            "realized_pnl": "0", "unrealized_pnl": "2",
            "cumulative_fee": "0.03", "funding": "-0.006",
            "wallet_balance": "101", "available_balance": "74",
            "open_order_count": 1,
            "protective_stop_client_id_or_null": "cq77" + "9" * 32,
            "fill_ids": [402],
        }
        for key, value in mutations.items():
            event = {**self.event, key: value}
            with self.subTest(key=key), self.assertRaisesRegex(
                BinanceReconciliationError, "VENUE_LOCAL_POSITION_MISMATCH"
            ):
                self.reconcile(
                    event_projection=event,
                    ledger_projection={**self.ledger, key: value},
                )

    def test_ledger_mismatch_is_independently_detected(self):
        with self.assertRaisesRegex(
            BinanceReconciliationError, "BINANCE_LEDGER_PROJECTION_MISMATCH"
        ):
            self.reconcile(ledger_projection={
                **self.ledger, "cumulative_fee": "0.03",
            })

    def test_ledger_projection_is_a_separate_required_input(self):
        event = dict(self.event)
        with self.assertRaisesRegex(
            BinanceReconciliationError,
            "BINANCE_LEDGER_PROJECTION_MISMATCH",
        ):
            self.reconcile(
                event_projection=event,
                ledger_projection={**self.ledger,
                                   "cumulative_fee": "0.03"},
            )

    def test_trade_must_bind_authorized_order_and_client_order_ids(self):
        event = dict(self.event)
        authorization = {
            "order_id": 202,
            "client_order_id": "cq77" + "2" * 32,
        }
        for changed in (
            {"order_id": 999, "client_order_id": authorization["client_order_id"]},
            {"order_id": 202, "client_order_id": "cq77" + "8" * 32},
        ):
            with self.subTest(changed=changed), self.assertRaisesRegex(
                BinanceReconciliationError,
                "BINANCE_RECONCILIATION_INPUT_INVALID",
            ):
                self.reconcile(
                    event_projection=event,
                    ledger_projection=self.ledger,
                    authorized_order=changed,
                    authorized_stop_or_null={
                        "client_algo_id": self.CLIENT,
                        "side": "BUY", "quantity": "0.025",
                        "trigger_price": "2036.43", "reduce_only": True,
                    },
                )

    def test_stop_must_bind_every_authorized_protection_field(self):
        event = dict(self.event)
        stop = {
            "client_algo_id": self.CLIENT, "side": "BUY",
            "quantity": "0.025", "trigger_price": "2036.43",
            "reduce_only": True,
        }
        mutations = {
            "client_algo_id": "cq77" + "8" * 32,
            "side": "SELL", "quantity": "0.024",
            "trigger_price": "2036.44", "reduce_only": False,
        }
        for key, value in mutations.items():
            with self.subTest(key=key), self.assertRaisesRegex(
                BinanceReconciliationError,
                "PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP",
            ):
                self.reconcile(
                    event_projection=event,
                    ledger_projection=self.ledger,
                    authorized_order={
                        "order_id": 202,
                        "client_order_id": "cq77" + "2" * 32,
                    },
                    authorized_stop_or_null={**stop, key: value},
                )

    def test_missing_or_wrong_protection_while_exposed_is_hard_stop(self):
        for algos in ((), (self.body({**json.loads(self.algos[0]),
                                      "algoStatus": "CANCELED"}),)):
            with self.subTest(algos=algos), self.assertRaisesRegex(
                BinanceReconciliationError,
                "PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP",
            ):
                self.reconcile(algo_documents=algos)

    def test_open_order_and_position_or_balance_mismatch_are_detected(self):
        open_order = self.body({**json.loads(self.orders[0]), "status": "NEW"})
        wrong_position = json.loads(self.position)
        wrong_position[0]["positionAmt"] = "-0.02"
        wrong_position = self.body(wrong_position)
        wrong_account = json.loads(self.account)
        wrong_account["availableBalance"] = "74"
        wrong_account["assets"][0]["availableBalance"] = "74"
        wrong_account = self.body(wrong_account)
        replacement_algo = self.body({**json.loads(self.algos[0]),
                                      "quantity": "0.02"})
        for changes in (
            {"order_documents": (open_order,)},
            {"position_document": wrong_position,
             "algo_documents": (replacement_algo,)},
            {"account_document": wrong_account},
        ):
            with self.assertRaisesRegex(
                BinanceReconciliationError, "VENUE_LOCAL_POSITION_MISMATCH"
            ):
                self.reconcile(**changes)

    def test_duplicate_key_extra_and_float_fail_before_projection(self):
        bad = (
            b'{"totalWalletBalance":"100","totalWalletBalance":"100"}',
            self.body({**json.loads(self.account), "extra": True}),
            b'{"totalWalletBalance":100.0,"availableBalance":"99"}',
        )
        for account in bad:
            with self.subTest(account=account), self.assertRaisesRegex(
                BinanceReconciliationError, "BINANCE_RECONCILIATION_INPUT_INVALID"
            ):
                self.reconcile(account_document=account)

    def test_loader_rejects_rehashed_semantic_tampering(self):
        document = json.loads(self.reconcile())
        document["venue_projection"]["funding"] = "0"
        document.pop("reconciliation_id")
        from hashlib import sha256
        document["reconciliation_id"] = "binance_reconciliation_" + sha256(
            canonical_json(document).encode()
        ).hexdigest()
        with self.assertRaisesRegex(
            BinanceReconciliationError, "BINANCE_RECONCILIATION_ARTIFACT_INVALID"
        ):
            load_binance_reconciliation_bytes(
                (canonical_json(document) + "\n").encode()
            )

    def test_fresh_interpreter_loader_replays_exact_bytes(self):
        data = self.reconcile()
        code = (
            "import sys; from crypto_quant.challenger_replacement_binance_reconciliation "
            "import load_binance_reconciliation_bytes as load; "
            "print(load(sys.stdin.buffer.read())['status'])"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code], input=data, capture_output=True,
            check=False, timeout=5,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout,
                         b"BINANCE_PRIVATE_RECONCILIATION_MATCHED\n")

    def test_capture_publication_rejects_same_bytes_at_replacement_inode(self):
        temporary_parent = (
            "/private/tmp"
            if sys.platform == "darwin" and Path("/private/tmp").is_dir()
            else tempfile.gettempdir()
        )
        with tempfile.TemporaryDirectory(dir=temporary_parent) as temporary:
            directory = Path(temporary) / "events"
            directory.mkdir(mode=0o700)
            entry = directory.lstat()
            identity = ChallengerReplacementEventRootIdentity(
                str(directory), entry.st_dev, entry.st_ino, entry.st_uid, "0700",
            )
            with open_challenger_replacement_event_root(identity) as root:
                payload = {"intent_id": "intent-" + "1" * 64,
                           "capture_version": "1.0.0"}
                for selector in ("event_input", "ledger_input", "venue_input"):
                    data = canonical_json({"selector": selector}).encode()
                    payload[selector + "_bytes_base64"] = __import__(
                        "base64").b64encode(data).decode()
                    payload[selector + "_sha256"] = hashlib.sha256(data).hexdigest()
                event = build_challenger_replacement_event(
                    sequence=1,
                    event_type="BINANCE_RECONCILIATION_INPUTS_CAPTURED",
                    slot_id="ETHUSDT@2026-08-28T00:00:00.000Z",
                    worker_id="fixture-capture", recorded_at="2026-08-28T00:05:00.000Z",
                    previous_event_hash="0" * 64,
                    payload_bytes=canonical_json(payload).encode(),
                    plan_hash="1" * 64, build_identity_hash="2" * 64,
                    event_root=root,
                )
                publish_challenger_replacement_event(root, event)
                loaded = reconciliation_module.load_binance_reconciliation_capture(
                    event_root=root, capture_event_sequence=1,
                    capture_event_hash=event.event_hash,
                )
                final = directory / "00000000000000000001.event.json"
                sentinel = Path(temporary) / "sentinel"
                final.rename(sentinel)
                final.write_bytes(event.final_bytes)
                os.chmod(final, 0o600)
                before = (sentinel.read_bytes(), sentinel.lstat().st_ino,
                          sentinel.lstat().st_mode, sentinel.lstat().st_nlink)
                with self.assertRaisesRegex(
                    BinanceReconciliationError,
                    "BINANCE_RECONCILIATION_CAPTURE_UNTRUSTED",
                ):
                    reconciliation_module.verify_binance_reconciliation_capture(
                        event_root=root, publications=loaded["publications"],
                    )
                after = (sentinel.read_bytes(), sentinel.lstat().st_ino,
                         sentinel.lstat().st_mode, sentinel.lstat().st_nlink)
                self.assertEqual(after, before)

    def test_artifact_binds_three_capture_records_and_strict_loader_reopens_event(self):
        temporary_parent = (
            "/private/tmp"
            if sys.platform == "darwin" and Path("/private/tmp").is_dir()
            else tempfile.gettempdir()
        )
        with tempfile.TemporaryDirectory(dir=temporary_parent) as temporary:
            directory = Path(temporary) / "events"
            directory.mkdir(mode=0o700)
            entry = directory.lstat()
            identity = ChallengerReplacementEventRootIdentity(
                str(directory), entry.st_dev, entry.st_ino, entry.st_uid, "0700",
            )
            with open_challenger_replacement_event_root(identity) as root:
                payload = {"intent_id": "intent-" + "1" * 64,
                           "capture_version": "1.0.0"}
                for selector in ("event_input", "ledger_input", "venue_input"):
                    body = canonical_json({"selector": selector}).encode()
                    payload[selector + "_bytes_base64"] = __import__(
                        "base64").b64encode(body).decode()
                    payload[selector + "_sha256"] = hashlib.sha256(body).hexdigest()
                event = build_challenger_replacement_event(
                    sequence=1, event_type="BINANCE_RECONCILIATION_INPUTS_CAPTURED",
                    slot_id="ETHUSDT@2026-08-28T00:00:00.000Z",
                    worker_id="fixture-capture", recorded_at="2026-08-28T00:05:00.000Z",
                    previous_event_hash="0" * 64, payload_bytes=canonical_json(payload).encode(),
                    plan_hash="1" * 64, build_identity_hash="2" * 64, event_root=root,
                )
                publish_challenger_replacement_event(root, event)
                capture = reconciliation_module.load_binance_reconciliation_capture(
                    event_root=root, capture_event_sequence=1,
                    capture_event_hash=event.event_hash,
                )
                data = self.reconcile(
                    capture_publications=capture["publications"],
                )
                structural = load_binance_reconciliation_bytes(data)
                self.assertEqual(
                    set(structural["capture_publications"]),
                    {"event_input", "ledger_input", "venue_input"},
                )
                strict = reconciliation_module.load_binance_reconciliation_bytes_strict(
                    data, event_root=root,
                )
                self.assertEqual(strict["reconciliation_id"],
                                 structural["reconciliation_id"])
                schema = json.loads(resources.files("crypto_quant").joinpath(
                    "schemas",
                    "challenger-replacement-binance-reconciliation-v1.schema.json",
                ).read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)
                self.assertEqual(
                    list(Draft202012Validator(schema).iter_errors(json.loads(data))),
                    [],
                )


if __name__ == "__main__":
    unittest.main()
