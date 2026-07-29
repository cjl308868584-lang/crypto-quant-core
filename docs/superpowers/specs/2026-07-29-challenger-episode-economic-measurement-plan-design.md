# v0.37 Challenger Episode 经济测量计划设计

日期：2026-07-29

状态：冻结

冻结基线：`v0.36.0` / `e2c03ce`

## 1. 目标

在首个 Challenger episode 出现退出结果以前，冻结其研究经济结果的成交代理、
成本、数量、来源和计算顺序，防止看到涨跌后选择更有利的价格、费用或时间。

v0.37 只发布机器可读 economic measurement plan，不获取未来行情、不计算首个
episode 结果，也不赋予盈利、Paper、Broker 或生产资格。

## 2. 为什么不能使用 Decision Close

每条 Challenger decision 使用的是 `scheduled_for` 以前已经闭合的 4h Kline，
但 decision 在 `recorded_at` 才实际形成。把该 4h close 当作 entry/exit fill 会使用
决策形成前的价格，构成不可成交的回看偏差。

因此：

- entry execution minute 固定为 entry decision `recorded_at` **严格之后**的第一个
  完整 UTC 分钟 open time；
- exit execution minute 按 exit decision `recorded_at` 使用同一规则；
- 若 `recorded_at` 恰在整分钟，仍使用下一分钟；
- 首个真实 entry recorded at 为 `2026-07-29T00:02:06.752Z`，所以 entry
  execution minute 已冻结为 `2026-07-29T00:03:00.000Z`；
- 任何 decision close、当前 BBO、日内最好价格或手工时间覆盖均不允许替代。

## 3. 唯一允许的数据来源

每个 execution minute 必须来自 Binance 官方 ETHUSDT Spot 1m **DAILY** archive：

- `data.binance.vision/data/spot/daily/klines/ETHUSDT/1m/`；
- 同名 `.zip` 和 `.CHECKSUM` 各一次持久化获取；
- URL 必须由 `HistoricalArchiveRequest` allowlist 派生，不能由调用方提供；
- checksum、唯一 CSV member、时间单位、OHLC 和完整 1440 行必须验证；
- 精确选中的 source row、row number、raw 12 columns 和 row hash 必须封存；
- entry/exit 同日时只能绑定同一官方日档；跨日时恰好绑定两个日期；
- 官方日档尚不可用时返回 pending，不得改用网页、REST 当前 Kline、第三方或手工值；
- source archive 获取发生在 outcome 以后，因此固定为
  `ARCHIVE_FORWARD_OUTCOME_RESEARCH_ONLY`，不是 PIT market input 或真实 fill。

## 4. 冻结成交与成本

与 v0.18/v0.28 已发布保守研究规则保持一致：

- reference capital：`1000 USDT`；
- product：Binance Spot `ETHUSDT` LONG；
- price tick：`0.01 USDT`；
- quantity step：`0.0001 ETH`；
- slippage：每边 `0.001`（10bps）；
- assumed taker fee：每边 `0.0015`（15bps）；
- entry source price：entry minute `high`；
- exit source price：exit minute `low`；
- entry fill：
  `ROUND_UP(entry_high * (1 + 0.001), 0.01)`；
- exit fill：
  `ROUND_DOWN(exit_low * (1 - 0.001), 0.01)`；
- quantity：
  `ROUND_DOWN(1000 / entry_fill, 0.0001)`；
- entry notional：`entry_fill * quantity`；
- exit notional：`exit_fill * quantity`；
- entry fee：`entry_notional * 0.0015`；
- exit fee：`exit_notional * 0.0015`；
- gross PnL：`(exit_fill - entry_fill) * quantity`；
- net PnL：`gross_pnl - entry_fee - exit_fee`；
- net return：`net_pnl / 1000`；
- positive label：只有 `net_return > 0` 时为 1，等于 0 不算正。

所有运算使用固定高精度 Decimal，禁止 binary float；舍入只在上述三个明确步骤
发生。0.5% Challenger entry distance 恰好等于未计 tick/quantity rounding 的双边
10bps 滑点加双边 15bps fee，不能再把这 0.5% 从 PnL 中重复扣除。

## 5. Plan 身份与状态

Plan 必须绑定：

- v0.35 first-slot receipt id/hash 和 committed file SHA-256；
- first decision id/hash、episode id、scheduled/recorded time；
- v0.36 observer design commit、package version 和 policy hash；
- frozen entry execution minute；
- exit execution minute 派生规则；
- source contract、fill contract、cost contract 和 exact calculation order；
- plan id/self hash、registered at 和 warnings。

v0.37 的真实状态只能是：

`PREREGISTERED_WAITING_FIRST_EPISODE_COMPLETION_AND_DAILY_ARCHIVE`

不得创建带 outcome、exit row、PnL、return 或 positive label 的 artifact。

## 6. 后续评估门

只有同时满足以下条件，后续版本才可计算：

1. v0.36 frozen observer 发布并重载合法 complete episode receipt；
2. entry/exit recorded_at 推导的 execution minute 与 plan 一致；
3. 对应官方 DAILY archive 和 checksum 已真实可用；
4. source builder 对原始 bytes 完成 checksum、CSV、1440 行和 exact-row 重放；
5. evaluator 按本 plan 的 Decimal 顺序重建全部值；
6. 结果 artifact 仍标记为 execution proxy、single episode 和 profitability
   ineligible。

任何缺行、checksum 失败、source 修订、时间不一致、错误舍入、费用覆盖或 plan
hash 不匹配都失败关闭。禁止因单笔结果好坏修改 v0.37 plan；如未来采用真实账户
费率或实时 BBO，必须作为新的、前向生效的独立 policy，不能反改本 episode。

## 7. 赚钱与 AI 含义

这个 plan 让“赚了多少”至少使用统一的、成本后、较保守且决策后可实现的研究代理，
消除用信号 Kline close 冒充成交和事后选成本的伪利润。

但一笔代理结果仍不证明可重复赚钱。需要连续多个不可回填 episode，计算全样本净
收益、最大回撤、尾部损失和下置信界；只有简单 Challenger 先通过，AI 才能在相同
entry/exit minute、成本、资本和事件集合上证明配对净增量。
