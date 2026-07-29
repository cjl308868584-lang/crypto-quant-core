# v0.38 Challenger Episode 经济结果评估器设计

日期：2026-07-29

状态：冻结

冻结基线：`v0.37.0` / `ae03b01`

冻结时间：北京时间 2026-07-29 10:55，早于首个合格退出槽位 16:00。

## 1. 目标

在首个 Challenger episode 退出结果出现以前，冻结一个纯离线、可重放的经济结果
评估器。它只把 v0.36 的完整 episode receipt、v0.37 的预注册 plan 与 Binance
官方 DAILY 1m archive exact bytes 转换为单笔研究代理结果。

本版本不观察退出、不获取市场数据、不生成真实结果，也不赋予盈利、Paper、Broker
或生产资格。

## 2. 输入信任链

评估器只接受：

1. exact v0.37 plan，且 `plan_id`、`plan_hash`、policy、entry minute 与已发布
   artifact 一致；
2. 由 v0.36 loader 复核过的 `FIRST_EPISODE_COMPLETED_VERIFIED` receipt，并绑定
   receipt exact file SHA-256；
3. 由 allowlisted `HistoricalArchiveRequest` 派生的 ETHUSDT Spot 1m DAILY
   `.zip` 与 `.CHECKSUM` exact bytes；
4. 调用者提供的 `retrieved_at`，且不得早于相应 UTC 日结束。

评估器不包含 HTTP transport。官方文件尚不可用时由上层保持 pending；禁止 REST、
第三方、手工价格和月档回填。

## 3. 决策与来源验证

- entry 必须是 receipt 的第一条 `ENTER_LONG` decision，并与 v0.37 plan 完全一致；
- exit 必须是 receipt 最后一条 `EXIT_LONG_SMA20` 或
  `EXIT_LONG_VERTICAL_24H` decision；
- entry/exit execution minute 都是各自 `recorded_at` 严格之后的下一完整 UTC
  分钟；
- execution minute 的日期集合决定唯一 archive 集合：同日恰好一个、跨日恰好两个；
- 每个 archive 必须 checksum 通过、只有预期 CSV member、ASCII、恰好 1440 条连续
  1m row、覆盖完整 UTC 日；
- 时间戳按 Binance 2025-01-01 后 microsecond 格式解释；
- 每条 row 必须有 12 列、OHLC 合法、close time 精确为下一分钟减 1 microsecond；
- 结果封存 archive/checksum/CSV SHA-256、精确 row number、原始 12 列与 row hash。

## 4. 经济计算

计算必须逐字执行 v0.37 plan 的 Decimal 顺序：

1. `entry_fill = ROUND_UP(entry_high × 1.001, 0.01)`；
2. `exit_fill = ROUND_DOWN(exit_low × 0.999, 0.01)`；
3. `quantity = ROUND_DOWN(1000 / entry_fill, 0.0001)`；
4. 依次计算 entry/exit notional；
5. 每边 fee = notional × `0.0015`；
6. gross PnL = `(exit_fill - entry_fill) × quantity`；
7. net PnL = gross PnL - 两边 fee；
8. net return = net PnL / `1000`；
9. 只有 net return 严格大于 0 才标记 positive。

只允许 50 位高精度 Decimal；禁止 binary float，且除价格与数量的三个冻结步骤外不
再舍入。0.5% Challenger 距离不得重复扣除。

## 5. 输出与重放

输出 `challenger-episode-economic-result-v1`，绑定 plan、completion receipt、
decision、source、完整计算分解、结果身份与 self hash。验证器必须从 exact receipt
和 archive bytes 重新构建并进行全对象比较；任何协调篡改都失败关闭。

允许发布器只写 canonical JSON exact bytes，已存在的不同 bytes 不覆盖。v0.38
只用合成 fixture 证明评估器可执行，不发布真实 episode result。

## 6. 安全与资格

- market request count：0；
- Broker request count：0；
- order submission count：0；
- strategy state write count：0；
- Runner invocation count：0；
- 输出固定标记为 archive-forward execution proxy、single episode、
  profitability ineligible；
- 正收益也只能是一条研究样本，不能宣称策略赚钱或 AI 优于基线。

## 7. 后续运行

退出后先由 v0.36 observer 封存和重载 receipt。官方日档未出现时保持 pending。
日档可用后，独立版本获取 exact bytes、使用本评估器生成真实 result，并把 source
bytes 放在 owner-only 目录；仓库只提交可公开的 hash-bound result artifact。
