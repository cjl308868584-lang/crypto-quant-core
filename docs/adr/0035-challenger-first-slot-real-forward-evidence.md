# ADR-0035：Challenger 首槽真实前向证据

日期：2026-07-29

状态：已接受

## 背景

`v0.34.0` 已在首槽前冻结只读观察器和成功、等待、漏槽边界。只有原
LaunchAgent 在预注册时间自然写入首条 decision，且 state、source bundle、日志、
安装 receipt 和当前 service 全部一致，才能发布首槽成功证据。

## 决策

1. 使用 tag `v0.34.0`（提交 `9d1895c`）的四参数 CLI 执行唯一一次成功观察。
2. 不 kickstart、bootstrap 或重跑 Runner，不覆盖时间、路径、symbol、URL 或命令。
3. 只接受首条 `scheduled_for=2026-07-29T00:00:00.000Z` 的 canonical decision。
4. SQLite 必须为 owner-only、WAL 为 0 bytes，并以 `mode=ro&immutable=1` 重放。
5. 首条 decision 必须与唯一 source bundle candidate 和 stdout 第 6 行
   `RECORDED` exact match。
6. Receipt 必须由同一 `v0.34.0` loader 立即重载；runtime 原件与 Git 副本
   canonical bytes 和 SHA-256 必须完全相同。
7. `ENTER_LONG` 仅是研究状态机 decision；系统仍无 Broker、余额读取或下单权限。
8. 首槽成功只建立不可回填的前向起点，不建立盈利、AI 优势、Paper 或生产资格。

## 真实结果

- LaunchAgent：`gui/501/local.crypto-quant.challenger-forward`；
- 观察时 runs / last exit：`6 / 0`；
- 首槽：`2026-07-29T00:00:00.000Z`；
- recorded at：`2026-07-29T00:02:06.752Z`；
- decision：
  `challenger_decision_7108b0226b32c858217ce3668d69b8cbb3efea614091a632f1c709afb80b4106`；
- decision hash：
  `c7ee6bfac0ac1da6986a9eb5089cc6cc8e2de520937935edbb8df45731b34ac7`；
- action：`ENTER_LONG`；
- source bundle hash：
  `43c7f55aefca8ccea6f204747b8e10d474cd31368c1dbf548c310b6ea16d28bf`；
- observer status：`FIRST_SLOT_RECORDED_VERIFIED`；
- observer launchctl/network/state-write/Broker/order：`1/0/0/0/0`；
- receipt id：
  `challenger_first_slot_receipt_fcc86fe447ab8b2728a9bcd80371c26c9a30f59cec0b01306b278392b28d3c2b`；
- receipt hash：
  `76acd1f21dbd0f4c71b45213a4d4d3983f7c3707ac77006b56da2675ecfa9521`；
- exact file SHA-256：
  `b1b03bbe584386d3199cef3561fe22b4c92c3f359429ec43838d2b00a9566e43`。

观察前后 state、stdout、stderr 和 source bundle 的 SHA-256 完全不变。Runtime
receipt 保持 uid 501、mode 0600、单 hardlink；Git artifact 与其 19,463 bytes
逐字节一致。

## 后果

系统已经证明预注册首槽被原调度链按时、完整、不可回填地记录，但结果仍为
`LOCAL_PREQUENTIAL_RESEARCH_ONLY`、`INELIGIBLE_NO_MATURE_OUTCOME` 和
`NO_PROFITABILITY_CLAIM`。LaunchAgent 继续积累后续 4h decision；在形成成熟退出、
完整成本和足够连续样本前，不启动新的 AI 模型搜索，也不开放任何交易权限。
