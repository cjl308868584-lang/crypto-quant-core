# v0.33 Challenger LaunchAgent 安装实施计划

1. 冻结当前用户 domain、固定 target、launchctl 命令和回滚边界。
2. 实现 source preflight、原子无覆盖安装和 bootstrap/print 验证。
3. 实现严格安装 receipt、Schema、自哈希、语义重放与 owner-only 发布。
4. 覆盖冲突、幂等、失败回滚、print 绑定和 CLI 命令边界测试。
5. 执行真实用户域安装，核验 service 与 RunAtLoad 日志。
6. 保存真实紧凑证据，更新 ADR、README、版本与 Evaluator build。
7. 运行 focused/full validation，提交、合并并标记 `v0.33.0`。
