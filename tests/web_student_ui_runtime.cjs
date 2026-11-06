"use strict";
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {setup} = require('./web_markdown_runtime.cjs');
const tick = () => new Promise(setImmediate);
const reply = body => ({ok:true,status:200,json:async()=>body});
const event = {preventDefault(){}};
const target = {subject:'user_client',target_version:1,relationship_to_netpilot:'remote'};
const action = {type:'client_check',session_id:'current-session',action_id:'one',task_version:1,target_version:1,mode:'initial',platform:'windows',collector_supported:true,upload_required:true};
const question = {type:'context_question',field:'network_access',question:'连接哪种网络？',choices:[{value:'campus_wifi',label:'校园 WiFi'},{value:'unknown',label:'不清楚'}]};
const plan = {plan_id:'plan',plan_version:1,status:'proposed',readiness:'ready',target_subject:'user_client',target_version:1,steps:[{step_id:'s1',order:1,title:'记录现象',status:'pending',risk:'low',instructions:['记录'],rollback_instructions:[]}]};
const record = {record_id:'old',session_id:'old-session',environment_profile:{os_family:'linux'},diagnostic_target:{subject:'netpilot_host',target_version:2},conversation_turns:[{user_message:'旧问题',assistant_answer:'旧回答'}],tool_calls:[],resolution:{state:'unresolved'},updated_at:new Date().toISOString()};
const put = (w,js) => w.eval(js);
const button = (w,text) => [...w.document.querySelectorAll('#case-next-action button')].find(b=>b.textContent===text);
function prepare(w) {put(w,`state.taskVersion=1;state.diagnosticTarget=${JSON.stringify(target)};state.environmentProfile={os_family:'windows',os_version:'11',network_access:'campus_wifi'};`);w.setBusy(false);}
const cases = {
 'ST-CONTRACT':async w=>{
   const d=w.document, ids=[...d.querySelectorAll('[id]')].map(el=>el.id);
   assert.equal(new Set(ids).size,ids.length);
   assert.equal(d.querySelector('.diagnostics-panel'),null);
   for(const id of ['environment-form','target-form','snapshot-form','remediation-section','verification-section','resolution-section','escalation-section','reasoning-trace','tool-timeline','metrics-grid','report-actions','demo-controls','scenario-control']) assert.ok(d.getElementById(id).closest('#diagnostic-details-dialog'),id);
   assert.ok(d.getElementById('my-history-card').closest('#history-dialog'));
   assert.ok(d.getElementById('client-check-dialog'));
 },
 'ST-ELEMENTS':async w=>{
   for(const file of ['app.js','student-ui.js','client-check.js']) {
     const source=fs.readFileSync(path.join(__dirname,'../web',file),'utf8');
     for(const match of source.matchAll(/(?:document\.)?querySelector\("#([a-z][a-z0-9-]*)"\)/g)) assert.ok(w.document.getElementById(match[1]),`${file}: ${match[1]}`);
   }
   assert.equal(typeof w.renderContextQuestion,'function');assert.equal(typeof w.renderUIAction,'function');
 },
 'ST-DEFAULT':async w=>{
   w.resetConversation();w.setBusy(false);
   assert.equal(w.document.querySelector('#diagnostic-details-dialog').open,false);
   for(const id of ['technical-details','report-details','demo-details','environment-editor','target-editor']) assert.equal(w.document.getElementById(id).open,false);
   assert.match(w.document.querySelector('#conversation').textContent,/不需要先填写网络配置/);
   assert.equal(w.document.querySelector('#case-next-action').hidden,true);
   assert.equal(w.document.querySelector('#send-button').textContent,'发送');
   assert.equal(w.document.querySelector('#session-label').closest('#workspace'),null);
 },
 'ST-DRAWER':async w=>{
   const open=w.document.querySelector('#diagnostic-details-open'),close=w.document.querySelector('#diagnostic-details-close');open.click();
   assert.equal(w.document.querySelector('#diagnostic-details-dialog').open,true);assert.equal(w.document.activeElement,close);
   assert.equal(w.eval('state.detailsOpen'),true);close.click();assert.equal(w.document.activeElement,open);assert.equal(w.eval('state.detailsOpen'),false);
 },
 'ST-ESC':async w=>{w.openDiagnosticDetails('timeline-section');const d=w.document.querySelector('#diagnostic-details-dialog');assert.equal(w.document.querySelector('#technical-details').open,true);d.dispatchEvent(new w.Event('cancel',{cancelable:true}));assert.equal(d.open,false);assert.equal(w.document.activeElement.id,'diagnostic-details-open');},
 'ST-ENVIRONMENT':async w=>{
   assert.equal(w.studentEnvironmentSummary(null),'环境待确认');assert.equal(w.studentEnvironmentSummary({os_family:'windows'}),'Windows · 网络类型未确认');
   assert.equal(w.studentEnvironmentSummary({os_family:'windows',os_version:'11',network_access:'campus_wifi',affected_scope:'web_only'}),'Windows 11 · 校园 WiFi · 仅网页');
   assert.ok(!/undefined|null|unknown/.test(w.studentEnvironmentSummary({os_family:'bad',network_access:null})));
   prepare(w);w.renderEnvironmentProfile(w.eval('state.environmentProfile'));w.openDiagnosticDetails();
   w.document.querySelector('#environment-editor > summary').click();w.document.querySelector('#environment-access').value='campus_wired';
   let sent;w.fetch=async(u,o)=>{assert.equal(u,'/api/session/environment/user');sent=JSON.parse(o.body);return reply({...w.eval('state.environmentProfile'),network_access:'campus_wired'});};await w.saveEnvironment(event);
   assert.equal(sent.network_access,'campus_wired');assert.match(w.document.querySelector('#case-environment').textContent,/校园有线/);
 },
 'ST-TARGET':async w=>{prepare(w);w.renderDiagnosticTarget(target);assert.equal(w.document.querySelector('#target-summary').textContent,'正在诊断：这台电脑');assert.match(w.document.querySelector('#target-technical').textContent,/remote/);assert.equal(w.document.querySelector('#target-form').closest('#target-editor').open,false);},
 'ST-SNAPSHOT':async w=>{prepare(w);put(w,`state.clientSnapshotSummary={target_version:1,generated_at:new Date().toISOString(),expires_at:new Date(Date.now()+100000).toISOString()}`);w.renderCaseStatus();assert.match(w.document.querySelector('#client-check-summary').textContent,/已完成/);put(w,'state.clientSnapshotSummary.stale=true');w.renderCaseStatus();assert.equal(w.document.querySelector('#client-check-summary').textContent,'结果已过期');},
 'ST-CONTEXT':async w=>{prepare(w);w.renderUIAction(w.appendMessage('assistant',question.question),question);w.setBusy(false);assert.ok(w.document.querySelector('.context-choices').closest('#conversation'));assert.ok(button(w,'查看问题'));button(w,'查看问题').click();assert.ok(w.document.activeElement.classList.contains('context-choice'));assert.equal(w.document.querySelector('#diagnostic-details-dialog').open,false);},
 'ST-CHECK':async w=>{prepare(w);w.renderUIAction(w.appendMessage('assistant','需要检查'),action);w.setBusy(false);assert.ok(w.document.querySelector('.client-check-actions').closest('#conversation'));button(w,'开始网络检查').click();assert.equal(w.document.querySelector('#client-check-dialog').open,true);assert.equal(w.eval('state.clientCheck.mode'),'initial');},
 'ST-RECHECK':async w=>{prepare(w);put(w,`state.verificationCycles=[{target_subject:'user_client',target_version:1,status:'awaiting_after_evidence'}]`);w.renderUIAction(null,{...action,mode:'recheck'});w.setBusy(false);button(w,'重新检查').click();assert.equal(w.eval('state.clientCheck.mode'),'recheck');assert.match(w.document.querySelector('#client-check-title').textContent,/重新检查/);},
 'ST-STALE-ACTION':async w=>{prepare(w);w.renderUIAction(null,{...action,target_version:2});w.setBusy(false);assert.equal(button(w,'开始网络检查'),undefined);assert.equal(button(w,'重新检查'),undefined);},
 'ST-PLAN':async w=>{prepare(w);put(w,`state.remediationPlan=${JSON.stringify(plan)}`);w.renderRemediationPlan(plan);w.setBusy(false);assert.match(w.document.querySelector('#case-next-action').textContent,/1 步修复建议/);button(w,'查看修复步骤').click();assert.equal(w.document.querySelector('#remediation-section').open,true);assert.equal(w.document.querySelector('#diagnostic-details-dialog').open,true);put(w,"state.remediationPlan.status='superseded'");w.setBusy(false);assert.equal(button(w,'查看修复步骤'),undefined);},
 'ST-VERIFICATION':async w=>{prepare(w);put(w,`state.verificationCycles=[{target_subject:'user_client',target_version:1,status:'completed',result:'improved'}]`);w.setBusy(false);assert.match(w.document.querySelector('#case-next-action').textContent,/修复后状态：有改善/);button(w,'查看对比').click();assert.equal(w.document.querySelector('#verification-section').open,true);assert.equal(button(w,'重新检查'),undefined);},
 'ST-RESOLUTION':async w=>{prepare(w);for(const [status,label] of Object.entries({diagnosing:'诊断中',resolved:'已解决',unresolved:'仍未解决',escalated:'建议报修'})){put(w,`state.resolution={state:'${status}'}`);w.renderResolution(w.eval('state.resolution'));w.setBusy(false);assert.equal(w.document.querySelector('#resolution-badge').textContent,label);}assert.ok(button(w,'生成报修材料'));},
 'ST-ESCALATION':async w=>{prepare(w);put(w,"state.resolution={state:'escalated',escalation_recommended:true}");w.setBusy(false);let calls=0;w.fetch=async(u,o)=>{assert.equal(u,'/api/session/escalation-package');assert.deepEqual(JSON.parse(o.body),{session_id:'current-session'});calls++;return reply({packages:[]});};button(w,'生成报修材料').click();await tick();assert.equal(calls,1);assert.equal(w.document.querySelector('#diagnostic-details-dialog').open,true);},
 'ST-HISTORY-RETURN':async w=>{
   prepare(w);const body=w.appendMessage('assistant','当前问题');w.renderUIAction(body,action);w.setBusy(false);
   const live=w.document.querySelector('.client-check-actions');w.setReportRecord('current-record');w.document.querySelector('#message-input').value='未发送';w.document.querySelector('#interaction-note').textContent='当前诊断已就绪';
   w.fetch=async()=>reply(record);await w.loadDiagnosisRecord('old');
   assert.equal(w.document.querySelector('#history-view-banner').hidden,false);assert.equal(w.document.querySelector('#send-button').disabled,true);
   assert.equal(w.eval('state.sessionId'),'current-session');assert.equal(w.eval('state.diagnosticTarget.subject'),'user_client');
   assert.match(w.document.querySelector('#case-environment').textContent,/Linux/);assert.equal(w.eval('state.activeRecordId'),'old');
   w.document.querySelector('#history-return').click();assert.equal(w.document.querySelector('.client-check-actions'),live);
   assert.match(w.document.querySelector('#conversation').textContent,/当前问题/);assert.ok(!w.document.querySelector('#conversation').textContent.includes('旧回答'));
   assert.equal(w.eval('state.activeRecordId'),'current-record');assert.equal(w.document.querySelector('#message-input').value,'未发送');assert.equal(w.document.querySelector('#send-button').disabled,false);
   assert.equal(w.document.querySelector('#interaction-note').textContent,'当前诊断已就绪');
   live.querySelector('button').click();assert.equal(w.document.querySelector('#client-check-dialog').open,true);
 },
 'ST-HISTORY-GUARDS':async w=>{
   prepare(w);w.fetch=async()=>reply(record);await w.loadDiagnosisRecord('old');let calls=0;w.fetch=async()=>{calls++;throw Error('must not mutate');};
   w.document.querySelector('#message-input').value='不能发送';await w.submitChat(event);await w.saveEnvironment(event);await w.saveDiagnosticTarget(event);await w.uploadClientSnapshot(event);await w.generateRemediationPlan();await w.verificationRequest('',{});await w.generateEscalation();await w.demoOperation('/api/demo/session',{});await w.createCustomScenario(event);await w.switchScenario();
   assert.equal(calls,0);for(const id of ['environment-save','target-save','snapshot-upload','remediation-generate','escalation-generate','send-button','demo-create'])assert.equal(w.document.getElementById(id).disabled,true,id);
 },
 'ST-HISTORY-PAGING':async w=>{put(w,'state.health.history_ready=true');let calls=[];w.fetch=async u=>{calls.push(u);return reply({items:[],next_cursor:u.includes('cursor=')?null:'page2'});};await w.openHistoryView();assert.equal(w.document.querySelector('#history-dialog').open,true);w.document.querySelector('#history-next').click();await tick();assert.equal(w.document.querySelector('#history-page-label').textContent,'第 2 页');w.document.querySelector('#history-previous').click();await tick();assert.equal(calls.length,2);assert.equal(w.document.querySelector('#history-page-label').textContent,'第 1 页');w.closeHistoryDialog();assert.equal(w.document.querySelector('#history-dialog').open,false);},
 'ST-HISTORY-SWITCH':async w=>{prepare(w);w.appendMessage('assistant','当前');w.fetch=async u=>reply({...record,record_id:u.endsWith('two')?'two':'one'});await w.loadDiagnosisRecord('one');await w.loadDiagnosisRecord('two');w.closeHistoryView();assert.equal(w.document.querySelector('#conversation').textContent.includes('旧回答'),false);assert.match(w.document.querySelector('#conversation').textContent,/当前/);},
 'ST-HISTORY-RACE':async w=>{prepare(w);let release;w.fetch=()=>new Promise(r=>release=r);const pending=w.loadDiagnosisRecord('old');w.showAuthGate();release(reply(record));await pending;assert.equal(w.eval('state.viewingHistory'),false);assert.equal(w.eval('state.historyPresentation'),null);assert.equal(w.document.querySelector('#history-view-banner').hidden,true);},
 'ST-DEMO':async w=>{prepare(w);assert.equal(w.document.querySelector('#demo-details').hidden,true);put(w,'state.health.demo_mode=true');w.setBusy(false);assert.equal(w.document.querySelector('#demo-details').hidden,false);assert.equal(w.document.querySelector('#demo-details').open,false);assert.ok(w.document.querySelector('#demo-controls').closest('#demo-details'));assert.ok(w.document.querySelector('#scenario-control').closest('#demo-details'));},
 'ST-RESET':async w=>{prepare(w);w.openDiagnosticDetails('technical-details');w.fetch=async()=>reply(record);await w.loadDiagnosisRecord('old');w.showAuthGate();for(const id of ['diagnostic-details-dialog','history-dialog','technical-details','report-details','demo-details'])assert.equal(w.document.getElementById(id).open,false);assert.equal(w.eval('state.historyPresentation'),null);assert.equal(w.eval('state.detailsSection'),null);assert.equal(w.document.querySelector('#demo-details').hidden,true);},
 'ST-STYLE':async w=>{const css=fs.readFileSync(path.join(__dirname,'../web/style.css'),'utf8');assert.match(css,/prefers-reduced-motion/);assert.match(css,/width: min\(1080px/);assert.match(css,/width: min\(520px/);assert.match(css,/@media \(max-width: 560px\)/);assert.match(css,/\.quick-prompts \{ flex-wrap: wrap/);assert.match(css,/\.verification-table-scroll \{ overflow-x: auto/);assert.match(css,/:focus-visible/);},
};
(async()=>{for(const name of process.argv[2]?[process.argv[2]]:Object.keys(cases)){const dom=await setup();try{await cases[name](dom.window);console.log(`${name} passed`);}finally{dom.window.close();}}})().catch(e=>{console.error(e);process.exitCode=1;});
