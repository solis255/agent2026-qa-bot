# TJU NetPilot 真实截图清单

本目录用于比赛材料中的真实运行截图。已收录用户提供的 `demo1` 和 `demo2` 两张原始浏览器截图；其余场景仍待采集。不得使用设计稿、生成图或空白占位图冒充运行结果。

应按 [`docs/MILESTONE9D_LAN_DEMO.md`](../docs/MILESTONE9D_LAN_DEMO.md) 配置好 `tju-llm`、启动当前提交对应版本并完成相应流程后，由人工从真实浏览器界面采集：

| 文件名 | 应展示的真实内容 |
|---|---|
| `00-login.png` | 未登录时的 TJU NetPilot 登录/注册入口；不得露出正在输入的密码 |
| `01-home.png` | TJU NetPilot 首页、服务状态和新会话初始界面 |
| `02-dns-diagnosis.png` | `dns_failure` Demo 的回答、诊断结论与 Tool Timeline |
| `03-ssh-diagnosis.png` | `tcp_ssh_blocked` Demo 的 TCP 22 证据与结论 |
| `04-rag-vpn.png` | VPN 知识问答、`knowledge_search` 和 community 来源 URL |
| [`05-history-report.png`](05-history-report.png) | `demo1` 的知识问答、个人诊断历史及报告预览/导出入口；画面显示 `community` 来源，但未打开报告预览 |
| [`06-multiuser-isolation.png`](06-multiuser-isolation.png) | `demo2` 登录后“我的诊断历史”为空，并显示当前用户标识；与 `05` 分别为真实截图，不拼接 |

目前 `00`–`04` 尚未采集。两张页面截图说明可见的账号与历史状态；服务端越权隔离由自动测试验证，截图本身不能证明跨设备 LAN 连通或端到端网络权限配置。

采集前检查：

- 页面与截图中不得出现 `TJU_API_KEY`、Authorization header、`.env` 内容或个人敏感信息；
- 截图不要包含密码输入、完整 Cookie Token、真实学号或浏览器开发者工具中的认证请求；
- Mock 截图应清楚显示为 Mock 场景，不能暗示为真实校园网检测；
- RAG 截图应保留真实 `source_type`，当前内置资料应显示 `community`；
- SSE 的逐块展示不能标注为模型 token streaming；
- 截图必须与当前仓库代码一致，不做改变诊断事实的后期合成。

后续截图补齐后，可在根 [`README.md`](../README.md) 顶部选择一张最能代表产品的真实截图进行引用；未采集的文件不要添加引用。
