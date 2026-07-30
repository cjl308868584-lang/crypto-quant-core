# v0.43 Challenger 多 Episode Cohort 注册设计

日期：2026-07-30

状态：冻结

## 1. 目标

在第二个 Challenger Episode 开始前，冻结一个不允许挑选样本、按短期 PnL 停止或
事后修改窗口的多 Episode cohort。它用于回答简单 Challenger 是否值得继续研究，
不启动 AI、不开放 Broker，也不把 90 天观察冒充系统级 Paper。

## 2. 已暴露结果与时间边界

设计时已知首个 Episode 的 v0.42 研究经济代理为负：

- entry：`2026-07-29T00:00:00.000Z`；
- exit：`2026-07-29T16:00:00.000Z`；
- net PnL：`-23.4627746535 USDT`；
- net return：`-0.0234627746535`；
- result file SHA-256：
  `8627677275c31de573f1a59f638ba1678772115dc6d932027a36e2f8b62d9fee`。

该结果必须永久保留为 `EXPOSED_PILOT_MANDATORY_ALL_STREAM`，不得因负值删除，也
不得伪装成结果前注册的 confirmatory 样本。

截至设计时，首个退出后的四个槽位全部为 `REJECT_ENTRY`，尚未开始第二个 Episode。
Future-only confirmatory cohort 固定为：

- start inclusive：`2026-07-30T12:00:00.000Z`；
- end exclusive：`2026-10-28T12:00:00.000Z`；
- duration：90 个完整自然日；
- slot cadence：UTC 4h；
- entry 在窗口内的 Episode 必须跟踪到自然退出，即使退出发生在 end 之后；最后
  允许的观察尾部固定为 end 后 24h。

## 3. Cohort 纳入规则

- 固定策略：
  `SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2`；
- policy hash：
  `2ef83c7c73fff8b163d9bad8527921bd0d87e60595680236e936254536c800e4`；
- registration hash：
  `885b33d3a91eae1d5822fe12c16773a446c23e702f9a4110ef32f474157fa27f`；
- route / direction / venue：
  `BASELINE_ONLY / LONG / BINANCE_SPOT`；
- primary endpoint：`GROWTH`；
- 所有 entry slot 位于 `[start, end)` 的 `ENTER_LONG` Episode 全部纳入；
- `REJECT_ENTRY` 不是经济 Episode，但必须保留以证明 4h 流连续且没有跳过不利
  候选时点；
- 每个 Episode 只使用冻结的 next-strict-UTC-minute 执行代理、10bps 双边滑点、
  15bps 双边 taker fee、1000 USDT 参考资本和既有 Decimal 舍入；
- 禁止人工传入日期、价格、费用、收益、label、Episode ID 或结果文件名。

## 4. 停止与报告规则

- 不因正、负 PnL、胜率、回撤或主观市场判断提前结束；
- 不允许在同一 cohort 内延长窗口、重置起点或重新开始 90 天；
- 若任一必需槽位 missed、发生不可解释 revision、state/log/bundle 不连续或
  trust binding 失败，confirmatory cohort 失败关闭，禁止回填；
- 90 天结束时样本、有效样本、完整月份、功效、CI 宽度或区块不足，一律
  `INCONCLUSIVE`，不得用点估计晋级；
- 中途只允许发布 completeness/operations 状态；任何 interim PnL 都必须标记
  `DESCRIPTIVE_NO_EARLY_SUCCESS`，不能形成盈利 PASS；
- 首个已暴露 pilot 与 future-only confirmatory 结果必须分栏报告，同时提供包含
  二者的 all-stream 描述，不能只展示更有利的一栏。

## 5. AI 边界

本 cohort 只验证简单基线。AI 训练、模型筛选和行为改变型 shadow 均不属于
v0.43；简单基线未在正式完整门上通过前，AI 不得用来掩盖失败。

若未来进入 `AI_ENHANCED`，必须在结果出现前另行冻结模型、候选事件、两套独立
经济账本、同 `proposal_id + decision_time` 配对、主终点、功效、CI 和 Holm
family。首个 pilot 或本 cohort 的后见信息不能被包装为 AI confirmatory 证据。

## 6. v0.43 交付

本版本新增：

- cohort plan Schema 及 package mirror；
- deterministic plan builder、loader 和自哈希；
- committed canonical plan artifact；
- 对窗口、known pilot、策略绑定、纳入/停止/报告/AI 边界的回归；
- ADR、实施追踪、版本与构建清单。

本版本不读取新的市场数据、不触发 Runner、不观察未来槽位、不产生第二个 Episode
receipt 或经济结果。发布必须在
`2026-07-30T12:00:00.000Z` 第二 cohort 起始槽位之前完成设计冻结提交；即使代码
发布稍后完成，该设计提交也必须早于起始槽位。

## 7. 验收

- plan canonical bytes、Schema、自哈希、stable ID 和语义重放一致；
- known pilot 的 result file hash、result id/hash、net PnL/return 精确绑定 v0.42；
- start/end/cadence/尾部和全部纳入规则不可由调用方覆盖；
- builder 不读取 runtime state、网络、Broker、订单或 credential；
- 同一输入重复 100 次产生完全相同 bytes；
- 篡改窗口、pilot、policy、停止规则或资格声明，即使重算自哈希也被 loader
  拒绝；
- 全量测试和构建清单通过；
- `v0.43.0` 不声称策略赚钱、完成 90 天 Paper 或 AI 优势。
