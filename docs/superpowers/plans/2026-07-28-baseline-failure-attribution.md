# v0.29 基线失败归因实施计划

1. 冻结设计
   - 固定输入数据集、归因维度、统计量和边界；
   - 预注册唯一成本预算 + 正动量 challenger；
   - 明确已看 archive 与未来 prequential 数据隔离。

2. 实现归因 Artifact
   - 新增 Schema 与 package mirror；
   - 实现确定性分组、经济分解、贡献集中度和自哈希；
   - 实现 semantic rebuild、owner-only 发布与加载。

3. 测试
   - 覆盖固定分组、费用翻转、贡献集中度和 fold 边界；
   - 覆盖重排、篡改、未知字段与 challenger 改写；
   - 覆盖 100 次确定性和 Schema mirror。

4. 真实归因
   - 从 owner-only v0.28 causal dataset 生成 compact Artifact；
   - 独立进程离线重建；
   - 记录真实结论，不运行 challenger 历史收益。

5. 发布 v0.29.0
   - 新增 ADR、实施追踪、README 与 build manifest；
   - 运行 focused/full tests、compile、JSON、mirror 与 diff 检查；
   - 提交、快进合并 main、标记 `v0.29.0`；
   - GitHub 仍需 `gh` 与 `origin`，不猜测远端。
