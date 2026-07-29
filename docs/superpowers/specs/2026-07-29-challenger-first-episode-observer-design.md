# v0.36 Challenger 首个 Episode 只读观察器设计

日期：2026-07-29

状态：冻结

冻结基线：`v0.35.0` / `c710b01`

## 1. 目标

在首个 episode 的退出结果可见以前，冻结并发布一个只读、失败关闭的观察器。
观察器从 v0.33 安装证据和 v0.32 LaunchAgent 契约推导唯一 runtime 路径，验证
SQLite decision chain、每槽唯一 source bundle、每槽唯一 stdout `RECORDED` 行和
当前 `launchctl print`，但不能触发 Runner、访问市场网络、写策略 state、调用
Broker 或提交订单。

v0.36 只交付观察器、Schema、测试和真实“进行中”观察结果；完整 episode 自然退出
后，后续证据版本才能封存成功 receipt。冻结发生时，已知 v0.35 首槽 action 是
`ENTER_LONG`，但尚未查看任何符合退出资格的未来槽位，所以成功定义不得随未来盈亏
修改。

## 2. 冻结输入与唯一权限

- forward start：`2026-07-29T00:00:00.000Z`；
- cadence：4 小时；record deadline：每槽 4 小时；
- 首个 entry：sequence 1，action `ENTER_LONG`；
- minimum hold until：`2026-07-29T08:00:00.000Z`；
- vertical exit at：`2026-07-30T00:00:00.000Z`；
- install receipt、contract、plist 和 receipt output root 使用 v0.35 设计冻结的四个
  绝对路径；
- CLI 只接受上述四类信任根路径，不接受 state、bundle、log、service、command、
  URL、symbol、credential、order 或 clock 覆盖；
- 唯一允许的外部命令是固定 argv：
  `/bin/launchctl print gui/501/local.crypto-quant.challenger-forward`；
- 观察器网络、Broker、订单和 state write count 必须全部为 0。

## 3. Episode 前缀定义

首个 episode 前缀从 sequence 1 开始，到同一 `episode_id` 第一次由 LONG 返回
FLAT 的 decision 为止，并满足：

1. sequence 1 必须在登记首槽由 FLAT 经 `ENTER_LONG` 进入 LONG；
2. 每条 decision 必须通过现有 canonical、自哈希、previous hash、4 小时连续性和
   semantic replay；
3. 退出前只能出现 `HOLD_LONG_MINIMUM` 或 `HOLD_LONG`，且 state 中的 episode id、
   entry、minimum hold 和 vertical exit 不变；
4. `HOLD_LONG_MINIMUM` 只能在 minimum hold 以前；
5. 首次返回 FLAT 只能是：
   - `EXIT_LONG_SMA20`，scheduled time 不早于 minimum hold；或
   - `EXIT_LONG_VERTICAL_24H`，scheduled time 不早于 vertical exit；
6. 完整前缀最多 7 条 decision（00、04、08、12、16、20、24 UTC）；
7. 若 state 已追加后续 decision，receipt 只绑定首个 episode 的不可变前缀，不把
   第二个 episode 混入首个 episode。

任何 gap、重复 sequence、错误 action、提前退出、越过 vertical exit 仍未退出、
episode state 漂移或首条不是登记 entry 都失败关闭。

## 4. Bundle 与日志交叉绑定

episode 前缀中的每条 decision 都必须恰好对应：

- 一个安全普通文件 source bundle；
- bundle 的 `candidate_decision` 与 SQLite canonical decision 完全相同；
- 一个 stdout `RECORDED` 行，绑定 decision id/hash、bundle path/hash；
- `server_time_request_count=3`、`kline_request_count=1`；
- `broker_request_count=0`、`order_submission_count=0`。

同一 scheduled time 出现零个或多个 bundle、零个或多个匹配日志行均失败。观察时
stdout/stderr 只保存 prefix stat/hash；后续允许追加，不允许修改已绑定前缀。
SQLite 允许以后追加 decision，但 receipt loader 必须重新证明已绑定 decision
前缀逐字节相同。

## 5. 冻结状态机

### 5.1 进行中

若首个 episode 前缀合法且最后一条 state 仍为 LONG：

- 返回 `FIRST_EPISODE_IN_PROGRESS_VERIFIED`；
- 不发布 receipt；
- 报告已验证 decision/bundle/log 数量、最后槽位、minimum hold、vertical exit；
- 若当前时间已达到下一槽 record deadline 而对应 decision 缺失，报告
  `CHALLENGER_FIRST_EPISODE_SLOT_MISSED`，不得继续等待；
- 若 vertical exit 槽位已记录但仍为 LONG，立即失败。

### 5.2 完成

只有 episode 首次合法返回 FLAT 且所有交叉绑定均通过时：

- 返回 `FIRST_EPISODE_COMPLETED_VERIFIED`；
- 发布 canonical、mode 0600、单 hardlink runtime receipt；
- receipt 固定绑定完整 decision/bundle/log 前缀、state file observation、
  launchctl print、安装证据和执行快照；
- loader 允许现场追加，但拒绝已绑定前缀变化；
- 后续证据版本只能复制 exact receipt bytes，不得重新计算一个更有利的 episode。

### 5.3 无资格或失败

以下结果不能形成成功 receipt：

- 首槽不存在、首槽不是 `ENTER_LONG` 或首槽已与 v0.35 证据冲突；
- 任何已到 deadline 的槽位缺失；
- state/WAL 正在变化、文件权限或所有权不安全；
- bundle、日志、service 或执行快照不一致；
- 观察时钟早于最后一条 decision 的 `recorded_at`；
- 观察器自身出现网络、Broker、订单、state 写入或任意命令能力。

禁止 kickstart、bootstrap、手工补槽、历史回填、改时钟或把第二个 episode 冒充
首个 episode。

## 6. Receipt 内容

成功 receipt 至少包含：

- receipt id/hash、observed at、冻结边界；
- install receipt、execution snapshot、contract、plist 和 launchctl evidence；
- state path/stat/hash、observed decision count、episode decision prefix、prefix root
  hash和chain end；
- episode id、entry/minimum/vertical/exit time、exit action；
- 按 sequence 排序的 bundle evidence；
- stdout prefix、每槽 matched line/hash，stderr prefix；
- 权限计数和资格声明。

Receipt 不计算或声称收益。decision 的 bar close 不是可成交价格，且本 forward
registration 没有冻结 entry/exit fill、手续费、滑点和仓位规模。将单个 episode
误标为盈利证据会制造选择偏差。

## 7. 验收与赚钱含义

- 设计提交必须早于首个可退出槽位并与实现提交分离；
- 进行中结果不写 receipt；
- SMA 提前退出与 24 小时垂直退出使用同一冻结规则；
- 成功、missing slot、篡改、重复 bundle/log、追加和时钟边界均有失败关闭测试；
- config 与 package Schema 镜像逐字节相同；
- 全量测试与 evaluator build 校验通过后才可发布 `v0.36.0`；
- v0.36 不改变 Challenger 策略和 LaunchAgent，不提供真实交易能力。

围绕赚钱，本版本的价值是确保第一笔完整研究 episode 不会被事后挑选、删除或改写。
一个 episode 无法证明可持续优势；后续仍需冻结成交与成本模型、积累多笔完整前向
样本，并用全成本净收益及下置信界判断是否值得进入 Paper 阶段。AI 仍无交易权限，
也不得在同一冻结评估前提下未胜过简单 Challenger 时升级。
