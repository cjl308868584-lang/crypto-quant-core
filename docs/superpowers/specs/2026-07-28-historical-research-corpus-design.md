# v0.26 历史研究语料与滚动 OOS 切分设计

日期：2026-07-28
状态：冻结设计基线
发布目标：`0.26.0`

## 1. 目的

v0.25 已能按真实 4h 时钟运行一个可恢复、只读的完整 Paper 周期，但当前
仓库没有足以训练和比较 AI Candidate 的连续历史语料。直接训练模型会把
单日 smoke、事后归档和正式 PIT 证据混为一谈，无法回答模型是否真的比
简单基线更赚钱。

v0.26 只建立训练前的数据基础：

1. 冻结 42 个完整 UTC 月的公开历史研究语料计划；
2. 冻结 8 个季度滚动 OOS fold 及每折前置 18 个月窗口；
3. 以可恢复、逐项幂等方式获取并验证 Binance 官方月度归档；
4. 发布机器可验证的覆盖、缺口和来源证明；
5. 明确把全部结果限制为 `ARCHIVE_REPLAY_ONLY`，不得冒充正式 PIT、
   OOS、Paper 或盈利证据。

本版本不训练 Logistic/XGBoost，不生成可部署 ModelBundle，也不改变任何
生产、Paper 或真实资金指针。

## 2. 官方来源与请求范围

Binance 官方公开数据说明同时提供 daily 和 monthly 文件，并为每个 ZIP
提供 `.CHECKSUM`。本版本在现有 `HistoricalArchiveRequest` 上增加月度
Kline 和月度 Mark Price Kline，继续复用已有的 HTTPS、同主机重定向、
大小、ZIP、CSV、官方 SHA-256 和严格解析边界。

固定语料流：

| 流 | market | family | symbol | interval | 用途 |
|---|---|---|---|---|---|
| `ETH_SPOT_4H` | SPOT | KLINES | ETHUSDT | 4h | 基础 proposal/价格/量价特征 |
| `BTC_CONTEXT_4H` | SPOT | KLINES | BTCUSDT | 4h | 只作上下文，不产生 BTC 订单 |
| `ETH_MARK_4H` | USD_M | MARK_PRICE_KLINES | ETHUSDT | 4h | 永续价格与基差研究 |
| `ETH_FUNDING` | USD_M | FUNDING_RATE | ETHUSDT | null | 资金费上下文 |

每个完整月份恰好四个请求。42 个月共 168 个 archive request、正常首次
完整下载共 336 个物理 GET。不得用 REST 数据静默填补 archive 缺口。

不纳入 v0.26：

- AggTrade、BBO、Order Book、OI 和真实成交；
- 真实账户手续费、真实滑点和真实 Funding cashflow；
- 任何需要密钥、Broker 或下单权限的请求；
- 由 4h OHLC 乐观推导的正式执行标签。

## 3. 固定窗口和 fold

默认冻结窗口：

- `corpus_start = 2023-01-01T00:00:00.000Z`
- `corpus_end_exclusive = 2026-07-01T00:00:00.000Z`
- 共 42 个完整 UTC 月；
- OOS 起点 `2024-07-01T00:00:00.000Z`；
- OOS 终点 `2026-07-01T00:00:00.000Z`；
- 共 8 个连续、无重叠、无缺口的季度 fold。

每折：

- `training_window_start = oos_start - 18 calendar months`
- `training_window_end = oos_start`
- `calibration_window` 是训练窗最后一个完整月；
- `fit_window` 是训练窗前 17 个完整月；
- 24h 标签的 purge/embargo 均冻结为 24 小时；
- OOS fold 必须是完整 UTC 季度。

这些区间只是训练/评估计划。归档数据在历史决策时点不可证明已被本系统
收到，因此任何 fold 都只能标记 `RESEARCH_ARCHIVE_FOLD`，不能获得正式
`PIT_VALID_OOS`。

## 4. 计划 Artifact

`HistoricalResearchCorpusPlan v1` 必须包含：

- schema/version/self-hash；
- 固定窗口、42 个月和 8 个 fold；
- 四个流的完整请求列表；
- 每个请求的稳定 `corpus_item_id`；
- 请求总数、预期 GET 数和有序请求根哈希；
- `ARCHIVE_REPLAY_ONLY` / `RESEARCH_DEVELOPMENT_ONLY` 边界；
- 明确的禁止用途和 warnings。

计划以请求业务内容生成稳定 ID，不依赖创建时间、文件路径或列表插入
顺序。验证器必须重建月份、fold、请求和根哈希，不能只核对 self-hash。

## 5. 可恢复状态

`HistoricalResearchCorpusState` 使用 SQLite：

- `journal_mode=WAL`
- `synchronous=FULL`
- 绑定 plan hash 与 output root；
- append-only event log；
- 每次打开完整重放事件链、租约和成功 snapshot 语义；
- 成功 source bytes 以 canonical JSON 精确保存，恢复时不重新请求；
- 发布使用 owner-only 目录和 mode `0600` 文件；
- 同路径不同 bytes 一律拒绝覆盖。

事件：

1. `CLAIMED`
2. `SUCCEEDED`
3. `FAILED`

租约固定 15 分钟。活动租约不得被第二 worker 抢占；租约过期后可恢复。
失败项可在后续运行重试，但成功项不可改写。每次 `run` 最多处理显式
`max_items`，默认 1，最大 16，避免一次不可控长任务。

每个成功项必须保存：

- exact snapshot bytes 与 SHA-256；
- snapshot self-hash；
- request/receipt/quality hashes；
- 官方 archive/checksum SHA-256；
- row count、首尾 event time；
- fetch/retrieval time；
- 独立 attestation 的期望 envelope hash。

同一进程计算出的 attestation hash 只是待外部锚定的期望值，不得自证
可信。没有独立重下载或外部签名锚时，corpus 仍是
`UNANCHORED_ARCHIVE_RESEARCH`。

## 6. 覆盖 Snapshot

每次运行后发布 `HistoricalResearchCorpusSnapshot v1`：

- plan hash、state event root、记录时间；
- 168 项的状态与哈希；
- 每流/月覆盖矩阵；
- succeeded/failed/pending/claimed 数；
- archive/checksum 物理 GET 数；
- duplicate、gap、quality blocking findings；
- corpus completeness；
- attestation anchoring completeness；
- AI training readiness；
- formal PIT/OOS/profitability eligibility。

只有全部 168 项成功、每项 `FORMAL_COMPLETE`、业务月份连续且 snapshot
语义重放通过时，`research_training_readiness` 才可为
`READY_FOR_ARCHIVE_RESEARCH_FEATURE_BUILD`。这仍不改变：

- `formal_pit_eligibility = INELIGIBLE_ARCHIVE_REPLAY`
- `release_oos_eligibility = INELIGIBLE`
- `profitability_eligibility = INELIGIBLE`

## 7. CLI 边界

CLI 只允许：

- 创建冻结默认计划；
- 初始化/恢复 state；
- 指定 output root、worker ID 和 `max_items`；
- 使用生产公开 transport 运行；
- 只读验证现有计划/state/snapshot。

CLI 不允许：

- 自定义 URL、主机、HTTP 方法或 shell 命令；
- 传入密钥或代理；
- 跳过官方 checksum；
- 把 daily/REST 响应伪装成计划内 monthly item；
- 修改成功项；
- 声称模型训练或发布已完成。

## 8. 验收

至少覆盖：

1. 月度 Spot/Mark 请求 URL 与 Schema；
2. 月度 Kline 跨闰年、月末和微秒边界的完整覆盖；
3. 默认计划 42 月、8 fold、168 item、336 GET；
4. 计划 tamper、乱序、缺月、重复 item 和 hash 改写失败；
5. 首次成功、活动租约、过期恢复、失败重试；
6. 成功后恢复为零网络；
7. source bytes、receipt、quality、state event chain tamper 失败；
8. 发布权限与冲突拒绝；
9. 不完整 corpus 永不 training-ready；
10. 完整 fixture corpus 只获得 archive research readiness；
11. CLI 不接受 URL、凭据或任意命令；
12. 新 Schema 的 config/package 镜像一致；
13. 现有 market-data、Paper、编排和全部回归测试不退化。

## 9. 发布边界

v0.26 的正确成功结论是“模型研究所需的连续公开归档可以被可恢复、可
审计地取得”，不是“AI 已经可用”或“策略已赚钱”。

下一版本才允许在完整 corpus 上实现同源 PIT 特征、event-based 标签和
低维 Logistic 研究基准；若真实 corpus 尚未完成，则只能用 fixture
验证训练代码，不得发布任何 Candidate 结论。
