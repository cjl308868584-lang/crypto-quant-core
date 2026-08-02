# ADR-0056：System Paper 确定性单槽运行时

日期：2026-08-02

状态：已接受

## 背景

v0.55 只冻结了无凭据 `BASELINE_ONLY` System Paper 计划。在启动 90 天计时前，
系统必须证明一个自然槽能把冻结公开输入确定性地转化为决策、风险裁决、
模拟订单/成交、经济账本、持仓对账和可验证快照，且不扩大凭据、账户、真实
Broker 或真实订单权限。

## 决策

1. 实现纯内存、Decimal-only 的确定性模拟 Broker；成交价固定使用 BBO 加单边
   10bps 滑点，费用固定为 15bps taker fee，不读时钟、随机数、文件或网络。
2. 所有订单事件通过已有 `OrderAggregate` 重放；支持部分成交、拒绝、取消、
   超时、断线、UNKNOWN、重复事件和超量成交失败关闭。可解析部分成交或断线结果
   必须在同槽确定性对账至终态；无法解析的 UNKNOWN 保持 RiskLock 并阻断后续新风险。
3. 运行时只接受与冻结计划一致的 `BINANCE_MARKET_DATA_ONLY` / `BINANCE:SPOT:ETHUSDT`；
   provider、市场类型、symbol、instrument id、contract multiplier、元数据生效时间和
   决策标的均必须一致。
4. 风险增加的数量上限使用含滑点的保守成交价计算，任何模拟成交名义金额
   不得超过风控批准值。
5. 账本对 BUY 记录持仓成本，对 SELL 释放加权成本并记录 realized gain/loss；快照
   同时保存持仓成本、累计已实现 PnL 和累计费用，每槽借贷必须平衡。
6. slot result 封存精确 plan、公开 market bundle、parent snapshot 与 fill scenario；
   production loader 使用这些输入完整重跑单槽并比较 canonical bytes，不只重算外层哈希。
7. 第一槽 parent 必须精确等于从冻结计划派生的 1000 USDT genesis；非首槽 loader
   必须接收按顺序的真实 parent result paths，逐个重放并验证 snapshot/slot hash 链。
8. result Schema 在 config 和 package 中逐字节镜像，载入器拒绝重复 JSON key、binary
   float、非规范 bytes、未知字段、语义伪造与不完整 parent chain。

## 后果

v0.56 证明了无凭据 System Paper 的单槽确定性运行原语与证据重放边界，但不
安装 service、不调用公开市场网络、不创建运行 state/start receipt，也不开始 90 天
计时。下一阶段仍需 WAL scheduler、崩溃恢复与故障注入；之后才是独立 deployment/install/
observer/start receipt、90 天 evaluator、tail-blind 投影与只读 Web/alerts/runbooks。

本决策不证明策略赚钱、AI 优于基线、Paper 已运行或具备实盘/Canary 资格；
`production_activation.enabled=false` 继续生效。
