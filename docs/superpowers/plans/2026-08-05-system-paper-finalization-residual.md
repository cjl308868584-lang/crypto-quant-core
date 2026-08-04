# System Paper Finalization Residual Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two remaining v0.59 combined-state release blockers without adding a mutable lock namespace or changing the evaluator's read-only production boundary.

**Architecture:** Serialize first-final publication by locking the already retained output-root directory inode, so pathname replacement cannot split the lock domain. In the post-tail reader, decide whether the retained SQLite group is semantically replayable before classifying its single retained slot-inventory capture; only the exact prepared-replay failure maps to raw-bound INCONCLUSIVE.

**Tech Stack:** Python 3.9 stdlib, `fcntl.flock`, retained directory/file descriptors, SQLite WAL snapshots, canonical JSON/SHA-256, JSON Schema 2020-12, `unittest`.

## Global Constraints

- Work only in `/Users/chenm4/Documents/虚拟货币/.worktrees/v0.59-system-paper-evaluation` on `codex/v0.59-system-paper-evaluation`.
- Implementation base is `5ca21287220ab92cb2f29713377d24b72c7dc777` and frozen design is `docs/superpowers/specs/2026-08-05-system-paper-finalization-residual-design.md`.
- Remote `origin/main` and annotated `v0.58.0` must remain peeled to `35a810622fc0449f2131ccbb806354b48deac15d` until the release workflow.
- Keep package version `0.59.0`, evaluator manifest version `1.53.0`, and `production_activation.enabled=false`.
- Every production-code behavior change requires a named real-behavior RED test observed failing for the intended reason before implementation.
- No install/start/bootstrap/kickstart/Runner/scheduler/maintenance, market request, Broker, order, credential, balance or production-state write.
- Do not redesign the shared exact publisher's deferred partial-target behavior in this plan.
- Do not push, open a PR, merge or tag until all task reviews, broad review and fresh controller verification are complete.

---

### Task 1: Lock the retained output-root directory inode

**Files:**
- Modify: `src/crypto_quant/system_paper_evaluation.py`
- Modify: `tests/test_system_paper_evaluation.py`

**Interfaces:**
- Consume: `_RetainedOutputRoot.descriptor`, `.entry`, `.verify()` and `.close()`.
- Produce: `_RetainedOutputRoot.locked: bool` and directory-descriptor `acquire_lock()` lifecycle.
- Preserve: `_publish_terminal_final()` holds one lock across existing scan, decision, publish, post-scan and final verification.

- [ ] **Step 1: Add the two lock-domain RED tests**

  Add tests with these exact names:

  ```python
  def test_directory_inode_lock_survives_former_lock_path_replacement(self):
      # Open two retained roots for the same directory.  Hold the first
      # directory lock, create/replace the former .lock filename, and prove
      # the second acquire callback cannot run until the first root closes.

  def test_former_lock_path_race_never_publishes_two_finals(self):
      # Race two distinct schema-valid candidates while the former pathname
      # is renamed/recreated.  Assert <= 1 result JSON and never two winners.
  ```

  Use `threading.Event`/`Barrier` and `ThreadPoolExecutor`; do not mock
  `fcntl.flock`. Count only `system_paper_evaluation_*.json` as final results.
  The second test may accept one winner plus terminal conflict or a fail-closed
  result/output conflict, but it must reject two mapping results and two JSON
  files.

- [ ] **Step 2: Run the named tests and preserve RED output**

  Run:

  ```bash
  PYTHONPATH=src /usr/bin/python3 -m unittest -v \
    tests.test_system_paper_evaluation.SystemPaperEvaluationAuthorityTests.test_directory_inode_lock_survives_former_lock_path_replacement \
    tests.test_system_paper_evaluation.SystemPaperEvaluationAuthorityTests.test_former_lock_path_race_never_publishes_two_finals
  ```

  Expected: the second acquisition enters while the first file-inode lock is
  still held, or the full race publishes two different final JSON files.

- [ ] **Step 3: Replace child-file locking with directory-inode locking**

  Change `_RetainedOutputRoot` to this lifecycle:

  ```python
  def __init__(self, path, descriptor, entry):
      self.path = path
      self.descriptor = descriptor
      self.entry = entry
      self.files = []
      self.locked = False

  def acquire_lock(self):
      if self.locked:
          raise SystemPaperEvaluationError(
              "SYSTEM_PAPER_EVALUATION_OUTPUT_INVALID"
          )
      try:
          fcntl.flock(self.descriptor, fcntl.LOCK_EX)
          self.verify()
          self.locked = True
      except Exception as error:
          try:
              fcntl.flock(self.descriptor, fcntl.LOCK_UN)
          except OSError:
              pass
          raise SystemPaperEvaluationError(
              "SYSTEM_PAPER_EVALUATION_OUTPUT_INVALID"
          ) from error
  ```

  In `close()`, release `LOCK_UN` on `self.descriptor` when `locked`, then close
  the directory descriptor. Remove `_LOCK_NAME`, `lock_descriptor`, all child
  lock opens and all lock-file inventory exemptions. Do not create or unlink a
  lock file.

- [ ] **Step 4: Run GREEN plus adjacency**

  Run the two named tests plus existing terminal concurrency/idempotency,
  output-root replacement, unexpected inventory and loader attachment tests.
  Require one lock domain, no lock child entry and no duplicate final.

- [ ] **Step 5: Commit Task 1**

  ```bash
  git add src/crypto_quant/system_paper_evaluation.py \
    tests/test_system_paper_evaluation.py
  git commit -m "fix: anchor system paper finalization lock"
  ```

### Task 2: Decide state binding before inventory completeness

**Files:**
- Modify: `src/crypto_quant/system_paper_evaluation.py`
- Modify: `tests/test_system_paper_evaluation.py`

**Interfaces:**
- Produce: `_post_tail_prepared_replay(...) -> Tuple[Optional[Mapping[str, Any]], Optional[str]]`.
- Consume: retained raw SQLite group, strict full start-receipt loader and the existing single retained inventory helpers.
- Preserve: pre-tail path never invokes full prepared replay or slot inventory capture.

- [ ] **Step 1: Add the five binding-precedence RED tests**

  Add these exact tests:

  ```python
  test_stable_prepared_corruption_with_empty_inventory_is_raw_bound
  test_stable_prepared_corruption_with_missing_inventory_is_raw_bound
  test_stable_prepared_corruption_with_unsafe_inventory_is_raw_bound
  test_authority_tamper_with_empty_inventory_remains_hard_failure
  test_prepared_capture_after_change_with_empty_inventory_is_source_changed
  ```

  For the first three, corrupt a prepared row, create the requested slot-root
  surface, call the public evaluator after tail, load the exact result and
  assert:

  ```python
  artifact["sources"]["state_binding_kind"] == "RAW_SQLITE_GROUP"
  artifact["sources"]["event_chain_end_hash_or_null"] is None
  artifact["reason_code_or_null"] == (
      "SYSTEM_PAPER_EVALUATION_PREPARED_REPLAY_INVALID"
  )
  artifact["evidence_inventory"]["inventory_state"] == expected_state
  ```

  The authority and capture-after tests assert the exact hard reason and zero
  `system_paper_evaluation_*.json` files.

- [ ] **Step 2: Run the five named tests and preserve RED output**

  Run only the five tests. Expected baseline failures: prepared corruption with
  incomplete inventory publishes `EVENT_CHAIN_END` plus
  `COHORT_INCOMPLETE`, or capture-after mutation is misclassified.

- [ ] **Step 3: Implement the exact prepared-replay classifier**

  Import `SystemPaperObserverError` and add a helper that calls
  `load_system_paper_start_receipt(...)`. Its exception contract is exact:

  ```python
  except SystemPaperStartReceiptError as error:
      cause = error.__cause__
      if (
          error.reason_code == "SYSTEM_PAPER_START_RECEIPT_SOURCE_CHANGED"
          and isinstance(cause, SystemPaperObserverError)
          and cause.reason_code
          == "SYSTEM_PAPER_OBSERVER_FIRST_SLOT_REPLAY_INVALID"
      ):
          retained.verify()
          state_retained.verify()
          return None, (
              "SYSTEM_PAPER_EVALUATION_PREPARED_REPLAY_INVALID"
          )
      raise SystemPaperEvaluationError(
          "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
      ) from error
  ```

  On success, require `replayed_start == start`; otherwise raise authority
  invalid. Do not use `except Exception` for the raw fallback.

- [ ] **Step 4: Reorder only the post-tail decision flow**

  After event replay and after the tail gate:

  1. call `_post_tail_prepared_replay()`;
  2. capture `surface_state`/inventory once;
  3. if prepared replay returned its reason, build raw-bound INCONCLUSIVE from
     that retained inventory;
  4. otherwise, if surface is not `PRESENT`, build event-chain-bound
     `COHORT_INCOMPLETE`; and
  5. otherwise continue exact cohort replay.

  Preserve all `retained.verify()`, `state_retained.verify()` and
  `cohort_retained.verify()` checks. A source changing after raw capture remains
  `SOURCE_CHANGED` and never publishes.

- [ ] **Step 5: Run GREEN plus the precedence matrix**

  Run the five new tests and existing tests covering: pre-tail blindness,
  stable event corruption, prepared corruption with present inventory, wrong
  first receipt, replayable empty/missing/unsafe inventory, source mutation,
  exact 540 and 541st slot. Require every new raw artifact to reload exactly.

- [ ] **Step 6: Commit Task 2**

  ```bash
  git add src/crypto_quant/system_paper_evaluation.py \
    tests/test_system_paper_evaluation.py
  git commit -m "fix: prioritize system paper raw state binding"
  ```

### Task 3: Bind the residual design into release metadata

**Files:**
- Modify: `docs/superpowers/specs/2026-08-04-system-paper-fixed-tail-evaluation-design.md`
- Modify: `docs/adr/0059-system-paper-fixed-tail-evaluation.md`
- Modify: `docs/implementation-status-v0.59.0.md`
- Modify: `README.md`
- Modify: `src/crypto_quant/build.py`
- Modify: `tests/test_estimators.py`
- Modify: `config/evaluator-build-manifest-v1.json`

**Interfaces:**
- Consume: settled Task 1/2 source and tests plus both 2026-08-05 residual documents.
- Produce: exact build input count/tree/self hashes under manifest `1.53.0` and package `0.59.0`.

- [ ] **Step 1: Add the build-input RED assertion**

  Extend the evaluator input test with both exact paths:

  ```python
  docs/superpowers/specs/2026-08-05-system-paper-finalization-residual-design.md
  docs/superpowers/plans/2026-08-05-system-paper-finalization-residual.md
  ```

  Run `PYTHONPATH=src /usr/bin/python3 -m unittest -v tests.test_estimators`.
  Expected RED: at least one residual document is missing from the frozen build
  input set.

- [ ] **Step 2: Update truthful release documentation**

  Document that directory-inode locking and binding-first post-tail ordering
  close the scoped re-review findings before release. Keep all statements
  credential-free and non-production. Do not claim cohort start, Paper result,
  profitability, AI advantage, Canary or live eligibility.

- [ ] **Step 3: Update build inputs and refresh once**

  Add all new/changed tracked v0.59 files to `src/crypto_quant/build.py` without
  removing prior inputs. Then run:

  ```bash
  PYTHONPATH=src /usr/bin/python3 scripts/refresh_evaluator_build_manifest.py
  PYTHONPATH=src /usr/bin/python3 scripts/validate_evaluator_build.py
  ```

  Keep manifest `1.53.0` and package `0.59.0`; record input count, tree hash and
  self-hash in the task report.

- [ ] **Step 4: Run Task 3 GREEN and static gates**

  Run estimator and evaluator CLI tests, both Schema JSON parsers and byte
  comparison, compileall and `git diff --check v0.58.0...HEAD`.

- [ ] **Step 5: Commit Task 3**

  ```bash
  git add README.md docs src/crypto_quant/build.py \
    tests/test_estimators.py config/evaluator-build-manifest-v1.json
  git commit -m "release: bind system paper residual hardening"
  ```

### Task 4: Final verification and review handoff

**Files:**
- Create ignored report: `.superpowers/sdd/2026-08-05-system-paper-finalization-residual/final-report.md`

**Interfaces:**
- Consume: reviewed Tasks 1-3 and final manifest bytes.
- Produce: evidence for the independent whole-branch reviewer and controller.

- [ ] **Step 1: Run focused release suites**

  ```bash
  PYTHONPATH=src /usr/bin/python3 -m unittest -q \
    tests.test_system_paper_evaluation \
    tests.test_system_paper_evaluation_cli \
    tests.test_system_paper_evidence \
    tests.test_system_paper_start_receipt \
    tests.test_estimators
  ```

- [ ] **Step 2: Run full local verification**

  ```bash
  PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -q
  PYTHONPYCACHEPREFIX=/private/tmp/crypto-quant-v059-residual-pycache \
    PYTHONPATH=src /usr/bin/python3 -m compileall -q src tests scripts
  PYTHONPATH=src /usr/bin/python3 scripts/validate_evaluator_build.py
  make validate
  git diff --check v0.58.0...HEAD
  git status --short
  ```

- [ ] **Step 3: Preserve production-absence evidence**

  Read-only checks must show absent System Paper runtime root/plist and
  `gui/501/local.crypto-quant.system-paper-v1` not loaded. Do not install or
  start anything.

- [ ] **Step 4: Write the final report**

  Map both residual findings to named RED, fix commit and GREEN output. Include
  focused/full counts, build hashes, production absence and any deferred Minor.
  Return `DONE` only with a clean worktree and no known Critical/Important.

## Plan Self-Review

- Design sections 3-10 each map to a task and named evidence.
- Directory locking never creates, opens, excludes or removes a child lock
  entry.
- Prepared replay precedes inventory outcome only after the tail; pre-tail
  blindness remains unchanged.
- Authority tamper, initially stable corruption and capture-after mutation have
  distinct explicit outcomes.
- No task changes shared publisher semantics, production roots or runtime state.
- Package/manifest versions remain `0.59.0`/`1.53.0`; only exact hashes refresh.
- Every implementation and verification step has an exact command or outcome.
