# ADR-0059：System Paper 固定尾部评估

日期：2026-08-04

状态：已接受

## 背景

v0.58 只完成 System Paper deployment trust chain 的代码与冻结合同。它没有渲染或安装
生产合同，没有启动服务或创建 start receipt，也没有开始 90 天窗口。因此在真实尾部到达前，
任何 PnL、收益、胜率、回撤、成本或经济门结论都不应被读取或发布。

## 决策

1. v0.59 冻结 System Paper 的 90 天固定尾部 evaluator、严格 loader、唯一七路径 CLI、
   结果 Schema、镜像 Schema 和测试；它只评估由 v0.58 信任链将来产生的 exact 输入。
2. evaluator 在 tail 前只返回 pending 健康信息并禁止读取经济证据；tail 后要求完整的
   540 个连续 4 小时槽、完整重放和冻结安全/成本/回撤/三段 30 天收益门。
3. 任一未来真实结果必须按实际结论原样封存为 `PASS`、`DID_NOT_PASS` 或
   `INCONCLUSIVE`；不得删除负结果、重命名结果、回填缺槽，或用经济表现覆盖证据缺口。
   机器状态分别为 `SYSTEM_PAPER_GATE_PASS`、`SYSTEM_PAPER_GATE_DID_NOT_PASS` 和
   `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`。
4. `PASS` 只表示 System Paper 研究门通过，可进入后续研究；它不表示盈利、AI 优势、
   Paper 已完成、Canary 资格或实盘资格。replacement Challenger 仍未完成。
5. 本 ADR 不授权渲染生产合同、preflight、安装、bootstrap、启动 Runner/scheduler、市场
   请求、Broker、订单、凭据或 state 写入。`production_activation.enabled=false` 保持不变。
6. 发布前最终审查发现了首次 final 竞态、证据重新捕获、output root 与 loader
   attachment 缺口。v0.59 在发布前已修复：使用 contract/start 终态 key 和 owner-only
   lock 封存首个结果，只保留一次 post-tail 快照，对稳定但不可重放 state 使用 raw
   SQLite 组绑定的 INCONCLUSIVE，并将发布/加载限定在 contract 派生的专用 root。

## 后果

本版本的可验证范围仅为代码、Schema、CLI、evaluator 和离线测试。System Paper 尚未
production 安装、未启动、未创建真实 start receipt、未开始 90 天，且没有真实评估结果。
任何后续真实结论都必须使用冻结 evaluator 从原始证据完整重放，并按上述三个结果之一
不可覆盖地保存。
