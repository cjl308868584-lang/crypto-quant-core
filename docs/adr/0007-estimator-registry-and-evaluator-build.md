# ADR-0007：Estimator Registry与Evaluator Build信任边界

状态：Accepted
日期：2026-07-26

## 背景

v0.6.0能够从ReleaseGatePolicy和Metric Catalog解析Gate，但Catalog中的`estimator_id`仍只是声明。若Evaluator直接信任Evidence提交的`metric_value`，发布者可以提交一个形式合法但未经相同算法重算的PASS；若把尚未实现的统计方法假装成可执行，AI路线会在没有可复现实证的情况下获得资金权限。

此外，Policy要求绑定`evaluator_build_hash`，但此前没有明确哪些源码、Schema、政策和算法向量属于同一个Evaluator构建，也无法识别“政策未变但执行代码已变”的情况。

## 决策

1. 新增版本化Estimator Registry。静态白名单只允许调用仓库内显式登记的确定性函数，不支持模块名、函数名或表达式的动态执行。
2. Registry采用Catalog补集语义：Catalog中的每个算法要么有可执行实现，要么显式归入`UNAVAILABLE`；未知算法和未实现算法均Fail-Closed，但使用不同原因码。
3. v0.7.0只登记具备完整输入契约的4个资本Estimator；其余53个算法不推测实现，不用占位值产生PASS。
4. 每个可执行Estimator必须列出精确输入字段和Golden vector ID。缺少字段、额外字段、二进制浮点、负资本、未验证快照或未知比较方式均Fail-Closed。
5. Golden vector bundle通过Schema、自哈希、Registry hash和双向覆盖校验；加载Registry时必须执行全部向量。
6. GateEvidence的`metric_value`只作为声明。Evaluator从受信Evidence字段构造Estimator输入，执行登记实现，并使用计算值评估Gate；声明值与计算值不一致会使Evidence无效。
7. 每次Estimator执行产生规范化`execution_hash`并进入Evidence validation hash，保证同一输入、实现和原因码得到相同审计标识。
8. Evaluator Build Manifest绑定全部`src/crypto_quant/*.py`、发布相关冻结配置、Schema、`pyproject.toml`和`requirements.lock`的原始SHA-256，并对文件映射再计算规范化树hash。
9. Manifest同时绑定Catalog、Registry、Golden bundle、Golden report、版本和覆盖数量；任一文件、数量、hash或能力声明不一致时加载失败。
10. Build Manifest当前是`BUILD_CANDIDATE`。生成真实hash不等于获得生产批准；激活Policy仍需外部审批后把该hash写入必需binding。

## 不变量

- Catalog中存在算法ID不等于该算法已经实现。
- Evidence自报值不能替代Evaluator独立执行。
- 未实现Estimator不得返回PASS或INCONCLUSIVE，必须返回FAIL。
- 二进制浮点不得进入资本业务计算。
- 改动任一Evaluator构建输入必须产生新的build hash。
- Golden vector全部通过不证明策略赚钱；它只证明指定算法在指定输入上的可复现行为。
- AI路线不能因模型预测分数较高而绕过经济收益、风险、成本、样本和资本门槛。

## 备选方案

- 直接信任Evidence里的Estimator ID和值：拒绝，无法证明使用了Catalog指定算法。
- 一次性实现全部57个算法：拒绝，统计定义、输入Artifact和样本政策尚未完全可执行，快速占位会制造虚假安全感。
- 允许动态导入Registry声明的函数：拒绝，配置篡改可能扩大执行面。
- 只对Python源码做hash：拒绝，Schema、政策、Catalog和依赖变化同样会改变评估语义。
- 将测试文件纳入生产build hash：暂不采用；测试通过Golden report和CI形成验证证据，生产运行语义由包源码与冻结配置绑定。

## 后果

- 资本门槛已有从Evidence字段到独立Estimator、Gate结果和验证hash的完整确定性链。
- 任一被绑定源码或冻结配置被修改，旧Manifest会立即失效。
- 53个统计、经济、稳健性、AI与治理Estimator仍明确不可执行；涉及它们的GateEvidence不能获得有效PASS。
- 当前Policy仍为`DESIGN_BASELINE`且生产激活关闭，因此v0.7.0不允许真实资金上线。
- 后续应按赚钱目标的因果顺序实现Estimator：先实现扣全成本经济收益和风险，再实现样本/Bootstrap稳健性，最后实现AI相对简单基线的增量价值。

## 验证证据

- Registry执行：`src/crypto_quant/estimators.py`
- Evaluator构建校验：`src/crypto_quant/build.py`
- GateEvidence集成：`src/crypto_quant/release.py`
- Registry与Golden向量：`config/estimator-registry-v1.json`、`config/estimator-golden-vectors-v1.json`
- 构建清单：`config/evaluator-build-manifest-v1.json`
- 防篡改与确定性测试：`tests/test_estimators.py`、`tests/test_evidence.py`
