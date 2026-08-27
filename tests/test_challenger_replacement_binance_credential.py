import dataclasses
import hashlib
import json
import os
from pathlib import Path
import pickle
import socket
import stat
import subprocess
import sys
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

from importlib import resources
from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_binance_private_protocol import (
    build_binance_private_request,
)
from crypto_quant.challenger_replacement_binance_credential import (
    BinanceCredentialError,
    _consume_binance_authorization,
    open_binance_credential_capability,
)


class BinanceCredentialCapabilityTests(unittest.TestCase):
    API_KEY = "A" * 32
    SECRET = "B" * 32

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "owner-only"
        self.root.mkdir(mode=0o700)
        self.path = self.root / "binance-hmac.json"
        body = (canonical_json({
            "api_key": self.API_KEY,
            "hmac_secret": self.SECRET,
        }) + "\n").encode("utf-8")
        self.path.write_bytes(body)
        self.path.chmod(0o600)
        self.reference = self._reference(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def _reference(self, path):
        parent = path.parent.stat()
        entry = path.stat()
        return {
            "$schema": "./challenger-replacement-binance-credential-reference-v1.schema.json",
            "schema_version": "1.0.0",
            "absolute_path": str(path),
            "parent_device": parent.st_dev,
            "parent_inode": parent.st_ino,
            "file_device": entry.st_dev,
            "file_inode": entry.st_ino,
            "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def _request(self):
        return build_binance_private_request(
            "SPOT_ACCOUNT", {}, timestamp_ms=1_787_788_800_000
        )

    def _reason(self, reference=None):
        with self.assertRaises(BinanceCredentialError) as caught:
            open_binance_credential_capability(
                reference=self.reference if reference is None else reference,
                expected_owner_uid=os.getuid(),
            )
        return caught.exception.reason_code

    def _snapshot(self, path):
        entry = path.stat()
        return (
            path.read_bytes(), stat.S_IMODE(entry.st_mode), entry.st_size,
            entry.st_dev, entry.st_ino, entry.st_nlink,
            entry.st_mtime_ns, entry.st_ctime_ns,
        )

    def test_owner_only_exact_file_opens_authorizes_once_and_redacts(self):
        capability = open_binance_credential_capability(
            reference=self.reference, expected_owner_uid=os.getuid()
        )
        self.assertEqual(capability.identity.device, self.path.stat().st_dev)
        self.assertEqual(capability.identity.inode, self.path.stat().st_ino)
        self.assertEqual(capability.identity.owner_uid, os.getuid())
        self.assertEqual(capability.identity.file_sha256,
                         self.reference["file_sha256"])
        self.assertEqual(capability.identity.key_fingerprint,
                         hashlib.sha256(self.API_KEY.encode()).hexdigest())
        authorization = capability.authorize(self._request())
        diagnostic = repr(capability) + repr(authorization)
        self.assertNotIn(self.API_KEY, diagnostic)
        self.assertNotIn(self.SECRET, diagnostic)
        self.assertFalse(hasattr(capability, "__dict__"))
        self.assertFalse(hasattr(authorization, "__dict__"))
        self.assertEqual(
            {name for name in dir(capability) if not name.startswith("_")},
            {"authorize", "close", "identity"},
        )
        self.assertEqual(
            {name for name in dir(authorization) if not name.startswith("_")},
            {"close"},
        )
        with self.assertRaises(TypeError):
            dataclasses.asdict(authorization)
        request, api_key, parameters = _consume_binance_authorization(
            authorization
        )
        self.assertEqual(request, self._request())
        self.assertEqual(bytes(api_key), self.API_KEY.encode())
        self.assertIn(b"&signature=", bytes(parameters))
        with self.assertRaises(BinanceCredentialError) as caught:
            _consume_binance_authorization(authorization)
        self.assertEqual(caught.exception.reason_code,
                         "BINANCE_CREDENTIAL_AUTHORIZATION_ALREADY_USED")
        authorization.close()
        self.assertEqual(set(api_key), {0})
        self.assertEqual(set(parameters), {0})
        with self.assertRaises(TypeError):
            pickle.dumps(authorization)
        retained_api_key = capability._api_key
        retained_secret = capability._secret
        capability.close()
        self.assertEqual(set(retained_api_key), {0})
        self.assertEqual(set(retained_secret), {0})
        with self.assertRaises(TypeError):
            pickle.dumps(capability)

    def test_reference_and_json_are_strict(self):
        capability = open_binance_credential_capability(
            reference=MappingProxyType(self.reference),
            expected_owner_uid=os.getuid(),
        )
        capability.close()
        for mutate in (
            lambda value: value.update(extra=True),
            lambda value: value.update(absolute_path="relative/key.json"),
            lambda value: value.update(file_inode=True),
            lambda value: value.update(file_sha256="A" * 64),
        ):
            candidate = dict(self.reference)
            mutate(candidate)
            with self.subTest(candidate=candidate):
                self.assertEqual(self._reason(candidate),
                                 "BINANCE_CREDENTIAL_REFERENCE_INVALID")
        self.path.write_bytes(
            b'{"api_key":"' + self.API_KEY.encode() +
            b'","api_key":"' + self.API_KEY.encode() +
            b'","hmac_secret":"' + self.SECRET.encode() + b'"}\n'
        )
        self.reference = self._reference(self.path)
        self.assertEqual(self._reason(), "BINANCE_CREDENTIAL_FORMAT_INVALID")

    def test_untrusted_types_links_mode_and_size_fail_without_sentinel_change(self):
        sentinel = self.root / "sentinel"
        sentinel.write_bytes(b"never touch me")
        sentinel.chmod(0o600)
        cases = []
        symlink = self.root / "symlink"
        symlink.symlink_to(sentinel)
        cases.append((symlink, "symlink"))
        hardlink = self.root / "hardlink"
        os.link(sentinel, hardlink)
        cases.append((hardlink, "hardlink"))
        fifo = self.root / "fifo"
        os.mkfifo(fifo, 0o600)
        cases.append((fifo, "fifo"))
        directory = self.root / "directory"
        directory.mkdir(mode=0o600)
        cases.append((directory, "directory"))
        sock_path = self.root / "socket"
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(sock_path))
        cases.append((sock_path, "socket"))
        wrong_mode = self.root / "wrong-mode"
        wrong_mode.write_bytes(b"{}\n")
        wrong_mode.chmod(0o644)
        cases.append((wrong_mode, "mode"))
        oversize = self.root / "oversize"
        oversize.write_bytes(b"x" * 8193)
        oversize.chmod(0o600)
        cases.append((oversize, "oversize"))
        before = self._snapshot(sentinel)
        try:
            for candidate, label in cases:
                with self.subTest(label=label):
                    reference = dict(self.reference)
                    entry = os.lstat(candidate)
                    reference.update(
                        absolute_path=str(candidate),
                        file_device=entry.st_dev,
                        file_inode=entry.st_ino,
                        file_sha256="0" * 64,
                    )
                    self.assertIn(self._reason(reference), {
                        "BINANCE_CREDENTIAL_FILE_UNTRUSTED",
                        "BINANCE_CREDENTIAL_FILE_INVALID",
                    })
                    self.assertEqual(self._snapshot(sentinel), before)
        finally:
            sock.close()

    def test_fifo_rejection_is_nonblocking_in_a_fresh_interpreter(self):
        fifo = self.root / "fresh-fifo"
        os.mkfifo(fifo, 0o600)
        entry = os.lstat(fifo)
        reference = dict(
            self.reference,
            absolute_path=str(fifo),
            file_device=entry.st_dev,
            file_inode=entry.st_ino,
            file_sha256="0" * 64,
        )
        script = (
            "import json,os,sys;"
            "from crypto_quant.challenger_replacement_binance_credential "
            "import open_binance_credential_capability as o,BinanceCredentialError as E;"
            "r=json.loads(sys.argv[1]);"
            "\ntry:o(reference=r,expected_owner_uid=os.getuid())"
            "\nexcept E as e:print(e.reason_code)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script, json.dumps(reference)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1,
        )
        self.assertEqual(
            result.stdout.strip(), b"BINANCE_CREDENTIAL_FILE_UNTRUSTED"
        )

    def test_missing_required_platform_flags_fails_before_open(self):
        for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"):
            with self.subTest(name=name), \
                    patch("crypto_quant.challenger_replacement_binance_credential.os.open") as opened, \
                    patch(
                        "crypto_quant.challenger_replacement_binance_credential._open_flag",
                        side_effect=lambda candidate, missing=name: (
                            None if candidate == missing else getattr(os, candidate)
                        ),
                    ):
                self.assertEqual(
                    self._reason(), "BINANCE_CREDENTIAL_PLATFORM_UNSUPPORTED"
                )
                opened.assert_not_called()

    def test_parent_and_file_identity_replacement_fail_closed(self):
        changed_parent = dict(self.reference, parent_inode=self.reference["parent_inode"] + 1)
        changed_file = dict(self.reference, file_inode=self.reference["file_inode"] + 1)
        self.assertEqual(self._reason(changed_parent),
                         "BINANCE_CREDENTIAL_PARENT_CHANGED")
        self.assertEqual(self._reason(changed_file),
                         "BINANCE_CREDENTIAL_FILE_UNTRUSTED")

    def test_open_capability_detects_parent_rename_and_same_bytes_new_inode(self):
        capability = open_binance_credential_capability(
            reference=self.reference, expected_owner_uid=os.getuid()
        )
        old_root = self.root.with_name("detached-owner-only")
        self.root.rename(old_root)
        self.root.mkdir(mode=0o700)
        try:
            with self.assertRaises(BinanceCredentialError) as caught:
                capability.authorize(self._request())
            self.assertEqual(caught.exception.reason_code,
                             "BINANCE_CREDENTIAL_ATTACHMENT_CHANGED")
        finally:
            capability.close()
            self.root.rmdir()
            old_root.rename(self.root)

        capability = open_binance_credential_capability(
            reference=self.reference, expected_owner_uid=os.getuid()
        )
        exact = self.path.read_bytes()
        self.path.unlink()
        self.path.write_bytes(exact)
        self.path.chmod(0o600)
        try:
            with self.assertRaises(BinanceCredentialError) as caught:
                capability.authorize(self._request())
            self.assertEqual(caught.exception.reason_code,
                             "BINANCE_CREDENTIAL_ATTACHMENT_CHANGED")
        finally:
            capability.close()

    def test_same_inode_same_size_credential_rewrite_is_rejected(self):
        capability = open_binance_credential_capability(
            reference=self.reference, expected_owner_uid=os.getuid()
        )
        before = self.path.stat()
        replacement = (canonical_json({
            "api_key": "C" * 32,
            "hmac_secret": "D" * 32,
        }) + "\n").encode("utf-8")
        self.assertEqual(len(replacement), before.st_size)
        with self.path.open("r+b", buffering=0) as stream:
            stream.write(replacement)
            stream.flush()
            os.fsync(stream.fileno())
        after = self.path.stat()
        self.assertEqual((after.st_dev, after.st_ino, after.st_size),
                         (before.st_dev, before.st_ino, before.st_size))
        self.assertNotEqual((after.st_mtime_ns, after.st_ctime_ns),
                            (before.st_mtime_ns, before.st_ctime_ns))
        try:
            with self.assertRaises(BinanceCredentialError) as caught:
                capability.authorize(self._request())
            self.assertEqual(caught.exception.reason_code,
                             "BINANCE_CREDENTIAL_ATTACHMENT_CHANGED")
        finally:
            capability.close()

    def test_replacement_during_read_is_rejected_and_opened_fds_close_once(self):
        import crypto_quant.challenger_replacement_binance_credential as module

        real_read = module._read
        real_open = os.open
        real_close = os.close
        opened = []
        closed = []

        def recording_open(*args, **kwargs):
            descriptor = real_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor

        def recording_close(descriptor):
            closed.append(descriptor)
            return real_close(descriptor)

        def replace_after_read(descriptor, size):
            body = real_read(descriptor, size)
            exact = self.path.read_bytes()
            self.path.unlink()
            self.path.write_bytes(exact)
            self.path.chmod(0o600)
            return body

        with patch.object(module.os, "open", side_effect=recording_open), \
                patch.object(module.os, "close", side_effect=recording_close), \
                patch.object(module, "_read", side_effect=replace_after_read):
            self.assertEqual(self._reason(),
                             "BINANCE_CREDENTIAL_FILE_UNTRUSTED")
        self.assertEqual(sorted(opened), sorted(closed))
        self.assertEqual(len(closed), len(set(closed)))

    def test_public_endpoint_cannot_receive_credential_authorization(self):
        capability = open_binance_credential_capability(
            reference=self.reference, expected_owner_uid=os.getuid()
        )
        try:
            request = build_binance_private_request(
                "SPOT_SERVER_TIME", {}, timestamp_ms=0
            )
            with self.assertRaises(BinanceCredentialError) as caught:
                capability.authorize(request)
            self.assertEqual(caught.exception.reason_code,
                             "BINANCE_CREDENTIAL_AUTHORIZATION_INVALID")
        finally:
            capability.close()

    def test_close_failure_is_fixed_and_every_descriptor_is_attempted_once(self):
        import crypto_quant.challenger_replacement_binance_credential as module

        capability = open_binance_credential_capability(
            reference=self.reference, expected_owner_uid=os.getuid()
        )
        descriptors = {capability._parent_fd, capability._file_fd}
        calls = []
        real_close = os.close

        def fail_close(descriptor):
            calls.append(descriptor)
            if descriptor in descriptors:
                raise OSError("injected close failure")
            return real_close(descriptor)

        with patch.object(module.os, "close", side_effect=fail_close):
            with self.assertRaises(BinanceCredentialError) as caught:
                capability.close()
        self.assertEqual(caught.exception.reason_code,
                         "BINANCE_CREDENTIAL_CLOSE_FAILED")
        self.assertEqual(set(calls), descriptors)
        self.assertEqual(len(calls), 2)
        for descriptor in descriptors:
            real_close(descriptor)

    def test_context_close_failure_does_not_override_primary_exception(self):
        import crypto_quant.challenger_replacement_binance_credential as module

        capability = open_binance_credential_capability(
            reference=self.reference, expected_owner_uid=os.getuid()
        )
        descriptors = {capability._parent_fd, capability._file_fd}
        real_close = os.close

        def fail_close(descriptor):
            if descriptor in descriptors:
                raise OSError("injected close failure")
            return real_close(descriptor)

        with patch.object(module.os, "close", side_effect=fail_close):
            with self.assertRaisesRegex(RuntimeError, "primary failure") as caught:
                with capability:
                    raise RuntimeError("primary failure")
        self.assertEqual(
            getattr(caught.exception, "close_failure_reason_code", None),
            "BINANCE_CREDENTIAL_CLOSE_FAILED",
        )
        for descriptor in descriptors:
            real_close(descriptor)

    def test_reference_schema_is_strict_and_matches_runtime_contract(self):
        schema = json.loads(resources.files("crypto_quant").joinpath(
            "schemas",
            "challenger-replacement-binance-credential-reference-v1.schema.json",
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(self.reference)), [])
        extra = dict(self.reference, api_key=self.API_KEY)
        self.assertTrue(list(validator.iter_errors(extra)))


if __name__ == "__main__":
    unittest.main()
