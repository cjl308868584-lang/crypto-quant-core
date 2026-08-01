# System Paper Readiness Audit v0.53.0

日期：2026-08-01

状态：已完成只读差距审计；System Paper 尚未达到启动条件

审计基线：`v0.53.0` / `d0a7f2e31c469c6983a205906d25e7b6f9d7e433`

上位设计：

- `docs/superpowers/specs/2026-08-01-challenger-paper-parallel-automation-design.md`；
- `docs/superpowers/plans/2026-08-01-v1-parallel-delivery-and-automation.md`；
- `docs/delivery-roadmap-v1.1.md` 第 5–7 阶段；
- `docs/release-evaluation-spec-v1.1.md` 第 7 节。

## 1. 审计结论

项目已经具有扎实的确定性研究、证据、订单状态、风险、账本和前向 Challenger 基础，
但尚不具备“启动完整系统级 90 天 Paper”的资格。当前缺口不是再增加一个策略指标，
而是把已有分散构件整合成一个独立、无凭据、可恢复、可对账、可自然调度、可从唯一
start receipt 计时的 System Paper runtime。

截至本审计：

- 可以继续工程开发、离线重放、故障注入和本机只读 Web 建设；
- 不可以把既有 offline Paper smoke 或旧 scheduler 记录算入新的 90 天 System Paper；
- 不可以接入真实 Broker、余额、交易 API key 或订单；
- 不可以宣称策略赚钱、AI 优于基线、Paper 已通过或具备 Canary 资格；
- 原 Challenger confirmatory cohort 已因自然漏槽永久失败，不能回填；该失败不阻止
  System Paper 工程，但原 cohort 不能继续作为未来 540 槽成功证据。

## 2. 状态分类

本审计只使用四种状态：

- `IMPLEMENTED_TESTED`：代码和自动化测试均存在；
- `IMPLEMENTED_NOT_PRODUCTION_PROVEN`：实现与测试存在，但缺真实自然运行或外部事实；
- `MISSING`：启动所需集成或可信 artifact 不存在；
- `BLOCKED_EXTERNAL`：实现已到边界，但当前机器、网络或外部批准事实尚未提供。

## 3. 启动门逐项审计

| Gate | Status | Authoritative evidence | Blocking consequence |
|---|---|---|---|
| 确定性决策与保守 offline Paper | `IMPLEMENTED_TESTED` | `src/crypto_quant/offline_paper.py`; `tests/test_offline_paper.py` | 仍需接入完整系统 runtime |
| 4h 可恢复 Paper 调度原语 | `IMPLEMENTED_TESTED` | `src/crypto_quant/paper_scheduler.py`; `tests/test_paper_scheduler.py` | 旧 scheduler 不能直接成为新 System Paper cohort |
| 可信时钟与运行健康 | `IMPLEMENTED_TESTED` | `src/crypto_quant/runtime_health.py`; `tests/test_runtime_health.py` | 仍需绑定新的 Paper service/start receipt |
| 订单 ACK/拒绝/部分成交/取消/UNKNOWN 状态机 | `IMPLEMENTED_TESTED` | `src/crypto_quant/orders.py`; `tests/test_orders.py` | 尚未由模拟 Broker 驱动 |
| Target、RiskLock 与逐级风险约束 | `IMPLEMENTED_TESTED` | `src/crypto_quant/execution.py`; `src/crypto_quant/risk.py`; corresponding tests | 尚未集成 Paper slot runtime |
| 只追加经济账本与 Outbox | `IMPLEMENTED_TESTED` | `src/crypto_quant/ledger.py`; `src/crypto_quant/economics.py`; corresponding tests | 尚未形成完整 Paper 对账闭环 |
| 同槽账户/Paper/永续上下文编排 | `IMPLEMENTED_TESTED` | `src/crypto_quant/context_cycle_orchestrator.py`; `tests/test_context_cycle_orchestrator.py` | 当前生产外部输入仍不完整 |
| 模拟 Broker runtime | `MISSING` | 仓库不存在 `system_paper_broker.py` 或等价 production module | 阻断 Paper start |
| 决策→风险→模拟订单→成交→账本→对账单槽集成 | `MISSING` | 仓库不存在 `system_paper_runtime.py` 或等价 production module | 阻断 Paper start |
| 独立 System Paper 计划与 evidence scope | `MISSING` | 没有 credential-free immutable System Paper plan artifact | 阻断 Paper start |
| 独立 WAL scheduler 与故障注入证据 | `MISSING` | 旧 scheduler 未绑定完整订单/账本/对账 runtime | 阻断 Paper start |
| 独立 LaunchAgent、install receipt 与首次自然槽 start receipt | `MISSING` | 只有 Challenger 和早期 Paper renderer；无 System Paper production install chain | 阻断 90 天计时 |
| 固定 90 天 System Paper evaluator | `MISSING` | 没有完整性、运行、成本、回撤、固定成本后经济门 evaluator | 阻断 Paper PASS |
| 真实账户 commission response | `BLOCKED_EXTERNAL` | `README.md` 明确记录真实响应缺失 | 不阻止保守无凭据 Paper；阻断 Canary 成本资格 |
| Futures public context 自然成功证据 | `IMPLEMENTED_NOT_PRODUCTION_PROVEN` | `src/crypto_quant/perpetual_context.py`; 当前 README 记录真实 host 首请求失败 | 阻断 SHORT Paper；LONG-only 不得冒充双方向 V1 |
| 批准 AI ModelBundle 与配对 Paper | `MISSING` | 当前仅 `NO_AI_BASE`; README 明确 AI 臂未批准 | AI route 保持禁用；不阻断 BASELINE_ONLY Paper |
| Tail-blind operations projection | `MISSING` | 无 `operations_projection.py` 或等价 allowlist read model | 不阻断 Paper start，但阻断可信 Web 展示 |
| 本机只读 Web/API | `MISSING` | `rg --files` 未发现 Web、frontend、dashboard 或 API 实现 | 不阻断 Paper start |
| 本地 alerts 与 System Paper runbook | `MISSING` | 无 System Paper 专属 alerts/runbook | 阻断无人值守 Paper 启动验收 |
| 真实交易权限 | `MISSING`（有意） | `production_activation.enabled=false`; 无 Broker/订单实现 | 必须保持缺失直到 Paper 与后续门全部通过 |

## 4. Challenger 当前运行事实

### 4.1 最后可信前缀

- 最后一条可信 decision 槽：`2026-08-01T00:00:00.000Z`
  （北京时间 2026-08-01 08:00）；
- decision count：19；
- 下一要求槽：`2026-08-01T04:00:00.000Z`
  （北京时间 2026-08-01 12:00）；
- state SHA-256：
  `0052d799b4ab0cd31edf48fc1ba5d4f414c68998b78a31f9a66b46c2d94e35c7`；
- 策略 stdout SHA-256：
  `68916d268d7ecc7b387877a70df28e20add34cd93ea54c5a8dd760d8aa1d10c2`。

### 4.2 永久漏槽

- `kern.boottime`：北京时间 `2026-08-01 16:26:20`；
- Runner 自然启动后 stderr mtime：北京时间 `2026-08-01 16:27:01`；
- stderr exact JSON：`{"error":"CHALLENGER_RUNNER_MISSED_SLOT"}`；
- stderr SHA-256：
  `5ded25390b412835a98a1d25adda4a6ab97af3486d405199710e12a6d0bb67a5`；
- LaunchAgent 最近退出码：1；
- 设计语义：current slot 晚于 next required slot 时永久不回填；
- v0.48 frozen tail-blind evaluator：
  `FAILED_CLOSED_NO_BACKFILL` /
  `CHALLENGER_COHORT_CUMULATIVE_CONTINUITY_INVALID`。

只读 evaluator 前后 state、stdout、stderr 哈希不变。漏槽路径只执行可信时间探测，
Kline、Broker、订单和策略状态写入均为 0。原 cohort 的失败是可信研究结果，不是可通过
删除 stderr、改时钟、补写 decision 或重新运行来修复的运维错误。

## 5. 对原并行安排的影响

原计划中的“Challenger 继续自然收集”和“System Paper 工程/运行”必须重新区分：

1. 旧 Challenger：进入不可变失败取证，不再具有 540 槽成功资格；
2. replacement Challenger：需要全新冻结设计、cohort id、start、state 和 output roots，
   并永久绑定旧 cohort 失败；未完成设计与安装门前不得启动；
3. System Paper：工程工作继续，不借用旧或新 Challenger 天数；
4. Web/alerts：仍可围绕 loader-verified read model 开发，不读取被禁止的中期经济字段；
5. Canary：仍要求未来 replacement Challenger 与 System Paper 各自通过完整门，当前
   不获得任何提前资格。

## 6. 最短关键路径

工程顺序固定为：

1. v0.54 封存本审计与 Challenger failure evidence 设计/证据；
2. v0.55 冻结 credential-free `BASELINE_ONLY` System Paper plan；
3. v0.56 集成模拟 Broker 与完整 slot runtime；
4. v0.57 完成 WAL scheduler、恢复和故障注入；
5. v0.58 完成独立 deployment/install/observer/start receipt；
6. v0.59 冻结 90 天 evaluator；
7. v0.60–v0.61 完成 tail-blind projection、只读 Web、alerts 和 runbooks；
8. replacement Challenger 单独设计、审查和启动，不覆盖旧 cohort；
9. 两条新证据流分别运行并验收，全部通过后才讨论极小资金 Canary。

## 7. 审计验证

在隔离工作树中执行：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

结果：714 tests，0 failures，耗时 188.997 秒。

只读外部检查还证明：

- `main`、`origin/main`、annotated tag `v0.53.0` 精确指向同一提交；
- GitHub 目标为私有 `cjl308868584-lang/crypto-quant-core`，当前权限 `ADMIN`；
- heartbeat 原位更新前后 Challenger runtime 五个关键文件哈希不变；
- 没有触发 Runner、maintenance、行情请求、Broker、订单或策略 state 写入。

## 8. 赚钱目标的客观含义

已有工程证明系统重视可重放、成本、风险和防伪，但尚未证明能赚钱。当前最有价值的工作
不是提前看中期收益或扩大 AI 复杂度，而是形成一个能在实时公开输入下长期、无真钱权限、
完整模拟执行与对账的 System Paper。Challenger 漏槽使时间成本增加，但如实失败关闭比
伪造连续样本更接近最终可用系统；任何隐藏或回填都会让未来盈利结论失去可信度。
