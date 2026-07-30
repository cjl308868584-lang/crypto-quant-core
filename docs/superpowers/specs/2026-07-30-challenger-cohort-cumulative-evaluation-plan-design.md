# v0.44 Challenger Cohort 累计经济评估计划设计

日期：2026-07-30

状态：冻结

## 1. 目标

在 v0.43 future-only cohort 的首个槽位和任何 confirmatory Episode 结果出现前，
冻结 90 天结束后的唯一累计经济评估方法。目标不是让现有单笔亏损“变好看”，而是
预先回答：简单 Challenger 在同一保守成本口径下，是否形成足以进入下一研究阶段
的正经济证据。

本计划只定义 `RESEARCH_CONTINUATION` 门，不是正式 Release Audit、系统 Paper、
实盘盈利证明或 AI 优势证明。

## 2. 来源与边界

唯一 cohort 来源为 v0.43 exact plan：

- plan ID：
  `challenger_episode_cohort_plan_56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c`；
- plan self hash：
  `20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201`；
- exact file SHA-256：
  `a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff`；
- window：
  `[2026-07-30T12:00:00.000Z, 2026-10-28T12:00:00.000Z)`；
- observation tail end：
  `2026-10-29T12:00:00.000Z`。

首个 v0.42 负结果继续作为
`EXPOSED_PILOT_MANDATORY_ALL_STREAM` 单独展示，不进入 confirmatory 统计量，也
不得从 all-stream 描述中删除。

## 3. 完整性总体

固定窗口包含 `540` 个 UTC 4h 槽位。最终评估必须证明：

- 每个槽位恰好一条合法 Challenger decision；
- decision chain、SQLite state、stdout 与唯一 source bundle 逐槽交叉一致；
- 所有 entry slot 在窗口内的 `ENTER_LONG` Episode 全部纳入；
- 每个纳入 Episode 跟踪到唯一自然退出，即使退出发生在窗口结束后；
- 每个 Episode 都有同一冻结口径生成的 completion receipt、官方日档 receipt
  和经济结果；
- `REJECT_ENTRY`、持有槽位及负 Episode 不得删除；
- 漏槽、重复、不可解释 revision、bundle/log/state 断链或 trust binding 失败
  直接 `FAILED_CLOSED_NO_BACKFILL`。

任何调用方不得传入日期、Episode 列表、价格、费用、PnL、label、样本排除项、
bootstrap 参数、阈值、result ID 或 filename。

## 4. Confirmatory 观察量

每个完成 Episode 按 entry slot 升序形成一个观察，值为冻结经济结果中的
`net_return`。它必须来自：

- next strict UTC minute；
- entry minute `high`、exit minute `low`；
- 双边 10bps slippage；
- 双边 15bps assumed taker fee；
- 1000 USDT reference capital；
- 0.01 USDT tick、0.0001 ETH step；
- Decimal-only 舍入。

主统计量为全部 confirmatory Episode 的算术平均净收益：

```text
mean_episode_net_return = sum(net_return_i) / completed_episode_count
```

这是固定名义资本的研究代理，不冒充复利账户收益。累计路径另按：

```text
equity_0 = 1000 USDT
equity_k = equity_(k-1) + net_pnl_usdt_k
```

计算最大回撤；任一 `equity_k <= 0` 直接判定经济门不通过。

## 5. 固定时间分块

90 天窗口从起点起划分为 6 个连续、互不重叠的 15 天块，每块固定 90 个槽位。
Episode 只按 entry slot 归属一个块，退出时间不改变归属。

- 每块必须至少有 1 个完成 Episode，否则证据不足；
- 至少 5/6 个块的 `sum(net_pnl_usdt)` 必须不小于 0；
- 空块不能按 0 收益计作非负块；
- 不允许根据结果改变块边界。

## 6. 冻结的统计设计

确认性主假设只有一个：

```text
H0: mean_episode_net_return <= 0
H1: mean_episode_net_return > 0
```

family size 固定为 1，Holm family-wise alpha 为 `0.05`，因此主假设 alpha 仍为
`0.05`。不得从多个候选指标中挑选显著者。

Moving-block Bootstrap 参数固定为：

- observation order：entry slot ascending；
- block length：`3` 个连续 Episode；
- minimum block count：`10`；
- sampling：
  `OVERLAPPING_NON_CIRCULAR_MBB_TRUNCATE_TO_N`；
- resample count：`10000`；
- seed：`2026073044`；
- quantile：
  `CONSERVATIVE_NEAREST_RANK_V1`；
- one-sided interval：
  `ONE_SIDED_95_PERCENTILE_MBB_LCB_V1`；
- two-sided precision interval：
  `TWO_SIDED_95_PERCENTILE_MBB_V1`；
- effective sample：
  `GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1`；
- power：
  `SHIFTED_CENTERED_MBB_AT_MERE_V1`；
- minimum economically relevant effect：
  `0.005` net return per Episode；
- achieved power minimum：`0.80`；
- two-sided CI maximum full width：`0.02`。

样本门固定为：

- nominal completed Episode count `>= 30`；
- effective event count `>= 20`；
- `floor(N / 3) >= 10`；
- 6 个固定块均非空；
- achieved power `>= 0.80`；
- two-sided CI full width `<= 0.02`。

任一样本、ESS、区块、功效或精度门不足时为 `INCONCLUSIVE`，不得把点估计用作
PASS。

## 7. 必需经济门

只有样本门全部满足后，才评估以下全部必需门：

1. `mean_episode_net_return_lcb95 > 0`；
2. 至少 `5/6` 固定 15 天块累计净 PnL 非负；
3. 固定名义资本累计路径最大回撤 `< 0.10`；
4. 1.5x 摩擦压力下全部 Episode 的累计净 PnL `>= 0`；
5. 删除净 PnL 最大的 5 个正 Episode 后，使用相同 MBB 参数重算的
   `mean_episode_net_return_lcb95 > 0`。

1.5x 摩擦压力固定为从相同官方 source rows 完整重算：

- entry slippage：`0.0015`，按 tick 向上；
- exit slippage：`0.0015`，按 tick 向下；
- 双边 taker fee：`0.00225`；
- quantity 重新按 `1000 / stressed_entry_fill` 向下到 0.0001 ETH；
- 其余公式和 Decimal 顺序不变。

Top-5 leave-out 只删除 `net_pnl_usdt > 0` 的最多 5 个 Episode，按 PnL 降序、
Episode ID 升序打破并列；若正 Episode 少于 5 个则删除全部正 Episode。删除后
样本门再次全部适用，不能只比较点估计。

## 8. 最终状态机

在 observation tail end 以前：

```text
COLLECTING_DESCRIPTIVE_NO_EARLY_SUCCESS
```

到达时间门并完成全部可信输入后，唯一允许的结果为：

- `RESEARCH_CONTINUATION_GATE_PASS`：样本门与 5 个经济门全部通过；
- `RESEARCH_CONTINUATION_GATE_DID_NOT_PASS`：样本门充足，但至少一个经济门失败；
- `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`：完整性可信但样本/ESS/块/功效/精度不足；
- `FAILED_CLOSED_NO_BACKFILL`：连续性、来源、身份或语义信任失败。

`RESEARCH_CONTINUATION_GATE_PASS` 只允许开发下一阶段评估，仍必须标记：

- `profitability = INELIGIBLE_RESEARCH_PROXY_NOT_SYSTEM_PAPER`；
- `release_oos = INELIGIBLE_NO_SEALED_RELEASE_AUDIT`；
- `execution = INELIGIBLE_PROXY_NOT_REAL_FILL`；
- `ai_comparison = INELIGIBLE_NO_PAIRED_AI_COHORT`。

## 9. 中途报告与停止规则

- 90 天内不得产生盈利 PASS；
- 不因正负 PnL、胜率、回撤、市场观点或暂时显著性提前成功或停止；
- 中途只发布槽位完整性、Episode 数和运行健康，不发布可被解释为成功的 PnL
  排名；
- 允许立即记录技术信任失败，但禁止修补后把同一 cohort 重新标为 confirmatory；
- 不允许延长、重置或复制本 cohort；不足只能得出 `INCONCLUSIVE`。

## 10. AI、Paper 与正式盈利边界

本计划没有 AI 模型、AI 行为权或 AI 账本。未来 AI 必须使用新的结果前配对计划。

本 cohort 也不满足现有系统 Paper 全部门：

- 没有真实 Broker、真实成交和实际滑点；
- 没有账户实际费率；
- 没有完整订单、对账、故障恢复和资本就绪证据；
- 90 天只覆盖两个完整 UTC 月，不能替代正式月度经济 PnL LCB；
- 没有 sealed Release Audit。

因此即使研究门通过，也不能宣传“策略已经赚钱”或开启真钱交易。

## 11. v0.44 交付与验收

本版本只交付评估计划，不观察 confirmatory 槽位或结果：

- exact Schema 及 package mirror；
- deterministic builder、loader、自哈希和 stable ID；
- canonical committed plan artifact；
- 精确绑定 v0.43 plan 的 ID/hash/file SHA；
- 对全部阈值、分块、压力、leave-out、状态机和资格边界的回归；
- ADR、实施追踪、版本与 evaluator build manifest。

验收：

- 同输入 100 次产生相同 canonical bytes；
- 调用方没有时间、样本、阈值、成本或统计参数覆盖；
- 篡改任一规则后即使重算自哈希，loader 仍拒绝；
- builder 不读取 runtime state、市场、Broker、订单或 credential；
- 不触发 Runner、不写 strategy state、不获取新的市场数据；
- v0.44 设计冻结提交早于 cohort 首槽
  `2026-07-30T12:00:00.000Z`。
