# Replacement Challenger Preregistration V2 Supersession Design

日期：2026-08-09

目标版本：`v0.64.0`（governance / plan-only）

基线：annotated `v0.63.0`，peeled commit
`df91e19240df14839125608422489adf3b902e76`

适用分支：`codex/v0.64-replacement-plan-v2`

## 1. 决策摘要

v0.64 只发布一个显式 superseding preregistration v2。它不修改、替换或删除 v0.62
tag 中的任何 byte，而是用新的 Schema、plan identity、plan hash 和独立 supersession
record 公开说明 storage safety correction。该 correction 只能在三层前置同时完整时被描述为
pre-start supersession：采集时机器快照显示没有可观察 replacement state；accountable owner
attestation 明确承担“在观察前从未 install/start/receipt/event/state write”的历史声明；
不可变 Git/release history 封存其能够观察的 repository 事实。任何代码、loader、Git 或
OS snapshot 都不得宣称证明 owner 历史声明为真；attestation 或可观察历史依据缺失时
supersession 失败关闭。

v2 保持研究对象不变：`scope`、`decision_policy`、`cohort_policy`、`evidence_policy`、
`predecessor`、零启动/零交易 authority，以及 service identity 与 runtime root 必须与
v0.62 committed canonical subtree byte-equal。只允许改变：Schema/version、只绑定 v0.63 predecessor
release 的 exact foundation、storage relative paths、唯一事实源合同、plan/status 的 supersession
metadata。v0.64 build/manifest identity 在 plan、machine evidence、attestation 和 record 全部生成后由
release manifest/status/ADR 单向绑定，不反向进入 plan 或 record hash。

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

`foundation` 只绑定 v0.63 predecessor release，必须是以下 exact object：

```json
{
  "release_tag": "v0.63.0",
  "peeled_commit": "df91e19240df14839125608422489adf3b902e76",
  "package_version": "0.63.0",
  "manifest_version": "1.57.0",
  "build_input_tree_hash": "7fdfd6c69f1342892b222882b76ee4988487a482c958a9cdacf00461b2fd8f19",
  "manifest_hash": "f4a74896a6d7b2166adba86075ef06b8d7986f900a086d04ee2f03754baded4b",
  "manifest_file_sha256": "13bea4bfcf633e767eed73d431e57d496dcee47820aacf92e7b61b0efed5c546"
}
```

v0.64 build/manifest identity 不进入此 object。`status` 固定为
`PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED`。`warnings` 必须精确等于 v0.62 原六项的原顺序、
原值，再且仅追加一项：

```text
OLD_COHORT_PERMANENTLY_FAILED_NO_BACKFILL
REPLACEMENT_RUNTIME_NOT_IMPLEMENTED
REPLACEMENT_NOT_INSTALLED_OR_STARTED
NO_INTERIM_ECONOMIC_REPORTING
NO_PROFITABILITY_OR_AI_ADVANTAGE_CLAIM
CANARY_NOT_AUTHORIZED
V0_62_SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION
```

删除、改写、重排原 warning，或追加第八项都失败关闭。

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
- v2 exact path、file SHA、plan ID、plan hash 与 v0.63 predecessor release foundation；
- `SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION`；
- `PLAN_SUPERSESSION_FORBIDDEN_AFTER_FIRST_START_RECEIPT_OR_CANONICAL_EVENT`；
- `NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION` machine evidence 及其 canonical hash；
- accountable owner attestation 及其 canonical hash；
- immutable Git/release-history evidence 及其 transcript hash；
- record ID 与 record hash。
- `C2_EVIDENCE_ATTESTATION_ONLY` 的 exact HEAD/status transcript、空 staging inventory，以及
  machine-evidence 与 attestation final 的 file SHA/stat identity。

record 的 self-hash 只排除自身 `record_hash`。plan 不反向绑定 record，以免 plan/file hash 与
record 形成循环。record canonical file SHA-256 是对已生成 exact bytes 的外部计算值，不是
record 内部字段；release status、ADR 和 build manifest 在 record 生成后单向绑定 plan file
SHA、attestation file SHA、record file SHA 与 v0.64 build identity，不将后者反向写入 plan 或 record。

### 5.3 Accountable owner attestation

owner attestation 是独立 canonical object，必须绑定 v0.62 exact identity、v2 plan ID/hash/file
SHA、machine-evidence hash、Git-history-evidence hash，并包含：

```text
attestation_type = ACCOUNTABLE_OWNER_PRE_START_HISTORY_ATTESTATION_V1
signer_github_login = cjl308868584-lang
signer_os_username = chenm4
signer_uid = 501
signed_at = canonical UTC timestamp collected at the signing ceremony
owner_acknowledgement = I_SIGN_AND_ACCEPT_ACCOUNTABILITY_FOR_THE_EXACT_DECLARATION
```

它还必须保存 `C1_EVIDENCE_ONLY` 的 exact HEAD/status transcript、空 staging inventory 与
machine-evidence final 的 file SHA/stat identity。`st_dev`、`st_ino`、`st_mtime_ns`、`st_ctime_ns`
以 canonical unsigned decimal string 保存，避免超过 exact JSON safe-integer 范围；mode 固定为
`0644`、nlink 固定为 `1`，size 必须在既定 1..4MiB 边界内。

`declaration` 必须是以下 exact UTF-8 string：

```text
I attest that, before the signed_at timestamp in this object and before the linked machine observation, the replacement Challenger service_identity and runtime_root bound by previous_plan and superseding_plan in this object had never been installed or started and had produced no start receipt, canonical event, real slot, or production state write. I accept accountability for this historical declaration and understand that it is not proved by the collector, loader, Git history, or operating-system snapshot.
```

attestation 必须在 owner 看到 exact declaration、两个 plan identity 和 machine/Git evidence hash 后经显式
确认，其 exact bytes 与审查 transcript 再进入 reviewed Git commit。这是可问责治理声明，不是
代码可验证的历史事实，也不宣称具有独立密码学真实性。Schema/loader 只能校验字段、
canonical hash 与绑定；审查者必须单独确认显式 owner approval 与提交 provenance。缺失、含糊、
身份不一致或 owner 未显式确认均禁止 supersession。

## 6. Snapshot、历史声明与 provenance

### 6.1 真实机器事实

正式 supersession record 的 machine evidence 只能由独立 OS 进程中的只读 production CLI 在 release
候选机器上采集：

```text
observation = NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION
system UTC time and timezone
effective uid
replacement runtime root lstat = ENOENT
target plist lstat = ENOENT
launchctl print gui/501/local.crypto-quant.challenger-replacement-v1 = NOT_LOADED
current runtime-tree start receipt root/count = ABSENT / 0 (derived only from absent runtime root)
current runtime-tree state event root/count = ABSENT / 0 (derived only from absent runtime root)
current runtime-tree canonical event count = 0 (derived only from absent runtime root)
collector state-write/Runner/market/Broker/order invocation counts = 0/0/0/0/0
```

effective uid 必须精确为 `501`；其他 uid 下不得将动态 uid 代入 service domain，而是固定
失败关闭。CLI 只能调用 `lstat/stat`、系统时间、uid 与固定 argv 的 `launchctl print`。禁止
mkdir、chmod、touch、写
receipt、bootstrap、kickstart、Runner、scheduler、maintenance、市场、账户、Broker 或订单。
所有命令参数、退出码、stdout/stderr exact bytes 或其封存 hash 都进入 machine evidence。

“runtime root 不存在”只允许派生“当前不存在的该树内 count=0”；不得推导历史 count=0、
历史从未启动或删除前的状态。`collector state-write count=0` 只表示 collector 自身没有写入，
不得命名或解释为 replacement production historical state-write count。machine evidence 的最强结论只是
`NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION`。

### 6.2 Immutable Git/release-history evidence

独立只读进程还必须封存 exact argv、exit code、stdout/stderr bytes/hash，以观察：

```text
v0.62.0 annotated tag object and peeled commit
v0.63.0 annotated tag object and peeled commit
v0.62 exact plan path, file SHA, plan ID and plan hash
reviewed v0.64 candidate commit, C0 raw Git status empty and ancestry from v0.63.0
Git history for committed artifacts/challenger-replacement and v0.62 ADR/status paths
```

该 evidence 只证明被查询 Git object/history 中可观察的事实；它不能证明未提交的机器行为、
已删除 runtime tree 或 owner 的历史声明。任何 Git 命令不明确、tag/repository 身份不一致，或
可观察 committed history 与 owner attestation 相矛盾，都禁止 supersession；空 Git 路径结果仍不替代
owner attestation。

### 6.3 可验证边界与治理 provenance

测试 fixture 固定：

```text
evidence_qualification = TEST_FIXTURE_ONLY_NOT_SUPERSESSION_EVIDENCE
```

正式 record 固定：

```text
evidence_qualification = REAL_MACHINE_READ_ONLY_SUPERSESSION_PRECONDITION
```

Schema/loader 只能拒绝结构不合法、hash/绑定不一致或 qualification claim 不正确的 bytes；
它不能证明 Python 进程未被 monkeypatch，也不能区分结构完全相同的伪造 fixture。测试只能证明
公开 CLI 没有身份、count、status、reason、hash、路径或 qualification override，不得宣称“fixture
在技术上不可伪造或提交”。

正式 provenance 由以下治理门共同形成：独立 OS 进程；exact reviewed HEAD 与候选状态 transcript；固定无 override
argv；封存 stdout/stderr/transcript；accountable owner attestation；另一个只读进程 replay；独立审查与
reviewed Git commit ceremony。其中任何一项缺失都不能生成或接受正式 supersession record。
v0.64 文档阶段不执行这些检查，也不生成 evidence/attestation/record。

### 6.4 固定路径与耐久发布边界

collector/attestation/record CLI 不接受 input path、output path、repository root 或任意 absolute path。它们
只能从已审查 module identity 派生 repository root，验证 owner、非 symlink ancestor、exact candidate
HEAD、第6.5节定义的 Git status allowlist、独立 protocol-staging inventory 和固定 relative artifact
path；派生路径不符 reviewed repository 时失败关闭。只有初始状态与最终提交后状态可称为
Git clean，中间状态必须按 allowlist 精确命名。

所有正式 plan、evidence、attestation 和 record 只能经 replacement-supersession 专用 publisher 发布。禁止
直接 `O_EXCL` 写 canonical final，也禁止复用 v0.63
`system_paper_evidence.publish_owner_exact`。专用协议必须：

1. retained parent dirfd 必须 owner uid=`501`、mode=`0755`，并经 identity、非 symlink ancestor 校验；缺少
   `O_NOFOLLOW`/`O_DIRECTORY`/`O_NONBLOCK` 时显式 unsupported；
2. 在同目录以非 canonical unique nonce staging name 和 `O_CREAT|O_EXCL|O_RDWR|O_NOFOLLOW`
   新建 mode=`0644`，验证实际 uid=`501`、mode=`0644`、nlink=`1`，通过唯一 retained fd 处理
   short write/EINTR；不得通过 path chmod 修复对象；
3. 在同一 fd 上 seek/readback exact bytes、size/hash/identity，然后 `fsync(file)`；
4. 用第6.6节冻结并实证的 atomic no-replace primitive 发布到固定 canonical final，再
   `fsync(parent dirfd)` 和重验 parent/final identity，只有完成后才返回成功；
5. crash 留下的 staging 永不作为 canonical evidence；fresh process 必须按第6.5节单独分类、封存且
   永不读/写/chmod/unlink/rename 它们。retry 可用新 nonce staging 完成同一 canonical final，但
   任何 orphan 残留都使 release 保持 `RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED`，禁止进入后续
   attestation/record/commit；final exact+trusted 必须重做 directory fsync 与 identity replay 后返回
   already-published；
6. existing final 以 `O_RDONLY|O_NOFOLLOW|O_NONBLOCK` 打开后先 `fstat`，在读取前只接受
   regular file、uid=`501`、mode=`0644`、nlink=`1` 和 bounded size；拒绝 FIFO、socket、directory、
   symlink、hardlink/extra-link、wrong owner/mode/size 或 different bytes；
7. file/dir fsync、close、identity 或 no-replace 任一失败不得返回成功，所有拒绝路径必须
   保持外部 sentinel bytes/mode/size/mtime/ctime/inode/nlink 不变。

上述 publisher 只服务本 supersession 的四个固定 artifact，不得演化为 generic storage API。

该边界采用分层威胁模型：它必须拒绝不可信既有对象、symlink/hardlink/nonregular、可观察的
parent/staging/final identity replacement，以及多个遵守协议的并发 publisher；随机 nonce、retained
dirfd、pre/post attachment checks 与 atomic no-replace 用于捕获这些冲突并失败关闭。它不声称抵抗一个
可持续以同一 UID 枚举目录并在最后一次 attachment check 与内核 rename 调用之间主动替换目录项的
恶意进程；Darwin `renameatx_np` 与 Linux `renameat2` 均不提供“仅当 source inode 等于已持有 fd”这一
原子条件。若该强对手属于范围，必须使用独立 OS UID/sandbox/特权 publisher，这是独立架构项目，
不得用 post-check 冒充已经防住。任何 post-check 冲突、unexpected final 或 orphan 都禁止 commit/release，
并保留该 worktree 取证。

### 6.5 候选 Git/发布状态机

Task 5 将 plan artifact 提交后冻结 `HEAD=H`。三项 supersession artifact 在同一 `H` 上顺序
生成，中间不得 commit/amend/rebase/checkout。每个命令必须在创建 staging 前封存 raw
`git status --porcelain=v1 --untracked-files=all`、`HEAD`、所有 allowlisted final 的 exact bytes/hash/stat/identity
与独立 staging inventory：

| State | HEAD | raw Git status exact allowlist | Next command |
|---|---|---|---|
| `C0_PLAN_COMMITTED_CLEAN` | `H` | empty | `collect-machine-evidence` |
| `C1_EVIDENCE_ONLY` | `H` | evidence final only | `record-owner-attestation` |
| `C2_EVIDENCE_ATTESTATION_ONLY` | `H` | evidence + attestation finals only | `assemble-record` |
| `C3_THREE_FINALS_UNCOMMITTED` | `H` | evidence + attestation + record finals only | exact three-file commit |
| `C4_THREE_FINALS_COMMITTED_CLEAN` | new commit `H2` | empty | release metadata/review |

表中的 allowlist 必须按以下 exact porcelain lines 以 byte-sorted tuple 比较：

```text
C1:
?? artifacts/challenger-replacement/challenger-replacement-supersession-machine-evidence-v0.64.0.json

C2:
?? artifacts/challenger-replacement/challenger-replacement-owner-attestation-v0.64.0.json
?? artifacts/challenger-replacement/challenger-replacement-supersession-machine-evidence-v0.64.0.json

C3:
?? artifacts/challenger-replacement/challenger-replacement-owner-attestation-v0.64.0.json
?? artifacts/challenger-replacement/challenger-replacement-plan-supersession-v0.64.0.json
?? artifacts/challenger-replacement/challenger-replacement-supersession-machine-evidence-v0.64.0.json
```

`collect-machine-evidence` 内的 machine evidence 保存创建 evidence staging 之前 `C0` 的 raw status exact
bytes，所以它能说“采集前 Git clean”。attestation 和 record 分别保存 `C1`/`C2` precondition
transcript，必须称为 exact allowlisted dirty state，不得称 clean。每个既有 final 都必须用 strict
loader 与 file identity 重放；额外 tracked/untracked entry、HEAD 变化或 allowlisted final identity 变化均
失败关闭。

machine-evidence、owner-attestation 与 supersession-record 的三个 fixed-path regression test
骨架必须在冻结 `HEAD=H` 前提交。正式 artifact 尚不存在时，每个测试只能按自己的 exact fixed path
使用 method-level absence-only skip；不得 broad skip 或捕获 loader 异常。到 Task 6 三项均生成后，必须
只运行这些已提交测试，要求三项全部实际执行且 skip count 为零，不得修改任何 code/test。因此
`C1`/`C2`/`C3` raw-status allowlist 始终只包含对应正式 JSON，`HEAD=H` 保持不变。

staging basename 必须匹配 ASCII regex
`\A\.v064-supersession-(plan|machine-evidence|owner-attestation|supersession-record)-[0-9a-f]{64}-[0-9a-f]{32}\.staging\Z`，并由精确
`.gitignore` rule 从普通 status 排除；这不允许把它当作“不存在”。每个 precondition 还必须用
retained artifact-parent dirfd 列出 staging namespace，封存 basename/lstat/uid/mode/size/dev/ino/nlink/mtime_ns/
ctime_ns。fresh process 对符合 exact basename grammar、regular file、uid=`501`、mode=`0644`、nlink=`1`
与 bounded size 的每一项只标记 `SEALED_UNTRUSTED_PROTOCOL_NAMESPACE_ENTRY`；不声称它由前一进程
创建，也不读取其内容作为 evidence。inventory 最多接受 64 项；symlink、hardlink/extra-link、
nonregular、wrong-owner/mode、超限 entry 或第65项使候选失败关闭。

已封存 orphan 不阻止 publisher 以新 nonce 对同一 exact final 做幂等 retry，但 fresh process 绝不修改
orphan。因此 external sentinel 的 bytes/mode/size/mtime/ctime/inode/nlink 保持不变。retry 成功后
若 orphan inventory 非空，状态为 `RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED`，不得伪报 `C1`-`C4`，
不得静默删除、quarantine 或忽略。本 v0.64 不设计 destructive cleanup；没有 orphan 的正常路径才能
到达 `C4_THREE_FINALS_COMMITTED_CLEAN`。orphan 阻断的 worktree 必须原样保留作失败取证；恢复只能
从 exact pre-artifact commit 创建全新隔离 worktree 并重走 ceremony，不得删除或修改 orphan。

### 6.6 Atomic no-replace 平台可行性门

本设计明确不选择 hardlink staging→final，避免 link 成功后 unlink 前崩溃留下 nlink=2 而
无法在不变更 external sentinel 的前提下安全恢复。唯一允许的 primitives 是：

- Darwin：用 `ctypes.CDLL(None, use_errno=True)` 解析
  `renameatx_np(src_dirfd, src_name, dst_dirfd, dst_name, RENAME_EXCL)`，`RENAME_EXCL=0x00000004`；
- Linux：用 `ctypes.CDLL(None, use_errno=True)` 解析
  `renameat2(src_dirfd, src_name, dst_dirfd, dst_name, RENAME_NOREPLACE)`，`RENAME_NOREPLACE=1`。

两者都以同一 retained artifact-parent dirfd 同时作为 src/dst dirfd，只接受固定 relative basenames。
`ctypes` signature 必须冻结为 `c_int, c_char_p, c_int, c_char_p, c_uint -> c_int`，并在读取
errno 前保留返回值。缺少 symbol，或返回 `ENOSYS`/`EOPNOTSUPP`/`ENOTSUP`，统一为
`CHALLENGER_REPLACEMENT_SUPERSESSION_ATOMIC_NOREPLACE_UNSUPPORTED`。禁止 `os.rename`、
`os.replace`、直写 final、hardlink 和任何 syscall-number/非 no-replace 静默降级。

在任何 Task 5 artifact 生成前，Task 4 代码提交必须先建立不含正式 artifact 的 Draft PR，并在
owner-only temporary directory 完成两个实证门：
同目录两进程竞争同一 final 只有一个 success、一个 `EEXIST`；existing final bytes/inode 不被
替换；file fsync、no-replace、directory fsync 各 crash boundary 的 fresh-process replay 符合第6.4/6.5节。
Draft PR 的 Linux Python 3.9/3.12 CI 都必须实际运行 Linux 路径；macOS release candidate 必须在目标
Mac 上实际运行 Darwin gate。Linux CI、Darwin mock 或任一平台 skip 不能替代目标实证。两个门都绑定
同一 Task 4 commit，且任一语义、symbol、kernel/filesystem 支持不符即在
artifact 前停止，不生成 plan/evidence/attestation/record。

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

- machine observation 不是 `NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION`；
- replacement runtime root/plist 当前存在，或 service 当前已加载；
- accountable owner attestation 缺失、不明确、未显式批准或与 plan/evidence identity 不符；
- immutable Git/release-history evidence 缺失、不明确或与冻结 tag/artifact identity 不符；
- owner attestation 不能声明历史 start receipt/canonical event/real slot/state write 均为零；
- collector 自身 state-write/Runner/market/Broker/order counter 任一非零或不明确。

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
5. foundation 精确等于 v0.63 predecessor object，warnings 精确等于 v0.62 list 加唯一追加项；
6. v2 plan ID/hash/file SHA自动派生并由production loader重放；
7. record 绑定 v1、v2、`NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION`、owner attestation 与
   Git/release-history evidence；
8. Schema/loader 测试只声称结构/hash/claim 校验，provenance 由独立进程、固定 argv、transcript、
   owner approval、审查与 commit ceremony 核对；
9. 四个正式 artifact 均通过第6.4节协议耐久发布，没有 partial canonical final；
10. old tag、artifact、ADR和status bytes与v0.62 tag完全一致；
11. machine snapshot 仅报告当前没有可观察 production root/plist/service/start receipt/event，collector 自身
    Runner/market/Broker/order/state-write 均为零；
12. C0-C4 每一步 HEAD/raw status/final identity/transcript 与 staging inventory 精确符合第6.5节，只有
    C0/C4 被称为 clean；
13. Draft-PR Linux Python 3.9/3.12 actual `renameat2` gate 与目标Mac actual `renameatx_np` gate 在
    Task 5 前绑定同一代码提交并通过；
14. protocol orphan 永不改变 external sentinel，且任何残留 orphan 都阻断 attestation/record/commit/release；
15. repository没有replacement runtime、deployment或exporter实现混入本版本。

任何值未知、当前路径存在、service已加载、attestation/provenance缺失、Schema/hash/identity
不一致或旧 bytes发生变化都停止发布，不生成“较好”record，不重新定义计划以绕过失败。
