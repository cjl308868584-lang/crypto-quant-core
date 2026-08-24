# Implementation Status v0.71.0

状态：`FIXTURE_ACCOUNTING_CORE_VERIFIED_LIFECYCLE_NOT_IMPLEMENTED`

## 已完成

- 冻结 credential-free Binance fixture simulation contract 与严格输入；
- 实现 plan/policy-bound LONG/SHORT/FLAT decision；
- 实现 Spot long / USDT perpetual short 互斥 signed snapshot；
- 实现 adverse fill、step/min-notional、fee、funding、margin、PnL、equity 与 exposure；
- 实现 daily loss、drawdown、gross drift、margin exhaustion、economic-gap 与 unresolved failure closure；
- 正式 contract artifact SHA-256：`65a0af1cccee5ad60aeaa7b0266bb217fab680d866ea3191ca77d214a292d86f`；
- Task 4 focused/adjacent：54 passed；独立定向审查 Critical 0 / Important 0 / Minor 0；
- 六模块 2,042 行，减 v0.70 基线 843 后为 1,199 / 1,200。

## 验证状态

- 最终代码状态 `d448c0d2ce1d77430768e38fcbb25f838b3f00e7`；
- final local full suite：1,962 passed，5 skipped，1,072.746s；
- compileall、focused release/artifact replay、diff-check：passed；
- `make validate`：process exit 0；release policy 正确保持
  `FAIL / PRODUCTION_ACTIVATION_DISABLED`，没有因此取得生产资格；
- 独立完整审查发现 Critical 0 / Important 2 / Minor 1；两个 Important
  以 Decimal-context 隔离和公开 input schema manifest 绑定关闭；
- 修复后定向复审：Critical 0 / Important 0 / Minor 1，批准最终候选；
- 剩余 Minor：公开函数 decorator 未保留 introspection metadata，不影响调用、
  结果、权限或确定性，记录到 v0.72；
- PR CI、main CI 和 annotated tag：`PENDING_REMOTE_RELEASE_GATES`。

远端 pending 只能在真实门完成后替换，不预写成功。

## 明确未实现

v0.71 lifecycle not implemented：无 ack/partial fill/UNKNOWN/stop/reconciliation、
无 v2 result/event orchestration、无 crash recovery 或 complete-cycle golden。
这些项目只可在独立 v0.72 spec/plan 下继续。

## 权限与结论边界

`production_activation=false`

`runtime_install_authorized=false`

`replacement_start_authorized=false`

`real_orders_allowed=false`

`no seven-day timer started`

`no 90-day timer started`

未安装或启动 service，未写 production root，未使用 network/account/credential/
Broker/order/funds。本版是 fixture-only accounting core，不证明盈利、AI 优势、
Paper 完成、Canary 资格或实盘能力。
