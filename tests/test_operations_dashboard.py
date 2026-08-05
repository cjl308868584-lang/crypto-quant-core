"""Loopback-only read-only operations dashboard tests."""

import http.client
import threading
import unittest

from crypto_quant.operations_alerts import build_operations_status_body
from crypto_quant.operations_dashboard import (
    OperationsDashboardError,
    create_operations_server,
)

from tests.test_operations_alerts import _projection_body


EXPECTED_CSP = (
    "default-src 'self'; connect-src 'self'; img-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
)


class RunningServer:
    def __init__(self, provider):
        self.server = create_operations_server(provider, port=0)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def port(self):
        return self.server.server_port

    def request(self, method, path, *, host=None, body=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=5
        )
        connection.putrequest(method, path, skip_host=host is not None)
        if host not in (None, ""):
            connection.putheader("Host", host)
        if body is not None:
            connection.putheader("Content-Length", str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse()
        value = response.read()
        headers = dict(response.getheaders())
        connection.close()
        return response.status, headers, value


class OperationsDashboardConstructionTests(unittest.TestCase):
    def assert_reason(self, reason, operation):
        with self.assertRaises(OperationsDashboardError) as caught:
            operation()
        self.assertEqual(caught.exception.reason_code, reason)
        self.assertEqual(str(caught.exception), reason)

    def test_rejects_every_nonliteral_loopback_host(self):
        invalid = ("localhost", "::1", "0.0.0.0", "", None, 127001)
        for host in invalid:
            with self.subTest(host=host):
                self.assert_reason(
                    "OPERATIONS_DASHBOARD_HOST_INVALID",
                    lambda host=host: create_operations_server(
                        _projection_body, host=host, port=0
                    ),
                )

    def test_rejects_invalid_ports_and_provider(self):
        for port in (True, False, -1, 65536, 1.5, "8765", None):
            with self.subTest(port=port):
                self.assert_reason(
                    "OPERATIONS_DASHBOARD_PORT_INVALID",
                    lambda port=port: create_operations_server(
                        _projection_body, port=port
                    ),
                )
        self.assert_reason(
            "OPERATIONS_DASHBOARD_PROVIDER_INVALID",
            lambda: create_operations_server(b"not-callable", port=0),
        )

    def test_api_calls_provider_once_and_returns_exact_canonical_status(self):
        calls = []
        projection = _projection_body()

        def provider():
            calls.append("called")
            return projection

        with RunningServer(provider) as running:
            status, headers, body = running.request(
                "GET",
                "/api/v1/status",
                host=f"127.0.0.1:{running.port}",
            )

        self.assertEqual(status, 200)
        self.assertEqual(calls, ["called"])
        self.assertEqual(body, build_operations_status_body(projection))
        self.assertEqual(
            headers["Content-Type"], "application/json; charset=utf-8"
        )
        self.assertEqual(headers["Content-Length"], str(len(body)))
        self.assertEqual(headers["Content-Security-Policy"], EXPECTED_CSP)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(
            headers["Permissions-Policy"],
            "camera=(), microphone=(), geolocation=()",
        )
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertNotIn("Set-Cookie", headers)


class OperationsDashboardHTTPBoundaryTests(unittest.TestCase):
    def assert_security_headers(self, headers):
        self.assertEqual(headers["Content-Security-Policy"], EXPECTED_CSP)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(
            headers["Permissions-Policy"],
            "camera=(), microphone=(), geolocation=()",
        )
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertNotIn("Set-Cookie", headers)

    def test_clean_unknown_and_suspicious_paths_fail_without_provider_call(self):
        calls = []

        def provider():
            calls.append("called")
            return _projection_body()

        suspicious = (
            "/api/v1/status?fresh=1",
            "/api/v1/%73tatus",
            "/api/v1/../status",
            "/api/v1/./status",
            "/api\\v1\\status",
            "/%00",
        )
        with RunningServer(provider) as running:
            status, headers, _ = running.request(
                "GET",
                "/unknown",
                host=f"127.0.0.1:{running.port}",
            )
            self.assertEqual(status, 404)
            self.assert_security_headers(headers)
            for path in suspicious:
                with self.subTest(path=path):
                    status, headers, _ = running.request(
                        "GET",
                        path,
                        host=f"127.0.0.1:{running.port}",
                    )
                    self.assertEqual(status, 400)
                    self.assert_security_headers(headers)
        self.assertEqual(calls, [])

    def test_missing_or_mismatched_host_fails_before_provider(self):
        calls = []

        def provider():
            calls.append("called")
            return _projection_body()

        with RunningServer(provider) as running:
            invalid = (
                "",
                "localhost:{}".format(running.port),
                "127.0.0.1",
                "127.0.0.1:1",
                "example.com:{}".format(running.port),
            )
            for host in invalid:
                with self.subTest(host=host):
                    status, headers, _ = running.request(
                        "GET", "/api/v1/status", host=host
                    )
                    self.assertEqual(status, 400)
                    self.assert_security_headers(headers)
        self.assertEqual(calls, [])

    def test_every_non_get_method_is_405_and_never_calls_provider(self):
        calls = []

        def provider():
            calls.append("called")
            return _projection_body()

        methods = (
            "HEAD",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
            "CONNECT",
            "TRACE",
        )
        with RunningServer(provider) as running:
            for method in methods:
                with self.subTest(method=method):
                    status, headers, _ = running.request(
                        method,
                        "/api/v1/status",
                        host=f"127.0.0.1:{running.port}",
                        body=b"{}" if method != "HEAD" else None,
                    )
                    self.assertEqual(status, 405)
                    self.assertEqual(headers["Allow"], "GET")
                    self.assert_security_headers(headers)
        self.assertEqual(calls, [])

    def test_provider_and_loader_failures_return_one_generic_secret_free_503(self):
        secret = "/Users/example/private/API_SECRET"
        providers = (
            lambda: (_ for _ in ()).throw(RuntimeError(secret)),
            lambda: "not-bytes",
            lambda: b'{"private":"' + secret.encode("utf-8") + b'"}',
        )
        expected = (
            b'{"error":"OPERATIONS_STATUS_UNAVAILABLE",'
            b'"new_risk_allowed":false}'
        )
        for provider in providers:
            with self.subTest(provider=provider):
                with RunningServer(provider) as running:
                    status, headers, body = running.request(
                        "GET",
                        "/api/v1/status",
                        host=f"127.0.0.1:{running.port}",
                    )
                self.assertEqual(status, 503)
                self.assertEqual(body, expected)
                self.assertNotIn(secret.encode("utf-8"), body)
                self.assertNotIn(b"Traceback", body)
                self.assertEqual(
                    headers["Content-Type"],
                    "application/json; charset=utf-8",
                )
                self.assert_security_headers(headers)


if __name__ == "__main__":
    unittest.main()
