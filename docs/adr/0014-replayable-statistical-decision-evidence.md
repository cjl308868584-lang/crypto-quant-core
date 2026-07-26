# ADR-0014：可重放的统计决策证据

状态：Accepted

日期：2026-07-27

## 背景

ReleaseGatePolicy 已声明累计试验家族的 Holm 多重检验、主要端点双侧
95% 区间宽度和最小经济相关效应（MERE）处的实际功效门，但此前对应
Estimator 不可执行。GateEvidence 若只上传调整后 p 值、区间宽度或功效标量，
Evaluator 无法证明试验家族完整、三个结果来自同一冻结序列，也无法阻止删除失败
Trial 或选择有利 Bootstrap 结果。

## 决策

新增统一的 `StatisticalDecisionSnapshot v1`。它冻结累计 Trial Registry、全部
可评估候选的源 `StatisticalSeriesSnapshot`、共同 Bootstrap 设计、完整 Holm
step-down 过程，以及当前候选的区间、ESS 和 MERE 功效。三个 Estimator 只读取
这一可信 Artifact：

- `HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1`
- `PRIMARY_ENDPOINT_CI_WIDTH_V1`
- `ACHIEVED_POWER_AT_MERE_V1`

失败、中止或无效 Trial 保留在 family 中，`raw_p = 1`；不能通过删除或改名逃避
多重检验惩罚。注册表身份投影稳定的 candidate、状态和 Recipe Release ID，
具体 Recipe、源序列和构建身份继续由快照、GateEvidence 与 Supporting
Observation 的外层哈希完整绑定，从而避免 Artifact 身份循环。

### 原始单侧 p 值

对 `H0: theta <= null_boundary`、`H1: theta > null_boundary`，使用与冻结设计一致的
重叠、非循环、截断到原长度的 moving-block bootstrap：

```text
residual_i = x_i - mean(x)
error_b = statistic(MBB(residual))
null_stat_b = null_boundary + error_b
raw_p = (1 + count(null_stat_b >= theta_hat)) / (B + 1)
```

add-one 规则避免有限重采样产生伪零 p 值。

### 双侧 95% 区间

```text
alpha = 1 - confidence_level = 0.05
lower_rank = max(1, ceil(B * alpha / 2))
upper_rank = min(B, ceil(B * (1 - alpha / 2)))
lower = sorted_replicates[lower_rank - 1]
upper = sorted_replicates[upper_rank - 1]
width = upper - lower
```

该双侧区间用于精度判断；源统计序列原有的一侧保守下界用途保持不变。

### Holm step-down

family 大小 `m` 等于完整 Trial Registry 长度，按 `raw_p ASC,
candidate_id ASC` 稳定排序：

```text
holm_threshold_i = family_wise_alpha / (m - i + 1)
```

从第一名开始，`raw_p_i <= holm_threshold_i` 时拒绝 H0 并继续；首次不满足时停止，
当前及后续候选均不拒绝 H0。

### MERE 达成功效

当前候选使用其实际 Holm rank 阈值：

```text
adjusted_alpha = family_wise_alpha / (m - current_rank + 1)
null_stat_b = null_boundary + error_b
critical_rank = min(B, ceil(B * (1 - adjusted_alpha)))
critical_value = sorted(null_stat)[critical_rank - 1]
alternative_stat_b = null_boundary + minimum_economic_effect + error_b
achieved_power = count(alternative_stat_b > critical_value) / B
```

功效不能替代 Holm Gate。Artifact 还使用
`GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1` 重算当前候选 ESS，并与
GateEvidence 样本状态精确匹配。

## 信任与失败关闭

Evaluator 重算全部派生量，并绑定 Artifact 自哈希、冻结证明、Policy/Catalog
身份、ExperimentManifest、trial family、MERE、FWER alpha、Trial 数量、注册表
哈希、Recipe、账户、资本/端点/窗口 Scope、ESS 和全部可评估源序列哈希。每个
嵌入源序列还必须通过 StatisticalSeries Schema，并与权威 accounting、
cost-allocation、split 和 statistical-design policy ID/hash 一致。Supporting
Observation 必须列全快照、注册表和 family 源哈希。
StatisticalSeries Schema 校验同时位于 Estimator Registry 输入边界，不能通过
绕开 GateEvidence 直接调用 Estimator 接受结构不完整的嵌入源。

样本或区块不足、零方差、Bootstrap 分辨率不足以解析 Holm alpha 时返回
`INCONCLUSIVE`；此时没有派生 ESS 缓存，不把合法 null 误判为 ESS 篡改。哈希、
Scope、设计、来源或缓存重放不一致时失败关闭。

## 被拒绝的替代方案

- 接受 GateEvidence 上传的 p 值、区间宽度或功效标量：无法验证来源与 family。
- 为 Holm、区间和功效建立三个独立 Artifact：容易发生样本、设计和版本漂移。
- 从 family 删除失败、中止或无效 Trial：会系统性低估多重试验惩罚。
- 使用二进制浮点或环境随机数：无法提供跨运行、跨环境一致的精确重放。

## 对赚钱目标的意义

该决策降低因重复试验、宽区间或低功效而错误放行“看起来赚钱”候选的概率。它改善
证据质量和假阳性控制，但不创造 alpha，不证明 AI 优于简单基线，也不证明策略
已经产生可交易净利润。

## 后果

- 58 个 Catalog 算法中 24 个可执行、34 个明确 Fail-Closed。
- Golden vectors 增至 39 个，覆盖 Holm、区间、功效及不确定边界。
- SAMPLE 和 AUDIT_BASE_ARM 的 Holm、区间宽度与功效门均从同一可信快照执行。
- Artifact 和 Supporting Observation 更大，Bootstrap 功效判断更保守。
- Policy 仍为 `DESIGN_BASELINE`，生产激活仍关闭；仓库没有 Broker、密钥或真实
  下单能力。

## 验证

- 统计重放与防篡改：`tests/test_statistical_decision.py`
- Registry、Golden 与 build manifest：`tests/test_estimators.py`
- GateEvidence、Manifest、Scope 与来源绑定：`tests/test_evidence.py`
- required Gate 与失败关闭：`tests/test_release.py`
