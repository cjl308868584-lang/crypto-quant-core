# 实施追踪 v0.42.0

日期：2026-07-30

状态：首个 Challenger Episode 真实经济代理结果已封存

## 本版本完成

- 在 v0.39 时间门后只获取 completion receipt 自动派生的唯一官方 DAILY 日档；
- 第一次 ZIP 404 保持 pending，第二次只重试同一 allowlisted 来源；
- 验证官方 checksum、完整 1,440 行 CSV、两条执行分钟原始行和全部来源哈希；
- 使用 v0.40 CLI 从七个可信绝对路径自动派生唯一结果；
- CLI 不接受日期、URL、价格、费用、收益、标签、result id 或 filename 覆盖；
- 结果 exact publish 后立即由 loader 重放；
- 将 runtime result 的 5,360 个 exact canonical bytes 封存到 Git；
- ZIP/checksum/archive receipt 继续只保存在仓库外 owner-only 目录；
- 没有 Runner、Broker、订单或 strategy state 写入。

## 真实结果

- Episode exit：`EXIT_LONG_SMA20 @ 2026-07-29T16:00:00.000Z`；
- entry execution minute：`2026-07-29T00:03:00.000Z`；
- exit execution minute：`2026-07-29T16:03:00.000Z`；
- entry source high / fill：`1925.76 / 1927.69`；
- exit source low / fill：`1890.08 / 1888.18`；
- filled quantity：`0.5187 ETH`；
- gross PnL：`-20.493837 USDT`；
- total fees：`2.9689376535 USDT`；
- net PnL：`-23.4627746535 USDT`；
- net return：`-2.34627746535%`；
- positive label：`0`；
- profitability：`INELIGIBLE_SINGLE_EPISODE`；
- result self hash：
  `2ac4e92fa32c3841548c433590cda3fea799702fdcda291d25866db2bd993fc4`；
- exact file SHA-256：
  `8627677275c31de573f1a59f638ba1678772115dc6d932027a36e2f8b62d9fee`；
- runtime uid/mode/link/size：`501 / 0600 / 1 / 5360`。

Git 副本
[challenger-episode-economic-result-v0.42.0.json](../artifacts/challenger-forward/challenger-episode-economic-result-v0.42.0.json)
与 runtime 原件逐字节一致。

## 安全边界

- archive acquisition network request：`2`（官方 ZIP + checksum）；
- result CLI market/Broker/order/Runner/state-write：`0/0/0/0/0`；
- binary float、time、price 和 fee override 均禁止；
- 没有账户 credential、余额读取、Broker 或订单能力；
- owner-only 原始日档未提交 Git。

## 验证

- committed result focused 回归：9/9；
- completion/archive/evaluator/result CLI 相邻回归：35/35；
- 全量 tests：578/578；
- Golden Vector：41；
- Evaluator build input：181；
- Build input tree hash：
  `8cee33e8c9474385b571cece010e9d87d218b5380871a2dbe1aa295035a119e5`；
- Evaluator build hash：
  `b05838499d8519e393f337883d611c3ac7cf14f1887a59f051fddb5af4cba72d`；
- `make validate`：完成；生产门禁继续保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 解释

这是首个真实前向 Episode 的研究经济代理，证明测量链可以忠实记录不利结果。负值
不能因“样本少”而删除，但单个样本也不能外推长期亏损。策略是否有正期望仍需持续
累积不可回填 Episode，并在固定成本口径下估计均值、回撤、尾部风险和下置信界。

AI 仍不进入交易链。只有简单基线形成足够连续前向证据后，才允许 AI 在完全相同
事件、时间、资本、成本和执行条件下做配对增量比较。

## 下一步

保留本负样本并继续自然收集后续 Episode；不得重置 registration、改参重跑或只
挑选正样本。后续阶段应把多 Episode 累计统计、停机规则和 AI 配对实验作为新的
结果前冻结设计。
