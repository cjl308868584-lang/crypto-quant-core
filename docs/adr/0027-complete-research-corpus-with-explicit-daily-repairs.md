# ADR-0027：完整研究语料与显式官方日档修复

日期：2026-07-28
状态：已接受

## 背景

v0.26 冻结了 42 月、四流、168 项研究语料计划。实际恢复执行后，全部
168 项均成功保存，但 Binance 两个月度 ETH Mark 4h 归档分别缺少一个
完整 UTC 日：`2023-02-24` 与 `2026-06-29`，合计 12 个 4h 间隔。

若把这两个来源缺口静默视为完整，会污染后续特征；若使用 REST、插值或
邻近值补齐，又会混合来源语义并制造无法审计的合成历史。

## 决策

1. 月度来源快照保持不可变，仍标记为 `RESEARCH_ONLY_DEGRADED`。
2. 只允许从缺失 open time 精确推导 Binance 官方 daily archive 请求；
   禁止调用方传入任意 URL、日期或替代数据源。
3. 每个 daily ZIP 必须在解析前通过官方 `.CHECKSUM`，且只能包含该日
   精确缺失的 open time；多行、少行、重复或与月度基底重叠均失败关闭。
4. 新增显式 repair bundle，绑定 plan、完整 corpus snapshot、月度基底、
   daily patch、来源 receipt、attestation、combined coverage root 和自哈希。
5. patch 与 bundle 只发布到仓库外 owner-only 目录；相同路径允许 exact
   bytes 幂等恢复，不同 bytes 冲突拒绝。
6. 保留 parser V1 快照兼容性；新下载使用 V2，并接受 Binance 官方
   underscore header 与 Funding schedule 的不超过 1 秒源时间抖动。
7. 修复完成后的最高状态是
   `READY_FOR_ARCHIVE_RESEARCH_FEATURE_BUILD_WITH_EXPLICIT_DAILY_REPAIRS`。
   它仍永久不具备 PIT、正式 OOS、发布或盈利资格。

## 理由

显式 sidecar 保留“月度文件原本有缺口”这一事实，同时用同一官方归档体系
的日文件恢复完整覆盖。combined coverage root 证明月度基底与日档 patch
没有重叠或遗漏，不需要改写任何已采集的来源快照。

这种设计把“研究可用”与“来源完美”分开，也避免为了追求全绿而隐瞒交易所
归档缺陷。独立新进程可以完全离线重建 repair bundle，证明后续研究不依赖
再次联网得到可变结果。

## 拒绝的方案

- REST 补洞：拒绝；来源、修订和可用性语义不同。
- 插值或前值填充：拒绝；会制造并不存在的价格事实。
- 合并后覆盖月度 JSON：拒绝；破坏原始证据与恢复语义。
- 忽略 12 个间隔：拒绝；会让滚动窗口和特征覆盖不一致。
- 因 archive 完整而宣称 PIT/OOS 有效：拒绝；归档是在历史事件后获取。

## 后果

研究特征工程现在拥有覆盖完整、可恢复、可审计的 archive corpus，但仍没有
event-based 执行标签、批准模型、正式 contemporaneous PIT 审计集、真实
账户成本或连续 Paper 证据。下一版本可以开始同源特征与低维 Logistic
基准研究，但任何 AI 模型都不能直接下单，也不能用回放结果宣称赚钱。
