# Replacement Challenger Install, Observer and Start Trust Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 发布 v0.68.0 的 replacement-specific、code-only 安装/观察/start-receipt 信任链，同时证明本版本没有安装、启动、网络、状态、Broker 或订单副作用。

**Architecture:** 以 v0.67 deployment candidate、v0.64 replacement plan 和 v0.68 release identity 为固定输入，分别实现 owner-only snapshot、install contract、preflight、atomic installer、只读 observer 和 start receipt。每个生产入口均为无参数固定入口；文件系统测试只 patch 私有 OS 边界，真实 installation ceremony 不属于本计划。

**Tech Stack:** Python 3.9/3.12、stdlib `os`/`ctypes`/`plistlib`/`subprocess`、`jsonschema`、现有 canonical JSON/event/live-input loaders、`unittest`。

**Spec:** `docs/superpowers/specs/2026-08-22-replacement-install-observer-start-design.md`

## Global Constraints

- 基线必须为 annotated `v0.67.0` peeled commit `ca022edccdcbb2d28b1ea25002e5f19512795e3e`。
- v0.68 最终状态固定为 `REPLACEMENT_INSTALL_TRUST_CHAIN_CODE_RELEASED_NOT_INSTALLED`。
- `production_activation=false`、`replacement_start_authorized=false`、`real_orders_allowed=false`。
- 本版本 production root/plist/service/network/state-write/Broker/order 计数全部为 0。
- 不执行真实 snapshot render、preflight、plist installation、`launchctl bootstrap` 或 start receipt publication。
- 不接受 path、URL、time、slot、command、environment、credential、Broker、order 或 filename override。
- 不引入 SQLite、scheduler、Broker、order lifecycle、交易所适配框架、第三方运行时依赖或 UI。
- 所有 canonical artifact 最大 4 MiB；snapshot 最多 1,024 文件、单文件 4 MiB、总计 128 MiB。
- Darwin/Linux 缺少 no-follow/nonblocking/directory/no-replace capability 时固定 fail closed，不降级到覆盖 rename。
- 日常只运行 focused tests；最终代码状态本地 full suite 一次。

## File Map

- `src/crypto_quant/challenger_replacement_install_trust.py`: 固定身份、路径、secure descriptor helpers、snapshot 与 contract codec/loader。
- `src/crypto_quant/challenger_replacement_install_preflight.py`: 固定只读机器检查、3 次 public time GET、receipt codec/loader。
- `src/crypto_quant/challenger_replacement_install.py`: plist no-replace publication、唯一 bootstrap 序列、rollback 与 install receipt。
- `src/crypto_quant/challenger_replacement_start.py`: 只读 observer、首个自然成功机会验证、start receipt codec/publisher。
- `src/crypto_quant/challenger_replacement_install_trust_cli.py`: 固定 snapshot/contract renderer 入口。
- `src/crypto_quant/challenger_replacement_install_preflight_cli.py`: 固定 preflight receipt 入口。
- `src/crypto_quant/challenger_replacement_install_cli.py`: 固定 installer 入口。
- `src/crypto_quant/challenger_replacement_start_cli.py`: 固定 observe/publish start receipt 入口。
- `src/crypto_quant/schemas/challenger-replacement-install-contract-v1.schema.json`: install contract mirror。
- `src/crypto_quant/schemas/challenger-replacement-install-preflight-v1.schema.json`: preflight receipt mirror。
- `src/crypto_quant/schemas/challenger-replacement-install-receipt-v1.schema.json`: install receipt mirror。
- `src/crypto_quant/schemas/challenger-replacement-start-receipt-v1.schema.json`: start receipt mirror。
- `config/` 中四份同名字 schema: committed authoritative schema。
- `tests/test_challenger_replacement_install_trust.py`: snapshot/contract/security/crash tests。
- `tests/test_challenger_replacement_install_preflight.py`: preflight/clock/credential/expiry tests。
- `tests/test_challenger_replacement_install.py`: launchctl/rollback/install receipt tests。
- `tests/test_challenger_replacement_start.py`: observer/start receipt/read-only tests。
- `tests/test_challenger_replacement_v068_release.py`: no-production-change、CLI/static/release identity gates。
- `docs/adr/0068-replacement-install-observer-start-trust-chain.md`: architecture decision。
- `docs/implementation-status-v0.68.0.md`: released-not-installed status。
- `src/crypto_quant/build.py`, `config/evaluator-build-manifest-v1.json`, `README.md`, `pyproject.toml`, `setup.py`, `src/crypto_quant/__init__.py`: v0.68 release metadata only after code is final.

---

### Task 1: Foundation, Fixed Paths and Schema Contracts

**Files:**
- Create: `src/crypto_quant/challenger_replacement_install_trust.py`
- Create: `config/challenger-replacement-install-contract-v1.schema.json`
- Create: `config/challenger-replacement-install-preflight-v1.schema.json`
- Create: `config/challenger-replacement-install-receipt-v1.schema.json`
- Create: `config/challenger-replacement-start-receipt-v1.schema.json`
- Create: matching four files under `src/crypto_quant/schemas/`
- Create: `tests/test_challenger_replacement_install_trust.py`
- Create: `tests/test_challenger_replacement_v068_release.py`

**Interfaces:**
- Produces: `ReplacementInstallTrustError(reason_code)`.
- Produces: `replacement_install_paths() -> Mapping[str, str]` with no arguments.
- Produces: `load_replacement_install_contract_bytes(data: bytes) -> Mapping[str, object]`.
- Consumes: v0.67 deployment loader and exact v0.64 plan loader.

- [ ] **Step 1: Write fixed-foundation and no-production-change RED tests**

Assert exact v0.67 repository/tag/tag-object/peeled commit/manifest/CI identities, exact runtime/plist/service paths, and authority booleans. Snapshot the production root, target plist and `launchctl print` result before and after module import; import must leave all observations unchanged. Add schema-mirror byte equality tests.

```python
def test_v068_import_has_zero_production_side_effects(self):
    before = self.observe_fixed_boundaries()
    import crypto_quant.challenger_replacement_install_trust  # noqa: F401
    self.assertEqual(self.observe_fixed_boundaries(), before)
```

- [ ] **Step 2: Run RED tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_install_trust \
  tests.test_challenger_replacement_v068_release -v
```

Expected: FAIL because modules/schemas do not exist.

- [ ] **Step 3: Implement the minimal foundation and strict schema loaders**

Define immutable constants for v0.67 foundation and fixed production paths. `replacement_install_paths()` must derive every child from the single fixed runtime root. Strict loaders must require canonical JSON, exact key sets, schema validation, stable id/self-hash and the authority tuple:

```python
{
    "production_activation": False,
    "runtime_install_authorized": True,
    "replacement_start_authorized": False,
    "real_orders_allowed": False,
}
```

Do not add filesystem writes or CLI code in this task.

- [ ] **Step 4: Run focused GREEN tests**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add config/challenger-replacement-*-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-*-v1.schema.json \
  src/crypto_quant/challenger_replacement_install_trust.py \
  tests/test_challenger_replacement_install_trust.py \
  tests/test_challenger_replacement_v068_release.py
git commit -m "feat: define replacement install trust contracts"
```

### Task 2: Secure Snapshot and Install Contract

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_install_trust.py`
- Modify: `tests/test_challenger_replacement_install_trust.py`
- Create: `src/crypto_quant/challenger_replacement_install_trust_cli.py`

**Interfaces:**
- Produces: `render_fixed_replacement_snapshot_and_contract() -> Mapping[str, object]` with no public arguments.
- Produces: `replay_replacement_snapshot(contract: Mapping[str, object]) -> Mapping[str, object]`.
- Produces: CLI `main(argv: Optional[Sequence[str]] = None) -> int`; only empty argv is valid.
- Consumes: exact v0.68 evaluator manifest inventory at ceremony time; code tests use private patched repo/root boundaries.

- [ ] **Step 1: Write snapshot security and crash RED tests**

Cover manifest-only inventory, 1,024/4 MiB/128 MiB bounds, source symlink/hardlink/FIFO/socket/wrong owner/mode, source replacement after read, short-write/EINTR, same-fd readback mismatch, file/dir fsync failures, no-replace race and same-bytes-new-inode final. Record external sentinel `bytes/mode/size/mtime_ns/ctime_ns/inode/nlink` before and after every rejection.

Use subprocess timeout for FIFO cases and patch only private wrappers such as `_openat`, `_write`, `_fsync` and `_rename_noreplace`; no production fault parameter is permitted.

- [ ] **Step 2: Verify the precise RED failures**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_install_trust -v
```

Expected: security/crash tests fail because snapshot publication is absent.

- [ ] **Step 3: Implement retained-dirfd snapshot publication**

Require `O_NOFOLLOW`, `O_NONBLOCK`, `O_DIRECTORY` and platform no-replace support. Create nonce staging with `0700`, write files via `O_CREAT|O_EXCL|O_RDWR|O_NOFOLLOW`, explicitly retry EINTR/short writes, seek/read the same fd, fsync files and directories, atomically publish and replay before success. Existing exact final must be opened read-only/nonblocking, fully replayed, parent-fsynced and revalidated before idempotent success.

Orphan staging is classified only by basename/stat and blocks that ceremony; never delete, chmod, follow or parse it.

- [ ] **Step 4: Build and load the fixed install contract**

Bind release, plan, deployment/plist, snapshot inventory/root identity, Python executable identity/import transcript, fixed schedule/paths and exact authority. Canonical self-hash excludes only its own hash field using the existing `artifact_self_hash` convention. Reject any unknown key or different bytes.

- [ ] **Step 5: Add the no-argument renderer CLI**

`main([])` calls the fixed renderer. Any positional or option argument exits non-zero before filesystem or network access. The module must not execute on import.

- [ ] **Step 6: Run focused and adjacent GREEN tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_install_trust \
  tests.test_challenger_replacement_deployment \
  tests.test_challenger_replacement_v067_release -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/crypto_quant/challenger_replacement_install_trust.py \
  src/crypto_quant/challenger_replacement_install_trust_cli.py \
  tests/test_challenger_replacement_install_trust.py
git commit -m "feat: build immutable replacement install snapshot"
```

### Task 3: Preflight Receipt and Fixed Clock Gate

**Files:**
- Create: `src/crypto_quant/challenger_replacement_install_preflight.py`
- Create: `src/crypto_quant/challenger_replacement_install_preflight_cli.py`
- Create: `tests/test_challenger_replacement_install_preflight.py`
- Modify: `tests/test_challenger_replacement_v068_release.py`

**Interfaces:**
- Produces: `observe_fixed_replacement_install_preflight() -> Mapping[str, object]`.
- Produces: `publish_fixed_replacement_install_preflight() -> Mapping[str, object]`.
- Produces: `load_replacement_install_preflight_bytes(data, *, contract, plist_bytes) -> Mapping`.
- Consumes: strict snapshot/contract replay from Task 2.

- [ ] **Step 1: Write platform, command and network-count RED tests**

Test exact Darwin arm64/uid/home/timezone, fixed origin/main/tag/admin/clean checks, absent service/plist/root, old service not loaded, 10 GB/100,000 inode thresholds, `pmset`, Python import identity, credential scan and exactly three GETs to `https://data-api.binance.vision/api/v3/time`. Unsupported platform must make command/network/write counts zero.

Add tests for oversized command output, timeout, non-UTF8 output, wrong Git identity, non-annotated tag, stale contract, clock skew, partial network success and receipt expiry.

- [ ] **Step 2: Run RED tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_install_preflight -v
```

Expected: FAIL because the preflight module is absent.

- [ ] **Step 3: Implement strict observation and receipt publication**

Run only fixed argv tuples with a minimal environment and bounded stdout/stderr. The network wrapper may call only the exact public time endpoint three times and must return request count 3 only after three verified responses. Contract-invalid failures return without receipt write; trusted-contract machine failures may publish one immutable forensic receipt. Verified receipts expire after 30 minutes.

Use fixed statuses only:

```text
PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE
PREFLIGHT_FAILED_CLOSED
PREFLIGHT_PLATFORM_UNSUPPORTED
```

- [ ] **Step 4: Add fixed CLI and static authority gates**

Reject all argv. Static tests scan production modules for credential literals, arbitrary URLs, `shell=True`, `kickstart`, Broker/order imports and public callback/fault parameters.

- [ ] **Step 5: Run focused and adjacent GREEN tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_install_preflight \
  tests.test_challenger_replacement_install_trust \
  tests.test_challenger_replacement_preflight \
  tests.test_runtime_health -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/crypto_quant/challenger_replacement_install_preflight.py \
  src/crypto_quant/challenger_replacement_install_preflight_cli.py \
  tests/test_challenger_replacement_install_preflight.py \
  tests/test_challenger_replacement_v068_release.py
git commit -m "feat: add replacement install preflight receipt"
```

### Task 4: Atomic Installer and Install Receipt

**Files:**
- Create: `src/crypto_quant/challenger_replacement_install.py`
- Create: `src/crypto_quant/challenger_replacement_install_cli.py`
- Create: `tests/test_challenger_replacement_install.py`
- Modify: `tests/test_challenger_replacement_v068_release.py`

**Interfaces:**
- Produces: `install_fixed_replacement_launch_agent() -> Mapping[str, object]`.
- Produces: `load_replacement_install_receipt_bytes(data, *, contract, preflight) -> Mapping`.
- Consumes: exact contract, plist, preflight and snapshot replay.

- [ ] **Step 1: Write launchctl ordering and crash-window RED tests**

Assert the only mutation command is:

```text
/bin/launchctl bootstrap gui/501 /Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist
```

Cover: preflight expired, service/plist already exists, plist publish crash, bootstrap failure, rollback inode replacement, post-print mismatch and successful run-count-zero verification. Patch fixed private command/file wrappers; do not add a production command seam.

- [ ] **Step 2: Verify RED failures**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_install -v
```

Expected: FAIL because installer behavior is absent.

- [ ] **Step 3: Implement no-replace plist publication and bootstrap state machine**

Before bootstrap, replay every input and revalidate absent targets. Publish plist using staging + same-fd readback + fsync + atomic no-replace. On bootstrap failure, unlink only if descriptor/path identity still matches this invocation, then fsync the parent. After successful bootstrap, never call `bootout`; a failed post-print produces `INSTALL_STATE_UNKNOWN_FAILED_CLOSED`.

- [ ] **Step 4: Implement strict install receipt**

Only a matching post-print with run count zero may produce `INSTALLED_WAITING_FOR_FIRST_NATURAL_SLOT`. Bind exact argv/exit/stdout/stderr hashes, source receipts, plist inode/stat/hash, snapshot root identity, `installed_at` and authority counters. Existing exact receipt is idempotent only after replay and parent fsync.

- [ ] **Step 5: Prove forbidden commands and zero runtime invocation**

Static and behavioral tests reject `kickstart`, `start`, `enable`, `submit`, `bootout`, shell execution and direct import/call of the runtime CLI. Failure paths must keep external sentinel snapshots exact.

- [ ] **Step 6: Run focused and adjacent GREEN tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_install \
  tests.test_challenger_replacement_install_preflight \
  tests.test_challenger_replacement_install_trust \
  tests.test_system_paper_launchctl -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/crypto_quant/challenger_replacement_install.py \
  src/crypto_quant/challenger_replacement_install_cli.py \
  tests/test_challenger_replacement_install.py \
  tests/test_challenger_replacement_v068_release.py
git commit -m "feat: install replacement launch agent atomically"
```

### Task 5: Read-only First-Natural-Slot Observer

**Files:**
- Create: `src/crypto_quant/challenger_replacement_start.py`
- Create: `tests/test_challenger_replacement_start.py`

**Interfaces:**
- Produces: `observe_fixed_replacement_first_slot() -> Mapping[str, object]`.
- Consumes: strict contract/preflight/install receipt, v0.66 event projection and v0.67 live capture/source/decision loaders.

- [ ] **Step 1: Write observer state-machine RED tests**

Cover zero events before/after first eligible trigger, exactly one complete success, failed first slot, partial event chain, non-empty stderr, non-zero launchctl exit, two successes, second-slot deadline passed, capture/source/decision mismatch, event/log/plist/snapshot identity replacement and malformed receipt.

Expected statuses are exact:

```text
WAITING_BEFORE_FIRST_ELIGIBLE_SLOT
WAITING_FOR_FIRST_NATURAL_SLOT
FIRST_NATURAL_SLOT_VERIFIED
FIRST_SLOT_OBSERVATION_WINDOW_MISSED
FAILED_CLOSED
```

- [ ] **Step 2: Add no-side-effect RED assertions**

Before and after each observer call, compare event root/log/plist/snapshot `bytes/mode/size/mtime_ns/ctime_ns/inode/nlink`. Count network/runtime/state-write/Broker/order as zero and allow exactly one fixed `launchctl print`.

- [ ] **Step 3: Run RED tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_start -v
```

Expected: FAIL because observer code is absent.

- [ ] **Step 4: Implement retained-capability observation**

Open and retain trusted roots before replay. Load all upstream receipts and exact event chain, cross-check the first `SLOT_SUCCEEDED` with v0.67 capture/source/decision bytes, logs and launchctl output. Return only canonical structural summary; do not expose PnL, return, win rate or gate result.

- [ ] **Step 5: Run focused and adjacent GREEN tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_start \
  tests.test_challenger_replacement_events \
  tests.test_challenger_replacement_runtime \
  tests.test_challenger_replacement_live_input \
  tests.test_challenger_replacement_live_runtime -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add src/crypto_quant/challenger_replacement_start.py \
  tests/test_challenger_replacement_start.py
git commit -m "feat: observe replacement first natural slot"
```

### Task 6: Start Receipt and No-argument CLI

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_start.py`
- Create: `src/crypto_quant/challenger_replacement_start_cli.py`
- Modify: `tests/test_challenger_replacement_start.py`
- Modify: `tests/test_challenger_replacement_v068_release.py`

**Interfaces:**
- Produces: `publish_fixed_replacement_start_receipt() -> Mapping[str, object]`.
- Produces: `load_replacement_start_receipt_bytes(data, *, install_receipt, contract) -> Mapping`.
- Consumes: `FIRST_NATURAL_SLOT_VERIFIED` observer result only.

- [ ] **Step 1: Write derivation, idempotency and publication RED tests**

From a fixture first slot `T`, assert exact derivation:

```python
self.assertEqual(receipt["first_scheduled_for"], T)
self.assertEqual(receipt["required_slot_count"], 540)
self.assertEqual(receipt["last_required_scheduled_for"], T + timedelta(hours=4 * 539))
self.assertEqual(receipt["tail_end"], T + timedelta(hours=4 * 540))
self.assertEqual(receipt["evaluation_not_before"], T + timedelta(hours=4 * 540, minutes=5))
```

Cover existing exact/different/untrusted receipt, concurrent no-replace, file/dir fsync failure, fresh-process replay and retained-source replacement. Verify non-verified observer states create zero receipt.

- [ ] **Step 2: Run RED tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_start -v
```

Expected: FAIL because receipt publication is absent.

- [ ] **Step 3: Implement strict start receipt codec and publisher**

Internally invoke the observer; accept no dates/counts/paths. Publish canonical bytes with staging + same-fd readback + fsync + atomic no-replace. Return success only after final replay, parent fsync and retained-root revalidation.

- [ ] **Step 4: Add the fixed observer/start CLI**

The no-argument CLI performs one observe-and-publish attempt. Any argv fails before launchctl, filesystem mutation or network. Import is side-effect-free.

- [ ] **Step 5: Run focused and adjacent GREEN tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_start \
  tests.test_challenger_replacement_install \
  tests.test_challenger_replacement_install_preflight \
  tests.test_challenger_replacement_install_trust -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```bash
git add src/crypto_quant/challenger_replacement_start.py \
  src/crypto_quant/challenger_replacement_start_cli.py \
  tests/test_challenger_replacement_start.py \
  tests/test_challenger_replacement_v068_release.py
git commit -m "feat: bind replacement start receipt"
```

### Task 7: Cross-layer Failure Matrix and YAGNI Gate

**Files:**
- Modify: `tests/test_challenger_replacement_install_trust.py`
- Modify: `tests/test_challenger_replacement_install_preflight.py`
- Modify: `tests/test_challenger_replacement_install.py`
- Modify: `tests/test_challenger_replacement_start.py`
- Modify: `tests/test_challenger_replacement_v068_release.py`
- Modify only if a failing test requires it: the four v0.68 production modules.

**Interfaces:**
- Produces: final reviewed code surface with no generic deployment/storage API.

- [ ] **Step 1: Add the committed end-to-end fixture ceremony RED test**

Use a fixture root and patched private boundaries to run render → preflight → install → observer → start receipt. Assert exact binding hashes across all artifacts and counters. This is not a production ceremony and must not reference the real runtime root.

- [ ] **Step 2: Add the complete failure matrix**

Parametrize every write/readback/file-fsync/dir-fsync/no-replace/bootstrap/post-print/observer-replay point. Each failure must return a fixed reason code, never success, and preserve external sentinel snapshots. At least one post-publication recovery must run in a fresh Python interpreter.

- [ ] **Step 3: Add static scope/YAGNI gates**

Scan new modules for `sqlite3`, scheduler imports, Broker/order modules, credential fields, mutable URL/path args, public callbacks/fault injectors, shell execution and UI code. Assert the new production modules together remain below 2,000 physical lines; if the limit is exceeded, stop and simplify before release.

- [ ] **Step 4: Run focused and full v0.68 tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_install_trust \
  tests.test_challenger_replacement_install_preflight \
  tests.test_challenger_replacement_install \
  tests.test_challenger_replacement_start \
  tests.test_challenger_replacement_v068_release -v
```

Expected: PASS.

- [ ] **Step 5: Run adjacent replacement tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_v2 \
  tests.test_challenger_replacement_events \
  tests.test_challenger_replacement_runtime \
  tests.test_challenger_replacement_live_input \
  tests.test_challenger_replacement_live_runtime \
  tests.test_challenger_replacement_deployment -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 7**

```bash
git add tests/test_challenger_replacement_install_trust.py \
  tests/test_challenger_replacement_install_preflight.py \
  tests/test_challenger_replacement_install.py \
  tests/test_challenger_replacement_start.py \
  tests/test_challenger_replacement_v068_release.py \
  src/crypto_quant/challenger_replacement_install_trust.py \
  src/crypto_quant/challenger_replacement_install_preflight.py \
  src/crypto_quant/challenger_replacement_install.py \
  src/crypto_quant/challenger_replacement_start.py
git commit -m "test: close replacement install failure matrix"
```

### Task 8: Release Metadata, Verification and Publication Candidate

**Files:**
- Create: `docs/adr/0068-replacement-install-observer-start-trust-chain.md`
- Create: `docs/implementation-status-v0.68.0.md`
- Modify: `README.md`
- Modify: `src/crypto_quant/build.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `tests/test_challenger_replacement_v068_release.py`

**Interfaces:**
- Produces: package `0.68.0`, evaluator manifest `1.62.0`, status `REPLACEMENT_INSTALL_TRUST_CHAIN_CODE_RELEASED_NOT_INSTALLED`.
- Consumes: final Task 1–7 source/test/schema inventory.

- [ ] **Step 1: Write release identity RED tests**

Require package version equality across all three locations, manifest `1.62.0`, exact file inventory/hash/tree/self-hash, ADR/status/README consistency and unchanged v0.64/v0.67 committed artifact bytes. Assert no production install/start receipt artifact is committed.

- [ ] **Step 2: Run RED release test**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v068_release -v
```

Expected: FAIL on old versions/missing status/manifest inventory.

- [ ] **Step 3: Update metadata once from final code state**

Set package `0.68.0`, manifest `1.62.0`, add exact source/schema/test/spec/plan/ADR/status inputs, then regenerate manifest hashes once using the repository’s existing build-manifest procedure. Document that v0.68 has not rendered the real snapshot, run preflight, installed plist, loaded service or written start receipt.

- [ ] **Step 4: Run focused release validation**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v068_release -v
python3 -m compileall -q src tests
git diff --check
```

Expected: PASS.

- [ ] **Step 5: Run the one final local full suite**

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
make validate
```

Expected: all tests PASS with only previously documented explicit skips; validation exits 0. Do not repeat this full suite on the unchanged commit.

- [ ] **Step 6: Request one independent complete review**

Review the entire `v0.67.0..HEAD` diff for Critical/Important issues, especially path races, crash durability, launchctl sequencing, receipt identity and forbidden side effects. Fix findings with focused RED→GREEN tests, then request only targeted re-review.

- [ ] **Step 7: Commit the release candidate**

```bash
git add pyproject.toml setup.py src/crypto_quant/__init__.py \
  src/crypto_quant/build.py config/evaluator-build-manifest-v1.json \
  docs/adr/0068-replacement-install-observer-start-trust-chain.md \
  docs/implementation-status-v0.68.0.md README.md \
  tests/test_challenger_replacement_v068_release.py
git commit -m "release: freeze replacement install trust chain v0.68.0"
```

- [ ] **Step 8: Prepare but do not silently execute remote publication**

Before remote writes, recheck public target repository, origin, ADMIN, clean branch and exact head. The approved publication flow is Draft PR → Python 3.9/3.12/macOS arm64 PR CI → fast-forward main → main CI → annotated `v0.68.0` tag with peeled commit equal to origin/main. If any CI or identity gate fails, stop and preserve evidence; never move an existing tag.

- [ ] **Step 9: Preserve the installation approval boundary**

After release, assemble one exact approval package listing production paths, three public time GETs, fixed launchctl argv, rollback/unknown-state rules and the first-natural-slot observation window. Do not render/install/start until that package is explicitly approved.
