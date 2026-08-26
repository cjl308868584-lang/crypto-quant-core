"""Narrow credential-free HTTP transport for fixed public evidence requests."""

import base64
import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from .canonical import utc_datetime


_HTTP_TIMEOUT_SECONDS = 15
_MAX_PUBLIC_BODY_BYTES = 4 * 1024 * 1024
_FORBIDDEN_HEADER_FRAGMENTS = (
    "authorization",
    "cookie",
    "api-key",
    "apikey",
    "api_key",
    "secret",
    "token",
    "x-mbx",
)


class PublicHttpError(ValueError):
    """The shared public HTTP boundary failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PublicHttpError("PUBLIC_HTTP_REDIRECT_FORBIDDEN")


@dataclass(frozen=True)
class PublicHttpResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes
    monotonic_rtt_ms: int
    request_started_at: str
    response_received_at: str


def _wall_now():
    return datetime.now(timezone.utc)


def _monotonic():
    return time.monotonic_ns()


def open_fixed_public_request(request: Request, *, max_body_bytes: int):
    """Open one already-selected bounded public HTTPS GET request."""

    if not isinstance(max_body_bytes, int) or isinstance(max_body_bytes, bool):
        raise PublicHttpError("PUBLIC_HTTP_LIMIT_INVALID")
    if not 1 <= max_body_bytes <= _MAX_PUBLIC_BODY_BYTES:
        raise PublicHttpError("PUBLIC_HTTP_LIMIT_INVALID")
    if not isinstance(request, Request):
        raise PublicHttpError("PUBLIC_HTTP_REQUEST_INVALID")
    try:
        parsed = urlsplit(request.full_url)
        header_names = tuple(name.lower() for name, _ in request.header_items())
    except (AttributeError, TypeError, ValueError) as error:
        raise PublicHttpError("PUBLIC_HTTP_REQUEST_INVALID") from error
    if (
        request.get_method() != "GET"
        or request.data is not None
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or any(
            fragment in name
            for name in header_names
            for fragment in _FORBIDDEN_HEADER_FRAGMENTS
        )
    ):
        raise PublicHttpError("PUBLIC_HTTP_REQUEST_INVALID")
    try:
        opener = build_opener(ProxyHandler({}), _RejectRedirects())
    except (OSError, TimeoutError, URLError) as error:
        raise PublicHttpError("PUBLIC_HTTP_TRANSPORT_FAILURE") from error
    started = _wall_now()
    monotonic_started = _monotonic()
    try:
        with opener.open(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
            body = response.read(max_body_bytes + 1)
            status = response.getcode()
            final_url = response.geturl()
            headers = dict(response.headers.items())
    except HTTPError as error:
        try:
            body = error.read(max_body_bytes + 1)
            status = error.code
            final_url = error.geturl()
            headers = dict(error.headers.items()) if error.headers else {}
        except (AttributeError, OSError, TypeError, ValueError) as read_error:
            raise PublicHttpError("PUBLIC_HTTP_RESPONSE_INVALID") from read_error
    except PublicHttpError:
        raise
    except (OSError, TimeoutError, URLError) as error:
        raise PublicHttpError("PUBLIC_HTTP_TRANSPORT_FAILURE") from error
    except (AttributeError, TypeError, ValueError) as error:
        raise PublicHttpError("PUBLIC_HTTP_RESPONSE_INVALID") from error
    received = _wall_now()
    monotonic_received = _monotonic()
    if (
        not isinstance(body, bytes)
        or len(body) > max_body_bytes
        or not isinstance(status, int)
        or isinstance(status, bool)
        or not 100 <= status <= 599
        or not isinstance(final_url, str)
        or final_url != request.full_url
        or received < started
        or monotonic_received < monotonic_started
    ):
        raise PublicHttpError("PUBLIC_HTTP_RESPONSE_INVALID")
    return PublicHttpResponse(
        status=status,
        final_url=final_url,
        headers=headers,
        body=body,
        monotonic_rtt_ms=(
            monotonic_received - monotonic_started + 999_999
        ) // 1_000_000,
        request_started_at=utc_datetime(started),
        response_received_at=utc_datetime(received),
    )


def attempt_document(response, sequence: int):
    """Encode one bounded HTTP response into deterministic evidence."""

    if (
        not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or not 1 <= sequence <= 3
    ):
        raise PublicHttpError("PUBLIC_HTTP_ATTEMPT_INVALID")
    try:
        headers = {key.lower(): value for key, value in response.headers.items()}
        body = bytes(response.body)
        status = response.status
        final_url = response.final_url
        started = response.request_started_at
        received = response.response_received_at
    except (AttributeError, TypeError, ValueError) as error:
        raise PublicHttpError("PUBLIC_HTTP_RESPONSE_INVALID") from error
    content_type = headers.get("content-type")
    if (
        not isinstance(status, int)
        or isinstance(status, bool)
        or not 100 <= status <= 599
        or not isinstance(final_url, str)
        or not final_url.startswith("https://")
        or not isinstance(started, str)
        or not isinstance(received, str)
        or (status == 200 and (
            not isinstance(content_type, str)
            or content_type.split(";", 1)[0].strip().lower()
            != "application/json"
        ))
    ):
        raise PublicHttpError("PUBLIC_HTTP_RESPONSE_INVALID")
    return {
        "sequence": sequence,
        "outcome": "HTTP_RESPONSE",
        "error_reason_or_null": None,
        "request_started_at": started,
        "response_received_at": received,
        "status": status,
        "final_url": final_url,
        "selected_headers": {
            "http_date_or_null": headers.get("date"),
            "etag_or_null": headers.get("etag"),
            "last_modified_or_null": headers.get("last-modified"),
            "retry_after_or_null": headers.get("retry-after"),
        },
        "body_size_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "response_body_base64": base64.b64encode(body).decode("ascii"),
    }


def transport_failure_attempt(sequence: int, *, started, received):
    """Encode one fixed transport failure without leaking exception text."""

    if (
        not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or not 1 <= sequence <= 3
    ):
        raise PublicHttpError("PUBLIC_HTTP_ATTEMPT_INVALID")
    try:
        if received < started:
            raise ValueError("backward wall clock")
        started_text = utc_datetime(started)
        received_text = utc_datetime(received)
    except (AttributeError, TypeError, ValueError) as error:
        raise PublicHttpError("PUBLIC_HTTP_CLOCK_INVALID") from error
    return {
        "sequence": sequence,
        "outcome": "TRANSPORT_ERROR",
        "error_reason_or_null": "PUBLIC_HTTP_TRANSPORT_FAILURE",
        "request_started_at": started_text,
        "response_received_at": received_text,
        "status": None,
        "final_url": None,
        "selected_headers": {
            "http_date_or_null": None,
            "etag_or_null": None,
            "last_modified_or_null": None,
            "retry_after_or_null": None,
        },
        "body_size_bytes": 0,
        "body_sha256": hashlib.sha256(b"").hexdigest(),
        "response_body_base64": "",
    }
