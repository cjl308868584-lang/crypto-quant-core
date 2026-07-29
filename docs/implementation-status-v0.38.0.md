# 实施追踪 v0.38.0

日期：2026-07-29

状态：首个 Challenger episode 经济评估器已在 outcome 前冻结并可执行

## 本版本完成

- 在首个合格退出槽位前提交冻结设计 `17c7348`；
- 新增 strict economic result Schema 的 config/package 镜像；
- 新增纯离线 plan、completion receipt 与 DAILY archive 输入信任链；
- 对官方 checksum、唯一 CSV、microsecond 时间、连续 1440 行和 exact row
  执行失败关闭验证；
- 同日只接受一个日档，跨日只接受两个由 execution minute 派生的日档；
- 实现 50 位 Decimal、三处固定舍入与完整成本/PnL/return 分解；
- 实现 deterministic semantic replay、exact publisher 和 secure loader；
- 不含 HTTP transport，不接受 URL、价格、时间或费用覆盖；
- 没有观察真实 exit，没有获取真实 archive，没有生成或发布真实 result。

## 验证

- economic evaluator focused tests：8/8；
- 相邻 plan、episode receipt、first-slot、execution source 与 causal tests：47/47；
- 全量 tests：560/560；
- Golden Vector：41；
- Evaluator build input：174；
- Build input tree hash：
  `1f2b6e94d69557942d85ab7c942fbd29a3cc0dd8bca0f0ebebceecf58981a5a4`；
- Evaluator build hash：
  `a8a2464d83f2b1ec5cd6a5c884262b5163a2f3eb82e38998d1e6e7a8cc74e11b`；
- `make validate`：完成；生产门禁保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 仍未证明

- 首个 episode 尚未完成只读验收；
- 对应官方 DAILY 1m archive 尚未获取；
- 仓库没有真实 economic result、真实 fill 或实际账户 fee；
- 单 episode 无论正负都不能证明可重复净优势；
- AI 臂仍无获批模型、配对前向 episode 或可发布增量证据；
- 系统仍无 Broker、余额读取或下单能力。

## 下一步

北京时间 2026-07-29 16:10 后先按 v0.36 observer 只读验收：

- complete：封存 exact receipt；官方 DAILY 档案未可用时继续 pending；
- archive available：只使用 exact bytes 和 v0.38 评估器生成研究代理；
- in progress：等待下一预注册槽位，不发布完成或经济证据；
- failure/missed：转入失败取证，禁止回填。

真实 result 应作为独立后续版本发布，不能修改 v0.37 plan 或 v0.38 evaluator。
