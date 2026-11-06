# Milestone 13D — Simplified Student UI

日期：2026-10-22；基线：main `f728c5f`（Student-friendly Client Diagnostics）。本次为前端信息架构调整，工作区交付，不自动提交 Git。

## 编码前审计与实施计划

已审计 README、DESIGN、architecture、13A/13B/13C 验收、现有 HTML/JS/CSS、公共 Schema、Task/Session 状态与 API 路由。原页面为固定 workspace 双栏：聊天、对话内动态动作在左；Demo/Mock、服务、环境、对象、Snapshot、诊断与指标、修复、验证、Resolution、报修、Reasoning、Timeline、History 长期显示在右。

实施前已向用户说明：保留唯一业务状态、卡片和原 render 函数，将右侧卡片移到分组抽屉；历史独立弹窗，继续复用 viewingHistory；学生主区仅显示聊天与明确下一步。13A/13C 动作保留在对应消息旁；Demo/Mock 移入高级区域。不修改后端诊断、Readiness、Extractor、Snapshot、Verification、Resolution 或数据库。

## 新页面与卡片迁移

```text
顶部：TJU NetPilot / 服务正常或异常 / 账号菜单
居中 Chat（最大 1080px）
  欢迎与新建会话 / 诊断详情
  中文处理状态 + 简短环境摘要（Demo 明确标注演示数据）
  有明确状态时才出现的下一步入口
  对话 / ContextQuestion / ClientCheckAction
  学生快速问题 / 输入框 / 发送

诊断详情（Desktop 520px 原生 modal；小屏全高全宽）
  当前诊断：展开
    环境摘要 → 修改环境 → 环境来源/技术信息
    对象摘要 → 修改对象/技术信息
    网络检查摘要 → 原高级上传与证据
    当前诊断结论
  处理过程：展开；修复/验证内层折叠，无记录则不显示空卡
    原修复计划 / 修复后验证 / 处理状态 / 报修材料
  技术详情：折叠
    原 Metrics/Debug / Reasoning / Tool Timeline / 系统概览 / Session
  报告：折叠
    原预览 / Markdown / JSON
  演示/开发：折叠，仅 DEMO_MODE 或场景切换启用时显示
    原 Demo scenarios/fixtures/reset / Mock/custom controls / 技术测试语句

账号菜单 → 我的诊断历史（独立 modal，原分页）
  选择记录后在聊天区只读展示，提供返回当前诊断
```

所有表单、工作流卡片与报告按钮各保留一份 DOM，无 sidebar/drawer 两套状态。完整证据仍在原 Snapshot Evidence、Tool 结果和历史/报告中，不减少后端数据。高级环境显示已确认的 VPN/代理字段与来源，主摘要避免未知枚举串。Target 的 subject/version/execution/limitation 位于高级 JSON 与原能力说明。

## 主流程动作与现有业务

`student-ui.js` 只投影已有结构化状态，不评估网络故障：

- 13A 问题仍用原 Chips、自由文本与 Chat/SSE；主区“查看问题”仅定位原按钮。
- 13C initial/recheck 仍以 `clientCheckActionCurrent` 验证服务端动作，再打开原三步向导；下载、选择、拖放、正式上传 API、一次性继续、拒绝及过期/重复处理均未替换。
- 当前对象上未失效且有步骤的计划出现“查看修复步骤”，定位并展开原修复卡；反馈仍调用原 API。
- 等待 After 时，有合法 recheck action 才提供“重新检查”；其他情形查看原验证进度，Demo 仍走 Fixtures。完成后主区只显示中文结果，Before/After 表留在详情。
- Resolution 主 Badge 使用中文：诊断中、等待操作、正在验证、有改善、已解决、仍未解决、建议报修；不把内部枚举作为主界面文案。
- 已解决显示“问题已解决”；escalated 或服务端推荐人工支持时出现“生成报修材料”，调用原生成函数，材料仍由用户自行交付，不提交外部工单。

环境编辑仍走 `/api/session/environment/user`；Target 仍走原 `diagnostic-target`。未修改 merge/provenance 或证据隔离算法。Session ID 从主 Header 移入技术详情。服务异常保留顶部文字和状态点及主区错误提示。

## 历史、状态与账号隔离

原游标分页、每页 10 条、上一页缓存、generation 和 authEpoch 检查保留。History Dialog 仅承载原列表，不引入路由或无限加载。读取历史后显示“历史记录 · 只读”，禁用输入和快捷问题；发送、环境/对象、上传、修复、验证、Resolution、报修生成及 Demo/Mock 写函数均保留或补齐 viewingHistory guard。

当前业务 state 不被历史字段覆盖。首次进入历史暂存现有展示 DOM 节点（含原动作监听器）、滚动位置、输入草稿、报告 ID 和提示文案；历史数据只用于只读渲染。返回时恢复原节点和报告，再从唯一当前 state 渲染工作流。支持连续切换历史再返回，不把旧记录当成可恢复 Session。延迟的旧账号历史响应不能污染新账号。

抽屉开关、展开区域、历史工件和展示暂存只属于前端内存，不进入 API、History/Report 或数据库。新会话、退出/账号切换会关闭弹窗并折叠内部详情，丢弃旧账号展示暂存。

## 响应式和可访问性

Desktop Chat 限宽居中，不再固定占用右侧栏；抽屉使用 showModal/close，键盘焦点移入关闭按钮，Escape 关闭后返回“诊断详情”。History 同样使用原生 modal。继续保留 aria-live、role=status、focus-visible、键盘按钮与 summary；处理/异常均有文字，不只依赖颜色。

320/375px 顶部与按钮可换行；快捷问题换行，输入框字号 16px。小屏聊天使用动态视口高度，对话内部滚动，保持 Composer 可见；抽屉全宽全高；向导限制到视口内。原表格使用独立横向滚动，长 URL/证据换行，不撑破页面。`prefers-reduced-motion: reduce` 禁用动画/过渡及平滑滚动。

## 修改文件

```text
web/index.html                         重新组织唯一 DOM，学生文案与原生 Dialog
web/app.js                             状态同步、只读 guard、历史返回和原渲染接入
web/client-check.js                    动作变化时刷新主区摘要，业务链保持原样
web/student-ui.js                      新增：摘要/抽屉/历史展示管理
web/style.css                         单栏、Drawer、Mobile、Reduced motion
web/package.json                      添加新增 DOM runner
tests/test_student_ui.py               新增：24 项 pytest 参数化入口
tests/web_student_ui_runtime.cjs       新增：真实 jsdom 交互与契约
tests/test_web_demo.py                 新脚本缓存版本与加载顺序
tests/test_web_auth_ui.py              新主区 class 的精确契约
tests/web_auth_runtime.cjs             新模块加载和测试 DOM API 支持
tests/web_markdown_runtime.cjs         共用测试加载与卡片迁移断言
tests/web_context_runtime.cjs          原表单的折叠编辑入口断言
tests/web_environment_runtime.cjs      简洁摘要与深层来源断言
tests/web_target_runtime.cjs           学生对象文案与高级边界断言
tests/web_resolution_runtime.cjs       中文状态标签
README.md
docs/architecture.md
docs/test-cases.md
docs/MILESTONE13D_VALIDATION.md
screenshots/milestone13d-*.jpg          真实浏览器截图
```

没有修改 `src/`、后端 API、数据库、模型配置或 Collector。旧测试的环境值、来源优先级、对象/账号边界、Evidence、工具数量、上传及工作流断言保留；仅更新新 UI 信息层级、文案和资源版本的明确预期。

## 自动验证

新增 **24 项**：无重复 ID/required elements/原功能容器、默认折叠、抽屉/焦点/Escape、环境编辑、对象/检查摘要、13A/13C 动作、重检查与旧动作隔离、修复/验证/状态/报修、历史恢复/写 guard/分页/切换/跨账号延迟响应、Demo/退出重置、响应式 CSS 和 reduced motion。原前端 113 项继续运行，总计 137 项。

首轮完整回归：`1334 passed, 2 failed in 416.83s`，两项为新 workspace class 和脚本缓存版本的旧精确断言，已更新并加强模块顺序检查。随后 Web/认证/新增用例定向：`31 passed in 25.84s`。新增 24 项 runner 单独全部通过。

完整回归先通过 `1360 passed in 443.94s`；最终交付复测为 **`1360 passed in 440.16s (0:07:20)`，exit 0**，相对基线新增 24 项。最终布局收敛后的 Web/认证/新增用例定向 **`31 passed in 27.28s`**；最终前端 **137 项通过，exit 0**；12I runner **6 PASS，exit 0**；`git diff --check` 通过。

交付日志：`.cache/13d-delivery.log`、`.cache/13d-web-final2.log`、`.cache/13d-demo.log`；定向检查 `.cache/13d-ui-delivery.log`。均为本地忽略的验证产物。

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.cache/pytest-13d-delivery
npm.cmd test --prefix web
.\.venv\Scripts\python.exe scripts/run_demo_scenarios.py
git diff --check
```

## 实际浏览器验收

隔离 `127.0.0.1:8189`、专用测试账号和 `.cache/13d-browser.db`。真实生产 App/API/SSE/Session/History/Report，知识模型与网络 handler 使用离线替身；Demo 使用原正式受控场景。无真实校园网络设置修改、Collector 执行或外部工单提交。

| Prompt 场景 | 实际验证结果 |
| --- | --- |
| UI-01 新 Session | 浏览器通过：居中 Chat、欢迎、中文轻量状态、学生快捷问题与发送；无永久技术侧栏。 |
| UI-02 纯知识 | 浏览器输入 VPN 使用问题，SSE 正常回答，无环境题或强制展开详情。回答为离线替身，未作为真实知识答案质量验收。 |
| UI-03 追问 | 浏览器“网络有问题”收到范围 Chips，点击仅网页后原 Chat/SSE 成功；旧题禁用。 |
| UI-04 网络检查 | 浏览器 Windows 故障出现开始/暂时不用，仍在对应消息旁；主区入口打开同一向导。 |
| UI-05 详情 | 浏览器打开/关闭分组抽屉，技术/报告/Demo 初始折叠；原表单和卡片可进入。 |
| UI-06 环境 | 浏览器从抽屉将接入保存为校园 WiFi，原接口成功，来源为用户/高，VPN 保持未知。 |
| UI-07 Target | 浏览器切换 NetPilot 服务主机，subject/version/能力更新，客户端动作退役；隔离规则由原 API 与全量测试验证。 |
| UI-08 修复 | 浏览器从“查看修复步骤”展开原卡，Demo 记录一步完成，原反馈 API 成功。 |
| UI-09 重新检查 | 使用正式 API、合成 DNS 快照及原反馈预置等待 After，会话恢复后主区显示“重新检查”；浏览器进入原三步向导，标题为重新检查网络。未执行采集器。Demo 同时实测 Before→反馈→After 对比。 |
| UI-10 已解决 | Demo After 显示 improved，用户确认原症状恢复后原 evaluator 判 resolved；主区显示已解决/问题已解决。 |
| UI-11 报修 | 浏览器主动请求人工支持，主区显示建议报修与生成材料；按钮成功生成 limited 脱敏材料并可预览，没有外部提交。 |
| UI-12 Reasoning | 默认折叠；浏览器在历史详情看到 24 条真实保存轨迹。恢复 Session 没有返回的旧轨迹不从文本补造。 |
| UI-13 Timeline | 浏览器可展开原工具时间线。此次客户端/Fixture 路径为 0 次 host Tool，显示空态符合实际；带工具数据的渲染、来源/错误信息由原 DOM 和 API 回归覆盖。 |
| UI-14 Report | 浏览器报告与报修材料预览成功；Markdown/JSON 按钮和正式导出由原 API/DOM 全量及六个 Demo runner 验证，本次不声称在浏览器重新下载过两份文件。 |
| UI-15 History | 浏览器真实列表第 1 页 10 条→第 2 页→上一页；选择历史禁用发送和环境/对象/上传；返回当前诊断恢复原动作。输入草稿和报告入口恢复另由 DOM 测试验证。 |
| UI-16 Demo/Mock | 浏览器从详情创建原 DNS Demo、加载 Before/After、修复反馈/确认和报告；Mock/custom 容器保留并受配置开关控制，其写链路由原完整 API/DOM 回归验证。 |
| UI-17 Mobile | 375×812：无横向溢出，Composer 底部约 773px；320×700 的重检查会话约 661px，向导无横向溢出、在视口内滚动。 |
| UI-18 Desktop | 1440×900：主 Chat 宽 1080px、Composer 底部约 810px；Drawer 520px，不挤压 Chat。另验 768/1024px，无横向溢出。 |
| UI-19 Keyboard | 浏览器实际 Tab 进入 summary、Enter 切换、Shift+Tab 返回关闭按钮；Escape 关闭并返回详情按钮。 |
| UI-20 Logout/Login | 浏览器从含历史轨迹的状态退出，主区隐藏、所有弹窗/技术详情关闭；同一专用账号重新登录成功。跨账号延迟响应隔离另有 DOM/原认证测试。 |

截图：`screenshots/milestone13d-student-desktop.jpg`（1440px）与 `milestone13d-student-mobile.jpg`（375px），均为最终页面真实浏览器截图，已目视检查。不同尺寸通过浏览器 viewport override 实测；临时覆盖已恢复，验收页面已关闭，隔离 localhost 端口已释放。下载/拖放的既有 13C 自动检查继续执行，本阶段没有冒称真实 Windows 运行或采集；正式用户数据库未修改。

## Prompt 的 20 项交付索引

| 项目 | 交付说明 |
| --- | --- |
| 1 修改文件 | 上方完整文件清单；没有后端改动。 |
| 2 页面架构 | 居中 Chat + 详情 Drawer + 历史 Dialog。 |
| 3 卡片去向 | “新页面与卡片迁移”逐项列出原侧栏所有模块。 |
| 4 默认信息 | 欢迎、对话、中文状态、环境摘要、明确下一步、快捷问题、Composer、新会话/账号菜单。 |
| 5 Drawer | 当前诊断、处理过程展开；技术、报告、演示/开发折叠。 |
| 6 环境/对象 | 原唯一表单及 API，高级详情中可编辑。 |
| 7 13A | 原 Chips/自由输入/Chat/SSE，留在消息附近。 |
| 8 13C | 原 typed action、三步 Wizard、正式上传与继续链保留。 |
| 9 修复 | 有可用计划才显示“查看修复步骤”，定位原卡。 |
| 10 验证 | 服务器 recheck action 驱动“重新检查”；完整对比在原卡。 |
| 11 状态/报修 | 中文 Badge、解决确认、按服务端状态显示材料入口。 |
| 12 技术降级 | Reasoning/Timeline/Metrics 保留且默认隐藏。 |
| 13 History | 账号菜单→独立列表，原分页、只读和返回当前诊断。 |
| 14 Demo/Mock | 原 scenarios/fixtures/custom 操作保留，配置允许才可见。 |
| 15 响应式 | 五种宽度；桌面限宽、小屏全宽、输入框和表格滚动。 |
| 16 Accessibility | 原生 modal、焦点、键盘/Escape、live/status、reduce motion。 |
| 17 新增测试 | 24 项，详见“自动验证”。 |
| 18 全量结果 | 自动验证记录与本地日志。 |
| 19 人工结果 | 上方 UI-01～20，明确区分浏览器和自动覆盖。 |
| 20 后续范围 | 见下节，不把 UI 改造宣称为新诊断/执行能力。 |

## 后续范围

本阶段不新增诊断算法、Tool、Readiness、Environment extractor、Snapshot schema、Verification/Resolution 规则、自动修复/上传、原生 App、桌面客户端、EXE 或 macOS collector、Multi-Agent、MCP、前端框架。继续保持原 no-build 静态部署。真实模型回答质量和真实校园网络/Windows Collector 现场验收不由此次 UI 自动检查替代。
