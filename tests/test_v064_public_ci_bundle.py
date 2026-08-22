import copy
import hashlib
import inspect
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, ValidationError

from crypto_quant.build import EvaluatorBuild
from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.v064_public_ci_bundle import (
    V064PublicCiBundleError,
    build_v064_public_root_commit,
    build_v064_public_ci_bundle_manifest,
    load_v064_public_ci_bundle_manifest,
    stage_v064_public_ci_bundle,
    verify_v064_public_ci_bundle,
)
from crypto_quant.v064_public_ci_r2_failure import (
    load_v064_public_ci_r2_failure_root,
)
from crypto_quant import v064_public_ci_bundle, v064_public_ci_bundle_cli


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "config" / "v064-public-ci-bundle-manifest-v1.schema.json"
PACKAGE_SCHEMA = (
    ROOT
    / "src"
    / "crypto_quant"
    / "schemas"
    / "v064-public-ci-bundle-manifest-v1.schema.json"
)
EXACT_FILES = (
    (".github/workflows/ci.yml", "PRIVATE_TEMPLATE_BLOB", "public_ci/v064/.github/workflows/ci.yml"),
    (".gitignore", "PRIVATE_TEMPLATE_BLOB", "public_ci/v064/.gitignore"),
    ("NOTICE.md", "PRIVATE_TEMPLATE_BLOB", "public_ci/v064/NOTICE.md"),
    ("README.md", "PRIVATE_TEMPLATE_BLOB", "public_ci/v064/README.md"),
    ("SECURITY.md", "PRIVATE_TEMPLATE_BLOB", "public_ci/v064/SECURITY.md"),
    (
        "src/crypto_quant/challenger_replacement_supersession_publish.py",
        "PRIVATE_GIT_BLOB",
        "src/crypto_quant/challenger_replacement_supersession_publish.py",
    ),
    (
        "tests/test_v064_linux_supersession_publish.py",
        "PRIVATE_GIT_BLOB",
        "tests/test_v064_linux_supersession_publish.py",
    ),
)
TEMPLATE_ROOT = ROOT / "public_ci" / "v064"
PRIVATE_F = "1967f79ff8d013bf149bf36e2cdcb6a81ed200ff"
PRIVATE_F2 = "5bc01c9b9b9d9a21846dd8c6ba1d81b0183dd219"
PRIVATE_F2_TREE = "53d3baf7d7c84e5bc8fcafa2561bbb959477ac4d"
PUBLIC_INVENTORY = tuple(
    sorted(
        [relative for relative, _kind, _source in EXACT_FILES]
        + ["bundle-manifest-v1.json"]
    )
)
CURRENT_PUBLIC_GIT_SOURCES = tuple(
    relative for relative, kind, _source in EXACT_FILES if kind == "PRIVATE_GIT_BLOB"
)
PREDECESSOR_FAILED_PUBLIC_WITNESS = {
    "repository": "cjl308868584-lang/crypto-quant-v064-public-ci",
    "private_candidate_f": "1967f79ff8d013bf149bf36e2cdcb6a81ed200ff",
    "private_tree_f": "5389cc01164ce6dd5955df1d014e974f4bf1a104",
    "public_commit": "0429837e5de8052e9e8216ed08ba9c7aa9c905b3",
    "public_tree": "4ebb723e73dc9eb43b7273febd96af3ef87ef951",
    "manifest_sha256": "c238c904495b167e436b2c32e822d8fa55285e42eaaad8e095805e73570e3fd7",
    "file_set_sha256": "2d7ed3d4b3380b43e50f16f04113eae46360397e46aeba2edd639ce46a7f76c7",
    "workflow_blob_oid": "d2c0104eafb8e1aa5ea68a60f716921f2668ce42",
    "run_id": 31850146784,
    "run_attempt": 1,
    "event": "push",
    "head_branch": "main",
    "status": "completed",
    "conclusion": "failure",
    "jobs": [
        {
            "python_version": "3.9",
            "job_id": 94924270273,
            "conclusion": "failure",
            "test_step_conclusion": "skipped",
        },
        {
            "python_version": "3.12",
            "job_id": 94924270340,
            "conclusion": "failure",
            "test_step_conclusion": "skipped",
        },
    ],
    "reason_code": "PUBLIC_SENSITIVE_BYTES_INVALID",
    "run_json_sha256": "f442ae366539fc4a244977fdafb2cd5de383b4248483381d8d79b751ea6a6099",
    "jobs_json_sha256": "9a69273c07548e97dbc2f43883eea4b5935f84256b7ad95b2874ca498bc67923",
    "run_log_sha256": "e47462120131eadb3161a40ffe679f4f74889103d7b3a13bb563df705f9ef32c",
    "transcript_summary_sha256": "cd2072e246698bec6d8767d37da4a3dca82d09fc38466a8009aea9690a0c9790",
}
R2_FAILURE_RECORD_PATH = (
    "artifacts/v064-public-ci-r2-failure/v064-public-ci-r2-failure-record-v1.json"
)
R2_FAILURE_RECORD_SHA256 = (
    "857150ae490e54d5b6bdaa816efb96cf3f24a9778220f61973312426644dd264"
)
PREDECESSOR_FAILED_PUBLIC_WITNESS_R2 = {
    "failure_record_path": R2_FAILURE_RECORD_PATH,
    "failure_record_sha256": R2_FAILURE_RECORD_SHA256,
    **json.loads((ROOT / R2_FAILURE_RECORD_PATH).read_text(encoding="utf-8")),
}


def _file(path, source_kind):
    return {
        "path": path,
        "size": 123,
        "sha256": "1" * 64,
        "source_kind": source_kind,
        "source_blob_oid": "2" * 40,
    }


def valid_bundle_manifest():
    return {
        "$schema": "./v064-public-ci-bundle-manifest-v1.schema.json",
        "schema_version": "1.2.0",
        "purpose": "V064_LINUX_PORTABILITY_WITNESS_ONLY",
        "source": {
            "private_repository": "cjl308868584-lang/crypto-quant-core",
            "candidate_commit": "3" * 40,
            "candidate_tree": "4" * 40,
            "private_release_baseline": "df91e19240df14839125608422489adf3b902e76",
            "object_format": "sha1",
            "historical_billing_blocked_private_pr": {
                "number": 32,
                "run_id": 31436609135,
                "status": "PRIVATE_PR_CI_NOT_EXECUTED_BILLING_BLOCKED",
            },
        },
        "public_repository": "cjl308868584-lang/crypto-quant-v064-public-ci-r3",
        "predecessor_failed_public_witnesses": [
            copy.deepcopy(PREDECESSOR_FAILED_PUBLIC_WITNESS),
            copy.deepcopy(PREDECESSOR_FAILED_PUBLIC_WITNESS_R2),
        ],
        "files": [
            _file(".github/workflows/ci.yml", "PRIVATE_TEMPLATE_BLOB"),
            _file(".gitignore", "PRIVATE_TEMPLATE_BLOB"),
            _file("NOTICE.md", "PRIVATE_TEMPLATE_BLOB"),
            _file("README.md", "PRIVATE_TEMPLATE_BLOB"),
            _file("SECURITY.md", "PRIVATE_TEMPLATE_BLOB"),
            _file(
                "src/crypto_quant/challenger_replacement_supersession_publish.py",
                "PRIVATE_GIT_BLOB",
            ),
            _file(
                "tests/test_v064_linux_supersession_publish.py",
                "PRIVATE_GIT_BLOB",
            ),
        ],
        "file_set_sha256": "5" * 64,
        "safety": {
            "production_activation": False,
            "credentials_present": False,
            "broker_allowed": False,
            "orders_allowed": False,
            "runtime_state_write_allowed": False,
        },
        "non_claims": [
            "NOT_FULL_PROJECT_CI",
            "NOT_PRIVATE_PR_CHECK",
            "NOT_STRATEGY_CORRECTNESS_EVIDENCE",
            "NOT_PROFITABILITY_OR_AI_ADVANTAGE_EVIDENCE",
            "NOT_PAPER_CANARY_OR_LIVE_TRADING_AUTHORIZATION",
        ],
    }


def _object_paths(value, path=()):
    if isinstance(value, dict):
        yield path
        for key, child in value.items():
            yield from _object_paths(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _object_paths(child, path + (index,))


def _at_path(value, path):
    for part in path:
        value = value[part]
    return value


def _canonical(value):
    return canonical_json(value).encode("utf-8") + b"\n"


def _git_bytes(repository, *arguments, input_bytes=None):
    return subprocess.run(
        ("/usr/bin/git", "-C", str(repository), *arguments),
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def _bare_git_bytes(git_directory, *arguments):
    return subprocess.run(
        ("/usr/bin/git", "--git-dir", str(git_directory), *arguments),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def _extract_exact_preflight(workflow_bytes):
    if b"\0" in workflow_bytes or b"\r" in workflow_bytes:
        raise AssertionError("workflow must be LF-only text")
    lines = workflow_bytes.splitlines(keepends=True)
    step = b"      - name: Verify closed bundle before repository imports\n"
    if lines.count(step) != 1:
        raise AssertionError("preflight step must be unique")
    index = lines.index(step)
    if lines[index + 1 : index + 3] != [
        b"        shell: bash\n",
        b"        run: |\n",
    ]:
        raise AssertionError("preflight header changed")
    script = []
    for line in lines[index + 3 :]:
        if line.startswith(b"          "):
            script.append(line[10:])
            continue
        break
    if not script or script[-1] != b"PY\n":
        raise AssertionError("preflight body is incomplete")
    return b"".join(script)


def _extract_workflow_step(workflow_bytes, name):
    if b"\0" in workflow_bytes or b"\r" in workflow_bytes:
        raise AssertionError("workflow must be LF-only text")
    lines = workflow_bytes.splitlines(keepends=True)
    step = ("      - name: %s\n" % name).encode("utf-8")
    if lines.count(step) != 1:
        raise AssertionError("workflow step must be unique")
    index = lines.index(step)
    if lines[index + 1 : index + 3] != [
        b"        shell: bash\n",
        b"        run: |\n",
    ]:
        raise AssertionError("workflow step header changed")
    script = []
    for line in lines[index + 3 :]:
        if line.startswith(b"          "):
            script.append(line[10:])
            continue
        break
    if not script:
        raise AssertionError("workflow step body is empty")
    return b"".join(script)


def _assert_setup_python_precedes_interpreter_capture(workflow_bytes):
    expected_step_headers = (
        b"      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09\n",
        b"      - name: Verify closed bundle before repository imports\n",
        b"      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1\n",
        b"      - name: Run fixed-owner public boundary\n",
    )
    step_headers = tuple(
        line
        for line in workflow_bytes.splitlines(keepends=True)
        if line.startswith(b"      - ")
    )
    if step_headers != expected_step_headers:
        raise AssertionError("workflow step order changed")
    ordered_markers = (
        expected_step_headers[0],
        expected_step_headers[1],
        b"      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1\n"
        b"        with:\n"
        b"          python-version: ${{ matrix.python-version }}\n",
        expected_step_headers[3],
    )
    for marker in ordered_markers:
        if workflow_bytes.count(marker) != 1:
            raise AssertionError("ordered workflow marker must be unique")
    offsets = [workflow_bytes.index(marker) for marker in ordered_markers]
    if offsets != sorted(offsets):
        raise AssertionError("workflow step order changed")
    capture = b'python_bin="$(command -v python)"\n'
    if workflow_bytes.count(capture) != 1:
        raise AssertionError("interpreter capture must be unique")
    fixed_owner = _extract_workflow_step(
        workflow_bytes, "Run fixed-owner public boundary"
    )
    if fixed_owner.count(capture) != 1:
        raise AssertionError("interpreter capture must follow setup-python")


def _write_executable(path, body):
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _write_fake_python(path, version, identity, log):
    _write_executable(
        path,
        """#!/bin/bash
set -euo pipefail
case "${1-}" in
  -c) printf '%%s\\n' '%s'; phase=precheck ;;
  --version) printf 'Python %s.0\\n'; phase=version ;;
  -m) phase=test ;;
  *) phase=other ;;
esac
printf '%%s|%%s|%%s\\n' '%s' "$phase" "$*" >> '%s'
"""
        % (version, version, identity, log),
    )


def _fixed_owner_fixture(temporary, setup_version, child_path_mode):
    root = Path(temporary)
    runner_bin = root / "runner-bin"
    harness_bin = root / "harness-bin"
    system_bin = root / "system-bin"
    poison_bin = root / "poison-bin"
    workspace = root / "workspace"
    for directory in (runner_bin, harness_bin, system_bin, poison_bin, workspace):
        directory.mkdir()
    invocation_log = root / "interpreter.log"
    sudo_log = root / "sudo.log"
    bash_env = root / "bash-env"
    bash_env.write_text(
        'cd() { builtin cd "$FIXTURE_WORKSPACE"; }\n', encoding="utf-8"
    )
    _write_fake_python(
        runner_bin / "python", setup_version, "setup-%s" % setup_version, invocation_log
    )
    _write_fake_python(system_bin / "python", "3.12", "system", invocation_log)
    _write_fake_python(poison_bin / "python", "9.9", "poison", invocation_log)
    for name in ("uname", "ldd", "head"):
        _write_executable(
            system_bin / name,
            "#!/bin/bash\nprintf '%s fixture\\n'\n" % name,
        )
    _write_executable(
        harness_bin / "sudo",
        """#!/usr/bin/python3
import json
import os
import subprocess
import sys

arguments = sys.argv[1:]
with open(os.environ["FIXTURE_SUDO_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(arguments, separators=(",", ":")) + "\\n")
if arguments[:3] != ["-u", "#501", "env"]:
    raise SystemExit(90)
arguments = arguments[3:]
assignments = {}
while arguments and arguments[0] != "/bin/bash":
    key, separator, value = arguments.pop(0).partition("=")
    if not separator or key == "PATH":
        raise SystemExit(91)
    assignments[key] = value
if arguments[:2] != ["/bin/bash", "-c"]:
    raise SystemExit(92)
mode = os.environ["FIXTURE_MODE"]
if mode == "current":
    if len(arguments) != 5:
        raise SystemExit(92)
    _, _, child_script, child_argv0, child_python = arguments
    marker = '\"$1\" --version;'
    if child_script.count(marker) != 1:
        raise SystemExit(93)
    child_script = "set -euo pipefail; " + marker + child_script.split(marker, 1)[1]
elif mode == "historical":
    if len(arguments) != 3:
        raise SystemExit(92)
    _, _, child_script = arguments
    child_argv0 = "v064-r2-fixed-owner"
    child_python = ""
else:
    raise SystemExit(94)
child_environment = dict(assignments)
child_environment.update({
    "BASH_ENV": os.environ["FIXTURE_BASH_ENV"],
    "FIXTURE_WORKSPACE": os.environ["FIXTURE_WORKSPACE"],
})
child_path = os.environ["FIXTURE_CHILD_PATH"]
if child_path:
    child_environment["PATH"] = child_path
result = subprocess.run(
    ["/bin/bash", "-c", child_script, child_argv0, child_python],
    env=child_environment,
)
raise SystemExit(result.returncode)
""",
    )
    child_path = {
        "missing": "",
        "poisoned": str(poison_bin),
        "system": str(system_bin),
    }[child_path_mode]
    environment = {
        "PATH": "%s:%s:%s" % (runner_bin, harness_bin, system_bin),
        "LC_ALL": "C",
        "LANG": "C",
        "FIXTURE_BASH_ENV": str(bash_env),
        "FIXTURE_CHILD_PATH": child_path,
        "FIXTURE_SUDO_LOG": str(sudo_log),
        "FIXTURE_WORKSPACE": str(workspace),
    }
    return environment, invocation_log, sudo_log


def _run_current_interpreter_handoff(workflow_bytes, matrix_version, environment, cwd):
    fixed_owner = _extract_workflow_step(
        workflow_bytes, "Run fixed-owner public boundary"
    )
    marker = b'python_bin="$(command -v python)"\n'
    if fixed_owner.count(marker) != 1:
        raise AssertionError("interpreter capture must be unique")
    handoff = fixed_owner[fixed_owner.index(marker) :]
    expression = b"${{ matrix.python-version }}"
    if handoff.count(expression) != 1:
        raise AssertionError("matrix version expression must be unique")
    rendered = b"set -euo pipefail\n" + handoff.replace(
        expression, matrix_version.encode("ascii")
    )
    current_environment = dict(environment, FIXTURE_MODE="current")
    return subprocess.run(
        ("/bin/bash", "-c", rendered),
        cwd=cwd,
        env=current_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _write_closed_checkout(destination, source_commit, use_worktree):
    destination.mkdir(mode=0o700)
    files = []
    for relative, source_kind, source_relative in EXACT_FILES:
        body = (
            (ROOT / source_relative).read_bytes()
            if use_worktree
            else _git_bytes(ROOT, "show", "%s:%s" % (source_commit, source_relative))
        )
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        oid = _git_bytes(ROOT, "hash-object", "--stdin", input_bytes=body).decode("ascii").strip()
        files.append(
            {
                "path": relative,
                "size": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "source_kind": source_kind,
                "source_blob_oid": oid,
            }
        )
    source_tree = _git_bytes(ROOT, "rev-parse", "%s^{tree}" % source_commit).decode("ascii").strip()
    if use_worktree:
        manifest = valid_bundle_manifest()
        manifest["source"]["candidate_commit"] = source_commit
        manifest["source"]["candidate_tree"] = source_tree
    else:
        manifest = valid_bundle_manifest()
        manifest["schema_version"] = "1.0.0"
        manifest["public_repository"] = "cjl308868584-lang/crypto-quant-v064-public-ci"
        del manifest["predecessor_failed_public_witnesses"]
        manifest["source"]["candidate_commit"] = source_commit
        manifest["source"]["candidate_tree"] = source_tree
    manifest["files"] = files
    manifest["file_set_sha256"] = business_hash(files)
    (destination / "bundle-manifest-v1.json").write_bytes(_canonical(manifest))
    _git_bytes(destination, "init", "-q")
    _git_bytes(destination, "config", "user.name", "V064 Preflight Fixture")
    _git_bytes(destination, "config", "user.email", "fixture@example.invalid")
    _git_bytes(destination, "add", "--all")
    _git_bytes(destination, "commit", "-q", "-m", "fixture: closed checkout")
    return manifest


def _run_exact_preflight(checkout, repository_name):
    workflow = (checkout / ".github/workflows/ci.yml").read_bytes()
    head = _git_bytes(checkout, "rev-parse", "HEAD").decode("ascii").strip()
    return subprocess.run(
        ("/bin/bash", "-c", _extract_exact_preflight(workflow)),
        cwd=checkout,
        env={
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "LANG": "C",
            "GITHUB_REPOSITORY": repository_name,
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": head,
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _replace_file_and_reseal(checkout, relative, body):
    path = checkout / relative
    path.write_bytes(body)
    manifest_path = checkout / "bundle-manifest-v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next(item for item in manifest["files"] if item["path"] == relative)
    entry["size"] = len(body)
    entry["sha256"] = hashlib.sha256(body).hexdigest()
    entry["source_blob_oid"] = _git_bytes(
        checkout, "hash-object", "--stdin", input_bytes=body
    ).decode("ascii").strip()
    manifest["file_set_sha256"] = business_hash(manifest["files"])
    manifest_path.write_bytes(_canonical(manifest))
    _git_bytes(checkout, "add", "--all")
    _git_bytes(checkout, "commit", "-q", "-m", "fixture: reseal mutation")


def _replace_readme_and_reseal(checkout, body):
    _replace_file_and_reseal(checkout, "README.md", body)


class V064PublicCiSchemaTests(unittest.TestCase):
    def schema(self):
        return json.loads(CONFIG_SCHEMA.read_text(encoding="utf-8"))

    def test_config_and_package_schemas_are_exact_valid_mirrors(self):
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        schema = self.schema()
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(valid_bundle_manifest())

    def test_manifest_requires_exact_ordered_r1_r2_failed_predecessors(self):
        schema = self.schema()
        validator = Draft202012Validator(schema)

        missing = copy.deepcopy(valid_bundle_manifest())
        del missing["predecessor_failed_public_witnesses"]
        with self.assertRaises(ValidationError):
            validator.validate(missing)

        predecessor = PREDECESSOR_FAILED_PUBLIC_WITNESS
        scalar_replacements = {
            "repository": "cjl308868584-lang/wrong",
            "private_candidate_f": "0" * 40,
            "private_tree_f": "0" * 40,
            "public_commit": "0" * 40,
            "public_tree": "0" * 40,
            "manifest_sha256": "0" * 64,
            "file_set_sha256": "0" * 64,
            "workflow_blob_oid": "0" * 40,
            "run_id": predecessor["run_id"] + 1,
            "run_attempt": 2,
            "event": "workflow_dispatch",
            "head_branch": "wrong",
            "status": "queued",
            "conclusion": "success",
            "reason_code": "WRONG",
            "run_json_sha256": "0" * 64,
            "jobs_json_sha256": "0" * 64,
            "run_log_sha256": "0" * 64,
            "transcript_summary_sha256": "0" * 64,
        }
        for key, replacement in scalar_replacements.items():
            changed = copy.deepcopy(valid_bundle_manifest())
            changed["predecessor_failed_public_witnesses"][0][key] = replacement
            with self.subTest(field=key), self.assertRaises(ValidationError):
                validator.validate(changed)

        for index, job in enumerate(predecessor["jobs"]):
            for key, original in job.items():
                changed = copy.deepcopy(valid_bundle_manifest())
                replacement = original + 1 if isinstance(original, int) else "wrong"
                changed["predecessor_failed_public_witnesses"][0]["jobs"][index][key] = replacement
                with self.subTest(job=index, field=key), self.assertRaises(ValidationError):
                    validator.validate(changed)

        structural_mutations = []
        wrong_version = copy.deepcopy(valid_bundle_manifest())
        wrong_version["schema_version"] = "1.1.0"
        structural_mutations.append(wrong_version)
        old_repository = copy.deepcopy(valid_bundle_manifest())
        old_repository["public_repository"] = (
            "cjl308868584-lang/crypto-quant-v064-public-ci-r2"
        )
        structural_mutations.append(old_repository)
        extra = copy.deepcopy(valid_bundle_manifest())
        extra["predecessor_failed_public_witnesses"][0]["unexpected"] = True
        structural_mutations.append(extra)
        extra_predecessor = copy.deepcopy(valid_bundle_manifest())
        extra_predecessor["predecessor_failed_public_witnesses"].append(
            copy.deepcopy(PREDECESSOR_FAILED_PUBLIC_WITNESS_R2)
        )
        structural_mutations.append(extra_predecessor)
        reordered = copy.deepcopy(valid_bundle_manifest())
        reordered["predecessor_failed_public_witnesses"].reverse()
        structural_mutations.append(reordered)
        duplicate = copy.deepcopy(valid_bundle_manifest())
        duplicate["predecessor_failed_public_witnesses"][1] = copy.deepcopy(
            duplicate["predecessor_failed_public_witnesses"][0]
        )
        structural_mutations.append(duplicate)
        unsafe = copy.deepcopy(valid_bundle_manifest())
        unsafe["predecessor_failed_public_witnesses"][1]["run"]["run_id"] = 2**53
        structural_mutations.append(unsafe)
        long_oid = copy.deepcopy(valid_bundle_manifest())
        long_oid["predecessor_failed_public_witnesses"][1]["public_source"]["root_commit"] = "f" * 64
        structural_mutations.append(long_oid)
        uppercase_hash = copy.deepcopy(valid_bundle_manifest())
        uppercase_hash["predecessor_failed_public_witnesses"][1]["raw_evidence"]["run_log"]["sha256"] = "A" * 64
        structural_mutations.append(uppercase_hash)
        for changed in structural_mutations:
            with self.assertRaises(ValidationError):
                validator.validate(changed)

    def test_manifest_rejects_wrong_purpose_permissions_and_source_identity(self):
        schema = self.schema()
        mutations = []

        wrong_purpose = copy.deepcopy(valid_bundle_manifest())
        wrong_purpose["purpose"] = "FULL_PROJECT_CI"
        mutations.append(wrong_purpose)

        order_permission = copy.deepcopy(valid_bundle_manifest())
        order_permission["safety"]["orders_allowed"] = True
        mutations.append(order_permission)

        invalid_commit = copy.deepcopy(valid_bundle_manifest())
        invalid_commit["source"]["candidate_commit"] = "not-a-sha"
        mutations.append(invalid_commit)

        mismatched_object_format = copy.deepcopy(valid_bundle_manifest())
        mismatched_object_format["source"]["candidate_commit"] = "3" * 64
        mutations.append(mismatched_object_format)

        wrong_historical_status = copy.deepcopy(valid_bundle_manifest())
        wrong_historical_status["source"]["historical_billing_blocked_private_pr"][
            "status"
        ] = "SUCCESS"
        mutations.append(wrong_historical_status)

        old_pr_claim = copy.deepcopy(valid_bundle_manifest())
        old_pr_claim["source"]["private_pr"] = 32
        mutations.append(old_pr_claim)

        for value in mutations:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    Draft202012Validator(schema).validate(value)

    def test_manifest_rejects_mixed_git_object_formats(self):
        schema = self.schema()
        for path in (
            ("source", "candidate_commit"),
            ("source", "candidate_tree"),
            ("files", 0, "source_blob_oid"),
            ("files", 5, "source_blob_oid"),
        ):
            changed = copy.deepcopy(valid_bundle_manifest())
            container = _at_path(changed, path[:-1])
            container[path[-1]] = "f" * 64
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    Draft202012Validator(schema).validate(changed)

    def test_manifest_requires_the_exact_sorted_non_manifest_file_set(self):
        schema = self.schema()

        duplicate = copy.deepcopy(valid_bundle_manifest())
        duplicate["files"].append(copy.deepcopy(duplicate["files"][0]))
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(duplicate)

        reordered = copy.deepcopy(valid_bundle_manifest())
        reordered["files"][0], reordered["files"][1] = (
            reordered["files"][1],
            reordered["files"][0],
        )
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(reordered)

        unknown = copy.deepcopy(valid_bundle_manifest())
        unknown["files"][0]["unexpected"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(unknown)

    def test_manifest_rejects_unknown_fields_at_every_object_boundary(self):
        schema = self.schema()
        validator = Draft202012Validator(schema)
        original = valid_bundle_manifest()
        for path in _object_paths(original):
            changed = copy.deepcopy(original)
            _at_path(changed, path)["unexpected"] = True
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    validator.validate(changed)


class V064PublicCiBundleManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name) / "repository"
        self.repository.mkdir(mode=0o700)
        self._git("init", "-q")
        self._git("config", "user.name", "V064 Fixture")
        self._git("config", "user.email", "fixture@example.invalid")
        for index, (relative, _kind, source_relative) in enumerate(EXACT_FILES):
            path = self.repository / source_relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("fixture-%d-%s\n" % (index, relative)).encode("utf-8"))
        self._git("add", "--", *(source for _relative, _kind, source in EXACT_FILES))
        self._git("commit", "-q", "-m", "fixture: freeze public inputs")
        self.commit = self._git("rev-parse", "HEAD").stdout.decode("ascii").strip()

    def tearDown(self):
        self.temporary.cleanup()

    def _git(self, *arguments, input_bytes=None):
        return subprocess.run(
            ("/usr/bin/git", "-C", str(self.repository), *arguments),
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def _blob(self, relative):
        source = next(item[2] for item in EXACT_FILES if item[0] == relative)
        oid = self._git("rev-parse", "%s:%s" % (self.commit, source)).stdout.strip()
        body = self._git("cat-file", "blob", oid).stdout
        return oid.decode("ascii"), body

    def test_builder_uses_exact_commit_blobs_and_builds_closed_manifest(self):
        mutated = self.repository / EXACT_FILES[-1][0]
        mutated.write_bytes(b"mutable-worktree-bytes-must-not-be-used\n")

        manifest = build_v064_public_ci_bundle_manifest(
            self.repository, self.commit
        )

        expected_entries = []
        for relative, source_kind, _source_relative in EXACT_FILES:
            oid, body = self._blob(relative)
            expected_entries.append(
                {
                    "path": relative,
                    "size": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "source_kind": source_kind,
                    "source_blob_oid": oid,
                }
            )
        self.assertEqual(manifest["files"], expected_entries)
        self.assertEqual(manifest["file_set_sha256"], business_hash(expected_entries))
        self.assertEqual(
            manifest["source"]["candidate_tree"],
            self._git("rev-parse", "%s^{tree}" % self.commit)
            .stdout.decode("ascii")
            .strip(),
        )
        self.assertEqual(manifest["source"]["candidate_commit"], self.commit)
        self.assertEqual(manifest["schema_version"], "1.2.0")
        self.assertEqual(
            manifest["public_repository"],
            "cjl308868584-lang/crypto-quant-v064-public-ci-r3",
        )
        self.assertEqual(
            manifest["predecessor_failed_public_witnesses"],
            [
                PREDECESSOR_FAILED_PUBLIC_WITNESS,
                PREDECESSOR_FAILED_PUBLIC_WITNESS_R2,
            ],
        )
        self.assertEqual(manifest["safety"], valid_bundle_manifest()["safety"])
        self.assertEqual(manifest["non_claims"], valid_bundle_manifest()["non_claims"])
        Draft202012Validator(self.schema()).validate(manifest)

    def schema(self):
        return json.loads(CONFIG_SCHEMA.read_text(encoding="utf-8"))

    def test_loader_requires_one_canonical_lf_and_recomputes_file_set_hash(self):
        manifest = build_v064_public_ci_bundle_manifest(
            self.repository, self.commit
        )
        path = Path(self.temporary.name) / "bundle-manifest-v1.json"
        path.write_bytes(canonical_json(manifest).encode("utf-8") + b"\n")
        os.chmod(path, 0o600)
        self.assertEqual(load_v064_public_ci_bundle_manifest(path), manifest)

        malformed = copy.deepcopy(manifest)
        malformed["files"][0]["sha256"] = "f" * 64
        path.write_bytes(canonical_json(malformed).encode("utf-8") + b"\n")
        with self.assertRaisesRegex(
            V064PublicCiBundleError, "V064_PUBLIC_CI_FILE_SET_HASH_MISMATCH"
        ):
            load_v064_public_ci_bundle_manifest(path)

        path.write_bytes(canonical_json(manifest).encode("utf-8"))
        with self.assertRaisesRegex(
            V064PublicCiBundleError, "V064_PUBLIC_CI_MANIFEST_CANONICAL_BYTES_REQUIRED"
        ):
            load_v064_public_ci_bundle_manifest(path)

    def test_builder_rejects_a_valid_commit_that_is_not_current_head(self):
        old_commit = self.commit
        readme = self.repository / "README.md"
        readme.write_bytes(b"new-reviewed-head\n")
        self._git("add", "--", "README.md")
        self._git("commit", "-q", "-m", "fixture: advance head")

        with self.assertRaisesRegex(
            V064PublicCiBundleError, "V064_PUBLIC_CI_SOURCE_NOT_REVIEWED_HEAD"
        ):
            build_v064_public_ci_bundle_manifest(self.repository, old_commit)

    def test_historical_r3_publisher_and_linux_test_blobs_match_f(self):
        original_source = "1967f79ff8d013bf149bf36e2cdcb6a81ed200ff"
        r3_source = "f9705fa2151ab98a5b9efe63be05979e4bc5bfa6"
        for relative in (
            "src/crypto_quant/challenger_replacement_supersession_publish.py",
            "tests/test_v064_linux_supersession_publish.py",
        ):
            original_oid = subprocess.run(
                (
                    "/usr/bin/git",
                    "-C",
                    str(ROOT),
                    "rev-parse",
                    original_source + ":" + relative,
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout.decode("ascii").strip()
            r3_oid = subprocess.run(
                (
                    "/usr/bin/git",
                    "-C",
                    str(ROOT),
                    "rev-parse",
                    r3_source + ":" + relative,
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout.decode("ascii").strip()
            self.assertEqual(r3_oid, original_oid)
            self.assertEqual(
                subprocess.run(
                    (
                        "/usr/bin/git",
                        "-C",
                        str(ROOT),
                        "cat-file",
                        "blob",
                        r3_oid,
                    ),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                ).stdout,
                subprocess.run(
                    (
                        "/usr/bin/git",
                        "-C",
                        str(ROOT),
                        "cat-file",
                        "blob",
                        original_oid,
                    ),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                ).stdout,
            )

    def test_builder_rejects_executable_or_symlink_source_entries(self):
        for case_name in ("executable", "symlink"):
            with self.subTest(case_name=case_name):
                path = self.repository / "public_ci/v064/README.md"
                if case_name == "executable":
                    path.chmod(0o755)
                else:
                    path.unlink()
                    path.symlink_to("NOTICE.md")
                self._git("add", "--", "public_ci/v064/README.md")
                self._git("commit", "-q", "-m", "fixture: untrusted git mode")
                current = self._git("rev-parse", "HEAD").stdout.decode("ascii").strip()
                with self.assertRaisesRegex(
                    V064PublicCiBundleError, "V064_PUBLIC_CI_SOURCE_ENTRY_INVALID"
                ):
                    build_v064_public_ci_bundle_manifest(self.repository, current)
                self.tearDown()
                self.setUp()

    def test_stage_creates_only_the_closed_public_tree_from_commit_blobs(self):
        destination = Path(self.temporary.name) / "public-candidate"
        manifest = stage_v064_public_ci_bundle(
            self.repository, self.commit, destination
        )

        actual = sorted(
            str(path.relative_to(destination))
            for path in destination.rglob("*")
            if path.is_file()
        )
        self.assertEqual(
            actual,
            sorted([relative for relative, _kind, _source in EXACT_FILES] + ["bundle-manifest-v1.json"]),
        )
        self.assertEqual(
            (destination / "bundle-manifest-v1.json").read_bytes(),
            canonical_json(manifest).encode("utf-8") + b"\n",
        )
        for entry in manifest["files"]:
            _oid, exact = self._blob(entry["path"])
            self.assertEqual((destination / entry["path"]).read_bytes(), exact)
        self.assertEqual(os.stat(destination).st_mode & 0o777, 0o700)

    def test_stage_rejects_forbidden_source_bytes_before_destination_creation(self):
        readme = self.repository / "public_ci/v064/README.md"
        readme.write_bytes(b"contact owner" + b"@" + b"example.com\n")
        self._git("add", "--", "public_ci/v064/README.md")
        self._git("commit", "-q", "-m", "fixture: forbidden public byte")
        current = self._git("rev-parse", "HEAD").stdout.decode("ascii").strip()
        destination = Path(self.temporary.name) / "must-not-exist"

        with self.assertRaisesRegex(
            V064PublicCiBundleError, "V064_PUBLIC_CI_SENSITIVE_BYTES_FORBIDDEN"
        ):
            stage_v064_public_ci_bundle(self.repository, current, destination)
        self.assertFalse(destination.exists())

    def test_stage_rejects_plain_business_and_authority_terms(self):
        readme = self.repository / "public_ci/v064/README.md"
        for index, forbidden in enumerate(
            (b"strategy\n", b"economic\n", b"broker\n", b"order\n", b"credential\n")
        ):
            with self.subTest(forbidden=forbidden):
                readme.write_bytes(forbidden)
                self._git("add", "--", "public_ci/v064/README.md")
                self._git("commit", "-q", "-m", "fixture: forbidden term")
                current = self._git("rev-parse", "HEAD").stdout.decode("ascii").strip()
                destination = Path(self.temporary.name) / ("term-%d" % index)
                with self.assertRaisesRegex(
                    V064PublicCiBundleError, "V064_PUBLIC_CI_SENSITIVE_BYTES_FORBIDDEN"
                ):
                    stage_v064_public_ci_bundle(self.repository, current, destination)
                self.assertFalse(destination.exists())

    def test_stage_rejects_token_and_non_allowlisted_url_patterns(self):
        readme = self.repository / "public_ci/v064/README.md"
        fixtures = (
            b"gh" + b"p_" + b"A" * 40 + b"\n",
            b"github_" + b"pat_" + b"A" * 30 + b"\n",
            b"https" + b"://example.invalid/path\n",
        )
        for index, forbidden in enumerate(fixtures):
            with self.subTest(index=index):
                readme.write_bytes(forbidden)
                self._git("add", "--", "public_ci/v064/README.md")
                self._git("commit", "-q", "-m", "fixture: forbidden token")
                current = self._git("rev-parse", "HEAD").stdout.decode("ascii").strip()
                destination = Path(self.temporary.name) / ("token-%d" % index)
                with self.assertRaisesRegex(
                    V064PublicCiBundleError, "V064_PUBLIC_CI_SENSITIVE_BYTES_FORBIDDEN"
                ):
                    stage_v064_public_ci_bundle(self.repository, current, destination)
                self.assertFalse(destination.exists())

    def test_all_real_public_inputs_pass_the_sensitive_scanner(self):
        import crypto_quant.v064_public_ci_bundle as module

        for _relative, _kind, source_relative in EXACT_FILES:
            with self.subTest(source_relative=source_relative):
                self.assertFalse(
                    module._forbidden_public_bytes(
                        (ROOT / source_relative).read_bytes(),
                        ".github/workflows/ci.yml"
                        if source_relative.endswith("/.github/workflows/ci.yml")
                        else source_relative,
                    )
                )

    def test_workflow_strategy_syntax_exception_is_path_scoped(self):
        import crypto_quant.v064_public_ci_bundle as module

        syntax = b"jobs:\n  test:\n    strategy:\n      matrix: {}\n"
        self.assertFalse(
            module._forbidden_public_bytes(syntax, ".github/workflows/ci.yml")
        )
        self.assertTrue(module._forbidden_public_bytes(syntax, "README.md"))

    def test_failed_partial_write_never_leaves_a_canonical_public_file(self):
        import crypto_quant.v064_public_ci_bundle as module

        destination = Path(self.temporary.name) / "partial"
        original = module._write_all
        calls = 0

        def fail_first(descriptor, body):
            nonlocal calls
            calls += 1
            if calls == 1:
                os.write(descriptor, body[:2])
                raise V064PublicCiBundleError("V064_PUBLIC_CI_WRITE_FAILED")
            return original(descriptor, body)

        with mock.patch.object(module, "_write_all", side_effect=fail_first):
            with self.assertRaisesRegex(
                V064PublicCiBundleError, "V064_PUBLIC_CI_WRITE_FAILED"
            ):
                stage_v064_public_ci_bundle(
                    self.repository, self.commit, destination
                )
        canonical = destination / EXACT_FILES[0][0]
        self.assertFalse(canonical.exists())

    def test_primary_write_failure_is_not_replaced_by_close_failure(self):
        import crypto_quant.v064_public_ci_bundle as module

        destination = Path(self.temporary.name) / "close"
        destination.mkdir()
        real_close = os.close

        def close_then_fail(descriptor):
            real_close(descriptor)
            raise OSError("injected close failure")

        with mock.patch.object(
            module, "_write_all", side_effect=V064PublicCiBundleError("PRIMARY_WRITE_FAILURE")
        ), mock.patch.object(module.os, "close", side_effect=close_then_fail):
            with self.assertRaisesRegex(V064PublicCiBundleError, "PRIMARY_WRITE_FAILURE"):
                module._write_new_file(destination / "final", b"body\n")

    def test_destination_replacement_after_creation_never_writes_displaced_tree(self):
        import crypto_quant.v064_public_ci_bundle as module

        destination = Path(self.temporary.name) / "candidate"
        displaced = Path(self.temporary.name) / "displaced"
        replacement = Path(self.temporary.name) / "replacement"
        replacement.mkdir()
        original_write = module._write_new_at
        calls = 0

        def replace_before_first_write(parent_descriptor, name, body):
            nonlocal calls
            calls += 1
            if calls == 1:
                destination.rename(displaced)
                replacement.rename(destination)
            return original_write(parent_descriptor, name, body)

        with mock.patch.object(
            module, "_write_new_at", side_effect=replace_before_first_write
        ):
            with self.assertRaises(V064PublicCiBundleError):
                stage_v064_public_ci_bundle(
                    self.repository, self.commit, destination
                )
        self.assertTrue(displaced.is_dir())
        self.assertEqual(list(destination.rglob("*")), [])

    def test_root_commit_is_parentless_deterministic_and_replays_exact_tree(self):
        candidates = []
        for name in ("first", "second"):
            public_root = Path(self.temporary.name) / name
            stage_v064_public_ci_bundle(self.repository, self.commit, public_root)
            candidates.append(
                build_v064_public_root_commit(
                    self.repository, self.commit, public_root
                )
            )

        self.assertEqual(candidates[0]["commit"], candidates[1]["commit"])
        self.assertEqual(candidates[0]["tree"], candidates[1]["tree"])
        self.assertEqual(candidates[0]["parent_count"], 0)
        self.assertEqual(
            candidates[0]["author_email"],
            "cjl308868584-lang@users.noreply.github.com",
        )
        self.assertEqual(
            candidates[0]["paths"],
            sorted([relative for relative, _kind, _source in EXACT_FILES] + ["bundle-manifest-v1.json"]),
        )
        for candidate in candidates:
            git_directory = Path(candidate["git_directory"])
            self.assertTrue(git_directory.is_dir())
            self.assertEqual(git_directory.stat().st_mode & 0o777, 0o700)
            replay = subprocess.run(
                ("/usr/bin/git", "--git-dir", str(git_directory), "rev-parse", "refs/heads/main"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            ).stdout.decode("ascii").strip()
            self.assertEqual(replay, candidate["commit"])

    def test_root_commit_rejects_symlink_hardlink_and_extra_special_objects(self):
        for case_name in ("symlink", "hardlink", "fifo", "empty-directory"):
            with self.subTest(case_name=case_name):
                public_root = Path(self.temporary.name) / ("root-" + case_name)
                stage_v064_public_ci_bundle(self.repository, self.commit, public_root)
                target = public_root / "README.md"
                sentinel = Path(self.temporary.name) / ("sentinel-" + case_name)
                sentinel.write_bytes(b"sentinel\n")
                sentinel.chmod(0o644)
                if case_name == "symlink":
                    target.unlink()
                    target.symlink_to(sentinel)
                elif case_name == "hardlink":
                    target.unlink()
                    os.link(sentinel, target)
                elif case_name == "fifo":
                    target.unlink()
                    os.mkfifo(target, 0o644)
                else:
                    (public_root / "unexpected-empty").mkdir()
                with self.assertRaisesRegex(
                    V064PublicCiBundleError, "V064_PUBLIC_CI_PUBLIC_ROOT_INVALID"
                ):
                    build_v064_public_root_commit(
                        self.repository, self.commit, public_root
                    )

    def test_builder_and_verifier_reject_untrusted_candidate_root_before_git_write(self):
        for operation in (build_v064_public_root_commit, verify_v064_public_ci_bundle):
            with self.subTest(operation=operation.__name__):
                public_root = Path(self.temporary.name) / ("mode-" + operation.__name__)
                stage_v064_public_ci_bundle(self.repository, self.commit, public_root)
                public_root.chmod(0o755)
                with self.assertRaisesRegex(
                    V064PublicCiBundleError, "V064_PUBLIC_CI_PUBLIC_ROOT_INVALID"
                ):
                    operation(self.repository, self.commit, public_root)
                self.assertFalse(
                    (public_root.parent / (public_root.name + ".git")).exists()
                )

    def test_builder_rejects_wrong_owner_root_identity_before_git_write(self):
        public_root = Path(self.temporary.name) / "wrong-owner-root"
        stage_v064_public_ci_bundle(self.repository, self.commit, public_root)
        real_fstat = os.fstat
        replaced = False

        def wrong_owner(descriptor):
            nonlocal replaced
            value = real_fstat(descriptor)
            if not replaced and stat.S_ISDIR(value.st_mode):
                replaced = True
                fields = list(value)
                fields[4] = value.st_uid + 1
                return os.stat_result(fields)
            return value

        with mock.patch.object(
            v064_public_ci_bundle.os, "fstat", side_effect=wrong_owner
        ):
            with self.assertRaisesRegex(
                V064PublicCiBundleError, "V064_PUBLIC_CI_PUBLIC_ROOT_INVALID"
            ):
                build_v064_public_root_commit(
                    self.repository, self.commit, public_root
                )
        self.assertFalse(
            (public_root.parent / (public_root.name + ".git")).exists()
        )

    def test_root_replacement_after_inventory_fails_before_git_write(self):
        public_root = Path(self.temporary.name) / "replace-after-inventory"
        displaced = Path(self.temporary.name) / "displaced-candidate"
        stage_v064_public_ci_bundle(self.repository, self.commit, public_root)
        real_inventory = v064_public_ci_bundle._inventory_public_root

        def replace_after_inventory(descriptor):
            result = real_inventory(descriptor)
            public_root.rename(displaced)
            public_root.mkdir(mode=0o700)
            return result

        with mock.patch.object(
            v064_public_ci_bundle,
            "_inventory_public_root",
            side_effect=replace_after_inventory,
        ):
            with self.assertRaisesRegex(
                V064PublicCiBundleError, "V064_PUBLIC_CI_PUBLIC_ROOT_INVALID"
            ):
                build_v064_public_root_commit(
                    self.repository, self.commit, public_root
                )
        self.assertFalse(
            (public_root.parent / (public_root.name + ".git")).exists()
        )

    def test_unexpected_primary_is_preserved_when_root_close_fails(self):
        public_root = Path(self.temporary.name) / "primary-close"
        stage_v064_public_ci_bundle(self.repository, self.commit, public_root)
        real_open_root = v064_public_ci_bundle._open_public_root
        real_close = os.close
        root_descriptor = []

        def record_root(root):
            descriptor, identity = real_open_root(root)
            root_descriptor.append(descriptor)
            return descriptor, identity

        def close_root_then_fail(descriptor):
            real_close(descriptor)
            if root_descriptor and descriptor == root_descriptor[0]:
                raise OSError("test-only root close failure")

        with mock.patch.object(
            v064_public_ci_bundle, "_open_public_root", side_effect=record_root
        ), mock.patch.object(
            v064_public_ci_bundle,
            "_inventory_public_root",
            side_effect=RuntimeError("test-only primary"),
        ), mock.patch.object(
            v064_public_ci_bundle.os, "close", side_effect=close_root_then_fail
        ):
            with self.assertRaisesRegex(RuntimeError, "test-only primary") as captured:
                build_v064_public_root_commit(
                    self.repository, self.commit, public_root
                )
        self.assertIn("root close failure", captured.exception.root_close_failure)

    def test_existing_parent_failure_matrix_closes_each_owned_descriptor_once(self):
        real_dup = os.dup
        real_open = os.open
        real_fstat = os.fstat
        real_stat = os.stat
        real_close = os.close
        for failure_point in ("child-fstat", "attachment-stat", "current-close"):
            with self.subTest(failure_point=failure_point):
                public_root = Path(self.temporary.name) / ("parent-" + failure_point)
                stage_v064_public_ci_bundle(self.repository, self.commit, public_root)
                root_descriptor = real_open(
                    public_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                )
                current_descriptor = []
                child_descriptor = []
                close_attempts = []
                attachment_stats = []

                def record_dup(descriptor):
                    duplicated = real_dup(descriptor)
                    current_descriptor.append(duplicated)
                    return duplicated

                def record_open(*arguments, **keywords):
                    descriptor = real_open(*arguments, **keywords)
                    child_descriptor.append(descriptor)
                    return descriptor

                def inject_fstat(descriptor):
                    if failure_point == "child-fstat" and descriptor in child_descriptor:
                        raise OSError("test-only child fstat failure")
                    return real_fstat(descriptor)

                def inject_stat(name, *arguments, **keywords):
                    if name == "src":
                        attachment_stats.append(name)
                        if failure_point == "attachment-stat" and len(attachment_stats) == 2:
                            raise OSError("test-only attachment stat failure")
                    return real_stat(name, *arguments, **keywords)

                def record_close(descriptor):
                    close_attempts.append(descriptor)
                    real_close(descriptor)
                    if (
                        failure_point == "current-close"
                        and current_descriptor
                        and descriptor == current_descriptor[0]
                    ):
                        raise OSError("test-only current close failure")

                try:
                    with mock.patch.object(
                        v064_public_ci_bundle.os, "dup", side_effect=record_dup
                    ), mock.patch.object(
                        v064_public_ci_bundle.os, "open", side_effect=record_open
                    ), mock.patch.object(
                        v064_public_ci_bundle.os, "fstat", side_effect=inject_fstat
                    ), mock.patch.object(
                        v064_public_ci_bundle.os, "stat", side_effect=inject_stat
                    ), mock.patch.object(
                        v064_public_ci_bundle.os, "close", side_effect=record_close
                    ):
                        with self.assertRaises(BaseException):
                            v064_public_ci_bundle._retained_existing_parent(
                                root_descriptor, ("src",)
                            )
                    self.assertEqual(len(current_descriptor), 1)
                    self.assertEqual(len(child_descriptor), 1)
                    self.assertNotEqual(current_descriptor[0], child_descriptor[0])
                    self.assertEqual(close_attempts.count(current_descriptor[0]), 1)
                    self.assertEqual(close_attempts.count(child_descriptor[0]), 1)
                finally:
                    real_close(root_descriptor)

    def test_read_primary_and_close_failure_matrix_preserves_first_failure(self):
        cases = (
            ("fstat", frozenset(("parent",)), ("parent_close_failure",)),
            (
                "read",
                frozenset(("file", "parent")),
                ("file_close_failure", "parent_close_failure"),
            ),
            ("stat", frozenset(("file",)), ("file_close_failure",)),
        )
        for primary_point, failing_closes, diagnostics in cases:
            with self.subTest(
                primary_point=primary_point, failing_closes=failing_closes
            ):
                captured = self._exercise_public_read_close_failures(
                    primary_point, failing_closes
                )
                self.assertIsInstance(captured.exception, RuntimeError)
                self.assertIn("test-only %s primary" % primary_point, str(captured.exception))
                for diagnostic in diagnostics:
                    self.assertIn("close failure", getattr(captured.exception, diagnostic))

    def test_read_close_failure_without_primary_is_fixed_domain_failure(self):
        for failing_closes in (
            frozenset(("file",)),
            frozenset(("parent",)),
            frozenset(("file", "parent")),
        ):
            with self.subTest(failing_closes=failing_closes):
                captured = self._exercise_public_read_close_failures(
                    None, failing_closes
                )
                self.assertIsInstance(captured.exception, V064PublicCiBundleError)
                self.assertEqual(
                    str(captured.exception), "V064_PUBLIC_CI_PUBLIC_ROOT_INVALID"
                )

    def _exercise_public_read_close_failures(self, primary_point, failing_closes):
        suffix = primary_point or "no-primary"
        suffix += "-" + "-".join(sorted(failing_closes))
        public_root = Path(self.temporary.name) / ("read-close-" + suffix)
        stage_v064_public_ci_bundle(self.repository, self.commit, public_root)
        real_retained = v064_public_ci_bundle._retained_existing_parent
        real_open = os.open
        real_fstat = os.fstat
        real_read = os.read
        real_stat = os.stat
        real_close = os.close
        root_descriptor = real_open(
            public_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        parent_descriptor = []
        file_descriptor = []
        close_attempts = []
        file_fstats = []
        file_stats = []

        def record_retained(*arguments, **keywords):
            descriptor = real_retained(*arguments, **keywords)
            parent_descriptor.append(descriptor)
            return descriptor

        def record_open(name, flags, *arguments, **keywords):
            descriptor = real_open(name, flags, *arguments, **keywords)
            if name == "ci.yml":
                file_descriptor.append(descriptor)
            return descriptor

        def inject_fstat(descriptor):
            if file_descriptor and descriptor == file_descriptor[0]:
                file_fstats.append(descriptor)
                if primary_point == "fstat" and len(file_fstats) == 1:
                    raise RuntimeError("test-only fstat primary")
            return real_fstat(descriptor)

        def inject_read(descriptor, size):
            if (
                primary_point == "read"
                and file_descriptor
                and descriptor == file_descriptor[0]
            ):
                raise RuntimeError("test-only read primary")
            return real_read(descriptor, size)

        def inject_stat(name, *arguments, **keywords):
            if name == "ci.yml":
                file_stats.append(name)
                if primary_point == "stat" and len(file_stats) == 2:
                    raise RuntimeError("test-only stat primary")
            return real_stat(name, *arguments, **keywords)

        def record_close(descriptor):
            role = None
            if file_descriptor and descriptor == file_descriptor[0]:
                role = "file"
            elif parent_descriptor and descriptor == parent_descriptor[0]:
                role = "parent"
            if role is not None:
                close_attempts.append(role)
            real_close(descriptor)
            if role in failing_closes:
                raise OSError("test-only %s close failure" % role)

        try:
            with mock.patch.object(
                v064_public_ci_bundle,
                "_retained_existing_parent",
                side_effect=record_retained,
            ), mock.patch.object(
                v064_public_ci_bundle.os, "open", side_effect=record_open
            ), mock.patch.object(
                v064_public_ci_bundle.os, "fstat", side_effect=inject_fstat
            ), mock.patch.object(
                v064_public_ci_bundle.os, "read", side_effect=inject_read
            ), mock.patch.object(
                v064_public_ci_bundle.os, "stat", side_effect=inject_stat
            ), mock.patch.object(
                v064_public_ci_bundle.os, "close", side_effect=record_close
            ):
                with self.assertRaises(BaseException) as captured:
                    v064_public_ci_bundle._read_public_file(
                        public_root / ".github" / "workflows" / "ci.yml",
                        root_descriptor,
                        ".github/workflows/ci.yml",
                    )
            self.assertEqual(close_attempts.count("file"), 1)
            self.assertEqual(close_attempts.count("parent"), 1)
            return captured
        finally:
            real_close(root_descriptor)

    def test_verifier_replays_exact_root_and_rejects_an_extra_file(self):
        public_root = Path(self.temporary.name) / "verified"
        stage_v064_public_ci_bundle(self.repository, self.commit, public_root)
        verified = verify_v064_public_ci_bundle(
            self.repository, self.commit, public_root
        )
        self.assertEqual(verified["status"], "V064_PUBLIC_CI_BUNDLE_VERIFIED")
        self.assertEqual(verified["file_count"], 8)

        (public_root / "extra.txt").write_bytes(b"extra\n")
        with self.assertRaisesRegex(
            V064PublicCiBundleError, "V064_PUBLIC_CI_PUBLIC_ROOT_INVALID"
        ):
            verify_v064_public_ci_bundle(self.repository, self.commit, public_root)


class V064PublicCiFinalFreezeTests(unittest.TestCase):
    def head(self):
        return _git_bytes(ROOT, "rev-parse", "HEAD^{commit}").decode("ascii").strip()

    def test_final_private_ancestry_failures_and_public_inventory_remain_closed(self):
        head = self.head()
        self.assertNotEqual(head, PRIVATE_F2)
        self.assertEqual(
            _git_bytes(ROOT, "rev-parse", PRIVATE_F2 + "^{tree}")
            .decode("ascii")
            .strip(),
            PRIVATE_F2_TREE,
        )
        _git_bytes(ROOT, "merge-base", "--is-ancestor", PRIVATE_F2, head)

        failure = load_v064_public_ci_r2_failure_root(
            ROOT / "artifacts" / "v064-public-ci-r2-failure"
        )
        self.assertEqual(
            failure["private_source"],
            {"candidate_commit": PRIVATE_F2, "candidate_tree": PRIVATE_F2_TREE},
        )
        self.assertEqual(
            failure["public_source"],
            {
                "repository": "cjl308868584-lang/crypto-quant-v064-public-ci-r2",
                "root_commit": "5541aba00e4e93e6389c2c61a81e69c2dd228947",
                "root_tree": "3d732e8e1fbb9cf94541f6e26e778d5eb21ca8f3",
            },
        )
        self.assertEqual(
            failure["workflow"]["blob_oid"],
            "ba5b6851ed53ad79100409b92c78c09c07608ed2",
        )
        self.assertFalse((ROOT / "artifacts" / "v064-public-ci-r2").exists())

        manifest = build_v064_public_ci_bundle_manifest(ROOT, head)
        self.assertEqual(
            manifest["public_repository"],
            "cjl308868584-lang/crypto-quant-v064-public-ci-r3",
        )
        self.assertEqual(
            [
                item.get("repository", item.get("public_source", {}).get("repository"))
                for item in manifest["predecessor_failed_public_witnesses"]
            ],
            [
                "cjl308868584-lang/crypto-quant-v064-public-ci",
                "cjl308868584-lang/crypto-quant-v064-public-ci-r2",
            ],
        )
        self.assertEqual(
            tuple(
                sorted(
                    [item["path"] for item in manifest["files"]]
                    + ["bundle-manifest-v1.json"]
                )
            ),
            PUBLIC_INVENTORY,
        )
        entries = {item["path"]: item for item in manifest["files"]}
        for relative in CURRENT_PUBLIC_GIT_SOURCES:
            with self.subTest(relative=relative):
                expected_oid = (
                    _git_bytes(ROOT, "rev-parse", f"{head}:{relative}")
                    .decode("ascii")
                    .strip()
                )
                self.assertEqual(entries[relative]["source_blob_oid"], expected_oid)

    def test_evaluator_build_manifest_exactly_replays_final_inputs(self):
        manifest = json.loads(
            (ROOT / "config" / "evaluator-build-manifest-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            {
                "manifest_version": manifest["manifest_version"],
                "package_version": manifest["package_version"],
                "metric_catalog_version": manifest["metric_catalog_version"],
                "schema_version": manifest["schema_version"],
            },
            {
                "manifest_version": "1.61.0",
                "package_version": "0.67.0",
                "metric_catalog_version": "1.1.6",
                "schema_version": "1.0.0",
            },
        )
        expected_paths = EvaluatorBuild.expected_file_paths(ROOT)
        expected_hashes = EvaluatorBuild.file_hashes(ROOT, expected_paths)
        self.assertEqual(tuple(manifest["file_hashes"]), expected_paths)
        self.assertEqual(manifest["file_hashes"], expected_hashes)
        self.assertEqual(
            manifest["build_input_tree_hash"], business_hash(expected_hashes)
        )
        self.assertEqual(
            manifest["manifest_hash"], artifact_self_hash(manifest, "manifest_hash")
        )

    def test_final_candidate_rebuild_is_exact_parentless_and_ref_closed(self):
        head = self.head()
        candidates = []
        candidate_bytes = []
        temporary_parent = (
            Path("/private/tmp")
            if sys.platform == "darwin" and Path("/private/tmp").is_dir()
            else ROOT
        )
        with tempfile.TemporaryDirectory(
            prefix="v064-r3-final-replay-", dir=temporary_parent
        ) as temporary:
            temporary_root = Path(temporary)
            for name in ("first", "second"):
                public_root = temporary_root / name
                stage_v064_public_ci_bundle(ROOT, head, public_root)
                candidate = build_v064_public_root_commit(ROOT, head, public_root)
                replayed = build_v064_public_root_commit(ROOT, head, public_root)
                verified = verify_v064_public_ci_bundle(ROOT, head, public_root)
                self.assertEqual(replayed, candidate)
                self.assertEqual(verified["commit"], candidate["commit"])
                self.assertEqual(verified["tree"], candidate["tree"])
                self.assertEqual(candidate["parent_count"], 0)
                self.assertEqual(tuple(candidate["paths"]), PUBLIC_INVENTORY)

                git_directory = Path(candidate["git_directory"])
                self.assertEqual(
                    _bare_git_bytes(
                        git_directory,
                        "for-each-ref",
                        "--format=%(refname) %(objectname)",
                    ),
                    ("refs/heads/main %s\n" % candidate["commit"]).encode("ascii"),
                )
                self.assertEqual(
                    _bare_git_bytes(git_directory, "rev-list", "--count", "--all"),
                    b"1\n",
                )
                self.assertNotIn(
                    b"\nparent ",
                    b"\n"
                    + _bare_git_bytes(
                        git_directory, "cat-file", "commit", candidate["commit"]
                    ),
                )
                candidates.append(candidate)
                candidate_bytes.append(
                    {
                        relative: (public_root / relative).read_bytes()
                        for relative in PUBLIC_INVENTORY
                    }
                )
        self.assertEqual(candidates[0]["commit"], candidates[1]["commit"])
        self.assertEqual(candidates[0]["tree"], candidates[1]["tree"])
        self.assertEqual(candidate_bytes[0], candidate_bytes[1])


class V064PublicCiWorkflowContractTests(unittest.TestCase):
    def test_historical_r2_child_resolves_system_python_after_path_is_dropped(self):
        workflow = _git_bytes(
            ROOT,
            "show",
            "5bc01c9:public_ci/v064/.github/workflows/ci.yml",
        )
        self.assertEqual(
            _git_bytes(ROOT, "hash-object", "--stdin", input_bytes=workflow)
            .decode("ascii")
            .strip(),
            "ba5b6851ed53ad79100409b92c78c09c07608ed2",
        )
        fixed_owner = _extract_workflow_step(
            workflow, "Run fixed-owner public boundary"
        )
        sudo_lines = [line for line in fixed_owner.splitlines() if line.startswith(b"sudo -u ")]
        self.assertEqual(len(sudo_lines), 1)
        self.assertIn(b"python --version", sudo_lines[0])
        self.assertIn(b"exec python -m unittest", sudo_lines[0])
        with tempfile.TemporaryDirectory() as temporary:
            environment, invocation_log, sudo_log = _fixed_owner_fixture(
                temporary, "3.9", "system"
            )
            environment["FIXTURE_MODE"] = "historical"
            runner_python = str(Path(temporary) / "runner-bin" / "python")
            command = (
                b'test "$(command -v python)" = "$EXPECTED_SETUP_PYTHON"\n'
                + sudo_lines[0]
                + b"\n"
            )
            result = subprocess.run(
                ("/bin/bash", "-c", command),
                cwd=temporary,
                env=dict(environment, EXPECTED_SETUP_PYTHON=runner_python),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            invocations = invocation_log.read_text(encoding="utf-8").splitlines()
            sudo_invocations = sudo_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            invocations,
            [
                "system|version|--version",
                "system|test|-m unittest -v tests/test_v064_linux_supersession_publish.py",
            ],
        )
        self.assertEqual(len(sudo_invocations), 1)

    def test_workflow_carries_one_absolute_matrix_interpreter_as_fixed_argument(self):
        workflow = (TEMPLATE_ROOT / ".github/workflows/ci.yml").read_bytes()
        fixed_owner = _extract_workflow_step(
            workflow, "Run fixed-owner public boundary"
        )
        expected_handoff = b"""python_bin="$(command -v python)"
test -n "$python_bin"
case "$python_bin" in /*) ;; *) exit 1 ;; esac
test -x "$python_bin"
test "$("$python_bin" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = "${{ matrix.python-version }}"
sudo -u '#501' env HOME=/opt/v064-public-ci-home TMPDIR=/opt/v064-public-ci-home \\
  V064_PUBLIC_LINUX_REQUIRED=1 PYTHONPATH=/opt/v064-public-ci-workspace/src:/opt/v064-public-ci-workspace/tests \\
  /bin/bash -c 'set -euo pipefail; /usr/bin/uname -sr; /usr/bin/ldd --version | /usr/bin/head -1; "$1" --version; cd /opt/v064-public-ci-workspace; exec "$1" -m unittest -v tests/test_v064_linux_supersession_publish.py' \\
  v064-fixed-owner "$python_bin"
"""
        self.assertTrue(fixed_owner.endswith(expected_handoff))
        handoff = fixed_owner[fixed_owner.index(b'python_bin="$(command -v python)"') :]
        self.assertEqual(handoff.count(b'python_bin="$(command -v python)"'), 1)
        self.assertNotIn(b" PATH=", handoff)
        self.assertNotIn(b"/usr/bin/env python", handoff)
        sudo_command = b" ".join(
            line.rstrip(b" \\") for line in handoff.splitlines() if line
        )
        arguments = shlex.split(sudo_command.decode("utf-8"))
        child_index = arguments.index("/bin/bash")
        child = arguments[child_index + 2]
        self.assertNotIn("python", child.replace('"$1"', ""))
        self.assertEqual(arguments[-2:], ["v064-fixed-owner", "$python_bin"])

    def test_setup_python_with_matrix_input_precedes_interpreter_capture(self):
        workflow = (TEMPLATE_ROOT / ".github/workflows/ci.yml").read_bytes()
        _assert_setup_python_precedes_interpreter_capture(workflow)
        capture = b'          python_bin="$(command -v python)"\n'
        setup = (
            b"      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1\n"
        )
        moved = workflow.replace(capture, b"", 1).replace(
            setup, capture + setup, 1
        )
        with self.assertRaisesRegex(
            AssertionError, "workflow step order changed|interpreter capture"
        ):
            _assert_setup_python_precedes_interpreter_capture(moved)

    def test_missing_child_path_uses_exact_fixed_39_binary_once_for_tests(self):
        workflow = (TEMPLATE_ROOT / ".github/workflows/ci.yml").read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            environment, invocation_log, sudo_log = _fixed_owner_fixture(
                temporary, "3.9", "missing"
            )
            result = _run_current_interpreter_handoff(
                workflow, "3.9", environment, temporary
            )
            invocations = invocation_log.read_text(encoding="utf-8").splitlines()
            sudo_invocations = sudo_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual([line.split("|", 2)[:2] for line in invocations], [
            ["setup-3.9", "precheck"],
            ["setup-3.9", "version"],
            ["setup-3.9", "test"],
        ])
        self.assertEqual(sum("|test|" in line for line in invocations), 1)
        self.assertEqual(len(sudo_invocations), 1)

    def test_poisoned_child_path_uses_exact_fixed_312_binary_once_for_tests(self):
        workflow = (TEMPLATE_ROOT / ".github/workflows/ci.yml").read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            environment, invocation_log, sudo_log = _fixed_owner_fixture(
                temporary, "3.12", "poisoned"
            )
            result = _run_current_interpreter_handoff(
                workflow, "3.12", environment, temporary
            )
            invocations = invocation_log.read_text(encoding="utf-8").splitlines()
            sudo_invocations = sudo_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual([line.split("|", 2)[:2] for line in invocations], [
            ["setup-3.12", "precheck"],
            ["setup-3.12", "version"],
            ["setup-3.12", "test"],
        ])
        self.assertNotIn("poison|", "\n".join(invocations))
        self.assertEqual(sum("|test|" in line for line in invocations), 1)
        self.assertEqual(len(sudo_invocations), 1)

    def test_relative_and_non_executable_interpreter_candidates_fail_before_sudo(self):
        workflow = (TEMPLATE_ROOT / ".github/workflows/ci.yml").read_bytes()
        for candidate_kind in ("relative", "non-executable"):
            with self.subTest(candidate_kind=candidate_kind), tempfile.TemporaryDirectory() as temporary:
                environment, invocation_log, sudo_log = _fixed_owner_fixture(
                    temporary, "3.9", "missing"
                )
                runner_python = Path(temporary) / "runner-bin" / "python"
                if candidate_kind == "relative":
                    environment["PATH"] = "runner-bin"
                else:
                    runner_python.chmod(0o644)
                    environment["PATH"] = str(runner_python.parent)
                result = _run_current_interpreter_handoff(
                    workflow, "3.9", environment, temporary
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(sudo_log.exists())
                self.assertFalse(invocation_log.exists())

    def test_reported_312_for_39_matrix_fails_before_sudo(self):
        workflow = (TEMPLATE_ROOT / ".github/workflows/ci.yml").read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            environment, invocation_log, sudo_log = _fixed_owner_fixture(
                temporary, "3.12", "missing"
            )
            result = _run_current_interpreter_handoff(
                workflow, "3.9", environment, temporary
            )
            invocations = invocation_log.read_text(encoding="utf-8").splitlines()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            [line.split("|", 2)[:2] for line in invocations],
            [["setup-3.12", "precheck"]],
        )
        self.assertFalse(sudo_log.exists())

    def test_public_readme_names_r3_engineering_purpose_and_failure_ancestry(self):
        body = (TEMPLATE_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("R3 is an engineering correction candidate", body)
        self.assertIn("R1 Run 31850146784 failure", body)
        self.assertIn("R2", body)
        self.assertIn("immutable predecessor evidence", body)

    def test_exact_f_preflight_reproduces_public_sensitive_self_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "old"
            _write_closed_checkout(checkout, PRIVATE_F, use_worktree=False)
            result = _run_exact_preflight(
                checkout, "cjl308868584-lang/crypto-quant-v064-public-ci"
            )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"PUBLIC_SENSITIVE_BYTES_INVALID\n")

    def test_exact_r3_preflight_accepts_closed_checkout_and_rejects_r2(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "r3"
            head = _git_bytes(ROOT, "rev-parse", "HEAD").decode("ascii").strip()
            _write_closed_checkout(checkout, head, use_worktree=True)
            accepted = _run_exact_preflight(
                checkout, "cjl308868584-lang/crypto-quant-v064-public-ci-r3"
            )
            rejected = _run_exact_preflight(
                checkout, "cjl308868584-lang/crypto-quant-v064-public-ci-r2"
            )
        self.assertEqual(
            accepted.returncode, 0, accepted.stderr.decode("utf-8", "replace")
        )
        self.assertIn(b"source_candidate_f=", accepted.stdout)
        self.assertEqual(accepted.stderr, b"")
        self.assertEqual(rejected.returncode, 1)
        self.assertEqual(rejected.stdout, b"")
        self.assertEqual(rejected.stderr, b"")

    def test_exact_r3_preflight_rejects_resealed_sensitive_payloads(self):
        payloads = (
            (b"/" + b"Users/fixture\n", b"PUBLIC_SENSITIVE_BYTES_INVALID\n"),
            (b"BEGIN " + b"PRIVATE KEY\n", b"PUBLIC_SENSITIVE_BYTES_INVALID\n"),
            (b"gh" + b"p_" + b"A" * 40 + b"\n", b"PUBLIC_SENSITIVE_BYTES_INVALID\n"),
            (b"owner" + b"@" + b"example.invalid\n", b"PUBLIC_EMAIL_INVALID\n"),
            (b"https" + b"://example.invalid/path\n", b"PUBLIC_URL_INVALID\n"),
            (b"bro" + b"kerclient\n", b"PUBLIC_FORBIDDEN_TERM\n"),
        )
        for index, (payload, reason) in enumerate(payloads):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                checkout = Path(temporary) / "r3"
                head = _git_bytes(ROOT, "rev-parse", "HEAD").decode("ascii").strip()
                _write_closed_checkout(checkout, head, use_worktree=True)
                _replace_readme_and_reseal(checkout, payload)
                result = _run_exact_preflight(
                    checkout, "cjl308868584-lang/crypto-quant-v064-public-ci-r3"
                )
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, reason)

    def test_exact_r3_preflight_rejects_any_other_literal_child_argument(self):
        mutations = (
            (
                b'[sys.executable, "-c", CRASH_CHILD, str(parent), "directory-fsync"]',
                b'[sys.executable, "-c", CRASH_CHILD, str(parent), "other-fixed"]',
            ),
            (
                b'[sys.executable, "-c", RETRY_CHILD, str(parent)]',
                b'[sys.executable, "-c", RETRY_CHILD, str(parent), "directory-fsync"]',
            ),
        )
        for before, after in mutations:
            with self.subTest(after=after), tempfile.TemporaryDirectory() as temporary:
                checkout = Path(temporary) / "r3"
                head = _git_bytes(ROOT, "rev-parse", "HEAD").decode("ascii").strip()
                _write_closed_checkout(checkout, head, use_worktree=True)
                relative = "tests/test_v064_linux_supersession_publish.py"
                body = (checkout / relative).read_bytes()
                self.assertGreaterEqual(body.count(before), 1)
                _replace_file_and_reseal(
                    checkout, relative, body.replace(before, after, 1)
                )
                result = _run_exact_preflight(
                    checkout, "cjl308868584-lang/crypto-quant-v064-public-ci-r3"
                )
                self.assertEqual(
                    result.stderr, b"PUBLIC_SUBPROCESS_TARGET_INVALID\n"
                )

    def test_workflow_has_only_bounded_events_permissions_and_pinned_actions(self):
        workflow = (TEMPLATE_ROOT / ".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("push:\n    branches: [main]", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        for forbidden in (
            "pull_request:",
            "pull_request_target:",
            "issues:",
            "issue_comment:",
            "permissions: write",
            "contents: write",
            "id-token:",
            "secrets.",
            "actions/cache",
            "upload-artifact",
        ):
            self.assertNotIn(forbidden, workflow)
        self.assertEqual(workflow.count("permissions:\n  contents: read"), 1)
        self.assertEqual(
            workflow.count(
                "actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09"
            ),
            1,
        )
        self.assertEqual(
            workflow.count(
                "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
            ),
            1,
        )
        self.assertIn('python-version: ["3.9", "3.12"]', workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("! getent passwd 501", workflow)
        self.assertIn("! getent group 501", workflow)
        self.assertIn("V064_PUBLIC_LINUX_REQUIRED=1", workflow)
        for required in (
            '"hash-object", "--", item["path"]',
            "PUBLIC_BLOB_IDENTITY_INVALID",
            "PUBLIC_SENSITIVE_BYTES_INVALID",
            "PUBLIC_IMPORT_SET_INVALID",
            "PUBLIC_DYNAMIC_CALL_INVALID",
            "PUBLIC_SUBPROCESS_TARGET_INVALID",
            "PUBLIC_EMAIL_INVALID",
            "PUBLIC_URL_INVALID",
            "PUBLIC_FORBIDDEN_TERM",
            "install -d -o 501 -g 501 -m 755 /opt/v064-public-ci-home/artifacts/challenger-replacement",
            'print("source_candidate_f="',
            'print("public_commit="',
            'print("manifest_sha256="',
            'print("file_set_sha256="',
        ):
            self.assertIn(required, workflow)
        self.assertEqual(
            workflow.count(
                '"$1" -m unittest -v tests/test_v064_linux_supersession_publish.py'
            ),
            1,
        )


class V064PublicCiBundleCliTests(unittest.TestCase):
    def test_cli_has_only_fixed_r3_candidate_and_no_repository_or_path_input(self):
        self.assertEqual(
            v064_public_ci_bundle_cli._CANDIDATE,
            Path("/private/tmp/crypto-quant-v064-public-ci-r3-candidate"),
        )
        self.assertEqual(
            tuple(inspect.signature(v064_public_ci_bundle_cli._build).parameters), ()
        )
        self.assertEqual(
            tuple(inspect.signature(v064_public_ci_bundle_cli._verify).parameters), ()
        )
        source = inspect.getsource(v064_public_ci_bundle_cli)
        for forbidden in ("--repository", "--candidate", "--path", "--output"):
            self.assertNotIn(forbidden, source)
