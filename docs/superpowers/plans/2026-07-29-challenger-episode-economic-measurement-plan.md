# v0.37 Challenger Episode 经济测量计划实施计划

1. 从 tag `v0.36.0` 建立独立分支，并在首个可退出槽位前提交冻结设计。
2. 新增 strict economic measurement plan Schema 的 config/package 镜像。
3. 实现纯离线、确定性的 plan builder、semantic validator、publisher 和 loader。
4. 从 v0.35 committed first-slot receipt 推导并锁定 entry execution minute
   `2026-07-29T00:03:00.000Z`。
5. 冻结官方 DAILY 1m archive、checksum、next-minute high/low、tick/step、双边
   slippage/fee 和 Decimal 计算顺序。
6. 测试 recorded_at 边界、时间覆盖、receipt 篡改、policy/公式篡改、binary
   float、Schema 镜像、canonical publication 和 idempotency。
7. 生成真实 `WAITING_FIRST_EPISODE_COMPLETION_AND_DAILY_ARCHIVE` artifact，不
   获取市场数据、不填 exit、不计算 PnL。
8. 更新 README、ADR、实施追踪、package/evaluator 版本和 build manifest。
9. 运行 focused、相邻、全量测试及 `make validate`。
10. 核验私有仓库、origin 和 ADMIN 权限后提交、推送、PR、快进合并 main，标记
    `v0.37.0`。
11. 更新北京时间 16:10 的后续只读任务：episode complete receipt 仍由 v0.36
    observer 生成，经济来源与结果必须继续服从 v0.37 plan。
