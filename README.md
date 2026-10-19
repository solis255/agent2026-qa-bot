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
| 诊断对象 | 区分浏览器设备 / NetPilot 服务主机 / Mock 模拟终端；按工具执行位置限制能力，证据与去重绑定对象版本 |
| 客户端快照 | Windows 只读脚本 → 手动 JSON 上传 → 客户端 Evidence；校验/脱敏/时效/去重/替换归档，不启用远程执行 |
| 引导式修复 | 批准目录生成低风险手动计划，展示理由/验证/回滚，记录完成/跳过/结果；不自动执行或重测 |
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
PATCH /api/session/diagnostic-target
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
12A 快照新增 `environment_profile` 并升级到 v5（12F 当前为 v10），SQLite 表结构仍为 v3；旧快照保持未知，不反推环境。
接口、隐私边界和验收见 [Milestone 12A](docs/MILESTONE12A_VALIDATION.md)。

### 诊断对象（Milestone 12B）

侧栏“诊断对象”显示当前对象、直接检测能力和工具执行位置。Local Web 默认选择远程的“当前浏览器设备”，
**不会调用服务主机的 DNS、Ping、网卡、TCP、HTTP 或路由工具来冒充用户设备检测**。
未上传客户端快照时，这类请求会依据现象/环境给出安全建议或追问；明确知识请求仍可检索 RAG。
选择“NetPilot 服务主机”，或明确说“检查这台 NetPilot 服务器的 DNS”，才允许 Local 主机工具。
Mock 模式保持只读的“Mock 模拟终端”，结果明确为模拟，不代表真实校园网络。

对象切换增加 `target_version`，但不增加任务版本、不创建空 Turn；旧网络观察保留作历史，不参与当前对象的
Evidence、Coverage、Hypothesis、工具去重或模型对话。Timeline 标记对象与执行位置；报告区分当前证据和其他对象历史检测。
Target API 只接受 `session_id` 与 `subject`，执行位置/限制由服务端计算，沿用账号 ownership。
快照 v6 保存最新 `diagnostic_target`，旧记录保持“未记录”；完整会话及历史对象证据仍保留。
实现、DT-01～DT-15、验证记录与四个人工验收状态见 [Milestone 12B](docs/MILESTONE12B_VALIDATION.md)。

### 客户端诊断快照（Milestone 12C）

Local 部署的远程“当前浏览器设备”可在侧栏下载 [Windows 只读脚本](scripts/client_diagnostic_windows.ps1)，
审阅后在允许运行脚本的 Windows 10/11 普通用户 PowerShell 执行 `./client_diagnostic_windows.ps1`，
得到 `netpilot-client-diagnostic.json`，再主动上传。不提供一键执行、自动上传、提权或降低执行策略。

服务端校验 Snapshot v1、敏感字段与大小（默认 256 KiB），只保存脱敏摘要和规范化 Evidence。
证据属于 `user_client` 的采集时点，不是 NetPilot Tool Call，也不允许服务主机网络 Tool 冒充客户端检测。
超过 15 分钟按历史快照解释，未来超过 5 分钟提示时钟偏差；重新上传替换当前快照，旧证据保留归档，
相同快照不重复生成 Evidence/Trace。历史 JSON 升级 v7，SQLite 结构仍 v3，不清除既有记录。

上传后可问“根据快照分析我的电脑网络”或“生成诊断报告”。DNS 同类证据聚合展示；
unsupported/error/unknown 不当网络异常。WinHTTP 代理不等于浏览器代理，Wi-Fi 不等于校园 Wi-Fi。
真实 Windows 普通用户运行尚待验收：本环境执行策略为 Restricted，未绕过策略，也未声称真实采集成功。
完整契约、CS-01～CS-18 与四个人工 Case 状态见 [12C 验收记录](docs/MILESTONE12C_VALIDATION.md)。

### 引导式修复计划（Milestone 12D）

诊断或明确询问“怎么解决 / 下一步怎么办”时，服务端可从本地批准目录生成最多 5 步手动计划。
侧栏“修复计划”展示低风险标签、适用对象、理由、操作、验证和回滚；可标记完成、跳过、失败及是否改善。
“还是不行”复用既有状态，不重复已完成无效或跳过的等价操作，也不会自动升级为高风险操作。

**Plan 不是执行。** 不运行 Shell、不提权、不改 DNS/Proxy/Route、防火墙或执行策略，不自动重测。
VPN/代理为未知时仅确认；已启用也只在普通公网且用户确认无依赖时建议短暂对比，并提供恢复方法。
对象、关键环境、诊断依据或快照时效变化使旧计划失效。completed 只表示步骤流程结束，不等于故障 resolved。

结构化计划与反馈保存在 Session 级 History / Report，历史 JSON 当前为 v10，SQLite 结构仍 v3，旧记录不会从文本反推计划。
完整接口、批准模板、GR-01～GR-20 和人工验收状态见 [12D 验收记录](docs/MILESTONE12D_VALIDATION.md)。

### 修复前后验证（Milestone 12E）

计划创建时冻结同一诊断对象的 Before 基线。手动步骤标记“已完成”后，进入新的 task version，但不会立即判定改善：

- 远程浏览器设备：重新运行 Windows 诊断脚本并上传新快照；不能用服务主机检测替代用户设备证据。
- NetPilot 服务主机：点击“开始验证”，只重测基线中的相关关键只读指标，不重跑完整诊断链。
- 按同一域名、同一网关、同一 TCP host/port 或同一 URL 比较，输出“有改善 / 无变化 / 变差 / 暂时无法确认”。
- 用户反馈单独记录；与客观证据冲突时显示“暂时无法确认”。过期、不支持或错误结果不会冒充恢复证据。

网页提供 Before/After 表格和主观反馈，History 与 Markdown/JSON 报告保存每轮验证。默认保留最近 `VERIFICATION_MAX_CYCLES=10` 轮；普通重复验证复用已有结果，只有显式“重新验证”才创建下一轮。
**Verification ≠ Resolution**：本阶段不自动判定 resolved、不自动修复、不生成 Support Package。
完整接口、BV-01～BV-20 和四个人工验收步骤见 [12E 验收记录](docs/MILESTONE12E_VALIDATION.md)。

### 诊断闭环状态（Milestone 12F）

每个 Session 保存确定性的 Support Case 状态：诊断中、等待操作、正在验证、已解决、有改善、未解决、建议人工处理。
状态由结构化复核、低风险步骤、用户确认、对象/任务版本及证据时效计算，不能由 LLM 或前端直接指定。

- “已解决”要求关键异常指标恢复、有效客观复核和用户明确确认，单独说“好了”、计划完成或复核 improved 均不充分。
- DNS 有改善但用户仍报告网页故障，状态为“有改善”；12E 的主客观冲突记录继续保留。
- 连续有效复核无改善且无安全步骤、权限/风险边界、充分支持的基础设施假设或用户请求，可建议人工处理；跳过和动作失败不算修复无效。
- 症状复发开启新 task version，切换对象重回诊断中；旧闭环记录保留。默认保留最近 `RESOLUTION_MAX_TRANSITIONS=30` 次真实状态转换，重复确认不增加状态版本。
- 用户可确认原始症状或请求人工支持，History、Trace、Markdown/JSON 报告保存闭环依据。Mock 继续明确标注为模拟终端。

**人工支持只是一项建议，不会提交工单、发送邮件、接入 ITSM、执行高风险修复或提权。** 默认无改善建议阈值为 `RESOLUTION_ESCALATE_AFTER_NO_IMPROVEMENT=2`。
详细决策规则、API、RS-01～RS-24 和人工验收状态见 [12F 验收记录](docs/MILESTONE12F_VALIDATION.md)。

### 测试

Milestone 11 新增可折叠的“诊断思路”：由 Turn Intent、Coverage、结构化 Evidence、
候选原因状态和停止条件本地生成，不是模型隐藏思维链，也不复制 Tool Timeline。
API 的 `reasoning_trace` 是当前 Turn 新增条目，History/Report 保存有界的 Session 累计条目。
默认 `REASONING_TRACE_ENABLED=true`、`REASONING_TRACE_MAX_STEPS=50`、
`REASONING_SUMMARY_LLM_ENABLED=false`，不会增加 LLM/Tool 调用。
显式启用可选摘要时最多增加一次 LLM 选择调用，只能选取已有结构化摘要，失败不影响聊天。
Milestone 11 当时快照升级到 v4（12F 当前为 v10），SQLite 表结构仍为 v3；旧记录的 Trace 为空，不根据旧答案反推。
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
73 项 DOM 测试；完整验收应先安装依赖，确保这些测试没有跳过。
依赖版本、许可证及更新方法见 [本地 Markdown 依赖](web/vendor/README.md)。
最新验证结果与人工检查项见 [折叠时间线与行内引用验收](docs/INLINE_CITATIONS_VALIDATION.md)；
上阶段记录见 [Markdown 与来源输出验收](docs/MARKDOWN_SOURCE_OUTPUT_VALIDATION.md)。

在已激活的项目虚拟环境中运行：

```bash
python -m pytest -q
```

Milestone 12F 修改前基线为 `791 passed in 240.97s`；2026-10-19 诊断闭环状态实现后的最终全量回归实测为：

```text
880 passed in 187.50s
```

测试默认使用 Fake LLM、Mock Provider 或受控替身，不依赖真实 TJU API 与现场网络状态。最终验收结果以本 README 后续提交对应的 CI/本地测试输出为准。

## 上游来源与许可证

本仓库由 Packt 项目 *Building AI Agents for Network Operations* 演进而来，并保留书籍 Chapter/Lab、Mock spine/leaf、Containerlab 和教学模板。TJU NetPilot 在此基础上形成独立的 `src/netpilot/` 正式产品路径与比赛功能。详细的复用边界、Lab Map 和上游链接见 [`docs/upstream.md`](docs/upstream.md)。

上游版权与 MIT 许可声明保留在 [`LICENSE`](LICENSE) 中：Copyright (c) 2026 Sif Baksh；Copyright (c) 2026 Packt。使用、修改和分发时须继续保留 MIT attribution。

贡献前请运行上述测试，遵守工具与数据安全边界，并保留上游许可声明。
