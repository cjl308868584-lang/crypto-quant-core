# ADR-0019：可恢复的长期 Paper 调度与禁止历史回填

状态：Accepted

日期：2026-07-27

## 背景

v0.18 证明了单个当前决策周期可以从公开响应重放到保守模拟成交和双经济
账本，但单次命令不能证明长期连续运行。简单地定时执行 CLI 仍会留下重复
周期、多进程竞争、崩溃后未知状态、发布一半和事后回填缺口等问题。若把
错过的周期用当前或历史归档补上，会制造当时并不存在的 contemporaneous
决策证据。

## 决策

v0.19 冻结 `ETHUSDT_PUBLIC_OFFLINE_PAPER_4H_UTC_V1`：

- 每 4 小时一个 UTC 槽位；
- 4h close 后延迟 5 分钟才到期；
- 槽位有效窗口为 4 小时；
- 租约 15 分钟；
- one-shot CLI，由外部 cron/launchd/systemd 重复调用，进程内部不 sleep；
- 每个新槽位最多执行一次形成证据的 v0.18 四公开 GET cycle；
- 第一次启动只从当前槽位开始，不伪造安装前历史；
- 已知状态后的未知中间槽位永久写 `SLOT_MISSED`；
- 已 claim/fail/prepared 但窗口过期的槽位写 `SLOT_EXPIRED`；
- missed/expired 槽位禁止事后回填。

调度状态使用 SQLite WAL/FULL synchronous。`schedule_events` 是 append-only
哈希链，UPDATE/DELETE 被触发器拒绝；每次状态变化前后均重放完整事件链和
状态机。

状态转换：

```text
UNSEEN → CLAIMED → PREPARED → SUCCEEDED
                 → FAILED → CLAIMED
         CLAIMED/PREPARED --lease expiry--> CLAIMED
UNSEEN → MISSED
CLAIMED/FAILED/PREPARED → EXPIRED
```

为解决数据库与文件系统不能共同事务的问题，精确 canonical run bytes 在
`RUN_PREPARED` 同一数据库事务中写入不可变 `prepared_blobs`，随后才原子
发布文件并追加 `RUN_SUCCEEDED`。因此：

- PREPARED 后崩溃：下一租约直接重发相同 bytes，不请求网络；
- 文件发布后、SUCCEEDED 前崩溃：下一租约识别相同文件并幂等完成；
- 活跃租约期间第二 worker：返回 BUSY；
- SUCCEEDED 后重复调用：返回 ALREADY_SUCCEEDED，网络计数为 0。

每次成功生成 `PaperScheduleSnapshot`，包含完整事件、事件 root、链尾、
槽位投影、尝试/失败/缺失计数和成功 cycle 的 run/trust hash。验证器从事件
重建 summary，不能信任调用方提供的计数。Snapshot 还需要 Artifact 外
attestation。

## 结果

优点：

- 同槽位只有一套最终证据；
- 崩溃恢复不需要重新获取不同市场响应；
- 多进程争用由持久租约而非进程内锁约束；
- 漏掉的周期永久可见，不能靠回填美化连续性；
- v0.18 的公开数据、正式决策、保守成交和经济重放语义完全复用；
- 失败尝试也进入不可变证据链。

代价与限制：

- 本版本不创建操作系统调度任务，尚不能声称自动连续运行；
- SQLite 是单机状态，不是分布式共识；
- 一个真实槽位仍不足 90 天；
- 没有 server-time/NTP offset、告警、永续上下文和真实账户费用；
- AI 仍未运行；
- 运行成功只说明调度闭环，不说明策略赚钱。

## 资格结论

v0.19 固定：

- `scheduler_eligibility=SCHEDULER_OPERATIONAL_SMOKE_ONLY`
- `paper_eligibility=LONGITUDINAL_COLLECTION_IN_PROGRESS`
- `profitability_eligibility=INSUFFICIENT_DURATION_COST_AND_AI`

本 ADR 不授权 API Key、账户、Broker、订单、自动交易、Canary、Live 或
盈利声明。
