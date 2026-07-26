# 开发路线与验收门槛 v1.1

状态：设计基线
日期：2026-07-26
上位文档：[系统计划 v1.1](system-plan-v1.1.md)
机器判定：[ReleaseGatePolicy v1.1](../config/release-gates-v1.1.json)
评估语义：[发布评估与证据规范 v1.1](release-evaluation-spec-v1.1.md)

## 1. 路线原则

本项目按“先证明可信，再证明赚钱，最后放大资金”的顺序推进：

```text
可信数据
  → 可重放决策
  → 保守执行模型
  → 简单基线有经济证据
  → AI有增量证据
  → 真实运行可靠
  → 极小资金Canary
  → 逐级扩大批准风险
```

任何高收益结果都不能抵消以下问题：

- 未来函数；
- 无法重现；
- 无法对账；
- 订单状态不明后盲目重发；
- 硬风险被绕过；
- 真实成本不成立；
- 封存审计集被污染。

## 2. 优先级

### P0：有资格谈收益

- 核心契约与不可绕过风险层；
- Point-in-time数据；
- 单一特征实现；
- 确定性回测和1m明细重放；
- 追加事件账本；
- 简单趋势基线；
- ExperimentManifest；
- 简单基线的一次性封存审计；
- `AI_ENHANCED` 路径才需要AI Candidate及其配对增量审计；
- 订单状态机和Binance故障测试。

P0完成前不使用真实资金。

### P1：有资格管理极小真钱

- 实时Shadow；
- PredictionEligibility；
- Model Registry与Last-Known-Good；
- 90天Paper；
- 告警、事故分级和Runbook；
- 25/50/75% Canary；
- 实际成本、成交和对账报告。

### P2：受控扩展

- 趋势顺向Pullback Challenger；
- Mean Reversion继续Shadow；
- TabPFN/Chronos等基础模型Shadow；
- 新闻/社媒/LLM结构化Shadow；
- Gate Adapter；
- 账户规模允许后再评估BTC真钱；
- 多策略组合与更复杂执行。

P2不能与P0/P1抢占关键可靠性工作。

## 3. 阶段路线

时间估计假设：一名开发者、已有Python/数据分析基础、非全职或半全职推进。时间是计划区间，不是交付承诺。

### 阶段0：项目治理与安全基线

预计：1周。

交付物：

- 六份v1.1权威文档（含开源参考附录），以及ReleaseGatePolicy、Metric Catalog、GateEvidence Schema、Policy/Metric Schema和RecipeRelease/ModelBundle/Approved Fallback Registry三份对象Schema；
- 确定性Release Evaluator骨架与Fail-Closed测试；
- 决策记录ADR模板；
- 依赖与许可证清单；
- 密钥、环境和账户隔离政策；
- 账户持有人所在地、交易所条款、税务记录和衍生品适格性检查清单；
- 风险政策机器可读版本；
- 测试目录和CI骨架；
- 事故等级与停机Runbook草案。

验收：

- 任何模块都无法通过依赖注入绕过RiskGate直接取得Broker；
- API密钥不进入仓库，实盘密钥禁止提现并与Testnet隔离；
- 所有硬风险参数有唯一权威来源；
- 关键决策变更必须产生版本和ADR。
- 所有Policy metric在Catalog中唯一解析，未知metric/estimator、缺少policy binding或条件字段时一律Fail-Closed；
- 相同Evidence重复100次得到相同Gate结果与业务hash。

No-Go：

- 账户权限无法限制；
- 合法访问、账户条款或衍生品资格无法确认；
- 风险参数可被策略或模型热改；
- 许可证来源不清。

### 阶段1：Point-in-time数据基础

预计：2–3周。

交付物：

- Binance OHLCV、Mark/Index/Premium、Funding、OI、Taker数据采集；
- InstrumentMetadata和费用版本；
- `event_time/available_at/ingested_at/recorded_at`；
- Raw Parquet和数据快照哈希；
- 4H闭合Bar Builder；
- 数据新鲜度、缺失、重复、跳变和时间同步检查；
- BTC上下文数据，只用于特征/Paper。

验收：

- 相同原始快照重复构建结果哈希一致；
- 未闭合4H K线不会进入决策；
- 所有正式字段拥有可用时间；
- 重复、迟到和乱序数据处理可重放；
- 数据缺失/过期时产生风险锁；
- InstrumentMetadata历史版本可恢复。

No-Go：

- 只有事件时间，没有真实可用时间；
- 数据修订会静默改变历史；
- 无法判断K线是否完整闭合。

### 阶段2：确定性研究引擎与简单基线

预计：3–4周。

交付物：

- 回测/Paper/Live共享的Decision Kernel；
- 简单趋势/突破基线；
- 12%目标波动和0/25/50/75/100风险档位；
- 8H最短持有、24H视野、滞回和no-trade band；
- 费用、Funding、Spread、Slippage、延迟、拒单和部分成交模型；
- 4H决策 + 1m/BBO关键区间明细重放；
- Prefix-vs-full、Warm-up递归检查；
- Freqtrade独立基线逐决策对照；
- 18个月训练/形成期、8个季度OOS折和最后12个月封存区配置。

验收：

- 相同事件流运行100次，决策和目标哈希一致；
- 回测与实时特征逐字段一致；
- 4H信号不在同一根4H收盘价成交；
- Freqtrade差异逐条有可解释原因；
- 所有成本能独立审计；
- LONG/SHORT报告完全分开。

简单基线初始经济门：

- 通过预注册功效与置信区间宽度门；
- 变量交易成本后净对数增长的一侧95%Moving-block Bootstrap下界大于0；
- 至少6/8个OOS季度成本后收益不为负；
- 正常成本下最大回撤低于10%；
- 1.5倍费用和滑点下仍保持非负；
- 2倍成本与不利Funding压力下最大回撤低于15%；
- 删除最大正收益季度后、以及删除盈利最大5笔交易后，变量成本后净对数增长的一侧95%下界都仍大于0；
- 单折、单笔和前5笔贡献占比作为诊断报告；
- `final_feature_count <= min(50, floor(effective_event_count/20))`；
- 每方向 `effective_event_count < 200` 时只允许NO_AI或低维Logistic研究，不允许XGBoost/Quantile成为硬组件；
- 按批准全风险规模计算的月度固定运营成本后economic PnL一侧95%下界大于0。

No-Go：

- 简单基线失败时，不用复杂AI掩盖；
- 保持空仓，修改经济假设或等待新数据。

### 阶段3：执行内核与Binance安全验证

预计：3–4周。

交付物：

- SQLite WAL追加账本、投影和Outbox；
- ExecutionIntent、PositionExecutor和Order状态机；
- Binance Spot/USDT永续Adapter；
- client order ID幂等；
- Fill去重；
- 启动、周期、重连和UNKNOWN专项对账；
- 固定点金额和交易所filter处理；
- 永续reduce-only灾难止损和现货ProtectiveOrder/Watchdog；
- Testnet和故障注入套件。

必须测试：

- HTTP提交前后超时；
- ACK丢失；
- Fill先于ACK；
- 部分成交后断线；
- Cancel状态未知；
- Cancel与Fill竞态；
- WS重复、乱序和sequence gap；
- 进程在每个外部副作用边界崩溃；
- 本地有订单但交易所无；
- 交易所有订单但本地无；
- 手工仓位；
- Funding、手续费和InstrumentMetadata变化；
- 反向信号必须先平旧仓、确认归零、再开新仓。
- Target覆盖仍有活动ChildOrderAttempt的旧Target；
- 伪造Canary multiplier不能突破RiskGate的Deployment Registry上限；
- 模型失效的FREEZE_INCREASES不能被误解释为FLATTEN。
- 25风险bucket按0.25参与计算，CANARY_25再乘0.25，不能出现百分数单位放大；
- 现货与永续反向仓位及全部风险增加型活动订单按最坏毛敞口计算，不能净额绕过1x；
- ProtectiveOrder完整追溯到RiskDecision/Intent/Attempt；现货数量被锁定时按amend、风险锁和Watchdog流程安全换单。

验收：

- 0次重复经济订单；
- 0次丢失成交；
- 0次风险放大；
- 不确定请求100%进入UNKNOWN；
- UNKNOWN不会换新ID盲目重发；
- 重启后能达到唯一明确状态，或保持安全锁定；
- 对账不一致时0次新增风险；
- Spot不做空，永续始终单向、逐仓、≤1x。

可选技术Spike：

- 使用NautilusTrader Binance USDM验证上述场景；
- 如果能够满足接口和故障门，可采用其Adapter；
- 如果不能，保留同一领域契约并实现薄Adapter；
- 业务层不得绑定Nautilus专有类型，以免Gate阶段无法替换。

### 阶段4：可选AI Candidate与Release Audit

预计：3–5周。

本阶段只适用于 `AI_ENHANCED`。选择 `BASELINE_ONLY` 时不为了形式完整而训练AI；确定性 `NO_AI_BASE` 仍须生成完整MetaDecision，并直接进入后续Shadow/Paper/Canary。简单基线无论选择哪条路线，都必须先完成自己的Release Audit。

交付物：

- Event-based Meta样本；
- Logistic Regression基准；
- XGBoost LONG/SHORT独立模型；
- 概率校准；
- 样本门允许时的q10/q50/q90净收益模型；否则形成INCONCLUSIVE记录并从硬仓位路径移除；
- PredictionEligibility和OOD；
- ExperimentManifest、ModelBundle、ModelCard；
- Model Registry与DeploymentTimeline；
- DSR/PBO、Moving-block Bootstrap和成本压力报告；
- 冻结配方后的一次性12个月Release Audit。

Candidate硬门：

- Lookahead、PIT、递归、切分和parity检查无严重错误；
- 完整记录全部Trial和失败；
- Purge/Embargo不短于最大标签/执行影响区间；
- 相同数据、代码和随机种子可重现；
- 模型包Golden Snapshot推理哈希一致；
- 许可证、特征schema和数据谱系完整。

Candidate经济门：

- 先通过简单基线经济门；
- 通过预注册样本功效、有效样本和CI宽度门；
- 预先选择 `GROWTH` 或 `RISK_EFFICIENCY` 主终点；
- AI臂自身变量成本净对数增长的一侧95%下界大于0，且批准全风险资本下、计入AI增量固定成本后的月度economic PnL一侧95%下界大于0；
- GROWTH路线：配对 `ΔAI` economic净对数增长的一侧95%Block Bootstrap下界大于0；
- RISK_EFFICIENCY路线：增量下界不低于 `-10%×abs(base_net_log_growth)`，且最大回撤与ES95改善的一侧95%配对Block Bootstrap下界均至少20%；
- 至少6/8 OOS季度绝对收益非负；
- 至少6/8 OOS季度不劣于简单基线；
- 删除最大正增量季度后，所选AI主终点仍完整通过；
- DSR置信概率≥95%；
- PBO≤20%；
- 正常成本最大回撤低于10%；
- 1.5倍成本下绝对净收益和ΔAI均不为负；
- 2倍成本压力下最大回撤低于15%；
- 模型Brier严格优于常数概率；XGBoost还必须在Brier上优于Logistic，GROWTH时增量LCB高于Logistic，RISK_EFFICIENCY时对Logistic形成预声明Pareto支配，否则只产生新的Logistic/NO_AI Candidate，不自动回退上线；
- ECE≤0.05并报告置信区间；
- `final_feature_count <= min(50, floor(effective_event_count/20))`，每方向effective_event_count至少200；
- AI增量样本只计AI实际改变基线动作/仓位的配对时点；
- Initial使用最后12个月一次性审计；Major使用结果揭晓前已提交hash的prequential Forward Evidence。首次结果揭晓前，设计、统计、数据、代码/环境、Accounting、CostAllocation、风险、执行、Forward Control、资本网格/资本搜索计划、`approved_production_capital_usdt`、`actual_deployable_capital_usdt`、`break_even_capital_lcb_root_usdt` 和Evaluator build必须全部冻结并有内容hash/freeze proof。二者均按Release Audit矩阵通过绝对收益、配对CI、实际功效、CI宽度和leave-out门；`AI_ENHANCED`还必须在同窗分别让 `BASELINE_LEDGER` 的 `AUDIT_BASE_ARM` 与 `AI_LEDGER` 的 `AUDIT_AI_ARM` 通过后，再依次运行 `AUDIT_AI_PAIRED_COMMON` 与所选 `AUDIT_AI_ENDPOINT.*` paired delta，不能仅凭点估计或单一账本通过。

所有阈值、比较运算符及REQUIRED/ADVISORY属性由ReleaseGatePolicy决定；指标单位/估计器和Evidence Scope分别由Metric Catalog与《发布评估与证据规范》决定。未来只能在打开新的封存窗口前前瞻修订，不能根据已看到的审计结果倒改。

No-Go：

- AI失败但简单基线通过：只有Approved Fallback Registry中存在仍有效、已发布且已批准的BASELINE_ONLY DeploymentLine Champion/Last-Known-Good记录时才回退，否则禁止新增风险；
- 两者都失败：保持空仓；
- 审计失败：该审计区永久标记已暴露，不能反复调参后重考。

### 阶段5：Forward Shadow

最低：7个完整自然日，且至少12个已完成的24H预测周期；样本不足则延长。

验收：

- 实时/离线特征和决策哈希一致；
- 0个schema、顺序、NaN或模型包错误；
- 每个预测可还原到Manifest；
- 延迟不影响下一可交易时点；
- 预测、拒绝原因和风险档位100%留档；
- 与Last-Known-Good逐事件比较；
- Shadow没有交易API权限。
- 以模拟Broker和故障注入通过当前Shadow scope的RUNTIME门；该PASS不能继承到Paper。

`BASELINE_ONLY` 对 `NO_AI_BASE` 决策链做同样的Shadow；只有 `AI_ENHANCED` 才要求模型包、预测与AI拒绝原因检查。7天只证明运行兼容性，不证明赚钱。

### 阶段6：系统Paper

最低：90个自然日。样本数按预注册运行/成本CI门判断；10笔或30个预测只能证明流程被触发，不能证明收益或P95成本。

系统门：

- 0次重复订单；
- 0次未记录成交；
- 0次硬风险、杠杆、逐仓或方向模式违规；
- 0次对账不一致时新增风险；
- 100%订单可追溯；
- 重启和断线均恢复到明确状态，或安全锁定；
- 决策重放一致率100%；
- 未解释TargetPosition差异为0。

前向一致性门：

- Paper变量成本后PnL位于预声明的OOS预测区间，未穿越伤害边界；`AI_ENHANCED` 还要求配对ΔAI未穿越其伤害边界；
- 最大回撤低于10%；
- 成交成本分布的预注册置信上界不超过离线压力预算；
- `AI_ENHANCED`才评估概率校准；只有Quantile影响硬仓位时才要求分位数覆盖率按固定窗口与置信区间合格，其他路径标记NOT_APPLICABLE；
- 批准全风险规模的月度固定成本后economic PnL一侧95%下界仍大于0。

期间禁止：

- 因短期PnL热改阈值；
- 跳过剩余观察时间；
- 用事后新模型替换历史Paper预测。

### 阶段7：真钱Canary

`25/50/75%` 指获批生产风险预算的权威Deployment Stage，不是账户余额比例。RiskGate独立读取该值，并将0.25/0.50/0.75乘在模型/基线建议敞口上；仍受12%目标波动、模型风险档位、1x杠杆和ETH单标的限制。

每一级：

- 只在预注册的30天区块末评估；
- 若成本/运行样本不足，进入下一个固定30天区块，最多3个区块；
- 90天后仍证据不足，退回Paper或Last-Good；
- route、direction、venue、stage和区块拥有独立Evidence Scope；上一阶段证据不能复制到下一阶段；
- 只能按25→50→75顺序前进，不能自动跳级；

升级门：

- 最大回撤低于10%；
- 未触发2%日损停止；
- 变量成本、成交率和Implementation Shortfall的预注册置信区间没有穿越伤害边界；
- `AI_ENHANCED` 才要求Live AI与同步Shadow基线分别报告“共同模拟成交下的策略增量”和“Live相对模拟的Execution Variance”；`BASELINE_ONLY`标记为NOT_APPLICABLE；
- `AI_ENHANCED`的校准未穿越控制带；Quantile影响硬仓位时，其覆盖率也未穿越控制带；
- 订单、成交、持仓、余额和本地账本完全对账；
- 当前30天区块内0个S0/S1事故；一旦发生，该区块立即失败，完成事故处理后必须从新的完整30天区块重新观察；
- 实际PnL路径未跌破预声明伤害边界；
- 当前账户在该stage multiplier和常见model bucket下具有足够min-notional可成交率；不足时不允许向上取整。
- 当前Canary stage重新通过同route、direction和venue scope的RUNTIME门；上一stage的RUNTIME证据不得复用。

Canary不是用10笔交易重新证明Alpha。固定成本可以作为预先批准的验证支出；扩大到正式全风险前，仍必须证明在实际成本更新后的full-risk月度economic PnL一侧95%下界为正。

失败动作：

- 立即锁定新增风险；
- 确定性管理现有仓位；
- 只使用Approved Fallback Registry中从当前source DeploymentLine显式映射、且方向、venue、stage和有效期均匹配的已发布DeploymentLine Champion/Last-Known-Good；简单基线也必须拥有独立批准记录；
- 没有合格回退对象时禁止新增风险；硬风险要求退出时归零；
- 形成事故或模型退役记录。

### 阶段8：Champion与受控扩展

成为Champion后仍不代表永久有效：

- Initial/Major RecipeRelease走完整Paper/Canary；同配方月度从零训练Minor ModelBundle；
- Minor Bundle必须在同窗、同批准资本和同policy bundle下重跑 `BASELINE_OFFLINE`，再经AI滚动OOS、Golden Snapshot和7天并行Shadow非劣检查后，才可在当前DeploymentLine内替换；
- `RISK_EFFICIENCY` Minor还必须保持相对活动Bundle的收益、最大回撤改善和ES95改善三维Pareto非劣，否则保留未过期Champion；
- 兼容Minor替换不重置Paper/Canary日历，但保留完整Bundle谱系；
- 新模型只需“训练完成”不得上线；
- Champion未过期且新模型没有明确改善时，默认不替换；
- route、主终点、基础Proposal、schema、标签、模型族/搜索、校准/阈值、Position/RiskPolicy、执行/Fill、数据源或Accounting/成本变化都属于Major，创建新DeploymentLine并重新走完整Audit、Paper与Canary；
- 长短方向独立退役。

P2功能只能在Champion稳定后逐项进入完整研究流程。

## 4. 模型和系统降级规则

### 4.1 立即禁止新增风险

- 数据过期或4H K线不完整；
- Feature schema/order/hash不匹配；
- 推理出现NaN/Inf/越界；
- 模型包哈希不匹配；
- 发现未来函数或审计污染；
- OOD超过硬阈值；
- 模型超过硬过期时间；
- 本地与交易所仓位无法解释；
- 订单UNKNOWN未解析；
- 交易所灾难止损缺失；
- 日损达到2%；
- 回撤达到10%警戒线；
- 重复下单或盲目重发；
- REST/WS连接状态不足以安全交易。

### 4.2 模型年龄

默认月度训练：

- 超过45天：预警，最大AI风险档位降一档；
- 超过90天：禁止该模型新增风险；
- schema、来源、费用或标签定义变化：立即失效。

### 4.3 运行退化

- 滚动30个决策中OOD拒绝率>30%：降一档并诊断；
- OOD拒绝率>50%：禁止新增风险；
- 连续20笔真实成交成本>模型假设1.5倍：禁止新增风险并重估成本；
- 至少30笔AI影响交易后，增量期望为负：降档或回退，按预声明控制带执行；
- 回撤≥12%：执行减半；
- 回撤≥15%：有序归零并停机；
- 回撤≥20%：重大事故，禁止自动重启。

低频样本不足时不使用短期点估计强行回退；但任何安全、数据或对账错误不等待样本。

## 5. 事故等级

| 等级 | 示例 | 自动动作 |
|---|---|---|
| S0 Critical | 未授权交易、提现权限暴露、硬风险越权、重复经济订单造成敞口 | 全局锁定、停止自动交易、人工接管 |
| S1 High | UNKNOWN盲重发、持仓无法对账、灾难止损缺失、账本损坏 | 禁止新增风险、必要时有序降至零 |
| S2 Medium | 数据/模型过期、OOD飙升、成本显著偏离、私有流降级 | 禁止或降低新增风险、专项诊断 |
| S3 Low | 非关键报表、UI、延迟告警 | 保持交易，安排修复 |

S0/S1必须形成包含时间线、影响、根因、补偿事件和防复发测试的事故报告。

## 6. 运营成本与最小经济账户

小资金阶段固定成本可能比手续费更致命。

权威定义通过逐资本重放求根：

```text
break_even_capital
  = inf { C :
      monthly_economic_pnl_lcb(
        capital=C,
        min_notional,
        discrete_buckets,
        fee_tiers,
        rejected_opportunities,
        approved_route_and_cost_policy) > 0 }
```

若在批准资本搜索区间内没有正根，则不存在已证明的有限Break-even Capital。每个资本点必须重新执行min-notional、离散bucket、费率阶梯、成交容量和NO_TRADE逻辑，不能只把同一收益率线性缩放。

只有在收益率、费用和可成交机会对资本近似线性时，才允许用以下诊断近似，不作为放行真值：

```text
linear_break_even_approximation
  = monthly_fixed_operating_cost
    / variable_cost_net_monthly_return_rate_lcb
```

例：固定成本10 USDT/月、线性近似下保守收益率为1%，100%批准风险规模约1,000 USDT才刚覆盖固定成本；25% Canary若承担全部固定成本，近似约4,000 USDT。真实结论仍以逐资本重放为准，因此小额Canary被定义为验证支出，而不是盈利证明。

可成交资本下界：

```text
minimum_tradable_capital
  = min_notional
    / (base_vol_exposure
       × (model_bucket / 100)
       × authoritative_stage_multiplier)
```

`model_bucket` 的存储单位是整数百分数 `0/25/50/75/100`。若分母为0或账户低于该值，结果是NO_TRADE，不能通过向上取整绕过。

V1约束：

- 正式阶段不购买付费另类数据；
- 文本AI保持Shadow并设置调用预算；
- 优先本地计算、开源数据和低成本基础设施；
- VPS、数据、告警和推理成本全部进入economic PnL；
- 若账户低于Break-even Capital，不得宣称项目经济盈利；
- 每个Canary阶段报告min-notional后的可成交机会率和阶段化Break-even Capital；
- OperatingCost、AIInferenceCost、ModelTrainingCost、MonitoringAndAuditCost和ExternalCashFlow全部作为账本事件记录；
- 研发时间单独记录，但不把研发时间成本混入策略交易边际判断。

## 7. 总体时间预期

在没有返工和数据问题的理想情况下：

- 工程与离线研究：约10–16周；
- Shadow：至少1周；
- Paper：至少90天；
- Canary：至少90天；

因此从空仓库到完整Champion，现实最低约8–10个月。任何阶段证据不足、样本不足或发生事故，都应延长，而不是压缩。

## 8. 最终Go/No-Go清单

两条路径共同必答项；扩大真钱风险前必须全部回答“是”：

- 数据具有真实Point-in-time语义吗？
- 特征在训练、回测、Paper和Live完全同源吗？
- 相同事件可以确定性重放吗？
- 简单基线本身全成本后赚钱吗？
- 收益跨多数OOS季度稳定吗？
- 1.5倍成本下仍成立、2倍成本下不越过15%回撤吗？
- 准备上线的每个方向是否分别通过，未通过方向是否保持禁用？
- 初始配方的封存审计是否只打开一次，后续Major是否只使用预先保存的前向审计证据？
- 订单UNKNOWN、部分成交和重启对账通过了吗？
- 风险层不可被模型绕过吗？
- 90天Paper通过了吗？
- 当前Canary级别是否完成固定评估区块并通过运行、成本与安全门？
- 真实成本、仓位和模拟假设一致吗？
- 批准全风险规模的月度固定运营成本后economic PnL一侧95%下界为正吗？
- 进入真钱stage的 `actual_deployable_capital_usdt` 是否同时不低于当前Evidence Scope的 `approved_production_capital_usdt` 和 `break_even_capital_lcb_root_usdt`，且风险规模未因额外资本自动放大？
- 当前不存在未解决S0/S1事故吗？

路径专属必答项：

- `BASELINE_ONLY`：当前生产决策是否全部来自已批准、可重放的 `NO_AI_BASE`，且没有未经批准的模型影响仓位？
- `AI_ENHANCED/GROWTH`：AI配对增量economic净对数增长的一侧95%Block Bootstrap下界是否大于0？
- `AI_ENHANCED/RISK_EFFICIENCY`：AI是否同时满足预注册的收益非劣界，以及最大回撤和ES95各改善至少20%？

只回答所选路径对应的问题；`BASELINE_ONLY` 的AI指标标记为 `NOT_APPLICABLE`，不得误判为失败。

任何一项为“否”，保持当前阶段或退回，不扩大资金。

## 9. 紧接着执行的第一个迭代

第一个迭代只建立可信骨架，不训练AI：

1. 建立Python包、测试和CI骨架。
2. 实现通用事件信封，以及MetaDecision动作、Target序列和PortfolioRiskSnapshot等核心契约schema。
3. 实现Decimal/tick/step值对象。
4. 建立SQLite WAL事件表、Outbox、OperatingCost/ExternalCashFlow事件和最小投影。
5. 编写RiskLock、Deployment Stage权威上限与10/12/15/20%回撤状态测试。
6. 定义Target supersession、稳定Intent和ChildOrderAttempt的状态测试。
7. 定义Binance InstrumentMetadata输入样例和舍入性质测试。
8. 实现事件重放的Golden Test。
9. 建立ADR、ExperimentManifest、DataQualityPolicy、SplitPolicy、StatisticalDesignPolicy、AccountingPolicy、CostAllocationPolicy、ForwardControlPolicy和事故报告模板。
10. 实现Release Policy/Metric/Evidence Schema校验与最小确定性Evaluator。

迭代验收：

- 还没有Broker下单能力；
- 所有核心对象都可序列化、哈希和重放；
- 风险只能缩小目标；
- 重复事件不会改变经济状态；
- CI自动执行契约、精度、状态机和重放测试。
- Release Evaluator在任一必需policy未绑定时只能返回FAIL，不能生成生产PASS。

通过后才进入真实数据采集。
