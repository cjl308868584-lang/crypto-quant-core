# ADR-0022：只读账户费率证据与真实成本边界

状态：Accepted

日期：2026-07-28

## 背景

v0.18 的离线 Paper 使用每边 15 bps 保守费用假设，v0.21 又补充了永续
Funding 压力场景，但系统仍不知道当前 Binance 账户对 ETHUSDT 实际适用的
Spot 和 USDⓈ-M commission rate。没有账户级成本，策略的扣费后收益判断可能
过度保守，也可能遗漏特殊费、税费、VIP 级别或折扣条件。

## 决策

v0.22 增加一个独立、one-shot、只读的账户费率取证工具。健康的三样本
Binance server-time 探针通过后，固定顺序执行三个签名 GET：

- `/sapi/v1/account/apiRestrictions`；
- `/api/v3/account/commission?symbol=ETHUSDT`；
- `/fapi/v1/commissionRate?symbol=ETHUSDT`。

第一个响应必须证明 `enableReading=true`、`ipRestrict=true`，且除这两个字段
外不存在值为 true 的布尔权限。若出现提现、转账、现货/保证金、期货、期权、
组合保证金或任何未来未知 true 权限，立即失败关闭，后续费率请求数为 0。

凭据只允许通过两个固定环境变量引用文件路径。文件必须由当前用户拥有、是
非链接的单硬链接普通文件、权限恰为 0600、大小受限，并位于 workspace 与
输出目录之外。CLI 不接受 key、secret、URL、host、header、proxy、symbol、
timestamp、account 或 order 参数。输出不保存 API key、secret、signature
或签名 URL。

Spot 费率分别保存 standard、special、tax 的 maker/taker 与 buyer/seller
分量。权威成本默认采用不依赖 BNB 余额的 no-discount 值；若账户与标的均
启用 BNB 折扣，只把 `standard component × discount` 加 special 与 tax
形成非权威情景。USDⓈ-M 保存账户当前 maker/taker rate。所有计算使用
Decimal，并报告每 1000 USDT 单边与双 taker-side 成本。

## 失败关闭边界

- 只提供 key/secret 字符串而不是合规文件路径时拒绝；
- symlink、hardlink、越界、权限或所有权错误、读取期间文件替换时拒绝；
- 时钟异常时账户请求数为 0；
- redirect、代理、自动重试、非 200、响应额外/缺失字段、binary float、
  非有限或负费率、symbol 不一致时拒绝；
- raw receipt、费用计算、权限摘要或资格字段被修改时，重放验证失败；
- 没有合规凭据时不进行真实 signed smoke，也不以 fixture、公开网页或其他
  账户费率替代。

## 结果与资格

- `production_eligibility=RESEARCH_ACCOUNT_COST_CONTEXT_ONLY`
- `historical_eligibility=CURRENT_ONLY_NO_BACKFILL`
- `order_execution_eligibility=NOT_IMPLEMENTED`
- `profitability_eligibility=INSUFFICIENT_LONGITUDINAL_EXECUTION_EVIDENCE`

本 ADR 缩小费用假设的不确定性，但不证明 alpha、实际成交费、滑点或盈利，
不授权余额读取、Broker、下单、杠杆、AI 自动决策或真实资金。
