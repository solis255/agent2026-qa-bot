"use strict";

const state = {
  sessionId: null,
  health: null,
  busy: false,
  scenarios: [],
};

const elements = {
  serviceState: document.querySelector("#service-state"),
  stateDot: document.querySelector(".state-dot"),
  stateText: document.querySelector(".state-text"),
  apiStatus: document.querySelector("#api-status"),
  llmStatus: document.querySelector("#llm-status"),
  ragStatus: document.querySelector("#rag-status"),
  toolMode: document.querySelector("#tool-mode"),
  scenarioControl: document.querySelector("#scenario-control"),
  scenarioSelect: document.querySelector("#scenario-select"),
  scenarioDescription: document.querySelector("#scenario-description"),
  conversation: document.querySelector("#conversation"),
  chatForm: document.querySelector("#chat-form"),
  messageInput: document.querySelector("#message-input"),
  sendButton: document.querySelector("#send-button"),
  newSession: document.querySelector("#new-session"),
  sessionLabel: document.querySelector("#session-label"),
  interactionNote: document.querySelector("#interaction-note"),
  diagnosisStatus: document.querySelector("#diagnosis-status"),
  diagnosisSummary: document.querySelector("#diagnosis-summary"),
  toolTimeline: document.querySelector("#tool-timeline"),
  sourceList: document.querySelector("#source-list"),
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
  reference: "参考资料",
};

function setBusy(busy, message = "") {
  state.busy = busy;
  elements.conversation.setAttribute("aria-busy", String(busy));
  const ready = Boolean(state.sessionId && state.health?.llm_configured);
  elements.messageInput.disabled = busy || !ready;
  elements.sendButton.disabled = busy || !ready;
  elements.newSession.disabled = busy || !state.health;
  elements.scenarioSelect.disabled = busy || elements.scenarioSelect.dataset.enabled !== "true";
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
  renderTools([]);
  renderSources([]);
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
    renderTools(response.tool_calls);
    renderSources(response.sources);
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

async function loadScenarios() {
  if (state.health?.tool_mode !== "mock") return;
  try {
    const response = await requestJSON("/api/scenarios");
    state.scenarios = response.scenarios;
    elements.scenarioSelect.replaceChildren();
    for (const scenario of response.scenarios) {
      const option = document.createElement("option");
      option.value = scenario.name;
      option.textContent = scenario.label;
      elements.scenarioSelect.append(option);
    }
    elements.scenarioSelect.value = response.current;
    elements.scenarioSelect.dataset.enabled = String(response.switch_enabled);
    elements.scenarioSelect.disabled = state.busy || !response.switch_enabled;
    elements.scenarioControl.hidden = false;
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
}

async function switchScenario() {
  const scenario = elements.scenarioSelect.value;
  if (!scenario || state.busy || elements.scenarioSelect.dataset.enabled !== "true") return;
  setBusy(true, "正在切换 Mock 场景并重置会话…");
  try {
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
  } catch (error) {
    appendMessage("error", error.message);
    elements.interactionNote.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function initialize() {
  try {
    const health = await requestJSON("/api/health");
    renderHealth(health);
    await Promise.all([createSession({ announce: false }), loadScenarios()]);
  } catch (error) {
    renderHealthError(error);
    setBusy(false);
  }
}

elements.chatForm.addEventListener("submit", submitChat);
elements.newSession.addEventListener("click", () => createSession());
elements.scenarioSelect.addEventListener("change", switchScenario);
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
