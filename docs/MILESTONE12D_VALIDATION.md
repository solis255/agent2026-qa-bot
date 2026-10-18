# Milestone 12D — Guided Remediation Plan

TJU NetPilot 将自由文本建议补充为批准目录中的结构化、可反馈的手动计划。
**Plan ≠ Execution。** 不自动执行、提权、修改配置或重测；流程 completed 不等于网络 resolved。

## 修改范围与实际架构

新增 [`remediation/`](../src/netpilot/remediation/)：

- [`models.py`](../src/netpilot/remediation/models.py)：Step / Plan / Readiness / Feedback 契约。
- [`catalog.py`](../src/netpilot/remediation/catalog.py)：本地、不可变、版本控制的动作模板。
- [`safety.py`](../src/netpilot/remediation/safety.py)：启动与 Planner 的 fail-closed P0 校验。
- [`planner.py`](../src/netpilot/remediation/planner.py)：确定性选择、排序、适用条件与时效过滤。
- [`service.py`](../src/netpilot/remediation/service.py)：复用、失效、反馈、Trace 和紧凑上下文。
- [`integration.py`](../src/netpilot/remediation/integration.py)：非致命 Agent 集成，不增加 LLM / Tool 调用。
- [`api/remediation_routes.py`](../src/netpilot/api/remediation_routes.py)：计划与反馈 API，无 execute 路由。

修改 Agent/Session/Context/Trace、API schemas/presenters/routes、History/Report、Web 与配置。
新增八组 pytest、共享 fixture helper 和 jsdom runtime；旧测试仅适配历史 JSON v8 等契约变化。
没有修改 Network Provider、Tool Registry 或 RAG 检索/引用算法，没有清库。

## Models

`RemediationStep` 包括 UUID、template_id、等价动作 key、顺序、标题、理由、instructions、
risk、requires_admin、changes_system_state、reversible、rollback、verification、continue_condition、
OS/Target 适用范围、Evidence/source refs、status/outcome、user_note 与时间。

- status：pending / completed / skipped / failed。
- outcome：unknown / improved / no_change / worse。
- pending/skipped 的 outcome 必须 unknown，skip 不是“执行成功”。
- 可逆状态变化必须有 rollback；P0 Catalog 进一步要求所有改变状态的动作可回滚且不需管理员。

`RemediationPlan` 包括 plan_id/version、target_subject/version、task_version、实际诊断分类、
置信度、Evidence IDs、snapshot ID、readiness/reason、status、steps、受控来源元数据及时间。
另存 context/environment digest 与归一化 symptom，用于判断是否仍适用，不保存任意命令。
置信度为已有结构化等级/规则的粗粒度映射，不是校准概率、准确率或 benchmark。

Plan status：proposed / in_progress / completed / superseded / cancelled。
未开始 proposed；有反馈 in_progress；全部步骤结束 completed，**并不自动判定网络已恢复**。
不实现 reopen、Resolved/Unresolved、自动 Before/After 或 Support Package。

## 批准目录与安全政策

当前 13 个静态模板，分类映射自已有诊断 taxonomy：

| 分类 | 初始批准动作 |
|---|---|
| dns | 确认 VPN/Proxy 状态、保存内容后重开应用、重连、必要时查核认证/学校说明、记录现象 |
| gateway_connectivity | 查看连接状态、重连、必要时认证、记录现象 |
| campus_auth | 校园重连、条件化重新认证、核验学校/维护者说明 |
| vpn / proxy | 确认状态；满足条件时在原应用短暂停用对比，随后可恢复原连接 |
| web_only | 确认范围、重开应用、检查已声明 VPN/Proxy 的适用条件 |
| single_service | 仅重开受影响服务、核验服务状态与访问条件，不处理整个网络 |
| unknown | 非状态修改的确认/记录步骤；完全无依据则不生成步骤 |

模板 ID：`confirm_scope`、`check_link`、`reopen_browser`、`reopen_service`、
`check_service_status`、`confirm_vpn_proxy`、`disconnect_vpn`、`pause_proxy`、
`reconnect_network`、`campus_reconnect`、`campus_reauthenticate`、
`check_official_guide`、`record_and_escalate`。

默认只选择 risk=low、requires_admin=false 的批准模板。启动时和测试时校验 Catalog；
高/中风险、无回滚的状态变化、空 instructions/verification 或危险命令失败关闭。
P0 模板不包含命令型操作、URL 或用户输入插值；LLM 无法添加模板，API 不接收 command/risk/admin override。
危险校验覆盖 Invoke-Expression、iwr/iex、下载执行链、Winsock/reset、静态改 DNS、路由删除、
网卡禁用/驱动删除、注册表、服务、Firewall、防护禁用、执行策略、提权及破坏性 shell 等。

## Planner、Evidence 和 Readiness

流程：对象/任务过滤 → 排除历史与时效不明观察 → 读取已有诊断分类、支持假设与环境 →
readiness → Catalog candidates → 风险/适用条件过滤 → 等价动作去重 → 排序 → 限制数量。

- 只用当前 subject / target_version / task_version 的可复用证据；Knowledge Sources 不充当实时 Evidence。
- 现有分类如 `dns_resolution_failure`、`local_network_configuration`、`tcp_connectivity_failure`、
  `http_connectivity_failure` 映射到 Catalog 分类，不引入冲突的诊断枚举。
- 结构化 diagnosis 不能覆盖矛盾的新 Evidence；不从 LLM Answer 的自然语言反推计划。
- 支持假设必须关联当前新鲜 Evidence ID，possible/unsupported/error 不升级为已确认根因。
- 远程 user_client 只给客户端手动步骤；Host 标识为 NetPilot 服务主机；Mock 明确仅演示。
- 目前模板均为跨 OS 的 UI/应用级动作；不认识 OS 时也不会套用 Windows 命令。模板支持 OS whitelist。
- 网关正常、DNS 异常不选择“查看网线”模板；单服务异常不选择整网重连/校园认证。
- `REMEDIATION_MAX_STEPS=5`；优先确认/核验、应用级动作、重连、认证等，按模板顺序去重。

| Readiness | 判断与限制 |
|---|---|
| ready | 对象明确，存在当前可操作异常证据；只生成批准的低风险手动步骤，不宣称唯一根因 |
| limited | 明确的网页现象但没有快照，或只有历史/时效不明观察；仅通用、非状态修改步骤 |
| not_ready | 对象不明、类型/证据完全不足、只有无效采集且无现象，或批准动作都已尝试/跳过；steps=[] |

校园认证必须 campus_wifi / campus_wired 且有认证失效现象或 HTTP 511 依据；
off_campus 不生成校园认证。Wi-Fi 网卡类型不推断校园接入。
VPN / Proxy 严格区分 True / False / None；None 仅确认，False 不生成停用步骤。
True 也只有在普通公网网页场景、明确“不依赖/不影响远程管理，否则跳过”的前提下临时对比，提供恢复原应用连接的 rollback。
内网资源/单服务场景不这样处理，不将 WinHTTP 状态当作全部浏览器代理。

## 生成、复用和失效

- 自动：diagnose / state_changed / followup_action；是否有步骤取决于 readiness。
- 默认不自动：meta_feedback / report_request / history_analysis / general_question / knowledge_request。
- 用户明确问“怎么解决、给修复步骤、还是不行”等可请求计划；明确资料检索仍保留正常 RAG 流程。
- “怎么解决/还是不行”优先复用当前证据和计划，不重新调用网络工具，不为了 Planner 额外调用 LLM。
- 同上下文 POST 幂等，保留 plan_id/version、步骤状态和反馈。
- Target/task、诊断依据/分类、关键 OS/接入/VPN/Proxy/影响范围、新 Snapshot、快照时效变化使旧 Plan superseded。
  新生成 plan_version +1，最多保留最近 20 份历史计划；不把 Host 旧计划应用到 Client。
- 新计划会排除同一对象版本已完成、跳过或失败的等价动作；`campus_reconnect` 与 `reconnect_network`
  共用 key，不能换名绕过去重。no_change/worse 只记录，不提升风险。
- 全部批准动作都不适用时停止并要求补充证据，不生成风险更高的“下一招”。
- Planner 异常只记录安全错误类型并返回 not_ready/no active plan，不影响主诊断成功；不记录用户备注或异常原文。

## API 与权限

```http
GET /api/session/remediation-plan?session_id=<uuid>
POST /api/session/remediation-plan
PATCH /api/session/remediation-plan/steps/<step_uuid>
```

POST body 仅 `{"session_id":"..."}`。PATCH 示例：

```json
{
  "session_id": "00000000-0000-4000-8000-000000000001",
  "action": "complete",
  "outcome": "no_change",
  "user_note": "网页仍打不开"
}
```

action 为 complete / skip / fail；skip 只能 unknown，fail 不能 improved。
备注上限 500，提醒勿填并拒绝明显凭据/标识；不进入 LLM Context，不写日志。
请求 extra=forbid，不回显被拒绝的输入。仅 Cookie 当前用户拥有的 Session 可操作，跨账号统一 404，
未登录 401，busy/旧计划/已结束步骤冲突 409，存储失败 503。相同完成反馈幂等，不重复 Trace。
接口返回 `Cache-Control: no-store`。不存在执行或远程重测接口。

更新在 Session 锁内以 draft → DB persist → memory commit 完成，失败不提交反馈。
不会增加 Turn / Tool / Network Tool 次数，不会虚构一条用户聊天。

## Context、Trace、History 与报告

Context Builder 新增 `REMEDIATION STATUS`：版本、对象/任务、status、每个等价动作的状态/outcome。
不同对象/任务的计划明确为 superseded；不注入原始用户备注、完整 Plan JSON 或命令。
System Prompt 明确不重复无效步骤、尊重跳过、不宣称已执行或 resolved，不生成 Catalog 外动作。

Trace 仅本地可解释事件：“生成修复计划”“用户执行修复步骤”，反馈区分完成/跳过/失败。
使用 `event_origin=remediation`，保留事件身份避免跨 Turn 重复，不是 Raw CoT；Trace 开关仍生效。
API 操作发生在首轮聊天前时暂存事件，在首个真实 Turn 一并持久化，不造空记录。

History Snapshot **v8**，SQLite 表结构仍 **v3**；v1–v7 缺失计划时为 None，绝不从旧 Answer 反推。
保存当前 Plan、最近历史失效 Plan、steps/status/outcomes、Evidence/source refs。
已有记录的反馈直接更新同一 Session 行，conversation_turns 不变；普通刷新从服务端恢复。
SessionStore 仍为进程内存；重启后旧 History 可读，但不自动重新激活旧 Session 或步骤。

Markdown / JSON Report 包含计划、风险、理由、操作、验证、回滚、状态/反馈、来源和用户备注。
Markdown 逃逸用户内容，Web 历史只读，失效计划不提供反馈按钮。
completed 始终只表示流程结束，不生成网络恢复结论。

## Web 与 Inline Citation

侧栏新增默认折叠“修复计划”：步数、ready/limited/not_ready 说明、风险标签、理由、操作、验证、回滚与停止条件。
突出首个 pending；用户可“已完成 / 跳过 / 执行失败”，并选有改善/没有变化/变差/不确定、填可选备注。
完成/跳过状态仍可展开查看，不提供重新执行、运行命令或一键修复。
同 Session 更新不关闭父折叠区；新 Session、切换账号、场景重置清空旧计划显示。

校园步骤 source_refs 使用既有 Marked + DOMPurify + Inline Citation renderer。
优先 official / maintainer；仅 community 时标记“需官方核验”，只建议核验，不直接照社区资料修改设置。
无来源依赖的通用步骤不挂引用；不恢复独立 Sources 面板。

## 自动化矩阵

| ID | 验收内容 | pytest |
|---|---|---|
| GR-01 | Remote DNS 快照、低风险、客户端绑定、零新增 Tool | `test_remediation_planner.py` |
| GR-02 / 03 | 有限网页现象 / 对象或证据不明 | `test_remediation_planner.py`, `test_remediation_api.py` |
| GR-04 / 05 | 校园接入 + 认证信号 / 校外禁认证 | `test_remediation_planner.py` |
| GR-06 / 07 | VPN/Proxy 三态与依赖条件 | `test_remediation_planner.py` |
| GR-08 / 09 | Target/Environment/新快照失效，单服务步骤 | `test_remediation_api.py`, `test_remediation_planner.py` |
| GR-10 / 11 | 完成 no_change / 跳过不可当作已执行 | `test_remediation_api.py`, `test_remediation_models.py` |
| GR-12 | 当前及新快照计划不重复已尝试等价动作 | `test_remediation_planner.py`, `test_remediation_context.py` |
| GR-13 / 14 | 高风险、危险命令、无回滚模板失败关闭 | `test_remediation_safety.py`, `test_remediation_catalog.py` |
| GR-15 | stale/skew 仅有限通用步骤 | `test_remediation_planner.py` |
| GR-16 | Alice/Bob ownership、认证、busy、override 拒绝 | `test_remediation_api.py` |
| GR-17 / 18 | SQLite 重开、完整会话不变、Report/JSON、Legacy v1–v7 | `test_remediation_history.py` |
| GR-19 | Trace 事件与幂等，不注入备注 | `test_remediation_context.py`, `test_remediation_history.py` |
| GR-20 | 折叠、顺序、首个 pending、反馈、引用、历史/退出/XSS | `test_remediation_ui.py`（8 项 jsdom） |

## 本次验证与人工验收（2026-10-19）

修改前普通沙箱运行：15 failed / 616 passed，失败集中在沙箱临时数据库认证 503，伴随 WinError 5。
未因此改认证或正式数据库；正常权限、隔离目录重跑基线：**631 passed in 118.66s**。
最终全量命令：

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-gr-handoff --tb=short
```

结果：**711 passed in 123.42s**，无失败、无跳过；新增 80 项 12D 用例，含 8 项 jsdom，
全仓共 56 项 DOM 测试。此前新建/刷新会话 readiness 默认值不一致已修正并全量复验。
`git diff --check`、新增文本空白与修改的 Markdown 相对链接检查均通过。
已清理本次仓库内的 pytest 临时目录；正式 `.env` / SQLite 未修改，未提交或推送。

| 人工 Case | 自动化结果 | 真实人工验收 |
|---|---|---|
| 1 DNS Failure | 合成 Remote Windows 快照、DNS 多目标失败、网关正常；低风险步骤、无管理员/DNS 修改、均有验证 | 待真实浏览器/设备确认 |
| 2 VPN | True + 普通网页 + 非依赖条件可临时断开，带恢复原连接回滚；False/None/内网不这样做 | 待用户手动确认，不代操作 VPN |
| 3 User Feedback | 完成重连 no_change → “还是不行”复用状态，当前及新快照计划均不重复重连 | 待真实浏览器操作确认 |
| 4 Target Switch | Client 旧计划 superseded，新计划绑定 Host；尚无 Host 证据时先 not_ready，不借用 Client Evidence | 待真实浏览器操作确认 |

测试使用 Fake LLM、受控 Provider、合成快照、ASGI TestClient 和 jsdom；没有为了验收改变真实网络，
没有执行任何修复动作。自动化通过不等于已完成上述四个真实人工 Case。
