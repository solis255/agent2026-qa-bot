"use strict";

const assert = require("node:assert/strict");
const reply = (body, status = 200) => ({ok:status < 400, status, json:async () => body});

function workflow({subject = "netpilot_host", sid = "current-session"} = {}) {
  const diagnostic_target = {
    subject, target_version:1, relationship_to_netpilot:subject === "user_client" ? "remote" : "same_host",
    execution_context:subject === "user_client" ? "unavailable" : "netpilot_host",
  };
  const scope = {schema_version:1, session_id:sid, target_subject:subject, target_version:1, task_version:1};
  const step = {
    step_id:"step-1", order:1, risk:"low", requires_admin:false, status:"pending", outcome:"unknown",
    title:"重新连接当前网络", rationale:"DNS 解析出现异常", instructions:["保存当前工作", "重新连接原网络"],
    verification:"重新访问原网页", rollback_instructions:["恢复原来的网络连接"], continue_condition:"连接仍失败时停止",
  };
  const plan = {
    plan_id:"plan-1", plan_version:1, task_version:1, target_subject:subject, target_version:1,
    status:"proposed", readiness:"ready", readiness_reason:"已有 DNS 证据",
    steps:[step, {...step, order:2, step_id:"step-2", title:"记录剩余现象"}],
  };
  const stepAction = {
    ...scope, type:"remediation_step", action_id:"action-step-1", plan_id:plan.plan_id, plan_version:plan.plan_version,
    step_id:"step-1", step_order:1, allowed_actions:["complete","skip","fail"],
  };
  const baseline = {task_version:1, evidence_ids:["before-dns"], stale:false};
  const before = {
    verification_id:"verification-1", verification_sequence:1, target_subject:subject, target_version:1,
    remediation_plan_id:plan.plan_id, remediation_plan_version:plan.plan_version, baseline, status:"baseline_ready",
    checks:[{metric:"dns_resolution", target:"example.invalid", baseline_value:"异常", baseline_status:"abnormal", change:"unknown"}],
  };
  const verifying = {...before, status:"awaiting_after_evidence", after_task_version:2};
  const verified = {...verifying, status:"completed", result:"improved", result_summary:"关键指标有改善。",
    checks:[{...before.checks[0], after_value:"正常", after_status:"normal", change:"improved"}],
    after:{task_version:2, evidence_ids:["after-dns"], stale:false}};
  const verificationAction = {
    ...scope, task_version:2, type:"verification", mode:"start", action_id:"action-start",
    verification_id:verifying.verification_id, verification_sequence:1, plan_id:plan.plan_id, plan_version:plan.plan_version,
  };
  const resolution = {
    state:"improved", state_version:3, user_confirmation:"unknown", objective_result:"improved",
    target_subject:subject, target_version:1, task_version:2, based_on_verification_id:verified.verification_id,
  };
  const confirmAction = {
    ...scope, task_version:2, type:"resolution_confirmation", action_id:"action-confirm",
    verification_id:verified.verification_id, resolution_state_version:3, question:"刚才遇到的网络问题，现在有什么变化？",
    choices:[
      {value:"resolved",label:"已经恢复正常"}, {value:"improved",label:"有改善，但还没有完全恢复"},
      {value:"not_resolved",label:"还是无法正常使用"}, {value:"unknown",label:"暂时无法确定"},
    ],
  };
  const base = {
    session_id:sid, task_version:1, diagnostic_target, environment_profile:{os_family:"windows"},
    remediation_plan:plan, verification_cycles:[before], resolution:{...resolution, state:"action_required", task_version:1},
    resolution_transitions:[], next_chat_action:stepAction,
  };
  const started = {
    ...base, task_version:2, remediation_plan:{...plan, status:"in_progress", steps:[{...step,status:"completed"},plan.steps[1]]},
    verification_cycles:[verifying], resolution:{...resolution,state:"verifying"}, next_chat_action:verificationAction,
  };
  const compared = {...started, verification_cycles:[verified], resolution, next_chat_action:confirmAction};
  const resolved = {
    ...compared, resolution:{...resolution, state:"resolved", user_confirmation:"resolved", state_version:4,
      reason_summary:"关键指标恢复，用户确认原始症状消失。"},
    verification_cycles:[{...verified,user_observation:{symptom_status:"resolved_by_user_report"}}], next_chat_action:null,
  };
  return {base, started, compared, resolved, stepAction, verificationAction, confirmAction, diagnostic_target, sid};
}

function install(w, result) {
  w.eval(`state.sessionId = ${JSON.stringify(result.session_id)}`);
  w.applySessionState(result);
  w.applyNextChatAction(result);
  w.setBusy(false);
}

function chatButton(w, label) {
  const button = [...w.document.querySelectorAll("#conversation button")].find(node => node.textContent === label);
  assert.ok(button, label);
  return button;
}

async function idle(w) {
  for (let index=0; index<20 && w.eval("state.busy"); index++) await new Promise(setImmediate);
  assert.equal(w.eval("state.busy"), false);
}

module.exports = {workflow, install, chatButton, idle, reply};
