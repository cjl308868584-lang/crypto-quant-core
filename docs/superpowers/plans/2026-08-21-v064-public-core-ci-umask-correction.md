# v0.64 Public Core CI Umask Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct restrictive-umask portability without weakening evidence publication, retire future public-mirror expansion, and release the exact fix through the now-public core repository.

**Architecture:** Preserve R1/R2/R3 as immutable historical evidence tied to exact Git objects. Normalize only a newly created, retained staging descriptor after validating its identity, and use ordinary public-core PR/main CI as the authority for current descendants. Do not create an R4 mirror, schema, witness, repository, or evidence root.

**Tech Stack:** CPython 3.9/3.12, standard-library `unittest`, POSIX descriptor I/O, Git object plumbing, GitHub Actions, canonical JSON/SHA-256.

**Spec:** `docs/superpowers/specs/2026-08-21-v064-public-core-ci-umask-correction-design.md`

## Global Constraints

- R1/R2/R3 committed artifacts, repositories, runs, schemas, and witness bytes remain unchanged.
- Current code authority is public PR Python 3.9/3.12 CI, fixed UID 501, merged-main CI, and annotated-tag identity.
- For production artifact publication, only a freshly `O_EXCL|O_NOFOLLOW`-created staging
  descriptor may be normalized with `fchmod`; no existing production final, staging, or external
  entry is chmodded.
- Only the test-owned reviewed checkout inside its verified `0700` private parent may normalize an exact
  `100644` HEAD plan through a retained no-follow descriptor; arbitrary world-writable plans remain rejected.
- Run the fixed UID boundary before the long full suite so security failures stop each matrix job early.
- No scheduler, deployment, Runner, Broker, credential, market/account request, order, production root, strategy-state write, or UI change.
- One local full suite for the final changed code state; no mechanical duplicate.

## File Structure

- `src/crypto_quant/challenger_replacement_supersession_publish.py`: new-descriptor normalization.
- `tests/test_challenger_replacement_plan_supersession.py`: restrictive-umask and security regressions.
- `tests/test_v064_public_ci_bundle.py`: historical F/F3 blob replay.
- `src/crypto_quant/build.py` and `tests/test_estimators.py`: exact build-input closure.
- The v0.64 supersession spec/plan: descriptor-normalization clarification.
- `config/evaluator-build-manifest-v1.json`: mechanically refreshed hashes.

---

### Task 1: Preserve and reproduce the public CI failure

**Files:**
- Test: `tests/test_challenger_replacement_plan_supersession.py`
- Evidence: `/private/tmp/v064-ci-logs/run-32485858116-failed.log`

**Interfaces:**
- Consumes: run `32485858116`, head `81d57221b6e1b947921aa30532e771654472f409`.
- Produces: deterministic RED evidence for tracked and staging mode `0640`.

- [x] **Step 1: Save the failed public job log**

```bash
gh run view 32485858116 --log-failed > /private/tmp/v064-ci-logs/run-32485858116-failed.log
rg -n -C 12 'FAIL|AssertionError|Traceback' /private/tmp/v064-ci-logs/run-32485858116-failed.log
```

Expected: Python 3.9 full suite succeeds and only the fixed-owner ceremony fails.

- [x] **Step 2: Reproduce the checkout failure without code changes**

```bash
(
  umask 0027
  PYTHONPATH=src:tests python3 -m unittest -v \
    test_challenger_replacement_plan_supersession.SupersessionCliBoundaryTests.test_temporary_git_ceremony_transitions_c0_through_c4_exactly
)
```

Expected before correction: the same tracked-plan assertion fails.

- [x] **Step 3: Add focused RED tests**

Add `test_ceremony_fixture_accepts_stricter_non_world_writable_tracked_plan` with literal modes
`0600` and `0640`. Add `test_exact_publish_normalizes_restrictive_process_umask`, temporarily set
`os.umask(0o027)`, publish fixed bytes, restore the umask in `finally`, and require committed mode
`0644`. Run each before implementation; expect the tracked-plan assertion and
`CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_UNTRUSTED` respectively.

### Task 2: Normalize only trusted new objects

**Files:**
- Modify: `tests/test_challenger_replacement_plan_supersession.py`
- Modify: `src/crypto_quant/challenger_replacement_supersession_publish.py`
- Modify: `docs/superpowers/specs/2026-08-09-replacement-challenger-plan-v2-supersession-design.md`
- Modify: `docs/superpowers/plans/2026-08-09-replacement-challenger-plan-v2-supersession.md`

**Interfaces:**
- Consumes: retained staging descriptor from `_publish_fixed`.
- Produces: caller-umask-independent exact mode `0644` publication.

- [x] **Step 1: Replace the tracked-plan discrete mode allowlist**

Require regular file, effective-UID ownership, nlink 1, owner-read, no special/execute bits, and no
world-write bit before exact HEAD/canonical byte verification. Keep hardlink, world-writable,
nonregular, byte-drift, and dirty-repository failures.

- [x] **Step 2: Add the preliminary staging predicate**

```python
def _trusted_new_empty_staging_stat(value: os.stat_result) -> bool:
    mode = stat.S_IMODE(value.st_mode)
    return (
        stat.S_ISREG(value.st_mode)
        and value.st_uid == os.geteuid() == 501
        and mode & ~0o644 == 0
        and value.st_nlink == 1
        and value.st_size == 0
    )
```

- [x] **Step 3: Normalize the retained descriptor**

After preliminary validation, call `os.fchmod(staging_fd, 0o644)`, re-`fstat`, require the same
device/inode and exact trusted mode, then continue unchanged write/readback/fsync/no-replace logic.

- [x] **Step 4: Run fixed-owner GREEN**

```bash
PYTHONPATH=src:tests python3 -m unittest -v \
  test_challenger_replacement_plan_supersession.FixedSupersessionPublisherTests \
  test_challenger_replacement_plan_supersession.SupersessionCliBoundaryTests
```

Expected: 41 tests pass. Also rerun C0→C4 under `umask 0027`; expect PASS.

- [x] **Step 5: Close the permissive checkout boundary**

Preserve run `32509529713` as the exact RED showing
`mode=0666 uid=501 euid=501 nlink=1 regular=True`. Add a controlled-checkout regression; first
verify the private parent, HEAD `100644` entry, and retained descriptor's canonical bytes, UID,
nlink, type, and size, then normalize the descriptor and revalidate its attachment identity and
exact mode. Keep the independent arbitrary-world-writable rejection unchanged. Run
`FixedSupersessionPublisherTests` plus `SupersessionCliBoundaryTests`; expect 42 tests. Require the
reordered public CI gate to pass on both Python versions before either full suite begins.

### Task 3: Split historical R3 evidence from current code

**Files:**
- Modify: `tests/test_v064_public_ci_bundle.py`

**Interfaces:**
- Consumes: F `1967f79ff8d013bf149bf36e2cdcb6a81ed200ff`, F3 `f9705fa2151ab98a5b9efe63be05979e4bc5bfa6`, and two frozen paths.
- Produces: a historical claim that permits reviewed current descendants.

- [ ] **Step 1: Add the historical-object RED**

Name the test `test_historical_r3_publisher_and_linux_test_blobs_match_f`. For each frozen path, use
`/usr/bin/git rev-parse <commit>:<path>` and `cat-file blob <oid>`. Require the F3 OID and bytes to
equal F. Current behavior is covered by the restrictive-umask publisher test, not by a source-change
detector against current HEAD.

- [ ] **Step 2: Verify the new test is initially absent**

```bash
PYTHONPATH=src:tests python3 -m unittest -v \
  test_v064_public_ci_bundle.V064PublicCiBundleManifestTests.test_historical_r3_publisher_and_linux_test_blobs_match_f
```

Expected: test lookup fails before the new historical contract exists.

- [ ] **Step 3: Replace only the obsolete current-HEAD assertion**

Delete `test_real_publisher_and_linux_test_blobs_remain_identical_to_f` and add the exact historical
test. Do not change R3 builders, schemas, artifacts, or witness loaders.

- [ ] **Step 4: Verify bundle/witness adjacency**

```bash
PYTHONPATH=src:tests python3 -m unittest -v test_v064_public_ci_bundle test_v064_public_ci_witness
```

Expected: all tests pass and committed R3 bytes replay unchanged.

### Task 4: Close build inputs and verify the final local state

**Files:**
- Modify: `src/crypto_quant/build.py`
- Modify: `tests/test_estimators.py`
- Create: `docs/superpowers/plans/2026-08-21-v064-public-core-ci-umask-correction.md`
- Modify: `config/evaluator-build-manifest-v1.json`

**Interfaces:**
- Consumes: `EvaluatorBuild.expected_file_paths(ROOT)`.
- Produces: exact final build tree and manifest hashes.

- [ ] **Step 1: Add a RED build-input closure assertion**

Add the new spec and plan paths to `test_v064_release_inputs_are_complete`, run that exact test, and
expect failure because `_V064_PUBLIC_CI_PRIVATE_CONTRACT_PATHS` lacks both.

- [ ] **Step 2: Add the two exact build paths**

Append both literal paths to `_V064_PUBLIC_CI_PRIVATE_CONTRACT_PATHS`. Do not glob or add unrelated
inputs.

- [ ] **Step 3: Run affected tests and static gates**

```bash
PYTHONPATH=src:tests python3 -m unittest -v \
  test_estimators.EvaluatorBuildTests.test_v064_release_inputs_are_complete \
  test_estimators.EvaluatorBuildTests.test_v064_public_ci_private_contract_is_frozen_in_build_inputs \
  test_challenger_replacement_plan_supersession test_v064_public_ci_bundle test_v064_public_ci_witness
python3 -m compileall -q src tests scripts
git diff --check
```

Expected: all pass with no new skips.

- [ ] **Step 4: Refresh and replay the build manifest**

```bash
PYTHONPATH=src python3 scripts/refresh_evaluator_build_manifest.py
PYTHONPATH=src python3 scripts/validate_evaluator_build.py
make validate
```

Expected: build replay passes; designed production-activation negative statuses remain non-authorizing.

- [ ] **Step 5: Run one full suite for the final changed state**

```bash
make test
```

Expected: all tests pass with only the five pre-existing formal-artifact skips. Do not repeat on an
unchanged tree.

- [ ] **Step 6: Commit the correction**

Stage only the files named by Tasks 2–4 and commit with message
`fix: normalize v0.64 public CI umask boundary`.

### Task 5: Complete normal public release gates

**Files:**
- No source edits after the final candidate commit.

**Interfaces:**
- Consumes: exact PR head, merged main, and annotated tag.
- Produces: published `v0.64.0` identity or an immutable failed gate.

- [ ] **Step 1: Push the exact descendant and verify PR #33**

```bash
git push origin codex/v0.64-public-ci-r3-design
gh pr view 33 --json headRefOid,isDraft,state,statusCheckRollup,url
```

- [ ] **Step 2: Require PR Python 3.9/3.12 and fixed UID success**

Run the fixed UID boundary before `make test` in each matrix job. Do not rerun an unchanged SHA. Any
failure stops merge and is debugged from exact logs.

- [ ] **Step 3: Merge and require exact merged-main CI**

```bash
gh pr ready 33
gh pr merge 33 --merge --delete-branch=false
git ls-remote origin refs/heads/main
```

Wait for the workflow whose `headSha` is the exact new remote main; require all jobs successful.

- [ ] **Step 4: Create and verify annotated `v0.64.0`**

```bash
git tag -a v0.64.0 <exact-main-sha> -m "v0.64.0"
git push origin v0.64.0
git ls-remote origin refs/heads/main refs/tags/v0.64.0 'refs/tags/v0.64.0^{}'
```

Expected: local tag type is `tag`, peeled remote tag equals `origin/main`, and the worktree is clean.
