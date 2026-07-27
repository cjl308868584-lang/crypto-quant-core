# 实施追踪 v0.27.0

日期：2026-07-28

状态：已完成并验证

## 本版本完成

- 在仓库外 owner-only 目录恢复执行完整 42 月、四流、168 项研究语料；
- 168/168 成功，0 pending、0 failed，独立新进程重放 338 个状态事件；
- 新解析器支持 Binance 官方 underscore header 与 Funding 不超过 1 秒的
  schedule 抖动，同时保留 V1 快照验证兼容；
- 对两个月度 ETH Mark 4h 来源缺口保留明确 degraded 状态；
- 从 exact missing open time 推导 `2023-02-24`、`2026-06-29` 两个官方
  daily archive，并通过官方 checksum；
- 用 2 个 daily patch 精确闭合 12 个 4h 间隔，无重叠、无插值、无 REST
  回填、无未解决间隔；
- 新增 repair Schema、语义重建、自哈希、combined coverage root、
  owner-only 原子发布与冲突拒绝；
- 在全新 Python 进程中禁止网络并离线重建 repair bundle，结果 exact match；
- Git 仅保存 compact completion evidence，不保存 61,812 KiB full corpus。

## 完整语料证据

- Plan hash：
  `1a00b56ebb1ebe89340a31665103eb60f631992b31170d26568e1011f06c086d`
- Base corpus snapshot hash：
  `138375b0f7cc88beffa9306f20c21d7d1ce6d6f1d91b8bd205703c6e33b315c6`
- Base event chain end：
  `7e8f1addc53981e0e2cee710562cd1d945ac2a5da5216dab1bf08089a5da0c82`
- Base physical GET：338；repair physical GET：4；
- Repair bundle hash：
  `4a7112cf14e8d6fd96cc0ec30c8df63494655b3e728d855b705febf3bbb1d557`
- Final coverage：168 monthly items + 2 explicit daily patches，未解决间隔 0；
- Final readiness：
  `READY_FOR_ARCHIVE_RESEARCH_FEATURE_BUILD_WITH_EXPLICIT_DAILY_REPAIRS`。

完整 compact 证据见
[binance-research-corpus-completion-v0.27.0.json](../artifacts/research-corpus/binance-research-corpus-completion-v0.27.0.json)。

## 验证证据

- repair/corpus/market focused tests：81/81；
- Golden Vector：41；
- 全量 tests：466/466；
- Evaluator build input：123；
- Build input tree hash：
  `63107af91718bdb0fd50c3f65f041b743fcb5e17fc6a556fd000d16e2dc227a6`
- Evaluator build hash：
  `348d8de7bd531df191a3e28b2402adeb94e2b4614a27f2a7f220a239104a9dd9`

## 赚钱与 AI 含义

本版本完成的是 AI 研究的连续输入层，不是盈利策略。它降低了缺失行、窗口
漂移、静默来源替换和不可恢复下载导致的假优势，但没有创造任何交易信号。

当前仍没有 event-based 保守执行标签、低维 Logistic 基准、批准的 XGBoost
ModelBundle、正式 PIT-valid OOS Release Audit、真实成交滑点或配对增量收益
证据。因此不能声称 AI 优于简单趋势/突破，更不能声称系统能赚钱。

## 下一步

1. 从完整 archive corpus 构造同槽位、严格滞后的低维特征；
2. 冻结 24h event-based 保守执行标签和成本口径；
3. 先训练 Logistic 研究基准，再让 XGBoost 只做成本感知过滤；
4. 继续累计 contemporaneous context-complete Paper；只有基线独立通过、
   AI 配对增量通过及 Forward 门通过后，才讨论真实资金。
