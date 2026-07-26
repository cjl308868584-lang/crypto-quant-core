# 虚拟货币量化策略系统计划 v1.1

状态：设计基线
日期：2026-07-26
适用范围：个人账户、200–1,000 USDT 初始资金、Binance 优先、ETH 4H
发布评估：[发布评估与证据规范 v1.1](release-evaluation-spec-v1.1.md)

## 1. 目标与成功定义

### 1.1 一句话目标

在不突破硬风险边界的前提下，最大化扣除交易费、资金费、滑点、基础设施、数据和 AI 推理费用后的长期复合增长。

### 1.2 “赚钱”在本项目中的准确含义

本项目不以回测收益最高、预测准确率最高或交易次数最多为目标。成功必须同时满足：

1. 封存样本和前向样本中存在成本后正收益证据。
2. 收益不是由单一行情、单一折或少数交易贡献。
3. Paper 与 Live 的信号、成交和成本偏差可解释。
4. 回撤、尾部损失和停机规则始终受确定性风控约束。
5. 固定运营成本没有吞掉小资金账户的交易收益。
6. 任意交易和模型决策均可追溯、重放和解释。

核心经济口径：

```text
fill_based_gross_pnl
  = side_sign × (exit_fill_price - entry_fill_price)
    × filled_quantity × contract_multiplier

trading_net_pnl
  = fill_based_gross_pnl
  - exchange_fees
  + signed_funding_cashflow

economic_pnl
  = trading_net_pnl
  - infrastructure_cost
  - paid_data_cost
  - ai_inference_cost
  - recurring_training_and_monitoring_cost
```

成交价已经包含买卖价差和滑点，因此不得再次从 `trading_net_pnl` 中扣除。系统另行报告相对决策参考价的 `implementation_shortfall`，用于解释执行质量。`signed_funding_cashflow > 0` 表示账户收到资金费，`< 0` 表示账户支付。

系统同时报告：

- 变量交易成本后的 `trading_net_pnl`；
- 分摊固定运营成本后的 `economic_pnl`；
- 相对参考价的执行偏差；
- AI相对同一Proposal基线的配对增量。

只有批准全风险规模下的月度 `economic_pnl` 一侧95%保守下界为正，才能声称项目在经济上赚钱。小额Canary可以被视为有预算上限的验证支出，不能仅凭其短期PnL宣称盈利。

所有收益门必须绑定同一版本化AccountingPolicy、CostAllocationPolicy、批准生产资本、方向和评估窗口。期间收益、未平仓保守估值、部分成交成本基础和AI/基线成本分摊以《核心数据契约与订单状态机》为准；不同资本或窗口的结果不得互相替代。

### 1.3 V1 的目标优先级

1. 不发生不可解释的重复下单、仓位漂移或失控风险。
2. 证明简单基线在保守成本模型下是否存在可交易性。
3. 证明 AI 相对简单基线是否带来稳定的增量价值。
4. 用极小资金验证 Paper 与 Live 的现实差距。
5. 在证据不足时保持空仓，而不是强行交易。

## 2. 已锁定范围

### 2.1 市场和账户

- 第一交易所：Binance。
- 第二交易所：Gate，只有在 Binance V1 稳定后通过独立 Adapter 接入。
- 永续账户模式：单向持仓、逐仓；现货不使用保证金。
- 最大杠杆：多空均为 1x。
- 初始资金：200–1,000 USDT。
- 资金低于 1,000 USDT：仅 ETH 允许实盘；BTC 仅作为市场状态特征和 Paper 对照。
- 产品：ETH/USDT 现货与 ETHUSDT 永续。
- V1 固定表达方式：LONG 默认使用 ETH/USDT 现货，SHORT 使用 ETHUSDT 逐仓永续；不根据 Funding 临时切换交易载体。
- 现货和永续合并计算 ETH 经济敞口，禁止同时持有互相对冲但增加费用的多空仓位。
- 多头和空头视为两个独立经济假设，分别研究、晋级和停用。

### 2.2 时间尺度

- 决策周期：4H K 线闭合后。
- 预测/标签视野：未来 24H。
- 正常最短持有：8H。
- 设置反手滞回和 no-trade band，禁止模型在阈值附近频繁翻转。
- 4H 负责决策；1m 或更细的 BBO/成交数据负责关键区间的保守成交重放。

### 2.3 V1 数据

正式数据：

- OHLCV；
- Mark Price、Index Price、Premium Index；
- Funding Rate；
- Open Interest；
- Taker Buy/Sell 或可获得的主动买卖指标；
- Binance 合约规格、费用、tick size、step size、min notional；
- 账户余额、持仓、订单和成交事件。

Shadow 数据：

- 新闻；
- 公告；
- 社交媒体；
- LLM/文本模型输出。

所有数据必须至少保留：

- `event_time`：事件在市场中发生的时间；
- `available_at`：策略在当时最早可合法使用该信息的时间；
- `ingested_at`：系统实际接收时间；
- `recorded_at`：系统将规范化事件写入账本的时间；
- `source`、`schema_version` 和内容哈希。

现货快照可以引用永续Mark/Index/Funding/OI作为市场上下文，但必须标记 `CONTEXT_ONLY`；这些字段对现货订单本身不是产品必填字段。产品必填矩阵由版本化 `DataQualityPolicy` 决定，不能用一套永续字段要求错误地阻止现货交易。

### 2.4 合规与资金边界

- 只在账户持有人依法可访问、符合交易所条款和身份/地区限制的环境运行；系统不提供绕过地区、KYC或监管限制的功能。
- 实盘资金必须是可承受全部损失的自有风险资本，不借款、不使用生活必需资金。
- 上线前由账户持有人确认所在地的税务、申报和衍生品适格要求；未确认时保持Paper。
- 系统保存成交、Funding、费用、估值和外部现金流记录以支持申报；策略报告默认税前，另做版本化税后情景，不用假定税率美化Alpha。
- 任何法律、账户条款或交易资格变化都触发合规锁，禁止新增风险，不能由模型覆盖。

## 3. 核心策略假设

### 3.1 两条 Champion 路线

```text
BASELINE_ONLY
  简单趋势/突破规则
  → 确定性NO_AI_BASE
  → 离散目标仓位
  → 确定性风险覆盖

AI_ENHANCED
  简单趋势/突破规则
  → 产生高召回方向信号
  → 已通过增量门的Meta模型判断是否值得交易
  → 通过独立门槛后才启用的分位数/不确定性组件
  → 离散目标仓位
  → 确定性风险覆盖
```

两条路线都可以成为Champion；只能选择一条作为某个方向的当前正式部署线。基础策略负责方向，AI 不重新发明交易方向。`AI_ENHANCED` 中AI的任务是：

- 拒绝低质量交易；
- 估计扣除成本后的正收益概率；
- 估计收益分位数和不确定性；
- 将合格机会映射到有限风险档位。

### 3.2 Challenger

- 趋势方向一致的回撤入场：正式 Challenger。
- 纯均值回归：只做 Shadow，未独立通过全部门槛前不得与 Champion 混合。
- TabPFN v2、Chronos-2 或后续基础模型：只做发布后的前向 Shadow；许可证、训练截止日和权重来源必须可追溯。
- 新闻/社媒模型：只输出结构化研究特征，不直接输出订单或仓位。

### 3.3 明确排除

- 端到端强化学习交易；
- LLM 猜下一根 K 线涨跌；
- 多 Agent 投票后直接买卖；
- 高频自动重训并自动替换 Champion；
- 自动扩展到数千或上万特征；
- 无限制 Hyperopt/AutoML 搜索。

## 4. 系统分层

```text
Point-in-time MarketSnapshot
    → FeaturePipeline
    → BaseStrategy
    → StrategyProposal
    → MetaDecision
    → PositionPolicy
    → TargetPosition
    → DeterministicRiskGate
    → ExecutionPlanner
    → OrderStateMachine
    → ExchangeAdapter
    → ExecutionReport
    → Ledger / PortfolioProjection
    → Reconciliation
```

### 4.1 分层不变量

1. `BaseStrategy` 只能输出 `StrategyProposal`，AI或确定性 `NO_AI_BASE` 只能输出 `MetaDecision`，只有 `PositionPolicy` 可以据此产生正式 `TargetPosition`；三者均不能调用交易所 API。
2. 风险层只能保持或缩小目标敞口，不能放大。
3. 风险限制不可由模型、Prompt、配置热更新或 Agent 修改。
4. 执行层不理解预测，只负责安全达到风险批准后的目标。
5. 交易所是订单、成交和实际持仓的最终权威来源。
6. 本地账本是可重放的事实记录，不是交易所真相的替代品。
7. 回测、Paper 和 Live 使用同一个 Decision Kernel；只替换时钟、数据和执行 Adapter。
8. 超时代表 `UNKNOWN`，不代表订单失败；未经查询和对账禁止重发。
9. `MetaDecision` 可以是模型输出，也可以是经过独立批准的确定性 `NO_AI_BASE`；不得使用空字段暗示绕过AI。
10. RiskGate必须消费交易所实际仓位、活动订单和账户权益的 `PortfolioRiskSnapshot`，不能只比较模型目标。

### 4.2 规划模块目录

```text
src/crypto_quant/
  domain/                 # 值对象、事件、契约、状态机
  config/                 # 版本化配置和环境校验
  data/
    collectors/           # Binance 市场和账户数据
    point_in_time/        # event_time/available_at/ingested_at 处理
    quality/              # 完整性、新鲜度、重复和跳变检查
    storage/              # Raw Parquet、快照和元数据
  features/               # 训练/回测/实盘共用的唯一特征实现
  strategies/
    trend_breakout/       # V1 基线
    pullback/             # Challenger
    mean_reversion/       # Shadow
  ai/
    datasets/             # Event-based Meta 样本
    models/               # Logistic、XGBoost、Quantile
    calibration/          # 概率校准
    eligibility/          # 模型/数据/OOD 资格判定
    registry/             # Experiment、Model、Deployment Timeline
  portfolio/              # 离散目标仓位和滞回
  risk/                   # 不可绕过的确定性风险层
  execution/
    planner/              # 目标仓位到订单计划
    oms/                  # 订单状态机和幂等
    adapters/binance/     # Binance Spot/USDM
    reconciliation/       # 启动、周期和异常对账
  backtest/
    event_engine/         # 与 Live 同事件语义
    fill_models/          # 费用、滑点、延迟、成交概率
    detail_replay/        # 1m/BBO 关键路径重放
  operations/
    scheduler/            # 4H 决策、月度训练
    monitoring/           # 数据、模型、风险、订单指标
    alerts/               # 事故告警和每日摘要
  research/               # 受控实验入口，不接触交易密钥

tests/
  unit/
  contracts/
  replay/
  leakage/
  fault_injection/
  integration/
  exchange_testnet/

artifacts/
  experiments/            # 不可变实验 Manifest 和报告
  models/                 # 本项目训练的安全模型文件
  predictions/            # OOS/Shadow 逐时点预测

docs/
  decisions/              # 决策记录
  runbooks/               # 停机、恢复、事故和密钥轮换
```

目录是边界约束，不要求 V1 一次性创建全部实现。

## 5. 数据和特征原则

### 5.1 单一特征来源

训练、回测、Paper 和 Live 必须调用同一份特征函数。每次推理保存：

- 数据截止时间和 watermark；
- 特征 schema/version/hash；
- 特征值或可重建快照；
- 缺失掩码；
- 模型版本；
- 决策结果。

离线重放与实时快照逐字段不一致时，该模型不能晋级。

### 5.2 数据质量门

以下任一情况禁止新增风险：

- 4H K 线未闭合；
- 关键数据超过允许延迟；
- 时间戳逆序或重复且无法解释；
- Mark/Index/Last Price 差异异常；
- 当前产品在 `DataQualityPolicy` 中声明的必需字段缺失；
- 合约规格或费用版本未知；
- 特征 schema 与模型不匹配；
- 系统时钟未同步。

### 5.3 存储

- 原始市场数据：追加式、分区 Parquet。
- 订单、成交、余额、风险和决策事实：SQLite WAL 追加日志。
- 实验和部署元数据：SQLite/结构化 Manifest。
- 模型：优先使用 XGBoost JSON/UBJ 等安全原生格式。
- 不加载不可信来源的 pickle/joblib 模型文件。
- 全部业务时间使用 UTC；UI 可以转换为 Asia/Shanghai。

## 6. 回测和验证架构

### 6.1 时间切分

- 初始及例行训练窗：滚动18个月。
- Walk-forward：8个季度OOS折，每折使用紧邻其前的18个月训练数据。
- 每个训练窗内部保留末段时间作为独立校准区；模型拟合区与校准区之间同样执行Purge/Embargo。
- 每折的绝对起止时间、校准区、数据哈希和时区写入不可变 `SplitPolicy`。
- 最后12个月：初始 `RecipeRelease` 的一次性封存审计集。
- 标签跨度24H；每个边界实施Purge + Embargo，长度不得短于标签和执行模拟的最大影响区间。
- 多头和空头单独生成报告。

初始封存审计只认证冻结的经济配方，不意味着同一个权重文件永久有效。配方不变的月度重训按Minor协议发布；经济逻辑变化的Major版本必须使用发布后预先保存的前向预测形成新审计证据，不能反复使用已暴露的12个月。

### 6.2 成交现实性

基础回测必须包含：

- Maker/Taker 费用；
- Funding；
- Bid/Ask Spread；
- 保守滑点；
- 下单延迟；
- tick/step/min-notional 舍入；
- 订单拒绝、部分成交和超时；
- 资金不足和逐仓约束。

4H 收盘只产生决策，不能在同一收盘价无滑点成交。关键入场、退出、止损和反手区间必须使用 1m/BBO 明细重放。

### 6.3 强制审计

每次候选发布必须通过：

1. Prefix-vs-full 差分未来函数检查。
2. 不同 warm-up 长度的递归稳定性检查。
3. 离线特征与实时特征 parity 检查。
4. Freqtrade 独立基线的逐决策对照。
5. 成本上调、延迟上调和成交恶化压力测试。
6. Moving-block bootstrap 脆弱性分析。
7. DSR/PBO 和总试验次数审计。

第三方框架只作为独立审计器，不作为收益真值。

## 7. AI 决策规则

### 7.1 V1 模型

- 可解释基准：Logistic Regression。
- 主候选：XGBoost 二分类 Meta 模型。
- 收益分布：样本与覆盖率门通过时，独立Quantile模型输出q10/q50/q90；否则只留Shadow诊断，不进入硬仓位映射。
- 概率校准：时间序列 OOS 校准器。
- Regime：以可解释规则或轻量模型产生风险状态，不直接产生订单。

分类目标：

```text
P(net_return_24h > 0 | base_signal, point_in_time_features)
```

回归目标：

```text
net_return_24h
  = (fill_based_gross_pnl
     - exchange_fees
     + signed_funding_cashflow)
    / label_reference_notional_usdt
```

Spread和Slippage已反映在Entry/Exit Fill中，仅作为Implementation Shortfall归因，不再重复扣除。

`label_reference_notional_usdt`由LabelPolicy按基础Proposal的统一全风险参考名义金额冻结；它不随AI接受/拒绝或风险bucket改变。Portfolio/economic gate使用另行冻结的批准生产资本。

### 7.2 Prediction Eligibility

每次预测先经过资格判定，至少覆盖：

- `STALE_MODEL`
- `MISSING_FEATURE`
- `DATA_STALE`
- `OUT_OF_DISTRIBUTION`
- `MODEL_DISAGREEMENT`
- `CALIBRATION_FAILED`
- `UNCERTAINTY_TOO_HIGH`
- `FEATURE_SCHEMA_MISMATCH`
- `RISK_LOCKED`

严重原因出现时，AI 输出 `FREEZE_INCREASES`，而不是用风险档位0暗示立即平仓；只有日损、15%回撤等硬风险原因才能输出 `FLATTEN`。OOD 样本不得从训练集中简单删除；崩盘、跳空和极端 Funding 是重要风险样本。

### 7.3 仓位映射

原始概率不得线性映射为仓位。`PositionPolicy` 根据以下信息输出 0/25/50/75/100%：

- 校准后的净正收益概率；
- 预期净收益下置信界；
- q10/q50/q90；
- OOD 和不确定性；
- 当前波动率与 12% 年化波动目标；
- 最短持有、滞回和 no-trade band；
- 当前风险状态。

PositionPolicy明确输出 `HOLD_CURRENT/FREEZE_INCREASES/REDUCE_TO/SET_TARGET/FLATTEN`。风险层可以进一步限制动作或降档，但不能升档。

风险档位表示“波动率目标计算出的基础风险预算比例”，不是账户余额比例。初始计算关系为：

```text
base_exposure
  = min(1.0, target_annual_vol / max(estimated_annual_vol, target_annual_vol))

model_exposure
  = base_exposure × risk_bucket / 100

stage_capped_exposure
  = model_exposure × authoritative_stage_multiplier

live_abs_exposure
  = min(stage_capped_exposure,
        deterministic_risk_cap,
        available_equity_cap,
        leverage_cap)

live_signed_exposure
  = direction_sign × live_abs_exposure
```

其中：

- `target_annual_vol = 12%`；
- `risk_bucket` 是整数百分数 `0/25/50/75/100`，进入公式时必须除以100；
- `estimated_annual_vol` 的算法、窗口和年化方式必须版本化，并在 Release Audit 前冻结；
- Canary的0.25/0.50/0.75/1.00 multiplier由RiskGate从只读Deployment Registry独立读取并乘在模型/基线建议敞口上，不能信任TargetPosition自报；
- 最终结果继续受 1x、可用权益、交易所最小名义金额和 RiskGate 限制；
- 数量取整只能降低风险，不能为了达到最小下单金额向上放大。

### 7.4 持仓状态语义

- 空仓时的普通合格Proposal可以建立新目标。
- 持仓后的前8H，普通新信号只能 `HOLD_CURRENT` 或向风险更小方向 `REDUCE_TO`，不能反手；日损、回撤、灾难止损、数据/执行事故可以覆盖最短持有并 `FLATTEN`。
- 8H后允许普通退出；反手仍必须先平旧载体、确认交易所实际敞口为零，再开新方向。
- 24H是标签和默认最大策略持有边界；到期时由同一PositionPolicy产生明确退出/续持决定，不能只在标签中退出而Live继续持有。
- 持仓期间每4H仍记录Proposal，但只有会改变批准敞口的决策计入AI增量配对样本。
- 标签生成、回测、Paper和Live必须调用同一个状态机，不能把重叠Proposal当作彼此独立的满仓交易。

## 8. 配方与模型生命周期

系统区分：

- `RecipeRelease`：特征、标签、模型族、超参数配方、校准、阈值、仓位映射、成本和风险接口的冻结经济逻辑；
- `ModelBundle`：按该配方和指定数据截止时间训练出的具体权重、预处理器和校准器；
- `DeploymentLine`：某个RecipeRelease当前所处的Paper/Canary/Champion阶段。

```text
RECIPE_CANDIDATE
  → SHADOW
  → PAPER
  → CANARY_25
  → CANARY_50
  → CANARY_75
  → CHAMPION
  → RETIRED
```

- Initial/Major RecipeRelease必须走完整Shadow、Paper和Canary。
- 同一冻结配方的月度从零重训属于Minor ModelBundle刷新；经数据质量、滚动OOS、Golden Snapshot和至少7天并行Shadow非劣检查后，可以在当前DeploymentLine内原子替换权重，不重置已完成的Paper/Canary日历证据。
- release route、主终点、基础Proposal、配方、特征、标签、模型族、搜索空间、校准方法、阈值、Position/RiskPolicy、执行/Fill模型、数据源或成本/Accounting定义变化均为Major，创建新DeploymentLine并重新走完整流程。
- 模型年龄从具体ModelBundle的训练数据截止时间计算；DeploymentLine可以在187天验证期间使用兼容Minor Bundle持续刷新。
- Warm-start/continual learning 只能进入 Shadow。
- 训练完成不等于上线。
- 每个拟替换Bundle至少前向Shadow 7天。
- 系统级 Paper 至少 90 天。
- 25/50/75% Canary 各至少 30 天，并独立通过阶段门。
- 模型切换必须原子完成，保留 Last-Known-Good。
- 模型过期时禁止新增风险，但不得因此无序平仓；由确定性风险和执行策略处理现有仓位。

完整规则见《AI 研究与模型治理 v1.1》。

## 9. 硬风险政策

### 9.1 账户级限制

- 目标年化波动率：12%。
- 日内损失限制：2%，按账户权益的已实现与未实现损益统一计算。
- 最大杠杆：1x。
- USDT永续使用单向、逐仓、杠杆不超过1x；现货不借币、不使用保证金。
- 不允许模型提高任何硬限制。

1x按“所有风险增加型活动订单都完全成交后的最坏毛敞口”计算，而不是按可被多空抵消的净敞口：

```text
worst_case_gross_exposure_usdt
  = current_spot_abs_notional
  + current_perp_abs_notional
  + sum(risk_increasing_active_order_max_fill_notional)

effective_leverage
  = worst_case_gross_exposure_usdt / marked_equity
```

reduce-only订单和不超过已有现货数量的保护性Sell不增加上式；无法证明订单只减仓时，按增加风险计。`effective_leverage <= 1.00`，且净ETH敞口仍必须满足方向和批准目标上限。禁止用现货与永续反向仓位互相抵消后声称低于1x。

日内损失按 UTC 自然日计算：

```text
daily_loss
  = (current_marked_equity
     - start_of_day_equity
     - net_external_cash_flow)
    / start_of_day_equity
```

达到 -2% 时：

- 取消未成交的新增风险订单；
- 目标风险降至零，并使用 reduce-only/保护性退出有序处理现有仓位；
- 激活 `DAILY_LOSS` 风险锁；
- 最早在下一个 UTC 自然日、完成清洁对账后才允许解除；
- 如果损失与执行、数据或安全事故有关，必须人工解除。

权益高水位和回撤也必须扣除充值、提现和内部划转影响，避免把外部现金流误判为收益或亏损。

### 9.2 回撤状态

| 从权益高水位回撤 | 状态 | 系统动作 |
|---|---|---|
| <10% | NORMAL | 按批准风险档位运行 |
| 10%–<12% | WARNING | `cap=min(当前实际风险, 原批准风险)`；禁止增加，只允许持有或减仓 |
| 12%–<15% | REDUCE | 继承WARNING；`cap=min(当前实际风险, 原批准风险×50%)`，只允许reduce-only |
| 15%–<20% | HALT | 目标风险为零，有序退出并停止自动交易 |
| ≥20% | HARD_BOUNDARY | 重大事故；目标为零，不得自动重启，必须人工复盘和重新审批 |

解锁带滞回：

- WARNING：回撤回到8%以下连续7天、系统健康和对账清洁后才可解除；
- REDUCE：回撤回到10%以下连续14天，并人工批准；
- HALT/HARD_BOUNDARY：完成事故复盘、重新通过至少30天Paper后，最多从CANARY_25重新开始；
- `BLOCK` 永远不能阻止保护性退出或风险缩减。

### 9.3 交易所保护

- 永续仓位支持时使用交易所原生 reduce-only 灾难止损。
- 现货多头使用交易所支持的保护性卖出止损；若只能使用止损限价，必须配置保守穿价区间，并由独立 Watchdog 在失效时执行紧急市价退出。
- 本地策略止损不能替代交易所灾难止损。
- 止损被取消、拒绝或规格失效时立即告警并进入风险锁。
- API 密钥仅授予读取与交易权限，禁止提现；使用 IP 白名单和独立环境密钥。

## 10. 执行和对账

### 10.1 订单原则

- 每个 Decision、Intent 和 Order 拥有稳定唯一 ID。
- 同一意图重复处理不得产生第二份经济订单。
- HTTP/WS 超时进入 `UNKNOWN`。
- `UNKNOWN` 必须按 client order ID、open orders 和 recent trades 查询。
- 部分成交后按最新实际仓位重新计算剩余量。
- 剩余量低于 min notional 时记录为 dust，不无限追单。

### 10.2 启动和重连

1. 锁定新增订单。
2. 重放本地追加日志和最近快照。
3. 查询交易所余额、持仓、活动订单和高水位后的成交。
4. 按 client order ID 与 trade ID 去重合并。
5. 生成明确的 ReconciliationResult。
6. 差异未解决时保持停机。
7. 状态一致且风险门允许后才恢复决策。

4H 系统无需高频轮询，但至少在每次启动、重连、`UNKNOWN`、订单终态以及每 5–15 分钟执行一次轻量对账。

## 11. 可观测性与事故处理

必须监控：

- 数据延迟和缺失；
- 特征/模型 schema；
- PredictionEligibility；
- 当前 TargetPosition 和 RiskState；
- 订单状态、部分成交、拒单和 UNKNOWN；
- 本地与交易所仓位差异；
- 实际费用、Funding 和滑点；
- Paper/Shadow/Live 决策偏差；
- 权益、日损、回撤和高水位；
- 固定运营成本及经济 PnL。

必须即时告警：

- 对账差异；
- 重复成交或疑似重复订单；
- 交易所止损缺失；
- 日损或回撤越线；
- 数据/模型过期；
- 密钥、权限或时钟异常；
- 无法解释的手工仓位。

事故处理原则：先停止新增风险并保存证据，再决定减仓或停机；不得让自动重训掩盖执行事故。

## 12. 开源借鉴边界

本项目采用 clean-room 方式借鉴架构：

- Freqtrade/FreqAI：防泄漏、模型过期、预测留档、交易所止损。
- Jesse：Primary Signal + Meta Labeling。
- Hummingbot：Controller → Executor。
- NautilusTrader：事件、订单状态机、固定点精度、对账和重放。
- LEAN：Alpha/Portfolio/Risk/Execution 契约。
- FinRL：训练/验证/交易环境分层，以及RL只留Shadow研究的反例边界。
- Qlib：Experiment Recorder 和 Deployment Timeline。
- vn.py：Gateway/App 与集中风险拦截。

不直接复制 GPL/AGPL 实现。所有未来引入的第三方代码必须登记仓库、版本、许可证、修改和分发义务。

逐项目来源、具体借鉴点、不采用项和许可证边界见[《开源项目参考与取舍 v1.1》](open-source-reference-notes-v1.1.md)。

## 13. Go/No-Go 总原则

真钱放行有两条互斥路径：

- `BASELINE_ONLY`：简单基线独立通过其统计、Shadow、Paper、Canary和运行门；AI指标不适用。
- `AI_ENHANCED`：简单基线先通过，AI再通过配对增量门以及同样的Shadow、Paper、Canary和运行门。

以下任一条件成立，不得进入对应真钱路径：

- 简单基线在封存样本中没有成本后正收益证据；
- AI_ENHANCED路径中，AI没有通过预声明的增量或风险效率门；
- 未来函数、特征 parity 或可重放性检查失败；
- 订单 UNKNOWN、部分成交或重启对账未通过故障测试；
- Paper 与模拟之间存在无法解释的偏差；
- 风险锁可被策略、AI 或配置绕过；
- 运营成本高于预期交易收益；
- 任何封存数据已被 Agent 或研究者用于反复选择模型。

如果AI失败但简单基线通过，只允许走 `BASELINE_ONLY`；如果简单基线失败，则保持空仓并回到经济假设，不用更复杂模型掩盖问题。阈值以版本化 [ReleaseGatePolicy v1.1](../config/release-gates-v1.1.json) 为准，指标与证据求值以其绑定的Metric Catalog和《发布评估与证据规范》为准。

## 14. 交付顺序

1. 契约、风险政策、事件日志和测试骨架。
2. 点时数据管线与数据质量门。
3. 确定性回测、1m 明细重放和简单基线。
4. 订单状态机、Binance Adapter、对账和故障注入。
5. AI 数据集、Logistic/XGBoost、校准和实验注册。
6. Shadow 与独立审计。
7. 90 天 Paper。
8. 25/50/75% Canary，各 30 天。
9. 满足全部门槛后才成为 Champion。

完整阶段验收见《开发路线与验收门槛 v1.1》。
