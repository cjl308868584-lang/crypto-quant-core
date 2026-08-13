import copy
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, ValidationError

from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant.v064_public_ci_bundle import (
    V064PublicCiBundleError,
    build_v064_public_root_commit,
    build_v064_public_ci_bundle_manifest,
    load_v064_public_ci_bundle_manifest,
    stage_v064_public_ci_bundle,
    verify_v064_public_ci_bundle,
)


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
        "schema_version": "1.0.0",
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
        "public_repository": "cjl308868584-lang/crypto-quant-v064-public-ci",
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


class V064PublicCiSchemaTests(unittest.TestCase):
    def schema(self):
        return json.loads(CONFIG_SCHEMA.read_text(encoding="utf-8"))

    def test_config_and_package_schemas_are_exact_valid_mirrors(self):
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        schema = self.schema()
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(valid_bundle_manifest())

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


class V064PublicCiWorkflowContractTests(unittest.TestCase):
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
        self.assertIn(
            "cd /opt/v064-public-ci-workspace && python --version && uname -sr && ldd --version | head -1 && exec python -m unittest -v tests/test_v064_linux_supersession_publish.py",
            workflow,
        )
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
                "python -m unittest -v tests/test_v064_linux_supersession_publish.py"
            ),
            1,
        )
