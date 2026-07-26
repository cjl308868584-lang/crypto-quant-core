# 实施追踪 v0.4.0

状态：Phase 0第四个增量
权威范围：[开发路线与验收门槛 v1.1，第9节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已经有实现和自动化证据的内容。“完成首版”不能被解释为生产批准。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python包、测试和CI骨架 | 完成 | `pyproject.toml`、`Makefile`、`.github/workflows/ci.yml` | `make test` |
| 2. 通用事件信封及核心契约 | 完成首版 | `contracts.py`、`execution.py` | 确定性ID、null/zero、lineage和风险上限测试 |
| 3. Decimal/tick/step值对象 | 完成首版 | `canonical.py`、`decimal_math.py` | Decimal边界和舍入测试 |
| 4. SQLite WAL、Outbox、成本/现金流和最小投影 | 完成首版 | `ledger.py` | 幂等、不可变、哈希链、Outbox、投影从零重建 |
| 5. RiskLock、Stage上限、回撤状态 | 完成领域首版 | `risk.py`、`execution.py` | 回撤10/12/15/20%、Stage、资本、UNKNOWN与1x最坏毛杠杆测试 |
| 6. Target supersession、Intent、Attempt状态 | 完成首版 | `execution.py`、`orders.py` | 跨载体Target序列、盲重试阻断、反向先平仓 |
| 7. InstrumentMetadata及舍入性质 | 完成首版 | `instruments.py`、离线Binance Fixture | 1,000组不放大性质测试、min-notional NO_TRADE、历史版本选择 |
| 8. 事件重放Golden Test | 完成Phase 0首版 | v1.1全部命名投影、Checkpoint、`projection_hash()` | trade ID幂等、迟到版本、冲突回滚、篡改检测、从零重放 |
| 9. ADR及政策/事故模板 | 完成模板首版 | ADR-0001至ADR-0004、治理Schema和8份JSON模板 | 正反Schema、固定边界、重复键、未审批语义测试 |
| 10. Schema验证和确定性Evaluator | 部分完成 | `release.py`、两套validate脚本 | 原6 Schema、治理Schema、149 Gate、确定性hash、缺binding必FAIL；安全AST/动态引用待补 |

## v0.4.0新增证据

- 8份治理模板逐一覆盖Experiment、DataQuality、Split、StatisticalDesign、Accounting、CostAllocation、ForwardControl和Incident Report。
- 所有模板均无artifact ID、批准人、批准时间、content hash或审批证据，并明确禁止生产使用。
- 模板Bundle Hash冻结为自动化Golden值；缺字段、重复JSON键或改变关键边界均失败。
- 模板存在后，DataQuality/Split/Statistical/Accounting/Cost/Forward六个Release binding仍保持缺失。
- Fill按账户、市场Scope和exchange trade ID去重；相同trade ID冲突使事件回滚。
- Balance、ProtectiveOrder进入版本化投影；保护不足或载体错误Fail-Closed。
- Checkpoint绑定事件链和完整状态投影，未对账Fill或保护不足时拒绝建立。
- Golden Replay覆盖Intent、Attempt、Order、Fill、Position、Balance、RiskLock、Deployment、ProtectiveOrder、Executor和Checkpoint。

## 仍然Fail-Closed

- 没有Broker、交易所Adapter、API密钥字段、网络请求或真实下单方法。
- 治理文件是模板，不是已批准Policy；不得写入ReleaseGatePolicy binding。
- 当前政策仍为`DESIGN_BASELINE`，且`production_activation.enabled=false`。
- Accounting、CostAllocation、DataQuality、Split、StatisticalDesign、ForwardControl、Compliance和Evaluator build仍未绑定，因此生产Readiness固定为FAIL。
- Evaluator尚未支持受限AST、动态threshold/expression引用、完整Evidence Scope及全部Gate聚合。
- AI训练、ModelBundle审批和AI_ENHANCED发布路线尚未开始。

## 下一增量

1. 实现Release Evaluator受限AST、白名单动态引用和Decimal运算。
2. 实现完整GateEvidence Scope精确匹配、条件聚合和INCONCLUSIVE传播。
3. 增加Policy中全部非literal threshold的正反边界测试。
4. 只有Evaluator覆盖率、build hash和Phase 0验收全部有证据后，才开始权威只读市场数据采集。
