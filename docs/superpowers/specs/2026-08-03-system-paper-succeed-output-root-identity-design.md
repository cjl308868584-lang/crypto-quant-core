# System Paper `succeed` 输出根身份封闭设计

日期：2026-08-03

状态：冻结

目标版本：`v0.57.0`

适用分支：`codex/v0.57-system-paper-scheduler`

上位设计：`docs/superpowers/specs/2026-08-02-system-paper-wal-scheduler-design.md`

## 1. 背景与目标

v0.57 runner 在入口保留了 output root 的目录描述符，并在 provider、runtime、发布前后
验证当前路径仍指向预检时的 `(st_dev, st_ino)`。但是 runner 调用
`SystemPaperScheduleState.succeed()` 时只传入 artifact 路径；状态层随后按路径重新打开
output root，因而丢失了预检身份。

攻击或故障可以发生在 runner 最后一次 `root_handle.validate()` 之后、`succeed()` 重新打开
路径之前：原 output root 被移走，原路径上创建 owner-only 替代目录，并放入完全相同的
artifact bytes。当前实现会接受替代目录并提交 `SUCCEEDED`。字节相同不能证明目录仍是本次
invocation 预检和发布所绑定的目录，因此这是发布阻断缺陷。

本修复仅关闭这个组件边界。它不改变 slot、市场输入、runtime、经济结果、调度窗口、故障
矩阵或 v0.57 的外部功能范围，也不安装或启动 System Paper。

## 2. 方案裁决

采用“显式可信身份 + 状态层事务内复核”：

- `_ValidatedRunnerOutputRoot.identity` 仍是本次 invocation 唯一可信根身份；
- `SystemPaperScheduleState.succeed()` 新增必填 keyword-only 参数
  `expected_output_root_identity: Tuple[int, int]`；
- runner 必须把保留句柄的 exact identity 传入状态层；
- `_artifact_body()` 接受同一 expected identity，并在读取前验证按路径打开的 root 描述符；
- `succeed()` 在 artifact 验证之后、提交 `SUCCEEDED` 前再次验证当前路径仍指向同一身份；
- 身份缺失、格式非法或不匹配均失败关闭并回滚。

不采用仅在 runner 增加一次外部检查，因为检查与 `succeed()` 重开之间仍有竞争窗口。不采用
把目录描述符的所有权交给状态层，因为这会把文件描述符生命周期耦合进 SQLite 状态对象，
扩大 v0.57 的改动面；本次不需要该复杂度即可证明 pathname reopen 绑定到冻结身份。

## 3. 接口与验证顺序

`succeed()` 的接口固定为：

```python
def succeed(
    self,
    claim: SystemPaperClaim,
    *,
    artifact_path: Path,
    expected_output_root_identity: Tuple[int, int],
    completed_at: object,
    before_commit: Optional[Callable[[], None]] = None,
) -> None:
```

身份必须是长度为 2 的整数 tuple，两个值均为正数；布尔值不视为整数。非法输入返回固定
`SYSTEM_PAPER_SCHEDULE_OUTPUT_ROOT_IDENTITY_INVALID`，不开始事务。

事务内顺序固定为：

1. 重放并验证事件链、claim 与 prepared result；
2. 验证 prepared `output_root_hash` 与 artifact path 派生路径一致；
3. `_artifact_body()` 使用 no-follow、owner-only 目录句柄打开 root，要求其
   `(st_dev, st_ino)` 等于 expected identity；
4. 读取并验证 exact artifact bytes、SHA-256、单链接、owner、模式、大小和当前文件身份；
5. 再按路径 no-follow 打开 root，验证 owner/mode/identity，证明 pathname 仍附着于冻结目录；
6. 追加 `SUCCEEDED` 并重放完整事件链；
7. 执行现有 `before_commit` 故障注入；
8. 最后一次按路径验证 root identity，然后提交事务。

步骤 3、5 或 8 的 identity 不匹配或路径消失统一返回
`SYSTEM_PAPER_SCHEDULE_OUTPUT_ROOT_RACE`；事务回滚，不存在 `SUCCEEDED` 事件。artifact
本身的安全、缺失、竞态与字节不匹配继续使用现有固定 reason code。

步骤 8 只保护成功提交所依据的 pathname 绑定；提交完成后外部目录被管理员移动不会改写
已经提交的历史事件，也不属于本次 invocation 的可原子控制范围。

## 4. 测试合约

必须先增加失败测试，再实现生产修复：

1. 在 runner 最后一次外部 `root_handle.validate()` 后、状态层身份验证期间，将原 root 重命名
   为 backup，并在原路径创建 `0700` 替代 root、`0700` slots 和含 exact bytes 的 `0600`
   artifact；必须抛出 `SYSTEM_PAPER_SCHEDULE_OUTPUT_ROOT_RACE`。
2. 直接调用 `succeed()` 时传入另一目录的身份，必须回滚且不写 `SUCCEEDED`。
3. 在 artifact 验证后、commit 前替换 root，必须由最终身份检查拒绝。
4. 正常执行、发布后恢复和已成功 replay 的 inode/bytes 行为保持不变。
5. 所有失败用例必须同时断言 prepared input/result 与原 artifact 保持不可变，provider、runtime、
   Broker、order 和 credential 安全计数不增加。

## 5. 发布门

本设计只解除 I3 对 v0.57 的阻断。代码必须通过聚焦、相邻、全量、`compileall`、构建清单和
`make validate`，并获得独立审查确认没有 Critical/Important 遗留，才允许推送和创建 Draft
PR。GitHub 写入前仍须核验目标私有仓库、`origin/main` 与 ADMIN 权限。合并、main CI 与
annotated `v0.57.0` 标签流程不变；不得安装、启动、触发 Runner 或开始 90 天计时。
