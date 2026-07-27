# ADR-0018：公开输入的离线 Paper 双臂重放

状态：Accepted

日期：2026-07-27

## 背景

v0.17 已能保存同时公开行情及真实客户端接收时刻，但仓库仍缺少从决策输入
到策略、模拟成交和经济账本的闭环。若直接把历史 Kline 与当前 BBO 拼接，
会制造不存在的历史成交；若在没有批准模型时伪造 AI 分数，又会污染后续
AI-vs-baseline 配对结论。

## 决策

v0.18 只运行一个当前 ETHUSDT 决策周期，网络边界固定为四个无凭据 GET：

1. 4h Kline，最多 200 根；
2. 单符号 `exchangeInfo`；
3. 冻结决策时刻；
4. 单符号 BBO；
5. 最近 100 个 AggTrade。

这里的“四个 GET”是 Kline、exchangeInfo、BBO、AggTrade；第 3 项是本地
时钟冻结，不是网络请求。执行观察请求必须在两个决策输入响应均已收到后
才可开始。完整原始 UTF-8 response、body hash、请求/接收/记录时刻和收据
都进入 Artifact，并可从原始 response 重跑。

简单基线固定为 `SPOT_LONG_SMA20_VOL12_BUCKET25_V1`：

- 最新已收盘 4h close 高于此前 20 根均值时发出 LONG，否则保持 FLAT；
- 用最近 20 个 4h log return 的样本标准差年化；
- 基础暴露为 `min(1, 0.12 / max(volatility, 0.12))`；
- LONG 风险档位固定为 25%，起始虚拟权益固定为 1000 USDT。

模拟成交固定为 `OFFLINE_PAPER_CONSERVATIVE_BBO_V1`。买入价使用
`ask × 1.001` 后向上按 tick 取整；保守退出价使用 `bid × 0.999` 后向下
取整。数量向下按 step 取整，并受公开 ask quantity、最大数量、最小数量和
最小名义价值限制。开仓与预期退出各假设 15 bps taker fee。滑点已进入
成交价，不得再次从损益扣除。

基线和 AI 使用两个独立临时 SQLite WAL：

- `BASELINE_LEDGER / BASELINE_ONLY`
- `AI_LEDGER / AI_ENHANCED`

两者使用同一决策时刻和同一市场输入。当前没有批准模型，因此 AI 臂固定
为 `NOT_RUN_NO_APPROVED_MODEL`、`FREEZE_INCREASES`、零成交；不得使用
启发式数值冒充 AI 输出，配对统计样本数固定为 0。

Artifact 同时使用 self-hash 和 Artifact 外保存的 attestation hash。验证器
必须重放原始响应、决策、取整、成交和两套经济账本，self-hash 不能自证
来源可信。

## 结果

优点：

- 首次闭合真实接收输入→正式决策契约→保守模拟成交→经济账本；
- LONG/FLAT 都由预先冻结规则决定，不能为制造成交而修改；
- 交易所公开 filter 直接约束 tick/step/min notional；
- AI 缺席被当作明确状态，不产生虚假增量；
- 立即清算权益把双边费用和滑点显式计入压力账。

限制：

- 单次 smoke 不是 90 天 Paper；
- REST BBO 没有源序列，AggTrade 只覆盖最近窗口；
- 15 bps 是研究假设，不是账户真实费率；
- 没有永续、Funding、Mark/Index/Premium/OI 同时上下文；
- 没有 AI 模型，因此不能比较 AI 与简单基线；
- 立即保守清算损益是执行成本压力值，不是 24h 策略收益。

## 资格结论

所有 v0.18 Artifact 固定为：

- `paper_eligibility=OFFLINE_PAPER_SMOKE_ONLY`
- `profitability_eligibility=INSUFFICIENT_DURATION_AND_AI`
- `paired_statistical_eligibility=INELIGIBLE_AI_NOT_RUN`

本 ADR 不授权 API Key、账户、Broker、订单、自动交易、资金接入或盈利
声明。
