# NautilusTrader Sandbox Isolation Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不触碰现有 System Paper、replacement Challenger 或任何 90 天证据事实的前提下，用一个固定 ETHUSDT 4H fixture 验证 NautilusTrader `1.227.0` 是否能作为下一代、非权威订单/成交/持仓/费用 sidecar 候选，并产出可独立复核的采用或拒绝报告。

**Architecture:** 当前 Python 3.9+ 核心只生成冻结的 Decision/Target/Risk 授权并只读比较结果；独立 Python 3.12 one-shot 进程加载一个 low-level `BacktestEngine`，只消费 canonical JSON 和固定 fixture，输出 canonical Order/Fills/Position/Fees artifact 后退出。两侧通过版本化 JSON Schema 和 exact hash 绑定，不共享数据库、运行根、服务、凭据或订单事实源。

**Tech Stack:** Python 3.9+ 核心、独立 CPython 3.12 sandbox、NautilusTrader `1.227.0`、`uv` frozen lock、JSON Schema 2020-12、标准库 `unittest`、canonical JSON/SHA-256、GitHub Actions Python 3.9/3.12（CI 只重放 committed evidence，不安装 145 MB wheel）。

## Execution outcome / scope closure

计划在 Task 1 的 frozen dependency acquisition 后进入失败关闭：官方同源、同版本、不放宽
hash 的两次有界尝试都未产生可用环境。因此 Task 2–3 的 request/result、fixture、
runner、engine 与 runtime failure suite 没有执行；已创建但未经引擎验证的通用协议文件已
从最终发布删除。

最终 v0.63 只交付 exact dependency lock、严格 loader、只读 preflight adapter 和
`INCONCLUSIVE_BLOCKED` report。fetch 描述明示为不可机器重放的会话 attestation；
`runtime_failure_suite_executed=false`。下文保留为原始条件实施计划的审计记录，
不表示相应任务已完成。任何重启都必须使用新语义版本和新计划。

---

## Global constraints

- 冻结设计：`docs/superpowers/specs/2026-08-05-nautilus-sandbox-isolation-spike-design.md`。
- 冻结基线：annotated `v0.62.0` / `e0a9b3eb6a3f385ea259722e6613df8708e8fe5a`。
- 不迁移、回填、重置、改起点或更换 v0.59、System Paper、replacement Challenger、旧 Challenger failure/decommission 或任何 90 天事实源。
- 不安装 LaunchAgent，不启动自然 Runner/scheduler/maintenance，不写任何现有 runtime/state/evidence root。
- `production_activation.enabled=false`、无凭据、无真实 Broker、无余额权限、无真实订单。
- Nautilus 只能存在于 `sandboxes/nautilus/.venv` 的独立 Python 3.12 环境；根包不得 import 或依赖 Nautilus，继续通过 Python 3.9 CI。
- sandbox runtime 网络调用计数必须为 0；唯一允许的网络阶段是按锁定 PyPI HTTPS 来源获取并校验候选 wheel/传递依赖。
- 同一个订单/持仓的唯一权威始终是 committed current-reference；Nautilus 输出只标记为 `NON_AUTHORITATIVE_SANDBOX_OBSERVATION`。
- 不为对齐而修改已暴露证据；所有差异必须映射到固定分类。
- 一次最终代码状态本地全量测试；一次完整独立审查，修复后只做针对性复审；保留 PR Python 3.9/3.12、main CI 与 annotated tag 身份验证。

## Fixed path surface

### Core package and contracts

- `src/crypto_quant/nautilus_sandbox_dependency.py`
- `src/crypto_quant/nautilus_sandbox_contract.py`
- `src/crypto_quant/nautilus_evidence_adapter.py`
- `config/nautilus-sandbox-dependency-lock-v1.schema.json`
- `config/nautilus-sandbox-request-v1.schema.json`
- `config/nautilus-sandbox-result-v1.schema.json`
- `config/nautilus-sandbox-comparison-v1.schema.json`
- matching mirrors under `src/crypto_quant/schemas/`

### Isolated Python 3.12 sidecar

- `sandboxes/nautilus/pyproject.toml`
- `sandboxes/nautilus/uv.lock`
- `sandboxes/nautilus/src/crypto_quant_nautilus_sandbox/__init__.py`
- `sandboxes/nautilus/src/crypto_quant_nautilus_sandbox/runner.py`
- `sandboxes/nautilus/tests/test_runner.py`

### Fixture and immutable evidence

- `tests/fixtures/nautilus-sandbox/ethusdt-4h-input-v1.json`
- `tests/fixtures/nautilus-sandbox/current-reference-v1.json`
- `artifacts/nautilus-sandbox/nautilus-sandbox-dependency-lock-v0.63.0.json`
- `artifacts/nautilus-sandbox/nautilus-sandbox-request-v0.63.0.json`
- `artifacts/nautilus-sandbox/nautilus-sandbox-result-v0.63.0.json`
- `artifacts/nautilus-sandbox/nautilus-sandbox-comparison-v0.63.0.json`

---

### Task 1: Freeze dependency, license, and isolated environment identity

**Files:**
- Create all dependency-lock schema/module/sandbox package metadata files listed above.
- Test: `tests/test_nautilus_sandbox_dependency.py`
- Test: `sandboxes/nautilus/tests/test_dependency_boundary.py`

**Interfaces:**

```python
def load_nautilus_sandbox_dependency_lock(path: Path) -> dict[str, object]: ...
def verify_nautilus_sandbox_dependency_lock(
    payload: Mapping[str, object], *, workspace_root: Path
) -> dict[str, object]: ...
```

- [ ] **Step 1: Write failing core boundary tests**

Assert exact package/version, `Requires-Python`, tag object, peeled commit, wheel filename/size/SHA-256, LGPL expression/blob/size/SHA-256, supported platform, lockfile SHA-256 and complete transitive artifact hashes. Assert rejection for an added key, changed hash, missing license, incompatible machine and non-owner file.

Run: `python -m unittest tests.test_nautilus_sandbox_dependency -v`

Expected: FAIL because loader/schema do not exist.

- [ ] **Step 2: Add the isolated package definition and frozen lock**

`sandboxes/nautilus/pyproject.toml` must require exactly `nautilus_trader==1.227.0`, Python `>=3.12,<3.13`, contain no live adapter package, and expose one console command:

```toml
[project.scripts]
crypto-quant-nautilus-sandbox = "crypto_quant_nautilus_sandbox.runner:main"
```

Generate the transitive lock only inside the sandbox:

```bash
uv lock --project sandboxes/nautilus --python 3.12
uv lock --project sandboxes/nautilus --python 3.12 --check
```

The committed lock must use hashes for every downloadable artifact. The root `pyproject.toml`, `requirements.lock` and Python 3.9 dependency graph remain unchanged at this task.

- [ ] **Step 3: Implement the strict core loader**

Use the repository canonical JSON and schema helpers. Reject symlinks, group/world-writable files, unknown fields, semantic drift and a lockfile hash mismatch. Never import `nautilus_trader` from the core module.

- [ ] **Step 4: Add a sandbox import-boundary test**

Verify the isolated package can import only under Python 3.12 and that core tests can import every `crypto_quant` module after `sys.modules.pop("nautilus_trader", None)` without installing Nautilus.

- [ ] **Step 5: Verify and commit**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_nautilus_sandbox_dependency -v
PYTHONPATH=sandboxes/nautilus/src python3.12 -m unittest discover -s sandboxes/nautilus/tests -p 'test_dependency_boundary.py' -v
git diff --check
```

Expected: PASS without creating `sandboxes/nautilus/.venv` or installing Nautilus. Commit message: `feat: freeze Nautilus sandbox supply chain`.

---

### Task 2: Freeze the directional request and current-reference contract

**Files:**
- Create request/result schemas and package mirrors.
- Create `src/crypto_quant/nautilus_sandbox_contract.py`.
- Create the fixed input and current-reference fixtures.
- Test: `tests/test_nautilus_sandbox_contract.py`.

**Interfaces:**

```python
def build_nautilus_sandbox_request(
    *, dependency_lock: Mapping[str, object], fixture: Mapping[str, object],
    current_reference: Mapping[str, object]
) -> dict[str, object]: ...

def load_nautilus_sandbox_request(path: Path) -> dict[str, object]: ...
def load_nautilus_sandbox_result(path: Path) -> dict[str, object]: ...
```

- [ ] **Step 1: Write failing canonical contract tests**

The fixture fixes ETHUSDT, Binance spot semantics, 4H timestamps, price/size precision, tick size, step size, min quantity, min notional, fees, starting cash and four named scenarios: immediate full fill, partial-then-full fill, below-minimum rejection, and restart replay. The current reference fixes Decision/Target/Risk authorization and expected order intent independently of Nautilus.

Reject an unbound decision, a risk limit expansion, relative path, hidden scenario, live venue, credential field, network URL, mutable runtime root or changed fixture/reference hash.

Run: `python -m unittest tests.test_nautilus_sandbox_contract -v`

Expected: FAIL because contracts do not exist.

- [ ] **Step 2: Implement canonical request/result loaders**

The request includes only exact dependency-lock hash, fixture hash, current-reference hash, fixed scenario list, absolute input path and one absolute temporary result path. The result schema requires:

```json
{
  "authority": "NON_AUTHORITATIVE_SANDBOX_OBSERVATION",
  "network_request_count": 0,
  "credential_access_count": 0,
  "live_broker_call_count": 0,
  "runtime_state_write_count": 0
}
```

Order/fill/fee/position/PnL events must be canonical, append-ordered and hash-addressed.

- [ ] **Step 3: Prove no production fact changes**

Record SHA-256 for all existing committed `artifacts/system-paper/**`, `artifacts/challenger-replacement/**`, and old failure/decommission artifacts before and after fixture generation. The hashes must be identical.

- [ ] **Step 4: Verify and commit**

Run:

```bash
python -m unittest tests.test_nautilus_sandbox_contract -v
python -m unittest tests.test_system_paper_runtime tests.test_challenger_replacement_plan -v
git diff --check
```

Expected: PASS. Commit message: `feat: freeze Nautilus sandbox boundary`.

---

### Task 3: Implement the one-shot low-level BacktestEngine runner

**Files:**
- Create isolated runner and its tests.
- Do not modify any production Runner, Broker, scheduler, LaunchAgent or state module.

**Interface:**

```text
crypto-quant-nautilus-sandbox \
  --request /absolute/owner-only/request.json \
  --dependency-lock /absolute/owner-only/dependency-lock.json \
  --result /absolute/owner-only/result.json
```

- [ ] **Step 1: Install only the isolated frozen environment**

Run:

```bash
uv sync --project sandboxes/nautilus --frozen --python 3.12
uv run --project sandboxes/nautilus --frozen python -c 'import nautilus_trader; print(nautilus_trader.__version__)'
```

Expected exact version: `1.227.0`. Capture installed wheel/dist metadata and license hash; mismatch fails closed and stops implementation without affecting the current core.

- [ ] **Step 2: Write failing golden and failure tests**

Use fresh temporary owner-only roots. Tests cover all four scenarios, a second fresh-process replay, malformed request, mismatched dependency lock, output collision, symlink, non-owner permissions, attempted network access, credential-shaped environment variable, live adapter import, second engine creation and an injected crash before publish.

Run:

```bash
uv run --project sandboxes/nautilus --frozen python -m unittest discover -s sandboxes/nautilus/tests -p 'test_runner.py' -v
```

Expected: FAIL because runner does not exist.

- [ ] **Step 3: Implement the minimum engine surface**

Create exactly one `BacktestEngine` per process with deterministic IDs, CASH account, NETTING OMS, no modules/live adapters and fixed venue/instrument. Feed only in-memory fixture quote/bar objects. A minimal Strategy submits exactly the preauthorized market order on the first eligible event. Enable deterministic liquidity consumption for partial-fill testing. Normalize engine events to the result contract after the engine stops.

The process must install a socket/network sentinel before importing the runner path, reject proxy/credential environment keys, use `O_CREAT|O_EXCL` plus fsync/rename for one-time publish, and never open a path outside the request/result/dependency inputs and sandbox-owned temporary output root.

- [ ] **Step 4: Verify deterministic recovery semantics**

The first process publishes the canonical result. A new process with the same exact request must either reproduce identical semantic bytes into a distinct empty result path or reject an existing path; it must never resume from or mutate the first process state.

- [ ] **Step 5: Verify and commit**

Run the focused isolated suite once after implementation. Expected: PASS with `network/credential/live_broker/runtime_state_write = 0/0/0/0`.

Commit message: `feat: add isolated Nautilus fixture runner`.

---

### Task 4: Implement the read-only Evidence Adapter and classifications

**Files:**
- Create `src/crypto_quant/nautilus_evidence_adapter.py`.
- Create comparison schema/mirror.
- Test: `tests/test_nautilus_evidence_adapter.py`.

**Interface:**

```python
def compare_nautilus_sandbox(
    *, dependency_lock: Mapping[str, object], request: Mapping[str, object],
    current_reference: Mapping[str, object], result: Mapping[str, object]
) -> dict[str, object]: ...
```

- [ ] **Step 1: Write failing comparison tests**

Compare decision binding, order intent, fill sequence/quantity/price, fees, final position, cash/PnL identity, tick/step/min-notional behavior and fresh-process replay. Every mismatch must be one of:

`SEMANTIC_EQUIVALENT`, `EXPECTED_MODEL_DIFFERENCE`, `ADAPTER_DEFECT`, `CURRENT_MODEL_LIMITATION`, `NAUTILUS_LIMITATION`, `SUPPLY_CHAIN_FAILURE`, or `UNRESOLVED_REJECT_ADOPTION`.

Any unclassified difference, missing field, zero-counter violation or failed hash chain yields `REJECT_ADOPTION`.

- [ ] **Step 2: Implement strict comparison**

The adapter reads artifacts only; it has no path to the engine, current Broker, state DB or network. It may calculate deterministic decimal identities but cannot modify either source artifact.

- [ ] **Step 3: Verify and commit**

Run:

```bash
python -m unittest tests.test_nautilus_evidence_adapter -v
python -m unittest tests.test_nautilus_sandbox_contract tests.test_nautilus_sandbox_dependency -v
git diff --check
```

Expected: PASS. Commit message: `feat: compare Nautilus sandbox evidence`.

**Fail-closed branch:** If the exact official frozen environment cannot be fetched after the initial
uv retry policy and one bounded same-source recovery attempt, Task 3 stops without a runner/result.
Task 4 then accepts only an exact `SUPPLY_CHAIN_FETCH_BLOCKED` evidence object and must emit
`INCONCLUSIVE_BLOCKED`; Golden/replay/adoption gates remain false. Tasks 5–7 may publish that
immutable rejection evidence and release identity, but must not create a synthetic sandbox result,
claim compatibility, change source/version/hash, or retry again within v0.63.

---

### Task 5: Run the exact Spike and freeze honest artifacts

**Files:**
- Create the four immutable v0.63 artifacts.
- Test: `tests/test_nautilus_sandbox_artifacts.py`.

- [ ] **Step 1: Write artifact replay tests before committing outputs**

Tests require exact canonical bytes, schema/loaders, dependency/fixture/reference/result hash chain, all zero safety counters, deterministic replay and one final status only: `ADOPTION_CANDIDATE_FOR_PREREGISTERED_SHADOW`, `REJECT_ADOPTION`, or `INCONCLUSIVE_REJECT_ADOPTION`.

Run: `python -m unittest tests.test_nautilus_sandbox_artifacts -v`

Expected: FAIL because artifacts are absent.

- [ ] **Step 2: Generate request and run two fresh-process observations**

Use `mktemp -d` owner-only roots, the frozen sidecar and no production paths. Compare both results byte-for-byte after removing only explicitly declared observation timestamps; if semantic bytes differ, classify and reject adoption.

- [ ] **Step 3: Publish exact artifacts once**

Copy through the repository no-overwrite canonical publisher, load them again with production loaders, compare runtime and committed bytes, and record stat/SHA-256. Do not rerun to search for a better outcome.

- [ ] **Step 4: Verify and commit**

Run focused artifact, contract, dependency and adapter suites. Expected: PASS regardless of candidate/reject outcome, provided the outcome is honestly preserved.

Commit message: `test: freeze Nautilus sandbox spike evidence`.

---

### Task 6: Record adoption decision, scope reduction, and release identity

**Files:**
- Create `docs/adr/0063-nautilus-sandbox-isolation-spike.md`.
- Create `docs/implementation-status-v0.63.0.md`.
- Update `README.md`, `pyproject.toml`, `src/crypto_quant/__init__.py`, `src/crypto_quant/build.py`, `scripts/refresh_evaluator_build_manifest.py`, `config/evaluator-build-manifest-v1.json`.
- Update/add version tests where required.

- [ ] **Step 1: Write the report from exact evidence**

The ADR must state the exact observed result and one of:

- candidate only for a separately preregistered future real-time Shadow; or
- reject and preserve the current core unchanged.

It must also mark generic broker/order/exchange/UI/scheduler/release expansion as stopped, vectorbt as offline research only, and Freqtrade as an independent comparison only.

- [ ] **Step 2: Add v0.63 to the build trust chain**

Bump package to `0.63.0`, build manifest to `1.57.0`, register all new source/schema/config/artifact/test/spec/plan/ADR/status paths, refresh once, and verify the manifest loader.

- [ ] **Step 3: Run final local verification once**

Run:

```bash
python -m unittest tests.test_nautilus_sandbox_dependency tests.test_nautilus_sandbox_contract tests.test_nautilus_evidence_adapter tests.test_nautilus_sandbox_artifacts -v
uv run --project sandboxes/nautilus --frozen python -m unittest discover -s sandboxes/nautilus/tests -v
python -m unittest discover -s tests -p 'test_*.py'
python -m compileall -q src tests scripts sandboxes/nautilus/src sandboxes/nautilus/tests
make validate
git diff --check
git status --short
```

This is the single local full-suite execution for the final code state. Do not repeat it on the same commit.

- [ ] **Step 4: Commit release candidate**

Commit message: `chore: release Nautilus sandbox spike v0.63.0`.

---

### Task 7: Review, PR, CI, merge, and annotated tag

- [ ] **Step 1: Request one complete independent review**

Review the entire `origin/main...HEAD` diff against the design and this plan. Critical/Important findings must reach zero. If fixes are required, add a regression test first where applicable, make a fix commit, run only focused/adjacent verification, then request targeted rereview of changed findings; do not repeat the full local suite or whole-branch review without code changes.

- [ ] **Step 2: Verify GitHub authority and open Draft PR**

Read-only verify private repository, exact origin, remote main baseline and ADMIN permission. Push branch and create a Draft PR with exact head SHA and safety statement.

- [ ] **Step 3: Require PR CI**

Require both Python 3.9 and Python 3.12 jobs on the exact PR head. CI verifies core contracts/artifacts and must not download/install Nautilus.

- [ ] **Step 4: Merge and verify main CI**

Merge only after approval and green PR CI. Verify `origin/main` exact merge identity and both main CI jobs.

- [ ] **Step 5: Create and verify annotated `v0.63.0`**

Create the tag only after main CI succeeds. Verify tag object type, peeled commit equals `origin/main`, remote tag identity and clean local worktree. Do not install or start a production Nautilus service after release.

---

## Exit criteria

v0.63 is complete only when the exact supply chain, fixed fixture, current reference, sandbox result and comparison are all loader-verified and immutable; all safety counters are zero; existing evidence hashes are unchanged; the outcome is honestly candidate/reject/inconclusive; local/PR/main gates pass; and the annotated tag peels exactly to remote main. A candidate outcome grants only permission to design a separately preregistered Shadow comparison. It does not grant production installation, 90-day stream modification, credentials, Broker access, real orders, Canary or claims of profitability.
