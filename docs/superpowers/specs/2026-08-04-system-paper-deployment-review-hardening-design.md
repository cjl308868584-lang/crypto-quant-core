# System Paper deployment trust chain review hardening design

日期：2026-08-04

目标版本：v0.58.0

基线：`fbd0b1a3c920b9d95a0def53a81325e1917f7114`

状态：冻结，取代原 v0.58 设计中与本文冲突的要求

## 1. 背景与裁决

v0.58 首轮实现在发布前独立审查中被确认存在四个阻断性缺陷：

1. `RunAtLoad=true` 使 `bootstrap` 可在 install receipt 封存前运行 runtime；
2. 通用 `_publish_exact` 的 `exists → os.replace` 竞态会覆盖并发创建的目标；
3. start-receipt loader 信任 receipt 内的 observation 字段，没有重放 SQLite、
   prepared records 和 log 语义；
4. production loaders 会执行仅绑定 pathname 的外部 Python。

本文选择 **calendar-only activation**：LaunchAgent 固定 `RunAtLoad=false`，installer
只负责安全加载配置和在 runtime 可能自然执行前封存 install receipt。首次
runtime 只能由安装后的下一个 `StartCalendarInterval` 自然触发。不增加
kickstart/start/enable/submit 或人工 Runner 入口。

放弃两个备选：

- disabled 两阶段 activation 需要额外可变 OS 事务和新命令，不必要；
- RunAtLoad runtime receipt gate 仍会在 bootstrap 时启动未取证进程，不符合安装边界。

## 2. 激活顺序与时间语义

- plist 必须且只能包含六个本地时间 `HH:05` 的 `StartCalendarInterval`，
  `RunAtLoad=false`。
- installer 仍只调用 `print → bootstrap → print`。`bootstrap` 成功不得导致
  runtime、network、scheduler、Broker 或 order 调用。
- install receipt 成功发布后，下一个严格晚于 `installed_at` 的 UTC 4h 边界才是
  `first_eligible_slot`。
- 重启不保证补停机期间的槽位。下一个自然日历触发由 scheduler 按已冻结
  no-backfill 状态机处理；如果因停机形成缺槽，必须永久失败而不是借
  RunAtLoad 补运行。

## 3. 真正的 no-overwrite 发布

新增 System Paper 专用 owner-only publisher，不再使用
`research_corpus._publish_exact`。它必须：

1. 使用 retained parent dirfd，要求目录当前 owner、exact `0700`、无 symlink；
2. 使用 `O_CREAT|O_EXCL|O_NOFOLLOW`、mode `0600` 创建随机临时文件，完整
   write/fsync；
3. 使用同一 dirfd 内的 no-replace `link()` 公布，成功后 unlink temp 并
   fsync directory；
4. `EEXIST` 时不 chmod、不 replace，只用 `O_NOFOLLOW` 打开已有目标，且仅在
   regular file、owner、mode `0600`、link count 1、size 和 exact bytes 全部一致时
   幂等成功；
5. contract/plist 两个文件仍各自 no-overwrite，任一冲突都失败关闭。

范围覆盖 launchd contract/plist、preflight receipt、install success/failure receipt 和
start receipt。

## 4. 纯 loader 与 Python 身份

- `load_system_paper_launchd_contract` 及其下游 preflight/install/observer/start loaders
  必须纯文件重放：不调用 subprocess、Python、Git、launchctl、network 或 runtime。
- snapshot import 检查只允许在 renderer 和 preflight 的显式 command boundary 运行，
  且必须使用可注入 runner。观察器总命令数仍为一次固定 launchctl print。
- contract 增加 Python executable `path/device/inode/mode/owner/size/sha256`、精确
  `sys.version`、package version 和 lockfile SHA-256 绑定。preflight 重做这些身份
  检查并显式运行 snapshot import；loader 只比较文件身份与冻结记录。
- 执行文件身份改变时必须重新 render/preflight，禁止路径相同即默认可信。

## 5. preflight 稳定性与凭据边界

- receipt 保留当时 `free_bytes` 作取证，loader 只要求 device、filesystem id、
  `is_local=true` 不变，并重算当前 `free_bytes >= 5 GiB`；不要求可变空闲字节
  完全相等。
- 新增 injectable credential-boundary probe。冻结环境变量名为
  `BINANCE_API_KEY`、`BINANCE_API_SECRET`、`BINANCE_SECRET_KEY`、
  `CRYPTO_QUANT_API_KEY`、`CRYPTO_QUANT_API_SECRET`；冻结文件为
  `~/.config/crypto-quant/credentials.json`、`~/.config/binance/credentials.json`、
  `~/.binance/credentials.json` 和 `<runtime_root>/credentials`。只记录命中名称与
  存在计数，永不读取、写入或输出 secret value。
- 任一 credential 边界命中时 status 必须失败关闭，且安装器为零 launchctl/
  write。

## 6. installer 终态、最终 target 和 launchctl 权威

- installer 在 bootstrap 前保留 parent/target descriptor 和 source plist bytes。bootstrap 后以
  descriptor + pathname 双重复核 target device/inode/mode/owner/link/size/SHA-256，并要求
  exact bytes 等于 source plist。receipt loader 复核全部字段，包含 device。
- post-bootstrap print 失败不删除已加载配置，但必须发布 immutable
  `LOADED_VERIFICATION_FAILED` forensic receipt，包含 pre-print、bootstrap、failed post-print、
  target 身份和零 runtime/network/Broker/order 计数，然后返回明确失败。成功
  loader 不得接受该 receipt 作为 install authority。
- launchctl print 使用固定、有界的实际 macOS fixture 解析器；必须按字段精确
  验证 label、plist path、program、有序 arguments、working directory、`PYTHONPATH`、runs、
  last exit status/state。不允许简单 substring 出现代替字段绑定。

## 7. observer 和持久 start-receipt replay

- observer 只使用 production loader 返回的 contract object，不得再次 raw pathname read。
- 首槽观察仍在发布时保留所有 source/state/WAL/log/artifact descriptor，并在发布前
  复核未改变。
- start receipt 必须可在后续槽位追加后持久重放。loader 对 contract、plist、
  preflight、install target、首个 source bundle 和首个 slot artifact 仍要求 exact
  bytes；对只追加 state/WAL/stdout 允许 size/mtime/hash 后续变化，但必须保持
  owner/mode/link 与同一文件身份。
- loader 从当前 SQLite/WAL 纯只读副本重放事件链，自动找到第一个
  `SUCCEEDED`，并重建到该事件为止的 chain hash、prepared input/result、slot id、
  first-eligible 时间、terminal count 和 result semantics。
- stdout 按 canonical JSONL 解析，必须保留与首槽 artifact 一致的第一条成功摘要；
  后续追加可接受。stderr 任何非空均失败关闭。
- 初次 launchctl print 的有界 exact stdout/stderr bytes 作为 receipt 内部证据封存。
  loader 只对这些 bytes 运行纯 parser，不再调用 launchctl。
- receipt 的 observation 必须与上述重建值精确一致；只协调修改字段和 self-hash
  不得通过。
- start receipt 文件固定非空且不超过4 MiB，读取前先验证 size。

## 8. 测试与发布门

每个审查 finding 都必须先有独立红灯回归，至少包含：

1. bootstrap fake 尝试执行 runtime 时证明 `RunAtLoad=false` 不运行，observer 派生
   安装后下一自然槽；
2. 并发目标在 publish 前创建，发布器不覆盖；只有 exact safe 目标幂等；
3. 协调修改 event-chain/prepared/log/first-slot 字段后重算 receipt hash 仍被 loader
   拒绝；后续合法槽追加后首槽 receipt 仍可重放；
4. 每次 production loader 的 subprocess/launchctl/network/runtime 调用数为零；observer 恰好
   一次 launchctl print；
5. `free_bytes` 合法漂移可加载，低于门槛拒绝；凭据 env/file 存在则预检失败；
6. post-bootstrap print 失败保留 forensic receipt；target 替换、设备变化或字节改变
   拒绝；
7. 真实字段 fixture 中的 displaced/duplicate/substring 伪绑定被拒绝；
8. oversized start receipt 在 JSON parse 前拒绝；所有 ranged `git diff --check` 通过。

修复后必须重新运行聚焦、相邻、全量 unittest、Schema mirror、compileall、
build manifest、`make validate`、独立复审，再进入 Draft PR/CI/main/tag。

## 9. 非目标与全局关闭

本设计不执行 production render/preflight/install/bootstrap/runtime，不创建 start receipt，
不开始90天计时，不请求市场、不读凭据值、不调用 Broker、不下单。它不实现
v0.59 evaluator、tail-blind projection、Web/alerts/runbooks 或 replacement Challenger。

`production_activation.enabled=false` 必须保持。任何测试、loader、hash、path、Schema、
LaunchAgent 或证据异常都阻断发布；禁止宣称盈利、AI 优势、Paper completion、
Canary 或实盘资格。
