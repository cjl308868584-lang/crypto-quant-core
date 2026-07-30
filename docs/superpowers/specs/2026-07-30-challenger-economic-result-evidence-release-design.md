# v0.42 Challenger 首个 Episode 经济结果证据发布设计

日期：2026-07-30

状态：冻结

## 1. 目标

封存首个 Challenger Episode 由官方 Binance DAILY 1m 日档、`v0.37` 事前经济
计划、`v0.36` 完成 receipt、`v0.39` 可信日档 loader 和 `v0.40` 离线结果 CLI
自动派生的唯一研究经济结果。

本设计在真实经济结果产生后记录发布边界；价格、费用、计算、身份和资格口径仍完全
受结果出现前冻结的设计提交 `7769185` 及其依赖 `dd3ab06`、`17c7348`、
`2e411a7` 约束。本设计不得事后更改经济参数、选择来源或重新定义标签。

## 2. 冻结输入与操作

- main 与 annotated tag `v0.41.0` 必须精确绑定完成 receipt；
- plan、completion receipt、install receipt、contract、plist、archive root 和
  result root 只能使用 v0.40 CLI 允许的七个绝对路径；
- 日期、URL、价格、费用、PnL、label、result id 和 filename 均不得人工输入；
- v0.39 只能请求从可信输入自动派生且已过时间门的官方 allowlisted ZIP/checksum；
- ZIP、checksum 和 archive receipt 保持仓库外 owner-only，不提交到 Git；
- result 必须由 v0.40 CLI exact publish 并立即由同链 loader 重载；
- 禁止 Runner、strategy state write、Broker、余额读取或订单。

## 3. 发布对象

只把 runtime result 的 exact canonical bytes 封存为
`artifacts/challenger-forward/challenger-episode-economic-result-v0.42.0.json`。
Git 副本必须与 runtime 原件逐字节相同，并固定：

- result file SHA-256、result id 与 result hash；
- plan、completion receipt 和 source archive 哈希绑定；
- entry/exit 1m 原始行、执行代理规则与 Decimal 计算顺序；
- 参考资本、数量、入场/退出价格、双边费用、gross/net PnL 和 net return；
- `positive_label=0`；
- `INELIGIBLE_SINGLE_EPISODE`、非真实成交和无盈利声明；
- market/Broker/order/Runner/state-write 为零。

## 4. 验收

- committed result 通过 canonical bytes、Schema、自哈希和完整 evaluator replay；
- runtime 与 Git artifact 的 bytes、size、SHA-256 完全一致；
- committed 结果必须保留负值，不得截断费用、修改舍入或改写标签；
- focused、相邻回归、全量测试和构建清单验证通过；
- PR 合并 main 且 main CI 成功后才能创建 annotated tag `v0.42.0`；
- 发布后删除只服务于首个 Episode 结果链的临时 heartbeat。

## 5. 赚钱与 AI 含义

本结果是首个不可回填前向 Episode 的保守执行代理，可用于证明测量链真实工作，并
揭示该样本在假设双边 taker fee 和滑点后的经济结果。它不是实际成交，也只有一个
样本，因此既不能证明策略长期亏损，也不能证明盈利能力。

这个负样本必须原样进入后续累计 Episode 序列，禁止删除、调参后重算或只展示未来
正样本。AI 仍不得接管交易；只有简单基线积累足够连续前向样本后，AI 才能在同事件、
时间、资本、成本和执行条件下证明配对净增量。
