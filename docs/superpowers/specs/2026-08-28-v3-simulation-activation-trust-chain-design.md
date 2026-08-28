# Replacement v3 Simulation Activation Trust Chain Design

日期：2026-08-28  
目标版本：`v0.78.0`  
基线：annotated `v0.77.0` / `39a973d51bdc8fc957a65052f4bb5f310a1f72c3`  
适用分支：`codex/v0.78-v3-simulation-activation-design`

## 1. 决策摘要

v0.78 只发布 replacement v3 的模拟安装与自然启动信任链代码。它不在代码
发布期间创建 production root、渲染真实 snapshot、执行网络 preflight、安装
plist、调用 `launchctl bootstrap`、启动 runtime、创建 install/start receipt，
也不开始 72 小时或 90 天计时。完成状态固定为
`V3_SIMULATION_ACTIVATION_TRUST_CHAIN_CODE_RELEASED_NOT_INSTALLED`。

v0.76 已冻结公开行情模拟 runtime、v3 deployment/start receipt builder、72 小时
qualifier 和 90 天 evaluator；v0.77 已冻结私有 Binance/Canary 代码，但保持关闭。
当前缺口是 v0.76 deployment 明确不可安装，且
`challenger_replacement_v3_runtime._load_fixed_runtime_sources()` 固定失败。v0.78
补齐 replacement-specific installed adapter、release-bound snapshot/contract、
preflight、installer、observer 与 start-receipt publisher。它不扩建通用 deployment、
scheduler、Broker、交易所适配或 UI。

代码 tag 必须先发布，真实 ceremony 才能绑定该 tag/main/CI 构建 snapshot。代码发布
与运行 receipt 不得进入同一个 tag，避免循环信任。

## 2. 采用方案和拒绝方案

### 2.1 采用：薄型 v3-specific trust chain

v0.78 保留 v0.69 已冻结的 replacement service/runtime root，并把它与旧失败的
`challenger-forward-v1` 隔离：

- service：`gui/501/local.crypto-quant.challenger-replacement-v1`；
- runtime root：
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1`；
- target plist：
  `/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist`。

名字中的 `v1` 是 replacement production-root identity，不是旧 540 槽研究计划。
v3 DecisionOpportunity、v0.75 72 小时和 v0.74 90 天合同由 plan/deployment/hash
绑定；为了改名再做一次 plan supersession 没有安全收益，因此不做。

### 2.2 拒绝：直接复用 v0.68 installer

v0.68 installer 强绑 v2 plan、旧 `SLOT_SUCCEEDED` 首槽语义和 540 槽 receipt。
复用会让 v3 runtime 由错误事实源授权，因此拒绝。只允许复用已经有独立安全测试的
private descriptor/no-follow/bounded-read/no-replace/fsync primitives；不得复用 v0.68
public builder/loader 伪装成 v3 contract。

### 2.3 拒绝：手工 Runner、kickstart 或常驻 shell

手工调用会改变自然机会起点，无法证明四小时调度和 fresh-process recovery。安装器
禁止 `kickstart/start/enable/submit`，只允许固定 bootstrap；首个事件必须由
`StartCalendarInterval` 自然产生。

### 2.4 拒绝：把 Binance 私有 adapter 接进模拟服务

72 小时生产模拟只允许公开 ETHUSDT GET。v0.77 的 credential/private transport/
order path 不进入 snapshot ProgramArguments 或 environment。真实 Binance ceremony
和 E0 是后续独立不可逆动作，不是 v0.78 范围。

## 3. 不可变安全边界

- `production_activation=false`；
- `credentials_allowed=false`、`account_requests_allowed=false`；
- `real_orders_allowed=false`、`fund_movement_allowed=false`；
- 只允许 v0.76 contract 中冻结的公开 ETHUSDT market GET；
- append-only canonical event log 是唯一权威；exports、日志和 UI 都不是；
- 不迁移、删除、重置或写入旧 `challenger-forward-v1` 证据；
- 不修改 v0.64/v0.69/v0.74/v0.75/v0.76/v0.77 artifact bytes；
- 不读取或展示 pre-tail 单笔/累计经济结果；
- v0.78 release 的 production-root/network/launchctl/state/order/fund 计数均为 0。

安装授权在 contract 中只表示“允许一次固定 plist bootstrap”，不表示策略生产激活，
更不表示私有交易授权。

## 4. 发布基础身份

v0.78 必须冻结并测试：

- repository：`cjl308868584-lang/crypto-quant-core`；
- visibility：`PUBLIC`；
- annotated tag：`v0.77.0`；
- tag object：`f4a40105ec67f6823229a526542dc6d29fac5394`；
- peeled commit/main：`39a973d51bdc8fc957a65052f4bb5f310a1f72c3`；
- tree：`af01967aa7345035cd40e306655be67b492242b2`；
- package：`0.77.0`；
- manifest version：`1.71.0`；
- manifest hash：
  `91ca11c6759eaab7727b0d003b5d35debd5566d2e7a9750ac06f0e0db958f302`；
- manifest file SHA-256：
  `7bf6488b3c4428a3497ee0a9e2ad5c68ac9fb5021fb8b1166de5c855dafccdb3`；
- build input tree hash：
  `63a57f7f5ef132efa0f565f5edd1f3621cca14015aea9c315eab3d5bc155f3de`；
- main CI run：`33145885379`，Python 3.9、Python 3.12、macOS arm64
  全部 `success`；
- v0.76 deployment artifact SHA-256：
  `28eec0ee5f424952ee96e0c711abc68d7d1cab592859515ba8f79958971d288b`；
- v0.77 fault receipt SHA-256：
  `0223b124515dc4b1ce688e2681b31cc3f596be0575a09c91641584aaf8eba4f9`。

v0.78 代码不得硬编码尚不存在的 v0.78 merge/tag object。发布后的 renderer 从
固定 repo checkout 验证 `HEAD == origin/main == v0.78.0^{}`、annotated tag、clean
worktree、package/manifest 和 exact main CI 三 job，随后把这些事实写入 owner-only
install contract。未来身份不反向进入 v0.78 Git manifest。

## 5. 固定 production 路径

production CLI 不接受 path override。固定路径为：

- runtime root：
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1`；
- deployment root：`<runtime>/deployment-v3`；
- snapshot root：`<deployment>/snapshots/<snapshot-tree-hash>`；
- contract：`<deployment>/challenger-replacement-v3-install-contract-v1.json`；
- candidate plist：`<deployment>/local.crypto-quant.challenger-replacement-v1.plist`；
- preflight receipts：`<deployment>/preflight-receipts`；
- install receipts：`<deployment>/install-receipts`；
- event root：`<runtime>/state/challenger-replacement-events-v1`；
- start receipts：`<runtime>/evidence/v3-start-receipts`；
- stdout/stderr：沿用 v0.76 deployment 的两个固定 log path；
- target plist：`~/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist`。

`deployment-v3` 与 v0.68 未执行的 `deployment` 路径分开，避免旧 contract/staging
被误当成 v3 authority。runtime/state/evidence/log/deployment 目录固定 `0700`，普通
文件固定 `0600`。所有边界拒绝 symlink、hardlink、FIFO、socket、wrong owner/mode、
same-bytes-new-inode 和验证后替换。

真实 renderer 只在整个 runtime root 不存在且 service/plist 未加载/不存在时安全创建
上述 owner-only tree。发现任何既有 replacement production object 即失败关闭，不进行
“修复”、chmod、删除、迁移或覆盖。

## 6. Snapshot、contract 和 candidate plist

### 6.1 Snapshot

snapshot inventory 是 v0.76 deployment `strategy_inventory` 的 exact key set，加上
v0.78 新增的 installed-adapter/trust-chain 模块、CLI 和直接 schema/resource 闭包；每一项
都必须存在于 v0.78 release manifest 且 bytes/hash 相等。renderer 不自行扫描，也不复制
v0.77 private credential/protocol/order/Canary 模块。上限为 256 文件、单文件 4 MiB、
总计 64 MiB。源和目标都以 retained dirfd、`O_NOFOLLOW`、bounded read 和 attachment
revalidation 处理。系统 Python、`jsonschema` 版本和 import closure 由 contract 的新进程
transcript 固定，ceremony 不执行依赖安装或下载。

发布协议是同目录 nonce staging：新 fd `O_EXCL|O_RDWR|O_NOFOLLOW`、short-write/EINTR
循环、same-fd readback、file fsync、目录 fsync、Darwin
`renameatx_np(RENAME_EXCL)` / Linux `renameat2(RENAME_NOREPLACE)`、parent fsync、
完整 replay。缺 symbol/flag/kernel 支持固定 `PLATFORM_UNSUPPORTED`，禁止降级为
`os.rename`、`os.replace` 或直接写 final。

orphan staging 不是权威。renderer 不删除、不修改、不把它当成功；封存 stat/name 后
失败关闭并要求独立 incident recovery。

### 6.2 Install contract

contract 必须绑定：

- v0.77 predecessor 与未来 v0.78 release/main/tag/CI/manifest；
- v0.69 plan、v0.74 economic plan、v0.75 accelerated plan；
- v0.76 deployment exact bytes/id/hash；
- snapshot inventory/tree/root identity；
- event root/start/log/deployment root identities；
- Python executable identity、版本和 clean isolated import transcript；
- service、schedule、ProgramArguments、environment、plist bytes/hash；
- public endpoint allowlist、clock policy和所有 authority false/zero；
- first eligible natural opportunity derivation rule。

contract 状态为 `V3_SIMULATION_INSTALL_CONTRACT_VERIFIED_NOT_INSTALLED`，其中
`runtime_install_authorized=true` 只授权固定 bootstrap；
`replacement_start_authorized=false`、`production_activation=false`、
`credentials_allowed=false`、`real_orders_allowed=false`。

### 6.3 Installed adapter

candidate plist 不直接调用 v0.76 固定失败的 source loader，而调用新的
`crypto_quant.challenger_replacement_v3_installed_runtime`。adapter 只做：

1. 重放固定 contract、candidate plist 和唯一成功 install receipt；
2. 以 receipt 身份打开 retained event root；
3. 从 snapshot 加载冻结 plan/contracts/build identity；
4. 构造现有 v3 state 并调用一次
   `run_challenger_replacement_v3_opportunity`；
5. 关闭所有 descriptor并输出一个 canonical terminal summary。

adapter 不实现策略、scheduler、retry loop、Broker、private transport 或 UI。receipt
缺失/重复/不可信时，在公开网络请求和 event append 前失败。start receipt 前 event root
只允许为空或首个 eligible opportunity 的合法 durable prefix；fresh process 从 prefix
恢复，不重新请求已耐久输入。

## 7. Preflight

preflight 除固定公开时钟检查外只读。它必须证明：

- Darwin arm64、uid 501、home 和 `Asia/Shanghai`；
- v0.78 tag/main/CI/manifest/snapshot/contract/plist/Python exact replay；
- replacement service/plist/runtime root 当前不存在；
- 旧 `challenger-forward` 已受控停用且其证据只读；
- exact System Paper v0.58 contract 与同一 30 分钟 ceremony 的 strict verified
  preflight receipt 可重放，且 System Paper root/service 与 replacement path/inode
  不重叠；
- owner/mode/device/local-filesystem、至少 10 GiB 和 100,000 inode；
- `pmset`/常在线/重启策略不会跨过 4 小时机会；
- 三次固定 Binance public server-time GET 通过，proxy/redirect 禁用；
- 没有 credential environment/file/import，账户/private/order authority 为 0；
- 当前时间位于 UTC 四小时边界后 `[10m,30m]`，receipt 有效 30 分钟且不会跨越
  下一自然 `boundary+4h+2m`。

状态仅为 `PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE`、`PREFLIGHT_FAILED_CLOSED` 或
`PREFLIGHT_PLATFORM_UNSUPPORTED`。失败 receipt 是取证，不允许改环境后反复重跑寻找
成功；任何重试必须解释前一失败并产生独立 immutable attempt。

## 8. Installer 与 install receipt

installer 无参数，只重放 fixed contract/plist/preflight。唯一 launchctl 序列：

1. `launchctl print gui/501/local.crypto-quant.challenger-replacement-v1`；
2. service/plist/runtime root 均满足 contract 时，原子 no-replace 发布 target plist；
3. `launchctl bootstrap gui/501 <fixed-target-plist>`；
4. 再次 `launchctl print`，验证 label/program/snapshot/schedule/environment 且 `runs=0`。

禁止 kickstart、start、enable、submit、shell、runtime invocation、bootout 自动回滚。
plist 创建后 bootstrap 失败或 bootstrap 后状态不明时，保留现场并返回
`INSTALL_STATE_UNKNOWN_FAILED_CLOSED`；不得 pathname unlink 或假报回滚。

只有 post-print 完整匹配并且 runtime 尚未运行，才 no-overwrite 发布
`INSTALLED_WAITING_FOR_FIRST_NATURAL_OPPORTUNITY` receipt。receipt 绑定 exact
preflight/contract/plist/snapshot/event-root identities、launchctl transcripts、
installed_at 和自动派生的下一 `UTC 4h + 2m` eligible opportunity。

## 9. First-opportunity observer 与 start receipt

observer 无参数，只读 contract/plist/preflight/install receipt、launchctl print、event
root、stdout/stderr 和首个公开 capture/result。它保留 descriptor，观察前后 replay
两次并要求 projection/stat/hash/attachment 不变。网络、runtime、state write、credential、
account、order、fund 计数全为 0。

状态为：

- `WAITING_BEFORE_FIRST_ELIGIBLE_OPPORTUNITY`；
- `WAITING_FOR_FIRST_NATURAL_OPPORTUNITY`；
- `FIRST_NATURAL_OBSERVED_VERIFIED`；
- `FIRST_OPPORTUNITY_MISSED_RECOVERABLE`；
- `FAILED_CLOSED`。

与 v0.68 不同，首个 flat MISSED 不使 generation 永久失败；它按 v0.69 如实保留，下一
自然机会可成为 shared start。exposed miss、unresolved UNKNOWN、对账不一致或非法证据
固定 `FAILED_CLOSED`。observer 不发布 receipt。

start publisher 只在 `FIRST_NATURAL_OBSERVED_VERIFIED` 时构造 v0.76 frozen v3 receipt，
并将同一自然 `OPPORTUNITY_OBSERVED` 绑定为：

- 72 小时 operational start：使用可信 `observed_at`；
- 90 天 economic start：使用 `scheduled_for`。

publisher 使用 nonce staging、same-fd readback、fsync、no-replace、dir fsync，发布前后
持有并重验 event/log/plist/root capabilities。已有 exact receipt 时补 fsync/replay 后
幂等返回；different/untrusted final 失败。时间、slot、filename、result 或起点均不能由
调用者传入。

## 10. 双流协调

replacement 与 System Paper 是独立事实源、独立 service/root/receipt/timer。v0.78 不修改
System Paper 代码。v0.78 发布后的双流 ceremony 顺序固定为：先渲染 exact System Paper
v0.58 contract/roots，再渲染 exact replacement v0.78 contract/roots，再执行 System Paper
preflight，最后执行会严格加载该 System Paper receipt 的 replacement preflight。两份
receipt 必须处于同一 30 分钟有效窗且都 eligible，才可在同一维护日分别执行固定
installer。若不能同日安全启动，各自从真实 start receipt 计时，不伪造共同起点。

replacement 的 72 小时不替代 90 天；System Paper 仍按 v0.59 的真实 540 槽/90 天合同。
日常只读 observer 不制造 Git 版本。健康检查不得读取 replacement pre-tail PnL、收益率、
胜率或提前 PASS。

## 11. CLI 和权限面

production CLI 恰好四个无参数入口：

1. render fixed snapshot/contract/plist；
2. collect/publish fixed preflight；
3. install fixed LaunchAgent；
4. observe/publish first-opportunity start receipt。

不接受 path、URL、host、symbol、time、slot、command、environment、credential、account、
Broker、order、receipt filename 或 fault callback。测试只 patch 私有低层边界。

renderer 允许固定 GitHub release identity 只读查询；preflight 只允许三次固定 Binance
public time GET；installer/observer/start publisher 网络为 0；自然 runtime 只允许 v0.76
公开 market contract。所有 private Binance endpoint 在 v0.78 snapshot import/static scan
中不可达。

## 12. 崩溃恢复和威胁模型

必须覆盖 snapshot/contract/plist/receipt 的每个 write/readback/file-fsync/dir-fsync/
no-replace 崩溃点，以及 bootstrap 前后、首个 event durable prefix、observer publication
前后。成功只能在 canonical final 与 parent directory durability 完成后返回。

拒绝路径不得写/chmod/unlink 外部 sentinel；测试快照包括 bytes/mode/size/mtime_ns/
ctime_ns/device/inode/nlink。existing FIFO 用 `O_RDONLY|O_NOFOLLOW|O_NONBLOCK` 后立即
fstat 并在 read 前拒绝；缺少 flags/primitive 固定 unsupported，不静默降级。

本版本防路径对象、symlink/hardlink/nonregular、rename race、same-bytes-new-inode、
partial final 和意外不一致。它不声称抵抗持续以同 UID 改写 root 的恶意进程；hash chain
是损坏检测，不是强对手真实性证明。

## 13. TDD 与范围预算

实施顺序：

1. v0.77 foundation、production absence 和 v0.76 deployment immutability RED→GREEN；
2. v3 snapshot/contract/plist codec 与 secure publication RED→GREEN；
3. installed adapter source loading/durable-prefix recovery RED→GREEN；
4. preflight/expiry/public-clock/zero-private-authority RED→GREEN；
5. installer/unknown-state/no-rollback/install receipt RED→GREEN；
6. observer/MISSED recovery/start publisher/dual clock RED→GREEN；
7. CLI/static authority/package/schema/fixture/fault tests；
8. status/ADR/runbook/version/manifest/release gates。

v0.78 新增生产 Python（含薄 CLI）总计不超过 2,900 行；测试不计。优先复用纯 codec、
event loader、v3 start builder 和已审核 private OS primitives。达到上限即停止扩建并重新
设计，禁止用预算修订掩盖复制式实现。

故障测试至少覆盖：

- all secure-publish crash points、并发 no-replace、idempotent exact replay；
- root/final/staging/plist/receipt symlink/hardlink/FIFO/socket/wrong-mode/replacement；
- release/tag/manifest/CI/Python/import/clock/disk/inode/power/network failure；
- plist publish 后 bootstrap 前、bootstrap failure、post-print mismatch；
- zero event、flat MISSED、natural OBSERVED、exposed miss、durable prefix、two workers；
- start receipt publication crash/replay and dual-clock exact derivation；
- credential/private endpoint/import/static scan、所有拒绝路径 authority=0。

最终代码状态本地 full suite 一次、compileall、`make validate`、diff-check；独立完整审查
一次，修复后只定向复审；PR Python 3.9/3.12 + macOS arm64 CI、main CI、annotated
`v0.78.0` identity。相同代码状态不重复 full suite。

## 14. 发布和后续 ceremony

v0.78 release 必须证明 production root/plist/service/start receipt 仍不存在，且
network/launchctl mutation/state/private/account/order/fund 全为 0。代码发布后才允许：

1. 从 exact System Paper v0.58 renderer 生成其 owner-only contract/roots；
2. 从 exact `v0.78.0` renderer 生成 replacement snapshot/contract/plist；
3. 依次运行 System Paper preflight 与绑定前者 receipt 的 replacement preflight；
4. 若两者均 eligible，执行各自一次 fixed bootstrap；
5. 不 kickstart，等待各自首个自然槽/机会；
6. observer 验证并发布独立 start receipt；
7. 从真实 receipt 开始 72 小时/90 天墙钟检查。

任一安装进入 UNKNOWN、出现旧 root 污染、私有权限、非零 order/fund 或证据不一致，立即
失败关闭并保留现场。安装成功不代表 Paper 完成、盈利、AI 优势、Canary 或实盘资格。
