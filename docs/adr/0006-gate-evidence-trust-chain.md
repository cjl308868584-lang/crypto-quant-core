# ADR-0006：GateEvidence信任链与独立重算

状态：Accepted
日期：2026-07-26

## 背景

v0.5.0已经能够确定性计算Gate和门组，但调用方仍可能提交错误的Gate ID、Metric、Estimator、Unit、阈值快照、结果或Scope。GateEvidence还包含RecipeRelease、ModelBundle、Policy binding、冻结证明、签名摘要和首次结果揭晓证明；只检查字段存在或只比较其中两个hash，无法阻止替换Artifact、拼接其他对象的合法签名或在看到结果后补签。

## 决策

1. GateEvidence业务hash固定为对完整信封移除`evidence_hash`字段后执行规范化SHA-256；其他字段均参与hash。
2. Evaluator不信任Evidence自报的Gate结果、阈值、Metric Unit或Estimator，全部从ReleaseGatePolicy和Metric Catalog独立解析并重算。
3. Evidence Schema、Gate Group、Gate ID、Metric ID、Comparator、Policy ID/Version、Catalog ID、Unit和Estimator任一不一致均使信封无效。
4. 每条required Gate必须有且仅有一个信封；缺失、重复、未知或无效信封使生产门组FAIL。
5. `policy_binding_hashes`必须与当前Evaluator内置Artifact、外部resolver结果和`frozen_release_inputs`中的Artifact hash三方完全一致；`policy_bundle_hash`固定为当前ReleaseGatePolicy内容hash与完整适用binding hash映射的规范化组合hash。
6. Binding ID必须与激活Policy中配置的ID一致，且freeze proof的`artifact_id`必须与resolver返回的ID一致。
7. 信任接口保存成对验证结果，而不是无上下文的摘要集合：
   - `signature_hash → freeze_evidence_hash`；
   - `freeze_evidence_hash → artifact_hash`；
   - `reveal_event_id → reveal_evidence_hash`；
   - Artifact签名或attestation → Artifact self hash。
8. 所有freeze proof必须早于首次结果揭晓；时间相等但缺少可证明事件顺序时Fail-Closed。
9. Evidence计算时间不得早于结果揭晓；评估窗口必须严格递增；有效样本数不得超过原始样本数。
10. RecipeRelease、ModelBundle和Approved Fallback Registry使用去除self-hash及签名字段后的规范化内容hash，并通过各自Schema与跨Artifact引用。
11. RecipeRelease必须绑定route、kind、endpoint、direction、venue、Policy hash、ExperimentManifest hash及Policy Bundle；AI Evidence还必须绑定ModelBundle、DeploymentLine和Model签名。
12. 三个资本值必须与已解析资本计划完全一致，且资本计划Artifact hash必须出现在Evidence的`artifact_hashes`。
13. `fallback_activation_requested=false`不产生任何回退资格；true时必须验证Registry/Record Schema、自哈希、签名、状态、有效期、来源Scope、最大Stage、Policy hash和Champion/LKG资格。
14. 生产门组入口始终叠加Policy Readiness。即使每条Evidence内部有效，只要Policy未激活或存在缺失binding，最终仍为FAIL。

## 不变量

- “字段里有signature hash”不等于签名已验证。
- 其他Artifact的合法签名不能拼接到当前freeze proof。
- Evidence自报PASS不能覆盖独立重算的FAIL或INCONCLUSIVE。
- 一个Gate的Evidence不能替代同组另一个Gate。
- Recipe、Model、DeploymentLine、route、endpoint、direction或venue不一致时AI Evidence无效。
- 过期、非APPROVED、来源Scope不符、超过批准Stage或目标不是Champion/LKG的fallback不能激活。
- 当前`DESIGN_BASELINE`仍不能产生生产PASS。

## 备选方案

- 只运行JSON Schema：拒绝，Schema不能证明hash、签名、冻结顺序或自报结果正确。
- 把所有“已验证签名”放在一个set中：拒绝，无法证明签名对应当前freeze evidence和Artifact。
- 信任Evidence中的阈值和结果：拒绝，发布者可以提交与Policy不同的快照。
- fallback只检查`status=APPROVED`：拒绝，不能防止过期、Scope替换、Stage越权或Candidate回退。
- 在没有公钥和Trust Store时假装完成ED25519验证：拒绝，生产安全边界必须明确由外部Verifier提供。

## 后果

- v0.6.0具备GateEvidence信封到生产门组结果的Fail-Closed验证协议。
- RecipeRelease、ModelBundle和Fallback Registry可验证Schema、自哈希、签名验证结果及关键交叉引用。
- 真正的ED25519实现、公钥轮换、Trust Store和外部Artifact resolver尚未接入；缺少其成对验证结果时Evidence必FAIL。
- ExperimentManifest和DeploymentLine仍缺少独立生产Schema；统计Metric仍由调用方提供，尚未由Estimator Registry计算。

## 验证证据

- 信封hash与信任上下文：`src/crypto_quant/evidence.py`
- GateEvidence独立重算及跨Artifact验证：`src/crypto_quant/release.py`
- 基线、AI、Fallback、冻结、Scope、hash与100次确定性测试：`tests/test_evidence.py`
- GateEvidence Schema：`config/release-evidence-v1.1.schema.json`
- Recipe/Model/Fallback Schema：`config/recipe-release-v1.1.schema.json`、`config/model-bundle-v1.1.schema.json`、`config/approved-fallback-registry-v1.1.schema.json`
