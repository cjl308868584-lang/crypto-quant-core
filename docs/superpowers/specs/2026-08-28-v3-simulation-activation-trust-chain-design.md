# Replacement v3 Minimal Simulation Activation Trust Chain Design

日期：2026-08-28  
目标版本：`v0.78.0`  
基线：annotated `v0.77.0` / `39a973d51bdc8fc957a65052f4bb5f310a1f72c3`  
适用分支：`codex/v0.78-v3-simulation-activation-design`

## 1. 决策

v0.78 是启动 replacement 72 小时公开行情模拟所需的最后一个代码版本。它在同一个
tag 内完整交付 release-bound installed adapter、最小 preflight、固定 installer、自然机会
observer 和 start-receipt publisher；任何必要代码都不得拆到 v0.79。

代码发布期间不创建 production root、不安装、不启动、不访问凭据/账户、不提交订单、
不移动资金，也不开始计时。tag 发布后只需一次独立外部动作，便可使用该 tag 自带 CLI
完成 render → preflight → bootstrap → 等待自然机会 → publish start receipt，不再修改
代码或制造新语义版本。运行 receipt 留在 owner-only production root。

发布状态为 `V3_SIMULATION_ACTIVATION_TRUST_CHAIN_CODE_RELEASED_NOT_INSTALLED`。

## 2. 收缩结果

相对原 350 行设计，删除或降级：

- 删除 System Paper v0.58 contract/preflight 和同一 30 分钟双流 ceremony 依赖；
- 删除 `deployment-v3` 新目录层，沿用 v0.76 固定 production paths；
- 删除通用 release-query/governance coordinator；
- 删除重新实现 secure-publish、snapshot tree、command transcript、clock transport；
- 删除新的 observer 引擎，直接复用 v0.76 observer/projection；
- 删除 v0.79 证据版本设想；
- System Paper/540 槽/90 天协调成为独立后台工作，不阻塞 replacement 72 小时；
- 生产代码上限从 2,900 行降到 1,500 行，目标 1,200 行以内；
- 实施从 8 项缩为 5 项，关键路径 1–3 天。

不能删除的三个新 schema 是 v3 install contract、v3 preflight receipt、v3 install
receipt。现有 v1 schema 硬编码 `v0.67.0/v0.68.0`、四文件 strategy-core、旧
`INSTALLED_WAITING_FOR_FIRST_NATURAL_SLOT` 和旧 adapter module；直接复用会错误接受
v2/540 槽事实源。

## 3. 复用边界

直接复用而不复制：

- `challenger_replacement_install_trust` 的 retained dirfd、no-follow/nonblocking read、
  snapshot publication、same-fd readback、fsync、platform no-replace、command transcript；
- `challenger_replacement_install_preflight` 的固定 launchctl/pmset/clock/credential probes；
- `challenger_replacement_install` 的 plist publication、command wrapper 和
  unknown-state/no-rollback 规则；
- v0.76 `challenger_replacement_v3_runtime`、`challenger_replacement_v3_observer`、
  `challenger_replacement_v3_start`、qualifier、economic evaluator 和 public HTTP contract。

private helper 不提升成通用 public framework。v3 模块只做不同身份/语义的薄组合。

## 4. 固定身份

- repository `cjl308868584-lang/crypto-quant-core`，`PUBLIC`；
- v0.77 tag object `f4a40105ec67f6823229a526542dc6d29fac5394`；
- peeled main `39a973d51bdc8fc957a65052f4bb5f310a1f72c3`；
- tree `af01967aa7345035cd40e306655be67b492242b2`；
- package `0.77.0`；manifest `1.71.0`；
- manifest hash `91ca11c6759eaab7727b0d003b5d35debd5566d2e7a9750ac06f0e0db958f302`；
- manifest file SHA-256
  `7bf6488b3c4428a3497ee0a9e2ad5c68ac9fb5021fb8b1166de5c855dafccdb3`；
- build tree hash `63a57f7f5ef132efa0f565f5edd1f3621cca14015aea9c315eab3d5bc155f3de`；
- main CI `33145885379`，Python 3.9/3.12/macOS arm64 success；
- v0.76 deployment SHA-256
  `28eec0ee5f424952ee96e0c711abc68d7d1cab592859515ba8f79958971d288b`。

v0.78 不硬编码未来 merge/tag。tag 后 fixed renderer 验证
`HEAD == origin/main == v0.78.0^{}`、annotated tag、clean checkout、package/manifest 与
exact main CI，再生成 owner-only contract。未来身份不反向进入 Git manifest。

## 5. 固定路径和 authority

沿用 v0.76 deployment：

- service `gui/501/local.crypto-quant.challenger-replacement-v1`；
- runtime root
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1`；
- snapshot `<runtime>/deployment/snapshot`；
- event root `<runtime>/state/challenger-replacement-events-v1`；
- start receipt `<runtime>/evidence/start-receipts/challenger-replacement-v3-start-receipt-v1.json`；
- target plist `/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist`；
- stdout/stderr 使用 v0.76 deployment exact paths。

这些路径与旧失败 `challenger-forward-v1` 完全不同。production CLI 无参数，不接受
path/URL/time/slot/command/environment/credential/order override。

始终 false/zero：`production_activation`、credentials、account/private requests、Broker、
real orders、fund movement。自然 runtime 只允许 v0.76 冻结的公开 ETHUSDT GET。

## 6. Snapshot、contract 和 installed adapter

snapshot 文件集等于 v0.76 deployment `strategy_inventory` exact key set，加 v0.78 薄
activation modules/CLI/schema 闭包；每项必须在 v0.78 manifest 中 hash 相等。不得复制
v0.77 private credential/protocol/order/Canary 模块。上限 256 文件、64 MiB。

snapshot 调用已有 `_publish_snapshot_from_inventory` 和 replay primitives；v3 wrapper 不
复制 write/fsync/no-replace。candidate plist 沿用 label/root/schedule/log paths，但 module
固定 `crypto_quant.challenger_replacement_v3_installed_runtime`，替代 v0.76 故意不可用的
`_load_fixed_runtime_sources()`。

installed adapter 仅重放 contract/plist/唯一 install receipt，打开 bound event root，
加载 v0.76 plan/contracts/build identity，调用一次
`run_challenger_replacement_v3_opportunity`，关闭 descriptor，输出 canonical summary。
receipt 缺失或不可信时在公开请求/event append 前失败。durable prefix 由现有 runtime
重放，不新增 retry/scheduler。

contract 只绑定 v0.78 release、v0.76 deployment、snapshot、Python/import、event-root、
plist、service/schedule/paths 和全部 false/zero authority。状态为
`V3_SIMULATION_INSTALL_CONTRACT_VERIFIED_NOT_INSTALLED`；
`runtime_install_authorized=true` 只允许一次 fixed bootstrap。

## 7. 最小 preflight

preflight 只证明 replacement 安装可安全执行：

- release/tag/main/CI/manifest/snapshot/contract/plist/Python exact replay；
- Darwin arm64、uid/home/timezone、磁盘/inode、pmset/常在线；
- runtime root/plist/service 不存在，旧 Challenger 受控停用；
- owner/mode/no-symlink/hardlink/FIFO/socket/path overlap；
- UTC 四小时边界后 `[10m,30m]`，receipt 30 分钟内有效且不跨下一 `4h+2m`；
- 三次固定 Binance public time GET，通过 proxy/redirect/size/clock gate；
- credential/private/account/order/fund authority 为 0。

不加载 System Paper contract/receipt。System Paper/90 天可独立启动，不影响 replacement
72 小时 eligibility。状态仅为 `PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE`、
`PREFLIGHT_FAILED_CLOSED`、`PREFLIGHT_PLATFORM_UNSUPPORTED`。

## 8. Installer、自然机会和 start receipt

installer 只允许：

1. `launchctl print <fixed service>`；
2. atomic no-replace 发布 `0600` target plist；
3. `launchctl bootstrap gui/501 <fixed plist>`；
4. 再次 print 并要求 label/program/schedule/environment exact、`runs=0`；
5. 发布 `INSTALLED_WAITING_FOR_FIRST_NATURAL_OPPORTUNITY` receipt。

禁止 kickstart/start/enable/submit/bootout、shell 或直接 runtime。bootstrap/plist 后失败
保留现场并返回 `INSTALL_STATE_UNKNOWN_FAILED_CLOSED`，不 unlink/chmod/假报回滚。

安装后只等待自然四小时机会。v0.76 observer 只读固定 root。v0.78 publisher 把
observation 交给 v0.76 start builder：flat MISSED 如实保留且后续自然 OBSERVED 可启动；
exposed miss、UNKNOWN、对账或证据失败关闭。

同一 `OPPORTUNITY_OBSERVED` 派生 operational `observed_at` 和 economic
`scheduled_for`。publisher 复用现有 exact publication primitive，no-overwrite/fsync/replay；
caller 不能传时间、slot、filename 或结果。start receipt 发布开始真实连续 72 小时；
90 天经济流可并行，但不阻塞 72 小时。

## 9. 验收、规模和发布

最小生产文件为 activation trust/CLI、installed runtime、preflight/CLI、install/CLI、
start/CLI 及三个 schema/mirrors。生产 Python 总计 `<1500` 行，目标 `<=1200`。
禁止新增策略、UI、通用 deployment/scheduler、Broker、交易所抽象或治理层。

TDD 覆盖 release/deployment identity、snapshot exclusion、missing receipt zero authority、
durable-prefix replay、clock/network/disk/service failure、唯一 launchctl sequence、bootstrap
unknown state、flat MISSED recovery、dual clocks、publication crash/idempotency、路径攻击、
sentinel unchanged、CLI/static private-authority absence。

最终代码状态 full suite 一次、compileall、`make validate`、diff-check；完整独立审查一次，
修复后定向复审；PR/main Python 3.9/3.12/macOS arm64 CI；annotated `v0.78.0` identity。

v0.78 tag 后无需 v0.79。剩余外部动作只有一次无凭据模拟安装/启动 ceremony，随后等待
首个自然机会（最多约 4 小时）并发布 start receipt，再经过真实连续 72 小时。代码发布
不执行这些动作，也不宣称盈利、AI 优势、Canary 或实盘资格。
