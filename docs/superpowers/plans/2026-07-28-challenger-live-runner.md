# v0.31 Challenger 实时只读 Runner 实施计划

1. 冻结唯一公共请求、可信时钟、槽位和跨槽 Kline 不可修订边界。
2. 实现固定 request/transport、严格 receipt 和 raw Kline replay。
3. 实现 due/not-due/missed 编排、source bundle 与先来源后 decision 提交。
4. 实现无 URL/time/symbol/credential/order 覆盖的 CLI。
5. 覆盖请求计数、幂等、输入修订、篡改、权限和 Schema mirror 测试。
6. 保存首槽前 not-run 证据，更新 ADR、README、版本和 Evaluator build。
7. 运行 focused/full validation，提交、合并并标记 `v0.31.0`。
