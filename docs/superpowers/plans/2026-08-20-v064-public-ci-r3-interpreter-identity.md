# v0.64 Public CI R3 Interpreter Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the R2 semantic failure as replayable evidence and build a local R3 public-CI candidate whose Python 3.9/3.12 jobs carry the exact `setup-python` interpreter across the UID 501 boundary without relying on `PATH`.

**Architecture:** Add one private, immutable R2 failure-evidence contract that derives the interpreter mismatch from exact captured Run, Jobs, and log bytes. Upgrade the existing closed bundle/witness contracts to R3 with ordered R1/R2 failure ancestry, then change only the public workflow's interpreter handoff while preserving the publisher and Linux-test blobs. Build and replay one parentless eight-file local candidate; stop with an exact approval package before any R3 repository, push, or Actions operation.

**Tech Stack:** Python 3.9-compatible standard library, `jsonschema` Draft 2020-12, canonical JSON, Git object plumbing, Bash/GitHub Actions, `unittest`, pinned `gh` 2.96.0 for the later separately approved acquisition.

**Spec:** `docs/superpowers/specs/2026-08-20-v064-public-ci-r3-interpreter-identity-design.md`

## Global Constraints

- The design is frozen at commit `f947d2b`; its file SHA-256 is `69dff502803a2ea2c50b66ee246dba5566674029aa22022c1907b10ad693ff2b`.
- Private baseline `F2` is `5bc01c9b9b9d9a21846dd8c6ba1d81b0183dd219`; private `F3` must be its strict descendant.
- R1 and R2 repositories, commits, trees, runs, jobs, refs, tags, releases, and captured raw evidence are immutable failures.
- Never rerun or add a commit/ref to `cjl308868584-lang/crypto-quant-v064-public-ci-r2`.
- R3 public repository identity is exactly `cjl308868584-lang/crypto-quant-v064-public-ci-r3` and its local candidate root is exactly `/private/tmp/crypto-quant-v064-public-ci-r3-candidate`.
- `src/crypto_quant/challenger_replacement_supersession_publish.py` must retain blob `8a67fffdfd17bdf26cc74ee23e14a7c8fe91b7a8`.
- `tests/test_v064_linux_supersession_publish.py` must retain blob `4fc14ffd73ce09803afb6cda724b51c919f1d8ba`.
- The R3 public tree is exactly eight files in one parentless root commit; no ninth file, parent, tag, release, or branch is permitted.
- Keep Python 3.9 syntax compatibility and add no runtime dependency.
- Keep every production/trading safety flag false. Do not add or execute scheduler, deployment, Runner, Broker, order, credential, market request, production root, strategy-state, owner-attestation, or funds behavior.
- Every behavior change uses exact RED, minimal GREEN, focused verification, and its own commit.
- Run the complete local suite exactly once on the final unchanged `F3` code state; do not repeat it mechanically.
- This plan authorizes local files, tests, commits, review, and candidate construction only. New public repository creation, push, Actions execution, and result acquisition require one later exact user approval.

## File Map

- `src/crypto_quant/v064_public_ci_r2_failure.py`: derive and load the immutable R2 semantic-failure record from fixed raw bytes.
- `config/v064-public-ci-r2-failure-record-v1.schema.json` and package mirror: closed failure-record schema.
- `artifacts/v064-public-ci-r2-failure/*`: three exact captured readbacks plus one derived canonical record.
- `src/crypto_quant/v064_public_ci_bundle.py`: R3 eight-file manifest, ordered predecessor failures, and deterministic parentless candidate builder.
- `src/crypto_quant/v064_public_ci_bundle_cli.py`: fixed R3 candidate root; no caller-selected path or repository.
- `public_ci/v064/.github/workflows/ci.yml`: absolute setup-python binary capture and fixed `$1` UID 501 handoff.
- `src/crypto_quant/v064_public_ci_witness.py`: R3 witness derivation with R1/R2 ancestry and interpreter identity checks.
- `src/crypto_quant/v064_public_ci_witness_cli.py`: fixed R3 repository/run acquisition and owner-only no-overwrite publication.
- `config/v064-public-ci-{bundle-manifest,witness}-v1.schema.json` and package mirrors: closed Schema version `1.2.0`.
- `public_ci/v064/{README.md,NOTICE.md}`: R3 purpose and immutable failure ancestry, without business or profitability claims.
- `tests/test_v064_public_ci_r2_failure.py`: raw-evidence derivation, mutation, loader, and no-overwrite tests.
- `tests/test_v064_public_ci_bundle.py`: R3 manifest/workflow/candidate regression tests.
- `tests/test_v064_public_ci_witness.py`: R3 witness/acquisition regression tests.
- `config/evaluator-build-manifest-v1.json`: mechanical final file-set/tree/self-hash refresh only.

---

### Task 1: Freeze and Derive the R2 Semantic-Failure Record

**Files:**
- Create: `src/crypto_quant/v064_public_ci_r2_failure.py`
- Create: `config/v064-public-ci-r2-failure-record-v1.schema.json`
- Create: `src/crypto_quant/schemas/v064-public-ci-r2-failure-record-v1.schema.json`
- Create: `tests/test_v064_public_ci_r2_failure.py`
- Create mechanically after RED/GREEN: `artifacts/v064-public-ci-r2-failure/v064-public-ci-r2-run-api-v1.json`
- Create mechanically after RED/GREEN: `artifacts/v064-public-ci-r2-failure/v064-public-ci-r2-jobs-api-v1.json`
- Create mechanically after RED/GREEN: `artifacts/v064-public-ci-r2-failure/v064-public-ci-r2-run-log-v1.txt`
- Create mechanically after RED/GREEN: `artifacts/v064-public-ci-r2-failure/v064-public-ci-r2-failure-record-v1.json`

**Interfaces:**
- Consumes: exact raw files `/private/tmp/v064-r2-failure-32328770160-{run-api.json,jobs-api.json}` and `/private/tmp/v064-r2-run-32328770160.log` with the size/SHA values frozen in design section 1.2.
- Produces: `derive_v064_public_ci_r2_failure(*, run_bytes: bytes, jobs_bytes: bytes, log_bytes: bytes) -> Dict[str, Any]`.
- Produces: `load_v064_public_ci_r2_failure(path: Path) -> Dict[str, Any]` and `load_v064_public_ci_r2_failure_root(root: Path) -> Dict[str, Any]`.
- The derived object has fixed `status="PUBLIC_LINUX_PORTABILITY_WITNESS_DID_NOT_PASS"` and `reason_code="PUBLIC_MATRIX_INTERPRETER_IDENTITY_MISMATCH"`; callers cannot supply either.

- [ ] **Step 1: Write exact raw-boundary RED tests**

Create tests that read the three `/private/tmp` sources only as test fixtures, assert exact sizes and SHA-256 values, and pass their bytes to the missing derivation function. Require the result to bind R2 repository/commit/tree/workflow/manifest/file-set/run/attempt/job identities and to derive:

```python
{
    "expected_python_versions": ["3.9", "3.12"],
    "observed_fixed_owner_versions": ["3.12.3", "3.12.3"],
    "status": "PUBLIC_LINUX_PORTABILITY_WITNESS_DID_NOT_PASS",
    "reason_code": "PUBLIC_MATRIX_INTERPRETER_IDENTITY_MISMATCH",
    "github_conclusion": "success",
    "success_witness_published": False,
}
```

Require `run_bytes` and `jobs_bytes` to be exact canonical JSON plus LF. Mutate each repository/commit/run/job/version/conclusion/log marker and require a fixed `V064PublicCiR2FailureError` reason. Verify the API exposes no status, reason, expected-version, observed-version, path, or repository input.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v tests.test_v064_public_ci_r2_failure
```

Expected: import failure because `v064_public_ci_r2_failure` does not exist.

- [ ] **Step 3: Implement the minimal closed Schema and derivation**

Implement a parameterless identity constant and strict JSON/log parsing. The record must include exact raw path, byte count, and SHA-256 objects, a closed ordered two-job observation, false safety flags, and `readback_provenance="POST_RUN_READ_ONLY_READBACK"`. Recompute all hashes in the loader; validate config/package Schema mirrors byte-for-byte. Do not accept a precomputed conclusion or parse arbitrary files.

- [ ] **Step 4: Run GREEN and mutation tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v tests.test_v064_public_ci_r2_failure
cmp config/v064-public-ci-r2-failure-record-v1.schema.json \
  src/crypto_quant/schemas/v064-public-ci-r2-failure-record-v1.schema.json
git diff --check
```

Expected: all pass; no formal artifact has yet been written.

- [ ] **Step 5: Publish the four local artifacts without reacquisition**

Add a test-only ceremony that first verifies all three source file identities, copies exact bytes to new fixed final names with `O_CREAT|O_EXCL|O_NOFOLLOW`, mode `0600`, full-write/readback/file-fsync/directory-fsync, and then publishes canonical derived record bytes. A pre-existing final must be exact/trusted or fail closed; it must never be overwritten, chmod-repaired, or silently adopted when bytes differ. Run the production loader on the fixed root and compare all three raw files byte-for-byte with `/private/tmp`.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/crypto_quant/v064_public_ci_r2_failure.py \
  config/v064-public-ci-r2-failure-record-v1.schema.json \
  src/crypto_quant/schemas/v064-public-ci-r2-failure-record-v1.schema.json \
  tests/test_v064_public_ci_r2_failure.py \
  artifacts/v064-public-ci-r2-failure
git commit -m "feat: preserve v0.64 public CI R2 semantic failure"
```

---

### Task 2: Upgrade the Closed Bundle Contract to R3

**Files:**
- Modify: `config/v064-public-ci-bundle-manifest-v1.schema.json`
- Modify: `src/crypto_quant/schemas/v064-public-ci-bundle-manifest-v1.schema.json`
- Modify: `src/crypto_quant/v064_public_ci_bundle.py`
- Modify: `src/crypto_quant/v064_public_ci_bundle_cli.py`
- Modify: `tests/test_v064_public_ci_bundle.py`
- Modify: `public_ci/v064/README.md`
- Modify: `public_ci/v064/NOTICE.md`

**Interfaces:**
- Consumes: Task 1 failure record and the exact R1 predecessor object already frozen in R2.
- Produces: Schema `1.2.0`, ordered `predecessor_failed_public_witnesses=[R1, R2]`, repository `cjl308868584-lang/crypto-quant-v064-public-ci-r3`, and fixed candidate root `/private/tmp/crypto-quant-v064-public-ci-r3-candidate`.

- [ ] **Step 1: Add Schema and builder RED tests**

Require exactly two predecessor objects in order. The R1 object must remain byte/object equal to the R2 baseline. The R2 object must bind Task 1 record identity and all design section 1.2 fields. Reject missing, extra, reordered, duplicated, or mutated predecessors; version other than `1.2.0`; old R2 repository/path; unsafe integer; wrong-length OID/hash; and any extra object property.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_bundle.V064PublicCiSchemaTests \
  tests.test_v064_public_ci_bundle.V064PublicCiBundleManifestTests \
  tests.test_v064_public_ci_bundle.V064PublicCiBundleCliTests
```

Expected: fail on version/repository/path and the old singular predecessor field.

- [ ] **Step 3: Implement the minimal R3 contract**

Replace the singular predecessor field with a fixed two-element array. Keep each nested object closed. Bind R2 failure-record path/SHA and semantic result, but do not copy raw log bodies into the public manifest. Update README/NOTICE only with R3 engineering purpose and immutable R1/R2 failure statements. Keep exactly eight public files.

- [ ] **Step 4: Prove preserved public source blobs and GREEN**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_bundle.V064PublicCiSchemaTests \
  tests.test_v064_public_ci_bundle.V064PublicCiBundleManifestTests \
  tests.test_v064_public_ci_bundle.V064PublicCiBundleCliTests
test "$(git hash-object src/crypto_quant/challenger_replacement_supersession_publish.py)" = \
  8a67fffdfd17bdf26cc74ee23e14a7c8fe91b7a8
test "$(git hash-object tests/test_v064_linux_supersession_publish.py)" = \
  4fc14ffd73ce09803afb6cda724b51c919f1d8ba
cmp config/v064-public-ci-bundle-manifest-v1.schema.json \
  src/crypto_quant/schemas/v064-public-ci-bundle-manifest-v1.schema.json
git diff --check
```

- [ ] **Step 5: Commit Task 2**

```bash
git add config/v064-public-ci-bundle-manifest-v1.schema.json \
  src/crypto_quant/schemas/v064-public-ci-bundle-manifest-v1.schema.json \
  src/crypto_quant/v064_public_ci_bundle.py \
  src/crypto_quant/v064_public_ci_bundle_cli.py \
  tests/test_v064_public_ci_bundle.py \
  public_ci/v064/README.md public_ci/v064/NOTICE.md
git commit -m "feat: bind v0.64 public CI R3 ancestry"
```

---

### Task 3: Carry the Exact Matrix Interpreter Across UID 501

**Files:**
- Modify: `public_ci/v064/.github/workflows/ci.yml`
- Modify: `tests/test_v064_public_ci_bundle.py`

**Interfaces:**
- Consumes: the `python` placed first on runner `PATH` by pinned `actions/setup-python`.
- Produces: a fixed-owner shell invocation whose positional `$1` is the absolute setup-python binary and whose interpreter use is exclusively `"$1"`.

- [ ] **Step 1: Add the historical R2 reproduction and R3 RED**

Extract the exact R2 fixed-owner block from commit `5bc01c9`. Run it in a controlled shell fixture with a fake setup-python binary first on `PATH` and a different fake system `python`; prove the R2 child resolves the system binary. Then require the current workflow to capture one absolute `python_bin`, compare its `major.minor` with the matrix value, omit `PATH` from sudo environment, pass the binary as fixed `$1`, and use no bare `python` in the child.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_bundle.V064PublicCiWorkflowContractTests
```

Expected: the historical reproduction passes and the R3 contract fails on the R2 child shell.

- [ ] **Step 3: Implement the bounded workflow fix**

Use this semantic form, retaining the existing UID/GID/HOME/workspace setup and exact test selector:

```bash
python_bin="$(command -v python)"
test -n "$python_bin"
case "$python_bin" in /*) ;; *) exit 1 ;; esac
test -x "$python_bin"
test "$("$python_bin" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = "${{ matrix.python-version }}"
sudo -u '#501' env HOME=/opt/cryptoquant-ci-home TMPDIR=/opt/cryptoquant-ci-home \
  V064_PUBLIC_LINUX_REQUIRED=1 PYTHONPATH=/opt/cryptoquant-ci-workspace/src:/opt/cryptoquant-ci-workspace/tests \
  /bin/bash -c 'set -euo pipefail; /usr/bin/uname -sr; /usr/bin/ldd --version | /usr/bin/head -1; "$1" --version; cd /opt/cryptoquant-ci-workspace; exec "$1" -m unittest -v tests/test_v064_linux_supersession_publish.py' \
  v064-fixed-owner "$python_bin"
```

Do not pass `PATH`, invoke `/usr/bin/env python`, copy the interpreter, build a venv, or change the exported Linux test.

- [ ] **Step 4: Add executable fixture GREEN tests**

Use temporary executable scripts as fake interpreters. Prove: a missing child `PATH` still invokes the fixed binary; a poisoned child `PATH` cannot redirect it; relative and non-executable candidates fail; reported `3.12` in a `3.9` matrix fails before sudo; fixed 3.9 and 3.12 identities each reach their exact fake binary once. Tests must execute the extracted shell logic rather than only search text.

- [ ] **Step 5: Run GREEN and blob immutability gate**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_bundle.V064PublicCiWorkflowContractTests
test "$(git hash-object src/crypto_quant/challenger_replacement_supersession_publish.py)" = \
  8a67fffdfd17bdf26cc74ee23e14a7c8fe91b7a8
test "$(git hash-object tests/test_v064_linux_supersession_publish.py)" = \
  4fc14ffd73ce09803afb6cda724b51c919f1d8ba
git diff --check
```

- [ ] **Step 6: Commit Task 3**

```bash
git add public_ci/v064/.github/workflows/ci.yml tests/test_v064_public_ci_bundle.py
git commit -m "fix: pin v0.64 public CI matrix interpreter"
```

---

### Task 4: Upgrade R3 Witness Derivation and Fixed Acquisition

**Files:**
- Modify: `config/v064-public-ci-witness-v1.schema.json`
- Modify: `src/crypto_quant/schemas/v064-public-ci-witness-v1.schema.json`
- Modify: `src/crypto_quant/v064_public_ci_witness.py`
- Modify: `src/crypto_quant/v064_public_ci_witness_cli.py`
- Modify: `tests/test_v064_public_ci_witness.py`

**Interfaces:**
- Consumes: Task 2 manifest, future exact R3 Run/Jobs/log/acquisition transcript bytes, and fixed run ID only.
- Produces: Schema `1.2.0`; `derive_v064_public_ci_witness(...)`; fixed output root `artifacts/v064-public-ci-r3`; fixed three `gh` read commands plus local transcript; no caller-selected status/version/repository/path.

- [ ] **Step 1: Add R3 witness RED tests**

Require ordered R1/R2 ancestry exact equality with the bundle. Require the two successful job logs to contain their distinct expected setup-python and fixed-owner interpreter identities. Mutate one fixed-owner identity so both show 3.12 and require `V064_PUBLIC_CI_LOG_INVALID`. Reject old repository, R2 root, singular predecessor, reordered predecessors, a caller-provided success flag, any extra property, and raw noncanonical API JSON.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_witness.V064PublicCiWitnessSchemaTests \
  tests.test_v064_public_ci_witness.V064PublicCiWitnessDerivationTests \
  tests.test_v064_public_ci_witness.V064PublicCiWitnessCliTests
```

Expected: fail on old version/repository/root and singular predecessor.

- [ ] **Step 3: Implement minimal Schema/loader changes**

Upgrade to `1.2.0`, bind R3 identities, and carry the exact two-element predecessor array from the loaded bundle. Parse each job's expected matrix version and the fixed-owner `Python X.Y.Z` line; require `3.9.x` for job 3.9 and `3.12.x` for job 3.12. Keep all status/conclusion/timestamp/job values derived from raw bytes.

- [ ] **Step 4: Update the fixed CLI without executing it**

Set repository and owner-only output root to R3. Keep `run_id` as the only acquisition selector. Require exactly one Run API, one Jobs API, and one log command with fixed repository; bound time and bytes; save exact stdout/stderr/argv/exit code; refuse overwrite, staging ambiguity, noncanonical JSON, mixed run identity, or an ineligible workflow result. Do not call `gh` during local tests.

- [ ] **Step 5: Run GREEN and closed-boundary tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_witness.V064PublicCiWitnessSchemaTests \
  tests.test_v064_public_ci_witness.V064PublicCiWitnessDerivationTests \
  tests.test_v064_public_ci_witness.V064PublicCiWitnessCliTests
cmp config/v064-public-ci-witness-v1.schema.json \
  src/crypto_quant/schemas/v064-public-ci-witness-v1.schema.json
git diff --check
```

- [ ] **Step 6: Commit Task 4**

```bash
git add config/v064-public-ci-witness-v1.schema.json \
  src/crypto_quant/schemas/v064-public-ci-witness-v1.schema.json \
  src/crypto_quant/v064_public_ci_witness.py \
  src/crypto_quant/v064_public_ci_witness_cli.py \
  tests/test_v064_public_ci_witness.py
git commit -m "feat: derive v0.64 public CI R3 witness"
```

---

### Task 5: Freeze and Replay the Local R3 Eight-File Candidate

**Files:**
- Modify mechanically: `config/evaluator-build-manifest-v1.json`
- Modify: `tests/test_v064_public_ci_bundle.py`
- Candidate only, never tracked in private tree: `/private/tmp/crypto-quant-v064-public-ci-r3-candidate`

**Interfaces:**
- Consumes: Tasks 1–4 and the exact final private commit `F3`.
- Produces: deterministic eight-file public manifest, parentless root commit/tree, per-file SHA/blob identities, and local replay report.

- [ ] **Step 1: Add final RED invariants before refreshing the manifest**

Require `F2` to be a strict ancestor of current HEAD; R1/R2 failure artifacts and exact repository identities to remain present; R2 formal success root to remain absent; the two immutable source blobs to match their fixed OIDs; public inventory to equal exactly the eight allowlisted paths; and local candidate rebuild to produce the same commit/tree twice without retaining an extra ref or parent.

- [ ] **Step 2: Run focused RED**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_r2_failure \
  tests.test_v064_public_ci_bundle \
  tests.test_v064_public_ci_witness
```

Expected: only build-manifest/file-set identity tests fail because the manifest has not been refreshed.

- [ ] **Step 3: Refresh the build manifest mechanically**

Use the repository's existing build-manifest generator/validator. Require the file set to be exact, every SHA to recompute, tree hash and self-hash to match, and package/schema/metric versions to remain unchanged unless the existing manifest contract itself requires a mechanical file-set increment. Do not hand-edit individual hashes.

- [ ] **Step 4: Commit final private code state `F3`**

```bash
git add config/evaluator-build-manifest-v1.json tests/test_v064_public_ci_bundle.py
git commit -m "build: freeze v0.64 public CI R3 candidate"
```

Record exact `F3` commit/tree and verify `git merge-base --is-ancestor 5bc01c9b9b9d9a21846dd8c6ba1d81b0183dd219 HEAD`.

- [ ] **Step 5: Build the candidate at the fixed root**

Run the fixed bundle CLI only after confirming the target root is absent. Verify with the production bundle loader and Git plumbing that the candidate is one parentless root commit with exactly eight files, no tags/releases/additional refs, exact manifest/file-set hashes, and the fixed publisher/Linux-test blob OIDs. Rebuild in a second fresh `/private/tmp` verification root using the library API and require identical commit/tree and bytes; do not push either root.

- [ ] **Step 6: Run embedded preflight and sensitive-payload negatives**

Execute the exact workflow preflight against the candidate. Reseal each private-only mutation independently (private-key marker, token, `/Users/`, email, nonallowlisted URL, Broker/order/credential marker), then require the fixed public error and empty success output. Restore and replay the exact candidate after each mutation.

- [ ] **Step 7: Keep candidate identity outside the tracked private tree**

Do not create a ninth public file or a new private candidate-identity artifact. The public manifest already records all eight identities; leave the built candidate solely under `/private/tmp` and recompute its hashes directly for the final approval package.

---

### Task 6: Final Verification, Independent Review, and One Approval Package

**Files:**
- Modify only when verification finds a real defect: files owned by Tasks 1–5.
- Do not create or modify any external repository.

**Interfaces:**
- Consumes: unchanged final `F3` and the local R3 candidate.
- Produces: one evidence-backed approval package for the four external operations: create public R3 repository, push exact root, allow one owner-push Actions run, read back exact result.

- [ ] **Step 1: Run focused and adjacent tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_r2_failure \
  tests.test_v064_public_ci_bundle \
  tests.test_v064_public_ci_witness \
  tests.test_challenger_replacement_plan_supersession \
  tests.test_challenger_replacement_plan_v2
```

Expected: all pass, no unexpected skips in R3 contract tests.

- [ ] **Step 2: Run static and build validation**

```bash
/usr/bin/python3 -m compileall -q src tests
git diff --check
make validate-build
```

Expected: all exit zero; substitute only the repository's exact existing build-validation target if `make help` shows a differently named target.

- [ ] **Step 3: Run the complete local suite once**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests
```

Expected: all tests pass. Do not run the complete suite again unless code changes afterward.

- [ ] **Step 4: Request one independent complete review**

Give the reviewer the design, plan, `F2..F3` diff, R2 raw/failure artifacts, immutable blob gates, candidate commit/tree/eight-file inventory, and all verification outputs. Require Critical=0 and Important=0. If findings require code changes, add an exact RED, fix minimally, run focused/adjacent tests and only the affected final gates, then request a targeted re-review; rerun the full suite only because the code state changed.

- [ ] **Step 5: Verify final clean identity**

Require clean worktree, `F2` strict ancestry, exact build-manifest replay, no R3 evidence-success root, no R3 GitHub repository created by this plan, and no changes to R1/R2 remotes. Capture exact `F3` commit/tree, eight file sizes/SHA-256/blob OIDs, deterministic public root commit/tree, workflow blob, test counts, and review verdict.

- [ ] **Step 6: Present one consolidated external approval package and stop**

The package must name the exact new public repository, visibility, parentless commit/tree, eight file hashes, one-push rule, Actions permissions, expected two jobs, immutable R1/R2 failures, and rollback/stop behavior. It must explicitly say that GitHub `success` is insufficient until the frozen loader validates distinct 3.9/3.12 fixed-owner interpreter identities. Do not create, push, dispatch, acquire, merge, or tag until that exact package receives user approval.
