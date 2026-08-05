"""Loopback-only read-only HTTP console for operations projections."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Mapping, Optional

from .operations_alerts import build_operations_status_body


_CSP = (
    "default-src 'self'; connect-src 'self'; img-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
)
_STATUS_UNAVAILABLE = (
    b'{"error":"OPERATIONS_STATUS_UNAVAILABLE",'
    b'"new_risk_allowed":false}'
)


class OperationsDashboardError(ValueError):
    """The dashboard boundary rejected its construction inputs."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class _OperationsHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, projection_provider):
        self.projection_provider = projection_provider
        super().__init__(address, _OperationsRequestHandler)


class _OperationsRequestHandler(BaseHTTPRequestHandler):
    server: _OperationsHTTPServer

    def log_message(self, format, *args):
        return None

    def _send(
        self,
        status: int,
        content_type: str,
        body: bytes,
        *,
        extra_headers: Optional[Mapping[str, str]] = None,
        write_body: bool = True,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", _CSP)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if write_body:
            self.wfile.write(body)

    def _host_valid(self) -> bool:
        expected = "127.0.0.1:{}".format(self.server.server_port)
        return self.headers.get("Host") == expected

    def _path_suspicious(self) -> bool:
        if any(character in self.path for character in ("%", "\\", "?", "#")):
            return True
        if any(ord(character) < 32 or ord(character) == 127 for character in self.path):
            return True
        return any(segment in {".", ".."} for segment in self.path.split("/"))

    def _method_not_allowed(self, *, write_body: bool = True) -> None:
        self._send(
            405,
            "text/plain; charset=utf-8",
            b"METHOD_NOT_ALLOWED" if write_body else b"",
            extra_headers={"Allow": "GET"},
            write_body=write_body,
        )

    def do_GET(self):
        if not self._host_valid():
            self._send(400, "text/plain; charset=utf-8", b"BAD_REQUEST")
            return
        if self._path_suspicious():
            self._send(400, "text/plain; charset=utf-8", b"BAD_REQUEST")
            return
        if self.path != "/api/v1/status":
            self._send(404, "text/plain; charset=utf-8", b"NOT_FOUND")
            return
        try:
            projection_body = self.server.projection_provider()
            body = build_operations_status_body(projection_body)
        except Exception:
            self._send(
                503,
                "application/json; charset=utf-8",
                _STATUS_UNAVAILABLE,
            )
            return
        self._send(200, "application/json; charset=utf-8", body)

    def do_HEAD(self):
        self._method_not_allowed(write_body=False)

    def do_POST(self):
        self._method_not_allowed()

    def do_PUT(self):
        self._method_not_allowed()

    def do_PATCH(self):
        self._method_not_allowed()

    def do_DELETE(self):
        self._method_not_allowed()

    def do_OPTIONS(self):
        self._method_not_allowed()

    def do_CONNECT(self):
        self._method_not_allowed()

    def do_TRACE(self):
        self._method_not_allowed()


def create_operations_server(
    projection_provider: Callable[[], bytes],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    """Create, but do not start, the fixed loopback operations server."""

    if host != "127.0.0.1":
        raise OperationsDashboardError("OPERATIONS_DASHBOARD_HOST_INVALID")
    if type(port) is not int or port < 0 or port > 65535:
        raise OperationsDashboardError("OPERATIONS_DASHBOARD_PORT_INVALID")
    if not callable(projection_provider):
        raise OperationsDashboardError(
            "OPERATIONS_DASHBOARD_PROVIDER_INVALID"
        )
    return _OperationsHTTPServer((host, port), projection_provider)
