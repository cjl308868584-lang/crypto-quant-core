import ast
import ctypes
import errno
import importlib.util
import os
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "src"
    / "crypto_quant"
    / "challenger_replacement_supersession_publish.py"
)


def _load_publisher():
    spec = importlib.util.spec_from_file_location("v064_public_publisher", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("PUBLISHER_IMPORT_SPEC_INVALID")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _require_linux_when_requested(platform_name, linux_required, euid=None):
    effective_uid = os.geteuid() if euid is None else euid
    if linux_required == "1":
        if platform_name != "linux":
            raise AssertionError("UNSUPPORTED_TEST_HOST")
        if effective_uid != 501:
            raise AssertionError("FIXED_OWNER_UID_501_REQUIRED")
    return platform_name == "linux"


def _snapshot(path):
    opened = path.stat()
    return (
        path.read_bytes(),
        stat.S_IMODE(opened.st_mode),
        opened.st_size,
        opened.st_mtime_ns,
        opened.st_ctime_ns,
        opened.st_dev,
        opened.st_ino,
        opened.st_nlink,
    )


def _publisher_parent():
    base = Path("/private/tmp") if sys.platform == "darwin" else Path(tempfile.gettempdir())
    temporary = tempfile.TemporaryDirectory(dir=base)
    parent = Path(temporary.name) / "artifacts" / "challenger-replacement"
    parent.mkdir(parents=True, mode=0o755)
    parent.chmod(0o755)
    return temporary, parent


def _child_environment():
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(ROOT / "src"),
    }


RAW_RACE_CHILD = r'''import os, sys, time
from pathlib import Path
import crypto_quant.challenger_replacement_supersession_publish as module
parent, staging, start = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
deadline = time.monotonic() + 5
while not start.exists():
    if time.monotonic() >= deadline:
        raise SystemExit(90)
    time.sleep(0.005)
descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
try:
    module._atomic_no_replace(descriptor, staging, "raw-final")
except FileExistsError:
    print("EEXIST")
else:
    print("SUCCESS")
finally:
    os.close(descriptor)
'''


CRASH_CHILD = r'''import os, sys
from pathlib import Path
import crypto_quant.challenger_replacement_supersession_publish as module
module._artifact_parent = lambda: Path(sys.argv[1])
scenario = sys.argv[2]
if scenario == "partial-write":
    def partial(descriptor, data):
        os.write(descriptor, data[:2])
        raise module.SupersessionPublishError("CHALLENGER_REPLACEMENT_SUPERSESSION_WRITE_FAILED")
    module._write_all = partial
elif scenario == "file-fsync":
    real = module._fsync_retry
    count = 0
    def fail_file_fsync(descriptor):
        global count
        count += 1
        if count == 1:
            raise module.SupersessionPublishError("CHALLENGER_REPLACEMENT_SUPERSESSION_FSYNC_FAILED")
        return real(descriptor)
    module._fsync_retry = fail_file_fsync
elif scenario == "no-replace":
    def fail_no_replace(*unused):
        raise module.SupersessionPublishError("CHALLENGER_REPLACEMENT_SUPERSESSION_ATOMIC_NOREPLACE_FAILED")
    module._atomic_no_replace = fail_no_replace
elif scenario == "directory-fsync":
    real = module._fsync_retry
    count = 0
    def fail_directory_fsync(descriptor):
        global count
        count += 1
        if count == 2:
            raise module.SupersessionPublishError("CHALLENGER_REPLACEMENT_SUPERSESSION_FSYNC_FAILED")
        return real(descriptor)
    module._fsync_retry = fail_directory_fsync
try:
    module.publish_challenger_replacement_plan_v2_bytes(b'{"fresh":true}\n')
except module.SupersessionPublishError as error:
    print(error.reason_code)
    raise SystemExit(17)
raise SystemExit(99)
'''


RETRY_CHILD = r'''import sys
from pathlib import Path
import crypto_quant.challenger_replacement_supersession_publish as module
module._artifact_parent = lambda: Path(sys.argv[1])
try:
    result = module.publish_challenger_replacement_plan_v2_bytes(b'{"fresh":true}\n')
except module.SupersessionPublishError as error:
    print(error.reason_code)
    raise SystemExit(18)
print(result["status"])
'''


FIFO_READ_CHILD = r'''import os, sys
from pathlib import Path
import crypto_quant.challenger_replacement_supersession_publish as module
parent, name = Path(sys.argv[1]), sys.argv[2]
descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
try:
    module._read_final(descriptor, name)
except module.SupersessionPublishError as error:
    print(error.reason_code)
    raise SystemExit(17)
finally:
    os.close(descriptor)
raise SystemExit(99)
'''


EXPECTED_TEST_IMPORTS = {
    "ast",
    "ctypes",
    "errno",
    "importlib.util",
    "os",
    "pathlib",
    "socket",
    "stat",
    "subprocess",
    "sys",
    "tempfile",
    "time",
    "unittest",
}


EXPECTED_PUBLISHER_IMPORTS = {
    "ctypes",
    "errno",
    "hashlib",
    "os",
    "pathlib",
    "platform",
    "re",
    "secrets",
    "stat",
    "sys",
    "typing",
}


def _imports_from_source(source, filename):
    names = set()
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {
                "__import__",
                "import_module",
            }:
                names.add("DYNAMIC_IMPORT_FORBIDDEN")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in {
                "__import__",
                "import_module",
            }:
                names.add("DYNAMIC_IMPORT_FORBIDDEN")
    return names


def _direct_imports(path):
    return _imports_from_source(path.read_text(encoding="utf-8"), str(path))


def _contains_email(body):
    atom = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._+-"
    domain = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-"
    for index, value in enumerate(body):
        if value != ord("@"):
            continue
        left = index
        while left and body[left - 1] in atom:
            left -= 1
        right = index + 1
        while right < len(body) and body[right] in domain:
            right += 1
        candidate = body[index + 1 : right]
        if left < index and b"." in candidate and not candidate.startswith(b"."):
            return True
    return False


def _object_snapshot(path):
    opened = path.lstat()
    body = path.read_bytes() if stat.S_ISREG(opened.st_mode) else None
    return (
        body,
        opened.st_mode,
        opened.st_size,
        opened.st_mtime_ns,
        opened.st_ctime_ns,
        opened.st_dev,
        opened.st_ino,
        opened.st_nlink,
    )


class V064StaticAndPortableBoundaryTests(unittest.TestCase):
    def test_linux_required_mode_fails_closed_on_non_linux(self):
        with self.assertRaisesRegex(AssertionError, "UNSUPPORTED_TEST_HOST"):
            _require_linux_when_requested("darwin", "1")

    def test_local_darwin_mode_and_required_linux_mode_are_distinct(self):
        self.assertFalse(_require_linux_when_requested("darwin", "0"))
        self.assertTrue(_require_linux_when_requested("linux", "1", euid=501))

    def test_fixed_publisher_loads_without_package_import(self):
        module = _load_publisher()
        self.assertEqual(
            module.__file__,
            str(MODULE_PATH),
        )

    def test_current_platform_noreplace_preserves_existing_sentinel(self):
        module = _load_publisher()
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging = parent / "staging"
            final = parent / "final"
            staging.write_bytes(b"new")
            final.write_bytes(b"sentinel")
            final.chmod(0o600)
            before = final.stat()
            descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(FileExistsError):
                    module._atomic_no_replace(
                        descriptor,
                        staging.name,
                        final.name,
                    )
            finally:
                os.close(descriptor)
            after = final.stat()
            self.assertEqual(final.read_bytes(), b"sentinel")
            self.assertEqual(
                (
                    stat.S_IMODE(after.st_mode),
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                    after.st_dev,
                    after.st_ino,
                    after.st_nlink,
                ),
                (
                    stat.S_IMODE(before.st_mode),
                    before.st_size,
                    before.st_mtime_ns,
                    before.st_ctime_ns,
                    before.st_dev,
                    before.st_ino,
                    before.st_nlink,
                ),
            )
            self.assertTrue(staging.is_file())

    def test_symlink_hardlink_fifo_socket_directory_and_wrong_mode_fail_before_io(self):
        module = _load_publisher()
        case_names = ("symlink", "hardlink", "socket", "directory", "wrong-mode", "wrong-uid")
        for case_name in case_names:
            with self.subTest(case_name=case_name), tempfile.TemporaryDirectory() as raw:
                parent = Path(raw)
                target = parent / "target"
                sentinel = parent / "sentinel"
                sentinel.write_bytes(b"sentinel")
                sentinel.chmod(0o600)
                listener = None
                if case_name == "symlink":
                    target.symlink_to(sentinel)
                elif case_name == "hardlink":
                    sentinel.chmod(0o644)
                    os.link(sentinel, target)
                elif case_name == "socket":
                    listener = socket.socket(socket.AF_UNIX)
                    listener.bind(str(target))
                elif case_name == "directory":
                    target.mkdir()
                else:
                    target.write_bytes(b"sentinel")
                    target.chmod(0o644 if case_name == "wrong-uid" else 0o600)
                before = _object_snapshot(target)
                descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                started = time.monotonic()
                original_trusted = module._trusted_file_stat
                original_read = module._read_exact_descriptor
                original_fstat = module.os.fstat
                reads = 0

                def tracked_read(*args, **kwargs):
                    nonlocal reads
                    reads += 1
                    return original_read(*args, **kwargs)

                class StatWithWrongUid:
                    def __init__(self, value):
                        self._value = value
                        self.st_uid = value.st_uid + 1

                    def __getattr__(self, name):
                        return getattr(self._value, name)

                def fstat_with_wrong_uid(fd):
                    return StatWithWrongUid(original_fstat(fd))

                try:
                    if case_name == "wrong-uid":
                        module._read_exact_descriptor = tracked_read
                        module.os.fstat = fstat_with_wrong_uid
                    with self.assertRaises(module.SupersessionPublishError):
                        module._read_final(descriptor, target.name)
                finally:
                    module._trusted_file_stat = original_trusted
                    module._read_exact_descriptor = original_read
                    module.os.fstat = original_fstat
                    os.close(descriptor)
                    if listener is not None:
                        listener.close()
                self.assertLess(time.monotonic() - started, 1.0)
                self.assertEqual(_object_snapshot(target), before)
                self.assertEqual(sentinel.read_bytes(), b"sentinel")
                if case_name == "wrong-uid":
                    self.assertEqual(reads, 0)

        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            fifo = parent / "fifo"
            os.mkfifo(fifo, 0o600)
            before = _object_snapshot(fifo)
            process = subprocess.Popen(
                [sys.executable, "-c", FIFO_READ_CHILD, str(parent), fifo.name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_child_environment(),
            )
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
                self.fail("FIFO_READ_BLOCKED_BEFORE_FSTAT")
            self.assertEqual(process.returncode, 17, stderr)
            self.assertIn(b"FINAL_UNTRUSTED", stdout)
            self.assertEqual(_object_snapshot(fifo), before)

    def test_required_file_flags_fail_closed_when_missing_or_zero(self):
        module = _load_publisher()
        for flag_name in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"):
            original = getattr(module.os, flag_name)
            for scenario in ("zero", "none", "missing"):
                try:
                    if scenario == "missing":
                        delattr(module.os, flag_name)
                    else:
                        setattr(module.os, flag_name, 0 if scenario == "zero" else None)
                    with self.subTest(flag_name=flag_name, scenario=scenario), self.assertRaisesRegex(
                        module.SupersessionPublishError,
                        "PLATFORM_UNSUPPORTED",
                    ):
                        module._required_flag(flag_name)
                finally:
                    setattr(module.os, flag_name, original)

    def test_unsupported_symbol_flags_and_errnos_never_fall_back(self):
        module = _load_publisher()
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            (parent / "staging").write_bytes(b"new")
            descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            original_cdll = module.ctypes.CDLL
            try:
                module.ctypes.CDLL = lambda *unused, **unused_keywords: object()
                with self.assertRaisesRegex(
                    module.SupersessionPublishError,
                    "ATOMIC_NOREPLACE_UNSUPPORTED",
                ):
                    module._atomic_no_replace(descriptor, "staging", "final")

                class FailingPrimitive:
                    argtypes = None
                    restype = None

                    def __init__(self, code):
                        self.code = code

                    def __call__(self, *unused):
                        ctypes.set_errno(self.code)
                        return -1

                attribute = "renameatx_np" if sys.platform == "darwin" else "renameat2"
                for code in {
                    errno.ENOSYS,
                    getattr(errno, "EOPNOTSUPP", errno.ENOSYS),
                    getattr(errno, "ENOTSUP", errno.ENOSYS),
                }:
                    library = type("Library", (), {})()
                    setattr(library, attribute, FailingPrimitive(code))
                    module.ctypes.CDLL = lambda *unused, _library=library, **unused_keywords: _library
                    with self.subTest(code=code), self.assertRaisesRegex(
                        module.SupersessionPublishError,
                        "ATOMIC_NOREPLACE_UNSUPPORTED",
                    ):
                        module._atomic_no_replace(descriptor, "staging", "final")
                self.assertTrue((parent / "staging").is_file())
                self.assertFalse((parent / "final").exists())
            finally:
                module.ctypes.CDLL = original_cdll
                os.close(descriptor)

    def test_short_write_eintr_and_close_paths_are_deterministic(self):
        module = _load_publisher()
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "target"
            descriptor = os.open(target, os.O_CREAT | os.O_RDWR, 0o600)
            original_write = module.os.write
            calls = 0

            def interrupted_short_write(fd, data):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise InterruptedError()
                if calls == 2:
                    return original_write(fd, data[:2])
                return original_write(fd, data)

            try:
                module.os.write = interrupted_short_write
                module._write_all(descriptor, b"abcdef")
            finally:
                module.os.write = original_write
                os.close(descriptor)
            self.assertEqual(target.read_bytes(), b"abcdef")
            self.assertEqual(calls, 3)

            descriptor = os.open(target, os.O_RDONLY)
            original_close = module.os.close
            try:
                module.os.close = lambda unused: (_ for _ in ()).throw(OSError(errno.EIO, "close"))
                with self.assertRaisesRegex(module.SupersessionPublishError, "CLOSE_FAILED"):
                    module._close(descriptor)
            finally:
                module.os.close = original_close
                original_close(descriptor)

    def test_post_fsync_attachment_and_orphan_inventory_block_success(self):
        module = _load_publisher()
        if os.geteuid() != 501:
            return
        temporary, parent = _publisher_parent()
        original_parent = module._artifact_parent
        try:
            module._artifact_parent = lambda: parent
            descriptor, expected = module._open_parent()
            displaced = parent.with_name("challenger-replacement-displaced")
            parent.rename(displaced)
            parent.mkdir(mode=0o755)
            parent.chmod(0o755)
            try:
                with self.assertRaisesRegex(module.SupersessionPublishError, "PARENT_INVALID"):
                    module._validate_parent(descriptor, expected)
            finally:
                os.close(descriptor)
            parent.rmdir()
            displaced.rename(parent)

            sentinel = Path(temporary.name) / "attachment-sentinel"
            sentinel.write_bytes(b"attachment")
            sentinel.chmod(0o600)
            before = _snapshot(sentinel)
            original_fsync = module._fsync_retry
            calls = 0

            def replace_after_file_fsync(descriptor):
                nonlocal calls
                original_fsync(descriptor)
                calls += 1
                if calls == 1:
                    staging = next(parent.glob(".v064-supersession-*.staging"))
                    staging.unlink()
                    staging.symlink_to(sentinel)

            module._fsync_retry = replace_after_file_fsync
            try:
                with self.assertRaisesRegex(module.SupersessionPublishError, "STAGING_UNTRUSTED"):
                    module.publish_challenger_replacement_plan_v2_bytes(b"attachment\n")
            finally:
                module._fsync_retry = original_fsync
            self.assertEqual(_snapshot(sentinel), before)

            for entry in parent.glob(".v064-supersession-*.staging"):
                entry.unlink()

            orphan = parent / (
                ".v064-supersession-plan-" + "a" * 64 + "-" + "b" * 32 + ".staging"
            )
            orphan.write_bytes(b"sealed")
            orphan.chmod(0o644)
            orphan_before = _snapshot(orphan)
            with self.assertRaisesRegex(
                module.SupersessionPublishError,
                "RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED",
            ):
                module.publish_challenger_replacement_plan_v2_bytes(b"plan\n")
            self.assertEqual(_snapshot(orphan), orphan_before)
        finally:
            module._artifact_parent = original_parent
            temporary.cleanup()

    def test_every_rejection_preserves_full_sentinel_snapshot(self):
        module = _load_publisher()
        if os.geteuid() != 501:
            return
        temporary, parent = _publisher_parent()
        original_parent = module._artifact_parent
        try:
            module._artifact_parent = lambda: parent
            sentinel = Path(temporary.name) / "external-sentinel"
            sentinel.write_bytes(b"external")
            sentinel.chmod(0o600)
            for case_name in ("symlink", "hardlink"):
                final = parent / "challenger-replacement-plan-v0.64.0.json"
                if case_name == "symlink":
                    final.symlink_to(sentinel)
                else:
                    os.link(sentinel, final)
                before = _snapshot(sentinel)
                with self.subTest(case_name=case_name), self.assertRaises(
                    module.SupersessionPublishError
                ):
                    module.publish_challenger_replacement_plan_v2_bytes(b"plan\n")
                self.assertEqual(_snapshot(sentinel), before)
                final.unlink()
        finally:
            module._artifact_parent = original_parent
            temporary.cleanup()

    def test_publisher_close_failure_never_reports_success_and_each_fd_closes_once(self):
        module = _load_publisher()
        if os.geteuid() != 501:
            return
        temporary, parent = _publisher_parent()
        original_parent = module._artifact_parent
        original_close = module._close
        close_attempts = {}

        def close_once_then_fail(descriptor):
            close_attempts[descriptor] = close_attempts.get(descriptor, 0) + 1
            original_close(descriptor)
            if len(close_attempts) == 1:
                raise module.SupersessionPublishError(
                    "CHALLENGER_REPLACEMENT_SUPERSESSION_CLOSE_FAILED"
                )

        try:
            module._artifact_parent = lambda: parent
            module._close = close_once_then_fail
            with self.assertRaisesRegex(module.SupersessionPublishError, "CLOSE_FAILED"):
                module.publish_challenger_replacement_plan_v2_bytes(b"close\n")
            self.assertTrue(close_attempts)
            self.assertEqual(set(close_attempts.values()), {1})
        finally:
            module._close = original_close
            module._artifact_parent = original_parent
            temporary.cleanup()

    def test_public_module_executes_with_only_allowlisted_imports_and_safe_bytes(self):
        self.assertEqual(_direct_imports(Path(__file__).resolve()), EXPECTED_TEST_IMPORTS)
        self.assertEqual(_direct_imports(MODULE_PATH), EXPECTED_PUBLISHER_IMPORTS)
        for name, child_source in (
            ("RAW_RACE_CHILD", RAW_RACE_CHILD),
            ("CRASH_CHILD", CRASH_CHILD),
            ("RETRY_CHILD", RETRY_CHILD),
            ("FIFO_READ_CHILD", FIFO_READ_CHILD),
        ):
            child_imports = _imports_from_source(child_source, name)
            self.assertNotIn("DYNAMIC_IMPORT_FORBIDDEN", child_imports)
            publisher_import = (
                "crypto_quant.challenger_replacement_supersession_publish"
            )
            self.assertEqual(
                child_imports,
                {publisher_import, "os", "pathlib", "sys", "time"}
                if name == "RAW_RACE_CHILD"
                else {publisher_import, "os", "pathlib", "sys"}
                if name in {"CRASH_CHILD", "FIFO_READ_CHILD"}
                else {publisher_import, "pathlib", "sys"},
            )

        publisher_body = MODULE_PATH.read_bytes()
        for forbidden in (
            b"os." + b"rename(",
            b"os." + b"replace(",
            b"os." + b"link(",
            b"syscall(",
        ):
            self.assertNotIn(forbidden, publisher_body)
        for path in (Path(__file__).resolve(), MODULE_PATH):
            body = path.read_bytes()
            lowered = body.lower()
            self.assertNotIn(b"\x00", body)
            self.assertNotIn(b"\r\n", body)
            for forbidden in (
                b"/" + b"Users/",
                b"http" + b"://",
                b"https" + b"://",
                b"BEGIN " + b"PRIVATE KEY",
                b"gh" + b"p_",
                b"github_" + b"pat_",
                b"@" + b"example.",
                b"production" + b"_root",
            ):
                self.assertNotIn(forbidden, body)
            self.assertFalse(_contains_email(body))
            for forbidden_token in (
                b"strat" + b"egy",
                b"econ" + b"omic",
                b"bro" + b"ker",
                b"ord" + b"er",
                b"cred" + b"ential",
            ):
                self.assertNotIn(forbidden_token, lowered)


class V064ActualLinuxBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.linux_host = _require_linux_when_requested(
            sys.platform,
            os.environ.get("V064_PUBLIC_LINUX_REQUIRED", "0"),
        )

    def _owner_required(self):
        return self.linux_host and os.geteuid() == 501

    def test_actual_renameat2_noreplace_preserves_existing_sentinel(self):
        if not self.linux_host:
            return
        module = _load_publisher()
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging = parent / "staging"
            final = parent / "final"
            staging.write_bytes(b"new")
            final.write_bytes(b"sentinel")
            before = final.stat()
            descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(FileExistsError):
                    module._atomic_no_replace(descriptor, staging.name, final.name)
            finally:
                os.close(descriptor)
            after = final.stat()
            self.assertEqual(final.read_bytes(), b"sentinel")
            self.assertEqual((after.st_dev, after.st_ino), (before.st_dev, before.st_ino))

    def test_two_fresh_interpreters_yield_one_success_and_one_eexist(self):
        if not self.linux_host:
            return
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            staging_names = ("raw-staging-a", "raw-staging-b")
            for name in staging_names:
                (parent / name).write_bytes(name.encode("ascii"))
            start = parent / "start"
            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", RAW_RACE_CHILD, str(parent), name, str(start)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=_child_environment(),
                )
                for name in staging_names
            ]
            start.touch()
            outcomes = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stderr)
                outcomes.append(stdout.strip())
            self.assertEqual(sorted(outcomes), [b"EEXIST", b"SUCCESS"])
            self.assertEqual((parent / "raw-final").stat().st_nlink, 1)

    def test_fresh_process_replays_file_fsync_and_noreplace_crash_boundaries(self):
        if not self._owner_required():
            return
        for scenario in ("partial-write", "file-fsync", "no-replace"):
            with self.subTest(scenario=scenario):
                temporary, parent = _publisher_parent()
                try:
                    crashed = subprocess.run(
                        [sys.executable, "-c", CRASH_CHILD, str(parent), scenario],
                        capture_output=True,
                        env=_child_environment(),
                        timeout=10,
                    )
                    self.assertEqual(crashed.returncode, 17, crashed.stderr)
                    retried = subprocess.run(
                        [sys.executable, "-c", RETRY_CHILD, str(parent)],
                        capture_output=True,
                        env=_child_environment(),
                        timeout=10,
                    )
                    self.assertEqual(retried.returncode, 18, retried.stderr)
                    self.assertIn(b"RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED", retried.stdout)
                    self.assertEqual(
                        (parent / "challenger-replacement-plan-v0.64.0.json").read_bytes(),
                        b'{"fresh":true}\n',
                    )
                finally:
                    temporary.cleanup()

    def test_fresh_process_repairs_visible_final_after_directory_fsync_failure(self):
        if not self._owner_required():
            return
        temporary, parent = _publisher_parent()
        try:
            crashed = subprocess.run(
                [sys.executable, "-c", CRASH_CHILD, str(parent), "directory-fsync"],
                capture_output=True,
                env=_child_environment(),
                timeout=10,
            )
            self.assertEqual(crashed.returncode, 17, crashed.stderr)
            final = parent / "challenger-replacement-plan-v0.64.0.json"
            inode = final.stat().st_ino
            retried = subprocess.run(
                [sys.executable, "-c", RETRY_CHILD, str(parent)],
                capture_output=True,
                env=_child_environment(),
                timeout=10,
            )
            self.assertEqual(retried.returncode, 0, retried.stderr)
            self.assertEqual(retried.stdout, b"ALREADY_PUBLISHED\n")
            self.assertEqual(final.stat().st_ino, inode)
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
