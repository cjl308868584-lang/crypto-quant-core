# 实施追踪 v0.26.0

日期：2026-07-28

状态：已完成并验证

## 本版本完成

- 月度 Binance Spot Kline 和 USDⓈ-M Mark Price Kline 请求、解析与完整
  覆盖验证；
- 闰月、月末和 2025-01 Spot 毫秒/微秒切换验证；
- 固定 `2023-01` 至 `2026-06` 的 42 月研究语料计划；
- 固定 ETH Spot、BTC context、ETH Mark、ETH Funding 四流，共 168 项、
  正常完整首次下载 336 个公开 GET；
- 固定 8 个季度 OOS fold、18 月滚动训练窗、最后 1 月校准和 24h
  purge/embargo；
- plan Schema、自哈希、稳定 item/fold ID、请求根和完整语义重建；
- SQLite WAL/FULL append-only 状态、15 分钟租约、失败重试和过期恢复；
- 成功 snapshot exact bytes、source/receipt/quality/attestation hash 重放；
- owner-only 原子发布、冲突拒绝及成功恢复零重复请求；
- 168 项 coverage snapshot、质量/锚定/研究 readiness 和永久
  `ARCHIVE_REPLAY_ONLY` 边界；
- 无 URL、代理、凭据、shell、Broker 或订单参数的 CLI；
- 两份新 Schema 的 config/package 精确镜像。

## 真实官方月度 smoke

使用 Binance 官方公开 `ETHUSDT` Spot 4h 月度归档 `2023-01`，首次与
独立重下载合计 4 个无凭据 GET：

- 官方 archive SHA-256：
  `5ef9f01e728f0cc9f154aeb8d9febfa8a72fd0817aca80d7358db5aef134ba6e`
- checksum file SHA-256：
  `f045392b8fa6c5328380d76c939cf2235dd43724e6b7e1fb3b6b1e7c5383052f`
- CSV SHA-256：
  `5f26a5bbfb0fe85284203ca08ddb9e38e542493e50d8ec37951257311f81d2ca`
- source-row root：
  `a07f6f828c3aa5b066384929cfe63fcb2b736e8db1e8ec362f4e96136182df92`
- 186 根 4h Kline，完整月 coverage，`FORMAL_COMPLETE`；
- 两次 archive/checksum/CSV/source-row root 全部一致；
- facts root 不同是预期行为，因为 fact 身份绑定各自真实 retrieval-time
  ingestion/availability，不能伪造为同一接收事件。

完整 compact 证据见
[binance-monthly-corpus-smoke-v0.26.0.json](../artifacts/research-corpus/binance-monthly-corpus-smoke-v0.26.0.json)。
完整 42 月语料未在发布验证中批量下载，也没有将原始 archive 或 full
snapshot 提交 Git。

## 验证证据

- 新 corpus/CLI focused tests：18/18；
- market-data focused tests：40/40；
- Golden Vector：41；
- 全量 tests：456/456；
- Evaluator build input：119；
- Build input tree hash：
  `601445db450a7515a875f8d511d2839ff30c1f3c4e8f148801d6bfad94cadb62`
- Evaluator build hash：
  `d05c86b51905b1f6eed2b1cbaaa5b3e3c2026149f5898693f4be19defaf0a7b4`

## 赚钱与 AI 含义

本版本修复的是“训练数据不连续且不可恢复”这一前置缺口，不是新增交易
信号。42 月计划和 8 fold 能减少数据挑选、窗口移动和切分泄漏，但官方
事后归档仍不能证明历史决策时的数据可用性。

当前只有 1/168 项真实 smoke，完整 corpus 的
`research_training_readiness` 仍为 `NOT_READY_INCOMPLETE_OR_INVALID`。
没有 Logistic/XGBoost、event-based 执行标签、ModelBundle、正式 OOS
Release Audit 或配对增量盈利证据，因此不得声称 AI 优于基线或策略赚钱。

## 下一步

1. 在仓库外 owner-only 数据目录分批恢复执行 168 项 corpus；
2. 完成后实现同源 PIT 特征、24h event-based 保守执行标签和低维
   Logistic 研究基准；
3. 同时继续等待只读账户凭据和真实 Futures 连通性，启动连续
   context-complete Paper；
4. 只有基线、AI 配对增量和正式 PIT/Forward 门全部通过后才讨论资金。
