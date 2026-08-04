# System Paper Fixed-Tail Evaluation Design

日期：2026-08-04
目标版本：`v0.59.0`
基线：annotated `v0.58.0` / `35a810622fc0449f2131ccbb806354b48deac15d`
适用分支：`codex/v0.59-system-paper-evaluation`

## 1. 决策摘要

v0.59 只冻结 System Paper 的90天固定尾部 evaluator、严格 loader、CLI、Schema、
测试和发布记录。本版不渲染生产 contract，不安装或启动 LaunchAgent，
不调用 Runner/scheduler，不请求市场、账户、Broker 或订单，不创建 start receipt。
发布前的残余复审又发现并关闭两个组合状态缺口：用 retained output
directory inode 作唯一 finalization lock domain，以及在 tail 后先判定
prepared state binding、再分类单次 retained inventory，同时保留事件调度与
start receipt 不一致时的硬权威失败。这些关闭不扩大本版的非生产边界。

evaluator 是研究门，不是盈利承诺或实盘授权。最终状态只能是：

- `SYSTEM_PAPER_GATE_PASS`：全部完整性、安全、重放和冻结经济门通过；
- `SYSTEM_PAPER_GATE_DID_NOT_PASS`：证据完整但至少一个预注册门失败；
- `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`：缺槽、失败/过期槽、不连续、来源失配或证据无法完整重放。

在固定尾部前只返回 `SYSTEM_PAPER_EVALUATION_PENDING_BEFORE_TAIL`，且禁止读取或输出
PnL、return、win rate、drawdown、cost、排名、置信区间或提前 PASS。

## 2. 信任边界与唯一输入

CLI 只接受七个绝对路径：

1. `--plan-path`；
2. `--start-receipt-path`；
3. `--install-receipt-path`；
4. `--contract-path`；
5. `--slot-root`；
6. `--runtime-root`；
7. `--output-root`。

禁止手工传入 clock/date/slot/PnL/fee/price/return/label/result id/filename/threshold。
生产 CLI 只使用 OS UTC clock。测试可注入 `_clock`，但该参数不出现在 CLI。

contract 的 strict loader 是根权威。evaluator 从有界、canonical 的 install receipt 预视图
中只派生 target plist 和 preflight receipt 路径，随后必须通过 v0.58 production loaders
完整复核 contract/plist/preflight/install/start。预视图不能单独提供任何权威。

`runtime-root`、`slot-root` 必须分别等于 contract 冻结的 runtime root 与
`root_paths.artifacts/system-paper-slots`。state 只能从
`root_paths.state/system-paper.sqlite` 派生；不接受手工 state 路径。

## 3. 时间门与 tail blindness

`cohort_started_at`、`cohort_tail_end` 和 `expected_slot_count=540` 只能来自 strict start
receipt。时间窗口是半开区间 `[start, tail)`，槽间隔固定4小时。最后一槽的
`scheduled_for = tail - 4h`。由于该槽的自然过期点为 `tail + 5m`，最终评估最早时间门是
`tail + 5m`。

时间门前：

- 只复核 contract/install/start 身份和 scheduler event 类型/连续性；
- 不打开 slot artifact，不调用 slot result loader；
- 返回字段只允许 status、observed_at、cohort_started_at、tail_end、elapsed_days、
  verified_terminal_slot_count、incident_count、next_required_slot 和 evidence_health；
- 不创建 output root 或 evaluation artifact。

时间门后也不允许选择子集、改阈值或重跑寻找更好结果。同一 exact 输入
只有一个稳定 evaluation id 和文件名。

## 4. 只读证据捕获

evaluator 必须同时保留所有固定来源的 no-follow descriptors，并在返回或发布前再次
复核 pathname identity、owner、mode、link count、size、mtime 与 exact bytes。

SQLite main/WAL/SHM 作为一个短暂快照组同时捕获，复制到 owner-only
`/private/tmp` 临时目录，只对副本使用 scheduler replay。禁止直接对 production SQLite
运行会改变 journal mode 或 schema 的打开方式。副本重放后必须再复核所有源
descriptors 未变。

槽位 artifact 依 scheduled time 和冻结 plan hash 自动派生 slot id 与 exact path。
目录 inventory 必须恰好是540个期望文件；symlink、hardlink、unknown file、替换、缺失或
非 owner-only 文件全部失败关闭。

## 5. 完整性与重放门

尾部后必须同时满足：

1. 恰好540个 scheduled slots，严格4小时连续；
2. 每槽恰好一个 `SUCCEEDED`，无 `FAILED/MISSED/EXPIRED`，无 active/nonterminal slot；
3. event chain、prepared input/result、artifact bytes 与 output-root identity 全部匹配；
4. 首槽与 start receipt exact 匹配，后续每槽 parent slot hash 严格连续；
5. 每个 slot 通过 production result loader 与 full deterministic replay；
6. 每个 runtime snapshot 的 processed slot ids 恰好等于当前前缀；
7. 每槽 decision/market/full-slot replay flags 全为 true；
8. 每槽 ledger balanced，reconciliation difference 全为0；
9. credential/account/real-Broker/real-order counters 全为0。

任一缺槽、永久失败槽、不连续或无法重放导致
`INCONCLUSIVE_INSUFFICIENT_EVIDENCE`，不允许回填或用经济表现覆盖。

tail 后的 state-only prepared replay 以 retained event projection 的首槽调度为锚，
并要求 start receipt 的首槽、90天 tail 与固定540槽声明精确一致。这些
schedule authority 失配是硬 `SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID`，
不得因 slot inventory 为 `EMPTY`、`MISSING` 或 `UNSAFE` 而降级为
INCONCLUSIVE。

## 6. 冻结安全与经济门

只有第5节完整证据全部成立时才读取经济字段并计算本节。

### 6.1 安全门

- duplicate order events = 0；
- unrecorded fills = 0；
- hard-risk violations = 0；
- unresolved reconciliation 期间 exposure increase = 0；
- 最终 active order = null，最终 risk state 不是由未解决 UNKNOWN 遗留；
- traceability ratio = 1，full replay ratio = 1。

### 6.2 成本门

每个模拟 fill 从该槽 replay input 的冻结 BBO touch 派生 execution shortfall。单边必须同时满足：

- effective fee rate `<= 0.0015`；
- effective slippage rate `<= 0.001`；
- 累计 modeled execution cost `<= gross filled notional * 0.0025`。

不允许人工输入 price、fee 或 cost。

### 6.3 回撤门

使用 `runtime_snapshot.marked_equity_usdt` 的高水位路径，将初始虚拟权益
`1000 USDT` 作为第一个观测点。最大回撤必须严格 `< 0.10`。

### 6.4 固定成本30天块收益门

90天窗口从 start 自动分为三个不重叠、每个180槽的30天块。每块收益为
`(block_end_marked_equity - block_start_equity) / block_start_equity`，已包含冻结费用与保守成交。

使用三个块的 sample mean 和 sample standard deviation，预注册单侧95% Student-t 下界：

`LCB = mean - 2.91998558035372 * sample_sd / sqrt(3)`。

所有计算使用 Decimal，禁止 binary float。门槛为 LCB 严格 `> 0`。该门只是后续
研究阶段条件，不表示可持续盈利。

## 7. 状态决策

- 尾部前：`SYSTEM_PAPER_EVALUATION_PENDING_BEFORE_TAIL`；
- 尾部后但完整证据不成立：`INCONCLUSIVE_INSUFFICIENT_EVIDENCE`；
- 完整证据成立且任一安全/成本/回撤/收益门失败：`SYSTEM_PAPER_GATE_DID_NOT_PASS`；
- 完整证据成立且全部门通过：`SYSTEM_PAPER_GATE_PASS`。

PASS 也只允许表述为“System Paper 研究门通过，可继续完成 replacement Challenger
与后续研究”。它不自动安装、创建 key、入金、下单或获得 Canary 资格。

## 8. 发布与重放

尾部前 pending 不写文件。尾部后首个有效最终状态（包括 PASS、DID_NOT_PASS 或
INCONCLUSIVE）必须发布到 contract 的 `root_paths.artifacts` 下唯一的
`system-paper-evaluations` 专用目录。调用方传入的 output root 必须与该派生路径完全
一致，且不得与 contract、start receipt、slot 或 state 来源重叠。目录与文件权限
固定为 owner-only `0700/0600`。

终态序列 key 只由 `(contract_hash, start_receipt_hash)` 派生。publisher 必须在专用
root 已保留的 owner-`0700` directory descriptor 上取得 `flock(LOCK_EX)`，并在同一
directory-inode critical section 中串行严格扫描、决策、发布和发布后扫描。
不创建、打开或忽略任何 child lock pathname；替换旧 lock 文件名不能分裂锁域，
且专用 root 中任何非 result 条目都失败关闭。首个终态包括 INCONCLUSIVE
永久封存该序列。同一 key 只有完全相同的 canonical bytes 才能幂等返回，
其他候选均为不可覆盖的 terminal conflict。文件名由 contract hash、start
receipt hash、`state_binding_hash` 和 exact slot inventory hash 派生。

production loader 必须要求传入路径等于 artifact 声明的 output root 下的 exact
`result_id.json`，保留该 owner-`0700` root descriptor，通过 dirfd no-follow 相对打开
文件，并在原始输入全量重算后再次验证 root/file attachment。loader 不得创建
root、lock 或结果文件。

## 9. Schema 与测试要求

Schema 两份镜像必须 byte-identical，`additionalProperties=false`，禁止 float/NaN/Infinity。
结果必须包含完整来源 hash、证据 inventory、每个门的 value/threshold/passed 和零权限计数。
尾部后只允许一次 authority/state/inventory 快照，错误路径不得重新捕获。state 绑定
为严格 union：可重放状态使用 `EVENT_CHAIN_END`；字节稳定但语义/event/prepared
不可重放的 SQLite main/WAL/SHM 组使用 `RAW_SQLITE_GROUP`并发布可加载的
INCONCLUSIVE。捕获后发生 identity 或字节变化始终硬失败；PASS 和 DID_NOT_PASS
只允许 `EVENT_CHAIN_END`。

必须覆盖：

- 尾部前禁止经济 loader 与零写；
- 540槽完整成功、缺槽、失败槽、重复槽、额外文件和 active slot；
- event/prepared/artifact/parent/runtime snapshot 协调篡改；
- 来源在捕获期间被同字节不同 inode 替换；
- safety/cost/drawdown/30-day LCB 每个门的通过和失败；
- PASS/DID_NOT_PASS/INCONCLUSIVE 全部如实保留；
- 首个终态串行、并发候选、专用 root 及来源重叠零写；
- 单次快照 race、raw SQLite state 绑定和捕获后变化硬失败；
- CLI 只有七个路径，无人工选择器；
- exact 发布、冲突、loader 全量重放、Schema mirror 和 build manifest。

tail 后事件重放成功后，evaluator 必须先从 retained SQLite descriptors 严格
重放 prepared input/result，再仅捕获一次 slot inventory。稳定 prepared 损坏选择
`RAW_SQLITE_GROUP` 绑定的 `PREPARED_REPLAY_INVALID`，并如实记录同一次
inventory 状态；只有 prepared state 可重放时，不完整 inventory 才选择
event-chain-bound `COHORT_INCOMPLETE`。tail 前仍禁止 prepared replay 与 inventory
捕获。

## 10. 明确非目标

- 不启动90天计时；
- 不实现 tail-blind operations projection、Web、alerts 或 runbooks（分别属于 v0.60/v0.61）；
- 不实现 replacement Challenger；
- 不更改 System Paper plan、runtime、scheduler、deployment 或证据 roots；
- 不声称盈利、AI edge、Paper completion、Canary 或实盘资格。

## 11. 审查自检

- 时间、槽位、价格、费用、阈值和 result id 均无手工输入；
- tail blindness 在读文件边界强制，不只是输出字段删除；
- 完整性失败与经济门失败分离为 INCONCLUSIVE 与 DID_NOT_PASS；
- 三个30天块和 Student-t 常数已预注册；
- 所有 production 来源只读，临时写入仅限 `/private/tmp` 副本和最终 owner-only artifact；
- `production_activation.enabled=false` 保持不变。
