# 实施追踪 v0.63.0

日期：2026-08-05

状态：NautilusTrader 隔离 Spike 在供应链预检阶段失败关闭；结论为
`INCONCLUSIVE_BLOCKED / NONE_KEEP_CURRENT_CORE`。未安装可用引擎，未运行兼容性对照，不采用。

## 本版本实际完成

- 独立 `sandboxes/nautilus` Python 3.12 package identity 与完整 `uv.lock`；根包继续
  Python 3.9+，根依赖没有 NautilusTrader；
- exact `nautilus_trader==1.227.0` tag/commit/wheel/size/SHA-256、Requires-Python、
  LGPL-3.0-or-later license identity 和所有 locked distribution hashes；
- 严格 dependency-lock Schema、owner-only loader、同一 file descriptor 的 `open/fstat/read/fstat`
  重放和完整 lock 语义绑定；
- 只读 preflight comparison Schema 和 Evidence Adapter，将绑定到完整 lock 的实际状态
  固定为 `INCONCLUSIVE_BLOCKED`；
- 静态失败关闭测试：篡改 lock/attestation、非 owner-only、symlink、平台和
  Schema 边界均被拒绝。

Git 中只保留两类 v0.63 制品：dependency lock 和 preflight comparison/report。
不存在 request、current-reference、result、runner 或 engine state。

## 供应链观察的证据边界

本会话观察到两次同版本、同官方来源、不放宽 hash 的 frozen sync 尝试：
第一次退出 1，第二次在无可靠进展后有界终止并退出 130。但 exact terminal
transcript bytes 没有作为机器可重放制品保留，也没有独立外部 attestation。

因此报告只把它表述为
`SUPPLY_CHAIN_FETCH_NOT_MACHINE_REPLAYABLE / SESSION_ATTESTATION_NOT_MACHINE_REPLAYABLE`，
不声称它是 exact failure receipt。`runtime_failure_suite_executed=false`；只有
`static_blocked_path_tests_executed=true`。

runner invocation、engine creation、market request、credential access、Broker request、real order、
production state write 和 result publish 计数均为 0。Golden、部分成交、拒单、费用、持仓、
PnL 和 fresh-process replay 均未执行、未通过。

## 对现有项目的影响

System Paper、replacement Challenger、旧 Challenger failure/decommission、v0.59 evaluator、
production services/roots/plists/state/logs 与所有 90 天事实源均未修改。没有迁移、
回填、重置、改起点、更换事实源、安装、bootstrap、kickstart、Runner、scheduler
或 maintenance。

未来若重评，必须另开语义版本、重新预注册，不得改写 v0.63。本版本不能声称
策略赚钱、AI 优势、Paper 已开始或完成、Shadow、Canary 或实盘资格；
`production_activation.enabled=false` 继续生效。
