import json
from importlib import resources
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_binance_private_contract import (
    BinancePrivateActivation,
)
from crypto_quant.challenger_replacement_binance_private_lifecycle import (
    BinancePrivateLifecycleError,
    apply_binance_order_observation,
    build_binance_order_intent_from_opportunity,
    derive_binance_client_order_id,
    prepare_binance_order_attempt,
)


class BinancePrivateLifecycleTests(unittest.TestCase):
    PLAN_HASH = "1" * 64
    BLOCK_ID = "e0-block-" + "2" * 64
    INTENT_ID = "replacement_intent_" + "3" * 64
    PREFLIGHT_ID = "binance_account_preflight_" + "4" * 64

    def setUp(self):
        self.activation = BinancePrivateActivation(
            activation_id="binance_private_activation_" + "5" * 64,
            build_identity={"release_tag": "v0.77.0"},
            configuration_sha256="6" * 64,
            account_approval_sha256="7" * 64,
            block_id=self.BLOCK_ID,
            stage="E0",
            capital_usdt="100",
            max_gross_exposure_usdt="50",
            max_leverage="0.5",
            expires_at="2026-08-28T00:00:00.000Z",
            production_activation=True,
        )
        self.preflight = {
            "status": "BINANCE_ACCOUNT_PREFLIGHT_VERIFIED_FLAT",
            "preflight_id": self.PREFLIGHT_ID,
            "configuration": {
                "position_mode": "ONE_WAY", "asset_mode": "SINGLE_ASSET",
                "symbol": "ETHUSDT", "margin_type": "ISOLATED",
                "leverage": 1, "auto_add_margin": False,
            },
        }
        self.projection = {
            "plan_hash": self.PLAN_HASH,
            "active_product_or_null": None,
            "unresolved_client_order_ids": [],
            "proven_absent_client_order_ids": [],
        }

    def intent(self, product="SPOT", action="OPEN_LONG", quantity="0.025"):
        return {
            "opportunity_id": "ETHUSDT@2026-08-27T12:00:00.000Z",
            "intent_id": self.INTENT_ID,
            "block_id": self.BLOCK_ID,
            "product": product,
            "action": action,
            "quantity": quantity,
            "attempt_ordinal": 1,
            "unsigned_intent_sha256": "8" * 64,
        }

    def prepare(self, **changes):
        intent = self.intent()
        intent.update(changes)
        return prepare_binance_order_attempt(
            intent=intent, projection=self.projection,
            preflight=self.preflight, activation=self.activation,
        )

    @staticmethod
    def body(value):
        return canonical_json(value).encode("utf-8")

    def spot_account(self, *, eth="0", usdt="100"):
        value = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "account-preflight-flat.json",
        ).read_text(encoding="utf-8"))["SPOT_ACCOUNT"]
        balances = {item["asset"]: item for item in value["balances"]}
        balances["ETH"]["free"] = eth
        balances["USDT"]["free"] = usdt
        return self.body(value)

    def futures_position(self, *, quantity="0", entry="0"):
        value = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "account-preflight-flat.json",
        ).read_text(encoding="utf-8"))["FUTURES_POSITION"]
        value[0]["positionAmt"] = quantity
        value[0]["entryPrice"] = entry
        return self.body(value)

    def spot_order(self, attempt, status="NEW", executed="0"):
        return self.body({
            "symbol": "ETHUSDT", "orderId": 101,
            "clientOrderId": attempt["venue_client_order_id"],
            "price": "0", "origQty": attempt["quantity"],
            "executedQty": executed, "cummulativeQuoteQty": "0",
            "status": status, "timeInForce": "GTC", "type": "MARKET",
            "side": attempt["side"], "transactTime": 1787832000000,
        })

    def futures_order(self, attempt, status="NEW", executed="0"):
        return self.body({
            "symbol": "ETHUSDT", "orderId": 202,
            "clientOrderId": attempt["venue_client_order_id"],
            "avgPrice": "0", "origQty": attempt["quantity"],
            "executedQty": executed, "cumQuote": "0", "status": status,
            "type": "MARKET", "side": attempt["side"],
            "positionSide": "BOTH", "reduceOnly": attempt["reduce_only"],
            "updateTime": 1787832000000,
        })

    def test_client_id_is_exact_deterministic_36_character_mapping(self):
        value = derive_binance_client_order_id(
            plan_hash=self.PLAN_HASH, block_id=self.BLOCK_ID,
            intent_id=self.INTENT_ID, attempt_ordinal=1, product="SPOT",
        )
        self.assertRegex(value, r"^cq77[0-9a-f]{32}$")
        self.assertEqual(len(value), 36)
        self.assertEqual(value, derive_binance_client_order_id(
            plan_hash=self.PLAN_HASH, block_id=self.BLOCK_ID,
            intent_id=self.INTENT_ID, attempt_ordinal=1, product="SPOT",
        ))
        self.assertNotEqual(value, derive_binance_client_order_id(
            plan_hash=self.PLAN_HASH, block_id=self.BLOCK_ID,
            intent_id=self.INTENT_ID, attempt_ordinal=2, product="SPOT",
        ))

    def test_private_intent_is_derived_from_verified_v076_opportunity(self):
        evidence = json.loads((Path(__file__).parent / "fixtures" /
                               "challenger_replacement_v076" /
                               "public-simulation-golden.json").read_text(
                                   encoding="utf-8"
                               ))
        slot = {
            "stage": "OPPORTUNITY_OBSERVED",
            "result_evidence": evidence,
        }
        intent = build_binance_order_intent_from_opportunity(
            slot=slot, activation=self.activation, attempt_ordinal=1,
        )
        self.assertEqual(
            {key: intent[key] for key in (
                "opportunity_id", "block_id", "product", "action",
                "quantity", "attempt_ordinal",
            )},
            {
                "opportunity_id": "ETHUSDT@2026-08-26T04:00:00.000Z",
                "block_id": self.BLOCK_ID, "product": "SPOT",
                "action": "OPEN_LONG", "quantity": "0.015",
                "attempt_ordinal": 1,
            },
        )
        self.assertRegex(intent["intent_id"], r"^replacement_intent_[0-9a-f]{64}$")
        self.assertRegex(intent["unsigned_intent_sha256"], r"^[0-9a-f]{64}$")

        altered = json.loads(canonical_json(evidence))
        altered["accounting"]["quantity"] = "0.016"
        with self.assertRaisesRegex(
            BinancePrivateLifecycleError, "BINANCE_ORDER_INTENT_INVALID"
        ):
            build_binance_order_intent_from_opportunity(
                slot={"stage": "OPPORTUNITY_OBSERVED",
                      "result_evidence": altered},
                activation=self.activation, attempt_ordinal=1,
            )

    def test_spot_and_futures_actions_map_to_exact_venue_intent(self):
        cases = (
            ("SPOT", "OPEN_LONG", "BUY", False, "SPOT_ORDER_QUERY"),
            ("SPOT", "CLOSE_LONG", "SELL", False, "SPOT_ORDER_QUERY"),
            ("PERPETUAL", "OPEN_SHORT", "SELL", False,
             "FUTURES_ORDER_QUERY"),
            ("PERPETUAL", "CLOSE_SHORT", "BUY", True,
             "FUTURES_ORDER_QUERY"),
        )
        for product, action, side, reduce_only, query in cases:
            with self.subTest(action=action):
                projection = dict(self.projection)
                if action.startswith("CLOSE_"):
                    projection["active_product_or_null"] = product
                attempt = prepare_binance_order_attempt(
                    intent=self.intent(product=product, action=action),
                    projection=projection, preflight=self.preflight,
                    activation=self.activation,
                )
                self.assertEqual(attempt["side"], side)
                self.assertIs(attempt["reduce_only"], reduce_only)
                self.assertEqual(attempt["required_first_endpoint"], query)
                self.assertFalse(attempt["send_permitted"])
                self.assertEqual(attempt["intent_id"], self.INTENT_ID)
                self.assertEqual(attempt["symbol"], "ETHUSDT")

    def test_mutual_exclusion_unknown_and_unproven_absence_block_new_send(self):
        for projection in (
            {**self.projection, "active_product_or_null": "PERPETUAL"},
            {**self.projection, "unresolved_client_order_ids": ["cq77" + "9" * 32]},
        ):
            with self.subTest(projection=projection):
                with self.assertRaises(BinancePrivateLifecycleError) as caught:
                    prepare_binance_order_attempt(
                        intent=self.intent(), projection=projection,
                        preflight=self.preflight, activation=self.activation,
                    )
                self.assertIn(caught.exception.reason_code, {
                    "BINANCE_PRODUCT_MUTUAL_EXCLUSION_BLOCKED",
                    "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN",
                })
        retry = self.intent(); retry["attempt_ordinal"] = 2
        with self.assertRaisesRegex(
            BinancePrivateLifecycleError, "BINANCE_ORDER_ABSENCE_NOT_PROVEN"
        ):
            prepare_binance_order_attempt(
                intent=retry, projection=self.projection,
                preflight=self.preflight, activation=self.activation,
            )

    def test_exact_proven_absent_retry_remains_query_first(self):
        retry = self.intent(); retry["attempt_ordinal"] = 2
        client_id = derive_binance_client_order_id(
            plan_hash=self.PLAN_HASH, block_id=self.BLOCK_ID,
            intent_id=self.INTENT_ID, attempt_ordinal=2, product="SPOT",
        )
        projection = {**self.projection,
                      "proven_absent_client_order_ids": [client_id]}
        attempt = prepare_binance_order_attempt(
            intent=retry, projection=projection, preflight=self.preflight,
            activation=self.activation,
        )
        self.assertTrue(attempt["send_permitted"])
        self.assertEqual(attempt["required_first_endpoint"], "SPOT_ORDER_QUERY")

    def test_ack_partial_fill_and_fee_events_are_exact_and_deduplicated(self):
        attempt = self.prepare()
        trades = (
            self.body({"symbol": "ETHUSDT", "id": 301, "orderId": 101,
                       "qty": "0.010", "price": "2000", "quoteQty": "20",
                       "commission": "0.02", "commissionAsset": "USDT",
                       "time": 1787832000001, "isBuyer": True}),
            self.body({"symbol": "ETHUSDT", "id": 302, "orderId": 101,
                       "qty": "0.005", "price": "2001", "quoteQty": "10.005",
                       "commission": "0.010005", "commissionAsset": "USDT",
                       "time": 1787832000002, "isBuyer": True}),
        )
        events = apply_binance_order_observation(
            attempt=attempt,
            order=self.spot_order(attempt, "PARTIALLY_FILLED", "0.015"),
            trades=trades + trades[:1],
            account=self.spot_account(eth="0.015", usdt="69.975"),
        )
        self.assertEqual([event["event_type"] for event in events], [
            "BINANCE_ORDER_ACKNOWLEDGED", "BINANCE_FILL_OBSERVED",
            "BINANCE_FILL_OBSERVED", "BINANCE_ORDER_PARTIALLY_FILLED",
        ])
        self.assertEqual(events[-1]["payload"]["cumulative_filled_quantity"],
                         "0.015")
        self.assertEqual(events[-1]["payload"]["cumulative_fee"], "0.030005")
        self.assertTrue(all(event["payload"]["intent_id"] == self.INTENT_ID
                            for event in events))

    def test_filled_and_cancel_fill_race_replay_late_fill(self):
        attempt = self.prepare(product="PERPETUAL", action="OPEN_SHORT")
        trade = self.body({
            "symbol": "ETHUSDT", "id": 401, "orderId": 202,
            "qty": "0.025", "price": "2000", "quoteQty": "50",
            "commission": "0.02", "commissionAsset": "USDT",
            "realizedPnl": "0", "time": 1787832000002,
            "buyer": False,
        })
        events = apply_binance_order_observation(
            attempt=attempt,
            order=self.futures_order(attempt, "CANCELED", "0.025"),
            trades=(trade,),
            account=self.futures_position(quantity="-0.025", entry="2000"),
        )
        self.assertEqual(events[-1]["event_type"], "BINANCE_ORDER_FILLED")
        self.assertEqual(events[-1]["payload"]["venue_terminal_status"],
                         "CANCELED")

    def test_reject_cancel_without_fill_and_unknown_are_distinct(self):
        attempt = self.prepare()
        account = self.spot_account()
        rejected = apply_binance_order_observation(
            attempt=attempt,
            order=self.body({"code": -2010, "msg": "rejected"}),
            trades=(), account=account,
        )
        canceled = apply_binance_order_observation(
            attempt=attempt, order=self.spot_order(attempt, "CANCELED", "0"),
            trades=(), account=account,
        )
        unknown = apply_binance_order_observation(
            attempt=attempt,
            order=self.body({"code": -1007, "msg": "timeout"}),
            trades=(), account=account,
        )
        self.assertEqual(rejected[-1]["event_type"], "BINANCE_ORDER_REJECTED")
        self.assertEqual(canceled[-1]["event_type"], "BINANCE_ORDER_CANCELED")
        self.assertEqual(unknown[-1]["event_type"], "BINANCE_ORDER_UNKNOWN")
        self.assertTrue(unknown[-1]["payload"]["blocks_new_risk"])

    def test_conflicting_duplicate_overfill_and_identity_mismatch_fail_closed(self):
        attempt = self.prepare()
        base = {"symbol": "ETHUSDT", "id": 301, "orderId": 101,
                "qty": "0.020", "price": "2000", "quoteQty": "40",
                "commission": "0.04", "commissionAsset": "USDT",
                "time": 1787832000001, "isBuyer": True}
        account = self.spot_account()
        cases = (
            ((self.body(base), self.body({**base, "price": "2001"})),
             "BINANCE_CONFLICTING_DUPLICATE_FILL"),
            ((self.body(base), self.body({**base, "id": 302, "qty": "0.010",
                                          "quoteQty": "20"})),
             "BINANCE_ORDER_OVERFILL"),
        )
        for trades, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(BinancePrivateLifecycleError, reason):
                    apply_binance_order_observation(
                        attempt=attempt,
                        order=self.spot_order(attempt, "FILLED", "0.025"),
                        trades=trades, account=account,
                    )
        wrong = json.loads(self.spot_order(attempt)); wrong["clientOrderId"] = "x"
        with self.assertRaisesRegex(
            BinancePrivateLifecycleError, "BINANCE_ORDER_IDENTITY_MISMATCH"
        ):
            apply_binance_order_observation(
                attempt=attempt, order=self.body(wrong), trades=(),
                account=account,
            )

    def test_noncanonical_duplicate_or_extra_documents_fail_closed(self):
        attempt = self.prepare()
        order = self.spot_order(attempt)
        for bad in (order + b"\n", b'{"status":"NEW","status":"NEW"}', b"[]"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(
                    BinancePrivateLifecycleError,
                    "BINANCE_ORDER_OBSERVATION_INVALID",
                ):
                    apply_binance_order_observation(
                        attempt=attempt, order=bad, trades=(),
                        account=self.spot_account(),
                    )

    def test_simplified_account_wrappers_are_not_accepted_as_venue_responses(self):
        cases = (
            (self.prepare(), self.body({"balances": []})),
            (self.prepare(product="PERPETUAL", action="OPEN_SHORT"),
             self.body({"positions": []})),
        )
        for attempt, account in cases:
            order = (self.spot_order(attempt) if attempt["product"] == "SPOT"
                     else self.futures_order(attempt))
            with self.subTest(product=attempt["product"]), self.assertRaisesRegex(
                BinancePrivateLifecycleError,
                "BINANCE_ORDER_OBSERVATION_INVALID",
            ):
                apply_binance_order_observation(
                    attempt=attempt, order=order, trades=(), account=account,
                )

    def test_tampered_attempt_and_impossible_venue_status_fail_closed(self):
        original = self.prepare()
        mutations = (
            ("side", "SELL"), ("reduce_only", True),
            ("quantity", "0.0250"), ("required_first_endpoint", "FUTURES_ORDER_QUERY"),
            ("send_permitted", "false"),
        )
        for key, value in mutations:
            attempt = {**original, key: value}
            with self.subTest(key=key):
                with self.assertRaisesRegex(
                    BinancePrivateLifecycleError,
                    "BINANCE_ORDER_OBSERVATION_INVALID",
                ):
                    apply_binance_order_observation(
                        attempt=attempt, order=self.spot_order(original),
                        trades=(), account=self.spot_account(),
                    )
        with self.assertRaisesRegex(
            BinancePrivateLifecycleError, "BINANCE_ORDER_FILL_REPLAY_MISMATCH"
        ):
            apply_binance_order_observation(
                attempt=original,
                order=self.spot_order(original, "FILLED", "0"), trades=(),
                account=self.spot_account(),
            )

    def test_futures_negative_realized_pnl_is_preserved(self):
        attempt = self.prepare(product="PERPETUAL", action="OPEN_SHORT")
        trade = self.body({
            "symbol": "ETHUSDT", "id": 501, "orderId": 202,
            "qty": "0.025", "price": "2000", "quoteQty": "50",
            "commission": "0.02", "commissionAsset": "USDT",
            "realizedPnl": "-0.01", "time": 1787832000002,
            "buyer": False,
        })
        events = apply_binance_order_observation(
            attempt=attempt,
            order=self.futures_order(attempt, "FILLED", "0.025"),
            trades=(trade,),
            account=self.futures_position(quantity="-0.025", entry="2000"),
        )
        self.assertEqual(events[1]["payload"]["realized_pnl"], "-0.01")

    def test_normalized_events_match_closed_schema_and_fixed_fixtures(self):
        schema = json.loads(resources.files("crypto_quant").joinpath(
            "schemas", "challenger-replacement-binance-private-event-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        fixture_root = resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077"
        )
        fixture = json.loads(fixture_root.joinpath(
            "private-order-observations.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(set(fixture), {"ACK", "PARTIAL", "FILL", "CANCEL", "UNKNOWN"})
        self.assertEqual(fixture["ACK"]["status"], "NEW")
        self.assertEqual(fixture["PARTIAL"]["status"], "PARTIALLY_FILLED")
        self.assertEqual(fixture["FILL"]["status"], "FILLED")
        self.assertEqual(fixture["CANCEL"]["status"], "CANCELED")
        self.assertEqual(fixture["UNKNOWN"]["code"], -1007)
        attempt = self.prepare()
        observed = apply_binance_order_observation(
            attempt=attempt, order=self.body({
                **fixture["ACK"],
                "clientOrderId": attempt["venue_client_order_id"],
                "origQty": attempt["quantity"],
            }), trades=(), account=self.spot_account(),
        )
        validator = Draft202012Validator(schema)
        for event in observed:
            envelope = {
                "$schema": "./challenger-replacement-binance-private-event-v1.schema.json",
                "schema_version": "1.0.0",
                "event_type": event["event_type"],
                "opportunity_id": attempt["opportunity_id"],
                "payload": event["payload"],
            }
            self.assertEqual(list(validator.iter_errors(envelope)), [])


if __name__ == "__main__":
    unittest.main()
