# TJU NetPilot 演示手册

本手册通过可复现的模拟数据展示师生从报告问题到确认恢复或交接人工支持的完整过程。界面、历史与导出会标记 `DEMO / 模拟数据`。演示使用本地快照，支持在没有 TJU API Key、RAG 索引和现场故障的情况下运行。

## 启动演示

按 [README](../README.md) 安装并激活项目虚拟环境。另开一个 Windows PowerShell 窗口，在项目根目录启动独立演示实例。

```powershell
$env:DEMO_MODE = "true"
$env:TOOL_MODE = "mock"
$env:SCENARIO_SWITCH_ENABLED = "false"
$env:RAG_ENABLED = "false"
$env:DIAGNOSIS_HISTORY_ENABLED = "true"
$env:DIAGNOSIS_DB_PATH = ".cache/competition-demo.db"
python -m uvicorn netpilot.main:app --host 127.0.0.1 --port 8001
```

打开 [演示首页](http://127.0.0.1:8001/)，注册专用演示账号并登录。在“诊断详情 → 演示 / 开发 → 演示模式 · Demo / Mock”中选择场景，点击“创建 / 切换当前演示”。点击“填入推荐测试语句”后，返回聊天区手动发送；聊天、快照和步骤操作分别在对应区域完成。

## DNS 恢复

1. 选择“A · DNS 修复成功”，发送“我的微信能用，但网页打不开，帮我检查一下”。诊断对象应为当前浏览器设备（远程）。
2. 加载 Before 快照，再发送“请根据当前快照分析网页问题并给出低风险修复计划”。查看网关、DNS 解析和 TCP 443 的客户端证据。多域名解析失败提供 DNS 链路异常线索，证据仍有覆盖限制。
3. 在“处理过程”的修复计划中找到“重新连接原校园网络”，点击“已完成”以模拟用户操作。加载 After 1 快照，观察同一批 DNS 目标恢复、验证结果为 `improved`。
4. 在“处理状态”中确认原始症状已恢复，查看“问题已解决”。打开“我的诊断历史”查阅完整处理过程，按需导出报告。

[查看 DNS 恢复截图](../screenshots/demo-dns-recovery.jpg)

## 两轮无改善后转人工

1. 选择“B · DNS 多轮无改善”，重复发问题、加载 Before 和分析快照，生成或查看低风险计划。
2. 第 1 轮标记“保存内容后重新打开应用”完成，再加载 After 1，查看结果 `unchanged`。
3. 第 2 轮记录“重新连接原校园网络”和“保留现象并反馈维护者”两个步骤，然后加载 After 2。查看两轮有效复核均无改善，且安全步骤耗尽后的升级状态。
4. 点击“生成报修材料”，预览 Markdown 或导出 Markdown / JSON。核对当前对象、证据、尝试步骤、两轮复核和人工核查建议。材料由演示用户自行交接。

[查看报修材料截图](../screenshots/demo-escalation.jpg)

## 其他场景

| 场景 | 重点观察 |
| --- | --- |
| `vpn_proxy` / `vpn_unknown` | 已确认 VPN 开启时，临时断开的建议带有前置条件和回退步骤。状态未知时先核对环境。 |
| `single_service` | 基础连通性正常、影响局限于单个服务时，建议围绕该服务进行核对。 |
| `recurrence` | 先按 DNS 恢复流程完成验证和确认，再发送“刚才好了，现在又打不开了”，观察任务推进到新版本，历史仍保留上一次处理结果。 |

需要重放时用“重置当前演示”，再按顺序加载 Before、After。重置创建新会话，之前的记录仍可在个人历史中查看。需要展示另一台 Windows 电脑的真实采集时，使用 [局域网使用指南](lan-demo.md)。

## 自动复现

```bash
python scripts/run_demo_scenarios.py
python scripts/run_demo_scenarios.py --scenario dns_escalation
```

Runner 使用临时账号和 SQLite，通过正式 API 检查六条路线，并校验状态、报告标识和报修导出脱敏。每条路线输出 `PASS` 或 `FAIL`，断言失败时进程返回非零状态。完整回归范围见 [测试与验收](test-cases.md)。
