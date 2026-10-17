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
  "SRC-04": async (w) => {
    const sources = ["official", "community", "maintainer"].map((source_type, index) => ({
      source_type, title: `资料 ${index}`, source: `https://example.test/${index}`,
      score: .9 - index / 10, file: `file-${index}.md`, chunk_id: `chunk-${index}`,
    }));
    w.renderSources(sources);
    const panel = w.document.querySelector("#source-list");
    assert.equal(panel.querySelectorAll("li").length, 3);
    for (const source of sources) {
      for (const value of [source.source_type, source.title, source.source, source.file, source.chunk_id, source.score.toFixed(3)]) {
        assert.ok(panel.textContent.includes(value));
      }
    }
    for (const link of panel.querySelectorAll("a")) {
      assert.equal(link.target, "_blank");
      assert.equal(link.rel, "noopener noreferrer");
    }
  },
};

(async () => {
  const selected = process.argv[2] ? [process.argv[2]] : Object.keys(cases);
  for (const name of selected) {
    const dom = await setup();
    try { await cases[name](dom.window); console.log(`${name} passed`); }
    finally { dom.window.close(); }
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
