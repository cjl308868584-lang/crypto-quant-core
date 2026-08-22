# DecisionOpportunity and Binance Canary Governance Design

日期：2026-08-23

目标版本：`v0.69.0`（governance / plan-only）

基线候选：`v0.68.0` 本地 release candidate
`b65481cce9c8955f73da5b78ef2bd3c981f3be3c`

适用分支：`codex/v0.69-decision-opportunity-canary-governance`

## 1. 决策摘要

v0.69 只冻结一个新的、显式 superseding preregistration v3。它把 replacement
Challenger 从“90 天内 540 个槽位必须全部成功，漏一槽永久失败”改为每四小时一个
`DecisionOpportunity`：每个机会必须永久记录为 `OBSERVED` 或 `MISSED`，漏机会禁止回填
决策、行情或成交，但不会使整个研究流永久失效；后续自然机会可以继续。

同一 append-only canonical event log 支持两条不可混淆的验收轨道：

1. **Operational Qualification**：真钱前最短 7 个完整自然日模拟运行；异常、机会覆盖率不足、
   策略周期不足或产品生命周期覆盖不足时只能延期，不能提前通过。
2. **Economic Evidence**：从独立 start receipt 起至少 90 个真实自然日，禁止提前读取或宣称
   profitability PASS。它继续回答经济有效性，不被 7 天运行资格替代。

v0.69 同时预注册 Binance-only Canary 梯级，但不提供任何凭据、Broker、订单、资金或安装
权限。首轮真钱产品只允许 ETH/USDT Spot 做多和 ETHUSDT USDⓈ-M 永续做空；两者对同一
经济资产互斥，任何反向必须先完成撤单、归零与对账。Gate.io 仅保留为未来独立阶段，不进入
本计划的实现或 fallback。

这是研究对象与运行风险合同的实质变化，不得描述为 v0.64 的 storage-only correction，也不得
声称原研究假设保持不变。由于 replacement 尚未 installation/start、没有 start receipt、没有
canonical production event，允许在新证据与 accountable owner attestation 支持下进行一次
pre-start re-registration；旧计划、tag、attestation、supersession record 和 v0.68 代码 bytes
永久保留。

## 2. 方案比较

### 2.1 方案 A：原地修改 v0.64/v0.68

拒绝。已有 plan hash、Schema、start receipt 派生规则和 release identity 均会失真，无法证明
变更发生在结果暴露前。

### 2.2 方案 B：删除 90 天研究，只做 7 天 Paper 后上真钱

拒绝。7 天只能覆盖运行、安全和资金升级条件，无法证明策略长期经济优势；这会把工程可运行
错误包装成盈利证据。

### 2.3 方案 C：显式 v3 + 同源双轨验收

采用。一次 preregistration 明确重置研究合同；一条机会事件流派生运行资格和 90 天经济证据，
减少两套调度/存储基础设施，同时保留不同的结论边界。现有证据发布、no-overwrite、retained
capability、observer 和只读 UI 组件只在新合同下复用，不复制通用平台。

## 3. 不可变前序与发布前置

### 3.1 必须逐字节保留

- v0.64 plan：
  `artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json`；
  file SHA-256 `5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f`；
  plan ID
  `challenger_replacement_plan_65d85d60a534a917f45a1ffa5fc9d3f74d6d24995b900d31b8c73cd26f0bd97b`；
  plan hash `c9a1e5f74c52fbf23be5a1d27fd23c25f3601ed58133178fc25480391ab65705`。
- v0.64 supersession record file SHA-256
  `8e5dce22cfb21f7a87fe5756dadbef7736bad12e6343a1bb1c503bd609252dd8`。
- v0.64 owner attestation file SHA-256
  `321087e3af1ab854d41519252c77710462eee85b1a96a4b2910962e4f046baaf`。
- v0.67 deployment artifact file SHA-256
  `8e7e073e2bb23d1509884f53d19fac299d96f38e15f9773e3a0b7d0ff103bea0`。
- v0.68 release candidate commit
  `b65481cce9c8955f73da5b78ef2bd3c981f3be3c`，包括其 install/observer/start trust-chain
  设计、测试与失败关闭修订。

不得 amend、force-move、删除、重生成或把旧 artifact 重新解释为 v3。旧 v0.64 plan 的最终
disposition 只能是 `SUPERSEDED_BEFORE_START_RESEARCH_AND_OPERATIONAL_POLICY_CHANGE`；这不是
研究 PASS、DID_NOT_PASS 或运行失败。

### 3.2 v0.68 release foundation 门

正式 v3 plan artifact 不得在 v0.68 annotated tag、peeled commit、origin/main、PR/main CI 和
manifest identity 全部一致前生成。设计/测试可以基于上述 local candidate 开展，但 builder
必须从最终 v0.68 release identity 读取常量；若 tag 最终未指向 `b65481c...`，停止并重新审查
foundation，不自动改 hash。

### 3.3 Pre-start 资格

机器采集只能证明采集时：runtime root/plist/service/start-receipt/canonical-event
`NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION`。它不能证明历史从未发生后又被删除。

正式 supersession 还必须绑定新的 accountable owner attestation，其 exact declaration 必须：

- 标明签署者身份、uid 和 UTC 时间；
- 绑定 v0.64 plan、v0.68 release identity、v3 plan 和 machine evidence；
- 声明在采集前 replacement 从未 install/start、从未生成 start receipt 或 canonical
  production event、从未提交真实订单；
- 承认该历史声明是治理责任声明，不是代码或 OS snapshot 可以证明的机器事实；
- 声明一旦存在首个 v3 start receipt 或 canonical production opportunity event，禁止再次以
  pre-start 理由重置计划。

缺 attestation、当前机器事实不一致、Git/release history 不一致或 provenance 不完整均失败关闭。
不得代替 owner 签署。

## 4. V3 计划结构

### 4.1 允许改变的研究字段

v3 不再要求与 v0.64 的 `/scope`、`/decision_policy`、`/cohort_policy`、`/evidence_policy` 或
`/authority` byte-equal。supersession record 必须列出并绑定至少以下 semantic diff：

- Spot LONG-only → `ETH_DIRECTIONAL_MUTUALLY_EXCLUSIVE_SPOT_LONG_OR_PERP_SHORT`；
- all 540 slots required → DecisionOpportunity outcomes；
- single 90-day gate → 7-day operational + 90-day economic dual track；
- maximum leverage 1× → staged gross exposure hard cap 2×；
- no Broker/orders/credentials authority → future Canary authority remains disabled until a later exact
  activation record；
- existing percentage deployment stages → E0/E1/E2 fixed-capital ladder。

未列出的前序 lineage、old-cohort failure、no-backfill、no-AI-authority、no-interim-profitability、
owner-only roots、append-only event authority、no-overwrite 和 failure-closed guarantees 必须保持。

### 4.2 固定产品与方向

```text
venue                  BINANCE_ONLY
economic_asset          ETH
spot_instrument          ETH/USDT Spot
spot_direction           LONG_ONLY_UNMARGINED
perpetual_instrument     ETHUSDT USDⓈ-M perpetual
perpetual_direction      SHORT_ONLY
perpetual_position_mode  ONE_WAY
perpetual_margin_mode    ISOLATED
technical_leverage_cap   2x
```

账户级 authoritative exposure state 只有：`FLAT`、`SPOT_LONG`、`PERP_SHORT`。禁止同时拥有两个
非零产品敞口；禁止 Hedge Mode；禁止 Cross Margin；禁止现货借贷或保证金做多。

### 4.3 不变的决策频率

- 机会网格：UTC `00:00/04:00/08:00/12:00/16:00/20:00`；
- 自然调用：`scheduled_for + 2m`；
- 合法决策捕获窗口：闭区间
  `[scheduled_for + 2m, scheduled_for + 10m]`；
- 不允许 CLI 传入 scheduled time、sequence、decision、price、PnL 或 outcome；
- 研究策略的指标、warm-up、阈值若改变，必须另行形成新 hypothesis registration，不得在
  v3 实现阶段暗改。

## 5. DecisionOpportunity 事实模型

### 5.1 每个机会恰好一个 terminal outcome

每个确定性 `scheduled_for` 派生唯一 `opportunity_id`。canonical projection 对每个机会只允许：

```text
OBSERVED
MISSED
```

`OBSERVED` 必须绑定完整 source capture、decision、risk/simulation result 及其 canonical hashes；
在未来真钱阶段还必须绑定 order/fill/position/fee/reconciliation evidence。

`MISSED` 必须绑定 `scheduled_for`、`detected_at` 和唯一 allowlisted reason code，例如：

```text
PROCESS_NOT_RUNNING
CAPTURE_WINDOW_EXPIRED
PUBLIC_MARKET_SOURCE_UNAVAILABLE
CLOCK_OR_CONNECTIVITY_UNTRUSTED
PRECONDITION_FAILED_CLOSED
```

MISSED 不包含替代行情、重算决策、模拟成交或人工 price/PnL。terminal outcome 不可改写；后续
自然机会继续使用新的 opportunity ID。

### 5.2 恢复而非回填

fresh process 必须先 replay canonical log。若发现已过期而未记录的确定机会，只能按时间顺序
追加 `MISSED`，记录真实 detection delay；不得调用市场源重建旧 decision，不得创建假
`OBSERVED`。之后才允许处理当前仍在合法窗口内的机会。

重复 exact event 幂等返回；相同 opportunity ID 的不同 outcome 或内容固定冲突。序号竞争由
optimistic parent hash 失败关闭，上层 replay/rebase；状态层不挑 winner、不偷偷改 outcome。

### 5.3 机会连续性与健康

“连续”改为：自 start 起每个确定机会最终都有 terminal outcome，且 event 序列无缺口。它不再
表示每个机会都成功决策。`MISSED` 数、比例、连续 missed 数、reason 分布和 detection delay
必须进入只读投影；不得隐藏、删除或用之后成功机会抵消其历史事实。

## 6. 双轨验收

### 6.1 Operational Qualification

计时从专用 operational start receipt 绑定的首个自然 `OBSERVED` 开始，绝不使用 install、tag、
preflight 或人工日期。最早评估时间为 start + 7 个完整自然日，但通过还必须同时满足：

- `observed_opportunities / due_opportunities >= 0.95`；
- 当前没有 unresolved opportunity、order、fill、position 或 reconciliation 状态；
- 至少 3 个真实策略周期；周期定义为从 `FLAT` 进入产品、再回到 `FLAT` 的完整生命周期；
- Spot long 与 perpetual short 各至少一个完整开平周期；
- 没有 S0/S1、重复经济订单、未记录成交、灾难止损缺失、账本/仓位差异或持续连接不足；
- fresh-process replay、kill/restart、network interruption、partial fill、timeout/UNKNOWN、保护单
  replace 和 reconciliation 故障注入全部通过冻结测试矩阵。

不足时状态固定为 `PENDING_AUTOMATIC_EXTENSION`，start 不重置，坏窗口不删除。随着后续真实机会
增加，覆盖率可恢复；历史 MISSED 永久保留。任何 unresolved safety failure 则为
`FAILED_CLOSED_REQUIRES_INCIDENT_REVIEW`，不能靠延长时间自动解除。

7 天结果只能是：

```text
OPERATIONAL_QUALIFICATION_PASS
PENDING_AUTOMATIC_EXTENSION
OPERATIONAL_QUALIFICATION_DID_NOT_PASS
INCONCLUSIVE_INSUFFICIENT_EVIDENCE
```

PASS 只允许进入 E0 审批讨论，不证明盈利。

### 6.2 Independent 90-day Economic Evidence

独立 economic start receipt 可与 operational receipt 绑定同一首个自然 `OBSERVED`，但有独立
identity、tail 和 evaluator。尾部早于 90 个完整自然日时禁止生成 final artifact、读取累计
profitability gate 或宣称提前 PASS。

final evaluator 必须纳入所有 opportunities，包括 MISSED，并报告 missingness sensitivity。
经济 PASS 的最低证据门固定包括：

- 实际自然时间不少于 90 天；
- opportunity terminal coverage 为 100%，即每个 due opportunity 最终为 OBSERVED 或 MISSED；
- OBSERVED coverage 不低于 95%；
- 所有进入仓位后的 mark、fill、fee、funding、position 和 ledger 生命周期完整；
- 没有 unresolved safety failure 或选择性删除；
- 冻结的收益、回撤、成本和置信区间门全部满足。

低于 95% 或经济生命周期不完整只能输出 `INCONCLUSIVE`，而不是永久摧毁运行流；真实亏损或未
达到冻结经济阈值输出 `DID_NOT_PASS`。不得通过延长、重置或挑选窗口寻找更好结果；若研究团队
希望新假设，必须另建下一 preregistration。

## 7. 模拟与 E0/E1/E2 资金阶梯

### 7.1 钱真前模拟门

v0.69 不启动模拟。后续实现必须先以固定 Binance instrument rules 和真实公开市场输入运行
credential-free simulation；不允许 fixture 计入 7 天。模拟订单、成交、费用、funding、仓位、
保护单和 ledger 全部进入 canonical evidence。

### 7.2 固定阶梯

| Stage | 资金硬上限 | 实际毛敞口上限 | 最短墙钟 | 最少周期 |
|---|---:|---:|---:|---:|
| E0 | 100 USDT | 0.5× | 7 天 | 3 |
| E1 | 300 USDT | 1× | 14 天 | 5 |
| E2 | 1000 USDT | 2× | 30 天 | 10 |

每一级均要求 Spot 与 perpetual 各至少一个完整开平周期。资金上限与 gross exposure 上限必须
同时执行，取更小者；未使用资本不得视为可自动加仓授权。

E1 未获新的宽松数值授权，因此继承 E0 的 absolute loss boundaries：单 UTC 日亏损达到
2 USDT 后停止新增风险，累计 high-water-mark drawdown 达 5 USDT 后归零并失败。E2 使用用户
明确批准的 normalized boundaries：单 UTC 日亏损达到 2% 后停止新增风险，累计回撤达到 7.5%
后归零并失败。所有比较包含 realized、unrealized、fee 与 funding，并使用保守 mark。

任何一级只有首个 immutable final evaluator 可决定 PASS/DID_NOT_PASS/INCONCLUSIVE；不得重跑找
更好结果。晋级不会自动发生，每一级需要新的 exact activation approval。

## 8. 互斥、归零与订单事实源

### 8.1 单一 PositionAuthority

同一账户和 ETH economic asset 只能有一个 authoritative target chain。Spot 与 perpetual adapter
只执行该 chain 的产品特定 intent，不能各自维护独立目标事实源。

从 `SPOT_LONG` 切到 `PERP_SHORT` 或反向时，必须按顺序：

1. 冻结新增风险；
2. 取消并确认所有旧产品 active orders；
3. reduce/close 旧产品；
4. 通过交易所账户快照、fill stream 和本地 ledger 三方对账，确认旧产品数量精确为零；
5. 确认不存在 unresolved UNKNOWN、late fill 或 duplicate economic order；
6. 建立并确认新产品 disaster stop；
7. 才允许新产品增加风险。

任一步未知或失败时保持/进入 reduce-only，不能猜测成功。

### 8.2 经济订单幂等

每个 economic intent 有稳定 client order ID 和唯一 attempt chain。网络超时不能直接重发；必须先
查询并对账。不同 exchange order ID 对应同一 economic intent、未记录 fill、fill websocket/REST
不一致或 local/venue position 不一致均固定失败关闭。

订单、成交、费用、funding、position、protective order 和 reconciliation 事件由 Evidence Adapter
规范化进入唯一 canonical log。Nautilus/simulation 与 live adapter 均不是研究事实源；它们只产生
待验证事件。禁止两套 engine 同时成为同一订单或仓位的 authority。

## 9. 风险与事故

### 9.1 立即失败关闭条件

以下任何一项阻止新增风险；有仓位时进入预注册的保守 flatten/reduce-only 流程：

- unresolved `UNKNOWN`；
- duplicate economic order；
- unrecorded or conflicting fill；
- ledger/venue position mismatch；
- disaster stop missing/unconfirmed；
- account mode、margin mode 或 leverage 不符合合同；
- clock、market/account connection 或 user-data stream 不足；
- S0/S1 incident；
- credential permission、IP allowlist 或 withdrawal boundary 不可信；
- evidence append、fsync、loader、hash、root identity 或 observer failure。

S0/S1 后不得自动重启风险。事故解锁需要独立 immutable incident record 与用户明确批准。

### 9.2 凭据合同

未来 credential root 必须在仓库和所有 runtime artifact root 之外，owner-only、无 symlink、
single-link、固定 allowlisted path。API key 必须：

- withdrawal disabled；
- IP allowlist exact match；
- 仅启用 Spot trade、USDⓈ-M Futures trade 和必要 read 权限；
- 不允许 sub-account 管理、universal transfer、margin loan、options 或其他 venue；
- 值不得进入 Git、plist、stdout/stderr、receipt、异常或测试 fixture。

v0.69 Schema 中 authority 仍固定 credentials/orders/production activation = false。只有后续
Canary activation artifact 才能授予某一 exact stage、capital、product 和 expiry；默认仍为拒绝。

## 10. UI 与观测

复用 v0.61 loopback-only read-only console。仅增加 strict projection 已验证字段：

- due/observed/missed opportunities、coverage、consecutive misses、last reason；
- operational/economic elapsed days 与 next gate；
- current product、gross exposure、stage、capital cap；
- open/unknown orders、fills、position/ledger reconciliation、disaster stop；
- daily loss、drawdown、incident/extension state。

UI 不读凭据、不调用 Broker、不提供操作按钮或写 API，不影响核心 scheduler/runtime，也不具有
交易授权权力。

## 11. 版本边界

- **v0.69**：本设计、Schema/plan/supersession/attestation 治理 artifact；plan-only。
- **v0.70**：DecisionOpportunity event、projection、operational + 90-day evaluator、observer/UI
  projection；无凭据、无真钱。
- **v0.71**：Binance Spot/perpetual deterministic simulation adapter、互斥状态机、风险/对账/
  restart/fault evidence；仍无凭据、无真钱。
- **v0.72**：credential/install/preflight/Canary activation trust chain 与 E0/E1/E2 receipts；代码
  发布不等于安装、入金或启动。

若任一版本过大，允许按独立审查边界顺延版本号，但不得把 plan、runtime 和真钱 activation
合并为一个不可审查提交。Gate.io 只能在 E0 之后的独立设计版本评估。

## 12. v0.69 文件与权限范围

v0.69 implementation 最多新增：

- v3 plan Schema mirrors、parameterless builder/strict loader；
- pre-start machine evidence、owner attestation 和 supersession record Schema/loader；
- fixed-path crash-safe governance publisher；
- committed plan/evidence/attestation/supersession artifacts；
- ADR、status、README、version/build manifest 和测试。

本版本禁止：runtime/event migration、scheduler、market/account network、Binance SDK、credential
读取、Broker/order/fill、production root/plist、launchctl、资金、真钱、UI 修改、7 天或 90 天计时。

## 13. 可证伪验收标准

1. v0.64/v0.67/v0.68 frozen bytes 与 identity 精确不变；
2. v3 semantic diff 完整列出，不声称 hypothesis unchanged；
3. machine snapshot、Git/release history 和 owner attestation 三层缺一即不生成 supersession；
4. owner exact declaration 在生成正式 attestation 前单独展示并获明确批准；
5. plan 固定四小时机会、MISSED no-backfill、双轨验收、95% coverage 和所有 ladder/risk 数值；
6. v0.69 authority 全部保持 no credential/no order/no activation；
7. formal artifact 使用 retained capability、nonce staging、same-fd readback、file+dir fsync 和
   atomic no-replace，existing FIFO/symlink/hardlink/wrong owner/mode/bytes 均失败关闭；
8. focused/adjacent tests、final full suite、compileall、make validate、diff-check 与独立 review
   Critical/Important=0；
9. GitHub PR/main CI 与 annotated tag identity 在远端发布获批后验证；
10. 任何结果都不声称盈利、AI 优势、Paper 完成、Canary 或实盘资格。

## 14. 最早 E0 边界

E0 最早发生在 v0.69-v0.72 全部发布、独立安装/启动获批、首个自然模拟 start receipt 后至少
7 个完整自然日，并满足三周期、双产品完整周期及全部安全门。若 2026-09-01 才能开始模拟，
数学上的最早 E0 为 2026-09-08 之后；该日期不是承诺，任何覆盖不足或异常均自动延期。

E0 仍需独立批准 API key、IP allowlist、账户模式、100 USDT 资金、production install/start 和
第一笔真钱订单。E1、E2、事故解锁及未来 Gate.io 各自需要新的 exact approval。
