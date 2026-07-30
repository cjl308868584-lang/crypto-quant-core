# v0.50 Challenger Cohort 证据维护 LaunchAgent 合同设计

日期：2026-07-31

状态：冻结

冻结基线：`v0.49.0` / `b7450d7510d3d5246148108edcec5a60ff2a4cb0`

## 1. 目标

v0.49 已把 receipt、官方日档和经济结果收口为单次、幂等、失败关闭的维护入口，
但仍依赖人工运行。v0.50 为该入口生成独立、确定性、无凭据的 macOS LaunchAgent
plist 与合同。

本版本只渲染、重放验证并发布 owner-only 合同，不安装、不加载、不调用
`launchctl`，也不声称自动维护已经运行。安装、私有执行快照和首次真实运行必须是
后续独立版本。

## 2. 不复用的组件

- `local_scheduler` 绑定账户 API key/secret 路径，不适合无凭据证据维护；
- `challenger_launchd` 绑定策略 Runner、state 和实时 source bundle，不允许扩展
  为同时执行控制面维护；
- 不修改已安装的 `local.crypto-quant.challenger-forward`。

新服务与策略服务完全分离，标签固定为：

```text
local.crypto-quant.challenger-cohort-evidence-maintenance
```

## 3. 固定信任根与路径

调用方只允许提供：

- repository root；
- Challenger runtime root；
- Python executable；
- v0.35 strategy install receipt；
- strategy contract；
- strategy plist；
- owner-only contract output root。

renderer 必须用现有 production loaders 验证 strategy install receipt、
contract、plist 的 exact 绑定。repository 必须包含 v0.49 maintenance core/CLI、
v0.43 cohort plan 和 v0.37 economic plan。所有路径必须为绝对路径；repository、
runtime、信任文件和 output 均拒绝 symlink。Python 必须是存在且可执行的普通文件。

固定程序参数自动派生为：

```text
<python>
-m
crypto_quant.challenger_cohort_evidence_maintenance_cli
--cohort-plan-path
<repository>/artifacts/challenger-forward/challenger-episode-cohort-plan-v0.43.0.json
--economic-plan-path
<repository>/artifacts/challenger-forward/challenger-episode-economic-plan-v0.37.0.json
--episode-receipt-output-root
<runtime>/cohort-receipts
--install-receipt-path
<verified-install-receipt>
--contract-path
<verified-strategy-contract>
--plist-path
<verified-strategy-plist>
--archive-output-root
<runtime>/cohort-archives
--result-output-root
<runtime>/cohort-results
```

CLI 不接受自定义 module、label、schedule、日志、计划、证据子目录或额外参数。

## 4. 固定调度

机器系统时区必须是 `Asia/Shanghai`、UTC+08:00、DST=0。

- 每天本地 `08:10` 唯一触发；
- 对应 UTC `00:10`，已经越过完整 UTC 日结束后 5 分钟的 archive 时间门；
- 与策略 Runner 本地 `08:02` 触发相隔 8 分钟；
- `RunAtLoad=false`，安装或登录不能制造非计划维护；
- `ThrottleInterval=60`；
- `ProcessType=Background`、`LowPriorityIO=true`；
- `AbandonProcessGroup=true`、`Umask=0077`；
- stdout/stderr 固定为
  `<runtime>/log/challenger-cohort-evidence-maintenance.{stdout,stderr}.log`。

若与策略 Runner 仍发生文件变化竞争，v0.45 原有 stat/hash/continuity 校验必须失败
关闭；不得通过等待、重试或触发 Runner 修复。

## 5. 环境与网络

EnvironmentVariables 只能包含：

```text
PYTHONPATH=<repository>/src
```

禁止 credential、HOME override、shell、URL、symbol、Broker、order、state 或
任意命令环境变量。网络范围只能是 v0.46 内部 allowlisted Binance official
DAILY ZIP/checksum；renderer 本身网络请求为 0。

## 6. 合同

新增 `challenger-cohort-evidence-maintenance-launchd-contract-v1.schema.json`。
合同至少绑定：

- label、repository/runtime/python；
- 三个 loader-verified strategy trust paths 及文件 SHA-256；
- v0.43/v0.37 plan path 及文件 SHA-256；
- 完整 program arguments、环境变量名、调度、日志路径；
- plist SHA-256；
- `NOT_INSTALLED_NO_EXTERNAL_RECEIPT`；
- network/Broker/order/state-write/Runner/launchctl/render requests 全部固定边界；
- 明确“不证明自动运行、盈利、Paper 或 AI 优势”的 warnings。

合同自哈希不能自证可信；另生成只依赖 contract id/hash、plist hash 和
installation status 的外部 attestation hash。loader 必须要求调用方提供该 trusted
attestation hash，禁止在 loader 内自行计算后当作外部信任。

## 7. 发布

renderer 创建：

- runtime `log` 目录：0700；
- output 固定子目录
  `challenger-cohort-evidence-maintenance-scheduler`：0700；
- plist 与 contract：0600、单 hardlink、canonical/exact、幂等；
- stdout/stderr 文件不预创建；
- receipt/archive/result 根不预创建。

相同 bytes 重试成功；任一不同 bytes 或额外目录项冲突失败。renderer 的返回只允许
`GENERATED_NOT_INSTALLED`，`launchctl_invoked=false`。

## 8. 验收

- Schema config/package mirror 逐字节一致并通过 Draft 2020-12；
- plist 和 program arguments 100 次确定性一致；
- loader 使用独立 trusted attestation hash，错误或缺失 hash 失败；
- 协调修改 contract + self-hash、plist、参数、计划、trust path、schedule、
  environment、日志或安全计数均由 semantic replay 拒绝；
- timezone、repository、runtime、Python、信任文件权限/symlink 错误失败；
- CLI 不暴露 install/load/launchctl/label/schedule/URL/credential/order/state；
- renderer 不 import Runner、Broker、credential、order 或 installation module；
- 真实 renderer 运行前后策略 state/stdout/stderr hash 不变，且
  `launchctl` 调用为 0；
- 聚焦、相邻、全量测试、compileall 和 evaluator build 全部通过。

## 9. 对赚钱目标的意义

该合同不增加收益。它减少长期 cohort 因人工漏维护造成的选择偏差风险，使负样本与
正样本更可靠地进入固定尾部累计门。只有后续安装并取得真实运行 receipt，才能声称
维护调度已启用；只有 v0.48 固定尾部研究门通过，才有资格进入下一研究阶段。
