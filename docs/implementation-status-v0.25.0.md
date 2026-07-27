# 实施追踪 v0.25.0

日期：2026-07-28

状态：已完成并验证

## 本版本完成

- 新增一次健康 probe/一个 monotonic clock 的正常完整周期；
- 固定账户 → Paper → 永续 → binding → context 顺序；
- 正常路径物理网络请求固定为 15；
- 新增独立 append-only SQLite WAL 和精确 source blobs；
- 决策前账户 snapshot 在失败/崩溃后只复用、不重采；
- Paper 和 context 继续复用原有独立 scheduler，不修改旧证据；
- 每次恢复重新通过时钟门，并显式记录不同 probe；
- 新增 orchestration snapshot、自哈希、外部 attestation 和完整重放；
- 缺凭据在任何网络前失败；
- 新增非安装型 LaunchAgent renderer 和 companion contract；
- plist/contract/state/source artifacts 使用 owner-only 权限；
- CLI 不开放 URL、proxy、secret value、order、symbol 或 clock override。

## 真实运行边界

仓库没有真实只读 credential 文件，Futures 真实来源也尚未成功，因此没有运行
真实完整周期，没有生成含用户路径的 plist，也没有调用 `launchctl`。冻结证据：
[context-cycle-orchestration-not-run-v0.25.0.json](../artifacts/orchestration/context-cycle-orchestration-not-run-v0.25.0.json)。

fixture 只证明顺序、PIT、请求计数、恢复和篡改拒绝，不进入真实 90 天日历。

## 赚钱与 AI 含义

本版本解决的是“能否可靠收集完整前向证据”，不是“策略是否已经赚钱”。只有
真实编排持续至少 90 天、补入真实成交/滑点并通过预注册统计门后，才可评价简单
基线；AI 仍必须在同一周期 bundle 上以 shadow-only 方式与基线配对。

## 最终验证证据

- v0.25 orchestration/LaunchAgent focused tests：16/16 通过
- v0.25 + evaluator build 定向 tests：25/25 通过
- 相关模块兼容回归：66/66 通过
- 全量 tests：436/436 通过
- Python compileall：通过
- Golden Vector：41/41 通过
- Evaluator build input：112 个文件
- Evaluator build input tree：
  `91fcc38c970f27bf2615b57cf976dd0d2b93366627dbffe65008d41551b6fc46`
- Evaluator build：
  `b320a0ca0ca96e659b2a1a61cd7fd4f275724c6e970f5fa4351c42e70224a34c`
- release/governance/schema/build validators：全部按冻结预期通过；release 保持
  `DESIGN_BASELINE` 失败关闭，governance 保持 `TEMPLATE_UNAPPROVED`
- 真实 context-complete orchestration：未运行，失败关闭
- LaunchAgent installation：未执行，无外部 receipt
