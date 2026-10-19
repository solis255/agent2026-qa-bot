# Milestone 12G — Escalation Package

## 1. 范围与审计

2026-10-19（Asia/Shanghai）。完成结构化、脱敏、有版本的人工交接材料；不发送邮件、短信或 Webhook，不对接 ITSM、校内平台或工单系统，不远程执行、不提权、不自动修复。只使用“已生成报修材料”，不能理解为已提交工单。

修改前 Git 工作区干净。审计了 `SessionTaskState`、Evidence / Hypotheses / Trace / Context、client_snapshot、remediation、verification、resolution、API 路由及 presenter、History / reports、Web 和相关测试。当前导出实现在 `reports.py`，此前没有独立的根级 `exports.py`。本次材料专用导出位于 `escalation/exports.py`，不复制诊断报告或聊天 transcript。

基线实际命令与结果：

```text
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-12g-baseline --tb=short
880 passed in 212.86s
```

未读取/打印生产 `.env` 或 API Key，未清空生产 SQLite、用户历史或知识索引。

## 2. 文件清单

新增正式代码：

```text
src/netpilot/escalation/__init__.py
src/netpilot/escalation/models.py
src/netpilot/escalation/builder.py
src/netpilot/escalation/privacy.py
src/netpilot/escalation/handoff_catalog.py
src/netpilot/escalation/service.py
src/netpilot/escalation/persistence.py
src/netpilot/escalation/exports.py
src/netpilot/api/escalation_routes.py
```

新增测试与记录：

```text
tests/escalation_helpers.py
tests/test_escalation_models.py
tests/test_escalation_builder.py
tests/test_escalation_privacy.py
tests/test_escalation_handoff.py
tests/test_escalation_api.py
tests/test_escalation_history.py
tests/test_escalation_export.py
tests/test_escalation_ui.py
tests/web_escalation_runtime.cjs
docs/MILESTONE12G_VALIDATION.md
```

修改现有接入点：

```text
.env.example, README.md, DESIGN.md, docs/architecture.md, docs/test-cases.md
src/netpilot/config.py, main.py, history.py, reports.py
src/netpilot/agent/task_state.py, session.py, schemas.py, orchestrator.py
src/netpilot/agent/context_builder.py, reasoning_trace.py
src/netpilot/api/routes.py, models/schemas.py
src/netpilot/remediation/integration.py
web/index.html, app.js, style.css, package.json
tests/test_client_snapshot_history.py, test_conversation_persistence.py
tests/test_environment_profile_history.py, test_reasoning_trace_persistence.py
tests/test_remediation_history.py, test_target_history.py
```

既有测试的修改仅为当前历史快照版本断言 v10 → v11，旧版本兼容测试继续保留。没有重构 Provider、Tool Registry、RAG、ResolutionEvaluator 或修复/复核算法。`remediation/integration.py` 仅让纯材料请求跳过计划生成。

## 3. Schema 与结构化信息

`EscalationPackage` 及嵌套对象采用 `frozen=True, extra=forbid`；集合使用 tuple，避免列表或字典的嵌套修改。

| 字段组 | 内容与边界 |
|---|---|
| identity | package_id、递增 package_version、session_id、generated_at |
| target | subject、relationship_to_netpilot、execution_context、target_version、明确范围 notice |
| environment | OS family/version、接入方式、VPN/代理开关、影响范围/服务；不包含完整 UA、MAC、SSID 或位置 |
| issue | 标题、初始/当前症状、primary_issue、已知开始/最近观察时间、已完成 Turn 数；不是完整对话 |
| evidence_summary | id、类别、normal/abnormal/unknown、短摘要、观察时间、对象、task_version、origin、stale |
| excluded_or_weakened_hypotheses | supported/weakened/excluded、依据说明和保留证据引用；不倾倒全部 possible 假设 |
| remediation_summary | 步骤/计划版本、真实 completed/skipped/failed、用户报告 outcome、风险、脱敏备注与已知完成时间 |
| verification_summary | cycle id、关联步骤、状态/结果、关键指标差异、单列主观反馈、完成时间及历史标记 |
| resolution | 原状态与状态版本、客观结果、主观确认、实际 reason code/summary |
| escalation_reason | Resolution 升级原因，或 user_requested_material；triggered_by 明确区分 |
| handoff / sources | 静态只读核查项；另列自包含来源元数据，非网络检测证据 |
| privacy / completeness | 规则覆盖字段、私有 IP 掩码开关、完整度及具体缺项 |
| provenance | created_from_state/task/target_version、source_state_fingerprint、package_digest |

普通 API POST 和自然语言“我要报修 / 帮我生成报修材料 / 帮我整理给运维人员”均支持生成。自然语言路径不运行 Tool 或主回答 LLM；独立生成 API 不依赖模型配置。材料请求不调用人工支持状态变更接口、不重新判定 Resolution，允许 unresolved / improved / action_required 等状态主动生成。实际点击“请求人工支持”仍遵循原 12F 行为，两者不同。

## 4. Evidence 选择与假设

只选择同一 subject + target_version、符合执行位置的直接证据：远程 user_client 必须来自用户上传快照；Local host 仅能代表 NetPilot 主机；Mock 必须来自 mock_target。Knowledge Search 不进入 Evidence 表。

按有效时效、最新 After、异常状态、较新观察排序；用类别、检测目标、端口、状态与时效去重。五条相同 DNS 检测不会变成五行；不同域名/不同状态不强行合并。默认最多 `ESCALATION_MAX_EVIDENCE_ITEMS=12` 条，超量/合并在限制说明中注明。保留的正常证据支持排除项，不能只列异常。

过期、被替代、时钟超前、旧 task version 观察标为历史/可能过时；无当前有效证据则不能判为完整。客户端来源明确写为“用户主动上传的客户端快照（采集时点，非远程执行）”。跨对象的旧症状、primary_issue、步骤和复核不能冒充新对象事实。

假设优先保留 supported、weakened、excluded；引用映射到保留的代表证据。只有历史依据或保留依据不足时，说明需要重验，而不是暗示当前唯一根因已确认。

## 5. 修复与验证摘要

不把 skipped/failed 当作“措施执行但无效”。只汇总已有 completed/skipped/failed 步骤，pending 不冒充已尝试。原步骤 schema 没有实际 started_at，因此输出 null；不会把计划创建时间伪造成执行时间。completed_at 仅对 completed/failed 使用记录更新时间，跳过没有虚构完成时间。

每轮复核保留 id、关联步骤、结果和最多 12 项关键差异；Before → After 与主观反馈分开。旧对象、旧任务、过期 After 或已 superseded 的验证标为历史，不拿用户反馈或静态 RAG 证明客观恢复。已有两轮真实合成快照 unchanged 的测试经过原 12E/12F 状态机得到 repeated_no_improvement，而不是直接伪造 Resolution 状态。

## 6. 原因与人工核查目录

escalated 时引用实际 escalation_reason / summary（例如 repeated_no_improvement）；其他状态主动请求时使用 user_requested_material，原 Resolution 原样保留。

`handoff_catalog.handoff_checks()` 只使用固定模板：核对影响范围/AP/VLAN、认证会话、DNS/DHCP 与接入策略、故障时段 DNS 可用性/日志，必要时授权人员只读核对出口/代理策略。不由 LLM 编写运维动作，不建议重启核心交换机、删除 ACL、关闭安全软件或修改生产 DNS。Mock 模板强调不得据模拟材料处理真实网络。

## 7. 完整度

| 级别 | 判定 |
|---|---|
| complete | 明确对象、已知 OS/接入方式、当前对象问题描述、有效关键证据、实际步骤反馈及可比较完成复核 |
| partial | 有直接有效证据，但缺少环境、描述、步骤或可比较 After 等关键项 |
| limited | 没有当前对象的直接有效证据，只有陈述或旧/过期观察 |

这些级别描述材料完整度，不是诊断准确率、唯一根因证明或修复成功。即使 complete，仍可明确“未知代理状态 / 未核验校园认证”等局部限制。未实现认证后台检测，不补造认证平台结论。

## 8. 隐私、IP 与 URL

`EscalationPrivacyPolicy` 的 hostname/MAC/SSID/tokens/cookies 移除不可关闭；API 不接受客户端隐私策略。构建器只复制白名单摘要字段，不输出原始快照、Tool data/arguments、整个数据库、系统提示词、模型隐藏推理或聊天 transcript。

所有可导出的自由文本（症状、证据、用户备注、假设名、验证差异和来源）均脱敏；还收集证据内部敏感键的已知值，移除它们在摘要中的重复出现。规则覆盖 MAC/BSSID、SSID、主机名、password、cookie、authorization、API key、token、secret、credential、完整 UA 和精确坐标；Header 整行移除，避免 Cookie 第二个值泄露。

- 默认保留已经存在的私有 IP，以便用户自行交给授权人员排查；不额外收集公网 IP。
- `ESCALATION_MASK_PRIVATE_IP=true` 时，如 `172.23.221.167` → `172.23.221.xxx`，私有 IPv6 也移除。
- URL 去掉 userinfo、fragment 和敏感 query key，保留安全参数，例如 `?token=abc&lang=zh` → `?lang=zh`。
- 来源按 official → maintainer → community 排序；社区来源明确“需官方核验”。导出中的 References 自包含，不要求接收人访问原 Session 页面。

脱敏不是任意文本中秘密的形式化识别证明；材料仍可能包含用户主动描述的业务信息及合法域名，转交前应人工审阅。`privacy.redacted_fields` 表示应用的规则覆盖范围，不是声称所有字段都曾在输入出现。

## 9. 指纹、不可变版本与摘要

`source_state_fingerprint` = 规范化结构化摘要 + Resolution state_version + task_version + target_version + plan_version + 最后 verification_id + 脱敏策略的 SHA-256。它也覆盖同一状态版本内的摘要/环境/反馈变化。仅忽略材料请求本身带来的 Turn 数变化。

相同指纹复用最新包，不生成新版本/Trace。发生变化时生成 vN+1，默认仅保留最近 `ESCALATION_MAX_PACKAGES=5` 版，sequence 不回退。达到保留上限移除最老版本是明确保留策略，不是原地重写旧版。

`package_digest` = 将 package_digest 字段排除后，JSON `ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False` 的 UTF-8 SHA-256。读取/导出校验摘要。它不是数字签名，无法对抗拥有数据库写权限的攻击者。

旧版不按最新状态重建；外层 GET 返回 stale_package_ids，或 historical=true，包内字节语义与 digest 不变。生成时间有效的旧观察不保证永远有效。

## 10. History 与持久化

历史 JSON Snapshot 升级为 v11；v1～v10 继续兼容，默认 escalation_packages=[]，不从旧聊天文本反推报修材料。原 SQLite metadata schema 保持 v3，新建兼容增量表 escalation_packages，使用 owner/session/version 唯一约束和不可变插入校验。

同一事务保存脱敏工件并更新已有 Session History 的 packages / Trace / Trace count，不增聊天 Turn。首次聊天前也能持久化工件，但不制造一条假的 History；第一次真实聊天后合并到 Session 行。重启后通过原账号及保存的 session_id 仍可查询/导出，历史页面可读取已有 History 里的版本。运行时 Session 失效不会自动恢复为可编辑状态。

`DIAGNOSIS_HISTORY_ENABLED=false` 时仅在内存保留，重启不保留，卡片生成响应会提示；启用但存储不可用的独立生成请求返回安全 503，不提交 draft。聊天仍遵循已有 History 写入失败降级规则：日志记录 diagnosis_storage_error，响应不包含成功保存的 record_id，不能把内存成功当作数据库持久化成功。

## 11. API 与导出

所有接口要求登录，当前 owner 限定；非归属资源 404，匿名 401。GET/下载 no-store，导出 nosniff。请求只能提交 session_id；不接受客户端 Evidence、reason、Resolution、user_id、command 或关闭脱敏。

| Method | URL | 说明 |
|---|---|---|
| POST | /api/session/escalation-package | JSON `{session_id}`，主动生成/复用 |
| GET | /api/session/escalation-package?session_id=UUID | 版本列表、外层 stale/historical 状态 |
| GET | /api/session/escalation-package/PKG_ID?session_id=UUID | 原版本 EscalationPackage |
| GET | /api/session/escalation-package/PKG_ID/export?session_id=UUID&format=md | 原版本 Markdown 附件 |
| GET | 同上 format=json | 精确 EscalationPackage Schema JSON 附件 |

Markdown 包含 12 节及 References：基本信息、环境、问题、关键证据表、假设、修复表、Before/After 表、处理状态、原因、核查建议、完整度、隐私。转义不可信 Markdown/HTML，JSON 不附带 History 外壳或原始 DB 行。

沿用 `DIAGNOSIS_REPORT_MAX_BYTES` 导出上限，超限 413；Session busy 返回 409，生成/存储错误返回安全 503。日志仅记录异常类型，不记录材料内容、原始输入或堆栈。独立请求构建/持久化在隔离 draft 上完成，失败不发布到 Session。

## 12. Web / Trace / Context

独立“报修材料”卡片允许用户主动生成；escalated 时同样可见。生成后显示版本、时间、完整度、范围及原因摘要、缺项、预览、Markdown/JSON 下载、“生成最新版报修材料”。历史视图隐藏生成按钮，仍可预览和下载具体旧版本。没有“提交工单”或对外发送按钮。

所有自由文本采用 textContent，预览为安全纯文本；下载由已认证的同源请求取得已脱敏内容。退出、账号切换、会话切换、异步返回过期均有守卫，避免旧账号材料显示给新账号。

Trace 事件 event_origin=escalation，只显示“生成升级报修材料 / 报修材料信息不完整”的公开决策摘要；不是模型思维链。Context Builder 仅增加 ESCALATION PACKAGE STATUS（版本、完整度、生成时间），不注入完整材料包。

## 13. EP 验收矩阵

| ID | 场景 / 预期 | 自动测试 |
|---|---|---|
| EP01 | 两轮 DNS 无改善、escalated、完整材料 | test_escalation_builder.py |
| EP02 | 主动请求但状态不变，0 新网络调用 | test_escalation_builder.py / api.py |
| EP03 | 30 条证据最多 12 条 | test_escalation_builder.py |
| EP04 | 同目标同状态 DNS 五条去重 | test_escalation_builder.py |
| EP05 | completed/no_change、skipped、failed 区分 | test_escalation_builder.py |
| EP06 | 两轮 Before/After 摘要 | test_escalation_builder.py |
| EP07/08/09 | 设备标识、凭据、默认 hostname 脱敏 | test_escalation_privacy.py |
| EP10/11 | URL 参数过滤、私有 IP 可选掩码 | test_escalation_privacy.py |
| EP12/13 | 缺 After=partial，无直接证据=limited | test_escalation_builder.py |
| EP14/15 | 静态 DNS/DHCP 核查项、Mock 明示 | test_escalation_handoff.py |
| EP16 | 相同状态幂等且不多 Trace | test_escalation_builder.py / api.py / history.py |
| EP17 | 新状态 v2，v1 原样，最多保留五版 | test_escalation_builder.py / history.py |
| EP18 | Alice/Bob/匿名与重启后的归属隔离 | test_escalation_api.py |
| EP19 | 独立工件 + History 重启读取 | test_escalation_history.py |
| EP20/21 | 自包含 Markdown / 精确 JSON Schema | test_escalation_export.py / models.py |
| EP22/23 | 无 transcript/raw snapshot/Tool JSON/隐藏推理 | test_escalation_export.py |
| EP24 | 卡片、生成、历史、预览、XSS、重置、时效、会话/异步守卫 | test_escalation_ui.py（9 个真实 DOM 场景） |
| EP25 | 两类公开 Trace，不倾倒原始数据 | test_escalation_builder.py / api.py |

额外覆盖：构建与存储失败回滚、超限导出、busy、冻结嵌套对象、禁止关闭脱敏、摘要篡改拒绝、来源排序/社区核验、跨对象症状隔离、紧凑 Context、重复材料聊天不增加版本。

## 14. 实际测试结果

首轮 7 个新测试文件：59 passed in 12.26s。现有 Resolution API/UI 冒烟：17 passed in 16.20s。首次全量 947 passed / 1 failed：失败为旧测试仍断言历史 schema=10；已更新为 11。后续补充边界和兼容回归：45 passed in 6.25s。

第一轮完整通过：952 passed in 196.69s。最终额外补充“新复核待 After 不能借旧复核判完整 / 当前构建器故障不影响旧材料读取”防护后，最终全量结果：

```text
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-12g-handoff --tb=short
954 passed in 193.74s (0:03:13)
```

比基线新增 74 个 pytest 用例，包含 9 个新 DOM 场景；总计 82 个 DOM 场景全部实际执行，无 skip。`git diff --check` 和修改 Markdown 的相对链接检查通过。测试全部使用临时数据库、合成快照、Fake LLM/受控 Provider，不代表真实校园故障或人工浏览器验收已完成。

## 15. 四项真实人工验收与当前结果

以下有合成快照、受控 Provider、API/DOM 自动化覆盖，**未在真实设备/浏览器手工执行**；不伪造截图、校园故障、真实修复效果或工单。

| Case | 人工操作及预期 | 真实人工结果 |
|---|---|---|
| 1 Repeated DNS Failure | 专用测试账号，远程 Windows/campus_wifi；DNS 异常、网关正常，两次低风险反馈 no_change + 两轮 unchanged 后 escalated/repeated_no_improvement；材料含 DNS/DHCP/同网段核查、隐私安全 | 待执行；原状态机合成场景自动化通过 |
| 2 Incomplete Material | 只填症状/环境，不上传快照，主动生成；partial/limited，明确缺直接证据和 After | 待执行；对应 API/构建自动化通过 |
| 3 Privacy | 仅使用合成 DESKTOP-ABC、00-11-22-33-44-55、TJU-WLAN、token=abc123、password=test；检查 Markdown/JSON 均不含原值；不得填真实凭据 | 待执行；两种导出格式脱敏自动化通过 |
| 4 Versioning | 保存 v1，再补新快照/验证生成 v2；旧版 JSON、摘要和导出不变，历史可读取两版 | 待执行；API/SQLite/SSE/不可变导出自动化通过 |

运行完整测试需 Node/jsdom；缺依赖会明确 skip，不能把 skip 当作 Web 已验收。真实浏览器/LAN 验收需另行使用专用测试账号和授权的低风险场景。History 持久化不等于跨进程运行时 Session 恢复。
