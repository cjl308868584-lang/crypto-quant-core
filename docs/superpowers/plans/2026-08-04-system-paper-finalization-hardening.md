# System Paper Finalization Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 关闭 v0.59 最终审查的 3 Critical / 3 Important，使首次 final、证据捕获、output root 和 loader 具有同一终态信任边界。

**Architecture:** 使用 contract 派生的专用 evaluation root，在 owner-only root lock 下以 contract/start 串行首次 final。post-tail 只保留一次 authority/state/inventory snapshot；语义不可重放但字节稳定的 state 使用 raw-state union 封存 INCONCLUSIVE。Loader 从声明 root dirfd 相对打开并贯穿重放复核 attachment。

**Tech Stack:** Python 3.9 stdlib, `fcntl.flock`, SQLite WAL, retained no-follow descriptors, Decimal fixed Context, JSON Schema 2020-12, canonical JSON/SHA-256, `unittest`.

## Global Constraints

- 工作目录固定为 `/Users/chenm4/Documents/虚拟货币/.worktrees/v0.59-system-paper-evaluation`。
- 分支固定为 `codex/v0.59-system-paper-evaluation`，修复基线为 `c38c30a9408fc3dd3c4c453c37e980a14fe0a1b0`，设计提交为 `97e7d1e`。
- 设计权威：`docs/superpowers/specs/2026-08-04-system-paper-finalization-hardening-design.md`。
- 一个 final fix implementer 顺序完成本计划；每个生产改动必须先 RED、后 GREEN。
- 禁止 production install/start/Runner/scheduler execution/market/Broker/order/credential/state write。
- 不修改 v0.58 plan/runtime/scheduler/deployment 运行语义或 production roots。
- `production_activation.enabled=false` 保持不变。
- package 保持 `0.59.0`；manifest 保持 `1.53.0`，只重新计算 final tree/self hash。
- 修复后必须 Critical 0 / Important 0、full discovery/compileall/build validator/`make validate` 全部有新鲜证据才能创建 PR。

---

### Task 1: Dedicated output root, terminal lock and anchored loader

**Files:**
- Modify: `src/crypto_quant/system_paper_evaluation.py`
- Modify: `tests/test_system_paper_evaluation.py`
- Modify: `config/system-paper-evaluation-v1.schema.json`
- Modify: `src/crypto_quant/schemas/system-paper-evaluation-v1.schema.json`

**Interfaces:**
- Produce: `_expected_evaluation_output_root(contract) -> Path`
- Produce: retained owner-only output-root/file attachment used by publisher and loader.
- Produce: terminal series key derived only from `contract_hash` and `start_receipt_hash`.

- [ ] **Step 1: Add terminal and root-isolation RED tests**

  Add real filesystem tests named:

  ```python
  test_first_inconclusive_terminal_blocks_recovered_second_result
  test_concurrent_finalization_publishes_one_exact_result
  test_output_root_must_equal_contract_derived_sibling
  test_output_root_overlap_with_start_contract_slot_and_state_is_zero_write
  test_loader_rejects_detached_moved_and_unsafe_root_copy
  ```

  The first test must publish INCONCLUSIVE, restore/make complete the same cohort, call the public evaluator again, assert a conflict, and assert exactly one cohort final remains. The overlap table must include start-receipt directory, contract directory, slot root and state directory; every case asserts no new directory entry in the source.

- [ ] **Step 2: Run RED tests**

  Run the five named tests with `PYTHONPATH=src /usr/bin/python3 -m unittest -v ...`.
  Expected failures must reproduce: two final IDs, source-directory pollution, or detached loader acceptance.

- [ ] **Step 3: Implement exact derived root and terminal serialization**

  Derive the only valid root as:

  ```python
  Path(contract["root_paths"]["artifacts"]) / "system-paper-evaluations"
  ```

  Reject any supplied root that differs or aliases/overlaps a retained source. Open/create a single owner-`0600` no-follow lock file under the owner-`0700` root and hold `fcntl.flock(..., LOCK_EX)` across strict existing-final scan, exact publish and post-publish scan. A final with the same `(contract_hash, start_receipt_hash)` is idempotent only when complete canonical bytes match; otherwise raise `SYSTEM_PAPER_EVALUATION_TERMINAL_CONFLICT` without creating a second JSON.

- [ ] **Step 4: Implement anchored loader**

  Require:

  ```python
  evaluation_path == Path(artifact["sources"]["output_root"]) / f"{artifact['result_id']}.json"
  ```

  Retain the declared owner-`0700` root descriptor, open the result relative to that dirfd with no-follow, and reverify root/file attachment after full recomputation. Loader must not create root/lock/result files.

- [ ] **Step 5: Run focused GREEN and publication adjacency**

  Run all Task 1 tests plus existing publication, conflict, unsafe-root, path-replacement and loader-side-effect tests. Require exact `0700/0600`, one final JSON per terminal key and zero source mutation.

- [ ] **Step 6: Commit**

  ```bash
  git add src/crypto_quant/system_paper_evaluation.py tests/test_system_paper_evaluation.py config/system-paper-evaluation-v1.schema.json src/crypto_quant/schemas/system-paper-evaluation-v1.schema.json
  git commit -m "fix: lock system paper cohort finalization"
  ```

### Task 2: Single capture and raw-state INCONCLUSIVE union

**Files:**
- Modify: `src/crypto_quant/system_paper_evaluation.py`
- Modify: `tests/test_system_paper_evaluation.py`
- Modify: `config/system-paper-evaluation-v1.schema.json`
- Modify: `src/crypto_quant/schemas/system-paper-evaluation-v1.schema.json`

**Interfaces:**
- Produce: `state_binding_kind = EVENT_CHAIN_END | RAW_SQLITE_GROUP`.
- Produce: `state_binding_hash`, `event_chain_end_hash_or_null`, `raw_state_group_hash`.
- Consume: retained cohort directory from the first post-tail scan; no error-path recapture.

- [ ] **Step 1: Add single-snapshot and corruption RED tests**

  Add:

  ```python
  test_initial_mismatch_snapshot_cannot_be_recaptured
  test_surface_to_exact_scan_change_is_source_changed
  test_stable_event_state_corruption_publishes_raw_bound_inconclusive
  test_stable_prepared_corruption_publishes_inconclusive
  test_raw_state_binding_changes_result_identity
  test_raw_state_capture_after_change_is_hard_failure
  ```

  The mismatch race deletes one expected artifact for the first scan and restores it before the old catch recapture; expected result is `SOURCE_CHANGED` and zero final. Stable corruption tests keep descriptors/bytes unchanged throughout evaluation and require a loadable final INCONCLUSIVE, not a hard error.

- [ ] **Step 2: Run RED tests**

  Confirm the current code either publishes a born-invalid final or raises `STATE_REPLAY_INVALID`/authority error without final evidence.

- [ ] **Step 3: Retain the first inventory snapshot on every outcome**

  Change `capture_directory` so it stores path, descriptor, directory identity and streaming snapshot before expected-name comparison. Return/raise a structured incomplete result without closing it. Remove the fresh `_inconclusive_inventory` recapture for an existing slot root; derive PRESENT/EMPTY/UNSAFE/mismatch evidence from the retained first snapshot. Missing root must retain its parent plus an absence attachment.

- [ ] **Step 4: Add raw SQLite group binding**

  Compute a canonical group hash from main/WAL/SHM byte hashes or exact absence before semantic replay. After `tail + 5m`, map a stable replay/schema/event/prepared failure to INCONCLUSIVE with:

  ```json
  {
    "state_binding_kind": "RAW_SQLITE_GROUP",
    "state_binding_hash": "<raw group hash>",
    "event_chain_end_hash_or_null": null,
    "raw_state_group_hash": "<same raw group hash>"
  }
  ```

  Replayable state uses `EVENT_CHAIN_END`, the real event hash as `state_binding_hash`, and still records `raw_state_group_hash`. Only post-capture identity/byte changes stay hard failures.

- [ ] **Step 5: Tighten the Schema union and result identity**

  Replace the old unconditional event-chain field with a strict `oneOf` for the two state bindings. Extend the bounded INCONCLUSIVE reason enum for state/prepared replay failures. Result identity must use `state_binding_hash`; PASS/DID_NOT_PASS must require `EVENT_CHAIN_END`.

- [ ] **Step 6: Run focused GREEN and mirror checks**

  Run all new tests, existing state/prepared mutation tests, schema three-state tests, and `cmp -s` for Schema mirrors.

- [ ] **Step 7: Commit**

  ```bash
  git add src/crypto_quant/system_paper_evaluation.py tests/test_system_paper_evaluation.py config/system-paper-evaluation-v1.schema.json src/crypto_quant/schemas/system-paper-evaluation-v1.schema.json
  git commit -m "fix: seal first system paper evidence snapshot"
  ```

### Task 3: Frozen-window count and Decimal context determinism

**Files:**
- Modify: `src/crypto_quant/system_paper_evaluation.py`
- Modify: `tests/test_system_paper_evaluation.py`

**Interfaces:**
- Consume: expected 540 slot IDs derived from strict start receipt.
- Produce: verified count limited to those IDs and a fully fixed Decimal context.

- [ ] **Step 1: Add RED boundary tests**

  Add:

  ```python
  test_541st_success_publishes_loadable_inconclusive
  test_541st_artifact_is_recorded_without_count_inflation
  test_complete_economic_result_ignores_ambient_decimal_context
  ```

  Build a valid 541st scheduler success/artifact after the frozen 540 window. Assert final INCONCLUSIVE, `verified_terminal_slot_count == 540`, extra evidence retained, exact publication and loader equality. Decimal test must compare exact canonical result under at least `ROUND_DOWN` and `ROUND_HALF_EVEN` plus altered Emin/Emax/traps.

- [ ] **Step 2: Run RED tests**

  Confirm the 541st case fails Schema due count 541 and the extreme Decimal probe changes output under ambient context.

- [ ] **Step 3: Implement window-limited count and fixed Context**

  Count successes only for the expected 540-ID set. Keep extra event/artifact evidence in the INCONCLUSIVE inventory. Define one module-level `decimal.Context` with exact precision, rounding, Emin, Emax and traps; use `localcontext(FROZEN_CONTEXT)` for every economic calculation.

- [ ] **Step 4: Run GREEN and adjacent economic boundaries**

  Run new tests plus fee/slippage/aggregate-cost, drawdown, block LCB and 100-repeat determinism tests.

- [ ] **Step 5: Commit**

  ```bash
  git add src/crypto_quant/system_paper_evaluation.py tests/test_system_paper_evaluation.py
  git commit -m "fix: freeze system paper evaluation window"
  ```

### Task 4: Audit metadata, build identity and truthful docs

**Files:**
- Modify: `docs/superpowers/specs/2026-08-04-system-paper-fixed-tail-evaluation-design.md`
- Modify: `docs/superpowers/plans/2026-08-04-system-paper-fixed-tail-evaluation.md`
- Modify: `docs/adr/0059-system-paper-fixed-tail-evaluation.md`
- Modify: `docs/implementation-status-v0.59.0.md`
- Modify: `README.md`
- Modify: `src/crypto_quant/build.py`
- Modify: `tests/test_estimators.py`
- Modify: `tests/test_system_paper_evaluation_cli.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `scripts/refresh_evaluator_build_manifest.py`

**Interfaces:**
- Consume: final source/Schema/test bytes from Tasks 1-3.
- Produce: build `1.53.0`, package `0.59.0`, refreshed exact hashes.

- [ ] **Step 1: Add RED build and mirror assertions**

  Add both new hardening design/plan paths to expected build inputs. Add semantic equality assertions across `pyproject.toml`, `setup.py` and `crypto_quant.__version__`. Change the CLI import regression to compare `sys.modules` before/after bare import while retaining the explicit forbidden-prefix list.

- [ ] **Step 2: Update design/plan/docs truthfully**

  Amend the original design sections 8-9 with terminal key, raw state binding and dedicated root. Add `scripts/refresh_evaluator_build_manifest.py` to the original Task 6 file list. ADR/status/README must state the finalization gaps were found before release and fixed; they must not claim installation, a started cohort, profitability, AI advantage, Canary or live eligibility.

- [ ] **Step 3: Run RED build tests, then update tracked inputs**

  Run `tests.test_estimators`; expect file-set mismatch until `src/crypto_quant/build.py` includes the new design/plan and all changed v0.59 files.

- [ ] **Step 4: Refresh manifest once after inputs settle**

  Keep package `0.59.0` and manifest `1.53.0`. Run:

  ```bash
  PYTHONPATH=src /usr/bin/python3 scripts/refresh_evaluator_build_manifest.py
  PYTHONPATH=src /usr/bin/python3 scripts/validate_evaluator_build.py
  ```

  Record new input count, tree hash and self-hash in the implementation report.

- [ ] **Step 5: Run focused build/CLI/Schema checks**

  Run estimator tests, CLI tests, both Schema JSON validation and byte comparison, compileall and `git diff --check`.

- [ ] **Step 6: Commit**

  ```bash
  git add docs README.md src/crypto_quant/build.py tests/test_estimators.py tests/test_system_paper_evaluation_cli.py config/evaluator-build-manifest-v1.json scripts/refresh_evaluator_build_manifest.py
  git commit -m "release: harden system paper evaluation v0.59.0"
  ```

### Task 5: Final fix-wave verification and handoff

**Files:**
- Create ignored report: `.superpowers/sdd/2026-08-04-system-paper-finalization-hardening/final-fix-report.md`

- [ ] **Step 1: Self-review every final-review finding**

  The report must map all 3 Critical / 3 Important to a named RED test, fix commit and GREEN output. It must separately list the shared publisher partial-target Minor as deferred and prove no source/production path was written.

- [ ] **Step 2: Run focused and adjacent suites**

  Run all System Paper evaluator/CLI/evidence/start-receipt tests and build tests.

- [ ] **Step 3: Run full local release verification**

  ```bash
  PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -q
  PYTHONPYCACHEPREFIX=/private/tmp/crypto-quant-v059-pycache PYTHONPATH=src /usr/bin/python3 -m compileall -q src tests scripts
  PYTHONPATH=src /usr/bin/python3 scripts/validate_evaluator_build.py
  make validate
  git diff --check v0.58.0...HEAD
  git status --short
  ```

- [ ] **Step 4: Preserve production absence evidence**

  Read-only checks must still show the System Paper runtime root and plist absent and `gui/501/local.crypto-quant.system-paper-v1` not loaded. Do not install or start them.

- [ ] **Step 5: Return fix-wave report**

  Return `DONE` only when all commands have explicit exit/result evidence, worktree is clean and no Critical/Important concern remains. Do not push, create PR or tag; controller owns re-review and release workflow.

## Plan Self-Review

- Hardening design sections 2-9 each map to a task and a named behavior test.
- The plan does not change seven-path CLI authority, v0.58 runtime/scheduler semantics or production roots.
- Terminal uniqueness is independent of mutable inventory; result identity remains evidence-specific.
- Initial stable corruption and capture-after mutation remain distinct outcomes.
- Loader attachment and output-root isolation use retained no-follow identities, not string comparison alone.
- Package/manifest semantic versions do not increment again; only exact hashes refresh.
- No placeholders, future implementation deferrals or production activation steps remain.
