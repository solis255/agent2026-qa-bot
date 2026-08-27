# Milestone 6 手动测试样例

## 测试准备

在项目根目录启动开发演示服务：

```powershell
$env:SCENARIO_SWITCH_ENABLED="true"
.\.venv\Scripts\python.exe -m uvicorn netpilot.main:app --host 127.0.0.1 --port 8001
```

打开 `http://127.0.0.1:8001/`。确认页头显示“后端服务正常”，服务概览显示 `MOCK 模式`、`TJU LLM 已配置`；知识库测试还要求 `知识库 已就绪`。

模型的措辞可能变化，验收时以右侧结构化时间线、状态和来源字段为准，不要求最终文字逐字一致。切换 Mock 场景会清理旧会话并自动创建新会话。

## 样例 1：DNS 故障

- 场景：`DNS 故障`
- 输入：

  > 我可以访问公网 IP，但打不开 github.com。请至少使用 ping_host 检查 1.1.1.1，并使用 dns_lookup 检查 github.com，最后根据证据简洁给出诊断。

- 预期：时间线包含 `Ping 可达性 / 正常` 和 `DNS 解析 / 发现异常`；DNS 数据为 `resolved: false`；结论指向 DNS 环节，不把否定结果误报成工具执行失败。

## 样例 2：默认网关不可达

- 场景：`网关不可达`
- 输入：

  > 我已连接 Wi-Fi 但完全不能上网。请先调用 get_network_info 查看默认网关，再用 ping_host 检查 192.168.1.1，并给出下一步建议。

- 预期：网络配置工具正常返回默认网关；Ping 显示 `发现异常`、`reachable: false`；建议优先检查本地接入、Wi-Fi 或网关，而不是先判断 DNS。

## 样例 3：SSH 端口受阻

- 场景：`SSH 端口受阻`
- 输入：

  > 网页可以打开，但 SSH 连接 ssh.example.com 的 22 端口失败。请使用 tcp_check 检查该主机的 22 端口，并依据结果判断。

- 预期：时间线包含 `TCP 端口 / 发现异常`；数据中 `connected: false`，并保留安全的 `failure_reason`；结论不把端口失败扩大为“整个网络断开”。

## 样例 4：HTTP 访问失败

- 场景：`HTTP 访问失败`
- 输入：

  > DNS 和 Ping 看起来正常，但 https://example.com 打不开。请分别检查 DNS、TCP 443 和 HTTP 访问，最后指出故障更接近哪一层。

- 预期：DNS、Ping/TCP 证据正常，`HTTP 访问 / 发现异常`；页面展开项显示结构化 HTTP 失败原因；最终判断更接近 HTTP/TLS/应用层。

## 样例 5：部分连通

- 场景：`部分连通`
- 输入：

  > 网络时好时坏。请用 ping_host 检查 1.1.1.1，再用 traceroute 检查 example.com，说明是否存在丢包或目的地不可达。

- 预期：至少一项证据为异常；页面同时显示工具耗时、轮次、调用 ID 和可展开数据；Agent 不无限重复同一工具与参数。

## 样例 6：VPN 知识库与来源

- 操作：点击 `新建会话`；Mock 网络场景不限。
- 输入：

  > 天津大学 VPN 怎么使用？请先调用 knowledge_search，只依据知识库回答，并标出资料类型、标题和原始 URL。

- 预期：时间线包含 `知识检索 / 参考资料`；来源区至少展示 `community`、标题、相关度、文件、chunk ID 和可点击的 `https://wiki.tjubot.cn/e-life/vpn`；回答明确社区资料不等于官方现行规定。

## 样例 7：同一会话追问

- 前置：完成样例 6，不点击“新建会话”。
- 输入：

  > 如果我现在就在校园网内，还需要使用它吗？只根据刚才的资料回答。

- 预期：页面保持相同会话 ID；回答能理解“它”指 VPN，并基于上一轮资料回答。历史只保存在服务端内存中，不应出现在浏览器 `localStorage` 或 `sessionStorage`。

## 样例 8：新会话隔离

- 操作：记录当前会话 ID，点击 `新建会话`。
- 预期：会话 ID 改变；聊天区、诊断结论、工具时间线和来源区恢复初始状态。输入“我刚才问了什么？”时，新会话不应知道上一会话内容。

## 样例 9：场景切换保护

不设置 `SCENARIO_SWITCH_ENABLED` 重新启动服务：

```powershell
Remove-Item Env:SCENARIO_SWITCH_ENABLED -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m uvicorn netpilot.main:app --host 127.0.0.1 --port 8001
```

- 预期：场景下拉框禁用；直接请求 `POST /api/scenarios/dns_failure` 返回 HTTP 403。
- 将 `TOOL_MODE=local` 后，场景接口不允许切换 Mock 数据；页面仍可使用只读 Local 工具。

## 整体验收清单

- 所有输入和模型回答都作为纯文本渲染，不执行其中的 HTML。
- 页面在手机宽度下变为单列，不出现横向页面溢出。
- 浏览器网络请求中没有 `TJU_API_KEY`；Key 只存在于服务端 `.env`。
- 连续提交期间按钮显示“诊断中”并禁用，完成后恢复。
- 右侧结论摘要、时间线和来源与当前最后一次回答一致。
