# 实施追踪 v0.65.0

日期：2026-08-22

状态：`INCONCLUSIVE_KEEP_CURRENT_CORE`

## 已完成

- 预注册 plan：file SHA-256
  `c5bff241ee4dbba2ceb271d2842a0663669161f33416b2f2ac6caea5a78d6c08`，plan ID
  `nautilus_v065_plan_85b7b8379ccbe4378d6495bc158f0151ca2dbd4cf5003326b5acd56241fe3bef`，
  plan hash `54f47c96500f3ab5688e629105777f74294370b1f6e957b1094bec896473f414`；
- reviewed code commit `1f8634046ba586d4db26b38cd432e92755c2b2be`，plan-only commit
  `2cdff05629b2c6d0da30d30b12a294311c9c61ac`；
- 正式 comparison SHA-256
  `b679261e72f0eb81364be2878dc4ef8813279f47b1f57d31b460032bd08a77e5`；
- 正式 receipt SHA-256
  `11d15412ef7402434f3802fa380b7c4183de55a04d6ce025036d29c341ecc252`；
- completion marker SHA-256
  `cc52af4c5db422a688d5775c5a4900ede2477f2663e7e6b717a9b4dedb263202`；
- production formal-set loader 已从实际 sibling files 独立重放，marker 状态为
  `FORMAL_CEREMONY_COMPLETED_VERIFIED`。

## 真实结果

首次且唯一正式 ceremony 输出：

- conclusion：`INCONCLUSIVE_KEEP_CURRENT_CORE`；
- reason：`NAUTILUS_V065_PLATFORM_MISMATCH`；
- `runner_invocation_count=0`；
- supply-chain transcripts：0；
- credential/market/account/Broker/order/production-state-write counters：全部 0。

根因是正式命令使用本机 CPython 3.9 启动，而冻结候选要求 CPython 3.12。失败发生在下载和
runner 前。结果不证明 Nautilus 不适配，不证明当前核心更优；没有 Golden、成交、费用、持仓、
PnL 或 fresh-process 引擎对照。

## 发布与 CI

- package：`crypto-quant-core 0.65.0`；
- evaluator build：`release-evaluator-build-v1@1.59.0`；
- 公共 Actions 保留 Ubuntu 3.9/3.12 core matrix；
- 独立 `macos-15` arm64/Python 3.12 job 只重放已提交 INCONCLUSIVE 证据，不运行 ceremony/runner，
  不安装 NautilusTrader；
- PR CI、merged-main CI 与 annotated tag identity 仍是发布门。

本版本没有安装或启动 System Paper/replacement service，没有开始 90 天/540 槽位，也没有任何
盈利、AI 优势、Canary 或实盘资格。
