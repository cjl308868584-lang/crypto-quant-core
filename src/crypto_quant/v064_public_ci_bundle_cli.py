"""Fixed local ceremony CLI for the bounded v0.64 public CI candidate."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .canonical import canonical_json
from .v064_public_ci_bundle import (
    V064PublicCiBundleError,
    build_v064_public_root_commit,
    stage_v064_public_ci_bundle,
    verify_v064_public_ci_bundle,
)
from .challenger_replacement_plan_supersession_cli import (
    SupersessionCommandError,
    _validate_reviewed_repo_root,
)


_REPOSITORY = Path(__file__).absolute().parents[2]
_CANDIDATE = Path("/private/tmp/crypto-quant-v064-public-ci-r3-candidate")


def _head() -> str:
    raw_module = Path(__file__)
    if not raw_module.is_absolute() or raw_module.is_symlink():
        raise V064PublicCiBundleError("V064_PUBLIC_CI_REPOSITORY_INVALID")
    try:
        _validate_reviewed_repo_root(_REPOSITORY)
    except SupersessionCommandError as error:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_REPOSITORY_INVALID") from error
    completed = subprocess.run(
        ("/usr/bin/git", "-C", str(_REPOSITORY), "rev-parse", "HEAD^{commit}"),
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        value = completed.stdout.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_GIT_IDENTITY_INVALID") from error
    if (
        completed.returncode
        or completed.stderr
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise V064PublicCiBundleError("V064_PUBLIC_CI_GIT_IDENTITY_INVALID")
    return value


def _build() -> dict:
    source_commit = _head()
    manifest = stage_v064_public_ci_bundle(_REPOSITORY, source_commit, _CANDIDATE)
    candidate = build_v064_public_root_commit(
        _REPOSITORY, source_commit, _CANDIDATE
    )
    return {
        "status": "V064_PUBLIC_CI_CANDIDATE_BUILT",
        "source_commit": source_commit,
        "manifest": manifest,
        "candidate": candidate,
    }


def _verify() -> dict:
    return verify_v064_public_ci_bundle(_REPOSITORY, _head(), _CANDIDATE)


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(prog="crypto-quant-v064-public-ci-bundle")
    parser.add_argument("command", choices=("build-candidate", "verify-candidate"))
    arguments = parser.parse_args(tuple(argv))
    try:
        result = _build() if arguments.command == "build-candidate" else _verify()
    except V064PublicCiBundleError as error:
        sys.stderr.write(error.reason_code + "\n")
        return 2
    sys.stdout.write(canonical_json(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
