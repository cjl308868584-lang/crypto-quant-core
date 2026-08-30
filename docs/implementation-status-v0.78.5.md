# Implementation Status v0.78.5

状态：`V3_SIMULATION_ACTIVATION_CANDIDATE_SUPERSEDED_NOT_INSTALLED`

## 历史证据与修复

v0.78.4 renderer 在发布前因
`CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_CONFLICT` 失败关闭：固定候选路径已由
v0.78.3 failed preflight receipt 所绑定的不可变候选文件占用。v0.78.3 receipt、
候选 plist、contract 与 snapshot 是历史证据，must not be deleted、覆盖、移动、
重命名或 chmod。

v0.78.5 为 contract、candidate plist、preflight receipts 与 install receipts
冻结独立的 `v0.78.5` 路径。旧 receipt 不会作为当前 install 输入；共享 snapshot
按完整 tree hash 寻址，event/start/target/service 路径保持不变。

## 当前权限边界

`production_activation=false`

`no replacement service installed or started`

`no credential created or read`

`no private Binance request made`

`no order submitted`

`no funds moved`

本版本只冻结代码、manifest 与 exact release identity；不执行 renderer、preflight、
安装、bootstrap、LaunchAgent 启动、自然机会观察或 start receipt。任何后续仪式都
必须使用 exact annotated v0.78.5，并保留 v0.78.3 的全部证据。
