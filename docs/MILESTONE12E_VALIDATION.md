# Milestone 12E — 修复前后验证

## 范围与安全边界

Verification ≠ Resolution。只实现结构化 Before/After 验证，不自动执行修复、不提权、不修改网络配置、不判定 resolved/unresolved/escalated，不生成 Support Package 或工单。

远程 user_client 的 After 只来自主动上传的 Windows Snapshot，网络 Provider 调用数必须为 0。Host 则只在明确完成手动步骤并点击开始后，通过现有 ToolRegistry/Provider 执行基线相关的关键只读检查；不新增 shell、远程命令或用户指定 Tool 参数入口。Mock 不提供真实 Host 验证或远程客户端上传通道，模拟基线 source_kind 明确为 mock_tools，不冒充主机证据。内部验证流程 failed 后应重新诊断获取有效证据，不从错误流程直接推断改善。

12C 快照依然是未签名、用户上传的采集时点数据。本阶段绑定的是 Session 的逻辑 target subject/version，不能认证上传文件确实来自同一物理设备；用户应在同一设备重新采集。知识资料与主观反馈都不成为客观网络 Evidence。

## 修改前审计与基线

已核对 Orchestrator、SessionTaskState、EvidenceRecord、Context Builder、Reasoning Trace、ToolPolicy、TargetCapability、client_snapshot、remediation、API/Presenter、History/Report、Web 与 tests。

- 修改前 `git status --short` 为空；没有清空数据库。
- 修改前全量：`711 passed in 152.29s`。
- EvidenceRecord 已经有 task_version、target、observed_at、superseded 和快照时效字段，无须重复新增版本字段。
- 12D Step status 为 pending/completed/skipped/failed，outcome 为 unknown/improved/no_change/worse；后者是用户声明，不是网络验证结果。
- 普通 Dedup 仍以规范化 Tool Signature 和当前任务可复用 Evidence 为依据。

## 文件边界

新增核心代码：

```text
src/netpilot/verification/
  __init__.py
  models.py       # 有界合同与冻结字段
  baseline.py     # 按对象/执行位置筛选，冻结指标摘要与 ID
  planner.py      # issue + 静态模板指标，critical/supporting
  diff.py         # 同指标/同目标比较
  evaluator.py    # 确定性总结果和主客观冲突
  service.py      # 生命周期、快照绑定、Host 复核、紧凑 Context
src/netpilot/api/verification_routes.py
```

集成改动位于 Agent/Session、remediation、client_snapshot、API schemas/presenters/routes、History、Report、Settings、`.env.example` 和 Web。没有重构稳定的 Local Provider、网络 Tool 安全检查、Auth 或 RAG/Citation 实现；普通去重与 Function Calling 调度未增加任意刷新权限。

修改文件清单（源码路径均以 `src/netpilot/` 为根）：

```text
.env.example, README.md
agent/context_builder.py, agent/orchestrator.py, agent/prompts.py
agent/reasoning_trace.py, agent/schemas.py, agent/session.py, agent/task_state.py
api/client_snapshot_routes.py, api/presenters.py, api/remediation_routes.py, api/routes.py
client_snapshot/service.py, config.py, history.py, main.py, models/schemas.py
remediation/catalog.py, remediation/integration.py, remediation/service.py, reports.py
web/app.js, web/index.html, web/package.json, web/style.css
tests/test_client_snapshot_history.py, tests/test_conversation_persistence.py
tests/test_environment_profile_history.py, tests/test_reasoning_trace_persistence.py
tests/test_remediation_api.py, tests/test_remediation_history.py, tests/test_target_history.py
```

既有测试的修改仅为历史 schema v9 和新增验证开始 Trace 的合同更新。新增测试包括下文 10 个 `test_verification_*.py`、`verification_helpers.py` 和 `web_verification_runtime.cjs`；另新增本文档。

## Schema 与冻结

| 模型 | 核心字段 |
|---|---|
| VerificationCycle | UUID、递增 sequence、target subject/version、plan ID/version、step IDs、status、baseline/after、checks/diffs、result/summary、user_observation、after_task_version、时间戳 |
| VerificationEvidenceSet | captured_at、Evidence IDs、snapshot ID/sequence、source_kind、stale、task_version |
| VerificationCheck | metric、规范化 target、Before/After 状态与简短展示值、critical/supporting、change、interpretation |
| EvidenceDiff | metric/target、Before/After 文本、change、解释；不是 raw dict |
| UserVerificationObservation | symptom_status、最多 500 字可选备注、服务器记录时间 |

baseline EvidenceSet 使用 frozen 模型及 tuple IDs，Cycle 的 baseline 字段不可赋值；Check 的 baseline 状态、值、metric、target 和 importance 也不可赋值。EvidenceSet 只引用 ID，不复制原始 Tool JSON。Check 保存的是冻结的有限指标摘要，不是证据原文。

plan 创建时立即建立 baseline candidate（baseline_ready）。候选只采用当前 subject/version/task version、正确执行 scope/origin 的有效网络记录。知识、用户声明、其他对象和旧 task 不进入 Baseline。旧 Evidence 仅 superseded，不因新快照被删除；Session 的普通 Tool Evidence 修剪会保护保留中 Cycle 的 Before/After ID。快照归档仍遵守 12C 容量限制，满时拒绝新导入而非静默丢失旧证据。

## Planner 与比较语义

静态 RemediationTemplate 新增 verification_metrics tuple，保留原先给用户看的自然语言 verification。Planner 将模板指标与既有 primary_issue 映射结合：DNS、网络配置/网关、ICMP、TCP、HTTP 等既有 issue 决定 critical，其余实际采集指标支持解释。没有相应客观基线的 VPN、认证或用户症状，不伪造检查结果。

- DNS：规范化同域名才能比较；异常→正常为 improved，正常→异常为 worsened，同有效状态为 unchanged。
- Gateway：同网关目标比较；普通公网 Ping 不冒充默认网关。
- TCP：规范化 host 和 port 都必须一致。
- HTTP：同规范化 URL（包括路径与 query）比较，不把其他网页成功当成原 URL 恢复。
- Network configuration：展示 DNS/IPv4/默认网关配置缺失、存在或未知；配置变化仅作解释，不能据此判 DNS resolution 正常。
- missing/unsupported/error/unknown、过期或疑似时钟偏差：not_comparable/unknown，不产生恢复结论。

Evaluator 优先级：任一可比较 critical worsened → worsened；至少一个 critical improved 且无 critical worsened → improved；全部 critical 可比较且 unchanged → unchanged；否则 inconclusive。Supporting 不覆盖 critical。部分关键指标不可比较时，表格仍明确缺口；有局部改善不代表完整恢复。

用户说恢复但关键指标仍异常，或客观指标改善但用户报告症状未改善，均为 inconclusive，并保存冲突说明。只有主观反馈同样为 inconclusive。步骤 outcome 会转换为带明确主观类型的 UserVerificationObservation，不会被直接采用为 improved。

## 生命周期、版本与去重

```text
Plan 创建 → baseline_ready
完成一个手动步骤 → task_version + 1，target_version 不变
  → awaiting_after_evidence
  → Remote：新快照 / Host：点击开始，重测相关关键指标
  → verifying → completed 或 inconclusive
内部流程异常 → failed（不等于网络 unchanged）
未结束时切换对象 / 普通 State Change / 绑定 Plan 失效 → superseded
```

同一等待阶段完成的其他步骤归入同一验证批次，记录多个 step IDs，不重复递增 task_version。跳过或执行失败的步骤不启动验证。下一个已完成 Cycle 后的修复步骤或显式重新验证创建下一 sequence，优先从上一轮 After 的当前有效 Evidence 建立新 Baseline。

正常重复 start/create 返回已有完成结果，不重新调用 Tool。显式 `reverify=true` 才新建下一 Cycle。验证中的重复 start 不产生并行重复请求；Session 锁串行保护、busy 返回 409。

验证刷新是独立、服务器端确定的调用入口：只采用冻结 Baseline 中关键指标的原 Tool/原参数，最多 10 次，只读 allowlist 由 Registry 重新校验。purpose=verification，带 verification_id，新记录归入当前 task version，并重新进入普通 Signature Dedup。没有改动普通 Orchestrator Dedup，也不允许 LLM/API 自行传入“跳过去重”。

一次验证拥有的 task bump 和 After 快照替换不会直接销毁其绑定 Plan；外部环境、对象或普通诊断状态变化仍按原规则失效。验证结束后用户明确要求下一步，可重新生成 Plan，排除已完成/跳过的等价操作，并保留已完成验证历史。

## Remote Snapshot

绑定必须同时满足：最新 Cycle 正在 awaiting_after_evidence、user_client、相同 target version、当前 after task version、记录 origin/scope 为 client_snapshot，且所有 generated_at 严格晚于 baseline.captured_at。

旧快照允许通过原 12C 导入机制归档，但不会绑定 After；提示“该快照生成时间不晚于修复前基线，无法用于修复后验证”，保持等待。格式/隐私校验失败不会提交 Session 修改。过期/clock skew 快照可导入、可保留对比，但结果 inconclusive，不作为改善依据。12C 固定探测范围和采集限制没有放宽。

## API、归属与原子性

| 方法 | 路径 | 内容 |
|---|---|---|
| GET | `/api/session/verification?session_id=<uuid>` | 当前账号的保留 Cycle |
| POST | `/api/session/verification` | `{session_id, reverify?: false}`；幂等创建，显式重新验证用 true |
| POST | `/api/session/verification/{id}/start` | `{session_id}`；Remote 等待上传，Host 限定只读复核 |
| POST | `/api/session/verification/{id}/user-observation` | `{session_id, symptom_status, note?}`；仅主观反馈 |

全部鉴权、owner-scoped；Bob 访问 Alice 为 404，未登录为 401。旧对象或失效验证不可修改；busy/冲突为 409，存储错误为 503。拒绝任意 Tool 参数、command、user_id 等额外字段，422 不回显敏感输入。返回 no-store。

Session draft → 持久化 → memory commit；存储失败不提交状态、版本或反馈。不写伪造 chat Turn，上传和按钮反馈不增加 conversation_turns。主机检查是只读；进程/存储失败后不承诺分布式 exactly-once，不能把失败称为网络无改善。

## Context、Trace、History 与 Report

- Context 新增 VERIFICATION STATUS：sequence、对象、Before/After task version、状态、结果、最多 10 项紧凑变化、主观反馈类型；不注入备注或完整原始 JSON。明确过期/失效结论仅属历史。
- “现在怎么样？”等明确查询直接复用当前结构化验证结果，不重新诊断或调用 LLM/Tool。
- Trace 记录“记录修复前基线 / 开始修复后验证 / 完成修复前后对比”，带 Evidence 引用和 verification origin，不输出 Raw CoT；尊重 Trace 开关。
- Session History JSON v9，兼容 v1–v8，旧记录 verification_cycles=[]；SQLite 表结构仍 v3，无清库。Client 历史由已有 client_evidence 保存，Host Evidence 由 verification_evidence 保存，Cycle 只引用 IDs。
- 默认最近 10 轮，`VERIFICATION_MAX_CYCLES` 范围 1–50；sequence 保持单调递增。活跃 Session 仍为进程内存，服务重启后 History 可读，不自动恢复为可编辑活动 Session。
- Markdown 报告增加步骤、对象、版本、时间、引用、Before/After 表格、总结果和主观反馈；JSON 完整导出 Cycle。文本采用既有转义，前端不直接显示 raw dict。
- 实际 Host 复核进入 Tool Timeline，标识 `Purpose: Verification`，历史记录保留真实调用；Snapshot 不伪造 Tool Call。

## Web

新增默认折叠“修复后验证”。Remote 显示需重新采集提示、下载脚本及新快照上传入口；Host 显示开始验证。显示四类结果、Before/After 指标表、用户主观反馈和非 Resolution 提醒。History 只读，旧对象不能修改，Auth epoch/session guard 防止延迟响应跨用户/跨会话写入，登出与新会话清空显示。

## 自动化验收矩阵

| ID | 用例 | pytest |
|---|---|---|
| BV-01/02 | DNS 恢复 / 无变化 | test_verification_snapshot.py |
| BV-03/04 | 网关变差、不同 DNS / TCP target 不可比较 | test_verification_diff.py |
| BV-05/06 | Remote Host 调用为 0 / Host 同参数合法刷新 | test_verification_target_scope.py、test_verification_api.py |
| BV-07/08 | 冻结不变、旧 After 保持等待 | test_verification_baseline.py、test_verification_snapshot.py |
| BV-09/10/11 | 两向冲突、只有主观反馈 | test_verification_evaluator.py、test_verification_api.py |
| BV-12/13/14 | task/target version、旧对象、失效 Plan | test_verification_target_scope.py |
| BV-15/16 | 重复验证不重跑 / 归属鉴权 | test_verification_api.py、test_verification_target_scope.py |
| BV-17/18/19 | 重读、表格导出、决策摘要 | test_verification_history.py |
| BV-20 | Remote/Host/表格/反馈/历史/XSS/重置 | test_verification_ui.py + web_verification_runtime.cjs |

另覆盖冻结模型、输入隐私、Catalog metrics、主机最小检查、Evidence pin、stale/skew、内部流程失败、循环上限、Trace 关闭和存储失败回滚。

### 实际测试记录

新增专项第一轮：72 passed in 20.58s。第一轮全量：1 failed, 782 passed in 150.50s，发现 12D“验证后下一步不能重新推荐旧动作”的兼容问题；已修复，相关 43 项回归及额外 28 项测试通过。

2026-10-19 最终代码（包含失效 Plan 防复活和新 Turn 冻结基线的容量保护）全量验收：

```text
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-12e-release --tb=short
791 passed in 148.75s (0:02:28)
```

相对修改前基线新增 80 个 pytest 用例，其中 8 个新 DOM 场景；现有与新增共 64 个 DOM 场景全部执行，没有 skip。`git diff --check`、新增文件空白检查、修改文档相对链接检查通过。真实人工验收状态仍见下表；自动化结果不替代人工验收。

## 四个人工验收 Case

以下均有合成快照、受控 Provider 和 API/DOM 自动测试，**未在真实设备和真实浏览器手工执行，不伪造截图或网络恢复**。

| Case | 手工步骤 | 预期 | 真实人工结果 |
|---|---|---|---|
| 1 Remote DNS Recovery | 同一设备 Before DNS 两域名失败、网关正常；完成低风险操作并上传新快照，DNS 两域名成功 | improved，不出现自动 Resolved | 待人工执行 |
| 2 Remote No Change | 新快照 DNS 仍失败 | completed / unchanged，不是流程 failed | 待人工执行 |
| 3 Feedback Conflict | After DNS 恢复，再反馈网页仍打不开 | inconclusive，并保留主客观差异 | 待人工执行 |
| 4 Host Recheck | 同一主机 github.com DNS 原失败；完成步骤后点击开始 | 仅 dns_lookup 同域名重测、Purpose: Verification、改善不代表解决 | 待人工执行 |

建议使用专用测试账号与授权的低风险场景。不要为验收故意关闭防护、修改 DNS/路由或影响重要网络业务。
