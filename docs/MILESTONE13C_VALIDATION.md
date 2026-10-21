# Milestone 13C — Student-friendly Client Diagnostics

实现与验收：2026-10-21 起；main 基线 `4a79f84`（Adaptive Diagnostic Flow）。修改保存在当前工作区，无自动 Git 提交。自动检查均使用隔离数据库与受控模型/网络替身，不改变真实校园网络。

## 编码前审计与边界

13B 的确定性 Gate 已按请求、必要环境、TargetCapability、当前 Evidence/Coverage/Sufficiency 产生 `need_client_evidence / request_client_evidence`。原 `ChatResponse.ui_action` 仅有 `ContextQuestion`；12C 通过 `/api/session/client-snapshot` 接收一个 JSON 和 session_id，在 `client_snapshot/validation.py` 校验、脱敏，再由 `service.normalize_snapshot()` 转换为客户端 Evidence。原侧栏要求下载 ps1、运行、选择 JSON、上传后再手工发问。12E 已有 `awaiting_after_evidence`，按同一对象和任务绑定 After、比较并交给 12F evaluator。

13C 只增加结构化交互和编排：原 13B 判定、12C parser/size/privacy/dedup/normalize、12E comparator、12F evaluator、ToolPolicy/Registry、History/Report 和 12I Demo 均复用。仓库实际样式文件是 `web/style.css`，不是 Prompt 中的 styles.css。

## 结构化动作与最终 union

`ChatUIAction = Annotated[ContextQuestion | ClientCheckAction, Field(discriminator="type")]`，Chat 与 SSE complete 使用相同模型。`ClientCheckAction` 继承严格 Pydantic 模型，`extra="forbid"`：

```text
type: Literal["client_check"]
session_id: UUID
action_id: UUID
task_version: int >= 1
target_version: int >= 1
mode: Literal["initial", "recheck"]
platform: Literal["windows"]
reason: 1..100 字符、稳定小写下划线 reason code
collector_supported: Literal[True]
upload_required: Literal[True]
```

不包含本地路径、URL、原始 Snapshot、密钥或用户原文，不由 LLM 选择类型。initial 的主要条件严格来自 13B：`need_client_evidence && request_client_evidence && client_evidence_supported is True`；还检查当前远程 user_client、Windows 与非 Demo。recheck 来自原 12E 当前版本的等待 After 状态。必要环境问题仍优先返回原 ContextQuestion；知识、Host、Mock、非支持平台不收到 Windows 检查动作。

动作 ID 由当前 Session/task/target/mode 确定，同阶段旧 UI 被退役。拒绝保存轻量 task/target scope；相同阶段不重复推送，也不创建 Evidence。“现在可以检查”明确重新开启，任务或对象切换后旧拒绝失效，不永久保存到账号或 SQLite。

## 三步向导与固定采集器

原生 Dialog 分为：下载诊断工具、在 Windows 本机运行、将结果拖回页面。说明检查活动接口、默认网关、DNS 与少量固定 DNS/TCP；不读密码、Cookie、浏览历史、MAC/SSID 或设备序列号，不声称完全匿名。

固定资源由当前实例提供：

```text
/static/client-tools/netpilot-windows-check.zip
/static/client-tools/client_diagnostic_windows.ps1
/static/client-tools/run_client_diagnostic_windows.cmd
/api/client-tools/windows             只读版本与 SHA-256 metadata
/api/client-tools/windows/source      固定脚本源码，text/plain
```

ZIP 仅包含仓库现有 ps1 与新 cmd，不使用请求参数、任意 URL、GitHub ref 或用户路径。metadata 提供 platform、collector_version、snapshot_schema_version=1 及文件/ZIP SHA-256；hash 用于文件一致性，不是代码签名。原 `/static/scripts/client_diagnostic_windows.ps1` 下载兼容保留。

新增 cmd 只以普通用户调用同目录的原 PowerShell collector，并指定同目录结果文件；不加 ExecutionPolicy 参数、不 bypass、不提权、不调用 NetPilot API，不下载代码或上传结果。界面明确要求先解压、审阅并在故障设备本机运行；策略阻止时可跳过，不能降低安全策略。原 ps1 未修改。

尚未完成真实 Windows 普通用户网络采集验收；此次通过固定字节/校验和、wrapper 命令边界与原安全测试验证。浏览器上传使用合成结果，不冒称执行过原生采集器。EXE/Installer 不存在，也未宣称已实现。

## 上传、友好状态与生命周期

支持 dragenter/dragover/dragleave/drop；一次一个文件。拖入明确标为上传的区域就是用户主动提交，文件选择后另点“上传并继续分析”。可用键盘进入文件选择器。扩展名/大小仅前端初筛，最后仍由正式 12C API 校验；没有 easy/student/v2 上传 API。

向导覆盖等待上传、正在验证、已接收、文件过期、时间可能不准确、格式不支持、文件过大、包含不允许的信息、重复文件及上传失败。服务端异常不展示 Pydantic traceback 或原始输入。过期/偏差结果保留历史，提供重新运行或仍使用有限结果的选择，不产生新鲜结果继续凭据。

普通网络检查在上传请求中附带动作 ID、task 与 target 的 scope headers；服务端在原 Session 锁内验证后才导入，旧向导不能把文件写到新任务/对象。无这些 headers 的旧高级上传保持原合同和校验。用户切换会话、logout、历史查看、task/target 变化会退役旧动作；异步响应同时核对 auth epoch、session、版本和 UI generation，不能污染新用户或新会话。Demo Fixture 保留原独立入口，不进入普通 Windows 向导。

## 上传后自动继续与 readiness 重算

所有已有诊断目标的上传在正式 normalize 后调用原 `assess_diagnostic_readiness()`，包括过期或偏差结果；绝不直接写 ready。无法被 Collector 补足的目标仍可为 continue_with_limitations。

只有当前 usable 的新客户端结果生成一次性 `ClientCheckReceipt(receipt_id, snapshot_id, task_version, target_version)`。重复文件、过期/偏差文件、修复前结果没有新凭据。receipt 只保存在有界 Session 内存中，不进入 History、报告、Trace 或日志。

前端使用原 Chat/SSE，发送严格枚举 `continuation="client_evidence_uploaded"` 与 UUID `continuation_id`，不直接调用 LLM。服务端在设置 busy 前验证 owner/session、receipt、当前 task/target、当前 snapshot 与可用性；完成后消费，重放、随机 ID、旧版本、其他会话、被替换或过期结果拒绝，且不会卡住 busy。任意 continuation 字符串/对象或与 context_answer 混用会被拒绝。

自动继续保留原症状，使用原诊断/计划编排和刚上传的实际客户端证据；再次重算 Gate、Coverage 与 Sufficiency。gateway/TCP 正常、DNS 异常可聚合指出采集时解析失败，不说“远程检测了你的电脑”。本路径不增加网络 Tool 调用或额外 LLM 总结调用。

采用最小兼容会话方案：系统继续是一个带明确 `turn_origin="system_continuation"` 的 Turn，规范化文本为 `[系统自动继续：网络检查结果已上传]`。History、页面回放与报告标为系统自动继续，不伪造用户原话；旧记录默认 origin=user，JSON 持久化 schema 仍为 v12，SQLite 仍为 v3。没有保存向导步骤、下载点击、文件对象或 drag hover。

成功后同步环境、对象、readiness、检查摘要/证据、修复计划、Verification 和 Resolution。高级手动上传若收到合法继续凭据，也自动继续，不再要求输入“请分析”。

## 重新检查与 12E

远程 Windows 的当前 `awaiting_after_evidence` 生成 mode=recheck，显示“重新检查”。正式新上传继续由原 `bind_snapshot → compare → VerificationEvaluator` 处理；13C 不直接更改 Resolution。

同一 Before 文件在等待 After 时直接去重，不生成新 Evidence/Trace/继续凭据；其他不晚于基线的结果保留原 12E 限制并提示重新运行。合格 After 输出 improved/unchanged/worsened/inconclusive；improved 不等于 resolved，原 12F 仍独立决定。

## 修改文件

```text
src/netpilot/client_snapshot/check_models.py              新增
src/netpilot/client_snapshot/check_flow.py                新增
src/netpilot/api/client_check_routes.py                   新增
scripts/run_client_diagnostic_windows.cmd                 新增
src/netpilot/conversation_context/models.py
src/netpilot/agent/{orchestrator,schemas,session,task_state}.py
src/netpilot/api/{client_snapshot_routes,presenters,routes,remediation_routes,verification_routes}.py
src/netpilot/models/schemas.py
src/netpilot/{main,history,reports}.py
web/client-check.js                                      新增
web/{app.js,index.html,style.css,package.json}
tests/test_client_check_flow.py                           新增
tests/test_client_check_collector.py                      新增
tests/test_client_check_ui.py                             新增
tests/web_client_check_runtime.cjs                        新增
tests/{test_context_acquisition,test_adaptive_diagnostic_flow,test_web_demo}.py
tests/{web_markdown_runtime,web_auth_runtime,web_verification_runtime}.cjs
README.md
docs/{architecture,test-cases,MILESTONE13C_VALIDATION}.md
screenshots/milestone13c-network-check-wizard.png
screenshots/milestone13c-expired-result.png
```

旧测试只按新功能更新：无 ContextQuestion 改为严格断言 client_check；旧上传后空 readiness 改为重算后的 analyze_existing；脚本缓存版本、实际模块加载顺序和重新检查入口调整为新的精确预期。旧安全、Evidence、版本、零主机调用、Verification、History 等业务断言保留，未删除失败测试或放宽权限断言。

## 自动化记录

基线：`1297 passed in 377.60s (0:06:17)`。新增初步三文件 37 项全部通过；受影响路径回归 `88 passed in 73.64s`。首轮全量中的旧 UI 预期、模块加载及旧 After 时间提示均已定位并修复。其后全量 **`1334 passed in 421.22s (0:07:01)`**，前端 **113 项通过**，Demo runner **6 PASS**。

浏览器边界复查后补充：过期上传也应即时重算准备度，以维持拒绝交互；旧向导上传应在锁内校验阶段。相关定向回归 `68 passed in 65.42s`、`42 passed in 50.78s`。上一轮全量 `1335 passed in 465.65s`。

最终完整验证：**`1336 passed in 452.59s (0:07:32)`，exit 0**；相对基线新增 **39 项测试**，三个新增 Python 文件分别覆盖 API/编排、固定工具资源和 16 项真实 DOM 场景。最终前端 `npm test`：**113 项通过，exit 0**；正式 Demo runner：**6 PASS，exit 0**；`git diff --check`：通过。临时浏览器页与独立验收服务均已关闭；正式用户数据库未修改或清理。

最终运行日志：`.cache/13c-final3.log`、`.cache/13c-web-delivery.log`、`.cache/13c-demo-delivery.log`。均为本地忽略产物。正式命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.cache/pytest-13c-final3
# web/ 目录：npm.cmd test
.\.venv\Scripts\python.exe scripts/run_demo_scenarios.py
git diff --check
```

## 人工验收 A–H

隔离实例 `127.0.0.1:8179`，专用账号/`.cache/13c-browser.db`，真实生产 API/Session/History 和 UI；LLM 与网络 handler 用离线替身。浏览器文件选择/下载过程耗时较长，合成结果实际超过有效期，按真实时效验收，不修改 generated_at 冒充现场采集。

| Case | 已验证的范围 |
| --- | --- |
| A Windows | 浏览器实际出现结构化“开始网络检查 / 暂时不用”，只读和权限说明正确。 |
| B 向导 | 浏览器逐步进入三步；实际下载当前实例固定 ZIP，显示普通用户运行与策略阻止时跳过说明；未执行 Windows collector。 |
| C 拖放/选择与自动继续 | 浏览器真实文件选择器可用并通过原 API 上传。新鲜结果自动继续、完整状态更新与拖放由正式 API + DOM 测试验证；不把过期浏览器文件冒称为 fresh。 |
| D DNS 异常 | 正式上传 DNS failure 合成 v1 结果并自动继续，实际 DNS 检查证据被分析，host handler=0；没有远程执行措辞。 |
| E 拒绝 | 浏览器实际点击“暂时不用”，再问“那怎么办”，返回受限建议，没有新的可点击检查按钮。API/DOM 同时验证正式拒绝、明确重新开启与版本失效。 |
| F macOS | 浏览器实际返回受限说明，Windows 脚本指引和检查启动按钮均不可见；API/DOM 同样验证不支持平台。 |
| G 旧结果 | 浏览器实际显示文件过期与重新运行/仍使用选项；仍使用后明确“历史检查信息、不作为当前状态”，Tool=0，没有自动继续。 |
| H 修复后 | 正式 API 测试完成原手动步骤后收到 recheck action，重复 Before 没有新 Evidence，After 经原 comparator 判 improved；Resolution 未被 13C 直接写成 resolved。 |

截图为真实浏览器捕获。原生 Windows 普通用户运行与真实校园网络故障不在本次已完成验收范围。

## 交付项与后续

Prompt 的 19 项交付内容均在以上章节：文件清单、13B 接入、union、拒绝、向导、固定下载/cmd 边界、拖放、正式上传、自动继续与验证、ready 重算、时效/重复、12E、不支持平台、测试数/全量结果及人工摘要。

留给 13D/P1：整体页面布局重构、签名 EXE/Installer、其他平台 collector、native app、自动更新。当前实现没有自动运行脚本、提权、降低执行策略、远程 Shell 或 collector 自动上传。
