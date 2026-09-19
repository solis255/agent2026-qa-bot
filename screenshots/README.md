# TJU NetPilot 真实截图清单

本目录用于比赛材料中的真实运行截图。当前仓库未提交这些 PNG；不得使用设计稿、生成图或空白占位图冒充运行结果。

应在配置好 `tju-llm`、启动当前提交对应版本并完成相应流程后，由人工从真实浏览器界面采集：

| 文件名 | 应展示的真实内容 |
|---|---|
| `01-home.png` | TJU NetPilot 首页、服务状态和新会话初始界面 |
| `02-dns-diagnosis.png` | `dns_failure` Demo 的回答、诊断结论与 Tool Timeline |
| `03-ssh-diagnosis.png` | `tcp_ssh_blocked` Demo 的 TCP 22 证据与结论 |
| `04-rag-vpn.png` | VPN 知识问答、`knowledge_search` 和 community 来源 URL |
| `05-history-report.png` | 诊断历史、记录恢复或故障报告预览/导出入口 |

采集前检查：

- 页面与截图中不得出现 `TJU_API_KEY`、Authorization header、`.env` 内容或个人敏感信息；
- Mock 截图应清楚显示为 Mock 场景，不能暗示为真实校园网检测；
- RAG 截图应保留真实 `source_type`，当前内置资料应显示 `community`；
- SSE 的逐块展示不能标注为模型 token streaming；
- 截图必须与当前仓库代码一致，不做改变诊断事实的后期合成。

截图补齐后，可在根 [`README.md`](../README.md) 顶部选择一张最能代表产品的真实截图进行引用；在 PNG 实际存在前不要添加该引用。
