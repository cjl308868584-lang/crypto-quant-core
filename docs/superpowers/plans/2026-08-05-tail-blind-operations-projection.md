# Tail-Blind Operations Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:executing-plans` and `superpowers:test-driven-development` task by task.

**Goal:** 发布 v0.60.0 的纯函数、严格 Schema 化、可重放且不泄露经济数据的只读运维投影，作为后续 loopback Web/alerts 的唯一数据边界。

**Architecture:** 三个零参数 adapter 按固定顺序各调用一次，分别返回 frozen/slotted typed source snapshot。projector 只逐字段组装 allowlist，验证 Git release identity、时间与跨字段状态机，派生 freshness/overall status，并生成 canonical `projection_hash`。严格 bytes loader 只接受 canonical JSON、镜像 Schema 和正确 hash；模块本身不读文件、不执行进程、不访问网络，也不写 artifact。

**Tech stack:** Python 3.9 stdlib, frozen/slotted dataclasses, `jsonschema` Draft 2020-12, canonical JSON/SHA-256, `unittest`.

## Global constraints

- 工作目录：`/Users/chenm4/Documents/虚拟货币/.worktrees/v0.60-tail-blind-operations-projection`。
- 分支：`codex/v0.60-tail-blind-operations-projection`。
- 发布基线：`v0.59.0^{}` 与 `origin/main` 均为 `3a4283bc06099f821ca72947535748d3e3760180`。
- 设计权威：`docs/superpowers/specs/2026-08-05-tail-blind-operations-projection-design.md`。
- 先红灯测试，后最小实现；每个中间提交只运行聚焦/相邻测试。
- 最终代码状态本地全量测试只运行一次；不在同机同提交机械重复。
- 独立审查一次；只有修复后才做针对性复审，不对无变化分支重做整审。
- 保留 PR Python 3.9/3.12 CI、main CI 与 annotated tag identity 验证。
- 禁止 production install/start、Runner/scheduler/maintenance、SQLite/策略 state 写入、市场网络、凭据、Broker、订单和真实资金行为。
- `production_activation.enabled=false` 保持不变。
- v0.60 不实现 Web、alerts、runbooks 或 replacement Challenger；这些是后续独立版本。

---

### Task 1: Freeze public types and loader-call authority

**Files:**
- Create: `tests/test_operations_projection.py`
- Create: `src/crypto_quant/operations_projection.py`

**Step 1: Write the failing public-contract tests**

Add helpers that create only valid source dataclasses, then prove all three loaders are invoked exactly once and in this order:

```python
calls = []
sources = OperationsProjectionSources(
    release_loader=lambda: calls.append("release") or release_source(),
    challenger_loader=lambda: calls.append("challenger") or challenger_source(),
    system_paper_loader=lambda: calls.append("system_paper") or paper_source(),
)
projection = build_operations_projection(NOW, sources)
self.assertEqual(calls, ["release", "challenger", "system_paper"])
self.assertEqual(projection["schema_version"], "1.0.0")
```

Also add red tests for:

- non-`OperationsProjectionSources` input;
- loader exception with secret/path text that must not be copied to the public exception;
- wrong loader return type;
- subclass/extra attribute attempts;
- frozen/slotted dataclass mutation and dynamic attribute rejection;
- source objects unchanged after projection.

Run and confirm RED:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_operations_projection.OperationsProjectionSourceBoundaryTests -v
```

Expected failure: import/module or public types do not exist.

**Step 2: Implement the minimum typed boundary**

Create:

```python
@dataclass(frozen=True, slots=True)
class SourceProvenance: ...

@dataclass(frozen=True, slots=True)
class ReleaseOperationsSource: ...

@dataclass(frozen=True, slots=True)
class ChallengerOperationsSource: ...

@dataclass(frozen=True, slots=True)
class SystemPaperOperationsSource: ...

@dataclass(frozen=True, slots=True)
class OperationsProjectionSources:
    release_loader: Callable[[], ReleaseOperationsSource]
    challenger_loader: Callable[[], ChallengerOperationsSource]
    system_paper_loader: Callable[[], SystemPaperOperationsSource]
```

Add `OperationsProjectionError(reason_code)` and a private loader wrapper that catches arbitrary exceptions and emits only `OPERATIONS_PROJECTION_SOURCE_LOAD_FAILED`. Do not import filesystem, `subprocess`, SQLite, HTTP, launchctl, Broker, or runtime modules.

**Step 3: Run focused tests and commit**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_operations_projection.OperationsProjectionSourceBoundaryTests -v
git diff --check
git add src/crypto_quant/operations_projection.py tests/test_operations_projection.py
git commit -m "feat: add typed operations projection boundary"
```

---

### Task 2: Validate source state machines, identity, time and freshness

**Files:**
- Modify: `tests/test_operations_projection.py`
- Modify: `src/crypto_quant/operations_projection.py`

**Step 1: Write red identity and time tests**

Table-drive these failures:

- package version not strict `MAJOR.MINOR.PATCH`;
- tag not exactly `v{package_version}`;
- main/tag commit not equal or not 40 lowercase hex;
- provenance hash not 64 lowercase hex;
- wrong `source_kind` for its section;
- non-canonical timestamps, local offsets, naive datetimes, microseconds not millisecond-aligned;
- observed source more than five minutes in the future.

Use exact boundary assertions:

```python
self.assertEqual(freshness_at(minutes=20), "FRESH")
self.assertEqual(freshness_at(minutes=20, milliseconds=1), "STALE")
self.assertRaisesReason(future_at(minutes=5, milliseconds=1),
                        "OPERATIONS_PROJECTION_FUTURE_SOURCE")
```

Run and confirm RED:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_operations_projection.OperationsProjectionValidationTests -v
```

**Step 2: Implement strict validation**

- Parse only canonical UTC `...SS.mmmZ` text and reproduce it with `utc_datetime`.
- Reject `bool` wherever an integer is required.
- Validate every enum explicitly.
- Require release provenance freshness output to be `IDENTITY_VERIFIED`.
- Derive operational provenance freshness from `now`; never accept freshness from adapters.
- Raise only the bounded design reason codes.

**Step 3: Add and satisfy cross-field state-machine tests**

Challenger cases:

- legacy failed/replacement not started;
- replacement not started;
- collecting with only `WITHHELD_PRE_TAIL`;
- final with each terminal gate;
- reject early terminal gate, invalid count/active/next-slot combinations and negative counts.

System Paper cases:

- `NOT_INSTALLED` requires all-zero counts, no next slot, unavailable risk/reconciliation and not-evaluated gate;
- `INSTALLED_NOT_STARTED` remains not evaluated;
- `COLLECTING` requires not-evaluated gate;
- only `FINAL` accepts a terminal gate;
- reject lifecycle contradictions and negative counts.

**Step 4: Run focused tests and commit**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_operations_projection.OperationsProjectionValidationTests \
  tests.test_operations_projection.OperationsProjectionStateMachineTests -v
git diff --check
git add src/crypto_quant/operations_projection.py tests/test_operations_projection.py
git commit -m "feat: enforce projection identity and state machines"
```

---

### Task 3: Assemble the tail-blind projection and derive health

**Files:**
- Modify: `tests/test_operations_projection.py`
- Modify: `src/crypto_quant/operations_projection.py`

**Step 1: Write red assembly and status tests**

Assert the exact top-level key order/content and exact per-section allowlists. Table-drive overall status:

```text
FAILED_CLOSED: service/evidence failed closed, or paper reconciliation failed closed
DEGRADED: stale, degraded, incident_count > 0, incident evidence, HALT/HARD_BOUNDARY
HEALTHY: every remaining valid state, including legitimate not-started
```

Add deterministic-hash tests using two independently created equal source sets. Expected:

```python
expected_hash = business_hash({
    "purpose": "TAIL_BLIND_OPERATIONS_PROJECTION_V1",
    **projection_without_hash,
})
```

Do not mutate returned mappings while calculating the hash.

**Step 2: Write red tail-blindness tests**

For pre-tail and final Challenger sources, canonicalize the complete projection and assert no case-insensitive occurrence of:

```text
pnl profit return win_rate drawdown equity price fee confidence ranking interval power
```

Create hostile source subclasses/objects carrying `pnl`, nested arbitrary mappings, fake credentials and absolute paths. They must either fail type validation or be structurally impossible; nothing hostile may appear in output or exception text.

System Paper may expose only simulated lifecycle counts, reconciliation, risk and final gate—not the measurements behind them.

Run and confirm RED:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_operations_projection.OperationsProjectionAssemblyTests \
  tests.test_operations_projection.OperationsProjectionTailBlindTests -v
```

**Step 3: Implement field-by-field assembly**

Build a new dictionary for every section. Never call `asdict`, `vars`, `__dict__`, recursive filters, mapping merge, or source serialization. Compute `projection_hash` only after the complete allowlisted mapping is built.

**Step 4: Run focused tests and commit**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_operations_projection.OperationsProjectionAssemblyTests \
  tests.test_operations_projection.OperationsProjectionTailBlindTests -v
git diff --check
git add src/crypto_quant/operations_projection.py tests/test_operations_projection.py
git commit -m "feat: build tail-blind operations projection"
```

---

### Task 4: Add mirrored strict Schema and canonical replay loader

**Files:**
- Create: `config/operations-projection-v1.schema.json`
- Create: `src/crypto_quant/schemas/operations-projection-v1.schema.json`
- Modify: `tests/test_operations_projection.py`
- Modify: `src/crypto_quant/operations_projection.py`

**Step 1: Write the failing loader and Schema tests**

Cover:

- exact mirror bytes;
- `Draft202012Validator.check_schema` success;
- `additionalProperties=false` at every object boundary;
- accepted canonical projection bytes;
- invalid UTF-8, empty/non-object/oversized bytes;
- duplicate keys, binary floats and non-finite constants;
- non-canonical whitespace/key order/newline;
- unknown top-level and nested fields;
- wrong enums/patterns/counts;
- changed content with stale hash and changed hash with stale content.

Test skeleton:

```python
body = canonical_json(projection).encode("utf-8")
self.assertEqual(load_operations_projection_bytes(body), projection)
with self.assertRaisesReason(tampered, "OPERATIONS_PROJECTION_HASH_MISMATCH"):
    load_operations_projection_bytes(tampered)
```

Run and confirm RED:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_operations_projection.OperationsProjectionLoaderTests -v
```

**Step 2: Implement the loader**

- Bound input before decode with a named constant.
- Use `object_pairs_hook` to reject duplicate keys and `parse_float`/`parse_constant` to reject floats.
- Require `canonical_json(value).encode("utf-8") == body` exactly; do not allow a trailing newline.
- Load only the packaged Schema with `importlib.resources` and cache the validator.
- Recompute the business hash from a copied mapping without `projection_hash`.
- Convert all external parse/Schema failures to `OPERATIONS_PROJECTION_BYTES_INVALID` or `OPERATIONS_PROJECTION_SCHEMA_INVALID`; preserve hash mismatch as its own bounded reason.

**Step 3: Create exact mirrored schemas**

The top-level and all nested objects must define `required`, exact enums/patterns/minimums, and `additionalProperties: false`. Copy the final config bytes to the packaged path using `apply_patch`; verify with `cmp`.

**Step 4: Run focused and adjacent tests, then commit**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_operations_projection -v
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_system_paper_evaluation \
  tests.test_challenger_cohort_cumulative_evaluation -q
cmp config/operations-projection-v1.schema.json \
  src/crypto_quant/schemas/operations-projection-v1.schema.json
git diff --check
git add config/operations-projection-v1.schema.json \
  src/crypto_quant/schemas/operations-projection-v1.schema.json \
  src/crypto_quant/operations_projection.py tests/test_operations_projection.py
git commit -m "feat: add strict operations projection replay"
```

If the named Challenger adjacent module differs, discover the exact existing filename with `rg --files tests | rg 'challenger.*cumulative'` and use that module; do not invent or skip it.

---

### Task 5: Prove purity and close adversarial gaps

**Files:**
- Modify: `tests/test_operations_projection.py`
- Modify: `src/crypto_quant/operations_projection.py` only if a red test proves a defect

**Step 1: Add red purity tests**

Patch or audit filesystem reads, writes, `open`, `Path`, subprocess, sockets, HTTP, SQLite, environment credentials and known Broker/order entry points. Import, build and load must need none of them. Assert only the three injected adapters run.

Add repeatability and immutability cases:

- 100 projections from identical immutable inputs are exactly equal;
- output mutation cannot change source objects;
- loader returns a fresh mapping;
- a loader that changes its result after first call cannot affect the projection because it is called only once;
- arbitrary loader exception text never appears in the public error.

**Step 2: Run focused tests and inspect forbidden imports/terms**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_operations_projection -v
rg -n 'subprocess|sqlite3|socket|requests|urllib|launchctl|Broker|order' \
  src/crypto_quant/operations_projection.py
rg -ni 'pnl|profit|return|win_rate|drawdown|equity|price|fee|confidence|ranking|interval|power' \
  config/operations-projection-v1.schema.json \
  src/crypto_quant/schemas/operations-projection-v1.schema.json
```

The first `rg` must have no operational import/use. The second must have no Schema match. Expected words may appear only in comments/tests that assert prohibition, never in source fields or output Schema.

**Step 3: Commit**

```bash
git diff --check
git add src/crypto_quant/operations_projection.py tests/test_operations_projection.py
git commit -m "test: harden operations projection boundary"
```

Skip the commit if no files changed after the adversarial tests; do not create a mechanical empty commit.

---

### Task 6: Bind v0.60 build identity and truthful release documentation

**Files:**
- Modify: `src/crypto_quant/build.py`
- Modify: `tests/test_estimators.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `src/crypto_quant/__init__.py`
- Create: `docs/adr/0060-tail-blind-operations-projection.md`
- Create: `docs/implementation-status-v0.60.0.md`
- Modify: `README.md`

**Step 1: Add red build-identity assertions**

Update `tests/test_estimators.py` to require:

- semantic/package version `0.60.0` in all mirrors;
- evaluator build manifest `1.54.0`;
- both Schema mirrors, module, tests, design, plan, ADR and implementation status in the expected file set.

Run the focused build test and confirm RED before production metadata changes:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_estimators.BuildManifestTests -v
```

Use the exact existing class name returned by `rg -n '^class .*Build' tests/test_estimators.py` if it differs.

**Step 2: Update version/build inputs once**

- Add `config/operations-projection-v1.schema.json` to `_FROZEN_CONFIG_PATHS`.
- Add the new test/design/plan/ADR/status files to `_FROZEN_RELEASE_PATHS`.
- Set package version mirrors to `0.60.0`.
- Set manifest and refresh-script expected versions to `1.54.0` / `0.60.0`.
- Do not refresh the manifest until every bound input has reached final bytes.

**Step 3: Write truthful docs**

ADR-0060 must state that the projection is a pure, tail-blind observation contract and does not install or start anything. Implementation status and README must say:

- v0.60 code/Schema/tests completed;
- System Paper still not installed/not started, no 90-day evidence;
- old Challenger cohort remains permanently failed for continuity, not profitability;
- no profit, AI advantage, Canary or live-trading claim;
- v0.61 Web/alerts/runbooks and replacement Challenger remain pending.

**Step 4: Refresh manifest only after inputs settle**

```bash
PYTHONPATH=src /usr/bin/python3 scripts/refresh_evaluator_build_manifest.py
PYTHONPATH=src /usr/bin/python3 scripts/validate_evaluator_build.py
cmp config/operations-projection-v1.schema.json \
  src/crypto_quant/schemas/operations-projection-v1.schema.json
git diff --check
```

**Step 5: Run focused build tests and commit**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_estimators -v
git add pyproject.toml setup.py src/crypto_quant/__init__.py \
  src/crypto_quant/build.py \
  config/evaluator-build-manifest-v1.json \
  scripts/refresh_evaluator_build_manifest.py tests/test_estimators.py \
  docs/adr/0060-tail-blind-operations-projection.md \
  docs/implementation-status-v0.60.0.md README.md
git commit -m "release: bind tail-blind projection v0.60.0"
```

---

### Task 7: One independent review, targeted fixes, and one final local verification

**Step 1: Freeze the review candidate**

Record `git rev-parse HEAD`, ensure status is clean, and request one independent full review against the frozen design. Review must explicitly cover:

- typed boundary and one-call order;
- release identity/time/state invariants;
- pre-tail economic redaction by structure;
- strict canonical loader, Schema and hash;
- purity/no side effects;
- package/build/docs truthfulness.

Do not repeat a full review if the commit does not change.

**Step 2: Handle findings with TDD**

For every valid Critical/Important finding:

1. reproduce it with one red focused regression;
2. implement the smallest correction;
3. run only the affected focused/adjacent tests;
4. refresh build manifest if bound bytes changed;
5. commit the fix;
6. request targeted re-review of the changed finding only.

Release gate: Critical 0 / Important 0. Suggestions may be recorded for later versions only when they do not affect the frozen safety contract.

**Step 3: Run the only local full verification for the final code state**

After review fixes and final manifest refresh, run exactly once:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -q
PYTHONPYCACHEPREFIX=/private/tmp/crypto-quant-v060-pycache \
  PYTHONPATH=src /usr/bin/python3 -m compileall -q src tests scripts
PYTHONPATH=src /usr/bin/python3 scripts/validate_evaluator_build.py
make validate
cmp config/operations-projection-v1.schema.json \
  src/crypto_quant/schemas/operations-projection-v1.schema.json
git diff --check v0.59.0...HEAD
git status --short
```

Do not rerun the full suite on the same commit and same machine. If this full run finds a defect and code changes, focused tests plus one new final-state full run are justified because the code state changed.

**Step 4: Reconfirm runtime safety boundary**

Read-only checks must show that v0.60 work did not create the System Paper production root/plist/service. Do not bootstrap, kickstart, install, stop or mutate anything while checking.

---

### Task 8: Draft PR, dual-Python CI, main CI and annotated tag

**Step 1: Verify GitHub authority immediately before writing**

Read-only verify:

- target is private `cjl308868584-lang/crypto-quant-core`;
- `origin` matches that repository;
- viewer permission is ADMIN;
- remote main and peeled `v0.59.0` still equal the frozen base;
- local branch contains the exact reviewed/verified commit and is clean.

**Step 2: Push and create Draft PR**

Push the branch, create one Draft PR, and bind its head SHA to the reviewed final commit. Mark ready only after PR checks are attached to that SHA.

**Step 3: Retain dual-Python PR CI**

Require Python 3.9 and 3.12 success. Do not duplicate those complete suites locally for the same commit. A CI-only portability failure must be reproduced narrowly, fixed with TDD, targeted re-reviewed, and then allowed to create a new CI run for the changed SHA.

**Step 4: Merge, verify main CI, tag exact main**

- Merge only the exact accepted PR head.
- Require main CI green.
- Create annotated `v0.60.0` at the exact remote main commit.
- Verify local and remote peeled tag commit equal remote main.
- Never move or replace an existing tag.

**Step 5: Preserve the next-phase boundary**

After tagging, do not install or start System Paper. v0.61 remains the loopback-only Web/alerts/runbooks version; replacement Challenger remains a separate later design and evidence root.

## Plan self-review

- Every v0.60 design section maps to a red test, implementation step and release gate.
- The projection has no generic mapping ingress or recursive redaction escape hatch.
- Challenger economics are absent from types and Schema, not merely hidden in rendering.
- System Paper exposes only operational counts/status and a terminal gate, never economic measurements.
- Freshness, identity and overall health are derived rather than trusted from sources.
- No task authorizes production activation, runtime mutation, market access or trading.
- The optimized verification policy removes duplicate mechanics while retaining one final local full suite, independent review, dual-Python PR CI, main CI and tag identity.

## Execution choice

The user has granted standing approval and asked not to be queried. Execute sequentially in this worktree using `superpowers:executing-plans`; do not delegate, install, start, or merge later phases into v0.60.
