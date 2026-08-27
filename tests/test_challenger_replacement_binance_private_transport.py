from dataclasses import replace
import hashlib
import http.client
import os
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import Mock, patch

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_binance_credential import (
    BinanceCredentialCapability,
    open_binance_credential_capability,
)
from crypto_quant.challenger_replacement_binance_private_contract import (
    BinancePrivateActivation,
)
from crypto_quant.challenger_replacement_binance_private_protocol import (
    build_binance_private_request,
)
from crypto_quant.challenger_replacement_binance_private_transport import (
    BinancePrivateTransportError,
    execute_binance_private_request,
)
from tests.challenger_replacement_v077_private_fixtures import (
    loaded_private_activation,
)


class _Response:
    def __init__(self, status=200, body=b"{}", headers=()):
        self.status = status
        self._body = body
        self._headers = headers

    def read(self, limit):
        return self._body[:limit]

    def getheaders(self):
        return self._headers


class _Connection:
    def __init__(self, response=None, request_error=None, response_error=None,
                 close_error=None):
        self.response = response or _Response()
        self.request_error = request_error
        self.response_error = response_error
        self.close_error = close_error
        self.requests = []
        self.close_count = 0

    def request(self, method, target, body=None, headers=None):
        self.requests.append((method, target, body, headers))
        if self.request_error:
            raise self.request_error

    def getresponse(self):
        if self.response_error:
            raise self.response_error
        return self.response

    def close(self):
        self.close_count += 1
        if self.close_error:
            raise self.close_error


class BinancePrivateTransportTests(unittest.TestCase):
    BUILD = {
        "release_tag": "v0.77.0",
        "peeled_commit": "1" * 40,
        "package_version": "0.77.0",
        "manifest_version": "v0.77.0",
        "build_input_tree_hash": "2" * 64,
        "manifest_hash": "3" * 64,
        "manifest_file_sha256": "4" * 64,
    }
    NOW = "2026-08-27T12:00:00.000Z"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name) / "credential"
        root.mkdir(mode=0o700)
        self.credential_path = root / "binance-hmac.json"
        self.api_key = "A" * 32
        self.secret = "B" * 32
        body = (canonical_json({
            "api_key": self.api_key, "hmac_secret": self.secret,
        }) + "\n").encode()
        self.credential_path.write_bytes(body)
        self.credential_path.chmod(0o600)
        parent, entry = root.stat(), self.credential_path.stat()
        self.reference = {
            "$schema": "./challenger-replacement-binance-credential-reference-v1.schema.json",
            "schema_version": "1.0.0",
            "absolute_path": str(self.credential_path),
            "parent_device": parent.st_dev,
            "parent_inode": parent.st_ino,
            "file_device": entry.st_dev,
            "file_inode": entry.st_ino,
            "file_sha256": hashlib.sha256(body).hexdigest(),
        }
        self.credential = open_binance_credential_capability(
            reference=self.reference, expected_owner_uid=os.getuid()
        )
        self.activation = loaded_private_activation(
            build_identity=self.BUILD, now=self.NOW,
            activation_id="activation_" + "5" * 64,
            block_id="block_" + "8" * 64,
        )

    def tearDown(self):
        self.credential.close()
        self.temporary.cleanup()

    def _request(self, mutating=False):
        if mutating:
            return build_binance_private_request(
                "SPOT_ORDER_CREATE", {
                    "symbol": "ETHUSDT", "side": "BUY", "type": "MARKET",
                    "quantity": "0.001", "newClientOrderId": "cq77" + "9" * 32,
                    "newOrderRespType": "FULL",
                }, timestamp_ms=1_787_788_800_000,
            )
        return build_binance_private_request(
            "SPOT_ACCOUNT", {}, timestamp_ms=1_787_788_800_000
        )

    def _execute(self, connection, request=None, activation=None):
        with patch.object(http.client, "HTTPSConnection", return_value=connection):
            return execute_binance_private_request(
                request or self._request(), credential=self.credential,
                activation=activation or self.activation,
                expected_build_identity=self.BUILD, now=self.NOW,
            )

    def test_directly_constructed_activation_cannot_authorize_transport(self):
        forged = BinancePrivateActivation(
            activation_id=self.activation.activation_id,
            build_identity=self.activation.build_identity,
            configuration_sha256=self.activation.configuration_sha256,
            account_approval_sha256=self.activation.account_approval_sha256,
            block_id=self.activation.block_id, stage=self.activation.stage,
            capital_usdt=self.activation.capital_usdt,
            max_gross_exposure_usdt=self.activation.max_gross_exposure_usdt,
            max_leverage=self.activation.max_leverage,
            expires_at=self.activation.expires_at,
            production_activation=True,
        )
        connection = _Connection()
        with self.assertRaisesRegex(
            BinancePrivateTransportError,
            "BINANCE_PRIVATE_TRANSPORT_NOT_AUTHORIZED",
        ):
            self._execute(connection, activation=forged)
        self.assertEqual(connection.requests, [])

    def test_no_authority_wrong_build_and_expiry_reject_before_secret_or_socket(self):
        cases = (
            None,
            replace(self.activation, production_activation=False),
            replace(self.activation, build_identity={**self.BUILD, "release_tag": "wrong"}),
            replace(self.activation, expires_at=self.NOW),
        )
        for activation in cases:
            with self.subTest(activation=activation), \
                    patch.object(BinanceCredentialCapability, "authorize") as authorize, \
                    patch.object(http.client, "HTTPSConnection") as connection:
                with self.assertRaises(BinancePrivateTransportError) as caught:
                    execute_binance_private_request(
                        self._request(), credential=self.credential,
                        activation=activation,
                        expected_build_identity=self.BUILD, now=self.NOW,
                    )
                self.assertEqual(caught.exception.reason_code,
                                 "BINANCE_PRIVATE_TRANSPORT_NOT_AUTHORIZED")
                authorize.assert_not_called()
                connection.assert_not_called()

    def test_fixed_https_request_ignores_proxy_environment_and_redacts_result(self):
        connection = _Connection(_Response(
            body=b'{"accountType":"SPOT"}',
            headers=(("X-MBX-USED-WEIGHT-1M", "7"),),
        ))
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://secret@evil.invalid"}), \
                patch.object(http.client, "HTTPSConnection", return_value=connection) as factory:
            result = execute_binance_private_request(
                self._request(), credential=self.credential,
                activation=self.activation,
                expected_build_identity=self.BUILD, now=self.NOW,
            )
        self.assertEqual(result.response_class, "QUERY_SUCCEEDED")
        self.assertEqual(result.status_or_null, 200)
        self.assertEqual(result.body, b'{"accountType":"SPOT"}')
        self.assertEqual(result.response_sha256, hashlib.sha256(result.body).hexdigest())
        self.assertEqual(result.rate_limit_headers,
                         (("x-mbx-used-weight-1m", "7"),))
        factory.assert_called_once()
        args, kwargs = factory.call_args
        self.assertEqual((args[0], kwargs["port"], kwargs["timeout"]),
                         ("api.binance.com", 443, 5.0))
        self.assertEqual(kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
        method, target, body, headers = connection.requests[0]
        self.assertEqual(method, "GET")
        self.assertTrue(target.startswith("/api/v3/account?"))
        self.assertIsNone(body)
        self.assertEqual(headers["X-MBX-APIKEY"], self.api_key)
        self.assertNotIn(self.api_key, repr(result))
        self.assertNotIn(self.secret, repr(result))
        self.assertEqual(connection.close_count, 1)

    def test_transport_result_repr_redacts_raw_response_body(self):
        sentinel = b"SENTINEL_PRIVATE_RESPONSE_BODY"
        result = self._execute(_Connection(_Response(body=sentinel)))
        self.assertEqual(result.body, sentinel)
        self.assertNotIn(sentinel.decode("ascii"), repr(result))

    def test_mutating_request_is_sent_once_and_timeout_becomes_unknown(self):
        connection = _Connection(request_error=TimeoutError("after send"))
        result = self._execute(connection, request=self._request(mutating=True))
        self.assertEqual((result.response_class, result.status_or_null),
                         ("UNKNOWN", None))
        self.assertEqual(len(connection.requests), 1)
        self.assertEqual(connection.close_count, 1)

        query = _Connection(response_error=TimeoutError("response timeout"))
        result = self._execute(query)
        self.assertEqual(result.response_class, "TRANSIENT_QUERY_FAILURE")
        self.assertEqual(len(query.requests), 1)

    def test_post_uses_fixed_form_body_without_retry_or_redirect_surface(self):
        connection = _Connection(_Response(body=b'{"symbol":"ETHUSDT"}'))
        result = self._execute(connection, request=self._request(mutating=True))
        self.assertEqual(result.response_class, "ACKNOWLEDGED")
        self.assertEqual(len(connection.requests), 1)
        method, target, body, headers = connection.requests[0]
        self.assertEqual((method, target), ("POST", "/api/v3/order"))
        self.assertIn(b"&signature=", body)
        self.assertEqual(headers["Content-Type"],
                         "application/x-www-form-urlencoded")
        self.assertNotIn("redirect", repr(connection.requests).lower())

    def test_connect_failure_is_proven_before_send(self):
        with patch.object(http.client, "HTTPSConnection",
                          side_effect=OSError("TLS setup failed")):
            with self.assertRaises(BinancePrivateTransportError) as caught:
                execute_binance_private_request(
                    self._request(mutating=True), credential=self.credential,
                    activation=self.activation,
                    expected_build_identity=self.BUILD, now=self.NOW,
                )
        self.assertEqual(caught.exception.reason_code,
                         "BINANCE_PRIVATE_TRANSPORT_CONNECT_FAILED")

    def test_tampered_host_or_path_fails_before_socket_construction(self):
        for tampered in (
            replace(self._request(), host="evil.invalid"),
            replace(self._request(), path="/api/v3/order"),
        ):
            with self.subTest(request=tampered), \
                    patch.object(http.client, "HTTPSConnection") as connection:
                with self.assertRaises(ValueError):
                    execute_binance_private_request(
                        tampered, credential=self.credential,
                        activation=self.activation,
                        expected_build_identity=self.BUILD, now=self.NOW,
                    )
                connection.assert_not_called()

    def test_redirect_rate_limit_server_error_and_malformed_success_classify(self):
        cases = (
            (302, b"{}", "RESPONSE_INVALID"),
            (418, b'{"code":-1003,"msg":"banned"}', "RATE_LIMITED"),
            (429, b'{"code":-1003,"msg":"slow"}', "RATE_LIMITED"),
            (500, b'{"code":-1000,"msg":"error"}', "UNKNOWN"),
            (200, b"not-json", "UNKNOWN"),
        )
        for status, body, expected in cases:
            with self.subTest(status=status):
                result = self._execute(
                    _Connection(_Response(status=status, body=body)),
                    request=self._request(mutating=True),
                )
                self.assertEqual(result.response_class, expected)

    def test_oversized_body_and_close_failure_fail_closed(self):
        oversized = _Connection(_Response(body=b"x" * (1_048_576 + 1)))
        with self.assertRaises(BinancePrivateTransportError) as caught:
            self._execute(oversized)
        self.assertEqual(caught.exception.reason_code,
                         "BINANCE_PRIVATE_TRANSPORT_RESPONSE_TOO_LARGE")
        closing = _Connection(close_error=OSError("close failed"))
        with self.assertRaises(BinancePrivateTransportError) as caught:
            self._execute(closing)
        self.assertEqual(caught.exception.reason_code,
                         "BINANCE_PRIVATE_TRANSPORT_CLOSE_FAILED")

        both = _Connection(
            _Response(body=b"x" * (1_048_576 + 1)),
            close_error=OSError("close failed"),
        )
        with self.assertRaises(BinancePrivateTransportError) as caught:
            self._execute(both)
        self.assertEqual(caught.exception.reason_code,
                         "BINANCE_PRIVATE_TRANSPORT_RESPONSE_TOO_LARGE")
        self.assertEqual(
            caught.exception.close_failure_reason_code,
            "BINANCE_PRIVATE_TRANSPORT_CLOSE_FAILED",
        )

    def test_malformed_status_body_or_header_is_a_fixed_response_failure(self):
        cases = (
            _Response(status="200", body=b"{}"),
            _Response(status=200, body="not-bytes"),
            _Response(status=200, body=b"{}", headers=((7, "value"),)),
            _Response(status=200, body=b"{}", headers=(
                ("Retry-After", "1"), ("retry-after", "2"),
            )),
        )
        for response in cases:
            with self.subTest(response=response):
                with self.assertRaises(BinancePrivateTransportError) as caught:
                    self._execute(_Connection(response))
                self.assertEqual(
                    caught.exception.reason_code,
                    "BINANCE_PRIVATE_TRANSPORT_RESPONSE_INVALID",
                )


if __name__ == "__main__":
    unittest.main()
