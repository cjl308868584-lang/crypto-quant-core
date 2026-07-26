# ADR-0012：删除最大正增量后的完整 Endpoint 复评

状态：Accepted
日期：2026-07-27

## 背景

v0.11.0已经能计算AI相对简单基线的配对经济增量，并能对一个统计序列执行删除最大正fold或事件后的下置信界估计。但“删样本后的单个统计量仍为正”不等于所选AI主终点仍然合格。

一个endpoint可能同时包含收益非劣、回撤改善、ES95改善或其他门槛。如果只重算其中一个指标，AI仍可能靠被删除单元所贡献的另一项指标通过，形成不完整的稳健性结论。

## 决策

新增不可变的`EndpointReevaluationSnapshot v1`和两个确定性Estimator：

- `LEAVE_MAX_POSITIVE_DELTA_FOLD_OUT_ENDPOINT_REEVALUATION_V1`
- `LEAVE_MAX_POSITIVE_DELTA_EVENT_OUT_ENDPOINT_REEVALUATION_V1`

复评过程固定为：

1. 只使用原始配对Artifact中`eligible=true`的AI改变行为时点。
2. 离线阶段按fold汇总`AI - baseline`经济贡献；只选择最大正贡献fold，贡献相同按`fold_id`升序。
3. 审计阶段按单个配对事件的`AI - baseline`贡献排序；贡献相同按`proposal_id + decision_time`升序。
4. 从BASELINE和AI来源序列同时删除被选中的pair，而不是直接修改delta数组。
5. 重算两个来源序列hash，重新执行proposal/time配对，并重算配对Artifact hash。
6. 从冻结的ReleaseGatePolicy解析所选endpoint的完整required gate集合。
7. 独立执行每一个可执行门，并以“所有适用required gate均PASS”作为唯一true条件。
8. 样本不足返回`INCONCLUSIVE`；Artifact、来源、政策或门定义不一致返回`FAIL`。两者均不能映射为true。

当前只对`GROWTH` endpoint形成可执行闭环。`RISK_EFFICIENCY`需要配对最大回撤和ES95区间，因此继续失败封闭。

## Artifact边界

`EndpointReevaluationSnapshot`保存：

- ReleaseGatePolicy和Metric Catalog的精确版本；
- endpoint及完整门定义；
- 排除方法、排除单元和重算贡献；
- 原配对序列hash及重建后配对序列hash；
- 每个已计算门的观察值、门槛、结果及结果hash；
- 总体`PASS`、`FAIL`或`INCONCLUSIVE`及Artifact自hash。

原配对序列作为独立冻结Artifact传入Estimator，不在复评Artifact内复制。这样避免同一事实存在两个可漂移副本。

GateEvidence必须同时冻结并绑定：

- `statistical_series_snapshot`
- `endpoint_reevaluation_snapshot`
- 两个来源arm序列hash
- 全部经济来源hash
- 重建后配对序列hash

Supporting Observation也必须列出复评Artifact、原配对序列和重建序列的来源hash。

## 对赚钱目标的意义

该门回答的不是“删掉最好的一组数据后平均值是否还好看”，而是：

> 在去掉最可能承载偶然优势的fold或审计事件后，AI所选择的完整经济目标是否仍满足所有冻结门槛？

它降低了单一行情阶段、单一事件或研究者选择性报告制造虚假AI盈利优势的概率，但仍不构成真实盈利证明。

## 后果

- Catalog中两个endpoint复评算法从不可执行变为可执行。
- Estimator Registry由18个增加到20个；不可执行项由39个降至37个。
- Golden vectors由27个增加到29个。
- 合成Golden样本在删除集中贡献后因区块不足返回`INCONCLUSIVE`，明确证明不足样本不会变成PASS。
- 单元测试另用满足最小区块数的派生样本验证`PASS`和`FAIL`边界。
- 真实数据、路径依赖逐交易重放、Holm、实际功效、CI宽度和风险效率区间仍未完成。

## 验证

- Artifact构造、重放及反篡改：`tests/test_endpoint_reevaluation.py`
- Registry与Golden：`tests/test_estimators.py`
- 配对来源语义：`tests/test_paired_statistics.py`
- Evidence来源绑定：`PolicyBundle._endpoint_reevaluation_reference_reasons()`
