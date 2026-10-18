"use strict";
const assert = require("node:assert/strict");
const {setup} = require("./web_markdown_runtime.cjs");
const sid = "11111111-1111-4111-8111-111111111111";
const remote = {subject:"user_client",relationship_to_netpilot:"remote",execution_context:"netpilot_host",limitation_code:"remote_client_not_directly_observable",target_version:1};
const host = {...remote,subject:"netpilot_host",relationship_to_netpilot:"same_host",limitation_code:"none",target_version:2};
const mock = {...remote,subject:"mock_client",relationship_to_netpilot:"simulated",execution_context:"mock_provider",limitation_code:"none"};
const reply = (body) => ({ok:true,status:200,json:async()=>body});
const cases = {
  "DT-REMOTE": async(w) => {
    w.eval(`state.diagnosticTarget = ${JSON.stringify(remote)}`);
    w.renderDiagnosticTarget(remote);
    w.setBusy(false);
    assert.match(w.document.querySelector("#target-summary").textContent,/当前浏览器设备（远程）/);
    assert.match(w.document.querySelector("#target-capability").textContent,/受限.*NetPilot 服务主机/);
    assert.match(w.document.querySelector("#target-status").textContent,/不会将服务主机结果当作此设备结果/);
    assert.equal(w.document.querySelector("#target-save").disabled,false);
  },
  "DT-SWITCH": async(w) => {
    w.eval(`state.diagnosticTarget = ${JSON.stringify(remote)}`);
    w.renderDiagnosticTarget(remote);
    w.document.querySelector("#target-subject").value = "netpilot_host";
    let body;
    w.fetch = async(url,options) => {assert.equal(url,"/api/session/diagnostic-target");body=JSON.parse(options.body);return reply(host);};
    await w.saveDiagnosticTarget({preventDefault(){}});
    assert.deepEqual(body,{session_id:"current-session",subject:"netpilot_host"});
    assert.equal(w.eval("state.diagnosticTarget.target_version"),2);
    assert.match(w.document.querySelector("#target-summary").textContent,/NetPilot 服务主机/);
    assert.match(w.document.querySelector("#target-capability").textContent,/可用/);
    assert.equal(w.document.querySelector("#timeline-count").textContent,"0");
  },
  "DT-MOCK": async(w) => {
    w.eval(`state.diagnosticTarget = ${JSON.stringify(mock)}`);
    w.renderDiagnosticTarget(mock);w.setBusy(false);
    assert.equal(w.document.querySelector("#target-subject").value,"mock_client");
    assert.equal(w.document.querySelector("#target-subject").disabled,true);
    assert.equal(w.document.querySelector("#target-save").disabled,true);
    assert.match(w.document.querySelector("#target-status").textContent,/由系统管理/);
  },
  "DT-TIMELINE": async(w) => {
    const tool = {round:1,tool_call_id:"dns",tool_name:"dns_lookup",duration_ms:1,finding_status:"normal",summary:"DNS正常",arguments:{domain:"github.com"},data:{resolved:true},target_subject:"netpilot_host",target_version:2,execution_context:"netpilot_host",execution_scope:"execution_host"};
    w.renderTools([tool,{...tool,target_subject:"mock_client",execution_context:"mock_provider",execution_scope:"mock_target"},{...tool,tool_name:"knowledge_search",execution_scope:"target_neutral"}]);
    const labels = [...w.document.querySelectorAll(".tool-execution-context")].map(n=>n.textContent);
    assert.match(labels[0],/执行位置：NetPilot 服务主机/);
    assert.match(labels[1],/执行位置：Mock Provider/);
    assert.match(labels[2],/非设备检测/);
    w.renderTools([{...tool,execution_context:"<img src=x onerror=evil()>"}]);
    assert.equal(w.document.querySelector("#tool-timeline img"),null);
  },
  "DT-REFRESH": async(w) => {
    w.history.replaceState(null,"",`#session=${sid}`);
    w.eval("state.diagnosticTarget = null;state.sessionId = null;");
    const urls=[];
    w.fetch = async(url) => {urls.push(url);return reply(url.includes("environment/browser") ? {} : {session_id:sid,diagnostic_target:host,environment_profile:{}});};
    await w.createSession({restore:true,announce:false});
    assert.equal(urls[0],`/api/session/${sid}`);
    assert.equal(w.eval("state.diagnosticTarget.subject"),"netpilot_host");
    assert.match(w.document.querySelector("#target-summary").textContent,/NetPilot 服务主机/);
    assert.equal(w.localStorage.length,0);
  },
  "DT-HISTORY": async(w) => {
    w.eval(`state.diagnosticTarget = ${JSON.stringify(remote)}`);
    w.fetch = async()=>reply({record_id:"old",diagnostic_target:host,conversation_turns:[],tool_calls:[]});
    await w.loadDiagnosisRecord("old");
    assert.match(w.document.querySelector("#target-summary").textContent,/历史对象：NetPilot 服务主机/);
    assert.equal(w.document.querySelector("#target-save").disabled,true);
    assert.equal(w.eval("state.diagnosticTarget.subject"),"user_client");
    w.resetConversation();
    assert.match(w.document.querySelector("#target-summary").textContent,/当前浏览器设备/);
    assert.match(w.formatReportPreview({diagnostic_target:host}),/诊断对象：NetPilot 服务主机/);
    w.renderDiagnosticTarget(undefined,{historical:true});
    assert.match(w.document.querySelector("#target-summary").textContent,/未记录/);
  },
  "DT-RESET": async(w) => {
    w.eval(`state.diagnosticTarget = ${JSON.stringify(host)}`);
    w.showAuthGate();
    assert.equal(w.eval("state.diagnosticTarget"),null);
    assert.equal(w.document.querySelector("#target-save").disabled,true);
  },
};
(async()=>{for(const name of process.argv[2]?[process.argv[2]]:Object.keys(cases)){const dom=await setup();try{await cases[name](dom.window);console.log(`${name} passed`);}finally{dom.window.close();}}})().catch(error=>{console.error(error);process.exitCode=1;});
