# Milestone 9B：资源所有权验收

本阶段完成需求分析文档第 36 节的 **9B — Resource Ownership**。9A 已提供账户、服务端 Auth Session 与 HttpOnly Cookie；9B 将现有诊断资源绑定当前用户。正式代码位于 `src/netpilot/agent/session.py`、`src/netpilot/history.py`、`src/netpilot/api/routes.py` 和 `src/netpilot/models/schemas.py`。

## 授权边界

- `POST /api/session` 使用当前登录用户 ID 创建进程内 Chat Session。`POST /api/chat` 和 `POST /api/chat/stream` 在占用 busy 标记之前校验 owner；跨账号或不存在的 session 均返回 404。
- `GET /api/diagnoses` 在 SQLite 查询中按 `user_id` 过滤，游标和 `session_id` 筛选仍限于当前用户。详情、报告预览与 Markdown/JSON 导出都按 `record_id + user_id` 查询；跨账号统一返回 404。
- 以上接口未登录时返回 401。`GET /api/health` 保持公开。Mock 场景写接口也要求登录，但 Mock 场景本身仍是应用级共享演示状态，不承诺 per-user 场景隔离。
- 认证由 `require_current_user` 统一提供；UUID 不被当作访问凭证。

## SQLite 迁移

`SQLiteDiagnosisRepository` 将数据库元数据版本从 1 升至 2；旧 `diagnosis_records` 缺少 `user_id` 时在事务内增加可空列，再建立用户索引。迁移重复运行安全；结构或版本不兼容时明确报错，不静默重建表。

旧记录原样保留且 `user_id=NULL`，不自动归属首个注册用户，普通账号不可见。新记录在数据库行和 JSON 快照中保存当前用户 ID。常规记录上限仅清理带用户 ID 的记录，不借新写入删除 legacy 数据。`users`、`auth_sessions` 与诊断记录仍共用配置的 `DIAGNOSIS_DB_PATH`。

## 自动验收

```bash
python -m pytest -q tests/test_auth_ownership.py
python -m pytest -q
git diff --check
```

`tests/test_auth_ownership.py` 覆盖未登录 401、A/B 会话互用 404、双用户历史列表/会话筛选隔离、详情/报告/两种导出跨账号 404，以及真实 v1 表迁移后旧数据保留、不可见、新数据带 owner、重复打开安全。既有 Session、SSE、History、Report 与 Agent 等回归测试继续运行。

## 后续阶段状态

本文件记录 9B 当时的验收范围。后续 9C 已实现 Web 登录/注册、当前用户、退出、改密码及“我的诊断历史”界面，见 [9C 验收说明](MILESTONE9C_VALIDATION.md)。9D 的配置预检与 LAN 流程见 [9D 手册](MILESTONE9D_LAN_DEMO.md)；双账号页面截图已收录，其余现场截图仍待完成。HTTP LAN 演示只可使用非敏感、专用测试密码，不能输入学校统一身份认证或其他复用密码。Local Provider 检测运行 NetPilot 的服务器主机，不是远端浏览器设备。
