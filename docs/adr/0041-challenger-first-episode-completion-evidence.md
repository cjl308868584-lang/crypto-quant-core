# ADR-0041：Challenger 首个 Episode 完成证据

日期：2026-07-30

状态：已接受

## 背景

`v0.36.0` 在退出结果出现前冻结了首个 Episode 的成功、进行中、漏槽和失败边界。
LaunchAgent 随后自然记录了五条 Episode decision，并在
`2026-07-29T16:00:00.000Z` 首次合法返回 `FLAT`。

## 决策

1. 使用与 tag `v0.36.0` 一致的 observer 代码和 v0.35 冻结的四个绝对路径执行
   唯一成功观察。
2. 不触发 Runner、kickstart、bootstrap、市场请求、Broker、订单或策略 state
   写入。
3. 只接受 `FIRST_EPISODE_COMPLETED_VERIFIED`，并立即使用同版本 loader 重载。
4. 将 runtime receipt 的 66,839 个 exact bytes 原样封存为 v0.41 artifact。
5. v0.41 只发布完成证据；官方日档及真实经济结果必须作为后续独立版本。

## 真实结果

- Episode id：
  `challenger_episode_45c86b2c0c1610d890c2d956915803c4b375b2838a66215f3f87311c8342be91`；
- entry / exit slot：
  `2026-07-29T00:00:00.000Z / 2026-07-29T16:00:00.000Z`；
- exit action：`EXIT_LONG_SMA20`；
- Episode / observed decision count：`5 / 7`；
- source bundle / matched stdout count：`5 / 5`；
- state / stdout / stderr SHA-256：
  `bc6ff15d8dde1e0e864a7ab907b4ad9efc65fd405351d30aa73997480e3c73b1` /
  `9b60c6a51a12e44ef7d7b0e0534541a7f92bb145f82ba06a0c940bee02e03918` /
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；
- observer launchctl/network/state-write/Broker/order：`1/0/0/0/0`；
- receipt id：
  `challenger_first_episode_receipt_ce39f2d82ee8eb116426e4073991c1af08480ddf25529574e13a976dfe2a2ed5`；
- receipt hash：
  `7c819d67693455c686d3f664290df6f85ed68887eefa917f564edd745e4fd8ff`；
- exact file SHA-256：
  `3c99f074df3029658d1a0569415259250c2043718f75446345999160ff293a06`。

观察前后 state、stdout 和 stderr 哈希不变。Runtime receipt 保持 uid 501、mode
0600、单 hardlink；Git 副本与其逐字节一致。

## 后果

首个 Episode 的自然进入、持有与退出路径已经形成不可回填证据，但单 Episode 仍
不能证明正期望。v0.39 只允许在时间门后获取由 receipt 派生的官方日档；首次真实
请求返回 ZIP 404，因此保持 pending，未运行 v0.40 经济结果 CLI。AI 臂仍无批准
模型或交易权限。
