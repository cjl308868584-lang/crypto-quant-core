# ADR-0057：System Paper 独立 WAL 调度器

日期：2026-08-02

状态：已接受

## 背景

v0.56 已提供无凭据、确定性的单槽 System Paper runtime，但没有长期调度、
崩溃恢复或故障注入边界。调度层必须保持与 runtime 独立，不能引入 CLI、
service、安装步骤、启动 receipt 或网络 transport；它只协调已冻结计划、调用方
提供的公开输入捕获边界和现有纯离线 runtime。

## 决策

1. 使用单独的 owner-safe SQLite state file，固定 `WAL` 和 `FULL` sync。事件、
   prepared inputs 与 prepared results 只追加，禁止 UPDATE/DELETE；所有 durable
   状态改变在 `BEGIN IMMEDIATE` 事务中提交。
2. 固定 UTC 4h cadence、5 分钟 close delay 与 15 分钟 lease。状态阶段只能为
   `CLAIMED → INPUT_PREPARED → RESULT_PREPARED → SUCCEEDED`，或在受限原因下
   进入 `FAILED`；缺失、过期和成功是不可变终态。恢复仅从已提交 durable stage
   推导，不能由调用者旗标跳过阶段。
3. 首次启动只从当前自然槽开始，禁止 historical backfill；之后发现的未记录自然槽
   永久标为 `MISSED`。前序 `MISSED`、`EXPIRED` 或非相邻槽会阻断后续 parent
   continuity，不能补槽、重置或把它转为合格证据。
4. prepared result 在发布前严格验证 canonical bytes、Schema、hash、账本、输入与
   output root，并由 loader 从 exact genesis 开始重放完整、有序且相邻的 parent
   artifact chain。仅重算外层 hash 或只提供直接 parent 均不充分。
5. 结果发布固定为 immutable artifact，成功提交前再次读取并验证精确 bytes；同一
   slot 只允许一份经济结果。并发 claim、live lease 和已成功 slot 都不得重复调用
   provider、runtime 或发布器。
6. 故障矩阵冻结在提交前/后 claim、input、result、publish 与 success 的 CRASH/
   ENOSPC 边界，以及 provider、order 和 artifact 写入失败。故障后只能恢复到最后
   已提交阶段，且不得伪造 `FAILED` 或 `SUCCEEDED`。
7. final review 强化不改变上述范围：每次 invocation 仍只采样一次时钟，但必须先于
   当前自然槽恢复唯一、最旧的非终态 durable INPUT/RESULT；恢复完成前不记录后续 gap，
   多份相互矛盾的 recoverable work 失败关闭。实际 `captured_at` 可晚于入口采样，但必须
   位于 `[入口采样, claim lease expiry)`，所有 schedule event time 仍绑定入口采样。
8. `SUCCEEDED` event 必须逐字段绑定 immutable prepared result 的 result SHA、runtime
   snapshot hash 与 output-root hash；六个 UPDATE/DELETE trigger 的名称、table、timing、
   action 与 RAISE body 在每次打开和完整重放时精确验证，不能被同名 no-op 替代。
9. output root 的 owner-safe fd 与 `(dev, ino)` 贯穿整个 runner invocation，并在 provider、
   runtime、publish 与 success 边界复核。既有 `system-paper-slots` 必须为当前 owner 且
   exact `0700`；publisher 在创建任何 temp/final 前再次校验 root identity 与该目录。
   所有 parent continuity 对外冻结为 `SYSTEM_PAPER_PARENT_CONTINUITY_BROKEN`，owned claim
   的 durable FAILED 也使用同一码。artifact write/fsync 的 ENOSPC 保留 durable RESULT，
   不伪造 FAILED/SUCCEEDED，并由下一 invocation 以零 provider/network/candidate 恢复。

## 后果

v0.57 完成的是 credential-free、deterministic、offline scheduler library；它不安装
或启动 Paper，不创建 CLI/service/network transport，也不开始 90 天计时。v0.58 的
deployment trust chain（独立 deployment/install/observer/start receipt）仍是后续门。

本决策不证明盈利、AI edge、Paper completion、Canary 或任何 real-trading 资格。
`production_activation.enabled=false` 继续生效。
