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
  querySelectorAll() { return []; }
  querySelector() { return { textContent: "" }; }
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
  if (url.startsWith("/api/diagnoses?")) {
    if (delayNextHistory) {
      delayNextHistory = false;
      return new Promise((resolve) => { releaseHistory = resolve; });
    }
    return response(200, { items: [], next_cursor: null });
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

  delayNextHistory = true;
  const oldHistoryRequest = get("history-refresh").handlers.click();
  await tick();
  assert.ok(releaseHistory);
  await get("logout-button").handlers.click();
  assert.equal(get("auth-gate").hidden, false);
  assert.equal(get("workspace").hidden, true);
  assert.equal(vm.runInContext("state.sessionId", context), null);
  assert.equal(get("account-name").textContent, "");
  assert.equal(get("report-content").textContent, "");

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
  process.stdout.write("9C Web runtime state flow passed\n");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
