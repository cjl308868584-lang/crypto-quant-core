# v0.34 Challenger 首槽观察 Receipt 实施计划

1. 冻结首槽、deadline、派生路径与零副作用权限边界。
2. 实现只读 SQLite replay、bundle/log/launchctl 交叉验证。
3. 实现严格 receipt Schema、自哈希、语义复核与 owner-only 发布。
4. 覆盖等待、pending、missed、成功、篡改、并发 sidecar 与 CLI 边界。
5. 保存首槽前真实状态证据，更新 ADR、README、版本与 Evaluator build。
6. 运行 focused/full validation，提交、合并并标记 `v0.34.0`。
7. 首槽触发后执行真实 observer；不把工具就绪伪装成首槽成功。
