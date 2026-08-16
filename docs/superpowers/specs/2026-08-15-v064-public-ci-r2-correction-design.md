# v0.64 公开 Linux CI R2 纠错设计

**状态：** 已批准的设计，尚未实施
**设计日期：** 2026-08-15
**私有候选基线 `F`：** `1967f79ff8d013bf149bf36e2cdcb6a81ed200ff`
**基线 tree：** `5389cc01164ce6dd5955df1d014e974f4bf1a104`
**失败公开仓库：** `cjl308868584-lang/crypto-quant-v064-public-ci`
**R2 公开仓库候选名：** `cjl308868584-lang/crypto-quant-v064-public-ci-r2`

## 0. 决策摘要

第一次公开 Linux witness 必须永久保留为失败。不得 rerun、删除、强推、改写、归档、复用
其仓库或把失败解释成 GitHub 基础设施问题。

R2 是一个新的、预注册的工程纠错候选：使用新私有候选 `F2`、新公开仓库、新的无父根提交
和一次新的 owner-push 运行。它只纠正公开 workflow 的两个已实证预检 false-positive，不改变 replacement
Challenger 的研究假设、Linux publisher、测试语义、阈值、v0.62 plan、owner ceremony、
资金权限或版本路线。R2 成功也只能形成 Linux portability witness，不能形成盈利、AI 优势、
Paper、Canary 或实盘结论。

## 1. 不可变失败前置证据

R2 的所有设计、manifest、witness 和后续私有状态必须精确绑定下列前置事实：

| 字段 | 精确值 |
|---|---|
| 公开仓库 | `cjl308868584-lang/crypto-quant-v064-public-ci` |
| 私有 source candidate `F` | `1967f79ff8d013bf149bf36e2cdcb6a81ed200ff` |
| 私有 `F` tree | `5389cc01164ce6dd5955df1d014e974f4bf1a104` |
| 失败公开 commit | `0429837e5de8052e9e8216ed08ba9c7aa9c905b3` |
| 失败公开 tree | `4ebb723e73dc9eb43b7273febd96af3ef87ef951` |
| bundle manifest SHA-256 | `c238c904495b167e436b2c32e822d8fa55285e42eaaad8e095805e73570e3fd7` |
| file-set SHA-256 | `2d7ed3d4b3380b43e50f16f04113eae46360397e46aeba2edd639ce46a7f76c7` |
| workflow blob OID | `d2c0104eafb8e1aa5ea68a60f716921f2668ce42` |
| Run ID / attempt | `31850146784` / `1` |
| Run event / branch | `push` / `main` |
| Run status / conclusion | `completed` / `failure` |
| Python 3.9 Job | `94924270273`, `failure` |
| Python 3.12 Job | `94924270340`, `failure` |
| 固定错误码 | `PUBLIC_SENSITIVE_BYTES_INVALID` |
| Run JSON SHA-256 | `f442ae366539fc4a244977fdafb2cd5de383b4248483381d8d79b751ea6a6099` |
| Jobs JSON SHA-256 | `9a69273c07548e97dbc2f43883eea4b5935f84256b7ad95b2874ca498bc67923` |
| 完整 log SHA-256 | `e47462120131eadb3161a40ffe679f4f74889103d7b3a13bb563df705f9ef32c` |
| Transcript summary SHA-256 | `cd2072e246698bec6d8767d37da4a3dca82d09fc38466a8009aea9690a0c9790` |

两个 Job 都在 `Verify closed bundle before repository imports` 失败；真正的
`Run fixed-owner public boundary` 步骤均为 `skipped`。日志中没有 `Ran N tests` 或 `OK`
结果标记。因此第一次运行既不是 Linux 测试 PASS，也不是 runner 分配前的基础设施失败，
不符合一次性 rerun 条件。

## 2. 根因与覆盖缺口

公开 workflow 将全部八个公开文件（包括 workflow 自身）交给敏感字节扫描。扫描器的规则源
中明文出现 `BEGIN PRIVATE KEY`，因此扫描 workflow 本身时必然命中自己的规则文本，产生
`PUBLIC_SENSITIVE_BYTES_INVALID`。

私有 exporter 的预发布扫描没有暴露该问题，因为其私钥 marker 是不同的精确形式
`-----BEGIN PRIVATE KEY-----`，而 public workflow 的运行时扫描使用更宽的
`BEGIN PRIVATE KEY`。现有测试验证了模板能通过私有扫描器，却没有在真实八文件 Git checkout
中执行 workflow 内嵌的 exact preflight script。根因是两条扫描边界缺少行为等价回归，不是
GitHub runner、Python 版本、Linux primitive 或 publisher 缺陷。

## 3. 方案比较与选择

### 3.1 新 R2 仓库和新根提交：采用

创建 `cjl308868584-lang/crypto-quant-v064-public-ci-r2`。它从一个新的无父根提交开始，
继续要求精确八文件、只读 token、固定 action SHA 和一次 owner-push 运行。失败的原仓库保持
原样，两次尝试的身份不会混在一个 Git history 或 branch 中。

### 3.2 在原仓库追加或改写提交：拒绝

追加提交会破坏“一个根提交、一个精确候选”的已批准合同；force-push、删除或重建会削弱
失败证据可发现性。原仓库不接受任何后续 branch、tag、release、workflow rerun 或 commit。

### 3.3 放弃 Linux witness：拒绝

这会让 v0.64 在已冻结的 Linux 实证门上永久不完整。R2 是对工程测试 harness 的透明纠错，
不是为了寻找更好的策略或经济结果。

## 4. 允许变化与禁止变化

### 4.1 `F2` 身份

`F2` 必须是 `F` 的严格后代。它只能包含：

- 本 R2 design、后续 implementation plan 和相应治理状态说明；
- R2 public repository 常量与固定 candidate root；
- bundle/witness Schema 中的 R2 repository 与 predecessor-failure 绑定；
- workflow 的 repository identity 和自扫描安全编码；
- private-only bundle/witness 回归测试；
- 因上述 exact inputs 变化而机械更新的 evaluator build manifest。

`F2` 中下列公开业务 bytes 必须与 `F` 的 Git blobs 完全一致：

- `src/crypto_quant/challenger_replacement_supersession_publish.py`；
- `tests/test_v064_linux_supersession_publish.py`。

Linux primitive、错误码、UID 501、crash/race 测试、owner-only path 规则和 sentinel 快照合同
均不得为了让 R2 变绿而修改。

### 4.1 自扫描修正后暴露的第二个预检 false-positive

私有 TDD 先精确复现首次公开失败，再拆分 marker 后，exact embedded preflight 继续运行并
稳定返回 `PUBLIC_SUBPROCESS_TARGET_INVALID`。AST 诊断表明，冻结 Linux 测试中六个受审子进程调用
有五个被原规则接受；唯一被误拒绝的是 `CRASH_CHILD` 的固定 `"directory-fsync"` crash-point
参数。首次公开 Run 在更早的自扫描门已终止，因此当时不可能观测到这个后续缺陷。

R2 允许的第二项修正只能是：在 fixed-Python-child 检查中，对 `CRASH_CHILD` 的最后一个参数
精确允许字面量 `"directory-fsync"`。不得允许其他 `Constant`、其他 child、其他位置、任意 crash-point、
动态命令或新 subprocess target。导出 Linux 测试 blob 仍必须与 `F` 字节相等。

### 4.2 全局禁止项

R2 不得新增或执行 scheduler、deployment、Runner、Broker、订单、凭据、网络行情、production
root、策略 state、owner attestation、正式 plan artifact、私有 merge/tag 或任何资金操作。
`production_activation=false`、`credentials_present=false`、`broker_allowed=false`、
`orders_allowed=false`、`runtime_state_write_allowed=false` 必须保持。

## 5. R2 manifest 与 predecessor failure

公开文件集仍精确为八个路径，文件名 `bundle-manifest-v1.json` 保持；其
`schema_version` 从 `1.0.0` 升为 `1.1.0`，增加唯一必填对象
`predecessor_failed_public_witness`。该对象精确包含第 1 节的：

- predecessor repository、private `F`/tree、public commit/tree；
- manifest/file-set/workflow identities；
- run ID、attempt、event、branch、status、conclusion；
- 两个 job ID/name/conclusion 和两个测试步骤的 `skipped` 事实；
- fixed reason code；
- Run/Jobs/log/transcript 四个 SHA-256。

R2 manifest 的 `public_repository` 必须为
`cjl308868584-lang/crypto-quant-v064-public-ci-r2`，source candidate 必须为 exact `F2`。
Schema 在每个对象边界使用 `additionalProperties=false`，所有整数保持 JSON safe integer，
所有 Git OID 固定 40 位小写 SHA-1，所有 SHA-256 固定 64 位小写十六进制。

原 v1 公共 manifest bytes、原公开 commit/tree 和原 GitHub run 不由新 loader 重新解释或改写；
它们只作为 predecessor failure 的精确输入身份存在。

## 6. Workflow 最小纠正

R2 workflow 保持原事件、权限、action SHA、matrix、owner UID、HOME/TMPDIR、测试命令和
closed-file verifier 不变。只允许以下语义变化：

1. 固定 repository 改为 R2 名称；
2. 敏感 marker 在 workflow source 中使用不会自匹配的字节片段构造，例如
   `b"BEGIN " + b"PRIVATE KEY"`；
3. fixed child 参数检查只额外接受 `CRASH_CHILD` 末位的精确 `"directory-fsync"`；
4. 运行时组合后的 marker 仍精确检测 `BEGIN PRIVATE KEY`；
5. workflow 不得通过排除自身、忽略 workflow path、删除规则、允许任意常量或扩大 allowlist 来变绿。

`/Users/`、token prefix、email、URL 和业务禁词的运行时规则继续有效。任何 marker 的 source
编码方式都必须由 private-only 测试证明“source 不自匹配、runtime 能命中真实 payload”。

## 7. TDD 与行为等价门

实施必须严格先 RED 后 GREEN，并至少覆盖：

1. **精确失败重现：** 从 `F` 的 workflow 提取唯一 heredoc preflight，在真实八文件临时 Git
   checkout 中运行，RED 必须得到 `PUBLIC_SENSITIVE_BYTES_INVALID`；这条测试绑定失败根因，
   不修改或重新执行 GitHub Run。
2. **R2 exact preflight：** 从 R2 workflow 提取同一边界并在 R2 八文件 candidate 中运行，
   要求 exit 0、stderr empty，并输出 source candidate、public commit、manifest 和 file-set marker。
3. **真实负例：** 分别向非 workflow 文件注入运行时构造的 private-key marker、token、
   `/Users/`、email、非 allowlisted URL 与业务禁词，exact preflight 必须以固定错误码拒绝。
4. **不允许测试自证：** 测试不能复制一份“修正后的扫描逻辑”代替执行 workflow 内嵌脚本；
   只能确定性提取 exact heredoc 并通过 fresh process 执行。
5. **closed Git checkout：** preflight 必须看到 exact tracked eight-file set、真实 blob OID、
   manifest hash 和无额外 tracked/untracked file；fixture 不得 mock Git hash-object/ls-files。
6. **原业务 blob 不变：** 用 `git show F:path` 对 publisher 和 Linux test 做 byte/OID equality。
7. **前置失败绑定：** 任一 predecessor field、hash、job、step 或 reason code mutation 均被
   manifest/witness Schema 与 loader 拒绝。
8. **R2 root replay：** candidate 必须只有八个文件、一个无父根提交、确定性 tree/commit；
   no-overwrite 和 sensitive scan 继续失败关闭。

生产代码不得新增 callback、fault injector、任意 output path、任意 repository、任意 run 结果
或人造 PASS 输入。

## 8. 私有 witness 结果合同

R2 成功时，私有 witness 必须同时绑定：

- 第 1 节的全部失败前置证据；
- R2 repository、root commit/tree、workflow blob、manifest/file-set；
- R2 的唯一 run、两个 job、exact steps、raw API/log/transcript bytes；
- `F -> F2 -> G2` 严格 ancestry；
- publisher/Linux-test blobs 从 `F` 到 `F2/G2` 不变；
- 所有交易与 production safety flags 为 false。

若 R2 任一 job 为 failure/cancelled/skipped，或 identity/日志/步骤不一致，则不得生成成功 witness
或 `G2`。只有 GitHub infrastructure 在任何验证/测试步骤执行前失败，才允许对 exact R2 commit
做最多一次 rerun；否则保留失败并停止，不自动设计 R3。

## 9. 审查、测试和发布顺序

1. 提交本 design；用户复核后编写独立 implementation plan；
2. 按 TDD 完成 Schema、loader、workflow、private-only tests 和 builder/CLI identity；
3. 每个 final code state 跑 focused/adjacent、compileall、diff-check；
4. 最终 `F2` code state 本地全量测试一次，不重复机械全量；
5. 独立完整审查一次，Critical/Important 清零；修复后只做针对性复审；
6. 构建并重放 owner-only R2 candidate，生成 exact 八文件/size/SHA/blob/manifest/commit/tree 审批包；
7. 单独向用户请求创建 R2 公开仓库、推送 exact root、运行一次 workflow、读取并封存结果；
8. 未获该精确批准前，不创建仓库、不推送、不 dispatch；
9. 成功 witness 与 `G2` 完成后，再单独请求私有 push/Draft PR/merge/tag 权限；
10. v0.65 Nautilus end-to-end Spike 与 v0.66 replacement runtime 排期保持不变。

## 10. 可证伪验收标准

R2 只有在以下事实全部成立时才能形成成功 portability witness：

- 原失败仓库、commit、run 和 logs 仍可读取且精确匹配第 1 节；
- R2 使用全新公开仓库和全新无父根提交；
- R2 public tree 精确八文件，无额外 history/ref/tag/release；
- workflow source 不包含会被自身 runtime rule 命中的完整 marker；
- exact embedded preflight 在真实 R2 checkout 成功，并对真实敏感 payload 失败；
- GitHub-hosted Ubuntu Python 3.9/3.12 都实际执行 Linux test，`Ran N tests` 与 `OK` 可由
  raw log 推导，且没有 skip/mock/fallback；
- production loader 从 exact raw bytes 推导结论，人不能传入 status/PASS/version/timestamp；
- predecessor failure 和 R2 success 同时进入最终私有 witness；
- 私有 full suite、review、build identity 和 unchanged-blob proof 均有精确证据；
- 没有扩大任何研究、资金、安装或交易权限。

任一条件缺失时，状态只能是 failure/inconclusive/pending；不得把 R2 或 v0.64 描述为已通过。
