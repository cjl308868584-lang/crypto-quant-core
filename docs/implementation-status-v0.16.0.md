# 实施追踪 v0.16.0

日期：2026-07-27

状态：已完成并验证

## 本版本完成

- 新增结构化、allowlisted 的 Binance 公开历史归档请求；
- 新增无凭据、GET-only、禁环境代理、同主机重定向受限的生产 transport；
- 在解压前验证官方 `.CHECKSUM` 与归档 SHA-256；
- 对 ZIP member、大小、压缩比、文件名和 CSV 列契约失败关闭；
- 支持 Spot Kline/AggTrade、USDⓈ-M Mark Price Kline/Funding Rate；
- 冻结 Decimal、UTC、来源行身份、quality report、receipt 和 snapshot 哈希；
- 新增独立、有效期化且需审批的 `FeeScheduleSnapshot` 契约；
- 原子发布不可变快照，冲突时拒绝覆盖；
- 固定所有官方历史归档为 `ARCHIVE_REPLAY_ONLY`；
- 将生产代码、治理/包内 Schema 和 compact smoke evidence 纳入 Evaluator
  build。

## 真实官方 smoke

请求：Binance Public Data，Spot `ETHUSDT`，daily Kline，`4h`，
`2026-07-25`。首次受限 GET 获取 ZIP 和 `.CHECKSUM` 均为 HTTP 200。

- Archive SHA-256：
  `a1f42574c036d4ae7670bb163dc1b787acf20f06bee958c32e736186757dc08b`
- CHECKSUM SHA-256：
  `2413eb36a0d9f1fa90bea973bdf0c8dd0e15e4306c21427b5f543f09ceb55897`
- Receipt hash：
  `cf55a569987aea60d967692cdb9f1f016bfaa205bb1af2813a8e28f37568053b`
- Row count：6
- Quality report hash：
  `4022ead3b3df6b21c57760ef10c35522d44a4dfb7da8c9cfe05c2baeb96a0746`
- Snapshot hash：
  `4061d3286e682a7c199dcca3949aae4bd6d95cc6c0b2b38d13f4a3c03765aabd`
- PIT policy：`ARCHIVE_REPLAY_ONLY`

第二次独立受限 GET 重新获取官方 `.CHECKSUM`，其 SHA-256 与首次完全
一致；对保留在临时目录的首次 ZIP 原始字节重放 importer 后，row count、
receipt、quality report 和 snapshot hash 全部一致。验证完成后已删除
临时 ZIP、完整快照和 normalized rows，只提交 compact evidence。

## 可执行覆盖

- Catalog 算法总数：58
- 可执行 Estimator：26
- 明确不可执行并失败关闭：32
- Golden Vector：41

## 最终验证证据

- Focused market-data tests：58 项，0 失败
- 全量测试：274 项，0 失败
- Golden report hash：
  `e3e7dc45865d860489514a574c64ca14a8dd6f089a0b74129414231741882fc3`
- Evaluator build hash：
  `455445cd10ddb78baa0013ca3be6ac11be41fc0229370844f73e1580d33ef931`

## 赚钱与 PIT 含义

真实来源不等于真实盈利证据。事后官方归档只能证明这次摄取时收到的
字节及其解析结果，不能证明系统在历史决策时刻已收到相同数据；它不能
通过 PIT/split gate。本版本也没有真实账户费率、成交、滑点、决策、
EconomicLedger 或离线 Paper Artifact。因此不能声称策略赚钱、AI
优于基线或任何 Bundle 已获得 OOS 晋级资格。

## 仍然失败关闭

- BBO、Order Book、OI、Index/Premium 与 contemporaneous receive-time
  修订链；
- 真实账户成交、实际手续费、实际滑点和 Funding cashflow；
- 真实 OOS、Shadow、Paper、Canary 经济与风控证据；
- `RISK_EFFICIENCY` 的配对 leave-out 整组复评；
- DSR/PBO；
- Broker、密钥、交易所账户 Adapter、真实订单和自动部署。

## 下一优先级

1. 建立带实际接收时间、缺口和修订链的 contemporaneous capture；
2. 用真实市场与成本事实生成离线 Paper 决策、fill、账本和统计 Artifact；
3. 绑定真实 OOS ReleaseEvidence 并继续保持 `ARCHIVE_REPLAY_ONLY`
   与 decision-eligible 数据隔离；
4. 只有在完整 Paper/Shadow 门槛通过后才考虑资金接入。
