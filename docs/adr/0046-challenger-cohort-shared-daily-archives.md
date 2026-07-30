# ADR-0046：Challenger Cohort 共享 UTC 日档

日期：2026-07-30

状态：已接受

## 背景

v0.39 的官方日档 receipt 绑定首个 pilot Episode，因此不能直接供 90 天 cohort
中的其他 Episode 复用。若为每笔 Episode 重复保存同一天，既浪费请求，也可能在
并发或远端修订时产生同日多份相互冲突的来源；若允许调用方传日期，则会重新引入
挑样和只计算正收益交易的空间。

## 决策

1. 以独立提交 `b550f4d` 冻结 v0.46 共享日档设计，继承 v0.45–v0.48 上位设计。
2. 生产 CLI 扫描固定 receipt 子目录并使用 v0.45 loader 验证全部文件；不接受
   Episode、日期、symbol、URL、价格或 PnL 选择器。
3. 日期只能从每个 receipt 的 entry/exit `recorded_at` 严格之后第一个完整 UTC
   分钟自动派生，并对全部 completed Episodes 求并集。
4. 每个 UTC 日在固定 owner-only 子目录只发布一份 exact ZIP、checksum 和
   canonical day receipt。
5. day receipt 绑定 exact cohort plan、固定 ETHUSDT Spot 1m DAILY request、
   全日 1440 行覆盖及内容哈希，但不绑定单个 Episode 或当时的 Episode 集合。
6. 后来出现的同日 Episode 必须复用已验证 exact bytes，网络请求为零；跨日只补
   缺失且已过日结束后五分钟时间门的日期。
7. 404 保持 pending，禁止 REST、网页、第三方、手工 fallback、Runner、Broker、
   订单或 runtime strategy state 写入。

## 后果

v0.46 为 v0.47 的逐 Episode 经济结果提供无冲突、可重放的共享来源，但不计算
收益，也不改变策略或交易行为。完整 cohort 是否具有成本后正收益，仍必须等待
v0.47 全纳入结果与 v0.48 固定尾部累计门，不能由单日、单 Episode 或少量正样本
推断。
