# ADR-0062：Replacement Challenger 预注册与证据隔离

日期：2026-08-05

状态：已接受

## 背景

原 Challenger confirmatory cohort 因 `CHALLENGER_RUNNER_MISSED_SLOT` 永久失去连续性资格，
对应 failure receipt 与 decommission receipt 已在 v0.54 逐字节封存。继续使用旧 service、SQLite、
日志、bundle 或 evidence root 会把失败 cohort 和新样本混成无法审计的证据流；直接恢复或补槽也会
破坏事前冻结的 540 槽全纳入合同。

同时，System Paper 的启动前代码已经独立完成到 v0.61，但仍未安装或启动。replacement
Challenger 需要先获得自己的研究身份和隔离合同，之后才能分别实现 runtime 与 deployment，不能
为了追求同日起跑而扩大安装或运行权限。

## 决策

1. v0.62 只发布 parameterless builder、严格 Schema mirrors、production loader 和 exact plan
   artifact。状态固定为 `PLAN_FROZEN_REPLACEMENT_NOT_STARTED`。
2. plan 永久绑定 v0.54 failure/decommission receipts、v0.43 cohort plan、v0.44 evaluation plan
   的 committed file SHA、business ID 与 business hash。旧失败事实不可删除或重写。
3. replacement 继承相同的 SMA20/5-bar momentum/0.005 distance/8h minimum hold/24h vertical
   exit 规则语义，但不继承旧固定 `forward_start`。未来起点只能来自首次自然成功槽的 verified
   start receipt；90 天、14,400 秒 cadence 和 540 个连续槽从该 receipt 派生。
4. 新身份固定为 `local.crypto-quant.challenger-replacement-v1`、
   `gui/501/local.crypto-quant.challenger-replacement-v1` 与全新的
   `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1` root。
   旧 Challenger、System Paper、repository/worktree 和临时目录均不得成为其 runtime root。
5. 旧 decisions、Episodes、receipts、archives、results、PnL、槽位或已运行天数一律不迁移、
   不回填、不计入 replacement。只保留 failure ancestry。
6. builder 和 loader 无网络、SQLite、process、launchd 或生产 state 能力。loader 只接受绝对、
   owner-controlled、单 hardlink、非 symlink 的普通文件，拒绝重复键、float、非 canonical bytes、
   Schema/hash/policy/semantic 绕过，并与唯一 builder exact 比较。
7. 所有凭据、账户、Broker、真实订单、production activation、install、start、Runner、市场请求和
   state write 权限固定为 false 或零。v0.62 不创建 production root/plist，不执行 preflight、
   install、bootstrap、kickstart、Runner、scheduler 或 maintenance。
8. 后续按三个独立审查层发布：v0.62 preregistration/isolation；v0.63 WAL runtime、exact recovery
   与故障注入；v0.64 deployment/preflight/install/observer/start-receipt 信任链。

## 被拒绝方案

- 改名复用旧 root：实现量小，但 inode 和证据 ancestry 无法证明隔离，拒绝。
- 在 v0.62 同时实现 runtime、deployment 和安装：审查面过大，且会把不可变研究身份与机器副作用
  混在一个发布门，拒绝。
- 指定一个人工同日开始时间：可能伪造不存在的自然首槽，拒绝；两条流必须从各自真实 start
  receipt 独立计时。

## 后果

v0.62 使 replacement cohort 的研究对象、失败 ancestry、全新路径和零权限边界可由 tag source
独立重放，但没有让系统更接近真实下单权限。它不证明 runtime、部署、90 天连续性、盈利、AI
优势、Canary 或实盘资格。即使未来两个 90 天 evaluator 都通过，也只允许讨论后续极小资金
Canary 的独立设计，不自动安装、创建 key、入金或下单。
