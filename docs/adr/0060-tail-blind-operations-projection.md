# ADR-0060：Tail-Blind 只读运维投影

日期：2026-08-05

状态：已接受

## 背景

System Paper 的确定性运行时、WAL 调度器、deployment trust chain 与固定尾部 evaluator
已经在 v0.56–v0.59 完成代码冻结，但尚未安装或启动。后续本地 Web 与告警需要一个稳定的
只读数据边界；如果直接拼接 receipt、SQLite 或 evaluator 输出，容易泄露 confirmatory
Challenger 的中期经济信息，也会让展示层获得文件、进程或网络能力。

## 决策

1. v0.60 提供 `build_operations_projection(now, sources)`。三个注入 adapter 按 release、
   Challenger、System Paper 的固定顺序各调用一次，并且只能返回 frozen/slotted typed
   source snapshot。
2. projector 逐字段创建 allowlist，不序列化 source object、不合并任意 mapping，也不
   接受来源提供的 freshness 或 overall status。Git main/tag/package identity、时间、状态机、
   freshness 与总体健康全部在边界内重新派生。
3. Challenger 在 final 前只暴露 `WITHHELD_PRE_TAIL`，任何阶段都不暴露 PnL、收益率、
   胜率、回撤、价格、费用、置信区间、排名或功效。System Paper 只暴露模拟订单生命周期、
   对账、风险和终态 gate，不暴露 gate 背后的经济测量。
4. `load_operations_projection_bytes` 只接受有界 canonical JSON、无重复键/float/未知字段、
   正确镜像 Schema、完整语义重建与 `projection_hash`。它只读取随包发布的 Schema resource，
   不读取任何运行证据、SQLite、路径、凭据或环境状态。
5. 本模块不发现来源、不运行 `launchctl`/subprocess、不访问网络、不持久化投影，也不写
   策略或证据 state。v0.61 才可在该纯投影之上实现 loopback-only Web/alerts/runbooks。
6. 本版本不授权 System Paper 安装、启动、Runner/scheduler、市场请求、Broker、订单、
   replacement Challenger 或真实资金行为；`production_activation.enabled=false` 不变。

## 后果

后续展示层只能消费一个小型、可重放、来源可追溯且经济盲化的对象。`HEALTHY` 只表示这份
allowlisted 运维观察内部一致，不证明盈利、AI 优势、Paper 完成、Canary 或实盘资格。
旧 Challenger cohort 的漏槽仍是永久连续性失败；replacement Challenger 必须使用全新
service/state/log/bundle/evidence roots。
