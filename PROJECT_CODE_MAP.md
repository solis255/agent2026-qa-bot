# 项目代码导航与文件职责说明

> 最后扫描：2026-08-23  
> 扫描范围：仓库中除 `.git/` 外的全部 81 个受版本控制文件。本文是后续新增的第 82 个文件。  
> 用途：后续修改前先查本文的“按需求快速定位”和对应目录，只有在职责或依赖不明确时再做局部扫描。

## 1. 项目概览

这是《Building AI Agents for Network Operations》的配套教学仓库，主线是：

```text
Ollama 基础与结构化解析
  -> RACE 提示工程
  -> 有/无记忆聊天机器人
  -> Agent 工具调用与故障排查
  -> MCP 工具复用和浏览器 UI
  -> 生产安全、审计与后端抽象
```

主要运行时是 Python 3.10+ 与本地 Ollama。Lab 1～3 默认使用 `llama3.2:3b`，Lab 4 使用 `deepseek-r1:8b`。大多数示例默认使用模拟设备；真实设备示例使用 Netmiko。Bonus Lab 使用 Bun/JavaScript。

## 2. 按需求快速定位

| 要修改的内容 | 首选位置 | 经常需要联动检查的位置 |
|---|---|---|
| 模拟设备、接口/BGP 故障场景 | `examples/mock_network_devices.py` | `labs/lab4-agentic/live_network_devices.py`、Lab 3/1 内嵌的 mock 数据、相关文档示例 |
| Ollama 地址、模型或生成参数 | 各 Lab 的入口脚本 | `README.md`、`QUICKSTART.md`、`examples/test_setup.py`、Bonus Lab 常量 |
| JSON 结构化输出与验证 | `labs/lab2-prompts/prompt_engineering_race.py` | Lab 1 各 parser、`docs/design-toolkit/structured-output-validation.md` |
| RACE 提示词 | `prompts/race_network_analysis_prompt.txt` 或 Lab 2 | `labs/lab2-prompts/PROMPT_TEMPLATES.md`、`docs/design-toolkit/race-prompt-worksheet.md` |
| 聊天记忆 | `labs/lab3-chatbot/chatbot_v2_with_memory.py` | `chatbot_v3_live_ssh.py`、Bonus Lab 两个 `server.js` |
| Mock Agent 工具或调度循环 | `labs/lab4-agentic/agentic_network_bot_ollama.py` | `agentic_network_bot.py`、`examples/mock_network_devices.py` |
| Ollama 原生 tool calling | `labs/lab4-agentic/agentic_network_bot.py` | `lab4b_agentic_network_bot_netmiko.py` |
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

### 3.1 Mock Agent 主链

```text
labs/lab4-agentic/agentic_network_bot_ollama.py
  -> examples/mock_network_devices.py
  -> Ollama /api/generate
```

`agentic_network_bot_ollama.py` 使用文本格式 `TOOL:` / `ARGS:` 解析工具调用，还包含确定性预规划、重复调用防护和 Ollama 失败时的兜底汇总。修改工具时需同步：工具映射、提示中的工具说明、参数清洗及底层 mock 函数。

### 3.2 Ollama 原生工具调用链

```text
labs/lab4-agentic/agentic_network_bot.py
  -> examples/mock_network_devices.py
  -> Ollama /api/chat（tools 字段）
```

这是原生 tool-calling 版本，与上一版本并行存在，不是简单副本。Lab 4B 沿用同类循环，但把工具实现替换成真实 Netmiko SSH。

### 3.3 MCP 与浏览器链

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

### 3.4 生产安全链

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
5. **自动测试覆盖很窄。** 当前只有 `tests/test_command_safety.py`，覆盖 Lab 5 的已知设备与 show 前缀，没有覆盖 Agent 循环、MCP 传输、真实 SSH、提示输出、UI 或 Lab 6 策略。
6. **文档中有教学草稿痕迹。** Lab 3 的大写扩展名 `.MD` 文档很长，包含代码逐段讲解；其中个别示例文件名与实际脚本名不同。以当前代码文件名为准。
7. **Bonus README 与主实现存在演进差异。** README 描述“四个 TODO、端口 3000”的入门任务；根 `server.js` 已发展为端口 3003 的完整 RACE Prompt Builder，`solution/server.js` 才是较精简的端口 3000 解答版。
8. **`config.txt` 是独立的 BGP 安全配置样例**，当前没有代码直接读取它；其中仍有占位符 `<LOCAL_AS>` 和示例口令字段。
9. **`examples/temperature.py` 注释与实际参数不一致。** 注释写 temperature 0.0，payload 实际为 1.5。
10. **模型/服务是运行前置条件。** 涉及 Ollama 的脚本多数不是离线单元测试，运行时需本地服务和对应模型；真实 SSH 版本还需可达设备与 Netmiko。

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
| `requirements.txt` | 全仓 Python 依赖：requests、Anthropic、dotenv、Netmiko、PyYAML、Rich、MCP、Starlette、Uvicorn、pytest。 |
| `REQUIREMENTS_TJU_NetPilot_Codex.md` | TJU NetPilot 比赛项目的需求、架构约束、里程碑与验收标准；正式应用开发以此为产品目标。 |
| `Makefile` | setup、Containerlab、基础脚本、Claude、MCP 和 pytest 的快捷命令；其中三个设备脚本依赖当前缺失的 inventory。 |
| `config.txt` | Cisco 风格的 eBGP 入站过滤、会话认证、最大前缀与 peer policy 配置样例；不在运行调用链中。 |
| `ai-networking-workshop-home.jpeg` | 1920×1278、约 290 KiB 的仓库/Workshop 首页图片资源；当前 Markdown 未直接引用。 |
| `PROJECT_CODE_MAP.md` | 本文件；新增、删除、重命名文件或改变核心调用链时更新。 |

### 5.2 `examples/`：共享模拟数据与小型示例

| 文件 | 作用与修改提示 |
|---|---|
| `examples/mock_network_devices.py` | **最重要的共享 mock 数据源。** 定义四台设备、leaf2 的 BGP Idle 和 Ethernet3 down 场景，并提供设备、接口、BGP、ping、只读命令、拓扑函数。Lab 4、5、6 直接依赖它。 |
| `examples/test_setup.py` | 检查 Python 3.10+、Ollama 可执行文件/服务、两个所需模型和关键 Lab 文件；用于环境验收，不是 pytest 测试。 |
| `examples/temperature.py` | 单次调用 Ollama `/api/generate` 展示 temperature 效果；当前实际 temperature 为 1.5。 |
| `examples/tokens_test.py` | 调用 Ollama 并读取 `prompt_eval_count`；有 main guard，可被 pytest 安全导入而不立即访问服务。 |
| `examples/interface_output.json` | leaf1 `show interfaces status` 的示例输入，供 Claude/RACE 分析脚本使用。 |
| `examples/bgp_output.json` | leaf1 `show ip bgp summary` 的示例输入。 |
| `examples/claude_response_example.md` | 对 interface 示例数据的期望 Claude 分析输出，展示固定章节结构和“缺失数据”表达。 |

### 5.3 `scripts/`：章节前置与外部 API/SSH 脚本

| 文件 | 作用与修改提示 |
|---|---|
| `scripts/01_python_basics.py` | 面向网络工程师的 Python 字典、列表、循环和函数入门；`build_show_command()` 是最小示例。 |
| `scripts/02_inventory_loader.py` | 用 PyYAML 读取设备 inventory 并打印清单；目前指向不存在的 `mcp_server/inventory.yml`。 |
| `scripts/03_connect_to_device.py` | 从同一缺失 inventory 获取 Netmiko 参数，对指定设备执行 `show version`；包含认证、超时和未知设备处理。 |
| `scripts/04_get_interfaces.py` | 通过 Netmiko 获取 `show interfaces status`，封装为 device/command/output JSON；同样依赖缺失 inventory。 |
| `scripts/05_claude_race_analysis.py` | 读取 RACE system prompt 和输入文件，调用 Anthropic Messages API；使用 `.env` 的 API key/model，默认输入示例为 `examples/interface_output.json`。 |
| `scripts/test_tju_api.py` | 从本地 `.env` 读取 TJU 专属端点和 Key，通过 OpenAI SDK 发送最小请求；不会输出 API Key，并对 401、429、连接和服务错误给出提示。 |

### 5.4 `prompts/`：外置提示词

| 文件 | 作用与修改提示 |
|---|---|
| `prompts/bad_prompt.txt` | 故意模糊的单句提示，用作结构化提示的反例。 |
| `prompts/race_network_analysis_prompt.txt` | Claude 网络输出分析的 RACE system prompt；规定只依据数据、只读、安全的下一检查和固定 Markdown 输出结构。 |

### 5.5 `labs/lab1-ollama/`：Ollama 基础与解析

| 文件 | 作用与修改提示 |
|---|---|
| `labs/lab1-ollama/simple_ollama_test.py` | Ollama 基础客户端；提供单轮聊天、模型比较、temperature 演示和网络问题样例。 |
| `labs/lab1-ollama/json_output_challenge.py` | 四个结构化输出挑战的集合版：接口、BGP、多厂商规范化和错误处理。 |
| `labs/lab1-ollama/challenge_1_interface_parser.py` | 把 Cisco interface 原始文本解析为固定 JSON，包含 fence 清理和字段存在性检查。 |
| `labs/lab1-ollama/challenge_2_bgp_parser.py` | 把 Arista 风格 BGP summary 解析成邻居数组，并找出非 Established 会话。 |
| `labs/lab1-ollama/challenge_3_multi_vendor.py` | 用同一模板把 Cisco、Arista、Juniper 接口状态归一为共同 schema。 |
| `labs/lab1-ollama/challenge_4_error_handling.py` | 处理 err-disabled、unknown、空数据，以及 fenced/带前言的模型 JSON；返回 `(result, error)` 而不是崩溃。 |
| `labs/lab1-ollama/netmiko_ssh_data.py` | 将 Netmiko 数据采集与 Ollama 健康分析串联；默认 `USE_MOCK=True`，包含接口和 BGP 两个 demo。 |
| `labs/lab1-ollama/ssh/challenge_1_interface_parser_ssh.py` | Challenge 1 的 SSH 版：采集 `show ip interface brief` 后交给 Ollama；默认 mock。 |
| `labs/lab1-ollama/ssh/challenge_2_bgp_parser_ssh.py` | Challenge 2 的 SSH 版：采集 `show bgp summary` 并解析；默认 mock。 |
| `labs/lab1-ollama/ssh/challenge_3_multi_vendor_ssh.py` | Challenge 3 的多设备/多厂商 SSH 版；每个设备可有独立 Netmiko 类型和 mock 输出。 |
| `labs/lab1-ollama/ssh/challenge_4_error_handling_ssh.py` | Challenge 4 的 SSH 版；同时处理连接错误、无输出、异常设备状态和模型 JSON 错误。 |

### 5.6 `labs/lab2-prompts/`：RACE 提示工程

| 文件 | 作用与修改提示 |
|---|---|
| `prompt_engineering_race.py` | Lab 2 核心：Ollama 调用、JSON/schema 约束、响应 JSON 提取、字段验证，以及 bad/good prompt 对比。修改结构化输出的首选文件。 |
| `labs/lab2-prompts/netmiko_config_parser.py` | 用 RACE 分析 SSH 或 mock 的运行配置/接口状态；演示接口配置解析和故障接口审计，默认 mock。 |
| `PROMPT_TEMPLATES.md` | 可复制的配置解析、安全告警、配置风险评分 RACE 模板与最佳实践。 |

### 5.7 `labs/lab3-chatbot/`：聊天状态与实时上下文

| 文件 | 作用与修改提示 |
|---|---|
| `labs/lab3-chatbot/chatbot_v1_stateless.py` | 每次仅发送当前问题的无状态基线，用第二个追问演示没有记忆。 |
| `chatbot_v2_with_memory.py` | `NetworkChatbot` 保存 user/assistant 历史、构建完整 prompt，支持 reset、历史长度、演示和交互模式。 |
| `labs/lab3-chatbot/chatbot_v3_live_ssh.py` | 在会话历史外增加 `LiveDeviceContext`；启动或 refresh 时采集接口/BGP 状态并注入 system prompt，支持 mock/Netmiko。 |
| `labs/lab3-chatbot/stateless.MD` | v1 的长篇教学说明、脚本拆解、预期输出及为何无状态失败。 |
| `labs/lab3-chatbot/memory.MD` | v2 的逐段教学说明，覆盖历史结构、prompt 构建、reset 和交互命令。 |
| `labs/lab3-chatbot/live_ssh.MD` | v3 的逐段教学说明，覆盖 mock/live 切换、状态快照、refresh 与交互流程；文中个别示例名可能滞后。 |

### 5.8 `labs/lab4-agentic/`：Agent 与工具调用

| 文件 | 作用与修改提示 |
|---|---|
| `agentic_network_bot_ollama.py` | 当前 README 推荐的本地 Agent 主实现；用 `/api/generate` 和文本 `TOOL/ARGS` 协议，加入启发式工具预规划、循环上限、去重和确定性 fallback。 |
| `agentic_network_bot.py` | 使用 Ollama `/api/chat` 原生 `tools` schema 的 Agent 版本；保留会话历史，执行多个 tool calls，并提供四种 demo、交互模式和挑战。 |
| `lab4b_agentic_network_bot_netmiko.py` | 真实 SSH 版本；包含设备/目标/接口校验、命令规范化、危险词和危险 show 模式阻断、敏感信息脱敏、工具 schemas 与 Agent 循环。真实网络改动优先审查此文件。 |
| `live_network_devices.py` | 与 `examples/mock_network_devices.py` 函数签名兼容的可替换适配器；`USE_LIVE` 控制 mock/Netmiko，包含版本、接口和 BGP 文本解析。 |
| `labs/lab4-agentic/README.md` | Lab 4 简明入口、工具列表、运行命令、文本工具调用流程和真实设备适配原则。 |
| `labs/lab4-agentic/bot.MD` | 原生 tool-calling Agent 的详细教学文档，涵盖 demos、交互、加工具、调温度和常见错误。 |

### 5.9 `labs/lab5-mcp/`：MCP 复用层与 UI

| 文件 | 作用与修改提示 |
|---|---|
| `network_tools.py` | MCP 下方的安全业务层；导入共享 mock，校验设备，包装 status/interface/BGP/ping/show/topology，show 仅做前缀限制。 |
| `mcp_server.py` | FastMCP server；公开 `devices`、`device_status`、`interface_status`、`bgp_summary`、`ping`、`show_command`、`topology`，支持 stdio 与 `--sse`。 |
| `client_test.py` | 不启动 MCP 的业务层冒烟测试，打印所有主要工具、合法 show 和被阻断命令的 JSON。 |
| `http_bridge.py` | 连接 SSE MCP server 的常驻 MCP Client，并用 Starlette 在 8765 端口暴露浏览器可调用的 JSON HTTP 路由。 |
| `ui.html` | 单文件浏览器 UI；调用 bridge 的 endpoints，展示原始 JSON，并用 SVG 绘制 spine/leaf 拓扑。 |
| `labs/lab5-mcp/README.md` | Lab 5 架构、两终端启动顺序、stdio 客户端配置、安全规则和练习。 |

### 5.10 `labs/lab6-production-readiness/`：生产就绪模式

| 文件 | 作用与修改提示 |
|---|---|
| `safe_tools.py` | 定义 `SafetyPolicy`、`ToolDecision`、`AuditEvent/Logger` 和 `SafeNetworkTools`；执行设备 allowlist、show 白名单、审批标志和结构化审计。 |
| `production_agent_skeleton.py` | 定义统一 `ToolResult`、抽象 `NetworkBackend`、可用的 mock backend、尚未实现的 real backend，以及面向 Agent 的 facade。 |
| `labs/lab6-production-readiness/production_checklist.md` | 上生产前的十类检查：范围、安全、凭据、审批、可观测性、可靠性、数据质量、测试、变更控制、go/no-go。 |
| `labs/lab6-production-readiness/README.md` | Lab 6 目标、运行命令、策略链、read-only-first 演进路线和练习。 |

### 5.11 `lab/`：Containerlab 真实实验拓扑

| 文件 | 作用与修改提示 |
|---|---|
| `lab/topology.clab.yml` | 名为 `ai-net` 的 cEOS 4.32.0F 三节点拓扑；定义 spine1、leaf1、leaf2 及三条 /31 链路。 |
| `lab/configs/spine1.cfg` | spine1 启动配置：接口、Loopback、AS 65000、两叶 BGP、管理 API/SSH 和 MGMT VRF。 |
| `lab/configs/leaf1.cfg` | leaf1 启动配置：AS 65101、到 spine1/leaf2 的接口、Loopback 和管理平面。 |
| `lab/configs/leaf2.cfg` | leaf2 启动配置：AS 65102、到 spine1/leaf1 的接口、Loopback 和管理平面。 |

### 5.12 `docs/design-toolkit/`：附录模板

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

### 5.13 `tests/`：自动测试

| 文件 | 作用与修改提示 |
|---|---|
| `tests/test_command_safety.py` | pytest 测试 Lab 5 `safe_show_command()`：允许 show、阻止 configure、未知设备先拒绝。新增安全策略时应优先扩展这里。 |

### 5.14 `bonus/lab-bun-chat/`：Bun Web Chat

| 文件 | 作用与修改提示 |
|---|---|
| `bonus/lab-bun-chat/README.md` | Bonus Lab 教程：Bun + Ollama + 会话记忆，围绕四个 TODO 和拓展练习。 |
| `server.js` | 完整版 Bun 服务与内嵌前端；端口 3003，保存会话历史，调用 Ollama `/api/chat`，并提供 RACE/P-E-N-E Prompt Builder、示例库和配置接口。 |
| `solution/server.js` | 较精简的参考解答；端口 3000，包含 system prompt、内存、聊天/reset API 和内嵌聊天页面。 |

## 6. 常用运行与验证命令

```bash
# 安装
python -m pip install -r requirements.txt

# 环境检查（需要本地 Ollama）
python examples/test_setup.py

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
- 调整 Ollama 模型、API endpoint、端口或启动顺序；
- 新增/修改 Agent 或 MCP 工具及参数 schema；
- 改变 mock 故障场景或设备拓扑；
- 改变真实设备凭据来源、安全策略、审批或审计路径；
- 修复本文第 4 节列出的已知边界。

建议后续先用“按需求快速定位”确定入口，再对该入口的直接 import、调用者和测试做局部扫描；不要仅凭相似文件名假定各教学版本行为一致。
