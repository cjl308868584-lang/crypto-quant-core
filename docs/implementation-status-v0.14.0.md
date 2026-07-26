# 实施追踪 v0.14.0

状态：Phase 0 第十四个增量

权威范围：[开发路线与验收门槛 v1.1，第 9 节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已有实现和自动化证据。所有正收益结果均来自合成 Golden Fixture，不是
策略或 AI 的真实盈利记录。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python 包、测试和 CI 骨架 | 完成 | `pyproject.toml`、`Makefile`、CI | `make test`、`make validate` |
| 2. 核心决策链和双臂角色 | 完成配对角色首版 | `contracts.py`、`ledger.py`、`statistics.py` | AI 路线独立 BASELINE/AI 账本测试 |
| 3. Decimal 及统计确定性 | 完成统计决策扩展 | `canonical.py`、`statistical_decision.py` | 多种全局 Decimal precision 下结果/hash 相同 |
| 4. SQLite WAL、Outbox 及经济投影 | 完成可追溯 v1.1 | `ledger.py`、`economics.py` | 不可变事件 sequence 与 Fill identity 测试 |
| 5. 风控及绝对经济门 | 完成领域首版 | `risk.py`、`economics.py` | 两臂绝对门不能由 delta 替代 |
| 6. Target、Intent、Attempt 和订单状态 | 完成首版 | `execution.py`、`orders.py` | 顺序、UNKNOWN 和反向先平仓测试 |
| 7. InstrumentMetadata 及舍入 | 完成首版 | `instruments.py` | 不放大性质和版本选择 |
| 8. 统计来源及路径重放 | 完成 Holm/区间/功效首版 | `statistical_decision.py`、`statistics.py` | family、MBB、ESS 和缓存防篡改测试 |
| 9. ADR 及治理模板 | 完成模板首版 | ADR-0001 至 ADR-0014、8 份治理模板 | Schema 与未审批语义测试 |
| 10. Schema 及确定性 Evaluator | 完成统计决策证据首版 | `estimators.py`、`release.py` | 151 Gate、24 个 Estimator、39 个 Golden vectors |

## v0.14.0 新增证据

- 新增统一 `StatisticalDecisionSnapshot v1`，冻结累计 Trial Registry、所有可评估
  family 源序列、共同 Bootstrap 设计、完整 Holm 过程及当前候选区间、ESS、功效。
- `HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1`、
  `PRIMARY_ENDPOINT_CI_WIDTH_V1` 和 `ACHIEVED_POWER_AT_MERE_V1`
  从明确 Fail-Closed 升级为可执行 Estimator。
- 失败、中止和无效 Trial 保留在 family 并以 `raw_p = 1` 参与排序；并列 p 值按
  `candidate_id` 稳定排序，Holm 首次失败后停止。
- 双侧区间、原始单侧 p 值和 MERE 功效使用同一冻结序列、确定性 MBB 和规范
  Decimal；功效使用候选实际 Holm rank 的调整 alpha。
- GateEvidence 绑定 Artifact、Policy/Catalog、ExperimentManifest、Recipe、
  Scope、资本、端点、窗口、ESS 和全部 family 源哈希；Supporting Observation
  缺任一来源即失败关闭。
- 新 required Gate：
  `HOLM_ADJUSTED_PRIMARY_PASS` 和
  `AUDIT_BASE_HOLM_ADJUSTED_PRIMARY_PASS`。
- 58 个 Catalog 算法中 24 个可执行、34 个明确 Fail-Closed；39 个 Golden
  vectors 全部通过。
- Golden report hash：
  `2c02a9cfd888efd18f348e2583ac0dc12746f612dbb8cd0b820a80802b11f34e`。
- Evaluator build hash：
  `74ff520f3c880242146ea285f181ea34532d3c14cc163539658c997f36eb74ec`。
- 全量自动化套件共 183 项通过；命令：
  `PYTHONPATH=src python3 -m unittest discover -s tests -v`。

## 失败关闭与变异覆盖

- Trial Registry 遗漏、顺序/状态/身份篡改和 Manifest 数量或注册表哈希不一致。
- 源序列自哈希、Scope、Recipe、Bootstrap 设计、候选窗口和 family 来源缺失。
- Holm 缓存的 p 值、rank、阈值、reached/rejected 状态篡改。
- CI、ESS、功效缓存篡改，以及 GateEvidence 样本 ESS 不一致。
- 样本/区块不足、零方差和 Bootstrap 分辨率不足返回 `INCONCLUSIVE`。
- GateEvidence 上传的有利标量不会替代可信快照重放结果。

## 围绕赚钱目标的解释

本增量回答的是：累计试验家族中当前候选的主要端点是否在控制 family-wise
假阳性后仍成立，估计区间是否足够窄，以及在预先冻结 MERE 处是否具有足够检测
能力。它减少反复试验、选择性报告和低功效结果造成的虚假“赚钱”结论，但不创造
alpha，也不证明真实交易可盈利。

仓库仍只有合成 Golden Fixture，没有封存历史/Paper 证据。当前 Policy 仍为
`DESIGN_BASELINE`，`production_activation.enabled=false`，治理模板未审批；没有
Broker、交易所 Adapter、API 密钥读取或真实下单能力。因此不能声明 AI 优于简单
基线、策略已经赚钱或可以投入真钱。

## 仍然 Fail-Closed

1. `RISK_EFFICIENCY` 的配对最大回撤和 ES95 改善区间。
2. 不连接真实 Broker 的离线双臂 Paper 证据生成、封存和摄取管线。
3. 真实、封存、获批的 BASELINE/AI 配对证据及独立审查。

DSR、PBO 和概率校准等未实现 Catalog 项继续明确 Fail-Closed，不由本增量隐式
替代。
