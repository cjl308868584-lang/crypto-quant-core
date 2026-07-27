# 实施追踪 v0.32.0

日期：2026-07-28

状态：真实 LaunchAgent 合同已生成；未安装、未加载、未运行

## 本版本完成

- 新增 challenger 专用 macOS LaunchAgent plist 与合同构建器；
- 固定 Asia/Shanghai、UTC+08:00、DST=0 时区校验；
- 固定本地 0/4/8/12/16/20 点02分和 RunAtLoad；
- 固定 Runner module、state/output 路径与 `PYTHONPATH`；
- 禁止 credential、shell、任意命令、URL、symbol、clock 与订单参数；
- 新增严格 Schema、自哈希、plist SHA-256 和 semantic replay；
- owner-only 创建 runtime/state/log/artifacts 与合同发布目录；
- 新增只渲染不安装的 CLI，代码不调用 `launchctl`。

## 真实本机合同

合同已生成到仓库外：

```text
/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1
```

- contract id：
  `challenger_launchd_contract_c13bc8c0c86845d929623c4c9b74127458a5f44086656edd93d2de488323a920`；
- contract hash：
  `ac1d58ebe5d7b99bdebe7f33dd674d7c60099c52068ea096314608ebc1ce0fe7`；
- local contract trust hash：
  `1a35cd9d3bfe763a41161da090ffc2fdf33a320bb8850b05440dfe8e94c6146d`；
- plist SHA-256：
  `a86f69f87e767198a9582ad27c44e850a092e8589bf42b7a05e1e22fdab19cfb`；
- runtime 目录：0700；
- contract/plist：0600；
- 安装状态：`NOT_INSTALLED_NO_EXTERNAL_RECEIPT`。

完整紧凑证据见
[challenger-launchd-not-installed-v0.32.0.json](../artifacts/challenger-forward/challenger-launchd-not-installed-v0.32.0.json)。

## 真实执行状态

- `launchctl` 调用：0；
- 用户 LaunchAgents 复制：否；
- bootstrap/load：否；
- server-time/Kline 请求：0；
- decision：0；
- Broker/order：0。

这意味着合同存在，但不能声称后台任务已安装或系统已经开始收集 forward。

## 验证

- v0.32 focused tests：9/9；
- 同一输入 100 次合同/plist exact match；
- 默认微秒 wall clock 正确规范化为毫秒；
- 时区、路径、权限、幂等、冲突和协调篡改失败关闭；
- Schema 与 package mirror exact；
- 全量 tests：519/519；
- Golden Vector：41；
- Evaluator build input：151；
- Build input tree hash：
  `39b674d11cc7ad98c203f146e7a6cbf93a5cda09f03e8bf9ab084bf8fc9086ef`；
- Evaluator build hash：
  `3b215339573a219ec1250b64a6c934520ef8246e57ad2893e79c8cbbb1560359`；
- `make validate` 完整执行成功；政策结果继续按设计为 `FAIL`。

## 下一步

安装前需要再次核对目标 plist hash、runtime 路径和 Python 依赖。安装、bootstrap、
launchctl print 与首次 RunAtLoad 必须分别形成 receipt；如果首槽错过，Runner
会失败且不允许回填。
