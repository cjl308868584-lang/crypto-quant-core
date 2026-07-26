# v0.13 完整交易 Top-5 删除与经济账本重放设计

状态：Approved under delegated authority

日期：2026-07-27

适用增量：v0.13.0

## 1. 目标

实现 `LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1`，用于回答：

> 在删除收益贡献最大的五笔完整交易后，策略的变量成本后净增长下界是否仍大于零？

这里的“交易”不是单个交易所成交 Fill，也不是单个 Proposal，而是同一品种仓位从零开始、经历一次或多次建仓和减仓、最终精确回到零的完整持仓周期。

本增量只提供可审计的稳健性反证工具。合成 Golden Vector 的正结果不是策略真实盈利证据，也不改变生产激活关闭状态。

## 2. 已批准的业务定义

### 2.1 完整交易周期

按单一经济 Scope 和 `instrument_id` 分别处理 Fill。固定排序为：

```text
exchange_event_time ASC,
source_event_sequence ASC,
fill_id ASC
```

当重放仓位满足以下状态转移时生成一笔完整交易：

```text
0
  → 首个非零仓位
  → 同方向加仓或不越过零的减仓
  → 0
```

交易周期的边界为首个开仓 Fill 到使仓位精确回零的 Fill，包含边界。其稳定 ID 由以下内容生成：

```text
trade_id
  = "trd:" + SHA256(
      scope identity
      + instrument_id
      + ordered fill_id sequence
    )
```

上传方不得自行声明或改写 `trade_id`。

以下周期不具备删除资格，但必须参与原路径重放：

- 评估窗口开始时已经存在的开仓；
- 到评估窗口结束仍未平仓的周期；
- 缺少边界 Fill 的周期。

Fill 导致仓位越过零、合约乘数在非零仓位期间改变，或者数量无法精确归零时，整个 Artifact 失败关闭。

### 2.2 单笔交易经济贡献

完整交易的变量成本后净经济贡献为：

```text
realized_fill_pnl
  - all_entry_and_exit_fill_fees
  + signed_funding_cashflows_during_trade
```

成交价已经包含 Spread 和 Slippage，不得再次扣减 `implementation_shortfall_usdt`。

共享基础设施、数据、训练、监控和审计等期间分配成本继续保留在反事实路径中，不随被删交易消失。这是保守处理：删除盈利交易不会获得额外的成本减免。

### 2.3 Funding 归属

Funding 按 `instrument_id + settled_at` 归属于结算时覆盖该持仓的周期。结算记录的 `position_quantity` 必须与重放仓位精确一致。

以下任一情况失败关闭：

- 非零 Funding 没有对应持仓；
- `position_quantity` 与重放仓位不一致；
- 同一 Funding 被分配到多个周期；
- Funding 时间或 ID 重复、乱序或超出窗口。

选中交易被删除时，其所属 Funding 同时删除。其他 Funding 保留。

## 3. 方案比较

### 方案一：直接删除统计观察

从 `StatisticalSeriesSnapshot` 删除五个正观察后重算 MBB。

拒绝原因：观察不等于交易；一个交易可能跨多个观察，一个观察也可能包含多笔交易。该方法无法重算资金费、费用、复利资本和持仓路径。

### 方案二：删除 EventLedger 中的 Fill 事件后重建现有投影

复制 SQLite 账本，删除 Fill 后调用现有 projection rebuild。

拒绝原因：原始 EquitySnapshot 是事实观测，不是反事实估值。保留它们会产生伪重放；删除它们后现有账本又没有逐品种可执行估值事实，无法重建权益曲线。

### 方案三：冻结专用反事实重放 Artifact

新增 `TradeReplaySnapshot v1`，冻结原 EconomicLedgerSnapshot、逐权益检查点的可执行估值、完整来源序列和政策绑定。先逐点复现原路径，再删除完整交易并重新生成经济贡献序列。

采用原因：

- 能证明输入路径与正式经济证据一致；
- 能处理分批成交、Funding、复利和多品种重叠；
- 不篡改不可变事实账本；
- 删除结果可以完整重放、哈希和纳入 Evidence 信任链；
- 任一归属或估值缺口都能明确失败关闭。

## 4. `TradeReplaySnapshot v1`

新增：

```text
config/trade-replay-snapshot-v1.schema.json
src/crypto_quant/trade_replay.py
```

Artifact 顶层至少包含：

- Schema 版本、自哈希、规范化算法和生成时间；
- 来源 `StatisticalSeriesSnapshot` 及其哈希；
- 按来源哈希唯一列出的全部 `EconomicLedgerSnapshot`；
- Accounting、CostAllocation、Split、StatisticalDesign 和 Experiment 绑定；
- 与来源序列完全一致的 Scope、批准资本和 Bootstrap 设计；
- 每个经济窗口的估值检查点；
- 原路径重放结果；
- 完整交易清单、贡献和 Funding 归属；
- 被选中删除的 `trade_id`；
- 删除后重建的 `StatisticalSeriesSnapshot`；
- `replay_verified: true`。

EconomicLedgerSnapshot 的 Fill 来源必须升级为可重放版本，并额外冻结：

```text
exchange_trade_id
local_order_id
venue_order_id
source_event_sequence
```

`exchange_trade_id` 仍只是交易所逐 Fill 去重键，不能直接作为完整周期的 `trade_id`。新版本快照的 Fill 身份、内容和顺序必须与 EventLedger 的不可变 `FillRecorded` 投影逐项一致；旧版缺少这些身份字段的快照不能升级猜测，只能对本 Estimator 返回 `FAIL`。

Funding、ExternalCashFlow、AllocatedCost 和 EquityPoint 同样增加 `source_event_sequence`。序列必须是来源 EventLedger 中严格递增的正整数；相同时间戳的跨类型事实以该序列确定先后，不允许用 ID 或数组上传顺序猜测。

### 4.1 估值检查点

每个来源 EquityPoint 必须有且只有一个相同时间戳的估值检查点。每个检查点按当时非零仓位列出：

```text
instrument_id
long_executable_exit_price_usdt
short_executable_exit_price_usdt
contract_multiplier
expected_exit_fee_usdt
valuation_source_hash
```

方向不适用的价格为 `null`。估值必须使用多头可执行 Bid 或空头可执行 Ask，并显式冻结预计退出费。不得从聚合 notional 或事后收益反推价格。

### 4.2 原路径复现门

在执行 Top-5 删除前，Evaluator 必须从期初权益、期初持仓、Fill、Funding、外部现金流、分配成本和估值检查点重建每个 EquityPoint。

账户清算权益和经济成本调整分两层计算，沿用现有 Catalog 语义：

```text
replayed_liquidation_equity
  = starting_liquidation_equity
  + realized_and_unrealized_trading_pnl_change
  - fill_fees
  + signed_funding
  + net_external_cash_flow

economic_adjusted_end_equity
  = replayed_liquidation_equity
  - interval_allocated_costs
```

`allocated_costs` 不得同时进入第一式和第二式。原路径复现比较第一式与来源 `liquidation_equity_usdt`；来源观察复现和反事实 log growth 使用第二式。这样与现有 `period_economic_pnl` 和 `cash_flow_adjusted_economic_log_growth` 保持一致。

必须逐点精确匹配：

- `liquidation_equity_usdt`；
- `position_cost_bases`；
- `expected_exit_fee_accrued_usdt`；
- 期末权益；
- 来源观察的经济增长贡献；
- 来源序列的观察顺序与哈希序列。

任何 Decimal、时间、Scope、来源哈希或逐点值不匹配时，不允许执行删除，返回 `FAIL`。

## 5. Top-5 选择和重放

### 5.1 排名

仅对经济贡献严格大于零的合格完整交易排序：

```text
economic_contribution_usdt DESC,
trade_id ASC
```

- 正贡献交易不少于五笔：精确删除前五笔；
- 正贡献交易少于五笔：删除全部正贡献交易；
- 没有正贡献交易：删除空集合，但仍完整重跑并输出结果。

### 5.2 反事实事件处理

删除集合中的：

- 全部 Fill；
- 已验证归属于该交易的全部 Funding。

保留：

- 其他交易的 Fill 和 Funding；
- 外部现金流；
- 全部期间分配成本；
- 原始估值检查点；
- 原 Bootstrap 设计、seed 和观察边界。

删除后从窗口期初按原顺序重新计算：

- 仓位和移动平均成本；
- 已实现与未实现 PnL；
- 手续费和 Funding；
- 每个检查点的清算权益；
- 每个来源观察的变量成本后净 log growth。

不得直接从原观察值减去交易贡献。

### 5.3 统计输出

删除后生成一条完整的 `PRIMARY_ENDPOINT_CONTRIBUTION` 系列：

- 保留原观察 ID、period、fold、Proposal 元数据和 Bootstrap 设计；
- 更新 `value`；
- 来源哈希改为本次反事实重放产生的经济快照哈希；
- 重新计算 `series_hash`；
- 使用 `ONE_SIDED_95_MOVING_BLOCK_BOOTSTRAP_V1` 的同一内核计算一侧 95% LCB。

每个来源观察必须与一个 EconomicLedgerSnapshot 具有完全相同的 period 边界和唯一来源哈希。反事实观察继续保留原 `source_economic_snapshot_hash` 作为事实来源，并新增由 Artifact 自身推导的 `counterfactual_replay_period_hash`；该字段证明变化后的值来自哪一段反事实路径。反事实序列顶层同时增加 `counterfactual_replay_id`，避免引用尚未计算的 Artifact 自哈希形成循环。StatisticalSeriesSnapshot Schema 升级后必须禁止普通事实序列携带这些字段，也禁止反事实序列缺少这些字段。

样本或区块不足返回 `INCONCLUSIVE`。Artifact、Schema、Scope、来源或重放不一致返回 `FAIL`。`FAIL` 与 `INCONCLUSIVE` 均不得晋级。

## 6. 信任链与发布集成

### 6.1 Estimator Registry

新增可执行 Estimator：

```text
LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1
implementation_id:
  trade_replay.leave-top-5-positive-trades-out-mbb-lcb95
input:
  trade_replay_snapshot
output:
  canonical Decimal
```

Registry、Metric Catalog、Golden Vector、Evaluator Build Manifest 和构建哈希必须同步升级。

### 6.2 GateEvidence

使用该 Estimator 的每个 GateEvidence 必须冻结：

- `trade_replay_snapshot_hash`；
- 原来源 series hash；
- 全部来源 economic snapshot hashes；
- 删除后 series hash；
- selected trade IDs；
- Estimator execution hash。

Supporting Observation Bundle 必须验证这些引用均存在、唯一、同 Scope 且哈希可重算。

### 6.3 Release 行为

原先因 Estimator 不可执行而失败关闭的三个门可以进入正常解析：

- `BASE_LEAVE_TOP_5_TRADES_OUT`；
- `AUDIT_BASE_LEAVE_TOP_5_TRADES_OUT`；
- `AUDIT_AI_LEAVE_TOP_5_TRADES_OUT`。

这不代表整个 Release Policy 会通过；其他不可执行 Estimator、缺失正式数据或未批准治理仍继续失败关闭。

## 7. API 与数据流

主构建 API：

```python
trade_replay_snapshot(
    *,
    replay_id,
    source_series_snapshot,
    economic_snapshots,
    valuation_checkpoints,
    generated_at,
) -> dict
```

构建器负责：

1. 验证所有输入 Artifact；
2. 验证完整一一来源绑定；
3. 重放并逐点复现原路径；
4. 派生完整交易周期和 Funding 归属；
5. 排名并选择删除集合；
6. 反事实重放；
7. 构建删除后 series；
8. 计算所有自哈希并再次语义验证。

Estimator 不信任构建器标记，会重新推导关键结果并比较 Artifact 声明。

## 8. 错误处理

核心失败码至少包括：

```text
TRADE_REPLAY_SCHEMA_INVALID
TRADE_REPLAY_SELF_HASH_MISMATCH
TRADE_REPLAY_SOURCE_SERIES_MISMATCH
TRADE_REPLAY_ECONOMIC_SOURCE_MISMATCH
TRADE_REPLAY_SCOPE_MISMATCH
TRADE_REPLAY_VALUATION_MISSING
TRADE_REPLAY_VALUATION_DUPLICATE
TRADE_REPLAY_ORIGINAL_EQUITY_MISMATCH
TRADE_REPLAY_ORIGINAL_POSITION_MISMATCH
TRADE_REPLAY_ORIGINAL_SERIES_MISMATCH
TRADE_REPLAY_FILL_CROSSES_ZERO
TRADE_REPLAY_MULTIPLIER_CHANGED
TRADE_REPLAY_FUNDING_POSITION_MISMATCH
TRADE_REPLAY_TRADE_ID_MISMATCH
TRADE_REPLAY_SELECTION_MISMATCH
TRADE_REPLAY_COUNTERFACTUAL_MISMATCH
```

统计样本不足沿用：

```text
STATISTICAL_SERIES_INSUFFICIENT_BLOCKS
```

## 9. 测试策略

严格按 TDD 增加以下行为测试：

1. 分批开仓、加仓、减仓和平仓只形成一个完整交易；
2. 多品种重叠周期独立生成稳定 `trade_id`；
3. 期初已有仓位和期末未平仓均不可入选；
4. Fill 越零和合约乘数改变失败关闭；
5. Funding 只归属于结算时的精确持仓；
6. 原始路径不能逐点复现时拒绝反事实删除；
7. 按贡献降序和 `trade_id` 升序稳定选择五笔；
8. 少于五笔和零笔正贡献边界；
9. 删除整笔交易会删除全部 Fill 和所属 Funding；
10. 期间分配成本与外部现金流保留；
11. 删除后从事实重建观察，而不是执行算术减法；
12. 不同 Decimal context 下输出和 execution hash 一致；
13. Schema、自哈希、来源哈希、Scope、选中 ID 和反事实输出篡改均失败；
14. Golden Vector 至少包含成功、无正交易、Funding 不一致和样本不足；
15. Release 三个 Top-5 Trade 门使用新 Estimator，且缺少 Artifact 时失败关闭；
16. 全量 `make test`、`make validate` 和生产策略审计符合预期。

每个测试必须指出它能捕获的具体错误，并使用手工推导的字面量期望值。

## 10. 非目标

v0.13 不包括：

- 真实交易所或 Broker 接入；
- 真实资金下单；
- Holm family-wise 校正；
- MERE 实际功效或双侧 CI 宽度；
- `RISK_EFFICIENCY` 的配对 MDD/ES95；
- 离线双臂 Paper 数据生成管线；
- 非 Golden 历史盈利证据。

这些仍按 v0.12 路线依次推进。

## 11. 版本与交付

计划升级：

- 包版本：`0.13.0`；
- 新增 ADR-0013；
- 新增 v0.13.0 实施状态；
- 更新 README、Registry、Metric Catalog、Build Manifest 和依赖哈希；
- 全量验证通过后提交并创建 `v0.13.0` Git tag。

设计规格必须先单独提交；实施代码在后续提交中完成。
