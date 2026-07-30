# 实施追踪 v0.44.0

日期：2026-07-30

状态：Cohort 累计经济评估计划已在首槽前注册

## 本版本完成

- 设计冻结提交 `cd3ad50`，北京时间 `2026-07-30 18:22:31`；
- 注册时间 `2026-07-30T10:22:40.000Z`；
- exact 绑定 v0.43 cohort plan ID/hash/file SHA；
- 固定 540 个必需槽位、六个 15 天时间块和全 Episode 纳入；
- 固定主假设、MBB、ESS、MERE、功效、CI 精度与样本门；
- 固定正常成本、1.5x 摩擦、最大回撤和 Top-5 leave-out 门；
- 固定最终状态机及研究/Paper/Release/AI 资格边界；
- 新增 Schema/package mirror、deterministic builder、owner-only publisher/
  loader、自哈希、stable ID 与 canonical artifact。

## 固定身份

- source v0.43 file SHA-256：
  `a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff`；
- evaluation plan ID：
  `challenger_cohort_evaluation_plan_54a5456345f57219e2ee8763fd35dd4c753e843d31709f342e283fd4026eb037`；
- plan self hash：
  `a6901e7e721682e6d3e7ded9000b5f183ed35e694b7036c7b596c0555a3ab440`；
- exact artifact SHA-256：
  `49e3b7642e163bb95c4ce01bc1c8d95a23b0cefce277d2f99f2e69029207a4d8`。

## 核心门

- completed Episode count：`>=30`；
- Geyer ESS：`>=20`；
- MBB：block length `3`、minimum blocks `10`、replicates `10000`；
- seed：`2026073044`；
- MERE：每 Episode 净收益 `0.005`；
- achieved power：`>=0.80`；
- two-sided CI full width：`<=0.02`；
- primary one-sided 95% LCB：`>0`；
- fixed 15-day blocks：至少 `5/6` 累计 PnL 非负且 6 块均非空；
- fixed-notional max drawdown：`<0.10`；
- 1.5x friction total PnL：`>=0`；
- leave Top-5 positive Episode 后主 LCB：`>0`。

## 安全与资格

- runtime-state read / market / Runner / Broker / order / state-write：
  `0/0/0/0/0/0`；
- 调用方时间、样本、阈值与经济覆盖：全部禁止；
- early success、PnL early stop、window reset/extension：全部禁止；
- profitability：
  `INELIGIBLE_RESEARCH_PROXY_NOT_SYSTEM_PAPER`；
- AI comparison：`INELIGIBLE_NO_PAIRED_AI_COHORT`。

## 验证

- focused 回归：9/9；
- 全量 tests：595/595；
- 100 次 deterministic build：逐字节一致；
- 参数和资格篡改在重算自哈希后仍被拒绝；
- Golden Vector：41；
- Evaluator build input：189；
- Build input tree hash：
  `aa06b7813fa5ccd90db7d6d7cc204205e2e5bfe116a081569a2cd758f54eb020`；
- Evaluator build hash：
  `d8c6e0edabc141cf2359a90da1e6a121fbd6b520b43fbcffe2cebb86471e65a3`；
- `make validate`：完成；生产门禁继续保持预期的
  `DESIGN_BASELINE / PRODUCTION_ACTIVATION_DISABLED` 关闭状态。

## 下一步

不干预地启动并持续收集 v0.43 cohort。下一工程版本应把只针对首个 Episode 的
receipt/archive/result 管线泛化为 cohort 内任意 Episode 的不可变逐项流水线，
但不得改变本版本冻结的统计与经济规则。
