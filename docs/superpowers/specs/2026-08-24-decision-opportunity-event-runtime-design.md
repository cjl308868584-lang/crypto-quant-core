# DecisionOpportunity Event Runtime Design

日期：2026-08-24

目标版本：`v0.70.0`

发布基线：annotated `v0.69.0`，peeled commit
`f98f8c49f5c6a2bb28d04ee01d3b1b0ba0348550`

适用分支：`codex/v0.70-decision-opportunity-runtime`

## 1. 决策摘要

v0.70 只实现 replacement v3 的 `DecisionOpportunity` canonical event runtime 和只读健康投影。
它不实现 Binance 模拟执行、生命周期评估器、部署、安装、启动、凭据或真钱 Canary。

权威仍是单一 append-only canonical event log。v0.70 复用 v0.66 已验证的 retained event-root
capability、canonical encoding、no-overwrite publish、fsync、fresh-process replay 和 optimistic parent
hash；不创建第二个数据库或导出事实源。

每个到期机会必须最终成为不可改写的 `OBSERVED` 或 `MISSED`：

```text
INPUT_PREPARED -> RESULT_PREPARED -> OPPORTUNITY_OBSERVED
        |                 |
        +-----------------+-----> OPPORTUNITY_MISSED

无 capture 的过期机会 ----------------> OPPORTUNITY_MISSED
```

`MISSED` 禁止回填或转换为 `OBSERVED`，但不永久终止整个研究流。下一个自然四小时机会可以继续。
这正是 v0.69 preregistration 对旧“漏一槽永久失败”模型的显式替代。

## 2. 权威基础与不可变前序

### 2.1 Release foundation

实现与发布必须精确绑定：

- annotated tag：`v0.69.0`；
- peeled commit：`f98f8c49f5c6a2bb28d04ee01d3b1b0ba0348550`；
- v3 plan：
  `artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json`；
- plan file SHA-256：
  `6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3`；
- plan hash：
  `f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486`；
- plan ID：
  `challenger_replacement_plan_v3_e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f`；
- v0.69 owner attestation：
  `artifacts/challenger-replacement/challenger-replacement-v3-owner-attestation-v0.69.0.json`；
  file SHA-256：
  `b1ec38575b2e4f2b93b9f4838aa04633f382b60aef65843e4812d9b5c799b9c7`；
- v0.69 supersession record：
  `artifacts/challenger-replacement/challenger-replacement-plan-v3-supersession-v0.69.0.json`；
  file SHA-256：
  `1d4932712304a890c5ff0a393d9674c38e2459faa3954a957ac0439ea770a32d`。

loader 必须验证 exact plan bytes、schema、plan ID/hash 和 authority。它不能接受调用方构造的“等价”
dict，也不能从任意路径加载替代 plan。

### 2.2 前序证据保持

v0.64、v0.67、v0.68 和 v0.69 的 artifact、tag、commit 与失败/未启动声明逐字节保留。v0.70 不迁移、
删除、重写或解释旧 v2 events。v2 与 v3 projection 必须通过 plan schema/hash 显式隔离；一个 root
不得混合两种语义。

v3 尚无 start receipt 或 canonical production opportunity event，因此本版本没有 production state
迁移。测试只能使用显式 fixture event-root identity；不得触碰未来 runtime root。

## 3. 范围拆分

v0.69 总路线不减少，只按独立审查边界拆分：

- `v0.70`：DecisionOpportunity event runtime、恢复、只读健康投影；
- `v0.71`：Binance Spot/perpetual deterministic simulation、互斥产品状态、risk、ledger、fill、fee、
  reconciliation 与 restart/fault evidence；
- `v0.72`：7-day operational evaluator、independent 90-day economic evaluator、observer 与现有 v0.61
  loopback-only UI 接线；
- `v0.73+`：deployment/install/start receipt、credential boundary 和 Canary activation trust chain。

若某一后续范围仍过大，必须再以书面 spec 拆分，不能把遗漏包装成 v0.70 已完成。

## 4. 数据模型

### 4.1 Event envelope

storage envelope 继续使用 `challenger_replacement_event_v1`，以保留已验证的 byte encoding 和磁盘
协议。其通用字段 `slot_id` 在 v3 中必须逐字等于 `opportunity_id`。这是 storage compatibility，
公共 v3 API、错误码、投影和文档不得继续宣称旧 slot 语义。

`opportunity_id` 的唯一编码为：

```text
ETHUSDT@YYYY-MM-DDTHH:MM:SS.000Z
```

其中时间必须位于 UTC 四小时网格。ID 由严格的 `scheduled_for` 派生，不能由 CLI 或调用者独立传入。

### 4.2 Opportunity schedule

固定网格为 UTC `00:00/04:00/08:00/12:00/16:00/20:00`：

```text
capture_open  = scheduled_for + 120 seconds
capture_close = scheduled_for + 600 seconds
```

v0.70 的纯 catch-up 函数必须同时接收：

- 由 fixture 或未来 start receipt loader 提供的 `start_scheduled_for`；
- 严格 UTC `detected_at`；
- canonical projection 的最后 terminal opportunity。

函数只派生确定性 due opportunities，按 scheduled time 升序返回。它不能读取系统当前时间来替代参数，
不能把 install/tag/commit time 当作 start，也不能在没有 start boundary 时创造第一个机会。正式 production
start boundary 由后续版本的 start receipt 提供；v0.70 只有 fixture authority。

### 4.3 Canonical event types

v3 event type 只允许：

```text
INPUT_PREPARED
RESULT_PREPARED
OPPORTUNITY_OBSERVED
OPPORTUNITY_MISSED
```

`SLOT_SUCCEEDED`、`SLOT_FAILED_PERMANENT` 或其他 v2 terminal event 在 v3 root 中均固定为
`CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID`。

### 4.4 INPUT_PREPARED

payload exact keys：

```text
opportunity_id
scheduled_for
capture_open
capture_close
capture_sha256
source_bundle_bytes_base64
source_bundle_sha256
```

source bundle 必须由严格 v3 loader 重放，绑定同一 opportunity、plan/build identity、前一已观察
decision state，并证明 captured_at 位于 capture window。`MISSED` 不会伪造 source bundle。

### 4.5 RESULT_PREPARED

payload exact keys：

```text
opportunity_id
scheduled_for
input_event_hash
input_event_sequence
source_bundle_sha256
decision_bytes_base64
decision_sha256
result_evidence_bytes_base64
result_evidence_sha256
previous_observed_decision_hash_or_null
```

`result_evidence` 使用版本化 strict JSON interface：

```text
$schema = ./challenger-replacement-opportunity-result-evidence-v1.schema.json
schema_version = 1.0.0
mode = FIXTURE_ONLY_NO_BROKER_NO_ORDER
opportunity_id
scheduled_for
decision_sha256
authority = {
  network_requests: 0,
  broker_requests: 0,
  orders: 0,
  credentials_used: false,
  production_state_writes: 0
}
```

v0.70 builder 仅为 tests/fixture 创建这种 proof-of-contract evidence；它不是模拟成交、风险批准、订单、
fill、fee、position 或 PnL。v0.71 必须以新的 schema supersede 它后，真实 simulation runner 才有资格
产生 `OBSERVED`。v0.70 不提供自然 runner，也不对 production opportunity 调用该 fixture builder。

### 4.6 OPPORTUNITY_OBSERVED

payload exact keys：

```text
opportunity_id
scheduled_for
input_event_hash
input_event_sequence
result_event_hash
result_event_sequence
source_bundle_sha256
decision_sha256
result_evidence_sha256
observed_at
```

`observed_at` 必须等于严格 capture/result evidence 所绑定的实际观察时间并位于 capture window。所有 hash
必须与前两阶段 exact 相等。只有 `RESULT_PREPARED` 可以进入 OBSERVED。

### 4.7 OPPORTUNITY_MISSED

payload exact keys：

```text
opportunity_id
scheduled_for
detected_at
missed_after_event_hash_or_null
missed_after_stage_or_null
reason_code
```

reason 必须来自 v3 plan allowlist。`detected_at` 必须严格晚于 `capture_close`。没有 durable stage 时两个
`missed_after_*` 均为 null；从 INPUT 或 RESULT 终结时，它们必须精确绑定当前 stage 与 parent hash。

过期 catch-up 路径在 append MISSED 前后必须保持：

```text
market/network calls = 0
decision builds = 0
simulation builds = 0
broker calls = 0
orders = 0
artifact exports = 0
```

任何 caller 提供的历史 price、decision、PnL、outcome 或替代 source 都被拒绝。

## 5. Projection 不变量

### 5.1 单 active opportunity

最多一个非 terminal opportunity。新 INPUT 只允许在没有 active opportunity 且所有更早 due opportunity
均 terminal 后追加。直接 MISSED 可以终结下一个确定 due opportunity而无需创建 active state。

### 5.2 Terminal immutability

每个 opportunity 恰好一个 terminal outcome。exact event retry 返回 `ALREADY_COMMITTED`；同一
opportunity 的不同 bytes、不同 reason 或 OBSERVED/MISSED 冲突固定失败。terminal 后任何 event 无效。

### 5.3 Parent state

只有 OBSERVED 更新 `previous_observed_source_bundle` 和 `previous_observed_decision`。MISSED 永远不制造
decision，也不清除最近 OBSERVED parent。下一个 OBSERVED 的 strategy parent 因而跨过任意数量 MISSED，
同时 projection 仍保存全部 missed facts。

### 5.4 Public projection

只读公共 projection 固定包含：

```text
events
opportunities
active_opportunity_id
first_scheduled_for
last_terminal_scheduled_for
next_required_opportunity
due_opportunity_count
terminal_opportunity_count
observed_opportunity_count
missed_opportunity_count
observed_coverage_decimal
current_consecutive_missed
maximum_consecutive_missed
missed_reason_counts
maximum_detection_delay_seconds
last_event_hash
next_sequence
orphan_staging_count
orphan_staging_bytes
```

coverage 使用 `Decimal(observed) / Decimal(due)`，canonical text 禁止 binary float。没有 due opportunity 时
coverage 为 null。`due` 来自显式 start boundary 与 observation boundary，不能仅以日志中已有 event 数量代替。

投影不得包含单笔或累计 PnL、收益率、胜率、排名、置信区间、功效或提前 PASS。

## 6. Catch-up 与恢复

### 6.1 启动顺序

每次调用必须：

1. retained capability replay 全部 canonical events；
2. 验证 plan/build/root identity 和 projection；
3. 从显式 start/detected boundary 派生 due opportunities；
4. 对每个已过 capture close 且没有 terminal 的机会按时间顺序 append MISSED；
5. replay/rebase；
6. 仅返回当前仍在 window 的唯一 eligible opportunity；
7. v0.70 不自动 capture、build decision 或产生 OBSERVED。

不同 worker 竞争同一 parent hash时只有一个 winner。loser 固定返回 sequence conflict，并由上层重新 replay；
状态层不得暗中重试、改 reason 或跳过机会。

### 6.2 Crash points

沿用 event publisher 已冻结的 staging、same-fd readback、file fsync、atomic no-replace、directory fsync
协议。fresh process 必须正确处理：

- append 前崩溃：无 event，重新派生；
- staging write/fsync 前后崩溃：orphan staging 非 authority；
- rename 后 dir fsync 前崩溃：retry/replay 补 durability confirmation；
- INPUT 或 RESULT 后崩溃：replay 后可继续同一机会或在 window 过期后终结为 MISSED；
- terminal 后崩溃：exact terminal replay，不重新计算 decision/result。

fsync、close、root identity、symlink/hardlink/FIFO/special object、size 或 attachment failure 均失败关闭，
不得 chmod 修复不可信对象。

## 7. Read-only eligibility projection

v0.70 只提供健康/准备度，不发布 operational 或 economic final artifact：

```text
NOT_STARTED_NO_START_BOUNDARY
PRE_TAIL_ELIGIBILITY_ONLY
BLOCKED_LIFECYCLE_EVIDENCE_NOT_IMPLEMENTED
```

即使 observed coverage 达到 95%，v0.70 仍必须是
`BLOCKED_LIFECYCLE_EVIDENCE_NOT_IMPLEMENTED`，因为 Spot/perpetual roundtrip、risk、ledger、fill、fee、
reconciliation 和 strategy cycle 尚未由 v0.71 实现。不得把 coverage health 称为 operational PASS。

90-day economic evaluator、7-day operational evaluator、start receipt 和 lifecycle projection 属于 v0.72+
的冻结合同。本版本不生成 evaluator result，不开始任何墙钟。

## 8. API 与模块边界

推荐新增：

```text
src/crypto_quant/challenger_replacement_opportunities.py
schemas/challenger-replacement-opportunity-result-evidence-v1.schema.json
tests/test_challenger_replacement_opportunities.py
tests/test_challenger_replacement_opportunity_runtime.py
```

现有 `challenger_replacement_events.py` 只做必要的通用 storage 修复；不得复制其 OS primitives。
现有 v2 `challenger_replacement_runtime.py` 保持 v2 replay compatibility，不把 v3 分支堆进同一大函数。
v3 module 可以复用 frozen event API，但必须拥有严格 v3 plan/build loaders 和 projection。

禁止新增 scheduler、deployment、LaunchAgent、Runner、Broker、exchange adapter、generic order lifecycle、
generic UI、REST write endpoint、第三方 runtime dependency 或 production injection seam。

## 9. 可证伪测试矩阵

### 9.1 Identity 与 codec

- exact v0.69 plan/build 接受；wrong file/hash/ID/schema/authority 拒绝；
- opportunity ID 与 UTC 4h grid 双向验证；非 UTC、非毫秒 canonical、off-grid、bool/int 混淆拒绝；
- payload exact keys、duplicate JSON keys、float/NaN、hash/base64/size 不符拒绝；
- `slot_id != opportunity_id` 拒绝；v2 terminal type 在 v3 projection 拒绝。

### 9.2 State machine

- genesis INPUT→RESULT→OBSERVED；
- direct MISSED；INPUT→MISSED；RESULT→MISSED；
- MISSED 后下一个机会 OBSERVED；连续多个 MISSED 后恢复；
- OBSERVED parent decision 跨 MISSED 正确延续；
- terminal 后追加、双 outcome、不同 missed reason、跳 stage、交错 active opportunity 拒绝；
- exact retry idempotent，stale optimistic token 冲突；
- terminal counts、reason distribution、consecutive misses 和 detection delay 精确。

### 9.3 No-backfill

- 多个过期机会按序只生成 MISSED；
- 过期路径最低边界 patch 证明 source/decision/simulation/network/Broker/order/export 调用全部为零；
- caller 注入 scheduled_for/opportunity_id/outcome/price/PnL 被拒绝；
- 当前合法 window 只返回 eligible，不在 v0.70 自动生成 OBSERVED；
- 没有 start boundary 返回 `NOT_STARTED_NO_START_BOUNDARY` 且零写。

### 9.4 Durability 与 concurrency

- 每个 crash point fresh process replay；
- same/different opportunity 的真实双进程竞争；
- rename 后 dir-fsync 前 retry/replay durability confirmation；
- symlink/hardlink/FIFO/socket/directory/wrong owner/mode/nlink/size 全部 read-before-reject 且不阻塞；
- sentinel bytes/mode/size/mtime/ctime/inode/nlink 不变；
- 每个成功 open fd close 尝试恰好一次，主异常不被 close failure 覆盖。

### 9.5 Projection arithmetic

- 0 due coverage=null；1/1、19/20、18/20、large integer 使用 Decimal exact；
- due opportunity gap、重复 scheduled time、out-of-order terminal 拒绝；
- current/max consecutive missed 在 OBSERVED 边界正确重置；
- no PnL/profit/return/win-rate/rank/power 字段静态门。

### 9.6 Isolation

- v2 fixture root 仍由 v2 loader 重放；v3 loader 拒绝 v2；
- v0.64/v0.69 artifacts hash 不变；
- 无 production root/plist/service/network/credential/order side effect；
- Linux Python 3.9/3.12 与 target macOS arm64 flags/primitive tests 均执行。

## 10. YAGNI 与规模门

v0.70 的价值是事实可信、漏机会恢复和失败关闭，不是通用交易平台。实现应优先组合现有 event publisher
和 canonical helpers。新增 production module 目标不超过 700 行；若超过，必须先删除重复 codec/projection
逻辑或重新拆分设计，不能用后续清理承诺越线。

任何为了未来 Binance、订单、UI 或 deployment 而尚未被 v0.70 测试消费的 abstraction 必须删除。

## 11. 发布门

严格顺序：

1. spec 独立审查；
2. detailed TDD implementation plan；
3. 每个行为先精确 RED，再最小 GREEN；
4. focused events/opportunity/runtime/plan tests；
5. adjacent evidence/decision/live-input tests；
6. 最终代码状态本地 full suite 一次、compileall、manifest/release validation；
7. 独立完整 review 一次，Critical/Important 清零；修复后只做 targeted rereview；
8. public Draft PR，Python 3.9/3.12 和 macOS arm64 CI；
9. merge main 后 main CI；
10. annotated `v0.70.0` tag 与 main peeled identity 完全一致。

同一 unchanged commit 不机械重复 full suite。CI 失败必须按根因修复，不能以仓库公开或额度恢复为由降低门槛。

## 12. Authority 与非声明

v0.70 全程必须保持：

```text
production_activation = false
runtime_install_authorized = false
replacement_start_authorized = false
credentials_allowed = false
account_requests_allowed = false
broker_requests_allowed = false
real_orders_allowed = false
```

发布 v0.70 只证明代码与 fixture evidence 满足冻结 event/recovery 合同。它不证明 Paper 已开始、7 天运行
资格、90 天经济证据、盈利、AI 优势、Canary 资格或实盘安全。任何未来安装、启动、凭据、资金或真钱
动作仍需要对应版本的 exact activation contract 和单独权限门。
