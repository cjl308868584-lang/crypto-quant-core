# 实施追踪 v0.15.0

日期：2026-07-27

状态：已完成并验证

## 本版本完成

- 新增 `PairedRiskEvaluationSnapshot v1`；
- 支持 `AI_VS_RECIPE_BASELINE`；
- 支持 `MINOR_CANDIDATE_VS_ACTIVE_BUNDLE`；
- 从两臂 StatisticalSeries 和精确 EconomicLedgerSnapshot 重放风险段；
- 实现最大回撤相对改善一侧 95% 配对 MBB 下界；
- 实现经验 ES95 相对改善一侧 95% 配对 MBB 下界；
- 所有匹配窗口进入风险路径，未配对窗口失败关闭为 `INCONCLUSIVE`；
- Release GateEvidence 与 Supporting Observation 绑定完整嵌套来源链；
- 六个既有 MDD/ES95 exact metric override 现在解析到可执行 Estimator。

## 可执行覆盖

- Catalog 算法总数：58
- 可执行 Estimator：26
- 明确不可执行并失败关闭：32
- Golden Vector：41

## 最终验证证据

- 全量测试：215 项，0 失败
- Golden report hash：`e3e7dc45865d860489514a574c64ca14a8dd6f089a0b74129414231741882fc3`
- Evaluator build hash：`d15dd8e155a3676ae93d61e81948544b4f4f50b4bc71d85e83b6db072bb27c04`

## 赚钱含义

本版本消除了用点估计、上传标量或错误差值序列证明“风险改善”的路径。
它让风险效率路线可以被可信检验，但仓库仍只有合成 Fixture，没有真实
历史 OOS、Shadow、Paper 或 Canary 经济证据。因此不能据此声称策略已经
赚钱、AI 已优于基线或任何 Bundle 可以实盘晋级。

## 仍然失败关闭

- `RISK_EFFICIENCY` 的配对 leave-out 整组复评；
- DSR/PBO；
- 真实 PIT 历史数据接入与离线 Paper 证据管线；
- Broker、密钥、交易所 Adapter、真实订单和自动部署。

## 下一优先级

1. 建立只读历史数据与成本事实摄取管线；
2. 生成真实 OOS StatisticalSeries/EconomicLedger/PairedRisk Artifact；
3. 完成 RISK_EFFICIENCY leave-out 整组复评；
4. 在任何资金接入前执行 Shadow/Paper 验证。
