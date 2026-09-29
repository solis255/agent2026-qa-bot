# Milestone 9A：数据库与认证核心验收

本阶段仅实现需求分析文档第 36 节的 **9A — DB + Auth Core**，不是完整的 Milestone 9 P0。正式代码位于 `src/netpilot/auth/` 和 `src/netpilot/api/auth_routes.py`。

## 已实现

- SQLite `users`、`auth_sessions` 表，与现有 Diagnosis History 共用 `DIAGNOSIS_DB_PATH`；建表幂等，不删除或改写现有诊断记录；已存在但字段不兼容的 Auth 表会明确报错。
- 用户名规范化为 lowercase，注册用户名限定为 3–32 位字母、数字、`_`、`-`；昵称可选；密码限定为 8–128 字符且不能只有空白。
- `argon2-cffi` 的 Argon2id 密码哈希；未知用户名登录使用 dummy hash 验证，登录错误统一返回“用户名或密码错误”。
- `secrets.token_urlsafe(32)` 生成浏览器 Session Token，SQLite 仅保存 SHA-256 摘要。服务端验证过期时间，退出立即撤销；登录 Session 数量有界。
- `HttpOnly`、`SameSite=Lax`、`Path=/`、有 `Max-Age` 的 Cookie；`AUTH_COOKIE_SECURE` 可切换 HTTPS Secure 标志；有 Origin 的跨站状态变更请求被拒绝。
- 注册后自动登录；修改密码验证旧密码、撤销该用户所有旧 Auth Sessions，并给当前浏览器新 Cookie。
- `/api/auth/*` 的 422 输入校验响应不回显提交的密码或其他原始请求字段。

## API

| Method | Path | 状态与返回 |
|---|---|---|
| POST | `/api/auth/register` | 201，公开用户信息，Set-Cookie；重名 409 |
| POST | `/api/auth/login` | 200，公开用户信息，Set-Cookie；凭据错误 401 |
| POST | `/api/auth/logout` | 204，服务端撤销，清除 Cookie |
| GET | `/api/auth/me` | 200，当前用户公开信息；未登录/过期 401 |
| POST | `/api/auth/change-password` | 204，撤销旧 Sessions 并轮换当前 Cookie；旧密码错误 401 |

注册示例（仅使用一次性演示凭据）：

```json
{"username":"demo_user","password":"demo-password-123","nickname":"演示用户"}
```

JSON 响应与日志不包含密码哈希、明文密码或完整 Session Token；Token 只通过必要的 `Set-Cookie` 响应头交给浏览器。密码由浏览器通过同源 API 的请求正文提交；若使用 HTTP，传输本身**不加密**。

## 配置

```env
AUTH_COOKIE_NAME=netpilot_session
AUTH_COOKIE_SECURE=false
AUTH_SESSION_HOURS=12
AUTH_MAX_ACTIVE_SESSIONS_PER_USER=5
```

`AUTH_COOKIE_SECURE=false` 仅为本机/比赛 HTTP 演示默认值，正式 HTTPS 环境必须改为 `true`。比赛 LAN Demo 只应使用专门测试账号与不复用的非敏感密码；绝不可输入天津大学统一身份认证密码、真实邮箱密码或其他复用凭据。

## 后续阶段状态

本文件记录 **9A 当时**的认证核心验收范围；之后的 9B 已实现 Chat Session owner、Diagnosis History `user_id` 迁移、Chat/History/Report/Export 授权与跨用户 404，详见 [9B 验收说明](MILESTONE9B_VALIDATION.md)。9C 的 Web 认证界面见 [9C 验收说明](MILESTONE9C_VALIDATION.md)；9D 的配置预检与 LAN 演示流程见 [9D 手册](MILESTONE9D_LAN_DEMO.md)，双账号页面截图已收录，跨设备 LAN 验收及其余截图仍待完成。

## 自动验收

在项目虚拟环境中运行：

```bash
python -m pytest tests/test_auth_api.py -q
python -m pytest -q
git diff --check
```

`tests/test_auth_api.py` 覆盖：注册、重名、输入校验、Argon2id/无明文、Cookie 属性、登录成功/统一失败、退出撤销、改密码及全设备旧会话失效、无效/过期 Token、活跃 Session 上限、Secure 配置、跨 Origin 拒绝、现有 Diagnosis History 数据库兼容。9B 权限隔离测试位于 `tests/test_auth_ownership.py`。
