# Replacement Challenger Three-Stage Event Runtime Design

日期：2026-08-22
目标版本：`v0.66.0`
状态：设计冻结；仅代码与候选发布，未安装、未启动
权威基线：annotated `v0.65.1` peeled commit
`9799a99823a1b3fbc33368357991b09ef7dc321b`

## 1. 目标

实现 replacement Challenger 的最小、可重放、失败关闭三阶段状态机：

```text
INPUT_PREPARED -> RESULT_PREPARED -> SLOT_SUCCEEDED
```

唯一权威状态是冻结 v2 plan 指定的
`state/challenger-replacement-events-v1` append-only canonical event log。
source bundle 与 decision 的 exact canonical bytes 保存在事件 payload 中；
`exports/source-bundles` 与 `exports/decisions` 未来只能从事件重建，不是 slot
success、observer 或 evaluator 的输入。

v0.66 不创建 production runtime root、plist、service、start receipt、export、observer
或 evaluator，不开始 90 天/540 槽计时。

## 2. 冻结依据

唯一 plan 为：

- path：`artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json`
- file SHA-256：
  `5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f`
- plan id：
  `challenger_replacement_plan_65d85d60a534a917f45a1ffa5fc9d3f74d6d24995b900d31b8c73cd26f0bd97b`
- plan hash：
  `c9a1e5f74c52fbf23be5a1d27fd23c25f3601ed58133178fc25480391ab65705`
- status：`PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED`

runtime 必须通过 `challenger_replacement_plan_v2_reasons` 复核整个 plan。不允许
v1 plan、人工精简 plan 或仅比较 plan hash。

v2 的以下冻结约束不变：

- `scope` 为 ETHUSDT/BINANCE_SPOT/LONG_ONLY/4h/BASELINE_ONLY；
- 90 天、540 个自然槽，无回填、无窗口延长、无 optional stopping；
- predecessor 漏槽失败和 decommission 永久保留；
- `production_activation=false`、`replacement_start_authorized=false`、
  `runtime_install_authorized=false`、无凭据、Broker 或真实订单；
- confirmatory tail 前禁止输出中期 PnL、收益率、胜率、排名、功效或提前 PASS。

## 3. 范围

### 3.1 包含

- replacement source bundle 的纯构建、strict bytes loader 和语义验证；
- replacement decision 的纯计算、父链和 4h/20-bar overlap 验证；
- retained event-root capability；
- 确定性 event codec、no-overwrite publication、durability confirmation 和 strict replay；
- three-stage projection、optimistic token、single-active-slot 和 fresh-process recovery；
- 仅使用 fixture/candidate root 的集成测试；
- v0.66 版本、构建清单、ADR、实施状态和发布门。

### 3.2 不包含

- deployment、installer、LaunchAgent、bootstrap、kickstart；
- scheduler、maintenance、natural Runner 调用或 production root 写入；
- observer、start receipt、episode receipt、archive、evaluator、exporter；
- SQLite、SQL、schema/trigger/PRAGMA、WAL/SHM、lease 或 stale takeover；
- source/decision 独立权威文件；
- 市场网络请求、凭据、账户、Broker、订单、资金或真实交易；
- 通用交易引擎、通用模拟 Broker、通用 UI 或 Nautilus runtime 集成。

## 4. 威胁模型

### 4.1 v0.66 基线

防御目标：

- 不可信的既有 root/final/staging path 对象；
- symlink、hardlink、FIFO、socket、directory 和非 regular final；
- 验证后 root/directory entry rename 或替换；
- partial write、short write、EINTR、file fsync 失败、no-replace 竞争、
  directory fsync 失败与 fresh-process replay；
- 多个遵守协议的并发 writer 争用同一 global sequence；
- 意外损坏、父哈希断裂、重复候选和非法 state transition。

所有 I/O 经 retained event directory descriptor、`O_NOFOLLOW`、`fstat`、
`st_uid`、regular type、mode、`st_nlink=1`、device/inode attachment 验证。

### 4.2 非承诺边界

v0.66 不声称抵抗一个可持续以同 UID 修改 event root 内容的恶意进程。
公开 hash chain 是损坏/不一致检测，不是对同 UID 攻击者的真实性证明。
强对手模型需独立 OS UID/沙箱/特权服务，或攻击者不可访问的密钥加外部
单调锚点；它是未来独立架构项目。

## 5. 文件和责任

### 5.1 生产模块

- `challenger_replacement_evidence.py`：仅 source bundle 构建、strict canonical bytes
  loader 和 schema/semantic validation。不存在 output-root、publisher、path loader 或 chmod。
- `challenger_replacement_decision.py`：仅 frozen policy 计算与 previous-decision
  semantic chain。不 I/O。
- `challenger_replacement_events.py`：event-root capability、codec、append 和 replay。
  不理解交易决策。
- `challenger_replacement_runtime.py`：三阶段 projection 和单槽 orchestration。
  只依赖前三个模块和 v2 plan validator。

四个模块最终总行数必须严格小于 `2743`。预算为：

```text
decision <= 360
evidence <= 650
events   <= 820
runtime  <= 500
target   <= 2330
```

超过 2743 不得以“稍后再删”继续；必须停止并重新设计。

### 5.2 Schema

- `challenger-replacement-source-bundle-v1.schema.json`
- `challenger-replacement-decision-v1.schema.json`

config 与 package resource 必须逐字节一致。Schema 只证明结构，semantic loader
还必须重算 self-hash、plan/build/parent identity 和时间/数据连续性。

## 6. Event root capability

`ChallengerReplacementEventRootIdentity` 精确包含：

```text
absolute_path, device, inode, uid, mode_octal
```

`open_challenger_replacement_event_root(identity)` 只打开已存在的 owner-only `0700`
directory。必须要求平台真实提供 `O_NOFOLLOW` 与 `O_DIRECTORY`；缺少时
`CHALLENGER_REPLACEMENT_EVENT_PLATFORM_UNSUPPORTED`，禁止 flag=0 降级。

capability 保留 dirfd，每次 I/O 前后重验 root stat 与 path attachment。公共构造器
不接受任意 path。v0.66 不创建 production root；测试显式创建 owner-only
fixture directory 并构造 identity。

## 7. Canonical event codec

### 7.1 Core

每个 event 的 exact deterministic JSON 包含：

```text
schema_version = challenger_replacement_event_v1
sequence                         1..(2^53-1)
event_type                       frozen enum
slot_id                          non-empty string
worker_id                        non-empty string
recorded_at                      canonical UTC millisecond timestamp
previous_event_hash              64 lowerhex; genesis = 64 zeros
payload_encoding                 base64_rfc4648
payload_bytes_base64             exact canonical payload bytes
payload_sha256                   SHA-256(payload bytes)
plan_hash                        exact v2 plan hash
build_identity_hash              hash of exact v0.66 build identity
event_root_device
event_root_inode
event_hash
```

`event_hash = SHA256("CHALLENGER_REPLACEMENT_EVENT_V1\\0" || canonical(core_without_event_hash))`。
loader 重新编码 core 和 full event，要求与输入 bytes 完全相同。事件最大
`4 MiB`；超限在创建 staging 前失败。

`worker_id` 仅是运行归属证据；`recorded_at` 是阶段首次耐久发布时间。
fresh retry 必须从 replay 取回已发布值，不得用新 worker/time 重建已存
sequence。

### 7.2 Publication

canonical final name 为 `00000000000000000001.event.json`。发布协议：

1. exact final fast path 在任何 staging 创建前完成；
2. 创建非规范 `.stage-<sequence>-<hash>-<nonce>.tmp`，
   `O_CREAT|O_EXCL|O_RDWR|O_NOFOLLOW`, mode `0600`；
3. `write_all` 显式处理 short write/EINTR；
4. 通过同一 retained O_RDWR fd `lseek/read` 回读 exact bytes/hash/size；
5. `fsync(file)`；
6. 在 Darwin 用 `renameatx_np(..., RENAME_EXCL)`，Linux 用
   `renameat2(..., RENAME_NOREPLACE)`；缺 symbol/kernel support 失败关闭；
7. rename 后用 retained fd 复核 final attachment/device/inode/nlink/mode；
8. `fsync(event dir)`；
9. 最后 root validate 后才返回 `COMMITTED`。

禁止 `os.rename`、`os.replace`、直接写 canonical final、hardlink publish 或 chmod 修复
不可信对象。orphan staging 不是业务候选；replay 只统计 name/count/bytes，
不读取其内容作为状态，也不删除/修改它。

exact final 重试在返回 `ALREADY_COMMITTED` 前必须重放 bytes，补做
directory fsync 并重验 root。EEXIST exact race 同样处理。different event 争用同一
sequence 返回 `CHALLENGER_REPLACEMENT_EVENT_SEQUENCE_CONFLICT`。

## 8. Three-stage payloads

### 8.1 `INPUT_PREPARED`

payload exact key set：

```json
{
  "capture_sha256": "64 lowerhex",
  "source_bundle_bytes_base64": "base64 exact canonical bytes",
  "source_bundle_sha256": "SHA-256(source bytes)"
}
```

只有无 active slot 时才能开始新 slot。source bundle 必须通过 strict loader，
绑定 exact v2 plan/build identity、21 根连续 4h bars、slot sequence/time 与父链。

### 8.2 `RESULT_PREPARED`

payload exact key set：

```json
{
  "input_event_hash": "64 lowerhex",
  "input_event_sequence": 1,
  "source_bundle_sha256": "64 lowerhex",
  "decision_bytes_base64": "base64 exact canonical bytes",
  "decision_sha256": "64 lowerhex",
  "previous_decision_hash_or_null": null
}
```

source hash 必须等于 active INPUT。decision strict loader 必须重算 decision self-hash，
绑定 source、plan、build identity 和 previous succeeded decision。genesis 仅 sequence=1 时
previous 为 null；后续槽必须使用 replay 中最后一个 succeeded decision，且 scheduled
time 严格 `+4h`、20-bar overlap 完全相同。

### 8.3 `SLOT_SUCCEEDED`

payload exact key set：

```json
{
  "input_event_hash": "64 lowerhex",
  "input_event_sequence": 1,
  "result_event_hash": "64 lowerhex",
  "result_event_sequence": 2,
  "source_bundle_sha256": "64 lowerhex",
  "decision_sha256": "64 lowerhex"
}
```

所有 hash/sequence 必须与前两个 event 严格相同。成功后 active slot 清空；
该 slot 永久 terminal，禁止后续事件。

### 8.4 失败 terminal

`SLOT_FAILED_PERMANENT` 是唯一 v0.66 槽级失败终端，payload exact key set：

```json
{
  "failed_after_event_hash": "64 lowerhex",
  "failed_stage": "INPUT_PREPARED|RESULT_PREPARED",
  "reason_code": "non-empty fixed domain reason"
}
```

只有已耐久绑定的 active slot 可追加失败事件，并必须使用发生错误时的
`expected_last_event_hash`。不得 fresh rebase 后给已推进槽追加失败。

非 Mapping capture、非法/empty slot id/time/worker、plan/build/event-root 不可信、replay
损坏或无法绑定合法 slot 的输入只返回固定错误，事件写入为 0；不伪造
`invalid-slot` 失败事件。

## 9. Projection invariants

`replay_challenger_replacement_runtime(event_root, plan, build_identity)` 必须：

- 从 sequence 1 开始连续，无 gap/duplicate；
- previous-event hash 链、plan hash、build hash 和 root identity 逐 event 一致；
- 任一时刻最多一个 active slot；
- 每个 slot 仅允许三阶段或在 INPUT/RESULT 后进入失败终端；
- terminal 后任何同 slot event 都是 `STATE_EVENT_INVALID`；
- 不同 slot 不得交错；
- INPUT/RESULT/SUCCESS payload exact key set 、base64、SHA、sequence/hash binding 逐项重验；
- source/decision exact bytes 在 replay 时重跑 semantic loader；
- 已完成 slot 的 scheduled time 严格 4h 连续；
- 返回 `last_event_hash`、`next_sequence`、active slot、completed count、failed count、
  next required slot 和 orphan staging 统计；
- 若存在 canonical final，内容/父链全部验证后、最终 root validate 前，对
  retained dirfd `fsync` 一次，以确认 rename 后/dir-fsync 前 crash durability。

任何不受信事件使整个 projection 失败，不得跳过、截断、修复或挑选较好链。

## 10. Runtime API 与并发

### 10.1 构造器

```python
ChallengerReplacementRuntimeState(
    event_root: ChallengerReplacementEventRoot,
    plan: Mapping[str, Any],
    build_identity: Mapping[str, Any],
)
```

禁止 path、output root、fault callback、storage adapter、network client 或 Broker。build identity exact keys：

```text
release_tag, peeled_commit, package_version, manifest_version,
build_input_tree_hash, manifest_hash, manifest_file_sha256
```

### 10.2 Append

`append(..., expected_last_event_hash=token)` 每次先 fresh replay。若当前 hash 不等于调用者
依据的 token，在构建 event 前固定返回
`CHALLENGER_REPLACEMENT_EVENT_SEQUENCE_CONFLICT`。状态层不暗中重试、rebase 或挑选
winner。

两个 worker 从同一 projection 先后 append，只有第一个可成功；第二个在构建
event 前冲突。两个进程同时到 no-replace 边界时，同 event 结果为
`{COMMITTED, ALREADY_COMMITTED}`，不同 event 为 `{COMMITTED, CONFLICT}`，且只留一个
canonical inode。

### 10.3 Slot orchestration

```python
run_challenger_replacement_slot(
    *, state, capture, observed_at, worker_id
) -> Mapping[str, Any]
```

入口先验证 capture 为 Mapping，slot id/observed_at/worker 为合法非空值。
每个阶段都使用刚 replay 得到的 token：

1. 新 slot：构建 exact source，append INPUT；
2. INPUT active：使用 INPUT event 冻结的 recorded_at/source bytes 构建 decision，
   append RESULT；
3. RESULT active：不重算 source/decision，只重放 exact bytes 并 append SUCCESS；
4. 已 succeeded 的同 slot retry：只 replay 并返回，source build、decision compute、
   event create/write 计数全为 0；
5. 存在其他 active slot 时，新 slot 返回 `ACTIVE_SLOT_CONFLICT`，不污染原 slot。

`_fail_slot` 仅能用错误发生时的 token。sequence conflict 原样上抛，不转成 slot
failure。

## 11. Crash/replay 表

| crash point | durable facts | fresh-process 行为 |
|---|---|---|
| staging create 前 | 无新 final | 重建同 event |
| partial staging write | orphan staging only | 忽略内容，重建同 event |
| file fsync 前/失败 | orphan staging only | 不得成功；重试发布 |
| no-replace 前 | complete staging only | 重建同 event |
| final visible, dir fsync 前 | exact final | replay/retry 补 dir fsync + root validate |
| dir fsync 后，返回前 | durable exact final | `ALREADY_COMMITTED` |
| INPUT 后进程退出 | INPUT final | 用冻结 source/time 构建 RESULT |
| RESULT 后进程退出 | INPUT+RESULT finals | 零重算 append SUCCESS |
| SUCCESS 后进程退出 | terminal chain | 纯 replay 返回 |

只有 canonical final 完整内容、父链和 directory durability 全部通过才可报告成功。

## 12. 测试策略

### 12.1 Event storage

- root/slot directory identity replacement；
- final/staging symlink、hardlink、extra-link、FIFO、socket、directory、wrong mode/uid；
- short write、EINTR、read/fstat/lseek/stat/write/fsync/close OSError；
- 主异常与 close 异常共存时保留主 reason 并记录 close 诊断；
- 1、`2^53-1` 合法，`2^53` 和 `10^20` 在 I/O 前拒绝；
- rename 后 dir fsync 前 crash，replay-only fresh interpreter 补 durability；
- multiprocessing 真实同 event/不同 event 竞争；
- orphan staging 统计但不读为业务状态；
- 所有拒绝路径的外部 sentinel bytes/mode/size/mtime_ns/ctime_ns/inode/nlink 不变。

### 12.2 Documents/decision

- genesis 与第二槽；
- 21 bars，20-bar overlap，strict +4h；
- previous decision 不得在 genesis 后为 null；
- plan/build/source/decision hash 篡改；
- float、duplicate key、noncanonical bytes、无限/非正 decimal；
- minimum hold、same-slot SMA exit、vertical exit 和 rejected entry 冻结语义。

### 12.3 Runtime

- exact three-stage happy path；
- 第二槽从 replayed previous source/decision 构建；
- 每个 crash point 的 fresh state/capability retry；
- success retry 的 build/compute/event-write 计数为 0；
- 两个 state 先读同 token 后顺序 append：一个成功、一个 conflict；
- 不同 slot 交错、terminal 后 event、wrong SUCCESS binding 皆 invalid；
- invalid capture 零 event；active-other-slot 零污染；
- 不生成 `.sqlite`、`-wal`、`-shm`、source/decision authority file；
- 静态扫描四模块：无 `sqlite3`、SQL/PRAGMA/WAL/SHM、`fault_injector`、
  scheduler/deployment/Runner/Broker/order/UI/network API；
- production root/plist/service 在测试前后均不存在/未加载。

## 13. 发布门

v0.66 候选必须：

1. 从 annotated `v0.65.1` exact peeled commit 的隔离 worktree 开发；
2. 每个功能/修复先 RED，再最小 GREEN；
3. focused/adjacent tests、compileall、diff-check、`make validate` 通过；
4. 四生产模块总行数 `<2743`；
5. 独立完整审查一次，Critical/Important 清零；修复后只针对性复审；
6. 最终未变代码状态本地全量测试一次；
7. 公开 Draft PR 的 Python 3.9/3.12 与 macOS arm64 CI 通过；
8. squash 合并后 main CI 通过；
9. annotated `v0.66.0` tag object 的 peeled commit 与 origin/main 精确一致。

发布状态只能是 `RUNTIME_RELEASED_NOT_INSTALLED`。它不授权安装/启动，不证明
90 天 Paper 已开始，不证明盈利、AI 优势、Canary 或实盘资格。

## 14. 旧未发布工程的处理

`codex/v0.64-replacement-runtime@67a65d5` 仅是未发布工程审计，不是 release
ancestor 或事实源。处理规则：

- 可保留：canonical event codec、retained root、no-replace publication、replay durability
  及其安全测试，但必须在 v0.65.1 基线重新审查；
- 可保留：纯 source/decision 语义，但必须改为 v2 plan validator；
- 必须删除：`SOURCE_BUNDLE_PUBLISHED`、`DECISION_PUBLISHED`、output-root、
  path publisher/recovery、publication record 与 artifact authority；
- 必须删除：SQLite/WAL 历史、lease/claim 和任意 fault injection API；
- 不对旧分支 rebase/改写/删除，保留其审计价值。
