# 实施追踪 v0.40.0

日期：2026-07-29

状态：首个 Challenger episode 经济结果 CLI 已在 outcome 前冻结

## 本版本完成

- 在首个合格退出槽位前提交冻结设计 `7769185`；
- 新增只接受七个可信绝对路径的离线结果 CLI；
- exact plan bytes 与 completion receipt bytes 分别计算文件 SHA-256；
- completion receipt 必须先经 v0.36 loader 复核；
- archives 必须由 v0.39 loader 完整重放；
- `evaluated_at` 自动取 archive receipts 的最大 `retrieved_at`；
- result id、文件名、价格、数量、费用、收益与标签均不可人工覆盖；
- 使用 v0.38 evaluator 构建、exact publish 并立即 loader 重载；
- owner-only 0700/0600 输出，同一输入重试保持相同路径与 exact bytes；
- 没有观察真实 exit、获取真实 archive 或生成真实 economic result。

## 验证

- result CLI focused tests：7/7；
- CLI、evaluator 与 archive acquisition 相邻测试：24/24；
- 全量 tests：576/576；
- Golden Vector：41；
- Evaluator build input：179；
- Build input tree hash：
  `f4200992e1c34b636b48509d0697f678f56873044ca3fe8b786443ca7c36273b`；
- Evaluator build hash：
  `399c9c408aac3c4702cde1fa3bc08dbf0339ef0c112fd3ce9e7a7720c696ad8c`；
- `make validate`：完成；生产门禁保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 安全边界

- CLI 没有 market transport，市场请求为 0；
- Runner、Broker、余额读取、订单提交与 strategy state write 为 0；
- 不接受 URL、日期、symbol、执行分钟或任何经济覆盖参数；
- archive 原始 bytes 继续只保存在仓库外；
- 本版本的所有成功结果均来自合成 fixture。

## 仍未证明

- 首个 episode 尚未完成只读验收；
- 对应 Binance DAILY archive 尚未真实获取；
- 仓库没有真实 economic result、真实 fill 或实际账户 fee；
- 单 episode 不能证明可重复净优势；
- AI 臂仍无获批模型和配对前向证据；
- 系统仍无 Broker、余额读取或下单能力。

## 下一步

北京时间 2026-07-29 16:10 后先使用 v0.36 observer 只读验收。若 complete，等待
v0.39 时间门并只获取所需官方日档；全部 verified 后才运行 v0.40 CLI。真实 result
必须作为新的独立版本封存。任何 failure、missed slot、404、checksum、覆盖或权限
错误都保持 pending/failed，禁止回填。
