# Implementation Status v0.78.4

状态：`V3_SIMULATION_ACTIVATION_PREFLIGHT_FIXED_NOT_INSTALLED`

## v0.78.3 失败证据

北京时间 2026-08-30 00:13，exact v0.78.3 preflight 发布了不可变失败
receipt。状态为 `PREFLIGHT_FAILED_CLOSED`，reason codes 为
`PREFLIGHT_PATH_BOUNDARY_INVALID` 与 `PREFLIGHT_POWER_UNSAFE`。receipt 的
全部私有权限计数为零，但其 `.149Z` 时间戳不符合既有 `.000Z` schema，因而
strict loader 正确拒绝。没有 install receipt、目标 replacement plist、
replacement service、event 或 start receipt。

旧 `gui/501/local.crypto-quant.challenger-forward` 当前 loaded 但 not running，
无 PID。它的目标 plist 与冻结 scheduler-v2 plist SHA-256
`f6b2283ad4c01ee6e7dc8e954bdcb29dd221d5b79d4a04b69618af1d26182b53`
一致。v0.78.4 不对旧服务执行 unload、disable、删除或修改。

## 最小修复

- 使用真实 `pmset -g custom` fixture 验证对齐空格，并按电源 section 严格
  要求唯一 `sleep 0`；不安全、缺失或歧义输出失败关闭。
- preflight builder 在建立 ID/hash 前将观察时间规范化到整秒，因此
  `observed_at` 与 `expires_at` 始终使用既有 canonical `.000Z` 格式。
- eligible 与 failed receipt 都通过同一 schema、canonical bytes、ID/hash 和
  semantic rebuild strict replay。

## 当前权限边界

`production_activation=false`

`no replacement service installed or started`

`no credential created or read`

`no private Binance request made`

`no order submitted`

`no funds moved`

本版本只发布代码与 exact release identity；不执行 renderer、preflight、安装、
bootstrap、LaunchAgent 启动、自然机会观察或 start receipt。v0.78.3 的全部
失败证据保持原位。
