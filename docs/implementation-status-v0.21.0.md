# 实施追踪 v0.21.0

日期：2026-07-27

状态：已完成并验证

## 本版本完成

- 固定 ETHUSDT USDⓈ-M 五个公开、无凭据 Futures GET；
- 复用 v0.20 三样本 server-time 健康门，blocked 时 Futures 调用数为 0；
- 禁用环境代理、任意 host、URL、header、credential、account 和 order；
- 保存五个 raw response、SHA-256、selected headers、可信请求/接收时刻和
  receipt hash；
- 严格解析 Mark、Index、Estimated Settle、Premium Kline、当前/4h OI 和
  Funding history；
- 验证 1m/4h 固定间隔、source capture window、历史时序和新鲜度；
- 从 raw receipts 重建 basis、OI 4h value change 和 observed Funding
  interval；
- 报告每 1000 USDT SHORT 的下一次、重复当前利率 24h 和两倍近期绝对值
  不利场景；
- Funding 间隔不一致时保留下一次场景，但 24h 场景固定为 null；
- 新增严格 Schema、self-hash、external attestation hash 和不可变 one-shot
  CLI；
- 不启用 SHORT、Broker、账户、API key、订单、真实资金或 AI 决策。

## 真实官方 smoke

执行：

```bash
PYTHONPATH=src python3 -m crypto_quant.perpetual_context_cli \
  --output-root /tmp/crypto-quant-v021-smoke
```

结果：

- 三样本 server-time 健康门完成；
- 第一个 `fapi.binance.com` Futures 请求在形成 HTTP receipt 前返回
  `PERPETUAL_TRANSPORT_FAILURE`；
- Futures request attempt：1；
- 有效 Futures receipt：0；
- 自动重试：0；
- 剩余四个请求：未执行；
- proxy、credential、account endpoint、order 和 substitute source：均未
  使用。

冻结证据：
[binance-perpetual-context-smoke-failure-v0.21.0.json](../artifacts/market-data/binance-perpetual-context-smoke-failure-v0.21.0.json)。

因此真实数据资格保持
`REAL_FUTURES_SMOKE_NOT_CAPTURED_NETWORK_UNREACHABLE`；fixture 重放通过不能
冒充真实 contemporaneous capture。

## 赚钱与 AI 含义

本版本让策略能在数据可达时量化 SHORT 的 Funding 方向、基差与 OI 拥挤度，
减少“信号看似赚钱但资金费/拥挤风险相反”的误判。它没有新增或证明 alpha，
Funding 压力场景不得进入 realized PnL。

AI 仍然没有批准模型，也没有可比较的 AI Paper 成交。永续上下文未来可作为
候选特征，但必须经过 PIT availability、泄漏审计、消融、成本后配对增量和
长期 Paper，不能因为字段增加就声称优于平台 AI。

## 最终验证证据

- 新增永续 plan/transport/parser/artifact/CLI/失败证据 tests：16 项，0 失败
- 永续模块 + Evaluator Build 聚焦 tests：19 项，0 失败
- 全量 tests：377 项，0 失败
- Python compileall：PASS
- Golden Vector：41 项
- Evaluator build input：85 个冻结文件
- Evaluator build input tree：
  `e5be3b0dd0451ff47243c4be9f409bd415ad3195bee3251afa794c176e4d2faa`
- Evaluator build：
  `792a91f6ecb09e95a2c124216df0710fe412442efc5938eee4c27b9333f08754`
- release/governance/schema/build validators：执行成功；Release Policy 仍按
  设计返回 `DESIGN_BASELINE` / `PRODUCTION_ACTIVATION_DISABLED`
- fixture raw receipt replay 与 external attestation：PASS
- 真实 Futures smoke：失败关闭，未伪造成功 Artifact
