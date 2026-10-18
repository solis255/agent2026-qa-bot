# Milestone 12A：Environment Profile

本阶段仅实现当前 Session 的用户网络环境画像，不实现 Diagnostic Target、Client Snapshot、诊断脚本、自动修复、Support Package 或远程命令。

## 文件清单

- 新增模型与合并/规则：[environment.py](../src/netpilot/environment.py)。
- Session / Agent 集成：修改 [session.py](../src/netpilot/agent/session.py)、[task_state.py](../src/netpilot/agent/task_state.py)、[AgentResult](../src/netpilot/agent/schemas.py)、[orchestrator.py](../src/netpilot/agent/orchestrator.py)、[context_builder.py](../src/netpilot/agent/context_builder.py)、[prompts.py](../src/netpilot/agent/prompts.py)。
- API / 应用装配：修改 [routes.py](../src/netpilot/api/routes.py)、[presenters.py](../src/netpilot/api/presenters.py)、[公开 schemas](../src/netpilot/models/schemas.py)、[models 导出](../src/netpilot/models/__init__.py)、[main.py](../src/netpilot/main.py)。
- 持久化/报告：修改 [history.py](../src/netpilot/history.py)、[reports.py](../src/netpilot/reports.py)。
- 前端：修改 [index.html](../web/index.html)、[app.js](../web/app.js)、[style.css](../web/style.css)、[package.json](../web/package.json)。
- 新增六组测试：[model](../tests/test_environment_profile_model.py)、[merge](../tests/test_environment_profile_merge.py)、[API](../tests/test_environment_profile_api.py)、[context](../tests/test_environment_profile_context.py)、[history](../tests/test_environment_profile_history.py)、[UI](../tests/test_environment_profile_ui.py)，以及 [DOM runtime](../tests/web_environment_runtime.cjs)。
- 原测试仅更新快照版本断言：[conversation_persistence](../tests/test_conversation_persistence.py)、[reasoning_trace_persistence](../tests/test_reasoning_trace_persistence.py)。文档修改 [README](../README.md)，新增本验收文档。

## 数据与来源

模型位于 [environment.py](../src/netpilot/environment.py)，请求/响应位于 [schemas.py](../src/netpilot/models/schemas.py)。

| 字段 | 合同与默认值 |
|---|---|
| client_mode | server_local / remote_browser / mock / unknown；Mock 应用初始化为 mock，Local Web/API 为 remote_browser，不通过 localhost 猜同机 |
| os_family | windows / macos / linux / android / ios / unknown |
| os_version | 可选的显式数字版本；不从 UA 猜测，OS 改变时清除不匹配旧版本 |
| network_access | campus_wifi / campus_wired / off_campus / mobile_hotspot / unknown |
| vpn_enabled、proxy_enabled | 严格 bool 或 null；未提到、用户选择不确定时均为 null，不是 false |
| affected_scope | all_network / web_only / single_service / internal_resource / unknown |
| affected_service | 可选服务名/域名标签，最大 80 字符；拒绝 URL、IP、硬件标识、凭据形态与 HTML |
| browser_online、browser_language | 可选严格 bool、归一化语言标签 |
| effective_type | 可选 slow-2g / 2g / 3g / 4g；不是物理接入方式 |
| estimated_rtt_ms、estimated_downlink_mbps | 可选有限非负估计；浏览器不支持时为空，非测量证据 |
| updated_at | 最近一次画像值或来源实质改变的 UTC 时间 |
| field_sources | 每字段 source（browser/user/server/mock/inferred）和 confidence（high/medium/low） |

合并规则为 `user > mock > browser > server > inferred`；同来源按最新显式更新。
只合并实际提供的字段，浏览器 unknown OS 不覆盖已知 OS；重复相同上报不修改画像时间。
用户/Mock 为 high，浏览器 OS 为 medium，浏览器网络估计为 low；置信度表示来源性质，不表示 Tool 已验证。

规则提取只处理保守的明确表述。问题、假设、第三方叙述和未来意图不转成事实；歧义场景请使用手动表单。
不会因只说“没开 VPN”就把 Proxy 也设为 false。当前不尝试覆盖所有自然语言表达，也不新增环境分类 LLM 请求。

## API 与 Session

| 接口 | 行为 |
|---|---|
| POST /api/session | 返回新 Session 与初始化画像 |
| GET /api/session/{session_id} | 当前账号拥有的 Session 与权威画像；响应 no-store |
| PATCH /api/session/environment/browser | session_id + 浏览器白名单字段，服务端固定 browser provenance |
| PATCH /api/session/environment/user | session_id + 可编辑字段，服务端固定 user provenance |

所有接口沿用登录 Cookie 和 Session ownership。跨用户/已失效 Session 返回 404，未登录 401；
诊断进行中 PATCH 返回 409。额外字段、任意 provenance/source、完整 UA 等请求被 Pydantic extra=forbid 拒绝。
422 响应不会回显被拒绝的输入值；存储错误返回安全 503，失败时不提交内存画像。

Browser PATCH 示例：

```json
{"session_id":"11111111-1111-4111-8111-111111111111","os_family":"windows","browser_online":true,"browser_language":"zh-CN"}
```

User PATCH 示例：

```json
{"session_id":"11111111-1111-4111-8111-111111111111","network_access":"campus_wifi","vpn_enabled":false,"proxy_enabled":null,"affected_scope":"web_only"}
```

[SessionStore](../src/netpilot/agent/session.py) 初始化并防御性复制画像，普通更新不会改变 Evidence、已执行 Tool Signature、turn_index 或 task_version。
已有明确 state_changed 重新取证逻辑保留；本阶段未新增环境版本或 Before/After 机制。
普通 Chat 与 SSE 共享同一 SessionTaskState 和保存路径，完成响应包含同一 environment_profile。
Session 锁覆盖 Turn 完成与历史持久化，避免 PATCH 与最终快照互相覆盖。
切换/删除激活 Mock 场景创建新 Session 时，前端同步清空旧画像并接收新 Session 初始化画像。

## Agent Context 与可解释边界

[Context Builder](../src/netpilot/agent/context_builder.py) 添加紧凑 `ENVIRONMENT PROFILE`：归一化字段、简单的 user confirmed/browser context 标签，不注入完整 field_sources JSON。
Agent 正常循环及 Knowledge Finalization 均收到画像，跨 Turn 复用，不增加提取 LLM Call。
System Prompt 和上下文明确：

- unknown 不等于 false；用户确认优先于浏览器推断。
- browser_online=true 不证明互联网健康，effective_type=4g 不证明蜂窝/热点接入。
- 校园 WiFi 不意味着已验证 DNS 或网关。
- remote_browser 下 Local Tools 仅检测 NetPilot 服务端，不能声称测了用户设备。
- Environment 是上下文，Evidence 是真实 Tool 观察，Reasoning Trace 是结构化决策摘要，三者不能混写。

关键环境首次建立/改变后，在下一实际 Turn 可记录“确认用户环境”摘要，明确非检测证据，不生成伪造 Evidence。
同画像后续 Turn 与普通浏览器重复上报不重复添加环境确认条目。

## 前端与刷新

[index.html](../web/index.html)、[app.js](../web/app.js)、[style.css](../web/style.css) 提供默认折叠“当前环境”卡片，支持六项字段编辑；单一服务才显示服务框。
三态 VPN/Proxy 的“不确定”发送 null；实际改动或主动确认的选择才获得 user provenance，不把未触碰字段统统标为用户确认。
手动确认与当前浏览器值相同时也可通过选择变更确认，后续浏览器上报不能覆盖。

仅 feature-detect 读取 navigator.onLine、language、userAgentData.platform/platform、connection.effectiveType/rtt/downlink。
不请求位置权限，不读取/保存完整 User-Agent、公网 IP、MAC、SSID/BSSID、Cookie/Token、浏览历史、精确位置或设备序列号。
受影响服务框只接受服务标签，不应粘贴任何敏感标识。该限制专指 Environment Profile，不改变原有合法 Tool 证据与对话记录的合同。

页面 URL 片段仅保存不透明 Session ID；刷新 GET 服务端恢复并重新上报低风险字段。
不使用 localStorage/sessionStorage 保存画像。其他账号拿到该片段也不能读取/修改；404 时创建自己的新 Session。
此改动不持久化整个运行时 Session：服务重启、容量淘汰或场景清理后，旧 Session 不能继续；已完成诊断的画像仍可从所属账号历史查看。
历史详情显示历史画像且禁止在该视图修改；不会把历史画像写回当前活跃 Session。继续提问时恢复当前 Session 画像。

## History / Report

[history.py](../src/netpilot/history.py) 的 SNAPSHOT_SCHEMA_VERSION 从 4 升至 **5**，SQLite 表结构/metadata 仍为 **3**。
每个用户每个 Session 仍一条累计记录，保存最新画像；对已有记录修改环境不增加 Turn、不修改诊断时间、指标、Trace 或 transcript。
尚无完成 Turn 时只保存进程内 Session 画像，不创建空诊断记录；第一轮完成后随记录写入 SQLite。
旧 v1～v4 缺字段时使用稳定 unknown/null 默认值，不根据旧消息、服务器 OS 或旧结论反推。

[reports.py](../src/netpilot/reports.py) 的 Markdown 加入“用户环境”清单，不显示 field_sources；JSON 导出保留画像及 provenance。
完整 conversation_turns、RAG source/citation、Reasoning Trace 与原有报告大小限制保留。

## 自动验收矩阵

| ID | 验收 | 测试文件 |
|---|---|---|
| EP-01 | 默认未知、Mock / Local 安全 client_mode | test_environment_profile_model.py / test_environment_profile_api.py |
| EP-02 | 浏览器白名单上报与固定来源 | test_environment_profile_api.py / test_environment_profile_ui.py |
| EP-03 | 用户 macOS 覆盖 browser Windows，后续 browser 不覆盖 | test_environment_profile_merge.py / test_environment_profile_api.py |
| EP-04 | 未提到/显式清除保持 null，不能当 false | test_environment_profile_model.py / test_environment_profile_merge.py |
| EP-05 | connection/userAgentData 不支持时跳过 | test_environment_profile_model.py / test_environment_profile_ui.py |
| EP-06 | 隐私字段拒绝、422 不回显、无 geolocation/UA 读取、DOM 纯文本 | test_environment_profile_model.py / test_environment_profile_api.py / test_environment_profile_ui.py |
| EP-07 | 跨账号 GET/PATCH 404、未登录 401、诊断中 409 | test_environment_profile_api.py |
| EP-08 | Context/Knowledge Finalization 收到画像、不增加 LLM 请求 | test_environment_profile_context.py |
| EP-09 | 三 Turn 混合 Chat/SSE 一行 History，重开 SQLite 后画像正确 | test_environment_profile_history.py |
| EP-10 | v1～v4 缺字段保持未知，原 transcript/Trace 不变 | test_environment_profile_history.py |
| EP-11 | Markdown 不含 provenance，JSON 保留 provenance | test_environment_profile_history.py |
| EP-12 | 编辑保存、同值确认、服务框显隐、服务端刷新、账号与历史隔离 | test_environment_profile_ui.py + web_environment_runtime.cjs |

额外验证：优先级所有来源两两组合、普通更新保留 Evidence/version、重复环境不重复 Trace、存储失败不提交画像、Mock 新 Session 不带旧画像。

## 验证记录与人工状态

2026-10-18 修改前仓库干净，基线：`420 passed in 62.77s`。
测试采用受控 LLM、Mock Provider、独立 SQLite 临时目录；前端采用实际 HTML/JS 与本地 jsdom，不访问真实 tju-llm。

最终运行：

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-ep-verified
# 494 passed in 74.12s，无失败、无跳过；相比 baseline 新增 74 项。
cd web
npm test
# 33 项通过（既有 25 + 新增 8 项 Environment DOM 检查）
cd ..
git diff --check
# 退出码 0
```

README 与本文档的 Markdown 相对链接已检查存在；原 README 不存在的 CONTRIBUTING.md 引用已移除。
本次测试临时目录在验证后清理，不修改用户数据、实际数据库或 .env；未提交/推送 Git。

三个需求场景的自动检查均覆盖，真实浏览器人工验收尚未执行：

| 人工 Case | 自动验证 | 人工状态 |
|---|---|---|
| 1 Windows 自动采集 + 手动校园 WiFi/VPN 关闭/Proxy 不确定/仅网页，刷新保留 | EP-BROWSER、EP-EDIT、EP-REFRESH + API 测试覆盖 | 待真实 Windows 浏览器实操 |
| 2 明确自然语言更新四字段、Proxy 仍未知 | merge/context/history 测试覆盖，真实 Orchestrator + 受控 LLM | 待真实应用实操 |
| 3 手动 macOS 不被后续 browser Windows 覆盖 | 来源两两组合、API 重复上报、表单保存测试覆盖 | 待真实浏览器实操 |

没有伪造截图或把 DOM 检查冒充真实浏览器手工结果。
