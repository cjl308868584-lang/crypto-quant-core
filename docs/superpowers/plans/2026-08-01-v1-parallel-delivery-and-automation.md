# V1 Parallel Delivery and Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变自然运行 Challenger 的前提下，完成 System Paper、只读运维 Web、可靠性与交付工程，并把当前 heartbeat 原位更新为两条 90 天证据流的阶段化协调器。

**Architecture:** Challenger 继续使用现有独立 LaunchAgent、状态库和证据根；System Paper 使用新服务名、新 owner-only 根、新 start receipt 和独立 90 天评估。Web 只消费 production-loader 验证后生成的 projection，不读取或写入运行状态库。每日 heartbeat 只协调设计、实现和只读验收，不代替任何自然 Runner 或 maintenance。

**Tech Stack:** Python 3.9+、标准库、`jsonschema>=4.25,<5`、SQLite WAL、macOS launchd、`unittest`、静态 HTML/CSS/JavaScript、GitHub Actions。

## Global Constraints

- 冻结设计：`docs/superpowers/specs/2026-08-01-challenger-paper-parallel-automation-design.md`。
- 冻结基线：`v0.53.0` / `d0a7f2e31c469c6983a205906d25e7b6f9d7e433`。
- Challenger 540 槽、现有 Runner、08:10 maintenance、状态库和证据根不得被本计划修改或手工触发。
- `production_activation.enabled=false` 必须保持不变；任何 Broker、余额、交易凭据和真实订单调用计数必须为 0。
- Paper 只允许冻结 allowlist 内的公开市场 GET；启动前的测试、smoke 和历史重放不计入 90 天。
- System Paper 与 Challenger 使用不同 service、SQLite、stdout/stderr、artifact root、receipt root 和 evaluation root。
- confirmatory tail 前禁止向 Web、日志或 heartbeat projection 暴露 Challenger PnL。
- Web 第一版只绑定 `127.0.0.1`，不提供任何写操作，不成为运行依赖。
- 每个实现任务采用 TDD，先失败测试、后最小实现、再聚焦/相邻/全量验证和独立提交。
- 每个实质版本按设计提交、实现提交、Draft PR、PR CI、main CI、annotated tag 流程交付；健康检查不制造版本。

---

## File Structure

### System Paper core

- `src/crypto_quant/system_paper_plan.py`：唯一冻结的 BASELINE_ONLY Paper 计划、scope 和成本/成交假设。
- `src/crypto_quant/system_paper_broker.py`：无网络模拟 Broker、订单事件与部分成交/拒绝/取消模型。
- `src/crypto_quant/system_paper_runtime.py`：公开输入到决策、风险、模拟订单、账本、对账和只追加槽位结果的协调器。
- `src/crypto_quant/system_paper_runtime_cli.py`：固定路径、单时钟、无凭据运行入口。
- `src/crypto_quant/system_paper_launchd.py`：独立 LaunchAgent 合同和私有执行快照渲染。
- `src/crypto_quant/system_paper_install.py`：受限安装与 install receipt。
- `src/crypto_quant/system_paper_observer.py`：只读首次自然槽与连续性观察器。
- `src/crypto_quant/system_paper_start_receipt.py`：唯一不可变 start receipt 与 loader。
- `src/crypto_quant/system_paper_evaluation.py`：90 天系统、经济和前向一致性门。
- `config/system-paper-*.schema.json` 与 `src/crypto_quant/schemas/system-paper-*.schema.json`：镜像 Schema。
- `tests/test_system_paper_*.py`：对应聚焦测试。

### Operations projection and Web

- `src/crypto_quant/operations_projection.py`：从可信 loaders 生成去敏、tail-blind 的只读 projection。
- `src/crypto_quant/operations_dashboard.py`：仅 loopback 的标准库 HTTP 服务。
- `src/crypto_quant/dashboard/index.html`：单页只读控制台。
- `src/crypto_quant/dashboard/app.js`：渲染总览、时间线、槽位、风险和告警。
- `src/crypto_quant/dashboard/styles.css`：本地静态样式。
- `tests/test_operations_projection.py`：projection、字段禁区和证据来源测试。
- `tests/test_operations_dashboard.py`：loopback、GET allowlist、无写方法测试。

### Operations and release

- `docs/runbooks/system-paper-operations.md`：安装、观察、告警、故障取证和恢复边界。
- `docs/runbooks/operations-dashboard.md`：本地启动与安全边界。
- `docs/implementation-status-v0.54.0.md` 至 `docs/implementation-status-v0.61.0.md`、
  `docs/adr/0054-*.md` 至 `docs/adr/0061-*.md`、`README.md`：每个版本的真实状态。
- `$CODEX_HOME/automations/challenger/automation.toml`：仅通过 Codex automation API 更新，不用 shell 直接写。

---

### Task 1: Read-only baseline and gap inventory

**Files:**
- Create: `docs/system-paper-readiness-audit-v0.53.0.md`
- Reference: `README.md`, `docs/delivery-roadmap-v1.1.md`, `docs/release-evaluation-spec-v1.1.md`

**Interfaces:**
- Consumes: Git `main@v0.53.0`、现有 Paper/执行/风险模块和 LaunchAgent 只读状态。
- Produces: 每项固定为 `IMPLEMENTED_TESTED`、`IMPLEMENTED_NOT_PRODUCTION_PROVEN`、`MISSING` 或 `BLOCKED_EXTERNAL` 的 gap inventory。

- [ ] **Step 1: Capture immutable repository baseline**

Run:

```bash
git status --short --branch
git rev-parse main
git rev-parse origin/main
git rev-parse v0.53.0^{}
git merge-base --is-ancestor v0.53.0 HEAD
```

Expected: `main`、`origin/main` 与 `v0.53.0^{}` 全部等于
`d0a7f2e31c469c6983a205906d25e7b6f9d7e433`；当前功能分支以该提交为祖先。
设计/计划分支允许只包含本计划明确列出的文档变更。

- [ ] **Step 2: Inventory existing capability without network or writes**

Run:

```bash
rg -n "class OrderAggregate|class PositionExecutor|class DrawdownPolicy" src/crypto_quant tests
rg -n "PaperSchedulePolicy|run_context_complete_paper_cycle" src/crypto_quant tests
rg -n "production_activation|90个自然日|系统Paper" config docs README.md
```

Expected: order/risk/scheduler primitives exist; System Paper production service, simulated Broker integration, start receipt, 90-day evaluator and Web do not.

- [ ] **Step 3: Write the audit with exact evidence**

The document must contain these rows and evidence paths:

```markdown
| Gate | Status | Evidence | Blocking consequence |
|---|---|---|---|
| Deterministic decision core | IMPLEMENTED_TESTED | `src/crypto_quant/offline_paper.py` | none |
| Order/UNKNOWN primitives | IMPLEMENTED_TESTED | `src/crypto_quant/orders.py` | integration still required |
| Simulated Broker runtime | MISSING | no production module | blocks Paper start |
| Real account fee response | BLOCKED_EXTERNAL | `README.md` current limitations | use frozen conservative Paper cost; blocks Canary, not Paper simulation |
| Futures public context | IMPLEMENTED_NOT_PRODUCTION_PROVEN | `src/crypto_quant/perpetual_context.py` | blocks SHORT Paper start until natural preflight passes |
| 90-day System Paper evidence | MISSING | no start receipt | blocks Paper PASS |
| Read-only Web | MISSING | no Web/API files | does not block Paper start |
```

- [ ] **Step 4: Review audit against the two source specifications**

Run:

```bash
rg -n "TBD|TODO|implement later|适当|酌情" docs/system-paper-readiness-audit-v0.53.0.md
git diff --check
```

Expected: first command returns no matches; second succeeds.

- [ ] **Step 5: Commit**

```bash
git add docs/system-paper-readiness-audit-v0.53.0.md
git commit -m "docs: audit system paper readiness"
```

### Task 2: Freeze the credential-free System Paper plan

**Files:**
- Create: `src/crypto_quant/system_paper_plan.py`
- Create: `config/system-paper-plan-v1.schema.json`
- Create: `src/crypto_quant/schemas/system-paper-plan-v1.schema.json`
- Create: `tests/test_system_paper_plan.py`
- Modify: `src/crypto_quant/build.py`

**Interfaces:**
- Consumes: `OfflinePaperPlan.create("ETHUSDT")`, V1 BASELINE_ONLY route, existing canonical hashing.
- Produces: `SystemPaperPlan.create() -> SystemPaperPlan`; `build_system_paper_plan() -> Mapping[str, Any]`; `load_system_paper_plan(path: Path) -> Mapping[str, Any]`.

- [ ] **Step 1: Write failing identity and boundary tests**

```python
def test_system_paper_plan_is_fixed_baseline_only_and_credential_free(self):
    plan = SystemPaperPlan.create()
    self.assertEqual(plan.symbol, "ETHUSDT")
    self.assertEqual(plan.route, "BASELINE_ONLY")
    self.assertEqual(plan.decision_cadence_seconds, 14_400)
    self.assertEqual(plan.starting_virtual_equity_usdt, Decimal("1000"))
    self.assertEqual(plan.slippage_per_side, Decimal("0.001"))
    self.assertEqual(plan.taker_fee_per_side, Decimal("0.0015"))
    self.assertFalse(plan.credentials_allowed)
    self.assertFalse(plan.real_orders_allowed)

def test_system_paper_plan_rejects_constructor_and_overrides(self):
    with self.assertRaises(TypeError):
        SystemPaperPlan(symbol="BTCUSDT")
```

- [ ] **Step 2: Run tests and observe the missing module failure**

Run: `PYTHONPATH=src python3 -m unittest tests.test_system_paper_plan -v`

Expected: FAIL with `ModuleNotFoundError: crypto_quant.system_paper_plan`.

- [ ] **Step 3: Implement the immutable plan**

```python
@dataclass(frozen=True, init=False)
class SystemPaperPlan:
    schema_version: str
    symbol: str
    route: str
    decision_cadence_seconds: int
    starting_virtual_equity_usdt: Decimal
    slippage_per_side: Decimal
    taker_fee_per_side: Decimal
    credentials_allowed: bool
    real_orders_allowed: bool

    @classmethod
    def create(cls) -> "SystemPaperPlan":
        return cls(_token=_PLAN_TOKEN)
```

The private constructor sets exact values from the test. `build_system_paper_plan()` adds policy hashes, public request families, `production_activation=false`, self-hash and `warnings=["PAPER_NOT_STARTED", "CANARY_NOT_AUTHORIZED"]`.

- [ ] **Step 4: Add strict loader and mirrored Schema tests**

Test canonical bytes, duplicate-key rejection, float rejection, self-hash, no unknown properties, both schema copies byte-identical, and no credential/account/order URL fields.

Run: `PYTHONPATH=src python3 -m unittest tests.test_system_paper_plan -v`

Expected: PASS.

- [ ] **Step 5: Add the schema to deterministic build inputs and commit**

```bash
PYTHONPATH=src python3 scripts/update_evaluator_build.py
git add src/crypto_quant/system_paper_plan.py src/crypto_quant/schemas/system-paper-plan-v1.schema.json config/system-paper-plan-v1.schema.json tests/test_system_paper_plan.py src/crypto_quant/build.py config/evaluator-build-v1.json
git commit -m "feat: freeze credential-free system paper plan"
```

### Task 3: Build the deterministic simulated Broker

**Files:**
- Create: `src/crypto_quant/system_paper_broker.py`
- Create: `tests/test_system_paper_broker.py`
- Reference: `src/crypto_quant/orders.py`, `src/crypto_quant/execution.py`, `src/crypto_quant/instruments.py`

**Interfaces:**
- Consumes: `OrderAggregate`, `OrderEventType`, instrument tick/step filters, frozen BBO/trade evidence.
- Produces: `SimulatedBroker.submit(command, market) -> SimulatedOrderResult`; `SimulatedBroker.reconcile(local_order_id) -> SimulatedOrderResult`.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_partial_then_full_fill_is_idempotent(self):
    broker = SimulatedBroker(FillScenario.partial_then_full("0.40"))
    first = broker.submit(self.command, self.market)
    second = broker.reconcile(first.local_order_id)
    duplicate = broker.reconcile(first.local_order_id)
    self.assertEqual(first.state, OrderState.PARTIALLY_FILLED)
    self.assertEqual(second.state, OrderState.FILLED)
    self.assertEqual(duplicate.result_hash, second.result_hash)

def test_disconnect_after_submit_becomes_unknown_and_blocks_new_risk(self):
    broker = SimulatedBroker(FillScenario.disconnect_after_submit())
    result = broker.submit(self.command, self.market)
    self.assertEqual(result.state, OrderState.UNKNOWN)
    self.assertTrue(result.risk_lock_required)
```

Add rejection, cancel-before-fill, fill-before-cancel, duplicate event, out-of-order event, min-notional, tick/step, timeout and impossible overfill tests.

- [ ] **Step 2: Verify tests fail**

Run: `PYTHONPATH=src python3 -m unittest tests.test_system_paper_broker -v`

Expected: missing module failure.

- [ ] **Step 3: Implement pure deterministic Broker state**

```python
@dataclass(frozen=True)
class SimulatedOrderResult:
    local_order_id: str
    state: OrderState
    requested_quantity: Decimal
    cumulative_filled_quantity: Decimal
    average_fill_price: Optional[Decimal]
    fee_usdt: Decimal
    event_ids: Tuple[str, ...]
    risk_lock_required: bool
    result_hash: str
```

`SimulatedBroker` receives all market evidence and scenarios through constructor arguments, performs zero I/O, and derives IDs from canonical inputs. It must call `OrderAggregate.apply()` for every transition and reject any non-deterministic random source.

- [ ] **Step 4: Run Broker and neighboring execution tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_system_paper_broker tests.test_orders tests.test_execution tests.test_instruments -v
```

Expected: PASS, with no network patch required.

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/system_paper_broker.py tests/test_system_paper_broker.py
git commit -m "feat: add deterministic system paper broker"
```

### Task 4: Integrate decisions, risk, accounting and reconciliation

**Files:**
- Create: `src/crypto_quant/system_paper_runtime.py`
- Create: `config/system-paper-slot-result-v1.schema.json`
- Create: `src/crypto_quant/schemas/system-paper-slot-result-v1.schema.json`
- Create: `tests/test_system_paper_runtime.py`
- Modify: `src/crypto_quant/build.py`

**Interfaces:**
- Consumes: `SystemPaperPlan`, existing public capture, deterministic decision, `DrawdownPolicy`, `SimulatedBroker`, economic ledger contracts.
- Produces: `run_system_paper_slot(inputs: SystemPaperSlotInputs) -> Mapping[str, Any]`; `load_system_paper_slot_result(path: Path) -> Mapping[str, Any]`.

- [ ] **Step 1: Write failing complete-slot tests**

```python
def test_slot_records_signal_risk_order_fill_ledger_and_reconciliation(self):
    result = run_system_paper_slot(self.inputs)
    self.assertEqual(result["status"], "SYSTEM_PAPER_SLOT_COMPLETED")
    self.assertEqual(result["safety_counts"]["credential_reads"], 0)
    self.assertEqual(result["safety_counts"]["real_broker_calls"], 0)
    self.assertEqual(result["safety_counts"]["real_order_writes"], 0)
    self.assertEqual(result["reconciliation"]["unexplained_position_difference"], "0")
    self.assertEqual(result["replay"]["decision_hash_match"], True)
```

Add losing trade, rejected order, no-trade, partial fill, UNKNOWN, drawdown lock, duplicate slot and ledger imbalance cases.

- [ ] **Step 2: Verify tests fail**

Run: `PYTHONPATH=src python3 -m unittest tests.test_system_paper_runtime -v`

Expected: missing module failure.

- [ ] **Step 3: Implement the slot coordinator**

```python
@dataclass(frozen=True)
class SystemPaperSlotInputs:
    plan: Mapping[str, Any]
    scheduled_for: str
    public_market_bundle: Mapping[str, Any]
    previous_runtime_snapshot: Mapping[str, Any]
    fill_scenario: FillScenario
```

The coordinator uses one injected UTC timestamp, writes no file, includes every accepted/rejected signal, and emits balanced ledger entries plus a deterministic runtime snapshot. Any UNKNOWN or reconciliation difference sets `risk_state="LOCKED"` and forbids exposure increase.

- [ ] **Step 4: Add strict result loader, Schema mirror and replay tests**

Test no floats, no unknown properties, self-hash, parent hash continuity, slot identity, plan hash binding, account/order counters fixed at zero and full replay equality.

Run: `PYTHONPATH=src python3 -m unittest tests.test_system_paper_runtime tests.test_ledger tests.test_risk tests.test_orders -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
PYTHONPATH=src python3 scripts/update_evaluator_build.py
git add src/crypto_quant/system_paper_runtime.py src/crypto_quant/schemas/system-paper-slot-result-v1.schema.json config/system-paper-slot-result-v1.schema.json tests/test_system_paper_runtime.py src/crypto_quant/build.py config/evaluator-build-v1.json
git commit -m "feat: integrate system paper runtime"
```

### Task 5: Add crash-safe scheduling and failure injection

**Files:**
- Create: `src/crypto_quant/system_paper_scheduler.py`
- Create: `tests/test_system_paper_scheduler.py`
- Create: `tests/test_system_paper_fault_injection.py`
- Reference: `src/crypto_quant/paper_scheduler.py`, `src/crypto_quant/context_cycle_orchestrator.py`

**Interfaces:**
- Consumes: `run_system_paper_slot`, fixed 4h policy and owner-only SQLite path.
- Produces: `run_due_system_paper_slot(...) -> Mapping[str, Any]`; append-only event chain with `CLAIMED`, `INPUT_PREPARED`, `RESULT_PREPARED`, `SUCCEEDED`, `FAILED`, `MISSED`, `EXPIRED`.

- [ ] **Step 1: Write scheduler recovery tests**

Test exactly-once slot publication, crash after input prepare, crash after result prepare, stale lease recovery, duplicate worker, missed natural slot, expired slot and immutable terminal state.

- [ ] **Step 2: Write fault-injection safety tests**

```python
for fault in ("disconnect", "timeout", "duplicate", "out_of_order", "partial_fill", "disk_full"):
    result = run_fault_scenario(fault)
    self.assertEqual(result.real_order_writes, 0)
    self.assertIn(result.final_state, {"RECOVERED", "LOCKED", "FAILED_CLOSED"})
    self.assertTrue(result.ledger_balanced)
```

- [ ] **Step 3: Verify both suites fail**

Run: `PYTHONPATH=src python3 -m unittest tests.test_system_paper_scheduler tests.test_system_paper_fault_injection -v`

Expected: missing scheduler module failure.

- [ ] **Step 4: Implement WAL scheduler and injected write boundaries**

Use `BEGIN IMMEDIATE`, fsync-before-rename immutable result publication, no historical backfill, and a single network-attempt budget owned by the public input stage. Recovery must reuse prepared exact bytes and make zero additional requests.

- [ ] **Step 5: Run adjacent recovery tests and commit**

```bash
PYTHONPATH=src python3 -m unittest tests.test_system_paper_scheduler tests.test_system_paper_fault_injection tests.test_paper_scheduler tests.test_context_cycle_orchestrator -v
git add src/crypto_quant/system_paper_scheduler.py tests/test_system_paper_scheduler.py tests/test_system_paper_fault_injection.py
git commit -m "feat: add crash-safe system paper scheduling"
```

### Task 6: Add independent deployment, install and natural-start evidence

**Files:**
- Create: `src/crypto_quant/system_paper_launchd.py`
- Create: `src/crypto_quant/system_paper_launchd_cli.py`
- Create: `src/crypto_quant/system_paper_install.py`
- Create: `src/crypto_quant/system_paper_install_cli.py`
- Create: `src/crypto_quant/system_paper_observer.py`
- Create: `src/crypto_quant/system_paper_observer_cli.py`
- Create: `src/crypto_quant/system_paper_start_receipt.py`
- Create: `src/crypto_quant/system_paper_start_receipt_cli.py`
- Create: matching mirrored Schemas and four test files.

**Interfaces:**
- Consumes: frozen plan, reviewed private executable snapshot, fixed user-domain launchd paths.
- Produces: service `local.crypto-quant.system-paper-v1`; install receipt; first-natural-slot start receipt; production loaders.

- [ ] **Step 1: Write separation and permission tests**

Assert the Paper service, argv, DB, stdout/stderr, output root and receipts contain no Challenger paths; plist mode is `0600`; runtime roots are `0700`; environment contains no API key names; only loop-free CLI argv is accepted.

- [ ] **Step 2: Write observer and receipt tests**

Test WAITING before natural slot, VERIFIED only after exactly one natural slot, failure on missed slot/non-zero exit/stderr/changed input hashes, no receipt on pending, exact-byte no-overwrite publication and production-loader replay.

- [ ] **Step 3: Verify tests fail**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_system_paper_*' -v`

Expected: deployment modules missing while Tasks 2–5 tests remain green.

- [ ] **Step 4: Implement renderers, installer, observer and start receipt**

The installer may call `launchctl bootstrap` only after its separate preflight proves no existing service/path conflict. The observer and receipt publisher may only call `launchctl print`; neither may kickstart/bootstrap, call the Runner, make market requests or write scheduler state.

- [ ] **Step 5: Run focused and Challenger non-interference tests**

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_system_paper_*' -v
PYTHONPATH=src python3 -m unittest tests.test_challenger_forward_runner tests.test_challenger_launchd tests.test_challenger_cohort_evidence_maintenance -v
```

Expected: PASS; fixture counters show Challenger writes and invocations remain zero.

- [ ] **Step 6: Commit deployment code without installing it**

```bash
git add src/crypto_quant/system_paper_* config/system-paper-* tests/test_system_paper_* src/crypto_quant/build.py config/evaluator-build-v1.json
git commit -m "feat: add system paper deployment trust chain"
```

### Task 7: Build the fixed 90-day System Paper evaluator

**Files:**
- Create: `src/crypto_quant/system_paper_evaluation.py`
- Create: `src/crypto_quant/system_paper_evaluation_cli.py`
- Create: mirrored `system-paper-evaluation-v1.schema.json`
- Create: `tests/test_system_paper_evaluation.py`
- Modify: `src/crypto_quant/build.py`

**Interfaces:**
- Consumes: exact start receipt, plan, install receipt, launchd contract, all natural slot results and runtime snapshots.
- Produces: `evaluate_system_paper(...) -> Mapping[str, Any]` with `SYSTEM_PAPER_GATE_PASS`, `SYSTEM_PAPER_GATE_DID_NOT_PASS` or `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`.

- [ ] **Step 1: Write pre-tail blindness and completeness tests**

Before `start + 90 natural days`, the evaluator may output only duration, slot count, continuity, incidents and next required slot; it must not publish final PnL, drawdown or PASS. At tail it requires the complete expected slot set and rejects backfilled or replacement results.

- [ ] **Step 2: Write frozen gate tests**

Test zero duplicate orders, zero unrecorded fills, zero hard-risk violations, zero risk increase while unreconciled, 100% traceability, 100% replay, zero unexplained target difference, drawdown below 10%, cost upper bound within budget and fixed-cost monthly lower confidence bound above zero.

- [ ] **Step 3: Implement evaluator and strict loader**

The evaluator derives dates, slot IDs, capital, costs and metrics from trusted inputs. CLI accepts only seven absolute paths: plan, start receipt, install receipt, launchd contract, slot root, runtime root and output root. It accepts no clock, PnL, fee, date, label or filename overrides.

- [ ] **Step 4: Run tests and commit**

```bash
PYTHONPATH=src python3 -m unittest tests.test_system_paper_evaluation -v
PYTHONPATH=src python3 scripts/update_evaluator_build.py
git add src/crypto_quant/system_paper_evaluation.py src/crypto_quant/system_paper_evaluation_cli.py src/crypto_quant/schemas/system-paper-evaluation-v1.schema.json config/system-paper-evaluation-v1.schema.json tests/test_system_paper_evaluation.py src/crypto_quant/build.py config/evaluator-build-v1.json
git commit -m "feat: add fixed-tail system paper evaluation"
```

### Task 8: Build the tail-blind operations projection

**Files:**
- Create: `src/crypto_quant/operations_projection.py`
- Create: `config/operations-projection-v1.schema.json`
- Create: `src/crypto_quant/schemas/operations-projection-v1.schema.json`
- Create: `tests/test_operations_projection.py`

**Interfaces:**
- Consumes: Challenger and Paper production loaders through injected read-only adapters.
- Produces: `build_operations_projection(now, sources) -> Mapping[str, Any]` containing only allowlisted fields.

- [ ] **Step 1: Write redaction and provenance tests**

```python
def test_pre_tail_projection_excludes_challenger_economics(self):
    projection = build_operations_projection(self.pre_tail_now, self.sources)
    encoded = canonical_json(projection)
    for forbidden in ("pnl", "return", "win_rate", "drawdown", "profit"):
        self.assertNotIn(forbidden, encoded.lower())
    self.assertEqual(projection["challenger"]["evidence_health"], "VERIFIED")
```

Also test stale source, loader failure, Paper-not-started, dual-running, incident and final-gate states. Every displayed value includes source artifact hash and observed timestamp.

- [ ] **Step 2: Verify missing module failure**

Run: `PYTHONPATH=src python3 -m unittest tests.test_operations_projection -v`

- [ ] **Step 3: Implement an explicit allowlist projection**

Never serialize arbitrary source mappings. Construct the output field-by-field: release identity, service health, Challenger verified slots/Episodes/next slot, Paper phase/days/slots/order counts/reconciliation/risk/alerts, and gate status.

- [ ] **Step 4: Run tests and commit**

```bash
PYTHONPATH=src python3 -m unittest tests.test_operations_projection -v
git add src/crypto_quant/operations_projection.py src/crypto_quant/schemas/operations-projection-v1.schema.json config/operations-projection-v1.schema.json tests/test_operations_projection.py
git commit -m "feat: add tail-blind operations projection"
```

### Task 9: Build the local read-only Web dashboard

**Files:**
- Create: `src/crypto_quant/operations_dashboard.py`
- Create: `src/crypto_quant/dashboard/index.html`
- Create: `src/crypto_quant/dashboard/app.js`
- Create: `src/crypto_quant/dashboard/styles.css`
- Create: `tests/test_operations_dashboard.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `build_operations_projection()` or a loader-verified projection snapshot.
- Produces: `GET /`, `GET /app.js`, `GET /styles.css`, `GET /api/v1/status`; all other paths/methods fail closed.

- [ ] **Step 1: Write server boundary tests**

Test binding rejects any host except `127.0.0.1`; POST/PUT/PATCH/DELETE return 405; unknown GET returns 404; path traversal returns 400; API response uses `Cache-Control: no-store`; server module imports no Runner, scheduler, install or Broker module.

- [ ] **Step 2: Verify missing module failure**

Run: `PYTHONPATH=src python3 -m unittest tests.test_operations_dashboard -v`

- [ ] **Step 3: Implement the loopback HTTP server**

Use `http.server.ThreadingHTTPServer`; inject the projection provider; set CSP `default-src 'self'`; set `X-Content-Type-Options: nosniff`; do not add dependencies, cookies, authentication, WebSocket or write endpoints.

- [ ] **Step 4: Implement the four read-only views**

The HTML contains stable regions `project-summary`, `challenger-timeline`, `paper-runtime`, `risk-alerts`. JavaScript fetches `/api/v1/status`, renders text using `textContent`, shows stale/failed evidence prominently, and never uses `innerHTML` with source values.

- [ ] **Step 5: Run unit and manual local smoke**

```bash
PYTHONPATH=src python3 -m unittest tests.test_operations_projection tests.test_operations_dashboard -v
PYTHONPATH=src python3 -m crypto_quant.operations_dashboard --fixture tests/fixtures/operations-projection-healthy.json --port 8765
```

Expected: only `http://127.0.0.1:8765` responds; four views render; no write control exists. Stop the fixture server after the check.

- [ ] **Step 6: Commit**

```bash
git add src/crypto_quant/operations_dashboard.py src/crypto_quant/dashboard tests/test_operations_dashboard.py pyproject.toml
git commit -m "feat: add local read-only operations dashboard"
```

### Task 10: Add operational alerts and runbooks

**Files:**
- Create: `src/crypto_quant/operations_alerts.py`
- Create: `tests/test_operations_alerts.py`
- Create: `docs/runbooks/system-paper-operations.md`
- Create: `docs/runbooks/operations-dashboard.md`

**Interfaces:**
- Consumes: operations projection.
- Produces: deterministic local alert records with severity `INFO`, `WARNING`, `CRITICAL`; no external messaging integration.

- [ ] **Step 1: Write alert classification tests**

Map stale evidence, missed slot, non-zero exit, UNKNOWN order, reconciliation difference, risk violation, disk pressure and loader failure to fixed severity and stable alert IDs. Repeated identical state returns the same alert ID.

- [ ] **Step 2: Implement deterministic alert projection**

Alerts are data only; the module cannot send email, Slack, SMS or place orders. `CRITICAL` always includes `new_risk_allowed=false` in the Paper projection.

- [ ] **Step 3: Write exact runbooks**

System Paper runbook contains preflight, natural-start observation, daily read-only check, incident evidence capture, prohibited remediation, recovery acceptance and 90-day final evaluation. Dashboard runbook contains loopback startup, health check, shutdown, stale-state interpretation and prohibition on public exposure.

- [ ] **Step 4: Test and commit**

```bash
PYTHONPATH=src python3 -m unittest tests.test_operations_alerts tests.test_operations_projection -v
git add src/crypto_quant/operations_alerts.py tests/test_operations_alerts.py docs/runbooks/system-paper-operations.md docs/runbooks/operations-dashboard.md
git commit -m "feat: add system paper operations alerts"
```

### Task 11: Release engineering and full verification

**Files:**
- Modify: `README.md`
- Create: `docs/implementation-status-v0.54.0.md` 至 `docs/implementation-status-v0.61.0.md`
- Create: `docs/adr/0054-*.md` 至 `docs/adr/0061-*.md`
- Modify: `pyproject.toml`, `src/crypto_quant_core.egg-info/PKG-INFO`, `config/evaluator-build-v1.json`

**Interfaces:**
- Consumes: completed tasks 1–10.
- Produces: independently reviewed semantic releases; no runtime install until deployment release passes.

- [ ] **Step 1: Split releases by reviewer-safe boundary**

Release order is fixed：

1. `v0.54.0`：并行交付设计、执行计划与 readiness audit；
2. `v0.55.0`：冻结 credential-free System Paper plan；
3. `v0.56.0`：模拟 Broker 与完整 slot runtime；
4. `v0.57.0`：WAL scheduler 与故障注入；
5. `v0.58.0`：deployment/install/observer/start-receipt 信任链；
6. `v0.59.0`：固定 90 天 System Paper evaluator；
7. `v0.60.0`：tail-blind operations projection；
8. `v0.61.0`：本机只读 Web、alerts 与 runbooks。

不得把 runtime install 与未经审查的代码创建合并在同一个不可逆步骤中。

- [ ] **Step 2: Run verification for each release**

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m compileall -q src tests scripts
make validate
```

Expected: all tests and technical validators pass; release policy still reports deliberate production activation disabled.

- [ ] **Step 3: Verify deterministic build and forbidden imports**

```bash
PYTHONPATH=src python3 scripts/validate_evaluator_build.py
rg -n "api[_-]?key|secret|create_order|cancel_order" src/crypto_quant/system_paper_* src/crypto_quant/operations_*
```

Expected: build passes; any regex match appears only in explicit rejection/absence checks, never a credential or real-order implementation.

- [ ] **Step 4: Use the existing GitHub release workflow**

Create a Draft PR, wait for PR CI, merge only on success, wait for main CI, then create an annotated tag exactly at merged main. Re-read repository, origin and ADMIN permission before every push.

### Task 12: Update the current heartbeat in place

**Files:**
- Modify through Codex automation API only: `$CODEX_HOME/automations/challenger/automation.toml`
- Reference: frozen design and this plan.

**Interfaces:**
- Consumes: current active task id, existing automation id `challenger`.
- Produces: one active heartbeat bound to the current task, daily at Beijing 08:25, coordinating Phases A–D; no project or runtime data migration.

- [ ] **Step 1: View and identify the existing automation**

Use the automation API in `view` mode for id `challenger`. Confirm it is a heartbeat and record its current target, status and schedule without running it.

- [ ] **Step 2: Update, do not duplicate**

Use the automation API in `update` mode. Preserve id `challenger` and its already-correct current task target, keep daily Beijing 08:25, and replace only the prompt/name needed for the frozen two-stream/four-phase policy. The prompt must require `superpowers:using-superpowers`, then design/plan/TDD/verification skills as applicable to each future implementation turn.

- [ ] **Step 3: Verify the stored automation**

View id `challenger` again. Confirm exactly one active heartbeat, current task binding, daily 08:25 schedule, both evidence streams, Paper readiness work, Web parallel work, no Runner/maintenance manual trigger, no real trading, and fail-closed behavior.

- [ ] **Step 4: Perform a side-effect audit**

Compare repository status, Challenger SQLite/stat hashes, stdout/stderr and LaunchAgent run counts before and after the automation update. Expected: automation metadata changes only; runtime and repository evidence do not change.

### Task 13: Start execution without waiting for the 90-day windows

**Files:**
- Follow Tasks 1–11 and the frozen design.

**Interfaces:**
- Consumes: verified in-place heartbeat update.
- Produces: continuous engineering progress while Challenger continues naturally; later, an independently qualified System Paper start.

- [ ] **Step 1: Begin with Task 1 on an isolated implementation worktree**

Use `superpowers:using-git-worktrees`, then `superpowers:executing-plans`. Do not run implementation work in the Challenger runtime directories.

- [ ] **Step 2: Keep the critical path ahead of Web polish**

At each checkpoint, finish the earliest blocking Paper gate before optional dashboard styling. Web projection/security work may proceed when it does not share mutable code or interfaces.

- [ ] **Step 3: Install only a reviewed deployment release**

After Tasks 2–6 have passed full CI and the install preflight is clean, install System Paper separately. The first natural successful slot creates its start receipt; that timestamp, not the engineering start date, begins the 90-day Paper window.

- [ ] **Step 4: Monitor both windows independently**

The daily heartbeat reports Challenger and Paper separately. A failure in one stream never rewrites, replaces or borrows evidence from the other. Only both final gates passing permits a new Canary design discussion.
