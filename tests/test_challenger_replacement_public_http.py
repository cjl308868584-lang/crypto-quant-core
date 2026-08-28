import unittest
from datetime import datetime, timezone
from email.message import Message
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from crypto_quant import challenger_replacement_public_http as public_http


class _Response:
    def __init__(self, body):
        self._body = body
        self.headers = {
            "Content-Type": "application/json",
            "Date": "Wed, 26 Aug 2026 04:04:00 GMT",
        }
        self.read_limits = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit):
        self.read_limits.append(limit)
        return self._body[:limit]

    def getcode(self):
        return 200

    def geturl(self):
        return "https://example.test/public"


class _Opener:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class PublicHttpBoundaryTests(unittest.TestCase):
    def test_https_get_is_proxy_free_bounded_and_monotonic(self):
        response = _Response(b'{"ok":true}')
        opener = _Opener(response)
        wall = (
            datetime(2026, 8, 26, 4, 4, tzinfo=timezone.utc),
            datetime(2026, 8, 26, 4, 4, 0, 100000, tzinfo=timezone.utc),
        )
        with patch.object(
            public_http, "build_opener", return_value=opener
        ) as built, patch.object(
            public_http, "_wall_now", side_effect=wall
        ), patch.object(
            public_http,
            "_monotonic",
            side_effect=(1_000_000_000, 1_100_000_000),
        ):
            actual = public_http.open_fixed_public_request(
                Request("https://example.test/public", method="GET"),
                max_body_bytes=32,
            )

        self.assertEqual(actual.status, 200)
        self.assertEqual(actual.final_url, "https://example.test/public")
        self.assertEqual(actual.body, b'{"ok":true}')
        self.assertEqual(actual.monotonic_rtt_ms, 100)
        self.assertEqual(actual.request_started_at, "2026-08-26T04:04:00.000Z")
        self.assertEqual(
            actual.response_received_at, "2026-08-26T04:04:00.100Z"
        )
        self.assertEqual(response.read_limits, [33])
        self.assertEqual(opener.calls[0][1], 15)
        self.assertEqual(built.call_args.args[0].proxies, {})

    def test_invalid_request_or_limit_fails_before_open(self):
        malformed = Request("https://example.test/public", method="GET")
        malformed.full_url = "https://[::1"
        cases = (
            (Request("http://example.test/public", method="GET"), 32,
             "PUBLIC_HTTP_REQUEST_INVALID"),
            (Request("https://example.test/public", method="POST"), 32,
             "PUBLIC_HTTP_REQUEST_INVALID"),
            (Request("https://example.test/public", method="GET"), True,
             "PUBLIC_HTTP_LIMIT_INVALID"),
            (Request("https://example.test/public", method="GET"), 0,
             "PUBLIC_HTTP_LIMIT_INVALID"),
            (Request("https://example.test/public", method="GET"),
             4 * 1024 * 1024 + 1, "PUBLIC_HTTP_LIMIT_INVALID"),
            (malformed, 32, "PUBLIC_HTTP_REQUEST_INVALID"),
        )
        with patch.object(
            public_http, "build_opener",
            side_effect=AssertionError("must fail before transport"),
        ):
            for request, limit, reason in cases:
                with self.subTest(reason=reason, limit=limit):
                    with self.assertRaises(public_http.PublicHttpError) as caught:
                        public_http.open_fixed_public_request(
                            request, max_body_bytes=limit
                        )
                    self.assertEqual(caught.exception.reason_code, reason)

    def test_credential_headers_fail_before_open(self):
        forbidden_headers = (
            {"Authorization": "Bearer sentinel"},
            {"Cookie": "session=sentinel"},
            {"X-MBX-APIKEY": "sentinel"},
            {"Proxy-Authorization": "Basic sentinel"},
        )
        with patch.object(
            public_http, "build_opener",
            side_effect=AssertionError("credentialed request reached transport"),
        ):
            for headers in forbidden_headers:
                with self.subTest(headers=tuple(headers)):
                    request = Request(
                        "https://example.test/public", method="GET", headers=headers
                    )
                    with self.assertRaises(public_http.PublicHttpError) as caught:
                        public_http.open_fixed_public_request(
                            request, max_body_bytes=32
                        )
                    self.assertEqual(
                        caught.exception.reason_code, "PUBLIC_HTTP_REQUEST_INVALID"
                    )

    def test_redirect_handler_rejects_without_following(self):
        with self.assertRaises(public_http.PublicHttpError) as caught:
            public_http._RejectRedirects().redirect_request(
                None, None, 302, "redirect", {}, "https://evil.example"
            )
        self.assertEqual(caught.exception.reason_code, "PUBLIC_HTTP_REDIRECT_FORBIDDEN")

    def test_http_error_response_is_returned_as_bounded_evidence(self):
        headers = Message()
        headers["Content-Type"] = "application/json"
        error = HTTPError(
            "https://example.test/public",
            429,
            "rate limited",
            headers,
            BytesIO(b'{"code":-1003}'),
        )
        wall = (
            datetime(2026, 8, 26, 4, 4, tzinfo=timezone.utc),
            datetime(2026, 8, 26, 4, 4, 0, 100000, tzinfo=timezone.utc),
        )
        with patch.object(
            public_http, "build_opener", return_value=_Opener(error)
        ), patch.object(
            public_http, "_wall_now", side_effect=wall
        ), patch.object(
            public_http, "_monotonic",
            side_effect=(1_000_000_000, 1_100_000_000),
        ):
            actual = public_http.open_fixed_public_request(
                Request("https://example.test/public", method="GET"),
                max_body_bytes=32,
            )
        self.assertEqual(actual.status, 429)
        self.assertEqual(actual.body, b'{"code":-1003}')
        self.assertEqual(actual.headers["Content-Type"], "application/json")

    def test_transport_failure_has_fixed_reason(self):
        with patch.object(
            public_http,
            "build_opener",
            return_value=_Opener(URLError("sentinel transport text")),
        ), patch.object(
            public_http,
            "_wall_now",
            return_value=datetime(2026, 8, 26, 4, 4, tzinfo=timezone.utc),
        ), patch.object(public_http, "_monotonic", return_value=1):
            with self.assertRaises(public_http.PublicHttpError) as caught:
                public_http.open_fixed_public_request(
                    Request("https://example.test/public", method="GET"),
                    max_body_bytes=32,
                )
        self.assertEqual(caught.exception.reason_code, "PUBLIC_HTTP_TRANSPORT_FAILURE")
        self.assertNotIn("sentinel", str(caught.exception))

    def test_oversize_body_fails_after_single_bounded_read(self):
        response = _Response(b"x" * 33)
        wall = (
            datetime(2026, 8, 26, 4, 4, tzinfo=timezone.utc),
            datetime(2026, 8, 26, 4, 4, 0, 100000, tzinfo=timezone.utc),
        )
        with patch.object(
            public_http, "build_opener", return_value=_Opener(response)
        ), patch.object(
            public_http, "_wall_now", side_effect=wall
        ), patch.object(
            public_http, "_monotonic",
            side_effect=(1_000_000_000, 1_100_000_000),
        ):
            with self.assertRaises(public_http.PublicHttpError) as caught:
                public_http.open_fixed_public_request(
                    Request("https://example.test/public", method="GET"),
                    max_body_bytes=32,
                )
        self.assertEqual(caught.exception.reason_code, "PUBLIC_HTTP_RESPONSE_INVALID")
        self.assertEqual(response.read_limits, [33])

    def test_backward_wall_or_monotonic_clock_fails_closed(self):
        cases = (
            (
                (
                    datetime(2026, 8, 26, 4, 4, 1, tzinfo=timezone.utc),
                    datetime(2026, 8, 26, 4, 4, tzinfo=timezone.utc),
                ),
                (1, 2),
            ),
            (
                (
                    datetime(2026, 8, 26, 4, 4, tzinfo=timezone.utc),
                    datetime(2026, 8, 26, 4, 4, 1, tzinfo=timezone.utc),
                ),
                (2, 1),
            ),
        )
        for wall, monotonic in cases:
            with self.subTest(wall=wall, monotonic=monotonic), patch.object(
                public_http,
                "build_opener",
                return_value=_Opener(_Response(b"{}")),
            ), patch.object(
                public_http, "_wall_now", side_effect=wall
            ), patch.object(
                public_http, "_monotonic", side_effect=monotonic
            ):
                with self.assertRaises(public_http.PublicHttpError) as caught:
                    public_http.open_fixed_public_request(
                        Request("https://example.test/public", method="GET"),
                        max_body_bytes=32,
                    )
                self.assertEqual(
                    caught.exception.reason_code, "PUBLIC_HTTP_RESPONSE_INVALID"
                )

    def test_attempt_document_records_exact_response_evidence(self):
        response = public_http.PublicHttpResponse(
            status=200,
            final_url="https://example.test/public",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Date": "Wed, 26 Aug 2026 04:04:00 GMT",
                "ETag": '"fixture"',
                "Last-Modified": "Wed, 26 Aug 2026 04:00:00 GMT",
                "Retry-After": "2",
            },
            body=b'{"ok":true}',
            monotonic_rtt_ms=100,
            request_started_at="2026-08-26T04:04:00.000Z",
            response_received_at="2026-08-26T04:04:00.100Z",
        )
        self.assertEqual(
            public_http.attempt_document(response, 2),
            {
                "sequence": 2,
                "outcome": "HTTP_RESPONSE",
                "error_reason_or_null": None,
                "request_started_at": "2026-08-26T04:04:00.000Z",
                "response_received_at": "2026-08-26T04:04:00.100Z",
                "status": 200,
                "final_url": "https://example.test/public",
                "selected_headers": {
                    "http_date_or_null": "Wed, 26 Aug 2026 04:04:00 GMT",
                    "etag_or_null": '"fixture"',
                    "last_modified_or_null": "Wed, 26 Aug 2026 04:00:00 GMT",
                    "retry_after_or_null": "2",
                },
                "body_size_bytes": 11,
                "body_sha256": (
                    "4062edaf750fb8074e7e83e0c9028c94"
                    "e32468a8b6f1614774328ef045150f93"
                ),
                "response_body_base64": "eyJvayI6dHJ1ZX0=",
            },
        )

    def test_http_200_attempt_requires_json_content_type(self):
        response = public_http.PublicHttpResponse(
            status=200,
            final_url="https://example.test/public",
            headers={"Content-Type": "text/plain"},
            body=b"{}",
            monotonic_rtt_ms=1,
            request_started_at="2026-08-26T04:04:00.000Z",
            response_received_at="2026-08-26T04:04:00.001Z",
        )
        with self.assertRaises(public_http.PublicHttpError) as caught:
            public_http.attempt_document(response, 1)
        self.assertEqual(caught.exception.reason_code, "PUBLIC_HTTP_RESPONSE_INVALID")

    def test_transport_failure_attempt_has_empty_exact_evidence(self):
        actual = public_http.transport_failure_attempt(
            3,
            started=datetime(2026, 8, 26, 4, 4, tzinfo=timezone.utc),
            received=datetime(
                2026, 8, 26, 4, 4, 0, 250000, tzinfo=timezone.utc
            ),
        )
        self.assertEqual(actual["sequence"], 3)
        self.assertEqual(actual["outcome"], "TRANSPORT_ERROR")
        self.assertEqual(actual["body_size_bytes"], 0)
        self.assertEqual(actual["response_body_base64"], "")
        self.assertEqual(
            actual["body_sha256"],
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855",
        )
        self.assertEqual(
            actual["error_reason_or_null"], "PUBLIC_HTTP_TRANSPORT_FAILURE"
        )


if __name__ == "__main__":
    unittest.main()
