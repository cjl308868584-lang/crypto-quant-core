# 实施追踪 v0.54.0

日期：2026-08-01

状态：已实现；原 Challenger cohort 永久失败证据与受控停用已逐字节封存

## 本版本交付

- missed-slot failure observer、restricted CLI、production loader 与双镜像 Schema；
- receipt-first decommission core/CLI 与双镜像 Schema；
- runtime → Git exact-byte release core/CLI；
- dirfd/no-follow/owner-only/no-overwrite publisher，阻断子目录符号链接和覆盖竞态；
- canonical 0600 failure receipt authority、最后 service print 后的再次 source snapshot、
  固定单次 bootout 与完整后验；
- bootout 尝试后的异常、非零结果、后验失败、source mutation 和成功 receipt 发布/重放
  失败的结构化取证路径；
- `observed_at`/4h current slot、重复 canonical stderr、domain projection、install/contract
  文件哈希和 boot time 辅助根因语义；
- 重启后 v0.35 install receipt 仅允许 `st_dev` 漂移的兼容修复；
- 两份真实 runtime receipts 的固定 Git artifacts 和 committed-artifact 回归。

## 真实 failure receipt

- runtime path：
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1/cohort-failures/challenger-cohort-failure-receipts/challenger_cohort_failure_receipt_955e47c773683f1ae4ba7997a84badc373d3daf5afb24763bdc88d1b95d30545.json`；
- Git artifact：
  `artifacts/challenger-forward/challenger-cohort-missed-slot-failure-receipt-v0.54.0.json`；
- receipt id：
  `challenger_cohort_failure_receipt_955e47c773683f1ae4ba7997a84badc373d3daf5afb24763bdc88d1b95d30545`；
- receipt hash：
  `3b2bcc2651bb80f58fb44d08ac4dfb2bdd9ab6c3ada4cfd83de00627ec8480b3`；
- exact size：55,482 bytes；
- runtime/Git SHA-256：
  `7907b97d4447039c686f53dc62694c37836417b4ae555d3322b16478319b85ae`；
- `cmp` 与 production loader：通过；
- status：`COHORT_MISSED_SLOT_FAILURE_VERIFIED`；
- equivalent evaluator：`FAILED_CLOSED_NO_BACKFILL` /
  `CHALLENGER_COHORT_CUMULATIVE_CONTINUITY_INVALID`；
- last/next/current slots：`00:00Z` / `04:00Z` / `12:00Z`；
- stderr occurrence count：2；launchd runs：2；
- historical backfill / continuity repair：false / false。

## 真实 decommission receipt

- runtime path：
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1/cohort-failures/challenger-cohort-decommission-receipts/challenger_cohort_decommission_receipt_30f87c50715e9f4c09b9b21072cb8c3f6fecf932d2703300adcf153fbab9323e.json`；
- Git artifact：
  `artifacts/challenger-forward/challenger-cohort-decommission-receipt-v0.54.0.json`；
- receipt id：
  `challenger_cohort_decommission_receipt_30f87c50715e9f4c09b9b21072cb8c3f6fecf932d2703300adcf153fbab9323e`；
- receipt hash：
  `56cfaa3f44b23e6dbc282f5947676ea93b4b92a89dcf90539a19eeb865b0bae7`；
- exact size：40,011 bytes；
- runtime/Git SHA-256：
  `540b831797228c950d954ee75b183fbeac08d63679463e14121fefc44fdf851f`；
- `cmp` 与 production loader：通过；
- status：`FAILED_COHORT_DECOMMISSIONED_VERIFIED`；
- fixed launchctl command count：5；fixed print count：4；bootout count：1；
- 后验：旧 service 未加载，固定 print rc=113、stdout 为空、stderr 为 exact not-found；
- operation failure receipt：0。

## 保留现场

停用前后 SHA-256 完全一致：

- state：`0052d799b4ab0cd31edf48fc1ba5d4f414c68998b78a31f9a66b46c2d94e35c7`；
- stdout：`68916d268d7ecc7b387877a70df28e20add34cd93ea54c5a8dd760d8aa1d10c2`；
- stderr：`ab446a5fd1eb21d5bbb69e3f9561abc8288361708031b5298e88833add547e64`。

所有 observer/decommission/release summary 的 market、Broker、order、strategy state
write、Runner invocation、maintenance invocation 均为 0。没有启动 replacement
Challenger 或 System Paper。

## 安全审查

第一次独立审查发现 receipt child symlink、非规范 receipt authority、TOCTOU、domain
projection、时间语义与失败取证问题；修复后第二次审查又复现最后 print 期间 receipt
替换、命令异常取证遗漏和 domain identity 未绑定。全部问题均先用 exploit-level 失败测试
复现，再修复；最终独立复审未发现 Critical/Important 问题，并给出受控生产序列 GO。

## 验证

- failure/decommission/release/install 聚焦与相邻回归：通过；
- committed artifacts canonical bytes、Schema、自哈希、固定 id/hash/size/SHA-256：通过；
- evaluator build input：244；manifest version：`1.48.0`；package version：`0.54.0`；
- evaluator tree hash：
  `d74fd96cfc1ceedcb2f733df3eac7758fddf2fd33ddeaef9616f5b89a99e24a4`；
- evaluator manifest hash：
  `51aaebf7eda47e35a0d5049498c29cb80f814f6a6ae2353c6f1fd9d7e6be5726`；
- compileall：通过；
- evaluator build：通过；全量 tests：753 项通过；
- `make validate`：命令通过，其中 release policy 按冻结安全设计输出 FAIL（缺少必需
  Policy 绑定且 `production_activation.enabled=false`），不构成发布失败；
- PR CI 与 main CI 在 GitHub 发布流程中复核。

## 尚未完成

本版本是失败证据与停用，不是盈利结论。原 90 天 cohort 永久不合格，不能继续累计或
用于提前 PASS。replacement Challenger 与 System Paper 尚未启动；它们必须使用全新
service/state/log/bundle/evidence roots，并在独立版本完成常在线、重启、时钟、磁盘、
网络与恢复预检后尽量同日自然启动，各自重新完成 90 天验收。

仓库仍没有批准 AI 模型、真实成交/实际滑点或实盘授权。`production_activation.enabled`
保持 false；即使后续研究门 PASS，也不等于可持续赚钱或可投入真实资金。
