# 实施追踪 v0.50.0

日期：2026-07-31

状态：真实证据维护 LaunchAgent 合同已生成；未安装、未加载、未运行

## 本版本完成

- 以独立提交 `e867d9f` 冻结 v0.50 详细设计；
- 新增与策略 Runner 完全分离的 maintenance LaunchAgent contract；
- 固定每天北京时间 08:10 / UTC 00:10，`RunAtLoad=false`；
- 自动绑定 v0.43 cohort plan、v0.37 economic plan 和 v2 strategy
  install receipt/contract/plist；
- 固化 v0.49 全部 CLI 参数和三个互不重叠 evidence roots；
- 环境变量只含 `PYTHONPATH`，无 credential、shell、URL、Broker、order、
  state 或 Runner selector；
- 新增 strict Schema/package mirror、自哈希、plist hash、semantic replay 与
  external attestation loader；
- owner-only exact publish、目录 inventory、幂等和冲突失败关闭；
- CLI 只渲染，不安装、不调用 `launchctl`。

## 真实合同

真实合同生成在仓库外：

```text
/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1/control/challenger-cohort-evidence-maintenance-v1
```

- contract id：
  `challenger_cohort_evidence_maintenance_launchd_contract_52c0e521e9212f80b0cda98485eeaccf5acde66d1f29ab537ecaa6bcace74562`；
- contract hash：
  `e3612b64ea737227b79fce0094c390018a9627885f6ebd482d2767d714558d3b`；
- exact contract file SHA-256：
  `a1b81ebfaf35174b8aaa9bb577427ac14bc6806fdc15a15e254bc4c06c239879`；
- external contract trust hash：
  `fd50f6b373b5d790d025f7e5be27211b1b7a9438254f6af1d255ca876e56ac2c`；
- plist SHA-256：
  `edfdc5bda907c265048652b2c9e69e0493473cdc06e14ed7df0d1a5bd3f099d1`；
- output/scheduler：0700；
- contract/plist：0600；
- installation：
  `NOT_INSTALLED_NO_EXTERNAL_RECEIPT`。

真实 loader 使用独立保存的 trust hash 成功复核相同 contract id。完整紧凑证据见
[v0.50 not-installed evidence](../artifacts/challenger-forward/challenger-cohort-evidence-maintenance-launchd-not-installed-v0.50.0.json)。

## 安全验证

- `launchctl`、network、Broker、order、strategy state write、Runner：全部 0；
- 未复制到 `~/Library/LaunchAgents`；
- 未 bootstrap/load；
- cohort receipt/archive/result roots 均未创建；
- runtime state/stdout/stderr SHA-256 前后分别保持：
  - `4332717a4822b948defd1ea38e22b3a53ee3ca54ed460a9d16b61d436b15d44c`；
  - `c17c05dc18072417efcbba3b7d2d6ff912a0bbd38e9ee86aadef296ea8b61f43`；
  - `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## 验证

- v0.50 聚焦 tests：11/11；
- v0.32/v0.33/v0.49/v0.50 相邻回归：40/40；
- 同一输入 100 次 contract/plist exact match；
- Schema mirror：逐字节一致且 Draft 2020-12 有效；
- 全量 tests：677/677；
- Python compileall：完成；
- Golden Vector：41；
- Evaluator build input：214；
- evaluator build 版本：`1.45.0`；
- Build input tree hash：
  `813ad075960fe9af05cb10e03097e568016b7ec06d4a26b0112132bf5db80d41`；
- Evaluator build hash：
  `e23da222833ed47fc9809df50cfb81c105946ae5040c14088262ed166e2f2e3b`；
- `make validate`：完成；生产门继续保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 下一步

下一版本创建绑定已发布 commit 的 owner-only 私有执行快照，以该快照重新渲染唯一
installation candidate contract，再用独立 restricted installer 安装并保存 exact
install/launchctl receipt。安装前不得声称自动维护已经启用；安装也不得触发策略
Runner。首次自然 08:10 运行需要单独验收 maintenance stdout/stderr、evidence
outputs 与策略 runtime hash。
