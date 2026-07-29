# v0.39 Challenger Episode 官方日档获取实施计划

1. 在首个合格退出槽前提交冻结设计。
2. 新增 strict archive receipt Schema 的 config/package 镜像。
3. 实现 completed-receipt/date/time gate，提前调用保证 0 请求。
4. 实现 allowlisted ZIP/checksum 获取、404 pending 和完整 1440 行验证。
5. 实现 owner-only exact publish、幂等恢复与 offline loader。
6. 实现只接受信任路径、不接受 URL/date/price/fee 的 CLI。
7. 用 fixture 覆盖 early、zip/checksum pending、success、retry、cross-day partial、
   checksum/coverage/权限/冲突失败及请求计数。
8. 更新 README、ADR、实施状态、版本与 evaluator build manifest。
9. 全量测试通过后发布 `v0.39.0`；不得在本版本获取真实 outcome archive。
