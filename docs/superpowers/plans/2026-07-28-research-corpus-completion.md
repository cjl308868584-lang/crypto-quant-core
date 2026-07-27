# v0.27 研究语料完成实施计划

1. 发布 `BINANCE_CSV_V2`
   - 官方月度表头；
   - Funding ±1 秒调度抖动；
   - V1 snapshot 兼容；
   - fixture 与真实格式测试。

2. 完成基础 corpus
   - 仓库外 owner-only 目录；
   - 168/168 source snapshots；
   - 记录 2 个 degraded monthly Mark gap；
   - completed rerun 零网络。

3. 实现 daily repair
   - repair bundle Schema；
   - base/patch scope、hash、attestation 和 exact missing-set 重放；
   - combined month coverage；
   - owner-only patch 发布；
   - tamper/overlap/missing/extra patch 测试。

4. 发布 v0.27
   - compact completion evidence；
   - ADR、实施状态、README；
   - package/build manifest 版本；
   - focused、Golden、全量测试；
   - 提交、快进合并 main、标签 `v0.27.0`。
