import json
from importlib import resources
import subprocess
import sys
import unittest

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_binance_reconciliation import (
    BinanceReconciliationError,
    load_binance_reconciliation_bytes,
    reconcile_binance_private_state,
)


class BinanceReconciliationTests(unittest.TestCase):
    CLIENT = "cq77" + "1" * 32

    @staticmethod
    def body(value):
        return canonical_json(value).encode("utf-8")

    def setUp(self):
        facts = {
            "product": "PERPETUAL", "signed_quantity": "-0.025",
            "average_entry_price_or_null": "2000", "realized_pnl": "-0.01",
            "unrealized_pnl": "1", "cumulative_fee": "0.02",
            "funding": "-0.005", "wallet_balance": "100",
            "available_balance": "75", "open_order_count": 0,
            "protective_stop_client_id_or_null": self.CLIENT,
            "fill_ids": [401],
        }
        self.event = {**facts, "ledger_projection": dict(facts)}
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
            "order_documents": self.orders, "trade_documents": self.trades,
            "account_document": self.account,
            "position_document": self.position,
            "income_documents": self.income, "algo_documents": self.algos,
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
            event = {**self.event, key: value,
                     "ledger_projection": {
                         **self.event["ledger_projection"], key: value,
                     }}
            with self.subTest(key=key), self.assertRaisesRegex(
                BinanceReconciliationError, "VENUE_LOCAL_POSITION_MISMATCH"
            ):
                self.reconcile(event_projection=event)

    def test_ledger_mismatch_is_independently_detected(self):
        event = {**self.event, "ledger_projection": {
            **self.event["ledger_projection"], "cumulative_fee": "0.03",
        }}
        with self.assertRaisesRegex(
            BinanceReconciliationError, "BINANCE_LEDGER_PROJECTION_MISMATCH"
        ):
            self.reconcile(event_projection=event)

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

    def test_noncanonical_duplicate_key_extra_and_float_fail_before_projection(self):
        bad = (
            self.account + b"\n",
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


if __name__ == "__main__":
    unittest.main()
