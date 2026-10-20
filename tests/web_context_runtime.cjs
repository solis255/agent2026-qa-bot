"use strict";
const assert = require("node:assert/strict");
const {setup} = require("./web_markdown_runtime.cjs");
const question = {type:"context_question", field:"network_access", question:"你现在连接的是哪种网络？", choices:[{value:"campus_wifi",label:"校园 WiFi"},{value:"unknown",label:"不清楚"}],allow_free_text:true};
const tick = () => new Promise(setImmediate);
function sse(payload) {
  let sent=false;
  return {ok:true,headers:{get:()=>"text/event-stream"},body:{getReader:()=>({read:async()=>{
    if(sent)return {done:true};sent=true;
    return {done:false,value:new TextEncoder().encode(`event: complete\ndata: ${JSON.stringify({response:payload})}\n\n`)};
  },cancel:async()=>{}})}};
}
const cases = {
  "CTX-RENDER":async w=>{const body=w.appendMessage("assistant",question.question);w.renderContextQuestion(body,question);w.setBusy(false);const group=w.document.querySelector(".context-choices");assert.equal(group.getAttribute("role"),"group");assert.equal(group.querySelectorAll("button").length,2);assert.equal(group.querySelector("button").type,"button");assert.equal(w.document.querySelector("#environment-card").open,false);},
  "CTX-SUBMIT":async w=>{const body=w.appendMessage("assistant",question.question);w.renderContextQuestion(body,question);w.setBusy(false);let release;let calls=0;let sent;w.fetch=async(url,options)=>{assert.equal(url,"/api/chat/stream");calls++;sent=JSON.parse(options.body);return new Promise(resolve=>{release=()=>resolve(sse({answer:"已记录",redacted_user_message:"校园 WiFi",ui_action:null,tool_calls:[],sources:[],reasoning_trace:[]}));});};const button=w.document.querySelector(".context-choice");button.click();button.click();await tick();assert.equal(calls,1);assert.equal(button.disabled,true);assert.deepEqual(sent.context_answer,{field:"network_access",value:"campus_wifi"});assert.equal(sent.message,"校园 WiFi");release();for(let i=0;i<8;i++)await tick();assert.equal(button.disabled,true);assert.equal(button.getAttribute("aria-pressed"),"true");assert.match(w.document.querySelector("#conversation").textContent,/已记录/);},
  "CTX-FAILURE-RETRY":async w=>{w.renderContextQuestion(w.appendMessage("assistant","问题"),question);w.setBusy(false);w.fetch=async()=>({ok:false,status:503,json:async()=>({detail:"稍后重试"})});const button=w.document.querySelector(".context-choice");button.click();for(let i=0;i<8;i++)await tick();assert.equal(button.disabled,false);assert.equal(button.getAttribute("aria-pressed"),"false");},
  "CTX-STALE-AUTH":async w=>{w.renderContextQuestion(w.appendMessage("assistant","问题"),question);const button=w.document.querySelector(".context-choice");w.renderContextQuestion(w.appendMessage("assistant","新问题"),question);w.setBusy(false);let calls=0;w.fetch=async()=>{calls++;};button.click();assert.equal(calls,0);assert.equal(button.disabled,true);w.showAuthGate();assert.equal(w.document.querySelector(".context-choices"),null);},
  "CTX-PROVENANCE":async w=>{w.renderEnvironmentProfile({os_family:"windows",network_access:"campus_wifi",vpn_enabled:null,affected_scope:"web_only",field_sources:{os_family:{source:"user",confidence:"high"},network_access:{source:"user",confidence:"high"}}});const text=w.document.querySelector("#environment-provenance").textContent;assert.match(text,/Windows · 来源：用户 · 置信度：高/);assert.match(text,/校园 WiFi · 来源：用户/);assert.match(text,/VPN：未知/);},
  "CTX-TEXT-SAFETY":async w=>{w.renderContextQuestion(w.appendMessage("assistant","问题"),{...question,choices:[{value:"unknown",label:'<img src=x onerror="alert(1)">'}]});assert.equal(w.document.querySelector(".context-choices img"),null);assert.match(w.document.querySelector(".context-choice").textContent,/<img/);},
};
(async()=>{for(const name of process.argv[2]?[process.argv[2]]:Object.keys(cases)){const dom=await setup();try{await cases[name](dom.window);console.log(`${name} passed`);}finally{dom.window.close();}}})().catch(error=>{console.error(error);process.exitCode=1;});
