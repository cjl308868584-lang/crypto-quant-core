# v0.26 历史研究语料实施计划

## 目标

实现冻结的 42 月公开归档研究语料计划、可恢复批量摄取和覆盖证明，为
下一步低维 Logistic AI Candidate 提供数据基础，同时保持
`ARCHIVE_REPLAY_ONLY` 失败关闭。

## 工作项

1. 扩展历史归档边界
   - 月度 Spot Kline；
   - 月度 USDⓈ-M Mark Price Kline；
   - 月度完整覆盖算法；
   - Schema 镜像和兼容测试。

2. 实现 corpus plan
   - 42 个完整 UTC 月；
   - 四条固定数据流；
   - 8 个季度滚动 OOS fold；
   - 168 个稳定 item 和请求根哈希；
   - 完整语义重放验证。

3. 实现可恢复 corpus state
   - SQLite WAL/FULL；
   - 15 分钟租约；
   - append-only 事件链；
   - exact snapshot bytes；
   - 成功恢复零网络；
   - tamper 和输出路径绑定。

4. 实现覆盖 snapshot 与 CLI
   - 逐流/月覆盖矩阵；
   - 缺口、失败、attestation anchoring 状态；
   - owner-only 原子发布；
   - 公开 GET-only 生产入口；
   - 无 URL/凭据/任意命令参数。

5. 发布与验证
   - 两份新 Schema 及 package mirror；
   - compact not-run/plan evidence；
   - ADR、实施追踪、README；
   - Evaluator build 版本和 input manifest；
   - focused、兼容、Golden 和全量测试；
   - 提交、快进合并 `main`、标签 `v0.26.0`。

## 明确不做

- 不下载并提交 42 月原始数据到 Git；
- 不训练 Logistic/XGBoost；
- 不生成或激活 ModelBundle；
- 不将 archive fold 标记为 PIT-valid OOS；
- 不接入账户、Broker、真实订单或资金。
