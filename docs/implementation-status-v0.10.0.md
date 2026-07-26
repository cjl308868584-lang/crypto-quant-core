# 实施追踪 v0.10.0

状态：Phase 0第十个增量
权威范围：[开发路线与验收门槛 v1.1，第9节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已有实现和自动化证据。Golden Vector中的正下界是算法Fixture，不是本策略的真实盈利证据。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python包、测试和CI骨架 | 完成 | `pyproject.toml`、`Makefile`、`.github/workflows/ci.yml` | `make test`、`make validate` |
| 2. 通用事件信封及核心契约 | 完成首版 | `contracts.py`、`execution.py` | 确定性ID、lineage和风险上限测试 |
| 3. Decimal/tick/step值对象 | 完成统计上下文扩展 | `canonical.py`、`decimal_math.py`、`statistics.py` | 禁用float、固定50位统计上下文和跨context确定性 |
| 4. SQLite WAL、Outbox及经济投影 | 完成经济投影首版 | `ledger.py`、`economics.py` | 哈希链、经济快照、全成本PnL和重放 |
| 5. RiskLock、Stage、回撤和敞口 | 完成领域首版 | `risk.py`、`execution.py`、`economics.py` | 日损、回撤、UNKNOWN和最坏毛杠杆 |
| 6. Target、Intent、Attempt和订单状态 | 完成首版 | `execution.py`、`orders.py` | supersession、盲重试阻断、反向先平仓 |
| 7. InstrumentMetadata及舍入 | 完成首版 | `instruments.py` | 1,000组不放大性质和版本选择 |
| 8. 事件及经济重放 | 完成统计来源扩展 | `economic_ledger_snapshot()`、`monthly_economic_series_snapshot()` | 投影、经济结果和逐月来源hash确定性 |
| 9. ADR及治理模板 | 完成模板首版 | ADR-0001至ADR-0010、8份治理模板 | Schema与未审批语义测试 |
| 10. Schema及确定性Evaluator | 完成依赖序列推断首版 | `statistics.py`、`estimators.py`、`release.py` | 149 Gate、14个Estimator、22个Golden vectors |

## v0.10.0新增证据

- 新增`StatisticalSeriesSnapshot v1`，冻结有序观察、来源经济快照、完整Scope、批准资本、实验和四类Policy hash。
- 月度经济序列只能由同Scope、同会计政策、互不重叠的EconomicLedgerSnapshot生成。
- 月度PnL按批准生产资本逐月重置；不同初始资本不能混入`USDT/月`分布。
- 系统独立识别完整UTC自然月，部分首尾月份排除，内部缺月、内部部分月或重叠直接失败。
- 实现Geyer Initial Positive Sequence ESS；零方差或区块不足返回INCONCLUSIVE。
- 实现非循环重叠Moving-block Bootstrap、一侧95%保守下界和SHA-256 rejection-sampling抽样。
- 实现现金流及分摊成本调整后的分段经济log growth。
- 通用主终点Bootstrap和月度PnL Bootstrap使用不同series kind及聚合规则，不能偷换单位。
- GateEvidence和Supporting Observation核验统计序列Scope、Experiment、批准资本、Policy和所有来源经济快照hash。
- Estimator Registry由9个增加到14个；Golden vectors由17个增加到22个。
- 新增测试覆盖全局Decimal context变化、部分月份、虚假完整月、重复/缺失来源、错误序列类型、零方差、区块不足、Artifact篡改和跨实验复用。

## 围绕赚钱目标的解释

本增量首次实现机器可执行的长期盈利判定核心：

```text
真实逐月全成本经济PnL
  → 保留时间依赖的Moving-block Bootstrap
  → 一侧95%月均PnL下置信界
```

只有真实、获批、完整月份的下界大于0，才能开始支持“经济上赚钱”的声明。代码中的Golden Fixture得到`10.875 USDT/月`只是验证算法和边界的合成数据，不能当作项目收益。

## 仍然Fail-Closed

- 当前Policy为`DESIGN_BASELINE`且生产开关关闭，治理模板未获批。
- 没有真实市场数据管线生成的完整月EconomicLedgerSnapshot或StatisticalSeriesSnapshot。
- SplitPolicy、StatisticalDesignPolicy、AccountingPolicy和CostAllocationPolicy仍未批准。
- 尚未实现AI与简单基线的同时间点配对Bootstrap、Holm多重检验、leave-out脆弱性、功效、CI宽度、DSR和PBO。
- 没有Broker、交易所Adapter、API密钥读取、网络请求或真实下单能力。
- 因此当前不能声明策略或AI已经证明赚钱，也不能投入真钱。

## 下一增量

1. 实现AI_LEDGER与BASELINE_LEDGER同proposal/time的配对增量序列。
2. 实现一侧95%配对Moving-block Bootstrap。
3. 实现删除最大正折、最大正事件和前5笔盈利交易后的脆弱性重放。
4. 实现同时候选家族的Holm校正及实际CI宽度证据。
5. 在不接Broker的前提下，开始离线Paper数据采集与完整月份Artifact生成。
