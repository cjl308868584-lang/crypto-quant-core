# v0.20 Paper 运行时钟、心跳与告警设计

日期：2026-07-27

状态：Frozen for implementation

## 1. 目标

在 v0.19 的可恢复 4h Paper scheduler 前增加一个失败关闭的运行健康门。每次
尝试新周期前先取得 Binance public server-time 证据，判断本机时钟是可信、
可校正还是必须阻断；随后把探针、调度结果、心跳连续性和本地告警写入
append-only 状态与可离线重放 Artifact。

v0.20 的目标是避免“错误时间上的正确模型”。它不增加交易信号，不接账户、
密钥、Broker、订单或外部消息服务，也不把运行健康误写成盈利证据。

## 2. 官方接口与安全边界

固定使用：

`GET https://data-api.binance.vision/api/v3/time`

Binance 官方 Spot REST 文档将 `GET /api/v3/time` 定义为无参数、权重 1 的
server-time endpoint；public market-data host 是
`https://data-api.binance.vision`，`NONE` endpoint 不需要签名。实现：

- 不接受 CLI URL、header、代理、API key、secret 或时间覆盖；
- 每次 probe 固定三个顺序 GET，不自动重试；
- 禁用环境代理，只允许同 HTTPS host redirect；
- 限制状态码、最终 URL、body 大小和严格 JSON；
- 429/418/5xx/网络错误全部失败关闭，不在进程内重试；
- 保存每个请求的本机 wall-clock 起止、monotonic RTT、响应 body/hash 和
  选定响应头。

## 3. 三样本区间时钟算法

Binance `serverTime` 为整数毫秒。对每个样本：

```text
start_ms  = floor(local_wall_start_ns / 1_000_000)
end_ms    = floor(local_wall_receive_ns / 1_000_000)
rtt_ms    = ceil((monotonic_end_ns - monotonic_start_ns) / 1_000_000)
lower_ms  = serverTime - end_ms   - 1
upper_ms  = serverTime - start_ms + 1
```

`±1ms` 是 server timestamp 和本机毫秒量化的保守边界。真实偏移应在每个
样本的 `[lower_ms, upper_ms]` 中。三个样本的交集是：

```text
intersection_lower = max(lower_ms)
intersection_upper = min(upper_ms)
```

冻结政策：

- 样本数必须正好为 3；
- 每个 RTT 必须不超过 3000ms；
- 三个区间必须有交集；
- 交集宽度不得超过 1000ms；
- 交集两端的最大绝对值不得超过 5000ms。

状态分类：

- `HEALTHY_ALIGNED`：整个交集位于 `[-1000ms, +1000ms]`；
- `HEALTHY_CORRECTED`：不 aligned，但满足全部稳定性和最大偏移约束；
- `BLOCKED`：任何约束失败。

校正值为交集中点的整数下界。健康时，以“最后一次本机 wall time +
校正值”为 wall anchor，以 monotonic clock 推进，生成本次 scheduler 和
四个 market-data receipt 使用的 `TrustedRuntimeClock`。这样不会因运行中
wall-clock 跳变倒退，也不会把一次响应的网络延迟误当作精确偏移。

真实设计审计的三次样本得到：

- RTT：731ms、1758ms、1720ms；
- 偏移交集：`[2129ms, 2861ms]`；
- 结论：当前本机未 aligned，但可稳定校正，不能简单因偏移超过 1 秒停机。

这些数值只用于设计校准，不作为测试 fixture 或未来运行结论。

## 4. 健康门与调度语义

`paper-runtime-run` 是新的 one-shot 入口：

1. 生成三样本 server-time probe；
2. 若 `BLOCKED`，禁止调用 v0.19 scheduler 和四个行情 GET；
3. 若健康，构造 `TrustedRuntimeClock` 后调用原 v0.19 scheduler；
4. 记录运行结果和告警转换；
5. 发布不可变 runtime snapshot。

网络计数必须分开报告：

- `server_time_request_count`；
- `paper_market_request_count`；
- `total_network_request_count`。

健康且首次执行一个槽位时为 `3 + 4 = 7`；同槽位重复健康检查仍会执行三个
server-time GET，但 v0.19 scheduler 保持零 market GET。若 probe 被阻断，
只允许 server-time 请求，不允许 market GET。

v0.19 scheduler、prepared bytes、租约、missed/expired 和“不回填”状态机
保持原样。runtime wrapper 不篡改已冻结的 v0.19 事件语义。

## 5. Append-only runtime 状态

独立 SQLite WAL/FULL synchronous 状态保存 `runtime_events`：

- 自增 sequence；
- `HEARTBEAT_RECORDED`；
- event time 使用 trusted time；若 probe 阻断则使用本机 time 并显式标记
  `LOCAL_UNTRUSTED`；
- canonical payload/hash；
- previous event hash；
- event hash。

UPDATE/DELETE 由 trigger 拒绝。每次追加前后重放完整哈希链。payload 保存：

- probe policy/hash、三样本完整 receipt 与 probe self-hash；
- health status、offset interval、correction；
- scheduler outcome/error 和 v0.19 snapshot/run hashes；
- 网络计数；
- heartbeat gap；
- active/raised/cleared alert codes。

第一次心跳不伪造历史。后续 trusted heartbeat 间隔超过
`15300s = 4h + 15min` 时产生 `PAPER_HEARTBEAT_GAP`。若前次或本次时间不
可信，不能计算可信 gap，并产生 `PAPER_HEARTBEAT_CONTINUITY_UNKNOWN`。

## 6. 可机器消费的本地告警

冻结告警：

- `PAPER_CLOCK_PROBE_BLOCKED`：S2，阻断新周期；
- `PAPER_HEARTBEAT_GAP`：S2，需要人工检查外部调度；
- `PAPER_HEARTBEAT_CONTINUITY_UNKNOWN`：S2，时间轴不可证明；
- `PAPER_SCHEDULER_FAILURE`：S2，周期失败；
- `PAPER_SCHEDULER_BUSY`：S3，另一个活跃 lease 正在运行。

snapshot 保存当前 active alerts 以及本次 raised/cleared transitions。告警
投递资格固定为 `LOCAL_ARTIFACT_ONLY`。没有配置 Slack、邮件或 PagerDuty
时，绝不声称告警已送达；同时保留
`EXTERNAL_ALERT_DELIVERY_NOT_CONFIGURED` 和
`OPERATING_SYSTEM_SCHEDULER_NOT_CONFIGURED`。

## 7. Runtime snapshot 与验证

`PaperRuntimeSnapshot` 包含：

- 冻结 policy/hash；
- 完整 append-only runtime event chain；
- events root、chain end；
- heartbeat 总数、健康/校正/阻断/失败计数；
- 首末可信心跳、最大可信 gap；
- 当前 active alerts；
- 最新 v0.19 cycle/schedule references；
- state integrity、self-hash 和外部 Artifact attestation。

validator 必须重新：

- 验证每个 probe receipt、区间和 health 分类；
- 重算 trusted correction；
- 重算事件 payload hash/链；
- 从事件投影 summary、alerts 和最新 references；
- 验证 snapshot self-hash 与外部 attestation。

## 8. 资格与非目标

v0.20 固定：

- `runtime_health_eligibility=OPERATIONAL_SMOKE_ONLY`；
- `scheduler_eligibility=SCHEDULER_OPERATIONAL_SMOKE_ONLY`；
- `paper_eligibility=LONGITUDINAL_COLLECTION_IN_PROGRESS`；
- `profitability_eligibility=INSUFFICIENT_DURATION_COST_AND_AI`。

不实现：

- 操作系统 cron/launchd 安装；
- 外部告警投递；
- NTP daemon 配置；
- AI 交易模型、LLM 下单或参数在线自修改；
- 永续合约上下文、账户真实费率；
- Canary、Live 或盈利声明。

运行健康只是赚钱系统的必要条件，不是充分条件。AI 仍应保持 shadow-only，
以后只能在可靠时间轴、长期样本、真实成本和 walk-forward/OOS 证据之后进入
受控候选。
