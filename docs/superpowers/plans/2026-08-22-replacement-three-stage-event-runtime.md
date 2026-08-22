# Replacement Challenger Three-Stage Event Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从已发布 v2 plan 实现仅以 append-only canonical event log 为权威的 replacement Challenger 三阶段可恢复 runtime。

**Architecture:** retained event-root capability 提供 no-follow/no-overwrite/durable append；纯 source/decision 模块产生可重放 canonical bytes；runtime projection 仅接受 `INPUT_PREPARED -> RESULT_PREPARED -> SLOT_SUCCEEDED` 和冻结失败终端。独立 source/decision artifact、SQLite 和 output-root 全部排除。

**Tech Stack:** Python 3.9+、stdlib descriptor/ctypes/SQLite-free I/O、`jsonschema`、`unittest`、GitHub Actions Python 3.9/3.12 + macOS 15 arm64。

**Spec:** `docs/superpowers/specs/2026-08-22-replacement-three-stage-event-runtime-design.md`

## Global Constraints

- Base and release predecessor are annotated `v0.65.1` peeled commit `9799a99823a1b3fbc33368357991b09ef7dc321b`.
- Exact v2 plan path is `artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json`; file SHA-256 is `5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f`.
- Authority is only `state/challenger-replacement-events-v1`; exports are reconstructible and non-authoritative.
- Success state machine is exactly `INPUT_PREPARED -> RESULT_PREPARED -> SLOT_SUCCEEDED`.
- The only slot failure terminal is `SLOT_FAILED_PERMANENT` after a valid INPUT or RESULT boundary.
- No SQLite/SQL/PRAGMA/WAL/SHM, output-root, artifact publisher, lease/claim, generic storage, scheduler, deployment, Runner, network, Broker, order, UI, production root, credential, account or money path.
- No public fault callback/enum/configuration seam; tests patch private low-level functions only.
- `production_activation=false`, `runtime_install_authorized=false`, `replacement_start_authorized=false`, `real_orders_allowed=false` remain unchanged.
- The four production modules `decision + evidence + events + runtime` must total strictly less than 2743 physical lines; stop before commit if the gate is not met.
- Every task uses RED -> minimal GREEN -> refactor; each final code state receives focused tests, and the milestone final state receives one local full suite only.

---

## File Map

**Create production files**

- `src/crypto_quant/challenger_replacement_events.py`: retained capability, event codec, durable publisher and strict replay.
- `src/crypto_quant/challenger_replacement_evidence.py`: pure source-bundle builder/bytes loader and semantics; no path I/O.
- `src/crypto_quant/challenger_replacement_decision.py`: pure frozen policy and parent-chain decision semantics.
- `src/crypto_quant/challenger_replacement_runtime.py`: projection, optimistic append and three-stage slot orchestration.
- `src/crypto_quant/schemas/challenger-replacement-source-bundle-v1.schema.json`: packaged source schema.
- `src/crypto_quant/schemas/challenger-replacement-decision-v1.schema.json`: packaged decision schema.
- `config/challenger-replacement-source-bundle-v1.schema.json`: exact source schema mirror.
- `config/challenger-replacement-decision-v1.schema.json`: exact decision schema mirror.

**Create test files**

- `tests/test_challenger_replacement_events.py`: descriptor, codec, crash, concurrency and replay safety.
- `tests/test_challenger_replacement_evidence.py`: v2-bound source bundle/schema/bytes tests.
- `tests/test_challenger_replacement_decision.py`: v2-bound policy and previous-decision tests.
- `tests/test_challenger_replacement_runtime.py`: three-stage projection/recovery/concurrency tests.
- `tests/test_challenger_replacement_v066_release.py`: scope, static, line-count, version and manifest gates.

**Create release docs**

- `docs/adr/0066-replacement-three-stage-event-runtime.md`
- `docs/implementation-status-v0.66.0.md`

**Modify release identity**

- `pyproject.toml`
- `setup.py`
- `src/crypto_quant/__init__.py`
- `src/crypto_quant/build.py`
- `config/evaluator-build-manifest-v1.json`
- `scripts/refresh_evaluator_build_manifest.py`
- `tests/test_estimators.py`
- `tests/test_v064_public_ci_bundle.py`
- `tests/test_nautilus_v065_release.py`
- `README.md`

---

### Task 1: Port and re-prove the capability-safe event store

**Files:**
- Create: `tests/test_challenger_replacement_events.py`
- Create: `src/crypto_quant/challenger_replacement_events.py`

**Interfaces:**
- Produces: `ChallengerReplacementEventRootIdentity`, `ChallengerReplacementEventRoot`, `build_challenger_replacement_event`, `load_challenger_replacement_event_bytes`, `publish_challenger_replacement_event`, `replay_challenger_replacement_events`, `open_challenger_replacement_event_root`.
- Consumes: `crypto_quant.canonical.canonical_json` only.

- [ ] **Step 1: Read the audited engineering source without modifying it**

Run:

```bash
git show 5adf7f8:src/crypto_quant/challenger_replacement_events.py | sed -n '1,900p'
git show 5adf7f8:tests/test_challenger_replacement_events.py | sed -n '1,1600p'
```

Confirm the source contains no runtime projection or artifact publication semantics and the test file covers final-visible/pre-dir-fsync replay.

- [ ] **Step 2: Add the event public-behavior tests first**

Use `apply_patch` to reconstruct the reviewed test file from `5adf7f8`, preserving tests for:

```python
def test_sequence_safe_integer_bounds_before_io(): ...
def test_fifo_final_publish_and_replay_never_block(): ...
def test_symlink_hardlink_and_replacement_preserve_external_sentinel(): ...
def test_visible_final_after_failed_dir_fsync_is_reconfirmed(): ...
def test_replay_only_fresh_process_confirms_directory_durability(): ...
def test_real_two_process_same_and_different_event_races(): ...
def test_primary_exception_survives_close_failure(): ...
```

Do not port tests for SQLite, runtime stages, output roots or source/decision artifacts.

- [ ] **Step 3: Run RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_events
```

Expected: import failure because `crypto_quant.challenger_replacement_events` does not exist.

- [ ] **Step 4: Add the minimal event module**

Use `apply_patch` to reconstruct only the reviewed event store from `5adf7f8`. Preserve:

```python
_MAX_CANONICAL_EVENT_BYTES = 4_194_304
_MAX_CANONICAL_EVENT_SEQUENCE = (1 << 53) - 1
_EVENT_HASH_DOMAIN = b"CHALLENGER_REPLACEMENT_EVENT_V1\x00"
```

Require `O_NOFOLLOW`, `O_DIRECTORY` and `O_NONBLOCK` explicitly; keep Darwin `renameatx_np(RENAME_EXCL)` and Linux `renameat2(RENAME_NOREPLACE)` fail-closed paths. Do not add a path-based constructor or public fault seam.

- [ ] **Step 5: Run GREEN and static scan**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_events
rg -n "sqlite3|PRAGMA|WAL|SHM|fault_injector|os\.replace|os\.rename" \
  src/crypto_quant/challenger_replacement_events.py
```

Expected: all tests pass; static scan returns no forbidden implementation.

- [ ] **Step 6: Commit**

```bash
git add src/crypto_quant/challenger_replacement_events.py \
  tests/test_challenger_replacement_events.py
git commit -m "feat: add replacement canonical event store"
```

---

### Task 2: Freeze v2 source bundle and decision documents

**Files:**
- Create: `config/challenger-replacement-source-bundle-v1.schema.json`
- Create: `config/challenger-replacement-decision-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-source-bundle-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-decision-v1.schema.json`
- Create: `tests/test_challenger_replacement_evidence.py`
- Create: `tests/test_challenger_replacement_decision.py`
- Create: `src/crypto_quant/challenger_replacement_evidence.py`
- Create: `src/crypto_quant/challenger_replacement_decision.py`

**Interfaces:**
- Produces: `build_challenger_replacement_source_bundle`, `load_challenger_replacement_source_bundle_bytes`, `build_challenger_replacement_decision`, `load_challenger_replacement_decision_bytes`.
- Consumes: exact v2 plan validated by `challenger_replacement_plan_v2_reasons`; exact build identity mapping.

- [ ] **Step 1: Add strict mirrored schemas and schema tests**

Use the reviewed schema shapes from `e5d6ce4`, but change plan validation tests to the exact v2 plan. Both source and decision schema must use `additionalProperties: false`, decimal strings rather than JSON floats, and exact parent/build/plan objects.

Add tests that assert:

```python
self.assertEqual(CONFIG_SOURCE.read_bytes(), PACKAGE_SOURCE.read_bytes())
self.assertEqual(CONFIG_DECISION.read_bytes(), PACKAGE_DECISION.read_bytes())
Draft202012Validator.check_schema(json.loads(CONFIG_SOURCE.read_text()))
Draft202012Validator.check_schema(json.loads(CONFIG_DECISION.read_text()))
```

- [ ] **Step 2: Add v2-bound RED tests**

Tests must load the committed v2 plan and prove:

```python
source = build_challenger_replacement_source_bundle(
    plan=plan_v2,
    capture=genesis_capture,
    observed_at="2026-08-22T04:00:00.000Z",
    build_identity=fixture_build,
    previous_source_bundle=None,
    previous_decision=None,
)
decision = build_challenger_replacement_decision(
    plan=plan_v2,
    source_bundle=source,
    recorded_at="2026-08-22T04:00:00.000Z",
    previous_decision=None,
)
```

Add second-slot tests requiring sequence 2, exact `+4h`, identical 20-bar overlap and non-null previous decision. Add duplicate-key, float, noncanonical bytes, self-hash, wrong v2 plan, wrong build and wrong parent failures.

- [ ] **Step 3: Run RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_evidence \
  tests.test_challenger_replacement_decision
```

Expected: missing module/API failures.

- [ ] **Step 4: Implement pure document semantics**

Port only the pure builder/semantic portions from `67a65d5`; delete every path/output capability and publisher function. Public bytes loaders accept `bytes`, never `Path`:

```python
def load_challenger_replacement_source_bundle_bytes(
    data: bytes, *, plan, build_identity, previous_source_bundle, previous_decision
) -> Dict[str, Any]: ...

def load_challenger_replacement_decision_bytes(
    data: bytes, *, plan, source_bundle, previous_decision
) -> Dict[str, Any]: ...
```

Replace every `challenger_replacement_plan_reasons` call with `challenger_replacement_plan_v2_reasons`. Preserve exact canonical bytes and self-hash replay. No file read/write/chmod/open is allowed in `challenger_replacement_evidence.py`.

- [ ] **Step 5: Run GREEN and static scope scan**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_evidence \
  tests.test_challenger_replacement_decision \
  tests.test_challenger_replacement_plan_v2
rg -n "open\(|read_bytes|write_bytes|chmod|OutputRoot|publish|recover|sqlite3|Broker|order" \
  src/crypto_quant/challenger_replacement_evidence.py \
  src/crypto_quant/challenger_replacement_decision.py
```

Expected: tests pass and forbidden scan is empty.

- [ ] **Step 6: Commit**

```bash
git add config/challenger-replacement-source-bundle-v1.schema.json \
  config/challenger-replacement-decision-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-source-bundle-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-decision-v1.schema.json \
  src/crypto_quant/challenger_replacement_evidence.py \
  src/crypto_quant/challenger_replacement_decision.py \
  tests/test_challenger_replacement_evidence.py \
  tests/test_challenger_replacement_decision.py
git commit -m "feat: freeze replacement v2 decision documents"
```

---

### Task 3: Implement the strict three-stage projection

**Files:**
- Create: `tests/test_challenger_replacement_runtime.py`
- Create: `src/crypto_quant/challenger_replacement_runtime.py`

**Interfaces:**
- Produces: `ChallengerReplacementRuntimeState`, `ChallengerReplacementRuntimeError`, `ChallengerReplacementRuntimeState.replay`, `ChallengerReplacementRuntimeState.append`.
- Consumes: event root capability, exact v2 plan, exact build identity and strict document bytes loaders.

- [ ] **Step 1: Add projection RED tests**

Construct canonical events through the public event builder/publisher, then assert replay accepts only:

```text
INPUT_PREPARED
INPUT_PREPARED -> RESULT_PREPARED
INPUT_PREPARED -> RESULT_PREPARED -> SLOT_SUCCEEDED
INPUT_PREPARED -> SLOT_FAILED_PERMANENT
INPUT_PREPARED -> RESULT_PREPARED -> SLOT_FAILED_PERMANENT
```

Add explicit failing chains for SOURCE_BUNDLE_PUBLISHED, DECISION_PUBLISHED, two active slots, terminal-followed-by-event, mismatched success sequence/hash/SHA, malformed capture hash, wrong plan/build/root and different slots interleaved.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_runtime.ProjectionTests
```

Expected: `challenger_replacement_runtime` missing.

- [ ] **Step 3: Implement projection and exact payload validators**

Define:

```python
_STAGES = ("INPUT_PREPARED", "RESULT_PREPARED", "SLOT_SUCCEEDED")
_TERMINAL = "SLOT_FAILED_PERMANENT"
```

`replay()` must strict-load event payload bytes, source bytes and decision bytes; bind all hashes/sequences; enforce one active slot and return:

```python
{
    "events": tuple(...),
    "slots": {...},
    "last_event_hash": "...",
    "next_sequence": 1,
    "active_slot_id": None,
    "completed_slot_count": 0,
    "failed_slot_count": 0,
    "next_required_slot": {...},
    "orphan_staging_count": 0,
    "orphan_staging_bytes": 0,
}
```

- [ ] **Step 4: Add and pass optimistic token tests**

Two state objects read the same RESULT projection. The first appends success; the second calls append with the stale hash and must receive `CHALLENGER_REPLACEMENT_EVENT_SEQUENCE_CONFLICT` before event construction. Final replay has one success event only.

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_runtime.ProjectionTests \
  tests.test_challenger_replacement_runtime.OptimisticAppendTests
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_runtime.py \
  tests/test_challenger_replacement_runtime.py
git commit -m "feat: project replacement three-stage events"
```

---

### Task 4: Implement deterministic slot orchestration and recovery

**Files:**
- Modify: `tests/test_challenger_replacement_runtime.py`
- Modify: `src/crypto_quant/challenger_replacement_runtime.py`

**Interfaces:**
- Produces: `run_challenger_replacement_slot(*, state, capture, observed_at, worker_id)`.
- Consumes: `ChallengerReplacementRuntimeState.replay/append` and pure source/decision APIs.

- [ ] **Step 1: Add genesis and successor RED tests**

Assert one invocation progresses all three stages and a second natural `+4h` capture uses the replayed previous source/decision. Patch the decision builder to assert successor `previous_decision is not None`.

- [ ] **Step 2: Add crash-boundary RED tests**

Using `unittest.mock.patch` only on private append wrappers, raise after INPUT commit and after RESULT commit. Open a fresh capability/state and retry:

- after INPUT: source build count 0, decision compute count 1, reaches success;
- after RESULT: source build and decision compute counts 0, reaches success;
- after SUCCESS: all build/compute/event-create/write counts 0, returns replayed result.

Do not add a production `fault_injector` parameter or enum.

- [ ] **Step 3: Run RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_runtime.SlotRuntimeTests \
  tests.test_challenger_replacement_runtime.CrashRecoveryTests
```

Expected: missing `run_challenger_replacement_slot` or stage-count failures.

- [ ] **Step 4: Implement minimal orchestration**

Each stage must call fresh replay, retain its `last_event_hash`, and append with that exact token. For an existing INPUT, build decision from INPUT event `recorded_at` and exact source bytes, not the retry arguments. For an existing RESULT, strict-load exact bytes and append success without recomputation.

Invalid unbound input returns a fixed runtime error with zero event. A valid active slot failure appends `SLOT_FAILED_PERMANENT` using the error-time token. Sequence conflict is re-raised unchanged and never converted into failure.

- [ ] **Step 5: Add active-slot and idempotency gates**

Tests must prove:

```python
self.assertEqual(event_count_after_success_retry, event_count_before_retry)
self.assertEqual((source_builds, decision_computes, event_writes), (0, 0, 0))
self.assertEqual(original_active_slot_events_after_other_slot, original_active_slot_events_before)
```

- [ ] **Step 6: Run GREEN**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_runtime \
  tests.test_challenger_replacement_events \
  tests.test_challenger_replacement_evidence \
  tests.test_challenger_replacement_decision
```

- [ ] **Step 7: Commit**

```bash
git add src/crypto_quant/challenger_replacement_runtime.py \
  tests/test_challenger_replacement_runtime.py
git commit -m "feat: recover replacement three-stage slots"
```

---

### Task 5: Close concurrency, crash and scope gates

**Files:**
- Modify: `tests/test_challenger_replacement_events.py`
- Modify: `tests/test_challenger_replacement_runtime.py`
- Create: `tests/test_challenger_replacement_v066_release.py`
- Modify only if a RED test requires it: the four production modules.

**Interfaces:**
- Produces: milestone safety regression and YAGNI proof.
- Consumes: all Task 1-4 public behavior.

- [ ] **Step 1: Run real multiprocessing gates**

Use a test-only `multiprocessing` barrier around the existing private `_rename_noreplace` wrapper. Verify one inode and exact outcomes:

```text
same event      {COMMITTED, ALREADY_COMMITTED}
different event {COMMITTED, CONFLICT}
```

At least one rename-after/dir-fsync-before failure must be replayed by a new interpreter that calls replay only.

- [ ] **Step 2: Add no-side-effect failure matrix**

Snapshot external sentinel `bytes/mode/size/mtime_ns/ctime_ns/inode/nlink`. Exercise symlink, hardlink, wrong mode, replacement and special-object failures. Assert the complete snapshot is unchanged and no canonical event is created on pre-append validation failures.

- [ ] **Step 3: Add static scope and line-count tests**

`tests/test_challenger_replacement_v066_release.py` must parse source text and reject:

```python
FORBIDDEN = (
    "sqlite3", "PRAGMA", "-wal", "-shm", "fault_injector",
    "SOURCE_BUNDLE_PUBLISHED", "DECISION_PUBLISHED",
    "ChallengerReplacementOutputRoot", "Broker", "order_writes",
)
```

It must assert:

```python
total = sum(len(path.read_text().splitlines()) for path in FOUR_MODULES)
self.assertLess(total, 2743)
```

Also assert no `.sqlite`, `-wal`, `-shm`, `exports/source-bundles` or `exports/decisions` file exists after integration tests.

- [ ] **Step 4: Run the complete v0.66 focused gate**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_events \
  tests.test_challenger_replacement_evidence \
  tests.test_challenger_replacement_decision \
  tests.test_challenger_replacement_runtime \
  tests.test_challenger_replacement_v066_release \
  tests.test_challenger_replacement_plan_v2 \
  tests.test_challenger_replacement_plan_supersession
python3 -m compileall -q src tests scripts
git diff --check
```

- [ ] **Step 5: Report and enforce YAGNI before commit**

Run:

```bash
wc -l src/crypto_quant/challenger_replacement_{decision,evidence,events,runtime}.py
git diff --numstat v0.65.1...HEAD
```

If total is 2743 or more, stop and redesign. Otherwise record exact module counts in the commit message notes and continue.

- [ ] **Step 6: Commit**

```bash
git add tests/test_challenger_replacement_events.py \
  tests/test_challenger_replacement_runtime.py \
  tests/test_challenger_replacement_v066_release.py \
  src/crypto_quant/challenger_replacement_*.py
git commit -m "test: close replacement runtime safety gates"
```

---

### Task 6: Freeze v0.66 release identity and documentation

**Files:**
- Create: `docs/adr/0066-replacement-three-stage-event-runtime.md`
- Create: `docs/implementation-status-v0.66.0.md`
- Modify: release identity and manifest files listed in File Map.

**Interfaces:**
- Produces: package `0.66.0`, manifest `1.60.0`, status `RUNTIME_RELEASED_NOT_INSTALLED`.
- Consumes: final unchanged Task 1-5 code and exact v2 plan.

- [ ] **Step 1: Add release RED tests**

Assert package versions are `0.66.0`, manifest version is `1.60.0`, all new production/schema/test/spec/plan/ADR/status paths are in `EvaluatorBuild.expected_file_paths`, v2 plan exact SHA is unchanged, and docs include:

```text
RUNTIME_RELEASED_NOT_INSTALLED
production_activation=false
runtime_install_authorized=false
replacement_start_authorized=false
no 90-day timer started
no profitability or AI advantage claim
```

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_v066_release \
  tests.test_estimators.EvaluatorBuildTests
```

Expected: version and missing build-input failures.

- [ ] **Step 3: Update release files and docs**

Set package `0.66.0`, manifest `1.60.0`; add `_V066_RELEASE_PATHS` in `build.py`; write ADR/status and README link. Do not alter v0.64 plan/supersession artifacts or v0.65 formal evidence bytes.

- [ ] **Step 4: Refresh and replay manifest**

```bash
PYTHONPATH=src python3 scripts/refresh_evaluator_build_manifest.py
PYTHONPATH=src python3 scripts/validate_evaluator_build.py
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_v066_release \
  tests.test_estimators.EvaluatorBuildTests \
  tests.test_v064_public_ci_bundle.V064PublicCiFinalFreezeTests \
  tests.test_nautilus_v065_release
make validate
python3 -m compileall -q src tests scripts
git diff --check
```

- [ ] **Step 5: Commit the release candidate**

```bash
git add README.md config pyproject.toml setup.py scripts \
  src/crypto_quant/__init__.py src/crypto_quant/build.py \
  tests/test_estimators.py tests/test_v064_public_ci_bundle.py \
  tests/test_nautilus_v065_release.py \
  tests/test_challenger_replacement_v066_release.py \
  docs/adr/0066-replacement-three-stage-event-runtime.md \
  docs/implementation-status-v0.66.0.md
git commit -m "release: freeze replacement runtime v0.66.0"
```

---

### Task 7: Independent review and final local verification

**Files:**
- Modify only for verified review findings.

**Interfaces:**
- Produces: final immutable release candidate with Critical=0 and Important=0.

- [ ] **Step 1: Request one independent full review**

Review exact `v0.65.1...HEAD`, spec, plan, four modules and tests. Require explicit findings for authority drift, crash recovery, descriptor safety, projection semantics, line cap and research/production boundaries.

- [ ] **Step 2: Fix findings with targeted RED/GREEN only**

Use `receiving-code-review`, `systematic-debugging` and TDD. After fixes, request targeted re-review only; do not repeat the full review without code changes.

- [ ] **Step 3: Run final focused/adjacent validation**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_events \
  tests.test_challenger_replacement_evidence \
  tests.test_challenger_replacement_decision \
  tests.test_challenger_replacement_runtime \
  tests.test_challenger_replacement_v066_release \
  tests.test_challenger_replacement_plan_v2 \
  tests.test_challenger_replacement_plan_supersession \
  tests.test_estimators.EvaluatorBuildTests
make validate
python3 -m compileall -q src tests scripts
git diff --check
```

- [ ] **Step 4: Run the single local full suite on final unchanged code**

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Record exact count, skips, elapsed time and exit code. Do not run a second local full suite on the same commit.

- [ ] **Step 5: Commit review fixes if any and prove clean state**

```bash
git status --short
git log --oneline v0.65.1..HEAD
git diff --check v0.65.1..HEAD
```

Expected: clean worktree and only reviewed v0.66 commits.

---

### Task 8: Public PR, main CI and annotated release tag

**Files:** none locally after the final candidate.

**Interfaces:**
- Produces: merged public main and annotated `v0.66.0` with exact peeled identity.

- [ ] **Step 1: Reverify remote authority**

```bash
gh repo view cjl308868584-lang/crypto-quant-core \
  --json nameWithOwner,visibility,viewerPermission,defaultBranchRef
git fetch origin --prune
git rev-parse origin/main
git rev-parse 'v0.65.1^{}'
```

Require PUBLIC, ADMIN, default `main`, and exact common predecessor `9799a99823a1b3fbc33368357991b09ef7dc321b`.

- [ ] **Step 2: Push branch and create Draft PR**

Push `codex/v0.66-replacement-event-runtime`. PR body must state the event-only authority, exact local test/review evidence and all nonclaims.

- [ ] **Step 3: Wait for public PR CI**

Require success for Python 3.9, Python 3.12 and macOS 15 arm64. Do not merge queued, skipped, cancelled or neutral checks.

- [ ] **Step 4: Squash merge and wait for main CI**

Verify PR head SHA before merge; record squash merge commit. Require all main jobs success and head SHA equal the merge commit.

- [ ] **Step 5: Create and verify annotated tag**

```bash
git tag -a v0.66.0 <exact-main-commit> \
  -m "v0.66.0: replacement three-stage event runtime"
git push origin refs/tags/v0.66.0
git ls-remote origin refs/heads/main refs/tags/v0.66.0 'refs/tags/v0.66.0^{}'
git cat-file -t v0.66.0
```

Require tag object type `tag` and peeled commit exactly equal origin/main. Record PR URL, PR CI run, main CI run, tag object and peeled commit in the durable checkpoint.
