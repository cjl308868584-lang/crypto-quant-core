# ADR-0017：同时公开行情捕获与保守时钟语义

状态：Accepted

日期：2026-07-27

## 背景

v0.16 的官方归档能证明事后收到的字节和解析结果，却不能证明系统在历史
决策时刻已看到这些数据。若直接用归档回测或只保存最终 Kline，容易产生
look-ahead、修订选择和成交时钟偏差。

## 决策

v0.17 使用 Binance 官方 market-data-only REST，只允许 ETHUSDT/BTCUSDT
的固定 Kline、AggTrade 和 BBO 请求。每个响应保存请求开始、客户端接收、
摄取/记录时刻、原始 UTF-8 JSON、body hash 和响应收据；session 从原始
body 重跑 parser 后才能验证。

Kline 以 open time 作为事件时刻、另存 close time，并保留未收盘 revision
chain。AggTrade 用源 trade time/aggregate ID 检测可观测缺口。REST BBO
没有源事件时间和序列号，只能使用客户端接收时刻代理并永久附带
`BBO_SEQUENCE_UNOBSERVABLE_REST_SNAPSHOT`。

真实烟测发现部分源 trade time 比捕获主机接收时钟领先约一秒。两套时钟
不能被视为同一时钟。receipt 保留未经改写的客户端接收时刻；observation
采用：

`available_at = max(source_event_time, client_receive_time)`

若应用该 floor，记录 `SOURCE_EVENT_TIME_CLOCK_FLOOR`、次数和最大领先
毫秒。这个规则宁可让数据更晚可用，也不允许事件尚未发生却已被系统使用。
它不是完整时钟同步，长期捕获服务仍需 NTP/server-time 偏移监测。

完整 snapshot 由外部 attestation 锚定 response roots、observation roots、
session identity/time 和 snapshot hash。验证器必须从保存的原始 response
重建观察、修订、缺口和质量报告。

## 结果

优点：

- 同时数据的实际客户端接收证据被保留；
- 未收盘 Kline 修订和轮询漏掉的 AggTrade ID 可见；
- BBO 和时钟局限无法被静默升级；
- capture 可作为后续离线 Paper 的真实输入。

代价：

- REST 轮询不能证明捕获了每次 BBO 更新；
- 原始 response 使本地完整 Artifact 大于 compact evidence；
- 短期 session 仍不能通过 Paper/PIT Release Gate；
- 后续需要长期调度、时钟监测、永续上下文和账户成本/成交事实。

## 资格结论

所有 v0.17 snapshot 固定为：

- `pit_eligibility=CONTEMPORANEOUS_RESEARCH_ONLY`
- `paper_eligibility=CAPTURE_REPLAY_ONLY`

本 ADR 不授权 API Key、账户、Broker、订单、自动交易或盈利声明。
