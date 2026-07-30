# v0.45–v0.48 Challenger Cohort Episode 证据流水线设计

日期：2026-07-30

状态：冻结

冻结基线：`v0.44.0` / `8da6fc9`

冻结时点要求：早于 confirmatory cohort 首槽
`2026-07-30T12:00:00.000Z`。

## 1. 目标

把 v0.36–v0.40 仅服务首个已暴露 pilot 的 receipt、官方日档和经济结果管线，
泛化为 v0.43 固定 90 天 cohort 中所有 Episode 的无选择、只追加流水线。旧
pilot artifact、Schema、loader 和结果逐字节保留，不修改、不重新解释。

本设计分四个连续发布：

- v0.45：全槽连续性与任意 completed Episode receipt；
- v0.46：跨 Episode 复用、按 UTC 日唯一保存的官方 1m 日档；
- v0.47：每个 completed Episode 的确定性经济结果及只追加 result index；
- v0.48：从完整槽流、全部 receipt/result 自动生成 cohort 累计评估。

四个版本均不改变策略、Runner、LaunchAgent 或 runtime state，也不增加实时市场
请求、Broker、余额或订单能力。

## 2. 冻结信任根

所有后续实现必须精确绑定：

- v0.43 cohort plan：
  `challenger_episode_cohort_plan_56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c`；
- cohort plan hash：
  `20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201`；
- cohort plan file SHA-256：
  `a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff`；
- v0.44 evaluation plan：
  `challenger_cohort_evaluation_plan_54a5456345f57219e2ee8763fd35dd4c753e843d31709f342e283fd4026eb037`；
- evaluation plan hash：
  `a6901e7e721682e6d3e7ded9000b5f183ed35e694b7036c7b596c0555a3ab440`；
- evaluation plan file SHA-256：
  `49e3b7642e163bb95c4ce01bc1c8d95a23b0cefce277d2f99f2e69029207a4d8`；
- v0.37 economic plan file SHA-256：
  `f22cb582a7df38e14220fca75359f6290af2fdb5896e5829ba5d7fd805cf54da`；
- economic policy hash：
  `32c81160e936caf4253e0eabe46104fde5f6b747e0525fa2ea916c028dea82f9`；
- v0.35 install receipt、contract、plist 和 receipt output root 的已冻结绝对路径。

v0.37 的 `first_episode` 字段只属于 pilot，不得拿来验证 cohort Episode。cohort
经济计算只复用 v0.43 已在结果前绑定的 exact economic policy；每个 cohort
Episode 的 entry/exit 时间必须从其 loader-verified decision receipt 自动派生。

## 3. 全槽连续性和 Episode 枚举

观察器从安装证据推导唯一 SQLite、bundle、stdout、stderr 和 service 路径，不接受
调用方提供这些路径。它从 cohort start 开始按 4 小时槽位验证：

1. 每个已到 record deadline 的槽位恰有一个 canonical decision、一个 source
   bundle 和一个匹配的 stdout `RECORDED`；
2. decision sequence、previous hash、policy/registration、输入窗口与 semantic
   replay 连续；
3. `REJECT_ENTRY` 必须保留，不能因为没有经济结果而忽略；
4. `ENTER_LONG` 自动开始唯一 Episode；后续 state 中的 episode id、entry、
   minimum hold 和 vertical exit 必须不变；
5. 第一次合法 `EXIT_LONG_SMA20` 或 `EXIT_LONG_VERTICAL_24H` 自动完成该 Episode；
6. cohort end 之后只允许完成 end 前已进入的 Episode，最晚不得超过固定 tail end；
7. 任一 gap、重复、revision、非法 state transition、漏槽或越过 vertical exit
   未退出均使 cohort 连续性失败关闭，禁止继续发布后续成功 receipt。

CLI 不接受 Episode ID、sequence、日期、时间、action、价格、PnL、文件名或
“只处理下一笔/某一笔”的选择器。每次运行都扫描完整可信 cohort 前缀，并按
entry slot 升序对所有已完成且尚未发布的 Episode 生成 receipt；已存在 receipt
必须 exact bytes 一致。

## 4. v0.45 Episode Receipt

每个 receipt 至少绑定：

- cohort plan id/hash/file SHA-256；
- install receipt、execution snapshot、contract、plist 与一次固定
  `launchctl print`；
- 观察时点的 SQLite stat/hash、总 decision count、chain end；
- 从 cohort start 到该 Episode exit 的连续 slot index：
  sequence、scheduled time、action、decision id/hash、state before/after；
- 本 Episode 的完整 canonical decisions；
- 每槽唯一 bundle path/hash 和匹配日志行/hash；
- entry、minimum hold、vertical exit、exit、entry ordinal；
- receipt 之前所有 completed Episode id 列表及 root hash，用于证明没有跳过较早
  Episode；
- stdout/stderr prefix stat/hash；
- network/Broker/order/state-write = 0。

receipt identity 不含 `observed_at` 和可追加的现场尾部；同一 Episode 在相同不可变
证据上重复观察必须得到相同 ID 与核心 hash。文件路径只能由
`<owner-only-root>/challenger-cohort-episode-receipts/<entry-slot>-<episode-id>.json`
自动生成，mode 0600、单 hardlink、canonical bytes、只追加。

在进行中的 Episode 不生成伪 completed receipt。CLI 只报告
`COHORT_EPISODE_IN_PROGRESS_VERIFIED`。没有入场时报告连续性进度，不生成空
Episode receipt。

## 5. v0.46 官方日档

所需 execution minute 一律为 decision `recorded_at` 后第一个严格完整 UTC 分钟。
对全部 loader-verified completed receipts 自动求 UTC 日并集。调用方不得传日期、
URL 或 symbol。

每个 UTC 日在 owner-only archive root 中只保存一份 exact ZIP、checksum 与
day receipt，允许多个 Episode 通过 content hash 复用；day receipt 不绑定单个
Episode，避免同日冲突和重复下载。只有完整 UTC 日结束后 5 分钟才允许请求。
404 保持 pending；禁止 REST、网页、第三方、手工 URL/date fallback。

## 6. v0.47 经济结果和索引

结果 CLI 从 exact cohort plan、economic plan、Episode receipt 和 verified day
archives 自动派生：

- entry/exit execution minute；
- worst-bar high/low 加 10bps 双边滑点；
- 15bps 双边 taker fee；
- 1000 USDT 固定参考资本；
- Decimal tick/step 舍入；
- gross/net PnL、net return 与 positive label。

不接受人工日期、价格、费用、数量、PnL、label、result id 或 filename。结果按
Episode id 唯一、canonical、0600、单 hardlink发布。只追加 index 必须按 entry
slot 排序，包含所有 completed receipts；缺 receipt、缺日档、重复 Episode、结果
冲突或次序异常均失败关闭。中期结果固定为
`DESCRIPTIVE_NO_EARLY_SUCCESS`，不能形成盈利通过。

## 7. v0.48 累计评估

只有到固定 tail end 后，才允许从：

- 540 个完整槽位的连续性证据；
- 全部 cohort Episode receipts；
- 全部 Episode economic results；
- exact v0.43 与 v0.44 plans；

自动生成唯一累计结果。实现必须逐项执行 v0.44 的样本、ESS、MBB、功效、区间、
固定时间块、回撤、1.5 倍摩擦与 leave-Top-5 门。pilot 与 confirmatory 分栏，
all-stream 必须包含负 pilot。tail end 前只能输出完整度状态，不能计算可用于提前
成功的中期门。

## 8. 权限与失败关闭

允许：

- 只读 SQLite、bundle、log、install/contract/plist；
- 固定 argv 的一次 `launchctl print`；
- 到日档时间门后的 allowlisted Binance archive ZIP/checksum GET；
- owner-only receipt/archive/result 输出。

禁止：

- Runner、kickstart、bootstrap、手工补槽或历史回填；
- runtime strategy state 写入；
- Broker、余额、凭据或订单；
- 新的实时市场请求；
- Episode、日期、价格、成本、样本或阈值覆盖；
- 删除负样本、按 PnL 停止、重置或延长 cohort。

任何 runtime 文件正在变化、权限不安全、信任根不符、重复/缺失证据、输出冲突或
未知 schema 都失败关闭。失败不能通过新版本重算成成功；只能另行保存失败取证。

## 9. v0.45 验收

- 设计提交早于 cohort 首槽，且与实现提交分离；
- fixture 覆盖无入场、进行中、多个 completed Episodes、连续 REJECT_ENTRY、
  cohort end 后自然退出、漏槽、重复、revision、非法 state transition；
- 一次运行发布全部且仅全部未发布 completed Episodes，不提供选择器；
- receipt loader 在现场追加后仍验证固定前缀，前缀变化立即拒绝；
- 同一输入重复 100 次产生相同 Episode identity 和 canonical core；
- config/package Schema 镜像逐字节一致；
- CLI 无 HTTP transport、Runner、Broker、credential 或 order import；
- 全量测试与 evaluator build manifest 通过；
- v0.45 不发布真实 cohort 经济结果，也不声称盈利、Paper 或 AI 优势。

## 10. 赚钱目标的解释

这条管线不会直接提高收益，它解决“只记录好看的交易”这一最危险的赚钱假象。
只有完整、不可挑选的 Episode 总体在全成本、功效、区间、路径风险与压力条件下
通过 v0.44，才有资格继续到下一研究阶段。任何单笔正收益、少量胜率或 AI 生成的
解释都不能替代该累计门。
