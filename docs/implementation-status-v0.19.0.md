# 实施追踪 v0.19.0

日期：2026-07-27

状态：已完成并验证

## 本版本完成

- 新增 UTC 4h/close+5m/15m lease 的冻结 Paper slot policy；
- 第一次启动只创建当前槽位，不回填安装前历史；
- 自动把已知运行期间的空洞记为 `MISSED_NO_CONTEMPORANEOUS_CAPTURE`；
- 把窗口已过但未成功的槽位记为 `EXPIRED`，两者均禁止重新执行；
- 新增 SQLite WAL/FULL synchronous append-only 调度事件链；
- event/blob UPDATE 和 DELETE 均由数据库触发器拒绝；
- `BEGIN IMMEDIATE` 原子 claim，支持 BUSY、lease reclaim、FAILED retry；
- 在文件发布前事务性保存精确 canonical run bytes、SHA、run/trust hash；
- 支持 PREPARED 后崩溃和文件发布后崩溃的零网络恢复；
- SUCCEEDED 同槽位重复调用不请求网络，幂等验证不可变文件；
- 新增严格 `PaperScheduleSnapshot` Schema、事件重放、self-hash 和外部
  attestation；
- 新增 one-shot CLI，仅接受 state path、output root 和 worker ID；
- 修复 v0.18 最后 response 与记录时钟同毫秒时的 +1ms 运行结束边界，
  使用 `max(actual_clock, deterministic_run_end)`，不 sleep、不改原始时刻。

## 真实官方调度 smoke

来源：`https://data-api.binance.vision`，Spot ETHUSDT，无凭据 GET。

### 槽位

- Slot：`ETHUSDT_20260727T120000Z`
- Scheduled：`2026-07-27T12:00:00.000Z`
- Due：`2026-07-27T12:05:00.000Z`
- Expires：`2026-07-27T16:05:00.000Z`
- 最终状态：SUCCEEDED
- Attempt：2
- Failed attempt：1
- Missed/Expired：0/0

Attempt 1 在真实网络完成后触发 `PAPER_CLOCK_INVALID`：最后 response 与
记录时钟落在同一毫秒，而经济窗口固定比 response 晚 1ms。失败被完整写入
事件链，没有删除或改写。修复为显式 deterministic run-end floor 后，
Attempt 2 使用新的当前公开响应成功。

### Cycle

- Artifact：
  `artifacts/paper/paper-slot-ethusdt_20260727t120000z.json`
- 决策时刻：`2026-07-27T14:21:46.076Z`
- 结束：`2026-07-27T14:21:47.544Z`
- 网络：4 个固定 public GET
- 基线：LONG / SET_TARGET / 25%
- 最新 close / SMA20：1959.67 / 1889.2445
- 模拟成交：BUY 0.0459 ETH @ 1953.13
- 起始/立即保守清算权益：1000 / 999.5509375795 USDT
- AI：`NOT_RUN_NO_APPROVED_MODEL`
- Artifact SHA-256：
  `19bd52e6bcbccbb8e6dfc909b68fe5a976de8e1bd1ee638c55e37aaf471059ea`
- Run hash：
  `0faf9fa348afe43f45351234061a5c706f4634fc7a400778da0f30a786624c34`
- External cycle attestation：
  `fa55a5ca73ac3a958b9ed2295b4c4b5b90ff09e2f6d0ba33f7cb48642eb3b167`
- Trusted replay reasons：空

### Schedule

- Artifact：
  `artifacts/paper/paper-schedule-ethusdt_20260727t120000z.json`
- Events：5（CLAIM, FAIL, CLAIM, PREPARE, SUCCEED）
- Event root：
  `fa784c0b94b4c67643ac5e612ad173641b306435d7f9f820fd112af74ea197c9`
- Event chain end：
  `e77da23bf2549609b7a8a56a4d4ff0d93a46cf1a4f7caac3ee5933cb7e556f6a`
- Snapshot hash：
  `34952efbab3ad2bba357447ac3a19e3abdfb4dfdb3468052371f9dd3a40cd8cf`
- External schedule attestation：
  `5ee8415e66dbd05175a8d69edc5b2e1cee7d3cc6cafa7aecad1c5e18b55892e8`
- Trusted replay reasons：空
- 观测自然日：1
- 90-day complete：false

同一状态库第三次调用返回：

- `outcome=ALREADY_SUCCEEDED`
- `network_request_count=0`
- cycle/schedule Artifact 均 `created=false`
- 所有 hash 与上次完全一致。

## 安全与恢复审查

- CLI 没有 time/slot/URL/header/key/account/order override；
- 生产 cycle 沿用 v0.18 精确四公开 GET，无自动网络重试；
- 两个数据库连接观察同一活跃租约，第二 worker 返回 BUSY；
- 过期租约只能追加新 CLAIM，旧事件不能修改；
- PREPARED blob 与 run replay、SHA、run/trust hash 每次打开均重新验证；
- fault injection 覆盖 before prepare、after prepare、after publish；
- 发布后恢复不替换 inode，完全相同 bytes 才幂等；
- symlink state file、事件篡改和 blob 篡改失败关闭；
- 没有账户、密钥、Broker、订单或资金能力。

## 最终验证证据

- 新增 scheduler/state/CLI tests：18 项，0 失败
- scheduler + v0.18 + 原子发布聚焦 tests：36 项，0 失败
- 全量 tests：342 项，0 失败
- Golden Vector：41 项
- Golden report：
  `e3e7dc45865d860489514a574c64ca14a8dd6f089a0b74129414231741882fc3`
- Catalog：58
- 可执行 Estimator：26
- 明确 unavailable：32
- Evaluator build input：70 个冻结文件
- Evaluator build input tree：
  `8c9983cba746613aee8b5fb3e1f642749864ea7302e4424cfa08fc95293e6cf3`
- Evaluator build：
  `8f22fd104c1efa3ff12e8cc3b2c3b79a0aa5d1de430370c134410ae0746e4d6d`
- release/governance/schema/build validators：执行成功；
  Release Policy 仍按设计返回 `DESIGN_BASELINE` /
  `PRODUCTION_ACTIVATION_DISABLED`
- Cycle trusted replay：PASS
- Schedule event replay：PASS
- Prepared exact-byte recovery：PASS
- 4-public-GET boundary：PASS
- WAL/FULL synchronous：PASS
- Same-slot idempotency：PASS，network request count 0
- 经济对账：PASS；保守退出价 1949.20、预期退出费
  0.1342024200、结束清算权益 999.5509375795

## 赚钱与 AI 含义

v0.19 让长期证据“难以重复、难以回填、可从崩溃恢复”，但不增加 alpha。
单槽位的立即保守清算仍为负成本压力；这不代表 24h 策略一定亏损，也不
能证明盈利。

当前仍不能声称：

- 已完成 90 天系统 Paper；
- 操作系统级调度已经启用；
- 简单基线长期扣费后盈利；
- AI 优于基线或平台 AI；
- 15 bps 假设等于真实账户费率；
- 当前系统具备任何资金资格。

## 下一优先级

1. 增加 server-time/NTP offset、调度心跳和连续运行告警；
2. 配置外部 one-shot 调度前先完成运行目录、备份和告警验收；
3. 增加永续 Mark/Index/Premium/OI 与 Funding 同时上下文；
4. 冻结外部批准、有效期明确的真实账户 FeeSchedule；
5. 至少连续运行 90 天，任何 missed/expired 均保留；
6. 再封存 AI 候选做同 proposal/time Shadow，不接真实资金。
