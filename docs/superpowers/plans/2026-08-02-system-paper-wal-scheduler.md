# System Paper WAL Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 v0.56 确定性单槽 runtime 增加独立、崩溃安全、不可回填且经济 exactly-once 的 SQLite WAL 调度层和冻结故障注入矩阵。

**Architecture:** 新模块维护 System Paper 专属的只追加 event/input/result 三表状态机，以 `BEGIN IMMEDIATE` 和租约串行化 worker；输入与结果分别在执行和发布前封存 exact canonical bytes。顶层 runner 只从 durable stage 恢复，使用 v0.56 完整 bytes loader 重放父链，并通过现有安全 immutable publisher 完成 fsync/no-overwrite 发布。

**Tech Stack:** Python 3.9+、标准库 `sqlite3`/`hashlib`/`json`、SQLite WAL、现有 canonical/evidence/runtime/publisher 原语、`unittest`、GitHub Actions Python 3.9/3.12。

## Global Constraints

- 冻结规格：`docs/superpowers/specs/2026-08-02-system-paper-wal-scheduler-design.md`。
- 权威基线：`v0.56.0` / `2bdd3aee51c8c48941d71ded90904a885353f790`。
- 固定 4h UTC cadence、5 分钟 close delay、15 分钟 lease、禁止 historical backfill。
- schedule slot id 必须逐字节等于 v0.56 `system_paper_slot` identity。
- 每次未准备 invocation 最多一次 provider capture；capture 固定四个 allowlisted public GET；prepared 后 provider/network 均为零。
- event、prepared input 和 prepared result 全部只追加，UPDATE/DELETE 永久禁止。
- result 必须通过 strict canonical bytes、Schema、hash、ledger、full replay 和完整 parent-chain 验证。
- prepared result 后不得重跑 runtime；发布后崩溃必须采用相同 bytes。
- 首槽使用 exact genesis；后续只允许相邻真实成功父槽，任何缺槽失败关闭。
- `production_activation.enabled=false`；credential/account/real Broker/real order 固定 `0/0/0/0`。
- 不实现 CLI、LaunchAgent、安装、observer、start receipt、公开市场 transport 或 90 天 evaluator。
- 不触碰 Challenger runtime/state/log/bundle/evidence root，不安装或启动 System Paper。
- 每个任务使用 TDD：先红灯、再最小实现、聚焦/相邻验证、独立 commit。

---

## File Structure

- `src/crypto_quant/system_paper_scheduler.py`：policy、slot、event projection、WAL state、prepared blobs、fault injector 和顶层 runner；不实现 HTTP 或 CLI。
- `src/crypto_quant/system_paper_runtime.py`：新增 exact-bytes production loader；现有 path loader 委托它，单槽语义不变。
- `tests/test_system_paper_scheduler.py`：时序、WAL、租约、prepared stages、父链、发布和 exactly-once 测试。
- `tests/test_system_paper_fault_injection.py`：冻结 failpoint/ENOSPC/provider/order 场景矩阵。
- `tests/test_system_paper_runtime.py`：bytes loader 与既有 path loader 的等价回归。
- `src/crypto_quant/build.py`、`scripts/refresh_evaluator_build_manifest.py`、`config/evaluator-build-manifest-v1.json`：新 production module/test 与 v0.57 build identity。
- `README.md`、`docs/adr/0057-system-paper-wal-scheduler.md`、`docs/implementation-status-v0.57.0.md`：真实交付状态和下一门。
- `pyproject.toml`、`setup.py`、`src/crypto_quant/__init__.py`、`tests/test_estimators.py`：`0.57.0` / manifest `1.51.0` 版本绑定。

---

### Task 1: Freeze policy, event chain, leases, and gaps

**Files:**
- Create: `src/crypto_quant/system_paper_scheduler.py`
- Create: `tests/test_system_paper_scheduler.py`
- Reference: `src/crypto_quant/paper_scheduler.py`
- Reference: `src/crypto_quant/system_paper_runtime.py`
- Reference: `src/crypto_quant/system_paper_plan.py`

**Interfaces:**
- Consumes: `system_paper_plan_reasons(plan)`, `stable_id`, `business_hash`, `canonical_json`, `utc_datetime`.
- Produces: `SystemPaperScheduleError`, `SystemPaperSlot`, `SystemPaperSchedulePolicy.create(plan)`, `SystemPaperClaim`, `SystemPaperScheduleState` with `events()`, `slot_projection()`, `verify_integrity()`, `record_gaps()`, and `claim()`.

- [ ] **Step 1: Write missing-module and fixed-policy tests**

Add tests asserting constructor rejection, fixed 4h/5m/15m policy, slot identity equality with v0.56, and invalid non-boundary times:

```python
class SystemPaperSchedulePolicyTests(unittest.TestCase):
    def test_policy_is_fixed_and_slot_identity_matches_runtime(self):
        plan = build_system_paper_plan()
        policy = SystemPaperSchedulePolicy.create(plan)
        slot = policy.current_slot("2026-08-02T12:05:11.000Z")
        self.assertEqual(policy.cadence_seconds, 14_400)
        self.assertEqual(policy.close_delay_seconds, 300)
        self.assertEqual(policy.lease_seconds, 900)
        self.assertFalse(policy.historical_backfill_allowed)
        self.assertEqual(
            slot.slot_id,
            stable_id(
                "system_paper_slot",
                {
                    "plan_hash": plan["plan_hash"],
                    "scheduled_for": "2026-08-02T12:00:00.000Z",
                },
            ),
        )

    def test_policy_rejects_direct_construction_and_plan_override(self):
        with self.assertRaises(TypeError):
            SystemPaperSchedulePolicy()
        changed = deepcopy(build_system_paper_plan())
        changed["scope"]["symbol"] = "BTCUSDT"
        with self.assertRaises(SystemPaperScheduleError):
            SystemPaperSchedulePolicy.create(changed)
```

- [ ] **Step 2: Run the policy tests and preserve the red light**

Run:

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_system_paper_scheduler.SystemPaperSchedulePolicyTests -v
```

Expected: FAIL with `ModuleNotFoundError: crypto_quant.system_paper_scheduler`.

- [ ] **Step 3: Implement policy, slot, time, worker, and path validators**

Implement immutable token-gated types. `current_slot(now)` subtracts the 5-minute close delay before flooring to the 4h UTC anchor. `slot_from_scheduled()` rejects non-4h boundaries. `_validate_state_path()` rejects symlinks/non-regular files/hardlinks and only creates the immediate parent directory.

```python
@dataclass(frozen=True, init=False)
class SystemPaperSlot:
    slot_id: str
    scheduled_for: str
    due_at: str
    expires_at: str

@dataclass(frozen=True, init=False)
class SystemPaperSchedulePolicy:
    plan_hash: str
    schedule_policy_hash: str
    cadence_seconds: int
    close_delay_seconds: int
    lease_seconds: int
    historical_backfill_allowed: bool

    @classmethod
    def create(cls, plan: Mapping[str, Any]) -> "SystemPaperSchedulePolicy": ...
    def slot_from_scheduled(self, scheduled_for: object) -> SystemPaperSlot: ...
    def current_slot(self, now: object) -> SystemPaperSlot: ...
```

- [ ] **Step 4: Add WAL, immutability, claim, and gap tests**

Add exact tests:

```python
def test_state_is_wal_full_sync_and_all_tables_are_immutable(self):
    with SystemPaperScheduleState(self.state_path, self.policy) as state:
        claim = state.claim(self.slot, worker_id="worker-a", claimed_at=self.now)
        self.assertEqual(claim.outcome, "CLAIMED")
        self.assertEqual(state.connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(state.connection.execute("PRAGMA synchronous").fetchone()[0], 2)
        trigger_names = {
            row[0] for row in state.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        }
        self.assertEqual(trigger_names, {
            "schedule_events_no_update", "schedule_events_no_delete",
            "prepared_inputs_no_update", "prepared_inputs_no_delete",
            "prepared_results_no_update", "prepared_results_no_delete",
        })
        with self.assertRaises(sqlite3.DatabaseError):
            state.connection.execute("DELETE FROM schedule_events")

def test_live_lease_is_busy_and_stale_lease_is_reclaimed(self):
    first = self.claim("worker-a", "2026-08-02T12:05:11.000Z")
    busy = self.claim("worker-b", "2026-08-02T12:10:00.000Z")
    reclaimed = self.claim("worker-b", "2026-08-02T12:21:00.000Z")
    self.assertEqual((first.attempt, busy.outcome, reclaimed.attempt), (1, "BUSY", 2))

def test_first_boot_does_not_backfill_and_later_unknown_slots_are_missed(self):
    first = self.policy.current_slot("2026-08-02T04:05:11.000Z")
    later = self.policy.current_slot("2026-08-02T16:05:11.000Z")
    with SystemPaperScheduleState(self.state_path, self.policy) as state:
        state.record_gaps(first, recorded_at="2026-08-02T04:05:11.000Z")
        state.claim(first, worker_id="worker-a", claimed_at="2026-08-02T04:05:11.000Z")
        self.assertEqual({row["slot_id"] for row in state.events()}, {first.slot_id})
        state.record_gaps(later, recorded_at="2026-08-02T16:05:11.000Z")
        missed = [
            item for item in state.slot_projection().values()
            if item["terminal_state"] == "MISSED"
        ]
    self.assertEqual([item["scheduled_for"] for item in missed], [
        "2026-08-02T08:00:00.000Z",
        "2026-08-02T12:00:00.000Z",
    ])
```

Also test two SQLite connections, event time monotonicity, event payload/hash tampering, illegal transitions, current-window retry after `FAILED`, expired unprepared slot, and terminal `MISSED/EXPIRED/SUCCEEDED` immutability.

- [ ] **Step 5: Implement append-only schema, event projector, gap recorder, and claim**

Create three tables with UPDATE/DELETE triggers. `_append_locked()` canonicalizes payload, binds sequential event/hash identity, and runs only inside `BEGIN IMMEDIATE`. Projection stores `attempt_status`, `durable_stage`, `active_claim`, attempt count and terminal state. `claim()` returns only `CLAIMED`, `RESUME_INPUT`, `RESUME_RESULT`, `BUSY`, `ALREADY_SUCCEEDED`, or `TERMINAL_INELIGIBLE`.

```python
@dataclass(frozen=True)
class SystemPaperClaim:
    outcome: str
    slot: SystemPaperSlot
    worker_id: str
    attempt: int
    claimed_at: str
    lease_expires_at: str
    durable_stage: str

class SystemPaperScheduleState:
    def events(self) -> Tuple[Dict[str, Any], ...]: ...
    def slot_projection(self) -> Dict[str, Dict[str, Any]]: ...
    def verify_integrity(self) -> str: ...
    def record_gaps(self, current_slot: SystemPaperSlot, *, recorded_at: object) -> None: ...
    def claim(self, slot: SystemPaperSlot, *, worker_id: str, claimed_at: object) -> SystemPaperClaim: ...
```

- [ ] **Step 6: Run policy/state tests and adjacent scheduler tests**

Run:

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_system_paper_scheduler.SystemPaperSchedulePolicyTests \
  tests.test_system_paper_scheduler.SystemPaperScheduleStateTests \
  tests.test_paper_scheduler.PaperScheduleStateTests -v
```

Expected: PASS; no System Paper test imports a network transport.

- [ ] **Step 7: Commit the state-machine primitive**

```bash
git add src/crypto_quant/system_paper_scheduler.py tests/test_system_paper_scheduler.py
git commit -m "feat: add system paper WAL state machine"
```

### Task 2: Persist and recover exact public input bytes

**Files:**
- Modify: `src/crypto_quant/system_paper_scheduler.py`
- Modify: `tests/test_system_paper_scheduler.py`
- Reference: `src/crypto_quant/system_paper_broker.py`
- Reference: `tests/test_system_paper_runtime.py`

**Interfaces:**
- Consumes: `FillScenario`, `fill_scenario_payload()`, `build_initial_system_paper_runtime_snapshot()`.
- Produces: `SystemPaperInputRequest`, `SystemPaperInputCapture`, `SystemPaperScheduleState.prepare_input()`, `load_prepared_input()`, and canonical input envelope bytes.

- [ ] **Step 1: Add failing capture-boundary tests**

Define the expected public types in tests:

```python
def test_input_prepare_is_atomic_exact_and_allowlisted(self):
    claim = self.claim_current()
    capture = SystemPaperInputCapture(
        public_market_bundle=self.market_bundle,
        capture_attempt_id="capture-20260802t120511z",
        captured_at="2026-08-02T12:05:11.000Z",
        request_families=(
            "SPOT_AGG_TRADE",
            "SPOT_BBO",
            "SPOT_EXCHANGE_INFO",
            "SPOT_KLINE_4H_WARMUP",
        ),
        network_request_count=4,
    )
    prepared = self.state.prepare_input(
        claim,
        plan=self.plan,
        capture=capture,
        previous_runtime_snapshot=build_initial_system_paper_runtime_snapshot(self.plan),
        fill_scenario=FillScenario.immediate_full(),
        output_root_hash=self.output_root_hash,
        prepared_at=capture.captured_at,
    )
    loaded = self.state.load_prepared_input(claim.slot)
    self.assertEqual(hashlib.sha256(loaded["input_bytes"]).hexdigest(), prepared["input_sha256"])
    self.assertEqual(self.state.slot_projection()[claim.slot.slot_id]["durable_stage"], "INPUT")
```

Add rejection tests for missing/duplicate/reordered/extra request families, counts other than 4, private/account/Broker family, stale captured_at, bundle `observed_at` mismatch, changed plan/bundle/fill/snapshot/output-root hash, and binary float/noncanonical envelope.
After one input row exists, assert UPDATE and DELETE on `prepared_inputs` both raise
`sqlite3.DatabaseError`; Task 3 performs the equivalent check for `prepared_results`.

- [ ] **Step 2: Run capture tests and verify the red light**

Run:

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_system_paper_scheduler.SystemPaperPreparedInputTests -v
```

Expected: FAIL because capture types and `prepare_input` do not exist.

- [ ] **Step 3: Implement capture types and atomic input preparation**

Use frozen dataclasses. `SystemPaperInputRequest` is derived from policy/plan/slot and contains no paths or credentials. `prepare_input()` validates the exact allowlist and active capture window, constructs this envelope, and inserts `INPUT_PREPARED` plus one `prepared_inputs` row in the same transaction:

```python
{
    "schema_version": "1.0.0",
    "slot_id": claim.slot.slot_id,
    "schedule_policy_hash": policy.policy_hash,
    "plan": plan,
    "scheduled_for": claim.slot.scheduled_for,
    "capture": capture_payload,
    "previous_runtime_snapshot": previous_runtime_snapshot,
    "fill_scenario": fill_scenario_payload(fill_scenario),
    "output_root_hash": output_root_hash,
}
```

`load_prepared_input()` revalidates event/blob set, SHA-256 and all embedded business hashes before returning bytes/payload.

```python
@dataclass(frozen=True)
class SystemPaperInputRequest:
    plan_hash: str
    slot_id: str
    scheduled_for: str
    capture_deadline: str
    request_families: Tuple[str, ...]

@dataclass(frozen=True)
class SystemPaperInputCapture:
    public_market_bundle: Mapping[str, Any]
    capture_attempt_id: str
    captured_at: str
    request_families: Tuple[str, ...]
    network_request_count: int

def prepare_input(
    self,
    claim: SystemPaperClaim,
    *,
    plan: Mapping[str, Any],
    capture: SystemPaperInputCapture,
    previous_runtime_snapshot: Mapping[str, Any],
    fill_scenario: FillScenario,
    output_root_hash: str,
    prepared_at: object,
) -> Mapping[str, Any]: ...
```

- [ ] **Step 4: Add and pass durable-input recovery tests**

Test that a failed attempt after input commit, or an expired lease, yields `RESUME_INPUT`; loaded bytes remain identical; a second input insert is rejected; recovery after the active window is allowed only when the input row already exists.

Run:

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_system_paper_scheduler.SystemPaperPreparedInputTests -v
```

Expected: PASS.

- [ ] **Step 5: Commit exact input persistence**

```bash
git add src/crypto_quant/system_paper_scheduler.py tests/test_system_paper_scheduler.py
git commit -m "feat: persist system paper slot inputs"
```

### Task 3: Add exact-bytes runtime loader and durable result parent chain

**Files:**
- Modify: `src/crypto_quant/system_paper_runtime.py`
- Modify: `tests/test_system_paper_runtime.py`
- Modify: `src/crypto_quant/system_paper_scheduler.py`
- Modify: `tests/test_system_paper_scheduler.py`

**Interfaces:**
- Consumes: `run_system_paper_slot(SystemPaperSlotInputs)`, existing strict path loader.
- Produces: `load_system_paper_slot_result_bytes(body: bytes, *, parent_result_bodies: Tuple[bytes, ...] = ()) -> Dict[str, Any]`, `SystemPaperScheduleState.prepare_result()`, `load_prepared_result()`, and `successful_parent_result_bodies()`.

- [ ] **Step 1: Write failing bytes-loader equivalence tests**

```python
def test_bytes_loader_matches_path_loader_and_replays_full_parent_chain(self):
    first = run_system_paper_slot(self.first_inputs)
    second = run_system_paper_slot(self.second_inputs(first["runtime_snapshot"]))
    first_body = canonical_json(first).encode("utf-8")
    second_body = canonical_json(second).encode("utf-8")
    loaded = load_system_paper_slot_result_bytes(
        second_body,
        parent_result_bodies=(first_body,),
    )
    self.assertEqual(loaded, second)
```

Add duplicate-key, binary float, noncanonical bytes, missing/extra/reordered parent bodies, parent tampering and newline-canonical acceptance tests. Existing `load_system_paper_slot_result(path, parent_result_paths=...)` must return exactly the same mapping.

- [ ] **Step 2: Run the new runtime loader tests and preserve the red light**

Run:

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_system_paper_runtime.SystemPaperRuntimeLoaderTests -v
```

Expected: FAIL importing `load_system_paper_slot_result_bytes`.

- [ ] **Step 3: Refactor the path loader through the bytes loader**

Move canonical bytes parsing and ordered `_verify_loaded_slot` replay into the new function. The path loader reads each validated absolute regular path as bytes and delegates. Do not change slot construction, hashes, ledger, risk or replay semantics.

```python
def load_system_paper_slot_result_bytes(
    body: bytes,
    *,
    parent_result_bodies: Tuple[bytes, ...] = (),
) -> Dict[str, Any]:
    expected_parent = None
    for parent_body in parent_result_bodies:
        parent = _load_slot_body(parent_body)
        _verify_loaded_slot(parent, expected_parent)
        expected_parent = parent
    result = _load_slot_body(body)
    _verify_loaded_slot(result, expected_parent)
    return result
```

- [ ] **Step 4: Run all runtime/broker tests**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_system_paper_runtime tests.test_system_paper_broker -v
```

Expected: PASS with the existing count plus the new loader cases.

- [ ] **Step 5: Write failing prepared-result and continuity tests**

Add tests that prepare one result from one exact input, reject any changed result bytes, and derive the next input only from all prior `SUCCEEDED` bodies:

```python
def test_result_prepare_replays_input_and_full_parent_chain(self):
    claim, input_record = self.prepare_first_input()
    result = run_system_paper_slot(self.inputs_from(input_record))
    record = self.state.prepare_result(
        claim,
        result_bytes=canonical_json(result).encode("utf-8"),
        parent_result_bodies=(),
        prepared_at=self.now,
    )
    self.assertEqual(record["slot_hash"], result["slot_hash"])
    self.assertEqual(self.state.slot_projection()[claim.slot.slot_id]["durable_stage"], "RESULT")
```

Also test exact genesis, two- and three-slot parent chains, a missing adjacent natural slot, MISSED/EXPIRED predecessor, missing artifact, altered parent bytes, output-root mismatch, loader failure, unbalanced ledger, and UNKNOWN requiring both `risk_state=LOCKED` and an active order.

- [ ] **Step 6: Implement prepared result and parent-chain derivation**

`prepare_result()` loads exact input bytes, reconstructs its expected replay inputs, then calls the bytes loader with the complete prior chain. The loader's mandatory pure replay proves the supplied candidate bytes match that input; do not perform a second candidate run outside the loader. Insert `RESULT_PREPARED` and `prepared_results` atomically. `successful_parent_result_bodies()` walks ordered schedule slots, requires 4h adjacency and `SUCCEEDED`, reads exact immutable artifacts, and replays the whole chain before returning it.

```python
def prepare_result(
    self,
    claim: SystemPaperClaim,
    *,
    result_bytes: bytes,
    parent_result_bodies: Tuple[bytes, ...],
    prepared_at: object,
) -> Mapping[str, Any]: ...

def load_prepared_result(self, slot: SystemPaperSlot) -> Dict[str, Any]: ...

def successful_parent_result_bodies(
    self,
    slot: SystemPaperSlot,
    *,
    output_root: Path,
) -> Tuple[bytes, ...]: ...
```

- [ ] **Step 7: Run prepared-result and adjacent runtime tests**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_system_paper_scheduler.SystemPaperPreparedResultTests \
  tests.test_system_paper_runtime tests.test_system_paper_broker -v
```

Expected: PASS.

- [ ] **Step 8: Commit the bytes trust chain**

```bash
git add src/crypto_quant/system_paper_runtime.py tests/test_system_paper_runtime.py \
  src/crypto_quant/system_paper_scheduler.py tests/test_system_paper_scheduler.py
git commit -m "feat: bind system paper scheduler result chain"
```

### Task 4: Orchestrate exact-once publication and recovery

**Files:**
- Modify: `src/crypto_quant/system_paper_scheduler.py`
- Modify: `tests/test_system_paper_scheduler.py`
- Modify: `src/crypto_quant/market_data_cli.py`
- Modify: `tests/test_market_data_cli.py`

**Interfaces:**
- Consumes: Tasks 1–3 state methods, `run_system_paper_slot`, `_publish_immutable`.
- Produces: backward-compatible optional publisher hooks, `SystemPaperInjectedFault`, `SystemPaperFaultInjector`, `run_due_system_paper_slot(...) -> Mapping[str, Any]`, `SystemPaperScheduleState.fail()`, and `succeed()`.

- [ ] **Step 1: Write failing end-to-end exactly-once tests**

```python
def test_run_then_same_slot_is_zero_capture_zero_runtime_idempotent(self):
    provider = RecordingProvider(self.capture)
    first = run_due_system_paper_slot(
        state_path=self.state_path,
        output_root=self.output_root,
        plan=self.plan,
        worker_id="worker-a",
        public_input_provider=provider,
        fill_scenario=FillScenario.immediate_full(),
        clock=lambda: self.now,
    )
    bomb = BombProvider()
    second = run_due_system_paper_slot(
        state_path=self.state_path,
        output_root=self.output_root,
        plan=self.plan,
        worker_id="worker-b",
        public_input_provider=bomb,
        fill_scenario=FillScenario.immediate_full(),
        clock=lambda: self.now,
    )
    self.assertEqual(first["outcome"], "EXECUTED")
    self.assertEqual(second["outcome"], "ALREADY_SUCCEEDED")
    self.assertEqual((second["provider_invocation_count"], second["network_request_count"], second["candidate_runtime_invocation_count"]), (0, 0, 0))
    self.assertEqual(Path(first["result_path_or_null"]).read_bytes(), Path(second["result_path_or_null"]).read_bytes())
```

Add live `BUSY`, terminal ineligible, output-root binding, one injected clock read, and returned safety-count tests.
Also assert an empty `SystemPaperFaultInjector({})` is inert, `CRASH` raises
`SystemPaperInjectedFault`, `ENOSPC` raises `OSError` with `errno.ENOSPC`, and unknown point/mode
construction is rejected.

- [ ] **Step 2: Run the runner tests and verify the red light**

Run:

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_system_paper_scheduler.SystemPaperScheduleRunnerTests -v
```

Expected: FAIL because `run_due_system_paper_slot` does not exist.

- [ ] **Step 3: Implement the fixed nine-stage runner**

Implement exactly the frozen order: sample clock once; verify/derive; record gaps; claim; capture-or-load input; run-or-load result; full bytes replay; immutable publish to `system-paper-slots/<slot_id>.json`; succeed; return summary. Use `_publish_immutable(..., output_directory="system-paper-slots")` and verify the final file body again before `SUCCEEDED`.

Extend the internal publisher with two optional, default-`None` callbacks: `after_first_write` is called
after the first positive `os.write` and before fsync; `after_payload_fsync` is called after file fsync and
identity verification but before the no-overwrite link commit. Existing callers pass neither callback and
must remain byte-for-byte behaviorally unchanged. Add focused `test_market_data_cli` cases proving default
publication and conflicts are unchanged, and proving each callback exception leaves no final artifact.

```python
class SystemPaperInjectedFault(RuntimeError):
    pass

@dataclass(frozen=True, init=False)
class SystemPaperFaultInjector:
    points: Mapping[str, str]

    def __init__(self, points: Mapping[str, str]):
        # Validate against the frozen point/mode sets and store a defensive copy.
        object.__setattr__(self, "points", MappingProxyType(dict(points)))

    def maybe_raise(self, point: str) -> None:
        mode = self.points.get(point)
        if mode == "CRASH":
            raise SystemPaperInjectedFault(point)
        if mode == "ENOSPC":
            raise OSError(errno.ENOSPC, point)

def run_due_system_paper_slot(
    *,
    state_path: Path,
    output_root: Path,
    plan: Mapping[str, Any],
    worker_id: str,
    public_input_provider: Callable[
        [SystemPaperInputRequest], SystemPaperInputCapture
    ],
    fill_scenario: FillScenario,
    clock: Callable[[], str],
    fault_injector: Optional[SystemPaperFaultInjector] = None,
) -> Mapping[str, Any]: ...
```

An `EXECUTED` response has this exact value shape (hash/path values are derived, never caller inputs):

```python
{
    "outcome": "EXECUTED",
    "slot_id": slot.slot_id,
    "provider_invocation_count": 1,
    "network_request_count": 4,
    "candidate_runtime_invocation_count": 1,
    "loader_replay_count": 1,
    "result_path_or_null": str(result_path.resolve()),
    "result_sha256_or_null": hashlib.sha256(result_bytes).hexdigest(),
    "slot_hash_or_null": result["slot_hash"],
    "runtime_snapshot_hash_or_null": result["runtime_snapshot"]["snapshot_hash"],
    "risk_state_or_null": result["runtime_snapshot"]["risk_state"],
    "safety_counts": {
        "credential_reads": 0,
        "account_requests": 0,
        "real_broker_calls": 0,
        "real_order_writes": 0,
    },
}
```

`RESUMED_INPUT` changes provider/network to `0/0`; `RESUMED_RESULT` and
`ALREADY_SUCCEEDED` additionally change candidate runtime to `0`. `BUSY` has all three call counts
zero and all five `*_or_null` fields equal `None`. `loader_replay_count` counts mandatory pure
production-loader verification and is not an economic execution count.

- [ ] **Step 4: Add crash-after-prepared and crash-after-publish tests**

Use the concrete injector and verify:

- after input commit: recovery makes `0/0` provider/network calls and one candidate runtime call;
- after result commit: recovery makes zero provider/network/candidate-runtime calls while still performing mandatory loader replay;
- after artifact publish: original bytes and inode remain, `created=false`, then `SUCCEEDED`;
- conflicting existing bytes, symlink, hardlink or replaced directory fails closed;
- `FAILED` preserves the highest durable stage.

- [ ] **Step 5: Implement `fail()`/`succeed()` and recovery outcomes**

`fail()` appends a fixed reason code only if the worker owns the active claim. `succeed()` requires `RESULT_PREPARED`, matching output root/result/snapshot hashes and verified final artifact bytes. Recovery outcomes are derived from the claim's durable stage, never a caller flag.

```python
def fail(
    self,
    claim: SystemPaperClaim,
    *,
    reason_code: str,
    failed_at: object,
) -> None: ...

def succeed(
    self,
    claim: SystemPaperClaim,
    *,
    artifact_path: Path,
    completed_at: object,
) -> None: ...
```

- [ ] **Step 6: Run focused and adjacent recovery tests**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_system_paper_scheduler \
  tests.test_system_paper_runtime \
  tests.test_paper_scheduler \
  tests.test_context_cycle_orchestrator -v
```

Expected: PASS; old scheduler/orchestrator behavior unchanged.

- [ ] **Step 7: Commit the exactly-once runner**

```bash
git add src/crypto_quant/system_paper_scheduler.py tests/test_system_paper_scheduler.py \
  src/crypto_quant/market_data_cli.py tests/test_market_data_cli.py
git commit -m "feat: orchestrate crash-safe system paper slots"
```

### Task 5: Freeze the full fault-injection matrix

**Files:**
- Modify: `src/crypto_quant/system_paper_scheduler.py`
- Create: `tests/test_system_paper_fault_injection.py`
- Modify: `tests/test_system_paper_scheduler.py`

**Interfaces:**
- Consumes: `run_due_system_paper_slot`, all v0.56 `FillScenario` factories.
- Produces: complete wiring and recovery evidence for the exact frozen failpoint set.

- [ ] **Step 1: Write the failing all-stage failpoint wiring tests**

```python
def test_every_frozen_failpoint_is_reached_at_its_exact_stage(self):
    for point in FROZEN_FAILPOINTS:
        with self.subTest(point=point):
            harness = FaultScenarioHarness(point=point, mode="CRASH")
            with self.assertRaises(SystemPaperInjectedFault):
                harness.run_first_invocation()
            harness.assert_durable_stage_matches_contract()
```

The accepted set must equal the spec exactly, including before-commit, after-commit, artifact
write/fsync/publish and before-success points. The durable-stage expectation is explicit per point.

- [ ] **Step 2: Run the wiring tests and verify the red light**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_system_paper_fault_injection.SystemPaperFaultWiringTests -v
```

Expected: FAIL because Task 4 only wired the recovery points used by its focused tests, not the full
before/after commit and ENOSPC matrix.

- [ ] **Step 3: Wire every frozen point at the exact boundary**

Keep the Task 4 adapter inert by default. Add `maybe_raise()` immediately before each transaction
commit and after each durable commit, around provider/candidate runtime, and inside publication. Do not
expose string failpoint parameters directly on the runner and do not add CLI/environment-variable support.

```python
injector.maybe_raise("BEFORE_INPUT_PREPARED_COMMIT")
self.connection.commit()
injector.maybe_raise("AFTER_INPUT_PREPARED_COMMIT")
```

- [ ] **Step 4: Add the table-driven recovery matrix**

For every frozen point, run a first invocation, inspect the durable stage/artifact count, advance beyond lease when required, then recover. Assert exact expected provider/network/runtime counts, one prepared result at most, one final artifact at most, balanced ledger, full loader replay and zero safety counters.

Add explicit SQLite ENOSPC tests by injecting before claim/input/result/success commit; assert transaction rollback leaves the immediately prior durable stage and never appends a false `FAILED` or `SUCCEEDED`.

- [ ] **Step 5: Add provider and order fault matrices**

Provider cases: duplicate/reordered families, count mismatch, stale capture, changed bundle hash, float, private/account family. Order cases: reject, cancel-before-fill, fill-before-cancel, partial-then-full, timeout, disconnect-then-full, permanent UNKNOWN and overfill. Assert each result is exactly one of:

```python
self.assertIn(outcome, {"RECOVERED", "LOCKED", "FAILED_CLOSED"})
self.assertEqual(result["safety_counts"], {
    "credential_reads": 0,
    "account_requests": 0,
    "real_broker_calls": 0,
    "real_order_writes": 0,
})
```

Permanent UNKNOWN must publish a balanced, loader-valid `LOCKED` result and block the next slot from increasing risk. Impossible overfill must form no prepared result and no artifact.

- [ ] **Step 6: Run all scheduler/fault/adjacent suites**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_system_paper_scheduler \
  tests.test_system_paper_fault_injection \
  tests.test_system_paper_runtime \
  tests.test_system_paper_broker \
  tests.test_paper_scheduler \
  tests.test_context_cycle_orchestrator -v
```

Expected: PASS without network patching or runtime installation.

- [ ] **Step 7: Commit the frozen fault matrix**

```bash
git add src/crypto_quant/system_paper_scheduler.py \
  tests/test_system_paper_scheduler.py tests/test_system_paper_fault_injection.py
git commit -m "test: freeze system paper scheduler faults"
```

### Task 6: Bind build identity, documentation, and v0.57 version

**Files:**
- Modify: `src/crypto_quant/build.py`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `tests/test_estimators.py`
- Modify: `README.md`
- Create: `docs/adr/0057-system-paper-wal-scheduler.md`
- Create: `docs/implementation-status-v0.57.0.md`

**Interfaces:**
- Consumes: completed Tasks 1–5 and exact verification outputs.
- Produces: package `0.57.0`, evaluator manifest `1.51.0`, committed build inputs, truthful release docs.

- [ ] **Step 1: Write failing build/version expectations**

Update estimator/version tests to expect package `0.57.0`, manifest `1.51.0`, and inclusion of:

```python
"src/crypto_quant/system_paper_scheduler.py"
"tests/test_system_paper_scheduler.py"
"tests/test_system_paper_fault_injection.py"
"docs/superpowers/specs/2026-08-02-system-paper-wal-scheduler-design.md"
"docs/superpowers/plans/2026-08-02-system-paper-wal-scheduler.md"
```

- [ ] **Step 2: Run build/version tests and preserve the red light**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_estimators -v
```

Expected: FAIL on old `0.56.0` / `1.50.0` identities and missing build inputs.

- [ ] **Step 3: Update package/build versions and refresh deterministic manifest**

Set `pyproject.toml`, `setup.py`, and `src/crypto_quant/__init__.py` to `0.57.0`; set refresh-script manifest version to `1.51.0`; add required paths to deterministic build selection if not already globbed. Run:

```bash
PYTHONPATH=src:tests python3 scripts/refresh_evaluator_build_manifest.py
PYTHONPATH=src:tests python3 scripts/validate_evaluator_build_manifest.py
```

Expected: both exit zero and the manifest package/version fields equal `0.57.0` / `1.51.0`.

- [ ] **Step 4: Write ADR, implementation status, and README update**

ADR fixes the independent WAL design, exact stages, full parent-chain loader, no-backfill policy and fault matrix. Status records actual test counts/hashes only after verification. README must say: scheduler library complete; Paper still not installed/started; v0.58 deployment trust chain remains; no profitability/AI/Canary claim.

- [ ] **Step 5: Run focused and build tests**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_system_paper_scheduler \
  tests.test_system_paper_fault_injection \
  tests.test_system_paper_runtime \
  tests.test_system_paper_broker \
  tests.test_estimators -v
PYTHONPYCACHEPREFIX=/private/tmp/crypto-quant-v057-pycache \
  python3 -m compileall -q src tests scripts
git diff --check
```

Expected: PASS.

- [ ] **Step 6: Commit release metadata**

```bash
git add README.md docs/adr/0057-system-paper-wal-scheduler.md \
  docs/implementation-status-v0.57.0.md pyproject.toml setup.py \
  src/crypto_quant/__init__.py src/crypto_quant/build.py \
  scripts/refresh_evaluator_build_manifest.py \
  config/evaluator-build-manifest-v1.json tests/test_estimators.py
git commit -m "release: document system paper scheduler v0.57.0"
```

### Task 7: Independent review, full verification, and GitHub release

**Files:**
- Modify only files required by verified review findings.
- Reference: all v0.57 files and release workflow.

**Interfaces:**
- Consumes: exact branch diff `v0.56.0..HEAD`.
- Produces: reviewed Draft PR, green PR/main CI, annotated `v0.57.0` exactly at merged main.

- [ ] **Step 1: Invoke `superpowers:requesting-code-review` on the exact diff**

Reviewer must inspect event transitions, transaction boundaries, durable-stage recovery, provider/network budget, parent-chain replay, publication races, fault coverage, Python 3.9 compatibility and safety counters. Critical/Important findings block release; apply valid findings through `superpowers:receiving-code-review` and rerun focused/adjacent tests after every fix.

- [ ] **Step 2: Run final focused and adjacent verification**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_system_paper_scheduler \
  tests.test_system_paper_fault_injection \
  tests.test_system_paper_runtime \
  tests.test_system_paper_broker \
  tests.test_paper_scheduler \
  tests.test_context_cycle_orchestrator \
  tests.test_estimators -v
```

- [ ] **Step 3: Run full release verification using `superpowers:verification-before-completion`**

```bash
PYTHONPATH=src:tests python3 -m unittest discover -s tests -q
PYTHONPYCACHEPREFIX=/private/tmp/crypto-quant-v057-pycache \
  python3 -m compileall -q src tests scripts
PYTHONPATH=src:tests python3 scripts/validate_evaluator_build_manifest.py
git diff --check
make validate
```

Expected: all technical commands exit zero. Release policy may continue to report its deliberate production gate closed because bindings/start evidence are absent and `production_activation.enabled=false`.

- [ ] **Step 4: Re-read exact Git/GitHub authority before writes**

Confirm target private repository `cjl308868584-lang/crypto-quant-core`, `origin`, remote `main`, branch ancestry, no existing `v0.57.0`, and connected account `ADMIN/push` permission. Abort on any mismatch.

- [ ] **Step 5: Use `superpowers:finishing-a-development-branch` and `github:yeet`**

Push `codex/v0.57-system-paper-scheduler`, create a Draft PR titled `release: crash-safe System Paper scheduler v0.57.0`, include safety/verification evidence, wait for Python 3.9/3.12 PR CI, then mark ready and merge only the reviewed head SHA.

- [ ] **Step 6: Wait for main CI and create the annotated tag**

After merged-main Python 3.9/3.12 CI succeeds, fetch remote main, create annotated `v0.57.0` at the exact merge commit, push it, and verify:

```bash
git ls-remote origin refs/heads/main refs/tags/v0.57.0 'refs/tags/v0.57.0^{}'
```

Expected: peeled tag SHA equals remote main SHA. Do not install/start System Paper.

- [ ] **Step 7: Update the existing daily heartbeat in place**

Keep the same automation id/schedule/thread. Replace authority with exact `main@v0.57.0` SHA and make v0.58 deployment/install/observer/start-receipt trust chain the next engineering phase. Preserve all no-runner/no-install/no-credentials/no-real-trading/fail-closed constraints.
