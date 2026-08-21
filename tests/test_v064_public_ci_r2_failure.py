import hashlib
import inspect
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.v064_public_ci_r2_failure import (
    V064PublicCiR2FailureError,
    derive_v064_public_ci_r2_failure,
    load_v064_public_ci_r2_failure,
    load_v064_public_ci_r2_failure_root,
)
from crypto_quant import v064_public_ci_r2_failure


ROOT = Path(__file__).resolve().parents[1]
RAW = {
    "run": (363, "310d2cad6840dc80d4cbcd6cc229d32704fd3c8854b44b6bbd893b708d4f9986"),
    "jobs": (2312, "3078337f2f8e5aa9add1b099391e19125d5dcdeaef803e1f50d9666716ad773c"),
    "log": (105558, "e6ee2bcf599cff56b0bcda8292bdb7a85e5ef186973f4fe3a14c67f97a0bbf47"),
}
ARTIFACT_NAMES = {
    "run": "v064-public-ci-r2-run-api-v1.json",
    "jobs": "v064-public-ci-r2-jobs-api-v1.json",
    "log": "v064-public-ci-r2-run-log-v1.txt",
    "record": "v064-public-ci-r2-failure-record-v1.json",
}
ARTIFACT_ROOT = ROOT / "artifacts" / "v064-public-ci-r2-failure"
PRIVATE_TMP_FIXTURES = {
    "run": Path("/private/tmp/v064-r2-failure-32328770160-run-api.json"),
    "jobs": Path("/private/tmp/v064-r2-failure-32328770160-jobs-api.json"),
    "log": Path("/private/tmp/v064-r2-run-32328770160.log"),
}


def _canonical(value):
    return canonical_json(value).encode("utf-8") + b"\n"


def _write_all(descriptor, body):
    view = memoryview(body)
    offset = 0
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise AssertionError("short fixture write")
        offset += written


def _read_exact(descriptor, size):
    body = bytearray()
    while len(body) < size:
        try:
            chunk = os.read(descriptor, size - len(body))
        except InterruptedError:
            continue
        if not chunk:
            raise AssertionError("short fixture read")
        body.extend(chunk)
    while True:
        try:
            extra = os.read(descriptor, 1)
        except InterruptedError:
            continue
        if extra:
            raise AssertionError("fixture read has trailing bytes")
        return bytes(body)


def _snapshot(path):
    value = path.lstat()
    result = (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    return result, path.read_bytes() if stat.S_ISREG(value.st_mode) else None


def _publish_once(root, name, body):
    """Test-only ceremony for final R2 evidence names."""
    flags = os.O_NOFOLLOW | os.O_NONBLOCK
    parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | flags)
    descriptor = None
    try:
        try:
            descriptor = os.open(
                name,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | flags,
                0o600,
                dir_fd=parent_fd,
            )
        except FileExistsError:
            before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            descriptor = os.open(name, os.O_RDONLY | flags, dir_fd=parent_fd)
            try:
                existing = _read_exact(descriptor, len(body))
            except AssertionError:
                existing = b""
            self_stat = os.fstat(descriptor)
            after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if existing != body or not stat.S_ISREG(self_stat.st_mode) or self_stat.st_uid != os.getuid() or self_stat.st_nlink != 1 or stat.S_IMODE(self_stat.st_mode) != 0o644 or (before.st_dev, before.st_ino) != (self_stat.st_dev, self_stat.st_ino) or (after.st_dev, after.st_ino) != (self_stat.st_dev, self_stat.st_ino):
                raise AssertionError("pre-existing final is not exact and trusted")
            return
        _write_all(descriptor, body)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if _read_exact(descriptor, len(body)) != body:
            raise AssertionError("same-fd readback mismatch")
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o644)
        attached = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(descriptor)
        if (attached.st_dev, attached.st_ino) != (opened.st_dev, opened.st_ino) or not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid() or opened.st_nlink != 1 or stat.S_IMODE(opened.st_mode) != 0o644:
            raise AssertionError("published final is untrusted")
        os.fsync(descriptor)
        os.fsync(parent_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


class V064PublicCiR2FailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bodies = {
            "run": (ARTIFACT_ROOT / ARTIFACT_NAMES["run"]).read_bytes(),
            "jobs": (ARTIFACT_ROOT / ARTIFACT_NAMES["jobs"]).read_bytes(),
            "log": (ARTIFACT_ROOT / ARTIFACT_NAMES["log"]).read_bytes(),
        }
        for name, body in cls.bodies.items():
            if len(body) != RAW[name][0]:
                raise AssertionError("unexpected %s fixture size" % name)
            if hashlib.sha256(body).hexdigest() != RAW[name][1]:
                raise AssertionError("unexpected %s fixture hash" % name)
        for name in ("run", "jobs"):
            if not cls.bodies[name].endswith(b"\n"):
                raise AssertionError("%s fixture must end in LF" % name)
            if cls.bodies[name] != _canonical(json.loads(cls.bodies[name])):
                raise AssertionError("%s fixture must be canonical JSON" % name)
        if all(path.is_file() for path in PRIVATE_TMP_FIXTURES.values()):
            for name, path in PRIVATE_TMP_FIXTURES.items():
                if path.read_bytes() != cls.bodies[name]:
                    raise AssertionError("private temporary %s fixture drifted" % name)

    def derive(self, **changes):
        bodies = dict(self.bodies)
        bodies.update(changes)
        return derive_v064_public_ci_r2_failure(
            run_bytes=bodies["run"], jobs_bytes=bodies["jobs"], log_bytes=bodies["log"]
        )

    def test_derives_closed_r2_semantic_failure_from_exact_readback(self):
        value = self.derive()
        self.assertEqual(value["status"], "PUBLIC_LINUX_PORTABILITY_WITNESS_DID_NOT_PASS")
        self.assertEqual(value["reason_code"], "PUBLIC_MATRIX_INTERPRETER_IDENTITY_MISMATCH")
        self.assertEqual(value["readback_provenance"], "POST_RUN_READ_ONLY_READBACK")
        self.assertEqual(value["private_source"], {
            "candidate_commit": "5bc01c9b9b9d9a21846dd8c6ba1d81b0183dd219",
            "candidate_tree": "53d3baf7d7c84e5bc8fcafa2561bbb959477ac4d",
        })
        self.assertEqual(value["public_source"], {
            "repository": "cjl308868584-lang/crypto-quant-v064-public-ci-r2",
            "root_commit": "5541aba00e4e93e6389c2c61a81e69c2dd228947",
            "root_tree": "3d732e8e1fbb9cf94541f6e26e778d5eb21ca8f3",
        })
        self.assertEqual(value["workflow"], {"path": ".github/workflows/ci.yml", "blob_oid": "ba5b6851ed53ad79100409b92c78c09c07608ed2"})
        self.assertEqual(value["bundle"], {"manifest_sha256": "b2017d2e4099ee64d0cbbcbd35f38b1833fbe351d2696f70248ad60056b20ae2", "file_set_sha256": "6c6d5bde35d1f5f4e484f5874b47fad3d0f575eef4eeb8e4deb9de659be4eb69"})
        self.assertEqual(value["run"], {"run_id": 32328770160, "run_attempt": 1, "event": "push", "head_branch": "main", "status": "completed", "github_conclusion": "success"})
        self.assertEqual(value["expected_python_versions"], ["3.9", "3.12"])
        self.assertEqual(value["observed_fixed_owner_versions"], ["3.12.3", "3.12.3"])
        self.assertEqual(value["jobs"], [
            {"python_version": "3.9", "job_id": 96305223463, "github_conclusion": "success", "observed_fixed_owner_version": "3.12.3"},
            {"python_version": "3.12", "job_id": 96305223215, "github_conclusion": "success", "observed_fixed_owner_version": "3.12.3"},
        ])
        self.assertFalse(value["success_witness_published"])
        self.assertEqual(value["safety"], {"production_activation": False, "credentials_present": False, "broker_allowed": False, "orders_allowed": False, "runtime_state_write_allowed": False})
        self.assertEqual(value["raw_evidence"]["run_api"], {"path": "artifacts/v064-public-ci-r2-failure/v064-public-ci-r2-run-api-v1.json", "size": RAW["run"][0], "sha256": RAW["run"][1]})

    def test_closed_derivation_rejects_identity_and_semantic_mutations(self):
        cases = (
            ("run", b"cjl308868584-lang/crypto-quant-v064-public-ci-r2", b"attacker/repository", "V064_PUBLIC_CI_R2_RUN_INVALID"),
            ("run", b"5541aba00e4e93e6389c2c61a81e69c2dd228947", b"0" * 40, "V064_PUBLIC_CI_R2_RUN_INVALID"),
            ("run", b"32328770160", b"32328770161", "V064_PUBLIC_CI_R2_RUN_INVALID"),
            ("jobs", b"96305223463", b"96305223464", "V064_PUBLIC_CI_R2_JOBS_INVALID"),
            ("jobs", b"portability (3.9)", b"portability (3.8)", "V064_PUBLIC_CI_R2_JOBS_INVALID"),
            ("run", b'"conclusion":"success"', b'"conclusion":"failure"', "V064_PUBLIC_CI_R2_RUN_INVALID"),
            ("log", b"source_candidate_f=5bc01c9b9b9d9a21846dd8c6ba1d81b0183dd219", b"source_candidate_f=0", "V064_PUBLIC_CI_R2_LOG_INVALID"),
            ("log", b"Python 3.12.3", b"Python 3.11.9", "V064_PUBLIC_CI_R2_LOG_INVALID"),
        )
        for source, old, new, reason in cases:
            with self.subTest(source=source, old=old):
                mutated = self.bodies[source].replace(old, new, 1)
                with self.assertRaisesRegex(V064PublicCiR2FailureError, "^" + reason + "$"):
                    self.derive(**{source: mutated})

    def test_rejects_noncanonical_api_bytes(self):
        run = json.loads(self.bodies["run"])
        noncanonical = json.dumps(run, indent=2).encode("utf-8") + b"\n"
        with self.assertRaisesRegex(V064PublicCiR2FailureError, "^V064_PUBLIC_CI_R2_RUN_INVALID$"):
            self.derive(run=noncanonical)

    def test_rejects_well_formed_raw_hash_only_drift_after_semantic_parsing(self):
        drifted = self.bodies["log"].replace(b"03:35:31", b"03:35:32", 1)
        with self.assertRaisesRegex(V064PublicCiR2FailureError, "^V064_PUBLIC_CI_R2_RAW_EVIDENCE_INVALID$"):
            self.derive(log=drifted)

    def test_requires_setup_python_and_fixed_owner_test_completion_markers(self):
        cases = (
            (b"Successfully set up CPython (3.9.25)", b"Successfully set up CPython (3.9.24)"),
            (b"Ran 16 tests in", b"Ran 15 tests in"),
            (b"Z OK\n", b"Z NO\n"),
        )
        for old, new in cases:
            with self.subTest(old=old):
                with self.assertRaisesRegex(V064PublicCiR2FailureError, "^V064_PUBLIC_CI_R2_LOG_INVALID$"):
                    self.derive(log=self.bodies["log"].replace(old, new, 1))

    def test_derivation_api_accepts_only_the_three_raw_byte_inputs(self):
        signature = inspect.signature(derive_v064_public_ci_r2_failure)
        self.assertEqual(tuple(signature.parameters), ("run_bytes", "jobs_bytes", "log_bytes"))
        self.assertTrue(all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values()))

    def test_schema_mirrors_and_accepts_the_derived_record(self):
        config = (ROOT / "config/v064-public-ci-r2-failure-record-v1.schema.json").read_bytes()
        package = (ROOT / "src/crypto_quant/schemas/v064-public-ci-r2-failure-record-v1.schema.json").read_bytes()
        self.assertEqual(config, package)
        Draft202012Validator(json.loads(config)).validate(self.derive())

    def test_schema_rejects_reordered_jobs_and_nonfrozen_raw_identity(self):
        schema = Draft202012Validator(json.loads((ROOT / "config/v064-public-ci-r2-failure-record-v1.schema.json").read_bytes()))
        reordered = self.derive()
        reordered["jobs"].reverse()
        with self.assertRaises(Exception):
            schema.validate(reordered)
        altered = self.derive()
        altered["raw_evidence"]["run_api"]["path"] = "other.json"
        with self.assertRaises(Exception):
            schema.validate(altered)

    def test_test_only_publication_then_production_loader_replays_exact_files(self):
        record = self.derive()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "artifacts" / "v064-public-ci-r2-failure"
            root.mkdir(parents=True)
            for key in ("run", "jobs", "log"):
                _publish_once(root, ARTIFACT_NAMES[key], self.bodies[key])
            _publish_once(root, ARTIFACT_NAMES["record"], _canonical(record))
            for key in ("run", "jobs", "log"):
                path = root / ARTIFACT_NAMES[key]
                self.assertEqual(path.read_bytes(), self.bodies[key])
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(load_v064_public_ci_r2_failure_root(root), record)
            self.assertEqual(load_v064_public_ci_r2_failure(root / ARTIFACT_NAMES["record"]), record)

    def test_loader_requires_exact_inventory_and_absent_formal_success_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = Path(temporary) / "artifacts"
            root = artifacts / "v064-public-ci-r2-failure"
            shutil.copytree(ARTIFACT_ROOT, root)
            self.assertEqual(load_v064_public_ci_r2_failure_root(root)["reason_code"], "PUBLIC_MATRIX_INTERPRETER_IDENTITY_MISMATCH")
            (root / "unexpected.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(V064PublicCiR2FailureError, "^V064_PUBLIC_CI_R2_ROOT_INVENTORY_INVALID$"):
                load_v064_public_ci_r2_failure_root(root)
            (root / "unexpected.json").unlink()
            (artifacts / "v064-public-ci-r2").mkdir()
            with self.assertRaisesRegex(V064PublicCiR2FailureError, "^V064_PUBLIC_CI_R2_SUCCESS_ROOT_PRESENT$"):
                load_v064_public_ci_r2_failure_root(root)
            (artifacts / "v064-public-ci-r2").rmdir()
            (artifacts / "v064-public-ci-r2").symlink_to("missing-success-root")
            with self.assertRaisesRegex(V064PublicCiR2FailureError, "^V064_PUBLIC_CI_R2_SUCCESS_ROOT_PRESENT$"):
                load_v064_public_ci_r2_failure_root(root)

    def test_final_replay_requires_no_follow_and_nonblocking_open(self):
        expected = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        with mock.patch("crypto_quant.v064_public_ci_r2_failure.os.open", wraps=os.open) as opened:
            self.assertEqual(load_v064_public_ci_r2_failure_root(ARTIFACT_ROOT)["status"], "PUBLIC_LINUX_PORTABILITY_WITNESS_DID_NOT_PASS")
        self.assertTrue(any(call.args[1] & expected == expected for call in opened.call_args_list))

    def test_test_only_publisher_replays_existing_final_without_blocking(self):
        body = b"fixture\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _publish_once(root, "fixture.json", body)
            expected = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            with mock.patch("tests.test_v064_public_ci_r2_failure.os.open", wraps=os.open) as opened:
                _publish_once(root, "fixture.json", body)
            self.assertTrue(any(call.args[1] & expected == expected for call in opened.call_args_list))

    def test_file_replay_preserves_unexpected_primary_through_close_failure(self):
        real_close = os.close
        real_open = os.open
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _publish_once(root, "fixture.json", b"fixture\n")
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
            opened = []

            def open_and_record(*arguments, **kwargs):
                descriptor = real_open(*arguments, **kwargs)
                if arguments[0] == "fixture.json":
                    opened.append(descriptor)
                return descriptor

            closed = []

            def close_after_real_cleanup(descriptor):
                closed.append(descriptor)
                real_close(descriptor)
                raise OSError("close")
            try:
                with mock.patch("crypto_quant.v064_public_ci_r2_failure.os.open", side_effect=open_and_record), mock.patch("crypto_quant.v064_public_ci_r2_failure.os.read", side_effect=KeyboardInterrupt), mock.patch("crypto_quant.v064_public_ci_r2_failure.os.close", side_effect=close_after_real_cleanup):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        v064_public_ci_r2_failure._read_final(parent_fd, "fixture.json", "TEST")
                self.assertEqual(closed, opened)
                self.assertEqual(len(closed), 1)
                self.assertIsInstance(caught.exception.close_error, OSError)
            finally:
                real_close(parent_fd)

    def test_root_replay_preserves_unexpected_primary_through_close_failure(self):
        real_close = os.close
        real_open = os.open
        opened = []
        closed = []

        def open_and_record(*arguments, **kwargs):
            descriptor = real_open(*arguments, **kwargs)
            if isinstance(arguments[0], Path):
                opened.append(descriptor)
            return descriptor

        def close_after_real_cleanup(descriptor):
            closed.append(descriptor)
            real_close(descriptor)
            raise OSError("close")

        with mock.patch("crypto_quant.v064_public_ci_r2_failure.os.open", side_effect=open_and_record), mock.patch("crypto_quant.v064_public_ci_r2_failure.os.listdir", side_effect=KeyboardInterrupt), mock.patch("crypto_quant.v064_public_ci_r2_failure.os.close", side_effect=close_after_real_cleanup):
            with self.assertRaises(KeyboardInterrupt) as caught:
                load_v064_public_ci_r2_failure_root(ARTIFACT_ROOT)
        self.assertEqual(closed, list(reversed(opened)))
        self.assertEqual(len(closed), 2)
        self.assertIsInstance(caught.exception.close_error, OSError)

    def test_root_replay_closes_owned_descriptors_after_first_close_failure(self):
        real_close = os.close
        real_open = os.open
        roles_by_descriptor = {}
        close_attempts = []
        injected_close_error = OSError("close")

        def open_and_track_role(*arguments, **kwargs):
            descriptor = real_open(*arguments, **kwargs)
            if arguments[0] == ARTIFACT_ROOT.parent:
                roles_by_descriptor[descriptor] = "artifacts-parent"
            elif arguments[0] == ARTIFACT_ROOT:
                roles_by_descriptor[descriptor] = "failure-root"
            return descriptor

        def close_after_real_cleanup(descriptor):
            role = roles_by_descriptor.get(descriptor)
            if role is not None:
                close_attempts.append(role)
            real_close(descriptor)
            if role == "failure-root":
                raise injected_close_error

        with mock.patch("crypto_quant.v064_public_ci_r2_failure.os.open", side_effect=open_and_track_role), mock.patch("crypto_quant.v064_public_ci_r2_failure.os.listdir", side_effect=KeyboardInterrupt), mock.patch("crypto_quant.v064_public_ci_r2_failure.os.close", side_effect=close_after_real_cleanup):
            with self.assertRaises(KeyboardInterrupt) as caught:
                load_v064_public_ci_r2_failure_root(ARTIFACT_ROOT)
        self.assertEqual(close_attempts, ["failure-root", "artifacts-parent"])
        self.assertEqual({role: close_attempts.count(role) for role in roles_by_descriptor.values()}, {"failure-root": 1, "artifacts-parent": 1})
        self.assertIs(caught.exception.close_error, injected_close_error)

    def test_loader_rechecks_success_root_after_private_stat_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = Path(temporary) / "artifacts"
            root = artifacts / "v064-public-ci-r2-failure"
            shutil.copytree(ARTIFACT_ROOT, root)
            real_fstat = os.fstat
            calls = 0
            initial_absence_observed = False

            def fstat_and_publish(descriptor):
                nonlocal calls
                value = real_fstat(descriptor)
                calls += 1
                if calls == 2:
                    self.assertTrue(initial_absence_observed)
                    (artifacts / "v064-public-ci-r2").mkdir()
                return value

            real_stat = os.stat

            def stat_and_record(path, *arguments, **kwargs):
                nonlocal initial_absence_observed
                if path == "v064-public-ci-r2" and arguments == ():
                    initial_absence_observed = True
                return real_stat(path, *arguments, **kwargs)

            with mock.patch("crypto_quant.v064_public_ci_r2_failure.os.fstat", side_effect=fstat_and_publish), mock.patch("crypto_quant.v064_public_ci_r2_failure.os.stat", side_effect=stat_and_record):
                with self.assertRaisesRegex(V064PublicCiR2FailureError, "^V064_PUBLIC_CI_R2_SUCCESS_ROOT_PRESENT$"):
                    load_v064_public_ci_r2_failure_root(root)
            self.assertTrue(initial_absence_observed)

    def test_test_only_publisher_new_final_retries_short_reads_and_eintr(self):
        real_read = os.read
        interrupted = False

        def short_read(descriptor, count):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise InterruptedError()
            return real_read(descriptor, min(1, count))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch("tests.test_v064_public_ci_r2_failure.os.read", side_effect=short_read):
                _publish_once(root, "fixture.json", b"fixture\n")
            self.assertEqual((root / "fixture.json").read_bytes(), b"fixture\n")

    def test_test_only_publisher_rejects_special_or_untrusted_existing_final(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sentinel = root / "sentinel"
            sentinel.write_bytes(b"unchanged")
            cases = []
            link = root / "link.json"; link.symlink_to(sentinel); cases.append(link)
            hard = root / "hard.json"; os.link(sentinel, hard); cases.append(hard)
            mode = root / "mode.json"; mode.write_bytes(b"fixture\n"); mode.chmod(0o600); cases.append(mode)
            for path in cases:
                with self.subTest(path=path.name):
                    before = _snapshot(path)
                    sentinel_before = _snapshot(sentinel)
                    with self.assertRaises(Exception):
                        _publish_once(root, path.name, b"fixture\n")
                    self.assertEqual(_snapshot(path), before)
                    self.assertEqual(_snapshot(sentinel), sentinel_before)

    def test_test_only_publisher_rejects_fifo_in_fresh_bounded_child_without_side_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sentinel = root / "sentinel"; sentinel.write_bytes(b"unchanged")
            fifo = root / "fifo.json"; os.mkfifo(fifo)
            before = _snapshot(fifo); sentinel_before = _snapshot(sentinel)
            code = (
                "from pathlib import Path\n"
                "from tests.test_v064_public_ci_r2_failure import _publish_once\n"
                "import sys\n"
                "try:\n"
                "    _publish_once(Path(sys.argv[1]), 'fifo.json', b'fixture\\n')\n"
                "except AssertionError as error:\n"
                "    if str(error) == 'pre-existing final is not exact and trusted':\n"
                "        raise SystemExit(0)\n"
                "    raise\n"
                "raise SystemExit(1)\n"
            )
            environment = dict(os.environ, PYTHONPATH="src:.")
            child = subprocess.Popen((sys.executable, "-c", code, str(root)), cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                stdout, stderr = child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                stdout, stderr = child.communicate()
                self.fail("FIFO publisher child exceeded bounded timeout: stdout=%r stderr=%r" % (stdout, stderr))
            self.assertEqual((child.returncode, stdout, stderr), (0, b"", b""))
            self.assertEqual(_snapshot(fifo), before)
            self.assertEqual(_snapshot(sentinel), sentinel_before)


if __name__ == "__main__":
    unittest.main()
