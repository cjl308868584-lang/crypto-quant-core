# ADR-0036：Challenger 首个 Episode 只读观察

日期：2026-07-29

状态：已接受

## 背景

`v0.35.0` 已证明首个预注册槽位真实产生 `ENTER_LONG`，但一条 entry decision
既没有退出，也不能回答策略是否赚钱。如果等看到退出方向或价格以后才定义
“完整 episode”，就会重新引入事后选择、删掉不利交易或改变退出解释的风险。

首个 entry 的 minimum hold 是 `2026-07-29T08:00:00.000Z`，因此设计和成功边界
必须在该时点前独立冻结。

## 决策

1. 在北京时间 2026-07-29 09:01，以提交 `1878c00` 冻结观察设计，早于首个可
   退出槽位。
2. 首个 episode 固定从 sequence 1 的 `ENTER_LONG` 开始，到同一 episode 首次
   合法返回 FLAT 为止。
3. 退出前只接受 `HOLD_LONG_MINIMUM` / `HOLD_LONG`；完成只接受
   `EXIT_LONG_SMA20` 或 `EXIT_LONG_VERTICAL_24H`。
4. 逐条交叉验证 SQLite canonical decision、唯一 source bundle 和唯一 stdout
   `RECORDED`；任何 gap、重复、state 漂移或 deadline 后缺槽都失败关闭。
5. Observer 只从 install receipt 和 contract 推导 runtime 路径，只运行一次固定
   `launchctl print`；不触发 Runner，不联网，不写 state，不调用 Broker 或订单。
6. `FIRST_EPISODE_IN_PROGRESS_VERIFIED` 不发布 receipt；只有
   `FIRST_EPISODE_COMPLETED_VERIFIED` 才发布 owner-only canonical receipt。
7. Receipt loader 允许 state/log 后续追加，但必须证明首个 episode 的 decision
   prefix、bundle 文件和 log prefix 未变化。
8. 不从 decision bar close 计算收益：当前 registration 没有冻结可成交价格、
   手续费、滑点和仓位规模，单 episode 也不能建立统计优势。

## 真实进行中结果

使用实现提交 `8cf09e408296f044230c3e2631d9d139738c4e22` 和 v0.35 的四个冻结
绝对路径，于 `2026-07-29T01:17:00.579Z` 只读观察：

- status：`FIRST_EPISODE_IN_PROGRESS_VERIFIED`；
- episode：
  `challenger_episode_45c86b2c0c1610d890c2d956915803c4b375b2838a66215f3f87311c8342be91`；
- decision count：1；
- next slot：`2026-07-29T04:00:00.000Z`；
- minimum hold：`2026-07-29T08:00:00.000Z`；
- vertical exit：`2026-07-30T00:00:00.000Z`；
- LaunchAgent runs / last exit：`6 / 0`；
- receipt published：false；
- launchctl/network/state-write/Broker/order：`1/0/0/0/0`。

观察前后：

- state SHA-256：
  `3d79a67cc8e917c00a7b620e67f82aa47b9985bbcdd1eaa663222a8a6247e0b9`；
- stdout SHA-256：
  `0262f4ce551b09b201b0b4a317f50962523433df4b1f4fb69a3dced8a62ada95`；
- stderr SHA-256：
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

三者哈希和文件 stat 均未变化；未创建 first-episode receipt 目录或成功文件。

## 后果

首个 episode 的未来结果现在只能落入事前冻结的进行中、合法完成或失败关闭路径，
不能因结果好坏改变定义。v0.36 证明观察机制就绪和当前前缀完整，不证明盈利。
LaunchAgent 保持原策略和原调度继续运行；后续版本使用本版本观察器封存自然成熟的
首个 episode，再单独冻结全成本成交代理并累计足够多的前向 episode。

AI 仍没有获批模型或交易权限。只有简单 Challenger 在相同成本和时间条件下先建立
可重复净优势，AI 才有资格以配对增量方式竞争。
