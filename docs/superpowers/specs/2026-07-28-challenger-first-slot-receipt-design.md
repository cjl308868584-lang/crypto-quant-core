# v0.34 Challenger 首槽观察 Receipt 设计

日期：2026-07-28

状态：冻结

## 1. 目标

在不联网、不触发 Runner、不修改状态库的前提下，观察并交叉验证 Challenger
登记首槽 `2026-07-29T00:00:00.000Z` 的真实结果。只有安装 receipt、当前
LaunchAgent、SQLite 首条 decision、source bundle 和 stdout 记录彼此完全一致，
才发布 owner-only 首槽 receipt。

该 receipt 只证明本机前向记录链闭环，不证明独立时间锚、结果成熟、收益或可下单。

## 2. 固定权限边界

- 只允许 `/bin/launchctl print gui/<uid>/local.crypto-quant.challenger-forward`；
- 不允许 bootstrap、kickstart、bootout、shell、网络、Broker 或订单；
- CLI 只接受 contract、plist、安装 receipt 和 receipt output root；
- state、bundle、stdout、stderr、service、target 均从已验证合同与安装 receipt
  推导，CLI 不允许覆盖；
- clock 只用于判定等待/漏槽，CLI 不允许提供时间。

## 3. 观察状态

- 当前时间早于首槽：`WAITING_BEFORE_FIRST_SLOT`，不发布 receipt；
- 首槽开始但未超过登记的 4h deadline，且 decision 尚未出现：
  `OBSERVATION_PENDING_WITHIN_RECORD_DEADLINE`，不发布 receipt；
- 超过 `2026-07-29T04:00:00.000Z` 仍没有首槽 decision：
  `FIRST_SLOT_MISSED`，失败关闭且不允许回填；
- 首条 decision 存在：其 `scheduled_for` 必须恰为登记首槽，否则失败；
- 验证全部通过：`FIRST_SLOT_RECORDED_VERIFIED` 并发布 receipt。

等待和 pending 不是错误，但也不是成功证据。

## 4. 只读状态验证

- state path 固定来自合同 ProgramArguments；
- state 必须是 uid 当前用户、mode 0600、link count 1 的普通文件；
- 观察时不得存在 `-wal` 或 `-shm`，否则视为运行中/未完成 checkpoint；
- 使用 SQLite `mode=ro&immutable=1` 与 `PRAGMA query_only=ON`；
- metadata 必须等于当前 Challenger policy/registration；
- decision bytes 必须 canonical JSON，并逐条 semantic replay；
- 观察前后 state SHA-256、inode、size 必须完全一致。

## 5. Source bundle 与日志

- bundle root 固定来自合同 output root；
- 首槽必须恰好存在一个可语义重放的 source bundle；
- bundle candidate decision 必须与 SQLite 首条 decision exact match；
- bundle 文件必须 uid 当前用户、0600、单 hardlink；
- stdout 必须是 bounded UTF-8 JSON Lines；receipt 绑定观察时的完整 prefix
  size/hash，后续只允许追加；
- 必须恰好有一条 `RECORDED` 记录绑定相同 decision id/hash、bundle path/hash；
- stderr 可为空或非空，但完整 size/hash 必须绑定；非空时 receipt 增加明确警告；
- 当前 `launchctl print` 必须绑定固定 service/program/state/output/log 路径，
  `last exit code` 必须为 0。

## 6. Receipt

Receipt 绑定：

- 经过重新加载验证的 v0.33 安装 receipt id/hash；
- contract/plist 与 execution snapshot；
- 固定 launchctl print argv、return code、stdout/stderr hash；
- state 文件观察时 stat/hash、metadata、decision count、首条 decision；
- source bundle id/hash/path/stat/file hash；
- stdout/stderr stat/hash、匹配日志行号和记录；
- observed_at、首槽、deadline；
- observer 自身 network/broker/order/state-write count 全为 0；
- Schema、自哈希、semantic replay 与 owner-only immutable publication。

## 7. 幂等与失败关闭

- 相同 receipt bytes 可幂等返回；
- 相同 receipt id 的不同 bytes 冲突；
- 多个首槽 bundle、多条匹配 RECORDED、decision/bundle/log 任一不一致均失败；
- state WAL/SHM 存在时不抢锁、不等待、不复制半完成状态；
- receipt 复核允许 state decision chain 与 stdout 在已绑定 prefix 后合法追加；
- 首条 decision、metadata、stdout prefix、目标、执行快照或 immutable bundle
  发生变化必须失败。

## 8. 验收

- before-start、within-deadline、missed 三种无 decision 状态正确；
- 成功 fixture 形成可加载、可重放 receipt；
- observer 执行前后 state bytes exact match；
- state metadata/row/bundle/log/launchctl 任一篡改失败；
- 多 bundle、多匹配日志、WAL/SHM、错误权限和 symlink 失败；
- CLI 无 state、bundle、log、service、command、URL、credential、order 或 clock
  覆盖；
- focused/full validation 后提交、合并并标记 `v0.34.0`；
- 真实首槽后再运行 observer，真实 receipt 作为下一证据版本提交。
