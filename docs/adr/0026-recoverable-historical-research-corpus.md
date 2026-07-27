# ADR-0026：可恢复历史研究语料与滚动 OOS 计划

日期：2026-07-28
状态：已接受

## 背景

v0.25 已完成只读完整周期编排，但仓库只有单日历史归档 smoke 和短周期
Paper。现阶段直接训练 AI 会把不连续样本、事后归档和正式 PIT 证据混为
一谈，也无法执行治理要求的 18 个月滚动训练、8 个季度 OOS 和最后 12
个月封存审计。

## 决策

1. 冻结 `2023-01` 至 `2026-06` 共 42 个完整 UTC 月。
2. 每月固定四条流：ETH Spot 4h、BTC Spot 4h 上下文、ETH USDⓈ-M Mark
   4h 和 ETH Funding，共 168 个 item。
3. 新增月度 Spot/Mark Kline 官方归档支持；所有 ZIP 在解压前验证官方
   `.CHECKSUM`。
4. 冻结 8 个连续季度 OOS fold，每折前置 18 个月训练窗、最后 1 月校准
   窗及 24h purge/embargo。
5. 使用绑定 plan/output 的 SQLite WAL/FULL append-only 状态、15 分钟
   租约和 exact source bytes 实现崩溃恢复。
6. 成功项永不重采或改写；失败项可重试；每次最多处理 16 项。
7. coverage snapshot 同时报告语料完整度、来源质量、独立 attestation
   锚定和明确的不合格用途。
8. 全部归档永久为 `ARCHIVE_REPLAY_ONLY`。即使 168 项齐全，也只允许
   `READY_FOR_ARCHIVE_RESEARCH_FEATURE_BUILD`，不能获得正式 PIT/OOS、
   ModelBundle 激活或盈利资格。

## 理由

月度文件把完整语料首次下载从约五千次 daily GET 降到 336 次 GET，同时
仍保留官方 ZIP/checksum/CSV/source-row 证据。逐项状态和精确 bytes 使
网络失败或进程崩溃不会把同一 item 悄悄替换为不同历史修订。

先冻结数据窗口和 fold，再写特征/训练代码，可以减少看到结果后移动窗口、
改变切分或反复调参的研究者自由度。BTC 仅作为上下文，继续遵守小资金
阶段不产生 BTC 订单的范围。

## 拒绝的方案

- 直接训练 XGBoost：拒绝；连续语料、标签和切分尚未形成。
- 把单日 smoke 重复采样成训练集：拒绝；不增加独立信息。
- 用 REST 静默填 monthly archive 缺口：拒绝；来源和修订语义不同。
- 把官方 checksum 当 PIT 证明：拒绝；它只证明摄取时下载的 archive
  bytes，不证明历史决策时本系统已收到这些数据。
- 将原始 42 月数据提交 Git：拒绝；体积、修订和凭据边界都应由仓库外
  owner-only 数据目录承载。

## 后果

v0.26 可以证明公开研究语料的计划、摄取和覆盖机制可靠，但不能证明 AI
优于基线或策略赚钱。下一版本只有在完整 corpus 实际就绪后，才可实现
同源特征、event-based 标签和低维 Logistic 研究基准；正式 Release Audit
仍必须等待 contemporaneous PIT 数据与独立政策批准。
