# v0.48 Challenger Cohort 固定尾部累计评估器设计

日期：2026-07-31

状态：冻结

冻结基线：`v0.47.0` /
`7ef8b8300e84f86fced1ff4c3d5e6d087a66e301`

上位设计：

- `docs/superpowers/specs/2026-07-30-challenger-cohort-episode-pipeline-design.md`
- `docs/superpowers/specs/2026-07-30-challenger-cohort-cumulative-evaluation-plan-design.md`

## 1. 目标

实现 v0.44 在任何 confirmatory outcome 出现前冻结的唯一累计评估方法。v0.48
必须从完整的 540 槽连续性、全部 v0.45 Episode receipts、v0.47 全纳入经济结果
与 exact v0.43/v0.44 plans 自动生成唯一研究继续门结果。

本版本不改变策略、Runner、LaunchAgent 或 runtime state，不发起市场网络请求，
不访问 Broker、余额、凭据或订单。它不提供任何样本、统计参数、阈值或结果选择器。

固定 observation tail end 为
`2026-10-29T12:00:00.000Z`。在此之前，CLI 只能返回
`COLLECTING_DESCRIPTIVE_NO_EARLY_SUCCESS`，不得读取、计算或展示 cohort PnL、
胜率、排序、置信区间、功效或任何可解释为提前成功的指标。

## 2. 冻结信任根

最终评估必须精确绑定：

- v0.43 cohort plan id：
  `challenger_episode_cohort_plan_56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c`；
- cohort plan hash：
  `20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201`；
- cohort plan file SHA-256：
  `a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff`；
- v0.44 evaluation plan id：
  `challenger_cohort_evaluation_plan_54a5456345f57219e2ee8763fd35dd4c753e843d31709f342e283fd4026eb037`；
- evaluation plan hash：
  `a6901e7e721682e6d3e7ded9000b5f183ed35e694b7036c7b596c0555a3ab440`；
- evaluation plan file SHA-256：
  `49e3b7642e163bb95c4ce01bc1c8d95a23b0cefce277d2f99f2e69029207a4d8`；
- v0.37 economic plan file SHA-256：
  `f22cb582a7df38e14220fca75359f6290af2fdb5896e5829ba5d7fd805cf54da`；
- v0.42 exposed pilot result id/hash/file SHA-256：
  `challenger_episode_economic_result_8f2b70abf6221dc2531ecd9e6b4ada9732e8775d9673b67d4865fe7fa9b18723` /
  `2ac4e92fa32c3841548c433590cda3fea799702fdcda291d25866db2bd993fc4` /
  `8627677275c31de573f1a59f638ba1678772115dc6d932027a36e2f8b62d9fee`；
- v0.35 install receipt、contract、plist 与 receipt output root 的冻结绝对路径；
- v0.47 production result Schema、semantic replay 与最新完整累计 index。

旧 pilot、plans、receipt/archive/result artifacts 与 loaders 必须逐字节保持不变。

## 3. 独立只读连续性观察

v0.48 不调用会补写 receipt 的 v0.45 observer。它复用同一 production
trust roots 与只读解析器，独立执行：

1. 从 install receipt/contract/plist 推导唯一 SQLite、bundle、stdout、stderr
   与 LaunchAgent service；
2. 只读加载全部 decisions；
3. 使用 v0.45 冻结状态机划分 cohort slots、completed Episodes 和 active
   Episode；
4. 对每个槽位验证唯一 source bundle 和唯一 stdout `RECORDED`；
5. 执行一次固定 argv 的 `launchctl print`，不允许 kickstart/bootstrap；
6. 绑定 state、540 个窗口槽位、必要 tail follow-up slots、bundle/log roots
   与 decision chain end。

最终时：

- `window_slot_count` 必须精确为 540；
- active Episode 必须为 null；
- 所有窗口内 entry 必须已自然退出；
- completed Episode 顺序和 ID 必须与全部 v0.45 receipts 精确一致；
- receipts 数必须与 v0.47 results/index 数精确一致；
- 漏槽、重复、revision、非法状态迁移、tail 后仍未退出或任一来源信任失败均
  `FAILED_CLOSED_NO_BACKFILL`，禁止回填后重算成成功。

失败时 CLI 返回结构化失败状态和 reason code，不发布一个依赖不可信输入的“成功
格式” artifact。

## 4. Pre-tail 状态

调用时点只能来自本机 UTC wall clock；CLI 不接受时间参数。测试可注入 clock，
但 production parser 不暴露。

在 tail end 以前，CLI 只读取 exact plans/pilot identity 和运行连续性，不读取
archive、v0.47 result 或 index 目录。stdout 只包含：

- status；
- observed_at；
- tail_end；
- verified cohort slot count；
- completed Episode count；
- active Episode id 或 null；
- next required slot 或 null；
- network/Broker/order/state-write/Runner 全零。

不创建 evaluation output root 或任何 artifact。

## 5. 最终结果输入完整性

到达 tail end 后才允许加载经济结果。最终 loader 必须：

1. 使用 v0.47 production discovery 验证全部 receipt 文件、ordinal、prior list
   与 entry slot 顺序；
2. 使用 v0.46 loader 验证全部且仅全部 required shared day archives；
3. 逐 Episode 使用 v0.47 builder 重建 result，并验证 exact result path/bytes/
   file SHA-256；
4. 验证 result inventory 没有缺失、多余或选择性删除；
5. 验证 0001..N 的不可变累计 index chain、每个累计前缀和最新完整 index；
6. N=0 时要求 result/index inventory 均为空，并使用 zero hash 表示空 index。

调用方不能传 result/index 文件、Episode 列表、日期、价格、费用、PnL 或排除项。

## 6. Confirmatory 统计内核

观察顺序固定为 entry slot 升序，观察值固定为每 Episode `net_return`，只允许
Decimal。

实现必须逐字节执行 v0.44 参数：

- arithmetic mean；
- block length 3；
- overlapping non-circular MBB truncate-to-N；
- 10,000 replicates；
- seed 2026073044；
- conservative nearest-rank；
- one-sided 95% LCB；
- two-sided 95% percentile interval；
- Geyer initial positive sequence ESS；
- MERE 0.005 下的 shifted-centered MBB achieved power。

样本门：

- N >= 30；
- ESS >= 20；
- floor(N/3) >= 10；
- 6 个固定 15 天块均至少 1 个 Episode；
- achieved power >= 0.80；
- two-sided CI full width <= 0.02。

统计量不可计算时使用 null 和明确 gate failure；不得用 0、点估计或正样本替代。

## 7. 路径、压力与稳健性

固定名义路径从 1000 USDT 开始，按 entry slot 顺序逐笔加
`net_pnl_usdt`。最大回撤采用先前高水位；任一 equity <= 0 使经济门失败。

每个 Episode 按 entry slot 归属 v0.44 固定的六个 15 天块。空块不算非负，至少
5/6 非空块累计净 PnL >= 0。

1.5x 摩擦必须从同一 v0.47 selected source rows完整重算：

- entry high + 15bps 并向上到 0.01；
- exit low - 15bps 并向下到 0.01；
- 双边各 22.5bps taker fee；
- 1000 USDT / stressed entry fill，向下到 0.0001 ETH；
- 汇总全部 Episode stressed net PnL。

leave-Top-5 只删除 `net_pnl_usdt > 0` 的最多五个 Episode，排序为 PnL 降序、
Episode ID 升序。删除后使用相同 MBB/ESS/power/CI 和固定时间块重新执行全部
样本门。leave-out 任一样本门不足使最终状态为
`INCONCLUSIVE_INSUFFICIENT_EVIDENCE`，不能降格为普通经济门失败。

## 8. 状态机

最终状态只允许：

- `RESEARCH_CONTINUATION_GATE_PASS`：原始与 leave-out 样本门全部通过，且五个
  经济门全部通过；
- `RESEARCH_CONTINUATION_GATE_DID_NOT_PASS`：样本门全部通过，但至少一个经济门
  失败；
- `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`：完整性可信，但原始或 leave-out
  样本门不足；
- `FAILED_CLOSED_NO_BACKFILL`：CLI 错误状态，不发布 final artifact。

PASS 仍固定：

- profitability：
  `INELIGIBLE_RESEARCH_PROXY_NOT_SYSTEM_PAPER`；
- release_oos：
  `INELIGIBLE_NO_SEALED_RELEASE_AUDIT`；
- execution：
  `INELIGIBLE_PROXY_NOT_REAL_FILL`；
- ai_comparison：
  `INELIGIBLE_NO_PAIRED_AI_COHORT`。

## 9. Pilot 与 all-stream

v0.42 负 pilot 永久单列，不能进入 confirmatory MBB、ESS、功效、时间块、回撤、
压力或 leave-out 门。

最终 artifact 同时包含只读的 all-stream 描述：

- pilot count 固定 1；
- confirmatory count；
- all-stream count；
- pilot/confirmatory/all-stream total net PnL；
- all-stream mean net return。

all-stream 只作描述，不参与 PASS。

## 10. Artifact、身份与发布

新增 `challenger-cohort-cumulative-evaluation-v1.schema.json`。最终 artifact
至少包含：

- exact plans 与 pilot bindings；
- final continuity slots、source roots 与安全计数；
- latest v0.47 index binding；
- 全部 confirmatory observations；
- 原始与 leave-out 统计、样本门；
- 六个时间块、路径、压力与五个经济门；
- final status、资格与警告。

`evaluated_at` 不使用调用时点，自动取 tail end 与全部 v0.47 result
`evaluated_at` 的最大值。identity 绑定 evaluation plan hash、continuity root、
latest index hash、pilot result hash 与 evaluated_at。

唯一路径：

`<owner-only-output-root>/challenger-cohort-cumulative-evaluations/<result-id>.json`

目录 0700；文件 0600、单 hardlink、canonical exact bytes、只追加。同一输入重复
100 次 bytes/inode/mtime 不变；同路径不同 bytes 失败关闭。

## 11. CLI

唯一参数为：

- `--cohort-plan-path`
- `--evaluation-plan-path`
- `--economic-plan-path`
- `--pilot-result-path`
- `--install-receipt-path`
- `--contract-path`
- `--plist-path`
- `--episode-receipt-output-root`
- `--archive-output-root`
- `--result-output-root`
- `--evaluation-output-root`

CLI 不接受 clock、state、bundle、log、service、Episode、日期、价格、费用、资本、
PnL、label、bootstrap、seed、阈值、排除项、result id 或 filename。

## 12. 验收

- 设计提交与实现提交分离；
- pre-tail fixture 证明不调用 economic loader、不读取 PnL、不创建输出；
- 540 槽/零 Episode得到可信 `INCONCLUSIVE`；
- >=30 Episode fixtures 覆盖 PASS、经济门失败、样本不足、ESS不足、空时间块、
  功效不足、CI过宽、非正 equity、1.5x stress、leave-Top-5；
- pilot 始终单列且包含在 all-stream；
- 缺 receipt/result/index、负结果删除、顺序/哈希/selected row 篡改全部失败；
- 100 次 deterministic build 与 exact retry；
- CLI authority、Schema mirrors、v0.44/v0.45/v0.47 回归、全量 tests、compile、
  evaluator build manifest 全部通过；
- 真实 pre-tail 只读运行返回收集中，0 market/Broker/order/state-write/Runner，
  不创建 final artifact；
- v0.48 不声称系统 Paper、真实成交、AI 优势或可启动真钱交易。

## 13. 赚钱目标的解释

v0.48 是本 cohort 第一个允许在固定时间门后做累计收益判断的版本，但 PASS 仅说明
这个简单规则在冻结研究代理下值得进入下一阶段。它不能把代理成交、假设费率和本地
前瞻证据升级成真实赚钱证明。真正接近资金上线仍需要独立的账户实际成本、Paper、
sealed OOS、故障恢复、对账、资本与合规门。
