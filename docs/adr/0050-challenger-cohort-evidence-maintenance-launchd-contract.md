# ADR-0050：证据维护必须使用独立、无凭据、非 RunAtLoad 的 LaunchAgent 合同

日期：2026-07-31

状态：已接受

## 背景

v0.49 已把 cohort receipt、官方日档和经济结果固定串联，但依赖人工记得执行。
现有通用调度器绑定账户 credential 路径；现有 Challenger LaunchAgent 又绑定实时
策略 Runner。把维护塞进任一现有服务都会扩大凭据或策略状态边界。

## 决策

1. 以独立提交 `e867d9f` 冻结 v0.50 详细设计。
2. 新增独立 label
   `local.crypto-quant.challenger-cohort-evidence-maintenance`。
3. plist 每天北京时间 08:10 唯一触发，对应 UTC 00:10，且
   `RunAtLoad=false`。
4. ProgramArguments 只调用 v0.49 maintenance CLI，计划、v2 strategy trust
   paths 与 receipt/archive/result roots 全部自动固化。
5. EnvironmentVariables 只含 `PYTHONPATH`；没有 credential、shell、URL、
   Broker、order、state 或 Runner 参数。
6. renderer 使用 production loaders 只读验证 strategy install receipt、
   contract 与 plist，不调用 `launchctl`，不发起网络请求。
7. 合同必须通过 Schema、自哈希、plist hash、语义重放和独立 trusted
   attestation；loader 不得自行生成信任值。
8. output root/scheduler directory 为 0700，合同/plist 为 0600；不得提前创建
   cohort evidence roots。
9. v0.50 只生成合同，固定状态
   `NOT_INSTALLED_NO_EXTERNAL_RECEIPT`；安装、私有快照和真实运行属于后续版本。

## 后果

系统现在有一份可以审计的自动维护合同，但尚未自动维护。它不改变策略、不增加
收益，也不证明服务已经运行。下一版本只有在再次复核 exact 合同、创建只读私有
执行快照、受控安装并保存 launchctl/runtime receipt 后，才能把
`automatic_maintenance` 从不合格改为已验证。安装候选必须以已发布 commit 的
私有快照重新渲染；不得把当前开发工作区路径直接当作长期执行代码。
