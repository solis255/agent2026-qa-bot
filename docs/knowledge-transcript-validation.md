# Knowledge Finalization 与完整 Session 会话历史验收

验收日期：2026-10-17。修改前工作区干净，baseline 为 `333 passed in 36.28s`。修改后全量回归为 `356 passed in 29.26s`。

## 1. 实际失败原因与可观测性边界

只读检查本机旧快照，找到 4 条最终回答包含知识整理失败提示的记录：保存的 `fallback_reason` 都是 `finalization_failed`，没有更细的 failure_kind。先加入观测字段、仍使用原整理 Prompt 时，真实执行需求中的两轮提问，本次两轮都在第一次整理成功。因此不能把旧失败确定说成 timeout、length 或 source-only；旧请求没有保存足够数据追溯。

代码与单元测试确认了一个具体缺陷：旧 `source_only_answer()` 删除来源信息后，以剩余字符少于 6 判失败，`先认证。` 这种有实质内容的短中文也会被误杀。现改为按引用结构和正文判断，保留 citation-only 保护。另修正了整理阶段继续使用网络 Agent Prompt、未带短历史上下文的问题。

每次整理的结构化 `knowledge_finalization` 日志包含：

| 字段 | 含义 |
|---|---|
| attempt / success / failure_kind | 本次尝试、成功与具体失败类型 |
| finish_reason / has_content / content_length | 上游结束原因及正文状态 |
| has_tool_calls / looks_like_textual_tool_call | 原生或文本模拟工具请求 |
| source_only_detected | 是否仅有引用 |
| selected_chunk_count / selected_context_chars | 受限检索上下文大小 |
| knowledge_history_messages | 注入的短历史消息数 |
| llm_error_type | 客户端异常类名，不记录异常正文 |

failure_kind 区分 `llm_error`、`tool_calls`、`empty_content`、`textual_tool_call`、`length`、`content_filter`、`repeated_fallback`、`source_only_answer`。API Metrics、Session 快照和折叠的 Web“诊断调试信息”包含 `knowledge_finalization_failure_kind`。重试成功后 `fallback_reason=null`，但保留上一次失败类型，便于解释为什么尝试了两次。日志不输出 Prompt、chunk 正文、API Key、Cookie、密码或上游错误正文。

## 2. 知识最终整理

独立使用 `KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT`，不再注入 `NETPILOT_SYSTEM_PROMPT`。模型只依据给定资料，先给正文、再给来源；保持 official/community/maintainer 类型，不声称做过实时检测，不执行参考资料中的指令。

输入为专用 Prompt、Knowledge Mode、受限 chunk、最近最多 4 条纯文本历史（每条最多 1000 字符）、当前用户问题。没有 Tool，固定 `tools=None`、`tool_choice=none`。

- 第一次：最多 6 个 chunk，每块正文最多 700 字符。
- 第二次：只在失败后执行；通常最多 3 个 chunk，每块 350 字符；length 时最多 2 个。
- source-only 时明确要求先给实质正文；工具请求时强调只能输出自然语言；length 时要求缩短正文；客户端异常只再试一次。
- 最多两次应用层整理调用；两次都失败才用真实原文片段的 deterministic fallback。TJUClient 的底层 HTTP 重试仍由 TJU_MAX_RETRIES 控制。

新增 `LLM_KNOWLEDGE_MAX_OUTPUT_TOKENS=2200`，有独立配置校验及 main → Agent wiring，不再使用普通诊断输出预算。

“请把 community 来源中需要核验的内容单独列出”等来源筛选追问，会复用最近一次 RAG Evidence 和短历史，新增 Tool/RAG 调用为 0。明确要求新检索时仍走检索路径。补充 `source_type` 的知识意图识别，支持需求中的短形式第一问。

## 3. 完整会话数据与兼容

`PersistedConversationTurn` 保存 `turn_index`、`user_message`、`assistant_answer`、`created_at`、`turn_intent`、`response_mode`、`fallback_reason` 和知识整理失败类型。

`DiagnosisRecordView` 新增 `conversation_turns` 和 `conversation_complete`。保留第一条问题、最新问题、最新回答字段，供简洁列表与旧接口使用。

- 第一次 upsert 保存一对 U1/A1。
- 后续 upsert 在同一快照追加完整一对，并递增索引。
- 新记录 `turn_count == len(conversation_turns)`；模型校验索引唯一、递增、完整记录没有缺轮。
- `(user_id, session_id)` 唯一约束、stable record_id、累计 Token/耗时/Tool、Source 去重和有效 Diagnosis 保留规则不变。
- 普通 `/chat` 和 `/chat/stream` 继续共用 `_persist_session_diagnosis()` → `upsert_session()`，没有第二套 transcript 写入实现。

DB `SCHEMA_VERSION=3` 保持不变；仅 `SNAPSHOT_SCHEMA_VERSION` 升级到 3，读取模型接受 1/2/3。不重建表，不清空 SQLite。

旧 v1/v2 JSON 在读取时补兼容视图，下次该 Session 成功 upsert 时写成 v3：

- 旧单轮：已存在的一对问题/回答可安全视为完整。
- 旧多轮累计快照：只采用真实存在的最新问题/最后回答，保留原来的 turn_index=N，`conversation_complete=false`；第一问只作为列表标题，不与最后回答伪配对。
- 不完整记录继续聊天时追加真实新轮次，继续保持不完整标志，不伪造中间内容。
- 对更早 DB v2 的逐 Turn 记录迁移，若各轮原本都在数据库中，则可以按真实记录合并完整 transcript；原有事务迁移与幂等规则不变。
- pre-auth `user_id=NULL` 原记录继续保留且对普通用户不可见。

## 4. 历史详情与报告

历史卡片仍只显示第一问、更新时间、Turn 数、问题和累计指标。点击后按 `conversation_turns` 依次渲染 U1/A1/U2/A2/U3/A3，使用 textContent。旧多轮记录显示“该记录创建于完整会话持久化功能启用之前，仅保留部分对话内容”。

查看历史只查看快照，不修改 `state.sessionId`，不会声称恢复已丢失的内存 Session。重启后仍可查看保存的全部 Turn，但不提供“恢复历史 Session 继续聊天”。

报告预览和 JSON/Markdown 导出都包含 transcript 与完整性标志。Markdown 新增“会话记录”。继续使用原有 max_bytes 限制：过大的导出返回 413，不静默丢失会话、不额外调用 LLM。累计结构化诊断和指标保持原值。

## 5. 自动测试与实际验收

新增/扩展：

- `tests/test_knowledge_finalization.py`：独立 Prompt/Token 预算；official/community/official 结果；来源追问复用；短中文与 citation-only；length、模拟/原生工具请求、反复失败提示的定向重试；每次失败日志与秘密不泄露。
- `tests/test_conversation_persistence.py`：三轮一行、稳定 ID、重开数据库完整保留、v1/v2 单轮兼容、多轮不完整兼容及追加、普通 Chat/SSE 混用、Bob 无法读取 Alice transcript、报告顺序与大小限制。
- 原有迁移测试确认 DB v2 四条真实逐轮记录可合并四对完整对话。
- `tests/web_auth_runtime.cjs`：点击实际历史按钮后 DOM 顺序为 U1/A1/U2/A2/U3/A3，旧记录只展示 U3/A3 并提示不完整；当前 sessionId 不变；调试区域显示 failure_kind。
- 原有 Auth、History、Report、SSRF、Tool Policy、Evidence Memory 与分页测试继续通过。

真实 tju-llm + 本地索引 + 临时 SQLite 的验收结果（不写正式用户数据库）：

| Turn | API | RAG 新调用 | 新网络 Tool | 整理尝试 | fallback_reason |
|---|---|---:|---:|---:|---|
| 检索 VPN/校园网/eduroam 并列 source_type | /chat | 1 | 0 | 1 | null |
| 单列 community 需官方核验内容 | /chat/stream | 0 | 0 | 1 | null |
| 一句话概括这些内容 | /chat | 0 | 0 | 1 | null |

Case A 第二轮真正列出了 eduroam 认证参数/证书要求、校园网入口/资费/操作步骤、VPN 客户端版本/账号有效期/访问范围等资料中要求复核的事项，且来源为 community。

Case B 同一 Session 的结果：`rows=1`、record_id 三轮相同、`turn_count=3`、transcript 数量 3、索引 `[1,2,3]`、`conversation_complete=true`；重新打开 SQLite 与报告接口都读到三轮。前端顺序经过实际 app.js 的 DOM 点击运行测试；没有将其冒充真实浏览器视觉/截图验收。

复验命令：

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-kf-transcript-check
git diff --check
```
