# 实施追踪 v0.63.0

日期：2026-08-05

状态：NautilusTrader 隔离 Spike 的依赖/合同/失败证据已冻结；官方 frozen environment 获取阻断，
结论为 `INCONCLUSIVE_BLOCKED`，不采用、不安装、不接管

## 本版本已完成

- 独立 `sandboxes/nautilus` Python 3.12 package identity 与完整 `uv.lock`；根包仍为 Python 3.9+，
  根依赖没有 Nautilus；
- exact `nautilus_trader==1.227.0` tag/commit/wheel/size/SHA-256、Requires-Python、LGPL expression、
  license blob/size/SHA-256 和所有 locked distribution artifact hashes；
- ETHUSDT Spot 4H fixed fixture、tick/step/min-notional、费用、四个预注册场景以及当前核心的
  Decision/Target/Risk fact source；
- one-way request/result Schema、严格 owner-only canonical loaders 和不允许 live adapter、credential、
  runtime network、Broker、real order 或 production state write 的合同；
- read-only Evidence Adapter、comparison Schema 和 `SUPPLY_CHAIN_FETCH_BLOCKED` exact failure evidence；
- dependency/contract/adapter/artifact failure tests，包含 hash、平台、权限、symlink、unknown field、
  authority/counter、failure tamper 和 synthetic-result 拒绝；
- exact artifacts：
  - dependency lock：17,997 bytes，SHA-256 `ed0342ea4274026b6d936b5489f215eb44b4ae5e8ba651b69f3ed01db09230ee`；
  - current reference：1,510 bytes，SHA-256 `ecd7acd19a94cf623c651d33a656f3e002ddaee04907688504b0120116dddc1e`；
  - request：4,437 bytes，SHA-256 `25a54dbb6429ea74ab073e5d6f9a075e09e51077b03422c1250d4adebdee42a5`；
  - comparison/report：2,303 bytes，SHA-256 `2e7c195f0d1c66c306cef696a048c497d0ca1d563a065fb67fab68b7d41fd7f4`。

## 真实失败与关闭动作

第一次 `uv sync --frozen` 在官方 `files.pythonhosted.org` 下载 `numpy==2.5.1` 时，127.6 秒内五次
重试全部超时并退出 1。第二次只对同一 official source、同一 version/hash 延长读取超时；约 13 分钟
仍未形成可用环境后有界终止，退出 130。source/version/hash relaxation 计数为 0。

因此：sandbox runner invocation、BacktestEngine creation、market request、credential access、Broker、
real order、production state write 和 result publish 全部为 0。仓库故意不存在
`nautilus-sandbox-result-v0.63.0.json` 和 sidecar `runner.py`，防止把未经真实引擎执行的模拟输出伪装成
兼容性证据。Golden、部分成交、拒绝、费用、持仓、PnL 和 fresh-process replay 均未执行、未通过。

## 对现有项目的影响

System Paper、replacement Challenger、旧 Challenger failure/decommission、v0.59 evaluator、production
services/roots/plists/state/logs 与所有 90 天事实源未修改。没有迁移、回填、重置、改起点、更换事实源、
安装、bootstrap、kickstart、Runner、scheduler 或 maintenance。

本版本的唯一采用状态是 `INCONCLUSIVE_BLOCKED / NONE_KEEP_CURRENT_CORE`。它不证明 Nautilus 不适合，
也不证明当前自研执行更好；它仅禁止在证据不足时接入下一阶段。未来若重评，必须另开版本和预注册
计划，v0.63 exact failure 不得覆盖。

本版本不能声称策略赚钱、AI 优势、Paper 已开始或完成、Shadow、Canary 或实盘资格；
`production_activation.enabled=false` 继续生效。
