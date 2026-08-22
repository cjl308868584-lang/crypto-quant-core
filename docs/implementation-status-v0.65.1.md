# 实施追踪 v0.65.1

## 结论

v0.65.1 是已发布 v0.65.0 研究证据之后的纯代码安全加固。它不重跑 v0.65.0 ceremony，
不修改 v0.65.0 research artifacts，也不产生新的 NautilusTrader 采用或拒绝结论。

v0.65.0 的唯一正式结论保持 `INCONCLUSIVE_KEEP_CURRENT_CORE`，原因为
`NAUTILUS_V065_PLATFORM_MISMATCH`，且 `runner_invocation_count=0`。该事实不证明
NautilusTrader 不适配，也不证明当前核心更优或具备盈利能力。

## 修复

- 平台门现在同时要求 macOS 15、arm64、Python 3.12 和 CPython；PyPy 等其他实现会在任何
  acquisition 前失败关闭。
- Sandbox runner 复用现有的有界命令执行器：标准输出和错误输出各受 4 MiB 上限约束，超时会
  终止进程组并进行有界 drain；超时、输出越界和启动失败映射为固定 runner failure。
- runner 的 credential、network 和 second-engine 安全违规分类保持不变。

## 权限边界

本版本不授权生产安装、真实 Broker 或订单，不创建凭据，不写 System Paper、replacement
Challenger 或任何现有 90 天证据根。`production_activation.enabled=false` 保持不变。

## 验收

- 新增非 CPython 平台红绿测试；
- 新增 runner timeout/output-limit 红绿测试；
- v0.65.0 四个正式 artifact 逐字节 SHA-256 回归；
- v0.65 loader/公开 CI 只读重放保持不变；
- 最终候选执行受影响测试、本地全量、公开 PR CI、main CI 与 annotated tag 身份门。
