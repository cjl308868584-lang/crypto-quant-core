# ADR-0067: Replacement Live Input and Deployment Candidate

状态：`DEPLOYMENT_CANDIDATE_RELEASED_NOT_INSTALLED`

v0.67 采用固定 Binance public GET adapter，把 exact live-capture bytes 绑定到 source/decision v2，并继续使用 v0.66 的 append-only 三阶段事件事实源。部署合同和 LaunchAgent plist 只是 Git 内不可变候选；preflight 只读且不发布 receipt。

拒绝通用交易所 adapter、通用 scheduler、Broker、订单生命周期和控制 UI。事件日志仍是唯一权威；exports 不是权威。candidate 不创建 production root、plist 或 service，也不启动 Runner。

`production_activation=false`
`runtime_install_authorized=false`
`replacement_start_authorized=false`
`real_orders_allowed=false`

`no 90-day timer started`。本版本不证明盈利、AI 优势或实盘资格。
