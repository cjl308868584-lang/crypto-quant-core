# 实施追踪 v0.16.0

日期：2026-07-27

状态：已完成并验证

## 本版本完成

- 新增结构化、allowlisted 的 Binance 公开历史归档请求；
- 新增无凭据、GET-only、禁环境代理、同主机重定向受限的生产 transport；
- 在解压前验证官方 `.CHECKSUM` 与归档 SHA-256；
- 对 ZIP member、大小、压缩比、文件名和 CSV 列契约失败关闭；
- 支持 Spot Kline/AggTrade、USDⓈ-M Mark Price Kline/Funding Rate；
- 冻结 Decimal、UTC、严格 source row、source/payload hashes、完整 quality
  report、receipt roots 和 snapshot 哈希；
- 完整验证要求在 Artifact 外独立保存的 trusted snapshot attestation；该
  envelope 绑定 receipt 与完整 snapshot hash，receipt-only 明确不充分；
- Kline 保留所有已验证 volume/trade/taker/open/close 字段；
- 每个 fact 显式保留 `ingested_at`，归档模式下与 fact `available_at` 及
  snapshot `ingested_at` 严格相等；
- Funding interval 由每行 source 值驱动，允许 schedule change；gap 只能
  生成永不 formal/PIT/pass 的 `RESEARCH_ONLY_DEGRADED` 研究快照；
- 新增按 venue/product/account tier/symbol 和有效期分组的独立
  `FeeScheduleSnapshot`；v0.16 生产用途无条件失败关闭；
- 原子发布不可变快照，冲突时拒绝覆盖，并在每个幂等 commit point
  重验 final-name inode/bytes；
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
  `fb70e609054a1d32c5a350bb4b623a076ac46c605e0236611726c5a5190b6b84`
- Source-row root：
  `9f8a6349342061ce65bea467bd5f1ac1619e481fed945c852ad15ad81eb70cbf`
- Facts root：
  `c315367ef3b9fd664118c972dc57fe0ad67c6959b7d74b8ae777b9f3cb099039`
- Row count：6
- Quality report hash：
  `6e1a9aab31fbdae54fbac2fd34fc366d2f09bca546574a178feb4c7e46351b60`
- Snapshot hash：
  `0930b265622811a4d73e9704f4eab0ddd1d7b0bf62ee248934553d55538d324a`
- External snapshot-attestation hash：
  `042f6bcfa291f7343b1b3b0f8e1fbcba209f7d29eb825ac1b487b35372c00d2d`
- PIT/quality：`ARCHIVE_REPLAY_ONLY` / `FORMAL_COMPLETE`

第二次独立受限 GET 重新获取 ZIP 与官方 `.CHECKSUM`，其 SHA-256 与首次
完全一致；用相同观测时间重放 importer 后，receipt、source-row/facts
roots、quality report、snapshot hash 和完整 snapshot bytes 全部一致。
全部 6 个 fact 的 ingestion/availability/snapshot 时间交叉验证通过。
external snapshot-attestation hash 也与重放完全一致。显式 trusted
snapshot attestation 验证 reasons 为空；无锚验证只返回
`TRUSTED_SNAPSHOT_ATTESTATION_REQUIRED`；receipt-only 返回
`TRUSTED_RECEIPT_ATTESTATION_INSUFFICIENT` 且不能 PASS。`recorded_at=2099`
和 `snapshot_id` 改写并重算 snapshot hash 均返回
`TRUSTED_SNAPSHOT_ATTESTATION_MISMATCH`。验证完成后完整临时快照已移至系统
废纸篓，仓库只提交 compact evidence。

## 可执行覆盖

- Catalog 算法总数：58
- 可执行 Estimator：26
- 明确不可执行并失败关闭：32
- Golden Vector：41

## 最终验证证据

- Focused market-data tests：75 项，0 失败
- 全量测试：291 项，0 失败
- Golden report hash：
  `e3e7dc45865d860489514a574c64ca14a8dd6f089a0b74129414231741882fc3`
- Build input tree hash：
  `8b8e759e226acb57d79ca9c9161e5d226b86c17effa9116c924e6f027611a544`
- Evaluator build hash：
  `2538bc3eec3a33a921cc7141d118bd4277eb9d703eeabeedf3d71d3267c8121f`

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
