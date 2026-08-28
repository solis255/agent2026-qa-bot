"use strict";

const state = {
  sessionId: null,
  health: null,
  busy: false,
  scenarios: [],
  historyCursor: null,
  activeRecordId: null,
};

const elements = {
  serviceState: document.querySelector("#service-state"),
  stateDot: document.querySelector(".state-dot"),
  stateText: document.querySelector(".state-text"),
  apiStatus: document.querySelector("#api-status"),
  llmStatus: document.querySelector("#llm-status"),
  ragStatus: document.querySelector("#rag-status"),
  historyStatus: document.querySelector("#history-status"),
  toolMode: document.querySelector("#tool-mode"),
  scenarioControl: document.querySelector("#scenario-control"),
  scenarioSelect: document.querySelector("#scenario-select"),
  scenarioDescription: document.querySelector("#scenario-description"),
  scenarioCapacity: document.querySelector("#scenario-capacity"),
  customScenarioNew: document.querySelector("#custom-scenario-new"),
  customScenarioDelete: document.querySelector("#custom-scenario-delete"),
  scenarioDialog: document.querySelector("#scenario-dialog"),
  scenarioDialogClose: document.querySelector("#scenario-dialog-close"),
  scenarioForm: document.querySelector("#custom-scenario-form"),
  scenarioFormCancel: document.querySelector("#scenario-form-cancel"),
  scenarioFormSubmit: document.querySelector("#scenario-form-submit"),
  scenarioFormStatus: document.querySelector("#scenario-form-status"),
  customScenarioName: document.querySelector("#custom-scenario-name"),
  customScenarioLabel: document.querySelector("#custom-scenario-label"),
  customScenarioDescription: document.querySelector("#custom-scenario-description"),
  scenarioNetworkConfigured: document.querySelector("#scenario-network-configured"),
  scenarioPingReachable: document.querySelector("#scenario-ping-reachable"),
  scenarioPingLoss: document.querySelector("#scenario-ping-loss"),
  scenarioDnsResolved: document.querySelector("#scenario-dns-resolved"),
  scenarioTcpConnected: document.querySelector("#scenario-tcp-connected"),
  scenarioHttpReachable: document.querySelector("#scenario-http-reachable"),
  scenarioHttpStatus: document.querySelector("#scenario-http-status"),
  scenarioTracerouteReached: document.querySelector("#scenario-traceroute-reached"),
  conversation: document.querySelector("#conversation"),
  chatForm: document.querySelector("#chat-form"),
  messageInput: document.querySelector("#message-input"),
  sendButton: document.querySelector("#send-button"),
  newSession: document.querySelector("#new-session"),
  sessionLabel: document.querySelector("#session-label"),
  interactionNote: document.querySelector("#interaction-note"),
  diagnosisStatus: document.querySelector("#diagnosis-status"),
  diagnosisSummary: document.querySelector("#diagnosis-summary"),
  tokenUsage: document.querySelector("#token-usage"),
  llmDuration: document.querySelector("#llm-duration"),
  toolDuration: document.querySelector("#tool-duration"),
  toolCount: document.querySelector("#tool-count"),
  toolTimeline: document.querySelector("#tool-timeline"),
  sourceList: document.querySelector("#source-list"),
  historyList: document.querySelector("#history-list"),
  historyRefresh: document.querySelector("#history-refresh"),
  historyLoadMore: document.querySelector("#history-load-more"),
  reportActions: document.querySelector("#report-actions"),
  reportPreview: document.querySelector("#report-preview"),
  exportMarkdown: document.querySelector("#export-markdown"),
  exportJson: document.querySelector("#export-json"),
  reportDialog: document.querySelector("#report-dialog"),
  reportContent: document.querySelector("#report-content"),
  reportClose: document.querySelector("#report-close"),
};

const TOOL_LABELS = {
  get_network_info: "获取网络配置",
  ping_host: "Ping 可达性",
  dns_lookup: "DNS 解析",
  tcp_check: "TCP 端口",
  http_check: "HTTP 访问",
  traceroute: "路由追踪",
  knowledge_search: "知识检索",
};

const STATUS_LABELS = {
  normal: "正常",
  abnormal: "发现异常",
  error: "执行失败",
  inconclusive: "结果不确定",
  blocked: "安全阻止",
  reference: "参考资料",
};

const ISSUE_LABELS = {
  undetermined: "尚未确定",
  no_issue_observed: "未发现异常",
  insufficient_evidence: "证据不足",
  dns_resolution_failure: "DNS 解析故障",
  local_network_configuration: "本地网络配置",
  icmp_unreachable: "ICMP 不可达",
  tcp_connectivity_failure: "TCP 连接故障",
  http_connectivity_failure: "HTTP 访问故障",
  proxy_fake_ip_mapping: "代理 Fake-IP",
};

const CONFIDENCE_LABELS = { high: "高", medium: "中", low: "低" };

function setBusy(busy, message = "") {
  state.busy = busy;
  elements.conversation.setAttribute("aria-busy", String(busy));
  const ready = Boolean(state.sessionId && state.health?.llm_configured);
  elements.messageInput.disabled = busy || !ready;
  elements.sendButton.disabled = busy || !ready;
  elements.newSession.disabled = busy || !state.health;
  elements.scenarioSelect.disabled = busy || elements.scenarioSelect.dataset.enabled !== "true";
  elements.customScenarioNew.disabled = busy || elements.customScenarioNew.dataset.available !== "true";
  elements.customScenarioDelete.disabled = busy;
  elements.scenarioFormSubmit.disabled = busy;
  elements.historyRefresh.disabled = busy;
  elements.historyLoadMore.disabled = busy;
  elements.reportPreview.disabled = busy || !state.activeRecordId;
  elements.exportMarkdown.disabled = busy || !state.activeRecordId;
  elements.exportJson.disabled = busy || !state.activeRecordId;
  for (const button of elements.historyList.querySelectorAll("button")) button.disabled = busy;
  elements.sendButton.textContent = busy ? "诊断中…" : "开始诊断";
  if (message) elements.interactionNote.textContent = message;
}

async function requestJSON(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
    let body = null;
    try {
      body = await response.json();
    } catch (_error) {
      body = null;
    }
    if (!response.ok) {
      throw new Error(body?.detail || `请求失败（HTTP ${response.status}）`);
    }
    return body;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时，请稍后重试。");
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function renderHealth(health) {
  state.health = health;
  elements.serviceState.classList.remove("offline");
  elements.serviceState.classList.add("online");
  elements.stateDot.className = "state-dot online";
  elements.stateText.textContent = "后端服务正常";
  elements.apiStatus.textContent = health.status === "ok" ? "正常" : "异常";
  elements.llmStatus.textContent = health.llm_configured ? "已配置" : "未配置";
  elements.ragStatus.textContent = health.rag_ready ? "已就绪" : "尚未构建";
  elements.historyStatus.textContent = health.history_ready ? "已就绪" : "未启用";
  elements.toolMode.textContent = `${String(health.tool_mode).toUpperCase()} 模式`;
  if (!health.llm_configured) {
    elements.interactionNote.textContent = "服务端尚未配置 TJU_API_KEY，聊天暂不可用。";
  }
}

function renderHealthError(error) {
  elements.serviceState.classList.add("offline");
  elements.stateDot.className = "state-dot offline";
  elements.stateText.textContent = "无法连接后端";
  elements.apiStatus.textContent = "不可用";
  elements.llmStatus.textContent = "未知";
  elements.ragStatus.textContent = "未知";
  elements.historyStatus.textContent = "未知";
  elements.toolMode.textContent = "离线";
  elements.interactionNote.textContent = error.message;
}

function appendMessage(role, text) {
  const article = document.createElement("article");
  article.className = `message ${role}-message`;
  const avatar = document.createElement("span");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "你" : role === "error" ? "!" : "AI";
  const content = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = role === "user" ? "你" : role === "error" ? "请求提示" : "诊断助手";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  content.append(title, paragraph);
  article.append(avatar, content);
  elements.conversation.append(article);
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

function resetConversation() {
  elements.conversation.replaceChildren();
  appendMessage(
    "assistant",
    "请描述网络现象。我会按需调用只读检测工具或校园网络知识库，并展示完整证据。",
  );
  renderDiagnosis(null);
  renderMetrics(null);
  renderTools([]);
  renderSources([]);
  setReportRecord(null);
}

function setReportRecord(recordId) {
  state.activeRecordId = recordId || null;
  elements.reportActions.hidden = !state.activeRecordId;
  elements.reportPreview.disabled = state.busy || !state.activeRecordId;
  elements.exportMarkdown.disabled = state.busy || !state.activeRecordId;
  elements.exportJson.disabled = state.busy || !state.activeRecordId;
  if (!state.activeRecordId && elements.reportDialog.open) elements.reportDialog.close();
}

async function createSession({ announce = true } = {}) {
  if (state.busy) return;
  setBusy(true, "正在创建新会话…");
  try {
    const session = await requestJSON("/api/session", { method: "POST" });
    state.sessionId = session.session_id;
    elements.sessionLabel.textContent = `会话 ${session.session_id.slice(0, 8)}`;
    resetConversation();
    elements.interactionNote.textContent = state.health?.llm_configured
      ? "会话已就绪。Enter 发送，Shift + Enter 换行。"
      : "会话已创建，但 TJU LLM 尚未配置。";
    if (announce) elements.messageInput.focus();
  } catch (error) {
    state.sessionId = null;
    elements.sessionLabel.textContent = "会话创建失败";
    appendMessage("error", error.message);
    elements.interactionNote.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

function renderDiagnosis(diagnosis) {
  elements.diagnosisStatus.className = "diagnosis-badge idle";
  if (!diagnosis) {
    elements.diagnosisStatus.textContent = "等待";
    elements.diagnosisSummary.textContent = "提交问题后显示本次诊断结论与证据数量。";
    return;
  }
  const status = diagnosis.status === "completed" ? "completed" : "warning";
  elements.diagnosisStatus.className = `diagnosis-badge ${status}`;
  elements.diagnosisStatus.textContent = diagnosis.status === "completed" ? "已完成" : "需注意";
  const evidenceCount = diagnosis.evidence?.length || 0;
  const summary = String(diagnosis.summary || "").replace(/\s+/g, " ").trim();
  const preview = summary.length > 180 ? `${summary.slice(0, 180)}…` : summary;
  const evidenceMeta = `${diagnosis.tool_rounds} 个工具轮次 · ${evidenceCount} 条结构化证据`;
  elements.diagnosisSummary.textContent = preview ? `${preview}（${evidenceMeta}）` : evidenceMeta;
}

function renderMetrics(metrics) {
  if (!metrics) {
    elements.tokenUsage.textContent = "--";
    elements.llmDuration.textContent = "--";
    elements.toolDuration.textContent = "--";
    elements.toolCount.textContent = "--";
    return;
  }
  const usage = metrics.token_usage || {};
  elements.tokenUsage.textContent = `${Number(usage.total_tokens || 0)}（输入 ${Number(usage.prompt_tokens || 0)} / 输出 ${Number(usage.completion_tokens || 0)}）`;
  elements.llmDuration.textContent = formatDuration(metrics.llm_duration_ms);
  elements.toolDuration.textContent = formatDuration(metrics.tool_duration_ms);
  elements.toolCount.textContent = String(Number(metrics.tool_calls || 0));
}

function formatDuration(value) {
  const milliseconds = Number(value || 0);
  return milliseconds >= 1000
    ? `${(milliseconds / 1000).toFixed(2)} s`
    : `${milliseconds.toFixed(milliseconds % 1 ? 1 : 0)} ms`;
}

function renderTools(tools) {
  elements.toolTimeline.replaceChildren();
  if (!tools?.length) {
    elements.toolTimeline.append(emptyState("01", "本次尚未调用网络或知识工具。"));
    return;
  }
  const list = document.createElement("ol");
  list.className = "timeline-list";
  for (const tool of tools) {
    const item = document.createElement("li");
    item.className = `timeline-item ${tool.finding_status}`;
    const heading = document.createElement("div");
    heading.className = "timeline-heading";
    const name = document.createElement("strong");
    name.textContent = TOOL_LABELS[tool.tool_name] || tool.tool_name;
    const badge = document.createElement("span");
    badge.className = `finding-badge ${tool.finding_status}`;
    badge.textContent = STATUS_LABELS[tool.finding_status] || tool.finding_status;
    heading.append(name, badge);
    const meta = document.createElement("small");
    meta.textContent = `第 ${tool.round} 轮 · ${tool.duration_ms} ms · ${tool.tool_call_id}`;
    const summary = document.createElement("p");
    summary.textContent = tool.summary;
    const details = document.createElement("details");
    const detailsTitle = document.createElement("summary");
    detailsTitle.textContent = "查看参数与结构化结果";
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(
      { arguments: tool.arguments, data: tool.data, error_code: tool.error_code },
      null,
      2,
    );
    details.append(detailsTitle, pre);
    item.append(heading, meta, summary, details);
    list.append(item);
  }
  elements.toolTimeline.append(list);
}

function renderSources(sources) {
  elements.sourceList.replaceChildren();
  if (!sources?.length) {
    elements.sourceList.append(emptyState("KB", "本次回答没有使用知识库来源。"));
    return;
  }
  const list = document.createElement("ul");
  list.className = "source-list";
  for (const source of sources) {
    const item = document.createElement("li");
    const type = document.createElement("span");
    type.className = `source-type ${source.source_type}`;
    type.textContent = source.source_type;
    const title = document.createElement("strong");
    title.textContent = source.title;
    const link = safeSourceLink(source.source);
    const meta = document.createElement("small");
    meta.textContent = `相关度 ${Number(source.score).toFixed(3)} · ${source.file} · ${source.chunk_id}`;
    item.append(type, title, link, meta);
    list.append(item);
  }
  elements.sourceList.append(list);
}

function safeSourceLink(value) {
  const fallback = document.createElement("span");
  fallback.textContent = "来源链接不可用";
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol)) return fallback;
    const link = document.createElement("a");
    link.href = url.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = url.href;
    return link;
  } catch (_error) {
    return fallback;
  }
}

function emptyState(code, message) {
  const container = document.createElement("div");
  container.className = "empty-state";
  const marker = document.createElement("span");
  marker.textContent = code;
  const text = document.createElement("p");
  text.textContent = message;
  container.append(marker, text);
  return container;
}

function renderHistoryItems(items, { append = false } = {}) {
  if (!append) elements.historyList.replaceChildren();
  if (!items?.length && !append) {
    elements.historyList.append(emptyState("DB", "还没有已保存的诊断记录。"));
    return;
  }
  let list = elements.historyList.querySelector(".history-list");
  if (!list) {
    list = document.createElement("ol");
    list.className = "history-list";
    elements.historyList.append(list);
  }
  for (const item of items || []) {
    const row = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.recordId = item.record_id;
    const question = document.createElement("strong");
    question.textContent = item.user_message;
    const meta = document.createElement("span");
    const issue = ISSUE_LABELS[item.primary_issue] || item.primary_issue;
    const confidence = CONFIDENCE_LABELS[item.confidence] || item.confidence;
    meta.textContent = `${formatHistoryTime(item.created_at)} · ${issue} · 置信度 ${confidence}`;
    const metrics = document.createElement("small");
    metrics.textContent = `${Number(item.metrics?.token_usage?.total_tokens || 0)} Token · ${formatDuration(item.metrics?.llm_duration_ms)}`;
    button.append(question, meta, metrics);
    button.addEventListener("click", () => loadDiagnosisRecord(item.record_id));
    row.append(button);
    list.append(row);
  }
}

function formatHistoryTime(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "时间未知";
  return parsed.toLocaleString("zh-CN", { hour12: false });
}

async function loadHistory({ append = false } = {}) {
  if (!state.health?.history_ready) {
    state.historyCursor = null;
    elements.historyLoadMore.hidden = true;
    renderHistoryItems([], { append: false });
    const message = elements.historyList.querySelector(".empty-state p");
    if (message) message.textContent = "诊断历史未启用或暂时不可用。";
    return;
  }
  const cursor = append ? state.historyCursor : null;
  const query = cursor
    ? `/api/diagnoses?limit=10&cursor=${encodeURIComponent(cursor)}`
    : "/api/diagnoses?limit=10";
  try {
    const response = await requestJSON(query);
    renderHistoryItems(response.items, { append });
    state.historyCursor = response.next_cursor;
    elements.historyLoadMore.hidden = !state.historyCursor;
  } catch (error) {
    if (!append) {
      elements.historyList.replaceChildren(emptyState("!", error.message));
    }
    elements.historyLoadMore.hidden = true;
  }
}

async function loadDiagnosisRecord(recordId) {
  if (!recordId || state.busy) return;
  setBusy(true, "正在读取历史诊断…");
  try {
    const record = await requestJSON(`/api/diagnoses/${encodeURIComponent(recordId)}`);
    elements.conversation.replaceChildren();
    appendMessage("user", record.user_message);
    appendMessage("assistant", record.answer);
    renderDiagnosis(record.diagnosis);
    renderMetrics(record.metrics);
    renderTools(record.tool_calls);
    renderSources(record.sources);
    setReportRecord(record.record_id);
    elements.interactionNote.textContent = `正在查看 ${formatHistoryTime(record.created_at)} 的诊断记录；当前会话仍可继续使用。`;
  } catch (error) {
    elements.interactionNote.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function submitChat(event) {
  event.preventDefault();
  const message = elements.messageInput.value.trim();
  if (!message || !state.sessionId || state.busy) return;
  appendMessage("user", message);
  elements.messageInput.value = "";
  setBusy(true, "Agent 正在收集证据，请勿重复提交…");
  try {
    const response = await requestJSON(
      "/api/chat",
      {
        method: "POST",
        body: JSON.stringify({ session_id: state.sessionId, message }),
      },
      120000,
    );
    appendMessage("assistant", response.answer);
    renderDiagnosis(response.diagnosis);
    renderMetrics(response.metrics);
    renderTools(response.tool_calls);
    renderSources(response.sources);
    setReportRecord(response.record_id);
    await loadHistory();
    elements.interactionNote.textContent = "诊断完成。你可以继续追问或新建会话。";
  } catch (error) {
    appendMessage("error", error.message);
    elements.interactionNote.textContent = error.message;
    if (error.message.includes("会话不存在")) state.sessionId = null;
  } finally {
    setBusy(false);
    elements.messageInput.focus();
  }
}

function formatReportPreview(report) {
  const diagnosis = report.diagnosis || {};
  const metrics = report.metrics || {};
  const usage = metrics.token_usage || {};
  const lines = [
    report.title || "TJU NetPilot 故障诊断报告",
    "",
    `报告 ID：${report.report_id}`,
    `生成时间：${formatHistoryTime(report.generated_at)}`,
    `主要问题：${ISSUE_LABELS[diagnosis.primary_issue] || diagnosis.primary_issue || "尚未确定"}`,
    `置信度：${CONFIDENCE_LABELS[diagnosis.confidence] || diagnosis.confidence || "未知"}`,
    "",
    "用户问题",
    String(report.question || ""),
    "",
    "诊断结论",
    String(report.conclusion || ""),
    "",
    "执行指标",
    `Token：${Number(usage.total_tokens || 0)}（输入 ${Number(usage.prompt_tokens || 0)} / 输出 ${Number(usage.completion_tokens || 0)}）`,
    `LLM 耗时：${formatDuration(metrics.llm_duration_ms)}`,
    `Tool 耗时：${formatDuration(metrics.tool_duration_ms)}`,
    `Tool 调用：${Number(metrics.tool_calls || 0)} 次`,
    "",
    "检测证据",
  ];
  if (!report.tool_calls?.length) lines.push("- 本次诊断没有调用工具。");
  for (const tool of report.tool_calls || []) {
    const label = TOOL_LABELS[tool.tool_name] || tool.tool_name;
    const status = STATUS_LABELS[tool.finding_status] || tool.finding_status;
    lines.push(`- ${label}［${status}］：${tool.summary}`);
  }
  lines.push("", "建议操作");
  const recommendations = diagnosis.recommendations || [];
  lines.push(...(recommendations.length ? recommendations.map((item) => `- ${item}`) : ["- 无额外建议。"]));
  lines.push("", "结论限制");
  const limitations = diagnosis.limitations || [];
  lines.push(...(limitations.length ? limitations.map((item) => `- ${item}`) : ["- 无额外限制。"]));
  lines.push("", "参考知识");
  const sources = report.sources || [];
  lines.push(...(sources.length ? sources.map((source) => `- ${source.title}：${source.source}`) : ["- 本次报告没有使用知识库来源。"]));
  return lines.join("\n");
}

async function previewReport() {
  if (!state.activeRecordId || state.busy) return;
  setBusy(true, "正在生成故障报告预览…");
  try {
    const recordId = encodeURIComponent(state.activeRecordId);
    const report = await requestJSON(`/api/diagnoses/${recordId}/report`);
    elements.reportContent.textContent = formatReportPreview(report);
    elements.reportDialog.showModal();
    elements.interactionNote.textContent = "报告已根据保存的诊断证据生成，未额外调用模型。";
  } catch (error) {
    elements.interactionNote.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function downloadReport(format) {
  if (!state.activeRecordId || state.busy) return;
  setBusy(true, `正在准备 ${format === "markdown" ? "Markdown" : "JSON"} 报告…`);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 30000);
  try {
    const recordId = encodeURIComponent(state.activeRecordId);
    const exportUrl = `/api/diagnoses/${recordId}/export?format=${format}`;
    const response = await fetch(exportUrl, {
      headers: { Accept: format === "markdown" ? "text/markdown" : "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) {
      let detail = `报告导出失败（HTTP ${response.status}）`;
      try {
        const body = await response.json();
        if (body?.detail) detail = body.detail;
      } catch (_error) {
        // Keep the bounded generic error when the server did not return JSON.
      }
      throw new Error(detail);
    }
    await response.body?.cancel();
    const link = document.createElement("a");
    link.href = exportUrl;
    link.download = `netpilot-diagnosis-${state.activeRecordId}.${format === "markdown" ? "md" : "json"}`;
    document.body.append(link);
    link.click();
    link.remove();
    elements.interactionNote.textContent = `${format === "markdown" ? "Markdown" : "JSON"} 报告已开始下载。`;
  } catch (error) {
    elements.interactionNote.textContent = error.name === "AbortError" ? "报告导出超时，请稍后重试。" : error.message;
  } finally {
    window.clearTimeout(timeout);
    setBusy(false);
  }
}

async function loadScenarios() {
  if (state.health?.tool_mode !== "mock") return;
  try {
    const response = await requestJSON("/api/scenarios");
    state.scenarios = response.scenarios;
    elements.scenarioSelect.replaceChildren();
    for (const scenario of response.scenarios) {
      const option = document.createElement("option");
      option.value = scenario.name;
      option.textContent = scenario.kind === "custom" ? `自定义 · ${scenario.label}` : scenario.label;
      elements.scenarioSelect.append(option);
    }
    elements.scenarioSelect.value = response.current;
    elements.scenarioSelect.dataset.enabled = String(response.switch_enabled);
    elements.scenarioSelect.disabled = state.busy || !response.switch_enabled;
    elements.scenarioControl.hidden = false;
    const atCapacity = response.custom_count >= response.custom_limit;
    elements.customScenarioNew.hidden = !response.switch_enabled;
    elements.customScenarioNew.dataset.available = String(response.switch_enabled && !atCapacity);
    elements.customScenarioNew.disabled = state.busy || !response.switch_enabled || atCapacity;
    elements.scenarioCapacity.textContent = response.switch_enabled
      ? `自定义场景 ${response.custom_count} / ${response.custom_limit}，服务重启后自动清空。`
      : "自定义场景功能随场景切换开关关闭。";
    renderScenarioDescription(response.current, response.switch_enabled);
  } catch (error) {
    elements.scenarioControl.hidden = false;
    elements.scenarioDescription.textContent = error.message;
  }
}

function renderScenarioDescription(name, enabled) {
  const scenario = state.scenarios.find((item) => item.name === name);
  const suffix = enabled ? "" : "（切换功能未启用）";
  elements.scenarioDescription.textContent = `${scenario?.description || "未知场景"}${suffix}`;
  elements.customScenarioDelete.hidden = scenario?.kind !== "custom" || !enabled;
}

async function activateScenario(scenario) {
  const response = await requestJSON(`/api/scenarios/${encodeURIComponent(scenario)}`, {
    method: "POST",
  });
    state.sessionId = response.session_id;
    elements.sessionLabel.textContent = `会话 ${response.session_id.slice(0, 8)}`;
    elements.scenarioSelect.value = response.current;
    renderScenarioDescription(response.current, true);
    resetConversation();
    appendMessage("assistant", `已切换到“${elements.scenarioSelect.selectedOptions[0].textContent}”测试场景。`);
    elements.interactionNote.textContent = "场景切换完成，旧会话已清理。";
}

async function switchScenario() {
  const scenario = elements.scenarioSelect.value;
  if (!scenario || state.busy || elements.scenarioSelect.dataset.enabled !== "true") return;
  setBusy(true, "正在切换 Mock 场景并重置会话…");
  try {
    await activateScenario(scenario);
  } catch (error) {
    appendMessage("error", error.message);
    elements.interactionNote.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

function syncCustomBehaviorFields() {
  if (elements.scenarioPingReachable.checked) {
    elements.scenarioPingLoss.disabled = false;
    if (Number(elements.scenarioPingLoss.value) >= 100) elements.scenarioPingLoss.value = "0";
    elements.scenarioPingLoss.max = "99";
  } else {
    elements.scenarioPingLoss.value = "100";
    elements.scenarioPingLoss.disabled = true;
  }
  if (elements.scenarioHttpReachable.checked) {
    elements.scenarioHttpStatus.disabled = false;
    if (!elements.scenarioHttpStatus.value) elements.scenarioHttpStatus.value = "200";
  } else {
    elements.scenarioHttpStatus.value = "";
    elements.scenarioHttpStatus.disabled = true;
  }
}

function openCustomScenarioDialog() {
  if (state.busy || elements.customScenarioNew.dataset.available !== "true") return;
  elements.scenarioForm.reset();
  elements.scenarioFormStatus.textContent = "";
  syncCustomBehaviorFields();
  elements.scenarioDialog.showModal();
  elements.customScenarioName.focus();
}

async function createCustomScenario(event) {
  event.preventDefault();
  if (state.busy || !elements.scenarioForm.reportValidity()) return;
  const pingReachable = elements.scenarioPingReachable.checked;
  const httpReachable = elements.scenarioHttpReachable.checked;
  const payload = {
    name: elements.customScenarioName.value.trim(),
    label: elements.customScenarioLabel.value.trim(),
    description: elements.customScenarioDescription.value.trim(),
    behavior: {
      network_configured: elements.scenarioNetworkConfigured.checked,
      ping_reachable: pingReachable,
      ping_packet_loss_percent: pingReachable ? Number(elements.scenarioPingLoss.value) : 100,
      dns_resolved: elements.scenarioDnsResolved.checked,
      tcp_connected: elements.scenarioTcpConnected.checked,
      http_reachable: httpReachable,
      http_status_code: httpReachable ? Number(elements.scenarioHttpStatus.value) : null,
      traceroute_reached: elements.scenarioTracerouteReached.checked,
    },
  };
  setBusy(true, "正在创建并切换自定义 Mock 场景…");
  elements.scenarioFormStatus.textContent = "正在校验场景…";
  try {
    const created = await requestJSON("/api/scenarios/custom", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await loadScenarios();
    elements.scenarioSelect.value = created.name;
    await activateScenario(created.name);
    elements.scenarioDialog.close();
  } catch (error) {
    elements.scenarioFormStatus.textContent = error.message;
    elements.interactionNote.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function deleteCurrentCustomScenario() {
  const scenario = state.scenarios.find((item) => item.name === elements.scenarioSelect.value);
  if (!scenario || scenario.kind !== "custom" || state.busy) return;
  setBusy(true, "正在删除自定义 Mock 场景…");
  try {
    const response = await requestJSON(
      `/api/scenarios/custom/${encodeURIComponent(scenario.name)}`,
      { method: "DELETE" },
    );
    if (response.session_id) {
      state.sessionId = response.session_id;
      elements.sessionLabel.textContent = `会话 ${response.session_id.slice(0, 8)}`;
      resetConversation();
    }
    await loadScenarios();
    appendMessage("assistant", `已删除自定义场景“${scenario.label}”，当前恢复为内置健康场景。`);
    elements.interactionNote.textContent = "自定义场景已删除，旧会话已清理。";
  } catch (error) {
    elements.interactionNote.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function initialize() {
  try {
    const health = await requestJSON("/api/health");
    renderHealth(health);
    await Promise.all([
      createSession({ announce: false }),
      loadScenarios(),
      loadHistory(),
    ]);
  } catch (error) {
    renderHealthError(error);
    setBusy(false);
  }
}

elements.chatForm.addEventListener("submit", submitChat);
elements.newSession.addEventListener("click", () => createSession());
elements.scenarioSelect.addEventListener("change", switchScenario);
elements.customScenarioNew.addEventListener("click", openCustomScenarioDialog);
elements.customScenarioDelete.addEventListener("click", deleteCurrentCustomScenario);
elements.scenarioForm.addEventListener("submit", createCustomScenario);
elements.scenarioDialogClose.addEventListener("click", () => elements.scenarioDialog.close());
elements.scenarioFormCancel.addEventListener("click", () => elements.scenarioDialog.close());
elements.scenarioPingReachable.addEventListener("change", syncCustomBehaviorFields);
elements.scenarioHttpReachable.addEventListener("change", syncCustomBehaviorFields);
elements.historyRefresh.addEventListener("click", () => loadHistory());
elements.historyLoadMore.addEventListener("click", () => loadHistory({ append: true }));
elements.reportPreview.addEventListener("click", previewReport);
elements.exportMarkdown.addEventListener("click", () => downloadReport("markdown"));
elements.exportJson.addEventListener("click", () => downloadReport("json"));
elements.reportClose.addEventListener("click", () => elements.reportDialog.close());
elements.reportDialog.addEventListener("click", (event) => {
  if (event.target === elements.reportDialog) elements.reportDialog.close();
});
elements.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.chatForm.requestSubmit();
  }
});
for (const button of document.querySelectorAll("[data-prompt]")) {
  button.addEventListener("click", () => {
    elements.messageInput.value = button.dataset.prompt || "";
    elements.messageInput.focus();
  });
}

initialize();
