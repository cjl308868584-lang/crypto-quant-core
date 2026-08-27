from dataclasses import replace
from importlib import resources
import json
from types import SimpleNamespace
import unittest

from crypto_quant.challenger_replacement_binance_private_protocol import (
    BinancePrivateRequest,
    build_binance_private_request,
    classify_binance_private_response,
    compute_binance_hmac_sha256,
    observe_binance_server_time,
    sign_binance_private_request,
    validate_binance_request_time,
)


class BinancePrivateProtocolTests(unittest.TestCase):
    def test_server_time_evidence_is_product_bound_and_midpoint_derived(self):
        calls = []
        clocks = iter((10_000, 10_200))

        def transport(request):
            calls.append(request.endpoint_id)
            return SimpleNamespace(
                response_class="QUERY_SUCCEEDED",
                body=b'{"serverTime":10150}',
            )

        evidence = observe_binance_server_time(
            product="SPOT", transport=transport,
            local_clock=lambda: next(clocks),
        )

        self.assertEqual(calls, ["SPOT_SERVER_TIME"])
        self.assertEqual(
            (evidence.product, evidence.local_before_ms,
             evidence.server_time_ms, evidence.local_after_ms,
             evidence.midpoint_ms, evidence.skew_ms),
            ("SPOT", 10_000, 10_150, 10_200, 10_100, 50),
        )

    def test_server_time_rejects_wrong_product_and_excessive_round_trip(self):
        def transport(_request):
            return SimpleNamespace(
                response_class="QUERY_SUCCEEDED",
                body=b'{"serverTime":10000}',
            )

        for product, clocks in (
            ("MARGIN", iter((10_000, 10_001))),
            ("PERPETUAL", iter((10_000, 11_001))),
        ):
            with self.subTest(product=product), self.assertRaisesRegex(
                ValueError, "BINANCE_SERVER_TIME_INVALID"
            ):
                observe_binance_server_time(
                    product=product, transport=transport,
                    local_clock=lambda: next(clocks),
                )

    def _mutating_request(self):
        return build_binance_private_request(
            "SPOT_ORDER_CREATE",
            {
                "symbol": "ETHUSDT",
                "side": "BUY",
                "type": "MARKET",
                "quantity": "0.001",
                "newClientOrderId": "cq77" + "0" * 32,
                "newOrderRespType": "FULL",
            },
            timestamp_ms=10000,
        )

    def test_official_spot_hmac_known_answer(self):
        fixture = json.loads(
            resources.files("crypto_quant").joinpath(
                "fixtures", "challenger-replacement-v077",
                "spot-hmac-known-answer.json",
            ).read_text(encoding="utf-8")
        )
        request = BinancePrivateRequest(
            request_id="binance_private_request_" + "0" * 64,
            endpoint_id="SPOT_ORDER_CREATE",
            host="api.binance.com",
            method="POST",
            path="/api/v3/order",
            encoded_parameters=fixture["payload_ascii"].encode("ascii"),
            parameter_names=(
                "symbol", "side", "type", "timeInForce", "quantity",
                "price", "recvWindow", "timestamp",
            ),
            mutating=True,
        )
        signature = compute_binance_hmac_sha256(
            request.encoded_parameters,
            fixture["illustrative_public_hmac_key_ascii"].encode("ascii"),
        )
        self.assertEqual(
            signature,
            fixture["expected_hmac_sha256_lowerhex"],
        )

    def test_tampered_request_identity_is_rejected_before_signing(self):
        request = build_binance_private_request(
            "SPOT_ORDER_QUERY",
            {
                "symbol": "ETHUSDT",
                "origClientOrderId": "cq77" + "e" * 32,
            },
            timestamp_ms=1787788800000,
        )
        tampered = replace(request, host="evil.invalid")
        with self.assertRaisesRegex(ValueError, "BINANCE_REQUEST_INVALID"):
            sign_binance_private_request(tampered, b"B" * 32)
        with self.assertRaisesRegex(ValueError, "BINANCE_REQUEST_INVALID"):
            classify_binance_private_response(
                tampered, status=200, body=b"{}", headers={}
            )

    def test_query_request_encoding_is_mapping_order_independent(self):
        client_id = "cq77" + "1" * 32
        first = build_binance_private_request(
            "SPOT_ORDER_QUERY",
            {"symbol": "ETHUSDT", "origClientOrderId": client_id},
            timestamp_ms=1787788800000,
        )
        second = build_binance_private_request(
            "SPOT_ORDER_QUERY",
            {"origClientOrderId": client_id, "symbol": "ETHUSDT"},
            timestamp_ms=1787788800000,
        )
        expected = (
            "origClientOrderId=" + client_id
            + "&recvWindow=5000&symbol=ETHUSDT&timestamp=1787788800000"
        ).encode("ascii")
        self.assertEqual(first, second)
        self.assertEqual(first.encoded_parameters, expected)
        self.assertEqual(
            first.parameter_names,
            ("origClientOrderId", "recvWindow", "symbol", "timestamp"),
        )
        self.assertEqual(
            (first.host, first.method, first.path, first.mutating),
            ("api.binance.com", "GET", "/api/v3/order", False),
        )

    def test_public_time_and_metadata_requests_never_gain_signed_parameters(self):
        clock = build_binance_private_request(
            "SPOT_SERVER_TIME", {}, timestamp_ms=0
        )
        mark = build_binance_private_request(
            "FUTURES_MARK_PRICE", {"symbol": "ETHUSDT"}, timestamp_ms=0
        )
        self.assertEqual((clock.encoded_parameters, clock.parameter_names), (b"", ()))
        self.assertEqual(
            (mark.encoded_parameters, mark.parameter_names),
            (b"symbol=ETHUSDT", ("symbol",)),
        )
        for parameters in (
            {"symbol": "ETHUSDT", "origClientOrderId": "cq77" + "1" * 32,
             "url": "https://example.invalid"},
            {"symbol": "BTCUSDT", "origClientOrderId": "cq77" + "1" * 32},
            {"symbol": "ETHUSDT", "origClientOrderId": 7},
        ):
            with self.subTest(parameters=parameters):
                with self.assertRaisesRegex(ValueError, "BINANCE_REQUEST_INVALID"):
                    build_binance_private_request(
                        "SPOT_ORDER_QUERY", parameters, timestamp_ms=1787788800000
                    )

    def test_every_frozen_endpoint_has_one_bounded_request_shape(self):
        client_id = "cq77" + "c" * 32
        parameters = {
            "SPOT_SERVER_TIME": {},
            "SPOT_EXCHANGE_INFO": {"symbol": "ETHUSDT"},
            "FUTURES_SERVER_TIME": {},
            "FUTURES_EXCHANGE_INFO": {},
            "FUTURES_MARK_PRICE": {"symbol": "ETHUSDT"},
            "API_RESTRICTIONS": {},
            "API_TRADING_STATUS": {},
            "SPOT_ACCOUNT": {},
            "SPOT_OPEN_ORDERS": {"symbol": "ETHUSDT"},
            "SPOT_ORDER_QUERY": {
                "symbol": "ETHUSDT", "origClientOrderId": client_id,
            },
            "SPOT_TRADES": {"symbol": "ETHUSDT", "orderId": "101"},
            "FUTURES_POSITION_MODE": {},
            "FUTURES_MULTI_ASSET_MODE": {},
            "FUTURES_SYMBOL_CONFIG": {"symbol": "ETHUSDT"},
            "FUTURES_ACCOUNT": {},
            "FUTURES_POSITION": {"symbol": "ETHUSDT"},
            "FUTURES_OPEN_ORDERS": {"symbol": "ETHUSDT"},
            "FUTURES_ORDER_QUERY": {
                "symbol": "ETHUSDT", "origClientOrderId": client_id,
            },
            "FUTURES_TRADES": {"symbol": "ETHUSDT", "orderId": "202"},
            "FUTURES_INCOME": {
                "symbol": "ETHUSDT", "incomeType": "FUNDING_FEE",
                "startTime": "1787702400000", "endTime": "1787788800000",
            },
            "FUTURES_ALGO_QUERY": {"clientAlgoId": client_id},
            "FUTURES_OPEN_ALGO_ORDERS": {"symbol": "ETHUSDT"},
            "SPOT_ORDER_CREATE": {
                "symbol": "ETHUSDT", "side": "BUY", "type": "MARKET",
                "quantity": "0.001", "newClientOrderId": client_id,
                "newOrderRespType": "FULL",
            },
            "SPOT_ORDER_CANCEL": {
                "symbol": "ETHUSDT", "origClientOrderId": client_id,
            },
            "FUTURES_ORDER_CREATE": {
                "symbol": "ETHUSDT", "side": "SELL", "type": "MARKET",
                "quantity": "0.002", "newClientOrderId": client_id,
                "positionSide": "BOTH", "reduceOnly": "false",
            },
            "FUTURES_ORDER_CANCEL": {
                "symbol": "ETHUSDT", "origClientOrderId": client_id,
            },
            "FUTURES_ALGO_CREATE": {
                "algoType": "CONDITIONAL", "symbol": "ETHUSDT",
                "side": "BUY", "positionSide": "BOTH",
                "type": "STOP_MARKET", "quantity": "0.002",
                "triggerPrice": "3200", "workingType": "MARK_PRICE",
                "reduceOnly": "true", "closePosition": "false",
                "clientAlgoId": client_id,
            },
            "FUTURES_ALGO_CANCEL": {"clientAlgoId": client_id},
            "FUTURES_SET_LEVERAGE": {"symbol": "ETHUSDT", "leverage": "2"},
            "FUTURES_SET_MARGIN_TYPE": {
                "symbol": "ETHUSDT", "marginType": "ISOLATED",
            },
        }
        for endpoint_id, values in parameters.items():
            with self.subTest(endpoint_id=endpoint_id):
                request = build_binance_private_request(
                    endpoint_id, values, timestamp_ms=1787788800000
                )
                self.assertEqual(request.endpoint_id, endpoint_id)
                self.assertLessEqual(len(request.encoded_parameters), 4096)

    def test_order_and_configuration_values_are_closed_before_signing(self):
        client_id = "cq77" + "d" * 32
        invalid = (
            ("SPOT_ORDER_CREATE", {
                "symbol": "ETHUSDT", "side": "BUY", "type": "MARKET",
                "quantity": "0", "newClientOrderId": client_id,
                "newOrderRespType": "FULL",
            }),
            ("FUTURES_ORDER_CREATE", {
                "symbol": "ETHUSDT", "side": "SELL", "type": "MARKET",
                "quantity": "0.002", "newClientOrderId": client_id,
                "positionSide": "SHORT", "reduceOnly": "false",
            }),
            ("FUTURES_ALGO_CREATE", {
                "algoType": "CONDITIONAL", "symbol": "ETHUSDT",
                "side": "BUY", "positionSide": "BOTH",
                "type": "STOP_MARKET", "quantity": "0.002",
                "triggerPrice": "3200", "workingType": "MARK_PRICE",
                "reduceOnly": "true", "closePosition": "true",
                "clientAlgoId": client_id,
            }),
            ("FUTURES_SET_LEVERAGE", {"symbol": "ETHUSDT", "leverage": "3"}),
            ("FUTURES_SET_MARGIN_TYPE", {
                "symbol": "ETHUSDT", "marginType": "CROSSED",
            }),
            ("FUTURES_INCOME", {
                "symbol": "ETHUSDT", "incomeType": "TRANSFER",
                "startTime": "1787702400000", "endTime": "1787788800000",
            }),
        )
        for endpoint_id, values in invalid:
            with self.subTest(endpoint_id=endpoint_id):
                with self.assertRaisesRegex(ValueError, "BINANCE_REQUEST_INVALID"):
                    build_binance_private_request(
                        endpoint_id, values, timestamp_ms=1787788800000
                    )

    def test_timing_window_rejects_future_boundary_and_expired_request(self):
        self.assertEqual(
            validate_binance_request_time(timestamp_ms=10999, server_time_ms=10000),
            999,
        )
        for timestamp in (11000, 4999):
            with self.subTest(timestamp=timestamp):
                with self.assertRaisesRegex(ValueError, "BINANCE_TIMESTAMP_INVALID"):
                    validate_binance_request_time(
                        timestamp_ms=timestamp,
                        server_time_ms=10000,
                    )

    def test_mutating_timeout_and_malformed_success_are_unknown(self):
        request = self._mutating_request()
        timeout = classify_binance_private_response(
            request,
            status=400,
            body=b'{"code":-1007,"msg":"Timeout"}',
            headers={},
        )
        malformed = classify_binance_private_response(
            request,
            status=200,
            body=b"not-json",
            headers={},
        )
        malformed_rejection = classify_binance_private_response(
            request,
            status=400,
            body=b"[]",
            headers={},
        )
        rejected = classify_binance_private_response(
            request,
            status=400,
            body=b'{"code":-2010,"msg":"NEW_ORDER_REJECTED"}',
            headers={},
        )
        self.assertEqual(timeout["response_class"], "UNKNOWN")
        self.assertEqual(malformed["response_class"], "UNKNOWN")
        self.assertEqual(malformed_rejection["response_class"], "UNKNOWN")
        self.assertEqual(rejected["response_class"], "REJECTED_PROVEN_NO_ACK")

    def test_response_above_fixed_json_depth_is_a_domain_failure(self):
        body = (b"[" * 65) + b"0" + (b"]" * 65)
        request = build_binance_private_request(
            "SPOT_SERVER_TIME", {}, timestamp_ms=0
        )
        with self.assertRaisesRegex(
            ValueError,
            "CHALLENGER_REPLACEMENT_BINANCE_RESPONSE_INVALID",
        ):
            classify_binance_private_response(
                request, status=200, body=body, headers={}
            )


if __name__ == "__main__":
    unittest.main()
