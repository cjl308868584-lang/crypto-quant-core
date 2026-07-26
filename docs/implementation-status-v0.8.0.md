# 实施追踪 v0.8.0

状态：Phase 0第八个增量
权威范围：[开发路线与验收门槛 v1.1，第9节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已有实现与自动化证据。Schema和测试Fixture不等于生产Artifact获批，Evidence可信也不等于策略具有盈利能力。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python包、测试和CI骨架 | 完成 | `pyproject.toml`、`Makefile`、`.github/workflows/ci.yml` | `make test`、`make validate` |
| 2. 通用事件信封及核心契约 | 完成首版 | `contracts.py`、`execution.py` | 确定性ID、null/zero、lineage和风险上限测试 |
| 3. Decimal/tick/step值对象 | 完成首版 | `canonical.py`、`decimal_math.py` | Decimal边界、禁用业务float和舍入测试 |
| 4. SQLite WAL、Outbox、成本/现金流和投影 | 完成Phase 0首版 | `ledger.py` | 幂等、不可变、哈希链、Outbox、投影重建 |
| 5. RiskLock、Stage上限、回撤状态 | 完成领域首版 | `risk.py`、`execution.py` | 回撤、Stage、资本、UNKNOWN与1x最坏毛杠杆测试 |
| 6. Target supersession、Intent、Attempt状态 | 完成首版 | `execution.py`、`orders.py` | Target序列、盲重试阻断、反向先平仓 |
| 7. InstrumentMetadata及舍入性质 | 完成首版 | `instruments.py`、离线Binance Fixture | 1,000组不放大性质、NO_TRADE和版本选择 |
| 8. 事件重放Golden Test | 完成Phase 0首版 | 全部命名投影、Checkpoint、`projection_hash()` | 冲突回滚、篡改检测和从零重放 |
| 9. ADR及政策/事故模板 | 完成模板首版 | ADR-0001至ADR-0008、治理Schema和8份JSON模板 | 正反Schema、固定边界和未审批语义测试 |
| 10. Schema验证和确定性Evaluator | 完成Artifact lineage首版 | `release.py`、`release_artifacts.py`、`estimators.py`、`build.py` | 149 Gate、4个Estimator、12个Golden vectors、Experiment/Line/Supporting防篡改 |

## v0.8.0新增证据

- 新增ExperimentManifest生产Schema，不再使用允许null的未审批治理模板作为正式发布对象。
- ExperimentManifest冻结完整研究谱系、代码环境、随机种子、点时数据、Purge/Embargo、经济口径、Trial预算、失败记录和输出hash。
- 采用实验内容hash与Recipe binding hash两段冻结，解决Recipe与Experiment互引形成的密码学循环。
- Recipe、Experiment、GateEvidence之间的route、endpoint、baseline reference、Recipe ID/hash、21项设计hash、批准资本和揭晓时间逐项验证。
- 新增DeploymentLine生产Schema、自哈希、attestation和完整阶段前缀验证。
- DeploymentLine绑定Recipe、Experiment、direction、venue及AI ModelBundle或NO_AI版本；跳级、倒序、缺失前序PASS或缺失阶段证据均失败。
- GateEvidence新增Experiment Schema/ID/hash、DeploymentLine Schema/hash和Supporting Bundle三字段引用。
- ReleaseGatePolicy升级至`1.1.3`，Exact Scope新增Experiment ID/hash和DeploymentLine hash，内容修订不能继续复用旧Scope。
- 新增Supporting Observation Bundle Schema；每项观测由Catalog解析并通过Estimator Registry重新执行。
- Bundle绑定Exact Scope、Policy bundle、Evaluator build、来源Artifact和attestation；伪造值即使重算对象hash和“签名验证结果”仍会被独立执行识别。
- 原始`supporting_observations`映射正式Fail-Closed，不再参与生产Gate求值。
- 三份新Schema及`release_artifacts.py`进入Evaluator Build Manifest。
- 当前完整测试数为98项；相同完整Evidence Group重复100次仍得到相同结果与validation hash。

## 围绕赚钱目标的解释

本增量没有增加新信号。它封住的是研究和AI最常见的“假盈利”入口：

1. 试了很多模型却只保留最好结果；
2. 在看到结果后更改route、终点、成本或统计口径；
3. 把另一条部署线或上一阶段PASS复制到当前资金阶段；
4. 手工传入对动态阈值有利的辅助指标；
5. 给伪造数值附加一个合法对象hash或签名。

只有把这些行为变成机器可拒绝的不变量，后续经济PnL和AI增量收益才值得用于资本决策。

## 仍然Fail-Closed

- 当前Policy仍为`DESIGN_BASELINE`且生产开关关闭，外部治理binding尚未批准。
- 仓库中没有真实获批的ExperimentManifest、DeploymentLine或Supporting Observation Bundle，只有严格Fixture。
- 真正的ED25519、公钥轮换、Trust Store和Artifact resolver尚未实现。
- DeploymentLine已有Schema和验证器，但还没有持久化状态命令、原子ModelBundle切换或操作审批流程。
- 57个Catalog算法仍只有4个资本Estimator可执行；53个经济、统计、稳健性、AI和治理Estimator继续失败关闭。
- 没有Broker、交易所Adapter、API密钥读取、网络请求或真实下单能力。

## 下一增量

1. 实现逐Fill扣手续费、滑点、资金费率和分摊成本的经济PnL Estimator。
2. 实现现金流调整权益、日损、最大回撤和最坏毛暴露Estimator。
3. 用现有账本投影生成可重放的Estimator输入Artifact和Golden vectors。
4. 随后实现有效样本、移动块Bootstrap和AI相对简单基线的配对增量Estimator。
5. 继续补齐Phase 0密钥/环境/账户隔离、适格性清单、机器风险政策和停机Runbook。
