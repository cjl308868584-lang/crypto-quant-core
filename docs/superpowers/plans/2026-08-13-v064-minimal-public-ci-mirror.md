# v0.64 Minimal Public CI Witness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a permanently auditable, minimal public Linux CI witness that proves the exact v0.64 private candidate's `renameat2(RENAME_NOREPLACE)` boundary on GitHub-hosted Ubuntu Python 3.9/3.12 without exposing the private project or weakening the frozen evidence gates.

**Architecture:** The private repository remains the only project and release authority. A private commit `F` contains a fixed public-bundle builder/verifier, an exact original publisher blob, a public-only standard-library Linux test, schemas, templates, and a strict witness loader. After local review, the builder creates one deterministic public root commit from a closed file allowlist; the public repository executes only the bound Linux test. A strict acquisition step seals GitHub run/job/log bytes, and a successor private commit `G` adds the derived witness while proving every public-source blob stayed unchanged. Task 5 of the existing v0.64 supersession ceremony resumes only from `G`.

**Tech Stack:** Python 3.9+ standard library, `unittest`, Draft 2020-12 JSON Schema through the existing root dependency, canonical JSON/SHA-256, Git object plumbing, GitHub CLI/API, GitHub Actions Ubuntu Python 3.9/3.12, Linux `ctypes` `renameat2`, macOS `renameatx_np` regression coverage.

## Global Constraints

- Authority stays in private `cjl308868584-lang/crypto-quant-core`; never change its visibility.
- The permanent public repository name is exactly `cjl308868584-lang/crypto-quant-v064-public-ci`.
- No public repository creation, public push, workflow dispatch, private push/PR replacement, merge, tag, owner attestation, installation, service start, production-root write, credential creation, Broker, order, or funding action without the user approval specified by the existing project contract.
- Public tracked paths are a closed set: `.github/workflows/ci.yml`, `.gitignore`, `README.md`, `SECURITY.md`, `NOTICE.md`, `bundle-manifest-v1.json`, `src/crypto_quant/challenger_replacement_supersession_publish.py`, and `tests/test_v064_linux_supersession_publish.py`.
- Never publish private Git history, `artifacts/`, private `docs/`, strategy/economic inputs, receipts/results, owner declarations, machine-absence evidence, production paths, personal email, credentials, or any non-allowlisted file.
- The original publisher bytes in the public repository must equal the same path's Git blob in private source commit `F`.
- The public-only test must be tracked in `F` and copied byte-for-byte; it uses only the Python standard library and loads the publisher with `importlib.util.spec_from_file_location`.
- Public manifest identity binds `F`; it does not contain public commit/tree OIDs and cannot contain later private commit `G`.
- Public workflow uses only owner `push` to `main` and `workflow_dispatch`; it must not use `pull_request`, `pull_request_target`, issue, comment, or fork events.
- Public workflow token permissions are exactly `contents: read`; checkout uses `persist-credentials: false`; no secrets, OIDC, package/cache/artifact upload, deployment, or write permission.
- `actions/checkout` is pinned to `fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09` and `actions/setup-python` is pinned to `ece7cb06caefa5fff74198d8649806c4678c61a1`; never use floating tags.
- Linux Python 3.9 and 3.12 jobs must execute real `renameat2` behavior with no skip, mock, `continue-on-error`, or synthesized PASS.
- Public repository creation/push is irreversible disclosure. Before it, show the user the exact repository name, eight-file set, every SHA-256, manifest/file-set hash, private `F`, candidate public commit/tree, and sensitive-information scan result, then obtain a targeted approval.
- Public run failure remains failure. A rerun is allowed once only when GitHub infrastructure failed before any test step on the exact same public commit.
- Public witness results never establish strategy correctness, profitability, AI advantage, Paper completion, Canary eligibility, or live-trading authorization.
- v0.62 plan/tag/bytes remain immutable. Old failed Task 5/6 artifacts and owner approvals are never reused.
- No generic mirroring platform, daemon, generalized release bot, trading engine, Broker/order lifecycle, UI, or third-party runtime dependency.
- Apply TDD for every code/behavior change: exact RED, minimal GREEN, refactor only while green.
- Run focused tests during tasks. Run one complete local suite only for final private code state `F`, followed by one independent complete review; valid fixes receive targeted re-review only.

---

## File Map

### Private source and governance files

- Modify: `docs/superpowers/specs/2026-08-09-replacement-challenger-plan-v2-supersession-design.md` — explicit transport amendment; preserves the failed private CI evidence and distinguishes private review from the public Linux witness.
- Modify: `docs/superpowers/plans/2026-08-09-replacement-challenger-plan-v2-supersession.md` — replaces only the unavailable Linux-transport steps with the exact `F`/public-run/`G` gate; all later Task 5–8 ceremony requirements remain.
- Modify: `docs/superpowers/specs/2026-08-12-v064-minimal-public-ci-mirror-design.md` — final design wording and exact implementation identities if review requires clarification.
- Create: `config/v064-public-ci-bundle-manifest-v1.schema.json` — configuration mirror for the closed bundle manifest.
- Create: `src/crypto_quant/schemas/v064-public-ci-bundle-manifest-v1.schema.json` — package mirror, byte-identical to config schema.
- Create: `config/v064-public-ci-witness-v1.schema.json` — configuration mirror for the private post-run witness.
- Create: `src/crypto_quant/schemas/v064-public-ci-witness-v1.schema.json` — package mirror, byte-identical to config schema.
- Create: `src/crypto_quant/v064_public_ci_bundle.py` — bundle manifest builder/loader, private Git-object reader, closed-set exporter, sensitive-byte policy, deterministic public Git object builder, and local replay verifier.
- Create: `src/crypto_quant/v064_public_ci_bundle_cli.py` — fixed-repository, fixed-path, no-network local candidate generation/replay CLI; no arbitrary output path or callback.
- Create: `src/crypto_quant/v064_public_ci_witness.py` — run/job/log transcript loader, strict result derivation, witness builder/loader, and `F`→`G` unchanged-blob proof.
- Create: `src/crypto_quant/v064_public_ci_witness_cli.py` — fixed GitHub repository/run acquisition and fixed private candidate output CLI; credentials are inherited by `gh` but never read, recorded, or printed by Python.
- Create: `tests/test_v064_public_ci_bundle.py` — schemas, manifest, closed set, Git-object source, scan, export, deterministic root commit, and CLI tests.
- Create: `tests/test_v064_linux_supersession_publish.py` — byte-identical public-only standard-library Linux/Darwin portability test.
- Create: `tests/test_v064_public_ci_witness.py` — API/log transcript, job-step derivation, failure closure, witness loader, and `F`→`G` tests.
- Modify: `config/evaluator-build-manifest-v1.json` — include new private production/schema/test/design inputs only after final code settles; do not change package version in `F`.

### Private public-template files

- Create: `public_ci/v064/.github/workflows/ci.yml` — pinned, read-only, owner-only-event workflow.
- Create: `public_ci/v064/.gitignore` — denies all local additions except the exact public path set; the exporter still enforces the set independently.
- Create: `public_ci/v064/README.md` — narrow Linux-witness purpose and explicit non-claims.
- Create: `public_ci/v064/SECURITY.md` — GitHub private vulnerability reporting only; no personal email.
- Create: `public_ci/v064/NOTICE.md` — copyright retained, inspection/replay purpose, no open-source license grant.

### Generated but not committed before approval

- Local owner-only candidate repository root with exactly eight public files and one deterministic root commit.
- Public `bundle-manifest-v1.json`, generated from private commit `F` and templates.
- No public GitHub repository, branch, run, tag, or release until the targeted approval gate.

### Post-run private evidence files in successor `G`

- Create: `artifacts/v064-public-ci/v064-public-ci-run-api-v1.json` — exact `gh api` stdout bytes for the fixed run endpoint.
- Create: `artifacts/v064-public-ci/v064-public-ci-jobs-api-v1.json` — exact `gh api` stdout bytes for the fixed jobs endpoint.
- Create: `artifacts/v064-public-ci/v064-public-ci-run-log-v1.txt` — exact `gh run view --log` stdout bytes.
- Create: `artifacts/v064-public-ci/v064-public-ci-acquisition-transcript-v1.json` — exact fixed argv, exit codes, stdout/stderr SHA-256 and byte counts; never credential values.
- Create: `artifacts/v064-public-ci/v064-public-ci-witness-v1.json` — canonical derived witness.
- Modify: `tests/test_v064_public_ci_witness.py` — remove only the exact formal-artifact skip and add committed-byte regression; do not modify production code after public CI.
- Modify: `config/evaluator-build-manifest-v1.json` — bind the exact post-run witness inputs/artifacts at `G`.

---

## Task 1: Freeze the Transport Amendment Before Code

**Files:**
- Modify: `docs/superpowers/specs/2026-08-09-replacement-challenger-plan-v2-supersession-design.md`
- Modify: `docs/superpowers/plans/2026-08-09-replacement-challenger-plan-v2-supersession.md`
- Modify: `docs/superpowers/specs/2026-08-12-v064-minimal-public-ci-mirror-design.md`

**Interfaces:**
- Consumes: failed private run `31436609135`, private PR #32, confirmed public-mirror design.
- Produces: exact `F`/public-run/`G` governance language that later builders and ceremony gates must enforce.

- [ ] **Step 1: Capture the pre-amendment contradiction**

Run read-only searches showing that the existing frozen documents still require Linux jobs inside the private Draft PR and do not define `F`/`G`. Save the exact command/output in the Task 1 checkpoint; do not add a permanent unit test that merely greps human prose.

- [ ] **Step 2: Make the minimum explicit document amendment**

Add a dated amendment that says:

```text
PRIVATE_PR_CI_NOT_EXECUTED_BILLING_BLOCKED = run 31436609135
PUBLIC_SOURCE_CANDIDATE_F = reviewed private source commit exported byte-for-byte
PUBLIC_LINUX_PORTABILITY_WITNESS_NOT_PRIVATE_PR_CHECK = independent bound transport
POST_WITNESS_PRIVATE_CANDIDATE_G = strict descendant of F with unchanged public-source blobs
```

State that this changes only the unavailable CI transport, not the test semantics, thresholds, private release authority, v0.62 bytes, owner-approval gate, or Task 5–8 evidence ceremony.

- [ ] **Step 3: Run document verification and diff checks**

Run the targeted marker/heading searches, then:

```bash
git diff --check
git diff -- docs/superpowers/specs/2026-08-09-replacement-challenger-plan-v2-supersession-design.md \
  docs/superpowers/plans/2026-08-09-replacement-challenger-plan-v2-supersession.md \
  docs/superpowers/specs/2026-08-12-v064-minimal-public-ci-mirror-design.md
```

Expected: each marker occurs in the intended amended section; original Task 5–8 headings and owner-attestation approval requirements remain; diff changes only the explicit transport paragraphs and this implementation-plan correction. Later Schema/builder/exporter/witness tests enforce the machine behavior and identities rather than testing prose.

- [ ] **Step 4: Commit**

```bash
git add \
  docs/superpowers/specs/2026-08-09-replacement-challenger-plan-v2-supersession-design.md \
  docs/superpowers/plans/2026-08-09-replacement-challenger-plan-v2-supersession.md \
  docs/superpowers/specs/2026-08-12-v064-minimal-public-ci-mirror-design.md \
  docs/superpowers/plans/2026-08-13-v064-minimal-public-ci-mirror.md
git commit -m "docs: preregister public Linux witness transport"
```

---

## Task 2: Add Strict Bundle and Witness Schemas

**Files:**
- Create: `config/v064-public-ci-bundle-manifest-v1.schema.json`
- Create: `src/crypto_quant/schemas/v064-public-ci-bundle-manifest-v1.schema.json`
- Create: `config/v064-public-ci-witness-v1.schema.json`
- Create: `src/crypto_quant/schemas/v064-public-ci-witness-v1.schema.json`
- Create: `tests/test_v064_public_ci_bundle.py`
- Create: `tests/test_v064_public_ci_witness.py`

**Interfaces:**
- Consumes: canonical JSON conventions and strict closed-object schema patterns.
- Produces: exact Draft 2020-12 schemas used by `load_v064_public_ci_bundle_manifest(path)` and `load_v064_public_ci_witness(path)`.

- [ ] **Step 1: Write schema RED tests**

Require config/package mirrors to be byte-identical, Draft 2020-12 valid, `additionalProperties: false` at every object, and exact enums/const values. Include mutation tests for:

```python
for mutation in (
    lambda v: v.update(purpose="FULL_PROJECT_CI"),
    lambda v: v["safety"].update(orders_allowed=True),
    lambda v: v["files"].append(v["files"][0]),
    lambda v: v["source"].update(candidate_commit="not-a-sha"),
):
    with self.assertRaises(ValidationError):
        Draft202012Validator(schema).validate(mutated(mutation))
```

Witness schema must require exact two Python jobs (`3.9`, `3.12`), success conclusions, nonempty step arrays, raw evidence SHA/size identities, exact private source `F`, and false trading permissions. It must reject a `candidate_g` field: `G` does not exist when witness bytes are built, so ancestry is externally verified after commit.

- [ ] **Step 2: Run RED**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_bundle.V064PublicCiSchemaTests \
  tests.test_v064_public_ci_witness.V064PublicCiWitnessSchemaTests
```

Expected: import/file-not-found failures for the four schemas.

- [ ] **Step 3: Add the minimum strict schemas**

Use exact public-manifest top-level keys:

```json
[
  "$schema", "schema_version", "purpose", "source", "public_repository",
  "files", "file_set_sha256", "safety", "non_claims"
]
```

Use exact witness top-level keys:

```json
[
  "$schema", "schema_version", "witness_id", "witness_hash", "status",
  "private_source", "public_source", "bundle", "workflow", "run",
  "jobs", "raw_evidence", "ancestry", "safety", "non_claims"
]
```

Require lowercase 40- or 64-hex Git OIDs according to the repository object format discovered by Git; all content SHA-256 values are exactly 64 lowercase hex.

- [ ] **Step 4: Run GREEN**

Run the two schema test classes and `git diff --check`.

- [ ] **Step 5: Commit**

```bash
git add config/v064-public-ci-*-v1.schema.json \
  src/crypto_quant/schemas/v064-public-ci-*-v1.schema.json \
  tests/test_v064_public_ci_bundle.py tests/test_v064_public_ci_witness.py
git commit -m "feat: add strict public CI witness schemas"
```

---

## Task 3: Build the Public-Only Portability Test with TDD

**Files:**
- Create: `tests/test_v064_linux_supersession_publish.py`
- Test source: `src/crypto_quant/challenger_replacement_supersession_publish.py`

**Interfaces:**
- Consumes: publisher module loaded by fixed file path.
- Produces: a standard-library test module whose exact bytes are exported to the public witness repository.

- [ ] **Step 1: Add the loader and first failing Linux primitive test**

Load only the fixed file:

```python
MODULE_PATH = ROOT / "src/crypto_quant/challenger_replacement_supersession_publish.py"
spec = importlib.util.spec_from_file_location("v064_public_publisher", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
```

Write a Linux-only assertion that fails on Darwin with a fixed `UNSUPPORTED_TEST_HOST` only when run locally, but in the public workflow Linux is mandatory and no unittest skip decorator is allowed. The workflow passes `V064_PUBLIC_LINUX_REQUIRED=1`; under that setting any non-Linux host is a test failure.

- [ ] **Step 2: Run exact RED on the target Mac**

Run without the Linux-required variable:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_linux_supersession_publish.V064PlatformContractTests
```

Expected: the initial contract test fails until the local-Darwin/public-Linux dispatch is explicitly implemented in the test harness. Do not add a production seam.

- [ ] **Step 3: Add minimal cross-platform harness behavior**

The test module must expose two explicit suites:

```python
class V064StaticAndPortableBoundaryTests(unittest.TestCase): ...
class V064ActualLinuxBoundaryTests(unittest.TestCase): ...
```

On Darwin, the actual-Linux class returns without `unittest.skip` only when `V064_PUBLIC_LINUX_REQUIRED` is absent; it still runs static no-fallback checks. When the environment variable equals `1`, `setUpClass` raises `AssertionError` unless `sys.platform == "linux"`.

- [ ] **Step 4: Add RED/GREEN slices for each required behavior**

For each slice, add one failing test, run that exact test, then add only the minimum test harness/fixture code. Do not change publisher production behavior unless the test reveals a real candidate defect; any such defect requires separate systematic debugging and targeted review.

Required test names:

```text
test_actual_renameat2_noreplace_preserves_existing_sentinel
test_two_fresh_interpreters_yield_one_success_and_one_eexist
test_fresh_process_replays_file_fsync_and_noreplace_crash_boundaries
test_fresh_process_repairs_visible_final_after_directory_fsync_failure
test_symlink_hardlink_fifo_socket_directory_and_wrong_mode_fail_before_io
test_unsupported_symbol_flags_and_errnos_never_fall_back
test_short_write_eintr_and_close_paths_are_deterministic
test_post_fsync_attachment_and_orphan_inventory_block_success
test_every_rejection_preserves_full_sentinel_snapshot
```

Use `subprocess.run([sys.executable, "-c", FIXED_CHILD_PROGRAM, ...])` for fresh interpreters, `multiprocessing.get_context("spawn")` only where a direct Python callable is essential, and finite timeouts. Snapshot exact `(bytes, mode, size, mtime_ns, ctime_ns, dev, ino, nlink)`.

- [ ] **Step 5: Run the complete public-only module on Mac Python 3.9/3.12**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v tests.test_v064_linux_supersession_publish
PYTHONPATH=src /Users/chenm4/Documents/虚拟货币/.venv/bin/python \
  -m unittest -v tests.test_v064_linux_supersession_publish
```

Expected: all static/Darwin-applicable tests PASS; no `skip` appears. Do not set `V064_PUBLIC_LINUX_REQUIRED=1` on Darwin.

- [ ] **Step 6: Static public-safety scan**

Require the public-only test to reject itself if it contains imports outside this set:

```python
ALLOWED_IMPORTS = {
    "ctypes", "errno", "hashlib", "importlib", "json", "multiprocessing",
    "os", "pathlib", "socket", "stat", "subprocess", "sys", "tempfile",
    "time", "unittest"
}
```

Also assert no `/Users/`, email address, HTTP URL, GitHub token pattern, strategy/economic term, production root, Broker, order, or credential access.

- [ ] **Step 7: Commit**

```bash
git add tests/test_v064_linux_supersession_publish.py
git commit -m "test: freeze public Linux publication boundary"
```

---

## Task 4: Implement the Bundle Manifest, Closed-Set Exporter, and Local Replay

**Files:**
- Create: `src/crypto_quant/v064_public_ci_bundle.py`
- Create: `src/crypto_quant/v064_public_ci_bundle_cli.py`
- Create: `public_ci/v064/.github/workflows/ci.yml`
- Create: `public_ci/v064/.gitignore`
- Create: `public_ci/v064/README.md`
- Create: `public_ci/v064/SECURITY.md`
- Create: `public_ci/v064/NOTICE.md`
- Modify: `tests/test_v064_public_ci_bundle.py`

**Interfaces:**
- Consumes: exact private commit `F`, fixed private repository, five templates, publisher blob, public-only test blob.
- Produces:

```python
def build_v064_public_ci_bundle_manifest(repository: Path, source_commit: str) -> dict: ...
def load_v064_public_ci_bundle_manifest(path: Path) -> dict: ...
def stage_v064_public_ci_bundle(repository: Path, source_commit: str, destination: Path) -> dict: ...
def verify_v064_public_ci_bundle(repository: Path, source_commit: str, public_root: Path) -> dict: ...
def build_v064_public_root_commit(repository: Path, source_commit: str, public_root: Path) -> dict: ...
```

The production CLI exposes only parameterless `build-candidate` and `verify-candidate` subcommands using reviewed repository identity and an owner-only fixed candidate root under `/private/tmp`; tests pass explicit capabilities to library functions, not arbitrary production CLI paths.

- [ ] **Step 1: Write manifest/loader RED tests**

Test canonical LF bytes, stable ID/hash derivation, sorted exact files, external manifest exclusion, source commit/tree/baseline/PR identities, original blob OIDs, false safety flags, exact non-claims, and config/package schema mirrors.

Run the exact test and confirm missing functions fail.

- [ ] **Step 2: Implement the minimal manifest builder/loader**

Reuse `canonical_json`, `stable_id`, `business_hash`, and existing strict-loader patterns. Manifest file entries use:

```python
{
    "path": relative_path,
    "size": len(data),
    "sha256": sha256(data).hexdigest(),
    "source_kind": "PRIVATE_GIT_BLOB" | "PRIVATE_TEMPLATE_BLOB" | "GENERATED_MANIFEST",
    "source_blob_oid": oid_or_none,
}
```

`file_set_sha256` hashes entries for the seven non-manifest files; the loader verifies the manifest separately and requires public exact set = manifest entry paths + `bundle-manifest-v1.json`.

- [ ] **Step 3: Write Git-object and mutable-worktree RED tests**

Create a temporary Git fixture where HEAD bytes differ from the worktree. Assert export resolves the OID with `git ls-tree -z` and passes that exact lowercase OID to `git cat-file blob`, never uses `Path.read_bytes()` for source files, and rejects a source commit not equal to reviewed branch HEAD.

- [ ] **Step 4: Implement fixed Git-object reads**

Invoke only `/usr/bin/git` with fixed `-C`, `rev-parse`, `ls-tree -z`, `cat-file blob`, `merge-base --is-ancestor`, `status --porcelain=v1 -z`, and `hash-object` arguments. Set a minimal fixed environment; map every nonzero/ambiguous result to a fixed `V064_PUBLIC_CI_*` reason code.

- [ ] **Step 5: Write sensitive-byte and closed-set RED tests**

Inject one forbidden file or one forbidden byte class at a time: token format, private key marker, email, `/Users/`, non-allowlisted URL, strategy/economic receipt terms, NUL, CRLF, wrong mode, symlink, hardlink, FIFO, socket, extra tracked/untracked file. Assert fixed failure and unchanged external sentinel snapshot.

- [ ] **Step 6: Implement minimal staging and scanning**

Create a new owner-only candidate directory with `O_NOFOLLOW`/lstat/fstat identity checks. Write only newly created files, `fsync` each, read back exact bytes on the same descriptor, then fsync the directory. No overwrite, chmod repair, delete, cleanup of unknown entries, callback, generic sync, or network.

- [ ] **Step 7: Write deterministic root-commit RED tests**

In a temporary bare Git object store, require exact root tree, one parentless commit, GitHub noreply author, fixed message, and fixed timestamp derived from a reviewed constant. Rebuilding the same source must return the same commit OID; any preexisting ref/history fails.

- [ ] **Step 8: Implement Git object construction**

Use `git hash-object -w --stdin`, `git mktree -z`, and `git commit-tree` with fixed author/committer environment. Do not run `git add` over a broad directory and do not include private `.git` metadata. Verify the root commit by `git ls-tree -r -z` and `git cat-file` replay.

- [ ] **Step 9: Write and verify public templates**

Workflow requirements are exact:

```yaml
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
```

Use the two pinned action commit SHAs from Global Constraints. Checkout uses `persist-credentials: false`. An inline shell precheck validates repository/ref, exact file list, then parses manifest with a Python **inline program embedded in the workflow file** and recomputes every non-manifest file size/SHA and `file_set_sha256` before loading any repository Python. The inline verifier is part of the workflow blob and must not import the repository. Do not hardcode manifest SHA into the workflow: manifest already hashes the workflow, so that would create a cycle.

After precheck and `setup-python`, require `getent passwd 501` and `getent group 501` both absent, create fixed UID/GID 501, create owner-501 mode-0700 HOME/TMPDIR/workspace, copy the already verified public tree, recursively chown it, reset workspace mode 0700 and publisher target parent mode 0755, then run exactly:

```text
sudo -u '#501' env \
  HOME=/opt/v064-public-ci-home TMPDIR=/opt/v064-public-ci-home \
  V064_PUBLIC_LINUX_REQUIRED=1 \
  PYTHONPATH=/opt/v064-public-ci-workspace/src:/opt/v064-public-ci-workspace/tests \
  python -m unittest -v tests/test_v064_linux_supersession_publish.py
```

The workflow test locks the commands and order. Do not mock owner identity or install dependencies.

Tests parse the YAML text contract without adding a YAML dependency and assert the absence of forbidden events/permissions/actions.

- [ ] **Step 10: Run Task 4 focused verification**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_bundle \
  tests.test_v064_linux_supersession_publish
python3 -m compileall -q src/crypto_quant/v064_public_ci_bundle.py \
  src/crypto_quant/v064_public_ci_bundle_cli.py \
  tests/test_v064_public_ci_bundle.py \
  tests/test_v064_linux_supersession_publish.py
git diff --check
```

- [ ] **Step 11: Commit**

```bash
git add src/crypto_quant/v064_public_ci_bundle.py \
  src/crypto_quant/v064_public_ci_bundle_cli.py \
  public_ci/v064 tests/test_v064_public_ci_bundle.py
git commit -m "feat: build closed public CI witness bundle"
```

---

## Task 5: Implement Strict GitHub Run Acquisition and Witness Derivation

**Files:**
- Create: `src/crypto_quant/v064_public_ci_witness.py`
- Create: `src/crypto_quant/v064_public_ci_witness_cli.py`
- Modify: `tests/test_v064_public_ci_witness.py`

**Interfaces:**
- Consumes: exact `F`, public repository/commit/tree, manifest, fixed GitHub run ID, exact run/jobs/log outputs.
- Produces:

```python
def derive_v064_public_ci_witness(
    *, bundle: dict, run_bytes: bytes, jobs_bytes: bytes,
    log_bytes: bytes, transcript: dict, private_repository: Path
) -> dict: ...
def load_v064_public_ci_witness(path: Path) -> dict: ...
def verify_v064_public_source_unchanged(
    repository: Path, source_commit_f: str, candidate_commit_g: str, manifest: dict
) -> dict: ...
```

Production CLI takes one decimal `--run-id`, verifies it belongs to the fixed public repository and exact expected public commit, and writes only the five fixed private artifact filenames through a new domain-specific fixed publisher in this module. The publisher uses a retained owner-only directory descriptor, noncanonical nonce staging, same-descriptor write/readback, file fsync, platform-proven atomic no-replace, directory fsync, final replay, and no-overwrite recovery; existing partial/untrusted objects fail closed and are never chmod-fixed or deleted. It accepts no repository, path, status, conclusion, Python version, PASS, filename, callback, or fault-injection override.

- [ ] **Step 1: Write strict run/jobs/log fixture RED tests**

Fixtures cover one exact successful run and mutations: wrong repository, event, branch, public SHA, attempt, workflow path/blob, job count, Python matrix, skipped/cancelled/failure job, empty steps, test step absent, `continue-on-error`, wrong runner OS, duplicate job, rerun after test execution, missing log marker, and inconsistent timestamps.

- [ ] **Step 2: Implement strict JSON/transcript loaders**

Reject BOM, CRLF, duplicate keys, unsafe integers, noncanonical fixed transcripts, unexpected keys, and non-UTF-8 log bytes. Store raw byte SHA/size separately; derive semantic objects only after raw validation.

- [ ] **Step 3: Write RED tests proving PASS cannot be supplied**

Static-scan CLI/parser signatures and patch fixed command outputs. Assert there is no argument or builder field for `status`, `conclusion`, `verified`, Python versions, run timestamps, repository, path, or filenames. `LINUX_PYTHON_3_9_VERIFIED` and `LINUX_PYTHON_3_12_VERIFIED` must arise only from exact job/step/log replay.

- [ ] **Step 4: Implement fixed acquisition CLI**

Run only these command families with a minimal environment:

```text
/opt/homebrew/bin/gh api repos/cjl308868584-lang/crypto-quant-v064-public-ci/actions/runs/31400000000
/opt/homebrew/bin/gh api 'repos/cjl308868584-lang/crypto-quant-v064-public-ci/actions/runs/31400000000/jobs?filter=all&per_page=100'
/opt/homebrew/bin/gh run view 31400000000 --repo cjl308868584-lang/crypto-quant-v064-public-ci --log
```

`31400000000` is a test-fixture decimal value in this code block. In production the CLI validates the sole user-supplied decimal `--run-id`, renders it into the same three fixed argv positions, and rejects every other argument.

Resolve actual `gh` path once during design implementation and freeze it for the target Mac; if the reviewed absolute path differs, update the plan/spec before artifact acquisition. Capture stdout/stderr exact bytes, exit code, byte count, and SHA-256. Never print environment or tokens.

- [ ] **Step 5: Write/implement `F`→`G` unchanged-source proof**

RED mutations change each public source/template/test blob between `F` and `G`, use a non-descendant `G`, or change schemas/loaders. GREEN requires `merge-base --is-ancestor F G`, exact public-source blob OIDs unchanged, and only the formal witness regression/artifact/build-manifest delta permitted after `F`.

- [ ] **Step 6: Write formal-artifact lifecycle tests**

Before the real five artifacts exist, exactly three fixed committed-artifact regression methods may skip with:

```text
FIXED_PUBLIC_CI_WITNESS_ARTIFACT_NOT_YET_PUBLISHED
```

All schema, builder, failure, CLI, and fixture tests must run. After artifacts exist, the exact three regressions must not skip.

Add publisher crash/race RED tests before implementation: partial write, file-fsync failure, no-replace boundary, visible-final/directory-fsync failure, exact retry, symlink/hardlink/FIFO/socket/wrong-mode final, competing publishers, staging orphan, fd close failure, and external sentinel full snapshot. Reuse the proven OS primitive implementation internally only after proving its source blob/behavior; do not call the existing four-artifact public API with a new filename and do not expose a generic storage interface.

- [ ] **Step 7: Run focused GREEN**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v tests.test_v064_public_ci_witness
python3 -m compileall -q src/crypto_quant/v064_public_ci_witness.py \
  src/crypto_quant/v064_public_ci_witness_cli.py \
  tests/test_v064_public_ci_witness.py
git diff --check
```

- [ ] **Step 8: Commit**

```bash
git add src/crypto_quant/v064_public_ci_witness.py \
  src/crypto_quant/v064_public_ci_witness_cli.py \
  tests/test_v064_public_ci_witness.py
git commit -m "feat: derive strict public Linux CI witness"
```

---

## Task 6: Freeze Private Candidate `F` and Prepare the Irreversible Approval Package

**Files:**
- Modify: `config/evaluator-build-manifest-v1.json`
- Test: all files from Tasks 1–5
- Generated locally only: owner-only candidate public Git object store/tree/commit

**Interfaces:**
- Consumes: final private code/templates/tests and exact private branch HEAD.
- Produces: reviewed private source commit `F`, deterministic public candidate commit/tree, and an approval package; no external writes.

- [ ] **Step 1: Update build manifest once**

Run the existing manifest builder only after all code settles. Require exact expected file set/hash/tree/self-hash. Do not change package version (`0.63.0`) or release metadata yet.

- [ ] **Step 2: Run focused and adjacent tests**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_v064_public_ci_bundle \
  tests.test_v064_linux_supersession_publish \
  tests.test_v064_public_ci_witness \
  tests.test_challenger_replacement_plan_v2 \
  tests.test_challenger_replacement_plan_supersession
python3 -m compileall -q src tests
git diff --check
```

- [ ] **Step 3: Run exactly one full local suite for final `F` code**

```bash
make validate
make test
```

Do not repeat the full suite on unchanged code.

- [ ] **Step 4: Request independent complete review**

Reviewer must inspect closed public set, sensitive scan, source Git-object binding, manifest self-reference avoidance, deterministic commit, workflow token/events/action SHAs, public-only Linux semantics, API/log derivation, `F`/`G` ancestry, and all non-claims. Critical/Important must be zero. Fixes use `receiving-code-review`, focused RED/GREEN, and targeted re-review; rerun full suite only if final code state changed after the previous full run.

- [ ] **Step 5: Commit reviewed `F`**

```bash
git add config/evaluator-build-manifest-v1.json
git commit -m "feat: prepare bounded public Linux CI witness"
```

Record `F=$(git rev-parse HEAD)`, its tree, parent, diff from `1809bd5...`, test evidence, and review result.

- [ ] **Step 6: Build and replay the local public candidate**

Use the fixed CLI against exact `F`. Verify:

- exact eight-file set;
- every mode/size/SHA/source blob OID;
- manifest and file-set hashes;
- sensitive scan zero findings;
- one parentless deterministic commit with noreply author;
- repeated build returns the same commit/tree;
- public root contains no private `.git` history, extra refs, artifacts, docs, email, home path, receipt, strategy, or credential material.

- [ ] **Step 7: Prepare the targeted approval package and stop**

Show the user:

```text
private repository/branch/F/tree
public repository exact name and visibility=PUBLIC
exact eight paths with size and SHA-256
bundle manifest SHA-256 and file-set SHA-256
candidate public root commit/tree and fixed author identity
workflow events/permissions/action SHAs
sensitive scan result
local tests/review result
irreversible visibility/fork/log consequences
```

Request one explicit approval covering only: create the named public repository, push the exact root commit to `main`, allow the owner-push workflow to run, and read/seal its result. It does not cover private merge/tag, public tag/archive, owner attestation, installation, or trading.

---

## Task 7: Create and Run the Exact Public Witness Repository

**Files:**
- External create: `cjl308868584-lang/crypto-quant-v064-public-ci` (public)
- External push: exact reviewed root commit to `refs/heads/main`
- No private worktree changes during creation/run.

**Interfaces:**
- Consumes: user-approved exact public commit/tree from Task 6.
- Produces: one GitHub Actions run on that commit with real Python 3.9/3.12 Linux jobs.

- [ ] **Step 1: Revalidate authority immediately before external write**

Require active authenticated account `cjl308868584-lang`, ADMIN on private source, exact private `F`, private source still private, target public repository absent, and candidate repository clean/replayable. If the target exists or any identity differs, stop.

- [ ] **Step 2: Create the exact public repository**

Use GitHub API/CLI with `--public`, no README/license/gitignore initialization, issues disabled when supported, wiki/projects disabled, and default branch `main`. Confirm it is empty before push. Do not create from the private repository UI and do not use a template/fork.

- [ ] **Step 3: Push only the approved root commit**

Set `V064_PUBLIC_COMMIT` to the exact approved lowercase Git OID printed in Task 6, require `git rev-parse "$V064_PUBLIC_COMMIT"` equals it, then push exactly `"$V064_PUBLIC_COMMIT:refs/heads/main"`. Immediately verify remote `main`, root tree, parent count zero, exact eight paths/blobs, visibility public, permissions, workflow file blob, and no extra refs/tags/branches.

- [ ] **Step 4: Observe the owner-push workflow once**

Do not manually dispatch if the push event created the run. Require exact public commit and workflow. Wait for both jobs; do not cancel or rerun for a test failure.

- [ ] **Step 5: Apply the rerun rule if and only if eligible**

If GitHub infrastructure fails before any test step and annotations/logs prove no test executed, rerun the same exact public commit once. Otherwise retain actual FAIL/CANCEL and stop v0.64.

- [ ] **Step 6: Report actual result without interpretation inflation**

Report run/job IDs and conclusions. Even on success, state only `PUBLIC_LINUX_PORTABILITY_WITNESS_COMPLETED`; do not claim private PR CI success, full suite success, profitability, or release readiness.

---

## Task 8: Seal the Public Run and Create Successor Private Candidate `G`

**Files:**
- Create: five files under `artifacts/v064-public-ci/` listed in File Map.
- Modify: `tests/test_v064_public_ci_witness.py`
- Modify: `config/evaluator-build-manifest-v1.json`

**Interfaces:**
- Consumes: first eligible successful public run, exact `F`, public commit/tree/manifest.
- Produces: strict private witness and successor private commit `G` that reopens existing v0.64 Task 5.

- [ ] **Step 1: Acquire through the fixed CLI**

Use only the public run ID. The CLI must first fetch/validate into an owner-only staging directory, derive the witness, replay every raw input, and no-overwrite publish the five fixed files. Any 404, API shape change, expired log, multiple matching jobs, non-success conclusion, or identity mismatch stops without partial canonical files.

- [ ] **Step 2: Run production loaders and exact-byte replay**

Verify all five owner/mode/nlink/type/path identities, raw byte hashes/sizes, canonical transcript, witness ID/hash/schema, exact job versions, test step markers, public commit/tree, manifest, workflow blob, private `F`, and false safety flags.

- [ ] **Step 3: Turn the exact three regression skips into real checks**

Only modify the precommitted regression section to load the fixed artifacts and compare exact bytes/hashes. Run the three exact tests and assert skip count zero.

- [ ] **Step 4: Verify `F`→candidate `G` unchanged-source boundary**

Before commit, use the index candidate tree to prove all publisher/test/template/builder/loader blobs from `F` remain unchanged except the exact permitted witness regression/build-manifest edits and five artifacts. No production code change is allowed after public CI; if code must change, discard the run as not applicable, return to Task 6, and create a new `F`/public commit/run.

- [ ] **Step 5: Update build manifest and run final post-run gate**

Run focused witness/bundle/Linux/supersession tests, compileall, diff-check, manifest replay, and the exact committed-artifact regressions with zero skips. Do not rerun the full suite if production code is unchanged from reviewed `F`; the focused post-run gate covers the new immutable data/regression only.

- [ ] **Step 6: Independent targeted review of exact evidence diff**

Reviewer verifies raw API/log bytes, derived conclusions, IDs/hashes, `F` ancestry, unchanged public source blobs, exact five-file publication, no credentials, and no human-supplied PASS. Critical/Important must be zero.

- [ ] **Step 7: Commit exact `G`**

```bash
git add artifacts/v064-public-ci \
  tests/test_v064_public_ci_witness.py \
  config/evaluator-build-manifest-v1.json
git commit -m "evidence: bind public Linux CI witness"
```

Record `G`, tree, parent=`F` or an explicitly reviewed evidence-only descendant chain, and unchanged-source verifier result.

- [ ] **Step 8: Stop before private remote integration**

Prepare a private push/Draft-PR replacement approval package. Do not push, close PR #32, merge, tag, archive public repository, create a public annotated tag, or resume Task 5 without the corresponding explicit approval.

---

## Task 9: Integrate `G` and Resume the Existing v0.64 Ceremony

**Files:**
- Existing private branch/PR only after user approval.
- Existing Task 5–8 files from `docs/superpowers/plans/2026-08-09-replacement-challenger-plan-v2-supersession.md`.

**Interfaces:**
- Consumes: approved/reviewed `G`, successful public witness, unchanged-source proof.
- Produces: an updated private Draft PR and permission to resume the already written v0.64 Task 5; this plan does not duplicate or weaken that ceremony.

- [ ] **Step 1: Push `G` and create a replacement private Draft PR only after approval**

Verify private repo/origin/main/tag/ADMIN identity, push the exact branch, create Draft PR, preserve PR #32 and run `31436609135` as billing-blocked history, and close #32 only after the replacement PR exists with an explanatory link.

- [ ] **Step 2: Record the absence of private hosted CI honestly**

The replacement private PR may still show billing-blocked hosted jobs. Its body must link the exact public repository/commit/run and private witness while stating that the public run is an independent bound witness, not a private PR check.

- [ ] **Step 3: Resume original Task 5 from exact `G`**

Re-run the pre-artifact Mac/Schema/design gates and strict public witness loader. Only then generate the formal v2 plan artifact. Continue all original C0–C4, owner-attestation, record, release, merge, and annotated-tag requirements unchanged.

- [ ] **Step 4: Preserve later permission gates**

When the owner ceremony displays a new exact `signed_at`, declaration hash, binding hash, plan/evidence identities, stop and request a fresh owner approval; never reuse earlier approval. Private merge/tag and public tag/archive each remain separate explicit actions.

---

## Final Verification Checklist

- [ ] Private `crypto-quant-core` remains private and authoritative.
- [ ] Public mirror contains exactly eight approved paths and one root history before any optional annotated tag.
- [ ] Public publisher/test bytes equal private `F` blobs.
- [ ] Manifest has no public commit/tree or `G` self-reference.
- [ ] Public workflow permissions/events/action SHAs are exact and no credentials persist after checkout.
- [ ] Python 3.9/3.12 actual Linux jobs both ran the real primitive with zero skip/mock/fallback.
- [ ] Raw run/jobs/log/transcript bytes are sealed and replayable.
- [ ] Witness conclusions are derived, never supplied.
- [ ] A post-commit verifier proves `G` is a strict descendant of `F`, with all public source blobs unchanged; witness bytes themselves contain no self-referential `G` OID.
- [ ] Failed private run `31436609135` remains visible as billing-blocked evidence.
- [ ] No Task 5 artifact, owner attestation, private merge/tag, installation, or trading action occurred early.
- [ ] Critical/Important review findings are zero.
- [ ] No profitability, AI-advantage, Paper-completion, Canary, or live-trading claim was made.
