"use strict";

const serviceState = document.querySelector("#service-state");
const apiStatus = document.querySelector("#api-status");
const llmStatus = document.querySelector("#llm-status");
const ragStatus = document.querySelector("#rag-status");
const toolMode = document.querySelector("#tool-mode");

function renderHealth(health) {
  serviceState.classList.add("online");
  serviceState.firstElementChild?.classList.add("online");
  serviceState.lastChild.textContent = " 后端服务正常";
  apiStatus.textContent = health.status === "ok" ? "正常" : "异常";
  llmStatus.textContent = health.llm_configured ? "已配置" : "未配置";
  ragStatus.textContent = health.rag_ready ? "已就绪" : "尚未构建";
  toolMode.textContent = `${String(health.tool_mode).toUpperCase()} 模式`;
}

function renderHealthError() {
  serviceState.classList.add("offline");
  serviceState.firstElementChild?.classList.add("offline");
  serviceState.lastChild.textContent = " 无法连接后端";
  apiStatus.textContent = "不可用";
  llmStatus.textContent = "未知";
  ragStatus.textContent = "未知";
  toolMode.textContent = "离线";
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Health request failed with ${response.status}`);
    }
    renderHealth(await response.json());
  } catch (_error) {
    renderHealthError();
  }
}

loadHealth();
