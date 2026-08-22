# ADR-0068: Replacement Install, Observer and Start Trust Chain

状态：`REPLACEMENT_INSTALL_TRUST_CHAIN_CODE_RELEASED_NOT_INSTALLED`

v0.68 为 replacement Challenger 冻结代码级安装信任链：固定 v0.67 strategy
snapshot 与 Python identity、owner-only runtime 目录、无参数 preflight/installer、
installed adapter、只读首槽 observer 以及 no-overwrite start receipt。所有成功
路径在返回前重放 exact bytes、fsync 目录并重验 retained descriptor 与授权
pathname 的 attachment。

installed adapter 只能恢复 install receipt 派生的首个 eligible slot，且
durable prefix 的每个 event 都必须来自 contract 固定 natural worker。在 start
receipt 发布前，已完成首槽也只能幂等重放，不得进入第二槽。observer
和 publisher 保留 event/log/plist capabilities，跨发布前后复核 bytes、stat、
attachment、event projection 与 upstream receipts。

本版只发布代码和冻结合同，不渲染真实 snapshot，不执行 preflight、
install、bootstrap 或 runtime，不写 production root、plist、install receipt 或 start
receipt。

`production_activation=false`
`runtime_install_authorized=true`
`replacement_start_authorized=false`
`real_orders_allowed=false`

`no 90-day timer started`。这个版本不证明盈利、AI 优势、Canary 或实盘资格。
