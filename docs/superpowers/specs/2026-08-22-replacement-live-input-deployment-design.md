# Replacement Challenger Live Input and Deployment Candidate Design

日期：2026-08-22
目标版本：`v0.67.0`
状态：设计候选；仅代码、测试与不可变候选 artifact，禁止安装和启动
权威基线：annotated `v0.66.0`，tag object
`3b7ee80d0b6eb5e57934bd5b6cecf837e0a562d6`，peeled commit
`12d835807580fb118f17942cd6a568e6b37818e3`

## 1. 问题与目标

v0.66 发布了 capability-safe append-only event log 和三阶段 runtime，但它的
source bundle 明确固定为：

```text
TEST_FIXTURE_ONLY_NOT_COHORT_EVIDENCE
```

而且输入由调用者传入，runtime 自身只验证
`network_request_count_observed_by_runtime=0`。因此 v0.66 证明了状态机、崩溃恢复和
证据封装的工程性质，不提供真实公开行情 acquisition，也不具备启动 90 天/540 槽
confirmatory cohort 的资格。直接为 v0.66 安装 LaunchAgent 会制造一个运行中的
fixture 系统，不能生成冻结计划要求的研究证据。

v0.67 的目标是闭合这一缺口，同时保持系统最有价值的边界——证据可信与失败关闭：

1. 新增 replacement 专用、凭据为零、固定 public GET 的 live input adapter；
2. 把成功 acquisition 的 exact request/response/time evidence 纳入 cohort-qualified
   source bundle，并逐字节进入 v0.66 event authority；
3. 新增无任意业务参数的自然槽 runtime CLI；
4. 生成固定 deployment artifact、LaunchAgent plist 和只读 machine preflight；
5. 所有产物仍是代码级候选，不安装、不 bootstrap、不 kickstart、不运行自然槽。

v0.68 才实现并执行受限 installer、只读 observer 和 first-natural-slot start receipt。
90 天计时只能从 v0.68 的真实 start receipt 派生，不能从 v0.67 tag、preflight、安装时间
或测试 fixture 派生。

## 2. 冻结权威

### 2.1 v2 research plan

唯一 plan：

- path：`artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json`；
- file SHA-256：
  `5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f`；
- plan id：
  `challenger_replacement_plan_65d85d60a534a917f45a1ffa5fc9d3f74d6d24995b900d31b8c73cd26f0bd97b`；
- plan hash：
  `c9a1e5f74c52fbf23be5a1d27fd23c25f3601ed58133178fc25480391ab65705`；
- status：`PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED`。

v0.67 不修改 plan bytes、plan hash、研究 scope、decision policy、540 槽、90 天、
predecessor failure、无 backfill、无 optional stopping、尾部前经济盲法或任何资金权限。
plan 中 `authority.market_request_count=0` 和 `state_write_count=0` 是 plan/supersession
冻结时的已观察事实，不被误读为未来合格 Runner 永远不能执行 plan 明确需要的公开行情
GET。未来每槽网络上限由本设计的 versioned acquisition contract 单独冻结。

### 2.2 v0.66 release foundation

v0.67 必须绑定以下完整 foundation，而不是只比较版本字符串：

- release tag：`v0.66.0`；
- tag object：`3b7ee80d0b6eb5e57934bd5b6cecf837e0a562d6`；
- peeled commit：`12d835807580fb118f17942cd6a568e6b37818e3`；
- package version：`0.66.0`；
- manifest version：`1.60.0`；
- manifest file SHA-256：
  `bff44edf8dd6025ad4683293380458d08e85e9b0f47377844dc5a86614e48ed6`；
- build input tree hash：
  `f22df35dd1a2c9dbf0885406fa5f8f7f6167efde1ac9a4e71049bc2c01ea86ae`；
- manifest hash：
  `c2f2288a69c2e370c62db2d58db9a241023f5c8edce87905d5d5e74d11e9fe3e`；
- main CI run：`32554406969`，Python 3.9、Python 3.12、macOS 15 arm64
  均为 `success`。

v0.67 release artifact 不反向包含尚未知的 v0.67 merge commit，避免 self-reference。
它冻结预期 `release_tag=v0.67.0`、package/build manifest identity 和完整 input tree。
最终 peeled commit 由 PR/main CI、annotated tag 与未来 v0.68 install receipt 正向绑定。

## 3. 方案选择

### 3.1 采用：replacement-specific adapter + 两阶段发布

v0.67 复用已审查的纯 HTTP、strict JSON、clock probe 和 descriptor 原语，但新增的公开
接口全部是 replacement-specific。网络 adapter 只输出一个冻结 `LiveCapture`；三阶段
runtime 仍是唯一状态写入者。deployment 只消费 v0.67 exact build identity。

优点：事实源单一、组件边界清楚、能在安装前完整测试；不会把旧 Challenger state、
System Paper SQLite 或通用交易引擎带入新 cohort。代价是安装/observer/start receipt
顺延到 v0.68，但每个版本均有独立、可审查的语义结果。

### 3.2 拒绝：单版本塞入 acquisition + install + observer + start receipt

该方案把网络、状态、launchd、安装事务和证据观察同时引入一个变更，故障面过大，难以在
一次审查中证明无越权和无事实源分叉，也会鼓励为赶启动窗口压缩 TDD。

### 3.3 拒绝：直接复用旧 Challenger Runner/SQLite/LaunchAgent

旧实现绑定旧 label、旧 roots、旧 state 与已永久失败 cohort。即使纯 parser 可按接口复用，
旧 orchestration、state、`_START`、artifact publisher 和 service identity 均不得成为
replacement authority。

## 4. 范围

### 4.1 v0.67 包含

- cohort-qualified replacement live-capture receipt/schema/strict loader；
- 固定 3 次 Binance server-time probe 加最多 3 次同一 kline 请求的 bounded adapter；
- cohort source bundle schema v2 与 decision schema v2；
- live slot CLI，从 verified clock 和 event projection 自动派生唯一 slot；
- v0.66 event log 与三阶段 runtime 的最小升级，不新增第四状态阶段；
- 固定 deployment artifact、plist renderer、production loaders；
- 只读 preflight 与 candidate receipt builder/loader；
- offline fixtures、HTTP failure matrix、fresh-process recovery 和静态安全门；
- v0.67 ADR、实施状态、build manifest、公开 PR/main CI 和 annotated tag。

### 4.2 v0.67 不包含

- 创建 `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1`；
- 写 `/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist`；
- `launchctl bootstrap`、`kickstart`、`start`、自然 Runner 或 production event 写入；
- install receipt、observer receipt、start receipt 或 90 天起点；
- credentials、API key、账户、余额、Broker、订单、资金或真钱；
- archive、PnL、收益率、胜率、rank、power、提前 PASS 或 evaluator；
- 通用 exchange adapter、通用 scheduler、通用 deployment framework、模拟 Broker 或 UI；
- 修改、迁移、删除、补写或回填旧 cohort 与 System Paper 的任何证据。

## 5. 组件边界

```text
Verified local clock + fixed public HTTPS
                 │
                 ▼
ReplacementLiveInputAdapter
  3 x /api/v3/time + 1..3 x /api/v3/klines
                 │ exact LiveCaptureReceipt bytes
                 ▼
cohort source-bundle v2 builder
                 │ exact source bytes
                 ▼
v0.66 three-stage runtime
 INPUT -> RESULT -> SUCCESS
                 │
                 ▼
append-only canonical event log (sole authority)
```

Deployment artifact、plist、preflight 只定义和验证如何调用这条链；它们不是行情、decision
或 cohort state 的事实源。未来 exports 仍是可重建派生物。

YAGNI 硬门：v0.67 新增或净增加的 Python 生产代码不得超过 1,800 physical lines；建议预算
为 live adapter 500、v2 document semantics 300、CLI 250、deployment/loader 500、preflight
250。不得复制 `system_paper_install.py`、旧 Challenger Runner 或通用 deployment framework
来消耗预算。超过上限时先删除重复 codec/path/command 逻辑或把 v0.68 范围移出，不能以
“以后再精简”继续发布。

## 6. Live input acquisition contract

### 6.1 固定网络面

只允许 HTTPS `GET`，无 request body、Cookie、Authorization、API key 或代理：

```text
host = data-api.binance.vision
time path = /api/v3/time
kline path = /api/v3/klines
symbol = ETHUSDT
interval = 4h
limit = 21
endTime = scheduled_for_epoch_ms - 1
```

URL query 使用字节序稳定排序。自定义 redirect handler 拒绝所有 redirect；
`ProxyHandler({})` 禁止读取环境代理。最终 URL、host、scheme、status、content type 和最大
body 均重验。连接/读取 timeout 每请求 15 秒。

每次自然 invocation：

- server-time probe 恰好 3 次；任一 probe 失败则本次 acquisition 失败；
- kline 最多 3 次，仅 transport error、HTTP 408/425/429/500/502/503/504 可重试；
- retry delay 固定为 `1s, 2s`，总 acquisition 必须在 slot 后 10 分钟内完成；
- HTTP 200 的 malformed/noncanonical/semantic-invalid body 永不重试；
- 最大 public request count 为 6，成功 receipt 记录每次 attempt；
- production API 不暴露 URL、host、retry、clock、sleep 或 transport override。

测试只 patch 私有 `_open_public_request`、`_monotonic` 和 `_sleep` 边界；不得新增
production callback/fault-injector/config seam。

### 6.2 时间和 slot 派生

server-time 三样本通过现有 verified clock policy：固定最大 RTT、offset spread 和本地
wall/monotonic 一致性门。adapter 不接受 `scheduled_for`、sequence 或 slot ID CLI 参数。

它从 strict event projection 派生：

- event log 为空：取 verified Binance time 之前最近一个完整 4h 边界作为 genesis；
- 已有 success：唯一候选为 projection 的 `next_required_slot.scheduled_for`；
- active slot：只允许恢复同一 slot，不发起新 acquisition；
- failed stream：永久失败，不再请求网络；
- 已有 success 后候选早于当前最近完整边界：固定 continuity gap，禁止旧 kline GET；
- 当前时间未进入 `[scheduled_for+2m, scheduled_for+10m]`：不请求 kline，失败关闭。

genesis 可在任一未来自然槽开始，因为 plan 的 start source 是 first verified natural slot。
首个 success 后，任何漏槽不得通过选择新 genesis、回退 `endTime` 或人工参数恢复。

### 6.3 LiveCaptureReceipt

新增 `challenger-replacement-live-capture-v1.schema.json`。canonical receipt 至少包含：

```text
schema/version/id/self-hash
plan id/hash
v0.67 build identity
evidence_qualification = REPLACEMENT_CONFIRMATORY_COHORT_INPUT
slot id/sequence/scheduled_for/captured_at
clock probe exact normalized records + trust hash
kline request exact method/url/request id
all attempts: started/received time, status/final URL/selected headers/body SHA/body bytes
selected_success_attempt_index
normalized 21-bar rows + each normalized row hash
network_request_count
credentials/broker/order/account counts = 0
```

response body 最大 256 KiB，receipt 最大 2 MiB。JSON duplicate key、float、NaN、unknown
field、noncanonical time/decimal/bytes、hash mismatch、wrong row count、wrong last close、future
availability、20-bar overlap revision 全部拒绝。

receipt exact bytes 只存在于 source bundle v2 payload 中；不创建独立 live receipt 权威文件。
HTTP attempt headers 只保留 `Date`、`ETag`、`Last-Modified`、`Retry-After`，不得记录
Cookie、Authorization 或任意响应 header。

## 7. Cohort source and decision documents

### 7.1 Schema versioning

新增：

- `challenger-replacement-source-bundle-v2.schema.json`；
- `challenger-replacement-decision-v2.schema.json`。

v1 fixture schema/loaders 保留用于重放 v0.66 tests，但 production live CLI 只接受 v2。
不得把 v1 的 qualification 原地改名，避免旧 fixture bytes 被重新解释为 cohort evidence。

source v2 固定：

```text
evidence_qualification = REPLACEMENT_CONFIRMATORY_COHORT_EVIDENCE
live_capture_receipt = exact validated receipt object
network_request_count_observed_by_core_runtime = 0
```

source v2 的 normalized klines 必须逐项等于 receipt 的 normalized rows。source self-hash、
plan/build/slot/parent identity 和 20-bar overlap 重新验证。decision v2 只改变 source schema/
build/qualification binding，不改变冻结 SMA20/momentum/hold/exit policy。

### 7.2 Event authority

事件 codec 和三阶段名称不变。`INPUT_PREPARED` payload 继续保存 exact source bytes；其
`capture_sha256` 变为 exact LiveCaptureReceipt bytes SHA-256。v0.67 runtime production path
要求 source v2，fixture-only API 在生产 CLI 不可达。

fresh-process recovery：

- INPUT 已提交：零网络，重放 embedded source 后继续 decision；
- RESULT 已提交：零网络、零 decision compute，继续 SUCCESS；
- SUCCESS 已提交：零网络、零 compute、零 append，返回 replayed result；
- 网络成功但 INPUT 未提交即崩溃：没有 durable state，fresh invocation 仅在同一 10 分钟
  window 内重新 acquisition；不得收养进程内存或临时外部文件；
- INPUT publish 的 staging orphan 仍按 v0.66 协议统计但不读取为业务状态。

## 8. Natural slot CLI

新增固定 module entry point：

```text
python -m crypto_quant.challenger_replacement_live_runtime_cli
```

production invocation 不接受业务参数。它只从固定 deployment contract 派生：plan、build
manifest、event-root identity、service label、runtime root 和日志路径。环境变量白名单仅为
`PYTHONPATH` 与 launchd 注入的 `XPC_SERVICE_NAME`；发现代理、credential-like 环境变量或
不匹配 service identity 即在网络前拒绝。

CLI stdout 只有一行 canonical、无经济数据的 summary：status、slot id、scheduled_for、
terminal stage、event count、next required slot 和固定 reason code。stderr 只允许单行固定
reason code；不得打印 HTTP body、环境、路径外内容、PnL 或 secret-like value。

CLI 仅有三个退出类：

- `0`：exact success 或 exact already-succeeded replay；
- `75`：窗口内 transient acquisition 未完成，且没有 durable INPUT；
- `1`：永久 contract/continuity/state/evidence failure。

v0.67 测试可以通过内部 Python API 注入 fixture capability；正式 CLI 不提供 `--path`、
`--date`、`--slot`、`--url`、`--fixture`、`--retry` 或 `--force`。

## 9. Deployment candidate

### 9.1 固定 identity 和路径

deployment artifact 与 plan 完全一致：

```text
service label = local.crypto-quant.challenger-replacement-v1
service identity = gui/501/local.crypto-quant.challenger-replacement-v1
runtime root = /Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1
event root = <runtime>/state/challenger-replacement-events-v1
stdout = <runtime>/log/challenger-replacement.stdout.log
stderr = <runtime>/log/challenger-replacement.stderr.log
target plist = /Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist
```

所有 old Challenger/System Paper roots、labels 和 artifacts 永久禁止。deployment artifact
绑定 v2 plan、v0.66 foundation、v0.67 expected build identity、固定 source file allowlist、
runtime CLI、network contract、plist bytes hash 和所有 owner-only paths。

### 9.2 LaunchAgent candidate

plist 固定：

- `RunAtLoad=false`、`KeepAlive=false`、`ProcessType=Background`；
- `StartCalendarInterval` 为 Asia/Shanghai 的 00/04/08/12/16/20 时、minute 2；
- ProgramArguments 只能是私有 immutable snapshot Python 和无参数 module entry point；
- WorkingDirectory 为私有 immutable snapshot；
- stdout/stderr 使用 plan 固定路径；
- 无 sockets、MachServices、WatchPaths、QueueDirectories 或 network proxy env；
- umask `077`，固定 PATH，不继承用户 shell 初始化；
- 不调用 shell、`launchctl`、installer 或维护程序。

plist renderer 100 次输出 exact bytes。loader 从 contract 重建期望 plist 并逐字比较；
不信任 plist 自报字段。

### 9.3 Code-only publication

v0.67 Git 只发布：

- deployment schema/package mirror；
- deterministic deployment artifact；
- reviewed plist candidate；
- production loaders；
- preflight code和fixture receipts。

它不在用户 Library 下发布文件。Git artifact publication 使用仓库内普通 commit，不把
Git publisher 当作 production install primitive。

## 10. Read-only machine preflight

preflight 只读验证并返回 canonical candidate receipt bytes；v0.67 release 时只运行 fixture
和临时目录测试，不执行真实 production preflight receipt publication。

目标 Mac 门至少包括：

- Darwin arm64、当前 UID=501、HOME=`/Users/chenm4`；
- Python 3.9/3.12 policy 与 exact executable device/inode/hash；
- timezone `Asia/Shanghai`、NTP/system clock health、3-sample Binance offset；
- repo public origin、ADMIN、clean exact annotated `v0.67.0`；
- package/build manifest/deployment artifact/plist exact replay；
- old failed service remains decommissioned；
- replacement runtime root、target plist、service 当前不存在且未加载；
- owner home/Library/LaunchAgents ancestor type/uid/mode/symlink safety；
- disk free/inode budget、sleep/power assertions、network DNS/TLS/public endpoints；
- credentials/Broker/account/order capability absent；
- `production_activation=false`、`runtime_install_authorized=false`、
  `replacement_start_authorized=false`、`real_orders_allowed=false`。

preflight 最多执行固定只读 commands 和本节允许的 public GET；不创建 runtime root、plist、
event、receipt、log 或 temporary file outside a caller-provided test root。CLI 正式 receipt
publication 留到 v0.68 install ceremony。

当前 absence 只能表述为 `NO_OBSERVABLE_REPLACEMENT_INSTALLATION_AT_COLLECTION`，不证明
历史从未安装。v0.64 accountable owner attestation 与 Git history 继续作为治理 provenance；
preflight loader 不声称用代码证明历史否定事实。

## 11. 安全与失败关闭

### 11.1 Path/I/O

所有 production loader 使用 retained descriptor、`O_NOFOLLOW|O_NONBLOCK`、regular type、
uid、mode、nlink、size-before-read、device/inode attachment 和 bounded read。缺少
`O_NOFOLLOW`/`O_DIRECTORY`/`O_NONBLOCK` 的支持平台固定 UNSUPPORTED，不以 `0` 降级。

不可信 existing path 永不 chmod/覆盖/删除。任何 publisher 都使用 same-directory nonce
staging、same-fd readback、file fsync、platform-proven atomic no-replace、dir fsync；禁止直接
写 canonical final。v0.67 不新增 production-root publisher。

### 11.2 网络

网络错误不得 append INPUT、RESULT、SUCCESS 或 failure event。只有通过完整 clock、HTTP、
schema、semantic 和 overlap 验证的 receipt 才能进入 runtime。active/terminal/conflict state
在任何 GET 前 replay；不需要网络时 request count 必须为 0。

### 11.3 权限

部署 artifact、plist 或 UI 没有交易授权能力。任何未来安装也不能改变：

```text
production_activation = false
credentials_allowed = false
broker_requests_allowed = false
account_requests_allowed = false
real_orders_allowed = false
```

## 12. 测试和可证伪验收

### 12.1 Acquisition

- exact 3 time + 1 kline happy path；
- kline transient 两次后第三次成功，exact request count=6；
- malformed 200、redirect、wrong host/path/query/status/content-type、oversize、timeout、TLS、
  duplicate key、float、bad row/hash/window 全部固定失败；
- credentials/proxy environment 在第一请求前拒绝；
- pre-window、post-window、active、terminal、failed 和 continuity gap request count=0；
- 同一 receipt 100 次 canonical bytes 完全一致；
- secret scan 证明 receipt/log 不含 header/token/cookie/env leakage。

### 12.2 State/recovery

- cohort v2 genesis 和第二槽完整三阶段；
- source v1 fixture 永远不能被 production CLI 当 cohort evidence；
- INPUT/RESULT/SUCCESS 各 crash boundary fresh-process replay；
- INPUT 已存、RESULT 已存、SUCCESS 已存的 retry network count 均为 0；
- success 后漏一个 4h slot 固定 continuity failure，禁止请求旧日期或新 genesis；
- symlink/hardlink/FIFO/socket/wrong uid/mode/size/inode replacement 无越界副作用；
- exact event log 是 observer/evaluator 的唯一输入，exports 不存在仍可完整 replay。

### 12.3 Deployment/preflight

- contract/plist 100 次 exact；schema mirrors byte-equal；
- fixed label/root/path/schedule/module args，任意 override 不存在；
- old/System Paper paths、SQLite、Broker/order/credential imports 静态拒绝；
- preflight 在 production-root absence fixture 前后 file tree exact unchanged；
- launchctl/network/subprocess 调用严格等于合同允许次数；
- Linux Python 3.9/3.12 运行纯合同与 loader tests；macOS arm64 job 运行 Darwin plist、flags、
  no-replace 与 target-machine preflight fixture tests；
- package/build manifest、README、ADR、status 和 exact release fixture 全部一致。

### 12.4 发布门

- 每个 TDD task 先精确 RED，再最小 GREEN；
- affected focused/adjacent tests；
- 最终代码状态本地 full suite 一次、compileall、make validate、diff-check；
- 独立完整审查一次，Critical/Important 清零；修复后只针对性复审；
- public Draft PR，Python 3.9/3.12 和 macOS arm64 PR CI；
- merge 后 main CI；
- annotated `v0.67.0` tag object 和 peeled commit 与 origin/main 精确一致。

同一未变化提交不在同一机器重复 full suite；无代码变化不重复整分支审查。

## 13. v0.68 handoff

v0.67 全部发布门通过后，v0.68 另行冻结：

1. owner-only immutable source snapshot；
2. exact preflight receipt publication；
3. atomic installer、install receipt 与 rollback；
4. bootstrap-only-no-run 证明；
5. 一次只读 launchctl/event/log observer；
6. 只有首次自然 `SLOT_SUCCEEDED` 才 no-overwrite 发布 start receipt；
7. 从 start receipt 自动派生 90 天/540 槽窗口。

若 v0.67 未通过 acquisition、recovery、supply-chain、CI 或安全门，v0.68 不得安装。

## 14. 对赚钱目标的意义

v0.67 不证明盈利，也不证明 AI 优势。它把真实公开输入、固定研究规则和唯一可重放状态链
连接起来，使未来 90 天结果能够回答“冻结策略在真实时间、真实公开行情和保守证据约束下
表现如何”，而不是回答“fixture 能否通过测试”。只有完整 540 槽、冻结 evaluator 和真实
PASS 才能进入极小资金 Canary 的讨论；DID_NOT_PASS 或 INCONCLUSIVE 同样是完整、必须保留
的研究结果。
