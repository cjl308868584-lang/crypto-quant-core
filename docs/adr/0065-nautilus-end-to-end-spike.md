# ADR-0065：NautilusTrader 端到端隔离 Spike

日期：2026-08-22

状态：`INCONCLUSIVE_KEEP_CURRENT_CORE`

## 决策

保留 v0.65 首次正式结果，不重跑、不挑选结果，也不让 NautilusTrader 接管任何当前事实源。
正式比较的固定 reason 为 `NAUTILUS_V065_PLATFORM_MISMATCH`，`runner_invocation_count=0`。

正式命令由仓库文档中的 `python3` 启动；本机该解释器是 CPython 3.9，而预注册候选要求
CPython 3.12。平台门在任何下载 transcript 和 Sandbox runner 前失败关闭，因此没有安装
NautilusTrader，没有执行 decision/order/fill/fee/position/PnL 或 fresh-process 对照。

该结果不证明 Nautilus 不适配，不证明当前核心更优，也不证明任何盈利、AI 优势、Paper 或
实盘资格。它只证明 v0.65 的冻结 ceremony 没有进入引擎兼容性验证。

## 不变边界

- 当前 System Paper、replacement Challenger 和旧 Challenger 证据不迁移、不回填、不重置；
- `production_activation=false`，无凭据、Broker、订单、资金或 production state 写入；
- v0.65 plan 与首次 formal result 永久保留；任何未来重评必须使用新的预注册版本，不能覆盖 v0.65；
- v0.66 继续 replacement 的三阶段 append-only event runtime，不因本次 INCONCLUSIVE 扩建通用交易引擎。

## 公共 CI

仓库已公开。v0.65 使用标准 GitHub Actions：保留 Ubuntu Python 3.9/3.12 core matrix，并增加
`macos-15` arm64、Python 3.12 的独立只读证据重放。该 job 只验证提交后的 plan、formal sibling
files、completion marker、分类和 `runner_invocation_count=0`；不调用 ceremony、不下载或安装
NautilusTrader，也不制造新的研究结论。所有 Actions 固定到 commit SHA。

## 不采用的解释

不能把 `INCONCLUSIVE_KEEP_CURRENT_CORE` 改写为 `REJECT_KEEP_CURRENT_CORE`。本次没有引擎输出，
因此不存在可以支持 build-vs-buy、成交真实性或经济差异判断的观测证据。
