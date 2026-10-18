# TJU NetPilot

> 天津大学校园网络智能诊断与服务 Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Model: tju-llm](https://img.shields.io/badge/model-tju--llm-brightgreen.svg)](https://ai.tju.edu.cn/)

TJU NetPilot 面向校园网连通性排障与服务知识问答。它不是只给出通用建议的 Chatbot：面对实时网络问题时，Agent 会按需调用受控、只读的网络 Tool 获取证据，再给出带结论、置信度、建议和限制的诊断；面对 VPN、eduroam 等知识问题时，可从带来源标记的本地知识库检索参考资料。

正式产品代码位于 [`src/netpilot/`](src/netpilot/)。仓库中的 `labs/`、`lab/`、`examples/`、`bonus/` 等目录是保留的上游教学资源，不参与 TJU NetPilot 的正式运行时，详见[上游来源与教学资源](docs/upstream.md)。

## 产品能力

| 能力 | 当前实现 |
|---|---|
| 模型 | `tju-llm`，通过 OpenAI-compatible Chat Completions 接口进行原生 Function Calling |
| Agent | 单 Agent、有界 Tool loop、Turn Intent / ToolPolicy、Coverage-based Stop、跨 Turn Evidence 与轻量 Hypothesis |
| 网络检测 | 六个 allowlisted、只读 Tool；严格参数校验与统一结构化证据 |
| Provider | 确定性离线 `MockNetworkProvider`；检测运行 NetPilot 主机的 `LocalNetworkProvider` |
| RAG | 本地 Markdown/TXT → 分块 → Embedding → FAISS → 带来源检索 |
| Web/API | 中文 Web、登录/注册/改密/退出、当前用户菜单、个人会话与历史、结构化 Tool Timeline、健康检查、Mock 场景控制 |
| 历史与报告 | 每个 Session 一条累计 SQLite 诊断记录、账号历史分析、每页 10 条上一页/下一页、确定性报告、Markdown/JSON 导出 |
| 环境画像 | 每个 Session 一份 EnvironmentProfile；浏览器低风险采集、用户编辑/明确表述更新、来源优先级、跨 Turn 复用、历史与报告保存 |
| 流式传输 | JSON-only SSE：`start → delta... → complete`，带 keep-alive 与安全错误事件 |
| 安全 | Tool allowlist、Pydantic 严格校验、SSRF 防护、`shell=False`、超时/输出/容量上限、日志脱敏 |

### 普通 Chatbot 与 TJU NetPilot

| 对比项 | 普通 Chatbot | TJU NetPilot |
|---|---|---|
| 实时网络状态 | 只能依据用户描述推测 | 先通过只读 Tool 取证，再依据结构化结果判断 |
| 工具边界 | 可能没有明确执行边界 | LLM 只能调用 `ToolRegistry` 中的 allowlisted tools |
| 诊断过程 | 通常只有自然语言答案 | 展示 Tool 参数、轮次、耗时、结果和证据状态 |
| 知识来源 | 可能不展示来源 | RAG 结果保留标题、URL、类型、文件、chunk 和相关度 |
| 可复现性 | 依赖现场网络与模型措辞 | Mock 场景可离线、确定性复现；Local 用于本机实测 |
| 留痕 | 通常只保留聊天文本 | 可持久化结构化诊断快照并导出报告 |

### 六个网络 Tool

| Tool | 用途 | 关键结果 |
|---|---|---|
| `get_network_info` | 检查运行 NetPilot 主机的网卡、IPv4、默认网关和 DNS | 本地接入配置 |
| `ping_host` | 有界 ICMP 探测 | 可达性、丢包、平均时延 |
| `dns_lookup` | 有界域名解析 | 是否解析、地址列表 |
| `tcp_check` | 检查指定 TCP 端口 | 是否连接、失败原因 |
| `http_check` | 只读检查公开 HTTP(S) URL | 请求是否发送、状态码、重定向与解析地址 |
| `traceroute` | 有界路由追踪 | 跳点与是否到达目标 |

当本地 RAG 索引就绪时，`ToolRegistry` 还会注册可选的 `knowledge_search`。它是知识检索 Tool，不属于上述六个网络检测 Tool。

`success=true` 表示 Tool 成功产生了诊断证据，并不表示网络一定健康。例如 `reachable=false` 是一次执行成功的异常观察；超时、执行错误与安全阻止会被单独分类。

## 测试 Demo

以下 Demo 建议使用 `TOOL_MODE=mock` 与 `SCENARIO_SWITCH_ENABLED=true`，以获得稳定、可复现的结构化结果。模型措辞可能变化，验收以 Tool Timeline、诊断分类和来源字段为准。

### Demo 1：DNS 故障

切换到 `dns_failure`，输入：

> 我可以访问公网 IP，但打不开 github.com。请至少使用 ping_host 检查 1.1.1.1，并使用 dns_lookup 检查 github.com，最后根据证据简洁给出诊断。

预期：Ping 为正常证据，DNS 为异常证据，结论优先指向 DNS 解析阶段，而不是把 `resolved=false` 误报成 Tool 执行失败。

### Demo 2：SSH 端口受阻

切换到 `tcp_ssh_blocked`，输入：

> 网页可以打开，但 SSH 连接 ssh.example.com 的 22 端口失败。请使用 tcp_check 检查该主机的 22 端口，并依据结果判断。

预期：`tcp_check` 返回 `connected=false` 与安全失败原因；结论定位到 TCP 22/SSH，不扩大为整个网络中断。

### Demo 3：VPN / RAG

确认 `/api/health` 的 `rag_ready=true`，输入：

> 天津大学 VPN 怎么使用？请先调用 knowledge_search，只依据知识库回答，并标出资料类型、标题和原始 URL。

预期：时间线显示知识参考，来源区展示 `community`、标题、相关度与原始 URL；回答明确社区资料不等于学校当前官方规定。

## 架构

```text
Browser / API Client
        |
        v
 FastAPI routes + Web static files
        |
        +--> SessionStore (有界文本历史 + SessionTaskState / Evidence Memory)
        |
        v
 Turn Intent --> ToolPolicy --> AgentOrchestrator <--> TJUClient <--> tju-llm
        |
        v
 ToolRegistry (allowlist + strict schemas)
        |
        +--> NetworkToolService --> MockNetworkProvider
        |                      \--> LocalNetworkProvider（仅本机）
        |
        \--> knowledge_search --> FaissRetriever --> 本地知识索引
        |
        v
 Diagnosis / Evidence --> ChatResponse --> SQLite history --> Report export
```

`AgentOrchestrator` 将对话和 allowlisted function schemas 发送给 `tju-llm`。模型返回原生 `tool_calls` 后，服务端按名称查找、校验参数并执行 Tool，再把每个结构化结果按对应的 `tool_call_id` 作为 `tool` 消息回填。循环由 `MAX_TOOL_ROUNDS` 限制，并会避免重复执行相同目标。

完整类名、请求流、错误边界与扩展点见[架构说明](docs/architecture.md)，设计取舍见[设计文档](DESIGN.md)。

## 运行

### 环境要求

- Python 3.10+
- Git
- 比赛平台分配的 TJU API Key 与专属 base URL
- 可选：构建 RAG 索引时需要首次下载 Embedding 模型

### Quick Start

```bash
git clone https://github.com/solis255/agent2026-qa-bot.git
cd agent2026-qa-bot

python -m venv .venv
```

Linux/macOS：

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
cp .env.example .env
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
Copy-Item .env.example .env
```

在私有 `.env` 中填写：

```text
TJU_API_KEY=你的比赛 API Key
TJU_API_BASE=比赛平台分配的专属 SDK base URL
TJU_MODEL=tju-llm
LLM_MAX_OUTPUT_TOKENS=1600
LLM_REPORT_MAX_OUTPUT_TOKENS=2800
MAX_RAG_CALLS_PER_TURN=2
```

不要把 `/chat/completions` 附加到 `TJU_API_BASE`；SDK 会自动补充该路径。`.env` 已被 Git 忽略，禁止提交或通过浏览器传递 API Key。

启动正式应用：

```bash
python -m uvicorn netpilot.main:app --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000/>，注册专用演示账号或登录后即可创建个人会话；右上角菜单提供“我的诊断历史”、修改密码和退出。健康检查位于 <http://127.0.0.1:8000/api/health>。没有 `TJU_API_KEY` 时应用仍会启动并返回 `llm_configured=false`，但聊天接口不可用；Tool Provider 构造阶段不会发出网络请求。

### Mock 演示

```powershell
$env:TOOL_MODE="mock"
$env:SCENARIO_SWITCH_ENABLED="true"
python -m uvicorn netpilot.main:app --host 127.0.0.1 --port 8001
```

内置场景：`healthy`、`dns_failure`、`gateway_unreachable`、`tcp_ssh_blocked`、`http_failure`、`partial_connectivity`。Mock Provider 不执行系统命令、Socket 或 HTTP 请求。



### RAG 索引

```bash
python scripts/build_knowledge_index.py
# 已有模型缓存时可离线重建
python scripts/build_knowledge_index.py --offline
```

流水线从 `knowledge/raw/` 读取带 YAML front matter 的 UTF-8 Markdown/TXT，确定性分块，使用配置的 Embedding 模型生成向量并写入 FAISS。当前仓库内置的校园网、VPN、eduroam 摘要均来自 TJUBOT Wiki，并明确标记为 `community`；当前没有把这些材料宣称为天津大学官方资料。Schema 支持 `official`、`community`、`maintainer`，新增正式资料时必须据实标记并保留原始 URL。检索文本始终作为 untrusted reference data，不能覆盖系统指令或触发任意 Tool。同一 Turn 的检索默认最多两次；格式相同或词集合高度相似的 query 会复用已有结果。API 中 `sources` 是知识操作参考，`diagnosis.evidence` 只包含实时 Network Evidence。

索引缺失、损坏、模型不匹配或本地模型缓存不可用时，`rag_ready=false`，`knowledge_search` 不注册；网络诊断与应用启动继续可用。

### API 与 SSE

主要接口：

```text
GET  /api/health
POST /api/session
GET  /api/session/{session_id}
PATCH /api/session/environment/browser
PATCH /api/session/environment/user
POST /api/chat
POST /api/chat/stream
GET  /api/diagnoses
GET  /api/diagnoses/{record_id}
GET  /api/diagnoses/{record_id}/report
GET  /api/diagnoses/{record_id}/export?format=markdown|json
GET  /api/scenarios
```

`POST /api/chat/stream` 当前是 transport-level SSE：后台先完成一次权威的、非流式 `tju-llm` + Tool loop，再把最终答案按字符块发出 `delta`，最后发送完整 `ChatResponse`。它不是模型 token streaming，也不会为流式显示发起第二次模型请求。

### 当前环境（Milestone 12A）

侧栏“当前环境”可展开查看/编辑操作系统、接入方式、VPN、Proxy、影响范围及受影响服务。
浏览器只自动提供归一化 OS、在线状态、语言及可选 Network Information API 估计；
不会自动判断校园 WiFi、VPN 或代理。未知保留为 `unknown` / `null`，不等于关闭。
用户确认的值优先于浏览器推断。明确陈述（如“我现在用 Windows 11，连校园 WiFi，没开 VPN”）
可由本地规则更新画像，不额外调用 LLM。

画像是上下文，不是实时 Tool Evidence。Local Tools 仍只检测运行 NetPilot 的主机。
正常刷新页面时通过 URL 片段里的 Session ID 从服务端恢复画像，不使用 localStorage 保存环境；
Session 仍是有界进程内存，重启/清理后需新建 Session，已完成会话的画像可从 SQLite 历史读取。
仅保存最新画像，不新增诊断记录/Turn，不因普通字段补充推进 `task_version`。
快照新增 `environment_profile` 并升级到 v5，SQLite 表结构仍为 v3；旧快照保持未知，不反推环境。
接口、隐私边界和验收见 [Milestone 12A](docs/MILESTONE12A_VALIDATION.md)。

### 测试

Milestone 11 新增可折叠的“诊断思路”：由 Turn Intent、Coverage、结构化 Evidence、
候选原因状态和停止条件本地生成，不是模型隐藏思维链，也不复制 Tool Timeline。
API 的 `reasoning_trace` 是当前 Turn 新增条目，History/Report 保存有界的 Session 累计条目。
默认 `REASONING_TRACE_ENABLED=true`、`REASONING_TRACE_MAX_STEPS=50`、
`REASONING_SUMMARY_LLM_ENABLED=false`，不会增加 LLM/Tool 调用。
显式启用可选摘要时最多增加一次 LLM 选择调用，只能选取已有结构化摘要，失败不影响聊天。
Milestone 11 当时快照升级到 v4（12A 当前为 v5），SQLite 表结构仍为 v3；旧记录的 Trace 为空，不根据旧答案反推。
实现、RT-01～RT-14 与四场景实际结果见 [Milestone 11 验收](docs/MILESTONE11_VALIDATION.md)。

Web 回答和历史回放使用本地 Marked + DOMPurify 安全渲染 Markdown；User/Error
保持纯文本，SSE 增量先显示原文，完成后统一排版。知识回答使用稳定 `source_ref` 的
行内尾标引用 `[1][2]`，直接打开对应来源，hover/focus 可查看来源类型与标题。
独立来源面板已移除；异常 fallback 同样按片段引用。报告/导出的独立来源区保留。
诊断时间线采用原生折叠区，初始/新 Session 默认收起，同 Session 更新步骤不改变展开状态。
运行应用无需 npm/CDN。首次运行前端 DOM/XSS 回归测试前，请安装测试依赖：

```powershell
cd web
npm ci --ignore-scripts
npm test
cd ..
```

需要 Node.js 22.13+（22.x）或兼容的 24+。缺少 Node/jsdom 时 pytest 会明确跳过
33 项 DOM 测试；完整验收应先安装依赖，确保这些测试没有跳过。
依赖版本、许可证及更新方法见 [本地 Markdown 依赖](web/vendor/README.md)。
最新验证结果与人工检查项见 [折叠时间线与行内引用验收](docs/INLINE_CITATIONS_VALIDATION.md)；
上阶段记录见 [Markdown 与来源输出验收](docs/MARKDOWN_SOURCE_OUTPUT_VALIDATION.md)。

在已激活的项目虚拟环境中运行：

```bash
python -m pytest -q
```

Milestone 12A 修改前基线为 `420 passed in 62.77s`；2026-10-18 环境画像实现后的全量回归实测为：

```text
494 passed in 74.12s
```

测试默认使用 Fake LLM、Mock Provider 或受控替身，不依赖真实 TJU API 与现场网络状态。最终验收结果以本 README 后续提交对应的 CI/本地测试输出为准。

## 上游来源与许可证

本仓库由 Packt 项目 *Building AI Agents for Network Operations* 演进而来，并保留书籍 Chapter/Lab、Mock spine/leaf、Containerlab 和教学模板。TJU NetPilot 在此基础上形成独立的 `src/netpilot/` 正式产品路径与比赛功能。详细的复用边界、Lab Map 和上游链接见 [`docs/upstream.md`](docs/upstream.md)。

上游版权与 MIT 许可声明保留在 [`LICENSE`](LICENSE) 中：Copyright (c) 2026 Sif Baksh；Copyright (c) 2026 Packt。使用、修改和分发时须继续保留 MIT attribution。

贡献前请运行上述测试，遵守工具与数据安全边界，并保留上游许可声明。
