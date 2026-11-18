"use strict";

const WORKFLOW_ACTION_TYPES = ["remediation_step", "verification", "resolution_confirmation"];
const VERIFICATION_STATUS = {
  baseline_ready:"已保存修复前检查结果", awaiting_after_evidence:"等待修复后检查结果",
  verifying:"正在对比修复前后的网络状态", completed:"验证已完成",
  inconclusive:"暂时无法确认修复效果", failed:"本次验证未能完成", superseded:"本轮验证已失效",
};
const OBSERVATION_LABELS = {
  resolved_by_user_report:"已经恢复正常", improved_by_user_report:"有改善，但还没有完全恢复",
  unchanged_by_user_report:"还是无法正常使用", worsened_by_user_report:"症状变差", unknown:"暂时无法确定",
};
const METRIC_STATUS = {normal:"正常", abnormal:"异常", unknown:"未知", unsupported:"不支持", error:"采集错误"};
const STEP_RISK = {low:"低风险", medium:"中风险", high:"高风险"};
const STEP_ACTION = {complete:"我已完成", skip:"暂时跳过", fail:"遇到问题"};

function workflowText(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}

function workflowTargetMatches(item) {
  return item && item.target_subject === state.diagnosticTarget?.subject &&
    item.target_version === state.diagnosticTarget?.target_version;
}

function currentWorkflowCycle() {
  const cycle = state.verificationCycles.at(-1);
  if (!workflowTargetMatches(cycle) || cycle.status === "superseded") return null;
  const version = cycle.status === "baseline_ready" ? cycle.baseline?.task_version : cycle.after_task_version;
  return version === state.taskVersion ? cycle : null;
}

function currentWorkflowPlan() {
  const plan = state.remediationPlan;
  if (!workflowTargetMatches(plan) || ["superseded", "cancelled"].includes(plan.status)) return null;
  const cycle = currentWorkflowCycle();
  if (plan.task_version === state.taskVersion ||
      (cycle?.remediation_plan_id === plan.plan_id && cycle?.remediation_plan_version === plan.plan_version)) return plan;
  return null;
}

function workflowCycleMatchesPlan(cycle, plan) {
  return Boolean(cycle && plan && cycle.remediation_plan_id === plan.plan_id &&
    cycle.remediation_plan_version === plan.plan_version);
}

function isCurrentWorkflowAction(action) {
  const plan = currentWorkflowPlan();
  const cycle = currentWorkflowCycle();
  switch (action.type) {
    case "remediation_step":
      return Boolean(plan) && plan.plan_id === action.plan_id && plan.plan_version === action.plan_version &&
        Array.isArray(action.allowed_actions) && plan.steps.some(step => step.step_id === action.step_id &&
          step.order === action.step_order && step.status === "pending" && step.risk === "low" && !step.requires_admin);
    case "verification":
      return !state.isDemo && action.mode === "start" && workflowCycleMatchesPlan(cycle, plan) &&
        cycle.verification_id === action.verification_id && cycle.verification_sequence === action.verification_sequence &&
        cycle.status === "awaiting_after_evidence" && plan.plan_id === action.plan_id && plan.plan_version === action.plan_version;
    case "resolution_confirmation":
      return Boolean(cycle?.after) && cycle.verification_id === action.verification_id &&
        ["completed", "inconclusive"].includes(cycle.status) && !cycle.user_observation &&
        state.resolution?.state_version === action.resolution_state_version &&
        state.resolution?.based_on_verification_id === action.verification_id && Array.isArray(action.choices);
    default:
      return false;
  }
}

function appendWorkflowButton(group, label, callback) {
  const button = workflowText("button", label);
  button.type = "button";
  button.addEventListener("click", callback);
  group.append(button);
}

function renderChatRemediationPlan(plan, action = null) {
  const card = document.createElement("section");
  card.className = "chat-workflow-card chat-remediation-card";
  const handled = plan.steps.filter(step => step.status !== "pending").length;
  card.append(workflowText("h3", "修复建议"), workflowText("p", `修复进度 ${handled} / ${plan.steps.length}`));
  if (Object.hasOwn(ISSUE_LABELS, plan.primary_issue))
    card.append(workflowText("p", `当前问题：${ISSUE_LABELS[plan.primary_issue]}`));
  if (plan.readiness_reason) card.append(workflowText("p", plan.readiness_reason));
  for (const step of plan.steps) {
    const current = step.step_id === action?.step_id;
    const label = `${step.order}. ${step.title} · ${STEP_RISK[step.risk] || "风险待确认"} · ${STEP_STATUS[step.status] || "待确认"}`;
    if (!current && step.status !== "pending") {
      card.append(workflowText("p", step.user_note ? `${label} · 备注：${step.user_note}` : label));
      continue;
    }
    const details = document.createElement("details");
    details.open = current;
    details.append(workflowText("summary", label), workflowText("p", step.rationale || ""));
    const instructions = document.createElement("ol");
    for (const instruction of step.instructions || []) instructions.append(workflowText("li", instruction));
    details.append(instructions);
    if (step.requires_admin) details.append(workflowText("p", "需要管理员权限"));
    if (step.verification) details.append(workflowText("p", `完成后检查：${step.verification}`));
    details.append(
      workflowText("p", `回滚：${step.rollback_instructions?.join("；") || "无需恢复配置"}`),
      workflowText("p", `停止条件：${step.continue_condition || "如果无法安全完成，请停止这一步。"}`),
    );
    if (current) {
      const controls = document.createElement("div");
      controls.className = "remediation-feedback-controls";
      const outcome = document.createElement("select");
      outcome.setAttribute("aria-label", "执行效果");
      for (const [value, label] of Object.entries(STEP_OUTCOME)) {
        const option = workflowText("option", label);
        option.value = value;
        outcome.append(option);
      }
      const note = document.createElement("textarea");
      note.maxLength = 500;
      note.setAttribute("aria-label", "步骤备注");
      note.placeholder = "可选备注";
      controls.append(outcome, note);
      for (const value of action.allowed_actions) {
        if (!Object.hasOwn(STEP_ACTION, value)) continue;
        appendWorkflowButton(controls, STEP_ACTION[value], () => submitWorkflowAction(action, value, {
          outcome: value === "complete" ? outcome.value : "unknown", user_note: note.value.trim() || null,
        }));
      }
      details.append(controls);
    }
    card.append(details);
  }
  return card;
}

function renderVerificationTable(checks, {detailed = false} = {}) {
  const scroll = document.createElement("div");
  scroll.className = "verification-table-scroll";
  const table = document.createElement("table");
  table.className = "verification-table";
  const header = table.createTHead().insertRow();
  for (const label of [detailed ? "指标 / 目标" : "指标", "修复前", "修复后", "变化"]) {
    const heading = workflowText("th", label);
    heading.scope = "col";
    header.append(heading);
  }
  const body = table.createTBody();
  for (const check of checks) {
    const row = body.insertRow();
    const metric = METRIC_LABEL[check.metric] || (detailed ? check.metric : "网络指标");
    const label = detailed && check.target ? `${metric} ${check.target}` : metric;
    for (const text of [
      label, check.baseline_value || METRIC_STATUS[check.baseline_status] || "未知",
      check.after_value || METRIC_STATUS[check.after_status] || "未采集",
      check.change === "not_comparable" ? "不可比较" : VERIFICATION_RESULT[check.change] || "未知",
    ]) row.append(workflowText("td", text));
  }
  scroll.append(table);
  return scroll;
}

function renderChatVerification(cycle) {
  const card = document.createElement("section");
  card.className = "chat-workflow-card chat-verification-card";
  const snapshot = state.clientSnapshotSummary;
  const snapshotExpired = cycle.after?.snapshot_id && cycle.after.snapshot_id === snapshot?.snapshot_id &&
    (snapshot.stale || snapshot.clock_skew_suspected || Date.now() > Date.parse(snapshot.expires_at));
  const comparisonExpired = cycle.after && (cycle.baseline?.stale || cycle.after.stale || snapshotExpired);
  card.append(workflowText("h3", `修复后验证 · 第 ${cycle.verification_sequence} 轮`),
    workflowText("p", comparisonExpired ? "这轮证据已失效，仅供回看。" : VERIFICATION_STATUS[cycle.status] || "等待验证"));
  const before = cycle.baseline?.stale ? "修复前结果已过期或时间不准确" :
    cycle.baseline?.evidence_ids?.length ? "已有修复前结果用于对照" : "缺少可用的修复前结果";
  const after = cycle.after?.evidence_ids?.length ? "已收到修复后结果" : "尚未收到修复后结果";
  card.append(workflowText("p", `${before}。${after}。`));
  if (cycle.status === "awaiting_after_evidence" && cycle.target_subject === "user_client") {
    if (state.isDemo) card.append(workflowText("p", "请在演示控制区加载修复后的演示检查结果。"));
    else if (state.nextChatAction?.type === "client_check" && state.nextChatAction.mode === "recheck")
      card.append(workflowText("p", "请在发生问题的这台电脑上重新检查网络，以便比较修复前后的状态。"));
    else card.append(workflowText("p", "当前等待这台设备的修复后检查结果。"));
  }
  if (!comparisonExpired && cycle.result_summary && cycle.status !== "awaiting_after_evidence")
    card.append(workflowText("p", cycle.result_summary));
  if (cycle.after && !comparisonExpired && cycle.checks?.length)
    card.append(renderVerificationTable(cycle.checks));
  if (cycle.user_observation)
    card.append(workflowText("p", `用户反馈：${OBSERVATION_LABELS[cycle.user_observation.symptom_status] || "暂时无法确定"}`));
  return card;
}

function renderWorkflowAction(body, action) {
  let card;
  if (action.type === "remediation_step") {
    card = renderChatRemediationPlan(currentWorkflowPlan(), action);
  } else {
    card = document.createElement("section");
    card.className = "chat-workflow-card";
    if (action.type === "verification") {
      card.append(workflowText("p", "重新检查相关网络指标，确认这一步的效果。"));
      appendWorkflowButton(card, "开始验证", () => submitWorkflowAction(action));
    } else {
      card.classList.add("chat-resolution-card");
      card.append(workflowText("h3", action.question));
      for (const choice of action.choices)
        appendWorkflowButton(card, choice.label, () => submitWorkflowAction(action, choice.value));
    }
  }
  card.dataset.actionId = action.action_id;
  if (body) body.after(card);
  else elements.conversation.append(card);
  return card;
}

function renderChatWorkflowStatus(body = null) {
  if (state.viewingHistory) return;
  const existing = elements.conversation.querySelector(".chat-workflow-status");
  const plan = currentWorkflowPlan();
  const cycle = currentWorkflowCycle();
  const sections = [];
  if (plan?.steps.length && state.nextChatAction?.type !== "remediation_step")
    sections.push(renderChatRemediationPlan(plan));
  if (cycle) sections.push(renderChatVerification(cycle));
  const resolution = state.resolution;
  if (workflowTargetMatches(resolution) && resolution.task_version === state.taskVersion &&
      (cycle?.user_observation || ["resolved", "escalated", "improved", "unresolved"].includes(resolution.state))) {
    const status = document.createElement("section");
    status.className = "chat-workflow-card";
    status.append(workflowText("h3", RESOLUTION_LABELS[resolution.state]),
      workflowText("p", resolution.reason_summary || ""));
    sections.push(status);
  }
  if (!sections.length) {
    existing?.remove();
    return;
  }
  const status = existing || document.createElement("div");
  status.className = "chat-workflow-status";
  status.replaceChildren(...sections);
  if (state.chatActionGroup?.isConnected) state.chatActionGroup.before(status);
  else if (body) body.after(status);
  else elements.conversation.append(status);
}

function submitWorkflowAction(action, value, feedback = {}) {
  if (state.nextChatAction !== action || !isCurrentChatAction(action) || state.busy) return;
  const {session_id, action_id, task_version, target_subject, target_version} = action;
  const scope = {session_id, action_id, task_version, target_subject, target_version};
  if (action.type === "resolution_confirmation") {
    if (!action.choices.some(choice => choice.value === value)) return;
    return workflowRequest("/api/session/resolution/confirm", "POST", {
      ...scope, status: value, verification_id: action.verification_id,
      resolution_state_version: action.resolution_state_version,
    }, {action, feedback: "已记录你对原始症状的反馈。"});
  }
  const planScope = {...scope, plan_id: action.plan_id, plan_version: action.plan_version};
  if (action.type === "verification") {
    return workflowRequest(`/api/session/verification/${encodeURIComponent(action.verification_id)}/start`, "POST", planScope, {action});
  }
  if (action.type === "remediation_step" && action.allowed_actions.includes(value)) {
    const messages = {
      complete:"已记录你完成了这一步。接下来需要验证修复效果，才能判断网络是否恢复。",
      skip:"已记录你跳过了这一步。",
      fail:"已记录这一步遇到的问题。",
    };
    return workflowRequest(`/api/session/remediation-plan/steps/${encodeURIComponent(action.step_id)}`, "PATCH",
      {...planScope, action: value, ...feedback}, {action, feedback: messages[value]});
  }
}
