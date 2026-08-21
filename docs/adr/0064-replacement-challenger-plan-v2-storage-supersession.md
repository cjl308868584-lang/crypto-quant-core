# ADR-0064：Replacement Challenger v2 存储安全 supersession

日期：2026-08-21

状态：已接受；`PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED`

## 背景

v0.62 冻结了 replacement Challenger 的研究范围、决策、540 槽/90 天 cohort、
失败 ancestry 和隔离身份，但存储路径合同仍指向 SQLite state 与两类独立
artifact。专项安全评审证明：在现有 CPython `sqlite3`/macOS 能力下，无法同时
保证主库、WAL/SHM、父目录 identity 和崩溃恢复都受 retained descriptor/no-follow
边界控制；直接写 canonical artifact 也会在 partial-write crash 后留下不可恢复的
最终路径。严格保留 v0.62 存储合同与失败关闭目标不可同时满足。

## 前置证据

- v0.62 plan 文件 SHA-256 保持
  `d450d1e9f8dc422eb5a93beb8a5ffbb1746a4a6d1facb3c5a20a76f4bd527734`，
  annotated `v0.62.0` 仍剥离到 `e0a9b3eb6a3f385ea259722e6613df8708e8fe5a`；
- 2026-08-21 的参数无关 collector 记录
  `NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION`：runtime root/plist 不存在，service
  未加载，当前树内 start receipt/canonical event 计数为 0；
- owner `cjl308868584-lang / chenm4 / uid 501` 签署历史声明，声明 SHA-256
  为 `408d98e2cccf6329a9db5ef1f3b5ad9e40c1e7cec22e86582e00b24f1820c7b0`。

当前 snapshot 只证明采集时的机器事实；Git 只证明不可变版本历史；Schema/loader
只证明结构、哈希、声明与绑定。它们都不证明 owner 的历史声明为真；责任
由签署者承担。

## 决策

1. 发布 v2 plan，状态为 `PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED`。v0.62 保持历史
   事实，标记为“启动前因存储安全纠正而被显式 supersede”，不静默改写，
   也不标记为研究 cohort 失败。
2. 唯一权威 state 改为 `state/challenger-replacement-events-v1` 下的 append-only
   canonical event log。Runner 只能写事件；observer/evaluator 只能消费严格 event
   projection。
3. `exports/source-bundles` 和 `exports/decisions` 仅为未来可重建的只读导出；
   它们不是 slot success、observer 或 evaluator 的事实源。v0.64 不实现 exporter。
4. v1/v2 的 `scope`、`decision_policy`、`cohort_policy`、`evidence_policy`、
   `predecessor`、`eligibility`、`authority`、service identity 和 runtime root 必须精确保持；
   只允许更改 Schema/version、storage relative paths、authority-source 合同和 supersession
   metadata。
5. 首个 start receipt 或 canonical event 之后永久禁止该 supersession。不得迁移、
   回填、补槽、重置起点或改写旧证据。
6. v0.64 build identity 为 `crypto-quant-core 0.64.0` 与
   `release-evaluator-build-v1@1.58.0`；构建清单单向绑定 plan、machine evidence、
   owner attestation、supersession record 和 public Linux R3 witness，不把它反向写入
   冻结 plan/record。

## 后果

v0.64 仅完成 plan/storage-governance supersession。它不包含 replacement runtime、
deployment、installer、observer、exporter、evaluator 或 start receipt，不创建 production
root/plist/service，不开始 90 天/540 槽位计时。`production_activation=false`，无
凭据、Broker、资金或真实订单。它不证明盈利、AI 优势、Paper 完成、Canary
或实盘资格。
