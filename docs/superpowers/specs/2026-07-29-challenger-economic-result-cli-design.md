# v0.40 Challenger 经济结果发布 CLI 设计

日期：2026-07-29

状态：冻结

冻结基线：`v0.39.0` / `c59d072`

冻结时间：北京时间 2026-07-29 13:05，早于首个合格退出槽位 16:00。

## 1. 目标

把 v0.36 completed receipt、v0.37 plan、v0.39 owner-only archives 和 v0.38
evaluator 连接成一个无人工经济参数的离线结果发布入口。

本版本只实现 CLI 并使用 fixture 验证，不观察真实 exit、不请求真实 archive、不生成
真实 episode result。

## 2. 唯一输入

CLI 只接受以下绝对路径：

- exact v0.37 economic plan；
- v0.36 completion receipt；
- install receipt；
- LaunchAgent contract；
- plist；
- v0.39 archive output root；
- owner-only result output root。

不接受 URL、日期、symbol、execution minute、OHLC、价格、数量、slippage、fee、
capital、PnL、label、result id、result filename、strategy state 或订单参数。

## 3. 信任和计算顺序

1. 读取 exact plan bytes 并保留 committed file SHA-256；
2. 使用 v0.36 loader 复核 completion receipt，再计算 exact file SHA-256；
3. 使用 v0.39 loader 重放全部 archive receipt、ZIP、checksum 和完整日档；
4. 从 archive receipt 的 `retrieved_at` 自动选择最大值作为 `evaluated_at`；
5. 调用 v0.38 evaluator 重建唯一经济结果；
6. 以 `result_id.json` 自动派生文件名并 exact publish；
7. 立即使用 v0.38 loader 从 plan、receipt 和 archive bytes 重载；
8. 输出 result id/hash、研究净 PnL/return 和固定资格警告。

`evaluated_at` 不取 CLI 当前时间，避免同一输入因重复运行产生不同 result id。

## 4. 输出边界

- result root 必须位于当前用户
  `~/Library/Application Support/CryptoQuant/` 下；
- root 为 0700、result 为 0600；
- 同一输入重复运行产生相同路径与 exact bytes，且网络请求为 0；
- 已存在不同 bytes、symlink、权限错误或 archive 不完整时失败关闭；
- 原始 archive bytes 不复制到 result 目录，不提交 Git；
- 后续公开版本只能复制 loader 复核后的 canonical result bytes。

## 5. 安全和资格

CLI 没有 HTTP transport、Runner、Broker、balance、order 或 strategy state 能力。
result 固定是 `ARCHIVE_FORWARD_OUTCOME_RESEARCH_ONLY` 的单 episode execution
proxy；即使 net PnL 为正，也不能宣称策略可重复赚钱或 AI 优于简单基线。

## 6. 后续运行

北京时间 2026-07-29 16:10 只执行 v0.36 observer。若 episode complete，先等待
v0.39 时间门和全部 official archive verified；之后才运行本 CLI。真实 result 必须
作为新的独立版本提交，不能修改 v0.37 plan、v0.38 evaluator、v0.39 acquisition
或 v0.40 orchestration。
