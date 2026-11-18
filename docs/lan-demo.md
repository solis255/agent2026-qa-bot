# 局域网演示与跨设备检查

部署 NetPilot 的电脑和访问它的设备需要互相可达。直连 HTTP 只用于可信、受控的局域网，使用演示专用账号和密码。登录认证与诊断历史共用 SQLite，演示实例可使用独立数据库。主机防火墙应将演示端口的访问限制在授权网段内。

## 配置和启动

按 [README](../README.md) 安装并填写私有 `.env`。下面是直连 HTTP 的 Mock 实例配置。`APP_HOST` 填写运行 NetPilot 的主机在可信网段的 IPv4 地址。

```dotenv
APP_HOST=192.168.1.10
APP_PORT=8000
AUTH_COOKIE_SECURE=false
DIAGNOSIS_HISTORY_ENABLED=true
DIAGNOSIS_DB_PATH=.cache/lan-demo.db
TOOL_MODE=mock
SCENARIO_SWITCH_ENABLED=true
RAG_ENABLED=true
DEBUG=false
```

现场可选两种路线。

- **普通 Mock 对话。** 配置模型 Key 和 SDK 基础地址，按需构建知识索引。`python scripts/check_lan_demo.py` 检查该路线的本地配置和索引文件。实际模型和跨设备可达性需另行验证。
- **无 Key 快照演示。** 设置 `DEMO_MODE=true`、`SCENARIO_SWITCH_ENABLED=false` 和 `RAG_ENABLED=false`，然后按照 [演示手册](DEMO_SCENARIOS.md) 操作。这条路线使用独立演示场景及快照。

```bash
python -m netpilot.main
```

此入口读取 `APP_HOST` 和 `APP_PORT`。使用 Uvicorn 命令启动时，显式传入 `--host` 和 `--port`。在另一台可信设备浏览器打开 `http://<服务主机可信私网地址>:8000/`，登录后从同一地址访问 `/api/health`。若无法访问，检查主机监听地址、端口和所处网段的隔离策略。使用 HTTPS 部署时开启 `AUTH_COOKIE_SECURE`，并按实际部署条件验证 Cookie 行为。

## 验证两台设备与两个账号

1. 用演示账号 A 运行一次诊断，确认“我的诊断历史”可显示该记录并导出报告。
2. 在另一台设备用演示账号 B 登录，确认个人历史只显示 B 的记录。越权请求应返回 404，相关回归见 [测试与验收](test-cases.md)。
3. 需要检查远程 Windows 设备时，另用 `TOOL_MODE=local` 实例，以“当前浏览器设备”为诊断对象，按“开始网络检查”的向导在故障 Windows 电脑上运行采集器、主动上传结果。诊断证据注明采集时点。选择“NetPilot 服务主机”时，Local 工具观察服务进程所在主机。

演示结束后退出测试账号并停止实例。数据库保留账号记录与诊断历史，按现场的数据保留要求处理。[截图目录](../screenshots/README.md) 说明了可用于展示的页面及数据来源。
