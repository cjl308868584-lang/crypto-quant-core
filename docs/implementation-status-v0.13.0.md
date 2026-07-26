# 实施追踪 v0.13.0

状态：Phase 0 第十三个增量

权威范围：[开发路线与验收门槛 v1.1，第 9 节](delivery-roadmap-v1.1.md#9-紧接着执行的第一个迭代)

本表只记录已有实现和自动化证据。所有正收益结果均来自合成 Fixture，不是策略或
AI 的真实盈利记录。

| 原交付物条目 | 当前状态 | 实现证据 | 验证证据 |
|---|---|---|---|
| 1. Python 包、测试和 CI 骨架 | 完成 | `pyproject.toml`、`Makefile`、CI | `make test`、`make validate` |
| 2. 核心决策链和双臂角色 | 完成配对角色首版 | `contracts.py`、`ledger.py`、`statistics.py` | AI 路线独立 BASELINE/AI 账本测试 |
| 3. Decimal 及统计确定性 | 完成交易反事实扩展 | `canonical.py`、`statistics.py`、`trade_replay.py` | 多种全局 Decimal precision 下结果/hash 相同 |
| 4. SQLite WAL、Outbox 及经济投影 | 完成可追溯 v1.1 | `ledger.py`、`economics.py` | 不可变事件 sequence 与 Fill identity 测试 |
| 5. 风控及绝对经济门 | 完成领域首版 | `risk.py`、`economics.py` | 两臂绝对门不能由 delta 替代 |
| 6. Target、Intent、Attempt 和订单状态 | 完成首版 | `execution.py`、`orders.py` | 顺序、UNKNOWN 和反向先平仓测试 |
| 7. InstrumentMetadata 及舍入 | 完成首版 | `instruments.py` | 不放大性质和版本选择 |
| 8. 统计来源及路径重放 | 完成 Top-5 完整交易首版 | `trade_replay.py`、`statistics.py` | 原路径复现、零到零周期、反事实 MBB |
| 9. ADR 及治理模板 | 完成模板首版 | ADR-0001 至 ADR-0013、8 份治理模板 | Schema 与未审批语义测试 |
| 10. Schema 及确定性 Evaluator | 完成交易集中度首版 | `estimators.py`、`release.py` | 149 Gate、21 个 Estimator、33 个 Golden vectors |

## v0.13.0 新增证据

- `EconomicLedgerSnapshot v1.1` 保存每个经济事实的
  `source_event_sequence`，Fill 保存三类不可变成交/订单 identity；v1.0 消费者保持
  兼容。
- 完整 replay 来源额外验证跨周期 sequence 与稳定事实 ID 唯一性，防止一个被选中
  交易的 Fill/Funding ID 碰撞后误删另一笔未选中交易。
- 新增 `TradeReplaySnapshot v1`，内嵌源 StatisticalSeries、EconomicSnapshot、
  可执行估值 checkpoint、原始路径、派生完整交易、Top-5 选择和反事实序列。
- 完整交易固定为单 instrument 的零到零持仓周期；split fills 合并为同一交易，
  overlapping instruments 独立处理，跨零 Fill 和 multiplier 漂移失败关闭。
- 原始路径必须在每个 checkpoint 精确复现 liquidation equity、position cost basis、
  expected exit fee 和源 observation。
- 反事实移除所选交易全部 Fill 与归属 Funding；保留外部现金流和 allocated cost；
  不重复扣减已体现在 Fill price 中的 implementation shortfall。
- 正贡献按贡献降序、`trade_id` 升序稳定选择最多五笔，然后重建
  StatisticalSeries v1.2 并执行原有一侧 95% MBB。
- GateEvidence 冻结 replay 与源统计序列；Supporting Observation 绑定所有源经济
  快照、反事实序列及每期 replay hash。
- ReleaseGatePolicy 版本保持 `1.1.4`，Metric Catalog 升至 `1.1.4`，
  Estimator Registry 升至 `1.5.0`，Evaluator Build Manifest 升至 `1.6.0`。
- 57 个 Catalog 算法中 21 个可执行、36 个明确 Fail-Closed；Golden vectors
  由 29 个增至 33 个。
- v0.13.0 定向发布验证共 53 项通过，覆盖 Registry、Release evaluator 和完整交易
  replay。
- 全量自动化套件共 160 项通过；确定性构建、5 类发布 Artifact Schema 和 8 份
  未审批治理模板均完成独立验证。

## 围绕赚钱目标的解释

本增量把集中度稳健性判断从不正确的近似：

```text
从收益数组删除五个最大值
```

升级为：

```text
冻结事件与估值事实
  → 精确复现原始权益路径
  → 按 instrument 派生零到零完整交易
  → 选择五个最大正贡献交易
  → 删除其全部 Fill 与归属 Funding
  → 保留现金流和全部 allocated cost
  → 重放剩余持仓与清算权益
  → 重建统计序列并计算保守下界
```

这能发现“策略利润集中在极少数交易”的风险，并减少因错误删除粒度造成的虚假
稳健性结论。合成 Golden Fixture 只证明算法确定、可重放且篡改会失败，不代表市场
中存在可交易 alpha。

## 仍然 Fail-Closed

- 没有真实、封存、获批的 BASELINE/AI 配对经济序列和 TradeReplaySnapshot。
- 当前 Policy 仍为 `DESIGN_BASELINE`，生产激活关闭，治理模板未审批。
- Holm family-wise correction、双侧 CI 宽度、MERE 实际功效、DSR、PBO 和校准区间
  未实现。
- `RISK_EFFICIENCY` 的配对最大回撤和 ES95 改善区间未实现。
- 没有离线双臂 Paper 数据生成与封存管线。
- 没有 Broker、交易所 Adapter、API 密钥读取或真实下单能力。
- 因此当前不能声明 AI 优于简单基线、策略已经赚钱或可以投入真钱。

## 下一增量

1. 实现 Holm 多重检验、CI 宽度与 MERE 实际功效，并绑定到 Release evidence。
2. 实现 `RISK_EFFICIENCY` 的配对最大回撤和 ES95 改善区间。
3. 建立不连接真实 Broker 的离线双臂 Paper 数据生成、封存和重放管线。
4. 用封存历史/Paper 数据生成第一份非 Golden 的 BASELINE/AI 配对 Evidence。
5. 只有前述证据通过后，再讨论只读交易所数据 Adapter；真实下单仍保持禁用。
