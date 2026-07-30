# 实施追踪 v0.47.0

日期：2026-07-30

状态：Cohort 全 Episode 经济结果与只追加索引已实现

## 本版本完成

- 以独立提交 `e687558` 冻结 v0.47 详细设计；
- exact 绑定 v0.43 cohort plan、v0.37 economic plan 与冻结 policy hash；
- 使用 v0.45 production loader 无选择扫描全部 completed Episode receipts；
- 使用 v0.46 production loader 读取全部且仅全部 required shared day archives；
- 自动派生 entry/exit next-strict UTC minute 和 exact selected raw rows；
- 按冻结 10bps 滑点、15bps 双边 taker fee、1000 USDT 与 Decimal tick/step
  计算 gross/net PnL、net return 和 positive label；
- 每 Episode 唯一 canonical result，0700/0600、单 hardlink、exact retry；
- 每 Episode 追加一个不可变累计 index 快照，验证 previous hash、完整前缀与
  receipt/result file SHA-256；
- 支持 result 已发布而 index 未发布的安全崩溃恢复；
- 新增两个 Schema/package mirrors、离线 CLI、ADR 与回归测试。

## 固定边界

- CLI 无 Episode id/path、ordinal、日期、时间、symbol、URL、价格、费用、数量、
  PnL、label、result id 或 filename selector；
- 无 completed receipt：0 result/index write；
- v0.47 不包含 HTTP transport，market request 为 0；
- Broker/order/strategy-state-write/Runner：`0/0/0/0`；
- result/index status：`DESCRIPTIVE_NO_EARLY_SUCCESS`；
- profitability：`INELIGIBLE_INTERIM_COHORT`；
- AI comparison：无新增资格。

## 验证

- v0.47 聚焦 tests：10/10；
- v0.40 pilot 与 v0.46 shared archive 回归：30/30；
- 全量 tests：641/641；
- Schema mirror：逐字节一致；
- Golden Vector：41；
- Evaluator build input：203；
- Build input tree hash：
  `44a1cc167eee118f85219efb02dc4d83ca49af698907443b9d58758b56f0b90a`；
- Evaluator build hash：
  `e554a5aa7938d9a168a5d9717e13d0c542a7e9dbb80cee8501b436452ac6fe8e`；
- `make validate`：完成；生产门继续保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 真实运行状态

北京时间 2026-07-30 使用 v0.35 冻结绝对路径执行真实 v0.47 CLI，返回
`COHORT_ECONOMIC_RESULT_NO_COMPLETED_EPISODES`。Episode receipt、result、
index、market request、Broker、order、state write、Runner 全部为 0；未创建空
cohort result/index 目录，既有 v0.42 pilot result 保持不变。

## 下一步

继续让 LaunchAgent 自然收集，不触发 Runner、不补槽。每个 completed Episode
先由 v0.45 receipt 和 v0.46 shared archive 管线完成证据，再运行 v0.47 追加结果。
固定 tail end 前不得执行 v0.48 盈利门或形成提前 PASS。
