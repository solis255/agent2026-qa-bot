# Milestone 12B：Diagnostic Target Awareness

只实现诊断对象、执行位置、能力限制与证据隔离。没有 Client Snapshot、PowerShell、上传 JSON、浏览器 Ping/DNS、自动修复、Support Package 或远程命令。

## 审计与基线

2026-10-18 修改前工作区干净，基线：`494 passed in 91.32s`。
当前没有 `src/netpilot/providers/`；真实实现是 [local_network.py](../src/netpilot/tools/local_network.py) 和 [mock_network.py](../src/netpilot/tools/mock_network.py)。
Local 使用服务进程的 psutil、socket、DNS resolver、HTTP transport 和受限 subprocess；不能观察远程浏览器的系统 DNS、网关和路由。
Mock 返回确定性场景数据，不是现场网络测量。本阶段未修改这两个 Provider 的实现或网络安全合同。

原 Registry 无 execution_scope；原签名只有 tool+canonical args；原 Evidence 没有设备对象元数据。
12A 已提供 EnvironmentProfile、Session ownership 与快照 v5；数据库结构/metadata 为 v3。

## 文件清单

| 类别 | 新增 / 修改 |
|---|---|
| 新增核心 | [diagnostic_target.py](../src/netpilot/diagnostic_target.py)、[target_capabilities.py](../src/netpilot/agent/target_capabilities.py) |
| Session / Agent | [session.py](../src/netpilot/agent/session.py)、[task_state.py](../src/netpilot/agent/task_state.py)、[Agent schemas](../src/netpilot/agent/schemas.py)、[orchestrator.py](../src/netpilot/agent/orchestrator.py)、[context_builder.py](../src/netpilot/agent/context_builder.py)、[prompts.py](../src/netpilot/agent/prompts.py) |
| Tool 安全 | [tool_registry.py](../src/netpilot/agent/tool_registry.py)、[tool_policy.py](../src/netpilot/agent/tool_policy.py)、[tool_signature.py](../src/netpilot/agent/tool_signature.py) |
| API / 装配 | [routes.py](../src/netpilot/api/routes.py)、[presenters.py](../src/netpilot/api/presenters.py)、[public schemas](../src/netpilot/models/schemas.py)、[models exports](../src/netpilot/models/__init__.py)、[main.py](../src/netpilot/main.py) |
| 持久化 / 报告 | [history.py](../src/netpilot/history.py)、[history_context.py](../src/netpilot/history_context.py)、[reports.py](../src/netpilot/reports.py) |
| Web | [index.html](../web/index.html)、[app.js](../web/app.js)、[style.css](../web/style.css)、[package.json](../web/package.json) |
| 新增模型 / 推导 / API 测试 | [model](../tests/test_diagnostic_target_model.py)、[derivation](../tests/test_diagnostic_target_derivation.py)、[API](../tests/test_diagnostic_target_api.py) |
| 新增安全 / 证据测试 | [tool policy](../tests/test_target_tool_policy.py)、[evidence scope](../tests/test_target_evidence_scope.py)、[dedup](../tests/test_target_dedup.py)、[context](../tests/test_target_context.py) |
| 新增持久化 / UI 测试 | [history](../tests/test_target_history.py)、[UI](../tests/test_target_ui.py)、[DOM runtime](../tests/web_target_runtime.cjs)、[受控测试替身](../tests/target_helpers.py) |
| 已有测试适配 | [chat API](../tests/test_chat_api.py)、[conversation](../tests/test_conversation_persistence.py)、[12A history](../tests/test_environment_profile_history.py)、[evidence memory](../tests/test_evidence_memory.py)、[trace](../tests/test_reasoning_trace.py)、[trace persistence](../tests/test_reasoning_trace_persistence.py)、[task state](../tests/test_task_state.py) |
| 文档 | [README](../README.md)、[architecture](architecture.md)、新增本验收记录 |

已有测试适配限于 v6 版本、新元数据合同、带对象的签名、Mock 可见标签、spy 透传 target，以及明确模拟对象的测试夹具；没有删除原有验收断言。

## DiagnosticTarget schema

| 字段 | 合同 |
|---|---|
| subject | user_client / netpilot_host / mock_client / unknown |
| relationship_to_netpilot | same_host / remote / simulated / unknown |
| execution_context | netpilot_host / mock_provider / unavailable，由实际 Provider 决定 |
| source | user / mock / environment / system / inferred |
| confidence | high / medium / low |
| target_version | 严格正整数，默认 1；subject 或 relationship 实质变化时 +1 |
| limitation_code | none / remote_client_not_directly_observable / unknown_target / provider_target_mismatch |
| updated_at | UTC 更新时间；同对象重复选择不更新时间/版本 |

没有可写的 `local_tools_applicable`。模型 extra=forbid，能力由 `TargetCapability` 动态计算。
来源选择优先级：`user > mock > environment > system > inferred`。
同来源最新显式选择优先；较低优先级的环境默认值不会覆盖用户选择。
execution_context 始终重算，不跟随用户 source 选择。

## 安全推导与显式选择

| 环境 / Provider | 默认对象 | 关系 | 执行位置 | 限制 |
|---|---|---|---|---|
| Mock Provider | mock_client | simulated | mock_provider | none（仅模拟） |
| remote_browser + Local | user_client | remote | netpilot_host | remote_client_not_directly_observable |
| server_local + Local，未可靠确认同机 | user_client | unknown | netpilot_host | unknown_target |
| server_local + 受信嵌入端确认同机 | user_client | same_host | netpilot_host | none |
| unknown + Local | unknown | unknown | netpilot_host | unknown_target |
| 环境声称 Mock，但实际 Local | mock_client | simulated | netpilot_host | provider_target_mismatch |

当前 Web/API 没有可靠的同机确认机制，不根据 127.0.0.1、浏览器声明或“本机”措辞授予客户端直接检测能力。
`same_host_confirmed` 仅是受信调用方的推导参数，不在 HTTP 请求中开放。

“检查这台 NetPilot 服务器的 DNS”与“检查运行 NetPilot 的这台服务器”可通过保守本地规则明确选 Host；
“我的电脑上不了网”可选 user_client。问题中的引述、第三方假设、否定检查请求不进行对象切换。
不新增独立 LLM 分类调用；未明确选择时使用当前持久 Session 对象。

Mock UI 只读，普通用户不能用 Target PATCH 把模拟终端变成真实设备。
Mock 里普通“我的电脑”场景仍诊断模拟终端；明确要求检查真实服务器时安全说明当前不支持，不用 Mock 结果冒充。

## Tool scope 与双重门禁

| Tool | Local execution_scope | Mock execution_scope |
|---|---|---|
| get_network_info | execution_host | mock_target |
| ping_host | execution_host | mock_target |
| dns_lookup | execution_host | mock_target |
| tcp_check | execution_host | mock_target |
| http_check | execution_host | mock_target |
| traceroute | execution_host | mock_target |
| knowledge_search（知识库就绪时） | target_neutral | target_neutral |

scope 是服务端 `ToolSpec` 元数据，不把额外属性塞进 tju-llm 的原生 function schema。
ToolPolicy 不维护网络工具名称长名单：按 Registry metadata + Intent + TargetCapability 筛选。
即使模型请求未提供的网络 Tool，Orchestrator 也不会分派；Registry 在调用 handler 前再次动态校验 scope。
对没有明确目标的 Local Registry 直接调用同样 fail closed。

能力矩阵：

- Local netpilot_host：允许 execution_host。
- Local user_client + 受信 same_host：允许 execution_host。
- Local remote/unknown user_client、unknown 对象：不允许 execution_host。
- Mock mock_client + simulated：允许 mock_target；其他真实对象不能借用模拟结果。
- target_neutral 可用，但仍受 Intent 与 RAG 配额/就绪状态约束。
- report_request / meta_feedback / history_analysis 继续 0 Network Tool；原有 Tool 参数、SSRF、shell=False 和输出限制保留。

远程网络诊断当前采用保守的本地响应路径：基于用户现象和 EnvironmentProfile 追问/给安全建议，不要求模型编造检测结果。
没有系统级证据时，不能证明用户 DNS 正常。明确知识请求仍走原 RAG / Knowledge Finalization / Citation 流程。
限制说明按对象版本去重，后续普通追问使用短提示，不反复大段声明。
Host/Mock 网络回答加对象标签并规范“你的设备/DNS”等措辞；知识回答、反馈、历史分析不作粗暴全文替换。

## Evidence、Dedup、Context

`AgentToolStep`、`EvidenceRecord`、ToolCallView、EvidenceView 新增：target_subject、target_version、execution_context、execution_scope。
网络调用从当前权威 Target 绑定元数据；客户端不能在 function args 注入这些值。
RAG 明确为 target_neutral，subject=unknown、execution_context=unavailable，不伪装成终端实时证据。

签名示例：

```text
netpilot_host:v2:dns_lookup:{"domain":"github.com"}
user_client:v3:dns_lookup:{"domain":"github.com"}
target_neutral:v1:knowledge_search:{"query":"vpn"}
```

网络 subject/version 不同的相同 tool+args 不复用。切回 Host 也是新版本，需要重新取证。
RAG 的查询复用仍是对象无关参考；现有每 Turn 最多两次与相似 query 去重保留。
task_version 与 target_version 相互独立；对象切换不伪造一次“网络状态改变”。

`reusable_evidence()` 和 Context Builder 都只接受当前 subject/version 的网络记录；Coverage、Hypothesis、已执行签名随之重算。
Context 新增规范化 `DIAGNOSTIC TARGET`，说明对象、关系、执行位置、直接观察能力与限制；正常循环与知识整理均接收。
不仅过滤结构化记录：运行时消息也记录对象版本，`begin_turn()` 只把当前对象版本消息传给模型。
自然语言当轮切换会丢弃旧对象模型 history；完整 transcript 仍保留，不能偷偷把旧 Host 回答当新 Client 事实。
Presenter 也防御性排除已标记的错对象网络观察，不将其放进当前 diagnosis.evidence。

## API / UI / Trace

```http
PATCH /api/session/diagnostic-target
```

```json
{"session_id":"11111111-1111-4111-8111-111111111111","subject":"netpilot_host"}
```

只允许 subject=user_client / netpilot_host；执行位置、关系、版本、source、limitation、能力均不接受客户端提交。
未登录 401，跨账号/失效 Session 404，忙碌会话 409，Mock 切换 409，伪造字段 422且不回显输入，存储失败安全 503且内存不提交。
POST/GET Session、Chat/SSE complete、场景重置响应均携带权威对象。
刷新仍沿用 URL 片段中的 Session ID 从服务器读取，不使用 localStorage。

UI 显示对象/直接检测能力/执行位置，允许 Local 切换浏览器设备与服务主机，Mock 只读。
切换后清除当前诊断卡/Timeline 的旧结果展示，保留可审计对话。
历史卡显示历史对象并只读，不覆盖当前 Session 对象；退出/账号变化清空前端对象状态。
Timeline 每个网络步骤标明对象、版本和执行位置，RAG 显示“对象无关参考，非设备检测”。

Reasoning Trace 在下一实际完成 Turn 记录“确认诊断对象”/“切换诊断对象”及“限制不适用的检测”。
同对象不重复确认；同版本的限制只记录一次，模型同时越权请求六个工具也不刷六条限制。
API 选择本身不伪造空 Turn/模型调用；最新对象会立即持久到已有 History 行，Trace 随实际 Turn 写入。

## History / Report

快照 **v5 → v6**，SQLite 表结构/metadata 仍为 **v3**，不添加新表。
每账号每 Session 一行，保存最新 diagnostic_target；conversation_turns 保存实际 Turn 的对象/版本，旧 Tool 观察继续保留。
同对象的历史指标仍按 Session 累计，跨对象后也是累计，不代表新对象执行过历史工具。
v1～v5 缺 Target 时使用稳定 unknown/unavailable，不依据旧 Tool、消息、OS 或 IP 反推。

切换后立即重置当前诊断视图，避免既有 Host primary_issue 被继承成 Client 故障结论。
报告含“诊断对象”节：对象、关系、执行位置、直接能力与对象版本。
Report `tool_calls` 仅为当前对象适用的工具及中性参考；其他网络工具位于 `archived_tool_calls`，
Markdown 置于“其他对象的历史检测（不用于当前结论）”。完整对话和 Session Trace 保留并明确为历史。
若选择了新对象但尚未完成该对象一轮诊断，报告明确“尚无当前对象结论”，不会把上一轮 Host 回答填成 Client 结论。
JSON 导出包含 Target、当前/归档工具元数据、完整对话与 Trace；Markdown 仍不输出环境 field_sources。
持久化历史分析也带对象标签且筛掉记录当前对象不适用的网络观察，不能跨对象证明当前设备状态。

运行时 Session 仍为有界内存；正常刷新可恢复，服务重启/淘汰后不承诺恢复活跃 Agent。
已完成会话的 Target、环境与完整历史保留在 SQLite，可从所属账号历史查看。尚未完成 Turn 的新 Session 不创建空诊断记录。

## 验收矩阵

| ID | 自动检查 |
|---|---|
| DT-01 | remote_browser 默认 user_client / remote / netpilot_host / 受限 |
| DT-02 | 六个 Local 网络 handler 实际调用计数为 0；模型越权请求同样不执行 |
| DT-03 | Remote 下 RAG 检索、知识整理和引用可用，知识证据不绑设备 |
| DT-04 | 显式 Host 允许 Local handler，Evidence/回答标明服务主机 |
| DT-05 | Mock 正常检测与模拟措辞，不能声称真实服务器已检测 |
| DT-06 | unknown 提前澄清，不调用网络 handler 或额外 LLM |
| DT-07 | Host→Client：版本+1，旧 Evidence/coverage/hypothesis/history 不进入当前推理 |
| DT-08 | 同对象复用、不同对象/版本不复用，切回 Host 重新执行 |
| DT-09 | 高置信度自然语言 Host/User 选择与来源优先级组合 |
| DT-10 | Auth/ownership、忙碌、伪造字段、Mock 只读、存储失败 |
| DT-11 | Context / Knowledge Finalization 的对象说明及旧事实隔离 |
| DT-12 | Chat/SSE 一致、SQLite 重开后目标与完整会话仍存在 |
| DT-13 | v1～v5 无 Target 保持未知，旧 Tool 不反推真实设备 |
| DT-14 | 建立/切换/限制 Trace 合理且去重 |
| DT-15 | Timeline Host / Mock / target-neutral 标签、DOM 安全与历史只读 |

测试不依赖真实 tju-llm，不探测真实主机网络。Local 场景使用标记为 Local 的受控 Provider 替身计数 handler，
以验证生产 Registry/Policy/Orchestrator 是否真正拦截，而不是只检查回答文字；这不是现场 Local 测量结果或 benchmark。
DOM 测试加载实际 Web 文件与 jsdom，不冒充人工浏览器操作。

## 四个人工场景的实际状态

最终自动验证：

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-dt-final --tb=short
# 557 passed in 94.51s，无失败、无跳过；较 baseline 新增 63 项。
cd web
npm test
# 40 项 DOM 检查通过（既有 33 + 新增 7 项 Target UI 检查）
cd ..
git diff --check
# 退出码 0
```

README、architecture 与本验收文档的相对链接已检查存在。测试临时目录在验证后清理；
未修改 .env 或用户实际数据库，未提交/推送 Git。

| 场景 | 自动结果覆盖 | 人工实际状态 |
|---|---|---|
| 1 另一台设备访问，诊断自己的网页故障 | Remote 默认、handler=0、受限 UI、服务端刷新均有测试 | 尚未在另一台电脑实操 |
| 2 切换服务主机，诊断 Host DNS | Local 受控 handler 执行、Evidence/措辞/Timeline 已测试 | 尚未做真实 Local DNS 浏览器演示 |
| 3 Host DNS 正常后切回用户设备 | API/自然语言切换、版本隔离、无旧证据、报告归档已测试 | 尚未做跨设备人工演示 |
| 4 Mock dns_failure 模拟终端 | 原有 DNS 场景回归 + 新 Target 模拟语义/只读 UI 检查 | 尚未新拍真实浏览器截图 |

未伪造人工验收、截图或网络测量。
