# Binance E0 operations v0.78.1

状态：`BINANCE_E0_CODE_COMPLETE_NOT_ACTIVATED`

## 默认边界

`production_activation=false`

`no service installed or started`

`no credential created or read`

`no private Binance request made`

`no order submitted`

`no funds moved`

代码发布不授予账户或交易权限。不得把 API secret 写入仓库、命令参数、日志或
receipt。真实凭据必须禁提现、IP allowlist、最小权限并保存在仓库外 owner-only
路径；创建或读取它们需要独立外部批准。

## 固定命令面

- `challenger-replacement-binance-e0 account-preflight`
- `challenger-replacement-binance-e0 private-runtime ETHUSDT@<UTC-4H-slot>`
- `challenger-replacement-binance-e0 emergency-stop ETHUSDT@<UTC-4H-slot>`

任何 endpoint、URL、symbol、quantity、credential、root 或 reason override 都必须
被拒绝。账户预检只允许冻结的 11 个只读端点并输出脱敏 receipt。私有运行只能消费
已提交 opportunity；紧急停止只能查询已暴露永续仓位并走固定 reduce-only flatten。

## 失败处理

未解决 UNKNOWN 不得重发。仓位不一致、保护止损缺失或资本门失败时禁止新增风险。
保存事件与错误现场，不删除、不补写、不手工修改为成功。真实账户/credential/
ceremony/E0 均不属于本代码发布步骤。
