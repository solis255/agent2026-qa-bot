"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { setup } = require("./web_markdown_runtime.cjs");
const sid = "11111111-1111-4111-8111-111111111111";
const profile = {client_mode:"mock", os_family:"windows", network_access:"campus_wifi", vpn_enabled:false, proxy_enabled:null, affected_scope:"web_only", browser_online:true, browser_language:"zh-CN", field_sources:{os_family:{source:"browser",confidence:"medium"}}};
const reply = (body, status=200) => ({ok:status < 400, status, json:async () => body});
const plain = (value) => JSON.parse(JSON.stringify(value));
const cases = {
  "EP-BROWSER": async (w) => {
    Object.defineProperty(w.navigator, "userAgentData", {value:{platform:"Windows"}, configurable:true});
    Object.defineProperty(w.navigator, "connection", {value:{effectiveType:"4g",rtt:50,downlink:10.2}, configurable:true});
    Object.defineProperty(w.navigator, "language", {value:"zh-CN", configurable:true});
    const values = plain(w.collectBrowserEnvironment());
    assert.equal(values.os_family, "windows");
    assert.equal(values.browser_online, true);
    assert.equal(values.browser_language, "zh-CN");
    assert.equal(values.effective_type, "4g");
    assert.equal(values.estimated_downlink_mbps, 10.2);
    assert.deepEqual(Object.keys(values).sort(), ["browser_language","browser_online","effective_type","estimated_downlink_mbps","estimated_rtt_ms","os_family"]);
    assert.equal(values.network_access, undefined);
    assert.equal(values.vpn_enabled, undefined);
  },
  "EP-UNSUPPORTED": async (w) => {
    Object.defineProperty(w.navigator, "connection", {value:undefined});
    Object.defineProperty(w.navigator, "userAgentData", {value:undefined});
    const values = plain(w.collectBrowserEnvironment());
    assert.equal(values.effective_type, undefined);
    assert.equal(values.estimated_rtt_ms, undefined);
    assert.equal(values.estimated_downlink_mbps, undefined);
    assert.equal(values.os_family, "unknown");
  },
  "EP-EDIT": async (w) => {
    w.eval(`state.environmentProfile = ${JSON.stringify(profile)}`);
    w.renderEnvironmentProfile(profile);
    const d = w.document;
    assert.equal(d.querySelector("#environment-proxy").value, "");
    d.querySelector("#environment-os").value = "macos";
    d.querySelector("#environment-scope").value = "single_service";
    d.querySelector("#environment-scope").dispatchEvent(new w.Event("change"));
    assert.equal(d.querySelector("#environment-service-label").hidden, false);
    d.querySelector("#environment-service").value = "github.com";
    let sent;
    w.fetch = async (url, options) => {
      assert.equal(url, "/api/session/environment/user");
      sent = JSON.parse(options.body);
      return reply({...profile,...sent,field_sources:{os_family:{source:"user",confidence:"high"}}});
    };
    await w.saveEnvironment({preventDefault(){}});
    assert.deepEqual(sent, {session_id:"current-session",os_family:"macos",affected_scope:"single_service",affected_service:"github.com"});
    assert.equal(d.querySelector("#environment-proxy").value, "");
    assert.match(d.querySelector("#environment-summary").textContent, /macOS.*VPN 关闭.*Proxy 未知/);
    assert.match(d.querySelector("#environment-status").textContent, /已保存到服务端/);
    // Confirming the same displayed value must still acquire user provenance.
    const os = d.querySelector("#environment-os");
    os.dispatchEvent(new w.Event("change", {bubbles:true}));
    await w.saveEnvironment({preventDefault(){}});
    assert.equal(sent.os_family,"macos");
    assert.equal(sent.proxy_enabled,undefined);
  },
  "EP-REFRESH": async (w) => {
    // Simulate reload: no in-memory profile; only opaque Session ID survives in URL.
    w.history.replaceState(null,"",`#session=${sid}`);
    w.eval("state.environmentProfile = null; state.sessionId = null;");
    const urls = [];
    w.fetch = async (url) => {
      urls.push(url);
      if (url === `/api/session/${sid}`) return reply({session_id:sid,environment_profile:profile});
      if (url === "/api/session/environment/browser") return reply(profile);
      throw new Error(`Unexpected request ${url}`);
    };
    await w.createSession({announce:false,restore:true});
    assert.deepEqual(urls, [`/api/session/${sid}`,"/api/session/environment/browser"]);
    assert.equal(w.eval("state.environmentProfile.network_access"), "campus_wifi");
    assert.equal(w.eval("state.environmentProfile.vpn_enabled"), false);
    assert.equal(w.eval("state.environmentProfile.proxy_enabled"), null);
    assert.match(w.document.querySelector("#environment-summary").textContent, /校园 WiFi/);
    assert.equal(w.localStorage.length, 0);
    assert.equal(w.sessionStorage.length, 0);
  },
  "EP-ISOLATION": async (w) => {
    w.history.replaceState(null,"",`#session=${sid}`);
    const newSid = "22222222-2222-4222-8222-222222222222";
    const fresh = {os_family:"unknown", network_access:"unknown", vpn_enabled:null, proxy_enabled:null};
    w.fetch = async (url) => {
      if (url === `/api/session/${sid}`) return reply({detail:"会话不存在"},404);
      if (url === "/api/session") return reply({session_id:newSid, environment_profile:fresh});
      return reply(fresh);
    };
    await w.createSession({announce:false,restore:true});
    assert.equal(w.eval("state.sessionId"),newSid);
    assert.equal(w.eval("state.environmentProfile.vpn_enabled"),null);
    assert.equal(w.location.hash,`#session=${newSid}`);
  },
  "EP-HISTORY": async (w) => {
    w.eval(`state.environmentProfile = ${JSON.stringify(profile)}`);
    w.fetch = async () => reply({record_id:"old",turn_count:1,environment_profile:{...profile,os_family:"linux"},conversation_turns:[],tool_calls:[],sources:[]});
    await w.loadDiagnosisRecord("old");
    assert.match(w.document.querySelector("#environment-summary").textContent, /历史环境：Linux/);
    assert.equal(w.document.querySelector("#environment-save").disabled,true);
    assert.equal(w.eval("state.environmentProfile.os_family"),"windows");
    w.resetConversation();
    assert.match(w.document.querySelector("#environment-summary").textContent, /^Windows/);
    assert.match(w.formatReportPreview({environment_profile:profile}), /用户环境：Windows/);
  },
  "EP-RESET": async (w) => {
    w.eval(`state.environmentProfile = ${JSON.stringify(profile)}`);
    w.showAuthGate();
    assert.equal(w.eval("state.environmentProfile"),null);
    assert.equal(w.document.querySelector("#environment-save").disabled,true);
    assert.match(w.document.querySelector("#environment-summary").textContent, /VPN 未知/);
  },
  "EP-PRIVACY": async (w) => {
    Object.defineProperty(w.navigator,"geolocation",{get(){throw new Error("Must not access location");}});
    Object.defineProperty(w.navigator,"userAgent",{get(){throw new Error("Must not access full User-Agent");}});
    w.collectBrowserEnvironment();
    w.renderEnvironmentProfile({...profile,browser_language:"<img src=x onerror=evil()>"});
    assert.equal(w.document.querySelector("#environment-card img"),null);
    const app = fs.readFileSync(path.join(__dirname,"../web/app.js"),"utf8");
    assert.ok(!/navigator\.geolocation|navigator\.userAgent\b|localStorage|sessionStorage/.test(app));
  },
};
(async () => {
  for (const name of process.argv[2] ? [process.argv[2]] : Object.keys(cases)) {
    const dom = await setup();
    try { await cases[name](dom.window); console.log(`${name} passed`); }
    finally { dom.window.close(); }
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
