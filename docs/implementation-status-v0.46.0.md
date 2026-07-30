# 实施追踪 v0.46.0

日期：2026-07-30

状态：Cohort 共享 UTC 日档层已实现

## 本版本完成

- 以独立提交 `b550f4d` 冻结 v0.46 详细设计；
- exact 绑定 v0.43 cohort plan ID/hash/file SHA；
- 安全扫描固定 v0.45 receipt 目录并逐份调用生产 loader；
- 验证 ordinal、Episode id、prior list 与 entry 顺序完整连续；
- 从全部 verified receipt 自动派生 entry/exit next-strict UTC minute；
- 对日期求并集，按日唯一保存官方 ETHUSDT Spot 1m ZIP/checksum/receipt；
- day receipt 验证完整 1440 行，但不绑定单 Episode，可跨 Episode 复用；
- 日结束后五分钟时间门、ZIP/checksum 404 pending 与断点恢复；
- owner-only 0700/0600、canonical exact publish、单 hardlink 与冲突拒绝；
- 新增 Schema/package mirror、共享 loader、CLI、ADR 与回归测试。

## 固定边界

- CLI 无 Episode id/path、日期、时间、symbol、URL、价格、费用、PnL 或 label
  selector；
- 无 completed receipt：0 network、0 write；
- 未到时间门：0 network、0 write；
- 每个缺失且 eligible 日期最多一个 ZIP GET 与一个 checksum GET；
- 已验证日期重试或同日新增 Episode：0 network；
- Broker/order/strategy-state-write/Runner：`0/0/0/0`；
- profitability：`INELIGIBLE_SOURCE_ONLY`；
- AI comparison：无新增资格。

## 验证

- v0.46 聚焦 tests：14/14；
- 旧 v0.39 archive acquisition 回归：9/9；
- 全量 tests：631/631；
- Schema mirror：逐字节一致；
- Golden Vector：41；
- Evaluator build input：197；
- Build input tree hash：
  `ca4f32df9d06cba658ded3fdc4c1bf19fb5845d8badb7220cc8b1e365146e6df`；
- Evaluator build hash：
  `dee8baf376719e4023f1a63cc129e054bc04c84b5d85b6293dcccf09b1fe6c15`；
- `make validate`：完成；生产门继续保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 真实运行状态

北京时间 2026-07-30 23:01 只读扫描真实 v0.45 receipt root，状态为
`COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES`；Episode receipt、required day、
verified day、network、Broker、order、strategy-state-write、Runner 全部为 0，
没有创建空成功 receipt 或共享 archive 目录。真实 state/stdout/stderr SHA-256
与 v0.45 首槽观察值逐字节一致。

## 下一步

v0.47 从全部 verified Episode receipts 与共享日档自动生成每 Episode
确定性经济结果和只追加 result index；不允许人工传入日期、价格、费用、PnL、
label、result id 或 filename。
