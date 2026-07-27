# 实施追踪 v0.28.0

日期：2026-07-28

状态：实现与研究验证完成；基线和 Logistic 均不晋级

## 本版本完成

- 新增官方 ETHUSDT Spot 1m execution source Schema、校验器、owner-only
  原子发布、冲突拒绝与离线语义重建；
- 完成 42 个月来源，保存 1,560 个事件所需分钟，月度 ZIP 与 checksum
  共 84 个持久化 GET；
- 显式保留 `2023-03-24T12:39Z` 至 `13:59Z` 的 81 个官方来源缺口；
  1,560 个所需分钟与缺口零交集；
- 新增 9 个严格滞后特征、非重叠 LONG episode、1m 保守成交代理、tick/
  step、双边滑点和双边费用后的 event-based 标签；
- 新增固定 L2 Logistic、fit-only 标准化、calibration-only Platt 和
  8 折滚动 archive OOS 研究；
- 大型来源、数据集和预测留在仓库外 owner-only 目录；Git 只保存紧凑证据。

## 数据与研究结果

- 输入：ETH/BTC/Mark 4h 各 7,662 条，Funding 3,831 条；
- 数据集：780 个非重叠 LONG 事件，254 正、526 负；
- 全数据集成本后净收益率和：`-3.6300846247900`；
- OOS：419 个事件，简单基线净收益率和 `-2.213351088241`，
  非负季度 0/8；
- Logistic 接受 10 个，接受率 `2.3866%`，过滤后净收益率和
  `0.01189175183`；
- Logistic Brier `0.2308197381485137016755870239`，常数 Brier
  `0.2246781772401062022031641408`，仅 2/8 折更优；
- 结论：基线拒绝、Logistic 拒绝、XGBoost 不获授权。

完整紧凑证据见
[binance-causal-logistic-research-v0.28.0.json](../artifacts/ai-research/binance-causal-logistic-research-v0.28.0.json)。

## 独立审计

- 6 个真实事实前缀产生 104/212/321/422/524/780 个样本，所有已完成样本
  均与全量构建逐条一致；
- 同一真实数据集与 8 折配方完整训练/预测 100 次，输出 exact match；
- 独立新 Python 进程禁网重放 42 月执行来源、数据集与 Logistic：
  网络调用 0、语义原因 0、owner-only 权限异常 0；
- 三组 Schema 与 package mirror exact match；
- focused research tests：19/19；
- 全量 tests：485/485；
- Golden Vector：41；
- Evaluator build input：133；
- Build input tree hash：
  `a3f0df32a2a37dc1023d53617c023685ee8a3c6ac81799f8d76cc3c3a67a5cba`；
- Evaluator build hash：
  `4ccf91a0752a37a7ebb6303ecf067ea28b39ea4fc54910ee7a7485347dcc35e7`；
- `make validate` 完整执行成功；政策结果继续按设计为 `FAIL`，因为生产绑定
  未提供且生产激活关闭。

## 赚钱与 AI 含义

本版本没有证明赚钱。Logistic 的过滤后点估计略正，主要因为它拒绝了
409/419 个候选事件；接受事件只有 10 个，且概率预测差于常数模型。若只看
过滤后累计值，会把“几乎不交易”误包装成 AI 优势。

这次结果支持一个重要优化：AI 必须是已经赚钱的简单基线之上的增量过滤器，
不能拯救失败基线。下一步不增加 XGBoost，而是先重新设计简单趋势/突破候选
逻辑、成本预算与市场状态假设，并用新的预登记 trial 重新验证。

## 仍未满足

- archive 不能证明 PIT-valid 正式 OOS；
- 没有真实账户费率、真实成交/滑点或成功的真实 Futures context；
- 没有连续 90 天 context-complete Paper；
- 没有任何批准 ModelBundle、Canary 或真实资金资格；
- 当前没有 Broker、余额读取或下单能力。
