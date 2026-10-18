# Markdown 与来源输出验收

本文保留上一次 Markdown/来源分离改造的验收记录。当前版本已进一步移除独立来源面板，
改为行内引用；最新行为与测试结果见 [折叠时间线与行内引用验收](INLINE_CITATIONS_VALIDATION.md)。

## 原因与边界

- `appendMessage` 原先统一创建 `<p>` 并设置 `textContent`，Assistant 的 Markdown 因此显示为原始标记。
- `_finalize_knowledge_answer` 成功后固定追加“检索来源（参考资料）”，同时多个知识提示词仍要求输出末尾来源列表，与独立 Sources 面板重复。
- 本次不修改 Tool Loop、Evidence Memory、认证归属、会话级历史结构和报告生成逻辑；只调整消息展示与正常知识回答的正文/来源分离。

## 实现

`web/markdown.js` 中的 `renderAssistantMarkdown` 是统一入口：本地 Marked
解析 → DOMPurify 标签/属性白名单 → 安全 `DocumentFragment` → `replaceChildren`。
不将原始字符串赋给 `innerHTML`。不允许图片、脚本、iframe、object、embed、SVG、
事件属性、style、id/name；链接额外限制为绝对 HTTP/HTTPS，并设置 `_blank` 与
`noopener noreferrer`。缺失依赖时降级为纯文本，不绕过净化。

User/Error 保持纯文本；Assistant 使用块级 `.message-body.markdown-body`。
SSE delta 只更新原文，完整结果收到后才解析 Markdown。历史详情仍逐条调用
`appendMessage`，因此与实时回答共用同一 renderer。标题、列表、引用、代码与表格有
轻量 CSS；表格/代码块横向滚动，不引入 UI 框架。

后端移除固定 Source append，并同步调整 synthesis、finalization retry、knowledge
response mode 与常规系统提示词。`AgentResult.sources` 的类型、标题、URL、score、file、
chunk_id 保留。用户询问 source_type 时正文可逐条讨论来源类型。失败 fallback
仍输出带来源类型、标题、原始片段及必要 URL 的溯源内容，不冒充正常模型综合回答。

本次不主动改写模型正文中的任意 URL，也不删除历史中已保存的旧 bibliography；
服务入口、下载地址等属于实际操作内容时可以出现在正文。正常综合阶段通过提示词避免
尾部 bibliography，Python 不再强制追加。

## 自动验收

2026-10-18，本机安装 Node/jsdom 测试依赖后：

| 范围 | 验证 | 对应测试 |
|---|---|---|
| MD-01/02 | heading、strong、列表、引用、代码、表格真实 DOM | `tests/test_web_markdown.py` / `tests/web_markdown_runtime.cjs` |
| MD-03 | User/Error HTML 与 Markdown 均为纯文本 | 同上 |
| MD-04 | 危险标签、事件、混淆 URL、嵌套 SVG/MathML；缺失 sanitizer fail-closed | 同上 |
| MD-05 | 仅 HTTP/HTTPS 外链，安全 target/rel；其他协议及相对链接移除 | 同上 |
| MD-06 | SSE 中间态不解析，完整 answer 才渲染 | 同上 |
| MD-07 | 两轮历史与实时 DOM 一致，不恢复旧 session | 同上 |
| SRC-01/02/03 | 无固定尾注、来源三条保留、所有 synthesis 提示词一致、source_type 问答 | `tests/test_knowledge_finalization.py` |
| SRC-04 | 独立 Sources 面板三种类型及完整元数据 | `tests/web_markdown_runtime.cjs` |
| 持久化/导出 | answer/transcript 原文未变成 HTML，Markdown 导出仍为文本 | `tests/test_diagnosis_reports.py` |
| 静态资源/认证 | 本地 JS 可由同源服务加载，账号切换/历史等原有回归 | `tests/test_web_auth_ui.py` / `tests/web_auth_runtime.cjs` |

基线：`python -m pytest -q`（使用项目 `.venv`）→ **356 passed**。
修改后：**368 passed in 42.87s**，无跳过；`git diff --check` 通过。
前端独立入口：`cd web`，`npm ci --ignore-scripts`，`npm test`。
pytest 也会运行这些 DOM 用例；缺少 Node/jsdom 时会明确跳过八项，不能将跳过当作完整验收。
依赖版本与许可证见 [本地依赖说明](../web/vendor/README.md)。

## 真实模型检查与人工待办

使用需求中的“校园网、VPN 和 eduroam 可信度/时效性”问题，运行了一次真实 tju-llm +
本地知识库的隔离 API 检查（Mock Network Provider、临时账号/数据库，未写现有用户历史）。
结果为 knowledge 模式，无 fallback，六条结构化来源；正文含标题、粗体、列表，没有
固定“检索来源（参考资料）”尾注。历史 transcript 与返回 answer 一致，导出类型为
`text/markdown; charset=utf-8`。本次模型自然回答未生成表格，表格渲染由 MD-02 验证。
这只验证输出分离与保存链路，不等同于对检索召回率或答案事实准确性的评估。

尚未执行人工浏览器目视验收或采集新截图。请重启/刷新部署后按原需求问题检查桌面与
手机宽度下的排版、Sources 面板、历史回放及 Markdown 下载；旧历史保留旧正文不回写。
不得将 jsdom 自动验证或本次 API 检查描述为人工浏览器验收。
