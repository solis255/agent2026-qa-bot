# Milestone 9C：Web 多用户界面验收

本阶段完成需求分析文档第 36 节的 **9C — Web UI**。改动集中于 `web/index.html`、`web/app.js`、`web/style.css`；认证和资源授权仍由 9A/9B 后端承担。

## 页面流程

1. 首页先调用 `GET /api/auth/me`。200 时显示当前用户和主界面，再创建该用户 Chat Session、加载健康状态、Mock 场景与“我的诊断历史”；401 时只显示登录/注册面板。
2. 登录和注册共用可切换表单。注册支持可选昵称、确认密码及基础前端校验；后端继续执行权威校验。注册成功由后端自动建立 HttpOnly Cookie 登录会话。
3. 右上角当前用户菜单提供“我的诊断历史”、修改密码和退出。改密成功后后端撤销旧 Auth Sessions 并轮换当前 Cookie。退出调用服务端撤销接口。
4. 退出、认证过期或页面从浏览器后退缓存恢复时清空页面中的旧会话、诊断、历史、报告和密码字段，再重新验证身份。迟到的旧账号请求不会覆盖新账号页面。

浏览器请求使用 `credentials: "same-origin"`，不在 `localStorage`、`sessionStorage`、URL 中保存密码或 Session Token。用户与诊断文本继续使用 `textContent` 等安全 DOM 接口渲染。静态 Web 不负责决定资源所有权；后端仍对每次受保护请求验证当前用户。

## 自动验收

```bash
python -m pytest -q tests/test_web_auth_ui.py tests/test_web_demo.py
python -m pytest -q
node --check web/app.js
git diff --check
```

`tests/test_web_auth_ui.py` 检查页面控件、同源 Cookie 请求和无浏览器 Token 存储；通过可选的 Node.js 模拟 DOM 运行时测试验证页面状态流转及旧账号迟到请求隔离；并以同源 HTTP 客户端覆盖注册、当前用户、个人历史、改密、退出、第二账号隔离与原账号重新登录。9A/9B 的认证与授权测试继续运行。这些自动检查不等同于真实浏览器视觉/交互验收。

## 人工验收待执行

- 在真实浏览器打开首页，分别检查无 Cookie、有效 Cookie 与过期 Cookie 时的界面；键盘和窄屏下检查登录、注册、错误提示、账号菜单及改密弹窗。
- 用两个专用测试账号完成诊断、历史、报告导出和切换账号，确认旧账号信息不残留；检查 Network 面板的同源 Cookie 和 SSE 行为。
- HTTP/LAN 演示只使用非敏感、未复用的测试密码，绝不输入学校统一身份认证密码。9D 配置预检与 LAN 演示脚本见 [`MILESTONE9D_LAN_DEMO.md`](MILESTONE9D_LAN_DEMO.md)；两张双账号页面截图已收录，其余截图与跨设备 LAN 验收仍需完成。
