# NautilusTrader Sandbox Isolation Spike Design

日期：2026-08-05

目标版本：`v0.63.0`

基线：annotated `v0.62.0` / `e0a9b3eb6a3f385ea259722e6613df8708e8fe5a`

适用分支：`codex/v0.63-nautilus-sandbox-spike`

## 0. 发布范围修订（实际终止分支）

本文原始设计保留了“供应链成功后执行 fixture/runner/result 对照”的条件路径。
实际执行在 frozen environment 未完整取得时进入失败关闭，因此 v0.63 的最终发布
范围只有：exact dependency metadata/完整 `uv.lock`、严格 owner-only loader、只读
preflight Evidence Adapter 与 `INCONCLUSIVE_BLOCKED` comparison/report。

后文中的 request/result Schema、ETH 4H fixture、current reference、runner、engine、Golden、
failure injection 和 fresh-process replay 均是条件路径，本版本未实现、未运行、未声称
完成，对应未验证文件从发布中删除。两次 fetch 只能作为会话 attestation；
exact transcript bytes 和外部 attestation 都不可用，所以不得称为 machine-replayable
failure receipt。本节对 v0.63 实际交付范围具有优先效力；条件路径若重启，必须
使用新语义版本和新预注册设计。

## 1. 决策摘要

v0.63 实现一条完全隔离的 NautilusTrader 离线兼容性 Spike，用于判断下一代订单、
成交、持仓、费用和重启语义是否值得通过薄 sidecar 复用成熟引擎。它不是当前
System Paper 或 replacement Challenger 的依赖，不替换任何已开始或即将开始的
90 天证据流，也不修改已暴露的决策、订单、成交、账本或评估证据。

本版本同时冻结一条架构收缩原则：项目继续自研不可伪造证据链、严格 loader、
fail-closed 边界、对账与研究门；通用回测引擎、模拟 Broker、通用订单生命周期、
行情/交易所适配、调度、发布编排、机器人和通用 UI 只保留当前必要修复，不再
平台化扩建。

## 2. v0.62 发布基线与当前状态

v0.63 只能从以下已验证基线开始：

- private repository：`cjl308868584-lang/crypto-quant-core`；
- remote `main`：`e0a9b3eb6a3f385ea259722e6613df8708e8fe5a`；
- annotated `v0.62.0` peeled commit：
  `e0a9b3eb6a3f385ea259722e6613df8708e8fe5a`；
- annotated tag object：`b33c0cf58a954f548f76792f0b7cf989dcf0900c`；
- PR #28 head：`93d37e62e5371aed0d27536011ed1ae9f5e6dedc`；
- PR CI run `31000847324`：Python 3.9/3.12 success；
- main CI run `31003846283`：Python 3.9/3.12 success。

v0.62 replacement plan artifact、old Challenger failure/decommission ancestry、System Paper v0.55–v0.61
合同和 v0.59 90 天 evaluator 继续有效。本 Spike 不迁移、回填、重置、改起点、更换事实源或
让任何旧证据重新资格化。

## 3. 方案比较

### 3.1 方案 A：当前 Python 3.9 进程内 import NautilusTrader

优点是调用链最短。缺点是 NautilusTrader `1.227.0` 要求 Python `>=3.12,<3.15`，且
`TradingNode`/`BacktestNode` 使用进程级全局状态，与当前 Python 3.9 兼容内核直接冲突。
本方案拒绝。

### 3.2 方案 B：立即建立独立长期服务或第二仓库

优点是操作系统和语言隔离最强。缺点是在未证明语义兼容前就增加长驻服务、安装、
发布、观测和第二个事实源。这会重复本项目正在削减的通用基础设施。本方案暂不采用。

### 3.3 方案 C：独立 Python 3.12 one-shot sidecar（采用）

当前系统通过 canonical JSON 请求文件输出已冻结的 Decision/Target/Risk 授权与固定 ETH 4H
fixture。独立 Python 3.12 进程只启动一个 low-level `BacktestEngine`，不导入任何 live adapter，
产生 Order/Fills/Position/Fees 事件后退出。官方文档明确建议固定、小体量、内存数据使用
low-level API；因此不为本 Spike 额外建 Parquet catalog 或 high-level node 配置。当前核心中的
Evidence Adapter 只读两边 exact artifacts 并生成差异报告。这是最小、方向明确、可拒绝的边界。

## 4. 官方供应链候选

信息来源只允许使用 [official installation documentation](https://nautilustrader.io/docs/latest/getting_started/installation/)、
[official architecture documentation](https://nautilustrader.io/docs/latest/concepts/architecture/)、
[official GitHub release](https://github.com/nautechsystems/nautilus_trader/releases/tag/v1.227.0)、
[official repository](https://github.com/nautechsystems/nautilus_trader) 和
[PyPI release metadata](https://pypi.org/pypi/nautilus_trader/1.227.0/json)。

固定候选：

- package/version：`nautilus_trader==1.227.0`；
- development status：Beta；
- `Requires-Python`：`>=3.12,<3.15`；
- official tag：`v1.227.0`；
- annotated tag object：`0ccb5b55879c072a6e07fc7cbe5297c53c378107`；
- peeled commit：`280ae1762df51a492a4ce71506a40b5c8706def5`；
- wheel：`nautilus_trader-1.227.0-cp312-cp312-macosx_15_0_arm64.whl`；
- wheel size：`145812901`；
- wheel SHA-256：
  `735fbbc0737be8f945ee641aeb0dbf0ea6b4c6111f11f10c244fe198f8158953`；
- license expression：`LGPL-3.0-or-later`；
- exact `LICENSE` Git blob：`5550e2db15f239ea8d3cf54bfa3b035eab8d3174`；
- exact `LICENSE` size：`7651`；
- exact `LICENSE` SHA-256：
  `ee907919ec88c9c017b1f8b608db20960b6598aefcc4fe58820bde955d65ed3c`。

候选运行平台固定为 macOS `>=15.0` ARM64 与 CPython `3.12.x`。当前开发机只读预检为
macOS `15.7.5` / `arm64` / CPython `3.12.13`。实施时必须另行生成全传递依赖锁和
全部 artifact hash；只锁顶层 wheel 不足以通过供应链门。

v0.63 不把 NautilusTrader 加入根 `pyproject.toml` 或根 `requirements.lock`。它使用
`sandboxes/nautilus/` 下的独立 Python 3.12 项目和 lockfile。任何 LGPL/NOTICE/重分发义务不清楚、
wheel/hash 不符、tag/commit 不符、传递依赖未锁定或平台不符都必须拒绝采用。

供应链获取与 sandbox 执行是两个独立阶段。获取阶段只允许 lockfile 固定的 PyPI HTTPS
artifacts，下载后必须在 import 前验证所有 hash；执行阶段必须使用已验证的本地环境并禁止全部
网络。供应链 HTTPS 不是市场、账户或 Broker 请求，不得被 sidecar 运行代码访问。

## 5. 事实源与数据流

### 5.1 唯一事实源

当前 System Paper/Challenger 仍是各自证据流的唯一事实源。Nautilus sandbox 是
`COUNTERFACTUAL_COMPATIBILITY_ONLY`，永不与当前系统共同拥有同一订单或持仓。它的订单 ID、
成交 ID、持仓 ID 和账本不能进入当前 runtime root、SQLite、WAL、receipt、index 或
90 天 evaluator。

### 5.2 边界方向

```text
frozen ETH 4H fixture
        +
current Decision / Target / Risk authorization
        |
        v
nautilus-sandbox-request-v1.json
        |
        | one CPython 3.12 process / one BacktestEngine
        v
Order / Fill / Position / Fee events
        |
        v
nautilus-sandbox-result-v1.json
        |
        | read-only Python 3.9 Evidence Adapter
        v
current reference + sandbox result -> comparison report
```

Decision/Target/Risk 不由 NautilusTrader 重新计算。sidecar 必须验证并原样绑定它们的
ID/hash，然后才能构造 sandbox order。这使“decision 比较”精确表示授权未被 sidecar
改写，而不是让第二个策略引擎成为决策事实源。

## 6. 文件协议

### 6.1 Request v1

Request 必须包含：

- schema/version/request id/self-hash；
- v0.62 foundation identity；
- dependency-lock id/hash 和预期 Python/platform/wheel identities；
- fixed fixture id/hash；
- ETHUSDT Spot instrument metadata：price tick、quantity step、minimum quantity、minimum notional、
  base/quote precision、maker/taker fee；
- 21 根已闭合 4H bars 与同一槽位 BBO/execution fixture；
- current decision id/hash、target id/hash、risk authorization id/hash；
- previous cash/position/cost/fees snapshot；
- 唯一允许的 offline scenario：`IMMEDIATE_FULL`、`PARTIAL_THEN_FULL`、
  `REJECTED`、`DISCONNECT_REPLAY`；
- authority counters 全部为零：credential/account/network/real Broker/real order/production write。

Request 不允许 URL、adapter name、credential name/value/path、account ID、live venue client、手工 PnL、
手工 fee 覆盖、随机种子、当前 production path 或任何已暴露 evidence path。

### 6.2 Result v1

Result 只允许包含：

- request/dependency/fixture/decision/target/risk exact bindings；
- runner build identity、Python/platform 实测值、Nautilus package version；
- normalized order events；
- normalized fill events；
- normalized position events；
- normalized fee events；
- final cash/position/cost/realized/unrealized/fees Decimal strings；
- tick/step/min-notional 接受或拒绝证据；
- first run semantic hash 和 fresh-process replay semantic hash；
- safety counters；
- result self-hash。

原始 Nautilus 对象、pickle、本地 cache/database、系统时间、随机状态、网络响应或凭据不能进入 Result。
所有商业数值使用 canonical Decimal string，不允许 JSON float/NaN。

### 6.3 Comparison report v1

Evidence Adapter 必须同时重放 exact dependency lock、request、current reference 和 sandbox result，
然后按字段比较：

- decision/target/risk binding；
- order side/type/quantity/acceptance；
- fill count/quantity/price/liquidity side；
- fee currency/rate/amount；
- position quantity/average price/cost basis；
- realized/unrealized PnL；
- tick/step/min-notional rounding/rejection；
- fresh-process replay/restart semantics；
- credential/network/Broker/order/production-write counters。

差异必须使用固定分类：

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

报告不得为了对齐而修改 current reference 或旧 evidence。任何差异都保留，只能在新的
future Shadow preregistration 中决定是否接受。

## 7. 进程、路径与权限隔离

代码中冻结候选身份，但 v0.63 不安装服务：

- reserved label：`local.crypto-quant.nautilus-sandbox-v1`；
- reserved service：`gui/501/local.crypto-quant.nautilus-sandbox-v1`；
- reserved root：
  `/Users/chenm4/Library/Application Support/CryptoQuant/nautilus-sandbox-v1`；
- reserved state root：`.../state`；
- reserved log root：`.../log`；
- reserved artifact root：`.../artifacts`；
- reserved plist：
  `/Users/chenm4/Library/LaunchAgents/local.crypto-quant.nautilus-sandbox-v1.plist`。

上述路径在 v0.63 实现前后都必须不存在，service 必须未加载。Spike 只允许在项目隔离
worktree 内的 ignored Python 3.12 virtual environment 和由测试创建的临时目录中运行。临时输出
只能通过显式 artifact review 进入 Git，不得进入任何 production root。

sidecar 只允许一次性 CLI，只接受绝对 `--request`、`--result` 与 `--dependency-lock`三个
路径。不允许 daemon、HTTP、socket、message queue、LaunchAgent、cron、Runner hook 或自动训练。

## 8. 安全边界

v0.63 全程固定：

- `production_activation.enabled=false`；
- `runtime_install_authorized=false`；
- `paper_start_authorized=false`；
- `replacement_start_authorized=false`；
- `sandbox_service_install_authorized=false`；
- `live_adapter_allowed=false`；
- `credential_reads=0`；
- `account_requests=0`；
- `market_network_requests=0`；
- `real_broker_calls=0`；
- `real_order_writes=0`；
- `production_state_writes=0`。

实施与测试必须清除常见交易所凭据环境变量，拒绝 request/result 中的凭据名称或值，
不 import Nautilus live adapters，并让测试中的 network sentinel 在任何 socket 连接尝试时立即失败。
这些措施只证明本 Spike 的固定路径无网络，不证明 NautilusTrader 全部代码无网络能力。

## 9. 重启与失败语义

首个 Spike 不实现 live cache 或持久化恢复。它实验两类语义：

1. 同一 exact request 在两个 fresh Python 3.12 进程中必须产生同一 semantic result hash；
2. 进程在结果原子发布前失败时，Evidence Adapter 必须报
   `INVALID_OR_INCOMPLETE_EVIDENCE`，不使用部分结果，不写 current state。

若 fresh-process replay 不稳定，或未来所需的 live restart/reconciliation 无法通过新的预注册
Shadow 计划验证，结论必须是拒绝采用，不能在本 Spike 中补造通用恢复引擎。

## 10. 采用门与报告状态

报告只能得到以下三种结论：

- `FUTURE_SHADOW_CANDIDATE`：供应链、许可证、Golden、故障、重放和安全门全部通过；
- `REJECT_KEEP_CURRENT_CORE`：已确定不兼容、不安全、无法锁定或收益不足以换取复杂度；
- `INCONCLUSIVE_BLOCKED`：官方 wheel/platform/license 或其他必需证据不可用。

`FUTURE_SHADOW_CANDIDATE` 只允许起草新的实时 Shadow 预注册计划，不允许安装、启动、
引入凭据、写 production state 或接管任何订单。`REJECT`/`INCONCLUSIVE` 不影响现有 90 天流。

采用所有必需条件：

1. version/tag/commit/wheel/hash/transitive lock 全部 exact；
2. LGPL-3.0-or-later 和 NOTICE/重分发记录完整；
3. request/result/report Schema 严格且 loader 可重放；
4. Golden 对照和所有故障测试通过；
5. safety counters 全部为零；
6. current evidence bytes/state/stat 前后不变；
7. 任何差异都已分类，无未解释差异；
8. 独立审查 Critical/Important 为零。

## 11. 最小 Spike 验收矩阵

### 11.1 Golden 场景

- ETHUSDT Spot，21 根已闭合 4H bars，一个确定性入场决策；
- `IMMEDIATE_FULL`：order intent、fill、fee、position、cash、cost basis、PnL 对照；
- `PARTIAL_THEN_FULL`：事件顺序、累计成交和单一经济结果；
- `REJECTED`：零成交、零费用、仓位不变；
- tick/step 四舍五入/向下取整边界；
- below-min-notional 拒绝；
- fresh-process exact semantic replay。

### 11.2 故障场景

- missing/wrong package version、wheel hash、tag/commit、license hash、transitive lock；
- wrong Python/platform/architecture；
- request duplicate key、float/NaN、non-canonical、unknown field、hash tamper；
- result duplicate/missing/reordered fill、overfill、fee/position/PnL tamper；
- unexpected live adapter import、credential presence、socket attempt；
- production path request/write；
- partial result、crash before publish、fresh-process nondeterminism；
- sandbox identity 与 current order/position identity 冲突。

任何故障都必须在 current production state write 之前失败，并产生固定 reason code 或无部分结果。

## 12. 文件影响清单

### 12.1 新增候选

- `docs/superpowers/specs/2026-08-05-nautilus-sandbox-isolation-spike-design.md`；
- `docs/superpowers/plans/2026-08-05-nautilus-sandbox-isolation-spike.md`；
- `docs/adr/0063-nautilus-sandbox-sidecar-boundary.md`；
- `docs/implementation-status-v0.63.0.md`；
- `config/nautilus-sandbox-dependency-lock-v1.json`；
- `config/nautilus-sandbox-request-v1.schema.json`；
- `config/nautilus-sandbox-result-v1.schema.json`；
- `config/nautilus-sandbox-comparison-v1.schema.json`；
- package Schema mirrors；
- `src/crypto_quant/nautilus_sandbox_contract.py`；
- `src/crypto_quant/nautilus_evidence_adapter.py`；
- `sandboxes/nautilus/pyproject.toml`、lockfile 和 one-shot runner；
- fixed ETH 4H request/current-reference/result/comparison fixtures；
- dependency/contract/adapter/Golden/failure tests；
- exact adoption/rejection report artifact。

### 12.2 只允许机械更新

- root package version；
- evaluator build manifest/version 与 frozen-input registry；
- Schema registry；
- README 文档索引与状态摘要；
- `.gitignore`，仅在独立 sandbox virtual environment 尚未被忽略时更新。

### 12.3 明确不影响

- `src/crypto_quant/system_paper_*`；
- `src/crypto_quant/challenger_*` 和 `src/crypto_quant/challenger_replacement_plan.py`；
- `src/crypto_quant/orders.py`、`ledger.py`、`instruments.py`、`risk.py`；
- 所有已提交 System Paper/Challenger artifacts、Schema、contracts、receipts、indexes 和 evaluators；
- root `requirements.lock` 的 runtime dependency set；
- 所有 production runtime root、plist、LaunchAgent、SQLite/WAL、logs 和 90 天起点；
- 当前 Web projection 的证据语义。

## 13. 停止扩建和延后项

以下项从 v0.63 起停止扩建，现有代码只做安全/证据缺陷修复：

- 新的通用 SimulatedBroker 场景和成交模型；
- 新的通用 order/position lifecycle 状态或多 venue 抽象；
- 新的通用行情/交易所 adapter 和 live Broker；
- replacement Challenger 专用 WAL/runtime 复制，直到 Spike 与 build-vs-buy 审计完成；
- 新的调度/发布/机器人框架；
- 通用交易 UI、操作按钮、通用图表和样式扩建。

保留且继续自研：

- exact evidence loaders、self/business hashes 与 trusted attestation 绑定；
- failure ancestry、no-overwrite 发布和 fail-closed reason codes；
- 项目独有的槽位连续性、固定尾部、研究门和不可回填语义；
- 账本/持仓/费用对账的证据适配层；
- 只读运维中与证据健康直接相关的视图。

vectorbt 只允许未来离线 Research 使用；Freqtrade 只作独立对照，不 import 为本项目库；
UI 优先现成只读观测工具，当前控制台只保留槽位、证据、风险与固定尾部视图。

## 14. 实现和发布门

- 使用独立 worktree/branch，不追加 v0.62 分支；
- 先红灯 contract/loader/adapter/Golden/failure tests，再实现；
- 不修改任何明确不影响文件；
- dependency lock 和 license record 必须能在不 import NautilusTrader 时由 Python 3.9 loader 重放；
- sandbox runner 必须在独立 Python 3.12 进程执行，根包仍支持 Python 3.9；
- 聚焦和相邻测试通过后，最终代码状态本地全量一次；
- 独立完整审查一次，修复后只做针对性复审；
- PR Python 3.9/3.12 CI、main CI、annotated `v0.63.0` 与 main identity 全部验证；
- exact Nautilus 对照只在隔离 Python 3.12 环境中执行一次，封存 result/report exact bytes；
- 为避免在 PR Python 3.9/3.12 全量 job 重复下载和安装 145 MB wheel，常规 CI 不安装
  NautilusTrader，只重放 dependency metadata、Schema、contract、Golden、failure tests 与已封存 bytes；
- 若未来需要在 CI 重新执行 sandbox，必须先作为独立设计审批，不得暗中增加根 CI 依赖或网络。

## 15. 非目标

v0.63 不：

- 安装或加载 LaunchAgent/service；
- 调用 System Paper 或 Challenger Runner/scheduler/maintenance；
- 替换自然槽位、事实源、账本或评估器；
- 请求市场、账户、Broker 或交易所网络；
- 读取或创建真实凭据；
- 写入 production state 或真实订单；
- 修改已暴露 evidence 来迫使对齐；
- 宣称 NautilusTrader 已采用、现有核心已替换、Paper 已完成、可持续赚钱、AI 优势、
  Canary 或实盘资格。

## 16. 对赚钱目标的意义

本 Spike 不提高收益预期，也不证明策略有 Alpha。它的价值是停止在非差异化基础设施上
持续投入，同时不牺牲本项目最有价值的证据可信与失败关闭。只有当成熟引擎在相同固定
fixture 下提供可验证、可重放、无新事实源的订单/成交/持仓语义，才值得进入下一个
Shadow 研究门。
