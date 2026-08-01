# v0.54 Challenger Cohort 漏槽失败证据与受控停用设计

日期：2026-08-01

状态：冻结

冻结代码基线：`v0.53.0` / `d0a7f2e31c469c6983a205906d25e7b6f9d7e433`

失败观察基线：tag `v0.48.0` /
`09b81b9f3a670a20301d4b1090bb4293afc5bc7c`

上位设计：

- `docs/superpowers/specs/2026-08-01-challenger-paper-parallel-automation-design.md`；
- `docs/system-paper-readiness-audit-v0.53.0.md`；
- `docs/superpowers/specs/2026-07-31-challenger-cohort-cumulative-evaluator-design.md`。

## 1. 问题与裁决

原 confirmatory cohort 的最后可信 decision 槽为
`2026-08-01T00:00:00.000Z`，下一要求槽为
`2026-08-01T04:00:00.000Z`。Mac 在北京时间 2026-08-01 16:26 重启，Runner
在 16:27 自然启动时，可信当前槽已经晚于下一要求槽，正确返回
`CHALLENGER_RUNNER_MISSED_SLOT`。冻结 v0.48 evaluator 随后返回
`FAILED_CLOSED_NO_BACKFILL` / `CHALLENGER_COHORT_CUMULATIVE_CONTINUITY_INVALID`。

该 cohort 已永久失去 540 槽连续性资格。v0.54 必须：

1. 用冻结信任根只读重建失败事实；
2. 发布唯一、不可变、可重放的 failure receipt；
3. 在 receipt 已验证后受控停用旧 Runner LaunchAgent，阻止无意义的周期失败；
4. 保留 plist、install receipt、contract、state、WAL、logs、source bundles 和全部
   cohort evidence 原字节；
5. 明确禁止补槽、回填、清空状态、改时间戳、重新把旧 cohort 标成可完成；
6. 不启动 replacement cohort，不启动 System Paper，不发起市场请求，不接触 Broker、
   凭据或订单。

## 2. 方案比较

### 方案 A：失败 receipt 后受控停用（采用）

先封存完整失败证据，再只对固定旧 service 执行一次 `launchctl bootout`，保留所有现场
文件。优点是阻止每 4 小时重复三次时间请求和相同 stderr，同时拥有可证明的停用链；
缺点是需要新增停用 receipt 和严格前后观察。

### 方案 B：只封存失败，保持旧 service active

实现较少，但旧 Runner 永远无法越过缺槽，会持续产生失败、公共时间请求和日志噪声，
增加误判和运营成本，不采用。

### 方案 C：清空旧 state 并原地重启

会覆盖失败事实、复用 service/root 身份并形成证据混淆，违反 no-backfill 和不可变性，
禁止。

## 3. 信任根与固定输入

Failure observer/receipt 必须精确绑定：

- v0.43 cohort plan；
- v0.44 cumulative evaluation plan；
- v0.35 strategy install receipt、LaunchAgent contract 和 frozen plist；
- v0.48 production continuity code identity；
- 由上述 install chain 自动派生的唯一 service、SQLite、stdout、stderr 和 source bundle
  root；
- owner-only failure output root：
  `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1/cohort-failures`。

CLI 不接受 service、state、log、bundle、slot、clock、error、hash、status、root 内文件名、
PnL、价格、费用、日期选择器、命令或布尔 override。调用方只提供 plans、install chain
和 failure output root 的绝对路径。

Observer 在进程内读取一次可信 UTC wall clock；测试可以注入时钟，production CLI
不得暴露。系统 reboot time 只作为辅助 root-cause observation，不参与“漏槽成立”的
必要逻辑，也不允许覆盖 continuity 判断。

## 4. 只读失败观察

Observer 严格按以下顺序执行：

1. 使用 production loaders 验证 plans、install receipt、contract 和 plist；
2. 记录 state、WAL、SHM、stdout、stderr、bundle inventory 的 stat 与 SHA-256；
3. 使用 SQLite immutable/read-only 方式重放全部 decisions；
4. 验证从 cohort start 到最后 decision 的每个槽具有唯一 decision、source bundle 和
   stdout `RECORDED`；
5. 自动派生 `last_scheduled_for` 和 `next_required_slot`；
6. 要求可信 current slot 严格晚于 `next_required_slot`；
7. 要求 stderr 是唯一 exact canonical JSON 行
   `{"error":"CHALLENGER_RUNNER_MISSED_SLOT"}`；
8. 对固定 argv 执行一次 `launchctl print`，要求 service not running、last exit 1；
9. 复用 v0.48 的冻结 plan/state/partition/bundle/launchd 语义，在 failure-specific
   observer 内将“下一要求槽已过且 exact stderr 为 MISSED_SLOT”归类为
   `CHALLENGER_COHORT_CUMULATIVE_CONTINUITY_INVALID`；不得在内部再次调用 v0.48 CLI
   或执行第二次 `launchctl print`；
10. 再次记录所有现场 stat/hash，要求前后完全不变。

任何已存在后续 decision、重复/缺失 bundle、stdout 不一致、stderr 多行、service 正在运行、
last exit 非 1、文件变化、loader 失败或 continuity 原因不同，均失败关闭且不发布 receipt。

观察 summary 固定状态：

- `COHORT_MISSED_SLOT_FAILURE_VERIFIED`；
- `COHORT_FAILURE_NOT_YET_OBSERVABLE`；
- `FAILED_CLOSED_EVIDENCE_UNTRUSTED`。

后两者不发布成功 receipt。

## 5. Failure receipt

Receipt 至少包含：

- receipt schema/version/id/hash 与 `observed_at`；
- plans 和 install chain 的 id/hash/file SHA-256；
- service、固定 schedule 和 launchd 观察摘要；
- last decision、last slot、next required slot、current slot；
- verified prefix slot/decision count；
- state/WAL/SHM、stdout、stderr 与 bundle inventory 的前后 stat/hash；
- stderr exact bytes 的 UTF-8 文本、size 与 SHA-256；
- v0.48 evaluator code identity、等价 failure status 和 reason；
- root-cause observation：boot time 晚于 required slot，仅作辅助说明；
- launchctl print 固定为 1，market/Kline/Broker/order/state-write/Runner/maintenance
  invocation 固定为 0；
- 固定资格：old cohort `PERMANENTLY_INELIGIBLE_CONTINUITY_GAP`，replacement
  `NOT_STARTED`，Paper `NOT_STARTED`，Canary `NOT_AUTHORIZED`；
- warnings：禁止 backfill、旧证据永久保留、失败不代表策略收益好坏。

唯一输出路径：

`<failure-output-root>/challenger-cohort-failure-receipts/<receipt-id>.json`

根目录和子目录 mode 0700，文件 mode 0600、单 hardlink、canonical compact JSON、
no-overwrite。相同输入重复调用保持 bytes、inode、mtime 不变；同路径不同 bytes 失败。
Production loader 必须重新执行 Schema、自哈希、路径、权限、source identity、continuity
语义和安全计数验证，不能只验证 self-hash。

## 6. 受控停用

停用是独立阶段，不与 failure receipt 发布合并：

`OBSERVE_AND_PUBLISH_FAILURE -> VERIFY_RECEIPT -> DECOMMISSION_PREFLIGHT -> BOOTOUT -> VERIFY_DECOMMISSION -> PUBLISH_DECOMMISSION_RECEIPT`

前置条件全部满足才允许继续：

- failure receipt 已由同版本 production loader 重放；
- receipt 绑定当前 exact install chain 和 service；
- service not running、last exit 1；
- 当前 state/log/bundle hashes 仍等于 failure receipt 的 after snapshot；
- service 精确为 `gui/501/local.crypto-quant.challenger-forward`；
- replacement service 和 System Paper service 均不存在；
- 禁止传入任意 launchctl command 或 service override。

唯一允许的状态变更是对固定旧 service 执行一次等价于：

```text
/bin/launchctl bootout gui/501/local.crypto-quant.challenger-forward
```

实现必须使用固定 argv、无 shell。不得删除或修改 plist、state、logs、bundles、receipt、
archive、result 或 install files。bootout 后固定 `launchctl print` 必须证明 service 不再
加载；所有现场文件 stat/hash 必须保持不变。

Decommission receipt 绑定 failure receipt exact bytes、bootout 前后 service 观察、固定
argv identity 和所有保留文件 after snapshot。输出到同一 owner-only failure root 的
`challenger-cohort-decommission-receipts/`，使用相同不可变发布规则。若 bootout 返回失败或
后验不可信，保存结构化失败 stdout/stderr，不伪报停用成功；旧 cohort 仍保持失败资格。

## 7. Replacement cohort 边界

v0.54 不创建、不安装、不启动 replacement cohort。后续独立设计必须：

- 使用新 cohort id、start/tail、service、state、log、bundle 和 evidence roots；
- 把 v0.54 failure receipt 和 decommission receipt 作为 predecessor；
- 不复制旧 decisions、Episode、receipt、archive、result 或天数；
- 在可靠常在线环境完成电源、重启、时钟、磁盘、网络和恢复验收；
- 与冻结 System Paper 尽量同日自然启动，各自独立计时；
- 未经过新的设计、计划、测试、PR/main/tag、安装预检和明确批准前不得启动。

## 8. 测试与验收

- 设计提交与实现提交分离；
- 正常 fixture 发布 canonical failure receipt，并由 production loader 重放；
- current slot 未晚于 next、stderr 为空/多行/错误、last exit 不符均不发布；
- internal gap、重复/缺 bundle、stdout 缺行、state/log 观察中变化均失败；
- production CLI 无 clock/service/state/log/slot/error/command override；
- 100 次 deterministic build 和 idempotent publish；
- decommission preflight 的任一 hash/service/receipt 不符时 bootout 调用次数为 0；
- 成功 fixture 只调用一次固定 bootout，文件前后 hash 全部不变；
- subprocess argv 测试证明无 shell、无删除、无 Runner、无 maintenance；
- runtime 当前现场先只读 observer，再发布 exact receipt；
- 只有 runtime receipt loader 复核成功，才允许在独立操作步骤执行受控停用；
- focused、相邻、全量 tests、Schema mirrors、compileall、evaluator build 和
  `make validate` 全部通过；
- failure receipt 和 decommission receipt 分别逐字节进入 Git，PR/main/tag 精确对齐。

## 9. 对赚钱目标的意义

漏槽不提供收益结论，但它暴露了运行基础设施无法保证 90 天连续在线。封存失败并停用
无效 cohort，避免系统继续制造看似活跃却统计无资格的数据。后续把 replacement
Challenger 与 System Paper 放到可靠常在线环境同日启动，虽然重新付出观察时间，却能让
最终收益、风险和运行结论建立在真实连续证据上；这是比保留虚假进度更接近赚钱目标的
选择。
