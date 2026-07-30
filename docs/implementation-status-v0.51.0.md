# 实施追踪 v0.51.0

日期：2026-07-31

状态：已实现、已真实安装；等待首次自然 08:10 运行

## 本版本交付

- 以提交 `ccd012e` 冻结私有快照与受限安装设计；
- 新增 owner-only content-addressed execution snapshot；
- 新增 deployment manifest、production loader 与 CLI；
- 新增固定用户域 installer、install receipt、production loader 与 CLI；
- 新增两个严格 Draft 2020-12 Schema，config/package mirror exact；
- candidate external trust 先在提交 `12dafda` 独立冻结；
- 真实执行固定 `print → bootstrap → print` 并安装维护 LaunchAgent；
- 没有 kickstart、RunAtLoad、手工维护调用、市场网络、Broker、订单或策略 state
  写入。

## 真实私有快照与候选

- prepared at：`2026-07-30T20:16:46.081Z`；
- snapshot：129 文件、2,351,237 bytes；
- tree hash：
  `8ae7cfac351c56a3666c33b18748d67e67ae82be3298caf8eb64de0a9d8e5904`；
- manifest hash：
  `410d5f48b25b1cbb3a99589002834698f95946ca0c6f6a59e98ebe5cb0072795`；
- candidate contract hash：
  `397070772e6131e57a5b9d2ea590b50b98fd5a3d7f4169e14116625a48d70564`；
- candidate external trust：
  `9f7d6b7e2beb8103fb8cf1da1281d086a243bc63f3c5cc7992a8d4c0b878b83f`；
- candidate plist SHA-256：
  `efd7070b185a7e6eca629f93502894b0c1def6a0277b9bb87c6a0c5c87a9d4e3`。

第一次真实准备因默认时钟携带微秒、未满足严格毫秒格式而失败。该次只创建了
owner-only snapshot，没有 candidate、launchctl 或安装；现场保留。修复后新增两项
默认时钟测试并生成新的 content-addressed snapshot，没有覆盖失败现场。

## 真实安装

- installed at：`2026-07-30T20:18:41.758Z`；
- verified at：`2026-07-30T20:18:41.761Z`；
- action：`INSTALLED_AND_BOOTSTRAPPED`；
- receipt id：
  `challenger_cohort_evidence_maintenance_install_receipt_22e924d97ad5edbd971791b1bfa4b6c53efa2ebf53ede0980af4ec24fb24aaba`；
- receipt hash：
  `ad39cc029d73c03656b20de7fa146d9acd3f963a5f9ef9f0eb6bb3417f1eff1b`；
- receipt file SHA-256：
  `9fa27c102e46fc1dcf65876050537d08ac4358d492fb89ca71b971f61af8c321`；
- target：0600、uid 501、单 hardlink、3,499 bytes；
- `launchctl`：preflight print=113、bootstrap=0、verified print=0；
- 安装后：`state=not running`、`runs=0`、`last exit code=never exited`；
- production receipt loader 独立重放通过。

## 安装前后安全边界

策略 runtime 三份 SHA-256 在安装前后完全不变：

- state：
  `3765170895811cc24a51154eef4c742f23874a760ff24520df07e722241fb6aa`；
- stdout：
  `1705c9e6f0d2171a3d4e055b30a0d02023c3e634fbee93a5b261b46391ca008d`；
- stderr：
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

安装后 maintenance stdout/stderr 和 cohort receipt/archive/result 根均不存在；
maintenance invocation、network、Broker、order、strategy state write 和 strategy
Runner invocation 全部为 0。

## 验证

- v0.51 focused tests：17/17；
- v0.33/v0.49/v0.50/v0.51 adjacent regression：48/48；
- 全量 tests：694/694；
- snapshot manifest：100 次确定性一致；
- compileall：通过；
- `make validate`：evaluator、Schema 与治理模板技术验证通过；
- release policy：按设计为 `DESIGN_BASELINE` /
  `PRODUCTION_ACTIVATION_DISABLED`；
- evaluator build input：224；
- evaluator manifest version：`1.46.0`；
- evaluator tree hash：
  `ffc44652035a6b49c16fc1b37d564dfb7a66f6d2e8386686f8bc059c81006fd2`；
- evaluator manifest hash：
  `efd2ae884e5306946eeeced2c010929ef0d8ca01d137a981beb73ff0944aa0ff`。

## 尚未完成

维护调度已安装但尚未自然执行。下一个允许动作是在北京时间 08:10 之后只读观察：

- `launchctl print` 的 run count 与 last exit；
- maintenance stdout/stderr exact bytes；
- v0.45/v0.46/v0.47 固定顺序 summary；
- cohort receipt/archive/result inventory；
- 策略 state 与日志没有被维护服务修改。

禁止 kickstart、补跑或手工调用维护入口。首次自然运行成功也只证明自动证据维护，
不证明 cohort 完整、策略盈利、Paper 或 AI 优势；v0.48 固定尾部累计门仍是研究
晋级的必要条件。
