# v0.29 基线失败归因与单一 Challenger 预注册设计

日期：2026-07-28

状态：冻结

## 1. 目标

解释 v0.28 的 `SPOT_LONG_SMA20_VOL12_BUCKET25_V1` 为什么在扣除保守执行
与费用后失败，并冻结一个单一、经济可解释的下一代简单基线假设。

本版本不搜索“最好参数”、不训练新 AI、不把已经看过的 2023-01 至
2026-06 archive 重新包装成正式 OOS，也不宣称赚钱。

## 2. 输入边界

- 唯一输入数据集：
  `causal_dataset_d9aed82cb5bb7b30df58d55debcde2f59eaf6b29d5e9bbf8f9d6f807adf01549`；
- 数据集 hash：
  `2a8ee3e2d2345f06764c654a6b0e94c777efafcafe54e88f4a2e2254f4629ec8`；
- 使用 v0.27 冻结的 8 个季度 fold，只用于描述已发生的失败；
- 输入必须通过 causal dataset Schema、自哈希和语义字段校验；
- 不读取 Logistic 概率，防止 AI 结果反向影响简单基线归因。

## 3. 固定归因维度

所有分组边界在运行真实归因前冻结：

1. `ALL_EVENTS`；
2. 8 个冻结 archive OOS fold；
3. 退出原因；
4. 持有时长；
5. `eth_sma20_distance`：
   `[0,0.005)`、`[0.005,0.01)`、`[0.01,0.02)`、`[0.02,+inf)`；
6. `eth_log_return_5`：`<0`、`>=0`；
7. `eth_annualized_volatility_20`：
   `[0,0.4)`、`[0.4,0.8)`、`[0.8,1.2)`、`[1.2,+inf)`；
8. `eth_mean_range_ratio_6`：
   `[0,0.01)`、`[0.01,0.02)`、`[0.02,0.04)`、`[0.04,+inf)`。

不得根据结果移动边界、合并分组或只展示有利分组。

## 4. 固定统计量

每组输出：

- 样本数、正标签数、正标签率；
- gross PnL、entry fee、exit fee、total fee、net PnL 的总和；
- gross/net 平均值；
- gross 正但 net 不正的 fee-flip 数；
- net 最小值、最大值；
- 按决策时间排序的 first/last time。

全局另外输出：

- Top-1 与 Top-5 正收益事件对全部正贡献的占比；
- 删除 Top-1 与 Top-5 后的净收益和；
- gross PnL 是否已在费用前为负；
- exact fee drag；
- 归因 Artifact 自哈希和全部分组 root hash。

这些是描述性诊断，不计算事后显著性，不形成晋级门。

## 5. 单一 Challenger 预注册

冻结唯一候选：

`SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2`

入场必须同时满足：

```text
current_close / prior_sma20 - 1 >= 0.005
ln(current_close / close_5_bars_ago) > 0
```

`0.005` 等于标签政策中双边 10bps slippage 与双边 15bps taker fee 的固定
名义成本预算。它不是从真实归因结果中搜索得到的最佳阈值。

退出、最短持有、垂直边界、tick、step、reference notional、费用与执行
代理全部保持 v0.28 不变。

## 6. 试验与验证隔离

- trial family：`baseline-rule-challenger-2026q3`；
- 经济假设数：1；
- 参数组合数：1；
- 不允许在同一版本增加 OR 条件、第二阈值或替代退出；
- 2023-01 至 2026-06 永久标记 `VIEWED_DEVELOPMENT_ONLY`；
- challenger 必须从完整 4h 事件流重新生成 episode，拒绝的候选不得消费
  持有窗口；
- v0.29 只预注册，不计算 challenger 历史收益；
- 最早新的 prequential forward 起点：
  `2026-07-29T00:00:00.000Z`；
- 只有决策前已经同时捕获的数据、成本与预测才可进入 forward 证据；
- 未达到预注册样本与时间门时结果为 `INCONCLUSIVE`，不得回看后改阈值。

## 7. Artifact 与安全边界

- 新增 `baseline-failure-attribution-v1.schema.json` 及 package mirror；
- Artifact 只保存 compact 归因，不复制完整 780 个样本；
- Artifact 绑定 dataset/fold/hypothesis hash；
- owner-only 大型输入保持仓库外；
- `formal_pit_eligibility=INELIGIBLE_ARCHIVE_REPLAY`；
- `baseline_advancement=REJECTED_V1`；
- `challenger_evaluation_status=NOT_RUN_PREREGISTERED_FORWARD_ONLY`；
- `profitability_eligibility=INELIGIBLE`。

## 8. 验收

- 固定 fixture 与真实数据均可确定性重建；
- 输入重排、字段篡改、缺分组、改阈值、改 fold 或改结论均失败关闭；
- 100 次 fixture 输出一致；
- 真实 Artifact 能独立重建且语义原因为空；
- Schema mirror exact；
- 全量测试、Evaluator build、README、ADR 与实施追踪更新；
- 提交、快进合并 main、标记 `v0.29.0`。
