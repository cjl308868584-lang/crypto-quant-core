# System Paper Fixed-Tail Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:executing-plans` and TDD task by task.

**Goal:** 发布一个尾部前不读经济数据、尾部后只从完整540槽可重放证据自动派生唯一结果的 v0.59 evaluator。

**Architecture:** 以 v0.58 production loaders 为来源信任根；先对 install receipt 做有界预览以派生 plist/preflight 路径，随后完整复核所有来源。尾部前只复核 scheduler event metadata；尾部后保留 production descriptors、拷贝 SQLite/WAL 到 `/private/tmp`、重放540槽的 event/prepared/artifact/runtime 链，然后计算冻结安全和经济门。只有最终状态创建 owner-only immutable artifact。

**Tech stack:** Python 3.9 stdlib, `Decimal`, SQLite WAL, `jsonschema`, canonical JSON/SHA-256, `unittest`.

## Global constraints

- 工作目录固定为 `/Users/chenm4/Documents/虚拟货币/.worktrees/v0.59-system-paper-evaluation`。
- 分支固定为 `codex/v0.59-system-paper-evaluation`，基线为 `v0.58.0^{}` = `35a810622fc0449f2131ccbb806354b48deac15d`。
- 设计权威：`docs/superpowers/specs/2026-08-04-system-paper-fixed-tail-evaluation-design.md`。
- 每个代码任务必须先红灯、后最小实现、再聚焦/相邻验证和独立提交。
- 禁止生产 install/start/Runner/scheduler/market/Broker/order/credential/state write。
- 不修改 v0.58 plan/runtime/scheduler/deployment 语义或 production roots。
- `production_activation.enabled=false` 保持不变。
- 在本地全量、独立审查、PR CI、main CI 通过前不创建 `v0.59.0` tag。

---

### Task 1: Strict authority derivation and pre-tail blindness

**Files:**
- Create: `src/crypto_quant/system_paper_evaluation.py`
- Create: `tests/test_system_paper_evaluation.py`

**Interfaces:**
- `observe_system_paper_evaluation_readiness(...) -> Mapping[str, Any]`
- Internal bounded install preview derives only plist and preflight paths before strict loaders.
- Internal retained source set holds plan/contract/plist/preflight/install/start through return.

- [ ] Write red tests for exactly seven absolute paths, bounded/canonical install preview, wrong derived path, source replacement and root mismatch.
- [ ] Write red pre-tail test that patches slot loader/economic accumulator/output publisher to raise; observation must still succeed without calling them.
- [ ] Implement strict v0.58 loader chain and exact runtime/slot-root comparison.
- [ ] Capture SQLite main/WAL/SHM with retained descriptors and replay only a `/private/tmp` copy.
- [ ] Return only the frozen pre-tail allowlist and no output root.
- [ ] Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_system_paper_evaluation.SystemPaperEvaluationAuthorityTests -v
```

- [ ] Commit: `feat: add tail-blind system paper evaluation authority`.

### Task 2: Exact 540-slot continuity and artifact replay

**Files:**
- Modify: `src/crypto_quant/system_paper_evaluation.py`
- Modify: `tests/test_system_paper_evaluation.py`

**Interfaces:**
- `_replay_system_paper_cohort(...)` returns an immutable ordered cohort only after the `tail + 5m` gate.

- [ ] Build a fixture factory for 540 deterministic slot artifacts and scheduler events without production I/O.
- [ ] Add red tests for missing/extra/duplicate artifacts, failed/missed/expired/nonterminal slots, wrong first receipt, broken 4h cadence and parent mismatch.
- [ ] Add red coordinated-mutation tests for event hash, prepared input/result, artifact bytes, snapshot prefix and output-root identity.
- [ ] Implement exact expected slot derivation from start receipt and plan hash.
- [ ] Require exact directory inventory, owner `0600`, one link, no symlink and stable descriptor identity.
- [ ] Replay every production slot loader and deterministic slot result; retain all artifact descriptors through final comparison.
- [ ] Run focused plus scheduler/runtime adjacency.
- [ ] Commit: `feat: replay complete system paper cohort evidence`.

### Task 3: Frozen safety, cost, drawdown and 30-day gates

**Files:**
- Modify: `src/crypto_quant/system_paper_evaluation.py`
- Modify: `tests/test_system_paper_evaluation.py`

**Interfaces:**
- `_evaluate_complete_system_paper_cohort(...) -> Mapping[str, Any]` uses Decimal only.

- [ ] Add red pass/fail tests for duplicate orders, unrecorded fills, hard-risk violations, risk increase during open reconciliation, final active order, traceability and replay.
- [ ] Add red cost tests for fee `0.0015`, slippage `0.001` and aggregate modeled cost `0.0025` boundaries.
- [ ] Add red maximum drawdown tests immediately below/equal/above `0.10`.
- [ ] Add red deterministic three-block Student-t LCB tests below/equal/above zero and 100-repeat equality.
- [ ] Implement Decimal accumulators, fixed `2.91998558035372` constant and three exact 180-slot blocks.
- [ ] Separate incomplete evidence from complete evidence that fails a gate.
- [ ] Run focused tests and compileall.
- [ ] Commit: `feat: evaluate frozen system paper research gates`.

### Task 4: Immutable final artifact, Schema and production loader

**Files:**
- Create: `config/system-paper-evaluation-v1.schema.json`
- Create: `src/crypto_quant/schemas/system-paper-evaluation-v1.schema.json`
- Modify: `src/crypto_quant/system_paper_evaluation.py`
- Modify: `tests/test_system_paper_evaluation.py`

**Interfaces:**
- `evaluate_system_paper(...) -> Mapping[str, Any]`
- `load_system_paper_evaluation(...) -> Mapping[str, Any]`

- [ ] Add red Schema tests for PASS/DID_NOT_PASS/INCONCLUSIVE and rejection of floats, unknown fields, malformed gates and claim inflation.
- [ ] Add red no-overwrite/idempotency, same-id conflict, unsafe root/file, over-limit pre-read and pathname replacement tests.
- [ ] Implement stable result id from contract/start/event-chain/inventory hashes.
- [ ] Publish only final states with `publish_owner_exact`; pending remains zero-write.
- [ ] Loader must replay exact original inputs and compare the complete artifact, not self-hash only.
- [ ] Mirror Schema byte-for-byte and run focused tests.
- [ ] Commit: `feat: seal system paper fixed-tail evaluation`.

### Task 5: Fixed seven-path CLI

**Files:**
- Create: `src/crypto_quant/system_paper_evaluation_cli.py`
- Create: `tests/test_system_paper_evaluation_cli.py`
- Modify: `pyproject.toml`

**Interfaces:**
- CLI accepts only the seven frozen path flags and uses OS UTC clock.

- [ ] Add red parser tests rejecting clock/date/slot/PnL/fee/price/threshold/id/filename and relative paths.
- [ ] Add pending, PASS, DID_NOT_PASS, INCONCLUSIVE and structured failure tests.
- [ ] Implement one canonical stdout line, one bounded canonical stderr line and stable exit codes.
- [ ] Verify imports/calls contain no network, Runner, scheduler execution, Broker or order authority.
- [ ] Commit: `feat: add fixed system paper evaluation cli`.

### Task 6: Build identity, version and truthful documentation

**Files:**
- Modify: `src/crypto_quant/build.py`
- Modify: `tests/test_estimators.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `pyproject.toml`, `setup.py`, `src/crypto_quant/__init__.py`, `src/crypto_quant_core.egg-info/PKG-INFO`
- Create: `docs/adr/0059-system-paper-fixed-tail-evaluation.md`
- Create: `docs/implementation-status-v0.59.0.md`
- Modify: `README.md`

- [ ] Add red build assertions for all new source/test/Schema/design/plan/docs files.
- [ ] Set package `0.59.0` and increment manifest version exactly once after inputs settle.
- [ ] Document code-only, not-installed, not-started status and all three truthful final outcomes.
- [ ] Refresh and validate manifest, Schema mirrors and package version mirrors.
- [ ] Commit: `release: document system paper evaluation v0.59.0`.

### Task 7: Independent review and local release verification

- [ ] Request independent spec-compliance and code-quality review covering tail blindness, exact 540-slot replay, retained descriptors, economic math, result state separation and CLI authority.
- [ ] Reproduce every valid finding with a red regression before fixing it.
- [ ] Require Critical 0 / Important 0 before release.
- [ ] Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -q
PYTHONPYCACHEPREFIX=/private/tmp/crypto-quant-v059-pycache \
  PYTHONPATH=src /usr/bin/python3 -m compileall -q src tests scripts
PYTHONPATH=src /usr/bin/python3 scripts/validate_evaluator_build.py
make validate
git diff --check v0.58.0...HEAD
git status --short
```

- [ ] Prove production runtime root, plist and service state were not changed by v0.59 development.

### Task 8: PR, CI, main and annotated tag

- [ ] Recheck private target repo, origin, remote main, `v0.58.0^{}` and ADMIN permission.
- [ ] Push exact reviewed branch and create Draft PR.
- [ ] Require Python 3.9/3.12 PR CI green for exact reviewed HEAD.
- [ ] Merge exact HEAD only; require remote main CI green.
- [ ] Create annotated `v0.59.0` exactly at remote main and verify peeled commit.
- [ ] Do not install/start anything after tagging; v0.60 projection remains the next engineering phase.

## Plan self-review

- Every design section maps to a task and a concrete test or release gate.
- Tail blindness is enforced before slot-file reads, not by output redaction alone.
- Completeness failure and gate failure remain distinct.
- CLI authority remains seven paths with no economic selector.
- Economic constants and strict inequalities are named, exact and preregistered.
- No task authorizes production activation or widens network/trading authority.

## Execution choice

The user has delegated implementation without further questions. Execute this plan inline and sequentially. Do not combine v0.60 Web/projection work or runtime installation into v0.59.
