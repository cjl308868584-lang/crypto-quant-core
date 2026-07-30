# 实施追踪 v0.41.0

日期：2026-07-30

状态：首个 Challenger Episode 已自然完成并由冻结观察器验证

## 本版本完成

- 使用与 tag `v0.36.0` 一致的 observer 和 v0.35 四个冻结绝对路径只读验收；
- 交叉重放五条 Episode decision、五个 source bundle 和五行 stdout；
- 验证退出后的两条 observed decision 不进入 Episode receipt；
- 立即使用 v0.36 loader 复核 runtime receipt；
- 将 runtime receipt 的 66,839 个 exact canonical bytes 封存到 Git；
- 新增 committed receipt 的 Schema、自哈希、固定语义与安全边界回归；
- 不修改策略、调度、Runner、安装快照或观察器。

## 真实完成证据

- observed at：`2026-07-30T00:12:52.982Z`；
- entry / exit slot：
  `2026-07-29T00:00:00.000Z / 2026-07-29T16:00:00.000Z`；
- exit recorded at：`2026-07-29T16:02:05.720Z`；
- exit action：`EXIT_LONG_SMA20`；
- Episode / observed decision count：`5 / 7`；
- source bundle / matched stdout count：`5 / 5`；
- receipt self hash：
  `7c819d67693455c686d3f664290df6f85ed68887eefa917f564edd745e4fd8ff`；
- exact file SHA-256：
  `3c99f074df3029658d1a0569415259250c2043718f75446345999160ff293a06`；
- runtime uid/mode/link/size：`501 / 0600 / 1 / 66839`；
- observer launchctl/network/state-write/Broker/order：`1/0/0/0/0`。

Git 副本
[challenger-first-episode-receipt-v0.41.0.json](../artifacts/challenger-forward/challenger-first-episode-receipt-v0.41.0.json)
与 runtime 原件逐字节一致。

## 日档状态

v0.37/v0.38 自动派生唯一所需日档 `2026-07-29`，时间门为
`2026-07-30T00:05:00.000Z`。门后 v0.39 首次真实调用只请求官方 allowlisted
ZIP，返回 404：

- status：`ARCHIVE_ACQUISITION_PENDING`；
- network request：`1`；
- checksum request：`0`；
- verified period：`0 / 1`；
- Broker/order/Runner/state-write：`0/0/0/0`。

因此没有使用 REST、网页、第三方或人工参数回退，也没有运行 v0.40 结果 CLI。

## 验证

- committed completion receipt focused 回归：10/10；
- observer、archive acquisition、economic evaluator/CLI 相邻回归：34/34；
- 全量 tests：577/577；
- Golden Vector：41；
- Evaluator build input：180；
- Build input tree hash：
  `bf81f374970ff8af1b9020d5c42cf0f4c109f5ce9876b880e15f5e698927fdf3`；
- Evaluator build hash：
  `943091d3b9710b122ffe04f472448752689074ef8e9109c976799403321b4e36`；
- `make validate`：完成；生产门禁继续保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 仍未证明

- 尚无本 Episode 的真实经济结果；
- 单 Episode 不能证明可重复净优势；
- 没有连续 90 天 Paper、真实 fill、实际滑点或账户级 PIT fee；
- AI 臂仍无批准模型和配对前向证据；
- 系统仍无 Broker、余额读取或下单能力。

## 下一步

保持日档获取 pending，稍后只用 v0.39 重试相同自动派生日期。官方 ZIP 和 checksum
全部 verified 后才运行 v0.40 离线 CLI；真实 result 必须作为独立后续版本封存。
