"use strict";
const assert = require("node:assert/strict");
const { setup, step } = require("./web_markdown_runtime.cjs");
const trace = ["intent", "planning", "decision"].map((phase, index) => ({
  step_index: index + 1, phase, title: ["识别任务", "制定检测计划", "继续检测"][index],
  summary: "依据 Coverage 决策，不复制 Tool JSON。", evidence_ids: index === 2 ? ["E1", "E2"] : [],
  turn_index: 1, task_version: 1, created_at: "2026-10-18T00:00:00Z",
}));

const cases = {
  "RT-13": async (w) => {
    const section = w.document.querySelector("#reasoning-section");
    assert.equal(section.tagName, "DETAILS");
    assert.equal(section.open, false);
    assert.ok(section.compareDocumentPosition(w.document.querySelector("#timeline-section")) & w.Node.DOCUMENT_POSITION_FOLLOWING);
    w.renderReasoningTrace(trace);
    assert.equal(w.document.querySelector("#reasoning-count").textContent, "3");
    section.querySelector("summary").click();
    assert.equal(section.open, true);
    w.renderReasoningTrace([...trace]);
    assert.equal(section.open, true);
    section.querySelector("summary").click();
    assert.equal(section.open, false);
    assert.equal(section.querySelectorAll("li").length, 3);
  },
  "RT-14": async (w) => {
    w.renderTools([step(1), step(2), step(3), step(4)]);
    w.renderReasoningTrace([
      ...trace,
      { ...trace[0], step_index: 4, title: '<img src=x onerror=alert(1)>', summary: '<script>window.pwned=1</script>', extra_raw_tool: { private: "DO_NOT_RENDER" } },
    ]);
    const box = w.document.querySelector("#reasoning-trace");
    assert.equal(box.querySelector("pre,details,img,script"), null);
    assert.ok(box.textContent.includes("<script>"));
    assert.ok(!box.textContent.includes("DO_NOT_RENDER"));
    assert.ok(!box.textContent.includes("TEST_ERROR"));
    assert.ok(box.textContent.includes("关联证据：2"));
    assert.equal(w.pwned, undefined);
    assert.ok(!w.document.querySelector("#tool-timeline").contains(box));
  },
  "RT-HISTORY": async (w) => {
    w.appendTurnReasoningTrace(trace.slice(0, 1));
    w.document.querySelector("#reasoning-section").open = true;
    const history = trace.map((item) => ({ ...item, step_index: item.step_index + 100 }));
    const record = { record_id:"history", updated_at:"2026-10-18T00:00:00Z", turn_count:2,
      conversation_complete:true, sources:[], tool_calls:[], diagnosis:null, metrics:null,
      reasoning_trace:history, conversation_turns:[1,2].map((index) => ({ user_message:`U${index}`, assistant_answer:`A${index}` })),
    };
    w.fetch = async () => ({ ok:true, json:async () => record });
    await w.loadDiagnosisRecord("history");
    assert.equal(w.document.querySelectorAll("#conversation .message").length, 4);
    assert.equal(w.document.querySelector("#reasoning-count").textContent, "3");
    assert.equal(w.document.querySelector("#reasoning-section").open, false);
    // Browsing history must not contaminate the active Session's trace.
    w.appendTurnReasoningTrace([trace[1]]);
    assert.equal(w.document.querySelector("#reasoning-count").textContent, "2");
    await w.loadDiagnosisRecord("legacy");
  },
  "RT-SSE": async (w) => {
    w.appendTurnReasoningTrace(trace.slice(0, 1));
    w.document.querySelector("#reasoning-section").open = true;
    let index = 0;
    const payload = { answer:"**依据证据**完成本轮。", sources:[], tool_calls:[], diagnosis:null, metrics:null, reasoning_trace:trace.slice(1) };
    const events = ['event: delta\ndata: {"text":"回答"}\n\n', `event: complete\ndata: ${JSON.stringify({ response:payload })}\n\n`];
    w.fetch = async (url) => url.startsWith("/api/diagnoses?")
      ? { ok:true, json:async () => ({items:[]}) }
      : { ok:true, headers:{ get:() => "text/event-stream" }, body:{ getReader:() => ({read:async () => {
        if (index === 1) assert.equal(w.document.querySelector("#reasoning-count").textContent, "1");
        return index < events.length ? {done:false, value:new TextEncoder().encode(events[index++])} : {done:true};
      }})}};
    w.document.querySelector("#message-input").value = "基于刚才结果继续分析";
    await w.submitChat({preventDefault(){}});
    assert.equal(w.document.querySelector("#reasoning-count").textContent, "3");
    assert.equal(w.document.querySelector("#reasoning-section").open, true);
    assert.ok(w.document.querySelector(".assistant-message strong"));
  },
  "RT-RESET": async (w) => {
    w.eval("state.health.reasoning_trace_max_steps = 2");
    w.appendTurnReasoningTrace(trace);
    assert.equal(w.document.querySelector("#reasoning-count").textContent, "2");
    w.document.querySelector("#reasoning-section").open = true;
    w.resetConversation();
    assert.equal(w.document.querySelector("#reasoning-count").textContent, "0");
    assert.equal(w.document.querySelector("#reasoning-section").open, false);
    assert.equal(w.eval("state.reasoningTrace.length"), 0);
  },
};

(async () => {
  for (const name of process.argv[2] ? [process.argv[2]] : Object.keys(cases)) {
    const dom = await setup();
    try { await cases[name](dom.window); console.log(`${name} passed`); }
    finally { dom.window.close(); }
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
