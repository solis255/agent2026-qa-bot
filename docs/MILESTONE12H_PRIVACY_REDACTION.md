# Milestone 12H：Privacy Redaction

## 入口和出口盘点

修改前扫描了 Agent task/evidence/trace、Client Snapshot、Remediation、Verification、Resolution、Escalation、History、Report、API presenter/SSE、配置、日志和 Web 页面。实际仓库没有独立的 `exports.py` / `logging.py`：普通导出位于 `reports.py`，日志入口为 `observability.py`，报修导出位于 `escalation/exports.py`。

| 原有边界 | 12H 处理 |
| --- | --- |
| 12G `escalation/privacy.py` 有独立正则 | 改为共享引擎的兼容门面；已知敏感值的跨文本清理也集中到 privacy |
| 12C 上传执行严格 schema、敏感 key 拒绝、主机名和网卡标识清理 | 保留拒绝语义，补齐凭据 key 变体；规范化 Evidence 再经过共享引擎 |
| 修复/验证备注以前直接拒绝包含凭据的文本 | 合法备注先脱敏再接受，保留原有长度和状态约束 |
| 工具结果可能包含 URL、主机名和任意结构化数据 | 原结果仅用于短期执行；Evidence、Presenter、任务内存提交前清理；工具 URL 在发出请求前移除敏感 query |
| History 结构化 snapshot 和索引预览列直接保存文字 | 写入前统一清理，读取旧记录及列表预览再做安全处理 |
| Report、JSON/Markdown、来源链接 | 最终生成前安全检查，保留经脱敏的会话内容和既有诊断结构 |
| 日志按部分 key 替换，工具异常可能包含 traceback | 仅允许元数据；未知 payload 字段直接不记录，工具异常只记录类名 |
| 前端直接回显刚发送的用户原文 | 等待服务端隐私处理后显示安全消息；调试数据只接收清理后的响应 |

## 策略和引擎

新增 `src/netpilot/privacy/`：

- `models.py`：`PrivacyPolicy` 配套的 `RedactionResult`、`RedactionMetadata`、`PrivacyAuditEvent` 契约及策略版本常量。
- `policy.py`：不可变 `PrivacyPolicy`、Settings 映射和请求级 ContextVar，避免多个应用/请求共享可变策略。
- `detectors.py`：集中定义预编译的凭据、MAC、主机名、SSID、私钥、JWT 等检测器。
- `url.py` / `ip.py`：URL 和地址语义处理。
- `redactor.py`：mapping/model/sequence/text/header/evidence、安全展示与导出的共同实现。
- `metadata.py` / `logging.py` / `middleware.py`：无原值的处理记录、日志元数据白名单、JSON 出口和异常处理。

Hard Redaction 无关闭开关：password/passwd/pwd、Token、Cookie/Set-Cookie、Authorization/Proxy-Authorization、API key、Secret、Credential、Session Token、Private Key，包含常见大小写、下划线、连字符及 camelCase 变体。配置错误不能让引擎保留凭据。

可配置项和默认值：

| 环境变量 | 默认值 | 行为 |
| --- | --- | --- |
| `PRIVACY_MASK_PRIVATE_IP` | false | 开启后 IPv4 保留前三段，IPv6 文本保留 /64 前缀 |
| `PRIVACY_REMOVE_PUBLIC_CLIENT_IP` | true | 按明确的客户端公网 IP 字段语义处理；保留公开目标地址 |
| `PRIVACY_REDACT_HOSTNAME` | true | 清理结构化主机名、明确标注的主机名和常见设备名 |
| `PRIVACY_REDACT_EMAIL` | false | 按需清理邮箱 |
| `PRIVACY_REDACT_PHONE` | false | 按需清理常见中国大陆手机号 |
| `PRIVACY_POLICY_VERSION` | 1 | 仅接受已实现的版本 |

报修材料继承 12G 更严格的主机名、MAC、SSID 清理要求；旧的 `ESCALATION_MASK_PRIVATE_IP` 与统一私网 IP 开关取更严格的结果。普通的 `network_name`、内部 `session_id`、DNS 域名、目标域名和端口不会仅因名称被删除。

统一占位符为 `[REDACTED]`、`[REDACTED_MAC]`、`[REDACTED_HOSTNAME]`、`[REDACTED_SSID]`，不包含原值长度或设备 hash。已知结构化敏感值也会从同一次处理的其他文本中移除。

处理顺序覆盖敏感字段、URL/凭据、标识符、IP 策略和长度限制。先脱敏再截断；截断不会留下半个 URL 或半个占位符。模型字符串同时遵守原字段长度约束，避免脱敏扩展导致后续 History 无法读取。递归深度默认限制为 24，自由文本默认限制为 4096。

## URL、Header 和 IP

URL 只允许绝对 HTTP(S)，移除 userinfo、敏感 query 和 fragment。`lang=zh` 等正常参数保留，Markdown 链接闭合符保持可用。IPv6 URL 默认保留；开启掩码后其主机部分归零，保证 URL 语法有效。文本中的 IPv6 使用前缀加 `xxxx`。

Header 按 key 清理 Authorization、Cookie、Set-Cookie、Proxy-Authorization、X-API-Key 等。普通 Content-Type 等诊断字段保留。

默认保留私网地址、DNS、网关、目标公网地址、loopback 和 link-local。客户端公网 IP 使用字段语义清理，不对所有公网 IP 做全局替换。启用私网掩码仍保留回环和链路本地地址。

## 持久化、旧数据和导出

Evidence 和 Reasoning Trace 创建时就经过安全处理。Session 的变更在持久化回调与内存提交前清理，History 同时覆盖首次插入、合并、局部更新和预览列。Remediation、Verification、Resolution 和 Escalation 的文本均在这些共同边界内。

旧 History 和旧 12G 材料保持读取兼容；读取和导出执行安全处理，不扫描或批量重写旧数据库。旧报修材料先验证原摘要，再对读取副本脱敏，输出副本重新计算摘要。新材料仍执行 owner/session 校验和不可变冲突检查。

普通报告与报修材料的 JSON、Markdown 均在生成前执行最终安全处理。JSON API 出口还有统一 safety pass；SSE 在切分回答前清理整段内容，防止凭据跨分片漏检。认证 Cookie 的正常签发/清除及无内容响应保持兼容。

`privacy_policy_version` 和 `privacy_metadata` 保存策略版本、类别、次数及标志，不保存删除前的内容。类别使用受限枚举。无变化的重复处理保持结果一致。

日志使用 `safe_log_context` 白名单，仅记录请求/会话 ID、工具、状态、耗时、计数、错误类和既有诊断运行指标。request body、上传 JSON、完整参数/结果及未知 payload 不进入日志。审计事件为 `redaction_applied` / `sensitive_upload_rejected`，只包含类别、次数和上下文。

API 参数错误不回显 input/ctx；未处理异常返回通用说明和 request ID，不回传异常原文。HTTP 日志使用路由模板，避免记录任意路径内容。

## UI

快照上传区显示简短隐私说明。报修区域及每份材料显示凭据、MAC/SSID、主机名保护和策略版本。用户消息等待服务端处理后显示 `redacted_user_message`，历史、报告预览、工具数据和调试区使用安全响应。

## 验证

基线：仓库 `.venv` 中 **954 passed**。系统 Python 没有 FastAPI；系统 pytest 临时目录有权限问题，因此验证使用仓库内独立 `--basetemp`，不清理或修改业务数据库。

新增测试覆盖十个要求的 `test_privacy_*.py` 文件，另有 `test_privacy_api.py` 和公用 helper，包含：

- Hard Policy 不可关闭、嵌套 key 和模型/序列、已知值重复出现、幂等、递归/长度边界。
- URL 凭据/敏感参数/fragment、危险 scheme、Header、可点击 Markdown、IPv6 URL。
- 默认地址保留、可选 IPv4/IPv6 掩码、客户端公网 IP 与公开目标 IP 区别。
- 快照 schema 拒绝及无原值审计、Evidence/Trace、真实 API 备注提交、SSE 分片。
- SQLite snapshot/索引列无原值、旧数据读取不改写、JSON/Markdown 最终检查、旧材料摘要兼容。
- 日志丢弃 payload、只记录类别和次数、API 错误不回显输入。

两处旧测试预期随 12H 更新：验证备注从“拒绝凭据文本”变为“接受已脱敏文本”；报告中的 `javascript:` 原文变为安全占位符。保留了状态、长度、确定性、序列化往返和导出大小限制等原有断言。

四个人工验收场景通过测试程序重放，并非人工点击浏览器：

| Case | 验证方式 | 预期 |
| --- | --- | --- |
| 1 敏感快照 | 上传 API 参数化提交 MAC/SSID/password/Cookie/Token/私钥字段 | 422；响应和审计无原值 |
| 2 用户备注 | 实际 PATCH 提交 `我的 token=abc123，重新连接以后还是不行` | 200；内存、SQLite、Markdown/JSON 和日志无 `abc123` |
| 3 地址保留 | 结构化地址及导出测试 | 默认保留 Client/DNS/Gateway；开启配置后保留前缀并掩码 |
| 4 报修导出 | 混合主机名/MAC/SSID/Bearer/URL Token 的完整材料 | 两种格式均无敏感原值，保留 `lang=zh`、DNS、网关和端口；摘要有效 |

最终全量结果：**1051 passed in 327.42s**，比基线新增 **97** 项测试。聊天、SSE、隐私 API、地址语义及结构化边界的最后一次定向回归为 **42 passed**。`git diff --check` 通过，Python 源码编译检查通过。

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.cache/pytest-privacy-complete
git diff --check
```

另做合成 Evidence 引擎检查：5 条记录中位耗时约 0.56 ms，200 条约 27.04 ms，输出均幂等；此测量仅反映本机环境，不作生产性能保证。

## 修改文件范围

新增 `src/netpilot/privacy/` 和上述测试、本文档。修改 Agent evidence/task/trace/session 边界、API schemas/presenters/routes/SSE、Snapshot validation/service/summary、Remediation note、History、Report、Escalation builder/privacy/models/persistence/exports、Settings、observability、工具异常/URL 验证以及 `web/index.html`、`web/app.js`、`web/style.css`、`.env.example`。

未添加数据库批量迁移、外部服务、DLP、KMS 或账号删除流程。

具体文件清单（路径相对仓库根目录）：

| 类型 | 文件 |
| --- | --- |
| 新增 privacy 核心 | `src/netpilot/privacy/__init__.py`, `models.py`, `policy.py`, `detectors.py`, `redactor.py`, `url.py`, `ip.py`, `metadata.py`, `logging.py`, `middleware.py` |
| 新增测试 | `tests/privacy_helpers.py`, `test_privacy_policy.py`, `test_privacy_structured.py`, `test_privacy_text.py`, `test_privacy_url.py`, `test_privacy_ip.py`, `test_privacy_snapshot.py`, `test_privacy_evidence.py`, `test_privacy_history.py`, `test_privacy_export.py`, `test_privacy_logging.py`, `test_privacy_api.py` |
| Agent | `src/netpilot/agent/task_state.py`, `reasoning_trace.py`, `session.py` |
| API | `src/netpilot/api/routes.py`, `presenters.py`, `sse.py`, `client_snapshot_routes.py`, `src/netpilot/models/schemas.py`, `src/netpilot/main.py` |
| Snapshot | `src/netpilot/client_snapshot/schemas.py`, `service.py`, `validation.py` |
| 持久化及报告 | `src/netpilot/history.py`, `src/netpilot/reports.py`, `src/netpilot/remediation/models.py` |
| Escalation | `src/netpilot/escalation/models.py`, `privacy.py`, `builder.py`, `persistence.py`, `exports.py` |
| 配置、日志、工具 | `.env.example`, `src/netpilot/config.py`, `src/netpilot/observability.py`, `src/netpilot/tools/base.py`, `validation.py` |
| Web | `web/index.html`, `web/app.js`, `web/style.css` |
| 更新旧测试预期 | `tests/test_diagnosis_reports.py`, `tests/test_verification_models.py` |
| 实现及验收文档 | `docs/MILESTONE12H_PRIVACY_REDACTION.md` |
