# ADR-0039：官方日档只能由完成凭据和时间门驱动

日期：2026-07-29

状态：Accepted

## 决策

首个 Challenger episode 的经济来源只能由 v0.39 采集器获取。采集器必须先验证
v0.36 completed receipt、v0.37 exact plan，再由 v0.38 规则派生日期；完整 UTC
日结束 5 分钟以前网络请求固定为 0。

请求只能由 Binance public archive allowlist 生成。ZIP 或 checksum 404 保持
pending，不允许 REST、网页、第三方或调用方 URL fallback。成功文件及 receipt
只写入仓库外 owner-only 目录；已验证日档重试为 0 请求。

## 理由

如果允许手工日期、URL、下载或获取时刻，v0.38 的严格计算仍可能建立在不可证明的
输入上。将 receipt、时间门、请求构造、完整日档验证和 exact bytes 封存连成一条
可恢复链，才能避免数据选择和来源替换。

## 后果

- episode 未完成或日档未闭合时不能“先下载再等结果”；
- Binance 尚未发布时只能等待；
- 跨日 episode 可以先保存第一日，但第二日缺失时不能生成经济结果；
- 原始日档不进入 Git；
- 单笔经济代理仍不证明盈利或 AI 优势。
