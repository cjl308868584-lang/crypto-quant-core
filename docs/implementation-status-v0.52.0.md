# 实施追踪 v0.52.0

日期：2026-07-31

状态：已实现；真实首槽前 WAITING，等待北京时间 08:10 自然运行

## 本版本交付

- 以提交 `6caab24` 冻结首次自然维护运行观察器设计；
- 新增只读 observer、CLI、production receipt loader；
- 新增严格 Draft 2020-12 receipt Schema，config/package mirror exact；
- 自动从 v0.51 install/deployment/contract 信任链派生 service、schedule、日志、
  strategy runtime 和三个 cohort roots；
- 固定 WAITING、PENDING、COMPLETED、MISSED/FAILED 状态机；
- 首槽成功 receipt 绑定 launchctl print、唯一 maintenance summary、日志前缀、
  cohort inventories 和观察前后不变证明；
- loader 允许未来只追加，不允许修改已封存日志前缀或 evidence 文件。

## 真实首槽前观察

- observed at：`2026-07-30T21:02:53.979Z`
  （北京时间 `2026-07-31 05:02:53.979`）；
- first natural schedule：`2026-07-31T00:10:00.000Z`
  （北京时间 `08:10`）；
- completion deadline：`2026-07-31T00:20:00.000Z`；
- LaunchAgent：not running、`runs=0`、never exited；
- maintenance stdout/stderr：不存在；
- cohort receipt/archive/result roots：不存在；
- status：`WAITING_BEFORE_FIRST_NATURAL_MAINTENANCE_RUN`；
- receipt published：false。

执行机 `date` 与独立 UTC+08 时间源均显示仍在首槽前，因此没有采信“已经过
12:10”的口述时间，也没有把合法 WAITING 误报为漏槽。

## 安全边界

观察前后完全不变：

- strategy state SHA-256：
  `3765170895811cc24a51154eef4c742f23874a760ff24520df07e722241fb6aa`；
- strategy stdout SHA-256：
  `1705c9e6f0d2171a3d4e055b30a0d02023c3e634fbee93a5b261b46391ca008d`；
- strategy stderr SHA-256：
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；
- maintenance invocation、observer network、Broker、order、strategy state write、
  strategy Runner invocation 全部为 0；
- 只执行一次固定 `launchctl print`。

## 验证

- v0.52 focused tests：10/10；
- v0.49/v0.50/v0.51/v0.52 adjacent regression：50/50；
- Schema mirror 与 Draft 2020-12：通过；
- compileall：通过；
- 真实 production loaders：通过；
- 真实 pre-slot read-only observation：WAITING，全部快照前后不变；
- 全量 tests：704/704；
- evaluator build input：229；
- evaluator manifest version：`1.47.0`；
- evaluator tree hash：
  `6ad6cf07e5058a9e46af6ba32f140beffae941563706b539448d67d56f5c93ab`；
- evaluator manifest hash：
  `97f3671227a4de8bc0a958adc60c605a72ab8bd49ac9017b35951d13deaebc68`；
- `make validate`：evaluator、Schema 与治理模板技术验证通过；release policy 按
  设计保持 `DESIGN_BASELINE` / `PRODUCTION_ACTIVATION_DISABLED`；
- main CI 在合并后复核。

## 尚未完成

北京时间 08:10 前禁止手动运行 maintenance。自然槽后必须使用本版本冻结的
observer：

- 成功则 exact 封存 first-run receipt，并作为独立后续版本发布；
- 10 分钟窗口内证据未完成则保持 PENDING；
- deadline 后 `runs=0` 或非零退出则进入失败取证，禁止补跑或伪报。

本版本不证明 cohort 完整、策略盈利、系统 Paper 或 AI 优势；90 天全纳入 cohort
和 v0.48 固定尾部累计门仍未完成。
