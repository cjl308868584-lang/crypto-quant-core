# ADR-0015：配对风险效率必须重放两臂路径

状态：Accepted

日期：2026-07-27

## 背景

`RISK_EFFICIENCY` 要求最大回撤和 ES95 改善的一侧 95% 配对
Moving-block Bootstrap 下界。既有 Catalog 已声明两个 Estimator，但
v0.14 以前没有可执行实现。现有配对增长序列只对 AI-minus-baseline
逐观察差值求和，不能恢复两条权益路径，也不能诚实表达 Minor
candidate-vs-active 比较。

## 决策

新增 `PairedRiskEvaluationSnapshot v1`，冻结 reference/candidate 两臂
StatisticalSeries、每个观察引用的 EconomicLedgerSnapshot、比较主体、
配对报告、政策和 Bootstrap 设计。

风险段从经济快照的相邻权益点重放现金流和成本调整后的对数收益。每个
bootstrap replicate 使用同一组匹配观察段索引重采样两臂，并在重采样
路径内分别重算风险。

最大回撤定义为：

```text
max(1 - exp(current_log_equity - prior_peak_log_equity))
```

经验 ES95 定义为所有正损失幅度 `max(0, -log_return)` 中最差
`max(1, ceil(5% × M))` 项的算术平均，不做插值。

每个 replicate 的改善统计量使用固定的原始 reference 风险作分母：

```text
(resampled_reference_risk - resampled_candidate_risk)
/ observed_reference_risk
```

这避免全上涨重采样产生零随机分母，也不选择性丢弃 replicate。

风险路径保留所有匹配窗口，包括动作未变化窗口。存在未配对窗口、没有
changed pair、区块不足或原始 reference 风险为零时返回
`INCONCLUSIVE`。结构、哈希、角色、来源或重放不一致返回 `FAIL`。

## 被拒绝的方案

- 对逐观察收益差直接计算风险：差值不能恢复高水位或尾部排序。
- 上传两臂 MDD/ES95 标量：标量没有可重采样单位，也无法证明来源。
- 继续把 Minor 两臂命名为 baseline/AI：会混淆配方基线与活动 Bundle。

## 后果

- AI-vs-baseline 和 Minor candidate-vs-active 共用同一数学口径；
- 两个风险 Estimator 都必须从专用 Artifact 执行；
- Supporting Observation 必须列出 Artifact、两臂 Series 和全部经济快照；
- 合成 Golden/单元测试只能证明实现确定且失败关闭，不能证明策略赚钱。
