# ADR-0008：实验、部署线与辅助观测的不可变信任链

状态：Accepted
日期：2026-07-26

## 背景

v0.7.0已经能独立执行登记的Estimator并绑定Evaluator build，但三个边界仍不完整：

1. GateEvidence中的ExperimentManifest只有freeze proof hash，没有生产Schema和完整内容验证。
2. `deployment_line_id`只是字符串，不能证明Recipe、方向、venue、阶段顺序和活动ModelBundle属于同一条DeploymentLine。
3. 动态阈值依赖的supporting observation仍可由调用方传入自由映射，Evaluator无法证明数值来自Catalog指定Estimator。

这些缺口会让一个形式合法的AI实验或辅助指标绕过研究预算、阶段顺序或独立重算，最终把不可信的收益证据带到资金门槛。

## 循环引用问题

v1.1文档要求RecipeRelease引用`experiment_manifest_hash`，同时ExperimentManifest又记录`recipe_release_hash`。若两个完整对象都把对方hash纳入自身self-hash，会形成密码学循环，无法构造稳定对象。

本增量采用两段冻结：

1. 先冻结实验预注册内容，计算不包含`recipe_binding`和签名的`experiment_manifest_hash`。
2. RecipeRelease引用该hash并计算自己的`recipe_release_hash`。
3. ExperimentManifest的`recipe_binding`再绑定实验hash、Recipe ID/hash，形成独立`recipe_binding_hash`。
4. 外部签名验证结果必须把Manifest attestation精确映射到`recipe_binding_hash`。

因此实验设计不可事后改变，Recipe也不能被替换，同时不存在循环self-hash。

## 决策

### ExperimentManifest

1. 新增生产Schema，覆盖身份谱系、route/endpoint、代码环境、随机种子、点时数据、InstrumentMetadata、Purge/Embargo、经济口径、21项冻结设计hash、Trial预算、失败Trial和输出Artifact。
2. 用于发布的Manifest必须为`COMPLETED`且结论为`CANDIDATE`；FAILED、INVALIDATED、未完成或拒绝结论不能进入正式GateEvidence。
3. 实际Trial数不得超过预声明预算，失败/中止/无效Trial合计不得超过实际Trial数；失败历史通过`trial_registry_hash`与`failure_log_hash`保留。
4. 数据窗口必须有时区、严格递增、不重叠且role不重复。
5. Route、endpoint、baseline reference、Recipe binding、全部经济设计hash、批准资本和首次结果揭晓顺序必须与RecipeRelease及GateEvidence一致。

### DeploymentLine

1. 新增生产Schema，将DeploymentLine固定为`RecipeRelease × direction × venue`，并绑定ExperimentManifest、route、endpoint和活动ModelBundle或NO_AI版本。
2. 阶段历史只能是`RECIPE_CANDIDATE → SHADOW → PAPER → CANARY_25 → CANARY_50 → CANARY_75 → CHAMPION`的前缀；不允许跳级、倒序或重用上一阶段PASS。
3. 所有已退出阶段必须PASS、有证据hash且时间严格递增；当前阶段必须是未退出的`IN_PROGRESS`。
4. Major不得继承旧证据；兼容Minor可以保留阶段日历，但报告必须按Bundle分段。
5. Line self-hash排除签名字段，外部attestation必须精确绑定Line hash；Evidence同时冻结Line ID和hash。
6. ReleaseGatePolicy `1.1.3`把Experiment ID/hash和DeploymentLine hash加入Exact Scope；同ID内容修订不能复用旧Evidence。

### Supporting Observation

1. 新增Supporting Observation Bundle Schema。每个observation保存Metric、Unit、Estimator、实现版本、精确输入、状态、值、原因码、执行hash和来源Artifact hash。
2. Bundle强绑定Evidence Scope hash、Policy bundle hash和Evaluator build hash。
3. Evaluator从Metric Catalog重新解析Estimator并在Registry中重新执行；调用方提交的值、状态、实现版本、原因或执行hash任一不一致都会使整个Bundle无效。
4. 所有来源hash必须属于当前Evidence的受信Artifact集合。
5. 原`supporting_observations`自由映射接口不再获得生产信任；即使参数仍为兼容而存在，只要传入就返回`RAW_SUPPORTING_OBSERVATIONS_FORBIDDEN`。
6. GateEvidence必须同时冻结Supporting Bundle Schema ID、Bundle ID和Bundle hash；不用Bundle时三者必须全部为null。

## 不变量

- Recipe、Experiment和DeploymentLine不是可互换的对象。
- 实验成功结论不能掩盖超预算搜索、失败Trial删除或设计hash变化。
- AI ModelBundle不能挂到另一条DeploymentLine。
- Paper PASS不能复制为Canary PASS，Canary阶段不能跳跃。
- Supporting observation的自哈希或签名不能替代Estimator独立重算。
- 未实现Estimator仍然FAIL；将它放入签名Bundle不会使其可执行。
- 上述契约证明证据可信，不证明策略本身赚钱。

## 备选方案

- 让Experiment和Recipe完整hash相互引用：拒绝，存在不可求解循环。
- 只验证Experiment模板Schema：拒绝，模板允许大量null且明确未审批。
- 只在GateEvidence保存DeploymentLine ID：拒绝，无法证明阶段顺序、Recipe或活动Bundle。
- 继续信任自由supporting映射：拒绝，发布者可以构造有利动态阈值。
- Bundle签名后不再执行Estimator：拒绝，签名只能证明来源，不能证明算法和值正确。

## 后果

- GateEvidence现在具备Recipe、Experiment、DeploymentLine、ModelBundle和Supporting Observation的明确对象边界与交叉引用。
- Evaluator build绑定三份新Schema和验证源码，任何语义改动都会产生新build hash。
- 当前仓库只有测试Fixture，没有获批的真实ExperimentManifest或DeploymentLine；外部ED25519 Trust Store仍未接入。
- 53个Estimator仍不可执行，所以多数经济、稳健性和AI supporting metrics继续Fail-Closed。
- 下一步优先实现扣除全部成本后的经济PnL、现金流调整权益、回撤与风险暴露Estimator。

## 验证证据

- Artifact验证：`src/crypto_quant/release_artifacts.py`
- GateEvidence集成：`src/crypto_quant/release.py`
- Experiment Schema：`config/experiment-manifest-v1.1.schema.json`
- DeploymentLine Schema：`config/deployment-line-v1.1.schema.json`
- Supporting Bundle Schema：`config/supporting-observation-bundle-v1.schema.json`
- 正反、篡改和独立重算测试：`tests/test_evidence.py`
