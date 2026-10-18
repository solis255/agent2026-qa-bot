# 折叠时间线与行内引用验收

## 交互与旧面板移除

时间线使用原生 `<details id="timeline-section">` / `<summary>`，保留原工具列表、
状态、耗时、参数、结构化 Evidence 和错误信息。初始、新 Session、打开历史时折叠；
`renderTools` 只更新内容及 count，不改 `open`，所以同 Session 的后续步骤和 SSE
完成态不会覆盖用户手动展开的选择。原生 summary 保留鼠标及键盘交互。

已从 `web/index.html` 删除独立“参考知识 / 校园网络来源”section、`#source-list`
及 empty state；从 `app.js` 删除 `sourceList`、`renderSources`、`safeSourceLink`
和所有面板调用；从 CSS 删除 `.source-list` / `.source-type` 专用样式。不是隐藏旧面板。
后端 `sources`、RAG metrics、报告和导出的独立来源区继续保留。

## 稳定引用协议

`source_ref = sha256((source + "|" + chunk_id).encode("utf-8")).hexdigest()[:12]`。
引用身份不依赖数组排序、score、文件位置或资料标题。同 chunk_id 不同 URL 的资料
不会误合并。`KnowledgeSource` 与 API `SourceView` 共用 canonical ref 规则，载入旧
snapshot 缺失该字段时自动计算；调用方提供不匹配的 ref 不能覆盖真实映射。
这是来源元数据的向后兼容扩展，不需要重建 FAISS 索引或 SQLite 表。

内部答案协议为 `[[cite:<source_ref>]]` 或 `[[cite:<ref1>,<ref2>]]`。
Knowledge Finalizer 的每段资料含 `[SOURCE]`、source_ref、source_type、title、content。
提示词要求仅在实际使用资料的句段末尾引用，不生成 URL bibliography，不用数组 index。
紧凑 Context Builder 也携带同样的 refs。

服务端校验返回 refs 属于本次提供的片段；无引用或未知 ref 分别记录
`missing_citations` / `invalid_citations`。保留最多两次无 Tool 的整理尝试，不新增
检索或网络检测。只有 marker、没有实质正文仍判失败。成功返回的 sources 按真实
引用 refs 选择，不再通过正文提到标题/URL 来猜测引用关系。

失败 fallback 保留实际片段、准确来源类型和标题，并在每个片段末尾附相应 marker，
不追加完整 URL 来源列表。检索原文自带的 citation 协议串会移除，避免冒充系统生成的
溯源尾标；原始 Tool Evidence 内容不变。引用 ID 校验不等于验证每项模型结论的事实
正确性，不应将其描述为自动事实核验。

## 安全渲染与编号

实时聊天、SSE 完成态、历史以及 fallback 均调用
`renderAssistantMarkdown(container, answer, sources)`：

```text
Markdown → Marked → DOMPurify 白名单 → 安全 DOM 文本节点扫描
         → 校验 ref 映射 → createElement 创建尾标 → replaceChildren
```

模型不能注入 citation DOM 或未经净化的 HTML。按本条回答第一次出现的 ref 分配
`[1][2]`，重复 ref 复用原编号；多来源逐个可点。不使用 sources 数组下标。
未知 ref 和未完成 marker 移除；冲突 ref 不生成错误链接；代码/现有链接中不嵌套新链接。
普通诊断摘要也去除内部 marker，避免协议串泄漏到侧栏。

仅绝对 HTTP/HTTPS URL 生成链接，设置 `_blank`、`noopener noreferrer`。
javascript/data/file/相对 URL 不生成链接，改为不可点击尾标。所有 metadata 都通过
DOM 文本/属性 API 设置；tooltip 和 aria-label 显示 Official / Community / Maintainer、
资料标题及合法 URL 的域名，不依赖颜色表达来源类型。

## History、SSE 与报告

SQLite Session snapshot 的 sources 按 source_ref 保留历史并集，旧 Turn 的 marker
不会因新轮次排序或来源变化而失效。历史中每一条 assistant_answer 均用整条记录的
source mapping 解析，各条回答独立编号；只浏览历史，不恢复已过期的 Session。

SSE delta 继续使用纯文本 buffer，不解析可能被拆开的 marker。complete 的完整
answer + sources 交给同一 renderer，最终不显示内部 marker。

Report/Export 的生成逻辑和独立来源章节未删除；Markdown 仍为 Markdown，JSON
保留 answer/transcript 与完整来源元数据（新增 source_ref）。旧回答如果没有 marker，
不补造“句段 ↔ 来源”关系，不重写其正文；旧记录仍可通过报告/导出查看原有来源。

## 验证结果（2026-10-18）

| 范围 | 覆盖 | 测试 |
|---|---|---|
| UI-01～03 | 默认折叠、点击展开/收起、步骤更新保留 open、新会话重置、数据不丢失 | `tests/web_markdown_runtime.cjs` |
| CIT-01～04 | 单/多引用、重复编号、首次出现顺序、类型与无障碍说明 | 同上 |
| CIT-05～07 | 未知/冲突 ref、危险 URL、metadata XSS、Markdown 混排、摘要清理 | 同上 |
| CIT-08～10 | 历史来源重排、拆分 SSE marker、旧来源面板真实删除 | 同上 |
| MD-01～07 | 原有 Markdown / XSS / User 纯文本 / History / SSE 回归 | 同上 |
| 后端协议 | refs 精确映射、缺失/未知/空/下标式 ref、有限重试、fallback 溯源 | `tests/test_knowledge_finalization.py` |
| 身份与持久化 | canonical hash、旧 metadata、同 chunk 不同 URL、Chat + SSE 同记录、重开 SQLite、报告/导出 | `tests/test_inline_citations.py` |

- 修改前：项目 `.venv` 的 `python -m pytest -q` → **368 passed in 39.88s**。
- 修改后：同一环境全量 pytest → **393 passed in 49.26s**，无跳过。
- `cd web` 后 `npm test` → **20 项 DOM 测试通过**。
- `git diff --check` → 通过。

运行完整前端验收前需 `cd web` / `npm ci --ignore-scripts`。没有 Node/jsdom 时
pytest 会明确跳过这 20 项，不应把跳过当作已验证。

使用需求中的 VPN、校园网、eduroam 可信度/时效性问题进行了真实 tju-llm + 本地知识库
隔离 API 检查（Mock Network Provider，临时测试账号/数据库，不写现有用户历史）：
首次整理成功，无 fallback；37 处引用涉及四个来源（official/community），所有 refs
均能解析；历史 transcript/source mapping 与报告导出正常。这是单次协议检查，
不是检索召回率、准确率或性能 benchmark。

## 人工验收待办

本次未执行人工浏览器目视验收或采集新截图。重启后端并 Ctrl+F5 刷新后：

1. 提交需求中的可信度问题，确认段落尾标可直接打开正确来源，正文无内部 marker。
2. hover/focus 尾标检查资料类型和标题，确认侧栏无独立来源面板。
3. 用鼠标和键盘展开/收起时间线，检查计数、参数、错误信息仍在。
4. 保持展开再追问，确认不会强制收起；新建 Session 确认重置。
5. 重新打开历史核对引用 URL；下载 Markdown/JSON 核对独立来源仍在。
6. 在手机宽度检查引用、表格和时间线是否溢出。

jsdom 和 API 检查不冒充人工浏览器验收。
