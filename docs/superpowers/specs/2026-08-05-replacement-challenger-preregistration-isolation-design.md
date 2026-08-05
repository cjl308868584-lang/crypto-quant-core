# Replacement Challenger Preregistration and Isolation Design

日期：2026-08-05

目标版本：`v0.62.0`

基线：annotated `v0.61.0` / `0811402ae4f9baebf905f548336ca2c29885ce9c`

适用分支：`codex/v0.62-replacement-challenger-plan`

## 1. 决策摘要

v0.62 只冻结 replacement Challenger 的 preregistration 与隔离合同。它发布一个
credential-free、不可变、可严格重放的计划 artifact、对应 Schema、production loader 和
回归测试，但不创建任何生产目录，不渲染 plist，不安装或启动 LaunchAgent，不调用旧或新
Runner，不请求市场数据，也不开始 90 天计时。

旧 confirmatory cohort 已因 4 小时槽位连续性缺口永久失败，旧服务已受控停用。replacement
不是恢复、迁移或续跑旧 cohort，而是使用相同决策规则语义、全新运行身份和全新证据根的
独立研究 cohort。它必须永久绑定旧 failure receipt 与 decommission receipt 作为
predecessor，保留失败事实，同时拒绝复制旧 decisions、Episode、receipt、archive、result、
PnL 或已运行天数。

本轮采用三层交付：

1. v0.62：preregistration、隔离合同、predecessor ancestry；
2. v0.63：新的 WAL runtime、exact prepared-input/result recovery 和故障注入；
3. v0.64：deployment、preflight、install、observer 与 start-receipt 信任链。

只有后续全部代码门和真实机器预检通过，才可另行授权安装。首次自然成功槽产生的 verified
start receipt 才能确定 cohort 起点；v0.62 不含固定日历起点。

## 2. 权威基线与 predecessor

### 2.1 v0.61 foundation

计划固定绑定：

- release tag：`v0.61.0`；
- peeled commit：`0811402ae4f9baebf905f548336ca2c29885ce9c`；
- package version：`0.61.0`；
- evaluator manifest version：`1.55.0`；
- build input tree hash：
  `b786255726e606fd8409ad668675ae35cefbb88a4d29f80d2cb8b92323812d76`；
- manifest hash：
  `e084ac0aa126824204f6f40fb89db52cd274e96abb96fd512ad6fdccd29eadb6`；
- manifest file SHA-256：
  `8e3b0f455238de170d55836ab0b76b1e2b41a894e540bf07c0e422a59e6e5296`。

### 2.2 旧失败链

计划固定引用以下 committed exact bytes：

| Source | Relative path | File SHA-256 | Business identity |
|---|---|---|---|
| Failure receipt | `artifacts/challenger-forward/challenger-cohort-missed-slot-failure-receipt-v0.54.0.json` | `7907b97d4447039c686f53dc62694c37836417b4ae555d3322b16478319b85ae` | receipt `challenger_cohort_failure_receipt_955e47c773683f1ae4ba7997a84badc373d3daf5afb24763bdc88d1b95d30545`, hash `3b2bcc2651bb80f58fb44d08ac4dfb2bdd9ab6c3ada4cfd83de00627ec8480b3` |
| Decommission receipt | `artifacts/challenger-forward/challenger-cohort-decommission-receipt-v0.54.0.json` | `540b831797228c950d954ee75b183fbeac08d63679463e14121fefc44fdf851f` | receipt `challenger_cohort_decommission_receipt_30f87c50715e9f4c09b9b21072cb8c3f6fecf932d2703300adcf153fbab9323e`, hash `56cfaa3f44b23e6dbc282f5947676ea93b4b92a89dcf90539a19eeb865b0bae7` |
| Old cohort plan | `artifacts/challenger-forward/challenger-episode-cohort-plan-v0.43.0.json` | `a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff` | plan `challenger_episode_cohort_plan_56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c`, hash `20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201` |
| Old evaluation plan | `artifacts/challenger-forward/challenger-cohort-evaluation-plan-v0.44.0.json` | `49e3b7642e163bb95c4ce01bc1c8d95a23b0cefce277d2f99f2e69029207a4d8` | plan `challenger_cohort_evaluation_plan_54a5456345f57219e2ee8763fd35dd4c753e843d31709f342e283fd4026eb037`, hash `a6901e7e721682e6d3e7ded9000b5f183ed35e694b7036c7b596c0555a3ab440` |

旧失败原因固定为 `CHALLENGER_RUNNER_MISSED_SLOT`，旧 cohort 资格固定为
`PERMANENTLY_INELIGIBLE_CONTINUITY_GAP`，旧服务固定为
`gui/501/local.crypto-quant.challenger-forward` / `local.crypto-quant.challenger-forward`，
真实后置状态为 `NOT_LOADED`且 service eligibility 为 `DECOMMISSIONED`。任何 loader 或未来部署链
看到 predecessor bytes、ID、hash、失败原因或停用状态不一致都必须失败关闭。

## 3. 方案比较

### 方案 A：改名复用旧 runtime root

优点是实现量最少。缺点是旧 SQLite、日志、source bundles 和 receipt roots 已属于永久失败
cohort，任何复用都会让新证据 ancestry 不可判定。本方案拒绝。

### 方案 B：v0.62 一次性交付完整 replacement runtime 与部署链

优点是表面上更快接近启动。缺点是把研究 preregistration、调度恢复、文件系统隔离和
launchd 权限合并为一个过大的审查面；任一缺陷都会迫使整条链重做。本方案拒绝。

### 方案 C：preregistration → runtime → deployment 分层（采用）

先冻结不可变研究和隔离身份，再让 runtime 与 deployment 分别依赖它。每层都能在无生产
副作用条件下独立测试、审查和发布，后续变更若触及策略或统计语义会显式创建新 evidence
scope，而不是偷偷改变运行对象。

## 4. 固定研究合同

replacement 继续研究旧 Challenger 的同一决策规则语义，但移除旧计划中已经过期的固定
`forward_start`。计划同时保存 predecessor policy identity 和新的 replacement policy hash，
从而证明阈值未变、时间 scope 已重置。

固定字段：

- mode：`REPLACEMENT_CHALLENGER_CONFIRMATORY`；
- route：`BASELINE_ONLY`；
- symbol/venue/direction：`ETHUSDT` / `BINANCE_SPOT` / `LONG_ONLY`；
- decision rule：FLAT 时 `latest/prior_sma20-1 >= 0.005` 且 5-bar log return
  `> 0` 才进入 LONG；LONG 最短持有 8h，此后 `latest <= prior_sma20` 退出，
  24h 强制退出，同槽 SMA 退出优先；拒绝入场不创建 Episode；
- predecessor policy id：`SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2`；
- predecessor policy hash：
  `2ef83c7c73fff8b163d9bad8527921bd0d87e60595680236e936254536c800e4`；
- hypothesis registration hash：
  `885b33d3a91eae1d5822fe12c16773a446c23e702f9a4110ef32f474157fa27f`；
- cadence：14400 秒；
- duration：90 个完整自然日；
- expected cohort slots：540；
- maximum Episode：24 小时，cohort window 结束后的 active Episode 必须自然跟随至退出；
- start source：`FIRST_VERIFIED_NATURAL_SLOT_FROM_START_RECEIPT`；
- start/end/tail 字段在 plan 中必须为 `null`，只能由未来 start receipt 派生；
- historical backfill、manual slot、window reset/extension、optional stopping 全部禁止。

旧 evaluation plan 的统计和经济方法保持 predecessor binding；replacement 专用 evaluator 必须
在启动前另行发布，并从本 plan 与 start receipt 派生日期。v0.62 不读取结果、不计算 PnL、
不形成 PASS/FAIL。

## 5. 固定运行隔离合同

未来生产身份固定为：

- label：`local.crypto-quant.challenger-replacement-v1`；
- service：`gui/501/local.crypto-quant.challenger-replacement-v1`；
- runtime root：
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1`；
- target plist：
  `/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist`。

根内只允许未来版本创建：

- `state/challenger-replacement.sqlite` 及 SQLite sidecars；
- `log/challenger-replacement.stdout.log`；
- `log/challenger-replacement.stderr.log`；
- `artifacts/source-bundles/*.json`；
- `artifacts/decisions/*.json`；
- `deployment/contract.json` 与 reviewed plist；
- `preflight-receipts/*.json`；
- `install-receipts/*.json`；
- `start-receipts/*.json`；
- `episode-receipts/*.json`、`archives/`、`results/`、`indexes/`、`evaluations/`。

目录必须为 owner-only `0700`，文件 `0600`、单 hardlink、no-overwrite。所有 ancestor 必须
拒绝 symlink。runtime root、plist、device/inode 和所有子路径不得与下列对象重叠：

- 旧 `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1`；
- System Paper `/Users/chenm4/Library/Application Support/CryptoQuant/system-paper-v1`；
- 任意 repository/worktree、`/tmp`、`/private/tmp`；
- 任意旧 state/log/bundle/receipt/archive/result inode。

v0.62 builder 和 loader 只处理内存与显式 plan 文件；不得检查或创建这些生产路径。真实
path/inode 检查属于未来 preflight。

## 6. 计划 artifact 与模块边界

新增：

- `src/crypto_quant/challenger_replacement_plan.py`；
- `config/challenger-replacement-plan-v1.schema.json`；
- `src/crypto_quant/schemas/challenger-replacement-plan-v1.schema.json`；
- `artifacts/challenger-replacement/challenger-replacement-plan-v0.62.0.json`；
- `tests/test_challenger_replacement_plan.py`。

公开 API：

```python
build_challenger_replacement_plan() -> dict
challenger_replacement_plan_hash(plan: Mapping[str, Any]) -> str
challenger_replacement_plan_reasons(plan: Mapping[str, Any]) -> tuple[str, ...]
load_challenger_replacement_plan(path: Path) -> dict
```

builder 不接受参数。plan 以各 policy section 的 business hash、整体 self-hash 和 stable plan id
绑定语义。loader 只接受绝对、非 symlink 的普通文件，限制 256 KiB，拒绝 duplicate keys、
JSON float/NaN、非 canonical bytes、未知字段、错误 self-hash、重算后仍与唯一 builder 不同的
语义以及任何 override。

计划不包含 URL、header、credential path、API key、账户 endpoint、Broker endpoint、订单
endpoint、历史价格、费用 override、PnL、outcome label 或人工日期。它只允许描述公开市场读取族，
不提供可执行网络地址。

## 7. 权限与状态

`authority` 固定：

- `credentials_allowed=false`；
- `account_requests_allowed=false`；
- `broker_requests_allowed=false`；
- `real_orders_allowed=false`；
- `production_activation=false`；
- `runtime_install_authorized=false`；
- `replacement_start_authorized=false`；
- `runner_invocation_count=0`；
- `market_request_count=0`；
- `state_write_count=0`。

status 固定为 `PLAN_FROZEN_REPLACEMENT_NOT_STARTED`。资格固定为 runtime、deployment、
start receipt 与 90 天证据均未完成；Canary、profitability、AI advantage 全部 ineligible。

## 8. 后续数据流

```text
v0.54 failure + decommission exact bytes
                  │
                  ▼
v0.62 replacement plan + isolation identity
                  │
                  ▼
v0.63 WAL runtime / recovery / fault injection
                  │
                  ▼
v0.64 deployment + preflight + install + observer
                  │
          first natural success only
                  ▼
immutable start receipt → independent 90-day clock
```

未来 runtime 可复用旧模块中纯函数形式的决策数学和严格 public Kline parser，但不得复用旧
`ChallengerForwardState`、旧 `_START`、旧 runner orchestration、旧 label 或任何旧路径。新
runtime 必须先 prepared input 持久化，再发布 bundle/decision，再原子提交状态，并对 crash
points 提供 exact replay；这些要求属于 v0.63。

## 9. 错误处理

所有错误以固定 reason code 失败关闭：

- `CHALLENGER_REPLACEMENT_PLAN_PATH_INVALID`；
- `CHALLENGER_REPLACEMENT_PLAN_JSON_INVALID`；
- `CHALLENGER_REPLACEMENT_PLAN_JSON_DUPLICATE_KEY`；
- `CHALLENGER_REPLACEMENT_PLAN_JSON_FLOAT_FORBIDDEN`；
- `CHALLENGER_REPLACEMENT_PLAN_CANONICAL_BYTES_REQUIRED`；
- `CHALLENGER_REPLACEMENT_PLAN_SCHEMA_INVALID`；
- `CHALLENGER_REPLACEMENT_PLAN_HASH_MISMATCH`；
- `CHALLENGER_REPLACEMENT_PLAN_SEMANTIC_MISMATCH`；
- `CHALLENGER_REPLACEMENT_PLAN_SEMANTIC_INVALID`。

builder 或 loader 失败时不得创建 plan、生产目录、数据库、日志、receipt 或网络请求。

## 10. 测试与发布门

- builder 100 次输出 exact canonical bytes；
- direct construction、参数和 override 不存在；
- plan 逐项冻结 predecessor、decision rule、540 槽、派生起点和新路径；
- old/new/System Paper roots、labels 与 relative paths 全部不重叠；
- predecessor committed file SHA、receipt/plan ID 和 business hash 与 plan 完全一致；
- Schema mirrors 逐字节一致且 Draft 2020-12 有效；
- duplicate key、float、unknown field、hash tamper、semantic rehash、relative path、symlink、
  oversized input 全部拒绝；
- source/AST 边界证明模块不导入网络、SQLite、subprocess 或 launchctl 代码；
- 构建/加载前后 production roots、plist 和 service 均不存在，network/Runner/state-write 为零；
- committed artifact 是 builder 的 canonical bytes 加单个换行，production loader 可重放；
- 新 Schema、module、test、artifact、设计、计划、ADR、实施状态和 README 进入 evaluator build；
- 最终代码状态本地全量一次、独立完整审查一次、修复后只做针对性复审；
- PR Python 3.9/3.12 CI、main CI、annotated `v0.62.0` tag 与 main identity 全部通过。

## 11. 非目标

v0.62 不实现或执行：

- runtime、SQLite、source bundle、decision 写入或故障恢复；
- deployment snapshot、contract/plist render、preflight、install、bootstrap、kickstart；
- observer、start receipt、maintenance、episode/economic pipeline；
- 市场、账户、Broker、订单或 credential 请求；
- System Paper 安装或启动；
- 中期或最终 PnL、收益率、胜率、统计 PASS 或 AI 优势判断。

## 12. 对赚钱目标的意义

旧 cohort 的漏槽说明运行连续性不足，不能通过迁移或回填修复。v0.62 把“同一决策规则的
新研究”与“旧失败证据”同时永久绑定，并先锁死服务、路径、样本和停止规则，防止以后因
结果不理想而改窗口、改阈值或挑证据。它本身不证明赚钱，但为能够被信任的下一次 90 天
检验建立了不可绕过的起点。
