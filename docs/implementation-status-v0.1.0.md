# 实施追踪 v0.1.0

状态：Phase 0首个增量
权威范围：[开发路线与验收门槛 v1.1，第9节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已经有实现和自动化证据的内容。“部分完成”不能被解释为满足阶段退出条件。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python包、测试和CI骨架 | 完成 | `pyproject.toml`、`Makefile`、`.github/workflows/ci.yml` | `make test` |
| 2. 通用事件信封及核心契约 | 部分完成 | `contracts.py`已有EventEnvelope、MetaDecision、TargetPosition、PortfolioRiskSnapshot | `test_contracts.py`；StrategyProposal、RiskDecision、Intent/Attempt待补 |
| 3. Decimal/tick/step值对象 | 完成首版 | `canonical.py`、`decimal_math.py` | `test_canonical.py` |
| 4. SQLite WAL、Outbox、成本/现金流和最小投影 | 完成首版 | `ledger.py` | 幂等、不可变、哈希链、Outbox、投影从零重建测试 |
| 5. RiskLock、Stage上限、回撤状态 | 部分完成 | `risk.py`已从机器政策加载10/12/15/20%回撤档位并限制目标 | `test_risk.py`；RiskLock与Deployment Registry待补 |
| 6. Target supersession、Intent、Attempt状态 | 未开始 | 无 | 下一增量 |
| 7. InstrumentMetadata及舍入性质 | 部分完成 | 已有通用tick/step函数 | Binance元数据契约和性质测试待补 |
| 8. 事件重放Golden Test | 完成最小版 | `EventLedger.rebuild_projections()` | `test_append_is_idempotent_and_projections_are_exactly_once` |
| 9. ADR及政策/事故模板 | 部分完成 | `docs/adr/` | 政策与事故模板待补 |
| 10. Schema验证和确定性Evaluator | 部分完成 | `release.py`、`validate_release_config.py` | 6 Schema、149 Gate交叉引用、重复100次同hash、缺binding必FAIL |

## 当前强制边界

- 没有Broker类、交易所Adapter、API密钥字段或下单方法。
- 当前政策仍为`DESIGN_BASELINE`，且`production_activation.enabled=false`。
- Accounting、CostAllocation、DataQuality、Split、StatisticalDesign、ForwardControl、Compliance和Evaluator build仍未绑定，因此生产Readiness固定为FAIL。
- Evaluator只实现literal threshold；AST、动态引用和boundary求值尚未完成时一律FAIL，不使用近似值放行。
- Python依赖已锁定于`requirements.lock`，许可证复核记录见`dependencies-and-licenses-v0.1.0.md`。

## 下一增量

1. 补齐StrategyProposal、RiskDecision、ExecutionIntent和ChildOrderAttempt。
2. 实现Target supersession及UNKNOWN订单状态机。
3. 补齐RiskLock与Deployment Registry权威Stage multiplier。
4. 增加Binance InstrumentMetadata样例和风险更小方向的舍入性质测试。
5. 建立DataQuality、Split、StatisticalDesign、Accounting、CostAllocation、ForwardControl及事故模板，但继续保持未绑定状态。
