# NautilusTrader End-to-End Isolation Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用一个预注册、可重放、无生产权限的 v0.65 Spike，真实判断 NautilusTrader `1.230.0` 是否值得进入未来 Shadow 研究。

**Architecture:** 当前 Python 3.9 核心只负责 plan、canonical request/result loaders 和只读 Evidence Adapter；独立 macOS arm64 CPython 3.12 one-shot sidecar 创建一个 BacktestEngine 并退出。代码/lock 先冻结，正式 plan artifact 再冻结，随后供应链和 sandbox ceremony 各只产生首个不可变结果。

**Tech Stack:** CPython 3.9/3.12、NautilusTrader `1.230.0`、uv frozen lock、JSON Schema 2020-12、canonical JSON/SHA-256、POSIX descriptor I/O、standard-library `unittest`、GitHub Actions Ubuntu matrix + macOS 15 arm64。

**Spec:** `docs/superpowers/specs/2026-08-22-nautilus-end-to-end-spike-design.md`

## Global Constraints

- 基线必须是 annotated `v0.64.0` peeled commit `c4f6ea213077850a8fc8b9bd3392f1a4bac466f9`。
- v0.63 spec/plan/ADR/lock/comparison/artifacts bytes 永不修改；其结论仍为 `INCONCLUSIVE_BLOCKED`。
- 单一版本、两阶段：供应链阶段失败即 v0.65 `INCONCLUSIVE_KEEP_CURRENT_CORE`；成功后同一版本继续零网络 sandbox。
- 根包保持 Python 3.9 compatible，根 `pyproject.toml` 和 `requirements.lock` 不增加 Nautilus runtime dependency。
- 无 LaunchAgent、daemon、Runner hook、scheduler、Broker、credentials、market/account request、real order 或 production state write。
- 正式 plan 在正式 acquisition 前 immutable publish；formal result 不重跑寻找更好结论。
- public core Python 3.9/3.12 CI 保留；Nautilus wheel 只进入独立 macOS 15 arm64 Python 3.12 job。
- 每个 task 严格 RED→GREEN→refactor；最终代码状态本地 full 一次；完整审查一次，修复后定向复审。

## Fixed File Map

### Core plan and supply chain

- `src/crypto_quant/nautilus_v065_plan.py`：构造/验证 immutable preregistration plan。
- `src/crypto_quant/nautilus_v065_supply_chain.py`：构造/验证 lock、transcript 和 receipt，不 import Nautilus。
- `src/crypto_quant/nautilus_v065_ceremony_cli.py`：只有固定 `publish-plan` 与 `acquire-and-run` 命令。
- `config/nautilus-e2e-spike-plan-v1.schema.json` 与 package mirror。
- `config/nautilus-supply-chain-receipt-v2.schema.json` 与 package mirror。

### Directional boundary and evidence

- `src/crypto_quant/nautilus_v065_contract.py`：request/result builders/loaders。
- `src/crypto_quant/nautilus_v065_evidence.py`：只读 comparison/classification。
- request/result/comparison v2 schemas 与 package mirrors。
- `tests/fixtures/nautilus-v065/ethusdt-4h-input-v2.json`。
- `tests/fixtures/nautilus-v065/current-reference-v2.json`。

### Isolated sidecar

- `sandboxes/nautilus-v065/pyproject.toml`、`uv.lock`。
- `sandboxes/nautilus-v065/src/crypto_quant_nautilus_v065/runner.py`。
- `sandboxes/nautilus-v065/tests/`：dependency、golden、failure、fresh-process tests。

### Formal evidence and release

- `artifacts/nautilus-sandbox/nautilus-e2e-spike-plan-v0.65.0.json`。
- `artifacts/nautilus-sandbox/v0.65.0/` 下的 receipt/transcripts/request/results/comparison。
- `.github/workflows/ci.yml`：新增独立 macOS arm64 sandbox job。
- `docs/adr/0065-nautilus-end-to-end-spike.md`、`docs/implementation-status-v0.65.0.md`。
- package/version/build manifest/README 的机械发布更新。

---

### Task 1: Freeze preregistration plan contract

**Files:**
- Create: `config/nautilus-e2e-spike-plan-v1.schema.json`
- Create: `src/crypto_quant/schemas/nautilus-e2e-spike-plan-v1.schema.json`
- Create: `src/crypto_quant/nautilus_v065_plan.py`
- Create: `tests/test_nautilus_v065_plan.py`

**Interfaces:**
- Consumes: v0.64 foundation, v0.63 predecessor artifacts, candidate code/lock commit and tree.
- Produces: `build_nautilus_v065_plan(*, repository_root: Path, candidate_commit: str) -> dict[str, object]` and `load_nautilus_v065_plan(path: Path) -> dict[str, object]`.

- [ ] **Step 1: Write plan RED tests**

Tests require exact v0.64 commit/tag, exact v0.63 dependency/comparison hashes, candidate `1.230.0` identities,
fixed scenarios/classifications/gates/counters and the candidate commit/tree. They reject unknown fields, changed
thresholds, latest `1.231.0`, missing predecessor, float values, unsafe file identity and a candidate commit that is
not the current reviewed code/lock predecessor.

```python
def test_plan_freezes_candidate_and_predecessor_bytes(self):
    plan = build_nautilus_v065_plan(repository_root=ROOT, candidate_commit=HEAD)
    self.assertEqual(plan["candidate"]["version"], "1.230.0")
    self.assertEqual(plan["candidate"]["wheel_sha256"], "033f6207d1c52095d64a7644f43b90cab939c2038044db70a4165f2acef3d079")
    self.assertEqual(plan["authority"]["real_orders_allowed"], False)
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=src:tests python3 -m unittest -v test_nautilus_v065_plan`

Expected: import failure because the v0.65 plan module does not exist.

- [ ] **Step 3: Implement the strict schema, builder and descriptor loader**

Use existing `canonical_json`/business hash helpers. Loader must use `O_RDONLY|O_NOFOLLOW|O_NONBLOCK`, require
regular/euid-owned/mode `0644` or stricter/nlink 1/size 1..4 MiB, bounded read, before/after fstat and attachment
recheck. It must recompute plan id/hash and all referenced Git/blob/file identities.

- [ ] **Step 4: Run GREEN and schema mirror gate**

Run:

```bash
PYTHONPATH=src:tests python3 -m unittest -v test_nautilus_v065_plan
cmp config/nautilus-e2e-spike-plan-v1.schema.json src/crypto_quant/schemas/nautilus-e2e-spike-plan-v1.schema.json
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add config/nautilus-e2e-spike-plan-v1.schema.json src/crypto_quant/schemas/nautilus-e2e-spike-plan-v1.schema.json src/crypto_quant/nautilus_v065_plan.py tests/test_nautilus_v065_plan.py
git commit -m "feat: freeze v0.65 Nautilus preregistration contract"
```

### Task 2: Freeze isolated dependency graph and receipt schema

**Files:**
- Create: `sandboxes/nautilus-v065/pyproject.toml`
- Create: `sandboxes/nautilus-v065/uv.lock`
- Create: `config/nautilus-supply-chain-receipt-v2.schema.json`
- Create: `src/crypto_quant/schemas/nautilus-supply-chain-receipt-v2.schema.json`
- Create: `src/crypto_quant/nautilus_v065_supply_chain.py`
- Create: `tests/test_nautilus_v065_supply_chain.py`
- Create: `sandboxes/nautilus-v065/tests/test_dependency_boundary.py`

**Interfaces:**
- Consumes: exact committed `uv.lock`, fixed official metadata/transcript fixtures.
- Produces: `build_nautilus_v065_dependency_lock(repository_root: Path) -> dict[str, object]`, `load_nautilus_v065_supply_chain_receipt(path: Path) -> dict[str, object]`.

- [ ] **Step 1: Write dependency and receipt RED tests**

Require exact top-level wheel filename/size/hash, tag object/peeled commit, LGPL bytes/hash, every transitive
distribution filename/size/hash, CPython/platform/tool identities, SLSA verification result, command transcripts,
and zero broker/credential/state counters. Reject any unpinned package, index/source change, sdist fallback, live
extra, missing stdout/stderr bytes or mismatch between transcript bytes and recorded hash.

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=src:tests python3 -m unittest -v test_nautilus_v065_supply_chain`

Expected: failure because v2 receipt/schema do not exist.

- [ ] **Step 3: Create only the isolated Python 3.12 project and lock**

`pyproject.toml` must contain `requires-python = ">=3.12,<3.13"` and exact
`nautilus_trader==1.230.0`, with no integrations extras. Generate lock in this sandbox only:

```bash
uv lock --project sandboxes/nautilus-v065 --python 3.12
uv lock --project sandboxes/nautilus-v065 --python 3.12 --check
```

Do not sync/install and do not execute formal acquisition in this task.

- [ ] **Step 4: Implement lock and receipt verification without importing Nautilus**

Parser accepts the exact committed uv lock version and reconstructs a sorted distribution inventory. Receipt
loader applies the same descriptor safety contract as Task 1 and recomputes every transcript/file/business hash.

- [ ] **Step 5: Run GREEN and root-isolation scan**

```bash
PYTHONPATH=src:tests python3 -m unittest -v test_nautilus_v065_supply_chain
PYTHONPATH=sandboxes/nautilus-v065/src python3.12 -m unittest discover -s sandboxes/nautilus-v065/tests -p 'test_dependency_boundary.py' -v
rg -n 'nautilus_trader|nautilus-trader' pyproject.toml requirements.lock src/crypto_quant --glob '!nautilus_v065_*'
git diff --check
```

The root scan must find no new import or dependency.

- [ ] **Step 6: Commit**

```bash
git add sandboxes/nautilus-v065 config/nautilus-supply-chain-receipt-v2.schema.json src/crypto_quant/schemas/nautilus-supply-chain-receipt-v2.schema.json src/crypto_quant/nautilus_v065_supply_chain.py tests/test_nautilus_v065_supply_chain.py
git commit -m "feat: lock v0.65 Nautilus supply chain"
```

### Task 3: Implement the fixed acquisition CLI

**Files:**
- Create: `src/crypto_quant/nautilus_v065_ceremony_cli.py`
- Modify: `src/crypto_quant/nautilus_v065_supply_chain.py`
- Create: `tests/test_nautilus_v065_acquisition.py`

**Interfaces:**
- Consumes: committed plan and lock, fixed repository root, private subprocess wrappers.
- Produces: `python -m crypto_quant.nautilus_v065_ceremony_cli publish-plan` and private
  `acquire_nautilus_v065_supply_chain(*, plan: Mapping[str, object]) -> dict[str, object]`; no
  path/version/URL/hash arguments. Task 6 adds the final `acquire-and-run` orchestration only after all components exist.

- [ ] **Step 1: Write CLI/acquisition RED tests**

Tests inspect parser/source and patch private fixed command/result-verification boundaries. They require only the
parameterless `publish-plan` command at this intermediate task, no public override, clean reviewed commit, owner-only temp root, fixed command order, sanitized env,
bounded stdout/stderr, exact PyPI JSON plus 14 individually transcribed nonredirecting wheel downloads, wheel
verification before install/import, SLSA verification, offline sync, exact installed-distribution inventory,
Nautilus license metadata and no loaded live-adapter module,
and fixed reason codes for timeout/hash/license/tag/attestation/platform failures.

```python
def test_intermediate_cli_exposes_only_parameterless_publish_plan(self):
    parser = build_parser()
    self.assertEqual(set(_subcommand_names(parser)), {"publish-plan"})
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=src:tests python3 -m unittest -v test_nautilus_v065_acquisition`

Expected: import failure because CLI does not exist.

- [ ] **Step 3: Implement exact command/transcript capture**

For each successful process, record executable dev/ino/mode/size/SHA before and after, exact argv, sanitized env
keys, start/end, exit code, stdout/stderr exact bytes (base64 only when non-UTF8), sizes and hashes. Reject output
over the fixed limit while the child is still running and terminate its process group; pass each locked wheel's exact
size to curl as its active maximum. Timeout handling has a bounded drain and cannot wait indefinitely for an escaped
pipe holder. Loader replay maps each command name to its fixed executable path class and derives all four tool records
from their exact version transcripts. No shell, redirects, inherited Git/Python/proxy/credential environment or
caller-provided executable. Do not use an unrecorded urllib download path. The receipt must contain exactly 25
ordered transcripts: four tool identities, PyPI JSON, tag, license, 14 wheels, SLSA and three offline environment
commands.

- [ ] **Step 4: Implement safe receipt publication**

Use a fixed public repository artifact root whose directory is owner-owned and never group/world writable (the
tracked parent may be `0755`); keep acquisition/execution temp roots and the formal ceremony child root `0700`.
Individual-file publication uses a retained parent descriptor, nonce staging, short-write/EINTR loop, same-fd
readback, file fsync, atomic no-replace and directory fsync. Existing exact final replays; untrusted/different final,
symlink, hardlink, FIFO, wrong mode or orphan protocol staging fails closed without chmod/delete.

- [ ] **Step 5: Run GREEN and failure adjacency**

```bash
PYTHONPATH=src:tests python3 -m unittest -v test_nautilus_v065_acquisition test_nautilus_v065_supply_chain test_challenger_replacement_plan_supersession.FixedSupersessionPublisherTests
python3 -m compileall -q src tests
git diff --check
```

- [ ] **Step 6: Materialize a non-authoritative development environment**

After the lock and acquisition boundary tests pass, download only the exact locked artifacts into an ignored cache,
verify every size/hash, and sync the ignored development venv:

```bash
uv sync --project sandboxes/nautilus-v065 --frozen --python 3.12
uv run --project sandboxes/nautilus-v065 --frozen python -c \
  'import nautilus_trader, platform; assert nautilus_trader.__version__ == "1.230.0"; assert platform.machine() == "arm64"'
```

This is development tooling, not the formal Spike acquisition or evidence. It may inform API implementation only;
it cannot change the frozen fixture, classifications, gates or candidate. Do not commit the cache/venv or label its
logs as a formal receipt.

- [ ] **Step 7: Commit**

```bash
git add src/crypto_quant/nautilus_v065_ceremony_cli.py src/crypto_quant/nautilus_v065_supply_chain.py tests/test_nautilus_v065_acquisition.py
git commit -m "feat: add fixed Nautilus acquisition ceremony"
```

### Task 4: Freeze request/result contracts and ETH 4H fixture

**Files:**
- Create: request/result v2 schemas and package mirrors.
- Create: `src/crypto_quant/nautilus_v065_contract.py`
- Create: `tests/fixtures/nautilus-v065/ethusdt-4h-input-v2.json`
- Create: `tests/fixtures/nautilus-v065/current-reference-v2.json`
- Create: `tests/test_nautilus_v065_contract.py`

**Interfaces:**
- Produces: `build_nautilus_v065_request(...)`, `load_nautilus_v065_request(path)`, `load_nautilus_v065_result(path)`.

- [ ] **Step 1: Write contract RED tests**

Freeze 21 closed bars, BBO/execution events, ETHUSDT tick/step/minimums/precisions/fees, starting cash/position,
Decision/Target/Risk bindings and four named scenarios. Reject URL, live venue client, credential field, production
path, float/NaN, manual fee/PnL, unbound decision or expanded risk.

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=src:tests python3 -m unittest -v test_nautilus_v065_contract`

- [ ] **Step 3: Implement minimal builders/loaders and canonical fixtures**

Event arrays are append-ordered and hash-bound. All business numbers are canonical Decimal strings. Request
authority counters and result safety counters are exact zero-valued objects; no optional escape hatches.

- [ ] **Step 4: Run GREEN and unchanged-authority hashes**

```bash
PYTHONPATH=src:tests python3 -m unittest -v test_nautilus_v065_contract test_system_paper_runtime test_challenger_replacement_plan
git diff --check
```

The test records exact committed System Paper/replacement artifact inventories before and after fixture generation
and requires byte/hash equality.

- [ ] **Step 5: Commit**

```bash
git add config/nautilus-sandbox-request-v2.schema.json config/nautilus-sandbox-result-v2.schema.json src/crypto_quant/schemas/nautilus-sandbox-request-v2.schema.json src/crypto_quant/schemas/nautilus-sandbox-result-v2.schema.json src/crypto_quant/nautilus_v065_contract.py tests/fixtures/nautilus-v065 tests/test_nautilus_v065_contract.py
git commit -m "feat: freeze v0.65 Nautilus directional boundary"
```

### Task 5: Implement the one-shot BacktestEngine runner

**Files:**
- Create: `sandboxes/nautilus-v065/src/crypto_quant_nautilus_v065/__init__.py`
- Create: `sandboxes/nautilus-v065/src/crypto_quant_nautilus_v065/runner.py`
- Create: `sandboxes/nautilus-v065/tests/test_runner_golden.py`
- Create: `sandboxes/nautilus-v065/tests/test_runner_failures.py`

**Interfaces:**
- Consumes: fixed request/receipt paths inside a test-owned root.
- Produces: `python -m crypto_quant_nautilus_v065.runner --request <fixed-test-path> --receipt <fixed-test-path> --result <fixed-test-path>` only inside the sandbox process; formal CLI supplies all paths.

- [ ] **Step 1: Write Golden and fault RED tests before runner code**

Use subprocesses and owner-only temp roots. Cover four scenarios, order/fill/fee/position/PnL, tick/step/min-notional,
second fresh process, missing/wrong receipt, noncanonical request, existing result, symlink/hardlink/FIFO, credential
env, socket attempt, live adapter import, second engine creation and crash before publish.

- [ ] **Step 2: Run RED in the isolated verified environment**

```bash
PYTHONPATH=sandboxes/nautilus-v065/src uv run --project sandboxes/nautilus-v065 --offline --frozen python -m unittest discover -s sandboxes/nautilus-v065/tests -v
```

Expected: runner import failure. This command is allowed only after Task 3's development acquisition fixtures have
verified the local environment; it is not the formal result ceremony.

- [ ] **Step 3: Implement exactly one low-level engine**

Construct one CASH/NETTING backtest venue, one ETHUSDT spot instrument and one minimal Strategy which submits only
the preauthorized order on the fixed eligible event. Feed only in-memory fixture data. Normalize engine outputs to
request-bound canonical events; do not expose raw objects, pickle, cache, database or wall-clock values.

- [ ] **Step 4: Enforce zero-network and atomic result publication**

Install socket sentinel before runner imports, reject proxy/cloud/exchange/broker-shaped env keys, statically reject
live adapter imports, and publish via verified staging/no-replace/fsync. A crash leaves no canonical success.

- [ ] **Step 5: Run GREEN twice as distinct tests, not result selection**

```bash
PYTHONPATH=sandboxes/nautilus-v065/src uv run --project sandboxes/nautilus-v065 --offline --frozen python -m unittest discover -s sandboxes/nautilus-v065/tests -v
PYTHONPATH=src:tests python3 -m unittest -v test_nautilus_v065_contract
```

- [ ] **Step 6: Commit**

```bash
git add sandboxes/nautilus-v065/src sandboxes/nautilus-v065/tests
git commit -m "feat: add isolated Nautilus fixture runner"
```

### Task 6: Implement read-only comparison and final classification

**Files:**
- Create: `config/nautilus-sandbox-comparison-v2.schema.json`
- Create: package schema mirror.
- Create: `src/crypto_quant/nautilus_v065_evidence.py`
- Modify: `src/crypto_quant/nautilus_v065_ceremony_cli.py`
- Create: `tests/test_nautilus_v065_evidence.py`

**Interfaces:**
- Produces: `compare_nautilus_v065(*, plan, receipt, request, current_reference, first_result, replay_result) -> dict[str, object]`.
- Produces final CLI surface: exactly parameterless `publish-plan` and `acquire-and-run` commands.

- [ ] **Step 1: Write comparison RED tests**

One test per exact difference class and terminal classification. Unclassified/multiple-conflicting differences,
counter violation, hash-chain break or modified current reference must fail closed. `ADOPT` requires all mandatory
gates and allows only exact or pure representation differences.

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=src:tests python3 -m unittest -v test_nautilus_v065_evidence`

- [ ] **Step 3: Implement pure read-only comparison**

The module imports loaders and Decimal helpers only. It has no subprocess, network, Broker, database, write API or
Nautilus import. It recomputes all hashes and compares each economic field explicitly.

- [ ] **Step 4: Complete the fixed ceremony orchestration**

Add `acquire-and-run` only now. It calls the Task 3 acquisition function; on verified receipt it builds the Task 4
request, invokes exactly two Task 5 fresh processes, then calls the pure comparison. On acquisition failure it
publishes only receipt + INCONCLUSIVE comparison and runner invocation count remains 0. Parser tests require the
exact two parameterless commands and reject every option or positional argument.
Observed credential, network or second-engine sentinel violations produce the fixed
`SAFETY_BOUNDARY_VIOLATION`/`REJECT_KEEP_CURRENT_CORE` result; generic execution failure remains INCONCLUSIVE.

- [ ] **Step 5: Run GREEN and static authority scan**

```bash
PYTHONPATH=src:tests python3 -m unittest -v test_nautilus_v065_evidence test_nautilus_v065_contract test_nautilus_v065_supply_chain
rg -n 'subprocess|socket|requests|urllib|Broker|sqlite|open\([^,]+,[[:space:]]*["'"']w' src/crypto_quant/nautilus_v065_evidence.py
git diff --check
```

Expected: tests pass; static scan finds no authority surface.

- [ ] **Step 6: Commit**

```bash
git add config/nautilus-sandbox-comparison-v2.schema.json src/crypto_quant/schemas/nautilus-sandbox-comparison-v2.schema.json src/crypto_quant/nautilus_v065_evidence.py src/crypto_quant/nautilus_v065_ceremony_cli.py tests/test_nautilus_v065_evidence.py tests/test_nautilus_v065_acquisition.py
git commit -m "feat: compare isolated Nautilus evidence"
```

### Task 7: Freeze code/lock review and immutable formal plan

**Files:**
- Create: `artifacts/nautilus-sandbox/nautilus-e2e-spike-plan-v0.65.0.json`
- Test: `tests/test_nautilus_v065_artifacts.py`

**Interfaces:**
- Consumes: clean reviewed code/lock predecessor commit.
- Produces: immutable formal plan and exact candidate identity for Task 8.

- [ ] **Step 1: Complete one read-only code/spec review**

Review `v0.64.0...HEAD` for Critical/Important findings, dependency isolation, exact fixture, no production authority,
safe publisher and complete difference gates. Fix findings with focused RED/GREEN tests; targeted rereview only.

- [ ] **Step 2: Write committed-artifact RED before generation**

Test exact path, canonical bytes, builder equality, v0.64/v0.63 bindings, code/lock predecessor commit/tree, schema,
hash/id and formal artifact absence-or-exact behavior. It must fail because the formal plan is absent.

- [ ] **Step 3: Publish the plan exactly once**

From a clean reviewed worktree:

```bash
PYTHONPATH=src python3 -m crypto_quant.nautilus_v065_ceremony_cli publish-plan
```

Verify loader replay, exact stat/SHA, allowed Git delta equals only the plan file, then commit:

```bash
git add artifacts/nautilus-sandbox/nautilus-e2e-spike-plan-v0.65.0.json tests/test_nautilus_v065_artifacts.py
git commit -m "test: preregister v0.65 Nautilus spike"
```

- [ ] **Step 4: Freeze candidate and prohibit further code changes**

After this commit, Task 8 may add only exact v0.65 receipt/transcript/request/result/comparison artifacts. Any source,
schema, fixture, lock or threshold change invalidates the ceremony and requires a new preregistration identity before
formal acquisition; it cannot reuse an observed result.

### Task 8: Execute the formal two-stage ceremony once

**Files:**
- Create only fixed files under `artifacts/nautilus-sandbox/v0.65.0/`.
- Modify no code/schema/fixture/lock.

**Interfaces:**
- Consumes: immutable plan, fixed CLI, exact candidate commit.
- Produces: first truthful `ADOPT`/`REJECT`/`INCONCLUSIVE` artifact set.

- [ ] **Step 1: Capture precondition evidence**

Require PUBLIC/ADMIN repository, exact origin/main `v0.64.0` foundation, clean candidate worktree, exact allowed ancestry,
no production roots/services/credentials, and zero existing v0.65 ceremony artifacts. Save raw precondition transcript.

- [ ] **Step 2: Run the only formal command**

```bash
PYTHONPATH=src python3 -m crypto_quant.nautilus_v065_ceremony_cli acquire-and-run
```

If acquisition fails, the CLI publishes receipt + `INCONCLUSIVE_KEEP_CURRENT_CORE` only and never invokes runner.
If it succeeds, the CLI runs first and replay fresh processes offline, then publishes request/results/comparison.
The CLI creates fixed owner-only `v0.65.0` once and retains its descriptor. Receipt/request/results/comparison use safe
individual-file publication. After production replay verifies their exact set, cross-document bindings and the
committed plan identity, publish `nautilus-sandbox-complete-v0.65.0.json` as the distinct final completion marker.
Fsync the parent immediately after creating and attaching the formal directory, before acquisition. Carry the
replay's exact bytes plus ephemeral dev/inode snapshot into retained-descriptor marker publication and recheck every
constituent plus the exact filename set before and after publication. Persist only portable name/size/SHA-256 file
bindings in the marker. The strict production formal-set loader independently enumerates and hashes the actual sibling
files before recomputing the marker self hash and bindings; it accepts no caller-supplied manifest. Never rename a
verified directory by pathname. Any existing formal directory blocks all reruns and is retained for evidence;
a crash before the completion marker therefore freezes a partial failure, not a false completed result.
Ceremony publication files remain exact `0600`; committed Git replay must also accept owner-owned, single-link,
non-group/world-writable `0644` checkout files without weakening no-follow, attachment, size or hash validation.
Before reporting success, replay the exact formal filename set with production schemas/loaders and verify all
receipt/request/result/comparison identities and hashes, mode, bindings and summary. Empty, incomplete, extra or
semantically invalid sets fail closed.

- [ ] **Step 3: Replay exact artifacts and prove no production mutation**

Run production loaders, `cmp` runtime/committed bytes where applicable, recompute hashes, verify final classification,
and compare pre/post System Paper/replacement artifact/state inventories and service status. All safety counters stay 0.

- [ ] **Step 4: Commit the first result without selection**

```bash
git add artifacts/nautilus-sandbox/v0.65.0
git commit -m "test: freeze v0.65 Nautilus spike result"
```

No second formal acquisition/result run is allowed for v0.65.

### Task 9: Add public CI replay and release metadata

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `docs/adr/0065-nautilus-end-to-end-spike.md`
- Create: `docs/implementation-status-v0.65.0.md`
- Modify: `README.md`, `pyproject.toml`, `src/crypto_quant/__init__.py`, `src/crypto_quant/build.py`, `config/evaluator-build-manifest-v1.json` and exact version/build tests.

**Interfaces:**
- Produces: core 3.9/3.12 jobs plus independent required `nautilus-sandbox (3.12, macos-15 arm64)` replay job.

- [ ] **Step 1: Write workflow RED tests**

Require pinned actions, minimal permissions, `runs-on: macos-15`, explicit `uname -m == arm64`, setup Python 3.12,
cache key containing wheel/lock/ABI/OS hashes, hash verification after cache, offline sandbox execution, exact committed
semantic replay, no secrets, no live adapters, and unchanged core matrix.

- [ ] **Step 2: Implement the independent parallel job**

Core jobs never install Nautilus. Sandbox job performs supply-chain cache/acquisition first, then a distinct offline
step. It does not generate or overwrite formal research artifacts; it compares ephemeral output with the committed
first result or verifies the committed INCONCLUSIVE branch without invoking runner.

- [ ] **Step 3: Record the honest ADR/status and mechanical release identity**

ADR states exact observed `ADOPT`/`REJECT`/`INCONCLUSIVE`, nonclaims and next allowed action. Bump package to
`0.65.0`, build manifest by one semantic revision, register only exact new files, and refresh once.

- [ ] **Step 4: Run final local verification once**

```bash
PYTHONPATH=src:tests python3 -m unittest -v test_nautilus_v065_plan test_nautilus_v065_supply_chain test_nautilus_v065_acquisition test_nautilus_v065_contract test_nautilus_v065_evidence test_nautilus_v065_artifacts
uv run --project sandboxes/nautilus-v065 --offline --frozen python -m unittest discover -s sandboxes/nautilus-v065/tests -v
python3 -m compileall -q src tests scripts sandboxes/nautilus-v065/src sandboxes/nautilus-v065/tests
make validate
make test
git diff --check
```

Do not repeat `make test` on the unchanged final code state.

- [ ] **Step 5: Commit release candidate**

```bash
git add -- \
  .github/workflows/ci.yml \
  README.md pyproject.toml src/crypto_quant/__init__.py src/crypto_quant/build.py \
  config/evaluator-build-manifest-v1.json \
  docs/adr/0065-nautilus-end-to-end-spike.md \
  docs/implementation-status-v0.65.0.md \
  tests/test_estimators.py
git commit -m "chore: release Nautilus end-to-end spike v0.65.0"
```

### Task 10: Review, public PR, merged-main CI and annotated tag

**Files:** none after the final candidate commit.

- [ ] **Step 1: Complete final independent review**

Critical/Important must be 0. If code changes follow, add focused RED/GREEN and targeted rereview; do not repeat
whole-branch review without relevant changes.

- [ ] **Step 2: Push and create Draft PR**

Read-only verify PUBLIC repository, origin, origin/main exact v0.64 foundation and ADMIN permission. Push exact branch,
create Draft PR, and bind exact head SHA.

- [ ] **Step 3: Require exact public PR CI**

Require successful core Python 3.9/3.12 jobs and independent macOS arm64 Python 3.12 sandbox replay job on the exact
PR head. Do not rerun an unchanged failure to search for success.

- [ ] **Step 4: Merge and require exact merged-main CI**

Merge only after all required jobs pass; capture merge SHA and require the same three jobs on exact origin/main.

- [ ] **Step 5: Create and verify annotated `v0.65.0`**

Tag exact merged main only after main CI. Verify local object type `tag`, remote tag object exists, peeled tag equals
origin/main, repository remains PUBLIC/ADMIN, and worktree is clean.

## Exit Criteria

v0.65 is complete when its first formal result is immutable and loader-replayable; the result is honestly one of
ADOPT/REJECT/INCONCLUSIVE; all safety counters are zero; existing research facts are unchanged; review and public
PR/main CI pass; and annotated `v0.65.0` peels to origin/main. ADOPT grants only permission to design a separate
preregistered Shadow comparison. It does not install, start, trade, fund, or claim profitability.
