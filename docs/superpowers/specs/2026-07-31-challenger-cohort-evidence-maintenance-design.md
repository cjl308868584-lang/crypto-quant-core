# v0.49 Challenger Cohort 证据维护协调器设计

日期：2026-07-31

状态：冻结

冻结基线：`v0.48.0` / `09b81b9f3a670a20301d4b1090bb4293afc5bc7c`

## 1. 问题与目标

v0.45、v0.46、v0.47 已分别实现全量 Episode receipt、共享官方日档和全纳入
经济结果，但生产操作仍需依次执行三个 CLI。90 天 cohort 期间，这会留下“自然
decision 持续写入、证据维护没有跟上”的运营断层。

v0.49 新增一个单次、幂等、失败关闭的维护协调器。它严格按以下顺序执行：

1. 使用 v0.45 observer 验证完整可信 cohort 前缀，并发布全部自然完成且尚未发布的
   Episode receipts；
2. 使用 v0.46 acquisition 从全部 loader-verified receipts 自动求 UTC 日并集，仅
   获取已经越过固定时间门且尚未验证的官方 ZIP/checksum；
3. 只有全部所需日档均 verified 后，才使用 v0.47 publisher 生成全部经济结果和
   只追加索引。

该协调器只减少安全管线的操作遗漏，不改变策略、样本、价格、成本或累计盈利门。

## 2. 信任根与固定输入

必须精确复用 v0.45–v0.47 的现有 production loaders 和固定信任根：

- v0.43 cohort plan；
- v0.37 economic plan；
- v0.35 install receipt、contract 和 plist；
- owner-only Episode receipt、daily archive、economic result 三个互不重叠的根。

CLI 只接受上述七个路径参数。不得接受 clock、状态库、bundle、log、service、
Episode、日期、URL、symbol、价格、费用、资本、PnL、label、result id、filename、
重试次数或阶段选择器。生产时钟只能在进程内读取一次 UTC now，并传给 receipt 和
archive 阶段，避免同次维护中出现两个不同的资格时点。

## 3. 状态机

每次调用都从 receipt 阶段开始，不允许跳阶段：

`OBSERVE_RECEIPTS -> ACQUIRE_ARCHIVES -> PUBLISH_RESULTS`

### 3.1 Receipt 阶段

任何连续性、现场文件、LaunchAgent 或 receipt 冲突错误都使整次调用失败。不得在
错误后继续请求 archive 或发布经济结果。

### 3.2 Archive 阶段

v0.46 原有规则保持不变：

- 没有 completed Episode 时为安全 no-op，网络请求为 0；
- 未到完整 UTC 日结束后 5 分钟时为 pending，请求为 0；
- ZIP/checksum 404 保持 pending，不使用任何 fallback；
- 已 verified 日档不重复请求；
- 只有 allowlisted official public archive transport 可发起 GET。

若状态不是 `COHORT_DAILY_ARCHIVE_COMPLETE`，协调器停止，不调用经济结果阶段。

### 3.3 Result 阶段

仅在 archive complete 时调用 v0.47。它必须重新加载全部 receipts 和 archives，
自动派生并发布全部尚缺结果及 index。任何集合不完整、冲突或顺序异常均失败关闭。
中期结果仍固定为 `DESCRIPTIVE_NO_EARLY_SUCCESS`。

## 4. 汇总输出

协调器不新增第四套持久化 artifact。v0.45–v0.47 已分别保存可重放的 exact
证据，重复保存维护日志会制造与研究结论无关的可变文件集合。

CLI 只向 stdout 输出 canonical compact JSON，包含：

- 总体状态与唯一 `observed_at`；
- 三个阶段是否执行、原始阶段状态和关键计数；
- 新建 receipt、verified day、网络请求、新结果和新 index 数；
- market/Broker/order/strategy-state-write/Runner 总计。

固定总体状态：

- `COHORT_EVIDENCE_NO_COMPLETED_EPISODES`；
- `COHORT_EVIDENCE_WAITING_ARCHIVES`；
- `COHORT_EVIDENCE_MAINTAINED_DESCRIPTIVE_NO_EARLY_SUCCESS`。

所有安全计数必须可由阶段返回值相加验证。出现缺字段、非整数、负数、未知状态、
或任一 Broker/order/state-write/Runner 非零均失败关闭。

## 5. 权限与路径

CLI 沿用 v0.47 的 owner、mode、symlink 和 output-base 验证，并要求 receipt、
archive、result 三根两两不等、互不为祖先。receipt 根允许尚不存在或 mode
0700/0755；archive/result 根允许尚不存在，存在时必须是 owner-only mode 0700。

不创建协调器输出目录。没有 completed Episode 的真实 no-op 必须保证 archive 和
result 根在调用前后均不出现。

## 6. 安全边界

允许：

- 只读 SQLite、source bundles、stdout/stderr、install receipt、contract、plist；
- 固定 argv 的一次 `launchctl print`；
- 发布自然完成 Episode 的 owner-only receipt；
- 时间门后的 allowlisted Binance official ZIP/checksum GET；
- 发布 verified archive、经济结果和只追加 index。

禁止：

- 调用 Runner、`kickstart`、`bootstrap`、补槽或回填；
- 写 runtime strategy state；
- Broker、余额、凭据或订单；
- 新增实时市场请求；
- REST、网页、第三方或手工 URL/date fallback；
- 按 PnL、Episode 或日期选择性执行；
- 固定 tail end 前调用 v0.48 或形成 PASS。

## 7. 验收

- 设计提交与实现提交分离；
- 单测覆盖 no completed、archive pending、archive partial、archive complete、
  receipt 失败、archive 失败、result 失败和未知/恶意阶段计数；
- pending 时证明 result publisher 调用次数为 0；
- complete 时证明固定顺序、单一时钟和全部关键字参数精确传递；
- CLI 路径越界、symlink、权限和根重叠均失败；
- CLI 不含 Runner、Broker、credential、order 或 v0.48 import；
- 真实当前 cohort no-op/maintenance 运行前后核对策略 state、stdout、stderr；
- 聚焦、相邻、全量测试、Schema mirror、compileall 和 evaluator build manifest
  全部通过。

## 8. 对赚钱目标的意义

v0.49 不创造收益，也不允许根据当前收益提前停止。它保证每个自然 completed
Episode 都更难被遗漏，每个负结果与正结果一样进入后续累计门。只有固定 tail end
后的 v0.48 对完整 540 槽和全纳入结果通过预注册统计门，才有资格进入下一研究
阶段；即使通过，也不是实盘盈利保证。
