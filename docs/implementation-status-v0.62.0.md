# 实施追踪 v0.62.0

日期：2026-08-05

状态：Replacement Challenger preregistration 与隔离合同已冻结；runtime 未实现、未安装、未启动、
未开始 90 天

## 本版本交付

- 参数为零的 `build_challenger_replacement_plan()`，固定研究 scope、原失败 ancestry、540 槽和
  全新 service/path identity；
- 每个 policy section 的 business hash、stable plan ID 与整体 self-hash；
- Draft 2020-12 config/package Schema mirrors，所有层级 `additionalProperties=false`；
- owner-controlled strict loader：绝对路径、regular file、owner、非 group/world writable、单
  hardlink、open/fstat identity、256 KiB 上限、duplicate key/float/canonical/Schema/hash/semantic
  失败关闭；
- exact plan artifact：
  `artifacts/challenger-replacement/challenger-replacement-plan-v0.62.0.json`，6,919 bytes，
  SHA-256 `78e703bfeb5b2b08af963ba14f08a66829613c680ccd6793df2a9a86e563ab3d`；
- 旧 v0.54 failure/decommission、v0.43 cohort、v0.44 evaluation committed bytes 的逐项重放；
- package `0.62.0` 与 evaluator build manifest `1.56.0`。

## 真实状态与权限边界

本版本只有 Git 代码、Schema、计划、artifact、测试和文档。replacement runtime root、plist 和
LaunchAgent 未创建或加载；System Paper 仍未安装或启动；旧 Challenger 继续保持永久失败和受控
停用。

所有 credential/account/Broker/order/production activation/install/start authority 为 false，
Runner/market/state-write counter 为零。没有调用旧或新 Runner、scheduler、maintenance，没有请求
市场、账户或 Broker，也没有写入 production strategy state。

旧 cohort 的 decisions、Episodes、receipts、archives、results、PnL、槽位和运行天数均不进入新
cohort。旧证据只作为不可删除的失败 ancestry。

## 尚未完成

- v0.63：全新 replacement WAL runtime、exact prepared input/result recovery、parent replay 与故障
  注入；
- v0.64：独立 deployment artifact、preflight、installer、observer 与 start receipt；
- replacement 专用 90 天 evaluator、tail-blind projection、只读 Web/alerts/runbooks；
- System Paper 与 replacement Challenger 各自的真实机器门、首次自然成功槽和独立 90 天证据；
- 两条流分别一次冻结终态评估后的研究决定。

因此 v0.62 不能声称 Paper 已开始或完成、策略赚钱、AI 优势、Canary 或实盘资格。
