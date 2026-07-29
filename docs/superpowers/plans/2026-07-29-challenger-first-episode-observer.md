# v0.36 Challenger 首个 Episode 只读观察器实施计划

1. 从 `v0.35.0` 建立独立分支，并先提交冻结设计，确保早于首个可退出槽位。
2. 新增 first-episode receipt Schema 的 config/package 镜像。
3. 实现只读 observer 和 CLI；信任路径只能由 install receipt 与 contract 推导。
4. 对完整 decision prefix、逐槽唯一 bundle、逐槽唯一日志、state prefix 和
   launchctl 进行交叉验证。
5. 进行中只返回 verified status，不发布 receipt；完整合法退出才发布并可重载。
6. 为正常进行中、两种退出、漏槽、提前/迟延退出、prefix 篡改、重复证据、WAL、
   权限、时钟和 CLI authority 编写失败关闭测试。
7. 使用 v0.35 冻结的四个绝对路径执行真实只读观察，记录当前状态和零权限计数；
   不触发 Runner，不增加市场请求。
8. 更新 README、实施状态、ADR、package 版本、evaluator manifest 和构建测试。
9. 运行 focused、相邻、全量测试与 `make validate`，检查 diff 和 secret。
10. 明确验证目标 GitHub 仓库、origin 和 ADMIN 权限后提交、推送、PR、合并 main，
    标记并推送 `v0.36.0`。
11. v0.36 发布后安排最早合格退出槽位的后续只读验收；pending 不发布完成证据，
    失败不得补写或伪报。
