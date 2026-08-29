# Implementation Status v0.78.3

状态：`V3_SIMULATION_ACTIVATION_FILESYSTEM_IDENTITY_FIXED_NOT_INSTALLED`

## 修复

在 exact annotated v0.78.2 checkout 执行已授权 renderer 时，目标 Mac 的
`/usr/bin/python3` inode 为 `1152921500312522874`。安装合同将该 OS identity
作为 JSON 整数参与 stable ID，触发 `integer exceeds the exact JSON safe range`。

v0.78.3 将同一信任链内 snapshot、event root、Python、plist、canonical event
header 与 start receipt 的 device/inode 全部编码为严格、无符号、无前导零的
十进制字符串。loader、preflight、installer 与 start wrapper 仅在 OS identity
比较或既有能力构造边界安全还原整数。全局 canonical JSON 限制未放宽，
identity 未截断、取模、浮点化或忽略。

测试包含大于 `2^53-1` 的确定性回归，以及目标 macOS `/usr/bin/python3`
真实 inode 回归。v0.78.2 renderer 留下的 owner-only runtime/snapshot 取证
目录未删除、未覆盖。

## 当前权限边界

`production_activation=false`

`no service installed or started`

`no credential created or read`

`no private Binance request made`

`no order submitted`

`no funds moved`

本版本只发布代码与不可变 release identity；未执行 renderer、preflight、
安装、LaunchAgent load/start、自然机会观察或 start receipt。72 小时与
90 天计时均未开始。
