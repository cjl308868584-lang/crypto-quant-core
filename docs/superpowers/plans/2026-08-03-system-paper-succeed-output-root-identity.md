# System Paper `succeed` Output Root Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind the runner's retained output-root `(st_dev, st_ino)` through `SystemPaperScheduleState.succeed()` so a same-path replacement can never produce a false `SUCCEEDED` event.

**Architecture:** Keep `_ValidatedRunnerOutputRoot` as the invocation authority and pass its identity through a required keyword-only state-layer contract. The state transaction validates that identity while reading the exact artifact and again immediately before commit; every mismatch fails closed and rolls back.

**Tech Stack:** Python 3.9+, SQLite WAL, `os.open`/`fstat`/`O_NOFOLLOW`, `unittest`, repository canonical JSON and build-manifest tooling.

## Global Constraints

- Target remains `v0.57.0` on `codex/v0.57-system-paper-scheduler`.
- Do not install, start, bootstrap, kickstart, or manually invoke System Paper or Challenger services.
- Do not add market requests, credential reads, Broker calls, account calls, or real/simulated runtime behavior.
- Preserve `production_activation.enabled=false` and all fixed zero safety counters.
- The only trusted output-root identity is `_ValidatedRunnerOutputRoot.identity` from the current invocation.
- Identity is a required two-positive-integer tuple; `bool` values are invalid.
- Output-root identity mismatch, disappearance, symlink replacement, or unsafe replacement must roll back with `SYSTEM_PAPER_SCHEDULE_OUTPUT_ROOT_RACE`.
- No push, PR, merge, or tag until focused, adjacent, full, compileall, build-manifest, `make validate`, and independent review gates pass.

---

### Task 1: Freeze the failing root-replacement regressions

**Files:**
- Modify: `tests/test_system_paper_scheduler.py:1034-1050`
- Modify: `tests/test_system_paper_scheduler.py:2113-2180`

**Interfaces:**
- Consumes: `SystemPaperScheduleState.succeed(...)`, `run_due_system_paper_slot(...)`, `RecordingProvider`, existing `prepare_slot()` and `write_result_artifact()` helpers.
- Produces: deterministic red tests for a wrong trusted identity, replacement before state-layer verification, and replacement during `before_commit`.

- [ ] **Step 1: Update the existing direct success call to supply the real root identity**

Open the owner-only output root with `os.stat(..., follow_symlinks=False)` and pass:

```python
root_stat = os.stat(self.output_root, follow_symlinks=False)
self.state.succeed(
    claim,
    artifact_path=artifact,
    expected_output_root_identity=(root_stat.st_dev, root_stat.st_ino),
    completed_at=claim.lease_expires_at,
)
```

This preserves the existing exact-lease-expiry assertion while adapting the intended API caller.

- [ ] **Step 2: Add a direct wrong-identity failure test**

Prepare one result and artifact with the existing helpers, create another owner-only directory,
use that directory's real identity as the wrong identity, snapshot events, then call:

```python
with self.assertRaisesRegex(
    SystemPaperScheduleError,
    "SYSTEM_PAPER_SCHEDULE_OUTPUT_ROOT_RACE",
):
    self.state.succeed(
        claim,
        artifact_path=artifact,
        expected_output_root_identity=other_identity,
        completed_at=claim.claimed_at,
    )
self.assertEqual(self.state.events(), events_before)
```

Also assert the artifact bytes/inode and prepared result row are unchanged.

- [ ] **Step 3: Add strict malformed-identity tests**

For `None`, `(1,)`, `(True, 2)`, `(0, 2)`, `[-1, 2]`, and `("1", 2)`, call the direct
`succeed()` API and require `SYSTEM_PAPER_SCHEDULE_OUTPUT_ROOT_IDENTITY_INVALID`. Snapshot
events and prepared rows before the loop and require exact equality after every case.

- [ ] **Step 4: Add the exact runner-to-state component-boundary replacement test**

Patch `SystemPaperScheduleState.succeed` with a wrapper that runs after the runner's last external validation, renames the original root to a backup, creates a new owner-only root and slots directory at the same path, copies the exact original artifact bytes into a new `0600` file, and calls the real method with unchanged kwargs:

```python
real_succeed = scheduler_module.SystemPaperScheduleState.succeed

def swapping_succeed(state, claim, **kwargs):
    self.output_root.rename(backup)
    self.output_root.mkdir(mode=0o700)
    replacement_slots = self.output_root / "system-paper-slots"
    replacement_slots.mkdir(mode=0o700)
    source = backup / "system-paper-slots" / (claim.slot.slot_id + ".json")
    replacement = replacement_slots / source.name
    replacement.write_bytes(source.read_bytes())
    os.chmod(replacement, 0o600)
    return real_succeed(state, claim, **kwargs)
```

Require `SYSTEM_PAPER_SCHEDULE_OUTPUT_ROOT_RACE`, no `SUCCEEDED` event, exact prepared result persistence, and no mutation of the artifact under the retained backup root.

- [ ] **Step 5: Add replacement-during-commit failure test**

Use a direct prepared claim/result/artifact and call `succeed(..., before_commit=swap_root)` where `swap_root` renames the original root and creates a safe empty replacement at the old path. Require the fixed race reason and transaction rollback; the event chain must end at `RESULT_PREPARED`.

- [ ] **Step 6: Run the red tests**

Run:

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_system_paper_scheduler.SystemPaperPreparedResultTests.test_succeed_rejects_wrong_expected_output_root_identity \
  tests.test_system_paper_scheduler.SystemPaperPreparedResultTests.test_succeed_rejects_malformed_expected_output_root_identity \
  tests.test_system_paper_scheduler.SystemPaperScheduleRunnerTests.test_output_root_replacement_between_runner_validation_and_succeed_fails_closed \
  tests.test_system_paper_scheduler.SystemPaperPreparedResultTests.test_succeed_rejects_output_root_replacement_before_commit -v
```

Expected: all four fail because the production method does not yet accept or enforce the trusted identity.

- [ ] **Step 7: Commit the red tests**

```bash
git add tests/test_system_paper_scheduler.py
git commit -m "test: reproduce system paper succeed root race"
```

---

### Task 2: Carry and enforce retained root identity inside `succeed`

**Files:**
- Modify: `src/crypto_quant/system_paper_scheduler.py:347-535`
- Modify: `src/crypto_quant/system_paper_scheduler.py:2003-2070`
- Modify: `src/crypto_quant/system_paper_scheduler.py:2320-2332`

**Interfaces:**
- Consumes: `_ValidatedRunnerOutputRoot.identity`, output-root pathname, prepared result exact bytes and SHA-256.
- Produces: required `expected_output_root_identity: Tuple[int, int]` on `succeed()`, identity-aware `_artifact_body()`, and transactional pathname attachment validation.

- [ ] **Step 1: Add strict identity input validation**

Add a private helper:

```python
def _expected_output_root_identity(value: object) -> Tuple[int, int]:
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or any(
            not isinstance(part, int) or isinstance(part, bool) or part <= 0
            for part in value
        )
    ):
        raise SystemPaperScheduleError(
            "SYSTEM_PAPER_SCHEDULE_OUTPUT_ROOT_IDENTITY_INVALID"
        )
    return value
```

- [ ] **Step 2: Add a reusable pathname-attachment validator**

Implement `_validate_output_root_attachment(output_root, expected_identity)` using an absolute, non-symlink path, `O_DIRECTORY | O_NOFOLLOW`, `os.fstat`, `_owner_safe_directory_stat`, and a second `os.stat(..., follow_symlinks=False)`. Require both opened and current `(st_dev, st_ino)` values to equal the validated expected identity. Map any path, safety, or identity failure to `SYSTEM_PAPER_SCHEDULE_OUTPUT_ROOT_RACE` and always close the descriptor.

- [ ] **Step 3: Bind `_artifact_body()` to the expected identity**

Change the signature to:

```python
def _artifact_body(
    output_root: Path,
    slot: SystemPaperSlot,
    *,
    expected_output_root_identity: Optional[Tuple[int, int]] = None,
    expected_bytes: bytes,
    expected_sha256: str,
) -> bytes:
```

When the optional identity is present, validate it before opening the root. Immediately after
`root_stat = os.fstat(root_fd)`, require its identity to equal that value. After the current artifact
identity check, call `_validate_output_root_attachment(output_root, expected_identity)`. Existing
parent-chain and read-only replay call sites omit the optional argument; the `succeed()` call must
provide it.

- [ ] **Step 4: Make the state-layer contract required and transactional**

Add `expected_output_root_identity: Tuple[int, int]` as a required keyword-only argument to `SystemPaperScheduleState.succeed()`. Validate it before `_transaction()`, pass it into `_artifact_body()`, call `_validate_output_root_attachment()` after artifact verification, append and verify `SUCCEEDED`, run the existing `before_commit`, call `_validate_output_root_attachment()` one final time, then commit. Existing `except` rollback behavior remains the only failure exit.

- [ ] **Step 5: Pass the retained identity from the runner**

Change the only production call to:

```python
state.succeed(
    claim,
    artifact_path=result_path,
    expected_output_root_identity=root_handle.identity,
    completed_at=sampled_at,
    before_commit=lambda: injector.maybe_raise("BEFORE_SUCCESS_COMMIT"),
)
```

- [ ] **Step 6: Run the focused tests and confirm green**

Run the exact four-test command from Task 1, then:

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_system_paper_scheduler -v
```

Expected: focused tests pass and the complete scheduler module passes.

- [ ] **Step 7: Run adjacent scheduler and artifact suites**

Run:

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_system_paper_scheduler \
  tests.test_system_paper_fault_injection \
  tests.test_system_paper_runtime \
  tests.test_market_data_cli -v
```

Expected: all pass with no new network, Broker, order, account, or credential activity.

- [ ] **Step 8: Commit the minimal production fix**

```bash
git add src/crypto_quant/system_paper_scheduler.py tests/test_system_paper_scheduler.py
git commit -m "fix: bind system paper succeed to retained output root"
```

---

### Task 3: Close the release gate and rebuild exact repository identity

**Files:**
- Modify: `.superpowers/sdd/2026-08-02-system-paper-wal-scheduler/progress.md`
- Modify: `docs/implementation-status-v0.57.0.md`
- Modify: `config/evaluator-build-manifest-v1.json`

**Interfaces:**
- Consumes: green Task 2 code and tests, frozen v0.57 build-input enumeration.
- Produces: accurate release status, refreshed manifest bytes, independent review evidence, and a clean publishable branch.

- [ ] **Step 1: Independently review the scoped repair**

Review `bc88ba8..HEAD` against the frozen 2026-08-03 design. Confirm all three deterministic race probes fail closed, no caller can omit the identity, no state transaction can commit after `before_commit` replaces the root, and no new Critical or Important finding remains. Record exact review result in the SDD ledger.

- [ ] **Step 2: Update implementation evidence**

Record the focused and adjacent test counts, review result, and the fact that I3 is addressed in `docs/implementation-status-v0.57.0.md`. Do not claim PR, CI, merge, tag, installation, Paper start, profitability, or 90-day evidence before those events occur.

- [ ] **Step 3: Refresh the exact build manifest**

Run:

```bash
PYTHONPATH=src:tests python3 scripts/refresh_evaluator_build_manifest.py
PYTHONPATH=src:tests python3 scripts/validate_evaluator_build.py
```

Expected: refresh succeeds and validation reports the exact current input set/tree/manifest hashes as valid.

- [ ] **Step 4: Run repository-wide verification**

Run:

```bash
PYTHONPATH=src:tests python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests scripts
PYTHONPATH=src:tests python3 scripts/validate_evaluator_build.py
make validate
git diff --check
git status --short
```

Expected: unit tests and compileall pass; build manifest passes; `make validate` produces its documented research fail-closed result only if the existing production-activation gate intentionally remains false; diff check is clean and status lists only intended evidence/manifest changes before commit.

- [ ] **Step 5: Commit exact release evidence**

```bash
git add .superpowers/sdd/2026-08-02-system-paper-wal-scheduler/progress.md \
  docs/implementation-status-v0.57.0.md config/evaluator-build-manifest-v1.json
git commit -m "release: close system paper scheduler review gate"
```

- [ ] **Step 6: Re-run immutable post-commit verification**

Run the full test, compileall, manifest validation, `make validate`, `git diff --check`, and clean-status commands again against the committed tree. Record exact HEAD, manifest version, input count, tree hash, manifest hash, and test count before any GitHub write.

- [ ] **Step 7: Verify GitHub authority and publish only the branch**

Confirm the connected account can see private repository `cjl308868584-lang/crypto-quant-core`, permission is ADMIN with push/pull, `origin` matches that repository, remote `main` equals the expected v0.56 base, the branch contains that base, and `v0.57.0` is absent. Then push `codex/v0.57-system-paper-scheduler` and create Draft PR `release: crash-safe System Paper scheduler v0.57.0` with exact review and verification evidence.

- [ ] **Step 8: Complete CI-controlled integration**

Wait for Python 3.9 and 3.12 PR CI, mark the reviewed head ready, merge only that head, wait for main CI, then create an annotated `v0.57.0` at the exact merged `origin/main` SHA. Push the tag and verify the peeled annotated tag equals remote main. Stop without installation or runtime start.
