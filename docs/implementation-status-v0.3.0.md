# 实施追踪 v0.3.0

状态：Phase 0第三个增量
权威范围：[开发路线与验收门槛 v1.1，第9节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已经有实现和自动化证据的内容。“部分完成”不能被解释为满足阶段退出条件。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python包、测试和CI骨架 | 完成 | `pyproject.toml`、`Makefile`、`.github/workflows/ci.yml` | `make test` |
| 2. 通用事件信封及核心契约 | 完成首版 | `contracts.py`、`execution.py` | 确定性ID、null/zero、lineage和风险上限测试 |
| 3. Decimal/tick/step值对象 | 完成首版 | `canonical.py`、`decimal_math.py` | Decimal边界和舍入测试 |
| 4. SQLite WAL、Outbox、成本/现金流和最小投影 | 完成首版 | `ledger.py` | 幂等、不可变、哈希链、Outbox、投影从零重建 |
| 5. RiskLock、Stage上限、回撤状态 | 完成领域首版 | `risk.py`、`execution.py` | 回撤10/12/15/20%、Stage、资本、UNKNOWN与1x最坏毛杠杆测试 |
| 6. Target supersession、Intent、Attempt状态 | 完成首版 | `execution.py`、`orders.py` | 跨载体Target序列、盲重试阻断、反向先平仓 |
| 7. InstrumentMetadata及舍入性质 | 完成首版 | `instruments.py`、离线Binance Fixture | 1,000组数量/名义金额不放大性质测试、min-notional NO_TRADE、历史版本选择 |
| 8. 事件重放Golden Test | 完成Phase 0首版 | 7类执行投影、`projection_hash()`、`rebuild_projections()` | 冻结Golden Hash、迟到版本、同版本冲突回滚、篡改检测与修复 |
| 9. ADR及政策/事故模板 | 部分完成 | ADR-0001至ADR-0003 | Experiment及7类政策/事故模板待补 |
| 10. Schema验证和确定性Evaluator | 部分完成 | `release.py`、`validate_release_config.py` | 6 Schema、149 Gate交叉引用、确定性hash、缺binding必FAIL；AST/动态引用待补 |

## v0.3.0新增证据

- InstrumentMetadata的有效区间、能力、费用、tick、step、min/max quantity、min notional及contract multiplier均进入确定性hash。
- Catalog拒绝有效期重叠并可按历史决策时间恢复唯一版本。
- 离线Binance输入样例明确声明非权威，不能误用为实时交易规格。
- 新增风险订单在价格取整后重新裁剪数量，最终名义金额不超过批准值。
- 保护性残余低于min notional时标记NO_TRADE与dust，不向上放大、不无限追单。
- Intent、Attempt、Order、Position、RiskLock、Deployment及Executor投影能够从事件账本完整重建。
- 迟到旧版本不回滚投影；同版本内容冲突使事件和投影同时回滚。
- 执行投影被篡改时完整性校验失败；重建恢复冻结Golden Hash。

## 仍然Fail-Closed

- 没有Broker、交易所Adapter、API密钥字段、网络请求或真实下单方法。
- Binance metadata只是测试Fixture，不代表2026年或任何时点的交易所实际规格。
- 当前政策仍为`DESIGN_BASELINE`，且`production_activation.enabled=false`。
- Accounting、CostAllocation、DataQuality、Split、StatisticalDesign、ForwardControl、Compliance和Evaluator build仍未绑定，因此生产Readiness固定为FAIL。
- `fills_projection`、`balances_projection`、`protective_orders_projection`和`checkpoints`尚未实现。
- AI训练、ModelBundle审批和AI_ENHANCED发布路线尚未开始。

## 下一增量

1. 建立ExperimentManifest、DataQualityPolicy、SplitPolicy、StatisticalDesignPolicy、AccountingPolicy、CostAllocationPolicy、ForwardControlPolicy和事故报告模板及Schema。
2. 补齐fills、balances、protective orders与checkpoints投影，并扩大Golden Replay。
3. 实现Evaluator安全AST与动态引用，未知表达式继续Fail-Closed。
4. Phase 0全部退出条件有证据后，才开始权威只读市场数据采集。
