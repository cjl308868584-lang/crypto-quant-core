# v0.52 Challenger Cohort 证据维护首次自然运行观察器设计

日期：2026-07-31

状态：冻结

冻结基线：`v0.51.0` / `d61e16ba7667975783e66c4ae0934872d9c1aed9`

## 1. 目标

v0.51 已把固定的 cohort 证据维护入口安装为每天北京时间 08:10
自然运行的独立 LaunchAgent，且 `RunAtLoad=false`。v0.52 在首次自然槽之前冻结一个
只读观察器，用于区分：

1. 首槽前正常等待；
2. 首槽后仍在 launchd 合理完成窗口内；
3. 首次自然运行已完成且证据完整；
4. 服务漏槽、失败、日志冲突或运行证据不可信。

观察器不运行维护入口，不调用 `kickstart`、`bootstrap`、`start` 或 `submit`，
不触发策略 Runner，不访问市场网络，不写策略 state，不调用 Broker 或订单。

## 2. 固定输入与派生路径

CLI 只接受以下五个输入：

- v0.51 maintenance install receipt 的绝对路径；
- v0.51 deployment manifest 的绝对路径；
- Git 冻结的 source contract external attestation hash；
- Git 冻结的 candidate contract external attestation hash；
- owner-only first-run receipt output root。

所有其他对象必须由 production loader 和上述可信对象自动派生，包括：

- candidate contract 与 plist；
- service、domain、安装 target；
- private execution snapshot；
- maintenance stdout/stderr；
- cohort receipt/archive/result roots；
- strategy state/stdout/stderr；
- 首次自然运行时间。

不得提供 service、label、uid、日志、输出目录、计划、日期、时区、schedule、
状态、结果、URL、凭据、Broker、订单、Runner 或命令选择器。

## 3. 首槽与状态机

由 install receipt 的 `verified_at`、candidate contract 的 Asia/Shanghai
本地日历调度和 `RunAtLoad=false` 自动求严格晚于安装验证时刻的首个 08:10：

```text
first_natural_scheduled_for = 2026-07-31T00:10:00.000Z
completion_deadline = first_natural_scheduled_for + 10 minutes
```

固定状态：

- 首槽前：`WAITING_BEFORE_FIRST_NATURAL_MAINTENANCE_RUN`；
- 首槽到完成期限内且没有完整成功证据：
  `FIRST_NATURAL_MAINTENANCE_RUN_PENDING`；
- 完整成功：
  `FIRST_NATURAL_MAINTENANCE_RUN_COMPLETED_VERIFIED`；
- 完成期限后 `runs=0`：失败关闭
  `CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_MISSED`；
- 任意非零退出、stderr 非空、stdout 不唯一、summary 不合法、绑定漂移或
  观察期间文件改变：失败关闭并进入失败取证。

WAITING 与 PENDING 不创建 receipt。成功 receipt 只能由已经自然产生的证据生成，
不得回填或补跑。

## 4. 只读观察顺序

1. 通过 v0.51 production loader 重放 deployment manifest 和 install receipt；
2. 从 manifest 派生 candidate contract/plist，并再次由 external trust 验证；
3. 对 strategy state/stdout/stderr、maintenance stdout/stderr 和三个 cohort
   output roots 建立观察前快照；
4. 只执行一次固定命令：

   ```text
   /bin/launchctl print gui/501/local.crypto-quant.challenger-cohort-evidence-maintenance
   ```

5. 读取 maintenance stdout/stderr 和 output inventory；
6. 对同一对象建立观察后快照并要求逐项相同；
7. 根据状态机返回 WAITING/PENDING，或验证并原子发布成功 receipt。

观察器不得创建缺失的日志或 cohort roots。只有成功 receipt output root 可以在
成功路径上创建。

## 5. launchd 与日志验收

launchctl print 必须与 install receipt、target、candidate contract 的 Python、
WorkingDirectory、module、固定参数、stdout/stderr 和 08:10 调度完全绑定。

成功要求：

- `runs >= 1`；
- `last exit code = 0`；
- state 为 `not running`；
- stdout 是 UTF-8，且恰好一条非空 JSON 行；
- stderr 存在且为空；
- JSON 的 `observed_at` 合法，且不早于首槽、不晚于 observer 的 `observed_at`；
- summary status 只能是 v0.49 协调器的三个公开成功终态之一；
- receipt/archive/result stage 的执行门和计数关系符合 v0.49 冻结语义；
- security counters 中 Broker、订单、strategy state write 和 Runner 为 0；
- maintenance 本身只允许其 summary 明示的官方 archive network request count。

stdout 出现额外行、历史手工执行、未知 status、缺字段或不一致计数均失败关闭。

## 6. 文件与 inventory 证据

每个已存在文件记录绝对路径、device、inode、uid、mode、link count、size 与
SHA-256；缺失记录为 `exists=false`。目录 inventory 递归记录相对路径、大小与
SHA-256，并拒绝 symlink、非普通文件、hardlink、非当前 uid 或 group/world
可写对象。

成功 receipt 绑定：

- install receipt、deployment manifest、candidate contract 与 snapshot；
- first schedule、deadline 与 observed time；
- launchctl print exact argv、return code、stdout/stderr hash 与 evidence hash；
- maintenance stdout/stderr exact stat/hash 和 parsed summary；
- cohort receipt/archive/result inventories；
- strategy state/stdout/stderr 观察前后 hash；
- 所有观察对象的 pre/post unchanged 证明；
- observer 自身的 network/Broker/order/state-write/Runner/maintenance invocation
  计数均为 0，launchctl print count 为 1。

receipt 使用严格 Draft 2020-12 Schema、self-hash、stable id、owner-only
目录和无覆盖 exact publish。production loader 必须重放全部静态信任、receipt
hash/schema/identity、日志 exact bytes 与 inventory。

## 7. 时间矛盾与失败规则

观察器只信任带 UTC 时区且毫秒规范化的 injected/system clock、冻结合同和本机
证据。界面口述时间与系统/独立时间源冲突时不得越过状态机。

- 首槽前 `runs=0`、日志与 roots 缺失是正常 WAITING；
- deadline 后 `runs=0` 是漏槽，不得误报 pending；
- deadline 后服务仍运行、无法取得稳定快照或日志未完成时失败关闭；
- 非零退出保留 exact launchctl/log 现场，不自动重启；
- 任何失败都不得调用 maintenance CLI、补写日志、生成伪 success receipt。

## 8. 验收与发布

- focused tests 覆盖 waiting、pending、success、missed、非零退出、非空 stderr、
  stdout 多行/篡改、summary 语义错误、inventory 漂移、CLI authority；
- Schema config/package mirror 逐字节一致；
- production loader 拒绝协调重哈希的 receipt、日志和 inventory 篡改；
- 真实首槽前只读运行返回 WAITING，不创建 receipt，全部被观察对象前后不变；
- 全量 tests、compileall 和 evaluator build manifest 通过；
- v0.52 仅发布 observer 与首槽前 WAITING artifact；真实首次运行 receipt 必须在
  自然 08:10 后作为独立后续版本封存；
- PR、main CI 和 annotated `v0.52.0` tag exact 对齐。

## 9. 对赚钱目标的意义

本版本不产生收益，也不证明策略赚钱。它证明每日证据维护不是人工挑时运行，并使
漏跑、失败和不利结果无法被静默忽略。真实首次运行、完整 90 天全纳入 cohort、
固定 tail 累计门和费用后统计结果仍是盈利判断的必要条件。
