# System Paper WAL 调度与故障注入设计

日期：2026-08-02

状态：冻结

目标版本：`v0.57.0`

权威基线：`v0.56.0` / `2bdd3aee51c8c48941d71ded90904a885353f790`

## 1. 目标与边界

本版本为 v0.56 的确定性单槽 runtime 增加崩溃安全、只追加、不可回填的 4 小时
调度层。它要证明同一个自然槽在进程崩溃、重复 worker、写入失败或重启恢复后仍只产生
一份经济结果，并能从已经持久化的精确输入或精确结果继续，而不是再次获取市场输入或
重新计算已准备结果。

本版本只实现可测试的 scheduler library 和故障注入合约。它不实现 CLI、LaunchAgent、
安装器、observer、start receipt 或 90 天 evaluator，不访问公开市场网络，不创建运行
目录，不启动 System Paper，也不开始 90 天计时。这些属于 v0.58 及后续版本。

全局安全边界保持不变：

- `production_activation.enabled=false`；
- 凭据、账户、真实 Broker、真实订单调用计数固定为零；
- 不读取余额，不创建或取消真实订单；
- 不修改 Challenger 的 service、SQLite、日志、bundle 或 evidence root；
- 不允许历史补槽、人工回填或用后来数据替换自然槽输入；
- 不因为 scheduler 成功而宣称策略赚钱、Paper 已启动或具备 Canary 资格。

## 2. 方案裁决

### 2.1 采用：独立 System Paper WAL 状态机

新增 `system_paper_scheduler.py`，复用现有 scheduler 已验证的工程模式：SQLite WAL、
`BEGIN IMMEDIATE`、只追加事件、不可变 prepared blobs、租约回收和 fsync 后原子发布。
业务事件、slot identity、input/result 验证和 parent-chain 全部为 System Paper 独立定义。

优点是不会让旧离线 Paper 调度语义渗入 v0.56 runtime，也不需要改动成熟的旧 scheduler。
代价是保留少量结构性重复；这些重复用于隔离两条证据链，属于有意的安全边界。

### 2.2 不采用：先抽象通用 scheduler 内核

通用内核可以减少重复，但会同时改动旧 `paper_scheduler.py` 和新 System Paper，扩大
回归面，并把 v0.57 的发布资格绑定到旧业务迁移。当前没有第二个完全相同的 runtime
合约，因此此抽象尚无足够证据支持。

### 2.3 不采用：包装旧 `PaperScheduleState`

旧状态机保存的是 offline-paper run，包含不同的事件名、artifact hash、网络请求计数和
业务校验。包装它会让新 scheduler 难以证明 exact v0.56 replay、parent result continuity
和单次公共输入预算，因此拒绝此方案。

## 3. 固定时序策略

`SystemPaperSchedulePolicy.create()` 是唯一构造入口，固定：

| 字段 | 固定值 |
|---|---|
| symbol | `ETHUSDT` |
| timezone | `UTC` |
| cadence | 14,400 秒 |
| anchor | UTC `00:00:00` |
| close delay | 300 秒 |
| lease | 900 秒 |
| active window | `[scheduled_for + 5m, scheduled_for + 4h + 5m)` |
| public input attempts | 每次 invocation 最多 1 次 provider 调用；prepared 后永久为 0 |
| historical backfill | `false` |

slot id 逐字节复用 v0.56 runtime 身份：
`stable_id("system_paper_slot", {"plan_hash": plan_hash, "scheduled_for": scheduled_for})`。
schedule policy hash 另行进入每个 event payload。调用者不能传入 slot id、cadence、窗口或
backfill 开关。

首次打开空状态库只认识当前自然槽，不为此前时间生成 MISSED 记录。状态库已有事件后，
首次看到更晚自然槽时，所有完全跨过且从未出现的中间槽被记录为 `MISSED`；已有但未准备
输入的旧槽被记录为 `EXPIRED`。`MISSED` 和 `EXPIRED` 永久不可领取。

一旦某槽的 `INPUT_PREPARED` 已提交，说明其输入在自然窗口内完成捕获；此槽即使后来超过
active window，也允许从 exact input/result bytes 完成恢复。恢复资格不能被用来准备新输入。

## 4. WAL 数据模型

状态库固定使用 SQLite `journal_mode=WAL`、`synchronous=FULL`、`foreign_keys=ON` 和
`busy_timeout=0`。数据库父目录和文件不得是符号链接；已有状态必须是普通单链接文件。

### 4.1 `schedule_events`

只追加全局事件链，字段固定为：

- 连续 `sequence`；
- 稳定 `event_id`、`event_type`、`slot_id`、`event_time`；
- canonical `payload_json` 与 `payload_hash`；
- `previous_event_hash` 与 `event_hash`。

首事件的 previous hash 为 64 个零。事件时间不得倒退。数据库触发器永久禁止 UPDATE 和
DELETE。每次打开状态库及每个写事务前后都完整重放事件链。

事件类型固定为：

- `CLAIMED`
- `INPUT_PREPARED`
- `RESULT_PREPARED`
- `SUCCEEDED`
- `FAILED`
- `MISSED`
- `EXPIRED`

### 4.2 `prepared_inputs`

每槽最多一行，保存 exact canonical input envelope bytes、SHA-256、plan hash、market bundle
hash、previous snapshot hash、fill scenario hash、output root hash 和来源事件 id。触发器禁止
UPDATE/DELETE。

input envelope 仅包含：冻结 plan、scheduled_for、公开 market bundle、由可信父结果派生的
previous runtime snapshot、冻结 fill scenario。它必须能直接构造
`SystemPaperSlotInputs`，不能包含调用者提供的 PnL、费用、结果 id、filename 或风险结论。

### 4.3 `prepared_results`

每槽最多一行，保存 exact canonical slot result bytes、SHA-256、slot hash、runtime snapshot
hash、parent slot hash、output root hash 和来源事件 id。触发器禁止 UPDATE/DELETE。

插入前必须调用 v0.56 production loader 等价的完整验证路径：Schema、canonical bytes、
self hash、账本平衡、订单 result hash、完整 replay 和 parent artifact chain。scheduler 不得
以只重算外层 hash 代替 production loader 验证。

### 4.4 事务边界

`claim`、`prepare_input`、`prepare_result`、`succeed`、`fail` 和 gap 记录分别在单个
`BEGIN IMMEDIATE` 事务中完成。prepared row 与对应 event 必须在同一事务提交，因此不可能
出现有事件无 blob 或有 blob 无事件。任何 SQLite/OSError 让事务回滚至上一个完整阶段。

## 5. 状态机与投影

每个槽由事件重放得到下列状态：

```text
ABSENT
  └─ CLAIMED ────────────────┐
       ├─ FAILED ── reclaim  │
       ├─ lease expires ─────┤
       └─ INPUT_PREPARED ────┤
              └─ RESULT_PREPARED
                     └─ SUCCEEDED

ABSENT/CLAIMED without prepared input after window
  └─ MISSED or EXPIRED (terminal)
```

投影规则：

- live lease 返回 `BUSY`，不写新事件；
- stale lease 可由新 worker 领取，attempt 递增；
- 投影同时保存 attempt status 与最高 durable stage；`FAILED` 只关闭当前 attempt，不抹去
  已提交的 `INPUT_PREPARED` 或 `RESULT_PREPARED`；
- 新 claim 根据 durable stage 固定返回 `CLAIMED`、`RESUME_INPUT` 或 `RESUME_RESULT`，恢复代码
  只能从对应的 exact blob 继续；
- `FAILED` 不是终态，只允许同一个自然窗口内重试，或在已经有 prepared input/result 时恢复；
- `MISSED`、`EXPIRED`、`SUCCEEDED` 是不可逆终态；
- `SUCCEEDED` 再调用返回 `ALREADY_SUCCEEDED`，provider 和 runtime 调用均为零；
- 任何非法跃迁、event/blob 集合不一致、hash 链断裂或租约所有权丢失都失败关闭。

`RESULT_PREPARED` 只能由同槽 `INPUT_PREPARED` 派生；`SUCCEEDED` 只能引用完全相同的 result
hash、snapshot hash 和 output root hash。

## 6. `run_due_system_paper_slot` 数据流

公开接口固定为：

```python
run_due_system_paper_slot(
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
) -> Mapping[str, Any]
```

`clock` 只在函数入口采样一次；同一次 invocation 的 claim、prepare 和 terminal event 均使用
该固定时间，禁止在业务步骤中再次读取系统时钟。v0.58 CLI 将提供真实时钟和固定路径；
v0.57 测试只使用注入值。

执行顺序固定为：

1. 验证 plan，派生 policy、当前 slot 和 owner-bound output root hash；
2. 记录既有时间线上的自然 gap；
3. 以 `BEGIN IMMEDIATE` 领取或恢复 slot；
4. 若没有 prepared input，调用 provider 恰好一次，验证 request 与返回 bundle 后，将完整
   input envelope exact bytes 与 `INPUT_PREPARED` 原子提交；
5. 若没有 prepared result，从数据库读取 exact input bytes，调用 v0.56 runtime 恰好一次形成
   candidate result，
   将 canonical result bytes 与 `RESULT_PREPARED` 原子提交；
6. 从数据库读取 exact result bytes，通过 production loader 与完整父链重放；
7. 以安全 no-overwrite publisher 将 exact bytes 发布到
   `system-paper-slots/<slot_id>.json`；文件已存在时仅在 bytes 完全相同才采用；
8. 发布成功后写 `SUCCEEDED`；若在发布后崩溃，下次读取同一 prepared result 并采用已存在的
   exact 文件，再写 `SUCCEEDED`；
9. 返回只含 outcome、slot identity、provider/runtime 调用计数、result 路径与 hash、状态摘要、
   风险状态和固定安全计数的映射。

provider request 由 scheduler 派生，只包含 plan hash、slot id、scheduled_for、capture deadline
和冻结 source allowlist。provider 不能获得 state connection、output path 或凭据。scheduler
自身不实现 HTTP；测试 provider 只返回已捕获 bundle。

`SystemPaperInputCapture` 固定包含 public market bundle、capture attempt id、实际 captured_at、
按顺序的 request families 和 `network_request_count`。request families 必须逐字节等于 plan
的四个公开 GET family，每个 family 恰好出现一次，count 必须等于 4；账户/private/Broker
family 一律拒绝。这里的“单次预算”指一个未准备槽在一次 scheduler invocation 内最多调用
provider 一次，该 capture attempt 内固定含四个 allowlisted GET。若 provider 已返回但 input
事务尚未提交就崩溃，后续 invocation 只可在原 active window 内重新进行一次 capture；禁止
同一 invocation 内循环重试。一旦 `INPUT_PREPARED` 提交，后续所有恢复的 provider invocation
和 network request count 永久为零。

## 7. 父链与经济 exactly-once

首个成功槽的 parent 必须逐字节等于 v0.56 冻结 genesis。后续槽必须使用最近且时间上恰好
相邻的 `SUCCEEDED` result；scheduler 从状态投影派生从 genesis 到前一槽的全部有序 artifact
paths，调用 v0.56 production loader 完整重放整条 parent chain，再从链尾派生 previous
snapshot。只验证最近一份文件或只比对 snapshot hash 均不合格。调用者不能覆盖 parent、
artifact list 或 previous snapshot。

若前一自然槽为 `MISSED`、`EXPIRED`、永久失败或缺少可信 artifact，后续槽不得运行 runtime，
并返回 `SYSTEM_PAPER_PARENT_CONTINUITY_BROKEN`。本版本不允许为了继续运行而从最新可用结果
跨越缺口。

经济 exactly-once 的权威是 prepared result：

- provider 最多执行一次，之后恢复输入调用计数为零；
- candidate runtime 最多对某一 prepared input 形成一份 prepared result；
- result 准备后恢复不得再次运行 candidate runtime；production loader 为验证 exact bytes 而
  执行的纯重放仍是强制步骤，它不产生新 artifact、ledger 写入或经济结果；
- immutable artifact 对同一路径只允许相同 bytes；
- `SUCCEEDED` 重放不得追加经济 ledger 或创建第二份结果。

UNKNOWN 未解析或 reconciliation 非 `RECONCILED` 的 v0.56 result 可以被封存，但其 snapshot
必须为 `LOCKED`，下一自然槽不得增加风险。若 runtime 或 loader 违反该约束，scheduler
拒绝准备结果。

## 8. 不可变发布

publisher 使用基于目录 fd 的 `O_NOFOLLOW` 检查，拒绝符号链接、非普通文件、硬链接和目录
替换。新文件先在目标目录写入 owner-only 临时文件，完成全部写入后 `fsync(file)`，再使用
不覆盖语义提交为最终名称，并 `fsync(directory)`。

最终文件已存在时：

- bytes 完全相同：返回 `created=false`；
- bytes 不同、类型异常或路径身份改变：失败关闭；
- 不删除、不替换、不截断既有文件。

临时文件失败可以清理；最终 artifact 永不由 scheduler 删除。v0.58 再负责固定 owner-only
根目录的创建与安装证明。

## 9. 故障注入合约

`SystemPaperFaultInjector` 是测试专用、默认无动作的显式 failpoint adapter。允许点固定为：

- `AFTER_CLAIM_COMMIT`
- `BEFORE_CLAIM_COMMIT`
- `BEFORE_INPUT_PROVIDER`
- `AFTER_INPUT_PROVIDER_BEFORE_COMMIT`
- `BEFORE_INPUT_PREPARED_COMMIT`
- `AFTER_INPUT_PREPARED_COMMIT`
- `AFTER_RUNTIME_BEFORE_RESULT_COMMIT`
- `BEFORE_RESULT_PREPARED_COMMIT`
- `AFTER_RESULT_PREPARED_COMMIT`
- `DURING_ARTIFACT_WRITE`
- `AFTER_ARTIFACT_FSYNC_BEFORE_COMMIT`
- `AFTER_ARTIFACT_PUBLISH_BEFORE_SUCCESS`
- `BEFORE_SUCCESS_COMMIT`

注入器只能抛出固定 `SystemPaperInjectedFault` 或模拟 `ENOSPC`，不能修改业务对象。production
调用若传入非默认注入器必须显式构造；v0.58 CLI 永不暴露 failpoint 参数。

固定验收矩阵：

| 故障 | 恢复期望 | 恢复期 provider / GET | 恢复期 candidate runtime | 经济结果数 |
|---|---|---:|---:|---:|
| claim 后崩溃 | lease 到期后重新领取 | 1 / 4 GET | 1 | 1 |
| provider 返回后、input commit 前崩溃 | 当前窗口内下一 invocation 重捕获 | 1 / 4 GET | 1 | 1 |
| input commit 后崩溃 | exact input 恢复 | 0 / 0 GET | 1 | 1 |
| runtime 后、result commit 前崩溃 | exact input 重算一次 | 0 / 0 GET | 1 | 1 |
| result commit 后崩溃 | exact result 恢复 | 0 / 0 GET | 0 | 1 |
| 文件写入 ENOSPC | prepared result 保留并失败关闭 | 0 / 0 GET | 0 | 1 |
| publish 后、success 前崩溃 | 采用相同文件并完成 | 0 / 0 GET | 0 | 1 |
| duplicate/out-of-order provider evidence | 输入拒绝，不形成 result | 1 / 拒绝 | 0 | 0 |
| partial/disconnect/timeout fill scenario | 由 v0.56 runtime 对账或锁定 | 0 / 0 GET | 1 | 1 |

“runtime 后、result commit 前”没有持久结果，因此恢复时允许从已持久 exact input 再运行；
每次尝试必须生成完全相同 bytes，否则准备阶段失败关闭。这个重算不构成第二个经济结果。

## 10. 错误分类

所有预期失败使用 `SystemPaperScheduleError(reason_code)`：

- 时钟、policy、slot、worker、路径或 plan 不合法；
- state/event/blob/hash/schema/canonical/replay/parent chain 不合法；
- slot 尚未到期、已终止、live lease busy 或 claim ownership 丢失；
- provider 超预算、request/bundle 不匹配或 input 非 contemporaneous；
- prepared result 与 input、parent、output root 不匹配；
- immutable publication 冲突或存储失败；
- gap 导致 parent continuity 断裂。

业务/输入/运行错误在仍可合法写状态时追加 `FAILED`，payload 只记录固定 reason code，不保存
异常字符串、路径外数据或凭据。SQLite commit 失败不能伪造 `FAILED`；调用方收到原始关闭
结果，下一次打开状态库从最后完整事务恢复。

## 11. 测试与验收

### 11.1 scheduler 聚焦测试

- WAL/FULL sync、表与事件链只追加、prepared rows 原子对应；
- exact-once publication、相同 worker 重试和 duplicate worker；
- live lease busy、stale lease recovery、claim ownership；
- 首次启动不回填、未知中间槽 MISSED、旧未准备槽 EXPIRED；
- input/result prepared 两个恢复阶段的调用计数；
- publish 后崩溃采用 exact bytes；
- terminal state 不可变；
- 首槽 exact genesis、后续相邻 parent、缺槽阻断；
- output root、plan、slot、bundle、snapshot、fill scenario 全部 hash 绑定；
- event/blob/artifact 篡改、symlink/hardlink/替换攻击失败关闭。

### 11.2 故障注入测试

- 本设计第 9 节所有 failpoint；
- `ENOSPC` 发生在 SQLite/input/result/artifact 边界；
- provider duplicate/out-of-order/stale evidence；
- v0.56 reject/cancel/partial/timeout/disconnect/UNKNOWN/overfill 场景；
- 每个场景安全计数为 `0/0/0/0`；
- 每个可发布场景 ledger 平衡、parent chain 可重放且最多一份经济结果；
- 失败场景最终为 `RECOVERED`、`LOCKED` 或 `FAILED_CLOSED`，绝不静默成功。

### 11.3 相邻与全量回归

聚焦测试之外必须运行：

- `tests.test_system_paper_broker`
- `tests.test_system_paper_runtime`
- `tests.test_paper_scheduler`
- `tests.test_context_cycle_orchestrator`
- 完整 unittest discovery；
- Python 3.9/3.12 CI；
- `compileall`、`git diff --check`、Schema mirror 和 evaluator build validator；
- `make validate`，其中 production activation 按设计继续关闭。

## 12. 交付物与发布门

v0.57 至少包含：

- `src/crypto_quant/system_paper_scheduler.py`；
- `tests/test_system_paper_scheduler.py`；
- `tests/test_system_paper_fault_injection.py`；
- evaluator build inputs；
- `docs/adr/0057-system-paper-wal-scheduler.md`；
- `docs/implementation-status-v0.57.0.md`；
- README 与 package/build 版本更新。

发布必须经过隔离分支、TDD 红灯、聚焦/相邻/全量/compileall/`make validate`、独立代码审查、
Draft PR、PR CI、合并 main、main CI，最后创建与 main 精确对齐的 annotated `v0.57.0`。

发布成功仍不得安装或启动 System Paper。下一版本 v0.58 才能设计并实现独立
deployment/install/observer/start receipt 信任链；安装还需另行通过自然启动前置验收。
