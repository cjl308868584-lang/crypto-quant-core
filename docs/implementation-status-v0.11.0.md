# 实施追踪 v0.11.0

状态：Phase 0第十一个增量
权威范围：[开发路线与验收门槛 v1.1，第9节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已有实现和自动化证据。所有正收益Golden结果均为合成Fixture，不是策略或AI的真实盈利记录。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python包、测试和CI骨架 | 完成 | `pyproject.toml`、`Makefile`、CI | `make test`、`make validate` |
| 2. 核心决策链和双臂角色 | 完成配对角色首版 | `contracts.py`、`ledger.py`、`statistics.py` | AI路线独立BASELINE/AI账本测试 |
| 3. Decimal及统计确定性 | 完成配对扩展 | `canonical.py`、`statistics.py` | 固定50位context、SHA-256抽样和Golden vectors |
| 4. SQLite WAL、Outbox及经济投影 | 完成双臂来源首版 | `ledger.py`、`economics.py` | 两臂经济快照hash和Scope验证 |
| 5. 风控及绝对经济门 | 完成领域首版 | `risk.py`、`economics.py` | 两臂绝对门不能由delta替代 |
| 6. Target、Intent、Attempt和订单状态 | 完成首版 | `execution.py`、`orders.py` | 顺序、UNKNOWN和反向先平仓测试 |
| 7. InstrumentMetadata及舍入 | 完成首版 | `instruments.py` | 不放大性质和版本选择 |
| 8. 统计来源及配对重放 | 完成GROWTH配对首版 | `paired_ai_delta_series_snapshot()` | proposal/time重建、未配对报告及delta反篡改 |
| 9. ADR及治理模板 | 完成模板首版 | ADR-0001至ADR-0011、8份治理模板 | Schema与未审批语义测试 |
| 10. Schema及确定性Evaluator | 完成配对增量首版 | `statistics.py`、`estimators.py`、`release.py` | 149 Gate、18个Estimator、27个Golden vectors |

## v0.11.0新增证据

- `StatisticalSeriesSnapshot v1.1`新增配对AI经济log-growth delta类型。
- 配对Artifact内嵌BASELINE和AI来源序列，并绑定全部经济快照hash、ModelBundle、基线Recipe、Experiment、政策、资本和Bootstrap设计。
- 唯一连接键为`proposal_id + decision_time`；重复键失败，未配对键分别报告。
- 只有AI实际改变动作或绝对敞口的时点进入ESS和配对Bootstrap。
- delta由Evaluator重算为`AI值 - 基线值`，不能单独篡改。
- 实现一侧95%配对Moving-block Bootstrap。
- 实现删除最大正fold、前5个正事件和最大正事件后的MBB压力估计。
- 修正`top_5_positive_trades`错误映射到事件Estimator的问题；逐交易门继续Fail-Closed。
- AI路线现在允许独立`BASELINE_LEDGER`，并使用ExperimentManifest冻结的基线Recipe。
- GateEvidence和Supporting Observation必须包含配对Artifact、两条来源序列及所有经济来源hash。
- Estimator Registry由14个增加到18个；Golden vectors由22个增加到27个。

## 围绕赚钱目标的解释

本增量把AI价值判定改为：

```text
相同proposal + 相同decision_time
  → 相同窗口、资本、政策和成交条件
  → AI经济log-growth贡献 - 简单基线贡献
  → 只保留AI真实改变行为的时点
  → 依赖时间序列一侧95%配对下置信界
```

只有基线自身赚钱、AI臂自身赚钱，并且真实配对增量下界满足预先选择的endpoint门，AI才可能被视为有经济价值。Golden Fixture的`0.008`正下界只验证算法。

## 仍然Fail-Closed

- 没有真实、封存、获批的BASELINE/AI配对经济序列。
- 当前Policy仍为`DESIGN_BASELINE`，生产激活关闭，治理模板未审批。
- 配对leave-max-delta后的整个endpoint门组复评尚未实现。
- 逐交易top-5删除需要路径依赖账本重放，不能用事件删除近似。
- RISK_EFFICIENCY路线的最大回撤和ES95改善配对区间未实现。
- Holm多重检验、实际功效、CI宽度、DSR、PBO和校准区间未实现。
- 没有Broker、交易所Adapter、API密钥读取或真实下单能力。
- 因此当前不能声明AI优于简单基线，也不能投入真钱。

## 下一增量

1. 冻结完整endpoint reevaluation Artifact并实现paired leave-max-delta整组复评。
2. 实现路径依赖的逐交易top-5删除经济账本重放。
3. 实现双侧区间宽度、MERE实际功效和Holm family-wise校正。
4. 实现RISK_EFFICIENCY的配对最大回撤与ES95改善区间。
5. 在不接真实Broker的前提下建立离线双臂Paper数据生成管线。
