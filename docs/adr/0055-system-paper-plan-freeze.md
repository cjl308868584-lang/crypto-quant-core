# ADR-0055：冻结无凭据 System Paper 计划

日期：2026-08-01

状态：已接受

## 背景

原 Challenger cohort 已因漏槽永久失败并停用，但这不阻止独立建设 System Paper。现有
仓库已有确定性基线、公开行情、订单状态、账本、风险和调度原语，却没有能开始独立
90 天系统级模拟的不可变计划。若在模拟 Broker、成本、范围和权限尚可变化时启动计时，
最终经济结论会受到事后选择污染。

## 决策

1. System Paper V1 只允许 `BASELINE_ONLY`，固定 ETHUSDT Spot LONG-only、4 小时决策
   节奏和 90 个自然日；不允许通过构造参数改标的、路线或节奏。
2. 起始资本固定为 1000 USDT 虚拟权益，不允许外部现金流、借贷或杠杆。
3. 成本固定为单边 10bps 滑点和单边 15bps taker fee；Spot LONG-only 的 Funding 明确
   为不适用且为 0，不得人工覆盖。
4. 市场数据边界只包含冻结的公开 GET 请求族；计划不保存 URL、headers、secret、
   credential path、账户端点或订单端点。
5. 模拟成交、部分成交、拒绝/取消/超时/UNKNOWN、账本/持仓对账、RiskLock 与 kill
   switch 都被固定为后续 runtime 的必需能力，但本版本不实现或安装 runtime。
6. `credentials_allowed=false`、`account_requests_allowed=false`、
   `broker_requests_allowed=false`、`real_orders_allowed=false`、
   `production_activation=false`；计划构建与加载均不得发起网络或写运行状态。
7. 每个策略/数据/资本/成本/fill/风险分区都有独立 policy hash，外层再绑定稳定 plan id
   与 self-hash；严格 loader 拒绝重复键、float、未知字段、非规范字节、hash 和语义篡改。
8. 双镜像 JSON Schema 与 exact Git artifact 进入 evaluator build inputs；任何影响范围、
   成本、fill、风险或权限的实质修改必须创建新的 evidence scope，不能拼接旧证据。

## 后果

v0.55 只证明研究计划已冻结且无真钱权限，不证明模拟 Broker、System Paper runtime、
90 天连续运行、盈利、AI 优势或 Canary 资格。下一关键版本是 v0.56 的确定性模拟 Broker
与完整单槽 runtime；安装和开始计时必须等待后续 deployment/start-receipt 信任链通过。

计划文件固定为
`artifacts/system-paper/system-paper-plan-v0.55.0.json`，SHA-256 为
`05ade7d62d755c8dc3b003e41f8ac47975f441450146f8f4b6020b454fb81fda`。
