# v0.17 同时公开行情捕获与可重放证据设计

状态：`APPROVED`

批准依据：项目所有者已明确全权委托，并要求无需逐项提问；本设计按既有
资金安全、证据门、PIT 语义和版本交付规则冻结。

日期：2026-07-27

## 1. 目的

v0.17 在 v0.16 事后归档之外，建立一条运行时实际观察公开市场数据的
只读链路。它解决的是：

1. 保存请求开始、响应接收、摄取和落盘时刻，而不是把历史事件时刻冒充
   系统当时可用时刻；
2. 保存原始响应哈希、逐条观察、Kline 修订和 AggTrade ID 连续性；
3. 对 REST BBO 无源事件时刻、无序列号的局限做机器可判定降级；
4. 生成内容寻址、可离线重放、外部锚定的 capture session；
5. 为后续离线 Paper 的决策、fill 和账本 Artifact 提供真实输入。

v0.17 不包含：

- API Key、签名请求、账户、订单、Broker 或资金能力；
- WebSocket 增量 order book、用户数据流或账户成交；
- 90 天 Paper 运行、策略收益、AI 增量价值或 Release PASS；
- OI、永续 Mark/Index/Premium、Funding cashflow；
- 将一次或少量 capture smoke 宣称为 decision-eligible 数据。

## 2. 已核实的官方源契约

v0.17 使用 Binance 官方 market-data-only REST：

- Base URL 固定为 `https://data-api.binance.vision`；
- 公开市场数据无需 API Key；
- `GET /api/v3/klines` 返回 Kline open/close time、OHLC、成交量和成交数；
- `GET /api/v3/aggTrades` 返回 aggregate trade ID、首尾 trade ID、价格、
  数量、时间和 maker side；
- `GET /api/v3/ticker/bookTicker` 返回当前 bid/ask 价格与数量，但响应不含
  源事件时间和序列号；
- Kline 与 AggTrade 数据源为数据库，bookTicker 数据源为内存；官方说明
  不同数据源可能存在异步延迟；
- 端点有 request weight、429 和 `Retry-After` 约束。

权威链接：

- <https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md>
- <https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md>
- <https://developers.binance.com/en/docs/products/spot/rest-api>

## 3. 方案选择

### 方案 A：直接接 WebSocket 并维护完整 order book

最接近实时交易，但首版需要重连、快照同步、update-ID 桥接、心跳和长时间
进程恢复。它会同时引入过多状态和依赖，难以在一个版本内完成严格证据
边界。保留为后续升级。

### 方案 B：轮询公开 REST，只保存规范化行情

实现简单，但丢失原始响应、传输时刻、请求收据和响应级完整性，无法证明
观察从何而来。拒绝。

### 方案 C：受限 REST capture + 响应收据 + 观察链 + session attestation

固定公共域名、端点、符号和查询；每个响应保存传输时刻与 body hash；
解析为不可变观察；在 session 层检测修订、重复和可观测缺口；再用外部
attestation 锚定完整 session。采用。

## 4. 支持矩阵

符号仅为 `ETHUSDT`、`BTCUSDT`。

| 数据族 | 端点 | 固定参数 | 可观测语义 |
|---|---|---|---|
| `SPOT_KLINE` | `/api/v3/klines` | `interval=1m/4h`、`limit=2` | 源 open/close time；同一 open time 可形成修订 |
| `SPOT_AGG_TRADE` | `/api/v3/aggTrades` | `limit=100` | 源 aggregate trade ID/time；可检测捕获样本内 ID 缺口 |
| `SPOT_BBO` | `/api/v3/ticker/bookTicker` | 单一 `symbol` | 无源时间/序列；仅是接收时刻的 REST snapshot |

调用方不能传 base URL、任意 path、任意 query、headers 或 credentials。
计划对象只允许选择上述枚举和参数范围。

## 5. 架构

```text
ContemporaneousCapturePlan
  → exact allowlisted REST requests
  → PublicMarketDataTransport (HTTPS GET, no proxy/credentials)
  → PublicCaptureResponseReceipt
  → strict family parser
  → ContemporaneousMarketObservation[]
  → CaptureSessionBuilder
       ├─ Kline revision chain
       ├─ AggTrade gap/duplicate analysis
       └─ BBO sequence-unobservable finding
  → ContemporaneousCaptureSnapshot
  → external session attestation
  → immutable compact artifact / later offline replay
```

核心库允许注入 transport 和 clock。生产 transport 只执行固定 HTTPS GET；
测试使用内存 transport。任何响应验证或解析失败都会终止本轮 session，
不得以部分成功伪装完整 capture。

## 6. 核心契约

### 6.1 `ContemporaneousCapturePlan`

字段：

- `schema_version`
- `provider=BINANCE_MARKET_DATA_ONLY`
- `symbol`
- `families`
- `kline_intervals`
- 固定 limit

计划必须包含三个 family。URL 和规范查询由库生成，查询参数按键排序。
v0.17 不提供任意单端点 CLI。

### 6.2 `PublicCaptureResponseReceipt`

每个 HTTP 响应保存：

- `request_id`、family、symbol、interval；
- 规范 URL；
- `request_started_at`、`response_received_at`；
- `ingested_at`、`recorded_at`；
- status、final URL；
- allowlisted 响应 metadata：`Date`、`ETag`、`Last-Modified`、
  `Retry-After`（缺失则 null）；
- bounded 原始 UTF-8 JSON response body、body size 和 SHA-256；
- `receipt_hash`。

约束：

`request_started_at <= response_received_at`

receipt 不保存授权 header，因为该接口不允许授权输入。保存原始 body 是为了
让离线验证器能从响应字节重跑 parser，而不是信任已规范化的观察；body size
有硬上限。
self-hash 只能证明内部完整性，不是信任锚。

### 6.3 `ContemporaneousMarketObservation`

公共字段：

- `observation_id`
- `fact_type`、symbol、interval；
- `business_key`
- `event_time`
- `event_time_basis`
- `available_at`
- `ingested_at`
- `recorded_at`
- response receipt hash 和 source index；
- 严格 source payload、source payload hash；
- 规范化 payload、payload hash；
- revision fields；
- `observation_hash`。

所有数值为 Decimal 字符串，不允许 float。所有时间为 UTC。

时间不变量：

`event_time <= available_at <= ingested_at <= recorded_at`

family 语义：

- Kline：`event_time=open_time`，`event_time_basis=SOURCE_OPEN_TIME`，并另存
  `close_time`。未收盘 Kline 可被捕获，但 `is_closed=false`，不得作为完整
  决策 bar；只有在 `available_at > close_time` 且后续重放仍一致时，完整
  bar 才可按 `close_time` 进入后续决策时钟；
- AggTrade：`event_time=trade_time`，
  `event_time_basis=SOURCE_TRADE_TIME`；
- BBO：源没有事件时间，因此
  `event_time=available_at=response_received_at`，
  `event_time_basis=CLIENT_RECEIVE_TIME_PROXY`。禁止将其升级为交易所事件
  时间。

### 6.4 修订、重复与缺口

Kline business key 为 `(symbol, interval, open_time)`。同一 key：

- 首次观察 `revision_no=0`；
- payload 改变时追加 revision，绑定
  `previous_observation_hash`；
- payload 完全相同为 duplicate observation，仍保留 receipt 但不新增
  规范化 revision；
- 已被观察为 closed 的 Kline 后续内容变化为 blocking finding。

AggTrade business key 为 aggregate trade ID。相同 ID 且 payload 相同为
重复；相同 ID 内容变化为 blocking finding。按 ID 排序后只对当前 capture
实际覆盖范围检测缺口，不能声称两个轮询之间没有错过更早已滚出 `limit`
窗口的数据。

BBO 以每个响应作为独立 snapshot；相同内容可计为重复。由于无序列号，
每个包含 BBO 的 session 必须带
`BBO_SEQUENCE_UNOBSERVABLE_REST_SNAPSHOT`，并保持 research-only。

### 6.5 `ContemporaneousCaptureSnapshot`

字段：

- schema、session ID、plan；
- session start/end/recorded time；
- 有序 response receipts；
- 有序 canonical observations；
- `quality_report`；
- `pit_eligibility=CONTEMPORANEOUS_RESEARCH_ONLY`；
- `paper_eligibility=CAPTURE_REPLAY_ONLY`；
- roots 和 `snapshot_hash`。

排序必须稳定。相同输入、时钟和 parser 版本必须得到相同 bytes/hash。
验证器用保存的 source payload 重新解析并重建 revision/gap/quality 结果。

完整可信验证要求 snapshot 外的 attestation。envelope 至少绑定：

- attestation schema/type；
- snapshot schema/parser；
- session ID、recorded time；
- response-receipts root、observations root；
- snapshot hash。

调用方必须显式传入从独立发布边界保存的 attestation hash；不能从待验证
snapshot 临时计算后自证。

## 7. 质量与资格

质量报告至少包含：

- response、observation、canonical observation 数量；
- family coverage；
- first/last source event 和 receive time；
- Kline revision/duplicate/closed-mutation count；
- AggTrade duplicate/gap/conflict count；
- BBO duplicate count；
- response latency；
- warnings、blocking findings 和 report hash。

阻断条件包括：

- 非 200、错误 host/final URL、超限 body、非法 JSON；
- family/symbol/interval 与请求不一致；
- Decimal、时间、OHLC、ID 或 bid/ask 关系非法；
- receipt/source/payload/revision/hash 不一致；
- closed Kline 被修改；
- AggTrade 同 ID 冲突；
- 时间不变量不成立；
- 缺少任一必需 family。

即使所有 blocking findings 为零，v0.17 也固定为
`CONTEMPORANEOUS_RESEARCH_ONLY`，原因至少包括：

- `CAPTURE_DURATION_BELOW_PAPER_MINIMUM`
- `BBO_SEQUENCE_UNOBSERVABLE_REST_SNAPSHOT`
- `PERPETUAL_CONTEXT_NOT_CAPTURED`
- `ACCOUNT_COSTS_AND_FILLS_NOT_CAPTURED`

这份数据可支持离线 parser/replay 和后续 fill model 校准，但不能通过
`PIT_AND_SPLIT_VALID` 或 Paper/Release Gate。

## 8. 传输安全与运行纪律

- 仅允许 `https://data-api.binance.vision`；
- 生产 transport 禁用环境代理；
- 只允许 GET，不接受 caller headers；
- 同一固定 host 内重定向才可继续；
- timeout 有限，响应流边读边限长；
- 单轮请求为 4 个：`1m Kline`、`4h Kline`、AggTrade、BBO；
- 429/418 不进行激进重试；解析 `Retry-After` 后失败关闭，由外层调度决定
  下一轮；
- 5xx/网络瞬态错误最多固定一次短重试，测试不真实 sleep；
- 原子 no-overwrite 发布，路径不可经 symlink 逃逸，冲突不覆盖。

## 9. CLI 与真实 smoke

CLI 只接受：

- `--symbol ETHUSDT|BTCUSDT`
- `--output-root`
- 可选固定 session ID

它运行一轮完整 capture，生成不可变 JSON snapshot，并输出 compact summary。
不接受 URL、API key、header、账户或 order 参数。

v0.17 真实 smoke 使用 `ETHUSDT` 连续运行两轮只读 capture，证明：

- 官方公共端点可访问；
- 收据包含实际请求/接收时刻；
- 三个 family 严格解析；
- 1m/4h Kline 相同 key 可形成 duplicate 或 revision；
- AggTrade ID 连续性和 BBO 降级可重放；
- snapshot 与 external attestation 可独立验证。

仓库只提交 compact evidence，不提交大体量原始行情和不必要的价格明细。

## 10. 对赚钱目标的作用

本版本不创造 alpha。它消除三类常见假利润：

1. 用事后修订数据回测，却假设实时当时已可用；
2. 用没有接收时间的 BBO 模拟成交，低估延迟和漏样；
3. 只保存最终 Kline，丢失未收盘 bar 的修订过程。

真正赚钱所需的下一步是：让策略在这条真实 receive-time 数据链上产生
双臂决策，使用保守 fill/cost model 形成离线 Paper 账本，再经过足够长的
OOS/Paper/Shadow 样本验证 AI 是否对基线有可重复的净增量价值。
