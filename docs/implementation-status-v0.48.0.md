# 实施追踪 v0.48.0

日期：2026-07-31

状态：固定尾部累计评估器已实现；真实 cohort 仍在收集

## 本版本完成

- 以独立提交 `543684f` 冻结 v0.48 详细设计；
- exact 绑定 v0.43 cohort plan、v0.44 evaluation plan、v0.37 economic plan
  与 v0.42 exposed negative pilot；
- 新增不发布 receipt 的只读 continuity observer；
- 尾部前不读取 archive、v0.47 result 或 index，不创建 evaluation artifact；
- 尾部后要求 540 槽、无 active Episode、receipt/result/index 一一对应；
- 使用 v0.47 builder 逐笔重建结果并验证完整 immutable index；
- 实现冻结 Decimal MBB 10,000 次、ESS、MERE power、CI、六时间块、固定名义
  drawdown、1.5x friction 与 leave-Top-5；
- 样本不足为 `INCONCLUSIVE`，可信样本的经济门失败才是 `DID_NOT_PASS`；
- pilot 永久排除于 confirmatory，仅进入 all-stream 描述；
- 新增 strict Schema/package mirror、owner-only exact artifact、离线 CLI、
  ADR 和聚焦测试。

## 固定边界

- CLI 不接受 clock、state、bundle、log、service、Episode、日期、价格、费用、
  资本、PnL、label、bootstrap、seed、阈值、排除项、result id 或 filename；
- 固定 tail end：`2026-10-29T12:00:00.000Z`；
- pre-tail 无 PnL、胜率、排序、置信区间、功效或提前 PASS；
- market/Broker/order/strategy-state-write/Runner：`0/0/0/0/0`；
- PASS 的 profitability 仍为
  `INELIGIBLE_RESEARCH_PROXY_NOT_SYSTEM_PAPER`；
- AI comparison 仍为 `INELIGIBLE_NO_PAIRED_AI_COHORT`。

## 验证

- v0.48 聚焦 tests：13/13；
- v0.44/v0.45/v0.47 与 v0.48 相邻回归：54/54；
- 全量 tests：654/654；
- Schema mirrors：逐字节一致且 Draft 2020-12 有效；
- Python compileall：完成；
- Golden Vector：41；
- Evaluator build input：207；
- Build input tree hash：
  `749ede6c2a1d357271b3f8a17aaf349e5aef9bde4f83704414b50ce9a0b4bb50`；
- Evaluator build hash：
  `cfbdd0add7870c3fe191939f59788c733b396e67c0ae2cf353ddd45aa8491004`；
- `make validate`：完成；生产门继续保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 真实运行状态

北京时间 2026-07-31 使用冻结绝对路径执行真实 v0.48 pre-tail CLI，返回
`COLLECTING_DESCRIPTIVE_NO_EARLY_SUCCESS`。观察时已验证 cohort 窗口槽位 2，
completed Episode 0、active Episode null，下一必需槽为
`2026-07-30T20:00:00.000Z`。market/Broker/order/state write/Runner 均为 0，
evaluation output root 调用前后均不存在。

首个 pilot Episode 已由 v0.36.0 loader 复核为
`FIRST_EPISODE_COMPLETED_VERIFIED`，但它位于 confirmatory 窗口外且结果为负，
只能作为 exposed pilot 保留。

## 下一步

继续让 LaunchAgent 自然收集，不触发 Runner、不补槽。每个 completed Episode
依次完成 v0.45 receipt、v0.46 shared archive 和 v0.47 result/index。固定
tail end 前不得读取累计 PnL 或形成提前 PASS；tail end 后才运行 v0.48 final。
