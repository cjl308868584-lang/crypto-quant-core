# 实施追踪 v0.12.0

状态：Phase 0第十二个增量
权威范围：[开发路线与验收门槛 v1.1，第9节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已有实现和自动化证据。所有正收益结果均来自合成Fixture，不是策略或AI的真实盈利记录。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python包、测试和CI骨架 | 完成 | `pyproject.toml`、`Makefile`、CI | `make test`、`make validate` |
| 2. 核心决策链和双臂角色 | 完成配对角色首版 | `contracts.py`、`ledger.py`、`statistics.py` | AI路线独立BASELINE/AI账本测试 |
| 3. Decimal及统计确定性 | 完成复评扩展 | `canonical.py`、`statistics.py`、`reevaluation.py` | 固定Decimal context、SHA-256抽样和Golden vectors |
| 4. SQLite WAL、Outbox及经济投影 | 完成双臂来源首版 | `ledger.py`、`economics.py` | 两臂经济快照hash和Scope验证 |
| 5. 风控及绝对经济门 | 完成领域首版 | `risk.py`、`economics.py` | 两臂绝对门不能由delta替代 |
| 6. Target、Intent、Attempt和订单状态 | 完成首版 | `execution.py`、`orders.py` | 顺序、UNKNOWN和反向先平仓测试 |
| 7. InstrumentMetadata及舍入 | 完成首版 | `instruments.py` | 不放大性质和版本选择 |
| 8. 统计来源及配对重放 | 完成GROWTH集中度复评首版 | `reevaluation.py` | 双臂删fold/event、重新配对、整组复评 |
| 9. ADR及治理模板 | 完成模板首版 | ADR-0001至ADR-0012、8份治理模板 | Schema与未审批语义测试 |
| 10. Schema及确定性Evaluator | 完成GROWTH复评首版 | `estimators.py`、`release.py` | 149 Gate、20个Estimator、29个Golden vectors |

## v0.12.0新增证据

- 新增`EndpointReevaluationSnapshot v1`。
- 删除最大正贡献fold时，按eligible配对delta聚合，稳定并列规则为`fold_id`。
- 删除最大正贡献审计事件时，稳定并列规则为`proposal_id + decision_time`。
- 排除操作同时作用于BASELINE和AI来源臂，再重算arm和paired Artifact，禁止直接改写delta。
- 从冻结ReleaseGatePolicy解析完整`AI_ENDPOINT.GROWTH`或`AUDIT_AI_ENDPOINT.GROWTH`门组。
- 只有全部适用required门PASS才输出true；FAIL和INCONCLUSIVE均不能晋级。
- GateEvidence必须冻结配对序列与复评Artifact，并绑定原始arm、经济来源和重建序列hash。
- Supporting Observation新增复评来源完整性验证。
- ReleaseGatePolicy升级至`1.1.4`，Metric Catalog升级至`1.1.3`。
- Estimator Registry由18个增加到20个；Golden vectors由27个增加到29个。

## 围绕赚钱目标的解释

本增量把集中度稳健性判断从：

```text
删掉最大贡献单元 → 看一个统计量
```

升级为：

```text
冻结双臂配对事实
  → 找出最大正贡献fold或事件
  → 从两臂同时删除
  → 重新生成paired经济序列
  → 重跑所选endpoint的完整门组
  → 全部required门通过才算稳健
```

这可以发现“AI收益主要由一个fold或一个事件支撑”的脆弱结果。Golden Fixture在删除后因有效区块不足返回`INCONCLUSIVE`，这是正确的失败封闭行为，不是盈利证据。

## 仍然Fail-Closed

- 没有真实、封存、获批的BASELINE/AI配对经济序列。
- 当前Policy仍为`DESIGN_BASELINE`，生产激活关闭，治理模板未审批。
- `RISK_EFFICIENCY`的配对最大回撤和ES95改善区间未实现，因此无法完成该endpoint整组复评。
- 逐交易top-5删除需要路径依赖账本重放，不能用事件删除近似。
- Holm多重检验、实际功效、CI宽度、DSR、PBO和校准区间未实现。
- 没有离线双臂Paper数据生成管线。
- 没有Broker、交易所Adapter、API密钥读取或真实下单能力。
- 因此当前不能声明AI优于简单基线，也不能投入真钱。

## 下一增量

1. 实现路径依赖的逐交易top-5删除经济账本重放。
2. 实现双侧区间宽度、MERE实际功效和Holm family-wise校正。
3. 实现`RISK_EFFICIENCY`的配对最大回撤与ES95改善区间。
4. 在不接真实Broker的前提下建立离线双臂Paper数据生成管线。
5. 用封存历史数据生成第一份非Golden的BASELINE/AI配对Evidence。
