# ADR-0031：Challenger 公共实时只读 Runner

日期：2026-07-28

状态：已接受

## 背景

v0.30 能确定性计算并追加 challenger decision，但调用方仍需自行提供 21 根
Kline、槽位和 recorded time。如果直接使用普通脚本传参，可能错误选择历史
时间、漏槽后回填，或只保存解析结果而丢失原始来源。

## 决策

1. 每次运行先执行已冻结的三样本 Binance server-time probe，并从同一
   monotonic anchor 生成当前时间和 recorded time。
2. 空 state 的下一槽固定为注册首槽；非空 state 只能是最后 decision +4h。
3. 早于下一槽返回 `NOT_DUE`；晚于下一槽返回 `MISSED_SLOT`；两者均不发送
   Kline 请求。
4. 正好到期时只发送一个固定公开 GET，endTime 必须由 slot-1ms 派生，
   symbol/interval/limit 固定为 ETHUSDT/4h/21。
5. 关闭环境代理，不自动重试，不接受 redirect，严格限制 body 大小和 JSON。
6. 首槽保存 21 根 Kline 的首次 availability；下一槽必须逐条匹配旧的 20 根
   raw row hash，并沿用其 availability。闭合行修订不可覆盖。
7. 保存完整 server-time probe、Kline HTTP receipt/raw body、标准化 Kline 和
   candidate decision 的 source bundle；bundle 校验并持久化后才追加 decision。
8. CLI 只接受 state path 和 output root，不允许 URL、host、symbol、slot、
   clock、credential 或订单覆盖。
9. Runner 永久无 Broker、余额、持仓和下单能力。

## 理由

赚钱研究的关键不是多跑一次回测，而是在结果未知时留下完整输入和决策。固定
请求与槽位派生阻止调用者选择有利时间；先保存 source bundle 再追加 decision，
确保任何 state decision 都有已落盘来源。跨槽保留首次 availability 可证明旧
Kline 没有用后续响应时间重新包装。

## 限制

Binance server-time receipt 能纠正本机时钟并保存来源，但本地文件仍可在事后
整体重建，因此不等于独立第三方 publication。没有外部 publication attestation
时，decision 只能是 `UNANCHORED_LOCAL_PREQUENTIAL_ONLY`。

## 后果

v0.31 已具备安全实时采集入口，但版本冻结时首槽尚未发生，因此真实请求、
source bundle 和 decision 均为 0。下一步是生成无凭据操作系统调度合同并在首槽
前完成审查；安装和启动必须产生独立 receipt，不能仅凭配置文件宣称已运行。
