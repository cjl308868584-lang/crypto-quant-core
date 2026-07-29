# 实施追踪 v0.35.0

日期：2026-07-29

状态：首个预注册 Challenger 槽位已真实记录并交叉验证

## 本版本完成

- 使用冻结的 `v0.34.0` observer 只读验收真实首槽；
- 绑定 v0.33 install receipt、82 文件私有执行快照、v0.32 contract 与目标 plist；
- 重放 SQLite 首条 canonical decision 和 decision chain；
- 验证唯一 source bundle、candidate decision、原始 HTTP receipt 与 probes；
- 绑定 stdout 第 6 行唯一 `RECORDED` 和空 stderr；
- 封存 runtime receipt 的 exact canonical bytes；
- 新增 committed receipt 的 Schema、自哈希、固定语义与安全边界回归；
- 修复安装器预检写入 bytecode cache 的跨平台副作用；
- GitHub CI 固定 Asia/Shanghai、Python 构建工具和当前 Actions major，并消除功能
  分支的重复 push/PR 矩阵。

## 真实首槽证据

- forward start：`2026-07-29T00:00:00.000Z`；
- recorded at：`2026-07-29T00:02:06.752Z`；
- observed at：`2026-07-29T00:15:46.913Z`；
- record deadline：`2026-07-29T04:00:00.000Z`；
- LaunchAgent runs / last exit：`6 / 0`；
- decision count：1；
- action：`ENTER_LONG`；
- decision eligibility：`LOCAL_PREQUENTIAL_RESEARCH_ONLY`；
- broker eligibility：`INELIGIBLE_NO_BROKER_ACCESS`；
- decision hash：
  `c7ee6bfac0ac1da6986a9eb5089cc6cc8e2de520937935edbb8df45731b34ac7`；
- source bundle hash：
  `43c7f55aefca8ccea6f204747b8e10d474cd31368c1dbf548c310b6ea16d28bf`；
- state SHA-256：
  `3d79a67cc8e917c00a7b620e67f82aa47b9985bbcdd1eaa663222a8a6247e0b9`；
- stdout prefix SHA-256：
  `0262f4ce551b09b201b0b4a317f50962523433df4b1f4fb69a3dced8a62ada95`；
- stderr：0 bytes；
- observer launchctl/network/state-write/Broker/order：`1/0/0/0/0`。

Runtime receipt：

- id：
  `challenger_first_slot_receipt_fcc86fe447ab8b2728a9bcd80371c26c9a30f59cec0b01306b278392b28d3c2b`；
- self hash：
  `76acd1f21dbd0f4c71b45213a4d4d3983f7c3707ac77006b56da2675ecfa9521`；
- file SHA-256：
  `b1b03bbe584386d3199cef3561fe22b4c92c3f359429ec43838d2b00a9566e43`；
- uid/mode/link/size：`501 / 0600 / 1 / 19463`。

Git 副本
[challenger-first-slot-receipt-v0.35.0.json](../artifacts/challenger-forward/challenger-first-slot-receipt-v0.35.0.json)
与 runtime 原件逐字节一致。

## 验证

- v0.35 receipt focused tests：9/9；
- 观察器、安装器、Runner 相邻回归：28/28；
- 全量 tests：536/536；
- Golden Vector：41；
- Evaluator build input：162；
- Build input tree hash：
  `d34632f2a2dd62f0929a8ba6ec4e127549bf2a2ce8c840d6ed56d9a3a111e6ae`；
- Evaluator build hash：
  `04baefa0db832b22bcf61106da07158514b06d71756e48b8d46099ac233406c9`；
- `make validate`：完成；发布门禁保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 仍未证明

- 首条 decision 尚未形成成熟退出和实现收益；
- 没有连续 90 天 Paper、真实成交、实际滑点或账户级完整成本；
- Binance server time 不是独立第三方时间锚；
- AI 臂仍无获批模型，不能声称优于简单基线；
- 系统仍无 Broker、余额读取或真实下单能力；
- 本证据不构成盈利、正式 OOS、Paper 或生产资格。

## 下一步

保持 LaunchAgent 和 registration 不变，继续按 UTC 4h 网格积累不可回填的
Challenger decision。先观察当前 `ENTER_LONG` episode 的预注册退出过程与完整成本，
再评估连续样本；成熟结果出现前不启动新的 AI 模型搜索。
