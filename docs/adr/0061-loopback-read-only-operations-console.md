# ADR-0061：本机只读运维控制台与确定性告警

日期：2026-08-05

状态：已接受

## 背景

v0.60 已把 release identity、Challenger 连续性和 System Paper 模拟订单生命周期、对账、风险
状态收敛成严格、tail-blind、canonical 的只读投影。直接让 Web 读取 SQLite、日志、receipt 或
LaunchAgent 会复制 production loader，扩大权限，并可能泄露 confirmatory economics；让远程
服务托管又会引入认证、暴露和数据留存问题。

## 决策

1. `operations_alerts.py` 的公开输入只能是 canonical projection bytes。它必须先调用 v0.60
   `load_operations_projection_bytes`，再从固定字段、固定顺序派生 stable alert IDs、severity、
   reason code、risk effect 和 `new_risk_allowed` 观察值。
2. Challenger-only warning 不阻断独立 System Paper 的风险观察；总体 `FAILED_CLOSED` 或任何
   Paper stale/incident/UNKNOWN/reconciliation/risk condition 均失败关闭。这个 boolean 是展示
   结论，不是执行授权。
3. `operations_dashboard.py` 只接受注入的 bytes provider，只绑定字面值 `127.0.0.1`，只开放
   `/`、`/app.js`、`/styles.css`、`/api/v1/status` 四个 GET。Host 必须包含实际 loopback port；
   编码/遍历/查询路径返回 400，未知 GET 返回 404，全部非 GET 返回 405。
4. provider、bytes、Schema、hash 或语义失败统一返回不含异常、路径或输入的 503。所有响应
   设置 no-store、CSP、nosniff、DENY、no-referrer 和 Permissions-Policy，不启用 CORS、cookie、
   session、WebSocket 或默认访问日志。
5. 页面只使用本地 package resources，一次 same-origin fetch，并以 `textContent` 渲染。
   不轮询、不提供按钮，不包含 Challenger 经济指标或外部资源。
6. CLI 只能接受一个绝对 `--projection-file` 和可选 `--port`；没有 `--host`。它启动前严格
   重放文件，每次 API 请求重新读取并重放，永不缓存旧健康状态。
7. 两份 runbook 只允许当前只读检查并记录未来授权门。v0.61 不安装、不 bootstrap、不启动
   System Paper，不调用 Runner/scheduler/maintenance、市场、Broker 或订单。

## 后果

本地 UI 可以安全失败而不影响证据流，且任何未来 adapter 都必须先把来源缩减到 v0.60 的
closed projection。fixture smoke 证明四个 GET 与 405 边界在真实 loopback socket 上工作；
fixture SHA-256 为
`bb1aec23580a2f18a723f33be86de3720a7b5a69342d5fbb82bc13a51707f0ba`。

控制台显示 `HEALTHY` 只说明 allowlisted 运维观察内部一致。它不证明 System Paper 已启动、
连续 90 天、策略盈利、AI 优势、Canary 或实盘资格。replacement Challenger 仍须使用全新
service/state/log/bundle/evidence roots，并永久保留旧 cohort 漏槽失败。
