# 本机只读运维控制台手册

版本：v0.61.0  
作用：显示 strict v0.60 operations projection；不控制任何运行组件

## 1. 安全边界

控制台只绑定 `127.0.0.1`，只提供：

```text
GET /
GET /app.js
GET /styles.css
GET /api/v1/status
```

它不读取 SQLite、日志、LaunchAgent、receipt 或环境变量，不调用 Runner、scheduler、
maintenance、Broker 或交易所，不写文件，不发送告警，不轮询，不提供操作按钮。停止控制台
不会影响 Challenger 或 System Paper 的状态与证据。

禁止改为 `localhost`、`::1`、`0.0.0.0` 或外部 IP；禁止端口转发、反向代理、隧道、容器
端口发布、云托管、CORS、认证材料、cookie、WebSocket 或远程静态资源。

## 2. 发布身份检查

从 v0.61.0 release worktree 执行：

```bash
git status --short
git rev-parse HEAD
git rev-parse 'refs/tags/v0.61.0^{}'
git rev-parse origin/main
```

第一条必须为空；后三条必须是同一个 40 位 commit。若 annotated tag 尚未发布、任意 identity
不同或工作树不干净，不把该 checkout 当作生产观察工具。

## 3. Projection 严格重放

本版本提交的健康 fixture 位于：

`/Users/chenm4/Documents/虚拟货币/.worktrees/v0.61-read-only-operations-console/tests/fixtures/operations-projection-healthy.json`

fixture SHA-256 固定为：

`bb1aec23580a2f18a723f33be86de3720a7b5a69342d5fbb82bc13a51707f0ba`

在启动演示前只读检查：

```bash
shasum -a 256 '/Users/chenm4/Documents/虚拟货币/.worktrees/v0.61-read-only-operations-console/tests/fixtures/operations-projection-healthy.json'
cd '/Users/chenm4/Documents/虚拟货币/.worktrees/v0.61-read-only-operations-console'
PYTHONPATH=src /usr/bin/python3 -c "from pathlib import Path; from crypto_quant.operations_projection import load_operations_projection_bytes; p=Path('/Users/chenm4/Documents/虚拟货币/.worktrees/v0.61-read-only-operations-console/tests/fixtures/operations-projection-healthy.json'); print(load_operations_projection_bytes(p.read_bytes())['projection_hash'])"
```

未来真实 projection 必须由冻结 production loaders 生成并以 canonical exact bytes提供；不能
手工编辑、补字段、去除告警、复制旧日期或把 receipt/SQLite 原文直接交给控制台。

## 4. 启动与健康检查

演示 fixture 的本地启动命令：

```bash
cd '/Users/chenm4/Documents/虚拟货币/.worktrees/v0.61-read-only-operations-console'
PYTHONPATH=src /usr/bin/python3 -m crypto_quant.operations_dashboard --projection-file '/Users/chenm4/Documents/虚拟货币/.worktrees/v0.61-read-only-operations-console/tests/fixtures/operations-projection-healthy.json' --port 8765
```

CLI 没有 `--host` 参数，不能选择外部接口。另一个终端只读检查：

```bash
curl --noproxy '*' --silent --show-error --fail http://127.0.0.1:8765/api/v1/status
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

`curl` 必须返回 canonical JSON；`lsof` 的监听地址必须是且只能是 `127.0.0.1:8765`。浏览器
只访问 `http://127.0.0.1:8765/`。不要使用 `localhost`。

## 5. 状态解释

- `HEALTHY`：allowlisted 来源、新鲜度、状态机和身份内部一致；不证明收益。
- `DEGRADED`：存在 stale、incident、service degradation 或风险警告；查看告警 reason code，
  不通过 UI 修复。
- `FAILED_CLOSED`：来源、服务、证据、对账或总体边界失败；`new_risk_allowed=false`。
- HTTP 503 与 `OPERATIONS_STATUS_UNAVAILABLE`：provider、canonical bytes、Schema、hash 或语义
  replay失败。响应故意不包含异常和路径。

Challenger 告警与 System Paper 风险观察保持独立；Challenger-only warning 不会伪造 Paper
失败。总体 `FAILED_CLOSED` 会关闭 Paper 的只读风险观察。任何 `new_risk_allowed=true` 仅表示
当前模拟 Paper allowlisted 状态未观察到冻结阻断条件，不授权安装、启动、Canary 或真实订单。

## 6. Projection 更新

CLI 每次状态请求重新读取同一个显式文件，并重新执行严格 loader。替换真实 projection 的
发布者必须先在控制台之外完成 atomic exact-byte 证据发布；控制台没有发布权限。文件瞬时
缺失、被截断、非 canonical 或 hash 不匹配时，API 返回固定 503，不缓存旧的健康结果。

不得为消除 503 而编辑 projection、删除换行、重算 hash、回退旧文件或改控制台代码。保存
原始 bytes/stat/SHA-256 与 reason code，按 System Paper 运维手册进入事故取证。

## 7. 关闭

在前台进程按一次 `Ctrl-C`。随后确认端口已释放：

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

预期没有输出。控制台不安装 LaunchAgent、不写 PID 文件、不创建运行根，因此不需要 bootout、
kickstart、清理 state 或补跑任何槽位。
