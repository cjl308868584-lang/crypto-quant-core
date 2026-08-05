# ADR-0063：NautilusTrader 隔离 Sandbox Spike

日期：2026-08-05

状态：已接受；本次采用结论为 `INCONCLUSIVE_BLOCKED`

## 背景

项目最有价值的能力是 exact evidence、严格 loader、失败 ancestry、不可回填和 fail-closed 研究门；
继续自研通用回测、模拟 Broker、订单生命周期、交易所适配、调度和通用 UI 会把投入从这些差异化
能力上移走。NautilusTrader 是成熟引擎候选，但 `1.227.0` 要求 Python 3.12+，而当前核心仍需
Python 3.9 兼容，且一个进程只能承载一个 engine/node 身份。

## 决策

1. v0.63 冻结独立 Python 3.12 one-shot sidecar 边界。当前核心只输出 fixed
   Decision/Target/Risk authorization；Nautilus 候选只能输出非权威 Order/Fills/Position/Fees
   observation；Evidence Adapter 只读比较。两套系统不得同时成为同一订单或持仓的事实源。
2. exact candidate 固定为 `nautilus_trader==1.227.0`、官方 tag/commit、macOS 15 ARM64 CPython
   3.12 wheel、SHA-256、LGPL-3.0-or-later license identity 和完整 `uv.lock` 传递 artifact hashes。
   根包与根 lock 不增加 Nautilus，继续支持 Python 3.9。
3. v0.63 只允许官方 PyPI 文件源。默认 frozen sync 在 `numpy==2.5.1` 下载上耗尽 uv 五次重试；
   同一来源、同一版本、同一 hash 的一次有界延长超时恢复在约 13 分钟无可靠进展后被终止。
   没有第三次尝试、换源、降版本或放宽 hash。
4. 因 frozen environment 未完整取得，本版本不创建 runner、不启动 `BacktestEngine`、不生成
   sandbox result、不执行 Golden 或 fresh-process replay。Evidence Adapter 只允许 exact
   `SUPPLY_CHAIN_FETCH_BLOCKED` evidence，并输出 `INCONCLUSIVE_BLOCKED`；Shadow 不合格。
5. fixture、current reference、directional request 和 comparison/report exact bytes 进入 Git。
   comparison 明确绑定 `sandbox_result_available=false`、零 runner/engine/credential/Broker/order/
   production-state counters 以及 `NONE_KEEP_CURRENT_CORE`。
6. System Paper、replacement Challenger、v0.59、旧 Challenger failure/decommission 和所有 90 天
   事实源完全不受影响；不迁移、回填、重置、改起点或更换事实源。
7. 从本版本起停止扩建通用模拟 Broker、通用订单/持仓生命周期、多 venue/交易所适配、通用 UI、
   调度/发布/机器人基础设施。现有实现只做必要安全或证据修复。vectorbt 仅用于离线研究；
   Freqtrade 仅作独立对照；自研 Web 只保留项目独有的证据健康、槽位连续性和固定尾部视图。

## 后果

本次结论不是 NautilusTrader 不兼容，也不是现有策略或项目失败；它只说明 v0.63 缺少完成采用判断
所必需的真实 wheel、Golden 与 replay 证据，因此必须保留当前核心并拒绝进入 Shadow。若未来外部
供应条件改变，只能创建新的语义版本和新的预注册 Spike，不得改写 v0.63 或反复重跑寻找更好结论。

本版本不提高收益预期，不证明 Alpha、盈利、AI 优势、Paper 完成、Canary 或实盘资格。
