# v0.18 真实输入驱动的离线 Paper 重放设计

状态：`APPROVED`

批准依据：项目所有者已全权委托并要求持续按版本交付；本设计按资金安全、
证据门、基线优先、AI 增量验证和不夸大盈利的既有规则冻结。

日期：2026-07-27

## 1. 目的

v0.18 将 v0.17 的同时行情证据继续推进为第一条完整、可重放的离线 Paper
业务链：

1. 用实际接收的 4h warm-up 构造决策输入；
2. 用冻结的简单趋势基线产生 Proposal、MetaDecision 和虚拟目标；
3. 在同一决策时刻建立 AI 对照臂；没有可信模型时明确冻结，而不是伪造 AI；
4. 用决策后收到的 BBO、公开交易规则和保守成本政策生成 simulated fill；
5. 把两个臂分别写入追加型虚拟账本并生成 EconomicLedgerSnapshot；
6. 生成配对 smoke observation、完整 Paper run snapshot 和外部 attestation；
7. 机器上阻止短期 smoke 被误报为 90 天 Paper、OOS 或盈利证据。

## 2. 不包含

- API Key、账户、余额、订单、Broker、交易 API 或任何真实副作用；
- 账户专属 `myFilters`、实际手续费 tier、折扣或真实成交；
- 永续 SHORT、Funding、Mark/Index/Premium/OI；
- 已批准 ModelBundle、真实 AI 推理或 AI 增量价值；
- 90 个自然日 Paper、月度序列、正式统计 CI 或 Release Gate PASS；
- 根据本次短期结果修改策略或成本参数。

## 3. 权威约束

项目内部冻结规则：

- 回测、Paper、Live 共用业务语义；
- 4h 信号不得在同一根 4h 收盘价成交；
- 简单基线必须先于 AI 证明经济价值；
- AI 只能过滤/分档，不能创造基础方向；
- AI 与基线使用相同 Proposal、时间轴、资本和 fill model；
- Paper 最少 90 个自然日，短期 smoke 只能证明流程触发；
- Spread/Slippage 体现在 fill price，不能在 PnL 中重复扣除；
- 手续费必须是独立经济事实。

Binance 官方公开契约：

- `GET /api/v3/exchangeInfo` 提供 symbol status、order types 和 symbol
  filters；
- `PRICE_FILTER` 定义 price tick；
- `LOT_SIZE` 定义 min/max quantity 和 step size；
- `MIN_NOTIONAL`/`NOTIONAL` 定义公开最低名义金额规则；
- 账户专属 `myFilters` 是 `USER_DATA`，v0.18 不访问，因此账户过滤器仍未知。

权威链接：

- <https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md>
- <https://github.com/binance/binance-spot-api-docs/blob/master/filters.md>
- <https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md>

## 4. 方案选择

### 方案 A：直接把 v0.17 的两根 4h Kline 当策略输入

没有足够 warm-up，无法形成版本化趋势/波动特征。拒绝。

### 方案 B：使用事后归档生成历史 Paper 盈利序列

归档是 `ARCHIVE_REPLAY_ONLY`，不能证明历史决策时可用。拒绝。

### 方案 C：同时获取 warm-up + 决策后执行观察 + 虚拟双账本

先从公开端点接收 200 根 4h Kline 和 `exchangeInfo`，冻结决策输入；再在
决策之后请求 BBO/AggTrade，保守模拟成交。所有原始 response、接收时刻、
策略/成本政策和两个虚拟账本都进入哈希链。采用。

## 5. 捕获时序

```text
GET 4h klines limit=200
  → GET exchangeInfo(symbol)
  → freeze PaperDecisionInput + decision_time
  → run baseline + explicit AI-unavailable arm
  → GET bookTicker(symbol)
  → GET aggTrades(limit=100)
  → conservative simulated broker
  → BASELINE_LEDGER + AI_LEDGER
  → OfflinePaperRunSnapshot + external attestation
```

顺序是证据的一部分。BBO 和 AggTrade 必须在 `decision_time` 之后收到，避免
使用决定发生前无法固定的“最佳成交”。调用方不能传 URL、query、header、
API key 或任意策略参数。

## 6. `PaperMarketInput`

### 6.1 固定请求

只支持 `ETHUSDT` Spot LONG：

- `GET /api/v3/klines?interval=4h&limit=200&symbol=ETHUSDT`
- `GET /api/v3/exchangeInfo?symbol=ETHUSDT`
- 决策冻结后：
  - `GET /api/v3/ticker/bookTicker?symbol=ETHUSDT`
  - `GET /api/v3/aggTrades?limit=100&symbol=ETHUSDT`

生产 transport 复用 v0.17 的 exact-host、GET-only、no-proxy、bounded read
边界。每个 receipt 保存原始 UTF-8 JSON 和 client request/receive time。

### 6.2 4h warm-up

- 最多 200 行，严格使用官方 Kline 12 列；
- 只使用 `close_time < decision_time` 的闭合 Kline；
- 至少 21 根闭合 Kline；
- business key、OHLC、成交量、时间和 source payload hash 全部保留；
- 历史 Kline 在本次响应前不能假定已可用；所有 warm-up 行的
  `available_at` 都是本次 response receive time；
- 最新闭合 bar 与前 20 根形成一个当前决策，不生成虚构历史决策。

### 6.3 公开 InstrumentMetadata

严格提取：

- status 必须 `TRADING`；
- base/quote 必须 `ETH`/`USDT`；
- order types 必须包含 `MARKET`；
- `PRICE_FILTER.tickSize`；
- `LOT_SIZE.minQty/maxQty/stepSize`；
- `MIN_NOTIONAL` 和/或 `NOTIONAL.minNotional`；若同时存在，保守取较大值；
- raw symbol/filter payload、payload hash、metadata hash。

公开 `exchangeInfo` 不包含账户手续费，也不能证明账户没有 `MAX_ASSET`
等专属 filter。结果只能作为研究 metadata。

## 7. 冻结基线

策略：

`SPOT_LONG_SMA20_VOL12_BUCKET25_V1`

决策只使用最近 21 根闭合 4h close：

```text
reference_sma20 = mean(previous 20 closes)
latest_close = newest closed close
trend_ratio = latest_close / reference_sma20 - 1

if latest_close > reference_sma20:
    direction = LONG
    action = SET_TARGET
    risk_bucket = 0.25
else:
    direction = FLAT
    action = HOLD_CURRENT
    risk_bucket = null
```

波动目标：

```text
log_return_i = ln(close_i / close_(i-1))
sample_vol = sample_std(last 20 log returns) × sqrt(6 × 365)
base_volatility_exposure = min(1, 0.12 / max(sample_vol, 0.12))
```

LONG 目标：

```text
signed_target_ratio = base_volatility_exposure × 0.25
target_notional = starting_virtual_equity × signed_target_ratio
```

规则、lookback、年化因子、资本、bucket 和 Decimal 运算全部版本化、哈希化。
本版本不根据 smoke PnL 改变参数。

## 8. 双臂语义

### 8.1 Baseline arm

生成现有正式契约：

- `StrategyProposal`
- `MetaDecision(decision_source=NO_AI_BASE)`
- `TargetPosition`

若趋势为 FLAT，MetaDecision 使用 `HOLD_CURRENT`，不以 bucket 0 暗示平仓。

### 8.2 AI arm

v0.18 没有 approved ModelBundle 和可信 inference runner。AI arm 必须记录：

- `arm_status=NOT_RUN_NO_APPROVED_MODEL`
- 与 baseline 相同的 decision key、Proposal 和资本；
- `recommended_action=FREEZE_INCREASES`
- 无模型概率、分位数、bucket 或虚拟订单；
- 独立 `AI_LEDGER`，起止权益相同、无 fill；
- `paired_eligibility=INELIGIBLE_AI_NOT_RUN`

不得创建名称看似模型、实为手工阈值的伪 ModelBundle。未来真实 AI runner
必须通过独立版本扩展接入。

## 9. 保守 simulated broker

政策：

`OFFLINE_PAPER_CONSERVATIVE_BBO_V1`

固定研究假设：

- starting virtual equity：`1000 USDT`
- entry taker fee：15 bps
- expected exit taker fee：15 bps
- BBO stress slippage：10 bps/side
- 只使用 decision 后收到的单次 BBO；
- BUY fill price：
  `round_up(ask × 1.001, price_tick)`；
- conservative exit price：
  `round_down(bid × 0.999, price_tick)`；
- quantity 向下对齐 `LOT_SIZE.stepSize`；
- fill quantity 不超过显示 ask quantity；
- 不跨越未观察 depth，不根据 AggTrade gap 补造流动性；
- 不满足 min quantity/notional 时为 `NO_FILL`；
- 显示量不足时只形成 `PARTIAL`；
- entry fee 与 expected exit fee 独立记录；
- implementation shortfall 相对 decision reference close 计算，已体现在 fill，
  不再重复扣除。

固定 15 bps 不是 Binance 账户事实，只是向保守方向冻结的研究假设。任何
正式 Paper/Production 必须替换为已批准、有效期明确的真实账户
FeeScheduleSnapshot。

## 10. 虚拟账本

Baseline 与 AI 使用两个独立临时 SQLite WAL `EventLedger`：

- 账户分别为 `paper-baseline` / `paper-ai`；
- UTC 当日 00:00 记录起始权益；
- simulated fill 作为 `FillRecorded` 追加；
- run end 记录 conservative liquidation equity；
- 无真实 deposit/withdrawal/funding；
- AI arm 无模型时不产生 fill；
- 每个账本生成现有 `EconomicLedgerSnapshot v1.1`；
- 两个 snapshot 使用相同窗口、资本、Accounting/Cost policy 和 fill policy。

LONG 未平仓的 run-end liquidation：

```text
cash = starting_equity - entry_notional - entry_fee
liquidation_value =
    cash + filled_qty × conservative_exit_price - expected_exit_fee
```

若无 fill，起止权益相同。

## 11. `OfflinePaperRunSnapshot`

完整 Artifact 至少包含：

- schema/version/run ID；
- 原始四个 response receipts；
- Paper market input、feature snapshot 和 public metadata；
- decision key/time；
- 冻结 baseline/fill/accounting/cost policy 及 hashes；
- baseline Proposal/MetaDecision/Target；
- baseline simulated order/fill/result；
- baseline/AI EconomicLedgerSnapshot；
- AI explicit unavailable record；
- paired smoke observation；
- quality report；
- `paper_eligibility=OFFLINE_PAPER_SMOKE_ONLY`；
- `profitability_eligibility=INSUFFICIENT_DURATION_AND_AI`；
- roots、snapshot hash。

验证器必须从原始 response 重新解析 warm-up、metadata、BBO/AggTrades，
重跑策略、order rounding、fill model 和两个 EventLedger，逐字段比较完整
snapshot。只改写输出并重算 self-hash 不能通过。

完整信任还要求 snapshot 外的 external attestation，绑定 run identity/time、
market response root、decision root、两个 economic snapshot hashes 和完整
snapshot hash。

## 12. 质量与失败关闭

Blocking：

- 任意请求非 200、host/path/query 不匹配；
- BBO/AggTrade 在 decision time 前接收；
- warm-up 少于 21 根闭合 bar、OHLC/时间非法；
- symbol 非 TRADING、缺 MARKET、缺必需 filter；
- binary float、NaN、Infinity、负价量；
- quantity 向上取整或超过 BBO 显示量；
- fill price 对 BUY 优于 stressed ask；
- min quantity/notional 被绕过；
- fee/exit fee 未独立扣除；
- source receipt、策略、fill、ledger 或 attestation 重放不一致；
- AI 无可信模型却产生非零目标/fill。

Mandatory warnings：

- `ACCOUNT_FEE_SCHEDULE_UNOBSERVED`
- `ACCOUNT_SPECIFIC_FILTERS_UNOBSERVED`
- `BBO_SEQUENCE_UNOBSERVABLE_REST_SNAPSHOT`
- `AGG_TRADE_WINDOW_GAPS_POSSIBLE`
- `PERPETUAL_CONTEXT_NOT_CAPTURED`
- `AI_MODEL_NOT_RUN`
- `PAPER_DURATION_BELOW_90_DAYS`
- `NO_FORMAL_STATISTICAL_SAMPLE`

## 13. 真实 smoke 与赚钱含义

真实 smoke 运行一次 ETHUSDT public-only Paper cycle。市场决定 LONG 或 FLAT
由预先冻结规则和当时数据决定，不能为了演示 fill 而修改规则。若为 LONG，
生成保守 partial/full fill 和 run-end liquidation；若为 FLAT，生成合法
no-trade 账本。

本版本证明的是：

- 真实输入能进入同一个可重放决策/成交/账本链；
- 成本和缺口不会被隐藏；
- AI 缺失会冻结，而不是伪造优势。

它不证明：

- 基线赚钱；
- AI 优于基线或平台 AI；
- Paper 通过；
- 可以接入资金。

下一阶段必须让该 pipeline 按固定调度持续至少 90 天，接入真实 approved
模型与账户成本事实，再生成月度配对统计和正式 ReleaseEvidence。
