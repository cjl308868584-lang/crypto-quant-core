# 实施追踪 v0.43.0

日期：2026-07-30

状态：多 Episode confirmatory cohort 已在第二 Episode 前注册

## 本版本完成

- 设计冻结提交 `9083bf5`，时间为北京时间 `2026-07-30 17:05:51`；
- cohort 注册时间为 `2026-07-30T09:10:00.000Z`；
- 固定 90 天 future-only 窗口：
  `2026-07-30T12:00:00.000Z` 至 `2026-10-28T12:00:00.000Z`；
- 固定 24h 退出跟踪尾部至 `2026-10-29T12:00:00.000Z`；
- 新增 Schema/package mirror、deterministic builder、owner-only publisher/
  loader、自哈希、stable ID 与 canonical artifact；
- 将 v0.42 首个负结果逐字段绑定为已暴露 pilot，禁止删除、翻正或冒充
  confirmatory；
- 冻结全 Episode 纳入、拒绝入场槽位连续性、停止、报告及 AI 边界；
- builder/loader 不读取 runtime state，不发起网络、Runner、Broker 或订单调用。

## 固定证据

- known pilot file SHA-256：
  `8627677275c31de573f1a59f638ba1678772115dc6d932027a36e2f8b62d9fee`；
- known pilot net PnL / return：
  `-23.4627746535 USDT / -0.0234627746535`；
- policy hash：
  `2ef83c7c73fff8b163d9bad8527921bd0d87e60595680236e936254536c800e4`；
- hypothesis registration hash：
  `885b33d3a91eae1d5822fe12c16773a446c23e702f9a4110ef32f474157fa27f`；
- cohort plan ID：
  `challenger_episode_cohort_plan_56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c`；
- plan self hash：
  `20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201`；
- exact artifact SHA-256：
  `a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff`。

## 结果解释

这是结果后暴露的 pilot 与结果前 future-only cohort 的明确分界，不是赚钱证明。
首个负样本保留在 all-stream，但不污染 confirmatory 估计。队列开始后不得因为
短期盈利或亏损提前结束、重置日期或挑选 Episode。

90 天到期并不自动意味着 PASS：证据不足时必须 `INCONCLUSIVE`。累计经济结果、
依赖稳健区间、回撤和尾部风险仍需后续独立冻结的 evaluator 版本完成。

## 安全边界

- market / Runner / Broker / order / strategy-state write：`0/0/0/0/0`；
- 没有凭据、余额读取、真实成交或生产交易能力；
- AI training/trading authority：关闭；
- profitability：`INELIGIBLE_COLLECTION_NOT_COMPLETE`。

## 验证

- cohort focused 回归：8/8；
- 全量 tests：586/586；
- 100 次 deterministic build：逐字节一致；
- 窗口、pilot、policy、停止、AI 与资格字段在重算自哈希后仍不可篡改；
- Golden Vector：41；
- Evaluator build input：185；
- Build input tree hash：
  `684fd7b4c838b924045030150d438637ef36bd02ceedef99321c97e5e808c0fd`；
- Evaluator build hash：
  `fe17edf5fe8cd061c8dbe9cf9b75547097077a8ac0d3711001560ade010084e1`；
- `make validate`：完成；生产门禁继续保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 下一步

不干预地持续保留 4h Challenger 流。为每个自然完成 Episode 使用相同冻结经济
代理生成结果，并建立只追加的 cohort ledger；中期只报告完整性与运行状态，不
发布盈利 PASS。后续再冻结累计评估器与最终 90 天裁决版本。
