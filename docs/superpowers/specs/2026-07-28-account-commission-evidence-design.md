# v0.22 当前账户手续费证据设计

日期：2026-07-28

状态：Frozen for implementation

## 1. 目标

为 ETHUSDT 现货 LONG 与 USDⓈ-M 永续 SHORT 获取当前账户实际 commission
rate，形成与 Binance server time、API key 身份和原始 USER_DATA response
绑定的可重放证据。它用于替换离线 Paper 中固定 15 bps/side 假设的研究
输入，不负责余额、持仓、订单、成交、Broker 或真实下单。

本版本不能把“当前费率”反填为历史费率，也不能仅凭调用方自填 approval
升级为 Production。

## 2. 官方来源

只允许以下 Binance 官方接口：

1. 三次公开
   `GET https://data-api.binance.vision/api/v3/time`；
2. `GET https://api.binance.com/sapi/v1/account/apiRestrictions`；
3. `GET https://api.binance.com/api/v3/account/commission?symbol=ETHUSDT`；
4. `GET https://fapi.binance.com/fapi/v1/commissionRate?symbol=ETHUSDT`。

后三个接口为 HMAC-SHA256 `USER_DATA` 请求，固定
`recvWindow=5000`，使用纠偏后的整数毫秒 timestamp，signature 最后追加。
v0.22 不支持 RSA、Ed25519、自定义 host、proxy、header、symbol、recvWindow
或请求顺序。

官方 Spot 文档规定安全 endpoint 需要 API key、timestamp 和 signature，并
支持把读取权限与交易权限分开；`account/commission` 返回 standard、
special、tax 和 BNB discount。官方 USDⓈ-M connector/接口固定
`fapi/v1/commissionRate`，返回账户当前 maker/taker commission rate。

参考：

- <https://developers.binance.com/en/docs/products/spot/rest-api>
- <https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md>
- <https://github.com/binance/binance-futures-connector-python>

## 3. 凭据边界

CLI 只接受 `--output-root`。API key 与 secret 的值不能通过 argv、JSON、
stdin、日志或 Artifact 传入。

固定从两个环境变量读取“文件路径”，而不是 secret 本身：

- `CRYPTO_QUANT_BINANCE_READONLY_API_KEY_FILE`
- `CRYPTO_QUANT_BINANCE_READONLY_API_SECRET_FILE`

凭据文件必须：

- 是当前用户拥有的普通文件；
- 不是 symlink；
- mode 为 `0600`，没有 group/other 权限；
- 小于 512 bytes；
- 内容为单行 ASCII，不能为空；
- 位于 output root 和 Git workspace 之外。

进程只在签名生命周期中持有 secret bytes，结束后覆盖可变 buffer。Python
运行时不能保证删除所有内部副本，因此文档必须明确剩余 process-memory
风险。Artifact 只保存 API key 的 SHA-256 fingerprint，不保存 key、
secret、signature 或带 signature 的 URL。

## 4. 只读权限门

必须先调用 `apiRestrictions`，并在请求另外两个费率 endpoint 之前验证：

- `enableReading=true`；
- `ipRestrict=true`；
- withdrawals、internal transfer、universal transfer 均禁用；
- Spot/Margin trading、Futures trading、Margin、Vanilla Options 均禁用。
- Portfolio Margin trading 和任何未来新增的权限布尔字段均不得为 true。

允许保留 Binance 新增的 false 权限字段，但任何未知 true 权限都按过宽处理。
任何必需字段缺失、类型错误、权限过宽或响应无法验证时：

- 两个 commission endpoint 调用数必须为 0；
- 输出 `ACCOUNT_CREDENTIAL_SCOPE_BLOCKED`；
- 不自动重试；
- 不因“只查询费率”而容忍可交易/可提现 key。

如果 Binance 的只读 key 无法访问某个 commission endpoint，则真实 smoke
失败关闭，不允许临时启用交易权限来绕过本门。

## 5. 请求与 receipt

每个 signed request 固定保存：

- family、host、path、公开 query 参数；
- timestamp、recvWindow；
- unsigned query SHA-256、signed query SHA-256；
- API key fingerprint；
- status、最终 host/path；
- selected headers；
- raw UTF-8 response body、body SHA-256；
- trusted request/receive time；
- receipt hash。

验证器从固定参数重新构造 unsigned query，并验证 query hash；signature 和
API key header 不持久化。HTTP transport 禁用环境 proxy，只允许原 host
HTTPS，10 秒 timeout、每个 endpoint 一次、body 上限 64 KiB。

完整成功请求边界为：

- server-time：3；
- permission：1；
- commission：2；
- total：6。

## 6. 严格解析

### 6.1 Spot

只接受 `symbol=ETHUSDT`，并严格解析：

- `standardCommission.{maker,taker,buyer,seller}`；
- `specialCommission.{maker,taker,buyer,seller}`；
- `taxCommission.{maker,taker,buyer,seller}`；
- `discount.{enabledForAccount,enabledForSymbol,discountAsset,discount}`。

所有 rate 是规范、有限、非负 Decimal unit ratio，且不大于 1。

对 role `maker/taker` 与 side `buyer/seller`：

```text
no_discount_rate =
  standard.role + standard.side
  + special.role + special.side
  + tax.role + tax.side
```

Spot Paper 的权威保守费率使用 `no_discount_rate`。只有 account 和 symbol
discount 同时启用且 asset 为 BNB 时，才额外报告：

```text
discounted_scenario =
  (standard.role + standard.side) * discount
  + special.role + special.side
  + tax.role + tax.side
```

这里的 `discount` 按 Binance Commission FAQ 是折后乘数，而不是“再减去的
比例”。由于没有证明 BNB 余额、实际扣费资产和 USDT 换算，discounted 值
仍只是情景，不得作为当前权威成本。

### 6.2 USDⓈ-M

只接受：

- `symbol=ETHUSDT`；
- `makerCommissionRate`；
- `takerCommissionRate`。

开仓和退出按各自 maker/taker role 使用同一当前 unit rate；报告
`two_taker_sides_rate = 2 * takerCommissionRate`。Funding 保持 v0.21
独立上下文，不与 commission 合并。

## 7. Artifact、时效和资格

`AccountCommissionSnapshot` 包含：

- server-time probe；
- permission receipt；
- Spot/Futures commission receipts；
- credential fingerprint；
- 规范 commission observations；
- 每 1000 USDT 单边和往返成本；
- 与 v0.18 固定 15 bps/side 假设的覆盖比较；
- quality report；
- self-hash。

外部 attestation hash 绑定 snapshot、probe、三个 receipt 和 credential
fingerprint，保存在 Artifact 之外。

当前费率的 `observed_at` 取最后一个 receipt 的 trusted receive time，
`valid_until` 固定为四小时后。过期后不得用于新的 Paper 决策。资格固定：

- `cost_context_eligibility=CURRENT_PAPER_CONTEXT_ONLY`
- `historical_backfill_eligibility=FORBIDDEN`
- `production_eligibility=EXTERNAL_APPROVAL_NOT_IMPLEMENTED`
- `profitability_eligibility=INSUFFICIENT_DURATION_AND_EXECUTION`

## 8. 失败与非目标

没有凭据时发布
`REAL_ACCOUNT_COMMISSION_SMOKE_NOT_RUN_NO_CREDENTIALS`，不能用网页 VIP_0
标准费率、fixture 或用户口述数字冒充账户事实。

v0.22 不：

- 查询余额、持仓、订单、成交或 UID；
- 请求或启用交易、提现、转账权限；
- 发送 POST/PUT/DELETE；
- 生成订单；
- 把当前费率用于历史回测；
- 估计 BNB 资产价值；
- 自动批准 FeeSchedule；
- 修改 v0.18 基线信号、v0.21 Funding 或 AI。
