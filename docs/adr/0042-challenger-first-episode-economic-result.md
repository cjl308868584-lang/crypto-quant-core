# ADR-0042：Challenger 首个 Episode 真实经济代理结果

日期：2026-07-30

状态：已接受

## 背景

v0.41 已逐字节封存首个自然完成 Episode。v0.37 在结果出现前冻结执行分钟、价格
代理、滑点、费用、资本与舍入；v0.38/v0.39/v0.40 分别冻结离线评估、官方日档
获取与无经济参数覆盖的唯一发布入口。

## 决策

1. 只接受从可信 plan 和 completion receipt 自动派生的 `2026-07-29` 官方
   ETHUSDT Spot DAILY 1m ZIP/checksum。
2. 第一次 ZIP 404 保持 pending；第二次只重试同一 allowlisted 请求，不使用
   REST、网页、第三方或手工 URL/date。
3. ZIP/checksum 通过官方校验且完整包含 1,440 行后，只使用 v0.40 离线 CLI
   自动计算并 exact publish。
4. 结果中的负 PnL、费用、标签和不合格状态必须原样提交，不允许修改或删除。
5. ZIP、checksum 和 archive receipt 保持仓库外 owner-only；Git 只封存可审阅的
   canonical result。

## 真实来源

- period：`2026-07-29`；
- retrieved at：`2026-07-30T07:44:38.317Z`；
- ZIP SHA-256：
  `8e4ebd2ab08f88e6d143b38c1c665a15affb2f0adba1e95a9e2fc3082e7ddb3d`；
- checksum file SHA-256：
  `96e061d56603920b23e561da9f51543edb5618c9c98e5a7a1a5f15d8004aeb74`；
- CSV SHA-256：
  `d25f3474af106f6054bb55ac0f42776adfd70f08e6f4944e4d56e10daeeffb06`；
- row count / range：
  `1440 / 2026-07-29T00:00:00.000Z..2026-07-29T23:59:00.000Z`；
- archive receipt hash：
  `95f00f03b25fd1cfd1635c4f2715bf1315fca7510706e62ca6adbc6fac9f6f0b`。

## 真实结果

- entry minute / source high / proxy fill：
  `00:03Z / 1925.76 / 1927.69`；
- exit minute / source low / proxy fill：
  `16:03Z / 1890.08 / 1888.18`；
- quantity：`0.5187 ETH`；
- entry / exit fee：`1.4998392045 / 1.469098449 USDT`；
- gross PnL：`-20.493837 USDT`；
- net PnL：`-23.4627746535 USDT`；
- net return：`-0.0234627746535`；
- positive label：`0`；
- result id：
  `challenger_episode_economic_result_8f2b70abf6221dc2531ecd9e6b4ada9732e8775d9673b67d4865fe7fa9b18723`；
- result hash：
  `2ac4e92fa32c3841548c433590cda3fea799702fdcda291d25866db2bd993fc4`；
- exact file SHA-256：
  `8627677275c31de573f1a59f638ba1678772115dc6d932027a36e2f8b62d9fee`。

## 后果

这个样本在冻结的保守成交代理和双边 15bps 假设 taker fee 后亏损约 2.35%，必须
作为后续累计样本的第一项保留。它不是实际成交、没有账户实际费率且只有一个
Episode，因此 `profitability=INELIGIBLE_SINGLE_EPISODE`；既不证明策略长期亏损，
也不证明盈利或 AI 优势。系统仍没有 Broker 或订单能力。
