# ADR-0038：在 Episode 退出前冻结离线经济评估器

日期：2026-07-29

状态：Accepted

## 决策

在首个合格退出槽之前发布 v0.38 纯离线评估器。它只接受 v0.37 exact plan、
v0.36 loader 复核的 completed receipt，以及 checksum 通过的 Binance 官方
ETHUSDT Spot DAILY 1m exact bytes。

评估器不含 transport，不接收价格、时间、费率或 URL 覆盖。它从 decision
`recorded_at` 派生 execution minute，验证完整 1440 行日档，封存 exact raw row，
并按 v0.37 的固定 Decimal 顺序计算保守成本后研究结果。

## 理由

只冻结 plan 仍可能在看到结果后改变解析器、缺行处理、跨日来源、舍入或计算顺序。
在 outcome 前同时冻结可执行评估器，才能把后续盈亏限制为“输入变化”，而不是
“规则变化”。

## 后果

- 官方日档未可用时只能 pending，不能用 REST 或第三方替代；
- 单笔正收益仍不构成可重复优势或 AI 增量；
- archive 行是事后研究成交代理，不是真实 fill；
- 实际账户手续费、真实滑点与 90 天连续 Paper 仍需独立证据；
- 评估器测试期间网络、Broker、订单、Runner 和策略 state 写入均为 0。
