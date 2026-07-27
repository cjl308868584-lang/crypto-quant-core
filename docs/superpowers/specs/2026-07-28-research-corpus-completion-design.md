# v0.27 研究语料完成与官方 Daily Repair 设计

日期：2026-07-28
状态：冻结设计基线
发布目标：`0.27.0`

## 1. 真实运行发现

v0.26 的 42 月计划已实际执行。Binance Futures 月度来源暴露两个不能在
fixture 中推断的问题：

1. 月度 Mark Price Kline 带官方下划线表头；
2. Funding `calc_time` 存在数毫秒调度抖动；
3. `ETHUSDT` Mark 月度文件在 `2023-02-24` 和 `2026-06-29` 各缺整日
   6 根 4h Kline，但对应官方 daily archive 完整。

本版本必须保存这些事实，不能插值、复制前值或把缺口月份标为
`FORMAL_COMPLETE`。

## 2. Parser V2

`BINANCE_CSV_V2`：

- 严格接受既有无表头/规范表头及 Binance 官方月度下划线表头；
- 不接受任意未知列名、列数或额外字段；
- Funding 仍保存原始毫秒 `calc_time`；
- 覆盖调度只容许 ±1 秒抖动；
- 超过 ±1 秒、重复、倒序或缺事件仍形成 blocking finding；
- 新 snapshot 使用 V2；
- 已冻结 V1 snapshot 继续按其 bytes、parser version 和 attestation
  验证，不能原地改写。

## 3. 月度 Corpus 完成边界

基础 corpus 必须满足：

- 168/168 item 均有 checksum-verified exact snapshot bytes；
- append-only state 完整重放；
- 0 pending、0 claimed、0 failed；
- 允许的 degraded item 只能是官方来源覆盖缺口；
- 任何 malformed、duplicate、scope、time、hash 或 checksum 错误仍失败；
- owner-only 目录 `0700`、文件 `0600`；
- completed state 再运行时网络调用为 0。

基础 corpus 的正确状态为
`READY_FOR_ARCHIVE_RESEARCH_FEATURE_BUILD_WITH_SOURCE_GAPS`，直到每个缺口
都有显式官方 patch。

## 4. Official Daily Repair Bundle

每个 repair：

- 强引用 plan、base corpus event chain、base item/snapshot/attestation；
- 列出精确缺失 `open_time`；
- 只接受同 provider/market/family/symbol/interval 的官方 daily archive；
- daily ZIP 与 `.CHECKSUM` 各自验证；
- daily snapshot 必须 `FORMAL_COMPLETE`；
- patch facts 必须恰好等于缺失集合；
- patch 与 base 不得有业务键重叠；
- base + patch 必须恰好覆盖完整 UTC 月；
- 不允许 REST、插值、合成价格或跨月数据。

Bundle 必须重放所有 base 与 patch source rows，生成不可变 self-hash 和
combined coverage root。只有全部 degraded item 被完全修复、没有未解决
缺口时，才产生：

`READY_FOR_ARCHIVE_RESEARCH_FEATURE_BUILD_WITH_EXPLICIT_DAILY_REPAIRS`

该状态仍固定：

- `formal_pit_eligibility = INELIGIBLE_ARCHIVE_REPLAY`
- `release_oos_eligibility = INELIGIBLE`
- `profitability_eligibility = INELIGIBLE`

## 5. 独立验证

发布前使用新进程：

1. 从 SQLite 开头重放 338 个事件和全部 168 个 source bytes；
2. 使用 bomb transport 证明 completed state 网络调用为 0；
3. 验证 168 个 source 文件和 repair 文件权限；
4. 验证四流 × 42 月 coverage；
5. 验证两个 repair 的官方 checksum、缺失集合和 combined coverage；
6. 生成 compact completion evidence，Git 不包含 60 MiB full corpus。

## 6. 不在本版本做

- 不训练 Logistic/XGBoost；
- 不把 archive/repaired archive 当 PIT-valid OOS；
- 不把 Mark daily repair 解释为真实成交价格；
- 不接入账户、Broker、下单或资金；
- 不删除 v0.26 失败发现或 v1 partial corpus 以美化历史。
