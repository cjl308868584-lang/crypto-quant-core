# 实施追踪 v0.23.0

日期：2026-07-28

状态：已完成并验证

## 本版本完成

- 新增 Paper 与账户 commission 的双源信任绑定；
- 两个源 Artifact 均要求 Schema、self-hash、语义重放和外部 attestation；
- 账户费率必须在决策前观测并覆盖 Paper run end，禁止事后回填；
- 从原始 Paper fill/economic snapshot 重建进场/退出 notional 和 15 bps
  假设费用；
- 使用账户 Spot no-discount `taker_buy` / `taker_sell` 精确重放费用；
- 只调整费用和保守清算权益，不改变信号、成交、数量、价格、滑点或行情；
- 无交易周期费用保持 0，权益保持不变；
- BNB discount 不进入权威结果，AI arm 不运行；
- 新增严格 Schema、self-hash、外部绑定 attestation 和 mode-0600 CLI；
- CLI 不联网、不读 credential、不读余额、不下单，也不接受任意费率覆盖。

## 费用重放样例

确定性 fixture 将 v0.18 的同一笔真实公开行情离线 Paper 成交与测试账户费率
绑定：

- 原 15 bps 双边费用：`0.2689136415 USDT`
- 测试账户 no-discount 双边费用：`0.046763081109 USDT`
- 费用差：`-0.222150560391 USDT`
- 原保守清算权益：`999.5506993585 USDT`
- 重放后保守清算权益：`999.772849918891 USDT`
- 重放后相对 1000 USDT 仍为：`-0.227150081109 USDT`

这些数值证明精确成本绑定路径和原假设的保守程度，不是仓库中的真实账户费率，
也不是 24h/90天收益或盈利证明。

## 真实绑定

仓库没有真实 `account-commission-snapshot-v1`，因此没有形成真实
Paper/account-cost binding。没有以测试 signer、fixture、网页费率或未来费率
替代真实账户证据。

冻结证据：
[binance-paper-account-cost-binding-not-run-v0.23.0.json](../artifacts/paper-cost/binance-paper-account-cost-binding-not-run-v0.23.0.json)。

## 赚钱与 AI 含义

系统现在能证明“同一笔 Paper 结果在当前账户成本下如何变化”，减少固定 15 bps
假设对可交易性判断的扭曲。但真实赚钱仍要求 PIT-valid 真实账户 snapshot、
长期 Paper、真实成交滑点和费用分布、固定运营成本以及统计下界。

AI 与基线未来必须绑定同一成本 Artifact；AI 不得通过使用更低费率、折扣情景或
不同 PIT 窗口获得表面增量。当前没有批准 AI 模型或配对 AI 成交。

## 最终验证证据

- Paper/account-cost source/PIT/math/schema/replay/CLI tests：12 项，0 失败
- Paper/account-cost + Evaluator Build 聚焦 tests：21 项，0 失败
- 全量 tests：404 项，0 失败
- Python compileall：PASS
- Golden Vector：41 项
- Evaluator build input：95 个冻结文件
- Evaluator build input tree：
  `3b4b42adeca5bf602b0b2bf9fdb7f6560ebdc1c7b254d9b5fd6aec056c571e03`
- Evaluator build：
  `3720bdd63df8ee7cb94b55b640ca305d44d6863b84b0c99be80d97c50d7bdd52`
- release/governance/schema/build validators：执行成功；Release Policy 仍按
  设计返回 `DESIGN_BASELINE` / `PRODUCTION_ACTIVATION_DISABLED`
- 真实 Paper/account-cost binding：未运行，失败关闭
