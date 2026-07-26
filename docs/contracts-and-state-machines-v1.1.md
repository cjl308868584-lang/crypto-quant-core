# 核心数据契约与订单状态机 v1.1

状态：设计基线
日期：2026-07-26
上位文档：[系统计划 v1.1](system-plan-v1.1.md)
发布证据：[发布评估与证据规范 v1.1](release-evaluation-spec-v1.1.md)

## 1. 目的

本文件定义研究、回测、Paper 和 Live 必须共同遵守的业务语言。实现可以替换，契约语义不得因运行模式变化。

唯一合法链路：

```text
MarketSnapshot
  → StrategyProposal
  → MetaDecision
  → TargetPosition
  → RiskDecision
  → ExecutionIntent
  → PositionExecutor / OrderEvent / Fill
  → ReconciliationResult
```

任何外部订单都必须能沿该链路追溯。研究代码、模型、Prompt、Dashboard 和人工脚本均不得绕过链路直接产生正式订单。

## 2. 通用事件信封

所有事实、命令和决策对象都必须包含：

| 字段 | 类型/约束 | 含义 |
|---|---|---|
| `schema_version` | String，必填 | 契约版本 |
| `event_id` | UUID/ULID，唯一 | 当前事件唯一标识 |
| `trace_id` | String | 一次4H决策到最终成交的完整链路 |
| `correlation_id` | String | 关联同一业务事务 |
| `causation_id` | String/Null | 直接导致当前事件的上游事件 |
| `run_id` | String | Backtest/Paper/Live运行实例 |
| `event_time` | UTC毫秒 | 市场或交易所事件实际发生时间 |
| `available_at` | UTC毫秒 | 系统最早可以合法使用该信息的时间 |
| `ingested_at` | UTC毫秒 | 原始信息到达本系统边界的时间 |
| `recorded_at` | UTC毫秒 | 本系统写入账本的时间 |
| `source` | Enum/String | Binance REST/WS、Replay、Model等 |
| `payload_hash` | SHA-256等 | 规范化Payload内容哈希 |
| `event_hash` | SHA-256等 | 信封与Payload的完整审计哈希 |

统一约束：

- 内部时间统一使用 UTC；展示层可以转为 Asia/Shanghai。
- 特征只能读取 `available_at <= decision_time` 的数据。
- `event_time` 不能代替 `available_at`。
- 价格、数量、金额、手续费和 PnL 在交易与账本边界使用 Decimal 或整数 tick/step。
- ML 特征可以使用 float64，但不能用二进制 float 记账。
- 修改历史事实必须追加补偿事件，禁止覆盖原事件。
- 相同 Payload 的规范化与哈希算法必须版本化。
- `event_time <= available_at <= ingested_at <= recorded_at` 为默认顺序；交易所延迟修订等例外必须携带明确原因码。

确定性规范：

- 业务对象哈希只覆盖规范化业务Payload，不包含随机 `event_id`、`run_id`、墙钟 `recorded_at`；
- 稳定的Decision/Target/Intent ID由业务键和schema版本确定性派生；
- `event_hash`用于审计完整事件，不要求不同运行实例相同；
- JSON使用固定键顺序、UTF-8、Decimal规范字符串和统一空值表示；
- NaN、Inf和负零不得进入正式Payload；
- 模型浮点输出先按ModelBundle声明的精度量化，再计算业务哈希；
- 重放测试使用逻辑时钟。所谓“运行100次哈希一致”指业务对象哈希一致，不要求事件信封哈希一致。

## 3. 标的与交易所元数据

### 3.1 InstrumentId

```text
exchange
account_id
market_type        SPOT | USDT_PERP
symbol
base_asset
quote_asset
settlement_asset
```

### 3.2 InstrumentMetadata

至少包含：

- `instrument_id`
- `effective_from/effective_to`
- `price_tick`
- `quantity_step`
- `min_quantity`
- `max_quantity`
- `min_notional`
- `contract_multiplier`
- `supported_order_types`
- `supported_time_in_force`
- `supports_reduce_only`
- `supports_stop_market`
- `maker_fee/taker_fee`
- `metadata_source`
- `metadata_hash`

下单必须使用决策当时有效的元数据。若交易所规格发生变化，旧元数据继续保留以保证历史重放。

任何价格和数量都向“风险更小”的方向取整。若最小名义金额要求只能通过放大风险才能满足，输出 `NO_TRADE_BELOW_MIN_NOTIONAL`。

V1 的经济方向与交易载体固定映射：

- LONG：ETH/USDT现货；
- SHORT：ETHUSDT逐仓永续；
- Perpetual LONG和动态Funding择场只做Shadow研究；
- 两个交易载体合并计算ETH净经济敞口，不得用名义上的“对冲”绕过1x和仓位限制。

产品能力与数据矩阵：

| 项目 | SPOT LONG | USDT_PERP SHORT |
|---|---|---|
| 账户约束 | 无借币、无保证金 | 单向、逐仓、杠杆≤1x |
| 交易必需行情 | Spot OHLCV/BBO/Trades | Perp OHLCV/BBO/Trades、Mark/Index |
| 上下文行情 | Perp Mark/Index/Premium/Funding/OI/Taker | Premium/Funding/OI/Taker |
| Funding结算 | 不适用，只作上下文 | 必须入账 |
| 风险缩减订单 | 保护性Sell | reduce-only Buy |
| 灾难保护 | 原生保护性卖出止损；必要时Watchdog市价退出 | 原生reduce-only stop-market/等价保护 |

`DataQualityPolicy`按产品声明必填、上下文和不适用字段；上下文字段缺失是否阻止新增风险由策略版本明确决定。

### 3.3 ProtectiveOrder

```text
protective_order_id
instrument_id
position_id
risk_decision_id
execution_intent_id
attempt_id
local_order_id
role                    DISASTER_STOP | STRATEGY_STOP
side
trigger_price
limit_price_or_null
covered_quantity
reduce_only_or_spot_sell
venue_order_id
replacement_of
unprotected_window_started_at_or_null
replacement_deadline_at_or_null
effective_at
status
risk_policy_id
risk_policy_hash
policy_version
```

ProtectiveOrder是普通风险批准链路中的保护角色，必须能沿 `Target → RiskDecision → ExecutionIntent → ChildOrderAttempt → OrderEvent` 追溯，并覆盖交易所实际仓位而非本地期望仓位。

替换规则按产品能力执行：

- 支持原子amend/cancel-replace时，优先使用交易所原子能力；
- 允许同时保留两张保护单且不会锁定/超卖数量时，先确认新保护有效再撤旧保护；
- 现货数量被旧Sell锁定、无法先挂新单时，先激活 `PROTECTIVE_REPLACE` 风险锁并禁止新增风险，再撤旧、立即提交新保护；
- 非原子替换的无保护计时起点是“旧保护撤单得到最终确认”与“首个能够证明实际仓位已经失去足额保护的风险敞口事件”两者中更早者；Cancel请求超时、ACK缺失或 `UNKNOWN` 不算已经撤单，必须查询并对账，但若交易所快照已证明保护缺失，则由该风险敞口事件立即开始计时；
- `RiskPolicy`必须冻结 `risk_thresholds.protective_order_replacement.maximum_unprotected_window_ms`。V1设计默认值为 `2000 ms`，但任何真钱部署都必须读取当前冻结RiskPolicy中的值，缺失时Fail-Closed；`replacement_deadline_at = unprotected_window_started_at + maximum_unprotected_window_ms`，开始时间和deadline必须先持久化并可在重启后恢复；
- 到达 `replacement_deadline_at` 时新保护仍未最终确认有效，系统必须保持 `FREEZE_INCREASES`，并经正常 `Target → Risk → Intent → Attempt → OrderEvent` 链路立即提交紧急市价或venue允许的保护性退出；若该退出提交失败、按冻结的通用请求超时进入 `UNKNOWN` 或对账仍无法确认退出，则立即升级为目标 `FLATTEN` 与持久 `HALT`，继续查询原请求且禁止换新ID盲目重发或自动恢复；
- 任一无保护窗口、覆盖数量不足或替换UNKNOWN都保持风险锁并告警，不能假装换单成功。

## 4. MarketSnapshot

每个正式4H决策只消费一个不可变快照。

关键字段：

```text
snapshot_id
instrument_id
decision_time
bar_open_time
bar_close_time
ohlcv_refs
mark_price
index_price
premium_index
funding_rate
next_funding_time
open_interest
taker_metrics
btc_context_ref
instrument_metadata_version
input_event_ids
data_watermark
data_freshness
missing_fields
quality_flags
snapshot_hash
```

上述字段按产品矩阵解释：Spot快照中的Mark/Index/Funding/OI来自永续上下文并带 `CONTEXT_ONLY`，不是Spot订单字段。

不变量：

1. 4H K线未闭合时不得生成正式快照。
2. 相同 `instrument + decision_time + snapshot_schema` 的正式快照内容必须唯一。
3. 修订数据只能生成新版本和补偿记录，不能静默覆盖。
4. 任何关键字段缺失、过期或来源不明时，快照只能用于观察，不能用于新增风险。

## 5. FeatureSnapshot

训练、回测和实时推理共用同一份特征实现。

关键字段：

```text
feature_snapshot_id
market_snapshot_id
feature_schema_version
feature_schema_hash
feature_code_commit
ordered_feature_names
feature_values
missing_mask
normalization_state_ref
data_cutoff
input_hash
feature_vector_hash
```

约束：

- 特征顺序属于模型契约，不能依赖字典偶然顺序。
- 任一特征名称、类型、含义或窗口变化都必须生成新 schema。
- 离线前缀重算与实时快照必须逐字段一致；数值型容差由特征schema显式声明。
- 禁止在实时路径中用训练时没有的隐式填充、缩放或类型转换。

## 6. StrategyProposal

规则策略负责提出方向；Meta模型不能凭空创造规则策略没有提出的方向。

关键字段：

```text
proposal_id
market_snapshot_id
feature_snapshot_id
strategy_id
strategy_version
strategy_role          BASE | CHALLENGER | SHADOW
direction              FLAT | LONG | SHORT
raw_strength
reason_codes
expected_horizon_hours = 24
minimum_hold_hours     = 8
valid_until
created_at
proposal_hash
```

约束：

- 多头和空头 Proposal 使用独立的研究与晋级记录。
- 同一 `strategy + instrument + decision_time` 的正式 Proposal 必须幂等。
- Shadow 策略只能写预测与虚拟目标，不得进入正式风险/执行链路。

## 7. MetaDecision

V1 的 AI 只回答“是否值得做、风险档位最多多大”，不改变基础方向。

关键字段：

```text
meta_decision_id
proposal_id
decision_source          NO_AI_BASE | MODEL
model_id_or_null
model_version_or_null
deployment_stage
calibration_version_or_null
p_net_positive_or_null
expected_net_return_or_null
return_q10_or_null
return_q50_or_null
return_q90_or_null
uncertainty_score_or_null
ood_score_or_null
eligible
ineligibility_reason_mask
recommended_action       NO_DECISION | HOLD_CURRENT | FREEZE_INCREASES | REDUCE_TO | SET_TARGET | FLATTEN
recommended_bucket_or_null
model_input_hash
prediction_hash
```

资格拒绝原因至少包括：

```text
STALE_MODEL
MISSING_FEATURE
DATA_STALE
OUT_OF_DISTRIBUTION
MODEL_DISAGREEMENT
CALIBRATION_FAILED
UNCERTAINTY_TOO_HIGH
FEATURE_SCHEMA_MISMATCH
MODEL_BUNDLE_INVALID
RISK_LOCKED
```

约束：

- `NO_AI_BASE`必须引用独立批准的确定性基线版本；模型字段显式为Null，不能省略整条MetaDecision。
- 模型/数据失效默认输出 `FREEZE_INCREASES` 且bucket为Null，不是用bucket=0暗示平仓。
- `SET_TARGET/REDUCE_TO` 的bucket只能是25/50/75/100；`FLATTEN`明确使用bucket=0；其他无数值目标的动作使用Null。
- 只有硬风险策略可以将动作升级为 `FLATTEN`。
- 原始概率不能直接线性映射仓位。
- 概率、分位数和不确定性必须来自已登记的不可变模型包。
- Shadow/Retired模型输出不得进入正式 TargetPosition。

## 8. TargetPosition

`TargetPosition` 是决策系统与确定性风险/执行系统之间唯一的经济仓位契约。

关键字段：

```text
target_id
target_sequence
supersedes_target_id_or_null
instrument_id
account_id
target_action            NO_DECISION | HOLD_CURRENT | FREEZE_INCREASES | REDUCE_TO | SET_TARGET | FLATTEN
direction                FLAT | LONG | SHORT
signed_target_ratio_or_null
risk_bucket_or_null
base_volatility_exposure
target_notional_usdt_or_null
volatility_target
volatility_estimator_version
decision_time
valid_until
minimum_hold_until
hysteresis_state
source_proposal_id
source_meta_decision_id
position_policy_version
target_hash
```

约束：

- 对 `SET_TARGET/REDUCE_TO`，`signed_target_ratio = sign × base_volatility_exposure × risk_bucket/100`；它是模型/基线建议，不包含Canary硬上限。
- `FLATTEN`必须明确携带ratio=0、bucket=0和notional=0；`NO_DECISION/HOLD_CURRENT/FREEZE_INCREASES`的三个数值目标字段必须为Null，不能用零暗示动作。
- `base_volatility_exposure = min(1, 12% / max(estimated_annual_vol, 12%))`；波动估计器必须版本化并在审计前冻结。
- `signed_target_ratio` 的绝对值由1x杠杆和账户可用权益进一步限制。
- Spot 不得为 SHORT。
- 方向反转不能通过一个反向大单完成：必须先 reduce-only 平旧仓、确认实际仓位为零，再产生新方向意图。
- 交易所最小名义金额不足时不得向上放大风险。
- Target过期后不得创建新的开仓订单；现有仓位由风险与退出政策管理。

动作语义：

- `NO_DECISION`：当前时点没有新经济意见，不改变已有目标；
- `HOLD_CURRENT`：维持当前交易所实际敞口；
- `FREEZE_INCREASES`：不能增加绝对风险，允许确定性退出规则减仓；
- `REDUCE_TO`：只允许降至指定上限；
- `SET_TARGET`：在全部风险门允许时向目标调整；
- `FLATTEN`：明确将经济敞口降至零。

同一账户和经济标的的 `target_sequence` 必须单调。新Target通过 `supersedes_target_id` 显式替代旧Target。

### 8.1 DeploymentRegistryRecord

RiskGate只读取经过审批的不可变部署记录：

```text
deployment_line_id
release_route
recipe_release_id
recipe_release_hash
direction
venue
stage
authoritative_stage_multiplier
approved_production_capital_usdt
break_even_capital_lcb_root_usdt
actual_deployable_capital_usdt_at_approval
capital_gate_evidence_hash
active_model_bundle_id_or_no_ai_base_version
approved_fallback_record_id_or_null
effective_from
expires_at
release_gate_policy_hash
required_policy_bundle_hash
approval_evidence_hash
status
```

stage与multiplier固定映射为CANARY_25=0.25、CANARY_50=0.50、CANARY_75=0.75、CHAMPION=1.00。新记录只能沿发布状态机合法迁移；每次切换追加新记录，禁止原地覆盖。Approved Fallback Registry的完整资格规则见《AI研究与模型治理》和《发布评估与证据规范》。

## 9. PortfolioRiskSnapshot、RiskLock 与 RiskDecision

### 9.1 PortfolioRiskSnapshot

RiskGate在每次决策前冻结交易所权威状态：

```text
portfolio_risk_snapshot_id
account_id
exchange_snapshot_time
marked_equity
available_balance
spot_positions
perp_positions
active_orders_max_potential_fill
protective_orders
net_eth_exposure
gross_eth_exposure
worst_case_gross_exposure_usdt
margin_used
effective_leverage
daily_loss
cash_flow_adjusted_high_watermark
current_drawdown
instrument_metadata_versions
snapshot_hash
```

活动订单按“所有风险增加型订单都完全成交后的最坏潜在毛敞口”计入风险。RiskGate不得只根据本地目标推断当前风险。

```text
worst_case_gross_exposure_usdt
  = current_spot_abs_notional
  + current_perp_abs_notional
  + sum(risk_increasing_active_order_max_fill_notional)

effective_leverage
  = worst_case_gross_exposure_usdt / marked_equity
```

无法证明为reduce-only/保护性减仓的活动订单一律按风险增加型计；现货与永续反向仓位不得在毛敞口中净额抵消。

### 9.2 RiskLock

风险锁是持久状态，不是一次性信号。

关键字段：

```text
lock_id
lock_type
scope                    GLOBAL | ACCOUNT | INSTRUMENT | MODEL
activated_at
trigger_value
policy_version
allowed_actions
release_condition
requires_manual_release
released_at
release_reason
```

锁类型至少包括：

```text
STARTUP
DATA_STALE
MODEL_INVALID
ORDER_UNKNOWN
POSITION_MISMATCH
CONNECTIVITY
DAILY_LOSS
DRAWDOWN_10
DRAWDOWN_12
DRAWDOWN_15
DRAWDOWN_20
DISASTER_STOP_MISSING
PROTECTIVE_REPLACE
COMPLIANCE
EXTERNAL_POSITION
MANUAL
```

清仓或模型重新预测不能自动解除风险锁。

### 9.3 RiskDecision

```text
risk_decision_id
input_target_id
portfolio_risk_snapshot_id
action                  HOLD_CURRENT | FREEZE_INCREASES | ALLOW | CLAMP | REDUCE_ONLY | FLATTEN | BLOCK
before_target_ratio_or_null
after_target_ratio
current_actual_ratio
before_notional
after_notional
approved_deployment_stage
authoritative_stage_multiplier
stage_capped_target_ratio
deployment_registry_version
triggered_limits
active_lock_ids
daily_loss
current_drawdown
available_equity
policy_version
reason_codes
risk_decision_hash
```

风险不变量：

1. 输入含数值目标时，`abs(after_target_ratio) <= abs(before_target_ratio)`；无数值目标时按动作与 `current_actual_ratio` 比较。
2. 风控不能将 LONG 直接变成 SHORT，或将 SHORT 直接变成 LONG。
3. 风险锁存在时，旧 Proposal 和旧 Target 不得重新开仓。
4. 10/12/15/20%回撤与2%日损边界使用账户权益的统一标记价格口径。
5. 日损和权益高水位必须扣除充值、提现和内部划转的影响。
6. 现货与永续合并后的ETH经济敞口不得超过批准值。
7. 对 `SET_TARGET/REDUCE_TO`，Canary上限由RiskGate从Deployment Registry读取；`stage_capped_target_ratio = before_target_ratio × authoritative_stage_multiplier`，再与确定性风险、权益和1x上限取更小值。`FLATTEN`保持0，其他无数值目标动作按当前实际敞口解释；Target自报的stage/multiplier字段一律忽略或拒绝。
8. `HOLD_CURRENT`要求输出在步长容差内等于当前实际敞口；`FREEZE_INCREASES/REDUCE_ONLY/BLOCK`要求 `abs(after_target_ratio) <= abs(current_actual_ratio)`，且不得阻止保护性退出。
9. `effective_leverage = worst_case_gross_exposure_usdt / marked_equity <= 1.00`；marked_equity≤0时禁止新增风险。
10. 创建任何真钱新增风险前，RiskGate必须用交易所权威余额重算 `actual_deployable_capital_usdt`；其低于Deployment Registry冻结的 `approved_production_capital_usdt` 或 `break_even_capital_lcb_root_usdt` 时输出 `FREEZE_INCREASES`。高于批准资本时也只能按批准资本定仓，不能自动放大。

日损口径：

```text
daily_loss
  = (current_marked_equity
     - start_of_utc_day_equity
     - net_external_cash_flow)
    / start_of_utc_day_equity
```

达到 `-2%` 时产生 `DAILY_LOSS` 锁，取消新增风险订单，将批准目标降至零并有序退出。最早在下一个UTC自然日完成清洁对账后解除；若与执行、数据或安全事故有关则要求人工解除。

回撤锁是累计且单调的：

- `DRAWDOWN_10`：不得增加相对当前实际风险；
- `DRAWDOWN_12`：继承10%限制，`cap=min(current_abs_exposure, approved_exposure×50%)`；
- `DRAWDOWN_15`：目标为零；
- `DRAWDOWN_20`：目标为零且禁止自动重启。

解除条件：

- 10%锁：回撤低于8%连续7天、数据/订单/对账健康；
- 12%锁：回撤低于10%连续14天并人工批准；
- 15%/20%锁：事故复盘、至少30天Paper和人工批准，最多从CANARY_25恢复。

## 10. ExecutionIntent

执行计划使用交易所当前真实仓位，而不是仅使用本地期望仓位。

关键字段：

```text
intent_id
risk_decision_id
target_id
instrument_id
exchange_position_before
desired_position
delta_quantity
reduce_only
order_policy
max_slippage_bps
deadline
idempotency_key
intent_status
instrument_metadata_version
intent_hash
```

约束：

- 同一经济意图重复处理时必须使用相同幂等键。
- 网络超时前后不得生成新的经济意图。
- 数量、价格和最小名义金额检查必须在提交前再次执行。
- 任何执行计划不得超过 RiskDecision 的批准风险。
- 一个稳定经济Intent可以拥有多个顺序ChildOrderAttempt；部分成交后的合法补单不创建新经济Intent。

### 10.1 ChildOrderAttempt

```text
attempt_id
intent_id
attempt_no
client_order_id
planned_quantity
planned_price_or_market
created_reason          INITIAL | REPRICE | RESIDUAL
supersedes_attempt_id_or_null
```

`client_order_id`由 `intent_id + attempt_no` 确定性派生。只有前一Attempt已被交易所确认终态或其剩余量已被对账解析，才允许创建下一Attempt。

## 11. PositionExecutor 状态机

正常路径：

```text
PLANNED
  → CLOSING_OPPOSITE
  → WAITING_FLAT
  → OPENING_OR_ADJUSTING
  → VERIFYING
  → SATISFIED
```

异常状态：

```text
BLOCKED_UNKNOWN
ABORTED_BY_RISK
EXPIRED
FAILED_PRE_SUBMIT
```

规则：

- 只有交易所确认实际仓位归零，才能从 `WAITING_FLAT` 进入新方向。
- 任一关联订单进入 UNKNOWN 时，Executor进入 `BLOCKED_UNKNOWN`。
- Target过期、风险锁升级或数据失效时，可以停止追单或进入 reduce-only，但不能放大风险。
- Executor的完成条件是交易所实际仓位进入批准目标的数量步长容差，不是“已经发送订单”。
- 每个账户和经济标的最多一个活动PositionExecutor。
- 新Target到达时，Executor先比较 `target_sequence`：忽略旧序列；对新序列取消不再安全的活动子订单、吸收取消前产生的全部Fill，再基于最新PortfolioRiskSnapshot重新规划。
- Target过期时禁止提交新的增加风险Attempt；已离开本地的Attempt进入查询/取消/对账，不能假定失败。

## 12. OrderEvent 与订单状态机

### 12.1 OrderEvent

```text
local_order_id
attempt_id
client_order_id
venue_order_id
instrument_id
previous_state
new_state
side
order_type
time_in_force
reduce_only
requested_quantity
acknowledged_quantity
cumulative_filled_quantity
remaining_quantity
requested_price
average_fill_price
exchange_sequence
exchange_event_time
reject_or_cancel_reason
raw_payload_hash
```

### 12.2 状态

正常路径：

```text
CREATED
  → RISK_APPROVED
  → SUBMITTING
  → ACKNOWLEDGED
  → PARTIALLY_FILLED
  → FILLED
```

取消路径：

```text
ACKNOWLEDGED | PARTIALLY_FILLED
  → CANCEL_PENDING
  → CANCELED
```

其他终态：

```text
RISK_DENIED
REJECTED
EXPIRED
FAILED_PRE_SUBMIT
```

不确定路径：

```text
SUBMITTING | ACKNOWLEDGED | PARTIALLY_FILLED | CANCEL_PENDING
  → UNKNOWN
```

规范化事件转换：

| 当前状态 | 规范化事件 | 新状态/动作 |
|---|---|---|
| CREATED | RISK_PASS | RISK_APPROVED |
| CREATED | RISK_DENY | RISK_DENIED |
| RISK_APPROVED | SUBMIT_STARTED | SUBMITTING |
| RISK_APPROVED | LOCAL_VALIDATION_FAILED | FAILED_PRE_SUBMIT |
| SUBMITTING | ACK | ACKNOWLEDGED |
| SUBMITTING | REJECT | REJECTED |
| SUBMITTING | PARTIAL_FILL | PARTIALLY_FILLED；允许Fill先于ACK |
| SUBMITTING | FULL_FILL | FILLED；允许Fill先于ACK |
| ACKNOWLEDGED | PARTIAL_FILL | PARTIALLY_FILLED |
| ACKNOWLEDGED | FULL_FILL | FILLED |
| ACKNOWLEDGED/PARTIALLY_FILLED | VENUE_EXPIRED | EXPIRED；保留已有累计Fill |
| ACKNOWLEDGED/PARTIALLY_FILLED | VENUE_CANCEL_CONFIRMED | CANCELED；保留已有累计Fill |
| ACKNOWLEDGED/PARTIALLY_FILLED | CANCEL_REQUESTED | CANCEL_PENDING |
| CANCEL_PENDING | PARTIAL_FILL | 累计Fill；保持CANCEL_PENDING并继续取消剩余量 |
| CANCEL_PENDING | FULL_FILL | FILLED；Cancel结果不再改变经济终态 |
| CANCEL_PENDING | CANCEL_CONFIRMED | CANCELED；允许累计成交量>0 |
| 任一可能已外发状态 | TIMEOUT/DISCONNECT/UNPARSEABLE | UNKNOWN |
| UNKNOWN | RECON_ACK | ACKNOWLEDGED |
| UNKNOWN | RECON_PARTIAL_FILL | PARTIALLY_FILLED或CANCEL_PENDING，取决于剩余订单是否仍在撤销 |
| UNKNOWN | RECON_FULL_FILL | FILLED |
| UNKNOWN | RECON_CANCELED | CANCELED |
| UNKNOWN | RECON_REJECTED | REJECTED |
| UNKNOWN | RECON_EXPIRED | EXPIRED |
| UNKNOWN | RECON_UNRESOLVED | 保持UNKNOWN并激活风险锁 |

竞态优先级：

1. Fill是不可撤销的经济事实，优先于ACK、Cancel和迟到终态。
2. `cumulative_filled_quantity`只能单调增加，且不得超过requested quantity。
3. Cancel只作用于未成交剩余量；CANCELED订单可以具有非零累计成交。
4. 迟到或重复终态不得逆转FILLED；冲突时进入对账并保留原始证据。
5. CANCELED后收到时间上早于Cancel生效的迟到Fill，仍追加Fill并修正持仓投影；若累计成交仍小于请求量，终态保持CANCELED；若累计成交达到请求量，经济终态提升为FILLED。

`UNKNOWN` 只能通过以下证据解析：

1. 使用原 `client_order_id` 查询；
2. 查询活动订单和订单历史；
3. 查询成交历史；
4. 对比实际仓位；
5. 生成明确的 ReconciliationResult。

每个UNKNOWN必须记录查询证据和解析原因。长期无法解析没有伪造的“FAILED”终态：保持UNKNOWN、冻结新增风险并等待交易所证据或人工事件。

禁止：

- 将超时直接视为失败；
- 为同一意图换新ID盲目重下；
- 通过删除本地订单掩盖UNKNOWN；
- 只依据WebSocket断开推断订单状态。

部分成交后订单即使最终为 CANCELED，累计成交仍永久有效；剩余差额必须基于交易所实际仓位重新规划。

## 13. Fill 与 AccountingEvent

### 13.1 Fill

```text
fill_id
exchange_trade_id
local_order_id
venue_order_id
instrument_id
side
quantity
price
decision_reference_price
liquidity_role          MAKER | TAKER
fee_amount
fee_asset
fee_value_usdt
fee_fx_rate_id
implementation_shortfall_usdt
exchange_event_time
raw_payload_hash
```

`exchange_trade_id` 在账户和市场范围内必须唯一去重。重复或乱序的REST/WS事件不得改变最终经济结果。

### 13.2 AccountingEvent

独立记录：

- BalanceSnapshot；
- PositionOpened/Changed/Closed；
- FeeCharged；
- FundingPaid/Received；
- RealizedPnl；
- UnrealizedPnlSnapshot；
- EquityHighWatermark；
- DailyLossState；
- ExternalCashFlow：DEPOSIT/WITHDRAWAL/INTERNAL_TRANSFER；
- OperatingCost：INFRASTRUCTURE/DATA/ALERTING；
- AIInferenceCost；
- ModelTrainingCost；
- MonitoringAndAuditCost；
- FxValuation：非USDT费用或成本的估值价格、来源和available_at。

Funding和手续费不得通过修改成交价隐式吞并，必须作为可审计独立事实。约定：

```text
fill_based_gross_pnl
  = side_sign × (exit_fill_price - entry_fill_price)
    × filled_quantity × contract_multiplier

trading_net_pnl
  = fill_based_gross_pnl
  - fee_value_usdt
  + signed_funding_cashflow
```

`signed_funding_cashflow > 0`表示收到，`< 0`表示支付。Spread/Slippage已经体现在Fill中，只作为Implementation Shortfall归因，不重复扣除。

成本分摊：

- AI臂承担其增量数据、推理、例行训练和监控成本；
- NO_AI与AI共享基础设施按同一版本化规则分摊，在配对增量中可以相消；
- 一次性研发时间单独报告为Project ROI，不混入每笔策略边际；
- 所有OperatingCost和ExternalCashFlow事件必须可重放，才能计算cash-flow-adjusted高水位与economic PnL。

### 13.3 AccountingPolicy 与期间收益

每个ReleaseEvaluationContext必须冻结：

```text
accounting_policy_id
cost_allocation_policy_id
reporting_asset                    USDT
cost_basis_method                  MOVING_WEIGHTED_AVERAGE
marking_method                     CONSERVATIVE_EXECUTABLE_CLOSE
approved_production_capital_usdt
evaluation_window_start/end
route
direction
recipe_release_id
```

V1统一规则：

- 同方向加仓按不含手续费的成交价与数量更新移动加权平均入场价；手续费由FeeCharged独立入账。
- 减仓按当时移动加权平均成本确认已实现PnL；一次Fill不得跨零反手，反手必须先确认实际仓位归零。
- 部分成交逐Fill入账，不能把订单平均价当作唯一经济事实。
- Funding按交易所结算事实分配给结算时实际持仓；研究标签使用同一持仓时间轴模拟。
- 非USDT费用先通过对应 `FxValuation` 转为USDT。
- 风险日损/保证金使用交易所Mark；绩效窗口末未平仓LONG按可执行Bid、SHORT按可执行Ask估值，并计提预计退出手续费，禁止用更有利的Mid粉饰结果。
- `approved_production_capital_usdt` 在打开Release Audit前冻结；不同资本、路线、方向或评估窗口不得复用同一GateEvidence。

期间指标从两个独立投影计算，避免重复叠加已实现与未实现PnL：

```text
period_trading_pnl_usdt
  = ending_liquidation_equity
  - starting_liquidation_equity
  - net_external_cash_flow

period_economic_pnl_usdt
  = period_trading_pnl_usdt
  - allocated_infrastructure_data_alerting_cost
  - allocated_ai_inference_cost
  - allocated_model_training_cost
  - allocated_monitoring_and_audit_cost
```

`economic_net_log_growth` 从扣除上述成本后的现金流调整权益路径计算；若权益任一时点≤0，结果直接FAIL，不能计算出虚假有限对数收益。AI与NO_AI使用相同起始资本、Proposal、时间轴和成交模型，各自维护独立虚拟账本；AI增量主指标是两个同单位 `economic_net_log_growth` 的配对差，USDT PnL差只作辅助报告。

## 14. ReconciliationResult

```text
reconciliation_id
trigger                  STARTUP | PERIODIC | RECONNECT | UNKNOWN | MANUAL
watermark_before
exchange_snapshot_hash
local_projection_hash
order_diffs
fill_diffs
position_diffs
balance_diffs
protective_order_diffs
compensation_event_ids
unresolved_items
result                   CLEAN | COMPENSATED | LOCKED
completed_at
```

交易所是余额、订单最终状态和实际仓位的权威来源。本地缺失但能证明属于本系统的订单/成交，通过补偿事件纳入账本；不得修改旧事件。

无法证明属于本系统的手工订单或仓位标记为 `EXTERNAL`：

- 立即锁定新增风险；
- 告警；
- 默认不自动取消或反向操作；
- 等待人工确认或硬风险政策接管。

## 15. 启动与断线恢复

### 15.1 启动

1. 激活 `STARTUP` 全局风险锁。
2. 校验SQLite WAL和事件链完整性。
3. 从账本重放订单、成交、仓位、余额、风险锁和部署模型。
4. 校验代码、配置、模型包和特征schema。
5. 与Binance同步时间并刷新InstrumentMetadata。
6. REST获取余额、实际仓位、活动订单、近期订单和重叠窗口成交。
7. 按client order ID和exchange trade ID合并去重。
8. 解析全部UNKNOWN。
9. 按产品校验：现货无借币、无保证金；永续为单向、逐仓、最大1x。
10. 建立私有WebSocket并检查sequence连续性。
11. 若有持仓，按产品能力矩阵确认ProtectiveOrder存在、方向和覆盖数量正确。
12. 只有无未解释差异、无UNKNOWN、数据和模型均有效时才解除启动锁。

### 15.2 持续对账

- 私有WebSocket：持续消费。
- 有活动订单、UNKNOWN或私有流降级时：至少每60秒REST核验活动订单和仓位。
- 正常状态：至少每5分钟核验仓位、活动订单和近期成交。
- 完整余额与账户核验：至少每15分钟。
- 提交/取消超时、重连、sequence gap和异常成交：立即专项对账。

### 15.3 连接降级

| 状态 | 允许动作 |
|---|---|
| 公共行情过期 | 禁止新增风险 |
| 私有WS断开、REST可用 | 只允许减仓；进入REST核验 |
| REST不可用、WS正常 | 禁止提交新订单 |
| REST和WS均不可用 | 全局锁定；依赖交易所已有灾难止损 |
| 连接恢复 | 完整对账后才可恢复 |

## 16. 追加账本和投影

V1 使用 SQLite WAL：

- `events`：不可变事实；
- `outbox`：待发送但尚未确认的执行命令；
- `orders_projection`；
- `fills_projection`；
- `positions_projection`；
- `balances_projection`；
- `external_cash_flows_projection`；
- `operating_costs_projection`；
- `protective_orders_projection`；
- `risk_locks_projection`；
- `model_deployments_projection`；
- `checkpoints`。

写外部订单前必须先持久化 ExecutionIntent/Outbox。外部副作用完成后追加结果事件并更新投影。崩溃恢复从事实与Outbox开始，而不是依据内存状态。

## 17. 系统不变量

1. 每个外部订单都有完整的 Target→Risk→Intent 链路。
2. 策略和AI没有Broker接口权限。
3. 风控后的绝对敞口不大于输入目标。
4. 同一4H决策不会因重启产生第二个经济订单。
5. 不确定请求必须进入UNKNOWN。
6. 事件可以至少一次到达，经济效果必须恰好一次。
7. 账本只追加；修正使用补偿事件。
8. 相同事件流重放产生相同决策、订单和仓位哈希。
9. 开启交易时，本地和交易所仓位在一个quantity step内一致。
10. Spot不做空；永续为单向、逐仓、最大1x。
11. LONG固定使用现货、SHORT固定使用永续；切换方向必须先消除旧载体敞口。
12. 方向反转必须先平仓并确认归零。
13. 回测、Paper和Live不分叉业务逻辑。
14. 所有特征在决策时点真实可用。
15. 风险锁优先于模型信号。
16. 每个实盘订单能追溯到原始行情、策略、模型和风险版本。
17. `FREEZE_INCREASES`与`FLATTEN`语义不同，任何组件不得用零仓位替代“无新决定”。
18. Canary上限由RiskGate的权威Deployment Registry执行，不能由TargetPosition决定。
19. 每个经济标的最多一个活动Executor；每个Intent的ChildOrderAttempt顺序和ID可确定性恢复。
20. 固定运营成本、AI增量成本和外部现金流均进入追加账本。
21. ProtectiveOrder与普通订单一样具备Target→Risk→Intent→Attempt→OrderEvent谱系。
22. `effective_leverage`使用最坏毛敞口，现货/永续反向仓位和UNKNOWN订单不得净额绕过1x。
23. 所有Gate收益都绑定AccountingPolicy、CostAllocationPolicy、批准资本和评估窗口。

## 18. 契约与故障验收

### 18.1 确定性

- 相同事件重复运行100次，Proposal、MetaDecision、Target、RiskDecision和Intent哈希一致。
- 从零重放完整日志后，所有投影与运行结束时一致。
- 重复、延迟和乱序事件不改变最终经济状态。

### 18.2 故障注入点

每个位置都必须强制杀进程并重启：

- Intent写入前后；
- HTTP发出前后；
- ACK前后；
- 部分成交前后；
- Cancel发出前后；
- WS Fill接收前后；
- 事件写入和投影更新前后。

通过条件：

- 0次重复经济订单；
- 0次丢失成交；
- 0次风险放大；
- 所有不确定请求进入UNKNOWN；
- 重启后能对账到唯一明确状态，或安全锁定。
- 伪造Target中的Canary multiplier不能突破Deployment Registry上限。
- 模型失效产生FREEZE_INCREASES时不得把已有仓位误平；硬风险FLATTEN必须确实降至零。
- 25风险bucket与CANARY_25分别按0.25相乘；百分数整数不能被当作unit ratio。
- 活动风险增加订单全成交后的最坏毛敞口不得超过1x；反向现货/永续不能净额抵消。
- 保护单换单在原子amend、可双挂和现货数量锁定三种能力下均保持可追溯并Fail-Closed。
- 现货换保护单时，Cancel为UNKNOWN不得视为已撤；从最终撤单确认或首个保护缺失事件中更早者计时，并在冻结的 `risk_thresholds.protective_order_replacement.maximum_unprotected_window_ms` 边界触发紧急退出，失败后进入FLATTEN/HALT。

### 18.3 必测对账案例

- 本地有订单、交易所无订单；
- 交易所有订单、本地无订单；
- 部分成交后断线；
- Fill重复、延迟和乱序；
- 手工订单和手工仓位；
- 手续费使用非USDT资产；
- Funding结算；
- 强平/自动减仓事件；
- InstrumentMetadata变化；
- WebSocket sequence gap。
- Fill先于ACK；
- Cancel与Fill同时发生；
- UNKNOWN分别解析为ACK/PARTIAL/FILLED/CANCELED/REJECTED/EXPIRED；
- 新Target覆盖仍有活动Attempt的旧Target；
- 非USDT手续费估值、运营成本和外部现金流重放。
- 多次加减仓和部分成交按MOVING_WEIGHTED_AVERAGE得到唯一PnL；
- 窗口末未平仓按保守可执行平仓价和退出费用估值；
- 相同Fill流在相同Accounting/Cost Policy下得到唯一标签、economic PnL和AI配对增量。

### 18.4 90天Paper系统门槛

- 0次重复经济订单；
- 0次未记录成交；
- 0次硬风险、杠杆、逐仓或单向模式违规；
- 0次对账不一致时继续新增风险；
- 100%订单可追溯；
- 所有断线和重启自动恢复到明确状态，或安全锁定等待人工处理。

上述是“有资格管理真钱”的门槛，不是盈利门槛。
