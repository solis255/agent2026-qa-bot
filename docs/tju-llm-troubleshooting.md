# TJU 模型排查

## 确认配置

在项目根目录使用私有 `.env` 配置 `TJU_API_KEY`、`TJU_API_BASE` 和 `TJU_MODEL=tju-llm`。`TJU_API_BASE` 填写平台分配的专属 SDK 基础地址，SDK 会追加 `/chat/completions`。`/api/health` 的 `llm_configured` 表示应用已有 Key 配置。

```bash
python scripts/test_tju_api.py
```

此脚本发起一次真实模型调用。知识问答还需 `rag_ready=true`。索引构建和模型缓存用法见 [README](../README.md)。

## 识别上游错误

| 现象 | 核对方式 |
| --- | --- |
| `401` / `403` | 核对 Key、专属地址与项目权限。这两类响应会直接结束尝试。 |
| `429` 且有明确配额错误码 | 检查模型平台的额度、计费或项目用量。客户端只根据明确的结构化兼容错误码归为额度问题。 |
| `429` 且原因未知 | 查看 `Retry-After` 和 `retry_stop_reason`。结合模型服务、代理或网关日志核对同一时间与请求 ID。单凭 HTTP 状态无法区分具体限流原因。 |
| 连接错误或超时 | 检查服务端到专属地址的网络路径和代理，查看每次尝试耗时与 `TJU_TIMEOUT_SECONDS`。 |
| 知识回答只展示引用原文 | 检索已提供可引用材料，模型整理失败后展示原文。若页面提示资料不足，则先核对知识索引和检索结果。 |

按 NetPilot 的 `request_id` 找日志事件 `tju_llm_request`，使用 `status_code`、`provider_request_id`、尝试序号和安全错误码定位。NetPilot 的 HTTP 200 可以承载正常传输的降级答案，上游状态以事件字段为准。向维护人员反馈时提供时间、请求 ID 和安全错误码。

## 重试与降级行为

`TJU_MAX_RETRIES` 默认允许两次额外 HTTP 尝试。`TJUClient` 集中处理退避，优先读取 `Retry-After` 或 `Retry-After-Ms`，每次逻辑模型调用的累计等待预算为 10 秒。服务端建议等待超过预算时停止；明确配额错误和上游要求停止重试时也会结束。单次请求超时由 `TJU_TIMEOUT_SECONDS` 控制。

明确的校园知识咨询先检索本地资料，再调用模型整理引用。持续 429 时保留可引用的本地资料，并提示整理状态。具备有效引用的查询通常只发起一次逻辑整理调用。`knowledge_finalization_attempts` 统计逻辑整理次数，可结合 `tju_llm_request` 查看实际 HTTP 尝试数。

```bash
python -m pytest -q tests/test_tju_429_retries.py tests/test_knowledge_429_api.py tests/test_knowledge_finalization.py
```

定向回归覆盖短暂 429 后恢复、持续限流、明确配额不足、来源不足、知识引用与 SSE 降级，使用受控上游响应。
