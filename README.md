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
35. [Historical Market Data Snapshot Schema](config/historical-market-data-snapshot-v1.schema.json)
36. [Fee Schedule Snapshot Schema](config/fee-schedule-snapshot-v1.schema.json)
37. [官方历史数据来源决策 ADR-0016](docs/adr/0016-public-historical-data-provenance.md)
38. [Binance 官方归档 Smoke Evidence v0.16.0](artifacts/market-data/binance-public-data-smoke-v0.16.0.json)
39. [实施追踪 v0.16.0](docs/implementation-status-v0.16.0.md)
40. [Contemporaneous Capture Snapshot Schema](config/contemporaneous-capture-snapshot-v1.schema.json)
41. [同时公开行情捕获决策 ADR-0017](docs/adr/0017-contemporaneous-public-capture.md)
42. [Binance 同时捕获 Smoke Evidence v0.17.0](artifacts/market-data/binance-contemporaneous-smoke-v0.17.0.json)
43. [实施追踪 v0.17.0](docs/implementation-status-v0.17.0.md)
44. [Offline Paper Run Schema](config/offline-paper-run-v1.schema.json)
45. [公开输入离线 Paper 决策 ADR-0018](docs/adr/0018-public-offline-paper-replay.md)
46. [Binance 离线 Paper Smoke Evidence v0.18.0](artifacts/paper/binance-offline-paper-smoke-v0.18.0.json)
47. [实施追踪 v0.18.0](docs/implementation-status-v0.18.0.md)
48. [Paper Schedule Snapshot Schema](config/paper-schedule-snapshot-v1.schema.json)
49. [长期 Paper 调度决策 ADR-0019](docs/adr/0019-durable-longitudinal-paper-scheduler.md)
50. [Binance 调度 Cycle Evidence v0.19.0](artifacts/paper/paper-slot-ethusdt_20260727t120000z.json)
51. [Binance 调度状态 Evidence v0.19.0](artifacts/paper/paper-schedule-ethusdt_20260727t120000z.json)
52. [实施追踪 v0.19.0](docs/implementation-status-v0.19.0.md)
53. [Paper Runtime Snapshot Schema](config/paper-runtime-snapshot-v1.schema.json)
54. [Server Time Probe Schema](config/server-time-probe-v1.schema.json)
55. [时钟健康门决策 ADR-0020](docs/adr/0020-server-time-runtime-health.md)
56. [Binance Runtime Smoke Evidence v0.20.0](artifacts/runtime/v0.20-smoke/)
57. [实施追踪 v0.20.0](docs/implementation-status-v0.20.0.md)
58. [Perpetual Context Snapshot Schema](config/perpetual-context-snapshot-v1.schema.json)
59. [当前永续上下文决策 ADR-0021](docs/adr/0021-current-perpetual-context.md)
60. [Binance Futures 直连失败证据 v0.21.0](artifacts/market-data/binance-perpetual-context-smoke-failure-v0.21.0.json)
61. [实施追踪 v0.21.0](docs/implementation-status-v0.21.0.md)
62. [Account Commission Snapshot Schema](config/account-commission-snapshot-v1.schema.json)
63. [只读账户费率证据决策 ADR-0022](docs/adr/0022-read-only-account-commission-evidence.md)
64. [Binance 账户费率未运行证据 v0.22.0](artifacts/account-cost/binance-account-commission-smoke-not-run-v0.22.0.json)
65. [实施追踪 v0.22.0](docs/implementation-status-v0.22.0.md)
66. [Paper Account Cost Binding Schema](config/paper-account-cost-binding-v1.schema.json)
67. [PIT Paper 账户成本绑定决策 ADR-0023](docs/adr/0023-pit-paper-account-cost-binding.md)
68. [Paper 账户成本绑定未运行证据 v0.23.0](artifacts/paper-cost/binance-paper-account-cost-binding-not-run-v0.23.0.json)
69. [实施追踪 v0.23.0](docs/implementation-status-v0.23.0.md)
70. [Paper Cycle Context Bundle Schema](config/paper-cycle-context-bundle-v1.schema.json)
71. [Paper Context Schedule Schema](config/paper-context-schedule-snapshot-v1.schema.json)
72. [上下文完整 Paper 侧车决策 ADR-0024](docs/adr/0024-context-complete-paper-sidecar.md)
73. [Context-complete Cycle 未运行证据 v0.24.0](artifacts/paper-context/binance-context-complete-cycle-not-run-v0.24.0.json)
74. [实施追踪 v0.24.0](docs/implementation-status-v0.24.0.md)
75. [Context Cycle Orchestration Snapshot Schema](config/context-cycle-orchestration-snapshot-v1.schema.json)
76. [Local Scheduler Contract Schema](config/local-scheduler-contract-v1.schema.json)
77. [可恢复完整周期编排决策 ADR-0025](docs/adr/0025-recoverable-context-cycle-orchestration.md)
78. [完整周期编排未运行证据 v0.25.0](artifacts/orchestration/context-cycle-orchestration-not-run-v0.25.0.json)
79. [实施追踪 v0.25.0](docs/implementation-status-v0.25.0.md)

如果文档之间出现冲突，以《系统计划 v1.1》的产品目标和硬风险约束为最高优先级；运行数据字段以《核心数据契约》为准，各发布对象字段以对应Schema为准；机制解释以《AI 研究与模型治理》和《开发路线与验收门槛》为准；发布数值、比较运算符、必需性和样本不足结果以 `ReleaseGatePolicy` 为准，指标单位/估计器以Metric Catalog为准，条件聚合和证据作用域以《发布评估与证据规范》为准。

机器政策当前是 `DESIGN_BASELINE` 且 `production_activation.enabled=false`。在DataQuality、Split、StatisticalDesign、Accounting、CostAllocation、ForwardControl、Compliance Attestation及Evaluator build hash全部绑定前，任何正式PASS都无效；这是有意的Fail-Closed状态。

当前策略有两条互斥发布路径：

- `BASELINE_ONLY`：简单趋势/突破独立证明扣费后经济价值，AI 指标不适用。
- `AI_ENHANCED`：简单基线先通过，再证明 AI 在相同候选事件、风险和成交条件下提供增量价值。

AI 失败不阻止已经独立通过全部门槛的简单基线；简单基线失败时，AI 不得用来掩盖失败。

## 实施状态

Git中的设计基线已冻结，当前代码版本为 `0.25.0`，正在逐项执行《开发路线与验收门槛》第9节。已完成规范化哈希、Decimal/tick/step基础、版本化InstrumentMetadata、核心决策链、SQLite WAL账本与Outbox、Golden Replay、RiskLock与部署档位风控、订单UNKNOWN对账、PositionExecutor、发布Artifact信任链、可重放经济账本、依赖序列统计、AI相对简单基线的同proposal/time配对增量、删除最大正贡献单元后的完整GROWTH endpoint复评、删除Top-5正贡献完整交易后的路径依赖经济重放、累计Trial Registry上的Holm/双侧区间宽度/ESS/MERE功效重放、AI-vs-baseline与Minor candidate-vs-active的配对最大回撤和ES95改善区间、Binance官方公开历史归档、公开Spot行情的同时只读捕获与修订/缺口证据、从当前公开输入到基线决策/保守模拟成交/双独立经济账本的单周期离线 Paper 闭环、4h槽位与可恢复长期Paper调度、三样本交易所时钟纠偏、当前永续 Mark/Index/Premium/OI/Funding 上下文、当前账户 Spot/USDⓈ-M commission 的只读取证边界、账户费率与Paper经济结果的PIT费用重放绑定、账户成本/永续同槽位的context-complete可恢复侧车，以及共享可信时钟、保留决策前账户证据的可恢复完整周期编排。完整验证都必须显式提供在Artifact之外保存的 trusted attestation hash，self-hash不能自证来源可信。

当前58个Catalog算法中有26个Estimator可执行，其余32个明确Fail-Closed。公开历史归档的结构化请求只能访问ETHUSDT/BTCUSDT的allowlisted数据族；生产transport只执行无凭据GET，必须在解压前通过官方checksum，并将来源、质量和快照绑定到哈希。真实smoke已验证2026-07-25 ETHUSDT Spot daily 4h归档，但全部事后归档固定为`ARCHIVE_REPLAY_ONLY`：URL不是Artifact身份，也不能证明历史决策时点的数据可用性。Fee Schedule因产品、账户层级、折扣和生效期而独立冻结，不能从行情或当前网页费率反填历史。

v0.17固定轮询公开market-data-only端点的1m/4h Kline、AggTrade和BBO，保存原始响应、客户端接收时刻、Kline修订、可观测AggTrade缺口和外部session attestation。BBO没有源事件时间/序列，固定标记为`BBO_SEQUENCE_UNOBSERVABLE_REST_SNAPSHOT`；交易所源时钟领先本机时使用保守clock floor并显式报告。真实两轮smoke重放通过，但持续时间不足、缺永续上下文和账户成本/成交，因此固定为`CONTEMPORANEOUS_RESEARCH_ONLY`/`CAPTURE_REPLAY_ONLY`。

v0.18严格分阶段获取当前4h warmup、公开exchangeInfo、BBO和AggTrade，冻结`SPOT_LONG_SMA20_VOL12_BUCKET25_V1`基线及`OFFLINE_PAPER_CONSERVATIVE_BBO_V1`成交规则，并分别生成BASELINE/AI临时WAL经济账本。真实smoke自然产生LONG和一笔0.0459 ETH模拟成交；立即保守清算权益为999.5506993585 USDT，显式包含双边滑点和双边15bps假设费用。这个负的成本压力值不是24h策略收益，也不证明盈利或亏损。

v0.19把cycle放入固定UTC 4h槽位：close后5分钟到期，15分钟租约，append-only SQLite WAL事件链。精确run bytes先进入不可变PREPARED blob再发布文件，因此崩溃恢复不重新请求不同市场响应。真实smoke保留了第一次`PAPER_CLOCK_INVALID`失败和第二次成功；同槽位再次调用返回`ALREADY_SUCCEEDED`且网络请求为0。missed/expired槽位永久不可回填。

v0.20在每次新周期前固定执行三个Binance public server-time GET，用保守offset interval交集区分aligned、可校正和blocked。真实smoke发现本机约慢2.51秒，使用monotonic anchor安全校正后首次执行为3个时间请求+4个行情请求；同槽位第二次为3+0，bomb行情transport调用为0。每次结果进入独立append-only WAL心跳链，保存gap和告警转换；外部告警投递仍未配置。

v0.21固定五个Binance USDⓈ-M public GET，在健康纠偏时钟之后捕获Mark、Index、Premium、OI和Funding；从原始receipt重建基差、4h OI变化和每1000 USDT SHORT Funding压力场景。只有历史Funding间隔一致时才计算24h场景，且明确不是预测或已实现收益。当前网络对官方Futures host的第一个请求仍失败关闭，因此真实快照尚未进入长期Paper，未使用替代来源。

v0.22固定三个USER_DATA signed GET，先证明API key为只读且IP-restricted，再读取当前ETHUSDT Spot与USDⓈ-M账户费率；任何额外true权限都会在commission请求前阻断。Spot权威成本保守使用standard/special/tax的no-discount总和，BNB折扣仅作非权威情景。由于没有合规credential文件，真实signed smoke按设计未运行，没有用fixture或平台默认费率冒充账户证据。

v0.23把完整Paper run、完整account commission snapshot及两个外部attestation做PIT绑定；只有账户费率在决策前可用并覆盖run end时，才用no-discount taker-buy/sell重算费用和保守清算权益。信号、成交、数量、价格和滑点保持不变。fixture重放显示旧15bps假设更保守，但成本调整后净变化仍为负；这不是实盘账户或盈利证据。

v0.24保留旧Paper scheduler证据不变，以独立append-only WAL侧车冻结同一4h槽位的Paper/account-cost/perpetual bundle。PREPARED或publish后崩溃均从原bytes恢复，source read和network均为0。context schedule只统计侧车SUCCEEDED，旧Paper成功不能继承；首尾间缺槽会破坏连续90天资格。

v0.25把账户费率、Paper、永续、binding和context sidecar固定在一个可恢复编排中。正常路径共享一次三样本probe和一个monotonic clock，物理请求为3+3+4+5=15；账户证据在Paper决策前进入独立不可变WAL，后续失败只复用不重采。新增LaunchAgent renderer只生成mode-0600 plist/合同，不调用`launchctl`，没有安装receipt就不声称已调度。

仓库仍没有真实账户费率响应、成功的真实Futures上下文、真实成交/实际滑点、已安装的操作系统调度或连续90天Paper证据，因此不能声称策略赚钱、AI优于基线或具备PIT-valid OOS证据。AI臂因没有批准模型固定为`NOT_RUN_NO_APPROVED_MODEL`、零成交和统计不合格；没有用启发式信号冒充AI。FeeSchedule因没有外部签名批准器而不支持`PRODUCTION`。当前没有Broker、余额读取或真实下单能力；凭据模块仅允许one-shot只读费率取证。下一步是在仓库外准备owner-only、IP-restricted只读凭据文件，先运行一个真实完整周期，再生成并外部安装LaunchAgent，随后累计至少90天。详细完成度见[实施追踪 v0.25.0](docs/implementation-status-v0.25.0.md)，边界见[ADR-0025](docs/adr/0025-recoverable-context-cycle-orchestration.md)。
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
