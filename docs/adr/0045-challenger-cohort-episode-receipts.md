# ADR-0045：Challenger Cohort 全量 Episode Receipt

日期：2026-07-30

状态：已接受

## 背景

v0.36–v0.42 的可信管线只能识别首个已暴露 pilot，并把其固定入口、receipt
schema 与经济计划硬编码在 loader 中。v0.43 已经要求 90 天窗口内全部 Episode
纳入；继续手工指定 Episode 会重新引入挑样、漏掉负样本和只报告好结果的空间。

## 决策

1. 以北京时间 2026-07-30 19:17、cohort 首槽以前的提交 `33c6d7a` 冻结
   v0.45–v0.48 全证据流水线。
2. v0.45 新增独立的 cohort Episode receipt schema、observer、loader 和 CLI；
   旧首 Episode artifact 与 loader 保持不变。
3. CLI 只接受 exact v0.43 cohort plan 与 v0.35 已冻结的安装信任根，不接受
   Episode、sequence、日期、时间、state、bundle、log、URL、价格或 PnL 选择器。
4. 每次观察从 cohort start 验证整个已到达 4h 槽前缀，包括所有
   `REJECT_ENTRY`，并自动枚举全部 completed Episodes。
5. 一次运行发布全部且仅全部尚未发布的 completed Episode receipt；进行中和无
   entry 状态不产生伪完成 receipt。
6. 每份 receipt 绑定从 cohort start 到自身 exit 的 decision/bundle/log
   前缀，以及所有更早 completed Episode ID，证明不能跳过较早样本。
7. receipt 为 owner-only、canonical、只追加；现场后续追加不破坏已绑定前缀，
   任何历史 revision、gap、重复或输出冲突失败关闭。

## 后果

v0.45 消除了通过调用参数只选择某一笔交易的能力，但只证明 Episode 证据完整，
不计算收益。v0.46 将实现按 UTC 日去重的官方日档层，v0.47 才生成全 Episode
经济结果，v0.48 在固定尾部结束后执行累计门。

本版本不改变 Runner、LaunchAgent、策略 state 或交易行为；没有 Broker、订单、
凭据或新增实时行情请求，也不构成盈利、Paper 或 AI 优势证据。
