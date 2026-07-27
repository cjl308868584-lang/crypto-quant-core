# ADR-0032：Challenger 无凭据 LaunchAgent 合同

日期：2026-07-28

状态：已接受

## 背景

v0.31 Runner 只有被及时调用才能保存首个前向槽位。手动记忆执行容易漏槽，
而通用调度脚本可能携带账户凭据、任意命令或错误的本地时区。

## 决策

1. 单独生成 Label 为 `local.crypto-quant.challenger-forward` 的 LaunchAgent。
2. 当前系统必须明确为 Asia/Shanghai、UTC+08:00、DST=0；本地每4小时的网格
   与 UTC 4h 网格一致。
3. 在本地 `0,4,8,12,16,20` 点02分及 RunAtLoad 调用 Runner。
4. ProgramArguments 只含 Python、固定 module、state path 和 output root。
5. 环境变量只含 `PYTHONPATH`；不包含 credential、URL、symbol、clock 或订单。
6. repository/runtime/python 必须是合法绝对路径；runtime 不得为 symlink。
7. plist 和合同必须自哈希、Schema 校验、语义重放并 owner-only 发布。
8. 生成器不调用 `launchctl`，合同固定标记
   `NOT_INSTALLED_NO_EXTERNAL_RECEIPT`。

## 理由

把“生成配置”和“安装运行”分开，能够在任何后台进程启动前审查真实路径、参数、
时区和权限。调度器只负责唤醒；是否到期、是否漏槽以及网络边界仍由 v0.31
Runner 失败关闭。

## 实际结果

已在仓库外生成真实合同和 plist：

- contract hash：
  `ac1d58ebe5d7b99bdebe7f33dd674d7c60099c52068ea096314608ebc1ce0fe7`；
- plist SHA-256：
  `a86f69f87e767198a9582ad27c44e850a092e8589bf42b7a05e1e22fdab19cfb`；
- runtime/state/log/artifacts：0700；
- contract/plist：0600；
- `launchctl` 调用：0。

## 后果

系统已有可审查的调度合同，但仍没有安装或运行证据。下一步若安装，必须把目标
plist inode/hash、launchctl domain/status、安装/加载时间和首次运行结果保存为
独立 receipt；失败不得被“合同已生成”掩盖。
