# v0.53 Challenger Cohort 维护首次自然运行证据发布设计

日期：2026-07-31

状态：冻结

冻结基线：`v0.52.0` /
`d0683658957c26ba868b567d27bfbe5fbb308175`

## 1. 目标

v0.52 已在首次自然北京时间 08:10 槽前发布只读 observer。v0.53 只在该
observer 返回
`FIRST_NATURAL_MAINTENANCE_RUN_COMPLETED_VERIFIED` 且发布 runtime receipt 后，
把同一 receipt 的 exact canonical bytes 封存进 Git。

本版本不修改 maintenance、LaunchAgent、策略 Runner、cohort 计划、日志、state
或 output roots，不重新执行维护，不访问市场，不调用 Broker 或订单。

## 2. 冻结基线与输入

唯一允许的观察器是 tag `v0.52.0` 对应提交中的：

```text
crypto_quant.challenger_cohort_evidence_maintenance_first_run_cli
```

固定 runtime 信任输入：

- maintenance install receipt：

  ```text
  /Users/chenm4/Library/Application Support/CryptoQuant/
  challenger-forward-v1/control/
  challenger-cohort-evidence-maintenance-install-v1/
  maintenance-install-receipts/
  challenger_cohort_evidence_maintenance_install_receipt_
  22e924d97ad5edbd971791b1bfa4b6c53efa2ebf53ede0980af4ec24fb24aaba.json
  ```

- deployment manifest：

  ```text
  /Users/chenm4/Library/Application Support/CryptoQuant/
  challenger-forward-v1/control/
  challenger-cohort-evidence-maintenance-deployment-v1/
  challenger-cohort-evidence-maintenance-install-candidate/
  deployment-manifest.json
  ```

- source contract external trust：
  `fd50f6b373b5d790d025f7e5be27211b1b7a9438254f6af1d255ca876e56ac2c`；
- candidate contract external trust：
  `9f7d6b7e2beb8103fb8cf1da1281d086a243bc63f3c5cc7992a8d4c0b878b83f`；
- v0.52 observer receipt output root：

  ```text
  /Users/chenm4/Library/Application Support/CryptoQuant/
  challenger-forward-v1/control/
  challenger-cohort-evidence-maintenance-first-run-v1
  ```

Git artifact 固定为：

```text
artifacts/challenger-forward/
challenger-cohort-evidence-maintenance-first-run-receipt-v0.53.0.json
```

## 3. 时间门与允许状态

首个自然 schedule 固定由 v0.52 推导为
`2026-07-31T00:10:00.000Z`，completion deadline 为
`2026-07-31T00:20:00.000Z`。

- schedule 前：只能 WAITING，不创建 v0.53；
- schedule 到 deadline：证据不完整只能 PENDING；
- deadline 后 `runs=0`：MISSED，进入失败取证；
- nonzero exit、非空 stderr、stdout 多行或 summary/inventory 不合法：FAILED；
- 只有 COMPLETED_VERIFIED 才能进入成功发布。

失败或漏槽不得手工调用 maintenance、`kickstart`、`bootstrap`、补写日志、
回填 output roots 或伪造 success receipt。失败版本必须另行冻结失败证据设计。

## 4. exact bytes 发布工具

新增独立 release core/CLI，仅接受：

- runtime receipt path；
- install receipt path；
- deployment manifest path；
- 两个 external trust hash；
- Git artifact output path。

工具必须：

1. 使用 v0.52 production loader 重放 runtime receipt；
2. 要求 runtime bytes 与 `canonical_json(receipt).encode("utf-8")` 完全一致；
3. 记录 runtime file SHA-256、size、uid、mode、link count；
4. 使用无覆盖 exact publish 写 Git artifact；
5. 再次要求 artifact bytes、SHA-256 与 runtime 原件完全一致；
6. 使用 production loader 从 Git artifact 再重放一次；
7. 返回 receipt id/hash、file hash/size 和 `EXACT_RECEIPT_RELEASED`。

禁止 clock、schedule、service、log、root、status、summary、PnL、date、URL、
network、credential、Broker、order、Runner、maintenance-now 或 command 参数。
工具不得调用 launchctl；launchctl evidence 已封存在 runtime receipt 中。

## 5. 成功 artifact 约束

Git artifact 必须是 runtime receipt 的逐字节副本，不能添加 release wrapper、
注释、换行、时间、Git commit 或人工摘要。发布元数据只能进入 ADR 和实施状态。

成功 receipt 必须继续证明：

- v0.51 deployment/install/contract/snapshot 信任链；
- 首次自然 schedule/deadline；
- `runs >= 1`、not running、last exit 0；
- 唯一 stdout maintenance summary 与空 stderr；
- cohort receipt/archive/result inventories；
- 观察前后 strategy state/log 和 maintenance evidence 不变；
- observer network/Broker/order/state-write/Runner/maintenance invocation 为 0；
- cohort/profitability/system-paper/AI 均仍 ineligible。

## 6. 发布流程

成功时：

1. 用 tag `v0.52.0` 代码运行 observer；
2. 立即用 v0.52 loader 重载 runtime receipt；
3. 保存 runtime receipt absolute path、stat、SHA-256 与 exact bytes；
4. 用冻结 release CLI 发布 Git artifact；
5. 复核 runtime/Git bytes 完全相同；
6. 新增 committed artifact 回归、ADR、实施状态和 README；
7. 版本升至 `0.53.0`，更新 evaluator manifest；
8. focused、adjacent、全量、compileall、`make validate` 全部通过；
9. PR CI、main CI 通过后创建 annotated `v0.53.0` tag。

tag、main 和 GitHub remote 必须精确指向同一合并提交。

## 7. 对赚钱目标的意义

首次维护成功只证明 evidence pipeline 能按自然计划运行，并减少人工遗漏亏损样本、
选择性归档或只发布有利 Episode 的空间。它不证明策略盈利，也不证明 AI 优势。

完整 90 天 cohort、全部 Episode 的费用后结果、固定 tail end、v0.48 的样本量、
ESS、功效、LCB、回撤、摩擦和 leave-Top-5 门仍必须全部满足，才能形成研究层面的
正向结论；研究 PASS 仍不等于实盘资格。
