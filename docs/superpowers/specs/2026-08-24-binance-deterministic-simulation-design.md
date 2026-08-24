# Binance Deterministic Simulation Design

日期：2026-08-24

目标版本：`v0.71.0`

发布基线：annotated `v0.70.0`，peeled commit
`50c41c847c49771dfd169778c850d270fab794c8`

适用分支：`codex/v0.71-binance-deterministic-simulation`

## 1. 决策摘要

v0.71 实现 replacement v3 的纯计算 Binance Spot-long / USDⓈ-M
perpetual-short deterministic simulation，并将完整 decision、risk、order、fill、fee、
funding、position、protective-stop 和 reconciliation 证据绑定到 v0.70 已验证的
`RESULT_PREPARED -> OPPORTUNITY_OBSERVED` 事件链。

本版只接受 committed fixture bytes，不读网络、系统时钟、账户、API key 或生产
root，不提供 natural Runner、scheduler、deployment、install/start、Broker 或任何真实
order 能力。因此 v0.71 是下一阶段运行候选的 deterministic proof，不开始 7 天或
90 天计时，不产生 Paper/Canary/盈利资格。

## 2. 权威与前序

### 2.1 唯一事实源

`state/challenger-replacement-events-v1` 的 append-only canonical event log 仍是唯一权威。
simulation engine、内存 snapshot、fixture 和未来 export 都不是独立事实源。

v0.71 不修改 v0.69 plan bytes/hash、v0.70 event envelope 或历史 event store 耐久协议。
新 simulation contract 只冻结执行模型的保守研究假设，必须绑定：

- v0.69 plan ID/hash/file SHA；
- v0.70 annotated tag/peeled commit/manifest identity；
- 本版 schema 版本与 canonical algorithm/policy hashes。

golden fixture manifest 单向绑定 simulation contract hash 和每个 fixture SHA-256；
release manifest 再同时绑定 contract/fixture manifest/code 文件。contract 不反向绑定
尚未生成的 fixture manifest，因此不形成 hash cycle。

simulation contract 在任何 natural start receipt 前发布，不是 post-hoc 经济参数调整。

### 2.2 Build identity 与 event-root 隔离

pre-release tests 只接受 schema 严格的 `v0.71.0-fixture` build mapping；event header
只绑定该 mapping 的 business hash，不宣称它证明尚未存在的 release provenance。
这些 tests 只写入新建、owner-only、明确标记为 test fixture 的空 event root。
v0.70 v1 committed regression 使用
独立 fixture roots 只读回放；v0.70/v0.71 events 不得在同一 root 内混用，也不得
迁移到未来 production root。

发布时 release manifest/status/ADR 才反向绑定 v0.71 exact tag/peeled/manifest identity，
不让 simulation contract 自我嵌入未知的未来 commit 形成 hash cycle。未来 natural
deployment/start 必须由 strict start loader 绑定当时单一已发布 release identity 和空
production event root。一个 cohort 中禁止静默跨 build；如确需升级，必须先发布
独立、可重放的 build-transition 合同。v0.71 不设计或执行该过渡。

### 2.3 未启动边界

v3 仍为 `PLAN_FROZEN_REPLACEMENT_V3_NOT_STARTED`。v0.71 不检查、创建或修改预期
production root/plist/service，不使用 v0.68 install trust chain。所有 tests 使用显式
temporary owner-only event-root capability。

## 3. 采用与拒绝的构件

### 3.1 可复用纯构件

仅复用已验证的无 I/O 原语：

- `canonical.py` / `decimal_math.py`：唯一 canonical JSON/Decimal/hash；
- `instruments.py`：InstrumentMetadata、tick/step/min-notional 和 order plan rounding；
- `orders.py`：去重、partial fill、UNKNOWN 和 reconciliation 聚合语义；
- `challenger_replacement_events.py`：capability-safe no-overwrite append/replay；
- v0.70 opportunity ID、window、terminal/no-backfill 投影。

### 3.2 不直接复用

`system_paper_runtime.py`、`system_paper_broker.py` 的隐含 long-only snapshot 和内部费率不作为
replacement authority。`ledger.py` 的通用部件只在逐条证明支持 signed perpetual 后才可
复用；否则写窄型 replacement position calculator，不扩大通用 ledger。

NautilusTrader v0.65 结论仍是 `INCONCLUSIVE_KEEP_CURRENT_CORE`，不 import、安装或嵌入
v0.71。Freqtrade/vectorbt 也不进入 runtime。

## 4. Canonical simulation contract

### 4.1 固定模式

contract 状态固定为：

```text
mode = FIXTURE_ONLY_DETERMINISTIC_BINANCE_SIMULATION
venue = BINANCE_ONLY
economic_asset = ETH
starting_virtual_equity_usdt = 100
gross_exposure_limit = 0.5
network_requests = 0
account_requests = 0
broker_requests = 0
orders_submitted_to_venue = 0
credentials_used = false
production_state_writes = 0
```

`100 USDT / 0.5x` 只是预注册 E0 的 simulation rehearsal，不是资金或 E0 授权。

### 4.2 保守成本假设

v0.69 plan 未冻结 account-specific fee/slippage/stop 数值。v0.71 在运行前用独立
simulation contract 冻结：

```text
market_order_slippage_per_side = 0.001
spot_taker_fee = 0.0015
perpetual_taker_fee = 0.0015
protective_stop_distance = 0.02
funding_source = EXACT_FIXTURE_RATE_AT_SCHEDULED_BOUNDARY
quote_quantum_usdt = 0.00000001
```

费率是 conservative research assumption，不宣称为用户 Binance 实际费率。未来 natural
simulation 需新的固定来源/loader；真钱 Canary 必须在 activation contract 中核对实际
account commission，不得沿用“模拟费率就是真实费率”。

### 4.3 整数与 Decimal

业务运算只用 `Decimal`。canonical decimal 不允许 exponent、NaN/Infinity、negative zero
或二进制 float。费用始终向不利方向量化；quantity 向下 step rounding；buy price 向上
tick rounding，sell price 向下 tick rounding。

## 5. Canonical source bundle

v0.71 新增 strict schema `challenger-replacement-binance-simulation-input-v1`。exact keys 包含：

- opportunity ID/scheduled/capture/observed time；
- 21 根连续、已封闭、UTC 4h ETHUSDT close bars；
- Spot 和 USDⓈ-M perpetual 的 exact InstrumentMetadata payload/hash；
- 两个产品的 bid/ask/last，perpetual mark，以及显式
  `funding_boundary_at_or_null/funding_rate_or_null`；两个 funding 字段必须同时为 null
  或同时有值，boundary 必须等于 `scheduled_for`；
- source kind=`COMMITTED_FIXTURE_NOT_LIVE_MARKET`；
- authority counts 全部为 0。

bars 必须恰好 21 根、时间无缺口、严格递增，最后一根 close boundary 等于
`scheduled_for`。OHLC 必须正数且 `low <= open/close <= high`。bid <= last <= ask，
perpetual mark 必须正数。metadata 必须在 observed time 唯一 effective，且精确为：

```text
BINANCE:SPOT:ETHUSDT
BINANCE:USDT_PERP:ETHUSDT
```

不得用 fixture 统计 7 天/90 天墙钟或写成“真实公开行情”。

InstrumentMetadata 中 `contract_multiplier` 必须为正 Decimal，并进入所有
notional/fee/PnL/funding 公式。为避免两个费率事实源，fixture metadata 的
`taker_fee` 必须与 simulation contract 中对应 product 的费率精确相等；
不相等直接 `SIMULATION_CONTRACT_METADATA_CONFLICT`，不选择任一方继续。

## 6. Decision policy

### 6.1 指标

`prior_sma20` 固定为前 20 根 close 的 Decimal arithmetic mean，不包含 latest close。
`eth_log_return_5` 只用于判断符号；对正价格，其符号与 `latest_close - close[-6]`
完全等价，因此 Python 3.9/3.12 都使用 exact Decimal comparison，不调用 float/log。

long signal 精确为 `latest_close >= prior_sma20 * 1.005` 且
`latest_close > close[-6]`；short signal 精确为
`latest_close <= prior_sma20 * 0.995` 且 `latest_close < close[-6]`。这是 v0.69
`decision_policy.long_entry/short_entry` 的 Decimal 实现，不引入新策略参数。

### 6.2 状态决策

```text
FLAT + long signal   -> OPEN_SPOT_LONG
FLAT + short signal  -> OPEN_PERP_SHORT
FLAT + neither       -> HOLD_FLAT
SPOT_LONG + exit     -> CLOSE_SPOT_LONG
SPOT_LONG + no exit  -> HOLD_SPOT_LONG
PERP_SHORT + exit    -> CLOSE_PERP_SHORT
PERP_SHORT + no exit -> HOLD_PERP_SHORT
risk flatten         -> RISK_FLATTEN
```

entry threshold、minimum hold 8h、vertical exit 24h 与 v0.69 plan 逐字一致。持仓时忽略反向
entry signal，只评估当前产品退出。close 后设置 `reverse_blocked_until_next_opportunity=true`，
同一 opportunity 不得反手。如果任何输入导致 long/short 同时真，固定
`DECISION_POLICY_AMBIGUOUS`。

decision document 使用独立 strict schema，绑定 plan/policy/source/previous-state hashes、全部
indicator values、position-before、action 和 exact reason。不允许 AI、训练参数或外部选择 action。

## 7. PositionAuthority 与 snapshot

snapshot 仅允许：

```text
FLAT
SPOT_LONG
PERP_SHORT
```

canonical snapshot 绑定 parent snapshot hash/opportunity ID，并包含 cash、signed base quantity、entry
price/time、perpetual isolated margin、realized/unrealized PnL、fees、funding、marked/peak equity、UTC-day
start equity、risk state、active order/protective-stop、reverse block，以及
`position_certainty=VERIFIED|UNRESOLVED`。

不变量：

- FLAT 时 quantity/margin/entry/order/stop 全为零/null；
- SPOT_LONG quantity > 0，无 margin borrowing，perpetual 字段为零；
- PERP_SHORT signed quantity < 0，isolated margin > 0，Spot quantity 为零；
- 不允许同时两产品非零；
- 不允许 Hedge/Cross/现货借贷；
- `UNRESOLVED` 时 position state/quantity 只表示 last verified projection，不宣称当前
  simulated venue position 已知；必须同时记录 unresolved intent IDs 和
  `STAGE_FAILED_LOCKED`，不再进行 strategy/risk-increasing action；
- 所有 snapshot 重算 self hash，fresh replay 必须逐字节一致。

snapshot 是 OBSERVED event 内的可重建 projection，不另外写 state file。MISSED 不修改
position/economic snapshot，但必须遵守第 7.2 节的 economic-gap 规则。

### 7.1 唯一 accounting 方程

记 fill quantity 的绝对值为 `q`、signed position quantity 为 `Q`、
`contract_multiplier=M`、fill/mark/entry 价为 `F/P/E`。所有 quote debit 向上、
quote credit 向下量化到 `0.00000001 USDT`；marked equity 向下量化，
风险比较使用量化后数值。

- `notional(q, price) = q * M * price`；
- market BUY 参考 `ask * (1 + slippage)` 并向上 tick rounding；market SELL
  参考 `bid * (1 - slippage)` 并向下 tick rounding；
- `fee = abs(q * M * F) * taker_fee`，始终作为 cash debit；
- Spot BUY：`cash -= q*M*F + fee`，`Q += q`；Spot SELL：
  `cash += q*M*F - fee`，`Q -= q`；
- Spot normal policy 不加仓；fault fixture 若产生 partial open fills，`E` 也必须按
  filled notional 的 quantity-weighted average 重算；
- Spot realized PnL 在 SELL 时为 `q*M*(F-E)`；Spot unrealized 为
  `Q*M*(bid-E)`，Spot equity 为 `cash + Q*M*bid`；
- perpetual `Q<0`表示 short；open/partial-open 的 `E` 按 filled notional 的
  quantity-weighted average 重算，正常策略不加仓，只有 fault fixtures 可出现
  partial fill；
- perpetual open 只扣 fee，`isolated_margin = abs(Q)*M*E/configured_leverage`，
  `available_cash = cash - isolated_margin`；margin 是保留额，不再从 equity 重复扣除；
- perpetual unrealized 为 `Q*M*(P-E)`，partial/complete close 的 realized 为
  `closed_signed_Q*M*(F-E)`，其中 `closed_signed_Q` 取被关闭的原 short 负数；
- perpetual close 将 realized 加入 cash、扣除 close fee，按剩余 Q 重算/释放
  isolated margin；`perpetual_equity = cash + unrealized`；
- funding cashflow 为 `-Q*M*mark*funding_rate`，正数为 credit、负数为 debit，
  在风险比较前进入 cash；
- `marked_equity` 在 FLAT 为 cash，Spot 为 `cash+Q*M*bid`，Perp 为
  `cash+Q*M*(mark-E)`。realized/unrealized/fees/funding 分量用于对账，不再向
  marked equity 重复相加。

v0.71 不模仿 Binance liquidation engine。如 `available_cash < 0` 或
`marked_equity <= 0`，固定 `SIMULATION_MARGIN_EXHAUSTED`、flatten/fail closed；该结果
不证明真实交易所强平价或保证金规则。

每个 observed boundary 处理顺序固定为：先对已存在仓位评估上一间隔的 stop，
再记录该 boundary 对应 funding，再 mark/equity/daily/high-water risk，最后才允许
本机会的 strategy decision 与新 risk approval。任一前置步骤失败，不得增加风险。

新 UTC 日的 `day_start_equity` 取本日 00:00 boundary 的 stop/funding/mark 已入账、
但本机会新 strategy action 尚未发生时的 current equity；genesis 取 100。
因此 20:00–00:00 的变动属于前一 UTC 日，新日不从旧 20:00 snapshot 起算。
`daily_loss=max(0, day_start_equity-current_equity)`。
先用 `drawdown=max(0, previous_high_water-current_equity)` 检查当前边界，再以
`max(previous_high_water,current_equity)` 更新 high water；fee/funding/stop fill 已在
`current_equity` 中，不重复计入。每一个 fill、fee、funding 或 stop/flatten 变更后
都重算 daily/drawdown 风险，不只在新开仓后计算；任意变更越过门槛都必须
flatten/fail closed。

### 7.2 MISSED 与持仓经济缺口

FLAT 时 MISSED 只保留 snapshot。SPOT_LONG/PERP_SHORT 时 MISSED 意味着 stop/mark（以及
可能的 funding）未被观测。v0.71 不改 v0.70 MISSED exact payload；投影器必须从
`previous snapshot non-FLAT + canonical MISSED event` 确定性派生
`economic_gap_locked=true`，并把该派生值、MISSED event hash 和 last verified snapshot hash
绑入后续 projection hash。从此禁止新风险，不需要、也不允许在 MISSED payload 增字段。
禁止用后来 fixture 回填遗漏机会。

v0.71 无账户权威，因此不实现伪造的 gap reconciliation；该 fixture root 的后续
opportunity 最多产生只减仓/失败关联证据，经济 evaluator 必须标记
INCONCLUSIVE/INELIGIBLE。未来 natural runtime 若要解锁，须先冻结独立的账户/行情
reconciliation 证据合同，不属于 v0.71。

## 8. Risk contract

v0.71 使用 E0 rehearsal 数值：同时执行 `capital <= 100 USDT` 和 `gross <= 0.5x`，
实际批准 notional 取两者中更小者。下单数量不从未滑点价倒推；必须先按
第 7.1 节得到 adverse rounded fill，再在整数 quantity-step lots 中确定性选择同时满足
capital、min/max/min-notional、margin 和成交后
`abs(Q)*M*conservative_mark/marked_equity <= 0.5` 的最大数量。无合法数量则
NO_TRADE，禁止使用未用资金自动加仓。

持仓期间 gross exposure 在每个 observed boundary 以 Spot bid 或 Perp mark 和当前
marked equity 重算。因价格/权益漂移超过 0.5 时，在策略决策前优先生成
reduce-only 风险缩减；剩余 quantity 仍按上述“最大合法 lots”求解，无法在
一次确定性缩减后恢复 `<=0.5` 则 flatten/fail closed。

UTC daily loss 包含 realized、unrealized、fees 和 funding。当日亏损 `>= 2 USDT`
后停止新增风险，但允许 reduce/close。high-water drawdown `>= 5 USDT` 时必须保守
flatten 并设置 `STAGE_FAILED_LOCKED`。比较在等号边界就触发。

任何下列状态固定阻止新风险，并在有仓位时只允许 reduce/flatten：

```text
UNRESOLVED_UNKNOWN
DUPLICATE_ECONOMIC_ORDER
UNRECORDED_OR_CONFLICTING_FILL
LEDGER_POSITION_MISMATCH
DISASTER_STOP_MISSING_OR_UNCONFIRMED
ACCOUNT_MARGIN_OR_LEVERAGE_MODE_MISMATCH
CLOCK_MARKET_ACCOUNT_OR_USER_STREAM_INSUFFICIENT
S0_OR_S1_INCIDENT
CREDENTIAL_OR_IP_BOUNDARY_UNTRUSTED
EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE
```

在 fixture-only v0.71 中，account/credential 分支必须是 `NOT_APPLICABLE_ZERO_AUTHORITY`，不得伪造
“账户已验证”。

## 9. Order/fill/fee/funding/reconciliation

### 9.1 稳定身份

economic intent ID 由 plan/opportunity/action/position-before/approved-notional 确定性派生。attempt/client
IDs 由 intent 派生，不接收调用方传入。exact retry 幂等；同 intent 的不同经济内容为
conflict。

### 9.2 产品语义

- Spot open：BUY，无 reduce-only；Spot close：SELL，数量不得超过持仓；
- Perpetual open：SELL，one-way + isolated；E0 `gross_exposure_limit=0.5` 是名义
  仓位/权益比，不是 Binance leverage 字段。fixture 合同将可执行的整数
  `configured_leverage=1`，保证 initial notional 最多为 50 USDT；任何路径的
  configured/effective leverage 都不得超过技术硬上限 `2`；
- Perpetual close：BUY + reduce-only，数量不得超过 abs(short)；
- 任何反手先完成 close/cancel/reconcile/verified-flat，然后等下一 opportunity。

### 9.3 成交与成本

normal fixture 只允许 deterministic immediate full market fill。partial/timeout/disconnect/late-fill/
duplicate/impossible-overfill 只出现在固定故障测试中，不通过 public production callback、CLI
参数或环境变量注入。测试只 patch 已存在的私有低层边界。

成交价、notional、fee、funding、realized/unrealized PnL、cash、margin 和 equity
只按第 7.1 节的唯一公式计算，本节不定义第二套简写公式。无 funding
boundary 必须显式 null，不得猜测。

### 9.4 Protective stop

开仓 fill 后必须产生唯一 persistent stop intent/ack：Spot long trigger 为 entry
向下 2% 并向下 tick rounding，perpetual short trigger 为 entry 向上 2% 并向上
tick rounding。stop quantity 每次 fill 后精确等于当前 abs(position)；partial fill 必须
先 cancel/replace 并完成 ack，否则锁定风险。

对新完成的 4h bar，Spot long 在 `low <= trigger` 时触发，Perp short 在
`high >= trigger` 时触发。保守 gap reference：Spot SELL 使用 `min(bar.open, trigger)`，
Perp BUY 使用 `max(bar.open, trigger)`，随后再应用第 7.1 节的 adverse slippage/tick
rounding。stop 评估早于同机会 strategy exit；触发后本机会不得反手。

正常 strategy close 前必须先记录 stop cancel ack，再提交 reduce close。如 close 未得到
已对账的 terminal full fill，必须立即为已知剩余仓位重建并确认 stop；重建
失败则尝试 flatten，flatten 仍不确定则进入 `position_certainty=UNRESOLVED`
和 `STAGE_FAILED_LOCKED`，绝不返回“仍受保护”。测试中的
late stop fill 必须和 close fill 同时对账；如会超过原持仓或建立反向仓位，固定
`UNRECORDED_OR_CONFLICTING_FILL`/`LEDGER_POSITION_MISMATCH` 失败关闭，不做
自动修正。

如 stop 未确认，该 result 必须执行模拟 flatten；flatten 仍未确认时产生
canonical failed-lifecycle evidence 和风险锁，不得声称 lifecycle complete。MISSED
期间不猜测 stop 是否触发，按第 7.2 节进入 economic gap。

### 9.5 Reconciliation

result 必须同时记录 engine order aggregate、simulated venue position 和 canonical ledger position。三者的
product/side/quantity/fees/funding 必须 exact 一致；不一致固定
`LEDGER_POSITION_MISMATCH`，不可选择一方覆盖另一方。

## 10. Result evidence v2 与 event integration

v0.71 新增 `challenger-replacement-opportunity-result-evidence-v2` strict schema，在新的
v0.71 fixture roots 中 supersede v0.70 fixture-only v1，但不改 RESULT event payload
envelope。v2 evidence 绑定：

- plan/simulation-contract/build/opportunity/source/decision hashes；
- previous snapshot hash 与 canonical next snapshot；
- risk approval/reason、target/product mutual exclusion；
- exact intent/order events/fills/fees/funding/stop/reconciliation；
- all authority counts = 0；
- result self hash。

v0.71 projection 从前一个 OBSERVED v2 result 取 next snapshot 作为下一个 previous snapshot。genesis
只允许冻结的 100 USDT FLAT snapshot。MISSED 保留上一 snapshot，不进行 funding/mark 回填。

terminal mapping 固定为：无合法 source/decision observation 才是 `MISSED`；已经完整
观测 source/decision，但 order/stop/reconciliation 失败时仍是 terminal
`OBSERVED`，同一 v2 result 必须显式携带
`lifecycle_status=FAILED_CLOSED`、单一 reason code 和风险锁。机会覆盖率可以计入该
OBSERVED，但 operational/economic completeness 不得计为成功；未来 evaluator 须把任一
unresolved failed lifecycle/gap 判为 DID_NOT_PASS 或 INCONCLUSIVE，不得用覆盖率掩盖。
若故障后仓位精确可对账，next snapshot 记录 VERIFIED 的实际剩余仓位与
锁定；若有 UNKNOWN/late-fill/reconciliation 歧义，next snapshot 只保留 last
verified position，标记 `position_certainty=UNRESOLVED`并绑定 unresolved intent IDs。

v0.70 evidence v1 只保留 committed regression，不得被 v0.71 normal simulation builder 产生。
compatibility tests 只能在隔离的 v0.70 fixture root 回放 v1，不得将 v1 事件追加或
复制到 v0.71 root。未来 production start contract 必须仅允许它明确冻结的
evidence version。

## 11. Crash/restart 语义

每次处理在内存中先从 event log replay previous snapshot，然后确定性计算 source -> decision ->
simulation result。只有 canonical bytes 全部验证后才 append RESULT/OBSERVED。

```text
before INPUT                    -> zero event; exact retry
after INPUT                     -> replay source bytes; no recapture
after RESULT                    -> replay exact result; zero recompute
after OBSERVED                  -> terminal exact replay
rename-before-dir-fsync         -> event-store durability confirmation
UNKNOWN/partial/reconcile fault -> no risk-increasing continuation
```

v0.71 不新增可配置 fault callback、fault enum CLI、path/command seam。fault tests 使用 mock.patch
私有 write/fsync/publish/aggregate 边界或直接构造严格故障 fixture。

## 12. 可证伪测试矩阵

### 12.1 Source/decision

- 21-bar continuity、OHLC、window、metadata effective interval、hash 和 canonical bytes；
- SMA20/0.5%/lag5 sign 的等号边界、正反例和 Python 3.9/3.12 golden；
- FLAT/SPOT/PERP 全部 action，8h/24h 边界，同机会反手拒绝；
- malformed/ambiguous/caller-injected decision 零 event。

### 12.2 Product/risk

- Spot/PERP 互斥，one-way/isolated/2x hard cap，E0 0.5x actual cap；
- tick/step/min-notional/dust/max quantity 的 exact rounding；
- daily loss 在 1.999.../精确 2/超过 2，drawdown 在 4.999.../精确 5/超过 5；
- 新风险被锁后 reduce-only 仍可执行，但不可反手或增仓。

### 12.3 Lifecycle/fault

- Spot/PERP 各一个 complete open/hold/close cycle；
- fee/slippage/funding/PnL/marked equity 逐字节 golden；
- partial fill、fill-before-ack、duplicate、timeout/UNKNOWN、disconnect/reconcile、late fill、
  overfill、stop missing、ledger mismatch；
- same intent exact retry 零重复经济 fill，different content 冲突；
- fresh interpreter 在 INPUT/RESULT/OBSERVED 每个耐久边界重放。

### 12.4 Safety/static

- patch socket/HTTP/SDK/keyring/path/clock/Broker/order side effects 必须全部为 0；
- public API 无 arbitrary path/time/price/PnL/outcome/scenario/fault callback；
- 无 float、random、SQLite、新 scheduler/deployment/Runner/UI；
- v0.69 plan、v0.70 event store/runtime source bytes 不变；
- final full suite 仅对最终代码状态本地运行一次。

## 13. 文件与规模边界

预计新增：

```text
challenger_replacement_binance_simulation_input.py
challenger_replacement_simulation_contract.py
challenger_replacement_simulation.py
challenger_replacement_opportunity_projection.py
challenger-replacement-binance-simulation-input-v1.schema.json
challenger-replacement-simulation-contract-v1.schema.json
challenger-replacement-opportunity-result-evidence-v2.schema.json
challenger-replacement-binance-golden-fixture-manifest-v1.schema.json
artifacts/challenger-replacement/challenger-replacement-binance-simulation-contract-v0.71.0.json
artifacts/challenger-replacement/challenger-replacement-binance-golden-fixture-manifest-v0.71.0.json
tests/fixtures/challenger_replacement_v071/{spot-cycle,perp-cycle}/*-{input,result}.json
```

simulation contract artifact 是 self-hashed canonical document，绑定 v0.69 plan 和 fee/slippage/
rounding/accounting 合同。golden fixture manifest 列出 simulation contract hash、排序后的
exact fixture paths/SHA-256 和自身 self-hash。它们不反向嵌入未来 commit；
最终 v0.71 release manifest/status/ADR 绑定两个 artifact 的 file SHA、tag、peeled
commit 和 CI。

golden 目录不发明第二套 bundle 格式。每个 `*-input.json` 都由 v0.71
input loader 逐字节重放，每个 `*-result.json` 都由 v2 result loader 逐字节
重放。event bytes 包含 fixture root 的 device/inode，不得作为跨机器 committed
golden；测试必须在当前机器新建的 owner-only root 中从 exact input/result 重建
event chain，比较 exact result bytes 以及投影中不含 root identity/event hash 的明确
业务字段（terminal status、lifecycle status、next snapshot）。禁止通过删除或改写
canonical event 字段制造伪 exact equality。
manifest 只定义排序后的 path/SHA/schema-kind/opportunity-order 清单、contract hash
和 self-hash，不是 runtime authority。fault lifecycle 依然由第 12.3 节的固定
test-only private-boundary patches 验证，不把不可自我描述的故障场景伪装成 portable
committed market fixture。

v0.70 opportunities 模块已有 696 行，v0.71 不在其中堆入执行引擎。
实现前先用行为不变的 TDD regression 将可复用的 envelope/projection 逻辑提取到
`challenger_replacement_opportunity_projection.py`；原模块保持公开门面且行数不增，
v2 dispatch/snapshot projection 只实现在单一投影模块中，不复制第二套 event
state machine。任一新生产模块不得超过 700 physical lines。

新 simulation 净新生产逻辑目标 `<= 1200` physical lines（不把纯移动代码伪计为
删减）。若 TDD 证明需要更大状态机，
必须将 v0.71 拆成可独立审查的语义版本，不用通用引擎抽象突破限额。

## 14. 发布门

1. design spec 与独立设计审查；
2. detailed TDD implementation plan；
3. 每个行为 exact RED -> minimal GREEN -> refactor；
4. focused source/decision/simulation/opportunity/event tests；
5. adjacent v0.69 plan、v0.70 regression、System Paper primitive tests；
6. fault/restart/golden matrix；
7. 最终代码状态本地 full suite 一次、compileall、manifest/release validation；
8. 独立完整 review 一次，Critical/Important 清零；修复后只定向复审；
9. public Draft PR，Python 3.9/3.12 和 macOS arm64 CI；
10. merge main 后 main CI；
11. annotated `v0.71.0` 与 main peeled identity 完全一致。

## 15. 明确非目标

v0.71 不：

- 网络获取 Binance 行情/交易规则/费率；
- 安装、启动、bootstrap/kickstart 任何 service；
- 读取账户、API key、IP allowlist 或资金；
- 提交真实或 testnet order；
- 开始 7-day/90-day 计时；
- 生成 operational/economic final artifact；
- 修改 v0.69 冻结 plan 或删除历史 MISSED；
- 宣称盈利、AI 优势、Paper 完成、E0/Canary 或实盘资格。

## 16. 后续顺序

- v0.72：7-day operational evaluator、independent 90-day economic evaluator、strict observer 与
  v0.61 loopback-only UI 接线；
- v0.73+：natural public-market capture/deployment/start receipt 信任链；
- 只有获得安装/启动显式批准后才开始真实 7 天和 90 天墙钟；
- E0 仍需 API key、IP allowlist、account mode、100 USDT、install/start 和 E0 activation
  的独立不可逆批准。
