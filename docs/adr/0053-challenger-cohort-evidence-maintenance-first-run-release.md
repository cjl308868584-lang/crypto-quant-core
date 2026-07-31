# ADR-0053：Challenger Cohort 维护首次自然运行证据发布

日期：2026-07-31

状态：已接受

## 背景

v0.51 已把每天北京时间 08:10 的证据维护 LaunchAgent 安装到固定用户域，
v0.52 又在首次自然槽之前冻结了只读 observer。首槽前的 WAITING 只能证明没有提前
运行，不能证明调度按期执行。真实成功证据必须来自冻结 observer，且不能通过
`kickstart`、手工调用维护入口、补写日志或回填 evidence roots 取得。

## 决策

1. 首次自然槽只允许使用 tag `v0.52.0`、提交
   `d0683658957c26ba868b567d27bfbe5fbb308175` 中的 production observer 验收。
2. 观察前先只读核对 LaunchAgent、SQLite/WAL、策略和维护日志、source bundles
   及 cohort receipt/archive/result roots。
3. 只有 observer 返回
   `FIRST_NATURAL_MAINTENANCE_RUN_COMPLETED_VERIFIED` 并发布 runtime receipt，
   才允许进入 v0.53。
4. v0.53 release CLI 只接受 runtime receipt、v0.51 install receipt、deployment
   manifest、两个冻结 external trust hash 和固定 Git artifact 路径。
5. release CLI 必须先用 v0.52 production loader 重放 runtime receipt，再以
   no-overwrite 方式发布逐字节副本，并从 Git artifact 再重放一次。
6. Git artifact 不添加 wrapper、时间、摘要、Git 身份或人工解释；发布说明只写入
   ADR、实施追踪和 README。
7. 本版本不修改 maintenance、策略 Runner、state、日志或 cohort roots，不增加
   市场网络、Broker、订单或凭据权限。

## 真实结果

- first natural schedule：`2026-07-31T00:10:00.000Z`
  （北京时间 `08:10`）；
- maintenance summary observed：`2026-07-31T00:10:04.110Z`；
- observer observed：`2026-07-31T08:00:42.902Z`
  （北京时间 `16:00:42.902`）；
- LaunchAgent：not running、`runs=1`、last exit `0`；
- maintenance stdout：唯一一行规范 summary，SHA-256
  `84b600b5cc82d06f59f38a10118764e5d7fde99cf7787901b19e466ca620ad67`；
- maintenance stderr：0 字节；
- maintenance status：`COHORT_EVIDENCE_NO_COMPLETED_EPISODES`；
- 首轮维护时 cohort slot 计数为 4，completed Episode 为 0，因此 archive 网络请求
  和经济结果均为 0；
- receipt id：
  `challenger_cohort_evidence_maintenance_first_run_receipt_c0298535143bb17418f2ebea5c08667c237f0a64a7a381547fff84d9bea42b07`；
- receipt hash：
  `b89087541fa590c41e4ae3533cb11da0e0328c0ff60cbad36e1972bd44446ee4`；
- runtime/Git 文件均为 10,273 字节，文件 SHA-256 均为
  `86e85a40ed9c09d90568b0c9cc50ad439092155718c929072ea3bb3539e3598f`；
- observer network、Broker、order、strategy state write、strategy Runner
  invocation、maintenance invocation 全部为 0。

## 后果

首次自然维护成功证明 evidence pipeline 能在预注册时间按计划执行，减少遗漏亏损
Episode、只归档有利结果或人工挑选时间的空间。它不证明策略盈利、cohort 完整、
系统 Paper 或 AI 优势。

后续必须继续自然收集完整 90 天、540 个槽位及全部 Episode，固定 tail end 前不得
运行累计 PnL 门。只有 v0.48 预注册的样本量、ESS、功效、LCB、时间块、回撤、
1.5 倍摩擦和 leave-Top-5 门在完整数据上满足，才可能得到研究 PASS；研究 PASS
仍不等于实盘资格。
