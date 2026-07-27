# ADR-0025：可恢复的完整周期编排与本机调度合同

状态：Accepted

日期：2026-07-28

## 背景

v0.24 已能把账户成本、scheduled Paper 和永续上下文绑定成同槽位侧车，但各
来源仍由独立 CLI 捕获。简单 shell 串联存在致命 PIT 缺口：账户费率必须早于
Paper 决策；若 Paper 成功后进程崩溃，重跑得到的账户费率会晚于决策，槽位无法
再成为 context-complete。

## 决策

新增独立 append-only orchestration WAL，正常顺序固定为：

1. 在任何网络请求前验证 owner-only、IP-restricted 只读凭据文件；
2. 一次三样本 Binance server-time 健康门；
3. 账户 commission；
4. scheduled Paper；
5. 永续 context；
6. PIT cost binding；
7. v0.24 context sidecar。

正常路径的账户、Paper 和永续共用同一个 monotonic trusted clock，物理请求数
固定为 `3 + 3 + 4 + 5 = 15`。账户/永续独立 Artifact 仍保留原 6/8 请求的
standalone-equivalent 证据合同；编排 snapshot 单独记录去重后的物理请求。

## 恢复语义

WAL 保存 `CLAIMED/ACCOUNT_PREPARED/PAPER_REFERENCED/
PERPETUAL_PREPARED/COST_BINDING_PREPARED/CONTEXT_SUCCEEDED/FAILED`，
精确保存账户、永续和 binding bytes。事件/blob/meta 禁止 update/delete，
每次打开都重放哈希链、租约、阶段和来源业务语义。

账户一旦 PREPARED 就永不重采；Paper 复用原 scheduler；永续或 binding
失败可在同槽位重新打开健康门继续。恢复路径可使用新的健康 probe，但 snapshot
明确记录 probe 数量，不能伪称全程同一进程时钟。

## LaunchAgent

新增 renderer 生成 mode-0600 plist 和合同：

- 上海本机时区下每 4 小时第 6 分钟运行；
- RunAtLoad 支持槽位内恢复；
- 只包含 credential **文件路径**，不读取或保存 credential value；
- 固定 Python module、状态和输出路径；
- 不接受 shell、URL、订单或任意命令；
- 不调用 `launchctl`。

没有外部安装/加载 receipt 时，状态固定为
`NOT_INSTALLED_NO_EXTERNAL_RECEIPT`。

## 安全与赚钱含义

缺凭据时零网络失败关闭；时钟阻断后不触发账户/Paper/永续；权限过大时在
commission 前阻断；整个模块没有余额、持仓、订单或成交端点。

这使长期数据收集更可靠，但仍不证明赚钱。真实运行、操作系统安装、连续
90 天、实际滑点和 AI 配对增量仍必须独立取得证据。
