const boot = window.__BOOTSTRAP__ || {};
const STAGE_ORDER = ["plan", "design", "tasks", "implement", "test", "review", "docs", "close"];
let currentState = boot.state || {};
let currentConfig = boot.config || {};
let currentRunId = currentState.run_id || null;
let activeTab = currentState.current_stage || "plan";
let source = null;
let lastPendingSignature = null;
let refreshTimer = null;
let previewRequestId = 0;
let lastKnownCurrentStage = currentState.current_stage || "plan";

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let message = await res.text();
    try {
      const parsed = JSON.parse(message);
      message = parsed.detail || message;
    } catch (_error) {
      // plain text response
    }
    throw new Error(message);
  }
  return res.json();
}

function renderTabs() {
  const host = document.getElementById("tab-bar");
  host.innerHTML = "";
  [...STAGE_ORDER, "settings"].forEach((tab) => {
    const button = document.createElement("button");
    button.className = `tab ${activeTab === tab ? "active" : ""}`;
    button.textContent = tab;
    button.addEventListener("click", () => {
      activeTab = tab;
      syncView();
    });
    host.appendChild(button);
  });
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderStageSummary(stages = {}) {
  const stage = stages[activeTab] || stages[currentState.current_stage] || {};
  const target = activeTab === "settings" ? currentState.current_stage : activeTab;
  document.getElementById("stage-title").textContent = `${target} stage`;
  document.getElementById("log-stage-label").textContent = `focused: ${target}`;
  document.getElementById("stage-summary").innerHTML = `
    <div class="metric"><span>Status</span><strong>${escapeHtml(stage.status || "-")}</strong></div>
    <div class="metric"><span>Agent</span><strong>${escapeHtml(stage.agent_used || currentConfig?.agents?.stages?.[target] || "-")}</strong></div>
    <div class="metric"><span>Iteration</span><strong>${escapeHtml(stage.iteration ?? "-")}</strong></div>
    <div class="metric"><span>Document</span><strong>${escapeHtml(stage.doc_path || "-")}</strong></div>
    <div class="metric"><span>Output</span><strong>${escapeHtml(stage.output || "-")}</strong></div>
  `;
  renderPlanEntry(target);
  renderResultPreview(target, stage);
}

function getNextStage(stage) {
  const index = STAGE_ORDER.indexOf(stage);
  if (index === -1 || index === STAGE_ORDER.length - 1) {
    return stage;
  }
  return STAGE_ORDER[index + 1];
}

async function renderResultPreview(target, stage) {
  const box = document.getElementById("result-box");
  if (!target || target === "settings") {
    box.innerHTML = "<p class=\"empty-copy\">선택된 단계가 없습니다.</p>";
    return;
  }
  const currentId = ++previewRequestId;
  const fallback = stage?.output || "";
  if (!fallback && !stage?.doc_path) {
    box.innerHTML = "<p class=\"empty-copy\">아직 표시할 결과물이 없습니다.</p>";
    return;
  }
  try {
    const data = await fetchJSON(`/docs/${target}`);
    if (currentId !== previewRequestId) return;
    box.innerHTML = data.html || "<p class=\"empty-copy\">아직 표시할 결과물이 없습니다.</p>";
  } catch (_error) {
    if (currentId !== previewRequestId) return;
    box.innerHTML = `<pre class="raw-preview">${escapeHtml(fallback)}</pre>`;
  }
}

function renderPlanEntry(target) {
  const host = document.getElementById("plan-entry");
  if (target !== "plan") {
    host.innerHTML = "";
    return;
  }
  host.innerHTML = `
    <div class="composer">
      <label for="plan-idea" class="composer-label">Idea / Feature</label>
      <textarea id="plan-idea" placeholder="만들고 싶은 기능이나 제품 아이디어를 입력하세요.">${escapeHtml(currentState.idea || "")}</textarea>
      <div class="row">
        <button id="save-idea" class="ghost">Save Idea</button>
        <button id="start-plan">Start Plan</button>
      </div>
    </div>
  `;
  document.getElementById("save-idea").addEventListener("click", saveIdeaOnly);
  document.getElementById("start-plan").addEventListener("click", startPlanRun);
}

function renderAgentSettings() {
  const host = document.getElementById("agent-settings");
  const stages = currentConfig?.agents?.stages || {};
  host.innerHTML = "";
  STAGE_ORDER.forEach((stage) => {
    const row = document.createElement("label");
    row.className = "agent-row";
    row.innerHTML = `
      <span>${stage}</span>
      <select data-stage="${stage}">
        <option value="claude">claude</option>
        <option value="codex">codex</option>
        <option value="coderabbit">coderabbit</option>
      </select>
    `;
    const select = row.querySelector("select");
    select.value = stages[stage] || "claude";
    select.addEventListener("change", (event) => {
      currentConfig.agents.stages[stage] = event.target.value;
    });
    host.appendChild(row);
  });
}

function appendLog(line) {
  const log = document.getElementById("log-box");
  log.textContent += `${line}\n`;
  log.scrollTop = log.scrollHeight;
}

function renderPending(action) {
  const box = document.getElementById("pending-box");
  if (!action) {
    box.className = "pending empty";
    box.textContent = "현재 대기 중인 액션이 없습니다.";
    lastPendingSignature = null;
    return;
  }
  const signature = JSON.stringify({
    type: action.type,
    stage: action.stage,
    prompt: action.prompt,
    context: action.context,
  });
  const activeElement = document.activeElement;
  const editingPending =
    activeElement &&
    (activeElement.id === "pending-input" || activeElement.id === "pending-notes");
  if (editingPending && signature === lastPendingSignature) {
    return;
  }
  lastPendingSignature = signature;
  box.className = "pending";
  const html = [
    `<div class="activity-line"><strong>${escapeHtml(action.type)}</strong><span>${escapeHtml(action.stage || "-")}</span></div>`,
    `<p class="small">상세 프롬프트는 로그에서 확인할 수 있습니다.</p>`,
  ];
  if (action.type === "approval") {
    html.push(`<textarea id="pending-notes" placeholder="메모"></textarea>`);
    html.push(`<div class="row"><button data-action="approve">Approve</button><button data-action="reject" class="ghost">Reject</button></div>`);
  } else if (action.type === "retry_decision") {
    html.push(`<div class="row"><button data-action="retry">Retry</button><button data-action="skip" class="ghost">Skip</button></div>`);
  } else if (action.type === "decision") {
    html.push(`<textarea id="pending-input" placeholder="필요하면 간단한 지시사항만 입력"></textarea>`);
    html.push(`<div class="row"><button data-action="proceed">Proceed</button><button data-action="cancel" class="ghost">Cancel</button></div>`);
  } else {
    html.push(`<textarea id="pending-input" placeholder="응답"></textarea>`);
    html.push(`<div class="row"><button data-action="submit">Submit</button></div>`);
  }
  box.innerHTML = html.join("");
  box.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => submitPending(action.stage, button.dataset.action));
  });
}

async function submitPending(stage, kind) {
  const notes = document.getElementById("pending-notes")?.value || "";
  const text = document.getElementById("pending-input")?.value || "";
  const requestId = currentState.pending_action?.request_id || null;
  try {
    if (kind === "approve") {
      await fetchJSON(`/stages/${stage}/approve`, { method: "POST", body: JSON.stringify({ notes, request_id: requestId }) });
    } else if (kind === "reject") {
      await fetchJSON(`/stages/${stage}/reject`, { method: "POST", body: JSON.stringify({ reason: notes, request_id: requestId }) });
    } else if (kind === "retry") {
      await fetchJSON(`/stages/${stage}/input`, { method: "POST", body: JSON.stringify({ retry: true, request_id: requestId }) });
    } else if (kind === "skip") {
      await fetchJSON(`/stages/${stage}/input`, { method: "POST", body: JSON.stringify({ retry: false, request_id: requestId }) });
    } else if (kind === "proceed") {
      await fetchJSON(`/stages/${stage}/input`, { method: "POST", body: JSON.stringify({ proceed: true, instruction: text, request_id: requestId }) });
    } else if (kind === "cancel") {
      await fetchJSON(`/stages/${stage}/input`, { method: "POST", body: JSON.stringify({ proceed: false, request_id: requestId }) });
    } else {
      await fetchJSON(`/stages/${stage}/input`, { method: "POST", body: JSON.stringify({ text, request_id: requestId }) });
    }
  } catch (error) {
    document.getElementById("pending-box").innerHTML = `<div class="error-box">${escapeHtml(error.message)}</div>`;
  }
  lastPendingSignature = null;
  await refresh();
}

async function refresh() {
  const activeElement = document.activeElement;
  const isEditing =
    activeElement &&
    ["pending-input", "pending-notes", "plan-idea", "jira-url", "jira-email", "jira-token", "jira-project"].includes(activeElement.id);
  if (isEditing) {
    return;
  }
  const data = await fetchJSON("/runs/current");
  currentState = data.state;
  document.getElementById("run-status").textContent = currentState.run_status;
  document.getElementById("current-stage").textContent = currentState.current_stage;
  const focusedStage = activeTab === "settings" ? lastKnownCurrentStage : activeTab;
  const focusedState = data.stages?.[focusedStage];
  if (
    activeTab !== "settings" &&
    focusedStage &&
    focusedState?.status === "approved" &&
    currentState.current_stage &&
    focusedStage !== currentState.current_stage
  ) {
    activeTab = currentState.current_stage;
  }
  lastKnownCurrentStage = currentState.current_stage || lastKnownCurrentStage;
  if (![...STAGE_ORDER, "settings"].includes(activeTab)) {
    activeTab = currentState.current_stage || "plan";
  }
  renderStageSummary(data.stages);
  renderPending(data.state.pending_action);
  if (data.state.log_tail) {
    document.getElementById("log-box").textContent = data.state.log_tail.join("\n");
  }
  if (data.state.run_id && data.state.run_id !== currentRunId) {
    currentRunId = data.state.run_id;
    connectEvents();
  }
  syncView();
  ensurePolling();
}

async function refreshConfig() {
  currentConfig = await fetchJSON("/config");
  document.getElementById("jira-enabled").checked = !!currentConfig?.jira?.enabled;
  document.getElementById("jira-url").value = currentConfig?.jira?.url || "";
  document.getElementById("jira-email").value = currentConfig?.jira?.email || "";
  document.getElementById("jira-token").value = currentConfig?.jira?.api_token || "";
  document.getElementById("jira-project").value = currentConfig?.jira?.project_key || "";
  renderAgentSettings();
  syncView();
}

async function saveIdeaOnly() {
  const idea = document.getElementById("plan-idea")?.value || "";
  await fetchJSON("/idea", { method: "POST", body: JSON.stringify({ idea }) });
  currentState.idea = idea || null;
  renderStageSummary(currentState.stages || {});
}

async function startPlanRun() {
  const idea = document.getElementById("plan-idea")?.value || "";
  await fetchJSON("/idea", { method: "POST", body: JSON.stringify({ idea }) });
  currentState.idea = idea || null;
  const data = await fetchJSON("/runs", {
    method: "POST",
    body: JSON.stringify({ from_stage: "plan", force: true }),
  });
  currentRunId = data.run_id;
  document.getElementById("log-box").textContent = "";
  connectEvents();
  await refresh();
}

function syncView() {
  document.getElementById("stage-view").classList.toggle("active", activeTab !== "settings");
  document.getElementById("settings-view").classList.toggle("active", activeTab === "settings");
  renderTabs();
  if (activeTab !== "settings") {
    lastKnownCurrentStage = activeTab;
    renderStageSummary(currentState.stages || {});
  }
}

function connectEvents() {
  if (!currentRunId) return;
  if (source) source.close();
  source = new EventSource(`/runs/${currentRunId}/events`);
  source.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "stage_started" && payload.stage && activeTab !== "settings") {
      activeTab = payload.stage;
      lastKnownCurrentStage = payload.stage;
    }
    if (payload.message) appendLog(payload.message);
    refresh();
    if (payload.type === "run_finished") {
      source.close();
      source = null;
    }
  };
  source.onerror = () => {
    source.close();
    source = null;
  };
}

function ensurePolling() {
  const shouldPoll = ["running", "waiting_input"].includes(currentState.run_status);
  if (shouldPoll && !refreshTimer) {
    refreshTimer = setInterval(refresh, 5000);
    return;
  }
  if (!shouldPoll && refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

document.getElementById("start-run").addEventListener("click", async () => {
  const payload = {
    stage: document.getElementById("run-stage").value || null,
    from_stage: document.getElementById("run-from").value || null,
    to_stage: document.getElementById("run-to").value || null,
    force: document.getElementById("run-force").checked,
  };
  const data = await fetchJSON("/runs", { method: "POST", body: JSON.stringify(payload) });
  currentRunId = data.run_id;
  document.getElementById("log-box").textContent = "";
  connectEvents();
  refresh();
});

document.getElementById("stop-run").addEventListener("click", async () => {
  if (!currentRunId) return;
  await fetchJSON(`/runs/${currentRunId}/stop`, { method: "POST" });
});

document.getElementById("jira-test").addEventListener("click", async () => {
  const payload = {
    enabled: document.getElementById("jira-enabled").checked,
    url: document.getElementById("jira-url").value,
    email: document.getElementById("jira-email").value,
    api_token: document.getElementById("jira-token").value,
    project_key: document.getElementById("jira-project").value,
  };
  const data = await fetchJSON("/jira/test", { method: "POST", body: JSON.stringify(payload) });
  document.getElementById("jira-result").textContent = JSON.stringify(data, null, 2);
});

document.getElementById("jira-create").addEventListener("click", async () => {
  const data = await fetchJSON("/jira/create-from-tasks", { method: "POST", body: JSON.stringify({}) });
  document.getElementById("jira-result").textContent = JSON.stringify(data, null, 2);
  refresh();
});

document.getElementById("save-config").addEventListener("click", async () => {
  currentConfig.jira = {
    enabled: document.getElementById("jira-enabled").checked,
    url: document.getElementById("jira-url").value || null,
    email: document.getElementById("jira-email").value || null,
    api_token: document.getElementById("jira-token").value || null,
    project_key: document.getElementById("jira-project").value || null,
  };
  await fetchJSON("/config", { method: "POST", body: JSON.stringify(currentConfig) });
  document.getElementById("jira-result").textContent = "config saved";
  await refreshConfig();
  await refresh();
});

renderTabs();
renderAgentSettings();
renderPending(currentState.pending_action);
renderStageSummary(currentState.stages || {});
if (currentRunId && ["running", "waiting_input"].includes(currentState.run_status)) {
  connectEvents();
}
ensurePolling();
