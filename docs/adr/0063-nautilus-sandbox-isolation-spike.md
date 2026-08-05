# ADR-0063：NautilusTrader 隔离 Sandbox 供应链预检

日期：2026-08-05

状态：已接受；本次结论为 `INCONCLUSIVE_BLOCKED`

## 背景

项目的差异化价值是 exact evidence、严格 loader、失败 ancestry、不可回填和
fail-closed 研究门。不再继续扩建通用回测、模拟 Broker、订单生命周期、交易所适配、
调度和通用 UI。NautilusTrader 是下一代候选，但 `1.227.0` 要求 Python 3.12+，
当前核心仍需 Python 3.9 兼容，因而必须为独立进程，不得导入核心。

## 决策

1. 候选版本锁定为 `nautilus_trader==1.227.0`，固定官方 tag/commit、macOS 15
   ARM64 CPython 3.12 wheel、SHA-256、LGPL-3.0-or-later license identity 和完整
   `uv.lock`。根包不增加 NautilusTrader。
2. 本版本在 frozen environment 供应链预检未完成后停止。不创建 runner、
   `BacktestEngine`、request/result 合同、fixture 或任何兼容性结果。不把未运行的
   协议伪装成已验证能力。
3. Git 只保留完整 dependency lock 和 preflight comparison/report。Evidence Adapter 必须
   重算并比较完整 lock，不得只接受一个 64 字符串。owner-only loader 使用
   同一 file descriptor 的 `open/fstat/read/fstat`，避免 path 级 TOCTOU。
4. 两次下载尝试只是会话观察；因为 exact transcript 和独立 attestation 均不可用，
   报告必须明示 `machine_replayable=false`，理由为
   `SUPPLY_CHAIN_FETCH_NOT_MACHINE_REPLAYABLE`。不得声称已有 exact failure receipt 或运行时
   failure suite。
5. 本次只能输出 `INCONCLUSIVE_BLOCKED / NONE_KEEP_CURRENT_CORE`。这不证明
   NautilusTrader 不适合，也不证明当前自研执行更好；只拒绝在证据不足时采用。
6. System Paper、replacement Challenger、v0.59、旧 Challenger failure/decommission
   和所有 90 天事实源完全不受影响；不迁移、回填、重置、改起点或更换事实源。
7. vectorbt 仅用于离线研究；Freqtrade 仅作独立对照；自研 Web 只保留项目独有的
   证据健康、槽位连续性和固定尾部视图。

## 后果

未来外部供应条件改变时，只能创建新的语义版本和新的预注册 Spike，不得改写
v0.63 或重跑以寻找更好结果。本版本不提高收益预期，不证明 Alpha、盈利、AI 优势、
Paper 完成、Canary 或实盘资格。
