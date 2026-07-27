# ADR-0016：官方历史归档只能作为可重放来源

状态：Accepted

日期：2026-07-27

## 背景

真实市场数据进入研究和 Paper 之前，必须同时证明来源、字节完整性、解析
结果和时间语义。官方公开归档提供真实历史事实和配套 SHA-256
校验，但事后下载无法证明这些字节在历史决策时刻已经被系统收到，也无法
证明归档后来没有被替换。

## 决策

Binance 公开归档统一标记为 `ARCHIVE_REPLAY_ONLY`。归档事实的
`available_at` 使用实际摄取时间，不回填为事件时间；这类快照可以用于
探索、确定性重放和原型验证，但不能令 `PIT_AND_SPLIT_VALID` 通过。

只允许由结构化请求生成的官方 HTTPS URL。获取链必须先读取 ZIP 和相邻
`.CHECKSUM`，验证官方 SHA-256 后才能解压、解析和发布快照。失败时不回退
到未校验字节。

URL 是定位信息，不是 Artifact 身份。相同 URL 的内容可能被修订，因此
身份绑定归档 SHA-256、checksum 文件 SHA-256、HTTP validator、receipt
hash、CSV/source-row/facts roots、quality report hash 和 snapshot hash。
每个 fact 同时保存严格 source row、source-row hash 与 normalized payload
hash；验证时重新调用 family parser 并逐字段比较。归档 fact 还显式保留
`ingested_at`，且必须与 `available_at` 及 snapshot `ingested_at` 相等。

所有这些 self-hash 只能证明内部一致，不能凭空产生外部信任。receipt
anchor 只覆盖来源链，不能覆盖 `snapshot_id`、`recorded_at` 等 snapshot
层字段。完整验证必须从受信获取边界独立保存并显式提供
`trusted_snapshot_attestation_hashes`。该外部 envelope 不写回 snapshot，
并绑定 snapshot schema/parser、identity/time、receipt hash 与完整
snapshot self-hash。默认无 snapshot attestation 的 Artifact 必须失败；
只传 legacy receipt anchor 明确返回
`TRUSTED_RECEIPT_ATTESTATION_INSUFFICIENT`。协调修改 raw row、ZIP、
checksum 或任意 snapshot 字段并重算全部 self-hash，仍无法匹配原先独立
保存的 snapshot-attestation anchor。

手续费计划单独保存为带有效期和审批状态的 `FeeScheduleSnapshot`。费率
取决于产品、账户等级、折扣和生效时间，不能从 Kline、AggTrade 或当前
网页费率推导，更不能用当前费率反填历史。v0.16 没有外部签名批准器，
因此生产用途无条件返回 `FEE_SCHEDULE_PRODUCTION_UNSUPPORTED`；研究用途
按 venue/product/account tier/symbol 和有效期验证。

Funding interval 是每行来源事实，不固定为 8 小时。连续性按当前行 interval
推导下一事件；gap 默认阻断，只能通过显式 research-degraded 路径保留，
并始终携带 `RESEARCH_ONLY_DEGRADED` 资格和非空验证 reason。

## 不变量

- v0.16 只允许 `data.binance.vision` 的公开 GET，不含密钥、签名、账户
  查询、POST 或订单能力；
- 官方 checksum 通过之前不得解压或解析；
- 原始 ZIP、完整 CSV 和 normalized rows 不进入仓库；
- source URL 相同而内容哈希不同，必须视为不同来源版本；
- 无独立 trusted snapshot attestation 时，完整快照不得判为 PASS；
- `ARCHIVE_REPLAY_ONLY` 不得支持 PIT-valid OOS 或盈利声明；
- v0.16 的 Fee Schedule 不存在生产晋级路径；
- Funding gap 的 degraded artifact 只能用于研究，不能进入正式证据门。

## 备选方案

- 只记录 URL：无法识别官方原地修订，拒绝。
- 把事件时间当作历史可用时间：会制造虚假的 PIT 资格，拒绝。
- 将当前公开费率和行情一起冻结：混淆市场事实与账户专属成本，拒绝。
- 提交原始 ZIP 和全部 normalized rows：体积大且不是发布审计所需，拒绝。

## 后果

v0.16 支持 Spot Kline、Spot AggTrade、USDⓈ-M Mark Price Kline 和
Funding Rate 的只读归档重放。BBO、Order Book、OI、Index/Premium、
账户成交、真实手续费、实际滑点和 contemporaneous receive-time
修订链仍缺失。

因此，本版本只能证明真实归档摄取链确定、完整且失败关闭，不能证明策略
赚钱，也不能提供 PIT-valid OOS、Shadow、Paper 或 Canary 证据。下一步
必须建立同时捕获实际接收时间与修订链的 contemporaneous capture，并用
真实数据生成离线 Paper 的决策、成交、费用、经济账本和统计 Artifact。

## 验证证据

- 实现：`src/crypto_quant/market_data.py`、
  `src/crypto_quant/market_data_cli.py`
- 契约：`config/historical-market-data-snapshot-v1.schema.json`、
  `config/fee-schedule-snapshot-v1.schema.json`
- 真实 smoke：`artifacts/market-data/binance-public-data-smoke-v0.16.0.json`
- 自动化测试：`tests/test_market_data.py`、`tests/test_market_data_cli.py`、
  `tests/test_market_data_final_review.py`
