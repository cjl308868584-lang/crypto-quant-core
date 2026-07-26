# 实施追踪 v0.2.0

状态：Phase 0第二个增量
权威范围：[开发路线与验收门槛 v1.1，第9节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已经有实现和自动化证据的内容。“部分完成”不能被解释为满足阶段退出条件。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python包、测试和CI骨架 | 完成 | `pyproject.toml`、`Makefile`、`.github/workflows/ci.yml` | `make test` |
| 2. 通用事件信封及核心契约 | 完成首版 | `contracts.py`已覆盖EventEnvelope、StrategyProposal、MetaDecision、TargetPosition、PortfolioRiskSnapshot；`execution.py`已覆盖RiskDecision、Intent、Attempt | 确定性ID、null/zero、lineage和风险上限测试 |
| 3. Decimal/tick/step值对象 | 完成首版 | `canonical.py`、`decimal_math.py` | `test_canonical.py` |
| 4. SQLite WAL、Outbox、成本/现金流和最小投影 | 完成首版 | `ledger.py` | 幂等、不可变、哈希链、Outbox、投影从零重建测试 |
| 5. RiskLock、Stage上限、回撤状态 | 完成领域首版 | `risk.py`、`execution.py` | 回撤10/12/15/20%、Stage multiplier、资本门槛、UNKNOWN与1x最坏毛杠杆测试；持久化投影待补 |
| 6. Target supersession、Intent、Attempt状态 | 完成首版 | `TargetBook`、`ProposalBook`、`AttemptBook`、`PositionExecutor` | 跨现货/永续经济标的序列、盲重试阻断、反向先平仓测试 |
| 7. InstrumentMetadata及舍入性质 | 部分完成 | 已有通用tick/step函数；Intent携带metadata version | Binance元数据契约、min notional及风险更小方向舍入性质待补 |
| 8. 事件重放Golden Test | 完成最小版 | `EventLedger.rebuild_projections()` | `test_append_is_idempotent_and_projections_are_exactly_once`；执行投影接入待补 |
| 9. ADR及政策/事故模板 | 部分完成 | `docs/adr/0001-*`、`docs/adr/0002-*` | 政策与事故模板待补 |
| 10. Schema验证和确定性Evaluator | 部分完成 | `release.py`、`validate_release_config.py` | 6 Schema、149 Gate交叉引用、重复100次同hash、缺binding必FAIL |

## v0.2.0新增的强制边界

- Proposal、Meta、Target、Risk、Intent均有确定性业务ID/哈希和显式lineage检查。
- Target按账户和ETH经济标的维护唯一序列；从现货LONG切换永续SHORT也必须显式supersede。
- 部署Stage multiplier、批准资本和venue均来自有效DeploymentRegistryRecord。
- RiskLock必须始终允许保护性`REDUCE_ONLY`和`FLATTEN`。
- 活动订单最大潜在成交计入1x上限；对账不干净、ORDER_UNKNOWN或当前最坏杠杆超限时冻结新增。
- Intent名义金额不得超过RiskDecision批准金额；Attempt不得超过已对账剩余Intent。
- Fill-before-ACK、Cancel/Fill竞态、累计成交单调性和全部UNKNOWN对账结果已有状态机测试。
- PositionExecutor在UNKNOWN时阻断；反向前必须等待交易所确认实际仓位为零。

## 仍然Fail-Closed

- 没有Broker类、交易所Adapter、API密钥字段或下单方法。
- 当前政策仍为`DESIGN_BASELINE`，且`production_activation.enabled=false`。
- Accounting、CostAllocation、DataQuality、Split、StatisticalDesign、ForwardControl、Compliance和Evaluator build仍未绑定，因此生产Readiness固定为FAIL。
- 执行状态机尚未接入持久化投影，不能对外部交易所产生副作用。
- AI训练、ModelBundle批准和AI_ENHANCED发布路线尚未开始；当前实现只保证未来AI不能绕过确定性风控。

## 下一增量

1. 实现Binance `InstrumentMetadata`快照、版本化、tick/step/min-notional约束和风险更小方向舍入性质测试。
2. 将RiskLock、DeploymentRegistry、订单和PositionExecutor投影接入追加账本并增加重放Golden Test。
3. 建立DataQuality、Split、StatisticalDesign、Accounting、CostAllocation、ForwardControl与事故政策模板，继续保持未绑定。
4. 完成Evaluator AST与动态引用支持，未知表达式仍Fail-Closed。
