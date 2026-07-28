# ADR-0033：Challenger LaunchAgent 安装与私有执行快照

日期：2026-07-28

状态：已接受

## 背景

v0.32 只生成合同，没有证明真实安装。v0.33 首次按合同从 `~/Documents` 启动
时，`launchctl` 已加载服务并显示正确 `PYTHONPATH`，但后台 Python 无法导入
项目模块，RunAtLoad 退出码为 1。终端中的相同最小环境可正常导入，因此仅验证
解释器和环境变量不足以证明后台可执行。

## 决策

1. 安装目标固定为当前用户 `gui/<uid>` 域和固定 Label，不提供任意目标、域、
   命令或凭据参数。
2. plist 以 owner-only 临时文件、fsync 和无覆盖原子 link 安装。
3. 只调用固定 `launchctl print`、`bootstrap`、`print`；bootstrap 失败时仅
   回滚本次新建文件。
4. bootstrap 成功后若 print 验证失败，保留现场，不删除可能仍被加载的 plist。
5. 执行代码必须位于 runtime 下 `deployment/<revision>` 私有快照，禁止直接
   从开发目录安装。
6. 安装 receipt 绑定合同、plist、目标 inode/device/mode/hash、全部固定命令
   evidence，以及执行快照逐文件树哈希。
7. 安装/加载和 RunAtLoad 分开取证；安装 receipt 不伪造运行成功。

## 实际结果

- 私有快照：提交 `b96955a`，82 文件，1,687,320 bytes；
- 执行树哈希：
  `10695e7ab2cf1fe2a284cfd2429dcd512b72b3d76cc03c09c27543a062f2e11c`；
- plist SHA-256：
  `f6b2283ad4c01ee6e7dc8e954bdcb29dd221d5b79d4a04b69618af1d26182b53`；
- hardened receipt hash：
  `e160a7f4603e45751e2618b9132adf5050e88c382e08a135f789a115de93b65c`；
- `launchd runs=2`，两个日志记录均为 `NOT_DUE`，`last exit code=0`；
- 每次 server-time 请求 3、合计 6，Kline/decision/order 均为 0；
- 安装发生在日历触发分钟，无法严格归因哪次来自 RunAtLoad、哪次来自日历触发。

第一次失败的 plist、日志和 receipt 均在 owner-only 目录中保留，没有删除。

## 后果

系统已经开始由操作系统按计划唤醒，但尚未到首个登记的 forward 时点，不能声称
已有 OOS 决策、收益或 AI 优势。部署快照一旦变化，receipt 复核将失败；后续代码
升级必须形成新的快照、合同、安装 receipt 和独立 RunAtLoad/首槽证据。
