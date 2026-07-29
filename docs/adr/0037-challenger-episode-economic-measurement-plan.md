# ADR-0037：Challenger Episode 经济测量计划

日期：2026-07-29

状态：已接受

## 背景

v0.36 在退出结果前冻结了首个 episode 的完成边界，但 decision 使用的 4h close
早于实际 `recorded_at`。若用该 close 作为 fill，或者看到结果后选择 BBO、分钟
价格与费用，都会产生不可成交或事后选择的伪利润。

首个 episode 最早在 `2026-07-29T08:00:00.000Z` 才有退出资格，因此经济测量
也必须在该时点以前冻结。

## 决策

1. 北京时间 2026-07-29 10:05，以提交 `dd3ab06` 冻结完整设计。
2. entry/exit execution minute 都是 decision `recorded_at` 严格之后的下一完整
   UTC 分钟；整分钟 recorded_at 也使用下一分钟。
3. 唯一来源是 checksum 验证通过的 Binance ETHUSDT Spot 官方 DAILY 1m archive。
4. entry 使用 minute high 加 10bps 后向上按 0.01 USDT 舍入；exit 使用 minute
   low 减 10bps 后向下舍入。
5. 以 1000 USDT 为 reference capital，quantity 向下按 0.0001 ETH 舍入，并扣
   entry/exit 各 15bps assumed taker fee。
6. 计算顺序固定为 fill、quantity、notional、fee、gross PnL、net PnL、net return
   和严格大于零标签；全部使用 Decimal。
7. 不允许调用方覆盖 price、time、fee、URL 或 fallback source。
8. v0.37 只发布 plan；不得获取未来 outcome、填写 exit、计算 PnL 或宣称盈利。

## 真实预注册结果

- plan registered at：`2026-07-29T02:15:24.000Z`；
- plan id：
  `challenger_episode_economic_plan_e5c86696889d209373ce536ee0f54be72e59d7de96b6868cd5ab0358491985a4`；
- plan hash：
  `fa43e1bb24ac0e9d70c82a3d09f03ca43a5f99c429f43e6c67d6e68029732831`；
- policy hash：
  `32c81160e936caf4253e0eabe46104fde5f6b747e0525fa2ea916c028dea82f9`；
- source v0.35 receipt file SHA-256：
  `b1b03bbe584386d3199cef3561fe22b4c92c3f359429ec43838d2b00a9566e43`；
- entry recorded at：`2026-07-29T00:02:06.752Z`；
- frozen entry execution minute：`2026-07-29T00:03:00.000Z`；
- market/Broker/order/state write count：`0/0/0/0`；
- status：
  `PREREGISTERED_WAITING_FIRST_EPISODE_COMPLETION_AND_DAILY_ARCHIVE`。

Artifact 中没有 exit execution minute、source row、PnL、return 或 positive label。

## 后果

后续结果只能按该 plan 计算；官方日档尚不可用时必须 pending，不得换源。即使单笔
成本后代理为正，仍是 archive outcome research proxy，不是实际成交或可重复盈利
证明。只有积累足够多的连续前向 episodes 并通过净收益、回撤、尾部风险和下置信界，
简单 Challenger 才有 Paper 资格；AI 必须在完全相同的事件与成本合同上证明增量。
