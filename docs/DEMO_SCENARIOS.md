# Milestone 12I — Real-world Demo & Acceptance Scenarios

本阶段把 12A–12H 的生产功能串成可复现的演示。所有 Fixture 都是 **DEMO / 模拟数据**，不能作为真实网络测量或实际报修依据。主展示 A + B 预计 5–7 分钟；不要求现场网络恰好故障。

## 准备、启动与登录

从仓库根目录运行，先按 README 安装 Python 依赖。前端 DOM 测试另需 `cd web` 后 `npm ci`，再回到仓库根目录。

Windows PowerShell 示例（独立演示数据库，不清理已有用户库）：

```powershell
.\.venv\Scripts\Activate.ps1
$env:DEMO_MODE="true"
$env:TOOL_MODE="mock"
$env:SCENARIO_SWITCH_ENABLED="false"
$env:RAG_ENABLED="false"
$env:DIAGNOSIS_HISTORY_ENABLED="true"
$env:DIAGNOSIS_DB_PATH=".cache/competition-demo.db"
python -m uvicorn netpilot.main:app --host 127.0.0.1 --port 8001
```

打开 `http://127.0.0.1:8001/`，注册专用演示账号并登录。Auth、Ownership、Privacy 和 ToolPolicy 始终启用。右侧展开“演示模式 · Demo / Mock”，选择场景，点击“创建 / 切换当前演示”。“填入推荐测试语句”只填输入框，需要操作者自行发送。

`DEMO_MODE` 默认 `false`：Selector 隐藏，Demo API 返回 404。上面的环境变量只影响当前终端启动的实例；结束后关闭该终端，或移除对应变量再启动常规实例。无需修改私有 `.env`。

这些远程客户端快照流程使用现有结构化诊断路径，无需 TJU API Key，也无需公网服务或 RAG。普通非 Demo 聊天继续保留原有 LLM 配置要求。如果进行需要模型的自由对话，按 README 在服务端配置 Key；模型不可用时结构化证据、计划、复核和处理状态仍保留。不要把 Key 放到前端。

## 场景与 Schema

`DemoScenario` / `DemoScenarioStep` 定义在 `src/netpilot/demo/models.py`，均拒绝未知字段，场景定义冻结。Scenario 包含 ID、标题、说明、目标模式、EnvironmentUpdate、快照 ID 序列、预期 issue / 模板 / verification / resolution、是否支持升级、推荐输入与步骤。Step 包含 `order >= 1`、`actor=user|system|fixture`、动作说明和预期状态。预期状态用于断言，不参与状态写入。

| 场景 ID | 展示目标 | 预计耗时 |
| --- | --- | --- |
| `dns_recovery` | A：多域名 DNS 失败 → 同目标恢复 → 用户确认 → resolved | 2–3 分钟 |
| `dns_escalation` | B：两轮 unchanged → 无剩余安全步骤 → escalated → complete 材料 | 2–3 分钟 |
| `vpn_proxy` | C：VPN=true 时条件式临时断开建议、回滚和业务依赖限制 | 约 1 分钟 |
| `vpn_unknown` | C 对照：VPN=None 时先确认，不能直接要求断开 | 约 1 分钟 |
| `single_service` | D：基础连通正常、单服务影响范围，不误做全局重置 | 约 1 分钟 |
| `recurrence` | E：先完整恢复，再复发进入下一任务版本，保留旧 transition | 约 3 分钟 |

## Demo A：远程 DNS 故障恢复

1. 选择“A · DNS 修复成功”，创建演示。展开“当前环境”：Windows、campus_wifi、web_only。诊断对象必须是“当前浏览器设备（远程）”，不是服务主机。
2. 填入并发送：“我的微信能用，但网页打不开，帮我检查一下。”此时尚无客户端证据，系统提示采集快照；Host Tool handler 次数为 0。
3. 点击“加载 Before 快照”。查看客户端证据：网关正常、DNS 已配置、`www.tju.edu.cn` 和 `www.baidu.com` 解析异常、TCP 443 基础连通正常。
4. 发送：“请根据当前快照分析网页问题并给出低风险修复计划。”查看诊断思路中的支持/削弱假设与证据关联。DNS 异常支持解析路径问题，不等于定位唯一根因。
5. 展开“修复计划”，必要时点“生成 / 更新低风险计划”。所有步骤为 low-risk、手动、不要求管理员。展开“重新连接原校园网络”，仅在演示中模拟完成，点正式“已完成”按钮；不需要真的断网。
6. 点击“加载 After 1 快照”（A 的唯一 After）。同一 normalized DNS targets 恢复；“修复后验证”展示 Before / After，结果 `improved`。
7. “处理状态”中将“原始症状确认”设为“原始症状已恢复”，点击“确认症状”。预期 `Resolution=resolved`，客观 improved 与用户 resolved 分列。
8. 可再发送“网页现在可以正常打开了”。刷新“我的诊断历史”，查看 `[Demo]` 卡片；预览/下载报告，顶部必须有 **DEMO / 模拟数据**。

讲解顺序：Environment → Diagnostic Target → Client Snapshot → 支持假设 → 低风险手动计划 → Before/After → Resolution。主机 handler 始终为 0；不是用服务主机探测替代远程设备检测。

## Demo B：两轮无改善后升级

1. 选择“B · DNS 多轮无改善”，创建演示；同 A 先发送推荐问题，再加载 Before，再发一次快照分析请求。
2. 查看同样的多域名 DNS failure。展开正式修复计划：重新打开应用、重新连接原校园网络、保留现象并反馈维护者。
3. 第 1 轮：在“保存内容后重新打开应用”点击“已完成”，然后加载 After 1。查看 `Verification V1=unchanged`，不是 resolved。
4. 第 2 轮：在“重新连接原校园网络”点击“已完成”，并完成“保留现象并反馈维护者”的记录准备步骤。两者在 V2 的等待 After 阶段反馈；不是额外伪造一轮验证。确保没有剩余 pending 安全步骤。
5. 加载 After 2。查看两个 completed 轮次均为 `unchanged`；状态自动变为 `escalated`，原因 `repeated_no_improvement`。无需点“请求人工支持”强制结果。
6. 点击“生成报修材料”，展开 `v1 · complete`。预览 Markdown，再下载 Markdown / JSON：应含 DNS 证据、已完成步骤、两轮客观验证、升级原因、建议人工核查项和 Privacy Summary，顶部带 Demo 标记。
7. 讲解隐私：仅生成材料供操作者自行交接，不自动提交工单。导出继续调用 12H Redactor；敏感 Token、MAC、SSID、hostname 与 URL query secret 的删除由自动验收检查。网关/DNS 诊断信息按现有隐私策略保留。

若在 Before 之前先聊天，正式 Planner 可能保留一个后来 superseded 的准备基线。演示只计算 **completed 的两轮** unchanged，不删除这些审计记录来凑数量。

讲解重点：两轮低风险操作 → 两轮客观无改善 → 安全步骤耗尽 → 正式状态机升级 → complete、隐私安全的交接材料。

## 备用 Demo C：VPN 与未知状态对照

1. 选择“C · VPN 场景”，创建演示，加载 Before。
2. 填入并发送“普通网页打不开，但是我现在开着 VPN”。展开计划，查看“仅在不依赖 VPN 时临时断开对比”。
3. 读取限制：业务不依赖 VPN、不影响远程管理、仅用原应用断开按钮、不改配置；回滚是“使用原 VPN 应用重新连接原连接，恢复先前状态”。步骤仍为 pending，不自动执行，不断言 VPN 是唯一根因。
4. 切换“C 变体 · VPN 状态未知”，创建独立演示、加载 Before、发送推荐语句。环境 VPN 显示“不确定”；计划不能包含 `disconnect_vpn`，先确认状态。

这展示 `unknown != false`。Proxy 使用同一三态环境契约；本次具体对照演示的是 VPN，不把代理状态未知描述为已关闭。

## 备用 Demo D：单服务故障

1. 选择“D · 单服务故障”，创建演示、加载 Before、发送推荐语句。
2. 查看 affected_scope=single_service；network_config、DNS、gateway、TCP 基础证据正常。
3. 诊断 `primary_issue=single_service`，表示用户报告的影响范围，不能凭这些基础探测断言目标服务或所有 HTTP 正常。
4. 计划集中于服务状态、访问条件、校园内外/VPN 需求和重新打开受影响应用。无 Network/Winsock Reset、静态改 DNS、全局重置或无关的校园网络重连。

为承接已有证据，本阶段补齐正式 Planner 的 single_service 范围分类：必须显式 single_service 环境且基础快照证据为正常；任何更优先的异常继续先处理。这是共享生产逻辑，没有 `if demo` 诊断分支。

## 备用 Demo E：恢复后复发

1. 可直接沿用已经 resolved 的 A，或选择“E · 问题复发”并执行完整 A 流程。
2. 先记下演示状态区的 task_version，发送：“刚才好了，现在又打不开了”。
3. 预期 task_version 恰好 +1、`Resolution=diagnosing`、`reason=symptom_recurred`，旧 resolved transition 仍在“状态变化记录”中。
4. 最新 Verification 的旧 improved 轮次保留，并在演示摘要中标为“历史轮次”；当前 objective_result 是 unknown，不能把上一次恢复当本次已恢复。

## Fixture、正式业务路径与隔离

8 份 JSON 位于 `tests/fixtures/demo/`：

```text
dns_recovery_before.json / dns_recovery_after.json
dns_escalation_before.json / dns_escalation_after_1.json / dns_escalation_after_2.json
vpn_enabled.json / single_service.json / privacy_case.json
```

仓库快照均通过正式 schema；DNS 成败对比使用相同 normalized targets，归档时间递增。Loader 只把 `generated_at` 平移到此次点击的 UTC 时间，以满足正式新鲜度与 baseline 先后约束；观察结果不修改、不补造。已加载快照缓存相同内容与 digest，重复请求幂等；禁止越序 After 与加载后回退旧 Before（409）。要重放请重置。`privacy_case` 用于 schema/隐私回归，不开放任意文件路径；B 的步骤备注另带合成敏感字段验证最终导出 Redactor。

调用链：受控文件白名单 → 正式 `parse_snapshot`（含大小/schema/隐私校验）→ `SessionStore.import_client_snapshot` → 正式证据构建、Verification/Resolution evaluator → 同一 History 更新回调。没有直接插 Evidence、改 Diagnosis 或 set resolved/escalated。

每个 DemoRuntime 独立拥有 SessionStore、ToolRegistry、Agent 和 Fixture 缓存，Target 由正式 Environment 初始化为 remote user_client。注册表保留 local scope 安全契约，让生产 ToolPolicy 在 handler 之前阻止远程主机工具；FixtureOnlyTools 自身也没有真实网络探测实现。既有全局 Mock 控制只管理普通会话，不能清除或改变 DemoRuntime。Alice、Bob 和不同场景之间互不共享 Demo 状态。

普通反馈/确认/报修使用原有 API：

```text
POST  /api/chat 或 /api/chat/stream
POST  /api/session/remediation-plan
PATCH /api/session/remediation-plan/steps/{step_id}
POST  /api/session/verification
POST  /api/session/resolution/confirm
POST  /api/session/escalation-package
GET   /api/diagnoses/{record_id}/export
GET   /api/session/escalation-package/{package_id}/export
```

Demo API（都要登录，会话操作都验证 Ownership；跨用户返回 404）：

```text
GET  /api/demo/scenarios
POST /api/demo/session                           {"scenario_id":"dns_recovery"}
POST /api/demo/session/{id}/scenario/{scenario_id}
POST /api/demo/session/{id}/reset
POST /api/demo/session/{id}/load-snapshot/{fixture_id}
GET  /api/demo/session/{id}
```

创建、切换、重置返回新 session_id。重置只退役当前用户指定的旧 DemoRuntime；不删 SQLite 历史、普通 Session 或其他用户状态。运行时会话仍在内存，服务重启后需创建新演示；持久化 History 可完整只读查看和导出，但不会把历史快照重新激活成可操作 Session。

## 标识、可观测性与 Metrics

Session、ChatResponse、History、Report、EscalationPackage 传递 `is_demo`、`demo_scenario_id` 和 `data_notice`。历史卡片前缀 `[Demo]`；真实历史分析查询排除 Demo 数据。Markdown 顶部显示 **DEMO / 模拟数据**，JSON 同样携带标识与说明；旧普通数据默认 false，旧 Package digest 保持兼容。

右侧演示摘要只展示 scenario、task/target version、resolution、latest verification（含历史提示）、plan version、Host handler 次数和验证轮数。原有 Environment、Target、诊断思路、工具时间线、计划、复核、Resolution、Package 卡片继续渲染正式结构化数据；不展示 Raw CoT、System Prompt、上传原始 JSON 或 Secrets。

状态 API 还返回 LLM calls/total tokens/duration、Tool evidence 数、RAG calls、Remediation steps、Verification cycles、Resolution transitions。LLM 观察器只累计实际调用和 usage；固定快照路径没有网络工具/RAG 调用，通常 LLM calls/tokens 也为 0，不为展示数字额外调用模型。

## 失败恢复与真实客户端展示

若自然语言生成异常、操作顺序错误、旧快照回放被拒绝或状态不符合预期：

1. 点“重置当前演示”，记录新的 Demo session_id。
2. 重发推荐问题、加载 Before，再发快照分析请求。
3. 从对应 A/B 的正式步骤继续，按顺序加载 After；不需要重启应用。

按钮请求期间会禁用，结束后重新启用允许的下一快照。连续无改善只在完成正式步骤并收齐客观 After 后生效。不要用“生成计划”反复换计划版本代替完成已有步骤。

真实 Windows 客户端展示为可选，和稳定 Fixture 主演示分开：另一台 Windows 浏览器访问可达的服务地址 → 登录 → 选择当前浏览器设备 → 下载并检查只读 PowerShell 脚本 → 普通用户手动运行 → 主动上传生成 JSON。遵守现有 LAN 启动/访问说明，不为演示降低执行策略。Target 仍为 remote user_client；导入不会解除主机工具限制。

在 Demo Session 通过正式上传卡片上传真实快照后，Banner 切换“当前使用真实客户端诊断快照”。会话仍保留 Demo 身份与导出标记，避免混用为真实报修数据。真实采集不保证重现 Fixture 预期故障；需要回到稳定展示时重置当前演示。

## 自动验收与复现命令

```powershell
python -m pytest -q
python scripts/run_demo_scenarios.py
python scripts/run_demo_scenarios.py --scenario dns_escalation
git diff --check
```

Runner 使用独立临时 DB 和一次性账号，RAG/Key 关闭，通过 TestClient 调用真实 Auth、Demo、Chat、Remediation、Snapshot、Resolution、History、Export API。失败断言返回非 0；不会修改运行中服务或正式库。6 条路线含 C 的未知状态变体；自动核查 B 两种格式导出中合成 Secrets 消失。

| 自动验收 | 覆盖 |
| --- | --- |
| DS-01–06 | A/B/C/C未知/D/E；低风险计划、两轮无改善、回滚、复发 |
| DS-07–08 | Remote host handler=0，客户端/主机证据隔离 |
| DS-09、16、19 | 真实 Redactor、敏感上传拒绝、Report/Package Demo 标记 |
| DS-10–12 | 持久化只读恢复、重置保留历史、多用户/普通会话隔离 |
| DS-13–15 | socket 禁用仍可跑通、正式 parser 拒绝、无最终状态注入、可观测字段白名单 |
| DS-17–18、20 | Auth、Ownership、默认关闭、非 Demo 行为回归 |
| DOM | 默认隐藏、推荐语句不发送、Auth race、状态摘要、重置清理、忙碌结束恢复快照按钮 |

此外包含全部 8 份 Fixture schema 验证、顺序/重复加载、LLM 错误保留证据与计划测试。既有 12A–12H 全量测试一起运行。

## 本次实际验收记录（2026-10-19）

修改前 baseline：`1051 passed in 315.93s`。浏览器验收使用本机独立测试 DB、无 Key / RAG，所有操作经页面正式按钮和聊天流程完成，没有写数据库造状态。

| 人工 Case | 实际结果 |
| --- | --- |
| Case 1 DNS Recovery | 已在浏览器完成：remote user_client、DNS 异常证据、手动重连反馈、After improved、用户确认后 resolved、Host handler=0。截图 `screenshots/milestone12i-dns-recovery.png`。 |
| Case 2 Escalation | 已在浏览器完成：V1/V2 均 unchanged，全部安全步骤完成后自动 escalated / repeated_no_improvement，材料 complete；预览包含 Demo 横幅、证据、两轮验证、Handoff 和 Privacy。截图 `screenshots/milestone12i-escalation.png`。 |
| Case 3 VPN | 已在浏览器完成两种状态对照：VPN=true 的计划含条件式临时断开与原连接回滚，全部 pending；VPN=None 的计划先“确认 VPN 与代理状态”，没有断开步骤，Host handler=0。 |
| Case 4 Recurrence | 已在浏览器沿用 resolved 的 A：发送复发语句后 task v2→v3、diagnosing / symptom_recurred，旧 resolved transition 保留，当前 objective unknown。 |

最终全量回归：`1090 passed in 435.07s (0:07:15)`，相对 baseline 新增 39 个通过用例。实际命令使用仓库 venv 与 `--basetemp=.cache/pytest-12i-final` 独立测试目录。

`python scripts/run_demo_scenarios.py`：A / B / C / C未知 / D / E **6 PASS，exit 0**。`npm test --prefix web`：全部前端运行时用例通过，exit 0。`git diff --check`：通过。验收期间临时 localhost 服务与浏览器页已关闭，未删除任何正式用户历史。

## 交付文件索引

- 新增 `src/netpilot/demo/{models,scenarios,runtime,acceptance}.py` 与包入口；`src/netpilot/api/demo_routes.py`。
- 新增 8 份 `tests/fixtures/demo/*.json`、`scripts/run_demo_scenarios.py`、`tests/test_demo_scenarios.py`、`tests/test_demo_ui.py`、`tests/web_demo_scenarios_runtime.cjs`、本操作文档和验收截图。
- 修改 Settings / main / `.env.example`、SessionTaskState / SessionStore / API schemas，以及 Chat、Snapshot、Remediation、Verification、Resolution、Escalation API 的会话路由。
- 修改 History / Reports / Escalation builder、models、exports，传递 Demo 标记并隔离历史分析；最小补齐共享 Planner / Snapshot 的单服务范围判断。
- 修改 `web/index.html`、`web/app.js`、`web/style.css`、`web/package.json` 和健康接口测试预期；README 增加入口。

## 最终交付报告（Prompt 的 18 项）

| 项目 | 结果 |
| --- | --- |
| 1. 新增/修改文件 | 上方交付文件索引列出全部分组，工作区保留可 review 的差异；未自动提交。 |
| 2. Scenario / Step Schema | 冻结场景、严格字段、三类 actor、步骤顺序和预期断言；见“场景与 Schema”。 |
| 3. 五个 Scenario | A/B/C/D/E 全覆盖，额外提供 C 的 VPN unknown 对照入口。 |
| 4. Fixtures | 8 份正式 schema-valid JSON，同 DNS targets、递增时间、只重定位 capture 时间。 |
| 5. DEMO_MODE | 默认 false；隐藏 Selector，Demo API 404。 |
| 6. Session-scoped 状态 | 每个 DemoRuntime 独立 Store / Registry / Agent / Fixture cache，多用户互不污染。 |
| 7. Demo API | 6 类入口，见接口列表；Auth + Ownership + feature gate。 |
| 8. Snapshot Ingestion | 正式 parse_snapshot → import_client_snapshot → production evidence/evaluator/persistence。 |
| 9. 正式修复/复核/状态 API | 使用原 Remediation feedback、Verification、Resolution confirm、Escalation builder；无最终状态注入。 |
| 10. Reset | 创建新 ID，仅退役当前旧 DemoRuntime；保留普通 Session、其他用户与全部历史。 |
| 11. History | 持久化 Demo 字段、卡片前缀；可完整只读恢复，真实历史分析排除 Demo。 |
| 12. Report / Package 标记 | Markdown 顶部 DEMO / 模拟数据，JSON 保留标记；正式 Privacy Redactor 始终生效。 |
| 13. Demo Runner | 独立临时 DB/账号，真实 HTTP API journeys，断言失败 exit 1。 |
| 14. 操作文档 | 本文包含准备、启动/登录、A/B 完整脚本、C/D/E 备用、耗时、讲解、恢复与真实客户端展示。 |
| 15. 自动验收 | DS-01–20 全覆盖，schema、offline、parser、隐私、失败保留和 6 项 DOM 回归；新增 39 个用例。 |
| 16. 全量测试 | 1090 passed，0 failed。 |
| 17. Runner 结果 | 6 PASS，exit 0。 |
| 18. 四个人工 Case | DNS Recovery、Escalation、VPN true/unknown、Recurrence 均在浏览器实际通过；见实际验收表和截图。 |
