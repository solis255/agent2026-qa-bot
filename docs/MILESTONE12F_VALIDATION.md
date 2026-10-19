# Milestone 12F — Resolution State

## 范围

实现 Session 级 Support Case 生命周期与人工支持建议，不提交真实工单、邮件、短信或第三方 ITSM 请求，不生成 Support Package，不执行高风险修复或管理员提权。

修改前仓库干净，全量基线为 `791 passed in 240.97s`。已审计 Agent/TaskState/Evidence/Hypotheses、Context/Trace、remediation、verification、client_snapshot、API/Auth ownership、History/Report、Web 和 tests。未输出生产密钥，未修改生产 `.env`、清空 SQLite 或重建用户历史。

## 文件清单

新增：

```text
src/netpilot/resolution/__init__.py
src/netpilot/resolution/models.py
src/netpilot/resolution/evaluator.py
src/netpilot/resolution/transitions.py
src/netpilot/resolution/policy.py
src/netpilot/resolution/service.py
src/netpilot/api/resolution_routes.py
tests/resolution_helpers.py
tests/test_resolution_models.py
tests/test_resolution_evaluator.py
tests/test_resolution_transitions.py
tests/test_resolution_escalation.py
tests/test_resolution_api.py
tests/test_resolution_context.py
tests/test_resolution_history.py
tests/test_resolution_ui.py
tests/web_resolution_runtime.cjs
docs/MILESTONE12F_VALIDATION.md
```

修改：

```text
.env.example, README.md
src/netpilot/agent/context_builder.py, orchestrator.py, prompts.py
src/netpilot/agent/reasoning_trace.py, schemas.py, session.py, task_state.py
src/netpilot/api/client_snapshot_routes.py, remediation_routes.py, routes.py, verification_routes.py
src/netpilot/config.py, history.py, main.py, models/schemas.py, reports.py
src/netpilot/remediation/integration.py
src/netpilot/verification/evaluator.py, service.py
web/app.js, index.html, style.css, package.json
tests/test_client_snapshot_history.py, test_conversation_persistence.py
tests/test_environment_profile_history.py, test_reasoning_trace_persistence.py
tests/test_remediation_api.py, test_remediation_history.py, test_target_history.py
```

既有测试只调整 JSON schema v10、新增状态 Trace 和目标持久化回调的合同。Local Provider、网络 Tool 的参数/SSRF/shell 安全实现、Auth 和 RAG/Citation 没有重构。

## 模型

| 模型 | 字段与约束 |
|---|---|
| ResolutionState | 仅 diagnosing / action_required / verifying / resolved / improved / unresolved / escalated |
| ResolutionRecord | state/version、reason code/summary、Verification/Plan 引用、主观确认、客观结果、升级建议/原因、更新及解决/升级时间 |
| ResolutionTransition | UUID、from/to、state_version、原因/摘要、Verification/Plan 引用、对象/任务版本与时间 |
| EscalationDecision | recommended、reason_code、summary；没有提交接口 |

Record 还保存 target subject/version、task version、case_start_task_version、用户主动请求标志。case_start 将症状复发后的新案例与旧修复尝试隔离，避免沿用旧问题的升级计数。所有用户输入模型 extra=forbid，不能直接提交 state、objective_result、admin_required 或其他权威字段。

## 确定性判定

ResolutionEvaluator 是纯函数；不读取模型回答，也不调用 LLM/Tool。Session 写入边界计算并通过 transitions.py 提交。

| 状态 | 实际规则 |
|---|---|
| diagnosing | 初始；对象/普通任务变化或复发后的重开；仍缺少安全动作或有效证据 |
| action_required | 当前作用域内有效 Plan 有 pending、low-risk、无管理员要求的步骤，且尚未进入复核等待 |
| verifying | awaiting_after_evidence / verifying；或已经执行过步骤后的显式新轮 baseline_ready |
| resolved | 同对象/当前任务的 completed + improved 复核，关键异常均恢复、证据有效，且用户明确确认 resolved |
| improved | 有客观改善但尚未完整确认、用户仍有症状，或用户单独报告改善/恢复但缺乏充分客观证据 |
| unresolved | 变差，或无变化且无剩余安全步骤；不等于不可修复，也不必立即升级 |
| escalated | 用户请求、权限/风险/充分基础设施依据等边界，或多次无改善且无安全步骤；只建议人工处理 |

12D 创建 Plan 时会自动生成 baseline_ready。若此时步骤尚未执行，按 action_required 展示，而不是一创建建议就显示正在验证。已完成步骤后显式开始下一轮 baseline_ready 才属于 verifying。

等待客观复核时仍以 verifying 表示流程，即使用户已主观报告恢复，也绝不会直接 resolved。用户请求人工优先，用户明确请求后保持建议，直到新任务/对象或新的复核流程重开。

## 严格 resolved 与主客观分离

必须同时满足：

1. Verification 指向当前 subject/version，After 属于当前 task version，且 task version 晚于 Baseline。
2. Before/After Evidence IDs 全部存在、scope/origin/context 一致，Remote 只能是客户端快照，Host 只能是主机 Tool；不能拿知识或其他对象证据替代。
3. 关键 Check 的目标/状态/变化必须能重新对应实际结构化 Evidence，不能仅信任 result 字符串或摘要。
4. 关键指标中原有异常已全部恢复，且没有已知 worsened 检查；不能因部分域名恢复就完全闭环。
5. After 非 stale、非 superseded、无 clock skew、未过 expires_at；无 expiry 的主机 After 最多采用 15 分钟内观察。
6. Verification completed/result=improved，不以 inconclusive/error/unsupported 作为完整恢复依据。
7. 用户明确确认原始症状 resolved。

12E 的 `VerificationEvaluator.evaluate()` 保留原综合语义：客观改善但用户仍报告故障时仍可为 inconclusive。新增 `objective()` 只抽出既有客观规则，Resolution 据此记录 `objective_result=improved` 和 `user_confirmation=not_resolved`，状态 improved，不抹掉 12E 冲突。

新的 Resolution confirm 是用户新的主观输入，会同步更新当前 Cycle 的 UserVerificationObservation，并重新计算其综合结果；不修改任何客观 Check/Evidence。这样用户后来明确确认恢复时，可以结束先前的主观冲突，而不是自动忽略冲突。重复相同确认不重写观察时间或增加 transition。

单独“好了”最多是主观改善；问句“好了？”、引述、假设和文档中的状态不作为确认。自然语言仅识别少量明确陈述，其他情况可用确认按钮。LLM 没有修改 Resolution 的 Tool，也不解析模型自由输出为状态。

## 升级策略

默认 `RESOLUTION_ESCALATE_AFTER_NO_IMPROVEMENT=2`（1–20）。只统计同对象、本次案例 epoch 内、引用有效、completed 且 result 为 unchanged/worsened 的 Cycle。failed/inconclusive/superseded 不计数，improved 打断连续无改善。历史有效尝试可来自之前 task version；过期后的历史观察不重新解释成当前可用于 resolved 的证据。

达到阈值但仍有安全步骤时可给人工建议，保留继续选择安全步骤的空间；达到阈值且无剩余步骤时 state=escalated。单次 unchanged + 无步骤为 unresolved，同时可以显示人工支持建议；这明确区分 unresolved 与 escalated。

其他 reason：

- no_safe_remediation_left：没有可继续采用的低风险动作，或剩余动作超出 P0 风险。
- admin_required：后续动作需要管理员权限，只建议人工核验，不提权。
- infrastructure_suspected：已有 supported infrastructure_issue，至少两条独立、当前作用域的有效异常证据支持，且无剩余安全用户侧动作；不因单次失败断言学校网络故障。
- insufficient_observability：动作尝试后缺少继续诊断所需的有效复核/直接可观测性；不把采集失败写成修复无效。
- user_requested：用户明确请求人工。
- verification_worsened：关键指标变差，建议暂停继续尝试并核验。
- user_declined_remaining_steps：全部跳过时准确写用户未继续执行，不写“措施均无效”。

当前自动 Hypothesis Tracker 没有生成基础设施故障这一类型；策略支持结构化 supported infrastructure_issue 的扩展，但不会为展示效果添加未经证据支持的新推断。中高风险/管理员步骤仍不由 P0 Catalog 自动生成，策略只为未来结构化边界提供 fail-closed 建议。

## 生命周期与审计

`transitions.py` 是唯一审计入口：真实状态变化才 state_version+1 并添加一条 Transition，同状态元数据更新不增加版本。同一 Case 内开放状态可按新依据流转；resolved 必须先经明确重开回 diagnosing。

- Target 切换：清除旧确认/升级请求，state=diagnosing，reason=target_changed；旧审计保留。目标与 Resolution 在同一 SQLite 更新中保存后再提交内存。
- 症状复发：“刚才好了，现在又打不开了”在 resolved Case 中使 task_version+1，target_version 不变，state=diagnosing，reason=symptom_recurred。不开自动网络检查，也不生成新的假精确计划。
- 普通新 task：重开，旧证据和处理状态仅归档；新问题不累计旧修复无改善次数。
- Verification 自身增加 task version：保持本次案例 epoch，清理上一状态确认，然后进入 verifying；不伪造额外诊断中间状态。若此前 resolved，则先明确重开。
- 用户撤回 resolved 确认也会重开新 task，不能在缺乏确认时继续保持已解决。
- 普通 Snapshot/Evidence 更新不是无条件重判入口，只有影响当前复核流程完成/失效时同步状态。

默认 `RESOLUTION_MAX_TRANSITIONS=30`（1–200），保留最近转换，state_version 单调递增不随裁剪归零。Trace 可关闭；关闭不影响独立的 Transition audit。

resolved 是其确认时间的闭环结论，不保证此后永不复发；证据自然老化不会自己创造复发事件。新进入 resolved 的每次判定仍必须通过完整时效检查。

## API 与安全

| 方法 | 路径 | 输入 |
|---|---|---|
| GET | `/api/session/resolution?session_id=<uuid>` | 读取当前状态/转换 |
| POST | `/api/session/resolution/confirm` | `{session_id, status: resolved|improved|not_resolved|unknown}` |
| POST | `/api/session/resolution/request-support` | `{session_id}` |

返回 resolution、resolution_transitions、相关简短 Trace 和 task_version。用户只提交主观确认，不直接 PATCH state。鉴权、owner scoped；Bob 访问 Alice 返回 404，未登录 401，busy 409，存储失败 503。422 不回显被拒绝的敏感值；响应 no-store。

确认/人工支持采用 Session draft → SQLite 持久化 → memory commit；失败不提交新 Resolution 或 Transition。按钮不增加 conversation_turns，也不创建假 Tool 调用。在首个实际聊天 Turn 之前，延续既有 Session 行架构将事件保留在内存，首个真实 Turn 创建历史行后一起保存，不编造问答。

## Context / Trace / History / Report

- Context 增加 RESOLUTION STATUS：状态/version、客观结果、主观确认、建议和原因；其他对象/任务的旧记录显示为 diagnosing，不注入原始证据 JSON 或用户备注。
- System Prompt 禁止覆盖结构化状态，区分 improved/unresolved/escalated，禁止声称已提交工单。
- 状态变化追加“诊断状态更新 / 确认问题已解决 / 建议升级人工处理”，origin=resolution，来自审计摘要而非 Raw CoT。
- History JSON v10，SQLite 表结构保持 v3；兼容 v1–v9，旧记录默认 diagnosing + 空转换，不从旧答案或 improved 文本反推 resolved。
- History Card 增加处理状态，不改变既有排序；Detail 展示原因、最后 Verification、用户确认和可折叠转换。
- Markdown 增加“最终处理状态”、对象、时间、客观结果、主观确认与原因；JSON 导出 resolution 和 resolution_transitions。

## Web 与 Mock

聊天顶部轻量 Badge + 状态面板，展示当前原因、客观/主观依据及审计。普通状态可确认症状、请求人工；有安全步骤时可跳转继续。resolved 提供查看过程/导出；escalated 只提供导出诊断报告，不出现假工单成功。History 只读，登出/新会话重置，异步返回有账号 epoch 与 Session guard，使用 textContent 展示状态文本。

Mock 也能用原模拟 Provider 的同参数只读验证完整流转状态，scope=mock_target、source_kind=mock_tools；按钮为“开始模拟验证”。Registry capability fail-closed，不能用 Local Provider 冒充 Mock 或远程客户端。Mock 请求与场景切换共享既有 runtime lock，UI/Report 继续标明 Mock 模拟终端，不代表真实校园网络。

Remote 显式“重新验证”创建下一轮 baseline_ready 后，显示“开始等待新快照”，调用原有 start API 推进到 awaiting_after_evidence，再采集上传。该按钮只开启等待阶段，不执行主机网络 Tool；避免所有步骤已完成时无法通过网页继续第二轮验证。

## 自动验收矩阵

| 编号 | 内容 | pytest |
|---|---|---|
| RS-01/02/03 | 初始、待操作、复核中 | test_resolution_evaluator.py |
| RS-04/05/06 | 严格已解决、部分改善、仅主观反馈 | test_resolution_evaluator.py、test_resolution_api.py |
| RS-07/08/09/10 | 未解决、连续无改善、基础设施边界、人工请求 | test_resolution_escalation.py、test_resolution_api.py |
| RS-11/12/13/14 | improved/Plan completed/变差/stale 均不直接 resolved | test_resolution_evaluator.py、test_resolution_api.py |
| RS-15/16 | 对象切换、自然语言复发、SSE 保存 | test_resolution_transitions.py、test_resolution_history.py |
| RS-17/18 | 幂等、版本、单条审计和有界保留 | test_resolution_transitions.py、test_resolution_api.py |
| RS-19/20/21 | 归属、重读、报告与 JSON | test_resolution_api.py、test_resolution_history.py |
| RS-22/23/24 | Badge/CTA、简短 Trace、不伪造工单 | test_resolution_ui.py、test_resolution_context.py |

另有 Model/输入越权、可配置阈值、过期 Host、篡改摘要、跨任务 Plan、复发 epoch、Mock 完整流转和存储失败原子性测试。

### 实际自动化结果

核心第一轮 53 passed in 3.04s；API/Context/History/UI 第一轮 30 passed in 29.21s；第一轮全量 874 passed in 218.37s。审阅后新增时效、作用域及摘要一致性防护，相关 44 项测试通过；随后全量 879 passed in 225.99s。远程二轮复核入口补充后，Web 回归 17 passed in 17.33s。目标切换的 Trace 计数也与新审计同步保存，相应 History 专项 11 passed in 12.83s。

2026-10-19 包含全部补丁的最终全量验收：

```text
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-12f-handoff --tb=short
880 passed in 187.50s (0:03:07)
```

相对修改前基线新增 89 个 pytest 用例，含 9 个新 DOM 场景；现有及新增共 73 个 DOM 场景全部执行，无 skip。`git diff --check`、修改文档相对链接与新增文件空白检查通过。测试使用隔离临时数据库、合成快照和受控 Provider，不替代下表的真实人工验收。

## 四项真实人工验收

以下全部具有合成快照、受控 Provider、API 与 DOM 自动测试，**尚未在真实设备/浏览器手工执行**，不伪造截图、网络恢复或工单。

| Case | 流程与预期 | 真实人工结果 |
|---|---|---|
| 1 Fully Resolved | DNS Before 异常 / After 正常；用户确认原始网页恢复 → resolved | 待执行 |
| 2 Improved Not Fixed | DNS 指标恢复但用户仍报网页打不开 → improved；保留 12E 冲突说明 | 待执行 |
| 3 Repeated No Improvement | 连续两轮有效 unchanged 且无剩余安全步骤 → escalated / repeated_no_improvement；仅建议人工 | 待执行 |
| 4 Problem Recurs | 已解决后报告复发 → task_version+1 / diagnosing / symptom_recurred；旧 resolved 审计保留 | 待执行 |

仅使用专用测试账号和授权的低风险场景。不要为验收关闭防护、重设 DNS/路由或影响重要业务。服务重启后的 History 可读，不自动恢复为可编辑活动 Session，这与既有 SessionStore 边界一致。
