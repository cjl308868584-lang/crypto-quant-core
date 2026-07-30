# ADR-0043：Challenger 多 Episode 前瞻队列

日期：2026-07-30

状态：已接受

## 背景

v0.42 已封存首个自然完成 Episode 的真实前向经济代理。该样本在冻结的成交代理
与成本口径下净亏损 `23.4627746535 USDT`。它必须保留，但单个 Episode 既不能
证明盈利，也不能证明长期亏损。若在看到该结果后自由选择起点、终点、样本或停止
时间，会产生选择偏差和可选停止，后续结论失去可信度。

在本决策冻结时，首个 Episode 退出后的四个槽位均为 `REJECT_ENTRY`，第二个
Episode 尚未开始。设计冻结提交 `9083bf5` 早于固定 cohort 起点。

## 决策

1. 首个 v0.42 结果永久标记为
   `EXPOSED_PILOT_MANDATORY_ALL_STREAM`，不纳入 future-only confirmatory
   估计，但必须出现在 all-stream 报告中。
2. confirmatory cohort 固定为
   `[2026-07-30T12:00:00.000Z, 2026-10-28T12:00:00.000Z)`；所有入场槽位
   位于该半开区间的 `ENTER_LONG` Episode 全部纳入。
3. 窗口内开始的 Episode 即使在终点后退出也跟踪至自然退出，观察尾部固定到
   `2026-10-29T12:00:00.000Z`。
4. 所有 `REJECT_ENTRY` 槽位保留作 4h 流连续性证据；漏槽、不可解释 revision
   或信任绑定失败时 fail closed，禁止回填。
5. 继续使用 v0.37 冻结的 next-strict-minute、双边 10bps 滑点、双边 15bps
   taker fee、1000 USDT 和 Decimal 口径。
6. 不允许因正负 PnL、胜率、回撤或主观判断提前停止，也不允许延长或重置同一
   cohort。中期结果只能是 `DESCRIPTIVE_NO_EARLY_SUCCESS`。
7. 90 天结束时若样本、有效样本、月份、功效、区间宽度或依赖区块不足，结果为
   `INCONCLUSIVE`，不能用点估计晋级。
8. AI 不进入该 cohort。未来 AI 比较必须另行在结果前冻结同事件、同时间、同
   资本与双账本的配对设计。

## 机器约束

v0.43 的 Schema 对 pilot、时间窗口、策略身份、成本、停止、报告、AI 和资格字段
使用精确常量。Builder 只接受 v0.42 exact result 及其外部 SHA-256，不接受日期、
Episode、费用或经济结果覆盖；loader 同时验证 Schema、自哈希与语义重建。重算
自哈希不能掩盖篡改。

## 后果

该版本只注册观察规则，不触发 Runner、市场请求、Broker、订单或 strategy state
写入，也不声称已完成 90 天 Paper。直到完整 cohort 结束并通过后续冻结的累计
评估门，`profitability` 与 `ai_comparison` 都保持不合格。
