# ADR-0013：删除 Top-5 正贡献完整交易后的经济路径重放

状态：Accepted  
日期：2026-07-27

## 背景

ReleaseGatePolicy 已要求基线、审计基线和审计 AI 路径通过“删除
Top-5 正贡献交易后的净对数增长下置信界”门。此前
`LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1`只能 Fail-Closed，
因为交易不是独立的收益数组元素：一次交易可能跨多个 Fill、多个统计周期并包含
Funding，删除它会改变持仓、未实现盈亏、退出费用和后续权益路径。

用“删除五个最大正收益事件”代替完整交易重放，会把路径依赖问题错误简化为数组
删除，并可能高估策略在去除集中盈利后的稳健性。

## 决策

新增 `TradeReplaySnapshot v1` 和可执行 Estimator
`LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1`。实现固定为以下语义：

1. 完整交易按单一 `instrument_id` 的持仓从零开始、经历一个或多个 Fill、再回到零
   的周期定义。开仓前已有持仓、期末未平仓周期和跨零 Fill 均不具备删除资格。
2. `trade_id` 由 scope、instrument 和有序 Fill ID 计算业务哈希，上传方不能提供或
   覆盖；exchange trade ID、订单 ID、Proposal ID 均不作为交易周期主键。
3. EconomicLedgerSnapshot v1.1 为每个事实保存不可变
   `source_event_sequence`；Fill 还保存 exchange/local/venue order identity。
   事实顺序固定为 `(event_time, source_event_sequence, stable fact ID)`。
4. 删除前必须用可执行估值 checkpoint 重放原始路径，并在每个 EquityPoint 精确
   复现持仓成本、预期退出费用、清算权益及源统计 observation。任一不一致立即
   `FAIL`。
5. 使用移动平均成本法计算完整交易贡献。原始正贡献从高到低排序，并列按
   `trade_id` 升序，最多选五个；不足五个时删除全部正贡献交易，没有正交易时仍
   生成可验证的反事实序列。
6. 反事实删除所选周期的全部 Fill 及其持仓期间归属的 Funding。外部现金流和所有
   allocated cost 保留，因为它们不是某笔盈利交易可选择性抹除的成本。
7. Fill price 已含 spread/slippage，`implementation_shortfall_usdt` 只作为审计事实，
   不再次扣减，避免双重计算成交成本。
8. 从删除后的事件路径重新计算 liquidation equity、每期经济净对数增长和
   StatisticalSeries v1.2，再执行既有一侧 95% moving-block bootstrap。
9. GateEvidence 必须同时冻结 TradeReplaySnapshot 与源
   StatisticalSeries；Supporting Observation 必须列全 replay、源序列、全部经济
   快照、反事实序列和每期反事实 replay hash。

## 被拒绝的替代方案

- 直接删除最大正收益 Fill：一个零到零周期可能含多个加仓、减仓 Fill，会破坏持仓
  路径。
- 使用交易所 `exchange_trade_id`：它通常标识单次成交，不等于完整持仓周期。
- 使用 Proposal 或审计事件近似交易：研究决策边界与实际成交/持仓边界不同。
- 直接从收益数组减去五个最大值：无法重算 Funding、未实现盈亏、退出费用和后续
  权益。
- 用数组位置推断事件顺序：数组可重排，不能替代账本的不可变 sequence。
- 删除 shared cost 或外部现金流：这会选择性美化反事实经济结果。

## 对赚钱目标的意义

该门回答的是：

> 如果移除原始路径中最赚钱的五个完整持仓周期，并按真实经济规则重放剩余路径，
> 策略的保守收益下界是否仍满足冻结门槛？

它能识别“总利润主要由极少数交易支撑”的脆弱策略，比删除事件或收益数组元素更
接近真实资金路径。但它只降低错误放行概率，不创造 alpha，也不证明策略或 AI
已经赚钱。

## 后果

- EconomicLedgerSnapshot 新增向后兼容的 v1.1 可回放事实身份。
- StatisticalSeries 新增 v1.2 反事实 replay provenance。
- Estimator Registry 由 20 个增加到 21 个可执行实现；不可执行项由 37 个降至
  36 个。
- Golden vectors 由 29 个增加到 33 个，覆盖计算、无正交易、样本不足和 Funding
  持仓不一致。
- 三个 Top-5 Trade Gate 现在均解析到同一确定性实现。
- 合成 Fixture 只证明代码边界和失败关闭语义；没有封存历史或 Paper 数据时，
  不能据此声明真实收益。

## 验证

- 原始路径、交易周期与反篡改：`tests/test_trade_replay.py`
- EconomicSnapshot v1.1：`tests/test_economics.py`、`tests/test_replay.py`
- Registry、Golden 与 build manifest：`tests/test_estimators.py`
- GateEvidence 与 Supporting Observation 来源绑定：
  `CompleteTradeReplayEvidenceTests`

