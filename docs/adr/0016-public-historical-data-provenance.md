# ADR-0016：官方历史归档只能作为可重放来源

状态：Accepted

日期：2026-07-27

## 背景

真实市场数据进入研究和 Paper 之前，必须同时证明来源、字节完整性、解析
结果和时间语义。官方公开归档提供真实历史事实和配套 SHA-256
校验，但事后下载无法证明这些字节在历史决策时刻已经被系统收到，也无法
证明归档后来没有被替换。

## 决策

Binance 公开归档统一标记为 `ARCHIVE_REPLAY_ONLY`。归档事实的
`available_at` 使用实际摄取时间，不回填为事件时间；这类快照可以用于
探索、确定性重放和原型验证，但不能令 `PIT_AND_SPLIT_VALID` 通过。

只允许由结构化请求生成的官方 HTTPS URL。获取链必须先读取 ZIP 和相邻
`.CHECKSUM`，验证官方 SHA-256 后才能解压、解析和发布快照。失败时不回退
到未校验字节。

URL 是定位信息，不是 Artifact 身份。相同 URL 的内容可能被修订，因此
身份绑定归档 SHA-256、checksum 文件 SHA-256、HTTP validator、receipt
hash、quality report hash 和 snapshot hash。

手续费计划单独保存为带有效期和审批状态的 `FeeScheduleSnapshot`。费率
取决于产品、账户等级、折扣和生效时间，不能从 Kline、AggTrade 或当前
网页费率推导，更不能用当前费率反填历史。

## 不变量

- v0.16 只允许 `data.binance.vision` 的公开 GET，不含密钥、签名、账户
  查询、POST 或订单能力；
- 官方 checksum 通过之前不得解压或解析；
- 原始 ZIP、完整 CSV 和 normalized rows 不进入仓库；
- source URL 相同而内容哈希不同，必须视为不同来源版本；
- `ARCHIVE_REPLAY_ONLY` 不得支持 PIT-valid OOS 或盈利声明；
- 未审批、有效期不匹配的手续费快照不得进入正式经济 PnL。

## 备选方案

- 只记录 URL：无法识别官方原地修订，拒绝。
- 把事件时间当作历史可用时间：会制造虚假的 PIT 资格，拒绝。
- 将当前公开费率和行情一起冻结：混淆市场事实与账户专属成本，拒绝。
- 提交原始 ZIP 和全部 normalized rows：体积大且不是发布审计所需，拒绝。

## 后果

v0.16 支持 Spot Kline、Spot AggTrade、USDⓈ-M Mark Price Kline 和
Funding Rate 的只读归档重放。BBO、Order Book、OI、Index/Premium、
账户成交、真实手续费、实际滑点和 contemporaneous receive-time
修订链仍缺失。

因此，本版本只能证明真实归档摄取链确定、完整且失败关闭，不能证明策略
赚钱，也不能提供 PIT-valid OOS、Shadow、Paper 或 Canary 证据。下一步
必须建立同时捕获实际接收时间与修订链的 contemporaneous capture，并用
真实数据生成离线 Paper 的决策、成交、费用、经济账本和统计 Artifact。

## 验证证据

- 实现：`src/crypto_quant/market_data.py`、
  `src/crypto_quant/market_data_cli.py`
- 契约：`config/historical-market-data-snapshot-v1.schema.json`、
  `config/fee-schedule-snapshot-v1.schema.json`
- 真实 smoke：`artifacts/market-data/binance-public-data-smoke-v0.16.0.json`
- 自动化测试：`tests/test_market_data.py`、`tests/test_market_data_cli.py`
