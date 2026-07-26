# ADR-0002：执行链路与UNKNOWN状态机

状态：Accepted
日期：2026-07-26

## 背景

《核心数据契约与订单状态机 v1.1》要求从策略事实到订单事实形成不可绕过的确定性链路，并明确区分“交易所已证明失败”和“结果未知”。如果超时、断连或响应不可解析被误判为失败并换新ID重试，可能产生重复仓位；如果Target、Intent或Attempt能够脱离上游批准独立生成，则执行层可能放大风控批准的风险。

## 决策

1. 实现 `StrategyProposal → MetaDecision → TargetPosition → RiskDecision → ExecutionIntent → ChildOrderAttempt` 首版契约与确定性业务ID。
2. Target按`(account_id, economic_asset)`维护唯一当前序列，现货LONG与永续SHORT共享ETH经济标的的supersession链。
3. 一个经济Intent使用稳定ID；重新定价或部分成交补单只能建立连续ChildOrderAttempt链，前序未终结或剩余量未对账时禁止盲目重试。
4. RiskGate只允许保持或缩小输入目标；部署Stage multiplier、批准资本、活动订单最坏成交、1x最坏毛杠杆、RiskLock和对账状态均参与确定性裁决。
5. ExecutionIntent必须绑定Target与RiskDecision，并用执行参考价格证明期望仓位名义金额不超过RiskDecision批准值。
6. 订单仅在请求可能已外发时进入`UNKNOWN`；只能由带`reconciliation_result_id`的交易所查询证据解析。
7. PositionExecutor按账户和经济标的单例运行；目标反向时先退出并等待交易所确认平仓，任何关联UNKNOWN都阻断重新规划。
8. 本版本仍不提供Broker、交易所Adapter、密钥读取或外部下单方法。

## 不变量

- MetaDecision不能创造StrategyProposal没有提出的方向。
- Shadow Proposal以及Candidate、Shadow、Retired决策不能进入正式Target链。
- 未通过eligibility的决策不能产生数值增仓目标。
- RiskLock不能阻止保护性减仓或平仓。
- Stage multiplier是DeploymentRegistry的权威值，不能由策略或模型覆盖。
- 活动订单按最大潜在成交计入最坏毛敞口，不能用现货/永续净额绕过1x。
- Intent数量不能超过风控批准名义金额；Attempt数量不能超过已对账剩余Intent。
- Fill可先于ACK到达；累计成交只能单调增加且不能超过订单量。
- Cancel与Fill竞态保留全部经济事实；`UNKNOWN`不能被伪造成`FAILED`。

## 备选方案

- 超时后立即换新client order ID重试：拒绝，可能产生重复订单与超额仓位。
- 为现货和永续建立两条独立ETH Target链：拒绝，会允许反向仓位并存且被净额掩盖。
- 让Executor自行重算或放宽RiskDecision：拒绝，破坏确定性风控的最终否决权。
- 立即连接Binance Testnet验证：暂缓；InstrumentMetadata、Adapter边界、对账投影和事故政策尚未完成。

## 后果

- v0.2.0可以离线验证完整执行状态语义，但不能真实或模拟连接交易所。
- InstrumentMetadata的venue规则、数量/价格舍入、最小名义金额和Adapter错误映射仍需后续实现。
- RiskLock、DeploymentRegistry、订单与Executor当前为领域对象/内存投影；持久化和从账本重建将在后续增量接入。

## 验证证据

- 核心契约：`src/crypto_quant/contracts.py`
- 风控与执行契约：`src/crypto_quant/execution.py`
- 订单与Executor状态机：`src/crypto_quant/orders.py`
- 自动化测试：`tests/test_contracts.py`、`tests/test_execution.py`、`tests/test_orders.py`
