# ADR-0040：经济结果只能由完整可信输入自动派生

日期：2026-07-29

状态：Accepted

## 决策

首个 Challenger episode 的真实研究经济结果只能由 v0.40 CLI 发布。CLI 必须依次
重载 v0.37 exact plan、v0.36 completed receipt 和 v0.39 全部 verified daily
archives，再调用 v0.38 evaluator、exact publisher 与 loader。

调用方只能提供这些证据和 owner-only 输出根的绝对路径。日期、symbol、执行分钟、
OHLC、价格、数量、滑点、费用、资本、PnL、标签、结果 ID、文件名、strategy state
和订单参数都不能覆盖。

`evaluated_at` 固定取 archive receipts 中最大的 `retrieved_at`，输出名固定为
`result_id.json`。同一输入重复运行必须得到相同路径和 exact bytes。

## 理由

评估器本身虽然严格，但若真实运行仍需人工抄写价格、时间、收益或输出身份，就会重新
引入选择性报告和不可重放操作。将 loader、派生、计算、发布与重载固定在一个离线入口，
才能确保结果完全由事前计划、前向完成凭据和官方日档决定。

## 后果

- archive 集不完整、权限不安全、存在 symlink 或 exact 文件冲突时失败关闭；
- CLI 没有 HTTP transport、Runner、Broker、余额、订单或 state write 能力；
- 正收益仍仅是单 episode 的保守执行代理，不证明可重复盈利；
- 真实结果必须在 episode 完成且日档发布后作为独立版本封存；
- AI 比较仍需同事件配对的独立前向样本，不能从本结果推断。
