# ADR-0049：Challenger Cohort 证据维护必须固定顺序、失败关闭

日期：2026-07-31

状态：已接受

## 背景

v0.45–v0.47 已分别建立自然完成 Episode 的 receipt、共享官方日档和全纳入经济
结果，但需要操作方依次运行三个入口。长期收集期间，漏跑中间步骤不会影响策略
decision，却会造成证据流水线落后，增加遗漏负样本或误判结果完整度的风险。

## 决策

1. 以独立提交 `0b1851f` 冻结 v0.49 详细设计。
2. 新增一个无持久化自身 artifact 的维护协调器，固定执行
   `v0.45 observer -> v0.46 acquisition -> v0.47 publisher`。
3. 同次运行只取一次 UTC now，并同时传给 observer 与 acquisition。
4. receipt 阶段任一失败立即停止；archive 未 complete 时绝不调用 result 阶段。
5. 没有 completed Episode 时返回零请求 no-op；时间门前请求为零；404 只保持
   pending，禁止任何替代来源。
6. 验证三个阶段的状态、集合计数和安全计数；未知状态、计数不一致或任何
   Broker/order/state-write/Runner 非零均失败关闭。
7. CLI 只接受冻结计划、信任根和三个互不重叠 owner-only 输出根，不接受
   Episode、日期、URL、价格、成本、PnL、阶段或重试覆盖。
8. v0.49 不调用 v0.48，不读取累计收益，也不能形成提前 PASS。

## 后果

cohort 证据维护从三个易漏操作收口为一个可重复运行的安全入口，同时继续保留
v0.45–v0.47 的 exact artifact 作为唯一持久化审计事实。它提高证据完整性，不提高
策略收益，也不改变最终统计门。是否值得进入下一研究阶段仍只能在固定 tail end
后由 v0.48 对完整 cohort 判定。
