# 虚拟货币量化策略系统

这是一个以“扣除全部成本后获得可重复的实盘收益”为目标的个人加密货币量化项目。

项目当前处于设计基线阶段。任何回测收益、模型准确率或论文结果都不构成实盘盈利承诺；系统首先要证明数据、验证、执行和风险闭环可信，然后才允许逐级使用真实资金。

## 当前权威文档

1. [系统计划 v1.1](docs/system-plan-v1.1.md)
2. [核心数据契约与订单状态机 v1.1](docs/contracts-and-state-machines-v1.1.md)
3. [AI 研究与模型治理 v1.1](docs/ai-research-governance-v1.1.md)
4. [开发路线与验收门槛 v1.1](docs/delivery-roadmap-v1.1.md)
5. [发布评估与证据规范 v1.1](docs/release-evaluation-spec-v1.1.md)
6. [开源项目参考与取舍 v1.1](docs/open-source-reference-notes-v1.1.md)
7. [机器可读发布门槛 v1.1](config/release-gates-v1.1.json)
8. [指标目录 v1.1](config/release-metrics-v1.1.json)
9. [政策 Schema](config/release-gates-v1.1.schema.json)
10. [指标 Schema](config/release-metrics-v1.1.schema.json)
11. [证据 Schema](config/release-evidence-v1.1.schema.json)
12. [RecipeRelease Schema](config/recipe-release-v1.1.schema.json)
13. [ModelBundle Schema](config/model-bundle-v1.1.schema.json)
14. [Approved Fallback Registry Schema](config/approved-fallback-registry-v1.1.schema.json)
15. [治理Artifact模板Schema](config/governance-artifact-v1.schema.json)
16. [未审批治理模板目录](config/templates/)
17. [Estimator Registry](config/estimator-registry-v1.json)
18. [Estimator Registry Schema](config/estimator-registry-v1.schema.json)
19. [Estimator Golden Vectors](config/estimator-golden-vectors-v1.json)
20. [Estimator Golden Vector Schema](config/estimator-golden-vectors-v1.schema.json)
21. [Evaluator Build Manifest](config/evaluator-build-manifest-v1.json)
22. [Evaluator Build Manifest Schema](config/evaluator-build-manifest-v1.schema.json)
23. [ExperimentManifest Schema](config/experiment-manifest-v1.1.schema.json)
24. [DeploymentLine Schema](config/deployment-line-v1.1.schema.json)
25. [Supporting Observation Bundle Schema](config/supporting-observation-bundle-v1.schema.json)
26. [Economic Ledger Snapshot Schema](config/economic-ledger-snapshot-v1.schema.json)
27. [Statistical Series Snapshot Schema](config/statistical-series-snapshot-v1.schema.json)
28. [Endpoint Reevaluation Snapshot Schema](config/endpoint-reevaluation-snapshot-v1.schema.json)
29. [Trade Replay Snapshot Schema](config/trade-replay-snapshot-v1.schema.json)
30. [Statistical Decision Snapshot Schema](config/statistical-decision-snapshot-v1.schema.json)
31. [ADR-0014：可重放的统计决策证据](docs/adr/0014-replayable-statistical-decision-evidence.md)
32. [实施追踪 v0.14.0](docs/implementation-status-v0.14.0.md)
33. [配对风险效率决策 ADR-0015](docs/adr/0015-paired-risk-efficiency-bootstrap.md)
34. [实施追踪 v0.15.0](docs/implementation-status-v0.15.0.md)
35. [Historical Market Data Snapshot Schema](config/historical-market-data-snapshot-v1.schema.json)
36. [Fee Schedule Snapshot Schema](config/fee-schedule-snapshot-v1.schema.json)
37. [官方历史数据来源决策 ADR-0016](docs/adr/0016-public-historical-data-provenance.md)
38. [Binance 官方归档 Smoke Evidence v0.16.0](artifacts/market-data/binance-public-data-smoke-v0.16.0.json)
39. [实施追踪 v0.16.0](docs/implementation-status-v0.16.0.md)
40. [Contemporaneous Capture Snapshot Schema](config/contemporaneous-capture-snapshot-v1.schema.json)
41. [同时公开行情捕获决策 ADR-0017](docs/adr/0017-contemporaneous-public-capture.md)
42. [Binance 同时捕获 Smoke Evidence v0.17.0](artifacts/market-data/binance-contemporaneous-smoke-v0.17.0.json)
43. [实施追踪 v0.17.0](docs/implementation-status-v0.17.0.md)
44. [Offline Paper Run Schema](config/offline-paper-run-v1.schema.json)
45. [公开输入离线 Paper 决策 ADR-0018](docs/adr/0018-public-offline-paper-replay.md)
46. [Binance 离线 Paper Smoke Evidence v0.18.0](artifacts/paper/binance-offline-paper-smoke-v0.18.0.json)
47. [实施追踪 v0.18.0](docs/implementation-status-v0.18.0.md)
48. [Paper Schedule Snapshot Schema](config/paper-schedule-snapshot-v1.schema.json)
49. [长期 Paper 调度决策 ADR-0019](docs/adr/0019-durable-longitudinal-paper-scheduler.md)
50. [Binance 调度 Cycle Evidence v0.19.0](artifacts/paper/paper-slot-ethusdt_20260727t120000z.json)
51. [Binance 调度状态 Evidence v0.19.0](artifacts/paper/paper-schedule-ethusdt_20260727t120000z.json)
52. [实施追踪 v0.19.0](docs/implementation-status-v0.19.0.md)
53. [Paper Runtime Snapshot Schema](config/paper-runtime-snapshot-v1.schema.json)
54. [Server Time Probe Schema](config/server-time-probe-v1.schema.json)
55. [时钟健康门决策 ADR-0020](docs/adr/0020-server-time-runtime-health.md)
56. [Binance Runtime Smoke Evidence v0.20.0](artifacts/runtime/v0.20-smoke/)
57. [实施追踪 v0.20.0](docs/implementation-status-v0.20.0.md)
58. [Perpetual Context Snapshot Schema](config/perpetual-context-snapshot-v1.schema.json)
59. [当前永续上下文决策 ADR-0021](docs/adr/0021-current-perpetual-context.md)
60. [Binance Futures 直连失败证据 v0.21.0](artifacts/market-data/binance-perpetual-context-smoke-failure-v0.21.0.json)
61. [实施追踪 v0.21.0](docs/implementation-status-v0.21.0.md)
62. [Account Commission Snapshot Schema](config/account-commission-snapshot-v1.schema.json)
63. [只读账户费率证据决策 ADR-0022](docs/adr/0022-read-only-account-commission-evidence.md)
64. [Binance 账户费率未运行证据 v0.22.0](artifacts/account-cost/binance-account-commission-smoke-not-run-v0.22.0.json)
65. [实施追踪 v0.22.0](docs/implementation-status-v0.22.0.md)
66. [Paper Account Cost Binding Schema](config/paper-account-cost-binding-v1.schema.json)
67. [PIT Paper 账户成本绑定决策 ADR-0023](docs/adr/0023-pit-paper-account-cost-binding.md)
68. [Paper 账户成本绑定未运行证据 v0.23.0](artifacts/paper-cost/binance-paper-account-cost-binding-not-run-v0.23.0.json)
69. [实施追踪 v0.23.0](docs/implementation-status-v0.23.0.md)
70. [Paper Cycle Context Bundle Schema](config/paper-cycle-context-bundle-v1.schema.json)
71. [Paper Context Schedule Schema](config/paper-context-schedule-snapshot-v1.schema.json)
72. [上下文完整 Paper 侧车决策 ADR-0024](docs/adr/0024-context-complete-paper-sidecar.md)
73. [Context-complete Cycle 未运行证据 v0.24.0](artifacts/paper-context/binance-context-complete-cycle-not-run-v0.24.0.json)
74. [实施追踪 v0.24.0](docs/implementation-status-v0.24.0.md)
75. [Context Cycle Orchestration Snapshot Schema](config/context-cycle-orchestration-snapshot-v1.schema.json)
76. [Local Scheduler Contract Schema](config/local-scheduler-contract-v1.schema.json)
77. [可恢复完整周期编排决策 ADR-0025](docs/adr/0025-recoverable-context-cycle-orchestration.md)
78. [完整周期编排未运行证据 v0.25.0](artifacts/orchestration/context-cycle-orchestration-not-run-v0.25.0.json)
79. [实施追踪 v0.25.0](docs/implementation-status-v0.25.0.md)
80. [Historical Research Corpus Plan Schema](config/historical-research-corpus-plan-v1.schema.json)
81. [Historical Research Corpus Snapshot Schema](config/historical-research-corpus-snapshot-v1.schema.json)
82. [可恢复历史研究语料决策 ADR-0026](docs/adr/0026-recoverable-historical-research-corpus.md)
83. [Binance 月度 Corpus Smoke Evidence v0.26.0](artifacts/research-corpus/binance-monthly-corpus-smoke-v0.26.0.json)
84. [实施追踪 v0.26.0](docs/implementation-status-v0.26.0.md)
85. [Historical Research Corpus Repair Schema](config/historical-research-corpus-repair-v1.schema.json)
86. [完整语料与显式日档修复 ADR-0027](docs/adr/0027-complete-research-corpus-with-explicit-daily-repairs.md)
87. [Binance 完整 Corpus Evidence v0.27.0](artifacts/research-corpus/binance-research-corpus-completion-v0.27.0.json)
88. [实施追踪 v0.27.0](docs/implementation-status-v0.27.0.md)
89. [Historical Execution Source Schema](config/historical-execution-source-v1.schema.json)
90. [Causal Feature/Label Dataset Schema](config/causal-feature-label-dataset-v1.schema.json)
91. [Logistic Archive Research Schema](config/logistic-archive-research-v1.schema.json)
92. [因果标签与 Logistic 档案研究 ADR-0028](docs/adr/0028-causal-logistic-archive-research.md)
93. [Binance 因果 Logistic 研究证据 v0.28.0](artifacts/ai-research/binance-causal-logistic-research-v0.28.0.json)
94. [实施追踪 v0.28.0](docs/implementation-status-v0.28.0.md)
95. [Baseline Failure Attribution Schema](config/baseline-failure-attribution-v1.schema.json)
96. [基线失败归因与仅前向 Challenger ADR-0029](docs/adr/0029-baseline-failure-attribution-and-forward-only-challenger.md)
97. [Binance 基线失败归因证据 v0.29.0](artifacts/baseline-research/binance-baseline-failure-attribution-v0.29.0.json)
98. [实施追踪 v0.29.0](docs/implementation-status-v0.29.0.md)
99. [Challenger Prequential Snapshot Schema](config/challenger-prequential-snapshot-v1.schema.json)
100. [Challenger 事件流与前向记录器 ADR-0030](docs/adr/0030-challenger-forward-event-stream-recorder.md)
101. [Challenger Forward 未运行证据 v0.30.0](artifacts/challenger-forward/binance-challenger-forward-not-run-v0.30.0.json)
102. [实施追踪 v0.30.0](docs/implementation-status-v0.30.0.md)
103. [Challenger Forward Source Bundle Schema](config/challenger-forward-source-bundle-v1.schema.json)
104. [Challenger 实时只读 Runner ADR-0031](docs/adr/0031-challenger-public-live-runner.md)
105. [Challenger Live Runner 未运行证据 v0.31.0](artifacts/challenger-forward/binance-challenger-live-runner-not-run-v0.31.0.json)
106. [实施追踪 v0.31.0](docs/implementation-status-v0.31.0.md)
107. [Challenger Launchd Contract Schema](config/challenger-launchd-contract-v1.schema.json)
108. [Challenger LaunchAgent 合同 ADR-0032](docs/adr/0032-challenger-launchagent-contract.md)
109. [Challenger LaunchAgent 未安装证据 v0.32.0](artifacts/challenger-forward/challenger-launchd-not-installed-v0.32.0.json)
110. [实施追踪 v0.32.0](docs/implementation-status-v0.32.0.md)
111. [Challenger LaunchAgent Install Receipt Schema](config/challenger-launchd-install-receipt-v1.schema.json)
112. [Challenger LaunchAgent 安装与私有快照 ADR-0033](docs/adr/0033-challenger-launchagent-install-and-private-snapshot.md)
113. [Challenger LaunchAgent 已安装证据 v0.33.0](artifacts/challenger-forward/challenger-launchd-installed-v0.33.0.json)
114. [实施追踪 v0.33.0](docs/implementation-status-v0.33.0.md)
115. [Challenger First Slot Receipt Schema](config/challenger-first-slot-receipt-v1.schema.json)
116. [Challenger 首槽只读观察 ADR-0034](docs/adr/0034-challenger-first-slot-read-only-receipt.md)
117. [Challenger 首槽前等待证据 v0.34.0](artifacts/challenger-forward/challenger-first-slot-waiting-v0.34.0.json)
118. [实施追踪 v0.34.0](docs/implementation-status-v0.34.0.md)
119. [Challenger 首槽真实前向证据 ADR-0035](docs/adr/0035-challenger-first-slot-real-forward-evidence.md)
120. [Challenger 首槽真实 Receipt v0.35.0](artifacts/challenger-forward/challenger-first-slot-receipt-v0.35.0.json)
121. [实施追踪 v0.35.0](docs/implementation-status-v0.35.0.md)
122. [Challenger First Episode Receipt Schema](config/challenger-first-episode-receipt-v1.schema.json)
123. [Challenger 首个 Episode 只读观察 ADR-0036](docs/adr/0036-challenger-first-episode-read-only-observer.md)
124. [Challenger 首个 Episode 进行中证据 v0.36.0](artifacts/challenger-forward/challenger-first-episode-in-progress-v0.36.0.json)
125. [实施追踪 v0.36.0](docs/implementation-status-v0.36.0.md)
126. [Challenger Episode Economic Plan Schema](config/challenger-episode-economic-plan-v1.schema.json)
127. [Challenger Episode 经济测量计划 ADR-0037](docs/adr/0037-challenger-episode-economic-measurement-plan.md)
128. [Challenger Episode 经济计划 v0.37.0](artifacts/challenger-forward/challenger-episode-economic-plan-v0.37.0.json)
129. [实施追踪 v0.37.0](docs/implementation-status-v0.37.0.md)
130. [Challenger Episode Economic Result Schema](config/challenger-episode-economic-result-v1.schema.json)
131. [Challenger Episode 经济评估器 ADR-0038](docs/adr/0038-challenger-episode-economic-evaluator.md)
132. [实施追踪 v0.38.0](docs/implementation-status-v0.38.0.md)
133. [Challenger Episode Archive Receipt Schema](config/challenger-episode-archive-receipt-v1.schema.json)
134. [Challenger Episode 官方日档采集 ADR-0039](docs/adr/0039-challenger-episode-archive-acquisition.md)
135. [实施追踪 v0.39.0](docs/implementation-status-v0.39.0.md)
136. [Challenger Episode 经济结果 CLI ADR-0040](docs/adr/0040-challenger-episode-economic-result-cli.md)
137. [实施追踪 v0.40.0](docs/implementation-status-v0.40.0.md)
138. [Challenger 首个 Episode 完成证据 ADR-0041](docs/adr/0041-challenger-first-episode-completion-evidence.md)
139. [Challenger 首个 Episode 完成 Receipt v0.41.0](artifacts/challenger-forward/challenger-first-episode-receipt-v0.41.0.json)
140. [实施追踪 v0.41.0](docs/implementation-status-v0.41.0.md)
141. [Challenger 首个 Episode 经济结果 ADR-0042](docs/adr/0042-challenger-first-episode-economic-result.md)
142. [Challenger 首个 Episode 经济结果 v0.42.0](artifacts/challenger-forward/challenger-episode-economic-result-v0.42.0.json)
143. [实施追踪 v0.42.0](docs/implementation-status-v0.42.0.md)
144. [Challenger Episode Cohort Plan Schema](config/challenger-episode-cohort-plan-v1.schema.json)
145. [Challenger 多 Episode 前瞻队列 ADR-0043](docs/adr/0043-challenger-episode-confirmatory-cohort.md)
146. [Challenger Episode Cohort Plan v0.43.0](artifacts/challenger-forward/challenger-episode-cohort-plan-v0.43.0.json)
147. [实施追踪 v0.43.0](docs/implementation-status-v0.43.0.md)
148. [Challenger Cohort Evaluation Plan Schema](config/challenger-cohort-evaluation-plan-v1.schema.json)
149. [Challenger Cohort 累计评估 ADR-0044](docs/adr/0044-challenger-cohort-cumulative-evaluation-plan.md)
150. [Challenger Cohort Evaluation Plan v0.44.0](artifacts/challenger-forward/challenger-cohort-evaluation-plan-v0.44.0.json)
151. [实施追踪 v0.44.0](docs/implementation-status-v0.44.0.md)
152. [Challenger Cohort Episode Receipt Schema](config/challenger-cohort-episode-receipt-v1.schema.json)
153. [Challenger Cohort 全量 Episode Receipt ADR-0045](docs/adr/0045-challenger-cohort-episode-receipts.md)
154. [实施追踪 v0.45.0](docs/implementation-status-v0.45.0.md)
155. [Challenger Cohort Shared Daily Archive Receipt Schema](config/challenger-cohort-daily-archive-receipt-v1.schema.json)
156. [Challenger Cohort 共享 UTC 日档 ADR-0046](docs/adr/0046-challenger-cohort-shared-daily-archives.md)
157. [实施追踪 v0.46.0](docs/implementation-status-v0.46.0.md)
158. [Challenger Cohort Episode Economic Result Schema](config/challenger-cohort-episode-economic-result-v1.schema.json)
159. [Challenger Cohort Economic Result Index Schema](config/challenger-cohort-economic-result-index-v1.schema.json)
160. [Challenger Cohort 全纳入经济结果 ADR-0047](docs/adr/0047-challenger-cohort-economic-results.md)
161. [实施追踪 v0.47.0](docs/implementation-status-v0.47.0.md)
162. [Challenger Cohort 固定尾部累计评估 Schema](config/challenger-cohort-cumulative-evaluation-v1.schema.json)
163. [Challenger Cohort 固定尾部累计评估 ADR-0048](docs/adr/0048-challenger-cohort-fixed-tail-cumulative-evaluation.md)
164. [实施追踪 v0.48.0](docs/implementation-status-v0.48.0.md)
165. [Challenger Cohort 证据维护 ADR-0049](docs/adr/0049-challenger-cohort-evidence-maintenance.md)
166. [实施追踪 v0.49.0](docs/implementation-status-v0.49.0.md)
167. [Challenger Cohort 证据维护 LaunchAgent Contract Schema](config/challenger-cohort-evidence-maintenance-launchd-contract-v1.schema.json)
168. [Challenger Cohort 证据维护调度 ADR-0050](docs/adr/0050-challenger-cohort-evidence-maintenance-launchd-contract.md)
169. [Challenger Cohort 证据维护未安装证据 v0.50.0](artifacts/challenger-forward/challenger-cohort-evidence-maintenance-launchd-not-installed-v0.50.0.json)
170. [实施追踪 v0.50.0](docs/implementation-status-v0.50.0.md)
171. [Challenger Cohort 维护 Deployment Manifest Schema](config/challenger-cohort-evidence-maintenance-deployment-manifest-v1.schema.json)
172. [Challenger Cohort 维护安装 Receipt Schema](config/challenger-cohort-evidence-maintenance-launchd-install-receipt-v1.schema.json)
173. [Challenger Cohort 维护安装 ADR-0051](docs/adr/0051-challenger-cohort-evidence-maintenance-install.md)
174. [Challenger Cohort 维护安装候选 v0.51.0](artifacts/challenger-forward/challenger-cohort-evidence-maintenance-install-candidate-v0.51.0.json)
175. [Challenger Cohort 维护安装证据 v0.51.0](artifacts/challenger-forward/challenger-cohort-evidence-maintenance-installed-v0.51.0.json)
176. [实施追踪 v0.51.0](docs/implementation-status-v0.51.0.md)
177. [Challenger Cohort 维护首次自然运行 Receipt Schema](config/challenger-cohort-evidence-maintenance-first-run-receipt-v1.schema.json)
178. [Challenger Cohort 维护首次自然运行观察 ADR-0052](docs/adr/0052-challenger-cohort-evidence-maintenance-first-run-observer.md)
179. [Challenger Cohort 维护首槽前等待证据 v0.52.0](artifacts/challenger-forward/challenger-cohort-evidence-maintenance-first-run-waiting-v0.52.0.json)
180. [实施追踪 v0.52.0](docs/implementation-status-v0.52.0.md)
181. [Challenger Cohort 维护首次自然运行证据 v0.53.0](artifacts/challenger-forward/challenger-cohort-evidence-maintenance-first-run-receipt-v0.53.0.json)
182. [Challenger Cohort 维护首次自然运行证据发布 ADR-0053](docs/adr/0053-challenger-cohort-evidence-maintenance-first-run-release.md)
183. [实施追踪 v0.53.0](docs/implementation-status-v0.53.0.md)
184. [Challenger Cohort 漏槽失败 Receipt Schema](config/challenger-cohort-failure-receipt-v1.schema.json)
185. [Challenger Cohort 停用 Receipt Schema](config/challenger-cohort-decommission-receipt-v1.schema.json)
186. [Challenger Cohort 漏槽失败证据 v0.54.0](artifacts/challenger-forward/challenger-cohort-missed-slot-failure-receipt-v0.54.0.json)
187. [Challenger Cohort 受控停用证据 v0.54.0](artifacts/challenger-forward/challenger-cohort-decommission-receipt-v0.54.0.json)
188. [Challenger Cohort 漏槽失败与受控停用 ADR-0054](docs/adr/0054-challenger-cohort-missed-slot-failure-evidence.md)
189. [实施追踪 v0.54.0](docs/implementation-status-v0.54.0.md)
190. [System Paper Plan Schema](config/system-paper-plan-v1.schema.json)
191. [System Paper 冻结计划 v0.55.0](artifacts/system-paper/system-paper-plan-v0.55.0.json)
192. [System Paper 计划冻结 ADR-0055](docs/adr/0055-system-paper-plan-freeze.md)
193. [实施追踪 v0.55.0](docs/implementation-status-v0.55.0.md)
194. [System Paper Slot Result Schema](config/system-paper-slot-result-v1.schema.json)
195. [System Paper 确定性单槽运行时 ADR-0056](docs/adr/0056-system-paper-deterministic-runtime.md)
196. [实施追踪 v0.56.0](docs/implementation-status-v0.56.0.md)
197. [System Paper 独立 WAL 调度器 ADR-0057](docs/adr/0057-system-paper-wal-scheduler.md)
198. [实施追踪 v0.57.0](docs/implementation-status-v0.57.0.md)
199. [System Paper deployment trust chain ADR-0058](docs/adr/0058-system-paper-deployment-trust-chain.md)
200. [实施追踪 v0.58.0](docs/implementation-status-v0.58.0.md)
201. [System Paper 固定尾部评估 Schema](config/system-paper-evaluation-v1.schema.json)
202. [System Paper 固定尾部评估 ADR-0059](docs/adr/0059-system-paper-fixed-tail-evaluation.md)
203. [实施追踪 v0.59.0](docs/implementation-status-v0.59.0.md)
204. [Tail-Blind 运维投影 Schema](config/operations-projection-v1.schema.json)
205. [Tail-Blind 运维投影 ADR-0060](docs/adr/0060-tail-blind-operations-projection.md)
206. [实施追踪 v0.60.0](docs/implementation-status-v0.60.0.md)
207. [本机只读运维控制台 ADR-0061](docs/adr/0061-loopback-read-only-operations-console.md)
208. [实施追踪 v0.61.0](docs/implementation-status-v0.61.0.md)
209. [System Paper 运维手册](docs/runbooks/system-paper-operations.md)
210. [本机只读运维控制台手册](docs/runbooks/operations-dashboard.md)
211. [Replacement Challenger Plan Schema](config/challenger-replacement-plan-v1.schema.json)
212. [Replacement Challenger 冻结计划 v0.62.0](artifacts/challenger-replacement/challenger-replacement-plan-v0.62.0.json)
213. [Replacement Challenger 预注册与证据隔离 ADR-0062](docs/adr/0062-replacement-challenger-preregistration-isolation.md)
214. [实施追踪 v0.62.0](docs/implementation-status-v0.62.0.md)

如果文档之间出现冲突，以《系统计划 v1.1》的产品目标和硬风险约束为最高优先级；运行数据字段以《核心数据契约》为准，各发布对象字段以对应Schema为准；机制解释以《AI 研究与模型治理》和《开发路线与验收门槛》为准；发布数值、比较运算符、必需性和样本不足结果以 `ReleaseGatePolicy` 为准，指标单位/估计器以Metric Catalog为准，条件聚合和证据作用域以《发布评估与证据规范》为准。

机器政策当前是 `DESIGN_BASELINE` 且 `production_activation.enabled=false`。在DataQuality、Split、StatisticalDesign、Accounting、CostAllocation、ForwardControl、Compliance Attestation及Evaluator build hash全部绑定前，任何正式PASS都无效；这是有意的Fail-Closed状态。

当前策略有两条互斥发布路径：

- `BASELINE_ONLY`：简单趋势/突破独立证明扣费后经济价值，AI 指标不适用。
- `AI_ENHANCED`：简单基线先通过，再证明 AI 在相同候选事件、风险和成交条件下提供增量价值。

AI 失败不阻止已经独立通过全部门槛的简单基线；简单基线失败时，AI 不得用来掩盖失败。

## 实施状态

Git中的设计基线已冻结，当前代码版本为 `0.62.0`，正在逐项执行《开发路线与验收门槛》第9节。已完成规范化哈希、Decimal/tick/step基础、版本化InstrumentMetadata、核心决策链、SQLite WAL账本与Outbox、Golden Replay、RiskLock与部署档位风控、订单UNKNOWN对账、PositionExecutor、发布Artifact信任链、可重放经济账本、依赖序列统计、AI相对简单基线的同proposal/time配对增量、删除最大正贡献单元后的完整GROWTH endpoint复评、删除Top-5正贡献完整交易后的路径依赖经济重放、累计Trial Registry上的Holm/双侧区间宽度/ESS/MERE功效重放、AI-vs-baseline与Minor candidate-vs-active的配对最大回撤和ES95改善区间、Binance官方公开历史归档、公开Spot行情的同时只读捕获与修订/缺口证据、从当前公开输入到基线决策/保守模拟成交/双独立经济账本的单周期离线 Paper 闭环、4h槽位与可恢复长期Paper调度、三样本交易所时钟纠偏、当前永续 Mark/Index/Premium/OI/Funding 上下文、当前账户 Spot/USDⓈ-M commission 的只读取证边界、账户费率与Paper经济结果的PIT费用重放绑定、账户成本/永续同槽位的context-complete可恢复侧车、共享可信时钟与保留决策前账户证据的可恢复完整周期编排、42个完整月与显式日档修复的完整研究语料、官方1m执行代理、严格因果event-based标签、固定低维Logistic档案研究、固定分组的简单基线失败归因、仅前向challenger事件流状态机与不可回填记录器、固定3+1公共请求边界的实时只读runner与source bundle、无凭据macOS LaunchAgent合同、固定用户域原子安装与私有执行快照、首槽state/bundle/log/install receipt的只读交叉取证、首个预注册真实decision的逐字节证据封存、在退出结果出现前冻结的首个episode只读观察器、决策后1m保守成交与双边成本计划、完整日档验证与Decimal经济结果评估器、只在completed receipt和日档时间门后工作的owner-only官方archive采集器、从全部可信输入自动派生唯一结果的离线CLI、首个自然完成episode的逐字节证据封存、在第二Episode前冻结的90天全纳入confirmatory cohort、在cohort首槽前冻结的累计经济评估门、从cohort start自动验证全部槽并为所有completed Episode生成不可选择receipt的只追加管线、从全部verified receipt自动求UTC日并集并跨Episode复用完整官方1m日档的共享归档层、从全部completed receipts和verified日档自动生成每Episode成本后结果与不可变累计索引的全纳入管线、固定尾部前禁止读取PnL、尾部后才对完整540槽运行预注册累计门的离线评估器、把 receipt/archive/result 三阶段按固定顺序安全串联的一次性证据维护协调器、每天08:10且与策略Runner隔离的证据维护LaunchAgent合同、由Git冻结external trust约束的owner-only私有执行快照、首次08:10自然维护证据、原 cohort 漏槽失败与停用证据，以及无凭据 BASELINE_ONLY System Paper 的90天范围、公开数据、虚拟本金、保守成本、模拟成交和零真实交易权限计划，及独立、崩溃安全、不可回填的 WAL scheduler library、deployment trust chain、90天固定尾部 evaluator、严格 tail-blind operations projection，以及仅回环、只读、无轮询的运维 Web、确定性告警与失败关闭运行手册，以及 replacement Challenger 的失败 ancestry、新运行身份、540槽预注册和严格证据隔离计划。完整验证都必须显式提供在Artifact之外保存的 trusted attestation hash，self-hash不能自证来源可信。

当前58个Catalog算法中有26个Estimator可执行，其余32个明确Fail-Closed。公开历史归档的结构化请求只能访问ETHUSDT/BTCUSDT的allowlisted数据族；生产transport只执行无凭据GET，必须在解压前通过官方checksum，并将来源、质量和快照绑定到哈希。真实smoke已验证2026-07-25 ETHUSDT Spot daily 4h归档，但全部事后归档固定为`ARCHIVE_REPLAY_ONLY`：URL不是Artifact身份，也不能证明历史决策时点的数据可用性。Fee Schedule因产品、账户层级、折扣和生效期而独立冻结，不能从行情或当前网页费率反填历史。

v0.17固定轮询公开market-data-only端点的1m/4h Kline、AggTrade和BBO，保存原始响应、客户端接收时刻、Kline修订、可观测AggTrade缺口和外部session attestation。BBO没有源事件时间/序列，固定标记为`BBO_SEQUENCE_UNOBSERVABLE_REST_SNAPSHOT`；交易所源时钟领先本机时使用保守clock floor并显式报告。真实两轮smoke重放通过，但持续时间不足、缺永续上下文和账户成本/成交，因此固定为`CONTEMPORANEOUS_RESEARCH_ONLY`/`CAPTURE_REPLAY_ONLY`。

v0.18严格分阶段获取当前4h warmup、公开exchangeInfo、BBO和AggTrade，冻结`SPOT_LONG_SMA20_VOL12_BUCKET25_V1`基线及`OFFLINE_PAPER_CONSERVATIVE_BBO_V1`成交规则，并分别生成BASELINE/AI临时WAL经济账本。真实smoke自然产生LONG和一笔0.0459 ETH模拟成交；立即保守清算权益为999.5506993585 USDT，显式包含双边滑点和双边15bps假设费用。这个负的成本压力值不是24h策略收益，也不证明盈利或亏损。

v0.19把cycle放入固定UTC 4h槽位：close后5分钟到期，15分钟租约，append-only SQLite WAL事件链。精确run bytes先进入不可变PREPARED blob再发布文件，因此崩溃恢复不重新请求不同市场响应。真实smoke保留了第一次`PAPER_CLOCK_INVALID`失败和第二次成功；同槽位再次调用返回`ALREADY_SUCCEEDED`且网络请求为0。missed/expired槽位永久不可回填。

v0.20在每次新周期前固定执行三个Binance public server-time GET，用保守offset interval交集区分aligned、可校正和blocked。真实smoke发现本机约慢2.51秒，使用monotonic anchor安全校正后首次执行为3个时间请求+4个行情请求；同槽位第二次为3+0，bomb行情transport调用为0。每次结果进入独立append-only WAL心跳链，保存gap和告警转换；外部告警投递仍未配置。

v0.21固定五个Binance USDⓈ-M public GET，在健康纠偏时钟之后捕获Mark、Index、Premium、OI和Funding；从原始receipt重建基差、4h OI变化和每1000 USDT SHORT Funding压力场景。只有历史Funding间隔一致时才计算24h场景，且明确不是预测或已实现收益。当前网络对官方Futures host的第一个请求仍失败关闭，因此真实快照尚未进入长期Paper，未使用替代来源。

v0.22固定三个USER_DATA signed GET，先证明API key为只读且IP-restricted，再读取当前ETHUSDT Spot与USDⓈ-M账户费率；任何额外true权限都会在commission请求前阻断。Spot权威成本保守使用standard/special/tax的no-discount总和，BNB折扣仅作非权威情景。由于没有合规credential文件，真实signed smoke按设计未运行，没有用fixture或平台默认费率冒充账户证据。

v0.23把完整Paper run、完整account commission snapshot及两个外部attestation做PIT绑定；只有账户费率在决策前可用并覆盖run end时，才用no-discount taker-buy/sell重算费用和保守清算权益。信号、成交、数量、价格和滑点保持不变。fixture重放显示旧15bps假设更保守，但成本调整后净变化仍为负；这不是实盘账户或盈利证据。

v0.24保留旧Paper scheduler证据不变，以独立append-only WAL侧车冻结同一4h槽位的Paper/account-cost/perpetual bundle。PREPARED或publish后崩溃均从原bytes恢复，source read和network均为0。context schedule只统计侧车SUCCEEDED，旧Paper成功不能继承；首尾间缺槽会破坏连续90天资格。

v0.25把账户费率、Paper、永续、binding和context sidecar固定在一个可恢复编排中。正常路径共享一次三样本probe和一个monotonic clock，物理请求为3+3+4+5=15；账户证据在Paper决策前进入独立不可变WAL，后续失败只复用不重采。新增LaunchAgent renderer只生成mode-0600 plist/合同，不调用`launchctl`，没有安装receipt就不声称已调度。

v0.26把AI训练前的数据窗口前瞻冻结为`2023-01`至`2026-06`，每月固定ETH Spot 4h、BTC context 4h、ETH Mark 4h和ETH Funding四流，共168项、正常完整首次下载336个公开GET。SQLite WAL/FULL状态保存exact snapshot bytes并支持租约恢复；全部齐全也只允许archive research feature build，永久不能把事后归档冒充PIT-valid OOS。真实官方月度smoke的186根Kline与独立重下载archive/checksum/CSV/source-row root一致；该版本发布时仅完成1/168。

v0.27在仓库外 owner-only 目录完成168/168项语料，并保留两个 Binance 月度 ETH Mark 来源缺口。系统只使用对应缺失UTC日的官方daily archive与checksum建立显式repair sidecar，精确补齐12个4h间隔；独立新进程在网络禁用时可完全重建repair bundle。完整覆盖只允许archive research feature build，仍不获得PIT、正式OOS或盈利资格。

v0.28从42个月官方ETHUSDT Spot 1m档案保存1,560个所需执行分钟，显式保留81个与所需行零交集的官方来源缺口。严格因果数据集包含780个非重叠LONG事件；419个滚动OOS事件中，简单基线8/8季度为负。固定Logistic只接受10个事件，过滤后累计点估计略正，但整体Brier差于常数预测器且仅2/8折更优。因此基线与Logistic均拒绝晋级，不启动XGBoost；这是防止“几乎全空仓”被包装成AI优势的预期Fail-Closed结果。

v0.29在查看真实分组前冻结归因边界，证明全部780个事件及419个pooled archive OOS事件在扣手续费前的保守成交代理gross PnL已经分别为`-1292.32171`与`-957.969754 USDT`；费用会扩大亏损，但不是唯一根因。203个SMA early-exit事件成本后全部为负，而24h组为正；这些结果只用于诊断，不能事后删除退出或挑低波动分组冒充新OOS。唯一成本预算+正动量challenger已预注册，但保持`NOT_RUN_PREREGISTERED_FORWARD_ONLY`。

v0.30把唯一预注册challenger实现为确定性4h事件流状态机：21根闭合ETHUSDT Spot Kline、成本距离与正动量同时入场、8h最短持有、SMA与24h退出。决策按连续槽位进入owner-only append-only SQLite WAL，精确重试幂等，漏槽、迟到、输入修订、UPDATE/DELETE和语义篡改全部失败关闭；研究决策没有Broker、Order或真实资金权限。版本冻结时尚未到首个允许槽位，因此只保存`WAITING_FORWARD_START_NO_DECISIONS`证据，不创建伪造快照或收益。

v0.31把记录器接到最小实时公共输入：每轮先用3个Binance server-time响应打开可信时钟门，只有当前槽位等于下一必需槽位时才执行1个由slot派生、禁止覆盖的ETHUSDT Spot 4h Kline GET。完整raw body、HTTP receipt、探针和candidate decision先组成owner-only source bundle，再追加state；早到与漏槽都产生0个行情请求。20根重叠Kline必须沿用首次availability，任何闭合行修订失败。CLI只接受state/output路径，不接受URL、时间、symbol、凭据或订单参数。版本冻结时仍早于首槽，因此真实网络请求和真实decision均为0。

v0.32固定并在仓库外真实生成`local.crypto-quant.challenger-forward` LaunchAgent合同：Asia/Shanghai +08:00无DST，本地0/4/8/12/16/20点02分触发，与UTC 4h网格一致；程序参数只包含runner module、state path和output root，环境变量只含PYTHONPATH，无credential、shell、URL或order。runtime与发布目录为0700，plist/合同为0600。生成器明确没有调用`launchctl`，因此状态仍是`NOT_INSTALLED_NO_EXTERNAL_RECEIPT`。

v0.33已把该合同安装到当前用户`gui/501`域。真实测试发现LaunchAgent不能可靠地从`~/Documents`导入项目模块，因此执行代码改为Application Support内由提交`b96955a`生成的owner-only私有快照；安装receipt绑定82个文件的树哈希、目标inode/hash和固定launchctl命令证据。修正后的两个后台调用均退出0并返回`NOT_DUE`，每次完成3次公开server-time请求；安装恰逢日历触发分钟，RunAtLoad与日历触发的逐次归因未被证明。Kline、decision、Broker和order均为0。第一次失败现场被完整归档，没有删除。

v0.34新增完全离线、只读的首槽观察器：不触发Runner、不联网、不写state，只从已验证安装receipt推导路径，并交叉验证SQLite首条decision、唯一source bundle、唯一stdout `RECORDED`和当前固定launchctl绑定。真实首槽前运行返回`WAITING_BEFORE_FIRST_SLOT`，decision/bundle为0/0，且没有发布伪成功receipt。非空WAL、漏槽、多个bundle、历史日志修改或任一协调篡改均失败关闭。

v0.35使用tag `v0.34.0`的冻结observer验收首个预注册槽位。LaunchAgent在`2026-07-29T00:02:06.752Z`自然写入唯一decision和source bundle；state、bundle、stdout第6行、install receipt、私有执行快照、contract、plist及当前`launchctl print`全部交叉一致。Runtime receipt由同一v0.34 loader重载，Git副本与原件19,463 bytes及SHA-256逐字节一致。Observer没有网络、Broker、订单或state写入；`ENTER_LONG`仅为`LOCAL_PREQUENTIAL_RESEARCH_ONLY`研究状态，不是下单。

v0.36在首个可退出槽位前冻结首个episode的完整成功、进行中、漏槽和失败边界。只读observer从安装证据推导唯一state/bundle/log/service路径，逐槽交叉绑定整个episode前缀；进行中不发布receipt，只有首次合法返回FLAT才封存。真实观察在`2026-07-29T01:17:00.579Z`返回`FIRST_EPISODE_IN_PROGRESS_VERIFIED`，decision为1，receipt未发布，观察前后state/stdout/stderr哈希不变，网络、Broker、订单和state写入均为0。

v0.37进一步在退出结果前冻结经济测量：entry/exit都只能使用decision `recorded_at`严格之后的下一完整UTC 1m，买入采用官方日档该分钟high加10bps并向上按0.01舍入，卖出采用low减10bps并向下舍入；1000 USDT、0.0001 ETH步长及双边15bps taker fee全部固定。真实entry minute由`00:02:06.752Z`派生为`00:03:00Z`。版本没有获取未来archive、没有填exit或PnL、市场请求为0，状态为预注册等待。

v0.38在同一退出结果出现前冻结并实现纯离线评估器：它只接受v0.37 exact plan、v0.36 loader复核的complete receipt，以及由allowlist派生且checksum通过的完整1440行官方DAILY 1m档案。entry/exit exact raw row、档案哈希和逐项Decimal计算全部可重放；同日只能一个日档、跨日只能两个。8个合成fixture测试覆盖正负结果、跨日、rounding、checksum、缺行、过早档案、协调篡改和exact publish/load。本版本没有读取真实退出、没有市场请求，也没有发布真实经济结果。

v0.39把官方日档获取接到受控操作层：只有v0.36 complete receipt、v0.37 exact plan和v0.38派生日期全部有效，且完整UTC日结束5分钟后，才允许由allowlist执行ZIP/checksum GET。404只返回pending；成功后在仓库外0700/0600目录封存exact bytes和hash-bound receipt。已验证日期重试为0请求，跨日只补缺失日期。CLI不接受URL、日期、价格、费用、订单或strategy state路径。本版本使用fixture完成9项专测，没有观察真实exit或发起真实archive请求。

v0.40把证据链收口为单一离线入口：CLI只接受v0.37计划、v0.36完成凭据、install/contract/plist、v0.39归档根与结果根的绝对路径；不接受时间、价格、费用、收益、标签或文件名覆盖。它从已验证归档的最大`retrieved_at`派生确定性结果身份，调用v0.38构建、exact publish并立即重载；重复运行保持同一路径和逐字节结果。版本只使用fixture，没有观察真实exit、发起市场请求或生成真实经济结果。

v0.41使用与v0.36.0一致的冻结observer验收首个自然完成Episode：五条Episode decision、五个source bundle和五行stdout交叉一致，`EXIT_LONG_SMA20`首次返回FLAT。Runtime receipt经同版本loader重载，Git副本与原件66,839 bytes及SHA-256逐字节一致；observer没有市场网络、Broker、订单或state写入。由receipt自动派生的唯一2026-07-29官方日档已过时间门，但v0.39首次ZIP请求返回404，因此经济结果继续pending且未使用任何回退。

v0.42只重试同一自动派生的官方2026-07-29 DAILY日档，ZIP与checksum均通过，完整1,440行CSV由v0.39 loader重放。v0.40离线CLI自动选择`00:03Z`与`16:03Z`两条1m行，在事前冻结的10bps双边滑点、15bps双边taker fee和Decimal舍入下得到gross `-20.493837`、net `-23.4627746535 USDT`、return `-2.34627746535%`。Runtime result经loader重载，Git副本与原件5,360 bytes及SHA-256逐字节一致；结果明确为非真实成交的单Episode不合格代理。

v0.43在第二Episode开始前把future-only confirmatory cohort固定为北京时间2026-07-30 20:00起的90天半开窗口。首个负结果永久保留为已暴露pilot；窗口内每个ENTER_LONG全部纳入，REJECT_ENTRY保留作连续性证据，窗口内入场跟踪到自然退出。禁止按PnL提前停止、重置、延长或挑样；中期只允许描述性报告，证据不足固定为`INCONCLUSIVE`。AI仍不进入该队列。

v0.44在cohort首槽前冻结累计评估：540槽位完整、至少30个Episode、ESS至少20、固定3-Episode MBB/10,000次重采样、MERE 0.5%、功效至少80%和CI全宽最多2%。通过还要求主收益LCB大于0、至少5/6固定15天块非负、最大回撤低于10%、1.5倍摩擦累计非负，以及删除Top-5正贡献后LCB仍大于0。任一样本或精度不足只能`INCONCLUSIVE`，研究PASS也不等于系统盈利。

v0.45在cohort首槽前冻结跨版本流水线，并新增任意Episode的只读receipt层。CLI不接受Episode、日期或state/log路径选择器；它从唯一安装信任根验证cohort start以来的全部4h槽、保留`REJECT_ENTRY`、自动枚举所有完成Episode并一次发布全部缺失receipt。每份receipt绑定更早Episode列表和自身exit前的decision/bundle/log前缀，后续现场追加不改变旧receipt。v0.45不计算PnL，也没有新增市场请求或交易权限。

v0.46把官方日档采集泛化为cohort共享层：CLI扫描全部v0.45 loader-verified receipt，从entry/exit `recorded_at`自动派生严格之后的完整UTC分钟及日期并集；调用方不能传Episode、日期、symbol或URL。每个日期只保存一份完整1440行ZIP/checksum/day receipt，receipt不绑定单个Episode，因此同日新增Episode可零请求复用exact bytes。时间门前与无completed receipt均为0请求；404保持pending；本版本不计算PnL。

v0.47把每笔completed cohort Episode自动转换为统一经济结果：只接受exact v0.43/v0.37 plans、v0.45 loader验证的完整receipt前缀和v0.46 loader验证的共享日档；entry/exit分钟、bar high/low、10bps滑点、15bps双边费率、1000 USDT和Decimal舍入全部自动派生。每个结果先exact发布，再追加包含完整前缀的不可变hash链索引；崩溃可安全恢复，负结果不能删除。中期状态始终为`DESCRIPTIVE_NO_EARLY_SUCCESS`。

v0.48把v0.44预注册计划实现为固定尾部累计评估器。它在`2026-10-29T12:00:00.000Z`前只读验证槽位、bundle、log和服务连续性，不读取或输出cohort收益；尾部后才要求完整540槽、无active Episode、全部receipt/result/index精确对应，并运行固定MBB、ESS、功效、六时间块、回撤、1.5倍摩擦和leave-Top-5门。样本不足只能`INCONCLUSIVE`；研究PASS也仍不等于系统盈利。

v0.49把v0.45 receipt、v0.46 shared archive和v0.47 result/index固定串联为单次幂等维护。每次运行共享唯一UTC观察时点；receipt连续性失败立即停止，日档pending/partial时不调用结果阶段，只有全部所需日档verified才发布全纳入结果。协调器不接受Episode、日期、URL、PnL或阶段选择器，不调用Runner、Broker、订单或策略state，也不在tail end前调用v0.48。

v0.50为v0.49生成独立LaunchAgent合同：每天北京时间08:10唯一触发、`RunAtLoad=false`，程序参数自动绑定全部计划、strategy trust和evidence roots；环境只有`PYTHONPATH`，不包含credential或策略Runner入口。真实合同已在仓库外以0700/0600生成并由external attestation复核，但尚未安装、加载或运行。

v0.51从v0.50 production loader验证通过的合同生成129文件owner-only content-addressed快照，重新渲染候选，并先在Git提交中冻结新的external trust。restricted installer只执行固定`print → bootstrap → print`；真实安装后服务`runs=0`、`state=not running`，策略state与日志哈希不变，维护日志及cohort证据根均未创建。调度已加载，但尚未证明首次自然08:10运行。

v0.52在首次自然维护槽前冻结只读observer，从v0.51信任链自动派生service、08:10时间门、日志与全部evidence roots；它只执行一次固定`launchctl print`，WAITING/PENDING不发布receipt，漏槽或非零退出失败关闭。真实首槽前观察为`runs=0`、never exited，所有策略文件和inventory前后不变；口述时间不能覆盖系统UTC时钟和launchd证据。

v0.53使用tag `v0.52.0`的冻结observer验收首次08:10自然维护运行：LaunchAgent自然运行一次并退出0，唯一stdout summary合法、stderr为空，策略state/日志和三个cohort inventory在观察前后不变。Runtime receipt经同版本production loader重放，Git副本与原件10,273 bytes及SHA-256逐字节一致。首轮维护时cohort尚无completed Episode，因此没有archive请求或经济结果；这证明自动证据管线按计划运行，不证明盈利。

v0.54确认原 Challenger cohort 在 `2026-08-01T04:00:00.000Z` 永久漏槽。只读 observer 封存 failure receipt 后，系统只对固定旧 Runner 执行一次无 shell bootout；旧 service 已不再加载，state/stdout/stderr 原字节不变。两份 runtime receipts 与 Git artifacts 逐字节一致。该结果证明连续性失败并阻止继续制造无资格数据，不评价收益；禁止补槽、回填或把旧 cohort 恢复为可完成。

v0.55冻结唯一的无凭据 `BASELINE_ONLY` System Paper 计划：ETHUSDT Spot LONG-only、4h决策、90天独立窗口、1000 USDT虚拟本金、单边10bps滑点和15bps taker费用。计划只列公开市场GET请求族，不包含URL、header、secret、账户或订单端点；模拟Broker、对账、风险锁和kill switch是后续启动前必需门。当前状态固定为`PLAN_FROZEN_PAPER_NOT_STARTED`，不安装runtime、不开始90天计时，也不形成收益或Canary资格。

v0.56实现无凭据确定性模拟Broker和完整单槽`decision→risk→simulated order/fill→ledger→reconciliation`闭环。它严格绑定冻结ETHUSDT Spot计划与有效InstrumentMetadata，使用含滑点的保守价限制批准名义金额，重放部分成交/断线/UNKNOWN等订单状态，并记录持仓成本、已实现PnL、未实现PnL和累计费用。production loader必须完整重跑槽位并验证exact genesis/parent artifact chain，单纯重算外层hash不足以通过。该版本仍不安装、不请求市场、不启动Paper或计时。

v0.57完成独立、无凭据、确定性离线 WAL scheduler library：固定4h UTC槽位、5分钟close delay、15分钟lease、只追加事件与prepared inputs/results、完整 parent-chain loader、immutable publish和冻结故障注入矩阵。它不是CLI、service或network transport；不安装、不启动Paper、不创建start receipt，也不开始90天计时。v0.58 deployment trust chain（独立deployment/install/observer/start receipt）仍是后续门。

v0.58完成代码级 System Paper deployment trust chain：固定公开行情 source bundle、单槽 runtime CLI、owner-only LaunchAgent 合同与执行快照、常在/时钟/重启/磁盘/网络 preflight、受限 installer、只读首槽 observer 与不可覆盖 start receipt。本版仅发布代码与冻结合同：未渲染生产合同、未执行 preflight/install/bootstrap/runtime，未创建 start receipt，90天计时仍未开始。

v0.59冻结 System Paper 的90天固定尾部 evaluator、严格 loader、七路径 CLI、结果 Schema、镜像 Schema 与离线测试。它在尾部前禁止读取经济字段，尾部后要求完整540槽、全量重放和固定安全/成本/回撤/30天块收益门。发布前审查发现的首次 final 竞态、证据重新捕获、output root 重叠和脱离 loader 缺口均已关闭；后续定向残余复审又关闭了可替换 child lock pathname 分裂锁域、以及不完整 inventory 抢先降级 prepared corruption 的问题。现在 finalization 直接锁定 retained output-directory inode；tail 后先在 retained SQLite 上完成 state-only prepared replay，再分类单次 inventory，稳定 prepared 损坏选择 raw-bound INCONCLUSIVE，retained event schedule 与 start receipt 的首槽、540槽/90天边界不一致则硬失败。它只实现并验证代码/Schema/CLI/evaluator：未 production 安装、未启动、未开始90天、没有真实结果；没有盈利、AI 优势、Canary 或实盘资格。未来真实结果必须原样封存为 `PASS`、`DID_NOT_PASS` 或 `INCONCLUSIVE`；`PASS` 也只进入后续研究，replacement Challenger 仍未完成。`production_activation.enabled=false`继续生效。

v0.60冻结纯函数 Tail-Blind 运维投影：三个 typed adapter 按固定顺序各调用一次，逐字段输出 release identity、Challenger 连续性状态和 System Paper 模拟订单生命周期/对账/风险状态；freshness、总体健康和 canonical hash 均在边界内派生。Challenger final 前只显示 `WITHHELD_PRE_TAIL`，类型和 Schema 结构上不存在中期经济指标；严格 loader 拒绝重复键、float、未知字段、非 canonical bytes、状态矛盾和 hash 篡改。本版本没有发现或读取 production evidence、安装或启动服务、访问市场/Broker、提交订单或写 state；Web/alerts/runbooks 仍属于 v0.61。

v0.61在 strict v0.60 projection 上实现本机只读运维控制台与确定性 alerts：服务只绑定字面值`127.0.0.1`，校验Host，只开放四个GET，所有非GET返回405，路径攻击400，来源失败返回不泄密503。页面只做一次same-origin读取并用`textContent`渲染，不轮询、无操作按钮、无远程资源；告警只从stale/degraded/failed-closed/incident/UNKNOWN/reconciliation/risk字段派生。两份runbook固定当前禁止安装/启动和未来失败关闭取证边界。本版仍未创建production root、LaunchAgent或任何真实Paper证据。

v0.62冻结 replacement Challenger 的预注册和证据隔离计划：唯一 parameterless builder、严格 Schema mirrors和 owner-controlled loader 永久绑定原 cohort 的漏槽失败/停用 exact bytes，同时固定全新 service、runtime root、plist和证据子路径。旧 decisions、Episodes、receipts、archives、results、PnL、槽位和运行天数全部禁止迁移或回填；90天/540槽只能从未来首个自然成功槽的 verified start receipt 派生。本版不实现 runtime/deployment，不安装、不启动、不请求市场或 Broker，状态固定为 `PLAN_FROZEN_REPLACEMENT_NOT_STARTED`。

仓库仍没有批准AI模型、真实成交与实际滑点、连续90天合格证据或实盘授权，因此不能声称策略赚钱、AI优于基线或具备PIT-valid OOS证据。原Challenger cohort已因漏槽永久失败并停用，禁止补槽、重置或继续累计；System Paper 的启动前代码批次现已覆盖 v0.59 evaluator、v0.60 Tail-Blind 运维投影和 v0.61 只读 Web/alerts/runbooks，但仍未 production 安装、未启动，尚无真实 install/start receipt 或已启动的90天证据。replacement Challenger 现仅完成 v0.62 预注册/隔离，尚缺 WAL runtime、deployment/start trust chain、评估器与运维层。两条流都必须在启动前工程和真实机器门完成后，才能从各自首个自然成功槽的 start receipt 独立计时。`production_activation.enabled=false`继续生效。详细完成度见[实施追踪 v0.62.0](docs/implementation-status-v0.62.0.md)，工程裁决见[ADR-0062](docs/adr/0062-replacement-challenger-preregistration-isolation.md)。
当前依赖及许可证记录见[依赖与许可证清单 v0.1.0](docs/dependencies-and-licenses-v0.1.0.md)。

本地验证：

```bash
make validate
make test
```

`make validate`在当前设计状态输出 `FAIL` 是正确结果：缺少必需Policy绑定且生产激活开关为关闭状态。

## 已锁定的 V1 范围

- 交易所：Binance 优先，Gate 仅作为后续适配。
- 标的：资金小于 1,000 USDT 时，仅 ETH 使用真实资金；BTC 只提供市场背景和纸面信号。
- 产品：LONG 使用无保证金 ETH/USDT 现货；SHORT 使用单向、逐仓、最大 1x 的 ETHUSDT USDT 本位永续。
- 决策频率：4 小时；预测/持有目标约 24 小时；正常情况下最短持有 8 小时，并设置反手滞回。
- 策略：简单趋势/突破负责提出方向；可选XGBoost成本感知Meta模型只有证明增量价值后才负责过滤和分档；确定性风控拥有最终否决权。
- 风险：目标年化波动率 12%；风险档位仅允许 0/25/50/75/100%。
- 上线：研究、Shadow、Paper、25/50/75% Canary、Champion 逐级晋级；任何新模型不得自动接管资金。

## 明确不做

- 不使用大于 1x 的杠杆。
- 不做高频、网格、做市、跨所套利和复杂订单网络。
- 不让 LLM、Agent 或强化学习模型直接下单。
- 不用封存审计集反复调参。
- 不因回测好看而跳过 Paper、Canary、对账或风险验收。
- 不直接复制 GPL/AGPL 项目的实现代码。
