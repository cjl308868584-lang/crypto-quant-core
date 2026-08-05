# System Paper 运维手册

版本：v0.61.0  
当前状态：`PLAN_FROZEN_PAPER_NOT_STARTED`

## 1. 当前唯一允许的结论

System Paper 已完成计划、模拟 Broker、单槽闭环、WAL 恢复、部署信任链、固定 90 天评估器、
tail-blind 投影和只读控制台的代码发布准备，但生产运行根、LaunchAgent、install receipt、start
receipt 和 90 天证据均不存在。代码和测试通过不等于已经安装、启动或盈利。

生产根固定为：

`/Users/chenm4/Library/Application Support/CryptoQuant/system-paper-v1`

目标 plist 固定为：

`/Users/chenm4/Library/LaunchAgents/local.crypto-quant.system-paper-v1.plist`

服务固定为：

`gui/501/local.crypto-quant.system-paper-v1`

在新的受限安装设计获得独立发布前，只允许以下只读确认：

```bash
test ! -e '/Users/chenm4/Library/Application Support/CryptoQuant/system-paper-v1'
test ! -e '/Users/chenm4/Library/LaunchAgents/local.crypto-quant.system-paper-v1.plist'
/bin/launchctl print gui/501/local.crypto-quant.system-paper-v1
```

前两条必须返回 0；第三条必须返回 service not found。任何相反结果都是未经预期的生产边界
变化，立即停止项目推进并保存只读取证结果。

## 2. 未来安装授权门

未来受限安装必须有一个独立语义版本冻结以下内容后才可执行：

1. 精确的 `origin/main`、annotated tag、package 和 build manifest 身份；
2. 固定 contract、plist、production roots 和 owner/mode/inode 约束；
3. preflight 的执行时刻、网络 allowlist、输出路径和失败取证规则；
4. installer 的唯一允许 `launchctl print → bootstrap → print` 序列；
5. 首槽 observer 的自然窗口和 start receipt 发布安排；
6. System Paper 与 replacement Challenger 各自独立的启动时刻和 90 天计时规则。

v0.61.0 不满足这项未来授权门。不得因为 Web 显示 `HEALTHY`、测试通过或当前机器空闲而提前
创建目录、渲染 contract、执行 preflight、安装 plist 或加载服务。

## 3. Preflight 的未来验收解释

只有冻结 contract 和 plist 已由 production loader 重放后，未来授权执行者才可调用
`crypto_quant.system_paper_preflight_cli`。它必须同时证明：

- 当前用户、macOS GUI domain、时区和系统时钟满足冻结要求；
- release checkout、tag、origin/main、package 和 manifest 完全一致；
- System Paper roots 与 Challenger roots 没有路径或 inode 重叠；
- owner、`0700` 目录、`0600` 文件、single-link、本地文件系统和至少 5 GiB 空间有效；
- 重启与常在线证据不会跨过 4 小时槽位；
- 仅固定 public time/ping preflight 请求发生，凭据、账户、Broker 和订单权限均为零；
- target plist 和 service 不存在冲突。

唯一可安装状态是 `PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE`，且 receipt 在冻结的 30 分钟窗口内。
任何 FAILED、过期、路径身份变化、网络偏差或 identity 不一致均不授权安装。失败 receipt 只能
用于取证，不能通过修改文件或重跑来寻找一个成功结果。

## 4. 安装与首次自然槽

未来 installer 不得 `kickstart`、`start`、`enable`、`submit` 或调用 runtime。它只允许在精确
preflight 授权下安装 `0600` plist 并 `bootstrap`。`RunAtLoad=false`，所以安装和登录不能制造
槽位。

安装成功后只等待日历自然触发。System Paper 的 UTC 4 小时槽在北京时间每天
`00:05、04:05、08:05、12:05、16:05、20:05` 进入 capture/run window。不得手工调用
Runner、runtime CLI、scheduler 或 maintenance，也不得改变系统时间。

首槽 observer 只可调用 `crypto_quant.system_paper_observer_cli`，且只读取 contract、plist、
preflight receipt、install receipt、LaunchAgent print、SQLite/WAL、stdout/stderr 和 slot
artifact。合法状态是：

- `WAITING_BEFORE_FIRST_NATURAL_SLOT`：尚未到自然槽；
- `WAITING_FOR_FIRST_NATURAL_SLOT`：窗口内尚无成功槽；
- `FIRST_NATURAL_SLOT_VERIFIED`：恰好一个自然成功槽；
- `FIRST_SLOT_OBSERVATION_WINDOW_MISSED`：第二槽已出现但首槽未封存；
- `FAILED_CLOSED`：槽位、日志、bundle、状态、路径或 loader 失败。

只有 `FIRST_NATURAL_SLOT_VERIFIED` 才允许未来冻结的 publisher 创建 exact-byte、no-overwrite
start receipt。90 天从 receipt 内首个真实 `scheduled_for` 派生，不能从计划日期、安装时间或
人工指定日期开始。

## 5. 每日只读检查

真实启动后，每日协调只读取并报告：

- LaunchAgent 是否为预期 label、program 和日历；
- state/WAL、stdout/stderr、slot artifact 的 stat、SHA-256 和 loader 状态；
- 已验证槽位、下一必需槽位、elapsed days；
- 模拟订单的 submitted/fill/partial/cancel/reject/timeout-UNKNOWN 计数；
- 对账、风险、incident 和 tail-blind gate 状态。

任何读取前后 stat/hash 变化、slot 缺口、非零退出、非法 stderr、UNKNOWN 未闭合、对账失败、
风险 HALT/HARD_BOUNDARY、loader/Schema/hash 不一致均进入失败取证。日常健康不创建 Git 版本，
也不读取 Challenger 的中期经济结果。

## 6. 事故取证与禁止修复

事故发生时按此顺序行动：

1. 停止任何会扩大状态的后续发布或启动工作；
2. 记录 UTC 时间、service print、文件 stat、SHA-256 和严格 loader reason code；
3. 保留原始 state/WAL、stdout/stderr、slot/bundle/receipt bytes，不覆盖、不移动、不规范化；
4. 将事件分类为临时 pending、可重放代码缺陷或永久 evidence failure；
5. 代码缺陷另开语义版本，用故障注入测试复现后修复，但不修改既有生产证据。

严格禁止：补槽、回填、改写时间、替换来源、删除 UNKNOWN、手工改 SQLite、复制别的 root、
重跑 final evaluator 寻找更好结果、改阈值、挑样本、创建凭据、查询账户、调用真实 Broker 或
下单。

## 7. 恢复接受条件

恢复不是“服务重新显示 running”。只有以下全部成立才可接受：

- 原事故 exact bytes 和 hashes 已保留；
- 冻结 loader 能解释恢复前后的不可变链；
- 没有缺槽、回填、跨 root 污染或 source 替换；
- UNKNOWN 订单按模拟 Broker 的冻结对账规则终结；
- ledger、position、order lifecycle 和 scheduler state 全部一致；
- 风险状态允许继续，且 production activation 和 real-order authority 仍为 false/zero。

永久缺槽或证据链断裂不能恢复为 PASS，只能保留 FAILED 或 INCONCLUSIVE。

## 8. 90 天终态

只有 start receipt 派生的 tail 已到、恰好 540 个连续槽、无 active slot、所有 input/result/state
可重放且证据自然完整时，才可使用 v0.59 冻结 evaluator 的七个 exact absolute paths执行一次
终态评估。不得手工传入时间、槽位、价格、费用、PnL、阈值、label、result id 或 filename。

首次有效结果无论是 `SYSTEM_PAPER_GATE_PASS`、`SYSTEM_PAPER_GATE_DID_NOT_PASS` 还是
`INCONCLUSIVE_INSUFFICIENT_EVIDENCE`，都必须 exact-byte 保存并作为独立后续版本发布。
PASS 只允许进入下一研究阶段；它不是盈利、AI 优势、Canary 或实盘资格。
