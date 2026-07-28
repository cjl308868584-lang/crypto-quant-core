# 实施追踪 v0.34.0

日期：2026-07-28

状态：首槽只读观察器已就绪；真实状态仍为首槽前等待

## 本版本完成

- 新增首槽观察器、最小 CLI 与严格 receipt Schema；
- 固定首槽、4h deadline、安装 receipt 与全部派生路径；
- 新增 SQLite immutable read-only replay 和 metadata/decision 语义验证；
- 正确区分 0-byte WAL、owner-only SHM 与非空未 checkpoint WAL；
- 交叉绑定唯一 source bundle、首条 decision 和唯一 stdout `RECORDED`；
- 新增 stdout/stderr prefix 证据，允许未来合法追加但拒绝历史修改；
- 新增当前固定 `launchctl print` 路径绑定与 last-exit-code 验证；
- observer 网络、Broker、订单和 state write 权限均固定为 0。

## 真实首槽前观察

- observed at：`2026-07-28T09:00:27.036Z`；
- status：`WAITING_BEFORE_FIRST_SLOT`；
- forward start：`2026-07-29T00:00:00.000Z`；
- record deadline：`2026-07-29T04:00:00.000Z`；
- 北京时间计划启动：`2026-07-29 08:02`；
- decision/source bundle：0/0；
- state：uid 501、0600、24576 bytes；
- state SHA-256：
  `c71bc440e69b35716e9938300ca2b9052ae96b095e522c1811e0d360a3ac8157`；
- WAL/SHM：0/32768 bytes；
- stdout/stderr：2 条 `NOT_DUE` / 0 bytes；
- observer launchctl/network/state-write/Broker/order：0/0/0/0/0；
- 成功 receipt：未发布。

紧凑证据见
[challenger-first-slot-waiting-v0.34.0.json](../artifacts/challenger-forward/challenger-first-slot-waiting-v0.34.0.json)。

## 验证

- v0.34 focused tests：8/8；
- 观察器、安装器、Runner 相邻回归：27/27；
- 全量 tests：535/535；
- Golden Vector：41；
- Evaluator build input：161；
- Build input tree hash：
  `90c6f18927b7236e4f5800b0406e7cbd4570ebb64debd6b7f690f5ff4c54da42`；
- Evaluator build hash：
  `cc1d188ce1e24e68458a82ccfb203f3db109fe57eff890ef7567a19d5143cf04`；
- `make validate`：通过；发布门禁保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 仍未证明

- 首槽尚未发生，没有真实 Kline、source bundle 或 decision；
- 没有成熟结果、连续 Paper、真实成交、滑点或盈利证据；
- AI 臂仍无获批模型；
- Binance server time 仍不是独立第三方时间锚；
- 系统仍无 Broker、余额读取或下单能力。

## 下一步

保持 v0.33 LaunchAgent 加载。北京时间 2026-07-29 08:02 后运行本观察器：
若 decision 尚未出现但仍在 deadline 内，只能标记 pending；若 source/state/log
一致则发布真实首槽 receipt；若到 12:00 仍缺首槽则永久标记 missed，禁止回填。
