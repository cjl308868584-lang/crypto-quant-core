"""Fixed GitHub evidence acquisition boundary for the v0.64 witness."""

import argparse
import hashlib
import os
import selectors
import stat
import subprocess
import sys
import time
from typing import Any, Dict, Sequence, Tuple

from .canonical import canonical_json


_GH = "/Users/chenm4/.local/bin/gh"
_REPOSITORY = "cjl308868584-lang/crypto-quant-v064-public-ci-r2"
_GH_SHA256 = "b1d6c442fde99ca27c04e1e74d624895abe37785f4a3e9e9b684bf7586ce4bc8"
_GH_VERSION = (
    b"gh version 2.96.0 (2026-07-02)\n"
    b"https://github.com/cli/cli/releases/tag/v2.96.0\n"
)
_GH_HOME = "/Users/chenm4"
_GH_ENV = {
    "HOME": _GH_HOME, "PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C",
}
_RUN_PROJECTION = "{id,workflow_id,run_attempt,event,head_branch,head_sha,status,conclusion,created_at,updated_at,path,repository:.repository.full_name}"
_JOBS_PROJECTION = "{total_count,jobs:[.jobs[]|{id,name,status,conclusion,runner_name,labels,started_at,completed_at,steps:[.steps[]|{number,name,status,conclusion}]}]}"


def _run_id(value: str) -> int:
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ValueError("V064_PUBLIC_CI_RUN_ID_INVALID")
    parsed = int(value)
    if parsed < 1 or parsed > (1 << 53) - 1 or str(parsed) != value:
        raise ValueError("V064_PUBLIC_CI_RUN_ID_INVALID")
    return parsed


def _commands(run_id: int) -> Tuple[Tuple[str, ...], ...]:
    value = str(run_id)
    prefix = "repos/%s/actions/runs/%s" % (_REPOSITORY, value)
    return (
        (_GH, "api", prefix, "--jq", _RUN_PROJECTION),
        (_GH, "api", prefix + "/jobs?filter=all&per_page=100", "--jq", _JOBS_PROJECTION),
        (_GH, "run", "view", value, "--repo", _REPOSITORY, "--log"),
    )


def _gh_file_sha256() -> str:
    descriptor = None
    digest = hashlib.sha256()
    try:
        opened_path = os.lstat(_GH)
        if (
            not stat.S_ISREG(opened_path.st_mode)
            or opened_path.st_uid != os.getuid()
            or opened_path.st_nlink != 1
            or stat.S_IMODE(opened_path.st_mode) != 0o755
        ):
            raise ValueError("V064_PUBLIC_CI_GH_INVALID")
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if not isinstance(nofollow, int) or not nofollow:
            raise ValueError("V064_PUBLIC_CI_GH_UNSUPPORTED")
        descriptor = os.open(_GH, os.O_RDONLY | nofollow)
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (opened_path.st_dev, opened_path.st_ino, opened_path.st_size):
            raise ValueError("V064_PUBLIC_CI_GH_INVALID")
        while True:
            body = os.read(descriptor, 1024 * 1024)
            if not body:
                break
            digest.update(body)
        attached = os.lstat(_GH)
        if (attached.st_dev, attached.st_ino, attached.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError("V064_PUBLIC_CI_GH_INVALID")
        return digest.hexdigest()
    except OSError as error:
        raise ValueError("V064_PUBLIC_CI_GH_INVALID") from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _verify_gh() -> Dict[str, Any]:
    file_sha256 = _gh_file_sha256()
    if file_sha256 != _GH_SHA256:
        raise ValueError("V064_PUBLIC_CI_GH_INVALID")
    completed = _run_bounded(
        (_GH, "--version"), timeout_seconds=5, max_bytes=4096,
    )
    if completed.returncode or completed.stderr or completed.stdout != _GH_VERSION:
        raise ValueError("V064_PUBLIC_CI_GH_INVALID")
    if _gh_file_sha256() != file_sha256:
        raise ValueError("V064_PUBLIC_CI_GH_INVALID")
    return {
        "path": _GH, "file_sha256": file_sha256,
        "version_size": len(completed.stdout),
        "version_sha256": hashlib.sha256(completed.stdout).hexdigest(),
    }


def _run_bounded(argv, *, timeout_seconds: int, max_bytes: int):
    process = None
    try:
        process = subprocess.Popen(
            argv,
            env=_GH_ENV,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if process.stdout is None or process.stderr is None:
            raise ValueError("V064_PUBLIC_CI_GH_COMMAND_FAILED")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        chunks = {"stdout": [], "stderr": []}
        sizes = {"stdout": 0, "stderr": 0}
        deadline = time.monotonic() + timeout_seconds
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("V064_PUBLIC_CI_GH_COMMAND_FAILED")
            events = selector.select(remaining)
            if not events:
                raise ValueError("V064_PUBLIC_CI_GH_COMMAND_FAILED")
            for key, _mask in events:
                body = os.read(key.fileobj.fileno(), 64 * 1024)
                if not body:
                    selector.unregister(key.fileobj)
                    continue
                name = key.data
                sizes[name] += len(body)
                if sizes[name] > max_bytes:
                    raise ValueError("V064_PUBLIC_CI_GH_OUTPUT_TOO_LARGE")
                chunks[name].append(body)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("V064_PUBLIC_CI_GH_COMMAND_FAILED")
        return_code = process.wait(timeout=remaining)
        return subprocess.CompletedProcess(
            argv, return_code, b"".join(chunks["stdout"]),
            b"".join(chunks["stderr"]),
        )
    except ValueError:
        raise
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("V064_PUBLIC_CI_GH_COMMAND_FAILED") from error
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()


def _capture(run_id: int) -> Dict[str, Any]:
    gh_identity = _verify_gh()
    raw = {}
    raw_stderr = {}
    records = []
    for name, argv in zip(("run_api", "jobs_api", "run_log"), _commands(run_id)):
        if _verify_gh() != gh_identity:
            raise ValueError("V064_PUBLIC_CI_GH_IDENTITY_CHANGED")
        completed = _run_bounded(
            argv, timeout_seconds=60, max_bytes=64 * 1024 * 1024,
        )
        if _verify_gh() != gh_identity:
            raise ValueError("V064_PUBLIC_CI_GH_IDENTITY_CHANGED")
        raw[name] = completed.stdout
        raw_stderr[name] = completed.stderr
        records.append({
            "name": name, "argv": list(argv), "exit_code": completed.returncode,
            "stdout_size": len(completed.stdout),
            "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
            "stderr_size": len(completed.stderr),
            "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        })
    return {
        "raw": raw, "raw_stderr": raw_stderr,
        "transcript": {
            "schema_version": "1.0.0", "gh_identity": gh_identity,
            "commands": records,
        },
    }


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(prog="crypto-quant-v064-public-ci-witness")
    parser.add_argument("--run-id", required=True, type=_run_id)
    arguments = parser.parse_args(tuple(argv))
    result = _capture(arguments.run_id)
    summary = {
        "schema_version": result["transcript"]["schema_version"],
        "commands": result["transcript"]["commands"],
    }
    sys.stdout.write(canonical_json(summary) + "\n")
    return 0 if all(item["exit_code"] == 0 for item in summary["commands"]) else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
