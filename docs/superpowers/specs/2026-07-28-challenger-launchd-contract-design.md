# v0.32 Challenger LaunchAgent 合同设计

日期：2026-07-28

状态：冻结

## 1. 目标

为 v0.31 公共只读 Runner 生成一个确定性、可重放、无凭据的 macOS
LaunchAgent plist 与合同。生成器创建 owner-only runtime 目录、日志路径和
不可变合同，但不调用 `launchctl`，不声称已安装或已运行。

## 2. 固定环境

- platform：macOS launchd；
- system timezone：`Asia/Shanghai`，当前 offset 必须 +08:00、DST=0；
- repository 必须包含 `pyproject.toml` 和 runner CLI；
- Python 必须是绝对、存在、普通且可执行文件；
- runtime root 必须是绝对路径且不能是 symlink；
- 不读取或保存任何 credential。

## 3. 固定 LaunchAgent

Label：

```text
local.crypto-quant.challenger-forward
```

ProgramArguments：

```text
<python>
-m
crypto_quant.challenger_forward_runner_cli
--state-path
<runtime>/state/challenger-forward.sqlite
--output-root
<runtime>/artifacts
```

EnvironmentVariables 只含：

```text
PYTHONPATH=<repository>/src
```

触发：

- 本地小时 `0,4,8,12,16,20`，minute `2`；
- Asia/Shanghai 固定 +08:00 且无 DST，因此与 UTC 4h 网格一致；
- `RunAtLoad=true`，Runner 自己决定 NOT_DUE/DUE/MISSED；
- stdout/stderr 固定写入 runtime/log；
- shell、URL、symbol、time、credential 与 order 参数均不存在。

## 4. 合同与发布

合同绑定：

- repository/runtime/python 绝对路径；
- timezone 名称与 +08:00 校验；
- cadence；
- 完整 program arguments 与环境变量名；
- plist SHA-256；
- `NOT_INSTALLED_NO_EXTERNAL_RECEIPT`；
- `launchctl_invoked=false`。

合同和 plist 必须可确定性重建、自哈希、Schema 校验并以 mode 0600 发布；
runtime/state、log、artifacts 和发布目录为 0700。相同 bytes 幂等，不同 bytes
冲突。

## 5. 验收

- plist 只包含固定 runner 参数；
- 无 credential 或订单字段；
- +08:00/DST/路径/Python/仓库错误失败关闭；
- plist 或合同即使协调重哈希仍可由 semantic replay 发现；
- CLI 不提供 install/load/launchctl 或任意命令参数；
- fixture 100 次输出一致；
- 全量验证、提交、合并并标记 `v0.32.0`。
