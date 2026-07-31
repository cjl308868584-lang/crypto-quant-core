# 实施追踪 v0.53.0

日期：2026-07-31

状态：已实现；首次 08:10 自然维护完成并逐字节封存

## 本版本交付

- 以提交 `275b462` 冻结首次自然维护运行证据发布设计；
- 新增 exact-byte release core/CLI，不接受时间、service、日志、root、summary、
  PnL、日期、URL、命令或运行阶段覆盖；
- 新增 runtime source 的 owner/mode/link/size/identity/canonical bytes 检查；
- 发布前后均使用 v0.52 production loader 重放；
- Git artifact 使用固定文件名、no-overwrite exact publish，并在重放失败时只回滚
  本次新建的精确目标；
- 新增 committed artifact 的 Schema、canonical bytes、receipt identity、文件哈希、
  自哈希和权限边界回归；
- 把真实 artifact 纳入 deterministic evaluator build。

## 真实只读验收

- observer baseline：tag `v0.52.0` /
  `d0683658957c26ba868b567d27bfbe5fbb308175`；
- first natural schedule：`2026-07-31T00:10:00.000Z`
  （北京时间 `08:10`）；
- completion deadline：`2026-07-31T00:20:00.000Z`；
- maintenance summary observed：`2026-07-31T00:10:04.110Z`；
- observer observed：`2026-07-31T08:00:42.902Z`；
- LaunchAgent：not running、`runs=1`、last exit `0`；
- status：`FIRST_NATURAL_MAINTENANCE_RUN_COMPLETED_VERIFIED`；
- maintenance status：`COHORT_EVIDENCE_NO_COMPLETED_EPISODES`；
- receipt published：true。

观察前后完全不变：

- strategy state SHA-256：
  `3061cdaf9cbd2c5867cb02d392a999741e8f44bbaac18efcf288cbbd5a96435f`；
- strategy stdout SHA-256：
  `265b03205ffe52a2c23d129fc96531a0a33296055e31fe9638afcf7c2c7508a5`；
- strategy stderr SHA-256：
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；
- maintenance stdout SHA-256：
  `84b600b5cc82d06f59f38a10118764e5d7fde99cf7787901b19e466ca620ad67`；
- maintenance stderr SHA-256：
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；
- observer network、Broker、order、strategy state write、strategy Runner
  invocation、maintenance invocation 全部为 0；
- observer 只执行一次固定 `launchctl print`。

## Exact receipt

- runtime path：
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1/control/challenger-cohort-evidence-maintenance-first-run-v1/maintenance-first-run-receipts/challenger_cohort_evidence_maintenance_first_run_receipt_c0298535143bb17418f2ebea5c08667c237f0a64a7a381547fff84d9bea42b07.json`；
- Git artifact：
  `artifacts/challenger-forward/challenger-cohort-evidence-maintenance-first-run-receipt-v0.53.0.json`；
- receipt id：
  `challenger_cohort_evidence_maintenance_first_run_receipt_c0298535143bb17418f2ebea5c08667c237f0a64a7a381547fff84d9bea42b07`；
- receipt hash：
  `b89087541fa590c41e4ae3533cb11da0e0328c0ff60cbad36e1972bd44446ee4`；
- exact size：10,273 bytes；
- runtime/Git SHA-256：
  `86e85a40ed9c09d90568b0c9cc50ad439092155718c929072ea3bb3539e3598f`；
- `cmp`：完全一致；
- v0.52 production loader 从 runtime 与 Git 两处重放：通过。

## 验证

- v0.53 release focused tests：9/9；
- v0.52 observer + v0.53 release regression：20/20；
- 版本/构建相邻回归：29/29；
- committed artifact Schema、canonical bytes、自哈希和固定身份：通过；
- evaluator build input：232；
- evaluator manifest version：`1.48.0`；
- package version：`0.53.0`；
- evaluator tree hash：
  `bccbfddd0134888aaeb8e72791a8defb07b9109c155ed88539a25e903bd3735a`；
- evaluator manifest hash：
  `e9abbaea6842b2dfcd056728c40d99c3d95fdbf28cf3b8376225fcf8d02ada0a`；
- compileall：通过；
- 全量 tests：714/714；
- `make validate`：evaluator、Schema 与治理模板技术验证通过；release policy 按
  设计保持 `DESIGN_BASELINE` / `PRODUCTION_ACTIVATION_DISABLED`；
- PR CI 与 main CI 在 GitHub 发布流程中复核。

## 尚未完成

首次维护成功不等于 cohort 完整或策略赚钱。首轮维护时 completed Episode 为 0，
因此没有日档请求或经济结果。系统必须继续自然运行至固定
`2026-10-29T12:00:00.000Z` tail end，并保留全部 540 槽和所有正负 Episode。

tail end 前禁止读取累计 PnL、提前停止、重置 cohort、人工补槽或按结果选择 Episode。
AI 臂仍没有批准模型，不得进入发布或下单链。
