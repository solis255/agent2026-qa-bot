# TJU NetPilot 设计说明

> 天津大学校园网络智能诊断与服务 Agent

本文描述 `agent2026-netpilot` 当前比赛版本的设计目标、关键取舍与边界。正式代码位于 [`src/netpilot/`](src/netpilot/)，实现细节和运行时流程见 [`docs/architecture.md`](docs/architecture.md)。

## 1. 设计目标

TJU NetPilot 的目标是把“用户描述网络现象”转换为“最少、只读、可审计的检测动作”，并基于结构化证据给出保守诊断。产品同时支持校园网服务知识问答，但不会把参考资料冒充实时网络证据。

本版本优先保证：比赛现场可复现、Tool 调用可解释、安全边界明确、依赖故障时可降级、诊断结果可回看和导出。它不以修改网络配置、代替人工运维或接入学校内部运维平台为目标。

## 2. 用户与场景

主要用户是遇到校园网接入、DNS、端口、HTTP、代理/VPN 或 eduroam 问题的师生，以及需要展示诊断过程的比赛评审。

核心场景包括：

- “能访问 IP 但打不开域名”的 DNS 定位；
- “网页正常但 SSH 失败”的 TCP 22 端口定位；
- 本地网卡、默认网关与基础公网连通性检查；
- HTTP/TLS/应用层与底层连通性的交叉验证；
- 校园 VPN、eduroam 等带来源的知识问答；
- 使用 Mock 场景稳定演示，或使用 Local Provider 检测运行 NetPilot 的主机。

## 3. 设计原则

1. **Evidence-first**：实时问题先取证再下结论；没有足够证据时明确说“不确定”。
2. **Least action**：只调用与现象直接相关的最少 Tool；普通知识问题不无意义调用网络 Tool。
3. **Read-only**：网络 Tool 只读取状态，不提供配置写入、重启或任意命令执行。
4. **Allowlist**：LLM 只能调用 `ToolRegistry` 注册的 allowlisted tools。
5. **Typed boundary**：输入、Tool 结果、API、历史快照与 RAG 元数据均使用明确 Schema。
6. **Source honesty**：官方、社区和维护者资料必须据实标记；当前内置知识材料是 community。
7. **Bounded execution**：Tool 轮次、超时、输出、消息、会话、历史和导出大小均有上限。
8. **Graceful degradation**：RAG、历史、系统命令或外部模型故障不应被掩饰或扩大。

## 4. Single Agent + Tools 的理由

当前任务链是线性的：理解问题、选择检测、收集证据、综合结论。一个 `AgentOrchestrator` 配合明确的 Tool Contract 足以覆盖这条链路，并保留完整的 assistant/tool 消息序列。相比引入更多自治角色，单 Agent 更容易限制 Tool 权限、关联 `tool_call_id`、控制轮次、复现实验和解释失败。

网络探测与知识检索的差异由 Tool 层处理，不需要为每类 Tool 创建独立 Agent。确定性诊断层还可以在模型最终输出异常时根据已收集证据生成安全 fallback。

## 5. 不使用 Multi-Agent 的当前理由

Multi-Agent 并非当前需求必要条件。现阶段没有需要并行自治协商、跨组织权限隔离或长期任务分工的业务流程；额外 Agent 会增加调用成本、状态协调、错误传播和审计复杂度，也会让“哪个角色有权调用哪个 Tool”更难验证。

未来只有在出现明确需求，例如独立的长时日志分析、不同权限域审批或多数据源并行取证时，才评估增加专门角色。评估标准是可衡量的任务收益，而不是架构形式本身。

## 6. 不强制 LangGraph 的理由

当前 Agent loop 只有少量明确状态：消息、Tool 轮次、已执行调用、来源、Token 与耗时。`AgentOrchestrator` 已以普通 Python 实现有界循环、重复调用抑制、失败 fallback 和历史注入，不需要额外工作流运行时。

不强制 LangGraph 并不否定图式编排。若后续出现可恢复的长事务、人工审批、复杂分支、并行节点或持久化执行图，再引入图框架会更有价值。现在保持依赖和状态面较小，更适合比赛交付。

## 7. Function Calling

`TJUClient.chat()` 调用 OpenAI-compatible Chat Completions，模型固定为 `tju-llm`，请求 `stream=false`。`ToolRegistry.schemas()` 生成原生 `type=function` 定义；严格模式会设置 `strict=true`、完整 `required` 字段和 `additionalProperties=false`。

模型返回原生 `tool_calls` 后，系统不解析自然语言中的伪 Tool 命令。每个调用必须命中注册名称，参数必须是 JSON 对象并通过相应 Pydantic 输入模型，随后才会执行 handler。结果以同一个 `tool_call_id` 作为 `role=tool` 消息回填模型。

## 8. Agent Tool Loop

`AgentOrchestrator.run()` 的核心流程是：

1. 组合系统提示、裁剪后的文本历史与当前用户消息；
2. 根据用户意图决定是否向模型提供 `knowledge_search`；
3. 将可用 Function schemas 发送给 `tju-llm`；
4. 若模型直接回答，则返回；若返回 Tool Calls，则逐个校验和执行；
5. 保存结构化 `AgentToolStep`，按 `tool_call_id` 回填 Tool 消息；
6. 根据新证据继续一轮模型调用或要求最终回答；
7. 达到 `MAX_TOOL_ROUNDS`、重复调用或模型异常时停止，并在已有证据允许时构造确定性 fallback。

一轮模型响应可以包含多个 Tool Call。相同 Tool/目标的重复检测会被去重，避免循环和无意义开销。

## 9. Evidence-first / 最小 Tool 调用

实时状态不能由语言模型记忆可靠得出。DNS、可达性、端口和 HTTP 等结论必须优先来自当前 Tool 证据；`resolved=false`、`connected=false` 等是“执行成功的异常观察”，不等同于 Tool 崩溃。

同时，取证不是越多越好。Agent 应从用户现象出发选择最小检测集，例如 SSH 单端口问题优先 `tcp_check`，DNS 现象用公网 IP Ping 与域名解析交叉验证。概念解释和普通知识回答允许直接作答；校园服务知识意图可启用 `knowledge_search`，但不应顺带运行无关网络探测。

## 10. Tool Registry

`ToolRegistry` 是模型与执行环境之间的强制边界。默认注册六个只读网络 Tool；仅当 Retriever 成功加载时注册 `knowledge_search`。未知名称返回 `unsupported`，非法 JSON、额外字段或越界值返回 `invalid_input`，handler 异常转换为安全的 `execution_error`。

Registry 对模型可见的是 Schema，对 handler 传入的是校验和归一化后的参数。它不暴露 Mock 场景切换、任意 Shell、文件系统、数据库写入或网络配置能力。

## 11. Mock / Local Provider

`MockNetworkProvider` 与 `LocalNetworkProvider` 都实现 `NetworkProvider`，通过 `NetworkToolService` 暴露相同的六个方法和统一 `ToolResult`。因此 Agent、Registry、API 和 Web 不需要知道 Provider 的内部实现。

- **Mock**：离线、确定性，支持六个内置场景和受开关保护的进程内自定义场景；不调用网络、Socket 或系统命令。
- **Local**：执行有界、只读的本机检查，支持 Windows、Linux 与 macOS；只检测运行 NetPilot 的主机及该主机到目标的路径，不代表远端浏览器设备，不登录网络设备，也不访问天津大学内部运维平台。

Mock 与 Local 必须继续共用 Tool Contract。新增 Provider 不应改变上层 Tool 名称或结果语义。

## 12. RAG

RAG 构建链路为：带 front matter 的 UTF-8 Markdown/TXT → `load_documents()` 校验来源 → `chunk_documents()` 确定性分块 → `FastEmbedProvider` 生成向量 → FAISS cosine index。运行时由 `FaissRetriever` 进行阈值过滤和 Top-K 检索。

每个结果保留 `title`、`source`、`source_type`、`file`、`chunk_id` 和 `score`。当前 `knowledge/raw/` 中校园网、VPN、eduroam 三份摘要全部来自 TJUBOT Wiki，标记为 `community`；Schema 虽支持 `official`，但不能把现有 community 材料改称官方资料。

RAG 文档是 **untrusted reference data**。检索文本不得覆盖系统指令、扩大 Tool 权限或自动触发命令；知识参考也不是当前连通性的实时证据。

## 13. Diagnosis / Evidence

`finding_status()` 将结果区分为 `normal`、`abnormal`、`error`、`inconclusive`、`blocked`、`reference`。`assess_diagnosis()` 再从结构化步骤生成主要问题、置信度、摘要、建议和限制。

这种分层防止三类误判：把网络负面观察当成执行失败；把 Tool 超时当成目标不可达；把 SSRF 阻止当成网站响应失败。若模型最终回答缺失或异常，`build_diagnostic_answer()` 可基于已有 Tool 步骤提供保守 fallback。

## 14. Session / History

`SessionStore` 与 SQLite Diagnosis History 解决不同问题：

- `SessionStore` 是进程内、有界、线程安全的对话上下文，只保存 user/assistant 文本；重启或场景清理后消失；同一会话一次只允许一个 active turn。
- `SQLiteDiagnosisRepository` 保存完成诊断的不可变结构化快照，包括问题、回答、诊断、指标、Tool Timeline 和来源；支持重启后读取、保留上限、游标分页和会话筛选。

历史写入失败不会回滚已经完成的聊天。持久化内容可能包含用户问题和网络证据，部署者必须设置路径权限、保留策略与备份策略。

## 15. SSE

`POST /api/chat/stream` 提供版本化 JSON-only SSE。服务先发送 `start`，后台线程执行与 `/api/chat` 相同的一次 Agent turn；等待期间可发送 keep-alive。完整结果产生后，答案按 `SSE_CHUNK_CHARS` 分块为 `delta`，最后发送包含完整 `ChatResponse` 的 `complete`；异常时发送安全 `error`。

这是 **transport-level SSE**，不是 `tju-llm` 的模型 token streaming。上游模型请求仍为 `stream=false`，delta 在完整 Agent/Tool 结果产生后才开始，且不会发起第二次模型请求。

## 16. 安全

- LLM 只能调用 allowlisted tools，所有输入拒绝未知字段并进行长度/范围校验；
- 六个网络 Tool 均只读，不存在网络配置写操作；
- Host/URL 规范化阻止命令元字符；子进程采用固定参数列表、`shell=False`、超时与输出上限；
- HTTP 仅允许 HTTP(S)，初始请求和每次重定向都检查解析地址，阻止 localhost、metadata、私网、回环与链路本地目标；
- API Key 使用 `SecretStr`，不进入健康响应、浏览器、诊断快照或结构化日志；
- Web 使用同源 API 与文本渲染，SSE 将不可信内容封装在 JSON data 中；
- 场景写操作仅在 Mock + 显式开关下开放，Local 模式拒绝；
- 日志记录请求/会话关联和安全错误类型，不记录聊天原文、Authorization 或 Tool 参数。

## 17. Graceful Degradation

- 未配置 `TJU_API_KEY`：应用与健康检查启动，聊天返回 503；
- RAG 索引缺失、损坏、模型不匹配或缓存不可用：`rag_ready=false`，不注册 `knowledge_search`，网络 Tool 继续可用；
- SQLite 初始化失败：`history_ready=false`，聊天继续；后续写入失败也不改变聊天结果；
- traceroute 命令不可用或 Tool 超时：返回 `inconclusive`，不伪造网络结论；
- 模型失败：无 Tool 证据时返回安全模型错误；已有证据时尽可能生成确定性 fallback；
- SSE 响应头发出后的异常：输出安全 `error` 事件，并释放 session busy 状态。

## 18. 测试

自动测试覆盖配置、TJU Client、Function Calling、Agent loop、多 Tool、轮次上限、Provider 契约、六个 Mock 场景、Local 解析、安全边界、RAG、会话、API、SSE、历史、报告、自定义场景和 Web 静态行为。

测试默认离线，使用 Fake LLM、Mock Provider、临时数据库或受控 monkeypatch，不把真实 TJU API 和现场网络作为稳定单元测试依赖。统一比赛验收映射见 [`docs/test-cases.md`](docs/test-cases.md)。模糊问题主动澄清目前没有可靠自动测试，明确列为 TODO。

## 19. 上游复用与原创改造边界

上游 Packt 项目提供书籍 Chapter/Lab、提示工程练习、Mock spine/leaf、Containerlab、MCP 示例、生产就绪模板与 MIT 许可基础。它们保留在 `labs/`、`lab/`、`examples/`、`bonus/`、`prompts/`、`docs/design-toolkit/` 等目录。

TJU NetPilot 的正式比赛产品位于 `src/netpilot/`，并配套 `web/`、`knowledge/`、相关 `scripts/` 与 `tests/`。比赛改造包括统一应用配置、`tju-llm` 客户端、原生 Function Calling、校园网只读 Tool Provider、证据诊断、RAG、Web/API、SSE、Session、SQLite History、报告与安全/测试体系。详细目录边界与 attribution 见 [`docs/upstream.md`](docs/upstream.md) 和 [`LICENSE`](LICENSE)。

## 20. 当前限制

- Local Provider 只能观察运行 NetPilot 的主机，无法直接检测另一台浏览器终端；
- 不接入天津大学内部网络运维平台、认证后台或设备遥测；
- 不修改 DNS、代理、网卡、路由器或任何网络配置；
- 当前内置 RAG 种子均为 community 摘要，不代表最新官方政策；
- SSE 不是模型 token streaming；
- SessionStore 不跨进程共享，SQLite History 也不是多节点协调服务；
- 诊断依赖用户提供足够目标信息，模糊问题主动澄清尚缺可靠自动验收；
- Mock 场景用于演示与测试，不能代表真实校园网络状态。

## 21. 后续演进

后续可按真实需求逐步加入：经审核的官方知识源及更新流程；更明确的澄清问题策略与自动测试；可选的真正模型 token streaming；带认证和权限隔离的部署；跨进程 Session/任务状态；更丰富但仍只读的数据源；OpenTelemetry 等标准观测；以及在确有并行或审批需求时评估图式编排或 Multi-Agent。

任何演进都应保持 allowlist、只读、来源诚实、实时问题 evidence-first 和 Mock/Local 共用 Tool Contract 这些基本边界。
