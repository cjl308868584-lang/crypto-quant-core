# v0.19 可恢复的长期 Paper 调度设计

日期：2026-07-27

状态：Frozen for implementation

## 1. 目标

把 v0.18 的单次公开输入离线 Paper cycle 变成可由 cron/launchd/systemd
反复调用、崩溃后可恢复、不会重复采集同一决策周期的长期运行器，为系统级
至少 90 个自然日 Paper 建立真实前向样本。

v0.19 只证明调度、恢复和证据连续性。它不等待 90 天，不把短期运行升级为
Paper PASS，也不接账户、密钥、Broker 或订单。

## 2. 冻结边界

- 标的：仅 ETHUSDT Spot；
- 业务 cycle：复用 v0.18 `OfflinePaperPlan`、决策核、成交核和双经济账本；
- 网络：每个成功槽位仍只允许 v0.18 的四个固定 public GET；
- 运行形态：one-shot CLI，不在进程内 `sleep`，由外部可靠调度器频繁调用；
- 状态：本地 SQLite WAL，append-only 事件与 prepared blob；
- 输出：每个槽位一个不可变 Paper run，加一个可重放调度 snapshot；
- 盈利/AI/Paper 资格保持失败关闭。

Binance 官方文档说明 public market data 可使用
`https://data-api.binance.vision`，公开 `NONE` 端点不需要签名；429 时调用方
必须退避。v0.19 不自动重试网络请求，失败只写状态并等下一次外部调用。

## 3. 槽位定义

固定政策 `ETHUSDT_PUBLIC_OFFLINE_PAPER_4H_UTC_V1`：

- cadence：4 小时；
- UTC anchor：00:00；
- close delay：5 分钟；
- lease：15 分钟；
- 一个槽位由对应 4h Kline close 时刻标识。

对调用时刻 `now`：

```text
slot_close = floor_4h(now - 5 minutes)
due_at     = slot_close + 5 minutes
expires_at = due_at + 4 hours
slot_id    = ETHUSDT_YYYYMMDDTHHMMSSZ
```

只有 `due_at <= now < expires_at` 的当前槽位可以发起网络采集。第一次启动从
当前槽位开始，不反推并伪造安装前的历史缺口。

已有状态后，最后已知槽位与当前槽位之间：

- 完全没有事件的槽位写 `SLOT_MISSED` /
  `MISSED_NO_CONTEMPORANEOUS_CAPTURE`；
- 有 CLAIM/FAIL/PREPARE 但未成功且窗口已过的槽位写 `SLOT_EXPIRED`；
- 任何 missed/expired 槽位都禁止事后回填。

## 4. Append-only 状态

SQLite 开启 WAL、foreign keys、full synchronous。两张表：

### 4.1 `schedule_events`

- 自增 sequence；
- event_id 唯一；
- event_type；
- slot_id；
- event_time；
- canonical payload JSON/hash；
- previous_event_hash；
- event_hash。

UPDATE/DELETE 触发器永久拒绝修改。

事件：

- `SLOT_CLAIMED`
- `RUN_PREPARED`
- `RUN_SUCCEEDED`
- `RUN_FAILED`
- `SLOT_MISSED`
- `SLOT_EXPIRED`

每次打开状态库都从 genesis 重算完整哈希链和状态转换。数据库异常、事件
复用、链断裂或不合法转换全部失败关闭。

### 4.2 `prepared_blobs`

在 `RUN_PREPARED` 同一事务中保存精确 run JSON bytes、SHA-256、run hash、
external attestation hash 和目标文件名。表同样禁止 UPDATE/DELETE。

prepared blob 解决文件系统与数据库不能共同事务的问题：

1. 网络与决策完成；
2. 精确 Artifact bytes 先写数据库并提交；
3. 原子、不可替换地发布文件；
4. 追加 `RUN_SUCCEEDED`。

若步骤 2 后崩溃，下一租约直接重发同一 bytes，不重新请求网络；若步骤 3
后崩溃，发布器识别完全相同 bytes 并幂等完成。

## 5. 租约与并发

claim 使用 `BEGIN IMMEDIATE`：

- SUCCEEDED：返回 idempotent，不请求网络；
- 未过期 CLAIM：返回 BUSY；
- 新槽位、FAILED 或过期 CLAIM：追加新 CLAIM，attempt +1；
- PREPARED：追加新 CLAIM 后直接恢复 prepared bytes。

worker_id 只是受限 ASCII 运行者标识，不包含主机秘密。租约不依赖进程内
锁，因此重启和多进程竞争行为可重放。

## 6. Artifact 约束

每槽位 run_id：

`paper-slot-<slot_id-lowercase>`

必须满足：

- run decision_time 位于 `[due_at, expires_at)`；
- 四个 receipt request start/receive 保留；
- v0.18 trusted replay reasons 为空；
- artifact name、run hash、bytes SHA、attestation 与 PREPARED 完全一致；
- 发布位置固定为 `<output-root>/paper/`；
- 不允许 CLI 提供任意 URL、header、账户或订单参数。

## 7. 调度 snapshot

`PaperScheduleSnapshot` 保存：

- schedule policy/hash；
- 全部 append-only 事件；
- 事件 root/hash；
- 每槽位最终投影与 attempt 数；
- success/missed/expired/transient failure 计数；
- 首末槽位、观测自然日、预期/成功槽位；
- 每个成功 run 的 artifact name、SHA、run hash、external attestation；
- 状态库完整性结果；
- self-hash 与 Artifact 外 attestation。

验证器从事件重建槽位投影，不信任调用方给出的 summary。

v0.19 固定：

- `scheduler_eligibility=SCHEDULER_OPERATIONAL_SMOKE_ONLY`
- `paper_eligibility=LONGITUDINAL_COLLECTION_IN_PROGRESS`
- `profitability_eligibility=INSUFFICIENT_DURATION_COST_AND_AI`

即使某次 PnL 为正，也不能升级这些结论。

## 8. 真实 smoke

用临时状态库运行一次当前真实槽位：

- 第一次调用产生 exactly one public Paper cycle；
- 第二次同槽位调用不发网络并返回 ALREADY_SUCCEEDED；
- snapshot 从事件重放无理由；
- 删除临时状态库前保存 compact schedule evidence；
- 每槽位完整 run Artifact 可提交；
- 不声称形成 90 天 Paper。

## 9. 非目标

- 不创建操作系统 cron/launchd 任务；
- 不在 Codex 会话内等待 90 天；
- 不使用历史归档补 missed slot；
- 不训练或伪造 AI；
- 不接 FeeSchedule、账户或真实成交；
- 不实现 WebSocket 常驻服务；
- 不开放 Live/Canary。

## 10. 后续

v0.20 应在调度基础上增加 server-time/NTP offset、进程健康与运行告警；之后
才补永续上下文、批准 FeeSchedule 和候选 AI Shadow。
