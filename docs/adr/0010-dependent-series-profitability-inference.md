# ADR-0010：依赖时间序列的盈利下置信界

状态：Accepted
日期：2026-07-26

## 背景

v0.9.0可以从账本重放单个窗口的全成本经济PnL，但“某个窗口赚钱”仍不能证明策略具有可重复的经济价值。加密货币收益存在自相关、重叠持有期和市场状态聚集，直接使用独立同分布假设、随机shuffle或名义交易数会低估不确定性。

发布规范要求：

- 主终点使用一侧95% Moving-block Bootstrap下界；
- 月度经济PnL只使用完整UTC自然月；
- 区块长度来自SplitPolicy；
- 最小区块数和重采样次数来自StatisticalDesignPolicy；
- 随机种子来自ExperimentManifest；
- 有效样本数使用Geyer Initial Positive Sequence；
- 样本或区块不足必须INCONCLUSIVE，不得按点估计PASS。

## 决策

### 1. StatisticalSeriesSnapshot

新增版本化统计序列Artifact，绑定：

- 账户、经济账本、route、方向、venue、Recipe和DeploymentLine；
- 完整评估窗口和批准生产资本；
- Accounting、CostAllocation、Split、StatisticalDesign Policy的ID与hash；
- ExperimentManifest ID/hash；
- 有序观察值、每个观察的经济快照来源hash和月度完整性；
- block length、minimum block count、resample count及seed；
- self-hash、来源经济快照hash集合和重放验证状态。

来源经济快照必须按时间排序、窗口不重叠、Scope和会计政策完全一致。来源hash必须与观察值一一对应、顺序一致且不得重复。

月度经济PnL采用`MONTHLY_RESET_TO_APPROVED_CAPITAL`：每个自然月从同一批准资本重新评估，避免资本复利或不同初始资本把“USDT/月”变成不可比较的单位。月度来源快照的开始清算权益必须等于批准资本。

### 2. 完整UTC月

完整月定义为：

```text
当月1日 00:00:00Z → 下月1日 00:00:00Z
```

系统独立计算`calendar_month_complete`，不信任提交方布尔值。部分月可以出现在序列首尾并被月度估算器排除；内部月份缺失、重叠或部分月份均使Artifact失败。Scope边界必须等于第一条观察开始和最后一条观察结束。

### 3. Geyer ESS

在时间排序贡献序列上：

```text
gamma_k = biased autocovariance at lag k
rho_k = gamma_k / gamma_0
依次检查 (rho_1 + rho_2), (rho_3 + rho_4), ...
在第一组非正pair前停止
tau = max(1, 1 + 2 × sum(retained rho))
ESS = floor(n / tau)
```

零方差、少于3个观察或非重叠区块数不足返回INCONCLUSIVE。ESS不得超过原始样本数。

### 4. Moving-block Bootstrap

算法冻结为：

1. 使用长度为`L`的重叠、非循环连续区块；
2. 每次抽取`ceil(n/L)`个区块，连接后截断到原序列长度；
3. 抽样索引由SHA-256 counter stream和冻结seed确定，不依赖Python随机库；
4. SHA-256到区块索引采用rejection sampling，避免模运算偏差；
5. 重采样次数至少1,000；
6. 一侧95%下界采用保守nearest-rank：排序后取`ceil(0.05 × B)`的样本；
7. 月度PnL统计量为完整月份的均值；主终点贡献统计量为评估窗口总和。

所有Decimal计算使用函数内固定50位、ROUND_HALF_EVEN上下文，调用方修改全局Decimal context不能改变结果或execution hash。

### 5. 类型与证据隔离

- `ONE_SIDED_95_MOVING_BLOCK_BOOTSTRAP_V1`只接受`PRIMARY_ENDPOINT_CONTRIBUTION`及`SUM`。
- `MONTHLY_ECONOMIC_PNL_MBB_LCB95_V1`只接受`MONTHLY_ECONOMIC_PNL_USDT`及`MEAN`。
- `COMPLETE_UTC_CALENDAR_MONTH_COUNT_V1`只接受月度经济PnL序列。
- 两种序列不能因为数值格式相同而互相替代。
- GateEvidence与Supporting Observation必须绑定统计序列、全部来源经济快照、实验、批准资本和四类政策hash。

### 6. 经济log growth

在相邻保守清算权益点之间：

```text
adjusted_end
  = ending_liquidation_equity
  - interval_external_cash_flow
  - interval_allocated_cost

period_log_growth = ln(adjusted_end / starting_liquidation_equity)
window_log_growth = sum(period_log_growth)
```

任何开始或调整后权益非正都失败关闭。分段链式计算避免把窗口中途充值的时间点错误处理为策略收益。

## 不变量

- 不用名义交易数替代有效样本数。
- 不把部分月份包装成完整月份。
- 不允许缺失的内部月份在无报告情况下被跳过。
- 不允许同一盈利经济快照重复贡献多个观察。
- 不允许结果揭晓后改变block length、重采样次数或seed。
- 不允许月度PnL序列冒充主终点净增长序列。
- Bootstrap代码通过不等于真实策略盈利下界为正。

## 备选方案

- 普通IID Bootstrap：拒绝，破坏时间依赖结构。
- Python `random.Random`：拒绝，发布证据不应依赖运行时PRNG实现细节。
- Circular Bootstrap：本版本拒绝，边界拼接可能创造不存在的跨期相邻关系。
- 正态近似置信区间：拒绝，收益分布通常偏态且厚尾。
- 用累计总PnL除月份数：拒绝，无法保留依赖结构和下界不确定性。
- 允许调用方直接上传收益数组：拒绝，缺少经济快照来源和Scope证明。

## 后果

- 57个Catalog算法中14个可执行，新增ESS、通用MBB、月度PnL MBB、完整UTC月计数和经济log growth。
- 43个算法继续失败关闭，包括配对AI Bootstrap、leave-out脆弱性、功效、CI宽度、Holm校正、DSR和PBO。
- 代码现在可以验证“给定一组真实、获批、完整的逐月经济快照，其月度盈利LCB是多少”，但仓库中没有真实获批数据，所以仍不能声称系统已证明赚钱。

## 验证证据

- 统计序列Schema：`config/statistical-series-snapshot-v1.schema.json`
- 算法和来源构建器：`src/crypto_quant/statistics.py`
- Registry及Golden vectors：`config/estimator-registry-v1.json`、`config/estimator-golden-vectors-v1.json`
- Evidence和Supporting绑定：`src/crypto_quant/release.py`、`src/crypto_quant/release_artifacts.py`
- 确定性、反篡改、部分月、样本不足和来源完整性测试：`tests/test_statistics.py`
