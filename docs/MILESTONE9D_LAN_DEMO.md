# Milestone 9D：可信 LAN 比赛演示手册

本手册用于 **TJU NetPilot — 天津大学校园网络智能诊断与服务 Agent** 的单机、同源 Web/API 比赛演示，不是正式校园服务部署方案。正式代码位于 [`src/netpilot/`](../src/netpilot/)；9A–9C 的认证、资源所有权和 Web 流程分别见 [`MILESTONE9A_VALIDATION.md`](MILESTONE9A_VALIDATION.md)、[`MILESTONE9B_VALIDATION.md`](MILESTONE9B_VALIDATION.md)、[`MILESTONE9C_VALIDATION.md`](MILESTONE9C_VALIDATION.md)。

## 1. 演示前安全边界

- **直连 HTTP 不加密密码或 Cookie 传输。** 只在可信、受控的 LAN 中使用专门创建、演示后不复用的测试账号和非敏感密码。不得输入天津大学统一身份认证密码、真实邮箱密码、学号或其他复用凭据；不接入学校认证系统。
- `APP_HOST=0.0.0.0` 会监听所有网络接口。仅在确认主机防火墙把 8000 端口限制到可信演示网段、且没有公网端口映射或不可信访客网络后启用。无法确认时保持默认 `127.0.0.1`，仅本机演示。
- 演示使用 `TOOL_MODE=mock`。Mock 结果是离线模拟，不代表真实校园网络。`TOOL_MODE=local` 只检测运行 NetPilot 的电脑，不检测远端浏览器设备。
- 后端持有 `TJU_API_KEY`，只放在被 Git 忽略的私有 `.env`/环境变量中，不复制到页面、截图、聊天正文或仓库。Mock 网络 Tool 离线，但真实 `tju-llm` 聊天仍需可用的模型接口。
- SQLite 文件同时保存账号哈希、服务端 Auth Session 摘要与诊断历史。限制本机文件访问权限；演示后按持有者决定备份/清理，不把数据库文件当作公开比赛材料。

## 2. 配置

先按根 [`README.md`](../README.md) 安装并创建私有 `.env`。直接 HTTP LAN 演示建议在 `.env` 中明确设置：

```env
AUTH_ENABLED=true
AUTH_COOKIE_NAME=netpilot_session
AUTH_COOKIE_SECURE=false
AUTH_SESSION_HOURS=12
AUTH_MAX_ACTIVE_SESSIONS_PER_USER=5
TOOL_MODE=mock
SCENARIO_SWITCH_ENABLED=true
DIAGNOSIS_HISTORY_ENABLED=true
RAG_ENABLED=true
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=false
```

另外填写比赛专用 `TJU_API_KEY` 与平台分配的 `TJU_API_BASE`，但不要把值写进文档、日志或截图。`AUTH_ENABLED` 只能为 `true`：设为 `false` 会拒绝启动，而非关闭鉴权。Cookie 使用 `HttpOnly`、`SameSite=Lax`、`Path=/` 和有界 `Max-Age`；直接 HTTP 才设置 `AUTH_COOKIE_SECURE=false`，未来 HTTPS 部署必须改为 `true`。不要同时开放跨域凭据访问。

如需 VPN/RAG 演示，先运行 `python scripts/build_knowledge_index.py`，然后确认健康检查中的 `rag_ready=true`。当前种子来源类型为 `community`，不是学校官方实时通知。

运行只读预检：

```bash
python scripts/check_lan_demo.py
```

预检只检查本地配置和 RAG 文件是否存在，不连接模型、不打开端口、不修改防火墙，也不打印密钥。全部 `OK` 后仍须人工检查实际 LAN 可达性、Cookie 行为和 `/api/health` 的 `llm_configured`、`rag_ready`、`history_ready`。若仅做本机演示，`APP_HOST=127.0.0.1` 导致 LAN 预检提示不就绪是预期行为。

## 3. 启动与访问

```bash
python -m netpilot.main
```

此入口读取 `APP_HOST` 和 `APP_PORT`。若改用 `uvicorn netpilot.main:app`，必须显式传 `--host` 和 `--port`；不能误以为 `.env` 的 `APP_HOST` 会覆盖 Uvicorn 命令行默认值。

先在服务端电脑打开 `http://127.0.0.1:8000/api/health`。仅当防火墙策略和演示网段已核对，再让另一台设备访问 `http://<服务端的可信私网 IPv4>:8000/`。两台设备均须使用同一个服务端地址及端口；不能把浏览器设备的 IP 当作 NetPilot 服务地址。校园 Wi-Fi 的客户端隔离、防火墙和跨网段策略可能阻止访问；本阶段不承诺所有手机或校园网段可达，也不要求修改学校网络策略。

## 4. 双账号演示脚本

1. 在真实浏览器打开首页，确认未登录时显示登录/注册面板。注册临时账号 **demo-a**（昵称可写“演示 A”），使用本次演示专用、不复用的非敏感密码。确认右上角显示当前用户。
2. 切换 Mock 场景为 `dns_failure`，输入根 README 中的 DNS Demo 问题。检查 Tool Timeline、诊断结论与 `record_id`；到“我的诊断历史”打开记录，预览并导出 Markdown/JSON 报告。
3. 点击退出登录。确认页面回到登录面板，旧对话、报告和历史不再显示。
4. 注册另一个临时账号 **demo-b**，确认“我的诊断历史”为空，不能看到 A 的记录。若直接用已知的 A 记录 ID 请求详情、报告或导出，后端应返回 404；不得把前端隐藏当成唯一授权控制。
5. 退出 B，重新登录 A，确认 A 的历史与报告仍在。需要展示 VPN/RAG 时，先确认 `rag_ready=true`，并如实显示 `community` 来源。

测试账号名如已被使用，可增加本次演示后缀。不要在演示材料中固定共享密码、展示浏览器开发者工具中的 Cookie/Authorization，或使用真实校园账号。

## 5. 真实截图与收尾

截图须来自当前代码的真实运行页面，并在拍摄时完成对应诊断；按 [`screenshots/README.md`](../screenshots/README.md) 的文件名和隐私检查清单采集。已收录 `demo1` 的个人历史/报告入口和 `demo2` 的空历史两张真实页面截图，`00`–`04` 尚待采集。不要伪造诊断 PNG、合成跨用户状态或把 Mock 结果描述为真实校园网络；未采集的图片不在 README 引用。这两张截图不单独证明服务端越权防护或跨设备 LAN 可达性。

演示结束后从 Web 退出各测试账号并停止进程。浏览器 Cookie 退出时撤销，但 SQLite 中的测试账号和诊断历史仍会保留；按照设备持有者的数据保留决定处理，不在脚本中自动删除数据库。此流程不替代 HTTPS、防火墙审计、真实浏览器人工验收或后续正式部署设计。

## 6. 回归命令

```bash
python -m pytest -q
node --check web/app.js
git diff --check
```

自动测试覆盖认证、Cookie、双用户资源隔离、旧库迁移、Web 状态流转与六个网络 Tool；已有人手提供的 `demo1`/`demo2` 页面截图。其他页面视觉、不同设备 LAN 连通、模型账号配额及余下截图需要现场人工确认。
