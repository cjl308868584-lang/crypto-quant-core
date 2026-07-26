# 实施追踪 v0.6.0

状态：Phase 0第六个增量
权威范围：[开发路线与验收门槛 v1.1，第9节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已有实现与自动化证据。“验证协议完成”不代表外部公钥、政策或数据已经获批。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python包、测试和CI骨架 | 完成 | `pyproject.toml`、`Makefile`、`.github/workflows/ci.yml` | `make test` |
| 2. 通用事件信封及核心契约 | 完成首版 | `contracts.py`、`execution.py` | 确定性ID、null/zero、lineage和风险上限测试 |
| 3. Decimal/tick/step值对象 | 完成首版 | `canonical.py`、`decimal_math.py` | Decimal边界和舍入测试 |
| 4. SQLite WAL、Outbox、成本/现金流和投影 | 完成Phase 0首版 | `ledger.py` | 幂等、不可变、哈希链、Outbox、完整命名投影重建 |
| 5. RiskLock、Stage上限、回撤状态 | 完成领域首版 | `risk.py`、`execution.py` | 回撤10/12/15/20%、Stage、资本、UNKNOWN与1x最坏毛杠杆测试 |
| 6. Target supersession、Intent、Attempt状态 | 完成首版 | `execution.py`、`orders.py` | 跨载体Target序列、盲重试阻断、反向先平仓 |
| 7. InstrumentMetadata及舍入性质 | 完成首版 | `instruments.py`、离线Binance Fixture | 1,000组不放大性质、NO_TRADE与历史版本选择 |
| 8. 事件重放Golden Test | 完成Phase 0首版 | 全部命名投影、Checkpoint、`projection_hash()` | 冲突回滚、篡改检测与从零重放 |
| 9. ADR及政策/事故模板 | 完成模板首版 | ADR-0001至ADR-0006、治理Schema和8份JSON模板 | 正反Schema、固定边界和未审批语义测试 |
| 10. Schema验证和确定性Evaluator | 完成Phase 0协议首版 | `release.py`、`evidence.py` | 149 Gate、AST、Scope、GateEvidence、Recipe/Model/Fallback信任链及确定性hash |

## v0.6.0新增证据

- GateEvidence完整信封使用排除self-hash字段后的规范化业务hash，篡改任一其他字段都会失配。
- Gate、Metric、Comparator、Estimator、Unit、阈值快照和结果均由Evaluator独立解析与重算。
- Policy binding ID/hash同时绑定当前Policy、内置Artifact、外部resolver与逐项freeze proof。
- 签名验证结果采用`signature → freeze evidence → artifact`成对映射，阻止跨Artifact拼接。
- 所有冻结时间必须早于首次结果揭晓；缺少Reveal验证、晚冻结或提前计算均Fail-Closed。
- RecipeRelease验证Schema、自哈希、attestation、Policy/Experiment hash、route、方向及venue。
- AI Evidence额外验证ModelBundle Schema、自哈希、签名、Recipe、DeploymentLine、endpoint、方向和venue。
- 资本计划hash进入Exact Scope，三个资本值与已解析冻结计划逐字段一致。
- Fallback激活验证Registry与Record的Schema、自哈希、签名、有效期、状态、来源Scope、Stage上限、Policy hash和Champion/LKG资格。
- 生产门组要求每个Gate恰好一个有效信封，并在信封聚合后再次执行Policy Readiness。
- 当前设计Policy下，内部有效Evidence仍被生产入口阻断；测试内存中的完整ACTIVE Policy仅用于证明PASS路径可达。
- 85项自动化测试通过；相同Evidence Group重复100次得到同一结果和业务hash。

## 仍然Fail-Closed

- 没有Broker、交易所Adapter、API密钥字段、网络请求或真实下单方法。
- 当前Policy仍为`DESIGN_BASELINE`且生产开关关闭，8个必需binding仍未批准。
- `EvidenceTrustContext`要求外部Verifier提供已经验证的成对结果；真正的ED25519、公钥Trust Store和密钥轮换尚未实现。
- 外部治理Policy的内容hash由resolver提供；这些Policy当前仍是未审批模板。
- ExperimentManifest和DeploymentLine还没有独立生产Schema与完整内容验证。
- AST依赖的supporting metric仍由调用方传入；Metric Catalog的统计Estimator尚未形成可执行Registry。
- Evaluator build manifest和Golden vector bundle尚未冻结，因此不能填写`evaluator_build_hash`。
- AI训练和正式ModelBundle审批尚未开始。

## 下一增量

1. 建立版本化Estimator Registry、Evaluator Build Manifest及其Schema。
2. 为已进入执行内核的确定性算法建立Golden vector bundle，并从manifest计算真实`evaluator_build_hash`。
3. 为ExperimentManifest、DeploymentLine和supporting metric evidence补齐生产Schema或明确独立契约。
4. 补齐Phase 0密钥/环境/账户隔离、适格性清单、机器风险政策和停机Runbook。
5. Phase 0全部退出条件有证据后，才开始权威只读市场数据采集。
