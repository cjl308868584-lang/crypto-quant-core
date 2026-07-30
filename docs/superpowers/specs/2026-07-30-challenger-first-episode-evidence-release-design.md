# v0.41 Challenger 首个 Episode 完成证据发布设计

日期：2026-07-30

状态：冻结

## 1. 目标

在预注册 Challenger 首个 Episode 自然退出后，封存由 `v0.36.0` 冻结只读观察器
生成、并由同版本 loader 复核的唯一 completion receipt。本版本只发布 Episode
完成证据，不修改策略、调度、Runner、安装快照或观察口径，也不发布经济结果。

本设计是在完成结果出现后记录发布边界；成功判定口径仍完全来自结果出现前冻结的
observer 设计提交 `1878c00`，不得用本设计改变或放宽该口径。

## 2. 冻结输入

- observer 代码必须与 tag `v0.36.0` 一致；
- install receipt、contract、plist 和 receipt output root 必须使用
  `v0.35` 冻结的四个绝对路径；
- runtime receipt 必须位于唯一的
  `challenger-first-episode-receipts` 子目录，保持当前用户、mode `0600`、单
  hardlink；
- 只接受 `FIRST_EPISODE_COMPLETED_VERIFIED` 且
  `receipt_published=true`；
- 必须由 `load_challenger_first_episode_receipt` 使用同一组冻结输入立即重载；
- 禁止 kickstart、bootstrap、重跑 Runner、补槽、修改 state/log/bundle、
  市场网络请求、Broker、订单或策略 state 写入。

## 3. 发布边界

成功时允许把 runtime receipt 的 exact canonical bytes 封存为
`artifacts/challenger-forward/challenger-first-episode-receipt-v0.41.0.json`，
并更新对应测试、ADR、实施追踪、README、package 版本和构建清单。

Git 副本必须与 runtime 原件逐字节相同，并固定：

- exact file SHA-256、receipt id 和 receipt hash；
- Episode id、entry/exit 槽位、退出动作及五条 Episode decision；
- 观察时全部七条 state decision 中的五条 Episode 前缀；
- 五个 source bundle 与五行 stdout `RECORDED`；
- state/stdout/stderr 观察前后不变；
- observer 的 network/Broker/order/state-write 计数全为零。

本版本不得提交 owner-only ZIP/checksum，不得运行或提交真实经济结果。v0.39
官方日档获取和 v0.40 离线经济结果必须保持后续独立流程；官方 404 只能保持
pending。

## 4. 验收

- committed receipt 通过 Schema、自哈希、canonical bytes 与冻结语义验证；
- runtime 与 committed artifact 的 bytes、size、SHA-256 完全一致；
- 退出必须为合法 Episode 首次返回 `FLAT`，且不能包含退出后的 decision；
- focused、相邻回归、全量测试和构建清单验证通过；
- 发布提交合并 `main` 后才能建立 annotated tag `v0.41.0`；
- 不得声称盈利、AI 优势、正式 OOS、Paper 或生产资格。

## 5. 赚钱与 AI 含义

完成首个自然 Episode 消除了事后挑选退出时点和漏记不利决策的空间，但单个
Episode 仍不能证明策略有正期望。只有在冻结的成交代理与成本口径下完成后续经济
计算，并持续积累足够多不可回填 Episode，才可估计净收益及其下置信界。

AI 臂继续没有批准模型和交易权限。简单 Challenger 未形成足够前向基线前，不用
AI 搜索替代证据；未来 AI 只能在相同事件、时间、资本、成本和执行条件下证明相对
简单基线的可重复净增量。
