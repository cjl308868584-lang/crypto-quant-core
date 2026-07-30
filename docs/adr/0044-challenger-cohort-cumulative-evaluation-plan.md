# ADR-0044：Challenger Cohort 累计经济评估计划

日期：2026-07-30

状态：已接受

## 背景

v0.43 在第二 Episode 之前冻结了 90 天全纳入 cohort，但只说明证据不足必须
`INCONCLUSIVE`，尚未固定 Episode 数、ESS、Bootstrap、功效、精度、压力与
leave-out 的具体门槛。若等待结果出现后再选择这些参数，仍会形成分析者自由度和
可选结论。

## 决策

1. 在 cohort 首槽之前，以提交 `cd3ad50` 冻结唯一累计评估设计。
2. 要求 90 天内 540 个 UTC 4h 槽位完整、连续且不可回填；所有 entry 位于窗口
   内的 Episode 全部进入 confirmatory 总体。
3. 首个 v0.42 负结果只作为已暴露 pilot 单列，并永久保留在 all-stream 描述中。
4. 主终点为每 Episode 扣除冻结摩擦后的平均 `net_return`，唯一确认性假设为其
   单侧 95% MBB 下界大于 0。
5. 固定 block length 3、10,000 replicates、seed 2026073044、保守 nearest-rank
   quantile、MERE 0.5%、功效至少 80%、双侧 CI 全宽最多 2%。
6. 要求至少 30 个完成 Episode、ESS 至少 20、至少 10 个 MBB block，且六个固定
   15 天时间块均非空。
7. 经济门还要求至少 5/6 时间块非负、固定名义路径最大回撤低于 10%、1.5x
   摩擦压力累计 PnL 非负，以及删除 Top-5 正贡献 Episode 后主下界仍大于 0。
8. 任一样本、ESS、块、功效或精度不足均为 `INCONCLUSIVE`；连续性或来源信任
   失败为 `FAILED_CLOSED_NO_BACKFILL`。
9. 90 天内禁止提前成功、按 PnL 停止、延长或重置窗口。

## 后果

即使全部研究门通过，也只允许进入下一研究阶段。结果仍不是系统 Paper、sealed
Release Audit、实际成交盈利或 AI 优势证据，不得开启真钱交易。

该计划 builder 不读取 runtime state、市场、Broker、订单或 credential；v0.44
不观察 confirmatory outcome，也不改变 LaunchAgent。
