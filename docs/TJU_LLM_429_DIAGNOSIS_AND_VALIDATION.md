# TJU LLM HTTP 429：根因、验证与排查

2026-11-18；基线 main `27cb2c6`。本次修复 NetPilot 对限流的处理和知识问答的请求量。没有用真实 TJU 凭据请求模型，也未确认线上故障已恢复。

## 已确认的根因

旧客户端在所有 HTTP 429 响应上设置 `x-should-retry=false`，覆盖了 SDK 的默认策略，因此 `TJU_MAX_RETRIES=2` 对 429 没有效果。SDK 抛出 `RateLimitError` 后，客户端映射为 `LLMRateLimitError`；旧知识流程若在工具选择阶段失败，就直接调用本地知识库后降级；若在最终整理失败，则直接展示已有资料。旧测试覆盖了这两个提前降级分支。正常知识流程通常由一次模型选工具和一次模型整理组成。

实际收到的 HTTP 429 来自配置的上游端点或路径上的网关，并非环境采集、学生界面或 RAG 检索生成的状态码。NetPilot 的问题是过早停止和多发一次请求；单凭 429 或降级文案不能判断是上游限流窗口、并发、过载、额度还是代理限制。天津大学公开的 [API 使用指南](https://agent2026.tju.edu.cn/docs/API%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97) 与[竞赛 FAQ](https://agent2026.tju.edu.cn/ai-competition/introduction/docs/faq.html) 说明速率限制可返回 429，没有列出用来区分以上原因的结构化错误码。

## 修复后的行为

- 移除了 `_skip_rate_limit_retry`。验证环境使用 OpenAI SDK 2.54.0；为固定日志、等待预算及不同 429 的行为，**HTTP 重试统一在 TJU Client**，SDK 构造与注入的真实 SDK 实例都设置 `max_retries=0`。默认两次额外尝试，即每次模型调用最多 3 次 HTTP 请求；0 时只有首次。最终 429 交给 Orchestrator 降级，不再启动另一轮 HTTP 重试。
- 优先解析 `Retry-After`（秒数或 HTTP 日期），其次解析 `Retry-After-Ms`（毫秒）；负值与非有限值无效。未提供有效建议时从 0.5 秒起指数退避，基准上限 4 秒，使用最多 25% 的向下抖动。每次模型调用累计等待最多 10 秒；若服务端要求的等待超出剩余预算，直接返回错误，不提前发送下一次请求。单次 HTTP timeout 仍由 `TJU_TIMEOUT_SECONDS` 控制，与退避预算独立。沿用 5xx、408、409、超时及连接错误的有限重试类别；请求错误 400、认证/权限错误 401/403 不重试，尊重上游的显式重试拒绝。
- 只有 HTTP 429 且 SDK 解析到明确的 OpenAI 兼容 `error.code` / `error.type`（`insufficient_quota`、`quota_exceeded`、`billing_hard_limit`、`daily_quota_exceeded`）才判为可能额度耗尽并停止重试。这些是兼容令牌，不断言 TJU 一定发出它们。不根据错误正文或相似词推断；未知 429 记录为 `unknown_429`。
- `eduroam 是什么？`、`天津大学 VPN 怎么使用？` 和校园 IPv6 概念问题：知识意图 → 按当前问题脱敏、归一化查询（最多 500 字符）→ ToolPolicy/Registry → 带来源的本地资料 → 一次无工具的 Knowledge Finalization。普通独立问题不借用跨主题资料；同一规范化查询和明确的来源筛选追问可复用会话证据。History + RAG 的原 Function Calling 与近义去重和检索次数上限不变。没有查询改写模型调用、额外 Reasoning Summary、环境追问或网络工具。
- 持续 429 后如实际重试过，会明确提示已有限重试但没能整理答案；如果配额、重试配置为零或者等待预算阻止重试，不声称已重试。保留原文片段、有效行内引用及 `official/community/maintainer` 类型，原文不标为模型整理的结果。非 429 的整理失败用通用提示；超时、解析、格式和引用错误仍可按既有合成规则最多整理两次。没有可引用资料时返回 `insufficient_sources`，不调用模型补写校园政策，也不声称观测到了 429。

## 日志与运维

按时间和 NetPilot `request_id` 查询 `tju_llm_request`，再用 `provider_request_id` 对照上游日志（供应方未返回有效 ID 时为空）。每条记录包括模型、尝试序号、耗时、HTTP 状态、错误类型、安全 provider code、Retry-After、是否会重试及停止原因。NetPilot 的 HTTP 状态和上游模型状态是两件事：例如 SSE 可用 NetPilot HTTP 200 正常传输一个降级答案，具体上游状态看这条日志的 `status_code`。

| 现象 | 检查方式 |
| --- | --- |
| 确认收到上游 429 | 找 `status_code=429` 与对应时间、尝试序号和上游请求 ID；重试已用完时 `retry_stop_reason=attempt_limit`。 |
| 区分速率限制与额度耗尽 | 查明确 provider code、Retry-After、停止原因，并到 [TJU 智能体广场](https://ai.tju.edu.cn/) 确认同一时段的用量、额度及项目权限。缺少依据时保持 `unknown_429`，不把未知原因判成 RPM、TPM 等。 |
| 区分 TJU 与代理或网关的 429 | 与部署侧网关、代理和 TJU 方按时间与请求 ID 交叉核对。没有供应方 ID 不代表一定来自代理，收到 ID 也不能单独证明具体限额。 |
| 排除本地错误被误判 | 本地输入校验、连接/超时或响应解析错误不转成 429；对照 `error_type` 与实际上游状态。联系支持应提供时间、请求 ID 与安全错误码，勿提供凭据或完整报文。 |

异常保留 `status_code`、安全 request ID、`retry_after_seconds`、`provider_error_code`、`attempts_made`，不携带上游异常体。客户端成功结果提供 `attempts_made` / `retry_count`；每次 HTTP 尝试通过日志计数。现有 API Metrics 的 `knowledge_finalization_attempts` 仍指逻辑整理调用，不是 HTTP 请求数；`knowledge_finalization_failure_kind` 区分 `llm_rate_limited`、`llm_quota_exhausted` 和既有失败类别。保持旧 Metrics / SQLite 结构，学生页面不展示额外诊断指标。

## 测试和人工复测

浏览器连接隔离 localhost 实例、专用测试账号和数据库；FastAPI / Chat SSE / ToolRegistry / TJU Client / OpenAI SDK 走实际生产代码，仅用本地 fixture 和 HTTP MockTransport 代替资料索引及上游。未调用真实 TJU 端点，样例不用于核验真实资料质量。

| Case | 观察结果 |
| --- | --- |
| A · eduroam | 中文综合及一个可点击引用，日志 1 次 HTTP 200，无追问或检查按钮。 |
| B · 同会话 VPN | 针对 VPN 的中文综合和独立来源，日志另有 1 次 HTTP 200，未沿用 eduroam 资料。 |
| C · 429 → 200 | 日志同一 NetPilot 请求 ID 下有两次尝试；页面正常回答，无 429 降级。 |
| D · 连续 429 | 3 次 HTTP 后停止；页面明确已经重试、显示未整理的本地原文及引用。 |
| E · 明确配额错误 | 只有首次 HTTP，`provider_reason=quota_exhausted`；页面显示额度提示和原文。 |
| F · 之后恢复 | 同一会话再问 VPN，1 次 HTTP 200，正常综合，无永久失败状态。 |

浏览器截图：[`tju-llm-429-offline-check.jpg`](../screenshots/tju-llm-429-offline-check.jpg)。自动校验另覆盖无来源、同问题复用、IPv6、Chat/SSE、引用/来源类型、重试头、等待预算、日志不含响应体和密钥。

- 新增 36 个 pytest 用例：`tests/test_tju_429_retries.py` 23 项、`tests/test_knowledge_429_api.py` 9 项，现有整理测试补充非 429 解析与 400/401/403 共 4 项。原模型选择工具断言改为本地直接检索及单次无工具整理断言，未删掉业务边界。原批量 RAG 测试迁到仍使用该循环的 History + RAG 路径，验证去重和调用封顶。
- 最终全量 pytest：**1403 passed in 466.63s (0:07:46)**。定向复测 114 项通过；前端 137 项通过，Demo Runner 6 项通过，`git diff --check` 通过。浏览器验收完成后已关闭隔离服务与标签页。
- 最终自动验证命令：`python -m pytest -q --tb=line --basetemp=.cache/pytest-429-complete`、`npm.cmd test --prefix web`、`python scripts/run_demo_scenarios.py`、`git diff --check`。

## 修改范围

- 设置与客户端：`.env.example`、`src/netpilot/llm/{tju_client,errors,schemas}.py`、`src/netpilot/privacy/logging.py`。
- 编排与回答：`src/netpilot/agent/{orchestrator,intent,fallbacks,schemas}.py`。
- 回归：`tests/test_{tju_429_retries,knowledge_429_api,knowledge_finalization,netpilot_llm,agent_rag_scenario,context_acquisition,environment_profile_context,milestone10d,milestone7,target_tool_policy,tool_policy}.py`。
- 文档与验收：`README.md`、`docs/architecture.md`、本文件和浏览器截图。未改前端页面/样式、上传、Session ownership、Report 或 SSE transport。
