# v0.64 最小公开 CI 镜像设计

**状态：** 设计候选，未创建公开仓库，未上传任何文件
**私有候选基线：** `1809bd5e913ee8ac208ad5c267c391fa33983ff5`
**当前私有 Draft PR：** `cjl308868584-lang/crypto-quant-core#32`
**公开仓库候选名：** `cjl308868584-lang/crypto-quant-v064-public-ci`

## 0. 治理身份

```text
PRIVATE_PR_CI_NOT_EXECUTED_BILLING_BLOCKED = run 31436609135
PUBLIC_SOURCE_CANDIDATE_F = reviewed private source commit exported byte-for-byte
PUBLIC_LINUX_PORTABILITY_WITNESS_NOT_PRIVATE_PR_CHECK = independent bound transport
POST_WITNESS_PRIVATE_CANDIDATE_G = strict descendant of F with unchanged public-source blobs
```

这些身份只修订 v0.64 Task 5 前不可用的 Linux transport。测试语义、阈值、私有 release
authority、v0.62 bytes/tag、owner approval 与原 Task 5-8 ceremony 均不改变。

## 1. 问题与目标

`crypto-quant-core` 必须保持私有。GitHub Actions 在 2026-08 计费周期已用完该账户的
2,000 免费 Linux 分钟；账号没有预算限制、没有待付账单，也没有付款方式。私有 PR #32 的
GitHub-hosted Python 3.9 任务在 runner 分配前失败，Python 3.12 任务被取消；它们不是代码或
测试失败。

v0.64 的冻结设计要求在 Task 5 产生正式 plan artifact 前，使用 Linux Python 3.9/3.12
实际执行 `renameat2(RENAME_NOREPLACE)` 路径。不允许用 macOS 结果、mock 或合成 PASS 替代。

本设计的目标是：

1. 不公开私有项目及其 Git 历史；
2. 使用一个永久保留的最小公开仓库，运行免费的标准 GitHub-hosted Linux runner；
3. 只证明冻结候选中与 Linux 平台相关的 no-replace、竞态、崩溃与文件身份边界；
4. 将公开 bundle 的每个 byte 绑定到一个精确私有候选提交；
5. 不把公开镜像 CI 伪报为私有 PR 的原仓库 CI；
6. 不创建 runtime、service、owner attestation、交易权限或任何 production state。

## 2. 方案比较与选择

### 2.1 直接公开 `crypto-quant-core`：拒绝

它会公开 371 个已观察历史提交、41 个运行/证据 JSON、个人提交邮箱、本机路径与
Actions 历史。一旦有人 fork，以后改回私有也不能收回公开副本。节省 CI 费用不足以支持
这个不可逆风险。

### 2.2 本机 self-hosted Linux runner：保留后备

它不消耗 Actions 分钟，但当前 Apple M4 主机没有现成 Linux 虚拟化/容器边界。安装虚拟化、
runner 注册和系统权限会引入比本问题更大的运维面。

### 2.3 最小公开 CI 镜像：采用

一个全新公开仓库从单一 root commit 开始，只公开实际 Linux 门所需的最小 bundle。
主项目保持私有，公开仓库永久保留作为可重放的发布证据。

## 3. 威胁模型与不可超出的声明

### 3.1 要防御

- 把错误或额外私有文件发布到公开仓库；
- 公开 bundle 文件与已审查私有 commit 不一致；
- workflow 在验 hash 前执行未绑定代码；
- 可变 action tag、过宽 GitHub token 或 `pull_request_target` 引入供应链/外部 PR 执行风险；
- 把 public-only 测试结果扩大为完整系统、盈利、AI 优势或实盘资格证明；
- 公开仓库发生后续篡改却仍被私有发布链引用。

### 3.2 不声称防御

- GitHub 平台或账户本身被完全控制；
- 一个能同时改写私有候选、公开镜像、GitHub 运行结果和最终私有发布记录的强攻击者；
- 镜像对整个私有项目的行为等价；
- 公开仓库删除或再私有后，历史副本会从互联网消失。

## 4. 双仓库权威边界

### 4.1 私有仓库是唯一项目权威

`cjl308868584-lang/crypto-quant-core` 继续唯一承载：

- v0.62/v0.64 plan、Schema、ADR、status 和构建清单；
- 所有策略、System Paper、Challenger、receipt、result 和 evaluator；
- owner attestation 与 supersession record；
- 最终 merge、annotated tag 和 release 身份。

公开镜像不是 plan、state、artifact、result 或发布权威。

### 4.2 公开仓库只是 Linux portability witness

`crypto-quant-v064-public-ci` 只回答：

> 与精确私有候选绑定的这些公开 bytes，是否在 GitHub-hosted Ubuntu 的 Python 3.9 和 3.12
> 上实际通过冻结 Linux no-replace/竞态/崩溃测试？

它不回答策略是否正确、是否赚钱、是否能启动、是否可下单或私有仓库的全量测试是否通过。

## 5. 精确公开文件白名单

公开 root commit 只允许下列相对路径；manifest 必须要求文件集合精确相等，不得仅验证
已知文件的 hash：

1. `.github/workflows/ci.yml`
2. `.gitignore`
3. `README.md`
4. `SECURITY.md`
5. `NOTICE.md`
6. `bundle-manifest-v1.json`
7. `src/crypto_quant/challenger_replacement_supersession_publish.py`
8. `tests/test_v064_linux_supersession_publish.py`

### 5.1 私有候选原样文件

`src/crypto_quant/challenger_replacement_supersession_publish.py` 必须与私有候选的同路径 blob 逐字节
相等。公开过程不得删除项目名、改错误码、改 UID 或重写 OS primitive；否则测试的就不是候选
代码。

公开测试通过 `importlib.util.spec_from_file_location` 从固定路径加载单一 publisher 模块，因此
`src/crypto_quant/__init__.py` 和 `tests/__init__.py` 都不需要，且禁止用空占位文件把它们加回公开集合。

### 5.2 新增的 public-only 测试

`tests/test_v064_linux_supersession_publish.py` 必须先在私有候选中用 TDD 实现、审查和提交，
然后原样复制到公开镜像。它只允许标准库，不读取 v0.62 plan、正式 artifacts、Git 历史或本机
路径。它至少覆盖：

- Linux 符号 `renameat2` 存在，且调用确实使用 `RENAME_NOREPLACE`；
- 既有 final 返回 `EEXIST`，不覆盖、不改 inode/bytes/mode/nlink/mtime/ctime；
- 两个 fresh interpreter 直接竞争 primitive，精确一个 `SUCCESS` 和一个 `EEXIST`；
- file fsync、no-replace 前后、directory fsync 前后的 fresh-process 崩溃/恢复语义；
- symlink、hardlink、FIFO、socket、directory、wrong mode、wrong uid 在 read/write 前失败关闭；
- `ENOSYS`/`EOPNOTSUPP`/`ENOTSUP` 与缺少 flag/symbol 的固定 unsupported 映射，无 `os.rename`、
  `os.replace`、hardlink 或 flag=0 fallback；
- short write/EINTR、fd close、post-fsync attachment replay 与 orphan blocking；
- 所有拒绝路径的 external sentinel bytes/mode/size/mtime/ctime/inode/nlink 完全不变。

### 5.3 永不公开

- `artifacts/` 和 `docs/` 中的私有历史、receipt、result、plan 或 owner declaration；
- 除第 5 节白名单外的所有 `src/`、`tests/`、`config/`、workflow 和构建文件；
- `.git/`、私有 commit message、author email、branch 列表、tag 列表或 Actions 旧日志；
- `/Users/chenm4`、LaunchAgent label、production root、账户余额、凭据、策略参数或经济结果；
- owner attestation、machine absence evidence 或 supersession record。

## 6. Bundle manifest 与绑定协议

`bundle-manifest-v1.json` 使用唯一、确定、带 LF 的 canonical JSON，且是不包含自身的外部
清单。它至少包含：

- `schema_version = 1.0.0`；
- `purpose = V064_LINUX_PORTABILITY_WITNESS_ONLY`；
- `source_private_repository = cjl308868584-lang/crypto-quant-core`；
- `source_candidate_commit`；
- `source_candidate_tree`；
- `private_release_baseline = df91e19240df14839125608422489adf3b902e76`（`v0.63.0^{}`）；
- `source_private_pr = 32` 或取代它的精确私有 Draft PR；
- `public_repository = cjl308868584-lang/crypto-quant-v064-public-ci`；
- 每个白名单文件的 path、size、SHA-256、source kind；
- 对原样文件额外记录私有 Git blob OID；
- `file_set_sha256`：对排序后 `(path, size, sha256, source_kind, source_blob_oid_or_null)`
  的 canonical 对象求 hash；
- `production_activation=false`、`credentials_present=false`、`broker_allowed=false`、
  `orders_allowed=false`、`runtime_state_write_allowed=false`；
- 公开声明的精确列表，包括“不是全量 CI”和“不是盈利/实盘证明”。

私有 exporter/verifier 必须在创建公开 Git commit 前：

1. 从精确 source commit 的 Git object database 读取原样 bytes，不从可变 worktree 复制；
2. 要求 source commit 是当前已审查私有分支 HEAD；
3. 对新增 public-only 文件要求已由同一 source commit 跟踪；
4. 对所有文件执行 exact set/hash/size/mode 验证；
5. 扫描精确 bytes，拒绝凭据格式、绝对 home 路径、邮箱、非白名单 URL 和禁止术语；
6. 在临时 owner-only staging 生成整个公开 tree，最后重放 manifest；
7. 若目标仓库非空、已有其他历史或文件集不等，失败关闭。

### 6.1 两阶段私有提交身份

- `F` 是 **public-source candidate**：它包含已审查的 publisher、public-only test、exporter/verifier
  和 witness loader 代码。公开 manifest 的 `source_candidate_commit/tree` 精确绑定 `F`；Linux CI
  证明的也只是 `F` 中被导出的 bytes。
- `G` 是 **post-witness private candidate**：它是 `F` 的严格后代，只在公开 CI 完成后新增
  exact public witness 与相应 regression/manifest 绑定。`G` 不被反向写入早已运行的公开
  manifest，否则会产生循环。
- Task 5 及后续 v0.64 ceremony 从 `G` 继续；它们必须同时证明 `G` 是 `F` 的后代，
  且 `F` 中所有公开源文件的 blob OID 在 `G` 中仍精确不变。

public witness 自身只绑定 `F`、public commit/tree 和 run evidence；它不包含尚未存在的 `G`
OID。`F→G` 的 ancestry/unchanged-blob 结论由 `G` 提交后的 verifier、regression 和 build manifest
外部绑定，不反向写入 witness。

## 7. 公开 workflow 合同

workflow 只在 owner push 和手动 `workflow_dispatch` 上运行，不监听 `pull_request`、
`pull_request_target`、issue、comment 或 fork 事件。第一个执行步骤必须在 Python import 前：

1. 验证 GitHub repository 和 ref 是固定的公开仓库 `main`；
2. 验证 worktree tracked/untracked 精确集合；
3. 重算全部文件 hash/size/blob 和 `file_set_sha256`；
4. 静态拒绝非白名单 import、网络、subprocess 目标、凭据、交易或 production path；
5. 输出 source candidate commit、当次 `github.sha`、manifest SHA-256 和 file-set SHA-256。

manifest 不包含 public commit OID 或 public tree OID；否则它会通过自身 blob 形成不可解的
自引用。public commit/tree 只由 GitHub push event/run 和私有 witness 在提交完成后外部绑定。

只有预检通过才运行 Python 3.9/3.12 matrix。其他要求：

- `runs-on: ubuntu-latest`，不使用 larger/self-hosted runner；
- `permissions: contents: read`，无 secrets、OIDC、packages、cache、artifact upload 或发布权限；
- `actions/checkout` 锁定 `fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09`，
  `actions/setup-python` 锁定 `ece7cb06caefa5fff74198d8649806c4678c61a1`，不使用浮动 `@vN`；
- checkout 是唯一先于 bundle 验证执行的第三方 action，必须使用 `persist-credentials: false`；
  bundle 验证之前不得 import/执行仓库 Python 或其他仓库脚本，只允许 workflow 内联 shell 验证；
- 不安装项目 package 或第三方 Python 运行依赖；
- Python 3.9/3.12 两个 job 都必须实际执行，不允许 skip/continue-on-error；
- 每个 job 都必须先 fail-closed 确认 UID/GID 501 未被占用，再创建临时用户/组与 owner-only
  HOME/TMPDIR/workspace，复制已验证 bundle 后固定 owner/mode，最后以真实 euid 501 执行测试；
  不允许 mock `geteuid`、修改 publisher 的 501 合同或用 root 直接跑边界测试；
- 每个 job 都必须输出 `sys.version`、`platform`、kernel release、glibc 身份和公开 commit；
- 失败或取消必须保持失败，不重跑以寻找更好结果。只有 GitHub 基础设施失败且无
  test step 时，才可对同一 exact public commit 重跑一次。

workflow 不硬编码 manifest SHA-256；manifest 已包含 workflow 文件身份，反向在 workflow 中硬编码
manifest SHA 会产生另一个不可解的循环。workflow 只根据 manifest bytes 重算非 manifest 文件集；
public commit/tree/workflow/manifest 的整体身份由推送前批准包和推送后私有 witness 外部绑定。

## 8. 结果回流与私有发布门

公开 CI 通过后，私有候选中创建一份不自引用的 `public-ci-witness-v1.json` 候选，其 bytes
由专用 builder 自动从固定输入派生，不允许人工输入 PASS。它绑定：

- 精确 private source commit/tree/PR；
- 精确 public repository/commit/tree；
- public bundle manifest bytes/SHA-256/file-set SHA-256；
- workflow file blob OID；
- GitHub run ID、attempt、workflow ID 和两个 job ID；
- 每个 job 的 status/conclusion/started/completed/runner image/Python 身份；
- GitHub API 返回的 job/step 结构 canonical bytes 及 hash；
- 下载日志的 exact bytes/SHA-256（日志可过期，因此必须在发布前封存）；
- `LINUX_PYTHON_3_9_VERIFIED` 和 `LINUX_PYTHON_3_12_VERIFIED` 只能由结构/日志重放派生。

它必须作为 v0.64 新的 pre-artifact gate，但不进入 v2 plan 或 supersession record 的反向 hash，
避免循环。最终 v0.64 build manifest、ADR 和 status 绑定该 witness file SHA-256。

私有 spec/plan 必须将旧句子“Draft-PR Linux Python 3.9/3.12 CI”显式修正为：

> 私有 Draft PR 是代码审查与发布对象；公开镜像是与该候选逐字节绑定的独立 Linux
> portability witness。两者不是同一 PR check，不得用一方结果声称另一方已运行。

这是显式治理更正，不是静默绕过失败 check。旧 run `31436609135` 及 billing 阻塞注释必须
保留在 PR #32 或其取代 PR 中。

## 9. 公开仓库生命周期和治理

- 创建公开仓库、首次 push、workflow 运行是不可逆的外部动作，必须在实施完成、本地审查
  通过后，向用户展示 exact repository name、file set、bundle hash 和 public commit 候选，再取得一次
  针对性批准；
- 仓库永久保留且默认 archive，不用它继续开发通用交易引擎；
- 首次有效 run 后创建 annotated tag，tag message 记录 private source commit、manifest hash 和 run ID；
- public commit 的 author email 使用账号的 GitHub noreply 地址，不公开本机邮箱；
- 不接受外部 PR；`SECURITY.md` 只提供 GitHub private vulnerability reporting，不公开个人邮箱；
- 不在本设计中授予开源许可。`NOTICE.md` 说明代码仅为公开检查/重放，版权保留；
  如果未来要采用 MIT/Apache/LGPL 等许可，必须作为单独用户决策；
- 公开后如发现凭据或超白名单文件，立即停止 v0.64，撤销凭据、保全 incident evidence；
  删库/再私有不得被表述为已收回公开数据。

## 10. TDD、审查与失败关闭

实施必须遵守：

1. 先给 private exporter/verifier、public-only test、manifest loader 和 witness loader 写精确 RED；
2. 最小 GREEN，不引入通用发布平台、同步 daemon、通用 UI 或第三方 runtime 依赖；
3. 对精确最终代码状态运行受影响专项、相邻测试、compileall、diff-check 和一次全量本地 suite；
4. 独立完整审查一次，Critical/Important 归零；修复后只定向复审；
5. 在真实公开前用一个本地 owner-only 裸仓库/临时 worktree 演练精确 root commit、manifest 重放和
   workflow 静态合同；
6. 任一敏感信息扫描命中、文件超白名单、hash/blob/tree 不等、Linux job 未实际执行、
   workflow 权限扩大或 GitHub API/log 无法封存时，立即失败关闭；
7. 失败时不返回 PASS、不生成 Task 5 plan artifact、不请求 owner attestation、不 merge/tag v0.64。

## 11. 对现有 v0.64 的影响

- PR #32 及 `1809bd5...` 保留为 billing-blocked 证据，不改写；
- 本 spec 及后续 exporter/test/witness 将产生一个新的 pre-artifact 私有候选 commit，因此新的公开
  bundle、Task 5 plan、machine evidence、owner attestation 和 record 必须全部绑定新 commit；
- 任何旧 Task 5/Task 6 文件或旧 owner approval 不得复用；
- v0.62 plan/tag/bytes 不修改，v0.64 仍只是 plan-only storage supersession；
- 本更正不改 scope、decision policy、cohort policy、evidence policy、predecessor failure、service identity、
  runtime root、无启动状态或交易权限；
- v0.65 Nautilus bounded Spike 的范围和排期不变，但只能在 v0.64 发布闭环后继续。

## 12. 可证伪验收标准

只有同时满足以下条件，才能用公开镜像替代“私有 PR 中实际 Linux CI”这一不再可用
的传输路径：

1. 私有仓库仍为 private，且历史、artifacts 和不在白名单的代码从未推送到公开镜像；
2. 公开仓库 exact tracked file set 等于第 5 节最终白名单；
3. 原样源文件与精确 private commit Git blob byte-for-byte 相等；
4. public-only test 在同一 private commit 中先经 TDD、本地验证和独立审查；
5. manifest exact set/hash/blob/tree/source-commit 重放通过；
6. workflow 只有 owner push/dispatch，permissions exact `contents: read`，无 secrets/网络业务请求/发布权限；
7. Ubuntu Python 3.9/3.12 都实际执行 Linux `renameat2` 测试且 success，无 skip/mock/continue-on-error；
8. run/job/step API bytes 和 logs exact bytes 在过期前封存，私有 witness loader 重放完整；
9. 公开 repository/commit/tree/workflow/run/jobs 与私有 witness 绑定完全一致；
10. 私有 spec/plan 显式记录 transport 更正，保留旧 billing-blocked run，不伪称 PR #32 CI 已通过；
11. Task 5 前的全部原有 Mac/Schema/design 门在新 private commit 上继续通过；
12. 公开动作的 exact repository name、file set、bundle hash 和候选 commit 已展示给用户并获得针对性批准。

若任一条不成立，v0.64 保持 pre-artifact blocked，不用“本地测试够了”、“公开了应该免费”
或“代码没改”替代真实证据。
