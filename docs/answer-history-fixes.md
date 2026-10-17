# 回答整理、持久化历史分析与分页修复

验收日期：2026-10-17。基于当前工作分支的 Session History v3；继续保证 `(user_id, session_id)` 唯一、稳定 record_id、累计 Turn/Token/Tool，以及 report/meta 不覆盖有效诊断。

## 根因与修复

1. RAG ToolResult / Evidence 已保留正文，但旧 Context Builder 主要注入引用，旧 knowledge fallback 只接收不含 content 的 KnowledgeSource；普通 Tool Loop 的最终整理失败后只列 URL。新增 `agent/knowledge.py` 共用受限片段提取，知识检索完成后显式进入 Tool-free Knowledge Finalization。
2. Agent 只有 Session 内的文本和 Evidence，没有当前账号的 SQLite 查询入口；涉及“区别”的历史请求还会误归类为 compare。新增 HISTORY_ANALYSIS / HISTORY 和 `history_context.py`，在普通 Chat 与 SSE 的共享服务端执行入口读取真实历史。
3. 前端把每批 cursor 结果追加到同一个列表。现改为上一页/下一页：每页 10 条，渲染时替换 DOM，并缓存每页的请求游标、结果及 next_cursor。

## Knowledge Finalization

```text
用户原问题 → knowledge_search → 保存带 content 的结构化 Evidence
  → 按相关度去重、最多 6 个 chunk，每块正文最多 900 字符
  → 新的整理请求：tools=None，tool_choice=none
  → 失败：最多 3 个 chunk，每块 400 字符，再整理一次
  → 再失败：输出受限原文片段、真实 source_type 和 URL，明确未完成综合整理
```

本 Turn 的新检索与明确复用的旧检索进入最终整理，不混入其它旧查询的片段。完整正文仍保留在结构化 Evidence；限制只用于模型上下文和降级展示。模型明确引用了某些资料时，返回的 Sources 优先采用这些实际引用；未给引用时补上提供给模型的参考来源。不会凭标题编造确定性知识总结。

`response_mode`、`fallback_reason`、`rag_calls`、`knowledge_finalization_attempts` 出现在 API Metrics、持久化快照和结构化日志中；每次整理失败都记录具体原因，最多两次应用层整理调用。上游 TJUClient 的 HTTP 重试仍由 TJU_MAX_RETRIES 控制。

只读检查本机旧快照时，相关 knowledge 记录中确实存在 `fallback_reason=finalization_failed`。没有对应截图的 record_id/request_id，不能把某一条记录精确认定为截图中的请求，也不能据此推断为 API timeout。

## 当前账号历史上下文

```text
FastAPI CurrentUser.id
  → _run_agent_turn()
  → parse_history_query()
  → HistoryContextService.query(user_id=服务端认证ID, query=...)
  → SQLite WHERE user_id=? AND primary_issue!='undetermined'
  → 有界 DiagnosisHistoryContextRecord
  → Agent HISTORY 分析
```

这不是模型 Tool。ChatRequest 不接受 user_id，模型没有选择或覆盖账号的入口。默认不运行任何 Tool；用户明确要求结合知识库时仅允许 knowledge_search，网络 Tool 仍被策略阻止。普通 Chat 与 SSE 使用同一绑定逻辑。

- “今天已有的三次诊断记录”：period=today、limit=3。
- “最近两次诊断”：period=recent、limit=2。
- “最近的诊断”：period=recent、limit=5。
- 查询硬上限 10 条；一个 Session 的多个 Turn 仍只算一条诊断。
- APP_TIMEZONE 默认 Asia/Shanghai；按该时区的午夜计算 UTC 半开区间，并以 Session 的 updated_at 判断当天活动。
- 纯知识问答、纯历史总结等没有有效 primary_issue 的 Session 不计入诊断比较。

上下文包含 record/session ID、创建/更新时间、turn_count、第一条和最新问题、primary_issue、confidence、诊断摘要、建议、关键工具参数/状态/受限事实、来源及累计 Token。默认 5 条、最多 10 条，按异常优先选取关键证据，正文与列表均有长度上限，不注入完整 SQLite snapshot。

数量不足时，服务端先给出实际数量，再分析现有记录；零条明确说明没有记录；数据库不可用与零条分别处理。模型失败时展示已有结构化诊断和建议，不要求用户重复复制数据库已有内容。

## Cursor 页面缓存

`historyPageIndex` 从 0 开始，`historyPages` 保存 `{requestCursor, items, nextCursor}`。下一页用当前页的 next_cursor 请求；上一页直接渲染已缓存结果，不需要 reverse cursor 或 OFFSET。每次 render 都替换当前列表，DOM 只保留本页条目。

首页禁用上一页，末页禁用下一页，请求期间两边禁用。刷新、诊断保存、退出和账号切换会丢弃旧缓存并回到首页。authEpoch 和 historyGeneration 同时阻止跨账号或过期请求回填数据。列表另有高度限制作为显示防护。

## 验收

修改前 baseline：298 passed。Windows 沙箱曾使临时认证数据库返回 503；在允许访问测试临时目录的执行环境中重复 baseline 后全绿。

原修复全量回归：`315 passed in 28.09s`；补充知识库比较路由修复后：`333 passed in 30.39s`。`git diff --check` 通过。

本次修改文件：新增 `src/netpilot/agent/knowledge.py`、`src/netpilot/history_context.py`、`tests/test_knowledge_finalization.py`、`tests/test_history_context.py` 和本文档；修改 Agent 的 `orchestrator.py`、`fallbacks.py`、`intent.py`、`response_modes.py`、`tool_policy.py`、`schemas.py`、`context_builder.py`、`evidence.py`；修改 API 的 `routes.py`、`presenters.py`、公共 `models/schemas.py`、`history.py`、`config.py`；适配 `web/index.html`、`web/app.js`、`web/style.css`；补充 `.env.example`、`requirements.txt`（Windows 所需 tzdata）与 README/DESIGN/architecture 说明。相关现有 RAG/History/Web 测试已同步。此前已存在的 Session History 改动继续保留。

自动测试文件：

- `tests/test_knowledge_finalization.py`：三种来源类型、正文有界、整理成功、一次重试、两次失败的原文降级，以及 llm_error / invalid_tool_loop / finalization_failed 的准确记录。
- `tests/test_history_context.py`：历史意图优先级、中文/数字数量、上限、上海午夜边界、同 Session 去重、用户隔离、普通/SSE 读取三条真实临时 SQLite 记录、零条/不足/模型失败。
- `tests/web_auth_runtime.cjs`（由 pytest 调用）：25 条历史翻页 DOM 数量 10→10→5→10、上一页缓存、刷新回首页、请求中禁用、退出与换账号清缓存、防止迟到响应泄露前账号数据。
- 原有 Auth/History/Migration/Report/Tool/SSRF/Evidence Memory 测试继续运行。

2026-10-17 的实际 smoke 结果：

| Case | 数据与模型 | 结果 |
|---|---|---|
| VPN/RAG | 本地真实 FAISS 索引 + 配置的真实 tju-llm | 完整使用回答与 official/community 来源；rag_calls=1，knowledge_finalization_attempts=1，fallback_reason=null，Network Tool=0 |
| 历史比较 | 临时 SQLite 中 DNS/Gateway/SSH-TCP 三个 Mock 诊断 Session + 真实 tju-llm | 返回逐项现象、工具证据、故障层次、建议与对比；history_context_records=3，Network Tool=0，RAG=0，fallback_reason=null |
| 分页 | 实际 web/app.js 的 Node DOM 运行测试，25 条受控记录 | 每页 10/10/5，返回上一页 10；没有 20/30 条的累加 |

上述 smoke 不修改正式用户数据库。真实浏览器中视觉布局与交互仍可按三个 Case 进行人工复核；这里不把 Node DOM 测试称为浏览器截图验收。

复验命令：

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-answer-history-check
git diff --check
```

## 知识库比较请求的后续修复

用户反馈“由于当前处于比较模式，我无法调用 knowledge_search”。根因为 compare 的关键词分支先于 knowledge_request；“比较/区别”甚至“还是请检索知识库”都会先命中比较模式，并被正确执行的 ToolPolicy 禁止检索。

现在明确的资料/知识检索请求优先于普通比较；校园 VPN/eduroam 等知识性比较也进入 knowledge_request，只允许 knowledge_search，随后仍走 Knowledge Finalization。单纯比较已有 Evidence 继续零 Tool；明确“不需要检索知识库”会被尊重。历史分析仍优先使用当前用户持久化上下文，只有明确要求资料检索时才开放 RAG；报告和元反馈保持零 Tool。引用了校园网/VPN 的已有证据分析也不会仅因主题词而改为检索。

新增 18 项回归覆盖上述优先级、否定检索、history/report/meta 保护，以及端到端知识比较调用。真实 tju-llm + 本地知识库验证“请检索知识库，比较天津大学 VPN 和 eduroam 的用途与使用条件，标注来源。”：intent=knowledge_request、response_mode=knowledge、rag_calls=1、network_tool_calls=0、knowledge_finalization_attempts=1、fallback_reason=null，返回实际对比和 3 个引用，无比较模式拒绝。
