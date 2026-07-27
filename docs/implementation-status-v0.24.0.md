# 实施追踪 v0.24.0

日期：2026-07-28

状态：已完成并验证

## 本版本完成

- 新增 scheduled Paper/account-cost/perpetual 的同槽位 context bundle；
- 要求 cost binding、Paper、账户 commission、perpetual 四个外部 attestation；
- Paper decision/run end、永续 source/recorded 和 bundle created 均绑定固定槽位；
- 永续与 Paper decision 最大偏差固定为 15 分钟；
- 永续上下文只作未消费/事后观测，不改变基线信号；
- Funding 只保留压力场景，明确不进入 realized PnL；
- 新增独立 SQLite WAL sidecar 与不可变事件/blob；
- PREPARED 后或 publish 后崩溃均以零 source read、零 network 恢复原 bytes；
- PREPARED 输出根被哈希绑定，不允许恢复到不同目录；
- bundle、输出 schedule、SQLite/WAL/SHM 使用 mode-0600；
- 新增 context schedule，90 天只统计 sidecar `SUCCEEDED`；
- 槽位缺口不会被旧 Paper 成功或后补 Artifact 掩盖；
- CLI 不提供 URL、proxy、key、secret、order、symbol、fee 或 clock override。

## 真实运行

仓库仍没有真实账户 commission snapshot，也没有成功的真实 Futures snapshot，
所以没有创建真实 context-complete PREPARED blob 或 schedule slot。测试 fixture
不会写入真实 schedule，也不会被计入 90 天。

冻结证据：
[binance-context-complete-cycle-not-run-v0.24.0.json](../artifacts/paper-context/binance-context-complete-cycle-not-run-v0.24.0.json)。

## 赚钱与 AI 含义

长期 Paper 现在有了更严格的“完整周期”定义：一个周期必须同时拥有原始 Paper、
PIT 账户成本和同槽位永续上下文，才能累计到 context-complete 日历。这样可以
防止只记录成功行情而漏掉费用/永续失败，导致幸存者偏差。

这仍不证明赚钱。必须先获得真实来源并持续至少 90 天，再用实际成交/滑点分布、
固定成本和预注册统计门判断。AI 仍未运行，未来 AI 与基线必须共享同一 bundle。

## 最终验证证据

- context bundle/PIT/WAL/recovery/schedule/CLI tests：16/16 通过
- context + evaluator build 定向 tests：25/25 通过
- 全量 tests：420/420 通过
- Python compileall：通过
- Golden Vector：41/41 通过
- Evaluator build input：103 个文件
- Evaluator build input tree：
  `9845efd7b4c3c73f7eda1f8b1cae03a12f6cd456b407646ab81a58b91c369022`
- Evaluator build：
  `dba78756604730275f50e0a13d2d83d439a5187e79076987609ba3c35fabd586`
- release/governance/schema/build validators：全部按冻结预期通过；release 保持
  `DESIGN_BASELINE` 失败关闭，governance 保持 `TEMPLATE_UNAPPROVED`
- 真实 context-complete cycle：未运行，失败关闭
