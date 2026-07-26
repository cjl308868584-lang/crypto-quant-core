# 实施追踪 v0.5.0

状态：Phase 0第五个增量
权威范围：[开发路线与验收门槛 v1.1，第9节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已经有实现和自动化证据的内容。“领域首版”不能被解释为生产批准或收益证明。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python包、测试和CI骨架 | 完成 | `pyproject.toml`、`Makefile`、`.github/workflows/ci.yml` | `make test` |
| 2. 通用事件信封及核心契约 | 完成首版 | `contracts.py`、`execution.py` | 确定性ID、null/zero、lineage和风险上限测试 |
| 3. Decimal/tick/step值对象 | 完成首版 | `canonical.py`、`decimal_math.py` | Decimal边界和舍入测试 |
| 4. SQLite WAL、Outbox、成本/现金流和投影 | 完成Phase 0首版 | `ledger.py` | 幂等、不可变、哈希链、Outbox、完整命名投影重建 |
| 5. RiskLock、Stage上限、回撤状态 | 完成领域首版 | `risk.py`、`execution.py` | 回撤10/12/15/20%、Stage、资本、UNKNOWN与1x最坏毛杠杆测试 |
| 6. Target supersession、Intent、Attempt状态 | 完成首版 | `execution.py`、`orders.py` | 跨载体Target序列、盲重试阻断、反向先平仓 |
| 7. InstrumentMetadata及舍入性质 | 完成首版 | `instruments.py`、离线Binance Fixture | 1,000组不放大性质测试、min-notional NO_TRADE、历史版本选择 |
| 8. 事件重放Golden Test | 完成Phase 0首版 | 全部命名投影、Checkpoint、`projection_hash()` | trade ID幂等、冲突回滚、篡改检测、从零重放 |
| 9. ADR及政策/事故模板 | 完成模板首版 | ADR-0001至ADR-0005、治理Schema和8份JSON模板 | 正反Schema、固定边界、重复键、未审批语义测试 |
| 10. Schema验证和确定性Evaluator | 完成领域首版 | `release.py` | 6 Schema、149 Gate、受限AST、动态引用、精确Scope、四态聚合及确定性hash |

## v0.5.0新增证据

- 全量盘点149个Gate：140个字面阈值、3个外部Policy引用、5个内联AST和1个Policy内AST引用。
- Policy允许的8个运算符全部由结构化解释器实现；无`eval`、无自由文本执行、无二进制浮点。
- Decimal输入转换为精确有理数运算；有限十进制无损输出，循环小数Fail-Closed，除零返回INCONCLUSIVE。
- Metric、Attribute、Expression和外部JSON Pointer四类引用均有白名单、缺失和非法路径处理。
- Policy中9个非字面阈值Gate全部具有边界PASS及边界外FAIL测试。
- Evidence Scope保留Policy必需维度，并纳入Policy binding hash、资本、AI、Canary及回退条件维度。
- stage、direction、Policy Bundle hash和批准资本不同时，整组Gate均FAIL，不能复用证据。
- 门组聚合保留全部子结果，并正确传播FAIL、INCONCLUSIVE和NOT_APPLICABLE。
- Initial/Major Audit和各Forward stage直接从Policy选择route专属门组与账本角色。
- 同一Scope与指标连续求值100次，Gate及Group业务hash完全一致。

## 仍然Fail-Closed

- 没有Broker、交易所Adapter、API密钥字段、网络请求或真实下单方法。
- 治理文件仍是未审批模板，不是冻结Policy binding。
- 当前政策仍为`DESIGN_BASELINE`，且`production_activation.enabled=false`。
- Accounting、CostAllocation、DataQuality、Split、StatisticalDesign、ForwardControl、Compliance和Evaluator build仍未绑定，因此生产Readiness固定为FAIL。
- GateEvidence的签名、freeze proof、Artifact内容hash、Evidence自报hash和跨Artifact引用尚未完成端到端验证。
- 当前求值输入仍由调用方提供已计算Metric；Metric Catalog中的统计估计器尚未实现。
- AI训练、ModelBundle审批和AI_ENHANCED发布路线尚未开始。

## 下一增量

1. 实现完整GateEvidence信封验证：Gate/Metric/Estimator/Unit一致性、Evidence hash、Policy binding hash及冻结顺序。
2. 建立版本化Estimator Registry与Evaluator build manifest，并为已实现算法增加Golden vectors。
3. 补齐Phase 0的密钥/环境/账户隔离政策、适格性检查清单、机器风险政策和事故停机Runbook。
4. 只有Phase 0全部退出条件有证据后，才开始权威只读市场数据采集。
