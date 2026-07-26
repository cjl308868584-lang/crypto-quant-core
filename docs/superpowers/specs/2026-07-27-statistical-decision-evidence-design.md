# v0.14 可重放统计决策证据设计

状态：Approved under delegated authority

日期：2026-07-27

适用增量：v0.14.0

## 1. 目标

把 ReleaseGatePolicy 已经声明、但当前仍不可执行的三项统计约束变成可重放证据：

1. 使用 Holm step-down 控制累计试验家族的 family-wise error rate；
2. 计算主要端点实际双侧 95% 置信区间宽度；
3. 在预先冻结的最小经济相关效应（MERE）处计算达成功效。

本增量围绕“更可靠地识别可赚钱策略”建设证伪能力，而不是把统计显著等同于盈利。通过这些门只说明候选结果在预先声明的误报率、精度和检验能力下仍成立；生产激活仍保持关闭，也不增加 Broker、API key 或真实下单能力。

## 2. 当前缺口

现有 Policy 和 Metric Catalog 已包含：

```text
simultaneous_release_adjustment = HOLM_V1
familywise_alpha = 0.05
ACHIEVED_POWER_AT_MERE_V1
PRIMARY_ENDPOINT_CI_WIDTH_V1
```

但 Estimator Registry 没有对应可执行实现，也没有 Artifact 能证明：

- family 是否包含全部累计试验；
- 原始 p 值是否由冻结的 OOS/Audit 序列重算；
- Holm 排名和 step-down 停止位置是否正确；
- CI 是否来自同一冻结序列和同一 Bootstrap 设计；
- 功效是否使用 MERE 和 Holm 调整后的 alpha；
- 上传方是否只填写了一个有利标量。

因此当前 Gate 必须失败关闭。v0.14 的任务不是放松这个状态，而是补齐从来源事实到 Gate 结果的完整执行链。

## 3. 方案比较

### 方案一：直接接收三个标量

GateEvidence 上传 `adjusted_p_value`、`ci_width` 和 `power`。

拒绝原因：无法证明 family 完整、来源序列一致或计算方法正确；上传方可以省略失败试验、选择有利区间或填写有利功效。

### 方案二：拆分候选推断 Artifact 与 Family Artifact

每个候选生成一个推断 Artifact，再生成一个只引用候选哈希的 Holm Family Artifact。

暂不采用原因：复用性较好，但会引入跨 Artifact 版本、冻结时间、缺失候选和引用完整性问题。Phase 0 当前没有需要独立复用候选推断的下游消费者。

### 方案三：统一 `StatisticalDecisionSnapshot`

一个 Artifact 冻结累计 Trial Registry、全部候选来源、统一统计设计、完整 Holm 过程以及当前候选的 CI 和功效结果。Evaluator 从嵌入的 `StatisticalSeriesSnapshot` 重算全部派生量。

采用原因：

- 一个自哈希边界可同时证明 family 完整性和当前候选身份；
- 三个 Estimator 使用同一来源，不会发生 p 值、CI 和功效基于不同样本的漂移；
- 中止、失败和无效 Trial 仍进入 family 大小；
- Release Evidence 只需冻结一个新增 Artifact；
- 实现边界足够小，适合 v0.14，未来需要复用时仍可升级拆分。

## 4. `StatisticalDecisionSnapshot v1`

新增：

```text
config/statistical-decision-snapshot-v1.schema.json
src/crypto_quant/statistical_decision.py
```

Artifact 顶层包含：

```text
schema_version = 1.0.0
snapshot_id
snapshot_hash
hash_algorithm = SHA-256
canonicalization = RFC8785_JCS
trial_family_id
current_candidate_id
release_gate_policy_id/version
metric_catalog_id/version
statistical_design_policy_id/hash
experiment_manifest_id/hash
scope
design
trial_registry
trial_registry_hash
analysis_status = COMPUTED | INCONCLUSIVE
analysis_reason_codes
family_results
current_candidate_results_or_null
generated_at
replay_verified = true
```

所有 Decimal 使用规范字符串；所有业务运算在固定 Decimal Context 中完成，禁止 binary float。自哈希计算时仅把 `snapshot_hash` 替换为 64 个零。

### 4.1 Scope

一个 Snapshot 只服务一个发布评估 Scope。以下字段在全部可评估 Trial 间必须一致：

```text
evaluation_ledger
release_route
direction
venue
deployment_line_id/hash
evaluation_window_start/end
approved_production_capital_usdt
endpoint_id
endpoint_unit
endpoint_direction = GREATER
```

候选的 `recipe_release_id/hash` 可以不同，这是 family 比较的对象。`current_candidate_id` 对应的 recipe 必须与 GateEvidence 实际 Scope 完全一致。

OOS 和 SEALED_AUDIT 必须生成不同 Snapshot；不得把 Audit 序列用于选择 OOS 候选，也不得在同一 Artifact 混合两个 Ledger。

### 4.2 统一统计设计

`design` 明确冻结：

```text
minimum_economic_effect
null_boundary
confidence_level = 0.95
confidence_side = TWO_SIDED
ci_method = PERCENTILE_MBB_V1
raw_p_value_method = CENTERED_MBB_GREATER_ADD_ONE_V1
power_method = SHIFTED_CENTERED_MBB_AT_MERE_V1
effective_sample_method = GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1
multiple_testing_method = HOLM_V1
family_wise_alpha = 0.05
block_length
minimum_block_count
resample_count
seed
sampling_rule = OVERLAPPING_NON_CIRCULAR_MBB_TRUNCATE_TO_N
quantile_rule = CONSERVATIVE_NEAREST_RANK_V1
```

这些值必须同时满足：

- block length、minimum block count、resample count、seed、confidence
  level、sampling rule 和 quantile rule 与当前及全部可评估候选的来源
  `bootstrap_design` 精确一致；
- 来源序列继续使用既有 `confidence_side = LOWER_ONE_SIDED` 表达其正式
  LCB 用途；本 Artifact 的 `confidence_side = TWO_SIDED` 只表达新增精度
  区间用途，两者不得因为 side 不同而被判为设计冲突；
- 与 ExperimentManifest 的 MERE、target power、trial family、Holm 和 FWER alpha 精确一致；
- Artifact 中的 StatisticalDesignPolicy ID/hash 与 Release Evidence 冻结绑定一致；
- 生成时间不早于评估窗口结束，冻结政策和 Manifest 的时间必须早于首次结果揭晓。

任一设计字段缺失、冲突或在结果后改变均返回 `FAIL`，不得降级为 `INCONCLUSIVE`。

### 4.3 Trial Registry 完整性

`trial_registry` 按 `candidate_id ASC` 保存累计 family，每个条目包含：

```text
candidate_id
candidate_status = EVALUATED | ABORTED | FAILED | INVALID
recipe_release_id/hash
source_series_snapshot_or_null
source_series_hash_or_null
```

规则：

- `candidate_id` 全局唯一，`current_candidate_id` 必须存在且状态为 `EVALUATED`；
- `len(trial_registry)` 必须等于 ExperimentManifest `actual_total_trials`；
- 规范化 Registry 身份投影的业务哈希必须等于 Manifest
  `trial_registry_hash`；该投影只包含 candidate ID、status 和 recipe
  ID，不包含 Recipe hash 或结果揭晓后才产生的 source series hash；
- `trial_family_id` 必须等于 Manifest 中冻结的家族 ID；
- 改模型名称、特征、seed、超参数、阈值、端点实现或 recipe 不能重置 family；
- `EVALUATED` 必须嵌入完整且自哈希有效的 `StatisticalSeriesSnapshot`；
- `ABORTED`、`FAILED` 和 `INVALID` 不允许附带结果序列，但仍计入 family 大小，并以原始 p 值 `1` 参加 Holm 排名；
- family 为空、当前候选缺失或 Trial 数量/哈希不一致时返回 `FAIL`。

该设计保守地防止删除失败尝试来降低多重检验惩罚。未来如果 Trial Registry 独立成为一等 Artifact，可在不改变统计语义的前提下改为外部引用。

Trial Registry 身份哈希不得包含 `recipe_release_hash` 或
`source_series_hash`：Recipe 和来源序列本身都绑定 ExperimentManifest
hash，如果 Manifest 再通过 Trial Registry hash 反向包含它们，会形成不可
构造的密码学循环。Registry 仍通过 candidate ID、status 和 recipe ID
禁止删除或改名；全部 Recipe/source hash 则由 Snapshot 自哈希、
GateEvidence `artifact_hashes` 和 Supporting Observation 完整集合承诺，
不能被替换或遗漏。

## 5. 可重放统计方法

### 5.1 共同 MBB 内核

设来源观察为 `x[0..n-1]`，区块长度为 `L`，重采样次数为 `B`。

沿用现有确定性 MBB：

```text
overlapping, non-circular blocks
start_count = n - L + 1
blocks_per_sample = ceil(n / L)
sample is truncated to n
draw start = SHA256("MBB_V1:{seed}:{replicate}:{draw}:{start_count}:{attempt}")
```

每个候选必须满足：

```text
n >= L
floor(n / L) >= minimum_block_count
n >= 3
```

区块或观察不足返回 `INCONCLUSIVE`。自哈希、Scope、设计或来源重放错误返回 `FAIL`。零方差使功效和 p 值不可辨识，返回 `INCONCLUSIVE`。

统计量按来源 `aggregation` 计算：

```text
SUM  -> sum(sample)
MEAN -> sum(sample) / n
```

### 5.2 原始单侧 p 值

对假设：

```text
H0: theta <= null_boundary
H1: theta >  null_boundary
```

先计算观察统计量 `theta_hat`。对原观察做中心化，生成 B 个 MBB 误差统计量：

```text
residual_i = x_i - mean(x)
error_b = statistic(MBB(residual))
null_stat_b = null_boundary + error_b
raw_p = (1 + count(null_stat_b >= theta_hat)) / (B + 1)
```

使用 add-one 规则避免有限重采样产生伪零 p 值。输出为精确 Decimal 比率。

### 5.3 双侧 95% CI 与宽度

从原始 `x` 生成 B 个 MBB 统计量并升序排列。令：

```text
alpha = 1 - confidence_level = 0.05
lower_rank = max(1, ceil(B * alpha / 2))
upper_rank = min(B, ceil(B * (1 - alpha / 2)))
lower = sorted_replicates[lower_rank - 1]
upper = sorted_replicates[upper_rank - 1]
width = upper - lower
```

`PRIMARY_ENDPOINT_CI_WIDTH_V1` 只返回当前候选的规范 Decimal `width`。Gate 阈值继续从冻结的 StatisticalDesignPolicy 路径解析；Estimator 不接受上传方另传阈值。

### 5.4 Holm step-down

family 大小 `m` 等于完整 Trial Registry 长度。按以下稳定顺序排序：

```text
raw_p ASC,
candidate_id ASC
```

第 `i` 名（从 1 开始）的阈值为：

```text
holm_threshold_i = family_wise_alpha / (m - i + 1)
```

从第一名开始：

- 若 `raw_p_i <= holm_threshold_i`，该候选拒绝 H0，继续下一名；
- 首次不满足时停止，该候选及其后所有候选均不拒绝 H0；
- `ABORTED`、`FAILED`、`INVALID` 的 `raw_p = 1`，永远不能通过。

`HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1` 返回当前候选的布尔 `rejected`。Snapshot 同时保存每个候选的 rank、raw p、阈值、是否已到达和是否拒绝，Validator 必须全部重算后精确比较。

### 5.5 MERE 达成功效

当前候选的有效 alpha 使用其实际 Holm rank 阈值：

```text
adjusted_alpha = family_wise_alpha / (m - current_rank + 1)
```

如果 step-down 在当前候选之前已经停止，Holm Gate 为 false；功效仍按该预先确定公式重算并报告，但不能替代 Holm Gate。

使用与原始 p 值相同的中心化 MBB 误差 `error_b`：

```text
null_stat_b = null_boundary + error_b
critical_rank = min(B, ceil(B * (1 - adjusted_alpha)))
critical_value = sorted(null_stat)[critical_rank - 1]
alternative_stat_b = null_boundary + minimum_economic_effect + error_b
achieved_power = count(alternative_stat_b > critical_value) / B
```

严格 `>` 与原假设方向一致，并对临界点采取保守处理。`ACHIEVED_POWER_AT_MERE_V1` 返回规范 Decimal 比率。

Artifact 还必须用现有 `GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1` 重算当前候选 `effective_event_count`，并与 GateEvidence `sample_status.effective_event_count` 精确匹配。MBB 直接保留序列依赖结构；ESS 用于证明样本状态和复杂度 Gate 使用的是同一来源，不用二次缩放 Bootstrap 方差。

## 6. 派生结果与防篡改

当 `analysis_status = COMPUTED` 时，`analysis_reason_codes` 必须为空，
`family_results` 为按 Holm 排名保存的完整列表：

```text
candidate_id
candidate_status
raw_p_value
holm_rank
holm_threshold
step_reached
rejected
```

`current_candidate_results` 包含：

```text
observed_statistic
effective_event_count
ci_lower
ci_upper
ci_width
holm_adjusted_alpha
holm_rejected
minimum_economic_effect
achieved_power
```

这些字段是可审计缓存，不是可信输入。`statistical_decision_snapshot_reasons` 必须从来源序列重算并逐字段精确比较；只重算自哈希而不重算派生结果不能使篡改通过。

当来源和绑定均合法，但区块、方差或重采样分辨率不足时：

```text
analysis_status = INCONCLUSIVE
analysis_reason_codes = sorted unique fixed reason codes
family_results = []
current_candidate_results = null
```

Validator 必须重放出相同的 `INCONCLUSIVE` 状态和原因；上传方不能自行把一个本应 `COMPUTED` 的结果降级隐藏，也不能把不确定结果填写成数值。结构、哈希、Scope、family 或绑定错误仍直接返回 `FAIL`，不得写进 `analysis_reason_codes` 冒充样本不足。

## 7. Estimator 与 Gate

Estimator Registry 新增三个可执行实现：

```text
PRIMARY_ENDPOINT_CI_WIDTH_V1
  callable: statistical_decision.primary-endpoint-ci-width
  output: canonical Decimal

ACHIEVED_POWER_AT_MERE_V1
  callable: statistical_decision.achieved-power-at-mere
  output: canonical Decimal ratio

HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1
  callable: statistical_decision.holm-family-adjusted-primary-pass
  output: boolean
```

Metric Catalog 新增：

```text
primary_endpoint_holm_adjusted_pass
audit_primary_endpoint_holm_adjusted_pass
```

并把新 Estimator 定义写入 `algorithms`。ReleaseGatePolicy 在 `SAMPLE` 中新增 required gate：

```text
HOLM_ADJUSTED_PRIMARY_PASS
metric = primary_endpoint_holm_adjusted_pass
comparator = EQ
threshold = true
```

在 `AUDIT_BASE_ARM` 中新增对应 required gate：

```text
AUDIT_BASE_HOLM_ADJUSTED_PRIMARY_PASS
metric = audit_primary_endpoint_holm_adjusted_pass
comparator = EQ
threshold = true
```

现有 `ACHIEVED_POWER`、`ACTUAL_CI_WIDTH` 及 Audit 对应 Gate 保留并改为可执行。任何一个 Gate 失败或不确定都不得晋级。

## 8. Release Evidence 信任链

使用上述任一 Estimator 的 GateEvidence 必须：

- 在 `frozen_release_inputs.statistical_decision_snapshot` 冻结 Artifact ID/hash；
- 在 Trust Context 提供同名完整 Artifact 文档及匹配哈希；
- 同时冻结并提供 StatisticalSeries、ExperimentManifest、StatisticalDesignPolicy 和 ReleaseGatePolicy 的准确引用；
- `artifact_hashes` 包含 Snapshot、自身来源 series、所有可评估 family member series 和 Trial Registry 哈希；
- Supporting Observation Bundle 的 `source_artifact_hashes` 包含上述完整集合且不得重复；
- 当前候选 Scope、recipe、ledger、window、capital、direction、venue 和 endpoint 与 GateEvidence 完全一致；
- `sample_status.effective_event_count` 与 Snapshot 重算结果一致；
- Estimator execution hash 纳入 Gate 结果哈希。

`release.py` 新增 `statistical_decision_snapshot` 专用路由和 reference validator。三个 Estimator 不得回退到 GateEvidence 上传标量，也不得在 Artifact 缺失时尝试使用普通 `statistical_series_snapshot` 猜测 family。

## 9. Schema、Golden Vector 与构建绑定

Schema 必须：

- `additionalProperties: false`；
- 限制版本、枚举、ID、SHA-256、日期时间和 Decimal；
- 对 EVALUATED/非可评估 Trial 使用条件 Schema；
- 要求 Trial Registry 至少一项，并根据 `analysis_status` 条件约束结果：
  `COMPUTED` 必须有完整 family/current 结果，`INCONCLUSIVE` 必须使用空列表和 `null`；
- 要求 Snapshot 所有设计字段显式存在。

Golden Vector 至少覆盖：

1. 两个可评估候选的 Holm step-down 正例；
2. 一个中止 Trial 仍扩大 family 的正例；
3. Holm 首次失败后停止的正例；
4. CI 宽度的确定性 Decimal 结果；
5. MERE 功效的确定性 Decimal 结果；
6. family 缺员、Trial Registry hash 不匹配、来源序列篡改和派生值篡改的 `FAIL`；
7. 区块不足、零方差和分辨率不足 Artifact 的确定性 `INCONCLUSIVE`；
8. Decimal 全局 Context 改变不影响结果/hash。

Evaluator Build Manifest 必须包含新 Schema、源码、Registry、Golden Vector、Metric Catalog 和 Gate Policy 哈希。发布前重新生成构建哈希和 Golden report，禁止手工填写。

## 10. 失败语义

返回 `FAIL`：

- Artifact/来源自哈希、Schema、Scope、policy/manifest 绑定不一致；
- Trial Registry 数量、family ID 或 hash 不一致；
- 当前候选缺失、非 EVALUATED 或 recipe 不匹配；
- family 派生 p 值、排序、阈值、停止状态、CI、ESS 或功效缓存不匹配；
- 设计在候选间不一致或与冻结 Manifest 不一致；
- Decimal、时间、ID 或来源序列非法。

返回 `INCONCLUSIVE`：

- 当前候选或任一需要重算 p 值的候选区块不足；
- 当前候选零方差，无法辨识 p 值/功效；
- Bootstrap 重采样数量不足以解析 Holm 调整后的 alpha，即
  `1 / (B + 1) > adjusted_alpha`。

最后一条防止 family 很大但重采样次数太少时产生虚假的“最小 p 值已足够”。`FAIL` 和 `INCONCLUSIVE` 均不能转成通过。
三个 Estimator 读取合法的 `INCONCLUSIVE` Snapshot 时必须返回同一状态和原因，不得返回 `null` 的 `COMPUTED`。

## 11. 非目标

v0.14 不包括：

- 自动搜索最优策略或自动修改超参数；
- Bayesian optimization、深度学习或 LLM 直接生成交易信号；
- 风险效率端点的成对区间；
- Paper Trading 数据采集；
- 实盘资金、Broker 连接、API key 管理或订单发送；
- 用合成 Golden Vector 宣称系统已经可以赚钱。

## 12. 验收标准

- 三个 Estimator 均在 Registry 中可执行并通过 Golden Vector；
- Holm required Gate 在 SAMPLE 和 AUDIT_BASE_ARM 中实际执行；
- 删除失败/中止 Trial、篡改 family 排名或替换来源序列均失败关闭；
- CI 宽度和 MERE 功效可从冻结来源精确重放；
- Release Evidence 缺少 Snapshot 或任一来源绑定时失败；
- 全量测试和 `make validate` 通过；
- 实现状态文档明确仍为 `DESIGN_BASELINE`、生产关闭；
- 版本更新为 `0.14.0`，合并后创建 annotated tag `v0.14.0`。
