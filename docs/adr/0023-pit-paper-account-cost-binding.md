# ADR-0023：PIT Paper 账户成本绑定

状态：Accepted

日期：2026-07-28

## 背景

v0.18 的离线 Paper 使用每边 15 bps 保守 taker fee，v0.22 能取证当前
ETHUSDT Spot 与 USDⓈ-M 账户费率，但两者仍是相互独立的 Artifact。若不建立
时间和信任绑定，系统可能把未来看到的低费率倒填到历史 Paper，产生虚假的
扣费后收益。

## 决策

v0.23 新增 `paper-account-cost-binding-v1`。构建器同时消费完整的
`offline-paper-run-v1`、`account-commission-snapshot-v1` 及各自在 Artifact
之外保存的 trusted attestation hash。两个源对象必须分别通过 Schema、
self-hash、语义重放和外部信任验证。

账户费率 `observed_at` 必须不晚于 Paper `decision_time`，`valid_until` 必须
覆盖 Paper `run_end`。不满足时失败关闭，禁止用事后当前费率回填。

对于已有 Spot BUY 成交，系统保持信号、数量、成交价、BBO、滑点和退出价不变，
只重建：

- 15 bps 假设的进场费与保守退出费；
- 账户 no-discount `taker_buy` 进场费；
- 账户 no-discount `taker_sell` 退出费；
- 两套费用之差；
- 费用变化后的保守清算权益和净变化。

BNB discount 不进入权威值，因为系统没有读取 BNB 余额或证明支付资产。无成交
周期的两套费用均为 0，权益不变。AI arm 继续是
`NOT_RUN_NO_APPROVED_MODEL`。

## 信任与安全边界

绑定 Artifact 嵌入两个完整源对象、源信任哈希副本、PIT 事实、费用公式和结果。
副本只用于谱系，不能取代调用方独立保存的 attestation。验证器会从两个嵌入源
完整重建绑定；即使攻击者重算 self-hash，费用、权益、资格或源对象篡改仍会
失败。

one-shot CLI 只读取本地 Artifact 与 trust-hash 文件，输出不可变 mode-0600
绑定文件。它不联网、不读取 credential、不访问余额、不下单，也不接受 URL、
API key、secret、fee override、symbol 或 created-at 参数。

## 结果与资格

- `paper_eligibility=COST_REPLAY_ONLY_NOT_LONGITUDINAL`
- `production_eligibility=NOT_APPROVED`
- `profitability_eligibility=INSUFFICIENT_DURATION_EXECUTION_AND_AI`

费用下降只表示原假设更保守，不等于策略盈利。当前仓库没有真实账户费率
snapshot，因此真实绑定未运行；fixture 只证明代码路径，不证明账户来源、90 天
Paper、AI 增量或实盘收益。
