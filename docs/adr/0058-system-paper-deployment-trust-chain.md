# ADR-0058：System Paper deployment trust chain

日期：2026-08-04

状态：已接受

## 背景

v0.57 只提供无凭据、确定性、离线的 WAL scheduler library，不存在可由
LaunchAgent 固定调用的 runtime CLI，也没有将 release checkout、执行快照、机器预检、
安装证据、只读首槽观察和90天起点串成单一信任链。在这些边界完成前，
安装或开始计时都不可验收。

## 决策

1. 使用固定 public-market source bundle 和 runtime CLI 作为唯一自然槽输入边界；禁止
   credential、账户端点、Broker 与 order 参数。
2. LaunchAgent 合同精确绑定 v0.57 foundation、v0.58 build identity、私有执行
   snapshot、固定 argv/environment、安全根目录和 UTC 4h 时间网格。渲染不安装、
   不启动服务。
3. preflight 对常在、时钟、重启、磁盘、网络、路径、Git/tag/build 身份进行
   fail-closed 校验；receipt 短期有效且不可覆盖。
4. installer 只允许固定 `launchctl print → bootstrap → print`，且仅在全部生产 loader
   复核后生成 owner-only install receipt；重试不得隐式 kickstart 或运行 Runner。
5. observer 只执行一次固定 `launchctl print`，保留文件描述符并在临时 SQLite 副本
   重放 state/WAL、prepared inputs/results、slot artifact 与 stdout/stderr。任何竞态、
   漏槽、失败、第二槽或协调篡改都失败关闭。
6. start receipt 只在首个自然成功槽仍保持 exact evidence bytes 时发布，从该槽
   自动派生90天半开窗口和540槽；pending 不创建输出根，冲突不覆盖。
7. 独立审查报告的4项Critical、6项Important和2项Minor全部进入冻结 hardening
   设计与实施计划：最终合同 `RunAtLoad=false`，loader不执行隐藏命令，安装只在冻结
   UTC安全窗口内进行，launchctl输出结构化解析，证据发布不可覆盖，start receipt
   从当前append-only state/log重放首槽语义并跨完整复核过程保留来源描述符。

## 后果

v0.58 只冻结和发布上述代码、Schema、合同与 loader。本版不渲染生产合同、
不执行 preflight/install/bootstrap/runtime，不创建 start receipt，也不开始90天计时。

本决策不证明盈利、AI edge、Paper completion、Canary 或任何真实交易资格。
`production_activation.enabled=false` 继续生效。
