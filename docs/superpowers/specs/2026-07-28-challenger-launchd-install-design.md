# v0.33 Challenger LaunchAgent 安装与 Receipt 设计

日期：2026-07-28

状态：冻结；真实 RunAtLoad 后增加部署快照修订

## 1. 目标

只接受 v0.32 已通过语义重放的合同与 plist，将完全相同的 bytes 安装到当前
macOS 用户 LaunchAgents 域，执行固定 `launchctl bootstrap` 与 `print`，并
生成不可变安装 receipt。

安装对象仍是无凭据、公共只读、无 Broker/Order 权限的 v0.31 Runner。

## 2. 固定目标

- 当前 uid 必须为普通用户；
- launchctl 必须固定为 `/bin/launchctl`；
- domain 必须为 `gui/<current_uid>`；
- service 必须为 `local.crypto-quant.challenger-forward`；
- target 必须为
  `$HOME/Library/LaunchAgents/local.crypto-quant.challenger-forward.plist`；
- target parent 必须是当前用户拥有的真实目录；
- CLI 不允许 target/domain/uid/label/command 覆盖。

## 3. 前置验证

- source contract/plist 通过 Schema、自哈希、plist hash 和 semantic replay；
- contract 状态必须是 `NOT_INSTALLED_NO_EXTERNAL_RECEIPT`；
- source plist mode 0600；
- repository/runtime/python 路径仍存在；
- repository 必须是 runtime 下 `deployment/<revision>` 的 owner-only 私有
  执行快照，禁止直接从 `~/Documents` 开发目录运行；
- receipt 必须绑定执行快照的逐文件相对路径、大小、SHA-256 汇总树哈希；
- Python 在最小 HOME/PYTHONPATH 环境可导入 `jsonschema` 与 `crypto_quant`；
- target 不存在，或存在完全相同 bytes；
- target 若不同，失败且不覆盖。

## 4. 安装事务

1. 在 LaunchAgents 内创建 mode 0600 临时文件，写入、fsync；
2. 原子 link/rename 成 target，不覆盖不同文件；
3. fsync LaunchAgents 目录；
4. 执行固定：

```text
/bin/launchctl bootstrap gui/<uid> <target>
/bin/launchctl print gui/<uid>/local.crypto-quant.challenger-forward
```

5. bootstrap/print 必须 return code 0；
6. print 输出必须包含 service label、program、state/output 路径；
7. 若本次新建 target 后 bootstrap 失败，删除本次 target 并 fsync；
8. 不自动运行 bootout，不替换已加载的不同服务。

## 5. Receipt

Receipt 绑定：

- source contract id/hash/trust hash 和 source plist hash；
- domain/service/target；
- target inode/device/uid/mode/link-count/size/hash；
- bootstrap 与 print 的固定 argv、return code、stdout/stderr hash；
- installed_at、verified_at；
- `INSTALLED_AND_LOADED`；
- RunAtLoad 结果只作独立字段，未观察时不得伪造成功；
- Broker/order count 固定 0。

Receipt 自哈希、严格 Schema、semantic replay 后发布为 owner-only 文件。

## 6. 幂等

- 相同 target 且 service 已加载：不再 bootstrap，只 print，receipt 标记
  `ALREADY_INSTALLED_AND_LOADED`；
- target 相同但 service 未加载：允许 bootstrap；
- target 不同或 service 指向不同 program：失败关闭；
- 同一 receipt bytes 幂等，不同 bytes 冲突。

## 7. 验收

- 命令 runner 只接受两个固定 launchctl argv；
- target 冲突不覆盖；
- bootstrap 失败回滚本次文件；
- 已加载相同服务幂等；
- print 缺失任何固定绑定失败；
- receipt Schema/self-hash/target stat/hash/semantic replay 通过；
- 修改执行快照任一文件后 receipt 复核失败；
- 开发目录合同必须在调用 launchctl 前失败关闭；
- CLI 无任意命令、target、domain、credential、URL、order 参数；
- 全量验证后执行真实安装，保存 receipt；
- 提交、合并并标记 `v0.33.0`。

## 8. 真实运行修订

首次真实安装证明 macOS LaunchAgent 虽能显示开发目录 `PYTHONPATH`，后台进程
仍无法从 `~/Documents` 导入项目模块，RunAtLoad 退出码为 1。该失败配置、日志
与 receipt 均被移动到 owner-only 归档，未删除。

修订后的合同改用 Application Support 内由已提交 `b96955a` 生成的私有执行
快照。重装后的 RunAtLoad 退出码为 0，返回 `NOT_DUE`。因此“终端最小环境可
导入”不再被视为充分条件；部署位置与逐文件树哈希成为安装 receipt 的强制绑定。
