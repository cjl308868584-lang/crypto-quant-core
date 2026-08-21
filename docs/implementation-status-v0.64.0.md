# 实施追踪 v0.64.0

日期：2026-08-21

状态：`PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED`

## 本版本完成

- 发布 replacement v2 plan：file SHA-256
  `5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f`，plan ID
  `challenger_replacement_plan_65d85d60a534a917f45a1ffa5fc9d3f74d6d24995b900d31b8c73cd26f0bd97b`，
  plan hash `c9a1e5f74c52fbf23be5a1d27fd23c25f3601ed58133178fc25480391ab65705`；
- 将 v0.62 的 SQLite/source-bundle/decision 路径合同显式 supersede 为 append-only
  canonical event log 权威和非权威、可重建 exports；
- 保持 v0.62 原文件 SHA-256
  `d450d1e9f8dc422eb5a93beb8a5ffbb1746a4a6d1facb3c5a20a76f4bd527734`、annotated tag
  和 peeled commit `e0a9b3eb6a3f385ea259722e6613df8708e8fe5a` 不变；
- 冻结参数无关 machine collector、安全 no-replace publisher、严格 Schema/loader、
  accountable owner attestation 和 supersession record；
- 用公开、只含 8 文件的 parentless R3 仓库实证 Linux Python 3.9/3.12
  `renameat2(RENAME_NOREPLACE)` 边界。公开 commit
  `460ec57568e863b2e39e7572193f2545542d586b`，tree
  `2ab63c4fdecb06d0a4498365b9debd53a122a2ba`，Actions run `32435172937` 成功。R1/R2
  失败仍作为不可变 ancestry 保留。

## 正式治理证据

| 对象 | 身份 | 外部文件 SHA-256 |
|---|---|---|
| Machine evidence | `challenger_replacement_supersession_machine_evidence_79ba192b18f7427d0ed78ff04a56c2b0812f66f87ef28fb65dd15ca7bdfd8ca7` / `7d1be628c1e75172dbb536351be1c8e7940d74bd0a828e6390fdae33b8a5f264` | `dd5e7970f4cfbfab71e9dec2894ce6ff96895dd20757dd8165acda9922939968` |
| Owner attestation | `challenger_replacement_owner_attestation_da8fba9c6d090cb2ed95ea02a4cabd7c6696b54b331d8b104b8b6c0bc1796a05` / `6572c417f9c8959e42d9a689625ed69e2568a4ebcd9f369dc59e384cbb38c32d` | `321087e3af1ab854d41519252c77710462eee85b1a96a4b2910962e4f046baaf` |
| Supersession record | `challenger_replacement_plan_supersession_e2bb0a9de3a639c97474a016ff52ab30ae6148be1a93426ab7ba351898efdbd3` / `ef1ae1fabce6b0d868b8bce855465b0221861c116e88ba64c15a92355b5693de` | `8e5dce22cfb21f7a87fe5756dadbef7736bad12e6343a1bb1c503bd609252dd8` |
| Public Linux R3 witness | `PUBLIC_LINUX_PORTABILITY_WITNESS_COMPLETED` / witness hash `f90c46551bf08b4b22509c0946576359cfa9186494c7925ef292639629c1a32a` | `2b6d8639baab5d637605f62e92f0ab217681d25b29c7b90e4f754fd42f52c1d2` |

Machine evidence 在 `2026-08-21T01:52:24.909Z` 观察到 runtime root/plist 不存在、
service 未加载、当前树内 start receipt/canonical event 计数为 0；collector 的
Runner/market/Broker/order/state-write 计数均为 0。这些只是采集时机器事实。

Owner `cjl308868584-lang / chenm4 / uid 501` 于 `2026-08-21T07:52:38.055Z`
签署历史声明，承担 replacement 在该时点前从未 install/start，也未生成 start
receipt、canonical event、real slot 或 production state write 的责任。声明 SHA-256
为 `408d98e2cccf6329a9db5ef1f3b5ad9e40c1e7cec22e86582e00b24f1820c7b0`。

Snapshot、Git history、Schema 和 loader 都不证明该历史声明为真；它们只验证
当前事实、不可变历史、结构、哈希和绑定。

## Release identity 与范围

- package：`crypto-quant-core 0.64.0`；
- evaluator build：`release-evaluator-build-v1@1.58.0`；
- 构建清单单向绑定本版本 code/Schema/artifact/docs/tests 与 R3 witness；最终
  `build_input_tree_hash` 和 `manifest_hash` 以
  `config/evaluator-build-manifest-v1.json` 的 strict loader 验证值为权威；
- v0.64 没有 replacement runtime、deployment、installer、observer、exporter、evaluator、
  production root/plist/service 或 start receipt；
- 没有迁移、回填、补槽、重置起点、市场请求、凭据、Broker、资金或真实订单。

本版本不开始 replacement 的 90 天/540 槽位计时，不证明策略盈利、AI 优势、
System Paper 完成、Canary 或实盘资格。`production_activation=false`、
`runtime_install_authorized=false`、`replacement_start_authorized=false`、
`real_orders_allowed=false` 保持。
