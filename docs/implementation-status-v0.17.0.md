# 实施追踪 v0.17.0

日期：2026-07-27

状态：已完成并验证

## 本版本完成

- 新增只允许 `ETHUSDT`/`BTCUSDT` 的 Binance market-data-only capture plan；
- 每轮固定获取 `1m`/`4h` Kline、最近 100 个 AggTrade 和单符号 BBO；
- 生产 transport 仅执行无凭据 HTTPS GET，禁环境代理、任意 URL/query/header；
- 保存请求开始、客户端响应接收、摄取/记录时刻、原始 UTF-8 response、
  body hash、HTTP metadata 和响应收据；
- 从原始 response 离线重跑 parser，不信任调用方提供的规范化观察；
- Kline 以 source open time 记录事件，另存 close time、closed 状态、重复
  和 revision chain；closed bar 内容变化失败关闭；
- AggTrade 绑定 aggregate/first/last trade ID、源时间、maker side，并检测
  重复、冲突和轮询样本内可观测 ID 缺口；
- REST BBO 明确使用 `CLIENT_RECEIVE_TIME_PROXY`，强制附带
  `BBO_SEQUENCE_UNOBSERVABLE_REST_SNAPSHOT`；
- 源时钟领先客户端时，保留原始客户端 receive time，并使用
  `SOURCE_EVENT_TIME_CLOCK_FLOOR` 保守满足 PIT 时间不变量；
- 新增严格治理/包内 Schema、不可变 CLI、完整 session self-hash 和外部
  snapshot attestation；
- 单轮可信 snapshot 可重新发行 opaque batch，用于离线合并重放；
- 固定所有 v0.17 capture 为 `CONTEMPORANEOUS_RESEARCH_ONLY` /
  `CAPTURE_REPLAY_ONLY`。

## 真实官方两轮 smoke

来源：`https://data-api.binance.vision`，Spot `ETHUSDT`，无凭据 GET。

两轮各请求四个固定端点，共 8 个 HTTP 200 response。每轮完整 snapshot
均用独立保存的 external attestation hash 验证，reasons 为空；再从保存的
原始 response 离线重发两个 opaque batch，合并生成两轮 session。

- Session：`ethusdt-public-smoke-two-round`
- 时间：`2026-07-27T12:30:26.048Z` 至
  `2026-07-27T12:31:06.984Z`
- Response：8
- 原始观察：210
- Canonical 观察：209
- Kline revision：2
- Kline duplicate：1
- closed Kline mutation：0
- AggTrade gap：301
- AggTrade conflict：0
- BBO duplicate：0
- source-clock floor：65
- 最大 source-clock ahead：1185ms
- Response receipts root：
  `4437d9d38e87e60db0e7cf9f4aa0084be665e996c88bbc53ec926efbbf701262`
- Observations root：
  `7938557339b26b2bca5f068539d62593dc7c2632093953a1a5af76b02074aa6c`
- Quality report：
  `088b4757ee4c113de7642a5eb6cc97aec3d3a8ceb12e97b7899d18ad0c8833e6`
- Snapshot：
  `db5aa112e526d045a3841f417c6b29e7f48ed6ebef3054ba91d7608a7ec58364`
- External attestation：
  `df7d4f2a5c71cda4841eabd86680b1437bd396d3d3ea2bdf4d95a4bc472eb432`
- Trusted validation reasons：空
- PIT/Paper：`CONTEMPORANEOUS_RESEARCH_ONLY` /
  `CAPTURE_REPLAY_ONLY`

真实 smoke 发现的 301 个 AggTrade ID 缺口不是测试失败，而是 REST 轮询
没有覆盖两轮之间全部成交的真实证据；系统没有把它静默补齐。65 个
source-clock floor 也保留为质量警告，没有把本机与交易所时钟假设为一致。

仓库只提交 compact hash/count evidence；完整 response 和价格/数量没有
提交，验证后临时完整 snapshots 已删除。

## 最终验证证据

- 新增 capture/CLI tests：16 项，0 失败
- Market-data/capture focused tests：91 项，0 失败
- 全量 tests：307 项，0 失败
- Golden Vector：41 项
- Golden report：
  `e3e7dc45865d860489514a574c64ca14a8dd6f089a0b74129414231741882fc3`
- Catalog：58
- 可执行 Estimator：26
- 明确 unavailable：32
- Evaluator build input tree：
  `7c16d31019c82297cf3a5be20f6ba37ff54da2541aa90b79fc7df4834046f7bb`
- Evaluator build：
  `acd51ed4e92768fbaa887969a01a0434c7c5e47763f2d2327cafc798f8680baf`
- release/governance/schema/build validators：执行成功；
  Release Policy 仍按设计返回 `DESIGN_BASELINE` /
  `PRODUCTION_ACTIVATION_DISABLED`

## 赚钱与 AI 含义

v0.17 没有创造或证明 alpha。它让后续策略/AI 必须面对真实接收时钟、
未收盘修订、轮询漏样和 BBO 局限，从而减少事后数据形成的假利润。

目前仍没有：

- 90 天以上真实 Paper 决策样本；
- 双臂 baseline/AI 同时决策；
- 保守 fill、真实账户手续费、实际滑点和 Funding cashflow；
- 完整 EconomicLedger、月度统计、OOS ReleaseEvidence；
- 永续 Mark/Index/Premium/OI 同时上下文；
- Broker、账户、密钥、订单或资金能力。

因此不能声称策略赚钱、AI 优于平台 AI、AI 优于简单基线或任何 Bundle
获得资金资格。

## 下一优先级

1. 用 capture snapshot 生成不可变的离线 Paper input/decision clock；
2. 同一候选时刻运行 `BASELINE_ONLY` 与 `AI_ENHANCED` 双臂决策；
3. 用 BBO、AggTrade gap 和保守 latency/cost model 生成 simulated fills；
4. 形成完整 EconomicLedger、配对月度序列和统计 Artifact；
5. 长期调度 capture，并增加 NTP/server-time 偏移、永续上下文和账户成本
   事实；
6. 只有完整 Paper/Shadow 门槛通过后才考虑资金接入。
