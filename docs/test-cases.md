# TJU NetPilot 比赛验收矩阵

本文档统一整理 TJU NetPilot（天津大学校园网络智能诊断与服务 Agent）的自动与手工验收。正式产品代码位于 [`src/netpilot/`](../src/netpilot/)。自动测试默认使用 Fake LLM、Mock Provider、临时 SQLite 或受控替身，不调用真实 `tju-llm`，也不依赖现场网络。

## 运行方式

在已激活的项目虚拟环境中：

```bash
python -m pytest -q
```

需要稳定演示 Web Mock 场景时：

```powershell
$env:TOOL_MODE="mock"
$env:SCENARIO_SWITCH_ENABLED="true"
python -m uvicorn netpilot.main:app --host 127.0.0.1 --port 8001
```

打开 <http://127.0.0.1:8001/>，先注册或登录专用演示账号。模型自然语言措辞允许变化，优先验收结构化 Tool Timeline、finding status、diagnosis、sources 和 HTTP/SSE contract。完整浏览器人工流程与 LAN Demo 硬化仍需执行。

## 验收矩阵

| ID | 类型 | 输入 / 场景 | 预期 | 自动 / 手工 | 对应 pytest 文件 |
|---|---|---|---|---|---|
| NP-SC-001 | Mock 场景：healthy | `TOOL_MODE=mock`，场景 `healthy`；运行六 Tool | 六 Tool 全部返回统一 `ToolResult`；未出现基础连通性异常；不发生外部 I/O | 自动 | `tests/test_mock_scenarios.py`、`tests/test_tools.py` |
| NP-SC-002 | Mock 场景：dns_failure | 场景 `dns_failure`；“能访问公网 IP，但打不开 github.com”，检查 `1.1.1.1` Ping 与 `github.com` DNS | Ping 正常；DNS `resolved=false`；该负面观察为成功证据；Agent 诊断指向 DNS 解析 | 自动 + 手工 | `tests/test_mock_scenarios.py`、`tests/test_agent_dns_scenario.py`、`tests/test_agent_orchestrator.py` |
| NP-SC-003 | Mock 场景：gateway_unreachable | 场景 `gateway_unreachable`；检查本机网络信息及默认网关 `192.168.1.1` | 保留接口/默认网关证据；网关 Ping `reachable=false`；建议优先本地接入/网关，不先归因 DNS | 自动 + 手工 | `tests/test_mock_scenarios.py`；Agent/Web 结论按本页手工验收 |
| NP-SC-004 | Mock 场景：tcp_ssh_blocked | 场景 `tcp_ssh_blocked`；“网页正常但 `ssh.example.com:22` 失败”，调用 `tcp_check` | `connected=false` 与安全 `failure_reason`；诊断定位 TCP 22/SSH，不扩大为整体断网 | 自动 + 手工 | `tests/test_mock_scenarios.py`；Agent/Web 结论按本页手工验收 |
| NP-SC-005 | Mock 场景：http_failure | 场景 `http_failure`；对 `example.com` 检查 DNS、TCP 443、HTTPS | DNS/Ping/TCP 证据健康；HTTP 为异常或错误状态证据；定位 HTTP/TLS/应用层 | 自动 + 手工 | `tests/test_mock_scenarios.py`、`tests/test_custom_scenarios.py` |
| NP-SC-006 | Mock 场景：partial_connectivity | 场景 `partial_connectivity`；检查 `1.1.1.1` Ping 和 `example.com` traceroute | 同时存在成功和退化证据；不无限重复相同 Tool/目标；结论保留限制 | 自动 + 手工 | `tests/test_mock_scenarios.py`、`tests/test_agent_orchestrator.py` |
| NP-RAG-001 | VPN / RAG | RAG ready；“天津大学 VPN 怎么使用？请调用 knowledge_search，并给出资料类型和来源” | 仅校园知识意图启用 `knowledge_search`；返回 title/URL/source_type/file/chunk/score；当前种子显示 `community`；资料作为 untrusted reference，不冒充实时证据或官方现行规定 | 自动 + 手工 | `tests/test_agent_rag_scenario.py`、`tests/test_milestone7.py`、`tests/test_rag_loader.py`、`tests/test_rag_index.py` |
| NP-AG-001 | Multiple tool calls | Fake LLM 一次返回多个原生 `tool_calls` | 每个 allowlisted Tool 都执行；保留完整 assistant/tool 顺序；每个结果匹配自己的 `tool_call_id` | 自动 | `tests/test_agent_orchestrator.py`、`tests/test_agentic_tju_loop.py` |
| NP-AG-002 | `MAX_TOOL_ROUNDS` | Fake LLM 持续请求新的 Tool；默认 `MAX_TOOL_ROUNDS=6` | 第七轮执行前停止；状态为 `max_tool_rounds`；有证据时给出保守 fallback，不无限循环 | 自动 | `tests/test_agent_orchestrator.py`、`tests/test_netpilot_config.py` |
| NP-AG-003 | Invalid tool arguments | 未知 Tool、非 JSON、数组参数、额外 `command` 字段、越界端口 | 不执行 handler；返回 `unsupported` 或 `invalid_input`；安全错误可回填模型 | 自动 | `tests/test_tool_registry.py`、`tests/test_agent_orchestrator.py`、`tests/test_tools.py` |
| NP-SEC-001 | SSRF | `file://`、FTP、localhost、回环、metadata、私网解析、重定向到 localhost、带凭据 URL | 在请求前或重定向前阻止；返回 `security_blocked`；不把 blocked 当成站点返回失败；限制重定向 | 自动 | `tests/test_tool_security.py`、`tests/test_milestone7.py` |
| NP-SEC-002 | Shell injection | Host 含 `;shutdown`、`&& whoami`、换行、参数前缀；检查所有子进程调用 | 输入校验拒绝；子进程始终固定 argv、`shell=False`；输出与超时有界 | 自动 | `tests/test_tool_security.py`、`tests/test_tools.py`、`tests/test_command_safety.py` |
| NP-HIS-001 | Session / History | 同一会话多轮；重启 repository；并发写入；超出保留上限；非法 cursor | `SessionStore` 保留有界文本上下文并拒绝并发 turn；SQLite 快照跨重启、可分页/筛选；失败安全降级 | 自动 | `tests/test_sessions.py`、`tests/test_chat_api.py`、`tests/test_diagnosis_history.py` |
| NP-AUTHZ-001 | 9B 多用户隔离 | A/B 各建会话和诊断；B 猜 A 的 session/record ID；v1 DB 迁移 | 未登录 401；跨用户 Chat/SSE、详情、报告、导出 404；列表仅本人；旧记录 `user_id=NULL` 保留且不可见；新记录带 owner | 自动 | `tests/test_auth_ownership.py`、`tests/test_sessions.py` |
| NP-WEB-AUTH-001 | 9C Web 认证 | 无 Cookie 打开首页；注册 A、改密、退出；注册 B；A 重新登录 | `/api/auth/me` 决定登录面板/主界面；Cookie 同源；A/B 历史隔离；退出清空旧内容；不在浏览器存储保存密码/Token | API 流程 + 静态断言自动；真实浏览器待手工 | `tests/test_web_auth_ui.py`、`tests/test_auth_api.py`、`tests/test_auth_ownership.py` |
| NP-LAN-001 | 9D LAN 预检 | `AUTH_ENABLED=false`；默认本机监听；HTTP Cookie Secure 误开；缺密钥/Mock 场景/RAG 索引 | 禁止关闭认证；预检只给安全动作提示、不输出密钥；缺项时非零退出，不宣称 LAN 或 RAG 已可用 | 自动配置/预检 + 现场手工连通 | `tests/test_lan_demo_preflight.py`、`tests/test_netpilot_config.py`；现场步骤见 `docs/MILESTONE9D_LAN_DEMO.md` |
| NP-SHOT-001 | 9D 真实截图 | 登录、DNS、SSH、VPN/RAG、个人历史/报告、B 空历史 | 文件来自当前版本真实浏览器运行画面；不含密码/Token/API Key；Mock、community 来源标识如实；未采集时不引用 PNG | 手工部分完成：`05`/`06` 已收录，`00`–`04` 待采集 | 无可替代的 pytest；采集规范见 `screenshots/README.md` |
| NP-REP-001 | Report / Export | 对同一 `record_id` 预览并重复导出 Markdown/JSON；非法格式/超限 | 不再次调用 Agent/LLM；ID、时间、正文稳定；内容完整且 Markdown 安全；非法请求被拒绝 | 自动 + 手工 | `tests/test_diagnosis_reports.py`、`tests/test_web_demo.py` |
| NP-SSE-001 | SSE | `POST /api/chat/stream`；正常、慢 worker、异常、客户端关闭；不可信换行文本 | `start` → keep-alive 可选 → `delta...` → `complete`，或安全 `error`；完整 response 一致；JSON 防事件行注入；session 被释放 | 自动 | `tests/test_chat_stream.py` |
| NP-SSE-002 | SSE 事实边界 | 检查 `TJUClient` 请求和 delta 时机 | 上游请求 `stream=false`；delta 只在完整 Agent 结果后分块；不得宣称模型 token streaming，不发生第二次模型请求 | 自动 + 文档审查 | `tests/test_netpilot_llm.py`、`tests/test_chat_stream.py` |
| NP-WEB-001 | Web manual demo | 先登录演示账号，再依次演示 DNS、SSH、VPN/RAG、个人历史与报告下载；手机宽度复核 | 中文界面可用；Tool Timeline、来源、指标、历史/报告与当前记录一致；退出后旧账号数据不再显示；响应式布局可读 | 手工待执行；静态表面有自动检查 | `tests/test_web_demo.py`、`tests/test_web_auth_ui.py`；原流程见 `docs/MILESTONE6_MANUAL_TEST_CASES.md` |
| NP-CLR-001 | 模糊问题主动澄清 | 仅输入“网络不行”或缺少目标/现象的信息 | **TODO：** 应先请求必要信息，避免随意选择大量 Tool；目前没有稳定、专门的自动测试，不能标记完成 | TODO / 手工观察 | 暂无可靠专项 pytest；后续应新增 Agent 行为测试 |

## 手工 Demo 详细步骤

先用专用非敏感测试凭据在首页注册并自动登录；确认右上角显示当前昵称/用户名，“我的诊断历史”初始为空。结束时退出，确认旧对话、报告与历史不再出现在页面；以第二账号登录，确认历史仍为空，再切回原账号复查其记录。
跨设备可信 LAN 配置、防火墙与真实截图按 [`MILESTONE9D_LAN_DEMO.md`](MILESTONE9D_LAN_DEMO.md) 验收；本矩阵的自动测试不证明现场 Wi-Fi 可达。

### DNS

1. 切换 `dns_failure`，确认切换后页面创建了新 session。
2. 输入 NP-SC-002 的问题。
3. 展开 Tool Timeline，确认 `ping_host` 为正常、`dns_lookup` 为发现异常，且 DNS Tool 自身 `success=true`。
4. 确认结论没有把域名解析失败写成“Tool 崩溃”。

### SSH

1. 切换 `tcp_ssh_blocked`。
2. 输入 NP-SC-004 的问题。
3. 确认 `tcp_check` 的目标和端口正确，`connected=false`，结论范围限于 SSH/TCP 22。

### VPN / RAG

1. 先查看 `/api/health`；只有 `rag_ready=true` 才继续。
2. 输入 NP-RAG-001 的问题。
3. 确认 Tool Timeline 显示知识参考，来源展示原始 URL 和 `community`。
4. 确认回答没有宣称来自天津大学官方现行政策。

### History / Report

1. 完成任一诊断并记录 `record_id`。
2. 新建 session 后从历史列表重新打开旧记录，确认问题、答案、diagnosis、metrics、Tool Timeline 和 sources 被完整恢复。
3. 预览报告并下载 Markdown/JSON；同一记录重复下载内容应稳定。
4. 重启服务后复查旧记录；若 `DIAGNOSIS_HISTORY_ENABLED=false`，应显示历史不可用但聊天仍可用。

### SSE

在浏览器 Network 面板确认聊天调用 `/api/chat/stream`，响应 Content-Type 是 `text/event-stream`。`delta` 逐块渲染不等于模型 token streaming；它们应在后台 Agent/Tool turn 完成后出现，最后的 `complete.response.answer` 应与拼接后的 delta 完全一致。

## 判定原则

- 以结构化证据为准，不要求模型自然语言逐字一致。
- Mock 结果只代表模拟场景；Local 结果只代表运行 NetPilot 的主机。
- `success=false` 与网络异常不是同义词；`abnormal`、`inconclusive`、`blocked` 必须区分。
- community 来源不能当作 official；RAG 参考不能当作实时检测。
- 未出现可靠自动测试的行为必须明确为 TODO，不用手工观察替代自动完成声明。
