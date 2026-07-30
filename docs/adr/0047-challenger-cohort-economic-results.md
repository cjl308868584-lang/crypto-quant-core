# ADR-0047：Challenger Cohort 经济结果必须全纳入并只追加

日期：2026-07-30

状态：已接受

## 背景

v0.45 已能为每个 completed Episode 生成不可选择的 receipt，v0.46 已能按 UTC
日唯一保存并复用官方完整日档，但尚未把每笔 Episode 自动转换为统一成本口径下的
经济结果。若允许调用方选择 Episode、日期、价格或文件名，就可以只计算正收益
交易；若持续改写单个索引文件，又无法证明历史负样本没有被删除。

## 决策

1. 以独立提交 `e687558` 冻结详细设计，并保持旧 pilot 结果逐字节不变。
2. CLI 每次扫描并使用 v0.45 loader 验证全部 receipt；不接受 Episode、日期、
   价格、费用、PnL、label、result id、filename 或时间覆盖。
3. v0.47 只读取 v0.46 loader 验证的共享日档，不包含 HTTP transport。
4. 每个 Episode 使用 decision `recorded_at` 后首个完整 UTC 分钟、bar high/low
   加双边 10bps 滑点、双边 15bps taker fee、1000 USDT 和 Decimal tick/step
   舍入生成唯一结果。
5. 每个结果绑定 exact cohort/economic plan、Episode receipt、day receipts、
   日档内容和 selected raw rows；owner-only exact publish，冲突失败关闭。
6. 每个新结果追加一个不可变累计 index 快照。第 N 个快照包含前 N 个全部结果并
   绑定前一快照 hash；任何缺号、乱序、遗漏或篡改均拒绝。
7. 中期状态固定为 `DESCRIPTIVE_NO_EARLY_SUCCESS`，profitability 固定为
   `INELIGIBLE_INTERIM_COHORT`。

## 后果

系统可以持续获得不可挑选的成本后 Episode 序列，但仍不能根据单笔或中期累计结果
声称策略赚钱。v0.48 只能在固定 tail end 后，对完整槽流和全部索引结果执行预注册
累计门；此前正负结果都只是描述性研究证据。
