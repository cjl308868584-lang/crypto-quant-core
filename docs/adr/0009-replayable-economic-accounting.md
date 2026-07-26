# ADR-0009：可重放经济账本与全成本收益口径

状态：Accepted
日期：2026-07-26

## 背景

v0.8.0已经能验证研究、部署线、模型和辅助观测的来源，但尚不能从账本独立重算收益、日损、回撤和最坏毛暴露。若这些数值仍由调用方直接提交，就可能出现：

1. 把充值当成策略收益；
2. 只计算已实现价差，漏掉手续费、资金费率或运营成本；
3. 成交价格已经包含滑点，却再次扣除implementation shortfall；
4. 将现货多头与永续空头净额抵消后低报杠杆；
5. 把另一账户、Recipe、部署线、评估窗口或成本政策的结果用于当前Gate。

## 决策

### 1. 冻结经济账本快照

新增`EconomicLedgerSnapshot v1`，由通过哈希链及投影完整性检查的SQLite账本生成。快照绑定：

- 账户、经济账本、发布路径、方向和交易场所；
- RecipeRelease及DeploymentLine的ID和hash；
- 评估窗口，业务事件采用`(start, end]`，权益边界采用`[start, end]`；
- AccountingPolicy及CostAllocationPolicy的ID和hash；
- 来源账本hash、来源投影hash和快照self-hash；
- 开始/结束清算权益、逐Fill事实、资金费、外部现金流、分摊成本和权益路径。

窗口开始和结束必须存在精确权益快照，所有权益点必须证明使用保守可执行平仓口径。重放投影后必须生成逐字相同的快照和结果。

### 2. 成交收益

`FILL_BASED_GROSS_MINUS_FEES_PLUS_SIGNED_FUNDING_V1`采用逐标的移动加权平均成本：

```text
fill_net_pnl
  = realized_price_pnl
  - sum(fee_value_usdt)
  + sum(signed_funding_cashflow_usdt)
```

实际Fill价格已经体现spread、冲击和滑点，因此`implementation_shortfall_usdt`只用于归因和模型评估，不从上述收益再次扣除。单个Fill不允许直接穿越零仓位；反向必须拆成平仓与新开仓事实，以保持成本基础明确。

### 3. 期间经济收益

```text
period_economic_pnl
  = ending_liquidation_equity
  - starting_liquidation_equity
  - net_external_cash_flow
  - allocated_operating_cost
```

充值为正、提现为负。分摊成本只允许`SHARED`或与发布路径一致的范围，Baseline不得吸收AI专属成本，AI路径也不得把Baseline专属成本作为自己的费用。

成交收益用于交易事实对账；期间经济收益用于完整商业口径。两者不是强制相等：未平仓浮动收益、保守退出成本和权益估值变化会造成合理差异，后续审计必须解释差额。

### 4. 日损、回撤与最坏毛暴露

- 日损按UTC日初marked equity为分母，扣除日内外部现金流，保留带符号收益率；`<= -2%`触发日损锁。
- 最大回撤在清算权益路径上扣除累计外部现金流和已分摊成本后计算；调整后权益非正时失败关闭。
- 最坏毛暴露为现货、永续、活动新增风险订单和`UNKNOWN`订单名义金额之和除以marked equity。
- 现货与永续不得为杠杆限制相互净额抵消；marked equity非正时失败关闭。

### 5. 发布证据

经济Estimator输入必须通过版本化Schema、自哈希、语义校验和Estimator Golden Vector。作为GateEvidence或Supporting Observation使用时，还必须与当前Evidence的Recipe、DeploymentLine、方向、venue、窗口、会计政策及成本政策逐项一致，并显式引用快照、来源账本和来源投影hash。

## 不变量

- 二进制float不得进入业务计算或冻结Artifact。
- 现金流不得成为策略收益。
- Fill手续费和资金费必须使用已折算为USDT的有符号事实。
- 实际成交价格中的滑点不得重复扣除。
- 未知活动订单按风险增加计入毛暴露。
- 快照Schema合法或有self-hash不等于来源可信；来源账本、投影和Evidence Scope必须同时验证。
- 单期点估计为正不证明策略可重复赚钱。

## 备选方案

- 直接信任交易所报表PnL：拒绝，无法绑定本项目的成本、现金流和发布范围。
- 只用逐Fill已实现收益：拒绝，会漏掉未平仓权益、保守退出成本和运营成本。
- 把implementation shortfall再扣一次：拒绝，实际Fill价格已经包含该经济影响。
- 用净ETH敞口计算杠杆：拒绝，会掩盖基差、融资、清算和活动订单风险。
- 让模型预测手续费或资金费替代事实：拒绝，预测只适合事前决策，事后经济核算必须用实际事实。

## 后果

- 57个Catalog算法中有9个可执行，新增5个覆盖经济PnL、日损、最大回撤和最坏毛暴露；其余48个继续失败关闭。
- 经济点估计可以被账本重放和独立重算，但月度经济PnL的移动块Bootstrap下置信界、有效样本量和AI相对基线配对增量尚未实现。
- 当前结果不能作为投入真钱或声称盈利能力的依据。

## 验证证据

- 快照Schema：`config/economic-ledger-snapshot-v1.schema.json`
- 经济算法：`src/crypto_quant/economics.py`
- 账本投影和快照生成：`src/crypto_quant/ledger.py`
- Estimator注册与Golden vectors：`config/estimator-registry-v1.json`、`config/estimator-golden-vectors-v1.json`
- 重放、反篡改、范围绑定和精确Decimal测试：`tests/test_economics.py`
