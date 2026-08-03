# System Paper Deployment Trust Chain Design

日期：2026-08-03  
目标版本：`v0.58.0`  
基线：annotated `v0.57.0` / `6b103a5d962ca53c470f08573418be73929b63a7`  
适用分支：`codex/v0.58-system-paper-deployment`

## 1. 决策摘要

v0.58 交付一条独立、无凭据、失败关闭的 System Paper 部署信任链，但只发布代码，
不执行安装、不 bootstrap、不启动 Runner，也不开始 90 天计时。

本设计采用 System Paper 原生实现，不复用或泛化 Challenger 的 service、state、log、
bundle、receipt 或 evidence root。它补齐 v0.57 缺失的固定自然槽运行入口，并在任何真实
Paper 证据产生前修正市场输入的时间语义。部署链由六个边界组成：

1. 公共输入适配器与固定 runtime CLI；
2. 可重放的 LaunchAgent contract 和 plist；
3. 独立、不可变的机器 preflight receipt；
4. 仅由 verified preflight 授权的 installer 和 install receipt；
5. 完全只读的首次自然槽 observer；
6. 首槽 start receipt 的 exact-byte、no-overwrite 发布和 production loader。

v0.58 的完成状态只能是 `DEPLOYMENT_TRUST_CHAIN_CODE_RELEASED_NOT_INSTALLED`。
`production_activation.enabled=false`、无交易凭据、无账户权限、无真实 Broker、无真实订单
继续保持。即使所有测试通过，也不得声称 System Paper 已启动或能够赚钱。

## 2. 已发现的启动前契约缺口

### 2.1 缺少自然槽可执行入口

v0.57 只提供 `run_due_system_paper_slot(...)` library。现有路线文档已经列出
`system_paper_runtime_cli.py`，但 v0.57 未实现该文件。没有它时，任何 plist 只能指向一个
不存在的 module；发布 launchd/installer 骨架会形成不可运行的部署假象。

v0.58 必须把 runtime CLI 纳入同一版本，且 CLI 只能接受固定 `--state-path` 和
`--output-root`。它不得接受时间、URL、symbol、plan、成本、价格、fill scenario、凭据、
账户、Broker、订单或历史日期覆盖。

### 2.2 市场元数据时间不能回填

v0.56 的 market bundle 只有 `observed_at`，并把它固定为逻辑槽位边界；runtime 同时用该
时间验证 `InstrumentMetadata.effective_from`。真实 public exchange-info 是在槽位结束后
5 分钟的 capture window 内取得，其元数据只能从真实 capture 时刻起生效。把
`effective_from` 改写为槽位边界会制造回填证据，而保留真实时间又会被现有 verifier 拒绝。

因此 v0.58 在真实 Paper 尚未启动、没有任何 start receipt 或 cohort evidence 时修正规约：

- bundle 删除含义模糊的 `observed_at`，改为 `scheduled_for` 表示不可变的逻辑 4h 槽位；
- bundle 新增 `captured_at`，来自四个 receipt 的可信时间边界；
- `scheduled_for + 5m <= captured_at < slot.expires_at`；
- metadata 按 `captured_at` 验证有效性，禁止改写其 `effective_from`；
- scheduler envelope 的 `capture.captured_at` 必须与 bundle `captured_at` 完全一致；
- 每根 Kline 保留 `open_time`、`close_time`、`close` 和 `source_row_hash`，要求严格连续且
  最后一根在 `scheduled_for - 1ms` 关闭；
- 四个完整、规范化 source receipts 连同 raw UTF-8 response、response hash 和 receipt hash
  嵌入 bundle，production loader必须能离线重放它们；只保存四个hash不足以证明来源；
- source receipts、规范化 market facts和bundle hash共同绑定真实来源。

这是 pre-start contract correction，不迁移、不转换、不回填任何运行证据。v0.56/v0.57 的
业务计算golden assertions在更新source-evidence fixture后必须保持等价；仓库目前没有真实
System Paper slot artifact需要向后兼容。

### 2.3 首槽观察不能依赖每日 08:25 协调

System Paper 每 4 小时运行一次，而每日 08:25 自动化不能保证在第二槽前封存首槽。
v0.58 不新增一个会写策略 state 的维护服务，也不让 Runner 自证 start receipt。受限安装
阶段必须另行安排首槽后、第二槽前的只读 observer 调度。若 observer 看到零槽则 `WAITING`；
看到恰好一个 verified natural success 才可发布 start receipt；看到两个或更多槽但没有既有
start receipt时必须 `FIRST_SLOT_OBSERVATION_WINDOW_MISSED`，禁止追溯补发。

## 3. 方案比较

### 方案 A：泛化 Challenger 部署代码

优点是初始代码量较少。缺点是 Challenger 的本地时区、decision/source bundle、旧 service
label 和 cohort failure 语义都与 System Paper 不同；抽象层会扩大已冻结 Challenger 代码的
回归面，也增加跨 evidence root 污染风险。本方案拒绝。

### 方案 B：System Paper 原生独立信任链（采用）

新增小而明确的 Paper modules，参考成熟的安全模式，但使用独立 Schema、reason codes、
service label、paths 和 loaders。它同时补齐真实 public input adapter/runtime CLI，并在启动前
修复时间契约。代码量较大，但每个边界可独立测试，且能证明部署对象确实可运行。

### 方案 C：只发布 contract/installer 骨架

该方案把 runtime CLI 和真实 capture adapter推迟到未来版本。它能较快生成一个 v0.58，
但 plist 指向不存在或未验证的入口，不能满足“完整 deployment/install/observer/start receipt”
的原路线。本方案拒绝。

## 4. 固定信任根

v0.58 的 renderer 和 production loaders必须绑定以下 v0.57 foundation identity：

- annotated tag：`v0.57.0`；
- peeled commit：`6b103a5d962ca53c470f08573418be73929b63a7`；
- package version：`0.57.0`；
- manifest version：`1.51.0`；
- build input tree hash：
  `2f0e0b9b23db0338f8aee0a743fa54b3cc63459860d8b34d5385ffbf499141f3`；
- manifest business hash：
  `3a25f58a7ad715a937aa8a95a9b65ca7965b837df05f791ddcea1355239beada`；
- manifest file SHA-256：
  `f926a034fda40e036682d353e541ad3dddbd43248e5bcf74446124db400568a6`。

v0.58 的最终 manifest、main commit 和 annotated tag 只能在实现、审查、CI 和合并后确定。
renderer 不硬编码尚不存在的 commit；它要求当前 checkout：

1. `HEAD` 被 annotated `v0.58.0` 精确引用；
2. worktree clean；
3. `v0.57.0` 是 `HEAD` 的祖先且 peeled commit 等于上述 foundation；
4. packaged version 和 v0.58 manifest 与 checkout 完全重放；
5. origin 是 `cjl308868584-lang/crypto-quant-core`，远端 main 与本地 `HEAD` 相等。

这些检查只在未来 contract render/preflight 执行；代码发布本身不渲染生产 contract。

## 5. 模块边界

### 5.1 `system_paper_public_input.py`

职责：把四个冻结公开 GET 转为 `SystemPaperInputCapture`，不持久化、不调用 scheduler、
不接触任何私有接口。

固定请求顺序：

1. `SPOT_KLINE_4H_WARMUP`；
2. `SPOT_EXCHANGE_INFO`；
3. `SPOT_BBO`；
4. `SPOT_AGG_TRADE`。

它复用 `offline_paper` 的 request/transport/receipt parser，并新增公开、可测试的
`build_system_paper_market_bundle(...)` adapter。每个 family 仅一次尝试，总计恰好 4 个
network requests；异常即失败，不重试。返回的 bundle exact keys 固定为：

- `bundle_hash`、`provider`、`scheduled_for`、`captured_at`；
- `instrument_metadata_schema_version`、`instrument_metadata`；
- `closed_4h_klines`（每行仅 `open_time/close_time/close/source_row_hash`）；
- `bbo`（仅 `bid_price/ask_price`）；
- `source_receipts`（四个完整、可离线重放的规范化 receipts）。

production loader先重放四个 raw response，再重建 metadata/Klines/BBO 并与 bundle字段逐字节
比较。生产 transport 显式禁用环境 proxy，拒绝 redirect 到 allowlist之外、任意 URL、任意
symbol、任意 method和超限 response。

### 5.2 `system_paper_runtime_cli.py`

职责：调用一次 `run_due_system_paper_slot(...)`。

公开参数仅有：

- `--state-path <absolute owner-only sqlite path>`；
- `--output-root <absolute owner-only artifact root>`。

内部固定：

- `build_system_paper_plan()`；
- OS UTC clock，毫秒规范化；
- public input adapter；
- `FillScenario.partial_then_full("0.40")`；
- worker id 从固定 service label、pid 和本次启动身份派生，不能由 CLI 提供。

成功只向 stdout 输出一行 canonical summary；失败只向 stderr 输出一行 canonical error 并返回
非零。不得输出 raw response、secret、PnL 汇总或未冻结路径。恢复已 prepared input/result时
必须保持零新增 network request。

### 5.3 `system_paper_launchd.py` 与 CLI

固定 label：`local.crypto-quant.system-paper-v1`。

固定 schedule：UTC 4h 槽位结束后 5 分钟；在 `Asia/Shanghai` 本地时间表现为每天
`00:05, 04:05, 08:05, 12:05, 16:05, 20:05`。`RunAtLoad=true` 只允许 scheduler 对当前
自然槽做 idempotent due check，不提供手工槽位或回填能力。

plist `ProgramArguments` 只能是 reviewed execution snapshot 内的 Python，加
`-m crypto_quant.system_paper_runtime_cli --state-path ... --output-root ...`。禁止 shell、循环、
watcher、任意 command、环境凭据和 Challenger path。

contract 绑定：

- v0.57 foundation identity；
- v0.58 release checkout和完整 build manifest；
- source snapshot inventory及每个文件 SHA-256；
- plan hash、scheduler policy hash；
- plist exact bytes/hash；
- service/state/log/artifact/install/start/preflight roots；
- path modes和 security boundary。

renderer只生成 owner-only contract/plist；`launchctl_invoked=false`。CLI没有 install/start参数。

### 5.4 `system_paper_preflight.py` 与 CLI

preflight 是 installer 之外的独立、不可变 receipt。CLI只接受 `--contract-path`和
`--plist-path`；输出位置从contract推导。它只读验证：

- 当前 macOS user domain、uid/home、system timezone；
- release checkout/tag/origin/main/build identity；
- execution snapshot replay和 Python import/version；
- service label、target plist、所有 roots 与 Challenger 完全分离；
- runtime、receipt、log、state roots 的owner、mode、symlink/hardlink和 device identity；
- 至少 5 GiB 可用空间，state和artifact root位于预期本地 filesystem；
- 用户域可用、登录 session 存在、LaunchAgent 能在重启后由 `RunAtLoad` 恢复；
- sleep/always-on evidence 不允许出现会跨过 4h 槽位的配置；
- clock gate 使用冻结 `/api/v3/time` 三样本 verifier；
- network gate 只允许一次 `GET https://data-api.binance.vision/api/v3/ping`；
- credential env/file count、Broker authority、order authority均为零；
- target service和 target plist不存在冲突。

所有 command/network boundaries可注入，测试不得触达真实 launchctl或网络。真实 preflight
属于未来受限安装阶段；v0.58 发布期间调用次数必须为零。

只有在exact contract/plist已经通过production loader、固定output root可被可信推导后，后续
machine probe失败才可发布 `PREFLIGHT_FAILED_CLOSED` forensic receipt；contract/plist本身
无效时必须零写并返回结构化错误。失败receipt永远不能授权installer。只有
`PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE`、exact contract hash和未过期30分钟的receipt可以
授权一次install attempt。preflight receipt不授权Runner、Broker或订单。

### 5.5 `system_paper_install.py` 与 CLI

installer CLI inputs只有contract、plist和verified preflight receipt；install receipt root从
contract推导。
它重新运行所有离线 replay检查，并确认 preflight未过期、机器和 path identity未变化。

允许的 launchctl序列只有：

1. `launchctl print gui/<uid>/local.crypto-quant.system-paper-v1`；
2. 仅在 service不存在且 target无冲突时，原子安装 mode `0600` plist；
3. `launchctl bootstrap gui/<uid> <fixed-target>`；
4. 再次 `launchctl print` 验证 exact program/path/hash bindings。

installer不能 kickstart、start、enable、submit、bootout或调用 runtime CLI。若 bootstrap失败，
只移除本次新建且 inode仍匹配的 target；若 bootstrap已成功但 post-print失败，保留已加载配置并
发布失败取证，禁止假称回滚。install receipt exact-byte、mode `0600`、no-overwrite。

安装发生在未来独立阶段，不属于 v0.58代码发布。

### 5.6 `system_paper_observer.py` 与 CLI

observer完全只读。CLI inputs只有contract、plist、preflight receipt和install receipt。
它加载production loaders，保留
state DB/WAL、stdout、stderr和slot artifact的 file descriptors，前后比较 stat及 SHA-256。
唯一允许的外部 command是一次固定 `launchctl print`；network、scheduler、runtime、Broker、
order、state write计数都必须为零。

状态机：

- `WAITING_BEFORE_FIRST_NATURAL_SLOT`：尚未到 first eligible slot；
- `WAITING_FOR_FIRST_NATURAL_SLOT`：窗口内零成功槽且没有MISSED/FAILED；
- `FIRST_NATURAL_SLOT_VERIFIED`：恰好一个 natural `SUCCEEDED`，slot result exact loader重放，
  event chain、prepared input/result、log summary、launchd run count与install identity一致；
- `FIRST_SLOT_OBSERVATION_WINDOW_MISSED`：未封存start receipt前已出现第二槽；
- `FAILED_CLOSED`：MISSED/EXPIRED/FAILED、non-zero exit、非法stderr、hash/path/loader不一致。

CLI只打印观察摘要，不写 receipt或任何运行文件。

### 5.7 `system_paper_start_receipt.py` 与 CLI

publisher内部调用只读 observer；仅 `FIRST_NATURAL_SLOT_VERIFIED` 可以构建 receipt。receipt
绑定 exact contract、preflight、install receipt、LaunchAgent print、SQLite event chain、
prepared input/result、首个slot exact bytes、stdout/stderr和所有stat/hash evidence。

`cohort_started_at`只能从首个 `scheduled_for` 派生，`cohort_tail_end`固定为其后 90 个完整日的
同一UTC边界，`expected_slot_count=540`。CLI inputs只有contract、plist、preflight receipt和
install receipt，不得接受output root、日期、slot、filename、PnL或label。receipt只能写入
contract固定的owner-only start root，使用stable id filename、mode `0600`、exact-byte
no-overwrite。

pending不创建文件；failure只返回失败并保留既有证据；相同 exact receipt幂等，冲突绝不覆盖。
production loader必须从 contract、plist、preflight和install receipt重新推导全部身份并重放。

## 6. 固定路径和隔离

生产根在未来 render时固定为：

`/Users/chenm4/Library/Application Support/CryptoQuant/system-paper-v1`

其下只允许：

- `state/system-paper.sqlite` 及SQLite sidecars；
- `log/system-paper.stdout.log`；
- `log/system-paper.stderr.log`；
- `artifacts/system-paper-slots/*.json`；
- `deployment/contract.json`与plist；
- `preflight-receipts/*.json`；
- `install-receipts/*.json`；
- `start-receipts/*.json`。

根和子目录 `0700`，文件 `0600`。路径不得位于仓库、`/tmp`、symlink ancestor、Challenger
roots或其他 evidence root下；不得与任何现有 inode/hardlink重叠。测试使用临时绝对路径，
不得创建上述生产目录。

## 7. Schema和production loaders

新增并镜像以下 Draft 2020-12 Schema：

- `system-paper-market-bundle-v1.schema.json`；
- `system-paper-launchd-contract-v1.schema.json`；
- `system-paper-preflight-receipt-v1.schema.json`；
- `system-paper-install-receipt-v1.schema.json`；
- `system-paper-start-receipt-v1.schema.json`。

`config/`和`src/crypto_quant/schemas/`字节必须一致。所有artifact使用 strict JSON、拒绝
duplicate keys/binary floats/unknown properties，包含self-hash但不能用self-hash自证external
trust。loader必须验证owner、mode、single link、size bound、canonical bytes、schema、hash、
semantic replay和cross-artifact bindings。

## 8. 失败关闭与不可逆边界

以下任一情况立即停止：

- v0.57 foundation、v0.58 manifest/main/tag/origin不一致；
- public input不是四个固定GET或发生retry/redirect/proxy/私有endpoint；
- service、argv、path或artifact包含Challenger root；
- production activation、credential、account、Broker或real order authority非零；
- preflight失败、过期、机器/path identity变化；
- target/service冲突；
- SQLite event chain、prepared bytes、result loader、log或launchd evidence不连续；
- observer在第二槽后才尝试首次封存；
- owner/mode/symlink/hardlink/hash/Schema/loader不一致；
- exact-byte目标冲突。

禁止自动修复、补槽、回填、替换来源、删除未知文件或重跑寻找更好结果。

## 9. 测试策略

TDD顺序必须先红灯后实现：

1. market time correction和production public input adapter；
2. runtime CLI的固定authority、四请求和recovery零请求；
3. contract/plist replay、release identity和Paper/Challenger隔离；
4. preflight success/failure forensic、30分钟expiry和零安装；
5. installer command矩阵、atomic target和receipt loader；
6. observer WAITING/VERIFIED/MISSED/FAILED状态机与前后只读哈希；
7. start receipt exact publish、pending零写、production replay；
8. Challenger non-interference、完整System Paper、全量、compileall和`make validate`。

测试必须注入clock、transport、launchctl、system probe和filesystem fixtures。v0.58所有测试及
发布流程的真实network、launchctl、bootstrap、Runner、Broker和order调用数都必须为零。

## 10. 发布门

v0.58发布顺序固定：

1. spec提交；
2. implementation plan提交；
3. 按TDD小步实现并提交；
4. production loader和build manifest绑定；
5. 独立代码审查；
6. focused、adjacent、完整unittest、compileall、`make validate`；
7. 核验私有目标仓库、origin、main和ADMIN权限；
8. Draft PR、Python 3.9/3.12 PR CI；
9. 只合并reviewed head；
10. main CI成功后创建与main精确对齐的annotated `v0.58.0`。

代码发布期间严禁render生产contract、执行preflight、install、bootstrap、触发runtime或创建
start receipt。受限安装仍需等v0.59 evaluator、v0.60 tail-blind projection和v0.61只读
Web/alerts/runbooks全部发布并通过未来独立安装设计门。

## 11. 完成定义

v0.58只有在以下证据全部存在时完成：

- 所有新增modules、mirrored schemas和production loaders已提交；
- 真实 public input可通过注入fixture证明生成可被runtime接受的bundle；
- plist指向存在且测试过的runtime CLI；
- installer没有verified preflight绝不bootstrap；
- observer和start receipt不触发任何运行或市场行为；
- 891项v0.57基线保持通过，新增测试及全量验证通过；
- manifest、docs、版本、PR/main CI、annotated tag全部精确一致；
- 没有生产runtime root、install receipt、start receipt或90天计时被创建。

这只证明部署信任链代码可进入下一门，不证明系统赚钱、AI优势、Paper完成或实盘资格。
