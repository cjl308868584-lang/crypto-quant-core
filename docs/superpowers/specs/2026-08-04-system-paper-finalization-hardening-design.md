# System Paper Finalization Hardening Design

日期：2026-08-04  
目标版本：`v0.59.0`  
基线：`c38c30a9408fc3dd3c4c453c37e980a14fe0a1b0`  
适用分支：`codex/v0.59-system-paper-evaluation`

## 1. 决策摘要

v0.59 最终审查证明正常完整路径之外仍存在六个终态信任缺口。本设计用一个
统一的 finalization authority 修复，不将它们分散为彼此无关的局部判断。

核心决定：

1. `output_root` 参数保留，但必须精确等于
   `contract.root_paths.artifacts/system-paper-evaluations`；
2. 同一 `(contract_hash, start_receipt_hash)` 只允许一个首次 final；
3. 从首次捕获到发布返回只使用同一组 retained descriptors/snapshots，禁止
   error catch 中二次取样；
4. 无法语义重放但字节稳定的 SQLite group 使用真实 raw-state binding 发布
   `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`；
5. loader 必须从声明的 owner-only output-root dirfd 相对打开 exact 文件，并在
   full replay 后重验 root/file attachment；
6. 冻结 cohort 的 verified count 只统计预注册 540 IDs；第 541 槽不得造成
   Schema hard error。

本版仍是 code-only research evaluator，不安装、不启动、不下单、不开始 90 天。

## 2. 专用 output root 与隔离

七路径 CLI 不变。evaluator 通过 strict contract loader 派生：

```text
expected_output_root = contract.root_paths.artifacts / "system-paper-evaluations"
```

传入的 `output_root` 必须与它词法路径、解析路径和预期 parent identity 一致。在任何
写入前，必须拒绝它与 plan/start/install/contract/plist/preflight/state/slot root 相等、
互为祖先/后代或 inode alias。唯一允许的关系是：evaluation root 与
`system-paper-slots` 是同一冻结 artifacts root 下的独立兄弟目录。

安全目录模式保持 `0700`，result 保持 `0600`。不对已存在的不安全路径执行
`chmod` 或覆盖。

## 3. Cohort 终态锁

定义稳定 series key：

```text
terminal_key = H(contract_hash, start_receipt_hash)
```

result ID 仍绑定 contract/start/state-binding/inventory 四项，但 result ID 不再承担“同 cohort
唯一终态”的责任。

专用 output root 内使用 owner-only、no-follow、single-link lock file 和 OS exclusive file lock
串行 finalization：

1. 获取 root lock；
2. 有界、strict 扫描现有 final JSON；
3. 若同 terminal key 已存在：只有 candidate exact bytes 一致时幂等返回；
4. 若同 terminal key 已存在但 event/inventory/status/bytes 不同：永久 conflict，零新文件；
5. 若不存在：使用 exact no-overwrite publisher 发布，发布前/callback/返回后均
   重验首次 authority snapshot；
6. 重扫 terminal series，确认恰好一个 final 后释放 lock。

崩溃产生的 invalid/partial final 必须使后续评估失败关闭，不得跳过它发布更好结果。

## 4. 单次证据捕获

post-tail 第一次 slot-root 扫描必须立即保留 directory FD 和完整 snapshot，无论结果是
PRESENT/EMPTY/UNSAFE/名称不匹配。

- exact 540：从这一 snapshot 打开和保留所有 artifact；
- missing/extra/unsafe：从同一 snapshot 派生 INCONCLUSIVE inventory；
- missing root：保留 parent dirfd 和 exact absence attachment；
- capture 后任何 name/stat/bytes/inode/mode 变化：`SOURCE_CHANGED`，零发布。

删除“第一次 exact scan 失败后关闭 FD，catch 内 fresh capture”路径。

## 5. State binding 与稳定损坏

在语义重放前，先保留 SQLite main/WAL/SHM group 并计算字节级 group hash。

结果 sources 改为明确的 union：

```text
state_binding_kind = EVENT_CHAIN_END | RAW_SQLITE_GROUP
state_binding_hash = <hash>
event_chain_end_hash_or_null = <hash | null>
raw_state_group_hash = <hash>
```

- replayable snapshot：`state_binding_kind=EVENT_CHAIN_END`，两个 event hash 字段一致；
- 捕获后稳定但无法重放：`RAW_SQLITE_GROUP`，event hash 为 null，发布
  `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`；
- 捕获后 raw bytes/path identity 变化：硬失败，不发布。

合法 INCONCLUSIVE reason 扩展为有界枚举，至少包含 state replay invalid 与 prepared/start
replay invalid。result identity 使用 `state_binding_hash`，因此不会伪造 event-chain end。

## 6. Loader root attachment

loader 必须：

1. strict parse artifact 前从 owner-`0700`、no-follow output-root dirfd 相对打开；
2. 要求 `evaluation_path == sources.output_root / (result_id + ".json")`；
3. 要求 sources.output_root 等于 strict contract 派生路径；
4. 在 full raw-input replay 前后重验 root identity、file attachment 和 exact bytes；
5. detached copy、symlink root、`0755` root、删除官方 root 后的副本全部拒绝；
6. loader 继续零发布、零目录创建。

## 7. 冻结窗口与第 541 槽

`verified_terminal_slot_count` 只计算从 start receipt 派生的 540 个预期 ID。窗口外的
event/projection/artifact 不得使计数超过 Schema 上限。

根据原冻结 exact-inventory 要求，第 541 槽或额外 artifact 仍导致
`INCONCLUSIVE_INSUFFICIENT_EVIDENCE`，但必须是可 Schema 验证、可发布、可 loader 重放的
终态，不得升级为 hard schema error。

## 8. Decimal 决定性加固

冻结 evaluator 完整 `decimal.Context`，至少固定 precision、rounding、Emin、Emax 与 traps，
不继承调用者全局 context。使用极端但合法的 Decimal 输入证明多个 ambient context 下
exact result bytes 一致。

## 9. Schema、测试与构建身份

双 Schema 增加 state binding union 与终态 reason，继续 byte-identical、
`additionalProperties=false`、禁止 float/NaN/Infinity。

必须先 RED 再 GREEN 覆盖：

- INCONCLUSIVE 后补齐同 cohort，零第二 result；
- concurrent finalization 只有一个 exact final；
- output-root 指向 start/contract/slot/state 目录全部零写拒绝；
- mismatch 后恢复 artifact 的 recapture race 硬失败；
- 稳定 state/event/prepared corruption 发布 raw-bound INCONCLUSIVE；
- detached/unsafe/moved loader path 拒绝；
- 第 541 槽封存可加载 INCONCLUSIVE；
- 完整 Decimal context 不受 ambient 变化影响。

新 design/plan/source/test/Schema/docs 进入 evaluator build identity。package 保持 `0.59.0`，manifest
version 保持 `1.53.0`，在所有输入稳定后重新计算 tree/self hash，不再增加语义版本。

## 10. 非目标与失败关闭

- 不改 v0.58 plan/runtime/scheduler/deployment 运行语义；
- 不处理 shared publisher 的 temp-inode 原子重写，partial target 继续 fail-closed；
- 不实现 Web/alerts/projection/replacement Challenger；
- 不安装、不启动、不网络请求、不凭据、不真实 Broker/订单；
- 不宣称可持续赚钱、AI 优势、Paper 完成或实盘资格。

`production_activation.enabled=false` 保持不变。
