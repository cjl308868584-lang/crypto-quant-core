# NautilusTrader End-to-End Isolation Spike Design

日期：2026-08-22

目标版本：`v0.65.0`

基线：annotated `v0.64.0` / `c4f6ea213077850a8fc8b9bd3392f1a4bac466f9`

适用分支：`codex/v0.65-nautilus-e2e-spike`

## 0. 决策摘要

v0.65 只回答一个 build-vs-buy 问题：在相同的固定 ETHUSDT 4H 输入和已冻结
Decision/Target/Risk 授权下，NautilusTrader 能否以隔离 one-shot sidecar 的形式提供可接受的
order intent、fill、fee、position、PnL、instrument-rule 和 fresh-process replay 语义。

本版本采用一个语义版本、两个不可跳过阶段：

1. `SUPPLY_CHAIN_ACQUISITION_AND_VERIFICATION`：固定并验证 Python、平台、wheel、hash、
   license、tag/commit、完整传递依赖锁、SLSA attestation、精确命令和 stdout/stderr；
2. `ZERO_NETWORK_SANDBOX_COMPARISON`：阶段 1 成功后，才在无凭据、无网络、无 live adapter 的
   fresh Python 3.12 进程中运行固定 fixture 和独立重放。

阶段 1 失败时，v0.65 诚实结束为 `INCONCLUSIVE_KEEP_CURRENT_CORE`，不得另开一个正式版本
重试相同假设以寻找更好结果。阶段 2 完成后只允许
`ADOPT_FOR_PREREGISTERED_SHADOW`、`REJECT_KEEP_CURRENT_CORE` 或
`INCONCLUSIVE_KEEP_CURRENT_CORE`。`ADOPT` 仅表示值得设计未来 Shadow，不授权生产依赖、服务安装、
凭据、订单、Canary 或实盘。

## 1. 为什么必须重评，而不能沿用 v0.63 结论

v0.63 的不可变结论为 `INCONCLUSIVE_BLOCKED`。其机器事实是：没有可重放的供应链 transcript，
没有安装引擎，没有执行 Golden、成交、费用、持仓、PnL 或 fresh-process 对照。它不证明
NautilusTrader 不适合，也不证明自研执行层更好。

v0.65 不修改 v0.63 的 spec、plan、ADR、lock、comparison 或 artifact bytes。它以新的预注册
计划和新的 artifact identities 重做一次真正 end-to-end 验证。v0.63 必须作为 predecessor
failure ancestry 被 v0.65 plan 和 final report 精确绑定。

## 2. 与项目赚钱目标的关系

本 Spike 不寻找 Alpha，也不提高任何收益预期。它削减的是非差异化工程成本：通用订单生命周期、
模拟 Broker、持仓/费用核算、回测执行和恢复语义若能由成熟引擎承担，项目资源可集中到策略研究、
真实 Paper 观察、证据可信、失败关闭和对账。

项目继续控制：

- Decision/Target/Risk 和策略研究合同；
- append-only evidence、严格 loader、hash/identity、失败 ancestry 和不可回填；
- 风险授权、对账、research gate 和只读运维投影。

项目停止扩建：

- 通用模拟 Broker 和新的通用成交模型；
- 通用 order/position lifecycle、venue abstraction 和交易所 adapter；
- 新的通用 scheduler、发布机器人和交易 UI。

## 3. 方案比较

### 3.1 继续扩建当前自研执行层

优点是没有第三方边界。缺点是重复制造 NautilusTrader 已覆盖的通用能力，并把时间从长期 Paper、
故障注入、恢复和对账移开。v0.63 没有产生支持该选择的证据。本方案不采用。

### 3.2 直接 import 或接管当前 Runner

优点是集成路径短。缺点是当前核心仍需 Python 3.9，而候选要求 Python 3.12+；同时会在验证前
创造第二事实源和生产依赖。本方案拒绝。

### 3.3 独立 Python 3.12 one-shot sidecar（采用）

当前核心生成 canonical request；独立进程创建一个 low-level BacktestEngine，输出 canonical
result 后退出；Evidence Adapter 只读比较。无 daemon、service、socket、HTTP、队列、Runner hook、
数据库或 production root。这是最小、方向明确、可以完整拒绝的架构。

## 4. 固定官方候选

正式权威只允许：

- [PyPI 1.230.0 JSON](https://pypi.org/pypi/nautilus_trader/1.230.0/json)；
- [GitHub release v1.230.0](https://github.com/nautechsystems/nautilus_trader/releases/tag/v1.230.0)；
- [official repository](https://github.com/nautechsystems/nautilus_trader)；
- [official installation documentation](https://nautilustrader.io/docs/latest/getting_started/installation/)；
- exact tag LICENSE bytes and official PyPI/GitHub attestations.

预注册候选固定为：

- package/version：`nautilus_trader==1.230.0`；
- `Requires-Python`：`>=3.12,<3.15`；
- official tag：`v1.230.0`；
- tag object：`112d335088ec11cdd1d60038b16c8fe56406aead`；
- peeled commit：`8160730c7c550480b0a439fb11086a4c4de15f0b`；
- wheel：`nautilus_trader-1.230.0-cp312-cp312-macosx_15_0_arm64.whl`；
- wheel size：`156035900`；
- wheel SHA-256：
  `033f6207d1c52095d64a7644f43b90cab939c2038044db70a4165f2acef3d079`；
- license：`LGPL-3.0-or-later`，exact `LICENSE` SHA-256
  `ee907919ec88c9c017b1f8b608db20960b6598aefcc4fe58820bde955d65ed3c`；
- target runtime：macOS `15.x` arm64、vanilla CPython `3.12.x`。

最新 `1.231.0` 的 CPython 3.12 ARM wheel 是 `macosx_26_0_arm64`，与冻结目标 Mac 15 不兼容。
选择 1.230.0 是显式的平台兼容决策，不是为了得到更好的业务结果。实施期间不得静默升级、降级、
改用 nightly/develop、sdist 或从源码构建。

预查值只用于写设计；正式 plan artifact、acquisition receipt 和 transcript 必须由 v0.65 固定 CLI
重新采集。预查不能冒充正式证据。

## 5. 预注册与防 post-hoc 状态机

同一 v0.65 分支依次形成不可回写的边界：

```text
CODE_AND_LOCK_REVIEWED
        |
        v
SPIKE_PLAN_PREREGISTERED
        |
        +-- acquisition failure --> INCONCLUSIVE_KEEP_CURRENT_CORE
        |
        v
SUPPLY_CHAIN_VERIFIED
        |
        v
SANDBOX_RESULT_PUBLISHED
        |
        v
COMPARISON_FINALIZED --> ADOPT / REJECT / INCONCLUSIVE
```

正式 `nautilus-e2e-spike-plan-v0.65.0.json` 必须在任何正式 wheel/metadata acquisition 前发布。
它绑定 v0.64 foundation、v0.63 predecessor artifact hashes、candidate version、code/lock predecessor
commit/tree、fixture hash、comparison fields、差异分类、adoption gates 和 safety counters。

plan 自身不能绑定包含自身的 commit。它绑定紧前一 `CODE_AND_LOCK_REVIEWED` commit；后续 ceremony
只允许 exact plan/result/report artifact 增量，代码、lock、fixture 或阈值变化立即失败关闭。plan bytes、
old v0.63 bytes 和首次 final result 永不修改。

## 6. 阶段 1：供应链获取与验证

### 6.1 隔离环境

- 独立项目：`sandboxes/nautilus-v065/`；
- 独立 ignored virtual environment；
- 根 `pyproject.toml`、根 `requirements.lock` 和 Python 3.9 import graph 不得依赖或 import Nautilus；
- 正式 acquisition root 使用 owner-only 临时目录，不得使用 production root；
- Python executable、OS、architecture、uv、gh、git 和 TLS client identities 在命令前后记录。

### 6.2 固定 acquisition CLI

CLI 不接受 version、URL、filename、hash、license、output filename 或 result 字段参数。它只读取
committed plan 和固定 repository root，按固定顺序执行：

1. 获取 exact PyPI version JSON；
2. 获取 exact Git tag object/peeled commit；
3. 获取 exact tag LICENSE；
4. 下载 committed lock 所列 exact wheels；
5. 在 import 前验证每个 size/hash；
6. 对 Nautilus wheel 执行 official GitHub attestation verification；
7. 在 verified local cache 上执行 offline frozen install；
8. fresh process 枚举并精确比较完整 installed-distribution name/version 集，验证 Nautilus metadata
   license、Python/platform，并证明没有加载任何 `nautilus_trader.adapters` 模块。

每个命令保存 exact argv、固定环境 allowlist、start/end、exit code、stdout bytes、stderr bytes、
byte count 和 SHA-256。stdout/stderr 在子进程运行期间分别以 4 MiB 上限主动读取，触限立即终止整个
进程组；timeout 后只允许固定的 bounded drain，逃逸并持有 pipe 的 descendant 不得阻塞返回。loader
按 command name 重放固定 executable path class，并要求四个 tool records 与前四条 version transcripts
逐字段一致。每个 wheel 的 curl 同时使用 committed lock 中的 exact size 作为 `--max-filesize`。任一
timeout、redirect drift、hash/size/tag/license/attestation mismatch、lock drift、
unsupported platform 或 transcript 缺失都结束为 INCONCLUSIVE。禁止改变源、版本、hash 或重试寻找更好
结果；只允许每个已预注册命令内部的固定网络 retry policy。

正式顺序先记录 uv/Python/git/gh identity，然后执行 PyPI version JSON、tag、license、按 lock 排序的
14 个 wheel 下载、SLSA、offline venv/sync/import，共 25 条 transcript。PyPI/license/wheel curl 都不
跟随 redirect；每个 wheel transcript 必须同时绑定 HTTP 200、exact effective URL、filename、size 和
SHA-256。下载不得再通过未记录的 urllib/浏览器路径完成。

wheel 和大体积传递依赖不进入 Git。Git 只封存 plan、lock、精确小型 transcript/metadata、hash、
license bytes/record 和 supply-chain receipt。Actions cache 不是事实源，cache miss 必须重新按 hash 验证。

## 7. 阶段 2：零网络 Sandbox

### 7.1 方向明确的数据边界

```text
fixed ETHUSDT 4H fixture
        +
Decision / Target / Risk authorization
        |
        v
canonical request v2
        |
        | one fresh CPython 3.12 process / one BacktestEngine
        v
Order / Fill / Position / Fee events
        |
        v
canonical result v2
        |
        | read-only Evidence Adapter in current core
        v
canonical comparison v2
```

Nautilus 不重新计算策略 decision。它必须原样绑定 decision/target/risk IDs 和 hashes，再将授权转换为
order intent。当前 reference 是比较事实源；sandbox result 永远标记
`NON_AUTHORITATIVE_COUNTERFACTUAL_SANDBOX`。同一订单/持仓不能同时由两套系统拥有。

### 7.2 固定场景

同一 ETHUSDT Spot 4H fixture 固定 21 根闭合 bars、instrument precision、tick、step、minimum quantity、
minimum notional、maker/taker fee、starting cash/position 和 BBO/execution events。场景固定为：

- `IMMEDIATE_FULL`：完整 order/fill/fee/position/PnL；
- `PARTIAL_THEN_FULL`：事件顺序、累计成交、单一最终经济状态；
- `BELOW_MINIMUM_REJECTED`：零 fill/fee，仓位和现金不变；
- `FRESH_PROCESS_REPLAY`：第二个全新进程产生相同 semantic result hash。

tick/step rounding、min-notional、fee currency/rate/amount、average price、cost basis、realized/unrealized
PnL 全部使用 canonical Decimal strings；禁止 JSON float、NaN、手工 PnL 或手工 fee override。

### 7.3 零网络和权限

执行阶段只使用 verified local cache/venv，清除 proxy、cloud、交易所和 broker-shaped 环境变量；安装
Python socket sentinel；只 import low-level backtest/model modules；禁用 live adapter discovery。测试只
证明固定代码路径的 network count 为 0，不宣称 Nautilus 整个包没有网络能力。

固定 counters 必须全部为 0：

- credential access；
- account request；
- market network request；
- live Broker call；
- real order write；
- production state write；
- service/Runner/scheduler invocation。

## 8. Artifact 和 loader 合同

新增 v2 合同，不修改 v0.63 v1 schemas：

- `nautilus-e2e-spike-plan-v1`；
- `nautilus-supply-chain-receipt-v2`；
- `nautilus-sandbox-request-v2`；
- `nautilus-sandbox-result-v2`；
- `nautilus-sandbox-comparison-v2`；
- `nautilus-formal-completion-v1`。

所有 canonical JSON 必须唯一编码、无 duplicate keys、LF 结尾、self/business hash 可重算、unknown field
拒绝。公开 Git artifact 父目录允许 `0700` 或 `0755`，但必须 owner-owned、owner 可访问且 group/world
不可写；正式 ceremony 子目录和 acquisition/execution temp roots 保持 `0700`。loaders 使用 no-follow
descriptor、regular/uid/mode/nlink/size/attachment 门和 bounded
read。publisher 使用 noncanonical nonce staging、same-fd readback/fsync、atomic no-replace 和 directory
fsync；任何 partial final、symlink、hardlink、FIFO、wrong mode、different bytes 或 fsync failure 都失败关闭。

单个 formal ceremony 先以 no-replace 创建固定 owner-only 正式容器并保持其 descriptor；receipt、request、
result 和 comparison 分别通过 nonce staging + atomic no-replace 发布。随后从 retained descriptor 完成整套
production replay 与 committed-plan binding，最后才发布独立 `nautilus-sandbox-complete-v0.65.0.json`
完成标记。正式目录 entry 在任何一次性 acquisition 前必须通过 parent-directory fsync 耐久化。不允许
按名称 rename 一个已验证目录，因为目录 entry 可在验证与 rename 之间被替换。正式容器
一旦存在就禁止重跑；崩溃留下的无 completion marker 部分目录只作为失败证据，不是完成结果，也不会再次请求
网络以寻找不同结论。

确认完成前必须从 retained formal descriptor 读取不含完成标记的 exact 文件名集合，用 production schema/loader
重放 receipt、request、first/replay result 与 comparison，并验证 comparison mode、bindings、
runner invocation count、summary 以及传入 ceremony 的 committed plan identity 一致。replay 返回 exact
bytes 与仅在当前发布事务内使用的 dev/inode snapshot；marker 必须经 retained formal descriptor 发布，
并在发布前后逐项比对 exact set、bytes/hash 和临时 identity，禁止按路径重新打开正式目录。完成标记
使用 strict mirrored schema，持久化绑定 plan、comparison 和所有组成文件的可移植 name/size/SHA-256，
不持久化 checkout 之间不稳定的 dev/inode。production formal-set loader 必须独立枚举并散列实际 sibling
files，再以这些实际值验证 marker；不得信任调用者提供的 file manifest。空目录、缺文件、
多文件、非 canonical bytes 或任一 loader 失败都不得产生完成标记。

正式 artifacts：

- `artifacts/nautilus-sandbox/nautilus-e2e-spike-plan-v0.65.0.json`；
- supply-chain receipt 与小型 raw transcripts；
- fixed request、first result、fresh-process replay result；
- final comparison/report；
- 最后发布、绑定整套文件 hashes 的 formal completion marker。

首次 final report 永久有效。不得删掉失败结果、修改阈值或重跑寻找更好分类。

## 9. 差异分类与采用门

每个字段差异必须属于：

- `EXACT_MATCH`；
- `EXPECTED_ENGINE_REPRESENTATION_DIFFERENCE`；
- `ROUNDING_POLICY_DIFFERENCE`；
- `FILL_MODEL_DIFFERENCE`；
- `FEE_MODEL_DIFFERENCE`；
- `POSITION_ACCOUNTING_DIFFERENCE`；
- `PNL_ACCOUNTING_DIFFERENCE`；
- `RESTART_SEMANTICS_DIFFERENCE`；
- `UNSUPPORTED_INSTRUMENT_RULE`；
- `SUPPLY_CHAIN_OR_LICENSE_FAILURE`；
- `SAFETY_BOUNDARY_VIOLATION`；
- `INVALID_OR_INCOMPLETE_EVIDENCE`。

`ADOPT_FOR_PREREGISTERED_SHADOW` 要求：供应链/SLSA/license 全部 verified；四个场景通过；所有安全
counters 为 0；fresh replay 相同；所有经济差异为 exact match 或预注册允许的纯 representation
difference；无 rounding/fill/fee/position/PnL/restart/instrument/safety 未解决差异；独立审查
Critical/Important 为 0。

任何已证明的不兼容或实际观察到的 credential、network 或 second-engine 安全边界违反为
`REJECT_KEEP_CURRENT_CORE`。证据缺失、一般 runner 失败或运行环境不可用为
`INCONCLUSIVE_KEEP_CURRENT_CORE`。三种结果都不改变现有 System Paper/replacement 事实源。

## 10. 公共 GitHub Actions 策略

仓库已经公开，因此不再设计私有 Actions 额度降级路径：

- 保留现有 Ubuntu Python 3.9/3.12 core matrix；它重放 schemas/loaders/committed evidence，不安装
  Nautilus；
- 新增独立 required `nautilus-sandbox (3.12, macos-15 arm64)` job，与 core jobs 并行；
- runner label 使用 `macos-15`，但 job 必须实测 `sw_vers`、`uname -m=arm64` 和 Python identity，
  不能只凭 label 推断；
- cache key 必须包含 exact wheel SHA、uv.lock SHA、Python ABI 和 runner OS；cache hit/miss 都重新验证
  bytes/hash；
- acquisition 可联网，sandbox execution step 必须使用 offline verified environment；
- CI 重放 committed first result 并要求 exact semantic equality，不生成或选择新的研究结论；
- PR CI、merged-main CI 和 annotated tag identity 都是发布门。

不再创建 R4、额度镜像仓库、降级 CI 或手工替代 GitHub evidence。

## 11. 故障矩阵

至少覆盖：

- wrong package/version/wheel size/hash/tag/commit/license/SLSA/transitive lock；
- wrong Python/OS/architecture/runner label assumption；
- transcript missing/truncated/noncanonical/changed argv/exit code；
- request/result duplicate key、unknown field、float/NaN、hash tamper；
- tick/step/min-notional boundary；
- fill reorder/overfill、fee/position/PnL tamper；
- live adapter import、credential-shaped env、socket attempt；
- production path read/write、service/Runner invocation；
- result collision、symlink/hardlink/FIFO/wrong mode/partial write/fsync failure；
- crash before final publish and fresh-process nondeterminism；
- current System Paper/replacement artifacts or state identity changed。

所有拒绝路径必须保持 external sentinel bytes/mode/size/mtime/ctime/inode/nlink 不变，并且 production
write counters 为 0。

## 12. 明确不影响

v0.65 不修改或调用：

- System Paper、Challenger、replacement Runner/scheduler/maintenance；
- production root、plist、LaunchAgent、SQLite/WAL、logs、receipts 或 90 天起点；
- root runtime dependencies；
- credentials、accounts、balances、market/live Broker 或 real orders；
- v0.63 committed artifacts；
- v0.64 supersession plan/evidence/attestation/record。

v0.65 不安装任何长期服务。所有运行只发生在 isolated worktree、owner-only temp root 和公开 CI
ephemeral runner 中。

## 13. 发布门与停止条件

- spec 和 plan 先冻结；
- 每项功能严格 TDD：精确 RED、最小 GREEN、重构；
- code/lock review 后再发布 immutable preregistration plan；
- formal acquisition 和 sandbox result 各执行一次，不选择更好结果；
- focused/adjacent tests；最终代码状态本地 full 一次；
- 独立完整审查一次，修复后只定向复审；
- 公共 PR core 3.9/3.12 + macOS 3.12 sandbox job 全绿；
- exact merged-main CI 全绿；
- annotated `v0.65.0` peeled commit 等于 origin/main。

任一 schema、loader、hash、license、attestation、CI、tag、permission 或 safety boundary 失败都停止发布
或形成冻结的 REJECT/INCONCLUSIVE 结果。不得为了发布成功放宽合同。

## 14. 非目标与声明边界

v0.65 不证明 Alpha、盈利、AI 优势、Paper 完成、Canary 或实盘资格。即使 ADOPT，也只获得设计一个
独立、预注册、无权限实时 Shadow 对照的资格；不得自动安装、不创建 key、不入金、不下单。
