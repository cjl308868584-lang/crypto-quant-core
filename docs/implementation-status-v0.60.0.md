# 实施追踪 v0.60.0

日期：2026-08-05

状态：Tail-Blind 只读运维投影代码、Schema 与离线验证已冻结；未安装、未启动、未开始 90 天

## 本版本交付

- 三个 frozen/slotted typed source snapshot 与固定顺序、单次调用的 adapter 边界；
- Git release identity、canonical UTC、20 分钟 freshness、5 分钟 future-skew、跨字段状态机
  与 `HEALTHY`/`DEGRADED`/`FAILED_CLOSED` 派生；
- Challenger pre-tail gate 隐藏和逐字段 allowlist，结构上排除经济指标、任意 mapping、路径、
  凭据和 adapter 异常文本；
- System Paper 模拟订单生命周期、对账、风险和终态 gate 的只读投影，不包含 gate 背后的
  经济测量；
- canonical `projection_hash`、有界严格 bytes loader、双镜像 closed Schema 与 adversarial
  离线测试；
- package `0.60.0` 与 evaluator build manifest `1.54.0`。

## 真实状态与权限边界

本版本只发布代码、Schema 和文档。它没有渲染合同、运行 preflight/installer、bootstrap 或
kickstart 服务，没有调用 Runner/scheduler/maintenance，没有读取 production SQLite 或日志，
没有市场网络、凭据、Broker、订单或资金动作，也没有写入任何 production state。

System Paper 仍未 production 安装、未启动、没有 start receipt、未开始 90 天。旧 Challenger
cohort 仍因漏槽永久失败并停用；该失败只评价连续性，不评价收益。replacement Challenger
尚未设计或启动，且未来必须使用全新 roots。`production_activation.enabled=false` 保持不变。

## 尚未完成

- v0.61 loopback-only Web、alerts 与 runbooks；
- System Paper 的独立受限安装与首次自然槽；
- replacement Challenger 的全新设计、服务与 90 天证据；
- 两条流分别完整 90 天后的冻结终态评估。

因此目前没有可持续盈利、AI 优势、Paper 完成、Canary 或实盘资格证据。即使投影状态为
`HEALTHY`，也只说明 allowlisted 运维观察内部一致。
