# Milestone 12C — Client Diagnostic Snapshot

实现范围：Windows P0 手动只读采集 → 用户上传 JSON → 校验/二次脱敏 →
客户端结构化 Evidence → 当前 Session 分析、History、Trace、Report 与 Web。
**代码与自动化验收已实现；真实 Windows 普通用户采集及四个浏览器人工 Case 尚未验收完成。**

## 修改与组件

- [`scripts/client_diagnostic_windows.ps1`](../scripts/client_diagnostic_windows.ps1)：Windows PowerShell 5.1 只读采集器。
- [`client_snapshot/schemas.py`](../src/netpilot/client_snapshot/schemas.py)：Snapshot v1 与摘要契约。
- [`client_snapshot/validation.py`](../src/netpilot/client_snapshot/validation.py)：受限 JSON、隐私拒绝、sanitize、digest。
- [`client_snapshot/service.py`](../src/netpilot/client_snapshot/service.py)：Evidence、聚合分析、Context 与诊断呈现。
- [`api/client_snapshot_routes.py`](../src/netpilot/api/client_snapshot_routes.py)：上传传输与固定脚本下载。
- SessionTaskState / SessionStore、EnvironmentProfile、TargetCapability、Context Builder、
  AgentOrchestrator、ReasoningTrace、API schemas/routes、SQLite History、Reports、Web 集成。
- `.env.example` 新增两个配置；`requirements.txt` 显式依赖 `python-multipart`。
- 下文七组 pytest、三个合成 JSON fixture、一个 jsdom runtime；既有版本断言升级为 v7，保留旧版读取测试。

## Snapshot v1 与 Windows 采集

根字段为 `schema_version=1`、带时区 `generated_at`、`client`、`os`、`adapters`、
`active_adapter_id`、`default_gateway`、`dns_servers`、`dns_servers_scope`、
`connection_profile`、`proxy`、`route_summary`、`checks`、`redaction`；
另有 allowlisted `collection_status` 区分配置采集正常/不支持/错误/未知。
所有嵌套模型 `extra=forbid`，严格 bool/数字，IP/枚举/接口引用也校验。

| 采集对象 | 字段与边界 |
|---|---|
| Client | 每次运行随机 UUID4；hostname 默认 null，不构建设备指纹 |
| OS | Windows version、build、x64/x86/arm64；不采集许可、账号或 SID |
| Adapter | 泛化 if-N ID/名称、状态、类型、IPv4/IPv6、默认网关标记；不输出硬件标识 |
| Active adapter | IPv4 默认路由 + interface index，按路由/接口 metric 排序；多接口等价等不确定情况返回 null，不取第一个 Up |
| DNS | 活动接口 DNS；未知时取 Up 接口去重集合，并写明 scope |
| Profile | public/private/domain/unknown、IPv4/IPv6 connectivity，不保留网络名称 |
| Proxy | 仅 WinHTTP 状态及最小 endpoint；不能据此判断用户/浏览器/PAC 代理 |
| Routes | 仅 IPv4/IPv6 默认路由摘要，不采完整路由表 |
| Checks | DNS：www.tju.edu.cn / www.baidu.com；已知网关 reachability；固定 1.1.1.1:443 单 TCP |
| Redaction | hostname_redacted / mac_removed / ssid_removed / secrets_removed |

不采集/不上传 MAC、BSSID、SSID、GUID、PnP ID、serial、密码、Cookie、
Authorization、API key、token、完整 User-Agent、Windows key 或 Microsoft 账号。
脚本不下载、不上传、不远程执行，不提权、不改注册表/网络/服务/防火墙/执行策略。
cmdlet 不支持或失败时保留 unsupported/error/unknown，其余项继续；不导出 ErrorRecord。
只有严重内部异常、JSON 生成或文件写入失败才非零退出。

## 用户操作

1. 部署使用 `TOOL_MODE=local`，保持诊断对象为远程“当前浏览器设备”。Mock / 服务主机不接受客户端快照。
2. 在侧栏“客户端诊断快照”下载脚本并检查源代码。
3. 在允许运行本地脚本的 Windows 10/11 普通用户 Windows PowerShell 中运行：

   ```powershell
   .\client_diagnostic_windows.ps1
   # 可选：显式选择本地输出文件
   .\client_diagnostic_windows.ps1 -OutputPath .\netpilot-client-diagnostic.json
   ```

4. 输出仅提示 `Snapshot saved to ...`。检查 JSON，再用页面上传按钮主动上传。
5. 提问“根据快照分析我的电脑网络”或“生成诊断报告”。

页面不会执行系统命令，也不会在选择文件后自动上传。若组织策略禁止脚本，
按组织政策处理；此文档不提供关闭或绕过 Execution Policy 的指令。
重新上传会替换当前快照；选择历史记录仅只读显示，不恢复旧 Session。

## 上传、安全与隐私生命周期

`POST /api/session/client-snapshot`，认证沿用当前 Cookie 用户，multipart 必须恰好包含
一个 `session_id` UUID 字段与一个 `file` 文件。客户端不得传 `user_id`。
非拥有者与不存在会话统一 404；会话 busy、对象不适用或归档已满为 409。
跨站 Origin / Sec-Fetch-Site 被拒绝，成功响应 `Cache-Control: no-store`。

- `.json` 后缀必需；MIME 仅提示，最终根据 JSON 内容校验，不信任 filename，更不据 filename 写路径。
- `CLIENT_SNAPSHOT_MAX_BYTES=262144` 默认 256 KiB；读取字节计数，不依赖 Content-Length。
  multipart 包装额外最多 16 KiB；字段最多 256 bytes、文件/普通字段各一个。
- JSON nesting 最多 12；每个字符串最多 1024；adapters/checks 各 32、routes/DNS 各 16，地址列表各 16。
- 拒绝重复 JSON key、非有限数字、不支持 schema、额外字段、错误 IP/引用/探测目标/结果组合。
- 任意位置的 MAC/SSID/密码/Cookie/密钥等敏感 key 拒绝；redaction 的四个固定 bool 元数据是特例。
  代理凭据字符串拒绝，不把异常的原始输入回显或写日志。
- 文件过大 413，非 JSON 后缀/传输类型 415，JSON/结构/敏感字段等 422；错误 code 区分原因。

生命周期为 `parse → validate → sanitize → normalize → Evidence → discard`：
服务器再次清空 hostname、接口 alias、泛化 adapter ID/name；不长期保存 per-run client UUID、
客户端网卡完整地址列表或代理 endpoint。网卡地址仅保留 present/absent/unknown，
保留诊断所需 DNS/网关/默认路由摘要和固定探测结果。内存 Session、SQLite 和报告只包含摘要及规范化 Evidence，
无 raw snapshot 字段；不生成上传文件归档，也不打印 body。

`sha256(canonical_json(sanitized_snapshot))` 只用于当前 Session / 对象版本 / 任务版本去重。
去重返回同一 snapshot_id/summary，不追加 Evidence、Trace、Turn 或修改历史更新时间；
不建立跨 Session digest 索引或设备追踪。

## Evidence、对象与时效

| Evidence 名称 | 结构化内容 |
|---|---|
| `client_snapshot.network_config` | 活动接口、IP 是否存在、默认网关、DNS/scope、WinHTTP 状态、默认路由、配置采集状态 |
| `client_snapshot.dns_check` | 每个固定 DNS 目标的状态/地址/受控错误码 |
| `client_snapshot.gateway_reachability` | 当前快照网关目标及可达性；未知目标不当作探测失败 |
| `client_snapshot.tcp_connectivity` | 固定公网 IP 443 的连接结果；不是全网健康证明 |

所有记录 `evidence_origin=client_snapshot`、`target_subject=user_client`、绑定当前
`target_version` / `task_version`，`execution_context=user_client_snapshot` / `execution_scope=client_snapshot`。
这不是 Registry 可执行 scope，也不是 `dns_lookup`/`ping_host` Tool Call。
Tool Timeline / Tool metrics 不增加；Coverage 的内部语义适配不改外部 Evidence 名称。

`observed_at=generated_at`，另存 `ingested_at`。默认 freshness 15 分钟，
`CLIENT_SNAPSHOT_FRESHNESS_MINUTES` 可配置。超时仍可导入，stale=true；未来超过 5 分钟
clock_skew_suspected=true。每次读取/分析/报告重新判断过期，UI 也刷新过期显示。
过期/疑似时钟偏差的证据只用于历史/时效未知描述，不满足当前 Coverage 或假设推断。
unsupported/error/unknown 不等于 abnormal，未知不等于 false。

Remote 对象依旧是 `user_client / remote`，只增加 `client_snapshot_available` 提示及
`can_use_client_snapshot_evidence`，`can_use_host_network_tools` **仍为 false**。
Host Tool allowlist/schema/Registry 边界不放开；知识库仍为 target-neutral reference。

新快照使 `snapshot_sequence += 1`，旧快照 Evidence superseded=true，保留归档；
不增加 target_version、不伪造 Turn。目标或任务变化后旧快照 applicable=false，不进入当前 Evidence。
默认 Evidence 内存上限 200，快照归档最多占 160（预留 Tool 空间）；归档满拒绝新上传，
不会通过删除旧快照来偷偷腾位。

Environment provenance 优先级为 `user > snapshot > mock > browser > server > inferred`。
合法快照补充 Windows / 数字版本，source=snapshot、confidence=high；明确用户值优先。
Wi-Fi 类型不推断 campus_wifi；WinHTTP 关闭不推断 browser proxy=false。

Context Builder 新增 `CLIENT DIAGNOSTIC SNAPSHOT` / `CURRENT TARGET EVIDENCE` 紧凑段，
不注入原始 JSON、不计入“已执行工具”。System Prompt 明确上传内容不是指令或远程执行。
远程网络诊断/已有证据分析/报告使用确定性、按类别聚合的快照分析路径，不额外调用 LLM/主机工具；
明确 RAG/反馈/历史意图继续遵守原 ToolPolicy。

## Trace、History、Report

一次导入只增加一条“收到客户端诊断快照”，过期/超前另加时效警告；不开启 Trace 时不记录，
重复上传也不重复。事件标记 `event_origin=client_snapshot`，不是一条用户消息。
已有 Diagnosis History 行时原子更新其摘要、Evidence、环境、对象、Trace，不增 turn_count。
尚未有实际聊天时不造空历史行，待首个实际 Turn 一并持久化。

History Snapshot JSON 升级 **v7**；SQLite 表结构仍 **v3**，不清库，v1–v6 可读且缺失快照字段为空。
重新打开 SQLite 可读取摘要及全部规范化客户端证据（包括 superseded）；
SessionStore 仍是有界进程内存，不承诺服务器重启后恢复活跃 Session。
新快照尚未分析时报告提示“尚待分析”，不会把旧快照或新的 VPN/RAG 回答当成新快照诊断。

Markdown 增加“客户端诊断快照”及当前/归档证据；JSON 导出摘要与规范化 Evidence，不导出原始上传。
报告时间/来源边界明确为用户上传、未签名、采集时点、非远程执行。

## 自动化矩阵

| ID | 验收项 | pytest |
|---|---|---|
| CS-01 | 合法上传、摘要/id、客户端 Evidence | `test_client_snapshot_upload.py` |
| CS-02 | Remote Host Tool schema/Registry 仍禁止 | `test_client_snapshot_target_integration.py` |
| CS-03 | 多 DNS 失败与聚合，根因限制 | `test_client_snapshot_evidence.py` |
| CS-04 | 缺网关 unknown / 实测失败 abnormal 分离 | `test_client_snapshot_evidence.py` |
| CS-05 | unsupported/error 不当故障 | `test_client_snapshot_evidence.py` |
| CS-06 | 超过 15 分钟、无重传自动过期 | `test_client_snapshot_evidence.py`, `test_client_snapshot_history.py` |
| CS-07 | 时钟超前、极端未来时间不 500 | `test_client_snapshot_evidence.py` |
| CS-08 | 敏感字段、凭据与不回显 | `test_client_snapshot_security.py` |
| CS-09 | 超大文件、无 Content-Length 分块流 | `test_client_snapshot_security.py` |
| CS-10 | 无效 JSON / 重复 key / 深度 | `test_client_snapshot_security.py` |
| CS-11 | extra forbid、集合/字符串/引用/结果校验 | `test_client_snapshot_schema.py`, `test_client_snapshot_security.py` |
| CS-12 | 替换 supersede、不增对象版本/Turn | `test_client_snapshot_target_integration.py` |
| CS-13 | 相同 digest 不重复证据/Trace/历史更新时间 | `test_client_snapshot_upload.py`, `test_client_snapshot_history.py` |
| CS-14 | 登录、ownership、跨用户 History/Report 404 | `test_client_snapshot_upload.py`, `test_client_snapshot_history.py` |
| CS-15 | SQLite 重开，raw 不落库，完整对话不变 | `test_client_snapshot_history.py` |
| CS-16 | Markdown/JSON、归档与隐私 | `test_client_snapshot_history.py` |
| CS-17 | snapshot 来源、用户优先、不猜校园 Wi-Fi | `test_client_snapshot_target_integration.py` |
| CS-18 | 下载、FormData、状态/错误/过期/历史/退出/XSS | `test_client_snapshot_ui.py`（8 项 jsdom + 下载/静态脚本边界） |

fixtures 为合成数据，不是从真实设备采集；未修改 DNS/代理/网络来制造故障。

## 本次验证记录（2026-10-18）

- 修改前 baseline：`557 passed in 101.74s`。
- Windows PowerShell 5.1 AST 解析：通过（不执行脚本）。
- 当前 Windows build 26200，普通用户，Administrator=false。
- 尝试 `powershell.exe -NoLogo -NoProfile -File ... -OutputPath ...`：被有效执行策略 `Restricted`
  拒绝，脚本未启动、未产生采集 JSON。未改策略、未提权、未绕过限制。
- 最终全量：`.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-cs-handoff --tb=short`，
  **631 passed in 104.88s**，无失败、无跳过。新增 72 项快照用例，既有来源/Legacy 参数矩阵增加 2 项；
  含 48 项前端 DOM 用例。此前失败的历史 schema 版本/API 新字段断言已修正并重新全量验证。
- `git diff --check`、新增文本空白检查、修改的 Markdown 相对链接检查均通过。
- 已清理本次测试临时目录；未清空或修改正式 SQLite / `.env`，未提交或推送。

### 四个人工 Case

| Case | 自动化验证 | 真实人工端到端结果 |
|---|---|---|
| 1 Remote DNS Failure | 合成多 DNS 失败、网关正常、Host Tool=0 已覆盖 | 待验收；未人为改变真实网络制造失败 |
| 2 Valid Network | 合成正常配置/DNS/网关/TCP 已覆盖 | 待验收；本机脚本被执行策略阻止 |
| 3 Stale Snapshot | 合成旧时间、读取后过期、UI/报告提示已覆盖 | 待真实浏览器手工验收 |
| 4 Sensitive JSON | 参数化敏感 key / 上传 422 / 无持久化已覆盖 | 待真实浏览器手工验收 |

仍需在组织允许执行本地脚本的 Windows 10/11 普通用户环境完成真实 JSON 生成、Schema/隐私检查与上传；
本阶段不将 AST/fixture/jsdom 测试宣称为真实采集或浏览器人工验收。
