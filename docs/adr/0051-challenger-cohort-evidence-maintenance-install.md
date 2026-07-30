# ADR-0051：Challenger Cohort 证据维护私有快照与受限安装

日期：2026-07-31

状态：已接受

## 背景

v0.50 的维护 LaunchAgent 合同仍指向开发工作树，并明确没有安装。直接复制该
plist 会重复 v0.33 已证明的后台导入风险，也会让自哈希合同在没有独立信任根时
自证可信。

## 决策

1. 维护调度使用独立 deployment 与 installer，不修改策略 Runner installer。
2. execution snapshot 只包含 package、pyproject 和两个固定计划，逐文件
   SHA-256 后发布到 owner-only content-addressed 目录。
3. 用 snapshot 重新渲染 candidate；candidate trust hash 先进入独立 Git 提交
   `12dafda`，installer 再显式接受该 hash。
4. installer 目标、uid/domain、label 和命令全部固定，只允许
   `print → bootstrap → print`。
5. `RunAtLoad=false`；安装不能运行维护入口。首次自然 08:10 必须单独取证。
6. deployment manifest 与 install receipt 均由 production loader 重做合同、
   快照、target stat、command evidence 和外部 trust 验证。
7. 第一次默认时钟微秒精度失败的 snapshot 保留；没有删除或伪造成候选。

## 真实结果

- snapshot：129 文件、2,351,237 bytes；
- tree hash：
  `8ae7cfac351c56a3666c33b18748d67e67ae82be3298caf8eb64de0a9d8e5904`；
- candidate trust：
  `9f7d6b7e2beb8103fb8cf1da1281d086a243bc63f3c5cc7992a8d4c0b878b83f`；
- installed plist SHA-256：
  `efd7070b185a7e6eca629f93502894b0c1def6a0277b9bb87c6a0c5c87a9d4e3`；
- receipt hash：
  `ad39cc029d73c03656b20de7fa146d9acd3f963a5f9ef9f0eb6bb3417f1eff1b`；
- `launchctl` 固定三次，安装后 `runs=0`、`state=not running`；
- 安装前后策略 state/stdout/stderr 哈希不变；
- maintenance 日志和 cohort receipt/archive/result 根均未由安装创建。

## 后果

每天 08:10 的维护调度已经安装并加载，但尚未证明首次自然运行。后续版本只能观察
自然槽，禁止 kickstart、补跑或手工调用维护入口。即使首次运行成功，也只证明证据
维护自动化；完整 cohort 和 v0.48 固定尾部累计门仍决定研究资格，安装本身不证明
盈利、Paper 或 AI 优势。
