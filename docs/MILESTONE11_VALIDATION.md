# Milestone 11 — Explainable Reasoning Trace

## 设计边界

产品界面称“诊断思路”。该功能是本地结构化 Decision Trace，不读取、请求、保存或
展示模型隐藏推理。数据来自现有 TurnIntent、ToolPolicy、Coverage、Evidence、
Hypothesis、EvidenceSufficiency、TaskVersion、ResponseMode 和 FallbackReason。
不复制用户消息、完整 Prompt、Tool JSON、知识 chunk、Cookie、密码或异常堆栈。

不重构认证、Tool Calling、RAG、Citation、会话级历史及 conversation_turns。
唯一相关的诊断语义补齐是将需求样例中的“完整排查 / 全面排查”加入既有完整网页
诊断同义词，使实际 Coverage 与用户目标一致，而不是在 Trace 中描述不存在的检查。

## 文件与数据模型

新增生产模块：`src/netpilot/agent/reasoning_trace.py`。它集中定义
`ReasoningTraceStep`、Builder、去重、截断及合并规则。

每个步骤含 step_index、八种 phase、title、summary、evidence_ids、hypothesis_names、
decision、UTC created_at、severity，另记录 turn_index / task_version。只新增
`reasoning_trace`，不新增 raw reasoning 或隐藏推理字段。

相关改动：

- `agent/schemas.py`、`task_state.py`、`session.py`：当前 Turn 结果、跨 Turn TaskState 与有界累计轨迹。
- `agent/orchestrator.py`：采集钩子与统一结果出口；模型/工具执行分支保持原有行为。
- `agent/coverage.py`：观察使用稳定 Evidence ID，补齐完整排查同义词。
- `config.py`、`main.py`、`.env.example`：配置与组件接线。
- `api/presenters.py`、`api/routes.py`、`models/`：响应、指标及安全的公开上限设置。
- `history.py`：Session snapshot 持久化与旧数据兼容。
- `reports.py`：Markdown / JSON 导出诊断思路。
- `web/index.html`、`app.js`、`style.css`：独立可折叠区域、历史回放、SSE complete、报告预览。
- README 与本验收文档；新增测试及辅助 fixture。此前未提交的行内引用和其他用户改动保留。

## Builder 与采集节点

| 阶段 | 实际触发点 | 记录内容 |
|---|---|---|
| intent | 完成分类后 | 当前任务类别，不保存原始用户消息 |
| planning | ToolPolicy 与 Coverage 已生成 | 必需检查范围、RAG 或无网络工具的处理方式 |
| evidence | 工具批次完成 / 复用已留存证据 / 读取历史 | 聚合同类观察、资料数量与类型、当前账号历史数量 |
| hypothesis | 本地 tracker 状态发生变化 | supported / weakened / excluded 等状态及关联证据 |
| decision | Coverage/Sufficiency、澄清、RAG、报告、反馈等分支 | 继续、停止、受限停止或复用的依据 |
| state_change | 进入新 task_version | 保留旧观察用于比较，新版本不重复使用旧实时证据 |
| fallback | 实际进入现有兜底或错误返回 | 受控原因摘要，不保存异常 payload |
| finalization | 返回最终 API 结果前 | 当前证据最支持的判断或非诊断任务处理结果 |

多个 DNS 观察归为一个类别条目，不逐个复制 Tool Step。继续决策关联当时的证据集合，
因此 DNS 异常后的 HTTP/TCP 缺口和解析链路归因限制可以单独解释。覆盖充分只表示
满足检查目标，不等于已确认唯一根因；覆盖不足时使用 `stop_limited`，不会冒称充分。

## 证据关联、去重与长度

每个新 `AgentToolStep` 获得独立 Evidence ID，`evidence_from_step` 保留同一 ID，
公共 ToolCallView 也返回该 ID。当前 Hypothesis 和 Trace 的 ID 因而能与 Session
Evidence/持久化工具记录对应，不再仅依赖可能跨 Turn 重复的模型调用 ID。
旧的无 Trace 历史保持原去重语义；有 Trace 关联的观察按真实证据身份保留。

去重签名为 turn_index、task_version、phase、title、排序去重后的 evidence_ids
与 decision。相同 Turn 内完全相同的决策不重复；不同 Turn 的意图不被误吞。
同类别证据在当前 Turn 聚合更新。上限默认 50，可配置 1～200；保留近期条目，
其余优先保留状态变化、兜底、意图、假设、决策和结论，避免无限增长或旧关键事件
挤掉所有新观察。索引保持单调而不伪造被截断的旧步骤。

## 配置与可选摘要

```dotenv
REASONING_TRACE_ENABLED=true
REASONING_TRACE_MAX_STEPS=50
REASONING_SUMMARY_LLM_ENABLED=false
```

默认路径只做本地结构化操作，测试确认 LLM/Tool 调用数与关闭 Trace 时相同。
关闭 Trace 时当前 Turn 返回空数组，不删除已经保存的历史。

显式启用可选摘要后，最多一次额外、无 Tool 的 LLM 调用，从最多十二条已有摘要中
选择 2～5 个 step_index。系统只接受有效且不重复的索引，并用已验证的原摘要生成
2～5 个 bullet；模型的自由文本、猜测、工具请求或隐藏推理不进入输出。
无效输出、超时和异常不改变主答案。Trace 关闭时也不会调用摘要模型。

指标含 reasoning_trace_steps、reasoning_summary_llm_used、
reasoning_summary_prompt_tokens / completion_tokens。`llm_used` 表示实际尝试调用，
即使该可选调用失败；有返回 usage 时计入总 usage，未提供 usage 时不虚构 Token 数。
默认关闭时 used=false、两项摘要 Token 均为 0。

## API、History 与 Report

- ChatResponse.reasoning_trace：仅当前 Turn 新增轨迹，SSE complete 同样返回。
- SessionTaskState.reasoning_trace：按同一上限保留跨 Turn 轨迹；task_version 改变不清空。
- DiagnosisRecordView.reasoning_trace：同一账号/Session 的有界累计轨迹，随 snapshot JSON 写入 SQLite。
- SNAPSHOT_SCHEMA_VERSION 从 3 升至 4；SQLite 表/metadata 版本仍为 3，不重建表，不迁移旧答案。
- 旧 v1/v2/v3 snapshot 缺失字段时返回 []，不反推旧推理。重新打开数据库可恢复新轨迹和完整 transcript。
- 原有登录与资源归属约束继续保护详情、报告和导出；Bob 读取 Alice 对应资源返回 404。
- Markdown 新增 `## 诊断思路`，JSON 保留结构化 reasoning_trace，报告预览也显示摘要。报告、引用来源和会话记录原有内容仍保留。

本功能不恢复重启后已经过期的内存 Chat Session；恢复指的是从持久化 History
重新展示完整 transcript 和已保存的轨迹，而不是重建缺失的 Agent 状态。

## 前端

“诊断思路”使用独立原生 details/summary，位于既有工具时间线上方。默认、新 Session
和打开历史时折叠；同 Session 更新条目及 SSE complete 不改变手动展开状态。
显示数量、阶段、标题、摘要和关联证据数量，不显示内部 Prompt 或 Tool JSON。
所有字段使用 textContent，恶意 HTML 也仅作为文本显示。

当前 Session 的 Trace 与浏览历史时的显示数据分离，防止浏览旧记录后继续聊天时
混入旧 Session 的轨迹。SSE delta 不生成虚构的实时思考；只在完整结果收到后更新。
原有安全 Markdown/Citation renderer 和折叠工具时间线继续通过回归。

## 自动测试

新增必需测试文件：

- `tests/test_reasoning_trace.py`：RT-01～09、DNS 聚合、缺口/停止、状态版本、任务分支、默认调用数及可选摘要安全失败。
- `tests/test_reasoning_trace_persistence.py`：RT-10/11、三轮重载、SSE、旧快照、截断、重复 transport ID 和历史分析实际记录数量。
- `tests/test_reasoning_trace_report.py`：RT-12、Markdown/JSON、字段边界与转义。
- `tests/test_reasoning_trace_ui.py` / `tests/web_reasoning_runtime.cjs`：RT-13/14、计数、原生折叠、区域分离、历史/SSE/重置和 XSS。
- `tests/reasoning_helpers.py`：受控 LLM fixtures，不把 fixture 输出冒充真实模型结果。

基线：项目 `.venv` 下 `python -m pytest -q` → **393 passed in 51.24s**。
修改后全量：**420 passed in 54.20s**，无跳过。
前端独立命令 `cd web` / `npm test` 覆盖原有 20 项与新增 5 项 DOM 用例。
`git diff --check` 通过。缺少 Node/jsdom 时 DOM 用例会明确跳过，完整验收应先
`npm ci --ignore-scripts`，不能将跳过算通过。

## 四场景实际检查

2026-10-18 使用真实 tju-llm、Mock DNS 故障、临时账号/数据库，通过实际 API
连续执行四轮。关闭可选摘要，没有写入现有用户历史，没有检测天津大学内部平台。

| Case | intent | 网络调用 | 主 LLM 调用 | Trace 条数 | 实际结果 |
|---|---|---:|---:|---:|---|
| A：微信正常但网页打不开，完整排查 | diagnose | 4 | 5 | 15 | 有计划、证据、假设、继续/停止；模型最终整理失败，进入现有 finalization_failed 安全兜底，Trace 如实记录 fallback |
| B：基于刚才继续分析 | analyze_existing | 0 | 1 | 5 | 复用已有证据，正常完成 |
| C：整理成运维报告 | report_request | 0 | 1 | 5 | 不重测网络，正常完成报告整理 |
| D：刚才没有回答问题 | meta_feedback | 0 | 1 | 5 | 直接处理反馈，不重新诊断 DNS |

四轮使用同一持久化记录：四对完整 transcript、30 条累计 Trace，snapshot v4；
History、Markdown/JSON Report 与导出检查通过。A 的安全兜底不是一次正常模型
综合成功，也不代表新增 Trace 导致模型重试；这些都是原有诊断/兜底分支的真实结果。
Trace 不会为了符合示例而补造多域名异常，受控测试另行覆盖两个不同域名的 DNS 失败。

以上是隔离 API 实测及 DOM 自动验收，不是人工浏览器目视检查；没有生成新截图。
仍建议重启服务、Ctrl+F5 后，在浏览器重复 A～D，并检查展开状态、历史回放、
手机宽度及报告下载。上述单次模型运行不作为准确率或延迟 benchmark。
