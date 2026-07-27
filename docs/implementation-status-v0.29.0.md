# 实施追踪 v0.29.0

日期：2026-07-28

状态：失败归因完成；v1 拒绝；forward-only challenger 已预注册但未评估

## 本版本完成

- 新增基线失败归因 Schema、确定性构建器、自哈希、语义重建、owner-only
  发布与加载；
- 在真实运行前冻结全部分组边界和统计量；
- 分离保守成交代理 gross PnL、entry/exit fee 与 net PnL；
- 固定报告 fold、退出原因、持有时间、SMA 距离、动量、波动与区间比例；
- 报告 fee flip、Top-1/Top-5 正贡献集中度和删除后结果；
- 预注册唯一简单 challenger，不运行历史收益、不训练 AI。

## 真实归因

- 全部事件：780 个，gross `-1292.32171 USDT`，fee
  `2337.76291479 USDT`，net `-3630.08462479 USDT`；
- pooled archive OOS：419 个，gross `-957.969754 USDT`，fee
  `1255.381334241 USDT`，net `-2213.351088241 USDT`；
- 203 个 SMA early-exit：0 个成本后正收益，net
  `-5151.7275681525 USDT`；
- 216 个 vertical 24h exit：142 个正收益，net
  `+2938.3764799115 USDT`；
- pooled OOS 删除 Top-5 正贡献后净收益率和：
  `-2.794711014398`；
- 结论：毛边际已经为负，费用不是唯一根因；退出路径值得下一轮研究，但不能
  根据本次已看结果直接改规则并宣称成功。

完整紧凑证据见
[binance-baseline-failure-attribution-v0.29.0.json](../artifacts/baseline-research/binance-baseline-failure-attribution-v0.29.0.json)。

## 已注册但未运行

`SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2` 固定要求：

- SMA20 distance `>= 0.005`；
- 5-bar ETH log return `> 0`；
- 其余退出、成本和执行代理保持不变；
- 必须从完整事件流重新生成 episode；
- 最早 forward 起点 `2026-07-29T00:00:00.000Z`；
- 当前状态 `NOT_RUN_PREREGISTERED_FORWARD_ONLY`。

## 验证

- fixture 100 次确定性重建 exact match；
- 真实 780 事件归因 100 次重建 exact match；
- 独立新进程禁网重建：网络调用 0、语义原因 0、权限异常 0；
- focused tests：6/6；
- Schema 与 package mirror exact；
- 全量 tests：491/491；
- Golden Vector：41；
- Evaluator build input：137；
- `make validate` 完整执行成功；政策结果继续按设计为 `FAIL`，因为正式绑定
  未提供且生产激活关闭。

- Build input tree hash：
  `a02be71b52a77e8c157e5eb3ebf4132af9b77bd39eb2b58a90f75b7f49d08d84`；
- Evaluator build hash：
  `6905f843cab9e6b05d830bb9ebc3663a7f7597966bed440c50f7d83e484a315f`。

## 赚钱含义

本版本没有找到赚钱策略；它排除了“亏损主要只是手续费”的错误解释。更便宜
的费率只能减小亏损，不能把负 gross edge 自动变正。

下一步只允许两条正当路径：按预注册规则积累真实前向 challenger 证据，或把
退出路径作为新的经济假设另行预注册。不能从本次最有利分组反向挑参数。
