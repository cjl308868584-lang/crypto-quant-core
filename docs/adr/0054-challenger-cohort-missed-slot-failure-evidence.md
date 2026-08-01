# ADR-0054：Challenger Cohort 漏槽失败证据与受控停用

日期：2026-08-01

状态：已接受

## 背景

原 confirmatory cohort 的最后可信槽为 `2026-08-01T00:00:00.000Z`，下一要求槽为
`2026-08-01T04:00:00.000Z`。系统在该槽之后重启，旧 Runner 自然运行时正确返回
`CHALLENGER_RUNNER_MISSED_SLOT`。缺槽使原 cohort 永久失去 540 槽连续性资格；不能通过
补槽、回填、重置 state 或修改时间戳恢复资格。

在实现安全审查期间，旧 LaunchAgent 于北京时间 20:02 又自然运行一次。state 与 stdout
未变化，stderr 变为两条逐字相同的 canonical missed-slot 行，`runs=2`。因此冻结设计按
原字节证据原则修订为：接受一条或多条完全相同的 canonical missed-slot 行，并记录精确
次数；混合错误、空行、截断或其他内容仍失败关闭。

## 决策

1. 使用 v0.43 cohort plan、v0.44 evaluation plan、v0.35 install receipt/contract/plist
   和 v0.48 evaluator identity 重建失败事实。
2. observer 只执行一次固定 `launchctl print`；不调用 Runner、maintenance、市场网络、
   Broker、订单或策略 state 写入。
3. runtime failure receipt 必须位于固定 owner-only root，目录 0700、文件 0600、单链接、
   canonical compact JSON、no-overwrite；发布使用 dirfd、`O_NOFOLLOW` 与原子无覆盖链接，
   子目录符号链接不能重定向写入。
4. failure receipt 绑定观察时刻与 4h 槽、install/contract 文件 SHA-256、stderr 完整
   bytes、boot time 辅助观察、等价 v0.48 failure status/reason 和全部零权限计数。
5. 只有同版本 production loader 重放 canonical runtime receipt 后，才允许对固定旧服务
   执行一次无 shell 的
   `/bin/launchctl bootout gui/501/local.crypto-quant.challenger-forward`。
6. decommission 必须使用规范 0600 failure receipt，绑定 receipt inode/hash、domain
   projection 与最后一次 service print；任何 replacement/System Paper 标签阻断 bootout。
7. bootout、后验、停用后快照或成功 receipt 发布/重放失败时，先保存结构化 owner-only
   operation failure evidence，再返回失败；不得通过重跑寻找成功结果。
8. v0.35 install receipt 的 `st_dev` 在同一文件系统重启后发生变化，而 inode、owner、
   mode、link、size、plist SHA-256 全部不变。loader 仅豁免该 boot-volatile device number，
   其余身份约束保持严格。
9. failure 与 decommission runtime receipts 分别逐字节进入固定 Git artifacts；Git 副本
   不添加 wrapper 或人工字段。

## 真实结果

- failure status：`COHORT_MISSED_SLOT_FAILURE_VERIFIED`；
- last trusted slot：`2026-08-01T00:00:00.000Z`；
- next required slot：`2026-08-01T04:00:00.000Z`；
- observed current slot：`2026-08-01T12:00:00.000Z`；
- boot time：`2026-08-01T08:26:21.265Z`，仅作辅助根因观察；
- stderr：两条逐字相同的 missed-slot canonical 行；
- decommission status：`FAILED_COHORT_DECOMMISSIONED_VERIFIED`；
- bootout count：1；bootout 后固定 print 返回 service not found；
- state/stdout/stderr SHA-256 在停用前后完全不变；
- 未产生 operation failure receipt；
- market、Broker、order、state-write、Runner、maintenance invocation 均为 0。

## 后果

原 cohort 永久失败且旧 Runner 已停用。此结论只证明运行连续性失败，不评价策略收益，
也不证明 AI 优势、系统 Paper 完成或实盘资格。replacement Challenger 和 System Paper
必须在独立版本使用新的 service/state/log/bundle/evidence roots，经设计、测试和发布后
同日自然启动；旧 decisions、Episode、receipt、archive、result 与已运行天数不得迁移。

即使未来研究门通过，也只能进入下一研究阶段；`production_activation.enabled=false`
继续生效，系统没有真实 Broker 下单授权。
