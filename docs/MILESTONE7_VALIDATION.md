# Milestone 7 验收说明

## 完成范围

Milestone 7 已实现并自动验证以下边界：

- Host、URL、端口、Tool JSON 与聊天消息使用严格 Pydantic 校验；
- HTTP(S) Scheme、localhost、metadata、私网/回环/链路本地地址和每次重定向均有 SSRF 防护；
- 系统命令固定参数列表、`shell=False`、超时与输出上限；HTTP 有总超时、响应头上限和重定向上限；
- Agent 工具轮次、相同目标调用、聊天历史、单条消息和内存会话总数有上限；
- `.env`、`*.key` 被 Git 忽略，API Key 使用 `SecretStr`，不返回浏览器、不进入审计日志；
- 日志包含 `request_id`、`session_id`、`tool_name`、`tool_duration`、`tool_success`、`llm_duration`、`http_status`、`error_type`；
- 诊断区分有效异常、工具执行错误、超时不确定、安全阻止和知识参考；
- Local 模式识别代理 `198.18.0.0/15` Fake-IP，明确说明 HTTP 请求尚未发送并给出代理/DNS 复测步骤；
- 普通公网连通性问题不会启用校园知识检索，校园 VPN/eduroam 使用说明仍可启用检索。

## 自动测试

在仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

本次验收结果：`184 passed`。测试完全离线，不依赖真实 TJU API 或现场网络状态。

关键专项测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_tool_security.py tests\test_milestone7.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_agent_orchestrator.py tests\test_sessions.py tests\test_chat_api.py -q
```

## Local 模式手动样例

在 `.env` 中设置 `TOOL_MODE=local`，然后使用未占用端口启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn netpilot.main:app --host 127.0.0.1 --port 8001
```

### 样例 1：代理关闭但仍残留 Fake-IP DNS

问题：

```text
我关闭了 VPN/代理，www.google.com 打不开。请检查 DNS、TCP 443 和 HTTPS，并根据证据给出可执行步骤。
```

如果 DNS 返回 `198.18.0.0/15`：

- HTTP 时间线应显示“安全阻止”，而不是“网站访问失败”；
- 证据中 `request_sent=false`，并保留 `resolved_addresses`；
- 结论应指出代理 Fake-IP/DNS 与流量接管不一致；
- 建议应包含退出残留代理 DNS、`ipconfig /flushdns`、`nslookup` 复查和重新检测 HTTPS；
- 不应调用 `knowledge_search`。

### 样例 2：Ping 工具自身超时

问题：

```text
请使用 ping_host 检查 1.1.1.1，并说明它是否可达。
```

如果系统工具超时，时间线应显示“结果不确定”，回答必须说明不能由工具超时推断目标不可达，不应声称 Ping 成功。

### 样例 3：校园资料意图

问题：

```text
天津大学 VPN 应该如何配置？请给出资料来源。
```

当本地 RAG 就绪时，可以调用 `knowledge_search`，并显示 community/official 等来源类型和原始 URL。资料只作参考，不作为当前连通性的检测证据。

## Mock 模式回归样例

设置 `TOOL_MODE=mock` 和 `SCENARIO_SWITCH_ENABLED=true`，在页面依次切换六种场景。确认：

- 页面可以新建会话并完成聊天；
- Tool Timeline 能区分正常、发现异常、执行失败、结果不确定、安全阻止和参考资料；
- DNS、网关、TCP、HTTP 等负面观察不会被描述为工具崩溃；
- 达到 Agent 最大工具轮次时安全停止并使用已有证据回答；
- 页面和网络响应不包含 `TJU_API_KEY`。

## 日志抽查

向任意 API 请求传入合法 `X-Request-ID`，响应应回传同一个值；未提供或格式非法时服务会生成 32 位 ID。日志应为单行 JSON，可按 `request_id` 关联 HTTP、Agent 与 Tool 事件。不要在日志中加入聊天原文、Tool 参数、Authorization Header 或任何 Secret。
