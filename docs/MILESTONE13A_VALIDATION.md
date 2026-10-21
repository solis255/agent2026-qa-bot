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

## Environment updates and state transitions

本节记录 13A 后续修复，日期 2026-10-21。修复前新增真实会话回归，先取得 **3 failed**：Windows/WiFi 无法覆盖为 Mac/有线、`Mac系统` 无法覆盖浏览器 Windows、`我现在改用有线网了` 仍保持 WiFi。修改前完整基线为 **1129 passed in 343.83s**，没有先修改失败测试期望来掩盖问题。

### 根因与修复范围

1. 原 OS 词形没有独立 Mac/Mac系统；网络规则要求“校园/校内 + 有线”，也没有目的状态解析。
2. 没有提取 Windows 11 的显式版本；同句出现历史值和新值时，原循环按固定正则顺序覆盖，不能可靠表达时间关系。
3. `acquire_context` 只合并环境，没有返回真实前后差异，也未把已知关键值变化接到原 task version 失效路径。
4. 纯环境陈述可能进入普通模型回答。模型可以声称“已更新”，而提取器实际上没产生任何变化。
5. 历史合并偏向保留“最后有意义的诊断”，没有同时检查 task_version；纯环境更新后，旧主机诊断可能仍被保留为当前结论。报告也只按 target 归类工具调用，没有排除已被任务版本归档的 evidence ID。

未调整 `PRECEDENCE`，未新增来源或环境模型。用户旧值 → 用户新值仍通过原 `merge_environment(source="user")`，用户确认后浏览器不能覆盖。

修改文件：

```text
src/netpilot/environment.py
src/netpilot/conversation_context/acquisition.py
src/netpilot/conversation_context/questions.py
src/netpilot/agent/intent.py
src/netpilot/agent/orchestrator.py
src/netpilot/agent/schemas.py
src/netpilot/agent/session.py
src/netpilot/history.py
src/netpilot/reports.py
tests/test_environment_transitions.py                 新增
tests/test_environment_transition_extraction.py       新增
tests/test_environment_profile_merge.py
docs/MILESTONE13A_VALIDATION.md
screenshots/milestone13a-environment-transition-fix.png 新增验收截图
```

### 提取与冲突规则

`environment.py` 采用 normalize → current clauses → current/transition destination → per-field candidates → schema 的确定性流程。保留假设、第三方、引用、问题、计划、不确定和否定语句的保守过滤；历史分句不作当前事实。字段候选包含多个未区分的系统或接入方式时，不随机选值。

- OS：支持 Windows / Windows 11 / Win11、Mac / Mac 系统 / Mac系统 / macOS / MacBook / 苹果电脑、Linux / Ubuntu 等明确的自身设备或当前状态表达。Windows 11 / Win11 同时写 `os_version="11"`；换到 Mac 清除旧 Windows 版本。
- 接入：校园 WiFi、WiFi、无线、无线网，以及有线网、有线网络、插网线、用网线等当前接入表达，映射至原枚举。校园产品语境中，无校外冲突的普通有线/WiFi 规范化为 campus_wired/campus_wifi。
- 地点：同段明确家里/校外时，普通有线/WiFi 优先为 off_campus；手机热点为 mobile_hotspot，不伪造物理链路观察。
- 转移：改用、改成、改为、换成、换到、切换到、切到、现在/目前等限定其右侧当前值。`从 WiFi 换成有线` 取有线，反向取 WiFi；`原来 Windows，现在 Mac` 取 Mac。
- MAC 安全：Mac 只有明确设备/当前状态上下文才可成为 OS；`MAC 地址`、`MAC address`、`网卡 MAC` 排除。单独提及 Mac 或 WiFi 不会自动形成事实，除非正在回答对应的 pending question。

`free_text_answer` 的 allowlist 补齐 Mac、Mac系统、Windows 11、WiFi、无线、有线网、网线、校园网线、手机热点、校外等。pending OS 短答 Windows 11/Win11 也保存用户明确提供的版本；结构化 Chips 仍只接受原字段/值枚举。

### 差异、分类、任务版本与证据

`AcquiredContext.changed_fields` 从 **合并前的 Profile 与实际 post-merge Profile** 计算，不从原句猜测；包括 family 改变时被清除的 os_version。示例：

```python
{"network_access": ("campus_wifi", "campus_wired")}
```

`environment_transition` 只在 os_family、network_access、vpn_enabled、proxy_enabled 的已知值 A → 不同已知值 B 时成立。

| 变化 | 语义 |
| --- | --- |
| unknown / None → known | enrichment；不因首次补充推进任务版本 |
| 同值重述 / 仅来源变化 | 不制造环境转移，不重复推进版本 |
| known A → known B（关键字段） | STATE_CHANGED；使用原任务版本机制，推进一次 |
| affected_scope 或版本补充 | 记录真实 changed field；不单凭范围/版本补全制造关键环境转移 |

Intent 层识别明确转移语言；acquisition 再比较真实前后值，防止“第一次说改用有线”被当作已发生的已知环境变化。显式重测保留 force_recheck；同时发生环境转移和重测也只推进一次。

Orchestrator 在临时诊断视图中使用原 `advance_version()`，在 Session finish 中正式提交一次。旧 evidence / Snapshot / plan / verification 全部保留，旧网络证据标记 superseded，不再出现在 reusable evidence / 当前 coverage / 当前 hypotheses 中。旧快照的 applicable=false，活动验证和计划失效，不能用旧 WiFi 或 Windows 的快照解释新环境。对象本身未显式切换时沿用原 target_version，task_version 已足以隔离新环境；不伪造客户端直接检测能力。

环境变化后的本轮不向模型注入旧的现场回答历史；新的 Context Builder 仍分离环境和证据。History 合并在 task_version 改变时采用当前诊断，不沿用旧主机故障结论；Report 按已 superseded 的 evidence ID 把旧工具调用移到 archived_tool_calls，保留全部记录且不列为当前检测。知识/报告/用户确认等原路径保留其职责；未修改 12A–12I 的正式数据来源和隐私策略。

### 回答与真实状态一致

纯环境更新走确定性确认，不调用 LLM、网络工具或可选 reasoning summary。确认由 `changed_fields` 和合并后的 Profile 生成，例如：

```text
已更新当前环境：接入方式已从“校园 WiFi”改为“校园有线”。环境信息不是网络检测证据。
```

同值重述或未识别的“神秘网络 / 银河系统”等表达，不产生“已更新 / 已记录 / 已切换”确认，保留原值并说明尚未确认变化。对抗测试预置一个试图返回虚假确认的模型，验证纯环境请求根本不会调用它。提到 VPN 的知识咨询不属于状态更新；只有实际开关陈述、设备/接入声明或转移描述才进入这个分支。

同时包含故障现象的消息继续正式诊断，附带由真实变化生成的环境确认；旧证据在分析前已失效。纯环境更新不会把“改用有线网”覆盖到原始故障症状。普通 Chat 与 SSE 的确认、Session 环境、History 实际问答和 Report 均有一致性断言。

### 自动验证与旧测试兼容

新增两个独立测试文件，覆盖 Prompt 的 TC-FIX-01～23：两个真实会话、OS/网络别名、转移目标、版本清除、校外优先、防误识别、pending 短答、实际变化、来源优先级、无变化/未识别输入、快照与工具证据归档、计划/验证失效、SSE/History/Report 一致性、首次补充不推进版本及同时重测只推进一次。

两条原 Windows 11 提取测试原先要求不包含 os_version，本次按明确新要求加强为同时断言 `os_version="11"`，其余字段和安全断言保留。知识检索与来源追踪测试原断言未修改；回归发现的误分流通过收紧生产分支修复。

新增回归共 **102 项**。首轮定向 **121 passed**，证据与兼容路径修正后 **134 passed in 11.61s**；额外的 History/Report 残留先有失败测试，再修复，相关回归 **30 passed in 17.08s**。两个新增文件单独运行 **102 passed in 15.20s**，含版本长度/ASCII 边界和独立导入测试：异常版本不放宽正式 Schema，不导致提取器抛错；acquisition 可先于 agent 包独立导入，不依赖全量测试的导入顺序。知识整理原回归 **36 passed**。

最终完整执行：**`1231 passed in 369.20s (0:06:09)`，exit 0**，相对 baseline 新增 102 项。实际命令为仓库 venv 下 `python -m pytest -q --basetemp=.cache/pytest-13a-fix-final3`。最终 `python scripts/run_demo_scenarios.py`：**6 PASS，exit 0**；`git diff --check`：通过。临时浏览器页与 localhost 验收服务已关闭；正式用户数据库和历史未删除。

### 人工浏览器复验

独立 localhost 实例、专用测试账号、独立 `.cache/13a-fix-browser.db`；环境识别、覆盖和确认走真实 Chat/SSE/Session，模型与网络 handler 使用离线替身。环境确认本身不调用替身模型。没有更改真实用户库。

| Case | 操作 | 实际结果 |
| --- | --- | --- |
| A | 网络有问题 → 某个服务 → Windows 11 + 校园 WiFi → Mac + 有线网 | 浏览器通过：面板从 Windows/校园 WiFi 变为 macOS/校园有线，两个字段来源均为用户；回答同步确认这两项真实变化。 |
| B | 校园 WiFi → “我现在改用有线网了” | 浏览器通过：变为校园有线，回答明确 WiFi → 有线；纯更新没有网络检测。 |
| C | 新会话：“我用 Mac系统，连有线网，微信正常，但是网页打不开。” | 浏览器通过：macOS / 校园有线 / 仅网页，无重复追问。 |
| D | “我的 MAC 地址是多少？” | 浏览器通过：Windows 与 browser provenance 保持不变，没有误记 macOS；此类知识答案质量不属于离线替身验收范围。 |

本修复不引入 13B readiness、13C Client Check/Collector/向导、13D 页面重构，也不新增模型抽取、Tool、远程执行、MCP 或多 Agent。

### 修复交付报告索引（14 项）

| 项目 | 结果 |
| --- | --- |
| 1. 根因 | 别名/当前状态语法不足、无真实差异和任务转移、模型自由确认、历史结论跨任务残留。 |
| 2. 修改文件 | 本节文件清单列出后端、两个新增测试文件、兼容期望和文档/截图。 |
| 3. extractor | NFKC 归一、保守分句过滤、目的状态优先、候选冲突处理、严格原 Schema。 |
| 4. OS 表达 | Windows/Win11、Mac/Mac系统/macOS/MacBook、Linux/Ubuntu 等自身当前状态。 |
| 5. 接入表达 | WiFi/无线、有线网/插网线、热点、校外；显式家里/校外优先。 |
| 6. 同句冲突 | 从 A 换到 B / 原来 A 现在 B 取 B；不能用固定正则顺序选值。 |
| 7. MAC 防误判 | 硬件地址上下文排除、当前设备语境约束，独立自动测试和浏览器 Case D。 |
| 8. user → user | 真实连续 Chat 会话覆盖旧用户值；user → browser 不回退的断言保留。 |
| 9. changes / transition | 只比较 post-merge 真值；首次补全、同值重述、关键已知变化区分。 |
| 10. Evidence | 正式 task version 归档；旧快照/工具/计划/验证失效；History 不删除、Report 归历史区。 |
| 11. 回答一致 | 纯更新零 LLM；确认来自实际差异；未识别/无变化不虚假确认；Chat/SSE/History/Report 一致。 |
| 12. 原人工会话回归 | 两个完整会话自动测试通过；浏览器 A–D 实际通过，见上表。 |
| 13. 新增数量 | 102 项，两个新增文件单独运行全部通过。 |
| 14. 最终全量 | 1231 passed，0 failed；新增 102 项，Runner 6 PASS，差异检查通过。 |
