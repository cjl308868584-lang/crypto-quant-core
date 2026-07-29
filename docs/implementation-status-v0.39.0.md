# 实施追踪 v0.39.0

日期：2026-07-29

状态：首个 Challenger episode 官方日档采集器已在 outcome 前冻结

## 本版本完成

- 在首个合格退出槽位前提交冻结设计 `2e411a7`；
- 新增 strict archive receipt Schema 的 config/package 镜像；
- 只有 exact plan 与 completed receipt 有效时才能派生唯一日期；
- 完整 UTC 日结束 5 分钟前固定 0 个网络请求；
- ZIP 404 使用 1 个请求返回 pending，checksum 404 使用 2 个请求返回 pending；
- 成功路径验证 checksum、唯一 CSV、microsecond 时间和完整连续 1440 行；
- owner-only 0700/0600 封存 ZIP、checksum 与 hash-bound receipt；
- 已验证日期重试 0 请求，跨日只获取尚未完成的日期；
- loader 直接生成 v0.38 evaluator 所需的 `daily_archives` mapping；
- CLI 不接受 URL、日期、symbol、价格、费用、订单或 strategy state path；
- 没有观察真实 exit，没有获取真实 archive，没有计算真实结果。

## 验证

- archive acquisition focused tests：9/9；
- 相邻 evaluator、plan、episode、market-data 与 execution tests：84/84；
- 全量 tests：569/569；
- Golden Vector：41；
- Evaluator build input：178；
- Build input tree hash：
  `690fb8f979fdd88af7dfc0d779d9b5cbaaf6afcdcee5eb143f493f355d6ec0e4`；
- Evaluator build hash：
  `f4b747ffff1b003c37bb3492e358fcedefa74d4854a3bfc22a2994c709ab68dd`；
- `make validate`：完成；生产门禁保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 仍未证明

- 首个 episode 尚未完成只读验收；
- Binance 对应 DAILY archive 尚未真实发布或获取；
- 仓库没有真实 economic result、真实 fill 或实际账户 fee；
- 单 episode 不能证明可重复净优势；
- AI 臂仍无获批模型和配对前向证据；
- 系统仍无 Broker、余额读取或下单能力。

## 下一步

北京时间 2026-07-29 16:10 后先用 v0.36 observer 只读验收。若 complete，封存
exact receipt，但必须等到所需日期的时间门后才调用 v0.39；archive 尚未发布时
保持 pending。全部日档 verified 后才允许 v0.38 生成研究经济代理，并作为独立版本
发布。任何 failure、missed slot、checksum 或覆盖错误都禁止回填。
