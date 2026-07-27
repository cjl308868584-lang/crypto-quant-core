# ADR-0024：上下文完整的 4h Paper 侧车

状态：Accepted

日期：2026-07-28

## 背景

v0.19/v0.20 已冻结 4h Paper scheduler、append-only WAL 和 PREPARED run blob；
v0.23 又能把账户费率绑定到 Paper 经济结果。但旧 scheduler 的成功槽位不包含
永续上下文，也不能证明真实账户成本。直接修改旧 PREPARED blob 会破坏已有崩溃
恢复证据。

## 决策

v0.24 保留旧 Paper run 和 scheduler 不变，新增独立的 context sidecar：

1. 消费同一 scheduled Paper run 的 `paper-account-cost-binding-v1`；
2. 消费同槽位、与决策时间相差不超过 15 分钟的
   `perpetual-context-snapshot-v1`；
3. 验证 cost binding、原 Paper、账户 commission、perpetual 四个外部
   attestation；
4. 形成 `paper-cycle-context-bundle-v1`；
5. 通过独立 append-only SQLite WAL 先 PREPARE 精确 bytes，再不可变发布；
6. 形成独立 `paper-context-schedule-snapshot-v1`。

Paper decision、run end、perpetual source/recorded time 和 bundle created time 必须
位于同一活动槽位。Perpetual 位于决策前时标记为
`PRE_DECISION_AVAILABLE_NOT_CONSUMED`，位于决策后时标记为
`POST_DECISION_OBSERVATIONAL_NOT_SIGNAL`。当前基线均不消费这些字段，禁止改写
已冻结信号。

## 崩溃恢复和计数

侧车事件只有 `CONTEXT_CLAIMED/PREPARED/SUCCEEDED/FAILED`。PREPARED blob
绑定 Artifact bytes、SHA-256、bundle/trust hash、全部源 attestation 和输出
根。事件与 blob 禁止 update/delete。

PREPARED 后或发布后崩溃时，租约到期后的 worker 只读取 WAL 中原 bytes：

- source read：0；
- network request：0；
- 不重新构建 bundle；
- 不更换输出根；
- 已发布同 bytes 直接采用。

90 天统计只计算 sidecar `SUCCEEDED`，旧 Paper `SUCCEEDED` 不继承为上下文完整。
首尾槽位之间缺失的 sidecar 被计入 unobserved，连续性失败。

## 安全与资格

bundle 不把 Funding 场景写入 realized PnL，不授权 SHORT，不读取余额，不下单，
不让永续字段改变当前 baseline。bundle、schedule snapshot、SQLite/WAL/SHM
均按 mode-0600 保护。

- `cycle_eligibility=CONTEXT_COMPLETE_RESEARCH_ONLY`
- `scheduler_eligibility=CONTEXT_SIDECAR_OPERATIONAL_RESEARCH_ONLY`
- `paper_eligibility=LONGITUDINAL_COLLECTION_IN_PROGRESS`
- `production_eligibility=NOT_APPROVED`

仓库仍缺真实账户 snapshot 和成功 Futures snapshot，因此真实侧车未运行；
fixture 只验证逻辑、恢复和篡改拒绝。
