# v0.38 Challenger Episode 经济结果评估器实施计划

1. 在首个合格退出槽以前提交并冻结设计。
2. 新增 strict result Schema 的 config/package 镜像。
3. 实现纯离线 plan/receipt/archive 验证、exact-row 提取与 Decimal 经济计算。
4. 实现 deterministic reasons、exact publisher 与 loader。
5. 用合成完整日档覆盖同日、跨日、正负结果、rounding、checksum、缺行、时间、
   receipt、plan 与协调篡改失败路径。
6. 明确验证测试期间 market/Broker/order/state/Runner 计数均为 0。
7. 更新 README、ADR、实施状态、版本与 evaluator build manifest。
8. 全量测试通过后发布 `v0.38.0`；本版本不得获取真实日档或生成真实 result。
