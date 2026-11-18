"use strict";
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {setup} = require('./web_markdown_runtime.cjs');
const {workflow, install, chatButton, idle} = require('./web_workflow_helpers.cjs');
const tick = () => new Promise(setImmediate);
const reply = body => ({ok:true,status:200,json:async()=>body});
const event = {preventDefault(){}};
const target = {subject:'user_client',target_version:1,relationship_to_netpilot:'remote'};
const action = {type:'client_check',session_id:'current-session',action_id:'one',task_version:1,target_version:1,mode:'initial',platform:'windows',collector_supported:true,upload_required:true};
const question = {type:'context_question',field:'network_access',question:'连接哪种网络？',choices:[{value:'campus_wifi',label:'校园 WiFi'},{value:'unknown',label:'不清楚'}]};
const canonicalCheck = {...action, schema_version:1, target_subject:target.subject};
const canonicalQuestion = {...question, schema_version:1, target_subject:target.subject, task_version:1, target_version:1, session_id:'current-session', action_id:'question-id'};
const plan = {plan_id:'plan',plan_version:1,status:'proposed',readiness:'ready',target_subject:'user_client',target_version:1,steps:[{step_id:'s1',order:1,title:'记录现象',status:'pending',risk:'low',instructions:['记录'],rollback_instructions:[]}]};
const record = {record_id:'old',session_id:'old-session',environment_profile:{os_family:'linux'},diagnostic_target:{subject:'netpilot_host',target_version:2},conversation_turns:[{user_message:'旧问题',assistant_answer:'旧回答'}],tool_calls:[],resolution:{state:'unresolved'},updated_at:new Date().toISOString()};
const put = (w,js) => w.eval(js);
const button = (w,text) => [...w.document.querySelectorAll('#case-next-action button')].find(b=>b.textContent===text);
const render = (w,body,action) => w.renderNextChatAction(w.resolveNextChatAction({ui_action:action}),body);
function prepare(w) {put(w,`state.taskVersion=1;state.diagnosticTarget=${JSON.stringify(target)};state.environmentProfile={os_family:'windows',os_version:'11',network_access:'campus_wifi'};`);w.setBusy(false);}
function complete(response) {
  let sent = false;
  return {ok:true, headers:{get:()=>'text/event-stream'}, body:{getReader:()=>({
    read:async()=>sent ? {done:true} : (sent=true,{done:false,value:new TextEncoder().encode(`event: complete\ndata: ${JSON.stringify({response})}\n\n`)}),
    cancel:async()=>{},
  })}};
}
const cases = {
 'ST-14B-01':async w=>{
   install(w,workflow().base);
   const card=w.document.querySelector('#conversation .chat-remediation-card');
   assert.match(card.textContent,/修复进度 0 \/ 2/);
   assert.match(card.textContent,/保存当前工作.*低风险|低风险.*保存当前工作/s);
   assert.match(card.textContent,/回滚.*停止条件/s);
   const details=card.querySelectorAll('details');
   assert.equal(details[0].open,true);assert.equal(details[1].open,false);
   assert.equal(details[0].querySelectorAll('button').length,3);assert.equal(details[1].querySelector('button'),null);
 },
 'ST-14B-02':async w=>{
   const f=workflow();install(w,f.base);let request;
   w.fetch=async(url,options)=>{request=[url,options.method,JSON.parse(options.body)];return reply(f.started);};
   chatButton(w,'我已完成').click();await idle(w);
   assert.deepEqual(request,['/api/session/remediation-plan/steps/step-1','PATCH',{
     session_id:f.sid,action_id:f.stepAction.action_id,task_version:1,target_subject:'netpilot_host',target_version:1,
     plan_id:'plan-1',plan_version:1,action:'complete',outcome:'unknown',user_note:null,
   }]);
   assert.equal(w.eval('state.remediationPlan.steps[0].status'),'completed');
   assert.equal(w.eval('state.nextChatAction.type'),'verification');
   assert.match(w.document.querySelector('#conversation').textContent,/已记录你完成.*验证修复效果/s);
 },
 'ST-14B-03':async w=>{
   for(const [label,choice] of [['暂时跳过','skip'],['遇到问题','fail']]){
     const f=workflow();install(w,f.base);let body;
     w.document.querySelector('#conversation select').value='improved';
     w.document.querySelector('#conversation textarea').value='说明';
     w.fetch=async(url,options)=>{body=JSON.parse(options.body);return reply({...f.base,next_chat_action:null});};
     chatButton(w,label).click();await idle(w);
     assert.equal(body.action,choice);assert.equal(body.outcome,'unknown');assert.equal(body.user_note,'说明');
     assert.equal(w.document.querySelector('#diagnostic-details-dialog').open,false);
   }
 },
 'ST-14B-04':async w=>{
   const f=workflow();
   for(const [status,label] of Object.entries({
     awaiting_after_evidence:'等待修复后检查结果',verifying:'正在对比修复前后的网络状态',completed:'验证已完成',
     inconclusive:'暂时无法确认修复效果',failed:'本次验证未能完成',
   })){
     const source=['completed','inconclusive'].includes(status)?f.compared:f.started;
     install(w,{...source,verification_cycles:[{...source.verification_cycles[0],status}],next_chat_action:null});
     const card=w.document.querySelector('#conversation .chat-verification-card');
     assert.ok(card.textContent.includes(label));assert.doesNotMatch(card.textContent,new RegExp(status));
     if(status==='completed')assert.match(card.querySelector('table').textContent,/DNS 解析.*异常.*正常.*有改善/s);
   }
 },
 'ST-14B-05':async w=>{
   const f=workflow();install(w,f.started);let release;const sent=[];
   w.fetch=(url,options)=>{sent.push([url,JSON.parse(options.body)]);return new Promise(resolve=>{release=()=>resolve(reply(f.compared));});};
   const start=chatButton(w,'开始验证');start.click();start.click();await tick();
   assert.deepEqual(sent,[['/api/session/verification/verification-1/start',{
     session_id:f.sid,action_id:f.verificationAction.action_id,task_version:2,target_subject:'netpilot_host',target_version:1,
     plan_id:'plan-1',plan_version:1,
   }]]);
   release();await idle(w);assert.equal(start.disabled,true);assert.equal(w.eval('state.detailsOpen'),false);
 },
 'ST-14B-06':async w=>{
   const f=workflow();
   for(const {value,label} of f.confirmAction.choices){
     install(w,f.compared);const sent=[];
     w.fetch=async(url,options)=>{sent.push([url,JSON.parse(options.body)]);return reply(f.resolved);};
     chatButton(w,label).click();await idle(w);
     assert.deepEqual(sent,[['/api/session/resolution/confirm',{
       session_id:f.sid,action_id:f.confirmAction.action_id,task_version:2,target_subject:'netpilot_host',target_version:1,
       status:value,verification_id:'verification-1',resolution_state_version:3,
     }]]);
     assert.equal(w.eval('state.nextChatAction'),null);
   }
 },
 'ST-14B-07':async w=>{
   const f=workflow();install(w,f.base);
   for(const [label,result] of [['我已完成',f.started],['开始验证',f.compared],['已经恢复正常',f.resolved]]){
     w.fetch=async()=>reply(result);
     chatButton(w,label).click();await idle(w);
     assert.equal(w.eval('state.detailsOpen'),false);assert.equal(w.document.querySelector('#diagnostic-details-dialog').open,false);
   }
 },
 'ST-14B-08':async w=>{
   const f=workflow();install(w,f.started);
   assert.equal(w.document.querySelector('#remediation-plan button,#remediation-plan textarea,#verification-content button,#verification-content select,#resolution-content select'),null);
   assert.match(w.document.querySelector('#verification-content').textContent,/before-dns/);
   assert.ok([...w.document.querySelectorAll('#resolution-content button')].some(item=>item.textContent==='请求人工支持'));
 },
 'ST-14B-09':async w=>{
   const sid='11111111-1111-4111-8111-111111111111';
   const f=workflow({sid});w.history.replaceState(null,'',`#session=${sid}`);
   const fetches=[];
   w.fetch=async (url,options)=>{fetches.push([url,options?.method]);return reply(url.includes('/environment/browser')?f.started.environment_profile:f.started);};
   await w.createSession({restore:true,announce:false});
   const restored=chatButton(w,'开始验证');
   w.applyNextChatAction(f.started);
   assert.equal(restored,chatButton(w,'开始验证'));
   assert.equal(fetches.filter(([url])=>url===`/api/session/${sid}`).length,1);
   assert.ok(fetches.every(([,method])=>method !== 'POST'));
 },
 'ST-14B-10':async w=>{
   const f=workflow();install(w,f.started);const stale=chatButton(w,'开始验证');let writes=0;
   w.fetch=async (_url,options)=>{if(options?.method)writes++;return reply({...record,...f.compared,session_id:'old-session'});};
   await w.loadDiagnosisRecord('old');
   stale.dispatchEvent(new w.MouseEvent('click'));
   await w.submitWorkflowAction(f.verificationAction);
   assert.equal(stale.disabled,true);assert.equal(writes,0);
   assert.equal(w.document.querySelector('#conversation button,#verification-content button,#resolution-content select'),null);
 },
 'ST-14B-11':async w=>{
   const f=workflow();install(w,f.base);const first=chatButton(w,'我已完成');
   for(let i=0;i<3;i++)w.applyNextChatAction({...f.base,next_chat_action:{...f.stepAction}});
   assert.equal(first,chatButton(w,'我已完成'));
   assert.equal(w.document.querySelectorAll('#conversation [data-action-id="action-step-1"]').length,1);
 },
 'ST-14B-12':async w=>{
   const f=workflow();install(w,f.base);const old=chatButton(w,'我已完成');const calls=[];
   w.fetch=async(url,options)=>{
     calls.push([url,options?.method]);
     return options.method==='PATCH'?{ok:false,status:409,json:async()=>({detail:'internal'})}:reply(f.started);
   };
   old.click();await idle(w);old.dispatchEvent(new w.MouseEvent('click'));
   assert.deepEqual(calls,[['/api/session/remediation-plan/steps/step-1','PATCH'],['/api/session/current-session',undefined]]);
   assert.equal(old.disabled,true);assert.equal(old.isConnected,false);
   assert.ok(chatButton(w,'开始验证'));assert.match(w.document.querySelector('#conversation').textContent,/这一步已经更新/);
   w.applySessionState({...f.started,task_version:3});
   assert.equal(w.document.querySelector('#conversation [data-action-id]'),null);
 },
 'ST-14B-13':async w=>{
   const f=workflow(),bad='<img src=x onerror=evil()>';
   const plan={...f.base.remediation_plan,steps:[
     {...f.base.remediation_plan.steps[0],title:bad,rationale:bad,instructions:[bad]},
     {...f.base.remediation_plan.steps[1],status:'completed',user_note:bad},
   ]};
   install(w,{...f.base,remediation_plan:plan});
   assert.match(w.document.querySelector('#conversation').textContent,/<img src=x/);
   assert.equal(w.document.querySelector('#conversation img'),null);
   install(w,{...f.compared,verification_cycles:[{...f.compared.verification_cycles[0],result_summary:bad}]});
   assert.match(w.document.querySelector('#conversation .chat-verification-card').textContent,/<img src=x/);
   assert.equal(w.document.querySelector('#conversation img'),null);
 },
 'ST-14B-14':async w=>{
   prepare(w);w.fetch=async()=>reply({});
   w.renderNextChatAction(canonicalCheck);chatButton(w,'开始网络检查').click();
   assert.equal(w.eval('state.clientCheck.mode'),'initial');
   const f=workflow({subject:'user_client'});
   install(w,{...f.started,next_chat_action:{...canonicalCheck,task_version:2,action_id:'recheck',mode:'recheck'}});
   assert.match(w.document.querySelector('#conversation .chat-verification-card').textContent,/这台电脑上重新检查/);
   assert.equal(w.document.querySelectorAll('#conversation .client-check-actions').length,1);
   chatButton(w,'重新检查').click();assert.equal(w.eval('state.clientCheck.mode'),'recheck');
 },
 'ST-14B-15':async w=>{
   const css=fs.readFileSync(path.join(__dirname,'../web/style.css'),'utf8');
   const rules=w.document.createElement('style');rules.textContent=css;w.document.head.append(rules);
   install(w,workflow().compared);
   const card=w.document.querySelector('#conversation .chat-verification-card');
   assert.equal(w.getComputedStyle(card).minWidth,'0px');
   assert.match(css,/max-width: min\(760px, 100%\)/);
   assert.equal(w.getComputedStyle(card.querySelector('.verification-table-scroll')).overflowX,'auto');
   assert.equal(chatButton(w,'已经恢复正常').disabled,false);
 },
 'ST-14B-E2E':async w=>{
   const f=workflow();install(w,{...f.base,remediation_plan:null,verification_cycles:[],next_chat_action:null});
   const calls=[];
   w.fetch=async(url,options)=>{
     if (options?.body) calls.push([url,JSON.parse(options.body)]);
     if(url==='/api/chat/stream')return complete({...f.base,answer:'当前发现 DNS 解析异常。',tool_calls:[],sources:[]});
     if(url.endsWith('/steps/step-1'))return reply(f.started);
     if(url.endsWith('/verification-1/start'))return reply(f.compared);
     if(url==='/api/session/resolution/confirm')return reply(f.resolved);
     return reply({items:[]});
   };
   await w.submitChat(event,{message:'我的微信能用，但是网页打不开，帮我检查一下。'});
   assert.match(w.document.querySelector('#conversation .chat-remediation-card').textContent,/重新连接当前网络/);
   chatButton(w,'我已完成').click();await idle(w);
   chatButton(w,'开始验证').click();await idle(w);
   assert.match(w.document.querySelector('#conversation .verification-table').textContent,/异常.*正常.*有改善/s);
   chatButton(w,'已经恢复正常').click();await idle(w);
   assert.match(w.document.querySelector('#conversation .chat-workflow-status').textContent,/已解决.*关键指标恢复/s);
   assert.equal(calls.length,4);assert.equal(calls[3][1].status,'resolved');
   assert.equal(w.eval('state.detailsOpen'),false);assert.equal(w.document.querySelector('#diagnostic-details-dialog').open,false);
 },
 'ST-14A-01':async w=>{
   prepare(w);w.applyNextChatAction({next_chat_action:canonicalQuestion,ui_action:action});
   assert.equal(w.eval('state.nextChatAction.action_id'),'question-id');
   assert.ok(button(w,'查看问题'));
   assert.equal(w.document.querySelector('.client-check-actions'),null);
 },
 'ST-14A-02':async w=>{
   prepare(w);w.applyNextChatAction({ui_action:question});
   assert.equal(w.eval('state.nextChatAction.session_id'),'current-session');
   assert.equal(w.document.querySelector('.context-choice').disabled,false);
   w.applyNextChatAction({ui_action:action});
   assert.ok(button(w,'开始网络检查'));
 },
 'ST-14A-03':async w=>{
   prepare(w);w.renderNextChatAction(canonicalQuestion);
   const prior=w.document.querySelector('.context-choice');
   w.applyNextChatAction({next_chat_action:null,ui_action:action});
   assert.equal(w.eval('state.nextChatAction'),null);
   assert.equal(prior.disabled,true);
   assert.equal(w.document.querySelector('.client-check-actions'),null);
 },
 'ST-14A-04':async w=>{
   prepare(w);
   for (const original of [canonicalQuestion,canonicalCheck]) {
     for (const [key,value] of Object.entries({session_id:'old-session',task_version:2,target_subject:'netpilot_host',target_version:2,schema_version:2})) {
       w.applyNextChatAction({next_chat_action:{...original,[key]:value}});
       assert.equal(w.eval('state.nextChatAction'),null,key);
     }
     w.renderNextChatAction(original);
     assert.equal(w.eval('state.nextChatAction.action_id'),original.action_id);
     assert.ok(w.document.querySelector(`[data-action-id="${original.action_id}"] button:not(:disabled)`));
   }
 },
 'ST-14A-05':async w=>{
   prepare(w);
   for (const action of [canonicalQuestion,canonicalCheck]) {
     w.applyNextChatAction({next_chat_action:action},w.appendMessage('assistant','首次'));
     const first=w.document.querySelector(`[data-action-id="${action.action_id}"]`);
     w.applyNextChatAction({next_chat_action:{...action}},w.appendMessage('assistant','重复'));
     w.applyNextChatAction({next_chat_action:{...action}});
     assert.deepEqual([...w.document.querySelectorAll(`[data-action-id="${action.action_id}"]`)], [first]);
   }
 },
 'ST-14A-06':async w=>{
   prepare(w);w.renderNextChatAction(canonicalQuestion);
   const prior=w.document.querySelector('.context-choice');
   w.applySessionState({task_version:2,diagnostic_target:target});w.setBusy(false);
   assert.equal(w.eval('state.nextChatAction'),null);assert.equal(prior.disabled,true);
   let calls=0;w.fetch=async()=>{calls++;};
   prior.dispatchEvent(new w.MouseEvent('click'));await tick();assert.equal(calls,0);
 },
 'ST-14A-07':async w=>{
   prepare(w);w.renderNextChatAction(canonicalQuestion);w.renderNextChatAction({...canonicalQuestion});
   const sent=[];
   w.fetch=async(url,options)=>{
     if (url==='/api/chat/stream') {
       sent.push(JSON.parse(options.body));
       return complete({answer:'已记录',next_chat_action:null,ui_action:question,tool_calls:[],sources:[],reasoning_trace:[]});
     }
     return reply({items:[]});
   };
   const choice=w.document.querySelector('.context-choice');choice.click();choice.click();
   for(let i=0;i<8;i++)await tick();
   assert.equal(sent.length,1);
   assert.deepEqual(sent[0].context_answer,{field:'network_access',value:'campus_wifi',action_id:'question-id',task_version:1,target_version:1});
   assert.equal(choice.disabled,true);assert.equal(w.eval('state.nextChatAction'),null);
 },
 'ST-14A-08':async w=>{
   prepare(w);w.renderNextChatAction(canonicalQuestion);
   const choice=w.document.querySelector('.context-choice');let writes=0, restores=0;
   w.fetch=async(url,options)=>{
     if (options?.method==='POST') writes++;
     if (url==='/api/session/current-session') {
       restores++;
       return reply({session_id:'current-session',task_version:1,diagnostic_target:target,next_chat_action:canonicalQuestion});
     }
     return reply({...record,next_chat_action:{...canonicalCheck,session_id:'old-session'}});
   };
   await w.loadDiagnosisRecord('old');
   assert.equal(choice.disabled,true);assert.equal(w.document.querySelector('.context-choices,.client-check-actions'),null);
   choice.dispatchEvent(new w.MouseEvent('click'));await w.declineClientCheck();await w.uploadClientCheck();
   assert.equal(writes,0);
   await w.closeHistoryView();assert.equal(restores,1);
   assert.equal(w.document.querySelector('.context-choice'),choice);assert.equal(choice.disabled,false);
 },
 'ST-14A-09':async w=>{
   prepare(w);w.renderNextChatAction(canonicalQuestion);const prior=w.document.querySelector('.context-choice');
   w.fetch=async url=>url==='/api/session'
     ? reply({session_id:'new-session',task_version:1,diagnostic_target:target,next_chat_action:null})
     : reply({os_family:'windows'});
   await w.createSession({announce:false});
   assert.equal(w.eval('state.sessionId'),'new-session');assert.equal(w.eval('state.nextChatAction'),null);
   assert.equal(prior.isConnected,false);assert.equal(prior.disabled,true);
 },
 'ST-14A-10':async w=>{
   prepare(w);w.fetch=async()=>reply({});
   w.renderNextChatAction(canonicalCheck);button(w,'开始网络检查').click();
   assert.equal(w.eval('state.clientCheck.mode'),'initial');
   w.renderNextChatAction({...canonicalCheck,mode:'recheck',action_id:'recheck-id'});button(w,'重新检查').click();
   assert.equal(w.eval('state.clientCheck.mode'),'recheck');
   const previous=w.document.querySelector('[data-action-id="recheck-id"] button');
   w.fetch=async url=>url==='/api/session/client-check/decline'
     ? {ok:false,status:409,json:async()=>({detail:'这次网络检查已失效。'})}
     : reply({session_id:'current-session',task_version:2,diagnostic_target:target,next_chat_action:null});
   await w.declineClientCheck();
   assert.equal(w.eval('state.taskVersion'),2);assert.equal(previous.disabled,true);
   w.renderNextChatAction(canonicalCheck);assert.equal(w.document.querySelector('#client-check-dialog').open,false);
   put(w,'state.isDemo=true');w.renderNextChatAction({...canonicalCheck,task_version:2});
   assert.equal(w.eval('state.nextChatAction'),null);assert.equal(w.document.querySelector('#client-check-launch').hidden,true);
 },
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
   assert.equal(typeof w.renderContextQuestion,'function');assert.equal(typeof w.renderNextChatAction,'function');
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
 'ST-CONTEXT':async w=>{prepare(w);render(w,w.appendMessage('assistant',question.question),question);w.setBusy(false);assert.ok(w.document.querySelector('.context-choices').closest('#conversation'));assert.ok(button(w,'查看问题'));button(w,'查看问题').click();assert.ok(w.document.activeElement.classList.contains('context-choice'));assert.equal(w.document.querySelector('#diagnostic-details-dialog').open,false);},
 'ST-CHECK':async w=>{prepare(w);render(w,w.appendMessage('assistant','需要检查'),action);w.setBusy(false);assert.ok(w.document.querySelector('.client-check-actions').closest('#conversation'));button(w,'开始网络检查').click();assert.equal(w.document.querySelector('#client-check-dialog').open,true);assert.equal(w.eval('state.clientCheck.mode'),'initial');},
 'ST-RECHECK':async w=>{prepare(w);put(w,`state.verificationCycles=[{target_subject:'user_client',target_version:1,status:'awaiting_after_evidence'}]`);render(w,null,{...action,mode:'recheck'});w.setBusy(false);button(w,'重新检查').click();assert.equal(w.eval('state.clientCheck.mode'),'recheck');assert.match(w.document.querySelector('#client-check-title').textContent,/重新检查/);},
 'ST-STALE-ACTION':async w=>{prepare(w);render(w,null,{...action,target_version:2});w.setBusy(false);assert.equal(button(w,'开始网络检查'),undefined);assert.equal(button(w,'重新检查'),undefined);},
 'ST-PLAN':async w=>{const f=workflow();install(w,f.base);button(w,'定位当前步骤').click();assert.equal(w.document.activeElement.textContent,'我已完成');assert.equal(w.document.querySelector('#diagnostic-details-dialog').open,false);w.applySessionState({remediation_plan:{...f.base.remediation_plan,status:'superseded'}});w.setBusy(false);assert.equal(button(w,'定位当前步骤'),undefined);},
 'ST-VERIFICATION':async w=>{const f=workflow();install(w,{...f.compared,next_chat_action:null});assert.match(w.document.querySelector('#case-next-action').textContent,/验证已完成/);assert.match(w.document.querySelector('#conversation .verification-table').textContent,/异常.*正常/s);assert.equal(button(w,'查看对比'),undefined);assert.equal(w.document.querySelector('#diagnostic-details-dialog').open,false);},
 'ST-RESOLUTION':async w=>{prepare(w);for(const [status,label] of Object.entries({diagnosing:'诊断中',resolved:'已解决',unresolved:'仍未解决',escalated:'建议报修'})){put(w,`state.resolution={state:'${status}'}`);w.renderResolution(w.eval('state.resolution'));w.setBusy(false);assert.equal(w.document.querySelector('#resolution-badge').textContent,label);}assert.ok(button(w,'生成报修材料'));},
 'ST-ESCALATION':async w=>{prepare(w);put(w,"state.resolution={state:'escalated',escalation_recommended:true}");w.setBusy(false);let calls=0;w.fetch=async(u,o)=>{assert.equal(u,'/api/session/escalation-package');assert.deepEqual(JSON.parse(o.body),{session_id:'current-session'});calls++;return reply({packages:[]});};button(w,'生成报修材料').click();await tick();assert.equal(calls,1);assert.equal(w.document.querySelector('#diagnostic-details-dialog').open,true);},
 'ST-HISTORY-RETURN':async w=>{
   prepare(w);const body=w.appendMessage('assistant','当前问题');render(w,body,action);w.setBusy(false);
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
   w.document.querySelector('#message-input').value='不能发送';await w.submitChat(event);await w.saveEnvironment(event);await w.saveDiagnosticTarget(event);await w.uploadClientSnapshot(event);await w.generateRemediationPlan();await w.workflowRequest('/api/session/verification','POST',{});await w.generateEscalation();await w.demoOperation('/api/demo/session',{});await w.createCustomScenario(event);await w.switchScenario();
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
