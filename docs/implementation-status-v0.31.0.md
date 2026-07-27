# 实施追踪 v0.31.0

日期：2026-07-28

状态：实时只读 Runner 完成；首槽尚未发生；未执行真实网络请求

## 本版本完成

- 复用三样本 Binance server-time probe 打开同一 monotonic 可信时钟门；
- 从 state 推导唯一 next required slot，不接受调用方时间覆盖；
- 固定一个 ETHUSDT Spot 4h/21 Kline 公共 GET，endTime 只能是 slot-1ms；
- `NOT_DUE` 和 `MISSED_SLOT` 路径均不发送行情请求；
- 严格验证 raw 12 列 Kline、4h 连续性、OHLC、完整窗口和闭合边界；
- 下一槽重叠 20 根 raw row 必须逐条不变，并沿用首次 availability；
- 新增包含完整 time probe、HTTP receipt/raw body、Kline 和 candidate decision
  的 owner-only source bundle；
- source bundle 先持久化，decision 后追加，避免无来源 decision；
- 新增只接受 state/output 路径的 CLI；
- 禁用环境代理、自动重试和 redirect，保持零凭据、零 Broker、零下单。

## 固定请求

每次 due run 的物理请求数固定为：

- Binance server time：3；
- Binance Spot Kline：1；
- credential/account/balance/order：0。

Kline URL 的 path、query names 和固定值不可覆盖；只有 `endTime` 按下一必需
slot 确定性派生。

## 真实状态

版本证据记录于 `2026-07-27T22:02:51.000Z`，仍早于
`2026-07-29T00:00:00.000Z` 注册首槽。因此没有运行真实网络 smoke：

- server-time requests：0；
- Kline requests：0；
- source bundles：0；
- decisions：0；
- outcomes/profitability claims：0；
- OS scheduler：未安装。

完整紧凑证据见
[binance-challenger-live-runner-not-run-v0.31.0.json](../artifacts/challenger-forward/binance-challenger-live-runner-not-run-v0.31.0.json)。

## 验证

- v0.31 focused tests：11/11；
- 固定 fixture 100 次 decision/source bundle exact match；
- due 路径 3+1 请求、同槽重试 3+0、早到/漏槽 3+0；
- Kline 修订、gap、未闭合、bad status/time 全部失败关闭；
- Schema 与 package mirror exact；
- 全量 tests：510/510；
- Golden Vector：41；
- Evaluator build input：146；
- Build input tree hash：
  `da9b1c05bc963778097633dc1f2e3f42f04b0e66f1f35523ca895dc1c60e868a`；
- Evaluator build hash：
  `febd0dbfa6de1fe088a394d7a47b03b2875b50377a0286534453742f0f1bad79`；
- `make validate` 完整执行成功；政策结果继续按设计为 `FAIL`，因为正式绑定
  未提供且生产激活关闭。

## 赚钱含义

Runner 让未来策略信号具备更强的来源与时间证据，但没有产生策略收益。Binance
server-time receipt 可以校正本机时钟，却不是独立第三方 publication；在补充
外部时间锚、观察未来结果、冻结实际成本并通过统计门以前，任何赚钱结论都不成立。

下一步是在首槽前生成并审查无凭据 LaunchAgent 合同；安装、加载和首次真实运行
必须分别保存 receipt。若首槽错过，不允许回填。
