# v0.46 Challenger Cohort 共享 UTC 日档设计

日期：2026-07-30

状态：冻结

冻结基线：`v0.45.0` / `84843239df90f8806bc29d0a84e68fd08efdf5e2`

上位设计：
`docs/superpowers/specs/2026-07-30-challenger-cohort-episode-pipeline-design.md`

## 1. 目标

把 v0.39 仅绑定首个 pilot Episode 的官方 Binance Spot ETHUSDT 1m
DAILY archive 采集器，泛化为 v0.43 预注册 cohort 的共享日档层：

- 自动读取 v0.45 已由 loader 验证的全部 completed Episode receipts；
- 从每个 Episode 的 entry/exit `recorded_at` 自动派生严格之后第一个完整
  UTC 分钟；
- 对这些分钟求 UTC 日并集；
- 每个 UTC 日只保存一份 exact ZIP、checksum 和 day receipt；
- 多个 Episode 或后续新增 Episode 可按内容哈希复用同一份日档；
- 不生成经济结果，不计算价格、费用、PnL 或盈利标签。

旧 pilot archive、receipt、loader、Schema 和经济结果保持逐字节不变。

## 2. 信任根与输入

实现必须精确绑定 v0.43 cohort plan：

- plan id：
  `challenger_episode_cohort_plan_56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c`；
- plan hash：
  `20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201`；
- plan file SHA-256：
  `a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff`。

生产 CLI 只接受：

- cohort plan path；
- v0.45 receipt output root；
- v0.35 install receipt、contract、plist path；
- owner-only archive output root。

CLI 不接受 Episode id/path、日期、时间、symbol、URL、价格、费用、PnL、
label、文件名或“只取下一日”等选择器。receipt 目录由固定子目录
`challenger-cohort-episode-receipts` 自动定位，所有 regular JSON 文件都必须
通过 `load_challenger_cohort_episode_receipt`。

receipt 必须按 ordinal 完整连续，Episode id 唯一，且每一份
`prior_completed_episodes.episode_ids` 精确等于此前已加载的 Episode id。
未知文件、symlink、非 owner、非 0600、重复、跳号或遗漏均失败关闭，并且在任何
网络请求前拒绝。

## 3. 日期自动派生

每个 loader-verified receipt 只使用：

- `episode.entry_recorded_at`；
- `episode.exit_recorded_at`。

execution minute 固定为 `recorded_at` 所在分钟向下取整后加一分钟，即第一个严格
完整 UTC 分钟。entry 与 exit execution minute 的 UTC 日期共同进入所需日集合。
集合按日期升序处理，范围只能来自 cohort start 至 observation tail end 所允许的
Episode。

没有 verified completed receipt 时，返回
`COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES`，网络请求与文件写入均为零。

## 4. Day receipt 与跨 Episode 复用

每个 day receipt 绑定：

- exact cohort plan id/hash/file SHA-256；
- 固定 Binance public archive request：
  `SPOT/KLINES/ETHUSDT/1m/DAILY/<derived-day>`；
- 自动构造的 exact ZIP/checksum URL 和文件名；
- 日结束后 5 分钟的 `eligible_at`；
- 首次成功获取的 `retrieved_at`；
- ZIP、checksum、CSV SHA-256；
- 精确 1440 行、首末 open time 和全日 source-row root hash；
- 固定安全边界和研究资格警告。

day receipt 不绑定单一 Episode，也不绑定首次下载时的 Episode 集合或 selected
rows。它证明整日 1440 个分钟完整，因此同日后来出现的新 entry/exit minute 可以
复用 exact ZIP/checksum/receipt，重试网络请求为零。

receipt identity 由 cohort plan hash、UTC 日、ZIP/checksum/CSV hash、
source-row root 与首次 `retrieved_at` 决定。输出固定为：

`<owner-only-root>/challenger-cohort-daily-archives/<YYYY-MM-DD>/`

其中只允许：

- `ETHUSDT-1m-<YYYY-MM-DD>.zip`；
- `ETHUSDT-1m-<YYYY-MM-DD>.zip.CHECKSUM`；
- `receipt.json`。

目录为 0700；文件为 0600、regular、owner-only、单 hardlink、canonical bytes。
已存在三件套必须 loader 验证；部分发布只允许用 exact bytes 恢复，任何冲突均
失败关闭。

## 5. 时间门与网络边界

UTC 日 `<D>` 的最早请求时间为 `<D+1>T00:05:00.000Z`。

- 时间门前：0 请求、0 写入；
- ZIP 404：pending，仅 1 请求，不发布成功 receipt；
- checksum 404：pending，共 2 请求，不发布成功 receipt；
- 成功：仅 allowlisted ZIP GET + checksum GET；
- 已验证日重试：0 请求；
- 只获取当前 receipt 并集内、已到时间门且缺失的日期。

禁止 REST API、网页、第三方、代理凭据、手工 URL/date fallback、实时行情请求、
Runner、launchctl kickstart/bootstrap、Broker、余额、订单和 runtime strategy
state 写入。Public transport 必须继续禁用环境代理并只允许
`https://data.binance.vision` 同主机跳转。

## 6. Loader 与后续 v0.47 接口

共享 loader 从同一组 loader-verified Episode receipts 重新派生日期集合，并对每
个日期重新验证：

- 文件与目录安全属性；
- Schema、self-hash、stable id；
- exact request 与 cohort plan binding；
- checksum、ZIP 中唯一预期 CSV；
- 1440 个连续 minute；
- CSV/source-row hashes 与 receipt 完全一致。

loader 返回按日期排序的 exact `(archive_bytes, checksum_bytes, retrieved_at)`
映射，供 v0.47 从 Episode receipt 自动选取 entry/exit 行。缺任一 required day
即失败，不允许调用方跳过或替换日期。

## 7. 状态机

调用结果只能是：

- `COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES`；
- `COHORT_DAILY_ARCHIVE_PENDING`；
- `COHORT_DAILY_ARCHIVE_PARTIAL`；
- `COHORT_DAILY_ARCHIVE_COMPLETE`。

每个日期只能是：

- `COHORT_DAILY_ARCHIVE_NOT_YET_ELIGIBLE`；
- `COHORT_DAILY_ARCHIVE_PENDING_ZIP_404`；
- `COHORT_DAILY_ARCHIVE_PENDING_CHECKSUM_404`；
- `COHORT_DAILY_ARCHIVE_VERIFIED`。

结果报告 receipt count、required day count、verified day count、每日期当前所需的
execution minutes 和本轮 request count，但这些可增长的 Episode 需求不写入
immutable day receipt。

## 8. 验收

- 设计提交与实现提交分离；
- Schema config/package 镜像逐字节一致；
- 0 receipt、单 Episode 同日、跨日、多个 Episode 同日、后续 Episode 复用、
  部分恢复、时间门、两种 404 均有 fixture；
- 缺 ordinal、重复 Episode、伪造 prior list、未知文件、symlink、权限错误在网络
  前失败；
- checksum、redirect、CSV 缺行/重复/乱序/非法数值失败关闭；
- 同一输入重复 100 次产生相同 day receipt identity/core；
- CLI help 证明没有 Episode/date/URL/symbol/price/PnL 选择器；
- CLI 模块无 Runner、Broker、credential 或 order import；
- 旧 v0.39 tests 全部保持通过；
- 全量测试、Schema mirror、compile 和 evaluator build manifest 通过；
- v0.46 不发布真实 cohort economic result，不声称盈利、Paper 或 AI 优势。

## 9. 赚钱目标的解释

共享日档层降低重复下载和跨 Episode 证据冲突，但本身不创造收益。它保证未来每笔
交易的经济结果都使用同一官方完整日档和冻结执行规则，防止按交易挑价格、挑日期或
只保留正收益。只有 v0.47 全纳入结果与 v0.48 累计门通过，系统才有资格讨论是否
存在可重复、成本后的正收益证据。
