# v0.21 当前永续上下文与 Funding 成本设计

日期：2026-07-27

状态：Frozen for implementation

## 1. 目标

为 ETHUSDT 4h 研究/Paper 决策生成一个与当前时刻绑定、可离线重放的
USDⓈ-M 永续上下文快照，补齐 Mark、Index、Premium、Open Interest 和
Funding。它用于判断基差、拥挤度和 SHORT 的资金费方向，不负责提出交易、
执行永续订单或升级资金资格。

## 2. 固定公共请求

只允许 `https://fapi.binance.com` 下五个无凭据 GET：

1. `/fapi/v1/premiumIndex?symbol=ETHUSDT`
2. `/fapi/v1/premiumIndexKlines?symbol=ETHUSDT&interval=1m&limit=2`
3. `/fapi/v1/openInterest?symbol=ETHUSDT`
4. `/futures/data/openInterestHist?symbol=ETHUSDT&period=4h&limit=30`
5. `/fapi/v1/fundingRate?symbol=ETHUSDT&limit=30`

接口身份参考 Binance 官方 USDⓈ-M 文档和官方 connector 的公开 market
methods。实现不接受 URL、host、header、proxy、key、secret、账户或订单
覆盖；禁用环境代理；只允许同 host HTTPS redirect；顺序执行、每个端点一次、
不自动重试。

捕获前先复用 v0.20 三样本 Spot server-time probe。只有
`HEALTHY_ALIGNED/HEALTHY_CORRECTED` 才允许五个 Futures GET。总请求边界为
`3 + 5 = 8`。

## 3. 原始证据与时间约束

每个 receipt 保存固定 request、status/final URL、selected headers、原始
UTF-8 body、SHA-256、本机/纠偏后开始与接收时刻及 receipt hash。

- `premiumIndex.time`、`openInterest.time` 必须落在本次可信捕获窗口附近；
- Funding 和 OI history 必须按 source timestamp 严格递增；
- 只接受 ETHUSDT；
- 所有价格、利率、数量使用规范 Decimal 字符串，拒绝 JSON binary float、
  NaN、Infinity、负 OI、非正价格和越界时间；
- response body 大小有固定上限；
- 完整 raw receipt 必须能重新解析到同一规范 observation。

## 4. 规范上下文

快照输出：

- mark/index/estimated settle；
- mark-index basis USDT 和 basis rate；
- 当前 premium-index 1m close；
- last funding rate、next funding time、interest rate；
- 当前 OI 数量；
- 最近 30 个 4h OI value 及最后一个 4h 变化率；
- 最近 30 个已结算 Funding Rate；
- 从连续 settlement timestamp 推导的 observed interval，若不一致则为 null。

`premiumIndexKlines` 的 premium close 与 `(mark-index)/index` 是不同事实，
不得互相替代。

## 5. Funding 成本场景

统一以 `1000 USDT` 名义本金报告，正数表示 SHORT 收到、负数表示 SHORT
支付：

- `next_funding_short_cashflow_per_1000`：
  `1000 * lastFundingRate`；
- 若 observed interval 可证明，按 `nextFundingTime` 计算未来 24h 内的结算
  次数；
- `repeated_current_rate_24h_short_cashflow_per_1000`：
  仅作“当前 rate 不变”场景，不是预测；
- `two_x_recent_absolute_adverse_24h_short_cashflow_per_1000`：
  用最近已结算 rate 的最大绝对值构造对 SHORT 不利的负 rate，再乘 2 和
  结算次数。

没有一致 observed interval 时，24h 数值为 null 并标记
`FUNDING_INTERVAL_NOT_PROVEN`。这些情景不得写入 realized PnL。

## 6. Artifact 与资格

`PerpetualContextSnapshot` 包含 server-time probe、五个 receipts、规范
observations、质量报告、Funding 场景、self-hash 和 Artifact 外
attestation。验证器必须从 raw receipts 重建全部字段。

固定资格：

- `context_eligibility=CONTEMPORANEOUS_CONTEXT_ONLY`
- `short_execution_eligibility=NOT_IMPLEMENTED`
- `paper_eligibility=LONGITUDINAL_COLLECTION_IN_PROGRESS`
- `profitability_eligibility=INSUFFICIENT_DURATION_COST_AND_EXECUTION`

## 7. 当前网络限制

2026-07-27 本机对 `fapi.binance.com`、`fapi1` 至 `fapi4` 的无代理 TLS
连接均被远端/网络路径重置；Spot public host 正常。实现不得使用第三方代理、
网页结果或其他交易所数据伪造 Binance receipt。

因此 v0.21 可以完成契约、传输边界、fixture 重放和失败关闭验证，但只有在
官方 Futures host 可直连后，才能冻结真实 contemporaneous smoke。缺少真实
smoke 不影响代码版本发布，但必须保留
`REAL_FUTURES_SMOKE_NOT_CAPTURED_NETWORK_UNREACHABLE`，不能声称当前永续
数据已经进入长期 Paper。

## 8. 非目标

- 不修改 v0.18 基线信号；
- 不启用 SHORT 或永续成交；
- 不把未来 Funding 场景当作已实现收益；
- 不接账户费率、杠杆、保证金、Broker 或订单；
- 不使用 LLM/AI 解释快照；
- 不因环境受限而放宽来源或 host。
