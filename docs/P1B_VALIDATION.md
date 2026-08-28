# P1-B 自动故障报告与 Markdown/JSON 导出验收说明

## 数据库与配置

P1-B 直接读取 P1-A 已保存的 SQLite 诊断快照，不需要安装或配置新的数据库服务。未保存历史记录时不能生成报告，因此应保持：

```text
DIAGNOSIS_HISTORY_ENABLED=true
DIAGNOSIS_DB_PATH=data/netpilot.db
DIAGNOSIS_REPORT_MAX_BYTES=1000000
```

`DIAGNOSIS_REPORT_MAX_BYTES` 限制单次导出文件的 UTF-8 字节数，可配置范围为 1024～5000000。超过限制时 API 返回 `413`，不会返回截断或结构损坏的文件。

## 已完成能力

- 从单条不可变诊断快照确定性生成报告，不发起第二次 LLM 请求；
- 报告包含标识与时间、用户问题、原回答、主要问题、置信度、建议、限制、Token/耗时指标、Tool 证据和知识来源；
- `GET /api/diagnoses/{record_id}/report` 返回版本化结构化预览；
- `GET /api/diagnoses/{record_id}/export?format=markdown|json` 下载 UTF-8 文件；
- 同一记录重复生成的 ID、时间和导出正文稳定一致；
- Markdown 对用户文本和工具文本进行控制字符清理及 Markdown/HTML 元字符转义；
- 来源链接只允许有效 HTTP/HTTPS，JSON 使用 Pydantic 模型序列化；
- 下载使用仅含 UUID 的确定性 ASCII 文件名，并设置 `private, no-store` 和 `nosniff`；
- 格式白名单、记录 UUID、报告体积均由服务端校验；
- Web 支持当前诊断和历史诊断的报告预览、Markdown 下载与 JSON 下载；
- 生成和导出错误使用安全中文消息，不返回数据库、堆栈或凭据。

## 自动验收

在仓库根目录运行全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

本次实现验收结果：`198 passed`。

只运行 P1-B 专项测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_diagnosis_reports.py tests\test_web_demo.py -q
```

专项测试覆盖：

- 报告字段完整、确定性以及 Markdown 注入字符安全处理；
- JSON 可以重新通过 `DiagnosisReportView` 校验；
- Markdown/JSON 的 MIME、下载头、文件名、缓存头和正文稳定性；
- 预览与两种导出不会增加 Agent/LLM 调用次数；
- API Key 等敏感值不进入预览或导出；
- 不存在记录、非法 UUID、非法格式、超限和历史关闭时的安全响应；
- Web 仅使用同源 API、`textContent` 与 Blob 下载，不使用 `innerHTML` 或浏览器持久化存储。

## 浏览器手动验收

启动服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn netpilot.main:app --host 127.0.0.1 --port 8001
```

打开 `http://127.0.0.1:8001/` 并确认：

1. 完成一次诊断后，诊断卡片出现“预览故障报告”“下载 Markdown”“下载 JSON”。
2. 点击预览可看到问题、结论、指标、证据、建议、限制和来源，关闭按钮与点击遮罩均可退出。
3. 两个下载按钮分别得到 `.md` 和 `.json` 文件，文件名中只有固定前缀与记录 UUID。
4. 新建会话后按钮隐藏；从诊断历史打开旧记录后按钮重新出现并对应旧记录。
5. 对同一记录重复下载，文件正文保持一致；JSON 可正常解析，Markdown 可正常阅读。
6. 浏览器控制台没有错误，预览文本不能作为 HTML 执行。

报告是对历史快照的可移植表达，不会重新检查实时网络状态。需要最新证据时，应先发起一次新的诊断，再导出新记录。
