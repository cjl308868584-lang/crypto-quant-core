"""Loopback-only read-only HTTP console for operations projections."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
import sys
from typing import Callable, Mapping, Optional

from .canonical import canonical_json
from .operations_alerts import build_operations_status_body


_CSP = (
    "default-src 'self'; connect-src 'self'; img-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
)
_STATUS_UNAVAILABLE = (
    b'{"error":"OPERATIONS_STATUS_UNAVAILABLE",'
    b'"new_risk_allowed":false}'
)
_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


class OperationsDashboardError(ValueError):
    """The dashboard boundary rejected its construction inputs."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise OperationsDashboardError(
            "OPERATIONS_DASHBOARD_CLI_ARGUMENT_INVALID"
        )


class _OnceAction(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None) -> None:
        if getattr(namespace, self.dest, None) is not None:
            raise OperationsDashboardError(
                "OPERATIONS_DASHBOARD_CLI_ARGUMENT_INVALID"
            )
        setattr(namespace, self.dest, value)


def _port(value: str) -> int:
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise OperationsDashboardError(
            "OPERATIONS_DASHBOARD_CLI_ARGUMENT_INVALID"
        )
    parsed = int(value)
    if parsed < 1 or parsed > 65535:
        raise OperationsDashboardError(
            "OPERATIONS_DASHBOARD_CLI_ARGUMENT_INVALID"
        )
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="crypto-quant-operations-dashboard",
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--projection-file", required=True, action=_OnceAction
    )
    parser.add_argument("--port", action=_OnceAction, type=_port)
    return parser


def _projection_path(value: object) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise OperationsDashboardError("OPERATIONS_DASHBOARD_CLI_PATH_INVALID")
    path = Path(value)
    raw_segments = value.split("/")
    if (
        not path.is_absolute()
        or any(segment in {"", ".", ".."} for segment in raw_segments[1:])
    ):
        raise OperationsDashboardError("OPERATIONS_DASHBOARD_CLI_PATH_INVALID")
    return path


def _write_cli_error(error: BaseException) -> None:
    reason = getattr(error, "reason_code", None)
    if (
        not isinstance(reason, str)
        or not reason.isascii()
        or not reason.replace("_", "").isalnum()
        or len(reason) > 160
    ):
        reason = "OPERATIONS_DASHBOARD_CLI_UNAVAILABLE"
    body = canonical_json(
        {
            "error": "OPERATIONS_DASHBOARD_CLI_FAILED",
            "reason_code": reason,
        }
    )
    try:
        sys.stderr.write(body + "\n")
        sys.stderr.flush()
    except Exception:
        pass


class _OperationsHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, projection_provider):
        self.projection_provider = projection_provider
        super().__init__(address, _OperationsRequestHandler)


class _OperationsRequestHandler(BaseHTTPRequestHandler):
    server: _OperationsHTTPServer

    def __getattr__(self, name):
        if name.startswith("do_"):
            return self._method_not_allowed
        raise AttributeError(name)

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
        if not self._host_valid() or self._path_suspicious():
            self._send(
                400,
                "text/plain; charset=utf-8",
                b"BAD_REQUEST",
                write_body=write_body,
            )
            return
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
        if self.path in _ASSETS:
            filename, content_type = _ASSETS[self.path]
            try:
                body = (
                    resources.files("crypto_quant")
                    .joinpath("dashboard", filename)
                    .read_bytes()
                )
            except Exception:
                self._send(
                    503,
                    "text/plain; charset=utf-8",
                    b"STATIC_ASSET_UNAVAILABLE",
                )
                return
            self._send(200, content_type, body)
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


def main(argv=None) -> int:
    """Serve one explicit strict projection on the fixed loopback host."""

    server = None
    try:
        arguments = _parser().parse_args(argv)
        projection_path = _projection_path(arguments.projection_file)

        def provider():
            return projection_path.read_bytes()

        build_operations_status_body(provider())
        server = create_operations_server(
            provider,
            port=arguments.port if arguments.port is not None else 8765,
        )
        server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        _write_cli_error(error)
        return 1
    finally:
        if server is not None:
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
