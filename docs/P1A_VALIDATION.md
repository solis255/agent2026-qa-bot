# P1-A 诊断历史与指标展示验收说明

## 数据库配置

P1-A 使用 Python 内置 SQLite，不需要安装 MySQL、PostgreSQL、SQLite 服务或额外 Python 包。默认配置为：

```text
DIAGNOSIS_HISTORY_ENABLED=true
DIAGNOSIS_DB_PATH=data/netpilot.db
DIAGNOSIS_MAX_RECORDS=1000
```

不配置这些变量时也可以直接启动。数据库目录会自动创建，数据库、`-wal` 和 `-shm` 文件均被 Git 忽略。

诊断历史会保存用户提交的问题和结构化网络证据。正式部署应根据隐私与保留策略调整数据库路径、文件权限和最大记录数。设置 `DIAGNOSIS_HISTORY_ENABLED=false` 可以完全关闭持久化。

## 已完成能力

- SQLite schema 版本校验、WAL、5 秒 busy timeout 和参数化 SQL；
- 线程安全写入和 `DIAGNOSIS_MAX_RECORDS` 有界淘汰；
- 每次完成聊天自动保存不可变诊断快照；
- 快照包含问题、回答、诊断分类、置信度、建议、限制、Tool Timeline、RAG 来源和执行指标；
- 指标包含 prompt/completion/total Token、LLM 总耗时、Tool 总耗时和 Tool 次数；
- `GET /api/diagnoses` 支持最多 100 条的游标分页和可选会话筛选；
- `GET /api/diagnoses/{record_id}` 返回完整历史详情；
- Web 支持历史刷新、加载更多和详情恢复；
- 数据库初始化或写入失败不会导致聊天失败；
- API Key、Authorization Header 和后端异常详情不进入快照或浏览器响应。

## 自动验收

在仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

本次实现验收结果：`193 passed`。

只运行 P1-A 专项测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_diagnosis_history.py tests\test_chat_api.py tests\test_web_demo.py -q
```

专项测试覆盖：

- 关闭并重新创建仓储后仍可读取完整记录；
- Token、LLM 耗时、Tool 耗时和调用次数准确；
- 保留上限、游标分页和会话过滤；
- 多线程并发写入；
- 未启用、记录不存在、非法游标和非法分页数量；
- 数据库路径不可用时应用安全启动；
- 写入失败时聊天继续成功；
- API Key 不出现在 SQLite 文件中。

## 浏览器手动验收

启动服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn netpilot.main:app --host 127.0.0.1 --port 8001
```

打开 `http://127.0.0.1:8001/` 并确认：

1. 服务概览显示“诊断历史 已就绪”。
2. 完成一次诊断后，“诊断结论”下方出现 Token、LLM 耗时、Tool 耗时和 Tool 次数。
3. 新记录出现在“诊断历史”列表顶部。
4. 新建会话后点击旧记录，页面恢复原问题、回答、指标、Tool Timeline 和来源。
5. 停止并重新启动服务，旧记录仍然存在并可以打开。
6. 浏览器控制台没有错误，页面没有使用 `localStorage` 或 `sessionStorage` 保存诊断内容。

健康接口中的 `history_ready=false` 表示历史功能被关闭或数据库初始化失败；它不代表聊天和网络 Tool 不可用。
