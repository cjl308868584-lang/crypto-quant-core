# ADR-0001：Phase 0确定性核心边界

状态：Accepted
日期：2026-07-26

## 背景

《开发路线与验收门槛 v1.1》第9节要求第一个迭代先建立可信骨架，不训练AI，也不提供Broker下单能力。核心对象必须可规范化、哈希和重放，风险只能缩小目标；任一必需Policy未绑定时，Release Evaluator只能FAIL。

## 决策

1. 使用Python 3.9+单进程包作为V1领域内核。
2. 审计Payload禁止binary float；交易、账本和风险边界使用Decimal规范字符串。
3. 业务ID仅从规范化业务字段派生，不读取墙钟或随机数。
4. 首个账本使用SQLite WAL、不可变events、哈希链、Outbox和最小经济投影。
5. Release Evaluator直接读取v1.1机器政策；未知metric/estimator、缺少条件、缺少binding或未支持阈值类型全部Fail-Closed。
6. 本版本不定义Broker、交易所密钥或外部下单方法。

## 不变量

- 不修改v1.1机器政策中的数值、路线、比较符和Fail-Closed语义。
- `StrategyProposal → MetaDecision → TargetPosition → RiskDecision → ExecutionIntent`链路不得被绕过。
- 事件至少一次到达，经济投影恰好一次。
- 回撤阈值只能从ReleaseGatePolicy读取。
- `production_activation.enabled=false`时不能产生生产PASS。

## 备选方案

- 直接采用完整交易框架：暂缓。它会在契约稳定前引入Broker能力和框架专有类型。
- 使用float并在展示时舍入：拒绝。无法满足逐次重放和会计确定性。
- 先连接Binance Testnet：拒绝。交付物明确要求首个迭代没有Broker能力。

## 后果

- 初期代码刻意只覆盖确定性内核，订单状态机、InstrumentMetadata和完整RiskGate将在后续增量补齐。
- JSON Schema验证只依赖基础`jsonschema`；date/date-time使用项目内的严格检查器，避免为当前未使用的格式引入额外依赖。CI使用`requirements.lock`，每次升级都必须复核全部传递依赖许可证。
- SQLite投影可以删除后从events完整重建；events本身不可更新或删除。

## 验证证据

- 实现：`src/crypto_quant/`
- 配置验证：`scripts/validate_release_config.py`
- 自动化测试：`tests/`
- CI：`.github/workflows/ci.yml`
