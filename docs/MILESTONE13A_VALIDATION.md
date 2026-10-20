# Milestone 13A — Conversational Context Acquisition

13A 将环境采集改为对话内按需追问，继续使用唯一的 `EnvironmentProfile`。它没有实现 13B 的 DiagnosticReadiness、13C 的网络检查向导或 13D 的整体学生版布局。

## 实现与文件

新增 `src/netpilot/conversation_context/`：

| 模块 | 职责 |
| --- | --- |
| `models.py` | 严格、有界的 Assessment、Question、Choice、Answer、AcquisitionState；字段和值 allowlist |
| `needs.py` | 纯函数判断本轮必要环境字段、缺失字段和原因，不调用模型 |
| `questions.py` | 固定单题模板、结构化选项、规范化答案、针对待回答问题的短文本解释 |
| `acquisition.py` | 复用 extractor/merge，记录 asked/unknown/pending，回答后继续原问题主题 |

修改 Agent 的 `orchestrator.py`、`schemas.py`、`task_state.py`、`session.py`、`intent.py`、`response_modes.py`；公共 `models/schemas.py`、API `routes.py` / `presenters.py`、`environment.py`、`history.py`、`reports.py`；Web 的 `index.html` / `app.js` / `style.css` / `package.json`。README、architecture、test-cases 增加必要说明。新增 4 个 Python 验收文件和 `tests/web_context_runtime.cjs`。

## 判断规则与优先级

1. 普通知识/服务咨询不要求运行环境。VPN 使用、eduroam、认证、下载地址、客服电话等继续原 Knowledge/RAG 路径。明确平台相关的客户端安装/配置步骤只允许补 `os_family`，浏览器或用户已给出时不再问。
2. 宽泛的当前网络症状优先补 `affected_scope`。这通常比一开始询问系统、VPN、Proxy 更有区分度。
3. 校园接入相关故障再补 `network_access`；VPN/Proxy 相关症状才分别补对应开关。普通网页故障不会固定追问 VPN/Proxy。
4. 显式工具/服务主机检查遵守原对象和工具策略，不在检查前索要学生设备环境。已有适用证据时不重开问卷；这只是避免重复获取上下文，没有新增 13B readiness 状态机。
5. 一次返回一个缺失字段。已有值、用户明确回答的 unknown、当前阶段已问过的字段不会立即再问。每题都有“不清楚”，也可自由输入。
6. 假设/第三方叙述走知识语义，不把描述当当前用户事实；History/Report/Meta 的原优先级保留。明确“VPN 连接失败”按当前故障处理，不因“连接”一词误入使用知识路径。

这些是保守 P0 规则，不保证覆盖所有症状。环境不是网络 Evidence，不能从校园 WiFi 或“VPN 开启”生成网关可达、DNS 正常等观察。

## 轻量状态与后续回答

`SessionTaskState.context_acquisition` 包含：

```json
{
  "asked_fields": [],
  "unknown_fields": [],
  "last_question_field": null,
  "topic": null,
  "task_version": 1,
  "target_version": 1
}
```

只存允许的字段名、问题主题和版本，不存整段消息、URL、设备标识或凭据。用户答“不清楚”时 VPN/Proxy 写 `None`，枚举写 `unknown`，通过原 `merge_environment(..., source="user")` 保留来源；绝不转成 false。后续主动确认时移除 unknown 标记。asked_fields 在阶段内抑制机械重复；任务/对象版本变更时按现有版本重新建立阶段，不改变版本本身的语义。

短回复只针对实际待回答的问题解释。例如“校园 WiFi”“也不能联网”“没开”“我不知道”。完整陈述继续优先使用原 deterministic extractor；小范围扩展 Win11、实际使用 macOS、微信能用与 Clash 的显式陈述，仍拒绝假设、第三方、问题句和不确定表达。不能把“我是不是开着 VPN 才导致网页打不开”当 VPN=true。

回答完成后继续先前的诊断或安装主题；不会把“校园 WiFi”误当独立知识问题，也不会覆盖原始故障症状。用户明确转向知识/报告等新请求时清理待回答问题。旧状态缺字段时采用安全空默认，不从旧回答反推 asked_fields；History 可只读恢复，不重新激活可点击 UI。

## Chat / SSE 契约

`ChatRequest` 保留原 `session_id` 和必填 `message`，增加可选 `context_answer`：

```json
{
  "session_id": "<current session UUID>",
  "message": "校园 WiFi",
  "context_answer": {"field": "network_access", "value": "campus_wifi"}
}
```

Field 仅允许 `os_family`、`network_access`、`affected_scope`、`vpn_enabled`、`proxy_enabled`。Value 使用各字段既有枚举；布尔选项是 `true` / `false` / `unknown` 字符串，服务端转换成 true / false / None。拒绝额外字段、越界值（422），拒绝未询问、过期或已消费的快捷回答（409）；校验在 Session busy 标记之前完成。Ownership/Auth 不变。

结构化回答的 message 由服务端规范化为可信选项标签；不会信任客户端伪造的自由文本描述。它仍作为正常 user/assistant Turn 写入对话与 History，而不是旁路 PATCH 环境。

`ChatResponse.ui_action` 是 `ContextQuestion | null`：

```json
{
  "answer": "你现在连接的是哪种网络？",
  "ui_action": {
    "type": "context_question",
    "field": "network_access",
    "question": "你现在连接的是哪种网络？",
    "choices": [
      {"value":"campus_wifi", "label":"校园 WiFi"},
      {"value":"campus_wired", "label":"校园有线"},
      {"value":"off_campus", "label":"校外网络"},
      {"value":"mobile_hotspot", "label":"手机热点"},
      {"value":"unknown", "label":"不清楚"}
    ],
    "allow_free_text": true
  }
}
```

所有新增模型 `extra="forbid"`，列表和文本有界。当前只支持 `context_question`，未提前添加 client_check / verification / remediation action。普通 Chat 与 SSE worker 共用 Agent、Session finish、Presenter、History upsert，`complete.response` 带完整 action；老客户端忽略新字段仍能显示 answer。采集状态保存到 History/JSON Report，按钮 DOM 不持久化。

## 前端行为

只根据结构化 action 渲染 Chips，不解析自然语言。原生按钮可 Tab 聚焦、Enter/Space 激活，有 group label、焦点样式、loading 禁用和选中状态。点击调用原 `/api/chat/stream`，不调用 Environment PATCH；请求中不能重复提交，成功后旧题按钮全部失效，失败可重试。自由输入照常走相同聊天流程。切换会话、历史查看、退出/鉴权失效时禁用或清理旧题，Auth epoch 继续阻止异步旧响应污染新账号。

原环境表单保留且默认折叠，入口改为“环境信息 / 查看详情”，提示无需预先填写。展开后显示系统、网络、VPN、代理、范围的值/来源/置信度，仍可通过原表单修正。没有进行 13D 整体布局重构。

## 复用的 Milestone 12 逻辑

- `initial_environment`、`extract_environment_updates`、`merge_environment` 和 PRECEDENCE；用户明确声明优先于浏览器，snapshot/mock/server 语义不变。
- Target 派生、执行能力和版本绑定；追问仍保留高级 Trace 的对象确认与限制，远程客户端不调用 host handler。
- Snapshot schema、privacy/freshness/size 校验、Evidence provenance；没有从环境补造 Evidence。
- 原 Planner、Remediation feedback、Verification、Resolution、Escalation builder/Redactor；上下文回答保留原症状。
- 原 Session busy/owner、History/Report/Export、12I 演示隔离/重置/模拟数据标记。

## 自动验证

```powershell
python -m pytest -q
python scripts/run_demo_scenarios.py
npm test --prefix web
git diff --check
```

新增用例：`tests/test_context_needs.py`、`test_context_questions.py`、`test_context_acquisition.py`、`test_context_ui_action.py`；DOM 实现在 `tests/web_context_runtime.cjs`。

| Prompt 用例 | 覆盖 |
| --- | --- |
| TC-13A-01 | 6 类知识不需环境、安装仅 OS、原 RAG 检索与来源路径，无额外 context LLM 调用 |
| TC-13A-02–03 | 单题、零模型/网络调用、无伪造证据/诊断、完整明确环境不重问 |
| TC-13A-04 | browser Windows → user macOS → browser 仍不能覆盖 |
| TC-13A-05–06 | unknown 保持 None、后续不再问、主动确认移除 unknown |
| TC-13A-07–08 | Chips 经正式 merge/History、非法字段/路径值/过期请求 4xx、状态和 busy 不变 |
| TC-13A-09–10 | 假设/第三方/问题句不污染环境；Clash 只表示代理，不猜 VPN |
| TC-13A-11–13 | Chat/SSE 同义、旧 Task/History 默认、原高级表单可用 |
| TC-13A-14 | 全量旧测试、12I runner、全部前端运行时回归 |
| DOM | Chips、选中/防双击、失败重试、旧题/Auth 清理、provenance、文本渲染防注入 |

旧测试只调整明确受到 13A 影响的交互前提：工具 loop/上限/去重/错误兜底/RAG 权限测试补充明确范围以进入原检测路径，保留其所有执行与安全断言；旧四题问卷断言改为单个 typed question 和 unknown 选项。Target Trace 的初始化/限制去重断言通过生产 Trace 集成保留，没有降低断言。

修改前 baseline：`1090 passed in 324.54s`。修复相关路径后的定向回归：`63 passed in 18.00s`。

最终全量：**`1129 passed in 431.93s (0:07:11)`，新增 39 项通过用例，exit 0**。实际运行使用仓库 venv 和 `--basetemp=.cache/pytest-13a-final` 独立临时目录。12I Runner：**6 PASS，exit 0**。`npm test --prefix web`：全部通过，exit 0。`git diff --check`：通过。

## 人工浏览器步骤与实际记录

使用独立 `.cache/13a-browser.db`、专用测试账号和 localhost 服务，真实 Chat/SSE/Environment/History API。知识回答使用明确标注的离线模型替身，验证的是交互路径；真实 RAG 的调用、来源和无额外 context 模型请求另由自动测试验证，不将界面替身回答宣称为联网模型质量验收。

| 场景 | 操作步骤 | 本次结果 |
| --- | --- | --- |
| A 纯知识 | 新会话，输入“eduroam 是什么？” | 浏览器已通过：直接走知识回答，无环境 Chips、无环境表单要求、无 Snapshot 请求。 |
| B 最小追问 | 新会话，输入“网页打不开。”；选择“只有网页有问题，其他应用能用” | 浏览器已通过：只返回影响范围一题；按钮选择进入聊天记录，成功后所有旧按钮禁用、选择项保持选中。 |
| C 完整陈述 | 新会话，输入“我用 Win11，连接校园 WiFi，微信能用，但是所有网页打不开。” | 浏览器已通过：无 Chips 追问；Windows / campus_wifi / web_only 均正确，三个字段来源均为用户、高置信度。 |
| D 不清楚 | 在已有 web_only 的 C 会话继续输入“VPN 一直失败”；对 VPN 题回答“我不知道。”，再发“还是打不开。” | 浏览器已通过：只问 VPN；未知被接受，VPN 仍未知、来源用户；后续无新 VPN 问题或可点击旧选项，没有冒充已检测。 |
| E 高级详情 | 在 C 后首次展开“环境信息 / 查看详情”；查看来源，再用原表单改接入方式 | 浏览器已通过：来源/置信度可见，VPN 未知；将校园 WiFi 改为校园有线，提示服务端保存成功，来源仍为用户。 |

截图 `screenshots/milestone13a-context-question.png` 展示对话内单题与快捷选项，`screenshots/milestone13a-environment-provenance.png` 展示未知 VPN 与用户来源。A–D 的对话均无需先填写环境表单；E 专门验证高级入口仍可手工修正。关闭浏览器或重启应用不等于重激活旧内存 Session；历史仍可只读查看和导出。验收没有修改或清空正式用户库。

## 留给后续里程碑

- 13B：统一 DiagnosticReadiness、按证据缺口自适应触发客户端检查及拒绝路径。
- 13C：开始网络检查 Action、采集/拖放上传向导、完成后自然继续分析、修复后重新检查；EXE 属于后续 P1。
- 13D：整体学生版布局与统一高级详情面板。

本阶段没有新增 Tool、自动修复、远程执行、Multi-Agent 或部署流程。

## 交付报告索引（Prompt 的 13 项）

| 项目 | 交付 |
| --- | --- |
| 1. 修改文件列表 | “实现与文件”列出新增包、后端、前端、测试和文档；工作区差异可直接 review。 |
| 2. 模块职责 | models / needs / questions / acquisition 四模块独立于 Orchestrator 大循环。 |
| 3. Need Assessment | 知识免环境、平台设置只 OS、故障范围优先、接入/VPN/Proxy 按相关性补充。 |
| 4. Question 优先级 | 每次一字段；已知/明确 unknown/阶段已问均跳过；必有 unknown 选项和自由文本入口。 |
| 5. 防重复状态 | asked_fields / unknown_fields / pending + topic/version；不保存原消息。 |
| 6. ui_action Schema | 上方完整 JSON，ContextQuestion 或 null；当前仅 context_question。 |
| 7. Chat/SSE 兼容 | 同一 Agent/finish/Presenter/upsert，SSE complete 包含完整响应，旧客户端保留 answer。 |
| 8. Chips 提交 | 原 chat/stream + 严格 ContextAnswer，服务端标签规范化、原 merge/user provenance、正常 Turn。 |
| 9. 复用 12 | 原环境/对象/证据/安全/快照/计划/复核/状态/隐私/历史/导出/演示流程。 |
| 10. 自动测试 | 新增 39 项；定向回归 63 passed，全部前端运行时通过，Runner 6 PASS。 |
| 11. 全量 pytest | 1129 passed，0 failed。 |
| 12. 后续范围 | DiagnosticReadiness / Client Check / Collector / 向导 / 学生版整体布局明确保留 13B–13D。 |
| 13. 人工步骤 | 上方 A–E 逐项操作与实际结果，浏览器全部通过；明确离线模型替身的验证边界。 |
