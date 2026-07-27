# v0.28 因果特征、保守标签与 Logistic 研究基准设计

日期：2026-07-28

## 1. 目标与边界

v0.28 把 v0.27 的完整 archive corpus 转换为第一个可重放的 LONG-only
Meta 研究数据集，并训练固定配方的低维 Logistic 基准。目标是回答：

> 在简单 ETH Spot LONG 基线产生可执行新开仓 Proposal 时，严格滞后的市场
> 状态能否过滤掉一部分扣除保守执行成本后为负的 24h 交易？

本版本是 `ARCHIVE_RESEARCH_ONLY`：

- 不把 2026 年获取的历史归档冒充 contemporaneous PIT 数据；
- 不运行 XGBoost、Quantile、自动特征搜索或超参数搜索；
- 不创建可批准、可部署的 ModelBundle；
- 不连接账户、Broker、余额或订单接口；
- 不声称 AI 优于基线或策略赚钱。

## 2. 为什么不能直接用 4h 收盘生成标签

当前 4h corpus 可以生成因果特征，但无法证明下一可交易事件的成交价格。
若使用信号 K 线收盘价或下一根 4h 收盘价成交，会产生同 K 线成交或 4h
窗口内择价偏差。

因此新增独立 ETHUSDT Spot 1m execution sidecar：

- 时间范围仍为 `2023-01` 至 `2026-06`；
- 每月只访问官方 monthly ZIP 与 `.CHECKSUM`，共 84 个无凭据 GET；
- ZIP/checksum exact bytes 保存在仓库外 owner-only 目录；
- compact snapshot 验证整月每一分钟连续性，但只固化实际 entry/exit 所需
  1m 原始行；
- Git 只保存 compact completion/research evidence，不保存月度 ZIP。

## 3. 基础 Proposal 与持仓路径

方向仅为 `LONG`，复用
`SPOT_LONG_SMA20_VOL12_BUCKET25_V1` 的核心信号：

- 决策发生在 ETH Spot 4h Kline 完整收盘之后；
- `latest_close > prior_20_sma` 且当前为 FLAT 时创建开仓 Proposal；
- Proposal 生效后至少持有 8 小时；
- 8 小时后，若 `latest_close <= prior_20_sma`，在下一分钟退出；
- 否则在开仓决策后 24 小时垂直退出；
- 退出决策时不允许同槽位重新开仓，最早在下一根 4h 收盘后产生新 Proposal；
- episode 互不重叠，避免把持仓中的重复 LONG 信号当作独立满仓交易。

SHORT 在本版本固定为 `NOT_RUN_NO_BASELINE_EXECUTION_POLICY`，不得由 LONG
结果外推。

## 4. 冻结特征

特征只读取 `event_time <= decision_time` 的归档事实，顺序固定为：

1. `eth_log_return_5`
2. `eth_sma20_distance`
3. `eth_annualized_volatility_20`
4. `eth_mean_range_ratio_6`
5. `eth_taker_buy_quote_ratio_6`
6. `btc_log_return_5`
7. `btc_sma20_distance`
8. `eth_mark_basis`
9. `eth_latest_funding_rate`

约束：

- 所有窗口都含当前已关闭 4h bar，但不含任何未来 bar；
- BTC 只作为上下文，不产生 BTC 订单；
- Mark 缺口只通过 v0.27 已绑定的 official daily repair sidecar 补齐；
- Funding 使用决策时点之前最近一次实际结算事实，不做未来利率预测；
- 缩放均在每个 fold 的 fit window 内拟合，calibration/OOS 不得影响均值、
  方差、权重或缺失处理；
- 缺少任一必需事实的样本失败关闭，不做前值回填或跨缺口插值。

由于 archive 的 `available_at` 是 2026 年摄取时刻，因果审计只证明
event-time lookahead-free，不证明历史时点本系统已经收到这些数据。

## 5. 冻结标签与成本

分类标签：

```text
y_take = 1 if realized_net_return_24h > 0 else 0
```

执行代理固定为 `OFFICIAL_1M_WORST_BAR_PLUS_10BPS_V1`：

- entry 使用开仓决策后的第一根 1m bar；
- LONG entry fill = 该分钟 `high × (1 + 10bps)`；
- exit 使用退出决策后的第一根 1m bar；
- LONG exit fill = 该分钟 `low × (1 - 10bps)`；
- 双边 taker fee 各 15bps；
- `label_reference_notional_usdt = 1000`，不随 AI 接受/拒绝或 bucket 改变；
- 数量按 `0.0001 ETH` 向下取整；
- Spot LONG funding cashflow 固定为 0；
- Spread/Slippage 已进入 fill，不再重复从标签扣除；
- entry/exit 1m 缺失、价格无效或顺序错误的样本标记 ineligible。

该代理比用 minute open 更保守，但仍没有历史 BBO、可见数量、部分成交、
拒单或真实账户费率，因此不能作为正式 execution/PIT 标签。

## 6. Split 与模型配方

复用 v0.27 plan 的 8 个季度 archive OOS fold：

- 每折紧邻其前 18 个月训练窗；
- 最后 1 个月只用于 calibration；
- fit/calibration/OOS 边界各实施 24h purge；
- 每个 OOS 起点前 24h 为 embargo，不计入评估；
- 不 shuffle，不随机划分；
- 全部 episode 依决策时间排序。

Logistic 配方固定：

- 方向：LONG；
- 9 个固定特征，无特征选择；
- fit-window z-score，零方差特征失败关闭；
- L2 Logistic，固定初始化、学习率、迭代数与输出量化；
- calibration month 只拟合一维 Platt intercept/slope；
- 接受门槛固定为 `p_net_positive >= 0.55`；
- 常数概率基准只使用 fit-window 正例率；
- 不搜索 seed、C、阈值、窗口或特征子集。

## 7. 报告但不晋级的指标

每折及总计至少报告：

- raw/eligible/positive episode count；
- Brier 与 fit-only constant Brier；
- baseline 与 Logistic-filtered 成本后标签收益；
- 接受率、配对增量和季度非负计数；
- feature count 与事件重叠诊断；
- Prefix-vs-full、warm-up 与 offline-prefix parity；
- 训练、calibration、OOS 的绝对 UTC 范围；
- 所有 source、dataset、recipe、prediction root hash。

v0.28 不用这些探索性结果通过正式 ReleaseGate。无论点估计如何：

- `formal_pit_eligibility = INELIGIBLE_ARCHIVE_REPLAY`
- `release_oos_eligibility = INELIGIBLE_EXPLORATORY_ARCHIVE`
- `model_activation_eligibility = INELIGIBLE_RESEARCH_ONLY`
- `profitability_eligibility = INELIGIBLE`

## 8. 验收

1. 42 个月 1m ZIP/checksum 全部可恢复、owner-only、整月连续；
2. 所有特征最大事件时间不晚于决策时间；
3. 所有 entry/exit minute 严格晚于各自决策；
4. Prefix-vs-full 与不同 warm-up 长度逐字段相同；
5. 边界 purge/embargo 无标签跨越；
6. 同一数据、配方和代码重复 100 次产生相同 dataset/model/prediction hash；
7. rehash 后的特征、标签、split、权重或汇总篡改仍被语义重建发现；
8. 全量测试、Schema 镜像、Evaluator build 与 compact evidence 一致；
9. 结果按 LONG 单独报告，SHORT 明确未运行；
10. README/ADR/实施追踪明确说明这不是盈利证明。
