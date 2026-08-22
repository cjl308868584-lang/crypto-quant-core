# ADR-0066: Replacement Challenger Three-Stage Event Runtime

Status: Accepted  
Release state: `RUNTIME_RELEASED_NOT_INSTALLED`

## Decision

Replacement Challenger 的唯一运行状态权威是
`state/challenger-replacement-events-v1` 中的 append-only canonical event log。
成功槽仅允许 `INPUT_PREPARED -> RESULT_PREPARED -> SLOT_SUCCEEDED`；有效 INPUT
或 RESULT 后只允许 `SLOT_FAILED_PERMANENT` 失败终端。source bundle 与 decision
的 exact canonical bytes 存在事件 payload 中，未来 exports 只可只读重建，不能成为
Runner、observer 或 evaluator 的第二事实源。

事件根通过 retained directory capability、no-follow、no-overwrite、same-fd readback、
file/directory fsync 和 fresh-process replay 失败关闭。runtime 每阶段 fresh replay 并以
`expected_last_event_hash` 做 optimistic concurrency；崩溃后从最后耐久边界继续，不补写
过去槽位，不从新时间戳重建已提交事件。

## Rejected alternatives

- SQLite/WAL/SHM：冻结 v2 plan 已在首次启动前显式 supersede 旧路径合同；stdlib
  SQLite 无法满足已冻结的同 UID 路径对象安全边界。
- source/decision 独立权威文件：直接写 final 存在 partial-file crash window，并会产生
  双事实源。
- 通用 Broker、订单生命周期、调度器或 UI：不属于 replacement 研究证据特有层，YAGNI。

## Authority boundary

本版本只发布代码与不可变合同：`production_activation=false`、
`runtime_install_authorized=false`、`replacement_start_authorized=false`、
`real_orders_allowed=false`。没有 production root、plist、service、Runner、scheduler、
network、credential、Broker、订单、receipt 或 export 写入。

`no 90-day timer started`。`no profitability or AI advantage claim`。发布成功只表示工程候选
可进入后续 deployment/observer/start-receipt 设计，不表示研究门通过或可实盘。

## Verification

事件层覆盖真实双进程 no-replace 竞争、rename 后/dir-fsync 前 fresh-process replay、
symlink/hardlink/FIFO/目录替换与 close/IO 异常。runtime 覆盖三阶段 payload、单 active
slot、父链、+4h/20-bar overlap、optimistic token，以及 INPUT/RESULT/SUCCESS 后重试。
四个生产模块保持严格少于 2743 行，且不含 SQLite、artifact publisher 或平台化设施。
