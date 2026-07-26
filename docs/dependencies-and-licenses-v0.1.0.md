# 依赖与许可证清单 v0.1.0

状态：Phase 0已锁定
复核日期：2026-07-26

本清单对应`requirements.lock`。许可证判断来自本地已安装发行包自带的LICENSE/COPYING文件；升级版本、改变来源或增加extra时必须重新复核。它不是法律意见。

| 包 | 锁定版本 | 用途 | 许可证文件结论 |
|---|---:|---|---|
| jsonschema | 4.25.1 | Draft 2020-12 Schema验证 | MIT文本 |
| attrs | 26.1.0 | jsonschema传递依赖 | MIT |
| jsonschema-specifications | 2025.9.1 | JSON Schema规范资源 | MIT文本 |
| referencing | 0.36.2 | Schema引用解析 | MIT文本 |
| rpds-py | 0.27.1 | referencing持久化数据结构 | MIT文本 |
| typing-extensions | 4.16.0 | Python版本兼容类型 | PSF-2.0 |

## 准入约束

- V1运行时代码除Python标准库外，只批准上述Schema验证依赖。
- 不引入交易机器人、模型框架或交易所SDK代码；后续Adapter必须单独ADR和许可证审查。
- CI先安装`requirements.lock`，再以`--no-deps`安装本项目，避免隐式漂移。
- 依赖锁变化必须更新本文件、运行全部测试并产生新Git提交。
- 本仓库当前未授予对外复制或分发许可证；第三方依赖仍各自遵循其许可证。
