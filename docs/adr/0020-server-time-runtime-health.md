# ADR-0020：三样本交易所时钟纠偏与 Paper 运行健康门

状态：Accepted

日期：2026-07-27

## 背景

v0.19 能保证一个 Paper 槽位只形成一套可恢复证据，但仍直接依赖本机 wall
clock。真实审计发现本机相对 Binance server-time 落后约 2 秒以上；简单地
忽略偏移会污染调度和未来签名请求，简单地用 1 秒阈值停机又会丢掉可安全
校正的周期。长期调度还缺少可回放心跳和机器告警。

## 决策

v0.20 在 v0.19 scheduler 前固定三个无凭据
`GET https://data-api.binance.vision/api/v3/time`：

- 每个响应形成保守 offset interval；
- 三个 interval 必须相交，交集宽度不超过 1000ms；
- 每个 RTT 不超过 3000ms；
- 交集的最大绝对偏移不超过 5000ms；
- 整个交集在 ±1000ms 内为 `HEALTHY_ALIGNED`；
- 其余稳定可界定偏移为 `HEALTHY_CORRECTED`；
- 无法满足约束时为 `BLOCKED`，禁止四个行情 GET 和 Paper 周期。

健康时用区间中点作为整数 correction，并以 monotonic clock 推进本次运行
时钟。wall clock 后续跳变不能让运行时钟倒退。

独立 SQLite WAL/FULL synchronous `runtime_events` 保存 append-only
`HEARTBEAT_RECORDED`。每个事件绑定完整 probe、scheduler 结果、分别统计的
时间/行情网络计数、heartbeat gap、active/raised/cleared alerts。UPDATE 和
DELETE 被 trigger 拒绝，每次追加和生成 snapshot 都重放完整链。

告警只具备 `LOCAL_ARTIFACT_ONLY` 资格。没有外部投递服务时，Artifact 不得
声称消息已送达。

## 结果

优点：

- 错误或不稳定时间不能启动新的策略周期；
- 可校正的稳定偏移不会无谓停机；
- 同槽位重复运行仍保持 v0.19 的零行情请求幂等性；
- 时间、调度、连续性和告警结论可以离线重放；
- 不需要账户、密钥或签名 endpoint。

代价与限制：

- 每次健康检查增加三个 public request；
- server-time 是应用级校正，不替代操作系统 NTP；
- 外部 scheduler 和外部告警投递仍未配置；
- 一个真实槽位和两次心跳不构成 90 天 Paper；
- 运行健康不增加 alpha，也不证明盈利。

## 资格

- `runtime_health_eligibility=OPERATIONAL_SMOKE_ONLY`
- `scheduler_eligibility=SCHEDULER_OPERATIONAL_SMOKE_ONLY`
- `paper_eligibility=LONGITUDINAL_COLLECTION_IN_PROGRESS`
- `profitability_eligibility=INSUFFICIENT_DURATION_COST_AND_AI`

本 ADR 不授权账户、Broker、订单、AI 自动决策、Canary、Live 或盈利声明。
