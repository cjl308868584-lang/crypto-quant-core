# 发布评估与证据规范 v1.1

状态：设计基线，Fail-Closed
日期：2026-07-26
上位文档：[系统计划 v1.1](system-plan-v1.1.md)
发布政策：[ReleaseGatePolicy v1.1](../config/release-gates-v1.1.json)

## 1. 目的

本规范回答一个具体问题：同一份研究与运行证据，是否能由两个独立Runner得到完全相同的 `PASS/FAIL/INCONCLUSIVE/NOT_APPLICABLE` 结果。

以下文件共同组成政策包：

- [ReleaseGatePolicy](../config/release-gates-v1.1.json)：门组、阈值、比较运算符、路线、阶段和动作；
- [ReleaseGatePolicy Schema](../config/release-gates-v1.1.schema.json)：政策结构、条件和表达式AST；
- [Metric Catalog](../config/release-metrics-v1.1.json)：指标单位、估计器和版本化算法；
- [Metric Catalog Schema](../config/release-metrics-v1.1.schema.json)：指标目录结构；
- [GateEvidence Schema](../config/release-evidence-v1.1.schema.json)：每个门的证据范围和审计信封；
- [RecipeRelease Schema](../config/recipe-release-v1.1.schema.json)：冻结route、endpoint、配方和政策hash；
- [ModelBundle Schema](../config/model-bundle-v1.1.schema.json)：绑定RecipeRelease、DeploymentLine、权重、接口和证据；
- [Approved Fallback Registry Schema](../config/approved-fallback-registry-v1.1.schema.json)：验证签名回退映射及Champion/LKG资格；
- 每个Release绑定的DataQualityPolicy、SplitPolicy、StatisticalDesignPolicy、AccountingPolicy、CostAllocationPolicy和ForwardControlPolicy。

当前 `production_activation.enabled=false` 是有意的。缺少任一必需绑定、Evaluator build hash或政策hash时，系统只能Fail-Closed，不能产生正式Release PASS。阶段0完成实现和一致性测试后，必须发布一个新policy版本才可激活，不能原地把false改成true。

## 2. 不可变发布身份

### 2.1 RecipeRelease

RecipeRelease至少冻结：

```text
schema_version
recipe_release_id
recipe_release_hash
hash_algorithm
canonicalization
release_kind                 INITIAL | MAJOR
release_route                BASELINE_ONLY | AI_ENHANCED
ai_endpoint                  null | GROWTH | RISK_EFFICIENCY
baseline_recipe_release_id
baseline_recipe_release_hash
model_family
directions
venues
experiment_manifest_hash
strategy_proposal_hash
feature_schema_hash
label_definition_hash
model_family_hash
hyperparameter_search_space_hash
calibration_method_hash
decision_thresholds_hash
position_policy_hash
risk_policy_hash
execution_fill_model_hash
data_source_policy_hash
cost_definition_hash
accounting_policy_hash
interface_compatibility_hash
data_quality_policy_hash
split_policy_hash
statistical_design_policy_hash
cost_allocation_policy_hash
forward_control_policy_hash
release_gate_policy_hash
policy_bundle_hash
created_at
frozen_at
first_outcome_available_at
freeze_attestation
status
```

route和endpoint必须在结果揭晓前进入RecipeRelease hash。同一RecipeRelease内不能从GROWTH切换到RISK_EFFICIENCY，也不能从AI_ENHANCED改成BASELINE_ONLY来解释同一审计结果。

在首次结果揭晓前，RecipeRelease中的全部设计、数据、统计、会计、成本、风险、执行和Forward Control hash，以及ModelBundle中的代码/环境hash，必须冻结。GateEvidence还必须在 `frozen_release_inputs` 中保存RecipeRelease及其Schema、ExperimentManifest、Metric Catalog、Evidence Schema、ReleaseGatePolicy、Risk/DataQuality/Split/StatisticalDesign/Accounting/CostAllocation/ForwardControl政策、合规证明和Evaluator build的逐项freeze proof；资本网格/资本搜索计划的内容hash进入 `artifact_hashes`，`approved_production_capital_usdt`、`actual_deployable_capital_usdt` 与 `break_even_capital_lcb_root_usdt` 同时冻结。上述freeze proof的 `frozen_at` 和所有资本输入都必须早于或等于 `first_result_revealed_at`。Initial的“首次揭晓”是第一次打开封存审计结果；Major的“首次揭晓”是第一条prequential预测对应结果变为可见。此后任一设计、会计、成本、资本、代码/环境或Evaluator hash，或任一批准资本/资本搜索输入发生变化，都必须创建新的RecipeRelease/Evidence Scope；已揭晓证据不得继续用于原Release。

### 2.2 ModelBundle

ModelBundle必须强引用 `recipe_release_id/hash`、DeploymentLine、route、endpoint、direction、接口兼容hash和输出量化精度。只有训练数据截止时间和冻结训练流水线产生的权重变化，才可能属于Minor Bundle。

### 2.3 DeploymentLine

DeploymentLine是 `RecipeRelease × direction × venue` 的阶段状态。Initial/Major创建新Line；Minor Bundle只能在通过专属刷新门后替换当前Line中的权重，不创建或跳跃阶段。

## 3. Evidence Scope

任何GateEvidence至少由以下维度唯一限定：

```text
gate_group_id
release_route
release_kind
recipe_release_id/hash
deployment_line_id
direction
venue
stage
evaluation_window_start/end
evaluation_ledger
approved_production_capital_usdt
actual_deployable_capital_usdt
break_even_capital_lcb_root_usdt
policy_bundle_hash
fallback_activation_requested
```

AI证据再加入 `ai_endpoint/model_bundle_id`；Canary证据再加入 `canary_block_number`。`gate_group_id` 与 `evaluation_ledger` 是GateEvidence顶层强制Scope维度：基础设施、结构和运行证据可使用 `ROUTE_RUNTIME`；AI Release Audit的绝对门分别使用 `BASELINE_LEDGER` 和 `AI_LEDGER`，公共配对稳健性及endpoint增量门使用 `PAIRED_COMPARISON`，不同角色的Evidence不得互相复用。只有 `fallback_activation_requested=true` 时才要求完整的签名回退记录证据；false并不表示存在回退资格。真钱stage必须固定 `actual_deployable_capital_usdt`、`break_even_capital_lcb_root_usdt` 及资本网格/资本搜索计划的artifact hash，这些值同样参与Exact Scope匹配。

规则：

- 只有Scope完全相同的Evidence才能复用。
- LONG的PASS不能用于SHORT。
- Binance Spot LONG的PASS不能用于USDT Perp SHORT。
- CANARY_25的PASS不能复制为CANARY_50。
- 500 USDT资本的economic gate不能替代1,000 USDT资本，反之亦然。
- 不同Accounting/Cost/Split/DataQuality/ForwardControl hash的证据不能合并。
- Minor替换前后的证据必须按Bundle分段，即使DeploymentLine日历允许连续累计。

## 4. 确定性Evaluator

正式Runner按固定顺序执行：

1. 使用JSON Schema验证政策、Metric Catalog和Evidence；未知Gate/Evidence字段、非法Decimal、未识别operator直接FAIL，其他扩展字段也必须由当前Evaluator build登记。
2. 解析所有必需policy binding及其内容hash；缺失直接FAIL。
3. 验证RecipeRelease、ExperimentManifest、ModelBundle和DeploymentLine之间的hash引用。
4. 根据 `release_kind × route × endpoint × direction × venue × stage` 选择唯一门矩阵。
5. 对每个条件门计算 `applies_when`：
   - 条件真：正常求值；
   - 条件假：`NOT_APPLICABLE`；
   - 条件字段缺失：FAIL，不能当作不适用。
6. 从Metric Catalog解析唯一metric family/override、单位和estimator；无匹配或多义性按Catalog规则FAIL。
7. 使用 `RELEASE_EXPR_AST_V1` 解析阈值。自由文本公式禁止参与正式求值。
8. Decimal按规范字符串精确比较；NaN、Inf、负零和二进制浮点阈值非法。
9. 样本或区块不足返回INCONCLUSIVE，不允许晋级。
10. 所有适用的required gate都PASS时，门组才PASS；ADVISORY指标不参与聚合。
11. 保存完整GateEvidence、输入artifact hash、政策hash、估计器版本和Evaluator build hash。

不能用一个名为 `all_checks_pass=true` 的上游布尔替代下游硬门。组合门只允许引用Policy中列明的子Gate ID，并保存每个子结果。

## 5. 样本与统计设计

统一使用 `effective_event_count`，估计器为 `GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1`。AI增量只保留AI实际改变基线动作或绝对敞口的配对时点，再计算ESS。

每个route、direction和endpoint在打开审计前必须冻结StatisticalDesignPolicy：

- 最小经济相关效应；
- achieved power算法及最低80%门；
- 最大允许CI宽度；
- Moving-block Bootstrap区块长度、最小区块数、重采样数和随机种子；
- ECE分箱和区间算法；
- DSR/PBO实现、收益频率和累计Trial family；
- 同时送审候选的Holm family-wise 5%调整。

正式门检查实际achieved power和实际CI宽度。仅存在“功效计划”文档不能通过。

风险效率路线的最大回撤与ES95改善都使用一侧95%配对Block Bootstrap下界，不用点估计晋级。基线和AI还执行leave-out脆弱性门；贡献占比只作诊断。

## 6. Release Audit矩阵

### 6.1 Initial

使用最后12个月封存历史，只允许运行一次。共同门：

- 结构、PIT、可重放、全部Trial和多重检验；
- 实际功效与CI宽度；
- 绝对变量成本净增长LCB>0；
- 正常最大回撤<10%；
- 1.5倍成本净增长≥0；
- 2倍成本加不利Funding最大回撤<15%；
- 分别移除最大正贡献fold及前5笔正贡献交易后，净增长LCB仍>0；
- 批准全风险资本的月度economic PnL LCB>0。

`BASELINE_ONLY`只在 `BASELINE_LEDGER` 上运行一次上述绝对门。`AI_ENHANCED`必须在完全相同的候选事件、评估窗口、起始批准资本、AccountingPolicy、CostAllocationPolicy、成交模型和其他policy hash下生成两个独立账本：

- `BASELINE_LEDGER`：执行冻结的 `NO_AI_BASE` 动作；
- `AI_LEDGER`：执行待发布AI的动作，并承担其增量数据、推理、训练、监控和审计成本。

评估顺序固定为：

1. 在 `BASELINE_LEDGER` 上运行 `AUDIT_BASE_ARM` 绝对门；
2. 在 `AI_LEDGER` 上独立运行 `AUDIT_AI_ARM` 绝对门；
3. 两套绝对门都PASS后，在 `PAIRED_COMPARISON` 上运行公共leave-max-delta稳健性组 `AUDIT_AI_PAIRED_COMMON`；
4. 公共配对门PASS后，再运行所选 `AUDIT_AI_ENDPOINT.*` 配对增量门。

AI路线的每条 `AUDIT_BASE_ARM`/`AUDIT_AI_ARM` GateEvidence必须在顶层 `gate_group_id` 与 `evaluation_ledger` 分别记录对应门组及 `BASELINE_LEDGER`/`AI_LEDGER`，`evidence_id`和账本Manifest hash也必须包含该角色；一条账本的PASS不得替代另一条。`AUDIT_AI_PAIRED_COMMON` 与 `AUDIT_AI_ENDPOINT.*` 使用 `evaluation_ledger=PAIRED_COMPARISON`，只能按同一 `proposal_id + decision_time` 连接两账本；窗口、资本或policy hash不一致直接FAIL。GROWTH检查配对增量LCB>0；RISK_EFFICIENCY检查收益非劣及两项风险改善LCB。

### 6.2 Major

不得重刷已暴露历史窗口。配方冻结后，所有预测必须在结果发生前提交hash并形成prequential Forward Evidence。日历长度本身不构成PASS；持续收集直至同一Audit门的功效、CI宽度和经济证据全部PASS，否则INCONCLUSIVE。

OOS的“6/8折”只适用于Research Walk-forward，不强行套到单个Audit窗口。Audit使用Policy明确列出的 `AUDIT_*` 门，不使用模糊的“适用门全部通过”占位符。

## 7. Paper与Canary

Paper至少90个完整自然日。所有路线检查绝对PnL伤害带、最大回撤、成本上界、full-risk月度economic PnL一侧95%下界和运行门；AI_ENHANCED另外按endpoint检查：

- GROWTH：配对增量控制带；
- RISK_EFFICIENCY：收益非劣、最大回撤收益和ES95收益三条独立控制带；
- 校准；Quantile影响硬仓位时再检查覆盖率。

### 7.1 Forward route × stage 唯一门矩阵

`RECIPE_CANDIDATE → SHADOW` 先按route通过Policy列出的全部Offline门和对应Release Audit矩阵。进入Forward后，每个当前stage在晋级或继续保持Champion资格前必须通过下表；表中 `RUNTIME` 每一行都必需，不能被其他门组隐含、替代或从上一stage继承。

| Route | 当前stage | 晋级或维持资格所需Gate Group |
|---|---|---|
| `BASELINE_ONLY` | `SHADOW` | `STRUCTURAL` + `SHADOW` + `RUNTIME` |
| `BASELINE_ONLY` | `PAPER` | `STRUCTURAL` + `PAPER_COMMON` + `RUNTIME` + `CAPITAL_READINESS` |
| `BASELINE_ONLY` | `CANARY_25` | `CANARY_25` scope的 `STRUCTURAL` + `CANARY_COMMON` + `RUNTIME` + `CAPITAL_READINESS` |
| `BASELINE_ONLY` | `CANARY_50` | `CANARY_50` scope的 `STRUCTURAL` + `CANARY_COMMON` + `RUNTIME` + `CAPITAL_READINESS` |
| `BASELINE_ONLY` | `CANARY_75` | `CANARY_75` scope的 `STRUCTURAL` + `CANARY_COMMON` + `RUNTIME` + `CAPITAL_READINESS` |
| `BASELINE_ONLY` | `CHAMPION` | 当前stage的 `STRUCTURAL` + `RUNTIME` + `CAPITAL_READINESS` |
| `AI_ENHANCED` | `SHADOW` | `STRUCTURAL` + `SHADOW` + `RUNTIME` |
| `AI_ENHANCED` | `PAPER` | `STRUCTURAL` + `PAPER_COMMON` + `PAPER_AI` + `RUNTIME` + `CAPITAL_READINESS` |
| `AI_ENHANCED` | `CANARY_25` | `CANARY_25` scope的 `STRUCTURAL` + `CANARY_COMMON` + `CANARY_AI` + `RUNTIME` + `CAPITAL_READINESS` |
| `AI_ENHANCED` | `CANARY_50` | `CANARY_50` scope的 `STRUCTURAL` + `CANARY_COMMON` + `CANARY_AI` + `RUNTIME` + `CAPITAL_READINESS` |
| `AI_ENHANCED` | `CANARY_75` | `CANARY_75` scope的 `STRUCTURAL` + `CANARY_COMMON` + `CANARY_AI` + `RUNTIME` + `CAPITAL_READINESS` |
| `AI_ENHANCED` | `CHAMPION` | 当前stage的 `STRUCTURAL` + `RUNTIME` + `CAPITAL_READINESS` |

Shadow没有交易API权限，但仍必须用模拟Broker和故障注入产生同scope的 `RUNTIME` 证据。Paper、每一级Canary和Champion必须重新产生各自stage、route、direction和venue的 `RUNTIME` 证据；缺失、FAIL或INCONCLUSIVE均禁止晋级或继续扩大风险。Canary的 `RUNTIME` 失败与 `CANARY_COMMON/CANARY_AI` 失败具有相同阻断效果。

Canary严格执行：

```text
PAPER → CANARY_25 → CANARY_50 → CANARY_75 → CHAMPION
```

每级只在固定30天区块末判定，最多3个区块。安全或预声明伤害边界可以提前停止，不能提前宣布成功。当前区块发生任一S0/S1即失败；事故关闭后从新的完整30天区块重启观察。

小额Canary不重新证明长期Alpha，也不要求SHORT在少数交易内点估计盈利；它验证运行、安全、可成交性、成本和伤害边界。正式盈利声明仍依赖批准全风险资本的月度economic PnL一侧95%下界。

## 8. Minor Bundle刷新

Minor刷新必须同时通过：

- Recipe、route、endpoint、direction、代码和接口hash完全一致；
- 只改变训练截止时间及冻结流程生成的权重；
- 在同一OOS窗口、批准资本和policy bundle下重新运行 `BASELINE_OFFLINE`，简单基线失效时不得用新AI Bundle掩盖；
- 数据质量、滚动OOS、样本和AI绝对/增量门；
- Golden Snapshot；
- 与活动Bundle使用完全相同OOS时点；
- 新旧配对economic growth一侧95%LCB不低于活动Bundle增长绝对值的-5%；
- 新Bundle最大回撤<10%，且相对活动Bundle恶化不超过1个百分点；
- `RISK_EFFICIENCY` 还要求相对活动Bundle的最大回撤改善LCB与ES95改善LCB均不劣于0；连同收益非劣门形成三维Pareto非劣，否则保留未过期Champion；
- ECE≤0.05，且恶化不超过0.01；
- 至少7天、12个结算周期的并行Shadow；
- 无无法解释的决策差异。

刷新失败时继续使用未过期的活动Bundle；达到90天仍无合格替代时禁止AI新增风险。Minor不重开历史封存审计，也不重置DeploymentLine日历；配方、接口或经济逻辑变化自动升级为Major。

## 9. 回退资格

回退只读取Approved Fallback Registry。签名记录使用 `source.*` 与 `fallback.*` 两个不可变route reference，把当前source route/recipe/deployment line显式映射到fallback route/recipe/deployment line及其ModelBundle或NO_AI版本，并精确匹配direction、venue、`fallback_qualification=CHAMPION|LAST_KNOWN_GOOD`、最大批准stage、政策hash、状态和有效期。

- `NO_AI_BASE`也只能来自仍有效、已发布且已批准的BASELINE_ONLY DeploymentLine Champion或该Line的已批准Last-Known-Good版本。
- Logistic只能来自仍有效、已经完成其适用Shadow/Paper/Canary路径并登记在Approved Fallback Registry中的已发布DeploymentLine：该Line的Champion或已批准Last-Known-Good Bundle均可；任何Candidate即使通过研究审批也没有实盘回退资格。
- XGBoost研究失败只能产生新的Logistic Candidate；该Candidate完成自己的完整发布路径前不得成为实盘fallback。
- 回退风险不得高于fallback记录批准的stage。
- 无匹配记录时 `FREEZE_INCREASES`；硬风险要求退出时才 `FLATTEN`。

## 10. 资本、敞口与会计

风险档位存储为整数百分数：

```text
bucket_ratio = risk_bucket / 100
model_exposure = base_volatility_exposure × bucket_ratio
stage_capped_exposure = model_exposure × authoritative_stage_multiplier
```

RiskGate独立重算上式，再与确定性风险、可用权益和1x上限取最小值。

1x使用所有风险增加型活动订单完全成交后的最坏毛敞口除以marked equity；现货与永续反向头寸不得净额抵消。订单角色UNKNOWN时按增加风险计。

AccountingPolicy固定移动加权平均成本、逐Fill部分成交、Funding分配、非USDT估值、窗口末可执行平仓价、批准资本和现金流调整。AI/NO_AI各自维护相同起始资本的虚拟账本；主增量是相同单位的economic net log growth之差。

Break-even Capital通过资本网格逐点重放并求 `monthly_economic_pnl_lcb(C)>0` 的最小正根。闭式 `fixed_cost/return_rate` 只在线性条件下作诊断，不参与放行。

进入任何真钱stage前，`actual_deployable_capital_usdt`（扣除不可用余额、预留资金和其他账户占用后可归属于本策略的真实资本）必须同时满足：

```text
actual_deployable_capital_usdt >= approved_production_capital_usdt
actual_deployable_capital_usdt >= break_even_capital_lcb_root_usdt
```

两项数值及其Accounting/CostAllocation/资本网格hash必须与当前Evidence Scope完全一致；`break_even_capital_lcb_root_usdt` 为null、没有有限正根或任一不等式不成立，均使 `CAPITAL_READINESS` 硬门FAIL。不能用较大批准资本的历史Evidence替代较小实际资本。实际资本高于批准资本也不自动扩大风险，仓位计算仍以批准资本为上限；扩大批准资本必须创建新的Evidence Scope并重新通过经济门。Canary按stage multiplier只使用其中一部分风险预算，因此其阶段PnL仍可作为预先批准的验证支出，但账户实际合格资本不能绕过上述两项真钱门。

## 11. Phase 0必须通过的Evaluator测试

- Policy、Metric、Evidence、RecipeRelease、ModelBundle和Approved Fallback Registry Schema正反例；
- 同Evidence运行100次得到完全相同结果和业务hash；
- 所有Policy metric都能在Catalog中唯一解析；
- 所有estimator ID都存在；
- 条件缺失不会被误判为NOT_APPLICABLE；
- BASELINE_ONLY不会要求AI证据；
- AI_ENHANCED同时检查绝对与endpoint证据；
- AI_ENHANCED Audit在同窗分别要求BASELINE_LEDGER与AI_LEDGER的绝对门，再要求 `AUDIT_AI_PAIRED_COMMON` 与endpoint paired delta门；
- Initial/Major Audit选择不同来源但相同经济原则；
- Forward每个stage按route选择唯一门组，且每一stage都要求同scope的RUNTIME；
- CANARY_25 Evidence不能用于CANARY_50；
- LONG Evidence不能用于SHORT；
- 资本或政策hash不同不能复用Evidence；
- 伪造Target stage multiplier不能突破RiskGate；
- 25档按0.25而不是25参与计算；
- 现货与永续对冲不能绕过1x毛敞口；
- Minor Recipe hash不一致时自动转Major；
- 未批准NO_AI/Logistic无法成为fallback；
- Candidate无论研究审批状态如何都不能成为实盘fallback；
- `fallback_activation_requested=false` 不会伪造回退资格；true时缺签名、过期、状态非APPROVED、目标非Champion/LKG或scope/hash不匹配均FAIL；
- `actual_deployable_capital_usdt` 低于 `approved_production_capital_usdt` 或 `break_even_capital_lcb_root_usdt` 时不能进入真钱stage；
- 当前Canary区块发生S0/S1后即使事故已关闭仍不能PASS；
- 缺少任一policy binding或Evaluator build hash时Fail-Closed。
