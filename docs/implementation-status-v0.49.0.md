# 实施追踪 v0.49.0

日期：2026-07-31

状态：证据维护协调器已实现；真实 cohort 仍在收集

## 本版本完成

- 以独立提交 `0b1851f` 冻结 v0.49 详细设计；
- 固定串联 v0.45 receipt、v0.46 shared archive、v0.47 result/index；
- 同次维护只读取一个 UTC 观察时点；
- receipt 失败时不进入 archive，archive 未 complete 时不进入 result；
- 无 completed Episode 时保持零 archive 请求且不创建 archive/result 根；
- 验证阶段状态、集合计数与全部安全计数，未知或矛盾摘要失败关闭；
- CLI 只暴露冻结计划、信任根和三个 owner-only 输出根；
- 不新增维护 artifact，不调用 v0.48，不形成提前盈利判断。

## 固定安全边界

- Runner/kickstart/bootstrap：禁止；
- Broker/order/credential/runtime strategy state write：禁止；
- 新实时市场请求：禁止；
- 官方日档只能由 v0.46 allowlist 在既有时间门后请求；
- 404、未到时间门和日档不完整均保持 pending；
- Episode、日期、URL、symbol、价格、费用、资本、PnL、label、阶段与重试不可
  由 CLI 覆盖。

## 验证

- v0.49 聚焦 tests：12/12；
- v0.45–v0.49 相邻回归：71/71；
- 全量 tests：666/666；
- Golden Vector：41；
- Evaluator build input：209；
- evaluator build 版本：`1.44.0`；
- Build input tree hash：
  `bb4521eb8e2a8608402e9ccb8a0e94ae42ca8fa80740b8d19eb5f449eb530858`；
- Evaluator build hash：
  `22d9eb55bd5e4a34cfa81e7675864cfbdc41aad0a6da33f699303b9476f0926a`；
- Python compileall：完成；
- `make validate`：完成；生产门继续保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 真实运行状态

北京时间 2026-07-31 使用 v2 冻结 install receipt、contract、plist 与固定
cohort receipt/archive/result 根执行真实 v0.49 CLI，观察时点为
`2026-07-30T18:35:06.933Z`，返回
`COHORT_EVIDENCE_NO_COMPLETED_EPISODES`：已验证 cohort 槽 2、
completed Episode 0、receipt 创建 0、required/verified day `0/0`、archive
网络请求 0，result 阶段未执行。三个 cohort 输出根调用前后均不存在。

runtime state/stdout/stderr SHA-256 调用前后分别保持：

- `4332717a4822b948defd1ea38e22b3a53ee3ca54ed460a9d16b61d436b15d44c`；
- `c17c05dc18072417efcbba3b7d2d6ff912a0bbd38e9ee86aadef296ea8b61f43`；
- `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

Broker/order/strategy-state-write/Runner 均为 0。

## 下一步

继续让 LaunchAgent 自然收集，不触发 Runner、不补槽。定期执行 v0.49 维护；
固定 tail end 前不得执行累计盈利门或形成提前 PASS，tail end 后才运行 v0.48
final。即使研究门通过，也仍需独立 sealed OOS、真实账户成本、Paper、对账、故障
恢复、资本和合规门。
