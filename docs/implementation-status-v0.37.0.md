# 实施追踪 v0.37.0

日期：2026-07-29

状态：首个 Challenger episode 经济测量已在 outcome 前预注册

## 本版本完成

- 在首个可退出槽位前提交冻结设计 `dd3ab06`；
- 新增 strict economic plan Schema 的 config/package 镜像；
- 新增纯离线 deterministic builder、semantic validator、publisher 和 loader；
- 从 v0.35 exact receipt 推导 entry recorded time 和 execution minute；
- 冻结 Binance 官方 DAILY 1m archive + checksum 唯一来源；
- 冻结 high/low 保守成交、tick/step、双边 slippage/fee 和 Decimal 计算顺序；
- 拒绝 receipt/file hash、时间、公式、费用、authority 和 Schema 篡改；
- 发布不含 outcome 的真实 waiting plan artifact；
- plan 构建过程市场、Broker、订单和 state 写入均为 0。

## 真实 Plan

- registered at：`2026-07-29T02:15:24.000Z`；
- entry recorded at：`2026-07-29T00:02:06.752Z`；
- entry execution minute：`2026-07-29T00:03:00.000Z`；
- policy hash：
  `32c81160e936caf4253e0eabe46104fde5f6b747e0525fa2ea916c028dea82f9`；
- plan id：
  `challenger_episode_economic_plan_e5c86696889d209373ce536ee0f54be72e59d7de96b6868cd5ab0358491985a4`；
- plan hash：
  `fa43e1bb24ac0e9d70c82a3d09f03ca43a5f99c429f43e6c67d6e68029732831`；
- file SHA-256：
  `f22cb582a7df38e14220fca75359f6290af2fdb5896e5829ba5d7fd805cf54da`；
- status：
  `PREREGISTERED_WAITING_FIRST_EPISODE_COMPLETION_AND_DAILY_ARCHIVE`。

Plan artifact：
[challenger-episode-economic-plan-v0.37.0.json](../artifacts/challenger-forward/challenger-episode-economic-plan-v0.37.0.json)。

## 验证

- economic plan focused tests：7/7；
- 相邻 episode、causal label 与 Offline Paper 回归：38/38；
- 全量 tests：552/552；
- Golden Vector：41；
- Evaluator build input：171；
- Build input tree hash：
  `92a277e53b7065e7367a158cc937cf9e2ae213f445e7673182eb83ad910f2256`；
- Evaluator build hash：
  `041320e3f3fbe36db8277c1494248080b5274f771cccf0b1e1537d2375e63981`；
- `make validate`：完成；发布门禁保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 仍未证明

- 首个 episode 尚未退出；
- 官方 entry/exit DAILY 1m archive 尚未获取；
- plan 没有任何 exit row、fill、PnL 或 return；
- future outcome source 是研究成交代理，不是实际 fill；
- assumed 15bps fee 不是当前账户真实费率；
- 单 episode 无法证明可重复净优势；
- AI 臂仍无获批模型，系统仍无 Broker、余额读取或下单能力。

## 下一步

北京时间 2026-07-29 16:10 后先按 v0.36 observer 只读验收 episode：

- complete：封存 exact receipt，但等待官方 DAILY 1m archive 可用后才按 v0.37
  plan 获取 source 和计算；
- in progress：继续等待预注册槽位；
- failure/missed：转入失败取证，禁止补写。

经济结果即使为正也只增加一笔研究样本；累计样本与风险统计未通过前不进入 Paper，
不启动 AI 晋级，更不开放真实资金。
