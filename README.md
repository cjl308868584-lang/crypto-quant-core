# 虚拟货币量化策略系统

这是一个以“扣除全部成本后获得可重复的实盘收益”为目标的个人加密货币量化项目。

项目当前处于设计基线阶段。任何回测收益、模型准确率或论文结果都不构成实盘盈利承诺；系统首先要证明数据、验证、执行和风险闭环可信，然后才允许逐级使用真实资金。

## 当前权威文档

1. [系统计划 v1.1](docs/system-plan-v1.1.md)
2. [核心数据契约与订单状态机 v1.1](docs/contracts-and-state-machines-v1.1.md)
3. [AI 研究与模型治理 v1.1](docs/ai-research-governance-v1.1.md)
4. [开发路线与验收门槛 v1.1](docs/delivery-roadmap-v1.1.md)
5. [发布评估与证据规范 v1.1](docs/release-evaluation-spec-v1.1.md)
6. [开源项目参考与取舍 v1.1](docs/open-source-reference-notes-v1.1.md)
7. [机器可读发布门槛 v1.1](config/release-gates-v1.1.json)
8. [指标目录 v1.1](config/release-metrics-v1.1.json)
9. [政策 Schema](config/release-gates-v1.1.schema.json)
10. [指标 Schema](config/release-metrics-v1.1.schema.json)
11. [证据 Schema](config/release-evidence-v1.1.schema.json)
12. [RecipeRelease Schema](config/recipe-release-v1.1.schema.json)
13. [ModelBundle Schema](config/model-bundle-v1.1.schema.json)
14. [Approved Fallback Registry Schema](config/approved-fallback-registry-v1.1.schema.json)
15. [治理Artifact模板Schema](config/governance-artifact-v1.schema.json)
16. [未审批治理模板目录](config/templates/)
17. [Estimator Registry](config/estimator-registry-v1.json)
18. [Estimator Registry Schema](config/estimator-registry-v1.schema.json)
19. [Estimator Golden Vectors](config/estimator-golden-vectors-v1.json)
20. [Estimator Golden Vector Schema](config/estimator-golden-vectors-v1.schema.json)
21. [Evaluator Build Manifest](config/evaluator-build-manifest-v1.json)
22. [Evaluator Build Manifest Schema](config/evaluator-build-manifest-v1.schema.json)
23. [ExperimentManifest Schema](config/experiment-manifest-v1.1.schema.json)
24. [DeploymentLine Schema](config/deployment-line-v1.1.schema.json)
25. [Supporting Observation Bundle Schema](config/supporting-observation-bundle-v1.schema.json)
26. [Economic Ledger Snapshot Schema](config/economic-ledger-snapshot-v1.schema.json)
27. [Statistical Series Snapshot Schema](config/statistical-series-snapshot-v1.schema.json)
28. [Endpoint Reevaluation Snapshot Schema](config/endpoint-reevaluation-snapshot-v1.schema.json)
29. [Trade Replay Snapshot Schema](config/trade-replay-snapshot-v1.schema.json)
30. [Statistical Decision Snapshot Schema](config/statistical-decision-snapshot-v1.schema.json)
31. [ADR-0014：可重放的统计决策证据](docs/adr/0014-replayable-statistical-decision-evidence.md)
32. [实施追踪 v0.14.0](docs/implementation-status-v0.14.0.md)
33. [配对风险效率决策 ADR-0015](docs/adr/0015-paired-risk-efficiency-bootstrap.md)
34. [实施追踪 v0.15.0](docs/implementation-status-v0.15.0.md)

如果文档之间出现冲突，以《系统计划 v1.1》的产品目标和硬风险约束为最高优先级；运行数据字段以《核心数据契约》为准，各发布对象字段以对应Schema为准；机制解释以《AI 研究与模型治理》和《开发路线与验收门槛》为准；发布数值、比较运算符、必需性和样本不足结果以 `ReleaseGatePolicy` 为准，指标单位/估计器以Metric Catalog为准，条件聚合和证据作用域以《发布评估与证据规范》为准。

机器政策当前是 `DESIGN_BASELINE` 且 `production_activation.enabled=false`。在DataQuality、Split、StatisticalDesign、Accounting、CostAllocation、ForwardControl、Compliance Attestation及Evaluator build hash全部绑定前，任何正式PASS都无效；这是有意的Fail-Closed状态。

当前策略有两条互斥发布路径：

- `BASELINE_ONLY`：简单趋势/突破独立证明扣费后经济价值，AI 指标不适用。
- `AI_ENHANCED`：简单基线先通过，再证明 AI 在相同候选事件、风险和成交条件下提供增量价值。

AI 失败不阻止已经独立通过全部门槛的简单基线；简单基线失败时，AI 不得用来掩盖失败。

## 实施状态

Git中的设计基线已冻结，当前代码版本为 `0.15.0`，正在逐项执行《开发路线与验收门槛》第9节。已完成规范化哈希、Decimal/tick/step基础、版本化InstrumentMetadata、核心决策链、SQLite WAL账本与Outbox、Golden Replay、RiskLock与部署档位风控、订单UNKNOWN对账、PositionExecutor、发布Artifact信任链、可重放经济账本、依赖序列统计、AI相对简单基线的同proposal/time配对增量、删除最大正贡献单元后的完整GROWTH endpoint复评、删除Top-5正贡献完整交易后的路径依赖经济重放、累计Trial Registry上的Holm/双侧区间宽度/ESS/MERE功效重放，以及AI-vs-baseline与Minor candidate-vs-active的配对最大回撤和ES95改善区间。

当前58个Catalog算法中有26个Estimator可执行，其余32个明确Fail-Closed。风险效率估计器会从两臂统计序列与经济快照重放完整路径，在每个配对Moving-block Bootstrap样本内重新计算最大回撤和经验ES95；上传标量、普通增长差序列或不完整来源链不能替代正式证据。仓库仍只有合成Golden Fixture，不能声称策略已经赚钱或AI已优于基线，离线Paper证据管线仍未实现。当前没有Broker、交易所Adapter、API密钥读取或真实下单能力。详细完成度见[实施追踪 v0.15.0](docs/implementation-status-v0.15.0.md)，风险统计决策见[ADR-0015](docs/adr/0015-paired-risk-efficiency-bootstrap.md)。
当前依赖及许可证记录见[依赖与许可证清单 v0.1.0](docs/dependencies-and-licenses-v0.1.0.md)。

本地验证：

```bash
make validate
make test
```

`make validate`在当前设计状态输出 `FAIL` 是正确结果：缺少必需Policy绑定且生产激活开关为关闭状态。

## 已锁定的 V1 范围

- 交易所：Binance 优先，Gate 仅作为后续适配。
- 标的：资金小于 1,000 USDT 时，仅 ETH 使用真实资金；BTC 只提供市场背景和纸面信号。
- 产品：LONG 使用无保证金 ETH/USDT 现货；SHORT 使用单向、逐仓、最大 1x 的 ETHUSDT USDT 本位永续。
- 决策频率：4 小时；预测/持有目标约 24 小时；正常情况下最短持有 8 小时，并设置反手滞回。
- 策略：简单趋势/突破负责提出方向；可选XGBoost成本感知Meta模型只有证明增量价值后才负责过滤和分档；确定性风控拥有最终否决权。
- 风险：目标年化波动率 12%；风险档位仅允许 0/25/50/75/100%。
- 上线：研究、Shadow、Paper、25/50/75% Canary、Champion 逐级晋级；任何新模型不得自动接管资金。

## 明确不做

- 不使用大于 1x 的杠杆。
- 不做高频、网格、做市、跨所套利和复杂订单网络。
- 不让 LLM、Agent 或强化学习模型直接下单。
- 不用封存审计集反复调参。
- 不因回测好看而跳过 Paper、Canary、对账或风险验收。
- 不直接复制 GPL/AGPL 项目的实现代码。
