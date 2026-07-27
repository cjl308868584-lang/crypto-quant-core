# 实施追踪 v0.20.0

日期：2026-07-27

状态：已完成并验证

## 本版本完成

- 固定 Binance public `GET /api/v3/time` 三样本探针；
- 保存原始 body、SHA、selected headers、wall/monotonic 时刻与 receipt hash；
- 用整数保守 offset interval 交集区分 aligned、corrected 和 blocked；
- 偏移稳定可界定时生成 monotonic-anchored corrected clock；
- probe 无效、RTT/偏移超限或区间不相交时阻断 v0.19 scheduler；
- 时间请求、Paper 行情请求和总网络计数独立保存；
- 新增 append-only SQLite WAL/FULL runtime heartbeat 事件链；
- 数据库 trigger 禁止 heartbeat UPDATE/DELETE；
- 新增 gap、continuity unknown、clock blocked、scheduler failure/busy 告警；
- 保存 active/raised/cleared transition，投递资格固定为本地 Artifact；
- 新增严格 runtime/probe Schema、完整事件/探针重放、self-hash 和外部
  attestation；
- 新增 one-shot `paper-runtime-run`，没有 URL、header、key、account、
  order、slot 或 time override；
- v0.19 scheduler 与 v0.18 经济重放语义保持不变。

## 真实官方 smoke

来源：Binance public market-data host，ETHUSDT Spot，无凭据 GET。

### 第一次运行

- Clock：`HEALTHY_CORRECTED`
- Offset intersection：`[2170ms, 2857ms]`
- Correction：`2513ms`
- RTT：`686ms / 2051ms / 825ms`
- Scheduler：`EXECUTED`
- Network：server-time `3` + market `4` = `7`
- Active alerts：空
- Slot：`ETHUSDT_20260727T120000Z`
- Cycle run hash：
  `885ca9c55fe6d12a699253308f4c75e65e248f15a6a87b3822914473a89ef356`
- Schedule snapshot hash：
  `0121b45b584878d6460077a7448d9064f1cc71fdaf0b272aee451faa8ce1f28c`
- Runtime snapshot hash：
  `ec87749c301fa6dbf038fb64ab161632553b79ed15a13ebc210ef68cd0d97e41`
- Runtime external attestation：
  `4a418154c8fa7ca5f106f2827a5a251152297a28e2fc75c266a6e84ef5df86f8`
- Runtime replay reasons：空

### 同槽位第二次运行

- Clock：`HEALTHY_CORRECTED`
- Offset intersection：`[2164ms, 2857ms]`
- Correction：`2510ms`
- Scheduler：`ALREADY_SUCCEEDED`
- Network：server-time `3` + market `0` = `3`
- 注入的 bomb market transport 调用数：`0`
- Heartbeat count：`2`
- Trusted heartbeat gap：`8s`
- Active alerts：空
- Runtime snapshot hash：
  `74842de4823394542203d582b8b6ca51182da66ad2d40394e187310c79976baf`
- Runtime external attestation：
  `06a0b68f8ea4a9ebe33df0383920dde733754c8cfd42e78307d0239d1f1b6586`
- Runtime replay reasons：空

冻结 Artifact 位于 `artifacts/runtime/v0.20-smoke/`，包含 cycle、schedule
以及第一次和第二次 runtime snapshot。临时 SQLite 状态库未提交。

## 安全与故障验证

- blocked probe 的 market transport 调用数为 0；
- transport failure 仍形成 blocked heartbeat Artifact；
- wall clock 跳变不影响 monotonic corrected clock；
- monotonic reversal 失败关闭；
- offset 超限、RTT 超限、区间不相交、status/redirect/JSON/body 篡改均被
  拒绝或阻断；
- runtime event、payload、chain、probe receipt、summary 和 alerts 均重放；
- symlink state path、数据库事件篡改、UPDATE/DELETE 失败关闭；
- alert raise/clear 和 heartbeat gap 从事件重新推导；
- 没有账户、密钥、Broker、订单或资金能力。

## 最终验证证据

- 新增 runtime health/state/wrapper/CLI/真实 Artifact tests：19 项，0 失败
- v0.19 scheduler + v0.20 聚焦 tests：33 项，0 失败
- 全量 tests：361 项，0 失败
- Golden Vector：41 项
- Evaluator build input：80 个冻结文件
- Evaluator build input tree：
  `665c03b1fa0fb6bc4ff6abd688580c2c49b733774e064ad3a6d92525478913f7`
- Evaluator build：
  `c39f4db633b83ae1dc8dd9117d73e708cfcc32e542c0e5973d843fa52995a24a`
- release/governance/schema/build validators：执行成功；Release Policy 仍按
  设计返回 `DESIGN_BASELINE` / `PRODUCTION_ACTIVATION_DISABLED`
- Cycle、schedule、runtime trusted replay：PASS
- 真实同槽位 market idempotency：PASS，第二次 market request count 0

## 赚钱与 AI 含义

v0.20 消除了一类会制造错误周期、错误特征和未来签名失败的运行风险，但不
增加交易 alpha。当前仍不能声称：

- 已完成连续 90 天系统 Paper；
- 操作系统调度和外部告警已经启用；
- 简单基线扣除真实费用后长期盈利；
- AI 优于简单基线或平台 AI；
- 系统具备任何资金资格。

下一版本不继续扩展运行基础设施，优先补永续 Mark/Index/Premium/OI、
Funding 和账户成本上下文，直接提高策略收益判断的真实性。
