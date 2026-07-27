# 实施追踪 v0.30.0

日期：2026-07-28

状态：前向记录能力完成；首槽尚未发生；零真实决策

## 本版本完成

- 把 v0.29 唯一预注册 challenger 实现为确定性 4h 事件流状态机；
- 固定 21 根 ETHUSDT Spot 闭合 Kline、成本距离与正动量双条件入场；
- 固定 8h 最短持有、SMA20 退出、24h vertical exit 和同槽优先级；
- 被拒绝的入场保持 FLAT，不创建 episode、不消费未来窗口；
- 相邻决策要求 20 根重叠 Kline 完全一致，任何历史输入修订失败关闭；
- 首槽、4h cadence、record deadline、availability 和连续性全部强制校验；
- 新增 owner-only append-only SQLite WAL，支持 exact retry 幂等、冲突拒绝、
  UPDATE/DELETE trigger 和 reopen semantic replay；
- 新增严格 Snapshot Schema、自哈希、语义重建、原子发布与加载；
- 模块不连接 Broker、Order、余额、持仓或真实下单。

## 冻结策略

策略：
`SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2`

- `latest_close / prior_sma20 - 1 >= 0.005`；
- `ln(latest_close / close_5_bars_ago) > 0`；
- policy hash：
  `2ef83c7c73fff8b163d9bad8527921bd0d87e60595680236e936254536c800e4`；
- registration hash：
  `885b33d3a91eae1d5822fe12c16773a446c23e702f9a4110ef32f474157fa27f`；
- forward start：
  `2026-07-29T00:00:00.000Z`。

## 真实状态

版本证据记录于 `2026-07-27T21:46:37.000Z`，早于注册的 forward start。
因此：

- decision count：0；
- snapshot：未创建；
- outcome：未观察；
- forward/Paper/Release/Profitability：全部不合格；
- 状态：
  `WAITING_FORWARD_START_NO_DECISIONS`。

完整紧凑证据见
[binance-challenger-forward-not-run-v0.30.0.json](../artifacts/challenger-forward/binance-challenger-forward-not-run-v0.30.0.json)。

## 验证

- v0.30 focused tests：8/8；
- 相同输入 100 次 deterministic exact match；
- Schema 与 package mirror exact；
- 全量 tests：499/499；
- Golden Vector：41；
- Evaluator build input：141；
- Build input tree hash：
  `63166ae5e0db16e3ef637595798597c8cf9dc8403a187f889e358401c9fa7294`；
- Evaluator build hash：
  `1aca49f771ec334665999f46922cebf942f2e7db9c696e759747f6fa6b93b27e`；
- `make validate` 完整执行成功；政策结果继续按设计为 `FAIL`，因为正式绑定
  未提供且生产激活关闭。

## 赚钱含义

本版本仍未证明赚钱。它解决的是“未来如何留下不可回填、可重放的策略决策”
这一证据问题，而不是把 fixture 或历史回放包装成收益。只有开始实时积累连续
forward 决策，并在对应未来结果揭晓后使用冻结成本和成交规则评估，才可能逐步
形成赚钱与否的证据。

下一步是配置实时公开数据采集和独立外部时间锚，从注册首槽开始持续写入记录。
任何错过的槽位必须永久记为缺失，不能事后补写。
