# v0.28 因果 Logistic 研究实施计划

1. 冻结设计
   - 审计 AI 治理、LabelPolicy、SplitPolicy 与 v0.27 repair 边界；
   - 固定 LONG-only episode、9 特征、1m 保守 fill、成本和 Logistic 配方；
   - 创建 `codex/v0.28-causal-logistic-research` 分支并提交设计。

2. 实现 execution sidecar
   - 新增 compact 1m source Schema 与 package mirror；
   - 验证官方 checksum、ZIP、整月分钟覆盖和 selected raw rows；
   - owner-only 原子发布、冲突拒绝、离线重放和恢复测试；
   - 在仓库外完成 42 个月官方 execution source。

3. 实现 feature/label dataset
   - 合并 v0.27 月度基底与显式 Mark daily repairs；
   - 生成非重叠 LONG episode；
   - 计算固定顺序特征和 1m 保守成本后标签；
   - 实现因果、prefix、warm-up、hash 与 schema 语义重建。

4. 实现 Logistic archive research
   - 实现 fit-only 标准化、固定 L2 Logistic 与 calibration-only Platt；
   - 执行 8 个季度 rolling OOS；
   - 生成 fold model、prediction 与 compact aggregate evidence；
   - 结果永久标记 exploratory/non-PIT/non-profit。

5. 发布 v0.28.0
   - 新增 ADR、实施追踪、README、build manifest；
   - 运行 focused/full tests、compile、schema mirror、敏感信息和差异检查；
   - 提交、快进合并 main、打 `v0.28.0` 标签；
   - 若 GitHub remote 与 `gh` 就绪则推送，否则保留明确 blocker。
