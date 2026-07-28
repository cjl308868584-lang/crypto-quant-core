# 实施追踪 v0.33.0

日期：2026-07-28

状态：真实 LaunchAgent 已安装、加载；首次 RunAtLoad 成功且尚未到期

## 本版本完成

- 新增固定用户域 LaunchAgent 安装器和最小 CLI；
- 固定 `/bin/launchctl`、`gui/<uid>`、Label 与 LaunchAgents 目标；
- 新增无覆盖原子安装、fsync、bootstrap 失败精确回滚；
- 新增 `launchctl print` program/path/state/output 绑定验证；
- 新增严格安装 receipt Schema、自哈希、固定命令 evidence 与语义复核；
- 强制使用 runtime 下 owner-only `deployment/<revision>` 执行快照；
- receipt 绑定逐文件路径、大小、SHA-256 汇总树哈希；
- 覆盖冲突、幂等、回滚、加载后验证失败、receipt/快照篡改和 CLI 权限边界。

## 真实安装与 RunAtLoad

- service：`gui/501/local.crypto-quant.challenger-forward`；
- target：
  `/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-forward.plist`；
- target：uid 501、mode 0600、inode 13229927；
- plist SHA-256：
  `f6b2283ad4c01ee6e7dc8e954bdcb29dd221d5b79d4a04b69618af1d26182b53`；
- execution snapshot：提交 `b96955a`，82 文件，1,687,320 bytes；
- execution tree hash：
  `10695e7ab2cf1fe2a284cfd2429dcd512b72b3d76cc03c09c27543a062f2e11c`；
- hardened receipt id：
  `challenger_launchd_install_receipt_d9f8b99b5aeef80bd7627fda751d856ce64b1e68bd016cf538dfe707b154260e`；
- hardened receipt hash：
  `e160a7f4603e45751e2618b9132adf5050e88c382e08a135f789a115de93b65c`；
- `launchd runs=2`，两个日志记录均退出 0；
- Runner：`NOT_DUE`，下个必需槽位 `2026-07-29T00:00:00.000Z`；
- 每次 server-time 请求 3、合计 6；Kline/decision/Broker/order：0/0/0/0；
- 安装发生在日历触发分钟，RunAtLoad 与日历触发的逐次归因未被证明。

首次从 `~/Documents` 运行因 macOS 后台访问边界无法导入模块而退出 1。该失败
现场已移动到
`control/failed-run-20260728-documents-tcc`，没有删除。随后改用 Application
Support 私有快照，重装和 RunAtLoad 均成功。

完整紧凑证据见
[challenger-launchd-installed-v0.33.0.json](../artifacts/challenger-forward/challenger-launchd-installed-v0.33.0.json)。

## 验证

- v0.33 focused tests：8/8；
- 相邻 LaunchAgent/Runner 回归：20/20；
- 全量 tests：527/527；
- Golden Vector：41；
- Evaluator build input：156；
- Build input tree hash：
  `96451f49285d5e40160c24f032aac774ee83494dbabff671a796540bf8386774`；
- Evaluator build hash：
  `1b661faeed625892e2765ffd3f4ad1cdea0a9d2ae61b7f85af16fe8eff79a9ee`；
- `make validate`：完整执行成功；政策按设计继续为 `FAIL`。

## 仍未证明

- 首个登记 forward 槽尚未发生，没有真实 Kline source bundle 或 decision；
- 没有结果成熟、连续 Paper、真实成交、滑点或盈利证据；
- AI 臂仍没有获批模型，不能进入发布或下单链；
- Binance server time 不是独立第三方时间锚；
- 系统仍无 Broker、余额读取或真实下单能力。

## 下一步

保持 LaunchAgent 加载，等待 `2026-07-29T00:00:00.000Z` 首槽。届时必须检查
source bundle、decision append、state cursor、日志和未回填约束，并生成独立首槽
receipt；任何漏槽或数据修订都必须失败关闭。
