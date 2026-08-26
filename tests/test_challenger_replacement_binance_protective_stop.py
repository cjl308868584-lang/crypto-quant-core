import json
from importlib import resources
import unittest

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_binance_private_lifecycle import (
    BinancePrivateLifecycleError,
    prepare_binance_protective_stop,
    reconcile_binance_protective_stop,
)


class BinanceProtectiveStopTests(unittest.TestCase):
    IDENTITY = {
        "plan_hash": "1" * 64,
        "block_id": "e0-block-" + "2" * 64,
        "intent_id": "replacement_intent_" + "3" * 64,
    }

    @staticmethod
    def body(value):
        return canonical_json(value).encode("utf-8")

    def prepare(self, quantity="0.025", trigger="2036.43"):
        return prepare_binance_protective_stop(
            short_quantity=quantity, trigger_price=trigger,
            intent_identity=self.IDENTITY,
        )

    def position(self, quantity="-0.025"):
        return self.body({
            "symbol": "ETHUSDT", "positionSide": "BOTH",
            "positionAmt": quantity, "entryPrice": "2000",
        })

    def algo(self, expected, status="NEW", **changes):
        value = {
            "algoId": 901, "clientAlgoId": expected["client_algo_id"],
            "algoType": "CONDITIONAL", "orderType": "STOP_MARKET",
            "symbol": "ETHUSDT", "side": "BUY", "positionSide": "BOTH",
            "quantity": expected["quantity"],
            "triggerPrice": expected["trigger_price"],
            "workingType": "MARK_PRICE", "reduceOnly": True,
            "closePosition": False, "algoStatus": status,
        }
        value.update(changes)
        return self.body(value)

    def test_prepare_is_exact_reduce_only_mark_price_conditional(self):
        expected = self.prepare()
        self.assertEqual(expected, {
            "protected_intent_id": self.IDENTITY["intent_id"],
            "symbol": "ETHUSDT", "algo_type": "CONDITIONAL",
            "order_type": "STOP_MARKET", "side": "BUY",
            "position_side": "BOTH", "working_type": "MARK_PRICE",
            "quantity": "0.025", "trigger_price": "2036.43",
            "reduce_only": True, "close_position": False,
            "client_algo_id": expected["client_algo_id"],
            "required_first_endpoint": "FUTURES_ALGO_QUERY",
            "send_permitted": False,
        })
        self.assertRegex(expected["client_algo_id"], r"^cq77[0-9a-f]{32}$")
        self.assertEqual(len(expected["client_algo_id"]), 36)

    def test_exposed_short_requires_exact_confirmed_stop(self):
        expected = self.prepare()
        result = reconcile_binance_protective_stop(
            position=self.position(), algo_order=self.algo(expected),
            expected=expected,
        )
        self.assertEqual(result, {
            "status": "BINANCE_PROTECTIVE_STOP_VERIFIED",
            "exposed": True, "new_risk_blocked": False,
            "client_algo_id": expected["client_algo_id"], "algo_id": 901,
            "quantity": "0.025", "trigger_price": "2036.43",
        })

    def test_partial_entry_requires_stop_quantity_to_match_current_exposure(self):
        expected = self.prepare(quantity="0.01")
        result = reconcile_binance_protective_stop(
            position=self.position("-0.01"), algo_order=self.algo(expected),
            expected=expected,
        )
        self.assertEqual(result["status"], "BINANCE_PROTECTIVE_STOP_VERIFIED")
        wrong = self.algo(expected, quantity="0.025")
        with self.assertRaisesRegex(
            BinancePrivateLifecycleError,
            "PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP",
        ):
            reconcile_binance_protective_stop(
                position=self.position("-0.01"), algo_order=wrong,
                expected=expected,
            )

    def test_wrong_side_trigger_type_or_position_mode_fails_closed(self):
        expected = self.prepare()
        mutations = (
            {"side": "SELL"}, {"triggerPrice": "2036.44"},
            {"workingType": "CONTRACT_PRICE"}, {"orderType": "LIMIT"},
            {"positionSide": "SHORT"}, {"reduceOnly": False},
            {"closePosition": True}, {"clientAlgoId": "cq77" + "9" * 32},
        )
        for change in mutations:
            with self.subTest(change=change):
                with self.assertRaisesRegex(
                    BinancePrivateLifecycleError,
                    "PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP",
                ):
                    reconcile_binance_protective_stop(
                        position=self.position(),
                        algo_order=self.algo(expected, **change),
                        expected=expected,
                    )

    def test_rejected_canceled_missing_or_lost_ack_while_exposed_is_hard_stop(self):
        expected = self.prepare()
        candidates = (
            self.algo(expected, status="CANCELED"),
            self.algo(expected, status="REJECTED"),
            self.body({"code": -1007, "msg": "timeout"}),
            self.body({"code": -2013, "msg": "order does not exist"}),
        )
        for document in candidates:
            with self.subTest(document=document):
                with self.assertRaisesRegex(
                    BinancePrivateLifecycleError,
                    "PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP",
                ):
                    reconcile_binance_protective_stop(
                        position=self.position(), algo_order=document,
                        expected=expected,
                    )

    def test_flat_position_requires_orphan_stop_cleanup(self):
        expected = self.prepare()
        result = reconcile_binance_protective_stop(
            position=self.position("0"),
            algo_order=self.algo(expected, status="CANCELED"),
            expected=expected,
        )
        self.assertEqual(result, {
            "status": "BINANCE_FLAT_STOP_CLEANED",
            "exposed": False, "new_risk_blocked": False,
            "client_algo_id": expected["client_algo_id"], "algo_id": 901,
            "quantity": "0", "trigger_price": "2036.43",
        })
        with self.assertRaisesRegex(
            BinancePrivateLifecycleError, "BINANCE_FLAT_ORPHAN_STOP_ACTIVE"
        ):
            reconcile_binance_protective_stop(
                position=self.position("0"), algo_order=self.algo(expected),
                expected=expected,
            )

    def test_no_gap_replacement_requires_new_verified_before_old_cancel(self):
        expected = self.prepare(quantity="0.02")
        result = reconcile_binance_protective_stop(
            position=self.position("-0.02"), algo_order=self.algo(expected),
            expected=expected,
        )
        self.assertEqual(result["status"], "BINANCE_PROTECTIVE_STOP_VERIFIED")
        self.assertFalse(result["new_risk_blocked"])
        # The caller may append STARTED only after this proof, then cancel old.
        self.assertEqual(result["client_algo_id"], expected["client_algo_id"])

    def test_noncanonical_duplicate_extra_and_invalid_prepare_fail_closed(self):
        expected = self.prepare()
        bad_documents = (
            self.algo(expected) + b"\n",
            b'{"algoId":1,"algoId":1}',
            self.body({**json.loads(self.algo(expected)), "extra": True}),
        )
        for document in bad_documents:
            with self.subTest(document=document):
                with self.assertRaises(BinancePrivateLifecycleError):
                    reconcile_binance_protective_stop(
                        position=self.position(), algo_order=document,
                        expected=expected,
                    )
        for quantity, trigger in (("0", "2036.43"), ("-1", "2036.43"),
                                  ("0.01", "NaN")):
            with self.assertRaisesRegex(
                BinancePrivateLifecycleError, "BINANCE_STOP_INTENT_INVALID"
            ):
                self.prepare(quantity, trigger)

    def test_stop_intent_and_reconciliation_match_private_event_schema(self):
        schema = json.loads(resources.files("crypto_quant").joinpath(
            "schemas", "challenger-replacement-binance-private-event-v1.schema.json"
        ).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        expected = self.prepare()
        reconciled = reconcile_binance_protective_stop(
            position=self.position(), algo_order=self.algo(expected),
            expected=expected,
        )
        for event_type, payload in (
            ("BINANCE_STOP_INTENT_AUTHORIZED", expected),
            ("BINANCE_STOP_RECONCILED", reconciled),
        ):
            envelope = {
                "$schema": "./challenger-replacement-binance-private-event-v1.schema.json",
                "schema_version": "1.0.0", "event_type": event_type,
                "opportunity_id": "ETHUSDT@2026-08-27T12:00:00.000Z",
                "payload": payload,
            }
            self.assertEqual(list(validator.iter_errors(envelope)), [])


if __name__ == "__main__":
    unittest.main()
