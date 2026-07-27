# ADR-0030：Challenger 事件流与仅前向记录器

日期：2026-07-28

状态：已接受

## 背景

v0.29 已拒绝费用前也亏损的 v1，并预注册唯一 challenger
`SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2`。若继续在已看 archive 上运行新规则，
结果仍然是开发数据，无法证明未来赚钱；若只保存最后状态，则无法证明拒绝信号、
持有窗口和退出路径没有被事后改写。

## 决策

1. 用 21 根连续且已闭合的 ETHUSDT Spot 4h Kline 构造每个决策。
2. FLAT 时仅在 `latest/prior_sma20-1 >= 0.005` 且 5-bar log return
   `> 0` 时进入 LONG。
3. LONG 最短持有 8h；此后 close `<= prior_sma20` 退出，24h 强制退出；
   同一槽位 SMA 退出优先。
4. 拒绝入场保持 FLAT，不创建 episode，也不消费后续窗口。
5. 首槽固定为 `2026-07-29T00:00:00.000Z`，此后严格每 4h 一次；
   不允许迟到、漏槽、乱序、回填或相邻窗口历史行修订。
6. 每条决策绑定输入事实 root、策略、预注册、上一决策和完整经济状态，
   并写入 owner-only append-only SQLite WAL。
7. exact bytes 重试幂等；同槽不同内容、UPDATE、DELETE、原始数据库篡改和
   semantic replay 不一致均失败关闭。
8. 决策永久为 research-only；模块不导入 Broker/Order/Execution，不读取余额，
   不下单。
9. 零决策时不生成 prequential snapshot；Git 只记录诚实的 not-run 证据。
10. 本地时钟即使满足槽位，也不能自证外部时间。缺少独立 publication
    attestation 时只能标记为 `UNANCHORED_LOCAL_CLOCK`。

## 理由

赚钱目标需要可区分“规则事先固定”和“看到结果后修改”的证据链。连续事件流和
输入重叠校验阻止重写历史；完整状态重放确保拒绝入场不会暗中消耗 episode；
append-only WAL 提供崩溃恢复和精确幂等。禁止 Broker 权限使研究收集器即使
失效也不能扩大为真实资金风险。

## 拒绝的方案

- 用 v0.28 archive 回填从 7 月 1 日开始的 forward：拒绝；规则当时尚未冻结。
- 只记录发生交易的槽位：拒绝；无法证明被拒绝信号和连续性。
- 为赶进度创建 fixture snapshot 作为真实证据：拒绝；fixture 只验证代码。
- 依赖 Git commit 时间作为唯一外部时间锚：拒绝；本地 commit 本身不是独立
  可信时间证明。
- 直接连接 Binance 下单：拒绝；当前阶段只收集研究决策。

## 后果

v0.30 只交付可验证的前向记录能力，不交付任何盈利结论。版本冻结时首槽尚未
发生，正式状态为 `WAITING_FORWARD_START_NO_DECISIONS`。下一步必须在允许槽位
实时采集官方公开输入，并添加仓库之外的独立时间锚；任何漏掉的槽位永久不可
回填。
