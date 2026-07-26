# 开源项目参考与取舍 v1.1

状态：研究参考，不构成依赖批准
复核日期：2026-07-26
上位文档：[系统计划 v1.1](system-plan-v1.1.md)

## 1. 结论

本项目不应成为另一个“带AI按钮的通用交易平台”，也不应直接Fork某个现成机器人。更合理的做法是：

1. 借鉴成熟项目已经验证过的分层、状态机、实验留档和故障处理思想；
2. 保留自己的经济口径、发布门、风险政策和Evidence Scope；
3. 对第三方代码逐项做版本、许可证、接口和故障语义审查；
4. 先证明简单基线赚钱，再让AI证明独立且可重复的增量价值。

我们的潜在优势不是模型更大，而是范围更窄、成本更真实、证据更严格、回退更可控。平台通常擅长快速研究、连接交易所和自动重训；本项目要赢，只能赢在“哪些收益证据可信、何时禁止上线、异常时怎样不扩大损失”。

## 2. 项目逐项参考

### 2.1 Freqtrade / FreqAI

来源：[Freqtrade GitHub](https://github.com/freqtrade/freqtrade)、[FreqAI](https://www.freqtrade.io/en/stable/freqai/)、[Lookahead Analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/)

值得借鉴：

- Dry-run、回测、交易所适配和SQLite持久化形成了低门槛的个人加密交易闭环；
- `lookahead-analysis`、`recursive-analysis` 把常见研究错误变成显式诊断命令；
- FreqAI展示了滚动训练、模型过期、预测保存、异常值处理和崩溃恢复的实用工程路径。

不直接照搬：

- “始终使用最新训练模型”不等于最新模型具有经济资格；本项目将其改成RecipeRelease、Minor ModelBundle、并行Shadow和非劣门；
- 10k级自动特征扩张不适合本项目的小有效样本；V1特征数受ESS约束；
- Freqtrade当前为GPL-3.0；未完成许可证审查前，只借鉴思想和公开接口行为，不复制实现。

对应落地：未来函数/递归稳定性测试、模型年龄门、预测留档、交易所保护单、Paper优先。

### 2.2 NautilusTrader

来源：[NautilusTrader GitHub](https://github.com/nautechsystems/nautilus_trader)、[Binance集成](https://nautilustrader.io/docs/latest/integrations/binance/)、[订单与持仓概念](https://nautilustrader.io/docs/latest/concepts/positions/)

值得借鉴：

- 研究、确定性模拟和实盘共享事件驱动架构；
- 订单、成交、持仓事件及ClientOrderId形成可审计谱系；
- 对账、重连、状态重建和精度类型是一等设计对象。

不直接照搬：

- V1资金和频率不需要一开始承担完整多资产、多venue引擎的复杂度；
- 我们先实现契约独立的单进程Python内核，再用Spike判断是否采用薄Adapter；
- 当前为LGPL-3.0，若链接、修改或分发必须单独复核义务。

对应落地：追加事件账本、UNKNOWN状态、Intent与Attempt分离、确定性重放、Decimal/定点边界和启动对账。

### 2.3 Hummingbot Strategy V2

来源：[Hummingbot GitHub](https://github.com/hummingbot/hummingbot)、[Strategy V2架构](https://hummingbot.org/strategies/v2-strategies/)

值得借鉴：

- Controller负责长期决策，Executor负责有限的订单/仓位任务；
- Executor有明确生命周期，便于局部恢复、停止和故障归因；
- Market Data Provider集中提供行情，减少策略直接依赖Connector。

不直接照搬：

- Hummingbot重点覆盖做市、套利、网格和多venue高频工作流，而这些不属于V1；
- Controller不能绕过本项目的PositionPolicy与RiskGate；
- Apache-2.0较宽松，但仍需登记版本、NOTICE和修改。

对应落地：`StrategyProposal → MetaDecision → TargetPosition → RiskDecision → ExecutionIntent → ChildOrderAttempt`。

### 2.4 Jesse

来源：[Jesse GitHub](https://github.com/jesse-ai/jesse)

值得借鉴：

- 简洁的策略表达、无未来函数回测、多时间框架、部分成交和Paper/Live工作流；
- 特征采集、标签、模型训练、校准和预测的端到端ML体验；
- Monte Carlo与批量比较提醒研究者不要只相信单一路径。

不直接照搬：

- `prediction probability > threshold`不能直接成为实盘订单；
- 自动优化只能在Research区工作，不能接触封存审计；
- MIT许可不消除模型验证、交易所和数据许可风险。

对应落地：简单趋势Proposal、AI Meta过滤、概率校准、配对增量账本和封存Release Audit。

### 2.5 QuantConnect LEAN

来源：[LEAN GitHub](https://github.com/QuantConnect/Lean)

值得借鉴：

- Alpha、Portfolio Construction、Risk Management、Execution的清晰职责边界；
- 事件驱动和可插拔组件让研究逻辑不必直接操作Broker。

不直接照搬：

- 完整LEAN平台对单标的、4H、个人账户V1过重；
- 本项目将Portfolio层压缩为PositionPolicy，但保留“信号不能跳过风险直接执行”的不变量；
- Apache-2.0代码若引入仍需保留归属和许可证文件。

对应落地：Strategy只提议，PositionPolicy唯一生成TargetPosition，RiskGate只能保持或缩小风险。

### 2.6 Microsoft Qlib

来源：[Qlib GitHub](https://github.com/microsoft/qlib)、[Qlib Recorder](https://github.com/microsoft/qlib/blob/main/docs/component/recorder.rst)

值得借鉴：

- ExperimentManager、Experiment、Recorder把参数、指标和产物绑定到单次运行；
- 离线研究与在线模型管理被视为完整工作流，而不是一个Notebook。

不直接照搬：

- 股票截面因子、Top-K组合和默认数据处理不适合ETH单标的；
- 自动因子/模型Agent不得读取Sealed Release Audit；
- Recorder概念会被收紧为不可变ExperimentManifest、RecipeRelease、ModelBundle和签名Evidence。

对应落地：全部Trial登记、失败实验保留、模型谱系、Golden Snapshot和DeploymentLine。

### 2.7 VeighNa / vn.py

来源：[vn.py GitHub](https://github.com/vnpy/vnpy)

值得借鉴：

- Gateway隔离交易所差异；
- App模块化和集中式Risk Manager体现“风险拦截应位于下单必经路径”；
- 数据记录、交易接口和运行服务彼此解耦。

不直接照搬：

- V1不引入完整桌面交易平台、国内期货生态或多进程分布式栈；
- 风控不能只做流控/撤单次数限制，还必须消费真实持仓、活动订单、权益和保护单状态；
- MIT许可代码也必须逐依赖登记。

对应落地：薄ExchangeAdapter、单一Broker能力边界、不可绕过RiskGate和交易规则规范化。

### 2.8 FinRL

来源：[FinRL GitHub](https://github.com/AI4Finance-Foundation/FinRL)

值得借鉴：

- 训练、验证、交易环境分层；
- 将成本、风险和市场环境纳入学习任务，而不是只预测价格；
- 可用作RL研究基准和故障/敏感性实验来源。

不直接照搬：

- RL策略在非平稳市场中具有高样本需求、奖励投机和难以解释的尾部风险；
- V1禁止RL直接控制仓位或订单，只允许长期Shadow Challenger；
- 当前MIT许可不代表训练数据、预训练权重或第三方环境自动可用。

对应落地：V1使用低方差Logistic/XGBoost Meta模型；RL留在P2研究，不进入真钱关键路径。

## 3. 综合后的AI方法论

从这些项目中最值得保留的不是某个模型，而是一条受控闭环：

```text
简单、可解释、成本后有正边际的BaseStrategy
  → point-in-time样本与固定标签
  → Logistic基准
  → XGBoost Meta过滤/离散风险档位
  → 概率校准、OOD与拒绝机制
  → 独立BASELINE_LEDGER和AI_LEDGER
  → 配对经济增量或风险效率门
  → Shadow / Paper / Canary
  → Champion或零新增风险
```

关键判断：

- AI首先应当减少坏交易和不确定时的敞口，而不是预测每根K线；
- 模型指标只能诊断，真正的主终点是全成本经济收益或预注册的风险效率；
- 自动重训只产生Candidate，不自动产生部署资格；
- LLM适合研究助理、文本结构化和事故摘要，不适合直接下单；
- 更复杂模型只有在相同窗口、资本、成本和风险下击败简单基准才有价值。

## 4. Clean-room与依赖准入

本附录记录的是架构观察，不是法律意见，也不是依赖批准。任何代码进入仓库前必须：

1. 锁定仓库、commit/tag和许可证hash；
2. 记录复制、修改、链接、分发和NOTICE义务；
3. 证明没有把第三方策略默认值当成本项目Alpha；
4. 通过本项目契约、风险、确定性重放和故障测试；
5. 对GPL/LGPL或许可证不清楚的实现，默认不复制，先做独立实现或法律复核。

许可证和项目功能会变化，正式依赖决策必须在引入当天重新核验，不能只依赖本附录日期。
