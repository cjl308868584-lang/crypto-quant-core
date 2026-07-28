# v0.35 Challenger 首槽真实证据发布设计

日期：2026-07-28

状态：冻结

## 1. 目标

在登记首槽 `2026-07-29T00:00:00.000Z` 发生后，使用已经随
`v0.34.0` 发布的只读观察器，封存本机 LaunchAgent 自然产生的首条 Challenger
decision、唯一 source bundle 和交叉验证 receipt。

本版本是一次前向证据发布，不修改策略、参数、首槽、deadline、Runner、安装
快照或观察器口径。它只回答“预注册的首槽是否被原系统按时、完整地记录”，不回答
策略是否赚钱。

## 2. 冻结输入

- 代码基线必须是 tag `v0.34.0` 对应提交 `9d1895c`；
- service 必须是
  `gui/501/local.crypto-quant.challenger-forward`；
- install receipt 固定为
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1/control/challenger-scheduler-v2/challenger-install-receipts/challenger_launchd_install_receipt_d9f8b99b5aeef80bd7627fda751d856ce64b1e68bd016cf538dfe707b154260e.json`；
- contract 固定为
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1/control/challenger-scheduler-v2/challenger-scheduler/challenger-launchd-contract.json`；
- plist 固定为
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1/control/challenger-scheduler-v2/challenger-scheduler/local.crypto-quant.challenger-forward.plist`；
- receipt output root 固定为
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1/control`，
  成功文件只能进入其 `challenger-first-slot-receipts` 子目录；
- observer CLI 不接受 state、bundle、log、service、command、URL、symbol、
  credential、order 或 clock 覆盖；
- 不允许 kickstart、bootstrap、重跑 Runner、手工补写 state、修改日志或复制
  历史 Kline 回填首槽。

## 3. 允许的真实结果

### 3.1 首槽前

`WAITING_BEFORE_FIRST_SLOT` 只表示时间未到，不创建 `v0.35.0` 证据发布。

### 3.2 Deadline 内等待

`OBSERVATION_PENDING_WITHIN_RECORD_DEADLINE` 只表示后台记录尚未可见：

- 不发布 receipt；
- 不触发 Runner；
- 保留 LaunchAgent 与原始现场；
- 最迟在 `2026-07-29T04:00:00.000Z` 前再次只读观察。

### 3.3 成功

只有 observer 返回 `FIRST_SLOT_RECORDED_VERIFIED` 且
`receipt_published=true` 时，才允许：

- 立即用 `load_challenger_first_slot_receipt` 重载同一 runtime receipt；
- 记录 runtime receipt 的 absolute path、SHA-256、receipt id/hash；
- 将完全相同的 canonical JSON bytes 封存为
  `artifacts/challenger-forward/challenger-first-slot-receipt-v0.35.0.json`；
- 在仓库内重新执行 Schema、自哈希和冻结语义验证；
- 更新 ADR、实施追踪、README、package/evaluator 版本与构建清单；
- 运行 focused、相邻回归、全量测试和 `make validate` 后提交、合并并标记
  `v0.35.0`。

仓库副本由 Git 管理，可使用普通仓库文件权限；runtime 原件必须继续保持 uid 当前
用户、mode 0600、单 hardlink，且二者 SHA-256 完全一致。

### 3.4 失败或漏槽

observer 返回错误，或 deadline 后报告
`CHALLENGER_FIRST_SLOT_MISSED` 时：

- 禁止创建名称或状态看似成功的 receipt；
- 禁止回填、改时钟、修改 registration 或把第二个槽位冒充首槽；
- 保存只读的 launchctl、state stat/hash、日志 stat/hash 和错误输出；
- `v0.35` 改为失败取证版本，必须先冻结独立失败证据 Schema/设计，再实现；
- 在根因被证明前，Challenger forward eligibility 保持失败关闭。

## 4. 成功交叉绑定

提交的证据必须同时绑定：

- v0.33 install receipt 与私有 execution snapshot；
- v0.32 contract、目标 plist 和当前 launchctl print；
- 首条 SQLite canonical decision、decision chain 与 state 观察前后 stat/hash；
- 唯一 source bundle、candidate decision、原始 HTTP receipt 与 probes；
- 唯一 stdout `RECORDED` 行及观察时 stdout/stderr prefix；
- observer 的网络、Broker、订单和 state write count 全为 0；
- `LOCAL_PREQUENTIAL_RESEARCH_ONLY`、`INELIGIBLE_NO_MATURE_OUTCOME` 和
  `NO_PROFITABILITY_CLAIM`。

## 5. 验收

- 首槽前与 deadline 内 pending 均不能形成发布；
- 成功 runtime receipt 可由 v0.34 loader 重载且观察现场未被修改；
- runtime 与 Git artifact 的 canonical bytes、SHA-256、receipt id/hash 一致；
- committed artifact 的 Schema、自哈希和全部语义可重放；
- 首槽必须恰为预注册时间，不能接受其他 slot；
- 发布版本只增加真实证据和相应验证，不改变产生该证据的运行代码；
- 全量测试、构建清单与文档中的数量和哈希必须来自最终提交候选；
- `v0.35.0` 不得声称成熟收益、AI 优势、Paper 通过或生产资格。

## 6. 赚钱与 AI 含义

首槽成功不是盈利，但它消除一个关键伪利润来源：事后选择开始时间、回填行情或
只保留有利样本。只有持续累积不可回填的前向完整周期，才能进一步估计全成本收益
及下置信界。

AI 继续保持未批准和无交易权限。简单 Challenger 尚未形成成熟结果前，不启动新的
模型搜索；未来 AI 只能在同一候选事件、时间、资本、成本和成交条件下证明相对简单
基线的可重复净增量。
