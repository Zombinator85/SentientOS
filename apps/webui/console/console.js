const overviewGrid = document.getElementById("overview-grid");
const nodesTable = document.querySelector("#nodes-table tbody");
const memoryInfo = document.getElementById("memory-info");
const healthChecks = document.getElementById("health-checks");
const installButton = document.getElementById("install-button");

let deferredPrompt = null;
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredPrompt = event;
  installButton.hidden = false;
});

installButton?.addEventListener("click", async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  await deferredPrompt.userChoice;
  deferredPrompt = null;
  installButton.hidden = true;
});

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`request failed: ${response.status}`);
  const text = await response.text();
  if (!text) return {};
  return JSON.parse(text);
}

function renderMetrics(metrics) {
  overviewGrid.innerHTML = "";
  const items = [
    { label: "Role", value: metrics.role },
    { label: "Model", value: metrics.model },
    { label: "Backend", value: metrics.backend },
    { label: "Uptime", value: `${Math.round(metrics.uptime_seconds)} s` },
    { label: "Dream Loop", value: metrics.dream_loop?.active ? "Active" : "Idle" },
    { label: "Pending Goals", value: metrics.pending_goals },
  ];
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "metric";
    card.innerHTML = `<h3>${item.label}</h3><p>${item.value ?? "–"}</p>`;
    overviewGrid.appendChild(card);
  }
}

function renderNodes(payload) {
  nodesTable.innerHTML = "";
  for (const node of payload.nodes ?? []) {
    const tr = document.createElement("tr");
    const capabilities = Object.keys(node.capabilities || {}).join(", ") || "–";
    const voice = node.last_voice_activity ? new Date(node.last_voice_activity * 1000).toLocaleTimeString() : "–";
    tr.innerHTML = `
      <td>${node.hostname}</td>
      <td>${node.trust_level}</td>
      <td>${capabilities}</td>
      <td>${voice}</td>
    `;
    nodesTable.appendChild(tr);
  }
}

function renderMemory(summary) {
  memoryInfo.innerHTML = "";
  const fragment = document.createElement("pre");
  fragment.textContent = JSON.stringify(summary, null, 2);
  memoryInfo.appendChild(fragment);
}

function renderHealth(snapshot) {
  healthChecks.innerHTML = "";
  for (const check of snapshot.checks ?? []) {
    const div = document.createElement("div");
    div.className = "health-row";
    div.innerHTML = `
      <span>${check.name}</span>
      <span class="status">${check.healthy ? "✅" : "⚠️"}</span>
    `;
    healthChecks.appendChild(div);
  }
  if (!snapshot.checks?.length) {
    const fallback = document.createElement("p");
    fallback.textContent = "No watchdog checks registered yet.";
    healthChecks.appendChild(fallback);
  }
}

async function refreshAll() {
  try {
    const status = await fetchJson("/admin/status", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderMetrics(status);
    const nodes = await fetchJson("/admin/nodes", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderNodes(nodes);
    const memory = await fetchJson("/admin/memory/summary", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderMemory(memory);
    const health = await fetchJson("/admin/health", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderHealth(health.watchdog ?? health);
  } catch (error) {
    console.warn("Failed to refresh console", error);
  }
}

refreshAll();
setInterval(refreshAll, 10000);
