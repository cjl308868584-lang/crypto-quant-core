# 实施追踪 v0.22.0

日期：2026-07-28

状态：已完成并验证

## 本版本完成

- 固定 ETHUSDT 的 API 权限、Spot commission 与 USDⓈ-M commission 三个
  USER_DATA signed GET；
- 复用 v0.20 三样本 server-time 健康门，blocked 时账户调用数为 0；
- 新增 owner-only、0600、非链接、边界外 credential-file gate 和内存清零
  的 opaque HMAC signer；
- 任何非读取/IP 限制之外的 true 权限都会在第一个响应后阻断，commission
  请求数为 0；
- 禁用代理、redirect、自动重试、任意 host、URL、header、symbol、time、
  account、balance 与 order override；
- 保存 raw response、redacted request transcript、receipt hash、self-hash
  和 external attestation hash，不保存 key、secret、signature 或签名 URL；
- 严格解析 Spot standard/special/tax/BNB discount 和 USDⓈ-M maker/taker；
- 权威成本使用 no-discount rate；BNB 折扣只作为非权威情景；
- 报告每 1000 USDT 单边/双边 taker 成本，并与 v0.18 的每边 15 bps 假设
  比较；
- 不启用余额读取、Broker、下单、真实资金或 AI 决策。

## 真实账户 smoke

没有在固定环境变量中发现合规的只读、IP-restricted credential 文件，因此
本版本没有创建签名，也没有发出 server-time 或账户请求。系统没有向聊天索取
secret，没有以 fixture、公开网页、平台默认费率或其他账户响应冒充真实账户
证据。

冻结证据：
[binance-account-commission-smoke-not-run-v0.22.0.json](../artifacts/account-cost/binance-account-commission-smoke-not-run-v0.22.0.json)。

因此真实账户资格保持 `REAL_ACCOUNT_COMMISSION_NOT_CAPTURED`。只有未来用户在
workspace 和输出目录之外自行准备两个 owner-only 0600 文件，并配置固定路径
环境变量后，才允许 one-shot 捕获。

## 赚钱与 AI 含义

本版本把“平台公布费率”升级为“当前账户、当前产品、当前标的”的可重放成本
输入，能减少策略因错误手续费假设产生的虚假盈利。但账户费率只是必要成本项：
没有真实成交滑点、长期 Paper、PIT-valid OOS 与配对增量，仍不能声称赚钱。

AI 与简单基线必须使用同一份已验证账户成本证据；AI 不得通过忽略 special、
tax、Funding 或折扣前提获得表面优势。当前仍无批准 AI 模型与可比较 AI Paper
成交。

## 最终验证证据

- 账户费率 plan/credential/permission/transport/parser/artifact/CLI tests：
  15 项，0 失败
- 账户费率模块 + Evaluator Build 聚焦 tests：24 项，0 失败
- 全量 tests：392 项，0 失败
- Python compileall：PASS
- Golden Vector：41 项
- Evaluator build input：90 个冻结文件
- Evaluator build input tree：
  `3edfc3fe439e1f505a8f642ec319aecc3f0775a9553cecb35adc9fb945d9a21d`
- Evaluator build：
  `312e51ad6adb83eae73995d2934284a95a04aa19cac86b380786cbf4e02d1f08`
- release/governance/schema/build validators：执行成功；Release Policy 仍按
  设计返回 `DESIGN_BASELINE` / `PRODUCTION_ACTIVATION_DISABLED`
- 真实 signed smoke：未运行，失败关闭，未伪造成功 Artifact
