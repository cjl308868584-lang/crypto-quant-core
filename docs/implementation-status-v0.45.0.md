# 实施追踪 v0.45.0

日期：2026-07-30

状态：Cohort 任意 Episode 只追加 receipt 管线已实现

## 本版本完成

- 在 cohort 首槽前以提交 `33c6d7a` 冻结 v0.45–v0.48 证据流水线；
- exact 绑定 v0.43 cohort plan ID/hash/file SHA；
- 从安装证据自动派生唯一 SQLite、bundle、log 与 LaunchAgent；
- 从 cohort start 验证连续 4h 槽及所有 `REJECT_ENTRY`；
- 自动枚举窗口内全部 `ENTER_LONG` Episode 并跟踪到首次合法退出；
- 单次调用发布全部且仅全部 completed Episode，不接受 Episode 选择器；
- 每份 receipt 绑定 cohort 前缀、完整 Episode、较早 Episode ID、bundle、log、
  state、install、contract、plist 与固定 `launchctl print`；
- owner-only canonical exact publish、幂等重载及现场追加兼容；
- 新增 Schema/package mirror、observer loader、CLI、ADR 与回归测试。

## 固定信任根

- cohort plan ID：
  `challenger_episode_cohort_plan_56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c`；
- cohort plan hash：
  `20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201`；
- exact cohort plan SHA-256：
  `a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff`；
- cohort window：
  `[2026-07-30T12:00:00.000Z, 2026-10-28T12:00:00.000Z)`；
- observation tail：
  `2026-10-29T12:00:00.000Z`。

## 安全与资格

- observer network / Runner / Broker / order / state-write：
  `0/0/0/0/0`；
- 唯一外部命令：固定 argv 的一次 `launchctl print`；
- Episode/date/time/price/PnL/state/log/bundle/URL override：全部禁止；
- in-progress 或仅 `REJECT_ENTRY`：不发布 completed receipt；
- profitability：`INELIGIBLE`；
- AI comparison：`INELIGIBLE_NO_PAIRED_AI_COHORT`。

## 验证

- v0.45 聚焦及旧首 Episode 回归：22/22；
- 全量 tests：617/617；
- Schema mirror：逐字节一致；
- Golden Vector：41；
- Evaluator build input：193；
- Build input tree hash：
  `b5453a0bbe4b517b13e9a46067db85f360763b65cc3cc407890b620803cb4ea0`；
- Evaluator build hash：
  `a5751dd283268e6dcf758c116b136b856e21c0a3ca3e8afb6c80415663220c5c`；
- `make validate`：完成；生产门继续保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 下一步

v0.46 实现按 UTC 日唯一保存、可跨 Episode 复用的官方 1m ZIP/checksum/day
receipt。日期只能从全部 loader-verified completed Episode 自动派生；未到完整日
结束后 5 分钟不得请求，404 保持 pending。
