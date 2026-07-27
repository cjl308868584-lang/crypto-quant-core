# v0.30 Challenger 前向记录器实施计划

1. 冻结策略、时间、状态机、SQLite 与快照边界。
2. 实现 21 根闭合 4h Kline 验证和固定入场/退出状态机。
3. 实现连续槽位 append-only WAL、幂等、冲突和重放。
4. 实现 prequential snapshot Schema、self-hash 与 semantic replay。
5. 覆盖确定性、拒绝不消费窗口、持有、退出、漏槽、迟到和篡改测试。
6. 保存 no-decision compact evidence，更新 ADR、README、版本与 build。
7. 运行 focused/full validation，提交、合并、标记 `v0.30.0`。
