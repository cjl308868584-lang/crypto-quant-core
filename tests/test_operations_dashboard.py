"""Loopback-only read-only operations dashboard tests."""

import ast
import http.client
import io
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from crypto_quant.operations_alerts import build_operations_status_body
from crypto_quant.operations_dashboard import (
    OperationsDashboardError,
    create_operations_server,
    main as dashboard_main,
)
from crypto_quant.operations_projection import load_operations_projection_bytes

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


class OperationsDashboardAssetTests(unittest.TestCase):
    def test_exact_static_routes_serve_packaged_local_assets(self):
        with RunningServer(_projection_body) as running:
            responses = {}
            for route in ("/", "/app.js", "/styles.css"):
                status, headers, body = running.request(
                    "GET",
                    route,
                    host=f"127.0.0.1:{running.port}",
                )
                responses[route] = (status, headers, body)

        expected_types = {
            "/": "text/html; charset=utf-8",
            "/app.js": "text/javascript; charset=utf-8",
            "/styles.css": "text/css; charset=utf-8",
        }
        for route, (status, headers, body) in responses.items():
            with self.subTest(route=route):
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Type"], expected_types[route])
                self.assertGreater(len(body), 100)

    def test_html_has_four_read_only_regions_and_no_operation_surface(self):
        with RunningServer(_projection_body) as running:
            _, _, body = running.request(
                "GET", "/", host=f"127.0.0.1:{running.port}"
            )
        html = body.decode("utf-8")

        for region in (
            "project-summary",
            "challenger-timeline",
            "paper-runtime",
            "risk-alerts",
        ):
            self.assertIn('id="{}"'.format(region), html)
        lowered = html.lower()
        for forbidden in (
            "<form",
            "<button",
            "http://",
            "https://",
            "pnl",
            "win_rate",
            "drawdown",
            "fee_usdt",
            "average_fill_price",
            "confidence_interval",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_javascript_is_one_shot_same_origin_and_uses_text_content(self):
        with RunningServer(_projection_body) as running:
            _, _, body = running.request(
                "GET", "/app.js", host=f"127.0.0.1:{running.port}"
            )
        script = body.decode("utf-8")

        self.assertEqual(script.count('fetch("/api/v1/status"'), 1)
        self.assertIn("document.createElement", script)
        self.assertIn("textContent", script)
        for forbidden in (
            "innerHTML",
            "outerHTML",
            "document.write",
            "WebSocket",
            "setInterval",
            "setTimeout",
            "http://",
            "https://",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, script)

    def test_modules_import_no_operational_or_mutating_capability(self):
        root = Path(__file__).resolve().parents[1] / "src" / "crypto_quant"
        forbidden = {
            "sqlite3",
            "subprocess",
            "socket",
            "crypto_quant.system_paper_runtime",
            "crypto_quant.system_paper_scheduler",
            "crypto_quant.system_paper_install",
            "crypto_quant.system_paper_broker",
            "crypto_quant.challenger_forward_runner",
        }
        for name in ("operations_alerts.py", "operations_dashboard.py"):
            tree = ast.parse((root / name).read_text(encoding="utf-8"))
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.lstrip("."))
            with self.subTest(name=name):
                self.assertTrue(imports.isdisjoint(forbidden), imports)


class OperationsDashboardCliTests(unittest.TestCase):
    def invoke(self, arguments):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = dashboard_main(arguments)
        return result, stderr.getvalue()

    def test_cli_rejects_relative_duplicate_host_and_invalid_port_arguments(self):
        secret = "relative/API_SECRET/projection.json"
        cases = (
            ["--projection-file", secret],
            [
                "--projection-file",
                "/tmp/projection.json",
                "--projection-file",
                "/tmp/other.json",
            ],
            [
                "--projection-file",
                "/tmp/projection.json",
                "--host",
                "0.0.0.0",
            ],
            [
                "--projection-file",
                "/tmp/projection.json",
                "--port",
                "65536",
            ],
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result, stderr = self.invoke(arguments)
                self.assertEqual(result, 1)
                self.assertIn("OPERATIONS_DASHBOARD_CLI_FAILED", stderr)
                self.assertNotIn("usage:", stderr)
                self.assertNotIn(secret, stderr)

    def test_committed_fixture_is_canonical_and_strictly_replayable(self):
        fixture = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "operations-projection-healthy.json"
        )
        body = fixture.read_bytes()

        projection = load_operations_projection_bytes(body)

        self.assertEqual(projection["release"]["release_tag"], "v0.60.0")
        self.assertEqual(projection["status"], "HEALTHY")
        self.assertEqual(projection["challenger"]["incident_count"], 0)
        self.assertEqual(projection["system_paper"]["phase"], "COLLECTING")


if __name__ == "__main__":
    unittest.main()
