# v0.64 Public CI R2 Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a new, preregistered R2 public Linux portability candidate that fixes the exact workflow self-scan defect, preserves the first public failure, and can generate a success witness only after real Python 3.9/3.12 Linux execution.

**Architecture:** Keep the failed public repository and Run `31850146784` immutable. A strict descendant private candidate `F2` updates only R2 repository identity, versioned manifest/witness contracts, the embedded workflow preflight, private-only regression tests, and the build manifest; the publisher and exported Linux test remain byte-identical to `F`. A new parentless root commit is built for `cjl308868584-lang/crypto-quant-v064-public-ci-r2`; external creation and push remain behind a fresh exact approval package.

**Tech Stack:** Python 3.9-compatible standard library, `jsonschema` Draft 2020-12, canonical JSON, Git object plumbing, Bash/GitHub Actions, `unittest`, pinned `gh` 2.96.0.

## Global Constraints

- The authoritative design is `docs/superpowers/specs/2026-08-15-v064-public-ci-r2-correction-design.md` at commit `6efb7fc9827e3f8ab818dbbf7f8bb579ad93111e`.
- Private baseline `F` is `1967f79ff8d013bf149bf36e2cdcb6a81ed200ff`; `F2` must be its strict descendant.
- The failed public repository, commit `0429837e5de8052e9e8216ed08ba9c7aa9c905b3`, Run `31850146784`, and Jobs `94924270273`/`94924270340` are immutable failure evidence.
- Never rerun, delete, archive, force-push, tag, release, or add commits/branches to `cjl308868584-lang/crypto-quant-v064-public-ci`.
- R2 public repository identity is exactly `cjl308868584-lang/crypto-quant-v064-public-ci-r2`.
- `src/crypto_quant/challenger_replacement_supersession_publish.py` and `tests/test_v064_linux_supersession_publish.py` must remain byte/OID-identical to `F`.
- The R2 public tree remains exactly eight files and one parentless root commit.
- Keep Python 3.9 syntax compatibility and add no runtime dependency.
- Keep `production_activation=false`, `credentials_present=false`, `broker_allowed=false`, `orders_allowed=false`, and `runtime_state_write_allowed=false`.
- No scheduler, deployment, Runner, Broker, order, credential, market request, production root, strategy state, owner attestation, private push/PR/merge/tag, or funds operation is allowed by this plan.
- Every behavior change follows exact RED, minimal GREEN, focused verification, and a separate commit.
- Run one local full suite only for the final `F2` code state. Do not mechanically repeat it on unchanged code.
- A second public repository/create/push/run requires a fresh exact user approval package after the R2 root commit/tree and eight hashes exist.

---

### Task 1: Freeze R2 Schema and Predecessor-Failure Contract

**Files:**
- Modify: `config/v064-public-ci-bundle-manifest-v1.schema.json`
- Modify: `src/crypto_quant/schemas/v064-public-ci-bundle-manifest-v1.schema.json`
- Modify: `config/v064-public-ci-witness-v1.schema.json`
- Modify: `src/crypto_quant/schemas/v064-public-ci-witness-v1.schema.json`
- Modify: `tests/test_v064_public_ci_bundle.py`
- Modify: `tests/test_v064_public_ci_witness.py`

**Interfaces:**
- Consumes: exact predecessor identities from design section 1.
- Produces: Schema version `1.1.0` with required `predecessor_failed_public_witness`; config/package mirrors remain byte-identical.

- [ ] **Step 1: Add RED fixture objects and mutation matrix**

Define one private test constant in both test modules with this exact shape:

```python
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
        {"python_version": "3.9", "job_id": 94924270273, "conclusion": "failure", "test_step_conclusion": "skipped"},
        {"python_version": "3.12", "job_id": 94924270340, "conclusion": "failure", "test_step_conclusion": "skipped"},
    ],
    "reason_code": "PUBLIC_SENSITIVE_BYTES_INVALID",
    "run_json_sha256": "f442ae366539fc4a244977fdafb2cd5de383b4248483381d8d79b751ea6a6099",
    "jobs_json_sha256": "9a69273c07548e97dbc2f43883eea4b5935f84256b7ad95b2874ca498bc67923",
    "run_log_sha256": "e47462120131eadb3161a40ffe679f4f74889103d7b3a13bb563df705f9ef32c",
    "transcript_summary_sha256": "cd2072e246698bec6d8767d37da4a3dca82d09fc38466a8009aea9690a0c9790",
}
```

Update valid manifest/witness fixtures to `schema_version="1.1.0"`, R2 repository identity, and the exact predecessor object. Add one mutation per scalar, job field, missing object, extra property, job reorder/duplicate, unsafe integer, 64-character Git OID, and non-lowercase hash. Each mutation must fail Schema validation.

- [ ] **Step 2: Run exact Schema RED tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_bundle.V064PublicCiSchemaTests \
  tests.test_v064_public_ci_witness.V064PublicCiWitnessSchemaTests
```

Expected: FAIL because current Schema requires version `1.0.0`, old repository identity, and has no predecessor object.

- [ ] **Step 3: Implement minimal closed Schema definitions**

In both manifest and witness Schemas:

- require top-level `predecessor_failed_public_witness`;
- set `schema_version` to `1.1.0`;
- set public repository const to `cjl308868584-lang/crypto-quant-v064-public-ci-r2`;
- add closed `$defs.predecessor_failed_public_witness`, `$defs.failed_jobs`, and `$defs.failed_job` matching the exact object above;
- retain `additionalProperties=false` at every object boundary;
- keep safe-integer maximum `9007199254740991`, 40-lowerhex Git OID, and 64-lowerhex SHA-256 constraints;
- change R2 raw evidence paths in witness Schema to `artifacts/v064-public-ci-r2/v064-public-ci-r2-{run-api,jobs-api,run-log,acquisition-transcript}-v1.*`.

Copy config/package Schema bytes exactly; do not create a second schema family.

- [ ] **Step 4: Run GREEN and mirror checks**

Run the Step 2 command, then:

```bash
cmp config/v064-public-ci-bundle-manifest-v1.schema.json \
  src/crypto_quant/schemas/v064-public-ci-bundle-manifest-v1.schema.json
cmp config/v064-public-ci-witness-v1.schema.json \
  src/crypto_quant/schemas/v064-public-ci-witness-v1.schema.json
git diff --check
```

Expected: all tests PASS and both `cmp` commands exit zero.

- [ ] **Step 5: Commit Task 1**

```bash
git add config/v064-public-ci-*-v1.schema.json \
  src/crypto_quant/schemas/v064-public-ci-*-v1.schema.json \
  tests/test_v064_public_ci_bundle.py tests/test_v064_public_ci_witness.py
git commit -m "test: freeze v0.64 public CI R2 evidence contract"
```

---

### Task 2: Build the R2 Manifest and Candidate Identity

**Files:**
- Modify: `src/crypto_quant/v064_public_ci_bundle.py`
- Modify: `src/crypto_quant/v064_public_ci_bundle_cli.py`
- Modify: `tests/test_v064_public_ci_bundle.py`
- Modify: `public_ci/v064/README.md`
- Modify: `public_ci/v064/NOTICE.md`

**Interfaces:**
- Consumes: Task 1 Schema and immutable predecessor constant.
- Produces: R2 `build_v064_public_ci_bundle_manifest(...)` and fixed candidate root `/private/tmp/crypto-quant-v064-public-ci-r2-candidate`.

- [ ] **Step 1: Add RED manifest and immutability tests**

Require the builder result to contain version `1.1.0`, R2 repository identity, and exact predecessor object. Read publisher/Linux-test blobs from `F` with `/usr/bin/git show`, then require current bytes and builder `source_blob_oid` to remain exact. Add a dedicated `V064PublicCiBundleCliTests` class with CLI static assertions for the new fixed candidate path and no caller-supplied repository/path.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_bundle.V064PublicCiBundleManifestTests \
  tests.test_v064_public_ci_bundle.V064PublicCiBundleCliTests
```

Expected: FAIL on old repository/version/path and missing predecessor object.

- [ ] **Step 3: Implement minimal R2 constants**

Add one immutable `_PREDECESSOR_FAILED_PUBLIC_WITNESS` mapping to `v064_public_ci_bundle.py`; return `copy.deepcopy`. Change only the manifest version/repository/predecessor fields and CLI fixed candidate path. Update public README/NOTICE only to identify R2 and immutable failed Run; add no URL, email, home path, business claim, or ninth file.

- [ ] **Step 4: Run GREEN and unchanged-blob gate**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_bundle.V064PublicCiBundleManifestTests \
  tests.test_v064_public_ci_bundle.V064PublicCiBundleCliTests
test "$(git hash-object src/crypto_quant/challenger_replacement_supersession_publish.py)" = \
  "$(git rev-parse 1967f79ff8d013bf149bf36e2cdcb6a81ed200ff:src/crypto_quant/challenger_replacement_supersession_publish.py)"
test "$(git hash-object tests/test_v064_linux_supersession_publish.py)" = \
  "$(git rev-parse 1967f79ff8d013bf149bf36e2cdcb6a81ed200ff:tests/test_v064_linux_supersession_publish.py)"
git diff --check
```

Expected: tests and both blob equality checks PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/crypto_quant/v064_public_ci_bundle.py \
  src/crypto_quant/v064_public_ci_bundle_cli.py \
  tests/test_v064_public_ci_bundle.py \
  public_ci/v064/README.md public_ci/v064/NOTICE.md
git commit -m "feat: bind v0.64 public CI R2 candidate"
```

---

### Task 3: Execute the Exact Embedded Preflight and Fix Self-Matching

**Files:**
- Modify: `public_ci/v064/.github/workflows/ci.yml`
- Modify: `tests/test_v064_public_ci_bundle.py`

**Interfaces:**
- Consumes: R2 candidate and exact old workflow from `F`.
- Produces: exact-heredoc behavior tests plus runtime-equivalent marker splitting.

- [ ] **Step 1: Add test-only exact preflight extractor**

Add a private helper that accepts workflow bytes, locates exactly one `Verify closed bundle before repository imports` `run: |` block, removes only fixed indentation, rejects ambiguity/CRLF/NUL, and executes `/bin/bash -c <exact_script>` in a real temporary Git checkout with fixed `GITHUB_REPOSITORY`, `GITHUB_REF`, and `GITHUB_SHA`. Do not add production code or YAML dependencies.

- [ ] **Step 2: Reproduce exact `F` failure**

Build an old eight-file checkout from `git show F:path` bytes plus canonical old manifest; initialize real Git. Execute exact old preflight and require exit 1, empty stdout, and stderr `PUBLIC_SENSITIVE_BYTES_INVALID\n`. This is a passing regression for the historic failure and never contacts GitHub.

- [ ] **Step 3: Add R2 success RED and self-consistent negative mutations**

Execute exact R2 preflight on a staged R2 checkout; before fix it must fail. For private-key marker, token, `/Users/`, email, non-allowlisted URL, and broker marker, update file bytes, manifest size/SHA/blob OID/file-set hash, commit the mutation, then require the exact sensitive failure. Construct forbidden test markers from byte fragments.

- [ ] **Step 4: Implement one semantic fix**

Change the contiguous workflow marker to:

```python
rb"Users/|BEGIN " + rb"PRIVATE KEY"
```

and fixed repository to R2. Do not exclude workflow, delete rules, or widen an allowlist.

- [ ] **Step 5: Run GREEN**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_bundle.V064PublicCiBundleManifestTests \
  tests.test_v064_public_ci_bundle.V064PublicCiWorkflowContractTests
git diff --check
```

Expected: historic failure reproduction, R2 success, and all malicious-payload rejection tests PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add public_ci/v064/.github/workflows/ci.yml tests/test_v064_public_ci_bundle.py
git commit -m "fix: prevent v0.64 public CI R2 self-match"
```

---

### Task 4: Derive an R2 Witness that Retains the Failure

**Files:**
- Modify: `src/crypto_quant/v064_public_ci_witness.py`
- Modify: `src/crypto_quant/v064_public_ci_witness_cli.py`
- Modify: `tests/test_v064_public_ci_witness.py`

**Interfaces:**
- Consumes: R2 bundle `1.1.0`, fixed R2 repository/root, successful R2 Run/Jobs/log/transcript bytes.
- Produces: `derive_v064_public_ci_witness(...) -> dict` version `1.1.0` containing predecessor failure and R2 success; a fixed-path, domain-specific R2 acquisition/publication CLI that acquires only the fixed R2 repository and can publish only the five fixed private evidence files.

- [ ] **Step 1: Add RED derivation and mutation tests**

Update successful fixtures to R2 repository/candidate. Require witness version `1.1.0`, exact predecessor object, and R2 public source. Mutate every predecessor field and require `V064_PUBLIC_CI_BUNDLE_INVALID` before success derivation. Assert no CLI/builder field accepts predecessor override, status, conclusion, Python version, repository, filename, output root, or PASS.

Add RED tests for the fixed five-file publisher before `F2` is frozen. The production CLI accepts only `--run-id`; it derives the reviewed private repository from the raw, non-symlinked module ancestry and uses only `artifacts/v064-public-ci-r2`. Tests may patch private low-level command/I/O wrappers and fixed module constants, but production exposes no caller path, generic storage API, callback, fault injector, or alternate repository. Require:

- owner-only retained parent identity and raw module/repository attachment checks;
- canonical JSON plus one LF for four JSON files and exact raw bytes for the log;
- nonce staging, same-fd write/readback, file fsync, atomic no-replace, directory fsync, final replay, and post-publish inventory;
- explicit unsupported/fail-closed handling for absent platform flags/primitives;
- symlink, hardlink, FIFO/nonregular, wrong-owner/mode/link-count, existing-different, orphan, short-write, fsync, no-replace, close, attachment-swap, and concurrent-loser tests with complete sentinel snapshots;
- all five outputs are staged and validated before the first canonical publication; a non-success Run or any acquisition/validation failure creates zero canonical files;
- crash after any individual canonical publication is recoverable only by exact trusted-byte replay of already-published files, followed by publication of the remaining prepared files; different or untrusted existing files block the whole ceremony without overwrite/chmod/unlink;
- precommitted formal-artifact regressions skip only when all five canonical paths are absent, and reject partial presence. These exact skips must be converted to real assertions after R2 success without changing production code.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v tests.test_v064_public_ci_witness
```

Expected: FAIL on old repository/root/version and missing predecessor output.

- [ ] **Step 3: Implement minimal R2 binding**

Set:

```python
_PUBLIC_REPOSITORY = "cjl308868584-lang/crypto-quant-v064-public-ci-r2"
_PUBLIC_ROOT = Path("/private/tmp/crypto-quant-v064-public-ci-r2-candidate")
```

Set witness version `1.1.0`, copy predecessor only from the replayed bundle, use Task 1 R2 raw paths, and change witness CLI `_REPOSITORY` to R2. Implement the fixed private artifact root and domain-specific five-file publisher described in Step 1 by reusing reviewed low-level no-replace primitives where their contracts match; do not reuse any direct-final writer and do not expose those primitives as a generic public API. Keep successful job/log requirements unchanged and expose no caller overrides.

- [ ] **Step 4: Run GREEN and adjacent tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_v064_public_ci_witness \
  tests.test_v064_public_ci_bundle \
  tests.test_v064_linux_supersession_publish
/usr/bin/python3 -m compileall -q \
  src/crypto_quant/v064_public_ci_bundle.py \
  src/crypto_quant/v064_public_ci_bundle_cli.py \
  src/crypto_quant/v064_public_ci_witness.py \
  src/crypto_quant/v064_public_ci_witness_cli.py \
  tests/test_v064_public_ci_bundle.py \
  tests/test_v064_public_ci_witness.py
git diff --check
```

Expected: all tests PASS; no external network occurs.

Also require the five formal-artifact regressions to report only their exact all-absent prepublication skips; any other skip is a failure. Record the exact skip identifiers for the Task 7 zero-skip gate.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/crypto_quant/v064_public_ci_witness.py \
  src/crypto_quant/v064_public_ci_witness_cli.py \
  tests/test_v064_public_ci_witness.py
git commit -m "feat: derive v0.64 public CI R2 witness"
```

---

### Task 5: Freeze and Review Private Candidate `F2`

**Files:**
- Modify: `config/evaluator-build-manifest-v1.json`
- Conditional modify: `src/crypto_quant/build.py`
- Conditional modify: `tests/test_estimators.py`
- Test: all Task 1-4 files and existing v0.64 supersession tests
- Generated locally only: `/private/tmp/crypto-quant-v064-public-ci-r2-candidate` and sibling bare Git store

**Interfaces:**
- Consumes: final Task 1-4 code state.
- Produces: reviewed private candidate `F2`, deterministic R2 root commit/tree, and exact irreversible approval package.

- [ ] **Step 1: Freeze evaluator build inputs**

Run `EvaluatorBuild.expected_file_paths()` RED coverage for the new R2 spec/plan and every modified private contract file. If the two new docs are absent, add only their exact paths to the existing v0.64 private-contract tuple in `src/crypto_quant/build.py`, update the focused test, and refresh `config/evaluator-build-manifest-v1.json` through the existing builder. Do not change package/release versions.

- [ ] **Step 2: Run focused final gate**

```bash
PYTHONWARNINGS=error::ResourceWarning PYTHONPATH=src /usr/bin/python3 -m unittest -v \
  tests.test_estimators.EvaluatorBuildTests \
  tests.test_v064_public_ci_bundle \
  tests.test_v064_public_ci_witness \
  tests.test_v064_linux_supersession_publish \
  tests.test_challenger_replacement_plan_v2 \
  tests.test_challenger_replacement_plan_supersession
/usr/bin/python3 -m compileall -q src tests
git diff --check
PYTHONPATH=src /usr/bin/python3 scripts/validate_evaluator_build.py
```

Expected: tests, compileall, diff-check, and evaluator-build replay PASS. Release activation validation may remain fail-closed because production activation is disabled.

- [ ] **Step 3: Run one full suite for final `F2` code**

```bash
make test
```

Save exact stdout/stderr bytes and SHA-256. Require zero failures; only predeclared formal-artifact skips may remain. Do not rerun on unchanged code.

- [ ] **Step 4: Request independent complete review**

Review immutable failure bindings, Schema closure, exact embedded preflight execution, self-consistent negative payloads, fixed identities, absence of caller PASS fields, publisher/Linux-test byte equality, build manifest, and no production/network/trading expansion. Critical/Important must be zero. Fixes use RED/GREEN and targeted re-review; rerun full suite only if production code changes.

- [ ] **Step 5: Commit `F2`**

```bash
git add config/evaluator-build-manifest-v1.json src/crypto_quant/build.py tests/test_estimators.py
git commit -m "feat: prepare v0.64 public CI R2 witness"
```

If build.py/test changes are unnecessary, stage only the manifest. Record `F2`, tree, ancestry from `F`, full-suite log hash, focused evidence, and review result.

- [ ] **Step 6: Build and replay local R2 candidate**

```bash
PYTHONPATH=src /usr/bin/python3 -m crypto_quant.v064_public_ci_bundle_cli build-candidate
PYTHONPATH=src /usr/bin/python3 -m crypto_quant.v064_public_ci_bundle_cli verify-candidate
```

Require exact eight files, all mode/size/SHA/source-blob identities, manifest/file-set hashes, zero sensitive findings, parent count zero, fixed noreply author, deterministic commit/tree, and publisher/Linux-test blob equality to `F`.

- [ ] **Step 7: Stop at new exact public approval package**

Show private branch/`F2`/tree; exact R2 repository name and PUBLIC visibility; eight paths/sizes/SHA-256/blob OIDs; manifest/file-set hashes; R2 root commit/tree; workflow actions/events/permissions; predecessor failure; local tests/review; and irreversible clone/fork/log consequences.

Request explicit approval covering only create R2 public repository, push exact root to `main`, allow one owner-push workflow, and read/seal its result. General prior authorization does not bypass this exact-bytes gate.

---

### Task 6: Create and Observe Exact R2 Public Run (After Exact Approval Only)

**Files:**
- External create: `cjl308868584-lang/crypto-quant-v064-public-ci-r2`
- External push: approved R2 root commit to `refs/heads/main`
- No private worktree changes during create/push/run

**Interfaces:**
- Consumes: exact user-approved `F2` and R2 root commit/tree.
- Produces: one real GitHub-hosted Ubuntu Python 3.9/3.12 Run or one retained honest failure.

- [ ] **Step 1: Revalidate before external write**

Require active account `cjl308868584-lang`, private source still private with ADMIN, exact private `F2`, R2 target absent, old failed repo/run unchanged, candidate replay clean, and no uncommitted private changes.

- [ ] **Step 2: Create empty public repository**

Create without README/license/gitignore initialization; disable issues/projects/wiki; default branch `main`; verify empty and public before push.

- [ ] **Step 3: Push only approved parentless root**

Push exact `<approved-r2-commit>:refs/heads/main`. Verify remote main/tree/parent count/eight paths/blob OIDs/visibility/permissions, one branch, zero tags/releases, and read-only workflow permissions.

- [ ] **Step 4: Observe owner-push Run once**

Do not manually dispatch when push creates the Run. Require exact R2 head/workflow and wait for both jobs. A test failure/cancel is retained and stops R2.

- [ ] **Step 5: Apply single infrastructure rerun rule**

Only if infrastructure fails before both validation/test steps execute and exact logs prove no validation/test ran, rerun the same commit once. No other rerun is eligible.

- [ ] **Step 6: Report actual result**

On success, report only `PUBLIC_LINUX_PORTABILITY_WITNESS_COMPLETED`. On failure, preserve exact hashes and stop without R3. Never claim private PR CI, profitability, Paper, Canary, or live readiness.

---

### Task 7: Seal Successful R2 Evidence and Create `G2` (Success Only)

**Files:**
- Create: `artifacts/v064-public-ci-r2/v064-public-ci-r2-run-api-v1.json`
- Create: `artifacts/v064-public-ci-r2/v064-public-ci-r2-jobs-api-v1.json`
- Create: `artifacts/v064-public-ci-r2/v064-public-ci-r2-run-log-v1.txt`
- Create: `artifacts/v064-public-ci-r2/v064-public-ci-r2-acquisition-transcript-v1.json`
- Create: `artifacts/v064-public-ci-r2/v064-public-ci-r2-witness-v1.json`
- Modify: `tests/test_v064_public_ci_witness.py`
- Modify: `config/evaluator-build-manifest-v1.json`

**Interfaces:**
- Consumes: first eligible successful R2 Run, exact `F2`, R2 root/manifest, old failure identities.
- Produces: strict five-file witness publication and successor private commit `G2`.

- [ ] **Step 1: Invoke the already-frozen acquisition and publisher**

Use only the successful R2 run ID with the exact production CLI frozen in `F2`. It captures fixed `gh` identity before/after each fixed API/log command, exact bytes, argv, exit codes, counts, and hashes into owner-only staging, then uses the already-reviewed five-file no-overwrite publisher. Any non-success or mismatch produces zero canonical success files. Do not modify production/template/Schema/builder/loader code after the Run.

- [ ] **Step 2: Replay production loaders**

Require exact file identity, canonical JSON/LF, witness Schema/id/hash, predecessor failure, R2 success, job versions/steps/log markers, false safety flags, `F -> F2` ancestry, and unchanged publisher/Linux-test blobs.

- [ ] **Step 3: Activate the precommitted formal-artifact regressions**

Run the precommitted regressions against the five fixed R2 files and require zero skips. If a test-only change is needed to replace an exact all-absent skip guard with committed hashes, it may add only those fixed hashes and must not alter production behavior, paths, parsing, or acceptance rules.

- [ ] **Step 4: Verify `F2 -> G2` unchanged-source boundary**

The index candidate may differ from `F2` only by five artifacts, exact regression lines, and build manifest. Any production/template/Schema/builder/loader change invalidates the public Run.

- [ ] **Step 5: Run focused post-run gate and review**

Run witness/bundle/Linux/supersession tests, compileall, diff-check, build-manifest replay, and artifact regressions. Do not repeat full suite because production code is unchanged from reviewed `F2`. Obtain targeted evidence review with Critical/Important zero.

- [ ] **Step 6: Commit exact `G2`**

```bash
git add artifacts/v064-public-ci-r2 \
  tests/test_v064_public_ci_witness.py \
  config/evaluator-build-manifest-v1.json
git commit -m "evidence: bind v0.64 public CI R2 witness"
```

Record `G2`, tree, parent chain, unchanged-source proof, witness hash, and all raw hashes.

- [ ] **Step 7: Stop before private integration**

Prepare separate approval for private push/replacement Draft PR. Do not close PR #32, merge, tag, archive public repositories, create public tags, resume owner attestation, install, or start service without later authorization.

---

## Completion Checklist

- [ ] Original failed repository and Run remain unchanged and publicly verifiable.
- [ ] R2 Schema/manifest/witness require exact predecessor failure.
- [ ] Exact old workflow self-match is reproduced locally without GitHub rerun.
- [ ] Exact R2 preflight succeeds on real closed checkout and rejects self-consistent malicious payloads.
- [ ] Publisher and exported Linux test are byte/OID-identical to `F`.
- [ ] `F2` is strict descendant of `F`; final code has one full-suite run and Critical/Important zero.
- [ ] R2 public root is parentless, deterministic, exactly eight files, and separately approved before disclosure.
- [ ] Python 3.9/3.12 real Linux tests run with exact markers and no skip/mock/fallback before success witness.
- [ ] Private witness binds first failure and R2 success; non-success creates no `G2`.
- [ ] No research, production, installation, credential, funds, or trading permission expands.
- [ ] v0.65 Nautilus and v0.66 replacement runtime sequence remains unchanged.
