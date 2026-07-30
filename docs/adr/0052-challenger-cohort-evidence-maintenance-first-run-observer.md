# ADR-0052：Challenger Cohort 维护首次自然运行只读观察器

日期：2026-07-31

状态：已接受

## 背景

v0.51 已加载每天北京时间 08:10 的独立维护 LaunchAgent，但安装只证明调度配置，
不能证明它曾自然运行。手工调用维护入口或 `kickstart` 会破坏“自然槽”证据，也可能
使日志和 cohort inventory 无法区分自动运行与人工补跑。

用户侧口述时间与执行机/独立 UTC+08 时间源一度冲突；仅根据口述时间把 `runs=0`
判为漏槽同样会制造错误结论。

## 决策

1. 在首槽前冻结独立 observer；CLI 只接受 install receipt、deployment manifest、
   两个 external trust hash 和 receipt output root。
2. service、contract、plist、schedule、日志、策略 runtime 与 cohort roots 全部从
   production-loader 验证的对象派生，不允许调用方选择。
3. 观察器只执行一次固定 `launchctl print`，不运行 maintenance、策略 Runner、
   Broker 或订单，不访问网络，不写策略 state。
4. 首个自然时间由 install `verified_at` 和冻结 Asia/Shanghai 08:10 cadence
   自动派生，固定 10 分钟完成窗口。
5. WAITING/PENDING 不发布 receipt；deadline 后 `runs=0` 失败关闭。只有成功退出、
   唯一 stdout summary、空 stderr、合法阶段关系和稳定 inventory 才发布 receipt。
6. receipt loader 固定首槽日志前缀和已观察文件，允许未来自然运行只追加新日志和
   evidence，不允许修改已封存前缀。
7. 口述时间不能覆盖系统 UTC clock、冻结 schedule 和 launchd 运行证据。

## 首槽前真实结果

- observed：`2026-07-30T21:02:53.979Z`
  （北京时间 `2026-07-31 05:02:53.979`）；
- first schedule：`2026-07-31T00:10:00.000Z`
  （北京时间 `08:10`）；
- deadline：`2026-07-31T00:20:00.000Z`；
- service：not running，`runs=0`，never exited；
- maintenance stdout/stderr 与 cohort receipt/archive/result roots 均不存在；
- 策略 state/stdout/stderr 及全部观察 inventory 前后不变；
- status：`WAITING_BEFORE_FIRST_NATURAL_MAINTENANCE_RUN`；
- receipt 未创建，maintenance/Runner/Broker/order/state-write 为 0。

## 后果

v0.52 可以在自然槽后无歧义地判定完成、pending、漏槽或失败，但本版本的 WAITING
不是成功 receipt。真实首槽结果必须在 08:10 后独立封存。即使首次维护成功，也只
证明证据管线按计划运行；90 天 cohort、固定 tail 累计门和费用后结果仍决定研究
资格，不能据此宣称盈利、Paper 或 AI 优势。
