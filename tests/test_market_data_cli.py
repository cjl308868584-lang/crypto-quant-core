import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import ProxyHandler
from unittest.mock import patch

import crypto_quant.market_data as market_data
from crypto_quant.market_data import (
    HistoricalArchiveRequest,
    HttpResponse,
    MarketDataError,
    PublicArchiveTransport,
    fetch_historical_market_data,
)


def archive_request():
    return HistoricalArchiveRequest.create(
        market="SPOT",
        data_family="KLINES",
        symbol="ETHUSDT",
        interval_or_null="1m",
        period_kind="DAILY",
        period="2024-01-02",
    )


def archive_bytes(request):
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    rows = []
    for minute in range(24 * 60):
        opened = start + timedelta(minutes=minute)
        closed = opened + timedelta(minutes=1) - timedelta(milliseconds=1)
        rows.append(
            f"{int(opened.timestamp() * 1000)},100,101,99,100,1,"
            f"{int(closed.timestamp() * 1000)},0,1,0,0,0"
        )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(request.expected_csv_name, ("\n".join(rows) + "\n").encode("ascii"))
    return output.getvalue()


class InMemoryTransport:
    def __init__(self, responses):
        self.responses = responses
        self.requested_urls = []

    def get(self, url):
        self.requested_urls.append(url)
        return self.responses[url]


def transport_for(request, *, archive_response=None, checksum_response=None):
    archive = archive_bytes(request)
    checksum = (
        f"{hashlib.sha256(archive).hexdigest()}  {request.archive_filename}\n"
    ).encode("ascii")
    return InMemoryTransport({
        request.archive_url: archive_response or HttpResponse(
            status=200,
            final_url=request.archive_url,
            headers={"ETag": '"archive-v1"', "Last-Modified": "Tue, 02 Jan 2024 00:00:00 GMT"},
            body=archive,
        ),
        request.checksum_url: checksum_response or HttpResponse(
            status=200,
            final_url=request.checksum_url,
            headers={},
            body=checksum,
        ),
    })


class FetchWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.request = archive_request()
        self.retrieved_at = "2026-07-27T00:00:00Z"

    def assert_reason(self, expected, callable_object, *args):
        with self.assertRaises(MarketDataError) as raised:
            callable_object(*args)
        self.assertEqual(raised.exception.reason_code, expected)

    def test_fetches_exactly_two_allowlisted_gets_and_binds_archive_http_validators(self):
        transport = transport_for(self.request)

        snapshot = fetch_historical_market_data(
            self.request, transport, self.retrieved_at
        )

        self.assertEqual(
            transport.requested_urls,
            [self.request.archive_url, self.request.checksum_url],
        )
        self.assertEqual(
            snapshot["source_receipt"]["source_etag_or_null"], '"archive-v1"'
        )
        self.assertEqual(
            snapshot["source_receipt"]["source_last_modified_at_or_null"],
            "Tue, 02 Jan 2024 00:00:00 GMT",
        )
        self.assertEqual(snapshot["ingested_at"], self.retrieved_at)
        self.assertEqual(snapshot["point_in_time_policy"], "ARCHIVE_REPLAY_ONLY")

    def test_rejects_redirect_to_a_host_outside_the_public_archive_allowlist(self):
        archive = archive_bytes(self.request)
        transport = transport_for(
            self.request,
            archive_response=HttpResponse(
                status=200,
                final_url="https://example.invalid/archive.zip",
                headers={},
                body=archive,
            ),
        )

        self.assert_reason(
            "HTTP_RESPONSE_REDIRECT_INVALID",
            fetch_historical_market_data,
            self.request,
            transport,
            self.retrieved_at,
        )

    def test_rejects_malformed_final_url_without_leaking_a_url_parser_error(self):
        transport = transport_for(
            self.request,
            archive_response=HttpResponse(
                status=200,
                final_url="https://data.binance.vision:invalid/archive.zip",
                headers={},
                body=archive_bytes(self.request),
            ),
        )

        self.assert_reason(
            "HTTP_RESPONSE_REDIRECT_INVALID",
            fetch_historical_market_data,
            self.request,
            transport,
            self.retrieved_at,
        )

    def test_rejects_malformed_ipv6_final_url_without_leaking_a_url_parser_error(self):
        transport = transport_for(
            self.request,
            archive_response=HttpResponse(
                status=200,
                final_url="https://[data.binance.vision/archive.zip",
                headers={},
                body=archive_bytes(self.request),
            ),
        )

        self.assert_reason(
            "HTTP_RESPONSE_REDIRECT_INVALID",
            fetch_historical_market_data,
            self.request,
            transport,
            self.retrieved_at,
        )

    def test_rejects_non_success_metadata_gaps_and_declared_content_limit(self):
        cases = (
            (
                "HTTP_STATUS_INVALID",
                HttpResponse(404, self.request.archive_url, {}, b"not found"),
            ),
            (
                "HTTP_RESPONSE_METADATA_INVALID",
                HttpResponse(200, None, {}, b""),
            ),
            (
                "HTTP_RESPONSE_TOO_LARGE",
                HttpResponse(
                    200,
                    self.request.archive_url,
                    {"Content-Length": str(64 * 1024 * 1024 + 1)},
                    b"",
                ),
            ),
        )
        for expected, response in cases:
            with self.subTest(expected=expected):
                self.assert_reason(
                    expected,
                    fetch_historical_market_data,
                    self.request,
                    transport_for(self.request, archive_response=response),
                    self.retrieved_at,
                )

    def test_verifies_official_checksum_before_invoking_the_parser(self):
        archive = archive_bytes(self.request)
        transport = transport_for(
            self.request,
            checksum_response=HttpResponse(
                200,
                self.request.checksum_url,
                {},
                b"0" * 64 + b"  ETHUSDT-1m-2024-01-02.zip\n",
            ),
        )

        with patch("crypto_quant.market_data.parse_market_facts") as parser:
            self.assert_reason(
                "CHECKSUM_DIGEST_MISMATCH",
                fetch_historical_market_data,
                self.request,
                transport,
                self.retrieved_at,
            )
        parser.assert_not_called()

    def test_concrete_transport_disables_environment_proxy_routing(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "https://proxy.invalid:8443"}):
            opener = market_data._public_archive_opener()

        self.assertFalse(
            any(isinstance(handler, ProxyHandler) for handler in opener.handlers)
        )
        self.assertEqual(len(opener.handle_open["https"]), 1)

    def test_checksum_read_is_bounded_to_its_own_limit_before_response_creation(self):
        class Response:
            def __init__(self):
                self.read_sizes = []

            def __enter__(self):
                return self

            def __exit__(self, *unused):
                return False

            def getcode(self):
                return 200

            def geturl(self):
                return self_url

            @property
            def headers(self):
                return {}

            def read(self, size):
                self.read_sizes.append(size)
                return b"x" * size

        class Opener:
            def open(self, request, timeout):
                return response

        self_url = self.request.checksum_url
        response = Response()
        with patch("crypto_quant.market_data._public_archive_opener", return_value=Opener()):
            self.assert_reason(
                "HTTP_RESPONSE_TOO_LARGE",
                PublicArchiveTransport().get,
                self_url,
            )
        self.assertEqual(response.read_sizes, [4 * 1024 + 1])


class MarketDataCliTests(unittest.TestCase):
    def setUp(self):
        self.request = archive_request()
        self.transport = transport_for(self.request)
        self.arguments = [
            "--market", "SPOT",
            "--data-family", "KLINES",
            "--symbol", "ETHUSDT",
            "--interval", "1m",
            "--period", "2024-01-02",
        ]

    def invoke(self, root, *, transport=None):
        from crypto_quant.market_data_cli import main

        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(
                [*self.arguments, "--output-root", str(root)],
                transport=transport or self.transport,
                clock=lambda: "2026-07-27T00:00:01Z",
            )
        return status, stdout.getvalue(), stderr.getvalue()

    def test_structured_arguments_write_a_canonical_artifact_below_selected_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "selected-root"
            status, stdout, stderr = self.invoke(root)

            self.assertEqual(status, 0)
            self.assertEqual(stderr, "")
            summary = json.loads(stdout)
            artifact = Path(summary["artifact_path"])
            self.assertTrue(artifact.is_relative_to(root.resolve()))
            self.assertEqual(artifact.parent, root.resolve() / "market-data")
            payload = artifact.read_bytes()
            self.assertEqual(payload, json.dumps(json.loads(payload), sort_keys=True, separators=(",", ":")).encode("utf-8"))
            snapshot = json.loads(payload)
            self.assertEqual(summary["snapshot_hash"], snapshot["snapshot_hash"])
            self.assertIn("source_receipt", snapshot)
            self.assertIn("quality_report", snapshot)

    def test_rejects_sensitive_or_arbitrary_endpoint_arguments(self):
        from crypto_quant.market_data_cli import main

        with tempfile.TemporaryDirectory() as temporary:
            for forbidden in ("--url", "--api-key", "--order", "--account"):
                with self.subTest(forbidden=forbidden):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        status = main([
                            *self.arguments,
                            "--output-root", temporary,
                            forbidden,
                            "value",
                        ])
                    self.assertNotEqual(status, 0)
                    self.assertIn("unrecognized arguments", stderr.getvalue())

    def test_identical_artifact_is_idempotent_but_conflicting_artifact_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self.invoke(root)
            artifact = Path(json.loads(first[1])["artifact_path"])
            first_inode = artifact.stat().st_ino
            second = self.invoke(root)
            self.assertEqual(first[0], 0)
            self.assertEqual(second[0], 0)
            self.assertFalse(json.loads(second[1])["created"])
            self.assertEqual(artifact.stat().st_ino, first_inode)
            artifact.write_bytes(b"conflicting")
            third = self.invoke(root, transport=transport_for(self.request))
            self.assertNotEqual(third[0], 0)
            self.assertEqual(artifact.read_bytes(), b"conflicting")

    def test_fetch_failure_leaves_no_final_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            failed = transport_for(
                self.request,
                archive_response=HttpResponse(500, self.request.archive_url, {}, b""),
            )
            status, _, _ = self.invoke(root, transport=failed)
            self.assertNotEqual(status, 0)
            self.assertFalse((root / "market-data").exists())

    def test_rejects_market_data_directory_symlink_without_writing_to_its_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            target = Path(temporary) / "target"
            root.mkdir()
            target.mkdir()
            (root / "market-data").symlink_to(target, target_is_directory=True)

            status, _, _ = self.invoke(root)

            self.assertNotEqual(status, 0)
            self.assertEqual(list(target.iterdir()), [])

    def test_rejects_final_symlink_and_hardlink_without_overwriting_them(self):
        from crypto_quant.market_data_cli import _artifact_bytes

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()
            snapshot = fetch_historical_market_data(
                self.request, self.transport, "2026-07-27T00:00:01Z"
            )
            artifact = root / "market-data" / (snapshot["snapshot_id"] + ".json")
            artifact.parent.mkdir()
            target = Path(temporary) / "target"
            target.write_bytes(b"target")
            artifact.symlink_to(target)
            status, _, _ = self.invoke(root)
            self.assertNotEqual(status, 0)
            self.assertEqual(target.read_bytes(), b"target")
            artifact.unlink()
            os.link(target, artifact)
            status, _, _ = self.invoke(root)
            self.assertNotEqual(status, 0)
            self.assertEqual(target.read_bytes(), b"target")
            self.assertEqual(os.stat(target).st_nlink, 2)

    def test_directory_replacement_during_publish_fails_without_creating_an_artifact(self):
        import crypto_quant.market_data_cli as cli

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()
            original_link = cli.os.link
            replaced = False

            def replace_directory_then_link(*args, **kwargs):
                nonlocal replaced
                if not replaced:
                    replaced = True
                    (root / "market-data").rename(root / "market-data-replaced")
                    (root / "market-data").mkdir()
                return original_link(*args, **kwargs)

            with patch("crypto_quant.market_data_cli.os.link", side_effect=replace_directory_then_link):
                status, _, _ = self.invoke(root)

            self.assertNotEqual(status, 0)
            self.assertEqual(list((root / "market-data").iterdir()), [])
            self.assertEqual(list((root / "market-data-replaced").iterdir()), [])

    def test_publisher_rolls_back_its_own_artifacts_when_link_fsync_or_cleanup_fails(self):
        import crypto_quant.market_data_cli as cli

        cases = ("link", "fsync", "cleanup")
        for fault in cases:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "root"
                root.mkdir()
                original_link = cli.os.link
                original_fsync = cli.os.fsync
                original_unlink = cli.os.unlink
                calls = {"fsync": 0, "cleanup": 0}

                def fail_link(*args, **kwargs):
                    if fault == "link":
                        raise OSError("link failed")
                    return original_link(*args, **kwargs)

                def fail_fsync(fd):
                    calls["fsync"] += 1
                    if fault == "fsync" and calls["fsync"] == 2:
                        raise OSError("directory fsync failed")
                    return original_fsync(fd)

                def fail_first_temp_cleanup(name, *args, **kwargs):
                    if fault == "cleanup" and str(name).startswith(".market-data-"):
                        calls["cleanup"] += 1
                        if calls["cleanup"] == 1:
                            raise OSError("cleanup failed")
                    return original_unlink(name, *args, **kwargs)

                with patch("crypto_quant.market_data_cli.os.link", side_effect=fail_link), patch(
                    "crypto_quant.market_data_cli.os.fsync", side_effect=fail_fsync
                ), patch("crypto_quant.market_data_cli.os.unlink", side_effect=fail_first_temp_cleanup):
                    status, _, _ = self.invoke(root)

                self.assertNotEqual(status, 0)
                output = root / "market-data"
                if output.exists():
                    self.assertEqual(list(output.iterdir()), [])

    def test_idempotent_returns_recheck_the_attached_directory_after_existing_and_collision_paths(self):
        import crypto_quant.market_data_cli as cli

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()
            first = self.invoke(root)
            artifact = Path(json.loads(first[1])["artifact_path"])
            original_read = cli._read_existing_artifact
            replaced = False

            def replace_after_existing_read(*args, **kwargs):
                nonlocal replaced
                value = original_read(*args, **kwargs)
                if value is not None and not replaced:
                    replaced = True
                    (root / "market-data").rename(root / "market-data-replaced")
                    (root / "market-data").mkdir()
                return value

            with patch(
                "crypto_quant.market_data_cli._read_existing_artifact",
                side_effect=replace_after_existing_read,
            ):
                status, _, _ = self.invoke(root)
            self.assertNotEqual(status, 0)
            self.assertTrue((root / "market-data-replaced" / artifact.name).exists())
            self.assertEqual(list((root / "market-data").iterdir()), [])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()
            snapshot = fetch_historical_market_data(
                self.request, self.transport, "2026-07-27T00:00:01Z"
            )
            payload = cli._artifact_bytes(snapshot)
            artifact_name = snapshot["snapshot_id"] + ".json"
            original_read = cli._read_existing_artifact
            reads = 0

            def missing_then_real(*args, **kwargs):
                nonlocal reads
                reads += 1
                return None if reads == 1 else original_read(*args, **kwargs)

            def collide_and_replace(*args, **kwargs):
                destination = root / "market-data" / artifact_name
                destination.write_bytes(payload)
                (root / "market-data").rename(root / "market-data-replaced")
                (root / "market-data").mkdir()
                raise FileExistsError

            with patch("crypto_quant.market_data_cli._read_existing_artifact", side_effect=missing_then_real), patch(
                "crypto_quant.market_data_cli.os.link", side_effect=collide_and_replace
            ):
                status, _, _ = self.invoke(root)
            self.assertNotEqual(status, 0)
            self.assertTrue((root / "market-data-replaced" / artifact_name).exists())
            self.assertEqual(list((root / "market-data").iterdir()), [])

    def test_precommit_failures_remove_their_temporary_inode(self):
        import crypto_quant.market_data_cli as cli

        for fault in ("write", "file_fsync", "initial_fstat", "post_write_fstat"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "root"
                root.mkdir()
                original_write = cli.os.write
                original_fsync = cli.os.fsync
                original_fstat = cli.os.fstat
                fstat_calls = 0

                def fail_write(*args, **kwargs):
                    if fault == "write":
                        raise OSError("write failed")
                    return original_write(*args, **kwargs)

                def fail_fsync(fd):
                    if fault == "file_fsync":
                        raise OSError("file fsync failed")
                    return original_fsync(fd)

                def fail_fstat(fd):
                    nonlocal fstat_calls
                    fstat_calls += 1
                    if (fault == "initial_fstat" and fstat_calls == 2) or (
                        fault == "post_write_fstat" and fstat_calls == 3
                    ):
                        raise OSError("fstat failed")
                    return original_fstat(fd)

                with patch("crypto_quant.market_data_cli.os.write", side_effect=fail_write), patch(
                    "crypto_quant.market_data_cli.os.fsync", side_effect=fail_fsync
                ), patch("crypto_quant.market_data_cli.os.fstat", side_effect=fail_fstat):
                    status, _, _ = self.invoke(root)

                self.assertNotEqual(status, 0)
                self.assertEqual(list((root / "market-data").iterdir()), [])

    def test_post_commit_close_errors_do_not_report_failure_and_resolve_runs_before_publish(self):
        import crypto_quant.market_data_cli as cli

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            original_close = cli.os.close
            close_calls = 0

            def fail_directory_closes(fd):
                nonlocal close_calls
                close_calls += 1
                if close_calls >= 2:
                    raise OSError("post-commit close failed")
                return original_close(fd)

            with patch("crypto_quant.market_data_cli.os.close", side_effect=fail_directory_closes):
                status, stdout, _ = self.invoke(root)
            self.assertEqual(status, 0)
            self.assertTrue(Path(json.loads(stdout)["artifact_path"]).exists())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            with patch("crypto_quant.market_data_cli.Path.resolve", side_effect=OSError("resolve failed")):
                status, _, _ = self.invoke(root)
            self.assertNotEqual(status, 0)
            self.assertFalse((root / "market-data").exists())
