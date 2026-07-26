# ADR-0003：版本化交易规格、安全舍入与执行重放

状态：Accepted
日期：2026-07-26

## 背景

《核心数据契约与订单状态机 v1.1》要求下单使用决策时有效的InstrumentMetadata，历史规格必须保留用于重放。数量、价格、最小数量和最小名义金额处理不能通过向上取整放大风险。追加账本还必须能从不可变事件恢复订单、仓位、风险锁、部署和Executor状态，迟到旧事件不能回滚当前经济状态。

## 决策

1. InstrumentMetadata包含v1.1冻结的价格、数量、名义金额、合约乘数、订单能力、费用、有效区间、来源和确定性metadata hash。
2. Metadata Catalog保留同一instrument的全部非重叠历史版本；决策时必须精确命中一个有效版本，否则Fail-Closed。
3. Binance样例只作为离线测试Fixture，显式标记`NON_AUTHORITATIVE_TEST_FIXTURE`，不得作为交易所当前规格或实盘依据。
4. 数量始终按quantity step向下取整，并同时受max quantity和RiskDecision批准名义金额限制。
5. 新增风险限价使用更不激进的价格方向：BUY向下、SELL向上；保护性减仓使用更易成交的方向：BUY向上、SELL向下。
6. 价格取整后重新计算批准名义金额可承受的最大数量，再按step向下裁剪，保证最终计划不超过批准值。
7. min quantity或min notional只能通过放大数量满足时输出明确NO_TRADE；保护性剩余量同时标记dust，不无限追单。
8. 追加账本增加Intent、Attempt、Order、Position、RiskLock、Deployment和PositionExecutor七类带版本完整事实投影。
9. 迟到的更低entity version保留在事件账本但不回滚投影；相同entity version内容冲突时整次事件追加回滚。
10. Projection Hash绑定完整投影和源事件。任何派生投影篡改必须被检测；从零重放恢复冻结的Golden Hash。

## 不变量

- 旧InstrumentMetadata不覆盖或删除，新旧有效区间不得重叠。
- 非LIMIT订单不能携带限价或time-in-force；不支持的订单能力必须拒绝。
- Spot不能设置交易所reduce-only；永续风险缩减必须设置reduce-only。
- 任一可交易计划的rounded quantity不大于请求数量。
- 任一新增风险计划的rounded notional不大于RiskDecision批准名义金额。
- min-notional失败不得通过向上取整数量变成可交易。
- 订单累计成交不得为负或超过请求数量。
- 投影只来源于已经进入不可变事件表的事实。
- 同一事件重复到达不重复产生经济效果。
- 相同事件流从零重放产生相同Projection Hash。

## 备选方案

- 启动时只读取交易所当前规格：拒绝，无法重放历史决策。
- 数量向上满足min notional：拒绝，会放大未批准风险。
- 所有限价统一向下或向上：拒绝，不能同时表达新增风险与保护性退出的执行方向。
- 只保存内存状态机最终结果：拒绝，崩溃后无法证明订单、仓位和UNKNOWN恢复过程。
- 允许同版本“最后写入者获胜”：拒绝，会让到达顺序改变经济状态。

## 后果

- v0.3.0能离线证明规格选择、舍入和首批执行投影可重放，但没有从Binance抓取权威metadata的Adapter。
- 当前执行投影使用带版本的完整事实快照；领域状态迁移仍由v0.2.0状态机验证。
- `fills_projection`、`balances_projection`、`protective_orders_projection`和`checkpoints`仍待后续实现，不能把本版解释为完整生产账本。

## 验证证据

- 元数据与订单规划：`src/crypto_quant/instruments.py`
- 非权威Binance样例：`config/instrument-metadata-binance-v1.sample.json`
- 追加账本与执行投影：`src/crypto_quant/ledger.py`
- 舍入性质测试：`tests/test_instruments.py`
- Golden Replay：`tests/test_replay.py`
