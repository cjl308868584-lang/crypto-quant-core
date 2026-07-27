# ADR-0021：当前永续上下文与 Funding 成本场景

状态：Accepted

日期：2026-07-27

## 背景

v0.20 已能可靠地形成 4h Paper 周期和时钟证据，但策略仍缺少 ETHUSDT
USDⓈ-M 永续的当前 Mark、Index、Premium、Open Interest 与 Funding
上下文。没有这些事实，SHORT 的基差、拥挤度和资金费方向只能被标记为
未知，不能严肃评估扣除成本后的收益。

## 决策

v0.21 在健康的三样本 Binance server-time 探针之后，顺序执行五个固定的
`fapi.binance.com` 无凭据 GET：

- 当前 Mark/Index/Funding；
- 两根 1m Premium Index Kline；
- 当前 Open Interest；
- 最近最多 30 根 4h Open Interest；
- 最近最多 30 次已结算 Funding Rate。

请求对象、host、路径、查询参数、顺序、重试数和响应大小全部固定。transport
禁用环境代理，只接受 HTTPS 固定 host 和固定最终 URL；CLI 不提供 URL、
header、proxy、key、secret、account、order 或 time override。

每个响应保存完整 UTF-8 body、SHA-256、selected headers、纠偏后请求/接收
时刻和 receipt hash。验证器必须从 raw receipt 重建 Mark-Index 基差、
Premium close、OI 变化、Funding 间隔和全部场景；Artifact self-hash 之外
仍需要调用方保存 external attestation hash。

Funding 场景统一使用 1000 USDT 名义本金，正数表示 SHORT 收到：

- 下一次结算按当前 last Funding Rate；
- 只有历史结算间隔一致时，才报告未来 24h 的重复当前利率场景；
- 同样条件下报告最近绝对 Funding 最大值两倍的 SHORT 不利场景。

这些值是压力场景，不是预测，也不能写入 realized PnL。

## 失败关闭边界

1m Kline 必须连续且覆盖当前 source time；4h OI 必须连续且不过期；Funding
历史必须有序且不过期；下一次 Funding 必须处于 source time 后 24h 内。
符号错误、JSON binary float、重复 key、非有限 Decimal、负 OI、非正价格、
未来/过期历史、异常时钟、redirect、非 200 或 body 篡改全部失败关闭。

2026-07-27 的真实直连尝试在健康时钟探针后，于第一个官方 Futures 请求发生
`PERPETUAL_TRANSPORT_FAILURE`。失败证据被冻结，未使用代理、网页结果、
第三方数据或其他交易所响应替代。

## 结果与资格

- `context_eligibility=CONTEMPORANEOUS_CONTEXT_ONLY`
- `short_execution_eligibility=NOT_IMPLEMENTED`
- `paper_eligibility=LONGITUDINAL_COLLECTION_IN_PROGRESS`
- `profitability_eligibility=INSUFFICIENT_DURATION_COST_AND_EXECUTION`

本 ADR 增加的是收益判断所需的可重放上下文，不增加交易 alpha，不授权
SHORT、账户、杠杆、Broker、订单、AI 自动决策或真实资金。
