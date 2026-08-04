# 实施追踪 v0.58.0

日期：2026-08-04

状态：deployment trust chain 代码已完成；发布审查与全量验证进行中；System Paper 未安装、未启动

## 本版本交付

- 从固定公开 Binance Spot 请求家族生成 canonical、hash-bound market source bundle；
- 固定 runtime CLI 将 source bundle 送入 v0.57 WAL scheduler，不接受 URL、时间、
  symbol、credential、Broker 或 order 参数；
- owner-only deployment snapshot 与 LaunchAgent 合同，绑定 foundation tag/commit、v0.58
  package/build manifest、origin/main、Python runtime、argv/environment 和独立 roots；
- 常在/休眠、时钟偏差、重启稳定性、磁盘容量与文件系统、公开网络边界的
  fail-closed preflight 及短期 exact receipt；
- 只允许固定 `print/bootstrap/print` 的 restricted installer 和 exact install receipt；
- 一次 `launchctl print` 的只读首槽 observer，交叉复核 service、state/WAL、source
  bundle、artifact、stdout/stderr 和完整 parent-chain；
- 仅首个自然成功槽才发布的 owner-only start receipt，自动派生90天窗口与
  540槽，pending 时不创建输出根。
- 独立审查的4项Critical、6项Important和2项Minor已逐项按TDD关闭：包括
  `RunAtLoad=false`、安全安装窗口、纯loader、结构化launchctl权威、不可覆盖发布、
  有界单描述符receipt读取，以及可接受后续正常增长但拒绝首槽前缀/来源身份替换的
  永久语义重放。

## 安全与权限边界

- 本版本的发布和测试不渲染生产 contract，不执行真实 preflight/install/
  bootstrap/runtime，不创建 start receipt；
- 测试只使用临时目录和注入的 launchctl/machine/filesystem/network 边界；
- 无 credential、账户权限、live Broker 或真实订单；`production_activation.enabled=false`
  未改变；
- 90天计时尚未开始，没有盈利、AI 优势、Paper 完成或 Canary 资格证据。

## 验证记录

- TDD 聚焦/相邻验证已通过；start receipt 11项及System Paper相关测试均已通过；
- receipt读取竞态和跨来源文件替换均先得到确定性红灯，再由保留描述符与最终身份复核关闭；
- v0.58 完整独立审查、全量 unittest、compileall、`make validate` 与最终 build
  hash 将在发布前填入本节。

## 尚未完成

只有当 v0.58 审查、PR/main CI 和 annotated tag 均完成后，才能继续 v0.59
90天 evaluator、tail-blind projection 与只读 Web/alerts/runbooks。这些代码门全部通过
前仍不得设计或执行生产安装。replacement Challenger 须绑定旧 cohort 漏槽
失败并使用全新、独立的 service/state/log/bundle/evidence roots。
