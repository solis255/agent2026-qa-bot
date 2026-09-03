# P1-D SSE 流式回答验收说明

## 实现边界

P1-D 新增：

```text
POST /api/chat/stream
Accept: text/event-stream
```

现有 `POST /api/chat` 不删除、不改变响应结构，供脚本和不支持 SSE 的调用方继续使用。浏览器默认使用流式端点。

这是传输层 SSE：连接和后台工作线程启动后立即发送 `start`，诊断耗时较长时发送心跳；原有 Agent 完成有界 Tool Loop 后，通过多个 `delta` 发送最终回答，再用 `complete` 返回完整结构化快照。它不会再次调用 LLM，也不会伪造 Token Usage。当前版本不宣称 TJU 上游模型 token 原生流式输出。

## 事件协议

所有公开事件都使用单行 JSON `data`，协议版本为 1：

```text
id: 0
event: start
data: {"schema_version":1,"session_id":"..."}

: keep-alive

id: 1
event: delta
data: {"schema_version":1,"sequence":0,"text":"问题判断：..."}

id: 2
event: complete
data: {"schema_version":1,"response":{...完整 ChatResponse...}}
```

后台发生未预期异常且 HTTP 头已经发送时，末尾事件为：

```text
event: error
data: {"schema_version":1,"code":"stream_failed","message":"诊断请求处理失败，请稍后重试。","retryable":true}
```

事件 ID 单调递增，`delta.sequence` 从 0 连续增长；拼接所有 `delta.text` 必须等于 `complete.response.answer`。心跳是 SSE 注释，不参与事件编号。

## 配置

```text
SSE_CHUNK_CHARS=32
SSE_HEARTBEAT_SECONDS=15
```

- `SSE_CHUNK_CHARS`：每个回答事件的最大 Python 字符数，范围 1～256；
- `SSE_HEARTBEAT_SECONDS`：后台诊断期间的心跳间隔，范围 1～30 秒。

不需要数据库或额外依赖。启用 P1-A 历史时，`complete.response.record_id` 正常返回；历史写入失败仍不影响回答完成。

## 安全与可靠性

- 用户问题、回答和工具证据只进入 JSON 序列化，不拼接到 `event` 或 `id` 行；
- 响应设置 `Cache-Control: no-cache, no-transform`、`X-Accel-Buffering: no` 和 `X-Content-Type-Options: nosniff`；
- API Key、Authorization、后端异常和堆栈不进入事件；
- 未知会话、busy 会话、无 API Key 和非法请求在发送 SSE 头前返回普通 HTTP 错误；
- worker 在响应迭代器之外立即启动，浏览器断开或停止读取不会让 Session 永久 busy；
- 同一 Session 仍只允许一个进行中的同步或流式 turn；
- 只有 `complete` 后前端才恢复指标、Timeline、来源、报告入口和历史列表；
- 流缺少 `complete`、JSON 损坏、Content-Type 错误或超时时，前端显示安全错误并保留已接收文本。

## 自动验收

运行全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

本次实现验收结果：`214 passed`。

运行 P1-D 专项测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_chat_stream.py tests\test_chat_api.py tests\test_sessions.py tests\test_web_demo.py -q
```

专项测试覆盖事件版本、顺序和 ID，UTF-8 分片重组，完整 `ChatResponse`，诊断历史写入，HTTP 预检，安全错误，busy 释放，心跳，断开后 worker 完成，以及 SSE 行注入防护。

## 手动验收

启动应用后先创建会话，再使用 `curl.exe -N` 观察原始事件：

```powershell
curl.exe -X POST http://127.0.0.1:8001/api/session
curl.exe -N -X POST http://127.0.0.1:8001/api/chat/stream `
  -H "Accept: text/event-stream" `
  -H "Content-Type: application/json" `
  -d '{"session_id":"替换为会话 UUID","message":"请检查当前网络。"}'
```

浏览器验收：

1. 提交问题后状态先变为“流式连接已建立，正在执行诊断”。
2. 回答区域逐段增长，而不是等待一个 JSON 响应后一次性创建消息。
3. 完成后指标、Tool Timeline、来源、报告按钮和历史记录照常出现。
4. 连续快速向同一 Session 提交第二个请求时，服务端返回 busy；页面正常操作不会重复提交。
5. 浏览器刷新或关闭连接后，等待后台 turn 完成，再使用该 Session 时不会永久返回 busy。
