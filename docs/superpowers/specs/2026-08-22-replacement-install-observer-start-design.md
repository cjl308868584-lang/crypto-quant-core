# Replacement Challenger Install, Observer and Start Trust Chain Design

日期：2026-08-22  
目标版本：`v0.68.0`  
基线：annotated `v0.67.0` / `ca022edccdcbb2d28b1ea25002e5f19512795e3e`  
适用分支：`codex/v0.68-replacement-install-trust-chain`

## 1. 决策摘要

v0.68 只发布 replacement Challenger 的安装信任链代码与冻结合同，不在本版本
渲染真实快照、不执行 preflight、不安装 plist、不调用 `launchctl bootstrap`、
不启动 Runner，也不创建 install/start receipt。完成状态固定为
`REPLACEMENT_INSTALL_TRUST_CHAIN_CODE_RELEASED_NOT_INSTALLED`。

发布后的真实 ceremony 必须是独立动作：v0.68 annotated tag 先成为不可变的代码
权威，然后才能生成绑定该 tag/main/CI 的 owner-only snapshot 和 preflight receipt。
真实安装和首个自然槽位证据在下一证据版本逐字节封存。这避免“尚未
存在的 tag 授权安装”或“运行后 receipt 反向进入已发布 tag”的循环信任。

## 2. 不可变边界

- `production_activation=false`、`real_orders_allowed=false`持续有效。
- 无交易所凭据、账户、余额、Broker、真实订单或资金写入。
- 不迁移、回填、重置或重新解释旧 Challenger 和 replacement 已冻结证据。
- append-only canonical event log 仍是 replacement 运行状态唯一权威；`exports/`仍不是权威。
- 不引入 SQLite、通用 scheduler、通用 Broker/order lifecycle、交易所适配平台或新 UI。
- v0.61 loopback-only 只读运维 UI 仅在后续投影接线时复用，不参与安装或启动。
- v0.68 本身的 production root/plist/service/network/state-write 计数必须全为 0。

## 3. 权威和身份

### 3.1 v0.67 前任发布基础

v0.68 代码必须冻结并测试以下已发布身份：

- repository: `cjl308868584-lang/crypto-quant-core`;
- visibility: `PUBLIC`;
- annotated tag: `v0.67.0`;
- tag object: `7c65c0a34cf37f4d46ed3cdd2a0278657aa3e8c5`;
- peeled commit/main: `ca022edccdcbb2d28b1ea25002e5f19512795e3e`;
- package version: `0.67.0`;
- evaluator manifest version: `1.61.0`;
- evaluator manifest hash:
`2b72a470a2f210461a3a6753fd3d603fee9b90df76e825deea3b9bde61a26110`;
- main CI run: `32572208544`;
- main CI jobs: Python 3.9, Python 3.12, macOS 15 arm64 均为 `success`;
- deployment candidate:
  `artifacts/challenger-replacement/challenger-replacement-deployment-v0.67.0.json`;
- frozen plist:
  `artifacts/challenger-replacement/local.crypto-quant.challenger-replacement-v1.plist`;
- superseding v2 plan 和 v0.64 supersession/attestation 原字节不变。

### 3.2 v0.68 最终发布身份

代码不硬编码尚未存在的 v0.68 commit 或 tag object。未来 ceremony 中的固定
renderer 必须从受审核的固定 repository 路径只读验证，并只允许 3 次固定、
只读 GitHub 查询：仓库 visibility/ADMIN、exact HEAD 的 main workflow run、该 run
的三个 jobs。GitHub 查询与市场请求分开计数：
`github_request_count=3`、`market_request_count=0`：

1. `HEAD == origin/main == v0.68.0^{}`;
2. `v0.68.0` 对象类型为 annotated `tag`;
3. worktree clean;
4. GitHub main CI 精确对应 HEAD 且三个固定 job 全部成功；
5. package/manifest/file inventory/tree hash/self-hash 可从 checkout 完整重放。

这些值进入未来 owner-only install contract 和 snapshot manifest，不反向进入
v0.68 Git manifest，避免自引用。

## 4. 采用方案与取舍

### 4.1 采用：replacement-specific 薄信任链

新模块只服务 replacement 的固定 label/path/event contract。它可调用已审核的
canonical JSON、event root capability 和 Darwin/Linux atomic no-replace 底层原语，但不将它们
泛化成新 storage/deployment framework。

### 4.2 拒绝：复制 System Paper 部署链

System Paper install/observer/start 现有实现超过 2,900 行，并且强绑 SQLite/WAL、
Paper artifact 和不同槽位语义。复制会引入两套事实源和大量通用基础设施。

### 4.3 拒绝：在一个 tag 中同时发布代码和真实 receipt

安装代码在 tag 之前没有最终身份；真实 receipt 又只能在 tag 之后产生。
两者合并会导致循环信任或修改已发布 tag，因此禁止。

## 5. 固定 production 路径

以下路径只能由冻结 builder 派生，production CLI 不接受 path override：

- runtime root:
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1`;
- deployment root: `<runtime>/deployment`;
- snapshot root: `<deployment>/snapshots/<snapshot_tree_hash>`;
- install contract: `<deployment>/challenger-replacement-install-contract-v1.json`;
- preflight root: `<deployment>/preflight-receipts`;
- install receipt root: `<deployment>/install-receipts`;
- start receipt root: `<runtime>/evidence/start-receipts`;
- event root: `<runtime>/state/challenger-replacement-events-v1`;
- stdout/stderr: v0.67 deployment 中的固定路径；
- target plist:
  `/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist`.

runtime/deployment/evidence/state/log 目录 mode 固定 `0700`，普通证据文件和 plist
固定 `0600`。所有路径边界拒绝 symlink、hardlink、wrong owner/mode、
non-regular/non-directory 对象和验证后替换。

## 6. Owner-only immutable execution snapshot

### 6.1 输入清单

renderer 从 v0.68 evaluator manifest 的 exact `file_hashes` 构建快照，不自行扫描或猜测
依赖。快照包含 manifest 列出的全部文件和 manifest 本身，确保 import/schema/
plan 闭包与发布完全一致。总数最多 1,024 个文件，单文件最多 4 MiB，
总计最多 128 MiB。

每个源文件用 no-follow/nonblocking descriptor 打开，验证 regular/uid/nlink/mode/size，
有界读取后再次 fstat 及 path attachment 验证。源字节必须与 manifest hash 一致。

### 6.2 发布协议

snapshot 在相同 retained parent dirfd 下使用非规范 nonce staging directory：

1. 以 owner-only `0700` 安全新建 staging；
2. 每个文件只通过 `O_CREAT|O_EXCL|O_RDWR|O_NOFOLLOW` 新 fd 写入；
3. 显式处理 short write/EINTR，同 fd seek/readback，验证 exact bytes/hash/size；
4. fsync 每个文件、每层目录和 staging root；
5. 用已实证的 platform no-replace primitive 原子发布到
   `<snapshot_tree_hash>`；禁止 `os.rename/os.replace` 覆盖降级；
6. fsync parent，replay 完整 inventory，再验证 source 未变，才能返回成功。

缺少 Darwin `renameatx_np(RENAME_EXCL)` 或 Linux `renameat2(RENAME_NOREPLACE)` 时固定
`PLATFORM_UNSUPPORTED`，不降级。已存在 exact final 只读 replay 并补做 parent fsync 后
返回 idempotent。任何 untrusted/different final 失败关闭。

崩溃留下的非规范 staging 不是 snapshot 或证据。新 ceremony 不删除、不修改、
不读取其内容；它封存名称/stat 后失败关闭，要求从同一发布 commit 新建
独立 ceremony 目录。不得静默清理可能的 external sentinel。

### 6.3 Python 身份

plist 固定使用 `/usr/bin/python3`，同时在 contract 中绑定 executable 的
device/inode/uid/mode/nlink/size/SHA-256、`sys.version`和 Python 3.9 compatibility。
`/usr/bin/python3` 是 root-owned 系统文件，目标机实证可有多个系统 hardlink；因此
不套用 owner-only evidence 的 `nlink=1`，而是绑定并在每次 replay 精确复核其实际
`st_nlink`，同时要求 regular、uid=0 且 group/world 不可写。快照的
`PYTHONPATH=<snapshot>/src`、`PYTHONDONTWRITEBYTECODE=1`，禁止 user site 和任意环境变量。
安装前用新进程从 snapshot import runtime CLI 并打印唯一 canonical identity。

v0.67 deployment plist 仅作为 predecessor ancestry 保留，不得作为安装输入：它固定
指向旧的 `deployment/snapshot/bin/python3`，与本节 v0.68 runtime identity 不同。
renderer 必须从 v0.68 contract 的 runtime/schedule/path 字段确定性生成独立 candidate
plist，owner-only no-overwrite 发布到
`<deployment>/local.crypto-quant.challenger-replacement-v1.plist`；contract 绑定其路径与
SHA-256。preflight 和 installer 每次都重放这份 candidate bytes，绝不安装 v0.67 plist。

## 7. Install contract

`challenger-replacement-install-contract-v1` 绑定：

- v0.67 predecessor 全部身份；
- v0.68 release/tag/main/CI/manifest 全部身份；
- v0.67 deployment candidate/plist/v2 plan exact bytes/hash/id；
- v0.68 独立 candidate plist exact path/hash；v0.67 plist 仅为 ancestry；
- snapshot file inventory/tree hash/root identity；
- Python identity/import transcript；
- service label、schedule、ProgramArguments、working directory、environment；
- 全部固定 path 及预期 owner/mode/device 合同；
- authority:
  `production_activation=false`,
  `runtime_install_authorized=true`,
  `replacement_start_authorized=false`,
  `real_orders_allowed=false`;
- `runtime_install_authorized=true` 只授权一次固定 plist bootstrap，不授权
  kickstart/start/runtime/network/Broker/order。

contract 使用唯一版本化 canonical encoding、self-hash 和 stable id，通过 owner-only
no-overwrite publisher 发布。生产 CLI 无 path/version/commit/URL 覆盖。

## 8. Preflight receipt

### 8.1 只读检查

preflight 在 installer 之外运行，除了一次固定 public clock gate 外不发起网络。
它仅读验证：

- Darwin arm64, uid 501, home `/Users/chenm4`, timezone `Asia/Shanghai`;
- v0.68 tag/main/CI/manifest/snapshot/contract/plist/Python import exact replay;
- target service 未加载、target plist 不存在；
- 旧 failed Challenger service 未加载；
- runtime/event/log/evidence/deployment roots 不与旧 cohort/System Paper 交叉；
- owner/mode/device/symlink/hardlink/FIFO/socket 边界；
- 本地文件系统、至少 10 GB 可用空间、100,000 inodes；
- `pmset` 证据不会导致跨过 4h 槽位；
- 3 次固定 Binance public time GET 的可信时钟门；
- plist/environment 不含 Binance/exchange credential，Broker/order authority 为 0。

GitHub token 不进入 LaunchAgent 环境，不冒充交易所凭据。preflight 只扫描固定
exchange-secret 名称和 contract/plist 字节，不使用宽泛 `token/secret` 子串造成假阻断。

### 8.2 状态

- `PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE`：全部检查通过；
- `PREFLIGHT_FAILED_CLOSED`：可信 contract 之后的机器检查失败；
- `PREFLIGHT_PLATFORM_UNSUPPORTED`：平台不匹配且 command/network 计数为 0。

只有 verified receipt 可授权 installer，且自 `observed_at` 起 30 分钟过期。contract/plist
无效时零写入；可信 contract 后的失败可用 no-overwrite 发布 forensic receipt。
运行期中的 network/launchctl mutation/state/Broker/order 计数分别为 `3/0/0/0/0`。

## 9. Atomic installer and install receipt

installer 入口无任意参数，只重放固定 contract/plist/preflight。允许的
launchctl 序列只有：

1. `launchctl print gui/501/local.crypto-quant.challenger-replacement-v1`;
2. 只在 service/plist 均不存在时，原子 no-replace 安装 mode `0600` plist；
3. `launchctl bootstrap gui/501 <fixed-target-plist>`;
4. 再次 `launchctl print` 验证 label/program/snapshot/path/schedule，并要求尚未自然运行。

禁止 `kickstart/start/enable/submit/bootout`，禁止 shell，禁止直接调用 runtime CLI。

- bootstrap 之前失败：零 launchctl mutation，不创建 plist。
- plist 创建后 bootstrap 失败：仅当目标 inode 仍等于本次新建 inode 时删除它，
  fsync parent；不删除 snapshot/contract/preflight。
- bootstrap 已成功但 post-print 失败：不声称回滚，不自动 bootout；封存
  `INSTALL_STATE_UNKNOWN_FAILED_CLOSED` 并进入事故解锁门。
- 只有 post-print 全部匹配且 run count=0 才发布
  `INSTALLED_WAITING_FOR_FIRST_NATURAL_SLOT` install receipt。

install receipt 绑定所有源 receipt/hash、plist target inode/stat/hash、snapshot root identity、
launchctl 命令 exact argv/exit/stdout/stderr bytes hash、installed_at 和权限计数。安装成功只表示
LaunchAgent 已加载且尚未运行，不表示 Paper 已开始。

## 10. Read-only first-slot observer

observer 只加载 production contract/plist/preflight/install receipt，保留 event root、stdout、
stderr 的 descriptor/capability，并只执行一次固定 `launchctl print`。网络、runtime、
state write、Broker、order 计数全为 0。

它使用 v0.66 event loader 重放全链，并使用 v0.67 source/decision/live-capture loader 交叉
验证首槽 exact bytes。不读取或输出 PnL、收益率、胜率或提前 gate。

状态机：

- `WAITING_BEFORE_FIRST_ELIGIBLE_SLOT`：未到 install receipt 派生的首个自然触发门；
- `WAITING_FOR_FIRST_NATURAL_SLOT`：门后仍没有成功槽，但未到漏槽截止；
- `FIRST_NATURAL_SLOT_VERIFIED`：恰好一个与安装后首槽匹配的完整 `SLOT_SUCCEEDED`，
  capture/source/decision/event/log/launchctl 全部一致；
- `FIRST_SLOT_OBSERVATION_WINDOW_MISSED`：在无 start receipt 时已进入第二槽或存在
  两个成功槽；
- `FAILED_CLOSED`：槽位失败/过期/缺失、非零退出、非空 stderr、event/log/path/
  loader/hash/launchctl 不一致。

observer 只返回 canonical summary，不发布 receipt。观察前后 event/log/plist/snapshot 的
bytes/stat/inode 必须不变。

## 11. Start receipt and 90-day boundary

start publisher 内部调用只读 observer；只有 `FIRST_NATURAL_SLOT_VERIFIED` 可构建并
no-overwrite 发布 start receipt。已有 exact receipt 幂等返回；已有 different/untrusted
对象失败关闭。发布前后重验所有 retained source。

receipt 自动派生：

- `first_scheduled_for =` 首个自然成功槽；
- `required_slot_count = 540`;
- `last_required_scheduled_for = first + 4h * 539`;
- `tail_end = first + 4h * 540 = first + 90d`;
- `evaluation_not_before = tail_end + 5m`;
- `cohort_status = STARTED_COLLECTION_ONLY`.

不允许人工传入日期、槽位、计数、起点、终点或文件名。只有该 receipt
才开始 replacement 的真实 90 天/540 槽位计时。install/preflight/tag 时间均不是起点。

## 12. CLI 与网络权限

production CLI 分为四个无参数入口：

1. render fixed snapshot/contract/plist;
2. collect/publish fixed preflight receipt;
3. install fixed LaunchAgent;
4. observe/publish first-slot start receipt。

它们不接受 path、URL、symbol、time、slot、command、environment、credential、Broker、
order 或 receipt filename 覆盖。测试通过私有低层 wrapper/mock 建立 fixture，不在生产
API 暴露 arbitrary callback/fault injector。

发布后的 renderer 只允许上文 3 次固定只读 GitHub 查询；preflight 只允许 3 次
固定 public Binance time GET；安装后自然 Runner 只允许 v0.67 固定 public GET。
installer/observer/start publisher 的 GitHub/市场网络计数均为 0。GitHub token
只能由 `gh` 进程读取，不进入 snapshot、contract、plist 或 LaunchAgent 环境；
任何交易所 private/account/credential 请求始终为 0。

## 13. 威胁模型

v0.68 防御：不可信既有路径对象、symlink/hardlink/FIFO/socket、验证后目录替换、
same-bytes-new-inode 替换、partial write/crash、concurrent no-replace race、越界 chmod/unlink，以及
receipt/event/hash/schema 协同篡改。所有拒绝路径必须保持 external sentinel 的
bytes/mode/size/mtime_ns/ctime_ns/inode/nlink 不变。

v0.68 不声称抵抗可持续以同 UID 改写 runtime root 内容的恶意进程。hash chain
用于损坏和不一致检测，不是恶意同 UID 下的真实性证明。强对手模型需要
独立 OS UID/沙箱或攻击者不可访问的密钥与外部单调锚点，不属于本版本。

## 14. TDD 和验收门

实施顺序固定为：

1. v0.67 foundation 与 no-production-change 回归；
2. snapshot/contract codec 和 secure publication RED→GREEN；
3. preflight loader/collector/publication RED→GREEN；
4. installer/rollback/install receipt RED→GREEN；
5. observer 状态机与只读无副作用 RED→GREEN；
6. start receipt/540-slot derivation/no-overwrite RED→GREEN；
7. CLI 静态权限、schema mirrors、committed fixture/golden/failure matrix；
8. release metadata/status/ADR/build manifest。

主要故障测必须覆盖：

- snapshot 每个 write/readback/file-fsync/dir-fsync/no-replace 崩溃点；
- parent/final/staging/plist/receipt 的 symlink/hardlink/FIFO/socket/wrong-mode/replacement；
- preflight 过期、时钟、断网、睡眠、磁盘、凭据边界与 release identity 失败；
- plist publish 后 bootstrap 前崩溃、bootstrap 失败、post-print 失败；
- observer 前后 event/log/plist/snapshot 替换；
- 零槽、一个成功槽、两个槽、首槽失败/漏失/过期；
- start receipt 发布竞态、目录 fsync 失败与 fresh-process replay；
- 所有拒绝路径零越界写/零 chmod/零 runtime invocation。

验证节奏：每个原子切片先精确 RED 再最小 GREEN；日常只跑受影响测试；
最终代码状态本地 full suite 一次、compileall、make validate、diff-check；独立完整审查
一次，修复后只针对性复审；PR Python 3.9/3.12 + macOS arm64 CI，main CI，
annotated tag 身份验证。同一未变代码状态不机械重复 full suite。

## 15. 发布和后续 ceremony

v0.68 发布前必须证明：

- 代码、schema、fixtures、spec/plan/status/ADR 全部一致；
- Critical/Important 审查发现为 0；
- package/manifest/main/tag 身份一致；
- production root、target plist、service、install/start receipt 仍不存在；
- network/launchctl mutation/runtime/state/Broker/order 计数为 0。

v0.68 发布后，真实 ceremony 需要一个合并审批包，精确列出：

1. 将写入的 production roots/plist/receipt paths；
2. renderer 固定 3 次 GitHub 只读查询、preflight 固定 3 次 public time GET；
3. rollback 与 post-bootstrap unknown-state 事故边界；
4. 首个自然槽位和第二槽前的 observer 时间门；
5. 不含 kickstart、手工 Runner、凭据、Broker、order 的声明。

安装成功后也不宣称盈利、AI 优势或实盘资格。只有首个自然成功槽位的
verified start receipt 才把 replacement 进入真实时间收集阶段。
