# 项目代码导航与文件职责说明

> 最后扫描：2026-08-26
> 扫描范围：仓库中除 `.git/`、虚拟环境和缓存外的项目文件。
> 用途：后续修改前先查本文的“按需求快速定位”和对应目录，只有在职责或依赖不明确时再做局部扫描。

## 1. 项目概览

这是《Building AI Agents for Network Operations》的配套教学仓库，主线是：

```text
TJU API 基础与结构化解析
  -> RACE 提示工程
  -> 有/无记忆聊天机器人
  -> Agent 工具调用与故障排查
  -> MCP 工具复用和浏览器 UI
  -> 生产安全、审计与后端抽象
```

主要运行时是 Python 3.10+ 与学校提供的 TJU 比赛 API，模型标识为 `tju-llm`。正式产品位于 `src/netpilot/`，通过 FastAPI 同源提供 `/api/health` 和 `web/` 中文页面，并初始化 Milestone 5 `TJUClient`、`ToolRegistry`、`AgentOrchestrator`、本地 FAISS Retriever 以及由 `TOOL_MODE` 选择的统一 Mock/Local 只读网络 Tool 层；应用启动不发起模型下载，RAG 不可用时安全降级。Lab 1～4 仍共用 `examples/tju_llm_client.py`；Lab 5～6 不直接调用 LLM。大多数示例默认使用模拟设备；真实设备示例使用 Netmiko。

## 2. 按需求快速定位

| 要修改的内容 | 首选位置 | 经常需要联动检查的位置 |
|---|---|---|
| NetPilot 配置、启动或健康状态 | `src/netpilot/config.py`、`src/netpilot/main.py` | `.env.example`、`src/netpilot/api/routes.py`、`tests/test_netpilot_config.py`、`tests/test_netpilot_api.py` |
| NetPilot API schema 或路由 | `src/netpilot/models/schemas.py`、`src/netpilot/api/routes.py` | `web/app.js`、API 测试、README |
| NetPilot 中文 Web 页面 | `web/index.html`、`web/app.js`、`web/style.css` | `src/netpilot/main.py` 的静态目录挂载、API schema |
| NetPilot Tool contract、参数或结果 | `src/netpilot/tools/schemas.py`、`validation.py` | Provider、Service、三组 Tool 测试、README |
| NetPilot Mock 故障场景 | `src/netpilot/tools/mock_network.py` | `src/netpilot/config.py` 的 `MockScenario`、`tests/test_mock_scenarios.py` |
| NetPilot 本机只读检测 | `src/netpilot/tools/local_network.py` | `service.py`、`requirements.txt`、Tool/安全测试 |
| 模拟设备、接口/BGP 故障场景 | `examples/mock_network_devices.py` | `labs/lab4-agentic/live_network_devices.py`、Lab 3/1 内嵌的 mock 数据、相关文档示例 |
| 正式 NetPilot TJU Chat、错误或结果 | `src/netpilot/llm/`、`src/netpilot/config.py` | `src/netpilot/main.py`、`tests/test_netpilot_llm.py`、`scripts/test_tju_api.py` |
| 正式 NetPilot Agent 编排与工具注册 | `src/netpilot/agent/` | `src/netpilot/llm/`、`src/netpilot/tools/`、三组 Agent 测试、`scripts/test_netpilot_agent.py` |
| NetPilot 知识加载、索引与检索 | `src/netpilot/rag/`、`knowledge/raw/` | `scripts/build_knowledge_index.py`、`tests/test_rag_*.py`、ToolRegistry、Agent prompt |
| Lab 1～4 TJU API 地址、模型或生成参数 | `examples/tju_llm_client.py`、根目录 `.env` | `.env.example`、`README.md`、`QUICKSTART.md` |
| JSON 结构化输出与验证 | `labs/lab2-prompts/prompt_engineering_race.py` | Lab 1 各 parser、`docs/design-toolkit/structured-output-validation.md` |
| RACE 提示词 | `prompts/race_network_analysis_prompt.txt` 或 Lab 2 | `labs/lab2-prompts/PROMPT_TEMPLATES.md`、`docs/design-toolkit/race-prompt-worksheet.md` |
| 聊天记忆 | `labs/lab3-chatbot/chatbot_v2_with_memory.py` | `chatbot_v3_live_ssh.py`、Bonus Lab 两个 `server.js` |
| Mock Agent 工具或调度循环 | `labs/lab4-agentic/agentic_network_bot.py` | `examples/mock_network_devices.py`、兼容入口 `agentic_network_bot_ollama.py` |
| TJU API 原生 Function Calling | `labs/lab4-agentic/agentic_network_bot.py` | `lab4b_agentic_network_bot_netmiko.py`、`examples/tju_llm_client.py` |
| 真实 SSH Agent、安全命令过滤 | `labs/lab4-agentic/lab4b_agentic_network_bot_netmiko.py` | `.env.example`、Containerlab 配置 |
| MCP 对外工具名称或参数 | `labs/lab5-mcp/mcp_server.py` | `network_tools.py`、`http_bridge.py`、`ui.html`、测试 |
| MCP 工具业务逻辑/设备校验 | `labs/lab5-mcp/network_tools.py` | `examples/mock_network_devices.py`、`tests/test_command_safety.py` |
| Lab 5 浏览器页面 | `labs/lab5-mcp/ui.html` | `http_bridge.py` 的 HTTP 路由与端口 |
| 生产策略、审计、命令白名单 | `labs/lab6-production-readiness/safe_tools.py` | `production_checklist.md`、design toolkit |
| Mock/真实后端接口 | `labs/lab6-production-readiness/production_agent_skeleton.py` | 真实设备适配器与统一结果 schema |
| Containerlab 拓扑/节点 | `lab/topology.clab.yml` | `lab/configs/*.cfg`、README 拓扑说明、脚本设备清单 |
| 安装依赖或运行命令 | `requirements.txt`、`Makefile` | `README.md`、`QUICKSTART.md` |
| 测试命令安全 | `tests/test_command_safety.py` | Lab 5 `network_tools.py`；Lab 4B 有另一套独立安全逻辑 |
| Bun Web 聊天/RACE 构建器 | `bonus/lab-bun-chat/server.js` | `bonus/lab-bun-chat/solution/server.js`、Bonus README |

## 3. 关键调用链与数据源

### 3.1 NetPilot 正式应用链

```text
浏览器 / Web
  -> FastAPI src/netpilot/main.py
  -> src/netpilot/api/routes.py
  -> Settings / TJUClient / ToolRegistry / AgentOrchestrator / Retriever / NetworkToolService
```

`create_app()` 不发起外部请求，允许未配置 API Key 时启动。TJU SDK transport 只在存在 Key 时创建，并在应用 lifespan 结束时关闭；真正的网络请求只由 `TJUClient.chat()` 发起。`/api/health` 仅公开布尔就绪状态、Tool 模式和服务状态；静态页面通过同源 `/api/health` 获取这些字段。

### 3.2 NetPilot Tool 调用链

```text
ToolRegistry / 其他受信调用方
  -> NetworkToolService
  -> MockNetworkProvider 或 LocalNetworkProvider
  -> 统一 ToolResult + typed data
```

Provider 在 FastAPI 应用创建时根据 `TOOL_MODE` 选择，但初始化阶段不执行探测。Mock 完全离线且提供六种场景；Local 使用 psutil、dnspython、socket、httpx 和固定参数的系统 ping/traceroute，所有入口先经过 Pydantic 与安全目标校验。

### 3.3 NetPilot 正式 Agent 与 TJU 调用链

```text
AgentOrchestrator
  -> TJUClient（messages + native function schemas）
  -> tju-llm tool_calls
  -> ToolRegistry（白名单 + Pydantic 参数校验）
  -> NetworkToolService（Mock 或 Local）
  -> role=tool + tool_call_id 回传 tju-llm
  -> AgentResult（最终回答 + 工具时间线）
```

Milestone 4 使用非流式原生 Function Calling，支持同一响应内的多个工具调用并保留精确 `tool_call_id`。工具只来自六项只读白名单，参数错误会作为结构化失败回传模型；循环默认最多执行六轮。普通 Chat 继续兼容，测试通过 Fake LLM/Mock SDK 保持离线，独立脚本负责真实模型验收。

### 3.4 NetPilot RAG 调用链

```text
knowledge/raw 中带来源的 Markdown/TXT
  -> loader + deterministic chunker
  -> FastEmbed BGE-small-zh-v1.5
  -> FAISS index + chunks metadata + manifest
  -> FaissRetriever
  -> ToolRegistry knowledge_search
  -> AgentResult.sources + 带原始 URL 的最终回答
```

索引构建脚本是唯一允许下载 Embedding 模型的正式入口；应用只使用本地缓存。索引缺失、损坏、模型不匹配或缓存不可用时 `rag_ready=false`，并且不注册 `knowledge_search`。当前种子资料是从北洋维基页面整理的社区测试摘要，必须与天津大学官方现行规定区分。

### 3.5 Lab 1～3 模型调用链

```text
Lab 1～3 入口脚本
  -> examples/tju_llm_client.py
  -> OpenAI SDK Chat Completions
  -> TJU_API_BASE（比赛专属地址）
```

凭据只由共享客户端从根目录 `.env` 或进程环境读取。修改鉴权、超时、错误映射或 token 展示时只需优先修改共享客户端并扩展 `tests/test_tju_llm_client.py`。

### 3.6 TJU API 原生工具调用链

```text
labs/lab4-agentic/agentic_network_bot.py
  -> examples/mock_network_devices.py
  -> examples/tju_llm_client.py（tools 字段）
  -> TJU API
```

`agentic_network_bot_ollama.py` 仅为旧路径兼容启动器。Lab 4B 沿用同类循环，但把工具实现替换成真实 Netmiko SSH。工具结果必须携带对应 `tool_call_id`，默认最多六轮。

### 3.7 MCP 与浏览器链

```text
labs/lab5-mcp/ui.html
  -> HTTP :8765
  -> http_bridge.py（MCP Client）
  -> MCP/SSE :8000
  -> mcp_server.py
  -> network_tools.py
  -> examples/mock_network_devices.py
```

若修改工具名或参数，必须自右向左检查整条链；只改 MCP server 会造成 UI 或 bridge 路由不匹配。

### 3.8 生产安全链

```text
Agent/调用方
  -> SafetyPolicy / backend contract
  -> mock 或未来真实后端
  -> 统一 ToolResult / 审计事件
```

`safe_tools.py` 展示策略与审计，`production_agent_skeleton.py` 展示后端抽象；二者是互补示例，目前没有合并为一套完整生产框架。

## 4. 已知边界、差异与维护风险

1. **存在三套拓扑口径。** `examples/mock_network_devices.py` 是 2 spine + 2 leaf；`lab/topology.clab.yml` 是 1 spine + 2 leaf；部分 SSH 脚本又内嵌 4 台设备配置。修改拓扑时不要默认它们会自动同步。
2. **`scripts/02_inventory_loader.py`、`03_connect_to_device.py`、`04_get_interfaces.py` 引用缺失文件** `mcp_server/inventory.yml`。当前仓库没有 `mcp_server/` 目录，这三个目标和 Makefile 的 `inventory`/`version`/`interfaces` 入口会因此失败，除非补回清单或改为现有数据源。
3. **凭据仅适合教学环境。** 多个 Lab 和 Containerlab 配置中硬编码 `admin/admin`。接入真实网络前应改用环境变量或 secrets manager，并使用只读、最小权限账号。
4. **命令安全实现不统一。** Lab 5 只检查命令以 `show` 开头；Lab 4B 还检查阻断词、危险 show 模式和目标格式；Lab 6 使用白名单。生产改动应以更严格的 Lab 4B/Lab 6 思路为基线。
5. **自动测试覆盖仍有限。** 现有测试已覆盖 NetPilot Settings/health/静态页面、六个网络 Tool、六种 Mock 场景、跨平台命令构造、SSRF/注入边界、TJU 客户端、Agent 多轮、RAG 加载/切块/FAISS/检索、知识工具和来源聚合；尚未自动化覆盖真实 API 稳定性、MCP 传输、真实 SSH 或 Lab 6 策略。真实 Agent 与 RAG 分别由两个独立脚本手工验收。
6. **文档中有教学草稿痕迹。** Lab 3 的大写扩展名 `.MD` 文档很长，包含代码逐段讲解；其中个别示例文件名与实际脚本名不同。以当前代码文件名为准。
7. **Bonus README 与主实现存在演进差异。** README 描述“四个 TODO、端口 3000”的入门任务；根 `server.js` 已发展为端口 3003 的完整 RACE Prompt Builder，`solution/server.js` 才是较精简的端口 3000 解答版。
8. **`config.txt` 是独立的 BGP 安全配置样例**，当前没有代码直接读取它；其中仍有占位符 `<LOCAL_AS>` 和示例口令字段。
9. **历史文件名仍包含 Ollama。** `labs/lab1-ollama/` 与 `agentic_network_bot_ollama.py` 为兼容旧教材路径而保留，内部已使用 TJU API。
10. **模型 API 是 Lab 1～4 的运行前置条件。** 需有效的比赛 Key、专属地址和网络连接；真实 SSH 版本还需可达设备与 Netmiko。

## 5. 逐文件职责说明

### 5.1 仓库根目录

| 文件 | 作用与修改提示 |
|---|---|
| `.env.example` | TJU 比赛 API、NetPilot Agent/Tool/RAG/App 以及上游 Claude、网络和 MCP 变量模板；新增环境变量时同步这里与相关 README。 |
| `.env` | 本地运行配置与密钥文件，已被 Git 忽略；`TJU_API_KEY` 只允许填写在这里或进程环境变量中，不得提交。 |
| `.gitignore` | 忽略 Python 构建物、虚拟环境、凭据、日志、测试缓存和 Containerlab 产物；有少量重复规则但不影响效果。 |
| `README.md` | 项目总入口：章节映射、安装、六个 Lab、拓扑、安全边界和故障排查。改变目录、模型或主运行命令时必须同步。 |
| `QUICKSTART.md` | 五分钟快速启动路线和最短实验路径；比 README 更面向首次运行者。 |
| `CONTRIBUTING.md` | 贡献流程、PEP 8/类型提示要求、测试建议和优先改进方向。 |
| `LICENSE` | MIT 许可证文本。通常不参与代码修改。 |
| `requirements.txt` | 全仓 Python 依赖：OpenAI/Anthropic、FastAPI/Pydantic、网络检测、FastEmbed/FAISS/NumPy 本地 RAG、Netmiko、MCP、Uvicorn 和 pytest。 |
| `pyproject.toml` | NetPilot 的 setuptools `src` 布局与 editable install 元数据；依赖继续以 `requirements.txt` 为单一清单。 |
| `REQUIREMENTS_TJU_NetPilot_Codex.md` | TJU NetPilot 比赛项目的需求、架构约束、里程碑与验收标准；正式应用开发以此为产品目标。 |
| `Makefile` | setup、Containerlab、基础脚本、Claude、MCP 和 pytest 的快捷命令；其中三个设备脚本依赖当前缺失的 inventory。 |
| `config.txt` | Cisco 风格的 eBGP 入站过滤、会话认证、最大前缀与 peer policy 配置样例；不在运行调用链中。 |
| `ai-networking-workshop-home.jpeg` | 1920×1278、约 290 KiB 的仓库/Workshop 首页图片资源；当前 Markdown 未直接引用。 |
| `PROJECT_CODE_MAP.md` | 本文件；新增、删除、重命名文件或改变核心调用链时更新。 |

### 5.2 `src/netpilot/`：正式 NetPilot 应用

| 文件 | 作用与修改提示 |
|---|---|
| `src/netpilot/config.py` | 使用 Pydantic Settings 读取根 `.env`，校验 TJU、Agent、Tool、RAG、App 配置；API Key 使用 `SecretStr` 且允许缺失启动。 |
| `src/netpilot/main.py` | FastAPI 应用工厂和正式入口；创建 TJUClient、网络 Tool、可选 Retriever、ToolRegistry 与 AgentOrchestrator，并准确设置 `rag_ready`。 |
| `src/netpilot/api/routes.py` | 当前提供 `/api/health`，只返回公开的布尔/枚举状态，不返回凭据。复杂 Agent 逻辑不得写入此层。 |
| `src/netpilot/models/schemas.py` | 正式 API Pydantic schema；当前定义 `HealthResponse`，后续按 Milestone 增加会话和诊断模型。 |
| `src/netpilot/llm/base.py` | Agent 依赖的 provider-neutral `LLMClient` Protocol，便于 Fake LLM 测试。 |
| `src/netpilot/llm/schemas.py` | 普通消息、assistant tool calls、tool result 消息、token 用量与稳定 `ChatResult`，不暴露 SDK 响应对象。 |
| `src/netpilot/llm/errors.py` | 未配置、请求、认证、限流、超时、连接、服务和异常响应的安全错误层。 |
| `src/netpilot/llm/tju_client.py` | 正式 TJU OpenAI-compatible Chat Completions 客户端；支持普通 Chat 和原生 Function Calling，配置 timeout/有限 retry，支持 Mock SDK 注入，校验响应并记录耗时。 |
| `src/netpilot/agent/prompts.py` | 证据优先、只读、来源区分、RAG Prompt Injection 防护和禁止重复检测的系统提示词。 |
| `src/netpilot/agent/schemas.py` | `AgentResult`、状态、token、工具证据时间线与结构化知识来源 schema。 |
| `src/netpilot/agent/tool_registry.py` | 六个网络工具及可选 `knowledge_search` 的严格 schema、白名单分派、参数校验与安全失败转换。 |
| `src/netpilot/agent/orchestrator.py` | 有界 messages → tool_calls → tool results → answer 循环，支持多调用并安全处理 LLM 错误和最大轮次。 |
| `src/netpilot/tools/schemas.py` | 六个工具的 Pydantic 输入/数据模型、稳定错误码与泛型 `ToolResult`；负面网络观察与工具执行错误分开表达。 |
| `src/netpilot/tools/validation.py` | Host/Domain/URL 的集中校验以及 HTTP localhost、metadata、内网和非公网地址阻断。 |
| `src/netpilot/tools/base.py` | Mock/Local 共用的 `NetworkProvider` 接口、耗时统计、参数失败与异常捕获边界。 |
| `src/netpilot/tools/mock_network.py` | 面向终端用户的六个完全离线故障场景；不复用 spine/leaf/BGP 产品语义。 |
| `src/netpilot/tools/local_network.py` | 本机接口/网关/DNS、Ping、DNS、TCP、HTTP 和 traceroute 的跨平台只读实现，含 timeout、输出上限、重定向与 SSRF 基础防护。 |
| `src/netpilot/tools/service.py` | 按 Settings 创建 Provider 并提供稳定委托接口；预留内部 Mock 场景切换，不提前公开 HTTP API。 |
| `src/netpilot/rag/loader.py` | 限量扫描 Markdown/TXT，要求 YAML 来源元数据并阻断符号链接、越界与超大文件。 |
| `src/netpilot/rag/chunker.py` | 中文友好的确定性重叠切块，并为每块生成稳定 ID。 |
| `src/netpilot/rag/embeddings.py` | 延迟加载的 FastEmbed 中文 BGE Provider，以及仅供离线测试的确定性 Hash Embedding。 |
| `src/netpilot/rag/index.py` | FAISS cosine 索引构建、原子文件替换、chunk 元数据和 manifest 完整性校验。 |
| `src/netpilot/rag/retriever.py` | Top-K、最低分数过滤、来源保留及应用本地只读加载工厂。 |

### 5.3 `web/`：正式中文 Web 壳

| 文件 | 作用与修改提示 |
|---|---|
| `web/index.html` | 中文单页结构，包含聊天、服务概览、Tool Timeline 和知识来源占位区；不保存 Key。 |
| `web/app.js` | 同源读取 `/api/health` 并渲染后端、LLM、RAG 和 Tool 模式状态。 |
| `web/style.css` | 桌面优先且支持窄屏的页面样式。 |
| `web/favicon.svg` | NetPilot 本地矢量页签图标，避免页面依赖外部图片资源。 |

### 5.4 `examples/`：共享模拟数据与小型示例

| 文件 | 作用与修改提示 |
|---|---|
| `examples/mock_network_devices.py` | **最重要的共享 mock 数据源。** 定义四台设备、leaf2 的 BGP Idle 和 Ethernet3 down 场景，并提供设备、接口、BGP、ping、只读命令、拓扑函数。Lab 4、5、6 直接依赖它。 |
| `examples/tju_llm_client.py` | **Lab 1～4 共用模型入口。** 读取并校验 `.env`，创建 OpenAI 客户端，统一文本/多轮/Function Calling、token 展示和安全错误信息。 |
| `examples/test_setup.py` | 离线检查 Python、TJU 配置字段和六个 Lab 入口；隐藏 API Key，不消耗 token。 |
| `examples/temperature.py` | 通过共享 TJU 客户端演示 temperature=1.5。 |
| `examples/tokens_test.py` | 发送最短响应并读取比赛 API 返回的 prompt token 用量；只在 main 下调用服务。 |
| `examples/interface_output.json` | leaf1 `show interfaces status` 的示例输入，供 Claude/RACE 分析脚本使用。 |
| `examples/bgp_output.json` | leaf1 `show ip bgp summary` 的示例输入。 |
| `examples/claude_response_example.md` | 对 interface 示例数据的期望 Claude 分析输出，展示固定章节结构和“缺失数据”表达。 |

### 5.5 `scripts/`：章节前置与外部 API/SSH 脚本

| 文件 | 作用与修改提示 |
|---|---|
| `scripts/01_python_basics.py` | 面向网络工程师的 Python 字典、列表、循环和函数入门；`build_show_command()` 是最小示例。 |
| `scripts/02_inventory_loader.py` | 用 PyYAML 读取设备 inventory 并打印清单；目前指向不存在的 `mcp_server/inventory.yml`。 |
| `scripts/03_connect_to_device.py` | 从同一缺失 inventory 获取 Netmiko 参数，对指定设备执行 `show version`；包含认证、超时和未知设备处理。 |
| `scripts/04_get_interfaces.py` | 通过 Netmiko 获取 `show interfaces status`，封装为 device/command/output JSON；同样依赖缺失 inventory。 |
| `scripts/05_claude_race_analysis.py` | 读取 RACE system prompt 和输入文件，调用 Anthropic Messages API；使用 `.env` 的 API key/model，默认输入示例为 `examples/interface_output.json`。 |
| `scripts/test_tju_api.py` | 通过正式 `Settings` 与 `TJUClient` 发送最小在线请求；不会输出 API Key，展示安全错误、token 用量和耗时。 |
| `scripts/test_netpilot_agent.py` | 以真实 `tju-llm` 和离线 `dns_failure` Mock 验收完整 Function Calling 链，不探测本机网络。 |
| `scripts/build_knowledge_index.py` | 从 `knowledge/raw` 构建 BGE + FAISS 本地索引；首次允许下载，支持 `--offline`。 |
| `scripts/test_netpilot_rag.py` | 以真实 `tju-llm` 验收 `knowledge_search`、社区来源标识、URL 引用和结构化 sources。 |

### 5.6 `prompts/`：外置提示词

| 文件 | 作用与修改提示 |
|---|---|
| `prompts/bad_prompt.txt` | 故意模糊的单句提示，用作结构化提示的反例。 |
| `prompts/race_network_analysis_prompt.txt` | Claude 网络输出分析的 RACE system prompt；规定只依据数据、只读、安全的下一检查和固定 Markdown 输出结构。 |

### 5.7 `labs/lab1-ollama/`：TJU API 基础与解析（目录名为历史兼容）

| 文件 | 作用与修改提示 |
|---|---|
| `labs/lab1-ollama/simple_ollama_test.py` | TJU API 基础入口；提供单轮聊天、模型参数、temperature 演示和网络问题样例。 |
| `labs/lab1-ollama/json_output_challenge.py` | 四个结构化输出挑战的集合版：接口、BGP、多厂商规范化和错误处理。 |
| `labs/lab1-ollama/challenge_1_interface_parser.py` | 把 Cisco interface 原始文本解析为固定 JSON，包含 fence 清理和字段存在性检查。 |
| `labs/lab1-ollama/challenge_2_bgp_parser.py` | 把 Arista 风格 BGP summary 解析成邻居数组，并找出非 Established 会话。 |
| `labs/lab1-ollama/challenge_3_multi_vendor.py` | 用同一模板把 Cisco、Arista、Juniper 接口状态归一为共同 schema。 |
| `labs/lab1-ollama/challenge_4_error_handling.py` | 处理 err-disabled、unknown、空数据，以及 fenced/带前言的模型 JSON；返回 `(result, error)` 而不是崩溃。 |
| `labs/lab1-ollama/netmiko_ssh_data.py` | 将 Netmiko 数据采集与 TJU API 健康分析串联；默认 `USE_MOCK=True`，包含接口和 BGP 两个 demo。 |
| `labs/lab1-ollama/ssh/challenge_1_interface_parser_ssh.py` | Challenge 1 的 SSH 版：采集 `show ip interface brief` 后交给 TJU API；默认 mock。 |
| `labs/lab1-ollama/ssh/challenge_2_bgp_parser_ssh.py` | Challenge 2 的 SSH 版：采集 `show bgp summary` 并解析；默认 mock。 |
| `labs/lab1-ollama/ssh/challenge_3_multi_vendor_ssh.py` | Challenge 3 的多设备/多厂商 SSH 版；每个设备可有独立 Netmiko 类型和 mock 输出。 |
| `labs/lab1-ollama/ssh/challenge_4_error_handling_ssh.py` | Challenge 4 的 SSH 版；同时处理连接错误、无输出、异常设备状态和模型 JSON 错误。 |

### 5.8 `labs/lab2-prompts/`：RACE 提示工程

| 文件 | 作用与修改提示 |
|---|---|
| `prompt_engineering_race.py` | Lab 2 核心：TJU API 调用、JSON/schema 约束、响应 JSON 提取、字段验证，以及 bad/good prompt 对比。修改结构化输出的首选文件。 |
| `labs/lab2-prompts/netmiko_config_parser.py` | 用 RACE 分析 SSH 或 mock 的运行配置/接口状态；演示接口配置解析和故障接口审计，默认 mock。 |
| `PROMPT_TEMPLATES.md` | 可复制的配置解析、安全告警、配置风险评分 RACE 模板与最佳实践。 |

### 5.9 `labs/lab3-chatbot/`：聊天状态与实时上下文

| 文件 | 作用与修改提示 |
|---|---|
| `labs/lab3-chatbot/chatbot_v1_stateless.py` | 每次仅发送当前问题的无状态基线，用第二个追问演示没有记忆。 |
| `chatbot_v2_with_memory.py` | `NetworkChatbot` 保存 user/assistant 历史、构建完整 prompt，支持 reset、历史长度、演示和交互模式。 |
| `labs/lab3-chatbot/chatbot_v3_live_ssh.py` | 在会话历史外增加 `LiveDeviceContext`；启动或 refresh 时采集接口/BGP 状态并注入 system prompt，支持 mock/Netmiko。 |
| `labs/lab3-chatbot/stateless.MD` | v1 的长篇教学说明、脚本拆解、预期输出及为何无状态失败。 |
| `labs/lab3-chatbot/memory.MD` | v2 的逐段教学说明，覆盖历史结构、prompt 构建、reset 和交互命令。 |
| `labs/lab3-chatbot/live_ssh.MD` | v3 的逐段教学说明，覆盖 mock/live 切换、状态快照、refresh 与交互流程；文中个别示例名可能滞后。 |

### 5.10 `labs/lab4-agentic/`：Agent 与工具调用

| 文件 | 作用与修改提示 |
|---|---|
| `agentic_network_bot_ollama.py` | 历史文件名兼容启动器；直接复用 `agentic_network_bot.py`，不再包含本地模型或文本工具协议。 |
| `agentic_network_bot.py` | 使用 TJU API 原生 `tools` schema 的 Agent 主实现；保留会话历史、回传 `tool_call_id`、执行多个工具，并提供 demo、交互和挑战。 |
| `lab4b_agentic_network_bot_netmiko.py` | 真实 SSH 版本；包含设备/目标/接口校验、命令规范化、危险词和危险 show 模式阻断、敏感信息脱敏、工具 schemas 与 Agent 循环。真实网络改动优先审查此文件。 |
| `live_network_devices.py` | 与 `examples/mock_network_devices.py` 函数签名兼容的可替换适配器；`USE_LIVE` 控制 mock/Netmiko，包含版本、接口和 BGP 文本解析。 |
| `labs/lab4-agentic/README.md` | Lab 4 简明入口、工具列表、运行命令、文本工具调用流程和真实设备适配原则。 |
| `labs/lab4-agentic/bot.MD` | 原生 tool-calling Agent 的详细教学文档，涵盖 demos、交互、加工具、调温度和常见错误。 |

### 5.11 `labs/lab5-mcp/`：MCP 复用层与 UI

| 文件 | 作用与修改提示 |
|---|---|
| `network_tools.py` | MCP 下方的安全业务层；导入共享 mock，校验设备，包装 status/interface/BGP/ping/show/topology，show 仅做前缀限制。 |
| `mcp_server.py` | FastMCP server；公开 `devices`、`device_status`、`interface_status`、`bgp_summary`、`ping`、`show_command`、`topology`，支持 stdio 与 `--sse`。 |
| `client_test.py` | 不启动 MCP 的业务层冒烟测试，打印所有主要工具、合法 show 和被阻断命令的 JSON。 |
| `http_bridge.py` | 连接 SSE MCP server 的常驻 MCP Client，并用 Starlette 在 8765 端口暴露浏览器可调用的 JSON HTTP 路由。 |
| `ui.html` | 单文件浏览器 UI；调用 bridge 的 endpoints，展示原始 JSON，并用 SVG 绘制 spine/leaf 拓扑。 |
| `labs/lab5-mcp/README.md` | Lab 5 架构、两终端启动顺序、stdio 客户端配置、安全规则和练习。 |

### 5.12 `labs/lab6-production-readiness/`：生产就绪模式

| 文件 | 作用与修改提示 |
|---|---|
| `safe_tools.py` | 定义 `SafetyPolicy`、`ToolDecision`、`AuditEvent/Logger` 和 `SafeNetworkTools`；执行设备 allowlist、show 白名单、审批标志和结构化审计。 |
| `production_agent_skeleton.py` | 定义统一 `ToolResult`、抽象 `NetworkBackend`、可用的 mock backend、尚未实现的 real backend，以及面向 Agent 的 facade。 |
| `labs/lab6-production-readiness/production_checklist.md` | 上生产前的十类检查：范围、安全、凭据、审批、可观测性、可靠性、数据质量、测试、变更控制、go/no-go。 |
| `labs/lab6-production-readiness/README.md` | Lab 6 目标、运行命令、策略链、read-only-first 演进路线和练习。 |

### 5.13 `lab/`：Containerlab 真实实验拓扑

| 文件 | 作用与修改提示 |
|---|---|
| `lab/topology.clab.yml` | 名为 `ai-net` 的 cEOS 4.32.0F 三节点拓扑；定义 spine1、leaf1、leaf2 及三条 /31 链路。 |
| `lab/configs/spine1.cfg` | spine1 启动配置：接口、Loopback、AS 65000、两叶 BGP、管理 API/SSH 和 MGMT VRF。 |
| `lab/configs/leaf1.cfg` | leaf1 启动配置：AS 65101、到 spine1/leaf2 的接口、Loopback 和管理平面。 |
| `lab/configs/leaf2.cfg` | leaf2 启动配置：AS 65102、到 spine1/leaf1 的接口、Loopback 和管理平面。 |

### 5.14 `docs/design-toolkit/`：附录模板

| 文件 | 作用与修改提示 |
|---|---|
| `docs/design-toolkit/README.md` | Toolkit 索引和推荐使用顺序。新增模板时更新此表。 |
| `docs/design-toolkit/agent-use-case-brief.yaml` | “只读 BGP 分诊助手”用例简报：问题、用户、范围、排除项、价值、成功指标、owner。 |
| `docs/design-toolkit/use-case-fit-scorecard.md` | 判断应使用 Agent、确定性自动化还是人工 runbook 的评分问题。 |
| `race-prompt-worksheet.md` | 在写入代码前设计 Role、Anchors、Context、Expected output 的工作表和骨架。 |
| `structured-output-validation.md` | JSON parse、必填项、枚举、类型、来源依据、不确定性与失败路径检查表。 |
| `docs/design-toolkit/memory-context-policy.md` | 会话历史、旧上下文摘要、原始工具结果、敏感数据、reset 和保留期决策表。 |
| `docs/design-toolkit/tool-inventory-safety-matrix.md` | 六类网络工具的用途、输入输出及安全规则清单。 |
| `docs/design-toolkit/tool-contract.yaml` | `bgp_summary` 的可复用工具契约样例，含参数、返回、阻断、错误、日志和版本兼容规则。 |
| `docs/design-toolkit/troubleshooting-evidence-record.yaml` | INC 案例证据记录样例，把 leaf2 的 Idle 邻居、down 接口与最终答案约束关联起来。 |
| `docs/design-toolkit/pilot-readiness-checklist.md` | 只读 pilot 前的范围、认证、授权、secret、验证、日志、失败行为和 ownership 检查。 |
| `docs/design-toolkit/operational-runbook.md` | 目的、范围、启动、健康检查、日志、失败、升级、禁用步骤的短 runbook 模板。 |
| `docs/design-toolkit/feature-flag-kill-switch.md` | read-only、设备范围、工具白名单、审批和全局禁用控制表及 kill switch 测试。 |
| `docs/design-toolkit/go-no-go-review.md` | 从只读继续扩展前的最终风险、检测、停止、解释、secret、审批和审计评审。 |

### 5.15 `tests/`：自动测试

| 文件 | 作用与修改提示 |
|---|---|
| `tests/test_command_safety.py` | pytest 测试 Lab 5 `safe_show_command()`：允许 show、阻止 configure、未知设备先拒绝。新增安全策略时应优先扩展这里。 |
| `tests/test_tju_llm_client.py` | 离线校验 Key 必填、base URL 不含 completion 路径、专属比赛地址和模型读取，不发送网络请求。 |
| `tests/test_agentic_tju_loop.py` | 用模拟模型响应验证 Lab 4 原生 Function Calling，并确保工具结果携带匹配的 `tool_call_id`。 |
| `tests/test_netpilot_llm.py` | 用注入的 Mock SDK Client 验证正式普通 Chat、SDK 配置、token/耗时解析、无 Key 行为、异常映射和畸形响应，全程不访问网络。 |
| `tests/test_netpilot_config.py` | 离线验证 Settings 默认值、API Key 脱敏、模式/范围校验和 TJU base URL 约束。 |
| `tests/test_netpilot_api.py` | 使用 FastAPI TestClient 验证 health、有/无 Key 启动、Tool Provider 初始化、无 secret 响应、中文首页和静态资源。 |
| `tests/test_tools.py` | 离线覆盖统一结果、非法参数、Local 接口信息、三平台命令、超时、DNS/TCP/HTTP/traceroute 和异常捕获。 |
| `tests/test_mock_scenarios.py` | 验证六种场景的关键证据组合、调用耗时、场景切换以及 Mock 不触发 socket/subprocess/httpx。 |
| `tests/test_tool_security.py` | 验证 Shell 注入、非法 Host/URL、SSRF、私网 DNS、恶意重定向、重定向上限、`shell=False` 和输出上限。 |

### 5.16 `bonus/lab-bun-chat/`：Bun Web Chat

| 文件 | 作用与修改提示 |
|---|---|
| `bonus/lab-bun-chat/README.md` | Bonus Lab 教程：Bun + Ollama + 会话记忆，围绕四个 TODO 和拓展练习。 |
| `server.js` | 完整版 Bun 服务与内嵌前端；端口 3003，保存会话历史，调用 Ollama `/api/chat`，并提供 RACE/P-E-N-E Prompt Builder、示例库和配置接口。 |
| `solution/server.js` | 较精简的参考解答；端口 3000，包含 system prompt、内存、聊天/reset API 和内嵌聊天页面。 |

## 6. 常用运行与验证命令

```bash
# 安装
python -m pip install -r requirements.txt
python -m pip install -e .

# NetPilot 正式应用
python -m uvicorn netpilot.main:app --reload

# NetPilot Milestone 2 Tool 层
pytest tests/test_tools.py -q
pytest tests/test_mock_scenarios.py -q
pytest tests/test_tool_security.py -q

# NetPilot Milestone 3 TJU LLM（离线 Mock）
pytest tests/test_netpilot_llm.py -q

# 配置检查（离线，不消耗 token）
python examples/test_setup.py

# 比赛 API 在线连通性检查
python scripts/test_tju_api.py

# 纯 mock 业务逻辑与测试
python labs/lab5-mcp/client_test.py
pytest -q

# 主 Agent
python labs/lab4-agentic/agentic_network_bot_ollama.py

# MCP 浏览器链：分别在两个终端运行
python labs/lab5-mcp/mcp_server.py --sse
python labs/lab5-mcp/http_bridge.py

# 生产模式演示
python labs/lab6-production-readiness/safe_tools.py
python labs/lab6-production-readiness/production_agent_skeleton.py
```

## 7. 后续维护本文的规则

发生以下任一变化时，应在同一提交中更新本文：

- 新增、删除、移动或重命名文件；
- 调整 TJU 模型、API endpoint、超时、重试或配置步骤；
- 新增/修改 Agent 或 MCP 工具及参数 schema；
- 改变 mock 故障场景或设备拓扑；
- 改变真实设备凭据来源、安全策略、审批或审计路径；
- 修复本文第 4 节列出的已知边界。

建议后续先用“按需求快速定位”确定入口，再对该入口的直接 import、调用者和测试做局部扫描；不要仅凭相似文件名假定各教学版本行为一致。
