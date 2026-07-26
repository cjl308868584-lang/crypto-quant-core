# v0.15 配对风险效率区间设计

状态：Approved under delegated authority

日期：2026-07-27

适用增量：v0.15.0

## 1. 目标

实现以下两个已在 Metric Catalog 和 ReleaseGatePolicy 中声明、但尚不可执行的估计器：

- `PAIRED_MAX_DRAWDOWN_RELATIVE_IMPROVEMENT_LCB95_V1`
- `PAIRED_ES95_RELATIVE_IMPROVEMENT_LCB95_V1`

它们必须同时支持：

1. `AI_ENHANCED/RISK_EFFICIENCY` 中 AI 相对配方基线的风险改善；
2. Initial/Audit 两套相同统计口径；
3. `MINOR_BUNDLE_REFRESH` 中候选 Bundle 相对活动 Bundle 的风险 Pareto 非劣。

本增量回答的是：

> 在同一批 OOS 决策窗口、同一经济核算政策和同一批准资本下，候选路径相对参考路径的最大回撤与 ES95 改善，是否具有一侧 95% 配对 Moving-block Bootstrap 下界？

本增量只补齐可审计的统计证据能力。合成 Golden Vector 的通过结果不代表真实策略已经盈利，也不开放交易所连接、API Key 或实盘下单。

## 2. 现状与缺口

现有 `PAIRED_AI_ECONOMIC_NET_LOG_GROWTH_DELTA` Artifact 已能：

- 按 `proposal_id + decision_time` 配对；
- 保存基线与 AI 两臂完整的来源统计序列；
- 重建逐观察收益差；
- 只对 AI 改变动作或绝对敞口的时点计算增长增量 LCB。

它不能直接充当风险改善证据，原因有四个：

1. MDD 和 ES95 是非线性路径统计量，不能对逐观察收益差求和后冒充风险差；
2. MDD 必须在每个 bootstrap 重采样路径上重新建立高水位；
3. 风险路径必须保留所有已匹配窗口；只保留“动作改变”窗口会删除共同的亏损、恢复和高水位，扭曲 MDD/ES95；
4. Minor 刷新比较的是活动 Bundle 与候选 Bundle，现有 `baseline/ai` 角色和 `BASELINE_LEDGER/AI_LEDGER` 约束无法诚实表达两臂都是 AI Bundle 的比较。

此外，现有统计序列只保存来源经济快照哈希。风险估计如果仅信任上传的 `baseline_value/ai_value`，无法证明这些值确实来自现金流和成本调整后的经济权益路径。

## 3. 方案比较

### 方案一：复用逐点 AI-minus-baseline delta

把现有 `observation.value` 的差值序列传给通用 MBB，再从差值推断风险改善。

拒绝原因：

- 不同的两条权益路径可以产生相同逐点差值，却具有完全不同的 MDD；
- ES95 的尾部排序在做差后不可逆；
- 只保留 eligible changed pairs 会破坏完整风险路径；
- 无法表达 Minor active-vs-candidate 角色。

### 方案二：分别上传两条最终风险标量

上传 baseline/candidate 的 MDD、ES95 点估计，再对标量差做区间或直接比较。

拒绝原因：

- 一个标量没有可重采样单位；
- 上传方可以选择权益采样频率、尾部定义或现金流处理；
- 无法证明两臂使用同一时间窗和同一重采样索引；
- 违反“点估计不得用于晋级”的既有治理规则。

### 方案三：通用配对风险重放 Artifact

新增 `PairedRiskEvaluationSnapshot v1`。Artifact 冻结：

- reference/candidate 两臂的完整 StatisticalSeriesSnapshot；
- 每个来源观察对应的 EconomicLedgerSnapshot；
- 比较角色和两臂主体身份；
- 配对报告、Bootstrap 设计、政策与实验身份；
- 从来源经济事实重放出的配对风险段。

估计器对相同的配对区块索引同时重采样两臂，在每个 replicate 中重建完整路径并分别计算 MDD/ES95。

采用原因：

- 同时解决路径非线性、来源真实性和 Minor 角色语义；
- 两个风险估计器共用一份配对事实与一套信任链；
- AI-vs-baseline 与 candidate-vs-active 使用相同数学算法；
- 任一缺失、错配或不可重放输入都能失败关闭；
- 不改变现有 v1.1 增长配对 Artifact，保持兼容。

## 4. `PairedRiskEvaluationSnapshot v1`

新增：

```text
config/paired-risk-evaluation-snapshot-v1.schema.json
src/crypto_quant/paired_risk.py
```

Estimator 输入字段固定为：

```text
paired_risk_evaluation_snapshot
```

### 4.1 顶层身份

Artifact 至少包含：

- `$schema`, `schema_version`, `snapshot_id`, `snapshot_hash`；
- `hash_algorithm = SHA-256`；
- `canonicalization = RFC8785_JCS`；
- `comparison_role`；
- `ai_endpoint = RISK_EFFICIENCY`；
- reference/candidate 主体身份；
- reference/candidate StatisticalSeriesSnapshot；
- 去重并按声明顺序保存的 EconomicLedgerSnapshot；
- 配对观察、配对报告；
- Accounting、CostAllocation、Split、StatisticalDesign、Experiment 绑定；
- Scope、批准资本、Bootstrap 设计；
- `generated_at` 和 `replay_verified = true`。

`comparison_role` 只允许：

```text
AI_VS_RECIPE_BASELINE
MINOR_CANDIDATE_VS_ACTIVE_BUNDLE
```

### 4.2 两臂主体

统一使用 `reference_arm` 与 `candidate_arm`，不复用含义不同的 `baseline/ai` 名称。

每臂包含：

- `role`；
- `subject_type`；
- `subject_id`；
- `subject_hash`；
- `statistical_series_snapshot`。

角色矩阵：

| comparison_role | reference role/type | candidate role/type |
|---|---|---|
| `AI_VS_RECIPE_BASELINE` | `RECIPE_BASELINE` / `RECIPE_RELEASE` | `AI_CANDIDATE` / `MODEL_BUNDLE` |
| `MINOR_CANDIDATE_VS_ACTIVE_BUNDLE` | `ACTIVE_BUNDLE` / `MODEL_BUNDLE` | `MINOR_CANDIDATE` / `MODEL_BUNDLE` |

AI-vs-baseline 的 reference scope 必须是 `BASELINE_LEDGER`，candidate scope 必须是 `AI_LEDGER`。

Minor 比较的两臂 scope 都必须是 `AI_LEDGER`；reference 主体必须绑定 GateEvidence/DeploymentLine 声明的活动 Bundle，candidate 主体必须绑定当前送审 ModelBundle。

### 4.3 来源统计序列

两臂都必须是：

```text
series_kind = PRIMARY_ENDPOINT_CONTRIBUTION
aggregation = SUM
capital_normalization = APPROVED_CAPITAL_EVALUATION_WINDOW
```

每个观察必须含有：

- `proposal_id`；
- `decision_time`；
- `fold_id`；
- `recommended_action`；
- `absolute_exposure_ratio`；
- `period_start`、`period_end`；
- `source_economic_snapshot_hash`；
- 现金流调整后经济对数收益 `value`。

两臂必须完全一致的字段：

- account、route、direction、venue；
- deployment line；
- evaluation window；
- approved capital；
- Accounting、CostAllocation、Split、StatisticalDesign、Experiment；
- Bootstrap 设计。

允许两臂 recipe/model 主体不同；其他统计设计不得不同。

### 4.4 经济来源快照

Artifact 必须嵌入每个来源观察引用的 EconomicLedgerSnapshot，且：

- 哈希唯一；
- 每个引用恰好解析为一个快照；
- 不允许未引用的额外快照；
- 快照自身语义验证通过；
- 快照 Scope、政策、窗口和 ledger role 与所属 arm 一致；
- 使用 `CASH_FLOW_ADJUSTED_ECONOMIC_LOG_GROWTH_V1` 重算后必须精确等于观察 `value`。

因此风险估计不信任上传方预先计算的 MDD、ES95 或风险改善标量。

## 5. 配对与风险段

### 5.1 配对键

配对键继续固定为：

```text
proposal_id + decision_time
```

匹配项还必须在以下字段完全相同：

- `period_start`；
- `period_end`；
- `fold_id`。

配对结果按：

```text
decision_time ASC, proposal_id ASC
```

排序。

Artifact 保存完整配对报告：

- 两臂观察数；
- 匹配数；
- changed/unchanged 数；
- 两侧未配对明细。

风险估计至少要求一个动作或绝对敞口发生变化。若没有变化，返回 `INCONCLUSIVE / PAIRED_RISK_NO_CHANGED_PAIRS`。

风险路径要求完整配对。任何未配对观察返回：

```text
INCONCLUSIVE / PAIRED_RISK_INCOMPLETE_PAIRING
```

原因是删除一个窗口会改变高水位和尾部样本，不可把它当作中性缺失。

### 5.2 风险段重放

每个匹配观察的每一臂，从来源 EconomicLedgerSnapshot 的有序权益点重放一个归一化经济收益段。

相邻权益点的现金流调整经济对数收益沿用现有正式算法：

```text
r_t = ln(
  (
    current_liquidation_equity
    - interval_external_cash_flow
    - interval_allocated_cost
  )
  / previous_liquidation_equity
)
```

分母或调整后分子非正时整个 Artifact `FAIL`。

段内保存：

- 严格递增的权益时间；
- canonical Decimal 对数收益序列；
- 来源 EconomicSnapshot hash；
- 来源 observation ID 与所属 StatisticalSeries hash 绑定。

段收益和必须精确等于来源 StatisticalSeries observation `value`。

两臂在同一匹配观察中可以有不同的内部权益采样点数量，但必须共享观察窗口边界。Bootstrap 的重采样单位是匹配观察段，而不是臂内单个权益点。

## 6. 确定性配对 Moving-block Bootstrap

两项估计器共用同一个重采样内核。

设完整匹配观察段数为 `N`，区块长度为 `L`。样本充足条件沿用：

```text
N >= L
floor(N / L) >= minimum_block_count
```

否则：

```text
INCONCLUSIVE / PAIRED_RISK_INSUFFICIENT_BLOCKS
```

每个 replicate：

1. 使用现有 `MBB_V1` SHA-256 rejection sampling；
2. 从 `N-L+1` 个非循环重叠区块中抽样；
3. 同一组区块索引同时应用于 reference 与 candidate；
4. 保留每个被抽中段的内部时间顺序；
5. 拼接后截断到 `N` 个观察段；
6. 分别重建两臂统计量；
7. 计算风险改善统计量。

固定：

```text
confidence_level = 0.95
confidence_side = LOWER_ONE_SIDED
sampling_rule = OVERLAPPING_NON_CIRCULAR_MBB_TRUNCATE_TO_N
quantile_rule = CONSERVATIVE_NEAREST_RANK_V1
```

LCB 为排序后第：

```text
max(1, ceil(0.05 * resample_count))
```

个 replicate 值。

所有业务算术使用固定 precision 50、`ROUND_HALF_EVEN` 的 `Decimal`；禁止 binary float。

## 7. 最大回撤改善

### 7.1 路径

把所选段的全部对数收益按顺序拼接，设置：

```text
log_equity_0 = 0
log_equity_t = sum(r_1 ... r_t)
```

最大回撤使用对数高水位直接计算：

```text
MDD = max(1 - exp(log_equity_t - prior_peak_log_equity))
```

初始权益 1 进入高水位集合。该定义对名义资本缩放不敏感。

### 7.2 改善统计量

先在原始完整 reference 路径计算 `observed_reference_mdd`。若为零：

```text
INCONCLUSIVE / PAIRED_RISK_REFERENCE_MDD_ZERO
```

每个 bootstrap replicate 使用固定的原始 reference 分母：

```text
mdd_improvement_b
  = (reference_mdd_b - candidate_mdd_b)
    / observed_reference_mdd
```

采用固定原始分母，而不是每个 replicate 的随机分母，原因是全上涨重采样可能产生零 MDD；固定分母仍精确对应“相对原始参考风险的配对风险减少”，同时避免选择性丢弃零风险 replicate。

点估计仍报告为：

```text
(observed_reference_mdd - observed_candidate_mdd)
/ observed_reference_mdd
```

但 Gate 只使用 LCB。

## 8. ES95 改善

### 8.1 冻结的经验 ES95

每个经济对数收益对应正损失幅度：

```text
loss_t = max(0, -r_t)
```

对长度 `M` 的损失序列：

```text
tail_count = max(1, ceil(0.05 * M))
ES95 = mean(largest tail_count losses)
```

该定义把 ES95 固定为最差 5% 经济对数收益的平均正损失幅度，不使用插值分位数，不受库版本影响。

### 8.2 改善统计量

先计算完整原始 reference 路径的 `observed_reference_es95`。若为零：

```text
INCONCLUSIVE / PAIRED_RISK_REFERENCE_ES95_ZERO
```

每个 replicate：

```text
es95_improvement_b
  = (reference_es95_b - candidate_es95_b)
    / observed_reference_es95
```

点估计使用对应的 observed 两臂 ES95，Gate 仍只使用 LCB。

## 9. Estimator 与 Metric Catalog

Registry 新增两个可执行条目，均：

- 输入 `paired_risk_evaluation_snapshot`；
- 输出 canonical decimal；
- deterministic = true；
- binary_float_allowed = false；
- 至少绑定一个正向 Golden Vector 和失败关闭向量。

Metric Catalog 对两个算法补充：

- 风险路径来源；
- 经验 ES95 的 tail-count 规则；
- MDD/ES95 bootstrap statistic 的固定 observed reference 分母；
- 零参考风险、未完整配对和样本不足状态。

现有六个 exact metric override 不改 ID：

- AI Initial MDD/ES95；
- AI Audit MDD/ES95；
- Minor candidate-vs-active MDD/ES95。

## 10. Release Evidence 与信任链

以下 Schema/逻辑增加 `paired_risk_evaluation_snapshot`：

- `release-evidence-v1.1.schema.json`；
- `supporting-observation-bundle-v1.schema.json`；
- `release.py` frozen input/reference validation；
- `release_artifacts.py` supporting observation validation；
- Evaluator build manifest 的 artifact schema 集合。

正式执行必须证明：

- GateEvidence frozen input 的 ID/hash 等于实际 Artifact；
- Artifact comparison role 与 release kind/metric 用途一致；
- candidate 主体等于 GateEvidence 当前 ModelBundle；
- AI-vs-baseline 的 reference recipe 等于 ExperimentManifest baseline；
- Minor 的 reference bundle 等于 GateEvidence/DeploymentLine active bundle；
- Artifact、两臂 StatisticalSeries、全部 EconomicSnapshot hash 都出现在证据来源集合；
- Supporting Observation 的 `source_artifact_hashes` 完整包含整条嵌套来源链；
- Estimator 重执行后的状态、值、版本、原因码和 execution hash 完全一致。

缺少专用 Artifact 时不得回退到 GateEvidence 上传标量、普通 paired delta series 或自由键值。

## 11. 失败关闭分类

`FAIL` 用于不可信或自相矛盾证据，例如：

- Schema、自哈希、来源哈希或嵌套 Artifact 被篡改；
- 角色、主体、Scope、Policy、Capital、Bootstrap 设计不匹配；
- 经济快照无法重放观察收益；
- 非正权益；
- 时间乱序、重叠或来源重复；
- Estimator 用错 endpoint 或 comparison role。

`INCONCLUSIVE` 用于证据真实但不足以形成区间，例如：

- 无 changed pair；
- 存在未配对窗口；
- 区块数不足；
- 原始 reference MDD 为零；
- 原始 reference ES95 为零。

两者都不能成为 PASS。

## 12. 测试与验收

### 12.1 数学正确性

- 手算路径验证 MDD；
- 手算最差 5% 尾部验证 ES95；
- 相同区块索引同时作用于两臂；
- MBB 非循环、截断、nearest-rank 与现有内核一致；
- 固定 observed reference 分母；
- 全局 Decimal context 变化不影响结果或哈希。

### 12.2 Artifact 防篡改

分别篡改：

- 两臂 observation value；
- 经济权益点、现金流、成本；
- 配对结果与配对报告；
- 主体 ID/hash 与 comparison role；
- Scope、政策、批准资本、Bootstrap seed；
- 嵌套来源哈希和来源顺序。

重新自哈希后仍必须因语义重放不一致而失败。

### 12.3 两类比较

- AI-vs-baseline 正向路径；
- Minor candidate-vs-active 正向路径；
- 两类角色互换或 ledger role 错配失败；
- Minor active bundle 与 DeploymentLine 不一致失败。

### 12.4 Release 集成

- 六个 exact metric 都解析到可执行 Estimator；
- 专用 Artifact 缺失时 Gate 失败；
- Supporting Observation 缺任一嵌套来源 hash 时失败；
- 上传 scalar 不能替代重执行；
- Artifact Scope 与 GateEvidence 不一致失败。

### 12.5 回归

- 现有 paired growth、ESS、trade replay、StatisticalDecision 全部保持通过；
- Registry 与 Golden Vector 完整性通过；
- JSON Schema 全量验证通过；
- Evaluator build hash 与 Golden report 重新冻结；
- 全量 `unittest` 通过。

## 13. 文档、版本与边界

新增 ADR：

```text
docs/adr/0015-paired-risk-efficiency-bootstrap.md
```

发布状态文档：

```text
docs/implementation-status-v0.15.0.md
```

版本更新为 `0.15.0`，发布后创建 annotated tag `v0.15.0`。

明确保留到后续增量的事项：

- RISK_EFFICIENCY 的配对 leave-out 整组复评；
- DSR/PBO 的可执行实现；
- 真实历史数据接入和策略盈利验证；
- Broker、密钥管理、实盘订单与自动部署。

本增量的完成标准是“风险效率统计门可被可信地执行”，不是“系统已经证明能赚钱”。
