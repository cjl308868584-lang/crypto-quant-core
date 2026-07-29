# 实施追踪 v0.36.0

日期：2026-07-29

状态：首个 Challenger episode 观察规则已事前冻结，真实 episode 仍在进行

## 本版本完成

- 在首个可退出槽位前独立提交冻结设计 `1878c00`；
- 新增 first-episode receipt Schema 的 config/package 镜像；
- 新增只读 observer、四参数 CLI 和不可变 receipt loader；
- 验证完整 decision prefix、逐槽唯一 source bundle、逐槽唯一 stdout
  `RECORDED`、state prefix 和当前 LaunchAgent；
- 区分进行中、SMA 完成、24h 垂直完成、漏槽和失败状态；
- 进行中不发布 receipt，完成 receipt 允许现场追加但拒绝已绑定前缀变化；
- 增加 deadline、重复证据、权限边界、receipt 篡改和 CLI authority 回归；
- 使用真实 runtime 完成零网络、零 Broker、零订单、零 state 写入观察；
- 将真实进行中结果冻结为 Git artifact。

## 真实观察

- observed at：`2026-07-29T01:17:00.579Z`；
- status：`FIRST_EPISODE_IN_PROGRESS_VERIFIED`；
- episode id：
  `challenger_episode_45c86b2c0c1610d890c2d956915803c4b375b2838a66215f3f87311c8342be91`；
- decision count：1；
- entry / last slot：`2026-07-29T00:00:00.000Z`；
- next slot：`2026-07-29T04:00:00.000Z`；
- minimum hold：`2026-07-29T08:00:00.000Z`；
- vertical exit：`2026-07-30T00:00:00.000Z`；
- LaunchAgent runs / last exit：`6 / 0`；
- observer launchctl/network/state-write/Broker/order：`1/0/0/0/0`；
- completion receipt published：false。

观察前后 state/stdout/stderr 的 stat 与 SHA-256 完全一致。进行中证据：
[challenger-first-episode-in-progress-v0.36.0.json](../artifacts/challenger-forward/challenger-first-episode-in-progress-v0.36.0.json)。

## 验证

- first-episode focused tests：9/9；
- 首槽 observer、Runner、状态机相邻回归：28/28；
- 全量 tests：545/545；
- Golden Vector：41；
- Evaluator build input：167；
- Build input tree hash：
  `f701ea320d6d4080fda98c971190689fb5636dcb4716f65d48c9b200f40d7b29`；
- Evaluator build hash：
  `6bc20e64e3c563836f38a02565c905b528cfdafd909d5f80803ddc483f33f7f1`；
- `make validate`：完成；发布门禁保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 仍未证明

- 首个 episode 尚未自然退出；
- 没有冻结的可成交 entry/exit、账户手续费、实际滑点和仓位规模；
- 单个 episode 无法建立收益分布或下置信界；
- 没有连续 90 天 Paper、真实成交或生产资格；
- Binance server time 不是独立第三方时间锚；
- AI 臂仍无获批模型，不能声称优于简单基线；
- 系统仍无 Broker、余额读取或真实下单能力。

## 下一步

保持 LaunchAgent、registration、策略和 state 不变。北京时间 2026-07-29 16:10
后首次使用冻结的 v0.36 observer 只读复核：

- 若 episode 已合法退出，封存 exact runtime receipt 并发布后续证据版本；
- 若仍为 LONG，保持 pending，继续等预注册槽位；
- 若漏槽或证据不一致，转入失败取证，禁止补写、重跑或伪报完成。

完整 episode 之后仍不能直接宣称赚钱；下一阶段必须先冻结成交与全成本计算，再累计
足够多的前向 episodes，以净收益、回撤、尾部风险和下置信界决定是否进入 Paper。
