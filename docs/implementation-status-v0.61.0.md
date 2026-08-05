# 实施追踪 v0.61.0

日期：2026-08-05

状态：Loopback-only 只读 Web、确定性 alerts 与 fail-closed runbooks 已冻结；未安装、未启动、
未开始 90 天

## 本版本交付

- `operations_alerts.py`：只接受 v0.60 strict loader 验证的 canonical bytes，按固定顺序派生
  stable alert IDs、INFO/WARNING/CRITICAL 计数和 Paper 风险观察；
- `operations_dashboard.py`：仅绑定 `127.0.0.1`、严格 Host、四个 GET route、全部非 GET 405、
  路径攻击 400、来源失败统一 secret-free 503；
- 每个响应的 no-store、CSP、nosniff、DENY、no-referrer、Permissions-Policy 与零 CORS/cookie；
- package 内静态 HTML/CSS/JavaScript：四个只读视图、一次 same-origin fetch、只用
  `textContent`、无轮询、无操作按钮、无远程资源；
- 只接受显式绝对 projection file 与 port 的 CLI，没有 host override；
- canonical healthy fixture 与真实 `127.0.0.1` socket smoke，fixture SHA-256 为
  `bb1aec23580a2f18a723f33be86de3720a7b5a69342d5fbb82bc13a51707f0ba`；
- System Paper 与控制台两份安全运行手册；
- package `0.61.0` 与 evaluator build manifest `1.55.0`。

## 真实状态与权限边界

本版本只发布代码、静态资源、fixture、测试和文档。它没有创建或读取 production System
Paper root，没有渲染 contract、执行 preflight/install/bootstrap、加载 LaunchAgent、调用
Runner/scheduler/maintenance，也没有访问市场、凭据、账户、Broker、余额、订单或写入
production state。

System Paper 仍为 `PLAN_FROZEN_PAPER_NOT_STARTED`：没有 install receipt、start receipt、
真实槽位或 90 天证据。旧 Challenger cohort 的漏槽失败与受控停用继续永久保留；replacement
Challenger 尚未设计或启动。

`new_risk_allowed` 只是对严格投影中 System Paper 状态的只读观察，不能授权安装、启动或任何
订单。即使 Web 显示 `HEALTHY`，也不能声称盈利、AI 优势、Paper 完成、Canary 或实盘资格。

## 尚未完成

- System Paper 的独立受限安装设计、机器 preflight、安装与首次自然槽；
- replacement Challenger 的独立冻结设计、全新 roots、安装与首次自然槽；
- 两条流各自从真实 start receipt 开始的完整 90 天；
- 两条流分别一次冻结终态评估后的后续研究决定。

上述事项必须继续按独立语义版本、失败关闭和不可回填规则推进。`production_activation.enabled=false`
保持不变。
