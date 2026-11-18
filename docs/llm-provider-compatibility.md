# 模型服务兼容与知识回答验证

## 配置

只在服务端私有 `.env` 中配置模型服务。修改后重启 NetPilot。`LLM_API_BASE` 是 SDK 基础地址，不能包含 `/chat/completions`。

```dotenv
# DeepSeek 示例：填账号实际可用的模型，勿提交真实 Key。
LLM_PROVIDER=deepseek
LLM_API_KEY=填在本机
LLM_API_BASE=https://api.deepseek.com
LLM_MODEL=填写实际可用的模型标识
```

其他 OpenAI-compatible 服务使用自己的 `LLM_PROVIDER` 标识及配套地址、Key 和模型。TJU 也可以使用这四项：Provider 写 `tju`、地址填写比赛分配的地址、模型写 `tju-llm`。未设 `LLM_*` 时原有 `TJU_API_BASE`、`TJU_API_KEY`、`TJU_MODEL=tju-llm` 继续生效。非 TJU Provider 必须显式配置三项连接信息；换基础地址时不会继承原 TJU Key。现有 `TJU_TIMEOUT_SECONDS` 和 `TJU_MAX_RETRIES` 仍控制所有 Provider 的 HTTP 尝试。

`deepseek` 请求使用非思考模式，避免工具往返需要回传私有推理字段，也给最终正文保留输出预算。对任何 Provider 返回的 `reasoning_content`，只判断是否存在，不展示、不记录原文、不回传。在使用 DeepSeek 的第三方代理时，如果其接口只接受标准字段，可将 Provider 配置为自己的标识，以使用通用请求格式。参考 [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) 和 [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。

## 定位结果与行为变化

修复前用 OpenAI SDK 离线复现：仅有 `reasoning_content` 的 HTTP 200 响应和 HTTP 200 错误包均被归为 `LLMResponseError`，错误包中的 `code` 丢失；正常正文即使带 `[S1]`，也会被最终整理误判为缺少旧式标记并反复重试。当前工作区只有旧 TJU 配置，没有可用于实际 DeepSeek 验收的凭据，也没有原始失败请求的结构化记录。这些是已复现的代码缺陷，不能据此判断原先三次线上调用的 `finish_reason`、HTTP 状态、是否发生引用不匹配或是否存在 200 错误包。

知识问题仍先本地检索再整理，模型请求不携带工具。约定 `[S1]` / `【S1】` 等短引用，服务端只把本轮选中片段的编号转换成真实引用；旧 `[[cite:…]]` 继续受同一白名单限制。实质正文缺引用时正常返回，`citation_mode=source_panel_only`，网页与历史记录显示当轮检索结果并保留官方／社区／维护者标签；仅凭来源区不能推断任一段落由该来源支持。混合有效及无效标记时删除无效标记，记录 `citation_partial`；仅有无效标记时强化引用要求再试一次。模型正文禁止自行添加链接；主张仍由提示约束基于检索片段。

`length` 改用短片段重试；只有推理、空正文、工具请求、被中止或只列来源时，最多额外整理一次。`content_filter` 直接降级。普通的 HTTP 400 和 `model_not_found` 报参数兼容性问题并保留资料。HTTP 200 错误包保留实际状态及安全错误元数据；`server_error` 报模型服务失败，不能误判为检索或引用失败。实际 HTTP 429 仍由客户端按 `Retry-After` 及预算处理，整理层不再发起新的限流重试。

## 验证与排查

本地离线浏览器验收使用实际项目 FAISS 检索和固定模拟模型响应。三道问题分别新建会话；都先执行 `knowledge_search`，没有询问环境或调用网络检测。模拟 Provider 标识为 `deepseek`、模拟模型为 `fixture/browser-model`。每题使用一次整理、一次模拟 HTTP 请求，结束原因为 `stop`。

| 问题 | 第一次最终整理 | 第二次 | 网页引用行为 |
| --- | --- | --- | --- |
| eduroam 是什么？ | 正文与当前片段标记 | 未发起 | 行内引用与可展开的资料区指向 eduroam 社区资料 |
| 天津大学 VPN 怎么使用？ | 正文无引用，记录 `citation_missing` | 未发起 | 显示资料区，包含检索到的 VPN 社区资料 |
| VPN 客户端具体怎么安装？ | 正文与当前片段标记 | 未发起 | 行内引用与可展开的资料区指向包含客户端说明的 VPN 社区资料 |

`tests/test_llm_provider_compatibility.py` 额外用真实 SDK 加模拟 HTTP 响应验证：`[S99]` 两次均非法，记录 `citation_invalid` 并展示原始资料；第一次纯推理、第二次有效正文时恢复；HTTP 200 + `server_error` 和 HTTP 400 均记录 `model_request_failed`，并区分错误类型与用户提示。

最终回归：全量 `pytest` 1422 项通过（包含 TJU 旧配置、Function Calling、429、Chat/SSE、History、Report、Mock、RAG 和 Milestone 13 流程）；`npm test --prefix web` 138 项通过；`scripts/run_demo_scenarios.py` 的 6 个场景通过。当前私有 `.env` 的旧设置仍解析为 `tju` / `tju-llm`，未发送在线 TJU 或 DeepSeek 验收请求。

真实验收时在自己的 `.env` 配置 DeepSeek 后逐题新建会话，按同一 `request_id` 对照 `knowledge_finalization` 和（沿用事件名的）`tju_llm_request`。前者记录最终整理次数、Provider、模型、`finish_reason`、选中片段数量和长度、实质输出及引用计数；后者记录每次 HTTP 尝试与去敏后的 HTTP 状态、Provider 错误 code/type/request ID。`success=true` 和 `failure_kind=citation_missing` 同时出现表示正文已正常生成。日志不记录完整输入、片段、推理、凭据或 Provider 错误包。浏览器的 HTTP 200 或 SSE `complete` 不代表上游模型请求成功。

## 修改文件

- 配置与说明：`.env.example`、`README.md`、`docs/llm-provider-compatibility.md`、`src/netpilot/config.py`。
- Provider 与日志：`src/netpilot/llm/tju_client.py`、`src/netpilot/llm/errors.py`、`src/netpilot/llm/schemas.py`、`src/netpilot/privacy/logging.py`。
- 知识整理与上下文：`src/netpilot/agent/knowledge.py`、`src/netpilot/agent/orchestrator.py`、`src/netpilot/agent/prompts.py`、`src/netpilot/agent/fallbacks.py`、`src/netpilot/agent/schemas.py`、`src/netpilot/conversation_context/needs.py`。
- API、历史及界面：`src/netpilot/api/presenters.py`、`src/netpilot/api/routes.py`、`src/netpilot/history.py`、`src/netpilot/models/schemas.py`、`web/app.js`、`web/index.html`、`web/markdown.js`、`web/style.css`。
- 测试：`tests/test_llm_provider_compatibility.py`、`tests/test_agent_rag_scenario.py`、`tests/test_diagnosis_history.py`、`tests/test_knowledge_429_api.py`、`tests/test_knowledge_finalization.py`、`tests/test_netpilot_llm.py`、`tests/test_reasoning_trace.py`、`tests/test_tju_429_retries.py`、`tests/test_web_demo.py`、`tests/web_markdown_runtime.cjs`。
