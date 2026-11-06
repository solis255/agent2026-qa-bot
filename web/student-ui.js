"use strict";

// Presentation only. Diagnostic decisions and workflow state remain in app.js/API.
function studentEnvironmentSummary(profile) {
  const p = profile || {};
  const os = ENVIRONMENT_OS[p.os_family];
  const parts = [];
  if (os && p.os_family !== "unknown") parts.push(os + (p.os_version ? ` ${p.os_version}` : ""));
  if (p.network_access && p.network_access !== "unknown" && ENVIRONMENT_ACCESS[p.network_access]) parts.push(ENVIRONMENT_ACCESS[p.network_access]);
  else if (parts.length) parts.push("网络类型未确认");
  if (p.affected_scope && p.affected_scope !== "unknown" && ENVIRONMENT_SCOPE[p.affected_scope]) parts.push(ENVIRONMENT_SCOPE[p.affected_scope]);
  return parts.join(" · ") || "环境待确认";
}

function displayedCase() {
  return state.viewingHistory ? state.historyRecord || {} : {
    environment_profile: state.environmentProfile, diagnostic_target: state.diagnosticTarget,
    client_snapshot_summary: state.clientSnapshotSummary, remediation_plan: state.remediationPlan,
    verification_cycles: state.verificationCycles, resolution: state.resolution,
  };
}

function renderDetailsSummary() {
  const data = displayedCase();
  const demo = state.viewingHistory ? data.is_demo : state.isDemo;
  document.querySelector("#case-environment").textContent = (demo ? "演示数据 · " : "") + studentEnvironmentSummary(data.environment_profile);
  const snapshot = data.client_snapshot_summary;
  const text = !snapshot ? "尚未进行" : snapshot.applicable === false || snapshot.target_version !== data.diagnostic_target?.target_version
    ? "先前设备或环境的检查结果" : snapshot.clock_skew_suspected ? "检查时间需要确认"
    : snapshot.stale || Date.now() > Date.parse(snapshot.expires_at) ? "结果已过期"
    : `✓ 已完成 · ${relativeCheckTime(snapshot.generated_at)}`;
  document.querySelector("#client-check-summary").textContent = text;
  document.querySelector("#remediation-section").hidden = !data.remediation_plan;
  document.querySelector("#verification-section").hidden = !data.verification_cycles?.length;
  document.querySelector("#history-view-banner").hidden = !state.viewingHistory;
  const demoEnabled = Boolean(state.health?.demo_mode || elements.scenarioSelect.dataset.enabled === "true");
  document.querySelector("#demo-details").hidden = !demoEnabled;
  document.querySelector("#report-details > p").hidden = Boolean(state.activeRecordId);
}

function relativeCheckTime(value) {
  const minutes = Math.floor((Date.now() - Date.parse(value)) / 60000);
  if (!Number.isFinite(minutes) || minutes < 0) return "采集时间待确认";
  return minutes < 1 ? "刚刚采集" : minutes < 60 ? `${minutes} 分钟前` : formatHistoryTime(value);
}

function renderCaseStatus() {
  renderDetailsSummary();
  const container = document.querySelector("#case-next-action");
  container.replaceChildren();
  if (!state.user || state.viewingHistory) { container.hidden = true; return; }
  const add = (text, label, callback) => {
    const row = document.createElement("div");row.className = "case-action-row";
    const summary = document.createElement("span");summary.textContent = text;row.append(summary);
    if (label) {
      const button = document.createElement("button");button.type = "button";button.className = "text-button";
      button.textContent = label;button.disabled = state.busy;
      button.addEventListener("click", () => {if (!state.busy && !state.viewingHistory && state.user) callback();});row.append(button);
    }
    container.append(row);
  };
  if (state.activeContextGroup?.isConnected) add("需要补充一个信息", "查看问题", () => {
    state.activeContextGroup?.scrollIntoView?.({block:"nearest"});state.activeContextGroup?.querySelector("button:not(:disabled)")?.focus();
  });
  const check = state.clientCheck.action;
  if (clientCheckActionCurrent(check)) add(check.mode === "recheck" ? "等待重新检查" : "需要进行网络检查", check.mode === "recheck" ? "重新检查" : "开始网络检查", openClientCheck);
  const plan = state.remediationPlan;
  const inScope = item => item && item.target_subject === state.diagnosticTarget?.subject && item.target_version === state.diagnosticTarget?.target_version;
  if (inScope(plan) && !["superseded","cancelled"].includes(plan.status) && plan.steps?.length)
    add(`已生成 ${plan.steps.length} 步修复建议`, "查看修复步骤", () => openDiagnosticDetails("remediation-section"));
  const cycle = state.verificationCycles.at(-1);
  if (inScope(cycle)) {
    if (cycle.status === "awaiting_after_evidence" && !clientCheckActionCurrent(check))
      add(state.isDemo ? "等待演示的修复后检查结果" : "等待修复后检查结果", "查看验证进度", () => openDiagnosticDetails("verification-section"));
    else if (cycle.status === "baseline_ready") add("完成修复步骤后可以验证", "查看验证", () => openDiagnosticDetails("verification-section"));
    else if (["completed","inconclusive","failed"].includes(cycle.status)) add(`修复后状态：${VERIFICATION_RESULT[cycle.result] || "暂时无法确认"}`, "查看对比", () => openDiagnosticDetails("verification-section"));
  }
  if (state.resolution?.state === "resolved") add("问题已解决", "查看处理过程", () => openDiagnosticDetails("workflow-details"));
  if (state.resolution?.state === "escalated" || state.resolution?.escalation_recommended)
    add("这个问题建议交给网络运维人员进一步处理。", "生成报修材料", async () => {openDiagnosticDetails("escalation-section");await generateEscalation();});
  container.hidden = container.childElementCount === 0;
}

function openDiagnosticDetails(section = "current-diagnosis-details") {
  if (!state.user) return;
  const dialog = document.querySelector("#diagnostic-details-dialog");
  state.detailsOpen = true;state.detailsSection = section;
  const target = document.getElementById(section) || document.querySelector("#current-diagnosis-details");
  for (let parent = target; parent && parent !== dialog; parent = parent.parentElement) {
    if (parent.tagName === "DETAILS") parent.open = true;
  }
  if (!dialog.open) dialog.showModal();
  document.querySelector("#diagnostic-details-open").setAttribute("aria-expanded", "true");
  document.querySelector("#diagnostic-details-close").focus();
  target.scrollIntoView?.({block:"nearest"});
}

function closeDiagnosticDetails() {
  const dialog = document.querySelector("#diagnostic-details-dialog");
  if (dialog.open) dialog.close();
  state.detailsOpen = false;
  document.querySelector("#diagnostic-details-open").setAttribute("aria-expanded", "false");
  if (state.user) document.querySelector("#diagnostic-details-open").focus();
}

async function openHistoryView() {
  if (!state.user || state.busy) return;
  elements.accountMenu.open = false;closeDiagnosticDetails();
  const dialog = document.querySelector("#history-dialog");
  if (!dialog.open) dialog.showModal();
  document.querySelector("#history-dialog-close").focus();
  await loadHistory();
}

function closeHistoryDialog() {
  const dialog = document.querySelector("#history-dialog");
  if (dialog.open) dialog.close();
  if (state.user) elements.accountName.focus();
}

// Retain live presentation nodes (including action listeners), never a second case state.
function preserveCurrentPresentation(note = elements.interactionNote.textContent) {
  if (state.historyPresentation) return;
  const ids = ["conversation","diagnosis-status","diagnosis-summary","token-usage","llm-duration","tool-duration","tool-count","metrics-debug","tool-timeline","timeline-count","reasoning-trace","reasoning-count"];
  const nodes = ids.map(id => {
    const el = document.getElementById(id), children = Array.from(el.childNodes), className = el.className;
    el.replaceChildren();return {id, children, className};
  });
  state.historyPresentation = {nodes, recordId:state.activeRecordId, note, scrollTop:elements.conversation.scrollTop,
    input:elements.messageInput.value, sessionLabel:elements.sessionLabel.textContent,
    escalationSessionId:state.escalationSessionId};
}

function closeHistoryView() {
  if (!state.viewingHistory || state.busy) return;
  const saved = state.historyPresentation;
  state.viewingHistory = false;state.historyRecord = null;state.historyPresentation = null;
  renderEnvironmentProfile(state.environmentProfile);renderDiagnosticTarget(state.diagnosticTarget);
  renderDiagnosticReadiness(state.diagnosticReadiness);
  renderClientSnapshot(state.clientSnapshotSummary,state.clientEvidence);
  renderRemediationPlan(state.remediationPlan);renderVerification(state.verificationCycles);
  renderResolution(state.resolution,state.resolutionTransitions);renderEscalation(state.escalationPackages);
  if (saved) {
    for (const {id,children,className} of saved.nodes) {const el=document.getElementById(id);el.replaceChildren(...children);el.className=className;}
    elements.interactionNote.textContent=saved.note;elements.messageInput.value=saved.input;
    elements.sessionLabel.textContent=saved.sessionLabel;state.escalationSessionId=saved.escalationSessionId;
    elements.conversation.scrollTop=saved.scrollTop;
    setReportRecord(saved.recordId);
  }
  document.querySelector("#client-check-launch").hidden = !clientCheckActionCurrent(state.clientCheck.action);
  setBusy(false);elements.messageInput.focus();
}

function resetStudentUI() {
  closeDiagnosticDetails();closeHistoryDialog();
  state.viewingHistory = false;
  state.historyPresentation = null;state.historyRecord = null;state.detailsSection = null;
  for (const details of document.querySelectorAll("#diagnostic-details-dialog details")) details.open = false;
  for (const id of ["technical-details","report-details","demo-details","environment-editor","target-editor","environment-source-details","advanced-client-check"]) document.getElementById(id).open = false;
  document.querySelector("#current-diagnosis-details").open = true;
  document.querySelector("#workflow-details").open = true;
}

function initStudentUI() {
  document.querySelector("#diagnostic-details-open").addEventListener("click", () => openDiagnosticDetails());
  document.querySelector("#diagnostic-details-close").addEventListener("click", closeDiagnosticDetails);
  const details = document.querySelector("#diagnostic-details-dialog");
  details.addEventListener("cancel", event => {event.preventDefault();closeDiagnosticDetails();});
  details.addEventListener("close", () => {state.detailsOpen=false;document.querySelector("#diagnostic-details-open").setAttribute("aria-expanded","false");});
  document.querySelector("#history-dialog-close").addEventListener("click", closeHistoryDialog);
  document.querySelector("#history-dialog").addEventListener("cancel", event => {event.preventDefault();closeHistoryDialog();});
  document.querySelector("#history-return").addEventListener("click", closeHistoryView);
}
