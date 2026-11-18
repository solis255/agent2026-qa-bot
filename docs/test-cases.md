# TJU NetPilot 测试与验收

从仓库根目录运行，安装方法见 [README](../README.md)。Python 回归使用模拟模型、Mock Provider 或受控替身。离线演示 Runner 使用临时 SQLite，自动走登录、聊天、快照、修复反馈、复核、历史和导出接口。

## 自动检查

```bash
npm ci --prefix web --ignore-scripts
python -m pytest -q
npm test --prefix web
python scripts/run_demo_scenarios.py
git diff --check
```

前端检查需要 Node.js 22.13+（22.x）或 24+。先安装 `web/` 测试依赖，再运行 Python 全量测试，以启用其中调用 Node.js 的 DOM 测试。

| 测试主题 | 检查点 | 测试入口 |
| --- | --- | --- |
| 只读工具与 Agent | 参数校验、调用轮次、诊断覆盖与证据去重、Mock 和 Local 输出契约 | [工具测试](../tests/test_tools.py)、[Agent 测试](../tests/test_agent_orchestrator.py) |
| 诊断对象与上下文 | 必要时澄清、对象切换后证据失效、远程对象限制服务主机工具 | [环境采集](../tests/test_context_acquisition.py)、[对象策略](../tests/test_target_tool_policy.py) |
| 客户端检查 | 向导、授权上传、隐私校验、重复或过期结果、回执续接 | [客户端检查流程](../tests/test_client_check_flow.py)、[快照上传](../tests/test_client_snapshot_upload.py) |
| 修复与闭环 | 手动步骤、前后证据范围、结果比较、恢复与升级条件 | [计划 API](../tests/test_remediation_api.py)、[验证 API](../tests/test_verification_api.py)、[处理状态 API](../tests/test_resolution_api.py) |
| 校园知识与限流 | 本地检索、行内引用、限流重试、带来源片段降级 | [知识整理](../tests/test_knowledge_finalization.py)、[429 API](../tests/test_knowledge_429_api.py)、[客户端重试](../tests/test_tju_429_retries.py) |
| 账号、历史与隐私 | 所有权、分页和持久化、脱敏、安全 Markdown、报修导出 | [所有权](../tests/test_auth_ownership.py)、[诊断历史](../tests/test_diagnosis_history.py)、[隐私导出](../tests/test_privacy_export.py)、[报修 API](../tests/test_escalation_api.py) |
| Web 与传输 | 学生端、历史回放、引用交互、SSE 事件顺序及会话释放 | [学生端](../tests/test_student_ui.py)、[SSE](../tests/test_chat_stream.py)、[前端命令](../web/package.json) |
| 演示场景 | DNS 恢复、两轮无改善后升级、VPN 状态对照、单服务异常和复发 | [Demo Runner](../scripts/run_demo_scenarios.py) |

## 浏览器和现场检查

| 场景 | 验收要点 |
| --- | --- |
| DNS 恢复和两轮无改善 | 按 [演示手册](DEMO_SCENARIOS.md) 核对 Before / After、处理状态及导出中的模拟数据标识。 |
| Windows 客户端检查 | 在实际故障电脑上按向导采集并上传。核对采集时点、证据来源和过期提示。 |
| 局域网与个人历史 | 按 [局域网指南](lan-demo.md) 用两个设备和两个账号核对连通性、登录、历史与报告。 |
| 校园知识与模型 | 配置私有 Key 和本地知识索引，分别运行下方在线检查，核对回答与来源类型。 |
| 桌面和移动布局 | 检查对话输入、诊断详情、操作按钮及历史回看。现有界面示例见 [截图目录](../screenshots/README.md)。 |

在线检查会调用配置的 TJU 模型服务。

```bash
python scripts/test_tju_api.py
python scripts/test_netpilot_agent.py
python scripts/test_netpilot_rag.py
```

`/api/health` 用于查看组件是否配置和就绪，在线脚本用于确认真实模型调用。出现 429 或凭据异常时见 [TJU 模型排查](tju-llm-troubleshooting.md)。
