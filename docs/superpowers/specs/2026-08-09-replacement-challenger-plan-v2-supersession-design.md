# Replacement Challenger Preregistration V2 Supersession Design

日期：2026-08-09

目标版本：`v0.64.0`（governance / plan-only）

基线：annotated `v0.63.0`，peeled commit
`df91e19240df14839125608422489adf3b902e76`

适用分支：`codex/v0.64-replacement-plan-v2`

## 1. 决策摘要

v0.64 只发布一个显式 superseding preregistration v2。它不修改、替换或删除 v0.62
tag 中的任何 byte，而是用新的 Schema、plan identity、plan hash 和独立 supersession
record 公开说明：v0.62 在 replacement Challenger 尚未安装、尚未启动、没有 start
receipt、没有 canonical event、没有真实槽位和没有 production state write 时，因冻结的
SQLite 与重复 artifact storage contract 无法同时满足已批准的失败关闭安全门而被 v2
取代。

v2 保持研究对象不变：`scope`、`decision_policy`、`cohort_policy`、`evidence_policy`、
`predecessor`、零启动/零交易 authority，以及 service identity 与 runtime root 必须与
v0.62 committed canonical subtree byte-equal。只允许改变：Schema/version 与机械 release
foundation、storage relative paths、唯一事实源合同、plan/status 的 supersession metadata。

v0.64 不实现 replacement runtime，不创建 production root/plist，不执行 Runner、scheduler、
maintenance、市场、账户、Broker 或订单动作，不生成 start receipt，不开始 90 天计时。原定
单一 end-to-end NautilusTrader Spike 保持 `v0.65.0`；三阶段 replacement event runtime
顺延到 `v0.66.0`。

## 2. 不可变 v0.62 基线

### 2.1 Git 与 plan artifact

supersession 必须逐字节绑定：

- annotated tag：`v0.62.0`；
- tag peeled commit：`e0a9b3eb6a3f385ea259722e6613df8708e8fe5a`；
- plan path：
  `artifacts/challenger-replacement/challenger-replacement-plan-v0.62.0.json`；
- file SHA-256：
  `d450d1e9f8dc422eb5a93beb8a5ffbb1746a4a6d1facb3c5a20a76f4bd527734`；
- plan ID：
  `challenger_replacement_plan_d4a542c1566f7a90466ca4d5301b81847f5b5eba93c7a00903d2d95331bc23a2`；
- plan hash：
  `95f395b17d9c09d325c58391542ce5f3d9df5ce6a706b1bba8ffcb62dc6c883c`；
- historical status：`PLAN_FROZEN_REPLACEMENT_NOT_STARTED`。

v0.62 artifact、Schema、ADR、status document、tag object 和 peeled commit 永不 amend、
force-move、删除或重新生成。新文档只能把它描述为
`SUPERSEDED_BEFORE_START_NO_COHORT_EVIDENCE`；不得描述为被静默修正、已经启动、研究失败或
无效 tag。

### 2.2 治理冲突

v0.62 `/isolation_policy/relative_paths` 冻结：

```json
{
  "state": "state/challenger-replacement.sqlite",
  "source_bundles": "artifacts/source-bundles",
  "decisions": "artifacts/decisions"
}
```

stdlib SQLite 无法在 retained dirfd/descriptor/VFS 边界内控制主库、WAL 和 SHM 的全部
打开与创建；直接写 canonical source/decision artifact 又会在 partial write 或断电后留下
不可恢复的 canonical partial。若同时补齐安全 SQLite、两套 artifact staging、descriptor、
FIFO 和 crash recovery，将扩展为新的通用存储平台并违反当前范围与 `<2743` 生产行数门。

因此严格执行 v0.62 storage contract 在当前已批准的安全模型和标准库边界内不可满足。把
event directory 伪装成 `.sqlite` 文件或让 ADR 覆盖 plan hash 都不允许。

## 3. Supersession 不改变研究假设

### 3.1 Canonical subtree byte-equality 门

测试必须从 committed v0.62 exact file bytes 通过 v1 production loader 得到 `v1`，从 v2
builder/loader 得到 `v2`，然后对下列 exact JSON paths 比较
`canonical_json(subtree).encode("utf-8")` 完全一致：

```text
/scope
/decision_policy
/cohort_policy
/evidence_policy
/predecessor
/eligibility
```

`/authority` 的以下 exact leaf paths 必须逐项类型和值一致：

```text
/authority/credentials_allowed                 false
/authority/account_requests_allowed            false
/authority/broker_requests_allowed             false
/authority/real_orders_allowed                 false
/authority/production_activation               false
/authority/runtime_install_authorized           false
/authority/replacement_start_authorized         false
/authority/runner_invocation_count              0
/authority/market_request_count                 0
/authority/state_write_count                    0
```

`/isolation_policy` 中除 `/isolation_policy/relative_paths` 与自动重算的
`/isolation_policy/policy_hash` 外，全部 subtree 必须 byte-equal；测试必须至少单独断言：

```text
/isolation_policy/service_label
/isolation_policy/service_identity
/isolation_policy/runtime_root
/isolation_policy/target_plist
/isolation_policy/forbidden_runtime_roots
/isolation_policy/directory_mode_octal
/isolation_policy/file_mode_octal
/isolation_policy/single_hardlink_required
/isolation_policy/no_overwrite_required
/isolation_policy/symlink_ancestors_forbidden
/isolation_policy/repository_or_worktree_root_allowed
/isolation_policy/cross_root_inode_reuse_allowed
```

不得使用不存在的 `strategy` 或 `evaluation` 泛称代替上述实际 JSON paths。

### 3.2 允许变化的路径

v2 只允许以下研究外变化：

```text
/$schema
/schema_version
/foundation
/plan_id
/plan_hash
/status
/warnings（只可新增本 supersession reason）
/isolation_policy/relative_paths
/isolation_policy/policy_hash
/storage_authority
/supersession
```

`foundation` 只记录 v0.63 release baseline 和 v0.64 build identity，不得携带策略、日期、价格、
费用、PnL 或结果。`status` 固定为
`PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED`。新增 warning 只能是
`V0_62_SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION`。

## 4. V2 storage contract

### 4.1 Exact relative paths

`/isolation_policy/relative_paths` 必须是以下 exact key set：

```json
{
  "state_events": "state/challenger-replacement-events-v1",
  "non_authoritative_exports": "exports",
  "stdout": "log/challenger-replacement.stdout.log",
  "stderr": "log/challenger-replacement.stderr.log",
  "deployment_contract": "deployment/contract.json",
  "deployment_plist": "deployment/local.crypto-quant.challenger-replacement-v1.plist",
  "preflight_receipts": "preflight-receipts",
  "install_receipts": "install-receipts",
  "start_receipts": "start-receipts",
  "episode_receipts": "episode-receipts",
  "archives": "archives",
  "results": "results",
  "indexes": "indexes",
  "evaluations": "evaluations"
}
```

v2 Schema 与 semantic validator 必须拒绝旧 keys：

```text
state
source_bundles
decisions
```

### 4.2 唯一事实源

新 `/storage_authority` 是带 `policy_hash` 的严格 object，固定：

```json
{
  "authoritative_state_kind": "APPEND_ONLY_CANONICAL_EVENT_LOG",
  "authoritative_relative_path": "state/challenger-replacement-events-v1",
  "runner_authority_source": "CANONICAL_EVENT_LOG_ONLY",
  "observer_authority_source": "STRICT_EVENT_PROJECTION_ONLY",
  "evaluator_authority_source": "STRICT_EVENT_PROJECTION_ONLY",
  "exports_authoritative": false,
  "exports_required_for_slot_success": false,
  "exports_required_for_evaluation": false,
  "exports_reconstructible": true,
  "source_bundle_export_subdirectory": "source-bundles",
  "decision_export_subdirectory": "decisions"
}
```

builder 在上述非自引用字段完全定型后，对该 object 的 canonical bytes 计算 SHA-256，
再添加唯一的 `policy_hash` 字段。Schema 的 exact key set 因此包含上述十一个非自引用
字段与 `policy_hash`；不允许调用者传入或覆盖该 hash。

`exports/source-bundles` 与 `exports/decisions` 只允许未来独立 exporter 从 strict event replay
生成。exporter 对 authoritative state 只读，但可向 export root 写派生文件。exports 可以不存在、
删除或重建，不能补 event 缺口，不能参与 start、连续性、slot success、observer health 或 evaluator。
v0.64 不实现或执行 exporter。

## 5. Supersession metadata 与独立 record

### 5.1 Plan 内 `/supersession`

v2 plan 必须绑定 v0.62 tag、peeled commit、path、file SHA、plan ID/hash，以及：

```text
reason = SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION
previous_plan_state = PLAN_FROZEN_REPLACEMENT_NOT_STARTED
previous_plan_disposition = SUPERSEDED_BEFORE_START_NO_COHORT_EVIDENCE
supersession_forbidden_after = FIRST_START_RECEIPT_OR_CANONICAL_EVENT
```

它不能引用尚未生成的 supersession record hash，以避免自引用循环。

### 5.2 独立 supersession record

正式 record 在正式 v2 plan artifact 已通过 loader 后才能生成。record 必须绑定：

- v0.62 exact file SHA、plan ID、plan hash、tag peeled commit；
- v2 exact path、file SHA、plan ID、plan hash、release baseline；
- `SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION`；
- `PLAN_SUPERSESSION_FORBIDDEN_AFTER_FIRST_START_RECEIPT_OR_CANONICAL_EVENT`；
- 真实机器零状态 evidence；
- record ID、record hash 与 canonical file SHA。

record 的 self-hash 只排除自身 `record_hash`。plan 不反向绑定 record，以免 plan/file hash 与
record 形成循环；release status、ADR 和 build manifest 可以在 record 生成后绑定两者。

## 6. 零状态证据

### 6.1 真实机器事实

正式 supersession record 的 machine evidence 只能由独立、只读 production CLI 在 release
候选机器上采集：

```text
system UTC time and timezone
effective uid
replacement runtime root lstat = ENOENT
target plist lstat = ENOENT
launchctl print gui/501/local.crypto-quant.challenger-replacement-v1 = NOT_LOADED
start receipt root/count = ABSENT / 0 (derived from absent runtime root)
state event root/count = ABSENT / 0 (derived from absent runtime root)
canonical event count = 0
replacement production state write count = 0
Runner/market/Broker/order invocation count performed by collector = 0
```

effective uid 必须精确为 `501`；其他 uid 下不得将动态 uid 代入 service domain，而是固定
失败关闭。CLI 只能调用 `lstat/stat`、系统时间、uid 与固定 argv 的 `launchctl print`。禁止
mkdir、chmod、touch、写
receipt、bootstrap、kickstart、Runner、scheduler、maintenance、市场、账户、Broker 或订单。
所有命令参数、退出码、stdout/stderr exact bytes 或其封存 hash 都进入 machine evidence。

“runtime root 不存在”允许派生其内部 start receipt/event count 为 0；不得声称证明机器历史上从未
运行任意程序。record 证明的是 replacement v1 的冻结绝对身份在观察时未 materialize，且本
collector 没有触发运行副作用。

### 6.2 测试与真实证据隔离

测试 fixture 固定：

```text
evidence_qualification = TEST_FIXTURE_ONLY_NOT_SUPERSESSION_EVIDENCE
```

正式 record 固定：

```text
evidence_qualification = REAL_MACHINE_READ_ONLY_SUPERSESSION_PRECONDITION
```

production loader 必须拒绝把 test fixture 当成正式 record。测试不得 monkeypatch production CLI
后写入 committed正式artifact；正式生成任务必须单独运行真实 CLI，然后由另一个只读 loader
重放 exact bytes。v0.64 文档阶段不执行这些检查，也不生成 receipt/record。

## 7. 三阶段 runtime 后续合同

v0.66 成功路径固定为：

```text
INPUT_PREPARED -> RESULT_PREPARED -> SLOT_SUCCEEDED
```

- `INPUT_PREPARED` 保存 exact materialized capture hash 与 source bytes；
- `RESULT_PREPARED` 保存 exact decision bytes并绑定source与previous decision；
- `SLOT_SUCCEEDED` 绑定前两项event sequence/hash和exact bytes SHA-256。

失败终端仍是独立 canonical event。不存在 `SOURCE_BUNDLE_PUBLISHED`、
`DECISION_PUBLISHED`、SQLite/WAL/SHM 或 Runner artifact path authority。

未来 observer 只读 retained event-root capability，验证root identity、sequence、parent hash、
plan/build identity、active slot、completed slot count、next required slot和orphan staging统计。
confirmatory tail前不得输出中期PnL、收益、胜率或提前PASS。

未来 evaluator 只接受v2 exact plan、install/start receipt、event-root identity和完整canonical
event sequence，从event payload重建source/decision并重放semantic parents。它不得读取exports
作为输入，也不得用exports补缺失event。

## 8. Supersession 禁令

v2 builder、record collector和loader必须失败关闭：

```text
PLAN_SUPERSESSION_FORBIDDEN_AFTER_FIRST_START_RECEIPT_OR_CANONICAL_EVENT
```

任一条件成立即禁止生成或接受 supersession record：

- replacement runtime root存在且身份不能证明为空；
- start receipt count非零或不明确；
- canonical event count非零或不明确；
- service已加载；
- production state write非零或不明确。

规则不是允许未来自动创建 v3。任何后续计划变化都必须再次经过独立治理设计；一旦真实 cohort
开始，storage、策略、窗口和evaluator合同不得以supersession方式改写。

## 9. 发布边界与版本顺序

```text
v0.64.0  superseding preregistration v2 only
v0.65.0  single end-to-end NautilusTrader Spike (unchanged)
v0.66.0  three-stage replacement event runtime
v0.67.0+ deployment / observer / start receipt
```

v0.64 不包含 runtime、deployment、installer、observer、exporter 或 evaluator。正式 v2 plan
artifact 必须在全部 builder/Schema/invariant/supersession tests 通过之后生成；supersession record
必须在 plan artifact loader通过之后生成。旧 v0.62 bytes/tag永不修改。

## 10. 可证伪验收标准

v0.64 只有同时满足以下条件才可成为 release候选：

1. v0.62 exact file/tag identity重放通过；
2. 第3.1节所有canonical subtree byte-equality门通过；
3. v2 relative path exact key set通过，旧三个key全部被拒绝；
4. storage authority明确event-only、exports non-authoritative；
5. v2 plan ID/hash/file SHA自动派生并由production loader重放；
6. supersession record绑定v1、v2和真实机器零状态证据；
7. test fixture不能成为正式record；
8. old tag、artifact、ADR和status bytes与v0.62 tag完全一致；
9. 没有production root/plist/service/start receipt/event/Runner/market/Broker/order/state write；
10. repository没有replacement runtime、deployment或exporter实现混入本版本。

任何值未知、路径存在、service已加载、event/start receipt非零、Schema/hash/identity不一致或旧
bytes发生变化都停止发布，不生成“较好”record，不重新定义计划以绕过失败。
