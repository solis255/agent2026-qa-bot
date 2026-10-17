"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor(id) {
    this.id = id;
    this.hidden = ["workspace", "account-menu"].includes(id);
    this.value = "";
    this.textContent = "";
    this.className = "";
    this.dataset = {};
    this.children = [];
    this.handlers = {};
    this.open = false;
    this.disabled = false;
    this.classList = { add() {}, remove() {} };
  }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  setAttribute(name, value) { this[name] = value; }
  removeAttribute(name) { delete this[name]; }
  replaceChildren(...children) { this.children = children; }
  append(...children) { this.children.push(...children); }
  querySelectorAll(selector) {
    const found = [];
    for (const child of this.children) {
      if (child.id === selector || (selector.startsWith(".") && child.className === selector.slice(1))) found.push(child);
      found.push(...child.querySelectorAll(selector));
    }
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || { textContent: "" }; }
  reportValidity() { return true; }
  reset() {
    const ids = this.id === "auth-form"
      ? ["auth-username", "auth-nickname", "auth-password", "auth-confirm"]
      : ["old-password", "new-password", "confirm-new-password"];
    for (const id of ids) elements.get(id).value = "";
  }
  focus() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
  scrollIntoView() {}
  get selectedOptions() { return [{ textContent: "健康" }]; }
}

const elements = new Map();
const get = (id) => {
  if (!elements.has(id)) elements.set(id, new Element(id));
  return elements.get(id);
};
const document = {
  querySelector(selector) { return get(selector.slice(1)); },
  querySelectorAll(selector) {
    return selector === ".register-only"
      ? [get("auth-nickname"), get("auth-confirm"), get("register-label-1"), get("register-label-2")]
      : [];
  },
  createElement(tag) { return new Element(tag); },
  body: new Element("body"),
};

let currentUser = null;
let delayNextHistory = false;
let releaseHistory = null;
let historyRecords = [];
let diagnosisDetail = null;
const calls = [];
const response = (status, payload) => ({
  ok: status >= 200 && status < 300,
  status,
  async json() { return payload; },
});
async function fetch(url, options = {}) {
  calls.push({ url, options });
  if (url === "/api/auth/me") {
    return currentUser ? response(200, currentUser) : response(401, { detail: "请先登录。" });
  }
  if (url === "/api/auth/register" || url === "/api/auth/login") {
    const payload = JSON.parse(options.body);
    currentUser = {
      id: payload.username === "alice" ? "alice-id" : "bob-id",
      username: payload.username,
      nickname: payload.nickname || null,
    };
    return response(url.endsWith("register") ? 201 : 200, currentUser);
  }
  if (url === "/api/auth/change-password") return response(204, null);
  if (url === "/api/auth/logout") {
    currentUser = null;
    return response(204, null);
  }
  if (url === "/api/health") {
    return response(200, {
      status: "ok", llm_configured: false, rag_ready: false,
      history_ready: true, tool_mode: "local",
    });
  }
  if (url === "/api/session") return response(201, { session_id: `${currentUser.id}-session` });
  if (url.startsWith("/api/diagnoses/") && diagnosisDetail) return response(200, diagnosisDetail);
  if (url.startsWith("/api/diagnoses?")) {
    if (delayNextHistory) {
      delayNextHistory = false;
      return new Promise((resolve) => { releaseHistory = resolve; });
    }
    const cursor = new URL(url, "http://test").searchParams.get("cursor");
    const offset = cursor ? Number(cursor) : 0;
    const items = historyRecords.slice(offset, offset + 10);
    return response(200, { items, next_cursor: offset + 10 < historyRecords.length ? String(offset + 10) : null });
  }
  throw new Error(`Unexpected request: ${url}`);
}

const window = {
  setTimeout,
  clearTimeout,
  addEventListener() {},
};
const context = vm.createContext({
  document, window, fetch, URL, AbortController, TextDecoder, Uint8Array,
  console,
});
const source = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
vm.runInContext(source, context, { filename: "web/app.js" });
const tick = () => new Promise((resolve) => setImmediate(resolve));
const submit = (id) => get(id).handlers.submit({ preventDefault() {} });

(async () => {
  await tick();
  assert.equal(get("auth-gate").hidden, false);
  assert.equal(get("workspace").hidden, true);
  assert.equal(calls.some((call) => call.url === "/api/session"), false);

  get("auth-register-tab").handlers.click();
  get("auth-username").value = "alice";
  get("auth-password").value = "test-password-123";
  get("auth-confirm").value = "mismatched-password";
  get("auth-nickname").value = "演示 A";
  await submit("auth-form");
  assert.equal(calls.some((call) => call.url === "/api/auth/register"), false);
  get("auth-confirm").value = "test-password-123";
  await submit("auth-form");
  assert.equal(get("auth-gate").hidden, true);
  assert.equal(get("workspace").hidden, false);
  assert.equal(get("account-name").textContent, "演示 A");
  assert.equal(vm.runInContext("state.sessionId", context), "alice-id-session");

  get("change-password-open").handlers.click();
  get("old-password").value = "test-password-123";
  get("new-password").value = "new-password-456";
  get("confirm-new-password").value = "mismatched-password";
  await submit("password-form");
  assert.equal(calls.some((call) => call.url === "/api/auth/change-password"), false);
  get("confirm-new-password").value = "new-password-456";
  await submit("password-form");
  assert.equal(get("password-dialog").open, false);
  assert.equal(get("old-password").value, "");
  assert.ok(calls.some((call) => call.url === "/api/auth/change-password"));

  diagnosisDetail = {
    record_id: "three-turn-record", session_id: "old-session-no-longer-in-memory",
    updated_at: "2026-10-17T10:00:00Z", turn_count: 3,
    user_message: "U1", latest_user_message: "U3", answer: "A3",
    diagnosis: { status: "completed", summary: "完整会话", tool_rounds: 0, evidence: [] },
    metrics: {}, sources: [], tool_calls: [], conversation_complete: true,
    conversation_turns: [1, 2, 3].map((index) => ({
      turn_index: index, user_message: `U${index}`, assistant_answer: `A${index}`,
    })),
  };
  context.transcriptHistoryItems = [{
    record_id: diagnosisDetail.record_id, user_message: "U1", updated_at: diagnosisDetail.updated_at,
    turn_count: 3, primary_issue: "undetermined", confidence: "low", metrics: {},
  }];
  vm.runInContext("renderHistoryItems(transcriptHistoryItems)", context);
  const transcriptButton = get("history-list").querySelectorAll("button")[0];
  await transcriptButton.handlers.click();
  assert.deepEqual(get("conversation").querySelectorAll("p").map((item) => item.textContent),
    ["U1", "A1", "U2", "A2", "U3", "A3"]);
  assert.equal(vm.runInContext("state.sessionId", context), "alice-id-session");
  assert.ok(!get("interaction-note").textContent.includes("仍可继续使用"));
  diagnosisDetail.conversation_complete = false;
  diagnosisDetail.conversation_turns = [diagnosisDetail.conversation_turns[2]];
  await vm.runInContext('loadDiagnosisRecord("three-turn-record")', context);
  assert.deepEqual(get("conversation").querySelectorAll("p").map((item) => item.textContent), ["U3", "A3"]);
  assert.ok(get("interaction-note").textContent.includes("仅保留部分对话内容"));
  assert.equal(vm.runInContext("state.sessionId", context), "alice-id-session");
  context.testMetrics = { response_mode: "knowledge", fallback_reason: "finalization_failed",
    knowledge_finalization_attempts: 2, knowledge_finalization_failure_kind: "source_only_answer" };
  vm.runInContext("renderMetrics(testMetrics)", context);
  assert.ok(get("metrics-debug").textContent.includes("source_only_answer"));

  historyRecords = Array.from({ length: 25 }, (_, index) => ({
    record_id: `alice-record-${index}`, user_message: `A 的诊断 ${index}`,
    updated_at: "2026-10-17T10:00:00Z", turn_count: 2,
    primary_issue: "dns_resolution_failure", confidence: "high", metrics: {},
  }));
  await get("history-refresh").handlers.click();
  assert.equal(get("history-list").querySelectorAll("li").length, 10);
  assert.equal(get("history-page-label").textContent, "第 1 页");
  assert.equal(get("history-previous").disabled, true);
  await get("history-next").handlers.click();
  assert.equal(get("history-list").querySelectorAll("li").length, 10);
  assert.equal(get("history-page-label").textContent, "第 2 页");
  await get("history-next").handlers.click();
  assert.equal(get("history-list").querySelectorAll("li").length, 5);
  assert.equal(get("history-page-label").textContent, "第 3 页");
  assert.equal(get("history-next").disabled, true);
  const requestCount = calls.length;
  await get("history-previous").handlers.click();
  assert.equal(calls.length, requestCount);
  assert.equal(get("history-list").querySelectorAll("li").length, 10);
  assert.equal(get("history-page-label").textContent, "第 2 页");
  await get("history-next").handlers.click();
  assert.equal(get("history-page-label").textContent, "第 3 页");

  // A saved diagnosis uses this same refresh path and invalidates old cursors.
  await vm.runInContext("loadHistory()", context);
  assert.equal(vm.runInContext("state.historyPageIndex", context), 0);
  assert.equal(vm.runInContext("state.historyPages.length", context), 1);
  assert.equal(get("history-list").querySelectorAll("li").length, 10);
  await get("history-next").handlers.click();
  await get("history-next").handlers.click();
  assert.equal(get("history-page-label").textContent, "第 3 页");

  delayNextHistory = true;
  const oldHistoryRequest = get("history-refresh").handlers.click();
  await tick();
  assert.ok(releaseHistory);
  assert.equal(get("history-previous").disabled, true);
  assert.equal(get("history-next").disabled, true);
  await get("logout-button").handlers.click();
  assert.equal(get("auth-gate").hidden, false);
  assert.equal(get("workspace").hidden, true);
  assert.equal(vm.runInContext("state.sessionId", context), null);
  assert.equal(get("account-name").textContent, "");
  assert.equal(get("report-content").textContent, "");
  assert.equal(vm.runInContext("state.historyPageIndex", context), 0);
  assert.equal(vm.runInContext("state.historyPages.length", context), 0);

  historyRecords = [];
  get("auth-username").value = "bob";
  get("auth-password").value = "test-password-123";
  await submit("auth-form");
  assert.equal(get("account-name").textContent, "bob");
  assert.equal(get("history-list").children[0].className, "empty-state");
  releaseHistory(response(200, {
    items: [{ record_id: "alice-secret", user_message: "A 的私有诊断" }],
    next_cursor: null,
  }));
  await oldHistoryRequest;
  assert.equal(get("history-list").children[0].className, "empty-state");
  assert.equal(vm.runInContext("state.user.id", context), "bob-id");
  assert.ok(calls.every((call) => call.options.credentials === "same-origin"));

  const streamEvents = [];
  context.streamEvents = streamEvents;
  context.fetch = async (_url, options) => {
    const chunks = [
      'id: 0\nevent: start\ndata: {"schema_version":1,"session_id":"test"}\n\n',
      ': keep-alive\n\n',
      'id: 1\nevent: complete\ndata: {"schema_version":1,"response":{"answer":"完成"}}\n\n',
    ].map((item) => Buffer.from(item, "utf8"));
    let index = 0;
    return {
      ok: true,
      status: 200,
      headers: { get(name) { return name === "content-type" ? "text/event-stream" : null; } },
      body: {
        getReader() {
          return {
            async read() {
              await new Promise((resolve) => setTimeout(resolve, 15));
              if (options.signal.aborted) {
                const error = new Error("aborted");
                error.name = "AbortError";
                throw error;
              }
              if (index >= chunks.length) return { value: undefined, done: true };
              return { value: chunks[index++], done: false };
            },
          };
        },
      },
    };
  };
  await vm.runInContext(
    'requestSSE("/api/chat/stream", {method: "POST", body: "{}"}, '
      + 'async (name) => streamEvents.push(name), 25)',
    context,
  );
  assert.deepEqual(streamEvents, ["start", "complete"]);
  process.stdout.write("9C Web runtime state flow passed\n");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
