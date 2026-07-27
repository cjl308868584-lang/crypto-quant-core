# 实施追踪 v0.18.0

日期：2026-07-27

状态：已完成并验证

## 本版本完成

- 新增只允许 ETHUSDT 的离线 Paper plan，生产 transport 禁用环境代理；
- 网络侧严格限制为 4 个 Binance market-data-only 无凭据 GET；
- 先接收 4h warmup 和 exchangeInfo，再冻结决策时刻，之后才允许获取 BBO
  和 AggTrade；
- 保存并重放所有原始 response、客户端请求/接收/记录时刻、HTTP metadata、
  body hash 和 receipt self-hash；
- 从 `exchangeInfo` 解析 TRADING/Spot/MARKET 资格、PRICE_FILTER、LOT_SIZE
  及 MIN_NOTIONAL/NOTIONAL 中更保守的最小名义价值；
- 冻结 `SPOT_LONG_SMA20_VOL12_BUCKET25_V1` 简单基线；
- 使用既有 StrategyProposal、MetaDecision、TargetPosition 正式契约和 lineage；
- 冻结 `OFFLINE_PAPER_CONSERVATIVE_BBO_V1`，同时计算进场滑点、双边费用、
  可见流动性限制、tick/step 取整和保守退出；
- 基线与 AI 分别写入独立临时 SQLite WAL，生成完整可重放
  EconomicLedgerSnapshot；
- 没有批准模型时，AI 臂明确 `NOT_RUN_NO_APPROVED_MODEL`、零成交、统计
  配对不合格；
- 新增严格 Schema、Artifact self-hash、外部 attestation 和原子不可变 CLI；
- 固定 Paper/盈利资格为 `OFFLINE_PAPER_SMOKE_ONLY` /
  `INSUFFICIENT_DURATION_AND_AI`。

## 真实官方 smoke

来源：`https://data-api.binance.vision`，Spot `ETHUSDT`，无凭据 GET。

- Artifact：`artifacts/paper/binance-offline-paper-smoke-v0.18.0.json`
- 决策时刻：`2026-07-27T13:30:54.977Z`
- 运行结束：`2026-07-27T13:30:58.455Z`
- 原始 response：4，全部 HTTP 200
- 已收盘 4h Kline：199
- AggTrade：100，窗口内可观测 aggregate ID gap：0
- BBO bid/ask：1952.89 / 1952.90 USDT
- 最新 close / 前 20 根 SMA：1959.67 / 1889.2445
- 年化 4h log-return 波动：0.33433323121249730060238153014254021040449405456216
- 基础波动暴露：0.3589233399408321428251390876
- 基线决策：LONG / SET_TARGET / 25%
- 模拟成交：BUY 0.0459 ETH @ 1954.86，名义价值 89.728074 USDT
- 假设进场费用：0.134592111 USDT
- 基线起始/立即保守清算权益：1000 / 999.5506993585 USDT
- AI：`NOT_RUN_NO_APPROVED_MODEL`，零成交，结束权益 1000 USDT
- Run hash：
  `3aaac1899b8db2f64567ef0790f2be4fac9703c6a9949aa7ec4576b21b0e4814`
- External attestation：
  `709c81d9884d7db45cf2b02f39f4bb9a422c68027dc39cd93a47aa07f725d1db`
- Trusted replay reasons：空

基线立即保守清算变化为 -0.4493006415 USDT，约 -0.04493%。这是把进场
滑点、退出滑点、进场费和预期退出费全部立即施加后的执行成本压力值；它
没有等待 24h 预测期限，因此既不是策略真实收益，也不能据此判断策略亏损
或盈利。

## 安全与经济审查

- 4 个请求均为固定 host/path/query 的公开 GET；
- Artifact 明确记录 `credentials_read=false`、
  `account_endpoints_called=false`、`orders_submitted=false`；
- 模块没有 Broker、账户、密钥、订单提交或任意 URL/header 参数；
- 两臂账本物理隔离且 scope 分别为 BASELINE_ONLY/AI_ENHANCED；
- fill price 已含滑点，EconomicLedger 不重复扣除 implementation shortfall；
- fee 独立计入，结束权益另计保守退出价格和预期退出 fee；
- exchangeInfo 只提供公开 symbol filter，账户费用和账户特定 filter 仍明确
  unknown；
- 8 项固定警告全部保留，未因 smoke 成功而降级。

## 最终验证证据

- 新增 offline Paper/CLI tests：16 项，0 失败
- 原子发布兼容聚焦 tests：18 项，0 失败
- 全量 tests：323 项，0 失败
- Golden Vector：41 项
- Golden report：
  `e3e7dc45865d860489514a574c64ca14a8dd6f089a0b74129414231741882fc3`
- Catalog：58
- 可执行 Estimator：26
- 明确 unavailable：32
- Evaluator build input：64 个冻结文件
- Evaluator build input tree：
  `33f2b56e37370727e26788d461213a2f7014414327f0ecf80169b412fb353f44`
- Evaluator build：
  `0cb972b6b0594061fde174a420499181bf0ed77bd4602cc9af95fbb0cd1f4b8d`
- release/governance/schema/build validators：执行成功；
  Release Policy 仍按设计返回 `DESIGN_BASELINE` /
  `PRODUCTION_ACTIVATION_DISABLED`
- Artifact trusted replay：PASS
- 4-public-GET boundary：PASS
- 经济对账：PASS；保守退出价 1950.93、预期退出费
  0.1343215305、结束清算权益 999.5506993585
- 安全边界：PASS；无凭据、账户、Broker 或订单能力

## 赚钱与 AI 含义

v0.18 改进的是“成本不会被漏掉”和“AI 不会被伪造”，而不是证明 alpha。
真实 smoke 的立即保守清算为负，说明单次入场至少要先克服约 4.5 bps 的
本实现压力成本；长期策略是否有净收益仍必须由 90 天以上、覆盖市场状态的
连续 Paper 决策和真实账户成本事实回答。

当前仍不能声称：

- 简单基线长期扣费后赚钱；
- AI 优于简单基线或平台 AI；
- 当前 15 bps 假设等于实际账户费率；
- 单次 smoke 具备统计功效或 OOS ReleaseEvidence；
- 任何 Bundle 获得真实资金资格。

## 下一优先级

1. 将同一离线 Paper cycle 变成固定 4h 长期调度，累计至少 90 天；
2. 补 NTP/server-time offset、永续 Mark/Index/Premium/OI 和 Funding 上下文；
3. 经外部批准后冻结真实账户 FeeSchedule，仍先保持无下单 Paper；
4. 训练并封存候选 AI bundle，只在同 proposal/time 输入上做过滤器；
5. AI 未通过 paired economic/risk/statistical gates 时继续保持基线独立；
6. 所有 Paper/Shadow 门槛通过前，不接账户、不加 Broker、不下单。
