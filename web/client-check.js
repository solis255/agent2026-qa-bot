"use strict";

// All eligibility comes from the server's discriminated action. No prose parsing.
function clientCheckActionCurrent(action) {
  return Boolean(action && action.type === "client_check" && action.platform === "windows" &&
    action.collector_supported === true && action.upload_required === true &&
    !state.isDemo && isCurrentChatAction(action) &&
    state.diagnosticTarget?.subject === "user_client" && state.diagnosticTarget?.relationship_to_netpilot === "remote");
}

function closeClientCheck() {
  const dialog = document.querySelector("#client-check-dialog");
  if (typeof dialog.close === "function") dialog.close(); else dialog.removeAttribute("open");
  state.clientCheck.open = false;
  state.clientCheck.generation += 1;
  state.clientCheck.file = null;
  state.clientCheck.uploading = false;
  document.querySelector("#client-check-file").value = "";
}

function renderClientCheckAction(body, action) {
  state.clientCheck.mode = action.mode;
  state.clientCheck.declined = false;
  const group = document.createElement("div");
  group.className = "client-check-actions";
  group.dataset.actionId = action.action_id;
  group.setAttribute("role", "group"); group.setAttribute("aria-label", "网络检查选项");
  for (const [label, handler] of [[action.mode === "recheck" ? "重新检查" : "开始网络检查", openClientCheck], ["暂时不用", declineClientCheck]]) {
    const button = document.createElement("button");button.type = "button";button.className = "client-check-button";
    button.textContent = label; button.disabled = state.busy;
    button.addEventListener("click", () => { if (state.nextChatAction === action && !state.busy && clientCheckActionCurrent(action)) handler(); });
    group.append(button);
  }
  (body || appendMessage("assistant", "可以继续当前网络检查。")).after(group);
  const launch = document.querySelector("#client-check-launch");
  launch.textContent = action.mode === "recheck" ? "重新检查" : "开始网络检查";
  return group;
}

function clientCheckStep(step) {
  state.clientCheck.step = step;
  for (const panel of document.querySelectorAll("[data-client-check-step]")) panel.hidden = Number(panel.dataset.clientCheckStep) !== step;
  document.querySelector("#client-check-progress").textContent = `第 ${step} 步，共 3 步`;
  document.querySelector("#client-check-title").textContent = state.clientCheck.mode === "recheck" ? "重新检查网络" : "网络检查";
}

function openClientCheck() {
  const action = state.nextChatAction;
  if (state.busy || !clientCheckActionCurrent(action)) return;
  state.clientCheck.open = true;state.clientCheck.file = null;state.clientCheck.continuation = null;
  state.clientCheck.generation += 1;
  document.querySelector("#client-check-file").value = "";
  document.querySelector("#client-check-file-label").textContent = "尚未选择文件";
  document.querySelector("#client-check-status").textContent = "等待上传";
  document.querySelector("#client-check-historical").hidden = true;
  clientCheckStep(1);
  const dialog = document.querySelector("#client-check-dialog");
  if (typeof dialog.showModal === "function") dialog.showModal(); else dialog.setAttribute("open", "");
  const epoch = state.authEpoch, generation = state.clientCheck.generation;
  requestJSON("/api/client-tools/windows").then(data => {
    if (epoch === state.authEpoch && generation === state.clientCheck.generation && state.clientCheck.open)
      document.querySelector("#client-check-metadata").textContent = `工具版本：${data.collector_version}；结果格式：v${data.snapshot_schema_version}\n` + Object.entries(data.sha256 || {}).map(([name, digest]) => `${name}: ${digest}`).join("\n");
  }).catch(() => {});
}

function clientCheckOperation() {
  return {epoch:state.authEpoch, sid:state.sessionId, generation:state.clientCheck.generation,
    task:state.taskVersion, target:state.diagnosticTarget?.target_version};
}

function clientCheckOperationCurrent(op) {
  return op.epoch === state.authEpoch && op.sid === state.sessionId && !state.viewingHistory &&
    op.generation === state.clientCheck.generation && op.task === state.taskVersion && op.target === state.diagnosticTarget?.target_version;
}

async function refreshClientCheckConflict(error) {
  retireNextChatAction();
  appendMessage("error", error.message);
  await refreshCurrentChatAction();
}

async function declineClientCheck() {
  const action = state.nextChatAction;
  if (state.busy || !clientCheckActionCurrent(action)) return;
  const op = clientCheckOperation();setBusy(true);
  try {
    const result = await requestJSON("/api/session/client-check/decline", {method:"POST", body:JSON.stringify({
      session_id:action.session_id, action_id:action.action_id, task_version:action.task_version, target_version:action.target_version})});
    if (!clientCheckOperationCurrent(op)) return;
    state.clientCheck.declined = true;
    const body = appendMessage("assistant", result.feedback);
    renderNextChatAction(resolveNextChatAction(result), body);
  } catch (error) {
    if (clientCheckOperationCurrent(op)) {
      if (error.status === 409) await refreshClientCheckConflict(error);
      else document.querySelector("#client-check-status").textContent = "暂时无法保存选择，请稍后重试。";
    }
  } finally { if (op.epoch === state.authEpoch && op.sid === state.sessionId) setBusy(false); }
}

function applyClientCheckPayload(data) {
  if (data.task_version != null) state.taskVersion = data.task_version;
  if (data.environment_profile) state.environmentProfile = data.environment_profile;
  if (data.diagnostic_target) state.diagnosticTarget = data.diagnostic_target;
  if (state.nextChatAction && !isCurrentChatAction(state.nextChatAction)) retireNextChatAction();
  if ("diagnostic_readiness" in data) renderDiagnosticReadiness(data.diagnostic_readiness);
  if ("client_snapshot_summary" in data) state.clientSnapshotSummary = data.client_snapshot_summary;
  if (data.client_evidence) state.clientEvidence = data.client_evidence;
  if ("remediation_plan" in data) state.remediationPlan = data.remediation_plan;
  if (data.verification_cycles) state.verificationCycles = data.verification_cycles;
  if ("remediation_readiness" in data) state.remediationReadiness = data.remediation_readiness;
  applyResolution(data);
  renderEnvironmentProfile(state.environmentProfile);renderDiagnosticTarget(state.diagnosticTarget);
  renderClientSnapshot(state.clientSnapshotSummary, state.clientEvidence);
  renderRemediationPlan(state.remediationPlan);renderVerification(state.verificationCycles);
}

function selectClientCheckFile(file) {
  const status = document.querySelector("#client-check-status");
  if (!file || !file.name.toLowerCase().endsWith(".json")) { status.textContent = "格式不支持，请选择网络检查生成的 JSON 文件。";state.clientCheck.file = null;return false; }
  if (file.size > (state.health?.client_snapshot_max_bytes || 262144)) { status.textContent = "文件过大，请重新运行网络检查工具。";state.clientCheck.file = null;return false; }
  state.clientCheck.file = file;
  document.querySelector("#client-check-file-label").textContent = file.name;
  status.textContent = "等待上传；点击“上传并继续分析”后提交。";return true;
}

function clientCheckError(error) {
  if (error.status === 413) return "文件过大，请重新运行网络检查工具。";
  if (error.status === 415) return "格式不支持，请选择网络检查生成的 JSON 文件。";
  if (/sensitive_fields|sensitive_values/.test(error.message || "")) return "文件包含不允许的信息，已拒绝接收。请使用本页提供的检查工具重新生成。";
  if (error.status === 422) return "这个诊断结果无法识别，请重新运行网络检查工具后再上传。";
  return "上传失败，请检查连接后重试。";
}

async function continueClientCheck(receipt) {
  if (!receipt || state.viewingHistory || !state.user || receipt.task_version !== state.taskVersion || receipt.target_version !== state.diagnosticTarget?.target_version) return;
  state.clientCheck.continuation = receipt;
  await submitChat({preventDefault() {}}, {message:"[系统自动继续：网络检查结果已上传]", continuation:receipt});
}

async function uploadClientCheck() {
  if (state.busy || state.clientCheck.uploading || !clientCheckActionCurrent(state.nextChatAction) || !state.clientCheck.file) return;
  const op = clientCheckOperation(), file = state.clientCheck.file;
  const status = document.querySelector("#client-check-status");
  state.clientCheck.uploading = true;setBusy(true);status.textContent = "正在验证检查结果…";
  const form = new FormData();form.append("session_id", op.sid);form.append("file", file);
  let receipt = null;
  try {
    const action = state.nextChatAction;
    const result = await requestJSON("/api/session/client-snapshot", {method:"POST", body:form, headers:{
      "X-NetPilot-Check-ID":action.action_id, "X-NetPilot-Task-Version":String(action.task_version), "X-NetPilot-Target-Version":String(action.target_version)}});
    if (!clientCheckOperationCurrent(op)) return;
    applyClientCheckPayload(result);appendTurnReasoningTrace(result.reasoning_trace || []);
    if (result.duplicate) {
      status.textContent = "重复文件：你上传的是刚才已经使用过的诊断结果，请重新运行网络检查工具生成新的结果。";
    } else if (result.client_check_upload_status === "before_result") {
      status.textContent = "这份检查结果生成于修复前，不能用于重新检查；请再次运行工具生成新的结果。";
    } else if (result.client_check_upload_status === "outdated_scope") {
      status.textContent = "这份结果在当前诊断范围变更前采集，仅供回看。请重新运行检查工具。";
      document.querySelector("#client-check-historical").hidden = false;
    } else if (result.client_snapshot_summary?.stale || result.client_snapshot_summary?.clock_skew_suspected) {
      status.textContent = result.client_snapshot_summary.stale ? "文件过期：这份检查结果采集时间较早，可能不能代表当前网络状态。" : "时间可能不准确：电脑时间与服务时间可能存在偏差，将降低这份结果的实时性判断。";
      document.querySelector("#client-check-historical").hidden = false;
    } else {
      status.textContent = "检查结果已接收。";
      receipt = result.client_check_continuation;
      closeClientCheck();
      appendMessage("assistant", "网络检查完成，已获得新的客户端网络证据。正在继续分析。");
    }
    if (!applyNextChatAction(result) && receipt) retireNextChatAction();
  } catch (error) {
    if (clientCheckOperationCurrent(op)) {
      if (error.status === 409) await refreshClientCheckConflict(error);
      else status.textContent = clientCheckError(error);
    }
  }
  finally {
    if (op.epoch === state.authEpoch && op.sid === state.sessionId) {state.clientCheck.uploading = false;setBusy(false);}
  }
  if (receipt && op.epoch === state.authEpoch && op.sid === state.sessionId && !state.viewingHistory) await continueClientCheck(receipt);
}

function initClientCheck() {
  document.querySelector("#client-check-launch").addEventListener("click", openClientCheck);
  document.querySelector("#client-check-close").addEventListener("click", closeClientCheck);
  document.querySelector("#client-check-dialog").addEventListener("cancel", event => {event.preventDefault();closeClientCheck();});
  for (const button of document.querySelectorAll("[data-client-check-next]")) button.addEventListener("click", () => clientCheckStep(Number(button.dataset.clientCheckNext)));
  document.querySelector("#client-check-skip").addEventListener("click", declineClientCheck);
  document.querySelector("#client-check-file").addEventListener("change", event => selectClientCheckFile(event.target.files?.[0]));
  document.querySelector("#client-check-upload").addEventListener("click", uploadClientCheck);
  document.querySelector("#client-check-rerun").addEventListener("click", () => {document.querySelector("#client-check-historical").hidden = true;clientCheckStep(2);});
  document.querySelector("#client-check-use-old").addEventListener("click", () => {closeClientCheck();appendMessage("assistant", "这份结果已保留为历史检查信息，不作为当前网络状态证明。我会继续提供受限排查建议。");});
  const zone = document.querySelector("#client-check-drop");
  for (const name of ["dragenter", "dragover"]) zone.addEventListener(name, event => {event.preventDefault();zone.classList.add("drag-hover");});
  zone.addEventListener("dragleave", event => {event.preventDefault();zone.classList.remove("drag-hover");});
  zone.addEventListener("drop", async event => {
    event.preventDefault();zone.classList.remove("drag-hover");
    if (!state.clientCheck.open || state.busy || !clientCheckActionCurrent(state.nextChatAction)) return;
    if (event.dataTransfer?.files?.length !== 1) {document.querySelector("#client-check-status").textContent = "请一次上传一个检查结果文件。";return;}
    if (selectClientCheckFile(event.dataTransfer.files[0])) await uploadClientCheck();
  });
  zone.addEventListener("keydown", event => {if (event.key === "Enter" || event.key === " ") {event.preventDefault();document.querySelector("#client-check-file").click();}});
}
