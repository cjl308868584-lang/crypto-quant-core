# ADR-0011：AI相对简单基线的配对增量价值

状态：Accepted
日期：2026-07-27

## 背景

v0.10.0可以计算单条受信经济序列的依赖时间序列下置信界，但不能回答“AI是否比简单基线多赚钱”。直接比较两个独立回测总收益会混入候选事件、市场窗口、资本、成交模型和成本政策差异，也可能把AI没有改变基线行为的时点计入有效样本。

Release Audit要求AI路线同时保留：

- `BASELINE_LEDGER`：冻结的`NO_AI_BASE`行为；
- `AI_LEDGER`：候选AI行为及其增量数据、推理、训练、监控和审计成本；
- `PAIRED_COMPARISON`：只按相同`proposal_id + decision_time`连接两臂；
- 两臂自身的绝对盈利门，以及AI减基线的增量门。

配对结果不能替代任一臂的绝对盈利证明。

## 决策

### 1. AI路线允许独立基线账本

`BASELINE_LEDGER`既可以属于`BASELINE_ONLY`，也可以作为`AI_ENHANCED`的对照臂。`AI_LEDGER`和`PAIRED_COMPARISON`仍只能属于`AI_ENHANCED`。

AI路线的基线经济快照和统计序列使用ExperimentManifest冻结的`baseline_recipe_release_id/hash`；AI臂及配对Artifact使用候选RecipeRelease。两臂共享账户、方向、venue、DeploymentLine、窗口、批准资本、Accounting、CostAllocation、Split、StatisticalDesign和Experiment。

### 2. StatisticalSeriesSnapshot v1.1

原Schema增加`PAIRED_AI_ECONOMIC_NET_LOG_GROWTH_DELTA`类型。配对Artifact内嵌两条完整来源序列，而不是接受一组无来源的delta数组，并绑定：

- 基线和AI两条StatisticalSeriesSnapshot及其self-hash；
- 两臂全部EconomicLedgerSnapshot来源hash；
- 基线Recipe、候选Recipe、ModelBundle和AI endpoint；
- Experiment及四类统计/经济Policy；
- 相同批准生产资本和Bootstrap设计；
- 完整配对观察与未配对报告。

正式Evidence还必须列出配对Artifact、两条来源序列及所有经济来源hash。任何缺失、替换或跨实验复用均失败关闭。

### 3. 配对和样本资格

唯一配对键为：

```text
(proposal_id, decision_time)
```

同一臂出现重复键直接失败。匹配观察还必须具有相同period、fold和冻结窗口。未配对观察不进入估计，但必须分别报告基线侧和AI侧的ID、键及经济来源hash。

只有以下任一条件为真时，该配对观察才进入ESS和Bootstrap：

```text
baseline_action != ai_action
OR
baseline_absolute_exposure_ratio != ai_absolute_exposure_ratio
```

AI没有改变动作和绝对敞口的时点保留在Artifact中用于审计，但不扩大名义或有效样本。

### 4. 增量定义

每个合格配对观察：

```text
delta_value
  = ai_economic_net_log_growth_contribution
  - baseline_economic_net_log_growth_contribution
```

AI臂贡献已经包含AI增量成本，因此delta中不得再次扣除同一USDT成本。两臂值、delta、动作、敞口及两个经济来源hash全部冻结，Evaluator根据内嵌来源序列重新推导；上传方不能单独改写delta。

### 5. 配对Moving-block Bootstrap

`ONE_SIDED_95_PAIRED_MOVING_BLOCK_BOOTSTRAP_V1`只接受配对增量序列：

1. 先按时间保留合格配对观察；
2. 使用SplitPolicy冻结的非循环重叠区块；
3. 使用ExperimentManifest seed和StatisticalDesignPolicy重采样次数；
4. 每次对delta区块整体重采样，保持配对关系；
5. 统计量为评估窗口增量log growth总和；
6. 返回保守nearest-rank一侧95%下界；
7. 没有AI改变样本、区块不足或无法计算ESS时返回INCONCLUSIVE。

GROWTH路线只有在基线臂和AI臂各自通过绝对门后，才允许用该下界与0比较。

### 6. 收益集中度压力

新增三个可执行Estimator：

- 删除总正贡献最大的fold后重算MBB下界；
- 删除最多5个最大正贡献事件后重算MBB下界；
- 删除最大正贡献事件后重算MBB下界。

相同贡献使用稳定ID字典序打破平局。删除后样本不足返回INCONCLUSIVE。

“事件”不等于“完成交易”。原Catalog中基线top-5-trades指标误接事件Estimator，本版本修正为`LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1`并保持不可执行，直到可以按`trade_id`重放完整路径依赖账本。

## 不变量

- 不比较不同proposal或decision time。
- 不池化两个账本后再分摊收益。
- 不把未配对观察静默丢弃。
- 不把AI未改变行为的时点计入有效样本。
- 不允许不同资本、窗口、政策、实验或Bootstrap设计的两臂配对。
- 不允许配对delta掩盖基线臂或AI臂自身亏损。
- 不把事件删除近似成逐交易账本重放。
- 合成Golden Vector的正delta下界不是本项目真实AI收益。

## 后果

- 57个Catalog算法中18个可执行，39个继续明确Fail-Closed。
- Golden vectors由22个增加到27个。
- GROWTH路线的配对增量LCB和配对ESS已有确定性实现。
- 风险效率路线的配对最大回撤/ES95改善、配对leave-out整组复评、逐交易重放、Holm、实际功效、CI宽度、DSR和PBO仍不可执行。
- 当前仓库没有真实配对经济观察，因此不能声明AI优于基线或项目已经赚钱。

## 验证证据

- 配对Schema和Artifact语义：`config/statistical-series-snapshot-v1.schema.json`
- 配对构建、ESS、Bootstrap和leave-out：`src/crypto_quant/statistics.py`
- Evidence来源绑定：`src/crypto_quant/release.py`、`src/crypto_quant/release_artifacts.py`
- Registry与Golden vectors：`config/estimator-registry-v1.json`、`config/estimator-golden-vectors-v1.json`
- 配对、排除、反篡改、来源和错误映射测试：`tests/test_paired_statistics.py`
