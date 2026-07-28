# v0.35 Challenger 首槽真实证据发布实施计划

1. 保持 v0.34 LaunchAgent、registration、运行快照和原始现场不变。
2. 北京时间 2026-07-29 08:02 后先只读核验 service、日志、state 和 bundle。
3. 用 v0.34 固定 CLI 执行 observer；pending 不重跑 Runner，成功才发布 receipt。
4. 成功时立即重载 runtime receipt，并证明观察前后 state 与日志 prefix 未变。
5. 将 exact canonical receipt bytes 封存到 Git，补充 ADR、状态、README 与版本。
6. 运行 receipt focused tests、相邻回归、全量测试、构建验证和 diff 检查。
7. 提交、快进合并到 `main` 并标记 `v0.35.0`。
8. 若失败或漏槽，停止成功路径，冻结失败取证设计，禁止回填或伪造 receipt。
9. GitHub 仅在明确代码仓库、`origin` 和认证写权限均验证后推送 main 与全部标签。
