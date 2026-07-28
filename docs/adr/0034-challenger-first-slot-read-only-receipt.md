# ADR-0034：Challenger 首槽只读观察 Receipt

日期：2026-07-28

状态：已接受

## 背景

LaunchAgent 安装与两次 `NOT_DUE` 只能证明调度链可运行，不能证明登记首槽实际保存
了公开输入和 decision。仅查看 stdout 也不能排除 state、bundle 或日志互不一致。

## 决策

1. 固定首槽为 `2026-07-29T00:00:00.000Z`，登记 deadline 为下一 4h 槽。
2. 观察器不得联网、触发 Runner、修改状态或接受路径/命令/时间覆盖。
3. 无 decision 时严格区分首槽前等待、deadline 内 pending 和永久 missed。
4. SQLite 只用 `mode=ro&immutable=1` 读取；非空 WAL 失败，合法 0-byte WAL 与
   owner-only SHM 可保留。
5. 首条 decision 必须与唯一 source bundle candidate 和唯一 stdout
   `RECORDED` 行 exact match。
6. 当前 LaunchAgent 必须由固定 `launchctl print` 证明路径绑定且最近退出码为 0。
7. Receipt 绑定安装 receipt、执行快照、观察时 state stat/hash、bundle、日志
   prefix 和固定命令 evidence。
8. 后续允许 decision chain 与日志在已验证 prefix 后追加；修改首条事实失败。

## 首槽前真实结果

真实观察时间 `2026-07-28T09:00:27.036Z`：

- 状态：`WAITING_BEFORE_FIRST_SLOT`；
- decision/source bundle：0/0；
- state SHA-256：
  `c71bc440e69b35716e9938300ca2b9052ae96b095e522c1811e0d360a3ac8157`；
- WAL：0 bytes；SHM：32768 bytes，均 owner-only；
- stdout 两条 `NOT_DUE`；stderr 0 bytes；
- observer 的 launchctl/network/state-write/broker/order：0/0/0/0/0；
- 成功 receipt：未发布。

## 后果

工具就绪不能被包装成首槽成功。首槽后必须再次运行观察器；只有生成
`FIRST_SLOT_RECORDED_VERIFIED` receipt 才能证明本机前向输入链闭环。该 receipt
仍不具备独立时间锚、成熟结果、正式 OOS 或盈利资格。
