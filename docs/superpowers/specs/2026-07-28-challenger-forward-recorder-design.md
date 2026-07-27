# v0.30 Challenger 事件流与前向记录器设计

日期：2026-07-28

状态：冻结

## 1. 目标

把 v0.29 预注册的
`SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2`
实现为确定性事件流状态机，并在每个连续 UTC 4h 时点把决策写入
append-only SQLite WAL。

本版本不下载历史数据、不计算 challenger 历史收益、不下单、不回填错过的
时点，也不创建盈利资格。

## 2. 固定策略

空仓入场必须同时满足：

```text
latest_close / prior_sma20 - 1 >= 0.005
ln(latest_close / close_5_bars_ago) > 0
```

- 21 根连续、已闭合 ETHUSDT Spot 4h Kline；
- 决策只使用最后一根 Kline close 后已经 available 的事实；
- LONG 后最短持有 8h；
- 8h 后 close `<= prior_sma20` 时退出；
- 24h 时强制 vertical exit；同一时点 SMA exit 优先；
- 被拒绝的空仓信号不创建 episode，也不消费未来窗口；
- 输出仅为 research decision，不生成 Broker、Order 或真实 Target。

策略注册 hash 必须等于 v0.29：
`885b33d3a91eae1d5822fe12c16773a446c23e702f9a4110ef32f474157fa27f`。

## 3. 前向时间边界

- 首个允许槽位：`2026-07-29T00:00:00.000Z`；
- UTC cadence：4h；
- 每个槽位的最新 Kline close 必须是 slot 前 1ms；
- decision recorded_at 必须 `>= slot` 且 `< slot + 4h`；
- 第一个记录必须正好是首槽；
- 后续记录必须正好是前一槽 +4h；
- 漏槽、迟到、旧槽、乱序和重写全部失败关闭；
- 本地时间约束不能替代外部时间证明，因此外部 publication attestation
  缺失时永久标记 `UNANCHORED_LOCAL_PREQUENTIAL_ONLY`。

## 4. 输入事实

每根 Kline 绑定：

- provider/market/family/symbol/interval；
- open_time、close_time、available_at；
- OHLC、source_row_hash。

要求：

- 时间连续、唯一、有序；
- OHLC 合法；
- `close_time < available_at <= recorded_at`；
- 决策事实 root 写入每条 decision；
- 输入变动必须改变 decision hash。

## 5. 状态机

状态：

- `FLAT`
- `LONG`

动作：

- `REJECT_ENTRY`
- `ENTER_LONG`
- `HOLD_LONG_MINIMUM`
- `HOLD_LONG`
- `EXIT_LONG_SMA20`
- `EXIT_LONG_VERTICAL_24H`

LONG 状态必须保存 episode_id、entry_decision_time、minimum_hold_until、
vertical_exit_at。任何状态字段均由上一条 decision replay 得到，调用方不能
直接传入。

## 6. 持久化

SQLite：

- `journal_mode=WAL`
- `synchronous=FULL`
- owner-only directory/file；
- append-only `decisions` 表；
- sequence、slot、decision_id 唯一；
- 每条记录绑定 previous_decision_hash；
- exact bytes 重试幂等，不同 bytes 冲突；
- reopen 时从 genesis 重放全部决策和经济状态；
- UPDATE/DELETE trigger 拒绝修改。

## 7. 快照

新增 `challenger-prequential-snapshot-v1.schema.json`：

- policy 与 registration hash；
- 全部 compact decisions；
- decisions root 与 chain end；
- FLAT/LONG/entry/reject/exit/missed 摘要；
- continuity status；
- state integrity；
- external time anchoring status；
- Paper/Release/Profitability 全部不合格。

没有任何 decision 时，Git 只保存
`WAITING_FORWARD_START_NO_DECISIONS` not-run 证据，不伪造快照。

## 8. 验收

- fixture 中拒绝后下一槽仍可入场；
- LONG 最短持有和两种退出路径正确；
- 100 次相同流输出一致；
- 首槽、间隔、deadline、availability 和 Kline 连续性失败关闭；
- exact retry 幂等，冲突/UPDATE/DELETE/数据库篡改失败；
- snapshot 自哈希、Schema、语义 replay 和 mirror 通过；
- 全量测试与 Evaluator build 通过；
- 提交、合并、标记 `v0.30.0`。
