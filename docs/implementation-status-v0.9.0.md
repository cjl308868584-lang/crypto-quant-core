# 实施追踪 v0.9.0

状态：Phase 0第九个增量
权威范围：[开发路线与验收门槛 v1.1，第9节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已有实现与自动化证据。经济Estimator产生的单期正值不等于策略已证明可重复赚钱，也不授权真实交易。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python包、测试和CI骨架 | 完成 | `pyproject.toml`、`Makefile`、`.github/workflows/ci.yml` | `make test`、`make validate` |
| 2. 通用事件信封及核心契约 | 完成首版 | `contracts.py`、`execution.py` | 确定性ID、null/zero、lineage和风险上限测试 |
| 3. Decimal/tick/step值对象 | 完成首版 | `canonical.py`、`decimal_math.py` | Decimal边界、禁用业务float和舍入测试 |
| 4. SQLite WAL、Outbox、成本/现金流和投影 | 完成经济投影首版 | `ledger.py` | 幂等、不可变、哈希链、经济快照及从零重放 |
| 5. RiskLock、Stage上限、回撤状态 | 完成领域首版 | `risk.py`、`execution.py`、`economics.py` | 回撤、日损、Stage、资本、UNKNOWN与最坏毛杠杆测试 |
| 6. Target supersession、Intent、Attempt状态 | 完成首版 | `execution.py`、`orders.py` | Target序列、盲重试阻断、反向先平仓 |
| 7. InstrumentMetadata及舍入性质 | 完成首版 | `instruments.py`、离线Binance Fixture | 1,000组不放大性质、NO_TRADE和版本选择 |
| 8. 事件重放Golden Test | 完成经济账本扩展 | 全部命名投影、Checkpoint、`economic_ledger_snapshot()` | 冲突回滚、篡改检测、经济结果重放一致 |
| 9. ADR及政策/事故模板 | 完成模板首版 | ADR-0001至ADR-0009、治理Schema和8份JSON模板 | 正反Schema、固定边界和未审批语义测试 |
| 10. Schema验证和确定性Evaluator | 完成经济点估计首版 | `economics.py`、`estimators.py`、`release.py`、`release_artifacts.py` | 149 Gate、9个Estimator、17个Golden vectors、经济Scope防偷换 |

## v0.9.0新增证据

- 新增`EconomicLedgerSnapshot v1` Schema，所有金额使用规范Decimal字符串，禁止业务float。
- 账本新增AllocatedCost、FundingCashFlow和EquitySnapshot投影；ExternalCashFlow补齐账户和业务flow ID；Fill补齐contract multiplier。
- 快照只由通过完整性检查的账本和投影生成，绑定账本hash、投影hash、会计政策、成本政策、Recipe、部署线、方向、venue和精确窗口。
- 实现逐Fill移动加权平均成本、已实现价差、实际手续费和有符号资金费核算。
- 明确实际Fill价格已包含spread/slippage，`implementation_shortfall`只用于归因，不重复扣除。
- 实现现金流调整后的期间经济PnL、UTC日损、清算权益最大回撤和不净额抵消的最坏毛暴露。
- 经济成本只允许Shared或与route一致的分摊范围，阻止Baseline和AI相互转嫁专属成本。
- GateEvidence可冻结经济快照；主Gate和Supporting Observation都会核验快照Scope、政策hash以及快照/账本/投影来源hash。
- Estimator Registry升级至9个可执行算法，Golden vectors由12个增至17个。
- 经济测试覆盖精确值、100次确定性、float拒绝、self-hash篡改、成本范围偷换、跨零Fill、滑点重复扣除防护、投影篡改和从零重放。

## 围绕赚钱目标的解释

本增量把“赚钱”从一个可手填的回测数字，缩小为可审计的经济事实：

```text
经济PnL = 结束清算权益 - 开始清算权益 - 外部现金流 - 分摊运营成本
```

因此充值、漏费、低报退出成本、现货/永续净额抵消和AI成本转嫁不能再制造表面盈利。逐Fill结果与权益结果同时保留，差异必须由未平仓估值、退出成本或数据问题解释。

这仍只是可靠测量，不是盈利证明。赚钱目标下一步需要证明：跨完整月份的全成本PnL下置信界为正，且AI相对同一简单基线、同一候选事件和同一执行条件的配对增量下置信界为正。

## 仍然Fail-Closed

- 当前Policy仍为`DESIGN_BASELINE`且生产开关关闭，外部治理binding尚未批准。
- 仓库中没有真实获批的经济快照、ExperimentManifest、DeploymentLine或Supporting Observation Bundle，只有严格Fixture。
- 57个Catalog算法仍有48个不可执行，包括有效样本量、完整UTC月份、移动块Bootstrap、经济log growth、AI配对增量及多重检验校正。
- 没有Broker、交易所Adapter、API密钥读取、网络请求或真实下单能力。
- 没有真实交易所余额/成交/资金费/标记价格采集器，也没有生产数据库迁移工具。
- 单期经济PnL为正、Golden Vector通过或代码测试通过，均不授权真钱。

## 下一增量

1. 实现完整UTC月份划分、有效样本量和固定block-length移动块Bootstrap。
2. 实现月度全成本经济PnL及net log growth的LCB95。
3. 实现AI与简单基线在相同候选事件上的配对增量、选择偏差控制和Holm校正。
4. 将经济快照生成接入Paper数据管线，再做跨月证据，不接Broker。
5. 补生产数据库版本迁移、密钥/账户隔离、机器风险政策和停机Runbook。
