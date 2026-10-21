# Milestone 13B — Adaptive Diagnostic Flow 验收与交付说明

日期：2026-10-21。基线：main `8e0a9f1`（13A_fix），工作区实现，无自动提交。

## 核心问题和实施位置

13A 已有确定性环境获取；12B/C 已有对象隔离和客户端快照；Coverage/Sufficiency 已有分层证据评估，但缺少统一的“是否应该采集、先问什么、能否复用”的编排决策。旧 `bool(snapshot_evidence(task))` 及 limitation hint 不能区分过期或时钟偏差快照，容易把历史采集误显为当前可用。

实际调用：`acquire_context → derive/merge target → 高优先级特殊动作 → assess_diagnostic_readiness → ContextQuestion / 确定性缺证据说明 / 原 _run_turn`。没有重写 Tool loop，没有新增网络 Tool 或 LLM 分类调用。13A 当前值提取、user 优先级、真实差异确认、环境变化 task version、旧证据归档继续保留。

## 最终 schema

`conversation_context.models.DiagnosticReadiness` 为 `extra="forbid"` 的 Pydantic 模型：

```text
state: knowledge_only | need_context | need_client_evidence | ready
reason: 1..100 字符的稳定小写下划线 code
missing_context_fields: list[ContextField]，最多 5 项
evidence_gap: list[str]，最多 8 项，现有 Sufficiency coverage 名称
target_subject: TargetSubject
target_version: int >= 1
task_version: int >= 1
can_use_host_network_tools: bool = false
can_use_mock_tools: bool = false
has_usable_client_evidence: bool = false
client_evidence_supported: bool | None = None
recommended_action:
  answer_knowledge | ask_context | analyze_existing |
  run_allowed_diagnostics | request_client_evidence | continue_with_limitations
```

不含原始消息、Snapshot、设备标识、密钥或 Cookie；不是 Evidence，也不授予执行权限。

## 四状态、优先级及复用关系

| 状态 | 判定和下一步 |
| --- | --- |
| knowledge_only | 不需要现场证据的知识/服务问答，沿用 Knowledge/RAG，不执行网络 Tool。 |
| need_context | 13A 已有必要问题，或确定需要客户端证据但 OS 未知；只返回一个原 ContextQuestion。 |
| need_client_evidence | 远程 user_client 无可执行现场工具，广泛网页/全网故障或明确自身实时检测，且当前证据不够；Windows 请求现有快照，其他平台受限指导。 |
| ready | 充分证据优先 analyze_existing；Host/Mock 能力允许时 run_allowed_diagnostics；单站点、无线可见性或 Collector 无法补足的缺口走 continue_with_limitations。 |

特殊动作先行：报告、历史分析、恢复确认、复发、验证结果、显式修复、报修/人工支持及反馈不被 Gate 阻塞。平台安装缺 OS 时，13A 的问题优先于知识回答。其余诊断先必要环境，再对象能力，再已有证据充分度，再采集需求。

- 13A：沿用 `EnvironmentProfile`、`EnvironmentNeedAssessment`、acquisition state、`acquire_context`、`assess_environment_need` 和 `plan_context_question`。新增 OS 问题使用相同 Chips、普通 Chat/SSE、allowlist 和 pending task/target 校验。“不清楚”保留 unknown，不反复追问。
- Target：唯一权限判断仍为 `evaluate_target_capabilities`；Host/Mock/remote 的关系和实际执行位置不由 Readiness 或模型改写。
- Evidence：唯一覆盖/充分度计算仍为 `coverage_from_observations` 与 `assess_evidence_sufficiency`，使用原 `DiagnosticGoal`。Environment 不设置任何 checked flag。
- 充分证据：沿用原等价 Tool Signature 和 correlated Tool feedback；`ToolPolicy.max_new_calls=0` 允许复用已执行结果但拦截新增取证，Registry 继续独立检查 target。

## 当前客户端证据的权威定义

`usable_client_snapshot_evidence(task)` 先调用现有 `reusable_evidence()`，再由同一 `usable_client_snapshot_records()` 校验：

```text
origin == client_snapshot
reusable == true
superseded == false
task_version == current task_version
target_subject == current subject
target_version == current target_version
stale == false
clock_skew_suspected == false
expires_at 存在且尚未过期
```

不删除旧记录。过期、时钟偏差、旧任务/对象的 Snapshot 继续用于历史、报告和 Before/After，但不满足当前准备度。显式回看过期快照可返回“历史采集状态”，不会恢复当前可用能力。Session 防御性读取、历史和 Report 在读取时刷新可用性；只有符合上述条件的当前证据才标 `client_snapshot_available`。

Windows 为 true；macOS/Linux/Android/iOS 为 false；unknown 为 null。false 表示暂无对应 Collector，可以继续受限诊断。Windows Collector v1 可提供 network_config、gateway、dns、tcp（以及 Sufficiency 中对应的组合覆盖）；无法提供公网 IP ping、HTTP 和 traceroute。fresh Snapshot 覆盖已足够时不重复上传；缺失可重新采集项才请求补充，Collector 无法提供的缺口给出限制。

单站点默认先比较服务、VPN/Proxy、浏览器与访问策略，不因此要求整机快照。后续明确“检查我的 DNS”可转入采集流程。WiFi 列表完全找不到网络时也先处理无线发现/覆盖问题。

## 临时回答、API 和缓存

Windows 缺证据时确定性说明远程客户端与服务主机的区别，并指向既有手动快照功能。macOS 等平台说明缺少对应采集器并给出低风险建议；回答不包含 PowerShell 或 ps1 操作命令。相同 task/target 下“那怎么办/下一步呢”缩短限制提示，仍明确证据不足。

`AgentResult.diagnostic_readiness` 经 presenter 暴露给普通 Chat 和 SSE complete。`SessionTaskState.last_diagnostic_readiness` 默认 null，Session GET 返回上次有效决策；特殊动作本轮 readiness 为 null，不覆盖该缓存。环境实际变化、任务/对象切换、快照上传替换和证据可用性变化使缓存失效，下一次对话重新评估。普通环境更新及高级表单都不会保留旧平台准备度；高级表单保存后立即隐藏旧平台指引。History 与 JSON Report 保存轻量决策；JSON 快照 schema 从 v11 升到 v12，旧版本缺字段默认 null，SQLite 表 schema 仍为 v3。

Trace 使用 decision 阶段，包含稳定 reason、动作及 task/target 版本；不记录 Snapshot 或敏感环境 dump。原 intent 首步骤顺序保留。Web 只消费服务端平台支持标志，隐藏非 Windows/未确认平台的旧 Windows 脚本指引，不自行判权限。

## 修改文件

```text
src/netpilot/conversation_context/models.py
src/netpilot/conversation_context/readiness.py             新增
src/netpilot/environment.py
src/netpilot/agent/intent.py
src/netpilot/agent/orchestrator.py
src/netpilot/agent/reasoning_trace.py
src/netpilot/agent/schemas.py
src/netpilot/agent/session.py
src/netpilot/agent/task_state.py
src/netpilot/api/presenters.py
src/netpilot/api/routes.py
src/netpilot/client_snapshot/service.py
src/netpilot/models/schemas.py
src/netpilot/history.py
src/netpilot/reports.py
src/netpilot/resolution/service.py
web/app.js
web/index.html
web/package.json
tests/test_diagnostic_readiness.py                         新增
tests/test_adaptive_diagnostic_flow.py                     新增
tests/test_readiness_ui.py                                 新增
tests/web_readiness_runtime.cjs                            新增
tests/test_context_acquisition.py
tests/test_client_snapshot_history.py
tests/test_conversation_persistence.py
tests/test_environment_profile_history.py
tests/test_reasoning_trace_persistence.py
tests/test_remediation_history.py
tests/test_target_history.py
tests/test_web_demo.py
README.md
docs/architecture.md
docs/test-cases.md
docs/MILESTONE13B_VALIDATION.md                             新增
screenshots/milestone13b-macos-readiness.png                新增
```

旧测试变更为 JSON 快照版本 11→12、静态脚本缓存版本的精确断言，以及在原三轮 scope/access 会话测试中补充“浏览器已知 Windows”前置条件，保留原环境、会话轮数、工具次数与持久化断言；新增测试单独覆盖 OS 未知时的新追问。未删除或弱化业务安全断言。前端更新脚本版本确保正常刷新可加载平台指引代码。

## 自动验证记录

基线全量：`1231 passed in 353.22s (0:05:53)`。首轮新增矩阵暴露规则与测试前置缺口，修正后定向 `77 passed in 35.07s`。首次完整回归发现五处：一条 SQLite schema 期望未更新、三条充分证据下原 Tool feedback 复用协议、以及 intent Trace 首步骤顺序；保留旧断言并修正生产集成。相关定向回归 `86 passed in 25.75s`。

补充端到端回归先发现“所有应用都不能联网/无法联网”被原环境更新分支截走，以及不受当前 Collector 支持的缺口仍得到通用重采集建议；新增失败测试后修复 extractor/纯更新症状排除和快照受限说明。充分证据下模型尝试请求新 DNS 参数的对抗测试验证 handler 不执行。相关回归 `4 passed, 21 deselected in 4.41s`。

上一轮完整测试 `1290 passed, 1 failed in 366.51s`，唯一失败为本次静态脚本缓存版本更新后的旧精确断言，已同步为新版本。之后完整套件 `1295 passed in 396.55s (0:06:36)`；环境修改后的缓存失效补充测试及相关 API/DOM 回归 `47 passed in 47.08s`。一次后台完整测试进程在 38% 时退出，未计为成功，随后重新完整执行。

最终全量：**`1297 passed in 378.60s (0:06:18)`，exit 0**。相对 main 基线新增 **66 项**，包含规则矩阵、正式 API/SSE/Session/持久化和三项 DOM 检查。最终 `npm test`：**97 项 DOM 检查通过，exit 0**；12I Demo runner：**6 PASS**；`git diff --check`：通过。临时浏览器页已关闭，独立 localhost 验收端口已释放，未删除或更改正式用户数据库。

最终命令与日志（`.cache/` 为本地忽略产物）：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.cache/pytest-13b-final4
# .cache/13b-final4.log

# 在 web/ 目录
npm.cmd test
# .cache/13b-web-final.log

.\.venv\Scripts\python.exe scripts/run_demo_scenarios.py
# .cache/13b-demo-final-delivery.log

git diff --check
```

## 场景 A–H 验收方法与结果

自动/API 验证均使用生产 App、Orchestrator、Session、Snapshot 正式解析/上传、History/Report 路径，独立临时数据库与离线受控 Provider/模型；不制造真实校园网络故障。浏览器使用 `127.0.0.1:8169` 和专用测试账号/数据库 `.cache/13b-browser.db`，不操作真实用户库。知识替身只验证路由，不作为知识答案质量验收。

| 场景 | 操作 | 期望/验证 |
| --- | --- | --- |
| A 知识 | eduroam 是什么 | knowledge_only，网络调用为 0，原 Knowledge/RAG 路径。 |
| B 补环境 | 网络有问题→全部网络→OS | 一次一个问题，scope 后 OS；不清楚不重复；结构化回复绑定当前版本。 |
| C Windows | Windows+校园 WiFi+微信正常+所有网页失败 | need_client_evidence/request_client_evidence，host handler=0，LLM=0。 |
| D Fresh | 正式上传当前 DNS failure Snapshot，再分析 | ready/analyze_existing，有实际采集时间与 DNS Evidence，无重复采集或 host 调用。 |
| E Stale | 上传过去/超前时间 Snapshot，再检查 DNS | 旧记录保留，不标当前可用，need_client_evidence；显式回看只陈述历史。 |
| F Mac | macOS+校园 WiFi+网页故障 | supported=false，受限指导，无不适用命令；侧栏隐藏 Windows 采集指引。 |
| G 单站点 | 只有 GitHub 打不开，百度正常 | ready/continue_with_limitations；后续明确检查自身 DNS 才请求客户端证据。 |
| H Host | 显式切换 NetPilot 服务主机，再检查 DNS | ready/run_allowed_diagnostics；仅受控 Local 替身 handler 执行，复问复用现有结果。 |

浏览器实际完成：A 的 Knowledge decision Trace 与 Tool=0；B 的单个范围问题和原 Chips 提交（浏览器已知 Windows，不额外追问 OS）；C 的确定性客户端证据提示、Tool=0 和 Windows 指引可见；F 的 Mac 受限回答、刷新后 supported=false 的说明，以及 Windows 采集命令不可见；G 的单站点受限建议、不立即请求快照；H 显式切换 NetPilot 服务主机后出现 run_allowed_diagnostics Trace 和 1 次受控 DNS handler，证据标注为服务主机。D/E 与 OS unknown 使用上列正式 API 集成测试验证，没有把自动测试冒称为浏览器上传操作。截图保存于上列 screenshots 文件。

## 13C / 13D 边界

本阶段没有新增 `ClientCheckAction`、开始网络检查按钮、EXE、自动下载/上传、上传向导或页面重构。13C 后续消费 `request_client_evidence` 决策实现检查交互与采集引导；其他平台 Collector 仍需独立实现。13D 后续处理整体布局及会话体验。现有手动采集/上传功能和 12I Demo 保持原流程。

## Prompt 交付项索引

| 项 | 内容 | 本文对应位置 |
| --- | --- | --- |
| 1 | 实现前核心问题 | 核心问题和实施位置 |
| 2 | 修改文件列表 | 修改文件 |
| 3 | 最终 schema | 最终 schema |
| 4 | 四状态规则 | 四状态、优先级及复用关系 |
| 5 | 决策优先级 | 四状态、优先级及复用关系 |
| 6 | 复用 13A | 原 acquisition、问答、Chips 与版本校验 |
| 7 | 复用 TargetCapability | 原权限计算与 Registry 边界 |
| 8 | 复用 EvidenceSufficiency | 原 Coverage/Goal/Sufficiency，未复制算法 |
| 9 | usable client evidence | 当前客户端证据的权威定义 |
| 10 | stale/skew/旧 task/target | 原始记录保留，当前准备度及可用性排除 |
| 11 | 平台支持 | Windows true；其他已知平台 false；未知 null |
| 12 | single_service | 低风险建议优先，显式自身检测才请求证据 |
| 13 | need_client_evidence 响应 | 临时回答、API 和缓存 |
| 14 | 不提前实现 13C | 13C / 13D 边界 |
| 15 | fail-closed 回归 | 远程调用 0、伪造 ready 仍拒绝、新参数检测仍拦截 |
| 16 | Chat/SSE | 相同 readiness、回答、Environment/Target；均走正式 presenter |
| 17 | 新增测试 | 三个 Python 测试文件共 66 项；DOM runtime 为其中 3 项的执行器 |
| 18 | 全量 pytest | 自动验证记录 |
| 19 | 手动验证 | 场景 A–H 验收方法与结果，区分浏览器与正式 API 证据 |
| 20 | 13C/13D 后续 | 13C / 13D 边界 |
