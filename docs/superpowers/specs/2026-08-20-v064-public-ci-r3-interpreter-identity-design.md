# v0.64 公开 Linux CI R3 解释器身份纠错设计

**状态：** 已获用户批准，仅限本地设计、实现、测试、审查与候选构建
**设计日期：** 2026-08-20
**私有候选基线 `F2`：** `5bc01c9b9b9d9a21846dd8c6ba1d81b0183dd219`
**基线 tree：** `53d3baf7d7c84e5bc8fcafa2561bbb959477ac4d`
**失败 R2 公开仓库：** `cjl308868584-lang/crypto-quant-v064-public-ci-r2`
**R3 公开仓库候选名：** `cjl308868584-lang/crypto-quant-v064-public-ci-r3`

## 0. 决策摘要

R2 必须永久保留为语义失败。GitHub 将 Run `32328770160` 标记为 `success`，但
`portability (3.9)` 的固定 owner 测试实际输出 `Python 3.12.3`；它没有形成真实的
Python 3.9/3.12 双版本 Linux portability witness。不得 rerun、删除、强推、改写、归档、
追加 branch/commit/tag/release，亦不得发布 R2 成功 witness 或 `G2`。

R3 是新的、显式 superseding 工程纠错候选。它使用新的私有 `F3`、新的公开仓库、新的无父
根提交和未来一次新的 owner-push 运行。R3 只修复固定 owner 边界的 Python 解释器身份传递，
同时把 R1 与 R2 两项失败作为不可变前置证据。它不改变 Linux publisher、Linux 测试语义、
阈值、UID 501、v0.62 plan、研究假设、资金权限或后续 v0.65/v0.66 路线。

当前授权只覆盖本地 spec、plan、代码、测试、审查和候选构建。创建 R3 公开仓库、推送、运行
Actions 和读取结果必须等八文件及 root commit/tree 确定后，再以一次 exact approval package
单独授权。

## 1. 不可变失败前置证据

### 1.1 R1 失败

R1 的全部身份继续逐字节沿用 R2 已冻结的
`predecessor_failed_public_witness` 对象，包括公开仓库
`cjl308868584-lang/crypto-quant-v064-public-ci`、commit
`0429837e5de8052e9e8216ed08ba9c7aa9c905b3`、Run `31850146784`、Jobs
`94924270273`/`94924270340` 和 reason `PUBLIC_SENSITIVE_BYTES_INVALID`。R3 不修改、
重排或弱化该对象的任何字段。

### 1.2 R2 失败

R3 必须精确绑定下列事实：

| 字段 | 精确值 |
|---|---|
| 私有 source candidate `F2` | `5bc01c9b9b9d9a21846dd8c6ba1d81b0183dd219` |
| 私有 `F2` tree | `53d3baf7d7c84e5bc8fcafa2561bbb959477ac4d` |
| R2 公开 repository | `cjl308868584-lang/crypto-quant-v064-public-ci-r2` |
| R2 root commit | `5541aba00e4e93e6389c2c61a81e69c2dd228947` |
| R2 root tree | `3d732e8e1fbb9cf94541f6e26e778d5eb21ca8f3` |
| R2 workflow blob | `ba5b6851ed53ad79100409b92c78c09c07608ed2` |
| R2 manifest SHA-256 | `b2017d2e4099ee64d0cbbcbd35f38b1833fbe351d2696f70248ad60056b20ae2` |
| R2 file-set SHA-256 | `6c6d5bde35d1f5f4e484f5874b47fad3d0f575eef4eeb8e4deb9de659be4eb69` |
| Run ID / attempt | `32328770160` / `1` |
| Run event / branch | `push` / `main` |
| GitHub status / conclusion | `completed` / `success` |
| Python 3.12 Job | `96305223215`, fixed-owner output `Python 3.12.3` |
| Python 3.9 Job | `96305223463`, setup-python `3.9.25`, fixed-owner output `Python 3.12.3` |
| 语义结果 | `PUBLIC_LINUX_PORTABILITY_WITNESS_DID_NOT_PASS` |
| 固定 reason | `PUBLIC_MATRIX_INTERPRETER_IDENTITY_MISMATCH` |
| Run JSON bytes / SHA-256 | `363` / `310d2cad6840dc80d4cbcd6cc229d32704fd3c8854b44b6bbd893b708d4f9986` |
| Jobs JSON bytes / SHA-256 | `2312` / `3078337f2f8e5aa9add1b099391e19125d5dcdeaef803e1f50d9666716ad773c` |
| Log bytes / SHA-256 | `105558` / `e6ee2bcf599cff56b0bcda8292bdb7a85e5ef186973f4fe3a14c67f97a0bbf47` |
| acquisition stderr bytes / SHA-256 | `0` / `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

R2 的 GitHub `success` 只是 workflow process exit 状态，不能覆盖解释器身份不匹配。冻结 R2
loader 返回 `V064_PUBLIC_CI_LOG_INVALID` 且正式 root `artifacts/v064-public-ci-r2` 未创建，
这是失败关闭的正确行为。

## 2. 根因

R2 在 `actions/setup-python` 后调用：

```text
sudo -u '#501' env HOME=... TMPDIR=... V064_PUBLIC_LINUX_REQUIRED=1 PYTHONPATH=... /bin/bash -c '... python ...'
```

setup-python 通过 runner 环境的 `PATH` 暴露所选解释器。R2 的 `sudo -u ... env` 没有传递该
PATH；子 shell 因而解析到系统 `python`，当时为 Python 3.12.3。两个 matrix job 都执行了
16 项测试，所以该事实不属于“测试前基础设施失败”，不得 rerun R2。

## 3. 方案比较与选择

### 3.1 绝对解释器路径作为固定位置参数：采用

setup-python 后在未降权 runner shell 中执行 `python_bin="$(command -v python)"`，要求它为绝对、
可执行路径，并用该 binary 报告的 `major.minor` 精确匹配 matrix value。随后将 `python_bin` 作为
`/bin/bash -c` 的固定 `$1` 传入 UID 501 进程。UID 501 只通过 `"$1" --version` 和
`exec "$1" -m unittest ...` 使用该解释器。`uname`、`ldd`、`head` 使用绝对系统路径。

这条路径不向 sudo 传递 runner PATH，也不在降权后搜索 `python`。

### 3.2 向 sudo 传递完整 PATH：拒绝

`env PATH="$PATH"` 改动较小，但证据仍依赖路径搜索、顺序和 runner PATH 内容。它不能像绝对
binary 身份那样直接证明两个 job 使用不同解释器。

### 3.3 复制解释器或创建 UID 501 venv：拒绝

这会新增复制、动态库、权限、安装和恢复语义；R3 只需把 setup-python 已安装的解释器安全地
交给固定 owner 边界，额外运行时不符合 YAGNI。

## 4. R3 workflow 协议

固定 owner step 必须遵守以下顺序：

1. 创建 UID/GID 501 和 owner-only HOME/workspace，复制 exact checkout 并固定权限；
2. `python_bin="$(command -v python)"`，要求非空、绝对且 `test -x`；
3. 使用 `"$python_bin" -c` 输出纯 `major.minor`，要求精确等于
   `${{ matrix.python-version }}`；
4. 不向 sudo 传递 PATH；将 `python_bin` 作为 bash 的固定 `$1`；
5. 降权 shell 内只允许 `"$1" --version` 和 `exec "$1" -m unittest -v
   tests/test_v064_linux_supersession_publish.py` 使用 Python；
6. 诊断命令固定为 `/usr/bin/uname -sr`、`/usr/bin/ldd --version | /usr/bin/head -1`；
7. 任一 identity、permission、copy 或 test 检查失败即非零，不产生 portability witness。

Workflow 继续只允许 `push: main` 与 `workflow_dispatch` 语法，但未来批准只执行一次 owner-push，
不手工 dispatch。`permissions: contents: read`、`persist-credentials: false`、Python matrix
`["3.9", "3.12"]` 和两个 action 的精确 SHA 保持不变。

## 5. R2 失败证据包

本地 `F3` 必须创建：

```text
artifacts/v064-public-ci-r2-failure/
  v064-public-ci-r2-run-api-v1.json
  v064-public-ci-r2-jobs-api-v1.json
  v064-public-ci-r2-run-log-v1.txt
  v064-public-ci-r2-failure-record-v1.json
```

前三个文件是已捕获 exact bytes。failure record 使用唯一、版本化、确定性 canonical JSON + LF，
绑定第 1.2 节全部身份、raw hashes、两个 observed interpreter、reason 和 false safety flags。
record 明确标记这些 raw bytes 是 Run 完成后的只读 readback，不冒充首次失败 CLI 已发布的
transcript。Loader 重新计算所有 raw SHA、解析 Run/Jobs/log，并独立推导 interpreter mismatch；
不能接受人工传入 DID_NOT_PASS、expected/observed version 或 reason。

正式 R2 success root 继续必须不存在。失败包不改变 R2 public repository，也不把 R2 宣称为
GitHub infrastructure failure。

## 6. R3 manifest、witness 与 ancestry

R3 bundle manifest 和 witness 的 `schema_version` 升级为 `1.2.0`。单个
`predecessor_failed_public_witness` 替换为 exact ordered
`predecessor_failed_public_witnesses=[R1, R2]`；两个 closed object 的字段、顺序、hash 和语义
均由 Schema 与 loader 固定。任何删除、重排、改写或重新封装后 hash 不一致都失败关闭。

R3 使用：

- repository `cjl308868584-lang/crypto-quant-v064-public-ci-r3`；
- candidate root `/private/tmp/crypto-quant-v064-public-ci-r3-candidate`；
- private ancestry `F -> F2 -> F3 -> G3`；
- private evidence root `artifacts/v064-public-ci-r3`；
- 全新 parentless public root commit；
- 精确八文件，除 manifest 外仍为 workflow、gitignore、NOTICE、README、SECURITY、publisher、
  Linux test。

R3 成功 witness 必须同时绑定 R1 failure、R2 semantic failure 和第一 eligible R3 success。
生产 loader 从 exact raw API/log bytes 自动推导结果；不得接受人工 status、PASS、Python version、
timestamp、repository、filename 或 output root。

## 7. 允许变化与禁止变化

`F3` 只允许：

- 本 design、implementation plan、R2 failure evidence/schema/loader/tests；
- R3 repository/candidate/evidence constants；
- bundle/witness Schema、builder、loader、fixed acquisition CLI；
- workflow 的解释器身份交接与 R3 repository identity；
- README/NOTICE 的 R3 与两项 predecessor failure 说明；
- private-only regression tests 和机械 build manifest 更新。

下列 public blobs 必须从 `F`、`F2` 到 `F3/G3` 完全相等：

- `src/crypto_quant/challenger_replacement_supersession_publish.py`；
- `tests/test_v064_linux_supersession_publish.py`。

R3 不得新增或执行 scheduler、deployment、Runner、Broker、订单、凭据、行情请求、production
root、策略 state、owner attestation、真实 plan artifact、私有 merge/tag 或资金操作。所有 safety
flags 保持 false。只读 Web/UI 与当前 R3 无关。

## 8. TDD 与验证

实现顺序：

1. RED：exact R2 raw evidence 能通过结构读取，但 3.9 job 的 observed interpreter 与 expected
   matrix version 不匹配；旧 loader 不能形成正式 failure record；
2. GREEN：最小 R2 failure schema/builder/loader，结果只能从 raw bytes 自动推导；
3. RED：提取的 R2 fixed-owner shell 在受控 fixture 中解析到系统 Python 3.12；
4. GREEN：R3 shell 使用固定绝对 `$1`，在 PATH 缺失/污染时仍调用指定解释器，并拒绝 version
   mismatch、相对/不可执行路径；
5. RED/GREEN：R3 manifest/witness 的双 predecessor、repository、version、root 与 ancestry；
6. RED/GREEN：R3 acquisition/publisher 的固定三命令、固定五文件、no-overwrite 和失败关闭；
7. 构建并重放本地 R3 八文件 parentless candidate，执行 exact embedded preflight 和敏感 payload
   negatives；
8. focused/adjacent、compileall、diff-check、build replay；最终代码状态本地 full suite 一次；
9. 独立完整审查一次，Critical/Important 为零；修复后只做针对性复审。

本地测试不得 mock Git object identity 来伪造 root commit；不得用 skip 代替 required contract。
Linux-only真实 UID/primitive 检查继续由公开八文件中的现有测试承担，其 blob 不得修改。

## 9. 当前阶段终点

当前阶段完成条件仅为：

- R3 spec/plan/实现/测试/审查在私有隔离 branch 完成；
- R2 失败证据可离线重放；
- R3 candidate 可确定性构建/重放，八文件 exact package 已知；
- 没有任何新的 GitHub repository、push、Actions Run 或 success witness。

达到该终点后，只向用户提交一次包含 exact private commit/tree、八文件 SHA/blob、R3 public
root commit/tree、测试/审查证据和不可逆风险的审批包。一般授权不替代该 exact 外部写入门。

## 10. 可证伪验收标准

R3 本地候选只有在以下事实全部成立时才可进入外部审批：

- R1、R2 仓库与失败身份保持可读取且不可变；
- R2 exact raw bytes 由 production loader 自动推导
  `PUBLIC_MATRIX_INTERPRETER_IDENTITY_MISMATCH`；
- R2 success evidence root 不存在，R2 Run 未 rerun；
- R3 workflow 不依赖降权后的 PATH，并把绝对解释器作为固定 `$1`；
- 私有测试证明 PATH 缺失/污染不能改变被调用解释器，version mismatch 必须失败；
- publisher/Linux-test blobs 与 `F`/`F2` exact 相等；
- R3 public tree 精确八文件、无额外 history/ref/tag/release；
- bundle/witness 双 failure ancestry、raw hashes、safety flags 和 no-PASS-input 合同闭合；
- focused、相邻、一次最终 full suite、build replay 与独立审查均通过；
- 没有创建或推送 R3 public repository，也没有真实交易或 production side effect。

任一条件缺失时保持 local candidate pending；不得宣称 R3、v0.64、Paper、Canary 或实盘通过。
