# AI 研究与模型治理 v1.1

状态：设计基线
日期：2026-07-26
上位文档：[系统计划 v1.1](system-plan-v1.1.md)
机器判定：[ReleaseGatePolicy v1.1](../config/release-gates-v1.1.json)
评估语义：[发布评估与证据规范 v1.1](release-evaluation-spec-v1.1.md)

## 1. AI 的职责边界

V1 的 AI 不是交易员，而是规则策略的成本感知 Meta-filter。

AI 可以：

- 判断一个已有的多头或空头 Proposal 是否值得执行；
- 预测扣除成本后的正收益概率；
- 预测未来24H净收益的分位数；
- 判断数据、模型和市场状态是否超出可信范围；
- 建议 0/25/50/75/100% 中的最大风险档位；
- 在不确定性升高时拒绝或缩小风险。

AI 不可以：

- 在规则策略没有提出方向时凭空创造方向；
- 直接调用 Broker 或交易所 API；
- 提高最大杠杆、回撤、日损或仓位限制；
- 自动部署自己刚训练出的模型；
- 读取交易密钥；
- 访问或反复试探封存审计集；
- 通过自然语言置信度直接决定仓位。

如果 AI 不可用：

- 若简单基线已经独立通过完整Champion验收且存在未过期的Approved Fallback Registry记录，可以退回该记录允许的风险档位；
- 否则输出 `FREEZE_INCREASES`；空仓保持空仓，已有仓位保持或减仓；
- 不得因模型错误而无序平仓，现有仓位由确定性风险和退出策略管理。

正式放行分为：

- `BASELINE_ONLY`：确定性 `NO_AI_BASE` MetaDecision，AI经济指标不适用；
- `AI_ENHANCED`：基础策略通过后，AI再通过预声明的配对增量门。

## 2. 研究问题

AI研究只回答预先选择的一类主要经济问题：

- `GROWTH`：在完全相同的基础趋势/突破Proposal、资本、成交模型和风险政策下，AI是否能提高扣除变量成本及AI增量运营成本后的复合收益？
- `RISK_EFFICIENCY`：在收益满足预注册非劣界且AI自身全成本盈利的前提下，AI是否能可靠降低最大回撤和ES95？

默认主终点为已计入AI增量成本的配对economic净对数增长。若某个假设要走“收益非劣、风险更低”路线，必须在实验前选择该路线并使用 `ReleaseGatePolicy` 中固定的收益非劣界和风险改善比例；不能看到结果后切换成功定义。

禁止用以下替代指标宣称成功：

- 分类准确率；
- F1；
- AUC；
- 训练损失；
- 零手续费收益；
- 单一回测区间的 Sharpe；
- 未计入全部试验次数的最佳模型结果。

这些指标只能用于诊断。最终判断以成本后经济结果和风险结果为准。

## 3. 研究数据区与权限隔离

### 3.1 数据区

| 区域 | 用途 | 谁可以访问 | 是否允许反馈调参 |
|---|---|---|---|
| Development | 初始训练、特征开发、单元测试 | 研究者、Agent | 允许 |
| Research Walk-forward | 8个季度OOS折、模型选择 | 研究者、受控Agent | 允许，但全部试验计数 |
| Sealed Release Audit | 最后12个月一次性发布审计 | 只读Release Runner | 不允许 |
| Forward Shadow/Paper | 发布后真实前向观测 | 运行系统 | 只能形成下一代研究，不可改写历史 |
| Canary/Live | 小资金现实验证 | 生产系统 | 不允许在线探索 |

### 3.2 封存集规则

1. Agent、自动特征搜索和超参数搜索在权限层面看不到 Sealed Release Audit。
2. 首次审计结果揭晓前冻结代码/环境、全部设计与数据schema、标签、模型、风险与执行、Accounting、CostAllocation、资本网格/资本搜索计划、批准/实际/Break-even资本、晋级政策及Evaluator build的内容hash；冻结证明写入RecipeRelease、ModelBundle和GateEvidence的 `frozen_release_inputs`/`artifact_hashes`，结果揭晓后不得追认或替换。
3. 审计只运行一次并保存完整输出。
4. 如果看到审计结果后修改任何经济逻辑，该12个月数据立即降级为已使用研究数据，不能再称为封存证据。
5. 该历史封存集只认证初始冻结RecipeRelease；同配方Minor重训不重复打开它。
6. 新Major RecipeRelease必须在配方冻结后生成真实前向、结果揭晓前已保存的预测，形成新的prequential审计证据，不能反复刷同一最后12个月。
7. Release Runner默认只返回 PASS/FAIL 和预先定义的审计报告，不给Agent开放交互式查询。

## 4. 假设和试验预算

- 每季度最多 12 个经济假设。
- 失败假设也占预算。
- 同一想法改变方向、标签、特征集合、交易阈值、持有时间或退出逻辑，视为新经济变体。
- 每个假设必须预先声明最大模型数、特征集合数、随机种子数和超参数试验数。
- 所有 Trial 都计入 DSR/PBO 和多重试验记录，不能只记录最佳结果。
- Trial family跨季度持续累计；改名、拆分LONG/SHORT、替换模型族、仓位映射或重新设种子不能清零历史试验数。
- 同时送入任何Release Audit的方向、模型、阈值和终点属于同一审计家族，必须使用预声明的多重检验调整。
- Agent的代码重试如果改变经济输出，也必须登记为Trial。
- 纯修复确定性Bug、且修复前结果全部作废时，可以不视为新经济假设，但必须保留事故和修复记录。

终止规则：

- 简单基线没有成本后证据时，停止增加 AI 复杂度。
- 连续两个研究周期都没有产生稳定的增量价值时，暂停该假设家族，不能靠扩大搜索空间继续刷结果。
- 达到季度预算后，进入复盘或等待新前向数据。

## 5. 样本与标签

### 5.1 样本单位

Meta模型只在基础策略产生有效 Proposal 的时点创建样本，而不是把每根K线都当作独立交易机会。

多头与空头：

- 可以共享部分市场状态特征；
- 标签、样本、校准、评估和晋级必须分别报告；
- 任一方向失败，不影响另一方向独立晋级；
- 未通过的方向在空仓时输出零风险；已有仓位时输出 `FREEZE_INCREASES`，是否退出由同一PositionPolicy和RiskGate决定。

### 5.2 标签

主分类标签：

```text
y_take = 1 if realized_net_return_24h > 0 else 0
```

连续标签：

```text
realized_net_return_24h
  = (side_sign × (exit_fill_price - entry_fill_price)
     × filled_quantity × contract_multiplier
     - exchange_fees
     + signed_funding_cashflow)
    / label_reference_notional_usdt
```

`signed_funding_cashflow > 0`表示收到资金费，`< 0`表示支付。成交价已经包含Spread和Slippage；二者只通过相对决策参考价的Implementation Shortfall报告，不得重复从标签扣除。

`label_reference_notional_usdt` 由冻结LabelPolicy按同一基础Proposal的全风险参考名义金额产生，对所有AI Candidate相同，不能由AI接受/拒绝或bucket反向改变标签分母。组合经济收益另按GateEvidence中冻结的 `approved_production_capital_usdt` 计算。

标签生成必须使用与正式回测相同的执行规则：

- 4H收盘后才产生信号；
- 从下一条可交易的1m/BBO事件开始模拟；
- 包含最短持有、滞回、止损/退出和24H垂直边界；
- 同一K线内同时触及止盈止损时采用保守路径；
- 交易所规格和费用使用当时版本；
- 无法合理模拟成交的样本标记原因，不得默认有利成交。

可以预先声明正收益门槛高于0，用于覆盖模型误差安全垫；门槛一旦进入封存审计不得事后修改。

### 5.3 重叠标签

24H标签跨越6根4H K线，必须：

- 在训练/验证边界 Purge 掉结果跨界的样本；
- 使用不短于最大标签/执行尾部的 Embargo；
- 计算有效样本数时考虑事件重叠和自相关；
- 不使用随机shuffle切分。

统一指标名为 `effective_event_count`。它在每个route、direction和主终点的时间排序贡献序列上，用 `GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1` 估计：

```text
tau = max(1, 1 + 2 × sum(initial_positive_sequence_of_autocorrelations))
effective_event_count = floor(raw_eligible_event_count / tau)
```

AI增量先限制为AI实际改变基线动作/敞口的配对时点，再计算同一ESS。零方差、无法稳定估计自相关或区块数不足时结果为INCONCLUSIVE。Block Bootstrap的区块长度、最小区块数和随机种子由SplitPolicy冻结。

有效样本门检查实际达成值，而不只检查“写过计划”：

- 对预声明的最小经济相关效应，achieved power至少80%；
- 实际置信区间宽度不超过StatisticalDesignPolicy中事前冻结的上限；
- 没有StatisticalDesignPolicy、算法版本或实际证据时直接FAIL/INCONCLUSIVE。

初始复杂度约束：

```text
final_feature_count <= min(50, floor(effective_event_count / 20))
```

- 每个拟获批方向的 `effective_event_count` 少于200时，只允许NO_AI或低维Logistic研究；
- q10/q90、XGBoost和校准是否可晋级取决于覆盖率置信区间和功效门，不能因为名义样本达到50就通过；
- AI增量的有效样本只计AI实际改变基线仓位/动作的配对时点；
- 样本不足一律标记 `INCONCLUSIVE`，延长Forward观察或降低模型复杂度。

### 5.4 SplitPolicy

每个RecipeRelease冻结一份不可变SplitPolicy：

- 8个季度OOS折的绝对UTC起止时间；
- 每折紧邻其前的18个月滚动训练窗；
- 训练窗末段的独立校准区；
- 拟合/校准/OOS之间的Purge与Embargo；
- 数据快照hash；
- 标签重叠Block定义；
- Sealed Audit的绝对cutoff、访问日志和执行次数。

没有SplitPolicy ID的结果无效。

## 6. 特征治理

### 6.1 V1原则

- 正式特征上限：50个。
- 优先使用有经济解释、平稳或尺度归一的特征。
- 特征只使用决策时点真实可获得的信息。
- 训练、回测、Paper和Live使用同一份函数及顺序。
- BTC只能作为上下文，不因BTC信号在小资金阶段直接产生BTC订单。

### 6.2 特征变更

以下任一变化都生成新 `feature_schema_version`：

- 名称、顺序、类型；
- 窗口长度；
- 缺失值处理；
- 缩放/标准化；
- 来源或时间对齐；
- 数据修订规则；
- 计算代码产生经济差异。

每个 Candidate 必须通过：

- Prefix-vs-full 差分检查；
- 不同startup长度的递归稳定性检查；
- 实时/离线逐字段parity；
- 缺失、异常、极端值和数据延迟测试。

OOD只用于拒绝/缩仓，不得简单删除崩盘、跳空、极端Funding或高波动尾部训练样本。

## 7. 模型复杂度阶梯

每一级只有在前一级形成可信基准后才允许进入：

1. `NO_AI_BASE`：所有合格规则信号按确定性风险交易。
2. `LOGISTIC_BASELINE`：低方差、可解释Meta基准。
3. `XGBOOST_META`：V1主要候选。
4. `QUANTILE_MODELS`：q10/q50/q90净收益分布。
5. `REGIME/UNCERTAINTY_GATE`：只否决或缩仓。
6. `PULLBACK_CHALLENGER`：独立Proposal与Meta模型。
7. Foundation/Text模型：仅Forward Shadow。

端到端RL、在线真钱探索和LLM直接交易不在V1阶梯中。

## 8. ExperimentManifest

每个实验运行产生不可变 Manifest，至少记录：

### 8.1 身份与谱系

- `experiment_id`
- `hypothesis_id`
- `parent_experiment_ids`
- `release_route`：BASELINE_ONLY/AI_ENHANCED
- `ai_endpoint_or_null`：GROWTH/RISK_EFFICIENCY
- `endpoint_policy_version`
- `baseline_recipe_release_id`
- `recipe_release_id`
- `recipe_release_hash`
- `route_and_endpoint_frozen_at`
- `created_by`：Human/Agent
- `created_at`
- `status`：PLANNED/RUNNING/FAILED/COMPLETED/INVALIDATED
- `failure_reason`

### 8.2 代码和环境

- Git commit；
- dirty worktree标识及补丁哈希；
- 运行环境lock/hash；
- 库和硬件摘要；
- 全部随机种子；
- 训练入口和参数。

### 8.3 数据

- 原始数据快照ID/hash；
- 数据来源和可用时间规则；
- InstrumentMetadata版本；
- 训练、校准、验证区间；
- Purge/Embargo；
- 缺失和异常处理；
- 数据质量报告。

### 8.4 经济定义

- StrategyProposal版本；
- 特征schema/hash；
- 标签版本；
- 成本模型版本；
- Fill/Slippage/Funding模型；
- AccountingPolicy与CostAllocationPolicy版本；
- 批准生产资本、报告币种和评估窗口；
- 风险政策版本；
- 仓位映射版本；
- Benchmark版本。
- StatisticalDesignPolicy版本、最小经济相关效应、目标功效、最大CI宽度；
- 多重检验family ID、调整方法和family-wise alpha；

### 8.5 搜索规模

- 预声明Trial预算；
- 实际总Trial数；
- 超参数空间；
- 特征集合数量；
- 阈值变体数量；
- 被中止、失败和无效Trial。

### 8.6 产物

- 训练模型和校准器哈希；
- OOS逐时点预测；
- 每折交易和权益曲线；
- 指标、图表和审计报告；
- 特征重要性与稳定性；
- 失败日志；
- 最终结论和签字。

不得删除失败Experiment来美化研究历史。

实现时采用两段冻结避免与RecipeRelease形成循环self-hash：先冻结不包含`recipe_binding`和attestation的实验预注册内容，再由RecipeRelease引用该内容hash，最后以独立签名的`recipe_binding_hash`绑定实验hash与Recipe ID/hash。任何一段不一致都使发布证据无效。

## 9. ModelBundle

正式模型包必须自包含：

```text
model_id / version
recipe_release_id
recipe_release_hash
deployment_line_id
release_route
ai_endpoint_or_null
baseline_recipe_release_id
direction
model_native_file
model_hash
feature_schema
ordered_feature_names
preprocessor
calibrator
ood_detector
training_start/end
data_snapshot_hash
label_version
cost_model_version
code_commit
environment_hash
expected_input_types
eligibility_thresholds
output_quantization_precision
interface_compatibility_hash
staleness_policy
license/provenance
oos_prediction_artifact
model_card
```

要求：

- 使用安全原生模型格式；不从不可信来源加载pickle/joblib。
- 推理加载后必须对固定Golden Snapshot产生预期哈希。
- 模型包不可原地修改；任何变化产生新ID。
- 模型、校准器、预处理器和特征顺序共同晋级。
- ModelBundle必须强引用冻结的RecipeRelease hash；route、endpoint、方向、接口hash或输出量化精度不一致时不得作为Minor替换。
- Last-Known-Good模型包必须可独立恢复。

## 10. ModelProvenanceCard

任何第三方基础模型或LLM至少记录：

- 仓库/提供商；
- 模型名称与精确版本；
- 权重hash；
- 许可证；
- 发布日期；
- 声明的训练截止日期；
- 输入窗口和预处理；
- 推理代码commit；
- Prompt和输出schema；
- 温度/随机性设置；
- 成本与延迟；
- 已知限制。

历史文本预测只能重放当时保存的输出。禁止用今天的新模型回填过去日期后当作点时历史证据。

## 11. RecipeRelease、ModelBundle 与生命周期

三个对象不可混用：

- `RecipeRelease`：冻结的经济配方；决定特征、标签、模型族、固定超参数/训练流程、校准、阈值、仓位映射、成本口径和主终点。
- `ModelBundle`：按RecipeRelease和某个数据截止时间训练出的具体权重包。
- `DeploymentLine`：RecipeRelease正在经历的Shadow/Paper/Canary/Champion阶段，其证据可以跨兼容Minor Bundle连续累计。

```text
RECIPE_CANDIDATE
  → SHADOW
  → PAPER
  → CANARY_25
  → CANARY_50
  → CANARY_75
  → CHAMPION
  → RETIRED
```

### 11.1 Candidate

- Initial/Major RecipeRelease必须经过完整历史审计、Shadow、Paper和Canary；
- 同一RecipeRelease默认每月从零训练Minor ModelBundle；
- Continual/Warm-start只允许作为Shadow研究分支；
- 训练完成不自动改变任何部署指针；
- 必须与当前Champion、简单基线和空仓基准比较。

Minor仅允许更新训练数据和权重；release route、主终点、基础StrategyProposal、特征、标签、模型族、搜索空间、校准方法、阈值、PositionPolicy/风险档位映射、RiskPolicy、执行/Fill模型、数据源、成本/Accounting口径或任何接口变化都属于Major，并创建新的DeploymentLine，旧证据不得继承。

Minor Bundle刷新必须由独立的 `MINOR_BUNDLE_REFRESH` 门判定，至少要求：

- RecipeRelease ID/hash、route、endpoint、direction、代码、特征/标签/成本/风险接口hash完全相同；
- 只允许训练数据截止时间和由冻结训练流程产生的权重变化；
- 在与活动Bundle相同的OOS窗口、批准资本和policy bundle下，重新运行 `BASELINE_OFFLINE`；基线失效即停止刷新；
- 重新通过数据质量、滚动OOS、样本、AI绝对/增量经济门、Golden Snapshot和接口兼容检查；
- 在同一OOS时点上与当前活动Bundle做配对经济非劣比较；`RISK_EFFICIENCY` 还必须让相对活动Bundle的最大回撤改善LCB与ES95改善LCB均不劣于0；
- AI Bundle继续满足校准/OOD/分位数硬组件条件；
- 至少7天并行Shadow，且业务决策hash差异全部可解释；
- 具体非劣界以ReleaseGatePolicy为唯一数值源。

任何不满足兼容条件的变化自动升级为Major；不能由人工标签把它强行声明为Minor。

### 11.2 Shadow

- 最少7个自然日前向运行；
- 保存每个预测及拒绝原因；
- 与Champion并行但不影响订单；
- 检查数据新鲜度、推理延迟、特征parity、预测覆盖和漂移。

兼容Minor Bundle经至少7天并行Shadow和预声明非劣检查后，可以在当前DeploymentLine内原子替换，不重置已经积累的Paper/Canary日历证据。

替换前后的每个Decision必须记录实际Bundle ID。证据可以在同一DeploymentLine内累计，但报告必须按Bundle分段；若Minor门后来被证明错误，受影响时段全部失效并退回上一个仍合格Bundle。

### 11.3 Paper

- 系统级Paper至少90天；
- 使用实时行情、真实决策时钟和保守模拟Broker；
- 运行完整风险、订单、对账和事故流程；
- Paper期间不得根据短期PnL热改经济参数。

### 11.4 Canary

- 25/50/75%批准风险档位，各至少30天；
- 每级只使用事先批准的小额资金和单独部署记录；
- 只能按 `PAPER → CANARY_25 → CANARY_50 → CANARY_75 → CHAMPION` 顺序前进；
- 每个route、direction、venue、stage和固定评估区块必须生成独立GateEvidence，上一阶段PASS不得复制为下一阶段PASS；
- Shadow、Paper、每一级Canary和Champion都必须产生当前stage同scope的RUNTIME GateEvidence；Shadow使用无交易权限的模拟Broker与故障注入，任何stage都不得继承上一stage的RUNTIME PASS；
- 任何阶段失败，只能回退Approved Fallback Registry中仍有效的已发布DeploymentLine Champion/Last-Known-Good，或保持零新增风险；
- 只在预注册的30天区块末评估；不足则进入下一个固定区块，最多3个区块；
- 短期正PnL不用于重新证明Edge，Canary主要验证安全、成交成本和模拟一致性；
- 安全事故或预注册伤害边界可以提前停止，不能每日查看PnL后选择性停机。

### 11.5 Champion

- Champion是部署指针，不是“最新训练模型”。
- 每个方向最多一个正式Champion。
- Champion继续接受数据、校准、执行偏差和经济表现监控。
- 替换必须原子完成并保留前一版本。

### 11.6 Approved Fallback Registry

回退对象不是字符串名称，而是不可变批准记录：

```text
fallback_approval_id
record_hash
source.release_route/ai_endpoint
source.recipe_release_id/hash
source.deployment_line_id
source.model_bundle_id | source.no_ai_base_version
fallback.release_route/ai_endpoint
fallback.recipe_release_id/hash
fallback.deployment_line_id
fallback.model_bundle_id | fallback.no_ai_base_version
fallback_qualification          CHAMPION | LAST_KNOWN_GOOD
direction
venue
maximum_approved_stage
approved_at
expires_at
policy_hashes
last_known_good_evidence_hash
status
qualification_attestation
signature
```

- `NO_AI_BASE`只有来自仍有效、已发布且已批准的独立 `BASELINE_ONLY` DeploymentLine Champion或该Line的已批准Last-Known-Good版本时，才可登记为回退对象。
- Logistic只有来自仍有效、已发布且已批准的 `AI_ENHANCED` DeploymentLine Champion或该Line的已批准Last-Known-Good Bundle时，才可回退；任何Candidate即使已获研究审批也没有实盘回退资格。
- 回退后的权威stage不得高于回退记录的 `maximum_approved_stage`。
- 当前source Line、方向、venue或政策hash不匹配时禁止使用该映射；fallback对象本身的Recipe、Line和Bundle资格也必须仍有效。
- 没有合格记录时，唯一动作是 `FREEZE_INCREASES`；硬风险另有要求时 `FLATTEN`。
- XGBoost在研究门失败时可以降级为新的Logistic Candidate，但不能因此跳过该Candidate自己的完整发布路径。

### 11.7 Staleness

初始默认：

- 距ModelBundle训练数据截止时间超过45天：预警并将最大AI风险档位降一级；
- 超过90天：禁止该模型新增风险；
- schema、数据源或成本定义变化：立即失效，不等待天数。

DeploymentLine在187天完整验证过程中通过兼容Minor Bundle保持新鲜；90天限制作用于具体Bundle，不作用于冻结RecipeRelease。具体天数只能在下一次Major Release Audit前前瞻修改。

## 12. 晋级门

阈值、边界包含关系和 `REQUIRED/ADVISORY` 属性以版本化ReleaseGatePolicy为准；指标单位/估计器以Metric Catalog为准；证据文件、条件聚合和作用域以《发布评估与证据规范》为准。本文解释经济意义；不得在不同报告中改用更宽松的同义表述。

### 12.1 硬有效性门：全部必须通过

- 无未来函数；
- 无训练/审计数据污染；
- Purge/Embargo正确；
- 特征实时/离线parity通过；
- 同输入推理可重现；
- Manifest与ModelBundle完整；
- 无未登记Trial；
- 长短方向独立报告；
- 交易、费用、Funding和Slippage均计入；
- 模型许可证与来源可接受；
- 风险层无法被模型绕过。

任一失败直接No-Go，不进入收益比较。

### 12.2 基线经济门

简单基线本身必须：

- 通过预注册样本功效和置信区间宽度门；
- 变量交易成本后净对数增长的一侧95%Moving-block Bootstrap下界大于0；
- 8个OOS折中至少6折成本后不为负；该项是跨时段稳健性附加门，不能替代前一项；
- 1.5倍费用/滑点压力下仍保持非负；
- 正常OOS最大回撤低于10%，2倍成本与不利Funding压力情景低于15%；
- 删除最大正收益折后，变量成本后净对数增长的一侧95%下界仍大于0；
- 删除盈利最大的5笔交易后，变量成本后净对数增长的一侧95%下界仍大于0；
- 单折、单笔和前5笔贡献占比继续报告，但只作诊断，不替代leave-out门；
- 交易频率和最短持有符合设计；
- 按批准全风险规模估算的月度固定运营成本后economic PnL一侧95%下界大于0。

如果基线失败，AI研究停止在Shadow。

### 12.3 AI增量经济门

相对于完全相同的Proposal、资本、时间轴、成交模型和风险政策，AI Candidate必须：

- 先通过简单基线门；
- 预先选择 `GROWTH` 或 `RISK_EFFICIENCY` 主终点路线；
- AI臂自身变量成本后净对数增长的一侧95%下界大于0；
- AI臂按批准全风险资本、计入AI增量固定成本后的月度economic PnL一侧95%下界大于0；
- `GROWTH`：配对增量economic净对数增长的一侧95%Moving-block Bootstrap下界大于0；
- `RISK_EFFICIENCY`：配对增量下界不低于 `-10% × abs(base_net_log_growth)`；最大回撤改善和ES95改善各自的一侧95%配对Block Bootstrap下界均至少20%；
- 至少6/8 OOS折自身变量成本后收益非负；
- 至少6/8 OOS折不劣于基线；
- 删除最大正增量折后，所选AI主终点仍完整通过；
- DSR置信概率≥95%，PBO≤20%；
- 正常成本下最大回撤低于10%；
- 1.5倍交易成本下自身净收益和相对基线增量均不为负；
- 2倍成本与不利Funding压力下最大回撤低于15%；
- XGBoost的OOS Brier必须严格低于常数概率和Logistic；GROWTH时其配对增量LCB必须高于Logistic，RISK_EFFICIENCY时其收益非劣LCB、回撤改善LCB和ES95改善LCB对Logistic形成Pareto支配（均不差且至少一项严格更好）；否则保留Logistic Candidate或NO_AI Candidate并走各自发布路径；
- 概率ECE≤0.05且报告分箱和置信区间；
- q10/q50/q90覆盖率的预声明置信区间包含目标覆盖率；不满足时Quantile模块不得成为硬仓位组件；
- 离散风险档位优于直接按原始概率线性加仓；
- Audit窗口同样通过预声明配对Block CI、功效、贡献集中度和绝对净收益门，不能凭一个大盈利交易或点估计大于0通过。

若有效样本不足以形成稳定置信区间，保持Shadow，不以点估计晋级。

`AI_ENHANCED` 的Release Audit必须在同一窗口、批准资本和全部policy hash下分别维护 `BASELINE_LEDGER` 与 `AI_LEDGER`：前者以 `evaluation_ledger=BASELINE_LEDGER` 独立通过 `AUDIT_BASE_ARM`，后者以 `evaluation_ledger=AI_LEDGER` 独立通过 `AUDIT_AI_ARM`；两套绝对门均PASS后，才以 `evaluation_ledger=PAIRED_COMPARISON` 依次执行 `AUDIT_AI_PAIRED_COMMON` 和所选 `AUDIT_AI_ENDPOINT.*` 配对增量门。任何一套绝对门失败都不得用另一套或配对增量掩盖。

配对AI增量定义：

```text
delta_ai_economic_net_log_growth
  = AI_arm_economic_net_log_growth
  - NO_AI_BASE_economic_net_log_growth
```

两臂从相同 `approved_production_capital_usdt` 开始并维护独立虚拟账本。AI臂的economic权益路径已经扣除增量数据、推理、训练、监控和审计成本；不得再从对数增长差中重复扣一次USDT成本。两臂共享的基础设施成本按同一CostAllocationPolicy分摊或相消。另行报告同窗口的USDT PnL差。Live报告必须拆成：

1. 同一保守模拟成交模型下的策略增量；
2. AI实盘成交相对模拟的Execution Variance。

不得把不同成交条件造成的差异算成AI Alpha。

### 12.4 运行门

Shadow、Paper、每一级Canary和Champion都必须在各自stage scope通过RUNTIME门；Shadow使用无交易权限的模拟Broker，其余阶段使用对应真实或Paper执行环境。运行门至少包括：

- 0次重复经济订单；
- 0次未记录成交；
- 0次硬风险绕过；
- 0次在未解释对账差异下新增风险；
- 100%订单可追溯；
- 正式决策与离线重放100%一致；
- 实际费用、Funding和滑点位于预声明模型容差；
- 模型拒绝和风险锁行为符合预期；
- Full-risk规模的月度economic PnL一侧95%下界仍满足Break-even门。
- 进入任何真钱stage时，`actual_deployable_capital_usdt` 同时不低于Evidence Scope冻结的 `approved_production_capital_usdt` 和 `break_even_capital_lcb_root_usdt`；超出批准资本的资金不自动扩大风险。

Paper/Canary的少量交易只验证运行、安全、可成交性和成本外推，不能单独重新证明长期Edge。小额Canary固定成本可以作为预先批准的验证支出单列。

## 13. 监控、降级与回退

立即禁止新增风险：

- 模型包或特征schema不匹配；
- 数据过期；
- OOD超过硬阈值；
- 校准器失效；
- 预测异常或NaN；
- 模型超过硬过期时间；
- 当前模型无法产生Golden Snapshot预期结果；
- 对账、连接或灾难止损风险锁；
- 任一硬风险状态。

退役或回退：

- 实际滑点、成本或交易频率持续超出审计假设；
- Forward表现穿越预先定义的劣化控制带；
- 决策/实盘差异无法解释；
- 上游数据定义、费用或交易规则发生实质变化；
- 发现历史泄漏、审计污染或未登记试验；
- 许可证或模型来源出现问题。

回退顺序：

```text
Current Champion
  → Last-Known-Good Champion
  → Independently Approved Simple Baseline
  → Zero New Risk
```

不得通过临时降低风控、放宽阈值或在线重训来“挽救”表现恶化的模型。

## 14. 文本AI和Agent

文本AI只输出严格结构化字段，例如：

```text
event_type
asset
directional_tone
novelty
credibility
time_horizon
source_count
published_at
available_at
uncertainty
```

每条结果保存：

- 原始文档；
- published/event/available/ingested/recorded时间；
- URL/来源和内容hash；
- 模型、Prompt、schema和推理代码版本；
- 原始响应；
- 解析结果；
- token、延迟和费用。

正式经济证据只采用模型发布后产生的Forward Shadow输出。LLM置信度不得直接进入仓位映射。

Agent研究权限：

- 可读取Development和Research Walk-forward；
- 不可读取Release Audit、Live密钥和Broker；
- 只能创建Proposal和ExperimentManifest；
- 不能修改硬风险政策；
- 不能自动晋级、部署或删除失败实验。

## 15. 赚钱导向报告

每个实验和部署同时报告：

### 15.1 一级经济指标

- 全成本 economic PnL；
- 净复合/对数增长；
- 相对简单基线的增量收益；
- 最大回撤和Time-under-water；
- Expected Shortfall/CVaR；
- 成本占毛收益比例；
- 固定运营成本的Break-even AUM。
- AI增量数据、推理、训练和监控成本；
- 共享固定成本的分摊规则；
- 小额Canary验证支出；

### 15.2 二级交易指标

- 换手率；
- 交易数和有效样本数；
- 多空分解；
- Regime分解；
- Maker/Taker比例；
- Funding贡献；
- 预期/实际滑点；
- 风险档位使用分布；
- 拒绝交易后的机会成本。

### 15.3 三级模型指标

- Brier Score/Skill；
- Calibration Curve和ECE；
- Precision/Recall/F1/AUC；
- 分位数覆盖率；
- OOD率；
- Feature稳定性与漂移；
- PredictionEligibility原因分布。

模型指标只能解释经济结果，不能覆盖经济结果。
