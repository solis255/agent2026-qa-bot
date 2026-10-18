"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { JSDOM } = require("../web/node_modules/jsdom");
const web = path.join(__dirname, "..", "web");
const tick = () => new Promise((resolve) => setImmediate(resolve));
const markdown = "# 标题\n\n这是 **重点**。\n\n### 小标题\n\n" +
  "| 类型 | 可信度 |\n|---|---|\n| official | 高 |\n\n" +
  "- 先认证\n- 再连接\n\n> 参考说明\n\n```text\n只读工具\n```";

async function setup() {
  // No CDN or network resource loading. Load exactly the bundles served by FastAPI.
  const dom = new JSDOM(fs.readFileSync(path.join(web, "index.html"), "utf8"), {
    url: "http://netpilot.test/", runScripts: "outside-only",
  });
  const w = dom.window;
  w.TextDecoder = TextDecoder;
  w.fetch = async () => ({ ok: false, status: 401, json: async () => ({ detail: "请登录" }) });
  for (const file of ["vendor/marked.umd.js", "vendor/purify.min.js", "markdown.js", "app.js"]) {
    vm.runInContext(fs.readFileSync(path.join(web, file), "utf8"), dom.getInternalVMContext(), { filename: file });
  }
  await tick();
  w.eval('state.user = {id: "test-user"}; state.sessionId = "current-session"; state.health = {llm_configured: true};');
  return dom;
}

const cases = {
  "MD-01": async (w) => {
    const body = w.appendMessage("assistant", markdown);
    assert.equal(body.tagName, "DIV");
    assert.ok(body.classList.contains("markdown-body"));
    assert.equal(body.querySelector("h1").textContent, "标题");
    assert.equal(body.querySelector("strong").textContent, "重点");
    assert.ok(!body.textContent.includes("#") && !body.textContent.includes("**"));
    assert.equal(body.querySelectorAll("li").length, 2);
    assert.ok(body.querySelector("blockquote"));
    assert.equal(body.querySelector("pre code").textContent.trim(), "只读工具");
  },
  "MD-02": async (w) => {
    const body = w.appendMessage("assistant", markdown);
    assert.equal(body.querySelector("table tbody td").textContent, "official");
    assert.equal(body.querySelectorAll("th").length, 2);
    assert.ok(!body.textContent.includes("|---|"));
  },
  "MD-03": async (w) => {
    const raw = '<script>alert(1)</script>\n**hello**';
    for (const role of ["user", "error"]) {
      const body = w.appendMessage(role, raw);
      assert.equal(body.textContent, raw);
      assert.equal(body.childElementCount, 0);
      assert.equal(body.tagName, "P");
    }
  },
  "MD-04": async (w) => {
    const body = w.appendMessage("assistant", [
      '<img src=x onerror="window.pwned=1"><script>window.pwned=1</script>',
      '<iframe srcdoc="<script>alert(1)</script>"></iframe><object data="x"></object><embed src="x">',
      '<svg onload="window.pwned=1"><a href="javascript:alert(1)">bad</a></svg>',
      '<math><mtext><table><mglyph><style><!--</style><img title="--><img src=x onerror=alert(1)>">',
      '<p onclick="window.pwned=1" style="color:red" id="x" name="x">safe</p>',
      '<a href="java&#x09;script:alert(1)" onmouseover="alert(1)">bad</a>',
    ].join("\n"));
    assert.equal(body.querySelector("script,iframe,object,embed,img,svg,math,style"), null);
    for (const element of body.querySelectorAll("*")) {
      for (const attribute of element.attributes) {
        assert.ok(!/^on/i.test(attribute.name));
        assert.ok(!["style", "id", "name"].includes(attribute.name));
        assert.ok(!/javascript:/i.test(attribute.value));
      }
    }
    assert.equal(w.pwned, undefined);
    // Dependency failure must never cause raw HTML insertion.
    w.DOMPurify = undefined;
    w.renderAssistantMarkdown(body, "<img src=x onerror=alert(1)>");
    assert.equal(body.childElementCount, 0);
  },
  "MD-05": async (w) => {
    const body = w.appendMessage("assistant",
      '[天津大学](https://www.tju.edu.cn) [HTTP](http://example.test) ' +
      '[evil](javascript:alert%281%29) [data](data:text/html,evil) [mail](mailto:test@test) ' +
      '[relative](/api/auth/logout) [protocol-relative](//evil.test)');
    const links = body.querySelectorAll("a");
    assert.equal(links.length, 2);
    assert.equal(links[0].href, "https://www.tju.edu.cn/");
    for (const link of links) {
      assert.equal(link.target, "_blank");
      assert.equal(link.rel, "noopener noreferrer");
    }
    assert.ok(body.textContent.includes("evil"));
  },
  "MD-06": async (w) => {
    let index = 0;
    const payload = { answer: markdown, diagnosis: null, metrics: null, tool_calls: [], sources: [] };
    const blocks = [
      'event: start\ndata: {}\n\n',
      `event: delta\ndata: ${JSON.stringify({ text: "# 标题\n\n**未完成" })}\n\n`,
      `event: complete\ndata: ${JSON.stringify({ response: payload })}\n\n`,
    ];
    w.fetch = async (url) => {
      if (url.startsWith("/api/diagnoses?")) return { ok: true, json: async () => ({ items: [] }) };
      assert.equal(url, "/api/chat/stream");
      return {
        ok: true, headers: { get: () => "text/event-stream" },
        body: { getReader: () => ({ read: async () => {
          if (index === 2) {
            const body = w.document.querySelector(".assistant-message .message-body");
            assert.equal(body.textContent, "# 标题\n\n**未完成");
            assert.equal(body.querySelector("h1"), null);
          }
          return index < blocks.length
            ? { value: new TextEncoder().encode(blocks[index++]), done: false }
            : { done: true };
        } }) },
      };
    };
    w.document.querySelector("#message-input").value = "请检索 VPN 资料";
    await w.submitChat({ preventDefault() {} });
    const body = w.document.querySelector(".assistant-message .message-body");
    assert.equal(body.querySelector("h1").textContent, "标题");
    assert.equal(body.querySelector("strong").textContent, "重点");
    assert.ok(body.querySelector("table"));
    assert.ok(!body.classList.contains("is-streaming"));
  },
  "MD-07": async (w) => {
    const live = w.appendMessage("assistant", markdown).cloneNode(true);
    const record = {
      record_id: "record", updated_at: "2026-10-18T00:00:00Z", turn_count: 2,
      conversation_complete: true, diagnosis: null, metrics: null, tool_calls: [], sources: [],
      conversation_turns: [1, 2].map((turn_index) => ({
        turn_index, user_message: "**用户原文**", assistant_answer: markdown,
      })),
    };
    w.fetch = async () => ({ ok: true, json: async () => record });
    await w.loadDiagnosisRecord("record");
    const bodies = w.document.querySelectorAll(".assistant-message .message-body");
    assert.equal(bodies.length, 2);
    for (const body of bodies) assert.equal(body.innerHTML, live.innerHTML);
    for (const body of w.document.querySelectorAll(".user-message .message-body")) {
      assert.equal(body.textContent, "**用户原文**");
      assert.equal(body.childElementCount, 0);
    }
    assert.equal(w.eval("state.sessionId"), "current-session");
  },
};

const sources = ["official", "community", "maintainer"].map((source_type, index) => ({
  source_ref: ["abc", "def", "ghi"][index], source_type, title: `资料 ${index}`,
  source: `https://example.test/${index}`, score: .9, file: `file-${index}.md`, chunk_id: `chunk-${index}`,
}));
const step = (index) => ({
  tool_name: "dns_lookup", finding_status: "abnormal", round: index,
  duration_ms: 7, tool_call_id: `tool-${index}`, summary: "DNS 异常",
  arguments: { domain: "example.test" }, data: { resolved: false }, error_code: "TEST_ERROR",
});
const links = (body) => [...body.querySelectorAll(".inline-citation")];
Object.assign(cases, {
  "UI-01": async (w) => {
    const timeline = w.document.querySelector("#timeline-section");
    assert.equal(timeline.tagName, "DETAILS");
    assert.equal(timeline.open, false);
    w.renderTools([step(1)]);
    assert.equal(timeline.open, false);
    assert.equal(w.document.querySelector("#timeline-count").textContent, "1");
    assert.ok(timeline.querySelector("pre").textContent.includes("TEST_ERROR"));
  },
  "UI-02": async (w) => {
    w.renderTools([step(1)]);
    const timeline = w.document.querySelector("#timeline-section");
    const summary = timeline.querySelector("summary");
    summary.click();
    assert.equal(timeline.open, true);
    summary.click();
    assert.equal(timeline.open, false);
    assert.equal(timeline.querySelectorAll("li").length, 1);
  },
  "UI-03": async (w) => {
    const timeline = w.document.querySelector("#timeline-section");
    timeline.querySelector("summary").click();
    w.renderTools([step(1)]);
    w.renderTools([step(1), step(2)]);
    assert.equal(timeline.open, true);
    assert.equal(w.document.querySelector("#timeline-count").textContent, "2");
    assert.equal(timeline.querySelectorAll("li").length, 2);
    w.resetConversation();
    assert.equal(timeline.open, false);
    assert.equal(w.document.querySelector("#timeline-count").textContent, "0");
  },
  "CIT-01": async (w) => {
    const body = w.appendMessage("assistant", "校园网官方说明。[[cite:abc]]", sources);
    assert.equal(body.textContent.trim(), "校园网官方说明。[1]");
    const link = links(body)[0];
    assert.equal(link.href, sources[0].source);
    assert.equal(link.target, "_blank");
    assert.equal(link.rel, "noopener noreferrer");
    assert.equal(link.getAttribute("aria-label"), "来源 1：Official，资料 0");
    assert.ok(link.title.includes("example.test"));
  },
  "CIT-02": async (w) => {
    const body = w.appendMessage("assistant", "共同支撑。[[cite:abc,def,abc]]", sources);
    assert.equal(body.textContent.trim(), "共同支撑。[1][2]");
    assert.ok(links(body)[1].title.includes("Community"));
  },
  "CIT-03": async (w) => {
    const body = w.appendMessage("assistant", "第一段[[cite:abc]]\n\n第二段[[cite:abc]]", sources);
    assert.deepEqual(links(body).map((link) => link.textContent), ["[1]", "[1]"]);
    assert.equal(links(body)[0].href, links(body)[1].href);
  },
  "CIT-04": async (w) => {
    const body = w.appendMessage("assistant", "C[[cite:ghi]]\n\nA[[cite:abc]]\n\nC[[cite:ghi]]", sources);
    assert.deepEqual(links(body).map((link) => [link.textContent, link.href]),
      [["[1]", sources[2].source], ["[2]", sources[0].source], ["[1]", sources[2].source]]);
    assert.ok(links(body)[0].title.includes("Maintainer"));
  },
  "CIT-05": async (w) => {
    const body = w.appendMessage("assistant", "安全[[cite:not-exist]][[cite:abc]] 未完成[[cite:garbage", sources);
    assert.equal(links(body).length, 1);
    assert.equal(links(body)[0].textContent, "[1]");
    assert.ok(!body.textContent.includes("[[cite:"));
    const conflict = w.appendMessage("assistant", "冲突[[cite:abc]]", [sources[0], { ...sources[0], source: "https://evil.test" }]);
    assert.equal(links(conflict).length, 0);
  },
  "CIT-06": async (w) => {
    for (const source of ["javascript:alert(1)", "data:text/html,x", "file:///x", "//evil.test", "/relative", "java\tscript:alert(1)"]) {
      const body = w.appendMessage("assistant", "安全[[cite:abc]]", [{ ...sources[0], source, title: '<img src=x onerror=alert(1)>' }]);
      assert.equal(body.querySelectorAll("a,img,script").length, 0);
      const citation = links(body)[0];
      assert.equal(citation.textContent, "[1]");
      assert.ok(citation.title.includes("链接不可用"));
      assert.equal(citation.getAttribute("onerror"), null);
    }
  },
  "CIT-07": async (w) => {
    const body = w.appendMessage("assistant", "### VPN\n\n**官方资料**介绍使用方式。[[cite:abc]]", sources);
    assert.equal(body.querySelector("h3").textContent, "VPN");
    assert.equal(body.querySelector("strong").textContent, "官方资料");
    assert.equal(links(body).length, 1);
    assert.ok(!body.textContent.includes("[[cite:"));
    w.renderDiagnosis({ status: "completed", summary: "资料说明[[cite:abc]]", evidence: [], tool_rounds: 1 });
    assert.ok(!w.document.querySelector("#diagnosis-summary").textContent.includes("[[cite:"));
  },
  "CIT-08": async (w) => {
    const answer = "### VPN\n\n资料介绍。[[cite:abc]]\n\n需要核验。[[cite:def]]";
    const live = w.appendMessage("assistant", answer, sources).innerHTML;
    const record = {
      record_id: "citation-record", updated_at: "2026-10-18T00:00:00Z", turn_count: 1,
      conversation_complete: true, diagnosis: null, metrics: null, tool_calls: [step(1)],
      sources: [...sources].reverse(), // Persistent union may have a different order.
      conversation_turns: [{ turn_index: 1, user_message: "VPN", assistant_answer: answer }],
    };
    w.fetch = async () => ({ ok: true, json: async () => record });
    w.document.querySelector("#timeline-section").open = true;
    await w.loadDiagnosisRecord("citation-record");
    const body = w.document.querySelector(".assistant-message .message-body");
    assert.equal(body.innerHTML, live);
    assert.equal(links(body)[0].href, sources[0].source);
    assert.equal(w.document.querySelector("#timeline-section").open, false);
  },
  "CIT-09": async (w) => {
    const answer = "VPN 说明。[[cite:abc]]";
    const payload = { answer, sources, tool_calls: [step(1)], diagnosis: null, metrics: null };
    let index = 0;
    const events = [
      ...["VPN 说明。[[ci", "te:ab", "c]]"].map((text) => `event: delta\ndata: ${JSON.stringify({ text })}\n\n`),
      `event: complete\ndata: ${JSON.stringify({ response: payload })}\n\n`,
    ];
    w.fetch = async (url) => url.startsWith("/api/diagnoses?")
      ? { ok: true, json: async () => ({ items: [] }) }
      : { ok: true, headers: { get: () => "text/event-stream" }, body: { getReader: () => ({ read: async () =>
        index < events.length ? { done: false, value: new TextEncoder().encode(events[index++]) } : { done: true },
      }) } };
    w.document.querySelector("#timeline-section").open = true;
    w.document.querySelector("#message-input").value = "VPN 怎么使用？";
    await w.submitChat({ preventDefault() {} });
    const body = w.document.querySelector(".assistant-message .message-body");
    assert.equal(body.textContent.trim(), "VPN 说明。[1]");
    assert.equal(links(body)[0].href, sources[0].source);
    assert.equal(w.document.querySelector("#timeline-section").open, true);
  },
  "CIT-10": async (w) => {
    assert.equal(w.document.querySelector("#source-list,.source-list,.source-type"), null);
    assert.ok(!w.document.querySelector(".diagnostics-panel").textContent.includes("校园网络来源"));
    assert.ok(!w.document.querySelector(".diagnostics-panel").textContent.includes("参考知识"));
    assert.equal(typeof w.renderSources, "undefined");
  },
});

module.exports = { setup, step, sources };
if (require.main === module) (async () => {
  const selected = process.argv[2] ? [process.argv[2]] : Object.keys(cases);
  for (const name of selected) {
    const dom = await setup();
    try { await cases[name](dom.window); console.log(`${name} passed`); }
    finally { dom.window.close(); }
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
