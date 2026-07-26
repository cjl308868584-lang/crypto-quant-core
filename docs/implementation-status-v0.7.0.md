# 实施追踪 v0.7.0

状态：Phase 0第七个增量
权威范围：[开发路线与验收门槛 v1.1，第9节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已有实现与自动化证据。Build hash存在不代表生产审批完成，Golden vector通过也不代表策略具有盈利能力。

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
| 9. ADR及政策/事故模板 | 完成模板首版 | ADR-0001至ADR-0007、治理Schema和8份JSON模板 | 正反Schema、固定边界和未审批语义测试 |
| 10. Schema验证和确定性Evaluator | 完成资本Estimator首版 | `release.py`、`evidence.py`、`estimators.py`、`build.py` | 149 Gate、Evidence信任链、4个Estimator、12个Golden vectors、Build防篡改 |

## v0.7.0新增证据

- Estimator Registry覆盖Metric Catalog全部57个算法ID：4个可执行，53个明确`UNAVAILABLE`。
- 可执行函数采用静态白名单和精确输入集合；缺失或额外输入均Fail-Closed。
- 资本业务计算使用`Decimal`规范化；负值和二进制浮点输入不能进入计算结果。
- 12个Golden vectors覆盖资本规范化、Scope/快照未验证、Break-even root的正值/null/zero以及比较边界。
- Registry和Golden bundle均验证Schema、自哈希、Catalog/Registry引用及双向向量覆盖。
- GateEvidence不再信任声明的`metric_value`：使用Catalog指定Estimator独立重算，声明与计算不一致时Evidence无效。
- Estimator执行hash进入Evidence validation hash；同一向量重复100次结果和报告hash一致。
- Evaluator Build Manifest绑定全部包Python文件、冻结发布配置、Schema、项目版本和依赖锁。
- 构建加载会验证精确文件集合、逐文件SHA-256、规范化树hash、Registry/Golden/report hash及覆盖声明。
- 篡改Registry、Golden bundle或任一Evaluator输入文件均被自动化测试拒绝。
- 当前完整测试数为94项；当前设计Policy的`make validate`仍预期输出发布Readiness `FAIL`。

## 围绕赚钱目标的解释

v0.7.0不新增交易信号，也不宣称提高收益。它解决的是更基础的盈利可信度问题：任何“通过门槛”的数值必须能由冻结算法和受信输入独立复算，不能由AI或发布者自报。

实现顺序继续遵循“先证明不会把假收益当真钱，再优化模型”：

1. 扣除手续费、滑点、资金费率和分摊成本后的经济PnL；
2. 回撤、损失、暴露和压力场景；
3. 样本有效性、Bootstrap置信下界和敏感性；
4. AI相对简单基线的配对增量价值；
5. 只有上述证据成立，才讨论扩大资本。

## 仍然Fail-Closed

- 没有Broker、交易所Adapter、API密钥字段、网络请求或真实下单方法。
- 当前Policy仍为`DESIGN_BASELINE`且生产开关关闭，外部治理binding仍未批准，`evaluator_build_hash`也未写入激活Policy。
- Build Manifest状态为`BUILD_CANDIDATE`，尚无外部签名、Trust Store或批准记录。
- 53个统计、经济、稳健性、AI和治理Estimator尚不可执行；相关Evidence不能有效PASS。
- 真正的ED25519、公钥轮换、ExperimentManifest和DeploymentLine生产Schema仍未实现。
- AI训练、正式ModelBundle审批和AI增量价值评估尚未开始。

## 下一增量

1. 为ExperimentManifest、DeploymentLine和supporting observation建立独立Schema与内容hash边界。
2. 优先实现扣全成本经济PnL、现金流调整权益、最大回撤和风险暴露Estimator。
3. 再实现有效样本、移动块Bootstrap和AI相对基线的配对Estimator。
4. 补齐Phase 0密钥/环境/账户隔离、适格性清单、机器风险政策和停机Runbook。
5. Phase 0全部退出条件有证据后，才开始权威只读市场数据采集。
