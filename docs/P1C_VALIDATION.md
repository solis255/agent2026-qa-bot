# P1-C 真正的自定义 Mock 测试场景验收说明

## 启用与生命周期

自定义场景沿用已有 Mock 场景安全开关：

```text
TOOL_MODE=mock
SCENARIO_SWITCH_ENABLED=true
CUSTOM_SCENARIO_MAX_COUNT=20
```

场景定义保存在服务进程内存中，重启服务后自动清空，不需要数据库或新增依赖。`CUSTOM_SCENARIO_MAX_COUNT` 可配置范围为 1～100，默认最多 20 个。

该功能用于可重复的测试和演示，不表示真实网络状态。切换任意场景都会清空旧会话；删除正在使用的自定义场景会原子回退到内置 `healthy` 场景、清空旧会话并返回新会话 ID。

## API

创建并查看自定义场景：

```http
POST /api/scenarios/custom
Content-Type: application/json

{
  "name": "dns_lab",
  "label": "宿舍 DNS 故障",
  "description": "公网 Ping 正常，但域名解析和后续连接失败。",
  "behavior": {
    "network_configured": true,
    "ping_reachable": true,
    "ping_packet_loss_percent": 0,
    "dns_resolved": false,
    "tcp_connected": false,
    "http_reachable": false,
    "http_status_code": null,
    "traceroute_reached": true
  }
}
```

```text
GET    /api/scenarios
POST   /api/scenarios/dns_lab
DELETE /api/scenarios/custom/dns_lab
```

场景名称只允许 3～32 位小写字母、数字、下划线和连字符，并且必须以字母开头。显示名称最多 40 字，说明最多 200 字。未知字段、控制字符、不一致的 Ping/HTTP 组合和无效数值返回 `422`；重名、覆盖内置名称或达到容量上限返回 `409`。

## 已完成能力

- 创建、列表、切换和删除运行时自定义场景；
- Web 表单支持网络配置、Ping/丢包、DNS、TCP、HTTP/状态码、traceroute 六类独立结果；
- 创建成功后自动切换并显示“自定义”标识；
- 内置六场景继续可用且不能被覆盖或删除；
- 所有定义通过不可变、`extra=forbid` 的 Pydantic schema；
- Mock Provider 仅合成现有 Tool 数据模型，不解释脚本、命令或任意 JSON 返回体；
- 自定义场景执行期间不调用 socket、subprocess 或 HTTP Client；
- 创建、删除和切换与 Agent 运行共享同一运行时锁，避免一次诊断混用两个场景；
- 场景数量有界，Local 模式和关闭切换开关时拒绝写操作；
- 页面使用 `textContent` 渲染用户场景文本，不使用 `innerHTML` 或浏览器持久化存储。

## 自动验收

在仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

本次实现验收结果：`207 passed`。

只运行 P1-C 专项测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_custom_scenarios.py tests\test_scenario_api.py tests\test_mock_scenarios.py tests\test_web_demo.py -q
```

专项测试覆盖严格输入关系、未知字段、六工具结果、零外部 I/O、内置保护、容量上限、重复名称、创建/列表/切换/删除、活动场景回退、旧会话失效、Local 模式和功能开关。

## 浏览器手动验收

启动开发模式：

```powershell
$env:TOOL_MODE="mock"
$env:SCENARIO_SWITCH_ENABLED="true"
.\.venv\Scripts\python.exe -m uvicorn netpilot.main:app --host 127.0.0.1 --port 8001
```

打开 `http://127.0.0.1:8001/`：

1. “Mock 故障场景”下方显示自定义容量和“新建自定义场景”。
2. 创建 `dns_lab`，取消 DNS、TCP 和 HTTP 成功开关，HTTP 状态码自动清空。
3. 提交后选择器显示“自定义 · …”，页面提示旧会话已清理。
4. 使用对应问题诊断，Tool Timeline 中的结果应与表单设置一致。
5. 点击“删除当前场景”，选择器回到“网络正常”，旧会话再次失效。
6. 重启服务后，自定义场景不再存在；六个内置场景不受影响。

若需要跨重启保存或多人共享场景，应在后续需求中单独设计持久化、权限和审计，不应复用诊断历史表隐式保存。
