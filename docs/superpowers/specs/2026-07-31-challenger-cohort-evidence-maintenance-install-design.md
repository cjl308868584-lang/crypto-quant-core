# v0.51 Challenger Cohort 证据维护私有快照与受限安装设计

日期：2026-07-31

状态：冻结

冻结基线：`v0.50.0` / `4526bb730dc34fcfc7d2ab72835486e1a692176c`

## 1. 目标

v0.50 已生成每天北京时间 08:10 运行一次 v0.49 固定维护入口的独立
LaunchAgent 合同，但合同仍指向开发工作树且明确未安装。v0.51 将：

1. 从 loader 验证通过的 v0.50 合同所绑定的源仓库生成 owner-only 私有执行快照；
2. 使用私有快照重新渲染安装候选合同与 plist；
3. 由独立、固定目标的 restricted installer 安装并加载维护 LaunchAgent；
4. 生成可重放验证的 deployment manifest 与 install receipt。

本版本不手工运行维护 CLI，不使用 `kickstart`，不触发策略 Runner，不访问市场，
不写策略 state，不调用 Broker 或订单。由于合同固定 `RunAtLoad=false`，真实
`bootstrap` 只能加载调度，首次执行必须等下一个自然 08:10 槽并在后续版本取证。

## 2. 独立组件和权限边界

不得修改或复用硬编码
`local.crypto-quant.challenger-forward` 的 v0.33 installer。新增：

- deployment core/CLI：只创建私有快照、manifest 和安装候选，不调用 launchctl；
- install core/CLI：只接受 deployment manifest、候选合同/plist、外部 trust hash
  和 receipt output root；
- 两个严格 Draft 2020-12 Schema；
- production loaders。

固定维护标签：

```text
local.crypto-quant.challenger-cohort-evidence-maintenance
```

固定用户域目标：

```text
$HOME/Library/LaunchAgents/
local.crypto-quant.challenger-cohort-evidence-maintenance.plist
```

CLI 不允许 target、uid、domain、label、module、schedule、command、URL、credential、
Broker、order、strategy state、Runner、kickstart、bootout 或 maintenance-now
参数。

## 3. 源合同与外部信任

deployment CLI 只接受：

- v0.50 source contract；
- v0.50 source plist；
- 调用方提供的 source contract trusted attestation hash；
- owner-only deployment output root。

必须使用 v0.50 production loader 验证 source contract、plist、外部 trust、
strategy install receipt/contract/plist、计划、Python、runtime 和系统时区。source
contract 必须为 `NOT_INSTALLED_NO_EXTERNAL_RECEIPT` 且 `RunAtLoad=false`。

candidate contract 重新渲染后产生新的 external attestation hash。该 hash 必须先
作为独立 release candidate evidence 提交冻结，再由 installer 显式输入。installer
不得从 candidate contract 自行计算 trust 后把它当作外部信任。

## 4. 私有执行快照

源文件集合固定为：

- `pyproject.toml`；
- `src/crypto_quant/` 下全部普通文件，排除 `__pycache__`、`.pyc` 和隐藏文件；
- v0.43 cohort plan exact bytes；
- v0.37 economic plan exact bytes。

源根、目录和文件必须：

- 为当前 uid 所有；
- 不含 symlink、非普通文件或 hardlink；
- 单文件不超过 4 MiB；
- 总大小不超过 32 MiB；
- 文件数不超过 1000；
- 读取前后 stat 一致。

按相对路径、大小、SHA-256 构造有序 file manifest，并计算 content tree hash。
快照固定发布到：

```text
<runtime>/deployment/
challenger-cohort-evidence-maintenance/<tree-hash-prefix>
```

父目录和所有子目录为 0700，文件为 0600。使用同一父目录内临时目录、逐文件
fsync、目录 fsync 和无覆盖原子 rename。已存在的同 hash 快照必须逐文件 exact
验证后幂等复用；任何额外、缺失或不同文件失败关闭。

私有快照不复制 `.git`、tests、docs、开发 artifact、凭据、日志、state 或现有
cohort evidence。

## 5. Deployment manifest 与候选合同

部署 manifest 至少绑定：

- source contract id/hash/trust/plist hash；
- source repository/runtime/Python；
- 全部快照相对文件、大小、SHA-256；
- snapshot root、file count、total bytes、tree hash；
- candidate contract id/hash/trust/plist hash 和 exact 路径；
- strategy trust 与 v0.43/v0.37 plan SHA；
- snapshot/candidate publish counts；
- network/launchctl/Broker/order/state-write/Runner/maintenance invocation
  全部为 0；
- “尚未安装、未运行、无盈利证明”的 warnings。

candidate 固定发布到 deployment output root 的
`challenger-cohort-evidence-maintenance-install-candidate` 子目录，目录 0700，
contract/plist/manifest 均 0600、单 hardlink、exact/idempotent。

production loader 必须重新验证 source contract、snapshot inventory/tree、
candidate contract semantic replay 和 manifest 自哈希。

## 6. 安装事务

installer 前置条件：

- 当前 uid 为普通用户；
- deployment manifest production loader 通过；
- candidate contract production loader 使用调用方提供的 candidate trust hash
  通过；
- candidate repository 必须等于 manifest snapshot root；
- candidate `RunAtLoad=false`、每天 08:10、无凭据；
- Python 在最小环境中从 snapshot `PYTHONPATH` 可导入
  `jsonschema`、`crypto_quant` 和 maintenance CLI；
- target 不存在或 bytes 完全相同。

固定命令顺序：

```text
/bin/launchctl print gui/<uid>/<label>
/bin/launchctl bootstrap gui/<uid> <target>   # 仅未加载时
/bin/launchctl print gui/<uid>/<label>
```

禁止 `kickstart`、`start`、`submit`、`bootout` 和任意 shell。target 使用 mode
0600 临时文件、fsync、无覆盖 hardlink 和父目录 fsync。新 target 的 bootstrap
失败时只回滚本次 target；bootstrap 成功后的 print 失败保留现场，不误删已加载
配置。已加载且 exact 的服务只执行两次 print，禁止重复 bootstrap。

print 必须绑定 service、target、Python、WorkingDirectory、maintenance module、
两个计划和三个 output root。安装前后策略 state/stdout/stderr exact hash 必须
由发布验收独立确认不变。

## 7. Install receipt

receipt 至少绑定：

- deployment manifest id/hash/file SHA；
- candidate contract id/hash/trust 和 plist SHA；
- execution snapshot root/tree hash/count/bytes；
- domain/service/target 及 target inode/device/uid/mode/link/hash；
- preflight print、bootstrap-or-null、verified print 的 exact argv、return code、
  stdout/stderr bytes hash和 evidence hash；
- installed_at、verified_at、install action；
- `INSTALLED_AND_LOADED_WAITING_FOR_NATURAL_SCHEDULE`；
- `run_at_load=false`、maintenance invocation count 0；
- launchctl command count 2 或 3；
- credential/network/Broker/order/state-write/Runner 全部为 0；
- “安装不证明首次自然运行、cohort 完整、盈利、Paper 或 AI 优势”的 warnings。

receipt owner-only exact 发布。loader 必须重做 manifest、contract、snapshot、
target stat/hash、命令 evidence 和语义绑定验证。

## 8. 失败与幂等

- target 不同：失败且不覆盖；
- 已加载服务绑定不同：失败且不修改；
- snapshot/candidate/manifest/receipt 相同 bytes：幂等；
- 同路径不同 bytes 或额外 inventory：失败；
- bootstrap 失败：仅新建 target 可回滚；
- post-bootstrap print 失败：保留现场，转失败取证；
- 当前时间已过 08:10 不授权补跑；不得 kickstart 或手工调用维护入口。

## 9. 验收

- 两个 Schema config/package mirror 逐字节一致并通过 Draft 2020-12；
- snapshot 100 次 manifest/tree 确定性一致；
- symlink、hardlink、TOCTOU、权限、大小、数量和额外 inventory 失败关闭；
- source 与 candidate 都要求调用方提供 external trust hash；
- candidate plist 与 private snapshot 路径完全绑定；
- installer fake launchctl 覆盖新装、已加载幂等、冲突、bootstrap 回滚、
  post-print 保留现场和 print 缺绑定；
- coordinated manifest/contract/plist/receipt rehash tamper 均被 production
  loaders 拒绝；
- CLI authority 搜索证明无任意目标/命令/运行触发选项；
- focused、adjacent、全量测试、compileall、evaluator build 全部通过；
- 真实部署和安装前后策略 state/stdout/stderr hash 不变；
- 真实安装只出现固定 print/bootstrap/print，维护日志、cohort receipt/archive/
  result roots不因安装产生，maintenance invocation count=0；
- commit、PR、main CI 与 annotated `v0.51.0` tag exact 对齐。

## 10. 对赚钱目标的意义

本版本仍不增加或证明收益。它把人工维护证据链变成系统级、固定时点、漏跑可观察的
调度，降低只处理有利 Episode、遗漏负样本和人工挑选时间造成的偏差。首次自然运行
receipt、完整 cohort 和 v0.48 固定 tail 累计门仍是后续必要条件；这些条件通过前，
系统不得声称策略赚钱、AI 优于基线或具备实盘资格。
