# v0.16 真实历史数据与成本事实只读摄取设计

状态：`APPROVED`

批准依据：项目所有者已明确全权委托，并要求无需逐项提问；本设计按既有资金安全、证据门和版本交付规则冻结。

日期：2026-07-27

## 1. 目的与边界

v0.16 建立一条对交易所只读、对本地证据库追加写入的真实数据摄取链路。它解决的是：

1. 从官方公开归档获取真实市场数据；
2. 在进入研究、回测或 Paper 之前验证来源、完整性、结构和时间语义；
3. 生成可哈希、可重放、可审计的规范化快照；
4. 将公开市场成本事实与账户专属成本假设严格分离；
5. 明确一份数据是否有资格支持 Point-in-Time（PIT）决策证据。

v0.16 不包含：

- API Key、签名请求、账户查询、订单或 Broker 能力；
- 自动交易、实盘资金启用或 Release Gate 放宽；
- 使用当前费率反填历史、把滑点假设伪装成源事实；
- 仅凭历史归档宣称数据在历史决策时已经可用；
- 直接产出“策略赚钱”的结论。

## 2. 已核实的权威外部事实

采用 Binance 官方公开数据仓库和官方 API 文档作为 v0.16 的源契约基线：

- 官方公开数据按日或按月提供，日文件通常次日可用，月文件通常在每月第一个星期一可用。
- 每个 ZIP 旁提供 `.CHECKSUM`，官方示例使用 SHA-256 校验。
- 官方明确说明归档文件可能因发现问题而被后续替换，因此 URL 不是不可变身份，必须保存内容哈希和校验文本哈希。
- Spot 归档自 2025-01-01 起时间戳为微秒；此前为毫秒。USDⓈ-M 公开示例仍以毫秒表达。
- Spot Kline 和 AggTrade 的列定义可追溯到官方 REST 端点；公开市场数据可走无需密钥的 market-data-only 端点。
- 公共 API 的数据源可能存在异步延迟；事件时间不能自动等同于系统当时可合法使用的时间。

权威链接：

- <https://github.com/binance/binance-public-data/blob/master/README.md>
- <https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md>
- <https://developers.binance.com/en/docs/products/spot/rest-api>

## 3. 方案比较与选择

### 方案 A：REST 响应直接写入经济账本

优点是路径短。缺点是分页、速率限制、请求时间和源字节都难复现，并且会混淆市场事实与成交/资金事实。拒绝。

### 方案 B：只做本地 CSV 解析器

确定性较好，但下载来源、官方校验、归档修订和安全边界均留给人工，无法形成完整证据链。拒绝作为最终方案。

### 方案 C：受限公开归档获取 + 原始收据 + 规范化快照

将获取、校验、解析、资格判定分层；只允许官方 HTTPS 主机和已知路径语法；保存官方校验、原始文件哈希、解析规则版本和质量结论。账户费率另建有效期快照。采用。

## 4. 架构

```text
HistoricalArchiveRequest
  → BinancePublicArchiveLocator
  → PublicArchiveFetcher (HTTPS GET only, no headers/secrets)
  → raw ZIP + CHECKSUM bytes
  → ArchiveSafetyValidator
  → OfficialChecksumVerifier
  → BinanceCsvParser
  → DataQualityEvaluator
  → HistoricalMarketDataSnapshot
  → immutable JSON artifact / later replay consumers

FeeScheduleSnapshot (manual, effective-dated, separately approved)
  → later cost/fill model
```

核心库允许注入 transport。生产 transport 仅执行 GET；测试使用内存 transport，不依赖网络。获取失败不得退回未校验数据。

## 5. v0.16 支持矩阵

首版只支持赚钱验证最需要、且官方列契约明确的数据：

| 市场 | 数据族 | 周期 | 用途 |
|---|---|---|---|
| Spot | `klines` | daily、`1m/15m/4h/1d` | ETHUSDT 主交易线、BTCUSDT 市场背景 |
| Spot | `aggTrades` | daily、无 interval | 成交方向、成交密度和后续滑点校准 |
| USDⓈ-M | `markPriceKlines` | daily、`1m/15m/4h/1d` | 永续估值与强平风险上下文 |
| USDⓈ-M | `fundingRate` | monthly、无 interval | 公开 Funding Rate 事实 |

允许符号仅为 `ETHUSDT`、`BTCUSDT`。这是 v1.1 资产范围，不提供任意符号或任意 URL 入口。

不在 v0.16 首版实现 BBO、Order Book、OI、Index/Premium、账户成交、实际手续费。缺少正式必填数据时，DataQualityPolicy 继续阻止新增风险。

## 6. 核心契约

### 6.1 `HistoricalArchiveRequest`

字段：

- `schema_version`
- `provider=BINANCE_PUBLIC_DATA`
- `market`：`SPOT` 或 `USD_M`
- `data_family`
- `symbol`
- `interval_or_null`
- `period_kind`：`DAILY` 或 `MONTHLY`
- `period`

构造时生成唯一、规范化的归档 URL 和 CHECKSUM URL。调用方不能传 URL。任何不在支持矩阵内的组合都 fail-closed。

### 6.2 `PublicArchiveReceipt`

字段：

- 完整请求；
- `archive_url`、`checksum_url`；
- `retrieved_at`；
- `archive_size_bytes`、`checksum_size_bytes`；
- `official_sha256`；
- `archive_sha256`、`checksum_file_sha256`；
- ZIP 内唯一 CSV member 名；
- CSV bytes SHA-256、source-row root 和 normalized-facts root；
- `source_last_modified_at_or_null`、`source_etag_or_null`；
- `receipt_hash`。

哈希使用现有 canonical business hash 规则。URL 相同但字节变化时必须生成不同 receipt。
`receipt_hash` 只是来源内容地址，不是完整 snapshot 的独立信任来源。

### 6.3 `MarketDataFact`

统一字段：

- `fact_id`：源文件哈希、行号和规范化业务键的确定性哈希；
- `fact_type`；
- `symbol`、`market`；
- `event_time`；
- `available_at`；
- `ingested_at`；
- `source_row_number`；
- 可重放的严格 `source_row`、`source_row_hash`；
- 数据族专属 payload；
- `payload_hash`。

所有数值保留为严格 Decimal 字符串，不允许 float。所有时间转换为 UTC。
验证器必须用 request、`ingested_at`、source row number 和保存的
`source_row` 重新调用同一 family parser，并逐字段比较规范化 payload、
业务键、时间和身份。Kline payload 保留 open/close time、OHLC、volume、
quote volume、trade count、taker base/quote volume 与已验证 ignore 字段。

### 6.4 `HistoricalMarketDataSnapshot`

字段：

- `schema_version`、`snapshot_id`；
- `receipt`；
- `parser_version`；
- `availability_basis`；
- 有序 facts；
- `quality_report`；
- `pit_eligibility`；
- `quality_eligibility`；
- `snapshot_hash`。

事实按 `(event_time, source_row_number, fact_id)` 排序。相同输入、相同 `retrieved_at` 和相同解析器版本必须得到相同哈希。
生产 fetch 和两个 snapshot builder 都只能消费 opaque `VerifiedArchive`
capability；不能接受 caller 提供的 facts、archive hash 或 checksum hash
拼装快照。

完整可信 PASS 还要求一个保存在 snapshot 之外的 external snapshot
attestation。规范 envelope 至少绑定 `receipt_hash + snapshot_hash`；v0.16
同时绑定 attestation schema/type、snapshot schema/parser、
`snapshot_id` 与 `recorded_at`。attestation hash 不写入 snapshot，避免与
snapshot self-hash 形成循环。调用方必须从受信获取/发布边界另行保存并
显式传入原始 attestation hash；不能从待验证 Artifact 临时计算后自证。
离线 `historical_market_data_snapshot_reasons` 默认无该 anchor 时返回
`TRUSTED_SNAPSHOT_ATTESTATION_REQUIRED`。只传 legacy receipt anchor 返回
`TRUSTED_RECEIPT_ATTESTATION_INSUFFICIENT`，不能获得完整 PASS。任意
snapshot 字段（包括 `snapshot_id`、`recorded_at`）改写并重算
`snapshot_hash` 后都必须与原 attestation anchor 不匹配。

### 6.5 `FeeScheduleSnapshot`

手续费不是公开行情事实。单独保存：

- venue、product、account_tier、symbol；
- maker/taker Decimal rate；
- `effective_from`、`effective_to_or_null`；
- source reference、recorded_at；
- lifecycle 和 approval；
- content hash。

未批准费率不得进入正式经济 PnL。v0.16 只冻结契约和验证，不将当前网页费率反推到历史。
overlap 按 `(venue, product, account_tier, symbol)` 分组。由于 v0.16
没有外部签名批准器，`usage_environment=PRODUCTION` 无条件返回
`FEE_SCHEDULE_PRODUCTION_UNSUPPORTED`；caller 自填姓名、时间并重算 content
hash 不能晋级。结构有效的 `RESEARCH` 合约仍可用于研究。

## 7. 时间与 PIT 语义

系统已有不变量：

`event_time <= available_at <= ingested_at <= recorded_at`

归档数据采用以下保守规则：

- `event_time` 来自源行。Kline 使用 `close_time`，因为收盘前不能使用完整 Kline；AggTrade 使用成交时间；Funding 使用结算时间。
- `ingested_at` 与 `recorded_at` 由本次摄取时钟提供。
- `available_at` 对离线官方归档设为 `ingested_at`，不伪造历史可用时间。
- `pit_eligibility=ARCHIVE_REPLAY_ONLY`，不得用于通过 `PIT_AND_SPLIT_VALID`。

这会让归档适合数据探索、回放和模型原型，但不适合证明某个历史时点的在线可用性。后续版本必须运行实时捕获器，保存实际接收时间和修订链，才能产生 `DECISION_ELIGIBLE` 数据。

## 8. 解析与验证

### 8.1 原始文件安全

- 仅 HTTPS，主机严格等于 `data.binance.vision`；
- 禁止重定向到其他主机；
- ZIP 最大 64 MiB，解压后最大 256 MiB；
- ZIP 只能包含一个预期 CSV member；
- 拒绝目录、绝对路径、`..`、加密 member、符号链接和异常压缩比；
- CHECKSUM 最大 4 KiB，只接受 `<64 hex>  <expected filename>`；
- 必须先校验官方 SHA-256，再解压和解析。

### 8.2 CSV

- UTF-8、RFC 4180 兼容读取；
- 允许官方文件有或无已知 header，但不允许未知 header；
- 每行列数必须完全匹配；
- 空值、NaN、Infinity、负价格/数量、非法布尔值、逆序 trade id 均拒绝；
- Kline 必须满足 `low <= open/close <= high`、`open_time < close_time`；
- 时间单位由 request 市场和 period 明确决定，不做数量级猜测：
  - Spot、period >= 2025-01-01：微秒；
  - Spot、period < 2025-01-01：毫秒；
  - USDⓈ-M：毫秒。

### 8.3 质量报告

至少包含：

- row count、first/last event time；
- duplicate business-key count；
- source-order regression count；
- Kline missing-interval count；
- malformed/rejected row count；
- checksum pass；
- expected period coverage；
- warnings 和 blocking findings；
- report hash。

任何 malformed row、重复业务键、时间倒退、校验失败都会阻断快照。Kline gap 显式记录并阻断正式数据资格；研究快照仍可由策略明确选择是否接受，但不能升级 Release Gate。

Funding Rate 不假设固定 8 小时。每行
`funding_interval_hours` 必须是 `1..24` 的严格正整数；连续性由当前行事件
时间加当前行 source interval 推导下一事件，因此允许月内 schedule
change。月首和月尾采用保守覆盖检查。Funding gap 进入
`missing_interval_count` 与 blocking findings；默认 strict builder 拒绝。
单独的 research-degraded builder 只允许 coverage/gap 类降级，输出
`quality_eligibility=RESEARCH_ONLY_DEGRADED`，且验证结果永远包含明确降级
reason，不能成为 formal/PIT/pass 数据。

## 9. 获取行为

命令行入口只接受结构化参数，不接受 URL：

```text
python -m crypto_quant.market_data fetch \
  --market spot \
  --family klines \
  --symbol ETHUSDT \
  --interval 4h \
  --period-kind daily \
  --period 2026-07-25 \
  --output <directory>
```

默认不覆盖已有文件。若目标已存在：

- 哈希和期望一致：幂等成功；
- 不一致：拒绝并要求新目录，保留两个版本的证据；
- 不自动删除、不静默替换。

幂等成功的 commit point 必须再次打开 final name，验证它仍指向初次读取的
同一 inode 且 bytes 完全一致；仅验证父目录仍 attached 不足以阻止并发
rename/replacement。

CLI 成功摘要必须公开 external snapshot-attestation hash，供调用方在
snapshot Artifact 之外持久化为信任锚。

网络错误、429、5xx、超时或内容超限均失败，不重试订单类请求（本模块不存在订单类请求）；公开 GET 最多按固定策略重试，测试中可禁用。

## 10. 与现有系统的集成

- 不直接写 `EconomicLedgerSnapshot`。市场行情不是成交、Funding 现金流或账户费用。
- `FundingRate` 是定价/成本输入；只有未来由持仓和结算规则计算出的 Funding cashflow 才进入经济账本。
- `HistoricalMarketDataSnapshot` 可在后续版本驱动同一个 Decision Kernel 和 Paper fill model。
- 快照必须进入 ReleaseEvidence 的 artifact 引用后，才可支持真实 OOS 报告。
- `ARCHIVE_REPLAY_ONLY` 不能令 `pit_and_split_check_pass=true`。

## 11. 测试与验收

单元测试必须覆盖：

1. URL/path 规范化和所有非法组合；
2. 官方 checksum 成功、失败、错误文件名和恶意文本；
3. ZIP traversal、多 member、zip bomb/size 限制；
4. 2024 Spot 毫秒与 2025+ Spot 微秒转换；
5. Kline、AggTrade、Mark Price Kline、Funding Rate 正常及异常行；
6. Decimal 精度、UTC、排序、重复、gap；
7. receipt/snapshot 哈希确定性与篡改检测；
8. 归档快照固定为 `ARCHIVE_REPLAY_ONLY`；
9. transport 只允许 GET、无认证材料；
10. CLI 在已有冲突文件上 fail-closed。

集成验收：

- 使用测试 fixture 完成 fetch → checksum → unzip → parse → snapshot；
- 对一个真实 ETHUSDT 官方小型归档执行 smoke test，并只提交 receipt/quality 摘要，不提交大体量原始市场数据；
- 全量原有测试继续通过；
- 无 API Key、签名、POST、订单或账户端点代码；
- README、状态、版本、权威计划同步更新；
- 合并后 tag `v0.16.0`。

## 12. 赚钱导向的结论

本版本不制造 Alpha，而是降低最危险的假利润来源：错时间单位、回看偏差、文件被替换、缺口被忽略、手续费被假设成事实。它对赚钱的贡献是让后续 AI 与基线比较建立在同一份真实、可复现、成本边界明确的数据上。

AI 模块在 v0.16 不获得更多权限。只有当真实数据生成的 OOS 增量证据继续满足统计、经济和风险下界门槛时，AI 才可能胜过 `NO_AI_BASE`；否则保持基线或不交易。
