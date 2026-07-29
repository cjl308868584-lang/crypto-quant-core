# v0.40 Challenger 经济结果发布 CLI 实施计划

1. 在首个合格退出槽前提交冻结设计。
2. 实现只接受信任路径的 CLI，不暴露经济或市场覆盖参数。
3. 使用 v0.36 loader、v0.39 archive loader 和 v0.38 evaluator/publisher/loader。
4. 自动派生最大 archive retrieved time、result id 和 result filename。
5. 覆盖成功、重复幂等、archive 缺失、plan/receipt/权限/路径冲突与参数面测试。
6. 明确测试期间网络、Runner、Broker、order 和 strategy state 操作为 0。
7. 更新 README、ADR、实施状态、版本与 evaluator build manifest。
8. 全量测试通过后发布 `v0.40.0`；不得在本版本生成真实 episode result。
