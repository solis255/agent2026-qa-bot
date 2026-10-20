"use strict";

const state = {
  user: null,
  authMode: "login",
  authBusy: false,
  authEpoch: 0,
  sessionId: null,
  environmentProfile: null,
  diagnosticTarget: null,
  clientSnapshotSummary: null,
  clientEvidence: [],
  remediationPlan: null,
  remediationReadiness: null,
  verificationCycles: [],
  resolution: null,
  resolutionTransitions: [],
  escalationPackages: [],
  escalationSessionId: null,
  environmentTouched: new Set(),
  viewingHistory: false,
  health: null,
  busy: false,
  scenarios: [],
  historyPageIndex: 0,
  historyPages: [],
  historyLoading: false,
  historyGeneration: 0,
  activeRecordId: null,
  reasoningTrace: [],
};

const elements = {
  resolutionBadge: document.querySelector("#resolution-badge"),
  resolutionContent: document.querySelector("#resolution-content"),
  resolutionNotice: document.querySelector("#resolution-notice"),
  escalationGenerate: document.querySelector("#escalation-generate"),
  escalationContent: document.querySelector("#escalation-content"),
  escalationNotice: document.querySelector("#escalation-notice"),
  verificationContent: document.querySelector("#verification-content"),
  verificationCount: document.querySelector("#verification-count"),
  verificationNotice: document.querySelector("#verification-notice"),
  remediationSection: document.querySelector("#remediation-section"),
  remediationGenerate: document.querySelector("#remediation-generate"),
  remediationStatus: document.querySelector("#remediation-status"),
  remediationCount: document.querySelector("#remediation-count"),
  remediationPlan: document.querySelector("#remediation-plan"),
  snapshotForm: document.querySelector("#snapshot-form"),
  snapshotFile: document.querySelector("#snapshot-file"),
  snapshotUpload: document.querySelector("#snapshot-upload"),
  snapshotSummary: document.querySelector("#snapshot-summary"),
  snapshotStatus: document.querySelector("#snapshot-status"),
  snapshotEvidence: document.querySelector("#snapshot-evidence"),
  targetForm: document.querySelector("#target-form"),
  targetSummary: document.querySelector("#target-summary"),
  targetCapability: document.querySelector("#target-capability"),
  targetSubject: document.querySelector("#target-subject"),
  targetSave: document.querySelector("#target-save"),
  targetStatus: document.querySelector("#target-status"),
  environmentForm: document.querySelector("#environment-form"),
  environmentSummary: document.querySelector("#environment-summary"),
  environmentBrowser: document.querySelector("#environment-browser"),
  environmentStatus: document.querySelector("#environment-status"),
  environmentSave: document.querySelector("#environment-save"),
  environmentScope: document.querySelector("#environment-scope"),
  environmentServiceLabel: document.querySelector("#environment-service-label"),
  authGate: document.querySelector("#auth-gate"),
  authTitle: document.querySelector("#auth-title"),
  authForm: document.querySelector("#auth-form"),
  authLoginTab: document.querySelector("#auth-login-tab"),
  authRegisterTab: document.querySelector("#auth-register-tab"),
  authUsername: document.querySelector("#auth-username"),
  authNickname: document.querySelector("#auth-nickname"),
  authPassword: document.querySelector("#auth-password"),
  authConfirm: document.querySelector("#auth-confirm"),
  authSubmit: document.querySelector("#auth-submit"),
  authStatus: document.querySelector("#auth-status"),
  workspace: document.querySelector("#workspace"),
  accountMenu: document.querySelector("#account-menu"),
  accountName: document.querySelector("#account-name"),
  myHistory: document.querySelector("#my-history"),
  myHistoryCard: document.querySelector("#my-history-card"),
  changePasswordOpen: document.querySelector("#change-password-open"),
  logoutButton: document.querySelector("#logout-button"),
  passwordDialog: document.querySelector("#password-dialog"),
  passwordForm: document.querySelector("#password-form"),
  oldPassword: document.querySelector("#old-password"),
  newPassword: document.querySelector("#new-password"),
  confirmNewPassword: document.querySelector("#confirm-new-password"),
  passwordStatus: document.querySelector("#password-status"),
  passwordSubmit: document.querySelector("#password-submit"),
  passwordCancel: document.querySelector("#password-cancel"),
  passwordDialogClose: document.querySelector("#password-dialog-close"),
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
  metricsDebug: document.querySelector("#metrics-debug"),
  toolTimeline: document.querySelector("#tool-timeline"),
  timelineSection: document.querySelector("#timeline-section"),
  timelineCount: document.querySelector("#timeline-count"),
  reasoningSection: document.querySelector("#reasoning-section"),
  reasoningCount: document.querySelector("#reasoning-count"),
  reasoningTrace: document.querySelector("#reasoning-trace"),
  historyList: document.querySelector("#history-list"),
  historyRefresh: document.querySelector("#history-refresh"),
  historyPrevious: document.querySelector("#history-previous"),
  historyNext: document.querySelector("#history-next"),
  historyPageLabel: document.querySelector("#history-page-label"),
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
  single_service: "单服务访问异常",
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
  for (const control of elements.resolutionContent.querySelectorAll("button,select")) control.disabled = busy || !state.user || state.viewingHistory || (control.dataset.export === "true" && !state.activeRecordId);
  elements.escalationGenerate.disabled = busy || !state.user || !state.sessionId || state.viewingHistory;
  for(const control of elements.escalationContent.querySelectorAll("button"))control.disabled=busy || !state.user;
  elements.remediationGenerate.disabled = busy || !state.user || !state.sessionId || state.viewingHistory;
  for (const control of elements.verificationContent.querySelectorAll("button,select,textarea")) control.disabled = busy || !state.user || state.viewingHistory;
  for (const control of elements.remediationPlan.querySelectorAll("button, select, textarea")) {
    control.disabled = busy || !state.user || state.viewingHistory || ["superseded", "cancelled"].includes(state.remediationPlan?.status);
  }
  const snapshotDisabled = busy || !state.user || !state.sessionId || state.viewingHistory || state.diagnosticTarget?.subject !== "user_client" || state.diagnosticTarget?.relationship_to_netpilot !== "remote";
  elements.snapshotFile.disabled = snapshotDisabled;
  elements.snapshotUpload.disabled = snapshotDisabled;
  for (const control of elements.targetForm.querySelectorAll("select, button")) {
    control.disabled = busy || !state.user || !state.sessionId || state.viewingHistory || state.diagnosticTarget?.subject === "mock_client";
  }
  for (const control of elements.environmentForm.querySelectorAll("select, input, button")) {
    control.disabled = busy || !state.user || !state.sessionId || state.viewingHistory;
  }
  elements.conversation.setAttribute("aria-busy", String(busy));
  const ready = Boolean(state.user && state.sessionId && (state.health?.llm_configured || state.isDemo));
  elements.messageInput.disabled = busy || !ready;
  elements.sendButton.disabled = busy || !ready;
  elements.newSession.disabled = busy || !state.user || !state.health;
  elements.scenarioSelect.disabled = busy || !state.user || elements.scenarioSelect.dataset.enabled !== "true";
  elements.customScenarioNew.disabled = busy || !state.user || elements.customScenarioNew.dataset.available !== "true";
  elements.customScenarioDelete.disabled = busy || !state.user;
  elements.scenarioFormSubmit.disabled = busy || !state.user;
  elements.historyRefresh.disabled = busy || !state.user;
  updateHistoryControls();
  elements.reportPreview.disabled = busy || !state.user || !state.activeRecordId;
  elements.exportMarkdown.disabled = busy || !state.user || !state.activeRecordId;
  elements.exportJson.disabled = busy || !state.user || !state.activeRecordId;
  elements.logoutButton.disabled = busy || !state.user;
  elements.changePasswordOpen.disabled = busy || !state.user;
  for (const button of elements.historyList.querySelectorAll("button")) button.disabled = busy || !state.user;
  for(const id of ["demo-create","demo-scenario-select","demo-fill-prompt","demo-refresh"]){const control=document.querySelector(`#${id}`);if(control)control.disabled=busy || !state.user;}
  const demoReset=document.querySelector("#demo-reset");if(demoReset)demoReset.disabled=busy || !state.user || !state.isDemo;
  for(const button of document.querySelectorAll("#demo-fixtures button"))button.disabled=busy || !state.user || button.dataset.available!=="true";
  elements.sendButton.textContent = busy ? "诊断中…" : "开始诊断";
  if (message) elements.interactionNote.textContent = message;
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function apiDetail(body, fallback) {
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail)) {
    return body.detail.map((item) => String(item.msg || "输入不符合要求")).join("；");
  }
  return fallback;
}

async function requestJSON(url, options = {}, timeoutMs = 15000) {
  const authEpoch = state.authEpoch;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      ...options,
      credentials: "same-origin",
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(options.body && !(typeof FormData !== "undefined" && options.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
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
      if (response.status === 401 && !url.startsWith("/api/auth/") && state.authEpoch === authEpoch) {
        showAuthGate("登录已过期，请重新登录。");
      }
      throw new ApiError(apiDetail(body, `请求失败（HTTP ${response.status}）`), response.status);
    }
    return body;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时，请稍后重试。");
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function requestSSE(url, options, onEvent, inactivityTimeoutMs = 45000) {
  const authEpoch = state.authEpoch;
  const controller = new AbortController();
  let inactivityTimeout = null;
  const armInactivityTimeout = () => {
    if (inactivityTimeout !== null) window.clearTimeout(inactivityTimeout);
    inactivityTimeout = window.setTimeout(() => controller.abort(), inactivityTimeoutMs);
  };
  const clearInactivityTimeout = () => {
    if (inactivityTimeout !== null) window.clearTimeout(inactivityTimeout);
    inactivityTimeout = null;
  };
  let completed = false;
  try {
    armInactivityTimeout();
    const response = await fetch(url, {
      ...options,
      credentials: "same-origin",
      signal: controller.signal,
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    clearInactivityTimeout();
    if (!response.ok) {
      let detail = `流式请求失败（HTTP ${response.status}）`;
      try {
        const body = await response.json();
        detail = apiDetail(body, detail);
      } catch (_error) {
        // Keep the bounded generic message when the server response is not JSON.
      }
      if (response.status === 401 && state.authEpoch === authEpoch) {
        showAuthGate("登录已过期，请重新登录。");
      }
      throw new ApiError(detail, response.status);
    }
    if (!response.headers.get("content-type")?.startsWith("text/event-stream")) {
      throw new Error("服务端没有返回有效的 SSE 响应。");
    }
    if (!response.body) throw new Error("当前浏览器无法读取流式响应。");

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    const dispatchBlock = async (block) => {
      if (!block || block.startsWith(":")) return;
      let eventName = "message";
      const dataLines = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      if (!dataLines.length) return;
      let data;
      try {
        data = JSON.parse(dataLines.join("\n"));
      } catch (_error) {
        throw new Error("服务端返回了无法解析的流式事件。");
      }
      if (eventName === "error") {
        throw new Error(data?.message || "流式诊断失败，请稍后重试。");
      }
      await onEvent(eventName, data);
      if (eventName === "complete") completed = true;
    };

    while (true) {
      armInactivityTimeout();
      const { value, done } = await reader.read();
      clearInactivityTimeout();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        await dispatchBlock(block);
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
    if (buffer.trim()) await dispatchBlock(buffer.trim());
    if (!completed) throw new Error("流式响应在完成事件前中断，请稍后重试。");
  } catch (error) {
    if (error.name === "AbortError") throw new Error("流式连接长时间未收到数据，请稍后重试。");
    throw error;
  } finally {
    clearInactivityTimeout();
  }
}

function setAuthMode(mode) {
  state.authMode = mode;
  const registering = mode === "register";
  elements.authTitle.textContent = registering ? "注册 TJU NetPilot" : "登录 TJU NetPilot";
  elements.authLoginTab.setAttribute("aria-pressed", String(!registering));
  elements.authRegisterTab.setAttribute("aria-pressed", String(registering));
  for (const field of document.querySelectorAll(".register-only")) field.hidden = !registering;
  elements.authUsername.minLength = registering ? 3 : 0;
  if (registering) {
    elements.authUsername.setAttribute("pattern", "[A-Za-z0-9_-]{3,32}");
  } else {
    elements.authUsername.removeAttribute("pattern");
  }
  elements.authPassword.minLength = registering ? 8 : 0;
  elements.authPassword.autocomplete = registering ? "new-password" : "current-password";
  elements.authConfirm.required = registering;
  elements.authSubmit.textContent = registering ? "创建账号并登录" : "登录";
  elements.authStatus.textContent = "";
  elements.authPassword.value = "";
  elements.authConfirm.value = "";
}

function showAuthGate(message = "请先登录或注册。") {
  state.authEpoch += 1;
  state.user = null;
  state.health = null;
  state.sessionId = null;
  state.isDemo = false;
  document.querySelector("#demo-controls")?.setAttribute("hidden", "");
  state.environmentProfile = null;
  state.diagnosticTarget = null;
  state.clientSnapshotSummary = null;
  state.clientEvidence = [];
  state.remediationPlan = null;
  state.remediationReadiness = null;
  state.verificationCycles = [];
  state.resolution = null; state.resolutionTransitions = [];
  state.escalationPackages=[];state.escalationSessionId=null;renderEscalation();
  state.viewingHistory = false;
  state.scenarios = [];
  resetHistoryPagination();
  elements.authGate.hidden = false;
  elements.workspace.hidden = true;
  elements.accountMenu.open = false;
  elements.accountMenu.hidden = true;
  elements.accountName.textContent = "";
  elements.authForm.reset();
  elements.passwordForm.reset();
  elements.passwordStatus.textContent = "";
  elements.reportContent.textContent = "";
  elements.scenarioForm.reset();
  elements.scenarioFormStatus.textContent = "";
  if (elements.passwordDialog.open) elements.passwordDialog.close();
  if (elements.reportDialog.open) elements.reportDialog.close();
  if (elements.scenarioDialog.open) elements.scenarioDialog.close();
  elements.messageInput.value = "";
  elements.interactionNote.textContent = "";
  elements.sessionLabel.textContent = "登录后创建会话";
  elements.historyList.replaceChildren(emptyState("DB", "登录后可查看自己的诊断历史。"));
  resetConversation();
  elements.conversation.replaceChildren();
  setBusy(false);
  setAuthMode("login");
  elements.authStatus.textContent = message;
  elements.stateDot.className = "state-dot online";
  elements.stateText.textContent = "请登录以继续";
}

async function enterAuthenticated(user) {
  if (state.user && state.user.id !== user.id) showAuthGate();
  state.authEpoch += 1;
  const authEpoch = state.authEpoch;
  state.user = user;
  elements.accountName.textContent = user.nickname || user.username;
  elements.accountMenu.hidden = false;
  elements.authGate.hidden = true;
  elements.workspace.hidden = false;
  elements.authForm.reset();
  setBusy(false);
  try {
    const health = await requestJSON("/api/health");
    if (state.authEpoch !== authEpoch) return;
    renderHealth(health);
    await Promise.all([
      createSession({ announce: false, restore: true }),
      loadScenarios(),
      loadDemoScenarios(),
      loadHistory(),
    ]);
  } catch (error) {
    if (state.authEpoch === authEpoch) {
      renderHealthError(error);
      setBusy(false);
    }
  }
}

async function submitAuth(event) {
  event.preventDefault();
  if (state.authBusy || !elements.authForm.reportValidity()) return;
  const registering = state.authMode === "register";
  if (registering && elements.authPassword.value !== elements.authConfirm.value) {
    elements.authStatus.textContent = "两次输入的密码不一致。";
    return;
  }
  state.authBusy = true;
  elements.authSubmit.disabled = true;
  elements.authLoginTab.disabled = true;
  elements.authRegisterTab.disabled = true;
  elements.authStatus.textContent = registering ? "正在创建账号…" : "正在登录…";
  const payload = {
    username: elements.authUsername.value.trim(),
    password: elements.authPassword.value,
  };
  if (registering) payload.nickname = elements.authNickname.value.trim() || null;
  try {
    const user = await requestJSON(
      registering ? "/api/auth/register" : "/api/auth/login",
      { method: "POST", body: JSON.stringify(payload) },
    );
    await enterAuthenticated(user);
  } catch (error) {
    elements.authStatus.textContent = error.message;
    elements.authPassword.value = "";
    elements.authConfirm.value = "";
  } finally {
    state.authBusy = false;
    elements.authSubmit.disabled = false;
    elements.authLoginTab.disabled = false;
    elements.authRegisterTab.disabled = false;
  }
}

async function logout() {
  if (!state.user || state.busy) return;
  const authEpoch = state.authEpoch;
  elements.logoutButton.disabled = true;
  try {
    await requestJSON("/api/auth/logout", { method: "POST" });
    if (state.authEpoch !== authEpoch) return;
    showAuthGate("已安全退出。你可以登录其他账号。");
    elements.authUsername.focus();
  } catch (error) {
    if (state.authEpoch === authEpoch) {
      elements.interactionNote.textContent = error.message;
      elements.logoutButton.disabled = false;
    }
  }
}

function openPasswordDialog() {
  if (!state.user || state.busy) return;
  elements.accountMenu.open = false;
  elements.passwordForm.reset();
  elements.passwordStatus.textContent = "";
  elements.passwordDialog.showModal();
  elements.oldPassword.focus();
}

async function submitPasswordChange(event) {
  event.preventDefault();
  if (!state.user || !elements.passwordForm.reportValidity()) return;
  const authEpoch = state.authEpoch;
  if (elements.newPassword.value !== elements.confirmNewPassword.value) {
    elements.passwordStatus.textContent = "两次输入的新密码不一致。";
    return;
  }
  elements.passwordSubmit.disabled = true;
  elements.passwordStatus.textContent = "正在修改密码…";
  try {
    await requestJSON("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        old_password: elements.oldPassword.value,
        new_password: elements.newPassword.value,
      }),
    });
    if (state.authEpoch !== authEpoch) return;
    elements.passwordForm.reset();
    elements.passwordDialog.close();
    elements.interactionNote.textContent = "密码已更新，其他设备上的旧登录会话已失效。";
  } catch (error) {
    if (state.authEpoch === authEpoch) {
      elements.passwordStatus.textContent = error.message;
      elements.oldPassword.value = "";
    }
  } finally {
    if (state.authEpoch === authEpoch) elements.passwordSubmit.disabled = false;
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

function appendMessage(role, text, sources = []) {
  const article = document.createElement("article");
  article.className = `message ${role}-message`;
  const avatar = document.createElement("span");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "你" : role === "error" ? "!" : "AI";
  const content = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = role === "user" ? "你" : role === "error" ? "请求提示" : "诊断助手";
  const body = document.createElement(role === "assistant" ? "div" : "p");
  body.className = role === "assistant" ? "message-body markdown-body" : "message-body";
  if (role === "assistant") renderAssistantMarkdown(body, text, sources);
  else body.textContent = text;
  content.append(title, body);
  article.append(avatar, content);
  elements.conversation.append(article);
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
  return body;
}

function resetConversation() {
  state.viewingHistory = false;
  renderEnvironmentProfile(state.environmentProfile);
  renderDiagnosticTarget(state.diagnosticTarget);
  renderClientSnapshot(state.clientSnapshotSummary, state.clientEvidence);
  elements.snapshotFile.value = "";
  renderRemediationPlan(state.remediationPlan);
  elements.remediationSection.open = false;
  renderVerification(state.verificationCycles);
  renderResolution(state.resolution,state.resolutionTransitions);
  renderEscalation(state.escalationPackages);
  elements.conversation.replaceChildren();
  appendMessage(
    "assistant",
    "请描述网络现象。我会按需调用只读检测工具或校园网络知识库，并展示完整证据。",
  );
  renderDiagnosis(null);
  renderMetrics(null);
  renderTools([]);
  elements.timelineSection.open = false;
  state.reasoningTrace = [];
  renderReasoningTrace([]);
  elements.reasoningSection.open = false;
  setReportRecord(null);
}

function setReportRecord(recordId) {
  state.activeRecordId = recordId || null;
  elements.reportActions.hidden = !state.activeRecordId || !state.user;
  elements.reportPreview.disabled = state.busy || !state.user || !state.activeRecordId;
  elements.exportMarkdown.disabled = state.busy || !state.user || !state.activeRecordId;
  elements.exportJson.disabled = state.busy || !state.user || !state.activeRecordId;
  if (!state.activeRecordId && elements.reportDialog.open) elements.reportDialog.close();
}

const ENVIRONMENT_OS = {unknown: "未知", windows: "Windows", macos: "macOS", linux: "Linux", android: "Android", ios: "iOS"};
const ENVIRONMENT_ACCESS = {unknown: "未知", campus_wifi: "校园 WiFi", campus_wired: "校园有线", off_campus: "校外网络", mobile_hotspot: "手机热点"};
const ENVIRONMENT_SCOPE = {unknown: "未知", all_network: "全部网络", web_only: "仅网页", single_service: "单一服务", internal_resource: "仅校内资源"};
const environmentBoolLabel = (value) => value === true ? "开启" : value === false ? "关闭" : "未知";

function formatEnvironmentSummary(profile) {
  const p = profile || {};
  return `${ENVIRONMENT_OS[p.os_family] || "未知"} · ${ENVIRONMENT_ACCESS[p.network_access] || "未知"} · VPN ${environmentBoolLabel(p.vpn_enabled)} · Proxy ${environmentBoolLabel(p.proxy_enabled)} · ${ENVIRONMENT_SCOPE[p.affected_scope] || "未知"}`;
}

function renderEnvironmentProfile(profile, { historical = false } = {}) {
  state.environmentTouched.clear();
  const p = profile || {};
  elements.environmentSummary.textContent = (historical ? "历史环境：" : "") + formatEnvironmentSummary(p);
  elements.environmentBrowser.textContent = `浏览器状态：${p.browser_online === true ? "在线（不等于互联网可达）" : p.browser_online === false ? "离线" : "未知"}；语言：${p.browser_language || "未知"}；模式：${p.client_mode || "unknown"}`;
  elements.environmentStatus.textContent = historical ? "当前为历史快照，不可在此修改。继续提问时使用当前 Session 环境。" : "用户确认优先于浏览器推断。";
  for (const name of ["os_family", "network_access", "vpn_enabled", "proxy_enabled", "affected_scope", "affected_service"]) {
    const control = elements.environmentForm.querySelector(`[name="${name}"]`);
    const value = p[name] ?? (["os_family", "network_access", "affected_scope"].includes(name) ? "unknown" : "");
    control.value = String(value);
  }
  elements.environmentServiceLabel.hidden = p.affected_scope !== "single_service";
}

function collectBrowserEnvironment() {
  const nav = window.navigator;
  if (!nav) return {};
  const values = {};
  if (typeof nav.onLine === "boolean") values.browser_online = nav.onLine;
  if (typeof nav.language === "string" && /^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$/.test(nav.language) && nav.language.length <= 35) values.browser_language = nav.language;
  const platform = String(nav.userAgentData?.platform || nav.platform || "").toLowerCase();
  values.os_family = /android/.test(platform) ? "android" : /iphone|ipad|ipod|ios/.test(platform) ? "ios" : /win/.test(platform) ? "windows" : /mac/.test(platform) ? "macos" : /linux/.test(platform) ? "linux" : "unknown";
  const connection = nav.connection;
  if (connection) {
    if (["slow-2g", "2g", "3g", "4g"].includes(connection.effectiveType)) values.effective_type = connection.effectiveType;
    if (Number.isInteger(connection.rtt) && connection.rtt >= 0 && connection.rtt <= 60000) values.estimated_rtt_ms = connection.rtt;
    if (Number.isFinite(connection.downlink) && connection.downlink >= 0 && connection.downlink <= 100000) values.estimated_downlink_mbps = connection.downlink;
  }
  return values;
}

async function uploadBrowserEnvironment(authEpoch, sessionId) {
  const baseline = state.environmentProfile;
  try {
    const values = collectBrowserEnvironment();
    if (!Object.keys(values).length) return;
    const profile = await requestJSON("/api/session/environment/browser", { method: "PATCH", body: JSON.stringify({session_id: sessionId, ...values}) });
    if (state.authEpoch !== authEpoch || state.sessionId !== sessionId) return;
    state.environmentProfile = profile;
    renderEnvironmentProfile(profile);
    invalidateDisplayedPlan(baseline, profile);
  } catch (_error) {
    if (state.authEpoch === authEpoch && state.sessionId === sessionId) elements.environmentStatus.textContent = "浏览器环境上报不可用；仍可手动填写环境，不影响诊断。";
  }
}

async function saveEnvironment(event) {
  event.preventDefault();
  if (!state.user || !state.sessionId || state.busy || state.viewingHistory) return;
  const authEpoch = state.authEpoch;
  const sessionId = state.sessionId;
  const baseline = state.environmentProfile || {};
  const values = {};
  for (const name of ["os_family", "network_access", "vpn_enabled", "proxy_enabled", "affected_scope", "affected_service"]) {
    const raw = elements.environmentForm.querySelector(`[name="${name}"]`).value;
    const value = ["vpn_enabled", "proxy_enabled"].includes(name) ? (raw === "" ? null : raw === "true") : name === "affected_service" ? (elements.environmentScope.value === "single_service" ? raw.trim() || null : null) : raw;
    const old = baseline[name] ?? (["os_family", "network_access", "affected_scope"].includes(name) ? "unknown" : null);
    if (value !== old || state.environmentTouched.has(name)) values[name] = value;
  }
  setBusy(true);
  try {
    const profile = await requestJSON("/api/session/environment/user", { method: "PATCH", body: JSON.stringify({session_id: sessionId, ...values}) });
    if (state.authEpoch !== authEpoch || state.sessionId !== sessionId) return;
    state.environmentProfile = profile;
    renderEnvironmentProfile(profile);
    elements.environmentStatus.textContent = "环境已保存到服务端；已有诊断证据保持不变。";
    invalidateDisplayedPlan(baseline, profile);
  } catch (error) {
    if (state.authEpoch === authEpoch) elements.environmentStatus.textContent = error.message;
  } finally {
    if (state.authEpoch === authEpoch) setBusy(false);
  }
}

const TARGET_LABELS = {user_client:"当前浏览器设备",netpilot_host:"NetPilot 服务主机",mock_client:"Mock 模拟终端",unknown:"未记录 / 未明确"};
const EXECUTION_LABELS = {netpilot_host:"NetPilot 服务主机",mock_provider:"Mock Provider",unavailable:"不可用 / 未记录"};

function renderDiagnosticTarget(target, {historical = false} = {}) {
  const t = target || {};
  elements.targetSummary.textContent = `${historical ? "历史对象：" : ""}${TARGET_LABELS[t.subject] || TARGET_LABELS.unknown}${t.relationship_to_netpilot === "remote" ? "（远程）" : ""}`;
  const capability = t.limitation_code === "client_snapshot_available" ? "采集时点证据可用，实时直接检测仍受限" : t.limitation_code === "none" ? t.subject === "mock_client" ? "模拟可用" : "可用" : "受限 / 未记录";
  elements.targetCapability.textContent = `直接检测能力：${capability}；网络工具执行位置：${EXECUTION_LABELS[t.execution_context] || EXECUTION_LABELS.unavailable}`;
  elements.targetSubject.value = t.subject || "unknown";
  elements.targetStatus.textContent = historical ? "历史快照只读，不会改变当前 Session 对象。" : t.subject === "mock_client" ? "Mock 模拟终端由系统管理。" : t.subject === "netpilot_host" ? "检测结果只描述 NetPilot 服务主机，不代表浏览器设备。" : "本机网络工具运行在服务主机，不会将服务主机结果当作此设备结果；当前尚不能直接读取远程客户端 DNS、网关和路由。";
}

function renderClientSnapshot(summary, evidence = [], {historical = false, target = state.diagnosticTarget} = {}) {
  elements.snapshotEvidence.replaceChildren();
  const inScope = summary && summary.applicable !== false && target?.subject === "user_client" && summary.target_version === target.target_version;
  if (!summary) {
    elements.snapshotSummary.textContent = "尚未导入";
    elements.snapshotStatus.textContent = "快照只用于远程当前浏览器设备；不会解除服务主机工具限制。";
    return;
  }
  const stale = summary.stale || Date.now() > Date.parse(summary.expires_at);
  const timing = stale ? "已过期（历史证据）" : summary.clock_skew_suspected ? "疑似时钟偏差" : "已导入（采集时点证据）";
  elements.snapshotSummary.textContent = `${historical ? "历史快照：" : ""}${timing} · Windows ${summary.os?.version || "版本未知"} · ${summary.active_interface_type || "接口未知"} · #${summary.snapshot_sequence} · ${summary.evidence_count} 条证据`;
  elements.snapshotStatus.textContent = `采集时间：${formatHistoryTime(summary.generated_at)}。${!inScope ? "其他对象/版本的历史快照，不用于当前结论。" : "非实时远程检测；上传会替换当前快照，旧证据保留归档。"}${historical ? "当前为只读历史。" : ""}`;
  for (const item of evidence.filter((item) => item.snapshot_id === summary.snapshot_id)) {
    const line = document.createElement("li");
    line.textContent = `${item.tool_name} [${item.status}]：${item.summary}`;
    elements.snapshotEvidence.append(line);
  }
}

const REMEDIATION_STATUS = {proposed:"待处理",in_progress:"进行中",completed:"流程结束（非故障解决）",superseded:"已失效，请重新生成",cancelled:"已取消"};
const STEP_STATUS = {pending:"待处理",completed:"已完成",skipped:"已跳过（未执行）",failed:"执行失败"};
const STEP_OUTCOME = {unknown:"暂不确定",improved:"有改善",no_change:"没有变化",worse:"变差"};

function invalidateDisplayedPlan(before, after) {
  if (!state.remediationPlan) return;
  if (["os_family","os_version","network_access","vpn_enabled","proxy_enabled","affected_scope","affected_service"].some(key => (before?.[key] ?? null) !== (after?.[key] ?? null))) {
    state.remediationPlan = {...state.remediationPlan,status:"superseded"};
    renderRemediationPlan(state.remediationPlan);
    state.verificationCycles=state.verificationCycles.map(c=>["baseline_ready","awaiting_after_evidence","verifying"].includes(c.status)?{...c,status:"superseded"}:c);
    renderVerification(state.verificationCycles);
  }
}

function renderRemediationPlan(plan, {historical = false} = {}) {
  elements.remediationPlan.replaceChildren();
  elements.remediationCount.textContent = `${plan?.steps?.length || 0} 步`;
  if (!plan) {
    elements.remediationStatus.textContent = "尚未生成修复计划；证据不足时先补充现象。";
    return;
  }
  const target = TARGET_LABELS[plan.target_subject] || "未明确";
  elements.remediationStatus.textContent = `${historical ? "历史计划（只读）· " : ""}v${plan.plan_version} · ${target} · ${REMEDIATION_STATUS[plan.status] || "未知状态"} · ${plan.readiness}：${plan.readiness_reason}`;
  const firstPending = plan.steps?.find(step => step.status === "pending");
  const list = document.createElement("ol");
  list.className = "remediation-list";
  for (const step of plan.steps || []) {
    const row = document.createElement("li");
    row.className = step === firstPending && plan.status !== "superseded" ? "remediation-current" : "";
    const details = document.createElement("details");
    details.open = step === firstPending;
    const heading = document.createElement("summary");
    heading.textContent = `${step.order}. ${step.title} · ${step.risk === "low" ? "低风险" : "非 P0 风险"} · ${STEP_STATUS[step.status] || "未知"} · ${STEP_OUTCOME[step.outcome] || "暂不确定"}`;
    const rationale = document.createElement("div");
    rationale.className = "markdown-body remediation-rationale";
    const refs = (step.source_refs || []).map(ref => `[[cite:${ref}]]`).join("");
    renderAssistantMarkdown(rationale, `为什么：${step.rationale || ""}${refs}`, plan.sources || []);
    const instructions = document.createElement("ol");
    for (const text of step.instructions || []) {const line = document.createElement("li");line.textContent = text;instructions.append(line);}
    details.append(heading, rationale, instructions);
    for (const text of [`完成后验证：${step.verification}`,`回滚：${(step.rollback_instructions || []).join("；") || "无需恢复配置"}`,`停止条件：${step.continue_condition || "用户自行决定停止"}`,`用户备注：${step.user_note || "无"}`]) {
      const line = document.createElement("p");line.textContent = text;details.append(line);
    }
    if (!historical && step.status === "pending" && !["superseded","cancelled"].includes(plan.status)) {
      const controls = document.createElement("div");controls.className = "remediation-feedback-controls";
      const outcome = document.createElement("select");outcome.setAttribute("aria-label",`步骤 ${step.order} 的反馈`);
      for (const [value,label] of Object.entries(STEP_OUTCOME)) {const option = document.createElement("option");option.value=value;option.textContent=label;outcome.append(option);}
      const note = document.createElement("textarea");note.maxLength=500;note.placeholder="可选备注，不填密码、Cookie 或密钥";note.setAttribute("aria-label",`步骤 ${step.order} 的备注`);
      controls.append(outcome,note);
      for (const [action,label] of [["complete","已完成"],["skip","跳过"],["fail","执行失败"]]) {
        const button = document.createElement("button");button.type="button";button.textContent=label;button.dataset.action=action;
        button.addEventListener("click",()=>sendRemediationFeedback(step.step_id,action,action === "skip" ? "unknown" : outcome.value,note.value));
        controls.append(button);
      }
      details.append(controls);
    }
    row.append(details);list.append(row);
  }
  elements.remediationPlan.append(list);
}

const RESOLUTION_LABELS={diagnosing:"诊断中",action_required:"等待操作",verifying:"正在验证",resolved:"已解决",improved:"有改善",unresolved:"未解决",escalated:"建议人工处理"};

function applyResolution(data) {
  state.resolution=data.resolution || null;state.resolutionTransitions=data.resolution_transitions || [];
  if(Object.hasOwn(data,"escalation_packages"))state.escalationPackages=data.escalation_packages || [];
  renderResolution(state.resolution,state.resolutionTransitions);
  if(!state.viewingHistory)renderEscalation(state.escalationPackages);
}

function renderResolution(record,transitions=[],{historical=false,target=state.diagnosticTarget}={}) {
  const status=Object.hasOwn(RESOLUTION_LABELS,record?.state) ? record.state : "diagnosing";
  const mock=target?.subject === "mock_client" ? " · Mock 模拟终端（非真实校园网络）" : "";
  elements.resolutionBadge.textContent=`${historical ? "历史状态：" : ""}${RESOLUTION_LABELS[status]}${mock}`;
  elements.resolutionBadge.dataset.state=status;
  elements.resolutionContent.replaceChildren();elements.resolutionNotice.textContent="";
  for(const text of [record?.reason_summary || "尚在收集诊断依据。",`客观复核：${record?.objective_result || "unknown"}；用户确认（主观）：${record?.user_confirmation || "unknown"}`,`状态版本：${record?.state_version || 1}；最后 Verification：${record?.based_on_verification_id || "无"}`]){const p=document.createElement("p");p.textContent=text;elements.resolutionContent.append(p);}
  if(record?.escalation_recommended){const p=document.createElement("p");p.textContent=`人工支持建议：${record.escalation_summary || record.escalation_reason || "建议人工核验"}。仅为建议，未提交外部工单。`;elements.resolutionContent.append(p);}
  const details=document.createElement("details"),summary=document.createElement("summary");summary.textContent=`状态变化记录（${transitions.length}）`;details.append(summary);
  for(const t of transitions){const p=document.createElement("p");p.textContent=`v${t.state_version} ${RESOLUTION_LABELS[t.from_state] || "未知"} → ${RESOLUTION_LABELS[t.to_state] || "未知"}：${t.summary}`;details.append(p);}elements.resolutionContent.append(details);
  if(historical || state.viewingHistory || !state.user || !state.sessionId)return;
  const controls=document.createElement("div");controls.className="resolution-controls";
  const button=(label,callback)=>{const b=document.createElement("button");b.type="button";b.textContent=label;b.addEventListener("click",callback);b.disabled=state.busy;controls.append(b);return b;};
  if(status === "resolved")button("查看修复过程",()=>{elements.remediationSection.open=true;document.querySelector("#verification-section").open=true;});
  if(["resolved","escalated"].includes(status)){
    const b=button("导出诊断报告",()=>elements.exportMarkdown.click());b.dataset.export="true";b.disabled=state.busy || !state.activeRecordId;
  }else{
    const select=document.createElement("select");select.setAttribute("aria-label","原始症状确认");
    for(const [value,label] of [["unknown","暂不确定"],["resolved","原始症状已恢复"],["improved","有改善但未完全恢复"],["not_resolved","仍未解决"]]){const o=document.createElement("option");o.value=value;o.textContent=label;select.append(o);}
    select.value=record?.user_confirmation || "unknown";controls.append(select);
    button("确认症状",()=>resolutionRequest("confirm",{session_id:state.sessionId,status:select.value}));
    button("请求人工支持",()=>resolutionRequest("request-support",{session_id:state.sessionId}));
    if(["improved","unresolved","action_required"].includes(status) && state.remediationPlan?.steps?.some(s=>s.status === "pending" && s.risk === "low" && !s.requires_admin))button("继续下一步",()=>{elements.remediationSection.open=true;elements.remediationSection.scrollIntoView?.({block:"nearest"});});
  }
  elements.resolutionContent.append(controls);
}

async function refreshResolution() {
  const epoch=state.authEpoch,sid=state.sessionId;
  if(!state.user || !sid || state.viewingHistory)return;
  const data=await requestJSON(`/api/session/resolution?session_id=${encodeURIComponent(sid)}`);
  if(epoch === state.authEpoch && sid === state.sessionId)applyResolution(data);
}

function renderEscalation(packages=[],{historical=false,sessionId=state.sessionId,staleIds=[]}={}) {
  if(!historical)packages=packages.filter(p=>!p.session_id || p.session_id === sessionId);
  state.escalationSessionId=sessionId;
  elements.escalationContent.replaceChildren();elements.escalationNotice.textContent="";
  elements.escalationGenerate.hidden=historical;
  elements.escalationGenerate.textContent=packages.length ? "生成最新版报修材料" : "生成报修材料";
  elements.escalationGenerate.disabled=state.busy || !state.user || !state.sessionId || historical;
  for(const p of [...packages].reverse()){
    const card=document.createElement("details"),summary=document.createElement("summary");
    const changed=!historical && ((p.created_from_state_version && p.created_from_state_version !== state.resolution?.state_version)
      || (p.created_from_target_version && p.created_from_target_version !== state.diagnosticTarget?.target_version)
      || (p.verification_summary?.at(-1)?.verification_id && p.verification_summary.at(-1).verification_id !== state.verificationCycles.at(-1)?.verification_id));
    const stale=staleIds.includes(p.package_id) || changed ? " · 状态已变化，旧材料仅供历史参考" : "";
    summary.textContent=`${historical ? "历史材料 · " : ""}v${p.package_version} · ${p.completeness} · ${formatHistoryTime(p.generated_at)}${stale}`;
    card.append(summary);
    const privacy=document.createElement("p");privacy.className="privacy-notice";
    privacy.textContent=`隐私处理：✓ 已移除凭据类信息 ✓ 已隐藏 MAC / SSID ✓ 已隐藏主机名；策略 v${p.privacy_policy_version || "1"}`;
    card.append(privacy);
    for(const value of [p.target?.notice,`处理状态：${RESOLUTION_LABELS[p.resolution?.state] || p.resolution?.state || "未知"}；${p.escalation_reason?.summary || ""}`,...(p.completeness_notes || [])]){
      const line=document.createElement("p");line.textContent=value || "";card.append(line);
    }
    for(const [label,format,preview] of [["预览报修材料","md",true],["下载 Markdown","md",false],["下载 JSON","json",false]]){
      const b=document.createElement("button");b.type="button";b.textContent=label;b.disabled=state.busy || !state.user;
      b.addEventListener("click",()=>openEscalation(p.package_id,sessionId,format,preview));card.append(b);
    }
    elements.escalationContent.append(card);
  }
}

async function generateEscalation() {
  if(!state.user || !state.sessionId || state.busy || state.viewingHistory)return;
  const epoch=state.authEpoch,sid=state.sessionId;setBusy(true);
  try{
    const data=await requestJSON("/api/session/escalation-package",{method:"POST",body:JSON.stringify({session_id:sid})});
    if(epoch !== state.authEpoch || sid !== state.sessionId || state.viewingHistory)return;
    state.escalationPackages=data.packages || [];
    renderEscalation(state.escalationPackages,{staleIds:data.stale_package_ids || []});
    appendTurnReasoningTrace(data.reasoning_trace || []);
    elements.escalationNotice.textContent="已生成报修材料；未提交工单、未通知任何外部人员。" + (data.persistence === "memory" ? " 当前仅保存在内存，服务重启后不保留。" : "");
  }catch(error){if(epoch === state.authEpoch && sid === state.sessionId)elements.escalationNotice.textContent=error.message;}
  finally{if(epoch === state.authEpoch)setBusy(false);}
}

async function openEscalation(id,sid,format,preview=false) {
  if(!state.user || state.busy || sid !== state.escalationSessionId)return;
  const epoch=state.authEpoch;setBusy(true);
  const controller=new AbortController(),timer=window.setTimeout(()=>controller.abort(),30000);
  try{
    const url=`/api/session/escalation-package/${encodeURIComponent(id)}/export?session_id=${encodeURIComponent(sid)}&format=${format}`;
    const response=await fetch(url,{credentials:"same-origin",signal:controller.signal,cache:"no-store"});
    if(!response.ok){if(response.status === 401 && epoch === state.authEpoch)showAuthGate("登录已过期，请重新登录。");throw new Error(`材料读取失败（HTTP ${response.status}）`);}
    const content=await response.text();
    if(epoch !== state.authEpoch || sid !== state.escalationSessionId)return;
    if(preview){document.querySelector("#report-title").textContent="报修材料预览";elements.reportContent.textContent=content;elements.reportDialog.showModal();}
    else{
      const blob=new Blob([content],{type:format === "md" ? "text/markdown;charset=utf-8" : "application/json"});
      const objectUrl=URL.createObjectURL(blob),link=document.createElement("a");
      link.href=objectUrl;link.download=`netpilot-escalation-${id}.${format}`;document.body.append(link);link.click();link.remove();
      window.setTimeout(()=>URL.revokeObjectURL(objectUrl),1000);
    }
  }catch(error){if(epoch === state.authEpoch && sid === state.escalationSessionId)elements.escalationNotice.textContent=error.name === "AbortError" ? "材料读取超时，请稍后重试。" : error.message;}
  finally{window.clearTimeout(timer);if(epoch === state.authEpoch)setBusy(false);}
}

async function resolutionRequest(action,body) {
  if(!state.user || !state.sessionId || state.busy || state.viewingHistory)return;
  const epoch=state.authEpoch,sid=state.sessionId;setBusy(true);
  try{
    const result=await requestJSON(`/api/session/resolution/${action}`,{method:"POST",body:JSON.stringify(body)});
    if(epoch !== state.authEpoch || sid !== state.sessionId)return;
    applyResolution(result);appendTurnReasoningTrace(result.reasoning_trace || []);
  }catch(error){if(epoch === state.authEpoch && sid === state.sessionId)elements.resolutionNotice.textContent=error.message;}
  finally{if(epoch === state.authEpoch)setBusy(false);}
}

const VERIFICATION_RESULT = {improved:"有改善",unchanged:"无变化",worsened:"变差",inconclusive:"暂时无法确认",unknown:"尚未验证"};
const METRIC_LABEL = {dns_resolution:"DNS 解析",gateway_reachability:"网关可达性",tcp_connectivity:"TCP 连通性",http_reachability:"HTTP 可达性",network_configuration:"网络配置",campus_auth:"校园认证",vpn_state:"VPN 状态",proxy_state:"代理状态",user_observed_symptom:"用户症状"};

function renderVerification(cycles = [], {historical = false} = {}) {
  elements.verificationContent.replaceChildren();
  elements.verificationNotice.textContent = "";
  elements.verificationCount.textContent = `${cycles.length} 轮`;
  if (!cycles.length) {elements.verificationContent.textContent = "尚无修复前后验证记录。";return;}
  const latest = cycles[cycles.length-1];
  for (const cycle of cycles) {
    const card = document.createElement("section");card.className = "verification-cycle";
    const title = document.createElement("h3");title.textContent = `验证 #${cycle.verification_sequence} · ${TARGET_LABELS[cycle.target_subject] || "未知对象"} v${cycle.target_version} · ${cycle.status}`;
    const result = document.createElement("p");result.textContent = `结果：${VERIFICATION_RESULT[cycle.result] || "未知"}。${cycle.result_summary || "尚待验证"}（有改善不等于故障解决）`;
    card.append(title,result);
    const scroll = document.createElement("div");scroll.className="verification-table-scroll";
    const table = document.createElement("table");table.className = "verification-table";
    const head = document.createElement("thead"),header=document.createElement("tr");
    for(const label of ["指标 / 目标","修复前","修复后","变化"]){const th=document.createElement("th");th.scope="col";th.textContent=label;header.append(th);}head.append(header);table.append(head);
    const body=document.createElement("tbody");
    for(const check of cycle.checks || []){
      const row=document.createElement("tr");
      for(const value of [`${METRIC_LABEL[check.metric] || check.metric} ${check.target || ""}`,check.baseline_value || "未知",check.after_value || "未采集",VERIFICATION_RESULT[check.change] || (check.change === "not_comparable" ? "不可比较" : "未知")]){const cell=document.createElement("td");cell.textContent=value;row.append(cell);}
      body.append(row);
    }
    table.append(body);scroll.append(table);card.append(scroll);
    const refs=document.createElement("p");refs.className="environment-note";refs.textContent=`Baseline task v${cycle.baseline?.task_version || "?"} / After task v${cycle.after_task_version || "?"}；Before ${cycle.baseline?.evidence_ids?.length || 0} 条 / After ${cycle.after?.evidence_ids?.length || 0} 条客观证据。`;card.append(refs);
    if(cycle.user_observation){const note=document.createElement("p");note.textContent=`用户主观反馈（非客观证据）：${cycle.user_observation.symptom_status}；${cycle.user_observation.note || "无备注"}`;card.append(note);}
    const inScope = !state.diagnosticTarget || (cycle.target_subject === state.diagnosticTarget.subject && cycle.target_version === state.diagnosticTarget.target_version);
    const current = cycle === latest && !historical && !state.viewingHistory && inScope && cycle.status !== "superseded";
    if(current && ["baseline_ready","awaiting_after_evidence"].includes(cycle.status)){
      if(cycle.target_subject === "user_client"){
        const prompt=document.createElement("p");prompt.textContent="需要修复后验证：完成手动步骤后，请重新运行 Windows 客户端诊断脚本，并上传新的诊断快照。";
        const download=document.createElement("a");download.href="/static/scripts/client_diagnostic_windows.ps1";download.textContent="下载诊断脚本";download.setAttribute("download","client_diagnostic_windows.ps1");
        const upload=document.createElement("button");upload.type="button";upload.textContent="上传新的诊断快照";upload.addEventListener("click",()=>{const details=elements.snapshotForm.closest("details");if(details)details.open=true;elements.snapshotFile.focus();elements.snapshotFile.click();});
        card.append(prompt,download,upload);
        if(cycle.status === "baseline_ready" && state.remediationPlan?.steps?.some(s=>s.status === "completed")){
          const begin=document.createElement("button");begin.type="button";begin.textContent="开始等待新快照";
          begin.addEventListener("click",()=>verificationRequest(`/${encodeURIComponent(cycle.verification_id)}/start`,{session_id:state.sessionId}));card.append(begin);
        }
      } else if(["netpilot_host","mock_client"].includes(cycle.target_subject)){
        const start=document.createElement("button");start.type="button";start.textContent=cycle.target_subject === "mock_client" ? "开始模拟验证" : "开始验证";start.addEventListener("click",()=>verificationRequest(`/${encodeURIComponent(cycle.verification_id)}/start`,{session_id:state.sessionId}));card.append(start);
      }
    }
    if(current){
      const controls=document.createElement("div");controls.className="verification-controls";
      const select=document.createElement("select");select.setAttribute("aria-label","用户主观症状反馈");
      for(const [value,label] of [["unknown","暂不确定"],["resolved_by_user_report","我感觉已恢复"],["improved_by_user_report","好多了"],["unchanged_by_user_report","还是一样"],["worsened_by_user_report","更差了"]]){const option=document.createElement("option");option.value=value;option.textContent=label;select.append(option);}
      const note=document.createElement("textarea");note.maxLength=500;note.placeholder="可选症状备注，不填密码或密钥";note.setAttribute("aria-label","验证反馈备注");
      const save=document.createElement("button");save.type="button";save.textContent="记录主观反馈";save.addEventListener("click",()=>verificationRequest(`/${encodeURIComponent(cycle.verification_id)}/user-observation`,{session_id:state.sessionId,symptom_status:select.value,note:note.value.trim() || null}));
      controls.append(select,note,save);card.append(controls);
      if(["completed","inconclusive"].includes(cycle.status)){
        const again=document.createElement("button");again.type="button";again.textContent="重新验证（新一轮）";again.addEventListener("click",()=>verificationRequest("",{session_id:state.sessionId,reverify:true}));card.append(again);
      }
    }
    elements.verificationContent.append(card);
  }
}

async function verificationRequest(suffix, body) {
  if(!state.user || !state.sessionId || state.busy || state.viewingHistory) return;
  const epoch=state.authEpoch,sid=state.sessionId;setBusy(true);
  elements.verificationNotice.textContent="正在验证 / 保存反馈…";
  try{
    const result=await requestJSON(`/api/session/verification${suffix}`,{method:"POST",body:JSON.stringify(body)});
    if(epoch !== state.authEpoch || sid !== state.sessionId)return;
    state.verificationCycles=result.verification_cycles || [];renderVerification(state.verificationCycles);appendTurnReasoningTrace(result.reasoning_trace || []);
    applyResolution(result);
    if(result.verification_tool_calls?.length) renderTools(result.verification_tool_calls);
  }catch(error){if(epoch === state.authEpoch && sid === state.sessionId)elements.verificationNotice.textContent=error.message;}
  finally{if(epoch === state.authEpoch)setBusy(false);}
}

async function remediationRequest(url, options) {
  if (!state.user || !state.sessionId || state.busy || state.viewingHistory) return;
  const epoch=state.authEpoch, sessionId=state.sessionId;
  setBusy(true);
  try {
    const result=await requestJSON(url, options);
    if (epoch !== state.authEpoch || sessionId !== state.sessionId) return;
    state.remediationPlan=result.remediation_plan || null;
    applyResolution(result);
    state.verificationCycles=result.verification_cycles || [];
    renderVerification(state.verificationCycles);
    state.remediationReadiness=result.remediation_readiness || null;
    renderRemediationPlan(state.remediationPlan);
    appendTurnReasoningTrace(result.reasoning_trace || []);
  } catch (error) {
    if (epoch === state.authEpoch && sessionId === state.sessionId) elements.remediationStatus.textContent=error.message;
  } finally {if (epoch === state.authEpoch) setBusy(false);}
}

async function generateRemediationPlan() {
  await remediationRequest("/api/session/remediation-plan",{method:"POST",body:JSON.stringify({session_id:state.sessionId})});
}

async function sendRemediationFeedback(stepId, action, outcome="unknown", userNote="") {
  await remediationRequest(`/api/session/remediation-plan/steps/${encodeURIComponent(stepId)}`,{method:"PATCH",body:JSON.stringify({session_id:state.sessionId,action,outcome,user_note:userNote.trim() || null})});
}

async function uploadClientSnapshot(event) {
  event.preventDefault();
  if (!state.user || !state.sessionId || state.busy || state.viewingHistory || state.diagnosticTarget?.subject !== "user_client" || state.diagnosticTarget?.relationship_to_netpilot !== "remote") return;
  const file = elements.snapshotFile.files?.[0];
  if (!file || !file.name.toLowerCase().endsWith(".json") || file.size > (state.health?.client_snapshot_max_bytes || 262144)) {
    elements.snapshotStatus.textContent = "请选择符合大小限制的 .json 文件。";
    return;
  }
  const epoch = state.authEpoch, sessionId = state.sessionId;
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("file", file);
  setBusy(true);
  try {
    const result = await requestJSON("/api/session/client-snapshot", {method:"POST", body:form});
    if (state.authEpoch !== epoch || state.sessionId !== sessionId) return;
    state.clientSnapshotSummary = result.client_snapshot_summary;
    state.clientEvidence = result.client_evidence || [];
    state.remediationPlan = result.remediation_plan || null;
    applyResolution(result);
    state.verificationCycles = result.verification_cycles || [];
    elements.verificationNotice.textContent = "正在对比修复前后状态…";
    renderVerification(state.verificationCycles);
    renderRemediationPlan(state.remediationPlan);
    state.environmentProfile = result.environment_profile;
    state.diagnosticTarget = result.diagnostic_target;
    renderClientSnapshot(state.clientSnapshotSummary, state.clientEvidence);
    renderEnvironmentProfile(state.environmentProfile);
    renderDiagnosticTarget(state.diagnosticTarget);
    appendTurnReasoningTrace(result.reasoning_trace || []);
    if (!result.duplicate) renderDiagnosis(null);
    elements.snapshotFile.value = "";
    elements.snapshotStatus.textContent += result.duplicate ? " 相同快照，未重复创建证据或轨迹。" : " 上传成功，可继续提问分析。";
  } catch (error) {
    if (state.authEpoch === epoch && state.sessionId === sessionId) elements.snapshotStatus.textContent = error.message;
  } finally {
    if (state.authEpoch === epoch) setBusy(false);
  }
}

async function saveDiagnosticTarget(event) {
  event.preventDefault();
  if (!state.user || !state.sessionId || state.busy || state.viewingHistory || state.diagnosticTarget?.subject === "mock_client") return;
  if (!["user_client","netpilot_host"].includes(elements.targetSubject.value)) return;
  const epoch = state.authEpoch, sessionId = state.sessionId;
  setBusy(true);
  try {
    const target = await requestJSON("/api/session/diagnostic-target", {method:"PATCH",body:JSON.stringify({session_id:sessionId,subject:elements.targetSubject.value})});
    if (state.authEpoch !== epoch || state.sessionId !== sessionId) return;
    const changed = state.diagnosticTarget?.target_version !== target.target_version;
    state.diagnosticTarget = target;
    renderDiagnosticTarget(target);
    renderClientSnapshot(state.clientSnapshotSummary, state.clientEvidence);
    if (state.isDemo) await refreshDemoStatus();
    elements.snapshotFile.value = "";
    if (changed) { renderDiagnosis(null); renderTools([]); if (state.remediationPlan) state.remediationPlan={...state.remediationPlan,status:"superseded"};renderRemediationPlan(state.remediationPlan); state.verificationCycles=state.verificationCycles.map(c=>["baseline_ready","awaiting_after_evidence","verifying"].includes(c.status)?{...c,status:"superseded"}:c);renderVerification(state.verificationCycles); }
    if(changed){applyResolution({resolution:{state:"diagnosing",reason_summary:"诊断对象已切换，旧处理状态不沿用。"}});await refreshResolution();}
    elements.targetStatus.textContent = "诊断对象已保存；其他对象的旧检测仅保留于历史，不参与当前结论。";
  } catch (error) {
    if (state.authEpoch === epoch) elements.targetStatus.textContent = error.message;
  } finally {
    if (state.authEpoch === epoch) setBusy(false);
  }
}

async function createSession({ announce = true, restore = false } = {}) {
  if (!state.user || state.busy) return;
  const authEpoch = state.authEpoch;
  setBusy(true, "正在创建新会话…");
  try {
    let session = null;
    const reference = restore ? window.location?.hash.match(/^#session=([0-9a-f-]{36})$/i)?.[1] : null;
    if (reference) {
      // Server ownership checks are authoritative, including after account changes.
      try {
        session = await requestJSON(`/api/session/${encodeURIComponent(reference)}`, {cache: "no-store"});
      } catch (error) {
        if (error.status !== 404) throw error;
      }
      if (state.authEpoch !== authEpoch) return;
    }
    if (!session) session = await requestJSON("/api/session", { method: "POST" });
    if (state.authEpoch !== authEpoch) return;
    state.sessionId = session.session_id;
    state.isDemo = Boolean(session.is_demo);
    state.demoScenarioId = session.demo_scenario_id || null;
    state.environmentProfile = session.environment_profile || null;
    state.diagnosticTarget = session.diagnostic_target || null;
    state.clientSnapshotSummary = session.client_snapshot_summary || null;
    state.clientEvidence = session.client_evidence || [];
    state.remediationPlan = session.remediation_plan || null;
    state.verificationCycles = session.verification_cycles || [];
    state.resolution = session.resolution || null;state.resolutionTransitions = session.resolution_transitions || [];
    state.escalationPackages=session.escalation_packages || [];
    state.remediationReadiness = session.remediation_readiness || null;
    window.history?.replaceState(null, "", `#session=${encodeURIComponent(session.session_id)}`);
    elements.sessionLabel.textContent = `会话 ${session.session_id.slice(0, 8)}`;
    resetConversation();
    if (!state.isDemo) await uploadBrowserEnvironment(authEpoch, session.session_id);
    if (state.isDemo) await refreshDemoStatus();
    else clearDemoSessionUI();
    if (state.authEpoch !== authEpoch) return;
    elements.interactionNote.textContent = state.health?.llm_configured
      ? "会话已就绪。Enter 发送，Shift + Enter 换行。"
      : "会话已创建，但 TJU LLM 尚未配置。";
    if (announce) elements.messageInput.focus();
  } catch (error) {
    if (state.authEpoch !== authEpoch) return;
    state.sessionId = null;
    elements.sessionLabel.textContent = "会话创建失败";
    appendMessage("error", error.message);
    elements.interactionNote.textContent = error.message;
  } finally {
    if (state.authEpoch === authEpoch) setBusy(false);
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
  const summary = String(diagnosis.summary || "").replace(/\[\[cite:[^\]\n]*(?:\]\]|$)/g, "").replace(/\s+/g, " ").trim();
  const preview = summary.length > 180 ? `${summary.slice(0, 180)}…` : summary;
  const evidenceMeta = `${diagnosis.tool_rounds} 个工具轮次 · ${evidenceCount} 条结构化证据`;
  elements.diagnosisSummary.textContent = preview ? `${preview}（${evidenceMeta}）` : evidenceMeta;
}

function renderMetrics(metrics) {
  elements.metricsDebug.textContent = metrics ? JSON.stringify({
    response_mode: metrics.response_mode,
    fallback_reason: metrics.fallback_reason,
    rag_calls: metrics.rag_calls,
    knowledge_finalization_attempts: metrics.knowledge_finalization_attempts,
    knowledge_finalization_failure_kind: metrics.knowledge_finalization_failure_kind,
    reasoning_trace_steps: metrics.reasoning_trace_steps,
    reasoning_summary_llm_used: metrics.reasoning_summary_llm_used,
  }, null, 2) : "暂无调试指标。";
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

function renderReasoningTrace(steps) {
  elements.reasoningTrace.replaceChildren();
  elements.reasoningCount.textContent = String(steps?.length || 0);
  if (!steps?.length) {
    elements.reasoningTrace.append(emptyState("RT", "本记录没有诊断思路；不会根据旧答案补造轨迹。"));
    return;
  }
  const phases = { intent: "识别", planning: "计划", evidence: "证据", hypothesis: "假设", decision: "决策", finalization: "结论", state_change: "状态变化", fallback: "兜底" };
  const list = document.createElement("ol");
  list.className = "reasoning-list";
  for (const step of steps) {
    const item = document.createElement("li");
    const heading = document.createElement("div");
    heading.className = "reasoning-heading";
    const phase = document.createElement("span");
    phase.className = "reasoning-phase";
    phase.textContent = phases[step.phase] || "诊断";
    const title = document.createElement("strong");
    title.textContent = step.title;
    heading.append(phase, title);
    const summary = document.createElement("p");
    summary.textContent = step.summary;
    item.append(heading, summary);
    if (step.evidence_ids?.length) {
      const meta = document.createElement("small");
      meta.textContent = `关联证据：${step.evidence_ids.length}`;
      item.append(meta);
    }
    list.append(item);
  }
  elements.reasoningTrace.append(list);
}

function appendTurnReasoningTrace(steps) {
  const known = new Map(state.reasoningTrace.map((step) => [step.step_index, step]));
  for (const step of steps || []) known.set(step.step_index, step);
  const limit = Math.max(1, Math.min(200, Number(state.health?.reasoning_trace_max_steps || 50)));
  const ordered = [...known.values()].sort((a, b) => a.step_index - b.step_index);
  const recentCount = Math.max(1, Math.floor(limit / 2));
  const recent = ordered.slice(-recentCount);
  const priority = { planning:0, evidence:1, intent:2, hypothesis:2, decision:2, finalization:2, state_change:3, fallback:3 };
  const older = ordered.slice(0, -recentCount).sort((a, b) => (priority[b.phase] - priority[a.phase]) || (b.step_index - a.step_index));
  state.reasoningTrace = [...recent, ...older.slice(0, limit - recent.length)].sort((a, b) => a.step_index - b.step_index);
  renderReasoningTrace(state.reasoningTrace);
}

function renderTools(tools) {
  elements.timelineCount.textContent = String(tools?.length || 0);
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
    meta.textContent = `第 ${tool.round} 轮 · ${tool.duration_ms} ms · ${tool.tool_call_id}${tool.purpose === "verification" ? " · Purpose: Verification" : ""}`;
    const location = document.createElement("small");
    location.className = "tool-execution-context";
    location.textContent = tool.execution_scope === "target_neutral" ? "对象无关的知识参考（非设备检测）" : `诊断对象：${TARGET_LABELS[tool.target_subject] || TARGET_LABELS.unknown} v${tool.target_version || 1} · 执行位置：${EXECUTION_LABELS[tool.execution_context] || EXECUTION_LABELS.unavailable}`;
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
    item.append(heading, meta, location, summary, details);
    list.append(item);
  }
  elements.toolTimeline.append(list);
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

function renderHistoryItems(items) {
  elements.historyList.replaceChildren();
  if (!items?.length) {
    elements.historyList.append(emptyState("DB", "还没有已保存的诊断记录。"));
    return;
  }
  const list = document.createElement("ol");
  list.className = "history-list";
  elements.historyList.append(list);
  for (const item of items || []) {
    const row = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.recordId = item.record_id;
    const question = document.createElement("strong");
    question.textContent = (item.is_demo ? "[Demo] " : "") + item.user_message;
    const meta = document.createElement("span");
    const issue = ISSUE_LABELS[item.primary_issue] || item.primary_issue;
    const confidence = CONFIDENCE_LABELS[item.confidence] || item.confidence;
    meta.textContent = `${formatHistoryTime(item.updated_at)} · ${Number(item.turn_count || 1)} 轮对话 · ${issue} · 置信度 ${confidence} · 状态：${RESOLUTION_LABELS[item.resolution?.state] || "诊断中"}`;
    const metrics = document.createElement("small");
    metrics.textContent = `${Number(item.metrics?.token_usage?.total_tokens || 0)} Token · ${Number(item.metrics?.tool_calls || 0)} 次 Tool · ${formatDuration(item.metrics?.llm_duration_ms)}`;
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

function updateHistoryControls() {
  const page = state.historyPages[state.historyPageIndex];
  const disabled = state.historyLoading || state.busy || !state.user;
  elements.historyPrevious.disabled = disabled || state.historyPageIndex === 0;
  elements.historyNext.disabled = disabled || !page?.nextCursor;
  elements.historyPageLabel.textContent = `第 ${state.historyPageIndex + 1} 页`;
  elements.historyList.setAttribute("aria-busy", String(state.historyLoading));
}

function resetHistoryPagination() {
  state.historyGeneration += 1;
  state.historyPageIndex = 0;
  state.historyPages = [];
  state.historyLoading = false;
  updateHistoryControls();
}

async function loadHistory({ pageIndex = 0, refresh = true } = {}) {
  if (!state.user) return;
  if (refresh) resetHistoryPagination();
  else if (state.historyLoading || pageIndex < 0) return;
  const authEpoch = state.authEpoch;
  const generation = state.historyGeneration;
  if (!state.health?.history_ready) {
    resetHistoryPagination();
    renderHistoryItems([]);
    const message = elements.historyList.querySelector(".empty-state p");
    if (message) message.textContent = "诊断历史未启用或暂时不可用。";
    return;
  }
  const cached = state.historyPages[pageIndex];
  if (cached) {
    state.historyPageIndex = pageIndex;
    renderHistoryItems(cached.items);
    updateHistoryControls();
    return;
  }
  const cursor = pageIndex === 0 ? null : state.historyPages[pageIndex - 1]?.nextCursor;
  if (pageIndex > 0 && !cursor) return;
  const query = cursor
    ? `/api/diagnoses?limit=10&cursor=${encodeURIComponent(cursor)}`
    : "/api/diagnoses?limit=10";
  state.historyLoading = true;
  updateHistoryControls();
  try {
    const response = await requestJSON(query);
    if (state.authEpoch !== authEpoch || state.historyGeneration !== generation) return;
    state.historyPages[pageIndex] = {
      requestCursor: cursor, items: response.items, nextCursor: response.next_cursor,
    };
    state.historyPageIndex = pageIndex;
    renderHistoryItems(response.items);
  } catch (error) {
    if (state.authEpoch !== authEpoch || state.historyGeneration !== generation) return;
    if (!state.historyPages.length) {
      elements.historyList.replaceChildren(emptyState("!", error.message));
    }
  } finally {
    if (state.authEpoch === authEpoch && state.historyGeneration === generation) {
      state.historyLoading = false;
      updateHistoryControls();
    }
  }
}

async function loadDiagnosisRecord(recordId) {
  if (!recordId || !state.user || state.busy) return;
  const authEpoch = state.authEpoch;
  setBusy(true, "正在读取历史诊断…");
  try {
    const record = await requestJSON(`/api/diagnoses/${encodeURIComponent(recordId)}`);
    if (state.authEpoch !== authEpoch) return;
    state.viewingHistory = true;
    renderEnvironmentProfile(record.environment_profile, { historical: true });
    renderDiagnosticTarget(record.diagnostic_target, {historical:true});
    renderRemediationPlan(record.remediation_plan,{historical:true});
    renderVerification(record.verification_cycles || [],{historical:true});
    renderResolution(record.resolution,record.resolution_transitions || [],{historical:true,target:record.diagnostic_target});
    renderEscalation(record.escalation_packages || [],{historical:true,sessionId:record.session_id});
    renderClientSnapshot(record.client_snapshot_summary, record.client_evidence || [], {historical:true, target:record.diagnostic_target});
    elements.snapshotFile.value = "";
    elements.conversation.replaceChildren();
    for (const turn of record.conversation_turns || []) {
      appendMessage("user", turn.user_message);
      appendMessage("assistant", turn.assistant_answer, record.sources);
    }
    renderDiagnosis(record.diagnosis);
    renderMetrics(record.metrics);
    renderTools(record.tool_calls);
    elements.timelineSection.open = false;
    renderReasoningTrace(record.reasoning_trace);
    elements.reasoningSection.open = false;
    setReportRecord(record.record_id);
    const legacyNote = record.conversation_complete === false
      ? "该记录创建于完整会话持久化功能启用之前，仅保留部分对话内容。"
      : "";
    elements.interactionNote.textContent = `${legacyNote}正在查看最近更新于 ${formatHistoryTime(record.updated_at)} 的历史快照，共 ${Number(record.turn_count || 1)} 轮；这不会恢复历史会话。`;
  } catch (error) {
    if (state.authEpoch === authEpoch) elements.interactionNote.textContent = error.message;
  } finally {
    if (state.authEpoch === authEpoch) setBusy(false);
  }
}

async function submitChat(event) {
  event.preventDefault();
  const message = elements.messageInput.value.trim();
  if (!message || !state.user || !state.sessionId || state.busy) return;
  const authEpoch = state.authEpoch;
  state.viewingHistory = false;
  renderEnvironmentProfile(state.environmentProfile);
  const userMessage = appendMessage("user", "消息已发送，正在进行隐私处理…");
  renderDiagnosticTarget(state.diagnosticTarget);
  renderClientSnapshot(state.clientSnapshotSummary, state.clientEvidence);
  renderRemediationPlan(state.remediationPlan);
  const streamedAnswer = appendMessage("assistant", "");
  streamedAnswer.classList.add("is-streaming");
  elements.messageInput.value = "";
  setBusy(true, "已连接流式诊断，Agent 正在收集证据…");
  try {
    let response = null;
    await requestSSE(
      "/api/chat/stream",
      {
        method: "POST",
        body: JSON.stringify({ session_id: state.sessionId, message }),
      },
      async (eventName, data) => {
        if (state.authEpoch !== authEpoch) return;
        if (eventName === "start") {
          elements.interactionNote.textContent = "流式连接已建立，正在执行诊断。";
        } else if (eventName === "delta") {
          streamedAnswer.textContent += String(data.text || "");
          elements.conversation.scrollTop = elements.conversation.scrollHeight;
        } else if (eventName === "complete") {
          response = data.response;
        }
      },
    );
    if (state.authEpoch !== authEpoch) return;
    if (!response) throw new Error("流式响应缺少完整诊断结果。");
    userMessage.textContent = response.redacted_user_message || "消息已处理（原文不在此展示）";
    if (response.environment_profile) state.environmentProfile = response.environment_profile;
    if (response.diagnostic_target) state.diagnosticTarget = response.diagnostic_target;
    state.clientSnapshotSummary = response.client_snapshot_summary || null;
    state.clientEvidence = response.client_evidence || [];
    state.remediationPlan = response.remediation_plan || null;
    state.verificationCycles = response.verification_cycles || [];
    applyResolution(response);
    renderVerification(state.verificationCycles);
    state.remediationReadiness = response.remediation_readiness || null;
    renderRemediationPlan(state.remediationPlan);
    renderClientSnapshot(state.clientSnapshotSummary, state.clientEvidence);
    renderDiagnosticTarget(state.diagnosticTarget);
    renderEnvironmentProfile(state.environmentProfile);
    renderAssistantMarkdown(streamedAnswer, response.answer, response.sources);
    renderDiagnosis(response.diagnosis);
    renderMetrics(response.metrics);
    if (state.isDemo) await refreshDemoStatus();
    renderTools(response.tool_calls);
    appendTurnReasoningTrace(response.reasoning_trace);
    setReportRecord(response.record_id);
    await loadHistory();
    if (state.authEpoch !== authEpoch) return;
    elements.interactionNote.textContent = "诊断完成。你可以继续追问或新建会话。";
  } catch (error) {
    if (state.authEpoch !== authEpoch) return;
    if (!streamedAnswer.textContent) streamedAnswer.textContent = "本次回答未能完成。";
    appendMessage("error", error.message);
    elements.interactionNote.textContent = error.message;
    if (error.message.includes("会话不存在")) state.sessionId = null;
  } finally {
    if (state.authEpoch === authEpoch) {
      setBusy(false);
      elements.messageInput.focus();
    }
  }
}

function formatReportPreview(report) {
  const diagnosis = report.diagnosis || {};
  const metrics = report.metrics || {};
  const usage = metrics.token_usage || {};
  const snapshot = report.client_snapshot_summary;
  const plan = report.remediation_plan;
  const lines = [
    report.title || "TJU NetPilot 故障诊断报告",
    `最终处理状态：${RESOLUTION_LABELS[report.resolution?.state] || "诊断中"}；${report.resolution?.reason_summary || "尚未记录闭环结论"}`,
    `客观复核：${report.resolution?.objective_result || "unknown"}；用户确认（主观）：${report.resolution?.user_confirmation || "unknown"}；仅建议人工处理，不提交外部工单。`,
    ...(report.verification_cycles || []).flatMap(c=>[`修复前后验证 #${c.verification_sequence}：${VERIFICATION_RESULT[c.result] || c.result} · ${c.status}；改善不等于故障解决。`,...(c.checks || []).map(k=>`${METRIC_LABEL[k.metric] || k.metric} ${k.target || ""}：${k.baseline_value || "未知"} → ${k.after_value || "未采集"}（${k.change}）`),c.result_summary || "",c.user_observation ? `用户主观反馈：${c.user_observation.symptom_status} ${c.user_observation.note || ""}` : ""]),
    ...(plan ? [`修复计划 v${plan.plan_version}：${REMEDIATION_STATUS[plan.status]}；仅用户手动操作，不代表故障已解决。`,...(plan.steps || []).flatMap(step=>[`${step.order}. ${step.title} · ${step.risk} · ${STEP_STATUS[step.status]} · ${STEP_OUTCOME[step.outcome]}`,`理由：${step.rationale}`,`操作：${step.instructions.join("；")}`,`验证：${step.verification}`,`回滚：${step.rollback_instructions.join("；")}`,`备注：${step.user_note || "无"}`])] : []),
    ...(snapshot ? [`客户端诊断快照：#${snapshot.snapshot_sequence}，${formatHistoryTime(snapshot.generated_at)}，${snapshot.stale || Date.now() > Date.parse(snapshot.expires_at) ? "已过期（历史）" : snapshot.clock_skew_suspected ? "疑似时钟偏差" : "采集时点证据"}，非远程执行。`, ...(report.client_evidence || []).map(item => `${item.superseded ? "历史归档" : "采集证据"}：${item.summary}`)] : []),
    `用户环境：${formatEnvironmentSummary(report.environment_profile)}`,
    `诊断对象：${TARGET_LABELS[report.diagnostic_target?.subject] || TARGET_LABELS.unknown}；执行位置：${EXECUTION_LABELS[report.diagnostic_target?.execution_context] || EXECUTION_LABELS.unavailable}`,
    "",
    `报告 ID：${report.report_id}`,
    `Session ID：${report.session_id}`,
    `创建时间：${formatHistoryTime(report.created_at)}`,
    `最近更新时间：${formatHistoryTime(report.updated_at)}`,
    `对话轮数：${Number(report.turn_count || 1)}`,
    `主要问题：${ISSUE_LABELS[diagnosis.primary_issue] || diagnosis.primary_issue || "尚未确定"}`,
    `置信度：${CONFIDENCE_LABELS[diagnosis.confidence] || diagnosis.confidence || "未知"}`,
    "",
    "用户问题",
    String(report.question || ""),
    "",
    "最近一轮用户消息",
    String(report.latest_user_message || report.question || ""),
    "",
    "诊断结论",
    String(report.conclusion || ""),
    "",
    "执行指标",
    "以下为 Session 累计指标，含历史对象，不代表当前对象已检测。",
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
  lines.push("", "诊断思路");
  lines.push(...(report.reasoning_trace?.length
    ? report.reasoning_trace.map((step, index) => `${index + 1}. ${step.title}：${step.summary}`)
    : ["- 本记录未保存诊断思路。"]));
  lines.push("", "建议操作");
  const recommendations = diagnosis.recommendations || [];
  lines.push(...(recommendations.length ? recommendations.map((item) => `- ${item}`) : ["- 无额外建议。"]));
  lines.push("", "结论限制");
  const limitations = diagnosis.limitations || [];
  lines.push(...(limitations.length ? limitations.map((item) => `- ${item}`) : ["- 无额外限制。"]));
  lines.push("", "参考知识");
  const sources = report.sources || [];
  lines.push(...(sources.length ? sources.map((source) => `- ${source.title}：${source.source}`) : ["- 本次报告没有使用知识库来源。"]));
  lines.push("", "会话记录");
  if (report.conversation_complete === false) {
    lines.push("该记录创建于完整会话持久化功能启用之前，仅保留部分对话内容。");
  }
  for (const turn of report.conversation_turns || []) {
    lines.push("", `Turn ${turn.turn_index}`, "用户：", turn.user_message,
      "诊断助手：", turn.assistant_answer);
  }
  return lines.join("\n");
}

async function previewReport() {
  if (!state.user || !state.activeRecordId || state.busy) return;
  const authEpoch = state.authEpoch;
  setBusy(true, "正在生成故障报告预览…");
  try {
    const recordId = encodeURIComponent(state.activeRecordId);
    const report = await requestJSON(`/api/diagnoses/${recordId}/report`);
    if (state.authEpoch !== authEpoch) return;
    elements.reportContent.textContent = formatReportPreview(report);
    document.querySelector("#report-title").textContent="诊断报告预览";
    elements.reportDialog.showModal();
    elements.interactionNote.textContent = "报告已根据保存的诊断证据生成，未额外调用模型。";
  } catch (error) {
    if (state.authEpoch === authEpoch) elements.interactionNote.textContent = error.message;
  } finally {
    if (state.authEpoch === authEpoch) setBusy(false);
  }
}

async function downloadReport(format) {
  if (!state.user || !state.activeRecordId || state.busy) return;
  const authEpoch = state.authEpoch;
  setBusy(true, `正在准备 ${format === "markdown" ? "Markdown" : "JSON"} 报告…`);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 30000);
  try {
    const recordId = encodeURIComponent(state.activeRecordId);
    const exportUrl = `/api/diagnoses/${recordId}/export?format=${format}`;
    const response = await fetch(exportUrl, {
      credentials: "same-origin",
      headers: { Accept: format === "markdown" ? "text/markdown" : "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) {
      let detail = `报告导出失败（HTTP ${response.status}）`;
      try {
        const body = await response.json();
        detail = apiDetail(body, detail);
      } catch (_error) {
        // Keep the bounded generic error when the server did not return JSON.
      }
      if (response.status === 401 && state.authEpoch === authEpoch) {
        showAuthGate("登录已过期，请重新登录。");
      }
      throw new ApiError(detail, response.status);
    }
    if (state.authEpoch !== authEpoch) return;
    await response.body?.cancel();
    const link = document.createElement("a");
    link.href = exportUrl;
    link.download = `netpilot-diagnosis-${state.activeRecordId}.${format === "markdown" ? "md" : "json"}`;
    document.body.append(link);
    link.click();
    link.remove();
    elements.interactionNote.textContent = `${format === "markdown" ? "Markdown" : "JSON"} 报告已开始下载。`;
  } catch (error) {
    if (state.authEpoch === authEpoch) {
      elements.interactionNote.textContent = error.name === "AbortError" ? "报告导出超时，请稍后重试。" : error.message;
    }
  } finally {
    window.clearTimeout(timeout);
    if (state.authEpoch === authEpoch) setBusy(false);
  }
}

async function loadScenarios() {
  if (!state.user || state.health?.tool_mode !== "mock") return;
  const authEpoch = state.authEpoch;
  try {
    const response = await requestJSON("/api/scenarios");
    if (state.authEpoch !== authEpoch) return;
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
    if (state.authEpoch !== authEpoch) return;
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
  const authEpoch = state.authEpoch;
  const response = await requestJSON(`/api/scenarios/${encodeURIComponent(scenario)}`, {
    method: "POST",
  });
  if (state.authEpoch !== authEpoch) return;
  state.sessionId = response.session_id;
  state.environmentProfile = response.environment_profile || null;
  state.diagnosticTarget = response.diagnostic_target || null;
  state.clientSnapshotSummary = null;
  state.clientEvidence = [];
  state.remediationPlan = null;
  window.history?.replaceState(null, "", `#session=${encodeURIComponent(response.session_id)}`);
  state.verificationCycles = [];
  elements.sessionLabel.textContent = `会话 ${response.session_id.slice(0, 8)}`;
  state.resolution = null;state.resolutionTransitions = [];
  state.escalationPackages=[];
  elements.scenarioSelect.value = response.current;
  renderScenarioDescription(response.current, true);
  resetConversation();
  appendMessage("assistant", `已切换到“${elements.scenarioSelect.selectedOptions[0].textContent}”测试场景。`);
  await uploadBrowserEnvironment(authEpoch, response.session_id);
  if (state.authEpoch !== authEpoch) return;
  elements.interactionNote.textContent = "场景切换完成，旧会话已清理。";
}

async function switchScenario() {
  const scenario = elements.scenarioSelect.value;
  if (!scenario || !state.user || state.busy || elements.scenarioSelect.dataset.enabled !== "true") return;
  const authEpoch = state.authEpoch;
  setBusy(true, "正在切换 Mock 场景并重置会话…");
  try {
    await activateScenario(scenario);
  } catch (error) {
    if (state.authEpoch === authEpoch) {
      appendMessage("error", error.message);
      elements.interactionNote.textContent = error.message;
    }
  } finally {
    if (state.authEpoch === authEpoch) setBusy(false);
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
  if (!state.user || state.busy || elements.customScenarioNew.dataset.available !== "true") return;
  elements.scenarioForm.reset();
  elements.scenarioFormStatus.textContent = "";
  syncCustomBehaviorFields();
  elements.scenarioDialog.showModal();
  elements.customScenarioName.focus();
}

async function createCustomScenario(event) {
  event.preventDefault();
  if (!state.user || state.busy || !elements.scenarioForm.reportValidity()) return;
  const authEpoch = state.authEpoch;
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
    if (state.authEpoch !== authEpoch) return;
    await loadScenarios();
    if (state.authEpoch !== authEpoch) return;
    elements.scenarioSelect.value = created.name;
    await activateScenario(created.name);
    elements.scenarioDialog.close();
  } catch (error) {
    if (state.authEpoch === authEpoch) {
      elements.scenarioFormStatus.textContent = error.message;
      elements.interactionNote.textContent = error.message;
    }
  } finally {
    if (state.authEpoch === authEpoch) setBusy(false);
  }
}

async function deleteCurrentCustomScenario() {
  const scenario = state.scenarios.find((item) => item.name === elements.scenarioSelect.value);
  if (!scenario || scenario.kind !== "custom" || !state.user || state.busy) return;
  const authEpoch = state.authEpoch;
  setBusy(true, "正在删除自定义 Mock 场景…");
  try {
    const response = await requestJSON(
      `/api/scenarios/custom/${encodeURIComponent(scenario.name)}`,
      { method: "DELETE" },
    );
    if (state.authEpoch !== authEpoch) return;
    if (response.session_id) {
      state.sessionId = response.session_id;
      state.environmentProfile = response.environment_profile || null;
      state.diagnosticTarget = response.diagnostic_target || null;
      state.clientSnapshotSummary = null;
      state.clientEvidence = [];
      state.remediationPlan = null;
      state.verificationCycles = [];
      state.resolution = null;state.resolutionTransitions = [];
      state.escalationPackages=[];
      window.history?.replaceState(null, "", `#session=${encodeURIComponent(response.session_id)}`);
      elements.sessionLabel.textContent = `会话 ${response.session_id.slice(0, 8)}`;
      resetConversation();
      await uploadBrowserEnvironment(authEpoch, response.session_id);
      if (state.authEpoch !== authEpoch) return;
    }
    await loadScenarios();
    if (state.authEpoch !== authEpoch) return;
    appendMessage("assistant", `已删除自定义场景“${scenario.label}”，当前恢复为内置健康场景。`);
    elements.interactionNote.textContent = "自定义场景已删除，旧会话已清理。";
  } catch (error) {
    if (state.authEpoch === authEpoch) elements.interactionNote.textContent = error.message;
  } finally {
    if (state.authEpoch === authEpoch) setBusy(false);
  }
}

async function initialize() {
  try {
    const user = await requestJSON("/api/auth/me");
    await enterAuthenticated(user);
  } catch (error) {
    showAuthGate(error.status === 401 ? "请先登录或注册。" : error.message);
    if (error.status !== 401) renderHealthError(error);
  }
}

elements.authLoginTab.addEventListener("click", () => setAuthMode("login"));
elements.authRegisterTab.addEventListener("click", () => setAuthMode("register"));
elements.authForm.addEventListener("submit", submitAuth);
elements.logoutButton.addEventListener("click", logout);
elements.changePasswordOpen.addEventListener("click", openPasswordDialog);
elements.passwordForm.addEventListener("submit", submitPasswordChange);
elements.passwordCancel.addEventListener("click", () => elements.passwordDialog.close());
elements.passwordDialogClose.addEventListener("click", () => elements.passwordDialog.close());
elements.myHistory.addEventListener("click", async () => {
  elements.accountMenu.open = false;
  const authEpoch = state.authEpoch;
  await loadHistory();
  if (state.authEpoch === authEpoch) {
    elements.myHistoryCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});
elements.chatForm.addEventListener("submit", submitChat);
elements.targetForm.addEventListener("submit", saveDiagnosticTarget);
elements.environmentForm.addEventListener("submit", saveEnvironment);
elements.snapshotForm.addEventListener("submit", uploadClientSnapshot);
elements.remediationGenerate.addEventListener("click", generateRemediationPlan);
window.setInterval?.(() => {
  if (state.user && state.clientSnapshotSummary && !state.viewingHistory && !state.busy) {
    renderClientSnapshot(state.clientSnapshotSummary, state.clientEvidence);
    const snapshot = state.clientSnapshotSummary;
    if (state.verificationCycles.at(-1)?.status !== "awaiting_after_evidence" && state.remediationPlan?.readiness === "ready" && state.remediationPlan.status !== "superseded" && state.remediationPlan.based_on_snapshot_id === snapshot.snapshot_id && (snapshot.stale || snapshot.clock_skew_suspected || Date.now() > Date.parse(snapshot.expires_at))) {
      state.remediationPlan = {...state.remediationPlan,status:"superseded"};
      renderRemediationPlan(state.remediationPlan);
    }
  }
}, 30000);
elements.environmentForm.addEventListener("change", (event) => {
  if (event.target.name) state.environmentTouched.add(event.target.name);
});
elements.environmentScope.addEventListener("change", () => {
  elements.environmentServiceLabel.hidden = elements.environmentScope.value !== "single_service";
});
elements.newSession.addEventListener("click", () => createSession());
elements.escalationGenerate.addEventListener("click",generateEscalation);
elements.scenarioSelect.addEventListener("change", switchScenario);
elements.customScenarioNew.addEventListener("click", openCustomScenarioDialog);
elements.customScenarioDelete.addEventListener("click", deleteCurrentCustomScenario);
elements.scenarioForm.addEventListener("submit", createCustomScenario);
elements.scenarioDialogClose.addEventListener("click", () => elements.scenarioDialog.close());
elements.scenarioFormCancel.addEventListener("click", () => elements.scenarioDialog.close());
elements.scenarioPingReachable.addEventListener("change", syncCustomBehaviorFields);
elements.scenarioHttpReachable.addEventListener("change", syncCustomBehaviorFields);
elements.historyRefresh.addEventListener("click", () => loadHistory());
elements.historyPrevious.addEventListener("click", () => loadHistory({
  pageIndex: state.historyPageIndex - 1, refresh: false,
}));
elements.historyNext.addEventListener("click", () => loadHistory({
  pageIndex: state.historyPageIndex + 1, refresh: false,
}));
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

function clearDemoSessionUI() {
  const reset=document.querySelector("#demo-reset");if(reset)reset.disabled=true;
  document.querySelector("#demo-fixtures")?.replaceChildren();
  const status=document.querySelector("#demo-status");if(status)status.textContent="请选择场景并创建独立的 Demo Session。";
  const banner=document.querySelector("#demo-banner");if(banner)banner.textContent="网络状态来自 Mock / Fixture，不代表现场真实网络。";
}

async function loadDemoScenarios() {
  const panel=document.querySelector("#demo-controls");
  if(!panel)return;
  panel.hidden=!state.health?.demo_mode;
  if(panel.hidden)return;
  const epoch=state.authEpoch;
  const data=await requestJSON("/api/demo/scenarios");
  if(epoch!==state.authEpoch)return;
  state.demoScenarios=data.scenarios || [];
  const select=document.querySelector("#demo-scenario-select");select.replaceChildren();
  for(const item of state.demoScenarios){const option=document.createElement("option");option.value=item.scenario_id;option.textContent=item.title;select.append(option);}
  if(state.demoScenarioId)select.value=state.demoScenarioId;
}

function applyDemoSession(session,{reset=false}={}) {
  state.sessionId=session.session_id;state.isDemo=Boolean(session.is_demo);state.demoScenarioId=session.demo_scenario_id;
  state.environmentProfile=session.environment_profile;state.diagnosticTarget=session.diagnostic_target;
  state.clientSnapshotSummary=session.client_snapshot_summary || null;state.clientEvidence=session.client_evidence || [];
  state.remediationPlan=session.remediation_plan || null;state.remediationReadiness=session.remediation_readiness || null;
  state.verificationCycles=session.verification_cycles || [];state.escalationPackages=session.escalation_packages || [];
  state.resolution=session.resolution;state.resolutionTransitions=session.resolution_transitions || [];
  state.viewingHistory=false;
  window.history?.replaceState(null,"",`#session=${encodeURIComponent(session.session_id)}`);
  elements.sessionLabel.textContent=`Demo · ${session.session_id.slice(0,8)}`;
  if(reset){resetConversation();setReportRecord(null);renderDiagnosis(null);renderTools([]);}
  else {renderEnvironmentProfile(state.environmentProfile);renderDiagnosticTarget(state.diagnosticTarget);renderClientSnapshot(state.clientSnapshotSummary,state.clientEvidence);renderRemediationPlan(state.remediationPlan);renderVerification(state.verificationCycles);applyResolution(session);appendTurnReasoningTrace(session.reasoning_trace || []);}
}

async function refreshDemoStatus() {
  if(!state.isDemo || !state.user || state.viewingHistory)return;
  const sid=state.sessionId,epoch=state.authEpoch;
  const data=await requestJSON(`/api/demo/session/${encodeURIComponent(sid)}`);
  if(sid!==state.sessionId || epoch!==state.authEpoch)return;
  const banner=document.querySelector("#demo-banner");
  banner.textContent=data.data_source==="uploaded" ? "当前使用真实客户端诊断快照；会话仍带 Demo 标记。" : "当前为演示模式，网络状态来自 Mock / Fixture。";
  document.querySelector("#demo-reset").disabled=false;
  document.querySelector("#demo-scenario-select").value=data.demo_scenario_id;
  document.querySelector("#demo-status").textContent=`${data.demo_scenario_id} · task v${data.task_version} / target v${data.target_version} · Resolution=${data.resolution} · Verification=${data.latest_verification || "尚无"}${data.latest_verification_historical ? "（历史轮次）" : ""} · Plan v${data.latest_plan_version || 0} · Host Tool=${data.host_handler_calls} · ${data.metrics.verification_cycles} 轮验证`;
  const fixtures=document.querySelector("#demo-fixtures");fixtures.replaceChildren();
  for(const [index,id] of (data.snapshot_fixtures || []).entries()){
    const button=document.createElement("button");button.type="button";button.textContent=`加载 ${index===0 ? "Before" : `After ${index}`} 快照`;
    button.dataset.available=String(!data.loaded_fixtures.includes(id) && index<=data.loaded_fixtures.length);
    button.disabled=state.busy || button.dataset.available!=="true";
    button.addEventListener("click",()=>{if(state.isDemo && state.sessionId===sid)demoOperation(`/api/demo/session/${encodeURIComponent(sid)}/load-snapshot/${encodeURIComponent(id)}`,{},false);});fixtures.append(button);
  }
}

async function demoOperation(url,body={},reset=true) {
  if(!state.user || state.busy)return;
  const epoch=state.authEpoch;setBusy(true);
  try {
    const session=await requestJSON(url,{method:"POST",body:JSON.stringify(body)});
    if(epoch!==state.authEpoch)return;
    applyDemoSession(session,{reset});
    await refreshDemoStatus();await loadHistory();
  } catch(error) {if(epoch===state.authEpoch)document.querySelector("#demo-status").textContent=error.message;}
  finally {if(epoch===state.authEpoch){setBusy(false);if(state.isDemo)await refreshDemoStatus();}}
}

document.querySelector("#demo-create")?.addEventListener("click",()=>{
  const id=document.querySelector("#demo-scenario-select").value;
  demoOperation(state.isDemo ? `/api/demo/session/${encodeURIComponent(state.sessionId)}/scenario/${encodeURIComponent(id)}` : "/api/demo/session",{scenario_id:id});
});
document.querySelector("#demo-reset")?.addEventListener("click",()=>{if(state.isDemo)demoOperation(`/api/demo/session/${encodeURIComponent(state.sessionId)}/reset`);});
document.querySelector("#demo-refresh")?.addEventListener("click",()=>refreshDemoStatus().catch(error=>{document.querySelector("#demo-status").textContent=error.message;}));
document.querySelector("#demo-fill-prompt")?.addEventListener("click",()=>{
  const id=document.querySelector("#demo-scenario-select").value;
  const scenario=state.demoScenarios?.find(item=>item.scenario_id===id);
  if(scenario){elements.messageInput.value=scenario.recommended_input;elements.messageInput.focus();}
});

initialize();
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    showAuthGate("正在验证登录状态…");
    initialize();
  }
});
