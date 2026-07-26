# ADR-0004：未审批治理模板与会计事实重放

状态：Accepted
日期：2026-07-26

## 背景

《开发路线与验收门槛 v1.1》第9节要求Phase 0建立ExperimentManifest、DataQuality、Split、StatisticalDesign、Accounting、CostAllocation、ForwardControl和事故报告模板。模板既要足以冻结后续研究和盈利证据，又不能仅因文件存在就被当成批准政策。账本还缺少逐Fill、余额、保护单与Checkpoint，无法完整证明订单经济事实、保护覆盖和启动恢复。

## 决策

1. 使用统一`governance-artifact-v1.schema.json`校验八类治理Artifact模板。
2. 所有模板固定为`TEMPLATE_UNAPPROVED`、`production_eligible=false`、无artifact ID、无审批人、无审批时间、无内容hash和无审批证据hash。
3. ExperimentManifest模板覆盖谱系、代码/环境、数据、经济定义、Trial预算和全部成功/失败产物；失败Trial不得从历史中删除。
4. DataQuality模板分别冻结SPOT LONG与USDT_PERP SHORT的required/context/not-applicable矩阵。
5. Split模板固定8个季度OOS折、18个月滚动训练、独立校准、12个月Sealed Audit和Initial一次执行限制；绝对时间、Purge/Embargo与数据hash仍必须在具体Release前填写。
6. StatisticalDesign模板固定Geyer ESS、最低80% achieved power、一侧95%区间和Holm family-wise 5%；最小效应、CI宽度及Bootstrap/ECE算法仍须事前填写。
7. Accounting模板固定USDT、移动加权平均、逐Fill、独立Fee/Funding事实、非USDT FxValuation及窗口末保守可执行平仓。
8. CostAllocation模板强制记录基础设施、AI推理、训练、监控审计成本，禁止在权益路径和增量指标中重复扣除。
9. ForwardControl模板冻结45/90天模型年龄、30决策OOD 30/50%、连续20 Fill成本1.5倍、30笔AI影响交易和12/15/20%回撤伤害边界。
10. Incident模板包含等级、时间线、影响、根因、补偿事件、修复动作和防复发测试；事故报告本身不解除RiskLock。
11. 账本新增逐Fill不可变投影，按`account + market_scope + exchange_trade_id`恰好一次入账。
12. Balance和ProtectiveOrder使用版本化全状态事实；ACTIVE保护单必须覆盖对应实际仓位。
13. Checkpoint绑定紧邻前一事件的Ledger Hash与当前State Projection Hash；订单累计Fill未与逐Fill事实对齐时禁止建立Checkpoint。

## 不变量

- 模板存在不能消除ReleaseGatePolicy中的任何缺失binding。
- 模板不能携带审批字段或生产资格。
- Schema缺字段、多字段、非法日期、改变固定会计/统计/前向边界均Fail-Closed。
- 同一exchange trade ID的重复REST/WS事实不重复影响经济状态；内容冲突回滚整个事件追加。
- Fee与Funding不得通过修改Fill价格隐式吞并。
- Fill quantity/price必须为正，Fee不能为负。
- Balance available + locked不能超过total。
- Spot保护必须为保护性SELL；永续保护必须使用reduce-only载体。
- ACTIVE保护数量不得小于实际Position数量。
- Checkpoint不能在Order累计成交与Fill事实不一致时建立。
- 从零重放后所有投影与Checkpoint Hash一致。

## 备选方案

- 只提供空白Markdown模板：拒绝，无法校验冻结字段或防止缺项。
- 将模板ID直接写入ReleaseGatePolicy：拒绝，模板未经过数据、统计、会计和人工审批。
- 只在Order保存平均成交价：拒绝，无法支持部分成交、Fee、Funding和精确重放。
- 按WebSocket事件次数累计Fill：拒绝，REST/WS重复会重复记账。
- 创建Checkpoint但不校验经济投影：拒绝，会把未对账状态固化为恢复起点。

## 后果

- v0.4.0建立了可复制填写的治理骨架和完整命名投影首版，但没有批准任何政策。
- 实际政策Artifact必须另行产生不可变ID、content hash、审批证据，并在结果揭晓前冻结。
- 当前Checkpoint是本地恢复证据，不替代交易所ReconciliationResult。
- Evaluator的安全AST、动态引用和完整Evidence Scope比较仍待后续实现。

## 验证证据

- 治理Schema：`config/governance-artifact-v1.schema.json`
- 八类模板：`config/templates/`
- 模板加载与校验：`src/crypto_quant/governance.py`
- 配置验证脚本：`scripts/validate_governance_templates.py`
- 账本投影：`src/crypto_quant/ledger.py`
- 治理测试：`tests/test_governance.py`
- 扩展Golden Replay：`tests/test_replay.py`
