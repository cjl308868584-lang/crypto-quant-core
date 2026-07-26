# ADR-0005：受限表达式、证据作用域与四态发布求值

状态：Accepted
日期：2026-07-26

## 背景

ReleaseGatePolicy包含140个字面阈值Gate、3个外部政策阈值引用、5个内联AST和1个AST引用。仅支持字面阈值会让实际功效、特征复杂度、AI收益非劣、Canary可交易机会和资本充足性等硬门无法正式求值。若使用Python `eval`、二进制浮点或Scope子集匹配，又会引入代码执行、精度漂移及跨阶段复用证据的风险。

## 决策

1. `RELEASE_EXPR_AST_V1`只接受Policy Schema声明的结构化节点，禁止自由文本表达式及运行时代码求值。
2. 运算符白名单固定为`ADD`、`SUBTRACT`、`MULTIPLY`、`DIVIDE`、`ABS`、`MIN`、`MAX`和`FLOOR`。
3. 表达式内部使用由Canonical Decimal精确转换的有理数运算，避免依赖进程级Decimal Context或二进制浮点。
4. 正式阈值快照必须能无损表示为有限Canonical Decimal；无限循环小数结果Fail-Closed。
5. 除零按ReleaseGatePolicy返回`INCONCLUSIVE`；未知节点、未知引用、缺失指标、非数值引用、非法arity、循环引用、深度或节点预算超限均返回FAIL。
6. `metric_ref`只能解析Metric Catalog中的数值指标；`expression_ref`和`threshold_ast_ref`只能解析Policy内白名单路径。
7. `threshold_reference`只解析Policy声明的binding及RFC 6901 JSON Pointer模板；缺binding、缺模板变量或路径不存在均FAIL。
8. Gate条件字段缺失返回FAIL，条件为假返回`NOT_APPLICABLE`，样本不足返回`INCONCLUSIVE`。
9. 门组保留每个子Gate结果及其确定性hash。任一required Gate为FAIL则门组FAIL；否则任一为INCONCLUSIVE则门组INCONCLUSIVE；全部required Gate均不适用才为NOT_APPLICABLE；其余为PASS。
10. GateEvidence Scope从Policy必需维度提取，并补充Catalog、Policy版本、Schema、资本、Policy binding hash及AI/Canary/回退条件维度。
11. Scope比较使用完整键集合和值的规范化hash，不接受子集匹配。stage、direction、venue、资本或任一Policy hash不同都不能复用。
12. Release Audit和Forward Gate选择直接来自机器Policy矩阵，不在应用代码中另建一份手工规则。

## 不变量

- 任何自由文本公式、未知operator或浮点输入都不能进入正式比较。
- 同一AST、指标、上下文和Scope重复求值必须产生同一结果与业务hash。
- `CANARY_25`证据不能用于`CANARY_50`，LONG不能用于SHORT，资本或Policy hash不同不能复用。
- `BASELINE_ONLY`审计不选择AI门；`AI_ENHANCED`必须保留BASELINE、AI和PAIRED三类账本角色。
- 子Gate的FAIL或INCONCLUSIVE不能被上游`all_checks_pass=true`之类布尔值覆盖。
- 当前Policy仍为`DESIGN_BASELINE`且生产开关关闭；求值器能力增加不等于批准生产交易。

## 备选方案

- 使用Python `eval`或字符串公式：拒绝，无法安全限制代码执行及运算语义。
- 使用`float`：拒绝，边界比较和跨运行时hash不可复现。
- 依赖全局Decimal Context：拒绝，调用方可改变精度，除法结果可能随进程状态变化。
- 只比较Scope子集：拒绝，会允许跨阶段、方向、资本或Policy版本复用历史PASS。
- 门组只保存最终布尔值：拒绝，无法审计哪个子Gate阻断，也无法正确传播INCONCLUSIVE和NOT_APPLICABLE。

## 后果

- v0.5.0可离线求值Policy中全部9个非字面阈值Gate，并覆盖边界内外测试。
- 门组结果与逐Gate hash可作为后续GateEvidence信封验证的计算内核。
- 本版尚未验证签名、freeze proof、Artifact内容hash与Evidence自报hash；这些仍是正式发布前的硬阻断项。
- 外部binding document必须由后续冻结Policy Bundle加载器提供，本版不会把未审批模板自动提升为binding。

## 验证证据

- Policy加载、AST、Scope和聚合：`src/crypto_quant/release.py`
- 9个动态阈值正反边界、除零、自由文本、Scope和100次确定性测试：`tests/test_release.py`
- 权威Policy：`config/release-gates-v1.1.json`
- GateEvidence Schema：`config/release-evidence-v1.1.schema.json`
