# v0.39 Challenger Episode 官方日档获取设计

日期：2026-07-29

状态：冻结

冻结基线：`v0.38.0` / `699d60e`

冻结时间：北京时间 2026-07-29 12:08，早于首个合格退出槽位 16:00。

## 1. 目标

为 v0.38 离线经济评估器提供唯一、可恢复、owner-only 的 Binance 官方 DAILY
1m archive 获取入口，消除人工下载、手工 URL、手工日期和无法证明获取时刻的问题。

本版本只实现并用 fixture 验证采集能力，不观察真实 exit、不请求真实 archive、不计算
真实经济结果。

## 2. 前置条件

采集器只有在以下输入全部有效时才能派生请求：

1. exact v0.37 economic plan；
2. 由 v0.36 loader 复核的
   `FIRST_EPISODE_COMPLETED_VERIFIED` receipt；
3. v0.38 evaluator 从 entry/exit `recorded_at` 派生出的唯一日期集合；
4. owner-only 绝对输出根目录。

没有 completed receipt 时不能接受调用方日期或 URL，也不能发起任何请求。

## 3. 时间门

每个 UTC 日期只有在该日完整结束后 5 分钟才允许首次请求：

`eligible_at = next_utc_day_start + 5 minutes`

- `now < eligible_at`：返回 `ARCHIVE_ACQUISITION_NOT_YET_ELIGIBLE`，网络请求为 0；
- 时间必须是 canonical UTC millisecond；
- 不能用文件修改时间或本机目录时间代替显式 `retrieved_at`；
- 时间门只避免明显的未闭合日档，不保证 Binance 已发布文件。

## 4. 唯一请求与 pending

请求必须由 `HistoricalArchiveRequest` allowlist 构造：

- provider：Binance public data；
- market：Spot；
- symbol：ETHUSDT；
- family：Klines；
- interval：1m；
- period kind：DAILY；
- 方法：无凭据 HTTPS GET；
- 禁止调用方 URL、redirect 到其他 host、代理凭据、REST、网页或第三方 fallback。

对每个未完成日期：

1. 请求 `.zip`；
2. zip 为 404 时立即返回 pending，该日期请求数为 1；
3. zip 为 200 后请求 `.CHECKSUM`；
4. checksum 为 404 时返回 pending，该日期请求数为 2；
5. 其他非 200、redirect、transport、checksum、ZIP、CSV 或覆盖错误均失败关闭。

pending 不创建成功 receipt，不把 404 伪报为失败归因或成功。

## 5. 完整验证与封存

成功日档必须通过 v0.38 相同验证：

- official checksum；
- 唯一预期 CSV member；
- ASCII 与 12 columns；
- 2025-01-01 后 microsecond 时间；
- 连续完整 1440 条 1m row；
- OHLC、close time 与整日覆盖；
- entry/exit 所需 exact row 存在。

owner-only 目录固定使用 0700，ZIP、CHECKSUM 和 receipt 使用 0600。receipt 绑定：

- v0.37 plan id/hash/file SHA；
- v0.36 completion receipt id/hash/file SHA；
- request 与 eligible/retrieved time；
- archive/checksum/CSV/source-row hashes；
- exact selected rows；
- 请求计数与无 Broker/order/state/Runner 边界；
- receipt id/self hash。

ZIP/checksum exact bytes 不提交 Git。仓库后续只提交不泄露凭据的经济 result。

## 6. 可恢复与幂等

- 已存在且 exact replay 合法的日期：返回 verified，网络请求为 0；
- 已存在相同 partial exact bytes：允许继续完成；
- 已存在不同 bytes、不同 receipt 或 symlink/hardlink/权限错误：失败关闭；
- 同日重复调用不得重新下载或覆盖；
- 跨日 episode 可以先封存第一日，第二日 pending；后续只请求第二日；
- 全部日期 verified 后 loader 返回 v0.38 所需的 `daily_archives` mapping。

## 7. CLI

CLI 只接受 plan path、completion receipt path、install receipt、contract、plist 和
archive output root；不接受 date、URL、symbol、price、fee、order 或 strategy
state path。CLI 必须先用 v0.36 loader 复核 receipt，再调用采集器。

## 8. 赚钱与 AI 含义

这个版本不增加收益，只提高“赚了多少”的来源可信度和可重放性。单笔结果仍不能
证明可重复赚钱；简单 Challenger 累积足够前向 episode 并通过成本后风险门以前，
AI 不得用更复杂模型掩盖基线失败。
