# v0.47 Challenger Cohort Episode 经济结果与只追加索引设计

日期：2026-07-30

状态：冻结

冻结基线：`v0.46.0` / `81a4d72096f291eb8f42e0703689308d5c06a337`

上位设计：
`docs/superpowers/specs/2026-07-30-challenger-cohort-episode-pipeline-design.md`

## 1. 目标

把 v0.45 发布的全部 completed Episode receipts 与 v0.46 按 UTC 日唯一保存的
官方 ETHUSDT Spot 1m 日档，转换为每个 Episode 唯一、确定性、可离线重放的经济
结果，并以不可变累计快照组成只追加 result index。

本版本只回答“冻结成交代理和成本口径下，每个已完成 Episode 的描述性结果是什么”。
它不改变策略、Runner、LaunchAgent 或 runtime state，不发起市场网络请求，不访问
Broker、余额、凭据或订单，也不形成提前盈利通过。

旧 pilot artifact、Schema、loader、CLI 和 v0.42 结果必须逐字节保留。

## 2. 冻结信任根

所有结果必须精确绑定：

- v0.43 cohort plan id：
  `challenger_episode_cohort_plan_56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c`；
- cohort plan hash：
  `20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201`；
- cohort plan file SHA-256：
  `a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff`；
- v0.37 economic plan id：
  `challenger_episode_economic_plan_e5c86696889d209373ce536ee0f54be72e59d7de96b6868cd5ab0358491985a4`；
- economic plan hash：
  `fa43e1bb24ac0e9d70c82a3d09f03ca43a5f99c429f43e6c67d6e68029732831`；
- economic plan file SHA-256：
  `f22cb582a7df38e14220fca75359f6290af2fdb5896e5829ba5d7fd805cf54da`；
- economic policy hash：
  `32c81160e936caf4253e0eabe46104fde5f6b747e0525fa2ea916c028dea82f9`；
- v0.35 install receipt、contract、plist 和 receipt output root 的冻结绝对路径。

economic plan 的 `first_episode` 仅属于已暴露 pilot，不参与 cohort Episode
验证。v0.47 只验证其 exact 文件、自哈希和 economic policy，再验证 v0.43
`measurement_binding` 与该 policy 精确一致。

## 3. 无选择 Episode 枚举

CLI 不接受 Episode id/path、ordinal、日期、时间、action 或“只处理某一笔”的
选择器。每次运行必须：

1. 从固定 receipt output root 的
   `challenger-cohort-episode-receipts` 目录扫描全部文件；
2. 对每个文件调用 v0.45 production loader；
3. 验证文件名、0600、单 hardlink、owner、ordinal 连续、entry slot 严格递增、
   prior completed Episode 列表与根哈希；
4. 按 entry slot 升序处理全部 receipts；
5. 重复 Episode、ordinal gap、跳过较早 Episode、未知文件或已有结果冲突均失败
   关闭。

没有 completed receipt 时，CLI 返回
`COHORT_ECONOMIC_RESULT_NO_COMPLETED_EPISODES`，结果和索引写入数均为零。

## 4. 唯一日档来源

v0.47 不含 HTTP transport，也不允许 REST、网页、第三方或手工日档输入。它必须
调用 v0.46 production loader，令 loader 从全部 receipts 自动求 required UTC 日
集合并验证每个 ZIP、checksum 和 day receipt。

每个 Episode 的 execution minute 为对应 entry/exit decision `recorded_at` 后第一
个严格完整 UTC 分钟。entry/exit 行必须来自 execution minute 所在的 verified
完整日档。缺任一 required day、1440 行覆盖不完整、checksum/receipt/hash 不符或
日档库存多出未派生日期，全部失败关闭且不发布新的 result/index。

结果同时绑定 day receipt id/hash/file SHA-256、ZIP/checksum/CSV SHA-256、
1440 行 root hash，以及被选中 entry/exit 行的 source row hash。

## 5. 确定性经济计算

每个 Episode 只允许使用 v0.37/v0.43 已冻结的口径，计算顺序固定为：

1. `entry_execution_minute`；
2. `exit_execution_minute`；
3. `entry_fill = ROUND_UP(entry_minute_high * (1 + 0.001), 0.01)`；
4. `exit_fill = ROUND_DOWN(exit_minute_low * (1 - 0.001), 0.01)`；
5. `quantity = ROUND_DOWN(1000 / entry_fill, 0.0001)`；
6. entry/exit notional；
7. 双边各 `0.0015` taker fee；
8. gross PnL；
9. net PnL；
10. `net_return = net_pnl / 1000`；
11. `positive_label = 1` 当且仅当 `net_return > 0`，否则为 `0`。

只允许 Decimal，禁止 binary float。调用方不得传价格、滑点、费用、资本、数量、
PnL、label、result id、filename 或 evaluated time。`evaluated_at` 自动取该
Episode 所需 day receipts 中最晚的 `retrieved_at`。

## 6. Result artifact

新增独立
`challenger-cohort-episode-economic-result-v1.schema.json`。每个结果至少绑定：

- exact cohort/economic plan；
- Episode receipt id/hash/file SHA-256、ordinal 与 entry slot；
- entry/exit decision、execution minute；
- verified source archives 与 selected rows；
- economic policy、计算顺序和完整 Decimal economics；
- `status = DESCRIPTIVE_NO_EARLY_SUCCESS`；
- market/Broker/order/state-write/Runner = `0/0/0/0/0`；
- `profitability = INELIGIBLE_INTERIM_COHORT`；
- proxy 非真实成交、假设费率、禁止提前成功等警告。

identity 不接受调用方输入，自动绑定 plan hash、receipt hash、entry/exit row
hash、economic policy hash 与 evaluated_at。路径唯一派生为：

`<owner-only-result-root>/challenger-cohort-economic-results/<entry-slot>-<episode-id>.json`

目录 0700；文件 0600、单 hardlink、canonical bytes、只追加。重复运行 exact
bytes 相同且 inode/mtime 不变；同路径不同 bytes 失败关闭。

## 7. 只追加累计索引

索引不是一个可改写文件。每个新 Episode 追加一个不可变累计快照：

`<owner-only-result-root>/challenger-cohort-economic-result-index/<ordinal:04d>-<index-id>.json`

新增独立 `challenger-cohort-economic-result-index-v1.schema.json`。第 N 个快照包含
按 entry slot 排序的前 N 个完整 entry；每个 entry 绑定 ordinal、Episode id、
entry slot、Episode receipt id/hash/file SHA-256，以及 result id/hash/file
SHA-256、net PnL、net return 和 positive label。快照还绑定：

- `previous_index_hash`，首个快照使用 64 个零；
- 当前 receipts root、results root 和 entries root；
- exact cohort/economic plan；
- `status = DESCRIPTIVE_NO_EARLY_SUCCESS`；
- `profitability = INELIGIBLE_INTERIM_COHORT`。

每次运行先完整验证已有索引文件的 0001..N 连续命名、previous hash 链、累计
前缀、所有已引用 receipt/result exact bytes 和语义重放。随后按序为尚未索引的
receipts 发布 result，再追加累计快照。已有索引多于 receipts、缺号、乱序、重复、
未知文件、被修改 result 或选择性遗漏均失败关闭。

崩溃恢复顺序固定为先 result、后 index。若 result 已 exact 发布但对应 index
尚未发布，重试只追加缺失 index；不得重写 result。

## 8. CLI 与输出

唯一 CLI 参数为路径：

- `--cohort-plan-path`
- `--economic-plan-path`
- `--episode-receipt-output-root`
- `--install-receipt-path`
- `--contract-path`
- `--plist-path`
- `--archive-output-root`
- `--result-output-root`

CLI 不接受 transport、clock、Episode/date/price/cost/result 选择器。成功摘要包含：
总 receipt/result/index 数、本次新增 result/index 数、最新 index id/hash/path，
以及 market/Broker/order/state-write/Runner 全零边界。

所有输入必须绝对路径、非 symlink、owner-only 或仓库允许的只读计划文件。archive、
receipt 与 result roots 必须位于允许的 owner-only base 下，互不相同且不互相
嵌套。

## 9. 失败原子性

发布前必须完成全部 trust-root、receipt 集合、日档集合和已有 result/index
验证。只有整个输入前缀可重放时才允许开始追加。

单个 Episode 发布阶段采用 exact create/link 语义。发生进程中断时，最多留下一个
已完整发布、尚未索引的 result；下一次运行验证 exact bytes 后继续。不得产生半个
JSON、覆盖旧文件、删除负样本或回滚索引。

## 10. 验收

- 设计提交与实现提交分离；
- fixture 覆盖无 Episode、单 Episode、多个 Episode、同日复用、跨日、正/负
  结果、崩溃后 result-only 恢复；
- 缺 receipt、ordinal gap、重复 Episode、缺日档、额外日档、checksum/day
  receipt/result/index 篡改、次序冲突全部失败关闭；
- 同一输入重复 100 次 result/index exact bytes、inode、mtime 不变；
- CLI help 证明没有 Episode/date/price/cost/PnL/label/id/filename/clock/URL
  selector；
- v0.40 pilot tests 与 v0.46 archive tests 全部回归通过；
- Schema mirrors、全量 tests、compile、evaluator build manifest 通过；
- 真实目录无 completed Episode 时只读运行必须 0 network、0 result/index
  write；
- v0.47 不发布 cohort 累计 PASS，不声称 Paper、AI 优势或系统可赚钱。

## 11. 赚钱目标的解释

v0.47 不提高策略收益；它让每笔完成交易在相同最坏成交代理和完整成本下自动入账，
使亏损样本和正样本同样不可删除。赚钱结论只能在固定 tail end 后，由 v0.48 对完整
槽流、全部 receipts/results 执行预注册的样本量、区间、回撤、压力与稳定性门后
产生。任何单笔正收益、当前正累计或 AI 解释都不能提前升级资格。
