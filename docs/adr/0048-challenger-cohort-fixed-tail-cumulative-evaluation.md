# ADR-0048：Challenger Cohort 累计结论必须等待固定尾部

日期：2026-07-31

状态：已接受

## 背景

v0.44 已在 confirmatory cohort 开始前冻结累计统计和经济门，v0.45-v0.47
已建立槽位、Episode receipt、共享日档、逐 Episode 结果和不可变累计索引。
尚缺的是一个不会提前查看收益、不会选择 Episode、也不会把缺证据解释为成功的
最终执行器。

## 决策

1. 以独立提交 `543684f` 冻结 v0.48 详细设计。
2. 新增独立只读 continuity observer；它复用冻结状态机验证 SQLite、全部
   source bundles、stdout records 与固定 `launchctl print`，但绝不调用会补写
   receipt 的 v0.45 observer。
3. 在 `2026-10-29T12:00:00.000Z` 前只返回槽位数、Episode 数和下一槽位，
   不读取 archive/result/index，不计算或输出 PnL、胜率、排序、区间或功效。
4. 到达尾部后要求 540 个窗口槽、无 active Episode，并让 completed Episode
   ID 与全部 v0.45 receipts、v0.47 results 和累计 index 精确一一对应。
5. 逐 Episode 使用 v0.47 production builder 和 v0.46 archive loader 重放；
   任何缺失、多余、篡改或选择性删除均
   `FAILED_CLOSED_NO_BACKFILL`。
6. 只允许 v0.44 冻结的 Decimal MBB、ESS、MERE power、六时间块、固定名义
   drawdown、1.5x friction 和 leave-Top-5 门。
7. 原始或 leave-out 样本门不足固定为
   `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`；只有二者样本门及全部经济门通过才
   `RESEARCH_CONTINUATION_GATE_PASS`。
8. 已暴露的 v0.42 负 pilot 永久单列，只进入 all-stream 描述，不进入
   confirmatory 判定。

## 后果

系统具备了固定尾部累计评估能力，但当前仍处于收集期。即使未来研究继续门 PASS，
它也只允许进入下一研究阶段，不是系统 Paper、真实成交、AI 优势或可持续盈利证明。
实盘资格仍需要账户实际成本、独立 sealed OOS、Paper、故障恢复、对账、资本和
合规门。
