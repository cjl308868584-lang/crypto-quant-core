# v0.31 Challenger 实时只读 Runner 设计

日期：2026-07-28

状态：冻结

## 1. 目标

把 v0.30 的确定性 challenger 状态机接到一个最小、固定、无凭据的 Binance
公共数据入口。Runner 只在当前应执行的 UTC 4h 槽位获取 21 根闭合 Kline，
保存完整时间探针和 HTTP receipt，再向 append-only challenger state 追加一条
research decision。

本版本不安装操作系统调度、不回填历史槽位、不观察未来结果、不计算收益、不读取
账户，也不提供 Broker、Order 或真实资金接口。

## 2. 固定网络边界

每次调用首先执行 v0.20 已冻结的三样本 Binance server-time probe。只有
`HEALTHY_ALIGNED` 或 `HEALTHY_CORRECTED` 才继续。

仅在当前槽位正好等于 state 的下一必需槽位时，执行一个公共 GET：

```text
https://data-api.binance.vision/api/v3/klines
  ?endTime=<scheduled_for_epoch_ms-1>
  &interval=4h
  &limit=21
  &symbol=ETHUSDT
```

- host、path、method、symbol、interval、limit 和 endTime 派生方式固定；
- 禁用环境代理；
- 自动重试 0 次；
- body 上限 256 KiB；
- redirect 必须仍是完整相同 URL；
- CLI 不接受 URL、host、symbol、slot、clock、header 或 credential 覆盖。

## 3. 槽位判定

- 注册首槽：`2026-07-29T00:00:00.000Z`；
- 可信当前时间向下取整到 UTC 4h；
- 空 state 的 next required slot 为注册首槽；
- 非空 state 的 next required slot 为最后一条 decision +4h；
- current slot 早于 next：`NOT_DUE`，Kline 请求 0；
- current slot 晚于 next：`MISSED_SLOT`，Kline 请求 0，永久不回填；
- current slot 等于 next：允许获取并追加；
- recorded_at 由同一 VerifiedRuntimeGate 的 monotonic clock 取得。

## 4. Kline 与跨槽一致性

Binance raw row 必须：

- 恰好 12 列；
- open/close 时间为整数毫秒且每根恰好 4h；
- 21 根严格连续、有序、唯一；
- 最后一根 close 为 slot 前 1ms；
- OHLC 和其余数值字段合法；
- ignore 字段固定为字符串 `"0"`。

`source_row_hash = business_hash(raw_row)`。

首槽 21 根行的 `available_at` 都是本次 response received time。后续槽位：

- 返回的前 20 根 raw row hash 必须逐条等于上一决策后 20 根；
- 重叠行沿用上一决策保存的原始 `available_at`；
- 只有新闭合的最后一根使用本次 response received time；
- 任一闭合 Kline 修订立即失败，不以新内容覆盖旧事实。

## 5. Source Bundle

每次到期执行先构建一个不可变 source bundle，包含：

- 完整 server-time probe；
- 本地派生 probe trust hash；
- 固定 Kline request；
- selected headers、完整 raw body、body SHA-256 和 receipt self-hash；
- 标准化 21 根 challenger Kline；
- candidate decision id/hash；
- bundle self-hash；
- 明确的本地时间与资格警告。

bundle 经 Schema、自哈希和 semantic replay 校验后，先以 hash 命名发布为
owner-only 文件，再追加 decision。若进程在两步间崩溃，最多留下不具备 state
引用资格的 orphan bundle；不得留下无来源 decision。

本地保存 Binance receipt 仍不是独立第三方 publication，因此正式状态保持
`UNANCHORED_LOCAL_PREQUENTIAL_ONLY`。

## 6. CLI

固定命令：

```text
python -m crypto_quant.challenger_forward_runner_cli
  --state-path <owner-only sqlite>
  --output-root <owner-only artifact root>
```

成功输出 `RECORDED`、`decision_id/hash`、`source_bundle_path/hash` 和请求计数；
尚未到期输出 `NOT_DUE`；漏槽、时钟、来源、发布或 state 错误返回非零。

## 7. 验收

- NOT_DUE 与 MISSED_SLOT 都产生 3 个 time 请求、0 个 Kline 请求；
- due 路径产生 3+1 请求并写入一条 decision；
- 同槽再次运行是 NOT_DUE，Kline 请求 0；
- 下一槽重叠 20 根完全沿用原 availability；
- Kline 修订、gap、未闭合、bad URL/status/body/clock 全部失败；
- bundle 自哈希、Schema、raw replay、decision binding 和 mirror 通过；
- CLI 暴露零 URL/time/symbol/credential/order 覆盖；
- fixture 100 次输出一致；
- 全量验证、提交、合并并标记 `v0.31.0`。
